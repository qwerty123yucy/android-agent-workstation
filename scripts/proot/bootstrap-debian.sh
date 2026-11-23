#!/usr/bin/env bash
# Bootstrap a PRoot Debian (13/Trixie ARM64) container for AI agents & closed-loop dev.
# Run INSIDE the PRoot Debian container.
# Options:
#   --with-headless   Also install chromium-headless-shell + CJK fonts for UI pre-checks
#   --with-apk-tools  Also install openjdk-21-jre-headless, ecj, aapt2, zipalign
set -euo pipefail

WITH_HEADLESS=0
WITH_APK_TOOLS=0
for arg in "$@"; do
    case "$arg" in
        --with-headless)  WITH_HEADLESS=1 ;;
        --with-apk-tools) WITH_APK_TOOLS=1 ;;
        -h|--help)
            echo "Usage: $0 [--with-headless] [--with-apk-tools]"
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown option: $arg" >&2
            exit 1
            ;;
    esac
done

echo "[1/4] Updating Debian packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

echo "[2/4] Installing core developer & agent tooling..."
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git curl wget ca-certificates gnupg \
    python3 python3-pip python3-venv \
    ripgrep fd-find bat jq tmux unzip zip \
    build-essential pkg-config gh adb

ln -sf /usr/bin/fdfind /usr/local/bin/fd
ln -sf /usr/bin/batcat /usr/local/bin/bat

if [ "$WITH_HEADLESS" -eq 1 ]; then
    echo "[3/4] Installing chromium-headless-shell + CJK font for GPU-less UI verification..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        chromium-headless-shell fonts-wqy-zenhei
else
    echo "[3/4] Skipping Headless Chromium (pass --with-headless to install)."
fi

if [ "$WITH_APK_TOOLS" -eq 1 ]; then
    echo "[4/4] Installing offline APK toolchain dependencies (JRE, ECJ, aapt2, zipalign)..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        openjdk-21-jre-headless ecj aapt2 zipalign
else
    echo "[4/4] Skipping offline APK dependencies (pass --with-apk-tools to install)."
fi

echo ""
echo "Bootstrap finished."
echo "Verify host ADB relay (if native Termux ADB is already connected):"
echo "  adb version && adb devices -l"
