#!/usr/bin/env python3
"""XLL equity block: WIDE sweep of cross-asset / cross-venue lead-lag on the cached t17 daily panel.

Leaders live inside the SAME cached panel (SPY/QQQ/IWM, the 11 sector SPDRs, TLT/IEF for rates,
UUP/FXE for FX, GLD/USO for commodities, HYG/LQD for credit, VIXY for vol, EFA/EWJ/FXI for
overseas sessions, plus a Bitstamp BTC daily series on disk) so nothing is re-fetched.

Same discipline as the crypto block: DESIGN window only, empirical time-shift null with one
shared shift per draw so the max-over-configs bar respects cross-config correlation.

KNOWN BIAS, stated up front: the t17 universe is drawn from a CURRENT broker asset list, so
delisted names are absent (survivorship). Every formula here is cross-sectionally demeaned and
dollar-neutral, which absorbs most but not all of that.
"""
from __future__ import annotations
import json, os, time
import numpy as np

ROOT = "/home/anont/meme"
PANEL = f"{ROOT}/research/data/xll_cache/eq_daily_panel.npz"
BTCCSV = f"{ROOT}/research/data/btc_usd_daily_bitstamp_2013_2026.csv"
OUTJ = f"{ROOT}/research/trading_bot/SWEEP_xll_equity.json"

DESIGN_END = "2022-01-01"
COST_BP_PER_SIDE = 5.0    # B22B measured full quoted spread p50=3bp on this liquidity band
                          # -> 1.5bp half-spread; +3.5bp impact/slippage rung (STRESS_LADDER).
MIN_DV = 3e6
N_NULL = 240
rng = np.random.default_rng(20260820)

LEADERS = ["SPY", "QQQ", "IWM", "TLT", "IEF", "UUP", "FXE", "GLD", "USO", "HYG", "LQD",
           "VIXY", "EEM", "EFA", "EWJ", "FXI", "SMH", "KRE", "XBI"]
SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]


def rolling_sum(a, w, axis=-1):
    cs = np.cumsum(a.astype(np.float64), axis=axis)
    out = cs.copy()
    hi = [slice(None)] * a.ndim; lo = [slice(None)] * a.ndim
    hi[axis] = slice(w, None); lo[axis] = slice(None, -w)
    out[tuple(hi)] = cs[tuple(hi)] - cs[tuple(lo)]
    return out


def lag(a, k=1):
    out = np.zeros_like(a)
    if a.ndim == 1: out[k:] = a[:-k]
    else: out[:, k:] = a[:, :-k]
    return out


def roll_k(a, k):
    return lag(rolling_sum(a, k, axis=-1).astype(np.float32), 1)


def xs_demean(W, tr):
    W = np.where(tr, W, 0.0)
    n = tr.sum(0)
    m = np.where(n > 0, W.sum(0) / np.maximum(n, 1), 0.0)
    return np.where(tr, W - m[None, :], 0.0)


def gross1(W):
    s = np.abs(W).sum(0)
    return np.where(s > 0, W / np.maximum(s, 1e-12), 0.0).astype(np.float32)


def rank_xs(X, tr):
    S = tr.shape[0]
    order = np.argsort(np.argsort(np.where(tr, X, -1e30), axis=0), axis=0).astype(np.float32)
    n = tr.sum(0).astype(np.float32)
    rk = order - (S - n)[None, :]                    # masked names sort to the bottom S-n slots
    return np.where(tr & (n[None, :] > 2), 2.0 * rk / np.maximum(n[None, :] - 1, 1) - 1.0, 0.0).astype(np.float32)


class Ctx: pass


def build_ctx(subsample=None, truncate_frac=None):
    """subsample/truncate exist for the LOOKAHEAD AUDIT only.

    truncate_frac replaces everything from that fraction of the sample onward with reversed
    prices. Any config whose weights on the surviving PREFIX change as a result is reading the
    future -- which is exactly how N1 was caught using the leader basket's same-day return.
    """
    z = np.load(PANEL, allow_pickle=True)
    syms = list(z["symbols"]); dates = list(z["dates"])
    C = z["close"]; O = z["open"]; V = z["vol"]; z.close()
    if subsample:
        keep = sorted(set(range(0, len(syms), max(1, len(syms) // subsample)))
                      | {i for i, s in enumerate(syms) if s in set(LEADERS + SECTORS)})
        syms = [syms[i] for i in keep]
        C, O, V = C[keep], O[keep], V[keep]
    if truncate_frac:
        cut = int(C.shape[1] * truncate_frac)
        C = C.copy(); O = O.copy(); V = V.copy()
        C[:, cut:] = C[:, cut:][:, ::-1] * 1.37
        O[:, cut:] = O[:, cut:][:, ::-1] * 1.37
        V[:, cut:] = V[:, cut:][:, ::-1]
    idx = {s: i for i, s in enumerate(syms)}

    lc = np.log(C, out=np.full_like(C, np.nan), where=C > 0)
    lo_ = np.log(O, out=np.full_like(O, np.nan), where=O > 0)
    rcc = np.diff(lc, axis=1).astype(np.float32)                  # close-to-close
    roc = (lc - lo_)[:, 1:].astype(np.float32)                    # open-to-close, same day
    rovn = (lo_[:, 1:] - lc[:, :-1]).astype(np.float32)           # overnight gap
    dates = dates[1:]

    v_cc = np.isfinite(rcc); v_oc = np.isfinite(roc); v_ov = np.isfinite(rovn)
    rcc = np.nan_to_num(rcc); roc = np.nan_to_num(roc); rovn = np.nan_to_num(rovn)

    dv = np.nan_to_num(C[:, 1:] * V[:, 1:]).astype(np.float32)
    adv = lag(rolling_sum(dv, 60, axis=1).astype(np.float32) / 60.0, 1)

    c = Ctx()
    c.syms = syms; c.dates = np.array(dates); c.idx = idx
    c.rcc, c.roc, c.rovn = rcc, roc, rovn
    c.adv = adv
    etfs = set(LEADERS + SECTORS)
    is_etf = np.array([s in etfs for s in syms])
    tr = v_cc & (adv > MIN_DV)
    tr[:, 1:] &= v_cc[:, :-1]
    tr &= ~is_etf[:, None]
    c.tradable = tr
    c.tradable_oc = tr & v_oc & v_ov
    c.design = c.dates < DESIGN_END

    # BTC daily close-to-close aligned onto the equity calendar
    c.rbtc = _btc(c)
    if truncate_frac:                    # the audit must corrupt the crypto leader too
        c.rbtc[int(len(c.rbtc) * truncate_frac):] = c.rbtc[int(len(c.rbtc) * truncate_frac):][::-1] * 1.37

    # trailing 250d beta of every name to every leader (causal)
    c.beta = {}
    for L in LEADERS + SECTORS:
        c.beta[L] = _beta(rcc, rcc[idx[L]], 250)
    c.beta["BTC"] = _beta(rcc, c.rbtc, 250)
    c.beta["CREDIT"] = _beta(rcc, rcc[idx["HYG"]] - rcc[idx["LQD"]], 250)
    c.beta["SIZE"] = _beta(rcc, rcc[idx["IWM"]] - rcc[idx["SPY"]], 250)
    c.beta["SPY_OVN"] = _beta(rovn, rovn[idx["SPY"]], 250)
    return c


def _beta(R, b, w):
    xy = rolling_sum(R * b[None, :], w, axis=1)
    xx = rolling_sum(b * b, w)
    out = np.where(xx[None, :] > 1e-12, xy / np.maximum(xx[None, :], 1e-12), 0.0)
    out[:, :w] = 0.0
    return np.clip(lag(out, 1), -4.0, 4.0).astype(np.float32)


def _btc(c):
    import csv, datetime
    px = {}
    with open(BTCCSV) as f:
        for row in csv.DictReader(f):
            try:
                ts = int(row["ts"])
                # BTC's daily close stamped at 00:00 UTC of day D is the close OF D-1; the value a
                # US session on date D can act on is the one stamped 00:00 UTC of D.
                d = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                px[d] = float(row["close"])
            except (KeyError, ValueError):
                continue
    prev = None; out = np.zeros(len(c.dates), np.float32)
    for i, d in enumerate(c.dates):
        p = px.get(str(d))
        if p and prev: out[i] = np.log(p / prev)
        if p: prev = p
    return out


def make_configs(c):
    F = []
    def add(name, desc, fn, which="cc"):
        F.append((name, desc, fn, which))
    I = c.idx

    # ---- L. index leads its components (close-to-close, next day)
    def spygap(k):
        return lambda c: xs_demean(c.beta["SPY"] * roll_k(c.rcc[I["SPY"]][None, :], k) - roll_k(c.rcc, k), c.tradable)
    add("L1_spy_gap_k1", "each stock is long by how far SPY's beta-implied move yesterday exceeded the stock's own move (index-leads-component catch-up, XS-neutral)", spygap(1))
    add("L2_spy_gap_k2", "same catch-up gap measured over SPY's last 2 days", spygap(2))
    add("L3_spy_gap_k5", "same catch-up gap measured over SPY's last 5 days", spygap(5))
    add("L4_spy_gap_k20", "same catch-up gap over SPY's last 20 days (slow transmission)", spygap(20))
    add("L5_spy_gap_rank", "cross-sectional RANK of the 1-day SPY catch-up gap",
        lambda c: rank_xs(c.beta["SPY"] * roll_k(c.rcc[I["SPY"]][None, :], 1) - roll_k(c.rcc, 1), c.tradable))
    add("L6_spy_gap_FADE", "SIGN-FLIPPED SPY catch-up gap: names that already overshot SPY keep going",
        lambda c: -xs_demean(c.beta["SPY"] * roll_k(c.rcc[I["SPY"]][None, :], 1) - roll_k(c.rcc, 1), c.tradable))
    add("L7_spy_push_beta_xs", "SPY's return yesterday times the stock's beta, XS-demeaned -- pure index transmission with NO own-return term",
        lambda c: xs_demean(c.beta["SPY"] * lag(c.rcc[I["SPY"]])[None, :], c.tradable))
    add("L8_qqq_gap_k1", "same 1-day catch-up gap but with QQQ as the leading index instead of SPY",
        lambda c: xs_demean(c.beta["QQQ"] * roll_k(c.rcc[I["QQQ"]][None, :], 1) - roll_k(c.rcc, 1), c.tradable))

    # ---- M. sector ETF leads its members
    def secgap(k):
        def f(c):
            B = np.stack([c.beta[s] for s in SECTORS])                     # (nsec, S, T)
            best = np.argmax(B, axis=0)                                    # each name's most-loaded sector
            lead = np.stack([roll_k(c.rcc[I[s]][None, :], k)[0] for s in SECTORS])  # (nsec, T)
            bl = np.take_along_axis(B, best[None], 0)[0]
            ld = lead[best, np.arange(c.rcc.shape[1])[None, :]]
            return xs_demean(bl * ld - roll_k(c.rcc, k), c.tradable)
        return f
    add("M1_sector_gap_k1", "each stock's catch-up gap against the sector SPDR it loads most on (1-day lead)", secgap(1))
    add("M2_sector_gap_k5", "same sector-ETF catch-up gap over the last 5 days", secgap(5))
    add("M3_sector_push_only", "the most-loaded sector SPDR's own return yesterday, XS-demeaned -- sector transmission without the own-return term",
        lambda c: xs_demean(np.stack([lag(c.rcc[I[s]]) for s in SECTORS])[
            np.argmax(np.stack([c.beta[s] for s in SECTORS]), axis=0), np.arange(c.rcc.shape[1])[None, :]], c.tradable))

    # ---- N. liquidity / size tier lead-lag inside equities
    def _liqtier(c):
        liq = rank_xs(c.adv, c.tradable)
        top = liq > 0.6
        # the leader basket MUST be lagged: using the same day's basket return is lookahead.
        lead = lag((np.where(top, c.rcc, 0.0).sum(0) / np.maximum(top.sum(0), 1)).astype(np.float32))
        return xs_demean(np.where(liq < 0.0, c.beta["SPY"] * lead[None, :] - lag(c.rcc), 0.0), c.tradable)
    add("N1_liqtier_lead", "the top-liquidity-quintile basket's move yesterday leads the bottom-half-liquidity names' catch-up gap", _liqtier)
    add("N2_size_rotation", "yesterday's IWM-minus-SPY small-vs-large rotation times each name's loading on that spread",
        lambda c: xs_demean(c.beta["SIZE"] * lag(c.rcc[I["IWM"]] - c.rcc[I["SPY"]])[None, :], c.tradable))

    # ---- O. genuine CROSS-ASSET transmission: rates / FX / commodities / credit / vol / crypto / overseas
    def xasset(key, lead_fn, k=1):
        return lambda c: xs_demean(c.beta[key] * roll_k(lead_fn(c)[None, :], k), c.tradable)
    add("O1_rates_lead_TLT", "yesterday's TLT (long-bond) return times each stock's trailing rate beta, XS-demeaned",
        xasset("TLT", lambda c: c.rcc[I["TLT"]]))
    add("O2_usd_lead_UUP", "yesterday's UUP (dollar index) return times each stock's trailing dollar beta",
        xasset("UUP", lambda c: c.rcc[I["UUP"]]))
    add("O3_oil_lead_USO", "yesterday's USO (crude) return times each stock's trailing oil beta",
        xasset("USO", lambda c: c.rcc[I["USO"]]))
    add("O4_credit_lead_HYGLQD", "yesterday's HYG-minus-LQD credit-spread return times each stock's loading on it",
        xasset("CREDIT", lambda c: c.rcc[I["HYG"]] - c.rcc[I["LQD"]]))
    add("O5_vol_lead_VIXY", "yesterday's VIXY return times each stock's trailing vol beta",
        xasset("VIXY", lambda c: c.rcc[I["VIXY"]]))
    add("O6_gold_lead_GLD", "yesterday's GLD return times each stock's trailing gold beta",
        xasset("GLD", lambda c: c.rcc[I["GLD"]]))
    add("O7_btc_lead_equity", "yesterday's Bitcoin (Bitstamp spot) return times each stock's trailing BTC beta -- crypto-to-equity transmission",
        xasset("BTC", lambda c: c.rbtc))
    add("O8_overseas_lead", "yesterday's EFA+EWJ+FXI overseas-session basket return times each stock's EFA beta -- the foreign close leads the US open",
        xasset("EFA", lambda c: (c.rcc[I["EFA"]] + c.rcc[I["EWJ"]] + c.rcc[I["FXI"]]) / 3.0))
    add("O9_rates_lead_5d", "TLT's last 5 days times the stock's rate beta (slower rates transmission)",
        xasset("TLT", lambda c: c.rcc[I["TLT"]], 5))
    add("O10_xasset_composite", "sum of the TLT, UUP, USO, credit and VIXY one-day transmission signals (composite cross-asset push)",
        lambda c: xs_demean(sum(c.beta[k] * roll_k(v(c)[None, :], 1) for k, v in
                                (("TLT", lambda c: c.rcc[I["TLT"]]), ("UUP", lambda c: c.rcc[I["UUP"]]),
                                 ("USO", lambda c: c.rcc[I["USO"]]), ("CREDIT", lambda c: c.rcc[I["HYG"]] - c.rcc[I["LQD"]]),
                                 ("VIXY", lambda c: c.rcc[I["VIXY"]]))), c.tradable))

    # ---- P. overnight leads intraday (uses the open, so it is same-day and genuinely causal)
    add("P1_spyovn_leads_oc", "SPY's OVERNIGHT gap times each stock's overnight beta, held from today's open to today's close",
        lambda c: xs_demean(c.beta["SPY_OVN"] * c.rovn[I["SPY"]][None, :], c.tradable_oc), which="oc")
    add("P2_ovn_gap_reversal", "the stock's own overnight gap minus its beta-implied share of SPY's gap, faded from open to close (idiosyncratic overnight overreaction)",
        lambda c: -xs_demean(c.rovn - c.beta["SPY_OVN"] * c.rovn[I["SPY"]][None, :], c.tradable_oc), which="oc")
    add("P3_ovn_gap_momentum", "the SAME idiosyncratic overnight gap traded with the opposite sign (continuation instead of reversal)",
        lambda c: xs_demean(c.rovn - c.beta["SPY_OVN"] * c.rovn[I["SPY"]][None, :], c.tradable_oc), which="oc")
    add("P4_overseas_leads_oc", "the overseas basket's close-to-close move yesterday, times EFA beta, traded US open-to-close today",
        lambda c: xs_demean(c.beta["EFA"] * lag((c.rcc[I["EFA"]] + c.rcc[I["EWJ"]] + c.rcc[I["FXI"]]) / 3.0)[None, :], c.tradable_oc), which="oc")
    # NOTE: the Bitstamp daily close is stamped at 23:59 UTC, i.e. AFTER the US close, so rbtc[t]
    # is NOT knowable at day t's open. It is lagged one day here; anything else is lookahead.
    add("P5_btcovn_leads_oc", "Bitcoin's most recent completed UTC-day move (crypto trades while the US is shut) times BTC beta, held US open-to-close",
        lambda c: xs_demean(c.beta["BTC"] * lag(c.rbtc)[None, :], c.tradable_oc), which="oc")

    # ---- Q. reverse direction: the breadth of the components leads the index
    add("Q1_breadth_leads_spy", "trade SPY ALONE on yesterday's gap between the equal-weight liquid universe and SPY itself (components lead the index)",
        lambda c: (lambda W: W)(_spy_only(c, lambda c: lag((np.where(c.tradable, c.rcc, 0.0).sum(0) / np.maximum(c.tradable.sum(0), 1)).astype(np.float32) - c.rcc[I["SPY"]]))))
    add("Q2_smh_leads_spy", "trade SPY alone on yesterday's SMH-minus-SPY gap (semis as the cyclical bellwether leading the tape)",
        lambda c: _spy_only(c, lambda c: lag(c.rcc[I["SMH"]] - c.rcc[I["SPY"]])))
    add("Q3_credit_leads_spy", "trade SPY alone on yesterday's HYG-minus-LQD credit-spread move (credit leads equity)",
        lambda c: _spy_only(c, lambda c: lag(c.rcc[I["HYG"]] - c.rcc[I["LQD"]])))
    return F


def _spy_only(c, sig_fn):
    W = np.zeros_like(c.rcc)
    W[c.idx["SPY"]] = sig_fn(c)
    return W


def score(c, W, which):
    tr = c.tradable_oc if which == "oc" else c.tradable
    if which == "cc":
        tr = tr | (np.arange(W.shape[0])[:, None] == c.idx["SPY"])   # SPY-only configs may hold SPY
    W = gross1(np.where(tr, W, 0.0))
    r = c.roc if which == "oc" else c.rcc
    pr = np.einsum("it,it->t", W, r).astype(np.float64)
    dW = np.abs(W - lag(W, 1)).sum(0)
    cost = dW * (COST_BP_PER_SIDE * 1e-4)
    d = c.design
    ann = np.sqrt(252.0)

    def sh(x, m):
        x = x[m]; x = x[np.isfinite(x)]
        return 0.0 if x.size < 100 or x.std() == 0 else float(x.mean() / x.std() * ann)

    return dict(n_bars=int(d.sum()),
                gross_sharpe=sh(pr, d), net_sharpe=sh(pr - cost, d),
                gross_bp_per_day=float(pr[d].mean() * 1e4),
                turnover_per_day=float(dW[d].mean()),
                cost_bp_per_day=float(cost[d].mean() * 1e4),
                holdout_gross_sharpe=sh(pr, ~d), holdout_net_sharpe=sh(pr - cost, ~d)), W


def null_sharpes(c, W, which, shifts):
    r = c.roc if which == "oc" else c.rcc
    d = c.design; ann = np.sqrt(252.0); out = []
    for s in shifts:
        if s > 0:
            pr = np.einsum("it,it->t", W[:, :-s], r[:, s:]); m = d[:-s]
        else:
            k = -s
            pr = np.einsum("it,it->t", W[:, k:], r[:, :-k]); m = d[k:]
        x = pr[m].astype(np.float64)
        out.append(0.0 if x.size < 100 or x.std() == 0 else float(x.mean() / x.std() * ann))
    return out


def main():
    t0 = time.time()
    c = build_ctx()
    print(f"ctx {c.rcc.shape} tradable/day={c.tradable.sum(0).mean():.0f} dates {c.dates[0]}..{c.dates[-1]} "
          f"design={c.design.sum()} holdout={(~c.design).sum()} ({time.time()-t0:.0f}s)", flush=True)
    T = c.rcc.shape[1]
    sh = rng.integers(5, T // 8, size=N_NULL // 2)
    shifts = np.concatenate([sh, -sh])

    results, nulls = [], []
    for name, desc, fn, which in make_configs(c):
        try:
            W = fn(c)
        except Exception as e:
            print(f"  {name}: BUILD FAILED {type(e).__name__} {e}", flush=True); continue
        res, W = score(c, W, which)
        res.update(name=name, formula_desc=desc, ret_leg=which)
        results.append(res)
        nulls.append(null_sharpes(c, W, which, shifts))
        print(f"  {name:24s} gross={res['gross_sharpe']:+6.2f} net={res['net_sharpe']:+7.2f} "
              f"tno={res['turnover_per_day']:.3f} bp/d={res['gross_bp_per_day']:+.2f}", flush=True)
        del W

    NULL = np.array(nulls)
    maxnull = NULL.max(axis=0)
    out = dict(block="us_equity_daily_leadlag", panel=PANEL,
               design_window=["2016-01-05", "2021-12-31"], holdout_window=["2022-01-03", "2026-08-14"],
               cost_bp_per_side=COST_BP_PER_SIDE,
               cost_provenance="B22B MEASURED full quoted spread p50=3bp on this liquidity band -> 1.5bp half-spread, plus a 3.5bp impact rung (STRESS_LADDER).",
               known_bias="t17 universe comes from a CURRENT broker asset list: delisted names absent (survivorship). All formulas are dollar-neutral and XS-demeaned, which absorbs most of it.",
               n_formulas=len(results),
               null=dict(n_draws=int(NULL.shape[1]),
                         method="time-shifted returns (>=5 days, both signs), one shared shift per draw so cross-config correlation is preserved",
                         sd_single_config_sharpe=float(NULL.std()),
                         expected_max_sharpe=float(maxnull.mean()),
                         p95_max_sharpe=float(np.percentile(maxnull, 95)),
                         naive_sqrt2lnN=float(np.sqrt(2 * np.log(max(len(results), 2))) * NULL.std())),
               results=sorted(results, key=lambda r: -abs(r["gross_sharpe"])))
    json.dump(out, open(OUTJ, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "results"}, indent=1))
    print("WROTE", OUTJ)


if __name__ == "__main__":
    main()
