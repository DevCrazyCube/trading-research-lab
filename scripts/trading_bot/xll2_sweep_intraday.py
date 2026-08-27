#!/usr/bin/env python3
"""XLL-2, block A: WIDE sweep of INTRADAY (5-minute) cross-asset / cross-listing lead-lag
on the cached rv_cache US panel (122 ETFs + mega-caps, 2021-01-04 .. 2026-08-14, RTH only).

Why this block exists: the first XLL sweep (research/trading_bot/SWEEP_xll_leadlag.md, 74
formulas) covered US equities at a DAILY frequency and crypto perps at 5m. The intraday
transmission channels -- index -> component inside the session, sector ETF -> member,
ETF <-> its creation basket, clone/dual-listed pairs, leveraged-vs-base, rates/credit/
commodity -> equity inside the day, and the US tape -> foreign ETFs whose underlying market
is CLOSED -- were never tested. That is what this does.

Discipline (identical to the first sweep):
  * every formula scored on a DESIGN window only; the held-out window is computed by the same
    code path but never used to pick anything;
  * the noise bar is EMPIRICAL: time-shifted returns, one shared shift per draw across all
    configs, so the max-over-configs bar respects how correlated these formulas are;
  * execution is deliberately un-idealised: the signal is built from CLOSES through bar t and
    the position is held over open[t+1] -> open[t+2]. One full bar of air between the last
    price the signal sees and the price it trades at. This is what kills the 5-minute
    bid-ask-bounce artefact that dominated the crypto block of the first sweep.
  * Sharpe is computed on the SESSION-aggregated P&L series (not on overlapping bar P&L),
    so smoothed/held positions cannot inflate it.
  * costs are per-side, per-symbol, tiered by trailing dollar volume.

KNOWN BIASES, stated up front:
  * the 122-name universe is a CURRENT list of liquid ETFs/mega-caps -> survivorship. Every
    formula is dollar-neutral and cross-sectionally demeaned, which absorbs most of it, but a
    name that died between 2021 and 2026 is simply absent.
  * bars are consolidated (SIP) 5-minute aggregates; a real fill inside the bar is not modelled
    beyond the flat per-side cost tier.
"""
from __future__ import annotations
import json, os, time
import numpy as np

ROOT = "/home/anont/meme"
PANEL = f"{ROOT}/research/data/xll2_cache/intraday5m_panel.npz"
OUTJ = f"{ROOT}/research/trading_bot/SWEEP_xll_leadlag_v2_intraday.json"
AUDIT_DIR = os.environ.get("XLL2_AUDIT_DIR", "/tmp/xll2_audit")

DESIGN_END = "2025-01-01"          # design 2021-01-04 .. 2024-12-31 ; holdout 2025-01-02 .. 2026-08-14
N_NULL = 200
BARS_PER_DAY = 78
BETA_W = 12 * BARS_PER_DAY         # ~12 sessions of 5m bars, causal
rng = np.random.default_rng(20260820)

# ---- universes -------------------------------------------------------------
INDEX = ["SPY", "QQQ", "IWM"]
SECTORS = ["XLB", "XLC", "XLE", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
VSECTORS = {"XLB": "VAW", "XLE": "VDE", "XLI": "VIS", "XLK": "VGT", "XLP": "VDC",
            "XLU": "VPU", "XLV": "VHT", "XLY": "VCR"}          # near-identical exposure, different ETF
MACRO = ["TLT", "IEF", "SHY", "HYG", "LQD", "JNK", "GLDM", "IAU", "SLV", "USO", "UNG", "VNQ"]
FOREIGN = ["EEM", "EFA", "EWJ", "EWZ", "FXI", "IEFA", "IEMG", "VEA"]
STOCKS = ["AAPL", "ABBV", "AMD", "AMZN", "AVGO", "BAC", "BRK_B", "COST", "CSCO", "CVX",
          "GOOG", "GOOGL", "INTC", "JNJ", "JPM", "KO", "LLY", "MA", "META", "MRK",
          "MSFT", "NFLX", "NVDA", "PEP", "TSLA", "UNH", "V", "WMT", "XOM"]
SEMIS = ["NVDA", "AMD", "AVGO", "INTC"]
# clone groups: different tickers, essentially the same exposure
CLONES = [["SPY", "IVV", "VOO", "SPLG"], ["QQQ", "QQQM"], ["ITOT", "SCHB", "VTI", "IWB"],
          ["EFA", "IEFA", "VEA"], ["EEM", "IEMG"], ["GLDM", "IAU"], ["SMH", "SOXX"],
          ["IJH", "MDY"], ["IWM", "VTWO", "VB"], ["GOOG", "GOOGL"]]
# leveraged / inverse ETF -> (base, multiple)
LEV = {"SSO": ("SPY", 2.0), "UPRO": ("SPY", 3.0), "SDS": ("SPY", -2.0), "SH": ("SPY", -1.0),
       "QLD": ("QQQ", 2.0), "TQQQ": ("QQQ", 3.0), "SQQQ": ("QQQ", -3.0), "PSQ": ("QQQ", -1.0),
       "TNA": ("IWM", 3.0), "TZA": ("IWM", -3.0), "TMF": ("TLT", 3.0), "TMV": ("TLT", -3.0)}
SECTOR_OF = {  # member -> the sector SPDR it belongs to (GICS, fixed a priori, not fitted)
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AVGO": "XLK", "AMD": "XLK", "INTC": "XLK",
    "CSCO": "XLK", "V": "XLK", "MA": "XLK",
    "AMZN": "XLY", "TSLA": "XLY", "COST": "XLP", "WMT": "XLP", "KO": "XLP", "PEP": "XLP",
    "GOOG": "XLC", "GOOGL": "XLC", "META": "XLC", "NFLX": "XLC",
    "JPM": "XLF_NA", "BAC": "XLF_NA", "BRK_B": "XLF_NA",   # no XLF in the cache -> VFH used
    "JNJ": "XLV", "ABBV": "XLV", "MRK": "XLV", "LLY": "XLV", "UNH": "XLV",
    "CVX": "XLE", "XOM": "XLE"}
SECTOR_OF = {k: ("VFH" if v == "XLF_NA" else v) for k, v in SECTOR_OF.items()}

# ---- costs -----------------------------------------------------------------
# PROVENANCE: B22B MEASURED the full quoted spread at p50 = 3bp on a mid-liquidity US band ->
# 1.5bp half-spread there. Tiers below scale that measurement by trailing dollar volume and add
# a STRESS rung for 5-minute impact. This is NOT a measurement of our own fills.
def cost_tier(adv_usd):
    c = np.full(adv_usd.shape, 6.0, np.float32)
    c[adv_usd > 5e7] = 3.5
    c[adv_usd > 3e8] = 2.0
    c[adv_usd > 2e9] = 1.0
    return c


# ---- helpers ---------------------------------------------------------------
def rolling_sum(a, w, axis=-1):
    cs = np.cumsum(a.astype(np.float64), axis=axis)
    out = cs.copy()
    hi = [slice(None)] * a.ndim
    lo = [slice(None)] * a.ndim
    hi[axis] = slice(w, None)
    lo[axis] = slice(None, -w)
    out[tuple(hi)] = cs[tuple(hi)] - cs[tuple(lo)]
    return out


def lag(a, k=1):
    out = np.zeros_like(a)
    if a.ndim == 1:
        out[k:] = a[:-k]
    else:
        out[:, k:] = a[:, :-k]
    return out


def xs_demean(W, tr):
    W = np.where(tr, W, 0.0)
    n = tr.sum(0)
    m = np.where(n > 0, W.sum(0) / np.maximum(n, 1), 0.0)
    return np.where(tr, W - m[None, :], 0.0).astype(np.float32)


def gross1(W):
    s = np.abs(W).sum(0)
    return np.where(s > 0, W / np.maximum(s, 1e-12), 0.0).astype(np.float32)


def rank_xs(X, tr):
    S = tr.shape[0]
    order = np.argsort(np.argsort(np.where(tr, X, -1e30), axis=0), axis=0).astype(np.float32)
    n = tr.sum(0).astype(np.float32)
    rk = order - (S - n)[None, :]
    return np.where(tr & (n[None, :] > 2), 2.0 * rk / np.maximum(n[None, :] - 1, 1) - 1.0, 0.0).astype(np.float32)


def smooth_hold(W, h):
    """Overlapping-portfolio construction: hold each signal h bars by averaging the last h
    weight vectors. Cuts turnover ~h-fold, exactly as a real h-bar hold would."""
    if h <= 1:
        return W
    return (rolling_sum(W, h, axis=1) / float(h)).astype(np.float32)


class Ctx:
    pass


def build_ctx(truncate_frac=None):
    z = np.load(PANEL, allow_pickle=True)
    syms = [str(s) for s in z["symbols"]]
    t = z["t"].astype(np.int64)
    O = z["o"].astype(np.float32)
    C = z["c"].astype(np.float32)
    DV = z["dv"].astype(np.float32)
    z.close()

    if truncate_frac:       # LOOKAHEAD AUDIT ONLY: corrupt the tail, weights on the prefix must not move
        cut = int(C.shape[1] * truncate_frac)
        O = O.copy(); C = C.copy(); DV = DV.copy()
        O[:, cut:] = O[:, cut:][:, ::-1] * 1.37
        C[:, cut:] = C[:, cut:][:, ::-1] * 1.37
        DV[:, cut:] = DV[:, cut:][:, ::-1]

    idx = {s: i for i, s in enumerate(syms)}
    day = (t // 86400).astype(np.int64)
    newday = np.empty(len(day), bool)
    newday[0] = True
    newday[1:] = day[1:] != day[:-1]
    bod = np.zeros(len(day), np.int32)          # bar-of-day
    k = 0
    for i in range(len(day)):
        k = 0 if newday[i] else k + 1
        bod[i] = k
    sess = np.cumsum(newday) - 1
    n_sess = sess[-1] + 1

    lc = np.log(C, out=np.full_like(C, np.nan), where=C > 0)
    lo_ = np.log(O, out=np.full_like(O, np.nan), where=O > 0)

    # close-to-close inside the session (first bar of a session -> 0)
    r = np.zeros_like(lc)
    r[:, 1:] = lc[:, 1:] - lc[:, :-1]
    r[:, newday] = 0.0
    valid_r = np.isfinite(r) & ~newday[None, :]
    r = np.nan_to_num(r).astype(np.float32)

    # EXECUTION leg: signal known at close of bar t -> hold open[t+1] -> open[t+2]
    R = np.zeros_like(lc)
    R[:, :-2] = lo_[:, 2:] - lo_[:, 1:-1]
    ok = np.isfinite(R)
    same = np.zeros(len(day), bool)
    same[:-2] = (day[:-2] == day[1:-1]) & (day[:-2] == day[2:])
    R = np.nan_to_num(R).astype(np.float32)
    exec_ok = ok & same[None, :]

    adv = lag((rolling_sum(DV, 5 * BARS_PER_DAY, axis=1) / (5 * BARS_PER_DAY)).astype(np.float32), 1) * BARS_PER_DAY

    c = Ctx()
    c.syms = syms; c.idx = idx; c.t = t; c.day = day; c.bod = bod
    c.sess = sess; c.n_sess = int(n_sess); c.newday = newday
    c.r = r; c.R = R; c.exec_ok = exec_ok; c.adv = adv
    c.cost_bp = cost_tier(np.nanmedian(np.where(adv > 0, adv, np.nan), axis=1))
    import datetime as _dt
    c.date = np.array([_dt.datetime.fromtimestamp(int(x), _dt.timezone.utc).strftime("%Y-%m-%d") for x in t])
    c.design = c.date < DESIGN_END
    c.sess_design = np.zeros(c.n_sess, bool)
    c.sess_design[sess[c.design]] = True

    base_ok = exec_ok & valid_r & (adv > 2e7)
    have = lambda S: np.array([s in set(S) for s in syms])
    c.u_stock = base_ok & have(STOCKS)[:, None]
    c.u_sector = base_ok & have(SECTORS + list(VSECTORS.values()))[:, None]
    c.u_foreign = base_ok & have(FOREIGN)[:, None]
    c.u_lev = base_ok & have(list(LEV))[:, None]
    c.u_clone = base_ok & have([s for g in CLONES for s in g] +
                               [x for kv in VSECTORS.items() for x in kv])[:, None]
    c.u_any = base_ok
    c.base_ok = base_ok

    # causal betas of everything to a handful of leaders
    def _beta(b):
        xy = rolling_sum(c.r * b[None, :], BETA_W, axis=1)
        xx = rolling_sum(b * b, BETA_W)
        out = np.where(xx[None, :] > 1e-12, xy / np.maximum(xx[None, :], 1e-12), 0.0)
        out[:, :BETA_W] = 0.0
        return np.clip(lag(out.astype(np.float32), 1), -4.0, 4.0)

    c.beta = {}
    for L in ["SPY", "QQQ", "IWM", "TLT", "USO", "GLDM"] + SECTORS + ["VFH"]:
        c.beta[L] = _beta(c.r[idx[L]])
    c.beta["CREDIT"] = _beta(c.r[idx["HYG"]] - c.r[idx["LQD"]])
    c.beta["CURVE"] = _beta(c.r[idx["TLT"]] - c.r[idx["SHY"]])
    # trailing vol of each name (causal), for risk-parity variants
    c.vol = np.sqrt(np.maximum(lag((rolling_sum(c.r ** 2, 5 * BARS_PER_DAY, axis=1) /
                                    (5 * BARS_PER_DAY)).astype(np.float32), 1), 1e-12))
    return c


def roll_k(a, k):
    """sum of the last k COMPLETED bars, ending at bar t (inclusive) -- causal at bar t."""
    return rolling_sum(a, k, axis=-1).astype(np.float32)


def armed(c, k):
    return (c.bod >= k)[None, :]


# ---------------------------------------------------------------------------
def make_configs(c):
    F = []
    I = c.idx

    def add(name, desc, fn, hold=1):
        F.append((name, desc, fn, hold))

    # ===== A. index leads its components, INSIDE the session ================
    def spygap(k, lead="SPY", uni="u_stock", sign=+1.0, beta1=False, rank=False, vs=False):
        def f(c):
            B = np.ones_like(c.r) if beta1 else c.beta[lead]
            g = B * roll_k(c.r[I[lead]][None, :], k) - roll_k(c.r, k)
            g = g * armed(c, k)
            if vs:
                g = g / c.vol
            u = getattr(c, uni)
            return sign * (rank_xs(g, u) if rank else xs_demean(g, u))
        return f

    add("A1_spygap_k1_h1", "index-leads-component catch-up: how far SPY's beta-implied 5m move exceeded the stock's own, XS-neutral, held one bar", spygap(1), 1)
    add("A2_spygap_k3_h3", "same catch-up gap over SPY's last 15 minutes, held 15 minutes", spygap(3), 3)
    add("A3_spygap_k12_h12", "same catch-up gap over SPY's last hour, held an hour", spygap(12), 12)
    add("A4_spygap_k39_h39", "same catch-up gap over SPY's last half session, held half a session", spygap(39), 39)
    add("A5_spygap_k12_FADE", "SIGN-FLIPPED hourly catch-up gap: names that already overshot SPY keep going", spygap(12, sign=-1.0), 12)
    add("A6_spypush_beta_xs_h12", "PURE index transmission: SPY's last-hour return times the stock's beta, XS-demeaned, NO own-return term",
        lambda c: xs_demean(c.beta["SPY"] * roll_k(c.r[I["SPY"]][None, :], 12) * armed(c, 12), c.u_stock), 12)
    add("A7_spygap_k12_beta1", "hourly catch-up gap with beta forced to 1 -- no beta estimation at all", spygap(12, beta1=True), 12)
    add("A8_spygap_k12_rank", "cross-sectional RANK of the hourly catch-up gap instead of its size", spygap(12, rank=True), 12)
    add("A9_qqqgap_k12", "hourly catch-up gap against QQQ instead of SPY", spygap(12, lead="QQQ"), 12)
    add("A10_spygap_k12_volscaled", "hourly catch-up gap divided by the name's trailing 5-day vol (risk-parity legs)", spygap(12, vs=True), 12)

    # ===== B. sector ETF leads its members ==================================
    def secgap(k, push_only=False, rot=False):
        def f(c):
            lead = np.zeros_like(c.r)
            B = np.zeros_like(c.r)
            for s, sec in SECTOR_OF.items():
                if s not in I or sec not in I:
                    continue
                lead[I[s]] = roll_k(c.r[I[sec]][None, :], k)[0]
                B[I[s]] = c.beta[sec][I[s]]
            if rot:
                rotv = np.zeros_like(c.r)
                spy = roll_k(c.r[I["SPY"]][None, :], k)[0]
                for s, sec in SECTOR_OF.items():
                    if s in I and sec in I:
                        rotv[I[s]] = roll_k(c.r[I[sec]][None, :], k)[0] - spy
                return xs_demean(B * rotv * armed(c, k), c.u_stock)
            g = B * lead if push_only else (B * lead - roll_k(c.r, k))
            return xs_demean(g * armed(c, k), c.u_stock)
        return f

    add("B1_sectorgap_k3_h3", "each stock's 15-minute catch-up gap against its own GICS sector SPDR", secgap(3), 3)
    add("B2_sectorgap_k12_h12", "same sector-SPDR catch-up gap over the last hour", secgap(12), 12)
    add("B3_sectorpush_only_h12", "the sector SPDR's own last-hour return times the member's sector beta -- sector transmission with NO own-return term", secgap(12, push_only=True), 12)
    add("B4_sector_rotation_h12", "sector-minus-SPY rotation over the last hour times the member's sector loading (rotation transmission)", secgap(12, rot=True), 12)

    # ===== C. the components lead the wrapper (reverse direction) ===========
    def one_name(target, sig_fn):
        def f(c):
            W = np.zeros_like(c.r)
            W[I[target]] = sig_fn(c) * c.base_ok[I[target]]
            return W
        return f

    def basket_gap(target, members, k, sign=+1.0):
        def sig(c):
            m = [I[s] for s in members if s in I]
            bas = roll_k(c.r[m].mean(0)[None, :], k)[0]
            return sign * (bas - roll_k(c.r[I[target]][None, :], k)[0]) * armed(c, k)[0]
        return one_name(target, sig)

    add("C1_breadth_leads_spy_k3", "trade SPY ALONE on the 15-minute gap between the equal-weight mega-cap basket and SPY itself (components lead the index)", basket_gap("SPY", STOCKS, 3), 3)
    add("C2_breadth_leads_spy_k12", "same breadth-leads-index gap over the last hour", basket_gap("SPY", STOCKS, 12), 12)
    add("C3_xlk_vs_members_k3", "trade XLK alone on the 15-minute gap between its equal-weight mega-cap members and the ETF (creation-basket lead-lag)", basket_gap("XLK", [s for s, v in SECTOR_OF.items() if v == "XLK"], 3), 3)
    add("C4_smh_vs_semis_k3", "trade SMH alone on the 15-minute gap between the equal-weight semis (NVDA/AMD/AVGO/INTC) and the ETF", basket_gap("SMH", SEMIS, 3), 3)
    add("C5_semis_lead_spy_k12", "trade SPY alone on the last hour of SMH-minus-SPY (semis as the cyclical bellwether leading the tape)",
        one_name("SPY", lambda c: (roll_k(c.r[I["SMH"]][None, :], 12)[0] - roll_k(c.r[I["SPY"]][None, :], 12)[0]) * armed(c, 12)[0]), 12)
    add("C6_credit_leads_spy_k12", "trade SPY alone on the last hour of the HYG-minus-LQD credit-spread move (credit leads equity)",
        one_name("SPY", lambda c: (roll_k(c.r[I["HYG"]][None, :], 12)[0] - roll_k(c.r[I["LQD"]][None, :], 12)[0]) * armed(c, 12)[0]), 12)
    add("C7_rates_lead_spy_k12", "trade SPY alone on TLT's last hour (rates transmission into the index, sign: bonds up -> equity up)",
        one_name("SPY", lambda c: roll_k(c.r[I["TLT"]][None, :], 12)[0] * armed(c, 12)[0]), 12)
    add("C8_smallcap_leads_spy_k12", "trade SPY alone on the last hour of IWM-minus-SPY (small caps as the risk-appetite tell)",
        one_name("SPY", lambda c: (roll_k(c.r[I["IWM"]][None, :], 12)[0] - roll_k(c.r[I["SPY"]][None, :], 12)[0]) * armed(c, 12)[0]), 12)

    # ===== D. clone / dual-listed pairs: one wrapper leads the other ========
    def clonegap(k, sign=+1.0, groups=None):
        gs = groups if groups is not None else CLONES
        def f(c):
            W = np.zeros_like(c.r)
            for g in gs:
                m = [I[s] for s in g if s in I]
                if len(m) < 2:
                    continue
                rk = roll_k(c.r[m], k)
                grp = rk.mean(0, keepdims=True)
                W[m] = sign * (grp - rk) * armed(c, k)      # long whoever lagged the clone group
            return xs_demean(W, c.u_clone)
        return f

    add("D1_clonegap_k1_h1", "clone/dual-listed ETF pairs (SPY-IVV-VOO-SPLG, QQQ-QQQM, GLDM-IAU, SMH-SOXX, GOOG-GOOGL, ...): long whichever leg lagged its group over the last 5 minutes", clonegap(1), 1)
    add("D2_clonegap_k3_h3", "same clone-group convergence over 15 minutes", clonegap(3), 3)
    add("D3_clonegap_k12_h12", "same clone-group convergence over an hour", clonegap(12), 12)
    add("D4_clonegap_k3_FADE", "SIGN-FLIPPED clone gap: the leg that ran ahead of its clones keeps running (divergence, not convergence)", clonegap(3, sign=-1.0), 3)
    add("D5_dualclass_goog_k3", "the GOOG/GOOGL dual-class pair alone: long the share class that lagged over 15 minutes", clonegap(3, groups=[["GOOG", "GOOGL"]]), 3)
    add("D6_vanguard_vs_spdr_k3", "Vanguard sector ETF vs its SPDR twin (VGT-XLK, VDE-XLE, ...): long whichever twin lagged over 15 minutes",
        clonegap(3, groups=[[a, b] for a, b in VSECTORS.items()]), 3)

    # ===== E. leveraged / inverse ETF vs its base ==========================
    def levgap(k, sign=+1.0, inverse_only=False):
        def f(c):
            W = np.zeros_like(c.r)
            for lv, (base, mult) in LEV.items():
                if lv not in I or base not in I:
                    continue
                if inverse_only and mult > 0:
                    continue
                if (not inverse_only) and mult < 0:
                    continue
                implied = mult * roll_k(c.r[I[base]][None, :], k)[0]
                W[I[lv]] = sign * (implied - roll_k(c.r[I[lv]][None, :], k)[0]) * armed(c, k)[0]
            return xs_demean(W, c.u_lev)
        return f

    add("E1_levgap_k3_h3", "leveraged ETFs (SSO/UPRO/QLD/TQQQ/TNA/TMF): long by how far the base index's L-times-implied 15m move exceeded the leveraged ETF's own", levgap(3), 3)
    add("E2_levgap_k12_h12", "same leveraged-vs-base tracking gap over an hour", levgap(12), 12)
    add("E3_invgap_k3_h3", "same construction on the INVERSE ETFs (SH/SDS/PSQ/SQQQ/TZA/TMV)", levgap(3, inverse_only=True), 3)
    add("E4_levgap_k3_FADE", "SIGN-FLIPPED leveraged tracking gap (divergence continues)", levgap(3, sign=-1.0), 3)

    # ===== F. genuine cross-asset transmission INSIDE the session ==========
    def xasset(key, lead_fn, k=12, uni="u_stock"):
        return lambda c: xs_demean(c.beta[key] * roll_k(lead_fn(c)[None, :], k) * armed(c, k), getattr(c, uni))

    add("F1_rates_push_k12", "TLT's last hour times each stock's trailing rate beta, XS-demeaned", xasset("TLT", lambda c: c.r[I["TLT"]]), 12)
    add("F2_credit_push_k12", "the HYG-minus-LQD credit move over the last hour times each stock's credit loading", xasset("CREDIT", lambda c: c.r[I["HYG"]] - c.r[I["LQD"]]), 12)
    add("F3_oil_push_k12", "USO's last hour times each stock's trailing oil beta", xasset("USO", lambda c: c.r[I["USO"]]), 12)
    add("F4_gold_push_k12", "GLDM's last hour times each stock's trailing gold beta", xasset("GLDM", lambda c: c.r[I["GLDM"]]), 12)
    add("F5_curve_push_k12", "the TLT-minus-SHY yield-curve move over the last hour times each stock's curve loading", xasset("CURVE", lambda c: c.r[I["TLT"]] - c.r[I["SHY"]]), 12)
    add("F6_macro_composite_k12", "sum of the rates, credit, oil, gold and curve one-hour transmission signals (composite cross-asset push)",
        lambda c: xs_demean(sum(c.beta[k_] * roll_k(v(c)[None, :], 12) for k_, v in
                                (("TLT", lambda c: c.r[I["TLT"]]), ("CREDIT", lambda c: c.r[I["HYG"]] - c.r[I["LQD"]]),
                                 ("USO", lambda c: c.r[I["USO"]]), ("GLDM", lambda c: c.r[I["GLDM"]]),
                                 ("CURVE", lambda c: c.r[I["TLT"]] - c.r[I["SHY"]]))) * armed(c, 12), c.u_stock), 12)
    add("F7_rates_push_k3", "the same rates transmission at a 15-minute lead window (fast channel)", xasset("TLT", lambda c: c.r[I["TLT"]], 3), 3)

    # ===== G. the US tape leads foreign ETFs whose underlying market is SHUT
    def forgap(k, push_only=False, sign=+1.0):
        def f(c):
            lead = roll_k(c.r[I["SPY"]][None, :], k)
            g = c.beta["SPY"] * lead if push_only else (c.beta["SPY"] * lead - roll_k(c.r, k))
            return sign * xs_demean(g * armed(c, k), c.u_foreign)
        return f

    add("G1_foreign_spygap_k3", "foreign-market ETFs (EEM/EFA/EWJ/EWZ/FXI/...) whose underlying exchange is CLOSED: catch-up gap to SPY's last 15 minutes", forgap(3), 3)
    add("G2_foreign_spygap_k12", "same US-leads-foreign catch-up gap over the last hour", forgap(12), 12)
    add("G3_foreign_spypush_k12", "PURE US-to-foreign transmission: SPY's last hour times the ETF's SPY beta, no own-return term", forgap(12, push_only=True), 12)
    add("G4_foreign_spygap_FADE", "SIGN-FLIPPED US-leads-foreign gap", forgap(12, sign=-1.0), 12)
    add("G5_foreign_leads_spy_k12", "reverse: trade SPY alone on the last hour of the equal-weight foreign-ETF basket minus SPY",
        basket_gap("SPY", FOREIGN, 12), 12)

    # ===== H. session-clock conditioners on one fixed structural family ====
    def timed(lo, hi, k=12):
        base = spygap(k)
        def f(c):
            W = base(c)
            m = ((c.bod >= lo) & (c.bod < hi))[None, :]
            return (W * m).astype(np.float32)
        return f

    add("H1_spygap_open30", "the hourly catch-up gap traded only in the first 30 minutes of the session", timed(12, 18), 12)
    add("H2_spygap_close30", "the hourly catch-up gap traded only in the last 30 minutes of the session", timed(BARS_PER_DAY - 8, BARS_PER_DAY), 12)
    add("H3_spygap_midday", "the hourly catch-up gap traded only between 11:00 and 15:00 ET (midday only)", timed(18, BARS_PER_DAY - 12), 12)

    # ===== I. state conditioners ==========================================
    def cond_bigmove(k=12, calm=False):
        base = spygap(k)
        def f(c):
            W = base(c)
            lead = roll_k(c.r[I["SPY"]][None, :], k)[0]
            sd = np.sqrt(np.maximum(lag(rolling_sum(c.r[I["SPY"]] ** 2, 5 * BARS_PER_DAY) / (5 * BARS_PER_DAY), 1), 1e-14)) * np.sqrt(k)
            big = np.abs(lead) > 2.0 * sd
            m = (~big if calm else big)[None, :]
            return (W * m).astype(np.float32)
        return f

    add("I1_spygap_bigmove_only", "the hourly catch-up gap armed only when SPY's last hour exceeded 2 trailing sigma", cond_bigmove(), 12)
    add("I2_spygap_calm_only", "the complement: the hourly catch-up gap armed only on CALM hours", cond_bigmove(calm=True), 12)

    return F


# ---------------------------------------------------------------------------
def sess_pnl(c, x):
    """aggregate a per-bar series into one number per session"""
    return np.bincount(c.sess, weights=x, minlength=c.n_sess)


def score(c, W, hold):
    W = smooth_hold(W, hold)
    if hold > 1:
        # the h-bar averaging window must lie entirely inside the session: no weight is carried
        # across the overnight gap, so the book is genuinely flat at every close.
        W = W * (c.bod >= hold - 1)[None, :]
    W = gross1(np.where(c.base_ok, W, 0.0))
    pr = np.einsum("it,it->t", W, c.R).astype(np.float64)
    dW = np.abs(W - lag(W, 1))
    cost = (dW * (c.cost_bp[:, None] * 1e-4)).sum(0).astype(np.float64)
    tno = dW.sum(0).astype(np.float64)

    g = sess_pnl(c, pr); n = sess_pnl(c, pr - cost)
    tn = sess_pnl(c, tno); cs = sess_pnl(c, cost)
    d = c.sess_design
    ann = np.sqrt(252.0)

    def sh(x, m):
        x = x[m]
        x = x[np.isfinite(x)]
        return 0.0 if x.size < 60 or x.std() == 0 else float(x.mean() / x.std() * ann)

    gd = g[d]
    be = float(gd.mean() / max(tn[d].mean(), 1e-12) * 1e4) if tn[d].mean() > 0 else 0.0
    ge = g[~d]
    be_h = float(ge.mean() / max(tn[~d].mean(), 1e-12) * 1e4) if tn[~d].mean() > 0 else 0.0
    return dict(n_sessions=int(d.sum()),
                gross_sharpe=sh(g, d), net_sharpe=sh(n, d),
                gross_bp_per_day=float(gd.mean() * 1e4),
                turnover_per_day=float(tn[d].mean()),
                cost_bp_per_day=float(cs[d].mean() * 1e4),
                breakeven_bp_per_side_design=be,
                holdout_gross_sharpe=sh(g, ~d), holdout_net_sharpe=sh(n, ~d),
                breakeven_bp_per_side_holdout=be_h), W


def null_sharpes(c, W, shifts):
    d = c.sess_design; ann = np.sqrt(252.0); out = []
    for s in shifts:
        if s > 0:
            pr = np.einsum("it,it->t", W[:, :-s], c.R[:, s:])
            sess = c.sess[:-s]
        else:
            k = -s
            pr = np.einsum("it,it->t", W[:, k:], c.R[:, :-k])
            sess = c.sess[k:]
        g = np.bincount(sess, weights=pr.astype(np.float64), minlength=c.n_sess)[d]
        g = g[np.isfinite(g)]
        out.append(0.0 if g.size < 60 or g.std() == 0 else float(g.mean() / g.std() * ann))
    return out


def main():
    t0 = time.time()
    audit = os.environ.get("XLL2_AUDIT")
    c = build_ctx(truncate_frac=float(audit) if audit else None)
    print(f"ctx syms={len(c.syms)} bars={c.r.shape[1]} sessions={c.n_sess} "
          f"design_sess={c.sess_design.sum()} holdout_sess={(~c.sess_design).sum()} "
          f"({time.time()-t0:.0f}s)", flush=True)
    T = c.r.shape[1]
    base = rng.integers(BARS_PER_DAY, T // 8, size=N_NULL // 2)
    shifts = np.concatenate([base, -base])

    results, nulls = [], []
    for name, desc, fn, hold in make_configs(c):
        try:
            W = fn(c)
        except Exception as e:
            print(f"  {name}: BUILD FAILED {type(e).__name__} {e}", flush=True)
            continue
        res, Wn = score(c, W, hold)
        res.update(name=name, formula_desc=desc, hold_bars=hold)
        results.append(res)
        if audit:
            os.makedirs(AUDIT_DIR, exist_ok=True)
            np.save(f"{AUDIT_DIR}/{name}.npy", Wn[:, :int(T * float(audit))].astype(np.float32))
        else:
            nulls.append(null_sharpes(c, Wn, shifts))
        print(f"  {name:26s} gross={res['gross_sharpe']:+6.2f} net={res['net_sharpe']:+8.2f} "
              f"tno/d={res['turnover_per_day']:6.2f} be={res['breakeven_bp_per_side_design']:5.2f}bp "
              f"({time.time()-t0:.0f}s)", flush=True)
        del W, Wn

    if audit:
        print("AUDIT WEIGHTS DUMPED")
        return

    NULL = np.array(nulls)
    maxnull = NULL.max(axis=0)
    out = dict(block="us_intraday_5m_xasset_leadlag", panel=PANEL,
               design_window=["2021-01-04", "2024-12-31"], holdout_window=["2025-01-02", "2026-08-14"],
               execution="signal from closes through bar t; position held open[t+1]->open[t+2] (one full bar of air); Sharpe on session-aggregated P&L",
               cost_model="per-symbol per-side tier by trailing ADV: >$2B 1.0bp, >$300M 2.0bp, >$50M 3.5bp, else 6.0bp",
               cost_provenance="B22B MEASURED full quoted spread p50=3bp on a mid-liquidity US band -> 1.5bp half-spread; tiers scale that by ADV and add a 5-minute impact rung (STRESS_LADDER). NOT a measurement of our own fills.",
               known_bias="122-name universe is a CURRENT liquid ETF/mega-cap list (survivorship); all formulas dollar-neutral and XS-demeaned, which absorbs most of it.",
               n_formulas=len(results),
               null=dict(n_draws=int(NULL.shape[1]),
                         method="time-shifted returns (>=1 session, both signs), one shared shift per draw so cross-config correlation is preserved",
                         sd_single_config_sharpe=float(NULL.std()),
                         expected_max_sharpe=float(maxnull.mean()),
                         p95_max_sharpe=float(np.percentile(maxnull, 95)),
                         naive_sqrt2lnN=float(np.sqrt(2 * np.log(max(len(results), 2))) * NULL.std())),
               results=sorted(results, key=lambda r: -abs(r["gross_sharpe"])))
    json.dump(out, open(OUTJ, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "results"}, indent=1))
    print("WROTE", OUTJ, f"({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
