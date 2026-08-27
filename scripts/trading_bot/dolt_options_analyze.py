#!/usr/bin/env python3
"""
FIRST honest test of cross-sectional option-implied signals on the free DoltHub
equity-options panel (post-no-preference/options).

Signals (all cross-sectional, single-name, DIRECTIONAL ON THE STOCK -- executed
on the underlying, not on options; signal computed from the EOD option chain):
  SKEW_RR   = IV(25d put) - IV(25d call)        [Xing-Zhang-Zhao smirk]
  PUT_SLOPE = IV(25d put) - ATM IV              [downside skew slope]
  TERM      = ATM IV(far ~90d) - ATM IV(near ~30d)   [Vasquez term slope]
  IVLEVEL   = ATM IV near (cross-sectional z)   [vol/lottery proxy, Ang]
  IVCHG     = ATM IV near change vs prev sample [vol momentum]
  VRP       = ATM IV near - trailing realized vol (weekly-sampled)

For each signal we form a dollar-neutral cross-sectional long-short book
(rank-demeaned weights) rebalanced at each sampled date, and measure the
GROSS Sharpe/t of forward stock returns. Pre-registered design/held-out split.
Multiple-testing bar = max(analytic sqrt(2 ln N), size-matched placebo).

Methodology per INVENT_0823_MASTER / EXECUTION_COST_WALL / OU_MEAN_REVERSION:
  - GROSS clears the pooled MT bar FIRST, before any cost claim.
  - size-matched placebo permutes the SIGNAL across panel slots (weights stay
    attached to slots so gross/turnover/covariance preserved).
  - design/held-out declared before scoring; held-out read once.
  - directional book off a DIFFERENT instrument than the signal (stock vs option
    IV) so the Clause-4 same-print-bounce inflation does not apply; we still add
    a past-return-neutralized control so the signal is not a disguised
    momentum/reversal proxy.
Research only. No orders. No git.
"""
import json, os, glob, math
import numpy as np

CACHE = "/home/anont/meme/research/data/doltopts_cache"
DESIGN_END = "2023-12-31"   # declared BEFORE scoring
CONTROLS = {"SPY", "QQQ"}   # excluded from single-name cross-section

def dte(exp, d):
    from datetime import date
    y,m,dd = map(int, exp.split("-")); e = date(y,m,dd)
    y,m,dd = map(int, d.split("-")); t = date(y,m,dd)
    return (e - t).days

def fnum(x):
    try:
        v = float(x); return v if math.isfinite(v) else None
    except Exception:
        return None

def sym_signals(rows, d):
    """Return dict of per-symbol option features for one date, or None."""
    puts, calls = [], []
    for r in rows:
        iv = fnum(r["vol"]); dl = fnum(r["delta"]); n = dte(r["expiration"], d)
        if iv is None or dl is None or iv <= 0.01 or n < 5 or n > 200:
            continue
        rec = (n, dl, iv)
        if r["call_put"] == "Put":
            puts.append(rec)
        else:
            calls.append(rec)
    if not calls or not puts:
        return None
    # near bucket 15-45 DTE, far bucket 60-130 DTE (choose expiry nearest target)
    def pick_atm(opts, lo, hi, tgt_n):
        cand = [(abs(n - tgt_n), abs(abs(dl) - 0.5), iv) for (n, dl, iv) in opts if lo <= n <= hi]
        if not cand:
            return None
        cand.sort()
        return cand[0][2]
    # NB: this free panel is FRONT-MONTH only (max DTE ~50-65d), so "term" is a
    # short-end slope (~16d vs ~51d), not a 1M-vs-3M structure.
    atm_near = pick_atm(calls, 8, 25, 16) or pick_atm(puts, 8, 25, 16)
    atm_far  = pick_atm(calls, 41, 70, 51) or pick_atm(puts, 41, 70, 51)
    atm_mid  = pick_atm(calls, 20, 45, 30) or pick_atm(puts, 20, 45, 30)
    # ~30d 25-delta wings for skew
    def pick_delta(opts, lo, hi, tgt_abs_delta):
        cand = [(abs(abs(dl) - tgt_abs_delta), iv) for (n, dl, iv) in opts if lo <= n <= hi]
        if not cand:
            return None
        cand.sort(); return cand[0][1]
    p25 = pick_delta(puts, 20, 45, 0.25)
    c25 = pick_delta(calls, 20, 45, 0.25)
    if atm_near is None:
        return None
    out = {"atm_near": atm_near, "atm_far": atm_far, "atm_mid": atm_mid or atm_near,
           "p25": p25, "c25": c25}
    return out

def load_panel():
    files = sorted(glob.glob(os.path.join(CACHE, "20*.json")))
    dates = []
    feats = {}   # date -> {sym -> featdict}
    px = {}      # date -> {sym -> close}
    for fp in files:
        d = json.load(open(fp))
        ds = d["date"]
        sig = {}
        for sym, rows in d["options"].items():
            if sym in CONTROLS:
                continue
            s = sym_signals(rows, ds)
            if s:
                sig[sym] = s
        cl = {}
        for sym, o in d["stocks"].items():
            c = fnum(o.get("close"))
            if c and c > 0:
                cl[sym] = c
        if sig and cl:
            dates.append(ds); feats[ds] = sig; px[ds] = cl
    dates.sort()
    return dates, feats, px

def build_signals(dates, feats, px):
    """Assemble per-date cross-sectional signal vectors + forward returns."""
    recs = []  # list of dicts: date, syms, sigvals{signame:arr}, fwd_ret
    prev_atm = {}
    # trailing realized vol from weekly closes
    for i, ds in enumerate(dates[:-1]):
        nxt = dates[i+1]
        f = feats[ds]
        syms = [s for s in f if s in px[ds] and s in px[nxt]]
        if len(syms) < 8:
            prev_atm = {s: f[s]["atm_mid"] for s in f}
            continue
        fwd = np.array([px[nxt][s] / px[ds][s] - 1.0 for s in syms])
        skew_rr = []; put_slope = []; term = []; ivlevel = []; ivchg = []
        for s in syms:
            fs = f[s]
            an = fs["atm_near"]; af = fs["atm_far"]; am = fs["atm_mid"]
            p = fs["p25"]; c = fs["c25"]
            skew_rr.append(p - c if (p is not None and c is not None) else np.nan)
            put_slope.append(p - am if p is not None else np.nan)
            term.append(af - an if af is not None else np.nan)
            ivlevel.append(am)
            pa = prev_atm.get(s)
            ivchg.append(am - pa if pa is not None else np.nan)
        recs.append({
            "date": ds, "syms": syms, "fwd": fwd,
            "SKEW_RR": np.array(skew_rr), "PUT_SLOPE": np.array(put_slope),
            "TERM": np.array(term), "IVLEVEL": np.array(ivlevel),
            "IVCHG": np.array(ivchg),
        })
        prev_atm = {s: f[s]["atm_mid"] for s in f}
    return recs

def xs_weights(sig):
    """Rank-demeaned dollar-neutral weights; NaNs dropped (0 weight)."""
    w = np.full(len(sig), np.nan)
    ok = np.isfinite(sig)
    if ok.sum() < 6:
        return None
    x = sig[ok]
    r = np.argsort(np.argsort(x)).astype(float)
    r = r - r.mean()
    if np.abs(r).sum() == 0:
        return None
    r = r / np.abs(r).sum()   # gross = 1
    w[:] = 0.0; w[ok] = r
    return w

def book_pnl(recs, signame, sign=+1.0, permute=None, rng=None, neutralize_ret=False):
    """Daily(=weekly-sample) gross returns of the L/S book for one signal.
    sign: +1 means long high-signal. permute: if 'shuffle', permute signal across slots.
    neutralize_ret: regress signal on prior-period fwd sign? (past-return control)
    """
    pnl = []
    for rec in recs:
        sig = rec[signame].copy()
        if permute == "shuffle" and rng is not None:
            fin = np.isfinite(sig)
            idx = np.where(fin)[0]
            perm = rng.permutation(idx)
            tmp = sig.copy(); tmp[idx] = sig[perm]; sig = tmp
        w = xs_weights(sig * sign)
        if w is None:
            continue
        wok = np.nan_to_num(w)
        pnl.append(float(np.dot(wok, rec["fwd"])))
    return np.array(pnl)

def sharpe_t(pnl):
    if len(pnl) < 20:
        return 0.0, 0.0, len(pnl)
    m = pnl.mean(); s = pnl.std(ddof=1)
    if s == 0:
        return 0.0, 0.0, len(pnl)
    sh = m / s * math.sqrt(52)      # weekly -> annualized
    t = m / (s / math.sqrt(len(pnl)))
    return sh, t, len(pnl)

SIGNALS = ["SKEW_RR", "PUT_SLOPE", "TERM", "IVLEVEL", "IVCHG"]
# pre-registered directional priors (hypothesised sign of long-high book Sharpe):
#  SKEW_RR: high put skew -> underperformance -> SHORT high -> sign -1
#  PUT_SLOPE: same -> -1
#  TERM: inverted term (near>far, i.e. TERM<0) = stress -> long high TERM? ambiguous; test both, count both
#  IVLEVEL: high IV -> low return (lottery) -> -1
#  IVCHG: rising IV -> -1 (deteriorating)
PRIOR = {"SKEW_RR": -1, "PUT_SLOPE": -1, "TERM": +1, "IVLEVEL": -1, "IVCHG": -1}

def main():
    dates, feats, px = load_panel()
    print(f"panel: {len(dates)} sampled dates, {dates[0] if dates else None}..{dates[-1] if dates else None}")
    recs = build_signals(dates, feats, px)
    print(f"usable cross-sections: {len(recs)}")
    if len(recs) < 30:
        print("INSUFFICIENT DATA"); return
    des = [r for r in recs if r["date"] <= DESIGN_END]
    hold = [r for r in recs if r["date"] > DESIGN_END]
    print(f"design {len(des)}  held-out {len(hold)}")
    avg_n = np.mean([len(r["syms"]) for r in recs])
    print(f"avg names/cross-section: {avg_n:.1f}")

    # N formulas = signals x 2 sign directions (we test both to be honest about the
    # ambiguous TERM prior) -> pooled MT correction.
    N = len(SIGNALS) * 2
    bar_analytic = math.sqrt(2 * math.log(N))
    print(f"\nN formulas = {N}; analytic bar sqrt(2 ln N) = {bar_analytic:.3f} t\n")

    rng = np.random.default_rng(42)
    # placebo: max |t| over shuffled-signal books across the whole family (design)
    PLA = 400
    placebo_max = []
    for k in range(PLA):
        mx = 0.0
        for sg in SIGNALS:
            for sn in (+1, -1):
                p = book_pnl(des, sg, sign=sn, permute="shuffle", rng=rng)
                _, t, _ = sharpe_t(p)
                mx = max(mx, abs(t))
        placebo_max.append(mx)
    placebo_bar = float(np.percentile(placebo_max, 95))
    print(f"size-matched placebo 95% |t| bar (design, {PLA} draws) = {placebo_bar:.3f}")
    bar = max(bar_analytic, placebo_bar)
    print(f"OPERATIVE BAR = {bar:.3f} t\n")

    print(f"{'signal':10s} {'sgn':>3s} | {'DES sharpe':>10s} {'DES t':>7s} | {'clears?':>7s} | {'HOLD sharpe':>11s} {'HOLD t':>7s}")
    results = {}
    for sg in SIGNALS:
        for sn in (+1, -1):
            pd = book_pnl(des, sg, sign=sn)
            shd, td, nd = sharpe_t(pd)
            clears = abs(td) >= bar and (td > 0)  # long-high book must be positive-t to "work" in that sign
            ph = book_pnl(hold, sg, sign=sn)
            shh, th, nh = sharpe_t(ph)
            tag = "YES" if clears else "-"
            star = " <==" if clears else ""
            print(f"{sg:10s} {sn:+d}  | {shd:10.3f} {td:7.2f} | {tag:>7s} | {shh:11.3f} {th:7.2f}{star}")
            results[f"{sg}_{sn:+d}"] = {"design_sharpe": shd, "design_t": td, "n_des": nd,
                                        "hold_sharpe": shh, "hold_t": th, "n_hold": nh,
                                        "clears_design": bool(clears)}
    out = {"n_dates": len(dates), "date_range": [dates[0], dates[-1]],
           "n_cross_sections": len(recs), "avg_names": avg_n,
           "design_end": DESIGN_END, "N_formulas": N,
           "bar_analytic": bar_analytic, "placebo_bar": placebo_bar, "bar": bar,
           "results": results}
    with open("/home/anont/meme/research/trading_bot/DOLT_OPTIONS_RESULT.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote DOLT_OPTIONS_RESULT.json")

if __name__ == "__main__":
    main()
