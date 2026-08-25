#!/usr/bin/env python3
"""INVENT_0825 post-hoc rail test (LABELLED, CANNOT PROMOTE).

PA_GAP_CD_FADE's only economic escape is an exit in the closing auction, which the
5-minute cube cannot price.  Panel B can.  This runs the identical gap-fade score on
Panel B restricted to the SAME 34 mega-cap names, so the universe is held fixed and the
only thing that changes is the rail: entry at the 15:49 print, exit in the closing
auction (0 bp spread, M0-measured on 99.96% of top-500 symbol-days; fee only).
"""
from __future__ import annotations
import json
import numpy as np
import od0825_sweep as S


def book(B, cols, dmask, px_in, sc, top_hint):
    ok = (np.isfinite(B.po) & np.isfinite(B.p29) & np.isfinite(px_in) & np.isfinite(B.pc)
          & (B.po > 0) & (B.p29 > 0) & (px_in > 0) & (B.pc > 0) & np.isfinite(sc))
    m = np.zeros(B.po.shape[1], bool); m[cols] = True
    ok = ok & m[None, :]
    ok = ok & (ok.sum(axis=1) >= 10)[:, None]
    w = S.weights_from_score(np.where(ok, sc, np.nan), ok)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.nan_to_num(np.where(ok, B.pc / px_in - 1.0, 0.0))
    g = (w * r).sum(axis=1)[dmask]
    ge = np.abs(w).sum(axis=1)[dmask]
    return g, ge


def rec(g, ge):
    tp = float(np.nanmean(ge))
    return {"gross_sharpe": S.sharpe(g), "bps_day": float(g.mean() * 1e4),
            "turnover": tp, "breakeven_bp_auction_exit": float(g.mean() * 1e4 / tp) if tp else None,
            "net_0.5": S.sharpe(S.net_series(g, ge, 0.5, True)),
            "net_1.0": S.sharpe(S.net_series(g, ge, 1.0, True)),
            "net_2.0": S.sharpe(S.net_series(g, ge, 2.0, True)),
            "n_days": int(g.size), "n_names_median": None}


def main():
    B = S.PanelB()
    syms = [str(s) for s in np.load(S.PANELB, allow_pickle=True)["syms"]]
    idx = {s: i for i, s in enumerate(syms)}
    have = [s for s in S.MEGA if s in idx]
    missing = [s for s in S.MEGA if s not in idx]
    cols = np.array([idx[s] for s in have])
    sc = -B.gapz
    out = {"universe": "MEGA-on-PanelB", "n_names": len(have), "missing": missing,
           "rail": "entry 15:49 print, exit CLOSING AUCTION (0bp spread, fee only)"}
    for lab, win in (("design", S.DESIGN), ("heldout", S.HELDOUT), ("presample", S.PRESAMPLE)):
        dm = (B.dates >= win[0]) & (B.dates <= win[1])
        g, ge = book(B, cols, dm, B.p49, sc, None)
        out[lab] = rec(g, ge)
        out[lab]["window"] = list(win)
        # the 10-minute-later fill, the bounce control
        g2, ge2 = book(B, cols, dm, B.p59, sc, None)
        out[lab + "_gapfill_p59"] = {"gross_sharpe": S.sharpe(g2), "bps_day": float(g2.mean() * 1e4)}
    p = S.OUTDIR / "INVENT_0825_opendrive_AUCTIONRAIL.json"
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
