# Griptape Nodes: Blender Library

Real-time camera capture and scene interaction nodes for Blender via HTTP server.

## Overview

This library provides Griptape Nodes for capturing images from Blender cameras in real-time. It communicates with Blender through a lightweight HTTP server that exposes Blender's camera system.

## Features

- **Real-time camera capture** from any Blender camera
- **Multiple output formats** (PNG, JPEG, EXR, TIFF)
- **Configurable resolution** and quality settings
- **Automatic camera detection** from active Blender scenes
- **Graceful error handling** when Blender is not available
- **Live camera streaming** for continuous capture

## Installation

1. Clone this repository into your Griptape Nodes workspace:
   ```bash
   cd $(gtn config | grep workspace_directory | cut -d'"' -f4)
   git clone <repository-url> griptape-nodes-blender
   ```

2. Install dependencies:
   ```bash
   cd griptape-nodes-blender
   uv sync
   ```

## Setup

### 1. Blender HTTP Server

You need to run a simple HTTP server inside Blender to expose the camera API. 

**Option A: Blender Add-on (Recommended)**
1. Install the Blender add-on (coming soon)
2. Enable it in Blender preferences
3. The server starts automatically when Blender opens

**Option B: Manual Script**
1. In Blender, go to Scripting workspace
2. Create a new text file and paste this script:

```python
import bpy
import json
import time
import threading
import gc
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

class BlenderCameraHandler(BaseHTTPRequestHandler):
    # Class-level rate limiting with very conservative intervals
    last_render_time = 0
    min_render_interval = 1.0  # Increased to 1 second between renders
    render_count = 0
    max_renders_before_cleanup = 5  # Force cleanup every 5 renders
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        params = parse_qs(parsed_path.query)
        
        try:
            if path == '/api/status':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    "status": "ok",
                    "blender_version": bpy.app.version_string,
                    "scene": bpy.context.scene.name,
                    "render_count": BlenderCameraHandler.render_count,
                    "render_engine": bpy.context.scene.render.engine
                }
                self.wfile.write(json.dumps(response).encode())
                
            elif path == '/api/cameras':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                cameras = []
                for obj in bpy.context.scene.objects:
                    if obj.type == 'CAMERA':
                        cameras.append({
                            "name": obj.name,
                            "location": list(obj.location),
                            "rotation": list(obj.rotation_euler)
                        })
                response = {"cameras": cameras}
                self.wfile.write(json.dumps(response).encode())
                
            elif path.startswith('/api/camera/') and path.endswith('/render'):
                # Ultra-conservative rate limiting
                current_time = time.time()
                if current_time - BlenderCameraHandler.last_render_time < BlenderCameraHandler.min_render_interval:
                    self.send_error(429, "Rate limited: Too many render requests")
                    return
                BlenderCameraHandler.last_render_time = current_time
                BlenderCameraHandler.render_count += 1
                
                camera_name = path.split('/')[3]
                
                # Find camera
                camera_obj = bpy.context.scene.objects.get(camera_name)
                if not camera_obj or camera_obj.type != 'CAMERA':
                    self.send_error(404, f"Camera '{camera_name}' not found")
                    return
                
                # Get parameters with very conservative defaults
                width = min(int(params.get('width', [640])[0]), 1280)  # Further reduced max
                height = min(int(params.get('height', [480])[0]), 720)  # Further reduced max
                format_type = params.get('format', ['jpeg'])[0].lower()
                quality = max(10, min(int(params.get('quality', [50])[0]), 100))
                
                # Force periodic cleanup
                if BlenderCameraHandler.render_count % BlenderCameraHandler.max_renders_before_cleanup == 0:
                    print(f"Performing periodic cleanup after {BlenderCameraHandler.render_count} renders")
                    self._force_cleanup()
                
                # Set render settings with ultra-conservative approach
                scene = bpy.context.scene
                original_camera = scene.camera
                original_res_x = scene.render.resolution_x
                original_res_y = scene.render.resolution_y
                original_format = scene.render.image_settings.file_format
                original_quality = scene.render.image_settings.quality
                original_percentage = scene.render.resolution_percentage
                original_engine = scene.render.engine
                original_device = None
                
                # Store original Cycles device if using Cycles
                if hasattr(scene.cycles, 'device'):
                    original_device = scene.cycles.device
                
                try:
                    # Ultra-aggressive cleanup before render
                    self._pre_render_cleanup()
                    
                    # Force CPU rendering for maximum stability
                    if scene.render.engine == 'CYCLES':
                        scene.cycles.device = 'CPU'
                        print("Forced CPU rendering for stability")
                    elif scene.render.engine not in ['WORKBENCH', 'EEVEE']:
                        # Switch to Workbench for fastest, most stable rendering
                        scene.render.engine = 'WORKBENCH'
                        print("Switched to Workbench engine for stability")
                    
                    # Set camera and render settings
                    scene.camera = camera_obj
                    scene.render.resolution_x = width
                    scene.render.resolution_y = height
                    scene.render.resolution_percentage = 100
                    
                    # Ultra-conservative image settings
                    if format_type == 'png':
                        scene.render.image_settings.file_format = 'PNG'
                        scene.render.image_settings.compression = 15  # Minimal compression
                        scene.render.image_settings.color_mode = 'RGB'
                    else:  # Default to JPEG for everything else
                        scene.render.image_settings.file_format = 'JPEG'
                        scene.render.image_settings.quality = quality
                        scene.render.image_settings.color_mode = 'RGB'
                    
                    # Disable all non-essential render features
                    scene.render.use_persistent_data = False
                    scene.render.use_motion_blur = False
                    
                    # Additional Eevee optimizations if using Eevee
                    if scene.render.engine == 'EEVEE':
                        scene.eevee.taa_render_samples = 8  # Minimal samples
                        scene.eevee.use_motion_blur = False
                        scene.eevee.use_bloom = False
                        scene.eevee.use_ssr = False  # Disable screen space reflections
                        scene.eevee.use_volumetric_lights = False
                    
                    # Force complete scene update with multiple passes
                    for _ in range(3):  # Multiple update passes for stability
                        bpy.context.view_layer.update()
                        time.sleep(0.05)
                    
                    scene.frame_set(scene.frame_current)
                    bpy.context.evaluated_depsgraph_get().update()
                    
                    # Longer stabilization delay
                    time.sleep(0.3)
                    
                    print(f"Starting render {BlenderCameraHandler.render_count}: {width}x{height} {format_type}")
                    
                    # Render with maximum error protection
                    try:
                        bpy.ops.render.render(write_still=False)
                    except Exception as render_error:
                        print(f"Render operation failed: {render_error}")
                        self.send_error(500, f"Render failed: {str(render_error)}")
                        return
                    
                    # Get and validate image data
                    image = bpy.data.images.get('Render Result')
                    if not image or not hasattr(image, 'pixels') or len(image.pixels) == 0:
                        self.send_error(500, "Render failed - no result image or empty pixels")
                        return
                    
                    # Save with enhanced error handling and unique naming
                    temp_dir = "/tmp"
                    if not os.path.exists(temp_dir):
                        temp_dir = bpy.app.tempdir
                    
                    timestamp = int(time.time() * 1000)
                    thread_id = threading.current_thread().ident
                    temp_path = os.path.join(temp_dir, f"blender_render_{thread_id}_{timestamp}.{format_type}")
                    
                    try:
                        image.save_render(temp_path)
                        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                            raise Exception("Saved file is empty or doesn't exist")
                    except Exception as save_error:
                        print(f"Failed to save render: {save_error}")
                        self.send_error(500, f"Failed to save render: {str(save_error)}")
                        return
                    
                    # Read and validate file
                    try:
                        with open(temp_path, 'rb') as f:
                            image_data = f.read()
                        
                        if not image_data or len(image_data) < 100:
                            raise Exception("Image data is empty or too small")
                            
                    except Exception as read_error:
                        print(f"Failed to read rendered image: {read_error}")
                        self.send_error(500, f"Failed to read rendered image: {str(read_error)}")
                        return
                    finally:
                        # Always clean up temp file
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception as cleanup_error:
                            print(f"Warning: Failed to clean up temp file: {cleanup_error}")
                    
                    # Send successful response
                    self.send_response(200)
                    self.send_header('Content-type', f'image/{format_type}')
                    self.send_header('Content-length', str(len(image_data)))
                    self.end_headers()
                    self.wfile.write(image_data)
                    
                    print(f"Render {BlenderCameraHandler.render_count} completed successfully")
                    
                finally:
                    # Ultra-comprehensive cleanup
                    try:
                        # Restore all original settings
                        scene.camera = original_camera
                        scene.render.resolution_x = original_res_x
                        scene.render.resolution_y = original_res_y
                        scene.render.resolution_percentage = original_percentage
                        scene.render.image_settings.file_format = original_format
                        scene.render.image_settings.quality = original_quality
                        scene.render.engine = original_engine
                        
                        if original_device and hasattr(scene.cycles, 'device'):
                            scene.cycles.device = original_device
                        
                        # Post-render cleanup
                        self._post_render_cleanup()
                        
                    except Exception as cleanup_error:
                        print(f"Warning: Settings restoration failed: {cleanup_error}")
                
            else:
                self.send_error(404, "Endpoint not found")
                
        except Exception as e:
            print(f"Blender server error: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))
    
    def _pre_render_cleanup(self):
        """Aggressive cleanup before rendering."""
        try:
            # Clear all render results
            for img_name in ['Render Result', 'Viewer Node']:
                if img_name in bpy.data.images:
                    bpy.data.images.remove(bpy.data.images[img_name])
            
            # Clear orphaned data
            bpy.data.orphans_purge()
            
            # Force garbage collection
            gc.collect()
            
        except Exception as e:
            print(f"Pre-render cleanup warning: {e}")
    
    def _post_render_cleanup(self):
        """Cleanup after rendering."""
        try:
            # Clear render result
            if 'Render Result' in bpy.data.images:
                bpy.data.images.remove(bpy.data.images['Render Result'])
            
            # Force scene update
            bpy.context.view_layer.update()
            
            # Enhanced garbage collection
            gc.collect()
            
            # GPU memory cleanup if available
            try:
                import bgl
                bgl.glFinish()
            except:
                pass
            
            # Additional delay for GPU recovery
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Post-render cleanup warning: {e}")
    
    def _force_cleanup(self):
        """Periodic forced cleanup."""
        try:
            print("Performing forced cleanup...")
            
            # Clear all images except essential ones
            essential_images = {'Render Result', 'Viewer Node'}
            for img in list(bpy.data.images):
                if img.name not in essential_images and img.users == 0:
                    bpy.data.images.remove(img)
            
            # Purge orphaned data
            bpy.data.orphans_purge()
            
            # Force multiple garbage collection passes
            for _ in range(3):
                gc.collect()
                time.sleep(0.05)
            
            print("Forced cleanup completed")
            
        except Exception as e:
            print(f"Forced cleanup warning: {e}")

def start_server():
    server = HTTPServer(('localhost', 8080), BlenderCameraHandler)
    print("Blender Camera Server started on http://localhost:8080")
    print("ULTRA-STABLE MODE:")
    print("- CPU rendering enforced for Cycles")
    print("- 1 second minimum between renders")
    print("- Aggressive memory cleanup")
    print("- Periodic forced cleanup every 5 renders")
    server.serve_forever()

# Start server in background thread
server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()
```

3. Run the script (this starts the HTTP server)
4. Keep Blender open while using the nodes

### 2. Configuration

The nodes will automatically connect to `localhost:8080`. To change this:

1. Set environment variables:
   ```bash
   export BLENDER_MCP_HOST=localhost
   export BLENDER_MCP_PORT=8080
   ```

2. Or configure in Griptape Nodes settings under "Blender" category.

## Available Nodes

### Blender Camera Capture
Captures a single frame from a specified Blender camera.

**Inputs:**
- `camera_name` - Name of the camera in Blender scene
- `output_format` - Image format (PNG, JPEG, EXR, TIFF)
- `resolution_x/y` - Output resolution in pixels
- `quality` - JPEG quality (1-100)

**Outputs:**
- `image_output` - Captured image as ImageUrlArtifact
- `status_output` - Status message from capture operation

### Blender Camera Stream
Provides real-time streaming from a Blender camera.

**Inputs:**
- `camera_name` - Name of the camera to stream from
- `frame_rate` - Capture rate in FPS (1-30)
- `output_format` - Image format for frames
- `resolution_x/y` - Stream resolution

**Outputs:**
- `frame_output` - Latest captured frame
- `frame_count` - Number of frames captured
- `status_output` - Stream status

### Blender Camera List
Lists all available cameras in the current Blender scene.

**Outputs:**
- `cameras_output` - List of camera names and properties
- `camera_count` - Total number of cameras

## Usage Examples

### Basic Camera Capture
1. Add "Blender Camera Capture" node
2. Set camera name (or leave as "Camera" for default)
3. Configure output format and resolution
4. Connect to image processing nodes
5. Run workflow

### Real-time Streaming
1. Add "Blender Camera Stream" node
2. Set frame rate (e.g., 10 FPS)
3. Connect to real-time processing pipeline
4. Stream will continue until workflow stops

### Multi-Camera Setup
1. Use "Blender Camera List" to discover cameras
2. Connect multiple "Camera Capture" nodes
3. Process different camera angles simultaneously

## Troubleshooting

### Blender Crashes on Second Camera Capture (After Moving Camera)

**This is a common issue when running camera capture multiple times after changing camera positions.**

**Root Causes:**
- GPU memory accumulation between renders
- Scene state not properly invalidated after camera movement
- Insufficient delays between render operations
- Render context conflicts

**Solutions:**

**1. Use the Updated MCP Server Script:**
The latest server script includes enhanced stability measures:
- Increased rate limiting (500ms between renders)
- Proper scene invalidation after camera changes
- Enhanced GPU memory cleanup
- Better error handling and recovery

**2. Workflow Best Practices:**
- Add a 1-2 second delay between camera captures in your workflow
- Use JPEG format instead of PNG for better performance
- Keep resolution at 1920x1080 or lower
- Avoid rapid successive captures (< 500ms apart)

**3. Blender Settings for Stability:**
```python
# Add these to your Blender scene for better stability:
import bpy
scene = bpy.context.scene

# Disable persistent data to free memory between renders
scene.render.use_persistent_data = False

# Use simpler render engine for real-time capture
scene.render.engine = 'WORKBENCH'  # or 'EEVEE' instead of 'CYCLES'

# Reduce samples for faster rendering
if scene.render.engine == 'EEVEE':
    scene.eevee.taa_render_samples = 16  # Lower samples
    scene.eevee.use_motion_blur = False
    scene.eevee.use_bloom = False
```

**4. If Crashes Continue:**
- Restart Blender between workflow runs
- Use single captures instead of streaming
- Monitor GPU memory usage
- Consider using CPU rendering for complex scenes

### Blender Crashes with Metal/GPU Errors

If Blender crashes with Metal GPU errors (especially on Apple Silicon Macs), try these solutions:

**1. Reduce Stream Settings:**
- Lower frame rate to 5 FPS or less
- Use JPEG format instead of PNG
- Reduce resolution (e.g., 1280x720 instead of 1920x1080)
- Lower JPEG quality to 50-75

**2. Blender Render Settings:**
- In Blender Preferences > System:
  - Set "Cycles Render Device" to "CPU" instead of "GPU"
  - Or reduce "GPU Memory Limit" if using GPU rendering
- In Scene Properties > Render:
  - Use "Workbench" or "Eevee" engine instead of "Cycles" for real-time capture
  - Disable "Motion Blur" and "Ambient Occlusion"

**3. System Settings:**
- Close other GPU-intensive applications
- Ensure adequate system memory (8GB+ recommended)
- Update to latest Blender version
- Update macOS to latest version

**4. Node Configuration:**
- Use single capture nodes instead of streaming for heavy scenes
- Add delays between captures in workflows
- Monitor frame count and stop/restart streams periodically

### "Cannot connect to Blender MCP server"
- Ensure Blender is running
- Verify the HTTP server script is active
- Check that port 8080 is not blocked
- Try restarting the server script in Blender

### "Camera not found"
- Verify camera exists in Blender scene
- Check camera name spelling (case-sensitive)
- Use "Blender Camera List" to see available cameras

### Poor Performance
- Reduce resolution for real-time streaming
- Lower frame rate for continuous capture
- Use PNG for quality, JPEG for speed

## Development

To extend this library:

1. Follow the [Node Development Guide](../node-development-guide.md)
2. Add new nodes to `blender/` directory
3. Register in `griptape_nodes_library.json`
4. Test with active Blender session

## Requirements

- Blender 3.0+ (tested with 4.0+)
- Python 3.8+
- Active Blender session with HTTP server running

## License

MIT License - see LICENSE file for details.
