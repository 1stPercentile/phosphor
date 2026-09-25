#!/usr/bin/env python3
"""Pip, alive.

He owns the bottom of the sidebar. This renders him as SwiftUI source; the
tick re-bakes it every minute. The sidebar evaluates `clock.second` live, so
everything below is a 60-frame schedule keyed off the wall clock: one frame a
second, a full minute of unique behaviour, then a NEW random schedule on the
next bake. That is how he blinks at random, changes where he looks, and never
visibly loops.

He is the Claude Code mascot, built from its own block glyphs:

      ▐▛███▛█
    ▝▜██████▀
      ▝▝ ▝▝

The two ▛ in the top row are missing their lower-right quadrant. That dark
notch IS his eye. Swapping that one glyph moves the pupil, so his eyes come
entirely from the block-glyph vocabulary and each row stays ONE Text, which is
what keeps him seamless:

    ▛ pupil down-right (default)   ▜ pupil down-left   ▀ a slit: the blink

Row two's ▜ and ▀ are his arms; the ▝▝ pairs are his legs. Both animate.

Every animated thing is emitted as a Swift func with an if-chain of literals,
because that is the one form the cmux sidebar interpreter reliably evaluates.
Arrays and `let` constants inside modifiers silently render the default.

    sprite.py [mood]     print the SwiftUI for one mood (default: a random idle)
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

# ── palette ───────────────────────────────────────────────────────────
SKIN = "#C77A5C"        # the mascot's own terracotta
DIM = "#1F8F4E"
RULE = "#0C2A17"
HOT = "#EAFFF3"
TEAR = "#6FD6FF"
SHADOW = "#0A1F14"
GROUND = "#020703"

SIZE = 30               # point size of the mascot glyphs
LINE = -6               # overlap that closes the seam between glyph rows
STRETCH = 1.3           # 30% taller at the same width

# ── his parts ─────────────────────────────────────────────────────────
# Only glyphs whose empty quadrant stays INSIDE his face. ▙ ▟ ▌ ▐ put the gap
# on the top edge of the row, where it merges with the background: he stops
# having eyes and grows notches in his crown. Looking up is conveyed by his
# body rising instead.
E_DEF, E_LEFT = "▛", "▜"        # pupil right / pupil left
E_SHUT = "▀"                    # a horizontal slit: the pixel-art closed eye.
                                # █ (no gap at all) reads as eyes VANISHED.

ARMS = "▝▜██████▀"       # at rest
ARMS_L = "▀▜██████▀"     # left arm reaches out (stub lengthens outward)
ARMS_R = "▝▜██████▀▘"    # right arm reaches out
ARMS_UP = "▀▜██████▀▘"   # both out
# Swapping an interior glyph (▜→▛, ▀→▜) punches a dark hole inside his body,
# which reads as a wound or a third eye. Arms only ever extend outward.
LEGS = "  ▝▝ ▝▝"
LEGS_L = " ▝▝   ▝▝"     # stride
LEGS_R = "   ▝▝▝▝"
LEGS_TIGHT = "   ▝▝▝▝"


def esc(t):
    return t.replace("\\", "\\\\").replace('"', '\\"')


def q(t):
    return f'"{esc(t)}"'


# ── moods ─────────────────────────────────────────────────────────────
def M(caption, gaze, blinks, motion, acc, colour,
      tears=False, arms=None, legs=None):
    """gaze: eye glyphs he drifts between. blinks: roughly per minute.
    motion: generator name. acc: frames cycled over his head.
    arms/legs: frame lists, or None for still."""
    return dict(caption=caption, gaze=gaze, blinks=blinks, motion=motion,
                acc=acc, acc_colour=colour, tears=tears, arms=arms, legs=legs)


# Pinnable poses: write one of these words to ~/.cache/phosphor/pip/state.txt.
POSES = {
    "thinking": M("thinking", [E_DEF, E_LEFT, E_DEF], 4, "bob",
                  ["·", "··", "···", "···", "··", "·"], DIM,
                  arms=[ARMS, ARMS, ARMS_L, ARMS]),
    "plotting": M("plotting", [E_LEFT, E_DEF, E_LEFT], 3, "lean",
                  ["◜", "◝", "◞", "◟"], "#41FF8D"),
    "trading":  M("at the desk", [E_DEF], 2, "jitter",
                  ["▁", "▃", "▅", "▇", "▅", "▃"], "#40C8E0",
                  arms=[ARMS_L, ARMS_R]),
    "mining":   M("mining", [E_DEF, E_LEFT], 4, "bob",
                  ["₿", " ₿", "  ₿", "   ₿", "  ₿"], "#F7931A",
                  arms=[ARMS, ARMS_UP]),
    "phone":    M("on his phone", [E_DEF, E_DEF, E_LEFT], 3, "drift",
                  ["$", " $", "  $", "   $"], "#41FF8D",
                  arms=[ARMS_R]),
}

# What he does on his own, one picked at random per bake.
IDLE = [
    M("vibing",         [E_DEF, E_LEFT, E_DEF], 5, "hop",
      ["˙", " ", "·", " "], DIM),
    M("dancing",        [E_LEFT, E_DEF], 3, "dance",
      ["♪", "♫", "♪", "♬"], "#FF7AD0",
      arms=[ARMS_L, ARMS_UP, ARMS_R, ARMS_UP],
      legs=[LEGS, LEGS_L, LEGS, LEGS_R]),
    M("locked in",      [E_DEF], 0, "jitter",
      ["▮", "▮", "▯"], "#41FF8D"),
    M("doomscrolling",  [E_LEFT, E_DEF], 3, "slump",
      ["▪", "▫", "▪", "▫"], "#40C8E0", arms=[ARMS_R]),
    M("coping",         [E_LEFT, E_LEFT, E_DEF], 6, "slump",
      ["·", " ", ".", " "], RULE, tears=True),
    M("gm",             [E_DEF, E_LEFT], 4, "rise",
      ["☀", " ☀", "  ☀", " ☀"], "#FFB000", arms=[ARMS, ARMS_UP]),
    M("touching grass", [E_DEF, E_LEFT], 4, "pace",
      ["❦", " ❦", "❦", "  ❦"], "#41FF8D",
      legs=[LEGS, LEGS_L, LEGS, LEGS_R]),
    M("up only",        [E_DEF, E_LEFT], 3, "hops",
      ["▁", "▂", "▄", "▆", "▇", "█"], "#41FF8D",
      arms=[ARMS, ARMS_UP], legs=[LEGS, LEGS_TIGHT]),
]

BY_NAME = {m["caption"]: m for m in IDLE}

# Chosen LIVE by the sidebar from what Claude is doing: the moment a Claude
# starts working he gets to work; the moment it needs you he waves; the
# moment it stops he's back to a mood.
LIVE = {
    "work":  M("working", [E_DEF, E_LEFT], 3, "jitter",
               ["▁", "▃", "▅", "▇", "▅", "▃"], "#40C8E0",
               arms=[ARMS_L, ARMS_R]),
    "needs": M("needs you", [E_DEF], 8, "hops",
               ["!", " ", "!", " "], "#FFB000",
               arms=[ARMS_UP, ARMS]),
}


# ── 60-frame schedules ────────────────────────────────────────────────
def gaze_track(gazes, n=60):
    """Hold a direction a few seconds, then pick another. Both eyes move
    together; that is what reads as looking rather than flickering."""
    out = []
    while len(out) < n:
        out += [random.choice(gazes)] * random.randint(3, 9)
    return out[:n]


def blink_track(gaze, blinks, n=60):
    """Random single-frame blinks over the gaze track, never in the first
    second (a blink right after a re-bake reads as a glitch)."""
    track = list(gaze)
    if blinks > 0:
        for s in random.sample(range(2, n - 1), min(blinks, n - 3)):
            track[s] = E_SHUT
    return track


def motion(kind, n=60):
    """(dx, dy) per second. Amplitudes are large on purpose: a two-pixel bob
    is invisible."""
    f = []
    for s in range(n):
        if kind == "bob":
            f.append((0, [0, -4, -7, -4, 0, 2][s % 6]))
        elif kind == "dance":
            k = s % 8
            f.append(([-16, -10, 0, 10, 16, 10, 0, -10][k],
                      [0, -12, 0, -12, 0, -12, 0, -12][k]))
        elif kind == "pace":
            k = s % 16
            f.append(((k if k < 8 else 15 - k) * 7 - 26,
                      0 if k % 2 == 0 else -3))
        elif kind == "rise":
            f.append((0, [10, 5, 0, -6, -12, -14, -12, -6][s % 8]))
        elif kind == "slump":
            f.append(([0, 1, 0, -1][s % 4], [9, 10, 12, 12, 10, 9][s % 6]))
        elif kind == "lean":
            f.append(([0, 4, 8, 9, 8, 4][s % 6], [0, 1, 3, 3, 1, 0][s % 6]))
        elif kind == "drift":
            f.append(([-6, -3, 0, 4, 7, 4, 0, -3][s % 8],
                      [-3, -6, -4, 0, 3, 5, 2, -1][s % 8]))
        elif kind == "jitter":
            f.append((random.choice([0, 0, 1, -1, 2, -2]),
                      random.choice([0, 0, 1, -1])))
        elif kind == "hop":
            # mostly grounded, a small clean jump every few seconds
            k = s % 7
            f.append((0, [0, 0, 0, -10, -14, -6, 0][k]))
        elif kind == "hops":
            f.append((0, [0, -16, -26, -16, 0, 0, -8, -14, -8, 0][s % 10]))
        else:
            f.append((0, 0))
    return f


def squash(dys):
    """Stretch in the air, squash on the landing frame, neutral otherwise.
    The classic: it is what makes a hop a hop."""
    out = []
    for i, dy in enumerate(dys):
        prev = dys[i - 1] if i else 0
        if dy < -5:
            out.append((0.97, STRETCH + 0.05))
        elif dy >= 0 and prev < -5:
            out.append((1.05, STRETCH - 0.07))
        else:
            out.append((1.0, STRETCH))
    return out


# ── swift emit ────────────────────────────────────────────────────────
def func(name, rtype, track, default, fmt=lambda v: str(v)):
    """A func over clock.second with an if-chain. Runs of one value merge
    into range checks, so a track that rarely changes stays short."""
    lines = [f"func {name}(_ s: Int) -> {rtype} {{"]
    i = 0
    while i < len(track):
        j = i
        while j + 1 < len(track) and track[j + 1] == track[i]:
            j += 1
        if track[i] != default:
            cond = f"s == {i}" if i == j else f"s >= {i} && s <= {j}"
            lines.append(f"    if {cond} {{ return {fmt(track[i])} }}")
        i = j + 1
    lines.append(f"    return {fmt(default)}")
    lines.append("}")
    return "\n".join(lines)


def schedules(m, tag):
    """All the per-second funcs for one pose, suffixed by tag."""
    eyes = blink_track(gaze_track(m["gaze"]), m["blinks"])
    mv = motion(m["motion"])
    dxs, dys = [p[0] for p in mv], [p[1] for p in mv]
    sc = squash(dys)
    acc = [m["acc"][s % len(m["acc"])] for s in range(60)]
    arms = [(m["arms"] or [ARMS])[s % len(m["arms"] or [ARMS])] for s in range(60)]
    if m["legs"]:
        legs = [m["legs"][s % len(m["legs"])] for s in range(60)]
    else:
        legs = [LEGS_TIGHT if dy < -4 else LEGS for dy in dys]
    row1 = [f" ▐{e}███{e}█" for e in eyes]
    return [
        func(f"pipRow1{tag}", "String", row1, row1[0], q),
        func(f"pipRow2{tag}", "String", arms, ARMS, q),
        func(f"pipRow3{tag}", "String", legs, LEGS, q),
        func(f"pipDX{tag}", "Int", dxs, 0),
        func(f"pipDY{tag}", "Int", dys, 0),
        func(f"pipSX{tag}", "Double", [x[0] for x in sc], 1.0),
        func(f"pipSY{tag}", "Double", [x[1] for x in sc], STRETCH),
        func(f"pipAcc{tag}", "String", acc, acc[0], q),
    ]


def selector(name, rtype):
    """One func that picks the right schedule by live mode."""
    return (f"func {name}(_ s: Int) -> {rtype} {{\n"
            f"    if pipMode() == \"work\" {{ return {name}W(s) }}\n"
            f"    if pipMode() == \"needs\" {{ return {name}N(s) }}\n"
            f"    return {name}I(s)\n}}")


def hook_mode():
    """(word, since): work / needs / idle, as last reported by Claude Code's
    hooks through mode.py. Stale after twenty minutes."""
    try:
        with open(paths.cache("pip", "mode.txt"), encoding="utf-8") as fh:
            word, ts = (fh.read().split() + ["idle", "0"])[:2]
        if word in ("work", "needs") and time.time() - int(ts) < 20 * 60:
            return word, int(ts)
    except (OSError, ValueError):
        pass
    return "idle", int(time.time())


def pinned():
    """A mood pinned by hand in ~/.cache/phosphor/pip/state.txt, else None."""
    try:
        with open(paths.cache("pip", "state.txt"), encoding="utf-8") as fh:
            s = fh.read().strip()
        return s if (s in POSES or s in BY_NAME) else None
    except OSError:
        return None


def render(state=None):
    hm, started = hook_mode()
    state = state or pinned()
    if hm == "work":
        m = LIVE["work"]
    elif hm == "needs":
        m = LIVE["needs"]
    else:
        m = POSES.get(state) or BY_NAME.get(state) or random.choice(IDLE)

    funcs = schedules(m, "I") + schedules(LIVE["work"], "W") + schedules(LIVE["needs"], "N")

    # Live mode, read by the sidebar every second. cmux's own agent list is the
    # fast path; the hook file (baked in below) covers sessions cmux can't see.
    funcs.append(f'''func pipMode() -> String {{
    let sel = workspaces.filter {{ $0.selected }}
    if sel.count == 0 {{ return "{hm}" }}
    let w = sel.first
    if w.agents == nil {{ return "{hm}" }}
    if w.agents.filter {{ $0.status == "needs_input" }}.count > 0 {{ return "needs" }}
    if w.agents.filter {{ $0.status == "working" }}.count > 0 {{ return "work" }}
    return "{hm}"
}}''')
    for name, rt in (("pipRow1", "String"), ("pipRow2", "String"),
                     ("pipRow3", "String"), ("pipDX", "Int"), ("pipDY", "Int"),
                     ("pipSX", "Double"), ("pipSY", "Double"), ("pipAcc", "String")):
        funcs.append(selector(name, rt))

    # While working, the caption walks the stages of a turn, timed from the
    # prompt (the hook's timestamp), live off the clock.
    funcs.append(f'''func pipCapW(_ s: Int) -> String {{
    let e = clock.epoch - {started}
    if e < 8 {{ return "reading…" }}
    if e < 30 {{ return "thinking…" }}
    if e < 150 {{ return "writing…" }}
    return "still going…"
}}''')
    funcs.append(f'''func pipCap(_ s: Int) -> String {{
    if pipMode() == "work" {{ return pipCapW(s) }}
    if pipMode() == "needs" {{ return "needs you" }}
    return {q(m["caption"])}
}}
func pipAccColour() -> String {{
    if pipMode() == "work" {{ return "{LIVE["work"]["acc_colour"]}" }}
    if pipMode() == "needs" {{ return "{LIVE["needs"]["acc_colour"]}" }}
    return "{m["acc_colour"]}"
}}
func pipCapColour() -> String {{
    if pipMode() == "needs" {{ return "#FFB000" }}
    if pipMode() == "work" {{ return "#40C8E0" }}
    return "{DIM}"
}}''')

    tears = ""
    if m["tears"]:
        ty = [[4, 12, 20, 26][s % 4] for s in range(60)]
        funcs.append(func("pipTearY", "Int", ty, 4))
        tears = f'''
                Text("●   ●")
                    .foregroundColor(pipMode() == "idle" ? "{TEAR}" : "{GROUND}")
                    .font(.system(size: 16, design: .monospaced)).bold()
                    .offset(x: 0, y: pipTearY(clock.second))
                    .zIndex(2)'''

    glyph = f'.font(.system(size: {SIZE}, design: .monospaced))'
    return f'''{chr(10).join(funcs)}

    // ═══ Pip ══════════════════════════════════════════════════════════
    // Fixed stage, so he can move anywhere inside it without reflowing
    // anything above. Pose is chosen LIVE from what Claude is doing.
    VStack(alignment: .leading, spacing: 0) {{

        Rectangle().fill("{RULE}").frame(height: 1).padding(.horizontal, 10)

        VStack(alignment: .center, spacing: 0) {{
            Text(pipAcc(clock.second))
                .foregroundColor(pipAccColour())
                .font(.system(size: 18, design: .monospaced))
                .frame(height: 26)

            ZStack {{
                VStack(alignment: .leading, spacing: {LINE}) {{
                    Text(pipRow1(clock.second)).foregroundColor("{SKIN}"){glyph}
                    Text(pipRow2(clock.second)).foregroundColor("{SKIN}"){glyph}
                    Text(pipRow3(clock.second)).foregroundColor("{SKIN}"){glyph}
                }}{tears}
            }}
            .scaleEffect(x: pipSX(clock.second), y: pipSY(clock.second))
            .offset(x: pipDX(clock.second), y: pipDY(clock.second))
            .frame(height: 88)

            Rectangle().fill("{SHADOW}")
                .frame(width: pipDY(clock.second) < -5 ? 44 : 86, height: 3)
                .padding(.top, 12)
        }}
        .frame(maxWidth: .infinity, height: 88, alignment: .center)
        .overlay(alignment: .bottomLeading) {{
            // his status lives in his room, bottom-left, level with his shadow
            HStack(spacing: 6) {{
                Text("Pip:").foregroundColor("{HOT}")
                    .font(.system(size: 11, design: .monospaced)).bold()
                    .frame(width: 32, alignment: .leading)
                Text(pipCap(clock.second)).foregroundColor(pipCapColour())
                    .font(.system(size: 11, design: .monospaced))
                    .lineLimit(1).fixedSize()
            }}
            .padding(.leading, 12)
            .offset(x: 15, y: 26)
        }}

        Rectangle().fill("{RULE}").frame(height: 1).padding(.horizontal, 10)

        // his shadow and nameplate hang below the stage; this is their room
        Spacer().frame(height: 60)
    }}
    .frame(maxWidth: .infinity, alignment: .leading)'''


if __name__ == "__main__":
    sys.stdout.write(render(sys.argv[1] if len(sys.argv) > 1 else None))
