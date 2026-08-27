#!/usr/bin/env python3
"""Detached collector for the Kalshi STRUCTURAL edge study (research-only, free public data).

Walks the Kalshi public settled-markets feed (keyless read), builds a diverse cross-section of
RESOLVED binary markets, and for each pulls a tiny candlestick window to snapshot the tradeable
book (yes_bid / yes_ask) at 25% / 50% / 75% through the market's life -- i.e. genuinely
pre-resolution, tradeable prices, with the spread needed for a realistic cost model.

Writes one compact JSONL row per market to OUT. Memory-frugal: streams, never accumulates
candles, appends rows as it goes. Detach it; it prints progress to stdout.

NO orders, NO account, NO wallet -- GET public data only. Kalshi-only (CFTC-regulated, US-legal
for the owner). Polymarket is NOT touched here.
"""
from __future__ import annotations
import json, sys, time, datetime as dt, urllib.request, urllib.error

HOST = "https://api.elections.kalshi.com/trade-api/v2"
UA = "meme-research-predmarket (officialjoy04@gmail.com) read-only public-data reader"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/anont/meme/research/data/predmarket_structural/rows.jsonl"
PER_SERIES_CAP = int(sys.argv[2]) if len(sys.argv) > 2 else 220
MIN_VOL = 200.0          # contracts of real trading over the market's life
_LAST = [0.0]
MIN_INT = 0.30

# Curated liquid recurring settled series across categories (verified 2026-08-26). Diversity by
# design so no single series dominates the calibration curve. Kalshi-only.
SEED_SERIES = [
    # Sports (moneyline + totals + props) -- spread of probabilities, high liquidity
    "KXMLBGAME", "KXMLBTOTAL", "KXMLBKS", "KXMLBHIT", "KXNFLGAME", "KXWNBAGAME",
    # Crypto hourly/15m ranges -- many longshot & favorite strikes
    "KXBTC15M", "KXETH15M", "KXSOL15M", "KXBTCD",
    # Weather daily highs / rain -- range ladders (good for nested-threshold H3)
    "KXHIGHNY", "KXHIGHCHI", "KXHIGHLAX", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHDEN",
    "KXHIGHPHIL", "KXRAINNYC",
    # Financials / macro
    "KXINXU", "KXNASDAQ100U", "KXCPI", "KXFED",
]

def throttle():
    w = MIN_INT - (time.monotonic() - _LAST[0])
    if w > 0: time.sleep(w)
    _LAST[0] = time.monotonic()

def get(url, tries=4):
    for a in range(tries):
        throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(1.0 * (a + 1)); continue
            return {"_err": e.code}
        except Exception:
            time.sleep(1.0 * (a + 1))
    return {"_err": "fail"}

def ts(s):
    try: return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except Exception: return None

def fnum(x):
    try:
        v = float(x); return v
    except Exception:
        return None

def pick_period(life_min):
    if life_min <= 180: return 1
    if life_min <= 3 * 1440: return 60
    return 1440

def snap_from_candles(cs, target_ts):
    """nearest candle to target_ts with a valid two-sided book -> (mid, spread, book_ts)."""
    best = None; bestd = None
    for c in cs:
        yb = c.get("yes_bid") or {}; ya = c.get("yes_ask") or {}
        b = fnum(yb.get("close_dollars")); a = fnum(ya.get("close_dollars"))
        if b is None or a is None: continue
        if not (0.0 < b <= 1.0) or not (0.0 <= a <= 1.0): continue
        if a < b: continue
        et = c.get("end_period_ts")
        if et is None: continue
        d = abs(et - target_ts)
        if bestd is None or d < bestd:
            bestd = d; best = (round((a + b) / 2.0, 4), round(a - b, 4), et)
    return best

def process_market(m, fout):
    tk = m.get("ticker", "")
    res = m.get("result")
    if res not in ("yes", "no"):
        return False
    vol = fnum(m.get("volume_fp")) or 0.0
    if vol < MIN_VOL:
        return False
    ser = tk.split("-")[0]
    st = ts(m.get("open_time")); en = ts(m.get("close_time"))
    if st is None or en is None or en <= st:
        return False
    life_min = (en - st) / 60.0
    period = pick_period(life_min)
    # ONE candlestick call spanning the whole life; extract all three snapshots from it.
    r = get(f"{HOST}/series/{ser}/markets/{tk}/candlesticks"
            f"?start_ts={st}&end_ts={en}&period_interval={period}")
    cs = r.get("candlesticks", []) if isinstance(r, dict) else []
    snaps = {}
    for frac in (0.25, 0.50, 0.75):
        tgt = int(st + frac * (en - st))
        s = snap_from_candles(cs, tgt)
        if s:
            snaps[str(frac)] = {"mid": s[0], "spread": s[1], "book_ts": s[2],
                                "lead_sec": en - s[2]}
    if "0.5" not in snaps:
        return False
    row = {
        "ticker": tk, "series": ser, "event": m.get("event_ticker"),
        "result": 1 if res == "yes" else 0,
        "floor_strike": m.get("floor_strike"), "cap_strike": m.get("cap_strike"),
        "vol": vol, "open_ts": st, "close_ts": en, "life_min": round(life_min, 1),
        "snaps": snaps,
    }
    fout.write(json.dumps(row) + "\n"); fout.flush()
    return True

def main():
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fout = open(OUT, "w")
    kept = 0; per_series = {}; t0 = time.time()
    for ser in SEED_SERIES:
        cur = ""; sk = 0; pages = 0
        while sk < PER_SERIES_CAP and pages < 8:
            url = f"{HOST}/markets?status=settled&limit=200&series_ticker={ser}"
            if cur: url += "&cursor=" + cur
            d = get(url)
            if "_err" in d:
                print(f"{ser} feed err {d}", flush=True); break
            pages += 1
            ms = d.get("markets", [])
            if not ms: break
            for m in ms:
                if sk >= PER_SERIES_CAP: break
                try:
                    if process_market(m, fout):
                        kept += 1; sk += 1
                except Exception as e:
                    print("row err", m.get("ticker"), repr(e)[:80], flush=True)
            cur = d.get("cursor") or ""
            if not cur: break
        per_series[ser] = sk
        print(f"[{ser}] kept={sk} total={kept} elapsed={int(time.time()-t0)}s", flush=True)
    fout.close()
    print(f"DONE kept={kept} distinct_series={len([k for k,v in per_series.items() if v])} "
          f"elapsed={int(time.time()-t0)}s", flush=True)
    print("per series:", sorted(per_series.items(), key=lambda kv: -kv[1]), flush=True)

if __name__ == "__main__":
    main()
