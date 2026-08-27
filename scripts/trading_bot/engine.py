#!/usr/bin/env python3
"""The bar-by-bar engine. Leakage-free BY CONSTRUCTION, and the construction is proved, not asserted.

HOW LOOKAHEAD IS PREVENTED -- THREE INDEPENDENT LAYERS
======================================================

**Layer 1 -- the strategy is never handed the series.** It receives a `PointInTimeView`, a
cursor over a private tuple. Every accessor clamps at the cursor: `view[i]` for `i > cursor`
raises `Refused`, `len(view)` is `cursor + 1`, `view.history(n)` returns the trailing window
and refuses if `n` exceeds the bars that have actually printed. The underlying tuple is
stored in a name-mangled slot on a `__slots__` class, so there is no `__dict__` to rummage
through and no attribute called `bars`.

**Layer 2 -- a decision can never be filled at the price that produced it.** A signal
computed from bar *i*'s close cannot be executed at bar *i*'s close: at the moment you knew
the close, the close had already printed. `execution_lag_bars` is therefore **>= 1 and
cannot be set to 0** -- the engine refuses. The fill happens at bar *i+lag*'s OPEN, and the
position is marked open-to-open, so the price you transact at and the price you mark at are
the same tick. The classic "fill at the open, mark at the close" mismatch cannot occur here
because the engine never mixes the two.

**Layer 3 -- the future-scramble audit, which is the one that actually proves it.**
Layers 1 and 2 constrain the *interface*. They cannot stop a strategy that holds its own
reference to the bars and reads ahead in it. So the engine runs the strategy a second time on
data that is **identical up to probe bar k and deterministically scrambled after it**. Every
decision at index <= k must be bit-identical between the two runs. If any differs, the
strategy consumed information from beyond bar k, and the run refuses naming the first
divergent index. It runs by default on every backtest and `run_backtest` refuses to report if
it fails.

The audit does not inspect the strategy, so it catches a peek through the view, through a
constructor-held copy of the series, or through anything derived from them, without caring
which. **For that to hold, a strategy that needs the bars must receive them from the factory**
-- see `build_strategy`. This was found the honest way: the first version of this audit
called `strategy_factory()` with no arguments, and the deliberately-leaky `CheatingOracle`
negative control sailed through it, because the oracle kept the *original* series while only
the engine's copy was scrambled. The negative control existed, was run, and failed the audit
rather than the audit failing it.

**Stated limit, because a guard that overclaims is worse than none.** A strategy that opens
its own data file inside `on_bar`, or reads a module global the harness never touches, is
outside what any re-run can detect. The audit's guarantee is: *no decision depends on the
future of the series the harness controls.* Out-of-band data is a code-review question, not
an arithmetic one.

ACCOUNTING
==========
Positions are signed fractions of equity: +1.0 fully long, -1.0 fully short, 0 flat.
Equity is tracked at each bar's OPEN, and the return of segment j -> j+1 is

    pos[j] * (open[j+1] - open[j]) / open[j]  -  trade_cost(at j)  -  borrow(j -> j+1)

where `pos[j]` is the target decided at bar `j - lag`. Trade costs are charged at bar j's
open, at bar j's open price.

**Turnover is charged PER SIDE (T6 correction).** `|pos[j] - pos[j-1]|` is not one trade: a
reversal from +1 to -1 is a 1.0 EXIT and then a 1.0 ENTRY, and those legs do not cost the same
when only the entry has ever been measured. The engine therefore splits every position change
with `costs.split_turnover` and hands both legs to the cost model, which prices them separately.
The previous version passed the lumped absolute change and the cost model charged one
side-agnostic rate to it -- which, under the B22B measured model whose ENTRY half-spread is
legitimately zero, gave every stop-out and every market-on-close a free spread. `entry_turnover`
and `exit_turnover` are reported per segment so the split is auditable rather than asserted, and
they sum to the old `turnover` exactly.

**Stated limit:** a position still open on the final bar is never closed, so it is never charged
an exit. That is honest marking (the position exists; it has not been sold), but it means a
buy-and-hold run pays one entry and no exit, and a strategy compared against it should not be
credited for the difference.

FLOAT BOUNDARY
==============
B22B has exactly one float boundary: `to_micros` at ingest. This engine adds exactly one
more and names it: **per-bar returns are exact `Fraction`s; the equity curve and every
statistic are float.** Nothing about a price, a fill, a cost or a return is ever float.
`equity_curve_exact()` recomputes the curve in exact rationals so a test can pin the float
path against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .costs import CostModel, split_turnover
from .frozen import Refused, parse_rfc3339_ns, to_micros, to_shares

NS_PER_DAY = 86_400 * 1_000_000_000
MIN_EXECUTION_LAG_BARS = 1


# ---------------------------------------------------------------------------
# The bar
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Bar:
    """One OHLCV bar. All prices integer micro-dollars, timestamp integer nanoseconds."""

    symbol: str
    ts_ns: int
    open_micros: int
    high_micros: int
    low_micros: int
    close_micros: int
    volume_shares: int
    trade_count: int = 0
    vwap_micros: int = 0

    @staticmethod
    def from_alpaca(symbol: str, raw: dict) -> "Bar":
        """Build from an Alpaca bar dict, crossing the frozen float boundary exactly once per field."""
        for key in ("t", "o", "h", "l", "c", "v"):
            if key not in raw:
                raise Refused(f"bar for {symbol} is missing field {key!r}; absent is not zero")
        bar = Bar(
            symbol=symbol,
            ts_ns=parse_rfc3339_ns(raw["t"]),
            open_micros=to_micros(raw["o"]),
            high_micros=to_micros(raw["h"]),
            low_micros=to_micros(raw["l"]),
            close_micros=to_micros(raw["c"]),
            volume_shares=to_shares(raw["v"]),
            trade_count=to_shares(raw["n"]) if raw.get("n") is not None else 0,
            vwap_micros=to_micros(raw["vw"]) if raw.get("vw") is not None else 0,
        )
        bar.validate()
        return bar

    def validate(self) -> None:
        """A bar that violates its own invariants is corrupt data, not a small problem."""
        if self.open_micros <= 0 or self.close_micros <= 0:
            raise Refused(f"{self.symbol} @ {self.ts_ns}: non-positive price; refusing")
        if self.low_micros > self.high_micros:
            raise Refused(f"{self.symbol} @ {self.ts_ns}: low > high; the bar is corrupt")
        if not (self.low_micros <= self.open_micros <= self.high_micros):
            raise Refused(f"{self.symbol} @ {self.ts_ns}: open outside [low, high]")
        if not (self.low_micros <= self.close_micros <= self.high_micros):
            raise Refused(f"{self.symbol} @ {self.ts_ns}: close outside [low, high]")
        if self.volume_shares < 0:
            raise Refused(f"{self.symbol} @ {self.ts_ns}: negative volume")


def validate_series(bars) -> tuple:
    """Freeze a bar sequence and refuse anything a point-in-time loop cannot trust.

    Strictly increasing timestamps: a duplicate or an out-of-order bar makes 'the past'
    ambiguous, and an ambiguous past is a leak waiting to happen.
    """
    series = tuple(bars)
    if len(series) < 2:
        raise Refused(f"a backtest needs at least 2 bars; got {len(series)}")
    symbols = {bar.symbol for bar in series}
    if len(symbols) != 1:
        raise Refused(f"one series, one symbol; got {sorted(symbols)}")
    for prev, cur in zip(series, series[1:]):
        if cur.ts_ns <= prev.ts_ns:
            raise Refused(
                f"bars out of order or duplicated at ts {cur.ts_ns} (previous {prev.ts_ns}). "
                "Ordering must come from the timestamp, never from list position as delivered."
            )
        cur.validate()
    series[0].validate()
    return series


# ---------------------------------------------------------------------------
# Layer 1: the clamped view
# ---------------------------------------------------------------------------

class PointInTimeView:
    """A read-only cursor over a bar series that cannot address the future.

    `__slots__` and a name-mangled store mean there is no `__dict__` and no attribute called
    `bars`. This is a guard, not a proof -- the proof is the scramble audit below.
    """

    __slots__ = ("__series", "__cursor")

    def __init__(self, series: tuple, cursor: int):
        if not isinstance(series, tuple):
            raise Refused("the view requires an immutable tuple; a list could be mutated under it")
        if not 0 <= cursor < len(series):
            raise Refused(f"cursor {cursor} outside [0, {len(series) - 1}]")
        object.__setattr__(self, "_PointInTimeView__series", series)
        object.__setattr__(self, "_PointInTimeView__cursor", cursor)

    # -- identity of "now" ---------------------------------------------------

    @property
    def index(self) -> int:
        """Index of the bar that has just closed. This is 'now'."""
        return self.__cursor

    @property
    def now(self) -> Bar:
        return self.__series[self.__cursor]

    @property
    def timestamp_ns(self) -> int:
        return self.__series[self.__cursor].ts_ns

    @property
    def symbol(self) -> str:
        return self.__series[self.__cursor].symbol

    # -- the past, and only the past -----------------------------------------

    def __len__(self) -> int:
        return self.__cursor + 1

    def __getitem__(self, i: int) -> Bar:
        if isinstance(i, slice):
            raise Refused(
                "slicing a point-in-time view is refused: a slice with an open or negative "
                "bound is the easiest way to silently address the future. Use history(n)."
            )
        if i < 0:
            i = self.__cursor + 1 + i
        if i < 0:
            raise Refused(f"bar index {i} precedes the start of the series")
        if i > self.__cursor:
            raise Refused(
                f"LOOKAHEAD REFUSED: bar {i} has not printed yet; the cursor is at "
                f"{self.__cursor}. The strategy may only see bars 0..{self.__cursor}."
            )
        return self.__series[i]

    def history(self, n: int) -> tuple:
        """The last `n` bars up to and including now. Refuses if `n` bars have not printed.

        This refusal is the ATR warm-up lesson from B22B generalised: computing a 14-period
        statistic from 13 observations is a warm-up error, and warm-up errors bias early
        results in whatever direction the missing data would have pushed them.
        """
        if n <= 0:
            raise Refused(f"history({n}) is not a window")
        if n > self.__cursor + 1:
            raise Refused(
                f"history({n}) requested at bar {self.__cursor}: only {self.__cursor + 1} bars "
                "have printed. Undefined is not zero, and a short window is not a full one."
            )
        return self.__series[self.__cursor + 1 - n:self.__cursor + 1]

    def closes(self, n: int) -> tuple:
        return tuple(bar.close_micros for bar in self.history(n))

    def __iter__(self):
        raise Refused(
            "iterating a point-in-time view is refused: it reads as 'all the data' at the call "
            "site while meaning 'the data so far', and that ambiguity is how lookahead enters. "
            "Ask for history(n) explicitly."
        )

    def __repr__(self) -> str:
        return f"<PointInTimeView {self.symbol} bar {self.__cursor} of visible {len(self)}>"


# ---------------------------------------------------------------------------
# Strategy contract
# ---------------------------------------------------------------------------

class Strategy:
    """Subclass and implement `on_bar`. That is the entire contract.

    `on_bar(view, state)` returns the TARGET position as a signed fraction of equity. It is
    called once per bar, in order, and the return value is filled `execution_lag_bars` later
    at that bar's open.

    `warmup_bars` is the number of bars the strategy needs before its first decision is
    meaningful. The engine will not call `on_bar` before then, and -- importantly -- the
    walk-forward splitter charges this warm-up to the TRAIN side so a test fold never
    silently begins with a statistic computed from its own future.
    """

    name = "unnamed"
    warmup_bars = 0

    def on_start(self, state: dict) -> None:
        """Called once before the first bar. Put mutable strategy state in `state`."""

    def on_bar(self, view: PointInTimeView, state: dict) -> Fraction:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "warmup_bars": self.warmup_bars, "class": type(self).__name__}


def _coerce_target(value, index: int) -> Fraction:
    if value is None:
        raise Refused(f"strategy returned None at bar {index}; None is not flat. Return 0 to be flat.")
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise Refused(f"strategy returned a non-finite target ({value}) at bar {index}")
        target = Fraction(value).limit_denominator(1_000_000)
    else:
        target = Fraction(value)
    return target


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    strategy: dict
    execution_lag_bars: int
    warmup_bars: int
    first_decision_index: int
    bar_timestamps_ns: tuple      # timestamp at each equity point (bar OPENs)
    positions: tuple              # Fraction, position effective at each equity point
    targets: tuple                # (bar_index, Fraction) every decision the strategy made
    returns: tuple                # exact Fraction, net of costs, one per segment
    gross_returns: tuple          # exact Fraction, before costs
    market_returns: tuple         # exact Fraction, the bar's own open-to-open move
    costs: tuple                  # exact Fraction, >= 0, one per segment
    turnover: tuple               # exact Fraction, |dpos| at each segment start
    cost_model: dict
    lookahead_audit: dict
    entry_turnover: tuple = ()    # exact Fraction, the part of |dpos| that OPENED exposure
    exit_turnover: tuple = ()     # exact Fraction, the part of |dpos| that CLOSED it

    @property
    def n_segments(self) -> int:
        return len(self.returns)

    def equity_curve(self) -> list:
        """Float equity curve, starting at 1.0. The declared second float boundary."""
        equity, curve = 1.0, [1.0]
        for r in self.returns:
            equity *= 1.0 + float(r)
            curve.append(equity)
        return curve

    def equity_curve_exact(self) -> list:
        """The same curve in exact rationals. Slow; exists so a test can pin the float path."""
        equity, curve = Fraction(1), [Fraction(1)]
        for r in self.returns:
            equity *= Fraction(1) + r
            curve.append(equity)
        return curve

    def total_cost_fraction(self) -> Fraction:
        return sum(self.costs, Fraction(0))

    def total_turnover(self) -> Fraction:
        return sum(self.turnover, Fraction(0))

    def total_entry_turnover(self) -> Fraction:
        return sum(self.entry_turnover, Fraction(0))

    def total_exit_turnover(self) -> Fraction:
        return sum(self.exit_turnover, Fraction(0))


def build_strategy(strategy_factory, series: tuple) -> Strategy:
    """Construct a strategy, handing it the series if its factory accepts one.

    THIS IS PART OF THE LEAKAGE GUARANTEE, not a convenience. The scramble audit works by
    substituting a different future; a strategy that holds its own reference to the bars must
    therefore receive them THROUGH the factory, so the audit can hand it the scrambled copy.
    A strategy that instead captures the real series in a closure the harness never sees is
    outside what any re-run can detect -- so the contract is: **if your strategy needs the
    bar series, take it as a constructor argument.**

    Arity is inspected rather than guessed at by try/except TypeError, because a TypeError
    raised *inside* a one-argument constructor would otherwise be silently retried as a
    zero-argument call and the strategy built with no data at all.
    """
    import inspect

    target = strategy_factory
    if inspect.isclass(target):
        target = target.__init__
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return strategy_factory()

    positional = [
        p for name, p in signature.parameters.items()
        if name != "self" and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        and p.default is p.empty
    ]
    if positional:
        return strategy_factory(series)
    return strategy_factory()


def _decide(series: tuple, strategy: Strategy, warmup: int, last_index: int):
    """Run the decision loop alone over [warmup, last_index]. Returns {bar_index: target}.

    Separated from the accounting because the audit needs decisions WITHOUT costs or equity,
    and because a decision loop that cannot be run in isolation cannot be audited in isolation.
    """
    state: dict = {}
    strategy.on_start(state)
    decisions = {}
    for i in range(warmup, last_index + 1):
        view = PointInTimeView(series, i)
        decisions[i] = _coerce_target(strategy.on_bar(view, state), i)
    return decisions


def _lcg(state: int) -> int:
    return (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)


def _scramble(series: tuple, from_index: int, seed: int) -> tuple:
    """Replace every bar strictly after `from_index` with a deterministic UNRELATED bar.

    The first version of this function multiplied every field of a bar by one per-bar factor.
    That was a real defect: scaling open, high, low and close together **preserves the sign of
    (close - open)**, so a strategy peeking at tomorrow's candle direction saw the same answer
    in both runs and the audit passed it. The defect was found by the negative control, which
    is the only reason the negative control exists.

    So the future is now REGENERATED rather than distorted: prices are drawn from a
    deterministic LCG anchored at the last honest close, destroying direction, ordering,
    magnitude and every relationship among them. Timestamps are preserved, because altering
    those would make the two runs diverge for an unrelated reason.
    """
    out = list(series[:from_index + 1])
    anchor = series[from_index].close_micros
    state = (seed * 2654435761) % (1 << 64)
    for bar in series[from_index + 1:]:
        state = _lcg(state)
        open_micros = max(2_000, anchor * (500 + (state >> 33) % 1001) // 1000)
        state = _lcg(state)
        close_micros = max(2_000, anchor * (500 + (state >> 33) % 1001) // 1000)
        state = _lcg(state)
        out.append(Bar(
            symbol=bar.symbol,
            ts_ns=bar.ts_ns,
            open_micros=open_micros,
            high_micros=max(open_micros, close_micros) + 1_000,
            low_micros=min(open_micros, close_micros) - 1_000,
            close_micros=close_micros,
            volume_shares=(state >> 40) % 10_000_000,
            trade_count=bar.trade_count,
            vwap_micros=(open_micros + close_micros) // 2,
        ))
    return tuple(out)


def lookahead_audit(
    series: tuple,
    strategy_factory,
    *,
    warmup: int,
    lag: int,
    probes: int = 6,
    seed: int = 20260816,
) -> dict:
    """Layer 3. Prove no decision at or before bar k depends on anything after bar k.

    TWO PROBES, because one is deterministic and the other is broad.

    **Truncation probe -- deterministic, and complete for any strategy that reads past the
    end.** Re-run on `series[:k+1]` and require every decision in [warmup, k] to match the
    full run. On the truncated series the later bars do not merely differ, they DO NOT EXIST:
    a forward-reading strategy must return something different or raise, and either is caught.
    No randomness, no seed, no chance of getting lucky.

    **Scramble probe -- broad, for a peek at a bar that exists in both runs.** Re-run on data
    identical up to k and regenerated after it. This catches a strategy that consumes the
    whole series for, say, a normalisation constant, which truncation alone might not move.

    Raises `Refused` on the first divergence, naming the bar and the probe that caught it.
    """
    if probes < 1:
        raise Refused("a lookahead audit with no probes proves nothing; probes must be >= 1")

    last_decidable = len(series) - 1 - lag
    if last_decidable < warmup:
        raise Refused(
            f"series too short: warmup {warmup} + lag {lag} leaves no decidable bar in "
            f"{len(series)} bars"
        )

    baseline = _decide(series, build_strategy(strategy_factory, series), warmup, last_decidable)

    span = last_decidable - warmup
    if span <= 0:
        probe_points = [warmup]
    else:
        probe_points = sorted({
            warmup + (span * (p + 1)) // (probes + 1) for p in range(probes)
        })
        probe_points = [k for k in probe_points if warmup <= k <= last_decidable] or [warmup]

    def compare(probe_series, k, label):
        verb = "removed" if label == "truncation" else "replaced"
        strategy = build_strategy(strategy_factory, probe_series)
        try:
            probe_decisions = _decide(probe_series, strategy, warmup, k)
        except Refused:
            raise
        except Exception as exc:                          # noqa: BLE001
            # A strategy that CRASHES once the future is gone was reading the future.
            # Letting this propagate as an ordinary error would turn a detected leak into an
            # unexplained traceback; swallowing it would turn one into a silent pass.
            raise Refused(
                f"LOOKAHEAD DETECTED ({label} probe at bar {k}). The strategy raised "
                f"{type(exc).__name__}: {exc} once bars after {k} were {verb}. A decision at "
                f"or before bar {k} that cannot be computed without the later bars is by "
                "definition using them."
            ) from exc
        for i in range(warmup, k + 1):
            if baseline[i] != probe_decisions[i]:
                raise Refused(
                    f"LOOKAHEAD DETECTED ({label} probe at bar {k}). The decision at bar {i} "
                    f"changed from {baseline[i]} to {probe_decisions[i]} when bars after {k} "
                    f"were {verb}. A decision at bar {i} cannot legitimately depend on bar "
                    f"{k + 1} or later. The leak need not be through the view -- check "
                    "anything the strategy was constructed with."
                )
        return k + 1 - warmup

    checked = 0
    for k in probe_points:
        # The slice of an already-validated tuple is validated; it is NOT re-checked with
        # validate_series, which requires >= 2 bars and would refuse the k = 0 probe -- the
        # very first and cheapest place a lookahead can be caught.
        checked += compare(series[:k + 1], k, "truncation")
        checked += compare(_scramble(series, k, seed + k), k, "scramble")

    return {
        "verdict": "PASS",
        "method": (
            "two probes at each point. TRUNCATION deletes the future, which no "
            "forward-reading strategy survives unchanged, and is deterministic. SCRAMBLE "
            "regenerates the future from an LCG, catching a peek at a bar that still exists. "
            "Every decision at or before the probe bar must be bit-identical to the full run."
        ),
        "probe_bars": probe_points,
        "decisions_compared": checked,
        "seed": seed,
        "truncation_probe_is_deterministic": True,
        "what_a_pass_means": (
            "no decision consumed information from beyond its own bar, through the view or "
            "through anything the strategy was constructed with. It does NOT certify the "
            "strategy is good, only that its inputs were legal. Out-of-band data the harness "
            "never supplies -- a file opened inside on_bar, a module global -- is outside what "
            "any re-run can detect and remains a code-review question."
        ),
    }


def run_backtest(
    series,
    strategy_factory,
    cost_model: CostModel,
    *,
    execution_lag_bars: int = 1,
    audit_probes: int = 6,
    audit_seed: int = 20260816,
    warmup_bars: int | None = None,
) -> BacktestResult:
    """Run one strategy over one bar series and return an auditable result.

    `strategy_factory` is a zero-argument callable returning a FRESH strategy. It is a
    factory rather than an instance because the audit must re-run from clean state; an
    instance carrying state from a previous pass would make the audit meaningless.
    """
    series = validate_series(series)

    if execution_lag_bars < MIN_EXECUTION_LAG_BARS:
        raise Refused(
            f"execution_lag_bars={execution_lag_bars} is refused. A signal computed from bar "
            "i's close cannot be filled at bar i's close: at the instant you knew the close, "
            "the close had already printed. The minimum honest lag is 1 bar, filled at the "
            "next bar's open. There is no flag to disable this."
        )

    probe = build_strategy(strategy_factory, series)
    if not isinstance(probe, Strategy):
        raise Refused("strategy_factory must return a Strategy subclass instance")
    warmup = probe.warmup_bars if warmup_bars is None else warmup_bars
    if warmup < 0:
        raise Refused(f"warmup_bars must be >= 0; got {warmup}")

    lag = execution_lag_bars
    last_decidable = len(series) - 1 - lag
    if last_decidable < warmup:
        raise Refused(
            f"{len(series)} bars leaves no decidable bar after warmup {warmup} and lag {lag}"
        )

    audit = lookahead_audit(
        series, strategy_factory, warmup=warmup, lag=lag, probes=audit_probes, seed=audit_seed,
    )

    decisions = _decide(
        series, build_strategy(strategy_factory, series), warmup, last_decidable
    )

    # Position effective at each bar's OPEN. The first mark point is the first bar that can
    # carry a decision: warmup + lag.
    first_mark = warmup + lag
    positions, timestamps = [], []
    held = Fraction(0)
    for j in range(first_mark, len(series)):
        source = j - lag
        if source in decisions:
            held = decisions[source]
        positions.append(held)
        timestamps.append(series[j].ts_ns)

    gross, net, costs, turnovers, market = [], [], [], [], []
    entry_turnovers, exit_turnovers = [], []
    previous = Fraction(0)
    for offset in range(len(positions) - 1):
        j = first_mark + offset
        bar, nxt = series[j], series[j + 1]
        pos = positions[offset]

        # PER SIDE. The lumped |pos - previous| is kept for reporting, but it is NOT what is
        # priced: an exit leg is charged the exit's spread and slippage, which is the whole
        # point of the T6 fix.
        entry_turnover, exit_turnover = split_turnover(previous, pos)
        turnover = entry_turnover + exit_turnover
        trade_cost = cost_model.trade_cost_fraction(
            bar.open_micros, entry_turnover=entry_turnover, exit_turnover=exit_turnover,
        )

        held_days = Fraction(nxt.ts_ns - bar.ts_ns, NS_PER_DAY)
        borrow = cost_model.borrow_cost_fraction(pos, held_days)

        move = Fraction(nxt.open_micros - bar.open_micros, bar.open_micros)
        gross_r = pos * move
        cost = trade_cost + borrow

        gross.append(gross_r)
        market.append(move)
        costs.append(cost)
        net.append(gross_r - cost)
        turnovers.append(turnover)
        entry_turnovers.append(entry_turnover)
        exit_turnovers.append(exit_turnover)
        previous = pos

    return BacktestResult(
        symbol=series[0].symbol,
        strategy=probe.describe(),
        execution_lag_bars=lag,
        warmup_bars=warmup,
        first_decision_index=warmup,
        bar_timestamps_ns=tuple(timestamps),
        positions=tuple(positions),
        targets=tuple(sorted(decisions.items())),
        returns=tuple(net),
        gross_returns=tuple(gross),
        market_returns=tuple(market),
        costs=tuple(costs),
        turnover=tuple(turnovers),
        cost_model=cost_model.to_report(),
        lookahead_audit=audit,
        entry_turnover=tuple(entry_turnovers),
        exit_turnover=tuple(exit_turnovers),
    )


__all__ = [
    "Bar", "validate_series", "PointInTimeView", "Strategy",
    "BacktestResult", "run_backtest", "lookahead_audit",
    "NS_PER_DAY", "MIN_EXECUTION_LAG_BARS",
]
