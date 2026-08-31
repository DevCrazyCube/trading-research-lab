#!/usr/bin/env python3
"""Authority-bound, hash-chained OPEN/TERMINAL/GHOST mark journal.

Unlike PAC_SCALP mark schema 1, deleting, inserting, reordering, cross-session splicing, or changing
the provider arm is detectable.  The caller supplies the expected byte offset and prior head, so a
runtime truncation or an out-of-band append refuses instead of silently starting a second history.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import pathlib

from .execution import RefusedExecution


SCHEMA = 2
GENESIS = "0" * 64
LIFECYCLES = frozenset({"OPEN", "TERMINAL", "GHOST"})
ARMS = frozenset({"PUBLIC_CONTROL", "LOW_LATENCY_INTERVENTION"})
VENUES = frozenset({"PUMP_CURVE", "PUMPSWAP", "UNAVAILABLE"})
RESERVE_KEYS = frozenset({"virtual_quote", "virtual_token", "real_quote", "real_token", "complete"})


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_sha(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


@dataclass(frozen=True)
class Authority:
    instrument_id: str
    seal_sha256: str
    activation_unix_nanos: int
    calibration_sha256: str
    campaign_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str) or not self.instrument_id:
            raise RefusedExecution("mark authority instrument is invalid")
        if not all(_is_sha(value) for value in (
                self.seal_sha256, self.calibration_sha256, self.campaign_sha256)):
            raise RefusedExecution("mark authority hashes are invalid")
        if type(self.activation_unix_nanos) is not int or self.activation_unix_nanos <= 0:
            raise RefusedExecution("mark authority activation is invalid")


@dataclass(frozen=True)
class JournalHead:
    sequence: int = 0
    record_sha256: str = GENESIS
    byte_offset: int = 0

    def __post_init__(self) -> None:
        if (type(self.sequence) is not int or self.sequence < 0 or not _is_sha(self.record_sha256)
                or type(self.byte_offset) is not int or self.byte_offset < 0):
            raise RefusedExecution("mark journal head is invalid")
        if (self.sequence == 0) != (self.record_sha256 == GENESIS):
            raise RefusedExecution("mark journal genesis/head mismatch")


def _validate_reserves(value: object) -> None:
    if not isinstance(value, dict) or set(value) != RESERVE_KEYS:
        raise RefusedExecution("mark reserve state is incomplete")
    for key in RESERVE_KEYS - {"complete"}:
        if type(value[key]) is not int or value[key] < 0:
            raise RefusedExecution("mark reserve state is not exact")
    if type(value["complete"]) is not bool:
        raise RefusedExecution("mark reserve complete flag is not boolean")


def build_record(authority: Authority, head: JournalHead, *, lifecycle: str, route_arm: str,
                 provider_id: str, venue: str, entry_id: str, mint: str,
                 evidence_source: str, raw_evidence_sha256: str,
                 source_received_unix_nanos: int | None,
                 request_started_unix_nanos: int,
                 evidence_received_unix_nanos: int,
                 decision_unix_nanos: int | None,
                 target_unix_nanos: int | None,
                 context_slot: int, reserve_state: dict,
                 entry_all_in_lamports: int,
                 wallet_proceeds_lamports: int | None,
                 ata_rent_reclaim_lamports: int | None,
                 ata_close_cost_lamports: int | None,
                 failed_attempt_cost_lamports: int,
                 liquidation_equity_lamports: int | None,
                 peak_liquidation_equity_lamports: int,
                 priceable: bool, decision_id: str | None = None,
                 attempt_id: str | None = None, terminal_reason: str | None = None) -> dict:
    if lifecycle not in LIFECYCLES or route_arm not in ARMS or venue not in VENUES:
        raise RefusedExecution("mark lifecycle/arm/venue is invalid")
    if not all(isinstance(value, str) and value for value in (
            provider_id, mint, evidence_source)) or not _is_sha(entry_id):
        raise RefusedExecution("mark identity is incomplete")
    if not _is_sha(raw_evidence_sha256):
        raise RefusedExecution("mark raw evidence hash is invalid")
    for value in (decision_id, attempt_id):
        if value is not None and not _is_sha(value):
            raise RefusedExecution("mark decision/attempt id is invalid")
    for label, value in (
            ("request", request_started_unix_nanos), ("receipt", evidence_received_unix_nanos),
            ("context slot", context_slot), ("entry all-in", entry_all_in_lamports),
            ("failed attempts", failed_attempt_cost_lamports),
            ("peak equity", peak_liquidation_equity_lamports)):
        if type(value) is not int or value < 0:
            raise RefusedExecution(f"mark {label} is invalid")
    if entry_all_in_lamports <= 0:
        raise RefusedExecution("mark entry all-in must be positive")
    for label, value in (("source receipt", source_received_unix_nanos),
                         ("decision", decision_unix_nanos), ("target", target_unix_nanos)):
        if value is not None and (type(value) is not int or value < 0):
            raise RefusedExecution(f"mark {label} is invalid")
    if request_started_unix_nanos > evidence_received_unix_nanos:
        raise RefusedExecution("mark evidence receipt predates its request")
    if (source_received_unix_nanos is not None
            and source_received_unix_nanos > evidence_received_unix_nanos):
        raise RefusedExecution("mark source receipt exceeds trusted evidence receipt")
    if evidence_received_unix_nanos <= authority.activation_unix_nanos:
        raise RefusedExecution("mark evidence predates activation")
    if lifecycle == "OPEN":
        if decision_unix_nanos is not None and decision_unix_nanos < evidence_received_unix_nanos:
            raise RefusedExecution("open-mark decision predates the evidence it uses")
        if target_unix_nanos is not None and (
                decision_unix_nanos is None or target_unix_nanos <= decision_unix_nanos):
            raise RefusedExecution("open-mark landing target is not strictly after decision")
    elif lifecycle == "TERMINAL":
        if (decision_unix_nanos is None or target_unix_nanos is None
                or not decision_unix_nanos < target_unix_nanos <= evidence_received_unix_nanos
                or not _is_sha(decision_id) or not _is_sha(attempt_id)):
            raise RefusedExecution("terminal mark lacks causal decision->target->landing linkage")
    elif decision_unix_nanos is not None or target_unix_nanos is not None \
            or decision_id is not None or attempt_id is not None:
        raise RefusedExecution("ghost mark cannot carry a new order linkage")
    _validate_reserves(reserve_state)
    if type(priceable) is not bool:
        raise RefusedExecution("mark priceable is not boolean")
    priced = (wallet_proceeds_lamports, ata_rent_reclaim_lamports,
              ata_close_cost_lamports, liquidation_equity_lamports)
    if priceable:
        if any(type(value) is not int or value < 0 for value in priced) \
                or wallet_proceeds_lamports <= 0:
            raise RefusedExecution("priceable mark lacks exact liquidation components")
        expected = (wallet_proceeds_lamports + ata_rent_reclaim_lamports
                    - ata_close_cost_lamports - failed_attempt_cost_lamports)
        if expected != liquidation_equity_lamports or expected <= 0:
            raise RefusedExecution("mark liquidation equity does not reconcile")
        if peak_liquidation_equity_lamports < liquidation_equity_lamports:
            raise RefusedExecution("mark peak equity is below observed equity")
    elif any(value is not None for value in priced):
        raise RefusedExecution("unpriceable mark invented liquidation values")
    if lifecycle == "TERMINAL" and (not isinstance(terminal_reason, str) or not terminal_reason):
        raise RefusedExecution("terminal mark lacks a reason")
    if lifecycle != "TERMINAL" and terminal_reason is not None:
        raise RefusedExecution("non-terminal mark carries a terminal reason")
    body = {
        "schema": SCHEMA,
        "instrument_id": authority.instrument_id,
        "seal_sha256": authority.seal_sha256,
        "activation_unix_nanos": authority.activation_unix_nanos,
        "calibration_sha256": authority.calibration_sha256,
        "campaign_sha256": authority.campaign_sha256,
        "sequence": head.sequence + 1,
        "previous_record_sha256": head.record_sha256,
        "lifecycle": lifecycle,
        "route_arm": route_arm,
        "provider_id": provider_id,
        "venue": venue,
        "entry_id": entry_id,
        "mint": mint,
        "evidence_source": evidence_source,
        "raw_evidence_sha256": raw_evidence_sha256,
        "source_received_unix_nanos": source_received_unix_nanos,
        "request_started_unix_nanos": request_started_unix_nanos,
        "evidence_received_unix_nanos": evidence_received_unix_nanos,
        "decision_unix_nanos": decision_unix_nanos,
        "target_unix_nanos": target_unix_nanos,
        "context_slot": context_slot,
        "reserve_state": reserve_state,
        "entry_all_in_lamports": entry_all_in_lamports,
        "wallet_proceeds_lamports": wallet_proceeds_lamports,
        "ata_rent_reclaim_lamports": ata_rent_reclaim_lamports,
        "ata_close_cost_lamports": ata_close_cost_lamports,
        "failed_attempt_cost_lamports": failed_attempt_cost_lamports,
        "liquidation_equity_lamports": liquidation_equity_lamports,
        "peak_liquidation_equity_lamports": peak_liquidation_equity_lamports,
        "priceable": priceable,
        "decision_id": decision_id,
        "attempt_id": attempt_id,
        "terminal_reason": terminal_reason,
    }
    return {**body, "record_sha256": _sha(body)}


def append(path: pathlib.Path, authority: Authority, head: JournalHead, **fields) -> JournalHead:
    raise RefusedExecution(
        "standalone performance mark writes are disabled; use PAC_SCALP_LL unified ledger MARK")
    # Kept below as unreachable reference code for legacy journal verification/migration.
    path = pathlib.Path(path)
    observed_size = path.stat().st_size if path.exists() else 0
    if observed_size != head.byte_offset:
        raise RefusedExecution("mark journal byte offset drift refuses")
    row = build_record(authority, head, **fields)
    payload = _canonical(row) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short mark-journal append")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if observed_size == 0:
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return JournalHead(row["sequence"], row["record_sha256"], observed_size + len(payload))


def verify(path: pathlib.Path, authority: Authority) -> JournalHead:
    path = pathlib.Path(path)
    if not path.exists():
        return JournalHead()
    head = JournalHead()
    offset = 0
    lifecycle_by_entry: dict[str, str] = {}
    identity_by_entry: dict[str, tuple] = {}
    with path.open("rb") as handle:
        for number, raw in enumerate(handle, 1):
            offset += len(raw)
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RefusedExecution(f"mark journal line {number} is malformed") from exc
            observed_hash = row.get("record_sha256")
            body = dict(row); body.pop("record_sha256", None)
            if observed_hash != _sha(body):
                raise RefusedExecution(f"mark journal line {number} hash mismatch")
            if (row.get("sequence") != head.sequence + 1
                    or row.get("previous_record_sha256") != head.record_sha256):
                raise RefusedExecution(f"mark journal line {number} chain mismatch")
            if any(row.get(key) != expected for key, expected in {
                    "instrument_id": authority.instrument_id,
                    "seal_sha256": authority.seal_sha256,
                    "activation_unix_nanos": authority.activation_unix_nanos,
                    "calibration_sha256": authority.calibration_sha256,
                    "campaign_sha256": authority.campaign_sha256}.items()):
                raise RefusedExecution(f"mark journal line {number} authority mismatch")
            field_names = {
                "lifecycle", "route_arm", "provider_id", "venue", "entry_id", "mint",
                "evidence_source", "raw_evidence_sha256", "source_received_unix_nanos",
                "request_started_unix_nanos", "evidence_received_unix_nanos",
                "decision_unix_nanos", "target_unix_nanos", "context_slot", "reserve_state",
                "entry_all_in_lamports", "wallet_proceeds_lamports",
                "ata_rent_reclaim_lamports", "ata_close_cost_lamports",
                "failed_attempt_cost_lamports", "liquidation_equity_lamports",
                "peak_liquidation_equity_lamports", "priceable", "decision_id", "attempt_id",
                "terminal_reason",
            }
            expected_keys = field_names | {
                "schema", "instrument_id", "seal_sha256", "activation_unix_nanos",
                "calibration_sha256", "campaign_sha256", "sequence",
                "previous_record_sha256", "record_sha256",
            }
            if set(row) != expected_keys:
                raise RefusedExecution(f"mark journal line {number} schema mismatch")
            rebuilt = build_record(
                authority, head, **{name: row[name] for name in field_names})
            if rebuilt != row:
                raise RefusedExecution(f"mark journal line {number} semantic rebuild mismatch")
            identity = (row["mint"], row["route_arm"], row["provider_id"],
                        row["entry_all_in_lamports"])
            prior_identity = identity_by_entry.setdefault(row["entry_id"], identity)
            if prior_identity != identity:
                raise RefusedExecution(f"mark journal line {number} changes entry identity/arm")
            prior_lifecycle = lifecycle_by_entry.get(row["entry_id"])
            lifecycle = row["lifecycle"]
            if lifecycle == "TERMINAL" and prior_lifecycle != "OPEN":
                raise RefusedExecution(f"mark journal line {number} terminates before an open mark")
            if lifecycle == "OPEN" and prior_lifecycle in {"TERMINAL", "GHOST"}:
                raise RefusedExecution(f"mark journal line {number} reopens a terminal entry")
            if lifecycle == "TERMINAL" and prior_lifecycle in {"TERMINAL", "GHOST"}:
                raise RefusedExecution(f"mark journal line {number} double-terminates an entry")
            if lifecycle == "GHOST" and prior_lifecycle not in {"TERMINAL", "GHOST"}:
                raise RefusedExecution(f"mark journal line {number} ghosts a non-terminal entry")
            lifecycle_by_entry[row["entry_id"]] = lifecycle
            head = JournalHead(row["sequence"], observed_hash, offset)
    return head
