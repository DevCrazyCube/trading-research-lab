#!/usr/bin/env python3
"""AFTERSHOCK causal execution-measurement primitives (handoff 424).

PAPER-ONLY and pure. This module does not submit, sign, or describe a fill as executable evidence.
Public order attempts require a manifest-derived, externally anchored ``SessionProof`` and an immutable
``DecisionRecord`` whose signal is the maximum coordinate of every declared detector-evidence item.
Caller-supplied verification and warm-up booleans do not exist.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import pathlib
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN, getcontext
from enum import Enum

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_LAMPORTS_PER_SOL = 1_000_000_000
getcontext().prec = 50


class RefusedExecution(Exception):
    """The evidence cannot support the requested measurement; fail closed."""


class PriceUnavailable(Exception):
    """A named, expected venue/kernel inability to produce a scenario quote."""


def _require_exact_int(label: str, value: object, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise RefusedExecution(f"{label} must be an exact int, got {type(value).__name__} {value!r}")
    if minimum is not None and value < minimum:
        raise RefusedExecution(f"{label} must be >= {minimum}, got {value}")
    return value


def _require_hash(label: str, value: object) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise RefusedExecution(f"{label} must be lowercase 64-hex, got {value!r}")
    return value


def _hash_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(payload).hexdigest()


class Source(str, Enum):
    PUMPPORTAL = "pumpportal"
    PUBLIC_RPC_PROCESSED = "public_rpc_processed"
    CANONICAL_RPC = "canonical_rpc"


class Calibration(str, Enum):
    UNCALIBRATED = "CALIBRATION_UNCALIBRATED"


class IntentKind(str, Enum):
    EXACT_QUOTE_BUY = "EXACT_QUOTE_BUY"
    EXACT_TOKEN_SELL = "EXACT_TOKEN_SELL"


class Unit(str, Enum):
    LAMPORTS = "lamports"
    ATOMS = "atoms"


class Outcome(str, Enum):
    SCENARIO_FILLED = "SCENARIO_FILLED"
    SCENARIO_FAILED_SLIPPAGE = "SCENARIO_FAILED_SLIPPAGE"
    SCENARIO_UNAVAILABLE = "SCENARIO_UNAVAILABLE"
    RIGHT_CENSORED_NO_BOUNDARY = "RIGHT_CENSORED_NO_BOUNDARY"


@dataclass(frozen=True, order=True)
class CanonicalCoord:
    slot: int
    transaction_index: int
    outer_index: int
    inner_index: int

    def __post_init__(self) -> None:
        for name in ("slot", "transaction_index", "outer_index", "inner_index"):
            _require_exact_int(f"CanonicalCoord.{name}", getattr(self, name), minimum=0)

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.slot, self.transaction_index, self.outer_index, self.inner_index)


@dataclass(frozen=True)
class ReserveState:
    virtual_quote: int
    virtual_token: int
    real_quote: int
    real_token: int
    complete: bool

    def __post_init__(self) -> None:
        _require_exact_int("ReserveState.virtual_quote", self.virtual_quote, minimum=1)
        _require_exact_int("ReserveState.virtual_token", self.virtual_token, minimum=1)
        _require_exact_int("ReserveState.real_quote", self.real_quote, minimum=0)
        _require_exact_int("ReserveState.real_token", self.real_token, minimum=0)
        if self.real_quote > self.virtual_quote or self.real_token > self.virtual_token:
            raise RefusedExecution("real reserves cannot exceed their corresponding virtual reserves")
        if type(self.complete) is not bool:
            raise RefusedExecution("ReserveState.complete must be bool")


@dataclass(frozen=True)
class ObservedEvent:
    mint: str
    observation_unix_nanos: int
    pre_state: ReserveState
    post_state: ReserveState
    source: Source
    evidence_sha: str
    coord: CanonicalCoord | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mint, str) or not self.mint.strip():
            raise RefusedExecution("ObservedEvent.mint is required")
        _require_exact_int("ObservedEvent.observation_unix_nanos", self.observation_unix_nanos, minimum=0)
        if not isinstance(self.pre_state, ReserveState) or not isinstance(self.post_state, ReserveState):
            raise RefusedExecution("ObservedEvent pre/post state must be ReserveState")
        if not isinstance(self.source, Source):
            raise RefusedExecution("ObservedEvent.source must be a Source enum")
        _require_hash("ObservedEvent.evidence_sha", self.evidence_sha)
        if self.source is Source.CANONICAL_RPC and self.coord is None:
            raise RefusedExecution("canonical_rpc observations require a complete canonical coordinate")


def event_commitment(event: ObservedEvent) -> str:
    if not isinstance(event, ObservedEvent):
        raise RefusedExecution("event commitment requires an ObservedEvent")

    def state(value: ReserveState) -> list[object]:
        return [value.virtual_quote, value.virtual_token, value.real_quote, value.real_token, value.complete]

    return _hash_json({
        "mint": event.mint,
        "observation_unix_nanos": event.observation_unix_nanos,
        "pre_state": state(event.pre_state),
        "post_state": state(event.post_state),
        "source": event.source.value,
        "evidence_sha": event.evidence_sha,
        "coord": list(event.coord.as_tuple()) if event.coord is not None else None,
    })


def validate_stream(events: list[ObservedEvent]) -> None:
    if not isinstance(events, list) or not events:
        raise RefusedExecution("event stream must be a non-empty list")
    if any(not isinstance(event, ObservedEvent) for event in events):
        raise RefusedExecution("every stream item must be an ObservedEvent")
    if len({event.mint for event in events}) != 1:
        raise RefusedExecution("one event stream may contain exactly one mint")
    if len({event.source for event in events}) != 1:
        raise RefusedExecution("mixed-source ordering is not causal; split the streams")
    coord_presence = {event.coord is not None for event in events}
    if len(coord_presence) != 1:
        raise RefusedExecution("partially canonicalized stream refused; coordinates must be all present or all absent")
    previous: ObservedEvent | None = None
    seen_coords: set[CanonicalCoord] = set()
    for index, event in enumerate(events):
        if previous is not None:
            if event.observation_unix_nanos <= previous.observation_unix_nanos:
                raise RefusedExecution(f"event {index} receive time is not strictly increasing")
            if event.pre_state != previous.post_state:
                raise RefusedExecution(f"event {index} pre-state does not reconcile to the preceding post-state")
            if event.coord is not None and event.coord <= previous.coord:  # type: ignore[operator]
                raise RefusedExecution(f"event {index} canonical coordinate is duplicate/backward")
        if event.coord is not None:
            if event.coord in seen_coords:
                raise RefusedExecution(f"event {index} duplicates canonical coordinate {event.coord}")
            seen_coords.add(event.coord)
        previous = event


def stream_labels(events: list[ObservedEvent]) -> tuple[str, ...]:
    validate_stream(events)
    labels = ["SIMULATED_OBSERVED_PATH"]
    if events[0].source is Source.PUMPPORTAL:
        labels.append("PUMPPORTAL_RECEIVE_TIME_SCENARIO")
    elif events[0].source is Source.PUBLIC_RPC_PROCESSED:
        labels.append("PUBLIC_RPC_PROCESSED_RECEIVE_TIME_SCENARIO")
    labels.append(Calibration.UNCALIBRATED.value)
    return tuple(labels)


@dataclass(frozen=True)
class LatencyModel:
    reaction_nanos: int
    calibration: Calibration = Calibration.UNCALIBRATED

    def __post_init__(self) -> None:
        _require_exact_int("LatencyModel.reaction_nanos", self.reaction_nanos, minimum=1)
        if self.calibration is not Calibration.UNCALIBRATED:
            raise RefusedExecution("latency calibration is unmeasured; only CALIBRATION_UNCALIBRATED is allowed")


@dataclass(frozen=True)
class OrderIntent:
    kind: IntentKind
    amount: int
    min_out: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, IntentKind):
            raise RefusedExecution("OrderIntent.kind must be an IntentKind enum")
        _require_exact_int("OrderIntent.amount", self.amount, minimum=1)
        _require_exact_int("OrderIntent.min_out", self.min_out, minimum=1)

    @property
    def expected_out_unit(self) -> Unit:
        return Unit.ATOMS if self.kind is IntentKind.EXACT_QUOTE_BUY else Unit.LAMPORTS


@dataclass(frozen=True)
class PriceResult:
    out_amount: int
    unit: Unit
    wallet_cost_lamports: int

    def __post_init__(self) -> None:
        _require_exact_int("PriceResult.out_amount", self.out_amount, minimum=0)
        if not isinstance(self.unit, Unit):
            raise RefusedExecution("PriceResult.unit must be a Unit enum")
        _require_exact_int("PriceResult.wallet_cost_lamports", self.wallet_cost_lamports, minimum=0)


@dataclass(frozen=True)
class SessionProof:
    """A value produced and re-verified by ``manifest.load_session_proof``; never caller-attested."""

    instrument_id: str
    seal_sha256: str
    frozen_json_canonical_sha256: str
    sealed_dependency_items: tuple[tuple[str, str], ...]
    session_event_sha256: str
    activation_root_sha256: str
    activation_anchor_sha256: str
    activation_unix_nanos: int
    resume_after_coord: tuple[int, int, int, int] | None
    warmup_completed_unix_nanos: int
    warmup_event_commitments: tuple[str, ...]
    warmup_max_observation_unix_nanos: int
    warmup_max_coord: tuple[int, int, int, int] | None
    warmup_scope: str = "mint_prefix"

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str) or not self.instrument_id:
            raise RefusedExecution("SessionProof.instrument_id is required")
        for name in ("seal_sha256", "frozen_json_canonical_sha256", "session_event_sha256",
                     "activation_root_sha256", "activation_anchor_sha256"):
            _require_hash(f"SessionProof.{name}", getattr(self, name))
        if not isinstance(self.sealed_dependency_items, tuple) or not self.sealed_dependency_items:
            raise RefusedExecution("SessionProof sealed dependency path/hash pairs are required")
        paths = []
        for item in self.sealed_dependency_items:
            if not isinstance(item, tuple) or len(item) != 2 or not all(isinstance(v, str) for v in item):
                raise RefusedExecution("SessionProof dependency item must be a (path, sha256) tuple")
            paths.append(item[0])
            _require_hash("SessionProof dependency sha256", item[1])
        if paths != sorted(set(paths)):
            raise RefusedExecution("SessionProof dependency paths must be unique and sorted")
        _require_exact_int("SessionProof.activation_unix_nanos", self.activation_unix_nanos, minimum=0)
        _require_exact_int("SessionProof.warmup_completed_unix_nanos", self.warmup_completed_unix_nanos,
                           minimum=self.activation_unix_nanos + 1)
        _require_exact_int("SessionProof.warmup_max_observation_unix_nanos",
                           self.warmup_max_observation_unix_nanos, minimum=self.activation_unix_nanos)
        if self.warmup_max_observation_unix_nanos > self.warmup_completed_unix_nanos:
            raise RefusedExecution("warm-up completion precedes its evidence")
        if not isinstance(self.warmup_event_commitments, tuple) or not self.warmup_event_commitments:
            raise RefusedExecution("SessionProof requires post-activation warm-up evidence")
        for value in self.warmup_event_commitments:
            _require_hash("SessionProof.warmup_event_commitment", value)
        if self.warmup_scope not in {"mint_prefix", "feed_global"}:
            raise RefusedExecution("SessionProof.warmup_scope is invalid")
        for label, coord in (("resume_after_coord", self.resume_after_coord),
                             ("warmup_max_coord", self.warmup_max_coord)):
            if coord is not None:
                if not isinstance(coord, tuple) or len(coord) != 4:
                    raise RefusedExecution(f"SessionProof.{label} must be a four-int tuple or None")
                for value in coord:
                    _require_exact_int(f"SessionProof.{label} item", value, minimum=0)

    @property
    def sealed_dependency_sha256(self) -> tuple[str, ...]:
        return tuple(value for _path, value in self.sealed_dependency_items)

    def dependency_sha256(self, relative_path: str) -> str:
        matches = [value for path, value in self.sealed_dependency_items if path == relative_path]
        if len(matches) != 1:
            raise RefusedExecution(f"dependency {relative_path!r} is absent from the sealed closure")
        return matches[0]


@dataclass(frozen=True)
class ExecutionContext:
    session: SessionProof

    def __post_init__(self) -> None:
        if not isinstance(self.session, SessionProof):
            raise RefusedExecution("ExecutionContext requires a manifest-derived SessionProof")


def _verify_context(ctx: ExecutionContext) -> SessionProof:
    if not isinstance(ctx, ExecutionContext):
        raise RefusedExecution("ExecutionContext is required")
    from . import manifest
    manifest.verify_session_proof(ctx.session)
    return ctx.session


def _validate_session_stream(events: list[ObservedEvent], proof: SessionProof) -> int:
    validate_stream(events)
    if proof.warmup_scope == "feed_global":
        if any(event.observation_unix_nanos <= proof.warmup_completed_unix_nanos for event in events):
            raise RefusedExecution("per-mint decision stream contains pre-global-warm-up evidence")
        if proof.resume_after_coord is not None:
            for event in events:
                if event.coord is None or event.coord.as_tuple() <= proof.resume_after_coord:
                    raise RefusedExecution("decision stream contains pre-resume/uncoordinated evidence")
        return 0
    warmup_count = len(proof.warmup_event_commitments)
    if len(events) <= warmup_count:
        raise RefusedExecution("stream contains warm-up only; no post-warm-up decision event")
    observed_prefix = tuple(event_commitment(event) for event in events[:warmup_count])
    if observed_prefix != proof.warmup_event_commitments:
        raise RefusedExecution("stream warm-up prefix does not match the externally anchored session proof")
    if events[warmup_count - 1].observation_unix_nanos != proof.warmup_max_observation_unix_nanos:
        raise RefusedExecution("warm-up maximum observation clock does not match the stream")
    if proof.resume_after_coord is not None:
        for event in events[:warmup_count]:
            if event.coord is None or event.coord.as_tuple() <= proof.resume_after_coord:
                raise RefusedExecution("warm-up contains pre-resume or uncoordinated evidence")
    return warmup_count


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    instrument_id: str
    seal_sha256: str
    session_event_sha256: str
    activation_root_sha256: str
    detector_sha256: str
    detector_module_path: str
    detector_callable_name: str
    spec_sha256: str
    evaluated_through_index: int
    evaluated_prefix_sha256: str
    stream_snapshot_count: int
    stream_snapshot_sha256: str
    evidence_indices: tuple[int, ...]
    evidence_commitments: tuple[str, ...]
    signal_index: int
    max_evidence_observation_unix_nanos: int
    max_evidence_coord: tuple[int, int, int, int] | None
    decision_unix_nanos: int

    def __post_init__(self) -> None:
        for name in ("decision_id", "seal_sha256", "session_event_sha256", "activation_root_sha256",
                     "detector_sha256", "spec_sha256", "evaluated_prefix_sha256",
                     "stream_snapshot_sha256"):
            _require_hash(f"DecisionRecord.{name}", getattr(self, name))
        if not isinstance(self.instrument_id, str) or not self.instrument_id:
            raise RefusedExecution("DecisionRecord.instrument_id is required")
        if not isinstance(self.detector_module_path, str) or not self.detector_module_path:
            raise RefusedExecution("DecisionRecord.detector_module_path is required")
        if (not isinstance(self.detector_callable_name, str) or
                not self.detector_callable_name.isidentifier()):
            raise RefusedExecution("DecisionRecord.detector_callable_name must be an identifier")
        _require_exact_int("DecisionRecord.evaluated_through_index", self.evaluated_through_index, minimum=0)
        _require_exact_int("DecisionRecord.stream_snapshot_count", self.stream_snapshot_count, minimum=1)
        if self.evaluated_through_index >= self.stream_snapshot_count:
            raise RefusedExecution("DecisionRecord evaluated prefix exceeds its stream snapshot")
        if not isinstance(self.evidence_indices, tuple) or not self.evidence_indices:
            raise RefusedExecution("DecisionRecord requires detector evidence indices")
        if tuple(sorted(set(self.evidence_indices))) != self.evidence_indices:
            raise RefusedExecution("DecisionRecord evidence indices must be unique and increasing")
        for value in self.evidence_indices:
            _require_exact_int("DecisionRecord.evidence_index", value, minimum=0)
        if not isinstance(self.evidence_commitments, tuple) or len(self.evidence_commitments) != len(self.evidence_indices):
            raise RefusedExecution("DecisionRecord evidence commitments must align with indices")
        for value in self.evidence_commitments:
            _require_hash("DecisionRecord.evidence_commitment", value)
        _require_exact_int("DecisionRecord.signal_index", self.signal_index, minimum=0)
        _require_exact_int("DecisionRecord.max_evidence_observation_unix_nanos",
                           self.max_evidence_observation_unix_nanos, minimum=0)
        _require_exact_int("DecisionRecord.decision_unix_nanos", self.decision_unix_nanos,
                           minimum=self.max_evidence_observation_unix_nanos)
        if self.signal_index != max(self.evidence_indices):
            raise RefusedExecution("signal_index must equal the maximum detector-evidence index")
        if self.signal_index > self.evaluated_through_index:
            raise RefusedExecution("signal index is beyond the detector's evaluated prefix")
        if self.max_evidence_coord is not None:
            if len(self.max_evidence_coord) != 4:
                raise RefusedExecution("max_evidence_coord must contain four integers")
            for value in self.max_evidence_coord:
                _require_exact_int("DecisionRecord.max_evidence_coord item", value, minimum=0)


def _decision_body(record: DecisionRecord) -> dict:
    return {
        "instrument_id": record.instrument_id,
        "seal_sha256": record.seal_sha256,
        "session_event_sha256": record.session_event_sha256,
        "activation_root_sha256": record.activation_root_sha256,
        "detector_sha256": record.detector_sha256,
        "detector_module_path": record.detector_module_path,
        "detector_callable_name": record.detector_callable_name,
        "spec_sha256": record.spec_sha256,
        "evaluated_through_index": record.evaluated_through_index,
        "evaluated_prefix_sha256": record.evaluated_prefix_sha256,
        "stream_snapshot_count": record.stream_snapshot_count,
        "stream_snapshot_sha256": record.stream_snapshot_sha256,
        "evidence_indices": list(record.evidence_indices),
        "evidence_commitments": list(record.evidence_commitments),
        "signal_index": record.signal_index,
        "max_evidence_observation_unix_nanos": record.max_evidence_observation_unix_nanos,
        "max_evidence_coord": list(record.max_evidence_coord) if record.max_evidence_coord else None,
        "decision_unix_nanos": record.decision_unix_nanos,
    }


def _load_sealed_detector(proof: SessionProof, module_path: str, callable_name: str,
                          detector_sha256: str):
    if not isinstance(module_path, str):
        raise RefusedExecution("detector module path must be a repo-relative string")
    pure = pathlib.PurePosixPath(module_path)
    if (pure.is_absolute() or ".." in pure.parts or pure.suffix != ".py" or
            not module_path.startswith("scripts/")):
        raise RefusedExecution("detector module path must be a safe repo-relative scripts/*.py path")
    expected = proof.dependency_sha256(module_path)
    if expected != detector_sha256:
        raise RefusedExecution("detector hash differs from the sealed dependency entry")
    root = pathlib.Path(__file__).resolve().parents[3]
    path = (root / pathlib.Path(*pure.parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RefusedExecution("detector module path escapes the repository") from exc
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RefusedExecution("detector module bytes drifted from the session seal")
    if not isinstance(callable_name, str) or not callable_name.isidentifier():
        raise RefusedExecution("detector callable name must be an identifier")
    module_name = ".".join(pure.with_suffix("").parts)
    module = importlib.import_module(module_name)
    detector = getattr(module, callable_name, None)
    if not callable(detector):
        raise RefusedExecution(f"sealed detector callable {callable_name!r} is absent")
    return detector


def _run_detector(detector, events: list[ObservedEvent], through_index: int,
                  warmup_count: int) -> tuple[int, ...]:
    output = detector(tuple(events[:through_index + 1]), warmup_count)
    if not isinstance(output, tuple) or not output:
        raise RefusedExecution("sealed detector must return a non-empty tuple of all evidence indices")
    if any(type(value) is not int for value in output):
        raise RefusedExecution("sealed detector evidence indices must be exact integers")
    if tuple(sorted(set(output))) != output:
        raise RefusedExecution("sealed detector evidence indices must be unique and increasing")
    if output[0] < warmup_count or output[-1] > through_index:
        raise RefusedExecution("sealed detector returned warm-up/future evidence")
    return output


def build_decision_record(events: list[ObservedEvent], ctx: ExecutionContext, *,
                          detector_module_path: str, detector_callable_name: str,
                          detector_sha256: str, spec_sha256: str) -> DecisionRecord:
    proof = _verify_context(ctx)
    warmup_count = _validate_session_stream(events, proof)
    _require_hash("detector_sha256", detector_sha256)
    _require_hash("spec_sha256", spec_sha256)
    if spec_sha256 != proof.frozen_json_canonical_sha256:
        raise RefusedExecution("decision spec hash does not match the sealed frozen JSON")
    decision_ns = time.time_ns()
    through = max((index for index, event in enumerate(events)
                   if event.observation_unix_nanos <= decision_ns), default=-1)
    if through < warmup_count:
        raise RefusedExecution("no post-warm-up observation was available at decision time")
    detector = _load_sealed_detector(
        proof, detector_module_path, detector_callable_name, detector_sha256)
    evidence_indices = _run_detector(detector, events, through, warmup_count)
    evidence = [events[index] for index in evidence_indices]
    if any(event.observation_unix_nanos <= proof.warmup_completed_unix_nanos for event in evidence):
        raise RefusedExecution("decision uses pre-warm-up-completion evidence")
    max_event = evidence[-1]
    max_coord = max_event.coord.as_tuple() if max_event.coord is not None else None
    if decision_ns < max_event.observation_unix_nanos:
        raise RefusedExecution("decision clock precedes the maximum evidence receive clock")
    prefix_sha = _hash_json([event_commitment(event) for event in events[:through + 1]])
    snapshot_sha = _hash_json([event_commitment(event) for event in events])
    body = {
        "instrument_id": proof.instrument_id,
        "seal_sha256": proof.seal_sha256,
        "session_event_sha256": proof.session_event_sha256,
        "activation_root_sha256": proof.activation_root_sha256,
        "detector_sha256": detector_sha256,
        "detector_module_path": detector_module_path,
        "detector_callable_name": detector_callable_name,
        "spec_sha256": spec_sha256,
        "evaluated_through_index": through,
        "evaluated_prefix_sha256": prefix_sha,
        "stream_snapshot_count": len(events),
        "stream_snapshot_sha256": snapshot_sha,
        "evidence_indices": list(evidence_indices),
        "evidence_commitments": [event_commitment(event) for event in evidence],
        "signal_index": evidence_indices[-1],
        "max_evidence_observation_unix_nanos": max_event.observation_unix_nanos,
        "max_evidence_coord": list(max_coord) if max_coord else None,
        "decision_unix_nanos": decision_ns,
    }
    return DecisionRecord(decision_id=_hash_json(body), **{
        **body,
        "evidence_indices": tuple(body["evidence_indices"]),
        "evidence_commitments": tuple(body["evidence_commitments"]),
        "max_evidence_coord": tuple(body["max_evidence_coord"]) if body["max_evidence_coord"] else None,
    })


def validate_decision_record(record: DecisionRecord, events: list[ObservedEvent], proof: SessionProof) -> None:
    if not isinstance(record, DecisionRecord):
        raise RefusedExecution("attempt requires a DecisionRecord")
    if record.decision_id != _hash_json(_decision_body(record)):
        raise RefusedExecution("DecisionRecord hash mismatch")
    if (record.instrument_id, record.seal_sha256, record.session_event_sha256,
            record.activation_root_sha256) != (
            proof.instrument_id, proof.seal_sha256, proof.session_event_sha256, proof.activation_root_sha256):
        raise RefusedExecution("DecisionRecord references a different manifest session")
    if record.spec_sha256 != proof.frozen_json_canonical_sha256:
        raise RefusedExecution("DecisionRecord spec differs from the sealed frozen JSON")
    if record.stream_snapshot_count > len(events):
        raise RefusedExecution("DecisionRecord stream snapshot is outside the current stream")
    snapshot_sha = _hash_json([
        event_commitment(event) for event in events[:record.stream_snapshot_count]])
    if snapshot_sha != record.stream_snapshot_sha256:
        raise RefusedExecution("DecisionRecord stream snapshot root does not match the stream")
    if record.evaluated_through_index >= record.stream_snapshot_count:
        raise RefusedExecution("DecisionRecord evaluated prefix is outside the stream")
    if events[record.evaluated_through_index].observation_unix_nanos > record.decision_unix_nanos:
        raise RefusedExecution("DecisionRecord evaluated a future receive-time observation")
    if (record.evaluated_through_index + 1 < record.stream_snapshot_count and
            events[record.evaluated_through_index + 1].observation_unix_nanos <= record.decision_unix_nanos):
        raise RefusedExecution("DecisionRecord omitted an observation already available at decision time")
    prefix_sha = _hash_json([
        event_commitment(event) for event in events[:record.evaluated_through_index + 1]])
    if prefix_sha != record.evaluated_prefix_sha256:
        raise RefusedExecution("DecisionRecord evaluated-prefix root does not match the stream")
    detector = _load_sealed_detector(
        proof, record.detector_module_path, record.detector_callable_name, record.detector_sha256)
    warmup_count = _validate_session_stream(events, proof)
    rerun = _run_detector(detector, events, record.evaluated_through_index, warmup_count)
    if rerun != record.evidence_indices:
        raise RefusedExecution("DecisionRecord is not the complete output of the sealed detector")
    if record.signal_index >= len(events):
        raise RefusedExecution("DecisionRecord signal index is outside the stream")
    actual = tuple(event_commitment(events[index]) for index in record.evidence_indices)
    if actual != record.evidence_commitments:
        raise RefusedExecution("DecisionRecord evidence does not match the stream")
    evidence = [events[index] for index in record.evidence_indices]
    max_event = evidence[-1]
    if max_event.observation_unix_nanos != record.max_evidence_observation_unix_nanos:
        raise RefusedExecution("DecisionRecord maximum receive clock is false")
    actual_coord = max_event.coord.as_tuple() if max_event.coord is not None else None
    if actual_coord != record.max_evidence_coord:
        raise RefusedExecution("DecisionRecord maximum canonical coordinate is false")
    if any(event.observation_unix_nanos <= proof.warmup_completed_unix_nanos for event in evidence):
        raise RefusedExecution("DecisionRecord contains pre-warm-up evidence")


@dataclass(frozen=True)
class ClockRecord:
    observation_unix_nanos: int
    decision_unix_nanos: int
    build_unix_nanos: None
    send_unix_nanos: None
    land_unix_nanos: None
    modeled_land_target_unix_nanos: int
    scenario_boundary_observation_unix_nanos: int | None

    def __post_init__(self) -> None:
        _require_exact_int("ClockRecord.observation_unix_nanos", self.observation_unix_nanos, minimum=0)
        _require_exact_int("ClockRecord.decision_unix_nanos", self.decision_unix_nanos,
                           minimum=self.observation_unix_nanos)
        _require_exact_int("ClockRecord.modeled_land_target_unix_nanos", self.modeled_land_target_unix_nanos,
                           minimum=self.decision_unix_nanos + 1)
        if any(value is not None for value in (self.build_unix_nanos, self.send_unix_nanos, self.land_unix_nanos)):
            raise RefusedExecution("unmeasured build/send/land clocks must remain null")
        if self.scenario_boundary_observation_unix_nanos is not None:
            _require_exact_int("ClockRecord.scenario_boundary_observation_unix_nanos",
                               self.scenario_boundary_observation_unix_nanos,
                               minimum=self.modeled_land_target_unix_nanos)


def _attempt_id(decision: DecisionRecord, intent: OrderIntent, mint: str, attempt_index: int) -> str:
    return _hash_json({
        "decision_id": decision.decision_id,
        "mint": mint,
        "kind": intent.kind.value,
        "amount": intent.amount,
        "min_out": intent.min_out,
        "attempt_index": attempt_index,
    })


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    attempt_index: int
    retry_of: str | None
    decision_id: str
    instrument_id: str
    seal_sha256: str
    activation_root_sha256: str
    mint: str
    intent: OrderIntent
    signal_index: int
    boundary_index: int | None
    outcome: Outcome
    out_amount: int | None
    out_unit: Unit | None
    fill_state: ReserveState | None
    cost_lamports: int | None
    cost_reason: str
    clocks: ClockRecord
    labels: tuple[str, ...]
    detail: str = ""

    def __post_init__(self) -> None:
        for label, value in (("attempt_id", self.attempt_id), ("decision_id", self.decision_id),
                             ("seal_sha256", self.seal_sha256),
                             ("activation_root_sha256", self.activation_root_sha256)):
            _require_hash(f"AttemptRecord.{label}", value)
        _require_exact_int("AttemptRecord.attempt_index", self.attempt_index, minimum=0)
        _require_exact_int("AttemptRecord.signal_index", self.signal_index, minimum=0)
        if self.boundary_index is not None:
            _require_exact_int("AttemptRecord.boundary_index", self.boundary_index,
                               minimum=self.signal_index + 1)
        if not isinstance(self.outcome, Outcome) or not isinstance(self.intent, OrderIntent):
            raise RefusedExecution("AttemptRecord carries an invalid outcome or intent")
        if not isinstance(self.clocks, ClockRecord):
            raise RefusedExecution("AttemptRecord.clocks must be ClockRecord")
        if self.cost_lamports is not None:
            _require_exact_int("AttemptRecord.cost_lamports", self.cost_lamports, minimum=0)


def attempt_order(events: list[ObservedEvent], decision: DecisionRecord, intent: OrderIntent,
                  latency: LatencyModel, ctx: ExecutionContext, price_fn, *,
                  attempt_index: int = 0, retry_of: str | None = None) -> AttemptRecord:
    """Evaluate one uncalibrated observed-path attempt without fabricating execution clocks."""
    proof = _verify_context(ctx)
    _validate_session_stream(events, proof)
    validate_decision_record(decision, events, proof)
    if not isinstance(intent, OrderIntent):
        raise RefusedExecution("intent must be an OrderIntent")
    if not isinstance(latency, LatencyModel):
        raise RefusedExecution("latency is required and must be a LatencyModel")
    _require_exact_int("attempt_index", attempt_index, minimum=0)
    signal = events[decision.signal_index]
    aid = _attempt_id(decision, intent, signal.mint, attempt_index)
    if attempt_index == 0:
        if retry_of is not None:
            raise RefusedExecution("attempt zero cannot reference a retry predecessor")
    else:
        expected = _attempt_id(decision, intent, signal.mint, attempt_index - 1)
        if retry_of != expected:
            raise RefusedExecution("retry_of must identify the immediately preceding distinct attempt")

    modeled_target = decision.decision_unix_nanos + latency.reaction_nanos
    boundary_index = next((index for index in range(decision.signal_index + 1, len(events))
                           if events[index].observation_unix_nanos >= modeled_target), None)
    labels = stream_labels(events)
    clocks = ClockRecord(
        observation_unix_nanos=decision.max_evidence_observation_unix_nanos,
        decision_unix_nanos=decision.decision_unix_nanos,
        build_unix_nanos=None,
        send_unix_nanos=None,
        land_unix_nanos=None,
        modeled_land_target_unix_nanos=modeled_target,
        scenario_boundary_observation_unix_nanos=(
            events[boundary_index].observation_unix_nanos if boundary_index is not None else None),
    )
    common = dict(
        attempt_id=aid, attempt_index=attempt_index, retry_of=retry_of,
        decision_id=decision.decision_id, instrument_id=proof.instrument_id,
        seal_sha256=proof.seal_sha256, activation_root_sha256=proof.activation_root_sha256,
        mint=signal.mint, intent=intent, signal_index=decision.signal_index,
        clocks=clocks, labels=labels,
    )
    if boundary_index is None:
        return AttemptRecord(
            **common, boundary_index=None, outcome=Outcome.RIGHT_CENSORED_NO_BOUNDARY,
            out_amount=None, out_unit=None, fill_state=None, cost_lamports=None,
            cost_reason="right_censored_send_and_landing_unobserved",
            detail="no observation brackets the modeled landing target; send/land/cost remain unknown")

    boundary = events[boundary_index]
    if boundary.coord is not None and decision.max_evidence_coord is not None:
        if boundary.coord.as_tuple() <= decision.max_evidence_coord:
            raise RefusedExecution("scenario boundary coordinate is not strictly after all decision evidence")
    elif boundary.observation_unix_nanos <= decision.max_evidence_observation_unix_nanos:
        raise RefusedExecution("scenario boundary receive time is not strictly after all decision evidence")
    fill_state = boundary.pre_state
    try:
        priced = price_fn(fill_state, intent)
    except PriceUnavailable as exc:
        return AttemptRecord(
            **common, boundary_index=boundary_index, outcome=Outcome.SCENARIO_UNAVAILABLE,
            out_amount=None, out_unit=None, fill_state=fill_state, cost_lamports=None,
            cost_reason="known_quote_unavailable_cost_unmeasured", detail=str(exc))
    if not isinstance(priced, PriceResult):
        raise RefusedExecution("price_fn must return PriceResult or raise PriceUnavailable")
    if priced.unit is not intent.expected_out_unit:
        raise RefusedExecution(
            f"price output unit {priced.unit.value} does not match {intent.kind.value} output unit "
            f"{intent.expected_out_unit.value}")
    if priced.out_amount == 0:
        return AttemptRecord(
            **common, boundary_index=boundary_index, outcome=Outcome.SCENARIO_UNAVAILABLE,
            out_amount=0, out_unit=priced.unit, fill_state=fill_state, cost_lamports=None,
            cost_reason="zero_output_is_unavailable_not_fill", detail="scenario quote returned zero output")
    if priced.out_amount < intent.min_out:
        return AttemptRecord(
            **common, boundary_index=boundary_index, outcome=Outcome.SCENARIO_FAILED_SLIPPAGE,
            out_amount=priced.out_amount, out_unit=priced.unit, fill_state=fill_state,
            cost_lamports=priced.wallet_cost_lamports,
            cost_reason="scenario_min_out_failure_current_attempt_only",
            detail=f"out {priced.out_amount} < min_out {intent.min_out}")
    return AttemptRecord(
        **common, boundary_index=boundary_index, outcome=Outcome.SCENARIO_FILLED,
        out_amount=priced.out_amount, out_unit=priced.unit, fill_state=fill_state,
        cost_lamports=priced.wallet_cost_lamports, cost_reason="scenario_current_attempt_processed",
        detail="uncalibrated observed-path scenario quote")


class RentStatus(str, Enum):
    NOT_CREATED = "NOT_CREATED"
    PREEXISTING = "PREEXISTING"
    LOCKED = "LOCKED"
    RECLAIMED_FULL_SELL_CLOSE = "RECLAIMED_FULL_SELL_CLOSE"
    CLOSE_FAILED = "CLOSE_FAILED"
    STRANDED_AT_HORIZON = "STRANDED_AT_HORIZON"


@dataclass(frozen=True)
class RentLedger:
    status: RentStatus
    rent_lamports: int
    close_cost_lamports: int | None
    settled_delta_lamports: int
    locked_lamports: int

    def __post_init__(self) -> None:
        if not isinstance(self.status, RentStatus):
            raise RefusedExecution("RentLedger.status must be RentStatus")
        _require_exact_int("RentLedger.rent_lamports", self.rent_lamports, minimum=0)
        if self.close_cost_lamports is not None:
            _require_exact_int("RentLedger.close_cost_lamports", self.close_cost_lamports, minimum=0)
        _require_exact_int("RentLedger.settled_delta_lamports", self.settled_delta_lamports)
        _require_exact_int("RentLedger.locked_lamports", self.locked_lamports, minimum=0)


def rent_outcome(*, ata_preexisting: bool, ata_created: bool, token_balance_after: int,
                 close_attempted: bool, close_succeeded: bool, reached_horizon: bool,
                 rent_lamports: int, close_cost_lamports: int | None) -> RentLedger:
    for label, value in (("ata_preexisting", ata_preexisting), ("ata_created", ata_created),
                         ("close_attempted", close_attempted), ("close_succeeded", close_succeeded),
                         ("reached_horizon", reached_horizon)):
        if type(value) is not bool:
            raise RefusedExecution(f"{label} must be bool")
    _require_exact_int("token_balance_after", token_balance_after, minimum=0)
    _require_exact_int("rent_lamports", rent_lamports, minimum=0)
    if close_cost_lamports is not None:
        _require_exact_int("close_cost_lamports", close_cost_lamports, minimum=0)
    if ata_preexisting and ata_created:
        raise RefusedExecution("an ATA cannot be both preexisting and newly created")
    if close_succeeded and not close_attempted:
        raise RefusedExecution("a close cannot succeed when it was not attempted")
    if close_attempted and token_balance_after != 0:
        raise RefusedExecution("an ATA close attempt with a non-zero token balance is inconsistent")
    if not close_attempted and close_cost_lamports is not None:
        raise RefusedExecution("close cost supplied without a close attempt")
    if close_succeeded and close_cost_lamports is None:
        raise RefusedExecution("a proven successful close requires its actual transaction cost")
    if not ata_preexisting and not ata_created:
        if token_balance_after != 0 or close_attempted or rent_lamports != 0:
            raise RefusedExecution("NOT_CREATED ATA cannot carry balance, rent, or close activity")
        return RentLedger(RentStatus.NOT_CREATED, 0, None, 0, 0)
    if ata_preexisting:
        if close_attempted or close_cost_lamports is not None:
            raise RefusedExecution("position PnL may not claim close/reclaim of a preexisting ATA")
        return RentLedger(RentStatus.PREEXISTING, 0, None, 0, 0)
    if rent_lamports <= 0:
        raise RefusedExecution("a newly created ATA requires positive measured rent")
    if token_balance_after > 0:
        status = RentStatus.STRANDED_AT_HORIZON if reached_horizon else RentStatus.LOCKED
        return RentLedger(status, rent_lamports, None, 0, rent_lamports)
    if not close_attempted:
        status = RentStatus.STRANDED_AT_HORIZON if reached_horizon else RentStatus.LOCKED
        return RentLedger(status, rent_lamports, None, 0, rent_lamports)
    if close_succeeded:
        assert close_cost_lamports is not None
        return RentLedger(RentStatus.RECLAIMED_FULL_SELL_CLOSE, rent_lamports,
                          close_cost_lamports, rent_lamports - close_cost_lamports, 0)
    return RentLedger(RentStatus.CLOSE_FAILED, rent_lamports, close_cost_lamports, 0, rent_lamports)


@dataclass(frozen=True)
class SolUsdObservation:
    value_str: str
    observed_unix_nanos: int
    source: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.value_str, str) or not self.value_str.strip():
            raise RefusedExecution("SOL/USD value must be a non-empty decimal string")
        _require_exact_int("SolUsdObservation.observed_unix_nanos", self.observed_unix_nanos, minimum=0)
        if not isinstance(self.source, str) or not self.source.strip():
            raise RefusedExecution("SOL/USD source is required")
        _require_hash("SolUsdObservation.evidence_sha256", self.evidence_sha256)


def q_lamports_for_usd(target_usd_str: str, sol_usd: SolUsdObservation, *,
                       decision_unix_nanos: int, max_staleness_nanos: int) -> int:
    if not isinstance(target_usd_str, str) or not target_usd_str.strip():
        raise RefusedExecution("target USD must be supplied as a decimal string")
    if not isinstance(sol_usd, SolUsdObservation):
        raise RefusedExecution("a typed point-in-time SOL/USD observation is required")
    _require_exact_int("decision_unix_nanos", decision_unix_nanos, minimum=0)
    _require_exact_int("max_staleness_nanos", max_staleness_nanos, minimum=0)
    if sol_usd.observed_unix_nanos > decision_unix_nanos:
        raise RefusedExecution("SOL/USD observation is after the decision")
    if decision_unix_nanos - sol_usd.observed_unix_nanos > max_staleness_nanos:
        raise RefusedExecution("SOL/USD observation exceeds the declared freshness bound")
    try:
        target = Decimal(target_usd_str)
        rate = Decimal(sol_usd.value_str)
    except (InvalidOperation, ValueError) as exc:
        raise RefusedExecution(f"invalid decimal sizing input: {exc}") from exc
    if not target.is_finite() or not rate.is_finite() or target <= 0 or rate <= 0:
        raise RefusedExecution("target USD and SOL/USD rate must be finite and positive")
    lamports = int(((target / rate) * Decimal(_LAMPORTS_PER_SOL)).to_integral_value(rounding=ROUND_DOWN))
    if lamports <= 0:
        raise RefusedExecution("target size rounds below one lamport")
    return lamports
