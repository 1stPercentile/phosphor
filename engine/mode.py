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

Pip follows whoever runs him, so each session keeps its own record in
sessions.json ("<mode> <work began> <last hook> <last work hook>", keyed by the
hook's session_id) and current() takes the most urgent across them: any session
waiting on you, then any working, then idle. One shared record let the last
hook win, so a prompt in one session hid another still waiting on you.
Prompts closer together than STRETCH are one working stretch, a turn that ends
inside it still reads as work, and a session drops out DECAY after its last
hook. mode.txt holds the aggregate in the same four fields.

    mode.py work | idle | needs
"""
import fcntl
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

MODE = paths.cache("pip", "mode.txt")
SESSIONS = paths.cache("pip", "sessions.json")
STRETCH = 5 * 60   # prompts closer together than this are one working stretch
DECAY = 20 * 60    # a session with no hook for this long drops out


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
    if len(times) == 1:
        # An old "<mode> <ts>" file: a work hook at ts, or no work at all.
        times = [times[0], times[0], times[0] if parts[0] == "work" else 0]
    times += [times[-1]] * (3 - len(times))
    return (parts[0], *times)


def read_sessions(now):
    """{session: (mode, began, last, last work)} for sessions heard from within DECAY."""
    try:
        with open(SESSIONS, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return None
    out = {}
    for sid, rec in (raw.items() if isinstance(raw, dict) else []):
        try:
            word, began, last, last_work = str(rec[0]), int(rec[1]), int(rec[2]), int(rec[3])
        except (TypeError, ValueError, IndexError):
            continue
        if now - last < DECAY:
            out[str(sid)] = (word, began, last, last_work)
    return out


def aggregate(sessions, now):
    """The most urgent state across sessions, in mode.txt's four fields."""
    live = [r for r in sessions.values() if now - r[2] < DECAY]
    if not live:
        return "idle", 0, 0, 0
    needs = [r for r in live if r[0] == "needs"]
    working = [r for r in live if r not in needs and (r[0] == "work" or now - r[3] < STRETCH)]
    word = "needs" if needs else "work" if working else "idle"
    began = min(r[1] for r in working) if working else 0
    return word, began, max(r[2] for r in live), max(r[3] for r in live)


def current(now=None):
    """The aggregate now; before any per-session hook, the old single mode.txt."""
    now = int(time.time() if now is None else now)
    sessions = read_sessions(now)
    if sessions is None:
        return read()
    return aggregate(sessions, now)


def _write(path, text):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def session_of(raw):
    try:
        sid = json.loads(raw).get("session_id")
    except (ValueError, AttributeError):
        sid = None
    return str(sid) if sid else "default"


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "idle").strip()
    if mode not in ("work", "idle", "needs"):
        mode = "idle"
    # the hook's JSON names the session; read it all so the hook never blocks on a full pipe
    try:
        raw = "" if sys.stdin.isatty() else sys.stdin.read()
    except Exception:
        raw = ""
    sid = session_of(raw)
    os.makedirs(os.path.dirname(MODE), exist_ok=True)
    now = int(time.time())
    with open(SESSIONS + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        sessions = read_sessions(now) or {}
        _, began, _, last_work = sessions.get(sid, ("idle", 0, 0, 0))
        if mode == "work":
            if now - last_work > STRETCH:
                began = now
            last_work = now
        sessions[sid] = (mode, began, now, last_work)
        _write(SESSIONS, json.dumps(sessions))
        _write(MODE, "%s %d %d %d\n" % aggregate(sessions, now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
