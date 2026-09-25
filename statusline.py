#!/usr/bin/env python3
"""Phosphor status line for Claude Code.

Claude Code pipes the live session in as JSON and prints whatever comes back,
under the input box. Everything here comes from that blob — no log scraping,
no API calls — so it is exact and instant.

Animation note: Claude Code re-runs this on `statusLine.refreshInterval`,
minimum 1 second. So the frame clock is 1 Hz and every moving thing derives
its phase from wall-clock time rather than from a frame counter — that way the
motion is continuous across re-runs and survives the process dying between
frames.

Two lines:
  1. what you are talking to, and where
  2. how much room is left — context, the 5-hour window, the 7-day window
"""

import json
import colorsys
import math
import sys
import time

# ── palette ───────────────────────────────────────────────────────────
RULE = "\033[38;2;12;42;23m"
META = "\033[38;2;31;143;78m"
LIVE = "\033[38;2;65;255;141m"
WARM = "\033[38;2;185;255;214m"
HOT = "\033[38;2;234;255;243m"
ALARM = "\033[38;2;255;176;0m"
OFF = "\033[0m"

# The unfilled part of a bar is a track, not background: it has to show how
# much room is left. Anything darker than this vanishes on the tube.
TRACK = "\033[38;2;30;74;51m"

# A rail, not a wall. Full blocks were too heavy for a line this dense.
FULL, EMPTY = "━", "─"

# Arrows that cycle forward, so a countdown reads as still running.
SPIN = "◐◓◑◒"
FLOW = "▹▸▹▹"


def rgb(r, g, b):
    return f"\033[38;2;{int(r)};{int(g)};{int(b)}m"


def phase(period):
    """0..1 sawtooth from wall-clock time. Continuous across re-runs."""
    return (time.time() % period) / period


# ── colour ────────────────────────────────────────────────────────────
def usage_rgb(pct, lift=0.0):
    """A continuous ramp rather than three buckets: muted neon green with
    room, sliding through amber, to red as it fills. `lift` brightens for the
    shimmer without changing the hue, so the bar pulses instead of flashing."""
    if pct is None:
        return TRACK
    p = max(0.0, min(100.0, float(pct))) / 100.0
    if p < 0.75:                      # green → amber across the first 3/4
        t = p / 0.75
        r, g, b = 58 + 197 * t, 222 - 54 * t, 126 - 82 * t
    else:                             # amber → red over the last quarter
        t = (p - 0.75) / 0.25
        r, g, b = 255, 168 - 76 * t, 44 + 76 * t
    k = 1.0 + 0.35 * lift
    return rgb(min(255, r * k), min(255, g * k), min(255, b * k))


# rainbow() advances 0.075 of the wheel per unit, so a full turn is 13.33.
WHEEL = 1.0 / 0.075


def rainbow_text(text, speed=2.6, spread=0.42):
    """Paint a string across the spectrum and drift it.

    The wheel is fitted to the WORD rather than stepped per character. The
    spread is deliberately under half a turn: a short word spanning the whole
    band lands on three unrelated colours and reads as a jump, where a tight
    gradient that drifts through the band reads as one moving thing.

    THE MAX RULE: anywhere the word "max" appears in this UI it gets the
    rainbow — Claude Max, effort max, anything later. Max is the ceiling, and
    the ceiling is the one thing allowed to be every colour at once.
    """
    if not text:
        return ""
    step = spread * WHEEL / len(text)
    off = -phase(speed)
    return "".join(rainbow(i * step, off) + ch
                   for i, ch in enumerate(text)) + OFF


def maxify(text, speed=1.1):
    """Rainbow the word 'max' wherever it occurs, leave the rest alone."""
    low = text.lower()
    if "max" not in low:
        return None
    out, i = [], 0
    while i < len(text):
        j = low.find("max", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        out.append(rainbow_text(text[j:j + 3], speed))
        i = j + 3
    return "".join(out)


def rainbow(i, offset=0.0):
    """Adrenaline, not crayon.

    Muting it killed the neon; the childishness was never the saturation, it
    was spanning every hue — a full wheel drags through yellows, olives and
    browns, which is what kindergarten looks like. This runs at full neon but
    only across the hot band: cyan, electric blue, violet, magenta, hot pink,
    red, orange. No green, no yellow, ever.

    The band ping-pongs rather than wrapping, so there is no seam where pink
    snaps back to cyan.
    """
    t = (i * 0.075 + offset) % 1.0
    t = 2.0 * t if t < 0.5 else 2.0 * (1.0 - t)      # triangle, no seam
    h = ((185.0 + t * 200.0) % 360.0) / 360.0        # 185° → 385°
    r, g, b = colorsys.hsv_to_rgb(h, 0.92, 1.0)
    return rgb(r * 255, g * 255, b * 255)


# ── bar ───────────────────────────────────────────────────────────────
def bar(pct, width=10, party=False):
    """A shimmer travels through the filled portion so the bar reads as live
    rather than as a screenshot. When `party`, the whole fill is a moving
    rainbow instead."""
    if pct is None:
        return f"{TRACK}{EMPTY * width}{OFF}"

    pct = max(0.0, min(100.0, float(pct)))
    on = int(round(pct / 100.0 * width))
    head = phase(1.8) * (width + 6) - 3        # shimmer position, in cells
    out = []

    for i in range(width):
        if i < on:
            if party:
                out.append(rainbow(i, -phase(1.1)) + FULL)
            else:
                # gaussian falloff around the travelling head
                lift = math.exp(-((i - head) ** 2) / 2.2)
                out.append(usage_rgb(pct, lift) + FULL)
        else:
            out.append(TRACK + EMPTY)
    return "".join(out) + OFF


def cycle(seq, period=1.0):
    return seq[int(time.time() / period) % len(seq)]


def until(epoch):
    if not epoch:
        return ""
    left = int(epoch - time.time())
    if left <= 0:
        return "now"
    h, m = left // 3600, (left % 3600) // 60
    return f"{h}h{m:02d}m" if h else f"{m}m"


def link(url, text):
    """OSC 8 hyperlink. Cmd+click opens it.

    This is the only kind of click a terminal status line can carry: it hands
    a URL to the OS. It cannot open Claude Code's own menus — those live
    inside Claude Code, and nothing printed to the terminal can reach them.
    So only things that genuinely ARE somewhere get linked.
    """
    if not url:
        return text
    return f"\033]8;;{url}\a{text}\033]8;;\a"


EFFORT_LABELS = {"low": "Low", "medium": "Medium", "high": "High",
                 "xhigh": "XHigh", "max": "Max"}


def effort_label(raw):
    return EFFORT_LABELS.get(str(raw).lower(), str(raw).title())


def repo_url(d):
    host = dig(d, "workspace.repo.host")
    owner = dig(d, "workspace.repo.owner")
    name = dig(d, "workspace.repo.name")
    if host and owner and name:
        return f"https://{host}/{owner}/{name}"
    return None


def dig(d, path, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur if cur is not None else default


def main():
    try:
        d = json.load(sys.stdin)
    except (ValueError, OSError):
        d = {}

    model = dig(d, "model.display_name", "claude")
    effort = dig(d, "effort.level")
    fast = dig(d, "fast_mode")
    cwd = dig(d, "workspace.current_dir", "") or ""
    folder = cwd.rstrip("/").rsplit("/", 1)[-1] or "~"
    cost = dig(d, "cost.total_cost_usd")
    dur = dig(d, "cost.total_duration_ms")
    added = dig(d, "cost.total_lines_added", 0)
    removed = dig(d, "cost.total_lines_removed", 0)

    ctx = dig(d, "context_window.used_percentage")
    five = dig(d, "rate_limits.five_hour.used_percentage")
    five_at = dig(d, "rate_limits.five_hour.resets_at")
    seven = dig(d, "rate_limits.seven_day.used_percentage")

    # ── use it or lose it ─────────────────────────────────────────────
    # Plenty of window left and it resets within the hour: that headroom is
    # about to evaporate. The rainbow says spend it.
    left = (five_at - time.time()) if five_at else None
    party = (five is not None and five < 50.0
             and left is not None and 0 < left < 3600)

    # ── line 1 · what and where
    painted = maxify(model)
    if painted:
        # every rainbow run ends with a reset, so re-assert the surrounding
        # colour after each one or the rest of the name goes default-white
        model_txt = f"{HOT}" + painted.replace(OFF, OFF + HOT) + OFF
    else:
        model_txt = f"{HOT}{model}{OFF}"
    bits = [f"{RULE}▖{OFF} {model_txt}"]
    if effort:
        label = effort_label(effort)
        bits.append(rainbow_text(label) if effort.lower() == "max"
                    else f"{META}{label}{OFF}")
    if fast:
        bits.append(f"{ALARM}fast{OFF}")
    bits.append(f"{WARM}{link('file://' + cwd, folder) if cwd else folder}{OFF}")
    branch = dig(d, "worktree.branch") or dig(d, "workspace.repo.name")
    if branch:
        bits.append(f"{RULE}⌥{OFF} {META}"
                    f"{link(repo_url(d), branch)}{OFF}")
    pr = dig(d, "pr.number")
    if pr:
        state = dig(d, "pr.review_state", "")
        col = (LIVE if state == "approved"
               else (ALARM if state == "changes_requested" else META))
        bits.append(f"{col}{link(dig(d, 'pr.url'), '#' + str(pr))}{OFF}")
    if added or removed:
        bits.append(f"{LIVE}+{added}{OFF}{RULE}/{OFF}{ALARM}-{removed}{OFF}")
    line1 = f" {RULE}·{OFF} ".join(bits)

    # ── line 2 · how much room is left
    seg = [f" {META}ctx{OFF} {bar(ctx)} "
           f"{usage_rgb(ctx)}{(ctx or 0):.0f}%{OFF}"]

    five_txt = f"{META}5h{OFF} {bar(five, party=party)} "
    if party:
        five_txt += f"{rainbow(0, -phase(1.1))}{(five or 0):.0f}%{OFF}"
    else:
        five_txt += f"{usage_rgb(five)}{(five or 0):.0f}%{OFF}"
    if five_at:
        # the spinner keeps turning, so a countdown looks like it is counting
        mark = cycle(SPIN, 0.5)
        col = rainbow(2, -phase(1.1)) if party else RULE
        five_txt += f" {col}{mark}{until(five_at)}{OFF}"
    seg.append(five_txt)

    if seven is not None:
        seg.append(f"{META}7d{OFF} {bar(seven, 7)} "
                   f"{usage_rgb(seven)}{seven:.0f}%{OFF}")

    tail = []
    if cost:
        tail.append(f"{LIVE}${cost:.2f}{OFF}")
    if dur:
        mins = int(dur / 60000)
        tail.append(f"{RULE}{mins // 60}h{mins % 60:02d}m{OFF}"
                    if mins >= 60 else f"{RULE}{mins}m{OFF}")
    if party:
        tail.append(f"{rainbow(4, -phase(1.1))}{cycle(FLOW, 0.25)} "
                    f"window resets — send it{OFF}")
    if tail:
        seg.append(f" {RULE}·{OFF} ".join(tail))

    line2 = f" {RULE}·{OFF} ".join(seg)

    print(line1)
    print(line2)


if __name__ == "__main__":
    main()
