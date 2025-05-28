#!/usr/bin/env python3
"""
Test script to validate Blender camera capture stability fixes.
Run this script to test multiple camera captures with delays.
"""

import requests
import time
import json

def test_blender_stability():
    """Test multiple camera captures to validate stability fixes."""
    
    base_url = "http://localhost:8080"
    
    print("Testing Blender Camera Capture Stability")
    print("=" * 50)
    
    # Test 1: Check server status
    print("1. Testing server connection...")
    try:
        response = requests.get(f"{base_url}/api/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Server connected - Blender {data.get('blender_version', 'Unknown')}")
            print(f"  Scene: {data.get('scene', 'Unknown')}")
        else:
            print(f"✗ Server returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Cannot connect to server: {e}")
        print("  Make sure Blender is running with the MCP server script")
        return False
    
    # Test 2: Get available cameras
    print("\n2. Getting available cameras...")
    try:
        response = requests.get(f"{base_url}/api/cameras", timeout=5)
        if response.status_code == 200:
            cameras = response.json().get('cameras', [])
            if cameras:
                camera_name = cameras[0]['name']
                print(f"✓ Found {len(cameras)} camera(s)")
                print(f"  Using camera: {camera_name}")
            else:
                print("✗ No cameras found in scene")
                return False
        else:
            print(f"✗ Failed to get cameras: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error getting cameras: {e}")
        return False
    
    # Test 3: Multiple captures with delays
    print(f"\n3. Testing multiple captures from '{camera_name}'...")
    print("   (This simulates moving camera between captures)")
    
    capture_params = {
        "format": "jpeg",
        "width": 1280,
        "height": 720,
        "quality": 75
    }
    
    success_count = 0
    total_tests = 5
    
    for i in range(total_tests):
        print(f"\n   Capture {i+1}/{total_tests}:")
        
        # Add delay between captures (simulating user moving camera)
        if i > 0:
            print("     Waiting 2 seconds (simulating camera movement)...")
            time.sleep(2.0)
        
        try:
            start_time = time.time()
            response = requests.get(
                f"{base_url}/api/camera/{camera_name}/render",
                params=capture_params,
                timeout=45
            )
            end_time = time.time()
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'image/' in content_type:
                    image_size = len(response.content)
                    render_time = end_time - start_time
                    print(f"     ✓ Success - {image_size:,} bytes in {render_time:.2f}s")
                    success_count += 1
                else:
                    print(f"     ✗ Unexpected content type: {content_type}")
            elif response.status_code == 429:
                print("     ⚠ Rate limited - waiting and retrying...")
                time.sleep(1.0)
                # Retry once
                response = requests.get(
                    f"{base_url}/api/camera/{camera_name}/render",
                    params=capture_params,
                    timeout=45
                )
                if response.status_code == 200:
                    print("     ✓ Success on retry")
                    success_count += 1
                else:
                    print(f"     ✗ Failed on retry: {response.status_code}")
            else:
                print(f"     ✗ Failed with status {response.status_code}")
                if response.headers.get('content-type') == 'application/json':
                    try:
                        error_data = response.json()
                        print(f"       Error: {error_data.get('error', 'Unknown')}")
                    except:
                        pass
                        
        except requests.exceptions.Timeout:
            print("     ✗ Timeout (>45s) - possible Blender crash")
        except requests.exceptions.ConnectionError:
            print("     ✗ Connection lost - Blender may have crashed")
            break
        except Exception as e:
            print(f"     ✗ Error: {e}")
    
    # Test results
    print(f"\n4. Test Results:")
    print(f"   Successful captures: {success_count}/{total_tests}")
    
    if success_count == total_tests:
        print("   ✓ All tests passed - stability fixes working!")
        return True
    elif success_count > 0:
        print("   ⚠ Partial success - some stability issues remain")
        return False
    else:
        print("   ✗ All tests failed - stability issues persist")
        return False

def test_rate_limiting():
    """Test rate limiting functionality."""
    print("\n" + "=" * 50)
    print("Testing Rate Limiting")
    print("=" * 50)
    
    base_url = "http://localhost:8080"
    
    # Get first camera
    try:
        response = requests.get(f"{base_url}/api/cameras", timeout=5)
        cameras = response.json().get('cameras', [])
        if not cameras:
            print("No cameras available for rate limit test")
            return
        camera_name = cameras[0]['name']
    except:
        print("Cannot get cameras for rate limit test")
        return
    
    print(f"Testing rapid requests to camera '{camera_name}'...")
    
    # Make rapid requests
    for i in range(3):
        try:
            start_time = time.time()
            response = requests.get(
                f"{base_url}/api/camera/{camera_name}/render",
                params={"format": "jpeg", "width": 640, "height": 480},
                timeout=10
            )
            end_time = time.time()
            
            if response.status_code == 429:
                print(f"  Request {i+1}: ✓ Rate limited (as expected)")
            elif response.status_code == 200:
                print(f"  Request {i+1}: ✓ Success in {end_time - start_time:.2f}s")
            else:
                print(f"  Request {i+1}: Status {response.status_code}")
                
        except Exception as e:
            print(f"  Request {i+1}: Error - {e}")
        
        # Small delay between rapid requests
        time.sleep(0.1)

if __name__ == "__main__":
    print("Blender Camera Capture Stability Test")
    print("Make sure Blender is running with the updated MCP server script!")
    print()
    
    # Run stability test
    stability_ok = test_blender_stability()
    
    # Run rate limiting test
    test_rate_limiting()
    
    print("\n" + "=" * 50)
    if stability_ok:
        print("✓ Stability tests PASSED - fixes are working!")
    else:
        print("✗ Stability tests FAILED - issues remain")
        print("\nTroubleshooting tips:")
        print("1. Make sure you're using the updated MCP server script")
        print("2. Try restarting Blender")
        print("3. Check Blender render engine (use Workbench/Eevee)")
        print("4. Reduce scene complexity")
    print("=" * 50) 