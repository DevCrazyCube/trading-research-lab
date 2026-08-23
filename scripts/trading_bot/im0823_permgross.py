#!/usr/bin/env python3
"""ADV-slot signal permutation on the GROSS series.

The null-stage permutation was run on the NET series, which is mis-specified: a permuted
score still pays the full cost, so the null distribution sits far below zero and any config
with a merely non-negative gross "beats" it.  The honest cross-sectional null asks whether
the score->symbol mapping carries information at all, i.e. it must be run on GROSS.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

import im0823_sweep as S

TOP = ["E4_PDPOC_MAGNET", "F2_LD_REV", "F3_LD_VWAPDEV_REV", "C1_VWAPDEV_MID_REV",
       "A5_DRIVE_EX_GAP", "G3_LD500_CONT_TOP150", "G1_LD500_CONT"]
NPERM = 500


def main() -> None:
    P = S.PanelA()
    F = S.Feat(P)
    B = S.PanelB()
    cfgs = {c["name"]: c for c in S.build_configs(F)}
    da = (P.daykey >= S.DESIGN[0]) & (P.daykey <= S.DESIGN[1])
    db = (B.dates >= S.DESIGN[0]) & (B.dates <= S.DESIGN[1])
    rng = np.random.default_rng(8232026)
    res = {}
    for nm in TOP:
        cfg = cfgs[nm]
        if cfg["panel"] == "A":
            cols = P.cols(cfg["universe"])
            legs = cfg.get("legs") or [(cfg["score"], cfg["s"], 1.0)]
            adv = P.adv[:, cols][da]
            prepped = []
            for score, s, wt in legs:
                px_in = P.vw[:, s + 1, :][:, cols][da]
                px_out = P.vw[:, 77, :][:, cols][da]
                sc = score[:, cols][da].astype(float)
                valid = (np.isfinite(sc) & np.isfinite(px_in) & np.isfinite(px_out)
                         & (px_in > 0) & (px_out > 0))
                valid = valid & (valid.sum(axis=1) >= 10)[:, None]
                r = np.nan_to_num(np.where(valid, px_out / px_in - 1.0, 0.0))
                prepped.append((np.nan_to_num(sc), valid, r, wt, S.adv_buckets(adv, valid)))
            obs = np.zeros(int(da.sum()))
            for sc, valid, r, wt, _ in prepped:
                obs += (S.weights_from_score(np.where(valid, sc, np.nan), valid) * wt * r).sum(axis=1)
            draws = []
            for _ in range(NPERM):
                tot = np.zeros(int(da.sum()))
                for sc, valid, r, wt, buck in prepped:
                    tot += (S.weights_from_score(S.shuffle_in_buckets(sc, buck, rng), valid) * wt * r).sum(axis=1)
                draws.append(S.sharpe(tot))
        else:
            ok0 = (B.in_uni & np.isfinite(B.po) & np.isfinite(B.p29) & np.isfinite(B.p49)
                   & np.isfinite(B.pc) & (B.po > 0) & (B.p29 > 0) & (B.p49 > 0) & (B.pc > 0))[db]
            sc0 = np.nan_to_num((cfg["sign"] * (B.p29 / B.po - 1.0))[db])
            adv = B.adv[db]
            ok = ok0
            if cfg["top"]:
                a = np.where(ok0, adv, np.nan)
                rk = np.argsort(np.argsort(-np.nan_to_num(a, nan=-1.0), axis=1), axis=1)
                ok = ok0 & (rk < cfg["top"])
            ok = ok & (ok.sum(axis=1) >= 20)[:, None]
            r = np.nan_to_num(np.where(ok, B.pc[db] / B.p49[db] - 1.0, 0.0))
            buck = S.adv_buckets(adv, ok)
            obs = (S.weights_from_score(np.where(ok, sc0, np.nan), ok) * r).sum(axis=1)
            draws = [S.sharpe((S.weights_from_score(S.shuffle_in_buckets(sc0, buck, rng), ok) * r).sum(axis=1))
                     for _ in range(NPERM)]
        o = S.sharpe(obs)
        d = np.asarray(draws, float)
        res[nm] = {"observed_gross_sharpe": o, "perm_mean": float(d.mean()),
                   "perm_sd": float(d.std(ddof=1)), "perm_p95": float(np.percentile(d, 95)),
                   "p_value_one_sided": float((np.sum(d >= o) + 1) / (d.size + 1)), "n_perm": int(d.size)}
        print(f"{nm:24s} obs {o:+6.2f}  null mean {d.mean():+5.2f} p95 {np.percentile(d,95):+5.2f} "
              f"p={res[nm]['p_value_one_sided']:.4f}", flush=True)
    p = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot" / "INVENT_0823_intramicro_permgross.json"
    p.write_text(json.dumps(res, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
