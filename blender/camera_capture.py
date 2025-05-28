import json
import base64
from typing import Optional, Any
from io import BytesIO
import time

from griptape.artifacts import ImageArtifact, ImageUrlArtifact, ErrorArtifact, TextArtifact
from griptape_nodes.traits.options import Options

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterGroup
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger, GriptapeNodes

# Import MCP client utilities
from .mcp_client import run_async_in_node, render_camera_async, list_cameras_async, get_scene_info_async


class BlenderCameraCapture(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "Blender"
        self.description = "Captures a single frame from a Blender camera via MCP server."
        self.metadata["author"] = "Griptape"
        self.metadata["dependencies"] = {"pip_dependencies": ["mcp", "nest-asyncio"]}

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
                traits={Options(choices=["PNG", "JPEG"])},
                ui_options={"display_name": "Format"}
            )
            Parameter(
                name="resolution_x",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=1920,
                tooltip="Output image width in pixels (64-4096).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"min": 64, "max": 4096, "display_name": "Width"}
            )
            Parameter(
                name="resolution_y",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=1080,
                tooltip="Output image height in pixels (64-4096).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"min": 64, "max": 4096, "display_name": "Height"}
            )
            Parameter(
                name="quality",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=90,
                tooltip="Image quality (1-100, applies to JPEG format only).",
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

    def _get_available_cameras(self) -> list[str]:
        """Fetch available cameras from the Blender MCP server."""
        try:
            result = run_async_in_node(list_cameras_async())
            if result.get("success") and result.get("cameras"):
                return [camera["name"] for camera in result["cameras"]]
            else:
                logger.warning(f"Could not fetch cameras: {result.get('error', 'Unknown error')}")
                return ["Camera"]
        except Exception as e:
            logger.warning(f"Could not fetch cameras from Blender MCP server: {e}")
            return ["Camera"]

    def _check_blender_connection(self) -> tuple[bool, str]:
        """Check if Blender MCP server is available."""
        try:
            result = run_async_in_node(get_scene_info_async())
            if result.get("success"):
                blender_info = result.get("blender", {})
                version = blender_info.get("version", "Unknown")
                return True, f"Connected to Blender {version}"
            else:
                return False, f"Blender MCP server error: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return False, f"Cannot connect to Blender MCP server: {str(e)}"

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

                # Call MCP server to render camera
                result = run_async_in_node(render_camera_async(
                    camera_name=camera_name,
                    width=resolution_x,
                    height=resolution_y,
                    format_type=output_format.upper(),
                    quality=quality
                ))

                if not result.get("success"):
                    error_msg = result.get("error", "Unknown error from Blender MCP server")
                    self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                    return ErrorArtifact(error_msg)

                # Get image data from result
                image_b64 = result.get("image")
                if not image_b64:
                    error_msg = "No image data received from Blender MCP server"
                    self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                    return ErrorArtifact(error_msg)

                # Decode base64 image data
                try:
                    image_data = base64.b64decode(image_b64)
                except Exception as decode_error:
                    error_msg = f"Failed to decode image data: {str(decode_error)}"
                    self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                    return ErrorArtifact(error_msg)

                # Validate image data
                if not image_data or len(image_data) < 100:
                    error_msg = "Received empty or corrupted image data"
                    self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                    return ErrorArtifact(error_msg)

                # Save image using StaticFilesManager
                file_extension = output_format.lower()
                timestamp = int(time.time() * 1000)
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
                render_time = result.get("render_time", 0)
                engine = result.get("engine", "Unknown")
                actual_width = result.get("width", resolution_x)
                actual_height = result.get("height", resolution_y)
                
                status_msg = f"Successfully captured {actual_width}x{actual_height} {output_format} image from camera '{camera_name}'\n"
                status_msg += f"Render time: {render_time:.2f}s, Engine: {engine}"
                self.parameter_output_values["status_output"] = status_msg

                return image_artifact

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