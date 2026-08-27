#!/usr/bin/env python3
"""STEP 3 of INVENT 0822B -- design-window diagnostics + a CLEAN size-matched placebo.

Why a second placebo.  The rotate-the-returns placebo in the sweep keeps the weights fixed
but pairs them with a return panel from another date; coins that were not yet listed then
have no return, so a dollar-neutral book silently acquires a large net exposure and the
null grows a fat right tail.  The clean placebo instead permutes the SIGNAL across the
day's ADV-RANK SLOTS with one permutation fixed for the whole replicate.  Slot j is very
nearly the same coin day after day, so the permuted signal keeps the original's
persistence and turnover; every leg is a genuinely live universe member, so neutrality and
the cross-sectional return covariance are exactly preserved; only the signal-to-coin
alignment is destroyed.

Also measures, on the DESIGN window only: market beta, per-family correlation, and the
liquidity-floor sensitivity of every formula that clears the analytic bar.
"""
from __future__ import annotations
import json, sys, datetime as dt, numpy as np
sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from inv0822b_xs_lib import (load, features, universe, fwd_ret, extremes_book, tranche,
                             evaluate, sharpe, tstat, breakeven_bp, shift, roll_mean,
                             HOLDS, FEE_BP, EXTREME, ANN)
import inv0822b_xs_forms as FORMS

BASE = "/home/anont/meme/research/trading_bot/INVENT_0822B_cryptoXS"
D0, D1 = dt.date(2019, 1, 1), dt.date(2023, 1, 1)
N_PERM = 400


def slots(U, F, top=50):
    """(top,T) coin index of the day's universe ordered by trailing ADV, -1 where empty."""
    adv = shift(roll_mean(F["qv"], 30), 1)
    S, T = U.shape
    idx = np.full((top, T), -1, np.int32)
    for t in range(T):
        m = np.where(U[:, t])[0]
        if m.size == 0:
            continue
        o = m[np.argsort(-np.where(np.isfinite(adv[m, t]), adv[m, t], -np.inf))]
        k = min(top, o.size)
        idx[:k, t] = o[:k]
    return idx


def to_slot(X, idx):
    out = np.full(idx.shape, np.nan)
    ok = idx >= 0
    cols = np.tile(np.arange(idx.shape[1]), (idx.shape[0], 1))
    out[ok] = X[idx[ok], cols[ok]]
    return out


def book_from_slotsig(S, k=EXTREME):
    """(N,top,T) slot signals -> (N,top,T) extremes weights."""
    N, M, T = S.shape
    X = np.where(np.isfinite(S), S, np.nan)
    big = np.where(np.isfinite(X), X, np.inf)
    order = np.argsort(big, axis=1)
    cnt = np.isfinite(X).sum(1)                      # (N,T)
    W = np.zeros_like(X)
    rank = np.argsort(order, axis=1)                 # rank of each slot, 0 = smallest
    lo = rank < k
    hi = (rank >= (cnt[:, None, :] - k)) & np.isfinite(X)
    ok = cnt >= 2 * k + 5
    W = np.where(hi & ok[:, None, :], 0.5 / k, 0.0) - np.where(lo & ok[:, None, :], 0.5 / k, 0.0)
    return W


def tranche3(W, H):
    if H <= 1:
        return W
    acc = np.zeros_like(W)
    for j in range(H):
        s = np.zeros_like(W)
        if j:
            s[:, :, j:] = W[:, :, :-j]
        else:
            s = W
        acc = acc + s
    return acc / H


def main():
    P = load(); F = features(P); U = universe(P, F)
    dates = P["dates"]
    btc = int(np.where(P["syms"] == "BTCUSDT")[0][0])
    R = fwd_ret(F)
    forms = FORMS.build(P, F, U, btc)
    names = sorted(forms)
    dm = (dates >= D0) & (dates < D1)
    des = json.load(open(f"{BASE}_DESIGN.json"))
    signs = des["signs"]
    res = {}

    # ---- market factor: equal-weight universe, VWAP-to-VWAP -----------------------
    Uw = U.astype(float)
    n_t = np.maximum(Uw.sum(0), 1)
    mkt = (np.where(U, np.nan_to_num(R), 0.0)).sum(0) / n_t
    res["market"] = dict(sharpe_design=sharpe(mkt[dm]), vol_ann=float(mkt[dm].std() * ANN))

    # ---- per-formula beta / correlation to that market ---------------------------
    betas, pnls = {}, {}
    for nm in names:
        fam, sig = forms[nm]
        w1 = extremes_book(sig, U)
        for H in HOLDS:
            key = f"{nm}|H{H}"
            w = tranche(w1, H)
            g = signs[key] * (w * np.nan_to_num(R)).sum(0)
            pnls[key] = g
            x, y = mkt[dm], g[dm]
            b = float(np.cov(x, y)[0, 1] / max(x.var(), 1e-18))
            betas[key] = dict(beta=b, corr=float(np.corrcoef(x, y)[0, 1]),
                              beta_h1=float(np.cov(x[:len(x)//2], y[:len(y)//2])[0,1] /
                                            max(x[:len(x)//2].var(), 1e-18)),
                              beta_h2=float(np.cov(x[len(x)//2:], y[len(y)//2:])[0,1] /
                                            max(x[len(x)//2:].var(), 1e-18)))
    res["beta_to_market_design"] = betas

    # ---- correlation among the top design formulas -------------------------------
    top = [r["key"] for r in sorted(des["rows"], key=lambda r: -r["gross"])[:12]]
    M = np.stack([pnls[k][dm] for k in top])
    C = np.corrcoef(M)
    res["top12_keys"] = top
    res["top12_corr"] = C.tolist()
    res["top12_mean_abs_corr"] = float((np.abs(C).sum() - len(top)) / (len(top) ** 2 - len(top)))

    # ---- CLEAN placebo: permute the signal across ADV-rank slots ------------------
    idx = slots(U, F, 50)
    Rs = to_slot(np.nan_to_num(R, nan=0.0), idx)
    Rs = np.nan_to_num(Rs)[:, dm]
    Sig = np.stack([to_slot(forms[nm][1], idx)[:, dm] for nm in names])   # (F,50,Td)
    keys = [f"{nm}|H{H}" for nm in names for H in HOLDS]
    sgn = np.array([signs[k] for k in keys])

    def score(Sarr):
        outs = []
        W = book_from_slotsig(Sarr)
        for H in HOLDS:
            outs.append(tranche3(W, H))
        Wall = np.stack(outs, axis=1).reshape(-1, Sarr.shape[1], Sarr.shape[2])
        # order must match `keys`: formula-major, hold-minor
        pnl = np.einsum("nmt,mt->nt", Wall, Rs, optimize=True)
        sd = pnl.std(1)
        return np.where(sd > 0, pnl.mean(1) / np.maximum(sd, 1e-18) * ANN, 0.0)

    real = score(Sig) * sgn
    rng = np.random.default_rng(9090)
    mx, allsr = [], []
    for _ in range(N_PERM):
        p = rng.permutation(50)
        s = score(Sig[:, p, :])
        allsr.append(s)
        mx.append(float(np.abs(s).max()))
    mx = np.array(mx); allsr = np.stack(allsr)
    res["clean_placebo"] = dict(
        n_permutations=N_PERM, n_tests=len(keys),
        E_max_abs_sharpe=float(mx.mean()), p50=float(np.percentile(mx, 50)),
        p95=float(np.percentile(mx, 95)), p99=float(np.percentile(mx, 99)),
        sd_single=float(np.mean(allsr.std(0))),
        observed_max=float(np.abs(real).max()),
        observed_max_key=keys[int(np.argmax(np.abs(real)))],
        frac_placebo_max_ge_observed=float((mx >= np.abs(real).max()).mean()),
        slot_check_real_vs_sweep={k: float(v) for k, v in
                                  zip(keys[:0], [])},
    )
    res["clean_placebo_per_formula"] = {
        k: dict(slot_sharpe=float(real[i]),
                p95=float(np.percentile(np.abs(allsr[:, i]), 95)),
                p_value=float((np.abs(allsr[:, i]) >= abs(real[i])).mean()))
        for i, k in enumerate(keys)}

    # ---- liquidity floor on the design winners -----------------------------------
    floors = {}
    adv30 = shift(roll_mean(F["qv"], 30), 1)
    for key in top[:6]:
        nm, hh = key.split("|H"); H = int(hh)
        fam, sig = forms[nm]
        row = {}
        for fl in (0, 5e6, 25e6, 100e6):
            Uf = U & (adv30 >= fl)
            w = tranche(extremes_book(sig, Uf), H)
            g, nt, dw = evaluate(w, R, FEE_BP)
            g = signs[key] * g
            net = g - dw * FEE_BP * 1e-4
            row[f"{int(fl/1e6)}M"] = dict(gross=sharpe(g[dm]), net=sharpe(net[dm]),
                                          net_t=tstat(net[dm]),
                                          univ=float(Uf[:, dm].sum(0).mean()))
        floors[key] = row
    res["liquidity_floor_design"] = floors

    json.dump(res, open(f"{BASE}_DIAG.json", "w"), indent=1, default=float)
    print("market design sharpe", round(res["market"]["sharpe_design"], 3))
    print("\nCLEAN PLACEBO:", json.dumps({k: v for k, v in res["clean_placebo"].items()
                                          if not isinstance(v, dict)}, indent=1))
    print("\ntop12 mean|corr|", round(res["top12_mean_abs_corr"], 3))
    print(f"\n{'key':24s} {'beta':>7s} {'corr':>7s} {'b_h1':>7s} {'b_h2':>7s} "
          f"{'slotSR':>7s} {'pp95':>6s} {'pval':>6s}")
    for k in top:
        b = betas[k]; c = res["clean_placebo_per_formula"][k]
        print(f"{k:24s} {b['beta']:7.2f} {b['corr']:7.2f} {b['beta_h1']:7.2f} "
              f"{b['beta_h2']:7.2f} {c['slot_sharpe']:7.2f} {c['p95']:6.2f} {c['p_value']:6.3f}")
    print("\nLIQUIDITY FLOOR (design net Sharpe):")
    for k, v in floors.items():
        print(f"  {k:24s} " + "  ".join(f"{f}:{v[f]['net']:+.2f}(u{v[f]['univ']:.0f})"
                                        for f in v))


if __name__ == "__main__":
    main()
