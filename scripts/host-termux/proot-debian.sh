#!/data/data/com.termux/files/usr/bin/bash
# Generic isolated PRoot Debian launcher with configurable timezone & UTF-8 locale.
# Install to: $PREFIX/bin/proot-debian  (chmod 700)
# Usage:
#   proot-debian
#   CONTAINER_TZ=Asia/Shanghai CONTAINER_LOCALE=en_US.UTF-8 proot-debian
set -euo pipefail

DISTRO="${PROOT_DISTRO:-debian}"
CONTAINER_TZ="${CONTAINER_TZ:-UTC}"
CONTAINER_LOCALE="${CONTAINER_LOCALE:-en_US.UTF-8}"
LOCALE_LANG="${CONTAINER_LOCALE%.*}"
LOCALE_SHORT="${LOCALE_LANG%%_*}"

exec proot-distro login "$DISTRO" --isolated -- \
  /usr/bin/env -i \
    HOME=/root \
    USER=root \
    LOGNAME=root \
    SHELL=/bin/bash \
    TERM="${TERM:-xterm-256color}" \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 \
    TZ="$CONTAINER_TZ" \
    TARGET_LOCALE="$CONTAINER_LOCALE" \
    TARGET_LANG="$LOCALE_LANG" \
    TARGET_SHORT="$LOCALE_SHORT" \
  /bin/bash --noprofile --norc -c '
    set -e
    LOCALE_PATTERN="^${TARGET_LANG}\\.utf-?8$"
    if ! locale -a 2>/dev/null | grep -Eqi "$LOCALE_PATTERN" || [ ! -f "/usr/share/zoneinfo/${TZ}" ]; then
      apt-get update
      DEBIAN_FRONTEND=noninteractive apt-get install -y locales tzdata
      localedef -i "$TARGET_LANG" -f UTF-8 "$TARGET_LOCALE"
    fi
    export LANG="$TARGET_LOCALE" LC_ALL="$TARGET_LOCALE" LANGUAGE="${TARGET_LANG}:${TARGET_SHORT}"
    ln -sf "/usr/share/zoneinfo/${TZ}" /etc/localtime
    printf "%s\n" "$TZ" > /etc/timezone
    exec /bin/bash -i
  '
