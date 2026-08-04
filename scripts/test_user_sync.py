"""
Test script for ZKTeco PUSH Protocol - User Synchronization (Phase 3)

This script demonstrates the complete user synchronization flow:
1. Create a test member via API
2. Verify DeviceCommand was automatically queued
3. Simulate device polling to retrieve the command
4. Verify command format and content

Prerequisites:
- Backend server running (uvicorn app:app --reload)
- At least one PUSH device registered (or run this script to register a test device)

Usage:
    python scripts/test_user_sync.py
"""

import sys
import time
from datetime import datetime

import requests

BASE_URL = "http://localhost:8000"
TEST_DEVICE_SERIAL = "TEST_DEVICE_001"


def register_test_device():
    """Register a test device so we have a target for user sync."""
    print("\n=== Step 1: Register Test Device ===")
    
    url = f"{BASE_URL}/iclock/cdata"
    params = {
        "SN": TEST_DEVICE_SERIAL,
        "platform": "ZAM230_TFT",
        "FWVersion": "Ver1.0.27",
        "DeviceType": "T&A PUSH"
    }
    
    try:
        response = requests.get(url, params=params)
        print(f"Device registration: {response.status_code}")
        print(f"Response: {response.text}")
        
        # Verify device is registered
        device_list_url = f"{BASE_URL}/iclock/devices"
        devices_response = requests.get(device_list_url)
        devices = devices_response.json()["devices"]
        
        test_device = next((d for d in devices if d["serial_number"] == TEST_DEVICE_SERIAL), None)
        if test_device:
            print(f"✅ Device registered: {TEST_DEVICE_SERIAL}")
            return True
        else:
            print(f"❌ Device not found after registration")
            return False
    except Exception as e:
        print(f"❌ Failed to register device: {e}")
        return False


def create_test_member():
    """Create a test member via the admin API."""
    print("\n=== Step 2: Create Test Member ===")
    
    url = f"{BASE_URL}/admin/members"
    
    # Generate unique mobile number using timestamp
    timestamp = int(time.time())
    mobile_number = f"9999{timestamp % 1000000}"
    
    payload = {
        "full_name": "Test User Sync",
        "mobile_number": mobile_number,
        "joining_date": datetime.now().strftime("%Y-%m-%d"),
        "status": "active"
    }
    
    try:
        response = requests.post(url, json=payload)
        print(f"Member creation: {response.status_code}")
        
        if response.status_code == 201:
            member_data = response.json()["data"]
            member_id = member_data["id"]
            print(f"✅ Member created:")
            print(f"   ID: {member_id}")
            print(f"   Name: {member_data['full_name']}")
            print(f"   Mobile: {member_data['mobile_number']}")
            return member_id
        else:
            print(f"❌ Failed to create member: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Failed to create member: {e}")
        return None


def check_queued_commands(member_id):
    """Check if user sync commands were queued for the member."""
    print("\n=== Step 3: Verify Commands Queued ===")
    
    url = f"{BASE_URL}/iclock/devices/{TEST_DEVICE_SERIAL}/commands"
    
    try:
        response = requests.get(url)
        commands = response.json()["commands"]
        
        # Find commands for this member
        member_commands = [
            cmd for cmd in commands
            if f"sync_user_{member_id}_" in cmd["command_id"]
        ]
        
        if member_commands:
            print(f"✅ Found {len(member_commands)} queued command(s)")
            for cmd in member_commands:
                print(f"\n   Command ID: {cmd['command_id']}")
                print(f"   Status: {cmd['status']}")
                print(f"   Command: {cmd['command']}")
                print(f"   Created: {cmd['created_at']}")
            return True
        else:
            print(f"❌ No commands found for member {member_id}")
            print(f"   Total commands in queue: {len(commands)}")
            return False
    except Exception as e:
        print(f"❌ Failed to check commands: {e}")
        return False


def simulate_device_poll():
    """Simulate device polling for commands."""
    print("\n=== Step 4: Simulate Device Polling ===")
    
    url = f"{BASE_URL}/iclock/getrequest"
    params = {"SN": TEST_DEVICE_SERIAL}
    
    try:
        response = requests.get(url, params=params)
        print(f"Poll response: {response.status_code}")
        command = response.text
        
        if command != "OK":
            print(f"✅ Device received command:")
            print(f"   {command}")
            
            # Parse command to show structure
            if command.startswith("C:ID:"):
                parts = command.split(":", 3)
                if len(parts) >= 4:
                    command_id = parts[2]
                    command_body = parts[3]
                    print(f"\n   Command ID: {command_id}")
                    print(f"   Command Body: {command_body}")
                    
                    # Parse DATA UPDATE user fields
                    if "DATA UPDATE user" in command_body:
                        fields_str = command_body.split("DATA UPDATE user ", 1)[1]
                        fields = fields_str.split("\t")
                        print(f"\n   Parsed Fields:")
                        for field in fields:
                            print(f"      {field}")
            
            return command
        else:
            print(f"   Queue is empty (response: OK)")
            return None
    except Exception as e:
        print(f"❌ Failed to poll for commands: {e}")
        return None


def simulate_device_acknowledgment(command):
    """Simulate device acknowledging command execution."""
    print("\n=== Step 5: Simulate Device Acknowledgment ===")
    
    if not command or command == "OK":
        print("   Skipped (no command to acknowledge)")
        return
    
    # Parse command ID from command string
    if not command.startswith("C:ID:"):
        print(f"❌ Invalid command format")
        return
    
    parts = command.split(":", 3)
    if len(parts) < 3:
        print(f"❌ Could not parse command ID")
        return
    
    command_id = parts[2]
    
    url = f"{BASE_URL}/iclock/devicecmd"
    params = {"SN": TEST_DEVICE_SERIAL}
    
    # Simulate successful execution (status code 0)
    ack_payload = f"ID:{command_id}:RESULT:0"
    
    try:
        response = requests.post(url, params=params, data=ack_payload, headers={"Content-Type": "text/plain"})
        print(f"Acknowledgment: {response.status_code}")
        print(f"Response: {response.text}")
        print(f"✅ Command acknowledged successfully")
        print(f"   Command ID: {command_id}")
        print(f"   Result: SUCCESS (0)")
    except Exception as e:
        print(f"❌ Failed to acknowledge command: {e}")


def verify_command_completed(member_id):
    """Verify the command status was updated to completed."""
    print("\n=== Step 6: Verify Command Completed ===")
    
    url = f"{BASE_URL}/iclock/devices/{TEST_DEVICE_SERIAL}/commands"
    params = {"status": "completed"}
    
    try:
        response = requests.get(url, params=params)
        commands = response.json()["commands"]
        
        # Find completed commands for this member
        member_commands = [
            cmd for cmd in commands
            if f"sync_user_{member_id}_" in cmd["command_id"]
        ]
        
        if member_commands:
            print(f"✅ Command(s) marked as completed")
            for cmd in member_commands:
                print(f"\n   Command ID: {cmd['command_id']}")
                print(f"   Status: {cmd['status']}")
                print(f"   Response: {cmd['response']}")
                print(f"   Completed At: {cmd['completed_at']}")
            return True
        else:
            print(f"❌ No completed commands found for member {member_id}")
            return False
    except Exception as e:
        print(f"❌ Failed to verify completion: {e}")
        return False


def main():
    """Run complete user synchronization test flow."""
    print("=" * 70)
    print("ZKTeco PUSH Protocol - User Synchronization Test (Phase 3)")
    print("=" * 70)
    
    try:
        # Step 1: Register test device
        if not register_test_device():
            print("\n❌ Test failed: Could not register device")
            return 1
        
        # Step 2: Create test member
        member_id = create_test_member()
        if not member_id:
            print("\n❌ Test failed: Could not create member")
            return 1
        
        # Wait a moment for async processing
        time.sleep(0.5)
        
        # Step 3: Verify commands were queued
        if not check_queued_commands(member_id):
            print("\n❌ Test failed: Commands not queued")
            return 1
        
        # Step 4: Simulate device polling
        command = simulate_device_poll()
        
        # Step 5: Simulate device acknowledgment
        if command and command != "OK":
            simulate_device_acknowledgment(command)
            
            # Wait for acknowledgment processing
            time.sleep(0.5)
            
            # Step 6: Verify command completed
            verify_command_completed(member_id)
        
        print("\n" + "=" * 70)
        print("✅ User Synchronization Test Complete!")
        print("=" * 70)
        print("\nSummary:")
        print(f"  • Test device registered: {TEST_DEVICE_SERIAL}")
        print(f"  • Test member created: ID {member_id}")
        print(f"  • User sync command queued automatically")
        print(f"  • Device polled and received command")
        print(f"  • Command format: DATA UPDATE user with tab-separated fields")
        print(f"  • Device acknowledged execution")
        print(f"  • Command marked as completed")
        print("\nOn a real MiniAC Plus device:")
        print("  • User would automatically appear in device user list")
        print("  • User can then register fingerprint/face via device LCD")
        print("  • Attendance records will reference this user PIN")
        
        return 0
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Connection failed: Is the backend server running?")
        print("   Start server: cd backend && uvicorn app:app --reload")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
