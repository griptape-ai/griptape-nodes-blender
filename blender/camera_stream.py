import json
import requests
import time
import threading
from typing import Optional, Any

from griptape.artifacts import ImageUrlArtifact, ErrorArtifact
from griptape_nodes.traits.options import Options

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterGroup
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger, GriptapeNodes


class BlenderCameraStream(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "Blender"
        self.description = "Provides real-time streaming from a Blender camera."
        self.metadata["author"] = "Griptape"
        self.metadata["dependencies"] = {"pip_dependencies": ["requests"]}
        
        # Stream control
        self._streaming = False
        self._stream_thread = None
        self._frame_count = 0

        # Camera list input (optional - for connecting to BlenderCameraList node)
        self.add_parameter(
            Parameter(
                name="cameras_input",
                tooltip="Camera list from BlenderCameraList node (optional)",
                type="ListArtifact",
                input_types=["ListArtifact"],
                allowed_modes={ParameterMode.INPUT}
            )
        )

        # Camera Settings Group
        with ParameterGroup(name="Camera Settings") as camera_group:
            Parameter(
                name="camera_name",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value="Camera",
                tooltip="Name of the camera in the Blender scene to stream from.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self._get_available_cameras())},
                ui_options={"display_name": "Camera"}
            )
        self.add_node_element(camera_group)

        # Stream Settings Group
        with ParameterGroup(name="Stream Settings") as stream_group:
            Parameter(
                name="frame_rate",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=5,
                tooltip="Capture rate in frames per second (1-15, capped for GPU stability).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"min": 1, "max": 15, "display_name": "Frame Rate (FPS)"}
            )
            Parameter(
                name="output_format",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value="JPEG",
                tooltip="Output image format for stream frames (JPEG recommended for speed).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["JPEG", "PNG", "TIFF"])},
                ui_options={"display_name": "Format"}
            )
            Parameter(
                name="resolution_x",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=1280,
                tooltip="Stream width in pixels (lower for better performance).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"min": 64, "max": 3840, "display_name": "Width"}
            )
            Parameter(
                name="resolution_y",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=720,
                tooltip="Stream height in pixels (lower for better performance).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"min": 64, "max": 2160, "display_name": "Height"}
            )
            Parameter(
                name="quality",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=75,
                tooltip="Image quality for JPEG format (lower for better performance).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"min": 10, "max": 100, "display_name": "Quality"}
            )
        self.add_node_element(stream_group)

        # Control Parameters
        self.add_parameter(
            Parameter(
                name="start_stream",
                input_types=["bool"],
                output_type="bool",
                type="bool",
                default_value=False,
                tooltip="Start or stop the camera stream.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Start Stream"}
            )
        )

        # Output Parameters
        self.add_parameter(
            Parameter(
                name="frame_output",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Latest captured frame from the stream.",
                ui_options={"pulse_on_run": True}
            )
        )
        self.add_parameter(
            Parameter(
                name="frame_count",
                output_type="int",
                type="int",
                default_value=0,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Total number of frames captured in this stream session."
            )
        )
        self.add_parameter(
            Parameter(
                name="status_output",
                output_type="str",
                type="str",
                default_value="Stream stopped",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Current stream status and performance information.",
                ui_options={"multiline": True}
            )
        )

    def _get_mcp_server_url(self) -> str:
        """Get the MCP server URL from configuration."""
        host = self.get_config_value("Blender", "BLENDER_MCP_HOST") or "localhost"
        port = self.get_config_value("Blender", "BLENDER_MCP_PORT") or "8080"
        return f"http://{host}:{port}"

    def _get_available_cameras(self) -> list[str]:
        """Fetch available cameras from the Blender MCP server."""
        try:
            url = f"{self._get_mcp_server_url()}/api/cameras"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                cameras = response.json().get("cameras", [])
                return [camera["name"] for camera in cameras] if cameras else ["Camera"]
            else:
                logger.warning(f"Blender MCP server returned status {response.status_code}")
                return ["Camera"]
        except Exception as e:
            logger.warning(f"Could not fetch cameras from Blender MCP server: {e}")
            return ["Camera"]

    def _check_blender_connection(self) -> tuple[bool, str]:
        """Check if Blender MCP server is available."""
        try:
            url = f"{self._get_mcp_server_url()}/api/status"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                status_data = response.json()
                return True, f"Connected to Blender {status_data.get('blender_version', 'Unknown')}"
            else:
                return False, f"Blender MCP server returned status {response.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to Blender MCP server. Make sure Blender is running with the MCP server."
        except Exception as e:
            return False, f"Error connecting to Blender: {str(e)}"

    def _capture_frame(self) -> tuple[ImageUrlArtifact | None, str]:
        """Capture a single frame from the camera."""
        try:
            # Get parameters
            camera_name = self.get_parameter_value("camera_name") or "Camera"
            output_format = self.get_parameter_value("output_format") or "JPEG"
            resolution_x = self.get_parameter_value("resolution_x") or 1280
            resolution_y = self.get_parameter_value("resolution_y") or 720
            quality = self.get_parameter_value("quality") or 75

            # If cameras_input is connected, validate camera_name exists in the list
            cameras_input = self.get_parameter_value("cameras_input")
            if cameras_input and hasattr(cameras_input, 'value'):
                available_cameras = [cam.get('name', '') for cam in cameras_input.value if isinstance(cam, dict)]
                if camera_name not in available_cameras and available_cameras:
                    camera_name = available_cameras[0]  # Use first available camera

            # Prepare capture request
            capture_params = {
                "format": output_format.lower(),
                "width": resolution_x,
                "height": resolution_y,
                "quality": quality if output_format.upper() == "JPEG" else None
            }

            # Remove None values
            capture_params = {k: v for k, v in capture_params.items() if v is not None}

            # Make capture request
            url = f"{self._get_mcp_server_url()}/api/camera/{camera_name}/render"
            response = requests.get(url, params=capture_params, timeout=5)

            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                
                if 'application/json' in content_type:
                    # Error response
                    error_data = response.json()
                    return None, f"Error: {error_data.get('error', 'Unknown error from Blender')}"
                
                elif 'image/' in content_type:
                    # Successful image response
                    image_data = response.content
                    
                    # Save image using StaticFilesManager
                    file_extension = output_format.lower()
                    filename = f"blender_stream_{camera_name}_{self._frame_count:06d}.{file_extension}"
                    
                    static_url = GriptapeNodes.StaticFilesManager().save_static_file(
                        image_data, filename
                    )
                    
                    return ImageUrlArtifact(static_url, name=f"stream_frame_{self._frame_count}"), "Frame captured"
                
                else:
                    return None, f"Unexpected response content type: {content_type}"
            
            else:
                return None, f"Server returned status {response.status_code}: {response.text}"

        except Exception as e:
            return None, f"Failed to capture frame: {str(e)}"

    def _stream_worker(self):
        """Background thread worker for continuous streaming."""
        frame_rate = self.get_parameter_value("frame_rate") or 5
        # Limit max frame rate to prevent GPU overload
        frame_rate = min(frame_rate, 15)  # Cap at 15 FPS for stability
        frame_interval = 1.0 / frame_rate
        
        last_capture_time = 0
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self._streaming:
            current_time = time.time()
            
            # Check if it's time for the next frame
            if current_time - last_capture_time >= frame_interval:
                # Add small delay to prevent GPU resource exhaustion
                time.sleep(0.05)  # 50ms delay between renders
                
                frame_artifact, status_msg = self._capture_frame()
                
                if frame_artifact:
                    consecutive_errors = 0  # Reset error counter
                    self._frame_count += 1
                    self.parameter_output_values["frame_output"] = frame_artifact
                    self.parameter_output_values["frame_count"] = self._frame_count
                    
                    # Update status with performance info
                    actual_fps = 1.0 / (current_time - last_capture_time) if last_capture_time > 0 else 0
                    status = f"Streaming at {actual_fps:.1f} FPS | Frame {self._frame_count} | {status_msg}"
                    self.parameter_output_values["status_output"] = status
                    
                    # Publish progress event for real-time updates
                    self.publish_update_to_parameter("frame_output", frame_artifact)
                    self.publish_update_to_parameter("frame_count", self._frame_count)
                    self.publish_update_to_parameter("status_output", status)
                else:
                    # Error occurred - implement backoff
                    consecutive_errors += 1
                    error_status = f"Stream error: {status_msg} (Error {consecutive_errors}/{max_consecutive_errors})"
                    self.parameter_output_values["status_output"] = error_status
                    self.publish_update_to_parameter("status_output", error_status)
                    
                    # Stop streaming if too many consecutive errors
                    if consecutive_errors >= max_consecutive_errors:
                        self._streaming = False
                        final_error = f"Stream stopped due to {consecutive_errors} consecutive errors. Last error: {status_msg}"
                        self.parameter_output_values["status_output"] = final_error
                        self.publish_update_to_parameter("status_output", final_error)
                        break
                    
                    # Exponential backoff for errors
                    time.sleep(min(0.5 * (2 ** consecutive_errors), 5.0))
                
                last_capture_time = current_time
            
            # Longer sleep to prevent excessive CPU usage and give GPU time to recover
            time.sleep(0.1)  # Increased from 0.01 to 0.1

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that Blender MCP server is available before running."""
        is_connected, message = self._check_blender_connection()
        if not is_connected:
            return [ConnectionError(message)]
        return None

    def process(self):
        """Start or stop the camera stream based on the start_stream parameter."""
        def stream_control_async():
            try:
                start_stream = self.get_parameter_value("start_stream")
                
                if start_stream and not self._streaming:
                    # Start streaming
                    self._streaming = True
                    self._frame_count = 0
                    self._stream_thread = threading.Thread(target=self._stream_worker, daemon=True)
                    self._stream_thread.start()
                    
                    camera_name = self.get_parameter_value("camera_name") or "Camera"
                    frame_rate = self.get_parameter_value("frame_rate") or 5
                    
                    status = f"Started streaming from camera '{camera_name}' at {frame_rate} FPS"
                    self.parameter_output_values["status_output"] = status
                    
                    return status
                
                elif not start_stream and self._streaming:
                    # Stop streaming
                    self._streaming = False
                    if self._stream_thread:
                        self._stream_thread.join(timeout=2.0)
                    
                    status = f"Stream stopped. Captured {self._frame_count} frames total."
                    self.parameter_output_values["status_output"] = status
                    
                    return status
                
                elif start_stream and self._streaming:
                    status = f"Stream already running. Captured {self._frame_count} frames."
                    return status
                
                else:
                    status = "Stream is stopped."
                    return status

            except Exception as e:
                error_msg = f"Stream control error: {str(e)}"
                logger.error(f"BlenderCameraStream error: {error_msg}")
                self.parameter_output_values["status_output"] = error_msg
                return error_msg

        yield stream_control_async

    def after_incoming_connection(self, source_node, source_parameter, target_parameter, modified_parameters_set=None):
        """Refresh camera list when connections are made."""
        if target_parameter.name == "camera_name":
            # Refresh available cameras
            cameras = self._get_available_cameras()
            if cameras:
                # Update the Options trait with new camera list
                camera_param = self.get_parameter_by_name("camera_name")
                if camera_param and camera_param.traits:
                    for trait in camera_param.traits:
                        if hasattr(trait, 'choices'):
                            trait.choices = cameras
                            break

    def __del__(self):
        """Cleanup: stop streaming when node is destroyed."""
        if self._streaming:
            self._streaming = False
            if self._stream_thread:
                self._stream_thread.join(timeout=1.0) 