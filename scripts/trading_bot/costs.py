#!/usr/bin/env python3
"""The cost model. Every component carries a PROVENANCE, and an unsourced number refuses.

THE RULE THIS PROGRAMME LEARNED THE EXPENSIVE WAY
--------------------------------------------------
Five domains have now died at the friction floor (memecoins, Binance, MNQ futures,
individual equities, and -- differently -- intraday momentum). The single most common way
a backtest lies is a cost that was assumed rather than measured, and the single most common
shape of that lie is a ZERO where a measurement is missing.

So this module inverts the default. **There is no default cost.** Every component must be
constructed with an explicit `SlippageProvenance`, and the provenance vocabulary makes the
difference between "we measured this" and "we read this in a paper" impossible to blur in
the report. `Refused` is raised for an absent input; it is never coerced to zero.

WHAT IS AND IS NOT AVAILABLE TODAY
----------------------------------
`MEASURED_B22B` is the provenance that carries a slippage magnitude measured by this
programme. **As of 2026-08-16 it is obtainable**: the B22B evaluation pass ran over the
pinned 30-day 2025 sample and its result is on disk at `research/B22B_SLIPPAGE_RESULT.json`.
`assert_available()` is now a GATE ON THAT FILE rather than a flat refusal -- if the artifact
is missing or does not cover the pinned sample, the provenance refuses again. The rule is
unchanged: a number may call itself a measurement only while the measurement exists.

`VENDOR_FEED_SNAPSHOT` is the borrow-cost provenance added alongside it. B22G pulled per-name
short-borrow status from the Alpaca account this programme would trade in, and per-name
indicative borrow fees from Interactive Brokers' shortable-securities feed. That is a
point-in-time snapshot of somebody else's published feed -- stronger than a paper's
assumption, weaker than our own controlled measurement -- so it gets its own name rather than
being filed under either neighbour. Result: `research/B22G_BORROW_COST.json`.

ARITHMETIC
----------
Prices are integer micro-dollars, from the frozen B22B `to_micros`. Cost RATES are exact
`Fraction`s, so a cost applied to an exact price stays exact. There is no float here.

SIGN CONVENTION, inherited from B22B
------------------------------------
Positive is always ADVERSE. Every function in this module returns a non-negative charge
against equity. A sign error is precisely how a favourable result gets manufactured, so it
is asserted rather than trusted: `assert_non_negative` guards every return.

COSTS ARE PER SIDE, AND THAT IS A CORRECTION (T6, 2026-08-17)
-------------------------------------------------------------
An earlier version of this module carried ONE spread/slippage term and the engine charged it on
`|target - held|`, side-agnostically. Combined with `b22b_measured_costs()`, whose half-spread is
legitimately ZERO because the B22B entry measurement already contains it, that meant **every EXIT
leg was charged the entry's number and no spread at all** -- and B22B measured entries only. The
exits of the rule it prices are a stop-loss market order and a market-on-close, neither of which
anybody has measured, and both of which cross the spread. The model was therefore ~3.4x cheaper
than its own honest lower bound, in the strategy's favour.

So there is no longer a single spread/slippage number. `entry_*` and `exit_*` are separate
components, the engine decomposes each position change into the part that OPENS exposure and the
part that CLOSES it (`split_turnover`), and each part is charged its own side. An unstated exit
side is a `Refused`, never a zero -- the same rule the rest of this module already lived by, now
applied to the leg that was quietly getting it for free.
"""

from __future__ import annotations

import enum
import json
import pathlib
from dataclasses import dataclass
from fractions import Fraction

from .frozen import MICROS, Refused

BP = Fraction(1, 10_000)
CALENDAR_DAYS_PER_YEAR = 365

_RESEARCH = pathlib.Path(__file__).resolve().parents[2] / "research"
B22B_RESULT_PATH = _RESEARCH / "B22B_SLIPPAGE_RESULT.json"
B22G_BORROW_PATH = _RESEARCH / "B22G_BORROW_COST.json"
M0_RESULT_PATH = _RESEARCH / "trading_bot" / "M0_AUCTION_FILLS.json"
T18_RESULT_PATH = _RESEARCH / "trading_bot" / "T18_EXIT_MEASUREMENT.json"

# T18 measured the EXIT leg -- the half of the round trip B22B is frozen out of -- on a pinned
# 50-session sample of the stock-days T17's held-out run actually traded. A result carrying
# fewer stop exits than this is a partial pass, and a partial pass reporting itself as "the
# measurement" is the failure this module exists to make visible.
T18_MIN_STOP_EXITS = 300

# M0 measured 5,670 symbol-days over 65 full sessions, six ADV tiers. A result covering fewer is
# a partial run; the auction-rail claim is a claim about a whole liquidity ladder and a truncated
# ladder cannot support it.
M0_MIN_SYMBOL_DAYS = 5_000

# The ADV-rank tiers M0 measured, and the only ones a zero-spread auction charge may be claimed
# for. `close_print_rate` inside the result file is the gate; these names index it.
M0_LIQUID_TIERS = ("A_rank_1_50", "B_rank_51_200", "C_rank_201_500", "D_rank_501_1500")

# The pinned sample is 30 days. A result covering fewer is a partial run, and a partial run
# reporting itself as "the measurement" is exactly the failure the checkpointed runner exists
# to make visible rather than hide.
B22B_PINNED_SAMPLE_DAYS = 30


def _load_json(path: pathlib.Path, what: str) -> dict:
    if not path.exists():
        raise Refused(f"{what} is absent at {path}; absence is refusal, never zero")
    return json.loads(path.read_text())


class SlippageProvenance(enum.Enum):
    """Where a cost number came from. The report prints this next to every number."""

    MEASURED_B22B = "measured by this programme via the pinned B22B harness"
    VENDOR_FEED_SNAPSHOT = "a point-in-time snapshot this programme pulled from a named feed"
    PUBLISHED_PAPER = "taken from a named paper's own stated cost assumption"
    PUBLISHED_ACADEMIC_MEASUREMENT = "a peer-reviewed measurement of someone else's orders"
    BROKER_SCHEDULE = "a published broker fee schedule"
    STRESS_LADDER = "not a measurement; a deliberately adverse rung in a sweep"
    EXCHANGE_MECHANISM_UNVERIFIED_FILL = (
        "NOT a measurement and NOT an assumption about size: a structural property of the "
        "venue's matching mechanism -- a single-price call auction clears every participant at "
        "one price, so there is no bid-ask to cross. It is legitimate ONLY while the order is "
        "actually filled AT that print. M0 (research/trading_bot/M0_AUCTION_FILLS.md) has now "
        "measured the two halves of that condition that a tape can answer -- an official print "
        "EXISTS, and it is LARGE -- but not the half that needs live orders, namely that OUR "
        "order is the one that clears in it. Any component carrying this provenance must still "
        "be accompanied by a stress rung charging a real half-spread on the same leg. Prefer "
        "MEASURED_M0_AUCTION_PRINT, which carries the measured domain of validity with it."
    )
    MEASURED_M0_AUCTION_PRINT = (
        "measured by this programme's M0 auction pass: an official auction print exists on "
        "99.96% of symbol-days in the top-500-ADV universe and clears a median $37 M at the "
        "close, so a small order's quoted-spread charge in that auction is zero. The residual "
        "-- that the broker's on-close/on-open order actually joins that cross -- is a LIVE "
        "measurement this provenance does not claim"
    )
    ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG = (
        "NOT a measurement of this leg. A deliberately adverse stand-in, carried across from a "
        "leg that WAS measured, for a leg nobody has measured yet"
    )
    MEASURED_T18_EXIT = (
        "measured by this programme's T18 tick pass: the EXIT leg of the ORB rule priced from "
        "SIP trades and quotes on a pinned sample of the stock-days T17's held-out run actually "
        "traded -- a stop-loss market order's realised NBBO fill against the stop level it "
        "triggered on, and a market-on-close's realised official closing print against the "
        "last-bar mark a backtest credits. This is the leg "
        "ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG stood in for; where this provenance is available "
        "it REPLACES that proxy rather than accompanying it. Like the B22B entry number it runs "
        "from a traded level to the far side of the book and therefore ALREADY CONTAINS the "
        "half-spread: never add one on top of it"
    )

    def assert_available(self) -> None:
        """A provenance is available only while the artifact backing it exists AND covers the
        sample it claims. This used to be an unconditional refusal for MEASURED_B22B because
        B22B had never been run; it is now a gate on the result file, so deleting or truncating
        that file returns the rig to refusing rather than silently keeping the label."""
        if self is SlippageProvenance.MEASURED_B22B:
            if not B22B_RESULT_PATH.exists():
                raise Refused(
                    "SlippageProvenance.MEASURED_B22B claims a measurement, but "
                    f"{B22B_RESULT_PATH} does not exist. Use PUBLISHED_PAPER, "
                    "PUBLISHED_ACADEMIC_MEASUREMENT, BROKER_SCHEDULE or STRESS_LADDER and say "
                    "so in the report -- do not label an assumption as a measurement."
                )
            result = json.loads(B22B_RESULT_PATH.read_text())
            complete = result.get("days_complete")
            if complete != B22B_PINNED_SAMPLE_DAYS:
                raise Refused(
                    f"{B22B_RESULT_PATH} covers {complete} of the {B22B_PINNED_SAMPLE_DAYS} "
                    "pinned days. A partial pass is not the measurement; finish the run or "
                    "use a different provenance."
                )
        if self is SlippageProvenance.MEASURED_M0_AUCTION_PRINT:
            if not M0_RESULT_PATH.exists():
                raise Refused(
                    "SlippageProvenance.MEASURED_M0_AUCTION_PRINT claims a measurement, but "
                    f"{M0_RESULT_PATH} does not exist. Use EXCHANGE_MECHANISM_UNVERIFIED_FILL "
                    "and say M0 is outstanding -- do not label an assumption as a measurement."
                )
            result = json.loads(M0_RESULT_PATH.read_text())
            n = (result.get("all") or {}).get("symbol_days")
            if not n or n < M0_MIN_SYMBOL_DAYS:
                raise Refused(
                    f"{M0_RESULT_PATH} covers {n} symbol-days against the {M0_MIN_SYMBOL_DAYS} "
                    "the auction-rail claim was measured over. A partial pass is not the "
                    "measurement."
                )
        if self is SlippageProvenance.MEASURED_T18_EXIT:
            if not T18_RESULT_PATH.exists():
                raise Refused(
                    "SlippageProvenance.MEASURED_T18_EXIT claims a measurement, but "
                    f"{T18_RESULT_PATH} does not exist. Use "
                    "ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG and say the exit is unmeasured -- do "
                    "not label a stand-in as a measurement."
                )
            result = json.loads(T18_RESULT_PATH.read_text())
            n = (((result.get("exit_stop_leg") or {}).get("100") or {})
                 .get("r_bp") or {}).get("n")
            if not n or n < T18_MIN_STOP_EXITS:
                raise Refused(
                    f"{T18_RESULT_PATH} carries {n} measured stop exits against the "
                    f"{T18_MIN_STOP_EXITS} the exit claim is made over. A partial pass is not "
                    "the measurement."
                )
        if self is SlippageProvenance.VENDOR_FEED_SNAPSHOT and not B22G_BORROW_PATH.exists():
            raise Refused(
                "SlippageProvenance.VENDOR_FEED_SNAPSHOT claims a pulled feed, but "
                f"{B22G_BORROW_PATH} does not exist."
            )


def assert_non_negative(charge: Fraction, what: str) -> Fraction:
    """Guard the adverse-sign convention. A cost that came out negative is a bug, not a rebate."""
    if charge < 0:
        raise Refused(
            f"{what} produced a NEGATIVE charge ({charge}). Positive is always adverse in this "
            "programme; a negative cost means a sign error, and a sign error is how a "
            "favourable result gets manufactured."
        )
    return charge


def _rate(value, what: str) -> Fraction:
    if value is None:
        raise Refused(f"{what} is absent; refusing to substitute zero (undefined is not zero)")
    rate = Fraction(value)
    if rate < 0:
        raise Refused(f"{what} must be non-negative under the adverse-sign convention; got {rate}")
    return rate


@dataclass(frozen=True)
class CostComponent:
    """One priced friction, with the reason it holds that value attached to it."""

    name: str
    value: Fraction
    unit: str
    provenance: SlippageProvenance
    source: str

    def __post_init__(self) -> None:
        if not self.source or not self.source.strip():
            raise Refused(
                f"cost component {self.name!r} has no source string. A number with no citation "
                "is an assumption wearing a measurement's clothes."
            )
        self.provenance.assert_available()

    def to_report(self) -> dict:
        return {
            "name": self.name,
            "value": str(self.value),
            "value_float": float(self.value),
            "unit": self.unit,
            "provenance": self.provenance.name,
            "provenance_meaning": self.provenance.value,
            "source": self.source,
        }


def split_turnover(previous: Fraction, target: Fraction) -> tuple:
    """Decompose a position change into (ENTRY turnover, EXIT turnover). Exact, and it sums.

    A signed position change hides two economically different trades. Going +1.0 -> -1.0 is not
    "2.0 of turnover"; it is a 1.0 EXIT (sell to flat) followed by a 1.0 ENTRY (sell short), and
    the two legs do not cost the same thing when only one of them has been measured. The retained
    part -- the same-signed overlap -- is not traded at all and must be charged nothing.

        overlap = min(|previous|, |target|) if they share a sign, else 0
        exit    = |previous| - overlap        (exposure closed)
        entry   = |target|   - overlap        (exposure opened)

    `entry + exit == |target - previous|` for every input, which is what makes this a
    reallocation of the old side-agnostic turnover rather than a new charge invented on top of
    it. That identity is asserted here rather than trusted, because a decomposition that quietly
    lost a leg would look exactly like the bug this function exists to fix.
    """
    previous, target = Fraction(previous), Fraction(target)
    same_sign = (previous > 0 and target > 0) or (previous < 0 and target < 0)
    overlap = min(abs(previous), abs(target)) if same_sign else Fraction(0)
    exit_turnover = abs(previous) - overlap
    entry_turnover = abs(target) - overlap
    if entry_turnover + exit_turnover != abs(target - previous):
        raise Refused(
            f"turnover decomposition lost a leg: entry {entry_turnover} + exit {exit_turnover} "
            f"!= |{target} - {previous}|. Refusing rather than charging a partial round trip."
        )
    if entry_turnover < 0 or exit_turnover < 0:
        raise Refused(f"negative turnover leg ({entry_turnover}, {exit_turnover})")
    return entry_turnover, exit_turnover


@dataclass(frozen=True)
class CostModel:
    """Commission + spread/slippage on every share traded, borrow on every short held.

    **EVERY SPREAD/SLIPPAGE TERM IS PER SIDE.** `entry_*` prices the leg that OPENS exposure,
    `exit_*` the leg that CLOSES it, and the engine splits each position change between them with
    `split_turnover`. There is no side-agnostic term any more, because there used to be one and
    it is what let an unmeasured exit inherit a measured entry's zero half-spread.

    `entry_half_spread` / `exit_half_spread`
        Charged on the traded notional of that side. This is the *taker* cost: a market or stop
        order crosses the spread. B22C establishes that what a retail taker actually pays is
        broker-dependent by up to 6.5x, and that a wholesaler-routed order receives price
        improvement on ~75% of marketable orders against ~12% at an exchange. This rig does not
        model price improvement -- charging the full half-spread is the conservative side of that
        uncertainty, and it is stated rather than hidden.

    `entry_extra_slippage` / `exit_extra_slippage`
        Impact and latency beyond the quoted half-spread. B22B measured this for ENTRIES ONLY.
        The exit term therefore cannot be a measurement, and it must not be a zero either: an
        exit that is a stop-loss market order is triggered BY the move that is going against the
        position, which is not a cheaper fill than the entry was. See `b22b_measured_costs`.

    `commission_micros_per_share`
        Per-share commission in micro-dollars. Zarattini/Barbon/Aziz model $0.0035/share
        and nothing else.

    `borrow_annual_rate`
        Stock-borrow fee for short exposure, accrued on notional per CALENDAR day -- borrow
        accrues over weekends and holidays, which is why it is not per trading day. Shorting
        is in this programme's mandate, so a rig that silently omitted borrow would flatter
        every short.

    **There is deliberately no `min_commission_micros`.** A per-order floor cannot be
    expressed in this accounting: costs here are fractions of equity, and the account size
    cancels out of every term (see `commission_fraction`), so a floor in dollars has nothing
    to be a floor *of*. An earlier draft carried the field, reported it, and never charged it
    -- a silent no-op that would have let an operator set a floor and see no effect. If a
    broker schedule with a per-order minimum ever matters, it needs a dollar-denominated
    account model, and that is a change to the engine, not a field on this dataclass.
    """

    entry_half_spread: CostComponent
    entry_extra_slippage: CostComponent
    commission_per_share: CostComponent
    borrow_annual: CostComponent
    exit_half_spread: CostComponent = None
    exit_extra_slippage: CostComponent = None

    def __post_init__(self) -> None:
        # The exit legs have a default in the SIGNATURE only so that the failure is a Refused
        # with an explanation rather than a bare TypeError. An absent exit side is refused:
        # this is the exact hole T6 closed, and a model constructed without one would silently
        # reopen it.
        for name in ("exit_half_spread", "exit_extra_slippage"):
            if getattr(self, name) is None:
                raise Refused(
                    f"CostModel is missing {name}. Spread and slippage are PER SIDE since T6: "
                    "the entry number cannot stand in for the exit, because B22B measured "
                    "entries only and the exits (stop-loss market, market-on-close) are "
                    "unmeasured AND cross the spread. State the exit side explicitly -- "
                    "absence is a refusal, never a zero."
                )

    # ---- per-trade friction -------------------------------------------------

    def spread_and_slippage_fraction(self) -> Fraction:
        """REMOVED. It was the bug: one number charged to both sides of a round trip."""
        raise Refused(
            "spread_and_slippage_fraction() no longer exists: a single side-agnostic "
            "spread/slippage number is what charged unmeasured EXIT legs the measured ENTRY's "
            "zero half-spread. Use entry_spread_and_slippage_fraction(), "
            "exit_spread_and_slippage_fraction(), or round_trip_bp()."
        )

    def entry_spread_and_slippage_fraction(self) -> Fraction:
        """Fraction of traded notional lost OPENING exposure: spread crossed plus impact."""
        total = (self.entry_half_spread.value + self.entry_extra_slippage.value) * BP
        return assert_non_negative(total, "entry_spread_and_slippage")

    def exit_spread_and_slippage_fraction(self) -> Fraction:
        """Fraction of traded notional lost CLOSING exposure: spread crossed plus impact."""
        total = (self.exit_half_spread.value + self.exit_extra_slippage.value) * BP
        return assert_non_negative(total, "exit_spread_and_slippage")

    def round_trip_bp(self) -> Fraction:
        """Total spread+slippage of one full round trip, in basis points of notional.

        Exact. This is the single number to quote when someone asks what the rig charges, and
        the reason it is a method rather than a docstring is that it cannot then drift away from
        what is actually charged.
        """
        total = (self.entry_half_spread.value + self.entry_extra_slippage.value
                 + self.exit_half_spread.value + self.exit_extra_slippage.value)
        return assert_non_negative(total, "round_trip")

    def commission_fraction(self, price_micros: int, notional_fraction: Fraction) -> Fraction:
        """Per-share commission expressed as a fraction of EQUITY.

        shares = notional_fraction * equity / price, so
        commission / equity = notional_fraction * per_share / price -- and the equity cancels,
        which is why this rig never needs a dollar account size to price commissions.
        """
        if price_micros is None:
            raise Refused("commission needs a price; absent price is a refusal, not a free fill")
        if price_micros <= 0:
            raise Refused(f"non-positive price {price_micros} micros cannot price a commission")
        charge = notional_fraction * self.commission_per_share.value / Fraction(price_micros)
        return assert_non_negative(charge, "commission")

    def trade_cost_fraction(self, price_micros: int, entry_turnover=None,
                            exit_turnover=None) -> Fraction:
        """Cost of a position change already SPLIT into its opening and closing legs.

        Both legs are required and neither defaults. The previous signature took one lumped
        `turnover` and charged one side-agnostic rate to it; a caller that still passes a single
        turnover lands on `exit_turnover=None` and is refused by name rather than being charged
        the cheaper of the two sides in silence.

        Use `split_turnover(previous, target)` to produce the pair. Commission is per SHARE and
        so is charged on the sum -- a broker does not care which direction the share went.
        """
        if entry_turnover is None or exit_turnover is None:
            raise Refused(
                "trade_cost_fraction() now requires BOTH entry_turnover and exit_turnover. "
                "A single lumped |target - held| is the T6 defect: it charged the ENTRY's "
                "spread/slippage to unmeasured EXIT legs, which in the measured model is a "
                "zero half-spread. Call split_turnover(previous, target) first."
            )
        entry_turnover, exit_turnover = Fraction(entry_turnover), Fraction(exit_turnover)
        if entry_turnover < 0 or exit_turnover < 0:
            raise Refused(
                f"turnover legs must be absolute sizes; got entry {entry_turnover}, "
                f"exit {exit_turnover}"
            )
        traded = entry_turnover + exit_turnover
        if traded == 0:
            return Fraction(0)
        charge = (
            entry_turnover * self.entry_spread_and_slippage_fraction()
            + exit_turnover * self.exit_spread_and_slippage_fraction()
            + self.commission_fraction(price_micros, traded)
        )
        return assert_non_negative(charge, "trade_cost")

    # ---- carry --------------------------------------------------------------

    def borrow_cost_fraction(self, position: Fraction, calendar_days: Fraction) -> Fraction:
        """Borrow fee on SHORT exposure only, accrued per calendar day.

        A long position pays no borrow. A negative `calendar_days` is a time-ordering bug and
        refuses -- bars running backwards would otherwise show up as a borrow REBATE.
        """
        if calendar_days < 0:
            raise Refused(
                f"negative holding period ({calendar_days} days) -- bars are out of order. "
                "Refusing rather than crediting a negative borrow charge."
            )
        short_notional = -position if position < 0 else Fraction(0)
        if short_notional == 0:
            return Fraction(0)
        charge = (
            short_notional
            * self.borrow_annual.value
            * calendar_days
            / Fraction(CALENDAR_DAYS_PER_YEAR)
        )
        return assert_non_negative(charge, "borrow")

    def to_report(self) -> dict:
        return {
            "entry_half_spread": self.entry_half_spread.to_report(),
            "entry_extra_slippage": self.entry_extra_slippage.to_report(),
            "exit_half_spread": self.exit_half_spread.to_report(),
            "exit_extra_slippage": self.exit_extra_slippage.to_report(),
            "commission_per_share": self.commission_per_share.to_report(),
            "borrow_annual": self.borrow_annual.to_report(),
            "entry_bp": float(self.entry_half_spread.value + self.entry_extra_slippage.value),
            "exit_bp": float(self.exit_half_spread.value + self.exit_extra_slippage.value),
            "round_trip_bp": float(self.round_trip_bp()),
            "note": (
                "Spread and slippage are PER SIDE. round_trip_bp is entry + exit, and is the "
                "number to quote. Borrow accrues on CALENDAR days, not trading days. Price "
                "improvement is NOT modelled: the full half-spread is charged to every taker "
                "fill, which is the conservative side of the B22C uncertainty."
            ),
        }


# ---------------------------------------------------------------------------
# Named, fully-sourced models. These are the only pre-built ones, and each says
# out loud which of its numbers is a measurement and which is a stress rung.
# ---------------------------------------------------------------------------

def zarattini_paper_costs() -> CostModel:
    """EXACTLY what Zarattini/Barbon/Aziz model, and nothing more.

    This exists to be the *straw man*: it is the cost model that produced Sharpe 2.81, and
    B22A established by machine-check that the paper contains the strings 'slippage',
    'bid-ask', 'market impact', 'capacity' and 'fill' zero times. Running a candidate under
    this model and under `retail_taker_costs()` and reporting the difference is the whole
    point of having a cost layer at all.
    """
    return CostModel(
        entry_half_spread=CostComponent(
            "entry_half_spread", Fraction(0), "bp of notional",
            SlippageProvenance.PUBLISHED_PAPER,
            "Zarattini, Barbon & Aziz (2024) SSRN 4729284 -- models no spread at all; "
            "'bid-ask' occurs 0 times in the paper (B22A machine-check).",
        ),
        entry_extra_slippage=CostComponent(
            "entry_extra_slippage", Fraction(0), "bp of notional",
            SlippageProvenance.PUBLISHED_PAPER,
            "Zarattini et al. -- 'slippage' and 'market impact' occur 0 times (B22A).",
        ),
        exit_half_spread=CostComponent(
            "exit_half_spread", Fraction(0), "bp of notional",
            SlippageProvenance.PUBLISHED_PAPER,
            "Zarattini et al. -- the paper's exits (stop-loss and market-on-close) are filled "
            "at the modelled level with no spread; 'fill' occurs 0 times (B22A). This zero is "
            "the STRAW MAN's own assumption, reproduced so the difference can be priced.",
        ),
        exit_extra_slippage=CostComponent(
            "exit_extra_slippage", Fraction(0), "bp of notional",
            SlippageProvenance.PUBLISHED_PAPER,
            "Zarattini et al. -- no exit impact is modelled either (B22A).",
        ),
        commission_per_share=CostComponent(
            "commission_per_share", Fraction(3500), "micro-dollars per share",
            SlippageProvenance.PUBLISHED_PAPER,
            "Zarattini et al. -- $0.0035/share, the only friction the paper models.",
        ),
        borrow_annual=CostComponent(
            "borrow_annual", Fraction(0), "fraction of short notional per year",
            SlippageProvenance.PUBLISHED_PAPER,
            "Zarattini et al. -- no borrow fee is modelled despite the strategy shorting.",
        ),
    )


_DYHRBERG = (
    "Dyhrberg, Shkilko & Werner, JFE 168 (2025): effective spread 49.06 bp at "
    "wholesalers / 46.98 bp at exchanges on marketable retail orders, i.e. a ~2.4 bp "
    "half-spread on a liquid name once the ~44%-of-quoted price improvement they "
    "measure is applied. Rounded UP to 2.5. Price improvement is not separately "
    "credited anywhere else in this rig."
)


def retail_taker_costs(
    half_spread_bp="2.5",
    extra_slippage_bp="0",
    commission_micros_per_share=0,
    borrow_annual_rate="0.003",
    exit_half_spread_bp=None,
    exit_extra_slippage_bp=None,
) -> CostModel:
    """A liquidity-TAKING retail account: crosses the spread on entry AND on exit.

    Defaults are deliberately conservative and each is sourced. `extra_slippage_bp` defaults
    to ZERO not because impact is zero but because B22B did not measure it for this population
    -- so the model is explicitly a LOWER BOUND on friction, exactly as B22B's own scope limit
    says its number will be. Sweep it with `stress_ladder()` rather than picking one flattering
    value.

    THE EXIT SIDE MIRRORS THE ENTRY BY DEFAULT, and that is a choice with a reason: a taker
    crosses the spread getting out exactly as it does getting in, so the symmetric charge is the
    honest one and the round trip is 2 x half_spread_bp = **5.0 bp** at the defaults. Passing
    `exit_half_spread_bp=0` is possible but would be a claim that the exit is free, and this
    module makes you type it rather than inherit it.
    """
    exit_half = half_spread_bp if exit_half_spread_bp is None else exit_half_spread_bp
    exit_extra = extra_slippage_bp if exit_extra_slippage_bp is None else exit_extra_slippage_bp
    return CostModel(
        entry_half_spread=CostComponent(
            "entry_half_spread", _rate(half_spread_bp, "half_spread_bp"), "bp of notional",
            SlippageProvenance.PUBLISHED_ACADEMIC_MEASUREMENT, _DYHRBERG,
        ),
        entry_extra_slippage=CostComponent(
            "entry_extra_slippage", _rate(extra_slippage_bp, "extra_slippage_bp"),
            "bp of notional",
            SlippageProvenance.STRESS_LADDER,
            "NOT MEASURED for this population. Zero here makes the model a stated LOWER BOUND "
            "on friction, never a claim that impact is absent. b22b_measured_costs() carries "
            "this programme's own measurement of the ORB entry instead.",
        ),
        exit_half_spread=CostComponent(
            "exit_half_spread", _rate(exit_half, "exit_half_spread_bp"), "bp of notional",
            SlippageProvenance.PUBLISHED_ACADEMIC_MEASUREMENT,
            _DYHRBERG + " Charged on the EXIT leg too: a stop-loss market order and a "
            "market-on-close are both taker fills, and neither is cheaper than the entry.",
        ),
        exit_extra_slippage=CostComponent(
            "exit_extra_slippage", _rate(exit_extra, "exit_extra_slippage_bp"),
            "bp of notional",
            SlippageProvenance.STRESS_LADDER,
            "NOT MEASURED. Nobody has measured the EXIT leg of this rule at all -- B22B is "
            "entry-only by design. Zero here is a stated lower bound on the exit, not a "
            "finding about it.",
        ),
        commission_per_share=CostComponent(
            "commission_per_share",
            _rate(commission_micros_per_share, "commission_micros_per_share"),
            "micro-dollars per share",
            SlippageProvenance.BROKER_SCHEDULE,
            "Zero-commission US equity brokers (Schwab, Robinhood, Fidelity) charge no "
            "per-share commission on unbundled retail orders; regulatory pass-throughs "
            "(SEC 31 fee, FINRA TAF) are sub-basis-point on a round trip and are folded "
            "into the half-spread's round-up rather than modelled separately.",
        ),
        borrow_annual=CostComponent(
            "borrow_annual", _rate(borrow_annual_rate, "borrow_annual_rate"),
            "fraction of short notional per year",
            SlippageProvenance.BROKER_SCHEDULE,
            "General-collateral US large-cap borrow, ~30 bp/yr. HARD-TO-BORROW NAMES ARE "
            "NOT THIS: single-name borrow can exceed 50%/yr, and any strategy that shorts "
            "small caps must re-source this number rather than inherit it. B22G has since "
            "MEASURED this on the ORB most-actives pool and the warning held: easy-to-borrow "
            "median 0.33%/yr, hard-to-borrow median 10.28%/yr, tail to 259.96%/yr. Use "
            "measured_borrow_annual() rather than this default whenever the strategy shorts.",
        ),
    )


DEFAULT_ATR_FILTER = "0.1"


def measured_extra_slippage(latency_ms: str = "100", percentile: str = "mean",
                            atr_filter: str = DEFAULT_ATR_FILTER) -> CostComponent:
    """Stop-ENTRY slippage as measured by B22B, in bp of notional. Entry only, by design.

    WHY bp OF NOTIONAL AND NOT bp OF R. B22B's headline unit is basis points of R, where
    R = 10% of ATR(14) -- the paper's own unit, which is what makes the verdict comparable to
    the paper's own reported edge. This rig charges a fraction of NOTIONAL. The two have
    different denominators, so the result file carries BOTH, each computed from the same raw
    integers the harness recorded (slippage_micros and the fill price). Rescaling a bp-of-R
    figure by an average ATR here would substitute an approximation for an exact quantity.

    WHAT THIS NUMBER ALREADY CONTAINS -- read before combining it. B22B prices the fill at the
    prevailing ASK (long) or BID (short) and measures the gap to the STOP price, which is a
    traded level. So the measured gap is the half-spread PLUS latency and momentum drift: it
    is the whole of what a fill-at-the-stop backtest omits. It must therefore NEVER be added
    on top of a separately-charged half-spread. `b22b_measured_costs()` sets ENTRY half_spread to
    zero for exactly this reason and says so in that component's own source string. The EXIT
    half-spread is a different leg and is charged in full.

    `atr_filter` -- DECONTAMINATION, and why the default is not "none". The preregistered trigger
    is "the first TRADE at or through the stop". SIP trades include odd-lot and out-of-sequence
    prints, so a dislocated print can trigger a stock-day at a level nobody could have traded;
    the fill is then measured against a stop that was never really touched, lands in the
    FAVOURABLE tail, and drags the MEAN -- the statistic this function charges -- DOWN. That is
    contamination in the strategy's favour, which is the direction this programme is required to
    be paranoid about. `atr_filter` names a rung of `t6_decontamination_ladder`: the stock-days
    whose trigger print was more than that many ATR(14) through the stop are dropped from the
    mean. The default **0.1** is one full R -- R is DEFINED as 10% of ATR(14), so this is "the
    trigger print was more than one whole risk-unit beyond the level", which is a dislocated
    print rather than the level being touched. It is also the adverse end of the defensible
    range, which is the end this programme takes when it is unsure. Pass `atr_filter=None` for
    the raw preregistered mean; the component then says in its own source that it is
    contaminated. Percentiles are always read from the UNFILTERED distribution -- every removed
    observation sits in the favourable tail, so the adverse percentiles are unmoved by the
    filter and using the raw ones is the conservative read.
    """
    result = _load_json(B22B_RESULT_PATH, "the B22B slippage result")
    # Read the CENTI-bp field, not the bp one. Whole basis points are too coarse for this
    # measurement -- the typical entry gap is a fraction of a bp on a $50 stock, so integer bp
    # truncates most of the distribution to 0 and makes a genuine small cost look like no cost.
    rung = result["notional_centibp"].get(str(latency_ms))
    if rung is None:
        raise Refused(
            f"B22B recorded no {latency_ms}ms latency rung; the ladder is "
            f"{sorted(result['notional_centibp'])}. An absent rung is a refusal, not a zero."
        )
    filter_note = ""
    if percentile == "mean":
        # The MEAN is the default, and deliberately so. A backtest charges friction on every
        # trade and sums it, so the quantity that governs the equity curve is the mean per
        # trade, not the median. The median here is exactly zero -- 166 of 429 stock-days fill
        # at the stop price -- and a cost model whose headline number is zero is one bad
        # inference away from the failure this whole module exists to prevent. B22B records
        # sum and n rather than a mean precisely so the mean can be taken EXACTLY here.
        if atr_filter is None:
            centibp = Fraction(rung["sum"], rung["n"])
            filter_note = (
                " UNFILTERED and therefore CONTAMINATED: this mean still contains the "
                "dislocated trigger prints (e.g. TSLA 2025-03-12, a sell stop at $244.30 "
                "triggered by a $223.92 print against a $248.07 bid), which are favourable "
                "outliers and pull the charged cost DOWN. Prefer the default atr_filter.")
        else:
            ladder = result.get("t6_decontamination_ladder")
            if ladder is None:
                raise Refused(
                    "the B22B result carries no t6_decontamination_ladder, so a decontaminated "
                    "mean cannot be read. Absence is a refusal: re-run the T6 ladder builder, "
                    "or pass atr_filter=None and accept the contaminated mean explicitly."
                )
            if str(latency_ms) != "100":
                raise Refused(
                    f"the decontamination ladder was built at the 100ms verdict rung only; "
                    f"{latency_ms}ms has no decontaminated mean. Absent is not zero."
                )
            entry = ladder["rungs"].get(str(atr_filter))
            if entry is None:
                raise Refused(
                    f"atr_filter {atr_filter!r} is not a rung of the decontamination ladder "
                    f"({sorted(ladder['rungs'])}, or None for the raw mean)."
                )
            centibp = Fraction(entry["sum"], entry["n"])
            raw = Fraction(rung["sum"], rung["n"])
            filter_note = (
                f" DECONTAMINATED at {atr_filter} ATR: {entry['n_removed']} of "
                f"{rung['n']} stock-days whose TRIGGER PRINT was more than {atr_filter} ATR(14) "
                f"through the stop are excluded, because a dislocated odd-lot/out-of-sequence "
                f"print measures a fill against a level that was never really touched and lands "
                f"in the FAVOURABLE tail. That raises the charged mean from {float(raw) / 100:.4f} "
                f"to {float(centibp) / 100:.4f} bp ({entry['mean_bp_vs_unfiltered_pct']:+.1f}%). "
                f"Sensitivity, so the threshold cannot hide: 1.0 ATR "
                f"{ladder['rungs']['1.0']['mean_bp_float']:.4f} bp "
                f"({ladder['rungs']['1.0']['mean_bp_vs_unfiltered_pct']:+.1f}%), 0.5 ATR "
                f"{ladder['rungs']['0.5']['mean_bp_float']:.4f} bp "
                f"({ladder['rungs']['0.5']['mean_bp_vs_unfiltered_pct']:+.1f}%), 0.1 ATR "
                f"{ladder['rungs']['0.1']['mean_bp_float']:.4f} bp "
                f"({ladder['rungs']['0.1']['mean_bp_vs_unfiltered_pct']:+.1f}%). The 1.0-ATR rung "
                "already in the result file is too loose to remove the very print the result's "
                "own prose cites (TSLA 2025-03-12 is 0.92 ATR through and survives it).")
    elif percentile in rung:
        centibp = Fraction(rung[percentile])
    else:
        raise Refused(f"{percentile!r} is not in the B22B distribution ({sorted(rung)} or 'mean')")
    value = centibp / 100      # centi-bp -> bp, exactly
    if value < 0:
        # The distribution has a favourable tail: at short horizons the quote sometimes sits
        # inside the stop. Charging a negative cost would be a REBATE for trading, so the
        # adverse-sign convention floors it at zero and says that it did.
        floored, note = Fraction(0), (
            f" (raw {percentile} was {value} bp, i.e. favourable; floored to zero because a "
            "negative cost is a rebate and this programme never credits one)")
    elif value == 0:
        floored, note = Fraction(0), (
            " (this zero is MEASURED, not missing: at this percentile the fill lands exactly on "
            "the stop. It is not a claim that the friction is zero -- see the tail below)")
    else:
        floored, note = Fraction(value), ""
    r_bp = result["r_bp"][str(latency_ms)]
    return CostComponent(
        "entry_extra_slippage", floored, "bp of notional",
        SlippageProvenance.MEASURED_B22B,
        f"B22B measured entry slippage, {percentile} at the {latency_ms}ms latency rung, over "
        f"{result['n_triggered']} triggered stock-days across the pinned 30-day 2025 sample "
        f"({result['days_complete']}/30 days complete, "
        f"{result['n_adverse_of_n'][str(latency_ms)]['adverse']} adverse / "
        f"{result['n_adverse_of_n'][str(latency_ms)]['exactly_zero']} exactly zero / "
        f"{result['n_adverse_of_n'][str(latency_ms)]['favourable']} favourable). "
        f"NEVER QUOTE THIS ALONE -- the tail is where it bites: p90 {rung['p90'] / 100} bp, "
        f"p95 {rung['p95'] / 100} bp, max {rung['max'] / 100} bp of notional; in the paper's own "
        f"unit p50 {r_bp['p50']}, p90 {r_bp['p90']}, p95 {r_bp['p95']} bp of R against the "
        f"800 bp of R the paper reports as its per-trade edge. Verdict {r_bp['verdict']}. "
        f"INCLUDES the half-spread -- see measured_extra_slippage.__doc__.{note}{filter_note} "
        "ENTRY ONLY: B22B never measured an exit, so this number must never be charged to an "
        "exit leg. The exit is priced separately and more expensively -- see "
        "b22b_measured_costs().",
    )


def measured_borrow_annual(tier: str = "etb_general_collateral") -> CostComponent:
    """Short-borrow fee for `tier`, from the B22G feed snapshot.

    Tiers exist because one borrow number for US equities is a fiction. B22G measured the ORB
    most-actives pool and found the easy-to-borrow median an order of magnitude below the
    hard-to-borrow median, and the hard-to-borrow tail three orders above it. A strategy that
    shorts the day's most-active names picks its tier by what it trades, not by what is
    convenient.
    """
    doc = _load_json(B22G_BORROW_PATH, "the B22G borrow-cost snapshot")
    rates = doc["rates_for_the_cost_model"]
    if tier not in rates:
        raise Refused(f"borrow tier {tier!r} is not in B22G ({sorted(rates)})")
    entry = rates[tier]
    rate = entry.get("annual_rate")
    if rate is None:
        raise Refused(f"B22G has no measured rate for tier {tier!r}; absent is not zero")
    # The corrected denominators (T6). B22G screened the 100-name POOL, but the rule only ever
    # met 52 of those names; quoting "36 of 100" describes a screen input, not the strategy's
    # universe. Absent is a refusal here too: a source string that silently reverted to the
    # wrong denominator would be the same error being re-shipped.
    fix = doc.get("t6_correction_screened_universe")
    if fix is None:
        raise Refused(
            "B22G carries no t6_correction_screened_universe block. The uncorrected file states "
            "'36 of 100 names cannot be shorted at any price', which is the wrong denominator "
            "AND an overclaim about what an Alpaca flag measures. Refusing to quote it."
        )
    den, flag, sig = (fix["denominator"], fix["what_the_alpaca_flag_does_and_does_not_mean"],
                      fix["unavailable_short_signals"])
    return CostComponent(
        "borrow_annual", Fraction(str(rate)), "fraction of short notional per year",
        SlippageProvenance.VENDOR_FEED_SNAPSHOT,
        f"B22G tier {tier!r}: {entry['as_pct_per_year']}%/yr. {entry['basis']}. Sources: "
        "Alpaca /v2/assets borrow_status for the traded account (complete over the universe) "
        "and Interactive Brokers' shortable-securities feed for the rate. "
        "AVAILABILITY, STATED CORRECTLY (a rate cannot express it, but the earlier wording "
        f"overstated it): {den['hard_to_borrow_among_screened']} of the "
        f"{den['names_the_b22b_rule_ACTUALLY_screened']} names the ORB rule ACTUALLY screened "
        f"are hard-to-borrow and NOT SHORTABLE AT ALPACA "
        f"({den['hard_to_borrow_share_of_screened']}) -- not 36 of 100, which is the size of the "
        "screen INPUT rather than of the traded universe. NOT SHORTABLE AT ALPACA IS NOT "
        f"'unborrowable at any price': {flag['htb_borrowable_elsewhere']} of the "
        f"{flag['htb_with_an_ibkr_rate']} hard-to-borrow names with an obtainable IBKR rate have "
        "shares AVAILABLE to borrow there, at 2.32%-259.96%/yr -- expensive, not impossible, and "
        f"a COST at another broker rather than a constraint. Of the {sig['short_signals']} short "
        f"signals in the B22B sample, {sig['in_names_not_shortable_at_alpaca']} are in names "
        f"Alpaca will not short, and {sig['leveraged_or_inverse_etp_signals']} of those "
        f"{sig['in_names_not_shortable_at_alpaca']} are LEVERAGED or INVERSE ETPs "
        f"({', '.join(sig['leveraged_or_inverse_etp_symbols'])}) -- an Alpaca PRODUCT "
        "restriction, not borrow scarcity; "
        f"exactly {sig['non_etp_signals']} is an ordinary common stock "
        f"({', '.join(sig['non_etp_symbols'])}). A strategy with a short leg must still handle "
        "availability as a constraint rather than a cost, but the constraint is mostly 'this "
        "broker does not lend leveraged ETPs', which a universe filter or another broker removes.",
    )


def measured_exit_half_spread(latency_ms: str = "100") -> CostComponent:
    """The half-spread an EXIT crosses, taken as the WORSE of two independent estimates.

    B22B never measured an exit. But it did record the QUOTED SPREAD at every trigger instant in
    exactly the universe this rule trades, and that is a legitimate lower bound on what crossing
    it costs. Two candidates therefore exist for the exit half-spread:

      (a) Dyhrberg/Shkilko/Werner JFE 168 (2025) -> 2.5 bp, the retail-taker literature number;
      (b) half of B22B's own MEAN quoted spread over the 429 triggered stock-days.

    They are close, which is the useful part: two unrelated sources landing in the same place is
    weak evidence that neither is silly. The component charges `max(a, b)`, because the guardrail
    on this work is "when uncertain, cost MORE", and because a strategy is never harmed by a
    friction estimate that turned out to be too honest.
    """
    result = _load_json(B22B_RESULT_PATH, "the B22B slippage result")
    spread = result["spread_bp"].get(str(latency_ms))
    if spread is None:
        raise Refused(f"B22B recorded no {latency_ms}ms spread rung; absent is not zero")
    measured_half = Fraction(spread["sum"], spread["n"]) / 2
    literature = Fraction(5, 2)
    value = max(measured_half, literature)
    return CostComponent(
        "exit_half_spread", value, "bp of notional",
        (SlippageProvenance.MEASURED_B22B if measured_half >= literature
         else SlippageProvenance.PUBLISHED_ACADEMIC_MEASUREMENT),
        "The EXIT leg crosses the spread and B22B never measured it, so this is the WORSE of "
        f"two estimates. (a) {_DYHRBERG} (b) B22B's own measured quoted spread over the "
        f"{spread['n']} triggered stock-days at the {latency_ms}ms rung: mean "
        f"{float(Fraction(spread['sum'], spread['n'])):.3f} bp full spread (median "
        f"{spread['p50']}, p90 {spread['p90']}, max {spread['max']} bp), i.e. a "
        f"{float(measured_half):.3f} bp half-spread in this exact universe. Charged: "
        f"max(a, b) = {float(value)} bp. A stop-loss market order and a market-on-close are "
        "both TAKER fills; neither gets the spread for free, and the previous model charged "
        "them zero because it reused the entry component whose half-spread is legitimately "
        "zero for a different reason.",
    )


def measured_auction_leg(leg: str, tier: str = "C_rank_201_500") -> tuple:
    """The honest price of one leg executed MOC/MOO, from the M0 measurement.

    Returns `(half_spread, extra_slippage)` -- the two components `CostModel` wants for a side.

    WHY THE HALF-SPREAD IS STILL ZERO, AND WHY THAT IS NOW A MEASUREMENT
    --------------------------------------------------------------------
    A filled auction order transacts at the single clearing price, and a backtest that MARKS at
    that same official print therefore has no quoted spread to charge. M0 did not overturn that.
    What M0 established is the part the mechanism argument never covered:

      * an official closing print EXISTS on 99.96 % of top-500-ADV symbol-days, and
      * it clears a median $37 M, so a retail-sized order is not the auction.

    WHY IT IS NOT ZERO EVERYWHERE, WHICH IS THE PART THAT CHANGED
    ------------------------------------------------------------
    Availability collapses down the liquidity ladder -- 94.6 % at ADV rank 1501-3000 and 61.8 %
    at rank 3001-6000. An MOC with no auction to clear in is not a free fill; it is an unfilled
    order that has to be unwound by hand across a spread. That expected cost is charged here as
    `auction_non_fill_provision`, read from the M0 result rather than typed in, and it is a
    FLOOR: it prices the spread of the manual unwind and NOT the overnight gap risk of carrying
    a position the strategy did not intend to hold. Outside the measured liquid tiers the
    function refuses rather than extrapolating.
    """
    if leg not in ("entry", "exit"):
        raise Refused(f"leg must be 'entry' or 'exit', not {leg!r}")
    if tier not in M0_LIQUID_TIERS:
        raise Refused(
            f"M0 measured the auction rail as usable only for ADV tiers {M0_LIQUID_TIERS}; "
            f"{tier!r} is outside them. At rank 1501-3000 the closing print is missing on 5.4 % "
            "of symbol-days and at rank 3001-6000 on 37.9 %, and the median closing auction "
            "there is $14 k. Charge a real half-spread on that leg, or do not trade it in the "
            "auction -- this function will not extrapolate a zero into a tier it was not "
            "measured in."
        )
    result = _load_json(M0_RESULT_PATH, "the M0 auction-fill result")
    prov = (result.get("non_fill_provision_bp") or {}).get(tier)
    if prov is None:
        raise Refused(f"M0 result carries no non-fill provision for {tier!r}; absent is refusal")
    tier_row = result["tiers"][tier]
    rate = tier_row["close_print_rate"]
    provision = _rate(str(round(prov["provision_bp"], 6)), "provision_bp")
    half = CostComponent(
        f"{leg}_half_spread", Fraction(0), "bp of notional",
        SlippageProvenance.MEASURED_M0_AUCTION_PRINT,
        f"MOC/MOO leg in ADV tier {tier}. A single-price cross has no bid-ask to cross AND M0 "
        f"measured that the cross is there to be crossed: an official closing print on "
        f"{rate * 100:.2f} % of {tier_row['symbol_days']} sampled symbol-days, median size "
        f"{result['tiers'][tier]['dists']['close_auction_notional_usd']['median'] / 1e6:.1f} $M. "
        "What remains unmeasured is that the BROKER's on-close order joins that cross; that is "
        "the live half of M0 and is not claimed here.",
    )
    extra = CostComponent(
        f"{leg}_extra_slippage", provision, "bp of notional",
        SlippageProvenance.MEASURED_M0_AUCTION_PRINT,
        f"auction_non_fill_provision for {tier}: P(no official closing print) = "
        f"{prov['p_no_print'] * 100:.2f} % x a full quoted spread "
        f"(2 x {prov['median_half_spread_bp']:.2f} bp median half-spread) to unwind by hand = "
        f"{prov['provision_bp']:.4f} bp. A FLOOR -- it excludes the overnight gap risk of "
        "carrying an unintended position, which M0 did not price.",
    )
    return half, extra


def measured_exit_leg_t18(kind: str = "blend", latency_ms: str = "100") -> tuple:
    """The EXIT side, from the T18 tick measurement. Returns `(half_spread, extra_slippage)`.

    ADDITIVE: this changes no existing cost number. `b22b_measured_costs()` still returns the
    T6 model with its `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG` exit, so every published result
    stays reproducible; a caller that wants the measured exit asks for it explicitly.

    `kind`
        "stop"   the stop-loss market order's own distribution;
        "moc"    the market-on-close's own distribution, i.e. the official closing print against
                 the last-bar mark the backtest credits;
        "blend"  the two weighted by the MEASURED outcome mix (what share of triggered
                 stock-days really stopped out, from ticks) -- the number to charge a rig that
                 does not distinguish its exits.

    THE HALF-SPREAD IS ZERO HERE AND THAT IS NOT AN OMISSION. The measured slippage runs from a
    TRADED level -- the print that triggered the stop, or the mark the backtest credits -- to
    the price a market order actually receives on the far side of the book. It therefore already
    contains the half-spread, exactly as B22B's entry number does and for the same reason
    `b22b_measured_costs()` sets the entry half-spread to zero. Charging 2.5 bp on top would
    double-count it.

    THE FILTERING RULE IS FROZEN AND IS NOT THE ENTRY'S. On the entry, dropping trigger prints
    more than 0.1 ATR through the level removes dislocated odd-lot prints that all sit in the
    FAVOURABLE tail. On the exit the same filter can cut either way -- it also removes genuine
    fast moves that gapped through the stop, which are the expensive fills. So the charged mean
    is **whichever of {unfiltered, decontaminated} is MORE ADVERSE**, and the component's own
    source string says which one that was.
    """
    if kind not in ("stop", "moc", "blend"):
        raise Refused(f"kind must be stop, moc or blend, not {kind!r}")
    result = _load_json(T18_RESULT_PATH, "the T18 exit measurement")
    SlippageProvenance.MEASURED_T18_EXIT.assert_available()

    def worse(block, raw_key, clean_key):
        raw, clean = block.get(raw_key) or {}, block.get(clean_key) or {}
        if not raw.get("n") or not clean.get("n"):
            raise Refused("the T18 result carries no exit distribution to charge; absence is "
                          "a refusal, never a zero")
        r_mean = Fraction(raw["sum"], raw["n"])
        c_mean = Fraction(clean["sum"], clean["n"])
        return ((r_mean, "unfiltered", raw["n"]) if r_mean >= c_mean
                else (c_mean, "decontaminated", clean["n"]))

    stop_block = result["exit_stop_leg"][str(latency_ms)]
    stop_mean, stop_basis, stop_n = worse(stop_block, "centibp", "centibp_decontaminated")
    moc_mean, moc_basis, moc_n = worse(result["moc_leg"], "centibp",
                                       "centibp_decontaminated")
    share = result["outcome_mix_tick_truth"]["stopped_share"]
    if share is None:
        raise Refused("the T18 result carries no measured outcome mix; refusing to blend")
    weight = Fraction(str(round(share, 6)))

    if kind == "stop":
        centibp, note, n = stop_mean, f"stop-loss market exits ({stop_basis}, n={stop_n})", stop_n
    elif kind == "moc":
        centibp, note, n = moc_mean, f"market-on-close exits ({moc_basis}, n={moc_n})", moc_n
    else:
        centibp = weight * stop_mean + (1 - weight) * moc_mean
        note = (f"{float(weight) * 100:.1f} % stop-loss ({stop_basis}, n={stop_n}) + "
                f"{(1 - float(weight)) * 100:.1f} % market-on-close ({moc_basis}, n={moc_n}), "
                "weighted by the MEASURED outcome mix")
        n = stop_n + moc_n
    value = centibp / 100                       # centi-bp -> bp, exactly
    if value < 0:
        value, floor_note = Fraction(0), (
            f" (the raw measured mean was {float(centibp) / 100:.4f} bp, i.e. FAVOURABLE; "
            "floored to zero because a negative cost is a rebate and this programme never "
            "credits one. The favourable sign is a real measurement and is reported in "
            "T18_EXIT_MEASUREMENT.json rather than hidden here)")
    else:
        floor_note = ""
    half = CostComponent(
        "exit_half_spread", Fraction(0), "bp of notional",
        SlippageProvenance.MEASURED_T18_EXIT,
        "ZERO ON PURPOSE, AND ONLY BECAUSE THE EXIT IS NOW MEASURED: the T18 number runs from "
        "the traded level to the far side of the book, so the half-spread is inside it. This "
        "zero is NOT the pre-T6 bug, which charged the ENTRY's zero to an unmeasured exit.",
    )
    extra = CostComponent(
        "exit_extra_slippage", value, "bp of notional",
        SlippageProvenance.MEASURED_T18_EXIT,
        f"T18 measured exit slippage, mean over {n} observations: {note}. "
        f"Charged {float(value):.4f} bp of notional. In the paper's own unit the stop leg is "
        f"p50 {stop_block['r_bp_decontaminated']['p50']}, p90 "
        f"{stop_block['r_bp_decontaminated']['p90']} bp of R against the 800 bp of R the paper "
        f"reports as its per-trade edge. NEVER add a half-spread on top.{floor_note}",
    )
    return half, extra


def b22b_measured_costs(latency_ms: str = "100", percentile: str = "mean",
                        borrow_tier: str = "etb_general_collateral",
                        commission_micros_per_share=0,
                        atr_filter: str = DEFAULT_ATR_FILTER) -> CostModel:
    """The ORB cost model with this programme's own measurements in it -- PER SIDE.

    ENTRY. `entry_half_spread` is deliberately ZERO, and that is not an omission: the B22B
    number already contains it (the fill is priced at the far side of the book against a stop set
    at a traded level), so charging 2.5 bp on top would double-count the spread.

    EXIT, WHICH IS THE T6 CORRECTION. B22B is entry-only BY DESIGN and the harness is frozen, so
    no measurement of the exit exists or can be conjured from it. The previous model had no exit
    side at all: the engine charged the entry components to both legs, so every stop-out and
    every market-on-close paid a ZERO half-spread and the entry's small measured drift. That made
    the round trip ~3.4x cheaper than this model's own honest lower bound, in the strategy's
    favour. The exit is now:

      exit_half_spread     max(2.5 bp literature, half of B22B's measured quoted spread) -- see
                           `measured_exit_half_spread`;
      exit_extra_slippage  the ENTRY's decontaminated measured magnitude, carried across as a
                           deliberately adverse PROXY and labelled as one. The argument for it
                           being a floor rather than a guess: a stop-loss exit is triggered BY
                           the adverse move, and a market-on-close prints into the largest
                           liquidity event of the day but at whatever the auction clears at. No
                           mechanism makes either systematically gentler than a stop ENTRY, and
                           charging zero would be the failure this module exists to prevent.

    The result is a round trip that costs strictly more than either leg alone and more than the
    5 bp `retail_taker_costs()` round trip. `retail_taker_costs()` remains the model to use when
    the slippage term is a stress rung rather than this measurement.
    """
    entry_slippage = measured_extra_slippage(latency_ms, percentile, atr_filter)
    return CostModel(
        entry_half_spread=CostComponent(
            "entry_half_spread", Fraction(0), "bp of notional",
            SlippageProvenance.MEASURED_B22B,
            "ZERO ON PURPOSE, NOT UNMODELLED: the entry_extra_slippage term in this same model "
            "is measured from the stop price to the prevailing ask/bid, so it already carries "
            "the half-spread. Charging one here as well would double-count it. THIS ZERO IS "
            "ENTRY-ONLY -- it does not and never did apply to the exit, and exit_half_spread "
            "carries the spread the exit really crosses.",
        ),
        entry_extra_slippage=entry_slippage,
        exit_half_spread=measured_exit_half_spread(latency_ms),
        exit_extra_slippage=CostComponent(
            "exit_extra_slippage", entry_slippage.value, "bp of notional",
            SlippageProvenance.ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG,
            "NOT A MEASUREMENT OF THE EXIT -- nobody has measured the exit of this rule, and "
            "the B22B harness is frozen entry-only by design, so this is the entry's own "
            f"measured magnitude ({float(entry_slippage.value):.4f} bp) charged again to the "
            "exit ON TOP of the exit half-spread. Rationale: a stop-loss exit is triggered by "
            "the move going against the position and a market-on-close takes whatever the "
            "auction clears at, so neither is systematically gentler than a stop ENTRY. The "
            "alternative was zero, and a zero where a measurement is missing is the single "
            "most common shape of the lie this module exists to stop. Replace this with a real "
            "measured exit when one exists; until then it is a stated stand-in, and it is on "
            "the adverse side by construction.",
        ),
        commission_per_share=CostComponent(
            "commission_per_share",
            _rate(commission_micros_per_share, "commission_micros_per_share"),
            "micro-dollars per share",
            SlippageProvenance.BROKER_SCHEDULE,
            "Zero-commission US equity brokers charge no per-share commission on unbundled "
            "retail orders. Set this to 3500 to reproduce the Zarattini et al. assumption.",
        ),
        borrow_annual=measured_borrow_annual(borrow_tier),
    )


def stress_ladder(base: CostModel, extra_slippage_bp_rungs=(0, 5, 10, 25, 50)):
    """The same model at several impact levels. A single cost number is never reported alone.

    B22D/B22E did this and it is what made the intraday-momentum result unambiguous: the
    strategy lost at the ZERO rung, so no cost argument could rescue it. A ladder answers
    'how much friction would it take to kill this' in one table.

    THE RUNG IS PER SIDE. It replaces the extra-slippage term on BOTH the entry and the exit, so
    a rung of 10 bp is 20 bp of additional impact over a round trip. A ladder that stressed only
    the entry would leave the exit -- the leg nobody has measured -- permanently at whatever the
    base model happened to carry, which is precisely the blind spot this rig just closed.
    """
    out = []
    for bp in extra_slippage_bp_rungs:
        def rung(side):
            return CostComponent(
                f"{side}_extra_slippage", _rate(bp, "extra_slippage_bp"), "bp of notional",
                SlippageProvenance.STRESS_LADDER,
                f"stress rung: {bp} bp of additional {side} impact beyond the quoted "
                "half-spread, charged on BOTH sides of the round trip. Not a measurement.",
            )
        out.append((Fraction(bp), CostModel(
            entry_half_spread=base.entry_half_spread,
            entry_extra_slippage=rung("entry"),
            exit_half_spread=base.exit_half_spread,
            exit_extra_slippage=rung("exit"),
            commission_per_share=base.commission_per_share,
            borrow_annual=base.borrow_annual,
        )))
    return out


def zero_cost_model() -> CostModel:
    """Frictionless. NOT a trading assumption -- a diagnostic.

    B19P's most load-bearing finding is that the memecoin exit family loses 16.89% *at zero
    transaction cost*, which closed every cost-reduction idea at once. A rig that cannot
    express zero cost cannot run that diagnostic. Any report generated with this model is
    tagged so it can never be mistaken for a tradeable result.
    """
    zero = lambda name, unit: CostComponent(  # noqa: E731
        name, Fraction(0), unit, SlippageProvenance.STRESS_LADDER,
        "DIAGNOSTIC ONLY: the frictionless bound, per B19P. If a strategy loses here, no "
        "execution improvement can rescue it. It is not a tradeable cost assumption.",
    )
    return CostModel(
        entry_half_spread=zero("entry_half_spread", "bp of notional"),
        entry_extra_slippage=zero("entry_extra_slippage", "bp of notional"),
        exit_half_spread=zero("exit_half_spread", "bp of notional"),
        exit_extra_slippage=zero("exit_extra_slippage", "bp of notional"),
        commission_per_share=zero("commission_per_share", "micro-dollars per share"),
        borrow_annual=zero("borrow_annual", "fraction of short notional per year"),
    )


__all__ = [
    "BP", "MICROS", "CALENDAR_DAYS_PER_YEAR", "DEFAULT_ATR_FILTER",
    "B22B_RESULT_PATH", "B22G_BORROW_PATH", "B22B_PINNED_SAMPLE_DAYS",
    "SlippageProvenance", "CostComponent", "CostModel", "assert_non_negative",
    "split_turnover", "zarattini_paper_costs", "retail_taker_costs", "stress_ladder",
    "zero_cost_model", "measured_extra_slippage", "measured_exit_half_spread",
    "measured_borrow_annual", "b22b_measured_costs",
]
