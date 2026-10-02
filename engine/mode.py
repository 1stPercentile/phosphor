#!/usr/bin/env python3
"""Pip's mode, driven by Claude Code's own hooks.

cmux's agent list can be empty for sessions it didn't launch itself, so the
sidebar can't always see "working" on its own. Claude Code can say so
directly: UserPromptSubmit fires when you send a prompt (working starts), Stop
when the response is done, Notification when Claude is waiting on you. Each
records the mode here; the minute tick bakes it into the sidebar.

It never re-bakes on its own. A hook fires on every turn of every session,
and every changed sidebar file is a full reload in cmux; with a few agents
running, re-baking per hook kept cmux busy and held up each prompt. Sessions
cmux can see still update Pip live through its agent list.

mode.txt is "<mode> <work began> <last hook> <last work hook>". Prompts closer
together than STRETCH are one working stretch: "work began" stays put and a
turn that ends inside the stretch still reads as work (sprite.hook_mode), so a
busy hour doesn't flip Pip back and forth.

    mode.py work | idle | needs
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

MODE = paths.cache("pip", "mode.txt")
STRETCH = 5 * 60


def read(path=None):
    """(mode, work began, last hook, last work hook); an old two-field file reads as one time."""
    try:
        with open(path or MODE, encoding="utf-8") as fh:
            parts = fh.read().split()
        times = [int(v) for v in parts[1:4]]
    except (OSError, ValueError):
        return "idle", 0, 0, 0
    if not parts or not times:
        return "idle", 0, 0, 0
    times += [times[-1]] * (3 - len(times))
    return (parts[0], *times)


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "idle").strip()
    if mode not in ("work", "idle", "needs"):
        mode = "idle"
    os.makedirs(os.path.dirname(MODE), exist_ok=True)
    now = int(time.time())
    _, began, _, last_work = read()
    if mode == "work":
        if now - last_work > STRETCH:
            began = now
        last_work = now
    tmp = MODE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(f"{mode} {began} {now} {last_work}\n")
    os.replace(tmp, MODE)
    # drain stdin so the hook never blocks on a full pipe
    try:
        sys.stdin.read()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
