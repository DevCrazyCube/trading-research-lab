#!/usr/bin/env python3
"""Coiled Leverage Expansion (Pick #2) -- GATE 0: the realised R-multiple distribution.

FROZEN SPEC: research/trading_bot/ORIGINAL_STRATEGY_SHORTLIST.md 6.1-6.9, gate 0.

    "On the design window only, with the ratcheting 1-ATR trail in place, measure:
       W = realised mean win in R-units.
       L = realised mean loss in R-units, including B22B stop slippage.
       break-even hit rate p* = L/(W+L) plus the friction term 12bp/(R*(W+L)).
     DEAD if the measured design-window hit rate is below p* + 3pp."

This is NOT a zero-friction signal census (that is Pick 1's gate 0). Pick 2's gate 0 is the
realised trailing-stop trade simulation, because the whole candidate turns on whether the
hit rate clears the trail-implied break-even. So the harness actually SIMULATES every trade:
entry at open of bar t+1, ratcheting 1-ATR stop, hard 6h exit, B22B stop-slippage on stop-outs.

--------------------------------------------------------------------------------------------
FROZEN, OBEYED HERE
--------------------------------------------------------------------------------------------
* Instrument: Binance USD-M USDT perps, 5-min bars, 6h holds (72 bars).
* Universe: point-in-time top-80 by trailing-30d quote vol (membership from the cached
  universe.json), RESTRICTED to the ATR tier -- trailing-30d median 1h-ATR >= 45 bp as of
  each month-start (6.1). Applied point-in-time, per symbol-month.
* Signal (6.3), symbol i bar t:
    D(i,t)  = log(sum_toptrader_long_short_ratio) - log(count_long_short_ratio)
    C(i,t)  = zscore_24h(sum_open_interest_value) [op] zscore_24h(realised 5-min vol)
    trigger = C in own trailing-30d top decile
              AND |D| in own trailing-30d top decile
              AND the bar's range breaks the trailing-12-bar high (long) / low (short)
                  in the direction of sign(D).
  entry at open of bar t+1, WITH-TREND in sign(D). One entry per coin per 6h. <=20 concurrent
  (concurrency does not bind gate-0's per-trade distribution; the >=20 cap is a sizing rule and
  is enforced in the power/Gate-1 arms, not here -- gate 0 measures the *unconstrained* per-trade
  R distribution, which the cap cannot improve).
* Stop: resting 1 x trailing-1h-ATR, ratcheting behind the trade, never widened. R = 1 x ATR
  at entry (6.4). Exit: stop, or hard 6h time exit.
* Estimand: realised R-multiple per trade, on the ATR>=45bp tier only. Stop slippage from B22B.

--------------------------------------------------------------------------------------------
DECLARED IMPLEMENTATION RESOLUTIONS (ambiguous / internally-inconsistent frozen spec points,
resolved and recorded -- mirroring the sibling harness's practice)
--------------------------------------------------------------------------------------------
(R1) COIL OPERATOR. 6.3 writes C = "z-score of OI over 24h DIVIDED BY the z-score of 24h
     realised volatility" AND "High C = OI built while volatility compressed". These two are
     INTERNALLY INCONSISTENT under literal division: coiled => OI_z>0 and vol_z<0 (vol below
     its 24h norm), so OI_z/vol_z is a large NEGATIVE number, which is the BOTTOM decile, not
     the top. The stated intent ("high C = coiled") and the stated selection ("C in top
     decile") can only both hold if C rises when OI_z rises and vol_z falls. We therefore run
     BOTH and report both, so the gate-0 verdict is robust to the reading:
       --coil-mode diff  (PRIMARY): C = OI_z - vol_z   (intent-consistent; top decile = coiled)
       --coil-mode ratio (LITERAL): C = OI_z / vol_z   (as written; top decile literally)
(R2) realised 5-min volatility at bar t = std of the trailing 12 (1h) 5-min log returns; its
     24h z-score uses the trailing 288-bar (24h) mean/sd ending AT t. OI z-score likewise uses
     the trailing 288-bar window ending AT t. (Both known at bar-t close; entry is t+1 open.)
(R3) "trailing-30d top decile" = C(t) (resp |D(t)|) >= the 90th percentile of C (resp |D|)
     over the strictly-prior 30-day window [t-8640 .. t-1]. Ends at t-1 (no self-inclusion),
     mirroring the sibling's decile window.
(R4) 1h ATR = ATR-14 on 1h bars (12x5min), true-range definition; the value at entry is the
     most recent COMPLETED 1h bar's ATR (causal). R_bp = ATR/entry_price * 1e4.
(R5) trailing-12-bar breakout: long iff high[t] > max(high[t-12..t-1]); short iff
     low[t] < min(low[t-12..t-1]). Trigger requires the breakout side to equal sign(D).
(R6) B22B stop slippage. 6.7 cites "p90 233 bp, p95 420 bp" which are B22B's r_bp figures
     (basis points of R, R=10%ATR). Carried into TRUE PRICE space they are B22B's
     notional_centibp distribution (p90 0.92bp, p95 2.49bp, max 8.99bp of fill price) -- tiny.
     We sample adverse price-bp from a percentile-anchored reconstruction of notional_centibp
     and add it to stop-out losses (converted to R via /ATR_bp). Slippage does NOT affect the
     hit rate (a loss stays a loss); it only deepens L. We report L and p* WITH and WITHOUT it.

DESIGN WINDOW: 6.6 freezes 2020-09-01 -> 2023-12-31. The cached metrics panel currently spans
2022-10 -> 2024-12 (it was built for Pick 1's 2023-24 window). This harness runs on whatever
slice of the design window is present and REPORTS the covered dates explicitly; a detached
backfill extends coverage to 2020-09. Gate 0 is a distributional measurement (W,L,hit-rate)
that converges on thousands of trades, so the covered slice yields a real kill/pass read; the
verdict is reported as "on the covered design slice" until the backfill completes.

USAGE
    python3 scripts/trading_bot/coiled_gate0.py                       # diff (primary) + ratio
    python3 scripts/trading_bot/coiled_gate0.py --coil-mode diff
    python3 scripts/trading_bot/coiled_gate0.py --entry-offset 2      # iff OI latency > 60s
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import orphanflush_gate0 as G  # noqa: E402  reuse validated IO/rolling machinery

CACHE = G.CACHE
RAW = G.RAW
UNIVERSE = CACHE / "universe.json"
B22B = pathlib.Path(__file__).resolve().parents[2] / "research" / "B22B_SLIPPAGE_RESULT.json"
RESULT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot" / "COILED_GATE0_RESULT.json"

BAR_MS = G.BAR_MS
BARS_1H = 12
BARS_24H = G.BARS_24H          # 288
BARS_30D = G.BARS_30D          # 8640
ATR_N = 14                     # ATR-14 on 1h bars
RV_WIN = 12                    # realised-vol window (1h of 5-min returns)
HOLD_BARS = 72                 # hard 6h time exit
DECILE_PCT = 90.0              # top decile
ATR_TIER_MIN_BP = 45.0         # 6.1 universe ATR screen
FRICTION_BP = 12.0             # 6.7 round-trip fees+spread
DESIGN_WINDOW = ("2020-09-01", "2023-12-31")   # 6.6 frozen
GATE0_MARGIN = 0.03            # DEAD if hit_rate < p* + 3pp
BASE_SYMBOL = G.BASE_SYMBOL


# ------------------------------------------------------------------ B22B stop-slippage sampler
def _load_b22b_centibp():
    """Percentile-anchored empirical sampler of B22B notional_centibp (adverse price slippage,
    positive=adverse, in hundredths of a bp). Returns a fn rng->float bp. Immaterial to the
    verdict (max ~9bp) but implemented faithfully per 6.7."""
    d = json.loads(B22B.read_text())["notional_centibp"]["0"]
    # anchors: (cum_prob, value_centibp). Below p10 we clamp at min (favourable tail ignored for a
    # cost charge -> use 0 as the favourable-side floor so slippage is never a *credit*).
    anchors = [(0.10, 0.0), (0.25, 0.0), (0.50, 0.0), (0.75, 0.0),
               (0.90, d["p90"]), (0.95, d["p95"]), (1.00, d["max"])]

    def sample(rng: np.random.Generator) -> float:
        u = rng.random()
        prev_p, prev_v = 0.0, 0.0
        for p, v in anchors:
            if u <= p:
                if p == prev_p:
                    return max(v, 0.0) / 100.0
                frac = (u - prev_p) / (p - prev_p)
                val = prev_v + frac * (v - prev_v)
                return max(val, 0.0) / 100.0
            prev_p, prev_v = p, v
        return max(d["max"], 0.0) / 100.0
    return sample


# ------------------------------------------------------------------ klines with high/low
def load_klines5m_hl(sym: str, months: list[str]) -> dict[int, tuple]:
    """open_time(ms) -> (open, high, low, close, quote_volume)."""
    out: dict[int, tuple] = {}
    d = RAW / "klines5m" / sym
    if not d.exists():
        return out
    for ym in months:
        p = d / f"{sym}-5m-{ym}.zip"
        if not (p.exists() and p.stat().st_size > 0):
            continue
        for row in G._read_zip_csv(p):
            if G._is_header(row):
                continue
            try:
                out[G._norm_ms(row[0])] = (float(row[1]), float(row[2]), float(row[3]),
                                           float(row[4]), float(row[7]))
            except (ValueError, IndexError):
                pass
    return out


def load_metrics_full(sym: str, days: list[str]) -> dict[int, tuple]:
    """create_time(ms) -> (sum_open_interest_value, sum_toptrader_ls, count_ls)."""
    out: dict[int, tuple] = {}
    d = RAW / "metrics" / sym
    if not d.exists():
        return out
    for day in days:
        p = d / f"{sym}-metrics-{day}.zip"
        if not (p.exists() and p.stat().st_size > 0):
            continue
        for row in G._read_zip_csv(p):
            if row[0] == "create_time":
                continue
            try:
                t = int(dt.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                        .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
                out[t] = (float(row[3]), float(row[5]), float(row[6]))
            except (ValueError, IndexError):
                pass
    return out


# ------------------------------------------------------------------ causal rolling helpers
def _roll_mean_std_incl(x: np.ndarray, win: int):
    """mean,std over window [t-win+1 .. t] INCLUSIVE (ends AT t). NaN if <win valid in window."""
    n = x.size
    valid = np.isfinite(x).astype(np.float64)
    xz = np.where(np.isfinite(x), x, 0.0)
    cs = np.concatenate([[0.0], np.cumsum(xz)])
    cs2 = np.concatenate([[0.0], np.cumsum(xz * xz)])
    cv = np.concatenate([[0.0], np.cumsum(valid)])
    mean = np.full(n, np.nan)
    std = np.full(n, np.nan)
    if n < win:
        return mean, std
    t = np.arange(win - 1, n)
    lo = t - win + 1
    cnt = cv[t + 1] - cv[lo]
    s = cs[t + 1] - cs[lo]
    s2 = cs2[t + 1] - cs2[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        m = s / cnt
        var = s2 / cnt - m * m
    good = (cnt >= win) & (var > 0)
    mm = np.full(t.size, np.nan); ss = np.full(t.size, np.nan)
    mm[cnt >= win] = m[cnt >= win]
    ss[good] = np.sqrt(var[good])
    mean[t] = mm; std[t] = ss
    return mean, std


def _seg_reduce(vals, seg_id, nseg, kind):
    """Grouped max/min over contiguous-labelled segments, vectorized."""
    out = np.full(nseg, -np.inf if kind == "max" else np.inf)
    if kind == "max":
        np.maximum.at(out, seg_id, vals)
    else:
        np.minimum.at(out, seg_id, vals)
    return out


def build_1h_atr(t, o, h, l, c):
    """Return (atr_px, atr_bp) aligned to the 5-min grid: at each 5-min bar, the ATR-14 (price and
    bp) of the most recent COMPLETED prior 1h bar (causal). 1h bars align to UTC hour boundaries."""
    n = t.size
    hour = (t // 3_600_000).astype(np.int64)
    uh, seg = np.unique(hour, return_inverse=True)   # seg: bar -> hour-segment index
    seg = seg.ravel()
    nseg = uh.size
    first_idx = np.zeros(nseg, dtype=np.int64)
    first_idx[seg[0]] = 0
    change = np.flatnonzero(np.diff(seg) != 0) + 1
    first_idx[seg[change]] = change
    last_idx = np.empty(nseg, dtype=np.int64)
    last_idx[:-1] = first_idx[1:] - 1
    last_idx[-1] = n - 1
    hh = _seg_reduce(h, seg, nseg, "max")
    hl = _seg_reduce(l, seg, nseg, "min")
    hc = c[last_idx]
    prev_close = np.concatenate([[np.nan], hc[:-1]])
    contig = np.concatenate([[False], np.diff(uh) == 1])
    tr = np.maximum(hh - hl, np.maximum(np.abs(hh - prev_close), np.abs(hl - prev_close)))
    tr[~contig] = (hh - hl)[~contig]
    # ATR-14 = trailing mean of TR over 14 CONTIGUOUS completed hours (mean via cumsum)
    cs = np.concatenate([[0.0], np.cumsum(tr)])
    # gaps: hour k is a discontinuity if contig[k] is False (k>=1). The 14-hour window ending at k
    # is fully contiguous iff there is no discontinuity in hours (k-12 .. k), i.e. contig True there.
    gap = (~contig).astype(np.float64)               # 1 where a hour boundary is broken
    gcs = np.concatenate([[0.0], np.cumsum(gap)])
    atr = np.full(nseg, np.nan)
    if nseg >= ATR_N:
        idx = np.arange(ATR_N - 1, nseg)
        # count of gaps within (k-12 .. k) inclusive == gcs[k+1]-gcs[k-12]
        gaps_in = gcs[idx + 1] - gcs[idx - (ATR_N - 2)]
        vals = (cs[idx + 1] - cs[idx + 1 - ATR_N]) / ATR_N
        vals[gaps_in > 0] = np.nan
        atr[idx] = vals
    atr_bp_hour = atr / hc * 1e4
    # map each 5-min bar to the PRIOR completed hour's ATR
    prev_atr = np.concatenate([[np.nan], atr[:-1]])
    prev_atr_bp = np.concatenate([[np.nan], atr_bp_hour[:-1]])
    return prev_atr[seg], prev_atr_bp[seg]


def rolling_p90_prior(x: np.ndarray, win: int, pct: float, min_valid: int) -> np.ndarray:
    """out[j] = pct-percentile of x[j-win .. j-1] (STRICTLY PRIOR window, ending at j-1), NaN-aware.
    NaN where fewer than min_valid finite values in the window. Chunked sliding-window."""
    n = x.size
    out = np.full(n, np.nan)
    if n <= win:
        return out
    swv = np.lib.stride_tricks.sliding_window_view(x, win)   # row k -> x[k .. k+win-1]
    # row k ends at k+win-1; we want out[j] from window ending at j-1 -> k = j-win
    valid = np.isfinite(swv).sum(axis=1)
    res = np.full(swv.shape[0], np.nan)
    step = 4000
    import warnings as _w
    with np.errstate(invalid="ignore"), _w.catch_warnings():
        _w.simplefilter("ignore", RuntimeWarning)
        for a in range(0, swv.shape[0], step):
            b = min(a + step, swv.shape[0])
            res[a:b] = np.nanpercentile(swv[a:b], pct, axis=1)
    res[valid < min_valid] = np.nan
    # out[j] = res[j-win] for j in [win .. n-1]
    out[win:] = res[:n - win]
    return out


# ------------------------------------------------------------------ per-symbol trigger + sim
def simulate_symbol(sym, base_membership, months, coil_mode, entry_offset, slip_sampler, rng, audit):
    k = load_klines5m_hl(sym, months)
    if not k:
        return []
    md = load_metrics_full(sym, G._days_for(months))
    t = np.array(sorted(k), dtype=np.int64)
    o = np.array([k[x][0] for x in t]); h = np.array([k[x][1] for x in t])
    l = np.array([k[x][2] for x in t]); c = np.array([k[x][3] for x in t])
    n = t.size
    oi = np.array([md.get(int(x), (np.nan,) * 3)[0] for x in t])
    tt = np.array([md.get(int(x), (np.nan,) * 3)[1] for x in t])
    cl = np.array([md.get(int(x), (np.nan,) * 3)[2] for x in t])
    contig = np.concatenate([[False], np.diff(t) == BAR_MS])

    # returns for realised vol
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.log(c / np.roll(c, 1))
    r[~contig] = np.nan

    # D = log(toptrader_ls) - log(count_ls)
    with np.errstate(divide="ignore", invalid="ignore"):
        D = np.log(tt) - np.log(cl)

    # realised vol rv[t] = std of last 12 5-min returns (ending at t)
    _, rv = _roll_mean_std_incl(r, RV_WIN)
    # z-scores over trailing 24h (ending at t)
    oi_mean, oi_std = _roll_mean_std_incl(oi, BARS_24H)
    rv_mean, rv_std = _roll_mean_std_incl(rv, BARS_24H)
    with np.errstate(divide="ignore", invalid="ignore"):
        oi_z = (oi - oi_mean) / oi_std
        vol_z = (rv - rv_mean) / rv_std
    if coil_mode == "diff":
        C = oi_z - vol_z
    else:  # ratio (literal)
        C = np.where(np.abs(vol_z) > 0, oi_z / vol_z, np.nan)

    absD = np.abs(D)
    atr_px, atr_bp = build_1h_atr(t, o, h, l, c)

    # ATR>=45bp tier screen, point-in-time: trailing-30d median 1h-ATR-bp as of each month-start.
    # Computed per-symbol here (depends only on this symbol), cached by month.
    atr_ok_month: dict[str, bool] = {}

    def month_atr_ok(ym: str) -> bool:
        if ym in atr_ok_month:
            return atr_ok_month[ym]
        y, m = int(ym[:4]), int(ym[5:7])
        ms = int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        lo = ms - BARS_30D * BAR_MS
        sel = (t >= lo) & (t < ms) & np.isfinite(atr_bp)
        ok = bool(sel.sum() >= BARS_24H and np.median(atr_bp[sel]) >= ATR_TIER_MIN_BP)
        atr_ok_month[ym] = ok
        return ok

    # breakout masks (trailing 12-bar high/low, strictly prior), vectorized
    if n > BARS_1H:
        swh = np.lib.stride_tricks.sliding_window_view(h, BARS_1H)   # row k -> h[k..k+11]
        swl = np.lib.stride_tricks.sliding_window_view(l, BARS_1H)
        prior_hi = np.full(n, np.nan); prior_lo = np.full(n, np.nan)
        prior_hi[BARS_1H:] = swh[:n - BARS_1H].max(axis=1)          # window ending at j-1
        prior_lo[BARS_1H:] = swl[:n - BARS_1H].min(axis=1)
    else:
        prior_hi = np.full(n, np.nan); prior_lo = np.full(n, np.nan)
    up_break = h > prior_hi
    dn_break = l < prior_lo

    warm = BARS_30D
    # cheap prefilter: breakout in SOME direction, finite signal inputs, past warmup.
    cand = np.where((up_break | dn_break) & np.isfinite(C) & np.isfinite(absD)
                    & np.isfinite(atr_px)
                    & (np.arange(n) >= warm)
                    & (np.arange(n) < n - entry_offset - HOLD_BARS - 1))[0]

    trades = []
    last_entry_bar = -10 ** 9
    for j in cand:
        if j <= last_entry_bar + HOLD_BARS:        # one entry per coin per 6h (cooldown)
            continue
        ym = G._month_of(int(t[j]))
        if sym not in base_membership.get(ym, set()):   # point-in-time top-80
            continue
        d_sign = 1 if D[j] > 0 else (-1 if D[j] < 0 else 0)
        if d_sign == 0:
            continue
        # breakout must be in sign(D) direction
        if d_sign > 0 and not up_break[j]:
            continue
        if d_sign < 0 and not dn_break[j]:
            continue
        if not month_atr_ok(ym):                          # ATR>=45bp tier screen
            continue
        # trailing-30d top-decile gates, computed LAZILY (only for bars past the cheap filters):
        # strictly-prior window [j-8640 .. j-1]; require >=24h of finite values.
        Cw = C[j - BARS_30D:j]; Cw = Cw[np.isfinite(Cw)]
        if Cw.size < BARS_24H or C[j] < np.percentile(Cw, DECILE_PCT):
            continue
        Dw = absD[j - BARS_30D:j]; Dw = Dw[np.isfinite(Dw)]
        if Dw.size < BARS_24H or absD[j] < np.percentile(Dw, DECILE_PCT):
            continue

        je = j + entry_offset
        if je + HOLD_BARS >= n:
            continue
        # contiguity of the trade window
        if int(t[je]) - int(t[j]) != entry_offset * BAR_MS:
            continue
        if not np.all(np.diff(t[je:je + HOLD_BARS + 1]) == BAR_MS):
            continue
        atr = atr_px[je]
        if not (np.isfinite(atr) and atr > 0):
            continue
        entry = o[je]
        r_bp = atr / entry * 1e4

        # ---- lookahead audit (sampled) ----
        if audit["checked"] < 150:
            audit["checked"] += 1
            if int(t[je]) != int(t[j]) + entry_offset * BAR_MS:
                audit["entry_next_bar"] = False
            # signal recomputed from arrays truncated at j must reproduce the gate values
            oz_t = (oi[j] - np.nanmean(oi[j - BARS_24H + 1:j + 1])) / (np.nanstd(oi[j - BARS_24H + 1:j + 1]) + 1e-30)
            if abs(oz_t - oi_z[j]) > 1e-6 * (abs(oi_z[j]) + 1):
                audit["signal_causal"] = False
                audit["violations"].append(f"{sym}@{t[j]}: oi_z drift {oz_t} vs {oi_z[j]}")
            # ATR at entry must use only completed hours strictly before entry's hour
            if (t[je] // 3_600_000) <= (t[j - 0] // 3_600_000) - 2:
                pass  # informational
            if je <= j:
                audit["fwd_future_only"] = False

        # ---- trailing-stop simulation ----
        dir_ = d_sign
        stop = entry - dir_ * atr
        mfe = entry
        exit_price = None
        stopped = False
        for b in range(je, je + HOLD_BARS):
            # adverse-first: check stop against this bar
            if dir_ > 0:
                if l[b] <= stop:
                    exit_price = stop; stopped = True; break
                mfe = max(mfe, h[b]); stop = max(stop, mfe - atr)
            else:
                if h[b] >= stop:
                    exit_price = stop; stopped = True; break
                mfe = min(mfe, l[b]); stop = min(stop, mfe + atr)
        if exit_price is None:                       # hard 6h time exit at open of bar je+HOLD
            exit_price = o[je + HOLD_BARS]
        r_gross = dir_ * (exit_price - entry) / atr  # realised R (gross of slippage/friction)
        slip_bp = slip_sampler(rng) if stopped else 0.0
        slip_R = slip_bp / r_bp                       # price-bp slippage -> R units
        r_net_slip = r_gross - slip_R                 # deepen the (adverse) fill on stop-outs
        trades.append((int(t[j]), sym, dir_, r_gross, r_net_slip, r_bp, stopped))
        last_entry_bar = j
    return trades


# ------------------------------------------------------------------ aggregate + gate
def gate0(trades, label):
    if not trades:
        return {"label": label, "n_trades": 0, "verdict": None}
    r_gross = np.array([x[3] for x in trades])
    r_slip = np.array([x[4] for x in trades])
    r_bp = np.array([x[5] for x in trades])
    stopped = np.array([x[6] for x in trades])
    mean_R_bp = float(np.mean(r_bp))

    def wl(rr):
        wins = rr[rr > 0]; losses = rr[rr <= 0]
        W = float(np.mean(wins)) if wins.size else 0.0
        L = float(np.mean(-losses)) if losses.size else 0.0
        hit = float(wins.size) / rr.size
        return W, L, hit, wins.size, losses.size

    W_g, L_g, hit, nw, nl = wl(r_gross)          # hit rate is slippage-independent
    W_s, L_s, hit_s, _, _ = wl(r_slip)           # W/L WITH B22B stop slippage
    fric_R = FRICTION_BP / mean_R_bp             # 12bp fees+spread as a fraction of R

    def pstar(W, L):
        base = L / (W + L) if (W + L) > 0 else float("nan")
        fric = fric_R / (W + L) if (W + L) > 0 else float("nan")
        return base, fric, base + fric

    p0_base, p0_fric, p0 = pstar(W_g, L_g)       # WITHOUT slippage in L
    ps_base, ps_fric, ps = pstar(W_s, L_s)       # WITH B22B slippage in L (the promotion number)

    verdict = "DEAD" if hit < ps + GATE0_MARGIN else "SURVIVES_GATE0"
    return {
        "label": label,
        "n_trades": len(trades), "n_wins": nw, "n_losses": nl,
        "n_stopped_out": int(stopped.sum()),
        "hit_rate": hit,
        "mean_R_bp": mean_R_bp,
        "friction_R_units": fric_R,
        "no_slippage": {"W": W_g, "L": L_g, "p_star_base": p0_base,
                        "p_star_friction": p0_fric, "p_star": p0,
                        "hit_minus_pstar": hit - p0},
        "with_b22b_slippage": {"W": W_s, "L": L_s, "p_star_base": ps_base,
                               "p_star_friction": ps_fric, "p_star": ps,
                               "hit_minus_pstar": hit - ps,
                               "margin_required": GATE0_MARGIN},
        "gate0_rule": "DEAD if hit_rate < p*(with B22B slippage) + 0.03",
        "verdict": verdict,
        "mean_R_realized_gross": float(np.mean(r_gross)),
        "mean_R_realized_with_slip": float(np.mean(r_slip)),
    }


def run(coil_mode, entry_offset, seed=12345):
    uni = json.loads(UNIVERSE.read_text())
    base_membership = {ym: set(v) for ym, v in uni["membership"].items()}
    plan = uni["fetch_plan"]
    union = uni["union"]

    # covered design slice = design window intersect present-metrics months
    d_lo = dt.date.fromisoformat(DESIGN_WINDOW[0])
    d_hi = dt.date.fromisoformat(DESIGN_WINDOW[1])

    # point-in-time top-80 membership restricted to design-window months (ATR tier applied
    # per-symbol inside simulate_symbol). covered months = design-window months that have data.
    covered_months = set()
    for ym in base_membership:
        y, m = int(ym[:4]), int(ym[5:7])
        if d_lo <= dt.date(y, m, 1) <= d_hi:
            covered_months.add(ym)

    slip_sampler = _load_b22b_centibp()
    rng = np.random.default_rng(seed)
    audit = {"checked": 0, "entry_next_bar": True, "signal_causal": True,
             "fwd_future_only": True, "violations": [],
             "note": "signal (D,C,deciles,breakout) uses bars <= t; entry at open of t+offset; "
                     "ATR from the prior completed 1h bar; sim uses only bars >= entry."}
    # Trim each symbol's fetch-months to what the covered design slice needs: the covered
    # months plus ~2 months of warmup for the 30-day decile + 24h z-score windows. Symbols with
    # no months in range contribute nothing to this slice and are skipped.
    warm_lo = min(covered_months)                      # e.g. '2023-01'
    y, m = int(warm_lo[:4]), int(warm_lo[5:7])
    for _ in range(2):                                  # step back 2 warmup months
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    warm_lo = f"{y:04d}-{m:02d}"
    hi_month = max(covered_months)

    all_trades = []
    per_symbol = 0
    for sym in union:
        months = [mm for mm in plan[sym] if warm_lo <= mm <= hi_month]
        if not months:
            continue
        tr = simulate_symbol(sym, base_membership, months, coil_mode, entry_offset,
                             slip_sampler, rng, audit)
        # keep only trades whose SIGNAL bar falls inside the covered design window
        tr = [x for x in tr
              if d_lo <= dt.datetime.fromtimestamp(x[0] / 1000, dt.timezone.utc).date() <= d_hi]
        if tr:
            per_symbol += 1
        all_trades.extend(tr)

    res = gate0(all_trades, f"coil-mode={coil_mode}")
    res.update({
        "harness": "coiled_gate0.py",
        "frozen_spec": "ORIGINAL_STRATEGY_SHORTLIST.md 6.1-6.9 gate 0",
        "coil_mode": coil_mode,
        "entry_offset_bars": entry_offset,
        "design_window_frozen": list(DESIGN_WINDOW),
        "covered_design_months": sorted(covered_months),
        "n_symbols_with_trades": per_symbol,
        "atr_tier_min_bp": ATR_TIER_MIN_BP,
        "friction_bp": FRICTION_BP,
        "lookahead_audit": audit,
    })
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coil-mode", choices=["diff", "ratio", "both"], default="both")
    ap.add_argument("--entry-offset", type=int, default=1)
    a = ap.parse_args()
    if not UNIVERSE.exists():
        print("universe.json absent", file=sys.stderr); return 2
    modes = ["diff", "ratio"] if a.coil_mode == "both" else [a.coil_mode]
    out = {}
    for mode in modes:
        print(f"=== running coil-mode={mode} ===", flush=True)
        res = run(mode, a.entry_offset)
        out[mode] = res
        print(json.dumps({k: res.get(k) for k in (
            "coil_mode", "covered_design_months", "n_trades", "n_wins", "n_losses",
            "n_stopped_out", "hit_rate", "mean_R_bp", "no_slippage", "with_b22b_slippage",
            "verdict")}, indent=1), flush=True)
    RESULT.write_text(json.dumps(out, indent=1))
    print(f"\nfull result -> {RESULT}", flush=True)
    print("lookahead_audit:", json.dumps(out[modes[0]]["lookahead_audit"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
