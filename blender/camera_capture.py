import json
import requests
import base64
from typing import Optional, Any
from io import BytesIO
import time

from griptape.artifacts import ImageArtifact, ImageUrlArtifact, ErrorArtifact, TextArtifact
from griptape_nodes.traits.options import Options

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterGroup
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger, GriptapeNodes


class BlenderCameraCapture(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "Blender"
        self.description = "Captures a single frame from a Blender camera via MCP server."
        self.metadata["author"] = "Griptape"
        self.metadata["dependencies"] = {"pip_dependencies": ["requests", "mcp"]}

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
                tooltip="Name of the camera in the Blender scene to capture from.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self._get_available_cameras())},
                ui_options={"display_name": "Camera"}
            )
        self.add_node_element(camera_group)

        # Output Settings Group
        with ParameterGroup(name="Output Settings") as output_group:
            Parameter(
                name="output_format",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value="PNG",
                tooltip="Output image format for the captured frame.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["PNG", "JPEG", "EXR", "TIFF"])},
                ui_options={"display_name": "Format"}
            )
            Parameter(
                name="resolution_x",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=1920,
                tooltip="Output image width in pixels.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"min": 64, "max": 7680, "display_name": "Width"}
            )
            Parameter(
                name="resolution_y",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=1080,
                tooltip="Output image height in pixels.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"min": 64, "max": 4320, "display_name": "Height"}
            )
            Parameter(
                name="quality",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=90,
                tooltip="Image quality (0-100, applies to JPEG format).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"min": 1, "max": 100, "display_name": "Quality"}
            )
        self.add_node_element(output_group)

        # Output Parameters
        self.add_parameter(
            Parameter(
                name="image_output",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Captured image from the Blender camera.",
                ui_options={"pulse_on_run": True, "is_full_width": True}
            )
        )
        self.add_parameter(
            Parameter(
                name="status_output",
                output_type="str",
                type="str",
                default_value="",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Status message from the capture operation.",
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

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that Blender MCP server is available before running."""
        is_connected, message = self._check_blender_connection()
        if not is_connected:
            return [ConnectionError(message)]
        return None

    def process(self):
        """Capture a frame from the specified Blender camera."""
        def capture_frame_async():
            try:
                # Get parameters
                camera_name = self.get_parameter_value("camera_name") or "Camera"
                output_format = self.get_parameter_value("output_format") or "PNG"
                resolution_x = self.get_parameter_value("resolution_x") or 1920
                resolution_y = self.get_parameter_value("resolution_y") or 1080
                quality = self.get_parameter_value("quality") or 90

                # If cameras_input is connected, validate camera_name exists in the list
                cameras_input = self.get_parameter_value("cameras_input")
                if cameras_input and hasattr(cameras_input, 'value'):
                    available_cameras = [cam.get('name', '') for cam in cameras_input.value if isinstance(cam, dict)]
                    if camera_name not in available_cameras and available_cameras:
                        camera_name = available_cameras[0]  # Use first available camera

                # Update status
                self.parameter_output_values["status_output"] = f"Capturing frame from camera '{camera_name}'..."

                # Add delay between captures to prevent GPU overload
                time.sleep(0.2)  # 200ms delay for stability

                # Prepare capture request with enhanced error handling
                capture_params = {
                    "format": output_format.lower(),
                    "width": min(resolution_x, 1920),  # Cap resolution for stability
                    "height": min(resolution_y, 1080),  # Cap resolution for stability
                    "quality": quality if output_format.upper() == "JPEG" else None
                }

                # Remove None values
                capture_params = {k: v for k, v in capture_params.items() if v is not None}

                # Make capture request with longer timeout and retry logic
                url = f"{self._get_mcp_server_url()}/api/camera/{camera_name}/render"
                
                max_retries = 2
                retry_delay = 1.0
                
                for attempt in range(max_retries + 1):
                    try:
                        if attempt > 0:
                            self.parameter_output_values["status_output"] = f"Retrying capture (attempt {attempt + 1}/{max_retries + 1})..."
                            time.sleep(retry_delay * attempt)  # Exponential backoff
                        
                        response = requests.get(url, params=capture_params, timeout=45)  # Increased timeout
                        break  # Success, exit retry loop
                        
                    except requests.exceptions.Timeout:
                        if attempt == max_retries:
                            error_msg = "Timeout: Blender render took too long (>45s)"
                            self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                            return ErrorArtifact(error_msg)
                        continue
                        
                    except requests.exceptions.ConnectionError:
                        if attempt == max_retries:
                            error_msg = "Connection error: Cannot reach Blender MCP server"
                            self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                            return ErrorArtifact(error_msg)
                        continue
                        
                    except Exception as req_error:
                        if attempt == max_retries:
                            error_msg = f"Request failed: {str(req_error)}"
                            self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                            return ErrorArtifact(error_msg)
                        continue

                if response.status_code == 200:
                    # Check if response is JSON (error) or binary (image)
                    content_type = response.headers.get('content-type', '')
                    
                    if 'application/json' in content_type:
                        # Error response
                        error_data = response.json()
                        error_msg = error_data.get('error', 'Unknown error from Blender')
                        self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                        return ErrorArtifact(error_msg)
                    
                    elif 'image/' in content_type:
                        # Successful image response
                        image_data = response.content
                        
                        # Validate image data
                        if not image_data or len(image_data) < 100:  # Minimum reasonable image size
                            error_msg = "Received empty or corrupted image data"
                            self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                            return ErrorArtifact(error_msg)
                        
                        # Save image using StaticFilesManager
                        file_extension = output_format.lower()
                        timestamp = int(time.time() * 1000)  # Add timestamp for uniqueness
                        filename = f"blender_capture_{camera_name}_{resolution_x}x{resolution_y}_{timestamp}.{file_extension}"
                        
                        try:
                            static_url = GriptapeNodes.StaticFilesManager().save_static_file(
                                image_data, filename
                            )
                        except Exception as save_error:
                            error_msg = f"Failed to save image: {str(save_error)}"
                            self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                            return ErrorArtifact(error_msg)
                        
                        # Create ImageUrlArtifact and set output
                        image_artifact = ImageUrlArtifact(static_url, name=f"blender_capture_{camera_name}_{timestamp}")
                        self.parameter_output_values["image_output"] = image_artifact
                        
                        # Update status with success info
                        actual_res_x = min(resolution_x, 1920)
                        actual_res_y = min(resolution_y, 1080)
                        self.parameter_output_values["status_output"] = f"Successfully captured {actual_res_x}x{actual_res_y} {output_format} image from camera '{camera_name}'"
                        
                        return image_artifact
                    
                    else:
                        error_msg = f"Unexpected response content type: {content_type}"
                        self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                        return ErrorArtifact(error_msg)
                
                elif response.status_code == 429:
                    error_msg = "Rate limited: Blender is processing too many requests. Try again in a moment."
                    self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                    return ErrorArtifact(error_msg)
                
                elif response.status_code == 404:
                    error_msg = f"Camera '{camera_name}' not found in Blender scene"
                    self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                    return ErrorArtifact(error_msg)
                
                else:
                    error_msg = f"Blender MCP server returned status {response.status_code}: {response.text[:200]}"
                    self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                    return ErrorArtifact(error_msg)

            except Exception as e:
                error_msg = f"Failed to capture frame: {str(e)}"
                logger.error(f"BlenderCameraCapture error: {error_msg}")
                self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                return ErrorArtifact(error_msg)

        yield capture_frame_async

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