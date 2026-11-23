#!/usr/bin/env python3
"""Dynamic OSC terminal title script for Antigravity CLI (agy).

Pairs with Custom Termux's two-line session drawer (OSC title on primary line +
PRoot-penetrated live command on muted secondary line) so every active session
shows live busy/idle state (◐/◑ vs ✳) and conversation topic at a glance.
"""

import json
import sys
import time

IDLE_ICON = "\u2733"               # ✳
BUSY_ICONS = ("\u25d0", "\u25d1")  # ◐, ◑
BUSY_STATES = {"working", "tool_use", "initializing", "authenticating"}
DEFAULT_TITLE = "Antigravity"


def clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def format_title(data: dict) -> str:
    title = clean_text(data.get("conversation_title")) or DEFAULT_TITLE
    state = clean_text(data.get("agent_state")).lower()
    waiting = data.get("tool_confirmation_pending") is True or state == "reviewing"

    if state in BUSY_STATES and not waiting:
        icon = BUSY_ICONS[int(time.time() / 0.96) % len(BUSY_ICONS)]
    else:
        icon = IDLE_ICON

    return f"{icon} {title}"


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    sys.stdout.write(f"{format_title(data)}\n")


if __name__ == "__main__":
    main()
