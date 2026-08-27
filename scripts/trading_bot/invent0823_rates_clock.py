#!/usr/bin/env python3
"""THE ANCHOR-CLOCK DIAGNOSTIC.

Family A/G measure a Treasury wrapper against the PUBLISHED constant-maturity curve and fade
the residual.  Every one of those residuals has rho1(Delta spread) = -0.40 .. -0.46, which the
programme's bounce gate reads as measurement-error bounce.  This script asks whether it is
bounce (the tick) or something else, by holding the instruments and the window fixed and
changing ONE thing: whether the anchor prints on the same clock as the tradable leg.

  * FRED H.15 constant-maturity yields are a **15:30 ET** snapshot.
  * The ETF prints at **16:00 ET**.

If the anchor is stale by half an hour, then

    e(t) = r(t) - D*dy_pub(t) ~= -D*[u(t) - u(t-1)],   u = the unobserved 15:30->16:00 move,

i.e. the residual is the FIRST DIFFERENCE of a near-white series, which forces rho1 -> -0.5
mechanically and makes the Roll(1984) "implied spread" equal the size of the missing half hour
rather than the bid-ask.  Two falsifiable predictions follow, and both are tested here:

  P1  Replace the 15:30 published anchor with a 16:00 anchor (another ETF on a DIFFERENT curve
      segment, so it is not a sibling pair) and rho1 must collapse toward 0.
  P2  The Roll-implied half-spread must track sigma_daily / sqrt(13) (a 30-minute slice of a
      6.5-hour session) across the whole duration ladder -- NOT the actual bid-ask, which for
      TLT is ~0.6 bp against a Roll-implied ~19 bp.
"""
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import invent0823_rates as M  # noqa: E402

# a 16:00 anchor drawn from a DIFFERENT curve segment (not a sponsor sibling)
CROSS = {"TLT": "IEF", "EDV": "TLT", "TLH": "IEF", "IEF": "TLT", "IEI": "IEF", "SHY": "IEI"}
SESSION_SLICES = 13.0     # 6.5h session / 30min


def roll_half_spread_bp(x):
    x = x[np.isfinite(x)]
    x = x - x.mean()
    c = float(np.mean(x[1:] * x[:-1]))
    return float(np.sqrt(-c) * 1e4) if c < 0 else float("nan")


def main():
    P = M.Panel(M.DESIGN_HI)
    E = M.Engine(P)
    dm = P.mask(M.DESIGN_LO, M.DESIGN_HI)

    p1 = {}
    for s, h in CROSS.items():
        W, bt = E.pair_weights(s, h)
        rr = np.sum(np.nan_to_num(P.R) * W, axis=1)
        rr[~np.isfinite(bt)] = np.nan
        p1[s] = {
            "cross_anchor": h,
            "rho1_raw_return": M.rho1(P.r(s)[dm]),
            "rho1_resid_vs_published_1530_curve": M.rho1(E.resid[s][dm]),
            "rho1_resid_vs_1600_etf_anchor": M.rho1(rr[dm]),
        }

    p2 = {}
    for s in M.LADDER:
        sig = float(np.nanstd(P.r(s)[dm]) * 1e4)
        p2[s] = {
            "daily_sigma_bp": sig,
            "predicted_30min_slice_bp": sig / np.sqrt(SESSION_SLICES),
            "roll_implied_half_spread_bp": roll_half_spread_bp(E.resid[s][dm]),
            "charged_half_spread_bp": float(P.hs[P.sidx[s]]),
            "median_duration_yrs": float(np.nanmedian(E.dur[s][dm])),
            "r2_of_published_curve": float(
                1 - np.nanvar(E.resid[s][dm]) / np.nanvar(P.r(s)[dm])),
        }

    pred = np.array([v["predicted_30min_slice_bp"] for v in p2.values()])
    obs = np.array([v["roll_implied_half_spread_bp"] for v in p2.values()])
    chg = np.array([v["charged_half_spread_bp"] for v in p2.values()])
    out = {
        "hypothesis": ("The A/G-family rho1 ~ -0.42 is NOT bid-ask bounce; it is the FRED H.15 "
                       "15:30 ET anchor being stale against a 16:00 ET ETF print."),
        "P1_replace_anchor_with_a_1600_clock": p1,
        "P2_roll_implied_tracks_the_missing_half_hour": p2,
        "P2_fit": {
            "corr_roll_vs_predicted_30min_slice": float(np.corrcoef(obs, pred)[0, 1]),
            "corr_roll_vs_charged_bidask": float(np.corrcoef(obs, chg)[0, 1]),
            "mean_ratio_roll_over_predicted": float(np.mean(obs / pred)),
            "mean_ratio_roll_over_charged": float(np.mean(obs / chg)),
        },
    }
    p = (pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
         / "INVENT_0823_rates_ANCHORCLOCK.json")
    p.write_text(json.dumps(out, indent=1))
    print(f"wrote {p}")
    print(f"P1: rho1 vs 15:30 published anchor  -> "
          f"{np.mean([v['rho1_resid_vs_published_1530_curve'] for v in p1.values()]):+.3f} (mean)")
    print(f"P1: rho1 vs 16:00 ETF anchor        -> "
          f"{np.mean([v['rho1_resid_vs_1600_etf_anchor'] for v in p1.values()]):+.3f} (mean)")
    print(f"P2: corr(Roll, 30min slice) = {out['P2_fit']['corr_roll_vs_predicted_30min_slice']:.3f}"
          f"   corr(Roll, bid-ask) = {out['P2_fit']['corr_roll_vs_charged_bidask']:.3f}")
    print(f"P2: Roll / predicted-slice ratio = "
          f"{out['P2_fit']['mean_ratio_roll_over_predicted']:.2f}x   "
          f"Roll / charged-bid-ask ratio = {out['P2_fit']['mean_ratio_roll_over_charged']:.2f}x")


if __name__ == "__main__":
    main()
