#!/usr/bin/env python3
"""POSTURE C1 -- survivorship-complete US equity daily panel fetcher.

NEW FILE. Touches nothing in arena/. Read-only against Alpaca market data.

Universe   : point-in-time union of every symbol appearing in the local FINRA
             RegSHO daily short-volume archive (2018-08-01 .. 2026-08-14, 2020
             sessions). A symbol that traded on any day is in the universe
             whether or not it exists today -> survivorship-complete.
Prices     : Alpaca /v2/stocks/bars, feed=sip, adjustment=all. Alpaca serves
             full history for delisted tickers (verified: TWTR, SIVB, FRC, ATVI,
             VMW all return bars).
Two stages : stage1 monthly bars for the whole universe (cheap liquidity
             prescreen), stage2 daily bars for everything that ever clears the
             prescreen.
"""
import hashlib, json, os, sys, time, urllib.request, urllib.parse, gzip, glob
from concurrent.futures import ThreadPoolExecutor

OUT = os.environ.get("C1_OUT", "/home/anont/meme/research/postures/c1_equity_skew")
os.makedirs(OUT, exist_ok=True)
START, END = "2018-08-01", "2026-08-14"

def _env():
    e = {}
    for line in open("/home/anont/meme/.env"):
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        e[k.strip()] = v.strip().strip('"').strip("'")
    return e
_E = _env()
HDR = {"APCA-API-KEY-ID": _E["ALPACA_API_KEY_ID"],
       "APCA-API-SECRET-KEY": _E["ALPACA_API_SECRET_KEY"],
       "accept": "application/json"}

def api(params, tries=6):
    url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as ex:
            if ex.code == 400:
                raise
            if ex.code == 429:
                time.sleep(3 * (i + 1)); continue
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    print("[warn] api gave up: " + url[:120], flush=True)
    return {"bars": {}, "next_page_token": None}

def pull(syms, timeframe):
    """Return {sym: [bars]} for a batch, splitting on 400s (bad tickers)."""
    out = {}
    p = {"symbols": ",".join(syms), "timeframe": timeframe, "start": START,
         "end": END, "limit": 10000, "feed": "sip", "adjustment": "all",
         "sort": "asc"}
    try:
        while True:
            d = api(p)
            for k, v in (d.get("bars") or {}).items():
                out.setdefault(k, []).extend(v)
            tok = d.get("next_page_token")
            if not tok:
                break
            p["page_token"] = tok
    except urllib.error.HTTPError:
        if len(syms) == 1:
            return {}                      # ticker Alpaca refuses
        h = len(syms) // 2
        out.update(pull(syms[:h], timeframe))
        out.update(pull(syms[h:], timeframe))
    return out

def universe():
    root = "/home/anont/meme/research/data/t16_panels/finra_regsho_daily/raw"
    seen = {}
    for d in sorted(glob.glob(root + "/session=*")):
        fs = glob.glob(d + "/*.csv.gz")
        if not fs:
            continue
        day = d[-10:]
        with gzip.open(fs[0], "rt") as fh:
            next(fh)
            for line in fh:
                s = line.split(",", 2)[1]
                r = seen.setdefault(s, [day, day, 0])
                r[1] = day; r[2] += 1
    return seen

def stage1():
    seen = universe()
    json.dump(seen, open(f"{OUT}/universe_regsho.json", "w"))
    # RegSHO prints warrants/units/preferreds as XXX/WS, XXX/U, XXX/PB. Alpaca
    # rejects those and each rejection triggers a bisect storm. Keep plain
    # alphabetic tickers only -- that is the common-stock/ETF universe anyway.
    syms = sorted(s for s in seen if s.isalpha() and s.isupper())
    print(f"[stage1] dropped {len(seen)-len(syms)} non-alpha tickers "
          f"(warrants/units/preferreds)", flush=True)
    print(f"[stage1] universe symbols = {len(syms)}", flush=True)
    B, res, t0 = 120, {}, time.time()
    batches = [syms[i:i + B] for i in range(0, len(syms), B)]
    done = [0]
    os.makedirs(f"{OUT}/monthly", exist_ok=True)
    def job(bt):
        # NOTE: str.hash() is randomised per process; use a stable digest so the
        # checkpoint actually resumes instead of silently refetching.
        fp = f"{OUT}/monthly/m_{hashlib.sha1(bt[0].encode()).hexdigest()[:8]}_{len(bt)}.json.gz"
        if os.path.exists(fp):
            done[0] += 1
            with gzip.open(fp, "rt") as fh:
                return json.load(fh)
        r = pull(bt, "1Month")
        peak = {k: max((b["v"] * b["vw"]) / 21.0 for b in v) if v else 0.0
                for k, v in r.items()}
        with gzip.open(fp + ".tmp", "wt") as fh:
            json.dump(peak, fh)
        os.replace(fp + ".tmp", fp)
        r = peak
        done[0] += 1
        if done[0] % 20 == 0:
            print(f"[stage1] batch {done[0]}/{len(batches)} {time.time()-t0:.0f}s", flush=True)
        return r
    with ThreadPoolExecutor(max_workers=10) as ex:
        for r in ex.map(job, batches):
            res.update(r)
    liq = res
    json.dump(liq, open(f"{OUT}/stage1_peak_adv.json", "w"))
    print(f"[stage1] done syms_with_data={len(liq)} elapsed={time.time()-t0:.0f}s", flush=True)
    return liq

def stage2(thresh=8e5):
    liq = json.load(open(f"{OUT}/stage1_peak_adv.json"))
    syms = sorted([s for s, v in liq.items() if v >= thresh])
    print(f"[stage2] prescreen peak_adv>=${thresh:,.0f} -> {len(syms)} symbols", flush=True)
    B, t0 = 60, time.time()
    os.makedirs(f"{OUT}/daily", exist_ok=True)
    batches = [(i, syms[i:i + B]) for i in range(0, len(syms), B)]
    done = [0]
    def job(arg):
        i, chunk = arg
        fp = f"{OUT}/daily/part_{i:06d}.json.gz"
        done[0] += 1
        if os.path.exists(fp):
            return
        d = pull(chunk, "1Day")
        tmp = fp + ".tmp"
        with gzip.open(tmp, "wt") as fh:
            json.dump({k: [[b["t"][:10], b["c"], b["v"], b["vw"], b["h"], b["l"]] for b in v]
                       for k, v in d.items()}, fh)
        os.replace(tmp, fp)
        if done[0] % 10 == 0:
            print(f"[stage2] batch {done[0]}/{len(batches)} {time.time()-t0:.0f}s", flush=True)
    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(job, batches))
    print(f"[stage2] done {time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "stage1"):
        stage1()
    if what in ("all", "stage2"):
        stage2()
