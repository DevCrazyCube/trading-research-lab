#!/usr/bin/env python3
"""Fetch: Alpaca SIP daily bars for the US legs (raw + adjusted), Yahoo daily for the
home legs, FX, and country ETFs. Cached to disk; re-running is a no-op."""
import json, pathlib, sys, time, urllib.request, urllib.parse, random
sys.path.insert(0, "/home/anont/meme")
from scripts.trading_bot.data import load_env_credentials, _fetch_page
from scripts.t29_crosslist.xl_universe import (US_SYMBOLS, HOME_SYMBOLS, FX_SYMBOLS,
                                               COUNTRY_ETF)

OUT = pathlib.Path("/home/anont/meme/research/data/t29_crosslist_cache")
OUT.mkdir(parents=True, exist_ok=True)
START, END = "2015-06-01", "2026-08-18"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")


def alpaca(adjustment):
    key, secret = load_env_credentials()
    out, token, pages = {}, None, 0
    for i in range(0, len(US_SYMBOLS), 100):
        chunk = ",".join(US_SYMBOLS[i:i + 100])
        token = None
        while True:
            params = {"symbols": chunk, "timeframe": "1Day", "start": START, "end": END,
                      "limit": 10000, "feed": "sip", "adjustment": adjustment}
            if token:
                params["page_token"] = token
            p = _fetch_page("/v2/stocks/bars", params, key, secret)
            for sym, bars in (p.get("bars") or {}).items():
                out.setdefault(sym, []).extend(bars)
            pages += 1
            token = p.get("next_page_token")
            if not token:
                break
            if pages > 800:
                raise SystemExit("paging runaway")
    print("alpaca", adjustment, "pages", pages, "symbols", len(out), flush=True)
    return out


def yahoo_one(sym, tries=3):
    q = urllib.parse.urlencode({"period1": 1433116800, "period2": 1787000000,
                                "interval": "1d", "events": "div,split"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?{q}"
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            d = json.loads(urllib.request.urlopen(req, timeout=45).read())
            r = (d.get("chart") or {}).get("result")
            if not r:
                return None
            r = r[0]
            ts = r.get("timestamp") or []
            q0 = r["indicators"]["quote"][0]
            adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(ts)
            tz = r["meta"].get("exchangeTimezoneName", "")
            rows = []
            import datetime as dt
            for i, t in enumerate(ts):
                c = q0["close"][i]
                if c is None:
                    continue
                # local exchange calendar date
                off = r["meta"].get("gmtoffset", 0)
                d0 = dt.datetime.fromtimestamp(t + off, dt.timezone.utc).strftime("%Y-%m-%d")
                rows.append({"d": d0, "c": c, "a": adj[i] if adj[i] is not None else c,
                             "h": q0["high"][i], "l": q0["low"][i],
                             "v": q0["volume"][i] or 0})
            return {"tz": tz, "currency": r["meta"].get("currency"), "rows": rows}
        except Exception as e:
            if a == tries - 1:
                print("FAIL", sym, repr(e)[:120], flush=True)
                return None
            time.sleep(2 + 3 * a)
    return None


def yahoo_many(syms, path):
    if path.exists():
        out = json.loads(path.read_text())
    else:
        out = {}
    n = 0
    for s in syms:
        if s in out:
            continue
        r = yahoo_one(s)
        if r:
            out[s] = r
        n += 1
        if n % 10 == 0:
            path.write_text(json.dumps(out))
            print("  ...", n, "fetched,", len(out), "ok", flush=True)
        time.sleep(0.7 + random.random() * 0.6)
    path.write_text(json.dumps(out))
    print("wrote", path, len(out), "series", flush=True)


if __name__ == "__main__":
    for adj in ("raw", "all"):
        p = OUT / f"us_bars_{adj}.json"
        if p.exists():
            print("cached", p, flush=True)
        else:
            p.write_text(json.dumps(alpaca(adj)))
            print("wrote", p, flush=True)
    yahoo_many(HOME_SYMBOLS, OUT / "home_bars.json")
    yahoo_many(FX_SYMBOLS + sorted(set(COUNTRY_ETF.values())), OUT / "fx_etf_bars.json")
    print("DONE", flush=True)
