"""
Simple Socket Client for Blender Communication
==============================================

Connects to the Blender socket server to send commands.
Much simpler than MCP stdio - no async context issues.
"""

import socket
import json
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BlenderSocketClient:
    """Client for communicating with Blender socket server"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, timeout: int = 60):
        self.host = host
        self.port = port
        self.timeout = timeout
    
    def _send_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a command to Blender and return the response with improved error handling"""
        request = {
            "command": command,
            "params": params or {}
        }
        
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Create socket connection with shorter timeout for connection
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(10)  # 10 second connection timeout
                    
                    try:
                        sock.connect((self.host, self.port))
                    except (socket.timeout, ConnectionRefusedError, OSError) as e:
                        if attempt == max_retries - 1:
                            return {
                                "success": False, 
                                "error": f"Cannot connect to Blender server at {self.host}:{self.port}. Make sure Blender socket server is running. Error: {str(e)}"
                            }
                        print(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        continue
                    
                    # Set longer timeout for command execution
                    sock.settimeout(self.timeout)
                    
                    # Send request
                    request_json = json.dumps(request)
                    try:
                        sock.sendall(request_json.encode('utf-8'))
                    except (socket.timeout, BrokenPipeError, ConnectionResetError) as e:
                        return {"success": False, "error": f"Failed to send command: {str(e)}"}
                    
                    # Receive response with chunked reading for large responses
                    try:
                        response_chunks = []
                        while True:
                            chunk = sock.recv(8192)
                            if not chunk:
                                break
                            response_chunks.append(chunk)
                        
                        if not response_chunks:
                            return {"success": False, "error": "Empty response from server"}
                            
                        response_data = b''.join(response_chunks).decode('utf-8')
                        
                    except socket.timeout:
                        return {"success": False, "error": f"Command timed out after {self.timeout} seconds"}
                    except (ConnectionResetError, BrokenPipeError) as e:
                        return {"success": False, "error": f"Connection lost during command execution: {str(e)}"}
                    
                    # Parse JSON response
                    try:
                        if not response_data.strip():
                            return {"success": False, "error": "Empty response from Blender server"}
                        
                        response = json.loads(response_data)
                        return response
                        
                    except json.JSONDecodeError as e:
                        return {
                            "success": False, 
                            "error": f"Invalid JSON response from server. Raw response: {response_data[:100]}..."
                        }
                        
            except Exception as e:
                if attempt == max_retries - 1:
                    return {"success": False, "error": f"Unexpected error: {str(e)}"}
                print(f"Attempt {attempt + 1} failed with error: {str(e)}, retrying...")
                time.sleep(retry_delay)
        
        return {"success": False, "error": "All connection attempts failed"}
    
    def health_check(self) -> Dict[str, Any]:
        """Check if Blender server is responsive"""
        return self._send_command("health_check")
    
    def get_scene_info(self) -> Dict[str, Any]:
        """Get current scene information"""
        return self._send_command("get_scene_info")
    
    def list_cameras(self) -> Dict[str, Any]:
        """List all cameras in the scene"""
        return self._send_command("list_cameras")
    
    def render_camera(self, camera_name: str = "Camera", width: int = 1920, height: int = 1080, 
                     format_type: str = "PNG", quality: int = 90) -> Dict[str, Any]:
        """Render from specified camera using simple code execution (reference project pattern)"""
        
        # Much simpler approach based on reference project
        render_code = f"""
import bpy
import os
import base64

print(f"DEBUG: Looking for camera named: '{camera_name}'")

# Find camera
camera = bpy.data.objects.get("{camera_name}")
if not camera or camera.type != 'CAMERA':
    print(f"DEBUG: Camera '{camera_name}' not found")
    print(f"DEBUG: Available cameras: {{[obj.name for obj in bpy.data.objects if obj.type == 'CAMERA']}}")
    result = {{"success": False, "error": f"Camera '{camera_name}' not found"}}
else:
    print(f"DEBUG: Found camera '{camera_name}', setting as active")
    # Set camera and basic settings
    scene = bpy.context.scene
    old_camera = scene.camera.name if scene.camera else "None"
    scene.camera = camera
    print(f"DEBUG: Changed active camera from '{{old_camera}}' to '{{camera.name}}'")
    
    scene.render.resolution_x = {width}
    scene.render.resolution_y = {height}
    
    # Use simplest possible settings
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.image_settings.file_format = 'PNG'
    
    # Render to file
    temp_file = "/tmp/blender_render.png"
    scene.render.filepath = temp_file
    print(f"DEBUG: Starting render with camera '{{scene.camera.name}}'")
    bpy.ops.render.render(write_still=True)
    print(f"DEBUG: Render completed")
    
    # Read and encode
    if os.path.exists(temp_file):
        with open(temp_file, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        os.remove(temp_file)
        result = {{"success": True, "image": image_data, "camera_used": camera.name}}
    else:
        result = {{"success": False, "error": "Render failed"}}
"""
        
        return self._send_command("execute_code", {"code": render_code})
    
    def execute_code(self, code: str) -> Dict[str, Any]:
        """Execute arbitrary Python code in Blender"""
        return self._send_command("execute_code", {"code": code})


class BlenderSocketClientManager:
    """Singleton manager for Blender socket client"""
    
    _instance: Optional[BlenderSocketClient] = None
    
    @classmethod
    def get_client(cls, host: str = "localhost", port: int = 8765) -> BlenderSocketClient:
        """Get or create the socket client instance"""
        if cls._instance is None:
            cls._instance = BlenderSocketClient(host, port)
        return cls._instance
    
    @classmethod
    def reset_client(cls):
        """Reset the client instance (useful for changing connection settings)"""
        cls._instance = None


# Convenience functions for easier integration
def health_check() -> Dict[str, Any]:
    """Quick health check function"""
    client = BlenderSocketClient()
    return client.health_check()


def get_scene_info() -> Dict[str, Any]:
    """Quick scene info function"""
    client = BlenderSocketClient()
    return client.get_scene_info()


def list_cameras() -> Dict[str, Any]:
    """Quick camera list function"""
    client = BlenderSocketClient()
    return client.list_cameras()


def render_camera(camera_name: str = "Camera", width: int = 1920, height: int = 1080, 
                 format_type: str = "PNG", quality: int = 90) -> Dict[str, Any]:
    """Quick render function"""
    client = BlenderSocketClient(timeout=120)  # Longer timeout for rendering
    return client.render_camera(camera_name, width, height, format_type, quality) 