#!/usr/bin/env python3
"""INVENT_0823 — intraday microstructure beyond the auction.

28 pre-registered low-turnover intraday formulas, scored on the design window
(2021-01-04..2024-12-31) with a realistic later fill and a mandatory one-bar-gap
re-entry test.  See research/trading_bot/INVENT_0823_intramicro_PREREGISTRATION.md.

Stages:
  --stage design   score all 28, both fills, all cost rungs -> _design.json
  --stage null     block-bootstrap best-of-N bar + ADV-slot permutation -> _null.json
  --stage heldout  frozen shortlist only (refuses to run without --only)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

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
FEE_BP = 0.15          # SEC 31 + FINRA TAF per unit turnover
ANN = np.sqrt(252.0)

MEGA = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "BRK.B",
        "JPM", "XOM", "UNH", "JNJ", "V", "PG", "HD", "MA", "COST", "WMT", "BAC", "CVX",
        "LLY", "ABBV", "MRK", "PEP", "KO", "ORCL", "CRM", "AMD", "INTC", "NFLX", "ADBE", "CSCO"]
LIQETF = ["SPY", "VTI", "QQQ", "IWM", "DIA", "MDY", "IJR", "IWF", "IWD", "MTUM", "USMV",
          "QUAL", "VLUE", "SPYG", "SPYV", "GLD", "SLV", "USO", "UNG", "EFA", "EEM", "EWJ",
          "FXI", "EWZ", "AGG", "LQD", "HYG", "JNK", "TLT", "IEF", "SHY", "TIP", "XLK",
          "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH",
          "KRE", "IBB", "XBI", "ITB", "GDX"]


# ---------------------------------------------------------------- panel loading
class PanelA:
    def __init__(self) -> None:
        z = np.load(CUBE, allow_pickle=True)
        self.daykey = z["daykey"]
        self.syms = list(z["syms"])
        self.o = z["o"]; self.h = z["h"]; self.l = z["l"]
        self.c = z["c"]; self.vw = z["vw"]; self.dv = z["dv"]; self.nt = z["nt"]
        self.D = self.daykey.size
        self.idx = {s: i for i, s in enumerate(self.syms)}
        # trailing 20-day mean dollar volume, strictly prior days
        day_dv = np.nansum(self.dv, axis=1)                      # (D,S)
        cs = np.nancumsum(np.nan_to_num(day_dv), axis=0)
        adv = np.full_like(day_dv, np.nan)
        adv[20:] = (cs[19:-1] - np.vstack([np.zeros((1, day_dv.shape[1])), cs[:-21]])) / 20.0
        self.adv = adv

    def cols(self, universe: str) -> np.ndarray:
        names = MEGA if universe == "MEGA" else LIQETF
        return np.array([self.idx[s] for s in names if s in self.idx])


def trailing_median(x: np.ndarray, w: int) -> np.ndarray:
    """Median of the previous `w` rows, strictly excluding the current row."""
    D, S = x.shape
    out = np.full_like(x, np.nan)
    for d in range(w, D):
        out[d] = np.nanmedian(x[d - w:d], axis=0)
    return out


# ---------------------------------------------------------------- feature block
class Feat:
    """All per-(day,symbol) features the 28 formulas need, computed once."""

    def __init__(self, P: PanelA) -> None:
        o, h, l, c, vw, dv, nt = P.o, P.h, P.l, P.c, P.vw, P.dv, P.nt
        D, NS, S = c.shape
        self.P = P
        op = o[:, 0, :]
        self.op = op
        self.r30 = c[:, 5, :] / op - 1.0
        self.r15 = c[:, 2, :] / op - 1.0
        self.r90 = c[:, 17, :] / op - 1.0
        self.r69 = c[:, 69, :] / op - 1.0
        prev_close = np.full_like(op, np.nan)
        prev_close[1:] = c[:-1, 77, :]
        self.gap = op / prev_close - 1.0

        # running VWAP up to slot s
        wsum = np.nancumsum(np.nan_to_num(vw * dv), axis=1)
        vsum = np.nancumsum(np.nan_to_num(dv), axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.rvwap = wsum / vsum                              # (D,78,S)

        # close-location-value order-flow proxy over bars 0..17
        rng = h - l
        with np.errstate(invalid="ignore", divide="ignore"):
            clv = ((c - l) - (h - c)) / rng
        clv = np.where(np.isfinite(clv), clv, 0.0)
        num = np.nansum(clv[:, :18, :] * np.nan_to_num(dv[:, :18, :]), axis=1)
        den = np.nansum(np.nan_to_num(dv[:, :18, :]), axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.ofi = np.where(den > 0, num / den, np.nan)

        dv90 = np.nansum(np.nan_to_num(dv[:, :18, :]), axis=1)
        nt90 = np.nansum(np.nan_to_num(nt[:, :18, :]), axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            ats = np.where(nt90 > 0, dv90 / nt90, np.nan)
        self.ats_rel = ats / trailing_median(ats, 20) - 1.0
        self.dv90_rel = np.where(dv90 > 0, dv90, np.nan) / trailing_median(np.where(dv90 > 0, dv90, np.nan), 20) - 1.0
        ntA = np.nansum(np.nan_to_num(nt[:, :12, :]), axis=1) / 12.0
        ntB = np.nansum(np.nan_to_num(nt[:, 12:18, :]), axis=1) / 6.0
        with np.errstate(invalid="ignore", divide="ignore"):
            self.nt_accel = np.where(ntA > 0, ntB / ntA - 1.0, np.nan)

        # opening ranges
        self.or60_hi = np.nanmax(h[:, :12, :], axis=1)
        self.or60_lo = np.nanmin(l[:, :12, :], axis=1)
        self.or30_hi = np.nanmax(h[:, :6, :], axis=1)
        self.or30_lo = np.nanmin(l[:, :6, :], axis=1)

        # volume profile over bars 0..23 -> POC / VAH / VAL
        self.poc, self.vah, self.val, self.rng2h = self._value_area(h[:, :24, :], l[:, :24, :],
                                                                    vw[:, :24, :], dv[:, :24, :])
        # previous session POC (full day)
        poc_full, _, _, rng_full = self._value_area(h, l, vw, dv)
        self.pd_poc = np.full_like(poc_full, np.nan)
        self.pd_poc[1:] = poc_full[:-1]
        self.pd_rng = np.full_like(rng_full, np.nan)
        self.pd_rng[1:] = rng_full[:-1]

    @staticmethod
    def _value_area(h, l, vw, dv, nbins: int = 20, frac: float = 0.70):
        D, NS, S = h.shape
        hi = np.nanmax(h, axis=1); lo = np.nanmin(l, axis=1)
        rng = hi - lo
        poc = np.full((D, S), np.nan); vah = np.full((D, S), np.nan); val = np.full((D, S), np.nan)
        ok_rng = np.isfinite(rng) & (rng > 0)
        dvc = np.nan_to_num(dv)
        for d in range(D):
            m = ok_rng[d]
            if not m.any():
                continue
            cols = np.where(m)[0]
            lo_d = lo[d, cols]; rng_d = rng[d, cols]
            b = np.floor((vw[d][:, cols] - lo_d) / rng_d * nbins)
            b = np.where(np.isfinite(b), b, -1)
            b = np.clip(b, -1, nbins - 1).astype(np.int64)
            prof = np.zeros((nbins, cols.size))
            w = dvc[d][:, cols]
            valid = b >= 0
            for k in range(nbins):
                prof[k] = (w * (b == k)).sum(axis=0)
            tot = prof.sum(axis=0)
            good = tot > 0
            if not good.any():
                continue
            centres = lo_d[None, :] + (np.arange(nbins)[:, None] + 0.5) / nbins * rng_d[None, :]
            pk = prof.argmax(axis=0)
            poc[d, cols] = np.where(good, centres[pk, np.arange(cols.size)], np.nan)
            # expand from POC toward the heavier neighbour until frac of volume is covered
            lo_i = pk.copy(); hi_i = pk.copy()
            acc = prof[pk, np.arange(cols.size)].copy()
            target = frac * tot
            for _ in range(nbins):
                need = acc < target
                if not need.any():
                    break
                up_ok = hi_i < nbins - 1
                dn_ok = lo_i > 0
                up_v = np.where(up_ok, prof[np.clip(hi_i + 1, 0, nbins - 1), np.arange(cols.size)], -1.0)
                dn_v = np.where(dn_ok, prof[np.clip(lo_i - 1, 0, nbins - 1), np.arange(cols.size)], -1.0)
                take_up = need & up_ok & (up_v >= dn_v)
                take_dn = need & dn_ok & ~take_up
                acc = acc + np.where(take_up, up_v, 0.0) + np.where(take_dn, dn_v, 0.0)
                hi_i = hi_i + take_up
                lo_i = lo_i - take_dn
                if not (take_up | take_dn).any():
                    break
            vah[d, cols] = np.where(good, lo_d + (hi_i + 1.0) / nbins * rng_d, np.nan)
            val[d, cols] = np.where(good, lo_d + lo_i / nbins * rng_d, np.nan)
        return poc, vah, val, rng


# ---------------------------------------------------------------- config table
def build_configs(F: Feat):
    """Return list of dicts: name, universe, score (D,S), entry slot s+1, kind."""
    P = F.P
    c = P.c
    cfgs = []

    def add(name, uni, score, s, family, extra=None):
        cfgs.append(dict(name=name, universe=uni, score=score, s=s, family=family,
                         panel="A", extra=extra or {}))

    # ---- A opening drive
    for uni in ("MEGA", "LIQETF"):
        pass
    add("A1_OD30_CONT", "MEGA", F.r30, 5, "opening_drive")
    add("A2_OD30_FADE", "MEGA", -F.r30, 5, "opening_drive")
    add("A3_OD15_CONT", "MEGA", F.r15, 2, "opening_drive")

    # A4 residual on a 60-day rolling beta to the universe-mean first-30 return
    cols = P.cols("MEGA")
    x = F.r30
    m = np.nanmean(x[:, cols], axis=1)
    D = x.shape[0]
    beta = np.full_like(x, np.nan)
    for d in range(60, D):
        xs = x[d - 60:d]
        ms = m[d - 60:d]
        good = np.isfinite(ms)
        if good.sum() < 40:
            continue
        mm = ms[good] - np.nanmean(ms[good])
        vv = np.nansum(mm * mm)
        if vv <= 0:
            continue
        xg = xs[good]
        xd = xg - np.nanmean(xg, axis=0)
        beta[d] = np.nansum(xd * mm[:, None], axis=0) / vv
    a4 = x - beta * m[:, None]
    add("A4_OD30_CONT_RESID", "MEGA", a4, 5, "opening_drive")
    add("A5_DRIVE_EX_GAP", "MEGA", F.r30 - F.gap, 5, "opening_drive")

    # ---- B order flow / trade size
    add("B1_OFI_MORN_CONT", "MEGA", F.ofi, 17, "order_flow")
    add("B2_OFI_MORN_FADE", "MEGA", -F.ofi, 17, "order_flow")
    add("B3_TRDSIZE_TILT", "MEGA", F.ats_rel * F.r90, 17, "order_flow")
    add("B4_VOLFRONT_DRIVE", "MEGA", F.dv90_rel * F.r90, 17, "order_flow")
    add("B5_NTRADE_ACCEL", "MEGA", F.nt_accel * F.r90, 17, "order_flow")

    # ---- C vwap deviation
    dev41 = c[:, 41, :] / F.rvwap[:, 41, :] - 1.0
    dev11 = c[:, 11, :] / F.rvwap[:, 11, :] - 1.0
    add("C1_VWAPDEV_MID_REV", "MEGA", -dev41, 41, "vwap_dev")
    add("C2_VWAPDEV_MID_CONT", "MEGA", dev41, 41, "vwap_dev")
    add("C3_VWAPDEV_1030_REV", "MEGA", -dev11, 11, "vwap_dev")
    cfgs.append(dict(name="C4_VWAPDEV_TWOLEG", universe="MEGA", family="vwap_dev", panel="A",
                     legs=[(-dev11, 11, 0.5), (-dev41, 41, 0.5)], score=None, s=None, extra={}))

    # ---- D opening-range breakout
    or_mid = (F.or60_hi + F.or60_lo) / 2.0
    or_rng = F.or60_hi - F.or60_lo
    with np.errstate(invalid="ignore", divide="ignore"):
        x23 = (c[:, 23, :] - or_mid) / or_rng
    d1 = np.where(np.abs(x23) > 0.5, x23, 0.0)
    d1 = np.where(np.isfinite(x23), d1, np.nan)
    add("D1_ORB_BREAK_XS", "MEGA", d1, 23, "orb")
    add("D2_ORB_FADE_XS", "MEGA", -d1, 23, "orb")
    or_mid30 = (F.or30_hi + F.or30_lo) / 2.0
    or_rng30 = F.or30_hi - F.or30_lo
    with np.errstate(invalid="ignore", divide="ignore"):
        x11 = (c[:, 11, :] - or_mid30) / or_rng30
    d3 = np.where(np.abs(x11) > 0.5, x11, 0.0)
    d3 = np.where(np.isfinite(x11), d3, np.nan)
    add("D3_ORB30_BREAK", "MEGA", d3, 11, "orb")
    with np.errstate(invalid="ignore", divide="ignore"):
        up = (c[:, 23, :] - F.or60_hi) / or_rng
        dn = (c[:, 23, :] - F.or60_lo) / or_rng
    ext = np.where(c[:, 23, :] > F.or60_hi, up, np.where(c[:, 23, :] < F.or60_lo, dn, 0.0))
    ext = np.where(np.isfinite(up) & np.isfinite(dn), ext, np.nan)
    add("D4_ORB_EXTENSION", "MEGA", ext, 23, "orb")

    # ---- E value area
    c23 = c[:, 23, :]
    e1 = np.where(c23 > F.vah, -1.0, np.where(c23 < F.val, 1.0, 0.0))
    e1 = np.where(np.isfinite(F.vah) & np.isfinite(F.val) & np.isfinite(c23), e1, np.nan)
    add("E1_VA_REJECT", "MEGA", e1, 23, "value_area")
    add("E2_VA_ACCEPT", "MEGA", -e1, 23, "value_area")
    with np.errstate(invalid="ignore", divide="ignore"):
        e3 = (F.poc - c23) / F.rng2h
    add("E3_POC_MAGNET", "MEGA", e3, 23, "value_area")
    with np.errstate(invalid="ignore", divide="ignore"):
        e4 = (F.pd_poc - c[:, 5, :]) / F.pd_rng
    add("E4_PDPOC_MAGNET", "MEGA", e4, 5, "value_area")

    # ---- F late-day drift, panel A
    add("F1_LD_CONT", "MEGA", F.r69, 69, "late_day")
    add("F2_LD_REV", "MEGA", -F.r69, 69, "late_day")
    dev69 = c[:, 69, :] / F.rvwap[:, 69, :] - 1.0
    add("F3_LD_VWAPDEV_REV", "MEGA", -dev69, 69, "late_day")

    # ---- G late-day drift, panel B breadth (handled separately)
    for nm, sgn, top in (("G1_LD500_CONT", 1.0, 0), ("G2_LD500_REV", -1.0, 0),
                         ("G3_LD500_CONT_TOP150", 1.0, 150)):
        cfgs.append(dict(name=nm, universe="TOP500_PIT", family="late_day", panel="B",
                         sign=sgn, top=top, score=None, s=None, extra={}))
    return cfgs


# ---------------------------------------------------------------- backtest core
def weights_from_score(sc: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Cross-sectional demean then L1-normalise to gross 1.0, per row."""
    w = np.where(valid, sc, np.nan)
    mu = np.nanmean(w, axis=1, keepdims=True)
    w = np.where(valid, w - mu, 0.0)
    g = np.abs(w).sum(axis=1, keepdims=True)
    return np.where(g > 0, w / np.maximum(g, 1e-12), 0.0)


def run_panelA(cfg, F: Feat, dmask: np.ndarray, gapshift: int) -> np.ndarray:
    """Daily gross PnL series over the selected days (aligned to P.daykey[dmask])."""
    P = F.P
    cols = P.cols(cfg["universe"])
    vw = P.vw
    legs = cfg.get("legs")
    if legs is None:
        legs = [(cfg["score"], cfg["s"], 1.0)]
    total = np.zeros(P.D)
    gross_exp = np.zeros(P.D)
    for score, s, wt in legs:
        e = s + 1 + gapshift
        if e > 76:
            e = 76
        px_in = vw[:, e, :][:, cols]
        px_out = vw[:, 77, :][:, cols]
        sc = score[:, cols]
        valid = np.isfinite(sc) & np.isfinite(px_in) & np.isfinite(px_out) & (px_in > 0) & (px_out > 0)
        enough = valid.sum(axis=1) >= 10
        valid = valid & enough[:, None]
        w = weights_from_score(sc, valid) * wt
        with np.errstate(invalid="ignore", divide="ignore"):
            r = np.where(valid, px_out / px_in - 1.0, 0.0)
        r = np.nan_to_num(r)
        total += (w * r).sum(axis=1)
        gross_exp += np.abs(w).sum(axis=1)
    return total[dmask], gross_exp[dmask]


class PanelB:
    def __init__(self) -> None:
        z = np.load(PANELB, allow_pickle=True)
        self.dates = z["dates"]
        self.po = z["po"]; self.p29 = z["p29"]; self.p49 = z["p49"]; self.p59 = z["p59"]
        self.pc = z["pc"]; self.in_uni = z["in_uni"]; self.adv = z["advusd"]


def run_panelB(cfg, B: PanelB, dmask: np.ndarray, gapshift: int):
    px_in = B.p59 if gapshift else B.p49
    ok = (B.in_uni & np.isfinite(B.po) & np.isfinite(B.p29) & np.isfinite(px_in)
          & np.isfinite(B.pc) & (B.po > 0) & (B.p29 > 0) & (px_in > 0) & (B.pc > 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        sc = cfg["sign"] * (B.p29 / B.po - 1.0)
    if cfg["top"]:
        a = np.where(ok, B.adv, np.nan)
        rank = np.argsort(np.argsort(-np.nan_to_num(a, nan=-1.0), axis=1), axis=1)
        ok = ok & (rank < cfg["top"])
    enough = ok.sum(axis=1) >= 20
    ok = ok & enough[:, None]
    w = weights_from_score(np.where(ok, sc, np.nan), ok)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(ok, B.pc / px_in - 1.0, 0.0)
    r = np.nan_to_num(r)
    return (w * r).sum(axis=1)[dmask], np.abs(w).sum(axis=1)[dmask]


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    if x.size < 30 or not np.isfinite(x).all() or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * ANN)


def net_series(gross: np.ndarray, gexp: np.ndarray, bp: float, auction_exit: bool) -> np.ndarray:
    """Turnover = entry |w| + exit |w|.  Panel B's exit is the closing auction: fee only."""
    entry = gexp * (bp + FEE_BP) / 1e4
    exit_ = gexp * ((0.0 if auction_exit else bp) + FEE_BP) / 1e4
    return gross - entry - exit_


# ---------------------------------------------------------------- stages
def score_all(days_a, days_b, F, B, cfgs, tag):
    rows = {}
    for cfg in cfgs:
        rec = {"name": cfg["name"], "family": cfg["family"], "universe": cfg["universe"],
               "panel": cfg["panel"]}
        for gapshift, lab in ((0, "primary"), (1, "gap")):
            if cfg["panel"] == "A":
                g, ge = run_panelA(cfg, F, days_a, gapshift)
                auction = False
            else:
                g, ge = run_panelB(cfg, B, days_b, gapshift)
                auction = True
            rec[f"{lab}_gross_sharpe"] = sharpe(g)
            rec[f"{lab}_turnover"] = float(np.nanmean(ge) * 2.0)
            rec[f"{lab}_gross_bps_day"] = float(np.nanmean(g) * 1e4)
            for bp in RUNGS:
                rec[f"{lab}_net_{bp}"] = sharpe(net_series(g, ge, bp, auction))
            rec[f"{lab}_n_days"] = int(np.isfinite(g).sum())
            # break-even one-way cost in bp per unit turnover
            tp = np.nanmean(ge) * (2.0 if not auction else 1.0)
            rec[f"{lab}_breakeven_bp"] = float(np.nanmean(g) * 1e4 / tp) if tp > 0 else float("nan")
            rec[f"{lab}_series"] = g.tolist() if lab == "primary" else None
            rec[f"{lab}_gexp"] = float(np.nanmean(ge))
        rows[cfg["name"]] = rec
        print(f"  [{tag}] {cfg['name']:24s} gross {rec['primary_gross_sharpe']:+6.2f} "
              f"net1 {rec['primary_net_1.0']:+6.2f} gap-net1 {rec['gap_net_1.0']:+6.2f} "
              f"turn {rec['primary_turnover']:.2f} be {rec['primary_breakeven_bp']:.2f}bp", flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["design", "null", "heldout", "presample"])
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    P = PanelA()
    F = Feat(P)
    B = PanelB()
    cfgs = build_configs(F)
    if args.stage in ("heldout", "presample") and not args.only:
        raise SystemExit("held-out/pre-sample stages refuse to run without an explicit --only shortlist")
    if args.only:
        keep = set(args.only.split(","))
        cfgs = [c for c in cfgs if c["name"] in keep]

    win = {"design": DESIGN, "null": DESIGN, "heldout": HELDOUT, "presample": PRESAMPLE}[args.stage]
    da = (P.daykey >= win[0]) & (P.daykey <= win[1])
    db = (B.dates >= win[0]) & (B.dates <= win[1])
    print(f"stage={args.stage} window={win} panelA days={da.sum()} panelB days={db.sum()}", flush=True)

    if args.stage in ("design", "heldout", "presample"):
        rows = score_all(da, db, F, B, cfgs, args.stage)
        suffix = {"design": "design", "heldout": "heldout", "presample": "presample"}[args.stage]
        out = OUTDIR / f"INVENT_0823_intramicro_{suffix}.json"
        payload = {"window": win, "n_configs": len(cfgs), "rungs": RUNGS, "headline_bp": HEADLINE,
                   "fee_bp_per_turnover": FEE_BP, "configs": rows}
        out.write_text(json.dumps(payload, indent=1))
        print("wrote", out, flush=True)
        return

    # ---- null stage
    design = json.loads((OUTDIR / "INVENT_0823_intramicro_design.json").read_text())
    names = list(design["configs"])
    # rebuild net series at the headline rung for the bootstrap
    series = {}
    for cfg in cfgs:
        if cfg["panel"] == "A":
            g, ge = run_panelA(cfg, F, da, 0)
            auction = False
        else:
            g, ge = run_panelB(cfg, B, db, 0)
            auction = True
        series[cfg["name"]] = (net_series(g, ge, HEADLINE, auction), g)
    L = min(len(v[0]) for v in series.values())
    net = np.vstack([series[n][0][:L] for n in names])
    gro = np.vstack([series[n][1][:L] for n in names])
    rng = np.random.default_rng(20260823)
    res = {}
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
        print(f"  bootstrap best-of-{len(names)} {lab}: p95 {res[lab]['p95']:+.2f}", flush=True)
    res["analytic_sqrt2lnN"] = float(np.sqrt(2 * np.log(len(names))) / np.sqrt(L / 252.0))
    res["n_configs"] = len(names)
    res["n_days"] = int(L)

    # ---- ADV-slot signal permutation for the top-6 by design net@headline
    rank = sorted(names, key=lambda n: -(design["configs"][n]["primary_net_1.0"]
                                         if np.isfinite(design["configs"][n]["primary_net_1.0"]) else -9))
    perm = {}
    for nm in rank[:6]:
        cfg = next(c for c in cfgs if c["name"] == nm)
        obs = sharpe(series[nm][0])
        draws = permutation_null(cfg, F, B, da, db, rng, n=500)
        p = float((np.sum(np.asarray(draws) >= obs) + 1) / (len(draws) + 1))
        perm[nm] = {"observed_net_sharpe": obs, "perm_mean": float(np.nanmean(draws)),
                    "perm_p95": float(np.nanpercentile(draws, 95)), "p_value": p, "n_perm": len(draws)}
        print(f"  perm {nm:24s} obs {obs:+.2f} null p95 {perm[nm]['perm_p95']:+.2f} p={p:.4f}", flush=True)
    res["permutation"] = perm
    out = OUTDIR / "INVENT_0823_intramicro_null.json"
    out.write_text(json.dumps(res, indent=1))
    print("wrote", out, flush=True)


def adv_buckets(adv: np.ndarray, valid: np.ndarray, nb: int = 10) -> np.ndarray:
    """Per-day ADV bucket id in 0..nb-1 for valid names; invalid names get nb (own group)."""
    a = np.where(valid, np.nan_to_num(adv, nan=0.0), np.inf)
    rank = np.argsort(np.argsort(a, axis=1, kind="stable"), axis=1)
    cnt = valid.sum(axis=1, keepdims=True).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        b = np.floor(rank / np.maximum(cnt, 1) * nb)
    b = np.clip(b, 0, nb - 1)
    return np.where(valid, b, nb).astype(np.int16)


def shuffle_in_buckets(sc: np.ndarray, buck: np.ndarray, rng) -> np.ndarray:
    """Permute score values within each (day, bucket) group.  Fully vectorised."""
    D, S = sc.shape
    rows = np.arange(D)[:, None]
    pos_order = np.argsort(buck, axis=1, kind="stable")
    val_order = np.argsort(buck.astype(np.float64) + rng.random((D, S)), axis=1, kind="stable")
    out = np.empty_like(sc, dtype=float)
    out[rows, pos_order] = np.asarray(sc, dtype=float)[rows, val_order]
    return out


def permutation_null(cfg, F, B, da, db, rng, n=500):
    """Permute the score vector within within-day ADV deciles; re-run the book."""
    draws = []
    if cfg["panel"] == "A":
        P = F.P
        cols = P.cols(cfg["universe"])
        legs = cfg.get("legs") or [(cfg["score"], cfg["s"], 1.0)]
        adv = P.adv[:, cols][da]
        prepped = []
        for score, s, wt in legs:
            e = s + 1
            px_in = P.vw[:, e, :][:, cols][da]
            px_out = P.vw[:, 77, :][:, cols][da]
            sc = score[:, cols][da].astype(float)
            valid = np.isfinite(sc) & np.isfinite(px_in) & np.isfinite(px_out) & (px_in > 0) & (px_out > 0)
            valid = valid & (valid.sum(axis=1) >= 10)[:, None]
            r = np.nan_to_num(np.where(valid, px_out / px_in - 1.0, 0.0))
            prepped.append((np.nan_to_num(sc), valid, r, wt, adv_buckets(adv, valid)))
        for _ in range(n):
            tot = np.zeros(int(da.sum())); gexp = np.zeros(int(da.sum()))
            for sc, valid, r, wt, buck in prepped:
                w = weights_from_score(shuffle_in_buckets(sc, buck, rng), valid) * wt
                tot += (w * r).sum(axis=1); gexp += np.abs(w).sum(axis=1)
            draws.append(sharpe(net_series(tot, gexp, HEADLINE, False)))
    else:
        ok0 = (B.in_uni & np.isfinite(B.po) & np.isfinite(B.p29) & np.isfinite(B.p49)
               & np.isfinite(B.pc) & (B.po > 0) & (B.p29 > 0) & (B.p49 > 0) & (B.pc > 0))[db]
        sc0 = np.nan_to_num((cfg["sign"] * (B.p29 / B.po - 1.0))[db])
        adv = B.adv[db]
        px_in = B.p49[db]; px_out = B.pc[db]
        ok = ok0
        if cfg["top"]:
            a = np.where(ok0, adv, np.nan)
            rk = np.argsort(np.argsort(-np.nan_to_num(a, nan=-1.0), axis=1), axis=1)
            ok = ok0 & (rk < cfg["top"])
        ok = ok & (ok.sum(axis=1) >= 20)[:, None]
        r = np.nan_to_num(np.where(ok, px_out / px_in - 1.0, 0.0))
        buck = adv_buckets(adv, ok)
        for _ in range(n):
            w = weights_from_score(shuffle_in_buckets(sc0, buck, rng), ok)
            draws.append(sharpe(net_series((w * r).sum(axis=1), np.abs(w).sum(axis=1), HEADLINE, True)))
    return draws


if __name__ == "__main__":
    main()
