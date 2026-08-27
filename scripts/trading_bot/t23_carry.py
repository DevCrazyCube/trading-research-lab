#!/usr/bin/env python3
"""T23 THE RULE. Cross-sectional perp funding carry, leakage-free, on the survivorship-complete
Binance USD-M panel. This file contains the decision; nothing else does.

WHAT THIS FIXES RELATIVE TO T21
-------------------------------
T21's +2.20 pp/yr carried four leakages, two self-disclosed and two found by the verifier:

  L1  the liquidity screen used TODAY'S 24h volume applied to a two-year-old history, so every
      name that was liquid then and is dead now was invisible.
      FIX: `screen_month()` reads ONLY daily quote volume from bars strictly BEFORE the holding
      month begins, from the historical dumps, for every symbol that existed then.

  L2  the threshold, the horizon and topN were chosen after seeing an earlier pass fail, with no
      declared trial count and no DSR.
      FIX: the grid is declared in T23_PREREGISTRATION.md before any number, the primary
      configuration is INHERITED from T21 rather than searched, and DSR is applied at the full
      declared trial count.

  L3  the universe came from live `exchangeInfo`, i.e. survivors only.
      FIX: the universe is the 920 fundingRate folders enumerated from data.binance.vision,
      delisted names included. A symbol enters and leaves on its own data.

  L4  all 22 months were in-sample.
      FIX: design/held-out split frozen in T23_POWER_GATE.md before the census.

And one omission neither party flagged: T21 measured REALISED FUNDING ONLY. A short perp against
a long spot is short the premium, and the premium's change over the holding month is real P&L.
`month_return()` charges it from `premiumIndexKlines`.

SIGN CONVENTION
---------------
Funding rate positive => longs pay shorts => the carrier (short perp, long spot) RECEIVES it.
Premium positive => perp above index. The carrier is short the premium, so a RISE in the premium
is a LOSS. Costs and tail charges are always non-negative and always subtracted.
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import pathlib
import random
import statistics

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "t23_cache"
PANEL = CACHE / "panel"
CASH_CSV = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "t13_cache" / "cash.csv"

# ---- frozen charges (see T23_POWER_GATE.md §5) ----------------------------------------------
ROUND_TRIP_BP = 36.8            # 30bp published VIP-0 fees + 5.2bp spot + 1.7bp perp half-spreads
DELISTING_TAIL = 0.0200         # -2.00% of position notional, measured worst 8h print (T21 §3f)
CAPITAL_MULTIPLIER = 1.2        # spot notional AND perp margin
VENUE_TAIL_BAR_PP = 1.00        # the required-edge bar, in pp/yr, over by-year T-bills

SCREEN_LOOKBACK_DAYS = 30
SCREEN_MIN_BARS = 20
MIN_HISTORY_DAYS = 60
MIN_FUNDING_PRINTS_IN_RANK_MONTH = 20


# ---------------------------------------------------------------------------
# calendar helpers
# ---------------------------------------------------------------------------

def ym_of(d: dt.date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = (y * 12 + (m - 1)) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def ym_start(ym: str) -> dt.date:
    return dt.date(int(ym[:4]), int(ym[5:7]), 1)


def ym_end(ym: str) -> dt.date:
    nxt = ym_add(ym, 1)
    return ym_start(nxt) - dt.timedelta(days=1)


def ms_to_date(ms: int) -> dt.date:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).date()


# ---------------------------------------------------------------------------
# panel loading
# ---------------------------------------------------------------------------

class Panel:
    """Everything the rule may read, and nothing it may not."""

    def __init__(self) -> None:
        self.funding_month: dict[str, dict[str, float]] = {}
        self.funding_prints: dict[str, dict[str, int]] = {}
        self.first_funding: dict[str, dt.date] = {}
        self.last_funding: dict[str, dt.date] = {}
        self.vol_days: dict[str, list[int]] = {}      # ordinal day numbers, sorted
        self.vol_vals: dict[str, list[float]] = {}    # quote volume aligned to vol_days
        self.premium_month_end: dict[str, dict[str, float]] = {}
        self.months: list[str] = []
        self.cash: list[tuple[dt.date, float]] = []

    # -- loaders -----------------------------------------------------------
    def load(self) -> "Panel":
        with (PANEL / "funding.csv").open() as fh:
            r = csv.reader(fh)
            next(r)
            for sym, ts, _iv, rate in r:
                ms = int(ts)
                d = ms_to_date(ms)
                ym = ym_of(d)
                fm = self.funding_month.setdefault(sym, {})
                fm[ym] = fm.get(ym, 0.0) + float(rate)
                fp = self.funding_prints.setdefault(sym, {})
                fp[ym] = fp.get(ym, 0) + 1
                if sym not in self.first_funding or d < self.first_funding[sym]:
                    self.first_funding[sym] = d
                if sym not in self.last_funding or d > self.last_funding[sym]:
                    self.last_funding[sym] = d

        with (PANEL / "perp_daily.csv").open() as fh:
            r = csv.reader(fh)
            next(r)
            for sym, day_ms, _close, qv, _cnt in r:
                d = ms_to_date(int(day_ms)).toordinal()
                self.vol_days.setdefault(sym, []).append(d)
                self.vol_vals.setdefault(sym, []).append(float(qv or 0.0))

        with (PANEL / "premium_daily.csv").open() as fh:
            r = csv.reader(fh)
            next(r)
            for sym, day_ms, prem in r:
                d = ms_to_date(int(day_ms))
                self.premium_month_end.setdefault(sym, {})[ym_of(d)] = float(prem or 0.0)

        allm = set()
        for fm in self.funding_month.values():
            allm |= set(fm)
        self.months = sorted(allm)

        with CASH_CSV.open() as fh:
            for row in csv.DictReader(fh):
                if row["date"] >= "2019-01-01":
                    self.cash.append((dt.date.fromisoformat(row["date"]), float(row["annual_pct"])))
        self.cash.sort()
        return self

    # -- point-in-time reads ----------------------------------------------
    def median_quote_volume(self, sym: str, as_of: dt.date) -> tuple[float, int]:
        """Median daily quote volume over the SCREEN_LOOKBACK_DAYS ending at `as_of`, inclusive.

        `as_of` is the last day of the month BEFORE the holding month. No bar dated after it is
        ever read. This is the fix for T21's Leakage 1.
        """
        days = self.vol_days.get(sym)
        if not days:
            return 0.0, 0
        hi = bisect.bisect_right(days, as_of.toordinal())
        lo = bisect.bisect_left(days, (as_of - dt.timedelta(days=SCREEN_LOOKBACK_DAYS - 1)).toordinal())
        vals = self.vol_vals[sym][lo:hi]
        if not vals:
            return 0.0, 0
        return statistics.median(vals), len(vals)

    def tbill_month_return(self, ym: str) -> float:
        """Compounding-free monthly accrual at the 3m T-bill rate quoted on the LAST business day
        BEFORE the holding month begins. Point in time, and by-year by construction."""
        start = ym_start(ym)
        idx = bisect.bisect_left(self.cash, (start, -1.0)) - 1
        if idx < 0:
            raise RuntimeError(f"no cash rate before {start}")
        rate = self.cash[idx][1] / 100.0
        days = (ym_end(ym) - start).days + 1
        return rate * days / 365.0


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------

class Config:
    def __init__(self, *, top_n: int, threshold_usd: float, name: str, mode: str = "rank"):
        self.top_n = top_n
        self.threshold_usd = threshold_usd
        self.name = name
        self.mode = mode  # "rank" | "all" | "btc" | "random"

    def as_dict(self) -> dict:
        return {"name": self.name, "top_n": self.top_n,
                "threshold_usd": self.threshold_usd, "mode": self.mode}


def screen_month(panel: Panel, ym: str, threshold_usd: float) -> list[str]:
    """The POINT-IN-TIME eligible universe for holding month `ym`.

    Everything here is decided on data dated on or before the last day of `ym - 1`.
    """
    as_of = ym_end(ym_add(ym, -1))
    prev = ym_add(ym, -1)
    out = []
    for sym in panel.funding_month:
        if not sym.endswith("USDT"):
            continue  # BUSD/USDC contracts are same-underlying duplicates of the USDT perp
        first = panel.first_funding.get(sym)
        if first is None or (ym_start(ym) - first).days < MIN_HISTORY_DAYS:
            continue
        if panel.funding_prints.get(sym, {}).get(prev, 0) < MIN_FUNDING_PRINTS_IN_RANK_MONTH:
            continue
        # Still listed at the moment of the rebalance. A contract that died mid-way through the
        # ranking month is not buyable on its last day, and without this check it would be
        # selected, contribute a silent zero for the holding month, and escape the delisting
        # tail charge -- a bias in the strategy's favour. Known at the rebalance, so PIT-safe.
        last = panel.last_funding.get(sym)
        if last is None or (as_of - last).days > 2:
            continue
        med, nbars = panel.median_quote_volume(sym, as_of)
        if nbars < SCREEN_MIN_BARS or med < threshold_usd:
            continue
        out.append(sym)
    return out


def rank_month(panel: Panel, ym: str, eligible: list[str]) -> list[str]:
    """Descending trailing-1-month realised funding. The signal, unchanged from T21."""
    prev = ym_add(ym, -1)
    return sorted(eligible, key=lambda s: -panel.funding_month[s][prev])


def month_return(panel: Panel, sym: str, ym: str, panel_last_month: str) -> dict:
    """One name's carry P&L for one holding month, as a fraction of that name's notional."""
    funding = panel.funding_month.get(sym, {}).get(ym, 0.0)
    prev = ym_add(ym, -1)
    pm = panel.premium_month_end.get(sym, {})
    p0, p1 = pm.get(prev), pm.get(ym)
    if p0 is None or p1 is None:
        dprem, prem_missing = 0.0, True
    else:
        dprem, prem_missing = p1 - p0, False
    last = panel.last_funding.get(sym)
    delisted = bool(last and ym_of(last) == ym and ym != panel_last_month)
    tail = DELISTING_TAIL if delisted else 0.0
    return {"funding": funding, "dpremium": dprem, "premium_missing": prem_missing,
            "delisted": delisted, "tail": tail,
            "gross": funding - dprem, "net_before_costs": funding - dprem - tail}


def run_book(panel: Panel, cfg: Config, months: list[str], *, seed: int | None = None) -> list[dict]:
    """Walk the book forward one month at a time. Returns one record per holding month."""
    rng = random.Random(seed) if seed is not None else None
    panel_last_month = panel.months[-1]
    held: set[str] = set()
    recs = []
    for ym in months:
        eligible = screen_month(panel, ym, cfg.threshold_usd)
        if cfg.mode == "btc":
            picks = ["BTCUSDT"] if "BTCUSDT" in eligible else []
        elif cfg.mode == "all":
            picks = list(eligible)
        elif cfg.mode == "random":
            picks = rng.sample(eligible, min(cfg.top_n, len(eligible))) if eligible else []
        else:
            picks = rank_month(panel, ym, eligible)[: cfg.top_n]
        if not picks:
            recs.append({"month": ym, "n_eligible": len(eligible), "n_held": 0,
                         "skipped": True})
            held = set()
            continue
        per = [month_return(panel, s, ym, panel_last_month) for s in picks]
        w = 1.0 / len(picks)
        gross = sum(p["gross"] for p in per) * w
        tail = sum(p["tail"] for p in per) * w
        new = set(picks)
        turnover = len(new - held) / len(new) if held else 1.0
        cost = turnover * ROUND_TRIP_BP / 10_000.0
        net = gross - tail - cost
        on_capital = net / CAPITAL_MULTIPLIER
        rf = panel.tbill_month_return(ym)
        med_vols = [panel.median_quote_volume(s, ym_end(ym_add(ym, -1)))[0] for s in picks]
        recs.append({
            "month": ym, "n_eligible": len(eligible), "n_held": len(picks), "picks": picks,
            "gross": gross, "funding": sum(p["funding"] for p in per) * w,
            "dpremium": sum(p["dpremium"] for p in per) * w,
            "premium_missing": sum(1 for p in per if p["premium_missing"]),
            "delistings": sum(1 for p in per if p["delisted"]),
            "tail": tail, "turnover": turnover, "cost": cost,
            "net": net, "on_capital": on_capital, "rf": rf, "excess": on_capital - rf,
            "median_pick_volume": statistics.median(med_vols) if med_vols else 0.0,
            "skipped": False,
        })
        held = new
    return recs


# ---------------------------------------------------------------------------
# summarisation
# ---------------------------------------------------------------------------

def summarise(recs: list[dict]) -> dict:
    live = [r for r in recs if not r["skipped"]]
    if len(live) < 2:
        return {"n_months": len(live), "degenerate": True}
    ex = [r["excess"] for r in live]
    net = [r["on_capital"] for r in live]
    mu, sd = statistics.fmean(ex), statistics.stdev(ex)
    years = len(live) / 12.0
    equity, peak, mdd = 1.0, 1.0, 0.0
    for r in live:
        equity *= (1.0 + r["on_capital"])
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1.0)
    return {
        "n_months": len(live),
        "years": years,
        "first_month": live[0]["month"], "last_month": live[-1]["month"],
        "gross_ann_pct": statistics.fmean([r["gross"] for r in live]) * 12 * 100,
        "funding_ann_pct": statistics.fmean([r["funding"] for r in live]) * 12 * 100,
        "dpremium_ann_pct": statistics.fmean([r["dpremium"] for r in live]) * 12 * 100,
        "tail_ann_pct": statistics.fmean([r["tail"] for r in live]) * 12 * 100,
        "cost_ann_pct": statistics.fmean([r["cost"] for r in live]) * 12 * 100,
        "net_on_capital_ann_pct": statistics.fmean(net) * 12 * 100,
        "rf_ann_pct": statistics.fmean([r["rf"] for r in live]) * 12 * 100,
        "excess_ann_pct": mu * 12 * 100,
        "excess_sd_ann_pct": sd * (12 ** 0.5) * 100,
        "excess_sharpe_ann": (mu * 12) / (sd * (12 ** 0.5)) if sd > 0 else float("nan"),
        "t_stat": mu / (sd / len(ex) ** 0.5) if sd > 0 else float("nan"),
        "worst_month_pct": min(net) * 100,
        "best_month_pct": max(net) * 100,
        "max_drawdown_pct": mdd * 100,
        "months_negative_excess": sum(1 for v in ex if v < 0),
        "mean_turnover": statistics.fmean([r["turnover"] for r in live]),
        "total_delistings_held": sum(r["delistings"] for r in live),
        "premium_missing_name_months": sum(r["premium_missing"] for r in live),
        "median_pick_volume_usd": statistics.median([r["median_pick_volume"] for r in live]),
        "mean_eligible": statistics.fmean([r["n_eligible"] for r in live]),
        "clears_venue_tail_bar": (mu * 12 * 100) > VENUE_TAIL_BAR_PP,
    }
