# Griptape Nodes Blender Integration

Camera capture nodes for Blender integration with Griptape workflows.

## Overview

This package provides Griptape nodes for capturing camera views from Blender scenes. The integration works through an external MCP (Model Context Protocol) server that communicates with Blender.

## Architecture

```
┌─────────────────┐    MCP Protocol    ┌──────────────────┐    Python API    ┌─────────┐
│ Griptape Nodes  │ ←─────────────────→ │   MCP Server     │ ←───────────────→ │ Blender │
│   (Clients)     │                    │  (Standalone)    │                   │  (bpy)  │
└─────────────────┘                    └──────────────────┘                   └─────────┘
```

## Files

- `blender/blender_mcp_server.py` - MCP server that connects to Blender
- `blender/mcp_client.py` - MCP client utilities for Griptape nodes
- `blender/camera_capture.py` - Camera capture node for Griptape workflows
- `blender/camera_list.py` - Node to list available cameras in Blender scene
- `blender/camera_stream.py` - Node for real-time camera streaming
- `requirements.txt` - Python dependencies

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Ensure Blender is Available

The MCP server needs to be able to run Blender. Make sure Blender is:
- Installed on your system
- Available in your PATH, or
- Located at a standard path like `/Applications/Blender.app/Contents/MacOS/Blender` (macOS)

### 3. Test the MCP Server

You can test the MCP server directly:

```bash
# This will start Blender in background mode with the MCP server
/Applications/Blender.app/Contents/MacOS/Blender --background --python blender/blender_mcp_server.py
```

## Usage

### Camera Capture Node

The camera capture node allows you to:
- Capture images from specific Blender cameras
- Set custom resolution (64x64 to 4096x4096)
- Choose output format (PNG or JPEG)
- Integrate Blender renders into Griptape workflows

**Parameters:**
- `camera_name` - Name of camera in Blender scene (default: "Camera")
- `width` - Image width in pixels (default: 1920)
- `height` - Image height in pixels (default: 1080)
- `format` - Output format: PNG or JPEG (default: PNG)
- `quality` - JPEG quality 1-100 (default: 90, ignored for PNG)

**Outputs:**
- `image_output` - Captured image as ImageArtifact
- `status_output` - Status message and render information

### Camera List Node

Lists all cameras available in the current Blender scene.

**Outputs:**
- `cameras_output` - List of camera information (name, location, rotation, active status)
- `camera_count` - Total number of cameras found

### Camera Stream Node

Provides real-time streaming from a Blender camera.

**Parameters:**
- `camera_name` - Name of camera to stream from
- `frame_rate` - Capture rate in FPS
- `stream_duration` - How long to stream (seconds)

**Outputs:**
- `frame_output` - Latest captured frame
- `frame_count` - Number of frames captured

## MCP Server Features

The MCP server provides these tools:

1. **render_camera** - Render image from specified camera
2. **list_cameras** - List all cameras in scene
3. **get_scene_info** - Get scene metadata (name, frame range, render settings)
4. **health_check** - Check if Blender is responding

### Engine Optimizations

The server automatically handles render engine issues:

- **Eevee Next** → Switches to Cycles CPU (headless rendering fix)
- **Cycles** → Forces CPU rendering for stability
- **Eevee** → Optimizes settings (reduced samples, disabled effects)
- **Workbench** → Uses as-is (most stable)

## Benefits

✅ **No Blender modifications** - Users don't need to change anything in Blender
✅ **Standard MCP protocol** - Works with any MCP client
✅ **Stable external process** - Won't hang or crash Blender
✅ **Automatic engine handling** - Fixes known Eevee Next issues
✅ **Clean separation** - Server handles all Blender complexity

## Development Status

🟢 **Ready for Testing** - MCP server and client implementation complete.

## Troubleshooting

### "Could not connect to Blender MCP server"

1. Verify Blender is installed and accessible
2. Check that `blender/blender_mcp_server.py` exists
3. Try running the server manually to see error messages
4. Ensure MCP dependencies are installed (`pip install -r requirements.txt`)

### "bpy module not available"

The MCP server must run with Blender's Python environment. This is handled automatically by the client launching Blender with the server script.

### Render Issues

The server includes automatic fixes for common issues:
- Eevee Next headless rendering problems
- GPU context issues in headless mode
- Memory cleanup between renders

## Requirements

- Blender 3.0+ (tested with 4.4+)
- Python 3.8+
- MCP dependencies (see requirements.txt)
