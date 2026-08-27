#!/usr/bin/env python3
"""STEP 2 of INVENT 0822B -- the design-window sweep + the SIZE-MATCHED placebo null.

Usage:  inv0822b_xs_sweep.py design      (writes ..._DESIGN.json, freezes signs)
        inv0822b_xs_sweep.py holdout     (reads the frozen signs, scores 2023-01-01+)

The placebo: every formula's WEIGHT matrix is held exactly fixed (so universe, turnover,
cost, hold and cross-sectional gross are identical) and the RETURN panel is rotated
circularly inside the same window.  That destroys the signal/return alignment and nothing
else.  E[max |Sharpe|] over all N formula-hold combinations, one shared rotation per
replicate so cross-formula correlation survives into the null.
"""
from __future__ import annotations
import json, sys, datetime as dt, numpy as np
sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from inv0822b_xs_lib import (load, features, universe, fwd_ret, extremes_book, tranche,
                             evaluate, sharpe, tstat, breakeven_bp, shift, rho1,
                             HOLDS, FEE_BP, ANN)
import inv0822b_xs_forms as FORMS

BASE = "/home/anont/meme/research/trading_bot/INVENT_0822B_cryptoXS"
D0, D1 = dt.date(2019, 1, 1), dt.date(2023, 1, 1)
H1 = dt.date(2026, 8, 1)
N_PLACEBO = 600


def window(dates, a, b):
    return (dates >= a) & (dates < b)


def main(mode):
    P = load(); F = features(P); U = universe(P, F)
    dates = P["dates"]
    btc = int(np.where(P["syms"] == "BTCUSDT")[0][0])
    R = fwd_ret(F)
    forms = FORMS.build(P, F, U, btc)
    names = sorted(forms)
    dmask = window(dates, D0, D1)
    hmask = window(dates, D1, H1)
    sel = dmask if mode == "design" else hmask

    frozen = None
    if mode == "holdout":
        frozen = json.load(open(f"{BASE}_DESIGN.json"))["signs"]

    rowsel = U.any(1)
    rows, Wstack, keys = [], [], []
    for nm in names:
        fam, sig = forms[nm]
        w1 = extremes_book(sig, U)
        siglag = shift(sig, 1)
        w1lag = extremes_book(siglag, U)
        for H in HOLDS:
            key = f"{nm}|H{H}"
            w = tranche(w1, H)
            g, nt, dw = evaluate(w, R, FEE_BP)
            gs_d = sharpe(g[dmask])
            sgn = frozen[key] if frozen is not None else (1.0 if gs_d >= 0 else -1.0)
            gg = sgn * (w * np.nan_to_num(R)).sum(0)
            cost = dw * FEE_BP * 1e-4
            net = gg - cost
            net20 = gg - dw * 20.0 * 1e-4
            wl = tranche(w1lag, H)
            gl, _, dwl = evaluate(wl, R, FEE_BP)
            gl = sgn * gl
            rec = dict(name=nm, fam=fam, hold=H, key=key, sign=float(sgn),
                       turn=float(dw[sel].mean()),
                       gross=sharpe(gg[sel]), gross_t=tstat(gg[sel]),
                       net=sharpe(net[sel]), net_t=tstat(net[sel]),
                       net20=sharpe(net20[sel]),
                       be_bp=breakeven_bp(gg[sel], dw[sel]),
                       lag1_gross=sharpe(gl[sel]), lag1_net=sharpe((gl - dwl * FEE_BP * 1e-4)[sel]),
                       worst_day=float(np.min(net[sel])), skew=float(_skew(net[sel])),
                       maxdd=float(_maxdd(net[sel])))
            rows.append(rec)
            if mode == "design":
                Wstack.append((sgn * w)[rowsel][:, dmask].astype(np.float32))
                keys.append(key)

    out = dict(mode=mode, n_formulas=len(names), n_tests=len(rows),
               window=[str(D0 if mode == "design" else D1),
                       str(D1 if mode == "design" else H1)],
               n_days=int(sel.sum()), fee_bp=FEE_BP,
               universe_mean_size=float(U[:, sel].sum(0).mean()),
               rows=rows)
    if mode == "design":
        out["signs"] = {r["key"]: r["sign"] for r in rows}
        out["null"] = placebo(np.stack(Wstack), R[rowsel][:, dmask], keys, rows)
    json.dump(out, open(f"{BASE}_{mode.upper()}.json", "w"), indent=1, default=float)
    _print(out)


def _skew(x):
    x = np.asarray(x, float); s = x.std()
    return float(((x - x.mean()) ** 3).mean() / s ** 3) if s > 0 else 0.0


def _maxdd(x):
    c = np.cumsum(np.nan_to_num(x))
    return float(np.min(c - np.maximum.accumulate(c)) / max(np.std(x) * ANN, 1e-12))


def placebo(A, Rd, keys, rows):
    """A: (N, S, Td) frozen sign-applied weights.  Rd: (S, Td) design returns."""
    Rd = np.nan_to_num(Rd).astype(np.float32)
    N, S, Td = A.shape
    rng = np.random.default_rng(20260822)
    offs = rng.integers(90, Td - 90, size=N_PLACEBO)
    idx0 = np.arange(Td)
    mx, per = [], np.zeros((N_PLACEBO, N), np.float32)
    for i, k in enumerate(offs):
        Rk = Rd[:, (idx0 + int(k)) % Td]
        pnl = np.einsum("nst,st->nt", A, Rk, optimize=True)
        sd = pnl.std(1); mu = pnl.mean(1)
        sh = np.where(sd > 0, mu / np.maximum(sd, 1e-18) * ANN, 0.0)
        per[i] = sh
        mx.append(float(np.abs(sh).max()))
    mx = np.array(mx)
    real = np.array([r["gross"] for r in rows])
    se = float(np.mean(np.abs(per).std(0)))
    n = len(rows)
    return dict(
        n_tests=n, n_replicates=N_PLACEBO,
        placebo_E_max_abs_sharpe=float(mx.mean()),
        placebo_p50=float(np.percentile(mx, 50)),
        placebo_p95=float(np.percentile(mx, 95)),
        placebo_p99=float(np.percentile(mx, 99)),
        placebo_sd_single_formula_sharpe=se,
        analytic_bar_sharpe_one_sided=float(np.sqrt(2 * np.log(n)) * se),
        analytic_bar_sharpe_sign_agnostic=float(np.sqrt(2 * np.log(2 * n)) * se),
        programme_cumulative_bar_sharpe=float(np.sqrt(2 * np.log(1040)) * se),
        observed_max_gross=float(np.abs(real).max()),
        frac_placebo_max_above_observed=float((mx >= np.abs(real).max()).mean()),
        per_formula_placebo_p95={k: float(np.percentile(np.abs(per[:, j]), 95))
                                 for j, k in enumerate(keys)},
    )


def _print(out):
    rows = sorted(out["rows"], key=lambda r: -r["gross"])
    print(f"== {out['mode']} {out['window']}  n_tests={out['n_tests']}  "
          f"days={out['n_days']}  univ={out['universe_mean_size']:.1f}")
    print(f"{'key':26s} {'fam':3s} {'turn':>6s} {'gross':>7s} {'gt':>6s} "
          f"{'net':>7s} {'nt':>6s} {'net20':>7s} {'BE':>7s} {'lag1g':>7s}")
    for r in rows:
        print(f"{r['key']:26s} {r['fam']:3s} {r['turn']:6.3f} {r['gross']:7.2f} "
              f"{r['gross_t']:6.2f} {r['net']:7.2f} {r['net_t']:6.2f} {r['net20']:7.2f} "
              f"{r['be_bp']:7.1f} {r['lag1_gross']:7.2f}")
    if "null" in out:
        print("\nNULL:", json.dumps({k: v for k, v in out["null"].items()
                                     if not isinstance(v, dict)}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "design")
