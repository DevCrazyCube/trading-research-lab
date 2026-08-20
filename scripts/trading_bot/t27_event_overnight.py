#!/usr/bin/env python3
"""T27 -- WIDE sweep over EVENT-conditioned overnight-equity formulas.

Sub-family: overnight equity around *events* (earnings announcements, 52-week
extremes, liquidity-rank promotions, turn-of-month, FOMC).  Sibling of T3
(pressure reversal) and T7 (ex-dividend open), and a deliberate extension of the
T26 sweep, which showed the *non-event* overnight space collapses onto one
feature (the last-ten-minute move).

Rails and costs are inherited verbatim from T26 / T3 / M0:

  rail A  "marketable"  -- signal may use the 15:59 last trade; entry is a
                           marketable order at the 15:59 print paying one measured
                           half-spread; exit is the next opening auction (0.50 bp).
  rail B  "MOC-legal"   -- information <= 15:49; entry at the official closing
                           print (0.50 bp); exit at the next opening auction.

  half-spread   1.13 bp design (2016-2021) / 1.43 bp held out (2022-2026)   [T3]
  auction leg   0.50 bp per auction print                                   [M0]
  borrow        30 bp/yr on the short notional, accrued over calendar days   [T6/T8]

Data, all cached, no network:
  research/data/t26_cache/panel.npz      auctions / 15:29,15:49,15:59 / ADV / universe
  research/data/t15_cache/earnings_8k.jsonl   SEC 8-K Item 2.02 filings by CIK,
                                              with EDGAR acceptance timestamps
  research/data/t15_cache/symbol_to_cik.json.gz

Usage:
  python3 t27_event_overnight.py events     # build the event panel (cached)
  python3 t27_event_overnight.py design
  python3 t27_event_overnight.py null [reps]
  python3 t27_event_overnight.py heldout NAME [NAME...]
"""

from __future__ import annotations

import bisect
import datetime
import gzip
import json
import math
import pathlib
import sys
from collections import defaultdict
from zoneinfo import ZoneInfo

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
PANEL = ROOT / "research" / "data" / "t26_cache" / "panel.npz"
T15 = ROOT / "research" / "data" / "t15_cache"
WORK = ROOT / "research" / "data" / "t27_cache"
WORK.mkdir(parents=True, exist_ok=True)
OUTDIR = ROOT / "research" / "trading_bot"

DESIGN_START, DESIGN_END = "2016-01-04", "2021-12-31"
TEST_START, TEST_END = "2022-01-03", "2026-08-14"

HALF_SPREAD_DESIGN_BP = 1.13
HALF_SPREAD_TEST_BP = 1.43
AUCTION_LEG_BP = 0.50
BORROW_ANNUAL_BP = 30.0

ET = ZoneInfo("America/New_York")

# FOMC decision dates (the day the statement is released), public calendar.
FOMC = """
2016-01-27 2016-03-16 2016-04-27 2016-06-15 2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-03-03 2020-03-15 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29
""".split()


# ===========================================================================
# 1. event panel
# ===========================================================================

def build_events():
    z = np.load(PANEL, allow_pickle=False)
    days = [str(d) for d in z["days"]]
    syms = [str(s) for s in z["syms"]]
    del z
    nD, nS = len(days), len(syms)
    day_idx = {d: i for i, d in enumerate(days)}
    sym_idx = {s: j for j, s in enumerate(syms)}

    with gzip.open(T15 / "symbol_to_cik.json.gz", "rt") as fh:
        cikmap = json.load(fh)["cik"]
    # cik -> list of panel columns (a CIK can carry two share classes)
    cols = defaultdict(list)
    for s, c in cikmap.items():
        j = sym_idx.get(s)
        if j is not None and c is not None:
            cols[int(c)].append(j)

    # session boundaries in ET for every panel day
    open_dt, close_dt = [], []
    for d in days:
        y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
        open_dt.append(datetime.datetime(y, m, dd, 9, 30, tzinfo=ET))
        close_dt.append(datetime.datetime(y, m, dd, 16, 0, tzinfo=ET))

    ANN = np.zeros((nD, nS), dtype=bool)          # announcement inside overnight window i
    ANN_INTRA = np.zeros((nD, nS), dtype=bool)    # announcement inside session i
    n_ev = n_night = n_intra = n_drop = 0

    for line in open(T15 / "earnings_8k.jsonl"):
        rec = json.loads(line)
        c = int(rec[0])
        js = cols.get(c)
        if not js:
            continue
        for fdate, ts, items, _acc in rec[1]:
            if not ts:
                continue
            t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(ET)
            if not (days[0] <= t.date().isoformat() <= days[-1]):
                continue
            n_ev += 1
            # locate the session index i such that t lands in [close_i, open_{i+1})
            # or in [open_i, close_i)
            i = bisect.bisect_right(close_dt, t) - 1     # last day whose close <= t
            if i < 0:
                # before the first close -> could be pre-open of day 0
                i2 = bisect.bisect_right(open_dt, t) - 1
                if i2 == 0 and t < close_dt[0]:
                    for j in js:
                        ANN_INTRA[0, j] = True
                    n_intra += 1
                else:
                    n_drop += 1
                continue
            if i + 1 < nD and t < open_dt[i + 1]:
                for j in js:
                    ANN[i, j] = True
                n_night += 1
            elif i + 1 < nD and open_dt[i + 1] <= t < close_dt[i + 1]:
                for j in js:
                    ANN_INTRA[i + 1, j] = True
                n_intra += 1
            else:
                n_drop += 1

    print(f"8-K 2.02 filings mapped to panel columns: {n_ev:,}", flush=True)
    print(f"  in an overnight window: {n_night:,}   intraday: {n_intra:,}   dropped: {n_drop:,}",
          flush=True)
    print(f"  symbol-nights flagged ANN: {int(ANN.sum()):,}", flush=True)

    # ---- derived: nights since / until an announcement night ----
    BIG = 99
    K_SINCE = np.full((nD, nS), BIG, dtype=np.int16)
    K_UNTIL = np.full((nD, nS), BIG, dtype=np.int16)
    K_UNTIL_PRED = np.full((nD, nS), BIG, dtype=np.int16)

    EV = ANN | ANN_INTRA
    for j in range(nS):
        ev = np.where(EV[:, j])[0]
        if ev.size == 0:
            continue
        # nights since: k = i - ev, for the most recent ev <= i
        last = -1
        cnt = BIG
        for i in range(nD):
            if EV[i, j]:
                last = i
                cnt = 0
            elif last >= 0:
                cnt = min(BIG, i - last)
            K_SINCE[i, j] = cnt
        # nights until (REALISED -- mild lookahead, flagged in the report)
        nxt = -1
        cnt = BIG
        for i in range(nD - 1, -1, -1):
            if EV[i, j]:
                nxt = i
                cnt = 0
            elif nxt >= 0:
                cnt = min(BIG, nxt - i)
            K_UNTIL[i, j] = cnt
        # nights until (PREDICTED, strictly point-in-time): last event + 91 calendar
        # days, snapped to the next panel day.  Uses only filings already public.
        for a, b in zip(ev[:-1], ev[1:]):
            d0 = datetime.date.fromisoformat(days[a])
            pred = d0 + datetime.timedelta(days=91)
            k = bisect.bisect_left(days, pred.isoformat())
            if k >= nD:
                k = nD - 1
            for i in range(a + 1, min(b + 1, nD)):
                K_UNTIL_PRED[i, j] = max(0, min(BIG, k - i))

    np.savez_compressed(WORK / "events.npz", ANN=ANN, ANN_INTRA=ANN_INTRA,
                        K_SINCE=K_SINCE, K_UNTIL=K_UNTIL, K_UNTIL_PRED=K_UNTIL_PRED,
                        days=np.array(days), syms=np.array(syms))
    print("wrote", WORK / "events.npz", flush=True)


# ===========================================================================
# 2. features
# ===========================================================================

def _roll_sum(x, w):
    v = np.isfinite(x)
    xz = np.where(v, x, 0.0)
    cs = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(xz, axis=0)], axis=0)
    cn = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(v, axis=0)], axis=0)
    out = np.full_like(x, np.nan)
    n = np.zeros(x.shape)
    out[w:] = cs[w:-1] - cs[:-1 - w]
    n[w:] = cn[w:-1] - cn[:-1 - w]
    out[n < w * 0.7] = np.nan
    return out


def _roll_std(x, w):
    v = np.isfinite(x)
    xz = np.where(v, x, 0.0)
    cs = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(xz, axis=0)], axis=0)
    cs2 = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(xz * xz, axis=0)], axis=0)
    cn = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(v, axis=0)], axis=0)
    s = np.full_like(x, np.nan); s2 = np.full_like(x, np.nan); n = np.zeros(x.shape)
    s[w:] = cs[w:-1] - cs[:-1 - w]
    s2[w:] = cs2[w:-1] - cs2[:-1 - w]
    n[w:] = cn[w:-1] - cn[:-1 - w]
    with np.errstate(invalid="ignore", divide="ignore"):
        var = s2 / n - (s / n) ** 2
    var[n < w * 0.7] = np.nan
    return np.sqrt(np.maximum(var, 0.0))


def _roll_max_strict(x, w):
    """trailing max over rows [i-w, i-1] (strictly past).  O(nD*nS) with a deque
    would be nicer; the panel is small enough for the simple sliding approach."""
    nD, nS = x.shape
    out = np.full_like(x, np.nan)
    # chunk over columns to keep RSS low
    for a in range(0, nS, 256):
        b = min(nS, a + 256)
        blk = x[:, a:b]
        acc = np.full((w, b - a), np.nan)
        for i in range(1, nD):
            acc[(i - 1) % w] = blk[i - 1]
            if i >= w:
                with np.errstate(invalid="ignore"):
                    out[i, a:b] = np.nanmax(acc, axis=0)
    return out


def _roll_min_strict(x, w):
    return -_roll_max_strict(-x, w)


def load_features():
    z = np.load(PANEL, allow_pickle=False)
    days = [str(d) for d in z["days"]]
    syms = [str(s) for s in z["syms"]]
    O = z["O"].astype(np.float64); C = z["C"].astype(np.float64)
    ON = z["O_next"].astype(np.float64)
    P29 = z["P29"].astype(np.float64); P49 = z["P49"].astype(np.float64)
    P59 = z["P59"].astype(np.float64)
    ADV = z["ADV"].astype(np.float64)
    U500 = z["U500"].astype(bool)
    CA = z["CA"].astype(bool); CA_next = z["CA_next"].astype(bool)
    halfday = z["halfday_exit"].astype(bool)
    del z
    for M in (O, C, ON, P29, P49, P59):
        M[~np.isfinite(M)] = np.nan
        M[M <= 0] = np.nan
    nD, nS = C.shape

    e = np.load(WORK / "events.npz", allow_pickle=False)
    assert [str(d) for d in e["days"]] == days and [str(s) for s in e["syms"]] == syms
    ANN = e["ANN"]; ANN_INTRA = e["ANN_INTRA"]
    K_SINCE = e["K_SINCE"].astype(np.int32)
    K_UNTIL = e["K_UNTIL"].astype(np.int32)
    K_UNTIL_PRED = e["K_UNTIL_PRED"].astype(np.int32)
    del e

    F = {}
    with np.errstate(invalid="ignore", divide="ignore"):
        Cprev = np.full_like(C, np.nan); Cprev[1:] = C[:-1]
        Oprev = np.full_like(O, np.nan); Oprev[1:] = O[:-1]
        F["p20_early"] = P49 / P29 - 1.0
        F["day49"] = P49 / O - 1.0
        F["p10"] = P59 / P49 - 1.0
        F["p30"] = P59 / P29 - 1.0
        F["day59"] = P59 / O - 1.0
        gap = O / Cprev - 1.0
        gap[CA] = np.nan
        gap[np.abs(gap) > 0.5] = np.nan
        F["gap"] = gap
        c2c = C / Cprev - 1.0
        c2c[CA] = np.nan
        c2c[np.abs(c2c) > 0.5] = np.nan
        F["c2c"] = c2c
        F["mom5"] = _roll_sum(c2c, 5)
        F["mom21"] = _roll_sum(c2c, 21)
        F["vol21"] = _roll_std(c2c, 21)
        F["adv"] = ADV

        # split/dividend-clean synthetic price index for the 52-week extremes
        r = np.where(np.isfinite(c2c), c2c, 0.0)
        PX = np.cumprod(1.0 + r, axis=0)
        PX[~np.isfinite(C)] = np.nan
        hi252 = _roll_max_strict(PX, 252)
        lo252 = _roll_min_strict(PX, 252)
        F["px_vs_hi"] = PX / hi252 - 1.0            # 0 at a new high, negative below
        F["px_vs_lo"] = PX / lo252 - 1.0            # 0 at a new low, positive above
        F["hl_pos"] = (PX - lo252) / np.maximum(hi252 - lo252, 1e-9)

    # ---- overnight targets ----
    with np.errstate(invalid="ignore", divide="ignore"):
        RET_A = ON / P59 - 1.0
        RET_B = ON / C - 1.0
    for M in (RET_A, RET_B):
        M[np.abs(M) > 0.5] = np.nan

    # ---- base validity (shared by every config, so the joint null is exact) ----
    need = ["p20_early", "day49", "p10", "p30", "day59", "gap", "mom5", "vol21",
            "adv", "px_vs_hi", "hl_pos"]
    valid = U500 & np.isfinite(RET_A) & np.isfinite(RET_B) & (~CA_next)
    for k in need:
        valid &= np.isfinite(F[k])
    valid &= ~halfday[:, None]
    valid[-1, :] = False

    # ---- the announcement-return features, measured on the announcement night ----
    with np.errstate(invalid="ignore", divide="ignore"):
        ann_ovn = np.where(ANN, RET_A, np.nan)            # the overnight jump itself
        ann_day = np.where(ANN_INTRA, C / O - 1.0, np.nan)
    # carry the most recent announcement return forward, aligned to K_SINCE
    LAST_JUMP = np.full((nD, nS), np.nan)
    src = np.where(ANN, ann_ovn, np.where(ANN_INTRA, ann_day, np.nan))
    cur = np.full(nS, np.nan)
    for i in range(nD):
        m = np.isfinite(src[i])
        cur = np.where(m, src[i], cur)
        LAST_JUMP[i] = cur
    F["last_jump"] = LAST_JUMP
    F["k_since"] = K_SINCE.astype(np.float64)
    F["k_until"] = K_UNTIL.astype(np.float64)
    F["k_until_pred"] = K_UNTIL_PRED.astype(np.float64)
    F["ann"] = ANN
    F["ann_intra"] = ANN_INTRA

    dts = [datetime.date.fromisoformat(d) for d in days]
    calgap = np.ones(nD)
    for i in range(nD - 1):
        calgap[i] = max(1, (dts[i + 1] - dts[i]).days)
    dow = np.array([d.weekday() for d in dts])
    months = np.array([d[:7] for d in days])
    tom = np.zeros(nD, dtype=bool)
    tom_first = np.zeros(nD, dtype=bool)
    tom_last = np.zeros(nD, dtype=bool)
    for m in np.unique(months):
        idx = np.where(months == m)[0]
        tom[idx[:3]] = True
        tom[idx[-1]] = True
        tom_first[idx[:3]] = True
        tom_last[idx[-2:]] = True
    fomc_set = set(FOMC)
    fomc = np.array([d in fomc_set for d in days])
    fomc_eve = np.zeros(nD, dtype=bool)
    fomc_eve[:-1] = fomc[1:]

    j_spy = syms.index("SPY")
    spy_c = C[:, j_spy]
    spy_r = np.full(nD, np.nan); spy_r[1:] = spy_c[1:] / spy_c[:-1] - 1.0
    spy_vol21 = np.full(nD, np.nan)
    for i in range(21, nD):
        w = spy_r[i - 21:i]
        w = w[np.isfinite(w)]
        if w.size >= 15:
            spy_vol21[i] = w.std(ddof=1)

    ctx = {"days": days, "syms": syms, "calgap": calgap, "dow": dow, "tom": tom,
           "tom_first": tom_first, "tom_last": tom_last, "fomc": fomc,
           "fomc_eve": fomc_eve, "spy_vol21": spy_vol21,
           "spy_day": F["day59"][:, j_spy], "j_spy": j_spy}
    return F, RET_A, RET_B, valid, ctx


# ===========================================================================
# 3. cross-sectional helpers (identical arithmetic to T26)
# ===========================================================================

def _xs_z(x, valid):
    xm = np.where(valid, x, np.nan)
    mu = np.nanmean(xm, axis=1, keepdims=True)
    sd = np.nanstd(xm, axis=1, keepdims=True)
    sd[sd == 0] = np.nan
    return (xm - mu) / sd


def _xs_rank(x, valid):
    nD, nS = x.shape
    out = np.full((nD, nS), np.nan)
    xm = np.where(valid, x, np.inf)
    order = np.argsort(xm, axis=1, kind="stable")
    n = valid.sum(axis=1)
    for i in range(nD):
        k = n[i]
        if k < 2:
            continue
        out[i, order[i, :k]] = np.arange(k) / (k - 1.0)
    return out


def _xs_resid(y, x, valid):
    ym = np.where(valid, y, np.nan); xm = np.where(valid, x, np.nan)
    dy = ym - np.nanmean(ym, axis=1, keepdims=True)
    dx = xm - np.nanmean(xm, axis=1, keepdims=True)
    num = np.nansum(dy * dx, axis=1, keepdims=True)
    den = np.nansum(dx * dx, axis=1, keepdims=True)
    den[den == 0] = np.nan
    return dy - (num / den) * dx


def _tercile(x, valid, which):
    r = _xs_rank(x, valid)
    if which == "hi":
        return valid & (r >= 2.0 / 3.0)
    if which == "lo":
        return valid & (r <= 1.0 / 3.0)
    return valid & (r > 1.0 / 3.0) & (r < 2.0 / 3.0)


def weights_decile(sig, sel, cut, min_names=100, fixed_k=None):
    """LONG the lowest `cut` of sig, SHORT the highest (T26's sign convention)."""
    nD, nS = sig.shape
    W = np.zeros((nD, nS))
    sm = np.where(sel & np.isfinite(sig), sig, np.inf)
    order = np.argsort(sm, axis=1, kind="stable")
    n = (sel & np.isfinite(sig)).sum(axis=1)
    for i in range(nD):
        ni = n[i]
        if ni < min_names:
            continue
        k = fixed_k if fixed_k is not None else max(1, int(ni * cut))
        if 2 * k > ni:
            continue
        o = order[i]
        W[i, o[:k]] = 0.5 / k
        W[i, o[ni - k:ni]] = -0.5 / k
    return W


def weights_grouped_decile(sig, sel, cut, groups, min_names=60):
    nD, nS = sig.shape
    W = np.zeros((nD, nS))
    for g in groups:
        W += weights_decile(sig, g, cut, min_names=20)
    live = np.abs(W).sum(axis=1)
    ok = (sel.sum(axis=1) >= min_names) & (live > 0)
    W[~ok] = 0.0
    W[ok] /= live[ok, None]
    return W


def weights_event_vs_xs(ev, sel, sign=+1.0, min_ev=5, min_ctrl=50):
    """+1 : LONG the event names, SHORT the equal-weighted non-event cross-section.
    A dollar-neutral 50/50 book with a genuine short leg (borrow is charged)."""
    nD, nS = ev.shape
    W = np.zeros((nD, nS))
    E = ev & sel
    Ctrl = sel & ~ev
    ne = E.sum(axis=1); nc = Ctrl.sum(axis=1)
    ok = (ne >= min_ev) & (nc >= min_ctrl)
    rows = np.where(ok)[0]
    for i in rows:
        W[i] = np.where(E[i], sign * 0.5 / ne[i], 0.0) + np.where(Ctrl[i], -sign * 0.5 / nc[i], 0.0)
    return W


def weights_within_event(sig, ev, sel, cut=0.30, min_ev=20):
    """rank the SIGNAL inside the event set only; long low, short high."""
    return weights_decile(sig, ev & sel, cut, min_names=min_ev)


def weights_single(nD, nS, j, sign=+1.0):
    W = np.zeros((nD, nS))
    W[:, j] = sign
    return W


# ===========================================================================
# 4. the config table
# ===========================================================================

def build_configs(F, valid, ctx):
    cfg = {}
    V = valid
    nD, nS = V.shape
    allday = np.ones(nD, dtype=bool)

    def add(name, rail, W, dmask=None, short_notional=0.5, note=""):
        cfg[name] = (rail, W, allday if dmask is None else dmask, short_notional, note)

    ANN = F["ann"]
    K_SINCE = F["k_since"]
    K_UNTIL = F["k_until"]
    K_UNTIL_PRED = F["k_until_pred"]
    JUMP = F["last_jump"]

    post1 = (K_SINCE == 1)
    post13 = (K_SINCE >= 1) & (K_SINCE <= 3)
    post15 = (K_SINCE >= 1) & (K_SINCE <= 5)
    post610 = (K_SINCE >= 6) & (K_SINCE <= 10)
    quiet = (K_SINCE > 10) & (K_UNTIL > 10)
    pre15 = (K_UNTIL >= 1) & (K_UNTIL <= 5)
    pre15p = (K_UNTIL_PRED >= 1) & (K_UNTIL_PRED <= 5)
    pre110p = (K_UNTIL_PRED >= 1) & (K_UNTIL_PRED <= 10)

    # ---- coverage-matched base universe -------------------------------------
    # An 8-K Item 2.02 exists only for domestic filers.  ~147 of the 500 point-in-time
    # top-ADV names on a typical day are ETFs or foreign issuers (SPY, QQQ, IWM, LQD,
    # BABA, TSM ...) and can NEVER be an event name.  Shorting "the rest of the
    # cross-section" therefore shorts a permanent ETF/ADR basket -- a factor bet, not
    # an event effect.  Every event-vs-cross-section book below is built inside VC:
    # names that have already filed at least one 8-K 2.02 by that date (point in time).
    covered = (K_SINCE < 99)
    VC = V & covered

    vol_hi = _tercile(F["vol21"], V, "hi")
    vol_lo = _tercile(F["vol21"], V, "lo")
    adv_hi = _tercile(F["adv"], V, "hi")
    adv_lo = _tercile(F["adv"], V, "lo")
    adv_mid = _tercile(F["adv"], V, "mid")

    # ---------------- N: the announcement night itself ----------------
    # sign convention below is EXPLICIT (+1 long the announcers), so a negative
    # result means "short the announcers", and both directions cost the same.
    add("N01_ann_long_vs_xs", "A", weights_event_vs_xs(ANN, VC, +1.0, min_ev=3),
        note="long every name whose 8-K 2.02 lands in tonight's overnight window, short the equal-weighted rest")
    add("N02_ann_long_advneutral", "A", _ann_advneutral(ANN, VC, adv_lo & covered, adv_mid & covered, adv_hi & covered),
        note="N01 built inside each dollar-ADV tercile and pooled (liquidity-neutral)")
    add("N03_ann_long_hivol", "A", weights_event_vs_xs(ANN, vol_hi & covered, +1.0, min_ev=3, min_ctrl=30),
        note="N01 inside the top trailing-vol tercile only")
    add("N04_ann_long_lovol", "A", weights_event_vs_xs(ANN, vol_lo & covered, +1.0, min_ev=3, min_ctrl=30),
        note="N01 inside the bottom trailing-vol tercile only")
    add("N05_ann_long_hiadv", "A", weights_event_vs_xs(ANN, adv_hi & covered, +1.0, min_ev=3, min_ctrl=30),
        note="N01 inside the top dollar-ADV tercile only")
    add("N06_ann_long_loadv", "A", weights_event_vs_xs(ANN, adv_lo & covered, +1.0, min_ev=3, min_ctrl=30),
        note="N01 inside the bottom dollar-ADV tercile only")
    add("N07_ann_p10_fade", "A", weights_within_event(F["p10"], ANN, V, 0.33, min_ev=10),
        note="among tonight's announcers ONLY, fade the 15:49->15:59 move (T3 inside the event set)")
    add("N08_ann_day_fade", "A", weights_within_event(F["day59"], ANN, V, 0.33, min_ev=10),
        note="among tonight's announcers ONLY, fade the full open->15:59 session move")
    add("N09_ann_runup_fade", "A", weights_within_event(F["mom5"], ANN, V, 0.33, min_ev=10),
        note="among tonight's announcers ONLY, fade the 5-day run-up into the print")
    add("N10_ann_hl_fade", "A", weights_within_event(F["hl_pos"], ANN, V, 0.33, min_ev=10),
        note="among tonight's announcers ONLY, long the ones nearest their 52w LOW, short nearest the 52w HIGH")
    add("N11_ann_long_moclegal", "B", weights_event_vs_xs(ANN, VC, +1.0, min_ev=3),
        note="N01 executed MOC-legal: closing auction in, opening auction out")

    # ---------------- P: pre-announcement drift ----------------
    add("P01_pre15_long", "A", weights_event_vs_xs(pre15 & ~ANN, VC, +1.0, min_ev=20),
        note="long names 1-5 sessions BEFORE a realised announcement (realised date, pre-announcement drift)")
    add("P02_pre15pred_long", "A", weights_event_vs_xs(pre15p & ~ANN, VC, +1.0, min_ev=20),
        note="P01 with the STRICTLY point-in-time predicted date (last filing + 91 calendar days)")
    add("P03_pre110pred_long", "A", weights_event_vs_xs(pre110p & ~ANN, VC, +1.0, min_ev=20),
        note="long names 1-10 sessions before the PREDICTED announcement")
    add("P04_pre_p10_fade", "A", weights_within_event(F["p10"], pre15p & ~ANN, V, 0.30, min_ev=30),
        note="T3 pressure fade restricted to the 5 sessions before a predicted announcement")

    # ---------------- D: post-announcement overnight drift ----------------
    add("D01_pead1_cont", "A", weights_within_event(-JUMP, post1, V, 0.30, min_ev=15),
        note="night 1 after the print: LONG the biggest positive announcement jump, short the biggest negative (PEAD in the overnight leg)")
    add("D02_pead1_rev", "A", weights_within_event(JUMP, post1, V, 0.30, min_ev=15),
        note="night 1 after the print: the reversal sign of D01")
    add("D03_pead13_cont", "A", weights_within_event(-JUMP, post13, V, 0.30, min_ev=25),
        note="nights 1-3 after the print, continuation of the announcement jump")
    add("D04_pead15_cont", "A", weights_within_event(-JUMP, post15, V, 0.30, min_ev=25),
        note="nights 1-5 after the print, continuation of the announcement jump")
    add("D05_pead610_cont", "A", weights_within_event(-JUMP, post610, V, 0.30, min_ev=25),
        note="nights 6-10 after the print, continuation (does the drift survive the first week?)")
    add("D06_pead15_c10", "A", weights_within_event(-JUMP, post15, V, 0.10, min_ev=40),
        note="D04 at a 10 % tail cut instead of 30 %")
    add("D07_pead15_resid_day", "A",
        weights_within_event(-_xs_resid(JUMP, F["day59"], post15 & V), post15, V, 0.30, min_ev=25),
        note="D04 on the cross-sectional residual of the jump on the same-session move")
    add("D08_pead15_z_over_vol", "A",
        weights_within_event(-JUMP / np.maximum(F["vol21"], 1e-5), post15, V, 0.30, min_ev=25),
        note="D04 with the jump risk-normalised by 21d realised vol")
    add("D09_pead_long_vs_xs", "A", weights_event_vs_xs(post15 & (JUMP > 0) & ~ANN, VC, +1.0, min_ev=15),
        note="long ONLY the positive-surprise names in nights 1-5, short the cross-section")
    add("D10_pead_short_vs_xs", "A", weights_event_vs_xs(post15 & (JUMP < 0) & ~ANN, VC, -1.0, min_ev=15),
        note="SHORT ONLY the negative-surprise names in nights 1-5, long the cross-section")
    add("D11_pead13_moclegal", "B", weights_within_event(-JUMP, post13, V, 0.30, min_ev=25),
        note="D03 executed MOC-legal (closing auction in, opening auction out)")
    add("D12_pead15_advneutral", "A",
        weights_grouped_decile(-JUMP, post15 & V, 0.30,
                               [post15 & adv_lo, post15 & adv_mid, post15 & adv_hi], min_names=25),
        note="D04 ranked within dollar-ADV terciles and pooled")
    # --- the unsigned controls: is the driver the SURPRISE or merely "recently reported"? ---
    add("D13_post15_long_vs_xs", "A", weights_event_vs_xs(post15 & ~ANN, VC, +1.0, min_ev=10),
        note="CONTROL: long EVERY name 1-5 nights after a print, irrespective of the surprise sign, short the cross-section")
    add("D14_pead_neg_long_vs_xs", "A", weights_event_vs_xs(post15 & (JUMP < 0) & ~ANN, VC, +1.0, min_ev=10),
        note="long ONLY the negative-surprise names in nights 1-5, short the cross-section")
    add("D15_post110_long_vs_xs", "A",
        weights_event_vs_xs(((K_SINCE >= 1) & (K_SINCE <= 10)) & ~ANN, VC, +1.0, min_ev=10),
        note="CONTROL: D13 over nights 1-10 instead of 1-5")
    add("D16_post1120_long_vs_xs", "A",
        weights_event_vs_xs(((K_SINCE >= 11) & (K_SINCE <= 20)) & ~ANN, VC, +1.0, min_ev=10),
        note="PLACEBO: long names 11-20 nights after a print -- the attention window should be over")
    add("D17_absjump_fade", "A", weights_within_event(np.abs(JUMP), post15, V, 0.30, min_ev=15),
        note="among post-print names, long the SMALLEST absolute surprise, short the largest (an attention, not a direction, sort)")

    # ---------------- X: the confound probe itself ----------------
    add("X01_covered_vs_uncovered", "A",
        weights_event_vs_xs(covered & (K_SINCE > 20), V, +1.0, min_ev=50, min_ctrl=30),
        note="CONFOUND PROBE, not a strategy: long domestic 8-K filers with no print in 20 sessions, short the ETF/ADR remainder of the top-500-ADV screen")

    # ---------------- G: gap conditioned on whether news arrived overnight ----------------
    add("G01_gapfade_postann", "A", weights_within_event(F["gap"], post1, V, 0.30, min_ev=15),
        note="fade this morning's realised close-to-open gap, restricted to names that announced LAST night")
    add("G02_gapfade_quiet", "A", weights_decile(F["gap"], quiet & V, 0.10, min_names=60),
        note="the same gap fade on names with NO announcement within +-10 sessions")
    add("G03_gapfade_all", "A", weights_decile(F["gap"], V, 0.10),
        note="the unconditional gap fade (T26's A25, repeated here as the reference)")

    # ---------------- T: T3 conditioned ON / OFF the event ----------------
    add("T01_p10_quiet", "A", weights_decile(F["p10"], quiet & V, 0.10, min_names=60),
        note="T3 pressure fade restricted to names with NO announcement within +-10 sessions")
    add("T02_p10_post15", "A", weights_within_event(F["p10"], post15, V, 0.20, min_ev=25),
        note="T3 pressure fade restricted to the 5 sessions after a print")
    add("T03_p10_annnight_excl", "A", weights_decile(F["p10"], V & ~ANN, 0.10, min_names=100),
        note="T3 pressure fade with tonight's announcers REMOVED from the book")

    # ---------------- H: 52-week extremes ----------------
    newhi = V & (F["px_vs_hi"] >= -1e-9)
    newlo = V & (F["px_vs_lo"] <= 1e-9)
    add("H01_newhi_cont", "A", weights_event_vs_xs(newhi, V, +1.0, min_ev=5),
        note="long names printing a new 252-day closing high today, short the cross-section, overnight")
    add("H02_newlo_cont", "A", weights_event_vs_xs(newlo, V, -1.0, min_ev=5),
        note="short names printing a new 252-day closing low today, long the cross-section")
    add("H03_hl_pos_fade", "A", weights_decile(F["hl_pos"], V, 0.10),
        note="continuous 52-week range position: long the bottom decile, short the top decile, overnight")
    add("H04_hl_pos_cont", "A", weights_decile(-F["hl_pos"], V, 0.10),
        note="the continuation sign of H03")
    add("H05_newhi_p10_fade", "A", weights_within_event(F["p10"], newhi, V, 0.30, min_ev=15),
        note="T3 pressure fade restricted to names at a new 52-week high")
    add("H06_newhi_moclegal", "B", weights_event_vs_xs(newhi, V, +1.0, min_ev=5),
        note="H01 executed MOC-legal")

    # ---------------- R: liquidity-rank promotion (the free proxy for an index add) ----------------
    prom = np.zeros_like(V)
    dm = np.array([d[:7] for d in ctx["days"]])
    months = np.unique(dm)
    memb = {m: V[np.where(dm == m)[0]].any(axis=0) for m in months}
    for k in range(1, len(months)):
        idx = np.where(dm == months[k])[0]
        prom[idx[:5], :] = (~memb[months[k - 1]])[None, :]
    prom &= V
    add("R01_rankpromote", "A", weights_event_vs_xs(prom, V, +1.0, min_ev=3),
        note="PROXY for an index add: names newly entering the point-in-time top-500-ADV screen, first 5 sessions of the month, long vs the cross-section")
    add("R02_rankpromote_p10", "A", weights_within_event(F["p10"], prom, V, 0.30, min_ev=10),
        note="T3 pressure fade restricted to newly promoted names")

    # ---------------- M: calendar events, single-instrument overnight ----------------
    j = ctx["j_spy"]
    W_spy = weights_single(nD, nS, j, +1.0)
    add("M01_spy_tom_first", "A", W_spy, ctx["tom_first"], 0.0,
        note="long SPY overnight on the first 3 sessions of a month (turn-of-month), one half-spread in, auction out")
    add("M02_spy_tom_last", "A", W_spy, ctx["tom_last"], 0.0,
        note="long SPY overnight on the last 2 sessions of a month")
    add("M03_spy_fomc_eve", "A", W_spy, ctx["fomc_eve"], 0.0,
        note="long SPY overnight into an FOMC decision day (the pre-FOMC announcement drift, overnight leg)")
    add("M04_spy_fomc_night", "A", W_spy, ctx["fomc"], 0.0,
        note="long SPY overnight AFTER an FOMC decision")
    add("M05_spy_alln", "A", W_spy, None, 0.0,
        note="unconditional long SPY overnight -- the benchmark every calendar cut has to beat")
    add("M06_spy_tom_moclegal", "B", W_spy, ctx["tom_first"], 0.0,
        note="M01 executed with an MOC order instead of a marketable 15:59 buy")

    return cfg


def _ann_advneutral(ANN, V, adv_lo, adv_mid, adv_hi):
    nD, nS = V.shape
    W = np.zeros((nD, nS))
    for g in (adv_lo, adv_mid, adv_hi):
        W += weights_event_vs_xs(ANN, g, +1.0, min_ev=2, min_ctrl=20)
    live = np.abs(W).sum(axis=1)
    ok = live > 0
    W[ok] /= live[ok, None]
    return W


# ===========================================================================
# 5. evaluation
# ===========================================================================

def evaluate(W, dmask, rail, short_notional, RET_A, RET_B, ctx, rows, half_spread_bp,
             auction_bp=AUCTION_LEG_BP, borrow_bp=BORROW_ANNUAL_BP):
    RET = RET_A if rail == "A" else RET_B
    R = np.where(np.isfinite(RET), RET, 0.0)
    live = (np.abs(W).sum(axis=1) > 0) & dmask
    sel = rows & live
    if sel.sum() < 30:
        return None
    gross = (W[sel] * R[sel]).sum(axis=1)
    entry = half_spread_bp if rail == "A" else auction_bp
    turn = np.abs(W[sel]).sum(axis=1)
    cost = turn * (entry + auction_bp) / 1e4
    if short_notional > 0:
        cost = cost + short_notional * (borrow_bp / 1e4) * ctx["calgap"][sel] / 365.25
    net = gross - cost
    return {"dates": np.array(ctx["days"])[sel], "gross": gross, "net": net, "cost": cost}


def stats(x):
    n = int(x.size)
    mu = float(np.mean(x)); sd = float(np.std(x, ddof=1)) if n > 2 else 0.0
    if sd == 0 or n < 3:
        return {"n": n, "mean_bp": mu * 1e4, "sharpe": 0.0, "t": 0.0}
    return {"n": n, "mean_bp": mu * 1e4, "sd_bp": sd * 1e4,
            "sharpe": mu / sd * math.sqrt(252.0), "t": mu / (sd / math.sqrt(n)),
            "hit": float((x > 0).mean())}


def window_rows(days, lo, hi):
    d = np.array(days)
    return (d >= lo) & (d <= hi)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "design"
    if cmd == "events":
        build_events()
        return
    F, RET_A, RET_B, valid, ctx = load_features()
    print(f"valid symbol-nights: {int(valid.sum()):,}", flush=True)
    cfg = build_configs(F, valid, ctx)
    print(f"configs: {len(cfg)}", flush=True)
    rows_design = window_rows(ctx["days"], DESIGN_START, DESIGN_END)
    rows_test = window_rows(ctx["days"], TEST_START, TEST_END)

    if cmd == "design":
        res = {}
        for name, (rail, W, dmask, sn, note) in cfg.items():
            r = evaluate(W, dmask, rail, sn, RET_A, RET_B, ctx, rows_design,
                         HALF_SPREAD_DESIGN_BP)
            if r is None:
                print(f"  {name}: too few nights", flush=True)
                continue
            res[name] = {"rail": rail, "note": note, "short_notional": sn,
                         "net": stats(r["net"]), "gross": stats(r["gross"]),
                         "mean_cost_bp": float(np.mean(r["cost"]) * 1e4)}
            s = res[name]
            print(f"  {name:24s} {rail} n={s['net']['n']:5d} net {s['net']['mean_bp']:+8.2f}bp "
                  f"SR {s['net']['sharpe']:+6.2f} t {s['net']['t']:+5.2f}  gross SR "
                  f"{s['gross']['sharpe']:+6.2f}", flush=True)
            np.save(WORK / f"net_design_{name}.npy", r["net"])
        json.dump(res, open(WORK / "design_results.json", "w"), indent=1)
        print("design sweep written", flush=True)

    elif cmd == "null":
        reps = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        rng = np.random.default_rng(20260820)
        names = list(cfg)
        drow = np.where(rows_design)[0]
        RA = np.where(np.isfinite(RET_A), RET_A, 0.0)[drow]
        RB = np.where(np.isfinite(RET_B), RET_B, 0.0)[drow]
        VD = valid[drow]
        vidx = [np.where(VD[i])[0] for i in range(VD.shape[0])]
        prep = []
        for name in names:
            rail, W, dmask, sn, note = cfg[name]
            live = ((np.abs(W).sum(axis=1) > 0) & dmask & rows_design)[drow]
            li = np.where(live)[0]
            if li.size < 50:
                continue
            prep.append((name, rail, W[drow][li], li))
        maxes, maxt = [], []
        per_name = {p[0]: [] for p in prep}
        for b in range(reps):
            PA, PB = RA.copy(), RB.copy()
            for i in range(VD.shape[0]):
                ix = vidx[i]
                if ix.size < 2:
                    continue
                perm = rng.permutation(ix.size)
                PA[i, ix] = RA[i, ix[perm]]
                PB[i, ix] = RB[i, ix[perm]]
            best, bestt = -9e9, -9e9
            for name, rail, Wl, li in prep:
                P = PA if rail == "A" else PB
                g = (Wl * P[li]).sum(axis=1)
                sd = g.std(ddof=1)
                if sd == 0:
                    s = t = 0.0
                else:
                    s = g.mean() / sd * math.sqrt(252.0)
                    t = g.mean() / (sd / math.sqrt(g.size))
                per_name[name].append(abs(s))
                best = max(best, abs(s)); bestt = max(bestt, abs(t))
            maxes.append(best); maxt.append(bestt)
            if (b + 1) % 25 == 0:
                print(f"  null rep {b+1}/{reps} max|SR| p50={np.quantile(maxes,.5):.3f} "
                      f"p95={np.quantile(maxes,.95):.3f} | max|t| p50={np.quantile(maxt,.5):.2f} "
                      f"p95={np.quantile(maxt,.95):.2f}", flush=True)

        def q(v):
            return {"mean": float(np.mean(v)), "p50": float(np.quantile(v, .5)),
                    "p90": float(np.quantile(v, .9)), "p95": float(np.quantile(v, .95)),
                    "p99": float(np.quantile(v, .99)), "max": float(np.max(v))}
        out = {"reps": reps, "n_configs": len(prep), "two_sided": True,
               "max_abs_sharpe_null": q(maxes), "max_abs_t_null": q(maxt),
               "per_name_sd": {n: float(np.std(v, ddof=1)) for n, v in per_name.items()},
               "per_name_p95": {n: float(np.quantile(v, .95)) for n, v in per_name.items()}}
        json.dump(out, open(WORK / "null_results.json", "w"), indent=1)
        print(json.dumps({"max_abs_sharpe_null": out["max_abs_sharpe_null"],
                          "max_abs_t_null": out["max_abs_t_null"]}, indent=1), flush=True)

    elif cmd == "heldout":
        picks = sys.argv[2:]
        res = {}
        for name in picks:
            rail, W, dmask, sn, note = cfg[name]
            r = evaluate(W, dmask, rail, sn, RET_A, RET_B, ctx, rows_test, HALF_SPREAD_TEST_BP)
            if r is None:
                print(f"  {name}: too few nights"); continue
            r2 = evaluate(W, dmask, rail, sn, RET_A, RET_B, ctx, rows_test,
                          HALF_SPREAD_TEST_BP * 2, auction_bp=AUCTION_LEG_BP * 2,
                          borrow_bp=BORROW_ANNUAL_BP * 3)
            r0 = evaluate(W, dmask, rail, sn, RET_A, RET_B, ctx, rows_test, 0.0,
                          auction_bp=0.0, borrow_bp=0.0)
            res[name] = {"rail": rail, "note": note, "net": stats(r["net"]),
                         "gross": stats(r0["net"]), "net_2x_cost": stats(r2["net"]),
                         "mean_cost_bp": float(np.mean(r["cost"]) * 1e4)}
            s = res[name]
            print(f"  {name:24s} HELD OUT n={s['net']['n']:5d} net {s['net']['mean_bp']:+8.2f}bp "
                  f"SR {s['net']['sharpe']:+6.2f} t {s['net']['t']:+5.2f} | 2x-cost SR "
                  f"{s['net_2x_cost']['sharpe']:+6.2f} | zero-cost SR {s['gross']['sharpe']:+6.2f}",
                  flush=True)
            np.save(WORK / f"net_test_{name}.npy", r["net"])
        p = WORK / "heldout_results.json"
        prev = json.load(open(p)) if p.exists() else {}
        prev.update(res)
        json.dump(prev, open(p, "w"), indent=1)
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
