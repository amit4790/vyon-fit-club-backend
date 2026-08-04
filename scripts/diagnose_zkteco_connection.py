"""Deep diagnostic matrix for pyzk connection behavior against the configured device."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import traceback
from typing import Callable

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from zk import ZK  # noqa: E402


@dataclass
class Attempt:
    name: str
    force_udp: bool
    ommit_ping: bool
    encoding: str
    force_tcp_path: bool = False
    map_6001_to_unauth: bool = False


def run_attempt(attempt: Attempt, base_key: int, timeout: int) -> None:
    print("\n" + "=" * 88)
    print(f"Attempt: {attempt.name}")
    print(
        f"host={settings.zkteco_device_host} port={settings.zkteco_device_port} "
        f"password={base_key} timeout={timeout} force_udp={attempt.force_udp} "
        f"ommit_ping={attempt.ommit_ping} encoding={attempt.encoding} "
        f"force_tcp_path={attempt.force_tcp_path} map_6001_to_unauth={attempt.map_6001_to_unauth}"
    )

    original_ack_unauth = None
    if attempt.map_6001_to_unauth:
        from zk import const

        original_ack_unauth = const.CMD_ACK_UNAUTH
        const.CMD_ACK_UNAUTH = 6001

    zk = ZK(
        settings.zkteco_device_host,
        port=settings.zkteco_device_port,
        timeout=timeout,
        password=base_key,
        force_udp=attempt.force_udp,
        ommit_ping=attempt.ommit_ping,
        verbose=True,
        encoding=attempt.encoding,
    )

    # pyzk connect() may silently switch to UDP when helper.test_tcp()!=0.
    # For diagnosis we can force the TCP branch so we know if that path works.
    if attempt.force_tcp_path:
        zk.helper.test_tcp = (lambda: 0)  # type: ignore[method-assign]

    try:
        test_tcp_result = zk.helper.test_tcp()
    except Exception as exc:
        test_tcp_result = f"ERROR:{exc.__class__.__name__}:{exc}"

    try:
        test_udp_result = zk.helper.test_udp()
    except Exception as exc:
        test_udp_result = f"ERROR:{exc.__class__.__name__}:{exc}"

    print(f"helper.test_tcp() => {test_tcp_result}")
    print(f"helper.test_udp() => {test_udp_result}")

    conn = None
    try:
        conn = zk.connect()
        print("CONNECT: SUCCESS")
        try:
            serial = conn.get_serialnumber()
        except Exception as exc:
            serial = f"ERROR:{exc.__class__.__name__}:{exc}"
        try:
            device_name = conn.get_device_name()
        except Exception as exc:
            device_name = f"ERROR:{exc.__class__.__name__}:{exc}"
        print(f"device_name={device_name}")
        print(f"serial_number={serial}")
        try:
            users = conn.get_users()
            print(f"get_users: SUCCESS ({len(users)} users)")
        except Exception as exc:
            print(f"get_users: ERROR {exc.__class__.__name__}: {exc}")
            traceback.print_exc()
    except Exception as exc:
        print(f"CONNECT: ERROR {exc.__class__.__name__}: {exc}")
        traceback.print_exc()
    finally:
        if attempt.map_6001_to_unauth and original_ack_unauth is not None:
            from zk import const

            const.CMD_ACK_UNAUTH = original_ack_unauth
        if conn is not None:
            try:
                conn.disconnect()
                print("disconnect: SUCCESS")
            except Exception as exc:
                print(f"disconnect: ERROR {exc.__class__.__name__}: {exc}")


def main() -> int:
    key = int(settings.zkteco_communication_key)
    timeout = int(settings.zkteco_timeout_seconds)

    attempts: list[Attempt] = [
        Attempt(name="Default TCP preference", force_udp=False, ommit_ping=True, encoding=settings.zkteco_encoding),
        Attempt(name="Force UDP", force_udp=True, ommit_ping=True, encoding=settings.zkteco_encoding),
        Attempt(name="TCP with ping pre-check", force_udp=False, ommit_ping=False, encoding=settings.zkteco_encoding),
        Attempt(name="Force TCP branch in pyzk", force_udp=False, ommit_ping=True, encoding=settings.zkteco_encoding, force_tcp_path=True),
        Attempt(name="Force TCP branch + GBK", force_udp=False, ommit_ping=True, encoding="gbk", force_tcp_path=True),
        Attempt(
            name="Force TCP + map 6001 to unauth",
            force_udp=False,
            ommit_ping=True,
            encoding=settings.zkteco_encoding,
            force_tcp_path=True,
            map_6001_to_unauth=True,
        ),
    ]

    print("ZKTeco deep diagnostic matrix")
    print(f"Configured device: {settings.zkteco_device_host}:{settings.zkteco_device_port}")
    print(f"Configured communication key: {key}")

    for attempt in attempts:
        run_attempt(attempt, base_key=key, timeout=timeout)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
