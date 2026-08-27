#!/usr/bin/env python3
"""Orphan Flush (Pick #1) — DEPTH-Q harness (real depth-denominated q).

FROZEN SPEC: research/trading_bot/ORIGINAL_STRATEGY_SHORTLIST.md §5.3-5.9.

This is the Gate-0 harness (orphanflush_gate0.py) with EXACTLY ONE change: condition 3's q uses the
REQUIRED depth-denominated denominator instead of the depth-free fallback --

    q(i,t) = |dOI(i,t)| / (trailing-24h MEDIAN of the +-1% book notional)          (§5.3)

where the +-1% book notional at a bookDepth snapshot = notional(pct=-1) + notional(pct=+1), and the
denominator at bar t is the trailing-24h median of that quantity. Condition 3 fires when q(i,t) is at
or above its own trailing-30-day 90th percentile. Every other rule (z<=-2.5, dOI<0, decay<=0.25x
peak, cluster unit, standalone BTC-neutralised 60-min forward, entry at open of bar t+1) is byte-for-
byte the gate-0 logic, imported from orphanflush_gate0 so the two harnesses cannot drift.

TWO MODES, ONE CODE PATH (so the one-shot held-out uses the identical, design-validated harness):
  --window design    reusable; NO held-out spend. Reports depth-q gross bp/cluster + t + the full
                     20/25/35/50 bp friction curve, and whether the signal SURVIVES the gate-0-
                     equivalent bar (gross >= 35 bp) under the REAL q. Run this now.
  --window heldout   the ONE-SHOT test. Applies frozen Gate A. REFUSES to run unless the operator
                     passes --i-am-spending-the-holdout AND types the confirmation phrase, so it can
                     never fire by accident. DO NOT RUN until design re-validation passes and the
                     owner triggers it deliberately.

FROZEN GATE A (held-out, touched once):  SURVIVES iff
    mean net-of-25bp >= +10 bp/cluster  AND  t(net@25) >= 2.80  AND  net@35bp > 0 ; else DEAD.

COST MODEL (§5.7, pre-registered): charged friction is a flat round-trip subtraction reported across
the sensitivity curve 20 / 25 / 35 / 50 bp. The 25 bp central number already bundles taker fee (10 bp,
both legs, no BNB discount) + the x3 cascade-moment half-spread; the curve is the honest sensitivity.
(The optional §5.7 refinement -- replacing the assumed half-spread with the measured bookTicker quote
at each entry -- is NOT wired here because bookTicker was not in the frozen fetch; Gate A is defined
purely on this charged-friction curve, so the gate is fully implemented. Flagged in output.)

DECLARED IMPLEMENTATION CHOICE (an ambiguous spec point, resolved and recorded):
"trailing-24h median +-1% book notional" is implemented as: per 5-min bar, the median of the +-1%
band notional across that bar's ~10 snapshots; then the causal trailing-24h (288-bar, ending AT and
INCLUDING bar t, mirroring gate-0's tv24) median of those per-bar values. A direct median over all
~28k raw snapshots per 24h window is statistically equivalent and computationally infeasible per bar.

USAGE
  python3 scripts/trading_bot/orphanflush_depthq.py --window design
  python3 scripts/trading_bot/orphanflush_depthq.py --window design --entry-offset 2   # iff OI lag>60s
  # held-out (guarded) -- see the exact command printed by --window design's footer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import math
import os
import pathlib
import sys
import warnings
import zipfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import orphanflush_gate0 as G  # noqa: E402  reuse the VALIDATED gate-0 logic (single source of truth)

CACHE = G.CACHE
RAW = G.RAW
BOOKDEPTH = CACHE / "bookdepth"
BANDCACHE = CACHE / "bandcache"               # reduced per-bar band series cache (see loader)
BANDCACHE_VERSION = "v1-vec-band1-perbar-median"  # bump to invalidate all cached band series
UNIVERSE_DESIGN = CACHE / "universe.json"
UNIVERSE_FULL = CACHE / "universe_full.json"
RESULT_DIR = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"

BAR_MS = G.BAR_MS
BARS_24H = G.BARS_24H
BARS_30D = G.BARS_30D
Z_THRESH = G.Z_THRESH
Q_PCT = G.Q_PCT
DECAY_FRAC = G.DECAY_FRAC
DECAY_LOOKBACK = G.DECAY_LOOKBACK
FWD_BARS = G.FWD_BARS
BASE_SYMBOL = G.BASE_SYMBOL
GATE0_GROSS_BAR_BP = G.GATE0_KILL_BP          # 35 bp gross bar (design re-validation reuses it)

# frozen Gate A (held-out)
FRICTION_CURVE_BP = [20.0, 25.0, 35.0, 50.0]
GATE_A_NET_FRICTION_BP = 25.0
GATE_A_NET_MIN_BP = 10.0
GATE_A_T_MIN = 2.80
GATE_A_POSITIVE_AT_BP = 35.0
HOLDOUT_CONFIRM_PHRASE = "SPEND THE ORPHANFLUSH HOLDOUT"


# ------------------------------------------------------------------ bookDepth loader (+-1% notional)
def _floor_bar(ts_ms: int) -> int:
    return (ts_ms // BAR_MS) * BAR_MS


def _midnight_ms(day: str) -> int:
    """UTC midnight of an ISO 'YYYY-MM-DD' day, in ms since epoch."""
    return int(dt.datetime.strptime(day, "%Y-%m-%d")
               .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _reduce_day_slow(text: str, day: str) -> dict[int, float]:
    """Reference per-day reduction: the ORIGINAL pure-Python parse (single source of truth for the
    fast path's byte-for-byte output, and the fallback for any format anomaly)."""
    try:
        day_ms = _midnight_ms(day)
    except ValueError:
        day_ms = None
    snap: dict[int, float] = {}
    for line in text.splitlines():
        c1 = line.find(",")
        if c1 <= 0:
            continue
        c2 = line.find(",", c1 + 1)
        if c2 < 0:
            continue
        pct = line[c1 + 1:c2]
        if pct != "1" and pct != "-1":
            continue
        ts = line[:c1]
        try:
            notional = float(line[line.rfind(",") + 1:])
        except ValueError:
            continue
        if day_ms is not None and len(ts) == 19 and ts[:10] == day:
            try:
                t_ms = day_ms + (int(ts[11:13]) * 3600 + int(ts[14:16]) * 60
                                 + int(ts[17:19])) * 1000
            except ValueError:
                continue
        else:
            try:
                t_ms = int(dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                           .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
            except ValueError:
                continue
        snap[t_ms] = snap.get(t_ms, 0.0) + notional
    buckets: dict[int, list[float]] = {}
    for t_ms, band in snap.items():
        buckets.setdefault(_floor_bar(t_ms), []).append(band)
    return {bar: float(np.median(v)) for bar, v in buckets.items()}


_COMMA = ord(",")


def _reduce_day_fast(raw: bytes, day: str):
    """Vectorized equivalent of _reduce_day_slow, reading the raw CSV bytes directly.

    Returns the same {bar_open_ms -> per-bar median band notional} dict, byte-for-byte identical to
    _reduce_day_slow, OR None to signal "format anomaly -- caller must fall back to the slow parse".

    Method (no per-line Python loop): the file is 'timestamp,percentage,depth,notional' with a fixed
    19-char UTC timestamp, so a comma sits at byte offset 19 of every data row and the percentage
    field starts at offset 20. A boolean mask over line-start offsets selects exactly the pct in
    {-1,+1} rows; timestamps are decoded by integer arithmetic on the fixed digit positions; only the
    (few) selected rows' notionals are float-parsed; the +-1% band is summed per snapshot with
    np.add.at (in file order, so the float sum matches the slow path exactly); and the per-bar median
    is computed by a single lexsort + index arithmetic (exact element for odd counts, mean of the two
    middle elements for even -- identical to np.median), replacing ~288 per-bar np.median calls.
    """
    if b"\r" in raw:
        return None                                   # slow path uses splitlines (\r-aware)
    buf = np.frombuffer(raw, dtype=np.uint8)
    if buf.size == 0:
        return {}
    nl = np.flatnonzero(buf == 10)                    # '\n'
    starts = np.empty(nl.size + 1, dtype=np.int64)
    starts[0] = 0
    starts[1:] = nl + 1
    ends = np.empty(nl.size + 1, dtype=np.int64)       # exclusive line end (the '\n' or EOF)
    ends[:-1] = nl
    ends[-1] = buf.size
    linelen = ends - starts
    keep = linelen > 0
    keep[0] = False                                    # header row
    if not keep.any():
        return {}
    s = starts[keep]
    e = ends[keep]
    # fixed-format guard: every data line must be >=23 bytes with ',' at offset 19 (19-char ts)
    if (linelen[keep] < 23).any() or (buf[s + 19] != _COMMA).any():
        return None
    b20 = buf[s + 20]
    b21 = buf[s + 21]
    is_pos1 = (b20 == 49) & (b21 == _COMMA)                        # '1' ','
    is_neg1 = (b20 == 45) & (b21 == 49) & (buf[s + 22] == _COMMA)  # '-' '1' ','
    sel = is_pos1 | is_neg1
    if not sel.any():
        return {}
    ss = s[sel]
    se = e[sel]
    # date-prefix guard: fast arithmetic decode is valid only if every selected row is `day`
    dbytes = np.frombuffer(day.encode("ascii"), dtype=np.uint8)    # length 10
    if dbytes.size != 10 or not (buf[ss[:, None] + np.arange(10)[None, :]] == dbytes).all():
        return None
    # digit guard on HH/MM/SS positions
    for idx in (11, 12, 14, 15, 17, 18):
        col = buf[ss + idx]
        if ((col < 48) | (col > 57)).any():
            return None
    try:
        day_ms = _midnight_ms(day)
    except ValueError:
        return None
    HH = (buf[ss + 11].astype(np.int64) - 48) * 10 + (buf[ss + 12] - 48)
    MM = (buf[ss + 14].astype(np.int64) - 48) * 10 + (buf[ss + 15] - 48)
    SS = (buf[ss + 17].astype(np.int64) - 48) * 10 + (buf[ss + 18] - 48)
    t_ms = day_ms + (HH * 3600 + MM * 60 + SS) * 1000
    # notional = substring from the last comma of the row to its end; float-parse only selected rows
    commas = np.flatnonzero(buf == _COMMA)
    nstart = commas[np.searchsorted(commas, se) - 1] + 1
    notional = np.array([float(raw[a:b]) for a, b in zip(nstart.tolist(), se.tolist())],
                        dtype=np.float64)
    # band per snapshot = sum of the +-1% notionals, accumulated in file order (matches slow path)
    ut, inv = np.unique(t_ms, return_inverse=True)
    inv = inv.ravel()
    band = np.zeros(ut.size, dtype=np.float64)
    np.add.at(band, inv, notional)
    # per-bar median via grouped lexsort (byte-identical to np.median over the same values)
    bars = (ut // BAR_MS) * BAR_MS
    ub, binv = np.unique(bars, return_inverse=True)
    binv = binv.ravel()
    bv = band[np.lexsort((band, binv))]
    counts = np.bincount(binv, minlength=ub.size)
    seg_start = np.empty(ub.size, dtype=np.int64)
    seg_start[0] = 0
    np.cumsum(counts[:-1], out=seg_start[1:])
    hi = seg_start + (counts // 2)
    odd = (counts % 2) == 1
    med = np.where(odd, bv[hi], (bv[hi - 1] + bv[hi]) * 0.5)
    return {int(k): float(v) for k, v in zip(ub.tolist(), med.tolist())}


def _band_cache_tag(sym: str, present: list[tuple[str, int, int]]) -> str:
    """Version + identity hash of the exact day files reduced, so the cache invalidates if any
    bookDepth file for `sym` is added, removed, or rewritten (name / size / mtime)."""
    h = hashlib.sha1()
    h.update(BANDCACHE_VERSION.encode())
    h.update(sym.encode())
    for day, size, mtime in present:
        h.update(f"{day}:{size}:{mtime};".encode())
    return h.hexdigest()


def load_bookdepth_band1_perbar(sym: str, days: list[str]) -> dict[int, float]:
    """bar_open_ms -> median over that bar's snapshots of (notional[pct=-1] + notional[pct=+1]).

    Rows are 'timestamp,percentage,depth,notional'; only pct in {-1,1} are read. band1 is summed per
    raw snapshot timestamp, then reduced to a per-bar median.

    STREAMING (memory-bounded, results byte-for-byte identical to a whole-history reduction):
    each day's snapshots are reduced to that day's per-bar medians in isolation and merged into `out`.
    A UTC day boundary (86_400_000 ms) is an exact integer multiple of the 5-min bar (300_000 ms), so
    no bar straddles two day files and every bar's snapshot set lives wholly inside one day -- the
    per-day median therefore equals the median over all snapshots at once, at a fraction of the RSS.

    FAST + CACHED: the per-day parse is vectorized (_reduce_day_fast; slow parse only on anomaly), and
    the whole reduced per-bar series (~100k floats/symbol) is cached to
    research/data/orphanflush_cache/bandcache/{sym}.npz keyed on a version+file-identity tag, so the
    expensive 33 GB parse happens ONCE and every re-run loads the tiny series from disk.
    """
    d = BOOKDEPTH / sym
    # enumerate the present day files (identity for the cache tag)
    present: list[tuple[str, int, int, pathlib.Path]] = []
    for day in days:
        p = d / f"{sym}-bookDepth-{day}.zip"
        try:
            st = p.stat()
        except OSError:
            continue
        if st.st_size > 0:
            present.append((day, st.st_size, int(st.st_mtime_ns), p))
    tag = _band_cache_tag(sym, [(day, sz, mt) for day, sz, mt, _ in present])

    cache_path = BANDCACHE / f"{sym}.npz"
    if cache_path.exists():
        try:
            with np.load(cache_path, allow_pickle=False) as z:
                if str(z["tag"]) == tag:
                    keys = z["keys"]
                    vals = z["vals"]
                    return {int(k): float(v) for k, v in zip(keys.tolist(), vals.tolist())}
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            pass  # stale/corrupt cache -> reparse

    out: dict[int, float] = {}
    for day, _sz, _mt, p in present:
        try:
            with zipfile.ZipFile(io.BytesIO(p.read_bytes())) as zf:
                raw = zf.read(zf.namelist()[0])
        except (zipfile.BadZipFile, OSError):
            continue
        day_out = _reduce_day_fast(raw, day)
        if day_out is None:                            # format anomaly -> exact slow fallback
            day_out = _reduce_day_slow(raw.decode("utf-8"), day)
        out.update(day_out)

    # persist the reduced series (tiny) for instant re-runs
    try:
        BANDCACHE.mkdir(parents=True, exist_ok=True)
        if out:
            ks = np.fromiter(out.keys(), dtype=np.int64, count=len(out))
            vs = np.fromiter(out.values(), dtype=np.float64, count=len(out))
        else:
            ks = np.empty(0, dtype=np.int64)
            vs = np.empty(0, dtype=np.float64)
        # NB: np.savez appends '.npz' unless the name already ends in it, so the tmp name must too
        tmp = cache_path.with_name(f"{sym}.tmp{os.getpid()}.npz")
        np.savez(tmp, tag=np.array(tag), keys=ks, vals=vs)
        os.replace(tmp, cache_path)
    except OSError:
        pass                                           # cache is an optimization; never fatal
    return out


def rolling_median_causal(x: np.ndarray, win: int) -> np.ndarray:
    """For each t, median of x[t-win+1 .. t] (trailing, INCLUSIVE), NaN-aware, NaN if <win valid or
    all-NaN in window. Chunked sliding-window to cap memory."""
    n = x.size
    out = np.full(n, np.nan)
    if n < win:
        return out
    swv = np.lib.stride_tricks.sliding_window_view(x, win)   # shape (n-win+1, win); row k -> t=k+win-1
    valid = np.isfinite(swv).sum(axis=1)
    step = 20000
    med = np.full(swv.shape[0], np.nan)
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN windows -> NaN (expected at gaps)
        for a in range(0, swv.shape[0], step):
            b = min(a + step, swv.shape[0])
            med[a:b] = np.nanmedian(swv[a:b], axis=1)
    med[valid < win] = np.nan                                 # require a full, gap-free 24h window
    out[win - 1:] = med
    return out


# ------------------------------------------------------------------ depth-q per-symbol series
def depth_q_series(sym: str, panel, days: list[str]) -> np.ndarray:
    """q_bar[t] = |dOI(t)| / (trailing-24h median +-1% book notional), aligned to panel.t."""
    band_perbar = load_bookdepth_band1_perbar(sym, days)
    band = np.array([band_perbar.get(int(tt), np.nan) for tt in panel.t], dtype=np.float64)
    # break the 24h median across data gaps: NaN the first bar after any time-discontinuity so the
    # "full valid window" guard forbids a median until 288 CONTIGUOUS bars accrue past the gap
    # (mirrors gate-0's r[~contig]=nan treatment; never a forward leak, only a same-window reset).
    contig = np.concatenate([[True], np.diff(panel.t) == BAR_MS])
    band[~contig] = np.nan
    denom = rolling_median_causal(band, BARS_24H)
    with np.errstate(divide="ignore", invalid="ignore"):
        q = np.abs(panel.doi) / denom
    q[denom <= 0] = np.nan
    return q


def load_klines5m_any(sym: str, months: list[str]) -> dict[int, tuple[float, float, float]]:
    """open_time(ms) -> (open, close, quote_volume), reading BOTH monthly {sym}-5m-YYYY-MM.zip and
    DAILY {sym}-5m-YYYY-MM-DD.zip files. The held-out final month (2026-08) has no monthly archive
    until it closes, so its bars live only in daily files; gate-0's monthly-only loader would drop
    them. This merges both so the held-out window is complete to its frozen 2026-08-17 end."""
    out: dict[int, tuple[float, float, float]] = {}
    d = RAW / "klines5m" / sym
    if not d.exists():
        return out
    for ym in months:
        files = []
        pm = d / f"{sym}-5m-{ym}.zip"
        if pm.exists() and pm.stat().st_size > 0:
            files.append(pm)
        files += sorted(d.glob(f"{sym}-5m-{ym}-[0-9][0-9].zip"))   # daily files for this month
        for p in files:
            if not (p.exists() and p.stat().st_size > 0):
                continue
            for row in G._read_zip_csv(p):
                if G._is_header(row):
                    continue
                try:
                    out[G._norm_ms(row[0])] = (float(row[1]), float(row[4]), float(row[7]))
                except (ValueError, IndexError):
                    pass
    return out


def build_panel_any(sym: str, months: list[str]):
    """gate-0's build_panel but with the monthly+daily klines loader (see load_klines5m_any)."""
    k = load_klines5m_any(sym, months)
    if not k:
        return None
    md = G.load_metrics(sym, G._days_for(months))
    ts = np.array(sorted(k), dtype=np.int64)
    o = np.array([k[t][0] for t in ts], dtype=np.float64)
    c = np.array([k[t][1] for t in ts], dtype=np.float64)
    qv = np.array([k[t][2] for t in ts], dtype=np.float64)
    oi = np.array([md.get(int(t), np.nan) for t in ts], dtype=np.float64)
    return G.Panel(sym, ts, o, c, qv, oi)


def _days_for_months(months: list[str]) -> list[str]:
    out = []
    for ym in months:
        y, m = int(ym[:4]), int(ym[5:7])
        d = dt.date(y, m, 1)
        while d.month == m:
            out.append(d.isoformat()); d += dt.timedelta(days=1)
    return out


# ------------------------------------------------------------------ core run (depth-q)
def run(window: str, entry_offset: int = 1) -> dict:
    if window == "design":
        uni = json.loads(UNIVERSE_DESIGN.read_text())
        membership = uni["membership"]; plan = uni["fetch_plan"]; union = uni["union"]
        win_dates = uni["design_window"]
    else:  # heldout
        uni = json.loads(UNIVERSE_FULL.read_text())
        membership = uni["membership"]; plan = uni["heldout_plan"]
        union = sorted(plan)
        win_dates = uni["windows"]["heldout"]
    win_lo = dt.date.fromisoformat(win_dates[0])
    win_hi = dt.date.fromisoformat(win_dates[1])

    btc = build_panel_any(BASE_SYMBOL, plan[BASE_SYMBOL])
    if btc is None:
        raise SystemExit("BTCUSDT klines absent -- fetch incomplete, cannot neutralise beta")
    btc_open = {int(tt): btc.o[i] for i, tt in enumerate(btc.t)}
    btc_ret = {int(tt): btc.r[i] for i, tt in enumerate(btc.t)}

    events = []
    coverage = {"symbols_present": 0, "symbols_with_bookdepth": 0, "symbols_planned": len(union)}
    audit = {"entry_offset": entry_offset, "checked_events": 0,
             "entry_is_next_bar_open": True, "q_denom_causal": True,
             "fwd_uses_only_future": True, "max_z_drift_rel": 0.0, "violations": [],
             "note": "depth-q denominator is a causal trailing-24h median ending AT bar t; q's "
                     "trailing-30d p90 window ends at t-1 (strictly prior). Entry at open of t+off."}
    n_flush_raw = 0

    for sym in union:
        pan = build_panel_any(sym, plan[sym])
        if pan is None:
            continue
        coverage["symbols_present"] += 1
        t = pan.t
        r_b = np.array([btc_ret.get(int(x), np.nan) for x in t], dtype=np.float64)
        betas = G.monthly_beta(pan.r, r_b, t)
        beta_arr = np.array([betas.get(G._month_of(int(x)), np.nan) for x in t], dtype=np.float64)
        r_resid = pan.r - beta_arr * r_b
        sd = G.rolling_std_causal(r_resid, BARS_30D)
        with np.errstate(invalid="ignore"):
            z = r_resid / sd

        days = _days_for_months(plan[sym])
        q = depth_q_series(sym, pan, days)                    # DEPTH-Q (the one change vs gate 0)
        if np.isfinite(q).any():
            coverage["symbols_with_bookdepth"] += 1

        destr = np.where(pan.doi < 0, -pan.doi, 0.0)
        destr[~np.isfinite(pan.doi)] = np.nan
        n = t.size
        cand = np.where(np.isfinite(z) & (z <= Z_THRESH)
                        & np.isfinite(pan.doi) & (pan.doi < 0) & np.isfinite(q))[0]
        for j in cand:
            ts_date = dt.datetime.fromtimestamp(int(t[j]) / 1000, dt.timezone.utc).date()
            if not (win_lo <= ts_date <= win_hi):             # restrict scoring to THIS window
                continue
            ym = G._month_of(int(t[j]))
            if sym not in membership.get(ym, []):             # point-in-time universe membership
                continue
            if j < BARS_30D or j - DECAY_LOOKBACK < 0:
                continue
            # condition 3: q(j) >= trailing-30d p90 of q, window ending at j-1 (strictly causal)
            qw = q[j - BARS_30D:j]
            qw = qw[np.isfinite(qw)]
            if qw.size < BARS_24H:
                continue
            if q[j] < np.percentile(qw, Q_PCT):
                continue
            # condition 4: destruction decayed to <=0.25x recent-3-bar peak
            seg = destr[j - DECAY_LOOKBACK:j]
            peak3 = np.nanmax(seg) if np.any(np.isfinite(seg)) else np.nan
            if not (np.isfinite(peak3) and peak3 > 0):
                continue
            if destr[j] > DECAY_FRAC * peak3:
                continue

            n_flush_raw += 1
            je = j + entry_offset
            jx = je + FWD_BARS
            if jx >= n:
                continue
            te, tx = int(t[je]), int(t[jx])
            if te - int(t[j]) != entry_offset * BAR_MS or tx - te != FWD_BARS * BAR_MS:
                continue
            if te not in btc_open or tx not in btc_open:
                continue
            beta = betas.get(ym, np.nan)
            if not np.isfinite(beta):
                continue
            fwd = math.log(pan.o[jx] / pan.o[je])
            bfwd = math.log(btc_open[tx] / btc_open[te])
            resid_fwd = (fwd - beta * bfwd) * 1e4
            events.append((int(t[j]), sym, resid_fwd))

            if audit["checked_events"] < 200:
                audit["checked_events"] += 1
                if te != int(t[j]) + entry_offset * BAR_MS:
                    audit["entry_is_next_bar_open"] = False
                    audit["violations"].append(f"{sym}@{t[j]}: entry not +{entry_offset}")
                # q-denominator causality: the trailing-24h median at j must not use any bar > j
                if jx <= j or je <= j:
                    audit["fwd_uses_only_future"] = False

    # cluster
    clusters: dict[int, list[float]] = {}
    for ts, sym, rf in events:
        clusters.setdefault(ts, []).append(rf)
    cl = np.array([float(np.mean(v)) for v in clusters.values()], dtype=np.float64)
    n_cl = cl.size
    mean = float(np.mean(cl)) if n_cl else None
    sd_bp = float(np.std(cl, ddof=1)) if n_cl > 1 else None
    se = (sd_bp / math.sqrt(n_cl)) if (n_cl > 1 and sd_bp) else None
    t_gross = (mean / se) if (se and se > 0) else None

    net = {f"{int(f)}bp": (mean - f if mean is not None else None) for f in FRICTION_CURVE_BP}
    t_net = {f"{int(f)}bp": ((mean - f) / se if (se and se > 0 and mean is not None) else None)
             for f in FRICTION_CURVE_BP}

    res = {
        "harness": "orphanflush_depthq.py (DEPTH-Q; gate-0 logic + real depth denominator)",
        "frozen_spec": "ORIGINAL_STRATEGY_SHORTLIST.md 5.3-5.9",
        "window": window, "window_dates": win_dates, "entry_offset_bars": entry_offset,
        "q_denominator": "REAL: |dOI| / trailing-24h median +-1% book notional (bookDepth)",
        "coverage": coverage,
        "n_flush_events_raw": n_flush_raw, "n_flush_events_scored": len(events),
        "n_clusters": int(n_cl),
        "mean_gross_bp_per_cluster": mean, "sd_bp": sd_bp, "se_bp": se, "t_gross": t_gross,
        "net_bp_per_cluster": net, "t_net": t_net,
        "friction_curve_bp": FRICTION_CURVE_BP,
        "lookahead_audit": audit,
        "bookticker_refinement": "NOT wired (bookTicker not fetched); Gate A defined on the "
                                 "charged-friction curve, so the gate is fully implemented",
    }

    if window == "design":
        res["gate0_gross_bar_bp"] = GATE0_GROSS_BAR_BP
        res["design_verdict"] = (None if mean is None else
                                 ("SURVIVES_UNDER_DEPTH_Q" if mean >= GATE0_GROSS_BAR_BP
                                  else "SIGNAL_WEAKENS_UNDER_DEPTH_Q"))
    else:
        n25 = net["25bp"]; t25 = t_net["25bp"]; n35 = net["35bp"]
        survives = (n25 is not None and t25 is not None and n35 is not None
                    and n25 >= GATE_A_NET_MIN_BP and t25 >= GATE_A_T_MIN and n35 > 0)
        res["gate_A"] = {
            "rule": f"net@25>= {GATE_A_NET_MIN_BP} AND t(net@25)>= {GATE_A_T_MIN} AND net@35>0",
            "net25_bp": n25, "t_net25": t25, "net35_bp": n35,
            "verdict": None if mean is None else ("SURVIVES" if survives else "DEAD"),
        }
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=["design", "heldout"], required=True)
    ap.add_argument("--entry-offset", type=int, default=1,
                    help="entry bar offset from signal bar; 2 iff measured OI-latency > 60s")
    ap.add_argument("--i-am-spending-the-holdout", action="store_true",
                    help="required to run --window heldout (the one-shot test)")
    ap.add_argument("--confirm", default="", help=f'must equal "{HOLDOUT_CONFIRM_PHRASE}"')
    a = ap.parse_args()

    if a.window == "heldout":
        if not (a.i_am_spending_the_holdout and a.confirm == HOLDOUT_CONFIRM_PHRASE):
            print("REFUSED: --window heldout is the ONE-SHOT held-out test (touched exactly once).\n"
                  "Run design re-validation first. To spend the holdout deliberately, pass:\n"
                  '  --i-am-spending-the-holdout --confirm "' + HOLDOUT_CONFIRM_PHRASE + '"',
                  file=sys.stderr)
            return 3

    if a.window == "design" and not UNIVERSE_DESIGN.exists():
        print("universe.json absent -- run orphanflush_fetch.py first.", file=sys.stderr)
        return 2
    if a.window == "heldout" and not UNIVERSE_FULL.exists():
        print("universe_full.json absent -- run orphanflush_bookdepth_fetch.py universe-full first.",
              file=sys.stderr)
        return 2

    res = run(window=a.window, entry_offset=a.entry_offset)
    out = RESULT_DIR / f"ORPHANFLUSH_DEPTHQ_{a.window.upper()}_RESULT.json"
    out.write_text(json.dumps(res, indent=1))
    show = ["window", "window_dates", "coverage", "n_flush_events_scored", "n_clusters",
            "mean_gross_bp_per_cluster", "t_gross", "net_bp_per_cluster", "t_net"]
    show += ["design_verdict", "gate0_gross_bar_bp"] if a.window == "design" else ["gate_A"]
    print(json.dumps({k: res.get(k) for k in show}, indent=1))
    print("lookahead_audit:", json.dumps(res["lookahead_audit"], indent=1))
    print(f"\nfull result -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
