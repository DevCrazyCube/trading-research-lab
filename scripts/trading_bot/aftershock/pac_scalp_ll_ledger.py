#!/usr/bin/env python3
"""Crash-safe O(new rows) hash-chained ledger for PAC_SCALP_LL.

The old core reread and revalidated the entire multi-megabyte ledger every 100 ms.  This journal
performs one full verification at process start, then binds every append to the persisted byte offset
and chain head.  A crash after append but before state clear is reconciled only when the exact pending
bytes are already present.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import pathlib

from .execution import RefusedExecution
from . import pac_v2_runner as core
from . import pac_scalp_ll_marklog as marks


SCHEMA = 2
GENESIS = "0" * 64
KINDS = frozenset({
    "ENTRY_DECISION", "ENTRY_FILLED", "ENTRY_REFUSED", "EXIT_DECISION",
    "EXIT_FILLED", "VENUE_STATE", "ATA_CLOSE", "MARK", "RESOLVED", "REFUSAL",
})
RESOLUTION_REASONS = frozenset({
    "PUMP_CURVE_FULL_SELL_PRIMARY_RENT_LOCKED",
    "PUMPSWAP_FULL_SELL_PRIMARY_RENT_LOCKED",
    "PUMPSWAP_SOLD_ATA_CLOSE_TIMEOUT_RENT_LOCKED",
    "CROSS_VENUE_DEADLINE_FULL_LOSS",
})
COMMON_BODY = frozenset({
    "entry_id", "mint", "arm", "provider_id", "event_unix_nanos", "payload",
    "submit_endpoint_identity", "observe_endpoint_identity", "config_fingerprint_sha256",
    "entry_cost_profile_sha256", "exit_cost_profile_sha256", "ata_close_cost_profile_sha256",
})
PAYLOAD_FIELDS = {
    "ENTRY_DECISION": frozenset({
        "decision_id", "evidence_sha256", "quote_input_lamports", "min_tokens_out",
        "decision_unix_nanos", "target_unix_nanos", "minimum_context_slot"}),
    "ENTRY_FILLED": frozenset({
        "decision_id", "attempt_id", "snapshot_sha256", "landing_unix_nanos", "token_atoms",
        "quote_input_lamports", "curve_fee_lamports", "route_cost_lamports",
        "ata_rent_lamports", "entry_all_in_lamports"}),
    "ENTRY_REFUSED": frozenset({"decision_id", "reason"}),
    "EXIT_DECISION": frozenset({
        "decision_id", "action", "venue", "decision_unix_nanos", "target_unix_nanos",
        "minimum_context_slot", "decision_liquidation_equity_lamports"}),
    "EXIT_FILLED": frozenset({
        "decision_id", "attempt_id", "venue", "snapshot_sha256", "landing_unix_nanos",
        "full_sale_token_atoms", "gross_quote_lamports", "venue_fee_lamports",
        "route_cost_lamports", "wallet_proceeds_lamports"}),
    "VENUE_STATE": frozenset({
        "state", "reason", "decision_id", "target_unix_nanos",
        "deadline_unix_nanos", "failed_attempt_cost_lamports"}),
    "ATA_CLOSE": frozenset({
        "decision_id", "attempt_id", "target_unix_nanos", "landing_unix_nanos",
        "full_sale_token_atoms", "succeeded", "close_cost_lamports",
        "rent_reclaimed_lamports", "modeled_rent_reclaim_lamports",
        "evidence_mode"}),
    "RESOLVED": frozenset({
        "reason", "terminal_equity_lamports", "entry_all_in_lamports",
        "net_return_num", "net_return_den", "unexitable_full_loss"}),
    "REFUSAL": frozenset({"stage", "reason", "evidence_sha256", "decision_id",
                            "attempt_id", "charged_lamports"}),
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_sha(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def genesis() -> dict:
    return {"sequence": 0, "record_sha256": GENESIS, "byte_offset": 0}


def semantic_genesis() -> dict:
    return {"entry_decisions": {}, "entries": {}, "exit_decisions": {}, "mark_lifecycle": {}}


def _validate_head(head: object) -> dict:
    if (not isinstance(head, dict) or set(head) != {"sequence", "record_sha256", "byte_offset"}
            or type(head["sequence"]) is not int or head["sequence"] < 0
            or not _is_sha(head["record_sha256"])
            or type(head["byte_offset"]) is not int or head["byte_offset"] < 0
            or ((head["sequence"] == 0) != (head["record_sha256"] == GENESIS))):
        raise RefusedExecution("low-latency ledger head is invalid")
    return head


def make_row(state: dict, kind: str, body: dict) -> dict:
    if kind not in KINDS or not isinstance(body, dict):
        raise RefusedExecution("low-latency ledger row inputs are invalid")
    reserved = {"schema", "instrument_id", "seal_sha256", "activation_unix_nanos", "kind",
                "calibration_sha256", "campaign_sha256", "sequence",
                "previous_record_sha256", "record_sha256"}
    if reserved & set(body):
        raise RefusedExecution("ledger body overrides a reserved authority/chain field")
    pending = state["pending_ledger_rows"]
    if pending:
        previous = pending[-1]
        sequence, head_hash = previous["sequence"], previous["record_sha256"]
    else:
        head = _validate_head(state["ledger_head"])
        sequence, head_hash = head["sequence"], head["record_sha256"]
    record = {
        "schema": SCHEMA,
        "instrument_id": state["instrument_id"],
        "seal_sha256": state["seal_sha256"],
        "activation_unix_nanos": state["activation_unix_nanos"],
        "calibration_sha256": state["calibration_sha256"],
        "campaign_sha256": state["campaign_sha256"],
        "kind": kind,
        "sequence": sequence + 1,
        "previous_record_sha256": head_hash,
        **body,
    }
    if "record_sha256" in body:
        raise RefusedExecution("ledger body cannot supply its own record hash")
    record["record_sha256"] = _sha(record)
    _validate_semantics(record)
    return record


def _integer(value: object, *, positive: bool = False) -> bool:
    return type(value) is int and value >= (1 if positive else 0)


def _validate_semantics(row: dict) -> None:
    kind = row.get("kind")
    body = {key: value for key, value in row.items() if key in COMMON_BODY}
    if set(body) != COMMON_BODY or kind not in KINDS:
        raise RefusedExecution("low-latency ledger event body schema mismatch")
    if (not isinstance(body["mint"], str) or not body["mint"]
            or body["arm"] not in marks.ARMS
            or not isinstance(body["provider_id"], str) or not body["provider_id"]
            or not all(isinstance(body[key], str) and body[key].startswith("https://") for key in (
                "submit_endpoint_identity", "observe_endpoint_identity"))
            or not all(_is_sha(body[key]) for key in (
                "config_fingerprint_sha256", "entry_cost_profile_sha256",
                "exit_cost_profile_sha256", "ata_close_cost_profile_sha256"))
            or not _integer(body["event_unix_nanos"])):
        raise RefusedExecution("low-latency ledger event identity is invalid")
    entry_id = body["entry_id"]
    if entry_id is not None and not _is_sha(entry_id):
        raise RefusedExecution("low-latency ledger entry id is invalid")
    if kind not in {"ENTRY_DECISION", "ENTRY_REFUSED", "REFUSAL"} and not _is_sha(entry_id):
        raise RefusedExecution("post-entry ledger event lacks an entry id")
    payload = body["payload"]
    if not isinstance(payload, dict):
        raise RefusedExecution("low-latency ledger event payload is not an object")
    if kind == "MARK":
        authority = marks.Authority(
            row["instrument_id"], row["seal_sha256"], row["activation_unix_nanos"],
            row["calibration_sha256"], row["campaign_sha256"])
        rebuilt = marks.build_record(authority, marks.JournalHead(), **payload)
        # Only semantic fields belong inside the unified journal; mark authority/chain lives outside.
        semantic = {key: rebuilt[key] for key in payload}
        if semantic != payload or payload.get("entry_id") != entry_id \
                or payload.get("mint") != body["mint"] \
                or payload.get("route_arm") != body["arm"] \
                or payload.get("provider_id") != body["provider_id"]:
            raise RefusedExecution("unified mark semantic/identity mismatch")
        return
    expected = PAYLOAD_FIELDS.get(kind)
    if expected is None or set(payload) != expected:
        raise RefusedExecution(f"low-latency ledger {kind} payload schema mismatch")
    for key, value in payload.items():
        if key.endswith("_sha256") or key in {"decision_id", "attempt_id"}:
            if value is not None and not _is_sha(value):
                raise RefusedExecution(f"low-latency ledger {kind}.{key} is invalid")
        elif key.endswith("_unix_nanos") or key.endswith("_lamports") \
                or key in {"minimum_context_slot", "min_tokens_out", "token_atoms",
                           "full_sale_token_atoms", "net_return_den"}:
            if value is not None and not _integer(value):
                raise RefusedExecution(f"low-latency ledger {kind}.{key} is not exact")
    if kind == "ENTRY_FILLED":
        expected_all_in = (payload["quote_input_lamports"] + payload["curve_fee_lamports"]
                           + payload["route_cost_lamports"] + payload["ata_rent_lamports"])
        if (payload["entry_all_in_lamports"] != expected_all_in
                or payload["token_atoms"] <= 0):
            raise RefusedExecution("entry fill all-cost does not reconcile")
        if payload["landing_unix_nanos"] != body["event_unix_nanos"]:
            raise RefusedExecution("entry fill event clock differs from landing")
    elif kind == "EXIT_FILLED":
        expected_wallet = (payload["gross_quote_lamports"] - payload["venue_fee_lamports"]
                           - payload["route_cost_lamports"])
        if (payload["wallet_proceeds_lamports"] != expected_wallet
                or expected_wallet <= 0 or payload["full_sale_token_atoms"] <= 0):
            raise RefusedExecution("exit fill all-cost/full-sale does not reconcile")
        if payload["landing_unix_nanos"] != body["event_unix_nanos"] \
                or payload["venue"] not in {"PUMP_CURVE", "PUMPSWAP"}:
            raise RefusedExecution("exit fill clock/venue is invalid")
    elif kind == "ENTRY_DECISION":
        if not (payload["decision_unix_nanos"] == body["event_unix_nanos"]
                < payload["target_unix_nanos"]):
            raise RefusedExecution("entry decision/target ordering is invalid")
    elif kind == "EXIT_DECISION":
        if (payload["action"] not in {
                "EXIT_HORIZON", "EXIT_HARD_STOP", "EXIT_CAPACITY", "EXIT_TRAIL",
                "VENUE_TRANSITION_REQUIRED"}
                or payload["venue"] not in {"PUMP_CURVE", "PUMPSWAP"}
                or not (payload["decision_unix_nanos"] == body["event_unix_nanos"]
                        < payload["target_unix_nanos"])):
            raise RefusedExecution("exit decision action/venue/clock is invalid")
    elif kind == "ATA_CLOSE":
        if (type(payload["succeeded"]) is not bool
                or payload["rent_reclaimed_lamports"] != 0
                or payload["evidence_mode"]
                != "MODELED_PAPER_ATA_CLOSE_SCENARIO_NOT_EXECUTABLE"
                or not (payload["target_unix_nanos"] <= payload["landing_unix_nanos"]
                        == body["event_unix_nanos"])):
            raise RefusedExecution("ATA-close evidence/rent lifecycle is inconsistent")
    elif kind == "VENUE_STATE":
        if (payload["state"] not in {
                "AWAITING_POOL", "SELL_DECIDED", "AWAITING_ATA_CLOSE",
                "UNSOLD_DEADLINE", "SOLD_CLOSE_TIMEOUT"}
                or payload["deadline_unix_nanos"] <= 0):
            raise RefusedExecution("venue state/deadline is invalid")
    elif kind == "RESOLVED":
        if (payload["net_return_den"] != payload["entry_all_in_lamports"]
                or payload["net_return_num"] != (payload["terminal_equity_lamports"]
                                                  - payload["entry_all_in_lamports"])
                or payload["reason"] not in RESOLUTION_REASONS
                or type(payload["unexitable_full_loss"]) is not bool
                or payload["unexitable_full_loss"] != (payload["terminal_equity_lamports"] == 0)):
            raise RefusedExecution("resolved return/full-loss flag does not reconcile")


def _advance_semantic(state: dict, row: dict) -> None:
    """Apply one exact lifecycle transition; callers use a copy until durable commit succeeds."""
    if not isinstance(state, dict) or set(state) != set(semantic_genesis()):
        raise RefusedExecution("low-latency ledger semantic checkpoint is invalid")
    kind, payload, entry_id = row["kind"], row["payload"], row["entry_id"]
    decisions, entries = state["entry_decisions"], state["entries"]
    exits, mark_lifecycle = state["exit_decisions"], state["mark_lifecycle"]
    if kind == "ENTRY_DECISION":
        decision = payload["decision_id"]
        if decision in decisions:
            raise RefusedExecution("entry decision is duplicated")
        decisions[decision] = {
            "mint": row["mint"], "status": "PENDING", "arm": row["arm"],
            "provider_id": row["provider_id"], "identity": _row_identity(row),
            "quote_input_lamports": payload["quote_input_lamports"],
            "min_tokens_out": payload["min_tokens_out"],
            "target_unix_nanos": payload["target_unix_nanos"]}
    elif kind == "ENTRY_REFUSED":
        decision = decisions.get(payload["decision_id"])
        if decision is None or decision["status"] != "PENDING":
            raise RefusedExecution("entry refusal has no pending decision")
        decision["status"] = "REFUSED"
    elif kind == "ENTRY_FILLED":
        decision = decisions.get(payload["decision_id"])
        if (decision is None or decision["status"] != "PENDING"
                or decision["mint"] != row["mint"] or entry_id in entries
                or decision["identity"] != _row_identity(row)
                or payload["quote_input_lamports"] != decision["quote_input_lamports"]
                or payload["token_atoms"] < decision["min_tokens_out"]
                or payload["landing_unix_nanos"] < decision["target_unix_nanos"]):
            raise RefusedExecution("entry fill has no unique matching decision")
        decision["status"] = "FILLED"
        entries[entry_id] = {
            "mint": row["mint"], "token_atoms": payload["token_atoms"], "phase": "OPEN",
            "identity": _row_identity(row), "entry_all_in_lamports": payload["entry_all_in_lamports"],
            "ata_rent_lamports": payload["ata_rent_lamports"], "failed_cost_lamports": 0,
            "wallet_proceeds_lamports": None, "venue_deadline_unix_nanos": None}
    elif kind == "EXIT_DECISION":
        entry = entries.get(entry_id)
        if (entry is None or entry["phase"] not in {"OPEN", "VENUE"}
                or entry["identity"] != _row_identity(row)):
            raise RefusedExecution("exit decision does not reference an open entry")
        if ((payload["venue"] == "PUMP_CURVE" and entry["phase"] != "OPEN")
                or (payload["venue"] == "PUMPSWAP" and entry["phase"] != "VENUE")
                or (payload["action"] == "VENUE_TRANSITION_REQUIRED"
                    and payload["venue"] != "PUMP_CURVE")):
            raise RefusedExecution("exit decision venue/action is out of lifecycle order")
        decision = payload["decision_id"]
        if decision in exits:
            raise RefusedExecution("exit decision is duplicated")
        exits[decision] = {
            "entry_id": entry_id, "status": "PENDING", "action": payload["action"],
            "venue": payload["venue"], "target_unix_nanos": payload["target_unix_nanos"]}
    elif kind == "EXIT_FILLED":
        decision = exits.get(payload["decision_id"])
        entry = entries.get(entry_id)
        if (decision is None or decision["entry_id"] != entry_id
                or decision["status"] != "PENDING" or entry is None
                or entry["phase"] not in {"OPEN", "VENUE"}
                or entry["identity"] != _row_identity(row)
                or decision["action"] == "VENUE_TRANSITION_REQUIRED"
                or payload["full_sale_token_atoms"] != entry["token_atoms"]
                or payload["venue"] != decision["venue"]
                or payload["landing_unix_nanos"] < decision["target_unix_nanos"]):
            raise RefusedExecution("exit fill is not a unique full-position sale")
        decision["status"] = "FILLED"
        entry["phase"] = "SOLD_AWAITING_CLOSE"
        entry["wallet_proceeds_lamports"] = payload["wallet_proceeds_lamports"]
    elif kind == "VENUE_STATE":
        entry = entries.get(entry_id)
        if (entry is None or entry["phase"] not in {"OPEN", "VENUE", "SOLD_AWAITING_CLOSE"}
                or entry["identity"] != _row_identity(row)):
            raise RefusedExecution("venue transition does not reference an open entry")
        venue_state = payload["state"]
        if venue_state == "AWAITING_POOL":
            decision = exits.get(payload["decision_id"])
            if (entry["phase"] != "OPEN" or decision is None
                    or decision["entry_id"] != entry_id or decision["status"] != "PENDING"
                    or decision["action"] != "VENUE_TRANSITION_REQUIRED"):
                raise RefusedExecution("pool discovery does not follow a curve venue transition")
            decision["status"] = "TRANSITIONED"
            entry["phase"] = "VENUE"
        elif venue_state == "SELL_DECIDED":
            decision = exits.get(payload["decision_id"])
            if (entry["phase"] != "VENUE" or decision is None
                    or decision["entry_id"] != entry_id or decision["status"] != "PENDING"
                    or decision["venue"] != "PUMPSWAP"):
                raise RefusedExecution("PumpSwap sell state lacks its pending decision")
        elif venue_state == "AWAITING_ATA_CLOSE":
            if entry["phase"] != "SOLD_AWAITING_CLOSE":
                raise RefusedExecution("ATA-close wait precedes a full sale")
        elif venue_state == "UNSOLD_DEADLINE":
            if (entry["phase"] != "VENUE"
                    or row["event_unix_nanos"] < payload["deadline_unix_nanos"]):
                raise RefusedExecution("unsold venue deadline is declared early")
            entry["phase"] = "VENUE_EXPIRED"
        elif venue_state == "SOLD_CLOSE_TIMEOUT":
            if entry["phase"] != "SOLD_AWAITING_CLOSE" \
                    or row["event_unix_nanos"] < payload["deadline_unix_nanos"]:
                raise RefusedExecution("sold close timeout is early/unbound")
            entry["phase"] = "CLOSE_TIMEOUT"
        entry["failed_cost_lamports"] = payload["failed_attempt_cost_lamports"]
        entry["venue_deadline_unix_nanos"] = payload["deadline_unix_nanos"]
    elif kind == "ATA_CLOSE":
        entry = entries.get(entry_id)
        if (entry is None or entry["phase"] != "SOLD_AWAITING_CLOSE"
                or entry["identity"] != _row_identity(row)
                or payload["full_sale_token_atoms"] != entry["token_atoms"]):
            raise RefusedExecution("ATA close is not bound to the unique full sale")
        entry["phase"] = "CLOSED" if payload["succeeded"] else "CLOSE_FAILED"
    elif kind == "RESOLVED":
        entry = entries.get(entry_id)
        if (entry is None or entry["phase"] == "RESOLVED"
                or entry["identity"] != _row_identity(row)):
            raise RefusedExecution("resolution lacks a live unique entry")
        if entry["phase"] == "VENUE_EXPIRED":
            expected_equity = 0
        elif entry["phase"] in {"CLOSED", "CLOSE_FAILED", "CLOSE_TIMEOUT"}:
            expected_equity = (entry["wallet_proceeds_lamports"]
                               - entry["failed_cost_lamports"])
        else:
            raise RefusedExecution("resolution precedes terminal sale/venue state")
        if (payload["terminal_equity_lamports"] != expected_equity
                or payload["entry_all_in_lamports"] != entry["entry_all_in_lamports"]):
            raise RefusedExecution("resolution economics are not derived from durable events")
        entry["phase"] = "RESOLVED"
    elif kind == "MARK":
        entry = entries.get(entry_id)
        lifecycle = payload["lifecycle"]
        prior = mark_lifecycle.get(entry_id)
        if entry is None:
            raise RefusedExecution("mark references an unknown entry")
        if lifecycle == "OPEN" and (entry["phase"] == "RESOLVED" or prior in {"TERMINAL", "GHOST"}):
            raise RefusedExecution("open mark follows terminal resolution")
        if lifecycle == "TERMINAL" and (prior in {"TERMINAL", "GHOST"}):
            raise RefusedExecution("entry has multiple terminal marks")
        if lifecycle == "GHOST" and (entry["phase"] != "RESOLVED" or prior not in {"TERMINAL", "GHOST"}):
            raise RefusedExecution("ghost mark precedes terminal resolution")
        mark_lifecycle[entry_id] = lifecycle
    elif kind == "REFUSAL" and entry_id is not None:
        entry = entries.get(entry_id)
        if entry is None or entry["identity"] != _row_identity(row):
            raise RefusedExecution("failed attempt references unknown/drifted entry")
        entry["failed_cost_lamports"] += payload["charged_lamports"]


def _row_identity(row: dict) -> tuple:
    return tuple(row[key] for key in (
        "mint", "arm", "provider_id", "calibration_sha256", "campaign_sha256",
        "submit_endpoint_identity", "observe_endpoint_identity", "config_fingerprint_sha256",
        "entry_cost_profile_sha256", "exit_cost_profile_sha256",
        "ata_close_cost_profile_sha256"))


def _validate_row(row: dict, *, instrument_id: str, seal_sha256: str,
                  activation_unix_nanos: int, calibration_sha256: str,
                  campaign_sha256: str, previous: dict) -> None:
    observed = row.get("record_sha256")
    body = dict(row); body.pop("record_sha256", None)
    if (row.get("schema") != SCHEMA or row.get("instrument_id") != instrument_id
            or row.get("seal_sha256") != seal_sha256
            or row.get("activation_unix_nanos") != activation_unix_nanos
            or row.get("calibration_sha256") != calibration_sha256
            or row.get("campaign_sha256") != campaign_sha256
            or row.get("sequence") != previous["sequence"] + 1
            or row.get("previous_record_sha256") != previous["record_sha256"]
            or observed != _sha(body)):
        raise RefusedExecution("low-latency ledger row/chain/authority mismatch")
    expected_keys = COMMON_BODY | {
        "schema", "instrument_id", "seal_sha256", "activation_unix_nanos",
        "calibration_sha256", "campaign_sha256", "kind", "sequence",
        "previous_record_sha256", "record_sha256",
    }
    if set(row) != expected_keys:
        raise RefusedExecution("low-latency ledger row has unknown/missing fields")
    _validate_semantics(row)


def verify(path: pathlib.Path, *, instrument_id: str, seal_sha256: str,
           activation_unix_nanos: int, calibration_sha256: str,
           campaign_sha256: str) -> dict:
    path = pathlib.Path(path)
    head, _ = verify_with_semantics(
        path, instrument_id=instrument_id, seal_sha256=seal_sha256,
        activation_unix_nanos=activation_unix_nanos,
        calibration_sha256=calibration_sha256, campaign_sha256=campaign_sha256)
    return head


def verify_with_semantics(path: pathlib.Path, *, instrument_id: str, seal_sha256: str,
                          activation_unix_nanos: int, calibration_sha256: str,
                          campaign_sha256: str) -> tuple[dict, dict]:
    path = pathlib.Path(path)
    head = genesis(); semantic = semantic_genesis(); offset = 0
    if not path.exists():
        return head, semantic
    with path.open("rb") as handle:
        for number, raw in enumerate(handle, 1):
            offset += len(raw)
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RefusedExecution(f"low-latency ledger line {number} is malformed") from exc
            _validate_row(row, instrument_id=instrument_id, seal_sha256=seal_sha256,
                          activation_unix_nanos=activation_unix_nanos,
                          calibration_sha256=calibration_sha256,
                          campaign_sha256=campaign_sha256, previous=head)
            _advance_semantic(semantic, row)
            head = {"sequence": row["sequence"], "record_sha256": row["record_sha256"],
                    "byte_offset": offset}
    return head, semantic


def _flush_locked(state: dict, *, state_path: pathlib.Path, ledger_path: pathlib.Path) -> None:
    head = _validate_head(state["ledger_head"])
    pending = state["pending_ledger_rows"]
    observed_size = ledger_path.stat().st_size if ledger_path.exists() else 0
    if not pending:
        if observed_size != head["byte_offset"]:
            raise RefusedExecution("low-latency ledger size drift refuses")
        return
    semantic = json.loads(json.dumps(state.get("ledger_semantic_state")))
    if not isinstance(semantic, dict):
        raise RefusedExecution("low-latency ledger lacks semantic checkpoint")
    previous = head
    for row in pending:
        _validate_row(row, instrument_id=state["instrument_id"],
                      seal_sha256=state["seal_sha256"],
                      activation_unix_nanos=state["activation_unix_nanos"],
                      calibration_sha256=state["calibration_sha256"],
                      campaign_sha256=state["campaign_sha256"], previous=previous)
        _advance_semantic(semantic, row)
        previous = {"sequence": row["sequence"], "record_sha256": row["record_sha256"],
                    "byte_offset": 0}
    payload = b"".join(_canonical(row) + b"\n" for row in pending)
    if observed_size < head["byte_offset"]:
        raise RefusedExecution("low-latency ledger was truncated")
    existing_extra = b""
    append_payload = payload
    if observed_size > head["byte_offset"]:
        with ledger_path.open("rb") as handle:
            handle.seek(head["byte_offset"])
            existing_extra = handle.read()
        if not payload.startswith(existing_extra):
            raise RefusedExecution("low-latency ledger crash recovery bytes mismatch")
        append_payload = payload[len(existing_extra):]
    if append_payload:
        created = not ledger_path.exists()
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(ledger_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            if os.write(descriptor, append_payload) != len(append_payload):
                raise OSError("short low-latency ledger append")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if created:
            directory = os.open(ledger_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    state["ledger_head"] = {
        "sequence": pending[-1]["sequence"],
        "record_sha256": pending[-1]["record_sha256"],
        "byte_offset": head["byte_offset"] + len(payload),
    }
    state["ledger_semantic_state"] = semantic
    state["pending_ledger_rows"] = []
    core._atomic_write(pathlib.Path(state_path), state)


def flush(state: dict, *, state_path: pathlib.Path, ledger_path: pathlib.Path) -> None:
    """Single-writer append/CAS. The lock covers size check, append, fsync and state replacement."""
    ledger_path = pathlib.Path(ledger_path)
    lock_path = ledger_path.with_name(ledger_path.name + ".writer.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RefusedExecution("another low-latency ledger writer owns the append CAS") from exc
        try:
            _flush_locked(state, state_path=pathlib.Path(state_path), ledger_path=ledger_path)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def commit(state: dict, rows: list[dict], *, state_path: pathlib.Path,
           ledger_path: pathlib.Path) -> None:
    state["pending_ledger_rows"].extend(rows)
    core._atomic_write(pathlib.Path(state_path), state)
    flush(state, state_path=pathlib.Path(state_path), ledger_path=pathlib.Path(ledger_path))
