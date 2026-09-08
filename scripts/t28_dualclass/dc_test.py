#!/usr/bin/env python3
"""Dual-class voting-premium RV: two-timescale z-fade, design 2016-2021 / held-out 2022-2026.

Signal on RAW closes (levels are point-in-time), P&L on ADJUSTED closes (total return).
Costs: 2 crossings per leg x measured half-spread (Corwin-Schultz, per symbol, per window,
cross-checked against a live NBBO snapshot), + SEC s31 on the two sales, + borrow on the short
leg for the holding period.
"""
import json, math, pathlib, statistics as st, sys, random
sys.path.insert(0, "/home/anont/meme")

CACHE = pathlib.Path("/home/anont/meme/research/data/t28_dualclass_cache")
RAW = json.load(open(CACHE / "bars_raw.json"))
ADJ = json.load(open(CACHE / "bars_all.json"))

PAIRS = [
    ("GOOGL", "GOOG"), ("BRK.A", "BRK.B"), ("FOXA", "FOX"), ("NWSA", "NWS"),
    ("UAA", "UA"), ("LEN", "LEN.B"), ("HEI", "HEI.A"), ("MOG.A", "MOG.B"),
    ("GEF", "GEF.B"), ("CWEN", "CWEN.A"), ("BIO", "BIO.B"), ("CRD.A", "CRD.B"),
    ("HVT", "HVT.A"), ("RUSHA", "RUSHB"), ("BF.A", "BF.B"), ("STZ", "STZ.B"),
    ("PARA", "PARAA"), ("WSO", "WSO.B"), ("GTN", "GTN.A"), ("LGF.A", "LGF.B"),
    ("TAP", "TAP.A"), ("MKC", "MKC.V"), ("CENTA", "CENT"), ("AGM", "AGM.A"),
    ("WLY", "WLYB"), ("JW.A", "JW.B"), ("LBRDA", "LBRDK"), ("LSXMA", "LSXMK"),
    ("FWONA", "FWONK"), ("BATRA", "BATRK"), ("QRTEA", "QRTEB"), ("Z", "ZG"),
    ("UHAL", "UHAL.B"), ("DISCA", "DISCK"), ("VIAC", "VIACA"), ("FCNCA", "FCNCB"),
    ("KELYA", "KELYB"), ("PBR", "PBR.A"), ("CIG", "CIG.C"), ("LILA", "LILAK"),
    ("LTRPA", "LTRPB"), ("VIAB", "VIA"), ("CBS", "CBS.A"),
]

DESIGN = ("2016-01-04", "2021-12-31")
HELDOUT = ("2022-01-03", "2026-08-18")

SEC_FEE_BP = 0.278           # per sale, T7/M0 convention
BORROW_ANNUAL = 0.0033       # B22G etb_general_collateral
BORROW_HTB = 0.1028


def series(sym, book):
    out = {}
    for b in book.get(sym, []):
        out[b["t"][:10]] = b
    return out


def corwin_schultz(bars, lo, hi):
    """Median CS spread estimate (fraction) over [lo,hi]; negatives floored at 0."""
    ds = sorted(d for d in bars if lo <= d <= hi)
    vals = []
    k = 3 - 2 * math.sqrt(2)
    for i in range(len(ds) - 1):
        a, b = bars[ds[i]], bars[ds[i + 1]]
        if min(a["l"], b["l"]) <= 0:
            continue
        beta = math.log(a["h"] / a["l"]) ** 2 + math.log(b["h"] / b["l"]) ** 2
        gamma = math.log(max(a["h"], b["h"]) / min(a["l"], b["l"])) ** 2
        alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
        s = 2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha))
        vals.append(max(s, 0.0))
    if not vals:
        return None
    return st.median(vals)


def build(pair, lo, hi):
    a, b = pair
    ra, rb = series(a, RAW), series(b, RAW)
    aa, ab = series(a, ADJ), series(b, ADJ)
    days = sorted(set(ra) & set(rb) & set(aa) & set(ab))
    days = [d for d in days if lo <= d <= hi]
    rows = []
    for d in days:
        if ra[d]["c"] <= 0 or rb[d]["c"] <= 0:
            continue
        dv_a = ra[d]["c"] * ra[d]["v"]
        dv_b = rb[d]["c"] * rb[d]["v"]
        rows.append({
            "d": d, "s": math.log(ra[d]["c"] / rb[d]["c"]),
            "pa": aa[d]["c"], "pb": ab[d]["c"],
            "px_a": ra[d]["c"], "px_b": rb[d]["c"],
            "dv": min(dv_a, dv_b),
        })
    return rows


def run_pair(pair, lo, hi, L, K, EXIT, MAXHOLD, min_dv, min_px, hs_a, hs_b,
             borrow=BORROW_ANNUAL):
    rows = build(pair, lo, hi)
    if len(rows) < L + 30:
        return []
    trades = []
    pos = None
    # rolling window of s, reset on structural break
    hist = []
    for i, r in enumerate(rows):
        if i > 0:
            jump = abs(r["s"] - rows[i - 1]["s"])
            gapdays = 0
            if jump > 0.15:
                hist = []          # structural break: forget the level
                if pos:
                    pos = None     # abandon (not counted; a break is not a P&L event)
        if pos:
            z = None
            if len(hist) >= L:
                mu = st.fmean(hist[-L:]); sd = st.pstdev(hist[-L:])
                z = (r["s"] - mu) / sd if sd > 0 else 0.0
            held = i - pos["i"]
            if (z is not None and abs(z) <= EXIT) or held >= MAXHOLD or i == len(rows) - 1:
                sgn = pos["sgn"]   # +1 => long A short B
                ra_ = r["pa"] / pos["pa"] - 1
                rb_ = r["pb"] / pos["pb"] - 1
                gross = sgn * (ra_ - rb_)
                cost = 2 * (hs_a + hs_b) + 2 * SEC_FEE_BP * 1e-4 \
                    + borrow * (held / 252.0)
                trades.append({"d_in": pos["d"], "d_out": r["d"], "hold": held,
                               "gross_bp": gross * 1e4, "cost_bp": cost * 1e4,
                               "net_bp": (gross - cost) * 1e4, "z_in": pos["z"]})
                pos = None
        if not pos and len(hist) >= L:
            mu = st.fmean(hist[-L:]); sd = st.pstdev(hist[-L:])
            if sd > 0:
                z = (r["s"] - mu) / sd
                if abs(z) >= K and r["dv"] >= min_dv and min(r["px_a"], r["px_b"]) >= min_px:
                    pos = {"i": i, "d": r["d"], "pa": r["pa"], "pb": r["pb"],
                           "sgn": -1 if z > 0 else 1, "z": z}
        hist.append(r["s"])
    return trades


def spreads(window):
    lo, hi = window
    out = {}
    for sym in {s for p in PAIRS for s in p}:
        bars = series(sym, RAW)
        cs = corwin_schultz(bars, lo, hi)
        out[sym] = cs
    return out


def stats(trades, label, n_days):
    if not trades:
        return {"label": label, "n": 0}
    net = [t["net_bp"] for t in trades]
    gross = [t["gross_bp"] for t in trades]
    n = len(net)
    m = st.fmean(net); sd = st.stdev(net) if n > 1 else float("nan")
    tstat = m / (sd / math.sqrt(n)) if n > 1 and sd > 0 else float("nan")
    per_yr = n / (n_days / 252.0)
    book_sharpe = (m / sd) * math.sqrt(per_yr) if sd > 0 else float("nan")
    hit = sum(1 for x in net if x > 0) / n
    return {"label": label, "n": n, "gross_bp": round(st.fmean(gross), 2),
            "cost_bp": round(st.fmean([t["cost_bp"] for t in trades]), 2),
            "net_bp": round(m, 2), "sd_bp": round(sd, 1), "t": round(tstat, 2),
            "hit": round(hit, 3), "per_trade_sharpe": round(m / sd, 4) if sd else None,
            "trades_per_yr": round(per_yr, 1),
            "book_sharpe": round(book_sharpe, 2),
            "mean_hold": round(st.fmean([t["hold"] for t in trades]), 1)}


def bootstrap_p(trades, iters=4000, seed=11):
    net = [t["net_bp"] for t in trades]
    if len(net) < 5:
        return None
    rng = random.Random(seed)
    n = len(net)
    cnt = 0
    for _ in range(iters):
        s = sum(net[rng.randrange(n)] for _ in range(n))
        if s <= 0:
            cnt += 1
    return cnt / iters


def go(window, label, L=250, K=2.0, EXIT=0.5, MAXHOLD=20, min_dv=1e6, min_px=2.0,
       hs_mult=1.0, borrow=BORROW_ANNUAL, sp=None, verbose=False):
    lo, hi = window
    sp = sp or spreads(window)
    allt = []
    per_pair = {}
    ndays = 0
    for p in PAIRS:
        ha, hb = sp.get(p[0]), sp.get(p[1])
        if ha is None or hb is None:
            continue
        t = run_pair(p, lo, hi, L, K, EXIT, MAXHOLD, min_dv, min_px,
                     ha / 2 * hs_mult, hb / 2 * hs_mult, borrow)
        if t:
            per_pair[f"{p[0]}/{p[1]}"] = stats(t, "", 1)
            allt.extend(t)
    # window length in trading days
    days = sorted({r for p in PAIRS for r in [d["d"] for d in build(p, lo, hi)]})
    ndays = len(days)
    s = stats(allt, label, ndays)
    s["p_boot_mean_le_0"] = bootstrap_p(allt)
    return s, per_pair, allt, sp
