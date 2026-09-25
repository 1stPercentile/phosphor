#!/usr/bin/env python3
"""Pip's window.

The band between the market board and Pip's room: the sky over wherever you
are. The sun and moon sit where they actually are, stars twinkle, clouds
drift, and the temperature sits in the corner. The weather is the market's:
clouds thicken with fear, rain falls when the market bleeds, a crash is a
storm.

Data is keyless: Open-Meteo for weather (fetched every 10 minutes), ipinfo
for a city-level location (cached daily; a `lat,lon` line in
~/.config/phosphor/location.txt overrides it), moon phase computed from the
epoch. Everything is baked once a minute; the motion (sun and moon crossing,
twinkle, cloud drift, rain) runs off the sidebar's clock between bakes.

Temperature is Celsius unless ~/.config/phosphor/units says `f`.
"""

import json
import math
import os
import time
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

CACHE = paths.cache("sky")
LOC = os.path.join(CACHE, "loc.json")
WX = os.path.join(CACHE, "wx.json")
OVERRIDE = os.path.join(paths.CONFIG, "location.txt")
UA = {"User-Agent": "phosphor/1"}

W = 40          # columns in the window
STARS = [2, 7, 12, 19, 24, 30, 36]
SKYLINE = "▂▃▅▃▂▇▅▂▃▆▃▂▂▅▃▇▂▃▅▂▃▂▅▃▂▃"

# phosphor
RULE, CHROME, LIVE, HOT, ALARM = "#0C2A17", "#1F8F4E", "#41FF8D", "#EAFFF3", "#FFB000"
DAYSKY = "#0A1F14"


def get(url, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save(path, obj):
    os.makedirs(CACHE, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


# ── data ──────────────────────────────────────────────────────────────
def location():
    try:
        with open(OVERRIDE) as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if "," in line:
                    lat, lon = (float(x) for x in line.split(",")[:2])
                    return {"lat": lat, "lon": lon, "city": "here", "at": time.time()}
    except (OSError, ValueError):
        pass
    loc = load(LOC)
    if loc and time.time() - loc.get("at", 0) < 86400:
        return loc
    try:
        d = get("https://ipinfo.io/json")
        lat, lon = (float(x) for x in d["loc"].split(","))
        loc = {"lat": lat, "lon": lon, "city": d.get("city", ""), "at": time.time()}
        save(LOC, loc)
        return loc
    except Exception:
        return loc or None


def weather(loc):
    wx = load(WX)
    if wx and time.time() - wx.get("at", 0) < 600:
        return wx
    if not loc:
        return wx
    try:
        d = get("https://api.open-meteo.com/v1/forecast"
                f"?latitude={loc['lat']}&longitude={loc['lon']}"
                "&current=temperature_2m,weather_code,cloud_cover,precipitation,is_day"
                "&daily=sunrise,sunset&timezone=auto&past_days=1&forecast_days=2"
                "&timeformat=unixtime")
        c = d["current"]
        wx = {
            "temp": c.get("temperature_2m"), "code": c.get("weather_code", 0),
            "cloud": c.get("cloud_cover", 0), "precip": c.get("precipitation", 0),
            "is_day": c.get("is_day", 1),
            "sunrise": d["daily"]["sunrise"], "sunset": d["daily"]["sunset"],
            "at": time.time(),
        }
        save(WX, wx)
    except Exception:
        pass
    return wx


ALPHA = os.path.join(CACHE, "alpha.json")


def alpha():
    """Market weather. This is what the window's clouds and rain encode, and
    what the tape under the skyline prints. Every source is keyless; any one
    of them failing just leaves its slot blank."""
    a = load(ALPHA)
    if a and time.time() - a.get("at", 0) < 300:
        return a
    a = dict(a or {})
    try:
        d = get("https://api.alternative.me/fng/?limit=1")["data"][0]
        a["fng"] = int(d["value"]); a["fng_word"] = d["value_classification"].lower()
    except Exception:
        pass
    try:
        g = get("https://api.coingecko.com/api/v3/global")["data"]
        a["btc_d"] = float(g["market_cap_percentage"]["btc"])
        a["mcap_24h"] = float(g["market_cap_change_percentage_24h_usd"])
    except Exception:
        pass
    try:
        prof = get("https://api.dexscreener.com/token-profiles/latest/v1")
        a["new_total"] = len(prof)
    except Exception:
        pass
    try:
        f = get("https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP")
        a["funding"] = float(f["data"][0]["fundingRate"]) * 100
    except Exception:
        a.pop("funding", None)
    a["at"] = time.time()
    save(ALPHA, a)
    return a


def moon_bucket(now):
    """0 new · 1 waxing crescent · 2 first quarter · 3 gibbous/full ·
    4 last quarter · 5 waning crescent."""
    ref = 947182440                     # 2000-01-06 18:14 UTC, a new moon
    age = ((now - ref) / 86400.0) % 29.530588
    f = age / 29.530588
    if f < 0.03 or f > 0.97:
        return 0
    if f < 0.22:
        return 1
    if f < 0.28:
        return 2
    if f < 0.72:
        return 3
    if f < 0.78:
        return 4
    return 5


def condition(code):
    if code == 0:
        return "clear"
    if code in (1, 2):
        return "cloudy"
    if code == 3:
        return "overcast"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 57:
        return "drizzle"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "storm"
    return "cloudy"


def refresh():
    """Called once a minute by the tick. Cheap unless a fetch is due."""
    loc = location()
    wx = weather(loc)
    return loc, wx


# ── swift ─────────────────────────────────────────────────────────────
def esc(t):
    return t.replace("\\", "\\\\").replace('"', '\\"')


def q(t):
    return f'"{esc(t)}"'


def func(name, rtype, track, default, fmt=lambda v: str(v)):
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


def sun_position(wx, now):
    """Where the sun or moon is across the window, and whether it's day.
    frac 0..1 across the sky; edge rows near the horizon."""
    rises, sets = wx.get("sunrise") or [], wx.get("sunset") or []
    if not rises or not sets:
        h = time.localtime(now).tm_hour
        return (6 <= h < 20), 0.5
    for r, s in zip(rises, sets):
        if r <= now < s:
            return True, (now - r) / max(1, s - r)
    # night: between a sunset and the next sunrise
    for i, s in enumerate(sets):
        nxt = rises[i + 1] if i + 1 < len(rises) else s + 12 * 3600
        if s <= now < nxt:
            return False, (now - s) / max(1, nxt - s)
    return bool(wx.get("is_day", 1)), 0.5


def render():
    now = time.time()
    loc, wx = refresh()

    day, frac = sun_position(wx, now)
    col = max(0, min(W - 1, int(frac * (W - 1))))
    low = frac < 0.15 or frac > 0.85            # near the horizon: row 2
    stale = (now - wx.get("at", 0)) > 900 if wx else True

    cond = condition(wx.get("code", 0)) if wx else "waiting"
    al = alpha()
    fng = al.get("fng")
    m24 = al.get("mcap_24h")
    # clouds thicken with fear; rain falls when the market bleeds; a crash is
    # a storm. real sun, moon and stars stay — that part is the actual sky.
    if fng is None:
        clouds = round((wx.get("cloud", 0) or 0) / 25) if wx else 0
    else:
        clouds = 4 if fng < 25 else (3 if fng < 45 else (2 if fng < 55 else (1 if fng < 75 else 0)))
    precip = 0.0 if m24 is None else (0.0 if m24 > -2 else (0.5 if m24 > -5 else (3.0 if m24 > -8 else 6.0)))
    snow = False
    storm = m24 is not None and m24 <= -8
    body = "●◗◑●◐◖"[moon_bucket(now)] if not day else "☼"
    body_col = HOT if day else LIVE
    if not day and moon_bucket(now) == 0:
        body = " "

    # ── row 1 (sky) and row 2 (clouds/horizon), 60 frames each ──
    r1, r2 = [], []
    for s in range(60):
        a = [" "] * W
        b = [" "] * W
        if not day:
            for c in STARS:
                if c in (2, 19, 30):
                    a[c] = "˙" if s % 2 else "·"
                elif c in (7, 24, 36):
                    a[c] = "·" if s % 2 else "˙"
                else:
                    a[c] = " " if s % 10 == 7 else "·"
        # clouds drift one column every ten seconds
        shift = (int(now) // 10 + s // 10) % W
        for i in range(min(4, clouds)):
            glyph = "▄▀▀▄▀" if i % 2 == 0 else "▀▄▄▀"
            base = [1, 11, 22, 31][i]
            for k, ch in enumerate(glyph):
                b[(base + k + shift) % W] = ch
        # rain / snow falls
        if precip > 0 and not storm or snow:
            step = 6 if precip < 1 else (4 if precip < 4 else 2)
            off = (s // 2 if snow else s) % 3
            gl = "·" if snow else "╵"
            for c in range(W):
                if (c + off) % step == 0:
                    if a[c] == " ":
                        a[c] = gl
                    if b[c] == " ":
                        b[c] = gl
        # sun / moon
        if low:
            b[col] = body
        else:
            a[col] = body
        r1.append("".join(a))
        r2.append("".join(b))

    # lightning: rows go hot on two frames a minute
    flash = [HOT if (storm and s in (17, 41)) else CHROME for s in range(60)]

    temp = wx.get("temp") if wx else None
    fahrenheit = paths.setting("units", "c").lower().startswith("f")
    tempt = "—°" if temp is None else (f"{round(temp * 9 / 5 + 32)}°" if fahrenheit else f"{round(temp)}°")
    word = "stale" if stale and wx else (f"{al.get('fng_word', cond)} {fng}" if fng is not None else cond)
    tcol = ALARM if (stale and wx) else LIVE
    wcol = ALARM if (stale and wx) else (
        "#FF4D4D" if (fng is not None and fng < 30) else ("#41FF8D" if (fng is not None and fng > 70) else CHROME))
    if not wx:
        tempt, tcol = "—°", CHROME
        if fng is None:
            word, wcol = "waiting", CHROME

    def sgn(v, fmt):
        return ("#41FF8D" if v >= 0 else "#FF4D4D"), fmt.format(v)
    tape = []
    if al.get("btc_d") is not None:
        tape += [("#1F8F4E", "btc.d "), ("#41FF8D", f"{al['btc_d']:.1f}")]
    if m24 is not None:
        c, t = sgn(m24, "{:+.1f}%")
        tape += [("#1F8F4E", "  mkt "), (c, t)]
    if al.get("funding") is not None:
        c, t = sgn(al["funding"], "{:+.3f}%")
        tape += [("#1F8F4E", "  fund "), (c, t)]
    if al.get("new_total") is not None:
        tape += [("#1F8F4E", "  new "), ("#41FF8D", f"{al['new_total']}")]
    tape_swift = "\n".join(
        f'                Text("{esc(t)}").foregroundColor("{c}")'
        f'.font(.system(size: 9, design: .monospaced)).lineLimit(1).fixedSize()'
        for c, t in tape) or '                Text(" ")'

    def split(rows):
        return ([r[:col] for r in rows], [r[col] for r in rows], [r[col + 1:] for r in rows])
    l1, m1, rr1 = split(r1)
    l2, m2, rr2 = split(r2)
    funcs = [
        func("skyR1L", "String", l1, l1[0], q), func("skyR1M", "String", m1, m1[0], q),
        func("skyR1R", "String", rr1, rr1[0], q),
        func("skyR2L", "String", l2, l2[0], q), func("skyR2M", "String", m2, m2[0], q),
        func("skyR2R", "String", rr2, rr2[0], q),
        func("skyFlash", "String", flash, CHROME, q),
    ]
    m1_col = body_col if not low else CHROME
    m2_col = body_col if low else CHROME
    sky_fill = DAYSKY if day else "#020703"

    return "\n".join(funcs) + f'''

    // ═══ Pip's window ═════════════════════════════════════════════════
    // The real sky; the weather is the market. No fixed heights and no
    // stroked overlay inside here: the host spreads and overflows both.
    // Natural sizing on a background panel is what lays out.
    VStack(alignment: .leading, spacing: 0) {{
    VStack(alignment: .leading, spacing: 4) {{
        VStack(alignment: .leading, spacing: 0) {{
            HStack(spacing: 0) {{
                Text(skyR1L(clock.second)).foregroundColor(skyFlash(clock.second))
                    .font(.system(size: 10, design: .monospaced)).lineLimit(1).fixedSize()
                Text(skyR1M(clock.second)).foregroundColor("{m1_col}")
                    .font(.system(size: 10, design: .monospaced)).lineLimit(1).fixedSize()
                Text(skyR1R(clock.second)).foregroundColor(skyFlash(clock.second))
                    .font(.system(size: 10, design: .monospaced)).lineLimit(1).fixedSize()
            }}
            HStack(spacing: 0) {{
                Text(skyR2L(clock.second)).foregroundColor(skyFlash(clock.second))
                    .font(.system(size: 10, design: .monospaced)).lineLimit(1).fixedSize()
                Text(skyR2M(clock.second)).foregroundColor("{m2_col}")
                    .font(.system(size: 10, design: .monospaced)).lineLimit(1).fixedSize()
                Text(skyR2R(clock.second)).foregroundColor(skyFlash(clock.second))
                    .font(.system(size: 10, design: .monospaced)).lineLimit(1).fixedSize()
            }}
        }}
        .padding(.horizontal, 4).padding(.vertical, 2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background("{sky_fill}")
        .cornerRadius(4)

        HStack(spacing: 0) {{
            Text("{SKYLINE}").foregroundColor("{RULE}")
                .font(.system(size: 10, design: .monospaced)).lineLimit(1).fixedSize()
            Spacer(minLength: 2)
            HStack(spacing: 4) {{
                Text("{tempt}").foregroundColor("{tcol}")
                    .font(.system(size: 10, design: .monospaced)).bold()
                Text("{word}").foregroundColor("{wcol}")
                    .font(.system(size: 10, design: .monospaced))
            }}
        }}

        // the tape: dominance, market cap, funding, fresh listings
        HStack(spacing: 0) {{
{tape_swift}
            Spacer(minLength: 0)
        }}
        .padding(.top, 1)
    }}
    Spacer(minLength: 0)
    }}
    .padding(6)
    .frame(maxWidth: .infinity, height: 114, alignment: .topLeading)
    .background("#050D08")
    .cornerRadius(8)
    .overlay {{ RoundedRectangle(cornerRadius: 8).stroke("#1F8F4E", lineWidth: 1) }}
    .padding(.horizontal, 10)
    .padding(.top, 2)
    .padding(.bottom, 0)'''


if __name__ == "__main__":
    print(render()[:400])
