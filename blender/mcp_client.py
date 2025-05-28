"""
MCP Client utilities for Blender integration
Provides shared MCP client functionality for Griptape nodes.
"""

import asyncio
import json
import logging
import subprocess
import sys
from typing import Any, Dict, Optional, List
from pathlib import Path

# MCP client imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

class BlenderMCPClient:
    """MCP Client for communicating with Blender MCP server"""
    
    def __init__(self, server_path: Optional[str] = None, blender_path: Optional[str] = None):
        self.server_path = server_path or self._find_server_path()
        self.blender_path = blender_path or self._find_blender_path()
        self.session: Optional[ClientSession] = None
        self._tools_cache: Optional[List[Dict]] = None
    
    def _find_server_path(self) -> str:
        """Find the Blender MCP server script"""
        # Look for server in same directory as this file
        current_dir = Path(__file__).parent
        server_path = current_dir / "blender_mcp_server.py"
        
        if server_path.exists():
            return str(server_path)
        
        raise FileNotFoundError("blender_mcp_server.py not found")
    
    def _find_blender_path(self) -> str:
        """Find Blender executable"""
        
        # Common Blender paths
        common_paths = [
            "/Applications/Blender.app/Contents/MacOS/Blender",  # macOS
            "/usr/bin/blender",  # Linux
            "C:\\Program Files\\Blender Foundation\\Blender\\blender.exe",  # Windows
        ]
        
        # Check if blender is in PATH
        try:
            result = subprocess.run(['which', 'blender'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        # Check common paths
        for path in common_paths:
            if Path(path).exists():
                return path
        
        # Default fallback
        return "blender"
    
    async def connect(self) -> bool:
        """Connect to the Blender MCP server"""
        if self.session is not None:
            return True
        
        try:
            # Command to run Blender with the MCP server script
            server_command = [
                self.blender_path,
                "--background",  # Run in background mode
                "--python", self.server_path
            ]
            
            logger.info(f"Starting Blender MCP server: {' '.join(server_command)}")
            
            # Create MCP client session
            server_params = StdioServerParameters(
                command=server_command[0],
                args=server_command[1:]
            )
            
            stdio_transport = stdio_client(server_params)
            stdio, write_stream, read_stream = await stdio_transport.__aenter__()
            
            self.session = ClientSession(read_stream, write_stream)
            
            # Initialize the session
            await self.session.initialize()
            
            logger.info("Connected to Blender MCP server")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Blender MCP server: {e}")
            self.session = None
            return False
    
    async def disconnect(self):
        """Disconnect from the MCP server"""
        if self.session:
            try:
                await self.session.close()
            except:
                pass
            finally:
                self.session = None
                self._tools_cache = None
    
    async def ensure_connected(self) -> bool:
        """Ensure we have a connection to the MCP server"""
        if self.session is None:
            return await self.connect()
        
        # Test connection with health check
        try:
            await self.health_check()
            return True
        except:
            # Connection lost, try to reconnect
            await self.disconnect()
            return await self.connect()
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server"""
        if not await self.ensure_connected():
            raise ConnectionError("Could not connect to Blender MCP server")
        
        if self._tools_cache is None:
            try:
                tools_result = await self.session.list_tools()
                self._tools_cache = [tool.model_dump() for tool in tools_result.tools]
            except Exception as e:
                logger.error(f"Failed to list tools: {e}")
                raise
        
        return self._tools_cache
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Call a tool on the MCP server"""
        if not await self.ensure_connected():
            raise ConnectionError("Could not connect to Blender MCP server")
        
        arguments = arguments or {}
        
        try:
            result = await self.session.call_tool(tool_name, arguments)
            
            # Extract result from MCP response
            if result.content and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    return json.loads(content.text)
                else:
                    logger.warning(f"Unexpected content type from tool {tool_name}")
                    return {"success": False, "error": "Unexpected response format"}
            else:
                logger.warning(f"Empty response from tool {tool_name}")
                return {"success": False, "error": "Empty response"}
                
        except Exception as e:
            logger.error(f"Tool call failed for {tool_name}: {e}")
            return {"success": False, "error": str(e)}
    
    async def render_camera(self, camera_name: str = "Camera", width: int = 1920, height: int = 1080, 
                          format_type: str = "PNG", quality: int = 90) -> Dict[str, Any]:
        """Render image from specified camera"""
        return await self.call_tool("render_camera", {
            "camera_name": camera_name,
            "width": width,
            "height": height,
            "format": format_type,
            "quality": quality
        })
    
    async def list_cameras(self) -> Dict[str, Any]:
        """List all cameras in the scene"""
        return await self.call_tool("list_cameras")
    
    async def get_scene_info(self) -> Dict[str, Any]:
        """Get scene information"""
        return await self.call_tool("get_scene_info")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check server health"""
        return await self.call_tool("health_check")

class BlenderMCPClientManager:
    """Singleton manager for Blender MCP client instances"""
    
    _instance: Optional[BlenderMCPClient] = None
    
    @classmethod
    def get_client(cls, server_path: Optional[str] = None, blender_path: Optional[str] = None) -> BlenderMCPClient:
        """Get or create the MCP client instance"""
        if cls._instance is None:
            cls._instance = BlenderMCPClient(server_path, blender_path)
        return cls._instance
    
    @classmethod
    async def cleanup(cls):
        """Clean up the client instance"""
        if cls._instance:
            await cls._instance.disconnect()
            cls._instance = None

# Convenience functions for use in Griptape nodes
async def render_camera_async(camera_name: str = "Camera", width: int = 1920, height: int = 1080,
                            format_type: str = "PNG", quality: int = 90) -> Dict[str, Any]:
    """Async function to render a camera - for use in node process methods"""
    client = BlenderMCPClientManager.get_client()
    return await client.render_camera(camera_name, width, height, format_type, quality)

async def list_cameras_async() -> Dict[str, Any]:
    """Async function to list cameras - for use in node process methods"""
    client = BlenderMCPClientManager.get_client()
    return await client.list_cameras()

async def get_scene_info_async() -> Dict[str, Any]:
    """Async function to get scene info - for use in node process methods"""
    client = BlenderMCPClientManager.get_client()
    return await client.get_scene_info()

def run_async_in_node(coro):
    """
    Helper to run async functions in synchronous node process methods.
    
    Usage in node process method:
        result = run_async_in_node(render_camera_async("Camera", 1920, 1080))
    """
    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, we need to use a different approach
            # This typically happens in Jupyter/async environments
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop, create new one
        return asyncio.run(coro) 