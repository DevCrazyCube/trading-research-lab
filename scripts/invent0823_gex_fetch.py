#!/usr/bin/env python3
"""INVENT-0823 SINGLE-NAME & SECTOR DEALER GAMMA: free option cache builder.

Alpaca serves expired OPRA option daily bars from ~2024-02-01. There is no free
per-strike open-interest HISTORY anywhere, so we build the closest free proxy:
per-contract DAILY VOLUME accumulated over the [E-70d, E] life of each MONTHLY
expiry, per strike, calls and puts, for a liquid single-name + sector-ETF universe.

At any observation day t this yields, for the front monthly and the next monthly,
a cumulative-traded-volume-by-strike ladder -> an OI proxy -> a GEX proxy.

Writes research/data/inv0823_gex/<UND>/<YYYY-MM-DD>.json   (idempotent)
       research/data/inv0823_gex/_stock/<UND>.json         (daily bars, raw+adj)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

ROOT = "/home/anont/meme"
OUT = os.path.join(ROOT, "research/data/inv0823_gex")
STOCKD = os.path.join(OUT, "_stock")

SINGLE = ("AAPL MSFT NVDA TSLA AMZN META GOOGL AMD NFLX AVGO JPM BAC XOM CVX WMT "
          "COST CRM INTC MU PLTR COIN BA DIS UBER PYPL GS PFE JNJ T VZ ORCL QCOM "
          "CAT LLY").split()
SECTOR = "XLF XLE XLK XLV XLI XLP XLU XLB XLRE XLC SMH IWM QQQ DIA EEM".split()
UNIV = SINGLE + SECTOR

START = date(2024, 2, 1)
END = date(2026, 8, 21)
NSIDE = 20
REF_OFFSETS = (60, 25, 5)   # calendar days before expiry to anchor strike ladders
LOOKBACK = 70               # calendar days of contract history per expiry


def creds():
    env = {}
    for line in open(os.path.join(ROOT, ".env")):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    return {"APCA-API-KEY-ID": env["ALPACA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET_KEY"]}


H = creds()


def get(url, params, tries=7):
    u = url + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            r = urllib.request.Request(u, headers=H)
            return json.load(urllib.request.urlopen(r, timeout=90))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(2 ** i, 30))
                continue
            raise
        except Exception:
            time.sleep(min(2 ** i, 30))
    raise RuntimeError("give up: " + u[:200])


def stock_bars(sym, adjustment):
    out, tok = [], None
    while True:
        q = {"symbols": sym, "timeframe": "1Day", "start": "2023-11-01",
             "end": END.isoformat(), "limit": 10000, "adjustment": adjustment}
        if tok:
            q["page_token"] = tok
        d = get("https://data.alpaca.markets/v2/stocks/bars", q)
        out += (d.get("bars") or {}).get(sym, [])
        tok = d.get("next_page_token")
        if not tok:
            break
    return out


def load_stock(sym):
    p = os.path.join(STOCKD, sym + ".json")
    if os.path.exists(p):
        return json.load(open(p))
    d = {"raw": stock_bars(sym, "raw"), "adj": stock_bars(sym, "all")}
    json.dump(d, open(p, "w"))
    return d


def third_fridays(a, b):
    out = []
    y, m = a.year, a.month
    while date(y, m, 1) <= b:
        d = date(y, m, 15)
        while d.weekday() != 4:
            d += timedelta(days=1)
        if a <= d <= b:
            out.append(d)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def ladder(refs):
    """Multi-resolution strike grid.

    The listed increment is NOT knowable in advance: the same underlying carries a
    $1 ladder on one expiry and a $2.50 ladder on the next. A grid whose step is
    not a divisor of the true step silently drops most of the ladder -- the first
    pass used $5 for every $200+ name and got only $5 strikes; the second used $1
    and got only the multiples of $5 out of a $2.50 ladder. So: a FINE half-step
    grid over the near-money +/-5% band (a divisor of $1, $2.50 and $5 ladders
    alike) unioned with a COARSE 5x grid over +/-20% for the wings. Strikes that do
    not exist simply return no bars."""
    ks = set()
    for s in refs:
        fine = 0.5 if s < 250 else 2.5 if s < 1000 else 5.0
        for step, band in ((fine, 0.05), (5 * fine, 0.20)):
            k0 = round(s / step) * step
            n = int(band * s / step)
            for j in range(-n, n + 1):
                k = round(k0 + j * step, 2)
                if k > 0:
                    ks.add(round(k * 1000))
    return sorted(ks)


def occ(und, exp, cp, k_milli):
    return f"{und}{exp:%y%m%d}{cp}{k_milli:08d}"


def main():
    os.makedirs(STOCKD, exist_ok=True)
    exps = third_fridays(START, END)
    t0 = time.time()
    nreq = 0
    for und in UNIV:
        os.makedirs(os.path.join(OUT, und), exist_ok=True)
        try:
            sb = load_stock(und)
        except Exception as e:
            print(f"STOCKFAIL {und} {e}", flush=True)
            continue
        raw = [(b["t"][:10], b["c"]) for b in sb["raw"]]
        if not raw:
            print(f"NOBARS {und}", flush=True)
            continue
        dts = [r[0] for r in raw]
        for exp in exps:
            p = os.path.join(OUT, und, exp.isoformat() + ".json")
            if os.path.exists(p):
                continue
            refs = []
            for off in REF_OFFSETS:
                target = (exp - timedelta(days=off)).isoformat()
                i = 0
                for j, d in enumerate(dts):
                    if d <= target:
                        i = j
                    else:
                        break
                if dts[i] <= target:
                    refs.append(raw[i][1])
            if not refs:
                continue
            ks = ladder(refs)
            syms = [occ(und, exp, cp, k) for k in ks for cp in "CP"]
            st = (exp - timedelta(days=LOOKBACK)).isoformat()
            rec = {}
            ok = True
            for j in range(0, len(syms), 60):
                chunk = syms[j:j + 60]
                tok = None
                while True:
                    q = {"symbols": ",".join(chunk), "timeframe": "1Day",
                         "start": st, "end": exp.isoformat(), "limit": 10000,
                         "sort": "asc"}
                    if tok:
                        q["page_token"] = tok
                    try:
                        d = get("https://data.alpaca.markets/v1beta1/options/bars", q)
                    except Exception as e:
                        print(f"FAIL {und} {exp} {e}", flush=True)
                        ok = False
                        break
                    nreq += 1
                    for s, bs in (d.get("bars") or {}).items():
                        rec.setdefault(s, []).extend(
                            [b["t"][:10], b["v"], b["c"], b["o"], b["h"], b["l"], b["n"]]
                            for b in bs)
                    tok = d.get("next_page_token")
                    if not tok:
                        break
                if not ok:
                    break
            if not ok:
                continue
            json.dump({"und": und, "expiry": exp.isoformat(), "refs": refs,
                       "bars": rec}, open(p, "w"))
        print(f"done {und}  req={nreq}  elapsed={time.time()-t0:.0f}s", flush=True)
    print("ALLDONE", flush=True)


if __name__ == "__main__":
    main()
