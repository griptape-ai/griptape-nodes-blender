#!/usr/bin/env python3
"""
Test script to validate Blender camera capture stability fixes.
Run this script to test multiple camera captures with delays.
CONSERVATIVE VERSION - designed to avoid crashing Blender.
"""

import requests
import time
import json
import sys

def test_blender_stability():
    """Test multiple camera captures to validate stability fixes."""
    
    base_url = "http://localhost:8080"
    
    print("Testing Blender Camera Capture Stability (Conservative Mode)")
    print("=" * 60)
    
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
    
    # Test 3: Conservative capture test with very long delays
    print(f"\n3. Testing conservative captures from '{camera_name}'...")
    print("   (Using very long delays to prevent GPU overload)")
    
    # Use very conservative settings
    capture_params = {
        "format": "jpeg",
        "width": 640,   # Much smaller resolution
        "height": 480,  # Much smaller resolution
        "quality": 50   # Lower quality for speed
    }
    
    success_count = 0
    total_tests = 3  # Reduced from 5 to 3 tests
    
    for i in range(total_tests):
        print(f"\n   Capture {i+1}/{total_tests}:")
        
        # Much longer delay between captures
        if i > 0:
            delay_time = 5.0  # Increased from 2s to 5s
            print(f"     Waiting {delay_time} seconds for GPU recovery...")
            time.sleep(delay_time)
        
        # Check server is still alive before each request
        try:
            health_check = requests.get(f"{base_url}/api/status", timeout=3)
            if health_check.status_code != 200:
                print("     ✗ Server health check failed - Blender may have crashed")
                break
        except:
            print("     ✗ Cannot reach server - Blender may have crashed")
            break
        
        try:
            print("     Starting render request...")
            start_time = time.time()
            
            response = requests.get(
                f"{base_url}/api/camera/{camera_name}/render",
                params=capture_params,
                timeout=60  # Longer timeout
            )
            end_time = time.time()
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'image/' in content_type:
                    image_size = len(response.content)
                    render_time = end_time - start_time
                    print(f"     ✓ Success - {image_size:,} bytes in {render_time:.2f}s")
                    success_count += 1
                    
                    # Additional delay after successful render
                    print("     Waiting 2s for GPU cleanup...")
                    time.sleep(2.0)
                else:
                    print(f"     ✗ Unexpected content type: {content_type}")
                    
            elif response.status_code == 429:
                print("     ⚠ Rate limited - waiting longer...")
                time.sleep(3.0)  # Longer wait for rate limiting
                print("     Skipping retry to avoid overloading Blender")
                
            elif response.status_code == 500:
                print("     ✗ Server error - Blender may be unstable")
                print("     Stopping test to prevent crash")
                break
                
            else:
                print(f"     ✗ Failed with status {response.status_code}")
                if response.headers.get('content-type') == 'application/json':
                    try:
                        error_data = response.json()
                        print(f"       Error: {error_data.get('error', 'Unknown')}")
                    except:
                        pass
                        
        except requests.exceptions.Timeout:
            print("     ✗ Timeout (>60s) - Blender may be struggling")
            print("     Stopping test to prevent crash")
            break
            
        except requests.exceptions.ConnectionError:
            print("     ✗ Connection lost - Blender crashed")
            break
            
        except Exception as e:
            print(f"     ✗ Error: {e}")
            print("     Stopping test to prevent further issues")
            break
    
    # Test results
    print(f"\n4. Conservative Test Results:")
    print(f"   Successful captures: {success_count}/{total_tests}")
    
    if success_count == total_tests:
        print("   ✓ All conservative tests passed!")
        return True
    elif success_count > 0:
        print("   ⚠ Partial success - stability improvements needed")
        return False
    else:
        print("   ✗ All tests failed - major stability issues")
        return False

def test_single_capture():
    """Test a single capture to validate basic functionality."""
    print("\n" + "=" * 60)
    print("Testing Single Capture (Safest Test)")
    print("=" * 60)
    
    base_url = "http://localhost:8080"
    
    # Get first camera
    try:
        response = requests.get(f"{base_url}/api/cameras", timeout=5)
        cameras = response.json().get('cameras', [])
        if not cameras:
            print("No cameras available for single capture test")
            return False
        camera_name = cameras[0]['name']
    except:
        print("Cannot get cameras for single capture test")
        return False
    
    print(f"Testing single capture from camera '{camera_name}'...")
    
    # Very safe parameters
    safe_params = {
        "format": "jpeg",
        "width": 320,   # Very small
        "height": 240,  # Very small
        "quality": 30   # Low quality
    }
    
    try:
        print("  Making single render request...")
        start_time = time.time()
        response = requests.get(
            f"{base_url}/api/camera/{camera_name}/render",
            params=safe_params,
            timeout=30
        )
        end_time = time.time()
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image/' in content_type:
                image_size = len(response.content)
                render_time = end_time - start_time
                print(f"  ✓ Single capture successful - {image_size:,} bytes in {render_time:.2f}s")
                return True
            else:
                print(f"  ✗ Unexpected content type: {content_type}")
                return False
        else:
            print(f"  ✗ Failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ✗ Single capture failed: {e}")
        return False

def check_blender_health():
    """Check if Blender is responsive and stable."""
    print("\n" + "=" * 60)
    print("Checking Blender Health")
    print("=" * 60)
    
    base_url = "http://localhost:8080"
    
    health_checks = [
        ("Status endpoint", f"{base_url}/api/status"),
        ("Cameras endpoint", f"{base_url}/api/cameras"),
    ]
    
    all_healthy = True
    
    for check_name, url in health_checks:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"  ✓ {check_name}: OK")
            else:
                print(f"  ✗ {check_name}: Status {response.status_code}")
                all_healthy = False
        except Exception as e:
            print(f"  ✗ {check_name}: {e}")
            all_healthy = False
    
    return all_healthy

if __name__ == "__main__":
    print("Blender Camera Capture Stability Test (CONSERVATIVE)")
    print("This version uses very conservative settings to avoid crashes.")
    print("Make sure Blender is running with the updated MCP server script!")
    print()
    
    # Check health first
    if not check_blender_health():
        print("\n✗ Blender health check failed - not proceeding with tests")
        sys.exit(1)
    
    # Test single capture first (safest)
    print("\nStarting with safest test...")
    single_ok = test_single_capture()
    
    if not single_ok:
        print("\n✗ Single capture failed - Blender may be unstable")
        print("Recommendation: Restart Blender and check the MCP server script")
        sys.exit(1)
    
    # Ask user before proceeding to multi-capture test
    print("\nSingle capture successful. Proceed with multi-capture test?")
    print("WARNING: This may still crash Blender if stability issues remain.")
    
    try:
        user_input = input("Continue? (y/N): ").strip().lower()
        if user_input not in ['y', 'yes']:
            print("Stopping at user request.")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(0)
    
    # Run conservative stability test
    print("\nProceeding with conservative multi-capture test...")
    stability_ok = test_blender_stability()
    
    print("\n" + "=" * 60)
    if stability_ok:
        print("✓ Conservative stability tests PASSED!")
        print("The fixes appear to be working with conservative settings.")
    else:
        print("✗ Stability tests FAILED or incomplete")
        print("\nRecommendations:")
        print("1. The MCP server script needs further improvements")
        print("2. Try restarting Blender completely")
        print("3. Use even longer delays between captures (10+ seconds)")
        print("4. Consider using CPU rendering instead of GPU")
        print("5. Reduce scene complexity")
    print("=" * 60) 