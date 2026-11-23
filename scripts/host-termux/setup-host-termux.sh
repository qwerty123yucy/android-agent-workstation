#!/data/data/com.termux/files/usr/bin/bash
# Host Termux bootstrapper (run in native Termux, NOT inside PRoot).
set -euo pipefail

if [ -z "${PREFIX:-}" ] || [ ! -d "$PREFIX" ]; then
    echo "[ERROR] Please run this script in native Termux (not inside PRoot)."
    exit 1
fi

echo "[1/3] Updating & upgrading existing Termux packages (prevents libc++ ABI mismatch)..."
pkg update -y
pkg upgrade -y

echo "[2/3] Installing host packages (proot-distro, tmux, zstd, android-tools, python, aapt2)..."
pkg install -y proot-distro tmux zstd android-tools python aapt2

echo "[3/3] Verifying adb binary..."
adb version

echo ""
echo "Host Termux setup complete."
echo "Next steps:"
echo "  1. proot-distro install debian"
echo "  2. install -m 700 scripts/host-termux/proot-debian.sh \"\$PREFIX/bin/proot-debian\""
echo "  3. proot-debian"
