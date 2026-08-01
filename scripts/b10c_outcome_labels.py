#!/usr/bin/env python3
"""B10c — leakage-safe simulated outcome label materializer. Phase 3-compatible, Phase 2 evidence.

Offline, read-only, no network. Pure library: no server, no UI, no model, no signal, no baseline,
no split, no wallet, no signing, no live RPC. Schema in `docs/OUTCOME_LABEL_SCHEMA.md`.

Turns `b10b` observed-state path records into one row per **preregistered decision x horizon**,
carrying the decision's t0 identity, the horizon's geometry, an exact-rational simulated return, an
exact-rational maximum drawdown, the liquidity or unavailability state, the censoring reason, and
evidence hashes. It computes labels. It does not compute a strategy, select an entry, or score one.

THE ASYMMETRY THIS MODULE EXISTS TO ENFORCE
===========================================

`DECISIONS.md` R1: *"fix decision instant t0 at the feature-vector timestamp; the label window is
`(t0, t0+H]`, and no feature may read an observation made after t0."*

**A label MAY read observations after t0. A feature MAY NOT.** Both halves live in one row here, so
the boundary has to be structural rather than remembered:

1. Every field is declared in exactly one of `DECISION_FIELDS` or `OUTCOME_FIELDS`, and a row whose
   keys are not exactly that disjoint union is refused. A new field cannot be added without saying
   which side of t0 it comes from.
2. `build_decision_facts` **has no parameter through which a mark could arrive** — no path, no
   result, no horizon — and a test pins its signature.
3. At merge time the decision block's whole reference graph is walked and refused if any mark from
   the path is reachable from it. `b10b` could not run that check at `decide_entry`, which by
   construction cannot see the future; this module holds both sides, so it can.
4. The decision block is asserted **identical across every horizon of the same decision**. Horizons
   are post-t0 geometry, so anything that varies with them has crossed the line.

THE WINDOW IS BURNED, AND WAS BURNED BEFORE THIS MODULE EXISTED
==============================================================

Every `CreateEvent` in the `b10b` corpus falls inside `[433,894,233, 434,097,833]`, which
`DECISIONS.md` (2026-07-28) burned for future cohort selection, and which R3 forbids measuring or
tuning any label on. So `window_status` is a **required** preregistration field, the only accepted
value is `burned_development`, and every row carries it. Counts produced here validate plumbing,
accounting and determinism. **They are not findings, they select nothing, and no threshold, horizon
or class may be carried out of them.**

THREE THINGS THIS MATERIALIZER REFUSES TO DO
============================================

1. **It never chooses a horizon.** There is no default anywhere in this file. Horizons are supplied
   in a preregistration document that must carry an identifier, and its SHA-256 is stamped on every
   row so a later reader can tell which document produced which number.
2. **It never builds a success label.** A horizon selected by realised value — a stop, a target, or
   "exit at the first fully executable moment" — is an oracle exit embedding a decision no strategy
   could have made. Those `b10b` rule kinds are refused by name, with the reason attached.
3. **It never turns absence of evidence into a number.** A right-censored horizon has a NULL return,
   not zero and not minus one. A completed curve is `structural_exit_unavailable`, never valued
   through PumpSwap. A curve we would not have entered still produces rows, so the denominator stays
   the whole cohort rather than the part that happened to be tradable.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B10B = _load("b10b_position_path", "b10b_position_path.py")
B10A = B10B.B10A
B9I = B10B.B9I
FreezeViolation = B10B.FreezeViolation

SCHEMA_VERSION = "1.0.0"

# Distinct from b10b's record label. A row here is a LABEL derived from an observed-state path, not
# the path itself, and it carries a horizon the path record knows nothing about.
LABEL_KIND = "SIMULATED_OBSERVED_PATH_LABEL"

# The only window status this project can honestly declare today. Adding a value requires a
# DECISIONS.md entry naming a fresh preregistered window disjoint from every burned range (R3), so
# the enum is the gate rather than a comment asking for one.
WINDOW_BURNED_DEVELOPMENT = "burned_development"
ALLOWED_WINDOW_STATUS = (WINDOW_BURNED_DEVELOPMENT,)

HORIZON_SLOT = "slot_horizon"
HORIZON_OBSERVATION = "observation_horizon"
HORIZON_ADMINISTRATIVE = "administrative_window_end"
HORIZON_KINDS = (HORIZON_SLOT, HORIZON_OBSERVATION, HORIZON_ADMINISTRATIVE)

# Refused by name rather than merely absent, so the reason travels with the refusal.
REFUSED_HORIZON_KINDS = {
    B10B.RULE_NET_AT_OR_BELOW:
        "a horizon selected by realised value is a stop, and a stop chosen after the outcome is "
        "visible is a profitability class, not a horizon",
    B10B.RULE_NET_AT_OR_ABOVE:
        "a horizon selected by realised value is a target, and a target chosen after the outcome "
        "is visible is a profitability class, not a horizon",
    B10B.RULE_FIRST_FULL_SIZE_EXIT:
        "selecting the exit instant by an outcome property is an oracle exit; the label would "
        "embed a decision no strategy could have made at t0",
}

OUTCOME_MARKED = "marked_at_horizon"
OUTCOME_RIGHT_CENSORED = "right_censored"
OUTCOME_STRUCTURAL_UNAVAILABLE = "structural_exit_unavailable"
OUTCOME_NO_OBSERVED_STATE = "no_observed_state_in_window"
OUTCOME_NO_DECISION = "no_decision"
OUTCOME_STATUSES = (OUTCOME_MARKED, OUTCOME_RIGHT_CENSORED, OUTCOME_STRUCTURAL_UNAVAILABLE,
                    OUTCOME_NO_OBSERVED_STATE, OUTCOME_NO_DECISION)

# Kept separate from `right_censored` on purpose. Right-censoring is a statement about window
# geometry: the horizon lies past the end of what was recorded. This is a different thing — the
# window covers the horizon and simply contains no canonical observation after t0. The only state
# available is then t0's own, and our own entry has already changed it, so pricing an exit against
# it would price our own impact away. That is the one place where this project's standing
# limitation stops being a residual and becomes the entire content of the label, so it gets its own
# status instead of being folded into censoring.
NO_OBSERVED_STATE_REASON = (
    "no canonical observation lies inside the label window (t0, t0+H], so the only state available "
    "is t0's own — which our hypothetical entry has already changed. Pricing an exit against it "
    "would price our own impact away, so no value is reported and none is inferred")

# Why no position exists to label. Every one is a property of t0 or of the corpus, never of an
# outcome, so a no-decision row leaks nothing by existing.
NO_DECISION_REASONS = (
    "out_of_regime_non_sol_quote", "out_of_regime_mayhem", "out_of_regime_mixed_within_curve",
    "no_transaction_terminal_state", "no_later_observation", "entry_refused")

# --------------------------------------------------------------------------------------------
# The field partition. This IS the leakage boundary; everything else enforces it.
# --------------------------------------------------------------------------------------------

DECISION_FIELDS = (
    "schema_version", "label_kind", "calibration", "window_status",
    "preregistration_id", "preregistration_sha256",
    "dataset_content_sha256",
    "mint", "bonding_curve",
    "t0_slot", "t0_transaction_index", "t0_outer_index", "t0_inner_index",
    "t0_virtual_quote", "t0_virtual_token", "t0_real_quote", "t0_real_token",
    # Grouping identities, all published at or before t0. R5 requires splitting by at least
    # `creator union user`; these are the raw keys that grouping will need. The grouping itself is
    # Phase 3 and is deliberately NOT implemented here.
    "creator", "create_user", "t0_user",
    "split_key_creator", "split_key_creator_union_t0_user",
    "order_quote_lamports", "entry_tokens_out", "entry_outlay_lamports",
    "entry_curve_fee_lamports", "entry_execution_cost_lamports",
    "fee_schedule_sha256", "cost_policy_sha256",
    "decision_sha256",
    "no_decision_reason",
)

OUTCOME_FIELDS = (
    "horizon_name", "horizon_kind", "horizon_parameter", "horizon_is_administrative",
    "horizon_target_slot", "observation_window_end_slot",
    "outcome_status", "censoring_reason",
    "mark_slot", "mark_transaction_index", "mark_outer_index", "mark_inner_index",
    "mark_index", "liquidity_state",
    "tokens_held", "tokens_executable", "tokens_unrealizable",
    "gross_exit_lamports", "exit_curve_fee_lamports", "exit_execution_cost_lamports",
    "exit_cost_total_lamports", "realizable_net_lamports",
    "net_return_numerator", "net_return_denominator", "capital_denominator_lamports",
    "max_drawdown_lamports", "max_drawdown_peak_lamports",
    "max_drawdown_ratio_numerator", "max_drawdown_ratio_denominator",
    "path_terminal_state", "observations_evaluated_to_horizon",
    "path_record_sha256",
    "row_sha256",
)


class LabelRefused(FreezeViolation):
    """Raised when a label cannot be materialized honestly from the evidence given."""


def _sha256_of(value):
    return hashlib.sha256(
        B10B.canonical_json(value).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------
# Preregistration
# --------------------------------------------------------------------------------------------

def assert_preregistration(document):
    """Validate a preregistration and return `(document, sha256)`.

    There is no default horizon in this module and there must never be one. A horizon chosen after
    looking at outcome counts is the move the whole preregistration apparatus exists to prevent, and
    a default is that move with nobody's name on it.
    """
    if not isinstance(document, dict):
        raise LabelRefused(
            f"preregistration must be a mapping, got {type(document).__name__}")
    identifier = document.get("preregistration_id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise LabelRefused(
            "preregistration must carry a non-empty `preregistration_id`; an unnamed "
            "preregistration cannot be cited, and one that cannot be cited is not one")
    status = document.get("window_status")
    if status not in ALLOWED_WINDOW_STATUS:
        raise LabelRefused(
            f"window_status {status!r} is not one of {list(ALLOWED_WINDOW_STATUS)}. Every "
            "CreateEvent in this corpus falls inside the B8b window burned on 2026-07-28, and R3 "
            "forbids measuring or tuning a label on it; declaring anything else here would be "
            "claiming evidence this project does not have")
    if not isinstance(document.get("purpose"), str) or not document["purpose"].strip():
        raise LabelRefused(
            "preregistration must state a `purpose`; on a burned window the purpose is the only "
            "thing separating a plumbing check from a finding")
    horizons = document.get("horizons")
    if not isinstance(horizons, list) or not horizons:
        raise LabelRefused(
            "preregistration must list at least one horizon. This module has no default horizon "
            "and must never acquire one")
    names = set()
    for horizon in horizons:
        assert_horizon(horizon)
        if horizon["name"] in names:
            raise LabelRefused(f"horizon name {horizon['name']!r} appears twice")
        names.add(horizon["name"])
    window_end = document.get("observation_window_end_slot")
    if isinstance(window_end, bool) or not isinstance(window_end, int) or window_end <= 0:
        raise LabelRefused(
            "preregistration must state `observation_window_end_slot` as a positive integer. "
            "Right-censoring is a statement about window geometry (C1/C2), so a censoring decision "
            "made without a stated window end is not a decision")
    return document, _sha256_of(document)


def assert_horizon(horizon):
    """One horizon's geometry, explicit and refused if it is anything else."""
    if not isinstance(horizon, dict):
        raise LabelRefused(f"horizon must be a mapping, got {type(horizon).__name__}")
    kind = horizon.get("kind")
    if kind in REFUSED_HORIZON_KINDS:
        raise LabelRefused(
            f"horizon kind {kind!r} is refused: {REFUSED_HORIZON_KINDS[kind]}")
    if kind not in HORIZON_KINDS:
        raise LabelRefused(
            f"horizon kind {kind!r} is not one of {list(HORIZON_KINDS)}")
    if not isinstance(horizon.get("name"), str) or not horizon["name"].strip():
        raise LabelRefused("horizon must carry a non-empty `name`")
    if kind == HORIZON_SLOT:
        _positive("horizon slots", horizon.get("slots"))
    elif kind == HORIZON_OBSERVATION:
        _positive("horizon count", horizon.get("count"))
    return horizon


def _positive(label, value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LabelRefused(f"{label} must be a positive integer, got {value!r}")
    return value


def horizon_parameter(horizon):
    if horizon["kind"] == HORIZON_SLOT:
        return horizon["slots"]
    if horizon["kind"] == HORIZON_OBSERVATION:
        return horizon["count"]
    return None


# --------------------------------------------------------------------------------------------
# The decision half — no parameter here can carry a mark
# --------------------------------------------------------------------------------------------

def build_decision_facts(t0_state, identity, order, schedule, cost_policy, entry,
                         preregistration, preregistration_sha256, dataset_content_sha256,
                         no_decision_reason=None):
    """Everything known at t0, and nothing else.

    THIS FUNCTION HAS NO PATH, MARK, RESULT OR HORIZON PARAMETER. A later author cannot feed it a
    post-t0 quantity without changing the signature and the test that pins it in the same edit.

    `entry` is `b10a`'s entry record, which is priced from t0 alone; it is passed rather than
    recomputed so the row cannot disagree with the path it came from.
    """
    if no_decision_reason is not None and no_decision_reason not in NO_DECISION_REASONS:
        raise LabelRefused(
            f"no_decision_reason {no_decision_reason!r} is not one of {list(NO_DECISION_REASONS)}")
    for field in ("mint", "bonding_curve"):
        if not isinstance(identity.get(field), str) or not identity[field]:
            raise LabelRefused(f"identity must carry a non-empty {field}")
    creator = identity.get("creator")
    create_user = identity.get("create_user")
    t0_user = identity.get("t0_user")
    for label, value in (("creator", creator), ("create_user", create_user)):
        if not isinstance(value, str) or not value:
            raise LabelRefused(
                f"identity must carry a non-empty {label}; R5 requires splitting by at least "
                "`creator union user` and a split key that may be absent is not a split key")
    if t0_user is not None and not isinstance(t0_user, str):
        raise LabelRefused("t0_user must be a string or None")

    facts = {
        "schema_version": SCHEMA_VERSION,
        "label_kind": LABEL_KIND,
        "calibration": B10B.CALIBRATION_UNCALIBRATED,
        "window_status": preregistration["window_status"],
        "preregistration_id": preregistration["preregistration_id"],
        "preregistration_sha256": preregistration_sha256,
        "dataset_content_sha256": dataset_content_sha256,
        "mint": identity["mint"],
        "bonding_curve": identity["bonding_curve"],
        "t0_slot": t0_state["slot"],
        "t0_transaction_index": t0_state["transaction_index"],
        "t0_outer_index": t0_state["outer_index"],
        "t0_inner_index": t0_state["inner_index"],
        "t0_virtual_quote": t0_state["virtual_quote"],
        "t0_virtual_token": t0_state["virtual_token"],
        "t0_real_quote": t0_state["real_quote"],
        "t0_real_token": t0_state["real_token"],
        "creator": creator,
        "create_user": create_user,
        "t0_user": t0_user,
        # Raw keys only. The union-find over `creator union user`, and the split that consumes it,
        # are Phase 3 and are not implemented here — emitting a key is not performing a split.
        "split_key_creator": creator,
        "split_key_creator_union_t0_user": "|".join(
            sorted({creator, create_user} | ({t0_user} if t0_user else set()))),
        "order_quote_lamports": None if order is None else order["quote_lamports"],
        "entry_tokens_out": None if entry is None else entry["tokens_out"],
        "entry_outlay_lamports": None if entry is None else entry["lamports_out_of_wallet"],
        "entry_curve_fee_lamports": (
            None if entry is None else entry["curve_fees"]["charged_total"]),
        "entry_execution_cost_lamports": (
            None if entry is None else entry["execution_costs"]["total"]),
        "fee_schedule_sha256": _sha256_of(dict(schedule)),
        "cost_policy_sha256": _sha256_of(dict(cost_policy)),
        "decision_sha256": None,
        "no_decision_reason": no_decision_reason,
    }
    if (entry is None) != (no_decision_reason is not None):
        raise LabelRefused(
            "a decision either priced an entry or states why it did not; exactly one, because a "
            "row with neither is unexplained and a row with both is contradictory")
    facts["decision_sha256"] = _sha256_of(
        {key: value for key, value in facts.items() if key != "decision_sha256"})
    return facts


# --------------------------------------------------------------------------------------------
# The outcome half — this side may read the future, and says so
# --------------------------------------------------------------------------------------------

def resolve_horizon(path_result, horizon, observation_window_end_slot):
    """Which observed state carries this horizon's label, or exactly why none does.

    `slot_horizon` resolves to the **state in force at `t0.slot + slots`** — the LAST evaluable mark
    at or before the target, not the first one after it. R1 fixes the label window at `(t0, t0+H]`.
    Taking the first mark AFTER the target would instead label "the value at the next trade,
    whenever that turned out to be", which is a different quantity and one that moves with how
    quiet the token happened to go.

    Three distinct ways there is no label, deliberately not merged into one:
    right-censored (the horizon lies past the recorded window), structurally unavailable (the curve
    completed first), and no observed state in the window (nothing traded inside it).
    """
    marks = [mark for mark in path_result["marks"] if mark["evaluable"]]
    terminated = path_result["terminal_state"] == B10B.TERMINAL_STRUCTURAL_UNAVAILABILITY
    kind = horizon["kind"]

    def outcome(mark, status, reason, target=None):
        return {"mark": mark, "target_slot": target, "status": status, "reason": reason}

    if kind == HORIZON_SLOT:
        target = path_result["t0"]["slot"] + horizon["slots"]
        if target > observation_window_end_slot:
            return outcome(None, OUTCOME_RIGHT_CENSORED,
                           f"horizon slot {target} is beyond the observation window end "
                           f"{observation_window_end_slot}; unreachable by window geometry "
                           "(DEFINITIONS.md C1/C2), never scored", target)
        if terminated and _completion_slot(path_result) <= target:
            return outcome(None, OUTCOME_STRUCTURAL_UNAVAILABLE,
                           "the curve completed at or before the horizon; curve trading has ended "
                           "and this regime has no exit venue after it", target)
        eligible = [mark for mark in marks if mark["coordinate"]["slot"] <= target]
        if eligible:
            return outcome(eligible[-1], OUTCOME_MARKED, None, target)
        return outcome(None, OUTCOME_NO_OBSERVED_STATE, NO_OBSERVED_STATE_REASON, target)

    if kind == HORIZON_OBSERVATION:
        count = horizon["count"]
        if len(marks) >= count:
            return outcome(marks[count - 1], OUTCOME_MARKED, None)
        if terminated:
            return outcome(None, OUTCOME_STRUCTURAL_UNAVAILABLE,
                           f"the curve completed after {len(marks)} evaluable observations, "
                           f"before the {count}th")
        if not marks:
            return outcome(None, OUTCOME_NO_OBSERVED_STATE, NO_OBSERVED_STATE_REASON)
        return outcome(None, OUTCOME_RIGHT_CENSORED,
                       f"only {len(marks)} evaluable observations exist within the window, fewer "
                       f"than the {count} this horizon requires; right-censored "
                       "(DEFINITIONS.md C1), never scored")

    # Administrative: the window's own edge. Reported because the accounting needs a
    # what-happened-by-the-end row, and flagged because its value moves with the window rather
    # than with the market.
    if marks:
        return outcome(marks[-1], OUTCOME_MARKED, None)
    if terminated:
        return outcome(None, OUTCOME_STRUCTURAL_UNAVAILABLE,
                       "the curve completed with no evaluable observation before it")
    return outcome(None, OUTCOME_NO_OBSERVED_STATE, NO_OBSERVED_STATE_REASON)


def _completion_slot(path_result):
    for mark in path_result["marks"]:
        if mark["liquidity"] == B10B.L3_STRUCTURAL_UNAVAILABLE:
            return mark["coordinate"]["slot"]
    raise LabelRefused("path reports structural unavailability with no completed mark")


def drawdown_to(path_result, mark_index):
    """Maximum drawdown on the realisable net exit value path, up to and including `mark_index`.

    Recomputed here rather than taken from the path record, because the path record's drawdown runs
    to the end of the observation window and a label at horizon H must not see past H. That is the
    same rule as R1 applied inside a derived statistic.
    """
    peak = worst = worst_peak = None
    counted = 0
    for mark in path_result["marks"]:
        if not mark["evaluable"]:
            continue
        if mark_index is not None and mark["index"] > mark_index:
            break
        value = mark["realizable_net_lamports"]
        peak = value if peak is None or value > peak else peak
        counted += 1
        fall = peak - value
        if worst is None or fall > worst:
            worst, worst_peak = fall, peak
    if peak is None:
        return {"max_drawdown_lamports": None, "max_drawdown_peak_lamports": None,
                "max_drawdown_ratio_numerator": None, "max_drawdown_ratio_denominator": None,
                "observations_evaluated_to_horizon": 0}
    numerator = denominator = None
    if worst > 0 and worst_peak > 0:
        numerator, denominator = _reduce(worst, worst_peak)
    return {"max_drawdown_lamports": worst, "max_drawdown_peak_lamports": worst_peak,
            "max_drawdown_ratio_numerator": numerator,
            "max_drawdown_ratio_denominator": denominator,
            "observations_evaluated_to_horizon": counted}


def _reduce(numerator, denominator):
    """Exact rational in lowest terms. No float ever appears in a label row."""
    if denominator == 0:
        raise LabelRefused("a rational with a zero denominator is not a number")
    divisor = math.gcd(abs(numerator), abs(denominator))
    return numerator // divisor, denominator // divisor


def build_outcome_facts(path_result, horizon, observation_window_end_slot, entry):
    """Everything from after t0, and the exact reason when there is nothing.

    Return is `docs/EXECUTABLE_RETURN.md` §1 exactly: `(Q_out - Q_in - C) / (Q_in + C)` with `C`
    the entry AND exit costs actually incurred, as an exact reduced integer pair. A censored or
    unavailable horizon carries NULL, never zero and never minus one — R4.
    """
    resolved = resolve_horizon(path_result, horizon, observation_window_end_slot)
    mark = resolved["mark"]
    facts = {
        "horizon_name": horizon["name"],
        "horizon_kind": horizon["kind"],
        "horizon_parameter": horizon_parameter(horizon),
        "horizon_is_administrative": horizon["kind"] == HORIZON_ADMINISTRATIVE,
        "horizon_target_slot": resolved["target_slot"],
        "observation_window_end_slot": observation_window_end_slot,
        "outcome_status": resolved["status"],
        "censoring_reason": resolved["reason"],
        "mark_slot": None, "mark_transaction_index": None, "mark_outer_index": None,
        "mark_inner_index": None, "mark_index": None, "liquidity_state": None,
        "tokens_held": None, "tokens_executable": None, "tokens_unrealizable": None,
        "gross_exit_lamports": None, "exit_curve_fee_lamports": None,
        "exit_execution_cost_lamports": None, "exit_cost_total_lamports": None,
        "realizable_net_lamports": None,
        "net_return_numerator": None, "net_return_denominator": None,
        "capital_denominator_lamports": None,
        "max_drawdown_lamports": None, "max_drawdown_peak_lamports": None,
        "max_drawdown_ratio_numerator": None, "max_drawdown_ratio_denominator": None,
        "path_terminal_state": path_result["terminal_state"],
        "observations_evaluated_to_horizon": 0,
        "path_record_sha256": B10B.record_hash(path_result),
        "row_sha256": None,
    }
    if resolved["status"] != OUTCOME_MARKED:
        return facts

    detail = mark["mark"]
    exit_fees = 0 if detail["curve_fees"] is None else detail["curve_fees"]["charged_total"]
    exit_execution = 0 if detail["execution_costs"] is None else detail["execution_costs"]["total"]
    quote_in = entry["quote_lamports"]
    cost_total = (entry["curve_fees"]["charged_total"] + entry["execution_costs"]["total"]
                  + exit_fees + exit_execution)
    numerator = detail["gross_exit_lamports"] - quote_in - cost_total
    denominator = quote_in + cost_total
    reduced_numerator, reduced_denominator = _reduce(numerator, denominator)
    facts.update({
        "mark_slot": mark["coordinate"]["slot"],
        "mark_transaction_index": mark["coordinate"]["transaction_index"],
        "mark_outer_index": mark["coordinate"]["outer_index"],
        "mark_inner_index": mark["coordinate"]["inner_index"],
        "mark_index": mark["index"],
        "liquidity_state": mark["liquidity"],
        "tokens_held": detail["tokens_held"],
        "tokens_executable": detail["tokens_executable"],
        "tokens_unrealizable": detail["tokens_unrealizable"],
        "gross_exit_lamports": detail["gross_exit_lamports"],
        "exit_curve_fee_lamports": exit_fees,
        "exit_execution_cost_lamports": exit_execution,
        "exit_cost_total_lamports": exit_fees + exit_execution,
        "realizable_net_lamports": detail["realizable_net_lamports"],
        "net_return_numerator": reduced_numerator,
        "net_return_denominator": reduced_denominator,
        "capital_denominator_lamports": denominator,
    })
    facts.update(drawdown_to(path_result, mark["index"]))
    return facts


# --------------------------------------------------------------------------------------------
# Merge, with the boundary enforced at the seam
# --------------------------------------------------------------------------------------------

def assert_field_partition(row):
    """Every key belongs to exactly one side of t0. No key may be in both or in neither."""
    declared_decision, declared_outcome = set(DECISION_FIELDS), set(OUTCOME_FIELDS)
    overlap = declared_decision & declared_outcome
    if overlap:
        raise LabelRefused(
            f"{sorted(overlap)} are declared on both sides of t0; a field cannot be simultaneously "
            "a decision-time fact and an outcome")
    keys = set(row)
    missing = (declared_decision | declared_outcome) - keys
    extra = keys - (declared_decision | declared_outcome)
    if missing:
        raise LabelRefused(f"label row is missing declared fields {sorted(missing)}")
    if extra:
        raise LabelRefused(
            f"label row carries undeclared fields {sorted(extra)}; every field must state which "
            "side of t0 it comes from, because that declaration is the leakage boundary")
    return True


def decision_block(row):
    return {field: row[field] for field in DECISION_FIELDS}


def outcome_block(row):
    return {field: row[field] for field in OUTCOME_FIELDS}


def materialize_row(decision_facts, outcome_facts, path_result=None):
    """One label row, with the leakage boundary checked at the seam rather than trusted."""
    row = dict(decision_facts)
    row.update(outcome_facts)
    assert_field_partition(row)
    if path_result is not None:
        # The identity check b10b could not run at `decide_entry`, which by construction cannot see
        # the future. This module holds both sides, so it can: no mark object may be reachable from
        # anything on the decision side of the row.
        B10B.assert_no_future_reachable(
            decision_block(row), [mark for mark in path_result["marks"]])
    row["row_sha256"] = _sha256_of({k: v for k, v in row.items() if k != "row_sha256"})
    return row


def materialize_decision(path_result, identity, preregistration, preregistration_sha256,
                         dataset_content_sha256, t0_state, order, schedule, cost_policy):
    """Every preregistered horizon for one decision that priced an entry."""
    entry = path_result["entry"]
    decision_facts = build_decision_facts(
        t0_state, identity, order, schedule, cost_policy, entry,
        preregistration, preregistration_sha256, dataset_content_sha256)
    window_end = preregistration["observation_window_end_slot"]
    rows = []
    for horizon in preregistration["horizons"]:
        outcome_facts = build_outcome_facts(path_result, horizon, window_end, entry)
        rows.append(materialize_row(decision_facts, outcome_facts, path_result))
    _assert_decision_block_invariant(rows)
    return rows


def materialize_no_decision(identity, preregistration, preregistration_sha256,
                            dataset_content_sha256, t0_state, schedule, cost_policy, reason):
    """Rows for a curve we would not have entered.

    They exist so that the denominator stays the whole cohort. Conditioning the label table on
    evaluability would silently select on tradability, and tradability is correlated with exactly
    the outcomes a later model would be asked to predict.
    """
    decision_facts = build_decision_facts(
        t0_state, identity, None, schedule, cost_policy, None,
        preregistration, preregistration_sha256, dataset_content_sha256,
        no_decision_reason=reason)
    rows = []
    for horizon in preregistration["horizons"]:
        outcome_facts = {field: None for field in OUTCOME_FIELDS}
        outcome_facts.update({
            "horizon_name": horizon["name"],
            "horizon_kind": horizon["kind"],
            "horizon_parameter": horizon_parameter(horizon),
            "horizon_is_administrative": horizon["kind"] == HORIZON_ADMINISTRATIVE,
            "observation_window_end_slot": preregistration["observation_window_end_slot"],
            "outcome_status": OUTCOME_NO_DECISION,
            "censoring_reason": f"no position exists to label: {reason}",
            "observations_evaluated_to_horizon": 0,
        })
        rows.append(materialize_row(decision_facts, outcome_facts))
    _assert_decision_block_invariant(rows)
    return rows


def _assert_decision_block_invariant(rows):
    """The decision block must be identical across every horizon of one decision.

    Horizons are post-t0 geometry. Anything on the decision side that moves with a horizon has, by
    definition, been computed from information after t0 — so this single equality catches a whole
    class of leaks without knowing which field caused them.
    """
    if not rows:
        return True
    first = B10B.canonical_json(decision_block(rows[0]))
    for row in rows[1:]:
        if B10B.canonical_json(decision_block(row)) != first:
            raise LabelRefused(
                f"the decision block of {row['bonding_curve']} varies across horizons; a "
                "decision-time fact that moves with a horizon was computed after t0")
    return True


# --------------------------------------------------------------------------------------------
# Independent recomputation
# --------------------------------------------------------------------------------------------

def assert_row_arithmetic(row, path_result=None):
    """Re-derive every number in the row and refuse any disagreement.

    Recomputed from the pinned curve functions and from the row's own primitive inputs, not from a
    neighbouring derived field, so a mistake cannot validate itself.
    """
    if row["outcome_status"] not in OUTCOME_STATUSES:
        raise LabelRefused(f"unknown outcome_status {row['outcome_status']!r}")
    if row["row_sha256"] != _sha256_of(
            {k: v for k, v in row.items() if k != "row_sha256"}):
        raise LabelRefused("row_sha256 does not match the row it is stamped on")

    if row["outcome_status"] != OUTCOME_MARKED:
        # R4: absence of evidence is never a number. A censored, unavailable or no-decision row
        # must carry nothing that a later reader could average.
        for field in ("net_return_numerator", "net_return_denominator", "realizable_net_lamports",
                      "gross_exit_lamports", "capital_denominator_lamports", "liquidity_state"):
            if row[field] is not None:
                raise LabelRefused(
                    f"{row['outcome_status']} row carries {field}={row[field]!r}; a horizon with "
                    "no observed value must be NULL, never zero and never minus one")
        if not row["censoring_reason"]:
            raise LabelRefused(
                f"{row['outcome_status']} row states no reason; an unexplained absence is "
                "indistinguishable from a lost row")
        return True

    if row["tokens_executable"] + row["tokens_unrealizable"] != row["tokens_held"]:
        raise LabelRefused("executable and unrealizable tokens do not sum to held")
    if row["exit_cost_total_lamports"] != (
            row["exit_curve_fee_lamports"] + row["exit_execution_cost_lamports"]):
        raise LabelRefused("exit cost total does not equal its components")
    if row["realizable_net_lamports"] != (
            row["gross_exit_lamports"] - row["exit_cost_total_lamports"]):
        raise LabelRefused("realizable net is not gross minus exit costs")
    if row["entry_outlay_lamports"] != (
            row["order_quote_lamports"] + row["entry_curve_fee_lamports"]
            + row["entry_execution_cost_lamports"]):
        raise LabelRefused("entry outlay does not equal quote plus entry costs")

    cost_total = (row["entry_curve_fee_lamports"] + row["entry_execution_cost_lamports"]
                  + row["exit_cost_total_lamports"])
    numerator = row["gross_exit_lamports"] - row["order_quote_lamports"] - cost_total
    denominator = row["order_quote_lamports"] + cost_total
    if row["capital_denominator_lamports"] != denominator:
        raise LabelRefused("capital denominator is not quote plus every cost (EXECUTABLE_RETURN §1)")
    # The same numerator by a second route: realisable net minus entry outlay. The two agree only
    # if every cost is counted exactly once, which is the mistake this check exists to catch.
    if numerator != row["realizable_net_lamports"] - row["entry_outlay_lamports"]:
        raise LabelRefused(
            f"net numerator {numerator} disagrees with realisable net minus outlay "
            f"{row['realizable_net_lamports'] - row['entry_outlay_lamports']}; a cost is counted "
            "twice or not at all")
    expected = _reduce(numerator, denominator)
    if (row["net_return_numerator"], row["net_return_denominator"]) != expected:
        raise LabelRefused(
            f"net return {row['net_return_numerator']}/{row['net_return_denominator']} does not "
            f"reduce from {numerator}/{denominator}")
    if math.gcd(abs(row["net_return_numerator"]), abs(row["net_return_denominator"])) != 1:
        raise LabelRefused("net return is not in lowest terms; the rational is not canonical")

    if path_result is not None:
        cited = [m for m in path_result["marks"] if m["index"] == row["mark_index"]]
        if len(cited) != 1:
            raise LabelRefused(f"mark_index {row['mark_index']} is not in the path record")
        if cited[0]["realizable_net_lamports"] != row["realizable_net_lamports"]:
            raise LabelRefused("row value disagrees with the path record it cites")
        if cited[0]["coordinate"]["slot"] != row["mark_slot"]:
            raise LabelRefused("row coordinate disagrees with the path record it cites")
        if row["path_record_sha256"] != B10B.record_hash(path_result):
            raise LabelRefused("path_record_sha256 does not match the record it cites")
        recomputed = drawdown_to(path_result, row["mark_index"])
        for field, value in recomputed.items():
            if row[field] != value:
                raise LabelRefused(
                    f"{field} is {row[field]!r} but recomputing the value path to the horizon "
                    f"gives {value!r}")
        if row["horizon_kind"] == HORIZON_SLOT and row["mark_slot"] > row["horizon_target_slot"]:
            raise LabelRefused(
                f"the label at horizon slot {row['horizon_target_slot']} was taken from a state at "
                f"slot {row['mark_slot']}, which is after it; the label window is (t0, t0+H]")
    return True


def canonical_json(rows):
    return B10B.canonical_json(rows)


def rows_hash(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row["row_sha256"].encode())
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true",
                        help="print the contract, field partition and refusals this module claims")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`, or use b10c_label_corpus.py")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "label_kind": LABEL_KIND,
        "allowed_window_status": list(ALLOWED_WINDOW_STATUS),
        "horizon_kinds": list(HORIZON_KINDS),
        "refused_horizon_kinds": REFUSED_HORIZON_KINDS,
        "outcome_statuses": list(OUTCOME_STATUSES),
        "no_decision_reasons": list(NO_DECISION_REASONS),
        "decision_fields": list(DECISION_FIELDS),
        "outcome_fields": list(OUTCOME_FIELDS),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FreezeViolation as error:
        print(f"FreezeViolation: {error}", file=sys.stderr)
        sys.exit(2)
