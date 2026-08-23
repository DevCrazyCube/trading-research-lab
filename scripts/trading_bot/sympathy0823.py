#!/usr/bin/env python3
"""INVENT_0823 `sympathy` -- intra-group lead-lag: does a group leader's sharp move make close
peers systematically over/under-react in the NEXT interval, executably?

Pre-registration: research/trading_bot/INVENT_0823_sympathy_PREREGISTRATION.md
sha256 2d284d0b7dd22f5b2c068cf8ec9ce7e523463ec09b1ef172a8f1941753db43aa -- this script refuses
to run against any other hash.

The whole design is built around one idea: a formula is a TRADE TABLE (day, signal bar, leg,
sign, holding, cost), and a single generic evaluator turns that table into a daily PnL series
given (a) a window, (b) an entry lag, (c) an optional day-shift, (d) an optional sign flip.
That makes the held-out run, the one-bar-gap re-entry test, and both placebo nulls the SAME
code path as the design run, which is the only way to be sure the null is size-matched.

Stages:  selftest | design | nulls | shortlist | holdout
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "rv_cache"
OUT = ROOT / "research" / "trading_bot"
PREREG = OUT / "INVENT_0823_sympathy_PREREGISTRATION.md"
PREREG_SHA = "2d284d0b7dd22f5b2c068cf8ec9ce7e523463ec09b1ef172a8f1941753db43aa"

DESIGN = ("2021-01-04", "2024-12-31")
HELDOUT = ("2025-01-02", "2026-08-14")
REG_BP = 0.15          # SEC 31 + FINRA TAF per unit turnover
NBAR = 78              # 5-minute bars per RTH session
LASTBAR = NBAR - 1

GROUPS = {
    "SEMI":     ("NVDA", ["AMD", "AVGO", "INTC", "SMH"]),
    "MEGATECH": ("AAPL", ["MSFT", "GOOGL", "META", "AMZN", "ADBE", "CRM", "ORCL", "CSCO",
                          "NFLX", "XLK"]),
    "BANK":     ("JPM",  ["BAC", "XLF", "KRE"]),
    "ENERGY":   ("XOM",  ["CVX", "XLE"]),
    "HEALTH":   ("LLY",  ["UNH", "JNJ", "MRK", "ABBV", "XLV", "IBB"]),
    "STAPLE":   ("WMT",  ["COST", "PG", "KO", "PEP", "XLP"]),
    "DISCR":    ("HD",   ["AMZN", "TSLA", "XLY"]),
    "GOLD":     ("GDX",  ["GDXJ", "GLD"]),
    "PAYMENT":  ("V",    ["MA"]),
}
# heavyweight -> index (each heavyweight is its own one-peer group)
INDEX_HEAVIES = ["AAPL", "MSFT", "NVDA", "AMZN", "META"]
# direction test: the sector ETF leads its members
ETF_GROUPS = {
    "ETF_SEMI":   ("SMH",  ["NVDA", "AMD", "AVGO", "INTC"]),
    "ETF_TECH":   ("XLK",  ["AAPL", "MSFT", "ADBE", "CRM", "ORCL", "CSCO"]),
    "ETF_BANK":   ("XLF",  ["JPM", "BAC"]),
    "ETF_ENERGY": ("XLE",  ["XOM", "CVX"]),
    "ETF_HEALTH": ("XLV",  ["LLY", "UNH", "JNJ", "MRK", "ABBV"]),
    "ETF_STAPLE": ("XLP",  ["WMT", "COST", "PG", "KO", "PEP"]),
}


def check_prereg():
    h = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if h != PREREG_SHA:
        sys.exit(f"REFUSED: pre-registration hash {h} != {PREREG_SHA}")


# ----------------------------------------------------------------- panel

class Panel:
    def __init__(self, synthetic=None):
        if synthetic is not None:
            self.__dict__.update(synthetic)
            return
        z = np.load(CACHE / "panel_rv.npz", allow_pickle=True)
        syms = [str(s) for s in z["syms"]]
        day = z["day"].astype(np.int64)
        slot = z["slot"].astype(np.int64)
        dk = np.asarray([str(x) for x in z["daykey"]])
        D = int(day.max()) + 1
        S = len(syms)
        close = np.full((D, NBAR, S), np.nan, np.float32)
        dvol = np.full((D, NBAR, S), np.nan, np.float32)
        close[day, slot] = z["close"]
        dvol[day, slot] = z["dvol"]
        daykey = np.empty(D, dtype="U10")
        daykey[day] = dk
        self.syms, self.close, self.dvol, self.daykey = syms, close, dvol, daykey
        self.D, self.S = D, S
        self.idx = {s: i for i, s in enumerate(syms)}
        self._costs()
        self._returns()

    def _costs(self):
        doc = json.loads((CACHE / "spread_proxy.json").read_text())
        hs = np.full(self.S, 2.5)
        for j, s in enumerate(self.syms):
            row = doc["symbols"].get(s.replace(".", "_")) or doc["symbols"].get(s)
            if row:
                hs[j] = row["headline_half_bp"]
        self.half_bp = hs
        self.cost_rt = 2.0 * (hs + REG_BP) * 1e-4    # round-trip cost, one leg, return units
        self.cost_provenance = doc["provenance"]

    def _returns(self):
        c = self.close.astype(np.float64)
        r = np.full_like(c, np.nan)
        r[:, 1:] = c[:, 1:] / c[:, :-1] - 1.0
        gap = np.full((self.D, self.S), np.nan)
        gap[1:] = c[1:, 0] / c[:-1, LASTBAR] - 1.0
        r[:, 0] = gap
        self.ret = r.astype(np.float32)     # bar returns; bar 0 is the overnight gap
        self.gap = gap.astype(np.float32)

    def window(self, w):
        return (self.daykey >= w[0]) & (self.daykey <= w[1])


def rolling_stats(P, leader, cols, win=20):
    """beta of each col on the leader and the leader's sigma, from the WINDOW ENDING d-1
    (strictly no same-day information). Intraday bars only (bar 0, the gap, excluded)."""
    L = P.idx[leader]
    rl = np.nan_to_num(P.ret[:, 1:, L].astype(np.float64))
    rp = np.nan_to_num(P.ret[:, 1:, :][:, :, cols].astype(np.float64))
    sll = (rl * rl).sum(axis=1)                      # [D]
    spl = (rp * rl[:, :, None]).sum(axis=1)          # [D, ncols]
    n = np.isfinite(P.ret[:, 1:, L]).sum(axis=1).astype(np.float64)

    def roll(x):
        cs = np.cumsum(np.concatenate([np.zeros((1,) + x.shape[1:]), x], axis=0), axis=0)
        out = np.full_like(x, np.nan, dtype=np.float64)
        out[win:] = cs[win:-1] - cs[:-win - 1]       # sum over days d-win .. d-1
        return out

    SLL, SPL, N = roll(sll), roll(spl), roll(n)
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = SPL / SLL[:, None]
        sig = np.sqrt(SLL / np.maximum(N, 1))
    return beta, sig


def rolling_gap_stats(P, leader, cols, win=60):
    L = P.idx[leader]
    gl = np.nan_to_num(P.gap[:, L].astype(np.float64))
    gp = np.nan_to_num(P.gap[:, cols].astype(np.float64))
    sll = gl * gl
    spl = gp * gl[:, None]

    def roll(x):
        cs = np.cumsum(np.concatenate([np.zeros((1,) + x.shape[1:]), x], axis=0), axis=0)
        out = np.full_like(x, np.nan, dtype=np.float64)
        out[win:] = cs[win:-1] - cs[:-win - 1]
        return out

    SLL, SPL = roll(sll), roll(spl)
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = SPL / SLL[:, None]
        sig = np.sqrt(SLL / win)
    return beta, sig


# ----------------------------------------------------------------- trade table

class Trades:
    """Columns are per LEG. `ev` groups legs belonging to the same event (one unit of capital
    per event, split across its legs). `d` is the session the PnL is booked to."""

    __slots__ = ("d", "b", "col", "sgn", "hold", "hcol", "hbeta", "ev", "name", "hold_to_close")

    def __init__(self, name, d, b, col, sgn, hold, ev, hcol=None, hbeta=None,
                 hold_to_close=False):
        self.name = name
        self.d = np.asarray(d, np.int64)
        self.b = np.asarray(b, np.int64)          # SIGNAL bar; entry is b + lag
        self.col = np.asarray(col, np.int64)
        self.sgn = np.asarray(sgn, np.float64)
        self.hold = int(hold)
        self.ev = np.asarray(ev, np.int64)
        self.hcol = None if hcol is None else np.asarray(hcol, np.int64)
        self.hbeta = None if hbeta is None else np.asarray(hbeta, np.float64)
        self.hold_to_close = hold_to_close

    def __len__(self):
        return self.d.size


def evaluate(P, tr, mask_days, lag=1, day_shift=0, flip=None, gross_only=False):
    """Daily PnL over the sessions selected by `mask_days`. One unit per event."""
    if len(tr) == 0:
        return np.zeros(int(mask_days.sum())), {}
    e = tr.b + lag
    x = np.full_like(e, LASTBAR) if tr.hold_to_close else np.minimum(e + tr.hold, LASTBAR)
    ok = (e >= 0) & (e < LASTBAR) & (x > e)
    d = tr.d
    dd = d + day_shift
    ok &= (dd >= 0) & (dd < P.D)
    if not ok.any():
        return np.zeros(int(mask_days.sum())), {}
    e, x, dsh, d2, col = e[ok], x[ok], dd[ok], d[ok], tr.col[ok]
    sgn = tr.sgn[ok].copy()
    ev = tr.ev[ok]
    c = P.close
    pe = c[dsh, e, col].astype(np.float64)
    px = c[dsh, x, col].astype(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        fwd = px / pe - 1.0
    cost = P.cost_rt[col].copy()
    if tr.hcol is not None:
        hc, hb = tr.hcol[ok], tr.hbeta[ok]
        he = c[dsh, e, hc].astype(np.float64)
        hx = c[dsh, x, hc].astype(np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            fwd = fwd - hb * (hx / he - 1.0)
        cost = cost + np.abs(hb) * P.cost_rt[hc]
    if flip is not None:
        sgn = sgn * flip[ev]
    pnl = sgn * fwd - (0.0 if gross_only else cost)
    good = np.isfinite(pnl)
    if not good.any():
        return np.zeros(int(mask_days.sum())), {}
    pnl, ev, d2, col = pnl[good], ev[good], d2[good], col[good]
    # 1 unit per event, split across the event's legs
    uev, inv = np.unique(ev, return_inverse=True)
    cnt = np.bincount(inv)
    ev_pnl = np.bincount(inv, weights=pnl) / cnt
    ev_day = np.zeros(uev.size, np.int64)
    ev_day[inv] = d2
    dayp = np.bincount(ev_day, weights=ev_pnl, minlength=P.D)
    dayn = np.bincount(ev_day, minlength=P.D)
    with np.errstate(invalid="ignore"):
        daily = np.where(dayn > 0, dayp / np.maximum(dayn, 1), 0.0)
    out = daily[mask_days]
    inwin = mask_days[d2]                     # counts must describe the WINDOW, not the panel
    diag = {
        "n_legs": int(inwin.sum()),
        "n_events": int(np.unique(ev[inwin]).size),
        "active_days": int((dayn[mask_days] > 0).sum()),
        "mean_cost_bp": float(np.mean(P.cost_rt[col]) * 1e4),
    }
    return out, diag


def sharpe(x):
    if x.size < 30:
        return float("nan")
    s = x.std(ddof=1)
    if not np.isfinite(s) or s <= 0:
        return float("nan")
    return float(x.mean() / s * np.sqrt(252))


# ----------------------------------------------------------------- formulas

def _shock_events(P, leader, k, sig, sign_filter=0, cum=1, volshock=False):
    """Boolean [D, NBAR] mask of leader shock bars (signal measured to the close of that bar)."""
    L = P.idx[leader]
    r = P.ret[:, :, L].astype(np.float64)
    if cum > 1:
        rr = np.full_like(r, np.nan)
        c = P.close[:, :, L].astype(np.float64)
        rr[:, cum:] = c[:, cum:] / c[:, :-cum] - 1.0
        r = rr
        sig = sig * np.sqrt(cum)
    m = np.zeros_like(r, dtype=bool)
    with np.errstate(invalid="ignore"):
        thr = k * sig[:, None]
        if volshock:
            v = P.dvol[:, :, L].astype(np.float64)
            med = np.nanmedian(np.where(np.isfinite(v), v, np.nan), axis=0)   # slot profile
            base = np.full_like(v, np.nan)
            base[20:] = np.nan
            # trailing 20-day mean of the same slot
            cs = np.cumsum(np.concatenate([np.zeros((1, NBAR)), np.nan_to_num(v)], 0), 0)
            base[20:] = (cs[20:-1] - cs[:-21]) / 20.0
            m = (v > k * base) & np.isfinite(v) & np.isfinite(base)
            m &= np.abs(r) > 0.5 * sig[:, None]
        else:
            m = np.abs(r) > thr
    m &= np.isfinite(r)
    if sign_filter > 0:
        m &= r > 0
    elif sign_filter < 0:
        m &= r < 0
    m[:, 0] = False           # bar 0 is the overnight gap; intraday claims exclude it
    m[:, LASTBAR - 1:] = False
    return m, r


def build_leader_formula(P, name, groups, k, hold, fade=False, hedged=False, sign_filter=0,
                         cum=1, volshock=False, hold_to_close=False, dispersion=False):
    d_, b_, col_, sgn_, ev_, hc_, hb_ = [], [], [], [], [], [], []
    ev0 = 0
    for gname, (leader, peers) in groups.items():
        cols = [P.idx[p] for p in peers if p in P.idx]
        if not cols:
            continue
        beta, sig = rolling_stats(P, leader, cols)
        m, rlead = _shock_events(P, leader, k, sig, sign_filter, cum, volshock)
        dd, bb = np.nonzero(m)
        if dd.size == 0:
            continue
        rp = P.ret[:, :, cols].astype(np.float64)
        if cum > 1:
            cc = P.close[:, :, cols].astype(np.float64)
            rp2 = np.full_like(rp, np.nan)
            rp2[:, cum:] = cc[:, cum:] / cc[:, :-cum] - 1.0
            rp = rp2
        bet = beta[dd]                                   # [E, ncols]
        deficit = bet * rlead[dd, bb][:, None] - rp[dd, bb]
        s = np.sign(deficit)
        if fade:
            s = -s
        if dispersion:
            # dollar-neutral inside the group: +1 the biggest laggard, -1 the biggest leader
            s = np.zeros_like(deficit)
            fin = np.isfinite(deficit)
            hi = np.argmax(np.where(fin, deficit, -np.inf), axis=1)
            lo = np.argmin(np.where(fin, deficit, np.inf), axis=1)
            rows = np.arange(deficit.shape[0])
            live = fin.sum(axis=1) >= 2
            s[rows[live], hi[live]] = 1.0
            s[rows[live], lo[live]] = -1.0
        good = np.isfinite(deficit) & np.isfinite(bet) & (s != 0)
        ei, pi = np.nonzero(good)
        if ei.size == 0:
            continue
        d_.append(dd[ei]); b_.append(bb[ei])
        col_.append(np.asarray(cols)[pi])
        sgn_.append(s[ei, pi])
        ev_.append(ei + ev0)
        if hedged:
            hc_.append(np.full(ei.size, P.idx[leader], np.int64))
            hb_.append(bet[ei, pi])
        ev0 += dd.size
    if not d_:
        return Trades(name, [], [], [], [], hold, [])
    kw = {}
    if hedged:
        kw = dict(hcol=np.concatenate(hc_), hbeta=np.concatenate(hb_))
    return Trades(name, np.concatenate(d_), np.concatenate(b_), np.concatenate(col_),
                  np.concatenate(sgn_), hold, np.concatenate(ev_),
                  hold_to_close=hold_to_close, **kw)


def build_breadth(P, name, groups, k, hold):
    """No single leader: the group's own median move is the 'leader', each member the peer."""
    d_, b_, col_, sgn_, ev_ = [], [], [], [], []
    ev0 = 0
    for gname, (leader, peers) in groups.items():
        members = [leader] + list(peers)
        cols = [P.idx[m] for m in members if m in P.idx]
        if len(cols) < 3:
            continue
        r = P.ret[:, :, cols].astype(np.float64)
        med = np.nanmedian(r, axis=2)                       # [D, NBAR]
        sd = np.nanstd(np.where(np.isfinite(med), med, np.nan), axis=1)   # per-day scale
        sig = np.full(P.D, np.nan)
        sig[20:] = np.convolve(np.nan_to_num(sd), np.ones(20) / 20, "full")[19:P.D - 1]
        m = np.abs(med) > k * sig[:, None]
        m &= np.isfinite(med)
        m[:, 0] = False
        m[:, LASTBAR - 1:] = False
        dd, bb = np.nonzero(m)
        if dd.size == 0:
            continue
        deficit = med[dd, bb][:, None] - r[dd, bb]
        s = np.sign(deficit)
        good = np.isfinite(deficit) & (s != 0)
        ei, pi = np.nonzero(good)
        d_.append(dd[ei]); b_.append(bb[ei])
        col_.append(np.asarray(cols)[pi]); sgn_.append(s[ei, pi]); ev_.append(ei + ev0)
        ev0 += dd.size
    if not d_:
        return Trades(name, [], [], [], [], hold, [])
    return Trades(name, np.concatenate(d_), np.concatenate(b_), np.concatenate(col_),
                  np.concatenate(sgn_), hold, np.concatenate(ev_))


def build_gap(P, name, groups, k, hold, fade=False, hold_to_close=False):
    """Leader's overnight gap (prev close -> 09:35 close) -> peer residual gap deficit.
    Signal bar is 0 (09:35 close); entry at bar 0 + lag."""
    d_, b_, col_, sgn_, ev_ = [], [], [], [], []
    ev0 = 0
    for gname, (leader, peers) in groups.items():
        cols = [P.idx[p] for p in peers if p in P.idx]
        if not cols:
            continue
        beta, sig = rolling_gap_stats(P, leader, cols)
        gl = P.gap[:, P.idx[leader]].astype(np.float64)
        gp = P.gap[:, cols].astype(np.float64)
        with np.errstate(invalid="ignore"):
            ev = np.abs(gl) > k * sig
        ev &= np.isfinite(gl) & np.isfinite(sig)
        dd = np.nonzero(ev)[0]
        if dd.size == 0:
            continue
        deficit = beta[dd] * gl[dd][:, None] - gp[dd]
        s = -np.sign(deficit) if fade else np.sign(deficit)
        good = np.isfinite(deficit) & (s != 0)
        ei, pi = np.nonzero(good)
        d_.append(dd[ei]); b_.append(np.zeros(ei.size, np.int64))
        col_.append(np.asarray(cols)[pi]); sgn_.append(s[ei, pi]); ev_.append(ei + ev0)
        ev0 += dd.size
    if not d_:
        return Trades(name, [], [], [], [], hold, [])
    return Trades(name, np.concatenate(d_), np.concatenate(b_), np.concatenate(col_),
                  np.concatenate(sgn_), hold, np.concatenate(ev_), hold_to_close=hold_to_close)


def build_latemove(P, name, groups, k, hold, fade=False, hold_to_close=True):
    """Leader's last-30-min move on day d-1 -> peer's gap on day d. Enter day d at bar 0+lag."""
    d_, b_, col_, sgn_, ev_ = [], [], [], [], []
    ev0 = 0
    for gname, (leader, peers) in groups.items():
        cols = [P.idx[p] for p in peers if p in P.idx]
        if not cols:
            continue
        L = P.idx[leader]
        c = P.close.astype(np.float64)
        late = c[:, LASTBAR, L] / c[:, LASTBAR - 6, L] - 1.0        # 30 min
        sd = np.full(P.D, np.nan)
        cs = np.cumsum(np.concatenate([[0.0], np.nan_to_num(late) ** 2]))
        sd[60:] = np.sqrt((cs[60:-1] - cs[:-61]) / 60.0)
        beta, _ = rolling_gap_stats(P, leader, cols)
        gp = P.gap[:, cols].astype(np.float64)
        with np.errstate(invalid="ignore"):
            ev = np.abs(late) > k * sd
        ev &= np.isfinite(late) & np.isfinite(sd)
        dprev = np.nonzero(ev)[0]
        dprev = dprev[dprev + 1 < P.D]
        if dprev.size == 0:
            continue
        dd = dprev + 1                                        # the session we trade
        deficit = beta[dd] * late[dprev][:, None] - gp[dd]
        s = -np.sign(deficit) if fade else np.sign(deficit)
        good = np.isfinite(deficit) & (s != 0)
        ei, pi = np.nonzero(good)
        d_.append(dd[ei]); b_.append(np.zeros(ei.size, np.int64))
        col_.append(np.asarray(cols)[pi]); sgn_.append(s[ei, pi]); ev_.append(ei + ev0)
        ev0 += dd.size
    if not d_:
        return Trades(name, [], [], [], [], hold, [])
    return Trades(name, np.concatenate(d_), np.concatenate(b_), np.concatenate(col_),
                  np.concatenate(sgn_), hold, np.concatenate(ev_), hold_to_close=hold_to_close)


def index_groups():
    return {f"IDX_{h}": (h, ["QQQ"]) for h in INDEX_HEAVIES}


def all_formulas(P):
    G = GROUPS
    F = {}
    F["C1a_INTRA_CATCHUP_k3_h3"] = build_leader_formula(P, "C1a", G, 3.0, 3)
    F["C1b_INTRA_CATCHUP_k3_h6"] = build_leader_formula(P, "C1b", G, 3.0, 6)
    F["C1c_INTRA_CATCHUP_k4_h6"] = build_leader_formula(P, "C1c", G, 4.0, 6)
    F["C1d_INTRA_CATCHUP_k3_h3_HEDGED"] = build_leader_formula(P, "C1d", G, 3.0, 3, hedged=True)
    F["C2a_INTRA_FADE_k3_h3"] = build_leader_formula(P, "C2a", G, 3.0, 3, fade=True)
    F["C2b_INTRA_FADE_k3_h12"] = build_leader_formula(P, "C2b", G, 3.0, 12, fade=True)
    IG = index_groups()
    F["C3a_HEAVY_TO_INDEX_k3_h6"] = build_leader_formula(P, "C3a", IG, 3.0, 6)
    F["C3b_HEAVY_TO_INDEX_k3_h6_HEDGED"] = build_leader_formula(P, "C3b", IG, 3.0, 6, hedged=True)
    F["C4a_BREADTH_LAGGARD_k2_h6"] = build_breadth(P, "C4a", G, 2.0, 6)
    F["C4b_BREADTH_LAGGARD_k3_h12"] = build_breadth(P, "C4b", G, 3.0, 12)
    F["C5a_GAP_CATCHUP_close"] = build_gap(P, "C5a", G, 2.0, 0, hold_to_close=True)
    F["C5b_GAP_CATCHUP_h12"] = build_gap(P, "C5b", G, 2.0, 12)
    F["C6a_GAP_FADE_close"] = build_gap(P, "C6a", G, 2.0, 0, fade=True, hold_to_close=True)
    F["C6b_GAP_FADE_h12"] = build_gap(P, "C6b", G, 2.0, 12, fade=True)
    F["C7a_LATEMOVE_NEXTOPEN_CATCHUP"] = build_latemove(P, "C7a", G, 2.0, 0)
    F["C7b_LATEMOVE_NEXTOPEN_FADE"] = build_latemove(P, "C7b", G, 2.0, 0, fade=True)
    F["C8a_VOLSHOCK_CATCHUP_h6"] = build_leader_formula(P, "C8a", G, 4.0, 6, volshock=True)
    F["C8b_VOLSHOCK_FADE_h6"] = build_leader_formula(P, "C8b", G, 4.0, 6, volshock=True, fade=True)
    F["C9a_ETF_LEADS_STOCK_CATCHUP_h6"] = build_leader_formula(P, "C9a", ETF_GROUPS, 3.0, 6)
    F["C9b_ETF_LEADS_STOCK_FADE_h6"] = build_leader_formula(P, "C9b", ETF_GROUPS, 3.0, 6, fade=True)
    F["C10a_INTRA_CATCHUP_DOWNONLY_k3_h6"] = build_leader_formula(P, "C10a", G, 3.0, 6, sign_filter=-1)
    F["C10b_INTRA_CATCHUP_UPONLY_k3_h6"] = build_leader_formula(P, "C10b", G, 3.0, 6, sign_filter=1)
    F["C11a_CUM30_CATCHUP_k3_h6"] = build_leader_formula(P, "C11a", G, 3.0, 6, cum=6)
    F["C11b_CUM30_FADE_k3_h6"] = build_leader_formula(P, "C11b", G, 3.0, 6, cum=6, fade=True)
    F["C12a_DISPERSION_NEUTRAL_k3_h6"] = build_leader_formula(P, "C12a", G, 3.0, 6, dispersion=True)
    F["C12b_DISPERSION_NEUTRAL_k3_h39"] = build_leader_formula(P, "C12b", G, 3.0, 39, dispersion=True)
    return F


# ----------------------------------------------------------------- stages

def stage_selftest():
    """Synthetic panel with a KNOWN sympathy effect, to prove (a) the engine finds a real
    catch-up, and (b) it does NOT find one that lives entirely in the bar we refuse to trade."""
    rng = np.random.default_rng(7)
    D, S = 400, 3
    syms = ["LEAD", "PEER_LATE", "PEER_INSTANT"]
    base = rng.normal(0, 0.001, (D, NBAR))          # common factor, gives the peers a real beta
    r = np.empty((D, NBAR, S))
    for j in range(S):
        r[:, :, j] = base + rng.normal(0, 0.0005, (D, NBAR))
    shock = rng.random((D, NBAR)) < 0.02
    shock[:, 0] = False
    shock[:, LASTBAR - 8:] = False
    sh = np.where(shock, 0.02, 0.0) * rng.choice([-1.0, 1.0], (D, NBAR))
    r[:, :, 0] += sh                                 # leader takes the whole shock at bar b
    dd, bb = np.nonzero(shock)
    # both peers take 40% of the shock at bar b -- so both have the same estimated beta and the
    # same measured deficit. They differ ONLY in WHEN the remaining 60% arrives.
    r[dd, bb, 1] += 0.4 * sh[dd, bb]
    r[dd, bb, 2] += 0.4 * sh[dd, bb]
    # PEER_LATE catches up over bars b+2 and b+3 -- reachable from an honest b+1 fill
    r[dd, bb + 2, 1] += 0.3 * sh[dd, bb]
    r[dd, bb + 3, 1] += 0.3 * sh[dd, bb]
    # PEER_INSTANT catches up entirely in bar b+1, the bar an honest fill forfeits
    r[dd, bb + 1, 2] += 0.6 * sh[dd, bb]
    close = 100.0 * np.exp(np.cumsum(r.reshape(D * NBAR, S), axis=0)).reshape(D, NBAR, S)
    syn = dict(syms=syms, close=close.astype(np.float32),
               dvol=np.full((D, NBAR, S), 1e6, np.float32),
               daykey=np.array([f"20{20 + i // 250:02d}-{1 + (i // 21) % 12:02d}-"
                                f"{1 + i % 21:02d}" for i in range(D)]),
               D=D, S=S, idx={s: i for i, s in enumerate(syms)},
               half_bp=np.full(S, 1.0), cost_rt=np.full(S, 2.3e-4),
               cost_provenance="SYNTHETIC")
    P = Panel(synthetic=syn)
    P._returns()
    g = {"T": ("LEAD", ["PEER_LATE", "PEER_INSTANT"])}
    res = {}
    for peer in ["PEER_LATE", "PEER_INSTANT"]:
        tr = build_leader_formula(P, "t", {"T": ("LEAD", [peer])}, 3.0, 6)
        m = np.ones(P.D, bool)
        for lag in (1, 2):
            pnl, dg = evaluate(P, tr, m, lag=lag)
            res[f"{peer}_lag{lag}_sharpe"] = sharpe(pnl)
            res[f"{peer}_lag{lag}_n"] = dg.get("n_legs", 0)
    # a signal built on pure noise must not produce an edge
    tr0 = build_leader_formula(P, "t", {"T": ("LEAD", ["PEER_LATE"])}, 3.0, 6)
    flip = rng.choice([-1.0, 1.0], size=tr0.ev.max() + 1)
    pnl, _ = evaluate(P, tr0, np.ones(P.D, bool), lag=1, flip=flip)
    res["sign_flipped_sharpe"] = sharpe(pnl)
    ok = (res["PEER_LATE_lag1_sharpe"] > 3.0
          and abs(res["PEER_INSTANT_lag1_sharpe"]) < res["PEER_LATE_lag1_sharpe"] / 2
          and abs(res["sign_flipped_sharpe"]) < 2.0)
    res["PASS"] = bool(ok)
    (OUT / "INVENT_0823_sympathy_SELFTEST.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    if not ok:
        sys.exit("SELFTEST FAILED")


def stage_design():
    check_prereg()
    P = Panel()
    F = all_formulas(P)
    m = P.window(DESIGN)
    rows = {}
    daily = {}
    for name, tr in F.items():
        row = {}
        for lag in (0, 1, 2, 3, 6):
            pnl, dg = evaluate(P, tr, m, lag=lag)
            row[f"net_sharpe_lag{lag}"] = sharpe(pnl)
            if lag == 1:
                g, _ = evaluate(P, tr, m, lag=1, gross_only=True)
                row["gross_sharpe"] = sharpe(g)
                row["net_sharpe"] = row["net_sharpe_lag1"]
                row["mean_net_bp_per_active_day"] = float(
                    np.mean(pnl[pnl != 0]) * 1e4) if (pnl != 0).any() else 0.0
                row.update(dg)
                daily[name] = pnl
        rows[name] = row
        print(f"{name:38s} gross {row['gross_sharpe']:+6.2f}  net {row['net_sharpe']:+7.2f} "
              f"lag0 {row['net_sharpe_lag0']:+7.2f} lag2 {row['net_sharpe_lag2']:+7.2f} "
              f"n={row.get('n_legs',0)} ev={row.get('n_events',0)}")
    np.savez_compressed(OUT / "INVENT_0823_sympathy_DESIGN_daily.npz", **daily)
    (OUT / "INVENT_0823_sympathy_DESIGN.json").write_text(json.dumps(
        {"window": DESIGN, "n_sessions": int(m.sum()), "cost_provenance": P.cost_provenance,
         "formulas": rows}, indent=1))


def stage_diag():
    """The mechanism, not the verdict. (1) The event study: after a leader shock, what does the
    peer actually do, bar by bar, in the direction the deficit says it should? (2) How big is the
    mispricing in bp versus what a round trip costs? (3) gross Sharpe as a function of entry lag
    -- including lag 0, the shared print we refuse to trade."""
    check_prereg()
    P = Panel()
    m = P.window(DESIGN)
    H = 13
    out = {"window": DESIGN}

    # ---- (1)(2) event study, pooled over the nine stock-led groups, k = 3
    acc = np.zeros(H); accn = np.zeros(H); acc2 = np.zeros(H)
    defbp = []
    per_group = {}
    for gname, (leader, peers) in GROUPS.items():
        cols = [P.idx[p] for p in peers if p in P.idx]
        beta, sig = rolling_stats(P, leader, cols)
        msk, rlead = _shock_events(P, leader, 3.0, sig)
        msk[:, LASTBAR - H:] = False
        dd, bb = np.nonzero(msk)
        if dd.size == 0:
            continue
        bet = beta[dd]
        deficit = bet * rlead[dd, bb][:, None] - P.ret[:, :, cols].astype(np.float64)[dd, bb]
        s = np.sign(deficit)
        keep = m[dd]
        c = P.close.astype(np.float64)
        g_acc = np.zeros(H)
        for j in range(H):
            fwd = c[dd, bb + j, :][:, cols] / c[dd, bb, :][:, cols] - 1.0
            v = (s * fwd)[keep]
            v = v[np.isfinite(v)]
            acc[j] += v.sum(); accn[j] += v.size; acc2[j] += (v ** 2).sum()
            g_acc[j] = float(v.mean() * 1e4) if v.size else np.nan
        dsel = np.abs(deficit)[keep]
        defbp.append(dsel[np.isfinite(dsel)].ravel())
        per_group[gname] = {
            "n_events": int(keep.sum()),
            "cum_signed_peer_move_bp": [round(x, 2) for x in g_acc],
            "mean_abs_deficit_bp": float(np.nanmean(np.abs(deficit)[keep]) * 1e4),
            "mean_peer_roundtrip_cost_bp": float(np.mean(P.cost_rt[cols]) * 1e4),
        }
    mean = acc / np.maximum(accn, 1) * 1e4
    sd = np.sqrt(np.maximum(acc2 / np.maximum(accn, 1) - (acc / np.maximum(accn, 1)) ** 2, 0)) * 1e4
    se = sd / np.sqrt(np.maximum(accn, 1))
    alldef = np.concatenate(defbp) * 1e4
    out["event_study_pooled"] = {
        "note": "cumulative SIGNED peer return from the close of the signal bar, in bp; "
                "offset 0 is the signal bar itself, offset 1 is the bar an honest fill forfeits",
        "n_leg_events": int(accn[1]),
        "cum_bp": [round(x, 3) for x in mean],
        "se_bp": [round(x, 3) for x in se],
        "t": [round(mean[j] / se[j], 2) if se[j] > 0 else None for j in range(H)],
        "mean_abs_deficit_bp": round(float(alldef.mean()), 2),
        "median_abs_deficit_bp": round(float(np.median(alldef)), 2),
        "mean_peer_roundtrip_cost_bp": round(float(np.mean(P.cost_rt) * 1e4), 2),
    }
    out["per_group"] = per_group

    # ---- (3) gross Sharpe by entry lag, and gross bp per leg-trade
    F = all_formulas(P)
    bylag = {}
    for name, tr in F.items():
        row = {}
        for lag in (0, 1, 2, 3, 6):
            g, dg = evaluate(P, tr, m, lag=lag, gross_only=True)
            row[f"gross_sharpe_lag{lag}"] = round(sharpe(g), 3)
        n, dg = evaluate(P, tr, m, lag=1)
        g, _ = evaluate(P, tr, m, lag=1, gross_only=True)
        act = g[g != 0]
        row["gross_bp_per_event_day"] = round(float(act.mean() * 1e4), 3) if act.size else None
        row["cost_bp_per_event_day"] = round(float((g - n)[g != 0].mean() * 1e4), 3) if act.size else None
        row["cost_over_gross"] = (round(row["cost_bp_per_event_day"] / row["gross_bp_per_event_day"], 2)
                                  if row["gross_bp_per_event_day"] not in (None, 0) else None)
        bylag[name] = row
    out["by_lag"] = bylag
    (OUT / "INVENT_0823_sympathy_DIAG.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["event_study_pooled"], indent=1))
    for k2, v in bylag.items():
        print(f"{k2:38s} gross lag0 {v['gross_sharpe_lag0']:+6.2f} lag1 {v['gross_sharpe_lag1']:+6.2f} "
              f"lag2 {v['gross_sharpe_lag2']:+6.2f} | gross {v['gross_bp_per_event_day']} bp "
              f"cost {v['cost_bp_per_event_day']} bp  c/g {v['cost_over_gross']}")


def stage_nulls(ndraw=400):
    check_prereg()
    P = Panel()
    F = all_formulas(P)
    m = P.window(DESIGN)
    rng = np.random.default_rng(20260823)
    names = list(F)
    maxA, maxB = [], []
    perA = {n: [] for n in names}
    perB = {n: [] for n in names}
    for i in range(ndraw):
        sA, sB = [], []
        delta = int(rng.choice(np.concatenate([np.arange(-60, -4), np.arange(5, 61)])))
        for n in names:
            tr = F[n]
            a, _ = evaluate(P, tr, m, lag=1, day_shift=delta)
            v = sharpe(a)
            sA.append(v if np.isfinite(v) else 0.0)
            perA[n].append(sA[-1])
            nev = int(tr.ev.max()) + 1 if len(tr) else 1
            flip = rng.choice([-1.0, 1.0], size=nev)
            b, _ = evaluate(P, tr, m, lag=1, flip=flip)
            v = sharpe(b)
            sB.append(v if np.isfinite(v) else 0.0)
            perB[n].append(sB[-1])
        maxA.append(max(sA)); maxB.append(max(sB))
        if (i + 1) % 50 == 0:
            print(f"  draw {i+1}/{ndraw}  maxA p95 {np.percentile(maxA,95):.2f} "
                  f"maxB p95 {np.percentile(maxB,95):.2f}", flush=True)
    res = {
        "ndraw": ndraw,
        "analytic_bar": float(np.sqrt(2 * np.log(len(names))) / np.sqrt(1005 / 252)),
        "placeboA_dayshift": {"mean_max": float(np.mean(maxA)), "p95_max": float(np.percentile(maxA, 95)),
                              "p99_max": float(np.percentile(maxA, 99))},
        "placeboB_signflip": {"mean_max": float(np.mean(maxB)), "p95_max": float(np.percentile(maxB, 95)),
                              "p99_max": float(np.percentile(maxB, 99))},
        "per_formula_p95": {n: {"A": float(np.percentile(perA[n], 95)),
                                "B": float(np.percentile(perB[n], 95))} for n in names},
    }
    (OUT / "INVENT_0823_sympathy_NULLS.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "per_formula_p95"}, indent=1))


def stage_shortlist():
    check_prereg()
    des = json.loads((OUT / "INVENT_0823_sympathy_DESIGN.json").read_text())
    nul = json.loads((OUT / "INVENT_0823_sympathy_NULLS.json").read_text())
    bar = max(nul["placeboA_dayshift"]["p95_max"], nul["placeboB_signflip"]["p95_max"],
              nul["analytic_bar"])
    passed, near = [], []
    for n, r in des["formulas"].items():
        g = r["gross_sharpe"]
        chk = {
            "gross_beats_bar": bool(np.isfinite(g) and g > bar),
            "net_positive": bool(r["net_sharpe"] > 0),
            "enough_trades": bool(r.get("n_legs", 0) >= 400 and r.get("active_days", 0) >= 150),
            "lag_robust": bool(np.isfinite(r["net_sharpe_lag2"]) and r["net_sharpe"] > 0
                               and r["net_sharpe_lag2"] >= 0.5 * r["net_sharpe"]),
        }
        rec = {"name": n, "gross": g, "net": r["net_sharpe"], "checks": chk,
               "all_pass": all(chk.values())}
        (passed if rec["all_pass"] else near).append(rec)
    passed.sort(key=lambda x: -x["net"])
    near.sort(key=lambda x: -x["net"])
    picks = [p["name"] for p in passed[:3]] or [p["name"] for p in near[:2]]
    doc = {"bar_used": bar, "bars": {"analytic": nul["analytic_bar"],
                                     "placeboA_p95": nul["placeboA_dayshift"]["p95_max"],
                                     "placeboB_p95": nul["placeboB_signflip"]["p95_max"]},
           "n_passing_all_gates": len(passed), "passed": passed, "near_misses": near[:6],
           "held_out_picks": picks,
           "promotion": bool(passed),
           "label": "PROMOTION" if passed else "BELOW THE NOISE BAR -- near-miss report only"}
    (OUT / "INVENT_0823_sympathy_SHORTLIST.json").write_text(json.dumps(doc, indent=1))
    print(json.dumps({k: doc[k] for k in ("bar_used", "bars", "n_passing_all_gates",
                                          "held_out_picks", "label")}, indent=1))


def stage_holdout():
    check_prereg()
    sl = json.loads((OUT / "INVENT_0823_sympathy_SHORTLIST.json").read_text())
    P = Panel()
    F = all_formulas(P)
    m = P.window(HELDOUT)
    res = {"window": HELDOUT, "n_sessions": int(m.sum()), "label": sl["label"], "formulas": {}}
    for n in sl["held_out_picks"]:
        tr = F[n]
        row = {}
        for lag in (0, 1, 2, 3, 6):
            pnl, dg = evaluate(P, tr, m, lag=lag)
            row[f"net_sharpe_lag{lag}"] = sharpe(pnl)
            if lag == 1:
                g, _ = evaluate(P, tr, m, lag=1, gross_only=True)
                row["gross_sharpe"] = sharpe(g)
                row["net_sharpe"] = row["net_sharpe_lag1"]
                row["t_net"] = row["net_sharpe"] * np.sqrt(int(m.sum()) / 252)
                row.update(dg)
        res["formulas"][n] = row
        print(f"HELDOUT {n:38s} gross {row['gross_sharpe']:+6.2f} net {row['net_sharpe']:+7.2f} "
              f"t {row['t_net']:+5.2f} n={row.get('n_legs',0)}")
    (OUT / "INVENT_0823_sympathy_HOLDOUT.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["selftest", "design", "diag", "nulls", "shortlist", "holdout"])
    ap.add_argument("--ndraw", type=int, default=400)
    a = ap.parse_args()
    {"selftest": stage_selftest, "design": stage_design, "diag": stage_diag,
     "nulls": lambda: stage_nulls(a.ndraw), "shortlist": stage_shortlist,
     "holdout": stage_holdout}[a.stage]()
