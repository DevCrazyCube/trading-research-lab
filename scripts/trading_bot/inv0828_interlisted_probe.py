#!/usr/bin/env python3
"""INVENT 2026-08-28 interlisted TSX/NYSE intraday measurability probe (pre-registered; stdlib only).
Reads NO return/PnL/sign. See research/trading_bot/INVENT_2026-08-28_interlisted_intraday.md."""
import json, math, statistics, sys, time, urllib.request, urllib.parse
from collections import defaultdict

PAIRS = [("RY.TO", "RY"), ("TD.TO", "TD"), ("ENB.TO", "ENB"), ("CNQ.TO", "CNQ"), ("SHOP.TO", "SHOP")]
FX = "CAD=X"
FLOOR_BP = 8.0
OUT = "research/trading_bot/INVENT_2026-08-28_interlisted_intraday.json"

def fetch(sym):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           f"?interval=1m&range=5d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.load(r)
    res = j["chart"]["result"][0]
    ts = res["timestamp"]
    close = res["indicators"]["quote"][0]["close"]
    out = {}
    for t, c in zip(ts, close):
        if c is not None and c > 0:
            out[t - (t % 60)] = float(c)
    time.sleep(0.7)
    return out, res["meta"].get("exchangeName"), res["meta"].get("gmtoffset")

def acf1(x):
    n = len(x)
    if n < 30:
        return None
    m = sum(x) / n
    v = sum((a - m) ** 2 for a in x)
    if v == 0:
        return None
    c = sum((x[i] - m) * (x[i - 1] - m) for i in range(1, n))
    return c / v

def main():
    fx, fxex, _ = fetch(FX)
    fx_keys = sorted(fx)
    def fx_at(t):
        # forward-fill FX up to 5 minutes
        for k in range(0, 6):
            if t - 60 * k in fx:
                return fx[t - 60 * k]
        return None
    results = {"pairs": {}, "fx_bars": len(fx), "fx_exchange": fxex, "floor_bp": FLOOR_BP,
               "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    med_rho, med_p95 = [], []
    for tsx, nyse in PAIRS:
        try:
            a, aex, _ = fetch(tsx)
            b, bex, _ = fetch(nyse)
        except Exception as e:
            results["pairs"][f"{tsx}/{nyse}"] = {"error": repr(e)}
            continue
        common = sorted(set(a) & set(b))
        by_day = defaultdict(list)
        for t in common:
            f = fx_at(t)
            if f is None:
                continue
            s = math.log(a[t] / f) - math.log(b[t])
            by_day[time.strftime("%Y-%m-%d", time.gmtime(t))].append((t, s))
        ds_all, dev_all, n_min = [], [], 0
        for d, rows in sorted(by_day.items()):
            rows.sort()
            ss = [s for _, s in rows]
            n_min += len(ss)
            med = statistics.median(ss)
            dev_all += [abs(s - med) * 1e4 for s in ss]
            for i in range(1, len(rows)):
                if rows[i][0] - rows[i - 1][0] == 60:  # consecutive minutes only
                    ds_all.append((rows[i][1] - rows[i - 1][1]) * 1e4)
        rho = acf1(ds_all)
        var_ds = statistics.pvariance(ds_all) if len(ds_all) > 1 else None
        var_e = (-rho * var_ds) if (rho is not None and rho < 0) else 0.0
        sigma_p = math.sqrt(max(0.0, var_ds - 2 * var_e)) if var_ds is not None else None
        dev_sorted = sorted(dev_all)
        p95 = dev_sorted[int(0.95 * (len(dev_sorted) - 1))] if dev_sorted else None
        r = {"tsx_exchange": aex, "nyse_exchange": bex, "sessions": len(by_day), "matched_minutes": n_min,
             "n_dS": len(ds_all), "sd_dS_bp": round(math.sqrt(var_ds), 2) if var_ds else None,
             "rho1_dS": round(rho, 3) if rho is not None else None,
             "sd_noise_bp": round(math.sqrt(var_e), 2) if var_ds else None,
             "sigma_persistent_per_min_bp": round(sigma_p, 2) if sigma_p is not None else None,
             "p95_abs_dev_from_session_median_bp": round(p95, 2) if p95 is not None else None,
             "median_abs_dev_bp": round(statistics.median(dev_all), 2) if dev_all else None,
             "mean_basis_bp_by_session": {d: round(statistics.median([s for _, s in rows]) * 1e4, 1)
                                          for d, rows in sorted(by_day.items())}}
        results["pairs"][f"{tsx}/{nyse}"] = r
        if rho is not None: med_rho.append(rho)
        if p95 is not None: med_p95.append(p95)
    results["median_rho1"] = round(statistics.median(med_rho), 3) if med_rho else None
    results["median_p95_dev_bp"] = round(statistics.median(med_p95), 2) if med_p95 else None
    k1 = results["median_rho1"] is not None and results["median_rho1"] <= -0.35
    k2 = results["median_p95_dev_bp"] is not None and results["median_p95_dev_bp"] < FLOOR_BP
    passed = (results["median_rho1"] is not None and results["median_rho1"] > -0.20
              and results["median_p95_dev_bp"] is not None and results["median_p95_dev_bp"] >= FLOOR_BP)
    results["verdict"] = {"K1_feed_measures_own_error": k1, "K2_below_friction_floor": k2, "PASS": passed,
                          "conclusion": ("DEAD" if (k1 or k2) else ("PASS_open_collector_task" if passed else "INDETERMINATE"))}
    json.dump(results, open(OUT, "w"), indent=1)
    print(json.dumps(results, indent=1))

if __name__ == "__main__":
    main()
