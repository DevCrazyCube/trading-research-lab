#!/usr/bin/env python3
"""Read-only, fail-closed PAC performance adapter for the local dashboard.

This module never runs the strategy and never repairs/mutates its files.  It only publishes a
performance curve when the scenario ledger contains a fully costed, internally reconciled schema.
Legacy/gross-only rows are surfaced as an integrity refusal instead of being charted as profit.
"""
from __future__ import annotations

from fractions import Fraction
import copy
import hashlib
import json
import pathlib
import subprocess
import threading
import time
from types import SimpleNamespace

from . import (
    pac_policy,
    pac_runner,
    pac_status,
    pac_v2_detector,
    pac_v2_runner,
    pac_v2_status,
    pac_v21_manifest,
    pac_v21_detector,
    pac_v21_runner,
    pac_v22_feed,
    pac_v22_manifest,
    pac_v22_runner,
    pac_v23_manifest,
    pac_v23_runner,
    pac_v24_manifest,
    pac_v24_runner,
    pac_v25_manifest,
    pac_v25_runner,
    pac_v26_manifest,
    pac_v26_runner,
    solusd_recorder,
)
from .execution import RefusedExecution


ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
STATE_PATH = RESEARCH / "AFTERSHOCK_PAC_V1_RUNNER_STATE.json"
LEDGER_PATH = RESEARCH / "AFTERSHOCK_PAC_V1_SCENARIO_LEDGER.jsonl"
LEDGER_SCHEMA = 2
STATE_SCHEMA = 3
_STATUS_TTL_SECONDS = 60.0
_STATUS_CACHE: dict = {"at": 0.0, "value": None}
_STATUS_LOCK = threading.Lock()
_V21_AUTHORITY_LOCK = threading.Lock()
_V21_SUCCESSOR_CACHE: dict = {"key": None, "value": None}
_V21_PROOF_CACHE: dict = {"key": None, "value": None}
_V2_CONTROL_CACHE: dict = {"at": 0.0, "value": None}
_V2_CONTROL_TTL_SECONDS = 30.0
_V22_DIAGNOSTIC_LOCK = threading.Lock()
_V22_DIAGNOSTIC: dict = {
    "initialized": False,
    "cursor": None,
    "buffers": {},
    "last_error": None,
}
_V22_PROOF_CACHE: dict = {"key": None, "value": None}
_V22_VIEW_LOCK = threading.RLock()
_V23_PROOF_CACHE: dict = {"key": None, "value": None}
_V23_VIEW_LOCK = threading.RLock()
_V24_PROOF_CACHE: dict = {"key": None, "value": None}
_V24_VIEW_LOCK = threading.RLock()
_V25_PROOF_CACHE: dict = {"key": None, "value": None}
_V25_VIEW_LOCK = threading.RLock()
_V26_PROOF_CACHE: dict = {"key": None, "value": None}
_V26_VIEW_LOCK = threading.RLock()
V26_RETIREMENT = RESEARCH / "AFTERSHOCK_PAC_V26_RETIREMENT.json"


def _exact_int(label: str, value, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise RefusedExecution(f"{label} must be an exact integer"
                               + (f" >= {minimum}" if minimum is not None else ""))
    return value


def _text(label: str, value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RefusedExecution(f"{label} must be a non-empty string")
    return value


def _decimal(value: Fraction, places: int = 6) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    scale = 10 ** places
    scaled = (value.numerator * scale) // value.denominator
    whole, frac = divmod(scaled, scale)
    return f"{sign}{whole}.{frac:0{places}d}"


def _read_state(path: pathlib.Path) -> dict:
    if not path.exists():
        return pac_runner._new_state()
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution(f"PAC runner state is unreadable: {type(exc).__name__}") from exc
    pac_runner._validate_state(state)
    if state["pending_ledger_rows"]:
        raise RefusedExecution("PAC runner has an unreconciled pending ledger transaction")
    return state


def _read_ledger(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise RefusedExecution(f"PAC ledger is unreadable: {type(exc).__name__}") from exc
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RefusedExecution(f"PAC ledger line {lineno} is invalid JSON") from exc
        if not isinstance(row, dict) or row.get("schema_version") != LEDGER_SCHEMA:
            raise RefusedExecution(f"PAC ledger line {lineno} is not fully-costed schema 2")
        pac_runner._validate_row(row)
        rows.append(row)
    return rows


def _latest_solusd_status() -> dict:
    """Dashboard-only O(last-record) freshness check. Sizing still uses the sealed recorder consumer."""
    path = solusd_recorder.OUTPUT
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            if size <= 0:
                raise RefusedExecution("SOL/USD recorder is empty")
            window = min(size, 65_536)
            handle.seek(size - window)
            lines = [line for line in handle.read().splitlines() if line.strip()]
        if not lines:
            raise RefusedExecution("SOL/USD recorder has no complete row")
        row = json.loads(lines[-1])
        raw = row.get("raw_response_utf8")
        if not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != row.get("raw_response_sha256"):
            raise RefusedExecution("latest SOL/USD raw response hash does not reconcile")
        payload = json.loads(raw)
        received = _exact_int("SOL/USD received_unix_nanos", row.get("received_unix_nanos"), minimum=0)
        now = time.time_ns()
        if received > now or now - received > solusd_recorder.MAX_LOCAL_AGE_NANOS:
            raise RefusedExecution("latest SOL/USD dashboard record is stale or future")
        price = solusd_recorder._price_string(row.get("price"))
        if (row.get("source") != solusd_recorder.SOURCE or row.get("quote_currency") != "USD"
                or not isinstance(payload, dict) or payload.get("price") != price
                or payload.get("time") != row.get("provider_trade_time")):
            raise RefusedExecution("latest SOL/USD dashboard row does not reconcile to source/raw fields")
        return {"status": "FRESH", "price": price, "received_unix_nanos": received,
                "source": solusd_recorder.SOURCE}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, RefusedExecution) as exc:
        return {"status": "REFUSED", "reason": str(exc)[:180]}


def _v21_authority_key() -> tuple:
    """Cheap invalidation key for immutable authority checks; live state is never cached here."""
    paths = (
        pac_v21_manifest.PREREG, pac_v21_manifest.FROZEN, pac_v21_manifest.SEAL,
        pac_v21_manifest.CAMPAIGN, pac_v21_manifest.JOURNAL, pac_v21_manifest.SAMPLES,
        pac_v21_manifest.ATTESTATIONS, pac_v21_manifest.ACTIVATION,
        *(ROOT / relative for relative in pac_v21_manifest.DEPENDENCY_PATHS),
        ROOT / ".git" / "HEAD", ROOT / ".git" / "index",
    )
    key = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            key.append((str(path), None, None))
        else:
            key.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(key)


def _v21_successor_status() -> dict:
    """Read-only V2.1 authority progress; never loads a signer, sends, or runs the candidate."""
    key = _v21_authority_key()
    with _V21_AUTHORITY_LOCK:
        if _V21_SUCCESSOR_CACHE["key"] == key:
            return copy.deepcopy(_V21_SUCCESSOR_CACHE["value"])
    seal = pac_v21_manifest.anchor_status()

    def artifact(path: pathlib.Path) -> str:
        if not path.exists():
            return "ABSENT"
        return "ANCHORED" if pac_v21_manifest._git_clean(path) else "UNANCHORED"

    campaign = artifact(pac_v21_manifest.CAMPAIGN)
    activation = artifact(pac_v21_manifest.ACTIVATION)
    if seal != "ANCHORED":
        stage = "SEAL_NOT_ANCHORED"
    elif campaign == "ABSENT":
        stage = "SEALED_DEFAULT_OFF_AWAITING_OWNER_CAMPAIGN"
    elif campaign != "ANCHORED":
        stage = "CAMPAIGN_AWAITING_GIT_ANCHOR"
    elif activation == "ABSENT":
        stage = "CAMPAIGN_ANCHORED_CALIBRATION_AND_ATTESTATION_REQUIRED"
    elif activation != "ANCHORED":
        stage = "ACTIVATION_AWAITING_GIT_ANCHOR"
    else:
        # Runtime still repeats live finalized verification; the dashboard never weakens that gate.
        stage = "ACTIVATION_ANCHORED_RUNTIME_LIVE_VERIFY_REQUIRED"
    value = {
        "instrument_id": pac_v21_manifest.INSTRUMENT,
        "status": stage,
        "seal": seal,
        "campaign": campaign,
        "activation": activation,
        "dependency_count": len(pac_v21_manifest.DEPENDENCY_PATHS),
        "formula": "1 payable shock · full recovery/floor · processed p90 · ≥3 buyers · 6× cover",
        "boundary": "PAPER CANDIDATE · DEFAULT OFF · NO PERFORMANCE EVIDENCE",
    }
    with _V21_AUTHORITY_LOCK:
        _V21_SUCCESSOR_CACHE.update({"key": key, "value": copy.deepcopy(value)})
    return value


def _v22_successor_status() -> dict:
    """Read-only V2.2 authority and low-lag feed status; never starts or activates anything."""
    seal = pac_v22_manifest.anchor_status()

    def artifact(path: pathlib.Path) -> str:
        if not path.exists():
            return "ABSENT"
        return "ANCHORED" if pac_v22_manifest._git_clean(path) else "UNANCHORED"

    campaign = artifact(pac_v22_manifest.CAMPAIGN)
    activation = artifact(pac_v22_manifest.ACTIVATION)
    try:
        health = pac_v22_feed.load_health()
        health_age = max(0, time.time_ns() - health["observed_unix_nanos"])
        feed_status = ("FRESH" if health["status"] == "FRESH"
                       and health_age <= pac_v22_feed.MAX_HEALTH_AGE_NANOS
                       and health["head_slot_lag"] is not None
                       and health["head_slot_lag"] <= pac_v22_feed.MAX_HEAD_SLOT_LAG
                       else "DEGRADED")
    except RefusedExecution as exc:
        health = {"status": "REFUSED", "reason": str(exc)[:180], "head_slot_lag": None,
                  "observed_unix_nanos": None}
        feed_status = "REFUSED"
    if activation == "ANCHORED":
        stage = "ACTIVATED_LOW_LAG_PAPER_RUNTIME"
    elif campaign == "ANCHORED":
        stage = "SEALED_CAMPAIGN_ANCHORED_BROADCAST_OWNER_GATED"
    elif seal == "ANCHORED":
        stage = "SEALED_LOW_LAG_FEED_CALIBRATION_CAMPAIGN_REQUIRED"
    else:
        stage = "V22_SEAL_NOT_ANCHORED"
    return {
        "instrument_id": pac_v22_manifest.INSTRUMENT, "status": stage,
        "seal": seal, "campaign": campaign, "activation": activation,
        "dependency_count": len(pac_v22_manifest.DEPENDENCY_PATHS),
        "feed": {**health, "effective_status": feed_status,
                 "process": _tmux_running("pac-v22-feed")},
        "formula": "V2.1 single-shock rule unchanged · low-lag causal feed",
        "boundary": "PAPER ONLY · PRE-ACTIVATION FEED DIAGNOSTIC · NO PERFORMANCE",
    }


def _v22_feed_diagnostic(*, now: int | None = None,
                         events_path: pathlib.Path | None = None,
                         receipts_path: pathlib.Path | None = None) -> dict:
    """Incremental, non-authoritative display of V2.2 traffic observed after dashboard startup.

    The first call starts at EOF, so the UI cannot accidentally present the pre-activation soak as
    forward strategy evidence.  Subsequent calls use the same authenticated feed consumer as the
    runner and retain only the causal 180-second window.  This never evaluates the strategy.
    """
    clock = time.time_ns() if now is None else now
    event_file = pac_v22_feed.EVENTS if events_path is None else pathlib.Path(events_path)
    receipt_file = pac_v22_feed.RECEIPTS if receipts_path is None else pathlib.Path(receipts_path)
    if type(clock) is not int or clock < 0:
        raise RefusedExecution("PAC V2.2 diagnostic clock is invalid")
    with _V22_DIAGNOSTIC_LOCK:
        if not _V22_DIAGNOSTIC["initialized"]:
            # Receipts are sampled before events, matching consume().  An event appended between the
            # two observations is retained as pending until its later receipt; no historical scan.
            receipt_offset = receipt_file.stat().st_size if receipt_file.exists() else 0
            event_offset = event_file.stat().st_size if event_file.exists() else 0
            _V22_DIAGNOSTIC.update({
                "initialized": True,
                "cursor": pac_v22_feed.Cursor(
                    event_offset=event_offset, receipt_offset=receipt_offset),
                "buffers": {},
                "last_error": None,
            })
        cursor = _V22_DIAGNOSTIC["cursor"]
        try:
            events = pac_v22_feed.consume(
                cursor, events_path=event_file, receipts_path=receipt_file,
                runner_seen_unix_nanos=clock)
            buffers = _V22_DIAGNOSTIC["buffers"]
            for event in events:
                rows = buffers.setdefault(event.mint, [])
                if rows and rows[-1].collector_epoch != event.collector_epoch:
                    rows.clear()
                rows.append(event)
            cutoff = clock - pac_v2_detector.pac_detector.MAX_PATTERN_SPAN_NANOS
            for mint in list(buffers):
                kept = [event for event in buffers[mint]
                        if event.source_received_unix_nanos >= cutoff]
                if kept:
                    buffers[mint] = kept
                else:
                    del buffers[mint]
            _V22_DIAGNOSTIC["last_error"] = None
        except (OSError, ValueError, RefusedExecution) as exc:
            _V22_DIAGNOSTIC["last_error"] = str(exc)[:180]
            raise

        candidates = []
        for mint, rows in _V22_DIAGNOSTIC["buffers"].items():
            latest = rows[-1]
            buyers = {event.trader for event in rows if event.side == "buy"}
            candidates.append({
                "mint": mint,
                "event_count": len(rows),
                "latest_source_received_unix_nanos": latest.source_received_unix_nanos,
                "age_millis": max(0, clock - latest.source_received_unix_nanos) // 1_000_000,
                "current_reserve_lamports": latest.post_state.real_quote,
                "reserve_cover_lamports": None,
                "reserve_cover_milli": None,
                "gate": "FEED_ONLY",
                "gate_depth": 0,
                "gate_label": "low-lag event observed; strategy evaluation begins after activation",
                "dwell_nanos": None,
                "reaction_p90_nanos": None,
                "buyer_breadth": len(buyers),
                "dwell_clock": "V22_FRAME_RECEIVE_TIME_DIAGNOSTIC",
            })
        candidates.sort(key=lambda row: (-row["latest_source_received_unix_nanos"], row["mint"]))
        count = sum(row["event_count"] for row in candidates)
        return {
            "boundary": "DASHBOARD_LOCAL_V22_FEED_DIAGNOSTIC_NOT_RUNNER_STATE_OR_PERFORMANCE",
            "quote_input_lamports": None,
            "summary": {
                "buffered_mints": len(candidates), "eligible_events": count,
                "pac_core_mints": 0, "p90_dwell_mints": 0,
                "probe_cover_mints": 0, "recovery_survival_mints": 0,
                "buyer_breadth_mints": 0, "qualified_mints": 0,
            },
            "candidates": candidates[:100],
        }


def v22_feed_snapshot() -> dict:
    """Show the anchored V2.2 feed soak without manufacturing fills or performance authority."""
    authority = _v22_successor_status()
    feed_status = authority["feed"]
    errors: list[str] = []
    try:
        candidate_funnel = _v22_feed_diagnostic()
    except (OSError, ValueError, RefusedExecution) as exc:
        errors.append(f"PAC V2.2 feed diagnostic refused: {str(exc)[:180]}")
        candidate_funnel = {
            "boundary": "V22_FEED_DIAGNOSTIC_REFUSED",
            "quote_input_lamports": None,
            "summary": {"buffered_mints": 0, "eligible_events": 0,
                        "pac_core_mints": 0, "p90_dwell_mints": 0,
                        "probe_cover_mints": 0, "recovery_survival_mints": 0,
                        "buyer_breadth_mints": 0, "qualified_mints": 0},
            "candidates": [],
        }
    summary = candidate_funnel["summary"]
    performance = _performance([])
    performance.update({"scenario_resolved": 0, "promotion_discovery_resolved": 0,
                        "discovery_progress": "0.0000"})
    fresh = feed_status.get("effective_status") == "FRESH" and feed_status.get("process") is True
    evidence_status = ("ACTIVE_FEED_SOAK_NO_PERFORMANCE_AUTHORITY" if fresh and not errors
                       else "REFUSED_V22_FEED_HEALTH")
    health_age = None
    observed = feed_status.get("observed_unix_nanos")
    if type(observed) is int:
        health_age = max(0, time.time_ns() - observed) // 1_000_000
    operational = {
        "instrument_id": pac_v22_manifest.INSTRUMENT,
        "status": authority["status"],
        "seal": authority["seal"], "campaign": authority["campaign"],
        "activation": authority["activation"],
        "dependency_count": authority["dependency_count"],
        "reaction_p90_nanos": None, "processed_samples": 0, "failed_samples": 0,
        "state": "FEED_HEALTH_VALID" if fresh and not errors else "REFUSED",
        "processes": {"supervisor": _tmux_running("pac-wd"),
                      "feed": bool(feed_status.get("process")), "runner": False},
        "solusd": _latest_solusd_status(), "latency_calibration": "CALIBRATION_REQUIRED",
        "last_status": f"{feed_status.get('effective_status', 'UNKNOWN')} · head lag "
                       f"{feed_status.get('head_slot_lag', '—')} slots · health age "
                       f"{health_age if health_age is not None else '—'}ms",
        "events_consumed_bytes": (pac_v22_feed.EVENTS.stat().st_size
                                  if pac_v22_feed.EVENTS.exists() else 0),
        "active_mint_buffers": summary["buffered_mints"],
        "eligible_feed_events": summary["eligible_events"],
        "scan_interval_millis": None,
        "runner_audit": "FEED_ONLY_SOAK_RUNNER_NOT_ACTIVATED",
        "head_slot_lag": feed_status.get("head_slot_lag"),
        "feed_health_age_millis": health_age,
        "open_gates": ["owner-authorized mainnet latency calibration",
                       "anchored V2.2 activation", "100 resolved forward paper positions"],
    }
    return {
        "instrument_id": pac_v22_manifest.INSTRUMENT,
        "title": "Single-Shock Payable Absorption · V2.2 low-lag feed",
        "boundary": "PRE-ACTIVATION FEED SOAK ONLY · NO PAPER FILLS · NO WALLET · NO ORDERS",
        "evidence_status": evidence_status,
        "integrity_errors": errors,
        "operational": operational,
        "formula": "V2.1 rule unchanged · one subscription · receive-time clock · ≤32-slot lag",
        "formula_note": "mint rows below prove fresh feed processing only; they are not signals or trades",
        "policy": {"bankroll_index_start": "100.00", "probe_index_points": "10.00",
                   "trail_percent": 12, "coverage_multiple": 6,
                   "max_hold_minutes": 12, "max_concurrent_positions": 1},
        "performance": performance, "open_positions": [], "pending_orders": [],
        "last_measurement_refusal": None, "candidate_funnel": candidate_funnel,
        "activity": [], "ledger_rows": 0,
        "challenger": {"instrument_id": pac_v21_manifest.INSTRUMENT,
                       "status": "BURNED_FEED_CLOCK_INVALID_ZERO_FILLS",
                       "note": "V2.1 recorded zero fills; its lagged/compressed feed clock invalidates it."},
        "successor": authority,
        "generated_at": time.time(),
    }


def _v22_offline_proof() -> pac_v22_runner.RuntimeProof:
    """Validate anchored V2.2 authority without performing the production live-RPC reread."""
    paths = (pac_v22_manifest.SEAL, pac_v22_manifest.CAMPAIGN,
             pac_v22_manifest.JOURNAL, pac_v22_manifest.SAMPLES,
             pac_v22_manifest.ATTESTATIONS, pac_v22_manifest.ACTIVATION,
             ROOT / ".git" / "HEAD", ROOT / ".git" / "index")
    key = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size)
                if path.exists() else (str(path), None, None) for path in paths)
    with _V22_VIEW_LOCK:
        if _V22_PROOF_CACHE["key"] == key:
            return _V22_PROOF_CACHE["value"]
        with pac_v22_manifest._configured():
            legacy = pac_v22_manifest.legacy
            seal = legacy.verify_seal()
            if (legacy.anchor_status() != "ANCHORED"
                    or not legacy._git_clean(legacy.ACTIVATION)):
                raise RefusedExecution("PAC V2.2 dashboard authority is not anchored")
            activation = legacy._json(legacy.ACTIVATION)
            legacy._activation_body(activation, seal)
            closed = legacy._load_bound_evidence(activation)
            legacy._activation_body(activation, seal, closed)
        proof = pac_v22_runner.RuntimeProof(
            seal["seal_sha256"], activation["activation_unix_nanos"], closed.calibration)
        _V22_PROOF_CACHE.update({"key": key, "value": proof})
        return proof


def v22_snapshot() -> dict:
    """Activated V2.2 state/ledger view, reusing the identical V2.1 book validator."""
    global pac_v21_manifest, pac_v21_runner, _v21_offline_proof
    authority = _v22_successor_status()
    with _V22_VIEW_LOCK:
        old_manifest, old_runner, old_proof = (
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof)
        pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
            pac_v22_manifest, pac_v22_runner, _v22_offline_proof)
        try:
            result = v21_snapshot(successor_status=authority)
        finally:
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
                old_manifest, old_runner, old_proof)
    processes = result["operational"]["processes"]
    processes.update({"supervisor": _tmux_running("pac-wd"),
                      "feed": _tmux_running("pac-v22-feed"),
                      "runner": _tmux_running("pac-v22")})
    healthy = result["operational"]["state"] == "VALID" and all(processes.values())
    result.update({
        "title": "Single-Shock Payable Absorption · V2.2 (low-lag calibrated)",
        "formula": "W≥$10 · full recovery/floor · processed p90 · ≥3 buyers · 6× max(probe, shock)",
        "formula_note": "V2.1 strategy unchanged; one-subscription low-lag causal feed",
        "challenger": {"instrument_id": "AFTERSHOCK_PAC_V21",
                       "status": "BURNED_FEED_CLOCK_INVALID_ZERO_FILLS",
                       "note": "V2.1 produced no fills and is retired; no outcome is carried forward."},
        "successor": authority,
    })
    result["operational"].update({
        "status": ("ACTIVE_AUTHENTICATED_PAPER_SCENARIO" if healthy
                   else "ACTIVE_RUNTIME_REFUSED"),
        "seal": authority["seal"], "campaign": authority["campaign"],
        "activation": authority["activation"],
        "dependency_count": authority["dependency_count"],
    })
    if result["operational"]["state"] == "VALID":
        result["evidence_status"] = ("VALID_CALIBRATED_PAPER_SCENARIO"
                                     if result["performance"]["resolved"]
                                     else "ACTIVE_CALIBRATED_SCANNING_NO_FILLS_YET")
    return result


_V2_GATE_LABELS = {
    "NO_PAC_CORE": "waiting for 2 sell/recovery cycles",
    "P90_DWELL": "PAC core · waiting for p90 dwell",
    "PROBE_COVER": "dwell passed · $10 probe too large",
    "RECOVERY_SURVIVAL": "probe covered · recovery eroded",
    "BUYER_BREADTH": "recovery held · waiting for 3 buyers",
    "RESERVE_COVER": "buyers passed · waiting for 6× cover",
    "QUALIFIED": "all frozen entry gates passed",
}


def _v2_candidate_row(mint: str, raw_events: list[dict], *, reaction_p90_nanos: int,
                      quote_input_lamports: int, now: int) -> dict:
    """Explain the deepest frozen V2 entry gate reached by one causal in-memory mint buffer.

    This is display-only diagnostics over evidence already admitted by the sealed runner. It neither
    mutates the runner nor creates a decision, and calls the frozen detector primitives instead of
    inventing looser UI thresholds.
    """
    if (not isinstance(mint, str) or not mint or not isinstance(raw_events, list)
            or type(reaction_p90_nanos) is not int or reaction_p90_nanos <= 0
            or type(quote_input_lamports) is not int or quote_input_lamports <= 0
            or type(now) is not int or now < 0):
        raise RefusedExecution("PAC V2 candidate diagnostic input is invalid")
    events = tuple(pac_v2_runner._event(item) for item in raw_events)
    if not events or any(event.mint != mint for event in events):
        raise RefusedExecution("PAC V2 candidate diagnostic mint/buffer mismatch")
    if not pac_v2_detector._valid_stream(events):
        raise RefusedExecution("PAC V2 candidate diagnostic stream is not causal and contiguous")
    latest = events[-1]
    if latest.source_received_unix_nanos > now:
        raise RefusedExecution("PAC V2 candidate diagnostic contains future evidence")

    best = {
        "depth": 0,
        "gate": "NO_PAC_CORE",
        "gate_detail": _V2_GATE_LABELS["NO_PAC_CORE"],
        "dwell_nanos": None,
        "buyer_breadth": 0,
        "largest_observed_sell_lamports": None,
        "reserve_cover_lamports": None,
    }

    def reached(depth: int, gate: str, detail: str, **metrics) -> bool:
        # recovery2 is scanned newest-first, so equal-depth ties retain the newest causal setup.
        if depth <= best["depth"]:
            return False
        best.update({"depth": depth, "gate": gate, "gate_detail": detail, **metrics})
        return True

    for recovery2 in range(len(events) - 1, 2, -1):
        prefix = events[:recovery2 + 1]
        pac_indices = pac_v2_detector.pac_detector.detector(prefix, 0)
        if not pac_indices or pac_indices[-1] != recovery2:
            continue
        w1, _r1, _w2, r2 = pac_indices
        dwell = latest.source_received_unix_nanos - events[r2].source_received_unix_nanos
        total_span = latest.source_received_unix_nanos - events[w1].source_received_unix_nanos
        newest_at_depth = reached(
            1, "P90_DWELL", _V2_GATE_LABELS["P90_DWELL"], dwell_nanos=dwell)
        if dwell < reaction_p90_nanos:
            if newest_at_depth:
                best["gate_detail"] = (
                    f"dwell {dwell / 1_000_000_000:.3f}s < p90 "
                    f"{reaction_p90_nanos / 1_000_000_000:.3f}s")
            continue
        if total_span > pac_v2_detector.pac_detector.MAX_PATTERN_SPAN_NANOS:
            if newest_at_depth:
                best["gate_detail"] = (
                    f"total span {total_span / 1_000_000_000:.3f}s exceeds 180s")
            continue
        reached(2, "PROBE_COVER", _V2_GATE_LABELS["PROBE_COVER"], dwell_nanos=dwell)
        if not pac_v2_detector.pac_detector.position_size_is_covered(
                prefix, pac_indices, quote_input_lamports):
            continue
        recovered = events[r2].post_state.real_quote
        dwell_events = events[r2:]
        reached(3, "RECOVERY_SURVIVAL", _V2_GATE_LABELS["RECOVERY_SURVIVAL"],
                dwell_nanos=dwell)
        if any(event.post_state.real_quote < recovered for event in dwell_events):
            continue
        buyers = {event.trader for event in dwell_events if event.side == "buy"}
        reached(4, "BUYER_BREADTH", _V2_GATE_LABELS["BUYER_BREADTH"],
                dwell_nanos=dwell, buyer_breadth=len(buyers))
        if len(buyers) < pac_v2_detector.BUYER_BREADTH_MIN:
            continue
        setup = events[w1:]
        largest = max((max(0, event.pre_state.real_quote - event.post_state.real_quote)
                       for event in setup), default=0)
        cover = pac_v2_detector.RESERVE_SHOCK_COVER_MULTIPLE * max(
            quote_input_lamports, largest)
        reached(5, "RESERVE_COVER", _V2_GATE_LABELS["RESERVE_COVER"],
                dwell_nanos=dwell, buyer_breadth=len(buyers),
                largest_observed_sell_lamports=largest, reserve_cover_lamports=cover)
        if latest.post_state.real_quote < cover:
            continue
        reached(6, "QUALIFIED", _V2_GATE_LABELS["QUALIFIED"], dwell_nanos=dwell,
                buyer_breadth=len(buyers), largest_observed_sell_lamports=largest,
                reserve_cover_lamports=cover)

    qualification = pac_v2_detector.qualify(
        events, reaction_p90_nanos=reaction_p90_nanos,
        quote_input_lamports=quote_input_lamports)
    if (qualification is None) != (best["depth"] < 6):
        raise RefusedExecution("PAC V2 dashboard gate trace diverged from frozen qualification")
    current_reserve = latest.post_state.real_quote
    required_cover = best["reserve_cover_lamports"]
    return {
        "mint": mint,
        "event_count": len(events),
        "latest_source_received_unix_nanos": latest.source_received_unix_nanos,
        "age_millis": (now - latest.source_received_unix_nanos) // 1_000_000,
        "current_reserve_lamports": current_reserve,
        "gate_depth": best.pop("depth"),
        "gate_label": _V2_GATE_LABELS[best["gate"]],
        "reaction_p90_nanos": reaction_p90_nanos,
        "reserve_cover_milli": (current_reserve * 1_000 // required_cover
                                 if isinstance(required_cover, int) and required_cover > 0 else None),
        **best,
    }


def _v2_candidate_funnel(buffers: dict, *, reaction_p90_nanos: int,
                         quote_input_lamports: int, now: int) -> dict:
    """Build a bounded, causal, read-only funnel for the PAC dashboard."""
    if not isinstance(buffers, dict):
        raise RefusedExecution("PAC V2 candidate buffers are invalid")
    candidates = [
        _v2_candidate_row(mint, raw_events, reaction_p90_nanos=reaction_p90_nanos,
                          quote_input_lamports=quote_input_lamports, now=now)
        for mint, raw_events in buffers.items()
    ]
    candidates.sort(key=lambda row: (
        -row["gate_depth"], -row["latest_source_received_unix_nanos"], row["mint"]))
    summary = {
        "buffered_mints": len(candidates),
        "eligible_events": sum(row["event_count"] for row in candidates),
        "pac_core_mints": sum(row["gate_depth"] >= 1 for row in candidates),
        "p90_dwell_mints": sum(row["gate_depth"] >= 2 for row in candidates),
        "probe_cover_mints": sum(row["gate_depth"] >= 3 for row in candidates),
        "recovery_survival_mints": sum(row["gate_depth"] >= 4 for row in candidates),
        "buyer_breadth_mints": sum(row["gate_depth"] >= 5 for row in candidates),
        "qualified_mints": sum(row["gate_depth"] >= 6 for row in candidates),
    }
    return {
        "boundary": "READ_ONLY_CAUSAL_BUFFER_DIAGNOSTIC_NOT_A_TRADE_OR_PERFORMANCE_ROW",
        "quote_input_lamports": quote_input_lamports,
        "summary": summary,
        "candidates": candidates[:100],
    }


_V21_GATE_LABELS = {
    "NO_PAYABLE_SHOCK": "waiting for one sell at least as large as the $10 probe",
    "FULL_RECOVERY": "payable shock · waiting for full reserve recovery",
    "P90_DWELL": "recovered · waiting for a later same-mint event ≥ processed-p90",
    "FLOOR_SURVIVAL": "dwell passed · recovery floor eroded",
    "BUYER_BREADTH": "floor held · waiting for 3 buyers excluding seller",
    "RESERVE_COVER": "buyers passed · waiting for 6× probe/shock cover",
    "QUALIFIED": "all frozen V2.1 entry gates passed",
}


def _v21_candidate_row(mint: str, raw_events: list[dict], *, processed_p90_nanos: int,
                       quote_input_lamports: int, now: int) -> dict:
    if (not isinstance(mint, str) or not mint or not isinstance(raw_events, list)
            or type(processed_p90_nanos) is not int or processed_p90_nanos <= 0
            or type(quote_input_lamports) is not int or quote_input_lamports <= 0
            or type(now) is not int or now < 0):
        raise RefusedExecution("PAC V2.1 candidate diagnostic input is invalid")
    events = tuple(pac_v2_runner._event(item) for item in raw_events)
    if (not events or any(event.mint != mint for event in events)
            or not pac_v2_detector._valid_stream(events)
            or events[-1].source_received_unix_nanos > now):
        raise RefusedExecution("PAC V2.1 candidate stream is non-causal or mismatched")
    latest = events[-1]
    best = {"depth": 0, "gate": "NO_PAYABLE_SHOCK",
            "gate_detail": _V21_GATE_LABELS["NO_PAYABLE_SHOCK"],
            "dwell_nanos": None, "buyer_breadth": 0,
            "largest_observed_sell_lamports": None, "reserve_cover_lamports": None}

    def reached(depth: int, gate: str, **metrics) -> None:
        if depth > best["depth"]:
            best.update({"depth": depth, "gate": gate,
                         "gate_detail": _V21_GATE_LABELS[gate], **metrics})

    for shock_index in range(len(events) - 2, -1, -1):
        shock = events[shock_index]
        shock_lamports = shock.pre_state.real_quote - shock.post_state.real_quote
        if shock.side != "sell" or shock_lamports < quote_input_lamports:
            continue
        buyers = {event.trader for event in events[shock_index + 1:]
                  if event.side == "buy" and event.trader != shock.trader}
        cover = pac_v21_detector.RESERVE_SHOCK_COVER_MULTIPLE * max(
            quote_input_lamports, shock_lamports)
        observed = {
            "buyer_breadth": len(buyers),
            "largest_observed_sell_lamports": shock_lamports,
            "reserve_cover_lamports": cover,
        }
        reached(1, "FULL_RECOVERY", **observed)
        recovery_index = next((index for index in range(shock_index + 1, len(events))
                               if events[index].post_state.real_quote
                               >= shock.pre_state.real_quote), None)
        if recovery_index is None:
            continue
        dwell = latest.source_received_unix_nanos - events[recovery_index].source_received_unix_nanos
        span = latest.source_received_unix_nanos - shock.source_received_unix_nanos
        reached(2, "P90_DWELL", dwell_nanos=dwell, **observed)
        if dwell < processed_p90_nanos or span > 180_000_000_000:
            continue
        reached(3, "FLOOR_SURVIVAL", dwell_nanos=dwell, **observed)
        if any(event.post_state.real_quote < shock.pre_state.real_quote
               for event in events[recovery_index:]):
            continue
        reached(4, "BUYER_BREADTH", dwell_nanos=dwell, **observed)
        if len(buyers) < pac_v21_detector.BUYER_BREADTH_MIN:
            continue
        reached(5, "RESERVE_COVER", dwell_nanos=dwell, **observed)
        if latest.post_state.real_quote < cover:
            continue
        reached(6, "QUALIFIED", dwell_nanos=dwell, **observed)

    qualification = pac_v21_detector.qualify(
        events, processed_p90_nanos=processed_p90_nanos,
        quote_input_lamports=quote_input_lamports)
    if (qualification is None) != (best["depth"] < 6):
        raise RefusedExecution("PAC V2.1 dashboard trace diverged from sealed qualification")
    current = latest.post_state.real_quote
    required = best["reserve_cover_lamports"]
    return {
        "mint": mint, "event_count": len(events),
        "latest_source_received_unix_nanos": latest.source_received_unix_nanos,
        "age_millis": (now - latest.source_received_unix_nanos) // 1_000_000,
        "current_reserve_lamports": current,
        "gate_depth": best.pop("depth"), "gate_label": _V21_GATE_LABELS[best["gate"]],
        "reaction_p90_nanos": processed_p90_nanos,
        "dwell_clock": "SAME_MINT_EVENT_TIME_NOT_WALL_CLOCK",
        "reserve_cover_milli": (current * 1_000 // required
                                 if isinstance(required, int) and required > 0 else None),
        **best,
    }


def _v21_candidate_funnel(buffers: dict, *, processed_p90_nanos: int,
                          quote_input_lamports: int, now: int) -> dict:
    if not isinstance(buffers, dict):
        raise RefusedExecution("PAC V2.1 candidate buffers are invalid")
    candidates = [_v21_candidate_row(
        mint, rows, processed_p90_nanos=processed_p90_nanos,
        quote_input_lamports=quote_input_lamports, now=now)
        for mint, rows in buffers.items()]
    candidates.sort(key=lambda row: (-row["gate_depth"],
                                     -row["latest_source_received_unix_nanos"], row["mint"]))
    return {
        "boundary": "READ_ONLY_V21_CAUSAL_BUFFER_DIAGNOSTIC_NOT_TRADE_OR_PERFORMANCE",
        "quote_input_lamports": quote_input_lamports,
        "summary": {
            "buffered_mints": len(candidates),
            "eligible_events": sum(row["event_count"] for row in candidates),
            "pac_core_mints": sum(row["gate_depth"] >= 1 for row in candidates),
            "p90_dwell_mints": sum(row["gate_depth"] >= 3 for row in candidates),
            "probe_cover_mints": sum(row["gate_depth"] >= 1 for row in candidates),
            "recovery_survival_mints": sum(row["gate_depth"] >= 4 for row in candidates),
            "buyer_breadth_mints": sum(row["gate_depth"] >= 5 for row in candidates),
            "qualified_mints": sum(row["gate_depth"] >= 6 for row in candidates),
        },
        "candidates": candidates[:100],
    }


def _validate_open(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise RefusedExecution("PAC open position must be an object")
    out = {
        "mint": _text("open.mint", raw.get("mint")),
        "token_atoms": _exact_int("open.token_atoms", raw.get("token_atoms"), minimum=1),
        "quote_input_lamports": _exact_int(
            "open.quote_input_lamports", raw.get("quote_input_lamports"), minimum=1),
        "entry_all_in_lamports": _exact_int(
            "open.entry_all_in_lamports", raw.get("entry_all_in_lamports"), minimum=1),
        "entry_curve_fee_lamports": _exact_int(
            "open.entry_curve_fee_lamports", raw.get("entry_curve_fee_lamports"), minimum=0),
        "entry_attempt_cost_lamports": _exact_int(
            "open.entry_attempt_cost_lamports", raw.get("entry_attempt_cost_lamports"), minimum=0),
        "ata_rent_lamports": _exact_int(
            "open.ata_rent_lamports", raw.get("ata_rent_lamports"), minimum=0),
        "entry_observation_unix_nanos": _exact_int(
            "open.entry_observation_unix_nanos", raw.get("entry_observation_unix_nanos"), minimum=0),
        "peak_full_exit_quote_lamports": _exact_int(
            "open.peak_full_exit_quote_lamports", raw.get("peak_full_exit_quote_lamports"), minimum=0),
        "entry_decision_id": _text("open.entry_decision_id", raw.get("entry_decision_id")),
        "entry_attempt_id": _text("open.entry_attempt_id", raw.get("entry_attempt_id")),
        "last_processed_observation_unix_nanos": _exact_int(
            "open.last_processed_observation_unix_nanos",
            raw.get("last_processed_observation_unix_nanos"), minimum=0),
    }
    if out["last_processed_observation_unix_nanos"] < out["entry_observation_unix_nanos"]:
        raise RefusedExecution("PAC open position resume clock precedes its entry")
    if out["entry_all_in_lamports"] != (out["quote_input_lamports"]
            + out["entry_curve_fee_lamports"] + out["entry_attempt_cost_lamports"]
            + out["ata_rent_lamports"]):
        raise RefusedExecution("PAC open position entry costs do not reconcile")
    return out


def _validate_rows(rows: list[dict], opens: list[dict], state: dict) -> tuple[list[dict], list[dict], list[dict]]:
    event_ids: set[str] = set()
    opened: dict[str, dict] = {}
    closed_attempts: set[str] = set()
    # A known-unavailable exit is represented by two authenticated facts from the sealed V1 producer:
    # (1) the attempt had no observable cost/output, and (2) that same attempt terminally resolved the
    # position at the full-loss bound.  This is one attempt referenced by two event rows, not a duplicate
    # attempt.  Retain the complete first row so only that exact producer relation is admitted below.
    unavailable_exit_attempts: dict[str, dict] = {}
    resolved: list[dict] = []
    performance_events: list[dict] = []
    activity: list[dict] = []
    for index, row in enumerate(rows):
        event_id = _text(f"ledger[{index}].event_id", row.get("event_id"))
        if event_id in event_ids:
            raise RefusedExecution("PAC ledger contains a duplicate event_id")
        event_ids.add(event_id)
        kind = row.get("kind")
        mint = _text(f"ledger[{index}].mint", row.get("mint"))
        if state["session_event_sha256"] is not None and (
                row.get("session_event_sha256") != state["session_event_sha256"]
                or row.get("activation_root_sha256") != state["activation_root_sha256"]):
            raise RefusedExecution("PAC ledger row belongs to another runner session")
        if kind == "opened":
            attempt_id = _text("opened.entry_attempt_id", row.get("entry_attempt_id"))
            if attempt_id in opened:
                raise RefusedExecution("PAC ledger contains a duplicate opened entry attempt")
            entry_all_in = _exact_int(
                "opened.entry_all_in_lamports", row.get("entry_all_in_lamports"), minimum=1)
            quote_input = _exact_int(
                "opened.quote_input_lamports", row.get("quote_input_lamports"), minimum=1)
            entry_curve = _exact_int("opened.entry_curve_fee_lamports",
                                     row.get("entry_curve_fee_lamports"), minimum=0)
            entry_attempt = _exact_int("opened.entry_attempt_cost_lamports",
                                       row.get("entry_attempt_cost_lamports"), minimum=0)
            rent = _exact_int("opened.ata_rent_lamports", row.get("ata_rent_lamports"), minimum=0)
            if entry_all_in != quote_input + entry_curve + entry_attempt + rent:
                raise RefusedExecution("PAC opened entry costs do not reconcile")
            opened[attempt_id] = row
            activity.append({"kind": kind, "mint": mint, "status": "OPENED",
                             "entry_attempt_id": attempt_id})
            continue
        if kind == "attempt_cost":
            attempt_id = _text("attempt_cost.attempt_id", row.get("attempt_id"))
            if attempt_id in closed_attempts:
                raise RefusedExecution("PAC ledger contains a duplicate attempt id")
            closed_attempts.add(attempt_id)
            cost = _exact_int("attempt_cost.attempt_cost_lamports",
                              row.get("attempt_cost_lamports"), minimum=0)
            denominator = _exact_int("attempt_cost.denominator_lamports",
                                     row.get("denominator_lamports"), minimum=1)
            observed = row.get("cost_observed")
            if type(observed) is not bool or (not observed and cost != 0):
                raise RefusedExecution("PAC failed-attempt cost observability does not reconcile")
            side = _text("attempt_cost.side", row.get("side"))
            outcome = _text("attempt_cost.outcome", row.get("outcome"))
            if side not in {"ENTRY", "EXIT"}:
                raise RefusedExecution("PAC failed-attempt side is invalid")
            if side == "EXIT" and outcome == "SCENARIO_UNAVAILABLE":
                unavailable_exit_attempts[attempt_id] = {
                    "mint": mint,
                    "entry_attempt_id": row.get("entry_attempt_id"),
                    "cost_observed": observed,
                    "attempt_cost_lamports": cost,
                }
            ret = Fraction(-cost, denominator)
            performance_events.append({"kind": kind, "return": ret,
                                       "unexitable_full_loss": False})
            activity.append({"kind": kind, "mint": mint,
                             "status": outcome,
                             "attempt_cost_lamports": cost,
                             "return_r": _decimal(ret)})
            continue
        if kind != "resolved":
            raise RefusedExecution(f"PAC ledger contains unknown kind {kind!r}")

        entry_attempt = _text("resolved.entry_attempt_id", row.get("entry_attempt_id"))
        exit_attempt = row.get("exit_attempt_id")
        if exit_attempt is not None:
            exit_attempt = _text("resolved.exit_attempt_id", exit_attempt)
            if exit_attempt in closed_attempts:
                unavailable = unavailable_exit_attempts.get(exit_attempt)
                if not (unavailable is not None
                        and unavailable["mint"] == mint
                        and unavailable["entry_attempt_id"] == entry_attempt
                        and unavailable["cost_observed"] is False
                        and unavailable["attempt_cost_lamports"] == 0
                        and row.get("exit_outcome") == "SCENARIO_UNAVAILABLE"
                        and row.get("unexitable_full_loss") is True):
                    raise RefusedExecution("PAC ledger contains a duplicate exit attempt")
            else:
                closed_attempts.add(exit_attempt)
        if entry_attempt not in opened:
            raise RefusedExecution("PAC resolution does not reference an earlier opened entry")
        if any(r["entry_attempt_id"] == entry_attempt for r in resolved):
            raise RefusedExecution("PAC entry resolves more than once")

        entry_cost = _exact_int(
            "resolved.entry_all_in_lamports", row.get("entry_all_in_lamports"), minimum=1)
        exit_net = _exact_int(
            "resolved.exit_net_proceeds_lamports", row.get("exit_net_proceeds_lamports"))
        num = _exact_int("resolved.net_return_num", row.get("net_return_num"))
        den = _exact_int("resolved.net_return_den", row.get("net_return_den"), minimum=1)
        if den != entry_cost or num != exit_net - entry_cost:
            raise RefusedExecution("PAC resolved return does not reconcile to all-in entry and net exit")
        opened_row = opened[entry_attempt]
        if entry_cost != opened_row["entry_all_in_lamports"]:
            raise RefusedExecution("PAC resolved entry cost differs from its opened row")
        gross = _exact_int("resolved.exit_gross_quote_lamports",
                           row.get("exit_gross_quote_lamports"), minimum=0)
        curve = _exact_int("resolved.exit_curve_fee_lamports",
                           row.get("exit_curve_fee_lamports"), minimum=0)
        attempt_cost = _exact_int("resolved.exit_attempt_cost_lamports",
                                  row.get("exit_attempt_cost_lamports"), minimum=0)
        if exit_net != gross - curve - attempt_cost:
            raise RefusedExecution("PAC exit net does not reconcile to gross quote, curve fee and attempt cost")
        if Fraction(num, den) < -1:
            raise RefusedExecution("PAC scenario return is below the full-loss floor")
        entry_obs = _exact_int(
            "resolved.entry_observation_unix_nanos", row.get("entry_observation_unix_nanos"), minimum=0)
        exit_obs = row.get("exit_boundary_observation_unix_nanos")
        if exit_obs is not None and _exact_int(
                "resolved.exit_boundary_observation_unix_nanos", exit_obs, minimum=0) <= entry_obs:
            raise RefusedExecution("PAC exit boundary is not strictly after entry")
        if row.get("unexitable_full_loss") is True and (num != -den or exit_net != 0):
            raise RefusedExecution("PAC unexitable row is not an exact full loss")
        resolved_row = {
            "kind": kind, "mint": mint,
            "action": _text("resolved.action", row.get("action")),
            "entry_attempt_id": entry_attempt, "exit_attempt_id": exit_attempt,
            "entry_observation_unix_nanos": entry_obs,
            "exit_boundary_observation_unix_nanos": exit_obs,
            "return": Fraction(num, den),
            "return_r": _decimal(Fraction(num, den)),
            "entry_all_in_lamports": entry_cost,
            "exit_net_proceeds_lamports": exit_net,
            "unexitable_full_loss": row.get("unexitable_full_loss") is True,
        }
        resolved.append(resolved_row)
        performance_events.append(resolved_row)
        activity.append({k: v for k, v in resolved_row.items() if k != "return"})

    open_attempts = {_text("open.entry_attempt_id", p["entry_attempt_id"]) for p in opens}
    unresolved_attempts = set(opened) - {row["entry_attempt_id"] for row in resolved}
    if open_attempts != unresolved_attempts:
        raise RefusedExecution("PAC state and ledger do not reconcile to the same open entries")
    if len(opens) > 1:
        raise RefusedExecution("PAC state violates the one-position discovery policy")
    return resolved, performance_events, activity


def _performance(resolved: list[dict], performance_events: list[dict] | None = None) -> dict:
    baseline = Fraction(100, 1)
    probe_index = Fraction(10, 1)
    equity = baseline
    peak = baseline
    max_dd = Fraction(0, 1)
    curve = [_decimal(equity, 4)]
    wins = losses = full_losses = 0
    total = Fraction(0, 1)
    performance_events = resolved if performance_events is None else performance_events
    for row in resolved:
        ret = row["return"]
        total += ret
        wins += ret > 0
        losses += ret < 0
        full_losses += row["unexitable_full_loss"]
    attempt_cost_events = sum(row["kind"] == "attempt_cost" for row in performance_events)
    total = sum((row["return"] for row in performance_events), Fraction(0, 1))
    for row in performance_events:
        ret = row["return"]
        equity += probe_index * ret
        curve.append(_decimal(equity, 4))
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    n = len(resolved)
    return {
        "resolved": n,
        "wins": wins,
        "losses": losses,
        "full_losses": full_losses,
        "failed_attempt_cost_events": attempt_cost_events,
        "win_rate": _decimal(Fraction(wins, n), 6) if n else None,
        "unexitable_rate": _decimal(Fraction(full_losses, n), 6) if n else None,
        "mean_return_r": _decimal(total / n, 6) if n else None,
        "sum_return_r": _decimal(total, 6),
        "normalized_capital_index": _decimal(equity, 4),
        "normalized_capital_change_pct": (_decimal((equity - baseline) / baseline, 6)
                                           if performance_events else None),
        "max_drawdown": _decimal(max_dd, 6) if performance_events else None,
        "equity_curve": curve,
        "minimum_discovery": 100,
        "discovery_progress": _decimal(Fraction(min(n, 100), 100), 4),
        "numeraire_note": (
            "Normalized 100-index: each fully-costed trade contributes 10 × return. "
            "It is not executable USD P&L and never includes unanchored/gross-only rows."),
    }


def snapshot(*, ledger_path: pathlib.Path = LEDGER_PATH, state_path: pathlib.Path = STATE_PATH,
             status_snapshot: dict | None = None) -> dict:
    if status_snapshot is not None:
        status = status_snapshot
    else:
        now = time.monotonic()
        with _STATUS_LOCK:
            if (_STATUS_CACHE["value"] is None
                    or now - _STATUS_CACHE["at"] >= _STATUS_TTL_SECONDS):
                _STATUS_CACHE["value"] = pac_status.status()
                _STATUS_CACHE["at"] = time.monotonic()
            status = copy.deepcopy(_STATUS_CACHE["value"])
        status["solusd"] = _latest_solusd_status()
        status["slow_inventory_refresh_seconds"] = _STATUS_TTL_SECONDS
    errors: list[str] = []
    state = pac_runner._new_state()
    rows: list[dict] = []
    opens: list[dict] = []
    resolved: list[dict] = []
    performance_events: list[dict] = []
    activity: list[dict] = []
    try:
        state = _read_state(state_path)
        rows = _read_ledger(ledger_path)
        opens = [_validate_open(raw) for raw in state["open_positions"]]
        resolved, performance_events, activity = _validate_rows(rows, opens, state)
    except RefusedExecution as exc:
        errors.append(str(exc))

    anchored = status.get("seal") == "ANCHORED" and status.get("activation") == "ANCHORED"
    if errors:
        evidence_status = "REFUSED_LEDGER_INTEGRITY"
        performance = _performance([])
    elif rows and not anchored:
        evidence_status = "REFUSED_UNANCHORED_EVIDENCE"
        errors.append("ledger rows exist while the current PAC seal/session is not anchored")
        performance = _performance([])
    elif rows:
        evidence_status = ("VALID_PAPER_SCENARIO"
                           if status.get("latency_calibration") == "CALIBRATED_FORWARD_CLOCKS"
                           else "VALID_UNCALIBRATED_PAPER_SCENARIO")
        performance = _performance(resolved, performance_events)
    else:
        evidence_status = "NO_FORWARD_EVIDENCE"
        performance = _performance([])

    scenario_resolved = performance["resolved"]
    calibrated = status.get("latency_calibration") == "CALIBRATED_FORWARD_CLOCKS"
    promotion_resolved = scenario_resolved if calibrated else 0
    performance["scenario_resolved"] = scenario_resolved
    performance["promotion_discovery_resolved"] = promotion_resolved
    performance["discovery_progress"] = _decimal(Fraction(min(promotion_resolved, 100), 100), 4)
    performance["calibration_note"] = (
        "Scenario outcomes do not count toward the 100-position promotion gate until build/sign/send/land "
        "and failure clocks are measured and separately frozen."
        if not calibrated else "Measured forward-clock outcomes count toward promotion discovery.")

    return {
        "instrument_id": "AFTERSHOCK_PAC_V1",
        "title": "Payable Absorption Compression",
        "boundary": "PAPER SCENARIO ONLY · NO WALLET · NO ORDERS · NOT A PROFIT CLAIM",
        "evidence_status": evidence_status,
        "integrity_errors": errors,
        "operational": status,
        "formula": "W2≥W1 · D2≤D1 · B2≥B1 · E2≥E1",
        "formula_note": "second sell/recovery is no weaker, no slower, and does not erode reserve capacity",
        "policy": {
            "bankroll_index_start": pac_policy.DISCOVERY_BANKROLL_USD,
            "probe_index_points": pac_policy.DISCOVERY_PROBE_USD,
            "trail_percent": 12,
            "coverage_multiple": 6,
            "max_hold_minutes": 12,
            "max_concurrent_positions": 1,
        },
        "performance": performance,
        "open_positions": opens,
        "pending_orders": state.get("pending_orders", []),
        "last_measurement_refusal": state.get("last_measurement_refusal"),
        "activity": list(reversed(activity[-100:])),
        "ledger_rows": len(rows),
        "challenger": {**pac_v2_status.status(), "live": _v2_live()},
        "generated_at": time.time(),
    }


def v2_snapshot() -> dict:
    """The PAC focus page's MAIN content, built from the live V2 calibrated runner's own scenario ledger +
    state — so the page shows the running challenger (its chart, positions, and resolved fills) instead of
    the burned V1 baseline. V1 is retired to a compact footnote in `challenger`."""
    status = pac_v2_status.status()
    led = RESEARCH / "AFTERSHOCK_PAC_V2_SCENARIO_LEDGER.jsonl"
    rows: list[dict] = []
    if led.exists():
        for line in led.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    resolved_rows = [r for r in rows if r.get("kind") == "resolved"]
    perf_rows, activity = [], []
    for r in resolved_rows:
        num, den = r.get("net_return_num"), r.get("net_return_den")
        if not (isinstance(num, int) and isinstance(den, int) and den):
            continue
        full = bool(r.get("unexitable_full_loss"))
        perf_rows.append({"kind": "resolved", "return": Fraction(num, den),
                          "unexitable_full_loss": full})
        entry_all_in = int(r.get("entry_all_in_lamports") or 0)
        activity.append({
            "kind": "resolved", "mint": r.get("mint", "—"),
            "return_r": _decimal(Fraction(num, den), 4),
            "entry_all_in_lamports": entry_all_in,
            "exit_net_proceeds_lamports": max(0, num + entry_all_in),
            "action": r.get("action", "—"), "unexitable_full_loss": full})
    performance = _performance(perf_rows)
    performance["scenario_resolved"] = performance["resolved"]
    performance["promotion_discovery_resolved"] = performance["resolved"]
    performance["discovery_progress"] = _decimal(Fraction(min(performance["resolved"], 100), 100), 4)

    state_error = None
    try:
        state = json.loads((RESEARCH / "AFTERSHOCK_PAC_V2_RUNNER_STATE.json").read_text())
    except (OSError, ValueError) as exc:
        state = {}
        state_error = f"PAC V2 dashboard state unreadable: {type(exc).__name__}"
    op, pend = state.get("open_position"), state.get("pending_order")
    open_positions = ([{"mint": op.get("mint", "—"),
                        "entry_all_in_lamports": int(op.get("entry_all_in_lamports") or 0)}]
                      if isinstance(op, dict) else [])
    pending_orders = ([{"mint": pend.get("mint", "—"), "side": pend.get("side", "ORDER"),
                        "amount": int(pend.get("amount") or 0),
                        "return_denominator_lamports": int(pend.get("amount") or 0)}]
                      if isinstance(pend, dict) else [])
    # Reuse the dashboard's reconciled raw-record view. SolUsdObservation intentionally exposes
    # value_str (not price_usd); the old duplicate adapter referenced the latter and hid every fresh
    # observation behind a blanket "unavailable" label.
    solusd = _latest_solusd_status()
    candidate_funnel = {
        "boundary": "READ_ONLY_CAUSAL_BUFFER_DIAGNOSTIC_NOT_A_TRADE_OR_PERFORMANCE_ROW",
        "quote_input_lamports": None,
        "summary": {"buffered_mints": 0, "eligible_events": 0, "pac_core_mints": 0,
                    "p90_dwell_mints": 0, "probe_cover_mints": 0,
                    "recovery_survival_mints": 0, "buyer_breadth_mints": 0,
                    "qualified_mints": 0},
        "candidates": [],
    }
    if state_error is None and state:
        try:
            now = time.time_ns()
            candidate_funnel = _v2_candidate_funnel(
                state.get("buffers"),
                reaction_p90_nanos=_exact_int(
                    "PAC V2 reaction_p90_nanos", state.get("reaction_p90_nanos"), minimum=1),
                quote_input_lamports=pac_v2_runner._quote_input(now), now=now)
        except (OSError, ValueError, RefusedExecution) as exc:
            state_error = f"PAC V2 candidate funnel refused: {str(exc)[:180]}"
    funnel_summary = candidate_funnel["summary"]
    operational = {
        **status,
        "solusd": solusd,
        "latency_calibration": "CALIBRATED_FINALIZED_RPC" if status.get("activation") == "ANCHORED" else None,
        "last_status": state.get("last_status"),
        "events_consumed_bytes": (state.get("cursor") or {}).get("event_offset") or 0,
        "active_mint_buffers": funnel_summary["buffered_mints"],
        "eligible_feed_events": funnel_summary["eligible_events"],
        "scan_interval_millis": int(pac_v2_runner.SCAN_INTERVAL_SECONDS * 1_000),
        "runner_audit": ("PASS_CAUSAL_STATE_VALID"
                         if status.get("state") == "VALID" else status.get("state")),
    }
    evidence = ("VALID_CALIBRATED_PAPER_SCENARIO" if resolved_rows
                else "ACTIVE_CALIBRATED_SCANNING_NO_FILLS_YET")
    return {
        "instrument_id": "AFTERSHOCK_PAC_V2",
        "title": "Payable Absorption Compression · V2 (mainnet-calibrated)",
        "boundary": "PAPER SCENARIO ONLY · NO WALLET · NO ORDERS · NOT A PROFIT CLAIM",
        "evidence_status": evidence,
        "integrity_errors": [state_error] if state_error else [],
        "operational": operational,
        "formula": "W2≥W1 · D2≤D1 · B2≥B1 · E2≥E1  +  p90 dwell · ≥3 buyers · 6× cover",
        "formula_note": "PAC pattern plus measured-p90 dwell, ≥3 observed buyers, and 6× largest-shock cover",
        "policy": {"bankroll_index_start": "100.00", "probe_index_points": "10.00",
                   "trail_percent": 12, "coverage_multiple": 6,
                   "max_hold_minutes": 12, "max_concurrent_positions": 1},
        "performance": performance,
        "open_positions": open_positions,
        "pending_orders": pending_orders,
        "last_measurement_refusal": None,
        "candidate_funnel": candidate_funnel,
        "activity": list(reversed(activity[-100:])),
        "ledger_rows": len(rows),
        "challenger": {"instrument_id": "AFTERSHOCK_PAC_V1", "status": "BURNED_BASELINE",
                       "note": "V1 was falsified (525 scenarios, index −559) and is retired; kept only as "
                               "a reference, not shown here.", "live": {}, "processes": {}},
        "successor": _v21_successor_status(),
        "generated_at": time.time(),
    }


def _tmux_running(name: str) -> bool:
    try:
        return subprocess.run(
            ["tmux", "has-session", "-t", f"={name}"], capture_output=True,
            timeout=2, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _v21_offline_proof() -> pac_v21_runner.RuntimeProof:
    key = _v21_authority_key()
    with _V21_AUTHORITY_LOCK:
        if _V21_PROOF_CACHE["key"] == key:
            return _V21_PROOF_CACHE["value"]
    seal = pac_v21_manifest.verify_seal()
    if (pac_v21_manifest.anchor_status() != "ANCHORED"
            or not pac_v21_manifest._git_clean(pac_v21_manifest.ACTIVATION)):
        raise RefusedExecution("PAC V2.1 dashboard authority is not anchored")
    activation = pac_v21_manifest._json(pac_v21_manifest.ACTIVATION)
    pac_v21_manifest._activation_body(activation, seal)
    closed = pac_v21_manifest._load_bound_evidence(activation)
    pac_v21_manifest._activation_body(activation, seal, closed)
    proof = pac_v21_runner.RuntimeProof(
        seal["seal_sha256"], activation["activation_unix_nanos"], closed.calibration)
    with _V21_AUTHORITY_LOCK:
        _V21_PROOF_CACHE.update({"key": key, "value": proof})
    return proof


def _v2_processes() -> dict:
    return {
        "supervisor": pac_v2_status._module_process(
            "scripts.trading_bot.aftershock.pac_v2_supervisor"),
        "feed": pac_v2_status._module_process(
            "scripts.trading_bot.aftershock.pac_v2_feed"),
        "runner": pac_v2_status._module_process(
            "scripts.trading_bot.aftershock.pac_v2_runner"),
    }


def _v2_control_status() -> dict:
    """Cache V2's immutable authority audit; refresh its process health on every dashboard read."""
    now = time.monotonic()
    with _STATUS_LOCK:
        cached = _V2_CONTROL_CACHE["value"]
        if cached is None or now - _V2_CONTROL_CACHE["at"] >= _V2_CONTROL_TTL_SECONDS:
            cached = pac_v2_status.status()
            _V2_CONTROL_CACHE.update({"at": now, "value": copy.deepcopy(cached)})
        value = copy.deepcopy(cached)
    processes = _v2_processes()
    value["processes"] = processes
    if value.get("state") == "VALID":
        value["status"] = ("ACTIVE_AUTHENTICATED_PAPER_SCENARIO"
                           if all(processes.values()) else "READY_AUTHENTICATED_NOT_RUNNING")
    return value


def v21_snapshot(*, successor_status: dict | None = None) -> dict:
    """Authenticated V2.1 paper book and causal candidate funnel; performs no live verification RPC."""
    led, state_path = pac_v21_runner.LEDGER, pac_v21_runner.STATE
    rows: list[dict] = []
    state: dict = {}
    state_error = None
    try:
        proof = _v21_offline_proof()
        state = json.loads(state_path.read_text())
        with pac_v21_runner._configured_core():
            pac_v2_runner._validate_state(state, pac_v21_runner._bridge(proof))
            if led.exists():
                for number, line in enumerate(led.read_text().splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise RefusedExecution(
                            f"PAC V2.1 ledger line {number} is malformed") from exc
                    pac_v2_runner._validate_ledger(row)
                    rows.append(row)
    except (OSError, ValueError, RefusedExecution) as exc:
        proof = None
        state_error = f"PAC V2.1 dashboard refused: {str(exc)[:180]}"

    resolved_rows = [row for row in rows if row.get("kind") == "resolved"]
    perf_rows, activity = [], []
    for row in resolved_rows:
        num, den = row.get("net_return_num"), row.get("net_return_den")
        if not (type(num) is int and type(den) is int and den > 0):
            state_error = "PAC V2.1 resolved return is not exact"
            perf_rows, activity = [], []
            break
        full = bool(row.get("unexitable_full_loss"))
        ret = Fraction(num, den)
        perf_rows.append({"kind": "resolved", "return": ret,
                          "unexitable_full_loss": full})
        entry_all_in = int(row.get("entry_all_in_lamports") or 0)
        activity.append({
            "kind": "resolved", "mint": row.get("mint", "—"),
            "return_r": _decimal(ret, 4), "entry_all_in_lamports": entry_all_in,
            "exit_net_proceeds_lamports": max(0, num + entry_all_in),
            "action": row.get("action", "—"), "unexitable_full_loss": full})
    performance = _performance(perf_rows)
    performance["scenario_resolved"] = performance["resolved"]
    performance["promotion_discovery_resolved"] = performance["resolved"]
    performance["discovery_progress"] = _decimal(
        Fraction(min(performance["resolved"], 100), 100), 4)

    op, pending = state.get("open_position"), state.get("pending_order")
    open_positions = ([{"mint": op.get("mint", "—"),
                        "entry_all_in_lamports": int(op.get("entry_all_in_lamports") or 0)}]
                      if isinstance(op, dict) else [])
    pending_orders = ([{"mint": pending.get("mint", "—"),
                        "side": pending.get("side", "ORDER"),
                        "amount": int(pending.get("amount") or 0),
                        "return_denominator_lamports": int(pending.get("amount") or 0)}]
                      if isinstance(pending, dict) else [])
    empty_summary = {"buffered_mints": 0, "eligible_events": 0, "pac_core_mints": 0,
                     "p90_dwell_mints": 0, "probe_cover_mints": 0,
                     "recovery_survival_mints": 0, "buyer_breadth_mints": 0,
                     "qualified_mints": 0}
    candidate_funnel = {"boundary": "V21_DIAGNOSTIC_UNAVAILABLE",
                        "quote_input_lamports": None, "summary": empty_summary,
                        "candidates": []}
    if state_error is None and proof is not None:
        try:
            now = time.time_ns()
            candidate_funnel = _v21_candidate_funnel(
                state["buffers"], processed_p90_nanos=proof.calibration.processed_p90_nanos,
                quote_input_lamports=pac_v2_runner._quote_input(now), now=now)
        except (OSError, ValueError, RefusedExecution) as exc:
            state_error = f"PAC V2.1 candidate funnel refused: {str(exc)[:180]}"
    summary = candidate_funnel["summary"]
    v2 = _v2_control_status()
    runner_up = _tmux_running("pac-v21")
    operational = {
        "instrument_id": pac_v21_manifest.INSTRUMENT,
        "status": ("ACTIVE_AUTHENTICATED_PAPER_SCENARIO" if runner_up and state_error is None
                   else "ACTIVE_RUNTIME_REFUSED"),
        "seal": pac_v21_manifest.anchor_status(), "campaign": "ANCHORED_PRE_SAMPLING",
        "activation": "ANCHORED", "dependency_count": len(pac_v21_manifest.DEPENDENCY_PATHS),
        "reaction_p90_nanos": (proof.calibration.processed_p90_nanos if proof else None),
        "processed_samples": (proof.calibration.processed_samples if proof else None),
        "failed_samples": (proof.calibration.failed_samples if proof else None),
        "state": "VALID" if state_error is None else "REFUSED",
        "processes": {"supervisor": bool((v2.get("processes") or {}).get("supervisor")),
                      "feed": bool((v2.get("processes") or {}).get("feed")),
                      "runner": runner_up},
        "solusd": _latest_solusd_status(), "latency_calibration": "CALIBRATED_PROCESSED_RPC",
        "last_status": state.get("last_status"),
        "events_consumed_bytes": (state.get("cursor") or {}).get("event_offset") or 0,
        "active_mint_buffers": summary["buffered_mints"],
        "eligible_feed_events": summary["eligible_events"],
        "scan_interval_millis": int(pac_v21_runner.SCAN_INTERVAL_SECONDS * 1_000),
        "runner_audit": "PASS_CAUSAL_STATE_VALID" if state_error is None else "REFUSED",
        "open_gates": (["100 resolved forward paper positions"]
                       if performance["resolved"] < 100 else []),
    }
    evidence_status = ("VALID_CALIBRATED_PAPER_SCENARIO" if resolved_rows
                       else "ACTIVE_CALIBRATED_SCANNING_NO_FILLS_YET")
    if state_error:
        evidence_status = "REFUSED_LEDGER_OR_RUNTIME_INTEGRITY"
    return {
        "instrument_id": pac_v21_manifest.INSTRUMENT,
        "title": "Single-Shock Payable Absorption · V2.1 (processed-calibrated)",
        "boundary": "PAPER SCENARIO ONLY · NO WALLET · NO ORDERS · NOT A PROFIT CLAIM",
        "evidence_status": evidence_status,
        "integrity_errors": [state_error] if state_error else [],
        "operational": operational,
        "formula": "W≥$10 · full recovery/floor · processed p90 · ≥3 buyers · 6× max(probe, shock)",
        "formula_note": "one payable sell absorbed, reserve recovery survives, then causal paper entry",
        "policy": {"bankroll_index_start": "100.00", "probe_index_points": "10.00",
                   "trail_percent": 12, "coverage_multiple": 6,
                   "max_hold_minutes": 12, "max_concurrent_positions": 1},
        "performance": performance, "open_positions": open_positions,
        "pending_orders": pending_orders, "last_measurement_refusal": None,
        "candidate_funnel": candidate_funnel,
        "activity": list(reversed(activity[-100:])), "ledger_rows": len(rows),
        "challenger": {"instrument_id": "AFTERSHOCK_PAC_V2", "status": v2.get("status"),
                       "note": "V2 remains the frozen two-shock control; V2.1 is now the focused book.",
                       "live": _v2_live(), "processes": v2.get("processes") or {}},
        "successor": (copy.deepcopy(successor_status) if successor_status is not None
                      else _v21_successor_status()),
        "generated_at": time.time(),
    }


def _v23_successor_status() -> dict:
    """Read-only V2.3 authority status; reuses the shared V2.2 low-lag feed. Starts nothing."""
    seal = pac_v23_manifest.anchor_status()

    def artifact(path: pathlib.Path) -> str:
        if not path.exists():
            return "ABSENT"
        return "ANCHORED" if pac_v23_manifest._git_clean(path) else "UNANCHORED"

    campaign = artifact(pac_v23_manifest.CAMPAIGN)
    activation = artifact(pac_v23_manifest.ACTIVATION)
    try:
        health = pac_v22_feed.load_health()
        health_age = max(0, time.time_ns() - health["observed_unix_nanos"])
        feed_status = ("FRESH" if health["status"] == "FRESH"
                       and health_age <= pac_v22_feed.MAX_HEALTH_AGE_NANOS
                       and health["head_slot_lag"] is not None
                       and health["head_slot_lag"] <= pac_v22_feed.MAX_HEAD_SLOT_LAG
                       else "DEGRADED")
    except RefusedExecution as exc:
        health = {"status": "REFUSED", "reason": str(exc)[:180], "head_slot_lag": None,
                  "observed_unix_nanos": None}
        feed_status = "REFUSED"
    if activation == "ANCHORED":
        stage = "ACTIVATED_CROSS_VENUE_PAPER_RUNTIME"
    elif campaign == "ANCHORED":
        stage = "SEALED_CAMPAIGN_ANCHORED_BROADCAST_OWNER_GATED"
    elif seal == "ANCHORED":
        stage = "SEALED_CROSS_VENUE_EXIT_CALIBRATION_CAMPAIGN_REQUIRED"
    else:
        stage = "V23_SEAL_NOT_ANCHORED"
    return {
        "instrument_id": pac_v23_manifest.INSTRUMENT, "status": stage,
        "seal": seal, "campaign": campaign, "activation": activation,
        "dependency_count": len(pac_v23_manifest.DEPENDENCY_PATHS),
        "feed": {**health, "effective_status": feed_status,
                 "process": _tmux_running("pac-v23-feed")},
        "formula": "V2.1 single-shock rule unchanged · low-lag feed · PumpSwap cross-venue exit",
        "boundary": "PAPER ONLY · READ-ONLY PUMPSWAP PRICING · NO WALLET · NO ORDERS",
    }


def _v23_offline_proof() -> pac_v23_runner.RuntimeProof:
    """Validate anchored V2.3 authority without the production live-RPC reread."""
    paths = (pac_v23_manifest.SEAL, pac_v23_manifest.CAMPAIGN,
             pac_v23_manifest.JOURNAL, pac_v23_manifest.SAMPLES,
             pac_v23_manifest.ATTESTATIONS, pac_v23_manifest.ACTIVATION,
             ROOT / ".git" / "HEAD", ROOT / ".git" / "index")
    key = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size)
                if path.exists() else (str(path), None, None) for path in paths)
    with _V23_VIEW_LOCK:
        if _V23_PROOF_CACHE["key"] == key:
            return _V23_PROOF_CACHE["value"]
        with pac_v23_manifest._configured():
            legacy = pac_v23_manifest.legacy
            seal = legacy.verify_seal()
            if (legacy.anchor_status() != "ANCHORED"
                    or not legacy._git_clean(legacy.ACTIVATION)):
                raise RefusedExecution("PAC V2.3 dashboard authority is not anchored")
            activation = legacy._json(legacy.ACTIVATION)
            legacy._activation_body(activation, seal)
            closed = legacy._load_bound_evidence(activation)
            legacy._activation_body(activation, seal, closed)
        proof = pac_v23_runner.RuntimeProof(
            seal["seal_sha256"], activation["activation_unix_nanos"], closed.calibration)
        _V23_PROOF_CACHE.update({"key": key, "value": proof})
        return proof


def v23_snapshot() -> dict:
    """Activated V2.3 cross-venue state/ledger view, reusing the identical V2.1 book validator."""
    global pac_v21_manifest, pac_v21_runner, _v21_offline_proof
    authority = _v23_successor_status()
    with _V23_VIEW_LOCK:
        old_manifest, old_runner, old_proof = (
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof)
        pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
            pac_v23_manifest, pac_v23_runner, _v23_offline_proof)
        try:
            result = v21_snapshot(successor_status=authority)
        finally:
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
                old_manifest, old_runner, old_proof)
    processes = result["operational"]["processes"]
    processes.update({"supervisor": _tmux_running("pac-wd") or _tmux_running("pac-v23"),
                      "feed": _tmux_running("pac-v23-feed"),
                      "runner": _tmux_running("pac-v23")})
    healthy = result["operational"]["state"] == "VALID" and all(processes.values())
    result.update({
        "title": "Single-Shock Payable Absorption · V2.3 (cross-venue PumpSwap exit)",
        "formula": "W≥$10 · full recovery/floor · processed p90 · ≥3 buyers · 6× max(probe, shock)",
        "formula_note": "V2.1 entry + V2.2 low-lag feed unchanged; graduated positions exit honestly on PumpSwap",
        "challenger": {"instrument_id": "AFTERSHOCK_PAC_V22",
                       "status": "RETIRED_PUMP_ONLY_EXIT_MIGRATION_BLIND",
                       "note": "V2.2 was falsified by graduation casualties (see AFTERSHOCK_PAC_V22_EVALUATION.md); superseded by V2.3."},
        "successor": authority,
    })
    result["operational"].update({
        "status": ("ACTIVE_AUTHENTICATED_PAPER_SCENARIO" if healthy
                   else "ACTIVE_RUNTIME_REFUSED"),
        "seal": authority["seal"], "campaign": authority["campaign"],
        "activation": authority["activation"],
        "dependency_count": authority["dependency_count"],
    })
    if result["operational"]["state"] == "VALID":
        result["evidence_status"] = ("VALID_CALIBRATED_PAPER_SCENARIO"
                                     if result["performance"]["resolved"]
                                     else "VALID_CALIBRATED_AWAITING_FIRST_RESOLVED")
    return result


def _v24_successor_status() -> dict:
    """Read-only V2.4 authority status; reuses the shared V2.2 low-lag feed. Starts nothing."""
    seal = pac_v24_manifest.anchor_status()

    def artifact(path: pathlib.Path) -> str:
        if not path.exists():
            return "ABSENT"
        return "ANCHORED" if pac_v24_manifest._git_clean(path) else "UNANCHORED"

    campaign = artifact(pac_v24_manifest.CAMPAIGN)
    activation = artifact(pac_v24_manifest.ACTIVATION)
    try:
        health = pac_v22_feed.load_health()
        health_age = max(0, time.time_ns() - health["observed_unix_nanos"])
        feed_status = ("FRESH" if health["status"] == "FRESH"
                       and health_age <= pac_v22_feed.MAX_HEALTH_AGE_NANOS
                       and health["head_slot_lag"] is not None
                       and health["head_slot_lag"] <= pac_v22_feed.MAX_HEAD_SLOT_LAG
                       else "DEGRADED")
    except RefusedExecution as exc:
        health = {"status": "REFUSED", "reason": str(exc)[:180], "head_slot_lag": None,
                  "observed_unix_nanos": None}
        feed_status = "REFUSED"
    if activation == "ANCHORED":
        stage = "ACTIVATED_HONEST_TOLL_PAPER_RUNTIME"
    elif campaign == "ANCHORED":
        stage = "SEALED_CAMPAIGN_ANCHORED_BROADCAST_OWNER_GATED"
    elif seal == "ANCHORED":
        stage = "SEALED_CROSS_VENUE_EXIT_CALIBRATION_CAMPAIGN_REQUIRED"
    else:
        stage = "V24_SEAL_NOT_ANCHORED"
    return {
        "instrument_id": pac_v24_manifest.INSTRUMENT, "status": stage,
        "seal": seal, "campaign": campaign, "activation": activation,
        "dependency_count": len(pac_v24_manifest.DEPENDENCY_PATHS),
        "feed": {**health, "effective_status": feed_status,
                 "process": _tmux_running("pac-v24-feed")},
        "formula": "V2.1 single-shock rule unchanged · low-lag feed · PumpSwap cross-venue exit",
        "boundary": "PAPER ONLY · READ-ONLY PUMPSWAP PRICING · NO WALLET · NO ORDERS",
    }


def _v24_offline_proof() -> pac_v24_runner.RuntimeProof:
    """Validate anchored V2.4 authority without the production live-RPC reread."""
    paths = (pac_v24_manifest.SEAL, pac_v24_manifest.CAMPAIGN,
             pac_v24_manifest.JOURNAL, pac_v24_manifest.SAMPLES,
             pac_v24_manifest.ATTESTATIONS, pac_v24_manifest.ACTIVATION,
             ROOT / ".git" / "HEAD", ROOT / ".git" / "index")
    key = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size)
                if path.exists() else (str(path), None, None) for path in paths)
    with _V24_VIEW_LOCK:
        if _V24_PROOF_CACHE["key"] == key:
            return _V24_PROOF_CACHE["value"]
        with pac_v24_manifest._configured():
            legacy = pac_v24_manifest.legacy
            seal = legacy.verify_seal()
            if (legacy.anchor_status() != "ANCHORED"
                    or not legacy._git_clean(legacy.ACTIVATION)):
                raise RefusedExecution("PAC V2.4 dashboard authority is not anchored")
            activation = legacy._json(legacy.ACTIVATION)
            legacy._activation_body(activation, seal)
            closed = legacy._load_bound_evidence(activation)
            legacy._activation_body(activation, seal, closed)
        proof = pac_v24_runner.RuntimeProof(
            seal["seal_sha256"], activation["activation_unix_nanos"], closed.calibration)
        _V24_PROOF_CACHE.update({"key": key, "value": proof})
        return proof


def v24_snapshot() -> dict:
    """Activated V2.4 cross-venue state/ledger view, reusing the identical V2.1 book validator."""
    global pac_v21_manifest, pac_v21_runner, _v21_offline_proof
    authority = _v24_successor_status()
    with _V24_VIEW_LOCK:
        old_manifest, old_runner, old_proof = (
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof)
        pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
            pac_v24_manifest, pac_v24_runner, _v24_offline_proof)
        try:
            result = v21_snapshot(successor_status=authority)
        finally:
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
                old_manifest, old_runner, old_proof)
    processes = result["operational"]["processes"]
    processes.update({"supervisor": _tmux_running("pac-wd") or _tmux_running("pac-v24"),
                      "feed": _tmux_running("pac-v24-feed"),
                      "runner": _tmux_running("pac-v24")})
    healthy = result["operational"]["state"] == "VALID" and all(processes.values())
    result.update({
        "title": "Single-Shock Payable Absorption · V2.4 (honest toll · reclaimed ATA rent)",
        "formula": "W≥$10 · full recovery/floor · processed p90 · ≥3 buyers · 6× max(probe, shock)",
        "formula_note": "V2.1 entry + V2.2 low-lag feed unchanged; graduated positions exit honestly on PumpSwap",
        "challenger": {"instrument_id": "AFTERSHOCK_PAC_V22",
                       "status": "RETIRED_PUMP_ONLY_EXIT_MIGRATION_BLIND",
                       "note": "V2.2 was falsified by graduation casualties (see AFTERSHOCK_PAC_V22_EVALUATION.md); superseded by V2.4."},
        "successor": authority,
    })
    result["operational"].update({
        "status": ("ACTIVE_AUTHENTICATED_PAPER_SCENARIO" if healthy
                   else "ACTIVE_RUNTIME_REFUSED"),
        "seal": authority["seal"], "campaign": authority["campaign"],
        "activation": authority["activation"],
        "dependency_count": authority["dependency_count"],
    })
    if result["operational"]["state"] == "VALID":
        result["evidence_status"] = ("VALID_CALIBRATED_PAPER_SCENARIO"
                                     if result["performance"]["resolved"]
                                     else "VALID_CALIBRATED_AWAITING_FIRST_RESOLVED")
    return result


def _v25_successor_status() -> dict:
    """Offline authority/process summary for the activated V2.5 paper successor."""
    try:
        pac_v25_manifest.verify_seal(require_anchor=True)
        seal = "ANCHORED"
    except RefusedExecution:
        seal = "REFUSED"
    activation = ("ANCHORED" if pac_v25_manifest.ACTIVATION.exists()
                  and pac_v25_manifest._anchored(pac_v25_manifest.ACTIVATION) else "ABSENT_OR_DIRTY")
    try:
        health = pac_v22_feed.load_health()
        age = max(0, time.time_ns() - health["observed_unix_nanos"])
        effective = ("FRESH" if health["status"] == "FRESH"
                     and age <= pac_v22_feed.MAX_HEALTH_AGE_NANOS
                     and health["head_slot_lag"] is not None
                     and health["head_slot_lag"] <= pac_v22_feed.MAX_HEAD_SLOT_LAG
                     else "DEGRADED")
    except RefusedExecution as exc:
        health = {"status": "REFUSED", "reason": str(exc)[:180], "head_slot_lag": None}
        effective = "REFUSED"
    return {
        "instrument_id": pac_v25_manifest.INSTRUMENT,
        "status": ("ACTIVATED_PREMISE_BOUND_PAPER_RUNTIME"
                   if seal == activation == "ANCHORED" else "V25_AUTHORITY_REFUSED"),
        "seal": seal, "campaign": "INHERITED_V24_EXECUTOR_ONLY", "activation": activation,
        "dependency_count": len(pac_v25_manifest.DEPENDENCY_PATHS),
        "feed": {**health, "effective_status": effective,
                 "process": _tmux_running("pac-v25-feed")},
        "formula": "paid overshoot · p90 survival · runway · one fill/mint · premise exit",
        "boundary": "PAPER ONLY · NO WALLET · NO ORDERS · NOT A PROFIT CLAIM",
    }


def _v25_offline_proof() -> pac_v25_runner.RuntimeProof:
    paths = (pac_v25_manifest.SEAL, pac_v25_manifest.ACTIVATION,
             pac_v24_manifest.ACTIVATION, ROOT / ".git" / "HEAD", ROOT / ".git" / "index")
    key = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size)
                if path.exists() else (str(path), None, None) for path in paths)
    with _V25_VIEW_LOCK:
        if _V25_PROOF_CACHE["key"] == key:
            return _V25_PROOF_CACHE["value"]
        seal = pac_v25_manifest.verify_seal(require_anchor=True)
        activation = pac_v25_manifest._json(pac_v25_manifest.ACTIVATION)
        body = dict(activation); observed = body.pop("activation_sha256", None)
        if (observed != pac_v25_manifest._sha(pac_v25_manifest._canonical(body))
                or activation.get("seal_sha256") != seal["seal_sha256"]
                or not pac_v25_manifest._anchored(pac_v25_manifest.ACTIVATION)):
            raise RefusedExecution("PAC V2.5 dashboard activation refuses")
        inherited = _v24_offline_proof()
        source_activation = pac_v24_manifest._json(pac_v24_manifest.ACTIVATION)
        if (activation.get("source_activation_sha256")
                != source_activation.get("activation_sha256")
                or activation.get("source_seal_sha256") != inherited.seal_sha256
                or activation.get("processed_p90_nanos")
                != inherited.calibration.processed_p90_nanos):
            raise RefusedExecution("PAC V2.5 dashboard calibration inheritance refuses")
        proof = pac_v25_runner.RuntimeProof(
            seal["seal_sha256"], activation["activation_unix_nanos"], inherited.calibration)
        _V25_PROOF_CACHE.update({"key": key, "value": proof})
        return proof


def _v25_candidate_funnel(state: dict, proof) -> dict:
    """Linear operational view; the sealed runner remains the only qualification authority.

    Re-running the quadratic detector over every 180-second buffer on every HTTP request can block
    the single-threaded read-only dashboard.  This view therefore reports causal traffic and the
    runner's durable pending/open verdict only; it never invents an independent qualification.
    """
    summary = {"buffered_mints": 0, "eligible_events": 0, "pac_core_mints": 0,
               "p90_dwell_mints": 0, "probe_cover_mints": 0,
               "recovery_survival_mints": 0, "buyer_breadth_mints": 0,
               "qualified_mints": 0}
    candidates = []
    now = time.time_ns()
    try:
        q = pac_v2_runner._quote_input(now)
    except (OSError, ValueError, RefusedExecution):
        q = None
    pending_mint = ((state.get("pending_order") or {}).get("mint")
                    if isinstance(state.get("pending_order"), dict) else None)
    open_mint = ((state.get("open_position") or {}).get("mint")
                 if isinstance(state.get("open_position"), dict) else None)
    for mint, raw in (state.get("buffers") or {}).items():
        try:
            events = tuple(pac_v2_runner._event(item) for item in raw)
        except RefusedExecution:
            continue
        if not events:
            continue
        summary["buffered_mints"] += 1
        summary["eligible_events"] += len(events)
        buyers = len({event.trader for event in events if event.side == "buy"})
        if any(event.side == "sell" for event in events):
            summary["pac_core_mints"] += 1
        qualified = mint in {pending_mint, open_mint}
        if qualified:
            summary["p90_dwell_mints"] += 1
            summary["probe_cover_mints"] += 1
            summary["recovery_survival_mints"] += 1
            summary["buyer_breadth_mints"] += 1
            summary["qualified_mints"] += 1
        candidates.append({
            "mint": mint, "event_count": len(events),
            "gate": ("RUNNER_PENDING_OR_OPEN" if qualified
                     else "RUNNER_SCANNING_PAID_OVERSHOOT_P90_RUNWAY"),
            "dwell_nanos": 0, "buyer_breadth": buyers,
            "reserve_cover_lamports": None,
            "dwell_clock": "processed_event_time",
            "age_millis": max(0, (now - events[-1].source_received_unix_nanos) // 1_000_000),
        })
    candidates.sort(key=lambda item: (item["gate"] != "RUNNER_PENDING_OR_OPEN",
                                      item["age_millis"]))
    return {"boundary": "V25_LINEAR_RUNNER_AUTHORITY_DIAGNOSTIC_NOT_A_SECOND_DETECTOR",
            "quote_input_lamports": q, "summary": summary, "candidates": candidates[:100]}


def v25_snapshot() -> dict:
    """V2.5 book using the shared exact ledger validator and a V2.5-specific causal funnel."""
    global pac_v21_manifest, pac_v21_runner, _v21_offline_proof
    authority = _v25_successor_status()
    facade = SimpleNamespace(
        INSTRUMENT=pac_v25_manifest.INSTRUMENT,
        DEPENDENCY_PATHS=pac_v25_manifest.DEPENDENCY_PATHS,
        anchor_status=lambda: authority["seal"])
    with _V25_VIEW_LOCK:
        old_manifest, old_runner, old_proof = (
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof)
        pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
            facade, pac_v25_runner, _v25_offline_proof)
        try:
            result = v21_snapshot(successor_status=authority)
        finally:
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
                old_manifest, old_runner, old_proof)
    processes = result["operational"]["processes"]
    processes.update({"supervisor": _tmux_running("pac-wd") or _tmux_running("pac-v25"),
                      "feed": _tmux_running("pac-v25-feed"),
                      "runner": _tmux_running("pac-v25")})
    healthy = result["operational"]["state"] == "VALID" and all(processes.values())
    try:
        state = json.loads(pac_v25_runner.STATE.read_text())
        proof = _v25_offline_proof()
        result["candidate_funnel"] = _v25_candidate_funnel(state, proof)
    except (OSError, ValueError, RefusedExecution):
        pass
    result.update({
        "title": "Paid Absorption · V2.5 (premise-bound house-edge test)",
        "formula": "sell≥$10 · reserve≥pre-shock+$10 for p90 · ≥3 buyers · 6× cover · 2× runway",
        "formula_note": "one fill per mint; premise-floor break exits immediately; unpriceable curve tests PumpSwap first",
        "challenger": {"instrument_id": "AFTERSHOCK_PAC_V24",
                       "status": "RETIRED_NEGATIVE_TYPICAL_TRADE",
                       "note": "V2.4 stopped at n=10 plus one right-censored open row; no result is copied into V2.5."},
        "successor": authority,
    })
    result["operational"].update({
        "status": "ACTIVE_AUTHENTICATED_PAPER_SCENARIO" if healthy else "ACTIVE_RUNTIME_REFUSED",
        "seal": authority["seal"], "campaign": authority["campaign"],
        "activation": authority["activation"], "dependency_count": authority["dependency_count"],
    })
    if result["operational"]["state"] == "VALID":
        result["evidence_status"] = ("VALID_CALIBRATED_PAPER_SCENARIO"
                                     if result["performance"]["resolved"]
                                     else "ACTIVE_CALIBRATED_SCANNING_NO_FILLS_YET")
    return result


def _v26_successor_status() -> dict:
    """Offline authority/process summary for the activated V2.6 risk-budget challenger."""
    try:
        pac_v26_manifest.verify_seal(require_anchor=True)
        seal = "ANCHORED"
    except RefusedExecution:
        seal = "REFUSED"
    activation = ("ANCHORED" if pac_v26_manifest.ACTIVATION.exists()
                  and pac_v26_manifest._anchored(pac_v26_manifest.ACTIVATION)
                  else "ABSENT_OR_DIRTY")
    try:
        health = pac_v22_feed.load_health()
        age = max(0, time.time_ns() - health["observed_unix_nanos"])
        effective = ("FRESH" if health["status"] == "FRESH"
                     and age <= pac_v22_feed.MAX_HEALTH_AGE_NANOS
                     and health["head_slot_lag"] is not None
                     and health["head_slot_lag"] <= pac_v22_feed.MAX_HEAD_SLOT_LAG
                     else "DEGRADED")
    except RefusedExecution as exc:
        health = {"status": "REFUSED", "reason": str(exc)[:180], "head_slot_lag": None}
        effective = "REFUSED"
    retirement = ("ANCHORED" if V26_RETIREMENT.exists()
                  and not subprocess.run(
                      ("git", "status", "--porcelain", "--", str(V26_RETIREMENT.relative_to(ROOT))),
                      cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip()
                  and subprocess.run(
                      ("git", "ls-files", "--error-unmatch", str(V26_RETIREMENT.relative_to(ROOT))),
                      cwd=ROOT, text=True, capture_output=True, check=False).returncode == 0
                  else "ABSENT_OR_DIRTY")
    status = ("RETIRED_FALSIFIED_EARLY_SAFETY_STOP" if retirement == "ANCHORED"
              else "ACTIVATED_ALL_COST_RISK_PAPER_CHALLENGER"
              if seal == activation == "ANCHORED" else "V26_AUTHORITY_REFUSED")
    return {
        "instrument_id": pac_v26_manifest.INSTRUMENT,
        "status": status, "retirement": retirement,
        "seal": seal, "campaign": "INHERITED_V25_EXECUTOR_ONLY", "activation": activation,
        "dependency_count": len(pac_v26_manifest.DEPENDENCY_PATHS),
        "feed": {**health, "effective_status": effective,
                 "process": _tmux_running("pac-v25-feed")},
        "formula": "V2.5 entry unchanged · full right tail · exact -8% all-cost risk exit",
        "boundary": "PAPER ONLY · NO WALLET · NO ORDERS · NOT A PROFIT CLAIM",
    }


def _v26_offline_proof() -> pac_v26_runner.RuntimeProof:
    paths = (pac_v26_manifest.SEAL, pac_v26_manifest.ACTIVATION,
             pac_v25_manifest.ACTIVATION, ROOT / ".git" / "HEAD", ROOT / ".git" / "index")
    key = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size)
                if path.exists() else (str(path), None, None) for path in paths)
    with _V26_VIEW_LOCK:
        if _V26_PROOF_CACHE["key"] == key:
            return _V26_PROOF_CACHE["value"]
        seal = pac_v26_manifest.verify_seal(require_anchor=True)
        activation = pac_v26_manifest._json(pac_v26_manifest.ACTIVATION)
        body = dict(activation); observed = body.pop("activation_sha256", None)
        if (observed != pac_v26_manifest._sha(pac_v26_manifest._canonical(body))
                or activation.get("seal_sha256") != seal["seal_sha256"]
                or not pac_v26_manifest._anchored(pac_v26_manifest.ACTIVATION)):
            raise RefusedExecution("PAC V2.6 dashboard activation refuses")
        inherited = _v25_offline_proof()
        source_activation = pac_v25_manifest._json(pac_v25_manifest.ACTIVATION)
        if (activation.get("source_activation_sha256")
                != source_activation.get("activation_sha256")
                or activation.get("source_seal_sha256") != inherited.seal_sha256
                or activation.get("processed_p90_nanos")
                != inherited.calibration.processed_p90_nanos):
            raise RefusedExecution("PAC V2.6 dashboard calibration inheritance refuses")
        proof = pac_v26_runner.RuntimeProof(
            seal["seal_sha256"], activation["activation_unix_nanos"], inherited.calibration)
        _V26_PROOF_CACHE.update({"key": key, "value": proof})
        return proof


def v26_snapshot() -> dict:
    """V2.6 forward book with the exact shared ledger validator and causal funnel."""
    global pac_v21_manifest, pac_v21_runner, _v21_offline_proof
    authority = _v26_successor_status()
    facade = SimpleNamespace(
        INSTRUMENT=pac_v26_manifest.INSTRUMENT,
        DEPENDENCY_PATHS=pac_v26_manifest.DEPENDENCY_PATHS,
        anchor_status=lambda: authority["seal"])
    with _V26_VIEW_LOCK:
        old_manifest, old_runner, old_proof = (
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof)
        pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
            facade, pac_v26_runner, _v26_offline_proof)
        try:
            result = v21_snapshot(successor_status=authority)
        finally:
            pac_v21_manifest, pac_v21_runner, _v21_offline_proof = (
                old_manifest, old_runner, old_proof)
    processes = result["operational"]["processes"]
    processes.update({"supervisor": _tmux_running("pac-wd") or _tmux_running("pac-v26"),
                      "feed": _tmux_running("pac-v25-feed"),
                      "runner": _tmux_running("pac-v26")})
    healthy = result["operational"]["state"] == "VALID" and all(processes.values())
    try:
        state = json.loads(pac_v26_runner.STATE.read_text())
        result["candidate_funnel"] = _v25_candidate_funnel(state, _v26_offline_proof())
    except (OSError, ValueError, RefusedExecution):
        pass
    result.update({
        "title": "Paid Absorption · V2.6 (right-tail + all-cost risk budget)",
        "formula": "V2.5 paid absorption · full runner · exact all-cost R≤-8% exit",
        "formula_note": "same entries as V2.5; full-size p90-landed risk exit; promotion must remain positive without its best trade",
        "challenger": {"instrument_id": "AFTERSHOCK_PAC_V25",
                       "status": "ACTIVE_FROZEN_BASELINE",
                       "note": "V2.5 continues unchanged to n=100; no row is copied into V2.6."},
        "successor": authority,
    })
    result["operational"].update({
        "status": "ACTIVE_AUTHENTICATED_PAPER_SCENARIO" if healthy else "ACTIVE_RUNTIME_REFUSED",
        "seal": authority["seal"], "campaign": authority["campaign"],
        "activation": authority["activation"], "dependency_count": authority["dependency_count"],
    })
    if result["operational"]["state"] == "VALID":
        result["evidence_status"] = ("VALID_CALIBRATED_PAPER_SCENARIO"
                                     if result["performance"]["resolved"]
                                     else "ACTIVE_CALIBRATED_SCANNING_NO_FILLS_YET")
    return result


def _entry_arm_stats() -> list:
    """Matched 3-way anti-exhaustion entry comparison: momentum control vs dip-reclaim vs early-curve.
    Each reuses the identical sealed exit engine; only the entry gate differs. Read-only, honest raw
    ledger stats (no promotion gate) so the arms are visible from the moment they fire."""
    arms = [
        ("MOMENTUM", "AFTERSHOCK_PAC_SCALP", "pac-scalp", "buy-the-spike (control · edgeless)"),
        ("DIP-RECLAIM", "AFTERSHOCK_PAC_SCALP_DIP", "pac-scalp-dip", "buy the shakeout-reclaim"),
        ("EARLY-CURVE", "AFTERSHOCK_PAC_SCALP_EARLY", "pac-scalp-early", "buy early on the curve"),
    ]
    out = []
    for name, inst, session, entry in arms:
        led = RESEARCH / f"{inst}_SCENARIO_LEDGER.jsonl"
        st = RESEARCH / f"{inst}_RUNNER_STATE.json"
        entries = resolved = wins = full = 0
        rs = []
        try:
            for line in led.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                k = r.get("kind")
                if k == "entry_decision":
                    entries += 1
                elif k == "resolved":
                    resolved += 1
                    if r.get("unexitable_full_loss"):
                        full += 1
                    num, den = r.get("net_return_num"), r.get("net_return_den")
                    if isinstance(num, int) and isinstance(den, int) and den:
                        rs.append(num / den)
        except OSError:
            pass
        open_n = pending = 0
        last_status = None
        try:
            s = json.loads(st.read_text())
            open_n = len(s.get("open_positions", {}))
            pending = len(s.get("pending_orders", {}))
            last_status = s.get("last_status")
        except (OSError, ValueError):
            pass
        # sum net return in SOL from the ledger's lamport fields
        net_lamports = 0
        try:
            for line in led.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("kind") == "resolved" and isinstance(r.get("net_return_num"), int):
                    net_lamports += r["net_return_num"]
        except OSError:
            pass
        out.append({
            "name": name, "instrument_id": inst, "entry": entry,
            "alive": _tmux_running(session),
            "entries": entries, "resolved": resolved,
            "wins": wins if rs == [] else sum(1 for v in rs if v > 0),
            "win_rate": round(sum(1 for v in rs if v > 0) / len(rs), 3) if rs else None,
            "mean_return_r": round(sum(rs) / len(rs), 4) if rs else None,
            "full_losses": full,
            "net_sol": round(net_lamports / 1e9, 4),
            "open": open_n, "pending": pending, "last_status": last_status,
            "is_control": inst == "AFTERSHOCK_PAC_SCALP",
        })
    return out


def scalp_snapshot() -> dict:
    """Multi-position portfolio convexity scalper view: the book, its ledger, and the mark meter."""
    from . import pac_scalp_manifest as sm
    from . import pac_scalp_runner as sr
    try:
        sm.verify_seal(require_anchor=True)
        seal = "ANCHORED"
    except Exception:  # noqa: BLE001
        seal = "UNANCHORED"
    activation = ("ANCHORED" if sm.ACTIVATION.exists() and sm._anchored(sm.ACTIVATION)
                  else "ABSENT")
    book, pending, last_status = [], 0, None
    try:
        st = json.loads(sr.STATE.read_text())
        last_status = st.get("last_status")
        pending = len(st.get("pending_orders", {}))
        for mint, p in st.get("open_positions", {}).items():
            book.append({"mint": mint, "entry_all_in_lamports": p.get("entry_all_in_lamports"),
                         "peak_net_exit_lamports": p.get("peak_net_exit_lamports", 0)})
    except (OSError, ValueError):
        pass
    resolved = wins = losses = full = 0
    rs, actions = [], {}
    try:
        for line in sr.LEDGER.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("kind") != "resolved":
                continue
            resolved += 1
            actions[r.get("action")] = actions.get(r.get("action"), 0) + 1
            if r.get("unexitable_full_loss"):
                full += 1
            num, den = r.get("net_return_num"), r.get("net_return_den")
            if isinstance(num, int) and isinstance(den, int) and den:
                value = num / den
                rs.append(value)
                wins += value > 0
                losses += value <= 0
    except OSError:
        pass
    mean = sum(rs) / len(rs) if rs else 0.0
    marks = 0
    try:
        marks = sum(1 for _ in sr.MARKS.read_text().splitlines())
    except OSError:
        pass
    processes = {"supervisor": _tmux_running("pac-wd"), "feed": _tmux_running("pac-scalp-feed"),
                 "runner": _tmux_running("pac-scalp")}
    healthy = activation == "ANCHORED" and all(processes.values())
    return {
        "instrument_id": "AFTERSHOCK_PAC_SCALP",
        "title": "Portfolio Convexity Scalper · multi-position (cut losers small, run winners)",
        "formula": "momentum entry · N=4 book · -6% hard stop · widening let-run peak-trail (18/25/35%)",
        "formula_note": "not an edge (entry is proven edgeless); harvests convexity — grab often, cut rugs small, ride runners",
        "boundary": "PAPER SCENARIO ONLY · NO WALLET · NO ORDERS · MEASUREMENT INSTRUMENT (honest EV negative on current evidence)",
        "operational": {
            "status": ("ACTIVE_MEASURING_PAPER_SCENARIO" if healthy else "ACTIVE_RUNTIME_DEGRADED"),
            "seal": seal, "activation": activation, "campaign": "INHERITED_V24_EXECUTOR_ONLY",
            "processes": processes, "last_status": last_status,
            "book_open": len(book), "pending_orders": pending, "marks_logged": marks,
            "reaction_p90_nanos": 3_788_307_712},
        "open_positions": book, "pending_orders": pending,
        "performance": {
            "resolved": resolved, "wins": wins, "losses": losses, "full_losses": full,
            "mean_return_r": round(mean, 4), "sum_return_r": round(sum(rs), 3),
            "win_rate": round(wins / resolved, 3) if resolved else 0.0,
            "exit_actions": actions, "marks_logged": marks},
        "evidence_status": "MEASURING_CONVEXITY_HINGE_FORWARD_NOT_A_PROFIT_CLAIM",
        "entry_arms": _entry_arm_stats(),
        "challenger": {"instrument_id": "AFTERSHOCK_PAC_V25",
                       "status": "RETIRED_EDGELESS_PAC_FAMILY",
                       "note": "PAC shock-absorption is proven edgeless; the convexity scalper supersedes the whole family."},
        "successor": {"instrument_id": "AFTERSHOCK_PAC_SCALP", "status": "ACTIVE_INSTRUMENT"},
    }


def _scalp_active() -> bool:
    try:
        from . import pac_scalp_manifest as sm
        return sm.ACTIVATION.exists() and sm._anchored(sm.ACTIVATION)
    except Exception:  # noqa: BLE001
        return False


def focus_snapshot() -> dict:
    # The multi-position convexity scalper supersedes the whole edgeless PAC family once activated.
    if _scalp_active():
        return scalp_snapshot()
    # Each successor becomes focus only after its separate activation anchor exists.
    v26 = _v26_successor_status()
    if v26.get("status") == "ACTIVATED_ALL_COST_RISK_PAPER_CHALLENGER":
        return v26_snapshot()
    v25 = _v25_successor_status()
    if v25["activation"] == "ANCHORED":
        return v25_snapshot()
    v24 = _v24_successor_status()
    if v24["activation"] == "ANCHORED":
        return v24_snapshot()
    v23 = _v23_successor_status()
    if v23["activation"] == "ANCHORED":
        return v23_snapshot()
    v22 = _v22_successor_status()
    # Once its campaign is anchored, V2.2 is the operational focus even before activation: this
    # exposes fresh feed traffic and the remaining calibration gate instead of silently showing the
    # known-invalid V2.1 clock.  The pre-activation snapshot cannot publish strategy performance.
    if v22["activation"] == "ANCHORED":
        return v22_snapshot()
    if v22["campaign"] == "ANCHORED":
        return v22_feed_snapshot()
    successor = _v21_successor_status()
    if successor["activation"] == "ANCHORED":
        return v21_snapshot(successor_status=v22)
    return v2_snapshot()


def _v2_live() -> dict:
    """Live V2 runner activity read offline from its own state + scenario ledger, so the dashboard shows
    the running challenger doing work (scanning / positions / resolved fills) distinct from the V1 baseline."""
    out = {"last_status": None, "events_consumed_bytes": 0, "open": 0, "pending": 0,
           "resolved": 0, "wins": 0, "losses": 0, "full_losses": 0}
    try:
        s = json.loads((RESEARCH / "AFTERSHOCK_PAC_V2_RUNNER_STATE.json").read_text())
        out["last_status"] = s.get("last_status")
        out["events_consumed_bytes"] = (s.get("cursor") or {}).get("event_offset") or 0
        out["open"] = int(s.get("open_position") is not None)
        out["pending"] = int(s.get("pending_order") is not None)
    except (OSError, ValueError):
        pass
    led = RESEARCH / "AFTERSHOCK_PAC_V2_SCENARIO_LEDGER.jsonl"
    try:
        for line in led.read_text().splitlines() if led.exists() else []:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("kind") != "resolved":
                continue
            out["resolved"] += 1
            if row.get("unexitable_full_loss"):
                out["full_losses"] += 1
            num, den = row.get("net_return_num"), row.get("net_return_den")
            if isinstance(num, int) and isinstance(den, int) and den:
                out["wins" if num > 0 else "losses"] += 1
    except OSError:
        pass
    return out


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2, default=str))
