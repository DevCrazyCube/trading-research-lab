#!/usr/bin/env python3
"""Forward-only PAC launch-window eligibility recorder (paper/data only).

This replaces the invalid LWS-vs-NULL admission measurement.  Every mint is classified once when
the *global* observed head has passed its t0+60 window, independently of portfolio capacity and
without requiring another trade by that mint.  Both treatment flags are emitted in the same immutable
record: ``base_eligible`` is the readable/covered cohort, while ``veto_eligible`` additionally removes
the frozen concentration veto.  UNREADABLE/NO_NET never become entries in either arm.

There is intentionally no position, wallet, signer, order, or return calculation in this process.
It is a causal cohort/data instrument for the next execution experiment, not a trading strategy.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
import pathlib
import tempfile
import time

from .execution import RefusedExecution
from . import pac_lws_feed as feed
from . import pac_lws_runner as legacy
from . import pac_lws_screen as screen


SCHEMA = 1
INSTRUMENT = "AFTERSHOCK_PAC_LWS_ELIGIBILITY_V2"
ROOT = pathlib.Path(__file__).resolve().parents[3]
DATA = ROOT / "research" / "data" / "aftershock" / "pac_lws"
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
STATE = DATA / "eligibility_v2_state.json"
LEDGER = DATA / "eligibility_v2.jsonl"
HEALTH = DATA / "eligibility_v2_health.json"
LOCK = DATA / "eligibility_v2.lock"
RETENTION_NANOS = 180_000_000_000
MARGIN_SLOTS = 2
MAX_CLOSE_OVERSHOOT_SLOTS = 8
COVERAGE_MULTIPLE = legacy.COVERAGE_MULTIPLE
GENESIS = "0" * 64


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _atomic(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical(value) + b"\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _append(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    payload = _canonical(value) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short eligibility append")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if not existed:
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _ledger_index(path: pathlib.Path) -> tuple[dict[str, dict], str, int]:
    """Validate the complete append chain and index mints for crash reconciliation."""
    by_mint: dict[str, dict] = {}; previous = GENESIS; count = 0
    if not path.exists():
        return by_mint, previous, count
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RefusedExecution("eligibility ledger contains malformed JSON") from exc
            body = dict(row); observed = body.pop("record_hash", None)
            mint = body.get("mint")
            if (not isinstance(mint, str) or not mint or mint in by_mint
                    or body.get("previous_record_hash") != previous or observed != _sha(body)):
                raise RefusedExecution("eligibility ledger chain/identity refuses")
            by_mint[mint] = row; previous = observed; count += 1
    return by_mint, previous, count


def _last_complete(path: pathlib.Path) -> tuple[int, dict | None]:
    if not path.exists() or path.stat().st_size == 0:
        return 0, None
    with path.open("rb") as handle:
        end = handle.seek(0, 2); complete_end = end
        handle.seek(end - 1)
        if handle.read(1) != b"\n":
            cursor = end
            while cursor > 0:
                size = min(65_536, cursor); cursor -= size; handle.seek(cursor)
                block = handle.read(size); index = block.rfind(b"\n")
                if index >= 0:
                    complete_end = cursor + index + 1; break
            else:
                return 0, None
        position = complete_end; data = b""
        while position > 0 and data.count(b"\n") < 2:
            size = min(65_536, position); position -= size; handle.seek(position)
            data = handle.read(min(size, complete_end - position)) + data
    lines = [line for line in data.split(b"\n") if line.strip()]
    if not lines:
        return complete_end, None
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RefusedExecution("eligibility cannot anchor a malformed feed tail") from exc
    return complete_end, value


def _seal_state(body: dict) -> dict:
    clean = dict(body); clean.pop("state_sha256", None)
    return {**clean, "state_sha256": _sha(clean)}


def _new_state(now: int, quote_input_lamports: int,
               registry_path: pathlib.Path, events_path: pathlib.Path) -> dict:
    event_offset, tail = _last_complete(events_path)
    if tail is None:
        input_seq, input_hash = -1, GENESIS
    else:
        body = dict(tail); observed = body.pop("event_hash", None)
        if (tail.get("schema") != feed.SCHEMA or tail.get("instrument_id") != feed.INSTRUMENT_ID
                or type(tail.get("seq")) is not int or tail["seq"] < 0
                or not isinstance(observed, str) or observed != feed._canonical_sha(body)):
            raise RefusedExecution("eligibility feed activation anchor refuses")
        input_seq, input_hash = tail["seq"], observed
    return _seal_state({
        "schema": SCHEMA, "instrument_id": INSTRUMENT, "activation_unix_nanos": now,
        "registry_offset": registry_path.stat().st_size if registry_path.exists() else 0,
        "event_offset": event_offset,
        "input_seq": input_seq, "input_hash": input_hash, "last_head_slot": None,
        "quote_input_lamports": quote_input_lamports,
        "pending": {}, "orphans": {}, "last_record_hash": GENESIS, "emitted": 0,
    })


def _load_state(path: pathlib.Path) -> dict:
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("eligibility state is unreadable") from exc
    body = dict(state) if isinstance(state, dict) else {}; observed = body.pop("state_sha256", None)
    required = {"schema", "instrument_id", "activation_unix_nanos", "registry_offset",
                "event_offset", "input_seq", "input_hash", "last_head_slot",
                "quote_input_lamports", "pending", "orphans", "last_record_hash", "emitted",
                "state_sha256"}
    if (not isinstance(state, dict) or set(state) != required or state["schema"] != SCHEMA
            or state["instrument_id"] != INSTRUMENT or type(state["activation_unix_nanos"]) is not int
            or type(state["registry_offset"]) is not int or type(state["event_offset"]) is not int
            or not isinstance(state["pending"], dict) or not isinstance(state["orphans"], dict)
            or type(state["input_seq"]) is not int or not isinstance(state["input_hash"], str)
            or state["last_head_slot"] is not None and type(state["last_head_slot"]) is not int
            or type(state["quote_input_lamports"]) is not int
            or type(state["emitted"]) is not int or not isinstance(state["last_record_hash"], str)
            or observed != _sha(body)):
        raise RefusedExecution("eligibility state schema refuses")
    return state


def _consume(path: pathlib.Path, offset: int, *, now: int | None = None,
             clock_field: str | None = None) -> tuple[list[dict], int]:
    """Consume complete JSONL records only; a writer's partial tail is retried next cycle."""
    if not path.exists():
        return [], offset
    rows, committed = [], offset
    with path.open("rb") as handle:
        size = handle.seek(0, 2)
        if offset < 0 or offset > size:
            raise RefusedExecution(f"{path.name} shrank or cursor escaped the file")
        handle.seek(offset)
        while True:
            start = handle.tell(); raw = handle.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                handle.seek(start); break
            try:
                row = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RefusedExecution(f"{path.name} contains malformed complete JSON") from exc
            if not isinstance(row, dict):
                raise RefusedExecution(f"{path.name} contains a non-object record")
            if clock_field is not None:
                clock = row.get(clock_field)
                if type(clock) is not int:
                    raise RefusedExecution(f"{path.name} record lacks an exact causal clock")
                if now is not None and clock > now:
                    handle.seek(start); break
            rows.append(row); committed = handle.tell()
    return rows, committed


def _event_view(row: dict) -> dict | None:
    mint, received, slot = row.get("mint"), row.get("received_unix_nanos"), row.get("slot")
    if not isinstance(mint, str) or not mint or type(received) is not int or type(slot) is not int:
        return None
    return {"mint": mint, "received_unix_nanos": received, "slot": slot,
            "trader": row.get("trader"), "is_buy": row.get("is_buy"),
            "token_amount": row.get("token_amount"), "post_real_token": row.get("post_real_token"),
            "reserve_delta_tokens": row.get("reserve_delta_tokens"),
            "anchored": row.get("anchored"), "reconciled": row.get("reconciled")}


def _verify_input_event(row: dict, *, previous_seq: int, previous_hash: str) -> None:
    body = dict(row); observed = body.pop("event_hash", None)
    if (row.get("schema") != feed.SCHEMA or row.get("instrument_id") != feed.INSTRUMENT_ID
            or not isinstance(row.get("collector_epoch"), str) or not row["collector_epoch"]
            or row.get("seq") != previous_seq + 1 or row.get("prev_hash") != previous_hash
            or not isinstance(observed, str) or observed != feed._canonical_sha(body)):
        raise RefusedExecution("eligibility input feed sequence/hash/epoch refuses")


def _record(info: dict, events: list[dict], *, head_slot: int, decided_ns: int,
            quote_input_lamports: int, previous_hash: str) -> dict:
    t0 = info["t0_slot"]
    window = [e for e in events if t0 <= e["slot"] <= t0 + screen.K_SLOTS]
    trades = []
    continuity = bool(window)
    for event in window:
        continuity &= event.get("anchored") is True and event.get("reconciled") is True
        if (type(event.get("token_amount")) is int and event["token_amount"] >= 0
                and isinstance(event.get("trader"), str) and event["trader"]):
            trades.append(screen.WindowTrade(
                slot=event["slot"], trader=event["trader"], is_buy=bool(event.get("is_buy")),
                token_amount=event["token_amount"],
                reserve_delta_tokens=event.get("reserve_delta_tokens")))
    verdict = screen.evaluate(trades, t0_slot=t0, dev_wallet=info.get("dev_wallet"))
    latest = max((e for e in events if e["slot"] <= t0 + screen.K_SLOTS
                  and e["received_unix_nanos"] <= decided_ns
                  and type(e.get("post_real_token")) is int),
                 key=lambda e: (e["received_unix_nanos"], e["slot"]), default=None)
    real_quote = None
    if latest is not None:
        real_quote = legacy.reconstruct_reserve_state(latest["post_real_token"]).real_quote
    readable = continuity and verdict.status in {screen.SURVIVED, screen.VETO_CONCENTRATION}
    covered = readable and real_quote is not None \
        and real_quote >= COVERAGE_MULTIPLE * quote_input_lamports
    body = {
        "schema": SCHEMA, "instrument_id": INSTRUMENT, "mint": info["mint"],
        "t0_slot": t0, "window_end_slot": t0 + screen.K_SLOTS,
        "global_head_slot": head_slot, "decided_unix_nanos": decided_ns,
        "create_observed_unix_nanos": info["create_observed_unix_nanos"],
        "window_event_count": len(window), "validated_trade_count": verdict.validated_trades,
        "buyers": verdict.buyers, "filter": verdict.status,
        "top_share_bps": verdict.top_share_bps, "dropped_crosscheck": verdict.dropped_crosscheck,
        "observed_chain_continuous": continuity, "real_quote_lamports": real_quote,
        "quote_input_lamports": quote_input_lamports,
        "coverage_floor_lamports": COVERAGE_MULTIPLE * quote_input_lamports,
        "base_eligible": bool(covered),
        "veto_eligible": bool(covered and verdict.status == screen.SURVIVED),
        "shadow": verdict.shadow, "previous_record_hash": previous_hash,
        "boundary": "OBSERVED_DECODED_CHAIN_ONLY_NO_NETWORK_COMPLETENESS_NO_ORDER_NO_RETURN",
    }
    return {**body, "record_hash": _sha(body)}


def run_once(*, now: int, quote_input_lamports: int, state_path: pathlib.Path = STATE,
             ledger_path: pathlib.Path = LEDGER, health_path: pathlib.Path = HEALTH,
             registry_path: pathlib.Path = feed.CREATION_REGISTRY,
             events_path: pathlib.Path = feed.EVENTS, feed_health_path: pathlib.Path = feed.HEALTH,
             initialize_at_eof: bool = True) -> dict:
    if type(now) is not int or now <= 0 or type(quote_input_lamports) is not int \
            or quote_input_lamports <= 0:
        raise RefusedExecution("eligibility run requires exact positive clock/notional")
    if not state_path.exists():
        state = _new_state(now, quote_input_lamports, registry_path, events_path)
        if not initialize_at_eof:
            state["registry_offset"] = 0; state["event_offset"] = 0
            state = _seal_state(state)
        _atomic(state_path, state)
        return {"schema": SCHEMA, "instrument_id": INSTRUMENT, "status": "INITIALIZED",
                "observed_unix_nanos": now, "global_head_slot": None, "pending": 0,
                "emitted_total": 0, "emitted_cycle": 0, "boundary": "DATA_ONLY_NO_ORDERS"}
    else:
        state = _load_state(state_path)
    if state["quote_input_lamports"] != quote_input_lamports:
        raise RefusedExecution("eligibility notional drift refuses")
    health = feed.load_health(feed_health_path, now=now, require_fresh=True)
    head_slot = health["head_slot"]
    if type(head_slot) is not int:
        raise RefusedExecution("eligibility requires a verified global head slot")

    prior_head = state["last_head_slot"]
    registries, state["registry_offset"] = _consume(
        registry_path, state["registry_offset"], now=now,
        clock_field="create_observed_unix_nanos")
    events, state["event_offset"] = _consume(
        events_path, state["event_offset"], now=now, clock_field="received_unix_nanos")
    for row in registries:
        mint, t0, created = row.get("mint"), row.get("t0_slot"), row.get("create_observed_unix_nanos")
        if (isinstance(mint, str) and mint and type(t0) is int and type(created) is int
                and created >= state["activation_unix_nanos"] and row.get("seedable") is True
                and row.get("create_after_first_trade") is False):
            state["pending"].setdefault(mint, {
                "mint": mint, "t0_slot": t0, "create_observed_unix_nanos": created,
                "dev_wallet": row.get("dev_wallet"), "events": state["orphans"].pop(mint, [])})
    for raw in events:
        _verify_input_event(raw, previous_seq=state["input_seq"], previous_hash=state["input_hash"])
        state["input_seq"], state["input_hash"] = raw["seq"], raw["event_hash"]
        event = _event_view(raw)
        if event is None or event["received_unix_nanos"] < state["activation_unix_nanos"]:
            continue
        mint = event["mint"]
        if mint in state["pending"]:
            state["pending"][mint]["events"].append(event)
        else:
            state["orphans"].setdefault(mint, []).append(event)

    existing, ledger_head, ledger_count = _ledger_index(ledger_path)
    # Append-first/state-second durability: if power failed between those writes, the validated ledger
    # is authoritative and the state catches up without recomputing a new clock/hash for the same mint.
    if state["emitted"] > ledger_count:
        raise RefusedExecution("eligibility state is ahead of its durable ledger")
    state["last_record_hash"] = ledger_head
    state["emitted"] = ledger_count
    emitted = 0
    for mint, info in sorted(list(state["pending"].items()), key=lambda item: item[1]["t0_slot"]):
        if head_slot <= info["t0_slot"] + screen.K_SLOTS + MARGIN_SLOTS:
            continue
        if mint in existing:
            del state["pending"][mint]
            continue
        missed = head_slot > info["t0_slot"] + screen.K_SLOTS + MAX_CLOSE_OVERSHOOT_SLOTS
        row = _record(info, info["events"], head_slot=head_slot, decided_ns=now,
                      quote_input_lamports=quote_input_lamports,
                      previous_hash=state["last_record_hash"])
        if missed:
            body = dict(row); body.pop("record_hash")
            body.update(filter="MISSED_CLOSURE", base_eligible=False, veto_eligible=False,
                        boundary="MISSED_CAUSAL_CLOSURE_NO_ORDER_NO_RETURN")
            row = {**body, "record_hash": _sha(body)}
        _append(ledger_path, row); existing[mint] = row; emitted += 1
        state["last_record_hash"] = row["record_hash"]
        state["emitted"] += 1
        del state["pending"][mint]

    cutoff = now - RETENTION_NANOS
    state["orphans"] = {mint: [e for e in rows if e["received_unix_nanos"] >= cutoff]
                        for mint, rows in state["orphans"].items()
                        if any(e["received_unix_nanos"] >= cutoff for e in rows)}
    state["last_head_slot"] = head_slot
    state = _seal_state(state)
    _atomic(state_path, state)
    summary = {"schema": SCHEMA, "instrument_id": INSTRUMENT, "status": "FRESH",
               "observed_unix_nanos": now, "global_head_slot": head_slot,
               "pending": len(state["pending"]), "emitted_total": state["emitted"],
               "emitted_cycle": emitted, "boundary": "DATA_ONLY_NO_ORDERS"}
    _atomic(health_path, {**summary, "health_sha256": _sha(summary)})
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC LWS slot-independent eligibility recorder")
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--quote-lamports", type=int, default=100_000_000)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("eligibility recorder already running") from exc
        while True:
            try:
                print(json.dumps(run_once(now=time.time_ns(),
                                          quote_input_lamports=args.quote_lamports),
                                 sort_keys=True), flush=True)
            except RefusedExecution as exc:
                print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}), flush=True)
            if args.once:
                return 0
            time.sleep(max(0.1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
