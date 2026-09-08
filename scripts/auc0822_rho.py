#!/usr/bin/env python3
"""INVENT_0822B -- the persistence/bounce anatomy of the auction dislocation itself.

The ρ1(Δ·) gate reads −0.5 for a series that is i.i.d. day to day. For a SPREAD LEVEL like the
close-auction dislocation d_t = ln(C_t/P59_t) that is the diagnostic verdict: the dislocation
carries no information from one session to the next, which is what a bid-ask/one-tick bounce in
the two constituent prints looks like. This script reports, per series and pooled:

  rho1(level), rho1(Δ level), sd(level) in bp, and the implied "signal share"
     var(persistent part) / var(total)  = (rho1(level) clipped at 0)
plus the same statistics for a TICK-SIZE control: |d| in ticks (half of a $0.01 tick over price).
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "research" / "data" / "auc0822_cache"
OUT = ROOT / "research" / "trading_bot"
sys.path.insert(0, str(ROOT))
from scripts.auc0822_engine import lag, MIN_PRICE, MAX_GAP, MAX_DAY  # noqa: E402


def ac(a, mask, k=1):
    x = np.where(mask, a, np.nan)
    p, q = x[k:], x[:-k]
    ok = np.isfinite(p) & np.isfinite(q)
    if ok.sum() < 1000:
        return float("nan"), 0
    pp, qq = p[ok] - p[ok].mean(), q[ok] - q[ok].mean()
    den = np.sqrt((pp * pp).sum() * (qq * qq).sum())
    return (float((pp * qq).sum() / den) if den > 0 else float("nan")), int(ok.sum())


def main():
    z = np.load(CACHE / "panel.npz", allow_pickle=False)
    p29, p49, p59, po, pc = z["p29"], z["p49"], z["p59"], z["po"], z["pc"]
    ca, in_uni = z["ca"], z["in_uni"]
    with np.errstate(divide="ignore", invalid="ignore"):
        l29, l49, l59, lo, lc = (np.log(v) for v in (p29, p49, p59, po, pc))
    for a in (l29, l49, l59, lo, lc):
        a[~np.isfinite(a)] = np.nan
    base = in_uni & (p59 >= MIN_PRICE) & (~ca) & np.isfinite(l59) & np.isfinite(lc) & np.isfinite(lo)
    d = lc - l59
    q = lo - lag(lc, 1)
    x = lc - lo
    guard = (np.abs(np.nan_to_num(q, nan=0.0)) <= MAX_GAP) & \
            (np.abs(np.nan_to_num(x, nan=0.0)) <= MAX_DAY)
    base = base & guard
    series = {
        "d_close_dislocation": lc - l59,
        "d49_close_vs_1549": lc - l49,
        "e_imbalance_window": l59 - l49,
        "f_pre_publication": l49 - l29,
        "q_open_gap": lo - lag(lc, 1),
        "x_print_day": lc - lo,
        "u_offhours": lo - lag(l59, 1),
        "ptc_print_vs_continuous": (lc - lag(lc, 1)) - (l59 - lag(l59, 1)),
    }
    out = {}
    tick_half_bp = np.where(base, (0.5 * 0.01) / p59 * 1e4, np.nan)
    out["_median_half_tick_bp"] = float(np.nanmedian(tick_half_bp))
    for nm, a in series.items():
        r1, n1 = ac(a, base, 1)
        r2, _ = ac(a, base, 2)
        r5, _ = ac(a, base, 5)
        dr1, _ = ac(a[1:] - a[:-1], base[1:] & base[:-1], 1)
        v = np.where(base, a, np.nan)
        out[nm] = {
            "rho1_level": r1, "rho2_level": r2, "rho5_level": r5,
            "rho1_first_difference": dr1,
            "sd_bp": float(np.nanstd(v) * 1e4),
            "median_abs_bp": float(np.nanmedian(np.abs(v)) * 1e4),
            "n_pairs": n1,
            "median_abs_in_half_ticks": float(np.nanmedian(np.abs(v) * 1e4 / tick_half_bp)),
        }
        print(f"{nm:26s} rho1(level) {r1:+.4f}  rho2 {r2:+.4f}  rho5 {r5:+.4f}  "
              f"rho1(diff) {dr1:+.4f}  sd {out[nm]['sd_bp']:7.2f}bp  "
              f"|median| {out[nm]['median_abs_bp']:6.2f}bp = "
              f"{out[nm]['median_abs_in_half_ticks']:.2f} half-ticks")
    (OUT / "INVENT_0822B_auction_RHO.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
