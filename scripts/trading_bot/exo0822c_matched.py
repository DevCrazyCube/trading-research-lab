#!/usr/bin/env python3
"""EXO_0822C — the matched-control estimator.

Post-hoc SHARPENING of the pre-registered E1 control, not a new formula.

E1 compares each event's hedged ex-day gap to the same symbol's hedged overnight
return on ONE nearby non-event date, which is a noisy control. Here the control is
the MEAN over every eligible non-event date in +/-3..15 sessions (typically ~20),
which cuts the control's contribution to the variance by an order of magnitude
without changing what is being estimated.

Statistic: mean over events of  eps_h - mean_k ON(d+k, i),  day-clustered t.
"""
from __future__ import annotations

import json
import sys

import numpy as np

from exo0822c_sweep import OUTDIR, Panel, real_returns, shuffle_rate
from exo0822c_diag import clustered_t


def main():
    P = Panel()
    z = np.load(OUTDIR.parent / "data/exo0822c/events.npz", allow_pickle=True)
    base = z["base"]
    clean = z["clean"]
    rng = np.random.default_rng(7)
    r = real_returns(P, shuffle_rate(P.y, P.evd, rng))
    eps = r["eps_h"]
    ON = P.ON
    d, i = P.evd, P.evs
    n = d.size

    ctrl = np.full(n, np.nan)
    nctrl = np.zeros(n)
    offs = [k for k in range(-15, 16) if abs(k) >= 3]
    acc = np.zeros(n)
    cnt = np.zeros(n)
    for k in offs:
        dd = d + k
        ok = (dd >= 1) & (dd < P.nd)
        ddc = np.clip(dd, 0, P.nd - 1)
        v = ON[ddc, i]
        good = ok & np.isfinite(v) & clean[ddc, i]
        acc += np.where(good, v, 0.0)
        cnt += good
    ctrl = np.where(cnt >= 8, acc / np.maximum(cnt, 1), np.nan)
    nctrl = cnt

    out = {}
    ordinary = P.typ == 0
    for win, sel in (("design", P.evd < P.cut), ("holdout", P.evd >= P.cut)):
        m = ordinary & sel & np.isfinite(ctrl) & np.isfinite(eps)
        a, t, nd_ = clustered_t(eps[m], P.evd[m])
        b, tb, _ = clustered_t(ctrl[m], P.evd[m])
        c, tc, _ = clustered_t(eps[m] - ctrl[m], P.evd[m])
        # yield-weighted version (matches A2_YW, the round's best design cell)
        wy = P.y[m]
        diffw = (eps[m] - ctrl[m]) * wy / np.mean(wy)
        cw, tcw, _ = clustered_t(diffw, P.evd[m])
        # top expanding-yield tercile
        out[win] = {
            "n_events": int(m.sum()), "n_days": nd_,
            "mean_control_days": float(np.mean(nctrl[m])),
            "event_bp": a, "event_t": t,
            "matched_control_bp": b, "control_t": tb,
            "event_minus_control_bp": c, "event_minus_control_t": tc,
            "yield_weighted_diff_bp": cw, "yield_weighted_diff_t": tcw,
        }
        # by yield tercile
        q = np.nanquantile(P.y[m], [1 / 3, 2 / 3])
        yt = {}
        for lab, s in (("lo", P.y <= q[0]), ("mid", (P.y > q[0]) & (P.y <= q[1])),
                       ("hi", P.y > q[1])):
            mm = m & s
            v1, v2, v3 = clustered_t(eps[mm] - ctrl[mm], P.evd[mm])
            yt[lab] = {"bp": v1, "t": v2, "n": int(mm.sum())}
        out[win]["by_yield_tercile"] = yt
        # splits, same estimator
        for lab, code in (("fwd_split", 1), ("rev_split", 2), ("special", 3)):
            mm = (P.typ == code) & sel & np.isfinite(ctrl) & np.isfinite(eps)
            if mm.sum() >= 5:
                v1, v2, v3 = clustered_t(eps[mm] - ctrl[mm], P.evd[mm])
                out[win][lab] = {"bp": v1, "t": v2, "n": int(mm.sum())}
    json.dump(out, open(OUTDIR / "INVENT_0822C_gaptether_MATCHED.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
