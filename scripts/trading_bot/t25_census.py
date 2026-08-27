#!/usr/bin/env python3
"""T25 — the mandatory power census for the cross-venue perp funding differential.

Judged against research/trading_bot/T25_POWER_GATE.md, whose sha256 is asserted here.
Computes DISPERSION ONLY on the held-out window: no held-out mean is computed, printed or
stored anywhere in this file, so running it does not spend the held-out window.

Usage: python3 scripts/trading_bot/t25_census.py
"""
from __future__ import annotations

import bisect
import collections
import csv
import datetime as dt
import hashlib
import json
import math
import os
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(REPO, "research", "data", "t25_cache")
HL_DIR = os.path.join(CACHE, "hl")
PANEL = os.path.join(REPO, "research", "data", "t23_cache", "panel")
TB = os.path.join(REPO, "research", "data", "t13_cache", "cash.csv")
GATE = os.path.join(REPO, "research", "trading_bot", "T25_POWER_GATE.md")
GATE_SHA = os.path.join(REPO, "research", "trading_bot", "T25_POWER_GATE.sha256")
OUT = os.path.join(REPO, "research", "trading_bot", "T25_POWER_CENSUS.json")

Z = 2.80  # 1.96 + 0.84 : two-sided 5 %, 80 % power.  Gate §2.
TOPN_GRID = (3, 5, 10, 20)  # Gate §2a
ADV_MIN = 20e6  # Gate §2b, T21 §3d's own $20 M/day threshold, applied point-in-time
E_CLAIM = 1.07  # Gate §4, pp/yr
E_MAX = 11.55  # Gate §4, pp/yr
BAR = 1.00  # Gate §6, pp/yr
FRICTION_PP = 1.591  # Gate §5, pp/yr
CAPITAL_MULT = 2.0  # Gate §5

WINDOWS = {  # Gate §3
    "DESIGN": ("2024-10", "2026-07"),
    "HELDOUT": ("2023-06", "2024-09"),
    "FULL": ("2023-06", "2026-07"),
}


def month_of(ms: int) -> str:
    d = dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def month_days(m: str) -> int:
    y, mo = int(m[:4]), int(m[5:])
    nxt = dt.date(y + (mo == 12), (mo % 12) + 1, 1)
    return (nxt - dt.date(y, mo, 1)).days


def months_between(lo: str, hi: str) -> list[str]:
    out, y, mo = [], int(lo[:4]), int(lo[5:])
    while f"{y:04d}-{mo:02d}" <= hi:
        out.append(f"{y:04d}-{mo:02d}")
        mo += 1
        if mo == 13:
            y, mo = y + 1, 1
    return out


def prev_month(m: str) -> str:
    y, mo = int(m[:4]), int(m[5:])
    return f"{y-1:04d}-12" if mo == 1 else f"{y:04d}-{mo-1:02d}"


def assert_gate() -> str:
    have = hashlib.sha256(open(GATE, "rb").read()).hexdigest()
    want = open(GATE_SHA).read().split()[0]
    if have != want:
        raise SystemExit(f"GATE HASH MISMATCH: {have} != {want}")
    return have


def load_hl() -> dict[str, dict[str, float]]:
    """coin -> month -> annualised realised funding, pp/yr (positive: longs pay shorts)."""
    out: dict[str, dict[str, float]] = {}
    for fn in sorted(os.listdir(HL_DIR)):
        if not fn.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(HL_DIR, fn)))
        acc: dict[str, float] = collections.defaultdict(float)
        cnt: dict[str, int] = collections.Counter()
        for t, rate, _premium in rec["prints"]:
            m = month_of(t)
            acc[m] += float(rate)
            cnt[m] += 1
        # require >= 90 % of the month's hourly prints before the month counts
        out[rec["coin"]] = {
            m: v * 365.25 / month_days(m) * 100.0
            for m, v in acc.items()
            if cnt[m] >= 0.90 * 24 * month_days(m)
        }
    return out


def load_binance(symbols: set[str]) -> dict[str, dict[str, float]]:
    acc: dict[str, dict[str, float]] = collections.defaultdict(lambda: collections.defaultdict(float))
    cnt: dict[str, dict[str, int]] = collections.defaultdict(collections.Counter)
    with open(os.path.join(PANEL, "funding.csv")) as fh:
        rd = csv.reader(fh)
        next(rd)
        for sym, t, ivl, rate in rd:
            if sym not in symbols:
                continue
            m = month_of(int(t))
            acc[sym][m] += float(rate)
            cnt[sym][m] += 1
    out: dict[str, dict[str, float]] = {}
    for sym, mm in acc.items():
        out[sym] = {
            m: v * 365.25 / month_days(m) * 100.0
            for m, v in mm.items()
            # 8h cadence -> 3/day; accept >= 80 % of that (4h symbols exceed it trivially)
            if cnt[sym][m] >= 0.80 * 3 * month_days(m)
        }
    return out


def load_adv(symbols: set[str]) -> dict[str, list[tuple[int, float]]]:
    """symbol -> sorted [(day_ms, quote_volume)] for the point-in-time trailing screen."""
    out: dict[str, list[tuple[int, float]]] = collections.defaultdict(list)
    with open(os.path.join(PANEL, "perp_daily.csv")) as fh:
        rd = csv.reader(fh)
        next(rd)
        for sym, day, _close, qv, _tr in rd:
            if sym in symbols:
                out[sym].append((int(day), float(qv)))
    for sym in out:
        out[sym].sort()
    return out


def trailing_adv(series: list[tuple[int, float]], asof_ms: int) -> float:
    lo = asof_ms - 30 * 86400_000
    i = bisect.bisect_right(series, (asof_ms, float("inf")))
    j = bisect.bisect_left(series, (lo, -1.0))
    win = series[j:i]
    return (sum(v for _, v in win) / len(win)) if len(win) >= 20 else 0.0


def month_end_ms(m: str) -> int:
    y, mo = int(m[:4]), int(m[5:])
    nxt = dt.date(y + (mo == 12), (mo % 12) + 1, 1)
    return int(dt.datetime(nxt.year, nxt.month, nxt.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def tbill_by_month() -> dict[str, float]:
    per: dict[str, list[float]] = collections.defaultdict(list)
    with open(TB) as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            if row["date"] >= "2023-01-01":
                per[row["date"][:7]].append(float(row["annual_pct"]))
    return {m: sum(v) / len(v) for m, v in per.items()}


def spearman(xs: list[float], ys: list[float]) -> float:
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def main() -> int:
    gate_sha = assert_gate()
    uni = json.load(open(os.path.join(CACHE, "universe.json")))
    rows = uni["download_universe"]
    coin2sym = {r["coin"]: r["binance"] for r in rows}
    delisted = {r["coin"] for r in rows if r["hl_delisted"]}

    hl = load_hl()
    have_hl = {c for c in hl if hl[c]}
    syms = {coin2sym[c] for c in hl}
    bn = load_binance(syms)
    adv = load_adv(syms)
    tb = tbill_by_month()

    full_months = months_between(*WINDOWS["FULL"])

    # ---- eligibility, strictly point-in-time (gate §2b) -------------------------------
    eligible: dict[str, list[str]] = {}
    for m in full_months:
        pm = prev_month(m)
        asof = month_end_ms(pm)
        ok = []
        for coin, sym in coin2sym.items():
            if coin not in hl:
                continue
            if pm not in hl[coin] or pm not in bn.get(sym, {}):
                continue
            if m not in hl[coin] or m not in bn.get(sym, {}):
                continue  # the month must be tradeable to both venues to be in the book
            if trailing_adv(adv.get(sym, []), asof) < ADV_MIN:
                continue
            ok.append(coin)
        eligible[m] = ok

    # A coin selected at the end of month t-1 whose funding series then STOPS is dropped by
    # `eligible` rather than charged.  Count that so the size of the omission is visible; the
    # test (not the census) must charge a delisting tail for it, as T23 did.
    dropped = 0
    selectable = 0
    for m in full_months:
        pm = prev_month(m)
        asof = month_end_ms(pm)
        for coin, sym in coin2sym.items():
            if coin not in hl or pm not in hl[coin] or pm not in bn.get(sym, {}):
                continue
            if trailing_adv(adv.get(sym, []), asof) < ADV_MIN:
                continue
            selectable += 1
            if m not in hl[coin] or m not in bn.get(sym, {}):
                dropped += 1

    # ---- the book ---------------------------------------------------------------------
    def book_series(months: list[str], topn: int) -> list[float]:
        """Monthly EXCESS return of the equal-weight top-N differential book, in %/month."""
        out = []
        for m in months:
            names = eligible.get(m, [])
            if len(names) < topn:
                continue
            pm = prev_month(m)
            scored = []
            for c in names:
                d_tr = hl[c][pm] - bn[coin2sym[c]][pm]
                d_rz = hl[c][m] - bn[coin2sym[c]][m]
                scored.append((abs(d_tr), math.copysign(1.0, d_tr), d_rz, c))
            scored.sort(reverse=True)
            picked = scored[:topn]
            gross_ann = sum(s * d for _, s, d, _ in picked) / len(picked)  # pp/yr on notional
            net_ann = (gross_ann - FRICTION_PP) / CAPITAL_MULT
            excess_ann = net_ann - tb.get(m, 3.84)
            out.append(excess_ann * month_days(m) / 365.25)
        return out

    census: dict = {
        "gate_file": "research/trading_bot/T25_POWER_GATE.md",
        "gate_sha256": gate_sha,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "z": Z,
        "E_claim_pp": E_CLAIM,
        "E_max_pp": E_MAX,
        "bar_pp": BAR,
        "download_universe_n": len(rows),
        "hl_coins_with_history": len(have_hl),
        "survivorship_note": {
            "selectable_coin_months": selectable,
            "dropped_because_a_venue_stopped_publishing_next_month": dropped,
            "share": round(dropped / selectable, 4) if selectable else None,
            "consequence": "the census drops these; a TEST must charge a delisting tail (T23 §5)",
        },
    }

    # ---- G0 : data census --------------------------------------------------------------
    hl_present = sum(1 for m in full_months for c in coin2sym if m in hl.get(c, {}))
    bn_present = sum(1 for m in full_months for c in coin2sym if m in bn.get(coin2sym[c], {}))
    both = sum(
        1
        for m in full_months
        for c in coin2sym
        if m in hl.get(c, {}) and m in bn.get(coin2sym[c], {})
    )
    census["G0"] = {
        "coin_months_binance_present": bn_present,
        "coin_months_hl_present": hl_present,
        "coin_months_both": both,
        "share_hl_of_binance": round(hl_present / bn_present, 4) if bn_present else 0.0,
        "threshold": 0.95,
        "pass": bool(bn_present and hl_present / bn_present >= 0.95),
    }

    # ---- G0b : survivorship proof -------------------------------------------------------
    dead_with_hist = sorted(c for c in delisted if hl.get(c))
    census["G0b"] = {
        "hl_delisted_in_download_universe": len(delisted),
        "hl_delisted_returning_history": len(dead_with_hist),
        "examples": dead_with_hist[:12],
        "threshold": 5,
        "pass": len(dead_with_hist) >= 5,
    }

    # ---- G3 : month counts ---------------------------------------------------------------
    counts = {
        w: sum(1 for m in months_between(*WINDOWS[w]) if len(eligible.get(m, [])) >= 20)
        for w in WINDOWS
    }
    census["G3"] = {
        "months_with_ge20_eligible": counts,
        "eligible_names_by_month": {m: len(eligible[m]) for m in full_months},
        "threshold": {"DESIGN": 18, "HELDOUT": 12},
        "pass": counts["DESIGN"] >= 18 and counts["HELDOUT"] >= 12,
    }

    # ---- dispersion, per window, per topN ---------------------------------------------
    disp: dict = {}
    for w, (lo, hi) in WINDOWS.items():
        months = months_between(lo, hi)
        per_n = {}
        for n in TOPN_GRID:
            s = book_series(months, n)
            if len(s) < 6:
                continue
            sd_ann = statistics.stdev(s) * math.sqrt(12)
            years = sum(month_days(m) for m in months) / 365.25
            per_n[str(n)] = {
                "n_months_used": len(s),
                "sd_annual_pct": round(sd_ann, 4),
                "years": round(years, 4),
                "MDE_annual_pp": round(Z * sd_ann / math.sqrt(years), 4),
            }
        disp[w] = per_n
    census["dispersion"] = disp

    def smallest(w: str) -> tuple[str, dict]:
        per_n = disp[w]
        k = min(per_n, key=lambda k: per_n[k]["MDE_annual_pp"])
        return k, per_n[k]

    for gname, w, thr, blocking in (
        ("G1", "HELDOUT", E_CLAIM, True),
        ("G1b", "FULL", E_CLAIM, True),
        ("G1max", "FULL", E_MAX, False),
        ("G2", "FULL", E_CLAIM - BAR, False),
    ):
        k, d = smallest(w)
        census[gname] = {
            "window": w,
            "topN_chosen_most_favourable": int(k),
            "sd_annual_pct": d["sd_annual_pct"],
            "years": d["years"],
            "MDE_annual_pp": d["MDE_annual_pp"],
            "threshold_pp": round(thr, 4),
            "ratio_MDE_over_threshold": round(d["MDE_annual_pp"] / thr, 3) if thr > 0 else None,
            "blocking": blocking,
            "pass": d["MDE_annual_pp"] <= thr,
        }

    # ---- G4 : capacity -------------------------------------------------------------------
    dep = json.load(open(os.path.join(CACHE, "hl_depth.json")))["depth20_usd"]
    med = statistics.median(dep)
    census["G4"] = {
        "hl_top20_depth_thinner_side_usd_median": round(med),
        "hl_top20_depth_p25": round(sorted(dep)[len(dep) // 4]),
        "per_name_notional_at_10pct_of_depth_usd": round(0.10 * med),
        "implied_book_usd": {str(n): round(n * 0.10 * med) for n in TOPN_GRID},
        "note": "one leg only; the Binance leg is deeper, the Hyperliquid leg binds",
    }

    # ---- diagnostics : persistence, DESIGN window only (gate §8) --------------------------
    dm = months_between(*WINDOWS["DESIGN"])
    xs, ys = [], []
    for m in dm:
        pm = prev_month(m)
        for c in eligible.get(m, []):
            xs.append(hl[c][pm] - bn[coin2sym[c]][pm])
            ys.append(hl[c][m] - bn[coin2sym[c]][m])
    census["diagnostic_persistence_DESIGN_ONLY"] = {
        "n_coin_months": len(xs),
        "spearman_trailing_vs_next_month_differential": round(spearman(xs, ys), 4) if xs else None,
        "label": "DESIGN WINDOW ONLY. Gate §8 forbids reading this as evidence for the candidate.",
    }
    if xs:
        allm = sorted(abs(v) for v in ys)
        census["diagnostic_realised_differential_DESIGN_ONLY"] = {
            "abs_differential_pp_per_yr": {
                "p50": round(allm[len(allm) // 2], 3),
                "p75": round(allm[int(0.75 * len(allm))], 3),
                "p90": round(allm[int(0.90 * len(allm))], 3),
            },
            "T21_snapshot_for_comparison": {"p50": 2.06, "p75": 11.41, "p90": 32.37},
        }

    census["gates_not_run_reason"] = None
    for g in ("G0", "G0b", "G3"):
        if not census[g]["pass"]:
            census["gates_not_run_reason"] = f"{g} failed: the test is not run"
    if census["gates_not_run_reason"]:
        census["VERDICT"] = "TEST NOT RUN — " + census["gates_not_run_reason"]
    elif not (census["G1"]["pass"] and census["G1b"]["pass"]):
        census["VERDICT"] = "POWER-BLOCKED — DEAD BY INSUFFICIENT POWER, held-out window NOT spent"
    else:
        census["VERDICT"] = "CENSUS PASSED - proceed to pre-registration"

    with open(OUT, "w") as fh:
        json.dump(census, fh, indent=1)
    print(json.dumps({k: v for k, v in census.items() if k != "G3"}, indent=1))
    print("\nG3 month counts:", census["G3"]["months_with_ge20_eligible"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
