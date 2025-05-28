import json
import requests
from typing import Optional, Any, List, Dict

from griptape.artifacts import TextArtifact, ErrorArtifact, ListArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterGroup
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger


class BlenderCameraList(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "Blender"
        self.description = "Lists all available cameras in the current Blender scene."
        self.metadata["author"] = "Griptape"
        self.metadata["dependencies"] = {"pip_dependencies": ["requests"]}

        # Control Parameters
        self.add_parameter(
            Parameter(
                name="refresh_trigger",
                input_types=["bool", "str"],
                output_type="bool",
                type="bool",
                default_value=True,
                tooltip="Trigger to refresh the camera list from Blender.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Refresh Cameras"}
            )
        )

        # Output Parameters
        self.add_parameter(
            Parameter(
                name="cameras_output",
                output_type="ListArtifact",
                type="ListArtifact",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="List of camera information including names, positions, and rotations.",
                ui_options={"pulse_on_run": True}
            )
        )
        self.add_parameter(
            Parameter(
                name="camera_names",
                output_type="list[str]",
                type="list[str]",
                default_value=[],
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Simple list of camera names for easy connection to other nodes."
            )
        )
        self.add_parameter(
            Parameter(
                name="camera_count",
                output_type="int",
                type="int",
                default_value=0,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Total number of cameras found in the scene."
            )
        )
        self.add_parameter(
            Parameter(
                name="status_output",
                output_type="str",
                type="str",
                default_value="",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Status message from the camera discovery operation.",
                ui_options={"multiline": True}
            )
        )

    def _get_mcp_server_url(self) -> str:
        """Get the MCP server URL from configuration."""
        host = self.get_config_value("Blender", "BLENDER_MCP_HOST") or "localhost"
        port = self.get_config_value("Blender", "BLENDER_MCP_PORT") or "8080"
        return f"http://{host}:{port}"

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

    def _fetch_cameras(self) -> tuple[List[Dict], str]:
        """Fetch camera information from Blender MCP server."""
        try:
            url = f"{self._get_mcp_server_url()}/api/cameras"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                cameras = data.get("cameras", [])
                
                if cameras:
                    status = f"Successfully found {len(cameras)} camera(s) in the scene"
                    return cameras, status
                else:
                    status = "No cameras found in the current Blender scene"
                    return [], status
            else:
                error_msg = f"Blender MCP server returned status {response.status_code}: {response.text}"
                return [], error_msg

        except Exception as e:
            error_msg = f"Failed to fetch cameras: {str(e)}"
            return [], error_msg

    def _format_camera_info(self, cameras: List[Dict]) -> List[Dict]:
        """Format camera information for better readability."""
        formatted_cameras = []
        
        for camera in cameras:
            formatted_camera = {
                "name": camera.get("name", "Unknown"),
                "location": {
                    "x": round(camera.get("location", [0, 0, 0])[0], 3),
                    "y": round(camera.get("location", [0, 0, 0])[1], 3),
                    "z": round(camera.get("location", [0, 0, 0])[2], 3)
                },
                "rotation": {
                    "x": round(camera.get("rotation", [0, 0, 0])[0], 3),
                    "y": round(camera.get("rotation", [0, 0, 0])[1], 3),
                    "z": round(camera.get("rotation", [0, 0, 0])[2], 3)
                }
            }
            formatted_cameras.append(formatted_camera)
        
        return formatted_cameras

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that Blender MCP server is available before running."""
        is_connected, message = self._check_blender_connection()
        if not is_connected:
            return [ConnectionError(message)]
        return None

    def process(self):
        """Fetch and list all cameras from the Blender scene."""
        def fetch_cameras_async():
            try:
                # Check if we should refresh (always true for this node)
                refresh_trigger = self.get_parameter_value("refresh_trigger")
                
                if not refresh_trigger:
                    status = "Camera refresh not triggered"
                    self.parameter_output_values["status_output"] = status
                    return ListArtifact([])

                # Update status
                self.parameter_output_values["status_output"] = "Fetching cameras from Blender..."

                # Fetch cameras from Blender
                cameras, status_msg = self._fetch_cameras()

                if cameras:
                    # Format camera information
                    formatted_cameras = self._format_camera_info(cameras)
                    
                    # Extract just the names for easy use
                    camera_names = [camera["name"] for camera in formatted_cameras]
                    
                    # Update outputs
                    self.parameter_output_values["camera_names"] = camera_names
                    self.parameter_output_values["camera_count"] = len(formatted_cameras)
                    self.parameter_output_values["status_output"] = status_msg
                    
                    # Create detailed camera list artifact
                    return ListArtifact(formatted_cameras, name="blender_cameras")
                
                else:
                    # No cameras found or error occurred
                    self.parameter_output_values["camera_names"] = []
                    self.parameter_output_values["camera_count"] = 0
                    self.parameter_output_values["status_output"] = status_msg
                    
                    if "error" in status_msg.lower() or "failed" in status_msg.lower():
                        return ErrorArtifact(status_msg)
                    else:
                        # No cameras but no error
                        return ListArtifact([])

            except Exception as e:
                error_msg = f"Failed to list cameras: {str(e)}"
                logger.error(f"BlenderCameraList error: {error_msg}")
                self.parameter_output_values["status_output"] = f"Error: {error_msg}"
                self.parameter_output_values["camera_names"] = []
                self.parameter_output_values["camera_count"] = 0
                return ErrorArtifact(error_msg)

        yield fetch_cameras_async 