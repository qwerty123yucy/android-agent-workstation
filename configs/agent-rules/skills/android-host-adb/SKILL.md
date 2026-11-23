---
name: android-host-adb
description: >-
  Host-specific constraints and quirks for using loopback ADB (127.0.0.1:5037 ->
  127.0.0.1:5555) from inside a Termux PRoot container. Activate before running
  on-device Android app automation, install, UI inspection, UTF-8 text input, or logcat tasks.
---

# Termux PRoot Host ADB Constraints

- **Reuse native Termux ADB**: Native Termux hosts the ADB server at `127.0.0.1:5037` connected to `127.0.0.1:5555`; `/usr/bin/adb` (`1.0.41`) reuses it directly. Never run `adb kill-server` or attempt wireless pairing inside `proot`.
- **On disconnect**: Verify with `adb devices -l`. If missing or `offline`, try `adb connect 127.0.0.1:5555` **once**. If still unavailable, stop and notify the user to reconfigure ADB in native Termux.
- **Duplicate loopback serial (`emulator-5554` + `127.0.0.1:5555`)**: After a daemon restart, ADB may auto-probe local port `5555` as `emulator-5554` alongside `127.0.0.1:5555`, causing bare `adb` commands to fail with `more than one device/emulator`. Always target `-s 127.0.0.1:5555` explicitly in scripts and commands.
- **No shared `/sdcard` (`--isolated`)**: Transfer artifacts over TCP streams (`adb -s 127.0.0.1:5555 exec-out screencap -p`, dump UI XML to `/data/local/tmp` then `adb -s 127.0.0.1:5555 exec-out cat`), not `/sdcard` bind mounts.
- **Privacy & foreground guard**: Only act on the user-authorized target package. Check `mCurrentFocus` (`dumpsys window displays`) before capturing UI or injecting input (`NotificationShade` = locked; `permissioncontroller` = permission prompt).
- **OEM ROM permission quirk**: If silent install or `input` injection fails with permission errors (`INJECT_EVENTS`), remind the user to enable **Disable Permission Monitoring (禁止权限监控)** on ColorOS or **USB Debugging (Security Settings)** on MIUI/HyperOS in Developer Options.

## Host-Device Etiquette & Closed-Loop Debugging

- **Non-disruptive automated runs (Personal Host Phone)**:
  1. **Mute test audio**: Support a silent flag/intent extra (e.g., `--ez silent_test true`) during automated ADB verification so BGM/SFX never play aloud unexpectedly.
  2. **Isolate user data**: Route automated debug/save-load tests to a temporary `SharedPreferences` / DB name so real app state is never overwritten.
  3. **Release wake locks when done**: After verification completes, run `adb -s 127.0.0.1:5555 shell am force-stop <package>` if the app holds `FLAG_KEEP_SCREEN_ON` or continuous VSync loops so the phone screen can sleep normally.
- **DisplayCutout handling**: Read `WindowInsets.getDisplayCutout()` safe left/right insets to pad interactive HUD controls while letting backgrounds bleed edge-to-edge.
- **Custom `Canvas` / Game UI inspection**: `uiautomator` cannot see inside custom `Canvas` views. Use `android:launchMode="singleTask"` + `onNewIntent` debug scene hooks and emit a structured `Logcat` diagnostic line (`viewWxH`, safe insets, `id@cx,cy` hit centers, pairwise `RectF` overlap & OOB counts) alongside `adb exec-out screencap -p` visual inspection.
- **Realistic dwell-tap & truncation checks**: Verify modal/menu opener buttons with a human-dwell press-hold-release (`adb -s 127.0.0.1:5555 shell input swipe <x> <y> <x> <y> 150`) rather than only intent jumps or zero-dwell taps so `ACTION_DOWN -> redraw -> ACTION_UP` bounce-close bugs surface. During screenshot review, treat `...` ellipsis truncation on actionable info/descriptions as a layout bug even when bounding-box checks report `overlaps=0`.

## UTF-8 / Non-ASCII Text Input (Android 10–16 Quirks)

- Do **not** use `adb shell input text` for CJK/UTF-8 text: it injects hardware-keyboard events that bypass soft IME composition and output garbled/ASCII text.
- Do **not** rely on background `shell` `IClipboard` writes + `KEYCODE_PASTE` (`279`): Android 10+ blocks clipboard access when UID `2000` is unfocused.
- **Preferred path for sharing/messaging apps**: Pass UTF-8 text losslessly via Binder `ACTION_SEND` (`text/plain`), single-quoting the `--es` payload inside a single `adb shell "..."` argument so remote `/system/bin/sh` does not split on spaces:
  ```bash
  adb -s 127.0.0.1:5555 shell "am start -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT '<UTF-8 text>' -n <package>/<ShareActivity>"
  ```
- **Privacy-minimal UI dumps**: When inspecting authorized apps with `uiautomator dump /data/local/tmp/ui.xml`, filter parsed XML nodes strictly to relevant navigation/button bounds and remove `/data/local/tmp/*.xml` when finished.
