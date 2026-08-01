"""Manual probe for the configured ZKTeco device connection and user list."""

from pathlib import Path
import sys


sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.device_service import (  # noqa: E402
    DeviceConnectionError,
    DeviceDependencyError,
    DeviceOperationError,
    DeviceService,
)


def main() -> int:
    service = DeviceService()

    try:
        service.connect()
        users = service.get_users()
        print(
            f"Connected to ZKTeco device at {service.settings.zkteco_device_host}:"
            f"{service.settings.zkteco_device_port} (device_id={service.settings.zkteco_device_id})"
        )
        print(f"User count: {len(users)}")
        for user in users[:10]:
            print(
                f"uid={user.uid} user_id={user.user_id} name={user.name!r} "
                f"privilege={user.privilege} enabled={user.enabled}"
            )
        if len(users) > 10:
            print(f"... {len(users) - 10} more users not shown")
        return 0
    except (DeviceDependencyError, DeviceConnectionError, DeviceOperationError) as exc:
        print(f"ZKTeco probe failed: {exc}")
        return 1
    finally:
        try:
            service.disconnect()
        except DeviceOperationError as exc:
            print(f"ZKTeco disconnect warning: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())