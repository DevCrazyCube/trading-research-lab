#!/usr/bin/env python3
"""AFTERSHOCK PAC V1 persistent causal PAPER-SCENARIO runner.

This is deliberately not a wallet or transaction sender. It advances sealed decisions over an
observed public-RPC tape and records only uncalibrated scenario outcomes. Entry and exit use a durable
two-step state machine: decide and persist first, then attempt only against a later observed boundary.
Consequently a HOLD never simulates a sell and neither entry nor exit can fill at its decision state.
"""
from __future__ import annotations

import fcntl
import argparse
import hashlib
import json
import os
import pathlib
import tempfile
import time
from dataclasses import asdict, dataclass

from . import feasibility
from . import manifest as _manifest
from . import pac_feed
from . import pac_policy as _policy
from . import solusd_recorder
from . import tape
from .execution import (
    DecisionRecord, ExecutionContext, IntentKind, LatencyModel, OrderIntent, Outcome,
    PriceUnavailable, RefusedExecution, attempt_order, build_decision_record, q_lamports_for_usd,
)

INSTRUMENT = "AFTERSHOCK_PAC_V1"
RUNNER_PATH = "scripts/trading_bot/aftershock/pac_runner.py"
DETECTOR_PATH = "scripts/trading_bot/aftershock/pac_detector.py"
STATE_SCHEMA = 3
LEDGER_SCHEMA = 2
SLIPPAGE_BPS = 1_000
SLIPPAGE_DEN = 10_000


def exit_poll(events: tuple, warmup_count: int) -> tuple:
    """Sealed exit observation: all evidence is the newest currently observable event."""
    if type(warmup_count) is not int or warmup_count < 0 or warmup_count >= len(events):
        return ()
    return (len(events) - 1,)


@dataclass
class OpenPosition:
    mint: str
    token_atoms: int
    quote_input_lamports: int
    entry_all_in_lamports: int
    entry_curve_fee_lamports: int
    entry_attempt_cost_lamports: int
    ata_rent_lamports: int
    entry_observation_unix_nanos: int
    peak_full_exit_quote_lamports: int
    entry_decision_id: str
    entry_attempt_id: str
    last_processed_observation_unix_nanos: int

    def __post_init__(self) -> None:
        if not isinstance(self.mint, str) or not self.mint:
            raise RefusedExecution("open position mint is required")
        positive = ("token_atoms", "quote_input_lamports", "entry_all_in_lamports")
        nonnegative = ("entry_curve_fee_lamports", "entry_attempt_cost_lamports", "ata_rent_lamports",
                       "entry_observation_unix_nanos", "peak_full_exit_quote_lamports",
                       "last_processed_observation_unix_nanos")
        for name in positive:
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise RefusedExecution(f"open position {name} must be a positive exact integer")
        for name in nonnegative:
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise RefusedExecution(f"open position {name} must be a non-negative exact integer")
        if self.entry_all_in_lamports != (self.quote_input_lamports + self.entry_curve_fee_lamports
                                         + self.entry_attempt_cost_lamports + self.ata_rent_lamports):
            raise RefusedExecution("open position all-in entry cost does not reconcile")
        if self.last_processed_observation_unix_nanos < self.entry_observation_unix_nanos:
            raise RefusedExecution("open position resume clock precedes entry")
        for name in ("entry_decision_id", "entry_attempt_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64:
                raise RefusedExecution(f"open position {name} is invalid")


def _state_path() -> pathlib.Path:
    return _manifest.RESEARCH / f"{INSTRUMENT}_RUNNER_STATE.json"


def _ledger_path() -> pathlib.Path:
    return _manifest.RESEARCH / f"{INSTRUMENT}_SCENARIO_LEDGER.jsonl"


def _lock_path() -> pathlib.Path:
    return _manifest.RESEARCH / f"{INSTRUMENT}_RUNNER.lock"


def _new_state() -> dict:
    return {
        "schema": STATE_SCHEMA,
        "session_event_sha256": None,
        "activation_root_sha256": None,
        "open_positions": [],
        "pending_orders": [],
        "pending_ledger_rows": [],
        "scan_watermark_unix_nanos": None,
        "last_entry_signal_observation_unix_nanos": None,
        "last_measurement_refusal": None,
    }


def _decision_to_dict(record: DecisionRecord) -> dict:
    raw = asdict(record)
    raw["evidence_indices"] = list(record.evidence_indices)
    raw["evidence_commitments"] = list(record.evidence_commitments)
    raw["max_evidence_coord"] = (list(record.max_evidence_coord)
                                   if record.max_evidence_coord is not None else None)
    return raw


def _decision_from_dict(raw: dict) -> DecisionRecord:
    if not isinstance(raw, dict) or set(raw) != set(DecisionRecord.__dataclass_fields__):
        raise RefusedExecution("pending order decision schema mismatch")
    values = dict(raw)
    try:
        values["evidence_indices"] = tuple(values["evidence_indices"])
        values["evidence_commitments"] = tuple(values["evidence_commitments"])
        values["max_evidence_coord"] = (tuple(values["max_evidence_coord"])
                                         if values["max_evidence_coord"] is not None else None)
        return DecisionRecord(**values)
    except (TypeError, ValueError) as exc:
        raise RefusedExecution("pending order decision is malformed") from exc


def position_from_dict(raw: dict) -> OpenPosition:
    if not isinstance(raw, dict) or set(raw) != set(OpenPosition.__dataclass_fields__):
        raise RefusedExecution("open position schema mismatch")
    return OpenPosition(**raw)


def position_to_dict(position: OpenPosition) -> dict:
    return asdict(position)


def _validate_pending(raw: dict) -> dict:
    required = {"side", "mint", "amount", "min_out", "decision", "action",
                "entry_attempt_id", "entry_decision_quote_lamports", "return_denominator_lamports"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise RefusedExecution("pending order schema mismatch")
    if raw["side"] not in {"ENTRY", "EXIT"}:
        raise RefusedExecution("pending order side is invalid")
    if not isinstance(raw["mint"], str) or not raw["mint"]:
        raise RefusedExecution("pending order mint is invalid")
    for name in ("amount", "min_out", "return_denominator_lamports"):
        if type(raw[name]) is not int or raw[name] < 1:
            raise RefusedExecution(f"pending order {name} must be positive exact integer")
    _decision_from_dict(raw["decision"])
    if raw["side"] == "ENTRY":
        if raw["action"] is not None or raw["entry_attempt_id"] is not None:
            raise RefusedExecution("entry pending order carries exit fields")
        if type(raw["entry_decision_quote_lamports"]) is not int or raw["entry_decision_quote_lamports"] < 1:
            raise RefusedExecution("entry pending order lacks its causal decision quote")
    else:
        allowed = {a.value for a in _policy.ExitAction if a not in {
            _policy.ExitAction.HOLD, _policy.ExitAction.UNEXITABLE_FULL_LOSS}}
        if raw["action"] not in allowed:
            raise RefusedExecution("exit pending order action is invalid")
        if not isinstance(raw["entry_attempt_id"], str) or len(raw["entry_attempt_id"]) != 64:
            raise RefusedExecution("exit pending order lacks entry identity")
        if raw["entry_decision_quote_lamports"] is not None:
            raise RefusedExecution("exit pending order carries an entry quote")
    return raw


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _ledger_row(body: dict, ctx: ExecutionContext) -> dict:
    row = {
        "schema_version": LEDGER_SCHEMA,
        "instrument_id": INSTRUMENT,
        "seal_sha256": ctx.session.seal_sha256,
        "session_event_sha256": ctx.session.session_event_sha256,
        "activation_root_sha256": ctx.session.activation_root_sha256,
        **body,
    }
    row["event_id"] = hashlib.sha256(_canonical(row).encode()).hexdigest()
    return row


def _validate_row(row: dict) -> dict:
    if not isinstance(row, dict) or row.get("schema_version") != LEDGER_SCHEMA:
        raise RefusedExecution("ledger row is not schema 2")
    event_id = row.get("event_id")
    if not isinstance(event_id, str) or len(event_id) != 64:
        raise RefusedExecution("ledger event id is invalid")
    body = dict(row)
    del body["event_id"]
    if hashlib.sha256(_canonical(body).encode()).hexdigest() != event_id:
        raise RefusedExecution("ledger event id does not authenticate its row")
    return row


def save_state(state: dict) -> None:
    _validate_state(state)
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".runner_", suffix=".json")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(state, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _append_ledger(row: dict) -> None:
    row = _validate_row(row)
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_by_id: dict[str, dict] = {}
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                old = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RefusedExecution(f"ledger line {number} is malformed") from exc
            _validate_row(old)
            if old["event_id"] in existing_by_id and existing_by_id[old["event_id"]] != old:
                raise RefusedExecution("ledger event id collision/tamper detected")
            existing_by_id[old["event_id"]] = old
    if row["event_id"] in existing_by_id:
        if existing_by_id[row["event_id"]] != row:
            raise RefusedExecution("ledger id exists with different bytes")
        return
    with path.open("a") as handle:
        handle.write(_canonical(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _validate_state(state: dict) -> dict:
    if not isinstance(state, dict) or set(state) != set(_new_state()) or state.get("schema") != STATE_SCHEMA:
        raise RefusedExecution("runner state is not schema 2")
    if not isinstance(state["open_positions"], list) or len(state["open_positions"]) > 1:
        raise RefusedExecution("runner open book must have at most one position")
    if not isinstance(state["pending_orders"], list) or len(state["pending_orders"]) > 1:
        raise RefusedExecution("runner pending book must have at most one order")
    if not isinstance(state["pending_ledger_rows"], list):
        raise RefusedExecution("runner ledger journal must be a list")
    positions = [position_from_dict(raw) for raw in state["open_positions"]]
    pending = [_validate_pending(raw) for raw in state["pending_orders"]]
    for row in state["pending_ledger_rows"]:
        _validate_row(row)
    for name in ("scan_watermark_unix_nanos", "last_entry_signal_observation_unix_nanos"):
        value = state[name]
        if value is not None and (type(value) is not int or value < 0):
            raise RefusedExecution(f"runner {name} is invalid")
    refusal = state["last_measurement_refusal"]
    if refusal is not None:
        required = {"reason", "side", "mint", "decision_id", "recorded_unix_nanos",
                    "excluded_late_predecision_count"}
        if not isinstance(refusal, dict) or set(refusal) != required:
            raise RefusedExecution("runner measurement refusal is malformed")
        if refusal["reason"] not in {
                "LATE_PREDECISION_OBSERVATION", "RIGHT_CENSORED_NO_BOUNDARY"}:
            raise RefusedExecution("runner measurement refusal reason is unknown")
        if refusal["side"] not in {"ENTRY", "EXIT"}:
            raise RefusedExecution("runner measurement refusal side is invalid")
        if (not isinstance(refusal["mint"], str) or not refusal["mint"]
                or not isinstance(refusal["decision_id"], str)
                or len(refusal["decision_id"]) != 64
                or type(refusal["recorded_unix_nanos"]) is not int
                or refusal["recorded_unix_nanos"] < 0
                or type(refusal["excluded_late_predecision_count"]) is not int
                or refusal["excluded_late_predecision_count"] < 0):
            raise RefusedExecution("runner measurement refusal fields are invalid")
    session_values = (state["session_event_sha256"], state["activation_root_sha256"])
    if (session_values[0] is None) != (session_values[1] is None):
        raise RefusedExecution("runner session binding is partial")
    if session_values[0] is not None and any(not isinstance(v, str) or len(v) != 64 for v in session_values):
        raise RefusedExecution("runner session binding is malformed")
    if pending and positions and pending[0]["side"] == "ENTRY":
        raise RefusedExecution("runner cannot have an entry pending while open")
    if pending and not positions and pending[0]["side"] == "EXIT":
        raise RefusedExecution("runner cannot have an exit pending while flat")
    if pending and positions and pending[0]["mint"] != positions[0].mint:
        raise RefusedExecution("pending exit mint differs from open position")
    return state


def load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return _new_state()
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("runner state is unreadable") from exc
    _validate_state(state)
    if state["pending_ledger_rows"]:
        for row in state["pending_ledger_rows"]:
            _append_ledger(row)
        state["pending_ledger_rows"] = []
        save_state(state)
    return state


def _commit(state: dict, rows: list[dict]) -> None:
    """State-first write-ahead journal; replay is idempotent after every crash boundary."""
    if state["pending_ledger_rows"]:
        raise RefusedExecution("cannot begin with an unreconciled ledger journal")
    for row in rows:
        _validate_row(row)
    state["pending_ledger_rows"] = rows
    save_state(state)
    for row in rows:
        _append_ledger(row)
    state["pending_ledger_rows"] = []
    save_state(state)


def session_context() -> ExecutionContext:
    try:
        proof = _manifest.load_session_proof(INSTRUMENT)
        _manifest.verify_session_proof(proof)
        return ExecutionContext(session=proof)
    except _manifest.Refused as exc:
        raise RefusedExecution(str(exc)) from exc


def _seal_hashes(ctx: ExecutionContext) -> tuple[str, str, str]:
    return (ctx.session.dependency_sha256(DETECTOR_PATH),
            ctx.session.dependency_sha256(RUNNER_PATH),
            ctx.session.frozen_json_canonical_sha256)


def _bind_session(state: dict, ctx: ExecutionContext) -> None:
    current = (ctx.session.session_event_sha256, ctx.session.activation_root_sha256)
    stored = (state["session_event_sha256"], state["activation_root_sha256"])
    if stored == (None, None):
        state["session_event_sha256"], state["activation_root_sha256"] = current
        save_state(state)
    elif stored != current:
        raise RefusedExecution("runner state belongs to another activation session")


def _min_out(quote: int) -> int:
    if type(quote) is not int or quote < 1:
        raise RefusedExecution("decision quote must be a positive exact integer")
    return max(1, quote * (SLIPPAGE_DEN - SLIPPAGE_BPS) // SLIPPAGE_DEN)


def _nonfill_row(pending: dict, attempt, ctx: ExecutionContext,
                 *, extra_labels: tuple[str, ...] = ()) -> dict:
    if (not isinstance(extra_labels, tuple)
            or any(not isinstance(label, str) or not label for label in extra_labels)):
        raise RefusedExecution("nonfill extra labels must be non-empty strings in a tuple")
    return _ledger_row({
        "kind": "attempt_cost", "side": pending["side"], "mint": pending["mint"],
        "attempt_id": attempt.attempt_id, "entry_attempt_id": pending["entry_attempt_id"],
        "outcome": attempt.outcome.value,
        "attempt_cost_lamports": int(attempt.cost_lamports or 0),
        "cost_observed": attempt.cost_lamports is not None,
        "denominator_lamports": pending["return_denominator_lamports"],
        "labels": list(extra_labels) + list(attempt.labels),
    }, ctx)


def _resolved_row(position: OpenPosition, *, action: str, decision_id: str,
                  attempt=None, accounting: dict | None, ctx: ExecutionContext,
                  extra_labels: tuple[str, ...] = ()) -> dict:
    unavailable = accounting is None
    exit_net = 0 if unavailable else int(accounting["wallet_delta_lamports"])
    if exit_net < 0:
        raise RefusedExecution("exit net proceeds cannot be negative")
    boundary_obs = None
    if (not isinstance(extra_labels, tuple)
            or any(not isinstance(label, str) or not label for label in extra_labels)):
        raise RefusedExecution("resolved extra labels must be non-empty strings in a tuple")
    labels: list[str] = list(extra_labels)
    outcome = Outcome.SCENARIO_UNAVAILABLE.value
    attempt_id = None
    if attempt is not None:
        attempt_id = attempt.attempt_id
        outcome = attempt.outcome.value
        labels.extend(attempt.labels)
        boundary_obs = attempt.clocks.scenario_boundary_observation_unix_nanos
    return _ledger_row({
        "kind": "resolved", "mint": position.mint, "action": action,
        "entry_attempt_id": position.entry_attempt_id,
        "entry_decision_id": position.entry_decision_id,
        "exit_decision_id": decision_id, "exit_attempt_id": attempt_id,
        "exit_outcome": outcome,
        "entry_observation_unix_nanos": position.entry_observation_unix_nanos,
        "exit_boundary_observation_unix_nanos": boundary_obs,
        "entry_all_in_lamports": position.entry_all_in_lamports,
        "quote_input_lamports": position.quote_input_lamports,
        "entry_curve_fee_lamports": position.entry_curve_fee_lamports,
        "entry_attempt_cost_lamports": position.entry_attempt_cost_lamports,
        "ata_rent_lamports": position.ata_rent_lamports,
        "exit_gross_quote_lamports": 0 if unavailable else int(accounting["gross_quote_lamports"]),
        "exit_curve_fee_lamports": 0 if unavailable else int(accounting["curve_fee_lamports"]),
        "exit_attempt_cost_lamports": 0 if unavailable else int(accounting["attempt_cost_lamports"]),
        "exit_net_proceeds_lamports": exit_net,
        "net_return_num": exit_net - position.entry_all_in_lamports,
        "net_return_den": position.entry_all_in_lamports,
        "unexitable_full_loss": unavailable,
        "ata_rent_treatment": "CHARGED_ON_ENTRY_NOT_RECLAIMED_NO_SEPARATE_CLOSE_ATTEMPT",
        "labels": labels,
    }, ctx)


def _record_measurement_refusal(state: dict, pending: dict, reason: str,
                                *, excluded_late_predecision_count: int = 0) -> None:
    if reason not in {"LATE_PREDECISION_OBSERVATION", "RIGHT_CENSORED_NO_BOUNDARY"}:
        raise RefusedExecution("unknown bounded measurement refusal")
    decision = _decision_from_dict(pending["decision"])
    if (type(excluded_late_predecision_count) is not int
            or excluded_late_predecision_count < 0):
        raise RefusedExecution("excluded late-predecision count is invalid")
    state["last_measurement_refusal"] = {
        "reason": reason,
        "side": pending["side"],
        "mint": pending["mint"],
        "decision_id": decision.decision_id,
        "recorded_unix_nanos": time.time_ns(),
        "excluded_late_predecision_count": excluded_late_predecision_count,
    }


def _attempt_stream(events: list, decision: DecisionRecord) -> tuple[list, int]:
    """Reconstruct the exact processed decision prefix plus genuinely post-decision observations.

    Per-mint files are append-only, but RPC decode/materialisation can lag their recorded receive clock.
    Rows appended after the hashed decision prefix with a receive clock at/before the internal decision
    were not part of the processed decision snapshot.  They cannot retroactively invalidate or improve
    the signal.  Exclude them from detector replay; the first later boundary's ``pre_state`` still
    contains their reserve effects, so entry/exit pricing remains post-gap and conservative.
    """
    if not isinstance(decision, DecisionRecord):
        raise RefusedExecution("attempt stream requires a DecisionRecord")
    snapshot_end = decision.stream_snapshot_count
    if snapshot_end > len(events):
        return events, 0  # public engine emits the precise out-of-stream refusal
    tail = events[snapshot_end:]
    late = [event for event in tail
            if event.observation_unix_nanos <= decision.decision_unix_nanos]
    # Keep the complete append-only stream so reserve-state continuity remains independently
    # checkable.  DecisionRecord validation applies the omission test only inside its committed
    # snapshot; attempt boundary search naturally skips tail rows earlier than modeled landing.
    return events, len(late)


def _advance_pending(state: dict, events: list, ctx: ExecutionContext, *,
                     latency: LatencyModel, price_fn) -> bool:
    """Advance one durable order. Return True when it remains right-censored."""
    if not state["pending_orders"]:
        return False
    pending = _validate_pending(state["pending_orders"][0])
    if not events or events[0].mint != pending["mint"]:
        return True
    decision = _decision_from_dict(pending["decision"])
    kind = IntentKind.EXACT_QUOTE_BUY if pending["side"] == "ENTRY" else IntentKind.EXACT_TOKEN_SELL
    intent = OrderIntent(kind, pending["amount"], pending["min_out"])
    attempt_events, late_count = _attempt_stream(events, decision)
    late_labels = ((f"PIPELINE_LAG_PREDECISION_EXCLUDED_{late_count}",)
                   if late_count else ())
    try:
        attempt = attempt_order(attempt_events, decision, intent, latency, ctx, price_fn)
    except RefusedExecution as exc:
        if str(exc) != "DecisionRecord omitted an observation already available at decision time":
            raise
        # A feed observation materialised between the runner's admission snapshot and its internal
        # decision clock.  The original decision is no longer a complete prefix, so it may never fill
        # retrospectively.  Invalidate it durably and release the single-position lock.
        state["pending_orders"] = []
        _record_measurement_refusal(
            state, pending, "LATE_PREDECISION_OBSERVATION",
            excluded_late_predecision_count=late_count)
        save_state(state)
        return False
    if attempt.outcome is Outcome.RIGHT_CENSORED_NO_BOUNDARY:
        # One historical decision cannot remain fillable forever.  ENTRY becomes a no-trade
        # measurement refusal.  A censored non-horizon EXIT is retried only via a fresh decision;
        # at the hard horizon the conservative portfolio outcome is an exact full loss.
        state["pending_orders"] = []
        _record_measurement_refusal(
            state, pending, "RIGHT_CENSORED_NO_BOUNDARY",
            excluded_late_predecision_count=late_count)
        if (pending["side"] == "EXIT"
                and pending["action"] == _policy.ExitAction.ATTEMPT_FULL_EXIT_HORIZON.value):
            position = position_from_dict(state["open_positions"][0])
            row = _resolved_row(
                position, action=_policy.ExitAction.UNEXITABLE_FULL_LOSS.value,
                decision_id=decision.decision_id, accounting=None, ctx=ctx,
                extra_labels=("HORIZON_EXIT_RIGHT_CENSORED_FULL_LOSS",) + late_labels)
            state["open_positions"] = []
            _commit(state, [row])
        else:
            save_state(state)
        return False

    state["pending_orders"] = []
    if attempt.outcome is not Outcome.SCENARIO_FILLED:
        rows = [_nonfill_row(pending, attempt, ctx, extra_labels=late_labels)]
        if pending["side"] == "EXIT" and attempt.outcome is Outcome.SCENARIO_UNAVAILABLE:
            position = position_from_dict(state["open_positions"][0])
            rows.append(_resolved_row(position, action=_policy.ExitAction.UNEXITABLE_FULL_LOSS.value,
                                      decision_id=decision.decision_id, attempt=attempt,
                                      accounting=None, ctx=ctx, extra_labels=late_labels))
            state["open_positions"] = []
        _commit(state, rows)
        return False

    if attempt.fill_state is None:
        raise RefusedExecution("filled attempt lacks a fill state")
    accounting = feasibility.kernel_accounting(attempt.fill_state, intent)
    if (accounting["out_amount"] != attempt.out_amount
            or accounting["attempt_cost_lamports"] != attempt.cost_lamports):
        raise RefusedExecution("attempt and all-cost accounting diverged")
    boundary_obs = attempt.clocks.scenario_boundary_observation_unix_nanos
    if type(boundary_obs) is not int:
        raise RefusedExecution("filled attempt lacks boundary receive clock")

    if pending["side"] == "ENTRY":
        all_in = -int(accounting["wallet_delta_lamports"])
        position = OpenPosition(
            mint=pending["mint"], token_atoms=int(attempt.out_amount),
            quote_input_lamports=pending["amount"], entry_all_in_lamports=all_in,
            entry_curve_fee_lamports=int(accounting["curve_fee_lamports"]),
            entry_attempt_cost_lamports=int(accounting["attempt_cost_lamports"]),
            ata_rent_lamports=int(accounting["ata_rent_lamports"]),
            entry_observation_unix_nanos=boundary_obs, peak_full_exit_quote_lamports=0,
            entry_decision_id=decision.decision_id, entry_attempt_id=attempt.attempt_id,
            last_processed_observation_unix_nanos=boundary_obs)
        state["open_positions"] = [position_to_dict(position)]
        row = _ledger_row({
            "kind": "opened", "mint": position.mint, "token_atoms": position.token_atoms,
            "quote_input_lamports": position.quote_input_lamports,
            "entry_all_in_lamports": position.entry_all_in_lamports,
            "entry_curve_fee_lamports": position.entry_curve_fee_lamports,
            "entry_attempt_cost_lamports": position.entry_attempt_cost_lamports,
            "ata_rent_lamports": position.ata_rent_lamports,
            "entry_observation_unix_nanos": position.entry_observation_unix_nanos,
            "entry_decision_id": position.entry_decision_id,
            "entry_attempt_id": position.entry_attempt_id,
            "labels": list(late_labels) + list(attempt.labels),
        }, ctx)
        _commit(state, [row])
        return False

    position = position_from_dict(state["open_positions"][0])
    if position.entry_attempt_id != pending["entry_attempt_id"]:
        raise RefusedExecution("pending exit references another entry")
    row = _resolved_row(position, action=pending["action"], decision_id=decision.decision_id,
                        attempt=attempt, accounting=accounting, ctx=ctx,
                        extra_labels=late_labels)
    state["open_positions"] = []
    _commit(state, [row])
    return False


def _build_exit(state: dict, position: OpenPosition, events: list, ctx: ExecutionContext, *,
                exit_sha: str, spec_sha: str) -> None:
    decision = build_decision_record(
        events, ctx, detector_module_path=RUNNER_PATH, detector_callable_name="exit_poll",
        detector_sha256=exit_sha, spec_sha256=spec_sha)
    observed = events[decision.evaluated_through_index]
    intent = OrderIntent(IntentKind.EXACT_TOKEN_SELL, position.token_atoms, 1)
    try:
        quote = feasibility.kernel_accounting(observed.post_state, intent)
        raw_net_quote = int(quote["wallet_delta_lamports"])
        # The pure policy consumes non-negative executable value.  A priceable dust exit can have
        # negative wallet value once gas exceeds proceeds; treat its economic value as zero while
        # still allowing recovery before an actual exit trigger.
        net_quote = max(0, raw_net_quote)
        reserve = observed.post_state.real_quote
    except PriceUnavailable:
        quote = None
        raw_net_quote = None
        net_quote = None
        reserve = None
    policy_state = _policy.PositionState(
        token_atoms=position.token_atoms, quote_input_lamports=position.quote_input_lamports,
        entry_observation_unix_nanos=position.entry_observation_unix_nanos,
        peak_full_exit_quote_lamports=position.peak_full_exit_quote_lamports)
    exit_decision = _policy.decide_exit(
        policy_state, full_exit_quote_lamports=net_quote, external_reserve_lamports=reserve,
        observation_unix_nanos=decision.decision_unix_nanos)
    position.peak_full_exit_quote_lamports = exit_decision.state.peak_full_exit_quote_lamports
    position.last_processed_observation_unix_nanos = observed.observation_unix_nanos
    state["open_positions"] = [position_to_dict(position)]

    if exit_decision.action is _policy.ExitAction.HOLD:
        save_state(state)
        return
    if exit_decision.action is _policy.ExitAction.UNEXITABLE_FULL_LOSS:
        row = _resolved_row(position, action=exit_decision.action.value,
                            decision_id=decision.decision_id, accounting=None, ctx=ctx)
        state["open_positions"] = []
        _commit(state, [row])
        return
    if raw_net_quote is not None and raw_net_quote <= 0:
        # HOLD above is deliberate: dust may recover.  Once trail/capacity/horizon requests an exit,
        # sending a transaction whose all-cost proceeds are non-positive only worsens the wallet.
        # Settle the already-paid entry as an exact full loss and release the book without inventing
        # a successful sell or charging an unobserved attempt.
        row = _resolved_row(
            position, action=_policy.ExitAction.UNEXITABLE_FULL_LOSS.value,
            decision_id=decision.decision_id, accounting=None, ctx=ctx,
            extra_labels=(f"NET_EXIT_NONPOSITIVE_AT_{exit_decision.action.value}",))
        state["open_positions"] = []
        _commit(state, [row])
        return
    if quote is None:
        raise RefusedExecution("exit policy requested an order without quote")
    state["pending_orders"] = [{
        "side": "EXIT", "mint": position.mint, "amount": position.token_atoms,
        "min_out": _min_out(int(quote["gross_quote_lamports"])),
        "decision": _decision_to_dict(decision), "action": exit_decision.action.value,
        "entry_attempt_id": position.entry_attempt_id, "entry_decision_quote_lamports": None,
        "return_denominator_lamports": position.entry_all_in_lamports,
    }]
    save_state(state)


def _build_entry(state: dict, events: list, ctx: ExecutionContext, *, q_lamports: int,
                 detector_sha: str, spec_sha: str, entry_after_unix_nanos: int) -> None:
    try:
        decision = build_decision_record(
            events, ctx, detector_module_path=DETECTOR_PATH, detector_callable_name="detector",
            detector_sha256=detector_sha, spec_sha256=spec_sha)
    except RefusedExecution as exc:
        if str(exc) == "sealed detector must return a non-empty tuple of all evidence indices":
            return
        raise
    signal_obs = events[decision.signal_index].observation_unix_nanos
    last_signal = state["last_entry_signal_observation_unix_nanos"]
    if signal_obs <= entry_after_unix_nanos or (last_signal is not None and signal_obs <= last_signal):
        return
    withdrawals = []
    for index in (decision.evidence_indices[0], decision.evidence_indices[2]):
        event = events[index]
        withdrawals.append(event.pre_state.real_quote - event.post_state.real_quote)
    if any(q_lamports > withdrawal for withdrawal in withdrawals):
        state["last_entry_signal_observation_unix_nanos"] = signal_obs
        save_state(state)
        return
    observed = events[decision.evaluated_through_index]
    quote = feasibility.kernel_accounting(
        observed.post_state, OrderIntent(IntentKind.EXACT_QUOTE_BUY, q_lamports, 1))
    state["pending_orders"] = [{
        "side": "ENTRY", "mint": events[0].mint, "amount": q_lamports,
        "min_out": _min_out(int(quote["out_amount"])), "decision": _decision_to_dict(decision),
        "action": None, "entry_attempt_id": None,
        "entry_decision_quote_lamports": q_lamports,
        "return_denominator_lamports": -int(quote["wallet_delta_lamports"]),
    }]
    state["last_entry_signal_observation_unix_nanos"] = signal_obs
    save_state(state)


def drive_once(events: list, state: dict, ctx: ExecutionContext, *, q_lamports: int,
               latency: LatencyModel, price_fn=None, entry_after_unix_nanos: int = 0) -> dict:
    """Advance one mint at the internal wall clock. No caller-supplied decision clock exists."""
    _validate_state(state)
    if not events:
        return state
    if type(q_lamports) is not int or q_lamports < 1:
        raise RefusedExecution("PAC quote size must be a positive exact integer")
    if type(entry_after_unix_nanos) is not int or entry_after_unix_nanos < 0:
        raise RefusedExecution("PAC entry admission watermark is invalid")
    price_fn = price_fn or feasibility.kernel_price_fn()
    _bind_session(state, ctx)
    detector_sha, exit_sha, spec_sha = _seal_hashes(ctx)
    mint = events[0].mint

    if state["pending_orders"]:
        if state["pending_orders"][0]["mint"] != mint:
            return state
        if _advance_pending(state, events, ctx, latency=latency, price_fn=price_fn):
            return state
        return state
    if state["open_positions"]:
        position = position_from_dict(state["open_positions"][0])
        if position.mint == mint:
            _build_exit(state, position, events, ctx, exit_sha=exit_sha, spec_sha=spec_sha)
        return state
    _build_entry(state, events, ctx, q_lamports=q_lamports, detector_sha=detector_sha,
                 spec_sha=spec_sha, entry_after_unix_nanos=entry_after_unix_nanos)
    return state


def runner_lock():
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RefusedExecution("another PAC runner owns the state lock") from exc
    return handle


def _causal_events(mint: str, proof, cutoff_unix_nanos: int) -> list:
    events = pac_feed.mint_events(
        mint, after_unix_nanos=proof.warmup_completed_unix_nanos)
    return [event for event in events if event.observation_unix_nanos <= cutoff_unix_nanos]


def _probe_lamports(decision_unix_nanos: int) -> int:
    quote = solusd_recorder.latest_observation(decision_unix_nanos=decision_unix_nanos)
    return q_lamports_for_usd(
        _policy.DISCOVERY_PROBE_USD, quote, decision_unix_nanos=decision_unix_nanos,
        max_staleness_nanos=solusd_recorder.MAX_LOCAL_AGE_NANOS)


def _active_mint(state: dict) -> str | None:
    if state["pending_orders"]:
        return state["pending_orders"][0]["mint"]
    if state["open_positions"]:
        return state["open_positions"][0]["mint"]
    return None


def _run_cycle_unlocked(*, reaction_nanos: int) -> dict:
    """One forward-only pass. The watermark is committed before file discovery.

    On a crash, this can skip an interval but cannot buy a pattern retrospectively. An existing position
    or pending order is always serviced before discovery. The anchored SessionProof is verified before
    any runner state is created or mutated.
    """
    latency = LatencyModel(reaction_nanos)
    ctx = session_context()
    cutoff = time.time_ns()
    state = load_state()
    _bind_session(state, ctx)
    previous = state["scan_watermark_unix_nanos"]
    state["scan_watermark_unix_nanos"] = cutoff
    save_state(state)  # state-first admission barrier; a crash misses rather than backfills
    if previous is None:
        return {"status": "WATERMARK_INITIALIZED_NO_BACKFILL", "cutoff_unix_nanos": cutoff,
                "open": len(state["open_positions"]), "pending": len(state["pending_orders"])}

    active = _active_mint(state)
    if active is not None:
        events = _causal_events(active, ctx.session, cutoff)
        if events:
            if state["pending_orders"] and state["pending_orders"][0]["side"] == "ENTRY":
                q = state["pending_orders"][0]["amount"]
            else:
                q = position_from_dict(state["open_positions"][0]).quote_input_lamports
            drive_once(events, state, ctx, q_lamports=q, latency=latency,
                       entry_after_unix_nanos=previous)
        return {"status": "ACTIVE_BOOK_ADVANCED", "cutoff_unix_nanos": cutoff,
                "mint": active, "open": len(state["open_positions"]),
                "pending": len(state["pending_orders"])}

    q = _probe_lamports(cutoff)
    candidates: list[tuple[int, str, list]] = []
    if tape.TAPE_DIR.exists():
        for path in tape.TAPE_DIR.glob("*.jsonl"):
            if path.name.startswith("_"):
                continue
            try:
                if path.stat().st_mtime_ns <= previous:
                    continue
            except OSError:
                continue  # incomplete inventory is a missed opportunity, never permission to backfill
            mint = path.stem
            events = _causal_events(mint, ctx.session, cutoff)
            if events and events[-1].observation_unix_nanos > previous:
                candidates.append((events[-1].observation_unix_nanos, mint, events))
    for _latest, mint, _admission_events in sorted(candidates):
        # Candidate inventory can take seconds across thousands of mint files.  Refresh the chosen
        # mint immediately before its internally-clocked decision so a stale admission snapshot does
        # not poison every later attempt.  The watermark still prevents retrospective admission.
        decision_events = _causal_events(mint, ctx.session, time.time_ns())
        drive_once(decision_events, state, ctx, q_lamports=q, latency=latency,
                   entry_after_unix_nanos=previous)
        if _active_mint(state) is not None:
            return {"status": "ENTRY_DECISION_PERSISTED", "cutoff_unix_nanos": cutoff,
                    "mint": mint, "open": len(state["open_positions"]),
                    "pending": len(state["pending_orders"])}
    return {"status": "NO_ELIGIBLE_SIGNAL", "cutoff_unix_nanos": cutoff,
            "candidates": len(candidates), "open": 0, "pending": 0}


def run_cycle(*, reaction_nanos: int) -> dict:
    with runner_lock():
        return _run_cycle_unlocked(reaction_nanos=reaction_nanos)


def run_loop(*, reaction_nanos: int, interval_seconds: float) -> None:
    if type(interval_seconds) not in {int, float} or isinstance(interval_seconds, bool) or interval_seconds <= 0:
        raise RefusedExecution("PAC loop interval must be positive")
    with runner_lock():
        while True:
            try:
                print(json.dumps(_run_cycle_unlocked(reaction_nanos=reaction_nanos),
                                 sort_keys=True), flush=True)
            except RefusedExecution as exc:
                print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]},
                                 sort_keys=True), flush=True)
            time.sleep(interval_seconds)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC paper-scenario runner (no wallet/order path)")
    parser.add_argument("--reaction-nanos", type=int, required=True,
                        help="explicit uncalibrated scenario latency; deliberately no default")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.once:
            print(json.dumps(run_cycle(reaction_nanos=args.reaction_nanos), sort_keys=True))
        else:
            run_loop(reaction_nanos=args.reaction_nanos, interval_seconds=args.interval)
        return 0
    except RefusedExecution as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
