#!/usr/bin/env python3
"""INVENT_0823 EXOTIC / HARD-TETHER round -- 22 pre-declared formulas, four families.

Run:  python scripts/trading_bot/exo0823_sweep.py --stage design
      python scripts/trading_bot/exo0823_sweep.py --stage reveal

`design` writes every held-out field as the literal string "SEALED".
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from trading_bot.data import load_bars  # noqa: E402
from trading_bot import exo0823_fetch as F  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "exo0823_cache"
OUT = ROOT / "research" / "trading_bot"

# ------------------------------------------------------------------ windows (frozen)
# Long-history families (H, L, F).
D0, D1 = "2016-01-05", "2023-12-29"
H0, H1 = "2024-01-02", "2026-08-20"
# Coin-wrapper family (C): the wrappers did not exist before 2024-01-11 / 2024-07-23.
CD0, CD1 = "2024-01-16", "2025-06-30"
CH0, CH1 = "2025-07-01", "2026-08-20"

SEC_FEE_BP = 0.278 / 100.0 * 100.0  # 0.278 bp of sale notional, expressed in bp
OPEN_PREMIUM = 1.5   # opening prints are wider than the day's average quote
SPREAD_FLOOR_BP = 1.0
SPREAD_SHOCK = 2.0

BTC_WRAPPERS = [s for s in F.BTC_WRAPPERS if s != "BTC"]  # 'BTC' ticker is not the mini trust
ETH_WRAPPERS = [s for s in F.ETH_WRAPPERS if s != "ETH"]

EAFE_FX_BASKET = {"FXE": 0.35, "FXY": 0.28, "FXB": 0.17, "FXF": 0.10, "FXC": 0.10}


# ------------------------------------------------------------------ panel
def build_panel() -> dict:
    syms = F.all_symbols() + ["BIL", "SHV"]
    per = {}
    for s in syms:
        try:
            bars, _ = load_bars(s, F.START, F.END, "1Day", cache_dir=CACHE, allow_network=False)
        except Exception:
            continue
        d = np.array([b.ts_ns // 86_400_000_000_000 for b in bars], dtype=np.int64)
        o = np.array([b.open_micros for b in bars], dtype=np.float64) / 1e6
        c = np.array([b.close_micros for b in bars], dtype=np.float64) / 1e6
        hi = np.array([b.high_micros for b in bars], dtype=np.float64) / 1e6
        lo = np.array([b.low_micros for b in bars], dtype=np.float64) / 1e6
        v = np.array([b.volume_shares for b in bars], dtype=np.float64)
        per[s] = (d, o, c, hi, lo, v)
    master = np.array(sorted(set(per["SPY"][0].tolist())), dtype=np.int64)
    n = len(master)
    pos = {int(d): i for i, d in enumerate(master)}
    P = {}
    for s, (d, o, c, hi, lo, v) in per.items():
        O = np.full(n, np.nan)
        C = np.full(n, np.nan)
        HI = np.full(n, np.nan)
        LO = np.full(n, np.nan)
        V = np.zeros(n)
        for j, dd in enumerate(d):
            i = pos.get(int(dd))
            if i is None:
                continue
            O[i], C[i], HI[i], LO[i], V[i] = o[j], c[j], hi[j], lo[j], v[j]
        P[s] = {"o": O, "c": C, "h": HI, "l": LO, "v": V}
    return {"dates": master, "px": P}


def date_index(master: np.ndarray, iso: str) -> int:
    from datetime import date
    y, m, dd = (int(x) for x in iso.split("-"))
    days = (date(y, m, dd) - date(1970, 1, 1)).days
    return int(np.searchsorted(master, days))


# ------------------------------------------------------------------ cost: Corwin-Schultz
def corwin_schultz_halfspread(h: np.ndarray, lo: np.ndarray, i0: int, i1: int) -> float:
    """Effective half-spread in bp from daily highs/lows (Corwin & Schultz 2012).

    MEASURED from the same bars the backtest trades, not assumed.  Negative daily estimates
    are set to zero (the paper's own convention) and the series median is taken.
    """
    H = h[i0:i1]
    L = lo[i0:i1]
    ok = np.isfinite(H) & np.isfinite(L) & (L > 0)
    H, L = H[ok], L[ok]
    if len(H) < 60:
        return float("nan")
    hl = np.log(H / L) ** 2
    beta = hl[:-1] + hl[1:]
    H2 = np.maximum(H[:-1], H[1:])
    L2 = np.minimum(L[:-1], L[1:])
    gamma = np.log(H2 / L2) ** 2
    k = 3 - 2 * np.sqrt(2.0)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    s = np.where(s < 0, 0.0, s)
    return float(np.median(s) / 2.0 * 1e4)  # half-spread, bp


# ------------------------------------------------------------------ helpers
def cumlogret(c: np.ndarray) -> np.ndarray:
    r = np.full(len(c), np.nan)
    r[1:] = np.log(c[1:] / c[:-1])
    out = np.full(len(c), np.nan)
    fin = np.isfinite(r)
    acc = 0.0
    for i in range(len(c)):
        if fin[i]:
            acc += r[i]
            out[i] = acc
        elif np.isfinite(c[i]):
            out[i] = acc
    return out


def logret(c: np.ndarray) -> np.ndarray:
    r = np.full(len(c), np.nan)
    r[1:] = np.log(c[1:] / c[:-1])
    return r


def rollz(x: np.ndarray, w: int) -> np.ndarray:
    n = len(x)
    z = np.full(n, np.nan)
    for i in range(w, n):
        seg = x[i - w:i + 1]
        if not np.all(np.isfinite(seg)):
            continue
        sd = seg.std(ddof=1)
        if sd <= 0:
            continue
        z[i] = (x[i] - seg.mean()) / sd
    return z


def diffk(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    out[k:] = x[k:] - x[:-k]
    return out


# ------------------------------------------------------------------ book construction
class Book:
    """Target weights per (day, symbol). Weights are formed from data THROUGH CLOSE t-1 and
    executed at the OPEN of day t. Gross exposure normalised to 1.0, split into H overlapping
    daily tranches."""

    def __init__(self, syms, n):
        self.syms = list(syms)
        self.idx = {s: i for i, s in enumerate(self.syms)}
        self.raw = np.zeros((n, len(self.syms)))
        self.n = n

    def add(self, t, sym, w):
        self.raw[t, self.idx[sym]] += w


def normalise_and_stagger(raw: np.ndarray, H: int) -> np.ndarray:
    g = np.abs(raw).sum(axis=1)
    w = np.zeros_like(raw)
    nz = g > 1e-12
    w[nz] = raw[nz] / g[nz][:, None]
    if H <= 1:
        return w
    out = np.zeros_like(w)
    for k in range(H):
        out[k:] += w[:len(w) - k] / H
    return out


def evaluate(w_target: np.ndarray, syms, px, halfspread_bp, i0, i1, shock=1.0, mode="open"):
    """Return dict of gross/net stats over [i0, i1).

    mode='open'       (headline)  w[t] is formed from data through CLOSE t-1, executed at the
                                  OPEN of t, and earns OPEN t -> OPEN t+1.  A closing-print
                                  bid-ask bounce in the signal therefore cannot be harvested.
    mode='close_lag'  (robustness) same signal, executed at the CLOSE of t, earns C t -> C t+1.
    mode='close_same' (CONTAMINATED, diagnostic only) the signal formed at close t earns
                                  C t -> C t+1: this is the construction that lets a closing
                                  bounce pay itself, and it is reported only to size that bounce.
    """
    n_days = i1 - i0
    key = "o" if mode == "open" else "c"
    if mode == "close_same":
        w_target = np.vstack([w_target[1:], w_target[-1:]])
    O = np.column_stack([px[s][key] for s in syms])
    R = np.full(O.shape, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        R[:-1] = O[1:] / O[:-1] - 1.0
    R[~np.isfinite(R)] = 0.0
    W = w_target.copy()
    W[~np.isfinite(W)] = 0.0
    # a leg with no price that day cannot be held
    live = np.isfinite(O) & (O > 0)
    W = np.where(live, W, 0.0)
    gross = (W[i0:i1] * R[i0:i1]).sum(axis=1)
    dW = np.abs(np.diff(np.vstack([W[i0 - 1:i0], W[i0:i1]]), axis=0))
    hs = np.array([halfspread_bp[s] for s in syms]) * OPEN_PREMIUM * shock / 1e4
    cost = (dW * hs[None, :]).sum(axis=1)
    sec = (np.maximum(-np.diff(np.vstack([W[i0 - 1:i0], W[i0:i1]]), axis=0), 0).sum(axis=1)
           * SEC_FEE_BP / 1e4)
    net = gross - cost - sec
    turn = dW.sum(axis=1)

    def sh(x):
        s = x.std(ddof=1)
        return float(x.mean() / s * np.sqrt(252)) if s > 0 else 0.0

    yrs = n_days / 252.0
    return {
        "days": int(n_days),
        "net_cash_weight": float(W[i0:i1].sum(axis=1).mean()),
        "short_weight": float(np.minimum(W[i0:i1], 0).sum(axis=1).mean()),
        "gross_sharpe": sh(gross),
        "net_sharpe": sh(net),
        "gross_t": sh(gross) * np.sqrt(yrs),
        "net_t": sh(net) * np.sqrt(yrs),
        "gross_bp_day": float(gross.mean() * 1e4),
        "net_bp_day": float(net.mean() * 1e4),
        "turnover_day": float(turn.mean()),
        "breakeven_bp": (float(gross.mean() / turn.mean() * 1e4 / OPEN_PREMIUM)
                         if turn.mean() > 0 else float("nan")),
        "_gross": gross,
        "_net": net,
    }


# ------------------------------------------------------------------ family builders
def build_all(panel):
    px = panel["px"]
    n = len(panel["dates"])
    specs = []   # (name, family, syms, raw_weight_matrix, H)

    # ---------------- FAMILY C : same-coin wrapper cross-section
    def coin_group(wrappers):
        avail = [s for s in wrappers if s in px]
        cl = {s: cumlogret(px[s]["c"]) for s in avail}
        M = np.column_stack([cl[s] for s in avail])
        ok = np.isfinite(M).all(axis=1)
        idxv = np.full(n, np.nan)
        idxv[ok] = M[ok].mean(axis=1)
        S = np.full(M.shape, np.nan)
        S[ok] = M[ok] - idxv[ok][:, None]
        return avail, S, ok

    btc_syms, btc_S, btc_ok = coin_group(BTC_WRAPPERS)
    eth_syms, eth_S, eth_ok = coin_group(ETH_WRAPPERS)

    def xs_book(groups, scorer, H, name, fam, perm=None):
        syms = sorted({s for g, _, _ in groups for s in g})
        raw = np.zeros((n, len(syms)))
        pos = {s: i for i, s in enumerate(syms)}
        for g, S, ok in groups:
            sc = scorer(S)
            if perm is not None:
                p = perm(len(g))
                sc = sc[:, p]
            for t in range(1, n):
                v = sc[t - 1]
                if not np.all(np.isfinite(v)) or not ok[t - 1]:
                    continue
                v = v - v.mean()
                a = np.abs(v).sum()
                if a <= 1e-12:
                    continue
                v = v / a
                for j, s in enumerate(g):
                    raw[t, pos[s]] += v[j]
        return (name, fam, syms, raw, H)

    def sc_negz(w):
        return lambda S: -np.column_stack([rollz(S[:, j], w) for j in range(S.shape[1])])

    def sc_negdiff(k):
        return lambda S: -np.column_stack([diffk(S[:, j], k) for j in range(S.shape[1])])

    G = [(btc_syms, btc_S, btc_ok), (eth_syms, eth_S, eth_ok)]
    specs.append(xs_book(G, sc_negz(20), 5, "C1_coin_z20_rev_H5", "C"))
    specs.append(xs_book(G, sc_negz(60), 5, "C2_coin_z60_rev_H5", "C"))
    specs.append(xs_book(G, sc_negdiff(1), 1, "C3_coin_d1_rev_H1", "C"))
    specs.append(xs_book(G, sc_negdiff(5), 5, "C4_coin_d5_rev_H5", "C"))
    specs.append(xs_book(G, sc_negdiff(20), 20, "C5_coin_d20_rev_H20", "C"))
    specs.append(xs_book(G, sc_negz(20), 1, "C6_coin_z20_rev_H1", "C"))

    rng = np.random.default_rng(20260823)
    fixed_perm = {}

    def permfn(k):
        if k not in fixed_perm:
            fixed_perm[k] = rng.permutation(k)
        return fixed_perm[k]

    placebo_C = xs_book(G, sc_negz(20), 5, "PLACEBO_C_idperm", "PLACEBO", perm=permfn)

    # ---------------- FAMILY H : FX-hedged triangle
    tris = []
    for u, h, x, lab in F.FX_TRIANGLES:
        if u not in px or h not in px:
            continue
        ru, rh = logret(px[u]["c"]), logret(px[h]["c"])
        if x == "BASKET":
            legs = {k: v for k, v in EAFE_FX_BASKET.items() if k in px}
            tot = sum(legs.values())
            legs = {k: v / tot for k, v in legs.items()}
            rx = np.zeros(n)
            m = np.ones(n, dtype=bool)
            for k, wgt in legs.items():
                rk = logret(px[k]["c"])
                m &= np.isfinite(rk)
                rx += np.nan_to_num(rk) * wgt
            rx = np.where(m, rx, np.nan)
        else:
            legs = {x: 1.0}
            rx = logret(px[x]["c"])
        e = np.full(n, np.nan)
        acc = 0.0
        for i in range(n):
            d = ru[i] - rh[i] - rx[i]
            if np.isfinite(d):
                acc += d
                e[i] = acc
        tris.append({"u": u, "h": h, "legs": legs, "e": e, "lab": lab})

    def tri_book(sel, scorer, H, name, xs=False):
        use = [t for t in tris if sel(t)]
        syms = sorted({t["u"] for t in use} | {t["h"] for t in use}
                      | {k for t in use for k in t["legs"]})
        raw = np.zeros((n, len(syms)))
        pos = {s: i for i, s in enumerate(syms)}
        sig = np.column_stack([scorer(t["e"]) for t in use])
        for t_i in range(1, n):
            v = sig[t_i - 1].copy()
            fin = np.isfinite(v)
            if not fin.any():
                continue
            v = np.where(fin, v, 0.0)
            if xs:
                v[fin] = v[fin] - v[fin].mean()
                r = np.argsort(np.argsort(v[fin]))
                q = np.zeros(fin.sum())
                nn = fin.sum()
                q[r >= nn - 2] = 1.0
                q[r < 2] = -1.0
                v = np.zeros_like(v)
                v[fin] = q
            a = np.abs(v).sum()
            if a <= 1e-12:
                continue
            v = v / a
            for j, tr in enumerate(use):
                if v[j] == 0:
                    continue
                raw[t_i, pos[tr["u"]]] += v[j]
                raw[t_i, pos[tr["h"]]] -= v[j]
                for k, wgt in tr["legs"].items():
                    raw[t_i, pos[k]] -= v[j] * wgt
        return (name, "H", syms, raw, H)

    CLEAN = {"eurozone_ishares", "germany_ishares", "japan_ishares", "uk_ishares"}
    specs.append(tri_book(lambda t: True, lambda e: -rollz(e, 20), 5, "H1_tri_z20_H5"))
    specs.append(tri_book(lambda t: True, lambda e: -rollz(e, 60), 5, "H2_tri_z60_H5"))
    specs.append(tri_book(lambda t: True, lambda e: -rollz(e, 20), 1, "H3_tri_z20_H1"))
    specs.append(tri_book(lambda t: True, lambda e: -diffk(e, 5), 5, "H4_tri_d5_H5"))
    specs.append(tri_book(lambda t: t["lab"] in CLEAN, lambda e: -rollz(e, 20), 5,
                          "H5_tri_clean_z20_H5"))
    specs.append(tri_book(lambda t: True, lambda e: -rollz(e, 20), 5, "H6_tri_xs_z20_H5",
                          xs=True))

    # ---------------- FAMILY L : leveraged path residual
    levs = []
    for lev, base, m in F.LEVERED:
        if lev not in px or base not in px:
            continue
        rl, rb = logret(px[lev]["c"]), logret(px[base]["c"])
        # residual of one day's realised levered log return vs m x base simple return
        d1 = np.full(n, np.nan)
        for i in range(n):
            if np.isfinite(rl[i]) and np.isfinite(rb[i]):
                theo = np.log1p(m * (np.exp(rb[i]) - 1.0)) if 1 + m * (np.exp(rb[i]) - 1) > 0 \
                    else np.nan
                d1[i] = rl[i] - theo
        cum = np.full(n, np.nan)
        acc = 0.0
        for i in range(n):
            if np.isfinite(d1[i]):
                acc += d1[i]
                cum[i] = acc
        levs.append({"lev": lev, "base": base, "m": m, "d1": d1, "cum": cum})

    def lev_book(sel, scorer, H, name, xs=False):
        use = [x for x in levs if sel(x)]
        syms = sorted({x["lev"] for x in use} | {x["base"] for x in use})
        raw = np.zeros((n, len(syms)))
        pos = {s: i for i, s in enumerate(syms)}
        sig = np.column_stack([scorer(x) for x in use])
        for t_i in range(1, n):
            v = sig[t_i - 1].copy()
            fin = np.isfinite(v)
            if not fin.any():
                continue
            v = np.where(fin, v, 0.0)
            if xs:
                vv = v[fin] - v[fin].mean()
                r = np.argsort(np.argsort(vv))
                nn = len(vv)
                q = np.zeros(nn)
                q[r >= nn - 5] = 1.0
                q[r < 5] = -1.0
                v = np.zeros_like(v)
                v[fin] = q
            a = np.abs(v).sum()
            if a <= 1e-12:
                continue
            v = v / a
            for j, L in enumerate(use):
                if v[j] == 0:
                    continue
                raw[t_i, pos[L["lev"]]] += v[j]
                raw[t_i, pos[L["base"]]] -= v[j] * L["m"]
        return (name, "L", syms, raw, H)

    specs.append(lev_book(lambda x: True, lambda x: -rollz(x["d1"], 20), 1, "L1_lev_te_z20_H1"))
    specs.append(lev_book(lambda x: True, lambda x: -diffk(x["cum"], 5), 5, "L2_lev_d5_H5"))
    specs.append(lev_book(lambda x: True, lambda x: -rollz(diffk(x["cum"], 20), 60), 5,
                          "L3_lev_d20z60_H5"))
    specs.append(lev_book(lambda x: True, lambda x: -rollz(diffk(x["cum"], 20), 60), 5,
                          "L4_lev_xs_H5", xs=True))
    specs.append(lev_book(lambda x: x["m"] > 0, lambda x: -rollz(diffk(x["cum"], 20), 60), 5,
                          "L5_levbull_d20z60_H5"))

    # L6: bull/bear parity -- a delta-neutral combo of a bull and a bear fund on one index
    pairs = {}
    for x in levs:
        pairs.setdefault(x["base"], {"bull": [], "bear": []})
        (pairs[x["base"]]["bull"] if x["m"] > 0 else pairs[x["base"]]["bear"]).append(x)
    parity = []
    for base, d in pairs.items():
        if not d["bull"] or not d["bear"]:
            continue
        bl = max(d["bull"], key=lambda z: abs(z["m"]))
        br = max(d["bear"], key=lambda z: abs(z["m"]))
        rb1, rb2 = logret(px[bl["lev"]]["c"]), logret(px[br["lev"]]["c"])
        wl, wr = 1.0 / abs(bl["m"]), 1.0 / abs(br["m"])
        e = np.full(n, np.nan)
        acc = 0.0
        for i in range(n):
            if np.isfinite(rb1[i]) and np.isfinite(rb2[i]):
                acc += wl * rb1[i] + wr * rb2[i]
                e[i] = acc
        parity.append({"a": bl["lev"], "b": br["lev"], "wa": wl, "wb": wr, "e": e})

    def parity_book(scorer, H, name):
        syms = sorted({p["a"] for p in parity} | {p["b"] for p in parity})
        raw = np.zeros((n, len(syms)))
        pos = {s: i for i, s in enumerate(syms)}
        sig = np.column_stack([scorer(p["e"]) for p in parity])
        for t_i in range(1, n):
            v = sig[t_i - 1]
            fin = np.isfinite(v)
            if not fin.any():
                continue
            v = np.where(fin, v, 0.0)
            a = np.abs(v).sum()
            if a <= 1e-12:
                continue
            v = v / a
            for j, p in enumerate(parity):
                if v[j] == 0:
                    continue
                raw[t_i, pos[p["a"]]] += v[j] * p["wa"]
                raw[t_i, pos[p["b"]]] += v[j] * p["wb"]
        return (name, "L", syms, raw, H)

    specs.append(parity_book(lambda e: -rollz(e, 20), 5, "L6_bullbear_parity_z20_H5"))

    placebo_L = lev_book(lambda x: True, lambda x: -rollz(diffk(x["cum"], 20), 60), 5,
                         "PLACEBO_L_idperm", xs=True)
    # identity permutation: shuffle which pair gets which signal, fixed through time
    pl_name, pl_fam, pl_syms, pl_raw, pl_H = placebo_L
    use = levs
    p = rng.permutation(len(use))
    sig = np.column_stack([-rollz(diffk(x["cum"], 20), 60) for x in use])[:, p]
    raw = np.zeros((n, len(pl_syms)))
    pos = {s: i for i, s in enumerate(pl_syms)}
    for t_i in range(1, n):
        v = sig[t_i - 1].copy()
        fin = np.isfinite(v)
        if not fin.any():
            continue
        vv = v[fin] - v[fin].mean()
        r = np.argsort(np.argsort(vv))
        nn = len(vv)
        q = np.zeros(nn)
        q[r >= nn - 5] = 1.0
        q[r < 5] = -1.0
        v = np.zeros(len(v))
        v[fin] = q
        a = np.abs(v).sum()
        if a <= 1e-12:
            continue
        v = v / a
        for j, L in enumerate(use):
            if v[j] == 0:
                continue
            raw[t_i, pos[L["lev"]]] += v[j]
            raw[t_i, pos[L["base"]]] -= v[j] * L["m"]
    placebo_L = ("PLACEBO_L_idperm", "PLACEBO", pl_syms, raw, 5)

    # ---------------- FAMILY F : fund-of-funds published-weight replication
    fofs = []
    for fof, wts in F.FOF.items():
        if fof not in px:
            continue
        wts = {k: v for k, v in wts.items() if k in px}
        tot = sum(wts.values())
        wts = {k: v / tot for k, v in wts.items()}
        rf = logret(px[fof]["c"])
        rr = np.zeros(n)
        m = np.ones(n, dtype=bool)
        for k, wgt in wts.items():
            rk = logret(px[k]["c"])
            m &= np.isfinite(rk)
            rr += np.nan_to_num(rk) * wgt
        rr = np.where(m, rr, np.nan)
        e = np.full(n, np.nan)
        acc = 0.0
        for i in range(n):
            d = rf[i] - rr[i]
            if np.isfinite(d):
                acc += d
                e[i] = acc
        fofs.append({"f": fof, "w": wts, "e": e})

    def fof_book(scorer, H, name):
        syms = sorted({x["f"] for x in fofs} | {k for x in fofs for k in x["w"]})
        raw = np.zeros((n, len(syms)))
        pos = {s: i for i, s in enumerate(syms)}
        sig = np.column_stack([scorer(x["e"]) for x in fofs])
        for t_i in range(1, n):
            v = sig[t_i - 1]
            fin = np.isfinite(v)
            if not fin.any():
                continue
            v = np.where(fin, v, 0.0)
            a = np.abs(v).sum()
            if a <= 1e-12:
                continue
            v = v / a
            for j, x in enumerate(fofs):
                if v[j] == 0:
                    continue
                raw[t_i, pos[x["f"]]] += v[j]
                for k, wgt in x["w"].items():
                    raw[t_i, pos[k]] -= v[j] * wgt
        return (name, "F", syms, raw, H)

    specs.append(fof_book(lambda e: -rollz(e, 20), 5, "F1_fof_z20_H5"))
    specs.append(fof_book(lambda e: -rollz(e, 60), 5, "F2_fof_z60_H5"))
    specs.append(fof_book(lambda e: -diffk(e, 5), 5, "F3_fof_d5_H5"))
    specs.append(fof_book(lambda e: -rollz(e, 20), 1, "F4_fof_z20_H1"))

    # ---------------- STATIC PUBLISHED-TETHER CARRY (no fitted signal at all)
    # Every structure below has its sign fixed by a PUBLISHED number (a prospectus expense
    # ratio, or a prospectus daily-leverage mandate), not by anything measured on the data.
    def static_book(weights: dict, name, fam, first_ok=None):
        syms = sorted(weights)
        raw = np.zeros((n, len(syms)))
        pos = {s: i for i, s in enumerate(syms)}
        live = np.ones(n, dtype=bool)
        for s in syms:
            live &= np.isfinite(px[s]["c"])
        for s, w in weights.items():
            raw[live, pos[s]] = w
        return (name, fam, syms, raw, 1)

    # C7/C8/C9 -- FEE-DIFFERENTIAL CARRY between wrappers on the SAME physical coin.
    # GBTC charges 1.50 %/yr and ETHE 2.50 %/yr; every competing wrapper charges <= 0.25 %.
    # Two funds holding the same coin must diverge at exactly the fee differential.  This is
    # the purest form of the programme's thesis: a third party (the sponsor) publishes the
    # tether, and the number is a contractual claim, not a statistic.
    lowfee_btc = [s for s in BTC_WRAPPERS if s != "GBTC" and s in px]
    lowfee_eth = [s for s in ETH_WRAPPERS if s != "ETHE" and s in px]
    if lowfee_btc and "GBTC" in px:
        w = {s: 0.5 / len(lowfee_btc) for s in lowfee_btc}
        w["GBTC"] = -0.5
        specs.append(static_book(w, "C7_feecarry_btc", "C"))
    if lowfee_eth and "ETHE" in px:
        w = {s: 0.5 / len(lowfee_eth) for s in lowfee_eth}
        w["ETHE"] = -0.5
        specs.append(static_book(w, "C8_feecarry_eth", "C"))
    if lowfee_btc and lowfee_eth and "GBTC" in px and "ETHE" in px:
        w = {}
        for s in lowfee_btc:
            w[s] = 0.25 / len(lowfee_btc)
        for s in lowfee_eth:
            w[s] = w.get(s, 0) + 0.25 / len(lowfee_eth)
        w["GBTC"] = -0.25
        w["ETHE"] = -0.25
        specs.append(static_book(w, "C9_feecarry_pooled", "C"))

    # C10 -- LONG-ONLY version of the wrapper cross-section: hold the three cheapest wrappers
    # in each coin group instead of the group.  No short leg, no borrow.
    def xs_longonly(groups, scorer, H, name, k=3):
        syms = sorted({s for g, _, _ in groups for s in g})
        raw = np.zeros((n, len(syms)))
        pos = {s: i for i, s in enumerate(syms)}
        for g, S, ok in groups:
            sc = scorer(S)
            for t in range(1, n):
                v = sc[t - 1]
                if not np.all(np.isfinite(v)) or not ok[t - 1]:
                    continue
                r = np.argsort(np.argsort(-v))   # rank 0 = highest score = cheapest
                for j, s in enumerate(g):
                    if r[j] < k:
                        raw[t, pos[s]] += 1.0 / k
                    raw[t, pos[s]] -= 1.0 / len(g)
        return (name, "C", syms, raw, H)

    specs.append(xs_longonly(G, sc_negz(20), 5, "C10_coin_cheapest3_vs_group_H5"))

    # L7 -- LEVERAGED-FUND DECAY CARRY.  Long m units of the base, short one unit of the
    # levered fund: the prospectus daily-leverage mandate makes this delta-neutral by
    # construction, and it collects the fund's expense ratio and financing spread.
    bulls = [x for x in levs if x["m"] > 0]
    if bulls:
        w = {}
        for x in bulls:
            w[x["lev"]] = w.get(x["lev"], 0) - 1.0 / len(bulls)
            w[x["base"]] = w.get(x["base"], 0) + x["m"] / len(bulls)
        specs.append(static_book(w, "L7_lev_decay_carry", "L"))

    # L8 -- BULL/BEAR SHORT-BOTH.  Short both sides of a levered pair at delta-neutral
    # weights: a mechanically zero-delta book that collects both funds' fees AND both
    # compounding drags.  Short-only, so the borrow/product-restriction wall applies in full.
    if parity:
        w = {}
        for p in parity:
            w[p["a"]] = w.get(p["a"], 0) - p["wa"] / len(parity)
            w[p["b"]] = w.get(p["b"], 0) - p["wb"] / len(parity)
        specs.append(static_book(w, "L8_bullbear_shortboth", "L"))

    # F5 -- fund-of-funds fee carry: long the published replication basket, short the wrapper.
    if fofs:
        w = {}
        for x in fofs:
            w[x["f"]] = w.get(x["f"], 0) - 1.0 / len(fofs)
            for k2, wgt in x["w"].items():
                w[k2] = w.get(k2, 0) + wgt / len(fofs)
        specs.append(static_book(w, "F5_fof_fee_carry", "F"))

    # ---------------- controls (NOT in N)
    ctrls = []
    raw = np.zeros((n, 1))
    raw[:, 0] = 1.0
    ctrls.append(("CTRL_LONG_SPY", "CTRL", ["SPY"], raw, 1))

    # SPY/IVV sibling pair -- a structure with a KNOWN real gross edge that is known to sit
    # inside the spread.  Harness sanity: gross should be positive.
    if "IVV" in px:
        ra, rb = logret(px["SPY"]["c"]), logret(px["IVV"]["c"])
        e = np.full(n, np.nan)
        acc = 0.0
        for i in range(n):
            if np.isfinite(ra[i]) and np.isfinite(rb[i]):
                acc += ra[i] - rb[i]
                e[i] = acc
        z = -rollz(e, 20)
        raw = np.zeros((n, 2))
        for t_i in range(1, n):
            if np.isfinite(z[t_i - 1]):
                raw[t_i, 0] = z[t_i - 1]
                raw[t_i, 1] = -z[t_i - 1]
        ctrls.append(("CTRL_SPY_IVV_z20_H5", "CTRL", ["SPY", "IVV"], raw, 5))

    return specs, [placebo_C, placebo_L], ctrls, {"tris": tris, "levs": levs, "fofs": fofs,
                                                  "btc": (btc_syms, btc_S),
                                                  "eth": (eth_syms, eth_S)}


# ------------------------------------------------------------------ financing / borrow ladder
BORROW_LADDER_BP_YR = {"b22g_etb_0.33pct": 33.0, "moderate_1pct": 100.0, "hard_3pct": 300.0}


def financing_ladder(stats: dict, i0: int, i1: int, cash_bp) -> dict:
    """A price-return backtest of a book with a non-zero net cash position is NOT a return.

    Longs must be funded and short proceeds earn a rebate.  This charges the book's mean net
    cash weight at the bill rate (BIL total return, free and published) and its short weight
    at three borrow rates.  Vol is unchanged by an almost-deterministic rate, so the adjusted
    Sharpe is the mean shift divided by the book's own daily SD.
    """
    r_cash = cash_bp(i0, i1)
    net_bp = stats["net_bp_day"]
    sd = float(np.std(stats["_net"], ddof=1))
    out = {"bil_bp_day": r_cash, "net_cash_weight": stats["net_cash_weight"],
           "short_weight": stats["short_weight"]}
    for label, bpyr in BORROW_LADDER_BP_YR.items():
        adj = net_bp - stats["net_cash_weight"] * r_cash \
            - abs(stats["short_weight"]) * bpyr / 252.0
        out[label] = {"excess_bp_day": float(adj),
                      "sharpe": float(adj / 1e4 / sd * np.sqrt(252)) if sd > 0 else 0.0}
    return out


# ------------------------------------------------------------------ published-fee tether test
# Sponsor-published annual expense ratios (prospectus headline rates, not the temporary
# launch waivers -- using the headline rate makes the PREDICTED differential a LOWER bound,
# because every waiver in this window made the real differential larger).
EXPENSE_RATIO = {
    "IBIT": 0.0025, "FBTC": 0.0025, "BITB": 0.0020, "ARKB": 0.0021, "BTCO": 0.0025,
    "HODL": 0.0025, "BRRR": 0.0025, "BTCW": 0.0025, "EZBC": 0.0019, "GBTC": 0.0150,
    "ETHA": 0.0025, "FETH": 0.0025, "ETHW": 0.0025, "ETHV": 0.0025, "QETH": 0.0025,
    "EZET": 0.0019, "ETHE": 0.0250,
}


def fee_tether_test(px, i_cd0, i_cd1, i_ch0, i_ch1, stage) -> dict:
    """Does the spread between two wrappers on the SAME coin drift at the published fee gap?

    This is the round's sharpest instance of the programme's thesis: the tether is not a
    fitted statistic, it is a contractual number in a prospectus.  If it does not show up
    here it will not show up anywhere.
    """
    out = {}
    for coin, dear, cheap in (("BTC", "GBTC", [s for s in BTC_WRAPPERS if s != "GBTC"]),
                              ("ETH", "ETHE", [s for s in ETH_WRAPPERS if s != "ETHE"])):
        cheap = [s for s in cheap if s in px and s in EXPENSE_RATIO]
        if dear not in px or not cheap:
            continue
        rd = logret(px[dear]["c"])
        R = np.column_stack([logret(px[s]["c"]) for s in cheap])
        m = np.isfinite(rd) & np.isfinite(R).all(axis=1)
        basket = np.where(m, np.nanmean(R, axis=1), np.nan)
        spread = np.where(m, basket - rd, np.nan)   # cheap minus dear
        pred = EXPENSE_RATIO[dear] - float(np.mean([EXPENSE_RATIO[s] for s in cheap]))

        def seg(i0, i1):
            x = spread[i0:i1]
            x = x[np.isfinite(x)]
            if len(x) < 30:
                return None
            ann = float(x.mean() * 252)
            se = float(x.std(ddof=1) / np.sqrt(len(x)) * 252)
            return {"n_days": len(x), "realised_drift_pct_yr": ann * 100,
                    "se_pct_yr": se * 100, "t_vs_zero": ann / se if se > 0 else 0.0,
                    "t_vs_published": (ann - pred) / se if se > 0 else 0.0,
                    "ann_vol_pct": float(x.std(ddof=1) * np.sqrt(252) * 100),
                    "implied_sharpe": float(ann / (x.std(ddof=1) * np.sqrt(252)))}

        out[coin] = {"dear": dear, "cheap_basket": cheap,
                     "published_fee_gap_pct_yr": pred * 100,
                     "design": seg(i_cd0, i_cd1),
                     "heldout": seg(i_ch0, i_ch1) if stage == "reveal" else "SEALED"}
    return out


# ------------------------------------------------------------------ rho1 gate
def rho1_of_spread_change(series_list) -> dict:
    vals = []
    for e in series_list:
        d = np.diff(e[np.isfinite(e)])
        if len(d) < 100:
            continue
        a, b = d[:-1], d[1:]
        if a.std() == 0 or b.std() == 0:
            continue
        vals.append(float(np.corrcoef(a, b)[0, 1]))
    if not vals:
        return {"n": 0}
    v = np.array(vals)
    return {"n": len(v), "median": float(np.median(v)), "mean": float(v.mean()),
            "p10": float(np.percentile(v, 10)), "p90": float(np.percentile(v, 90))}


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["design", "reveal"], required=True)
    args = ap.parse_args()

    panel = build_panel()
    master = panel["dates"]
    px = panel["px"]

    i_d0, i_d1 = date_index(master, D0), date_index(master, D1)
    i_h0, i_h1 = date_index(master, H0), date_index(master, H1)
    i_cd0, i_cd1 = date_index(master, CD0), date_index(master, CD1)
    i_ch0, i_ch1 = date_index(master, CH0), date_index(master, CH1)

    hs = {}
    for s in px:
        v = corwin_schultz_halfspread(px[s]["h"], px[s]["l"], max(0, i_d0), i_h1)
        hs[s] = max(SPREAD_FLOOR_BP, v) if np.isfinite(v) else 25.0

    # cash rate: BIL total return, a free published proxy for the overnight bill rate.
    bil = logret(px["BIL"]["c"])
    bil = np.where(np.isfinite(bil), bil, 0.0)

    def cash_bp(i0, i1):
        return float(bil[i0:i1].mean() * 1e4)

    specs, placebos, ctrls, prims = build_all(panel)

    rho = {
        "H_triangle_residual": rho1_of_spread_change([t["e"] for t in prims["tris"]]),
        "L_levered_residual": rho1_of_spread_change([x["cum"] for x in prims["levs"]]),
        "F_fof_residual": rho1_of_spread_change([x["e"] for x in prims["fofs"]]),
        "C_btc_wrapper_residual": rho1_of_spread_change(
            [prims["btc"][1][:, j] for j in range(prims["btc"][1].shape[1])]),
        "C_eth_wrapper_residual": rho1_of_spread_change(
            [prims["eth"][1][:, j] for j in range(prims["eth"][1].shape[1])]),
    }

    # ---- stale-open diagnostic.  If a thin fund's OPENING print is stale, an open-to-open
    # return series lags the close-to-close one and a close-formed signal can "predict" a
    # return it has already seen.  Measured, not assumed.
    stale = {}
    for s in sorted(px):
        O, C = px[s]["o"], px[s]["c"]
        m = np.isfinite(O) & np.isfinite(C)
        idx = np.where(m)[0]
        idx = idx[(idx >= i_d0) & (idx < i_h1)]
        if len(idx) < 200:
            continue
        eq = float(np.mean(np.isclose(O[idx[1:]], C[idx[:-1]], rtol=1e-9)))
        roo = O[idx[1:]] / O[idx[:-1]] - 1
        rcc = C[idx[:-1]] / C[idx[:-2].tolist() + [idx[-2]]][:len(roo)] - 1
        rcc = np.diff(np.log(C[idx]))
        roo = np.diff(np.log(O[idx]))
        L = min(len(rcc), len(roo)) - 1
        c = float(np.corrcoef(roo[1:L + 1], rcc[:L])[0, 1]) if L > 50 else float("nan")
        stale[s] = {"frac_open_eq_prev_close": eq, "corr_openret_t_vs_closeret_tm1": c}

    results = []
    pnl_design = {}
    for name, fam, syms, raw, H in specs + placebos + ctrls:
        W = normalise_and_stagger(raw, H)
        if fam == "C":
            d = evaluate(W, syms, px, hs, i_cd0, i_cd1)
            dsh = evaluate(W, syms, px, hs, i_cd0, i_cd1, shock=SPREAD_SHOCK)
        elif fam == "PLACEBO" and name.endswith("C_idperm"):
            d = evaluate(W, syms, px, hs, i_cd0, i_cd1)
            dsh = evaluate(W, syms, px, hs, i_cd0, i_cd1, shock=SPREAD_SHOCK)
        else:
            d = evaluate(W, syms, px, hs, i_d0, i_d1)
            dsh = evaluate(W, syms, px, hs, i_d0, i_d1, shock=SPREAD_SHOCK)
        pnl_design[name] = d["_gross"]
        j0, j1 = (i_cd0, i_cd1) if (fam == "C" or name.endswith("C_idperm")) else (i_d0, i_d1)
        dlag = evaluate(W, syms, px, hs, j0, j1, mode="close_lag")
        dcon = evaluate(W, syms, px, hs, j0, j1, mode="close_same")
        rec = {"formula": name, "family": fam, "H": H, "n_legs": len(syms),
               "design": {k: v for k, v in d.items() if not k.startswith("_")},
               "design_shock_net_sharpe": dsh["net_sharpe"],
               "design_closelag_gross_sharpe": dlag["gross_sharpe"],
               "design_contaminated_gross_sharpe": dcon["gross_sharpe"],
               "design_financing_ladder": financing_ladder(d, j0, j1, cash_bp)}
        if args.stage == "reveal":
            if fam == "C" or name.endswith("C_idperm"):
                h = evaluate(W, syms, px, hs, i_ch0, i_ch1)
                hsk = evaluate(W, syms, px, hs, i_ch0, i_ch1, shock=SPREAD_SHOCK)
            else:
                h = evaluate(W, syms, px, hs, i_h0, i_h1)
                hsk = evaluate(W, syms, px, hs, i_h0, i_h1, shock=SPREAD_SHOCK)
            k0, k1 = (i_ch0, i_ch1) if (fam == "C" or name.endswith("C_idperm")) else (i_h0, i_h1)
            rec["heldout"] = {k: v for k, v in h.items() if not k.startswith("_")}
            rec["heldout_shock_net_sharpe"] = hsk["net_sharpe"]
            rec["heldout_closelag_gross_sharpe"] = evaluate(
                W, syms, px, hs, k0, k1, mode="close_lag")["gross_sharpe"]
            rec["heldout_financing_ladder"] = financing_ladder(h, k0, k1, cash_bp)
        else:
            rec["heldout"] = "SEALED"
            rec["heldout_shock_net_sharpe"] = "SEALED"
        results.append(rec)

    # ---- size-matched placebo null: sign-flip block bootstrap of the max |Sharpe| over the
    # N scored formulas, blocks of 10 days, the SAME block signs across formulas so their
    # correlation survives into the null.
    scored = [r["formula"] for r in results if r["family"] in ("C", "H", "L", "F")]
    N = len(scored)
    long_names = [f for f in scored if not f.startswith("C")]
    coin_names = [f for f in scored if f.startswith("C")]

    def boot_max(names, reps=2000, block=10, seed=7):
        if not names:
            return {}
        M = np.column_stack([pnl_design[f] for f in names])
        T = M.shape[0]
        rg = np.random.default_rng(seed)
        nb = int(np.ceil(T / block))
        mx = np.empty(reps)
        Md = M - M.mean(axis=0)
        for r in range(reps):
            sgn = rg.choice([-1.0, 1.0], size=nb)
            s = np.repeat(sgn, block)[:T]
            X = Md * s[:, None]
            sd = X.std(axis=0, ddof=1)
            sh = np.where(sd > 0, X.mean(axis=0) / np.where(sd > 0, sd, 1) * np.sqrt(252), 0.0)
            mx[r] = np.abs(sh).max()
        one = np.abs(Md * np.repeat(rg.choice([-1.0, 1.0], size=nb), block)[:T][:, None])
        return {"n_formulas": len(names), "E_max_abs_sharpe": float(mx.mean()),
                "p95": float(np.percentile(mx, 95)), "p99": float(np.percentile(mx, 99)),
                "single_formula_null_sd": float(np.std([
                    np.abs(Md[:, j]).mean() for j in range(Md.shape[1])]) * 0 + 1.0 /
                    np.sqrt(T / 252.0))}

    nulls = {"long_history_families": boot_max(long_names),
             "coin_family": boot_max(coin_names, seed=11)}
    yrs_long = (i_d1 - i_d0) / 252.0
    yrs_coin = (i_cd1 - i_cd0) / 252.0
    nulls["analytic"] = {
        "N_scored": N,
        "sqrt_2lnN": float(np.sqrt(2 * np.log(N))),
        "sqrt_2ln2N": float(np.sqrt(2 * np.log(2 * N))),
        "SE_sharpe_long_window": float(1 / np.sqrt(yrs_long)),
        "SE_sharpe_coin_window": float(1 / np.sqrt(yrs_coin)),
        "bar_sharpe_long": float(np.sqrt(2 * np.log(2 * N)) / np.sqrt(yrs_long)),
        "bar_sharpe_coin": float(np.sqrt(2 * np.log(2 * N)) / np.sqrt(yrs_coin)),
    }

    blob = {
        "round": "INVENT_0823_exotic_tether",
        "stage": args.stage,
        "windows": {"design": [D0, D1], "heldout": [H0, H1],
                    "coin_design": [CD0, CD1], "coin_heldout": [CH0, CH1]},
        "n_scored_formulas": N,
        "cost_model": {
            "half_spread_bp_per_symbol": {k: round(v, 2) for k, v in sorted(hs.items())},
            "provenance": "Corwin-Schultz (2012) effective spread from the same daily "
                          "high/low bars the backtest trades; median of daily estimates, "
                          "negative estimates zeroed, floored at 1.0 bp half-spread",
            "open_premium_multiplier": OPEN_PREMIUM,
            "shock_multiplier": SPREAD_SHOCK,
            "sec_fee_bp_on_sales": SEC_FEE_BP,
        },
        "rho1_bounce_gate": rho,
        "stale_open_diagnostic": stale,
        "published_fee_tether_test": fee_tether_test(px, i_cd0, i_cd1, i_ch0, i_ch1,
                                                     args.stage),
        "nulls": nulls,
        "results": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    fn = OUT / ("INVENT_0823_exotic_DESIGN.json" if args.stage == "design"
                else "INVENT_0823_exotic.json")
    fn.write_text(json.dumps(blob, indent=1))
    print(f"wrote {fn}")

    print("\nrho1 gate:")
    for k, v in rho.items():
        print(" ", k, v)
    print("\nnulls:", json.dumps(nulls, indent=1))
    print(f"\n{'formula':32s} {'fam':4s} {'Dgross':>7s} {'Dnet':>7s} {'Dshk':>7s} "
          f"{'turn':>6s} {'BE bp':>7s}")
    for r in sorted(results, key=lambda x: -x["design"]["gross_sharpe"]):
        d = r["design"]
        print(f"{r['formula']:32s} {r['family']:4s} {d['gross_sharpe']:7.2f} "
              f"{d['net_sharpe']:7.2f} {r['design_shock_net_sharpe']:7.2f} "
              f"{d['turnover_day']:6.3f} {d['breakeven_bp']:7.2f}")


if __name__ == "__main__":
    main()
