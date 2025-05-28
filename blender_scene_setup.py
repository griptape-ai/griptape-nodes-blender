"""
Blender Scene Setup Script for Stable Camera Capture
Run this script in Blender to optimize your scene for camera capture stability.
"""

import bpy

def setup_scene_for_capture():
    """Configure the current scene for stable camera capture."""
    
    scene = bpy.context.scene
    
    print("Setting up scene for stable camera capture...")
    
    # Basic render settings
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    
    # Disable problematic features
    scene.render.use_persistent_data = False
    scene.render.use_motion_blur = False
    
    # Configure based on render engine
    if scene.render.engine == 'BLENDER_EEVEE_NEXT':
        print("Configuring Eevee Next for stability...")
        
        # Reduce samples for speed
        if hasattr(scene.eevee, 'taa_render_samples'):
            scene.eevee.taa_render_samples = 16
            print(f"Set TAA samples to {scene.eevee.taa_render_samples}")
        
        # Disable expensive features
        if hasattr(scene.eevee, 'use_motion_blur'):
            scene.eevee.use_motion_blur = False
            print("Disabled motion blur")
            
        if hasattr(scene.eevee, 'use_bloom'):
            scene.eevee.use_bloom = False
            print("Disabled bloom")
            
        if hasattr(scene.eevee, 'use_ssr'):
            scene.eevee.use_ssr = False
            print("Disabled screen space reflections")
            
        if hasattr(scene.eevee, 'use_volumetric_lights'):
            scene.eevee.use_volumetric_lights = False
            print("Disabled volumetric lighting")
            
        # Set conservative shadow settings
        if hasattr(scene.eevee, 'shadow_cube_size'):
            scene.eevee.shadow_cube_size = '512'
            print("Set shadow cube size to 512")
            
        if hasattr(scene.eevee, 'shadow_cascade_size'):
            scene.eevee.shadow_cascade_size = '1024'
            print("Set shadow cascade size to 1024")
    
    elif scene.render.engine == 'CYCLES':
        print("Configuring Cycles for stability...")
        
        # Force CPU rendering for stability
        scene.cycles.device = 'CPU'
        print("Set Cycles to CPU rendering")
        
        # Reduce samples
        scene.cycles.samples = 32
        print(f"Set Cycles samples to {scene.cycles.samples}")
        
    elif scene.render.engine == 'WORKBENCH':
        print("Workbench engine detected - already optimized for speed")
        
    else:
        print(f"Unknown render engine: {scene.render.engine}")
        print("Consider switching to Workbench or Eevee for better stability")
    
    # Image format settings
    scene.render.image_settings.file_format = 'JPEG'
    scene.render.image_settings.quality = 90
    scene.render.image_settings.color_mode = 'RGB'
    
    print("Scene setup complete!")
    print(f"Render engine: {scene.render.engine}")
    print(f"Resolution: {scene.render.resolution_x}x{scene.render.resolution_y}")
    
    return True

def test_render():
    """Test render the current scene to verify setup."""
    
    print("\nTesting render...")
    
    scene = bpy.context.scene
    
    # Store original settings
    original_res_x = scene.render.resolution_x
    original_res_y = scene.render.resolution_y
    
    try:
        # Use small resolution for test
        scene.render.resolution_x = 320
        scene.render.resolution_y = 240
        
        print("Performing test render (320x240)...")
        bpy.ops.render.render(write_still=False)
        
        # Check if render result exists
        if 'Render Result' in bpy.data.images:
            image = bpy.data.images['Render Result']
            if image and hasattr(image, 'pixels') and len(image.pixels) > 0:
                print("✓ Test render successful!")
                return True
            else:
                print("✗ Test render failed - no image data")
                return False
        else:
            print("✗ Test render failed - no render result")
            return False
            
    except Exception as e:
        print(f"✗ Test render failed with error: {e}")
        return False
        
    finally:
        # Restore original settings
        scene.render.resolution_x = original_res_x
        scene.render.resolution_y = original_res_y

if __name__ == "__main__":
    print("Blender Scene Setup for Camera Capture")
    print("=" * 50)
    
    # Setup scene
    setup_success = setup_scene_for_capture()
    
    if setup_success:
        # Test render
        test_success = test_render()
        
        if test_success:
            print("\n✓ Scene is ready for camera capture!")
            print("You can now run the MCP server script and test camera capture.")
        else:
            print("\n✗ Scene setup completed but test render failed.")
            print("Check your scene for issues (missing materials, lights, etc.)")
    else:
        print("\n✗ Scene setup failed.")
    
    print("=" * 50) 