#!/usr/bin/env python3
"""X2_FLOWSTREAK slippage harness — reuses the frozen sweep book + free ±1% bookDepth to measure the
per-side fill cost and re-charge the held/design book, per the frozen pre-registration.

It does NOT re-derive the signal: it calls the exact `perpmicro_sweep`/`perpmicro_sweep2` primitives to
get X2_FLOWSTREAK's hourly weights, actual per-name turnover, and gross book return, then joins the free
Binance ±1% bookDepth band (via `orphanflush_depthq.load_bookdepth_band1_perbar`) and charges the
uniform-density walk model + taker fee on the REAL hourly turnover. The half-spread / adverse-selection
component is NOT in ±1% bookDepth (needs aggTrades / L2) — it is reported as 0 and flagged pending, so
this PoC is an honest LOWER BOUND on cost.

    python -m scripts.trading_bot.x2_slippage_harness --window design      # PoC on cached 2023-2024
    python -m scripts.trading_bot.x2_slippage_harness --window holdout     # after held-out depth download
"""
from __future__ import annotations

import datetime as dt
import json
import multiprocessing as mp
import pathlib
import sys
import time

import numpy as np

_TB = str(pathlib.Path(__file__).resolve().parent)
if _TB not in sys.path:
    sys.path.insert(0, _TB)               # so `import perpmicro_sweep` resolves inside the package dir
import perpmicro_sweep as ps               # noqa: E402
import perpmicro_sweep2 as s2              # noqa: E402
import orphanflush_depthq as dq            # noqa: E402
from scripts.trading_bot import x2_slippage_model as M   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "data" / "x2_slippage" / "result.json"
DESIGN = ("2023-01-01", "2024-04-01")     # s2.DESIGN
HOLDOUT = ("2025-01-01", "2026-08-16")
FROZEN_SIGN = 1.0                          # verified design sign for X2_FLOWSTREAK
HOUR_MS = 3_600_000
BAR_MS = 300_000
SAMPLE_EVERY = 11                          # sample ~1 in 11 days for the median-band estimate (10x faster)
TURNOVER_COVER = 0.98                      # load depth for the symbols carrying this much book turnover


def _days(a: str, b: str) -> list[str]:
    d, end, out = dt.date.fromisoformat(a), dt.date.fromisoformat(b), []
    while d < end:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _median_band_worker(args):
    """Per-symbol MEDIAN ±1% band notional (USD) over a SAMPLE of days — a stable capacity estimate of
    typical depth (the prereg's 'median band'), ~10x faster than a full per-hour series. Module-level so
    it pickles for the process pool. Returns (sym, median_band or nan, n_bars_seen)."""
    sym, days_sample = args
    try:
        per5 = dq.load_bookdepth_band1_perbar(sym, days_sample)
    except Exception:  # noqa: BLE001 — a missing/broken symbol contributes no depth
        return sym, float("nan"), 0
    if not per5:
        return sym, float("nan"), 0
    vals = np.fromiter(per5.values(), dtype=np.float64)
    vals = vals[np.isfinite(vals) & (vals > 0)]
    return sym, (float(np.median(vals)) if vals.size else float("nan")), int(vals.size)


def _load_median_bands(syms: np.ndarray, keep: list[int], window: tuple[str, str]) -> np.ndarray:
    """Median ±1% band per kept symbol, sampled + parallel, persisted so re-runs (and the held-out
    window later) are instant. Returns an (S,) array of USD notionals, NaN where no depth."""
    S = syms.size
    wtag = f"{window[0]}_{window[1]}"
    cache = OUT.parent / f"band_med_{wtag}.json"
    stored = {}
    if cache.exists():
        try:
            stored = json.loads(cache.read_text())
        except (OSError, ValueError):
            stored = {}
    days_all = _days(*window)
    sample = days_all[::SAMPLE_EVERY] or days_all
    todo = [(str(syms[k]), sample) for k in keep if str(syms[k]) not in stored]
    if todo:
        print(f"  loading median band for {len(todo)} symbols ({len(sample)} sampled days each)…",
              flush=True)
        procs = max(1, min(6, (mp.cpu_count() or 2) - 1))
        t0 = time.time()
        with mp.Pool(procs) as pool:
            for i, (sym, med, nb) in enumerate(pool.imap_unordered(_median_band_worker, todo), 1):
                stored[sym] = med
                if i % 10 == 0 or i == len(todo):
                    print(f"    {i}/{len(todo)}  {sym}={med:.0f}  ({time.time()-t0:.0f}s)", flush=True)
        cache.write_text(json.dumps(stored))
    band = np.full(S, np.nan)
    for k in keep:
        v = stored.get(str(syms[k]))
        if v is not None and np.isfinite(v) and v > 0:
            band[k] = v
    return band


def build_book(window: tuple[str, str]):
    pan = np.load(s2.PANEL_X, allow_pickle=True)
    p = s2.build2(pan, has_metrics=False, top_n=50, min_names=25)
    entry = [f for f in s2.catalogue2(p) if f[0] == "X2_FLOWSTREAK"][0]
    name, x, H, scheme, tmask, cls, desc = entry
    x = np.ascontiguousarray(x.astype(np.float32))
    w = ps.weights_from_signal(x, p.univ, scheme)               # (S, T) target ±0.05, gross 1
    hold = ps.hold_from_weights(w, H)                            # (S, T) actual 24h-overlap position
    pnl, pf, dh = ps.evaluate(x, p, H, scheme, None)            # per-hour price / funding / turnover
    gross_h = FROZEN_SIGN * (pnl + pf)                          # (T,) book gross return per hour
    syms = np.array([str(s) for s in (p.sym if hasattr(p, "sym") else pan["symbols"])])
    mask = ps.window_mask(p.t, *window)
    return p, w, hold, gross_h, syms, mask


def run(window_name: str, depth_window_name: str | None = None) -> dict:
    window = DESIGN if window_name == "design" else HOLDOUT
    is_poc = window_name == "design"
    dwn = depth_window_name or window_name          # depth may come from a different window (proxy)
    depth_window = DESIGN if dwn == "design" else HOLDOUT
    depth_is_proxy = dwn != window_name
    p, w, hold, gross_h, syms, mask = build_book(window)
    t = p.t
    S, T = w.shape

    # per-name hourly turnover |Δhold| (charge slippage on what is actually traded, not the target)
    dhold = np.zeros_like(hold)
    dhold[:, 1:] = np.abs(hold[:, 1:] - hold[:, :-1])
    idx = np.where(mask)[0]
    turn_in = dhold[:, idx]                                     # (S, n_hours) turnover in-window
    total_turn = float(turn_in.sum())

    # select the symbols carrying ~98% of book turnover and load ONE median +-1% band each (fast).
    per_sym_turn = turn_in.sum(axis=1)
    order = np.argsort(per_sym_turn)[::-1]
    cum = np.cumsum(per_sym_turn[order]) / (total_turn or 1)
    keep = order[:int(np.searchsorted(cum, TURNOVER_COVER) + 1)]
    keep = [int(k) for k in keep if per_sym_turn[k] > 0]
    band_med = _load_median_bands(syms, keep, depth_window)     # (S,) scalar per symbol, NaN if none
    covered = int(np.isfinite(band_med[keep]).sum())

    gross_d = _to_daily(gross_h[idx])                           # daily book gross return in-window
    b = band_med[:, None]                                       # (S,1) broadcast over hours

    capacity = []
    for aum in M.AUM_GRID:
        with np.errstate(divide="ignore", invalid="ignore"):
            frac = (aum * turn_in) / b                          # traded / +-1% band, per name-hour
        slip_bp = np.where(np.isfinite(frac), np.where(frac >= 1.0, 100.0, 100.0 * 0.5 * frac), 100.0)
        slip_bp = np.where(turn_in > 0, slip_bp, 0.0)           # no trade -> no slippage
        cost_bp = slip_bp + M.TAKER_FEE_BP                      # half-spread pending aggTrades (=0 here)
        cost_frac_h = (turn_in * cost_bp).sum(axis=0) / 1e4     # book cost fraction per hour
        net_d = _to_daily(gross_h[idx] - cost_frac_h)
        mean, tstat, n = _mean_t(net_d)
        twcost = float((turn_in * cost_bp).sum() / total_turn) if total_turn > 0 else None
        capacity.append({"aum_usd": aum, "cost_bp_per_side": round(twcost, 2) if twcost else None,
                         "net_mean_R": round(mean, 5), "t": round(tstat, 2), "n_days": n})

    verdict, max_aum, note = M.verdict(capacity, corr_l5_l6=None, is_poc=is_poc)
    # integrity guard: a proxy depth window that fails to cover the book cannot yield a real verdict —
    # uncovered (new-listing) names get the 100 bp cap, which fabricates cost. Do NOT call that KILL.
    cov_frac = _cov_frac(turn_in, b)
    if depth_is_proxy and cov_frac < 0.90:
        verdict = "PENDING_DATA"
        max_aum = None
        note = (f"depth is a design-era proxy covering only {cov_frac*100:.0f}% of holdout turnover "
                "(2025-26 has new listings absent from 2023-24 depth; uncovered names hit the 100 bp "
                "cap and fabricate cost). Download held-out bookDepth for the real verdict.")
    # representative slippage magnitude at the target AUM (turnover-weighted, excl. fee)
    slip_at_target = _tw_slip(turn_in, b, M.AUM_TARGET, total_turn)

    gmean, gt, gn = _mean_t(gross_d)
    result = {
        "instrument": "X2_FLOWSTREAK", "window": window_name, "depth_window": dwn,
        "depth_is_proxy": depth_is_proxy,
        "generated_unix": int(time.time()), "verdict": verdict,
        "max_tradeable_aum_usd": max_aum, "note": note,
        "n_rebalances": int(mask.sum()), "n_days": gn,
        "n_names_median": int(np.median((w[:, idx] != 0).sum(axis=0))),
        "gross_mean_R_daily": round(gmean, 5), "gross_t": round(gt, 2),
        "breakeven_bp": M.BREAKEVEN_BP,
        "capacity_curve": capacity,
        "per_side_cost_components": {"slippage_bp": round(slip_at_target, 2),
                                     "fee_bp": M.TAKER_FEE_BP, "half_spread_bp": None},
        "coverage": {"names_with_depth": covered, "names_active": len(keep),
                     "frac_rebalance_notional_covered": round(_cov_frac(turn_in, b), 4)},
        "caveats": ["half-spread/adverse-selection NOT in +-1% bookDepth -> reported 0 (LOWER BOUND); "
                    "needs aggTrades/L2"]
        + (["design-window PoC is a method check, not the frozen verdict"] if is_poc else [])
        + (["depth is a DESIGN-era proxy (held-out bookDepth not yet downloaded); depth is stable for "
            "the majors carrying most turnover, but the rigorous run uses held-out depth"]
           if depth_is_proxy else []),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    return result


def _to_daily(x: np.ndarray) -> np.ndarray:
    n = (x.size // 24) * 24
    return x[:n].reshape(-1, 24).sum(axis=1) if n else np.array([])


def _mean_t(a: np.ndarray):
    n = a.size
    if n == 0:
        return 0.0, 0.0, 0
    m = float(a.mean())
    if n < 2:
        return m, 0.0, n
    sd = float(a.std(ddof=1))
    se = sd / np.sqrt(n) if sd > 0 else 0.0
    return m, (m / se if se else 0.0), n


def _tw_slip(turn, b, aum, total):
    """Turnover-weighted mean modeled slippage (bp, excl. fee) at `aum`. `b` is the (S,1) median band."""
    if total <= 0:
        return 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = aum * turn / b
    slip = np.where(np.isfinite(frac), np.where(frac >= 1, 100.0, 50.0 * frac), 100.0)
    slip = np.where(turn > 0, slip, 0.0)
    return float((turn * slip).sum() / total)


def _cov_frac(turn, b):
    """Fraction of book turnover carried by names that HAVE a depth estimate. `b` is (S,1)."""
    tot = float(turn.sum())
    if tot <= 0:
        return 0.0
    finite_rows = np.isfinite(b[:, 0])
    return float(turn[finite_rows].sum()) / tot


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    window = "design"
    depth = None
    if "--window" in argv:
        window = argv[argv.index("--window") + 1]
    if "--depth" in argv:
        depth = argv[argv.index("--depth") + 1]
    print(f"x2 slippage harness: window={window} depth={depth or window} …", flush=True)
    r = run(window, depth)
    print(json.dumps({k: r[k] for k in ("instrument", "window", "verdict", "max_tradeable_aum_usd",
                                        "n_rebalances", "coverage")}, indent=2), flush=True)
    for c in r["capacity_curve"]:
        print(f"  ${c['aum_usd']:>9,}  cost/side {str(c['cost_bp_per_side']):>6} bp  "
              f"net {c['net_mean_R']:+.5f}  t {c['t']:+.2f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
