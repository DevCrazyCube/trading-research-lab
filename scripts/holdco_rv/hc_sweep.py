#!/usr/bin/env python3
"""Holdco / corporate-structure RV: one parameterised sweep over many structurally
different formulas.  Design window only unless --holdout is passed.

Signal on RAW closes (levels are point-in-time).  P&L on ADJUSTED closes (total return).
Fills at the NEXT session's close after the signal close (no same-bar fill).
Costs: 2 crossings per leg x Corwin-Schultz half-spread measured per symbol per window,
+ SEC s31 0.278bp on each sale, + borrow on the short leg for the holding period.
"""
from __future__ import annotations
import json, math, pathlib, statistics as st, sys, random, itertools, argparse

sys.path.insert(0, "/home/anont/meme")
from scripts.holdco_rv.hc_universe import (GROUP_P, GROUP_H, GROUP_S, GROUP_M,
                                           VALID, EXCLUDE)
import datetime as _dt

CACHE = pathlib.Path("/home/anont/meme/research/data/holdco_cache")
RAW = json.load(open(CACHE / "bars_raw.json"))
ADJ = json.load(open(CACHE / "bars_all.json"))

DESIGN = ("2016-01-04", "2021-12-31")
HELDOUT = ("2022-01-03", "2026-08-18")

SEC_FEE_BP = 0.278            # per sale, T7/M0 convention
BORROW_ETB = 0.0033           # B22G etb_general_collateral 0.33%/yr
BORROW_HTB = 0.1028           # B22G htb_median 10.28%/yr
BREAK_JUMP = 0.15             # |dlog(ratio)| above this = corporate action, re-anchor

_SER: dict = {}


HYGIENE = {"excluded": sorted(EXCLUDE), "validity_clipped": {}, "gap_segments": {},
           "stale_days_dropped": {}}


def series(sym, book, tag):
    """Cleaned per-symbol date->bar map.

    Alpaca serves a series BY TICKER and stitches successive occupants of the same ticker,
    sometimes carrying the previous occupant's last price forward flat.  Three guards:
      1. EXCLUDE / VALID windows established by price-level verification (see universe file);
      2. gap segmentation -- a >20 calendar-day hole means a different listing, keep the
         longest contiguous segment;
      3. stale-price drop -- >=5 consecutive sessions at an identical raw close is a
         carried-forward price, not a market.
    """
    key = (sym, tag)
    if key in _SER:
        return _SER[key]
    if sym in EXCLUDE:
        _SER[key] = {}
        return _SER[key]
    bars = sorted(book.get(sym, []), key=lambda b: b["t"])
    if sym in VALID:
        lo, hi = VALID[sym]
        n0 = len(bars)
        bars = [b for b in bars if lo <= b["t"][:10] <= hi]
        HYGIENE["validity_clipped"][sym] = [n0, len(bars)]
    # gap segmentation
    segs, cur = [], []
    for b in bars:
        d = _dt.date.fromisoformat(b["t"][:10])
        if cur and (d - _dt.date.fromisoformat(cur[-1]["t"][:10])).days > 20:
            segs.append(cur)
            cur = []
        cur.append(b)
    if cur:
        segs.append(cur)
    if len(segs) > 1:
        HYGIENE["gap_segments"][sym] = [len(s) for s in segs]
        segs.sort(key=len, reverse=True)
    bars = segs[0] if segs else []
    # stale-price runs (uses the RAW book for the test regardless of tag)
    rawb = sorted(RAW.get(sym, []), key=lambda b: b["t"])
    stale = set()
    run, prev = 0, None
    for b in rawb:
        if prev is not None and b["c"] == prev:
            run += 1
        else:
            run = 0
        if run >= 4:                       # 5th+ identical close
            stale.add(b["t"][:10])
        prev = b["c"]
    if stale:
        HYGIENE["stale_days_dropped"][sym] = len(stale)
    _SER[key] = {b["t"][:10]: b for b in bars if b["t"][:10] not in stale}
    return _SER[key]


def corwin_schultz(bars, lo, hi):
    ds = sorted(d for d in bars if lo <= d <= hi)
    vals, k = [], 3 - 2 * math.sqrt(2)
    for i in range(len(ds) - 1):
        a, b = bars[ds[i]], bars[ds[i + 1]]
        if min(a["l"], b["l"]) <= 0:
            continue
        beta = math.log(a["h"] / a["l"]) ** 2 + math.log(b["h"] / b["l"]) ** 2
        gamma = math.log(max(a["h"], b["h"]) / min(a["l"], b["l"])) ** 2
        alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
        s = 2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha))
        vals.append(max(s, 0.0))
    return st.median(vals) if vals else None


_HS: dict = {}


def half_spread(sym, lo, hi):
    key = (sym, lo, hi)
    if key not in _HS:
        cs = corwin_schultz(series(sym, RAW, "r"), lo, hi)
        _HS[key] = None if cs is None else cs / 2.0
    return _HS[key]


# ------------------------------------------------------------------ panel


def panel(a, b, lo, hi, warmup=300):
    """Aligned daily rows for a pair.  `warmup` extra sessions BEFORE lo are kept so a
    250-day z-window is available on the first tradable day (they are never traded)."""
    ra, rb = series(a, RAW, "r"), series(b, RAW, "r")
    aa, ab = series(a, ADJ, "a"), series(b, ADJ, "a")
    days = sorted(set(ra) & set(rb) & set(aa) & set(ab))
    if not days:
        return []
    hi_idx = [i for i, d in enumerate(days) if d <= hi]
    if not hi_idx:
        return []
    end = hi_idx[-1]
    lo_idx = [i for i, d in enumerate(days) if d >= lo]
    if not lo_idx:
        return []
    start = max(0, lo_idx[0] - warmup)
    rows = []
    for i in range(start, end + 1):
        d = days[i]
        if ra[d]["c"] <= 0 or rb[d]["c"] <= 0 or aa[d]["c"] <= 0 or ab[d]["c"] <= 0:
            continue
        rows.append({
            "d": d, "tradable": d >= lo,
            "lr": math.log(ra[d]["c"] / rb[d]["c"]),
            "pa": aa[d]["c"], "pb": ab[d]["c"],
            "px_a": ra[d]["c"], "px_b": rb[d]["c"],
            "dv": min(ra[d]["c"] * ra[d]["v"], rb[d]["c"] * rb[d]["v"]),
        })
    # log return series for beta/return-space spreads
    for i, r in enumerate(rows):
        if i == 0:
            r["ra"] = r["rb"] = 0.0
        else:
            r["ra"] = math.log(r["pa"] / rows[i - 1]["pa"])
            r["rb"] = math.log(r["pb"] / rows[i - 1]["pb"])
    # rolling 125-session spread vol + its expanding median (both causal), for the
    # lowvol/highvol conditioners.  Precomputed once so the sweep stays O(n).
    dl = [0.0] + [rows[i]["lr"] - rows[i - 1]["lr"] for i in range(1, len(rows))]
    W = 125
    s1 = s2 = 0.0
    vols = [None] * len(rows)
    for i in range(1, len(rows)):
        s1 += dl[i]
        s2 += dl[i] * dl[i]
        if i > W:
            s1 -= dl[i - W]
            s2 -= dl[i - W] * dl[i - W]
        if i >= W:
            m = s1 / W
            vols[i] = math.sqrt(max(s2 / W - m * m, 0.0))
    # rolling 125-session return-beta of A on B, for the beta-neutral hedge
    sab = sbb = 0.0
    ra_, rb_ = [r["ra"] for r in rows], [r["rb"] for r in rows]
    for i in range(len(rows)):
        sab += ra_[i] * rb_[i]
        sbb += rb_[i] * rb_[i]
        if i >= W:
            sab -= ra_[i - W] * rb_[i - W]
            sbb -= rb_[i - W] * rb_[i - W]
        rows[i]["rbeta"] = (max(0.2, min(3.0, sab / sbb))
                            if i >= W and sbb > 0 else None)
    seen = []
    for i, v in enumerate(vols):
        if v is None:
            rows[i]["volreg"] = None
            continue
        rows[i]["volreg"] = None if len(seen) < 20 else (
            "low" if v <= st.median(seen) else "high")
        seen.append(v)
        if len(seen) > 1500:
            seen = seen[-1500:]
    return rows


# ------------------------------------------------------------------ formulas
# A formula is a dict:
#   spread : "z" | "ret" | "beta" | "level"
#   L      : lookback for mean/vol/regression
#   K      : entry threshold (z units, or fractional level for "level")
#   E      : exit threshold
#   MH     : max hold (sessions)
#   hedge  : "dollar" | "beta"
#   cond   : None | "lowvol" | "highvol" | "bigdv"

def formula_grid():
    fs = []
    for sp, L, K in itertools.product(("z", "ret", "beta"), (60, 125, 250), (1.5, 2.0, 2.5)):
        fs.append({"spread": sp, "L": L, "K": K, "E": 0.5, "MH": 20,
                   "hedge": "dollar", "cond": None})
    base = {"spread": "z", "L": 125, "K": 2.0, "E": 0.5, "MH": 20,
            "hedge": "dollar", "cond": None}
    fs.append({**base, "E": 0.0})
    fs.append({**base, "MH": 60})
    fs.append({**base, "MH": 5})
    fs.append({**base, "hedge": "beta"})
    fs.append({**base, "cond": "lowvol"})
    fs.append({**base, "cond": "highvol"})
    fs.append({**base, "cond": "bigdv"})
    for i, f in enumerate(fs):
        f["id"] = i
        f["name"] = (f"{f['spread']}/L{f['L']}/K{f['K']}/E{f['E']}/MH{f['MH']}"
                     f"/{f['hedge']}" + (f"/{f['cond']}" if f["cond"] else ""))
    return fs


def level_grid():
    """Level-anchored formulas: only meaningful where a contractual ratio exists."""
    fs = []
    for K, E, MH in itertools.product((0.02, 0.05, 0.10), (0.0, 0.01), (20, 60)):
        fs.append({"spread": "level", "L": 0, "K": K, "E": E, "MH": MH,
                   "hedge": "dollar", "cond": None})
    for i, f in enumerate(fs):
        f["id"] = 1000 + i
        f["name"] = f"level/K{f['K']:.0%}/E{f['E']:.0%}/MH{f['MH']}"
    return fs


# ------------------------------------------------------------------ engine


_SIG: dict = {}


def signal_series(rows, spread, L, anchor, pkey):
    """Causal signal value per session.  Cached per (pair, spread, L) so the K/E/MH
    variations of the grid do not recompute it."""
    key = (pkey, spread, L)
    if key in _SIG:
        return _SIG[key]
    n = len(rows)
    out = [None] * n
    if spread == "level":
        anch = anchor
        for i in range(1, n):
            j = rows[i]["lr"] - rows[i - 1]["lr"]
            if abs(j) > BREAK_JUMP and anch is not None:
                anch = anch * math.exp(j)     # corporate action: re-anchor
            if anch is not None:
                out[i] = rows[i]["lr"] - math.log(anch)
        _SIG[key] = out
        return out
    if spread == "z":
        x = [r["lr"] for r in rows]
    elif spread == "ret":
        x, c = [], 0.0
        for r in rows:
            c += r["ra"] - r["rb"]
            x.append(c)
    else:                              # beta: residual of log pa on log pb, rolling OLS
        la = [math.log(r["px_a"]) for r in rows]
        lb = [math.log(r["px_b"]) for r in rows]
        x = [None] * n
        sa = sb = sab = sbb = 0.0
        for i in range(n):
            sa += la[i]; sb += lb[i]; sab += la[i] * lb[i]; sbb += lb[i] * lb[i]
            if i >= L:
                k = i - L
                sa -= la[k]; sb -= lb[k]; sab -= la[k] * lb[k]; sbb -= lb[k] * lb[k]
            if i >= L - 1:
                cov = sab - sa * sb / L
                var = sbb - sb * sb / L
                if var > 0:
                    bt = cov / var
                    x[i] = la[i] - bt * lb[i]
        # z-score the residual against its own trailing window of residuals
        for i in range(n):
            if i < 2 * L - 2 or x[i] is None:
                continue
            w = [v for v in x[i - L + 1:i + 1] if v is not None]
            if len(w) < L // 2:
                continue
            mu = st.fmean(w); sd = st.pstdev(w)
            if sd > 0:
                out[i] = (x[i] - mu) / sd
        _SIG[key] = out
        return out
    s1 = s2 = 0.0
    for i in range(n):
        s1 += x[i]; s2 += x[i] * x[i]
        if i >= L:
            s1 -= x[i - L]; s2 -= x[i - L] * x[i - L]
        if i >= L - 1:
            mu = s1 / L
            var = s2 / L - mu * mu
            if var > 0:
                out[i] = (x[i] - mu) / math.sqrt(var)
    _SIG[key] = out
    return out


def run_pair(rows, f, hs_a, hs_b, anchor=None, min_dv=1e6, min_px=2.0,
             borrow=BORROW_ETB, pkey=None):
    """Returns list of trades.  Signal at close t, fill at close t+1."""
    L, K, E, MH = f["L"], f["K"], f["E"], f["MH"]
    n = len(rows)
    if n < max(L, 30) + 10:
        return []
    sigs = signal_series(rows, f["spread"], L, anchor, pkey)
    trades, pos = [], None
    for i in range(1, n - 1):        # need i+1 to fill
        r = rows[i]
        prev = rows[i - 1]
        jump = r["lr"] - prev["lr"]
        broke = abs(jump) > BREAK_JUMP
        if broke and pos is not None:
            pos = None                       # abandon, not a P&L event
        sig = sigs[i]

        # ---- exit
        if pos is not None and sig is not None:
            held = i - pos["i"]
            if abs(sig) <= E or held >= MH or i == n - 2:
                fill = rows[i + 1]
                ra_ = fill["pa"] / pos["fa"] - 1
                rb_ = fill["pb"] / pos["fb"] - 1
                h = pos["h"]
                gross = pos["sgn"] * (ra_ - h * rb_)
                lev = 1.0 + h                       # gross notional per $1 long leg
                cost = 2 * (hs_a + h * hs_b) + (1 + h) * SEC_FEE_BP * 1e-4 \
                    + borrow * max(h, 1.0) * (held / 252.0)
                trades.append({"d_in": pos["d"], "d_out": fill["d"], "hold": held,
                               "gross_bp": gross * 1e4, "cost_bp": cost * 1e4,
                               "net_bp": (gross - cost) * 1e4, "sig_in": pos["sig"],
                               "lev": lev})
                pos = None

        # ---- entry
        if pos is None and sig is not None and r["tradable"] and not broke:
            if abs(sig) < K:
                continue
            if r["dv"] < min_dv or min(r["px_a"], r["px_b"]) < min_px:
                continue
            if f["cond"] == "bigdv" and r["dv"] < 1e7:
                continue
            if f["cond"] in ("lowvol", "highvol"):
                reg = r.get("volreg")
                if reg is None or reg != f["cond"][:-3]:
                    continue
            fill = rows[i + 1]
            h = 1.0
            if f["hedge"] == "beta":
                h = r.get("rbeta") or 1.0
            pos = {"i": i, "d": fill["d"], "fa": fill["pa"], "fb": fill["pb"],
                   "sgn": -1 if sig > 0 else 1, "sig": sig, "h": h}
    return trades


# ------------------------------------------------------------------ stats


def stats(trades, n_days):
    if not trades:
        return {"n": 0}
    net = [t["net_bp"] for t in trades]
    n = len(net)
    m = st.fmean(net)
    sd = st.stdev(net) if n > 1 else float("nan")
    t = m / (sd / math.sqrt(n)) if n > 1 and sd > 0 else float("nan")
    per_yr = n / max(n_days / 252.0, 1e-9)
    sharpe = (m / sd) * math.sqrt(per_yr) if sd and sd > 0 else float("nan")
    return {"n": n,
            "gross_bp": round(st.fmean([x["gross_bp"] for x in trades]), 2),
            "cost_bp": round(st.fmean([x["cost_bp"] for x in trades]), 2),
            "net_bp": round(m, 2), "sd_bp": round(sd, 1), "t": round(t, 2),
            "hit": round(sum(1 for x in net if x > 0) / n, 3),
            "trades_per_yr": round(per_yr, 1),
            "sharpe": round(sharpe, 2),
            "mean_hold": round(st.fmean([x["hold"] for x in trades]), 1)}


def n_sessions(lo, hi):
    ds = set()
    for b in RAW.get("SPY", []):
        pass
    # use a broad-coverage symbol
    for sym in ("CHTR", "PAA", "SIRI", "CNA"):
        for b in RAW.get(sym, []):
            d = b["t"][:10]
            if lo <= d <= hi:
                ds.add(d)
        if ds:
            break
    return len(ds)


# ------------------------------------------------------------------ groups


def pairs_for(group):
    if group == "P":
        return [(a, b, r) for a, b, r, _ in GROUP_P]
    if group == "H":
        return [(a, b, None) for a, b, _ in GROUP_H]
    if group == "S":
        return [(a, b, None) for a, b, _ in GROUP_S]
    raise ValueError(group)


def run_group(group, window, formulas, borrow=BORROW_ETB, hs_mult=1.0):
    lo, hi = window
    nd = n_sessions(lo, hi)
    out = {}
    panels = {}
    for a, b, ratio in pairs_for(group):
        rows = panel(a, b, lo, hi)
        if len(rows) < 60:
            continue
        tr = [r for r in rows if r["tradable"]]
        if len(tr) < 60:
            continue
        ha, hb = half_spread(a, lo, hi), half_spread(b, lo, hi)
        if ha is None or hb is None:
            continue
        panels[(a, b)] = (rows, ha * hs_mult, hb * hs_mult, ratio)
    for f in formulas:
        if f["spread"] == "level" and group != "P":
            continue
        allt, per_pair = [], {}
        for (a, b), (rows, ha, hb, ratio) in panels.items():
            anchor = ratio if f["spread"] == "level" else None
            if f["spread"] == "level" and anchor is None:
                continue
            t = run_pair(rows, f, ha, hb, anchor=anchor, borrow=borrow,
                         pkey=(a, b, lo, hi))
            if t:
                per_pair[f"{a}/{b}"] = stats(t, nd)
                allt.extend(t)
        s = stats(allt, nd)
        s["formula"] = f["name"]
        s["id"] = f["id"]
        s["n_pairs"] = len(per_pair)
        out[f["name"]] = {"agg": s, "per_pair": per_pair}
    return out, sorted(panels)


# ------------------------------------------------------------------ group M


def deal_rows(t, q, ratio, cash, ann, end):
    ra, rb = series(t, RAW, "r"), series(q, RAW, "r")
    aa, ab = series(t, ADJ, "a"), series(q, ADJ, "a")
    days = sorted(d for d in (set(ra) & set(rb) & set(aa) & set(ab)) if ann <= d <= end)
    rows = []
    for d in days:
        pt, pq = ra[d]["c"], rb[d]["c"]
        if pt <= 0 or pq <= 0:
            continue
        implied = ratio * pq + cash
        rows.append({"d": d, "pt": pt, "pq": pq, "implied": implied,
                     "spr": (implied - pt) / pt,
                     "at": aa[d]["c"], "aq": ab[d]["c"],
                     "dv": min(pt * ra[d]["v"], pq * rb[d]["v"])})
    return rows


def run_deal(rows, ratio, K, E, MH, hs_t, hs_q, borrow, exit_at_close=True):
    n = len(rows)
    trades, pos = [], None
    for i in range(n - 1):
        r = rows[i]
        if pos is not None:
            held = i - pos["i"]
            last = (i == n - 2)
            if r["spr"] <= E or held >= MH or (exit_at_close and last):
                fill = rows[i + 1]
                rt = fill["at"] / pos["at"] - 1
                rq = fill["aq"] / pos["aq"] - 1
                h = ratio * pos["pq"] / pos["pt"]      # short notional per $1 long target
                gross = rt - h * rq
                cost = 2 * (hs_t + h * hs_q) + (1 + h) * SEC_FEE_BP * 1e-4 \
                    + borrow * h * (held / 252.0)
                trades.append({"d_in": pos["d"], "d_out": fill["d"], "hold": held,
                               "gross_bp": gross * 1e4, "cost_bp": cost * 1e4,
                               "net_bp": (gross - cost) * 1e4, "sig_in": pos["spr"]})
                pos = None
        if pos is None and i < n - 2 and r["spr"] >= K and r["dv"] >= 1e6:
            fill = rows[i + 1]
            pos = {"i": i, "d": fill["d"], "at": fill["at"], "aq": fill["aq"],
                   "pt": fill["pt"], "pq": fill["pq"], "spr": r["spr"]}
    return trades


def deal_grid():
    fs = []
    for K, E, MH in itertools.product((0.005, 0.01, 0.02, 0.04),
                                      (0.0, 0.002), (60, 250)):
        fs.append({"K": K, "E": E, "MH": MH,
                   "name": f"deal/K{K:.1%}/E{E:.1%}/MH{MH}"})
    for i, f in enumerate(fs):
        f["id"] = 2000 + i
    return fs


def run_M(split, formulas, borrow=BORROW_ETB, hs_mult=1.0):
    """split: 'design' -> announce < 2022-01-01; 'holdout' -> announce >= 2022-01-01."""
    deals = []
    for t, q, ratio, cash, ann, end, closed in GROUP_M:
        if split == "design" and ann >= "2022-01-01":
            continue
        if split == "holdout" and ann < "2022-01-01":
            continue
        rows = deal_rows(t, q, ratio, cash, ann, end)
        if len(rows) < 20:
            continue
        ht, hq = half_spread(t, ann, end), half_spread(q, ann, end)
        if ht is None or hq is None:
            continue
        deals.append((t, q, ratio, rows, ht * hs_mult, hq * hs_mult))
    span_days = sum(len(r[3]) for r in deals)
    out = {}
    for f in formulas:
        allt, per_deal = [], {}
        for t, q, ratio, rows, ht, hq in deals:
            tr = run_deal(rows, ratio, f["K"], f["E"], f["MH"], ht, hq, borrow)
            if tr:
                per_deal[f"{t}/{q}"] = stats(tr, len(rows))
                allt.extend(tr)
        # annualisation: a deal book runs concurrently; use calendar span of the split
        lo = min(r[3][0]["d"] for r in deals) if deals else "2016-01-04"
        hi = max(r[3][-1]["d"] for r in deals) if deals else "2021-12-31"
        s = stats(allt, n_sessions(lo, hi))
        s["formula"] = f["name"]
        s["id"] = f["id"]
        s["n_deals"] = len(per_deal)
        out[f["name"]] = {"agg": s, "per_pair": per_deal}
    return out, [d[0] + "/" + d[1] for d in deals]


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default="design", choices=("design", "holdout"))
    ap.add_argument("--borrow", default="etb", choices=("etb", "htb"))
    ap.add_argument("--hs-mult", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    win = DESIGN if a.window == "design" else HELDOUT
    borrow = BORROW_ETB if a.borrow == "etb" else BORROW_HTB
    fg = formula_grid()
    lg = level_grid()
    dg = deal_grid()
    res = {"window": a.window, "span": win, "borrow": a.borrow,
           "hs_mult": a.hs_mult, "groups": {}}
    for g in ("P", "H", "S"):
        forms = fg + (lg if g == "P" else [])
        r, pl = run_group(g, win, forms, borrow=borrow, hs_mult=a.hs_mult)
        res["groups"][g] = {"formulas": r, "pairs": [f"{x[0]}/{x[1]}" for x in pl]}
        print(f"[{g}] pairs={len(pl)} formulas={len(r)}", file=sys.stderr)
    r, dl = run_M(a.window, dg, borrow=borrow, hs_mult=a.hs_mult)
    res["groups"]["M"] = {"formulas": r, "pairs": dl}
    print(f"[M] deals={len(dl)} formulas={len(r)}", file=sys.stderr)
    n = sum(len(v["formulas"]) for v in res["groups"].values())
    res["hygiene"] = HYGIENE
    res["n_formulas"] = n
    res["expected_max_sharpe_under_null_SE"] = round(math.sqrt(2 * math.log(n)), 3)
    path = a.out or f"/home/anont/meme/research/data/holdco_cache/sweep_{a.window}_{a.borrow}.json"
    pathlib.Path(path).write_text(json.dumps(res))
    print("wrote", path, "N formulas", n, file=sys.stderr)


if __name__ == "__main__":
    main()
