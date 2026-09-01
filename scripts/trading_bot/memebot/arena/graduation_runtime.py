#!/usr/bin/env python3
"""Read-only causal PumpSwap paper runtime for MEMEBOT_GRAD_V1."""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import pathlib
import sys
import time

from . import exit_engine as EX
from . import runtime as RT
from . import manifest as MF
from .arms import bundle_momentum as BM
from .arms import graduation as G
from .. import ws_data
from ...aftershock import solusd_recorder
from ...aftershock.execution import q_lamports_for_usd
from ...aftershock.execution import PriceUnavailable
from ...aftershock.pac_v2_pumpswap import (
    PumpSwapProvider, PumpSwapUnavailable, observation_to_dict, sell_quote)

INSTRUMENT = G.ARM.instrument
POLL_SECONDS = 5
STATE_SCHEMA = 1


def _path() -> pathlib.Path:
    return RT.DATA / INSTRUMENT / "state.json"


def _new_state(authority: dict) -> dict:
    return {"schema": STATE_SCHEMA, "instrument": INSTRUMENT,
            "activation_unix_nanos": authority["activated_unix_nanos"],
            "tape_cursor": authority["tape_sequence"],
            "tape_head": authority["tape_head_sha256"], "tape_offset": authority["tape_offset"],
            "mints": {}, "candidates": {}, "open": {}, "sampled_mints": {},
            "pending_ledger": [], "census": {}, "cycles": 0}


def _load() -> tuple[dict, bool]:
    authority = MF.require_activation(G.ARM)
    path = _path(); fresh = not path.exists(); state = RT._load(path, _new_state(authority))
    required = {"schema", "instrument", "activation_unix_nanos", "tape_cursor", "tape_head",
                "tape_offset", "mints", "candidates", "open", "sampled_mints",
                "pending_ledger", "census", "cycles"}
    if (not isinstance(state, dict) or set(state) != required or state["schema"] != STATE_SCHEMA
            or state["instrument"] != INSTRUMENT):
        raise RuntimeError("graduation state refuses")
    if state["activation_unix_nanos"] != authority["activated_unix_nanos"]:
        raise RuntimeError("graduation state activation does not match authority")
    return state, fresh


def _save(state: dict) -> None:
    RT._save(_path(), state)


def _inc(state: dict, name: str) -> None:
    state["census"][name] = state["census"].get(name, 0) + 1


def _drain(state: dict) -> None:
    ledger = RT._ledger(G.ARM)
    while state["pending_ledger"]:
        event = state["pending_ledger"][0]
        if event["kind"] == "opened":
            ledger.append_opened(event["row"])
        elif event["kind"] == "resolved":
            ledger.append_resolved(event["row"]); state["open"].pop(event["row"]["mint"], None)
        elif event["kind"] == "void":
            ledger.append_void(event["row"])
        else:
            raise RuntimeError("graduation pending kind refuses")
        state["pending_ledger"].pop(0); _save(state)


def _rows(state: dict) -> list[tuple[dict, int]]:
    path = ws_data.TRADE_BUFFER_PATH
    if not path.exists():
        if state["tape_offset"]:
            raise RuntimeError("graduation tape disappeared")
        return []
    if path.stat().st_size < state["tape_offset"]:
        raise RuntimeError("graduation tape truncated")
    output = []
    with path.open("rb") as handle:
        handle.seek(state["tape_offset"])
        while True:
            start = handle.tell(); raw = handle.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                handle.seek(start); break
            row = json.loads(raw); output.append((row, handle.tell()))
    return output


def _created(state: dict) -> set[str]:
    return {row["mint"] for row in ws_data.read_buffer()
            if isinstance(row.get("mint"), str) and type(row.get("received_unix_nanos")) is int
            and row["received_unix_nanos"] > state["activation_unix_nanos"]}


def _migration_slot(provider: PumpSwapProvider, candidate: dict) -> int | None:
    signature = candidate.get("signature")
    if not isinstance(signature, str) or not signature:
        return None
    body = {"jsonrpc": "2.0", "id": 91, "method": "getTransaction",
            "params": [signature, {"encoding": "json", "commitment": "confirmed",
                                    "maxSupportedTransactionVersion": 0}]}
    response, status, outcome = provider._rpc(body)
    if outcome != "RETRIEVED" or status != 200 or not isinstance(response, dict):
        return None
    result = response.get("result")
    slot = result.get("slot") if isinstance(result, dict) else None
    return slot if type(slot) is int and slot > 0 else None


def _void(state: dict, mint: str, reason: str, candidate: dict) -> None:
    void_id = RT._sha({"instrument": INSTRUMENT, "mint": mint, "reason": reason,
                       "migration": candidate.get("record_sha256")})
    state["pending_ledger"].append({"kind": "void", "row": {
        "void_id": void_id, "mint": mint, "reason": reason,
        "decision_unix_nanos": candidate["received_unix_nanos"]}})
    state["candidates"].pop(mint, None); _inc(state, reason); _save(state); _drain(state)


def _open_candidate(state: dict, mint: str, candidate: dict, provider: PumpSwapProvider) -> None:
    now_ns = time.time_ns()
    if candidate.get("migration_slot") is None:
        candidate["migration_slot"] = _migration_slot(provider, candidate)
        if candidate["migration_slot"] is None:
            if now_ns - candidate["received_unix_nanos"] > G.MIGRATION_CONFIRM_TIMEOUT_S * 1e9:
                _void(state, mint, "UNCONFIRMED_MIGRATION", candidate)
            return
    try:
        observation = provider.capture(mint, candidate["migration_slot"] + G.LATENCY_SLOTS)
    except PumpSwapUnavailable:
        if now_ns - candidate["received_unix_nanos"] > G.POOL_CONFIRM_TIMEOUT_S * 1e9:
            _void(state, mint, "UNCONFIRMED_LIVE_POOL", candidate)
        return
    decision_ns = observation.response_received_unix_nanos
    usd = solusd_recorder.latest_observation(decision_unix_nanos=decision_ns)
    q = q_lamports_for_usd(G.SIZE_USD, usd, decision_unix_nanos=decision_ns,
                           max_staleness_nanos=solusd_recorder.MAX_LOCAL_AGE_NANOS)
    quote = G.buy_quote(q, observation.reserves)
    entry_all_in = q + G.ENTRY_ROUTE_COST_LAMPORTS + G.ATA_RENT_LAMPORTS
    entry_id = RT._sha({"instrument": INSTRUMENT, "mint": mint,
                        "migration": candidate["record_sha256"],
                        "pool_evidence": observation.raw_response_sha256})
    cohort = candidate["cohort"]
    raw = {"mint": mint, "entry_id": entry_id, "cohort": cohort,
           "entry_day": RT._day(decision_ns / 1e9), "entry_unix_nanos": decision_ns,
           "entry_all_in_lamports": entry_all_in, "quote_input_lamports": q,
           "token_atoms": quote["base_out_atoms"], "pool": observation.pool,
           "last_slot": observation.context_slot, "peak_equity_lamports": 0,
           "pending_exit": None, "unavailable_polls": 0, "last_gross_exit_lamports": 0,
           "last_evidence_sha256": observation.raw_response_sha256}
    state["open"][mint] = raw; state["sampled_mints"][mint] = entry_id
    state["candidates"].pop(mint, None)
    state["pending_ledger"].append({"kind": "opened", "row": {
        "entry_id": entry_id, "mint": mint, "entry_day": raw["entry_day"],
        "entry_price": q / quote["base_out_atoms"], "decision_unix_nanos": candidate["received_unix_nanos"],
        "landing_unix_nanos": decision_ns, "evidence_sha256": candidate["record_sha256"],
        "landing_evidence_sha256": observation.raw_response_sha256,
        "gate_tier": cohort, "basis": "pumpswap_exact_cp"}})
    _save(state); _drain(state)


def _terminal(state: dict, raw: dict, *, reason: str, equity: int,
              evidence_sha256: str) -> None:
    entry = raw["entry_all_in_lamports"]
    net_num = equity - entry
    resolution_id = RT._sha({"entry_id": raw["entry_id"], "reason": reason,
                             "evidence": evidence_sha256})
    row = {"resolution_id": resolution_id, "entry_id": raw["entry_id"], "mint": raw["mint"],
           "entry_day": raw["entry_day"], "cohort": raw["cohort"], "reason": reason,
           "basis": "pumpswap_exact_cp", "entry_price": 1.0,
           "exit_price": equity / entry,
           "gross_return": (raw.get("last_gross_exit_lamports", 0)
                            / raw["quote_input_lamports"] - 1.0),
           "net_return": net_num / entry, "net_marginal": None,
           "real_reserve_bound_hit": equity == 0,
           "held_s": int((time.time_ns() - raw["entry_unix_nanos"]) / 1e9),
           "decomposition": {"entry_all_in_lamports": entry, "terminal_equity_lamports": equity}}
    state["pending_ledger"].append({"kind": "resolved", "row": row}); _save(state); _drain(state)


def _service_open(state: dict, mint: str, raw: dict, provider: PumpSwapProvider) -> None:
    pending = raw.get("pending_exit")
    minimum = pending["target_slot"] if pending else raw["last_slot"]
    try:
        observation = provider.capture(mint, minimum)
        quote = sell_quote(raw["token_atoms"], observation.reserves)
        raw["unavailable_polls"] = 0
    except (PumpSwapUnavailable, PriceUnavailable):
        if (not pending and time.time_ns() - raw["entry_unix_nanos"] >= G.HORIZON_S * 1e9):
            raw["pending_exit"] = {"reason": "HORIZON",
                "target_slot": raw["last_slot"] + G.LATENCY_SLOTS,
                "trigger_evidence_sha256": raw["last_evidence_sha256"]}
            pending = raw["pending_exit"]
        raw["unavailable_polls"] += 1
        if pending and raw["unavailable_polls"] >= G.UNAVAILABLE_POLLS:
            _terminal(state, raw, reason="UNAVAILABLE_FULL_LOSS", equity=0,
                      evidence_sha256=pending["trigger_evidence_sha256"])
        return
    raw["last_gross_exit_lamports"] = quote["net_quote_lamports"]
    raw["last_evidence_sha256"] = observation.raw_response_sha256
    equity = (quote["net_quote_lamports"] - G.EXIT_ROUTE_COST_LAMPORTS
              + G.ATA_RENT_LAMPORTS - G.ATA_CLOSE_COST_LAMPORTS)
    equity = max(0, equity)
    raw["last_slot"] = observation.context_slot
    raw["peak_equity_lamports"] = max(raw["peak_equity_lamports"], equity)
    if pending:
        _terminal(state, raw, reason=pending["reason"], equity=equity,
                  evidence_sha256=observation.raw_response_sha256)
        return
    net = (equity - raw["entry_all_in_lamports"]) / raw["entry_all_in_lamports"]
    mark = equity / raw["entry_all_in_lamports"]
    position = EX.Position(mint, INSTRUMENT, "causal_cp", 1.0,
                           raw["entry_unix_nanos"] / 1e9,
                           peak=raw["peak_equity_lamports"] / raw["entry_all_in_lamports"])
    reason = EX.exit_signal(position, mark, time.time(), all_cost_net_return=net)
    if time.time_ns() - raw["entry_unix_nanos"] >= G.HORIZON_S * 1e9:
        reason = reason or "HORIZON"
    if reason:
        raw["pending_exit"] = {"reason": reason,
            "target_slot": observation.context_slot + G.LATENCY_SLOTS,
            "trigger_evidence_sha256": observation.raw_response_sha256}


def _cycle_unlocked(provider: PumpSwapProvider) -> dict:
    if not ws_data.trade_data_authorized():
        raise RuntimeError("graduation arm refuses without PUMPPORTAL_DATA_API_KEY")
    state, fresh = _load(); RT._ledger(G.ARM).ensure_genesis(); _drain(state)
    created = _created(state)
    for row, end in _rows(state):
        body = dict(row); observed = body.pop("record_sha256", None)
        if (row.get("sequence") != state["tape_cursor"] + 1
                or row.get("previous_record_sha256") != state["tape_head"]
                or observed != hashlib.sha256(ws_data._canonical(body)).hexdigest()):
            raise RuntimeError("graduation tape continuity refuses")
        mint = row["mint"]
        if mint in created:
            bucket = state["mints"].setdefault(mint, [])
            if row.get("tx_type") in {"buy", "sell"} and len(bucket) < 2000:
                bucket.append(row)
            if (row.get("tx_type") in {"migrate", "migration"}
                    and mint not in state["sampled_mints"] and mint not in state["candidates"]):
                cohort = "PROXY_PASS" if BM.first_six_signal(bucket) else "CONTROL_PROXY_FAIL"
                state["candidates"][mint] = {"received_unix_nanos": row["received_unix_nanos"],
                    "record_sha256": row["record_sha256"], "signature": row.get("signature"),
                    "cohort": cohort, "migration_slot": None}
        state["tape_cursor"], state["tape_head"], state["tape_offset"] = (
            row["sequence"], row["record_sha256"], end)
        _save(state)
    for mint, candidate in list(state["candidates"].items()):
        _open_candidate(state, mint, candidate, provider)
    for mint, raw in list(state["open"].items()):
        _service_open(state, mint, raw, provider)
    state["cycles"] += 1; _save(state)
    return {"fresh": fresh, "candidates": len(state["candidates"]), "open": len(state["open"]),
            "census": state["census"]}


def cycle(provider: PumpSwapProvider | None = None) -> dict:
    provider = provider or PumpSwapProvider(
        exchange_path=RT.DATA / INSTRUMENT / "pumpswap_exchanges.jsonl")
    lock_path = RT.DATA / INSTRUMENT / "runtime.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another graduation runtime owns the instrument") from exc
        return _cycle_unlocked(provider)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN); os.close(descriptor)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]; once = "--once" in argv
    while True:
        try:
            print(json.dumps({"instrument": INSTRUMENT, **cycle()}, sort_keys=True), flush=True)
        except Exception as exc:
            print(json.dumps({"instrument": INSTRUMENT, "error": str(exc)[:240]}), flush=True)
        if once:
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
