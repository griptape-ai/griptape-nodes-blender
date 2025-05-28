#!/usr/bin/env python3
"""
Diagnostic script to identify the cause of Blender crashes during camera capture.
This script performs minimal operations to isolate the crash source.
"""

import requests
import time
import json
import sys

def diagnose_blender_crash():
    """Perform step-by-step diagnosis to identify crash causes."""
    
    base_url = "http://localhost:8080"
    
    print("Blender Crash Diagnostic Tool")
    print("=" * 50)
    print("This tool will help identify what's causing Blender to crash.")
    print()
    
    # Step 1: Basic connectivity
    print("Step 1: Testing basic connectivity...")
    try:
        response = requests.get(f"{base_url}/api/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Connected to Blender {data.get('blender_version')}")
            print(f"  Scene: {data.get('scene')}")
            print(f"  Render engine: {data.get('render_engine', 'Unknown')}")
            print(f"  Render count: {data.get('render_count', 0)}")
        else:
            print(f"✗ Status check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Cannot connect: {e}")
        return False
    
    # Step 2: Camera detection
    print("\nStep 2: Testing camera detection...")
    try:
        response = requests.get(f"{base_url}/api/cameras", timeout=5)
        if response.status_code == 200:
            cameras = response.json().get('cameras', [])
            if cameras:
                print(f"✓ Found {len(cameras)} camera(s):")
                for cam in cameras:
                    print(f"  - {cam['name']} at {cam['location']}")
                camera_name = cameras[0]['name']
            else:
                print("✗ No cameras found")
                return False
        else:
            print(f"✗ Camera detection failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Camera detection error: {e}")
        return False
    
    # Step 3: Minimal render test
    print(f"\nStep 3: Testing minimal render from '{camera_name}'...")
    
    # Ultra-minimal parameters
    minimal_params = {
        "format": "jpeg",
        "width": 160,    # Tiny resolution
        "height": 120,   # Tiny resolution
        "quality": 10    # Lowest quality
    }
    
    print(f"  Using minimal settings: {minimal_params}")
    
    try:
        print("  Making render request...")
        start_time = time.time()
        
        response = requests.get(
            f"{base_url}/api/camera/{camera_name}/render",
            params=minimal_params,
            timeout=30
        )
        
        end_time = time.time()
        render_time = end_time - start_time
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image/' in content_type:
                image_size = len(response.content)
                print(f"  ✓ Minimal render successful!")
                print(f"    Size: {image_size:,} bytes")
                print(f"    Time: {render_time:.2f}s")
                print(f"    Content-Type: {content_type}")
            else:
                print(f"  ✗ Unexpected content type: {content_type}")
                return False
        elif response.status_code == 429:
            print("  ⚠ Rate limited on first request - server may be overloaded")
            return False
        else:
            print(f"  ✗ Render failed: {response.status_code}")
            if response.headers.get('content-type') == 'application/json':
                try:
                    error_data = response.json()
                    print(f"    Error: {error_data.get('error')}")
                except:
                    pass
            return False
            
    except requests.exceptions.Timeout:
        print("  ✗ Timeout - Blender may be frozen")
        return False
    except requests.exceptions.ConnectionError:
        print("  ✗ Connection lost - Blender may have crashed")
        return False
    except Exception as e:
        print(f"  ✗ Render error: {e}")
        return False
    
    # Step 4: Test server health after render
    print("\nStep 4: Checking server health after render...")
    time.sleep(2)  # Wait a moment
    
    try:
        response = requests.get(f"{base_url}/api/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Server still responsive")
            print(f"    Render count now: {data.get('render_count', 0)}")
        else:
            print(f"  ✗ Server health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Server health check error: {e}")
        return False
    
    # Step 5: Test second render (this is where crashes often happen)
    print("\nStep 5: Testing second render (crash-prone operation)...")
    print("  Waiting 3 seconds before second render...")
    time.sleep(3)
    
    try:
        print("  Making second render request...")
        start_time = time.time()
        
        response = requests.get(
            f"{base_url}/api/camera/{camera_name}/render",
            params=minimal_params,
            timeout=30
        )
        
        end_time = time.time()
        render_time = end_time - start_time
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image/' in content_type:
                image_size = len(response.content)
                print(f"  ✓ Second render successful!")
                print(f"    Size: {image_size:,} bytes")
                print(f"    Time: {render_time:.2f}s")
                return True
            else:
                print(f"  ✗ Second render - unexpected content type: {content_type}")
                return False
        else:
            print(f"  ✗ Second render failed: {response.status_code}")
            return False
            
    except requests.exceptions.Timeout:
        print("  ✗ Second render timeout - likely crash point")
        return False
    except requests.exceptions.ConnectionError:
        print("  ✗ Second render connection lost - Blender crashed here")
        return False
    except Exception as e:
        print(f"  ✗ Second render error: {e}")
        return False

def get_blender_info():
    """Get detailed Blender configuration info."""
    print("\nBlender Configuration Analysis")
    print("=" * 50)
    
    base_url = "http://localhost:8080"
    
    try:
        response = requests.get(f"{base_url}/api/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            
            print(f"Blender Version: {data.get('blender_version', 'Unknown')}")
            print(f"Scene Name: {data.get('scene', 'Unknown')}")
            print(f"Render Engine: {data.get('render_engine', 'Unknown')}")
            print(f"Total Renders: {data.get('render_count', 0)}")
            
            # Analyze render engine
            engine = data.get('render_engine', '').upper()
            if engine == 'CYCLES':
                print("\n⚠ WARNING: Using Cycles render engine")
                print("  Cycles can be GPU-intensive and crash-prone")
                print("  Recommendation: Switch to Workbench or Eevee")
            elif engine == 'EEVEE':
                print("\n✓ Using Eevee render engine (good for real-time)")
            elif engine == 'WORKBENCH':
                print("\n✓ Using Workbench render engine (most stable)")
            else:
                print(f"\n? Unknown render engine: {engine}")
            
        else:
            print("Cannot get Blender configuration")
            
    except Exception as e:
        print(f"Configuration check failed: {e}")

def recommend_fixes():
    """Provide recommendations based on diagnosis."""
    print("\nRecommendations to Prevent Crashes")
    print("=" * 50)
    
    print("1. UPDATE MCP SERVER SCRIPT:")
    print("   - Use the ultra-stable version from the README")
    print("   - It forces CPU rendering and aggressive cleanup")
    
    print("\n2. BLENDER SETTINGS:")
    print("   - Switch render engine to 'Workbench' (most stable)")
    print("   - Or use 'Eevee' with minimal samples")
    print("   - Avoid 'Cycles' for real-time capture")
    
    print("\n3. SCENE OPTIMIZATION:")
    print("   - Reduce scene complexity")
    print("   - Remove unnecessary objects")
    print("   - Disable motion blur, bloom, etc.")
    
    print("\n4. WORKFLOW CHANGES:")
    print("   - Add 2-3 second delays between captures")
    print("   - Use smaller resolutions (640x480 or less)")
    print("   - Restart Blender every 10-20 captures")
    
    print("\n5. SYSTEM SETTINGS:")
    print("   - Close other GPU-intensive applications")
    print("   - Ensure adequate RAM (8GB+ recommended)")
    print("   - Update Blender to latest version")

if __name__ == "__main__":
    print("Starting Blender crash diagnosis...")
    print("Make sure Blender is running with the MCP server script!")
    print()
    
    # Get system info first
    get_blender_info()
    
    # Run diagnosis
    success = diagnose_blender_crash()
    
    print("\n" + "=" * 50)
    if success:
        print("✓ DIAGNOSIS COMPLETE - No crashes detected!")
        print("The current setup appears stable with minimal renders.")
        print("Try the conservative test script next.")
    else:
        print("✗ DIAGNOSIS FAILED - Crash or instability detected!")
        print("The issue occurs during basic rendering operations.")
    
    # Always provide recommendations
    recommend_fixes()
    
    print("\n" + "=" * 50) 