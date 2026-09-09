"""Queue ZKTeco device super-admin USERINFO (Pri=14) for gym owners.

App SUPER_ADMIN is unrelated to machine menu privilege. Member sync only ever
sends Pri=0/1, so an on-device admin set to a member PIN can be demoted on resync.

Uses reserved PINs outside the member/trainer ranges so future syncs won't overwrite.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from core.device_pins import DEVICE_PRIVILEGE_SUPER_ADMIN
from database import SessionLocal
from services.push_device_service import PushDeviceService, UserSyncCommand

# Reserved PINs: below trainer offset (50000), far above current member ids.
DEVICE_ADMINS = (
    {"pin": 99901, "name": "Amit Sharma", "password": "9999"},
    {"pin": 99902, "name": "Vishal", "password": "9999"},
)

TARGET_SERIAL = "TBS2254700504"


def main() -> None:
    db = SessionLocal()
    try:
        print("members 1-5:", list(db.execute(text(
            "SELECT id, full_name FROM members WHERE id <= 5 ORDER BY id"
        ))))
        print("max member id:", db.execute(text("SELECT MAX(id) FROM members")).scalar())
        print("admins:", [dict(r._mapping) for r in db.execute(text(
            "SELECT id, full_name, role FROM users WHERE role IN ('SUPER_ADMIN','ADMIN') ORDER BY id"
        ))])

        service = PushDeviceService(db)
        queued = []
        for index, admin in enumerate(DEVICE_ADMINS):
            command_id = service._next_command_id(member_id=admin["pin"], salt=9100 + index)
            command = UserSyncCommand.build_update_userinfo_command(
                command_id=command_id,
                pin=str(admin["pin"]),
                name=admin["name"],
                privilege=DEVICE_PRIVILEGE_SUPER_ADMIN,
                password=admin["password"],
            )
            row = service.queue_command(
                device_serial=TARGET_SERIAL,
                command_id=str(command_id),
                command=command,
                max_retries=3,
            )
            queued.append(
                {
                    "db_id": row.id,
                    "command_id": command_id,
                    "pin": admin["pin"],
                    "name": admin["name"],
                    "command": command,
                }
            )
            print("queued:", queued[-1])

        print(f"\nQueued {len(queued)} super-admin USERINFO command(s) for {TARGET_SERIAL}.")
        print("Device menu login: use PIN + password 9999 after the machine polls getrequest.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
