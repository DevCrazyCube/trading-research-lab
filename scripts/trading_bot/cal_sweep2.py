#!/usr/bin/env python3
"""WIDE calendar / session / structural-flow sweep -- BATCH 2.

Batch 1 (scripts/trading_bot/cal_sweep.py, 52 formulas) concluded the theme is noise.
This batch is NOT a re-parameterisation of batch 1. It deliberately fills the structural
gaps batch 1 left open:

  * session DECOMPOSITION crossed with the calendar (batch 1 used the overnight/intraday
    split in only 3 of 52 formulas; the whole "is a calendar effect an open-gap effect or
    a session effect" question was untested)
  * CROSS-SECTIONAL calendar sorts across an ETF panel (batch 1's only cross-section was
    the survivorship-biased single-stock panel)
  * NAMED holidays as separate events (batch 1 pooled all exchange holidays)
  * expiry mechanics other than the monthly OPEX date (VIX expiry, post-OPEX Monday,
    pre-OPEX drift, quad-witching sector dispersion)
  * crypto flow structures batch 1 did not have: CME-gap continuation, weekend-move
    reversion at the Asia handoff, funding conditioned on MAGNITUDE with an 8h hold,
    alt/major session rotation, Deribit weekly-expiry block

Discipline is inherited from batch 1 and is not relaxed:
  * every formula written a-priori, no fitted constants
  * scored on the DESIGN window only; holdout numbers printed only for names passed on
    the command line AFTER the sweep is frozen
  * family bar = empirical max|z| under circular rotation of returns against a fixed
    calendar, statistic studentised per formula to strip deterministic cost drift
  * costs charged per side on |dw|: ETF 1.0bp, stock 2.5bp, perp 5.0bp
"""

from __future__ import annotations

import datetime as dt
import json
import sys

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from scripts.trading_bot.cal_sweep import (  # noqa: E402
    COST_ETF_BP,
    COST_PERP_BP,
    COST_STOCK_BP,
    OUT,
    SPLIT_CRYPTO,
    SPLIT_DAILY,
    SPLIT_XS,
    Family,
    net_pnl,
    rotate_live,
    sharpe,
)

# ETF cross-sectional panel: liquid, broad, and all live by mid-2003 so the design window
# (which ends 2016-12-31) still holds ~13 years of cross-section.
XE_SYMS = ["SPY", "QQQ", "IWM", "MDY", "DIA", "OEF", "RSP",
           "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY",
           "EFA", "EEM", "EWJ", "EWZ", "TLT", "IEF", "LQD", "GLD"]


# =======================================================================================
# extra calendar features batch 1 did not build
# =======================================================================================

def extra_features(dates, F):
    D = F["D"]
    n = len(D)
    month, year, dow = F["month"], F["year"], F["dow"]
    ym = F["ym"]
    day = F["day"]

    # ---- VIX monthly expiry: the Wednesday 30 days before the third Friday of the
    #      FOLLOWING month (CFE rule). Mark the session and its week.
    vix_exp = np.zeros(n, bool)
    vix_week = np.zeros(n, bool)
    dset = {d: i for i, d in enumerate(D)}
    for m in np.unique(ym):
        y, mo = (m - 1) // 12, (m - 1) % 12 + 1
        nm_y, nm_m = (y, mo + 1) if mo < 12 else (y + 1, 1)
        first = dt.date(nm_y, nm_m, 1)
        tf = first + dt.timedelta(days=((4 - first.weekday()) % 7) + 14)
        w = tf - dt.timedelta(days=30)
        for back in range(0, 6):                       # nearest prior session
            cand = w - dt.timedelta(days=back)
            if cand in dset:
                i = dset[cand]
                vix_exp[i] = True
                wk0 = cand - dt.timedelta(days=cand.weekday())
                for k in range(len(D)):
                    if wk0 <= D[k] <= cand:
                        vix_week[k] = True
                break

    # ---- named holidays -------------------------------------------------------------
    thanks = np.zeros(n, bool)          # session before + session after Thanksgiving
    july4 = np.zeros(n, bool)
    xmas_week = np.zeros(n, bool)       # Dec 24 .. Dec 31
    post_labor = np.zeros(n, bool)      # 5 sessions after Labor Day
    for y in np.unique(year):
        # Thanksgiving = 4th Thursday of November
        nov1 = dt.date(int(y), 11, 1)
        th = nov1 + dt.timedelta(days=((3 - nov1.weekday()) % 7) + 21)
        sel = [i for i in range(n) if D[i].year == y]
        if not sel:
            continue
        before = [i for i in sel if D[i] < th]
        after = [i for i in sel if D[i] > th]
        if before:
            thanks[before[-1]] = True
        if after:
            thanks[after[0]] = True
        # July 4th: the session before and the session after the holiday date
        j4 = dt.date(int(y), 7, 4)
        b = [i for i in sel if D[i] < j4]
        a = [i for i in sel if D[i] > j4]
        if b:
            july4[b[-1]] = True
        if a:
            july4[a[0]] = True
        # Labor Day = first Monday of September; 5 sessions after
        s1 = dt.date(int(y), 9, 1)
        ld = s1 + dt.timedelta(days=(0 - s1.weekday()) % 7)
        aft = [i for i in sel if D[i] > ld]
        for i in aft[:5]:
            post_labor[i] = True
    for i in range(n):
        if month[i] == 12 and day[i] >= 24:
            xmas_week[i] = True

    # ---- OPEX satellites -------------------------------------------------------------
    opx = F["opex"]
    oi = np.where(opx)[0]
    opex_pre3 = np.zeros(n, bool)
    opex_mon_after = np.zeros(n, bool)
    for i in oi:
        opex_pre3[max(0, i - 3): i] = True
        for k in range(i + 1, min(n, i + 5)):
            if dow[k] == 0:
                opex_mon_after[k] = True
                break

    # ---- month-boundary index maps ---------------------------------------------------
    month_start = np.zeros(n, bool)
    month_start[0] = True
    month_start[1:] = ym[1:] != ym[:-1]
    year_start = np.zeros(n, bool)
    year_start[0] = True
    year_start[1:] = year[1:] != year[:-1]

    return dict(vix_exp=vix_exp, vix_week=vix_week, thanks=thanks, july4=july4,
                xmas_week=xmas_week, post_labor=post_labor, opex_pre3=opex_pre3,
                opex_mon_after=opex_mon_after, month_start=month_start,
                year_start=year_start)


def block_excl_cumsum(c, start_flag):
    """Per-block cumulative sum of `c` (n,k) EXCLUDING row t (strictly prior info)."""
    n = c.shape[0]
    cs = np.cumsum(c, axis=0)
    starts = np.where(start_flag)[0]
    base = np.zeros_like(c)
    blk = np.zeros(n, int)
    blk[starts] = 1
    blk = np.cumsum(blk) - 1
    prev_cs = np.vstack([np.zeros((1, c.shape[1])), cs[:-1]])
    base_vals = prev_cs[starts]                      # cumsum up to the row before block start
    base = base_vals[blk]
    incl = cs - base
    return incl - c                                  # through t-1


# =======================================================================================
# batch-2 family
# =======================================================================================

class Family2(Family):

    def _register(self):
        F = self.F
        self.E = extra_features(self.dates, F)
        E = self.E
        dow, tdom, rtdom = F["dow"], F["tdom"], F["rtdom"]
        month, quad = F["month"], F["quad"]
        opx, ow = F["opex"], F["opex_week"]
        ph, qh = F["pre_hol"], F["post_hol"]
        self.xe_js = [self.si[s] for s in XE_SYMS]
        n = self.n

        tom = (rtdom == 1) | (tdom <= 3)
        tom2 = (rtdom <= 2) | (tdom <= 2)
        first_half = tdom <= 10
        second_half = tdom >= 11

        # ================= H. session decomposition x calendar =======================
        self.add("SESS_TOM_OVERNIGHT", "long SPY over the OPEN GAP only (prev close->open) "
                 "on every turn-of-month session -- is the TOM effect an overnight effect?",
                 "daily", lambda R: self._one_pnl("SPY", tom, R, "ovn"), ["SPY"])
        self.add("SESS_TOM_INTRADAY", "long SPY open->close only on every turn-of-month "
                 "session (the same window, the other half of the day)",
                 "daily", lambda R: self._one_pnl("SPY", tom, R, "intr"), ["SPY"])
        self.add("SESS_OPEXDAY_INTRADAY", "long SPY open->close on the monthly OPEX session "
                 "only (pin release inside the day)",
                 "daily", lambda R: self._one_pnl("SPY", opx, R, "intr"), ["SPY"])
        self.add("SESS_OPEXDAY_OVERNIGHT", "long SPY over the gap INTO the OPEX session "
                 "(overnight positioning ahead of expiry)",
                 "daily", lambda R: self._one_pnl("SPY", opx, R, "ovn"), ["SPY"])
        self.add("SESS_PREHOL_INTRADAY", "long SPY open->close on the last session before "
                 "every exchange holiday (pre-holiday drift, intraday leg)",
                 "daily", lambda R: self._one_pnl("SPY", ph, R, "intr"), ["SPY"])
        self.add("SESS_PREHOL_OVERNIGHT", "long SPY over the gap INTO the pre-holiday "
                 "session (pre-holiday drift, overnight leg)",
                 "daily", lambda R: self._one_pnl("SPY", ph, R, "ovn"), ["SPY"])
        self.add("SESS_POSTHOL_GAP", "long SPY over the holiday gap itself (last close "
                 "before the holiday -> first open after)",
                 "daily", lambda R: self._one_pnl("SPY", qh, R, "ovn"), ["SPY"])
        self.add("SESS_TDOM1_GAP", "long SPY over the open gap into the FIRST session of "
                 "each month only (new-money inflow hits the open)",
                 "daily", lambda R: self._one_pnl("SPY", tdom == 1, R, "ovn"), ["SPY"])
        self.add("SESS_EOM_GAP", "long SPY over the open gap into the LAST session of each "
                 "month only",
                 "daily", lambda R: self._one_pnl("SPY", rtdom == 1, R, "ovn"), ["SPY"])
        self.add("SESS_MOC_REVERSAL", "first session of the month, open->close: take the "
                 "OPPOSITE sign of the last session of the prior month's open->close move "
                 "(month-end MOC imbalance reversal)",
                 "daily", lambda R: self._moc_reversal(R), ["SPY"])
        self.add("SESS_MON_GAP_VS_DAY", "long SPY over the weekend gap and SHORT SPY "
                 "Monday open->close (weekend news vs Monday session, as one trade)",
                 "daily", lambda R: self._gap_vs_day(R, dow == 0), ["SPY"])

        # ================= I. cross-sectional ETF calendar sorts =====================
        self.add("XE_MONTHEND_REV", "last 2 sessions of the month, across a 24-ETF panel: "
                 "long the worst month-to-date third, short the best (rebalance flow into "
                 "the laggards)",
                 "daily", lambda R: self._xe(R, rtdom <= 2, "mtd", -1.0), ["EEM", "TLT", "GLD"])
        self.add("XE_MONTHSTART_CONT", "first 2 sessions of the month: the same MTD sort "
                 "in the CONTINUATION direction (long prior-month winners)",
                 "daily", lambda R: self._xe(R, tdom <= 2, "pmtd", +1.0), ["EEM", "TLT", "GLD"])
        self.add("XE_JAN_REV", "January only: long last calendar year's worst third of the "
                 "ETF panel, short the best (January reversal at the asset-class level)",
                 "daily", lambda R: self._xe(R, month == 1, "pyr", -1.0), ["EEM", "TLT", "GLD"])
        self.add("XE_MON_REV", "Mondays only: long Friday's worst third of the ETF panel, "
                 "short Friday's best (weekend overreaction reverses)",
                 "daily", lambda R: self._xe(R, dow == 0, "prev", -1.0), ["EEM", "TLT", "GLD"])
        self.add("XE_OPEXWEEK_LOWVOL", "OPEX week: long the low-trailing-vol third of the "
                 "ETF panel, short the high-vol third (dealer gamma suppresses movers)",
                 "daily", lambda R: self._xe(R, ow, "vol", -1.0), ["EEM", "TLT", "GLD"])
        self.add("XE_TOM_DISPERSION", "turn-of-month: long the high-trailing-vol third of "
                 "the ETF panel, short the low-vol third (flow hits the beta names)",
                 "daily", lambda R: self._xe(R, tom, "vol", +1.0), ["EEM", "TLT", "GLD"])

        # ================= J. turn-of-month structure, new mechanisms ================
        self.add("HALF_MONTH_SPLIT", "long SPY on trading days 1-10 of the month, SHORT SPY "
                 "on day 11 to month end (the half-month split as one always-on trade)",
                 "daily", lambda R: self._half_month(R, first_half, second_half), ["SPY"])
        self.add("TOM_DURATION_EXT", "last 2 sessions of the month: long TLT / short IEF "
                 "(bond indices extend duration at each month-end reconstitution)",
                 "daily", lambda R: self._pair_pnl("TLT", "IEF", rtdom <= 2, R), ["TLT", "IEF"])
        self.add("TOM_CREDIT_FLOW", "turn-of-month: long LQD / short IEF (credit index "
                 "rebalance and coupon reinvestment)",
                 "daily", lambda R: self._pair_pnl("LQD", "IEF", tom, R), ["LQD", "IEF"])
        self.add("TOM_EM_MINUS_DM", "turn-of-month: long EEM / short EFA",
                 "daily", lambda R: self._pair_pnl("EEM", "EFA", tom, R), ["EEM", "EFA"])
        self.add("TOM_USD", "long UUP over the turn-of-month window (month-end FX fixing "
                 "dollar demand)",
                 "daily", lambda R: self._one_pnl("UUP", tom, R, "c2c"), ["UUP"])
        self.add("TOM_GOLD_2X2", "long GLD the last 2 and first 2 sessions of each month",
                 "daily", lambda R: self._one_pnl("GLD", tom2, R, "c2c"), ["GLD"])
        self.add("TOQ_SPY_MINUS_TLT_UNCOND", "quarter ends only, last 2 sessions: short SPY "
                 "/ long TLT UNCONDITIONALLY (no month-to-date conditioner -- the pure "
                 "quarter-end rebalance direction)",
                 "daily", lambda R: self._pair_pnl(
                     "TLT", "SPY", (rtdom <= 2) & np.isin(month, [3, 6, 9, 12]), R),
                 ["TLT", "SPY"])
        self.add("TOM_SECTOR_DEFENSIVE", "turn-of-month: long XLP+XLU / short XLK+XLY "
                 "(defensive vs cyclical around the flow window)",
                 "daily", lambda R: self._basket_pair(
                     ["XLP", "XLU"], ["XLK", "XLY"], tom, R),
                 ["XLP", "XLU", "XLK", "XLY"])

        # ================= K. expiry mechanics beyond the OPEX date ==================
        self.add("VIXEXP_WEEK_SPY", "long SPY through the week of VIX monthly expiry (the "
                 "Wednesday 30 days before the next third Friday)",
                 "daily", lambda R: self._one_pnl("SPY", E["vix_week"], R, "c2c"), ["SPY"])
        self.add("VIXEXP_DAY_SPY", "long SPY on the VIX expiry session only",
                 "daily", lambda R: self._one_pnl("SPY", E["vix_exp"], R, "c2c"), ["SPY"])
        self.add("OPEX_MON_AFTER_SPY", "long SPY only on the first Monday after monthly "
                 "OPEX (dealers re-hedge into the new cycle)",
                 "daily", lambda R: self._one_pnl("SPY", E["opex_mon_after"], R, "c2c"), ["SPY"])
        self.add("OPEX_PRE3_SPY", "long SPY the 3 sessions BEFORE monthly OPEX (drift into "
                 "the pin)",
                 "daily", lambda R: self._one_pnl("SPY", E["opex_pre3"], R, "c2c"), ["SPY"])
        self.add("QUADWITCH_DISPERSION", "quad-witching session only: long XLK / short XLP "
                 "(index-level unwind hits high-beta sectors)",
                 "daily", lambda R: self._pair_pnl("XLK", "XLP", opx & quad, R), ["XLK", "XLP"])
        self.add("OPEX_SPY_MINUS_IWM", "long SPY / short IWM through OPEX week (index-option "
                 "gamma is concentrated in large caps)",
                 "daily", lambda R: self._pair_pnl("SPY", "IWM", ow, R), ["SPY", "IWM"])

        # ================= L. named holidays, separately =============================
        self.add("THANKSGIVING_SPY", "long SPY the session before and the session after "
                 "Thanksgiving",
                 "daily", lambda R: self._one_pnl("SPY", E["thanks"], R, "c2c"), ["SPY"])
        self.add("JULY4_SPY", "long SPY the session before and the session after July 4",
                 "daily", lambda R: self._one_pnl("SPY", E["july4"], R, "c2c"), ["SPY"])
        self.add("XMAS_WEEK_SPY", "long SPY every session from Dec 24 to year end",
                 "daily", lambda R: self._one_pnl("SPY", E["xmas_week"], R, "c2c"), ["SPY"])
        self.add("POST_LABORDAY_SHORT", "short SPY the 5 sessions after Labor Day "
                 "(September re-risking weakness)",
                 "daily", lambda R: self._one_pnl(
                     "SPY", E["post_labor"], R, "c2c", sign=-1.0), ["SPY"])
        self.add("PREHOL_SMALLCAP", "long IWM / short SPY on the last session before every "
                 "exchange holiday (thin-tape small-cap drift)",
                 "daily", lambda R: self._pair_pnl("IWM", "SPY", ph, R), ["IWM", "SPY"])

        # ================= M. crypto flow structures =================================
        hod, cdow = self.CF["hod"], self.CF["dow"]
        self.add("XT_WEEKEND_REV_ASIA", "Monday 00-08 UTC: take the OPPOSITE sign of the "
                 "Sat+Sun BTC move (weekend illiquidity overreaction unwinds when Asia "
                 "returns)",
                 "crypto", lambda R: self._c_weekend(R, dst=(0, 8), sign=-1.0))
        self.add("XT_WEEKEND_CONT_US", "Monday 13-21 UTC: take the SAME sign as the Sat+Sun "
                 "BTC move (CME reopens and the weekend move continues into US hours)",
                 "crypto", lambda R: self._c_weekend(R, dst=(13, 21), sign=+1.0))
        self.add("XT_FUNDING_MAG_8H", "hold -sign(last settled funding) for the WHOLE 8h "
                 "block, but only when |funding| is in the top third of its trailing "
                 "90-day distribution (magnitude conditioner, low turnover)",
                 "crypto", lambda R: self._c_funding_mag(R))
        self.add("XT_ALT_SESSION_ROT", "long ETH / short BTC perp in the Asia session "
                 "(00-08 UTC), reversed in the US session (13-21 UTC)",
                 "crypto", lambda R: self._c_session_rot(R))
        self.add("XT_DERIBIT_EXPIRY_BLOCK", "long BTC perp in the 08-16 UTC block on Fridays "
                 "(Deribit options settle 08:00 UTC Friday; gamma is released after)",
                 "crypto", lambda R: self._c_pnl(R, 0, (cdow == 4) & (hod >= 8) & (hod < 16)))
        self.add("XT_MONTHEND_DERISK", "short BTC perp on the last UTC day of the month, "
                 "long on the first (the opposite convention to a turn-of-month long)",
                 "crypto", lambda R: self._c_monthend_derisk(R))
        self.add("XT_POST_US_CLOSE", "long BTC perp only in the 21-24 UTC block (after the "
                 "US equity close, before Asia)",
                 "crypto", lambda R: self._c_pnl(R, 0, hod >= 21))
        self.add("XT_ALT_WEEKEND_SPREAD", "long an ETH/SOL/BNB perp basket Fri-Sun UTC and "
                 "SHORT it Mon-Thu (weekend alt bid as a self-financing spread)",
                 "crypto", lambda R: self._c_week_spread(R))
        self.add("XT_SESSION_HANDOFF_EU", "sign of the Asia-session (00-08 UTC) BTC move "
                 "carried through the EU session (08-13 UTC) -- continuation, not reversal",
                 "crypto", lambda R: self._c_handoff(R, src=(0, 8), dst=(8, 13), sign=+1.0))

        # ================= N. single-stock cross-section, new events =================
        self.add("XS_OPEXWEEK_MOM", "OPEX week: long the 21-day winners third of the stock "
                 "panel, short the losers third (pin momentum)",
                 "xs", lambda R: self._xs2(R, mode="opex_mom"))
        self.add("XS_FRIDAY_REV", "Fridays only: long the week's losers third, short the "
                 "winners third (weekly reversal into the weekend)",
                 "xs", lambda R: self._xs2(R, mode="fri_rev"))
        self.add("XS_TOM_LOWVOL", "turn-of-month: long the LOW-vol third of the stock panel, "
                 "short the high-vol third (the opposite tilt to batch 1's XS_TOM_HIVOL)",
                 "xs", lambda R: self._xs2(R, mode="tom_lowvol"))

    # ---- daily bodies ----------------------------------------------------------------
    def _moc_reversal(self, R):
        ir = R["intr"][:, self.si["SPY"]]
        tdom, rtdom = self.F["tdom"], self.F["rtdom"]
        n = self.n
        last_intr = np.zeros(n)
        cur = 0.0
        for i in range(n):
            last_intr[i] = cur
            if rtdom[i] == 1:
                cur = ir[i]
        w = np.where(tdom == 1, -np.sign(last_intr), 0.0)
        turn = np.abs(w) * 2.0
        return w * ir - turn * COST_ETF_BP * 1e-4

    def _gap_vs_day(self, R, mask):
        j = self.si["SPY"]
        g, d = R["ovn"][:, j], R["intr"][:, j]
        w = np.where(mask, 1.0, 0.0)
        # long the gap, short the session: 2 crossings for the gap, 2 for the session
        return w * (g - d) - np.abs(w) * 4.0 * COST_ETF_BP * 1e-4

    def _half_month(self, R, m1, m2):
        r = R["c2c"][:, self.si["SPY"]]
        w = np.where(m1, 1.0, 0.0) + np.where(m2, -1.0, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_ETF_BP * 1e-4

    def _basket_pair(self, longs, shorts, mask, R):
        c = R["c2c"]
        rl = c[:, [self.si[s] for s in longs]].mean(axis=1)
        rs = c[:, [self.si[s] for s in shorts]].mean(axis=1)
        w = np.where(mask, 0.5, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * (rl - rs) - np.abs(w - prev) * 2 * COST_ETF_BP * 1e-4

    def _xe(self, R, act, score_kind, sign):
        c = R["c2c"]
        js = self.xe_js
        sub = c[:, js]
        n, k = sub.shape
        F = self.F
        if score_kind == "mtd":
            S = block_excl_cumsum(sub, F["ym"] != np.roll(F["ym"], 1))
        elif score_kind == "pmtd":
            # previous month's FULL return, carried into the new month
            ms = F["ym"] != np.roll(F["ym"], 1)
            ms[0] = True
            incl = block_excl_cumsum(sub, ms) + sub
            S = np.zeros_like(sub)
            starts = np.where(ms)[0]
            for a, b in zip(starts, list(starts[1:]) + [n]):
                S[a:b] = incl[a - 1] if a > 0 else 0.0
        elif score_kind == "pyr":
            ys = F["year"] != np.roll(F["year"], 1)
            ys[0] = True
            incl = block_excl_cumsum(sub, ys) + sub
            S = np.zeros_like(sub)
            starts = np.where(ys)[0]
            for a, b in zip(starts, list(starts[1:]) + [n]):
                S[a:b] = incl[a - 1] if a > 0 else 0.0
        elif score_kind == "prev":
            S = np.vstack([np.zeros((1, k)), sub[:-1]])
        elif score_kind == "vol":
            cs = np.cumsum(np.vstack([np.zeros((1, k)), sub ** 2]), axis=0)
            v = np.sqrt(np.maximum(cs[60:] - cs[:-60], 0) / 60.0)
            S = np.vstack([np.full((60, k), np.nan), v])[:n]
            S = np.vstack([np.full((1, k), np.nan), S[:-1]])
        else:
            raise ValueError(score_kind)

        W = np.zeros((n, len(self.syms)))
        live = self.live[:, js]
        for i in np.where(act)[0]:
            sc = S[i]
            ok = live[i] & np.isfinite(sc)
            if ok.sum() < 12:
                continue
            idxs = np.where(ok)[0]
            order = idxs[np.argsort(sc[idxs])]
            t = max(1, len(order) // 3)
            lo, hi = order[:t], order[-t:]
            for q in hi:
                W[i, js[q]] = sign * 0.5 / t
            for q in lo:
                W[i, js[q]] = -sign * 0.5 / t
        return net_pnl(W, c, COST_ETF_BP)

    # ---- crypto bodies ---------------------------------------------------------------
    def _c_weekend(self, R, dst, sign):
        r = R[:, 0]
        hod, cdow, di = self.CF["hod"], self.CF["dow"], self.CF["day_idx"]
        ndays = int(di.max()) + 1
        dayret = np.zeros(ndays)
        np.add.at(dayret, di, r)
        wk = np.zeros(ndays)
        wk[2:] = dayret[:-2] + dayret[1:-1]           # for day d: d-2 (Sat) + d-1 (Sun)
        m = (cdow == 0) & (hod >= dst[0]) & (hod < dst[1])
        w = np.where(m, sign * np.sign(wk[di]), 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_PERP_BP * 1e-4

    def _c_funding_mag(self, R):
        r = R[:, 0]
        f = self.f_prev
        # trailing top-third threshold of |funding| using strictly prior settlements
        af = np.abs(f)
        thr = self.fund_thr
        s = np.where(af >= thr, -np.sign(f), 0.0)
        w = s
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_PERP_BP * 1e-4

    def _c_session_rot(self, R):
        hod = self.CF["hod"]
        spread = R[:, 1] - R[:, 0]                    # ETH - BTC
        asia = hod < 8
        us = (hod >= 13) & (hod < 21)
        w = np.where(asia, 0.5, 0.0) + np.where(us, -0.5, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * spread - np.abs(w - prev) * 2 * COST_PERP_BP * 1e-4

    def _c_monthend_derisk(self, R):
        r = R[:, 0]
        ds = self.CF["dates"]
        dnum = np.array([d.day for d in ds])
        mon = np.array([d.year * 12 + d.month for d in ds])
        n = len(r)
        last_day = np.zeros(n, bool)
        di = self.CF["day_idx"]
        for i in range(n - 1):
            if mon[i] != mon[i + 1]:
                last_day[di == di[i]] = True
        w = np.where(last_day, -1.0, 0.0) + np.where(dnum <= 1, 1.0, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_PERP_BP * 1e-4

    def _c_week_spread(self, R):
        r = R[:, [1, 2, 3]].mean(axis=1)
        cdow = self.CF["dow"]
        w = np.where(cdow >= 4, 1.0, -1.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_PERP_BP * 1e-4

    # ---- stock cross-section ---------------------------------------------------------
    def _xs2(self, R, mode):
        n, k = R.shape
        F = self.xF
        tdom, rtdom, dow = F["tdom"], F["rtdom"], F["dow"]
        ow = F["opex_week"]
        live = self.xLIVE
        cs = np.cumsum(np.vstack([np.zeros((1, k)), R ** 2]), axis=0)
        vol = np.sqrt(np.maximum(cs[60:] - cs[:-60], 0) / 60.0)
        VOL = np.vstack([np.full((60, k), np.nan), vol])[:n]
        VOL = np.vstack([np.full((1, k), np.nan), VOL[:-1]])
        lp = np.cumsum(np.vstack([np.zeros((1, k)), R]), axis=0)
        M21 = np.vstack([np.full((21, k), np.nan), (lp[21:] - lp[:-21])])[:n]
        M21 = np.vstack([np.full((1, k), np.nan), M21[:-1]])
        M4 = np.vstack([np.full((4, k), np.nan), (lp[4:] - lp[:-4])])[:n]
        M4 = np.vstack([np.full((1, k), np.nan), M4[:-1]])

        tom = (rtdom == 1) | (tdom <= 3)
        if mode == "opex_mom":
            act, score, sign = ow, M21, +1.0
        elif mode == "fri_rev":
            act, score, sign = dow == 4, M4, -1.0
        elif mode == "tom_lowvol":
            act, score, sign = tom, VOL, -1.0
        else:
            raise ValueError(mode)

        W = np.zeros((n, k))
        for i in np.where(act)[0]:
            sc = score[i]
            ok = live[i] & np.isfinite(sc)
            if ok.sum() < 30:
                continue
            idxs = np.where(ok)[0]
            order = idxs[np.argsort(sc[idxs])]
            t = max(1, len(order) // 3)
            W[i, order[-t:]] = sign * 0.5 / t
            W[i, order[:t]] = -sign * 0.5 / t
        return net_pnl(W, R, COST_STOCK_BP)


def build_funding_threshold(fam):
    """Trailing top-third threshold of |funding| per hour, strictly prior information."""
    f = np.abs(fam.f_prev)
    n = len(f)
    thr = np.full(n, np.inf)
    # funding changes only every 8h; compute on the hourly grid with an expanding window
    # capped at 90 days (270 settlements ~ 2160 hours)
    W = 90 * 24
    for start in range(0, n, 24):
        end = min(start + 24, n)
        a = max(0, start - W)
        if start - a < 24 * 30:
            continue
        q = np.quantile(f[a:start], 2.0 / 3.0)
        thr[start:end] = q
    return thr


def main():
    NREP = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    fam = Family2()
    fam.fund_thr = build_funding_threshold(fam)
    N = len(fam.reg)
    print(f"{N} batch-2 formulas registered", flush=True)
    design = fam.run(window="design")

    rng = np.random.default_rng(20260820)
    null = {k: [] for k in design}
    for rep in range(NREP):
        kd = int(rng.integers(200, fam.n - 200))
        kc = int(rng.integers(2000, len(fam.cms) - 2000))
        kx = int(rng.integers(100, len(fam.xdates) - 100))
        sh = fam.run(shift=(kd, kc, kx), window="design")
        for k, v in sh.items():
            null[k].append(v)
        if (rep + 1) % 10 == 0:
            print(f"  null rep {rep+1}/{NREP}", flush=True)

    names = [r[0] for r in fam.reg]
    M = np.array([null[k] for k in names])
    mu = M.mean(axis=1)
    sd = np.where(M.std(axis=1) > 1e-9, M.std(axis=1), 1e-9)
    Z = (M - mu[:, None]) / sd[:, None]
    maxz_null = np.abs(Z).max(axis=0)
    design_vec = np.array([design[k] for k in names])
    zdes = (design_vec - mu) / sd

    # combined-family bar: batch 1 + batch 2 tried on the SAME theme, so the honest bar
    # for "did anything in this theme beat noise" pools both families.
    b1 = json.loads((OUT / "SWEEP_calendar_session.json").read_text())
    n1 = b1["n_formulas"]
    combined_n = n1 + N

    rows = []
    for i, (name, desc, ds, fn, first) in enumerate(fam.reg):
        nl = M[i]
        rows.append(dict(
            name=name, desc=desc, dataset=ds,
            design_sharpe=round(float(design_vec[i]), 3),
            null_mean_sharpe=round(float(mu[i]), 3),
            null_sd_sharpe=round(float(sd[i]), 3),
            z_vs_own_null=round(float(zdes[i]), 2),
            p_two_sided=round(float((np.abs(nl - mu[i]) >= abs(design_vec[i] - mu[i])).mean()), 4),
            beats_batch2_bar=bool(abs(zdes[i]) > float(np.percentile(maxz_null, 95))),
        ))
    rows.sort(key=lambda r: -abs(r["z_vs_own_null"]))

    res = dict(
        theme="calendar_session_structural_flow__batch2",
        n_formulas=N,
        n_formulas_theme_total=combined_n,
        batch1_reference="research/trading_bot/SWEEP_calendar_session.json",
        generated="2026-08-20",
        design_windows=dict(
            etf_daily=f"{fam.dates[0]}..{SPLIT_DAILY} ({int(fam.d_design.sum())} sessions)",
            stock_panel=f"{fam.xdates[0]}..{SPLIT_XS} ({int(fam.x_design.sum())} sessions)",
            crypto_perp_hourly=f"{fam.CF['iso'][0]}..{SPLIT_CRYPTO} ({int(fam.c_design.sum())} hours)",
        ),
        holdout_windows=dict(
            etf_daily=f"2017-01-01..{fam.dates[-1]} ({int(fam.d_hold.sum())} sessions)",
            stock_panel=f"2022-01-01..{fam.xdates[-1]} ({int(fam.x_hold.sum())} sessions)",
            crypto_perp_hourly=f"2024-01-01..{fam.CF['iso'][-1]} ({int(fam.c_hold.sum())} hours)",
        ),
        costs_bp_per_side=dict(etf=COST_ETF_BP, stock=COST_STOCK_BP, perp=COST_PERP_BP),
        null=dict(
            method=("circular rotation of every return array against a fixed calendar "
                    "(inside each instrument's live span); whole family re-scored per "
                    "replicate; per-formula studentised; max|z| across the family"),
            replicates=NREP,
            expected_max_abs_z=round(float(maxz_null.mean()), 3),
            max_abs_z_p50=round(float(np.percentile(maxz_null, 50)), 3),
            max_abs_z_p90=round(float(np.percentile(maxz_null, 90)), 3),
            max_abs_z_p95=round(float(np.percentile(maxz_null, 95)), 3),
            analytic_sqrt_2lnN_batch2=round(float(np.sqrt(2 * np.log(N))), 3),
            analytic_sqrt_2lnN_theme_total=round(float(np.sqrt(2 * np.log(combined_n))), 3),
        ),
        design_max_abs_z=round(float(np.abs(zdes).max()), 3),
        results=rows,
    )
    (OUT / "SWEEP_calendar_session_batch2.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["null"], indent=1))
    print(f"design max|z| = {res['design_max_abs_z']}  (batch2 N={N}, theme total={combined_n})")
    print(f"{'z':>7} {'Sharpe':>8} {'nullmu':>8} {'p':>7}  formula")
    for r in rows:
        print(f"{r['z_vs_own_null']:+7.2f} {r['design_sharpe']:+8.3f} "
              f"{r['null_mean_sharpe']:+8.3f} {r['p_two_sided']:7.4f}  "
              f"[{r['dataset']}] {r['name']}")


if __name__ == "__main__":
    main()
