#!/usr/bin/env python3
"""Restricted local HTTP bridge for exposing a single whitelisted Android package
over 127.0.0.1 from native Termux into an --isolated PRoot container.

Security guards:
  1. Binds strictly to 127.0.0.1.
  2. Requires constant-time X-Bridge-Token authentication on every route.
  3. Verifies APK package name via `aapt2 dump badging` before installing.
  4. Checks foreground window via `dumpsys window` before screenshot/ui-tree/input.

Usage (native Termux):
  export ALLOWED_PKG="com.example.myapp"
  export BRIDGE_TOKEN="$(head -c 24 /dev/urandom | base64)"
  export ADB_SERIAL="127.0.0.1:5555"
  python3 adb_bridge.py
"""

import hmac
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

ALLOWED_PKG = os.environ.get("ALLOWED_PKG", "").strip()
BRIDGE_TOKEN = os.environ.get("BRIDGE_TOKEN", "").strip()
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "18765"))
ADB_SERIAL = os.environ.get("ADB_SERIAL", "127.0.0.1:5555").strip()
MAX_APK_BYTES = 200 * 1024 * 1024  # 200 MB

PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
ACTIVITY_RE = re.compile(r"^[A-Za-z0-9_.$]+$")
FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s+u\d+\s+([A-Za-z0-9_.]+)(?:/[^}\s]+)?\}")
AAPT_PKG_RE = re.compile(r"package:\s+name='([^']+)'")
LOG_PID_RE = re.compile(r"^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+(\d+)\s+\d+\s+")

SAFE_KEYS = {
    "KEYCODE_BACK",
    "KEYCODE_ENTER",
    "KEYCODE_DEL",
    "KEYCODE_TAB",
    "KEYCODE_ESCAPE",
    "KEYCODE_DPAD_UP",
    "KEYCODE_DPAD_DOWN",
    "KEYCODE_DPAD_LEFT",
    "KEYCODE_DPAD_RIGHT",
    "KEYCODE_DPAD_CENTER",
}


def adb_cmd(*args: str) -> list[str]:
    base = ["adb"]
    if ADB_SERIAL:
        base += ["-s", ADB_SERIAL]
    return base + list(args)


def run_cmd(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def get_foreground_pkg() -> str | None:
    for subcmd in (("dumpsys", "window", "displays"), ("dumpsys", "window")):
        res = run_cmd(adb_cmd("shell", *subcmd), timeout=10)
        text = res.stdout.decode("utf-8", errors="replace")
        m = FOCUS_RE.search(text)
        if m:
            return m.group(1)
        if "mCurrentFocus=" in text:
            return None
    return None


def get_apk_pkg(apk_path: str) -> str | None:
    res = run_cmd(["aapt2", "dump", "badging", apk_path], timeout=30)
    if res.returncode != 0:
        return None
    m = AAPT_PKG_RE.search(res.stdout.decode("utf-8", errors="replace"))
    return m.group(1) if m else None


def get_filtered_logs(lines: int) -> str:
    chunks: list[str] = []

    pid_res = run_cmd(adb_cmd("shell", "pidof", ALLOWED_PKG), timeout=10)
    pids = [p for p in pid_res.stdout.decode("utf-8", errors="replace").split() if p.isdigit()]
    for pid in pids:
        r = run_cmd(adb_cmd("logcat", "-d", f"--pid={pid}", "-t", str(lines)), timeout=15)
        out = r.stdout.decode("utf-8", errors="replace").strip()
        if out:
            chunks.append(f"=== live pid {pid} ===\n{out}")

    crash_res = run_cmd(adb_cmd("logcat", "-d", "-b", "crash", "-t", str(max(lines, 200))), timeout=15)
    crash_lines = crash_res.stdout.decode("utf-8", errors="replace").splitlines()
    crash_pids: set[str] = set()
    for line in crash_lines:
        if (
            f"Process: {ALLOWED_PKG}," in line
            or f"Process: {ALLOWED_PKG} " in line
            or f">>> {ALLOWED_PKG} <<<" in line
        ):
            m = LOG_PID_RE.match(line)
            if m:
                crash_pids.add(m.group(1))
    if crash_pids:
        matched = []
        for line in crash_lines:
            m = LOG_PID_RE.match(line)
            if m and m.group(1) in crash_pids:
                matched.append(line)
        if matched:
            chunks.append("=== crash buffer ===\n" + "\n".join(matched[-lines:]))

    return "\n\n".join(chunks)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"[bridge] {self.address_string()} - {fmt % args}\n")

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, code: int, content_type: str, data: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _check_auth(self) -> bool:
        token = self.headers.get("X-Bridge-Token", "")
        if not hmac.compare_digest(token, BRIDGE_TOKEN):
            self._send_json(401, {"error": "unauthorized"})
            return False
        return True

    def _require_foreground(self) -> bool:
        fg = get_foreground_pkg()
        if fg != ALLOWED_PKG:
            self._send_json(
                403,
                {
                    "error": "target_not_in_foreground",
                    "allowed_pkg": ALLOWED_PKG,
                    "foreground_pkg": fg,
                },
            )
            return False
        return True

    def _read_body(self, max_bytes: int) -> bytes | None:
        raw_len = self.headers.get("Content-Length", "0")
        if not raw_len.isdigit():
            self._send_json(400, {"error": "invalid Content-Length"})
            return None
        length = int(raw_len)
        if length > max_bytes:
            self._send_json(413, {"error": f"body too large (max {max_bytes} bytes)"})
            return None
        return self.rfile.read(length) if length > 0 else b""

    def do_GET(self) -> None:
        if not self._check_auth():
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                state = run_cmd(adb_cmd("get-state"), timeout=5)
                self._send_json(
                    200,
                    {
                        "ok": state.returncode == 0,
                        "adb_state": state.stdout.decode().strip() or state.stderr.decode().strip(),
                        "adb_serial": ADB_SERIAL,
                        "allowed_pkg": ALLOWED_PKG,
                        "foreground_pkg": get_foreground_pkg(),
                    },
                )
            elif parsed.path == "/screenshot":
                if not self._require_foreground():
                    return
                res = run_cmd(adb_cmd("exec-out", "screencap", "-p"), timeout=20)
                if res.returncode != 0 or not res.stdout.startswith(b"\x89PNG"):
                    self._send_json(500, {"error": "screencap failed", "stderr": res.stderr.decode(errors="replace")})
                    return
                self._send_bytes(200, "image/png", res.stdout)
            elif parsed.path == "/ui-tree":
                if not self._require_foreground():
                    return
                dump = run_cmd(adb_cmd("shell", "uiautomator", "dump", "/data/local/tmp/agent_ui.xml"), timeout=25)
                if dump.returncode != 0:
                    self._send_json(
                        500,
                        {
                            "error": "uiautomator dump failed",
                            "stdout": dump.stdout.decode(errors="replace"),
                            "stderr": dump.stderr.decode(errors="replace"),
                        },
                    )
                    return
                cat = run_cmd(adb_cmd("exec-out", "cat", "/data/local/tmp/agent_ui.xml"), timeout=15)
                run_cmd(adb_cmd("shell", "rm", "-f", "/data/local/tmp/agent_ui.xml"), timeout=10)
                if cat.returncode != 0:
                    self._send_json(500, {"error": "read ui xml failed", "stderr": cat.stderr.decode(errors="replace")})
                    return
                self._send_bytes(200, "application/xml; charset=utf-8", cat.stdout)
            elif parsed.path == "/logcat":
                qs = parse_qs(parsed.query)
                try:
                    lines = max(1, min(1000, int(qs.get("lines", ["200"])[0])))
                except ValueError:
                    lines = 200
                text = get_filtered_logs(lines)
                self._send_bytes(200, "text/plain; charset=utf-8", text.encode("utf-8"))
            else:
                self._send_json(404, {"error": "not found"})
        except subprocess.TimeoutExpired:
            self._send_json(504, {"error": "adb command timed out"})
        except FileNotFoundError as e:
            self._send_json(500, {"error": f"missing binary in Termux: {e}"})

    def do_POST(self) -> None:
        if not self._check_auth():
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/install":
                data = self._read_body(MAX_APK_BYTES)
                if data is None:
                    return
                if not data:
                    self._send_json(400, {"error": "empty APK body"})
                    return
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".apk", delete=False) as f:
                        f.write(data)
                        tmp_path = f.name
                    pkg = get_apk_pkg(tmp_path)
                    if pkg != ALLOWED_PKG:
                        self._send_json(
                            403,
                            {"error": "apk_package_mismatch", "allowed_pkg": ALLOWED_PKG, "apk_pkg": pkg},
                        )
                        return
                    res = run_cmd(adb_cmd("install", "-r", "-t", tmp_path), timeout=120)
                    self._send_json(
                        200 if res.returncode == 0 else 500,
                        {
                            "ok": res.returncode == 0,
                            "stdout": res.stdout.decode(errors="replace").strip(),
                            "stderr": res.stderr.decode(errors="replace").strip(),
                        },
                    )
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)

            elif parsed.path == "/launch":
                raw = self._read_body(16 * 1024)
                if raw is None:
                    return
                body = json.loads(raw.decode("utf-8")) if raw else {}
                if body.get("clear_data"):
                    run_cmd(adb_cmd("shell", "pm", "clear", ALLOWED_PKG), timeout=15)
                activity = body.get("activity")
                if activity:
                    if not isinstance(activity, str) or not ACTIVITY_RE.match(activity):
                        self._send_json(400, {"error": "invalid activity name"})
                        return
                    res = run_cmd(adb_cmd("shell", "am", "start", "-W", "-n", f"{ALLOWED_PKG}/{activity}"), timeout=20)
                else:
                    res = run_cmd(
                        adb_cmd("shell", "monkey", "-p", ALLOWED_PKG, "-c", "android.intent.category.LAUNCHER", "1"),
                        timeout=20,
                    )
                self._send_json(
                    200 if res.returncode == 0 else 500,
                    {
                        "ok": res.returncode == 0,
                        "stdout": res.stdout.decode(errors="replace").strip(),
                        "stderr": res.stderr.decode(errors="replace").strip(),
                    },
                )

            elif parsed.path == "/stop":
                res = run_cmd(adb_cmd("shell", "am", "force-stop", ALLOWED_PKG), timeout=15)
                self._send_json(200 if res.returncode == 0 else 500, {"ok": res.returncode == 0})

            elif parsed.path == "/input":
                if not self._require_foreground():
                    return
                raw = self._read_body(16 * 1024)
                if raw is None:
                    return
                body = json.loads(raw.decode("utf-8")) if raw else {}
                action = body.get("action")
                if action == "tap":
                    x, y = int(body["x"]), int(body["y"])
                    cmd = adb_cmd("shell", "input", "tap", str(x), str(y))
                elif action == "swipe":
                    x1, y1 = int(body["x1"]), int(body["y1"])
                    x2, y2 = int(body["x2"]), int(body["y2"])
                    dur = max(50, min(3000, int(body.get("duration_ms", 300))))
                    cmd = adb_cmd("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur))
                elif action == "key":
                    code = str(body.get("code", ""))
                    if code not in SAFE_KEYS:
                        self._send_json(400, {"error": "disallowed keycode", "allowed": sorted(SAFE_KEYS)})
                        return
                    cmd = adb_cmd("shell", "input", "keyevent", code)
                elif action == "text":
                    text = str(body.get("text", ""))
                    if not text or len(text) > 500 or not all(32 <= ord(c) <= 126 for c in text):
                        self._send_json(400, {"error": "text must be 1..500 printable ASCII chars"})
                        return
                    safe_arg = shlex.quote(text.replace(" ", "%s"))
                    cmd = adb_cmd("shell", "input", "text", safe_arg)
                else:
                    self._send_json(400, {"error": "unsupported action (tap|swipe|key|text)"})
                    return
                res = run_cmd(cmd, timeout=15)
                self._send_json(
                    200 if res.returncode == 0 else 500,
                    {"ok": res.returncode == 0, "stderr": res.stderr.decode(errors="replace").strip()},
                )
            else:
                self._send_json(404, {"error": "not found"})
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            self._send_json(400, {"error": f"bad request: {e}"})
        except subprocess.TimeoutExpired:
            self._send_json(504, {"error": "adb command timed out"})
        except FileNotFoundError as e:
            self._send_json(500, {"error": f"missing binary in Termux: {e}"})


def main() -> None:
    if not PKG_RE.match(ALLOWED_PKG):
        sys.exit("ERROR: Set a valid ALLOWED_PKG env var, e.g. export ALLOWED_PKG=com.example.myapp")
    if len(BRIDGE_TOKEN) < 12:
        sys.exit("ERROR: Set BRIDGE_TOKEN env var with at least 12 characters")

    server = HTTPServer(("127.0.0.1", BRIDGE_PORT), Handler)
    print(
        f"ADB Bridge listening on http://127.0.0.1:{BRIDGE_PORT} "
        f"(allowed_pkg={ALLOWED_PKG}, serial={ADB_SERIAL or 'default'})",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
