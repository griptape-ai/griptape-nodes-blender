#!/usr/bin/env python3
"""
Blender MCP Server for Griptape Nodes
Provides MCP protocol interface to Blender rendering capabilities.
"""

import asyncio
import base64
import json
import logging
import os
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

# MCP imports
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("blender_mcp_server")

class BlenderMCPServer:
    """MCP Server for Blender integration"""
    
    def __init__(self):
        self.server = Server("blender-mcp-server")
        self.bpy = None
        self.blender_available = False
        self.render_count = 0
        
        # Register MCP handlers
        self._register_handlers()
        
    def _register_handlers(self):
        """Register MCP tool handlers"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """List available tools"""
            return [
                types.Tool(
                    name="render_camera",
                    description="Render image from specified Blender camera",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "camera_name": {
                                "type": "string",
                                "description": "Name of the camera to render from",
                                "default": "Camera"
                            },
                            "width": {
                                "type": "integer", 
                                "description": "Image width in pixels",
                                "default": 1920,
                                "minimum": 64,
                                "maximum": 4096
                            },
                            "height": {
                                "type": "integer",
                                "description": "Image height in pixels", 
                                "default": 1080,
                                "minimum": 64,
                                "maximum": 4096
                            },
                            "format": {
                                "type": "string",
                                "description": "Output image format",
                                "enum": ["PNG", "JPEG"],
                                "default": "PNG"
                            },
                            "quality": {
                                "type": "integer",
                                "description": "JPEG quality (1-100, ignored for PNG)",
                                "default": 90,
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="list_cameras",
                    description="List all cameras in the current Blender scene",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="get_scene_info",
                    description="Get information about the current Blender scene",
                    inputSchema={
                        "type": "object", 
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="health_check",
                    description="Check if Blender is available and responding",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            """Handle tool calls"""
            
            if not await self._ensure_blender():
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "success": False,
                        "error": "Blender not available"
                    })
                )]
            
            try:
                if name == "render_camera":
                    result = await self._render_camera(arguments)
                elif name == "list_cameras":
                    result = await self._list_cameras()
                elif name == "get_scene_info":
                    result = await self._get_scene_info()
                elif name == "health_check":
                    result = await self._health_check()
                else:
                    result = {
                        "success": False,
                        "error": f"Unknown tool: {name}"
                    }
                
                return [types.TextContent(
                    type="text",
                    text=json.dumps(result)
                )]
                
            except Exception as e:
                logger.error(f"Error in tool {name}: {e}")
                return [types.TextContent(
                    type="text", 
                    text=json.dumps({
                        "success": False,
                        "error": str(e)
                    })
                )]
    
    async def _ensure_blender(self) -> bool:
        """Ensure Blender is available and bpy is imported"""
        if self.blender_available:
            return True
            
        try:
            # Try to import bpy
            if self.bpy is None:
                import bpy
                self.bpy = bpy
                logger.info(f"Connected to Blender {bpy.app.version_string}")
            
            # Test basic functionality
            _ = self.bpy.context.scene
            self.blender_available = True
            return True
            
        except ImportError:
            logger.error("bpy module not available - Blender not running in Python environment")
            self.blender_available = False
            return False
        except Exception as e:
            logger.error(f"Error connecting to Blender: {e}")
            self.blender_available = False
            return False
    
    async def _render_camera(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Render image from specified camera"""
        
        camera_name = args.get("camera_name", "Camera")
        width = args.get("width", 1920)
        height = args.get("height", 1080)
        format_type = args.get("format", "PNG").upper()
        quality = args.get("quality", 90)
        
        # Cap resolution for stability
        width = max(64, min(width, 4096))
        height = max(64, min(height, 4096))
        
        self.render_count += 1
        logger.info(f"Render #{self.render_count}: {camera_name} at {width}x{height} {format_type}")
        
        try:
            scene = self.bpy.context.scene
            
            # Validate camera exists
            if camera_name not in self.bpy.data.objects:
                return {
                    "success": False,
                    "error": f"Camera '{camera_name}' not found"
                }
            
            camera_obj = self.bpy.data.objects[camera_name]
            if camera_obj.type != 'CAMERA':
                return {
                    "success": False,
                    "error": f"Object '{camera_name}' is not a camera"
                }
            
            # Store original settings
            original_camera = scene.camera
            original_width = scene.render.resolution_x
            original_height = scene.render.resolution_y
            original_format = scene.render.image_settings.file_format
            original_quality = scene.render.image_settings.quality
            original_engine = scene.render.engine
            
            try:
                # Apply render settings
                scene.camera = camera_obj
                scene.render.resolution_x = width
                scene.render.resolution_y = height
                scene.render.resolution_percentage = 100
                
                # Handle engine-specific optimizations
                await self._optimize_render_engine(scene)
                
                # Set image format
                if format_type == "JPEG":
                    scene.render.image_settings.file_format = 'JPEG'
                    scene.render.image_settings.quality = quality
                    scene.render.image_settings.color_mode = 'RGB'
                else:  # PNG
                    scene.render.image_settings.file_format = 'PNG'
                    scene.render.image_settings.color_mode = 'RGBA'
                
                # Update scene
                self.bpy.context.view_layer.update()
                
                # Perform render
                start_time = time.time()
                
                # Clear existing render result
                if 'Render Result' in self.bpy.data.images:
                    self.bpy.data.images.remove(self.bpy.data.images['Render Result'])
                
                # Render
                self.bpy.ops.render.render(write_still=False)
                
                render_time = time.time() - start_time
                
                # Get render result
                if 'Render Result' not in self.bpy.data.images:
                    return {
                        "success": False,
                        "error": "No render result generated"
                    }
                
                render_result = self.bpy.data.images['Render Result']
                
                # Validate pixel data
                if not render_result.pixels or len(render_result.pixels) == 0:
                    return {
                        "success": False,
                        "error": "Render produced empty pixel data"
                    }
                
                # Convert to base64
                image_data = await self._pixels_to_base64(render_result, width, height, format_type)
                
                return {
                    "success": True,
                    "image": image_data,
                    "width": width,
                    "height": height,
                    "format": format_type,
                    "camera": camera_name,
                    "render_time": render_time,
                    "engine": scene.render.engine,
                    "render_count": self.render_count
                }
                
            finally:
                # Restore original settings
                scene.camera = original_camera
                scene.render.resolution_x = original_width
                scene.render.resolution_y = original_height
                scene.render.image_settings.file_format = original_format
                scene.render.image_settings.quality = original_quality
                scene.render.engine = original_engine
                
                # Cleanup
                await self._cleanup_render()
                
        except Exception as e:
            logger.error(f"Render error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _optimize_render_engine(self, scene):
        """Optimize render engine for headless operation"""
        
        engine = scene.render.engine
        
        if engine == 'BLENDER_EEVEE_NEXT':
            logger.warning("Eevee Next detected - switching to Cycles CPU for stability")
            scene.render.engine = 'CYCLES'
            scene.cycles.device = 'CPU'
            scene.cycles.samples = 32
            
        elif engine == 'CYCLES':
            # Force CPU rendering for stability
            scene.cycles.device = 'CPU'
            scene.cycles.samples = min(scene.cycles.samples, 64)
            
        elif engine in ['EEVEE', 'BLENDER_EEVEE']:
            # Optimize Eevee settings
            if hasattr(scene.eevee, 'taa_render_samples'):
                scene.eevee.taa_render_samples = min(scene.eevee.taa_render_samples, 16)
            if hasattr(scene.eevee, 'use_motion_blur'):
                scene.eevee.use_motion_blur = False
        
        # Disable persistent data for memory management
        scene.render.use_persistent_data = False
    
    async def _pixels_to_base64(self, image, width: int, height: int, format_type: str) -> str:
        """Convert Blender image pixels to base64"""
        
        pixels = list(image.pixels)
        pixel_count = len(pixels)
        expected_pixels = width * height * 4  # RGBA
        
        if pixel_count != expected_pixels:
            logger.warning(f"Pixel count mismatch: got {pixel_count}, expected {expected_pixels}")
        
        # Convert float pixels to bytes
        byte_pixels = []
        for i in range(0, len(pixels), 4):
            if i + 3 < len(pixels):
                r = int(max(0, min(1, pixels[i])) * 255)
                g = int(max(0, min(1, pixels[i+1])) * 255) 
                b = int(max(0, min(1, pixels[i+2])) * 255)
                a = int(max(0, min(1, pixels[i+3])) * 255)
                
                if format_type == "JPEG":
                    # RGB only for JPEG
                    byte_pixels.extend([r, g, b])
                else:
                    # RGBA for PNG
                    byte_pixels.extend([r, g, b, a])
        
        if not byte_pixels:
            raise RuntimeError("Failed to convert pixel data")
        
        image_bytes = bytes(byte_pixels)
        return base64.b64encode(image_bytes).decode('utf-8')
    
    async def _cleanup_render(self):
        """Clean up after render"""
        try:
            # Remove render result
            if 'Render Result' in self.bpy.data.images:
                self.bpy.data.images.remove(self.bpy.data.images['Render Result'])
            
            # Periodic deep cleanup
            if self.render_count % 5 == 0:
                logger.info("Performing periodic cleanup")
                self.bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
                
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
    
    async def _list_cameras(self) -> Dict[str, Any]:
        """List all cameras in the scene"""
        try:
            cameras = []
            for obj in self.bpy.context.scene.objects:
                if obj.type == 'CAMERA':
                    cameras.append({
                        "name": obj.name,
                        "location": list(obj.location),
                        "rotation": list(obj.rotation_euler),
                        "active": obj == self.bpy.context.scene.camera
                    })
            
            return {
                "success": True,
                "cameras": cameras,
                "count": len(cameras)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _get_scene_info(self) -> Dict[str, Any]:
        """Get scene information"""
        try:
            scene = self.bpy.context.scene
            
            return {
                "success": True,
                "scene": {
                    "name": scene.name,
                    "frame_current": scene.frame_current,
                    "frame_start": scene.frame_start,
                    "frame_end": scene.frame_end,
                    "render_engine": scene.render.engine,
                    "resolution": [scene.render.resolution_x, scene.render.resolution_y],
                    "active_camera": scene.camera.name if scene.camera else None
                },
                "blender": {
                    "version": self.bpy.app.version_string,
                    "version_tuple": list(self.bpy.app.version)
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _health_check(self) -> Dict[str, Any]:
        """Health check"""
        try:
            # Test basic Blender functionality
            scene_name = self.bpy.context.scene.name
            
            return {
                "success": True,
                "status": "healthy",
                "blender_version": self.bpy.app.version_string,
                "scene": scene_name,
                "render_count": self.render_count
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

async def main():
    """Run the MCP server"""
    
    # Check if running in Blender environment
    try:
        import bpy
        logger.info(f"Running in Blender {bpy.app.version_string}")
    except ImportError:
        logger.error("Not running in Blender Python environment")
        logger.error("Please run this script from within Blender or with Blender's Python")
        sys.exit(1)
    
    # Create and run server
    server_instance = BlenderMCPServer()
    
    # Run the MCP server
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="blender-mcp-server",
                server_version="1.0.0",
                capabilities=server_instance.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main()) 