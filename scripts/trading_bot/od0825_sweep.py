#!/usr/bin/env python3
"""INVENT_0825 - open-drive / close-drive microstructure.

26 pre-registered formulas, deliberately disjoint from the 28 killed by INVENT_0823.
See research/trading_bot/INVENT_0825_opendrive_PREREGISTRATION.md.

Stages:
  --stage selftest  planted-edge / sign-flip / random / planted-artefact checks
  --stage design    score all 26, both fills, all cost rungs
  --stage null      block-bootstrap best-of-26 bar + ADV-decile permutation on GROSS
  --stage heldout   frozen shortlist only (refuses to run without --only)
  --stage presample Panel B 2016-2020 (refuses to run without --only)
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
CUBE = ROOT / "research" / "data" / "im0823_cache" / "cube.npz"
PANELB = ROOT / "research" / "data" / "auc0822_cache" / "panel.npz"
OUTDIR = ROOT / "research" / "trading_bot"

DESIGN = ("2021-01-04", "2024-12-31")
HELDOUT = ("2025-01-02", "2026-08-14")
PRESAMPLE = ("2016-01-04", "2020-12-31")

RUNGS = [0.5, 1.0, 2.0, 2.5]
HEADLINE = 1.0
FEE_BP = 0.15
ANN = np.sqrt(252.0)

MEGA = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "BRK.B",
        "JPM", "XOM", "UNH", "JNJ", "V", "PG", "HD", "MA", "COST", "WMT", "BAC", "CVX",
        "LLY", "ABBV", "MRK", "PEP", "KO", "ORCL", "CRM", "AMD", "INTC", "NFLX", "ADBE", "CSCO"]
LIQETF = ["SPY", "VTI", "QQQ", "IWM", "DIA", "MDY", "IJR", "IWF", "IWD", "MTUM", "USMV",
          "QUAL", "VLUE", "SPYG", "SPYV", "GLD", "SLV", "USO", "UNG", "EFA", "EEM", "EWJ",
          "FXI", "EWZ", "AGG", "LQD", "HYG", "JNK", "TLT", "IEF", "SHY", "TIP", "XLK",
          "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH",
          "KRE", "IBB", "XBI", "ITB", "GDX"]


# --------------------------------------------------------------------- helpers
def roll_sd(x: np.ndarray, w: int) -> np.ndarray:
    """SD of the previous `w` rows, strictly excluding the current row."""
    D, S = x.shape
    out = np.full_like(x, np.nan)
    for d in range(w, D):
        out[d] = np.nanstd(x[d - w:d], axis=0, ddof=1)
    return out


def roll_med(x: np.ndarray, w: int) -> np.ndarray:
    D, S = x.shape
    out = np.full_like(x, np.nan)
    for d in range(w, D):
        out[d] = np.nanmedian(x[d - w:d], axis=0)
    return out


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    if x.size < 30 or not np.isfinite(x).all() or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * ANN)


def weights_from_score(sc, valid):
    w = np.where(valid, sc, np.nan)
    mu = np.nanmean(np.where(valid, w, np.nan), axis=1, keepdims=True)
    w = np.where(valid, w - mu, 0.0)
    w = np.nan_to_num(w)
    g = np.abs(w).sum(axis=1, keepdims=True)
    return np.where(g > 0, w / np.maximum(g, 1e-12), 0.0)


def net_series(gross, gexp, bp, auction_exit):
    entry = gexp * (bp + FEE_BP) / 1e4
    exit_ = gexp * ((0.0 if auction_exit else bp) + FEE_BP) / 1e4
    return gross - entry - exit_


# ----------------------------------------------------------------- Panel A
class PanelA:
    def __init__(self):
        z = np.load(CUBE, allow_pickle=True)
        self.daykey = z["daykey"]
        self.syms = [str(s) for s in z["syms"]]
        self.o = z["o"]; self.h = z["h"]; self.l = z["l"]
        self.c = z["c"]; self.vw = z["vw"]; self.dv = z["dv"]
        self.D = self.daykey.size
        self.idx = {s: i for i, s in enumerate(self.syms)}
        day_dv = np.nansum(self.dv, axis=1)
        cs = np.nancumsum(np.nan_to_num(day_dv), axis=0)
        adv = np.full_like(day_dv, np.nan)
        adv[20:] = (cs[19:-1] - np.vstack([np.zeros((1, day_dv.shape[1])), cs[:-21]])) / 20.0
        self.adv = adv

    def cols(self, universe):
        names = MEGA if universe == "MEGA" else LIQETF
        return np.array([self.idx[s] for s in names if s in self.idx])


class FeatA:
    def __init__(self, P: PanelA):
        o, h, l, c, vw = P.o, P.h, P.l, P.c, P.vw
        op = o[:, 0, :]
        self.op = op
        prev_close = np.full_like(op, np.nan)
        prev_close[1:] = c[:-1, 77, :]
        with np.errstate(invalid="ignore", divide="ignore"):
            self.gap = op / prev_close - 1.0
            self.r30 = c[:, 5, :] / op - 1.0
            self.r60 = c[:, 11, :] / op - 1.0
            self.odisl = op / vw[:, 0, :] - 1.0

        # 5-min bar returns over the first hour: bar0 uses the open, bars 1..11 close/close
        with np.errstate(invalid="ignore", divide="ignore"):
            b0 = (c[:, 0, :] / op - 1.0)[:, None, :]
            brest = c[:, 1:12, :] / c[:, 0:11, :] - 1.0
        bars = np.concatenate([b0, brest], axis=1)              # (D,12,S)
        absum = np.nansum(np.abs(bars), axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.er = np.where(absum > 0, np.abs(self.r60) / absum, np.nan)
        sg = np.sign(bars)
        flips = np.nansum(np.abs(np.diff(sg, axis=1)) > 0, axis=1).astype(float)
        self.chop = flips / 11.0
        bad = ~np.isfinite(absum) | (absum <= 0)
        self.chop = np.where(bad, np.nan, self.chop)

        # first-hour range, and location of the hour-1 close inside it
        hi = np.nanmax(h[:, :12, :], axis=1)
        lo = np.nanmin(l[:, :12, :], axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            rel = (hi - lo) / op
            self.rr = rel / roll_med(rel, 20)
            self.h1loc = (c[:, 11, :] - lo) / np.where(hi - lo > 0, hi - lo, np.nan)

        gsd = roll_sd(self.gap, 60)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.gapz = np.clip(self.gap / np.where(gsd > 0, gsd, np.nan), -5, 5)


def run_panelA(cfg, F: FeatA, dmask, gapshift):
    P = F.P if hasattr(F, "P") else cfg["_P"]
    cols = P.cols(cfg["universe"])
    e = min(cfg["s"] + 1 + gapshift, 76)
    px_in = P.vw[:, e, :][:, cols]
    px_out = P.vw[:, 77, :][:, cols]
    sc = cfg["score"][:, cols]
    valid = (np.isfinite(sc) & np.isfinite(px_in) & np.isfinite(px_out)
             & (px_in > 0) & (px_out > 0))
    valid = valid & (valid.sum(axis=1) >= 10)[:, None]
    w = weights_from_score(sc, valid)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.nan_to_num(np.where(valid, px_out / px_in - 1.0, 0.0))
    return (w * r).sum(axis=1)[dmask], np.abs(w).sum(axis=1)[dmask]


# ----------------------------------------------------------------- Panel B
class PanelB:
    def __init__(self):
        z = np.load(PANELB, allow_pickle=True)
        self.dates = z["dates"]
        self.po = z["po"]; self.p29 = z["p29"]; self.p49 = z["p49"]; self.p59 = z["p59"]
        self.pc = z["pc"]; self.ca = z["ca"]; self.in_uni = z["in_uni"]; self.adv = z["advusd"]

        prev_pc = np.full_like(self.pc, np.nan)
        prev_pc[1:] = self.pc[:-1]
        with np.errstate(invalid="ignore", divide="ignore"):
            gap = self.po / prev_pc - 1.0
            drive = self.p29 / self.po - 1.0
        gap = np.where(self.ca, np.nan, gap)
        gap = np.where(np.abs(gap) > 0.5, np.nan, gap)     # residual CA guard
        self.gap = gap
        self.drive = drive
        gsd = roll_sd(gap, 60)
        dsd = roll_sd(drive, 60)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.gapz = np.clip(gap / np.where(gsd > 0, gsd, np.nan), -5, 5)
            self.drivez = np.clip(drive / np.where(dsd > 0, dsd, np.nan), -5, 5)

    def base_ok(self, need_gap):
        ok = (self.in_uni & np.isfinite(self.po) & np.isfinite(self.p29)
              & np.isfinite(self.p49) & np.isfinite(self.p59) & np.isfinite(self.pc)
              & (self.po > 0) & (self.p29 > 0) & (self.p49 > 0) & (self.p59 > 0) & (self.pc > 0)
              & np.isfinite(self.drivez))
        if need_gap:
            ok = ok & np.isfinite(self.gapz)
        return ok


def panelB_score(cfg, B: PanelB):
    gz, dz = B.gapz, B.drivez
    n = cfg["name"]
    if n == "PB_GAPZ_FADE" or n == "PB_GAPZ_FADE_T150":
        return -gz
    if n == "PB_GAPZ_GO":
        return gz
    if n == "PB_IDIOGAP_FADE":
        m = np.nanmean(np.where(B.in_uni, gz, np.nan), axis=1, keepdims=True)
        return -(gz - m)
    if n == "PB_GAPGO_CONFIRMED":
        return np.where(np.sign(gz) == np.sign(dz), gz, 0.0)
    if n == "PB_GAPFADE_UNCONF":
        return np.where(np.sign(gz) != np.sign(dz), -gz, 0.0)
    if n == "PB_TOTMOVE_FADE":
        return -(gz + dz)
    if n == "PB_DRIVEZ_FADE":
        return -dz
    if n == "PB_DRIVEZ_GO":
        return dz
    if n == "PB_DRIVE_EXMKT_FADE":
        m = np.nanmean(np.where(B.in_uni, dz, np.nan), axis=1, keepdims=True)
        return -(dz - m)
    if n == "PB_DRIVE_CONF_FADE":
        return np.where(np.sign(gz) == np.sign(dz), -dz, 0.0)
    if n == "PB_GAPDRIVE_CROSS":
        return -gz * dz
    raise KeyError(n)


def run_panelB(cfg, B: PanelB, dmask, gapshift):
    px_in = B.p59 if gapshift else B.p49
    ok = B.base_ok(cfg["need_gap"])
    sc = cfg.get("_scoreB")
    if sc is None:
        sc = panelB_score(cfg, B)
    if cfg.get("top"):
        a = np.where(ok, B.adv, np.nan)
        rk = np.argsort(np.argsort(-np.nan_to_num(a, nan=-1.0), axis=1), axis=1)
        ok = ok & (rk < cfg["top"])
    ok = ok & np.isfinite(sc)
    ok = ok & (ok.sum(axis=1) >= 20)[:, None]
    w = weights_from_score(np.where(ok, sc, np.nan), ok)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.nan_to_num(np.where(ok, B.pc / px_in - 1.0, 0.0))
    return (w * r).sum(axis=1)[dmask], np.abs(w).sum(axis=1)[dmask]


# ----------------------------------------------------------------- config table
def build_configs(P: PanelA, F: FeatA):
    cfgs = []

    def A(name, uni, score, s, family):
        cfgs.append(dict(name=name, panel="A", universe=uni, score=score, s=s,
                         family=family, _P=P))

    def Bc(name, family, need_gap=True, top=None):
        cfgs.append(dict(name=name, panel="B", family=family, need_gap=need_gap, top=top))

    xs_med = np.nanmedian(F.er, axis=1, keepdims=True)

    # --- Panel A: path shape
    A("PA_ER_DRIVE_CONT", "MEGA", F.r60 * F.er, 11, "path_shape")
    A("PA_ER_DRIVE_FADE", "MEGA", -F.r60 * F.er, 11, "path_shape")
    A("PA_CHOP_DRIVE_FADE", "MEGA", -F.r60 * F.chop, 11, "path_shape")
    A("PA_ER_HI_CONT", "MEGA", np.where(F.er > xs_med, F.r60, 0.0) * np.where(np.isfinite(F.er), 1.0, np.nan),
      11, "path_shape")

    # --- Panel A: range-scaled drive
    A("PA_RCOMP_DRIVE_CONT", "MEGA", F.r60 / np.where(F.rr > 0, F.rr, np.nan), 11, "range_scaled")
    A("PA_REXP_DRIVE_FADE", "MEGA", -F.r60 * F.rr, 11, "range_scaled")
    A("PA_H1LOC_FADE", "MEGA", -(F.h1loc - 0.5), 11, "range_scaled")
    A("PA_RCOMP_DRIVE_CONT_ETF", "LIQETF", F.r60 / np.where(F.rr > 0, F.rr, np.nan), 11, "range_scaled")

    # --- Panel A: opening-print dislocation
    A("PA_ODISL_FADE", "MEGA", -F.odisl, 1, "open_disloc")
    A("PA_ODISL_CONT", "MEGA", F.odisl, 1, "open_disloc")
    A("PA_ODISL_X_GAP", "MEGA", -F.odisl * np.sign(F.gapz), 1, "open_disloc")

    # --- Panel A: open drive -> close drive
    A("PA_OD30_CD_CONT", "MEGA", F.r30, 70, "od_to_cd")
    A("PA_OD30_CD_FADE", "MEGA", -F.r30, 70, "od_to_cd")
    A("PA_GAP_CD_FADE", "MEGA", -F.gapz, 70, "od_to_cd")

    # --- Panel B: gap families
    Bc("PB_GAPZ_FADE", "gap")
    Bc("PB_GAPZ_GO", "gap")
    Bc("PB_IDIOGAP_FADE", "gap")
    Bc("PB_GAPGO_CONFIRMED", "gap")
    Bc("PB_GAPFADE_UNCONF", "gap")
    Bc("PB_TOTMOVE_FADE", "gap")
    Bc("PB_GAPZ_FADE_T150", "gap", top=150)

    # --- Panel B: vol-scaled drive
    Bc("PB_DRIVEZ_FADE", "drive", need_gap=False)
    Bc("PB_DRIVEZ_GO", "drive", need_gap=False)
    Bc("PB_DRIVE_EXMKT_FADE", "drive", need_gap=False)
    Bc("PB_DRIVE_CONF_FADE", "drive")
    Bc("PB_GAPDRIVE_CROSS", "drive")
    return cfgs


# ----------------------------------------------------------------- scoring
def score_all(da, db, F, B, cfgs, tag):
    rows = {}
    for cfg in cfgs:
        rec = {"name": cfg["name"], "family": cfg["family"], "panel": cfg["panel"],
               "universe": cfg.get("universe", "TOP%d" % (cfg.get("top") or 500))}
        for gapshift, lab in ((0, "primary"), (1, "gap")):
            if cfg["panel"] == "A":
                g, ge = run_panelA(cfg, F, da, gapshift)
                auction = False
            else:
                g, ge = run_panelB(cfg, B, db, gapshift)
                auction = True
            rec[f"{lab}_gross_sharpe"] = sharpe(g)
            rec[f"{lab}_turnover"] = float(np.nanmean(ge) * (1.0 if auction else 2.0))
            rec[f"{lab}_gross_bps_day"] = float(np.nanmean(g) * 1e4)
            for bp in RUNGS:
                rec[f"{lab}_net_{bp}"] = sharpe(net_series(g, ge, bp, auction))
            rec[f"{lab}_n_days"] = int(np.isfinite(g).sum())
            tp = np.nanmean(ge) * (1.0 if auction else 2.0)
            rec[f"{lab}_breakeven_bp"] = float(np.nanmean(g) * 1e4 / tp) if tp > 0 else float("nan")
            if lab == "primary":
                rec["primary_series"] = [float(v) for v in g]
        rows[cfg["name"]] = rec
        print(f"  [{tag}] {cfg['name']:26s} gross {rec['primary_gross_sharpe']:+6.2f} "
              f"net1 {rec['primary_net_1.0']:+6.2f} gapnet1 {rec['gap_net_1.0']:+6.2f} "
              f"turn {rec['primary_turnover']:.2f} be {rec['primary_breakeven_bp']:.2f}bp", flush=True)
    return rows


# ----------------------------------------------------------------- nulls
def adv_buckets(adv, valid, nb=10):
    a = np.where(valid, np.nan_to_num(adv, nan=0.0), np.inf)
    rank = np.argsort(np.argsort(a, axis=1, kind="stable"), axis=1)
    cnt = valid.sum(axis=1, keepdims=True).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        b = np.floor(rank / np.maximum(cnt, 1) * nb)
    return np.where(valid, np.clip(b, 0, nb - 1), nb).astype(np.int16)


def shuffle_in_buckets(sc, buck, rng):
    D, S = sc.shape
    rows = np.arange(D)[:, None]
    pos_order = np.argsort(buck, axis=1, kind="stable")
    val_order = np.argsort(buck.astype(np.float64) + rng.random((D, S)), axis=1, kind="stable")
    out = np.empty_like(sc, dtype=float)
    out[rows, pos_order] = np.asarray(sc, dtype=float)[rows, val_order]
    return out


def permutation_null_gross(cfg, F, B, da, db, rng, n=500):
    draws = []
    if cfg["panel"] == "A":
        P = cfg["_P"]
        cols = P.cols(cfg["universe"])
        e = min(cfg["s"] + 1, 76)
        px_in = P.vw[:, e, :][:, cols][da]
        px_out = P.vw[:, 77, :][:, cols][da]
        sc = cfg["score"][:, cols][da].astype(float)
        valid = (np.isfinite(sc) & np.isfinite(px_in) & np.isfinite(px_out)
                 & (px_in > 0) & (px_out > 0))
        valid = valid & (valid.sum(axis=1) >= 10)[:, None]
        r = np.nan_to_num(np.where(valid, px_out / px_in - 1.0, 0.0))
        buck = adv_buckets(P.adv[:, cols][da], valid)
        sc0 = np.nan_to_num(sc)
        for _ in range(n):
            w = weights_from_score(shuffle_in_buckets(sc0, buck, rng), valid)
            draws.append(sharpe((w * r).sum(axis=1)))
    else:
        ok = B.base_ok(cfg["need_gap"])
        sc = panelB_score(cfg, B)
        if cfg.get("top"):
            a = np.where(ok, B.adv, np.nan)
            rk = np.argsort(np.argsort(-np.nan_to_num(a, nan=-1.0), axis=1), axis=1)
            ok = ok & (rk < cfg["top"])
        ok = ok & np.isfinite(sc)
        ok = ok & (ok.sum(axis=1) >= 20)[:, None]
        ok = ok[db]
        sc0 = np.nan_to_num(sc[db])
        with np.errstate(invalid="ignore", divide="ignore"):
            r = np.nan_to_num(np.where(ok, (B.pc / B.p49)[db] - 1.0, 0.0))
        buck = adv_buckets(B.adv[db], ok)
        for _ in range(n):
            w = weights_from_score(shuffle_in_buckets(sc0, buck, rng), ok)
            draws.append(sharpe((w * r).sum(axis=1)))
    return draws


# ----------------------------------------------------------------- self-test
def selftest(P, F, B, da):
    rng = np.random.default_rng(20260825)
    cols = P.cols("MEGA")
    out = {}
    px_in = P.vw[:, 12, :]
    px_out = P.vw[:, 77, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        fwd = px_out / px_in - 1.0
    base = dict(name="ST", panel="A", universe="MEGA", s=11, family="st", _P=P)

    # 1 planted edge: the realised forward return itself
    c1 = dict(base, score=np.where(np.isfinite(fwd), fwd, np.nan))
    g, ge = run_panelA(c1, F, da, 0)
    out["planted_edge_gross"] = sharpe(g)
    c2 = dict(base, score=-c1["score"])
    g2, _ = run_panelA(c2, F, da, 0)
    out["planted_edge_negated"] = sharpe(g2)

    # 2 random score
    c3 = dict(base, score=rng.standard_normal(F.r60.shape))
    g3, _ = run_panelA(c3, F, da, 0)
    out["random_score_gross"] = sharpe(g3)

    # 3 planted ONE-BAR artefact: score = the return of the entry bar only
    with np.errstate(invalid="ignore", divide="ignore"):
        onebar = P.vw[:, 12, :] / P.vw[:, 11, :] - 1.0
    c4 = dict(base, score=np.where(np.isfinite(onebar), onebar, np.nan))
    ga, gea = run_panelA(c4, F, da, 0)
    gb, geb = run_panelA(c4, F, da, 1)
    out["onebar_artefact_primary"] = sharpe(ga)
    out["onebar_artefact_gapfill"] = sharpe(gb)
    out["gate_detects_artefact"] = bool(sharpe(gb) < 0.5 * sharpe(ga))

    # 4 Panel B planted edge
    cb = dict(name="PB_GAPZ_FADE", panel="B", family="st", need_gap=True, top=None)
    with np.errstate(invalid="ignore", divide="ignore"):
        cb["_scoreB"] = B.pc / B.p49 - 1.0
    db = (B.dates >= DESIGN[0]) & (B.dates <= DESIGN[1])
    gB, _ = run_panelB(cb, B, db, 0)
    out["panelB_planted_edge_gross"] = sharpe(gB)
    return out


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True,
                    choices=["selftest", "design", "null", "heldout", "presample"])
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    P = PanelA()
    F = FeatA(P)
    B = PanelB()
    cfgs = build_configs(P, F)

    if args.stage == "selftest":
        da = (P.daykey >= DESIGN[0]) & (P.daykey <= DESIGN[1])
        res = selftest(P, F, B, da)
        print(json.dumps(res, indent=1))
        (OUTDIR / "INVENT_0825_opendrive_selftest.json").write_text(json.dumps(res, indent=1))
        return

    if args.stage in ("heldout", "presample") and not args.only:
        raise SystemExit("held-out / pre-sample refuse to run without an explicit --only shortlist")
    if args.only:
        keep = set(args.only.split(","))
        cfgs = [c for c in cfgs if c["name"] in keep]
        missing = keep - {c["name"] for c in cfgs}
        if missing:
            raise SystemExit(f"unknown configs: {sorted(missing)}")

    win = {"design": DESIGN, "null": DESIGN, "heldout": HELDOUT, "presample": PRESAMPLE}[args.stage]
    da = (P.daykey >= win[0]) & (P.daykey <= win[1])
    db = (B.dates >= win[0]) & (B.dates <= win[1])
    print(f"stage={args.stage} window={win} panelA_days={da.sum()} panelB_days={db.sum()}", flush=True)

    if args.stage in ("design", "heldout", "presample"):
        if args.stage == "presample":
            cfgs = [c for c in cfgs if c["panel"] == "B"]
            if not cfgs:
                raise SystemExit("pre-sample is Panel B only; no Panel B config in --only")
        rows = score_all(da, db, F, B, cfgs, args.stage)
        out = OUTDIR / f"INVENT_0825_opendrive_{args.stage}.json"
        out.write_text(json.dumps({"window": win, "n_configs": len(cfgs), "rungs": RUNGS,
                                   "headline_bp": HEADLINE, "fee_bp_per_turnover": FEE_BP,
                                   "configs": rows}, indent=1))
        print("wrote", out, flush=True)
        return

    # ---- null stage
    design = json.loads((OUTDIR / "INVENT_0825_opendrive_design.json").read_text())
    names = [c["name"] for c in cfgs]
    series = {}
    for cfg in cfgs:
        if cfg["panel"] == "A":
            g, ge = run_panelA(cfg, F, da, 0); auction = False
        else:
            g, ge = run_panelB(cfg, B, db, 0); auction = True
        series[cfg["name"]] = (net_series(g, ge, HEADLINE, auction), g)
    L = min(len(v[0]) for v in series.values())
    net = np.vstack([series[n][0][:L] for n in names])
    gro = np.vstack([series[n][1][:L] for n in names])
    rng = np.random.default_rng(20260825)
    res = {"n_configs": len(names), "n_days": int(L)}
    for lab, mat in (("net", net), ("gross", gro)):
        dm = mat - mat.mean(axis=1, keepdims=True)
        block, R = 5, 2000
        nblk = int(np.ceil(L / block))
        best = np.empty(R)
        for r in range(R):
            st = rng.integers(0, L - block, size=nblk)
            idx = (st[:, None] + np.arange(block)[None, :]).ravel()[:L]
            s = dm[:, idx]
            sh = s.mean(axis=1) / np.maximum(s.std(axis=1, ddof=1), 1e-18) * ANN
            best[r] = sh.max()
        res[lab] = {"mean": float(best.mean()), "p95": float(np.percentile(best, 95)),
                    "p99": float(np.percentile(best, 99))}
        print(f"  bootstrap best-of-{len(names)} {lab}: mean {res[lab]['mean']:+.2f} "
              f"p95 {res[lab]['p95']:+.2f} p99 {res[lab]['p99']:+.2f}", flush=True)
    res["analytic_sqrt2lnN"] = float(np.sqrt(2 * np.log(len(names))) / np.sqrt(L / 252.0))

    rank = sorted(names, key=lambda n: -(design["configs"][n]["primary_gross_sharpe"]
                                         if np.isfinite(design["configs"][n]["primary_gross_sharpe"]) else -9))
    perm = {}
    for nm in rank[:8]:
        cfg = next(c for c in cfgs if c["name"] == nm)
        obs = sharpe(series[nm][1])
        draws = permutation_null_gross(cfg, F, B, da, db, rng, n=500)
        d = np.asarray(draws, float)
        p = float((np.sum(d >= obs) + 1) / (d.size + 1))
        perm[nm] = {"observed_gross_sharpe": obs, "perm_mean": float(np.nanmean(d)),
                    "perm_p95": float(np.nanpercentile(d, 95)), "p_value": p, "n_perm": int(d.size)}
        print(f"  perm {nm:26s} obs {obs:+.2f} nullmean {perm[nm]['perm_mean']:+.2f} "
              f"nullp95 {perm[nm]['perm_p95']:+.2f} p={p:.4f}", flush=True)
    res["permutation_on_gross"] = perm
    out = OUTDIR / "INVENT_0825_opendrive_null.json"
    out.write_text(json.dumps(res, indent=1))
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
