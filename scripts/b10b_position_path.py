#!/usr/bin/env python3
"""B10b — canonical OBSERVED-STATE position path evaluator. Phase 2, second bounded slice.

Offline, read-only, no network. Pure library: no server, no UI, no model, no signal, no wallet, no
signing, no live RPC. Schema in `docs/POSITION_PATH_SCHEMA.md`.

Given a decision state at t0, an explicit order and cost policy, and a chronologically ordered
sequence of LATER canonical reserve observations for the SAME mint, this module prices one
hypothetical entry and then marks that position to an executable-size-constrained exit at every
later observation, producing a drawdown path, liquidity states, reason codes and explicit
horizon/exit-rule outcomes.

WHAT THIS IS, STATED NARROWLY, BECAUSE THE WIDER READING WOULD BE FALSE
======================================================================

The later reserve observations came from a world in which **our hypothetical trade never
happened**. They are not counterfactual states and this module never calls them that. What it
computes is an *observed-state scenario diagnostic*: our entry's own price impact is priced
exactly against t0 (`b10a.price_entry`), our exit's own price impact is priced exactly against each
observed state, and nothing in between is adjusted. Every record therefore carries the label
`SIMULATED_OBSERVED_PATH`, which exists precisely so it cannot be read as `SIMULATED` round-trip
replay of a world containing our order.

**The unmodelled part, named so it cannot be quietly assumed.** Our entry would have removed
`tokens_out` from the real token reserve and added quote lamports to it. That perturbation would
persist into every later state, and other participants would have responded to it. This module does
not model persistence and does not model response. It also does **not** state the sign of the
resulting bias: see `no_valid_counterfactual_variant` below.

WHY THE OBVIOUS FIX IS REFUSED
==============================

The tempting repair is to add our reserve delta to each later observed state, or to replay the
observed orders against shifted reserves. Both are refused, and not for caution's sake — neither is
valid for any trade variant this venue offers:

- **exact-input buys** (`buy_exact_sol_in`, `buy_exact_quote_in`) pin the quote spent, so replaying
  one against shifted reserves yields a different token amount than the trader received. Their
  slippage bound is on the tokens out, and it is not in the reserve evidence.
- **legacy exact-token buys** (`buy`, `buy_v2`) pin the tokens received, so replaying one yields a
  different quote cost than the trader paid — possibly above the `max_sol_cost` they signed, in
  which case the real transaction would have FAILED and the observation would not exist.
- **sells** (`sell`, `sell_v2`) pin the tokens in and would yield different proceeds, likewise
  bounded by a `min_sol_output` the trader signed.

In every variant the order's *other* dimension moves, and in two of the three the trade may not
have landed at all. Beyond arithmetic, the decision to trade is itself not invariant to the price.
So there is no variant for which counterfactual replay is provably valid, and this module performs
none. A "small impact" assumption would supply the missing validity by assertion; none is made and
no tolerance exists anywhere in this file.

THREE THINGS THIS EVALUATOR REFUSES TO DO
=========================================

1. **It never lets a later observation reach the entry decision.** `decide_entry` has no path
   parameter, and the feature view handed to an entry policy is a scalar-only immutable mapping
   whose object graph is walked at runtime to prove no observation is reachable from it.
2. **It never accepts an ordering it cannot verify.** The canonical order is
   `(slot, transaction_index, outer_index, inner_index)`. Duplicates, backwards steps, a first
   observation at or before t0, and a foreign mint each fail closed.
3. **It never invents value it cannot realise.** Exit size is constrained by what the real quote
   reserve can actually pay, the unrealisable remainder is reported as tokens and never valued, a
   completed curve is structural unavailability rather than a mark, and a horizon the observation
   window does not reach is right-censored rather than scored.
"""
import argparse
import gc
import hashlib
import importlib.util
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B10A = _load("b10a_simulator_kernel", "b10a_simulator_kernel.py")
B9I = B10A.B9I
B9D = B10A.B9D
FreezeViolation = B10A.FreezeViolation

# Bumped when the result shape changes in a way a reader must notice. Consumers pin it. Independent
# of `b10a`'s version: these are different records with different claims behind them.
SCHEMA_VERSION = "1.0.0"

# Deliberately NOT `b10a`'s `SIMULATED`. That label covers a round trip priced against two states.
# This one additionally asserts that the later states are OBSERVED — drawn from a world without our
# order — and a reader who conflates the two would be reading a counterfactual claim this module
# does not make.
OUTCOME_SIMULATED_OBSERVED_PATH = "SIMULATED_OBSERVED_PATH"
CALIBRATION_UNCALIBRATED = B10A.CALIBRATION_UNCALIBRATED

# Travels with every record. A field is cheaper to read than a document.
LIMITATION_OBSERVED_STATES = (
    "Later states are OBSERVED, from a world without our hypothetical trade. Our entry's own "
    "reserve impact is priced at t0 and our exit's own reserve impact is priced at each observed "
    "state, but the persistence of our entry impact into later states, and other participants' "
    "response to it, are NOT modelled. The sign of the resulting bias is not determined here.")
LIMITATION_NO_COUNTERFACTUAL = (
    "No reserve delta is added to any later state and no observed order is replayed "
    "counterfactually. No trade variant makes that provably valid: exact-input buys pin the quote, "
    "legacy buys pin the tokens, sells pin the tokens, and each carries a signed slippage bound "
    "that the shifted price may violate, in which case the observed transaction would not exist.")
LIMITATION_NO_LATENCY = (
    "No latency between observing a state and landing a transaction is modelled. The t0 decision "
    "state is stated by the caller and entry is priced against it exactly, as in b10a.")

CANONICAL_ORDER = B10A.CANONICAL_ORDER

# The full canonical coordinate is required here, where b10a required only `slot`. A slot-level
# ordering check cannot separate two observations in the same slot, and this module's whole subject
# is the order of states within a path.
COORDINATE_FIELDS = CANONICAL_ORDER
STATE_FIELDS = ("virtual_quote", "virtual_token", "real_quote", "real_token",
                "quote_mint", "mayhem_mode", "complete", "slot")

# Everything an entry policy may see. Scalars only, copied out of t0, wrapped immutably, and the
# resulting object graph is walked before the policy is called.
ENTRY_FEATURE_FIELDS = STATE_FIELDS + ("transaction_index", "outer_index", "inner_index")

# Liquidity states. `L3_structural_unavailable` is b10a's constant, reused rather than restated.
#
# `L1m` is NOT the L1 of `docs/EXECUTABLE_RETURN.md` §3. That L1 is an ECONOMIC condition —
# "`real_quote_reserves` below the minimum economically meaningful exit" — and §3 deliberately
# leaves its threshold unfrozen, because choosing one after seeing the outcome distribution is the
# selection the preregistration apparatus exists to prevent. `L1m` is the strictly MECHANICAL floor
# underneath it: the largest executable size pays zero lamports gross. It chooses no threshold, it
# reports where the integer arithmetic runs out, and the economic L1 remains open.
L0_FULL = "L0_full_size_executable"
L1M_NO_EXECUTABLE_SIZE = "L1m_no_executable_size"
L2_SIZE_CONSTRAINED = "L2_size_constrained"
L3_STRUCTURAL_UNAVAILABLE = B10A.L3_CURVE_COMPLETE

REASON_FULL_SIZE = "priced_full_size"
REASON_SIZE_CONSTRAINED = "priced_size_constrained"
REASON_NO_EXECUTABLE_SIZE = "no_executable_size"
REASON_CURVE_COMPLETE = "curve_complete"
REASON_INTRA_TRANSACTION = "exit_unreachable_intra_transaction"

# Path terminal states.
TERMINAL_STRUCTURAL_UNAVAILABILITY = "structural_unavailability"
TERMINAL_RIGHT_CENSORED = "path_exhausted_right_censored"

# Exit-rule outcomes. `right_censored` is neither success nor failure and must never be counted as
# either: it is `DEFINITIONS.md` C1 administrative censoring applied to a rule instead of a token.
RULE_TRIGGERED = "triggered"
RULE_RIGHT_CENSORED = "right_censored"
RULE_STRUCTURALLY_UNAVAILABLE = "structurally_unavailable"

RULE_SLOT_HORIZON = "slot_horizon"
RULE_OBSERVATION_HORIZON = "observation_horizon"
RULE_FIRST_FULL_SIZE_EXIT = "first_full_size_exit"
RULE_TERMINAL_OBSERVATION = "terminal_observation"
RULE_NET_AT_OR_BELOW = "net_value_at_or_below"
RULE_NET_AT_OR_ABOVE = "net_value_at_or_above"
RULE_KINDS = (RULE_SLOT_HORIZON, RULE_OBSERVATION_HORIZON, RULE_FIRST_FULL_SIZE_EXIT,
              RULE_TERMINAL_OBSERVATION, RULE_NET_AT_OR_BELOW, RULE_NET_AT_OR_ABOVE)


class PathRefused(FreezeViolation):
    """Raised when the evaluator cannot honestly evaluate the path it was given."""


# --------------------------------------------------------------------------------------------
# Canonical ordering
# --------------------------------------------------------------------------------------------

def canonical_key(record):
    """The canonical coordinate, as a comparable tuple. Insertion order is never an ordering."""
    key = []
    for field in COORDINATE_FIELDS:
        if field not in record:
            raise PathRefused(
                f"record has no {field}; the canonical order is {list(COORDINATE_FIELDS)} and a "
                "record missing any component cannot be placed in it")
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise PathRefused(f"canonical coordinate {field} must be an integer, got {value!r}")
        key.append(value)
    return tuple(key)


def assert_canonical_sequence(observations, *, mint, after):
    """Every observation is for `mint`, strictly after `after`, and strictly increasing.

    Duplicates, backwards steps and a foreign mint each raise. This function is the only route by
    which a path enters the evaluator, so an unordered path cannot be evaluated by accident.
    """
    if isinstance(observations, (dict, str, bytes)):
        raise PathRefused("observations must be a sequence of observation mappings")
    ordered = list(observations)
    previous = canonical_key(after)
    for position, observation in enumerate(ordered):
        if not isinstance(observation, dict):
            raise PathRefused(
                f"observation {position} is {type(observation).__name__}, not a mapping")
        if observation.get("mint") != mint:
            raise PathRefused(
                f"observation {position} is for mint {observation.get('mint')!r}, not {mint!r}; a "
                "path mixing mints is not a path")
        key = canonical_key(observation)
        if key == previous:
            raise PathRefused(
                f"observation {position} repeats canonical coordinate {key}; a duplicate "
                "observation would double-count a state")
        if key < previous:
            raise PathRefused(
                f"observation {position} at {key} precedes {previous}; the sequence is not in "
                f"canonical order {list(CANONICAL_ORDER)}. Database insertion order is not an "
                "ordering")
        previous = key
    return ordered


# --------------------------------------------------------------------------------------------
# The leakage barrier
# --------------------------------------------------------------------------------------------

def _reachable_object_ids(root, limit=10_000, keep=False):
    """Every object reachable from `root` by reference, keyed by id, bounded.

    Bounded because an unbounded walk from an arbitrary object reaches the interpreter. The bound is
    an error if hit, never a silent truncation: a truncated walk would report "no leak found" for
    the graph it did not finish looking at.
    """
    seen, frontier = {}, [root]
    while frontier:
        current = frontier.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen[identity] = current if keep else None
        if len(seen) > limit:
            raise PathRefused(
                f"entry feature view reaches more than {limit} objects; it is supposed to be a "
                "handful of scalars, so a graph this size means something else got in")
        frontier.extend(gc.get_referents(current))
    return seen


# Everything the entry feature view's object graph is allowed to contain. A container of any other
# kind is a route to whatever it holds, and the future is the thing most worth holding.
#
# `None` is on the list because it has no referents at all and so cannot be a route to anything.
# It does NOT thereby become an acceptable feature: `entry_feature_view` still refuses a t0 field
# whose value is None, by a separate per-field check. This list governs the reachability walk,
# which downstream callers (b10c) also run over records that legitimately carry nulls.
ALLOWED_VIEW_TYPES = (types.MappingProxyType, dict, int, str, bool, type(None))


def entry_feature_view(t0_state, observations=()):
    """A scalar-only immutable view of the decision state, proven to reach nothing else.

    The proof is not a comment. The whole object graph reachable from the returned view is walked
    and every object in it must be a mapping or a scalar; anything else raises. That check is
    meaningful WITHOUT knowing what the future contains, which matters because `decide_entry` — the
    only caller in the evaluator — has no access to the future and so cannot pass it here to be
    excluded. `observations` is the stronger, identity-based check, available to a caller that does
    hold a path (the test suite does); the view is built before it is consulted and no value in it
    is ever read.
    """
    if not isinstance(t0_state, dict):
        raise PathRefused(f"t0 state must be a mapping, got {type(t0_state).__name__}")
    view = {}
    for field in ENTRY_FEATURE_FIELDS:
        if field not in t0_state:
            raise PathRefused(
                f"t0 state has no {field}; an entry feature the decision state does not carry "
                "cannot be supplied from anywhere else without leaking")
        value = t0_state[field]
        if not isinstance(value, (int, str, bool)):
            raise PathRefused(
                f"t0 feature {field} is {type(value).__name__}; only scalars may cross into an "
                "entry policy, because a container is a route to whatever it holds")
        view[field] = value
    frozen = types.MappingProxyType(view)
    assert_no_future_reachable(frozen, observations)
    return frozen


def assert_no_future_reachable(view, observations=()):
    """Two checks on the reference graph reachable from an entry feature view.

    The first is that every reachable object is a mapping or a scalar. It needs no knowledge of the
    future, which is what makes it usable by `decide_entry` — the one caller that by construction
    cannot see the path. The second is identity: none of `observations` may be reachable. It is
    strictly stronger and strictly narrower, available to a caller that does hold a path.
    """
    reachable = _reachable_object_ids(view, keep=True)
    for obj in reachable.values():
        if not isinstance(obj, ALLOWED_VIEW_TYPES):
            raise PathRefused(
                f"the entry feature view reaches a {type(obj).__name__}; only mappings and scalars "
                "may be reachable, because any other container is a route out of the decision "
                "instant")
    forbidden = {id(observation) for observation in observations}
    if forbidden & set(reachable):
        raise PathRefused(
            "an observation from the path is reachable from the entry feature view; entry pricing "
            "would be able to read the future")
    return True


def decide_entry(t0_state, schedule, cost_policy, *, order=None, entry_policy=None):
    """Price the entry from t0 alone.

    This function HAS NO PATH PARAMETER. That is the leakage boundary, made structural rather than
    promised: there is no argument through which a later observation could arrive, so no future
    version of the caller can pass one without changing this signature and the test that pins it.
    """
    if (order is None) == (entry_policy is None):
        raise PathRefused(
            "state exactly one of `order` or `entry_policy`; two sources of order size would let "
            "one silently win, and neither is a default")
    if entry_policy is not None:
        if not callable(entry_policy):
            raise PathRefused("entry_policy must be callable")
        order = entry_policy(entry_feature_view(t0_state))
        if not isinstance(order, dict):
            raise PathRefused(
                f"entry policy returned {type(order).__name__}, not an order mapping")
    return B10A.price_entry(t0_state, order, schedule, cost_policy)


# --------------------------------------------------------------------------------------------
# Executable-size-constrained exit
# --------------------------------------------------------------------------------------------

def max_executable_tokens(virtual_quote, virtual_token, real_quote, tokens_held):
    """The largest size the real quote reserve can actually pay for, exactly.

    `quote_out_for_tokens_in` is non-decreasing in `tokens_in`, so the executable sizes form a
    prefix and a binary search finds its end. Maximality is then PROVEN on the result rather than
    trusted: one more token must overdraw the reserve. No tolerance, no epsilon, no sampling.
    """
    for label, value in (("virtual_quote", virtual_quote), ("virtual_token", virtual_token),
                         ("real_quote", real_quote), ("tokens_held", tokens_held)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PathRefused(f"{label} must be a non-negative integer, got {value!r}")
    if virtual_quote <= 0 or virtual_token <= 0:
        raise PathRefused(
            f"virtual reserves ({virtual_quote}, {virtual_token}) are non-positive; the curve is "
            "undefined")
    low, high = 0, tokens_held
    while low < high:
        middle = (low + high + 1) // 2
        if B9I.quote_out_for_tokens_in(virtual_quote, virtual_token, middle) <= real_quote:
            low = middle
        else:
            high = middle - 1
    gross = B9I.quote_out_for_tokens_in(virtual_quote, virtual_token, low)
    if gross > real_quote:
        raise PathRefused(
            f"executable size {low} draws {gross} lamports against a reserve of {real_quote}; the "
            "size search is wrong and the result would be proceeds no counterparty can pay")
    if low < tokens_held:
        next_gross = B9I.quote_out_for_tokens_in(virtual_quote, virtual_token, low + 1)
        if next_gross <= real_quote:
            raise PathRefused(
                f"size {low + 1} is also executable ({next_gross} <= {real_quote}) but was not "
                "selected; the size search did not return the maximum")
    return low, gross


def mark_to_exit(state, tokens_held, schedule, cost_policy):
    """Mark a position to a size-constrained exit against ONE observed state.

    Returns a record whose `realizable_net_lamports` is the value of what could actually be sold,
    never of what is merely held. The remainder is reported as tokens and is NOT valued: pricing it
    at the marginal rate would report proceeds the reserve cannot pay, and pricing it at zero would
    assert a loss the evidence does not show.
    """
    B10A.assert_eligible_state(state, when="observed")
    B10A.assert_cost_policy(cost_policy)
    B10A.assert_fee_schedule(schedule)
    for field in ("real_quote", "real_token"):
        value = state[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PathRefused(f"observed {field} must be a non-negative integer, got {value!r}")
    if isinstance(tokens_held, bool) or not isinstance(tokens_held, int) or tokens_held < 0:
        raise PathRefused(f"tokens_held must be a non-negative integer, got {tokens_held!r}")

    if state["complete"]:
        return {"liquidity": L3_STRUCTURAL_UNAVAILABLE, "reason": REASON_CURVE_COMPLETE,
                "tokens_held": tokens_held, "tokens_executable": 0,
                "tokens_unrealizable": tokens_held,
                "gross_exit_lamports": None, "realizable_net_lamports": None,
                "curve_fees": None, "execution_costs": None, "exit": None,
                "state_slot": state["slot"]}

    executable, gross = max_executable_tokens(
        state["virtual_quote"], state["virtual_token"], state["real_quote"], tokens_held)
    if gross == 0:
        # Nothing can be sold for even one lamport. No transaction would be submitted, so no
        # execution cost is charged: a fee for a trade nobody makes is an invented cost, and the
        # symmetric error to an invented proceed.
        return {"liquidity": L1M_NO_EXECUTABLE_SIZE, "reason": REASON_NO_EXECUTABLE_SIZE,
                "tokens_held": tokens_held, "tokens_executable": 0,
                "tokens_unrealizable": tokens_held,
                "gross_exit_lamports": 0, "realizable_net_lamports": 0,
                "curve_fees": None, "execution_costs": None, "exit": None,
                "state_slot": state["slot"]}

    # By construction `gross <= real_quote`, which is exactly the condition `b10a.price_exit`
    # refuses to violate. Calling it rather than reimplementing it keeps one exit-pricing
    # implementation in the project: a second copy drifts from the gate that validates the first.
    priced = B10A.price_exit(state, executable, schedule, cost_policy)
    if priced["quote_lamports"] != gross:
        raise PathRefused(
            f"size search and b10a disagree on the gross exit ({gross} vs "
            f"{priced['quote_lamports']}); one of the two is not the venue's arithmetic")
    full = executable == tokens_held
    return {
        "liquidity": L0_FULL if full else L2_SIZE_CONSTRAINED,
        "reason": REASON_FULL_SIZE if full else REASON_SIZE_CONSTRAINED,
        "tokens_held": tokens_held,
        "tokens_executable": executable,
        "tokens_unrealizable": tokens_held - executable,
        "gross_exit_lamports": gross,
        "realizable_net_lamports": priced["lamports_into_wallet"],
        "curve_fees": priced["curve_fees"],
        "execution_costs": priced["execution_costs"],
        "exit": priced,
        "state_slot": state["slot"],
    }


# --------------------------------------------------------------------------------------------
# Path evaluation
# --------------------------------------------------------------------------------------------

def _observed_state(observation):
    """The curve state an exit of ours would face after this observation.

    `complete` and the reserves come from the observation itself. The caller builds them; this only
    projects the b10a-shaped state out, so `assert_eligible_state` governs both modules.
    """
    return {field: observation[field] for field in STATE_FIELDS if field in observation}


def _coordinate(record):
    return {field: record[field] for field in COORDINATE_FIELDS}


def evaluate_position_path(t0_state, observations, schedule, cost_policy, *,
                           mint, order=None, entry_policy=None, exit_rules=(), evidence=None):
    """One entry at t0, marked to a constrained exit at every later observed state.

    The entry is decided and priced BEFORE any observation is read, through a function that has no
    path parameter. Everything after that is outcome.
    """
    if not isinstance(mint, str) or not mint:
        raise PathRefused("mint must be a non-empty string; a path without a mint cannot be "
                          "checked for contamination")
    B10A.assert_fee_schedule(schedule)
    B10A.assert_cost_policy(cost_policy)
    canonical_key(t0_state)
    B10A.assert_eligible_state(t0_state, when="t0")
    if t0_state.get("mint") is not None and t0_state["mint"] != mint:
        raise PathRefused(
            f"t0 state is for mint {t0_state['mint']!r}, not {mint!r}")

    path = assert_canonical_sequence(observations, mint=mint, after=t0_state)
    entry = decide_entry(t0_state, schedule, cost_policy, order=order, entry_policy=entry_policy)
    tokens_held = entry["tokens_out"]

    marks, terminal, dropped = [], TERMINAL_RIGHT_CENSORED, 0
    for index, observation in enumerate(path):
        if terminal == TERMINAL_STRUCTURAL_UNAVAILABILITY:
            dropped += 1
            continue
        state = _observed_state(observation)
        if not observation.get("is_transaction_terminal", True):
            # Our exit is its own transaction and cannot land inside somebody else's. A state that
            # exists only part-way through another transaction is therefore not a state we could
            # ever trade against, and marking a position to it would report a price nobody could
            # have taken. It is recorded, not evaluated.
            marks.append({
                "index": index, "coordinate": _coordinate(observation),
                "evaluable": False, "liquidity": None, "reason": REASON_INTRA_TRANSACTION,
                "mark": None, "realizable_net_lamports": None,
                "net_versus_entry_lamports": None,
                "running_peak_lamports": None, "drawdown_lamports": None})
            continue
        mark = mark_to_exit(state, tokens_held, schedule, cost_policy)
        evaluable = mark["realizable_net_lamports"] is not None
        if mark["liquidity"] == L3_STRUCTURAL_UNAVAILABLE:
            terminal = TERMINAL_STRUCTURAL_UNAVAILABILITY
        marks.append({
            "index": index, "coordinate": _coordinate(observation),
            "evaluable": evaluable, "liquidity": mark["liquidity"], "reason": mark["reason"],
            "mark": mark,
            "realizable_net_lamports": mark["realizable_net_lamports"],
            "net_versus_entry_lamports": (
                None if not evaluable
                else mark["realizable_net_lamports"] - entry["lamports_out_of_wallet"]),
            "running_peak_lamports": None, "drawdown_lamports": None})

    drawdown = _annotate_drawdown(marks)
    rules = [_evaluate_rule(rule, marks, t0_state, terminal) for rule in exit_rules]
    return {
        "schema_version": SCHEMA_VERSION,
        "outcome_label": OUTCOME_SIMULATED_OBSERVED_PATH,
        "calibration": CALIBRATION_UNCALIBRATED,
        "limitations": [LIMITATION_OBSERVED_STATES, LIMITATION_NO_COUNTERFACTUAL,
                        LIMITATION_NO_LATENCY],
        "mint": mint,
        "evidence": evidence or {},
        "t0": _coordinate(t0_state),
        "entry": entry,
        "observations_supplied": len(path),
        "observations_evaluated": sum(1 for mark in marks if mark["evaluable"]),
        "observations_recorded_not_evaluated": sum(1 for mark in marks if not mark["evaluable"]),
        "observations_dropped_after_completion": dropped,
        "marks": marks,
        "drawdown": drawdown,
        "terminal_state": terminal,
        "terminal_coordinate": (_coordinate(path[-1]) if path else None),
        "exit_rules": rules,
        "fee_schedule": dict(schedule),
        "cost_policy": dict(cost_policy),
    }


def _annotate_drawdown(marks):
    """Peak-to-trough drawdown on the realisable NET exit value path, in exact lamports.

    The ratio is reported as an exact numerator/denominator pair, never a float, and only when the
    running peak is strictly positive. A ratio against a peak of zero or less is not a small number,
    it is an undefined one, and reporting `0.0` or `inf` there would invent a drawdown figure for a
    position that never had value to lose.
    """
    peak = None
    peak_index = trough_index = None
    worst = 0
    worst_peak = None
    for mark in marks:
        if not mark["evaluable"]:
            continue
        value = mark["realizable_net_lamports"]
        if peak is None or value > peak:
            peak, peak_index = value, mark["index"]
        mark["running_peak_lamports"] = peak
        fall = peak - value
        mark["drawdown_lamports"] = fall
        if fall > worst:
            worst, worst_peak, trough_index = fall, peak, mark["index"]
    if peak is None:
        return {"evaluable_points": 0, "peak_lamports": None, "trough_lamports": None,
                "peak_index": None, "trough_index": None, "max_drawdown_lamports": None,
                "max_drawdown_peak_lamports": None,
                "max_drawdown_ratio_numerator": None, "max_drawdown_ratio_denominator": None,
                "series": "realizable_net_exit_value"}
    ratio_numerator = ratio_denominator = None
    if worst > 0 and worst_peak is not None and worst_peak > 0:
        ratio_numerator, ratio_denominator = worst, worst_peak
    return {
        "evaluable_points": sum(1 for mark in marks if mark["evaluable"]),
        # The GLOBAL maximum of the value path. Not necessarily the peak the worst drawdown fell
        # from — a later, higher peak followed by a shallow fall leaves the deepest drop behind an
        # earlier one — so the drawdown's own peak is reported separately rather than inferred.
        "peak_lamports": peak,
        "peak_index": peak_index,
        "max_drawdown_peak_lamports": worst_peak,
        "trough_lamports": (None if trough_index is None else worst_peak - worst),
        "trough_index": trough_index,
        "max_drawdown_lamports": worst,
        "max_drawdown_ratio_numerator": ratio_numerator,
        "max_drawdown_ratio_denominator": ratio_denominator,
        "series": "realizable_net_exit_value",
    }


def _rule_int(rule, field):
    value = rule.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PathRefused(f"exit rule {rule.get('name')!r} needs an integer {field}, got {value!r}")
    return value


def _evaluate_rule(rule, marks, t0_state, terminal):
    """One caller-stated exit rule against the mark path.

    The evaluator chooses no rule and proposes none. Every rule here is supplied by the caller, and
    a rule that never fires is RIGHT-CENSORED — not a loss, not a win, and not a zero.
    """
    if not isinstance(rule, dict):
        raise PathRefused(f"exit rule must be a mapping, got {type(rule).__name__}")
    kind = rule.get("kind")
    if kind not in RULE_KINDS:
        raise PathRefused(
            f"exit rule kind {kind!r} is not one of {list(RULE_KINDS)}; the evaluator does not "
            "interpret an unknown rule")
    name = rule.get("name") or kind
    evaluable = [mark for mark in marks if mark["evaluable"]]

    hit = None
    if kind == RULE_SLOT_HORIZON:
        target = t0_state["slot"] + _rule_int(rule, "slots")
        hit = next((m for m in evaluable if m["coordinate"]["slot"] >= target), None)
        detail = {"target_slot": target}
    elif kind == RULE_OBSERVATION_HORIZON:
        count = _rule_int(rule, "count")
        if count <= 0:
            raise PathRefused(f"exit rule {name!r} needs a positive count, got {count}")
        hit = evaluable[count - 1] if len(evaluable) >= count else None
        detail = {"required_evaluable_observations": count,
                  "available_evaluable_observations": len(evaluable)}
    elif kind == RULE_FIRST_FULL_SIZE_EXIT:
        hit = next((m for m in evaluable if m["liquidity"] == L0_FULL), None)
        detail = {}
    elif kind == RULE_TERMINAL_OBSERVATION:
        hit = evaluable[-1] if evaluable else None
        detail = {}
    elif kind == RULE_NET_AT_OR_BELOW:
        floor = _rule_int(rule, "lamports")
        hit = next((m for m in evaluable if m["realizable_net_lamports"] <= floor), None)
        detail = {"threshold_lamports": floor}
    else:
        target_value = _rule_int(rule, "lamports")
        hit = next((m for m in evaluable if m["realizable_net_lamports"] >= target_value), None)
        detail = {"threshold_lamports": target_value}

    if hit is not None:
        return {"name": name, "kind": kind, "detail": detail, "outcome": RULE_TRIGGERED,
                "at": hit["coordinate"], "index": hit["index"],
                "liquidity": hit["liquidity"],
                "realizable_net_lamports": hit["realizable_net_lamports"],
                "net_versus_entry_lamports": hit["net_versus_entry_lamports"],
                "censoring": None}
    if terminal == TERMINAL_STRUCTURAL_UNAVAILABILITY:
        return {"name": name, "kind": kind, "detail": detail,
                "outcome": RULE_STRUCTURALLY_UNAVAILABLE, "at": None, "index": None,
                "liquidity": L3_STRUCTURAL_UNAVAILABLE, "realizable_net_lamports": None,
                "net_versus_entry_lamports": None,
                "censoring": "curve completed before the rule could fire; curve trading has ended "
                             "and this regime has no exit venue after it"}
    return {"name": name, "kind": kind, "detail": detail, "outcome": RULE_RIGHT_CENSORED,
            "at": None, "index": None, "liquidity": None, "realizable_net_lamports": None,
            "net_versus_entry_lamports": None,
            "censoring": "the rule did not fire within the observation window; right-censored at "
                         "the last observation (DEFINITIONS.md C1), not scored as an outcome"}


# --------------------------------------------------------------------------------------------
# Arithmetic invariants, deterministic serialisation
# --------------------------------------------------------------------------------------------

def assert_path_arithmetic(result):
    """Re-derive every priced quantity independently and refuse any disagreement.

    This exists because a path evaluator can be internally consistent and still wrong. Each check
    recomputes from the pinned curve functions rather than from the record's own neighbouring
    fields, so a mistake cannot validate itself.
    """
    entry = result["entry"]
    fees = entry["curve_fees"]
    if entry["lamports_out_of_wallet"] != (entry["quote_lamports"] + fees["charged_total"]
                                           + entry["execution_costs"]["total"]):
        raise PathRefused("entry outlay is not quote + charged fees + execution costs")
    if fees["charged_total"] != fees["fee"] + fees["creator_fee"] + fees["cashback"]:
        raise PathRefused("entry charged fee total does not equal its components")

    previous = None
    for mark in result["marks"]:
        key = tuple(mark["coordinate"][field] for field in COORDINATE_FIELDS)
        if previous is not None and key <= previous:
            raise PathRefused(f"mark coordinates are not strictly increasing at {key}")
        previous = key
        detail = mark["mark"]
        if detail is None or detail["exit"] is None:
            continue
        state_quote = detail["exit"]["quote_lamports"]
        exit_fees = detail["curve_fees"]
        if exit_fees["charged_total"] != (
                exit_fees["fee"] + exit_fees["creator_fee"] + exit_fees["cashback"]):
            raise PathRefused(f"exit charged fee total does not equal its components at {key}")
        if detail["realizable_net_lamports"] != (
                state_quote - exit_fees["charged_total"] - detail["execution_costs"]["total"]):
            raise PathRefused(f"realizable net is not gross - fees - execution at {key}")
        if detail["tokens_executable"] + detail["tokens_unrealizable"] != detail["tokens_held"]:
            raise PathRefused(f"executable and unrealizable tokens do not sum to held at {key}")
        if detail["tokens_held"] != result["entry"]["tokens_out"]:
            raise PathRefused(f"mark holds a size the entry did not buy at {key}")

    peak = None
    for mark in result["marks"]:
        if not mark["evaluable"]:
            continue
        value = mark["realizable_net_lamports"]
        peak = value if peak is None or value > peak else peak
        if mark["running_peak_lamports"] != peak:
            raise PathRefused(f"running peak disagrees with the value path at {mark['index']}")
        if mark["drawdown_lamports"] != peak - value:
            raise PathRefused(f"drawdown disagrees with peak minus value at {mark['index']}")
    return True


def canonical_json(record):
    """Byte-stable serialisation. Sorted keys, no insignificant whitespace, no floats anywhere."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def record_hash(record):
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true",
                        help="print the contract, labels and limitations this module claims")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`, or use b10b_path_dataset.py")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "outcome_label": OUTCOME_SIMULATED_OBSERVED_PATH,
        "calibration": CALIBRATION_UNCALIBRATED,
        "canonical_order": list(CANONICAL_ORDER),
        "liquidity_states": [L0_FULL, L2_SIZE_CONSTRAINED, L1M_NO_EXECUTABLE_SIZE,
                             L3_STRUCTURAL_UNAVAILABLE],
        "exit_rule_kinds": list(RULE_KINDS),
        "rule_outcomes": [RULE_TRIGGERED, RULE_RIGHT_CENSORED, RULE_STRUCTURALLY_UNAVAILABLE],
        "limitations": [LIMITATION_OBSERVED_STATES, LIMITATION_NO_COUNTERFACTUAL,
                        LIMITATION_NO_LATENCY],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FreezeViolation as error:
        print(f"FreezeViolation: {error}", file=sys.stderr)
        sys.exit(2)
