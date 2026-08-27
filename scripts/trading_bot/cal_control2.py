#!/usr/bin/env python3
"""Post-freeze controls for the batch-2 calendar design leaders.

Run ONLY after the design sweep is frozen. Three controls per leader:

  1. PLACEBO WINDOW sweep -- the identical signal moved to neighbouring calendar windows.
     A real structural-flow effect decays away from the boundary; noise does not care.
  2. ALWAYS-ON control -- the identical signal with the calendar gate REMOVED. This is the
     control that killed batch 1's leader: if the ungated signal earns the same money, the
     calendar is not the edge.
  3. Held-out numbers for both the gated and ungated versions.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.trading_bot.cal_sweep import COST_ETF_BP, OUT, net_pnl, sharpe  # noqa: E402
from scripts.trading_bot.cal_sweep2 import (  # noqa: E402
    XE_SYMS,
    Family2,
    block_excl_cumsum,
    build_funding_threshold,
)


def score_windows(fam, pnl, syms=()):
    """Score design/holdout with the SAME live-start truncation the sweep applied.

    Without this the control silently evaluates years in which half the ETF panel did
    not exist yet, and the control number is not comparable to the sweep number.
    """
    first = 0
    for s in syms:
        nz = np.where(fam.live[:, fam.si[s]])[0]
        if len(nz):
            first = max(first, int(nz[0]))
    out = {}
    for win, m0 in (("design", fam.d_design), ("holdout", fam.d_hold)):
        m = m0.copy()
        m[:first] = False
        out[win] = round(sharpe(pnl[m], 252), 3)
    return out


def xe_pmtd_pnl(fam, act, sign=+1.0):
    """XE_MONTHSTART_CONT machinery, with an arbitrary activation mask."""
    c = fam.c2c
    js = fam.xe_js
    sub = c[:, js]
    n, k = sub.shape
    ym = fam.F["ym"]
    ms = ym != np.roll(ym, 1)
    ms[0] = True
    incl = block_excl_cumsum(sub, ms) + sub
    S = np.zeros_like(sub)
    starts = np.where(ms)[0]
    for a, b in zip(starts, list(starts[1:]) + [n]):
        S[a:b] = incl[a - 1] if a > 0 else 0.0
    W = np.zeros((n, len(fam.syms)))
    live = fam.live[:, js]
    for i in np.where(act)[0]:
        sc = S[i]
        ok = live[i] & np.isfinite(sc)
        if ok.sum() < 12:
            continue
        idxs = np.where(ok)[0]
        order = idxs[np.argsort(sc[idxs])]
        t = max(1, len(order) // 3)
        for q in order[-t:]:
            W[i, js[q]] = sign * 0.5 / t
        for q in order[:t]:
            W[i, js[q]] = -sign * 0.5 / t
    return net_pnl(W, c, COST_ETF_BP)


def pair_pnl(fam, a, b, mask):
    r = fam.c2c[:, fam.si[a]] - fam.c2c[:, fam.si[b]]
    w = np.where(mask, 0.5, 0.0)
    prev = np.concatenate([[0.0], w[:-1]])
    return w * 2 * r * 0.5 - np.abs(w - prev) * 2 * COST_ETF_BP * 1e-4


def one_intraday(fam, sym, mask, sign=1.0):
    r = fam.intr[:, fam.si[sym]]
    w = np.where(mask, sign, 0.0)
    return w * r - np.abs(w) * 2.0 * COST_ETF_BP * 1e-4


XE_ANCHOR = ("EEM", "TLT", "GLD")   # same live-start anchor the sweep used


def main():
    fam = Family2()
    fam.fund_thr = build_funding_threshold(fam)
    F = fam.F
    tdom, rtdom, dow = F["tdom"], F["rtdom"], F["dow"]
    opx, ow = F["opex"], F["opex_week"]
    res = {}

    # ---- 1. XE_MONTHSTART_CONT -------------------------------------------------------
    pw = {}
    for lo in range(1, 11, 2):
        m = (tdom >= lo) & (tdom <= lo + 1)
        pw[f"tdom {lo}-{lo+1}"] = score_windows(fam, xe_pmtd_pnl(fam, m), XE_ANCHOR)
    allon = score_windows(fam, xe_pmtd_pnl(fam, np.ones(fam.n, bool)), XE_ANCHOR)
    # the sort refreshed monthly but held all month = the ungated cross-sectional
    # asset-momentum trade this formula is a calendar slice of
    res["XE_MONTHSTART_CONT"] = dict(
        desc="first 2 sessions of the month: long prior-month winner third of a 24-ETF "
             "panel, short the loser third",
        placebo_windows=pw,
        always_on_same_sort=allon,
    )

    # ---- 2. SESS_OPEXDAY_INTRADAY ----------------------------------------------------
    # the formula is SHORT-side: design Sharpe -0.695 long, so the tradable side is short.
    pw2 = {}
    pw2["OPEX session (the formula, short)"] = score_windows(
        fam, one_intraday(fam, "SPY", opx, -1.0), ("SPY",))
    # placebo: each other session of OPEX week, short intraday
    oi = np.where(opx)[0]
    for back in range(1, 5):
        m = np.zeros(fam.n, bool)
        for i in oi:
            if i - back >= 0 and ow[i - back]:
                m[i - back] = True
        pw2[f"OPEX week, {back} session(s) before"] = score_windows(
            fam, one_intraday(fam, "SPY", m, -1.0), ("SPY",))
    # placebo: the 1st / 2nd / 4th Friday of the month instead of the third
    fri = dow == 4
    ym = fam.F["ym"]
    for k, lbl in ((0, "1st"), (1, "2nd"), (3, "4th")):
        m = np.zeros(fam.n, bool)
        for mm in np.unique(ym):
            sel = np.where(fri & (ym == mm))[0]
            if len(sel) > k:
                m[sel[k]] = True
        pw2[f"{lbl} Friday of the month instead of the 3rd"] = score_windows(
            fam, one_intraday(fam, "SPY", m, -1.0), ("SPY",))
    # placebo: every OTHER Friday (non-OPEX Fridays), short intraday
    fri_non = (dow == 4) & (~opx)
    pw2["every non-OPEX Friday"] = score_windows(
        fam, one_intraday(fam, "SPY", fri_non, -1.0), ("SPY",))
    pw2["every session (always on, short)"] = score_windows(
        fam, one_intraday(fam, "SPY", np.ones(fam.n, bool), -1.0), ("SPY",))
    res["SESS_OPEXDAY_INTRADAY"] = dict(
        desc="short SPY open->close on the monthly OPEX session (the design leader has "
             "Sharpe -0.695 long, so short is the tradable side)",
        placebo_windows=pw2,
    )

    # ---- 3. TOM_DURATION_EXT ---------------------------------------------------------
    pw3 = {}
    for lo in range(1, 11, 2):
        m = (rtdom >= lo) & (rtdom <= lo + 1)
        pw3[f"rtdom {lo}-{lo+1}"] = score_windows(fam, pair_pnl(fam, "TLT", "IEF", m), ("TLT","IEF"))
    pw3["every session (always on)"] = score_windows(
        fam, pair_pnl(fam, "TLT", "IEF", np.ones(fam.n, bool)), ("TLT","IEF"))
    res["TOM_DURATION_EXT"] = dict(
        desc="last 2 sessions of the month: long TLT / short IEF (bond index duration "
             "extension)",
        placebo_windows=pw3,
    )

    # ---- 4. XE_MONTHEND_REV ----------------------------------------------------------
    pw4 = {}
    for lo in range(1, 11, 2):
        m = (rtdom >= lo) & (rtdom <= lo + 1)
        pw4[f"rtdom {lo}-{lo+1}"] = score_windows(fam, xe_pmtd_pnl(fam, m, sign=-1.0), XE_ANCHOR)
    res["XE_MONTHEND_REV_proxy"] = dict(
        desc="month-end reversal window sweep, using the prior-month sort reversed "
             "(a stationary proxy for the MTD sort so the windows are comparable)",
        placebo_windows=pw4,
    )

    # ---- 5. cost sensitivity for the three leaders -----------------------------------
    cost_rows = {}
    for bp in (1.0, 2.0, 3.0, 5.0):
        # every pnl body in THIS module reads the module-global COST_ETF_BP
        globals()["COST_ETF_BP"] = bp
        cost_rows[f"{bp}bp"] = dict(
            XE_MONTHSTART_CONT=score_windows(fam, xe_pmtd_pnl(fam, tdom <= 2), XE_ANCHOR),
            SESS_OPEXDAY_INTRADAY=score_windows(
                fam, one_intraday(fam, "SPY", opx, -1.0), ("SPY",)),
            TOM_DURATION_EXT=score_windows(fam, pair_pnl(fam, "TLT", "IEF", rtdom <= 2), ("TLT","IEF")),
        )
    res["cost_sensitivity_design_and_holdout"] = cost_rows

    p = OUT / "SWEEP_calendar_session_batch2_CONTROLS.json"
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
