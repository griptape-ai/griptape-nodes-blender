# Griptape Nodes Blender Integration

Camera capture nodes for Blender integration with Griptape workflows.

## Overview

This package provides Griptape nodes for capturing camera views from Blender scenes. The integration works through a simple socket server that runs inside Blender, providing a reliable and efficient communication channel.

## Architecture

```
┌─────────────────┐    Socket/TCP     ┌──────────────────┐    bpy Python API ┌─────────┐
│ Griptape Nodes  │ ←─────────────────→ │  Socket Server   │ ←───────────────→ │ Blender │
│   (Clients)     │     JSON/8765     │  (Inside Blender) │                   │ (3D App) │
└─────────────────┘                   └──────────────────┘                   └─────────┘
```

## Features

- ✅ **Simple socket communication** - No complex async context issues
- ✅ **Runs inside Blender** - Direct access to bpy API and scene data  
- ✅ **Real-time camera capture** - Render images from any camera in scene
- ✅ **Comprehensive camera metadata** - Focal length, sensor info, DOF, transforms
- ✅ **Dynamic UI updates** - Camera dropdowns and metadata labels update automatically
- ✅ **Flow control support** - Both nodes integrate seamlessly into control workflows
- ✅ **Always fresh data** - Camera List Node re-evaluates on every workflow run
- ✅ **Automatic engine handling** - Fixes Eevee Next and GPU issues automatically
- ✅ **No external dependencies** - Just Python standard library
- ✅ **Easy setup** - Copy/paste script into Blender

## Files

- `blender/blender_socket_server.py` - Socket server that runs inside Blender
- `blender/socket_client.py` - Socket client utilities for Griptape nodes  
- `blender/camera_capture.py` - Camera capture node for Griptape workflows
- `blender/camera_list.py` - Node to list available cameras in Blender scene

## Quick Setup

### 1. Start Blender Socket Server

1. **Open Blender**
2. **Go to Scripting workspace** (tab at top)
3. **Create new text file** (click "New")
4. **Copy the entire contents** of `blender/blender_socket_server.py`
5. **Paste into Blender's text editor**
6. **Click "Run Script"** button

The server will auto-start and show:
```
✓ Blender Socket Server started on localhost:8765
Ready to receive commands from Griptape nodes
```

### 2. Use Griptape Nodes

The camera capture and camera list nodes will automatically connect to the socket server running in Blender.

## Server Controls

### In Blender Console:
```python
start_server()    # Start the socket server
stop_server()     # Stop the socket server  
server_status()   # Check if running
```

### In Blender UI:
- **3D Viewport** → Press `N` → **Griptape tab**
- **Start/Stop buttons** with status indicator
- **Port information** display

## Available Nodes

### Camera Capture Node

Captures single frames from Blender cameras with detailed camera metadata display.

**Flow Control:**
- `exec_in` - Flow input for control sequencing
- `exec_out` - Flow output for control sequencing

**Parameters:**
- `cameras_input` - Connect to Camera List Node for dynamic camera data (optional)
- `camera_name` - Name of camera in Blender scene (dropdown updates automatically)
- `resolution_x` - Image width in pixels (64-4096, default: 1920)
- `resolution_y` - Image height in pixels (64-4096, default: 1080) 
- `output_format` - PNG or JPEG (default: PNG)
- `quality` - JPEG quality 1-100 (default: 90)

**Camera Metadata Labels (displayed under Camera dropdown):**
- `Status` - Shows if camera is active scene camera
- `Focal Length` - Lens focal length in mm
- `Sensor` - Sensor dimensions, fit mode, and camera type
- `Depth of Field` - DOF settings including focus distance and f-stop
- `Transform` - Camera location and rotation coordinates

**Outputs:**
- `image_output` - Captured image as ImageUrlArtifact
- `status_output` - Render information and timing

**Features:**
- ✅ **Dynamic camera dropdown** - Updates automatically when connected to Camera List Node
- ✅ **Rich metadata display** - Shows detailed camera properties in real-time
- ✅ **Enhanced camera data** - Accesses comprehensive Blender camera properties
- ✅ **Auto camera validation** - Switches to available camera if selection invalid

### Camera List Node

Lists all cameras in the current Blender scene with comprehensive metadata.

**Flow Control:**
- `exec_in` - Flow input for control sequencing  
- `exec_out` - Flow output for control sequencing

**Features:**
- ✅ **Always re-evaluates** - Fetches fresh camera data on every workflow run
- ✅ **Comprehensive camera data** - Collects detailed camera properties via Blender API
- ✅ **Automatic fallback** - Falls back to basic data if enhanced collection fails

**Outputs:**
- `cameras_output` - Detailed camera info including metadata (ListArtifact)
- `camera_count` - Total number of cameras found
- `status_output` - Operation status and connection info

**Enhanced Camera Data Collected:**
- **Basic Transform:** Location, rotation, scale, active status
- **Lens Properties:** Focal length, sensor dimensions, sensor fit mode
- **Camera Type:** Perspective, orthographic, panoramic
- **Field of View:** Angular measurements for framing calculations
- **Clipping Distances:** Near and far render boundaries
- **Depth of Field:** Focus distance, aperture f-stop settings
- **Composition:** Camera shift for perspective correction
- **Matrix Data:** Full 4x4 transformation matrix for precise positioning

## Workflow Integration

### Connected Workflow (Recommended)

For the best experience, connect Camera List Node → Camera Capture Node:

```
┌─────────────────┐ cameras_output ┌──────────────────────┐
│ Camera List     │────────────────→│ Camera Capture      │
│                 │                 │                      │
│ • Always fresh  │                 │ • Dynamic dropdown  │
│ • Detailed data │                 │ • Metadata labels   │
│ • Flow control  │                 │ • Auto validation   │
└─────────────────┘                 └──────────────────────┘
```

**Benefits:**
- ✅ **Camera dropdown updates automatically** when scene changes
- ✅ **Rich metadata display** under camera selection
- ✅ **Always current data** - Camera List always re-evaluates  
- ✅ **Seamless flow control** - Both nodes support exec in/out

### Standalone Usage

Camera Capture Node works independently but with limited features:
- Static camera dropdown (populated at node creation)
- Basic status messages instead of detailed metadata
- Manual refresh required for scene changes

## Socket Server Commands

The server responds to these JSON commands on port 8765:

### Health Check
```json
{"command": "health_check"}
```

### Scene Information  
```json
{"command": "get_scene_info"}
```

### List Cameras
```json
{"command": "list_cameras"}
```

### Render Camera
```json
{
  "command": "render_camera",
  "params": {
    "camera_name": "Camera",
    "width": 1920,
    "height": 1080,
    "format_type": "PNG",
    "quality": 90
  }
}
```

### Execute Code (Enhanced Camera Data)
```json
{
  "command": "execute_code", 
  "params": {
    "code": "import bpy; cameras = [{'name': obj.name, 'focal_length': obj.data.lens} for obj in bpy.data.objects if obj.type == 'CAMERA']"
  }
}
```

## Engine Handling

The server automatically handles render engine issues:

- **Eevee Next** → Switches to Cycles CPU (headless stability)
- **Cycles** → Forces CPU rendering (avoids GPU context issues)
- **Other engines** → CPU-only for maximum stability

## Benefits vs MCP Approach

✅ **No async context issues** - Simple socket connections  
✅ **Persistent server** - Runs inside Blender, stays responsive
✅ **Easy debugging** - Clear JSON communication
✅ **No complex dependencies** - Just Python sockets
✅ **Better performance** - Direct bpy access, no process spawning

## Troubleshooting

### "Could not connect to Blender server at localhost:8765"

1. **Make sure Blender is running** with the socket server script
2. **Check server status** in Blender console: `server_status()`
3. **Restart server** if needed: `stop_server()` then `start_server()`
4. **Check port availability** - make sure nothing else is using port 8765

### "PIL not available for PNG encoding"

The server needs PIL for image encoding. Install in Blender's Python:
```bash
/Applications/Blender.app/Contents/Resources/4.4/python/bin/python3.11 -m pip install Pillow
```

### Socket Server Not Starting

1. **Check Blender console** for error messages
2. **Verify script is run inside Blender** (not external Python)
3. **Try different port** by editing the script: `BlenderSocketServer(port=8766)`

### Render Issues

- Server forces CPU rendering for stability
- Automatically switches problematic engines (Eevee Next)
- Check Blender console for render error messages

## Requirements

- **Blender 3.0+** (tested with 4.4.3)
- **Python 3.8+** (included with Blender)
- **Pillow** (for image encoding, install in Blender's Python)

## No External Dependencies

Unlike the previous MCP approach, this socket-based solution requires no external Python packages in your Griptape environment. All communication happens through standard Python sockets.
