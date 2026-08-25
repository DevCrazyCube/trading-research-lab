#!/usr/bin/env python3
"""INVENT_0825 diagnostics: where does the gross live, and is it the same object twice?"""
from __future__ import annotations
import json
import numpy as np
import od0825_sweep as S


def leg(P, F, cfg, cols, i, j, dmask):
    """Gross PnL of holding the config's book from bar i vwap to bar j vwap."""
    px_in = P.vw[:, i, :][:, cols]
    px_out = P.vw[:, j, :][:, cols]
    sc = cfg["score"][:, cols]
    ent = P.vw[:, min(cfg["s"] + 1, 76), :][:, cols]
    valid = (np.isfinite(sc) & np.isfinite(ent) & np.isfinite(px_in) & np.isfinite(px_out)
             & (ent > 0) & (px_in > 0) & (px_out > 0)
             & np.isfinite(P.vw[:, 77, :][:, cols]))
    valid = valid & (valid.sum(axis=1) >= 10)[:, None]
    w = S.weights_from_score(sc, valid)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.nan_to_num(np.where(valid, px_out / px_in - 1.0, 0.0))
    return (w * r).sum(axis=1)[dmask]


def main():
    P = S.PanelA(); F = S.FeatA(P); B = S.PanelB()
    cfgs = {c["name"]: c for c in S.build_configs(P, F)}
    da = (P.daykey >= S.DESIGN[0]) & (P.daykey <= S.DESIGN[1])
    db = (B.dates >= S.DESIGN[0]) & (B.dates <= S.DESIGN[1])
    out = {}

    # ---- 1. Panel A hold decomposition for the od_to_cd family (entry 71, exit 77)
    for nm in ("PA_GAP_CD_FADE", "PA_OD30_CD_FADE"):
        cfg = cfgs[nm]; cols = P.cols(cfg["universe"])
        full = leg(P, F, cfg, cols, 71, 77, da)
        first = leg(P, F, cfg, cols, 71, 72, da)
        rest = leg(P, F, cfg, cols, 72, 77, da)
        out[nm + "_hold_decomp"] = {
            "full_71_77": {"bps_day": float(full.mean() * 1e4), "sharpe": S.sharpe(full)},
            "first_bar_71_72": {"bps_day": float(first.mean() * 1e4), "sharpe": S.sharpe(first),
                                "pct_of_full": float(first.mean() / full.mean() * 100) if full.mean() else None},
            "rest_72_77": {"bps_day": float(rest.mean() * 1e4), "sharpe": S.sharpe(rest)},
        }

    # ---- 2. Panel A entry-slot profile for PA_GAP_CD_FADE (diagnostic, not selection)
    cfg = cfgs["PA_GAP_CD_FADE"]; cols = P.cols("MEGA")
    prof = {}
    for s in (5, 11, 23, 35, 47, 59, 65, 70, 73, 75):
        c2 = dict(cfg); c2["s"] = s
        g, ge = S.run_panelA(c2, F, da, 0)
        prof[f"entry_bar_{s+1}"] = {"gross_sharpe": S.sharpe(g), "bps_day": float(g.mean() * 1e4),
                                    "hold_bars": 77 - (s + 1)}
    out["PA_GAP_CD_FADE_entry_slot_profile"] = prof

    # ---- 3. gap-fade held from the OPEN (the honest long-hold version, no late-day cherry pick)
    for s in (5, 11):
        c2 = dict(cfg); c2["s"] = s
        g, ge = S.run_panelA(c2, F, da, 0)
        out[f"PA_GAP_FADE_open_hold_entry{s+1}"] = {
            "gross_sharpe": S.sharpe(g), "bps_day": float(g.mean() * 1e4),
            "net_1.0": S.sharpe(S.net_series(g, ge, 1.0, False)),
            "breakeven_bp": float(g.mean() * 1e4 / (np.nanmean(ge) * 2.0))}

    # ---- 4. Panel B hold decomposition for the gap family (p49 -> close)
    for nm in ("PB_GAPZ_FADE", "PB_DRIVEZ_FADE", "PB_TOTMOVE_FADE"):
        cfg = cfgs[nm]
        ok = B.base_ok(cfg["need_gap"])
        sc = S.panelB_score(cfg, B)
        ok = ok & np.isfinite(sc)
        ok = ok & (ok.sum(axis=1) >= 20)[:, None]
        w = S.weights_from_score(np.where(ok, sc, np.nan), ok)
        legs = {}
        with np.errstate(invalid="ignore", divide="ignore"):
            for lab, a, b in (("p49_to_close", B.p49, B.pc), ("p49_to_p59", B.p49, B.p59),
                              ("p59_to_close", B.p59, B.pc), ("p29_to_p49", B.p29, B.p49)):
                r = np.nan_to_num(np.where(ok, b / a - 1.0, 0.0))
                x = (w * r).sum(axis=1)[db]
                legs[lab] = {"bps_day": float(x.mean() * 1e4), "sharpe": S.sharpe(x)}
        base = legs["p49_to_close"]["bps_day"]
        legs["pct_of_hold_in_last_10min"] = float(legs["p59_to_close"]["bps_day"] / base * 100) if base else None
        out[nm + "_hold_decomp"] = legs

    # ---- 5. are the two panels the same object?
    cfgA = cfgs["PA_GAP_CD_FADE"]
    gA, _ = S.run_panelA(cfgA, F, da, 0)
    cfgB = cfgs["PB_GAPZ_FADE"]
    gB, _ = S.run_panelB(cfgB, B, db, 0)
    n = min(len(gA), len(gB))
    dA = P.daykey[da][:n]; dB = B.dates[db][:n]
    same = dA == dB
    out["panelA_vs_panelB_gapfade"] = {
        "days_aligned": bool(same.all()), "n": int(n),
        "corr_daily_pnl": float(np.corrcoef(gA[:n][same], gB[:n][same])[0, 1]),
    }

    # ---- 6. gap-fade PnL by gap tercile (is it all in the extreme tail?)
    gz = F.gapz[:, cols]
    px_in = P.vw[:, 71, :][:, cols]; px_out = P.vw[:, 77, :][:, cols]
    valid = np.isfinite(gz) & np.isfinite(px_in) & np.isfinite(px_out) & (px_in > 0) & (px_out > 0)
    valid = valid & (valid.sum(axis=1) >= 10)[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.nan_to_num(np.where(valid, px_out / px_in - 1.0, 0.0))
    az = np.where(valid, np.abs(gz), np.nan)
    q = np.nanquantile(az[da], [1 / 3, 2 / 3])
    terc = {}
    for lab, m in (("small_gap", az < q[0]), ("mid_gap", (az >= q[0]) & (az < q[1])),
                   ("large_gap", az >= q[1])):
        vv = valid & np.nan_to_num(m, nan=False).astype(bool)
        vv = vv & (vv.sum(axis=1) >= 5)[:, None]
        w = S.weights_from_score(np.where(vv, -gz, np.nan), vv)
        x = (w * r).sum(axis=1)[da]
        terc[lab] = {"bps_day": float(x.mean() * 1e4), "sharpe": S.sharpe(x)}
    out["PA_GAP_CD_FADE_by_gap_tercile"] = terc

    p = S.OUTDIR / "INVENT_0825_opendrive_DIAG.json"
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
