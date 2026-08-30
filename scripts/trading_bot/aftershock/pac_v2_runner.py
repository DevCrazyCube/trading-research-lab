#!/usr/bin/env python3
"""Persistent causal PAC V2 PAPER-SCENARIO runner.

There is deliberately no wallet, signer, transaction builder, or sender here.  A decision persists a
modeled landing target; only an account snapshot requested after that target can price the attempt.
This removes PAC V1's dependency on a later trade and makes the horizon a wall-clock invariant.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
import pathlib
import tempfile
import time

from .execution import IntentKind, OrderIntent, PriceUnavailable, RefusedExecution, q_lamports_for_usd
from .feasibility import kernel_accounting
from . import pac_v2_detector as detector
from . import pac_v2_feed as feed
from . import pac_v2_policy as policy
from .pac_v2_calibration import Calibration
from .pac_v2_snapshot import (
    LandingSnapshot, MAX_SNAPSHOT_STALENESS_NANOS, PublicRpcSnapshotProvider,
    SnapshotProvider, SnapshotUnavailable,
    snapshot_to_dict,
)
from .pac_v2_pumpswap import (
    PumpSwapProvider, PumpSwapUnavailable, observation_to_dict,
    sell_quote as pumpswap_sell_quote,
)
from . import solusd_recorder


INSTRUMENT = "AFTERSHOCK_PAC_V2"
SCHEMA = 2
LEDGER_SCHEMA = 2
PROBE_USD = "10"
SLIPPAGE_BPS = 1_000
SLIPPAGE_DEN = 10_000
SNAPSHOT_TIMEOUT_NANOS = MAX_SNAPSHOT_STALENESS_NANOS
SCAN_INTERVAL_SECONDS = 0.10
# The bonding-curve feed goes permanently silent when a mint graduates to PumpSwap, so a held
# position must be actively re-observed on-chain.  This is the throttled cadence of that liveness
# probe for the single open position, and the bounded window a graduated pool has to become
# observable before an unexitable full loss is booked (the 12-minute horizon is the hard backstop).
POSITION_REFRESH_INTERVAL_NANOS = 2_000_000_000
POOL_GRACE_NANOS = 120_000_000_000
# On a CONFIRMED full-position exit the token account is emptied and can be closed, refunding its
# rent-exemption deposit (the single largest toll component) minus one closeAccount transaction's gas.
# A real bot always reclaims this; charging it as a permanent sunk cost understates every trade by
# ~2%.  Reclaimed only on an observed full exit, never on an unexitable full loss (the position is
# stuck and its close cannot be confirmed).
ATA_CLOSE_GAS_LAMPORTS = 5_000
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
STATE = RESEARCH / f"{INSTRUMENT}_RUNNER_STATE.json"
LEDGER = RESEARCH / f"{INSTRUMENT}_SCENARIO_LEDGER.jsonl"
LOCK = RESEARCH / f"{INSTRUMENT}_RUNNER.lock"


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class RuntimeProof:
    seal_sha256: str
    activation_unix_nanos: int
    calibration: Calibration

    def __post_init__(self) -> None:
        if (not isinstance(self.seal_sha256, str) or len(self.seal_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.seal_sha256)):
            raise RefusedExecution("PAC V2 runtime seal hash is invalid")
        if type(self.activation_unix_nanos) is not int or self.activation_unix_nanos < 0:
            raise RefusedExecution("PAC V2 activation is invalid")
        if not isinstance(self.calibration, Calibration):
            raise RefusedExecution("PAC V2 runtime lacks typed latency calibration")
        if max(self.calibration.last_land_unix_nanos,
               self.calibration.last_attested_unix_nanos) >= self.activation_unix_nanos:
            raise RefusedExecution("PAC V2 activation must follow the attested calibration artifact")


@dataclass
class OpenPosition:
    mint: str
    token_atoms: int
    quote_input_lamports: int
    entry_all_in_lamports: int
    entry_curve_fee_lamports: int
    entry_attempt_cost_lamports: int
    ata_rent_lamports: int
    entry_unix_nanos: int
    peak_net_exit_lamports: int
    failed_exit_cost_lamports: int
    entry_id: str
    last_context_slot: int
    last_state: dict
    graduated_first_seen_unix_nanos: int = 0
    last_refresh_unix_nanos: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.mint, str) or not self.mint:
            raise RefusedExecution("PAC V2 open position mint is invalid")
        for name in ("token_atoms", "quote_input_lamports", "entry_all_in_lamports"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise RefusedExecution(f"PAC V2 open position {name} is invalid")
        for name in ("entry_curve_fee_lamports", "entry_attempt_cost_lamports", "ata_rent_lamports",
                     "entry_unix_nanos", "peak_net_exit_lamports", "failed_exit_cost_lamports",
                     "last_context_slot", "graduated_first_seen_unix_nanos",
                     "last_refresh_unix_nanos"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise RefusedExecution(f"PAC V2 open position {name} is invalid")
        if self.entry_all_in_lamports != (self.quote_input_lamports + self.entry_curve_fee_lamports
                                         + self.entry_attempt_cost_lamports + self.ata_rent_lamports):
            raise RefusedExecution("PAC V2 open-position entry costs do not reconcile")
        if (not isinstance(self.entry_id, str) or len(self.entry_id) != 64
                or any(c not in "0123456789abcdef" for c in self.entry_id)):
            raise RefusedExecution("PAC V2 open-position entry id is invalid")
        try:
            feed.ReserveState(**self.last_state)
        except (TypeError, ValueError, RefusedExecution) as exc:
            raise RefusedExecution("PAC V2 open-position reserve state is invalid") from exc


def _new_state(proof: RuntimeProof, *, event_offset: int, receipt_offset: int) -> dict:
    return {
        "schema": SCHEMA, "instrument_id": INSTRUMENT,
        "seal_sha256": proof.seal_sha256,
        "activation_unix_nanos": proof.activation_unix_nanos,
        "calibration_sha256": proof.calibration.artifact_sha256,
        "reaction_p90_nanos": proof.calibration.reaction_p90_nanos,
        "cursor": {"event_offset": event_offset, "receipt_offset": receipt_offset,
                   "pending": {}, "rejected_receipts": []},
        "buffers": {}, "open_position": None, "pending_order": None,
        "entry_watermark_source_unix_nanos": proof.activation_unix_nanos,
        "pending_ledger_rows": [], "last_status": "INITIALIZED_NO_BACKFILL",
    }


def _validate_state(state: dict, proof: RuntimeProof) -> None:
    required = {"schema", "instrument_id", "seal_sha256", "activation_unix_nanos",
                "calibration_sha256", "reaction_p90_nanos", "cursor", "buffers",
                "open_position", "pending_order", "entry_watermark_source_unix_nanos",
                "pending_ledger_rows", "last_status"}
    if not isinstance(state, dict) or set(state) != required:
        raise RefusedExecution("PAC V2 runner state schema mismatch")
    bindings = (state["schema"] == SCHEMA and state["instrument_id"] == INSTRUMENT
                and state["seal_sha256"] == proof.seal_sha256
                and state["activation_unix_nanos"] == proof.activation_unix_nanos
                and state["calibration_sha256"] == proof.calibration.artifact_sha256
                and state["reaction_p90_nanos"] == proof.calibration.reaction_p90_nanos)
    if not bindings:
        raise RefusedExecution("PAC V2 runner state is bound to a different runtime proof")
    cursor = state["cursor"]
    if (not isinstance(cursor, dict) or set(cursor) != {
            "event_offset", "receipt_offset", "pending", "rejected_receipts"}
            or any(type(cursor[key]) is not int or cursor[key] < 0
                   for key in ("event_offset", "receipt_offset"))
            or not isinstance(cursor["pending"], dict)
            or not isinstance(cursor["rejected_receipts"], list)):
        raise RefusedExecution("PAC V2 runner cursor is invalid")
    for rejection in cursor["rejected_receipts"]:
        if (not isinstance(rejection, dict)
                or set(rejection) != {"event_id", "reason", "receipt_sha256"}
                or rejection["reason"] not in {"ORPHAN_RECEIPT", "DUPLICATE_RECEIPT"}
                or not isinstance(rejection["event_id"], str)
                or not isinstance(rejection["receipt_sha256"], str)
                or len(rejection["receipt_sha256"]) != 64
                or any(c not in "0123456789abcdef"
                       for c in rejection["receipt_sha256"])):
            raise RefusedExecution("PAC V2 runner cursor contains a malformed receipt refusal")
    if not isinstance(state["buffers"], dict) or not isinstance(state["pending_ledger_rows"], list):
        raise RefusedExecution("PAC V2 runner collections are invalid")
    if type(state["entry_watermark_source_unix_nanos"]) is not int:
        raise RefusedExecution("PAC V2 entry watermark is invalid")
    if state["open_position"] is not None:
        if not isinstance(state["open_position"], dict):
            raise RefusedExecution("PAC V2 open position is not an object")
        try:
            OpenPosition(**state["open_position"])
        except TypeError as exc:
            raise RefusedExecution("PAC V2 open position schema mismatch") from exc
    pending = state["pending_order"]
    if pending is not None:
        required_pending = {"side", "mint", "amount", "min_out", "decision_id",
                            "decision_unix_nanos", "target_unix_nanos", "action", "entry_id",
                            "minimum_context_slot", "observation_failures",
                            "last_observation_failure"}
        venue = pending.get("venue") if isinstance(pending, dict) else None
        allowed = required_pending | ({"venue", "graduated_first_seen_unix_nanos"}
                                      if venue is not None else set())
        if not isinstance(pending, dict) or set(pending) != allowed:
            raise RefusedExecution("PAC V2 pending-order schema mismatch")
        if venue is not None and (venue != "PUMPSWAP"
                or type(pending["graduated_first_seen_unix_nanos"]) is not int
                or pending["graduated_first_seen_unix_nanos"] <= 0):
            raise RefusedExecution("PAC V2 pending-order venue is invalid")
        if pending["side"] not in {"ENTRY", "EXIT"}:
            raise RefusedExecution("PAC V2 pending-order side is invalid")
        for name in ("amount", "min_out", "decision_unix_nanos", "target_unix_nanos",
                     "minimum_context_slot"):
            if type(pending[name]) is not int or pending[name] <= 0:
                raise RefusedExecution(f"PAC V2 pending-order {name} is invalid")
        if (pending["target_unix_nanos"]
                != pending["decision_unix_nanos"] + state["reaction_p90_nanos"]):
            raise RefusedExecution("PAC V2 pending target does not equal decision plus calibrated p90")
        if (not isinstance(pending["decision_id"], str) or len(pending["decision_id"]) != 64
                or type(pending["observation_failures"]) is not int
                or pending["observation_failures"] < 0):
            raise RefusedExecution("PAC V2 pending-order identity/counter is invalid")
        if pending["side"] == "ENTRY":
            if pending["action"] is not None or pending["entry_id"] is not None or state["open_position"] is not None:
                raise RefusedExecution("PAC V2 pending entry carries exit/open-position fields")
        else:
            if venue == "PUMPSWAP":
                exit_allowed = {"EXIT_VENUE_TRANSITION"}
            else:
                exit_allowed = {value.value for value in policy.ExitAction} - {
                    policy.ExitAction.HOLD.value, policy.ExitAction.UNEXITABLE_FULL_LOSS.value}
            if (pending["action"] not in exit_allowed or not isinstance(pending["entry_id"], str)
                    or state["open_position"] is None
                    or pending["mint"] != state["open_position"]["mint"]
                    or pending["entry_id"] != state["open_position"]["entry_id"]):
                raise RefusedExecution("PAC V2 pending exit does not reconcile to the open position")
    for mint, raw_events in state["buffers"].items():
        if not isinstance(mint, str) or not mint or not isinstance(raw_events, list):
            raise RefusedExecution("PAC V2 durable buffer is invalid")
        events = tuple(_event(item) for item in raw_events)
        if events and (any(item.mint != mint for item in events)
                       or any(right.source_received_unix_nanos <= left.source_received_unix_nanos
                              for left, right in zip(events, events[1:]))
                       or any(right.pre_state != left.post_state for left, right in zip(events, events[1:]))):
            raise RefusedExecution("PAC V2 durable buffer ordering/reconciliation failed")
    for row in state["pending_ledger_rows"]:
        _validate_ledger(row)


def _atomic_write(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pac_v2_", suffix=".json")
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _event_dict(event: feed.ClockedEvent) -> dict:
    row = asdict(event)
    return row


def _event(raw: dict) -> feed.ClockedEvent:
    try:
        values = dict(raw)
        values["pre_state"] = feed.ReserveState(**values["pre_state"])
        values["post_state"] = feed.ReserveState(**values["post_state"])
        return feed.ClockedEvent(**values)
    except (KeyError, TypeError, ValueError) as exc:
        raise RefusedExecution("PAC V2 durable event is malformed") from exc


def _cursor(raw: dict) -> feed.Cursor:
    return feed.Cursor(event_offset=raw["event_offset"], receipt_offset=raw["receipt_offset"],
                       pending=dict(raw["pending"]),
                       rejected_receipts=list(raw["rejected_receipts"]))


def _cursor_dict(cursor: feed.Cursor) -> dict:
    return {"event_offset": cursor.event_offset, "receipt_offset": cursor.receipt_offset,
            "pending": cursor.pending, "rejected_receipts": cursor.rejected_receipts}


def _ledger_row(state: dict, kind: str, body: dict) -> dict:
    row = {"schema": LEDGER_SCHEMA, "instrument_id": INSTRUMENT,
           "seal_sha256": state["seal_sha256"],
           "calibration_sha256": state["calibration_sha256"],
           "activation_unix_nanos": state["activation_unix_nanos"],
           "kind": kind, **body}
    # A body payload (e.g. a rejected feed receipt) may carry its OWN "event_id"; our ledger id must be the
    # hash of the row WITHOUT any event_id, exactly as _validate_ledger recomputes it — otherwise a foreign
    # event_id pollutes the hash and every later _validate_ledger refuses the row (blocking the runner).
    row.pop("event_id", None)
    row["event_id"] = _hash(row)
    return row


def _validate_ledger(row: dict) -> None:
    if (not isinstance(row, dict) or row.get("schema") != LEDGER_SCHEMA
            or row.get("instrument_id") != INSTRUMENT):
        raise RefusedExecution("PAC V2 ledger row schema mismatch")
    event_id = row.get("event_id"); body = dict(row); body.pop("event_id", None)
    if not isinstance(event_id, str) or _hash(body) != event_id:
        raise RefusedExecution("PAC V2 ledger row hash mismatch")


def _flush(state: dict, *, state_path: pathlib.Path, ledger_path: pathlib.Path) -> None:
    existing: dict[str, dict] = {}
    if ledger_path.exists():
        for number, line in enumerate(ledger_path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RefusedExecution(f"PAC V2 ledger line {number} is malformed") from exc
            _validate_ledger(row)
            if row["event_id"] in existing and existing[row["event_id"]] != row:
                raise RefusedExecution("PAC V2 ledger id collision")
            existing[row["event_id"]] = row
    if state["pending_ledger_rows"]:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_existed = ledger_path.exists()
        with ledger_path.open("a") as handle:
            for row in state["pending_ledger_rows"]:
                _validate_ledger(row)
                if row["event_id"] not in existing:
                    handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                    existing[row["event_id"]] = row
            handle.flush(); os.fsync(handle.fileno())
        if not ledger_existed:
            directory = os.open(ledger_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        state["pending_ledger_rows"] = []
        _atomic_write(state_path, state)


def _commit(state: dict, rows: list[dict], *, state_path: pathlib.Path,
            ledger_path: pathlib.Path) -> None:
    state["pending_ledger_rows"].extend(rows)
    _atomic_write(state_path, state)
    _flush(state, state_path=state_path, ledger_path=ledger_path)


def _snapshot_attempt_id(pending: dict, snapshot: LandingSnapshot) -> str:
    return _hash({"decision_id": pending["decision_id"], "side": pending["side"],
                  "target": pending["target_unix_nanos"], "snapshot": snapshot.raw_response_sha256})


def _resolve_full_loss(state: dict, position: OpenPosition, *, now: int, action: str,
                       reason: str, attempt_id: str | None = None,
                       evidence_refusal: str | None = None) -> dict:
    body = {
        "mint": position.mint, "entry_id": position.entry_id, "exit_attempt_id": attempt_id,
        "action": action, "reason": reason, "resolved_unix_nanos": now,
        "entry_all_in_lamports": position.entry_all_in_lamports,
        "failed_exit_cost_lamports": position.failed_exit_cost_lamports,
        "net_exit_lamports": 0,
        "net_return_num": -position.entry_all_in_lamports - position.failed_exit_cost_lamports,
        "net_return_den": position.entry_all_in_lamports, "unexitable_full_loss": True,
        "ata_rent_treatment": "CHARGED_NOT_RECLAIMED_WITHOUT_OBSERVED_CLOSE",
    }
    if evidence_refusal is not None:
        body["evidence_refusal"] = evidence_refusal
    return _ledger_row(state, "resolved", body)


def _complete_pending(state: dict, provider: SnapshotProvider, pumpswap_provider, *,
                      now: int) -> list[dict]:
    pending = state["pending_order"]
    if pending is None or now < pending["target_unix_nanos"]:
        return []
    if pending.get("venue") == "PUMPSWAP":
        return _complete_pumpswap_exit(state, pumpswap_provider, pending, now=now)
    if now - pending["target_unix_nanos"] >= SNAPSHOT_TIMEOUT_NANOS:
        state["pending_order"] = None
        if pending["side"] == "ENTRY":
            return [_ledger_row(state, "entry_rejected", {
                "mint": pending["mint"], "decision_id": pending["decision_id"],
                "reason": "SNAPSHOT_DEADLINE_ELAPSED",
                "decision_unix_nanos": pending["decision_unix_nanos"],
                "target_unix_nanos": pending["target_unix_nanos"],
                "observation_failures": pending["observation_failures"]})]
        position = OpenPosition(**state["open_position"])
        if pending["action"] == policy.ExitAction.EXIT_HORIZON.value:
            state["open_position"] = None
            return [_resolve_full_loss(
                state, position, now=now, action=pending["action"],
                reason="HORIZON_SNAPSHOT_DEADLINE_ELAPSED")]
        return [_ledger_row(state, "exit_rejected", {
            "mint": pending["mint"], "entry_id": pending["entry_id"],
            "decision_id": pending["decision_id"], "action": pending["action"],
            "reason": "SNAPSHOT_DEADLINE_RETURN_TO_HOLD",
            "observation_failures": pending["observation_failures"]})]
    try:
        snapshot = provider.capture(
            pending["mint"], pending["target_unix_nanos"], pending["minimum_context_slot"])
    except SnapshotUnavailable as exc:
        pending["observation_failures"] += 1
        pending["last_observation_failure"] = str(exc)[:200]
        return []
    except RefusedExecution as exc:
        # Decode/owner/layout/regime refusals are permanent for this requested fill. They must
        # advance the state rather than crash-looping the single-position lock.
        pending["observation_failures"] += 1
        state["pending_order"] = None
        if pending["side"] == "ENTRY":
            return [_ledger_row(state, "entry_rejected", {
                "mint": pending["mint"], "decision_id": pending["decision_id"],
                "reason": "SNAPSHOT_PERMANENT_REFUSAL",
                "refusal": str(exc)[:200],
                "decision_unix_nanos": pending["decision_unix_nanos"],
                "target_unix_nanos": pending["target_unix_nanos"],
                "observation_failures": pending["observation_failures"]})]
        position = OpenPosition(**state["open_position"])
        state["open_position"] = None
        return [_resolve_full_loss(
            state, position, now=now, action=pending["action"],
            reason="EXIT_SNAPSHOT_PERMANENT_REFUSAL",
            evidence_refusal=str(exc)[:200])]

    attempt_id = _snapshot_attempt_id(pending, snapshot)
    intent = OrderIntent(IntentKind.EXACT_QUOTE_BUY if pending["side"] == "ENTRY"
                         else IntentKind.EXACT_TOKEN_SELL,
                         pending["amount"], pending["min_out"])
    try:
        accounting = kernel_accounting(snapshot.state, intent)
    except PriceUnavailable:
        accounting = None
    if pending["side"] == "ENTRY":
        state["pending_order"] = None
        if accounting is None or accounting["out_amount"] < pending["min_out"]:
            return [_ledger_row(state, "entry_rejected", {
                "mint": pending["mint"], "decision_id": pending["decision_id"],
                "attempt_id": attempt_id, "reason": "UNAVAILABLE_OR_SLIPPAGE",
                "snapshot": snapshot_to_dict(snapshot)})]
        all_in = -accounting["wallet_delta_lamports"]
        entry_id = _hash({"decision_id": pending["decision_id"], "attempt_id": attempt_id})
        position = OpenPosition(
            mint=pending["mint"], token_atoms=accounting["out_amount"],
            quote_input_lamports=pending["amount"], entry_all_in_lamports=all_in,
            entry_curve_fee_lamports=accounting["curve_fee_lamports"],
            entry_attempt_cost_lamports=accounting["attempt_cost_lamports"],
            ata_rent_lamports=accounting["ata_rent_lamports"],
            entry_unix_nanos=snapshot.response_received_unix_nanos,
            peak_net_exit_lamports=0, failed_exit_cost_lamports=0, entry_id=entry_id,
            last_context_slot=snapshot.context_slot,
            last_state=asdict(snapshot.state))
        state["open_position"] = asdict(position)
        return [_ledger_row(state, "entry_filled", {
            "mint": position.mint, "entry_id": entry_id,
            "decision_id": pending["decision_id"], "attempt_id": attempt_id,
            "quote_input_lamports": position.quote_input_lamports,
            "token_atoms": position.token_atoms,
            "entry_all_in_lamports": position.entry_all_in_lamports,
            "entry_curve_fee_lamports": position.entry_curve_fee_lamports,
            "entry_attempt_cost_lamports": position.entry_attempt_cost_lamports,
            "ata_rent_lamports": position.ata_rent_lamports,
            "snapshot": snapshot_to_dict(snapshot)})]

    position = OpenPosition(**state["open_position"])
    state["pending_order"] = None
    if accounting is None or accounting["wallet_delta_lamports"] <= 0:
        state["open_position"] = None
        return [_resolve_full_loss(state, position, now=now, action=pending["action"],
                                   reason="UNAVAILABLE_OR_NET_NEGATIVE_DUST", attempt_id=attempt_id)]
    if accounting["out_amount"] < pending["min_out"]:
        position.failed_exit_cost_lamports += accounting["attempt_cost_lamports"]
        state["open_position"] = asdict(position)
        if pending["action"] == policy.ExitAction.EXIT_HORIZON.value:
            state["open_position"] = None
            return [_resolve_full_loss(state, position, now=now, action=pending["action"],
                                       reason="HORIZON_SLIPPAGE_FAILURE", attempt_id=attempt_id)]
        return [_ledger_row(state, "exit_rejected", {
            "mint": position.mint, "entry_id": position.entry_id, "attempt_id": attempt_id,
            "action": pending["action"], "reason": "SLIPPAGE_RETURN_TO_HOLD",
            "attempt_cost_lamports": accounting["attempt_cost_lamports"]})]
    net_exit = accounting["wallet_delta_lamports"]
    state["open_position"] = None
    return [_ledger_row(state, "resolved", {
        "mint": position.mint, "entry_id": position.entry_id, "exit_attempt_id": attempt_id,
        "action": pending["action"], "reason": "SCENARIO_ACCOUNT_SNAPSHOT_FILLED",
        "resolved_unix_nanos": snapshot.response_received_unix_nanos,
        "entry_all_in_lamports": position.entry_all_in_lamports,
        "failed_exit_cost_lamports": position.failed_exit_cost_lamports,
        "net_exit_lamports": net_exit,
        "net_return_num": net_exit - position.entry_all_in_lamports
                          - position.failed_exit_cost_lamports
                          + position.ata_rent_lamports - ATA_CLOSE_GAS_LAMPORTS,
        "net_return_den": position.entry_all_in_lamports, "unexitable_full_loss": False,
        "ata_rent_reclaimed_lamports": position.ata_rent_lamports - ATA_CLOSE_GAS_LAMPORTS,
        "ata_rent_treatment": "RECLAIMED_ON_CONFIRMED_FULL_EXIT_NET_CLOSE_GAS",
        "snapshot": snapshot_to_dict(snapshot)})]


def _refresh_and_check_graduation(state: dict, position: OpenPosition, provider: SnapshotProvider,
                                  pumpswap_provider, *, now: int) -> list[dict] | None:
    """Throttled active on-chain liveness probe for the open position.

    The bonding-curve feed goes permanently silent the moment a mint graduates, so the passively
    fed trail state can freeze on a healthy-looking price forever.  This re-reads the curve on a
    bounded cadence.  A healthy live curve refreshes ``last_state`` (so the fast feed trail is never
    stale) and returns ``None`` to fall through to the normal trail.  Any non-tradeable curve (a
    zeroed/closed/complete account, or a transient read failure) escalates to a PumpSwap venue
    transition — the pool's existence is the definitive graduation test.
    """
    if now - position.last_refresh_unix_nanos < POSITION_REFRESH_INTERVAL_NANOS:
        return None
    position.last_refresh_unix_nanos = now
    state["open_position"] = asdict(position)  # persist the throttle stamp even on a failed read
    tradeable = None
    try:
        tradeable = provider.capture(position.mint, now, position.last_context_slot)
    except (SnapshotUnavailable, RefusedExecution):
        # Missing/closed/zeroed/complete curve, or a transient malformed read: the PumpSwap probe
        # in _complete_pumpswap_exit decides graduation-vs-transient, bounded by the grace window.
        tradeable = None
    if tradeable is not None and not tradeable.state.complete:
        position.last_state = asdict(tradeable.state)
        position.last_context_slot = max(position.last_context_slot, tradeable.context_slot)
        # The curve is live again: re-arm the graduation grace clock so a prior transient blip can
        # never poison a genuine graduation minutes later into a zero-grace false full loss. The
        # grace window must only ever accumulate over one contiguous graduation-belief episode.
        position.graduated_first_seen_unix_nanos = 0
        state["open_position"] = asdict(position)
        return None
    if position.graduated_first_seen_unix_nanos == 0:
        position.graduated_first_seen_unix_nanos = now
        state["open_position"] = asdict(position)
    return _open_venue_transition(state, position, now=now)


def _open_venue_transition(state: dict, position: OpenPosition, *, now: int) -> list[dict]:
    """Set a forced cross-venue liquidation of a graduated position on PumpSwap.

    This is not a trailed exit: our feed can no longer track the mint, so the honest action is to
    liquidate at the live pool price (``min_out`` = 1; the resolution books whatever the AMM gives,
    a loss included).  The modeled p90 landing latency still applies at resolution.
    """
    decision_id = _hash({"instrument": INSTRUMENT, "side": "EXIT_VENUE", "mint": position.mint,
                         "entry_id": position.entry_id, "decision_unix_nanos": now})
    state["pending_order"] = {
        "side": "EXIT", "venue": "PUMPSWAP", "mint": position.mint, "amount": position.token_atoms,
        "min_out": 1, "decision_id": decision_id, "decision_unix_nanos": now,
        "target_unix_nanos": now + state["reaction_p90_nanos"],
        "minimum_context_slot": position.last_context_slot,
        "action": "EXIT_VENUE_TRANSITION", "entry_id": position.entry_id,
        "graduated_first_seen_unix_nanos": position.graduated_first_seen_unix_nanos,
        "observation_failures": 0, "last_observation_failure": None,
    }
    return [_ledger_row(state, "exit_decision", {
        "mint": position.mint, "entry_id": position.entry_id, "decision_id": decision_id,
        "action": "EXIT_VENUE_TRANSITION", "decision_unix_nanos": now,
        "target_unix_nanos": state["pending_order"]["target_unix_nanos"],
        "minimum_context_slot": state["pending_order"]["minimum_context_slot"],
        "venue": "PUMPSWAP", "decision_net_exit_lamports": None})]


def _complete_pumpswap_exit(state: dict, pumpswap_provider, pending: dict, *, now: int) -> list[dict]:
    """Resolve a graduated position against the live PumpSwap pool, honestly and boundedly.

    Pool observed -> price the constant-product sell (all-cost, exit gas charged at the same modeled
    per-tx cost the entry paid) and resolve.  Pool not yet observable -> return to HOLD and retry
    until the grace window or the 12-minute horizon, at which point the honest outcome is an
    unexitable full loss: no provable sale route exists.
    """
    position = OpenPosition(**state["open_position"])
    grace_exceeded = now - pending["graduated_first_seen_unix_nanos"] >= POOL_GRACE_NANOS
    horizon_reached = now - position.entry_unix_nanos >= policy.MAX_HOLD_NANOS

    def _bounded_or_full_loss(reason: str, exc: Exception) -> list[dict]:
        state["pending_order"] = None
        if grace_exceeded or horizon_reached:
            state["open_position"] = None
            return [_resolve_full_loss(state, position, now=now, action="EXIT_VENUE_TRANSITION",
                                       reason=reason, evidence_refusal=str(exc)[:200])]
        return [_ledger_row(state, "exit_rejected", {
            "mint": position.mint, "entry_id": position.entry_id, "action": "EXIT_VENUE_TRANSITION",
            "reason": f"{reason}_RETRY", "attempt_cost_lamports": 0,
            "observation_failures": pending["observation_failures"] + 1})]

    try:
        observation = pumpswap_provider.capture(position.mint, pending["minimum_context_slot"])
    except PumpSwapUnavailable as exc:
        return _bounded_or_full_loss("VENUE_TRANSITION_NO_ROUTE", exc)
    except RefusedExecution as exc:
        return _bounded_or_full_loss("VENUE_TRANSITION_REFUSED", exc)

    state["pending_order"] = None
    attempt_id = _hash({"venue": "PUMPSWAP", "pool": observation.pool, "mint": position.mint,
                        "entry_id": position.entry_id, "context_slot": observation.context_slot})
    try:
        quote = pumpswap_sell_quote(position.token_atoms, observation.reserves)
    except PriceUnavailable as exc:
        state["open_position"] = None
        return [_resolve_full_loss(state, position, now=now, action="EXIT_VENUE_TRANSITION",
                                   reason="VENUE_TRANSITION_UNPRICEABLE", attempt_id=attempt_id,
                                   evidence_refusal=str(exc)[:200])]
    # Exit gas is a Solana per-tx cost, not venue-specific: charge the same modeled cost the entry
    # paid so the return stays all-cost.  A net that cannot cover its own gas is an honest full loss.
    exit_gas = position.entry_attempt_cost_lamports
    net_exit = quote["net_quote_lamports"] - exit_gas
    if net_exit <= 0:
        state["open_position"] = None
        return [_resolve_full_loss(state, position, now=now, action="EXIT_VENUE_TRANSITION",
                                   reason="VENUE_TRANSITION_NET_NONPOSITIVE", attempt_id=attempt_id)]
    state["open_position"] = None
    return [_ledger_row(state, "resolved", {
        "mint": position.mint, "entry_id": position.entry_id, "exit_attempt_id": attempt_id,
        "action": "EXIT_VENUE_TRANSITION", "reason": "PUMPSWAP_POOL_SNAPSHOT_FILLED",
        "resolved_unix_nanos": observation.response_received_unix_nanos,
        "entry_all_in_lamports": position.entry_all_in_lamports,
        "failed_exit_cost_lamports": position.failed_exit_cost_lamports,
        "net_exit_lamports": net_exit, "exit_gas_lamports": exit_gas,
        "net_return_num": net_exit - position.entry_all_in_lamports
                          - position.failed_exit_cost_lamports
                          + position.ata_rent_lamports - ATA_CLOSE_GAS_LAMPORTS,
        "net_return_den": position.entry_all_in_lamports, "unexitable_full_loss": False,
        "ata_rent_reclaimed_lamports": position.ata_rent_lamports - ATA_CLOSE_GAS_LAMPORTS,
        "ata_rent_treatment": "RECLAIMED_ON_CONFIRMED_FULL_EXIT_NET_CLOSE_GAS",
        "pumpswap": observation_to_dict(observation), "pumpswap_quote": quote})]


def _service_position(state: dict, provider: SnapshotProvider, pumpswap_provider, *,
                      now: int) -> list[dict]:
    if state["open_position"] is None or state["pending_order"] is not None:
        return []
    position = OpenPosition(**state["open_position"])
    # The account response that established the entry can arrive after this cycle's initial clock
    # sample. Never run an exit policy backward; service begins on a later cycle.
    if now < position.entry_unix_nanos:
        return []
    graduation_rows = _refresh_and_check_graduation(
        state, position, provider, pumpswap_provider, now=now)
    if graduation_rows is not None:
        return graduation_rows
    position = OpenPosition(**state["open_position"])  # last_state/refresh stamp may have changed
    reserve = feed.ReserveState(**position.last_state)
    intent = OrderIntent(IntentKind.EXACT_TOKEN_SELL, position.token_atoms, 1)
    try:
        quote = kernel_accounting(reserve, intent)
        net = quote["wallet_delta_lamports"]
        if net <= 0:
            net = None
    except PriceUnavailable:
        quote = None; net = None
    decision_position = policy.Position(
        position.token_atoms, position.quote_input_lamports, position.entry_unix_nanos,
        position.peak_net_exit_lamports)
    try:
        outcome = policy.decide(
            decision_position, now_unix_nanos=now, net_exit_lamports=net,
            real_quote_lamports=(reserve.real_quote if net is not None else None))
    except ValueError as exc:
        raise RefusedExecution("PAC V2 exit policy refused an invalid causal clock/quote") from exc
    position.peak_net_exit_lamports = outcome.position.peak_net_exit_lamports
    state["open_position"] = asdict(position)
    if outcome.action == policy.ExitAction.HOLD:
        return []
    if outcome.action == policy.ExitAction.UNEXITABLE_FULL_LOSS:
        state["open_position"] = None
        return [_resolve_full_loss(state, position, now=now, action=outcome.action.value,
                                   reason="OBSERVED_STATE_UNPRICEABLE")]
    assert quote is not None and net is not None
    decision_id = _hash({"instrument": INSTRUMENT, "side": "EXIT", "mint": position.mint,
                         "entry_id": position.entry_id, "action": outcome.action.value,
                         "decision_unix_nanos": now, "state": position.last_state, "net_quote": net})
    state["pending_order"] = {
        "side": "EXIT", "mint": position.mint, "amount": position.token_atoms,
        "min_out": max(1, quote["out_amount"] * (SLIPPAGE_DEN - SLIPPAGE_BPS) // SLIPPAGE_DEN),
        "decision_id": decision_id, "decision_unix_nanos": now,
        "target_unix_nanos": now + state["reaction_p90_nanos"],
        "minimum_context_slot": position.last_context_slot,
        "action": outcome.action.value, "entry_id": position.entry_id,
        "observation_failures": 0, "last_observation_failure": None,
    }
    return [_ledger_row(state, "exit_decision", {
        "mint": position.mint, "entry_id": position.entry_id, "decision_id": decision_id,
        "action": outcome.action.value, "decision_unix_nanos": now,
        "target_unix_nanos": state["pending_order"]["target_unix_nanos"],
        "minimum_context_slot": state["pending_order"]["minimum_context_slot"],
        "decision_net_exit_lamports": net})]


def _admit_candidate(state: dict, *, now: int, quote_input_lamports: int) -> list[dict]:
    if state["open_position"] is not None or state["pending_order"] is not None:
        return []
    best = None
    for mint, raw_events in state["buffers"].items():
        events = tuple(_event(item) for item in raw_events)
        qualification = detector.qualify(
            events, reaction_p90_nanos=state["reaction_p90_nanos"],
            quote_input_lamports=quote_input_lamports)
        if (qualification is None
                or events[qualification.evidence_indices[-1]].source_received_unix_nanos
                <= state["entry_watermark_source_unix_nanos"]):
            continue
        candidate = (events[qualification.evidence_indices[-1]].source_received_unix_nanos,
                     mint, events, qualification)
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        return []
    signal_source, mint, events, qualification = best
    decision_state = events[-1].post_state
    intent = OrderIntent(IntentKind.EXACT_QUOTE_BUY, quote_input_lamports, 1)
    try:
        decision_quote = kernel_accounting(decision_state, intent)
    except PriceUnavailable:
        state["entry_watermark_source_unix_nanos"] = max(
            state["entry_watermark_source_unix_nanos"], signal_source)
        return [_ledger_row(state, "entry_rejected", {
            "mint": mint, "reason": "DECISION_STATE_UNPRICEABLE",
            "decision_unix_nanos": now, "evidence_event_ids": list(qualification.evidence_event_ids)})]
    decision_id = _hash({"instrument": INSTRUMENT, "side": "ENTRY", "mint": mint,
                         "decision_unix_nanos": now,
                         "evidence_event_ids": qualification.evidence_event_ids,
                         "quote_input_lamports": quote_input_lamports})
    state["pending_order"] = {
        "side": "ENTRY", "mint": mint, "amount": quote_input_lamports,
        "min_out": max(1, decision_quote["out_amount"]
                       * (SLIPPAGE_DEN - SLIPPAGE_BPS) // SLIPPAGE_DEN),
        "decision_id": decision_id, "decision_unix_nanos": now,
        "target_unix_nanos": now + state["reaction_p90_nanos"], "action": None,
        "minimum_context_slot": max(event.slot for event in events),
        "entry_id": None, "observation_failures": 0, "last_observation_failure": None,
    }
    state["entry_watermark_source_unix_nanos"] = max(
        state["entry_watermark_source_unix_nanos"], signal_source)
    return [_ledger_row(state, "entry_decision", {
        "mint": mint, "decision_id": decision_id, "decision_unix_nanos": now,
        "target_unix_nanos": state["pending_order"]["target_unix_nanos"],
        "minimum_context_slot": state["pending_order"]["minimum_context_slot"],
        "quote_input_lamports": quote_input_lamports,
        "decision_tokens_out": decision_quote["out_amount"],
        "evidence_event_ids": list(qualification.evidence_event_ids),
        "buyer_breadth": qualification.buyer_breadth,
        "dwell_nanos": qualification.dwell_nanos,
        "largest_observed_sell_lamports": qualification.largest_observed_sell_lamports,
        "reserve_cover_lamports": qualification.reserve_cover_lamports})]


def _update_buffers(state: dict, events: list[feed.ClockedEvent], *, now: int) -> None:
    active = None
    if state["open_position"] is not None:
        active = state["open_position"]["mint"]
    if state["pending_order"] is not None:
        active = state["pending_order"]["mint"]
    for event in events:
        if event.source_received_unix_nanos <= state["activation_unix_nanos"]:
            continue
        buffer = state["buffers"].setdefault(event.mint, [])
        # A collector reconnect starts a new continuity epoch.  Its first event is a seed and is
        # intentionally omitted by feed.consume(); the first usable event therefore cannot be
        # reconciled to the previous epoch's last reserve.  Retaining both epochs would make every
        # subsequent state validation fail closed on a legitimate reconnect.
        if buffer and buffer[-1].get("collector_epoch") != event.collector_epoch:
            buffer.clear()
        buffer.append(_event_dict(event))
        if state["open_position"] is not None and event.mint == state["open_position"]["mint"]:
            state["open_position"]["last_state"] = asdict(event.post_state)
            state["open_position"]["last_context_slot"] = max(
                state["open_position"]["last_context_slot"], event.slot)
    cutoff = now - detector.pac_detector.MAX_PATTERN_SPAN_NANOS
    for mint in list(state["buffers"]):
        kept = [item for item in state["buffers"][mint]
                if item["source_received_unix_nanos"] >= cutoff]
        if mint == active and not kept and state["buffers"][mint]:
            kept = [state["buffers"][mint][-1]]
        if kept:
            state["buffers"][mint] = kept
        else:
            del state["buffers"][mint]


def _quote_input(now: int) -> int:
    observation = solusd_recorder.latest_observation(decision_unix_nanos=now)
    return q_lamports_for_usd(
        PROBE_USD, observation, decision_unix_nanos=now,
        max_staleness_nanos=solusd_recorder.MAX_LOCAL_AGE_NANOS)


def _run_once_at(proof: RuntimeProof, provider: SnapshotProvider, pumpswap_provider=None, *,
                 now: int,
                 quote_input_lamports: int | None = None, state_path: pathlib.Path = STATE,
                 ledger_path: pathlib.Path = LEDGER, events_path: pathlib.Path = feed.EVENTS,
                 receipts_path: pathlib.Path = feed.RECEIPTS,
                 initialize_at_eof: bool = True) -> dict:
    """Deterministic test seam. Production callers use run_once, whose clock is internal."""
    # Duck-typed on purpose: when the runner is launched via `python -m …pac_v2_runner` it executes as
    # __main__, so its RuntimeProof class object differs from the manifest-imported package class, and a
    # strict isinstance would reject a genuine, manifest-built proof. Verify the required attributes instead.
    if (not all(hasattr(proof, attr) for attr in ("activation_unix_nanos", "calibration", "seal_sha256"))
            or not hasattr(provider, "capture") or not hasattr(pumpswap_provider, "capture")):
        raise RefusedExecution("PAC V2 run requires runtime proof and both venue providers")
    if type(now) is not int or now <= proof.activation_unix_nanos:
        raise RefusedExecution("PAC V2 runner clock is not post-activation")
    state_path = pathlib.Path(state_path); ledger_path = pathlib.Path(ledger_path)
    if not state_path.exists():
        event_offset = pathlib.Path(events_path).stat().st_size if initialize_at_eof and pathlib.Path(events_path).exists() else 0
        receipt_offset = pathlib.Path(receipts_path).stat().st_size if initialize_at_eof and pathlib.Path(receipts_path).exists() else 0
        state = _new_state(proof, event_offset=event_offset, receipt_offset=receipt_offset)
        _atomic_write(state_path, state)
        return {"status": "INITIALIZED_NO_BACKFILL", "open": 0, "pending": 0, "new_events": 0}
    try:
        state = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("PAC V2 runner state is unreadable") from exc
    _validate_state(state, proof)
    _flush(state, state_path=state_path, ledger_path=ledger_path)
    cursor = _cursor(state["cursor"])
    rejected_before = len(cursor.rejected_receipts)
    new_events = feed.consume(cursor, events_path=events_path, receipts_path=receipts_path,
                              runner_seen_unix_nanos=now)
    state["cursor"] = _cursor_dict(cursor)
    _update_buffers(state, new_events, now=now)
    rows = [_ledger_row(state, "feed_refusal", item)
            for item in cursor.rejected_receipts[rejected_before:]]
    if rows:
        # An authenticated but orphan/duplicate receipt is advanced and recorded once. The whole
        # coincident event batch is conservatively ineligible rather than replayed after restart.
        if new_events:
            state["entry_watermark_source_unix_nanos"] = max(
                state["entry_watermark_source_unix_nanos"],
                max(event.source_received_unix_nanos for event in new_events))
        state["last_status"] = "FEED_REFUSAL_ADVANCED"
        _commit(state, rows, state_path=state_path, ledger_path=ledger_path)
        return {"status": state["last_status"],
                "open": int(state["open_position"] is not None),
                "pending": int(state["pending_order"] is not None),
                "new_events": len(new_events), "ledger_rows": len(rows)}
    completion_rows = _complete_pending(state, provider, pumpswap_provider, now=now)
    rows += completion_rows
    opened_this_cycle = any(row["kind"] == "entry_filled" for row in completion_rows)
    # Persist a completed fill/terminal transition before any later policy work. A downstream
    # refusal can no longer replay the entry snapshot after restart.
    committed_rows = 0
    if completion_rows:
        _commit(state, rows, state_path=state_path, ledger_path=ledger_path)
        committed_rows = len(rows)
        rows = []
    if not opened_this_cycle:
        rows += _service_position(state, provider, pumpswap_provider, now=now)
    if state["open_position"] is None and state["pending_order"] is None:
        q = quote_input_lamports if quote_input_lamports is not None else _quote_input(now)
        if type(q) is not int or q <= 0:
            raise RefusedExecution("PAC V2 quote input is invalid")
        rows += _admit_candidate(state, now=now, quote_input_lamports=q)
    # Once this batch is causally observed it can never become a future new signal after a restart.
    if new_events:
        state["entry_watermark_source_unix_nanos"] = max(
            state["entry_watermark_source_unix_nanos"],
            max(event.source_received_unix_nanos for event in new_events))
    state["last_status"] = ("PENDING" if state["pending_order"] else
                            "OPEN" if state["open_position"] else "SCANNING")
    _commit(state, rows, state_path=state_path, ledger_path=ledger_path)
    return {"status": state["last_status"], "open": int(state["open_position"] is not None),
            "pending": int(state["pending_order"] is not None), "new_events": len(new_events),
            "ledger_rows": committed_rows + len(rows)}


def run_once(proof: RuntimeProof, provider: SnapshotProvider, pumpswap_provider=None, *,
             quote_input_lamports: int | None = None, state_path: pathlib.Path = STATE,
             ledger_path: pathlib.Path = LEDGER, events_path: pathlib.Path = feed.EVENTS,
             receipts_path: pathlib.Path = feed.RECEIPTS,
             initialize_at_eof: bool = True) -> dict:
    """Run one production cycle using only the engine-owned wall clock."""
    return _run_once_at(
        proof, provider, pumpswap_provider, now=time.time_ns(),
        quote_input_lamports=quote_input_lamports,
        state_path=state_path, ledger_path=ledger_path, events_path=events_path,
        receipts_path=receipts_path, initialize_at_eof=initialize_at_eof)


def _lock(path: pathlib.Path = LOCK):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RefusedExecution("another PAC V2 runner owns the state lock") from exc
    return handle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2 calibrated paper-scenario runner")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=SCAN_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    try:
        # Importing the activation gate only here keeps the core independently negative-testable.
        from .pac_v2_manifest import load_runtime_proof
        proof = load_runtime_proof()
        provider = PublicRpcSnapshotProvider()
        pumpswap_provider = PumpSwapProvider()
        with _lock():
            while True:
                started = time.monotonic()
                try:
                    result = run_once(proof, provider, pumpswap_provider)
                except RefusedExecution as exc:
                    result = {"status": "CYCLE_REFUSED", "reason": str(exc)[:240]}
                    print(json.dumps(result, sort_keys=True), flush=True)
                    if args.once:
                        return 2
                else:
                    print(json.dumps(result, sort_keys=True), flush=True)
                if args.once:
                    break
                remaining = args.interval - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)
        return 0
    except RefusedExecution as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
