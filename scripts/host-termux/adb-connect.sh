#!/data/data/com.termux/files/usr/bin/bash
# Native Termux helper to pair/connect wireless ADB and pin port 5555 on loopback.
# Run in native Termux (NOT inside PRoot).
set -euo pipefail

if ! command -v adb >/dev/null 2>&1; then
    echo "[ERROR] adb not found. Run: pkg update && pkg upgrade -y && pkg install -y android-tools"
    exit 1
fi

echo "[*] Checking existing loopback ADB connection (127.0.0.1:5555)..."
if adb devices | grep -Eq '^127\.0\.0\.1:5555[[:space:]]+device$'; then
    echo "[OK] Already connected to 127.0.0.1:5555."
    adb devices -l
    exit 0
fi

if adb connect 127.0.0.1:5555 2>/dev/null | grep -qi "connected to 127.0.0.1:5555"; then
    if adb devices | grep -Eq '^127\.0\.0\.1:5555[[:space:]]+device$'; then
        echo "[OK] Reconnected to 127.0.0.1:5555."
        adb devices -l
        exit 0
    fi
fi

echo ""
echo "No active connection on 127.0.0.1:5555."
echo "Open Settings -> Developer Options -> Wireless Debugging (use split-screen for pairing)."
read -r -p "Need first-time wireless pairing? [y/N] " need_pair

if [[ "${need_pair:-}" =~ ^[Yy]$ ]]; then
    read -r -p "Enter pairing port shown on screen: " pair_port
    adb pair "127.0.0.1:${pair_port}"
fi

read -r -p "Enter Wireless Debugging connection port (main screen): " conn_port
adb connect "127.0.0.1:${conn_port}"

echo "[*] Pinning ADB TCP port to 5555..."
adb -s "127.0.0.1:${conn_port}" tcpip 5555
sleep 1
adb disconnect >/dev/null 2>&1 || true
adb connect 127.0.0.1:5555

echo ""
echo "[*] Active devices:"
adb devices -l
echo ""
echo "Tip: Inside PRoot, always target '-s 127.0.0.1:5555' and NEVER run 'adb kill-server'."
