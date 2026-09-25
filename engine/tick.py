#!/usr/bin/env python3
"""The minute tick: fetch prices, then re-bake the cmux sidebar.

The cmux sidebar runtime has no network, and neither does a prompt that has
to stay instant. So nothing fetches on demand: this runs on a timer (launchd,
every 60 s), writes one small JSON file, and everything else reads that file.

Watchlist: ~/.config/phosphor/tokens.txt (falls back to config/tokens.txt).
CoinGecko and Dexscreener need no key; a tick uses a handful of requests.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

TOKENS = paths.config_file("tokens.txt")
CACHE_DIR = paths.CACHE
CACHE = os.path.join(CACHE_DIR, "ticker.json")
LINE = os.path.join(CACHE_DIR, "ticker.line")
DEX_API = "https://api.dexscreener.com/token-pairs/v1/{chain}/{addr}"
CG_API = ("https://api.coingecko.com/api/v3/simple/price"
          "?ids={ids}&vs_currencies=usd&include_24hr_change=true"
          "&include_market_cap=true&include_24hr_vol=true")
TIMEOUT = 8
ANCHORS = os.path.join(CACHE_DIR, "anchors.json")
CG_HISTORY = ("https://api.coingecko.com/api/v3/coins/{id}/history"
              "?date={date}&localization=false")


def month_anchor(sym, cg_id, anchors):
    """The price at 00:00 UTC on the 1st of this month, fetched once per
    symbol per month and cached, so the board can say whether the month is
    net up or down in dollars. CoinGecko history is keyless; one call per
    symbol per month is nothing."""
    if not cg_id:
        return None
    key = time.strftime("%Y-%m")
    month = anchors.setdefault(key, {})
    if sym in month:
        return month[sym]
    try:
        data = get_json(CG_HISTORY.format(id=cg_id, date=time.strftime("01-%m-%Y")))
        px = float(data["market_data"]["current_price"]["usd"])
    except Exception:
        return None            # try again next poll; never fabricate one
    finally:
        time.sleep(1.5)        # history is rate-limited harder than price;
                               # this runs at most once per symbol per month
    month[sym] = px
    return px


def read_tokens(path):
    """Returns (majors, dex). Unparseable lines are skipped, not fatal —
    a typo in the watchlist should cost one row, not the whole board."""
    majors, dex = [], []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                p = line.split()
                if p[0].upper() == "CG" and len(p) == 3:
                    majors.append({"symbol": p[1], "id": p[2]})
                elif p[0].upper() == "DEX" and len(p) in (4, 5):
                    dex.append({"symbol": p[1], "chain": p[2], "address": p[3],
                                "id": p[4] if len(p) == 5 else None})
    except FileNotFoundError:
        pass
    return majors, dex


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "phosphor/1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def fetch_majors(majors):
    """One request for every major, not one each."""
    if not majors:
        return [], []
    ids = ",".join(m["id"] for m in majors)
    data = get_json(CG_API.format(ids=ids))
    rows, errors = [], []
    for m in majors:
        d = data.get(m["id"])
        if not d:
            errors.append(f"{m['symbol']}: not returned")
            continue
        rows.append({
            "symbol": m["symbol"],
            "name": m["id"].replace("-", " ").title(),
            "price": d.get("usd"),
            "mcap": d.get("usd_market_cap"),
            "change24": d.get("usd_24h_change"),
            "vol24": d.get("usd_24h_vol"),
            "liq": None,
            "url": f"https://www.coingecko.com/en/coins/{m['id']}",
        })
    return rows, errors


def deepest_pair(pairs):
    """Whichever pair holds the most liquidity is the one that sets the price."""
    best, best_liq = None, -1.0
    for p in pairs or []:
        liq = ((p.get("liquidity") or {}).get("usd")) or 0.0
        try:
            liq = float(liq)
        except (TypeError, ValueError):
            liq = 0.0
        if liq > best_liq:
            best, best_liq = p, liq
    return best


def fetch(tok):
    data = get_json(DEX_API.format(chain=tok["chain"], addr=tok["address"]))
    pairs = data if isinstance(data, list) else data.get("pairs")
    p = deepest_pair(pairs)
    if not p:
        return None

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "symbol": tok["symbol"],
        "name": (p.get("baseToken") or {}).get("name"),
        "price": num(p.get("priceUsd")),
        "mcap": num(p.get("marketCap")) or num(p.get("fdv")),
        "change24": num((p.get("priceChange") or {}).get("h24")),
        "vol24": num((p.get("volume") or {}).get("h24")),
        "liq": num((p.get("liquidity") or {}).get("usd")),
        "url": p.get("url"),
    }


def load_anchors():
    try:
        with open(ANCHORS) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def previous_rows():
    try:
        with open(CACHE) as fh:
            return {r["symbol"]: r for r in json.load(fh).get("rows", [])}
    except (OSError, ValueError, KeyError):
        return {}


def main():
    majors, dex = read_tokens(TOKENS)
    rows, errors = [], []
    anchors = load_anchors()
    prev = previous_rows()

    try:
        mrows, merrs = fetch_majors(majors)
        rows.extend(mrows)
        errors.extend(merrs)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        errors.append(f"majors: {type(e).__name__}")

    for r, m in zip(rows, majors):
        r["cg_id"] = m["id"]
    for tok in dex:
        try:
            row = fetch(tok)
            if row:
                row["cg_id"] = tok.get("id")
                rows.append(row)
            else:
                errors.append(f"{tok['symbol']}: no pair")
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            errors.append(f"{tok['symbol']}: {type(e).__name__}")

    # A source that fails this minute must not blank the board. Carry the
    # last good row forward, marked stale, in watchlist order.
    got = {r["symbol"]: r for r in rows}
    order = [m["symbol"] for m in majors] + [t["symbol"] for t in dex]
    merged = []
    for sym in order:
        if sym in got:
            merged.append(got[sym])
        elif sym in prev:
            old = dict(prev[sym]); old["stale"] = True
            merged.append(old)
    rows = merged

    # month-to-date, in dollars: whether the month is up or down.
    # History is rate-limited harder than price, so at most ONE new anchor is
    # fetched per poll; the rest fill in over the next few minutes and are
    # then cached for the month.
    fetched = 0
    for r in rows:
        cg = r.pop("cg_id", None)
        key = time.strftime("%Y-%m")
        cached = anchors.get(key, {}).get(r["symbol"])
        if cached is None and (fetched >= 1 or errors):
            a = None
        else:
            a = month_anchor(r["symbol"], cg, anchors)
            if cached is None and a is not None:
                fetched += 1
        a = a if a is not None else anchors.get(key, {}).get(r["symbol"])
        r["mtd_anchor"] = a
        r["mtd"] = (r["price"] - a) if (a and r.get("price") is not None) else None
        r["mtd_pct"] = ((r["price"] / a - 1) * 100) if (a and r.get("price")) else None

    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = ANCHORS + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(anchors, fh)
    os.replace(tmp, ANCHORS)
    payload = {"at": int(time.time()), "rows": rows, "errors": errors}
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    os.replace(tmp, CACHE)          # readers never see a half-written file

    # Pre-render the banner line here so opening a terminal costs a `cat`
    # rather than a Python start-up.
    try:
        import render
        tmp = LINE + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(render.line(payload) + "\n")
        os.replace(tmp, LINE)
    except Exception:
        pass                        # the board still works without the line

    # Bake the same numbers into the cmux sidebar. Saving the file is what
    # updates it: the sidebar cannot fetch anything itself.
    try:
        import render_sidebar
        render_sidebar.main()
    except Exception as e:
        print(f"sidebar: {type(e).__name__}: {e}", file=sys.stderr)

    if errors and not rows:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
