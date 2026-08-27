#!/usr/bin/env python3
"""INVENT_0823 follow-up: re-run the two mechanism carries on the EXECUTABLE subset only.

The short leg of every structure here is screened against a LIVE, per-symbol
`GET /v2/assets` snapshot from the account this programme would trade in
(`research/data/exo0823_cache/alpaca_assets_flags.json`).  A name whose `shortable` flag is
false is removed from the book entirely -- not charged a higher rate, removed.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from trading_bot import exo0823_sweep as S  # noqa: E402
from trading_bot import exo0823_fetch as F  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
FLAGS = json.loads((ROOT / "research" / "data" / "exo0823_cache"
                    / "alpaca_assets_flags.json").read_text())
BORROW = {"b22g_etb_0.33pct": 33.0, "moderate_1pct": 100.0, "hard_3pct": 300.0}


def shortable(sym: str) -> bool:
    return bool(FLAGS.get(sym, {}).get("shortable"))


def main():
    panel = S.build_panel()
    master, px = panel["dates"], panel["px"]
    n = len(master)
    ix = {k: S.date_index(master, v) for k, v in
          {"d0": S.D0, "d1": S.D1, "h0": S.H0, "h1": S.H1,
           "cd0": S.CD0, "cd1": S.CD1, "ch0": S.CH0, "ch1": S.CH1}.items()}
    hs = {}
    for s in px:
        v = S.corwin_schultz_halfspread(px[s]["h"], px[s]["l"], ix["d0"], ix["h1"])
        hs[s] = max(S.SPREAD_FLOOR_BP, v) if np.isfinite(v) else 25.0
    bil = S.logret(px["BIL"]["c"])
    bil = np.where(np.isfinite(bil), bil, 0.0)

    def static(weights):
        syms = sorted(weights)
        raw = np.zeros((n, len(syms)))
        live = np.ones(n, dtype=bool)
        for s in syms:
            live &= np.isfinite(px[s]["c"])
        for j, s in enumerate(syms):
            raw[live, j] = weights[s]
        return syms, raw

    def run(label, weights, a, b):
        syms, raw = static(weights)
        W = S.normalise_and_stagger(raw, 1)
        st = S.evaluate(W, syms, px, hs, ix[a], ix[b])
        r_cash = float(bil[ix[a]:ix[b]].mean() * 1e4)
        sd = float(np.std(st["_net"], ddof=1))
        row = {"window": label, "days": st["days"], "raw_net_sharpe": st["net_sharpe"],
               "raw_net_bp_day": st["net_bp_day"],
               "net_cash_weight": st["net_cash_weight"], "short_weight": st["short_weight"],
               "bil_bp_day": r_cash}
        for k, bp in BORROW.items():
            adj = st["net_bp_day"] - st["net_cash_weight"] * r_cash \
                - abs(st["short_weight"]) * bp / 252.0
            yrs = st["days"] / 252.0
            shp = adj / 1e4 / sd * np.sqrt(252) if sd > 0 else 0.0
            row[k] = {"excess_bp_day": adj, "excess_pct_yr": adj * 252 / 100.0,
                      "sharpe": shp, "t": shp * np.sqrt(yrs)}
        return row

    out = {}

    # --- L7 executable subset: bull LETFs whose SHORT leg is available today
    bulls = [(lev, base, m) for lev, base, m in F.LEVERED if m > 0 and shortable(lev)]
    dropped = [lev for lev, base, m in F.LEVERED if m > 0 and not shortable(lev)]
    w = {}
    for lev, base, m in bulls:
        w[lev] = w.get(lev, 0) - 1.0 / len(bulls)
        w[base] = w.get(base, 0) + m / len(bulls)
    out["L7_exec"] = {"kept": [b[0] for b in bulls], "dropped_not_shortable": dropped,
                      "design": run("design", w, "d0", "d1"),
                      "heldout": run("heldout", w, "h0", "h1")}

    # --- L7 single-index variants: is it one fund or the whole complex?
    for lev, base, m in bulls:
        w1 = {lev: -1.0, base: m}
        out[f"L7_single_{lev}"] = {"design": run("design", w1, "d0", "d1"),
                                   "heldout": run("heldout", w1, "h0", "h1")}

    # --- C9 executable: both short legs (GBTC, ETHE) confirmed shortable+ETB today
    lowb = [s for s in S.BTC_WRAPPERS if s != "GBTC" and s in px]
    lowe = [s for s in S.ETH_WRAPPERS if s != "ETHE" and s in px]
    w = {}
    for s in lowb:
        w[s] = 0.25 / len(lowb)
    for s in lowe:
        w[s] = w.get(s, 0) + 0.25 / len(lowe)
    w["GBTC"] = -0.25
    w["ETHE"] = -0.25
    out["C9_exec"] = {"short_leg_flags": {k: FLAGS.get(k) for k in ("GBTC", "ETHE")},
                      "design": run("design", w, "cd0", "cd1"),
                      "heldout": run("heldout", w, "ch0", "ch1")}

    p = ROOT / "research" / "trading_bot" / "INVENT_0823_exotic_EXEC.json"
    p.write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        if "design" not in v:
            continue
        d, h = v["design"], v["heldout"]
        print(f"{k:22s} D raw {d['raw_net_sharpe']:6.2f} etb {d['b22g_etb_0.33pct']['sharpe']:6.2f}"
              f" ({d['b22g_etb_0.33pct']['excess_pct_yr']:+.2f}%/yr, t {d['b22g_etb_0.33pct']['t']:+.2f})"
              f" | H raw {h['raw_net_sharpe']:6.2f} etb {h['b22g_etb_0.33pct']['sharpe']:6.2f}"
              f" ({h['b22g_etb_0.33pct']['excess_pct_yr']:+.2f}%/yr, t {h['b22g_etb_0.33pct']['t']:+.2f})")


if __name__ == "__main__":
    main()
