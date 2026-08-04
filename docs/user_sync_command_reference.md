# ZKTeco iClock Protocol - User Sync Command Reference

## Command Structure

### Full Command Format
```
C:ID:{command_id}:DATA UPDATE user {field1}={value1}\t{field2}={value2}\t...
```

### Example
```
C:ID:sync_user_123_DEVICE001_1234567890:DATA UPDATE user pin=123	username=John Doe	privilege=0	password=	card=12345
```

## Field Definitions

### Required Fields

#### `pin` (Required)
- **Type:** String (numeric)
- **Description:** User identifier on device (unique per device)
- **VYON Mapping:** `member.id`
- **Example:** `pin=123`
- **Notes:** Primary key for user on device, used in attendance logs

#### `username` (Required)
- **Type:** String
- **Description:** User display name shown on device LCD and reports
- **VYON Mapping:** `member.full_name`
- **Example:** `username=John Doe`
- **Max Length:** 24 characters (device-dependent)
- **Notes:** Visible in device menus and attendance reports

#### `privilege` (Required)
- **Type:** Integer
- **Description:** User privilege level on device
- **VYON Mapping:** Fixed `0` for all members
- **Example:** `privilege=0`
- **Values:**
  - `0` = Normal user (default for members)
  - `14` = Administrator (for device management)
- **Notes:** Members always get privilege=0

#### `password` (Optional but included)
- **Type:** String
- **Description:** User password for device login
- **VYON Mapping:** Empty string `""`
- **Example:** `password=`
- **Notes:** Blank for normal users, device uses biometric/card instead

#### `card` (Optional but included)
- **Type:** String (numeric)
- **Description:** RFID card number for card-based access
- **VYON Mapping:** `member.device_card` if available
- **Example:** `card=12345` or `card=`
- **Notes:** Required only if using card readers

## Command Generation

### Python Implementation

```python
from services.push_device_service import UserSyncCommand

# Generate command
command = UserSyncCommand.build_update_user_command(
    command_id="sync_user_123_DEVICE001_1234567890",
    pin="123",
    username="John Doe",
    privilege=0,
    password="",
    card="12345"
)

# Result:
# C:ID:sync_user_123_DEVICE001_1234567890:DATA UPDATE user pin=123	username=John Doe	privilege=0	password=	card=12345
```

### Command ID Format

```
sync_user_{member_id}_{device_serial}_{timestamp}
```

**Components:**
- `sync_user_` - Prefix indicating user sync operation
- `{member_id}` - VYON member ID (e.g., `123`)
- `{device_serial}` - Target device serial (e.g., `DEVICE001`)
- `{timestamp}` - Unix timestamp for uniqueness (e.g., `1234567890`)

**Example:** `sync_user_123_DEVICE001_1234567890`

## Device Response

### Success Response

When device successfully creates/updates user:

```
ID:{command_id}:RESULT:0
```

**Example:**
```
ID:sync_user_123_DEVICE001_1234567890:RESULT:0
```

### Error Response

When device fails to process command:

```
ID:{command_id}:RESULT:{error_code}
```

**Common Error Codes:**
- `1` - Invalid command format
- `2` - Duplicate PIN (should not happen with UPDATE)
- `3` - Device storage full
- `4` - Invalid privilege level
- `5` - Field validation error

## Protocol Flow

### Complete Synchronization Sequence

```
┌─────────────┐                  ┌──────────────┐                  ┌────────────┐
│   Backend   │                  │   Database   │                  │   Device   │
└──────┬──────┘                  └──────┬───────┘                  └─────┬──────┘
       │                                │                                 │
       │ 1. Create Member               │                                 │
       ├───────────────────────────────>│                                 │
       │                                │                                 │
       │ 2. Queue DeviceCommand         │                                 │
       ├───────────────────────────────>│                                 │
       │    (status=pending)            │                                 │
       │                                │                                 │
       │                                │ 3. Poll for Commands            │
       │                                │<────────────────────────────────┤
       │                                │                                 │
       │ 4. Get Pending Command         │                                 │
       │<───────────────────────────────┤                                 │
       │    (status → executing)        │                                 │
       │                                │                                 │
       │ 5. Return Command              │                                 │
       ├────────────────────────────────────────────────────────────────>│
       │    C:ID:cmd:DATA UPDATE user...│                                 │
       │                                │                                 │
       │                                │ 6. Create User Locally          │
       │                                │                    ┌────────────┤
       │                                │                    │            │
       │                                │                    └───────────>│
       │                                │                                 │
       │                                │ 7. Acknowledge Success          │
       │<────────────────────────────────────────────────────────────────┤
       │    ID:cmd:RESULT:0             │                                 │
       │                                │                                 │
       │ 8. Update Command              │                                 │
       ├───────────────────────────────>│                                 │
       │    (status → completed)        │                                 │
       │                                │                                 │
```

## Field Separator

**CRITICAL:** Fields MUST be separated by TAB character (`\t`, ASCII 9)

### Incorrect (spaces):
```
DATA UPDATE user pin=123 username=John Doe privilege=0
```
❌ Device will not parse correctly

### Correct (tabs):
```
DATA UPDATE user pin=123	username=John Doe	privilege=0
```
✅ Device parses successfully

### Python Implementation:
```python
# Use chr(9) or \t for tabs
fields = ["pin=123", "username=John Doe", "privilege=0"]
command_body = chr(9).join(fields)  # or "\t".join(fields)
```

## Testing Commands

### Manual Command Test

**1. Register test device:**
```bash
curl "http://localhost:8000/iclock/cdata?SN=TEST001"
```

**2. Queue manual command:**
```python
from services.push_device_service import PushDeviceService, UserSyncCommand
from database import SessionLocal

db = SessionLocal()
service = PushDeviceService(db)

command = UserSyncCommand.build_update_user_command(
    command_id="manual_test_001",
    pin="999",
    username="Test User",
    privilege=0,
    password="",
    card=""
)

service.queue_command(
    device_serial="TEST001",
    command_id="manual_test_001",
    command=command
)
```

**3. Device polls:**
```bash
curl "http://localhost:8000/iclock/getrequest?SN=TEST001"
```

**4. Verify command format:**
```
C:ID:manual_test_001:DATA UPDATE user pin=999	username=Test User	privilege=0	password=	card=
```

## Troubleshooting

### Command Not Received by Device

**Check:**
1. Device is active: `SELECT * FROM push_devices WHERE serial_number='XXX'`
2. Command is pending: `SELECT * FROM device_commands WHERE status='pending'`
3. Device is polling: Check logs for `GET /iclock/getrequest`
4. Command format correct: Verify tabs not spaces

### Device Returns Error

**Check:**
1. PIN is numeric
2. Username within length limit
3. Privilege is 0 or 14
4. Tab separators used (not spaces)
5. Device has available storage

### User Not Appearing on Device

**Verify:**
1. Command status is completed: `SELECT * FROM device_commands WHERE command_id='XXX'`
2. Device acknowledged with RESULT:0
3. Device LCD menu shows user list
4. Device firmware supports user management

## References

- **ZKTeco PUSH SDK Documentation** - Official protocol specification
- **iClock Protocol Guide** - Command format reference
- **VYON Implementation:** [push_device_service.py](../services/push_device_service.py)
- **Phase 3 Documentation:** [PUSH_PHASE3_USER_SYNC.md](PUSH_PHASE3_USER_SYNC.md)

## Quick Reference Card

| Aspect | Value |
|--------|-------|
| **Protocol** | iClock PUSH |
| **Command Type** | `C:ID:cmd_id:DATA UPDATE user` |
| **Field Separator** | TAB (`\t`, ASCII 9) |
| **Required Fields** | pin, username, privilege |
| **Success Response** | `ID:cmd_id:RESULT:0` |
| **Default Privilege** | `0` (normal user) |
| **PIN Source** | `member.id` from VYON |
| **Username Source** | `member.full_name` from VYON |
| **Card Source** | `member.device_card` from VYON |
