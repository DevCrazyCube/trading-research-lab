"""Tests of scripts/factory/fastmom.py — synthetic bars, hand-computed answers.

    cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_fastmom.py -q

The numbers in the hand-computed cases are worked out in the comments next to them. `ref_sim` is an
independent minute-by-minute state machine written from the pre-registration; the module's jump-to-the-
next-signal simulator must reproduce it trade for trade on random bars with gaps and zero-volume minutes.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile

import numpy as np
import pytest

from scripts.factory import fastmom as fm

BP = 1e-4


# ---------------------------------------------------------------------------------------- helpers
def flat_bars(n, px=100.0, sym="BTCUSDT"):
    a = np.full(n, px)
    return dict(o=a.copy(), h=a.copy(), l=a.copy(), c=a.copy(), vol=np.ones(n)), sym


def mk(d, sym="BTCUSDT", t0=0):
    return fm.Bars(sym, t0, d["o"], d["h"], d["l"], d["c"], d["vol"])


def setbar(d, i, o, h, l, c):
    assert h >= max(o, c) and l <= min(o, c)
    d["o"][i], d["h"][i], d["l"][i], d["c"][i] = o, h, l, c


F = {f.fid: f for f in fm.formulas()}


def synth(n, seed, vol=6e-4, gaps=(), zeros=()):
    """Random bars with volatility clustering, small open gaps, optional missing runs and zero-volume runs."""
    rng = np.random.default_rng(seed)
    o = np.empty(n)
    h = np.empty(n)
    l = np.empty(n)
    c = np.empty(n)
    px = 100.0
    v = vol
    for i in range(n):
        v = 0.9 * v + 0.1 * vol * (0.4 + 2.2 * rng.random())
        if rng.random() < 0.02:
            v *= 3.0
        op = px * (1.0 + 0.15 * v * rng.standard_normal())
        steps = op * np.cumprod(1.0 + v / 2.0 * rng.standard_normal(4))
        o[i], c[i] = op, steps[-1]
        h[i] = max(op, steps.max())
        l[i] = min(op, steps.min())
        px = c[i]
    volu = 1.0 + rng.random(n)
    for a, ln in zeros:                       # no-trade minutes: flat at the previous close, volume 0
        for i in range(a, a + ln):
            o[i] = h[i] = l[i] = c[i] = c[i - 1]
            volu[i] = 0.0
    for a, ln in gaps:                        # absent from the archive
        for arr in (o, h, l, c, volu):
            arr[a:a + ln] = np.nan
    return dict(o=o, h=h, l=l, c=c, vol=volu)


def ref_sim(bars, f, side, sig5, w0, w1):
    """Independent reference: walk the minutes one by one. Returns (trades, deferred time exits)."""
    o, h, l, tr, n = bars.o, bars.h, bars.l, bars.tradeable, bars.n
    out = []
    deferred = 0
    pos = None
    pending = None
    for t in range(n):
        # --- the open of bar t: a due time exit first, then a pending entry
        if pos is not None and t >= pos["due"] and tr[t]:
            out.append((pos["s"], pos["e"], t, pos["side"], o[t], fm.KIND_TIME))
            deferred += t != pos["due"]
            pos = None
        elif pos is None and pending is not None:
            s, sd = pending
            if tr[t] and w0 <= t <= w1 - f.maxhold:
                pos = {"s": s, "e": t, "side": sd, "px": o[t], "due": t + f.maxhold, "best": o[t]}
        pending = None
        # --- inside bar t: stops and targets (never for the fixed-hold family)
        if pos is not None and f.family != "M1" and tr[t] and t < pos["due"]:
            sd, px, sg = pos["side"], pos["px"], sig5[pos["s"]]
            fill = kind = None
            if f.family == "M3":
                if sd > 0:
                    sl, tp = px * (1 - f.b * sg), px * (1 + f.a * sg)
                    if l[t] <= sl:
                        fill, kind = (o[t], fm.KIND_GAP) if o[t] <= sl else (sl, fm.KIND_STOP)
                    elif h[t] >= tp:
                        fill, kind = tp, fm.KIND_TP
                else:
                    sl, tp = px * (1 + f.b * sg), px * (1 - f.a * sg)
                    if h[t] >= sl:
                        fill, kind = (o[t], fm.KIND_GAP) if o[t] >= sl else (sl, fm.KIND_STOP)
                    elif l[t] <= tp:
                        fill, kind = tp, fm.KIND_TP
            else:                                              # M2: evaluate both orders of high and low
                d = f.y * sg
                if sd > 0:
                    if o[t] <= pos["best"] * (1 - d):
                        fill, kind = o[t], fm.KIND_GAP
                    else:
                        b0 = max(pos["best"], o[t])
                        b1 = max(b0, h[t])
                        low_first = b0 * (1 - d) if l[t] <= b0 * (1 - d) else None
                        high_first = b1 * (1 - d) if l[t] <= b1 * (1 - d) else None
                        if low_first is not None:
                            fill, kind = low_first, fm.KIND_STOP
                        elif high_first is not None:
                            fill, kind = high_first, fm.KIND_RATCHET
                        else:
                            pos["best"] = b1
                else:
                    if o[t] >= pos["best"] * (1 + d):
                        fill, kind = o[t], fm.KIND_GAP
                    else:
                        b0 = min(pos["best"], o[t])
                        b1 = min(b0, l[t])
                        high_first = b0 * (1 + d) if h[t] >= b0 * (1 + d) else None
                        low_first = b1 * (1 + d) if h[t] >= b1 * (1 + d) else None
                        if high_first is not None:
                            fill, kind = high_first, fm.KIND_STOP
                        elif low_first is not None:
                            fill, kind = low_first, fm.KIND_RATCHET
                        else:
                            pos["best"] = b1
            if fill is not None:
                out.append((pos["s"], pos["e"], t, sd, fill, kind))
                pos = None
        # --- the close of bar t: a signal, only if flat
        if pos is None and side[t] != 0:
            if f.family == "M1" or (np.isfinite(sig5[t]) and sig5[t] > 0):
                pending = (t, int(side[t]))
    return out, deferred


# ---------------------------------------------------------------------------- the declared grid
def test_formula_grid_and_costs_match_the_preregistration():
    fl = fm.formulas()
    assert len(fl) == 43 and len({f.fid for f in fl}) == 43
    assert sum(f.family == "M1" for f in fl) == 36
    assert sum(f.family == "M2" for f in fl) == 4
    assert sum(f.family == "M3" for f in fl) == 3
    assert {(f.k, f.x, f.h) for f in fl if f.family == "M1"} == {(k, float(x), h) for k in (1, 5, 15)
                                                               for x in (1, 2, 3) for h in (1, 5, 15, 60)}
    assert {(f.N, f.y) for f in fl if f.family == "M2"} == {(30, 1.0), (30, 2.0), (120, 1.0), (120, 2.0)}
    assert {(f.a, f.b, f.k, f.x) for f in fl if f.family == "M3"} == {(1.0, 1.0, 5, 2.0), (2.0, 1.0, 5, 2.0),
                                                                    (1.0, 2.0, 5, 2.0)}
    assert [f.maxhold for f in fl if f.family == "M2"] == [60] * 4
    assert [f.maxhold for f in fl if f.family == "M3"] == [30] * 3
    assert len(fl) * len(fm.SYMBOLS) == 129
    assert fm.base_cost_side_bp("BTCUSDT") == pytest.approx(5.07)
    assert fm.base_cost_side_bp("ETHUSDT") == pytest.approx(5.24)
    assert fm.base_cost_side_bp("SOLUSDT") == pytest.approx(5.60)
    assert fm.MAKER_BOUND_BP == 2.0 and fm.SIGMA_WINDOW == 1440
    assert fm.DESIGN_T_MIN == 3.0 and fm.HOLDOUT_T_MIN == 2.0 and fm.BH_Q == 0.10
    assert len(fm.month_range("2021-01", "2023-12")) == 36
    assert len(fm.month_range("2024-01", "2026-10")) == 34
    assert len(fm.month_range(fm.DATA_FIRST_MONTH, fm.DATA_LAST_MONTH)) * 3 == 210
    assert fm.month_bounds_ms("2021-01") == (1609459200000, 1612137600000)
    assert fm.month_bounds_ms("2023-12")[1] == fm.month_bounds_ms("2024-01")[0] == 1704067200000


def test_frozen_preregistration_hash():
    assert fm.sha256_file(fm.PREREG_PATH) == fm.PREREG_SHA256


# ------------------------------------------------------------------------------- entry timing
def test_signal_at_t_fills_at_open_of_t_plus_1_hand_case():
    d, _ = flat_bars(12)
    setbar(d, 5, 100.0, 102.0, 100.0, 102.0)        # the move that makes the signal happens INSIDE bar 5
    setbar(d, 6, 102.5, 103.0, 102.0, 103.0)        # entry bar: opens at 102.5
    setbar(d, 7, 103.5, 104.0, 103.0, 103.2)        # exit bar (h = 1): opens at 103.5
    bars = mk(d)
    side = np.zeros(12, dtype=np.int8)
    side[5] = 1
    tr = fm.simulate(bars, F["M1.k1.x1.h1"], side)
    assert tr.sig.tolist() == [5] and tr.entry.tolist() == [6] and tr.exit.tolist() == [7]
    assert tr.exit_px[0] == 103.5
    # a look-ahead fill at the open of the signal bar (100.0) would have booked 102.5/100 - 1 = +250 bp
    assert tr.gross[0] == pytest.approx(103.5 / 102.5 - 1.0, abs=1e-15)
    # changing everything in bar 6 except its open cannot change the trade
    setbar(d, 6, 102.5, 109.0, 95.0, 96.0)
    tr2 = fm.simulate(mk(d), F["M1.k1.x1.h1"], side)
    assert tr2.gross[0] == tr.gross[0] and tr2.entry.tolist() == [6]


def test_burst_signal_cannot_see_the_next_bar():
    """Quiet tape, then one +50 bp minute at bar T. The 3-sigma burst can only fire at the CLOSE of bar T and
    fill at the open of T+1. A simulator that peeked one bar ahead would fire at T-1 and buy the open of T,
    i.e. BEFORE the jump, and book it."""
    n, T = 1500, 1460
    c = 100.0 * np.cumprod(1.0 + 1e-4 * np.where(np.arange(n) % 2 == 0, 1.0, -1.0))
    c[T:] *= 1.005
    o = np.concatenate(([100.0], c[:-1]))
    d = dict(o=o, h=np.maximum(o, c), l=np.minimum(o, c), c=c, vol=np.ones(n))
    bars = mk(d)
    cache = fm.SignalCache(bars)
    f = F["M1.k1.x3.h1"]
    side, _ = cache.signal(f)
    assert side[T] == 1 and not side[:T].any()
    tr = fm.simulate(bars, f, side)
    assert tr.sig[0] == T and tr.entry[0] == T + 1
    assert tr.gross[0] == pytest.approx(o[T + 2] / o[T + 1] - 1.0, abs=1e-15)
    assert abs(tr.gross[0]) < 2e-4                       # the jump itself (+50 bp) is NOT in the trade
    assert o[T + 1] / o[T] - 1.0 > 45e-4                  # ... which is what a peeking fill at open[T] would book


# --------------------------------------------------------------------------- sigma: past bars only
def test_trailing_std_matches_numpy_and_needs_a_full_window():
    rng = np.random.default_rng(1)
    r = 1e-3 * rng.standard_normal(4000)
    s = fm.trailing_std(r, 1440)
    assert np.isnan(s[:1439]).all() and np.isfinite(s[1439:]).all()
    for i in (1439, 1440, 2000, 3999):
        assert s[i] == pytest.approx(np.std(r[i - 1439:i + 1], ddof=1), rel=1e-10)
    r2 = r.copy()
    r2[2500] = np.nan                                     # one missing return poisons exactly 1,440 windows
    s2 = fm.trailing_std(r2, 1440)
    assert np.isnan(s2[2500:2500 + 1440]).all()
    assert np.isfinite(s2[2499]) and np.isfinite(s2[2500 + 1440])
    assert np.array_equal(s2[:2500], s[:2500], equal_nan=True)
    assert s2[2500 + 1440] == pytest.approx(np.std(r[2501:2501 + 1440], ddof=1), rel=1e-10)


def test_sigma_k_is_the_std_of_overlapping_k_minute_returns_ending_at_the_signal_bar():
    bars = mk(synth(3200, 7))
    cache = fm.SignalCache(bars)
    c = bars.c
    for k in (1, 5, 15):
        t = 3000
        rk = np.array([c[i] / c[i - k] - 1.0 for i in range(t - 1439, t + 1)])      # 1,440 returns, last = bar t
        assert cache.sigma(k)[t] == pytest.approx(np.std(rk, ddof=1), rel=1e-9)
        assert np.isnan(cache.sigma(k)[1439 + k - 1]) and np.isfinite(cache.sigma(k)[1439 + k])


def test_truncation_bars_after_t_cannot_change_anything_up_to_t():
    n, t = 5200, 3600
    d = synth(n, 11, zeros=((2500, 3), (4000, 5)))
    e = {k: v.copy() for k, v in d.items()}
    rng = np.random.default_rng(99)
    fac = 1.0 + 0.05 * rng.standard_normal(n - t - 1)
    for key in ("o", "h", "l", "c"):
        e[key][t + 1:] *= fac                               # every bar after t is altered
    e["h"][t + 1:] = np.maximum(e["h"][t + 1:], np.maximum(e["o"][t + 1:], e["c"][t + 1:]))
    e["l"][t + 1:] = np.minimum(e["l"][t + 1:], np.minimum(e["o"][t + 1:], e["c"][t + 1:]))
    e["vol"][t + 1:] = np.where(rng.random(n - t - 1) < 0.05, 0.0, 1.0)
    A, B = mk(d), mk(e)
    ca, cb = fm.SignalCache(A), fm.SignalCache(B)
    for k in (1, 5, 15):
        assert np.array_equal(ca.sigma(k)[:t + 1], cb.sigma(k)[:t + 1], equal_nan=True)     # bit-identical
        assert not np.array_equal(ca.sigma(k)[t + 1:], cb.sigma(k)[t + 1:], equal_nan=True)
    checked = 0
    for f in fm.formulas():
        sa, ga = ca.signal(f)
        sb, gb = cb.signal(f)
        assert np.array_equal(sa[:t + 1], sb[:t + 1])
        ta = fm.simulate(A, f, sa, ga, 1500, n - 1)
        tb = fm.simulate(B, f, sb, gb, 1500, n - 1)
        # trades decided AND finished by bar t are identical; the first trade that reaches past t may differ
        da = [(int(s), int(x), int(sd), float(p)) for s, x, sd, p in zip(ta.sig, ta.exit, ta.side, ta.exit_px) if x <= t]
        db = [(int(s), int(x), int(sd), float(p)) for s, x, sd, p in zip(tb.sig, tb.exit, tb.side, tb.exit_px) if x <= t]
        assert da == db
        # every signal bar <= t - 1 that opened a trade is the same in both worlds (entry <= t is past data)
        assert [int(s) for s in ta.sig if s < t] == [int(s) for s in tb.sig if s < t]
        checked += len(da)
    assert checked > 500


# ------------------------------------------------------------------- fixed hold: P&L and costs
def test_fixed_hold_pnl_with_costs_hand_computed():
    d, _ = flat_bars(40)
    d["o"][11] = 100.0
    d["o"][16] = 101.0          # long  11 -> 16 : +100 bp gross
    d["o"][21] = 200.0
    d["o"][26] = 198.0          # short 21 -> 26 : 198/200 - 1 = -1 % on the price -> +100 bp gross for a short
    d["o"][31] = 100.0
    d["o"][36] = 99.5           # long  31 -> 36 : -50 bp gross
    for i in (11, 16, 21, 26, 31, 36):
        d["h"][i] = max(d["h"][i], d["o"][i])
        d["l"][i] = min(d["l"][i], d["o"][i])
    side = np.zeros(40, dtype=np.int8)
    side[10], side[20], side[30] = 1, -1, 1
    tr = fm.simulate(mk(d), F["M1.k1.x1.h5"], side)
    assert tr.entry.tolist() == [11, 21, 31] and tr.exit.tolist() == [16, 26, 36]
    assert tr.gross == pytest.approx([0.01, 0.01, -0.005], abs=1e-15)
    assert tr.hold_bars.tolist() == [5, 5, 5]
    row = fm.pair_row("BTCUSDT", F["M1.k1.x1.h5"], tr, 0, 1, "design")
    # BTC: 5.0 + 0.07 = 5.07 bp per side -> 10.14 bp round trip
    assert row["cost_side_bp"] == pytest.approx(5.07) and row["round_trip_cost_bp"] == pytest.approx(10.14)
    assert row["mean_bp_gross"] == pytest.approx((100 + 100 - 50) / 3)                 # 50.0
    assert row["mean_bp_net"] == pytest.approx(50.0 - 10.14)                           # 39.86
    assert row["median_bp_net"] == pytest.approx(100 - 10.14)                          # 89.86
    assert row["mean_bp_maker"] == pytest.approx(50.0 - 4.0)                           # 2 bp per side, no spread
    assert row["breakeven_cost_side_bp"] == pytest.approx(25.0)                        # 50 / 2
    assert row["win_rate_net"] == pytest.approx(2 / 3) and row["win_rate_gross"] == pytest.approx(2 / 3)
    assert row["total_net"] == pytest.approx((89.86 + 89.86 - 60.14) * BP)
    assert row["n_long"] == 2 and row["n_short"] == 1 and row["exits_time"] == 3
    eth = fm.pair_row("ETHUSDT", F["M1.k1.x1.h5"], tr, 0, 1, "design")
    sol = fm.pair_row("SOLUSDT", F["M1.k1.x1.h5"], tr, 0, 1, "design")
    assert eth["mean_bp_net"] == pytest.approx(50.0 - 10.48) and sol["mean_bp_net"] == pytest.approx(50.0 - 11.20)


def test_a_one_bp_winner_is_a_loser_after_costs():
    d, _ = flat_bars(10)
    d["o"][4] = d["h"][4] = 100.01
    side = np.zeros(10, dtype=np.int8)
    side[2] = 1                                                 # buy 100.00 at bar 3, sell 100.01 at bar 4
    tr = fm.simulate(mk(d), F["M1.k1.x1.h1"], side)
    row = fm.pair_row("BTCUSDT", F["M1.k1.x1.h1"], tr, 0, 1, "design")
    assert row["mean_bp_gross"] == pytest.approx(1.0, abs=1e-9)
    assert row["mean_bp_net"] == pytest.approx(1.0 - 10.14, abs=1e-9)
    assert row["win_rate_gross"] == 1.0 and row["win_rate_net"] == 0.0


# -------------------------------------------------------------------- one position at a time
def test_one_position_at_a_time_and_the_reentry_convention():
    d, _ = flat_bars(60)
    side = np.zeros(60, dtype=np.int8)
    for s in (10, 11, 12, 15, 16, 17, 30):
        side[s] = 1
    tr = fm.simulate(mk(d), F["M1.k1.x1.h5"], side)
    # s=10 -> in from the open of 11 to the open of 16. Signals at the closes of 11, 12 and 15 come while the
    # position is open (15 closes before the exit at the open of 16) -> ignored. The close of 16 is flat -> taken.
    assert tr.sig.tolist() == [10, 16, 30]
    assert tr.entry.tolist() == [11, 17, 31] and tr.exit.tolist() == [16, 22, 36]
    # h = 1: in at the open of s+1, out at the open of s+2; the close of s+1 is still "in position"
    side1 = np.zeros(60, dtype=np.int8)
    side1[10:20] = 1
    tr1 = fm.simulate(mk(d), F["M1.k1.x1.h1"], side1)
    assert tr1.sig.tolist() == [10, 12, 14, 16, 18]
    # trades never overlap
    for f, sd in ((F["M1.k1.x1.h5"], side), (F["M1.k1.x1.h1"], side1)):
        t = fm.simulate(mk(d), f, sd)
        assert (t.entry[1:] > t.exit[:-1]).all()


# -------------------------------------------------------------------------- M3: target / stop
def _m3_case(setup, sd=1, fid="M3.a1.b1", n=50, sg=0.01, entry=100.0):
    d, _ = flat_bars(n, entry)
    setup(d)
    side = np.zeros(n, dtype=np.int8)
    side[9] = sd                                                 # signal at the close of 9 -> entry at the open of 10
    sig5 = np.full(n, sg)
    return fm.simulate(mk(d), F[fid], side, sig5)


def test_m3_stop_fills_before_target_inside_one_bar():
    # entry 100, sigma_5 = 1 % -> take-profit 101, stop 99. Bar 11 trades BOTH 101.5 and 98.9.
    tr = _m3_case(lambda d: (setbar(d, 10, 100.0, 100.5, 99.5, 100.2), setbar(d, 11, 100.2, 101.5, 98.9, 100.0)))
    assert tr.exit.tolist() == [11] and tr.kind.tolist() == [fm.KIND_STOP]
    assert tr.exit_px[0] == pytest.approx(99.0) and tr.gross[0] == pytest.approx(-0.01)
    assert tr.hold_bars.tolist() == [2]
    # the same bar without the low: the target fills AT 101, not at the high
    tr = _m3_case(lambda d: (setbar(d, 10, 100.0, 100.5, 99.5, 100.2), setbar(d, 11, 100.2, 101.5, 99.2, 100.0)))
    assert tr.kind.tolist() == [fm.KIND_TP] and tr.exit_px[0] == pytest.approx(101.0)
    assert tr.gross[0] == pytest.approx(0.01)
    # both inside the ENTRY bar: still the stop
    tr = _m3_case(lambda d: setbar(d, 10, 100.0, 101.2, 98.7, 100.0))
    assert tr.exit.tolist() == [10] and tr.kind.tolist() == [fm.KIND_STOP] and tr.gross[0] == pytest.approx(-0.01)
    assert tr.hold_bars.tolist() == [1]
    # short: target 99, stop 101; a bar touching both -> stop at 101 -> -1 %
    tr = _m3_case(lambda d: setbar(d, 12, 100.0, 101.2, 98.5, 100.0), sd=-1)
    assert tr.exit.tolist() == [12] and tr.kind.tolist() == [fm.KIND_STOP]
    assert tr.exit_px[0] == pytest.approx(101.0) and tr.gross[0] == pytest.approx(-0.01)


def test_m3_asymmetric_levels():
    # (a, b) = (2, 1): target 102, stop 99
    tr = _m3_case(lambda d: setbar(d, 13, 100.0, 101.9, 99.5, 101.0), fid="M3.a2.b1")
    assert tr.kind.tolist() == [fm.KIND_TIME]                    # 101.9 < 102: nothing hit, time exit
    tr = _m3_case(lambda d: setbar(d, 13, 100.0, 102.0, 99.5, 101.0), fid="M3.a2.b1")
    assert tr.kind.tolist() == [fm.KIND_TP] and tr.gross[0] == pytest.approx(0.02)
    # (a, b) = (1, 2): target 101, stop 98
    tr = _m3_case(lambda d: setbar(d, 13, 100.0, 100.5, 98.5, 99.0), fid="M3.a1.b2")
    assert tr.kind.tolist() == [fm.KIND_TIME]
    tr = _m3_case(lambda d: setbar(d, 13, 100.0, 100.5, 97.9, 99.0), fid="M3.a1.b2")
    assert tr.kind.tolist() == [fm.KIND_STOP] and tr.gross[0] == pytest.approx(-0.02)
    # short with (2, 1): target 98, stop 101
    tr = _m3_case(lambda d: setbar(d, 13, 100.0, 100.5, 97.9, 99.0), sd=-1, fid="M3.a2.b1")
    assert tr.kind.tolist() == [fm.KIND_TP] and tr.exit_px[0] == pytest.approx(98.0) and tr.gross[0] == pytest.approx(0.02)


def test_m3_gap_through_stop_pays_the_open_and_target_gets_no_improvement():
    # long, stop 99: bar 11 OPENS at 98.5 -> filled at 98.5, not at 99
    tr = _m3_case(lambda d: setbar(d, 11, 98.5, 98.8, 98.0, 98.6))
    assert tr.exit.tolist() == [11] and tr.kind.tolist() == [fm.KIND_GAP]
    assert tr.exit_px[0] == 98.5 and tr.gross[0] == pytest.approx(-0.015)
    assert tr.hold_bars.tolist() == [1]                           # entry open of 10 -> open of 11
    # long, target 101: bar 11 OPENS at 101.7 -> filled at 101 (no price improvement)
    tr = _m3_case(lambda d: setbar(d, 11, 101.7, 101.9, 101.4, 101.5))
    assert tr.kind.tolist() == [fm.KIND_TP] and tr.exit_px[0] == pytest.approx(101.0)
    # short, stop 101: bar 11 opens at 101.8 -> pays 101.8
    tr = _m3_case(lambda d: setbar(d, 11, 101.8, 102.0, 101.5, 101.6), sd=-1)
    assert tr.kind.tolist() == [fm.KIND_GAP] and tr.gross[0] == pytest.approx(-(101.8 / 100.0 - 1.0))


def test_m3_time_exit_at_the_open_30_minutes_after_entry():
    def setup(d):
        d["o"][40] = 100.4
        d["h"][40] = 100.4
    tr = _m3_case(setup)
    assert tr.entry.tolist() == [10] and tr.exit.tolist() == [40] and tr.kind.tolist() == [fm.KIND_TIME]
    assert tr.gross[0] == pytest.approx(0.004) and tr.hold_bars.tolist() == [30]
    # a touch on bar 40 itself (after the time exit at its open) is irrelevant; one on bar 39 is not
    tr = _m3_case(lambda d: setbar(d, 40, 100.0, 105.0, 95.0, 100.0))
    assert tr.kind.tolist() == [fm.KIND_TIME] and tr.gross[0] == pytest.approx(0.0)
    tr = _m3_case(lambda d: setbar(d, 39, 100.0, 105.0, 99.5, 100.0))
    assert tr.exit.tolist() == [39] and tr.kind.tolist() == [fm.KIND_TP]


# ------------------------------------------------------------------------- M2: trailing stop
def _m2_case(setup, sd=1, fid="M2.N30.y1", n=80, sg=0.01, entry=100.0):
    d, _ = flat_bars(n, entry)
    setup(d)
    side = np.zeros(n, dtype=np.int8)
    side[9] = sd
    return fm.simulate(mk(d), F[fid], side, np.full(n, sg))


def test_m2_trailing_stop_hand_computed_long():
    # entry 100 at the open of bar 10, trail 1 %.
    # bar 10: high 100.5, low 99.8  -> stop at the open 99.0 (not hit); ratcheted 100.5*0.99 = 99.495 (not hit)
    # bar 11: high 101.0, low 100.3 -> best 101.0, ratcheted stop 99.99 (not hit)
    # bar 12: opens 100.5, low 99.9 -> stop in force 101*0.99 = 99.99 hit -> filled 99.99
    def setup(d):
        setbar(d, 10, 100.0, 100.5, 99.8, 100.4)
        setbar(d, 11, 100.6, 101.0, 100.3, 100.9)
        setbar(d, 12, 100.5, 100.7, 99.9, 100.0)
    tr = _m2_case(setup)
    assert tr.exit.tolist() == [12] and tr.kind.tolist() == [fm.KIND_STOP]
    assert tr.exit_px[0] == pytest.approx(99.99) and tr.gross[0] == pytest.approx(-0.0001)
    assert tr.hold_bars.tolist() == [3]


def test_m2_ratchet_inside_one_bar_takes_the_worse_order():
    # bar 11 opens 100.6 (new best), high 102, low 100.1.
    #   low first : stop in force = 100.6*0.99 = 99.594 -> not reached -> the trade would survive
    #   high first: best 102 -> stop 100.98, low 100.1 <= 100.98 -> out at 100.98
    # the worse order for the trade is "high first": filled at 100.98 (+98 bp), the position is closed
    def setup(d):
        setbar(d, 10, 100.0, 100.5, 99.8, 100.4)
        setbar(d, 11, 100.6, 102.0, 100.1, 101.9)
    tr = _m2_case(setup)
    assert tr.exit.tolist() == [11] and tr.kind.tolist() == [fm.KIND_RATCHET]
    assert tr.exit_px[0] == pytest.approx(100.98) and tr.gross[0] == pytest.approx(0.0098)
    # when the low ALSO reaches the stop that was in force at the open, "low first" is the worse order:
    # bar 11 opens 100.6, high 102, low 99.5 <= 99.594 -> filled at 99.594, not at 100.98
    def setup2(d):
        setbar(d, 10, 100.0, 100.5, 99.8, 100.4)
        setbar(d, 11, 100.6, 102.0, 99.5, 101.9)
    tr = _m2_case(setup2)
    assert tr.kind.tolist() == [fm.KIND_STOP] and tr.exit_px[0] == pytest.approx(100.6 * 0.99)


def test_m2_stop_is_live_on_the_entry_bar():
    tr = _m2_case(lambda d: setbar(d, 10, 100.0, 100.2, 98.9, 99.5))          # low 98.9 <= 99.0
    assert tr.exit.tolist() == [10] and tr.kind.tolist() == [fm.KIND_STOP] and tr.gross[0] == pytest.approx(-0.01)
    tr = _m2_case(lambda d: setbar(d, 10, 100.0, 100.2, 99.3, 99.5), fid="M2.N30.y2")   # trail 2 %: stop 98
    assert tr.kind.tolist() == [fm.KIND_TIME]


def test_m2_gap_through_the_trailing_stop_pays_the_open():
    # best 100.4 after bar 10 -> stop 99.396; bar 11 OPENS at 99.0 -> filled 99.0
    def setup(d):
        setbar(d, 10, 100.0, 100.4, 99.6, 100.3)
        setbar(d, 11, 99.0, 99.2, 98.5, 99.1)
    tr = _m2_case(setup)
    assert tr.exit.tolist() == [11] and tr.kind.tolist() == [fm.KIND_GAP]
    assert tr.exit_px[0] == 99.0 and tr.gross[0] == pytest.approx(-0.01)
    assert tr.hold_bars.tolist() == [1]


def test_m2_short_mirror_and_time_exit():
    # short entry 100, trail 1 %: bar 10 low 99.0 (best 99.0) high 100.2 -> at the open stop 101 not hit;
    # ratchet: 99.0*1.01 = 99.99 <= high 100.2 -> out at 99.99 (low first, then the bounce): +1 bp
    tr = _m2_case(lambda d: setbar(d, 10, 100.0, 100.2, 99.0, 99.5), sd=-1)
    assert tr.kind.tolist() == [fm.KIND_RATCHET] and tr.exit_px[0] == pytest.approx(99.99)
    assert tr.gross[0] == pytest.approx(-(99.99 / 100.0 - 1.0))
    # short, high first: 101.2 >= 101 -> stop at 101 -> -1 %
    tr = _m2_case(lambda d: setbar(d, 10, 100.0, 101.2, 99.0, 99.5), sd=-1)
    assert tr.kind.tolist() == [fm.KIND_STOP] and tr.gross[0] == pytest.approx(-0.01)
    # nothing happens for 60 minutes -> out at the open of bar 70
    def setup(d):
        d["o"][70] = 99.7
        d["l"][70] = 99.7
    tr = _m2_case(setup, sd=-1)
    assert tr.exit.tolist() == [70] and tr.kind.tolist() == [fm.KIND_TIME]
    assert tr.gross[0] == pytest.approx(0.003) and tr.hold_bars.tolist() == [60]


def test_breakout_signal_uses_the_previous_n_bars_only():
    d = synth(400, 5)
    for key in ("o", "h", "l", "c"):
        d[key][200] = np.nan                                    # a hole: no breakout signal while it is in the window
    for N in (30, 120):
        s = fm.breakout_side(d["h"], d["l"], d["c"], N)
        for t in range(400):
            if t < N:
                exp = 0
            else:
                hh, ll = d["h"][t - N:t].max(), d["l"][t - N:t].min()       # NaN if the hole is inside
                exp = int(d["c"][t] > hh) - int(d["c"][t] < ll)
            assert s[t] == exp
        assert not s[201:201 + N].any()
    # hand case: close above the highest HIGH of the previous 30 bars, not merely above their closes
    d, _ = flat_bars(60)
    d["h"][40] = 100.8
    setbar(d, 50, 100.0, 100.7, 100.0, 100.7)                   # 100.7 < 100.8 -> no signal
    setbar(d, 55, 100.0, 100.9, 100.0, 100.9)                   # 100.9 > 100.8 -> long
    s = fm.breakout_side(d["h"], d["l"], d["c"], 30)
    assert s[50] == 0 and s[55] == 1 and int(np.abs(s).sum()) == 1


def test_burst_signal_thresholds():
    r = np.array([0.0, 0.0011, -0.0011, 0.002, 0.001, np.nan, 0.003])
    sg = np.array([0.001, 0.001, 0.001, 0.001, 0.001, 0.001, np.nan])
    assert fm.burst_side(r, sg, 1.0).tolist() == [0, 1, -1, 1, 0, 0, 0]       # strict inequality, NaN -> 0
    assert fm.burst_side(r, sg, 2.0).tolist() == [0, 0, 0, 0, 0, 0, 0]
    assert fm.burst_side(np.array([0.0021, -0.0021]), np.array([0.001, 0.001]), 2.0).tolist() == [1, -1]
    assert fm.burst_side(np.array([0.5]), np.array([0.0]), 1.0).tolist() == [0]    # sigma = 0 is not a signal


# ---------------------------------------------------------------- missing and zero-volume bars
def test_no_entry_on_a_zero_volume_or_missing_bar():
    d, _ = flat_bars(40)
    d["vol"][11] = 0.0                                            # entry bar of the signal at 10: no trade
    for key in ("o", "h", "l", "c", "vol"):
        d[key][21] = np.nan                                       # entry bar of the signal at 20: missing
    side = np.zeros(40, dtype=np.int8)
    side[10] = side[20] = side[30] = 1
    tr = fm.simulate(mk(d), F["M1.k1.x1.h1"], side)
    assert tr.sig.tolist() == [30]
    assert tr.skipped_untradeable_entry == 2


def test_exit_due_on_a_missing_bar_fills_at_the_next_available_open():
    d, _ = flat_bars(40)
    for i in (16, 17):
        for key in ("o", "h", "l", "c", "vol"):
            d[key][i] = np.nan
    d["vol"][18] = 0.0                                            # present but no trade: not an available open
    d["o"][19] = d["h"][19] = 100.3
    side = np.zeros(40, dtype=np.int8)
    side[10] = 1                                                  # in at 11, due at 16 -> filled at 19
    tr = fm.simulate(mk(d), F["M1.k1.x1.h5"], side)
    assert tr.exit.tolist() == [19] and tr.deferred_exits == 1
    assert tr.gross[0] == pytest.approx(0.003) and tr.hold_bars.tolist() == [8]
    # the same for the 30-minute time exit of M3; stops are not evaluated on the dead bars
    d, _ = flat_bars(60)
    d["vol"][40] = 0.0
    d["o"][41] = d["h"][41] = 100.2
    side = np.zeros(60, dtype=np.int8)
    side[9] = 1
    tr = fm.simulate(mk(d), F["M3.a1.b1"], side, np.full(60, 0.01))
    assert tr.exit.tolist() == [41] and tr.kind.tolist() == [fm.KIND_TIME] and tr.deferred_exits == 1


def test_no_entry_whose_time_limit_falls_outside_the_window():
    d, _ = flat_bars(100)
    side = np.zeros(100, dtype=np.int8)
    side[[20, 38, 39, 50]] = 1
    f = F["M1.k1.x1.h60"]
    tr = fm.simulate(mk(d), f, side, None, 0, 99)
    assert tr.sig.tolist() == [20]                                # in from 21 to 81; nothing valid after that
    tr = fm.simulate(mk(d), f, side[:] * (np.arange(100) != 20), None, 0, 99)
    # signal 38: entry 39, time limit 99 = the last bar -> allowed. signal 39: entry 40, limit 100 -> not allowed.
    assert tr.sig.tolist() == [38]
    tr = fm.simulate(mk(d), F["M1.k1.x1.h1"], side, None, 39, 99)
    assert tr.sig.tolist() == [38, 50]                            # the window starts at 39: the entry at 21 is outside it


# --------------------------------------------------------------- reference simulator cross-check
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_simulator_reproduces_the_minute_by_minute_reference_on_random_bars(seed):
    n = 9000
    d = synth(n, 100 + seed, gaps=((3500, 20), (6000, 2)), zeros=((1700, 4), (5200, 7), (7450, 3), (8100, 30), (8600, 1)))
    bars = mk(d)
    cache = fm.SignalCache(bars)
    w0, w1 = 1500, n - 1
    total = 0
    kinds = set()
    for f in fm.formulas():
        side, sg = cache.signal(f)
        tr = fm.simulate(bars, f, side, sg, w0, w1)
        ref, deferred = ref_sim(bars, f, side, sg, w0, w1)
        assert len(tr) == len(ref), f.fid
        for i, (s, e, x, sd, px, kd) in enumerate(ref):
            assert (int(tr.sig[i]), int(tr.entry[i]), int(tr.exit[i]), int(tr.side[i]), int(tr.kind[i])) == (s, e, x, sd, kd), f.fid
            assert tr.exit_px[i] == pytest.approx(px, rel=1e-13), f.fid
            assert tr.gross[i] == pytest.approx(sd * (px / bars.o[e] - 1.0), abs=1e-14)
        assert tr.deferred_exits == deferred, f.fid
        assert (tr.entry[1:] > tr.exit[:-1]).all() if len(tr) > 1 else True
        assert bars.tradeable[tr.entry].all() and (tr.entry >= w0).all() and (tr.exit <= w1).all()
        total += len(tr)
        kinds |= set(tr.kind.tolist())
    assert total > 3000
    assert kinds == {fm.KIND_TIME, fm.KIND_STOP, fm.KIND_TP, fm.KIND_GAP, fm.KIND_RATCHET}


def test_fade_is_the_opposite_side_at_the_same_entry_with_the_same_rule():
    def setup(d):
        setbar(d, 10, 100.0, 100.5, 99.5, 100.2)
        setbar(d, 11, 100.2, 101.5, 99.2, 100.0)                  # long: target 101 hit. short: stop 101 hit
    d, _ = flat_bars(50)
    setup(d)
    side = np.zeros(50, dtype=np.int8)
    side[9] = 1
    bars = mk(d)
    sg = np.full(50, 0.01)
    tr = fm.simulate(bars, F["M3.a1.b1"], side, sg)
    assert tr.gross[0] == pytest.approx(0.01)
    fg = fm.fade_gross(bars, F["M3.a1.b1"], tr, sg)
    assert fg[0] == pytest.approx(-0.01)
    # a bar touching both levels stops out BOTH directions: follow -1 %, fade -1 % -> drag -1 %, edge 0
    d, _ = flat_bars(50)
    setbar(d, 10, 100.0, 101.5, 98.5, 100.0)
    bars = mk(d)
    tr = fm.simulate(bars, F["M3.a1.b1"], side, sg)
    fg = fm.fade_gross(bars, F["M3.a1.b1"], tr, sg)
    assert tr.gross[0] == pytest.approx(-0.01) and fg[0] == pytest.approx(-0.01)


# --------------------------------------------------------------------------------- statistics
def test_day_clustered_t_hand_computed():
    # returns 1..6 (bp), two trades a day for three days. mean 3.5; residuals -2.5 -1.5 | -0.5 0.5 | 1.5 2.5
    # cluster sums -4, 0, 4 -> sum of squares 32. var = G/(G-1) * 32 / N^2 = 1.5 * 32 / 36 = 4/3
    # t = 3.5 / sqrt(4/3) = 3.031089
    v = np.array([1, 2, 3, 4, 5, 6], dtype=float) * BP
    t, g = fm.cluster_t(v, np.array([0, 0, 1, 1, 2, 2]))
    assert g == 3 and t == pytest.approx(3.5 / math.sqrt(4.0 / 3.0), rel=1e-12)
    assert t == pytest.approx(3.0310889, abs=1e-6)
    # one trade per day: the clustered t is the ordinary one-sample t
    t1, g1 = fm.cluster_t(v, np.arange(6))
    assert g1 == 6 and t1 == pytest.approx(v.mean() / (v.std(ddof=1) / math.sqrt(6)), rel=1e-12)
    # perfectly correlated days: clustering must LOWER t relative to treating trades as independent
    w = np.array([2.0, 2.0, 2.0, -1.0, -1.0, -1.0, 2.0, 2.0, 2.0]) * BP
    t_c, _ = fm.cluster_t(w, np.array([0, 0, 0, 1, 1, 1, 2, 2, 2]))
    t_iid = w.mean() / (w.std(ddof=1) / 3.0)
    # mean 1; cluster sums 3, -6, 3 -> 54; var = 1.5 * 54 / 81 = 1.0 -> t = 1.0
    assert t_c == pytest.approx(1.0, rel=1e-12) and t_c < t_iid
    assert math.isnan(fm.cluster_t(v, np.zeros(6, dtype=int))[0])          # one cluster: no t
    assert math.isnan(fm.cluster_t(np.array([]), np.array([]))[0])


def test_benjamini_hochberg_toy_vectors():
    # Benjamini & Hochberg (1995), 15 p-values at q = 0.05: the 4 smallest are rejected
    p = [0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298, 0.0344, 0.0459, 0.3240, 0.4262, 0.5719,
         0.6528, 0.7590, 1.0]
    assert fm.benjamini_hochberg(p, 0.05).tolist() == [True] * 4 + [False] * 11
    # step-UP: p(2) = 0.04 > 0.025 fails its own line, but p(4) = 0.045 <= 0.05 rescues all four
    assert fm.benjamini_hochberg([0.045, 0.01, 0.041, 0.04], 0.05).tolist() == [True] * 4
    assert fm.benjamini_hochberg([0.06, 0.01, 0.041, 0.04], 0.05).tolist() == [False, True, False, False]
    # order does not matter, NaN is p = 1 and still counts in m
    assert fm.benjamini_hochberg([float("nan"), 0.02, 0.9, 0.9], 0.10).tolist() == [False, True, False, False]
    assert fm.benjamini_hochberg([float("nan"), 0.03, 0.9, 0.9], 0.10).tolist() == [False] * 4      # 0.03 > 0.1/4
    # 129 tests, one candidate: it needs p <= 0.10 / 129 = 0.000775
    p129 = [1.0] * 128
    assert fm.benjamini_hochberg(p129 + [0.00077], 0.10)[-1]
    assert not fm.benjamini_hochberg(p129 + [0.00078], 0.10)[-1]
    try:
        from scripts.factory import mtest
    except Exception:                                              # the sibling library is optional here
        return
    rng = np.random.default_rng(5)
    pv = np.concatenate((rng.random(100), 1e-4 * rng.random(12)))
    assert fm.benjamini_hochberg(pv, 0.10).tolist() == list(np.asarray(mtest.bh_fdr(pv, 0.10)["reject"]).astype(bool))


def test_series_stats_daily_sharpe_counts_empty_days_as_zero():
    # day 0: +100 bp, +200 bp; day 2: -100 bp; days 1 and 3: no trade
    ret = np.array([0.01, 0.02, -0.01])
    st = fm.series_stats(ret, np.array([0, 0, 2]), 4)
    # daily = [0.03, 0, -0.01, 0]: mean 0.005, deviations 0.025 -0.005 -0.015 -0.005 -> ss 0.0009 -> sd sqrt(0.0003)
    assert st["sharpe_daily"] == pytest.approx(0.005 / math.sqrt(0.0003), rel=1e-12)
    assert st["sharpe_ann"] == pytest.approx(0.005 / math.sqrt(0.0003) * math.sqrt(365), rel=1e-12)
    assert st["mean_bp"] == pytest.approx(200 / 3) and st["median_bp"] == pytest.approx(100.0)
    assert st["win_rate"] == pytest.approx(2 / 3) and st["total"] == pytest.approx(0.02)
    assert st["total_compounded"] == pytest.approx(1.01 * 1.02 * 0.99 - 1.0, rel=1e-12)
    empty = fm.series_stats(np.array([]), np.array([], dtype=int), 4)
    assert math.isnan(empty["mean_bp"]) and empty["total"] == 0.0


def test_trades_are_booked_to_the_utc_day_of_entry():
    d, _ = flat_bars(3 * 1440 + 10)
    side = np.zeros(len(d["o"]), dtype=np.int8)
    w0 = 5                                                          # window starts at index 5 (= 00:00 of day 0)
    side[[w0 + 1438, w0 + 1439, w0 + 2 * 1440 + 100]] = 1
    tr = fm.simulate(mk(d), F["M1.k1.x1.h1"], side, None, w0, len(side) - 1)
    # s = w0+1438 -> entry w0+1439 (day 0, 23:59) -> exit w0+1440; s = w0+1439 is ignored (position open)
    assert tr.entry.tolist() == [w0 + 1439, w0 + 2 * 1440 + 101]
    row = fm.pair_row("BTCUSDT", F["M1.k1.x1.h1"], tr, w0, 3, "design")
    assert row["n_days_with_trades"] == 2 and row["n_days_window"] == 3
    day = (tr.entry - w0) // 1440
    assert day.tolist() == [0, 2]


def test_p_values_and_the_pass_rules():
    p1, p2 = fm.t_pvalues(3.0, 1001)
    assert p1 == pytest.approx(0.001383, abs=2e-5) and p2 == pytest.approx(2 * p1)
    assert fm.t_pvalues(-3.0, 1001)[0] == pytest.approx(1 - p1, abs=1e-12)
    assert fm.t_pvalues(float("nan"), 50) == (1.0, 1.0) and fm.t_pvalues(5.0, 1) == (1.0, 1.0)

    def row(mean, t, g=1000, n=5000):
        a, b = fm.t_pvalues(t, g)
        return {"n_trades": n, "mean_bp_net": mean, "t_net": t, "p_one_sided_net": a, "p_two_sided_net": b}

    # 127 clearly negative pairs, one strong positive, one positive at t = 3.1
    rows = [row(-8.0, -25.0) for _ in range(127)] + [row(4.0, 4.5), row(2.0, 3.1)]
    fm.apply_pass_rule(rows, 3.0, with_bh=True)
    assert rows[-2]["design_pass"] is True
    # t = 3.1: one-sided p = 0.00099 <= 0.10 * 2 / 129 = 0.00155 (second smallest of two candidates) -> rejected
    assert rows[-1]["bh_reject_one_sided"] is True and rows[-1]["design_pass"] is True
    assert not any(r["design_pass"] for r in rows[:127])
    assert all(r["bh_reject_two_sided"] for r in rows[:127]) and not any(r["bh_reject_one_sided"] for r in rows[:127])
    # alone, t = 3.1 does NOT survive BH over 129 (needs p <= 0.000775, i.e. t >= ~3.17)
    rows = [row(-8.0, -25.0) for _ in range(128)] + [row(2.0, 3.1)]
    fm.apply_pass_rule(rows, 3.0, with_bh=True)
    assert rows[-1]["t_net_ge_3"] is True and rows[-1]["bh_reject_one_sided"] is False and rows[-1]["design_pass"] is False
    # with no significant negatives the two-sided reading is the binding one: t = 3.25, one-sided p 0.00060 passes
    # 0.000775, two-sided 0.0012 does not
    rows = [row(-0.1, -0.2) for _ in range(128)] + [row(2.0, 3.25)]
    fm.apply_pass_rule(rows, 3.0, with_bh=True)
    assert rows[-1]["bh_reject_one_sided"] is True and rows[-1]["bh_reject_two_sided"] is False
    assert rows[-1]["design_pass"] is False
    # t below 3 never passes, whatever BH says; a positive mean is required
    rows = [row(2.0, 2.99) for _ in range(129)]
    fm.apply_pass_rule(rows, 3.0, with_bh=True)
    assert all(r["bh_reject_one_sided"] for r in rows) and not any(r["design_pass"] for r in rows)
    rows = [row(2.0, 2.0), row(2.0, 1.99), row(-2.0, -5.0), row(float("nan"), float("nan"), n=0)]
    fm.apply_pass_rule(rows, 2.0, with_bh=False)
    assert [r["holdout_pass"] for r in rows] == [True, False, False, False]


# ----------------------------------------------------------------------- random-entry control
def test_random_entry_control_is_minus_the_round_trip_cost():
    n = 120_000
    rng = np.random.default_rng(42)
    c = 100.0 * np.cumprod(1.0 + 5e-4 * rng.standard_normal(n))             # driftless walk, 5 bp a minute
    o = np.concatenate(([100.0], c[:-1]))
    d = dict(o=o, h=np.maximum(o, c), l=np.minimum(o, c), c=c, vol=np.ones(n))
    d["vol"][5000:5040] = 0.0
    bars = mk(d)
    cache = fm.SignalCache(bars)
    f = F["M1.k1.x1.h5"]
    side, _ = cache.signal(f)
    tr = fm.simulate(bars, f, side, None, 1500, n - 1)
    assert len(tr) > 4000
    g1 = fm.random_entry_gross(bars, tr, 1500, n - 1, np.random.default_rng([7, 1]))
    g2 = fm.random_entry_gross(bars, tr, 1500, n - 1, np.random.default_rng([7, 1]))
    assert np.array_equal(g1, g2)                                           # seeded -> reproducible
    assert len(g1) == len(tr)
    se = g1.std(ddof=1) / math.sqrt(len(g1))
    assert abs(g1.mean()) < 4 * se                                          # gross ~ 0
    rt = 2 * fm.base_cost_side_bp("BTCUSDT")
    assert g1.mean() * 1e4 - rt == pytest.approx(-rt, abs=4 * se * 1e4)     # net ~ - round trip


def test_random_entry_control_keeps_each_trade_s_side_and_holding_time():
    # price ramp o[i] = 100 + i: a trade of side s held d bars from bar e returns exactly s * d / (100 + e),
    # so the entry bar can be read back from the control's return and must be a whole bar inside the window
    n = 600
    o = 100.0 + np.arange(n)
    bars = mk(dict(o=o, h=o.copy(), l=o.copy(), c=o.copy(), vol=np.ones(n)))
    entry = np.array([10, 20, 30, 40])
    exit_ = np.array([15, 22, 30, 41])                              # the third exits INSIDE its entry bar
    side = np.array([1, -1, 1, -1], dtype=np.int8)
    kind = np.array([fm.KIND_TIME, fm.KIND_GAP, fm.KIND_STOP, fm.KIND_TP], dtype=np.int8)
    tr = fm.Trades(entry - 1, entry, exit_, side, o[exit_], kind, np.zeros(4))
    assert tr.hold_bars.tolist() == [5, 2, 1, 2]                    # open-to-open, intrabar exits to the bar's end
    w0, w1 = 50, 399
    for seed in range(20):
        g = fm.random_entry_gross(bars, tr, w0, w1, np.random.default_rng(seed))
        e = side * tr.hold_bars / g - 100.0
        assert np.allclose(e, np.round(e), atol=1e-6)
        assert (np.round(e) >= w0).all() and (np.round(e) + tr.hold_bars <= w1).all()
        assert (np.sign(g) == side).all()


def test_random_entry_control_detects_a_broken_cost_or_a_lookahead_fill():
    """What the control is for: a simulator that books the signal bar's own move shows a large positive gross
    on the REAL entries while the random entries stay at zero."""
    n = 60_000
    rng = np.random.default_rng(8)
    c = 100.0 * np.cumprod(1.0 + 5e-4 * rng.standard_normal(n))
    o = np.concatenate(([100.0], c[:-1]))
    bars = mk(dict(o=o, h=np.maximum(o, c), l=np.minimum(o, c), c=c, vol=np.ones(n)))
    f = F["M1.k1.x2.h1"]
    side, _ = fm.SignalCache(bars).signal(f)
    tr = fm.simulate(bars, f, side, None, 1500, n - 1)
    honest = tr.gross.mean() * 1e4
    peeking = (tr.side * (bars.o[tr.sig + 1] / bars.o[tr.sig] - 1.0)).mean() * 1e4     # fill at the open of the SIGNAL bar
    assert abs(honest) < 1.0 and peeking > 8.0                               # a 2-sigma minute is >= 10 bp here


# --------------------------------------------------------------------------------- data layer
def _csv(rows, header):
    lines = ["open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore"] if header else []
    for t, o, h, l, c, v, cnt in rows:
        lines.append(f"{t},{o},{h},{l},{c},{v},{t + 59999},{v * c},{cnt},0,0,0")
    return ("\n".join(lines) + "\n").encode()


def test_parse_kline_csv_header_units_and_month_bounds():
    lo, hi = fm.month_bounds_ms("2021-01")
    rows = [(lo, 1.0, 2.0, 0.5, 1.5, 10.0, 7), (lo + 60000, 1.5, 1.6, 1.4, 1.5, 0.0, 0), (lo + 180000, 1.5, 1.7, 1.5, 1.6, 3.0, 2)]
    for header in (False, True):
        a, info = fm.parse_kline_csv(_csv(rows, header), "2021-01")
        assert info == {"rows": 3, "header": header, "unit": "ms"}
        assert a[:, 0].tolist() == [lo, lo + 60000, lo + 180000]
        assert a[0, 1:].tolist() == [1.0, 2.0, 0.5, 1.5, 10.0, 7.0]
    with pytest.raises(ValueError, match="outside the month"):
        fm.parse_kline_csv(_csv([(hi, 1, 1, 1, 1, 1, 1)], False), "2021-01")
    with pytest.raises(ValueError, match="outside the month"):
        fm.parse_kline_csv(_csv([(lo - 60000, 1, 1, 1, 1, 1, 1)], True), "2021-01")
    with pytest.raises(ValueError, match="minute grid"):
        fm.parse_kline_csv(_csv([(lo + 30000, 1, 1, 1, 1, 1, 1)], False), "2021-01")
    with pytest.raises(ValueError, match="strictly increasing"):
        fm.parse_kline_csv(_csv([rows[0], rows[0]], False), "2021-01")
    micro = [(lo * 1000, 1.0, 2.0, 0.5, 1.5, 10.0, 7), (lo * 1000 + 60_000_000, 1.5, 1.6, 1.4, 1.5, 1.0, 1)]
    a, info = fm.parse_kline_csv(_csv(micro, True), "2021-01")
    assert info["unit"] == "us" and a[:, 0].tolist() == [lo, lo + 60000]
    with pytest.raises(ValueError, match="mixes"):
        fm.parse_kline_csv(_csv([rows[0], micro[1]], False), "2021-01")


def test_bars_grid_tradeable_and_next_tradeable():
    d, _ = flat_bars(8)
    d["vol"][2] = 0.0
    for key in ("o", "h", "l", "c", "vol"):
        d[key][4:6] = np.nan
    b = mk(d)
    assert b.present.tolist() == [True, True, True, True, False, False, True, True]
    assert b.tradeable.tolist() == [True, True, False, True, False, False, True, True]
    assert b.next_tradeable.tolist() == [0, 1, 3, 3, 6, 6, 6, 7, 8]
    assert fm._runs(~b.present) == [(4, 2)] and fm._runs(np.zeros(3, dtype=bool)) == []


def _write_month(root, sym, ym, o, h, l, c, vol, header, drop=()):
    lo, hi = fm.month_bounds_ms(ym)
    n = (hi - lo) // 60000
    assert len(o) == n
    keep = np.ones(n, dtype=bool)
    for a, ln in drop:
        keep[a:a + ln] = False
    t = lo + 60000 * np.arange(n, dtype=np.int64)
    cnt = np.where(vol > 0, 5, 0)
    M = np.column_stack([t, o, h, l, c, vol, t + 59999, vol * c, cnt, np.zeros(n), np.zeros(n), np.zeros(n)])[keep]
    buf = io.StringIO()
    if header:
        buf.write("open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n")
    np.savetxt(buf, M, delimiter=",", fmt=["%d", "%.6f", "%.6f", "%.6f", "%.6f", "%.3f", "%d", "%.3f", "%d", "%d", "%d", "%d"])
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{sym}-1m-{ym}.csv", buf.getvalue())
    p = root / sym / f"{sym}-1m-{ym}.zip"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(zb.getvalue())
    (root / sym / f"{sym}-1m-{ym}.zip.CHECKSUM").write_text(f"{hashlib.sha256(zb.getvalue()).hexdigest()}  {p.name}\n")
    return p


def _build_world(tmp_path, monkeypatch, btc_phi):
    """Three symbols, three synthetic months: design = 2021-01..02, holdout = 2021-03 (warm-up 2021-02).
    With btc_phi > 0 BTCUSDT has strongly autocorrelated minutes (a momentum rule must pass); ETH and SOL are noise."""
    raw = tmp_path / "raw"
    monkeypatch.setattr(fm, "RAW_1M", raw)
    monkeypatch.setattr(fm, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(fm, "REPORT_DIR", tmp_path / "report")
    monkeypatch.setattr(fm, "DATA_FIRST_MONTH", "2021-01")
    monkeypatch.setattr(fm, "DATA_LAST_MONTH", "2021-03")
    monkeypatch.setattr(fm, "DESIGN_FIRST_MONTH", "2021-01")
    monkeypatch.setattr(fm, "DESIGN_LAST_MONTH", "2021-02")
    monkeypatch.setattr(fm, "HOLDOUT_WARMUP_MONTH", "2021-02")
    monkeypatch.setattr(fm, "HOLDOUT_FIRST_MONTH", "2021-03")
    monkeypatch.setattr(fm, "HOLDOUT_LAST_MONTH", "2021-03")
    months = ["2021-01", "2021-02", "2021-03"]
    sizes = [(fm.month_bounds_ms(m)[1] - fm.month_bounds_ms(m)[0]) // 60000 for m in months]
    n = sum(sizes)
    for si, sym in enumerate(fm.SYMBOLS):
        rng = np.random.default_rng(1000 + si)
        phi = btc_phi if sym == "BTCUSDT" else 0.0
        eps = (12e-4 if phi else 4e-4) * rng.standard_normal(n)
        r = np.empty(n)
        prev = 0.0
        for i in range(n):
            prev = phi * prev + eps[i]
            r[i] = prev
        c = 100.0 * np.cumprod(1.0 + r)
        o = np.concatenate(([100.0], c[:-1]))
        h = np.maximum(o, c) * (1.0 + 1e-4 * rng.random(n))
        l = np.minimum(o, c) * (1.0 - 1e-4 * rng.random(n))
        vol = np.ones(n)
        vol[3000:3010] = 0.0
        a = 0
        for mi, (m, sz) in enumerate(zip(months, sizes)):
            sl = slice(a, a + sz)
            drop = ((20000, 30),) if (sym == "SOLUSDT" and mi == 0) else ()
            _write_month(raw, sym, m, o[sl], h[sl], l[sl], c[sl], vol[sl], header=(mi == 2), drop=drop)
            a += sz
    return tmp_path


@pytest.fixture()
def tiny_world(tmp_path, monkeypatch):
    return _build_world(tmp_path, monkeypatch, btc_phi=0.75)


@pytest.fixture()
def noise_world(tmp_path, monkeypatch):
    return _build_world(tmp_path, monkeypatch, btc_phi=0.0)


def test_pipeline_end_to_end_and_the_holdout_seal(tiny_world):
    run = tiny_world / "run"
    assert fm.stage_verify() == 0
    # sealed: no holdout month can be parsed, no holdout stage can run
    with pytest.raises(SystemExit, match="sealed"):
        fm.load_bars("BTCUSDT", "2021-02", "2021-03")
    with pytest.raises(SystemExit, match="sealed"):
        fm.stage_holdout()
    with pytest.raises(SystemExit, match="sealed"):
        fm.stage_descriptive()
    # the design month loads; the data report sees the hole and the zero-volume minutes
    bars, rep = fm.load_bars("SOLUSDT", "2021-01", "2021-02")
    assert rep["bars_expected"] == (31 + 28) * 1440 and rep["bars_missing"] == 30 and rep["missing_runs"] == 1
    assert rep["missing_run_list"] == [{"start_utc": "2021-01-14T21:20Z", "minutes": 30}]
    assert rep["zero_volume_bars"] == 10 and rep["zero_trade_count_bars"] == 10 and rep["files_with_header_row"] == 0
    assert np.isnan(bars.c[20000:20030]).all() and not bars.tradeable[3000:3010].any()

    assert fm.stage_design() == 0
    ledger = json.loads((run / "design_ledger.json").read_text())
    rows = ledger["rows"]
    assert len(rows) == 129 and ledger["meta"]["holdout_months_parsed"] == 0
    assert (run / "design_ledger.csv").read_text().count("\n") == 130
    byid = {r["pair_id"]: r for r in rows}
    mom = byid["BTCUSDT|M1.k1.x1.h1"]
    assert mom["design_pass"] is True and mom["mean_bp_net"] > 0 and mom["t_net"] > 3
    assert not any(r["design_pass"] for r in rows if r["symbol"] != "BTCUSDT")
    for r in rows:                                                # identities that must hold on every row
        if r["n_trades"]:
            assert r["mean_bp_net"] == pytest.approx(r["mean_bp_gross"] - r["round_trip_cost_bp"], abs=1e-9)
            assert r["mean_bp_maker"] == pytest.approx(r["mean_bp_gross"] - 4.0, abs=1e-9)
            assert r["breakeven_cost_side_bp"] == pytest.approx(r["mean_bp_gross"] / 2, abs=1e-12)
            assert r["n_long"] + r["n_short"] == r["n_trades"]
            assert (r["exits_time"] + r["exits_stop"] + r["exits_ratchet_stop"] + r["exits_gap_stop"]
                    + r["exits_take_profit"]) == r["n_trades"]
    ctrl = (run / "control_design.csv").read_text().splitlines()
    assert len(ctrl) == 130

    # still sealed until the passers are frozen
    with pytest.raises(SystemExit, match="sealed"):
        fm.stage_holdout()
    assert fm.stage_passers() == 0
    frozen = json.loads((run / "DESIGN_PASSERS.json").read_text())
    assert frozen["n_pairs"] == 129 and frozen["n_passers"] == len(frozen["passers"]) >= 1
    assert "BTCUSDT|M1.k1.x1.h1" in {p["pair_id"] for p in frozen["passers"]}
    assert (run / "DESIGN_PASSERS.sha256").read_text().split()[0] == fm.sha256_file(run / "DESIGN_PASSERS.json")
    assert frozen["design_ledger_csv_sha256"] == fm.sha256_file(run / "design_ledger.csv")

    # the design cannot be silently re-run after the freeze
    with pytest.raises(SystemExit, match="frozen"):
        fm.stage_design()

    assert fm.stage_holdout() == 0
    hp = json.loads((run / "holdout_passers.json").read_text())
    assert {r["pair_id"] for r in hp["rows"]} == {p["pair_id"] for p in frozen["passers"]}
    assert all(r["window"] == "holdout" and "holdout_pass" in r for r in hp["rows"])
    hmom = {r["pair_id"]: r for r in hp["rows"]}["BTCUSDT|M1.k1.x1.h1"]
    assert hmom["holdout_pass"] is True and hmom["n_days_window"] == 31

    assert fm.stage_descriptive() == 0
    desc = json.loads((run / "holdout_descriptive.json").read_text())
    assert len(desc["rows"]) == 129 and "DESCRIPTIVE" in desc["meta"]["status"]
    assert all("holdout_pass" not in r for r in desc["rows"])
    # holdout trades start in the holdout month: the first possible entry is 2021-03-01 00:00
    dmom = {r["pair_id"]: r for r in desc["rows"]}["BTCUSDT|M1.k1.x1.h1"]
    assert dmom["n_trades"] == hmom["n_trades"] and dmom["mean_bp_net"] == pytest.approx(hmom["mean_bp_net"])

    # the frozen tables are regenerated byte for byte, and the sensitivity stage starts from the same baseline
    assert fm.stage_reproduce() == 0
    again = json.loads((run / "REPRODUCTION.json").read_text())
    assert again["all_identical"] is True and len(again["files"]) == 4
    assert fm.stage_sensitivity() == 0
    sens = json.loads((run / "sensitivity_design.json").read_text())
    assert [s["reading"].split("_")[0] for s in sens["summary"]] == ["R0", "S1", "S2", "S3"]
    assert sens["summary"][0]["pairs"] == 129 and sens["summary"][3]["pairs"] == 12
    assert sens["summary"][0]["largest_gross_change_vs_registered_bp"] == 0.0
    assert sens["summary"][2]["trades"] > sens["summary"][0]["trades"]             # re-entry at the exit print trades more
    # the report text was written for "no passer": with a passer it must refuse rather than tell the wrong story
    with pytest.raises(SystemExit, match="no design passer"):
        fm.stage_report()

    # tampering with the ledger after the freeze closes the holdout again
    p = run / "design_ledger.csv"
    p.write_text(p.read_text() + "x\n")
    with pytest.raises(SystemExit, match="changed after"):
        fm.stage_holdout()


def test_unverified_zip_is_refused(tiny_world):
    z = fm.zip_path("ETHUSDT", "2021-01")
    z.write_bytes(z.read_bytes() + b"x")
    assert fm.stage_verify() == 1
    with pytest.raises(SystemExit, match="published sha256"):
        fm.load_bars("ETHUSDT", "2021-01", "2021-01")


def test_clustered_t_matches_statsmodels_on_random_data():
    sm = pytest.importorskip("statsmodels.api")
    rng = np.random.default_rng(12)
    day = np.sort(rng.integers(0, 200, size=5000))
    shock = 3e-4 * rng.standard_normal(200)                                   # a common daily component
    v = 1e-4 + shock[day] + 8e-4 * rng.standard_normal(5000)
    t, g = fm.cluster_t(v, day)
    res = sm.OLS(v, np.ones(len(v))).fit(cov_type="cluster", cov_kwds={"groups": day})
    assert g == len(np.unique(day)) and t == pytest.approx(float(res.tvalues[0]), rel=1e-10)
    assert abs(t) < abs(v.mean() / (v.std(ddof=1) / math.sqrt(len(v))))        # clustering lowers |t| here


# --------------------------------------------------- the real archive (skipped when it is not on disk)
REAL_SLICES = [("BTCUSDT", "2021-02", "2021-03"), ("SOLUSDT", "2022-02", "2022-04"), ("ETHUSDT", "2023-09", "2023-11")]


def _need_archive(sym, first, last):
    if not all(fm.zip_path(sym, m).exists() for m in fm.month_range(first, last)):
        pytest.skip("1-minute archive not on disk")


@pytest.mark.parametrize("sym,first,last", REAL_SLICES)
def test_real_archive_slices_match_the_reference_simulator(sym, first, last):
    """Design-window months only (the loader refuses anything later until the passers are frozen). The slices
    hold real zero-volume runs (BTC 2021-03-02, ETH 2023-09 / 2023-11) and the two SOLUSDT archive holes."""
    _need_archive(sym, first, last)
    bars, rep = fm.load_bars(sym, first, last)
    cache = fm.SignalCache(bars)
    w0, w1 = 1500, bars.n - 1
    total = 0
    kinds = set()
    for f in fm.formulas():
        side, sg = cache.signal(f)
        tr = fm.simulate(bars, f, side, sg, w0, w1)
        ref, deferred = ref_sim(bars, f, side, sg, w0, w1)
        assert len(ref) == len(tr) and deferred == tr.deferred_exits, f.fid
        got = list(zip(tr.sig.tolist(), tr.entry.tolist(), tr.exit.tolist(), tr.side.tolist(), tr.kind.tolist()))
        assert got == [(s, e, x, sd, kd) for s, e, x, sd, _, kd in ref], f.fid
        assert np.allclose(tr.exit_px, [r[4] for r in ref], rtol=1e-12, atol=0.0), f.fid
        total += len(tr)
        kinds |= set(tr.kind.tolist())
    assert total > 100_000 and kinds == {0, 1, 2, 3, 4}
    if sym == "SOLUSDT":
        assert rep["bars_missing"] == 7200 and rep["missing_runs"] == 2
    else:
        assert rep["bars_missing"] == 0 and rep["zero_volume_bars"] > 0


@pytest.mark.parametrize("sym,k,x,h", [("BTCUSDT", 1, 1, 1), ("SOLUSDT", 5, 2, 5), ("ETHUSDT", 15, 3, 60)])
def test_frozen_design_ledger_is_reproduced_by_an_independent_pandas_path(sym, k, x, h):
    pd = pytest.importorskip("pandas")
    ledger = fm.RUN_DIR / "design_ledger.json"
    _need_archive(sym, fm.DESIGN_FIRST_MONTH, fm.DESIGN_LAST_MONTH)
    if not ledger.exists():
        pytest.skip("no design ledger on disk")
    row = {r["pair_id"]: r for r in json.loads(ledger.read_text())["rows"]}[f"{sym}|M1.k{k}.x{x}.h{h}"]
    bars, _ = fm.load_bars(sym, fm.DESIGN_FIRST_MONTH, fm.DESIGN_LAST_MONTH)
    df = pd.DataFrame({"o": bars.o, "c": bars.c, "v": bars.vol})
    r = df["c"] / df["c"].shift(k) - 1.0
    sig = r.rolling(1440, min_periods=1440).std()                 # pandas: ddof = 1, the window ends at the row
    side = np.where(r > x * sig, 1, np.where(r < -x * sig, -1, 0)).tolist()
    o = df["o"].to_numpy()
    tradeable = (np.isfinite(o) & (df["v"].to_numpy() > 0)).tolist()
    n = len(df)
    gross = []
    t = 0
    while t < n - 1 - h:                                          # the last allowed signal has t + 1 + h = n - 1
        if side[t] != 0 and tradeable[t + 1]:
            e = t + 1
            xx = e + h
            while xx < n and not tradeable[xx]:
                xx += 1
            if xx >= n:
                break
            gross.append(side[t] * (o[xx] / o[e] - 1.0))
            t = xx
        else:
            t += 1
    assert len(gross) == row["n_trades"]
    assert float(np.mean(gross)) * 1e4 == pytest.approx(row["mean_bp_gross"], abs=1e-9)
    assert float(np.mean(gross)) * 1e4 - row["round_trip_cost_bp"] == pytest.approx(row["mean_bp_net"], abs=1e-9)


def test_frozen_ledger_t_statistics_match_statsmodels_on_the_real_trades():
    sm = pytest.importorskip("statsmodels.api")
    ledger = fm.RUN_DIR / "design_ledger.json"
    sym = "ETHUSDT"
    _need_archive(sym, fm.DESIGN_FIRST_MONTH, fm.DESIGN_LAST_MONTH)
    if not ledger.exists():
        pytest.skip("no design ledger on disk")
    rows = {r["pair_id"]: r for r in json.loads(ledger.read_text())["rows"]}
    bars, _ = fm.load_bars(sym, fm.DESIGN_FIRST_MONTH, fm.DESIGN_LAST_MONTH)
    cache = fm.SignalCache(bars)
    for fid in ("M1.k15.x3.h60", "M2.N30.y1", "M3.a1.b2"):
        side, sg = cache.signal(F[fid])
        tr = fm.simulate(bars, F[fid], side, sg, 0, bars.n - 1)
        row = rows[f"{sym}|{fid}"]
        net = tr.gross - 2 * fm.base_cost_side_bp(sym) * 1e-4
        day = tr.entry // 1440
        res = sm.OLS(net, np.ones(len(net))).fit(cov_type="cluster", cov_kwds={"groups": day})
        assert row["t_net"] == pytest.approx(float(res.tvalues[0]), rel=1e-9)
        daily = np.zeros(1095)
        np.add.at(daily, day, net)
        assert row["sharpe_ann_net"] == pytest.approx(daily.mean() / daily.std(ddof=1) * math.sqrt(365), rel=1e-9)
        assert row["n_trades"] == len(tr) and row["mean_bp_gross"] == pytest.approx(tr.gross.mean() * 1e4, abs=1e-9)


def test_sensitivity_switches_default_to_the_registered_behaviour():
    bars = mk(synth(6000, 77, zeros=((2500, 3),)))
    c0, c1 = fm.SignalCache(bars), fm.SignalCache(bars, sigma_lag=1)
    assert np.array_equal(c1.sigma(5)[1:], c0.sigma(5)[:-1], equal_nan=True) and np.isnan(c1.sigma(5)[0])
    more = 0
    for f in fm.formulas():
        side, sg = c0.signal(f)
        a = fm.simulate(bars, f, side, sg, 1500, 5999)
        b = fm.simulate(bars, f, side, sg, 1500, 5999, reentry_at_exit=False, trail_ratchet=True)
        assert np.array_equal(a.sig, b.sig) and np.array_equal(a.exit_px, b.exit_px)
        c = fm.simulate(bars, f, side, sg, 1500, 5999, reentry_at_exit=True)
        assert (c.entry[1:] >= c.exit[:-1]).all() and len(c) >= len(a)       # may re-enter AT the exit print, never before
        more += len(c) - len(a)
        if f.family == "M2":
            d = fm.simulate(bars, f, side, sg, 1500, 5999, trail_ratchet=False)
            assert not (d.kind == fm.KIND_RATCHET).any() and (a.kind == fm.KIND_RATCHET).any()
    assert more > 0


def test_noise_world_has_no_passer_and_the_report_is_written_from_the_files(noise_world):
    """Pure noise in all three symbols: nothing may pass, the passers-only holdout must stay empty, and the
    report builder must run end to end on whatever the files say."""
    run = noise_world / "run"
    assert fm.stage_design() == 0 and fm.stage_passers() == 0
    frozen = json.loads((run / "DESIGN_PASSERS.json").read_text())
    assert frozen["n_passers"] == 0 and frozen["passers"] == [] and frozen["n_mean_net_positive"] == 0
    assert fm.stage_holdout() == 0
    assert (run / "holdout_passers.csv").read_text().count("\n") == 1          # header only
    assert json.loads((run / "holdout_passers.json").read_text())["rows"] == []
    assert fm.stage_descriptive() == 0 and fm.stage_sensitivity() == 0 and fm.stage_reproduce() == 0
    rows = json.loads((run / "design_ledger.json").read_text())["rows"]
    ctrl = {r.split(",")[0]: r for r in (run / "control_design.csv").read_text().splitlines()[1:]}
    assert len(ctrl) == 129
    # on noise every fixed-hold pair loses about its round trip: gross within a few bp of zero
    m1 = [r for r in rows if r["family"] == "M1" and r["n_trades"] > 2000]
    assert len(m1) > 30 and all(abs(r["mean_bp_gross"]) < 1.0 for r in m1)
    assert all(r["mean_bp_net"] < -8.0 for r in m1)
    (run / "download_manifest.json").write_text(json.dumps({
        "files_expected": 9, "status_counts": {"ok": 9}, "bytes_total": 9_000_000,
        "files": [{"status": "ok", "checksum_ok": True, "fetched_utc": "2026-01-01T00:00:00Z"}] * 9}))
    assert fm.stage_report() == 0
    text = (noise_world / "report" / "FASTMOM_RESULTS.md").read_text()
    for needle in ("## 1. Verdict", "DEAD at this cost", "### 3.1 M1", "### 3.2 M2", "### 3.3 M3", "## 6. Maker optimistic bound",
                   "### 7.2 Descriptive table", "### 8.1 Random-entry control", "## 10. Every open point",
                   "## 11. Does the verdict depend", "## 12. Limits", "## 13. Deviations and disclosures", "claude-fable-5-2"):
        assert needle in text, needle
    assert text.count("| BTC M1.") == 36 and text.count("| SOL M2.") == 4 and text.count("| ETH M3.") == 3
    import re
    assert re.search(r"(?<![a-z])nan(?![a-z])", text.lower()) is None            # no undefined number leaked into the text
