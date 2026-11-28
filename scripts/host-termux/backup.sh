#!/data/data/com.termux/files/usr/bin/bash
# Zero-loss Termux + PRoot container backup script (run in native Termux, NOT inside PRoot).
# Optional env vars:
#   PROOT_DISTRO=debian
#   BACKUP_DIR=/sdcard/Download/termux-migration
#   TERMUX_APK=/path/to/custom-termux.apk
set -euo pipefail

DISTRO="${PROOT_DISTRO:-debian}"
OUT_DIR="${BACKUP_DIR:-/sdcard/Download/termux-migration}"
TERMUX_APK="${TERMUX_APK:-}"

echo "========================================================"
echo "  Termux + PRoot (${DISTRO}) Native Backup Script"
echo "========================================================"

if [ -z "${PREFIX:-}" ] || [ ! -d "${PREFIX}/var/lib/proot-distro" ]; then
    echo "[ERROR] Please exit PRoot/Agent sessions and run this script in native Termux."
    exit 1
fi

if ! command -v proot-distro >/dev/null 2>&1; then
    echo "[ERROR] proot-distro command not found."
    exit 1
fi

if [ -d "$PREFIX/var/lib/proot-distro/containers/${DISTRO}/rootfs" ]; then
    ROOTFS_DIR="$PREFIX/var/lib/proot-distro/containers/${DISTRO}/rootfs"
elif [ -d "$PREFIX/var/lib/proot-distro/installed-rootfs/${DISTRO}" ]; then
    ROOTFS_DIR="$PREFIX/var/lib/proot-distro/installed-rootfs/${DISTRO}"
else
    echo "[ERROR] PRoot container '${DISTRO}' not found."
    exit 1
fi

if pgrep -x proot >/dev/null 2>&1 || pgrep -x vroot >/dev/null 2>&1; then
    echo "[WARN] Active proot / vroot container processes detected!"
    echo "       Exit all container and Agent sessions first so SQLite WAL logs flush cleanly."
    read -r -p "Continue anyway? [y/N] " ans
    if [[ ! "${ans:-}" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Verify shared storage write access
if [ ! -d "$(dirname "$OUT_DIR")" ] || ! mkdir -p "$OUT_DIR" 2>/dev/null || ! touch "$OUT_DIR/.write_test" 2>/dev/null; then
    echo "[*] Requesting shared storage permission..."
    termux-setup-storage
    sleep 3
    mkdir -p "$OUT_DIR"
    if ! touch "$OUT_DIR/.write_test" 2>/dev/null; then
        echo "[ERROR] Cannot write to $OUT_DIR. Grant storage permission and retry."
        exit 1
    fi
fi
rm -f "$OUT_DIR/.write_test"
rm -rf "$OUT_DIR/custom-bin" "$OUT_DIR/${DISTRO}-proot.tar."*

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/5] Exporting restore.sh and optional Custom Termux APK..."
HAS_RESTORE=0
if [ -f "$SCRIPT_DIR/restore.sh" ]; then
    cp -f "$SCRIPT_DIR/restore.sh" "$OUT_DIR/restore.sh"
    HAS_RESTORE=1
fi

HAS_APK=0
if [ -n "$TERMUX_APK" ] && [ -f "$TERMUX_APK" ]; then
    cp -f "$TERMUX_APK" "$OUT_DIR/termux-custom-arm64-v8a.apk"
    HAS_APK=1
elif [ -f "$ROOTFS_DIR/root/migration/termux-custom-arm64-v8a.apk" ]; then
    cp -f "$ROOTFS_DIR/root/migration/termux-custom-arm64-v8a.apk" "$OUT_DIR/termux-custom-arm64-v8a.apk"
    HAS_APK=1
fi

echo "[2/5] Capturing user-created scripts in \$PREFIX/bin (skipping dpkg-owned binaries/symlinks)..."
STAGE_BIN="$(mktemp -d "${TMPDIR:-$PREFIX/tmp}/custom-bin.XXXXXX")"
trap 'rm -rf "$STAGE_BIN"' EXIT INT TERM

if command -v dpkg >/dev/null 2>&1; then
    dpkg --get-selections > "$OUT_DIR/outer-packages.txt" || true
    for f in "$PREFIX/bin"/*; do
        [ -f "$f" ] || continue
        [ -L "$f" ] && continue
        if ! dpkg -S "$f" >/dev/null 2>&1; then
            cp -pf "$f" "$STAGE_BIN/"
            echo "      Captured custom script: $(basename "$f")"
        fi
    done
fi
tar --numeric-owner -czpf "$OUT_DIR/custom-bin.tar.gz" -C "$STAGE_BIN" .
rm -rf "$STAGE_BIN"
trap - EXIT INT TERM

echo "[3/5] Archiving host Termux \$HOME (excluding ~/storage symlinks)..."
tar --numeric-owner --exclude='./storage' -czpf "$OUT_DIR/termux-home.tar.gz" -C "$HOME" .

echo "[4/5] Exporting PRoot '${DISTRO}' via native 'proot-distro backup'..."
if command -v zstd >/dev/null 2>&1; then
    proot-distro backup "$DISTRO" | zstd -1 -T0 -f - -o "$OUT_DIR/${DISTRO}-proot.tar.zst"
    ROOTFS_ARCHIVE="${DISTRO}-proot.tar.zst"
else
    proot-distro backup "$DISTRO" | gzip -1 > "$OUT_DIR/${DISTRO}-proot.tar.gz"
    ROOTFS_ARCHIVE="${DISTRO}-proot.tar.gz"
fi

echo "[5/5] Verifying archive integrity, entry count & SHA-256 checksums..."
gzip -t "$OUT_DIR/custom-bin.tar.gz"
gzip -t "$OUT_DIR/termux-home.tar.gz"

LIST_FILE="$(mktemp "${TMPDIR:-$PREFIX/tmp}/archive-list.XXXXXX")"
trap 'rm -f "$LIST_FILE"' EXIT INT TERM

if [ "$ROOTFS_ARCHIVE" = "${DISTRO}-proot.tar.zst" ]; then
    zstd -t "$OUT_DIR/$ROOTFS_ARCHIVE"
    zstd -dc "$OUT_DIR/$ROOTFS_ARCHIVE" | tar -tf - > "$LIST_FILE"
else
    gzip -t "$OUT_DIR/$ROOTFS_ARCHIVE"
    gzip -dc "$OUT_DIR/$ROOTFS_ARCHIVE" | tar -tf - > "$LIST_FILE"
fi

ENTRY_COUNT="$(wc -l < "$LIST_FILE" | tr -d ' ')"
echo "      Container archive entries: $ENTRY_COUNT"
if [ "$ENTRY_COUNT" -lt 5000 ]; then
    echo "[ERROR] Archive entry count looks unexpectedly low ($ENTRY_COUNT)!"
    exit 1
fi

for required_pat in \
    "${DISTRO}/.*usr/bin/env" \
    "${DISTRO}/.*root/\.bashrc"
do
    if ! grep -Eq "$required_pat" "$LIST_FILE"; then
        echo "[ERROR] Missing expected path in container archive: $required_pat"
        exit 1
    fi
done
rm -f "$LIST_FILE"
trap - EXIT INT TERM

SUM_TARGETS=("custom-bin.tar.gz" "termux-home.tar.gz" "$ROOTFS_ARCHIVE")
[ "$HAS_RESTORE" -eq 1 ] && SUM_TARGETS=("restore.sh" "${SUM_TARGETS[@]}")
[ "$HAS_APK" -eq 1 ] && SUM_TARGETS=("termux-custom-arm64-v8a.apk" "${SUM_TARGETS[@]}")

(
    cd "$OUT_DIR"
    sha256sum "${SUM_TARGETS[@]}" > SHA256SUMS.txt
)

echo ""
echo "========================================================"
echo "  Backup & SHA-256 verification passed!"
echo "  Output directory: $OUT_DIR"
ls -lh "$OUT_DIR"
echo "========================================================"
echo "Restore on a new/reinstalled Termux with:"
echo "  termux-setup-storage"
echo "  bash $OUT_DIR/restore.sh"
echo "========================================================"
