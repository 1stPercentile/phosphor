#!/usr/bin/env python3
"""Shared Phosphor formatting for prices.

The shell banner, the Dock board and the sidebar read the same cache and the
same colour rules, so a price never looks like two different things in two
places.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

CACHE = paths.cache("ticker.json")

RULE = "\033[38;2;12;42;23m"
META = "\033[38;2;31;143;78m"
LIVE = "\033[38;2;65;255;141m"
WARM = "\033[38;2;185;255;214m"
HOT = "\033[38;2;234;255;243m"
ALARM = "\033[38;2;255;176;0m"
DOWN = "\033[38;2;255;77;77m"   # market red — amber stays for machine faults
OFF = "\033[0m"


def load():
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def money(v):
    """Prices span nine orders of magnitude here. Pick a shape that fits."""
    if v is None:
        return "—"
    if v >= 10000:
        return f"{v:,.0f}"
    if v >= 100:
        return f"{v:,.2f}"
    if v >= 1:
        return f"{v:,.3f}"
    if v >= 0.001:
        return f"{v:.4f}"
    return f"{v:.8f}".rstrip("0")


def big(v):
    if v is None:
        return "—"
    for cut, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= cut:
            return f"{v / cut:.2f}{suf}"
    return f"{v:.0f}"


def mtd(v):
    """Signed dollars since the 1st. Precision follows the price's scale so
    a small-cap reads as cents and BTC as whole dollars."""
    if v is None:
        return RULE, "—"
    col = LIVE if v >= 0 else DOWN
    a = abs(v)
    if a >= 100:
        txt = f"{a:,.0f}"
    elif a >= 1:
        txt = f"{a:,.2f}"
    else:
        txt = f"{a:.4f}"
    return col, f"{'+' if v >= 0 else '−'}${txt}"


def shade(pct, up):
    """Magnitude in the colour: three steps each way, same as the sidebar."""
    a = abs(pct or 0)
    if up:
        return ("\033[38;2;140;255;196m" if a >= 5 else
                "\033[38;2;65;255;141m" if a >= 1 else "\033[38;2;47;184;106m")
    return ("\033[38;2;255;138;138m" if a >= 5 else
            "\033[38;2;255;77;77m" if a >= 1 else "\033[38;2;192;60;60m")


def arrow(change):
    """Direction is a glyph and a colour, never a minus sign to squint at."""
    if change is None:
        return RULE, "·", "—"
    return (shade(change, change >= 0), "▲" if change >= 0 else "▼",
            f"{abs(change):.2f}%")


def age(at):
    d = max(0, int(time.time() - at))
    if d < 90:
        return f"{d}s"
    if d < 5400:
        return f"{d // 60}m"
    return f"{d // 3600}h"


def line(data):
    """One compact line — what a terminal prints as it opens."""
    if not data or not data.get("rows"):
        return f"{RULE}·{OFF} {META}no feed{OFF}"
    out = []
    for r in data["rows"]:
        col, gl, ch = arrow(r.get("change24"))
        out.append(f"{WARM}{r['symbol']}{OFF} {LIVE}{money(r.get('price'))}{OFF} "
                   f"{col}{gl}{ch}{OFF}")
    return f"{RULE}·{OFF}  ".join(out)


def board(data, width=44):
    """The full readout — what the Dock panel holds open all day."""
    rows = []
    rule = f"{RULE}{'─' * width}{OFF}"
    if not data or not data.get("rows"):
        return [f"{META}no feed{OFF}", rule,
                f"{RULE}the poller has not written a price yet{OFF}"]

    rows.append(f"{RULE}▖{OFF} {META}MARKET{OFF} {RULE}·{OFF} {META}24H{OFF}"
                f"{' ' * max(1, width - 28)}{RULE}fed {age(data['at'])} ago{OFF}")
    rows.append(rule)
    for r in data["rows"]:
        col, gl, ch = arrow(r.get("change24"))
        sym = f"{HOT}{r['symbol']:<5}{OFF}"
        price = f"{LIVE}{money(r.get('price')):>13}{OFF}"
        chg = f"{col}{gl} {ch:>6}{OFF}"
        rows.append(f"{sym} {price}  {chg}")
        mc, mt = mtd(r.get("mtd"))
        rows.append(f"      {mc}{mt:>10}{OFF} {RULE}since 1st"
                    f"   mcap {big(r.get('mcap')):>7}{OFF}")
    if data.get("errors"):
        rows.append(rule)
        rows.append(f"{ALARM}✗ {', '.join(data['errors'])[:width - 2]}{OFF}")
    return rows
