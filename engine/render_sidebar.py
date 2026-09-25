#!/usr/bin/env python3
"""Bake the board, the sky and Pip into the cmux sidebar.

The sidebar runtime has no network and no filesystem: it can only read cmux's
own state. So prices and weather reach it the one way left: rendered as
literal source into phosphor.swift, which cmux hot-reloads on save.

cmux/phosphor.tmpl.swift is the thing to edit. This replaces its three
markers and writes ~/.config/cmux/sidebars/phosphor.swift (PHOSPHOR_SIDEBAR
overrides the target).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import render  # noqa: E402
import sky  # noqa: E402
import sprite  # noqa: E402

MARK = "// {{TICKER}}"
PIP_MARK = "// {{PIP}}"
SKY_MARK = "// {{SKY}}"


def esc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def shade(pct, up):
    """Colour carries magnitude, not just sign. A 0.3% move is a whisper, a
    9% move is a shout, and the eye should get that before the number does.
    Three steps each way, all inside the up-green / down-red families."""
    a = abs(pct or 0)
    if up:
        return "#8CFFC4" if a >= 5 else ("#41FF8D" if a >= 1 else "#2FB86A")
    return "#FF8A8A" if a >= 5 else ("#FF4D4D" if a >= 1 else "#C03C3C")


def token_block(r):
    """One line per token: symbol, price, month-to-date in dollars, 24h."""
    sym = r["symbol"]
    price = render.money(r.get("price"))
    change = r.get("change24")
    v = r.get("mtd")

    if v is None:
        m_txt, m_col = "—", "#0C2A17"
    else:
        a_ = abs(v)
        t = f"{a_:,.0f}" if a_ >= 100 else (f"{a_:,.2f}" if a_ >= 1 else f"{a_:.4f}")
        m_txt = f"{'+' if v >= 0 else '−'}${t}"
        m_col = shade(r.get("mtd_pct"), v >= 0)

    if change is None:
        c_col, c_txt = "#0C2A17", "·"
    else:
        c_col = shade(change, change >= 0)
        c_txt = f"{'▲' if change >= 0 else '▼'}{abs(change):.1f}%"

    return f'''        HStack(spacing: 7) {{
            Text("{esc(sym)}").foregroundColor("#EAFFF3")
                .font(.system(size: 12, design: .monospaced)).bold()
                .frame(width: 40, alignment: .leading).lineLimit(1)
            Text("{esc(price)}").foregroundColor("#41FF8D")
                .font(.system(size: 12, design: .monospaced))
                .monospacedDigit().lineLimit(1).fixedSize()
            Text("{m_txt}").foregroundColor("{m_col}")
                .font(.system(size: 12, design: .monospaced))
                .monospacedDigit().lineLimit(1).fixedSize()
            Text("{c_txt}").foregroundColor("{c_col}")
                .font(.system(size: 12, design: .monospaced)).bold()
                .monospacedDigit().lineLimit(1).fixedSize()
        }}'''


def build(data):
    if not data or not data.get("rows"):
        return ('        Text("no feed yet").foregroundColor("#1F8F4E")\n'
                '            .font(.system(size: 11, design: .monospaced))')
    rows = "\n".join(token_block(r) for r in data["rows"])
    # The board needs air under the heading or it reads as a table.
    return ("        VStack(alignment: .leading, spacing: 3) {\n"
            + rows + "\n        }\n        .padding(.top, 7)")


def bake(template=paths.TEMPLATE, mood=None):
    with open(template, encoding="utf-8") as fh:
        tmpl = fh.read()
    for mark in (MARK, PIP_MARK, SKY_MARK):
        if mark not in tmpl:
            raise ValueError(f"{template}: no {mark} marker")
    body = tmpl.replace(MARK, build(render.load()))
    body = body.replace(PIP_MARK, sprite.render(mood))
    try:
        body = body.replace(SKY_MARK, sky.render())
    except Exception as e:                     # the window never takes the sidebar down
        body = body.replace(SKY_MARK, f'    Text("{esc(f"window: {type(e).__name__}")}").foregroundColor("#FFB000")')
    return body


def main(out=None):
    out = out or paths.SIDEBAR
    body = bake()
    # Only touch the file when it actually changed: every write is a
    # hot-reload, and reloading an unchanged sidebar is a free flicker.
    try:
        with open(out, encoding="utf-8") as fh:
            if fh.read() == body:
                return 0
    except OSError:
        pass
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.replace(tmp, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
