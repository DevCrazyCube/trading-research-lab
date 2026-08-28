#!/usr/bin/env python3
"""AFTERSHOCK seal, session, warm-up, and activation-root authority (handoff 424).

The seal is written before observation and must be externally anchored in git. Each process activation is
followed by a fully post-activation warm-up record. A separate git-anchored activation-root file then pins
that session's hash-chain root. Until both anchors are present and clean, ``load_session_proof`` refuses.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import time

from . import Refused

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_INSTRUMENT = re.compile(r"^[A-Z0-9_]+$")
_SESSION_REASONS = {"first_activation", "restart_resume"}

# Exact transitive measurement dependencies known today. Future experiment modules are declared separately
# in the frozen JSON and the declared full list must equal BASE union experiment: no optional omissions.
BASE_DEPENDENCY_PATHS = (
    "research/pump_amm_idl_9c82f61.json",
    "research/pump_idl_9c82f61.json",
    "scripts/b10a_simulator_kernel.py",
    "scripts/b10b_position_path.py",
    "scripts/b9d_transaction_bodies.py",
    "scripts/b9i_quote_reproduction.py",
    "scripts/rpc_http_identity.py",
    "scripts/trading_bot/aftershock/__init__.py",
    "scripts/trading_bot/aftershock/ecr.py",
    "scripts/trading_bot/aftershock/execution.py",
    "scripts/trading_bot/aftershock/feasibility.py",
    "scripts/trading_bot/aftershock/frozen.py",
    "scripts/trading_bot/aftershock/manifest.py",
    "scripts/trading_bot/memebot/__init__.py",
    "scripts/trading_bot/memebot/frozen.py",
)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())


def _require_hash(label: str, value: object) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise Refused(f"{label} must be lowercase 64-hex, got {value!r}")
    return value


def _require_int(label: str, value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise Refused(f"{label} must be an exact integer >= {minimum}, got {value!r}")
    return value


def _require_instrument(instrument: str) -> str:
    if not isinstance(instrument, str) or _INSTRUMENT.fullmatch(instrument) is None:
        raise Refused(f"invalid instrument id {instrument!r}")
    return instrument


def _canonical_json_sha(path: pathlib.Path) -> str:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"cannot parse canonical JSON {path.name}: {exc}") from exc
    return _hash_json(value)


def _repo_path(relative: str) -> pathlib.Path:
    if not isinstance(relative, str) or not relative or pathlib.PurePosixPath(relative).is_absolute():
        raise Refused(f"dependency path must be a non-empty repo-relative POSIX path: {relative!r}")
    pure = pathlib.PurePosixPath(relative)
    if ".." in pure.parts:
        raise Refused(f"dependency path escapes the repository: {relative!r}")
    resolved = (ROOT / pathlib.Path(*pure.parts)).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise Refused(f"dependency path escapes the repository: {relative!r}") from exc
    if not resolved.is_file():
        raise Refused(f"sealed dependency is missing/not a file: {relative}")
    return resolved


def _git_committed(path: pathlib.Path) -> bool:
    """True only when this exact working-tree file is tracked and byte-clean against HEAD."""
    try:
        relative = str(path.resolve().relative_to(ROOT))
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative], cwd=ROOT,
            capture_output=True, timeout=10, check=False)
        if tracked.returncode != 0:
            return False
        clean = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", relative], cwd=ROOT,
            capture_output=True, timeout=10, check=False)
        return clean.returncode == 0 and path.is_file()
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def _seal_path(instrument: str) -> pathlib.Path:
    return RESEARCH / f"{_require_instrument(instrument)}_SEAL.json"


def _activation_path(instrument: str) -> pathlib.Path:
    return RESEARCH / f"{_require_instrument(instrument)}_ACTIVATION.jsonl"


def _activation_anchor_path(instrument: str, root_sha256: str) -> pathlib.Path:
    _require_hash("activation root", root_sha256)
    return RESEARCH / f"{_require_instrument(instrument)}_ACTIVATION_ANCHOR_{root_sha256}.json"


def _frozen_paths(instrument: str) -> tuple[pathlib.Path, pathlib.Path]:
    instrument = _require_instrument(instrument)
    return (RESEARCH / f"{instrument}_PREREGISTRATION.md", RESEARCH / f"{instrument}_FROZEN.json")


def _load_frozen(instrument: str) -> tuple[pathlib.Path, pathlib.Path, dict, dict]:
    prereg, frozen_path = _frozen_paths(instrument)
    if not prereg.is_file() or not frozen_path.is_file():
        raise Refused(f"cannot seal {instrument}: preregistration or frozen JSON missing")
    try:
        frozen = json.loads(frozen_path.read_text())
    except json.JSONDecodeError as exc:
        raise Refused(f"{frozen_path.name} is invalid JSON: {exc}") from exc
    if not isinstance(frozen, dict) or frozen.get("instrument_id") != instrument:
        raise Refused(f"{frozen_path.name} does not declare instrument_id {instrument!r}")
    prereg_sha = _sha_bytes(prereg.read_bytes())
    if frozen.get("preregistration_sha256") != prereg_sha:
        raise Refused("frozen JSON preregistration hash does not match the markdown bytes")
    config = frozen.get("execution_realism")
    if not isinstance(config, dict):
        raise Refused("frozen JSON lacks an execution_realism object")
    _require_int("warmup_min_events", config.get("warmup_min_events"), minimum=1)
    _require_int("warmup_min_span_nanos", config.get("warmup_min_span_nanos"), minimum=0)
    if config.get("warmup_scope", "mint_prefix") not in {"mint_prefix", "feed_global"}:
        raise Refused("execution_realism.warmup_scope must be mint_prefix or feed_global")
    declared = config.get("dependency_paths")
    experiment = config.get("experiment_dependency_paths")
    if not isinstance(declared, list) or not declared or any(not isinstance(v, str) for v in declared):
        raise Refused("execution_realism.dependency_paths must be a non-empty string list")
    if not isinstance(experiment, list) or not experiment or any(not isinstance(v, str) for v in experiment):
        raise Refused("execution_realism.experiment_dependency_paths must name the future detector/resolver/spec modules")
    if len(set(declared)) != len(declared) or declared != sorted(declared):
        raise Refused("dependency_paths must be unique and lexicographically sorted")
    if len(set(experiment)) != len(experiment) or experiment != sorted(experiment):
        raise Refused("experiment_dependency_paths must be unique and lexicographically sorted")
    if set(experiment) & set(BASE_DEPENDENCY_PATHS):
        raise Refused("experiment dependencies must be separate from the base execution closure")
    expected = sorted(set(BASE_DEPENDENCY_PATHS) | set(experiment))
    if declared != expected:
        missing = sorted(set(expected) - set(declared))
        extra = sorted(set(declared) - set(expected))
        raise Refused(f"dependency closure mismatch; missing={missing}, extra={extra}")
    for relative in declared:
        _repo_path(relative)
    return prereg, frozen_path, frozen, config


def compute_seal(instrument: str) -> dict:
    prereg, frozen_path, _frozen, config = _load_frozen(instrument)
    dependencies = {
        relative: _sha_bytes(_repo_path(relative).read_bytes())
        for relative in config["dependency_paths"]
    }
    body = {
        "schema_version": 3,
        "instrument_id": instrument,
        "prereg_sha256": _sha_bytes(prereg.read_bytes()),
        "frozen_json_canonical_sha256": _canonical_json_sha(frozen_path),
        "dependency_sha256": dependencies,
    }
    return {**body, "seal_sha256": _hash_json(body)}


def write_seal(instrument: str) -> dict:
    seal = compute_seal(instrument)
    path = _seal_path(instrument)
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise Refused(f"existing seal is malformed: {exc}") from exc
        if existing != seal:
            raise Refused(f"{path.name} already contains a different final seal")
        return existing
    path.write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n")
    return seal


def verify_seal(instrument: str) -> dict:
    path = _seal_path(instrument)
    if not path.is_file():
        raise Refused(f"{instrument} has no seal")
    try:
        written = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise Refused(f"{path.name} is malformed: {exc}") from exc
    expected = compute_seal(instrument)
    if written != expected:
        raise Refused(f"{instrument} seal or a sealed dependency drifted")
    return written


def seal_anchor(instrument: str) -> str:
    try:
        verify_seal(instrument)
    except Refused:
        return "UNANCHORED"
    return "ANCHORED" if _git_committed(_seal_path(instrument)) else "UNANCHORED"


def _require_seal_anchor(instrument: str) -> dict:
    seal = verify_seal(instrument)
    if not _git_committed(_seal_path(instrument)):
        raise Refused("seal is UNANCHORED; activation and evidence are prohibited until owner-gated commit")
    return seal


def _coord(value: object, *, nullable: bool) -> list[int] | None:
    if value is None and nullable:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise Refused("canonical coordinate must be four exact non-negative integers")
    result = [_require_int("canonical coordinate item", item) for item in value]
    return result


def _event_sha(body: dict) -> str:
    return _hash_json(body)


def _append_event(path: pathlib.Path, body: dict) -> dict:
    event = {**body, "event_sha256": _event_sha(body)}
    with path.open("a") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


def _read_activation_verified(instrument: str) -> list[dict]:
    path = _activation_path(instrument)
    if not path.is_file() or path.stat().st_size == 0:
        raise Refused(f"{instrument} has no activation chain")
    seal = verify_seal(instrument)
    _prereg, _frozen_path, _frozen, frozen_config = _load_frozen(instrument)
    try:
        lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise Refused(f"activation chain contains invalid JSON: {exc}") from exc
    previous_sha = None
    previous_time = -1
    pending_session = None
    completed_session = None
    for index, event in enumerate(lines):
        if not isinstance(event, dict):
            raise Refused(f"activation event {index} is not an object")
        stored = _require_hash(f"activation event {index} hash", event.get("event_sha256"))
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        if stored != _event_sha(body):
            raise Refused(f"activation event {index} hash mismatch")
        if event.get("schema_version") != 3 or event.get("instrument_id") != instrument:
            raise Refused(f"activation event {index} schema/instrument mismatch")
        if event.get("seal_sha256") != seal["seal_sha256"]:
            raise Refused(f"activation event {index} references another seal")
        if event.get("prev_event_sha256") != previous_sha:
            raise Refused(f"activation event {index} breaks the hash chain")
        recorded = _require_int(f"activation event {index} recorded_unix_nanos",
                                event.get("recorded_unix_nanos"))
        if recorded <= previous_time:
            raise Refused(f"activation event {index} has a non-monotonic internal clock")
        kind = event.get("event_kind")
        if kind == "session_activation":
            required = {
                "schema_version", "event_kind", "instrument_id", "session_reason",
                "recorded_unix_nanos", "resume_after_coord", "seal_sha256",
                "prev_event_sha256", "event_sha256",
            }
            if set(event) != required:
                raise Refused(f"session activation {index} fields differ from the closed schema")
            reason = event.get("session_reason")
            if reason not in _SESSION_REASONS:
                raise Refused(f"activation event {index} has unknown reason")
            if pending_session is not None:
                raise Refused("a new session began before prior post-activation warm-up completed")
            if index == 0:
                if reason != "first_activation" or event.get("resume_after_coord") is not None:
                    raise Refused("first event must be first_activation with no resume coordinate")
            else:
                if reason != "restart_resume" or completed_session is None:
                    raise Refused("later session must be restart_resume after a completed session")
                resume = _coord(event.get("resume_after_coord"), nullable=False)
                previous_max = completed_session.get("warmup_max_coord")
                if previous_max is None or resume < previous_max:
                    raise Refused("restart coordinate is absent or behind the prior completed warm-up")
            pending_session = event
        elif kind == "warmup_complete":
            required = {
                "schema_version", "event_kind", "instrument_id", "recorded_unix_nanos",
                "session_event_sha256", "warmup_event_commitments", "warmup_evidence_root_sha256",
                "warmup_event_count", "warmup_min_events", "warmup_min_span_nanos",
                "warmup_min_observation_unix_nanos", "warmup_max_observation_unix_nanos",
                "warmup_max_coord", "warmup_scope", "seal_sha256",
                "prev_event_sha256", "event_sha256",
            }
            if set(event) != required:
                raise Refused(f"warm-up event {index} fields differ from the closed schema")
            if pending_session is None or event.get("session_event_sha256") != pending_session["event_sha256"]:
                raise Refused("warm-up does not close the pending session")
            commitments = event.get("warmup_event_commitments")
            if not isinstance(commitments, list) or not commitments:
                raise Refused("warm-up evidence commitments are missing")
            for commitment in commitments:
                _require_hash("warm-up event commitment", commitment)
            if event.get("warmup_event_count") != len(commitments):
                raise Refused("warm-up event count does not reconcile")
            if event.get("warmup_evidence_root_sha256") != _hash_json(commitments):
                raise Refused("warm-up evidence root does not reconcile")
            min_events = _require_int("warmup_min_events", event.get("warmup_min_events"), minimum=1)
            min_span = _require_int("warmup_min_span_nanos", event.get("warmup_min_span_nanos"))
            if (min_events != frozen_config["warmup_min_events"] or
                    min_span != frozen_config["warmup_min_span_nanos"]):
                raise Refused("warm-up event policy differs from the sealed frozen policy")
            if event.get("warmup_scope") != frozen_config.get("warmup_scope", "mint_prefix"):
                raise Refused("warm-up scope differs from the sealed frozen policy")
            if len(commitments) < min_events:
                raise Refused("warm-up event count is below the sealed minimum")
            min_obs = _require_int("warmup_min_observation_unix_nanos",
                                   event.get("warmup_min_observation_unix_nanos"))
            max_obs = _require_int("warmup_max_observation_unix_nanos",
                                   event.get("warmup_max_observation_unix_nanos"))
            if max_obs - min_obs < min_span:
                raise Refused("warm-up observation span is below the sealed minimum")
            if max_obs > recorded:
                raise Refused("warm-up completion predates its evidence")
            _coord(event.get("warmup_max_coord"), nullable=True)
            completed_session = event
            pending_session = None
        else:
            raise Refused(f"activation event {index} has unknown event_kind {kind!r}")
        previous_sha = stored
        previous_time = recorded
    if pending_session is not None:
        return lines
    if completed_session is None:
        raise Refused("activation chain has no completed post-activation warm-up")
    return lines


def append_activation(instrument: str, *, session_reason: str, last_coord: list[int] | None) -> dict:
    seal = _require_seal_anchor(instrument)
    if session_reason not in _SESSION_REASONS:
        raise Refused(f"unknown session_reason {session_reason!r}")
    path = _activation_path(instrument)
    existing = _read_activation_verified(instrument) if path.exists() and path.stat().st_size else []
    if session_reason == "first_activation":
        if existing or path.exists():
            raise Refused("first_activation is set-once; activation path already exists")
        if last_coord is not None:
            raise Refused("first_activation cannot carry a resume coordinate")
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
        except FileExistsError as exc:
            raise Refused("first_activation lost the exclusive-create race") from exc
    else:
        if not existing or existing[-1].get("event_kind") != "warmup_complete":
            raise Refused("restart_resume requires a prior completed warm-up")
        last_coord = _coord(last_coord, nullable=False)
        previous_max = existing[-1].get("warmup_max_coord")
        if previous_max is None or last_coord < previous_max:
            raise Refused("restart_resume lacks a monotonic persisted canonical coordinate")
    now = time.time_ns()
    if existing and now <= existing[-1]["recorded_unix_nanos"]:
        raise Refused("session activation clock is not strictly monotonic")
    body = {
        "schema_version": 3,
        "event_kind": "session_activation",
        "instrument_id": instrument,
        "session_reason": session_reason,
        "recorded_unix_nanos": now,
        "resume_after_coord": list(last_coord) if last_coord is not None else None,
        "seal_sha256": seal["seal_sha256"],
        "prev_event_sha256": existing[-1]["event_sha256"] if existing else None,
    }
    return _append_event(path, body)


def append_warmup_complete(instrument: str, events: list) -> dict:
    seal = _require_seal_anchor(instrument)
    chain = _read_activation_verified(instrument)
    session = chain[-1]
    if session.get("event_kind") != "session_activation":
        raise Refused("warm-up can only close the latest uncompleted session activation")
    from .execution import ObservedEvent, event_commitment, validate_stream
    _prereg, _frozen_path, _frozen, config = _load_frozen(instrument)
    scope = config.get("warmup_scope", "mint_prefix")
    if scope == "mint_prefix":
        validate_stream(events)
    else:
        if not isinstance(events, list) or not events or any(not isinstance(event, ObservedEvent) for event in events):
            raise Refused("feed-global warm-up requires observed events")
        if len({event.source for event in events}) != 1:
            raise Refused("feed-global warm-up cannot mix observation sources")
        if any(right.observation_unix_nanos <= left.observation_unix_nanos
               for left, right in zip(events, events[1:])):
            raise Refused("feed-global warm-up receive clocks must be strictly increasing")
    minimum_events = config["warmup_min_events"]
    minimum_span = config["warmup_min_span_nanos"]
    if len(events) < minimum_events:
        raise Refused(f"post-activation warm-up has {len(events)} events, needs {minimum_events}")
    if events[0].observation_unix_nanos <= session["recorded_unix_nanos"]:
        raise Refused("warm-up contains pre-activation evidence")
    span = events[-1].observation_unix_nanos - events[0].observation_unix_nanos
    if span < minimum_span:
        raise Refused(f"post-activation warm-up spans {span}ns, needs {minimum_span}ns")
    resume = session.get("resume_after_coord")
    if resume is not None:
        for event in events:
            if event.coord is None or list(event.coord.as_tuple()) <= resume:
                raise Refused("restart warm-up contains pre-resume/uncoordinated evidence")
    now = time.time_ns()
    if now <= session["recorded_unix_nanos"] or now < events[-1].observation_unix_nanos:
        raise Refused("warm-up completion clock precedes activation or evidence")
    commitments = [event_commitment(event) for event in events]
    max_coord = list(events[-1].coord.as_tuple()) if events[-1].coord is not None else None
    body = {
        "schema_version": 3,
        "event_kind": "warmup_complete",
        "instrument_id": instrument,
        "recorded_unix_nanos": now,
        "session_event_sha256": session["event_sha256"],
        "warmup_event_commitments": commitments,
        "warmup_evidence_root_sha256": _hash_json(commitments),
        "warmup_event_count": len(commitments),
        "warmup_min_events": minimum_events,
        "warmup_min_span_nanos": minimum_span,
        "warmup_min_observation_unix_nanos": events[0].observation_unix_nanos,
        "warmup_max_observation_unix_nanos": events[-1].observation_unix_nanos,
        "warmup_max_coord": max_coord,
        "warmup_scope": scope,
        "seal_sha256": seal["seal_sha256"],
        "prev_event_sha256": session["event_sha256"],
    }
    return _append_event(_activation_path(instrument), body)


def write_activation_anchor(instrument: str) -> dict:
    seal = _require_seal_anchor(instrument)
    chain = _read_activation_verified(instrument)
    root = chain[-1]
    if root.get("event_kind") != "warmup_complete":
        raise Refused("cannot anchor a session before post-activation warm-up completes")
    body = {
        "schema_version": 1,
        "instrument_id": instrument,
        "seal_sha256": seal["seal_sha256"],
        "session_event_sha256": root["session_event_sha256"],
        "activation_root_sha256": root["event_sha256"],
        "activation_chain_prefix_sha256": _hash_json([event["event_sha256"] for event in chain]),
    }
    anchor = {**body, "anchor_sha256": _hash_json(body)}
    path = _activation_anchor_path(instrument, root["event_sha256"])
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise Refused(f"existing activation anchor is malformed: {exc}") from exc
        if existing != anchor:
            raise Refused("activation anchor path already contains different bytes")
        return existing
    path.write_text(json.dumps(anchor, indent=2, sort_keys=True) + "\n")
    return anchor


def _known_anchor_paths(instrument: str) -> set[pathlib.Path]:
    prefix = f"{instrument}_ACTIVATION_ANCHOR_"
    paths = set(RESEARCH.glob(prefix + "*.json"))
    try:
        pattern = str((RESEARCH / (prefix + "*.json")).relative_to(ROOT))
        result = subprocess.run(["git", "ls-files", "--", pattern], cwd=ROOT,
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode == 0:
            paths.update(ROOT / line for line in result.stdout.splitlines() if line.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return paths


def _verified_anchors(instrument: str, chain: list[dict], seal: dict) -> list[dict]:
    paths = _known_anchor_paths(instrument)
    if not paths:
        raise Refused("activation root is UNANCHORED; evidence prohibited")
    by_sha = {event["event_sha256"]: (index, event) for index, event in enumerate(chain)}
    verified = []
    for path in sorted(paths):
        if not path.is_file() or not _git_committed(path):
            raise Refused(f"activation anchor {path.name} is missing, dirty, or uncommitted")
        try:
            anchor = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise Refused(f"activation anchor {path.name} is malformed: {exc}") from exc
        body = {key: value for key, value in anchor.items() if key != "anchor_sha256"}
        if anchor.get("anchor_sha256") != _hash_json(body):
            raise Refused(f"activation anchor {path.name} has an invalid internal hash")
        if anchor.get("instrument_id") != instrument or anchor.get("seal_sha256") != seal["seal_sha256"]:
            raise Refused(f"activation anchor {path.name} references another instrument/seal")
        root_sha = anchor.get("activation_root_sha256")
        if root_sha not in by_sha or by_sha[root_sha][1].get("event_kind") != "warmup_complete":
            raise Refused(f"activation anchor {path.name} root is absent from the verified chain")
        index, root = by_sha[root_sha]
        if anchor.get("session_event_sha256") != root.get("session_event_sha256"):
            raise Refused(f"activation anchor {path.name} session reference is false")
        expected_prefix = _hash_json([event["event_sha256"] for event in chain[:index + 1]])
        if anchor.get("activation_chain_prefix_sha256") != expected_prefix:
            raise Refused(f"activation anchor {path.name} chain prefix does not reconcile")
        verified.append(anchor)
    return verified


def load_session_proof(instrument: str):
    seal = _require_seal_anchor(instrument)
    chain = _read_activation_verified(instrument)
    latest = chain[-1]
    if latest.get("event_kind") != "warmup_complete":
        raise Refused("latest session has no completed post-activation warm-up")
    anchors = _verified_anchors(instrument, chain, seal)
    matching = [anchor for anchor in anchors if anchor["activation_root_sha256"] == latest["event_sha256"]]
    if len(matching) != 1:
        raise Refused("latest activation root is not anchored exactly once")
    session = next((event for event in chain
                    if event["event_sha256"] == latest["session_event_sha256"]), None)
    if session is None or session.get("event_kind") != "session_activation":
        raise Refused("warm-up references a missing session activation")
    from .execution import SessionProof
    _prereg, _frozen_path, _frozen, config = _load_frozen(instrument)
    anchor = matching[0]
    return SessionProof(
        instrument_id=instrument,
        seal_sha256=seal["seal_sha256"],
        frozen_json_canonical_sha256=seal["frozen_json_canonical_sha256"],
        sealed_dependency_items=tuple(sorted(seal["dependency_sha256"].items())),
        session_event_sha256=session["event_sha256"],
        activation_root_sha256=latest["event_sha256"],
        activation_anchor_sha256=anchor["anchor_sha256"],
        activation_unix_nanos=session["recorded_unix_nanos"],
        resume_after_coord=(tuple(session["resume_after_coord"])
                            if session["resume_after_coord"] is not None else None),
        warmup_completed_unix_nanos=latest["recorded_unix_nanos"],
        warmup_event_commitments=tuple(latest["warmup_event_commitments"]),
        warmup_max_observation_unix_nanos=latest["warmup_max_observation_unix_nanos"],
        warmup_max_coord=(tuple(latest["warmup_max_coord"])
                          if latest["warmup_max_coord"] is not None else None),
        warmup_scope=config.get("warmup_scope", "mint_prefix"),
    )


def verify_session_proof(proof) -> None:
    from .execution import SessionProof
    if not isinstance(proof, SessionProof):
        raise Refused("session proof has the wrong type")
    expected = load_session_proof(proof.instrument_id)
    if proof != expected:
        raise Refused("session proof differs from the latest anchored manifest-derived proof")


def first_activation_nanos(instrument: str) -> int:
    """Compatibility read, now requiring a fully anchored current session rather than a bare hash chain."""
    chain = _read_activation_verified(instrument)
    first = chain[0]
    if first.get("event_kind") != "session_activation" or first.get("session_reason") != "first_activation":
        raise Refused("activation chain does not begin with first_activation")
    load_session_proof(instrument)
    return first["recorded_unix_nanos"]
