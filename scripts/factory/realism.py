"""realism.py — the DRIFT-AWARE account simulator (DESIGN_v2 §3.6).

Two jobs:
  1. the OFFICIAL engine for books that are re-balanced on a schedule (monthly / weekly long-only
     primaries). `engine.backtest` assumes the target fractions are restored at no cost on every
     print; a real book holds UNITS that drift with prices between trades. This module tracks units.
  2. the realism pass: the same book at EUR 1k / 5k / 10k once lot sizes, minimum fees, spreads and
     financing mark-ups are real.
`VenueSpec.ideal()` (no fees, no spread, no mark-up, fractional units) makes it the frictionless
reference; with it and a trade on every print the account's return equals `engine.backtest`'s
gross (price + carry) return to ~1e-12 — the two engines agree on what the frictionless book is.
Add a proportional fee and the account's cost series is the engine's `turnover_model="drift"` cost
to second order in the fee: both pay for restoring the targets as prices move. Measured on 24 slow
books at 10 bp: within 2.2e-6 of equity on any print and 0.04 % in total (the engine drifts
positions against the book's price return only; the account's equity has also paid the previous
fee and earned carry). The "target" model charges those accounts 2.2x-3.4x too little.

EXECUTION TIMING — exactly the engine's
  `w[s]` is the target decided at row s from rows <= s. It can be traded at
        row s + lag          at the price panel.prices[s + lag]                 (lag >= 1), or
        row s + extra_lag    at the price exec_prices[s + extra_lag]            (extra_lag >= 0),
  the exec print being strictly later in clock time than the decision print of its row (same
  refusals as the engine). Call that offset `delay`. At TRADE row t the account therefore trades
  towards w[t - delay]; rows t < delay trade nothing. Units bought at print t first earn the
  interval (t, t+1], i.e. `held[t+1]` — the same row in which the engine first holds w[t - delay].
  `rebalance_mask` marks TRADE rows, not decision rows: on a True row t the target is w[t - delay].
  To trade the decision of row s, set the mask True on row s + delay
  (`portfolio.rebalance_rows(index, "monthly", offset=delay)` builds exactly that).

THE ACCOUNT, print by print (X = the execution series; m_i = contract_notional_i; days_t = calendar
days between print t-1 and print t, `engine.calendar_days`)

  for t = 0 .. T-1:
    1. EARN (t-1, t] on the units held since print t-1, n_i = units_i * m_i * X[t-1, i] its start notional:
           price P&L   = SUM_i units_i * m_i * (X[t, i] - last valid X_i)
           carry       = SUM_i n_i * carry[t, i]                    (the panel's financing leg / funding)
           financing   = SUM_i ( max(n_i, 0) * financing_long_bp_year_i + max(-n_i, 0) * financing_short_bp_year_i )
                         / 1e4 * days_t / 365                       (venue mark-ups, calendar time)
           equity     += price P&L + carry - financing                              -> E_mark[t]
    2. CONTRIBUTE: on the first print of each calendar month after row 0, equity += monthly_contribution
                                                                                    -> E_pre[t]
    3. TRADE, if t is a trade row (`rebalance_mask[t]`, or every row when the mask is None) and t >= delay:
           f_i = w[t - delay, i] ;  current weight c_i = units_i * m_i * X[t, i] / E_pre[t]
           instrument i is traded only if  |f_i - c_i| > no_trade_band * max(|f_i|, 1e-4)
               (band 0 = always re-balance to target; when it trades it goes TO THE TARGET, not to
               the edge of the band);
           desired notional = f_i * E_pre[t]; if SUM_i |notional_i| / leverage_cap_i would exceed
               E_pre[t], the instruments being traded are scaled down pro rata until it does not;
           units = desired notional / (m_i * X[t, i]), rounded TOWARDS ZERO to a multiple of
               lot_step_i (lot_step 0 = fractional units);
           an order below min_notional_i is not sent, unless it closes the position in full; orders
               smaller than 1e-12 of equity are float dust and are ignored;
           each order pays  max(min_fee_i, fee_bp_i/1e4 * notional) + half_spread_bp_i/1e4 * notional
                                                                                    -> equity[t]
       Between trades NOTHING is done: units stay, weights drift with prices.

  Per-print returns, booked like the engine (the cost of the trade at t-1 lands in row t, the first
  row the new position earns):
        net[t]   = E_mark[t] / E_pre[t-1] - 1                         net[0] = 0
        gross[t] = (price P&L[t] + carry[t]) / E_pre[t-1]             (before fees, spread, financing)
        held[t, i] = n_i / E_pre[t-1]                                 (the weight actually in force)
  With no contributions PROD(1 + net) is the account's growth up to the last mark.

WHAT THE NUMBERS ARE IN
  One currency: prices, fees, minimum fees and equity are all in the panel's price currency. There is
  no currency conversion (an EUR account trading USD instruments carries EURUSD exposure that is NOT
  modelled) — pass `currency` to `VenueSpec.from_json` so that amounts quoted in another currency come
  back UNKNOWN rather than silently mis-scaled.
  `equity` is the EXCESS-return account, like every series in this tree: the carry panel already
  charges funded positions the risk-free rate. The cash yield a venue actually pays is reported
  separately (`report_total=True`, column `flows["cash_yield"]`), never mixed into `equity`
  (DESIGN_v2 §2). Per print it is
      max(idle cash - cash_interest_threshold, 0) * cash_interest_bp_year / 1e4 * days_t / 365
        + (funded long notional) * tbill[t]
  where idle cash = equity - funded long notional. The second term hands back the risk-free leg
  that the carry panel charged a FUNDED long (shares, spot): its holder paid cash and owes no
  financing. TOTAL return of the account = excess (`net`) + cash_yield / pre-trade equity. Balances
  are those of the excess account: the yield is not re-invested in the simulation.

UNKNOWN IS NOT ZERO
  Every `VenueSpec` cost field is Optional; None means UNKNOWN (null / "UNKNOWN" / free text in
  `landscape/venues.json`). `simulate_account` REFUSES when a field the run depends on is unknown:
  always fee_bp, min_fee, half_spread_bp, lot_step, min_notional, contract_notional, leverage_cap;
  financing_long_bp_year if the book is ever long, financing_short_bp_year if it is ever short;
  cash_interest_bp_year, cash_interest_threshold and `funded` when `report_total=True`.
  Fill a gap only with `spec.with_overrides(field=value)`, which records that the value did not come
  from the file. `VenueSpec.ideal()` is the explicit all-zero venue, named so that a frictionless
  run can never be mistaken for a costed one (`venue_id == "IDEAL"`).

STATED LIMITS
  * Orders fill in full at X[t] +/- half the spread: no market impact, no partial fills, no queue.
  * The leverage cap is enforced when trading (targets are cut) and only REPORTED between trades
    (`n_prints_over_cap`); margin calls and forced liquidation are not modelled. Equity <= 0 stops
    the account (`ruined_at`).
  * A price missing on a print (policy "zero") leaves the position marked at its last valid price and
    the P&L of the gap is realised when the price returns — unlike the engine, which books 0 for both
    NaN-return rows. On a gappy panel the two therefore differ by design. An order that cannot be
    priced on a trade row is not sent; it is reconsidered on the next trade row.
  * Financing and cash interest accrue on calendar days (ACT/365), like the engine's hold costs;
    cash interest is a flat annual rate.
  * The tracking error is measured against `ideal_net`; by default that is `engine.backtest(w)` at
    zero cost, which re-balances on every print. For a scheduled book pass the reference you mean.
"""
from __future__ import annotations

import json
import math
import pathlib
import re
from dataclasses import dataclass, field, fields, replace
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from .engine import (
    DAYS_PER_YEAR, Refused, aligned_exec_prices, backtest, calendar_days, resolve_shift, validate_prices,
    validate_weights,
)
from .panel import PanelBundle
from .stats import Window, window_mask

COST_FIELDS = (
    "fee_bp", "min_fee", "half_spread_bp", "lot_step", "min_notional", "contract_notional",
    "financing_long_bp_year", "financing_short_bp_year", "leverage_cap", "cash_interest_bp_year",
    "cash_interest_threshold",
)
ALWAYS_REQUIRED = ("fee_bp", "min_fee", "half_spread_bp", "lot_step", "min_notional", "contract_notional", "leverage_cap")
JSON_KEYS: Dict[str, Tuple[str, ...]] = {
    "fee_bp": ("fee_bp", "fee_bp_taker"),
    "min_fee": ("min_fee", "min_fee_per_order"),
    "half_spread_bp": ("half_spread_bp", "typical_half_spread_bp"),
    "lot_step": ("lot_step",),
    "min_notional": ("min_notional", "min_order_notional"),
    "contract_notional": ("contract_notional", "contract_multiplier"),
    "financing_long_bp_year": ("financing_long_bp_year",),
    "financing_short_bp_year": ("financing_short_bp_year",),
    "leverage_cap": ("leverage_cap", "leverage_caps"),
    "cash_interest_bp_year": ("cash_interest_bp_year",),
    "cash_interest_threshold": ("cash_interest_threshold",),
}
UNKNOWN_WORDS = {"", "unknown", "n/a", "na", "none", "null", "tbd", "?", "-"}
NO_TRADE_FLOOR = 1e-4          # weight floor in the no-trade test: |f - c| > band * max(|f|, NO_TRADE_FLOOR)
DUST = 1e-12                   # orders below this fraction of equity are float noise, not orders


# --------------------------------------------------------------------------------------------------
# VenueSpec
# --------------------------------------------------------------------------------------------------
def _resolve(raw, class_keys: Sequence[str], currency: Optional[str]) -> Tuple[Optional[float], str]:
    """(number or None, why) for one raw JSON value. None = UNKNOWN. Never guesses."""
    if raw is None:
        return None, "null"
    if isinstance(raw, bool):
        return None, "a boolean is not a number"
    if isinstance(raw, (int, float)):
        return (float(raw), "number") if math.isfinite(raw) else (None, "not finite")
    if isinstance(raw, str):
        text = raw.strip()
        if text.lower() in UNKNOWN_WORDS:
            return None, f"marked unknown ({raw!r})"
        try:
            value = float(text)
        except ValueError:
            return None, f"free text, not a number: {text[:80]!r}"
        return (value, "numeric string") if math.isfinite(value) else (None, "not finite")
    if isinstance(raw, dict):
        for key in class_keys:
            if key in raw:
                value, why = _resolve(raw[key], class_keys, currency)
                return value, f"[{key!r}] {why}"
        if "value" in raw:
            value, why = _resolve(raw["value"], class_keys, currency)
            return value, f"[value] {why}"
        if "amount" in raw:
            quoted = raw.get("currency")
            if quoted is not None and currency is not None and \
                    not re.search(rf"\b{re.escape(currency)}\b", str(quoted), flags=re.IGNORECASE):
                return None, f"amount is quoted in {quoted!r}, the simulation currency is {currency!r}"
            value, why = _resolve(raw["amount"], class_keys, currency)
            return value, f"[amount] {why}"
        if "markup_bp" in raw:
            value, why = _resolve(raw["markup_bp"], class_keys, currency)
            return value, f"[markup_bp] {why}"
        if currency is not None:
            for key in raw:
                if isinstance(key, str) and key.upper() == currency.upper():
                    value, why = _resolve(raw[key], class_keys, currency)
                    return value, f"[{key!r}] {why}"
        return None, f"object with no usable key (pass instrument_class=...); keys: {sorted(map(str, raw))[:12]}"
    return None, f"unsupported JSON type {type(raw).__name__}"


@dataclass(frozen=True)
class VenueSpec:
    """Trading terms of ONE instrument class at ONE venue, in the simulation currency.

    fee_bp                   commission per side, bp of order notional
    min_fee                  minimum commission per ORDER, currency units (0.0 = the venue has none)
    half_spread_bp           half the bid-ask spread, bp of order notional, paid on every order
    lot_step                 order-size increment in UNITS; 0.0 = fractional units allowed
    min_notional             smallest order the venue accepts, currency units (0.0 = none)
    contract_notional        currency value of ONE unit per 1.0 of price (1.0 for shares / spot;
                             the contract multiplier for futures and CFDs)
    financing_long_bp_year   mark-up charged on LONG notional per year, on top of the carry panel
    financing_short_bp_year  mark-up charged on SHORT notional per year
    leverage_cap             maximum gross notional / equity for this class (1.0 = unlevered;
                             math.inf = no cap, as in `VenueSpec.ideal()`)
    cash_interest_bp_year    flat annual rate the venue pays on cash above the threshold
    cash_interest_threshold  cash balance below which no interest is paid, currency units
    funded                   True if a long position is PAID FOR in cash (shares, spot crypto);
                             False if cash stays as collateral (CFD, FX, perps, futures)
    venue_id, instrument_class, currency, notes   provenance; `notes[field]` says where each value
                             came from ('status': 'ok' | 'unknown' | 'override' | 'given')

    None = UNKNOWN for every cost field, and unknown is never zero: `simulate_account` refuses a run
    that depends on an unknown field. `VenueSpec()` is the all-unknown spec.
    """

    fee_bp: Optional[float] = None
    min_fee: Optional[float] = None
    half_spread_bp: Optional[float] = None
    lot_step: Optional[float] = None
    min_notional: Optional[float] = None
    contract_notional: Optional[float] = None
    financing_long_bp_year: Optional[float] = None
    financing_short_bp_year: Optional[float] = None
    leverage_cap: Optional[float] = None
    cash_interest_bp_year: Optional[float] = None
    cash_interest_threshold: Optional[float] = None
    funded: Optional[bool] = None
    venue_id: str = "custom"
    instrument_class: Optional[str] = None
    currency: Optional[str] = None
    notes: dict = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        for name in COST_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            unbounded = name == "leverage_cap" and isinstance(value, float) and value == math.inf
            if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)) \
                    or not (math.isfinite(value) or unbounded) or value < 0:
                raise Refused(f"VenueSpec.{name} must be a finite number >= 0, or None for UNKNOWN; got {value!r}")
            object.__setattr__(self, name, float(value))
        if self.leverage_cap is not None and self.leverage_cap <= 0:
            raise Refused(f"VenueSpec.leverage_cap must be > 0; got {self.leverage_cap!r}")
        if self.contract_notional is not None and self.contract_notional <= 0:
            raise Refused(f"VenueSpec.contract_notional must be > 0; got {self.contract_notional!r}")
        if self.funded is not None and not isinstance(self.funded, bool):
            raise Refused(f"VenueSpec.funded must be True, False or None; got {self.funded!r}")

    # ---- the reference venue
    @classmethod
    def ideal(cls, funded: Optional[bool] = None) -> "VenueSpec":
        """The FRICTIONLESS, FRACTIONAL venue: no commission, no minimum fee, no spread, no financing
        mark-up, no minimum order, infinitely divisible units (lot_step 0), one unit = one price
        (contract_notional 1), no leverage cap (inf), no cash interest. With it `simulate_account`
        is the frictionless drift-aware reference engine: its return is price + carry and nothing
        else. Every field is KNOWN to be zero here — this is a named choice, not a default; the
        result's meta carries venue_id "IDEAL". `funded` only matters for `report_total`."""
        notes = {name: {"status": "given", "why": "VenueSpec.ideal(): frictionless reference"} for name in COST_FIELDS}
        return cls(fee_bp=0.0, min_fee=0.0, half_spread_bp=0.0, lot_step=0.0, min_notional=0.0, contract_notional=1.0,
                   financing_long_bp_year=0.0, financing_short_bp_year=0.0, leverage_cap=math.inf,
                   cash_interest_bp_year=0.0, cash_interest_threshold=0.0, funded=funded, venue_id="IDEAL",
                   instrument_class="ideal", notes=notes)

    # ---- unknowns
    def unknown_fields(self) -> List[str]:
        """Names of the fields that are UNKNOWN (None), `funded` included."""
        return [n for n in COST_FIELDS + ("funded",) if getattr(self, n) is None]

    def require(self, names: Sequence[str], what: str = "this simulation") -> None:
        """Raise `Refused` naming every field in `names` that is unknown."""
        missing = [n for n in names if getattr(self, n) is None]
        if missing:
            why = "; ".join(f"{n}: {self.notes.get(n, {}).get('why', 'not given')}" for n in missing)
            raise Refused(
                f"venue {self.venue_id!r} (class {self.instrument_class!r}): {what} needs {missing}, which "
                f"are UNKNOWN — an unknown cost is not zero. [{why}] Supply sourced values with "
                f"spec.with_overrides(...)."
            )

    def with_overrides(self, **values) -> "VenueSpec":
        """A copy with some fields set by hand; each is recorded in `notes` as status 'override'
        (it did not come from the venue file — say in the report where it did come from)."""
        bad = [k for k in values if k not in COST_FIELDS + ("funded",)]
        if bad:
            raise Refused(f"unknown VenueSpec field(s) {bad}")
        notes = dict(self.notes)
        for k, v in values.items():
            notes[k] = {"status": "override", "value": v, "was": getattr(self, k)}
        return replace(self, notes=notes, **values)

    # ---- loading
    @classmethod
    def from_json(cls, path, venue_id: str, *, instrument_class: Union[str, Sequence[str], None] = None,
                  currency: Optional[str] = "EUR") -> "VenueSpec":
        """Read one venue from `landscape/venues.json`, tolerant of nulls, "UNKNOWN" and free text.

        path              the JSON file. Accepted layouts: {"venues": [ {...}, ... ]} (each with a
                          "venue_id" / "id"), {"venues": {id: {...}}}, {id: {...}}, or a bare list.
        venue_id          which venue.
        instrument_class  key (or keys, tried in order) used when a field is an object keyed by
                          instrument class or symbol, e.g. ("fx_cfd_majors", "fx_cfd", "fx_cfd_major").
        currency          the simulation currency. An amount quoted in another currency is UNKNOWN
                          (no conversion is attempted); a currency-keyed object is read at this key.

        Field lookup (first key present wins): fee_bp <- fee_bp | fee_bp_taker; min_fee <- min_fee |
        min_fee_per_order; half_spread_bp <- half_spread_bp | typical_half_spread_bp; lot_step;
        min_notional <- min_notional | min_order_notional; contract_notional <- contract_notional |
        contract_multiplier; financing_*_bp_year (a number, or an object's "markup_bp");
        leverage_cap <- leverage_cap | leverage_caps; cash_interest_bp_year; cash_interest_threshold;
        funded (a JSON boolean).
        A value resolves to a number only if it IS one (or a numeric string, or reachable through
        the class key / "value" / "amount" / "markup_bp" / the currency key). null, "UNKNOWN", prose
        and anything else become None, with the reason kept in `notes[field]["why"]`. Nothing is
        ever defaulted: a spec loaded from a sparse file refuses to simulate until its gaps are
        filled explicitly.
        """
        path = pathlib.Path(path)
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise Refused(f"cannot read venue file {path}: {exc}") from exc
        venues = doc.get("venues", doc) if isinstance(doc, dict) else doc
        entry = None
        if isinstance(venues, dict):
            entry = venues.get(venue_id)
        elif isinstance(venues, list):
            for item in venues:
                if isinstance(item, dict) and venue_id in (item.get("venue_id"), item.get("id")):
                    entry = item
                    break
        if not isinstance(entry, dict):
            known = sorted(venues) if isinstance(venues, dict) else \
                [str(i.get("venue_id", i.get("id"))) for i in venues if isinstance(i, dict)] if isinstance(venues, list) else []
            raise Refused(f"venue {venue_id!r} not found in {path}; known: {known}")
        if instrument_class is None:
            class_keys: Tuple[str, ...] = ()
        elif isinstance(instrument_class, str):
            class_keys = (instrument_class,)
        else:
            class_keys = tuple(instrument_class)
        values: Dict[str, Optional[float]] = {}
        notes: Dict[str, dict] = {}
        for name in COST_FIELDS:
            key = next((k for k in JSON_KEYS[name] if k in entry), None)
            if key is None:
                values[name], notes[name] = None, {"status": "unknown", "why": f"no key {JSON_KEYS[name]} in the venue entry"}
                continue
            value, why = _resolve(entry[key], class_keys, currency)
            if value is not None and value < 0:
                value, why = None, f"negative value {value!r}"
            if name in ("leverage_cap", "contract_notional") and value is not None and value <= 0:
                value, why = None, f"non-positive value {value!r}"
            values[name] = value
            notes[name] = {"status": "ok" if value is not None else "unknown", "json_key": key, "why": why,
                           "raw": json.dumps(entry[key])[:200]}
        funded_raw = entry.get("funded")
        funded = funded_raw if isinstance(funded_raw, bool) else None
        notes["funded"] = {"status": "ok" if funded is not None else "unknown",
                           "why": "boolean" if funded is not None else "no boolean 'funded' key in the venue entry"}
        return cls(venue_id=str(venue_id), instrument_class=class_keys[0] if class_keys else None, currency=currency,
                   funded=funded, notes=notes, **values)


# --------------------------------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------------------------------
@dataclass
class AccountResult:
    """Outcome of `simulate_account`. Every Series / DataFrame shares the panel index.

    equity         account value after the trading costs of each print (currency; excess-return account)
    net            per-print time-weighted return, booked like the engine: E_mark[t] / E_pre[t-1] - 1
    gross          per-print return before fees, spread and financing: (price P&L + carry) / E_pre[t-1]
    units          units held AFTER the trade of each print
    held           realised exposure in force over (t-1, t]: start notional / E_pre[t-1] (cf. engine `held`);
                   it DRIFTS between trades
    gross_leverage SUM_i |held[t, i]|
    flows          per print, currency: price_pnl, carry, financing, fees, spread, contribution
                   (+ cash_yield when report_total) — equity[t] - equity[t-1] is their signed sum
    turnover       traded notional / pre-trade equity, at the print of the trade
    cost_breakdown totals in currency {fees, spread, financing, carry (signed income), price_pnl,
                   contributions} and the frictions in bp per year of average equity
    tracking       {tracking_error_ann, mean_gap_ann, corr, n_obs}: sim net minus the ideal net
    ideal_net      the frictionless `engine.backtest` net it was compared with
    meta           counts (orders, skips, rounding, caps), the venue fields used, the conventions
    """

    equity: pd.Series
    net: pd.Series
    gross: pd.Series
    units: pd.DataFrame
    held: pd.DataFrame
    gross_leverage: pd.Series
    flows: pd.DataFrame
    turnover: pd.Series
    cost_breakdown: dict
    tracking: dict
    ideal_net: pd.Series
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------------------------------
# The simulator
# --------------------------------------------------------------------------------------------------
def _per_instrument(venue, cols: list) -> List[VenueSpec]:
    if isinstance(venue, VenueSpec):
        return [venue] * len(cols)
    if isinstance(venue, Mapping):
        missing = [c for c in cols if c not in venue]
        if missing:
            raise Refused(f"venue mapping has no VenueSpec for instruments {missing}")
        specs = [venue[c] for c in cols]
        if not all(isinstance(s, VenueSpec) for s in specs):
            raise Refused("venue mapping values must be VenueSpec objects")
        return specs
    raise Refused(f"venue must be a VenueSpec or a mapping instrument -> VenueSpec; got {type(venue).__name__}")


def simulate_account(
    panel: PanelBundle,
    w: pd.DataFrame,
    *,
    equity0: float,
    venue: Union[VenueSpec, Mapping[str, VenueSpec]],
    monthly_contribution: float = 0.0,
    lag: int = 1,
    exec_prices: Optional[pd.DataFrame] = None,
    extra_lag: int = 0,
    missing_return: str = "refuse",
    rebalance_mask: Optional[pd.Series] = None,
    no_trade_band: float = 0.0,
    ideal_net: Optional[pd.Series] = None,
    window: Window = None,
    report_total: bool = False,
) -> AccountResult:
    """Run target fractions `w` through an account that holds UNITS (module docstring for the loop).

    panel, w, lag, exec_prices, extra_lag   exactly as `engine.backtest` (same timing refusals): the
                          target decided at row s can be traded at row s + lag, or on the exec print
                          of row s + extra_lag.
    equity0               starting equity, currency units (> 0).
    venue                 one `VenueSpec` for every instrument, or a mapping instrument -> VenueSpec.
                          `VenueSpec.ideal()` = the frictionless reference.
    monthly_contribution  cash added on the first print of each calendar month after row 0 (>= 0).
    missing_return        "refuse": a held position with no price / carry on a print raises.
                          "zero": it is carried at its last valid price (counted in meta).
    rebalance_mask        boolean Series on the panel index: the account may trade only on True rows
                          (TRADE rows: on a True row t it trades towards w[t - delay]). None = every
                          print is a trade row. Between trade rows units are untouched and DRIFT.
    no_trade_band         on a trade row, instrument i is left alone when
                          |target weight - current weight| <= no_trade_band * max(|target weight|, 1e-4);
                          otherwise it is traded to the target. 0.0 (default) = always re-balance.
    ideal_net             the per-print net to track against; None = `engine.backtest(w)` at ZERO cost
                          and zero hold cost (re-balanced on every print — pass your own reference
                          for a scheduled book).
    window                (start, end) over which tracking error and the bp-per-year costs are
                          computed (None = all rows), as `stats.summarize`.
    report_total          also report the venue's cash yield (needs cash_interest_bp_year,
                          cash_interest_threshold and `funded` on every spec).

    Returns an `AccountResult`. Raises `Refused` on an unknown venue field the run depends on.
    """
    if not isinstance(panel, PanelBundle):
        raise Refused(f"panel must be a PanelBundle; got {type(panel).__name__}")
    if missing_return not in ("refuse", "zero"):
        raise Refused(f"missing_return must be 'refuse' or 'zero'; got {missing_return!r}")
    for name, value, low_ok in (("equity0", equity0, False), ("monthly_contribution", monthly_contribution, True),
                                ("no_trade_band", no_trade_band, True)):
        if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)) \
                or not math.isfinite(value) or value < 0 or (value == 0 and not low_ok):
            raise Refused(f"{name} must be a finite number {'>= 0' if low_ok else '> 0'}; got {value!r}")
    cols = list(panel.prices.columns)
    idx = panel.prices.index
    T, N = len(idx), len(cols)
    shift = resolve_shift(panel, lag, extra_lag, exec_prices)
    delay = shift - 1
    W = validate_weights(w, panel)
    W = np.where(np.isnan(W), 0.0, W)
    dec_px = validate_prices(panel.prices, "panel.prices")
    X = dec_px if exec_prices is None else aligned_exec_prices(panel, exec_prices)
    C = None if panel.carry is None else panel.carry[cols].to_numpy(dtype=np.float64)
    if rebalance_mask is None:
        trade_row = np.ones(T, dtype=bool)
    else:
        if not isinstance(rebalance_mask, pd.Series) or not rebalance_mask.index.equals(idx):
            raise Refused("rebalance_mask must be a boolean Series on the panel index")
        if rebalance_mask.dtype != bool:
            raise Refused(f"rebalance_mask must have dtype bool (no NaN); got {rebalance_mask.dtype}")
        trade_row = rebalance_mask.to_numpy(dtype=bool)

    specs = _per_instrument(venue, cols)
    ever_long = (W > 0).any(axis=0)
    ever_short = (W < 0).any(axis=0)
    for j, spec in enumerate(specs):
        need = list(ALWAYS_REQUIRED)
        if ever_long[j]:
            need.append("financing_long_bp_year")
        if ever_short[j]:
            need.append("financing_short_bp_year")
        if report_total:
            need += ["cash_interest_bp_year", "cash_interest_threshold", "funded"]
        spec.require(need, what=f"simulating {cols[j]!r}")

    def arr(name: str, scale: float = 1.0) -> np.ndarray:
        return np.array([(getattr(s, name) or 0.0) * scale for s in specs], dtype=np.float64)

    fee_frac, min_fee, hs_frac = arr("fee_bp", 1e-4), arr("min_fee"), arr("half_spread_bp", 1e-4)
    lot, min_notional, mult, cap = arr("lot_step"), arr("min_notional"), arr("contract_notional"), arr("leverage_cap")
    fin_long, fin_short = arr("financing_long_bp_year", 1e-4), arr("financing_short_bp_year", 1e-4)   # ANNUAL fractions
    funded = np.array([bool(s.funded) for s in specs])
    cash_rate = cash_floor = 0.0
    if report_total:
        terms = {(s.cash_interest_bp_year, s.cash_interest_threshold) for s in specs}
        if len(terms) != 1:
            raise Refused(f"one account has one cash rate; the instruments' VenueSpecs disagree: {sorted(terms)}")
        rate_bp, cash_floor = terms.pop()
        cash_rate = rate_bp / 1e4                                       # annual fraction
    tbill = panel.tbill.to_numpy(dtype=np.float64)
    months = idx.year.to_numpy() * 12 + idx.month.to_numpy()
    year_frac = calendar_days(idx) / DAYS_PER_YEAR

    units = np.zeros(N)
    mark = np.full(N, np.nan)                         # last valid execution price per instrument
    equity = float(equity0)
    e_pre_prev = float("nan")
    idle_prev = 0.0                                   # interest-bearing cash after the previous print (report_total)
    funded_long_prev = 0.0                            # funded long notional after the previous print (report_total)

    out_equity, out_net, out_gross = np.zeros(T), np.zeros(T), np.zeros(T)
    out_turn, out_traded, margin_use = np.zeros(T), np.zeros(T), np.zeros(T)
    out_units, out_held = np.zeros((T, N)), np.zeros((T, N))
    flows = {k: np.zeros(T) for k in ("price_pnl", "carry", "financing", "fees", "spread", "contribution", "cash_yield")}
    counts = {"n_orders": 0, "n_orders_at_min_fee": 0, "n_orders_skipped_min_notional": 0,
              "n_orders_skipped_no_price": 0, "n_trades_skipped_in_band": 0, "n_targets_rounded_to_zero": 0,
              "n_prints_leverage_capped": 0, "n_prints_over_cap": 0, "n_missing_price_held": 0,
              "n_missing_carry_held": 0, "n_trade_rows": 0}
    rounded_by_instrument = np.zeros(N, dtype=np.int64)
    ruined_at: Optional[int] = None

    for t in range(T):
        x = X[t]
        valid = ~np.isnan(x)
        # ---- 1. earn (t-1, t] on the units held since print t-1
        if t >= 1:
            held_now = units != 0.0
            if held_now.any():
                start = np.where(held_now, units * mult * mark, 0.0)
                miss = held_now & ~valid
                if miss.any():
                    if missing_return == "refuse":
                        j = int(np.flatnonzero(miss)[0])
                        raise Refused(f"held {cols[j]!r} has no price at {idx[t]}; pass missing_return='zero' to "
                                      f"carry it at its last price and report the count")
                    counts["n_missing_price_held"] += int(miss.sum())
                ok = held_now & valid
                flows["price_pnl"][t] = float((units[ok] * mult[ok] * (x[ok] - mark[ok])).sum())
                if C is not None:
                    c = C[t]
                    no_c = held_now & np.isnan(c)
                    if no_c.any():
                        if missing_return == "refuse":
                            j = int(np.flatnonzero(no_c)[0])
                            raise Refused(f"held {cols[j]!r} has no carry at {idx[t]}")
                        counts["n_missing_carry_held"] += int(no_c.sum())
                    has_c = held_now & ~np.isnan(c)
                    flows["carry"][t] = float((start[has_c] * c[has_c]).sum())
                flows["financing"][t] = float(
                    (np.maximum(start, 0.0) * fin_long + np.maximum(-start, 0.0) * fin_short).sum()) * year_frac[t]
                if e_pre_prev > 0:
                    out_held[t] = start / e_pre_prev
            if report_total:
                # interest on idle cash above the threshold, plus the risk-free leg the carry panel charged a
                # FUNDED long position (it was bought with cash: the holder does not actually pay r_f on it)
                flows["cash_yield"][t] = max(idle_prev - cash_floor, 0.0) * cash_rate * year_frac[t] \
                    + funded_long_prev * tbill[t]
            equity += flows["price_pnl"][t] + flows["carry"][t] - flows["financing"][t]
            if ruined_at is None and e_pre_prev > 0:
                out_net[t] = equity / e_pre_prev - 1.0
                out_gross[t] = (flows["price_pnl"][t] + flows["carry"][t]) / e_pre_prev
        mark = np.where(valid, x, mark)
        # ---- 2. contribute
        if t >= 1 and monthly_contribution > 0 and months[t] != months[t - 1] and ruined_at is None:
            flows["contribution"][t] = float(monthly_contribution)
            equity += float(monthly_contribution)
        e_pre = equity
        if ruined_at is None and e_pre <= 0.0:
            ruined_at = t
            units = np.zeros(N)
        # ---- 3. trade towards the target decided `delay` prints ago — only on a trade row
        s = t - delay
        traded_notional = 0.0
        if s >= 0 and trade_row[t] and ruined_at is None:
            counts["n_trade_rows"] += 1
            f = W[s]
            current = np.where(units != 0.0, units * mult * mark, 0.0)        # mark == x wherever x is valid
            off_target = np.abs(f - current / e_pre) > no_trade_band * np.maximum(np.abs(f), NO_TRADE_FLOOR)
            want = off_target if no_trade_band > 0 else (f * e_pre != current)
            counts["n_trades_skipped_in_band"] += int(((f * e_pre != current) & ~want).sum())
            counts["n_orders_skipped_no_price"] += int((want & ~valid).sum())
            go = want & valid
            if go.any():
                desired = np.where(go, f * e_pre, current)
                need_fixed = float((np.abs(current[~go]) / cap[~go]).sum())
                need_trade = float((np.abs(desired[go]) / cap[go]).sum())
                if need_fixed + need_trade > e_pre * (1.0 + 1e-12) and need_trade > 0:
                    desired[go] *= max(0.0, (e_pre - need_fixed) / need_trade)
                    counts["n_prints_leverage_capped"] += 1
                for j in np.flatnonzero(go):
                    raw_units = desired[j] / (mult[j] * x[j])
                    if lot[j] > 0:
                        new_units = math.copysign(math.floor(abs(raw_units) / lot[j] + 1e-9) * lot[j], raw_units)
                        if new_units == 0.0:
                            new_units = 0.0                              # no negative zero
                        if raw_units != 0.0 and new_units == 0.0:
                            counts["n_targets_rounded_to_zero"] += 1
                            rounded_by_instrument[j] += 1
                    else:
                        new_units = raw_units
                    order = new_units - units[j]
                    notional = abs(order) * mult[j] * x[j]
                    if notional <= DUST * e_pre:
                        continue                                         # nothing to do (or float dust)
                    if notional < min_notional[j] and new_units != 0.0:
                        counts["n_orders_skipped_min_notional"] += 1
                        continue
                    pct_fee = fee_frac[j] * notional
                    fee = max(min_fee[j], pct_fee)
                    counts["n_orders"] += 1
                    counts["n_orders_at_min_fee"] += int(min_fee[j] > pct_fee)
                    flows["fees"][t] += fee
                    flows["spread"][t] += hs_frac[j] * notional
                    traded_notional += notional
                    units[j] = new_units
                equity -= flows["fees"][t] + flows["spread"][t]
        # ---- 4. record
        position = np.where(units != 0.0, units * mult * mark, 0.0)
        out_traded[t] = traded_notional
        if e_pre > 0:
            out_turn[t] = traded_notional / e_pre
            margin_use[t] = float((np.abs(position) / cap).sum()) / e_pre
            counts["n_prints_over_cap"] += int(margin_use[t] > 1.0 + 1e-9)
        if report_total:
            funded_long_prev = float((np.maximum(position, 0.0) * funded).sum())
            idle_prev = equity - funded_long_prev
        out_equity[t] = equity
        out_units[t] = units
        e_pre_prev = e_pre

    ppy = float(panel.periods_per_year)
    net = pd.Series(out_net, index=idx, name="net")
    if ideal_net is None:
        # cost is zero, so the turnover model cannot change this net; "target" only avoids the drift model's
        # refusal of a book that loses 100 % in one print — the account below handles that itself (`ruined_at`).
        ideal = backtest(panel, w, lag=lag, cost_bp_side=0.0, hold_cost_long_bp_year=0.0, hold_cost_short_bp_year=0.0,
                         exec_prices=exec_prices, extra_lag=extra_lag, missing_return=missing_return,
                         turnover_model="target").net
        ideal_source = "engine.backtest(w) at zero cost (frictionless, re-balanced on every print)"
    else:
        if not isinstance(ideal_net, pd.Series) or not ideal_net.index.equals(idx):
            raise Refused("ideal_net must be a Series on the panel index")
        ideal = ideal_net.astype(np.float64)
        ideal_source = "supplied by the caller"
    mask = window_mask(idx, window)
    n_win = int(mask.sum())
    gap = (net - ideal).to_numpy()[mask]
    net_w, ideal_w = net.to_numpy()[mask], ideal.to_numpy()[mask]
    tracking = {
        "tracking_error_ann": float(gap.std(ddof=1) * math.sqrt(ppy)) if n_win > 1 else float("nan"),
        "mean_gap_ann": float(gap.mean() * ppy) if n_win else float("nan"),
        "corr": float(np.corrcoef(net_w, ideal_w)[0, 1]) if n_win > 2 and net_w.std() > 0 and ideal_w.std() > 0
        else float("nan"),
        "n_obs": n_win,
        "ideal": ideal_source,
    }
    years = float(year_frac[mask].sum()) if n_win else float("nan")       # calendar years inside the window
    avg_equity = float(out_equity[mask].mean()) if n_win else float("nan")

    def bp_year(total: float) -> float:
        return float(1e4 * total / avg_equity / years) if n_win and avg_equity > 0 and years > 0 else float("nan")

    totals = {k: float(v[mask].sum()) for k, v in flows.items()}
    traded_ccy = float(out_traded[mask].sum())
    cost_breakdown = {
        "fees": totals["fees"], "spread": totals["spread"], "financing": totals["financing"],
        "carry": totals["carry"], "price_pnl": totals["price_pnl"], "contributions": totals["contribution"],
        "fees_bp_year": bp_year(totals["fees"]), "spread_bp_year": bp_year(totals["spread"]),
        "financing_bp_year": bp_year(totals["financing"]), "carry_bp_year": bp_year(totals["carry"]),
        "frictions_bp_year": bp_year(totals["fees"] + totals["spread"] + totals["financing"]),
        "traded_notional": traded_ccy,
        "fees_bp_of_traded_notional": float(1e4 * totals["fees"] / traded_ccy) if traded_ccy > 0 else float("nan"),
        "turnover_sides_per_year": float(out_turn[mask].sum() / years) if n_win and years > 0 else float("nan"),
        "avg_equity": avg_equity,
        "calendar_years": years,
    }
    if report_total:
        cost_breakdown["cash_yield"] = totals["cash_yield"]
        cost_breakdown["cash_yield_bp_year"] = bp_year(totals["cash_yield"])
    flow_frame = pd.DataFrame({k: v for k, v in flows.items() if k != "cash_yield" or report_total}, index=idx)
    meta = dict(counts)
    meta.update({
        "equity0": float(equity0), "final_equity": float(out_equity[-1]) if T else float(equity0),
        "monthly_contribution": float(monthly_contribution),
        "rebalance_mask": "every print" if rebalance_mask is None else f"{int(trade_row.sum())} trade rows of {T}",
        "no_trade_band": float(no_trade_band),
        "priced_on": "prices" if exec_prices is None else "exec_prices", "shift": int(shift), "delay": int(delay),
        "missing_return_policy": missing_return, "periods_per_year": ppy,
        "financing_day_count": "ACT/365 on the UTC calendar dates of the panel index",
        "ruined_at": None if ruined_at is None else idx[ruined_at].isoformat(),
        "max_margin_utilisation": float(margin_use.max()) if T else 0.0,
        "targets_rounded_to_zero_by_instrument": {str(c): int(n) for c, n in zip(cols, rounded_by_instrument) if n},
        "venue": {str(c): {"venue_id": s.venue_id, "instrument_class": s.instrument_class,
                           "overridden": sorted(k for k, v in s.notes.items() if v.get("status") == "override"),
                           **{f.name: (None if getattr(s, f.name) is None else
                                       ("inf" if getattr(s, f.name) == math.inf else getattr(s, f.name)))
                              for f in fields(s) if f.name in COST_FIELDS + ("funded",)}}
                  for c, s in zip(cols, specs)},
        "report_total": bool(report_total),
        "currency_note": "single currency; no FX conversion is modelled",
    })
    held_frame = pd.DataFrame(out_held, index=idx, columns=cols)
    return AccountResult(
        equity=pd.Series(out_equity, index=idx, name="equity"),
        net=net,
        gross=pd.Series(out_gross, index=idx, name="gross"),
        units=pd.DataFrame(out_units, index=idx, columns=cols),
        held=held_frame,
        gross_leverage=held_frame.abs().sum(axis=1).rename("gross_leverage"),
        flows=flow_frame,
        turnover=pd.Series(out_turn, index=idx, name="turnover"),
        cost_breakdown=cost_breakdown,
        tracking=tracking,
        ideal_net=ideal.rename("ideal_net"),
        meta=meta,
    )


__all__ = ["VenueSpec", "AccountResult", "simulate_account", "COST_FIELDS", "ALWAYS_REQUIRED", "JSON_KEYS",
           "NO_TRADE_FLOOR", "DUST"]
