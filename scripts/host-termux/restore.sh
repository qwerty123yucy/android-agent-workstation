#!/data/data/com.termux/files/usr/bin/bash
# Zero-loss Termux + PRoot container restore script (run in native Termux).
# Optional env vars:
#   PROOT_DISTRO=debian
#   BACKUP_DIR=/sdcard/Download/termux-migration
set -euo pipefail

DISTRO="${PROOT_DISTRO:-debian}"
IN_DIR="${BACKUP_DIR:-/sdcard/Download/termux-migration}"

echo "========================================================"
echo "  Termux + PRoot (${DISTRO}) Native Restore Script"
echo "========================================================"

if [ ! -d "$IN_DIR" ]; then
    echo "[*] Requesting shared storage permission..."
    termux-setup-storage
    sleep 3
fi

if [ ! -f "$IN_DIR/SHA256SUMS.txt" ]; then
    echo "[ERROR] $IN_DIR/SHA256SUMS.txt not found. Verify storage permission and backup path."
    exit 1
fi

echo "[1/5] Verifying SHA-256 checksums..."
(
    cd "$IN_DIR"
    sha256sum -c SHA256SUMS.txt
)

echo "[2/5] Updating repositories and installing host packages..."
pkg update -y
pkg upgrade -y
DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::="--force-confnew" \
    proot-distro tmux zstd android-tools python aapt2

echo "[3/5] Restoring host Termux \$HOME and custom \$PREFIX/bin scripts..."
tar --no-same-owner --delay-directory-restore -xzpf "$IN_DIR/termux-home.tar.gz" -C "$HOME"
if [ -f "$IN_DIR/custom-bin.tar.gz" ]; then
    tar --no-same-owner --skip-old-files -xzpf "$IN_DIR/custom-bin.tar.gz" -C "$PREFIX/bin"
    # Adapt hardcoded shebangs if restoring into a coexist package (e.g. non-com.termux PREFIX)
    if [ "$PREFIX" != "/data/data/com.termux/files/usr" ]; then
        while IFS= read -r entry; do
            name="${entry#./}"
            [ -n "$name" ] && [ -f "$PREFIX/bin/$name" ] || continue
            if head -n 1 "$PREFIX/bin/$name" | grep -q "/data/data/com.termux/files/usr"; then
                sed -i "s|/data/data/com.termux/files/usr|$PREFIX|g" "$PREFIX/bin/$name"
                chmod 700 "$PREFIX/bin/$name"
            fi
        done < <(tar -tzf "$IN_DIR/custom-bin.tar.gz")
    fi
fi

echo "[4/5] Restoring PRoot '${DISTRO}' container via 'proot-distro restore'..."
if [ -d "$PREFIX/var/lib/proot-distro/containers/${DISTRO}" ] || [ -d "$PREFIX/var/lib/proot-distro/installed-rootfs/${DISTRO}" ]; then
    proot-distro remove "$DISTRO" || true
fi

if [ -f "$IN_DIR/${DISTRO}-proot.tar.zst" ]; then
    zstd -dc "$IN_DIR/${DISTRO}-proot.tar.zst" | proot-distro restore
elif [ -f "$IN_DIR/${DISTRO}-proot.tar.gz" ]; then
    gzip -dc "$IN_DIR/${DISTRO}-proot.tar.gz" | proot-distro restore
else
    echo "[ERROR] Missing ${DISTRO}-proot.tar.{zst,gz} in $IN_DIR"
    exit 1
fi

echo "[5/5] Smoke-testing restored container..."
proot-distro login "$DISTRO" --isolated -- /bin/bash -lc '
    echo "  OS     : $(grep PRETTY_NAME /etc/os-release | cut -d= -f2-)"
    echo "  Time   : $(date)"
    echo "  Locale : LANG=${LANG:-unset} TZ=${TZ:-unset}"
'

echo ""
echo "========================================================"
echo "  Restore & verification complete!"
echo "  Run 'source ~/.bashrc' (or open a new Termux session) to begin."
echo "========================================================"
