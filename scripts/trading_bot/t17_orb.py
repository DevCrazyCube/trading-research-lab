#!/usr/bin/env python3
"""T17 — THE FROZEN ORB RULE. Hashed by `research/trading_bot/T17_PREREGISTRATION.md`.

Every decision the strategy makes lives in this file. Data collection lives in
`t17_collect.py`, the universe screen in `t17_screen.py`, and the run/report driver in
`t17_run.py`. This file is hashed BEFORE any T17 PnL number exists; editing it after that
point breaks the hash and invalidates the run, which is the entire point.

THE RULE (Zarattini, Barbon & Aziz 2024, SSRN 4729284, §2.1 and §4)
-------------------------------------------------------------------
1. Universe: open >= $5, 14-day avg volume >= 1,000,000 shares, ATR(14) >= $0.50.
   All three evaluated on information available at 09:30 -- see `t17_screen.py` for the one
   place this corrects the B22B runner's same-day ATR lookahead.
2. Opening range = [09:30, 09:35) ET. Direction from that candle: bullish -> long only,
   bearish -> short only, DOJI -> no trade. Direction is not a free parameter.
3. "Stocks in Play": opening-5-minute volume >= 100 % of the same stock's own 14-session
   average opening-5-minute volume, then the TOP 20 by that ratio.
4. Entry: stop order at the opening-range high (long) / low (short).
5. Stop loss: R = 10 % of ATR(14) from the ENTRY FILL. Target: the close.
6. Sizing: 1 % of equity risked per position, gross exposure capped at 4x equity.

WHAT THIS FILE ADDS TO THE PAPER, AND WHY EACH ADDITION IS ADVERSE
-------------------------------------------------------------------
The paper credits a fill at exactly the stop price and models only $0.0035/share. Every gap
below is filled on the side that costs the trader money, because the whole question is what
the omitted friction does:

  a. GAP-THROUGH FILLS. If the bar that triggers the entry OPENS beyond the stop level, the
     fill is the OPEN, not the level. Same for a stop-loss exit. A stop order cannot fill
     better than the market.
  b. SAME-BAR AMBIGUITY. If one minute bar both triggers the entry and covers the stop-loss
     level, the stop-loss is assumed to have been hit in that bar. Minute bars do not carry
     tick order, so the adverse ordering is assumed.
  c. SLIPPAGE IS NEVER ZERO. Two modes, both driven by the T5/B22B MEASUREMENT and neither
     by the paper's zero:
        MEAN      -- the T6 per-side cost model, charged as a fraction of notional.
        EMPIRICAL -- a per-trade draw from B22B's 429 measured entry-slippage observations,
                     in basis points of R, applied to the PRICE. The exit draws independently
                     from the same distribution (B22B never measured an exit; this is the
                     `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG` provenance) and additionally pays
                     the exit half-spread. This mode is what carries the FAT TAIL into the
                     drawdown, which a mean cannot do.
  d. CAPITAL IS RESERVED AT DECISION TIME. The 4x gross cap is applied at 09:35 in relative-
     volume rank order, before it is known which stops trigger. A backtest that only charged
     capital to the trades that happened would be using the future to allocate.

ARITHMETIC. Integer micro-dollars throughout, via the frozen `to_micros`. Money never
touches a float until the report.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from trading_bot import frozen as PINNED  # noqa: E402

Refused = PINNED.Refused

# ---------------------------------------------------------------- frozen parameters

TOP_N = 20                       # the paper's "top 20 by relative volume"
MIN_RELVOL_NUM = 100             # >= 100 % of its own 14-session average, as an integer ratio
MIN_RELVOL_DEN = 100
RELVOL_LOOKBACK = 14
MIN_RELVOL_HISTORY = 10          # of the 14; fewer is a REFUSAL, not a relvol of 1.0
RISK_FRACTION_NUM = 1            # 1 % of equity per position
RISK_FRACTION_DEN = 100
GROSS_LEVERAGE_CAP = 4           # 4x equity
STOP_LOSS_ATR_PCT = PINNED.STOP_LOSS_ATR_PCT     # 10, from the pinned harness

# The design/held-out split, fixed here and nowhere else.
DESIGN_START, DESIGN_END = "2016-01-26", "2021-12-31"
HELDOUT_START, HELDOUT_END = "2022-01-03", "2026-08-14"
# Secondary window, entirely AFTER the paper's own 2016-2023 study period, reported alongside.
POSTPAPER_START, POSTPAPER_END = "2024-01-02", "2026-08-14"


# ---------------------------------------------------------------- selection

def relative_volume(today_vol: int, history: list) -> int:
    """Opening-5-minute volume as an integer percentage of its own 14-session average.

    Refuses on a short history: a stock with three observations has no 14-session average,
    and substituting the mean of three would manufacture a relative volume for exactly the
    newly-listed, thinly-covered names whose breakouts are most likely to be noise.
    """
    if len(history) < MIN_RELVOL_HISTORY:
        raise Refused(
            f"relative volume needs >= {MIN_RELVOL_HISTORY} of the last {RELVOL_LOOKBACK} "
            f"opening-range observations; got {len(history)}. Absent is not 100 %."
        )
    avg = sum(history) // len(history)
    if avg <= 0:
        raise Refused("a zero average opening volume has no relative volume; refusing")
    return today_vol * 100 // avg


def select(candidates: list) -> list:
    """Top-N by relative volume among candidates that pass the >= 100 % filter.

    `candidates` are (relvol_pct, symbol, direction, opening, atr_micros). Ties break on
    symbol so the selection is deterministic and cannot depend on dict ordering.
    """
    eligible = [c for c in candidates
                if c[0] * MIN_RELVOL_DEN >= MIN_RELVOL_NUM * 100 and c[2] is not None]
    eligible.sort(key=lambda c: (-c[0], c[1]))
    return eligible[:TOP_N]


# ---------------------------------------------------------------- one stock-day

def simulate_stock_day(direction: str, entry_level: int, r_micros: int, bars: list,
                       entry_slip_micros: int, exit_slip_micros: int,
                       entry_bar_stop_rule: str = "close") -> dict:
    """One position, minute by minute, in integer micro-dollars.

    `bars` are the session's 1-minute bars from 09:35 inclusive, each a dict of integer
    micro-dollar o/h/l/c, in time order. `entry_slip_micros` / `exit_slip_micros` are
    ADVERSE magnitudes already signed positive-is-worse by the caller.

    Returns the outcome and the per-share PnL. NO_TRIGGER is a distinct outcome and is never
    a zero-PnL trade: it is a trade that did not happen (B22B's rule, carried across).

    THE ENTRY BAR IS THE ONE PLACE "ALWAYS ASSUME THE WORST" IS WRONG, AND WHY
    --------------------------------------------------------------------------
    R here is ~0.5 % of price (10 % of an ATR that is ~5 % of price on this universe) and a
    one-minute bar in a top-relative-volume name routinely spans that much. So on the bar
    that triggers the entry, the bar's LOW is very often already more than R below the
    breakout level -- but most of that low happened BEFORE the breakout, when no position
    existed. Charging it would stop out a large share of trades at -1R for a reason that is
    an artifact of bar granularity, not of the market.

    Two rules, and the choice is stated rather than buried:
      "close"    (frozen default) -- on the ENTRY bar only, the stop is deemed hit iff the
                 bar CLOSES beyond it. A bar that closes through the stop certainly traded
                 through it after the entry. From the next bar on, the LOW/HIGH is used as
                 normal.
      "full_bar" (reported as a sensitivity, never as the headline) -- the entry bar's whole
                 low/high is used, i.e. the maximally adverse reading.
    """
    if direction not in ("long", "short"):
        raise Refused(f"direction must be long or short, got {direction!r}")
    if r_micros <= 0:
        raise Refused("R must be positive")
    if not bars:
        raise Refused("no intraday bars: a stock-day with no data is missing, not flat")

    sign = 1 if direction == "long" else -1

    entry_index = None
    for i, b in enumerate(bars):
        touched = (b["h"] >= entry_level) if sign > 0 else (b["l"] <= entry_level)
        if touched:
            entry_index = i
            break
    if entry_index is None:
        return {"outcome": "NO_TRIGGER"}

    b = bars[entry_index]
    # (a) gap-through: a stop order cannot fill better than the market.
    base = max(entry_level, b["o"]) if sign > 0 else min(entry_level, b["o"])
    fill = base + sign * entry_slip_micros
    stop_level = fill - sign * r_micros

    if entry_bar_stop_rule not in ("close", "full_bar"):
        raise Refused(f"unknown entry_bar_stop_rule {entry_bar_stop_rule!r}")

    for j in range(entry_index, len(bars)):
        bj = bars[j]
        if j == entry_index and entry_bar_stop_rule == "close":
            hit = (bj["c"] <= stop_level) if sign > 0 else (bj["c"] >= stop_level)
        else:
            hit = (bj["l"] <= stop_level) if sign > 0 else (bj["h"] >= stop_level)
        if hit:
            # (b) same-bar ambiguity resolves against the trader; (a) applies to the exit too,
            # except on the entry bar, whose open precedes the entry and cannot be the exit.
            if j == entry_index:
                exit_base = (min(stop_level, bj["c"]) if sign > 0
                             else max(stop_level, bj["c"]))
            else:
                exit_base = min(stop_level, bj["o"]) if sign > 0 else max(stop_level, bj["o"])
            exit_price = exit_base - sign * exit_slip_micros
            return {"outcome": "STOPPED", "entry": fill, "exit": exit_price,
                    "pnl_per_share": sign * (exit_price - fill),
                    "slip_micros": entry_slip_micros + exit_slip_micros,
                    "entry_index": entry_index, "exit_index": j}

    close = bars[-1]["c"]
    exit_price = close - sign * exit_slip_micros
    return {"outcome": "CLOSE", "entry": fill, "exit": exit_price,
            "pnl_per_share": sign * (exit_price - fill),
            "slip_micros": entry_slip_micros + exit_slip_micros,
            "entry_index": entry_index, "exit_index": len(bars) - 1}


def position_shares(equity_micros: int, r_micros: int) -> int:
    """1 % of equity risked over a stop distance of R. Integer shares, rounded DOWN."""
    if equity_micros <= 0:
        raise Refused("no equity left to size a position with")
    if r_micros <= 0:
        raise Refused("R must be positive")
    return (equity_micros * RISK_FRACTION_NUM) // (RISK_FRACTION_DEN * r_micros)


def apply_gross_cap(sized: list, equity_micros: int, mode: str = "pro_rata") -> list:
    """Enforce the 4x gross-exposure cap on the whole basket.

    (d) The cap is applied at 09:35, on the ENTRY LEVELS, before it is known which stops
    trigger. Reserving capital only for the trades that actually happened would allocate
    with the future.

    WHY THIS BINDS ALMOST EVERY DAY, AND WHY THE DEFAULT IS PRO-RATA. On this universe R
    (10 % of ATR(14)) is about 0.5 % of price, so risking 1 % of equity over a stop that
    close puts roughly **2x equity of notional into a SINGLE position**. Twenty of them is
    ~40x, and the cap is 4x. The two readings of "1 % risked per position, max 4x leverage"
    therefore give very different strategies:

      pro_rata  -- keep all twenty names and scale every position by 4x/(required), so the
                   basket is 4x gross and each position risks ~0.1 % of equity. This is the
                   reading that actually trades "the top 20", which is what the paper's
                   headline row is, and it is the DIVERSIFIED and therefore
                   strategy-FAVOURABLE reading.
      truncate  -- take positions in relative-volume rank order until the cap is spent,
                   which on this universe means about TWO names a day.

    Sharpe is invariant to a uniform leverage scale, so this choice does not move the
    verdict through leverage; it moves it through DIVERSIFICATION, and the default is the
    one that gives the strategy the most of it. `truncate` is reported as a sensitivity.
    """
    cap = GROSS_LEVERAGE_CAP * equity_micros
    live = [i for i in sized if i["shares"] > 0]
    if not live:
        return []
    # Notional in MICRO-dollars: price_micros * shares is already micro-dollars.
    required = sum(i["shares"] * i["entry_level"] for i in live)
    if mode == "truncate":
        used, taken = 0, []
        for item in live:
            n = item["shares"] * item["entry_level"]
            if used + n > cap:
                continue
            used += n
            taken.append(item)
        return taken
    if mode != "pro_rata":
        raise Refused(f"unknown gross-cap mode {mode!r}")
    if required <= cap:
        return live
    out = []
    for item in live:
        shares = item["shares"] * cap // required
        if shares <= 0:
            continue
        scaled = dict(item)
        scaled["shares"] = shares
        out.append(scaled)
    return out


# ---------------------------------------------------------------- slippage draws

class EmpiricalSlippage:
    """B22B's 429 measured entry-slippage observations, in basis points of R.

    WHY bp OF R AND NOT bp OF NOTIONAL. R is this strategy's own risk unit and the stop
    distance; a slippage of 1,181 bp of R is 11.8 % of the risk on the trade whatever the
    stock's price is. Charging in R is what makes the FAT TAIL bite the PnL rather than
    being averaged away in a notional-fraction cost term.

    The favourable tail is KEPT (it is a measurement, not a modelling choice) but the
    contaminated observations are removed at the same 0.1-ATR rung the T6 cost model uses --
    a trigger print more than one whole R beyond the stop is a dislocated print, and every
    one of them sits in the favourable tail where it flatters the strategy.

    Draws are from a fixed seed via a linear congruential generator, so a run is exactly
    reproducible and no library RNG version can change a published number.
    """

    PATH = ROOT / "research" / "trading_bot" / "T17_SLIPPAGE_EMPIRICAL.json"
    DECONTAMINATION_ATR = 0.1

    def __init__(self, seed: int, floor_at_zero: bool = False):
        rows = json.loads(self.PATH.read_text())
        kept = [r for r in rows if r["through_atr"] <= self.DECONTAMINATION_ATR]
        if len(kept) < 100:
            raise Refused(f"only {len(kept)} decontaminated slippage observations; refusing")
        self.values = sorted(r["slippage_r_bp"] for r in kept)
        if floor_at_zero:
            self.values = [max(0, v) for v in self.values]
        self.seed = seed & 0xFFFFFFFFFFFFFFFF
        self.state = self.seed
        self.n = len(self.values)

    def _next(self) -> int:
        self.state = (6364136223846793005 * self.state + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return self.state >> 33

    def draw_micros(self, r_micros: int) -> int:
        """One adverse slippage magnitude in micro-dollars, positive is worse."""
        v = self.values[self._next() % self.n]
        return v * r_micros // 10000


__all__ = [
    "TOP_N", "MIN_RELVOL_HISTORY", "RELVOL_LOOKBACK", "GROSS_LEVERAGE_CAP",
    "DESIGN_START", "DESIGN_END", "HELDOUT_START", "HELDOUT_END",
    "POSTPAPER_START", "POSTPAPER_END",
    "relative_volume", "select", "simulate_stock_day", "position_shares",
    "apply_gross_cap", "EmpiricalSlippage",
]
