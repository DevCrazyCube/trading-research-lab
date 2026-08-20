#!/usr/bin/env python3
"""Signals + the two book constructions. All P&L from US-listed adjusted closes only."""
import math
import numpy as np

SEC_FEE = 0.278e-4        # per sale, T7/M0 convention
BORROW_ETB = 0.0033       # B22G easy-to-borrow general collateral, annual
BORROW_HTB = 0.1028       # B22G hard-to-borrow, annual


def borrow_rate(sym, bstat, etb_rate=BORROW_ETB, htb_rate=BORROW_HTB):
    """Three states, not two. A LIVE /v2/assets snapshot cannot say what a DELISTED ticker's
    borrow was in 2018, and reading 'inactive' as 'not shortable' silently deletes exactly
    the pairs a cross-listing study exists to test (CUK, BBL, RDS.A/B, AMOV are all inactive
    today). So: 'etb' -> general collateral; 'unknown' -> charged the HARD-to-borrow rate,
    because absence is refusal and refusal is priced expensively, never at zero; 'htb' ->
    the name is live and flagged not-shortable, which is a fact, so it is excluded."""
    st = bstat.get(sym, "unknown")
    if st == "etb":
        return etb_rate
    if st == "unknown":
        return htb_rate
    return None          # cannot be shorted
BREAK = 0.15


def seg_starts(s):
    """Index of the first observation of the current no-corporate-action segment."""
    n = len(s)
    br = np.zeros(n, dtype=bool)
    br[1:] = np.abs(np.diff(s)) > BREAK
    idx = np.arange(n)
    return np.maximum.accumulate(np.where(br, idx, 0))


def signal(s, mode, L=60, L2=250, hl=30):
    """Returns (sig, valid). sig[t] uses only s[0..t]."""
    n = len(s)
    ss = seg_starts(s)
    avail = np.arange(n) - ss + 1
    if mode == "d1":
        sig = np.zeros(n); sig[1:] = np.diff(s)
        return sig, avail >= 2
    if mode == "ewma":
        m = np.zeros(n); v = np.zeros(n); sig = np.zeros(n)
        lam = 0.5 ** (1.0 / hl)
        mu = s[0]; var = 0.0
        for t in range(n):
            if t > 0 and ss[t] != ss[t - 1]:
                mu, var = s[t], 0.0
            mu = lam * mu + (1 - lam) * s[t]
            var = lam * var + (1 - lam) * (s[t] - mu) ** 2
            sd = math.sqrt(var)
            sig[t] = (s[t] - mu) / sd if sd > 1e-12 else 0.0
        return sig, avail >= L
    c1 = np.concatenate([[0.0], np.cumsum(s)])
    c2 = np.concatenate([[0.0], np.cumsum(s * s)])

    def roll(w):
        a = np.arange(n)
        lo = np.maximum(a - w + 1, 0)
        m = (c1[a + 1] - c1[lo]) / w
        v = (c2[a + 1] - c2[lo]) / w - m * m
        return m, np.sqrt(np.maximum(v, 0.0))
    m1, sd1 = roll(L)
    if mode == "z":
        sd = np.where(sd1 > 1e-12, sd1, np.nan)
        return (s - m1) / sd, (avail >= L) & (sd1 > 1e-12)
    if mode == "dev":
        return s - m1, avail >= L
    if mode == "twoscale":
        m2, _ = roll(L2)
        sd = np.where(sd1 > 1e-12, sd1, np.nan)
        return (s - m2) / sd, (avail >= L2) & (sd1 > 1e-12)
    raise ValueError(mode)


def _wts(g, weighting):
    if weighting == "invvol":
        w = np.array([1.0 / max(c[5], 1e-4) if np.isfinite(c[5]) else 0.0 for c in g])
        if w.sum() <= 0:
            w = np.ones(len(g))
    else:
        w = np.ones(len(g))
    return w / w.sum()


def _stats(net, h, label):
    net = np.asarray(net, dtype=float)
    n = len(net)
    if n < 5:
        return {"label": label, "n": n, "net_bp": None, "sharpe": None, "t": None}
    m, sd = float(net.mean()), float(net.std(ddof=1))
    t = m / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    sharpe = (m / sd) * math.sqrt(252.0 / h) if sd > 0 else float("nan")
    return {"label": label, "n": n, "net_bp": round(m * 1e4, 2),
            "sd_bp": round(sd * 1e4, 1), "t": round(t, 2),
            "sharpe": round(sharpe, 3), "hit": round(float((net > 0).mean()), 3),
            "years": round(n * h / 252.0, 2)}


def xsec(names, syms, dates, hs, bstat, *, mode="z", L=60, L2=250, hl=30, frac=0.1, h=5,
         zgate=None, region_neutral=False, weighting="equal", entry_lag=0,
         min_dv=1e6, min_px=2.0, hs_mult=1.0, borrow=BORROW_ETB, htb=BORROW_HTB,
         etb_only=True, placebo=None, seed=7, label=""):
    """Cross-sectional dollar-neutral book of US ADR lines ranked on the ADR-vs-home spread.
    Non-overlapping h-day periods, so the t-stat needs no autocorrelation correction."""
    dix = {d: i for i, d in enumerate(dates)}
    prep = {}
    for u in syms:
        nm = names.get(u)
        if nm is None or hs.get(u) is None:
            continue
        sig, val = signal(nm["s"], mode, L, L2, hl)
        r = np.zeros(len(nm["s"])); r[1:] = np.diff(np.log(nm["px_adj"]))
        vol = np.full(len(r), np.nan)
        if len(r) > 21:
            c = np.concatenate([[0.0], np.cumsum(r * r)])
            a = np.arange(len(r))
            lo = np.maximum(a - 20, 0)
            vol = np.sqrt(np.maximum((c[a + 1] - c[lo]) / 21.0, 1e-12))
        prep[u] = {"idx": {d: i for i, d in enumerate(nm["d"])}, "sig": sig, "val": val,
                   "px": nm["px_adj"], "dv": nm["dv"], "px_raw": nm["px_raw"],
                   "reg": nm["region"], "vol": vol, "hs": hs[u] * hs_mult}
    if not prep:
        return _stats([], h, label), []
    nets, detail = [], []
    wprev = {}
    step = h
    for k in range(0, len(dates) - h - entry_lag - 1, step):
        d = dates[k]
        de = dates[k + entry_lag]
        dx = dates[k + entry_lag + h]
        cands = []
        for u, p in prep.items():
            i = p["idx"].get(d); ie = p["idx"].get(de); ix = p["idx"].get(dx)
            if i is None or ie is None or ix is None or not p["val"][i]:
                continue
            if p["dv"][i] < min_dv or p["px_raw"][i] < min_px:
                continue
            sg = p["sig"][i]
            if not np.isfinite(sg):
                continue
            if zgate is not None and abs(sg) < zgate:
                continue
            cands.append((u, sg, p["px"][ix] / p["px"][ie] - 1.0, p["reg"], p["hs"],
                          p["vol"][ie]))
        if len(cands) < 6:
            continue
        if placebo == "flip":
            cands = [(c[0], -c[1]) + c[2:] for c in cands]
        elif placebo == "shuffle":
            # break the name<->signal correspondence, keep the cross-sectional distribution.
            # A book that still earns under this is earning from the SELECTION MACHINERY,
            # not from the cross-listing spread.
            rng = np.random.default_rng(seed + k)
            perm = rng.permutation(len(cands))
            cands = [(cands[i][0], cands[j][1]) + cands[i][2:]
                     for i, j in enumerate(perm)]
        groups = {}
        for c in cands:
            groups.setdefault(c[3] if region_neutral else "_", []).append(c)
        Ls, Ss = [], []
        for g in groups.values():
            if len(g) < 4:
                continue
            g.sort(key=lambda x: x[1])
            m = max(1, int(round(len(g) * frac)))
            lo = g[:m]
            hi = [c for c in reversed(g)
                  if (not etb_only) or borrow_rate(c[0], bstat, borrow, htb) is not None][:m]
            if not lo or not hi:
                continue
            Ls.append(lo); Ss.append(hi)
        if not Ls:
            continue

        def wmean(groups_):
            tot_r = tot_hs = 0.0
            for g in groups_:
                w = _wts(g, weighting)
                tot_r += float(np.dot(w, [c[2] for c in g]))
                tot_hs += float(np.dot(w, [c[4] for c in g]))
            return tot_r / len(groups_), tot_hs / len(groups_)
        rl, _ = wmean(Ls)
        rs, _ = wmean(Ss)
        gross = rl - rs

        # ---- TURNOVER-AWARE cost. Charging a full round trip every period assumes the
        # book is rebuilt from scratch each time; for a persistent signal at h=1 that
        # overstates the bill by several times. Weights: +1/nL on each long, -1/nS on each
        # short, so gross exposure is 2.0 and a COMPLETE rebuild is sum|dw| = 4.0 -- which
        # reproduces the old 2*(hs_L+hs_S) exactly. Anything less is a real saving.
        wnew = {}
        for g in Ls:
            wts = _wts(g, weighting)
            for c, w in zip(g, wts):
                wnew[c[0]] = wnew.get(c[0], 0.0) + w / len(Ls)
        for g in Ss:
            wts = _wts(g, weighting)
            for c, w in zip(g, wts):
                wnew[c[0]] = wnew.get(c[0], 0.0) - w / len(Ss)
        hsmap = {c[0]: c[4] for g in Ls + Ss for c in g}
        turn = 0.0
        spread_cost = 0.0
        for sym in set(wnew) | set(wprev):
            dw = abs(wnew.get(sym, 0.0) - wprev.get(sym, 0.0))
            if dw <= 0:
                continue
            turn += dw
            spread_cost += dw * hsmap.get(sym, prep[sym]["hs"] if sym in prep else 0.0)
        wprev = wnew
        brates = [borrow_rate(c[0], bstat, borrow, htb) for g in Ss for c in g]
        brates = [b for b in brates if b is not None] or [htb]
        cost = spread_cost + SEC_FEE * 0.5 * turn + float(np.mean(brates)) * (h / 252.0)
        nets.append(gross - cost)
        detail.append({"d": d, "gross": gross, "cost": cost, "turnover": turn,
                       "nL": sum(len(g) for g in Ls), "nS": sum(len(g) for g in Ss)})
    st = _stats(nets, h, label)
    if detail:
        # The ZERO-COST counterfactual. If a formula cannot clear the noise bar even when
        # every crossing, fee and borrow charge is set to zero, then no cost model, no
        # universe screen and no execution improvement can rescue it -- the signal itself
        # is absent. This is the number the verdict rests on.
        g = _stats([x["gross"] for x in detail], h, label + " GROSS")
        st["gross_t"] = g.get("t")
        st["gross_sharpe"] = g.get("sharpe")
        st["gross_bp"] = round(float(np.mean([x["gross"] for x in detail])) * 1e4, 2)
        st["cost_bp"] = round(float(np.mean([x["cost"] for x in detail])) * 1e4, 2)
        st["mean_names_side"] = round(float(np.mean([x["nL"] for x in detail])), 1)
        st["mean_turnover"] = round(float(np.mean([x["turnover"] for x in detail])), 2)
    return st, detail


def pair_rv(us_raw, us_adj, pairs, lo, hi, hs, bstat, *, L=250, K=2.0, EXIT=0.5, MAXHOLD=20,
            min_dv=3e5, min_px=2.0, hs_mult=1.0, borrow=BORROW_ETB, htb=BORROW_HTB,
            etb_only=True, label=""):
    """T28-shaped two-timescale z-fade on pairs where BOTH legs are US-listed."""
    def by(sym, book):
        return {b["t"][:10]: b for b in book.get(sym, [])}
    trades = []
    per_pair = {}
    for a, b, why in pairs:
        if hs.get(a) is None or hs.get(b) is None:
            continue
        # either leg can end up the SHORT leg, so both must be shortable at all
        ba = borrow_rate(a, bstat, borrow, htb)
        bb = borrow_rate(b, bstat, borrow, htb)
        if etb_only and (ba is None or bb is None):
            continue
        bmax = max(ba or htb, bb or htb)
        ra, rb, aa, ab = by(a, us_raw), by(b, us_raw), by(a, us_adj), by(b, us_adj)
        days = sorted(set(ra) & set(rb) & set(aa) & set(ab))
        days = [d for d in days if lo <= d <= hi]
        rows = []
        for d in days:
            if ra[d]["c"] <= 0 or rb[d]["c"] <= 0:
                continue
            rows.append({"d": d, "s": math.log(ra[d]["c"] / rb[d]["c"]),
                         "pa": aa[d]["c"], "pb": ab[d]["c"],
                         "dv": min(ra[d]["c"] * ra[d]["v"], rb[d]["c"] * rb[d]["v"]),
                         "px": min(ra[d]["c"], rb[d]["c"])})
        if len(rows) < L + 30:
            continue
        hist, pos, tp = [], None, []
        for i, r in enumerate(rows):
            if i > 0 and abs(r["s"] - rows[i - 1]["s"]) > BREAK:
                hist, pos = [], None
            z = None
            if len(hist) >= L:
                w = np.array(hist[-L:]); sd = w.std()
                z = (r["s"] - w.mean()) / sd if sd > 0 else 0.0
            if pos:
                held = i - pos["i"]
                if (z is not None and abs(z) <= EXIT) or held >= MAXHOLD or i == len(rows) - 1:
                    g = pos["sgn"] * ((r["pa"] / pos["pa"] - 1) - (r["pb"] / pos["pb"] - 1))
                    c = 2 * (hs[a] + hs[b]) * hs_mult + 2 * SEC_FEE + bmax * (held / 252.0)
                    tp.append(g - c)
                    pos = None
            if not pos and z is not None and abs(z) >= K and r["dv"] >= min_dv \
                    and r["px"] >= min_px:
                pos = {"i": i, "pa": r["pa"], "pb": r["pb"], "sgn": -1 if z > 0 else 1}
            hist.append(r["s"])
        if tp:
            per_pair[f"{a}/{b}"] = {"n": len(tp), "net_bp": round(float(np.mean(tp)) * 1e4, 1)}
            trades.extend(tp)
    import datetime as dt
    years = max((dt.date.fromisoformat(hi) - dt.date.fromisoformat(lo)).days / 365.25, 0.1)
    st = _stats(trades, 1, label)
    if st.get("n", 0) >= 5:
        tr = np.asarray(trades, float)
        per_yr = len(tr) / years
        st["trades_per_yr"] = round(per_yr, 1)
        st["sharpe"] = round(float(tr.mean() / tr.std(ddof=1)) * math.sqrt(per_yr), 3)
        st["years"] = round(years, 2)
    st["pairs"] = len(per_pair)
    st["per_pair"] = per_pair
    return st, trades
