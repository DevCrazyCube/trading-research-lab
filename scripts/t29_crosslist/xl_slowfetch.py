#!/usr/bin/env python3
"""Slow, resumable, atomic Yahoo fetch. Yahoo rate-limits this host in short bursts;
pace ~1 req/3s, rotate query1/query2, back off hard on 429, write via tmp+rename so a kill
can never truncate the cache."""
import json, os, pathlib, sys, time, random, urllib.request, urllib.parse, datetime as dt

sys.path.insert(0, "/home/anont/meme")
from scripts.t29_crosslist.xl_universe import (HOME_SYMBOLS, FX_SYMBOLS, COUNTRY_ETF)

OUT = pathlib.Path("/home/anont/meme/research/data/t29_crosslist_cache")
UAS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
       "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
       "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"]
HOSTS = ["query1", "query2"]
_i = [0]


def fetch(sym):
    q = urllib.parse.urlencode({"period1": 1433116800, "period2": 1787000000,
                                "interval": "1d", "events": "div,split"})
    _i[0] += 1
    host = HOSTS[_i[0] % len(HOSTS)]
    url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": random.choice(UAS),
                                               "Accept": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=45).read())
    r = (d.get("chart") or {}).get("result")
    if not r:
        return None
    r = r[0]
    ts = r.get("timestamp") or []
    q0 = r["indicators"]["quote"][0]
    adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(ts)
    off = r["meta"].get("gmtoffset", 0)
    rows = []
    for i, t in enumerate(ts):
        c = q0["close"][i]
        if c is None:
            continue
        rows.append({"d": dt.datetime.fromtimestamp(t + off, dt.timezone.utc).strftime("%Y-%m-%d"),
                     "c": c, "a": adj[i] if adj[i] is not None else c,
                     "h": q0["high"][i], "l": q0["low"][i], "v": q0["volume"][i] or 0})
    if not rows:
        return None
    return {"tz": r["meta"].get("exchangeTimezoneName", ""),
            "currency": r["meta"].get("currency"), "rows": rows}


def save(path, d):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    os.replace(tmp, path)


for path, want in ((OUT / "fx_etf_bars.json", FX_SYMBOLS + sorted(set(COUNTRY_ETF.values()))),
                   (OUT / "home_bars.json", HOME_SYMBOLS)):
    d = {}
    if path.exists():
        try:
            d = json.loads(path.read_text())
        except Exception:
            d = {}
    delay = 3.0
    for rnd in range(8):
        missing = [s for s in want if s not in d]
        print(f"{path.name} round {rnd}: {len(missing)} missing (have {len(d)})", flush=True)
        if not missing:
            break
        got = 0
        for sym in missing:
            try:
                r = fetch(sym)
                if r:
                    d[sym] = r
                    got += 1
                    if got % 5 == 0:
                        save(path, d)
                delay = 2.5
            except Exception as e:
                if "429" in repr(e):
                    # Yahoo's limiter is a fixed cooldown window, not a rising penalty.
                    # Sleep it out once and resume at the base pace; multiplicative
                    # backoff just burns the window without buying anything.
                    save(path, d)
                    time.sleep(70)
                    delay = 2.5
                    continue
                print("  err", sym, repr(e)[:80], flush=True)
            time.sleep(delay + random.random())
        save(path, d)
        print(f"  round {rnd} recovered {got}, delay now {delay:.1f}", flush=True)
        if got == 0:
            time.sleep(180)
    save(path, d)
    print(path.name, "FINAL missing:", [s for s in want if s not in d], flush=True)
print("SLOWFETCH DONE", flush=True)
