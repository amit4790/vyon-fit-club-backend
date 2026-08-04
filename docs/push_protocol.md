# ZKTeco PUSH Protocol Implementation

## Overview

This implementation provides support for ZKTeco devices using the official **PUSH (iClock/ADMS) protocol** over HTTP.

The PUSH protocol is the official communication method for modern ZKTeco devices that operate in "PUSH mode" or "ADMS mode", where the device initiates all communication with a server via HTTP requests.

## Architecture

### Communication Model

**Traditional (Standalone/TCP) vs PUSH Protocol:**

| Aspect | Standalone SDK (pyzk) | PUSH Protocol (This Implementation) |
|--------|----------------------|-------------------------------------|
| Communication | Server polls device via TCP | Device pushes data to server via HTTP |
| Initiator | Server | Device |
| Protocol | Proprietary binary | HTTP (GET/POST) |
| Compatibility | Older firmware | Modern firmware (Ver 1.0.27+) |
| Real-time | Requires constant polling | Device pushes immediately |

### Protocol Flow

1. **Device Registration/Heartbeat**
   - Device periodically calls `GET /iclock/cdata?SN={serial}`
   - Server registers device and updates last_seen timestamp

2. **Command Polling**
   - Device periodically calls `GET /iclock/getrequest?SN={serial}`
   - Server returns one pending command or "OK" if none exist
   - Command is marked as "executing"

3. **Command Acknowledgment**
   - Device executes command
   - Device posts result to `POST /iclock/devicecmd?SN={serial}`
   - Server updates command status (completed/failed)

4. **Attendance Upload**
   - Device captures attendance (check-in/check-out)
   - Device posts data to `POST /iclock/cdata?SN={serial}`
   - Server logs raw data for processing

## Endpoints

### GET /iclock/cdata

**Purpose:** Device heartbeat and registration

**Query Parameters:**
- `SN` (required): Device serial number
- `options`: Device capabilities (optional)
- `pushver`: Protocol version (optional)
- `FWVersion`: Firmware version (optional)
- `platform`: Device platform (optional)
- `DeviceType`: Device type (optional)

**Response:** `OK`

**Example:**
```http
GET /iclock/cdata?SN=ZAM230001234&pushver=2.0&FWVersion=Ver1.0.27 HTTP/1.1

Response:
OK
```

### GET /iclock/getrequest

**Purpose:** Command polling by device

**Query Parameters:**
- `SN` (required): Device serial number

**Response:**
- `OK` if no commands pending
- Command string if command exists: `C:ID:command_id:COMMAND_TYPE command_data`

**Example:**
```http
GET /iclock/getrequest?SN=ZAM230001234 HTTP/1.1

Response (no commands):
OK

Response (command pending):
C:ID:cmd_123:DATA UPDATE user pin=123	username=John Doe	privilege=0
```

### POST /iclock/devicecmd

**Purpose:** Command acknowledgment from device

**Query Parameters:**
- `SN` (required): Device serial number

**Request Body:**
```
ID:command_id:RESULT:status_code
```

Status codes:
- `0`: Success
- Non-zero: Error code

**Response:** `OK`

**Example:**
```http
POST /iclock/devicecmd?SN=ZAM230001234 HTTP/1.1
Content-Type: text/plain

ID:cmd_123:RESULT:0

Response:
OK
```

### POST /iclock/cdata

**Purpose:** Attendance data upload from device

**Query Parameters:**
- `SN` (required): Device serial number
- `table`: Data type (usually "ATTLOG")
- `Stamp`: Timestamp (optional)

**Request Body (ATTLOG format):**
```
ATTLOG:user_pin	timestamp	status	verify_mode	work_code	reserved
```

Fields:
- `user_pin`: User ID on device
- `timestamp`: `YYYY-MM-DD HH:MM:SS`
- `status`: `0`=check-in, `1`=check-out
- `verify_mode`: Verification method (1=fingerprint, 4=face, etc.)
- `work_code`: Work code/department
- `reserved`: Reserved field

**Response:** `OK`

**Example:**
```http
POST /iclock/cdata?SN=ZAM230001234&table=ATTLOG HTTP/1.1
Content-Type: text/plain

ATTLOG:123	2024-01-15 09:30:00	0	1	0	0
ATTLOG:456	2024-01-15 09:31:00	0	1	0	0

Response:
OK
```

## Database Schema

### push_devices

Tracks registered devices and connection status.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| serial_number | String(100) | Device serial number (unique) |
| device_name | String(200) | Device display name |
| platform | String(100) | Device platform (e.g., "ZAM230_TFT") |
| firmware_version | String(100) | Firmware version |
| device_type | String(50) | Device type (e.g., "T&A PUSH") |
| first_seen | DateTime | First registration timestamp |
| last_seen | DateTime | Last heartbeat timestamp |
| is_active | Boolean | Active status |
| registration_payload | String | Raw registration data |
| created_at | DateTime | Record creation timestamp |
| updated_at | DateTime | Record update timestamp |

### device_commands

Command queue for devices.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| command_id | String(100) | Unique command identifier |
| device_serial | String(100) | Target device serial |
| command | Text | Command string (iClock format) |
| status | Enum | pending/executing/completed/failed |
| response | Text | Device response |
| error_message | Text | Error message if failed |
| created_at | DateTime | Command creation timestamp |
| executed_at | DateTime | Execution start timestamp |
| completed_at | DateTime | Completion timestamp |
| retry_count | Integer | Retry attempt count |
| max_retries | Integer | Maximum retry attempts |

### device_attendance_logs

Raw attendance data uploads.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| device_serial | String(100) | Source device serial |
| raw_payload | Text | Complete raw ATTLOG data |
| content_type | String(100) | HTTP Content-Type |
| content_length | Integer | Payload size |
| is_processed | Boolean | Processing status |
| processed_at | DateTime | Processing timestamp |
| processing_error | Text | Processing error message |
| record_count | Integer | Number of ATTLOG records |
| uploaded_at | DateTime | Upload timestamp |
| created_at | DateTime | Record creation timestamp |

## Configuration

### Environment Variables

```bash
# Enable PUSH protocol support
DEVICE_PUSH_ENABLED=true

# Log complete raw payloads for debugging
DEVICE_PUSH_LOG_RAW=true
```

### Settings in `core/config.py`

```python
# ZKTeco PUSH Protocol settings
device_push_enabled: bool = True
device_push_log_raw: bool = True
```

## Usage

### Service Layer: PushDeviceService

The `PushDeviceService` class provides methods for:

**Device Management:**
```python
service = PushDeviceService(db)

# Register or update device
device = service.register_or_update_device(
    serial_number="ZAM230001234",
    device_info={"platform": "ZAM230_TFT", "firmware_version": "Ver1.0.27"}
)

# Get device
device = service.get_device("ZAM230001234")
```

**Command Queue:**
```python
# Queue a command
command = service.queue_command(
    device_serial="ZAM230001234",
    command_id="cmd_123",
    command="C:ID:cmd_123:DATA UPDATE user pin=123\tusername=John Doe"
)

# Get next pending command
command = service.get_pending_command("ZAM230001234")

# Acknowledge command
service.acknowledge_command(
    command_id="cmd_123",
    device_serial="ZAM230001234",
    response_data="ID:cmd_123:RESULT:0",
    success=True
)
```

**Attendance Logging:**
```python
# Log attendance upload
log = service.log_attendance_upload(
    device_serial="ZAM230001234",
    raw_payload="ATTLOG:123\t2024-01-15 09:30:00\t0\t1\t0\t0",
    content_type="text/plain",
    content_length=50
)
```

### Admin Endpoints

**List devices:**
```http
GET /iclock/devices
```

**List device commands:**
```http
GET /iclock/devices/{serial_number}/commands?status=pending
```

## User Synchronization (Future)

The `UserSyncCommand` interface provides command builders for user management:

```python
# Build user update command (future implementation)
command = UserSyncCommand.build_update_user_command(
    command_id="cmd_123",
    pin="123",
    username="John Doe",
    privilege=0
)
# Result: "C:ID:cmd_123:DATA UPDATE user pin=123	username=John Doe	privilege=0"

# Build user delete command (future implementation)
command = UserSyncCommand.build_delete_user_command(
    command_id="cmd_456",
    pin="123"
)
# Result: "C:ID:cmd_456:DATA DELETE user pin=123"
```

## Logging

All operations are logged with structured context:

```python
logger.info(
    "Device heartbeat: ZAM230001234",
    extra={
        "device_serial": "ZAM230001234",
        "last_seen": "2024-01-15T09:30:00",
        "endpoint": "GET /iclock/cdata"
    }
)
```

When `DEVICE_PUSH_LOG_RAW=true`, complete payloads are logged for debugging.

## Device Configuration

### Configure Device for PUSH Mode

1. **Access device web interface or LCD panel**
2. **Navigate to communication settings**
3. **Set communication mode to "PUSH" or "ADMS"**
4. **Configure server address:**
   - IP: Your backend server IP
   - Port: 8000 (or your FastAPI port)
   - Path: `/iclock/cdata`
5. **Save and restart device**

### Example Device Settings

```
Communication Mode: PUSH
Server IP: 192.168.31.100
Server Port: 8000
Upload Path: /iclock/cdata
Request Path: /iclock/getrequest
Command Path: /iclock/devicecmd
```

## Testing

### Verify Device Registration

```bash
# Check if device is registered
curl http://localhost:8000/iclock/devices

# Expected response:
{
  "devices": [
    {
      "id": 1,
      "serial_number": "ZAM230001234",
      "device_name": "Main Entrance",
      "platform": "ZAM230_TFT",
      "firmware_version": "Ver1.0.27",
      "last_seen": "2024-01-15T09:30:00"
    }
  ]
}
```

### Queue Test Command

```python
from services.push_device_service import PushDeviceService

service = PushDeviceService(db)
command = service.queue_command(
    device_serial="ZAM230001234",
    command_id="test_123",
    command="C:ID:test_123:INFO"
)
```

Device will receive command on next poll.

## Migration from pyzk

This implementation **coexists** with the existing pyzk/Standalone SDK implementation.

**Current state:**
- Legacy `DeviceService` using pyzk remains functional
- New `PushDeviceService` added for PUSH protocol
- Both can be used simultaneously

**Future cleanup (separate PR):**
- Remove pyzk dependency
- Remove legacy `DeviceService`
- Remove pyzk configuration
- Update all device integrations to use PUSH protocol

## Troubleshooting

### Device not connecting

1. Check device is in PUSH mode
2. Verify server IP/port in device settings
3. Check firewall allows inbound connections on port 8000
4. Check logs for device heartbeat: `grep "Device heartbeat" logs/app.log`

### Commands not executing

1. Check command format matches iClock protocol
2. Verify device is polling `/iclock/getrequest`
3. Check command status: `GET /iclock/devices/{serial}/commands`
4. Review device acknowledgment logs

### Attendance not uploading

1. Verify device has attendance records
2. Check device upload settings
3. Review raw payload logs when `DEVICE_PUSH_LOG_RAW=true`
4. Check database for `device_attendance_logs` entries

## References

- **ZKTeco PUSH SDK Documentation** (official protocol specification)
- **iClock Protocol Specification** (command format reference)
- **Device firmware documentation** (device-specific settings)

## Support Matrix

| Device Model | Firmware Version | Status |
|--------------|------------------|--------|
| MiniAC Plus | Ver1.0.27 | ✅ Tested |
| ZKTeco F18 | Ver1.0+ | ⚠️ Untested |
| ZKTeco K40 | Ver1.0+ | ⚠️ Untested |

Devices must support PUSH/ADMS communication mode.
