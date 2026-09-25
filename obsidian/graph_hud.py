#!/usr/bin/env python3
"""Phosphor graph HUD: Obsidian's graph view as a terminal HUD around the note cloud.

Writes <vault>/.obsidian/snippets/phosphor-graph.css. Turn the snippet on once under
Settings > Appearance > CSS snippets; Obsidian hot-reloads it whenever this rewrites it.

    top-left      vault shape: notes / links / unresolved, and the colour key
    top-right     ticker            <- ~/.cache/phosphor/ticker.json (optional)
    bottom-left   recent commits    <- git log of the vault (opt-in, --log)

The radar ring, rain, grid and scanlines are the only decoration. Numbers stay
literal: green up, red down (the market), amber when a source is stale or broken.

Usage:
    python3 graph_hud.py /path/to/vault [--log] [--static]

The vault can also come from $PHOSPHOR_VAULT or the first line of
~/.config/phosphor/vault. Run it on a timer (cron, launchd, systemd) to keep the
readouts fresh; it writes only when something changed. Stdlib only, Python 3.9+.

The ticker is fed by anything you like. Write ~/.cache/phosphor/ticker.json as

    {"at": 1767225600, "errors": [],
     "rows": [{"symbol": "BTC", "price": 64000.0, "change24": 2.1,
               "mtd_pct": -4.0, "pinned": true}]}

"at" is epoch seconds; "change24" and "mtd_pct" are percentages; "mtd_pct" and
"pinned" are optional, and a pinned row is drawn white-hot. No file, no panel. A
file that can't be read, or is more than ten minutes old, is flagged in amber.
"""
import argparse, base64, datetime, json, math, os, random, re, subprocess, sys, time
from pathlib import Path

TICKER = Path.home() / ".cache/phosphor/ticker.json"
VAULT_FILE = Path.home() / ".config/phosphor/vault"
STATIC_MARKER = Path.home() / ".config/phosphor/graph-static"
SNIPPET = ".obsidian/snippets/phosphor-graph.css"

LIVE, CHROME, HOT, PALE = "#41FF8D", "#1F8F4E", "#EAFFF3", "#9BFFC9"
AMBER, RED = "#FFB000", "#FF4D4D"
FONT = "JetBrainsMono Nerd Font,Menlo,monospace"
CW = 6.7  # px per character at 11px


# ── data ──────────────────────────────────────────────────────────────

BROKEN = {"broken": True}  # the ticker file exists but can't be read


def load_ticker(path=None):
    """None when there is no ticker file, BROKEN when it can't be read, else the parsed feed."""
    path = Path(path) if path else TICKER
    if not path.exists():
        return None
    try:
        tk = json.loads(path.read_text())
        datetime.datetime.fromtimestamp(float(tk["at"]))
        if not isinstance(tk["rows"], list):
            raise ValueError("rows is not a list")
        return tk
    except Exception:
        return BROKEN


def excluded(filters):
    """Obsidian's Excluded files: a /regex/ or a path prefix, both case-insensitive. No globs."""
    pats = [re.compile(f[1:-1], re.I) if len(f) > 2 and f[0] == f[-1] == "/" else re.compile("^" + re.escape(f), re.I)
            for f in (x.strip() for x in filters) if f]
    return lambda path: any(p.search(path) for p in pats)


# Obsidian 1.13's parser: links outside fenced and inline code, %% comments %% and HTML comments;
# a Markdown link counts when its URL has no scheme (./, ../ or a bare path).
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[`~]*[ \t]*$|\Z)", re.M | re.S)
INLINE = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)", re.S)
COMMENTS = re.compile(r"%%.*?%%|<!--.*?-->", re.S)
WIKI = re.compile(r"!?\[\[([^\]\n]+?)\]\]")
MDLINK = re.compile(r"!?\[((?:[^\[\]\n]|\[[^\[\]\n]*\])*)\]\((<[^>\n]*>|[^)\s]*)((?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?)\s*\)")


def resolver(files):
    """getLinkpathDest, ported from Obsidian's app.js: by file name, then relative, exact or path-suffix match."""
    import collections, posixpath
    by_name = collections.defaultdict(list)
    for f in files:
        by_name[posixpath.basename(f).lower()].append(f)
    parent = lambda p: p[:p.rfind("/")] if "/" in p else ""

    def dest(e, src):
        if not e:
            return src
        n = e.lower()
        i = posixpath.basename(n)
        r = by_name.get(i) if "." in i else None
        if not r:  # an extensionless link names a note, never an extensionless file of the same name
            n = (e + ".md").lower()
            i = posixpath.basename(n)
            r = by_name.get(i)
        if not r:
            return None
        if i == n and len(r) == 1:
            return r[0]
        o = parent(src).lower()
        if n.startswith(("./", "../")):
            if n.startswith("./../"):
                n = n[2:]
            if n.startswith("./"):
                n = (o + "/" if o else "") + n[2:]
            else:
                while n.startswith("../"):
                    n, o = n[3:], parent(o)
                n = (o + "/" if o else "") + n
            for f in r:
                if f.lower() == n:
                    return f
        n = n[1:] if n.startswith("/") else n
        for f in r:
            if f.lower() == n:
                return f
        if e.startswith("/"):
            return None
        return next((f for f in r if f.lower().endswith(n)), None)
    return dest


def vault_shape(vault):
    """Notes, links and unresolved link targets, counted the way Obsidian's graph counts them.

    Obsidian follows folder symlinks inside the vault, hides dot-folders, keeps Excluded files
    out of the graph (they still resolve as destinations), and counts both [[wikilinks]] and
    internal [Markdown](links). It does not resolve a link through an alias. node_modules is
    skipped outright for speed, so a link Obsidian resolves only by accident to some package's
    file (a README's [LICENSE](LICENSE) finding a LICENSE.md inside node_modules) counts as
    unresolved here, which is the truer reading.
    """
    import unicodedata, urllib.parse
    vault = Path(vault)
    try:
        filters = json.loads((vault / ".obsidian/app.json").read_text()).get("userIgnoreFilters", [])
    except (OSError, ValueError, AttributeError):
        filters = []
    ignored = excluded(filters)
    files, seen = [], set()
    for d, dirs, names in os.walk(vault, followlinks=True):
        real = os.path.realpath(d)
        if real in seen:
            dirs[:] = []
            continue
        seen.add(real)
        rel = os.path.relpath(d, vault)
        rel = "" if rel == "." else rel
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "node_modules"]
        files += [f"{rel}/{n}" if rel else n for n in names if not n.startswith(".")]
    dest = resolver(files)
    norm = lambda s: unicodedata.normalize("NFC", s.replace(" ", " ").strip())
    notes = links = 0
    missing = set()
    for f in files:
        if not f.lower().endswith(".md") or ignored(f):
            continue
        notes += 1
        try:
            body = (vault / f).read_text(errors="ignore")
        except OSError:
            continue
        body = COMMENTS.sub("", INLINE.sub("", FENCE.sub("", body)))
        refs = []
        for m in WIKI.finditer(body):
            e = m.group(1)
            e = e[:e.find("|")] if e.find("|") > 0 else e
            e = e.strip()
            refs.append(norm(e[:-1] if e.endswith("\\") else e))
        for m in MDLINK.finditer(WIKI.sub("", body)):
            u = m.group(2)
            u = u[1:-1] if u.startswith("<") else u
            if u and (u.startswith(("./", "../")) or ":" not in u):
                try:
                    refs.append(norm(urllib.parse.unquote(u, errors="strict")))
                except UnicodeDecodeError:
                    continue
        for e in refs:
            links += 1
            e = e.split("#", 1)[0]
            if dest(e, f) is None:
                missing.add(e[:-3].lower() if e.lower().endswith(".md") else e.lower())
    return notes, links, len(missing)


def commits(vault, n=10):
    """Recent commits that touched the vault directory, newest first.

    `-- .` keeps a vault that lives inside a bigger repository to its own history.
    Returns [] when the vault is not in a git repository or git is not installed.
    """
    try:
        r = subprocess.run(["git", "-C", str(vault), "log", "-n", str(n), "--format=%ct\t%s", "--", "."],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    rows = []
    for line in r.stdout.splitlines():
        ts, _, subj = line.partition("\t")
        try:
            rows.append((datetime.datetime.fromtimestamp(int(ts)), subj))
        except ValueError:
            continue
    return rows


# ── formatting ────────────────────────────────────────────────────────
# Colour is the meaning, per the Phosphor law:
#   green up · red down (the market) · amber = a source is wrong or stale
#   white-hot = the one thing to look at: a pinned symbol, a fresh commit.
# Brightness and glow scale with size: noise (<3%) sits dim, a real move (3–10%)
# is coloured, a big move (≥10%) is full neon with a glow and an arrow.


def price(v):
    if not isinstance(v, (int, float)):
        return "n/a"
    return "{:,.0f}".format(v) if v >= 1000 else "%.2f" % v if v >= 1 else "%.4f" % v


def move(v):
    """-> (text, colour, opacity, glow) for a % change, loud in proportion to its size."""
    if not isinstance(v, (int, float)):
        return "n/a", CHROME, .5, False
    a = abs(v)
    s = ("%+.0f%%" % v) if a >= 1 else ("%+.1f%%" % v)
    if a < 3:
        return "· " + s, PALE, .55, False
    col = LIVE if v > 0 else RED
    if a < 10:
        return s, col, .85, False
    return ("▲ " if v > 0 else "▼ ") + s, col, 1, True


def ago(dt):
    s = (datetime.datetime.now() - dt).total_seconds()
    return "%dm" % (s // 60) if s < 3600 else "%dh" % (s // 3600) if s < 86400 * 2 else "%dd" % (s // 86400)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


NEON = ('<defs><filter id="n" x="-20%" y="-60%" width="140%" height="220%">'
        '<feGaussianBlur stdDeviation="2.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        '</filter><filter id="s" x="-20%" y="-60%" width="140%" height="220%">'
        '<feGaussianBlur stdDeviation="1.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>')


def svg(w, h, body, size=11):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'font-family="{FONT}" font-size="{size}" xml:space="preserve">{NEON}{body}</svg>')


def txt(x, y, s, fill=CHROME, op=.75, anchor="start", glow=None, weight=None, size=None):
    f = f' filter="url(#{glow})"' if glow else ""
    w = f' font-weight="{weight}"' if weight else ""
    z = f' font-size="{size}"' if size else ""
    return (f'<text x="{x:.0f}" y="{y}" fill="{fill}" fill-opacity="{op}" '
            f'text-anchor="{anchor}"{f}{w}{z}>{esc(s)}</text>')


def mtxt(x, y, v, anchor="end"):
    s, c, op, big = move(v)
    return txt(x, y, s, c, op, anchor, "n" if big else ("s" if op > .6 else None))


def uri(s):
    return "data:image/svg+xml;base64," + base64.b64encode(s.encode()).decode()


def stale_tag(x, y, label, anchor="end"):
    return (f'<text x="{x:.0f}" y="{y}" fill="{AMBER}" text-anchor="{anchor}" filter="url(#s)">{esc(label)}'
            f'<animate attributeName="fill-opacity" values="1;.35;1" dur="2.4s" repeatCount="indefinite"/></text>')


def name(x, y, label, pinned):
    return (txt(x, y, "◆ " + label, HOT, 1, glow="s", weight="bold") if pinned
            else txt(x, y, "  " + label, PALE, .7))


# ── panels ────────────────────────────────────────────────────────────

def header(shape, market=False):
    """Title, the vault's shape, and a key to every colour the HUD is showing."""
    notes, links, unresolved = shape
    title = "▌PHOSPHOR//LATTICE"
    b = [txt(0, 15, title, LIVE, 1, glow="n", weight="bold", size=13)]
    x = CW * 13 / 11 * len(title) + 22
    for label, col, glow in (("%d notes" % notes, HOT, "s"), (" · ", CHROME, None),
                             ("%d links" % links, HOT, "s"), (" · ", CHROME, None),
                             ("%d unresolved" % unresolved, AMBER if unresolved else CHROME,
                              "s" if unresolved else None)):
        b.append(txt(x, 15, label, col, .9, glow=glow))
        x += CW * len(label)
    key = [("●", "note", LIVE), ("●", "unresolved / stale", AMBER)]
    if market:
        key += [("▲", "up", LIVE), ("▼", "down", RED), ("·", "noise <3%", PALE), ("◆", "pinned", HOT)]
    y, lx = 38, 0
    for mark, label, col in key:
        b.append(txt(lx, y, mark, col, 1, glow="s"))
        b.append(txt(lx + CW * 1.6, y, label, CHROME, .75))
        lx += CW * (len(label) + 4)
    b.append(f'<line x1="0" y1="48" x2="520" y2="48" stroke="{LIVE}" stroke-opacity=".35" stroke-dasharray="2 3"/>')
    return svg(530, 54, "".join(b))


def ticker(tk):
    if tk is BROKEN or not isinstance(tk, dict) or tk.get("broken"):
        return svg(270, 20, stale_tag(0, 14, "TICKER  feed unreadable", "start"))
    rows = [r for r in tk.get("rows", []) if isinstance(r, dict) and r.get("symbol")]
    mtd = any(isinstance(r.get("mtd_pct"), (int, float)) for r in rows)
    W = 270 if mtd else 215
    day = 205 if mtd else W
    at = datetime.datetime.fromtimestamp(float(tk["at"]))
    stale = (datetime.datetime.now() - at).total_seconds() > 600
    b = [txt(0, 12, "TICKER", LIVE, .9, glow="s", weight="bold"),
         stale_tag(W, 12, "■ STALE " + ago(at)) if stale else txt(W, 12, at.strftime("%H:%M"), PALE, .7, "end"),
         txt(day, 30, "24h", CHROME, .7, "end")]
    if mtd:
        b.append(txt(W, 30, "mtd", CHROME, .7, "end"))
    y = 48
    if not rows:
        b.append(stale_tag(0, y, "no rows in feed", "start"))
        y += 16
    for r in rows:
        pinned = bool(r.get("pinned"))
        b.append(name(0, y, str(r["symbol"])[:10], pinned))
        b.append(txt(145, y, price(r.get("price")), HOT, .95 if pinned else .8, "end", "s" if pinned else None))
        b.append(mtxt(day, y, r.get("change24")))
        if mtd:
            s, c, op, _ = move(r.get("mtd_pct"))
            b.append(txt(W, y, s, c, op * .75, "end"))
        y += 16
    errors = tk.get("errors") or []
    if errors:
        b.append(stale_tag(0, y + 4, "■ %d feed error%s" % (len(errors), "" if len(errors) == 1 else "s"), "start"))
        y += 20
    return svg(W, y - 10, "".join(b))


# Commit subjects written by sync tools rather than a person: Obsidian Git's default
# "vault backup: …", and anything that starts "backup", "auto", "autocommit" or "autosave".
AUTO = re.compile(r"(vault backup|backup|auto(commit|save)?)\b", re.I)


def vault_log(rows, lh=16):
    W = 520
    b = [txt(0, 12, "VAULT LOG", LIVE, .9, glow="s", weight="bold"),
         txt(CW * 11, 12, "git · ", CHROME, .7),
         txt(CW * 17, 12, "▪ work", HOT, .9), txt(CW * 25, 12, "▪ auto", CHROME, .8)]
    for i, (dt, subj) in enumerate(rows):
        y = 32 + i * lh
        auto = AUTO.match(subj) is not None
        area, _, rest = subj.partition(": ") if ": " in subj else ("", "", subj)
        fresh = (datetime.datetime.now() - dt).total_seconds() < 1800
        b.append(txt(0, y, dt.strftime("%H:%M"), LIVE if fresh else CHROME, .95 if fresh else .7,
                     glow="s" if fresh else None))
        if auto:
            b.append(txt(CW * 7, y, (subj[:62] + "…") if len(subj) > 63 else subj, CHROME, .65))
        else:
            b.append(txt(CW * 7, y, area, HOT, 1, glow="s", weight="bold"))
            rest = rest if len(rest) <= 58 - len(area) else rest[:57 - len(area)] + "…"
            b.append(txt(CW * (9 + len(area)), y, rest, PALE, .85))
    return svg(W, 32 + len(rows) * lh - lh + 6, "".join(b))


# ── decoration ────────────────────────────────────────────────────────

def radar():
    c = 500
    ticks = []
    for d in range(0, 360, 3):
        a = math.radians(d)
        r2 = 470 - (18 if d % 45 == 0 else 6)
        ticks.append(f'<line x1="{c+470*math.cos(a):.1f}" y1="{c+470*math.sin(a):.1f}" '
                     f'x2="{c+r2*math.cos(a):.1f}" y2="{c+r2*math.sin(a):.1f}"/>')
    sweep = (f'<g><path d="M{c} {c} L{c+470} {c} A470 470 0 0 0 {c+470*math.cos(-.35):.1f} {c+470*math.sin(-.35):.1f} Z" '
             f'fill="{LIVE}" fill-opacity=".03"/>'
             f'<line x1="{c}" y1="{c}" x2="{c+470}" y2="{c}" stroke="{LIVE}" stroke-opacity=".12"/>'
             f'<animateTransform attributeName="transform" type="rotate" from="0 {c} {c}" to="360 {c} {c}" '
             f'dur="14s" repeatCount="indefinite"/></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">'
            f'<g stroke="{LIVE}" stroke-opacity=".2" fill="none">{"".join(ticks)}'
            f'<circle cx="{c}" cy="{c}" r="470"/><circle cx="{c}" cy="{c}" r="300" stroke-dasharray="2 10"/>'
            f'<path d="M{c-490} {c}h40M{c+450} {c}h40M{c} {c-490}v40M{c} {c+450}v40"/></g>{sweep}</svg>')


def rain(w, h, cell, bright, seed=1789):
    rnd = random.Random(seed)  # seeded per call, so the same inputs always render the same file
    glyphs = [chr(x) for x in range(0xFF66, 0xFF9E)] + list("0123456789:.=*+<>")
    rows, out = h // cell, []
    for col in range(w // cell):
        if rnd.random() < .55:
            continue
        head, length = rnd.randrange(rows), rnd.randint(4, rows // 3)
        for i in range(length):
            op = bright * (1 - i / length) ** 1.8
            out.append(f'<text x="{col*cell}" y="{((head-i)%rows+1)*cell}" fill-opacity="{op:.2f}">'
                       f'{rnd.choice(glyphs)}</text>')
    return svg(w, h, f'<g fill="{LIVE}">{"".join(out)}</g>', size=cell - 2)


def grid():
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48">'
            f'<circle cx="0" cy="0" r="1" fill="{LIVE}" fill-opacity=".14"/></svg>')


SCOPE = '.workspace-leaf-content:is([data-type="graph"],[data-type="localgraph"])'

CSS = """/* ═════════════════════════════════════════════════════════════════════
   PHOSPHOR GRAPH HUD
   generated by graph_hud.py — edit the script, not this file.
   A terminal HUD around the note cloud. Every readout is live: {READOUTS}.
   Only the radar, rain, grid and scanlines are decoration. The notes stay
   the brightest thing.
   Updated {STAMP}.
   ═════════════════════════════════════════════════════════════════════ */

SCOPE .view-content {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  background-color: #010301;
  background-image:
    url("{RAIN}"),
    radial-gradient(ellipse at 50% 50%, rgba(65,255,141,.06) 0%, transparent 60%),
    url("{GRID}");
  background-size: 480px 960px, 100% 100%, 48px 48px;
  background-position: 0 0, center, center;
  animation: lattice-rain 60s linear infinite;
}

@keyframes lattice-rain {
  from { background-position: 0 0, center, center; }
  to   { background-position: 0 960px, center, center; }
}

/* the HUD: readouts pinned to the edges, one faint radar ring behind the cloud */
SCOPE .view-content::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background-image:
    {LAYER_IMAGES};
  background-repeat: no-repeat;
  background-position:
    {LAYER_POSITIONS};
  background-size: {LAYER_SIZES};
}

/* the tube: scanlines, a faint sweep, a soft vignette — clicks pass through */
SCOPE .view-content::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 3;
  pointer-events: none;
  background:
    linear-gradient(180deg, transparent 0%, rgba(65,255,141,.025) 49%, rgba(65,255,141,.05) 50%, transparent 51%) 0 0 / 100% 300% no-repeat,
    repeating-linear-gradient(180deg, rgba(0,0,0,.22) 0 1px, transparent 1px 3px),
    radial-gradient(ellipse at center, transparent 60%, rgba(0,0,0,.35) 100%);
  animation: lattice-sweep 11s linear infinite;
}

@keyframes lattice-sweep {
  from { background-position: 0 -100%, 0 0, center; }
  to   { background-position: 0 200%,  0 0, center; }
}

/* the point cloud is the focus: nodes glow, edges barely there */
SCOPE .view-content canvas {
  filter:
    drop-shadow(0 0 2px rgba(65,255,141,1))
    drop-shadow(0 0 7px rgba(65,255,141,.6))
    drop-shadow(0 0 18px rgba(65,255,141,.25));
}

.graph-view.color-fill            { color: #41FF8D; }
.graph-view.color-fill-focused    { color: #FFFFFF; }
.graph-view.color-fill-highlight  { color: #EAFFF3; }
.graph-view.color-fill-tag        { color: #1F8F4E; }
.graph-view.color-fill-attachment { color: #0C2A17; }
.graph-view.color-fill-unresolved { color: #FFB000; }
.graph-view.color-circle          { color: #EAFFF3; }
.graph-view.color-line            { color: rgba(65,255,141,.2); }
.graph-view.color-line-highlight  { color: #EAFFF3; }
.graph-view.color-arrow           { color: #41FF8D; }
.graph-view.color-text            { color: #B9FFD6; }

SCOPE .graph-controls {
  z-index: 4;
  background: rgba(1,3,1,.88);
  border: 1px solid #0C2A17;
  backdrop-filter: blur(3px);
}
"""


def static_css(css, force=False):
    """The two infinite background-position animations repaint rather than composite, and can
    hold Obsidian's GPU process near a full core for as long as the graph is open. --static,
    PHOSPHOR_GRAPH_STATIC=1 or the marker file ~/.config/phosphor/graph-static turns both
    into `none`; everything else renders as before. Default: the HUD animates."""
    if not (force or STATIC_MARKER.exists() or os.environ.get("PHOSPHOR_GRAPH_STATIC") == "1"):
        return css
    return (css.replace("animation: lattice-rain 60s linear infinite;", "animation: none; /* static */")
               .replace("animation: lattice-sweep 11s linear infinite;", "animation: none; /* static */"))


def render(vault, with_log=False, static=False):
    """The whole snippet for this vault, with {STAMP} still unfilled."""
    tk = load_ticker()
    rows = commits(vault) if with_log else []
    # (panel, position, size) back to front: the first layer paints on top
    market = tk is not None and tk is not BROKEN
    layers = [(header(vault_shape(vault), market=market), "left 22px top 18px", "auto")]
    readouts = ["the vault's shape"]
    if tk is not None:
        layers.append((ticker(tk), "right 72px top 18px", "auto"))  # clear of the graph controls
        readouts.append("the ticker")
    if rows:
        layers.append((vault_log(rows), "left 22px bottom 20px", "auto"))
        readouts.append("the vault's git log")
    layers.append((radar(), "center", "min(92vmin, 92%) auto"))
    parts = {
        "READOUTS": ", ".join(readouts),
        "RAIN": uri(rain(480, 960, 14, .2)),
        "GRID": uri(grid()),
        "LAYER_IMAGES": ",\n    ".join('url("%s")' % uri(s) for s, _, _ in layers),
        "LAYER_POSITIONS": ",\n    ".join(p for _, p, _ in layers),
        "LAYER_SIZES": ", ".join(z for _, _, z in layers),
    }
    css = CSS.replace("SCOPE", SCOPE)
    for k, v in parts.items():
        css = css.replace("{" + k + "}", v)
    return static_css(css, static)


def resolve_vault(arg=None):
    """The vault path from the argument, then $PHOSPHOR_VAULT, then ~/.config/phosphor/vault."""
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("PHOSPHOR_VAULT", "").strip()
    if env:
        return Path(env).expanduser()
    try:
        lines = VAULT_FILE.read_text().splitlines()
    except OSError:
        lines = []
    first = lines[0].strip() if lines else ""
    return Path(first).expanduser() if first else None


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="graph_hud.py",
        description="Render Obsidian's graph view as a Phosphor terminal HUD "
                    "(writes <vault>/" + SNIPPET + ").")
    ap.add_argument("vault", nargs="?",
                    help="vault folder; defaults to $PHOSPHOR_VAULT, then the first line of ~/.config/phosphor/vault")
    ap.add_argument("--log", action="store_true",
                    help="add a panel with the vault's recent git commits (off by default)")
    ap.add_argument("--static", action="store_true",
                    help="no rain or sweep animation (lighter on the GPU)")
    args = ap.parse_args(argv)

    vault = resolve_vault(args.vault)
    if vault is None:
        sys.exit("graph_hud: no vault. Pass its path, set PHOSPHOR_VAULT, "
                 "or put the path on the first line of ~/.config/phosphor/vault.")
    if not vault.is_dir():
        sys.exit("graph_hud: %s is not a folder." % vault)
    if not (vault / ".obsidian").is_dir():
        sys.exit("graph_hud: %s has no .obsidian folder, so it is not an Obsidian vault "
                 "(open it in Obsidian once to create one)." % vault)

    out = vault / SNIPPET
    css = render(vault, with_log=args.log, static=args.static)
    try:
        old = out.read_text()
    except OSError:
        old = ""
    strip = lambda s: re.sub(r"Updated .*?\.\n", "", s)
    if strip(old) == strip(css):
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(css.replace("{STAMP}", time.strftime("%Y-%m-%d %H:%M")))
    print("%s  %d KB" % (out, len(css) // 1024))
    return out


if __name__ == "__main__":
    main()
