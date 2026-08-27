#!/usr/bin/env python3
"""Corrected H3 (cross-market internal consistency) collector -- SIMULTANEOUS books only.

The main collector snapshots each market at 50% of ITS OWN life, so sibling strikes in one event
are sampled at different wall-clock times -> spurious 'arbs'. This collector instead, per event,
pulls EVERY sibling market's book at ONE common timestamp t* inside the window where all legs are
simultaneously live. Two genuinely single-underlying structures:

  * NESTED thresholds  (KXMLBTOTAL 'Over N runs')  -> YES(strike) must be monotone decreasing.
  * PARTITION buckets  (KXHIGH* daily-high ranges) -> exactly one resolves YES; YES mids sum to ~1.

Free public Kalshi read only; NO orders/account/wallet. Writes one JSON ladder per line.
"""
from __future__ import annotations
import json, sys, time, datetime as dt, urllib.request, urllib.error

HOST = "https://api.elections.kalshi.com/trade-api/v2"
UA = "meme-research-predmarket (officialjoy04@gmail.com) read-only public-data reader"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/anont/meme/research/data/predmarket_structural/h3_ladders.jsonl"
EVENTS_PER_SERIES = int(sys.argv[2]) if len(sys.argv) > 2 else 130
NESTED = ["KXMLBTOTAL"]
PARTITION = ["KXHIGHNY", "KXHIGHLAX", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHDEN", "KXHIGHPHIL", "KXHIGHAUS"]
_LAST = [0.0]; MIN_INT = 0.30

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
    try: return float(x)
    except Exception: return None

def book_at(ser, tk, t):
    r = get(f"{HOST}/series/{ser}/markets/{tk}/candlesticks"
            f"?start_ts={t-300}&end_ts={t+300}&period_interval=1")
    cs = r.get("candlesticks", []) if isinstance(r, dict) else []
    best = None; bd = None
    for c in cs:
        yb = c.get("yes_bid") or {}; ya = c.get("yes_ask") or {}
        b = fnum(yb.get("close_dollars")); a = fnum(ya.get("close_dollars"))
        et = c.get("end_period_ts")
        if b is None or a is None or et is None: continue
        if not (0.0 <= b <= 1.0) or not (0.0 <= a <= 1.0) or a < b: continue
        d = abs(et - t)
        if bd is None or d < bd:
            bd = d; best = (b, a, et)
    return best

def collect_series(ser, kind, fout):
    # group settled markets by event
    ev = {}
    cur = ""; pages = 0
    while pages < 6:
        url = f"{HOST}/markets?status=settled&limit=200&series_ticker={ser}"
        if cur: url += "&cursor=" + cur
        d = get(url)
        if "_err" in d: break
        pages += 1
        for m in d.get("markets", []):
            if m.get("result") not in ("yes", "no"): continue
            ev.setdefault(m["event_ticker"], []).append(m)
        cur = d.get("cursor") or ""
        if not cur or len(ev) >= EVENTS_PER_SERIES * 3: break
    done = 0
    for etk, ms in ev.items():
        if done >= EVENTS_PER_SERIES: break
        if len(ms) < 3: continue
        opens = [ts(m["open_time"]) for m in ms]; closes = [ts(m["close_time"]) for m in ms]
        if any(x is None for x in opens + closes): continue
        lo = max(opens); hi = min(closes)
        if hi - lo < 120: continue          # need a real simultaneous-live window
        tstar = int(lo + 0.5 * (hi - lo))
        legs = []
        for m in ms:
            vol = fnum(m.get("volume_fp")) or 0.0
            bk = book_at(ser, m["ticker"], tstar)
            if not bk: continue
            b, a, bts = bk
            legs.append({"strike": m.get("floor_strike"), "cap": m.get("cap_strike"),
                         "sub": m.get("yes_sub_title"), "result": 1 if m["result"] == "yes" else 0,
                         "vol": vol, "bid": b, "ask": a, "mid": round((a + b) / 2, 4),
                         "spread": round(a - b, 4), "bts": bts})
        if len(legs) < 3: continue
        fout.write(json.dumps({"series": ser, "kind": kind, "event": etk,
                               "tstar": tstar, "n_legs": len(legs), "legs": legs}) + "\n")
        fout.flush()
        done += 1
    return done

def main():
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fout = open(OUT, "w")
    t0 = time.time()
    for ser in NESTED:
        n = collect_series(ser, "nested", fout)
        print(f"[nested {ser}] events={n} elapsed={int(time.time()-t0)}s", flush=True)
    for ser in PARTITION:
        n = collect_series(ser, "partition", fout)
        print(f"[partition {ser}] events={n} elapsed={int(time.time()-t0)}s", flush=True)
    fout.close()
    print(f"DONE elapsed={int(time.time()-t0)}s", flush=True)

if __name__ == "__main__":
    main()
