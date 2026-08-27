#!/usr/bin/env python3
"""WIDE sweep ROUND 2: futures term structure / roll / seasonality / carry-momentum.

Round 1 (`ts_sweep.py`, 49 formulas) covered: ETF maturity ladders, cross-sectional
and time-series commodity carry, basis momentum, carry x momentum, seasonality,
the VIX curve, the equity-index basis, and rates-curve carry. Verdict: noise
(best +0.80 vs bootstrap E[max] +0.78).

THIS FILE IS NOT A RE-TUNE OF THOSE. Every formula here is in a family round 1
never touched, and the headline addition is a term structure that is **directly
measured** rather than proxied:

  FX FUTURES BASIS.  Yahoo carries both the CME FX future (6E/6J/6B/6A/6C/6S) and
  the matching spot rate (EURUSD=X, ...). log(F/S) IS the forward premium -- the
  observable term structure -- with no ETF-fee offset and no ladder proxy. Divided
  by time-to-IMM-expiry (3rd Wednesday of Mar/Jun/Sep/Dec, computed from the
  calendar, no lookahead) it is an annualised carry. Sanity: JPY 2007 +4.35%/yr,
  AUD 2007 -1.47%, CHF 2024 +3.70% -- the right signs and magnitudes for those
  rate differentials.

  HONESTY FLAG ON THE FX P&L LEG. A long FX-futures total return is
  spot_return + carry/252. The carry term is MODELLED from the same basis the
  signal reads, so a long-high-carry book books that carry by construction. That
  is how forwards actually work (it is not lookahead: basis at t-1 sets the carry
  earned t->t+1), but it means any FX-carry result here is the KNOWN FX carry
  premium being re-measured, not an edge being discovered. Every FX formula is
  therefore also scored SPOT-ONLY (carry leg deleted) and both numbers reported.

Other new families: energy-complex spreads with real ETF legs (Brent-WTI via
BNO/USO, crack via UGA/USO), carry-quality / carry-stability / sector-neutral
transforms, regime overlays (vol gate, dollar trend, vol targeting), roll-window
timing, and new fixed-prior seasonals.

P&L RULE INHERITED FROM ROUND 1 (non-negotiable): `X=F` continuous series are the
front contract's SPLICED PRICE -- the roll yield is deleted from them, so they are
SIGNAL INPUTS ONLY. Every commodity/equity/rates P&L leg is an ETF adjusted close.

USAGE
    python3 scripts/trading_bot/ts_sweep2.py design
    python3 scripts/trading_bot/ts_sweep2.py holdout --names A,B,C
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ts_sweep as ts  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "trading_bot"
THEME = "futures_term_structure_r2"

DESIGN_START, DESIGN_END = ts.DESIGN_START, ts.DESIGN_END
HOLD_START, HOLD_END = ts.HOLD_START, ts.HOLD_END
ANN = ts.ANN

roll_mean, roll_std, zscore, lag, cum_lr = (
    ts.roll_mean, ts.roll_std, ts.zscore, ts.lag, ts.cum_lr)

# --- tradable legs -----------------------------------------------------------
# ETF costs inherited from round 1 (bp per side of turnover, ASSUMED spread-scale).
# FX futures legs added: CME 6E ticks 0.5bp and commission is ~0.2bp of notional,
# so 1.5bp/side is already conservative; the thinner crosses are charged more.
FX_COST_BP = {"FX_EUR": 1.5, "FX_JPY": 1.5, "FX_GBP": 2.0,
              "FX_AUD": 2.5, "FX_CAD": 2.5, "FX_CHF": 3.0}
COST_BP = dict(ts.COST_BP)
COST_BP.update(FX_COST_BP)

# currency -> (futures symbol, spot symbol, invert_spot_to_usd_per_foreign)
FX_PAIRS = [
    ("EUR", "6E=F", "EURUSD=X", False),
    ("JPY", "6J=F", "JPY=X", True),
    ("GBP", "6B=F", "GBPUSD=X", False),
    ("AUD", "6A=F", "AUDUSD=X", False),
    ("CAD", "6C=F", "CAD=X", True),
    ("CHF", "6S=F", "CHF=X", True),
]

# commodity carry panel sectors (indices into ts.CARRY_PAIRS order)
SECTORS = {"energy": [0, 1, 2, 3], "metals": [4, 5, 6, 7], "ags": [8, 9, 10, 11]}


# --- IMM calendar (deterministic, no lookahead) ------------------------------
def _third_wed(y: int, m: int) -> datetime.date:
    d = datetime.date(y, m, 1)
    return d + datetime.timedelta(days=(2 - d.weekday()) % 7 + 14)


def time_to_imm(dates: np.ndarray) -> np.ndarray:
    out = np.empty(len(dates))
    for i, ymd in enumerate(dates):
        d = datetime.date(ymd // 10000, ymd // 100 % 100, ymd % 100)
        t = 0.25
        for y in (d.year, d.year + 1):
            done = False
            for m in (3, 6, 9, 12):
                e = _third_wed(y, m)
                if e > d:
                    t = max((e - d).days, 3) / 365.0
                    done = True
                    break
            if done:
                break
        out[i] = t
    return out


# ---------------------------------------------------------------------------
class Sweep2(ts.Sweep):
    """Round-1 panel + an FX-futures sleeve with a measured basis and a modelled
    carry leg. `carry_mode` picks the FX P&L convention:
        'total'    spot return + basis carry/252   (a real collateralised future)
        'spotonly' spot return only                (carry leg deleted -- robustness)
    """

    def __init__(self, carry_mode: str = "total"):
        self.P = ts.Panel()
        self.T = self.P.T
        self.dates = self.P.dates
        self.carry_mode = carry_mode
        self._build_fx()
        self.assets = sorted(COST_BP)
        self.ai = {a: i for i, a in enumerate(self.assets)}
        self.K = len(self.assets)
        cols = []
        for a in self.assets:
            cols.append(self.FXR[a] if a in FX_COST_BP else self.P.ret(a, adj=True))
        self.R = np.column_stack(cols)
        self.cost = np.array([COST_BP[a] / 1e4 for a in self.assets])
        self._cache = {}
        self._build_carry()

    # -- FX sleeve ----------------------------------------------------------
    def _build_fx(self):
        Tt = time_to_imm(self.dates)
        self.fxnames, self.fxleg = [], []
        basis_cols, carry_cols, clean_cols, spotlr_cols = [], [], [], []
        self.FXR = {}
        for cur, fsym, ssym, inv in FX_PAIRS:
            F = self.P.close.get(fsym)
            Sp = self.P.close.get(ssym)
            if F is None or Sp is None:
                continue
            S = 1.0 / Sp if inv else Sp.copy()
            ok = np.isfinite(F) & np.isfinite(S) & (F > 0) & (S > 0)
            b = np.full(self.T, np.nan)
            b[ok] = np.log(F[ok] / S[ok])
            b[np.abs(b) > 0.05] = np.nan               # bad-print guard
            carry = b / Tt                             # annualised, +ve = fwd premium
            carry = np.clip(carry, -0.25, 0.25)
            slr = np.full(self.T, np.nan)
            slr[1:] = S[1:] / S[:-1] - 1.0
            slr[~np.isfinite(slr)] = np.nan
            slr[np.abs(slr) > 0.25] = np.nan
            # long-foreign-currency future total return.
            # F > S  =>  foreign fwd premium  =>  foreign yields LESS  =>  carry is
            # a DRAG on a long-foreign position, hence the minus sign.
            # STALE-QUOTE CORRECTION (see module docstring / SWEEP md).
            # Yahoo's `=X` spot bar stamps EARLIER than the CME settle, so the raw
            # daily basis contains hours of futures move that spot has not printed
            # yet: corr(basis_t, futret_t) = +0.35 and corr(basis_t, spotret_t+1)
            # = +0.33 -- the same number. That gap is zero-mean and unwinds in one
            # day, while the rate differential is persistent, so a 21d MEAN of the
            # basis keeps the carry and averages the artifact away. Both the P&L
            # accrual and the clean signal (FCS) use the smoothed estimate.
            carry_s = lag(roll_mean(carry, 21), 1)
            tr = slr.copy()
            if self.carry_mode == "total":
                acc = -np.nan_to_num(carry_s, nan=0.0) / ANN
                tr = np.where(np.isfinite(slr), slr + acc, np.nan)
            leg = f"FX_{cur}"
            self.fxnames.append(cur)
            self.fxleg.append(leg)
            self.FXR[leg] = np.nan_to_num(tr, nan=0.0) * np.isfinite(slr)
            basis_cols.append(b)
            carry_cols.append(-carry)                  # carry EARNED by long-foreign
            clean_cols.append(-carry_s)                # stale-corrected version
            spotlr_cols.append(np.where(np.isfinite(slr), np.log1p(np.clip(slr, -0.9, None)), np.nan))
        self.FB = np.column_stack(basis_cols)
        self.FC = np.column_stack(carry_cols)          # RAW basis carry (contaminated)
        self.FCS = np.column_stack(clean_cols)         # 21d-mean basis carry (clean)
        self.FL = np.column_stack(spotlr_cols)
        self.NF = len(self.fxnames)

    # -- generic weight builders -------------------------------------------
    def blank(self):
        return np.zeros((self.T, self.K))

    def xs(self, score, legs, n_side=2, mode="tercile", vol_scale=None):
        """Cross-sectional long/short over an arbitrary leg list."""
        W = self.blank()
        n = len(legs)
        for t in range(self.T):
            row = score[t]
            ok = np.isfinite(row)
            if ok.sum() < 2 * n_side + 1:
                continue
            idx = np.nonzero(ok)[0]
            w = np.zeros(n)
            if mode == "zscore":
                r = row[idx]
                w[idx] = (r - r.mean()) / (r.std() + 1e-12)
            else:
                order = idx[np.argsort(row[idx])]
                ns = min(n_side, len(order) // 2)
                w[order[-ns:]] = 1.0
                w[order[:ns]] = -1.0
            if vol_scale is not None:
                vs = vol_scale[t]
                w = w * np.where(np.isfinite(vs) & (vs > 1e-6), 1.0 / vs, 0.0)
            g = np.abs(w).sum()
            if g < 1e-12:
                continue
            w /= g
            for j in range(n):
                if w[j] != 0.0:
                    W[t, self.ai[legs[j]]] += w[j]
        return W

    def tsw(self, score, legs):
        """Per-name time-series sign, gross-normalised to 1."""
        W = self.blank()
        Sg = np.sign(np.nan_to_num(score, nan=0.0))
        g = np.abs(Sg).sum(axis=1)
        g[g < 1e-12] = np.nan
        Wn = np.nan_to_num(Sg / g[:, None], nan=0.0)
        for j, leg in enumerate(legs):
            W[:, self.ai[leg]] += Wn[:, j]
        return W

    def fxvol(self, k=63):
        return np.column_stack([roll_std(self.FL[:, j], k) for j in range(self.NF)]) * math.sqrt(ANN)

    def fxmom(self, k, skip=0):
        out = []
        for j in range(self.NF):
            c = cum_lr(self.FL[:, j], k)
            out.append(c - cum_lr(self.FL[:, j], skip) if skip else c)
        return np.column_stack(out)


# --- calendar helpers --------------------------------------------------------
def monthly_hold(W, dates):
    """Freeze weights except on the first trading day of each month."""
    ym = dates // 100
    out = np.zeros_like(W)
    cur = np.zeros(W.shape[1])
    prev = -1
    for t in range(len(dates)):
        if ym[t] != prev:
            cur = W[t].copy()
            prev = ym[t]
        out[t] = cur
    return out


def gate(W, mask):
    return W * np.where(np.isfinite(mask) & (mask > 0), 1.0, 0.0)[:, None]


def vol_target(W, S, target=0.10, k=63):
    """Scale gross so the book's own trailing realised vol hits `target`. Causal."""
    g, _, Wf = ts._legs(S, W)
    r = np.concatenate([[np.nan], g])
    sd = roll_std(r, k) * math.sqrt(ANN)
    s = np.where(np.isfinite(sd) & (sd > 1e-3), target / sd, 0.0)
    s = np.clip(lag(s, 1), 0.0, 4.0)
    return W * np.nan_to_num(s, nan=0.0)[:, None]


# ---------------------------------------------------------------------------
def build_formulas(S: Sweep2):
    F = []
    d = S.dates
    mon = ts.month_of(d)
    bdm = ts.bday_of_month(d)

    def add(name, desc, W, group):
        F.append({"name": name, "desc": desc, "W": W, "group": group})

    def put(leg, series):
        W = S.blank()
        W[:, S.ai[leg]] = np.nan_to_num(series, nan=0.0)
        return W

    def pair(long_leg, short_leg, series):
        """Dollar-neutral pair: +s in long_leg, -s in short_leg, gross-1."""
        W = S.blank()
        s = np.nan_to_num(series, nan=0.0) * 0.5
        W[:, S.ai[long_leg]] += s
        W[:, S.ai[short_leg]] -= s
        return W

    def ladder(deferred, front, k=63, z=504):
        """Contango estimate from a maturity-ladder ETF pair; +ve = contango."""
        sp = S.P.lr(deferred) - S.P.lr(front)
        return zscore(roll_mean(sp, k) * ANN, z)

    # ======================= I. FX FUTURES BASIS CARRY ======================
    FXC = S.FC                                    # annualised carry earned long-foreign
    fxz = np.column_stack([zscore(FXC[:, j], 252) for j in range(S.NF)])
    add("I1_FX_XS_CARRY_M",
        "rank 6 CME FX futures by MEASURED basis carry (log(F/S)/T_IMM); long top2 / short bottom2, monthly rebalance",
        monthly_hold(S.xs(FXC, S.fxleg, n_side=2), d), "I_fx_basis")
    add("I2_FX_XS_CARRY_D",
        "DISQUALIFIED ARTIFACT: same rank on the RAW same-day basis, rebalanced DAILY. "
        "Not a carry signal -- Yahoo's =X spot bar stamps before the CME settle, so the raw "
        "basis is a stale-quote gap. Kept in the count as evidence; see I2X.",
        S.xs(FXC, S.fxleg, n_side=2), "I_fx_basis")
    add("I2X_FX_XS_CARRY_D_LAG1",
        "the MECHANISM TEST on I2: identical formula with the signal lagged ONE extra day. "
        "If I2 were carry this barely moves; if it is a stale quote it dies.",
        S.xs(np.column_stack([lag(FXC[:, j], 1) for j in range(S.NF)]), S.fxleg, n_side=2),
        "I_fx_basis")
    add("I3_FX_XS_CARRY_Z",
        "continuous cross-sectional z-score weights on basis carry (no tercile cut), monthly",
        monthly_hold(S.xs(FXC, S.fxleg, mode="zscore"), d), "I_fx_basis")
    add("I4_FX_TS_CARRY",
        "per-currency TIME-SERIES: long if own basis carry z252 > 0, short if < 0",
        monthly_hold(S.tsw(fxz, S.fxleg), d), "I_fx_basis")
    add("I5_FX_CARRY_VOLSCALED",
        "basis-carry rank sized 1/vol63 (risk-parity carry)",
        monthly_hold(S.xs(FXC, S.fxleg, n_side=2, vol_scale=S.fxvol(63)), d), "I_fx_basis")
    add("I6_FX_CARRY_X_MOM",
        "rank by z(basis carry) + z(12-1 spot momentum): carry and trend voting together",
        monthly_hold(S.xs(
            np.column_stack([zscore(FXC[:, j], 504) for j in range(S.NF)])
            + np.column_stack([zscore(S.fxmom(252, 21)[:, j], 504) for j in range(S.NF)]),
            S.fxleg, n_side=2), d), "I_fx_basis")
    add("I7_FX_CARRY_CHANGE",
        "rank by the 63d CHANGE in basis carry (FX basis momentum), not its level",
        monthly_hold(S.xs(FXC - np.column_stack([lag(FXC[:, j], 63) for j in range(S.NF)]),
                          S.fxleg, n_side=2), d), "I_fx_basis")
    add("I8_FX_DOLLAR_CARRY",
        "DOLLAR factor: hold the equal-weight 6-currency basket long when its AVERAGE basis carry z504 > 0, short when < 0",
        monthly_hold(S.tsw(
            np.repeat(zscore(np.nanmean(FXC, axis=1), 504)[:, None], S.NF, axis=1),
            S.fxleg), d), "I_fx_basis")
    _vixz = zscore(np.log(np.maximum(S.P.close.get("^VIX"), 1e-6)), 252)
    add("I9_FX_CARRY_RISKGATE",
        "FX basis carry ON only while log(VIX) z252 < +1 (the carry-crash conditioner), flat otherwise",
        gate(monthly_hold(S.xs(FXC, S.fxleg, n_side=2), d), 1.0 - (_vixz > 1.0)), "I_fx_basis")
    add("I10_FX_CARRY_SLOPE_GATE",
        "FX basis carry sized by how DISPERSED the cross-section is (carry spread top-bottom z504); wide curve = bigger bet",
        monthly_hold(S.xs(FXC, S.fxleg, n_side=2), d)
        * np.clip(zscore(np.nanmax(FXC, axis=1) - np.nanmin(FXC, axis=1), 504), 0, 3)[:, None] / 3.0,
        "I_fx_basis")

    # --- clean FX family: carry from the 21d-MEAN basis (stale gap averaged out) ---
    FXS = S.FCS
    add("I11_FXCLEAN_XS_CARRY_D",
        "STALE-CORRECTED FX carry: rank on the 21d-MEAN basis carry (lagged 1d), rebalanced daily",
        S.xs(FXS, S.fxleg, n_side=2), "I_fx_clean")
    add("I12_FXCLEAN_XS_CARRY_M",
        "stale-corrected FX basis carry rank, monthly rebalance",
        monthly_hold(S.xs(FXS, S.fxleg, n_side=2), d), "I_fx_clean")
    add("I13_FXCLEAN_XS_CARRY_Z",
        "stale-corrected FX carry, continuous cross-sectional z-weights, monthly",
        monthly_hold(S.xs(FXS, S.fxleg, mode="zscore"), d), "I_fx_clean")
    add("I14_FXCLEAN_TS_CARRY",
        "per-currency time-series sign of the stale-corrected carry z252",
        monthly_hold(S.tsw(np.column_stack([zscore(FXS[:, j], 252) for j in range(S.NF)]),
                           S.fxleg), d), "I_fx_clean")
    add("I15_FXCLEAN_CARRY_VOLSCALED",
        "stale-corrected FX carry rank sized 1/vol63 (risk-parity FX carry)",
        monthly_hold(S.xs(FXS, S.fxleg, n_side=2, vol_scale=S.fxvol(63)), d), "I_fx_clean")
    add("I16_FXCLEAN_CARRY_RISKGATE",
        "stale-corrected FX carry, flat whenever log(VIX) z252 > +1 (carry-crash conditioner)",
        gate(monthly_hold(S.xs(FXS, S.fxleg, n_side=2), d), 1.0 - (_vixz > 1.0)), "I_fx_clean")
    add("I17_FXCLEAN_CARRY_X_MOM",
        "stale-corrected FX carry z + 12-1 spot momentum z, ranked jointly, monthly",
        monthly_hold(S.xs(
            np.column_stack([zscore(FXS[:, j], 504) for j in range(S.NF)])
            + np.column_stack([zscore(S.fxmom(252, 21)[:, j], 504) for j in range(S.NF)]),
            S.fxleg, n_side=2), d), "I_fx_clean")

    # ================= J. ENERGY-COMPLEX SPREADS (real ETF legs) ============
    lbno, luso, luga, lung = (S.P.lr("BNO"), S.P.lr("USO"), S.P.lr("UGA"), S.P.lr("UNG"))
    bw = np.nancumsum(np.nan_to_num(lbno - luso, nan=0.0))      # Brent-WTI relative level
    add("J1_BRENT_WTI_REV",
        "Brent-WTI as a tradeable pair: -z252 of the cumulative log BNO/USO spread; fade the stretched leg",
        pair("BNO", "USO", -zscore(bw, 252)), "J_energy_spread")
    add("J2_BRENT_WTI_MOM",
        "same BNO/USO pair but TREND: +sign of the 63d change in the spread",
        pair("BNO", "USO", np.sign(bw - lag(bw, 63))), "J_energy_spread")
    add("J3_BRENT_WTI_CURVE",
        "BNO/USO pair signed by which CURVE is more backwardated: z504 of 63d (BZ=F minus CL=F) drift",
        pair("BNO", "USO", zscore(roll_mean(S.P.lr("BZ=F", adj=False) - S.P.lr("CL=F", adj=False), 63) * ANN, 504)),
        "J_energy_spread")
    ck = np.nancumsum(np.nan_to_num(luga - luso, nan=0.0))       # gasoline crack proxy
    add("J4_CRACK_REV",
        "gasoline crack proxy UGA/USO: -z252 of the cumulative spread (crack mean reversion)",
        pair("UGA", "USO", -zscore(ck, 252)), "J_energy_spread")
    add("J5_CRACK_SEASONAL",
        "fixed prior: long UGA / short USO Feb-May (refinery turnaround into driving season), flip Sep-Dec, flat else",
        pair("UGA", "USO", np.where(np.isin(mon, [2, 3, 4, 5]), 1.0,
                                    np.where(np.isin(mon, [9, 10, 11, 12]), -1.0, 0.0))),
        "J_energy_spread")
    add("J6_NG_CRUDE_RATIO",
        "fuel-substitution pair: -z504 of the cumulative log UNG/USO ratio",
        pair("UNG", "USO", -zscore(np.nancumsum(np.nan_to_num(lung - luso, nan=0.0)), 504)),
        "J_energy_spread")
    add("J7_CRACK_X_CURVE",
        "UGA/USO crack pair traded only when the WTI curve is BACKWARDATED (USL/USO ladder z504 < 0), flat in contango",
        gate(pair("UGA", "USO", -zscore(ck, 252)), -ladder("USL", "USO")), "J_energy_spread")

    # ============ K. CARRY-QUALITY TRANSFORMS ON THE COMMODITY PANEL ========
    c63, c252 = S.carry(63), S.carry(252)
    cstd = np.column_stack([roll_std(S.CD[:, j], 252) * ANN for j in range(S.NC)])
    add("K1_CARRY_INFO_RATIO",
        "rank commodities by carry / std(carry) -- the INFORMATION RATIO of the roll yield, not its level",
        ts.Sweep.xs_weights(S, np.where(cstd > 1e-9, c252 / cstd, np.nan), n_side=4), "K_carry_quality")
    add("K2_CARRY_TERM_SLOPE",
        "rank by (63d carry - 252d carry): whether a name's roll yield is IMPROVING vs its own year",
        ts.Sweep.xs_weights(S, c63 - c252, n_side=4), "K_carry_quality")
    sec = np.full(S.NC, 0)
    for si, (_, ix) in enumerate(SECTORS.items()):
        for j in ix:
            sec[j] = si
    cn = c252.copy()
    for si in range(3):
        cols = np.nonzero(sec == si)[0]
        cn[:, cols] = c252[:, cols] - np.nanmean(c252[:, cols], axis=1)[:, None]
    add("K3_CARRY_SECTOR_NEUTRAL",
        "carry rank DEMEANED within energy/metals/ags -- strips the sector bet, keeps the within-sector curve call",
        ts.Sweep.xs_weights(S, cn, n_side=4), "K_carry_quality")
    add("K4_CARRY_MINUS_MOM",
        "contrarian combo: rank by z(carry252) - z(12-1 momentum); buy high carry that has NOT already run",
        ts.Sweep.xs_weights(S, np.column_stack([zscore(c252[:, j], 504) for j in range(S.NC)])
                            - np.column_stack([zscore(S.cmom(252, 21)[:, j], 504) for j in range(S.NC)]),
                            n_side=4), "K_carry_quality")
    add("K5_CARRY_LOWVOL_TILT",
        "carry rank restricted to the 6 LOWEST-realised-vol commodities (carry is a vol-risk premium; take it where vol is calm)",
        ts.Sweep.xs_weights(S, np.where(
            np.argsort(np.argsort(np.nan_to_num(S.cvol(63), nan=9e9), axis=1), axis=1) < 6, c252, np.nan),
            n_side=2), "K_carry_quality")
    add("K6_CARRY_DISPERSION_SIZED",
        "cross-sectional carry sized by carry DISPERSION z504 (trade big only when the curve spread is unusually wide)",
        ts.Sweep.xs_weights(S, c252, n_side=4)
        * np.clip(zscore(np.nanstd(c252, axis=1), 504), 0, 3)[:, None] / 3.0, "K_carry_quality")
    add("K7_CARRY_PERSISTENCE",
        "trade only names whose carry sign has been STABLE all year (|mean sign of daily carry z| > 0.6), flat elsewhere",
        ts.Sweep.xs_weights(S, np.where(
            np.abs(np.column_stack([roll_mean(np.sign(zscore(c252[:, j], 504)), 252) for j in range(S.NC)])) > 0.6,
            c252, np.nan), n_side=3), "K_carry_quality")

    # ================== L. REGIME OVERLAYS ON A CARRY COMPOSITE =============
    # four carry sleeves, each gross-1
    sl_com = ts.Sweep.xs_weights(S, c252, n_side=4)
    vixc = np.log(np.maximum(S.P.close.get("^VIX"), 1e-6)) - np.log(np.maximum(S.P.close.get("^VIX3M"), 1e-6))
    sl_vol = put("SVXY", -np.sign(vixc))
    curve = S.P.close.get("^TNX") - S.P.close.get("^IRX")
    sl_rat = put("TLT", np.sign(curve))
    sl_fx = monthly_hold(S.xs(FXS, S.fxleg, n_side=2), d)   # clean (stale-corrected) FX carry
    comp = (sl_com + sl_vol + sl_rat + sl_fx) / 4.0
    add("L1_FOURSLEEVE_CARRY",
        "equal-risk composite of FOUR carry sleeves: commodity curve + vol curve + rates curve + FX basis",
        comp, "L_regime")
    add("L2_FOURSLEEVE_VOLGATE",
        "the four-sleeve carry composite, FLAT whenever log(VIX) z252 > +1",
        gate(comp, 1.0 - (_vixz > 1.0)), "L_regime")
    add("L3_FOURSLEEVE_VOLTARGET",
        "the four-sleeve composite scaled to a 10% trailing-realised-vol target (causal, capped 4x)",
        vol_target(comp, S, 0.10, 63), "L_regime")
    sleeve_carry = np.column_stack([
        np.nanmean(np.where(np.isfinite(c252), c252, np.nan), axis=1) * 0 + np.nanmax(c252, axis=1) - np.nanmin(c252, axis=1),
        -vixc, curve / 100.0, np.nanmax(FXS, axis=1) - np.nanmin(FXS, axis=1)])
    sz = np.column_stack([zscore(sleeve_carry[:, j], 504) for j in range(4)])
    Wd = np.zeros_like(comp)
    for j, sl in enumerate([sl_com, sl_vol, sl_rat, sl_fx]):
        Wd += sl * np.clip(np.nan_to_num(sz[:, j], nan=0.0), 0, 3)[:, None]
    gg = np.abs(Wd).sum(axis=1)
    Wd = Wd / np.where(gg > 1e-12, gg, np.nan)[:, None]
    add("L4_SLEEVE_CARRY_WEIGHTED",
        "allocate ACROSS the four sleeves in proportion to each sleeve's OWN carry z504 -- carry-timing the carry sleeves",
        np.nan_to_num(Wd, nan=0.0), "L_regime")
    dol = -np.nanmean(S.FL, axis=1)                    # +ve = USD strengthening
    add("L5_COMMOD_CARRY_DOLLAR_GATE",
        "commodity cross-sectional carry ON only when the trade-weighted dollar 126d trend is DOWN (weak USD = commodity-friendly)",
        gate(sl_com, -np.sign(cum_lr(dol, 126))), "L_regime")
    add("L6_COMMOD_CARRY_TREND_GATE",
        "commodity carry ON only when the sleeve's OWN 126d equity-curve trend is positive (strategy-level trend filter)",
        gate(sl_com, np.sign(lag(cum_lr(np.concatenate([[np.nan], ts._legs(S, sl_com)[0]]), 126), 1))),
        "L_regime")

    # ================= M. ROLL-WINDOW / CALENDAR TIMING =====================
    add("M1_PRE_ROLL_LADDER",
        "front-run the index roll: long USL / short USO on business days 3-7 only, flat otherwise",
        pair("USL", "USO", np.where((bdm >= 3) & (bdm <= 7), 1.0, 0.0)), "M_roll_timing")
    add("M2_POST_ROLL_FADE",
        "the mirror window: long USL / short USO on business days 10-14 only (after the roll has cleared)",
        pair("USL", "USO", np.where((bdm >= 10) & (bdm <= 14), 1.0, 0.0)), "M_roll_timing")
    add("M3_EXPIRY_WEEK_CRUDE",
        "hold USO only across the WTI expiry window (business days 13-17), flat the rest of the month",
        put("USO", np.where((bdm >= 13) & (bdm <= 17), 1.0, 0.0)), "M_roll_timing")
    add("M4_ROLL_WINDOW_CONDITIONED",
        "trade the roll window (bdays 5-9) in the DIRECTION of the prevailing curve: long USO in backwardation, short in contango",
        put("USO", np.where((bdm >= 5) & (bdm <= 9), -np.sign(ladder("USL", "USO")), 0.0)), "M_roll_timing")
    add("M5_MONTHEND_COMMOD",
        "turn-of-month in the broad commodity basket: long DBC on the last 1 + first 3 trading days",
        put("DBC", np.where((bdm <= 3) | (ts.bdays_left(d) <= 1), 1.0, 0.0)), "M_roll_timing")

    # ================= N. NEW FIXED-PRIOR SEASONALS =========================
    add("N1_GRAIN_HARVEST",
        "fixed prior: long the grain basket (CORN/WEAT/SOYB) Feb-Jun, short Aug-Nov (northern-hemisphere harvest pressure)",
        (put("CORN", np.where(np.isin(mon, [2, 3, 4, 5, 6]), 1 / 3, np.where(np.isin(mon, [8, 9, 10, 11]), -1 / 3, 0.0)))
         + put("WEAT", np.where(np.isin(mon, [2, 3, 4, 5, 6]), 1 / 3, np.where(np.isin(mon, [8, 9, 10, 11]), -1 / 3, 0.0)))
         + put("SOYB", np.where(np.isin(mon, [2, 3, 4, 5, 6]), 1 / 3, np.where(np.isin(mon, [8, 9, 10, 11]), -1 / 3, 0.0)))),
        "N_seasonal")
    add("N2_GOLD_SEASONAL",
        "fixed prior: long GLD Aug-Feb (festival/Q4 demand), short Mar-Jul",
        put("GLD", np.where(np.isin(mon, [8, 9, 10, 11, 12, 1, 2]), 1.0, -1.0)), "N_seasonal")
    add("N3_NG_CURVE_SEASONAL",
        "trade UNG by the SEASONAL SIGN OF THE CURVE, not of price: long when the UNL/UNG ladder is backwardated during Nov-Mar draw season",
        put("UNG", np.where(np.isin(mon, [11, 12, 1, 2, 3]), -np.sign(ladder("UNL", "UNG")), 0.0)), "N_seasonal")
    add("N4_XS_CARRY_SEASONAL",
        "cross-sectional: rank commodities by their OWN expanding prior-years mean CARRY in the current calendar month (seasonality of the curve, not of the return)",
        _seasonal_carry(S, c63, mon), "N_seasonal")
    add("N5_METALS_SEASONAL_PAIR",
        "fixed prior: long GLD / short SLV Nov-Feb, flip May-Aug (the precious-metals seasonal ratio)",
        pair("GLD", "SLV", np.where(np.isin(mon, [11, 12, 1, 2]), 1.0,
                                    np.where(np.isin(mon, [5, 6, 7, 8]), -1.0, 0.0))), "N_seasonal")
    add("N6_JAN_REBALANCE_COMMOD",
        "index-rebalance prior: long DBC / short GSG across the Dec-Jan annual index reweight window, flat else",
        pair("DBC", "GSG", np.where(np.isin(mon, [12, 1]), 1.0, 0.0)), "N_seasonal")

    return F


def _seasonal_carry(S: Sweep2, c, mon):
    """Expanding-window prior-years mean carry for the CURRENT calendar month.

    Strictly causal: at date t only months that have fully ended before t are used.
    """
    T, NC = c.shape
    score = np.full((T, NC), np.nan)
    sums = {}
    counts = {}
    ym = S.dates // 100
    prev_ym = -1
    for t in range(T):
        if ym[t] != prev_ym and prev_ym > 0:
            m = prev_ym % 100
            msk = ym == prev_ym
            for j in range(NC):
                v = np.nanmean(c[msk, j]) if np.isfinite(c[msk, j]).any() else np.nan
                if np.isfinite(v):
                    sums[(m, j)] = sums.get((m, j), 0.0) + v
                    counts[(m, j)] = counts.get((m, j), 0) + 1
            prev_ym = ym[t]
        elif prev_ym < 0:
            prev_ym = ym[t]
        m = mon[t]
        for j in range(NC):
            n = counts.get((m, j), 0)
            if n >= 4:
                score[t, j] = sums[(m, j)] / n
    return ts.Sweep.xs_weights(S, score, n_side=4)


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["design", "holdout"])
    ap.add_argument("--names", default="")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()

    S = Sweep2("total")
    F = build_formulas(S)
    print(f"panel {S.dates[0]}..{S.dates[-1]}  T={S.T}  assets={S.K}  formulas={len(F)}", flush=True)

    if a.cmd == "design":
        rows, Ws = [], []
        for f in F:
            r = ts.evaluate(S, f["W"], DESIGN_START, DESIGN_END)
            if r is None:
                print(f"  {f['name']:28s} SKIP (insufficient design coverage)", flush=True)
                continue
            rows.append({"name": f["name"], "group": f["group"], "desc": f["desc"], **r})
            Ws.append(f["W"])
            print(f"  {f['name']:28s} SR={r['sharpe']:+.2f} (sign {r['orientation']:+d}) "
                  f"gross={r['gross_sharpe']:+.2f} cost={r['cost_drag_annual']*100:5.2f}%/yr "
                  f"ret={r['ann_ret']*100:+.1f}% vol={r['ann_vol']*100:.1f}% dd={r['max_dd']*100:.0f}%",
                  flush=True)

        # --- FX robustness: rescore every FX-touching formula with the modelled
        #     carry leg DELETED (spot returns only).
        S2 = Sweep2("spotonly")
        F2 = {x["name"]: x["W"] for x in build_formulas(S2)}
        spot_only = {}
        for r in rows:
            if r["group"] in ("I_fx_basis", "I_fx_clean", "L_regime"):
                rr = ts.evaluate(S2, F2[r["name"]], DESIGN_START, DESIGN_END)
                if rr:
                    spot_only[r["name"]] = {"sharpe": rr["sharpe"], "orientation": rr["orientation"],
                                            "ann_ret": rr["ann_ret"]}
        del S2, F2

        nm = ts.null_max(S, Ws, DESIGN_START, DESIGN_END, B=a.boot)
        draws = nm.pop("_draws")
        N = len(rows)
        yrs = rows[0]["years"]
        analytic_t = math.sqrt(2 * math.log(2 * N))
        analytic_sr = analytic_t / math.sqrt(yrs)
        emp_p = {r["name"]: float((draws >= r["sharpe"]).mean()) for r in rows}
        srs = sorted(r["sharpe"] for r in rows)
        out = {
            "theme": THEME,
            "round": 2,
            "round1_artifact": "research/trading_bot/SWEEP_futures_term_structure.json",
            "design_window": f"{DESIGN_START}..{DESIGN_END}",
            "holdout_window_reserved": f"{HOLD_START}..{HOLD_END} (NOT evaluated by this command)",
            "n_formulas_tested": N,
            "search_is_sign_agnostic": True,
            "analytic_expected_max_t_sqrt2ln2N": analytic_t,
            "analytic_expected_max_sharpe": analytic_sr,
            "bootstrap_null": nm,
            "fx_pnl_convention": "spot return + modelled basis carry/252; carry-deleted rescore in fx_spot_only_rescore",
            "fx_spot_only_rescore": spot_only,
            "design_sharpe_distribution": {
                "min": srs[0], "p25": srs[len(srs) // 4], "median": srs[len(srs) // 2],
                "p75": srs[3 * len(srs) // 4], "max": srs[-1],
                "n_above_bootstrap_expected_max": sum(1 for s in srs if s > nm["expected_max_sharpe"]),
                "n_above_bootstrap_p95": sum(1 for s in srs if s > nm["p95_max_sharpe"]),
                "all_sorted": srs,
            },
            "results": sorted(rows, key=lambda r: -r["sharpe"]),
            "bootstrap_p_values": emp_p,
        }
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"SWEEP_{THEME}_DESIGN.json").write_text(json.dumps(out, indent=2))
        print(f"\nN={N} formulas, sign-agnostic -> 2N={2*N} effective tries over {yrs:.1f}y")
        print(f"  analytic  E[max t] = sqrt(2 ln 2N) = {analytic_t:.2f} -> Sharpe {analytic_sr:.2f}")
        print(f"  bootstrap E[max SR] = {nm['expected_max_sharpe']:.2f}  "
              f"p95 = {nm['p95_max_sharpe']:.2f}  p99 = {nm['p99_max_sharpe']:.2f}")
        print(f"  design Sharpes: min {srs[0]:+.2f}  med {srs[len(srs)//2]:+.2f}  max {srs[-1]:+.2f}")
        print("top by best-sign net Sharpe:")
        for r in out["results"][:10]:
            so = spot_only.get(r["name"])
            extra = f" spot_only={so['sharpe']:+.2f}" if so else ""
            flag = "  BEATS BAR" if emp_p[r["name"]] < 0.05 else ""
            print(f"  {r['name']:28s} SR={r['sharpe']:+.2f} sign={r['orientation']:+d} "
                  f"boot p={emp_p[r['name']]:.3f}{extra}{flag}")
        return 0

    names = [x for x in a.names.split(",") if x]
    rows = []
    for f in F:
        if f["name"] not in names:
            continue
        dd = ts.evaluate(S, f["W"], DESIGN_START, DESIGN_END)
        h = ts.evaluate(S, f["W"], HOLD_START, HOLD_END)
        rows.append({"name": f["name"], "desc": f["desc"], "design": dd, "holdout": h})
        print(f"  {f['name']:28s} design SR={dd['sharpe']:+.2f} t={dd['t_stat']:+.2f} | "
              f"HELD-OUT SR={h['sharpe']:+.2f} t={h['t_stat']:+.2f} ret={h['ann_ret']*100:+.1f}% "
              f"vol={h['ann_vol']*100:.1f}% dd={h['max_dd']*100:.0f}% yrs={h['years']}", flush=True)
    (OUT / f"SWEEP_{THEME}_HOLDOUT.json").write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
