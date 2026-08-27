#!/usr/bin/env python3
"""Orphan Flush (Pick #1) — GATE 0: gross-at-zero-cost census on the DESIGN window.

FROZEN SPEC: research/trading_bot/ORIGINAL_STRATEGY_SHORTLIST.md §5.3–5.5, gate 0.

    "Run the FLUSH leg on the design window only, at zero friction, primary estimand
     (standalone, BTC-neutralised, 60-min, cluster-level).
     DEAD if mean gross < 35 bp per cluster."

This harness reads ONLY from research/data/orphanflush_cache/ (metrics + 5m klines, no bookDepth).
It prints the standalone mean gross bp/cluster, the cluster-level t-stat, and n_clusters, plus a
LOOKAHEAD AUDIT that proves the signal at bar t uses no information past bar t and that entry is at
the OPEN of bar t+1 (T3 found a 9-min lookahead worth half its result — this asserts against it).

WHAT IS FROZEN AND OBEYED HERE
------------------------------
* Universe: point-in-time top-80 by trailing-30d quote vol (built by orphanflush_fetch.py; membership
  enforced per event).
* FLUSH event at bar t iff all four hold (§5.3):
    1. z(i,t) <= -2.5              BTC-neutralised residual, trailing-30d beta + trailing-30d sd
    2. dOI(i,t) < 0               open interest destroyed
    3. q(i,t) >= trailing-30d p90 destruction large vs the book that absorbed it
    4. destruction rate decayed to <= 0.25x its recent-3-bar peak  the seller is finished
* Observation unit = the FLUSH CLUSTER: all flush events sharing a 5-min timestamp, equal-weighted
  to one return (§5.4).
* Estimand = STANDALONE BTC-neutralised 60-min forward return of the flush leg, entry at OPEN of
  bar t+1, exit 60 min (12 bars) later. Zero friction for gate 0.

DELIBERATE, DECLARED SUBSTITUTION (the one place the frozen plan is ambiguous for gate 0)
-----------------------------------------------------------------------------------------
q's PRIMARY denominator is the trailing-24h median +-1% book notional, which requires bookDepth.
§5.2 / §7 state gate 0 needs NO bookDepth. §5.3 supplies the DEPTH-FREE FALLBACK
(|dOI| / trailing-24h quote volume) for exactly the depth-free context. Gate 0 therefore uses the
depth-free q. The depth-denominated q is required before the HELD-OUT run, not for this census.
Flagged in the output.

USAGE (run only once the fetch has landed; safe to run on a partial cache — it reports coverage):
    python3 scripts/trading_bot/orphanflush_gate0.py
    python3 scripts/trading_bot/orphanflush_gate0.py --entry-offset 1   # 2 iff OI-latency>60s
    python3 scripts/trading_bot/orphanflush_gate0.py --audit-only
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import pathlib
import sys
import zipfile

import numpy as np

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "orphanflush_cache"
RAW = CACHE / "raw"
UNIVERSE = CACHE / "universe.json"
RESULT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot" / "ORPHANFLUSH_GATE0_RESULT.json"

BAR_MS = 300_000                 # 5 minutes
BARS_24H = 288
BARS_30D = 288 * 30
Z_THRESH = -2.5
Q_PCT = 90.0                     # trailing-30d q percentile gate
DECAY_FRAC = 0.25                # destruction rate <= 0.25x recent peak
DECAY_LOOKBACK = 3               # "over the last 3 bars"
FWD_BARS = 12                    # 60-minute forward window
GATE0_KILL_BP = 35.0            # DEAD if mean gross/cluster < 35 bp
BASE_SYMBOL = "BTCUSDT"


# --------------------------------------------------------------------------- IO
def _read_zip_csv(path: pathlib.Path) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as zf:
        text = zf.read(zf.namelist()[0]).decode("utf-8")
    return [r for r in csv.reader(io.StringIO(text)) if r]


def _is_header(row: list[str]) -> bool:
    try:
        float(row[0]); return False
    except (ValueError, IndexError):
        return True


def _norm_ms(v: str) -> int:
    n = int(float(v))
    return n // 1000 if n > 10 ** 14 else n


def _month_of(t_ms: int) -> str:
    d = dt.datetime.fromtimestamp(t_ms / 1000, dt.timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def load_klines5m(sym: str, months: list[str]) -> dict[int, tuple[float, float, float]]:
    """open_time(ms) -> (open, close, quote_volume)."""
    out: dict[int, tuple[float, float, float]] = {}
    d = RAW / "klines5m" / sym
    for ym in months:
        p = d / f"{sym}-5m-{ym}.zip"
        if not (p.exists() and p.stat().st_size > 0):
            continue
        for row in _read_zip_csv(p):
            if _is_header(row):
                continue
            try:
                out[_norm_ms(row[0])] = (float(row[1]), float(row[4]), float(row[7]))
            except (ValueError, IndexError):
                pass
    return out


def load_metrics(sym: str, days: list[str]) -> dict[int, float]:
    """create_time(ms) -> sum_open_interest_value."""
    out: dict[int, float] = {}
    d = RAW / "metrics" / sym
    for day in days:
        p = d / f"{sym}-metrics-{day}.zip"
        if not (p.exists() and p.stat().st_size > 0):
            continue
        for row in _read_zip_csv(p):
            if row[0] == "create_time":
                continue
            try:
                t = int(dt.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                        .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
                out[t] = float(row[3])   # sum_open_interest_value
            except (ValueError, IndexError):
                pass
    return out


def _days_for(months: list[str]) -> list[str]:
    days = []
    for ym in months:
        y, m = int(ym[:4]), int(ym[5:7])
        d = dt.date(y, m, 1)
        while d.month == m:
            days.append(d.isoformat()); d += dt.timedelta(days=1)
    return days


# --------------------------------------------------------------------------- rolling helpers
def rolling_std_causal(x: np.ndarray, win: int) -> np.ndarray:
    """Std over the window of `win` values ENDING at t-1 (strictly causal, excludes t).

    NaNs in x break the estimate for any window containing them (returned as NaN), so a data gap
    never silently borrows across it. O(n) via prefix sums on a NaN-zeroed copy + a validity count.
    """
    n = x.size
    valid = np.isfinite(x).astype(np.float64)
    xz = np.where(np.isfinite(x), x, 0.0)
    cs = np.concatenate([[0.0], np.cumsum(xz)])
    cs2 = np.concatenate([[0.0], np.cumsum(xz * xz)])
    cv = np.concatenate([[0.0], np.cumsum(valid)])
    out = np.full(n, np.nan)
    if n <= win:
        return out
    t = np.arange(win, n)              # output index; window is [t-win, t-1]
    cnt = cv[t] - cv[t - win]
    s = cs[t] - cs[t - win]
    s2 = cs2[t] - cs2[t - win]
    with np.errstate(invalid="ignore", divide="ignore"):
        var = s2 / cnt - (s / cnt) ** 2
    good = (cnt >= win) & (var > 0)    # full window, no missing bar, positive variance
    res = np.full(t.size, np.nan)
    res[good] = np.sqrt(var[good])
    out[t] = res
    return out


# --------------------------------------------------------------------------- per-symbol panel
class Panel:
    """Merged, gap-aware 5-minute panel for one symbol on its fetch grid."""

    def __init__(self, sym: str, t, o, c, qv, oi):
        self.sym = sym
        self.t = t; self.o = o; self.c = c; self.qv = qv; self.oi = oi
        contig = np.concatenate([[False], np.diff(t) == BAR_MS])
        # bar log return, broken across gaps
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.log(c / np.roll(c, 1))
        r[~contig] = np.nan
        self.r = r
        # dOI, broken across gaps or missing OI
        doi = oi - np.roll(oi, 1)
        doi[~contig] = np.nan
        doi[~np.isfinite(oi) | ~np.isfinite(np.roll(oi, 1))] = np.nan
        self.doi = doi
        self.idx = {int(tt): i for i, tt in enumerate(t)}


def build_panel(sym: str, months: list[str]) -> Panel | None:
    k = load_klines5m(sym, months)
    if not k:
        return None
    md = load_metrics(sym, _days_for(months))
    ts = np.array(sorted(k), dtype=np.int64)
    o = np.array([k[t][0] for t in ts], dtype=np.float64)
    c = np.array([k[t][1] for t in ts], dtype=np.float64)
    qv = np.array([k[t][2] for t in ts], dtype=np.float64)
    oi = np.array([md.get(int(t), np.nan) for t in ts], dtype=np.float64)
    return Panel(sym, ts, o, c, qv, oi)


def monthly_beta(r_i: np.ndarray, r_b: np.ndarray, t: np.ndarray) -> dict[str, float]:
    """beta(i) per design month on the trailing-30d window ending at month-start (no forward data)."""
    betas: dict[str, float] = {}
    months = sorted({_month_of(int(x)) for x in t})
    for ym in months:
        y, m = int(ym[:4]), int(ym[5:7])
        ms = int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        lo = ms - BARS_30D * BAR_MS
        sel = (t >= lo) & (t < ms) & np.isfinite(r_i) & np.isfinite(r_b)
        if sel.sum() < BARS_24H:                 # need >=1 day of overlap to fit
            betas[ym] = np.nan; continue
        ri, rb = r_i[sel], r_b[sel]
        vb = np.var(rb)
        betas[ym] = float(np.cov(ri, rb)[0, 1] / vb) if vb > 0 else np.nan
    return betas


# --------------------------------------------------------------------------- gate 0
def run(entry_offset: int = 1, audit_only: bool = False) -> dict:
    uni = json.loads(UNIVERSE.read_text())
    membership = uni["membership"]                # ym -> [in-universe symbols]
    plan = uni["fetch_plan"]                        # sym -> [fetch months]
    union = uni["union"]

    # BTC factor
    btc = build_panel(BASE_SYMBOL, plan[BASE_SYMBOL])
    if btc is None:
        raise SystemExit("BTCUSDT klines absent -- fetch incomplete, cannot neutralise beta")
    btc_ret = {int(tt): btc.r[i] for i, tt in enumerate(btc.t)}
    btc_open = {int(tt): btc.o[i] for i, tt in enumerate(btc.t)}

    events = []          # (t_signal, sym, resid_fwd_bp)
    audit = {"entry_offset": entry_offset, "checked_events": 0,
             "entry_is_next_bar_open": True, "signal_no_future_index": True,
             "truncation_identical": True, "fwd_uses_only_future": True,
             "max_z_drift_rel": 0.0, "violations": [],
             "note": "truncation check recomputes the signal from arrays cut at bar j and compares "
                     "to the full-array value; a real lookahead shifts z by O(1)+, so the causality "
                     "tolerance is relative (rtol 1e-3). Sub-1e-4 drift is np.cumsum roundoff over "
                     "differing array lengths, not future information."}
    coverage = {"symbols_present": 0, "symbols_planned": len(union)}
    n_flush_raw = 0

    for sym in union:
        if sym == BASE_SYMBOL:
            pass  # BTC can be in-universe; residual ~0 so it won't flush, but process uniformly
        pan = build_panel(sym, plan[sym])
        if pan is None:
            continue
        coverage["symbols_present"] += 1
        t = pan.t
        # align BTC returns/opens to this symbol's grid
        r_b = np.array([btc_ret.get(int(x), np.nan) for x in t], dtype=np.float64)
        betas = monthly_beta(pan.r, r_b, t)
        beta_arr = np.array([betas.get(_month_of(int(x)), np.nan) for x in t], dtype=np.float64)
        r_resid = pan.r - beta_arr * r_b
        sd = rolling_std_causal(r_resid, BARS_30D)          # trailing-30d, ends at t-1
        with np.errstate(invalid="ignore"):
            z = r_resid / sd

        # trailing-24h quote volume (depth-free q denominator), causal through t
        qv = pan.qv.copy()
        qv[~np.isfinite(qv)] = 0.0
        cvq = np.concatenate([[0.0], np.cumsum(qv)])
        destr = np.where(pan.doi < 0, -pan.doi, 0.0)         # destruction rate (>=0)
        destr[~np.isfinite(pan.doi)] = np.nan

        n = t.size
        # candidate mask: cheap conditions first (z, dOI<0)
        cand = np.where(np.isfinite(z) & (z <= Z_THRESH) & np.isfinite(pan.doi) & (pan.doi < 0))[0]
        for j in cand:
            ym = _month_of(int(t[j]))
            if sym not in membership.get(ym, []):            # point-in-time universe membership
                continue
            if j < BARS_30D or j - DECAY_LOOKBACK < 0:
                continue
            # condition 3: q >= trailing-30d p90
            if j - BARS_24H < 0:
                continue
            tv24 = cvq[j + 1] - cvq[j + 1 - BARS_24H]         # last 288 bars incl j
            if tv24 <= 0:
                continue
            qj = abs(pan.doi[j]) / tv24
            # trailing-30d q window ending at j-1 (causal)
            lo = j - BARS_30D
            doi_w = pan.doi[lo:j]
            qv_end = cvq[lo + 1:j + 1] - cvq[lo + 1 - BARS_24H:j + 1 - BARS_24H] \
                if lo + 1 - BARS_24H >= 0 else None
            if qv_end is None:
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                q_w = np.abs(doi_w) / qv_end
            q_w = q_w[np.isfinite(q_w) & (qv_end > 0)]
            if q_w.size < BARS_24H:
                continue
            if qj < np.percentile(q_w, Q_PCT):
                continue
            # condition 4: destruction decayed to <=0.25x recent-3-bar peak
            peak3 = np.nanmax(destr[j - DECAY_LOOKBACK:j]) if np.any(
                np.isfinite(destr[j - DECAY_LOOKBACK:j])) else np.nan
            if not (np.isfinite(peak3) and peak3 > 0):
                continue
            if destr[j] > DECAY_FRAC * peak3:
                continue

            n_flush_raw += 1
            # forward return: entry OPEN of bar j+offset, exit +12 bars
            je = j + entry_offset
            jx = je + FWD_BARS
            if jx >= n:
                continue
            te, tx = int(t[je]), int(t[jx])
            if te - int(t[j]) != entry_offset * BAR_MS or tx - te != FWD_BARS * BAR_MS:
                continue                                      # require contiguous entry/exit bars
            if te not in btc_open or tx not in btc_open:
                continue
            beta = betas.get(ym, np.nan)
            if not np.isfinite(beta):
                continue
            fwd = math.log(pan.o[jx] / pan.o[je])
            bfwd = math.log(btc_open[tx] / btc_open[te])
            resid_fwd = (fwd - beta * bfwd) * 1e4             # bp
            events.append((int(t[j]), sym, resid_fwd))

            # ---- lookahead audit on a sample ----
            if audit["checked_events"] < 200:
                audit["checked_events"] += 1
                if te != int(t[j]) + entry_offset * BAR_MS:
                    audit["entry_is_next_bar_open"] = False
                    audit["violations"].append(f"{sym}@{t[j]}: entry not +{entry_offset} bar")
                # truncation check: recompute z(j), dOI(j), q(j) from arrays TRUNCATED at j
                ct = t[:j + 1]; cc = pan.c[:j + 1]; coi = pan.oi[:j + 1]
                contig = np.concatenate([[False], np.diff(ct) == BAR_MS])
                with np.errstate(divide="ignore", invalid="ignore"):
                    rr = np.log(cc / np.roll(cc, 1)); rr[~contig] = np.nan
                doi_t = coi - np.roll(coi, 1); doi_t[~contig] = np.nan
                rb_t = r_b[:j + 1]
                bt = monthly_beta(rr, rb_t, ct).get(ym, np.nan)
                rres = rr - bt * rb_t
                sd_t = rolling_std_causal(rres, BARS_30D)
                z_t = rres[j] / sd_t[j] if (np.isfinite(sd_t[j]) and sd_t[j] > 0) else np.nan
                if np.isfinite(z_t) and np.isfinite(z[j]):
                    drift = abs(z_t - z[j]) / (abs(z[j]) + 1e-9)
                    audit["max_z_drift_rel"] = max(audit["max_z_drift_rel"], float(drift))
                    if drift > 1e-3:                    # a real lookahead is O(1)+, not roundoff
                        audit["truncation_identical"] = False
                        audit["violations"].append(f"{sym}@{t[j]}: z leak rel={drift:.2e} "
                                                   f"({z_t} vs {z[j]})")
                else:
                    audit["truncation_identical"] = False
                    audit["violations"].append(f"{sym}@{t[j]}: z nan mismatch")
                if not (np.isfinite(doi_t[j]) and np.isfinite(pan.doi[j])
                        and abs(doi_t[j] - pan.doi[j]) <= 1e-6 * (abs(pan.doi[j]) + 1.0)):
                    audit["truncation_identical"] = False
                    audit["violations"].append(f"{sym}@{t[j]}: dOI truncation mismatch")
                if jx <= j or je <= j:
                    audit["fwd_uses_only_future"] = False

    # cluster: equal-weight events sharing a 5-min timestamp
    clusters: dict[int, list[float]] = {}
    for ts, sym, rf in events:
        clusters.setdefault(ts, []).append(rf)
    cl_rets = np.array([float(np.mean(v)) for v in clusters.values()], dtype=np.float64)
    n_cl = cl_rets.size

    res = {
        "gate": "GATE 0 -- gross-at-zero-cost census (design window, FLUSH leg, standalone, "
                "BTC-neutralised, 60-min, cluster-level)",
        "frozen_spec": "research/trading_bot/ORIGINAL_STRATEGY_SHORTLIST.md gate 0",
        "design_window": uni["design_window"],
        "q_denominator": "DEPTH-FREE FALLBACK: |dOI| / trailing-24h quote volume "
                         "(gate 0 needs no bookDepth; depth-q required before held-out run)",
        "entry_offset_bars": entry_offset,
        "coverage": coverage,
        "n_flush_events_raw": n_flush_raw,
        "n_flush_events_scored": len(events),
        "n_clusters": int(n_cl),
        "mean_gross_bp_per_cluster": float(np.mean(cl_rets)) if n_cl else None,
        "sd_bp": float(np.std(cl_rets, ddof=1)) if n_cl > 1 else None,
        "t_stat": (float(np.mean(cl_rets) / (np.std(cl_rets, ddof=1) / math.sqrt(n_cl)))
                   if n_cl > 1 and np.std(cl_rets, ddof=1) > 0 else None),
        "gate0_kill_threshold_bp": GATE0_KILL_BP,
        "verdict": None,
        "lookahead_audit": audit,
    }
    if n_cl and res["mean_gross_bp_per_cluster"] is not None:
        res["verdict"] = "DEAD" if res["mean_gross_bp_per_cluster"] < GATE0_KILL_BP else "SURVIVES_GATE0"
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry-offset", type=int, default=1,
                    help="entry bar offset from signal bar; 2 iff measured OI-latency > 60s")
    ap.add_argument("--audit-only", action="store_true")
    a = ap.parse_args()
    if not UNIVERSE.exists():
        print("universe.json absent -- run orphanflush_fetch.py first (or wait for the fetch).",
              file=sys.stderr)
        return 2
    res = run(entry_offset=a.entry_offset, audit_only=a.audit_only)
    RESULT.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in (
        "coverage", "n_flush_events_scored", "n_clusters", "mean_gross_bp_per_cluster",
        "t_stat", "gate0_kill_threshold_bp", "verdict")}, indent=1))
    print("lookahead_audit:", json.dumps(res["lookahead_audit"], indent=1))
    print(f"\nfull result -> {RESULT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
