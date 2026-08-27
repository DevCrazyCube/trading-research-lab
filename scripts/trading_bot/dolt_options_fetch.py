#!/usr/bin/env python3
"""
Detached fetcher for post-no-preference/options (DoltHub) via the free SQL API.

Access facts discovered empirically:
  - Only `date=` equality (leading PK col) is fast. Any act_symbol-only scan,
    COUNT, DISTINCT, or date-range query times out at the API's ~55s wall.
  - Responses cap at 1000 rows (RowLimit).
  - A per-(date, symbol) full-chain point query returns <=~200 rows in ~1.3s, always.

Strategy: weekly sampling across 2019-02..2026-08, ~50 liquid single names +
SPY/QQQ controls, one full-chain point query per (date, symbol). Underlying
open/close from the sibling post-no-preference/stocks ohlcv table (one query/date).

Cache: research/data/doltopts_cache/<DATE>.json  (resumable; skips done dates)
Research only. No orders, no money, no git.
"""
import json, os, sys, time, urllib.parse, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

OPT_API = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master?q="
STK_API = "https://www.dolthub.com/api/v1alpha1/post-no-preference/stocks/master?q="
CACHE = "/home/anont/meme/research/data/doltopts_cache"
os.makedirs(CACHE, exist_ok=True)

UNIV = ["AAPL","MSFT","AMZN","GOOGL","NVDA","TSLA","JPM","BAC","V","JNJ",
        "XOM","WMT","HD","KO","DIS","NFLX","CRM","ORCL","INTC","AMD",
        "QCOM","IBM","BA","CAT","GE","T","VZ","NKE","MCD","PFE",
        "MRK","UNH","CVX","COST","PEP","PG","CSCO","MMM","HON","GS",
        "MS","C","WFC","MA","ABBV","TXN","LOW","TGT","SBUX","ADBE",
        "SPY","QQQ"]

def q(api, sql, tries=4):
    url = api + urllib.parse.quote(sql)
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=70) as r:
                d = json.loads(r.read().decode())
            if d.get("query_execution_status") == "Success":
                return d.get("rows", [])
            # RowLimit still returns rows; treat as partial success for point queries
            if d.get("query_execution_status") == "RowLimit":
                return d.get("rows", [])
            # Error -> retry
        except Exception:
            pass
        time.sleep(1.5 * (i + 1))
    return None

def chain(sym, date):
    sql = (f"SELECT strike,call_put,expiration,bid,ask,vol,delta,gamma,vega,theta "
           f"FROM option_chain WHERE act_symbol='{sym}' AND date='{date}'")
    return q(OPT_API, sql)

def stocks(date):
    inlist = ",".join(f"'{s}'" for s in UNIV)
    sql = f"SELECT act_symbol,open,close,volume FROM ohlcv WHERE date='{date}' AND act_symbol IN ({inlist})"
    return q(STK_API, sql)

def resolve_date(target):
    """Probe target and nearby days for populated AAPL data; return first populated date str."""
    for off in (0, 1, -1, 2, -2):
        d = target + dt.timedelta(days=off)
        if d.weekday() >= 5:
            continue
        ds = d.isoformat()
        rows = q(OPT_API, f"SELECT delta FROM option_chain WHERE act_symbol='AAPL' AND date='{ds}' LIMIT 1")
        if rows:
            return ds
    return None

def fetch_date(target):
    ds = resolve_date(target)
    if ds is None:
        return (target.isoformat(), "empty")
    out = os.path.join(CACHE, ds + ".json")
    if os.path.exists(out):
        return (ds, "cached")
    opt = {}
    for sym in UNIV:
        rows = chain(sym, ds)
        if rows:
            opt[sym] = rows
    stk_rows = stocks(ds)
    stk = {r["act_symbol"]: {"open": r["open"], "close": r["close"], "volume": r["volume"]}
           for r in (stk_rows or [])}
    rec = {"date": ds, "options": opt, "stocks": stk}
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, out)
    return (ds, f"ok nsym={len(opt)} nstk={len(stk)}")

def main():
    start = dt.date(2019, 2, 13)
    end = dt.date(2026, 8, 19)
    # every Wednesday
    targets = []
    d = start
    while d <= end:
        if d.weekday() == 2:
            targets.append(d)
        d += dt.timedelta(days=1)
    print(f"[{dt.datetime.now()}] {len(targets)} weekly target dates, univ={len(UNIV)}", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_date, t): t for t in targets}
        for fu in as_completed(futs):
            ds, status = fu.result()
            done += 1
            if done % 10 == 0 or "ok" in status:
                print(f"[{done}/{len(targets)}] {ds} {status}", flush=True)
    print(f"[{dt.datetime.now()}] DONE {done} dates", flush=True)

if __name__ == "__main__":
    main()
