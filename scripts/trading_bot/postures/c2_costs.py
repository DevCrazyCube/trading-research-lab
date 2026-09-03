"""POSTURE C2 economics: round-trip cost per instrument, computed from published
exchange contract specs times a live price from the local free-data cache.

Nothing here is assumed: tick size and contract size are exchange specs (cited in
the report); the price is the last close in research/data/c2_cache. Round-trip
spread cost of crossing a one-tick-wide book = exactly one tick.
"""
import json
import os

import numpy as np

CACHE = "/home/anont/meme/research/data/c2_cache"

# (label, contract size, tick value $, price source, price multiplier for notional)
# CME/CBOT published specs.
SPECS = [
    # Euro FX futures 6E: 125,000 EUR, min tick 0.00005 USD/EUR = $6.25
    ("CME 6E (EUR/USD future)", "fx_g10", "EUR", 125000.0, 6.25, "price*size"),
    # 10Y T-Note ZN: $100,000 face, tick 1/2 of 1/32 pt = $15.625; quote in points
    ("CBOT ZN (10y note future)", None, None, 1000.0, 15.625, "px_points"),
    ("CBOT ZF (5y note future)", None, None, 1000.0, 7.8125, "px_points"),
    ("CBOT ZT (2y note future)", None, None, 2000.0, 7.8125, "px_points"),
]


def last_close(panel, sym):
    z = np.load(os.path.join(CACHE, panel + ".npz"), allow_pickle=True)
    syms = [str(s) for s in z["syms"]]
    v = z["px"][:, syms.index(sym)]
    v = v[~np.isnan(v)]
    return float(v[-1])


def ts_last(sym):
    import datetime
    p = "/home/anont/meme/research/data/ts_cache/raw/%s.json" % sym
    d = json.load(open(p))["chart"]["result"][0]
    c = [x for x in d["indicators"]["quote"][0]["close"] if x is not None]
    return float(c[-1])


def main():
    rows = []

    # --- CME 6E Euro FX future
    eurusd = last_close("fx_g10", "EUR")     # USD per EUR, FRED DEXUSEU
    notional = 125000.0 * eurusd
    bp = 1e4 * 6.25 / notional
    rows.append(("CME 6E Euro FX future", eurusd, notional, 6.25, bp))

    # --- CBOT Treasury futures: quoted in points of $100,000 (ZT: $200,000) face
    for sym, face, tick, name in (("ZN=F", 100000.0, 15.625, "CBOT ZN 10y"),
                                  ("ZF=F", 100000.0, 7.8125, "CBOT ZF 5y"),
                                  ("ZT=F", 200000.0, 7.8125, "CBOT ZT 2y"),
                                  ("ZB=F", 100000.0, 31.25, "CBOT ZB 30y")):
        px = ts_last(sym)                    # points, e.g. 112.34
        notional = face * px / 100.0
        bp = 1e4 * tick / notional
        rows.append((name, px, notional, tick, bp))

    print("%-24s %10s %14s %9s %10s" % ("instrument", "last px", "notional $",
                                        "1 tick $", "RT bp"))
    for n, px, no, tk, bp in rows:
        print("%-24s %10.4f %14.0f %9.4f %10.3f" % (n, px, no, tk, bp))

    # gaps measured in c2_analyze
    res = json.load(open(os.path.join(CACHE, "c2_results.json")))
    by = {r["label"]: r for r in res if r.get("gate1") == "PASS"}
    fxrt = rows[0][4]
    znrt = [r for r in rows if r[0] == "CBOT ZN 10y"][0][4]

    print("\nstructural handicap per day / one round trip")
    print("  (how many round trips of short-gamma bleed a market-neutral book eats "
          "per day)")
    pairs = [("G10 FX vs USD (spot, FRED H.10)", fxrt, "6E"),
             ("DM FX vs EUR (ECB)", fxrt, "6E"),
             ("EM/Asia FX vs USD, investable only (FRED H.10)", fxrt, "6E"),
             ("US Treasury curve, duration-proxy TR (FRED CMT)", znrt, "ZN")]
    for lab, rt, tag in pairs:
        if lab not in by:
            continue
        g = abs(by[lab]["delta_bp_day"])
        hi = max(abs(by[lab]["ci_lo_bp"]), abs(by[lab]["ci_hi_bp"]))
        print("  %-50s |gap|=%.3f bp/day  RT(%s)=%.3f bp  ratio=%.2fx "
              "(worst-case CI edge %.2fx)" % (lab[:50], g, tag, rt, g / rt, hi / rt))
    print("  %-50s |gap|=%.3f bp/day  RT=%.3f bp  ratio=%.2fx"
          % ("crypto perps (given, C1)", 57.07, 24.1, 57.07 / 24.1))


if __name__ == "__main__":
    main()
