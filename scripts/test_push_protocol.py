"""
Test script for ZKTeco PUSH protocol endpoints.

This script simulates a device interacting with the PUSH protocol server.

Usage:
    python scripts/test_push_protocol.py
"""

import requests
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"
DEVICE_SERIAL = "TEST_MINIAC_001"


def test_device_heartbeat():
    """Test device registration/heartbeat endpoint."""
    print("\n=== Testing Device Heartbeat (GET /iclock/cdata) ===")
    
    url = f"{BASE_URL}/iclock/cdata"
    params = {
        "SN": DEVICE_SERIAL,
        "platform": "ZAM230_TFT",
        "FWVersion": "Ver1.0.27",
        "DeviceType": "T&A PUSH",
        "pushver": "2.0"
    }
    
    response = requests.get(url, params=params)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    assert response.status_code == 200
    assert response.text == "OK"
    print("✅ Device heartbeat successful")


def test_command_polling_empty():
    """Test command polling when no commands exist."""
    print("\n=== Testing Command Polling - Empty Queue (GET /iclock/getrequest) ===")
    
    url = f"{BASE_URL}/iclock/getrequest"
    params = {"SN": DEVICE_SERIAL}
    
    response = requests.get(url, params=params)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    assert response.status_code == 200
    assert response.text == "OK"
    print("✅ Empty queue polling successful")


def test_list_devices():
    """Test listing registered devices."""
    print("\n=== Testing Device List (GET /iclock/devices) ===")
    
    url = f"{BASE_URL}/iclock/devices"
    
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    data = response.json()
    print(f"Registered Devices: {len(data['devices'])}")
    
    if data['devices']:
        device = data['devices'][0]
        print(f"  - Serial: {device['serial_number']}")
        print(f"  - Platform: {device['platform']}")
        print(f"  - Firmware: {device['firmware_version']}")
        print(f"  - Last Seen: {device['last_seen']}")
    
    assert response.status_code == 200
    assert len(data['devices']) > 0
    print("✅ Device listing successful")


def test_attendance_upload():
    """Test attendance data upload."""
    print("\n=== Testing Attendance Upload (POST /iclock/cdata) ===")
    
    url = f"{BASE_URL}/iclock/cdata"
    params = {
        "SN": DEVICE_SERIAL,
        "table": "ATTLOG",
        "Stamp": str(int(time.time()))
    }
    
    # Simulate attendance records
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = f"ATTLOG:123\t{timestamp}\t0\t1\t0\t0\nATTLOG:456\t{timestamp}\t0\t1\t0\t0"
    
    response = requests.post(url, params=params, data=payload, headers={"Content-Type": "text/plain"})
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    print(f"Payload: {payload}")
    assert response.status_code == 200
    assert response.text == "OK"
    print("✅ Attendance upload successful")


def test_device_commands():
    """Test device command history."""
    print("\n=== Testing Command History (GET /iclock/devices/{serial}/commands) ===")
    
    url = f"{BASE_URL}/iclock/devices/{DEVICE_SERIAL}/commands"
    
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    data = response.json()
    print(f"Total Commands: {len(data['commands'])}")
    
    if data['commands']:
        cmd = data['commands'][0]
        print(f"  - Command ID: {cmd['command_id']}")
        print(f"  - Status: {cmd['status']}")
        print(f"  - Created: {cmd['created_at']}")
    
    assert response.status_code == 200
    print("✅ Command history retrieval successful")


def main():
    """Run all PUSH protocol tests."""
    print("=" * 60)
    print("ZKTeco PUSH Protocol - Integration Test")
    print("=" * 60)
    
    try:
        # Test endpoints
        test_device_heartbeat()
        test_command_polling_empty()
        test_list_devices()
        test_attendance_upload()
        test_device_commands()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        print("\nPUSH protocol implementation is working correctly.")
        print("Device can now communicate using iClock protocol.")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except requests.exceptions.ConnectionError:
        print("\n❌ Connection failed: Is the backend server running?")
        print("   Start server: uvicorn app:app --reload")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
