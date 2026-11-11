"""xcheck.py — an INDEPENDENT naive engine, used only to cross-check `engine.py` (DESIGN_v2 §3, §7).

It is written from the contract's text and shares NO code with `engine.py` (it does not import it).
Where the fast engine shifts whole matrices, this one walks the calendar the way a trader would:

    for every print t, in time order:
        1. earn the interval (t-1, t] on the positions that were put on at print t-1
           (price return, carry, hold cost), and book the cost of the trade done at print t-1;
        2. execute, at print t, the target that was decided `delay` prints earlier. The size of that
           trade is measured from where the book STANDS at print t:
             turnover_model="drift"  — each position has just grown by its own price return while
                                       the book grew by its price P&L: it stands at
                                       position * (1 + return) / (1 + book price P&L);
             turnover_model="target" — as if nothing had moved: it stands at the old target.

    delay = lag        when positions are filled on the panel's own prints   (lag >= 1)
    delay = extra_lag  when they are filled on an execution print F that is strictly later than
                       the decision print of the same row                    (extra_lag >= 0)

Everything is plain Python: lists, floats, `math.isnan`, explicit loops over prints and instruments.
It is slow on purpose and must never be used for a sweep. `tests/test_xcheck.py` asserts that the
two engines agree to 1e-10 on >= 100 random panels (lags, extra lags, per-instrument costs, hold
costs, carry, NaN warm-up, listings/delistings, exec prices).

Contract text implemented (DESIGN_v2 §3.1):
    r_t = X_t / X_{t-1} - 1                    X = panel prices, or the exec prices when given
    net = SUM held*r + SUM held*carry - SUM |d held|*cost_side
          - SUM (max(held,0)*hc_long + max(-held,0)*hc_short) * days/365,   hc = bp_year / 1e4,
          days = calendar days between the previous print and this one (UTC dates), 0 on the first print
    a target is flat (0) when it is NaN or when no decision exists yet;
    a held position with no return / no carry: 'refuse' raises, 'zero' books 0 and counts it
    (and such a position drifts by 0);
    under "drift" a book whose price P&L over one interval is -100 % or worse (1 + P&L <= 1e-9) is
    refused, unless it is the last print (no later trade is measured from it).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd


class NaiveRefused(Exception):
    """The naive engine's own refusal (deliberately not `engine.Refused`: no shared code)."""


@dataclass
class NaiveResult:
    """Same per-print quantities as `engine.BacktestResult`, computed by the loop."""

    net: pd.Series
    gross: pd.Series
    price_pnl: pd.Series
    carry: pd.Series
    cost: pd.Series
    hold_cost: pd.Series
    held: pd.DataFrame
    turnover: pd.Series
    gross_leverage: pd.Series
    meta: dict = field(default_factory=dict)
    turnover_target: pd.Series = None


def _bp_for(spec, name: str, what: str) -> float:
    """The bp value of `spec` for instrument `name`: a number, or a per-instrument dict / Series."""
    if spec is None or isinstance(spec, bool):
        raise NaiveRefused(f"{what}: not a cost: {spec!r}")
    if isinstance(spec, dict):
        if name not in spec:
            raise NaiveRefused(f"{what}: no entry for {name!r}")
        value = spec[name]
    elif isinstance(spec, pd.Series):
        if name not in spec.index:
            raise NaiveRefused(f"{what}: no entry for {name!r}")
        value = spec.loc[name]
    else:
        value = spec
    if value is None or isinstance(value, bool):
        raise NaiveRefused(f"{what}: not a cost for {name!r}: {value!r}")
    value = float(value)
    if math.isnan(value) or math.isinf(value) or value < 0.0:
        raise NaiveRefused(f"{what}: bad value for {name!r}: {value!r}")
    return value


def naive_backtest(
    panel,
    w: pd.DataFrame,
    *,
    lag: int = 1,
    cost_bp_side,
    hold_cost_long_bp_year=0.0,
    hold_cost_short_bp_year=0.0,
    exec_prices=None,
    extra_lag: int = 0,
    missing_return: str = "refuse",
    turnover_model: str = "drift",
) -> NaiveResult:
    """Loop re-computation of `engine.backtest` with the same arguments. See the module docstring."""
    if missing_return not in ("refuse", "zero"):
        raise NaiveRefused(f"missing_return: {missing_return!r}")
    if turnover_model not in ("drift", "target"):
        raise NaiveRefused(f"turnover_model: {turnover_model!r}")
    names = list(panel.prices.columns)
    stamps = list(panel.prices.index)
    n_prints = len(stamps)
    # calendar days since the previous print, from the UTC dates of the stamps themselves
    utc_dates = [stamp.tz_convert("UTC").date() for stamp in stamps]
    gap_days = [0] + [(utc_dates[k] - utc_dates[k - 1]).days for k in range(1, n_prints)]

    # ---- which price series, and how many prints pass between a decision and its execution
    if exec_prices is None:
        if isinstance(lag, bool) or int(lag) != lag or lag < 1:
            raise NaiveRefused(f"lag must be an integer >= 1; got {lag!r}")
        if extra_lag != 0:
            raise NaiveRefused("extra_lag is only defined with exec_prices")
        delay = int(lag)
        price_frame = panel.prices
    else:
        if panel.meta.get("exec_prices_strictly_after_decision") is not True:
            raise NaiveRefused("exec prices are not certified to be strictly after the decision print")
        if lag != 1:
            raise NaiveRefused("lag must stay at its default when exec_prices is given")
        if isinstance(extra_lag, bool) or int(extra_lag) != extra_lag or extra_lag < 0:
            raise NaiveRefused(f"extra_lag must be an integer >= 0; got {extra_lag!r}")
        delay = int(extra_lag)
        price_frame = exec_prices
        if list(price_frame.index) != stamps or set(price_frame.columns) != set(names):
            raise NaiveRefused("exec_prices is not aligned to the panel")

    if list(w.index) != stamps or set(w.columns) != set(names):
        raise NaiveRefused("w is not aligned to the panel")

    price = {name: [float(v) for v in price_frame[name].tolist()] for name in names}
    target = {name: [float(v) for v in w[name].tolist()] for name in names}
    accrual = None
    if panel.carry is not None:
        accrual = {name: [float(v) for v in panel.carry[name].tolist()] for name in names}

    side_cost = {name: _bp_for(cost_bp_side, name, "cost_bp_side") / 10000.0 for name in names}
    long_fee = {name: _bp_for(hold_cost_long_bp_year, name, "hold_cost_long_bp_year") / 10000.0 for name in names}
    short_fee = {name: _bp_for(hold_cost_short_bp_year, name, "hold_cost_short_bp_year") / 10000.0 for name in names}

    for name in names:
        for v in price[name]:
            if not math.isnan(v) and (math.isinf(v) or v <= 0.0):
                raise NaiveRefused(f"non-positive price for {name!r}")
        for v in target[name]:
            if math.isinf(v):
                raise NaiveRefused(f"infinite target for {name!r}")

    position = {name: 0.0 for name in names}      # what is held going INTO the next interval
    booked_cost = 0.0                             # cost of the trade just executed, booked next row
    booked_turnover = 0.0
    booked_target_change = 0.0
    out = {k: [] for k in ("net", "gross", "price_pnl", "carry", "cost", "hold_cost", "turnover", "turnover_target",
                           "gross_leverage")}
    held_rows = []
    n_nan_target = sum(1 for name in names for v in target[name] if math.isnan(v))
    n_no_return = 0
    n_no_carry = 0

    for t in range(n_prints):
        # ---- 1. earn the interval (t-1, t] on the positions put on at print t-1
        price_pnl = 0.0
        carry_pnl = 0.0
        hold_fee = 0.0
        leverage = 0.0
        grew_by = {name: 0.0 for name in names}       # each held instrument's own return over (t-1, t]
        for name in names:
            h = position[name]
            leverage += abs(h)
            if h == 0.0:
                continue
            before = price[name][t - 1] if t >= 1 else float("nan")
            now = price[name][t]
            if math.isnan(before) or math.isnan(now):
                if missing_return == "refuse":
                    raise NaiveRefused(f"held {name!r} at {stamps[t]} has no return")
                n_no_return += 1
            else:
                grew_by[name] = now / before - 1.0
                price_pnl += h * grew_by[name]
            if accrual is not None:
                c = accrual[name][t]
                if math.isinf(c):
                    raise NaiveRefused(f"infinite carry for {name!r}")
                if math.isnan(c):
                    if missing_return == "refuse":
                        raise NaiveRefused(f"held {name!r} at {stamps[t]} has no carry")
                    n_no_carry += 1
                else:
                    carry_pnl += h * c
            annual_rate = long_fee[name] if h > 0.0 else short_fee[name]
            hold_fee += abs(h) * annual_rate * gap_days[t] / 365.0
        gross = price_pnl + carry_pnl
        out["price_pnl"].append(price_pnl)
        out["carry"].append(carry_pnl)
        out["gross"].append(gross)
        out["cost"].append(booked_cost)
        out["hold_cost"].append(hold_fee)
        out["net"].append(gross - booked_cost - hold_fee)
        out["turnover"].append(booked_turnover)
        out["turnover_target"].append(booked_target_change)
        out["gross_leverage"].append(leverage)
        held_rows.append([position[name] for name in names])

        # ---- 2. at print t, execute the target decided `delay` prints ago
        decided_at = t - delay
        booked_cost = 0.0
        booked_turnover = 0.0
        booked_target_change = 0.0
        book_now = 1.0 + price_pnl                    # the book after (t-1, t], per unit of its start value
        wiped_out = book_now <= 1e-9                  # -100 % to within rounding
        if turnover_model == "drift" and wiped_out and t < n_prints - 1:
            raise NaiveRefused(f"the book lost 100 % or more over the print ending {stamps[t]}")
        for name in names:
            if decided_at < 0:
                wanted = 0.0
            else:
                wanted = target[name][decided_at]
                if math.isnan(wanted):
                    wanted = 0.0
            if turnover_model == "drift" and position[name] != 0.0 and not wiped_out:
                stands_at = position[name] * (1.0 + grew_by[name]) / book_now
            else:
                stands_at = position[name]
            traded = abs(wanted - stands_at)
            booked_turnover += traded
            booked_cost += traded * side_cost[name]
            booked_target_change += abs(wanted - position[name])
            position[name] = wanted

    index = panel.prices.index
    return NaiveResult(
        net=pd.Series(out["net"], index=index, name="net", dtype=float),
        gross=pd.Series(out["gross"], index=index, name="gross", dtype=float),
        price_pnl=pd.Series(out["price_pnl"], index=index, name="price_pnl", dtype=float),
        carry=pd.Series(out["carry"], index=index, name="carry", dtype=float),
        cost=pd.Series(out["cost"], index=index, name="cost", dtype=float),
        hold_cost=pd.Series(out["hold_cost"], index=index, name="hold_cost", dtype=float),
        held=pd.DataFrame(held_rows, index=index, columns=names, dtype=float),
        turnover=pd.Series(out["turnover"], index=index, name="turnover", dtype=float),
        turnover_target=pd.Series(out["turnover_target"], index=index, name="turnover_target", dtype=float),
        gross_leverage=pd.Series(out["gross_leverage"], index=index, name="gross_leverage", dtype=float),
        meta={
            "delay": delay,
            "n_nan_w": n_nan_target,
            "n_missing_return_held": n_no_return,
            "n_missing_carry_held": n_no_carry,
        },
    )


__all__ = ["naive_backtest", "NaiveResult", "NaiveRefused"]
