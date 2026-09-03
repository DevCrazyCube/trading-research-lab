#!/usr/bin/env python3
"""POSTURE C1 economics -- MEASURE the round trip, do not assume it.

Corwin-Schultz was tried first and rejected: on synthetic data with a known
2bp spread it returns ~36bp (the estimator's upward bias swamps a modern
equity spread). So the cost is measured straight off historical NBBO quotes
from the same SIP feed the panel is built from.

Round trip (cross the spread twice) = the full relative quoted spread.
"""
import json, os, random, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c1_measure_equity_skew as M

OUT = M.OUT
env = {}
for line in open("/home/anont/meme/.env"):
    line = line.strip()
    if line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
H = {"APCA-API-KEY-ID": env["ALPACA_API_KEY_ID"],
     "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET_KEY"]}
TIMES = ["15:00:00", "16:00:00", "17:00:00", "18:00:00", "19:00:00"]   # UTC, RTH

def quotes(syms, day, hhmmss):
    q = urllib.parse.urlencode({"symbols": ",".join(syms),
                                "start": f"{day}T{hhmmss}Z",
                                "end": f"{day}T{hhmmss[:6]}{int(hhmmss[6:])+3:02d}Z",
                                "limit": 5000, "feed": "sip", "sort": "asc"})
    for i in range(4):
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                "https://data.alpaca.markets/v2/stocks/quotes?" + q, headers=H), timeout=120)
            return json.loads(r.read()).get("quotes", {}) or {}
        except Exception:
            time.sleep(2 * (i + 1))
    return {}

def main():
    syms, dates, close, dv, uni, isetf = M.load()
    S, D = close.shape
    live = np.isfinite(close)
    dvf = np.where(np.isfinite(dv), dv, 0.0)
    cs = np.cumsum(dvf, axis=1)
    adv = np.full((S, D), np.nan)
    adv[:, 22:] = (cs[:, 21:-1] - cs[:, :-22]) / 21.0
    rng = random.Random(20260903)
    sample_days = list(range(63, D - 1, 63))
    jobs = []
    for j in sample_days:
        rank = np.where(np.isfinite(adv[:, j]) & live[:, j], adv[:, j], -1.0)
        top = np.argsort(-rank)[:500]
        top = [int(i) for i in top if rank[i] > 0]
        if len(top) < 100:
            continue
        pick = rng.sample(top, 60)
        day = str(dates[j])
        for t in TIMES:
            for b in range(0, len(pick), 30):
                jobs.append((day, t, [str(syms[i]) for i in pick[b:b + 30]], j))
    print(f"[cost] {len(jobs)} quote requests over {len(sample_days)} sample sessions", flush=True)
    rows = []
    def run(job):
        day, t, batch, j = job
        out = []
        for s, qs in quotes(batch, day, t).items():
            for x in qs:
                bp, ap = x.get("bp", 0), x.get("ap", 0)
                if bp > 0 and ap > bp:
                    out.append((day, s, (ap - bp) / ((ap + bp) / 2) * 1e4))
                    break
        return out
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(run, jobs):
            rows.extend(r)
    sp = np.array([r[2] for r in rows])
    yrs = np.array([r[0][:4] for r in rows])
    res = {
        "method": "historical NBBO from Alpaca SIP; first quote at each of 5 RTH "
                  "instants per sampled session; 60 random names from that session's "
                  "top-500 by trailing-21d dollar volume (point-in-time, delisted "
                  "names included)",
        "n_quote_observations": int(sp.size),
        "n_sample_sessions": len(set(r[0] for r in rows)),
        "relative_quoted_spread_bp": {
            "median": round(float(np.median(sp)), 3),
            "mean": round(float(sp.mean()), 3),
            "p25": round(float(np.percentile(sp, 25)), 3),
            "p75": round(float(np.percentile(sp, 75)), 3),
            "p90": round(float(np.percentile(sp, 90)), 3),
        },
        "round_trip_bp_median": round(float(np.median(sp)), 3),
        "round_trip_bp_mean": round(float(sp.mean()), 3),
        "by_year_median_bp": {y: round(float(np.median(sp[yrs == y])), 3)
                              for y in sorted(set(yrs.tolist()))},
        "note": "commissions at US retail brokers are $0; this is the spread component only",
    }
    print(json.dumps(res, indent=2))
    json.dump(res, open(f"{OUT}/cost_measured.json", "w"), indent=2)

if __name__ == "__main__":
    main()
