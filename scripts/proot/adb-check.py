#!/usr/bin/env python3
"""Safe loopback ADB relay health check from inside a PRoot container.

Queries the host Termux ADB server at 127.0.0.1:5037 over raw TCP without
ever spawning or killing an adb daemon inside PRoot.
"""

import socket
import sys

ADB_HOST = "127.0.0.1"
ADB_PORT = 5037


def adb_query(command: str, timeout: float = 3.0) -> str:
    payload = f"{len(command):04x}{command}".encode("ascii")
    with socket.create_connection((ADB_HOST, ADB_PORT), timeout=timeout) as sock:
        sock.sendall(payload)
        status = sock.recv(4)
        if status != b"OKAY":
            rest = sock.recv(4096).decode("utf-8", errors="replace")
            raise RuntimeError(f"ADB server returned {status!r}: {rest}")
        length_hex = sock.recv(4)
        if len(length_hex) < 4:
            return ""
        expected = int(length_hex.decode("ascii"), 16)
        chunks = []
        received = 0
        while received < expected:
            chunk = sock.recv(min(4096, expected - received))
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")


def main() -> int:
    try:
        proto_hex = adb_query("host:version")
        proto_num = int(proto_hex, 16) if proto_hex else -1
        devices = adb_query("host:devices-l").strip()
    except OSError as exc:
        print(f"[FAIL] Cannot reach native Termux ADB server at {ADB_HOST}:{ADB_PORT}: {exc}")
        print("       Start/reconnect ADB in native Termux first (never run 'adb kill-server' inside PRoot).")
        return 1
    except Exception as exc:
        print(f"[FAIL] ADB protocol query failed: {exc}")
        return 1

    print(f"[OK]   Host ADB server reachable at {ADB_HOST}:{ADB_PORT} (protocol 1.0.{proto_num})")
    if not devices:
        print("[WARN] No devices attached. In native Termux run: adb connect 127.0.0.1:5555")
        return 2

    lines = [line for line in devices.splitlines() if line.strip()]
    print("[OK]   Attached devices:")
    for line in lines:
        print(f"       {line}")
    if len(lines) > 1:
        print("[TIP]  Multiple serials detected (e.g. emulator-5554 + 127.0.0.1:5555).")
        print("       Always pass '-s 127.0.0.1:5555' to adb commands.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
