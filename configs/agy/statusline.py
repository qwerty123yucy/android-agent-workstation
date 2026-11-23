#!/usr/bin/env python3
"""Minimal, restrained mobile-friendly status line for Antigravity CLI (agy).

Displays execution mode + running subagents on the left, and concise model +
effort level right-aligned to fit narrow mobile terminal widths cleanly.
"""

import json
import os
import re
import sys

RESET = "\033[0m"
DIM = "\033[2m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"

VENDORS = {"gemini", "claude", "google", "anthropic"}
EFFORTS = {"minimal", "low", "medium", "high", "max", "xhigh"}
VIM_MODES = {"normal", "insert", "visual", "replace", "command"}
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def visible_len(text: str) -> int:
    return len(ANSI_RE.sub("", text))


def get_terminal_width(data: dict) -> int:
    for key in ("terminal_width", "columns", "cols"):
        val = data.get(key)
        if isinstance(val, (int, float)) and int(val) > 20:
            return int(val)

    env_cols = os.environ.get("COLUMNS", "")
    if env_cols.isdigit() and int(env_cols) > 20:
        return int(env_cols)

    try:
        fd = os.open("/dev/tty", os.O_RDONLY)
        try:
            cols = os.get_terminal_size(fd).columns
            if cols > 20:
                return cols
        finally:
            os.close(fd)
    except Exception:
        pass

    return 80


def resolve_mode(data: dict) -> str:
    for key in ("cycle_mode", "mode", "agent_mode", "agentMode", "permission_mode", "execution_mode"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            cand = val.strip().lower()
            if cand not in VIM_MODES:
                return cand

    for parent in ("agent", "permissions", "session"):
        sub = data.get(parent)
        if isinstance(sub, dict):
            for key in ("cycle_mode", "mode", "agent_mode", "agentMode"):
                val = sub.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip().lower()

    return "default"


def parse_model_and_effort(model: dict) -> tuple[str, str]:
    raw_name = (model.get("display_name") or model.get("id") or "").strip()
    raw_id = (model.get("id") or "").strip()
    effort = (model.get("effort") or "").strip().lower()

    m = re.search(r"\(([^)]+)\)\s*$", raw_name)
    if m and not effort:
        cand = m.group(1).strip().lower()
        if cand in EFFORTS:
            effort = cand

    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", raw_name)
    if "-" in cleaned and " " not in cleaned:
        cleaned = cleaned.replace("-", " ")

    tokens = cleaned.split()
    while len(tokens) > 1 and tokens[-1].lower() in EFFORTS:
        popped = tokens.pop().lower()
        if not effort:
            effort = popped

    if not effort and raw_id:
        id_parts = re.sub(r"\s*\([^)]*\)\s*$", "", raw_id).replace("-", " ").split()
        if id_parts and id_parts[-1].lower() in EFFORTS:
            effort = id_parts[-1].lower()

    kept = [
        t for t in tokens
        if t.lower() not in VENDORS and not re.fullmatch(r"v?\d+(?:\.\d+)*", t.lower())
    ]
    short_name = " ".join(kept).lower() if kept else cleaned.lower()
    return short_name, effort


def format_mode(mode: str) -> str:
    norm = mode.replace("_", "-")
    if norm in {"accept-edits", "acceptedits"}:
        return f"{MAGENTA}▸▸ accept edits{RESET}"
    if norm in {"auto", "autopilot"}:
        return f"{YELLOW}▸▸ auto{RESET}"
    if norm == "plan":
        return f"{CYAN}plan{RESET}"
    return f"{DIM}default{RESET}"


def format_right(short_name: str, effort: str) -> str:
    parts = []
    if short_name:
        parts.append(f"{DIM}{short_name}{RESET}")
    if effort:
        if effort in {"high", "max", "xhigh"}:
            parts.append(effort)
        else:
            parts.append(f"{DIM}{effort}{RESET}")
    return " ".join(parts)


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    left_parts = [format_mode(resolve_mode(data))]

    subagents = data.get("subagents") if isinstance(data.get("subagents"), list) else []
    running = sum(1 for s in subagents if isinstance(s, dict) and s.get("status") == "running")
    if running > 0:
        left_parts.append(f"{DIM}{running} {'agent' if running == 1 else 'agents'}{RESET}")

    left = "  ".join(left_parts)

    model = data.get("model") if isinstance(data.get("model"), dict) else {}
    short_name, effort = parse_model_and_effort(model)
    right = format_right(short_name, effort)

    if right:
        usable_width = max(20, get_terminal_width(data) - 2)
        gap = max(2, usable_width - visible_len(left) - visible_len(right))
        sys.stdout.write(f"{left}{' ' * gap}{right}\n")
    else:
        sys.stdout.write(f"{left}\n")


if __name__ == "__main__":
    main()
