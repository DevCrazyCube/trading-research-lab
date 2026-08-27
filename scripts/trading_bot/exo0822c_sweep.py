#!/usr/bin/env python3
"""EXO_0822C sweep — the PUBLISHED-GAP TETHER. 28 pre-registered formulas.

Pre-registration: research/trading_bot/INVENT_0822C_gaptether_PREREGISTRATION.md
sha256 987b283f548c54a12bd3a3ca935d99cdc8e80863a6c1eaac0d4e39892065ca65
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
EV = ROOT / "research/data/exo0822c/events.npz"
OUTDIR = ROOT / "research/trading_bot"

SPLIT = "2023-01-03"
CE_HEAD, CE_SHOCK, CE_AUCT = 3.0, 6.0, 0.5      # bp/side, event leg
CH = 1.0                                        # bp/side, hedge leg


# ------------------------------------------------------------------ panel ---
class Panel:
    def __init__(self):
        z = np.load(EV, allow_pickle=True)
        self.dates = z["dates"]
        self.nd = len(self.dates)
        self.evd = z["evd"].astype(np.int64)
        self.evs = z["evs"].astype(np.int64)
        self.y = z["y"]
        self.g = z["g"]
        self.eps = z["eps"]
        self.typ = z["typ"]
        self.regular = z["regular"]
        self.adv = z["adv"]
        self.price = z["price"]
        RON = z["RON"].astype(np.float64)
        ROC = z["ROC"].astype(np.float64)
        R = z["R"].astype(np.float64)
        m_on, m_oc, m_oo, m_cc = z["m_on"], z["m_oc"], z["m_oo"], z["m_cc"]
        self.m_oo = m_oo
        self.m_on = m_on
        self.eps_h = z["eps_h"]
        # hedged residual matrices
        self.ON = RON - m_on[:, None]
        self.OC = ROC - m_oc[:, None]
        Rh = R - m_oo[:, None]
        # cumulative sums for O(1) forward windows
        v = np.isfinite(Rh)
        c = np.where(v, Rh, 0.0)
        self.cum = np.vstack([np.zeros((1, Rh.shape[1])), np.cumsum(c, 0)])
        self.cnt = np.vstack([np.zeros((1, Rh.shape[1])), np.cumsum(~v, 0)])
        # trailing overnight vol (60d), ending at d-1
        w = np.isfinite(self.ON)
        x = np.where(w, self.ON, 0.0)
        cx = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(x, 0)])
        cx2 = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(x * x, 0)])
        cw = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(w, 0)])
        L = 60
        self.vol = np.full_like(x, np.nan)
        nd_ = x.shape[0]
        n = cw[L:nd_] - cw[0:nd_ - L]
        s1 = cx[L:nd_] - cx[0:nd_ - L]
        s2 = cx2[L:nd_] - cx2[0:nd_ - L]
        with np.errstate(invalid="ignore", divide="ignore"):
            var = s2 / np.maximum(n, 1) - (s1 / np.maximum(n, 1)) ** 2
            vv = np.sqrt(np.maximum(var, 0))
        vv[n < 30] = np.nan
        self.vol[L:nd_] = vv
        # close-to-close hedged, for the run-up family
        self.CCH = None
        self.ru5 = z["ru5"]
        self.ru20 = z["ru20"]
        self.pl = z["pl"]
        # design / held-out masks over events
        cut = int(np.searchsorted(self.dates, SPLIT))
        self.cut = cut
        self.ndes = cut
        self.nhold = self.nd - cut

    def fwd(self, d, i, h):
        """hedged cumulative open-to-open return over h sessions from open(d)."""
        d = np.asarray(d)
        ok = (d >= 0) & (d + h <= self.nd)
        dd = np.clip(d, 0, self.nd - h)
        out = self.cum[dd + h, i] - self.cum[dd, i]
        bad = (self.cnt[dd + h, i] - self.cnt[dd, i]) > 0
        out = np.where(ok & ~bad, out, np.nan)
        return out


# ---------------------------------------------------------------- returns ---
def real_returns(P: Panel, yshuf=None):
    d, i = P.evd, P.evs
    r = {}
    # published-tether residual, hedged against the clean universe's overnight median
    r["eps_h"] = P.eps_h
    # the SAME gap with no published rate subtracted (family-E no-tether control)
    r["graw_h"] = P.g - P.m_on[d]
    # the tether replaced by a WRONG published rate (rates permuted within the day)
    if yshuf is not None:
        r["eps_shuf_h"] = P.g - np.log(np.clip(1.0 - yshuf, 1e-6, None)) - P.m_on[d]
    r["oc"] = P.OC[d, i]
    r["f1"] = P.fwd(d, i, 1)
    r["f2"] = P.fwd(d, i, 2)
    r["f5"] = P.fwd(d, i, 5)
    r["f20"] = P.fwd(d, i, 20)
    r["f5d"] = P.fwd(d + 1, i, 5)
    r["ru5"] = P.ru5
    r["ru20"] = P.ru20
    r["pl"] = P.pl
    r["sig_eps"] = r["eps_h"]
    r["sig_graw"] = r["graw_h"]
    r["vol"] = P.vol[d, i]
    r["mkt"] = P.m_oo
    return r


def placebo_returns(P: Panel, rng):
    """Same symbols, same cohort structure, a nearby NON-event date."""
    d, i = P.evd, P.evs
    n = d.size
    off = rng.integers(3, 16, n) * rng.choice([-1, 1], n)
    dd = np.clip(d + off, 61, P.nd - 25)
    r = {}
    r["eps_h"] = P.ON[dd, i]
    r["graw_h"] = P.ON[dd, i]
    r["eps_shuf_h"] = P.ON[dd, i]
    r["oc"] = P.OC[dd, i]
    r["f1"] = P.fwd(dd, i, 1)
    r["f2"] = P.fwd(dd, i, 2)
    r["f5"] = P.fwd(dd, i, 5)
    r["f20"] = P.fwd(dd, i, 20)
    r["f5d"] = P.fwd(dd + 1, i, 5)
    r["ru5"] = P.fwd(dd - 6, i, 5)
    r["ru20"] = P.fwd(dd - 21, i, 20)
    off2 = rng.integers(3, 16, n) * rng.choice([-1, 1], n)
    dd2 = np.clip(d + off2, 61, P.nd - 25)
    r["pl"] = P.ON[dd2, i]
    r["sig_eps"] = r["eps_h"]
    r["sig_graw"] = r["graw_h"]
    r["vol"] = P.vol[dd, i]
    mk = P.m_oo.copy()
    k = int(rng.integers(40, P.nd - 40))
    r["mkt"] = np.roll(mk, k)
    return r


# --------------------------------------------------------------- formulas ---
# each formula: (name, family, ret_key, horizon, builder)
# builder(P, r, expq) -> (weights over events, active mask)

def _z_demean(vals, evd, mask, minn=3):
    """cohort-demeaned weights normalised to sum|w| = 1 per day."""
    w = np.zeros_like(vals)
    idx = np.where(mask & np.isfinite(vals))[0]
    if idx.size == 0:
        return w
    order = np.argsort(evd[idx], kind="stable")
    idx = idx[order]
    days = evd[idx]
    bnds = np.flatnonzero(np.r_[True, days[1:] != days[:-1], True])
    for a, b in zip(bnds[:-1], bnds[1:]):
        if b - a < minn:
            continue
        sl = idx[a:b]
        v = vals[sl]
        v = v - v.mean()
        s = np.abs(v).sum()
        if s > 0:
            w[sl] = v / s
    return w


def _eq(evd, mask):
    w = np.zeros(mask.size)
    idx = np.where(mask)[0]
    if idx.size == 0:
        return w
    order = np.argsort(evd[idx], kind="stable")
    idx = idx[order]
    days = evd[idx]
    bnds = np.flatnonzero(np.r_[True, days[1:] != days[:-1], True])
    for a, b in zip(bnds[:-1], bnds[1:]):
        sl = idx[a:b]
        w[sl] = 1.0 / len(sl)
    return w


def _prop(vals, evd, mask):
    w = np.zeros(vals.size)
    idx = np.where(mask & np.isfinite(vals) & (vals > 0))[0]
    if idx.size == 0:
        return w
    order = np.argsort(evd[idx], kind="stable")
    idx = idx[order]
    days = evd[idx]
    bnds = np.flatnonzero(np.r_[True, days[1:] != days[:-1], True])
    for a, b in zip(bnds[:-1], bnds[1:]):
        sl = idx[a:b]
        v = vals[sl]
        w[sl] = v / v.sum()
    return w


def _half(vals, evd, mask, top=True, minn=2):
    """within-day top/bottom half by vals, equal weight."""
    out = np.zeros(vals.size, bool)
    idx = np.where(mask & np.isfinite(vals))[0]
    if idx.size == 0:
        return out
    order = np.argsort(evd[idx], kind="stable")
    idx = idx[order]
    days = evd[idx]
    bnds = np.flatnonzero(np.r_[True, days[1:] != days[:-1], True])
    for a, b in zip(bnds[:-1], bnds[1:]):
        if b - a < minn:
            continue
        sl = idx[a:b]
        med = np.median(vals[sl])
        out[sl] = (vals[sl] >= med) if top else (vals[sl] < med)
    return out


def _spread(vals, evd, mask, minn=4):
    w = np.zeros(vals.size)
    idx = np.where(mask & np.isfinite(vals))[0]
    if idx.size == 0:
        return w
    order = np.argsort(evd[idx], kind="stable")
    idx = idx[order]
    days = evd[idx]
    bnds = np.flatnonzero(np.r_[True, days[1:] != days[:-1], True])
    for a, b in zip(bnds[:-1], bnds[1:]):
        if b - a < minn:
            continue
        sl = idx[a:b]
        v = vals[sl]
        med = np.median(v)
        hi = v >= med
        lo = ~hi
        if hi.sum() == 0 or lo.sum() == 0:
            continue
        w[sl[hi]] = 0.5 / hi.sum()
        w[sl[lo]] = -0.5 / lo.sum()
    return w


def expanding_tercile(y, evd, nd):
    """q33/q67 of y over strictly earlier events, per event."""
    n = y.size
    order = np.argsort(evd, kind="stable")
    q33 = np.full(n, np.nan)
    q67 = np.full(n, np.nan)
    ys = y[order]
    ds = evd[order]
    bnds = np.flatnonzero(np.r_[True, ds[1:] != ds[:-1], True])
    for a, b in zip(bnds[:-1], bnds[1:]):
        if a >= 200:
            hist = ys[:a]
            q33[order[a:b]] = np.quantile(hist, 1 / 3)
            q67[order[a:b]] = np.quantile(hist, 2 / 3)
    return q33, q67


FORMULAS = [
    # name, family, return key, horizon H, apriori sign (None => frozen on design)
    ("A1_EQ", "A", "eps_h", 1, +1),
    ("A2_YW", "A", "eps_h", 1, +1),
    ("A3_YHI", "A", "eps_h", 1, +1),
    ("A4_YLO", "A", "eps_h", 1, +1),
    ("A5_YSPREAD", "A", "eps_h", 1, +1),
    ("A6_SPECIAL", "A", "eps_h", 1, +1),
    ("A7_REG", "A", "eps_h", 1, +1),
    ("A8_IRREG", "A", "eps_h", 1, +1),
    ("A9_ADVHI", "A", "eps_h", 1, +1),
    ("A10_ADVLO", "A", "eps_h", 1, +1),
    ("B1_EPS_OC", "B", "oc", 1, None),
    ("B2_Y_OC", "B", "oc", 1, None),
    ("B3_GRAW_OC", "B", "oc", 1, None),
    ("C1_EPS_H1", "C", "f1", 1, None),
    ("C2_EPS_H5", "C", "f5", 5, None),
    ("C3_EPS_H20", "C", "f20", 20, None),
    ("C4_EPS_GAP5", "C", "f5d", 5, None),
    ("C5_EPSAGG_TS", "C", "mkt", 1, None),
    ("C6_EPS_VOLADJ", "C", "f5", 5, None),
    ("D1_FWD_GAP", "D", "eps_h", 1, +1),
    ("D2_FWD_H20", "D", "f20", 20, None),
    ("D3_REV_GAP", "D", "eps_h", 1, -1),
    ("D4_REV_H20", "D", "f20", 20, -1),
    ("E1_PLACEBO_DATE", "E", "pl", 1, +1),
    ("E2_SHUFFLE_RATE", "E", "eps_shuf_h", 1, +1),
    ("E3_NOTETHER", "E", "graw_h", 1, +1),
    ("E4_RUNUP5", "E", "ru5", 5, None),
    ("E5_RUNUP20", "E", "ru20", 20, None),
]


def build_weights(name, P, r, ctx, rng=None):
    evd = P.evd
    ordinary = (P.typ == 0)
    special = (P.typ == 3)
    fwds = (P.typ == 1)
    revs = (P.typ == 2)
    q33, q67 = ctx["q33"], ctx["q67"]
    y = P.y
    if name == "A1_EQ":
        return _eq(evd, ordinary)
    if name == "A2_YW":
        return _prop(y, evd, ordinary)
    if name == "A3_YHI":
        return _eq(evd, ordinary & np.isfinite(q67) & (y >= q67))
    if name == "A4_YLO":
        return _eq(evd, ordinary & np.isfinite(q33) & (y <= q33))
    if name == "A5_YSPREAD":
        return _spread(y, evd, ordinary)
    if name == "A6_SPECIAL":
        return _eq(evd, special)
    if name == "A7_REG":
        return _eq(evd, ordinary & P.regular)
    if name == "A8_IRREG":
        return _eq(evd, ordinary & ~P.regular)
    if name == "A9_ADVHI":
        return _eq(evd, _half(P.adv, evd, ordinary, True))
    if name == "A10_ADVLO":
        return _eq(evd, _half(P.adv, evd, ordinary, False))
    if name == "B1_EPS_OC":
        return _z_demean(r["sig_eps"], evd, ordinary)
    if name == "B2_Y_OC":
        return _z_demean(y, evd, ordinary)
    if name == "B3_GRAW_OC":
        return _z_demean(r["sig_graw"], evd, ordinary)
    if name in ("C1_EPS_H1", "C2_EPS_H5", "C3_EPS_H20", "C4_EPS_GAP5"):
        return _z_demean(r["sig_eps"], evd, ordinary)
    if name == "C6_EPS_VOLADJ":
        v = r["sig_eps"] / np.where(np.isfinite(r["vol"]) & (r["vol"] > 0), r["vol"], np.nan)
        return _z_demean(v, evd, ordinary)
    if name == "D1_FWD_GAP":
        return _eq(evd, fwds)
    if name == "D2_FWD_H20":
        return _eq(evd, fwds)
    if name == "D3_REV_GAP":
        return _eq(evd, revs)
    if name == "D4_REV_H20":
        return _eq(evd, revs)
    if name == "E1_PLACEBO_DATE":
        return _eq(evd, ordinary & np.isfinite(r["pl"]))
    if name == "E2_SHUFFLE_RATE":
        return _prop(ctx["yshuf"], evd, ordinary)
    if name == "E3_NOTETHER":
        return _eq(evd, ordinary)
    if name in ("E4_RUNUP5", "E5_RUNUP20"):
        return _eq(evd, ordinary)
    raise KeyError(name)


def shuffle_rate(y, evd, rng):
    ys = y.copy()
    order = np.argsort(evd, kind="stable")
    ds = evd[order]
    bnds = np.flatnonzero(np.r_[True, ds[1:] != ds[:-1], True])
    for a, b in zip(bnds[:-1], bnds[1:]):
        sl = order[a:b]
        ys[sl] = y[sl][rng.permutation(b - a)]
    return ys


def eval_formula(name, fam, rkey, H, P, r, ctx, dmask_lo, dmask_hi, ce, sign=1.0, rng=None):
    """returns dict with daily net series stats over [dmask_lo, dmask_hi) date range."""
    nd = P.nd
    pnl = np.zeros(nd)
    cost = np.zeros(nd)
    if name == "C5_EPSAGG_TS":
        # aggregate cohort-mean eps -> TS sign on the clean-universe market
        s = np.zeros(nd)
        ordinary = P.typ == 0
        vals = r["sig_eps"]
        idx = np.where(ordinary & np.isfinite(vals))[0]
        np.add.at(s, P.evd[idx], vals[idx])
        cnt = np.zeros(nd)
        np.add.at(cnt, P.evd[idx], 1.0)
        with np.errstate(invalid="ignore"):
            s = np.where(cnt >= 3, s / np.maximum(cnt, 1), np.nan)
        pos = np.sign(np.nan_to_num(s))
        mkt = r["mkt"]
        good = np.isfinite(mkt)
        pnl[good] = sign * pos[good] * mkt[good] * 1e4
        turn = np.abs(np.diff(np.r_[0.0, sign * pos]))
        cost = turn * CH
        gross_ex = pnl.copy()
    else:
        w = build_weights(name, P, r, ctx, rng)
        ret = r[rkey]
        ok = np.isfinite(ret) & (w != 0)
        wj = w[ok] * sign
        rj = ret[ok]
        dj = P.evd[ok] + H
        dj = np.clip(dj, 0, nd - 1)
        np.add.at(pnl, dj, wj * rj * 1e4 / H)
        # event legs: 2 sides per trade; hedge leg on the net exposure
        np.add.at(cost, dj, 2.0 * ce * np.abs(wj) / H)
        net_exp = np.zeros(nd)
        np.add.at(net_exp, dj, wj / H)
        cost += 2.0 * CH * np.abs(net_exp)
        gross_ex = pnl.copy()
    sl = slice(dmask_lo, dmask_hi)
    gp = gross_ex[sl]
    npnl = (gross_ex - cost)[sl]
    n = npnl.size
    yrs = n / 252.0
    out = {}
    for tag, ser in (("gross", gp), ("net", npnl)):
        sd = ser.std(ddof=1)
        sr = ser.mean() / sd * np.sqrt(252) if sd > 0 else 0.0
        out[tag + "_sr"] = float(sr)
        out[tag + "_t"] = float(sr * np.sqrt(yrs))
        out[tag + "_bpd"] = float(ser.mean())
    out["cost_bpd"] = float(cost[sl].mean())
    turn_bpd = out["cost_bpd"] / max(ce, 1e-9)
    out["breakeven_bp"] = float(out["gross_bpd"] / turn_bpd) if turn_bpd > 0 else 0.0
    out["active_days"] = int((gross_ex[sl] != 0).sum())
    return out, gross_ex, cost


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "design"
    P = Panel()
    rng = np.random.default_rng(20260822)
    q33, q67 = expanding_tercile(P.y, P.evd, P.nd)
    ctx = {"q33": q33, "q67": q67, "yshuf": shuffle_rate(P.y, P.evd, rng)}
    r = real_returns(P, ctx["yshuf"])

    if mode == "design":
        lo, hi = 0, P.cut
    else:
        lo, hi = P.cut, P.nd

    frozen_path = OUTDIR / "INVENT_0822C_gaptether_DESIGN.json"
    frozen = json.load(open(frozen_path)) if (mode != "design" and frozen_path.exists()) else None

    res = {}
    for name, fam, rkey, H, ap in FORMULAS:
        if mode == "design":
            base, _, _ = eval_formula(name, fam, rkey, H, P, r, ctx, lo, hi, CE_HEAD, 1.0, rng)
            sign = float(ap) if ap is not None else (1.0 if base["gross_bpd"] >= 0 else -1.0)
        else:
            sign = float(frozen[name]["sign"])
        o_head, _, _ = eval_formula(name, fam, rkey, H, P, r, ctx, lo, hi, CE_HEAD, sign, rng)
        o_shock, _, _ = eval_formula(name, fam, rkey, H, P, r, ctx, lo, hi, CE_SHOCK, sign, rng)
        o_auct, _, _ = eval_formula(name, fam, rkey, H, P, r, ctx, lo, hi, CE_AUCT, sign, rng)
        res[name] = {
            "family": fam, "H": H, "sign": sign, "apriori": ap is not None,
            "gross_sr": o_head["gross_sr"], "gross_t": o_head["gross_t"],
            "gross_bpd": o_head["gross_bpd"],
            "net_sr": o_head["net_sr"], "net_t": o_head["net_t"], "net_bpd": o_head["net_bpd"],
            "net_sr_shock": o_shock["net_sr"], "net_sr_auction": o_auct["net_sr"],
            "cost_bpd": o_head["cost_bpd"], "breakeven_bp": o_head["breakeven_bp"],
            "active_days": o_head["active_days"],
        }
    tag = "DESIGN" if mode == "design" else "HOLDOUT"
    json.dump(res, open(OUTDIR / f"INVENT_0822C_gaptether_{tag}.json", "w"), indent=1)
    order = sorted(res, key=lambda k: -abs(res[k]["gross_t"]))
    print(f"=== {tag}  n_days={hi-lo}  ({P.dates[lo]} .. {P.dates[hi-1]})")
    print(f"{'formula':18s} {'fam':3s} {'sgn':>4s} {'grossSR':>8s} {'grossT':>7s} "
          f"{'gbp/d':>7s} {'netSR':>7s} {'netT':>7s} {'BE bp':>7s} {'auctSR':>7s} {'days':>6s}")
    for k in order:
        v = res[k]
        print(f"{k:18s} {v['family']:3s} {v['sign']:+4.0f} {v['gross_sr']:8.2f} {v['gross_t']:7.2f} "
              f"{v['gross_bpd']:7.2f} {v['net_sr']:7.2f} {v['net_t']:7.2f} "
              f"{v['breakeven_bp']:7.2f} {v['net_sr_auction']:7.2f} {v['active_days']:6d}")


if __name__ == "__main__":
    main()
