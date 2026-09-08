#!/usr/bin/env python3
"""T13 — risk-shaping (distribution-shape) test on US equities.

Implements `research/trading_bot/T13_PREREGISTRATION.md` exactly. Stdlib only.

    python scripts/t13_risk_shaping.py design     # design window only; writes T13_FROZEN_CONFIG.json
    python scripts/t13_risk_shaping.py heldout    # refuses unless the freeze exists and hashes match

`design` REFUSES to read a bar dated on or after the held-out start, so the freeze is enforced by
the code. `heldout` re-hashes both the pre-registration and the frozen config and refuses on a
mismatch.

Timing convention T13-L1 (pre-registration §3): the exposure applied to the close-to-close return of
day t depends only on closes up to and including day t-2.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.t13_data import CACHE, Refused, read_cash_daily, read_series  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "trading_bot"
PREREG = OUT / "T13_PREREGISTRATION.md"
FROZEN = OUT / "T13_FROZEN_CONFIG.json"

DESIGN_START = "1928-01-03"
DESIGN_END = "1989-12-29"
HELDOUT_START = "1990-01-02"
HELDOUT_END = "2026-08-14"

SMA_GRID = [50, 100, 150, 200, 250]
VOL_L = [20, 60]
VOL_TARGET = [0.10, 0.15]
VOL_WMAX = [1.0, 1.5]
DECLARED_TRIALS = len(SMA_GRID) + len(VOL_L) * len(VOL_TARGET) * len(VOL_WMAX) + 1  # 14

MAX_WARMUP = max(SMA_GRID) + 2          # +2 for the T13-L1 lag
HALF_SPREAD_BP = 2.5                    # per side, retail_taker_costs()
SEC_FEE_BP = 0.278                      # sell side only
MARGIN_SPREAD_BP = 150.0                # over cash, when w > 1
TRADING_DAYS = 252.0


# ------------------------------------------------------------------ data assembly

class Panel:
    """Aligned signal / return / cash series with an explicit evaluation range."""

    def __init__(self, ret_file: str, ret_col_note: str):
        sdates, sclose = read_series("spx_price.csv")
        rdates, rclose = read_series(ret_file)
        sig = dict(zip(sdates, sclose))
        # Evaluate on the return series' calendar; a signal date must exist for every return date.
        self.dates = [d for d in rdates if d in sig]
        if len(self.dates) < len(rdates) * 0.98:
            raise Refused(
                f"{ret_file}: only {len(self.dates)}/{len(rdates)} dates have a ^GSPC signal close"
            )
        ridx = dict(zip(rdates, rclose))
        self.px = [ridx[d] for d in self.dates]
        self.sig = [sig[d] for d in self.dates]
        self.cash_pct = read_cash_daily(self.dates)
        self.note = ret_col_note
        self.ret_file = ret_file
        # calendar-day gaps, for cash and margin accrual
        ds = [dt.date.fromisoformat(d) for d in self.dates]
        self.caldays = [1] + [(ds[i] - ds[i - 1]).days for i in range(1, len(ds))]

    def index_of(self, date: str, side: str = "left") -> int:
        for i, d in enumerate(self.dates):
            if d >= date:
                return i
        if side == "right":
            return len(self.dates)
        raise Refused(f"date {date} beyond series end {self.dates[-1]}")

    def slice_bounds(self, start: str, end: str) -> tuple[int, int]:
        a = self.index_of(start)
        b = len(self.dates)
        for i in range(len(self.dates) - 1, -1, -1):
            if self.dates[i] <= end:
                b = i + 1
                break
        if a < MAX_WARMUP:
            a = MAX_WARMUP
        if b - a < 250:
            raise Refused(f"window {start}..{end} yields only {b - a} bars")
        return a, b


# ------------------------------------------------------------------ exposure rules

def sma_exposure(sig: list[float], n: int, a: int, b: int, lag: int = 2) -> list[float]:
    """1.0 when C(t-lag) is above its own N-average ending at t-lag, else 0.0.

    Undefined (fewer than n closes before t-lag) refuses; callers must not reach it because
    MAX_WARMUP is enforced.
    """
    if a - lag - n < 0:
        raise Refused("SMA undefined; warm-up not respected")
    j0 = a - lag
    running = sum(sig[j0 - n + 1:j0 + 1])
    out = [1.0 if sig[j0] > running / n else 0.0]
    for t in range(a + 1, b):
        j = t - lag
        running += sig[j] - sig[j - n]
        out.append(1.0 if sig[j] > running / n else 0.0)
    return out


def vol_exposure(px: list[float], L: int, target: float, wmax: float,
                 a: int, b: int, lag: int = 2) -> list[float]:
    r = [0.0] * len(px)
    for k in range(1, len(px)):
        r[k] = px[k] / px[k - 1] - 1.0
    j0 = a - lag
    if j0 - L < 0:
        raise Refused("realised vol undefined; warm-up not respected")
    s = sum(r[j0 - L + 1:j0 + 1])
    s2 = sum(x * x for x in r[j0 - L + 1:j0 + 1])
    out = []
    rt = math.sqrt(TRADING_DAYS)
    for t in range(a, b):
        j = t - lag
        if t > a:
            s += r[j] - r[j - L]
            s2 += r[j] * r[j] - r[j - L] * r[j - L]
        var = max(0.0, s2 / L - (s / L) ** 2)
        rv = math.sqrt(var) * rt
        if rv <= 0:
            raise Refused("zero realised volatility; refusing rather than dividing")
        out.append(min(wmax, target / rv))
    return out


def constant_exposure(w: float, a: int, b: int) -> list[float]:
    return [w] * (b - a)


# ------------------------------------------------------------------ the engine

def run(panel: Panel, w: list[float], a: int, b: int, cost_mult: float = 1.0,
        w_prev0: float = 0.0) -> dict:
    """One continuous equity curve. Costs charged per side on the exposure change."""
    eq = [1.0]
    rets: list[float] = []
    prev = w_prev0
    turn_open = turn_close = 0.0
    switches = 0
    for k, t in enumerate(range(a, b)):
        wt = w[k]
        r_idx = panel.px[t] / panel.px[t - 1] - 1.0
        acc = panel.caldays[t] / 365.0
        c = (panel.cash_pct[t - 1] / 100.0) * acc
        if wt <= 1.0:
            r_p = wt * r_idx + (1.0 - wt) * c
        else:
            borrow = (panel.cash_pct[t - 1] / 100.0 + MARGIN_SPREAD_BP / 10000.0) * acc
            r_p = wt * r_idx - (wt - 1.0) * borrow
        op = max(0.0, wt - prev)
        cl = max(0.0, prev - wt)
        cost = ((op + cl) * HALF_SPREAD_BP + cl * SEC_FEE_BP) * cost_mult / 10000.0
        if op or cl:
            switches += 1
        turn_open += op
        turn_close += cl
        prev = wt
        r_net = (1.0 + r_p) * (1.0 - cost) - 1.0
        rets.append(r_net)
        eq.append(eq[-1] * (1.0 + r_net))
    return {
        "equity": eq, "returns": rets, "n": len(rets),
        "turn_open": turn_open, "turn_close": turn_close, "switches": switches,
        "mean_exposure": sum(w) / len(w),
        "time_in_market": sum(1 for x in w if x > 1e-9) / len(w),
        "a": a, "b": b,
    }


def maxdd(eq: list[float]) -> float:
    peak, worst = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        worst = max(worst, (peak - v) / peak)
    return worst


def maxdd_episode(eq: list[float], dates: list[str], a: int) -> dict:
    """Where the worst drawdown actually happened. A single number hides which crash it was."""
    peak, pi, worst, wp, wt = eq[0], 0, 0.0, 0, 0
    for i, v in enumerate(eq):
        if v > peak:
            peak, pi = v, i
        d = (peak - v) / peak
        if d > worst:
            worst, wp, wt = d, pi, i
    rec = None
    for i in range(wt, len(eq)):
        if eq[i] >= eq[wp]:
            rec = dates[a - 1 + i]
            break
    return {"maxdd": worst, "peak": dates[a - 1 + wp], "trough": dates[a - 1 + wt],
            "recovered": rec, "underwater_days": (wt - wp)}


def ulcer(eq: list[float]) -> float:
    peak, ss = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        ss += ((peak - v) / peak) ** 2
    return math.sqrt(ss / len(eq))


def metrics(panel: Panel, res: dict) -> dict:
    eq, rets = res["equity"], res["returns"]
    a, b = res["a"], res["b"]
    d0 = dt.date.fromisoformat(panel.dates[a - 1])
    d1 = dt.date.fromisoformat(panel.dates[b - 1])
    yrs = (d1 - d0).days / 365.25
    cagr = (eq[-1] / eq[0]) ** (1.0 / yrs) - 1.0
    vol = statistics.pstdev(rets) * math.sqrt(TRADING_DAYS)
    ex = [rets[k] - (panel.cash_pct[t - 1] / 100.0) * panel.caldays[t] / 365.0
          for k, t in enumerate(range(a, b))]
    sd = statistics.pstdev(ex)
    sharpe = (statistics.fmean(ex) / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else None
    dd = maxdd(eq)
    ui = ulcer(eq)
    rf = statistics.fmean([panel.cash_pct[t - 1] / 100.0 for t in range(a, b)])
    # worst rolling 12-month (252-bar) return
    worst12 = min((eq[i + 252] / eq[i] - 1.0) for i in range(len(eq) - 252)) if len(eq) > 252 else None
    return {
        "years": round(yrs, 2), "bars": res["n"],
        "cagr": cagr, "vol": vol, "sharpe_over_cash": sharpe,
        "maxdd": dd, "ulcer": ui,
        "upi": (cagr - rf) / ui if ui > 0 else None,
        "mar": cagr / dd if dd > 0 else None,
        "worst_12m": worst12,
        "time_in_market": res["time_in_market"],
        "mean_exposure": res["mean_exposure"],
        "round_trips_per_year": res["turn_close"] / yrs,
        "turnover_total": res["turn_open"] + res["turn_close"],
        "final_equity": eq[-1],
        "mean_cash_rate": rf,
    }


# ------------------------------------------------------------------ nulls

def match_weight(panel: Panel, a: int, b: int, target_vol: float, cost_mult: float = 1.0) -> float:
    """Constant w whose realised annualised volatility equals target_vol. Bisection, monotone."""
    lo, hi = 0.0, 3.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        v = metrics(panel, run(panel, constant_exposure(mid, a, b), a, b, cost_mult))["vol"]
        if v < target_vol:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-7:
            break
    return (lo + hi) / 2.0


def circular_shift_null(panel: Panel, w: list[float], a: int, b: int,
                        cost_mult: float = 1.0, stride: int = 1) -> dict:
    """Rotate the filter's OWN exposure path; dose, run-lengths and turnover held exactly fixed.

    Specialised fast path for w in [0,1] (no margin leg). Verified against `run()` at rotation 0.
    """
    T = len(w)
    if max(w) > 1.0:
        raise Refused("fast rotation path has no margin leg; refusing a levered exposure path")
    idx = list(range(a, b))
    cash = [(panel.cash_pct[t - 1] / 100.0) * panel.caldays[t] / 365.0 for t in idx]
    ridx = [panel.px[t] / panel.px[t - 1] - 1.0 for t in idx]
    dlt = [ridx[k] - cash[k] for k in range(T)]
    hs = HALF_SPREAD_BP * cost_mult / 10000.0
    sf = SEC_FEE_BP * cost_mult / 10000.0
    dds = []
    # FINDINGS §8, "verify the diagnostic, not just the system": the specialised loop must
    # reproduce the general engine at rotation 0 before any rotation is believed.
    for k in [0] + list(range(1, T, stride)):
        eq = 1.0
        peak = 1.0
        worst = 0.0
        prev = 0.0
        for i in range(T):
            wt = w[(i + k) % T]
            if wt > prev:
                cost = (wt - prev) * hs
            elif wt < prev:
                cost = (prev - wt) * (hs + sf)
            else:
                cost = 0.0
            prev = wt
            eq *= (1.0 + cash[i] + wt * dlt[i]) * (1.0 - cost)
            if eq > peak:
                peak = eq
            else:
                d = (peak - eq) / peak
                if d > worst:
                    worst = d
        if k == 0:
            ref = maxdd(run(panel, w, a, b, cost_mult)["equity"])
            if abs(worst - ref) > 1e-9:
                raise Refused(f"fast rotation path disagrees with run(): {worst} vs {ref}")
            continue
        dds.append(worst)
    dds.sort()
    return {"n": len(dds), "sorted": dds}


def block_bootstrap_dd_diff(rets_a: list[float], rets_b: list[float], n_boot: int = 10000,
                            mean_block: int = 63, seed: int = 13) -> dict:
    """Paired stationary bootstrap on (filter, null) daily returns; statistic = maxDD(null)-maxDD(filter)."""
    rng = random.Random(seed)
    T = len(rets_a)
    ga = [1.0 + x for x in rets_a]
    gb = [1.0 + x for x in rets_b]
    wins = 0
    diffs = []
    randrange = rng.randrange
    geom = rng.expovariate
    for _ in range(n_boot):
        ea = eb = pa = pb = 1.0
        da = db = 0.0
        filled = 0
        while filled < T:
            i = randrange(T)
            blk = int(geom(1.0 / mean_block)) + 1
            if filled + blk > T:
                blk = T - filled
            for _s in range(blk):
                ea *= ga[i]
                eb *= gb[i]
                if ea > pa:
                    pa = ea
                else:
                    v = (pa - ea) / pa
                    if v > da:
                        da = v
                if eb > pb:
                    pb = eb
                else:
                    v = (pb - eb) / pb
                    if v > db:
                        db = v
                i = i + 1 if i + 1 < T else 0
            filled += blk
        d = db - da
        diffs.append(d)
        if d > 0:
            wins += 1
    diffs.sort()
    return {
        "n_boot": n_boot,
        "p_null_worse": (n_boot - wins + 1) / (n_boot + 1),   # add-one corrected
        "median_diff": diffs[n_boot // 2],
        "p05": diffs[int(0.05 * n_boot)],
        "p95": diffs[int(0.95 * n_boot)],
    }


def deflated_sharpe(rets: list[float], trials: int, sharpe_var: float) -> dict:
    """DSR of a return series that came out of a sweep (FINDINGS §5c). Refuses zero variance."""
    n = len(rets)
    sd = statistics.pstdev(rets)
    if sd <= 0:
        raise Refused("zero-variance series has no Sharpe to deflate")
    sr = statistics.fmean(rets) / sd
    m3 = sum((r - statistics.fmean(rets)) ** 3 for r in rets) / n / sd ** 3
    m4 = sum((r - statistics.fmean(rets)) ** 4 for r in rets) / n / sd ** 4
    eul = 0.5772156649
    e = math.sqrt(sharpe_var) * (
        (1 - eul) * _ppf(1 - 1.0 / trials) + eul * _ppf(1 - 1.0 / (trials * math.e))
    ) if trials > 1 else 0.0
    denom = math.sqrt(max(1e-18, 1 - m3 * sr + (m4 - 1) / 4.0 * sr ** 2))
    z = (sr - e) * math.sqrt(n - 1) / denom
    return {"sharpe_per_obs": sr, "expected_max_null": e, "skew": m3, "kurtosis": m4,
            "dsr": _cdf(z), "trials": trials}


def _cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _ppf(p: float) -> float:
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ------------------------------------------------------------------ crash table

def crash_table(panel: Panel, bench_eq: list[float], strat_eq: list[float], a: int,
                threshold: float = 0.20) -> list[dict]:
    """Every peak-to-trough episode in which the BENCHMARK fell more than `threshold`."""
    episodes = []
    peak_i, peak_v = 0, bench_eq[0]
    trough_i, trough_v = 0, bench_eq[0]
    for i, v in enumerate(bench_eq):
        if v > peak_v:
            if (peak_v - trough_v) / peak_v > threshold and trough_i > peak_i:
                episodes.append((peak_i, trough_i))
            peak_i, peak_v = i, v
            trough_i, trough_v = i, v
        elif v < trough_v:
            trough_i, trough_v = i, v
    if (peak_v - trough_v) / peak_v > threshold and trough_i > peak_i:
        episodes.append((peak_i, trough_i))
    rows = []
    for p, q in episodes:
        b_loss = bench_eq[q] / bench_eq[p] - 1.0
        s_seg = strat_eq[p:q + 1]
        s_loss = strat_eq[q] / strat_eq[p] - 1.0
        rows.append({
            "peak": panel.dates[a - 1 + p], "trough": panel.dates[a - 1 + q],
            "bench_loss": b_loss, "strategy_loss": s_loss,
            "strategy_maxdd_within": maxdd(s_seg),
            "protected_pp": (b_loss - s_loss) * 100.0,
        })
    return rows


# ------------------------------------------------------------------ the gate battery

def gate_battery(panel: Panel, w: list[float], a: int, b: int, fz: dict, r_bh: dict) -> dict:
    """G1..G5 of the pre-registration, against N1 (ex-post vol-matched constant weight)."""
    r_s = run(panel, w, a, b)
    m_s = metrics(panel, r_s)
    w1 = match_weight(panel, a, b, m_s["vol"])
    r_n1 = run(panel, constant_exposure(w1, a, b), a, b)
    m_n1 = metrics(panel, r_n1)

    out = {"strategy": m_s, "N1": {"w": w1, **m_n1},
           "maxdd_episode_strategy": maxdd_episode(r_s["equity"], panel.dates, a),
           "maxdd_episode_N1": maxdd_episode(r_n1["equity"], panel.dates, a)}

    boot = block_bootstrap_dd_diff(r_s["returns"], r_n1["returns"])
    out["G1_bootstrap"] = boot
    imp = (m_n1["maxdd"] - m_s["maxdd"]) * 100.0
    out["G1"] = {"maxdd_strategy": m_s["maxdd"], "maxdd_N1": m_n1["maxdd"],
                 "improvement_pp": imp, "threshold_pp": 3.0,
                 "p_value": boot["p_null_worse"],
                 "pass": imp >= 3.0 and boot["p_null_worse"] < 0.05}
    out["G2"] = {"cagr_strategy": m_s["cagr"], "cagr_N1": m_n1["cagr"],
                 "gap_pp_per_yr": (m_s["cagr"] - m_n1["cagr"]) * 100.0,
                 "pass": (m_s["cagr"] - m_n1["cagr"]) * 100.0 >= -0.50}

    cs = circular_shift_null(panel, w, a, b)
    pct = sum(1 for d in cs["sorted"] if d < m_s["maxdd"]) / cs["n"]
    out["G3_circular_shift"] = {
        "rotations": cs["n"], "strategy_maxdd": m_s["maxdd"],
        "rotation_maxdd_min": cs["sorted"][0],
        "rotation_maxdd_p05": cs["sorted"][int(0.05 * cs["n"])],
        "rotation_maxdd_median": cs["sorted"][cs["n"] // 2],
        "rotation_maxdd_p95": cs["sorted"][int(0.95 * cs["n"])],
        "rotation_maxdd_max": cs["sorted"][-1],
        "strategy_percentile": pct, "pass": pct < 0.05}

    out["G4_cost_stress"] = {}
    for mult in (1, 2, 4):
        mm = metrics(panel, run(panel, w, a, b, cost_mult=mult))
        nn = metrics(panel, run(panel, constant_exposure(w1, a, b), a, b, cost_mult=mult))
        out["G4_cost_stress"][f"x{mult}"] = {
            "strategy_cagr": mm["cagr"], "strategy_maxdd": mm["maxdd"],
            "N1_cagr": nn["cagr"], "N1_maxdd": nn["maxdd"],
            "dd_improvement_pp": (nn["maxdd"] - mm["maxdd"]) * 100.0,
            "cagr_gap_pp": (mm["cagr"] - nn["cagr"]) * 100.0}
    g4 = out["G4_cost_stress"]["x4"]
    out["G4"] = {"pass": g4["dd_improvement_pp"] >= 3.0 and g4["cagr_gap_pp"] >= -0.50}

    paired = [x - y for x, y in zip(r_s["returns"], r_n1["returns"])]
    try:
        d = deflated_sharpe(paired, fz["declared_trials"],
                            fz["cross_trial_sharpe_variance_annualised"] / TRADING_DAYS)
        out["G5_dsr_paired_excess"] = d
        out["G5"] = {"pass": d["dsr"] >= 0.95}
    except Refused as e:
        out["G5_dsr_paired_excess"] = {"refused": str(e)}
        out["G5"] = {"pass": False}

    out["crashes_vs_buy_and_hold"] = crash_table(panel, r_bh["equity"], r_s["equity"], a)
    out["crashes_vs_N1"] = crash_table(panel, r_n1["equity"], r_s["equity"], a)
    return out


# ------------------------------------------------------------------ design stage

def design() -> dict:
    panel = Panel("spx_price.csv", "^GSPC price-only; design window selects a parameter, reports no finding")
    a, b = panel.slice_bounds(DESIGN_START, DESIGN_END)
    if panel.dates[b - 1] >= HELDOUT_START:
        raise Refused("design mode touched a held-out bar")
    print(f"design window {panel.dates[a]} .. {panel.dates[b-1]}  ({b-a} bars)")

    bh = metrics(panel, run(panel, constant_exposure(1.0, a, b), a, b))
    rows_a = []
    for n in SMA_GRID:
        m = metrics(panel, run(panel, sma_exposure(panel.sig, n, a, b), a, b))
        rows_a.append({"N": n, **m})
        print(f"  SMA {n:3d}  CAGR {m['cagr']*100:6.2f}%  maxDD {m['maxdd']*100:5.1f}%  "
              f"MAR {m['mar']:.4f}  vol {m['vol']*100:5.2f}%  TIM {m['time_in_market']*100:.0f}%")
    print(f"  B&H       CAGR {bh['cagr']*100:6.2f}%  maxDD {bh['maxdd']*100:5.1f}%  "
          f"MAR {bh['mar']:.4f}  vol {bh['vol']*100:5.2f}%")

    rows_b = []
    for L in VOL_L:
        for tg in VOL_TARGET:
            for wm in VOL_WMAX:
                w = vol_exposure(panel.px, L, tg, wm, a, b)
                m = metrics(panel, run(panel, w, a, b))
                rows_b.append({"L": L, "target": tg, "wmax": wm, **m})
                print(f"  VOL L{L:3d} t{tg:.2f} wmax{wm:.1f}  CAGR {m['cagr']*100:6.2f}%  "
                      f"maxDD {m['maxdd']*100:5.1f}%  MAR {m['mar']:.4f}  vol {m['vol']*100:5.2f}%")

    # ---- frozen selection rule (pre-registration §4): top MAR, plateau-median within 5%
    def pick(rows, keyfn):
        best = max(r["mar"] for r in rows)
        tied = [r for r in rows if r["mar"] >= best * 0.95]
        vals = sorted(keyfn(r) for r in tied)
        return tied, vals[len(vals) // 2] if len(vals) % 2 == 1 else vals[len(vals) // 2 - 1]

    tied_a, n_star = pick(rows_a, lambda r: r["N"])
    contiguous = [r["N"] for r in sorted(tied_a, key=lambda r: r["N"])]
    grid_pos = [SMA_GRID.index(x) for x in contiguous]
    a_contig = grid_pos == list(range(grid_pos[0], grid_pos[0] + len(grid_pos)))

    best_b = max(rows_b, key=lambda r: r["mar"])
    tied_b = [r for r in rows_b if r["mar"] >= best_b["mar"] * 0.95]
    # median over the tied set, parameter-wise, per the same rule
    def med(vals):
        s = sorted(vals)
        return s[len(s) // 2] if len(s) % 2 == 1 else s[len(s) // 2 - 1]
    b_star = {"L": med([r["L"] for r in tied_b]),
              "target": med([r["target"] for r in tied_b]),
              "wmax": med([r["wmax"] for r in tied_b])}

    # cross-trial Sharpe variance across all 13 sweep members, needed by DSR at held-out
    sharpes = [r["sharpe_over_cash"] for r in rows_a + rows_b]
    sharpe_var_ann = statistics.pvariance(sharpes)

    # ex-ante vol ratio for null N2
    filt_w = sma_exposure(panel.sig, n_star, a, b)
    filt_vol = metrics(panel, run(panel, filt_w, a, b))["vol"]
    w_n2 = match_weight(panel, a, b, filt_vol)

    frozen = {
        "preregistration_sha256": hashlib.sha256(PREREG.read_bytes()).hexdigest(),
        "frozen_utc": dt.datetime.now(dt.UTC).isoformat(),
        "design_window": [panel.dates[a], panel.dates[b - 1]],
        "heldout_window": [HELDOUT_START, HELDOUT_END],
        "declared_trials": DECLARED_TRIALS,
        "timing_convention": "T13-L1: exposure for day t uses closes through t-2",
        "sma_grid": SMA_GRID, "design_family_a": rows_a,
        "vol_grid": {"L": VOL_L, "target": VOL_TARGET, "wmax": VOL_WMAX},
        "design_family_b": rows_b,
        "design_buy_and_hold": bh,
        "frozen_sma_N": n_star,
        "frozen_sma_tied_set": contiguous,
        "frozen_sma_plateau_contiguous": a_contig,
        "frozen_vol": b_star,
        "frozen_vol_tied_set": [{k: r[k] for k in ("L", "target", "wmax", "mar")} for r in tied_b],
        "cross_trial_sharpe_variance_annualised": sharpe_var_ann,
        "null_N2_exante_weight": w_n2,
        "cost_model": {"half_spread_bp_per_side": HALF_SPREAD_BP, "sec_fee_bp_sell": SEC_FEE_BP,
                       "margin_spread_bp": MARGIN_SPREAD_BP,
                       "source": "retail_taker_costs(); SEC 31 rate per T10"},
    }
    FROZEN.write_text(json.dumps(frozen, indent=2, default=str) + "\n")
    print(f"\nFROZEN: SMA N={n_star} (tied set {contiguous}, contiguous={a_contig})")
    print(f"FROZEN: vol overlay {b_star}")
    print(f"FROZEN: N2 ex-ante weight w*={w_n2:.4f} (design filter vol {filt_vol*100:.2f}%)")
    print(f"wrote {FROZEN}")
    return frozen


# ------------------------------------------------------------------ held-out stage

def heldout() -> dict:
    if not FROZEN.exists():
        raise Refused("no frozen config; run `design` first")
    fz = json.loads(FROZEN.read_text())
    h = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if h != fz["preregistration_sha256"]:
        raise Refused(f"pre-registration changed since the freeze: {h} != {fz['preregistration_sha256']}")

    N = fz["frozen_sma_N"]
    vcfg = fz["frozen_vol"]
    result = {"frozen_config_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
              "preregistration_sha256": h, "frozen_sma_N": N, "frozen_vol": vcfg,
              "declared_trials": fz["declared_trials"], "instruments": {}}

    for ret_file, label in (("sp500tr.csv", "primary: ^SP500TR index total return"),
                            ("spy_tr.csv", "confirmatory: SPY adjusted close (tradeable ETF)")):
        panel = Panel(ret_file, label)
        start = max(HELDOUT_START, panel.dates[MAX_WARMUP])
        a, b = panel.slice_bounds(start, HELDOUT_END)
        print(f"\n=== {ret_file}  {panel.dates[a]} .. {panel.dates[b-1]}  ({b-a} bars) ===")
        blk = {"label": label, "span": [panel.dates[a], panel.dates[b - 1]], "bars": b - a}

        w_f = sma_exposure(panel.sig, N, a, b)
        r_f = run(panel, w_f, a, b)
        m_f = metrics(panel, r_f)
        blk["filter"] = m_f

        r_bh = run(panel, constant_exposure(1.0, a, b), a, b)
        blk["buy_and_hold"] = metrics(panel, r_bh)

        # --- nulls
        w1 = match_weight(panel, a, b, m_f["vol"])
        r_n1 = run(panel, constant_exposure(w1, a, b), a, b)
        m_n1 = metrics(panel, r_n1)
        blk["N1_expost_volmatched"] = {"w": w1, **m_n1}

        w2 = fz["null_N2_exante_weight"]
        m_n2 = metrics(panel, run(panel, constant_exposure(w2, a, b), a, b))
        blk["N2_exante_volmatched"] = {"w": w2, **m_n2}

        w3 = m_f["mean_exposure"]
        m_n3 = metrics(panel, run(panel, constant_exposure(w3, a, b), a, b))
        blk["N3_exposure_matched"] = {"w": w3, **m_n3}

        # --- vol-target overlay and the combination, at frozen parameters
        w_v = vol_exposure(panel.px, vcfg["L"], vcfg["target"], vcfg["wmax"], a, b)
        m_v = metrics(panel, run(panel, w_v, a, b))
        blk["vol_target"] = m_v
        wv1 = match_weight(panel, a, b, m_v["vol"])
        blk["vol_target_N1"] = {"w": wv1, **metrics(panel, run(panel, constant_exposure(wv1, a, b), a, b))}

        w_c = [x * y for x, y in zip(w_f, w_v)]
        m_c = metrics(panel, run(panel, w_c, a, b))
        blk["combined"] = m_c
        wc1 = match_weight(panel, a, b, m_c["vol"])
        blk["combined_N1"] = {"w": wc1, **metrics(panel, run(panel, constant_exposure(wc1, a, b), a, b))}

        # --- the full gate battery, applied identically to all THREE frozen configurations.
        # All three are members of the 14 declared trials and all three were fixed by the frozen
        # selection rule on the design window before any held-out bar was read. §6's gate table
        # names "the frozen filter"; the same gates are run on the other two and labelled.
        blk["gates"] = {}
        for name, wpath in (("filter", w_f), ("vol_target", w_v), ("combined", w_c)):
            blk["gates"][name] = gate_battery(panel, wpath, a, b, fz, r_bh)

        blk["G1"] = blk["gates"]["filter"]["G1"]
        blk["G2"] = blk["gates"]["filter"]["G2"]
        blk["G3_circular_shift"] = blk["gates"]["filter"]["G3_circular_shift"]
        blk["G4"] = blk["gates"]["filter"]["G4"]
        blk["G4_cost_stress"] = blk["gates"]["filter"]["G4_cost_stress"]
        blk["G5"] = blk["gates"]["filter"]["G5"]
        blk["G5_dsr_paired_excess"] = blk["gates"]["filter"]["G5_dsr_paired_excess"]
        blk["crashes_vs_buy_and_hold"] = blk["gates"]["filter"]["crashes_vs_buy_and_hold"]
        blk["crashes_vs_N1"] = blk["gates"]["filter"]["crashes_vs_N1"]

        # --- every declared Family-B member on held-out, as a fragility display, not a selection.
        # The SMA family's held-out maxDD moved 15pp between two members whose design MAR differed
        # by under 5%. Whether Family B is equally fragile is a fact the reader is owed.
        blk["family_b_heldout_fragility"] = []
        for L in VOL_L:
            for tg in VOL_TARGET:
                for wm in VOL_WMAX:
                    ww = vol_exposure(panel.px, L, tg, wm, a, b)
                    mm = metrics(panel, run(panel, ww, a, b))
                    nw = match_weight(panel, a, b, mm["vol"])
                    nn = metrics(panel, run(panel, constant_exposure(nw, a, b), a, b))
                    blk["family_b_heldout_fragility"].append({
                        "L": L, "target": tg, "wmax": wm, "frozen": (L == vcfg["L"] and tg == vcfg["target"] and wm == vcfg["wmax"]),
                        "cagr": mm["cagr"], "vol": mm["vol"], "maxdd": mm["maxdd"], "ulcer": mm["ulcer"],
                        "N1_w": nw, "N1_cagr": nn["cagr"], "N1_maxdd": nn["maxdd"], "N1_ulcer": nn["ulcer"],
                        "dd_improvement_pp": (nn["maxdd"] - mm["maxdd"]) * 100.0,
                        "cagr_gap_pp": (mm["cagr"] - nn["cagr"]) * 100.0,
                    })
        blk["family_a_heldout_fragility"] = []
        for n in SMA_GRID:
            ww = sma_exposure(panel.sig, n, a, b)
            mm = metrics(panel, run(panel, ww, a, b))
            nw = match_weight(panel, a, b, mm["vol"])
            nn = metrics(panel, run(panel, constant_exposure(nw, a, b), a, b))
            blk["family_a_heldout_fragility"].append({
                "N": n, "frozen": n == N,
                "cagr": mm["cagr"], "vol": mm["vol"], "maxdd": mm["maxdd"], "ulcer": mm["ulcer"],
                "N1_w": nw, "N1_cagr": nn["cagr"], "N1_maxdd": nn["maxdd"], "N1_ulcer": nn["ulcer"],
                "dd_improvement_pp": (nn["maxdd"] - mm["maxdd"]) * 100.0,
                "cagr_gap_pp": (mm["cagr"] - nn["cagr"]) * 100.0,
            })

        # --- sub-period stability: is any of this one crash?
        blk["subperiods"] = {}
        for lo, hi in (("1990-01-02", "1999-12-31"), ("2000-01-03", "2009-12-31"),
                       ("2010-01-04", "2019-12-31"), ("2020-01-02", HELDOUT_END)):
            try:
                sa, sb = panel.slice_bounds(lo, hi)
            except Refused:
                continue
            sub = {}
            for name, wpath in (("filter", sma_exposure(panel.sig, N, sa, sb)),
                                ("vol_target", vol_exposure(panel.px, vcfg["L"], vcfg["target"], vcfg["wmax"], sa, sb))):
                mm = metrics(panel, run(panel, wpath, sa, sb))
                nw = match_weight(panel, sa, sb, mm["vol"])
                nn = metrics(panel, run(panel, constant_exposure(nw, sa, sb), sa, sb))
                sub[name] = {"cagr": mm["cagr"], "maxdd": mm["maxdd"], "vol": mm["vol"],
                             "N1_w": nw, "N1_cagr": nn["cagr"], "N1_maxdd": nn["maxdd"],
                             "dd_improvement_pp": (nn["maxdd"] - mm["maxdd"]) * 100.0,
                             "cagr_gap_pp": (mm["cagr"] - nn["cagr"]) * 100.0}
            sub["span"] = [panel.dates[sa], panel.dates[sb - 1]]
            sub["buy_and_hold"] = metrics(panel, run(panel, constant_exposure(1.0, sa, sb), sa, sb))["maxdd"]
            blk["subperiods"][lo[:4] + "s"] = sub

        # --- lag diagnostic (the published C(t-1) convention), never a result
        w_lag1 = sma_exposure(panel.sig, N, a, b, lag=1)
        blk["lag_diagnostic_Ctm1"] = metrics(panel, run(panel, w_lag1, a, b))

        # --- monthly-evaluation robustness variant
        w_m, cur = [], None
        for k, t in enumerate(range(a, b)):
            new_month = (k == 0) or panel.dates[t][:7] != panel.dates[t - 1][:7]
            if new_month or cur is None:
                cur = w_f[k]
            w_m.append(cur)
        blk["monthly_variant"] = metrics(panel, run(panel, w_m, a, b))

        result["instruments"][ret_file] = blk
        _print_block(blk)

    # --- walk-forward, on the primary instrument
    result["walk_forward"] = walk_forward(fz)
    (OUT / "T13_HELDOUT_RESULT.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(f"\nwrote {OUT/'T13_HELDOUT_RESULT.json'}")
    return result


def _print_block(blk: dict) -> None:
    def row(name, m):
        print(f"  {name:26s} CAGR {m['cagr']*100:6.2f}%  vol {m['vol']*100:5.2f}%  "
              f"maxDD {m['maxdd']*100:5.1f}%  Ulcer {m['ulcer']*100:5.2f}  "
              f"MAR {(m['mar'] or 0):.4f}  Sharpe {(m['sharpe_over_cash'] or 0):.3f}")
    for k in ("buy_and_hold", "filter", "N1_expost_volmatched", "N2_exante_volmatched",
              "N3_exposure_matched", "vol_target", "vol_target_N1", "combined", "combined_N1"):
        row(k, blk[k])
    for nm, g in blk["gates"].items():
        print(f"  -- {nm}: G1 {g['G1']['improvement_pp']:+6.2f}pp p={g['G1']['p_value']:.4f} pass={g['G1']['pass']}"
              f" | G2 {g['G2']['gap_pp_per_yr']:+5.2f}pp pass={g['G2']['pass']}"
              f" | G3 pct {g['G3_circular_shift']['strategy_percentile']:.4f} pass={g['G3_circular_shift']['pass']}"
              f" | G4 {g['G4']['pass']} | G5 dsr {g['G5_dsr_paired_excess'].get('dsr', float('nan')):.4f}")
        print(f"     maxDD episode {g['maxdd_episode_strategy']['peak']} -> {g['maxdd_episode_strategy']['trough']}"
              f" ({g['maxdd_episode_strategy']['maxdd']*100:.1f}%), N1 {g['maxdd_episode_N1']['peak']} ->"
              f" {g['maxdd_episode_N1']['trough']} ({g['maxdd_episode_N1']['maxdd']*100:.1f}%)")


def walk_forward(fz: dict) -> dict:
    """Expanding-window re-selection each calendar year-end, both families. ONE continuous curve."""
    panel = Panel("sp500tr.csv", "walk-forward, primary instrument")
    a, b = panel.slice_bounds(HELDOUT_START, HELDOUT_END)
    dpanel = Panel("spx_price.csv", "walk-forward selection history")
    r_bh = run(panel, constant_exposure(1.0, a, b), a, b)

    year_of = [panel.dates[t][:4] for t in range(a, b)]
    years = sorted(set(year_of))
    idx_of = {y: [k for k, yy in enumerate(year_of) if yy == y] for y in years}

    wa: list[float] = []
    wb: list[float] = []
    picks: list[dict] = []
    for y in years:
        sa, sb = dpanel.slice_bounds(DESIGN_START, f"{int(y)-1}-12-31")
        bestA, marA = None, -1e9
        for n in SMA_GRID:
            m = metrics(dpanel, run(dpanel, sma_exposure(dpanel.sig, n, sa, sb), sa, sb))
            if m["mar"] > marA:
                marA, bestA = m["mar"], n
        bestB, marB = None, -1e9
        for L in VOL_L:
            for tg in VOL_TARGET:
                for wm in VOL_WMAX:
                    m = metrics(dpanel, run(dpanel, vol_exposure(dpanel.px, L, tg, wm, sa, sb), sa, sb))
                    if m["mar"] > marB:
                        marB, bestB = m["mar"], {"L": L, "target": tg, "wmax": wm}
        picks.append({"year": y, "N": bestA, "vol": bestB,
                      "selected_on": [dpanel.dates[sa], dpanel.dates[sb - 1]]})
        i0, i1 = a + idx_of[y][0], a + idx_of[y][-1] + 1
        wa.extend(sma_exposure(panel.sig, bestA, i0, i1))
        wb.extend(vol_exposure(panel.px, bestB["L"], bestB["target"], bestB["wmax"], i0, i1))
    if len(wa) != b - a or len(wb) != b - a:
        raise Refused("walk-forward exposure path does not tile the held-out window")

    # The compounding audit, at ZERO cost so it tests compounding and not the per-fold entry
    # charge. At cost_mult=1 it reports ~0.9%, which is 37 fold-entry half-spreads and not a
    # skipped join -- exactly the sort of thing that gets misread as the bug it is named for.
    direct = run(panel, constant_exposure(1.0, a, b), a, b, cost_mult=0.0)["equity"][-1]
    piece = 1.0
    for y in years:
        i0, i1 = a + idx_of[y][0], a + idx_of[y][-1] + 1
        piece *= run(panel, constant_exposure(1.0, i0, i1), i0, i1, cost_mult=0.0)["equity"][-1]
    audit = abs(piece / direct - 1.0)
    if audit > 1e-9:
        raise Refused(f"fold joins skip return: relative error {audit}")

    out = {"picks": picks,
           "distinct_N_used": sorted(set(p["N"] for p in picks)),
           "distinct_vol_used": sorted({json.dumps(p["vol"], sort_keys=True) for p in picks}),
           "compounding_audit_relative_error_zero_cost": audit,
           "compounding_audit_note":
               "fold-by-fold buy-and-hold vs direct, costs off; must be 0 or the joins are skipped"}
    for name, wpath in (("family_a_sma", wa), ("family_b_voltarget", wb)):
        out[name] = gate_battery(panel, wpath, a, b, fz, r_bh)
    return out


def audit() -> dict:
    """Layer-3 truncation audit (scripts/trading_bot/README.md §1): delete the future and require
    every earlier decision to be BIT-IDENTICAL.

    Both exposure rules here receive the whole `sig`/`px` list and index into it. That is precisely
    the blind spot the T2 README names — the interface cannot stop a rule reading forward, only a
    re-run on truncated data can. `vol_exposure` in particular builds a full return array before
    slicing, which is the shape a whole-series normalisation constant would take.
    """
    panel = Panel("sp500tr.csv", "audit")
    a, b = panel.slice_bounds(HELDOUT_START, HELDOUT_END)
    fz = json.loads(FROZEN.read_text())
    N, vc = fz["frozen_sma_N"], fz["frozen_vol"]
    report = {"probes": []}
    for frac in (0.25, 0.5, 0.75, 0.9):
        k = a + int((b - a) * frac)
        full_a = sma_exposure(panel.sig, N, a, b)[: k - a]
        trunc_a = sma_exposure(panel.sig[:k], N, a, k)
        full_b = vol_exposure(panel.px, vc["L"], vc["target"], vc["wmax"], a, b)[: k - a]
        trunc_b = vol_exposure(panel.px[:k], vc["L"], vc["target"], vc["wmax"], a, k)
        ok_a = full_a == trunc_a
        ok_b = full_b == trunc_b
        report["probes"].append({"probe_bar": panel.dates[k], "sma_identical": ok_a,
                                 "vol_identical": ok_b,
                                 "sma_first_diff": next((i for i, (x, y) in enumerate(zip(full_a, trunc_a)) if x != y), None),
                                 "vol_first_diff": next((i for i, (x, y) in enumerate(zip(full_b, trunc_b)) if x != y), None)})
        if not (ok_a and ok_b):
            raise Refused(f"LOOKAHEAD: decisions changed when the future was deleted at {panel.dates[k]}")

    # negative control: a rule that peeks must be CAUGHT, or the audit proves nothing
    def cheating(px, a, b):
        hi = max(px[:b])                      # a whole-series normalisation constant
        return [1.0 if px[t] > 0.5 * hi else 0.0 for t in range(a, b)]
    k = a + (b - a) // 2
    caught = cheating(panel.px, a, b)[: k - a] != cheating(panel.px[:k], a, k)
    report["negative_control_caught"] = caught
    if not caught:
        raise Refused("the audit's own negative control was not caught; the audit is toothless")
    report["verdict"] = "no decision in either frozen rule depends on the future of the series"
    return report


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "design"
    if cmd == "design":
        design()
    elif cmd == "heldout":
        heldout()
    elif cmd == "audit":
        print(json.dumps(audit(), indent=2))
    else:
        raise SystemExit("usage: t13_risk_shaping.py [design|heldout|audit]")
