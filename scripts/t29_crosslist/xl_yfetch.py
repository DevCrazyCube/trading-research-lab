#!/usr/bin/env python3
"""Yahoo daily-bar fetcher: verbose per-symbol log, atomic saves, resumable, guarded by
__main__ so importing it never starts a second crawl."""
import json, os, pathlib, sys, time, random, urllib.request, urllib.parse, datetime as dt

sys.path.insert(0, "/home/anont/meme")
OUT = pathlib.Path("/home/anont/meme/research/data/t29_crosslist_cache")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/125.0.0.0 Safari/537.36")
HOSTS = ["query1", "query2"]


def fetch(sym, i):
    q = urllib.parse.urlencode({"period1": 1433116800, "period2": 1787000000,
                                "interval": "1d", "events": "div,split"})
    url = (f"https://{HOSTS[i % 2]}.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(sym)}?{q}")
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    r = (d.get("chart") or {}).get("result")
    if not r:
        return None
    r = r[0]
    ts = r.get("timestamp") or []
    q0 = r["indicators"]["quote"][0]
    adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(ts)
    off = r["meta"].get("gmtoffset", 0)
    rows = []
    for j, t in enumerate(ts):
        c = q0["close"][j]
        if c is None:
            continue
        rows.append({"d": dt.datetime.fromtimestamp(t + off, dt.timezone.utc)
                     .strftime("%Y-%m-%d"), "c": c,
                     "a": adj[j] if adj[j] is not None else c,
                     "h": q0["high"][j], "l": q0["low"][j], "v": q0["volume"][j] or 0})
    if not rows:
        return None
    return {"tz": r["meta"].get("exchangeTimezoneName", ""),
            "currency": r["meta"].get("currency"), "rows": rows}


def save(path, d):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    os.replace(tmp, path)


def run(path, want):
    d = {}
    if path.exists():
        try:
            d = json.loads(path.read_text())
        except Exception:
            d = {}
    i = 0
    for rnd in range(5):
        missing = [s for s in want if s not in d]
        print(f"== {path.name} round {rnd}: {len(missing)} missing, have {len(d)}",
              flush=True)
        if not missing:
            break
        for sym in missing:
            i += 1
            t0 = time.time()
            try:
                r = fetch(sym, i)
                if r:
                    d[sym] = r
                    save(path, d)
                    print(f"ok   {sym:<16} {len(r['rows']):>5} rows "
                          f"{r['currency']} {time.time()-t0:.1f}s", flush=True)
                else:
                    print(f"none {sym}", flush=True)
                time.sleep(2.0 + random.random())
            except Exception as e:
                msg = repr(e)[:70]
                print(f"ERR  {sym:<16} {msg} {time.time()-t0:.1f}s", flush=True)
                time.sleep(45 if "429" in msg else 3)
    print(path.name, "FINAL missing:", [s for s in want if s not in d], flush=True)


if __name__ == "__main__":
    from scripts.t29_crosslist.xl_universe import (HOME_SYMBOLS, FX_SYMBOLS, COUNTRY_ETF)
    run(OUT / "fx_etf_bars.json", FX_SYMBOLS + sorted(set(COUNTRY_ETF.values())))
    run(OUT / "home_bars.json", HOME_SYMBOLS)
    print("YFETCH DONE", flush=True)
