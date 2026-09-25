#!/usr/bin/env python3
"""Pip's mode, driven by Claude Code's own hooks.

cmux's agent list can be empty for sessions it didn't launch itself, so the
sidebar can't always see "working" on its own. Claude Code can say so
directly: UserPromptSubmit fires when you send a prompt (working starts), Stop
when the response is done, Notification when Claude is waiting on you. Each
writes one word here and re-bakes the sidebar, so Pip changes pose within a
second of Claude changing state.

    mode.py work | idle | needs
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

MODE = paths.cache("pip", "mode.txt")


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "idle").strip()
    if mode not in ("work", "idle", "needs"):
        mode = "idle"
    os.makedirs(os.path.dirname(MODE), exist_ok=True)
    tmp = MODE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(f"{mode} {int(time.time())}\n")
    os.replace(tmp, MODE)
    # drain stdin so the hook never blocks on a full pipe
    try:
        sys.stdin.read()
    except Exception:
        pass
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "render_sidebar.py")],
                   timeout=20, capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
