#!/usr/bin/env python3
"""PAC-only causal tape adapter and feed-global warm-up collector.

Old tape rows may seed the immediately preceding reserve state, but can never become decision evidence.
PAC observations require the post-2026-08-28 integer receive clock, explicit public-RPC provenance, and a
transaction signature. This module is read-only; it does not activate an instrument or write a ledger.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from . import ecr, tape
from .execution import ObservedEvent, RefusedExecution, ReserveState, Source, validate_stream


PAC_SOURCE = "public_rpc_processed"


def _state(line: dict) -> ReserveState:
    try:
        kernel = ecr.reserves_from_tape({
            "v_sol": line["v_sol"], "v_tokens": line["v_tokens"],
            "pool": line.get("pool", "pump"),
        })
        return ReserveState(
            virtual_quote=int(kernel["virtual_quote"]),
            virtual_token=int(kernel["virtual_token"]),
            real_quote=int(kernel["real_quote"]),
            real_token=int(kernel["real_token"]),
            complete=bool(kernel["complete"]),
        )
    except (KeyError, TypeError, ValueError, RefusedExecution) as exc:
        raise RefusedExecution("PAC tape row has invalid reserves") from exc


def causal_events_from_lines(lines: list[dict], *, after_unix_nanos: int) -> list[ObservedEvent]:
    if type(after_unix_nanos) is not int or after_unix_nanos < 0:
        raise RefusedExecution("PAC tape boundary must be an exact non-negative clock")
    if not isinstance(lines, list):
        raise RefusedExecution("PAC tape lines must be a list")
    events: list[ObservedEvent] = []
    previous_state = None
    mint = None
    for line in lines:
        if not isinstance(line, dict):
            raise RefusedExecution("PAC tape row must be an object")
        post = _state(line)
        pre = previous_state or post
        previous_state = post
        received = line.get("received_unix_nanos")
        if received is None:
            continue  # legacy row can establish prior state, never evidence
        if type(received) is not int or received < 0:
            raise RefusedExecution("PAC tape receive clock must be an exact non-negative integer")
        if received <= after_unix_nanos:
            continue
        row_mint = line.get("mint")
        signature = line.get("sig")
        if (not isinstance(row_mint, str) or not row_mint
                or not isinstance(signature, str) or not signature
                or line.get("observation_source") != PAC_SOURCE):
            raise RefusedExecution("PAC evidence lacks mint/signature/public-RPC provenance")
        if mint is None:
            mint = row_mint
        elif row_mint != mint:
            raise RefusedExecution("one PAC mint stream cannot mix mints")
        evidence_body = {key: line.get(key) for key in tape.TAPE_FIELDS}
        digest = hashlib.sha256(json.dumps(
            evidence_body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        events.append(ObservedEvent(
            mint=row_mint, observation_unix_nanos=received,
            pre_state=pre, post_state=post, source=Source.PUBLIC_RPC_PROCESSED,
            evidence_sha=digest, coord=None))
    if events:
        validate_stream(events)
    return events


def mint_events(mint: str, *, after_unix_nanos: int) -> list[ObservedEvent]:
    if not isinstance(mint, str) or not mint:
        raise RefusedExecution("PAC mint is required")
    return causal_events_from_lines(tape.read_tape(mint), after_unix_nanos=after_unix_nanos)


def collect_global_warmup(*, after_unix_nanos: int, minimum_events: int,
                          minimum_span_nanos: int) -> list[ObservedEvent]:
    for label, value, minimum in (
            ("minimum_events", minimum_events, 1),
            ("minimum_span_nanos", minimum_span_nanos, 0)):
        if type(value) is not int or value < minimum:
            raise RefusedExecution(f"PAC {label} is invalid")
    collected: list[ObservedEvent] = []
    for path in tape.TAPE_DIR.glob("*.jsonl"):
        if path.name.startswith("_"):
            continue
        mint = path.stem
        collected.extend(mint_events(mint, after_unix_nanos=after_unix_nanos))
    collected.sort(key=lambda event: event.observation_unix_nanos)
    if any(right.observation_unix_nanos <= left.observation_unix_nanos
           for left, right in zip(collected, collected[1:])):
        raise RefusedExecution("PAC global warm-up has duplicate/backward receive clocks")
    selected: list[ObservedEvent] = []
    for event in collected:
        selected.append(event)
        if (len(selected) >= minimum_events
                and selected[-1].observation_unix_nanos - selected[0].observation_unix_nanos
                >= minimum_span_nanos):
            return selected
    raise RefusedExecution("PAC feed-global warm-up is not complete")
