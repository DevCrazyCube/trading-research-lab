#!/usr/bin/env python3
"""Event-driven causal paper runtime for BUNDLE_MOMENTUM_V1. No signer or order path."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
import pathlib
import sys
import time

from . import exit_engine as EX
from . import fill as F
from . import runtime as RT
from . import manifest as MF
from .arms import bundle_momentum as BM
from .chainledger import ChainLedger
from .. import ws_data
from ...aftershock.execution import PriceUnavailable
from ...aftershock.pac_v2_pumpswap import PumpSwapProvider, PumpSwapUnavailable, sell_quote

POLL_SECONDS = 0.25
STATE_SCHEMA = 1
INSTRUMENT = BM.ARM.instrument


def _state_path() -> pathlib.Path:
    return RT.DATA / INSTRUMENT / "state.json"


def _ledger() -> ChainLedger:
    return RT._ledger(BM.ARM)


def _new_state(authority: dict) -> dict:
    return {"schema": STATE_SCHEMA, "instrument": INSTRUMENT,
            "activation_unix_nanos": authority["activated_unix_nanos"],
            "tape_cursor": authority["tape_sequence"],
            "tape_head": authority["tape_head_sha256"], "tape_offset": authority["tape_offset"],
            "mints": {}, "pending_entries": {}, "open": {},
            "sampled_mints": {}, "pending_ledger": [], "voids": 0, "cycles": 0}


def _load_state() -> tuple[dict, bool]:
    authority = MF.require_activation(BM.ARM)
    path = _state_path(); fresh = not path.exists()
    state = RT._load(path, _new_state(authority))
    required = {"schema", "instrument", "activation_unix_nanos", "tape_cursor", "tape_head",
                "tape_offset",
                "mints", "pending_entries", "open", "sampled_mints", "pending_ledger",
                "voids", "cycles"}
    if (not isinstance(state, dict) or set(state) != required or state["schema"] != STATE_SCHEMA
            or state["instrument"] != INSTRUMENT or type(state["tape_cursor"]) is not int
            or type(state["tape_offset"]) is not int or state["tape_offset"] < 0
            or not all(isinstance(state[k], dict) for k in (
                "mints", "pending_entries", "open", "sampled_mints"))
            or not isinstance(state["pending_ledger"], list)):
        raise RuntimeError("bundle runtime state refuses")
    if state["activation_unix_nanos"] != authority["activated_unix_nanos"]:
        raise RuntimeError("bundle state activation does not match authority")
    return state, fresh


def _save(state: dict) -> None:
    RT._save(_state_path(), state)


def _drain(state: dict) -> None:
    ledger = _ledger()
    while state["pending_ledger"]:
        event = state["pending_ledger"][0]
        if event["kind"] == "opened":
            ledger.append_opened(event["row"])
        elif event["kind"] == "resolved":
            ledger.append_resolved(event["row"])
            state["open"].pop(event["row"]["mint"], None)
        elif event["kind"] == "void":
            ledger.append_void(event["row"])
        else:
            raise RuntimeError("bundle pending ledger kind refuses")
        state["pending_ledger"].pop(0); _save(state)


def _decimal(row: dict, key: str) -> Decimal:
    try:
        value = Decimal(row[key])
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise RuntimeError(f"bundle reserve {key} invalid") from exc
    if not value.is_finite() or value <= 0:
        raise RuntimeError(f"bundle reserve {key} nonpositive")
    return value


def _reserves(row: dict) -> tuple[float, float, float]:
    virtual_sol = _decimal(row, "virtual_sol")
    virtual_tokens = _decimal(row, "virtual_tokens")
    return float(virtual_sol), float(virtual_tokens), float(max(Decimal(0), virtual_sol - Decimal(30)))


def _entry_token_atoms(reserves: tuple[float, float, float]) -> int:
    sol, tokens = (Decimal(str(reserves[0])), Decimal(str(reserves[1])))
    effective = Decimal(str(BM.SIZE_SOL)) * (Decimal(1) - Decimal(str(F.TOLL_BUY)))
    output = tokens * effective / (sol + effective)
    atoms = int(output * Decimal(1_000_000))
    if atoms <= 0:
        raise RuntimeError("bundle entry token output is unavailable")
    return atoms


def _created_after_activation(state: dict) -> set[str]:
    output = set()
    for row in ws_data.read_buffer():
        ns = row.get("received_unix_nanos")
        if type(ns) is int and ns > state["activation_unix_nanos"] and isinstance(row.get("mint"), str):
            output.add(row["mint"])
    return output


def _position(mint: str, raw: dict, variant: str) -> EX.Position:
    value = raw[variant]
    return EX.Position(mint, INSTRUMENT, "causal_cp", raw["entry_price"],
                       raw["opened_unix_nanos"] / 1e9, peak=value["peak"],
                       peak_net_return=value.get("peak_net_return", -1.0),
                       size_sol=BM.SIZE_SOL, entry_reserves=tuple(raw["entry_reserves"]))


def _signal_variant(raw: dict, variant: str, row: dict) -> None:
    value = raw[variant]
    if value.get("result") is not None or value.get("pending") is not None:
        return
    reserves = _reserves(row)
    current = F.causal_fill_cp(tuple(raw["entry_reserves"]), reserves[:2], BM.SIZE_SOL,
                               latency_s=BM.LATENCY_S,
                               real_sol_withdrawable_at_exit=reserves[2])
    p = _position(raw["mint"], raw, variant)
    mark = reserves[0] / reserves[1]
    if variant == "primary":
        reason = EX.exit_signal(p, mark, row["received_unix_nanos"] / 1e9,
                                all_cost_net_return=current.net_return)
    else:
        p.peak = max(p.peak, mark)
        reason = "HARD_STOP" if current.net_return <= -EX.HARD_STOP else None
        if reason is None and mark <= p.peak * 0.90:
            reason = "FLAT_10_TRAIL"
        if reason is None and row["received_unix_nanos"] - raw["opened_unix_nanos"] > EX.HORIZON_S * 1e9:
            reason = "HORIZON"
    value["peak"], value["peak_net_return"] = p.peak, p.peak_net_return
    if reason:
        value["pending"] = {"reason": reason,
                            "target_ns": row["received_unix_nanos"] + int(BM.LATENCY_S * 1e9),
                            "deadline_ns": row["received_unix_nanos"]
                            + int((BM.LATENCY_S + BM.EXIT_BOUNDARY_TIMEOUT_S) * 1e9),
                            "trigger_record_sha256": row["record_sha256"]}


def _land_variant(raw: dict, variant: str, row: dict) -> None:
    value = raw[variant]; pending = value.get("pending")
    if not pending or row["received_unix_nanos"] < pending["target_ns"]:
        return
    reserves = _reserves(row)
    p = _position(raw["mint"], raw, variant)
    result = EX.resolve(p, pending["reason"], exit_reserves=reserves[:2],
                        real_sol_withdrawable=reserves[2], latency_s=BM.LATENCY_S,
                        now_ts=row["received_unix_nanos"] / 1e9)
    result["landing_record_sha256"] = row["record_sha256"]
    value["result"], value["pending"] = result, None


def _maybe_finish(state: dict, mint: str) -> None:
    raw = state["open"].get(mint)
    if not raw or any(raw[v].get("result") is None for v in ("primary", "comparator")):
        return
    primary, comparator = raw["primary"]["result"], raw["comparator"]["result"]
    resolution_id = RT._sha({"entry_id": raw["entry_id"],
                             "primary": primary["landing_record_sha256"],
                             "comparator": comparator["landing_record_sha256"]})
    row = {**primary, "entry_id": raw["entry_id"], "resolution_id": resolution_id,
           "entry_day": raw["entry_day"], "minutes_since_first_seen": 0,
           "comparator_net_return": comparator["net_return"],
           "comparator_reason": comparator["reason"],
           "top_share_bps": raw["top_share_bps"], "clump_ns": raw["clump_ns"]}
    state["pending_ledger"].append({"kind": "resolved", "row": row}); _save(state); _drain(state)


def _migration_result(raw: dict, variant: str, observation) -> dict:
    quote = sell_quote(raw["token_atoms"], observation.reserves)
    exit_sol = quote["net_quote_lamports"] / 1_000_000_000
    fixed_sol = 2_250_000 / 1_000_000_000
    net = (exit_sol - BM.SIZE_SOL - fixed_sol) / BM.SIZE_SOL
    tokens = raw["token_atoms"] / 1_000_000
    return {"mint": raw["mint"], "arm": INSTRUMENT, "reason": "MIGRATION_EXIT",
            "basis": "pumpswap_exact_cp", "entry_price": raw["entry_price"],
            "exit_price": (exit_sol / tokens if tokens else 0.0),
            "gross_return": round(exit_sol / BM.SIZE_SOL - 1.0, 6),
            "net_return": round(net, 6), "net_marginal": None,
            "real_reserve_bound_hit": False,
            "held_s": int((observation.response_received_unix_nanos
                           - raw["opened_unix_nanos"]) / 1e9),
            "decomposition": {"venue": "PUMPSWAP", "variant": variant,
                              "quote": quote, "fixed_cost_sol": fixed_sol},
            "landing_record_sha256": observation.raw_response_sha256}


def _service_migration(state: dict, mint: str, raw: dict, provider: PumpSwapProvider,
                       now_ns: int) -> None:
    pending = raw.get("migration")
    if not pending or now_ns < pending["target_ns"]:
        return
    try:
        observation = provider.capture(mint, pending["minimum_context_slot"])
        for variant in ("primary", "comparator"):
            if raw[variant].get("result") is None:
                raw[variant]["result"] = _migration_result(raw, variant, observation)
                raw[variant]["pending"] = None
        raw["migration"] = None
        _maybe_finish(state, mint)
    except (PumpSwapUnavailable, PriceUnavailable):
        if now_ns < pending["deadline_ns"]:
            return
        for variant in ("primary", "comparator"):
            if raw[variant].get("result") is None:
                p = _position(mint, raw, variant)
                result = EX.resolve(p, "RUG_UNPRICED", latency_s=BM.LATENCY_S,
                                    now_ts=now_ns / 1e9)
                result["landing_record_sha256"] = pending["trigger_record_sha256"]
                raw[variant]["result"], raw[variant]["pending"] = result, None
        raw["migration"] = None
        _maybe_finish(state, mint)


def _process_row(state: dict, row: dict, created: set[str]) -> None:
    mint = row["mint"]
    if mint not in created:
        state["tape_cursor"], state["tape_head"] = row["sequence"], row["record_sha256"]
        _save(state); return
    raw = state["open"].get(mint)
    if raw is not None:
        raw["last_event_ns"] = row["received_unix_nanos"]
        raw["last_record_sha256"] = row["record_sha256"]
        if row.get("tx_type") in {"migrate", "migration"}:
            raw["migration"] = {"target_ns": row["received_unix_nanos"] + int(BM.LATENCY_S * 1e9),
                                "deadline_ns": row["received_unix_nanos"]
                                + int((BM.LATENCY_S + BM.EXIT_BOUNDARY_TIMEOUT_S) * 1e9),
                                "minimum_context_slot": (row.get("slot")
                                                         if type(row.get("slot")) is int else 0),
                                "trigger_record_sha256": row["record_sha256"]}
            state["tape_cursor"], state["tape_head"] = row["sequence"], row["record_sha256"]
            _save(state)
            return
        raw["last_reserves"] = list(_reserves(row))
        for variant in ("primary", "comparator"):
            _land_variant(raw, variant, row)
            _signal_variant(raw, variant, row)
        _maybe_finish(state, mint)
    pending = state["pending_entries"].get(mint)
    if pending is not None and row["received_unix_nanos"] >= pending["target_ns"]:
        reserves = _reserves(row)
        entry_math = F.causal_fill_cp(reserves[:2], reserves[:2], BM.SIZE_SOL,
                                      latency_s=BM.LATENCY_S,
                                      real_sol_withdrawable_at_exit=reserves[2])
        entry_id = pending["entry_id"]
        state["open"][mint] = {"mint": mint, "entry_id": entry_id,
            "entry_reserves": list(reserves[:2]), "entry_price": entry_math.entry_price,
            "opened_unix_nanos": row["received_unix_nanos"], "entry_day": RT._day(time.time()),
            "last_event_ns": row["received_unix_nanos"], "last_reserves": list(reserves),
            "last_record_sha256": row["record_sha256"],
            "token_atoms": _entry_token_atoms(reserves), "migration": None,
            "top_share_bps": pending["top_share_bps"], "clump_ns": pending["clump_ns"],
            "primary": {"peak": entry_math.entry_price, "peak_net_return": entry_math.net_return,
                        "pending": None, "result": None},
            "comparator": {"peak": entry_math.entry_price, "peak_net_return": entry_math.net_return,
                           "pending": None, "result": None}}
        del state["pending_entries"][mint]
        open_row = {"entry_id": entry_id, "mint": mint, "entry_day": RT._day(time.time()),
                    "entry_price": entry_math.entry_price,
                    "decision_unix_nanos": pending["decision_ns"],
                    "landing_unix_nanos": row["received_unix_nanos"],
                    "evidence_sha256": pending["evidence_sha256"],
                    "landing_evidence_sha256": row["record_sha256"],
                    "gate_tier": "AT_S6_CONCENTRATION_PROXY", "basis": "causal_cp"}
        state["pending_ledger"].append({"kind": "opened", "row": open_row}); _save(state); _drain(state)
    mint_state = state["mints"].setdefault(mint, {"rows": []})
    if mint not in state["sampled_mints"] and mint not in state["pending_entries"]:
        mint_state["rows"].append(row)
        signal = BM.first_six_signal(mint_state["rows"])
        if signal:
            entry_id = RT._sha({"instrument": INSTRUMENT, "mint": mint,
                                "decision_sequence": signal["decision_sequence"],
                                "evidence": signal["evidence_record_sha256"]})
            state["sampled_mints"][mint] = entry_id
            state["pending_entries"][mint] = {"entry_id": entry_id,
                "decision_ns": signal["decision_unix_nanos"],
                "target_ns": signal["decision_unix_nanos"] + int(BM.LATENCY_S * 1e9),
                "deadline_ns": signal["decision_unix_nanos"]
                + int((BM.LATENCY_S + BM.ENTRY_BOUNDARY_TIMEOUT_S) * 1e9),
                "top_share_bps": signal["top_share_bps"], "clump_ns": signal["clump_ns"],
                "evidence_sha256": signal["evidence_record_sha256"]}
    state["tape_cursor"], state["tape_head"] = row["sequence"], row["record_sha256"]
    _save(state)


def _timeouts(state: dict, now_ns: int, provider: PumpSwapProvider) -> None:
    for mint, pending in list(state["pending_entries"].items()):
        if now_ns >= pending["deadline_ns"]:
            void_id = RT._sha({"entry_id": pending["entry_id"], "reason": "VOID_NO_ENTRY_BOUNDARY"})
            state["pending_ledger"].append({"kind": "void", "row": {
                "void_id": void_id, "entry_id": pending["entry_id"], "mint": mint,
                "reason": "VOID_NO_ENTRY_BOUNDARY", "decision_unix_nanos": pending["decision_ns"]}})
            del state["pending_entries"][mint]; state["voids"] += 1; _save(state); _drain(state)
    for mint, raw in list(state["open"].items()):
        if raw.get("migration"):
            _service_migration(state, mint, raw, provider, now_ns)
            if mint not in state["open"] or raw.get("migration"):
                continue
        for variant in ("primary", "comparator"):
            value = raw[variant]; pending = value.get("pending")
            if pending and now_ns >= pending["deadline_ns"]:
                p = _position(mint, raw, variant)
                result = EX.resolve(p, "RUG_UNPRICED", latency_s=BM.LATENCY_S,
                                    now_ts=now_ns / 1e9)
                result["landing_record_sha256"] = pending["trigger_record_sha256"]
                value["result"], value["pending"] = result, None
            elif (value.get("result") is None and pending is None
                  and now_ns - raw["last_event_ns"] >= BM.DEAD_SILENCE_S * 1e9):
                value["pending"] = {"reason": "DEAD_SILENCE",
                    "target_ns": now_ns + int(BM.LATENCY_S * 1e9),
                    "deadline_ns": now_ns + int((BM.LATENCY_S + BM.EXIT_BOUNDARY_TIMEOUT_S) * 1e9),
                    "trigger_record_sha256": raw.get("last_record_sha256", "0" * 64)}
        _maybe_finish(state, mint)
    _save(state)


def _new_tape_rows(state: dict) -> list[dict]:
    path = ws_data.TRADE_BUFFER_PATH
    if not path.exists():
        if state["tape_offset"] != 0:
            raise RuntimeError("bundle tape disappeared below persisted cursor")
        return []
    if path.stat().st_size < state["tape_offset"]:
        raise RuntimeError("bundle tape truncated below persisted cursor")
    rows = []
    with path.open("rb") as handle:
        handle.seek(state["tape_offset"])
        while True:
            start = handle.tell(); raw = handle.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                handle.seek(start); break
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError("bundle tape has a malformed complete row") from exc
            rows.append((row, handle.tell()))
    return rows


def _cycle_unlocked(provider: PumpSwapProvider) -> dict:
    if not ws_data.trade_data_authorized():
        raise RuntimeError("bundle arm refuses without PUMPPORTAL_DATA_API_KEY")
    state, fresh = _load_state(); _ledger().ensure_genesis(); _drain(state)
    created = _created_after_activation(state)
    rows = _new_tape_rows(state)
    for row, end_offset in rows:
        body = dict(row); observed_hash = body.pop("record_sha256", None)
        if (row.get("sequence") != state["tape_cursor"] + 1
                or row.get("previous_record_sha256") != state["tape_head"]
                or observed_hash != hashlib.sha256(ws_data._canonical(body)).hexdigest()):
            raise RuntimeError("bundle tape cursor/head continuity refuses")
        _process_row(state, row, created)
        state["tape_offset"] = end_offset; _save(state)
    _timeouts(state, time.time_ns(), provider); state["cycles"] += 1; _save(state)
    return {"fresh": fresh, "rows": len(rows), "open": len(state["open"]),
            "pending": len(state["pending_entries"]), "voids": state["voids"]}


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
            raise RuntimeError("another bundle runtime owns the instrument") from exc
        return _cycle_unlocked(provider)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN); os.close(descriptor)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    once = "--once" in argv
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
