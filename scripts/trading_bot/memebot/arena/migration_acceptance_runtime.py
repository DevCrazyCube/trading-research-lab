#!/usr/bin/env python3
"""Read-only causal PumpSwap paper runtime for MIGRATION_ACCEPTANCE_V1.

Evolved from graduation_runtime.py (confirmed-migration → exact-CP PumpSwap fill machinery). The arm
(arms/migration_acceptance.py) owns the identity, the frozen spec, the exact-CP `buy_quote` and the pure
`stress_test_exit_capacity` simulation; this runtime wires them to the live tape and adds:

  * the CONFIRMED-migration gate + live-pool capture (a single observation at migration_slot + LATENCY_SLOTS);
  * the EXECUTABLE EXIT-CAPACITY STRESS TEST as a hard entry precondition (clip <= 5% of pool capacity, then
    STRESS_SELLS position-size sells absorbed, then the full $10 recovers into the depressed pool) — a failed
    stress test is a STRATEGY VOID (EXIT_CAPACITY_VOID / STRESS_TEST_FAILED), never a trade and never a loss;
  * the shared-sizer global slot: a PROXY_PASS (primary) entry claims one of the max-2 global PRIMARY slots
    (else PRIMARY_SLOT_FULL void); controls are executed identically for a null baseline but NEVER touch the
    slot; the slot is released when the position pops (resolved or measurement void); reconcile_slots at cycle
    start self-heals a crash-orphaned slot;
  * the RUG-arbiter routing of the one −100% site (an exit that stays unpriceable): raw['pool'] is the
    liquidity account — only a positively-dead pool books a real −100%, anything else is a right-censored
    MEASUREMENT_FAILURE void that frees the slot;
  * the boot-closure guard: the closure sha loaded at import is re-checked every cycle so a stale process can
    never run old code under a freshly-written activation.

No signer, no order path, no wallet. Paper measurement only; the verdict is runtime.report_arm's.
"""
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
from . import sizer as SZ
from .chainledger import ChainLedger
from .helius_rug_arbiter import classify_unpriced
from .arms import bundle_momentum as BM
from .arms import migration_acceptance as MA
from .. import ws_data
from ...aftershock import solusd_recorder
from ...aftershock.execution import q_lamports_for_usd, PriceUnavailable
from ...aftershock.pac_v2_pumpswap import PumpSwapProvider, PumpSwapUnavailable, sell_quote

INSTRUMENT = MA.ARM.instrument
POLL_SECONDS = 5
STATE_SCHEMA = 1
MAX_TAPE_ROWS_PER_CYCLE = 20_000

# The ONE shared portfolio/slot file for the whole arena (global max-2 PRIMARY across ALL arms).
PORTFOLIO = RT.DATA / "portfolio.json"

# --- boot-closure guard (handoff 460) -------------------------------------------------------------------
# Capture this arm's executable closure sha at IMPORT (= process boot). code_sha256() and require_activation
# both read the CURRENT on-disk files, so after a commit they agree with a fresh on-disk activation even
# though THIS long-lived process still runs the OLD resolver from memory. Comparing the live disk sha to this
# boot capture refuses that: a stale process must not run its old code under a new activation. The arm's
# closure list includes THIS runtime file + every module it imports.
_BOOT_SHA = MA.ARM.code_sha256()


def _boot_guard() -> None:
    live = MA.ARM.code_sha256()
    if live != _BOOT_SHA:
        raise RuntimeError(
            f"{INSTRUMENT}: BOOT CLOSURE DRIFT — this process loaded code {_BOOT_SHA[:8]} but the on-disk "
            f"closure is now {live[:8]}. A stale process must NOT run its old resolver under a freshly-"
            "written activation (handoff 460). Restart the runtime.")


def _path() -> pathlib.Path:
    return RT.DATA / INSTRUMENT / "state.json"


def _ledger() -> ChainLedger:
    _boot_guard()                       # guard every ledger touch (drain + genesis) before it happens
    authority = MF.require_activation(MA.ARM)
    return ChainLedger(RT.DATA / INSTRUMENT / "ledger.jsonl", INSTRUMENT,
                       authority["code_sha256"], authority["prereg_sha256"],
                       authority["spec_sha256"], authority["activation_sha256"])


def _new_state(authority: dict) -> dict:
    return {"schema": STATE_SCHEMA, "instrument": INSTRUMENT,
            "activation_unix_nanos": authority["activated_unix_nanos"],
            "tape_cursor": authority["tape_sequence"],
            "tape_head": authority["tape_head_sha256"], "tape_offset": authority["tape_offset"],
            "mints": {}, "candidates": {}, "open": {}, "sampled_mints": {},
            "pending_ledger": [], "census": {}, "cycles": 0, "created": {}}


def _load() -> tuple[dict, bool]:
    authority = MF.require_activation(MA.ARM)
    path = _path(); fresh = not path.exists(); state = RT._load(path, _new_state(authority))
    required = {"schema", "instrument", "activation_unix_nanos", "tape_cursor", "tape_head",
                "tape_offset", "mints", "candidates", "open", "sampled_mints",
                "pending_ledger", "census", "cycles", "created"}
    if (not isinstance(state, dict) or set(state) != required or state["schema"] != STATE_SCHEMA
            or state["instrument"] != INSTRUMENT):
        raise RuntimeError("migration_acceptance state refuses")
    if state["activation_unix_nanos"] != authority["activated_unix_nanos"]:
        raise RuntimeError("migration_acceptance state activation does not match authority")
    return state, fresh


def _save(state: dict) -> None:
    RT._save(_path(), state)


def _inc(state: dict, name: str) -> None:
    state["census"][name] = state["census"].get(name, 0) + 1


def _release(event: dict) -> None:
    """Free the global PRIMARY slot a terminal row held. release_primary is idempotent, so a WAL replay that
    re-runs this before the pending event is popped is safe."""
    mint = event.get("release_slot")
    if mint:
        SZ.release_primary(INSTRUMENT, mint, PORTFOLIO)


def _drain(state: dict) -> None:
    ledger = _ledger()
    while state["pending_ledger"]:
        event = state["pending_ledger"][0]
        if event["kind"] == "opened":
            ledger.append_opened(event["row"])
        elif event["kind"] == "resolved":
            ledger.append_resolved(event["row"]); state["open"].pop(event["row"]["mint"], None)
            _release(event)
        elif event["kind"] == "void":
            ledger.append_void(event["row"])
            mint = event.get("remove_open_mint")
            if mint:
                state["open"].pop(mint, None)
            _release(event)
        else:
            raise RuntimeError("migration_acceptance pending kind refuses")
        state["pending_ledger"].pop(0); _save(state)


def _rows(state: dict, limit: int) -> list[tuple[dict, int]]:
    path = ws_data.TRADE_BUFFER_PATH
    if not path.exists():
        if state["tape_offset"]:
            raise RuntimeError("migration_acceptance tape disappeared")
        return []
    if path.stat().st_size < state["tape_offset"]:
        raise RuntimeError("migration_acceptance tape truncated")
    output = []
    with path.open("rb") as handle:
        handle.seek(state["tape_offset"])
        while len(output) < limit:
            start = handle.tell(); raw = handle.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                handle.seek(start); break
            row = json.loads(raw); output.append((row, handle.tell()))
    return output


def _absorb_creates(state: dict) -> None:
    """Fold newly-observed post-activation create mints into the persisted eligibility set (bounded create
    buffer; persisting also stops a trimmed create line from silently dropping a still-eligible mint)."""
    activation = state["activation_unix_nanos"]
    for row in ws_data.read_buffer():
        received = row.get("received_unix_nanos")
        if isinstance(row.get("mint"), str) and type(received) is int and received > activation:
            state["created"][row["mint"]] = received


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


def _void(state: dict, mint: str, reason: str, candidate: dict, detail: str | None = None) -> None:
    """A STRATEGY VOID: the candidate was screened out (bad migration, thin/failed pool, no slot) — never a
    trade and never a loss. No open exists yet and no slot is held, so nothing to pop or release."""
    void_id = RT._sha({"instrument": INSTRUMENT, "mint": mint, "reason": reason,
                       "migration": candidate.get("record_sha256")})
    state["pending_ledger"].append({"kind": "void", "row": {
        "void_id": void_id, "mint": mint, "reason": reason, "cohort": candidate.get("cohort"),
        "detail": detail, "decision_unix_nanos": candidate["received_unix_nanos"]}})
    state["candidates"].pop(mint, None); _inc(state, reason); _save(state); _drain(state)


def _open_candidate(state: dict, mint: str, candidate: dict, provider: PumpSwapProvider) -> None:
    now_ns = time.time_ns()
    # A late fill is lookahead-adjacent. If migration-signal → fill latency has blown the bounded window
    # (a backlog casualty), VOID before any economic read — never fill late.
    if now_ns - candidate["received_unix_nanos"] > MA.MAX_ENTRY_LAG_S * 1e9:
        _void(state, mint, "ENTRY_LAG_EXCEEDED", candidate)
        return
    # confirmed migration: the signature must resolve to a real confirmed slot
    if candidate.get("migration_slot") is None:
        candidate["migration_slot"] = _migration_slot(provider, candidate)
        if candidate["migration_slot"] is None:
            if now_ns - candidate["received_unix_nanos"] > MA.MIGRATION_CONFIRM_TIMEOUT_S * 1e9:
                _void(state, mint, "UNCONFIRMED_MIGRATION", candidate)
            return
    # confirmed LIVE PumpSwap pool: capture real reserves at migration_slot + LATENCY_SLOTS
    try:
        observation = provider.capture(mint, candidate["migration_slot"] + MA.LATENCY_SLOTS)
    except PumpSwapUnavailable:
        if now_ns - candidate["received_unix_nanos"] > MA.POOL_CONFIRM_TIMEOUT_S * 1e9:
            _void(state, mint, "UNCONFIRMED_LIVE_POOL", candidate)
        return
    decision_ns = observation.response_received_unix_nanos
    usd = solusd_recorder.latest_observation(decision_unix_nanos=decision_ns)
    q = q_lamports_for_usd(MA.SIZE_USD, usd, decision_unix_nanos=decision_ns,
                           max_staleness_nanos=solusd_recorder.MAX_LOCAL_AGE_NANOS)
    try:
        quote = MA.buy_quote(q, observation.reserves)
    except ValueError as exc:
        _void(state, mint, "STRESS_TEST_FAILED", candidate, detail=f"entry buy unavailable: {str(exc)[:80]}")
        return
    base_in_atoms = quote["base_out_atoms"]

    # ---- THE ACCEPTANCE GATE: executable exit-capacity stress test on the LIVE pool, BEFORE any entry ----
    stress = MA.stress_test_exit_capacity(observation.reserves, base_in_atoms, q, usd.value_str)
    if not stress["ok"]:
        _void(state, mint, stress["reason"], candidate, detail=stress.get("detail"))
        return

    # PROXY_PASS (primary) claims one of the global max-2 slots; a full arena is a PRIMARY_SLOT_FULL strategy
    # void (declared, outcome-independent). Controls are executed but never touch the slot.
    cohort = candidate["cohort"]
    holds_slot = False
    if cohort == "PROXY_PASS":
        if not SZ.try_acquire_primary(INSTRUMENT, mint, PORTFOLIO):
            _void(state, mint, "PRIMARY_SLOT_FULL", candidate,
                  detail="arena at global 2-primary cap")
            return
        holds_slot = True

    entry_all_in = q + MA.ENTRY_ROUTE_COST_LAMPORTS + MA.ATA_RENT_LAMPORTS
    entry_id = RT._sha({"instrument": INSTRUMENT, "mint": mint,
                        "migration": candidate["record_sha256"],
                        "pool_evidence": observation.raw_response_sha256})
    raw = {"mint": mint, "entry_id": entry_id, "cohort": cohort,
           "entry_day": RT._day(decision_ns / 1e9), "entry_unix_nanos": decision_ns,
           "entry_all_in_lamports": entry_all_in, "quote_input_lamports": q,
           "token_atoms": base_in_atoms, "pool": observation.pool,
           "last_slot": observation.context_slot, "peak_equity_lamports": 0,
           "pending_exit": None, "unavailable_polls": 0, "last_gross_exit_lamports": 0,
           "last_evidence_sha256": observation.raw_response_sha256, "holds_slot": holds_slot,
           "stress_capacity_usd": stress.get("capacity_usd")}
    state["open"][mint] = raw; state["sampled_mints"][mint] = entry_id
    state["candidates"].pop(mint, None)
    state["pending_ledger"].append({"kind": "opened", "row": {
        "entry_id": entry_id, "mint": mint, "entry_day": raw["entry_day"],
        "entry_price": q / base_in_atoms, "decision_unix_nanos": candidate["received_unix_nanos"],
        "landing_unix_nanos": decision_ns, "evidence_sha256": candidate["record_sha256"],
        "landing_evidence_sha256": observation.raw_response_sha256,
        "gate_tier": cohort, "basis": "pumpswap_exact_cp",
        "stress_absorbed": stress.get("absorbed"), "stress_capacity_usd": stress.get("capacity_usd")}})
    _save(state); _drain(state)


def _terminal(state: dict, raw: dict, *, reason: str, equity: int, evidence_sha256: str,
              arbiter: dict | None = None) -> None:
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
    if arbiter is not None:
        row["arbiter_verdict"] = arbiter.get("verdict")
        row["arbiter_reason"] = arbiter.get("reason")
    state["pending_ledger"].append({"kind": "resolved", "row": row,
        "release_slot": raw["mint"] if raw.get("holds_slot") else None})
    _save(state); _drain(state)


def _measurement_void(state: dict, raw: dict, arbiter: dict) -> None:
    """An unpriceable exit whose pool the arbiter could NOT positively confirm dead: a right-censored
    MEASUREMENT_FAILURE, NEVER a −100%. Pops the open and frees the slot."""
    mint = raw["mint"]
    void_id = RT._sha({"entry_id": raw["entry_id"], "kind": "measurement_void"})
    row = {"void_id": void_id, "entry_id": raw["entry_id"], "mint": mint,
           "reason": "MEASUREMENT_FAILURE", "cohort": raw["cohort"], "entry_day": raw["entry_day"],
           "arbiter_verdict": arbiter.get("verdict"), "arbiter_reason": arbiter.get("reason"),
           "decision_unix_nanos": raw["entry_unix_nanos"]}
    state["pending_ledger"].append({"kind": "void", "row": row, "remove_open_mint": mint,
        "release_slot": mint if raw.get("holds_slot") else None})
    _inc(state, "MEASUREMENT_FAILURE"); _save(state); _drain(state)


def _resolve_unpriced(state: dict, raw: dict, pending: dict) -> None:
    """The single −100% site: an exit decision that stayed unpriceable for UNAVAILABLE_POLLS. Ask the Helius
    arbiter whether the pool is positively dead. RUG_CONFIRMED → a real −100% primary loss; anything else → a
    measurement-failure void (the price feed was down, not the coin)."""
    mint = raw["mint"]
    try:
        arb = classify_unpriced(mint, raw.get("pool"))   # raw['pool'] is the PumpSwap pool = liquidity acct
    except Exception as exc:  # noqa: BLE001 — an arbiter failure is a measurement failure, never a rug
        arb = {"verdict": "INDETERMINATE_VOID", "reason": f"arbiter error: {str(exc)[:80]}"}
    if arb["verdict"] == "RUG_CONFIRMED":
        _terminal(state, raw, reason="UNAVAILABLE_FULL_LOSS", equity=0,
                  evidence_sha256=pending["trigger_evidence_sha256"], arbiter=arb)
        return
    _measurement_void(state, raw, arb)


def _service_open(state: dict, mint: str, raw: dict, provider: PumpSwapProvider) -> None:
    pending = raw.get("pending_exit")
    minimum = pending["target_slot"] if pending else raw["last_slot"]
    try:
        observation = provider.capture(mint, minimum)
        quote = sell_quote(raw["token_atoms"], observation.reserves)
        raw["unavailable_polls"] = 0
    except (PumpSwapUnavailable, PriceUnavailable):
        if (not pending and time.time_ns() - raw["entry_unix_nanos"] >= MA.HORIZON_S * 1e9):
            raw["pending_exit"] = {"reason": "HORIZON",
                "target_slot": raw["last_slot"] + MA.LATENCY_SLOTS,
                "trigger_evidence_sha256": raw["last_evidence_sha256"]}
            pending = raw["pending_exit"]
        raw["unavailable_polls"] += 1
        if pending and raw["unavailable_polls"] >= MA.UNAVAILABLE_POLLS:
            _resolve_unpriced(state, raw, pending)     # arbiter decides real RUG vs measurement void
        return
    raw["last_gross_exit_lamports"] = quote["net_quote_lamports"]
    raw["last_evidence_sha256"] = observation.raw_response_sha256
    equity = (quote["net_quote_lamports"] - MA.EXIT_ROUTE_COST_LAMPORTS
              + MA.ATA_RENT_LAMPORTS - MA.ATA_CLOSE_COST_LAMPORTS)
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
    if time.time_ns() - raw["entry_unix_nanos"] >= MA.HORIZON_S * 1e9:
        reason = reason or "HORIZON"
    if reason:
        raw["pending_exit"] = {"reason": reason,
            "target_slot": observation.context_slot + MA.LATENCY_SLOTS,
            "trigger_evidence_sha256": observation.raw_response_sha256}


def _cycle_unlocked(provider: PumpSwapProvider) -> dict:
    _boot_guard()
    if not ws_data.trade_data_authorized():
        raise RuntimeError("migration_acceptance arm refuses without PUMPPORTAL_DATA_API_KEY")
    state, fresh = _load(); _ledger().ensure_genesis(); _drain(state)
    # STARTUP self-heal for the acquire-side leak: release any of OUR slots whose mint is not a live
    # slot-holding open (a crash between try_acquire_primary and recording the open orphans a slot forever).
    SZ.reconcile_slots(INSTRUMENT, [m for m, r in state["open"].items() if r.get("holds_slot")], PORTFOLIO)
    # service open positions first so they are never starved behind a large tape/entry batch
    for mint, raw in list(state["open"].items()):
        _service_open(state, mint, raw, provider)
    _absorb_creates(state)
    for row, end in _rows(state, MAX_TAPE_ROWS_PER_CYCLE):
        body = dict(row); observed = body.pop("record_sha256", None)
        if (row.get("sequence") != state["tape_cursor"] + 1
                or row.get("previous_record_sha256") != state["tape_head"]
                or observed != hashlib.sha256(ws_data._canonical(body)).hexdigest()):
            raise RuntimeError("migration_acceptance tape continuity refuses")
        mint = row["mint"]; transitioned = False
        if (mint in state["created"] and mint not in state["sampled_mints"]
                and mint not in state["candidates"]):
            bucket = state["mints"].setdefault(mint, [])
            if row.get("tx_type") in {"buy", "sell"} and len(bucket) < 2000:
                bucket.append(row)
            if row.get("tx_type") in {"migrate", "migration"}:
                cohort = "PROXY_PASS" if BM.first_six_signal(bucket) else "CONTROL_PROXY_FAIL"
                state["candidates"][mint] = {"received_unix_nanos": row["received_unix_nanos"],
                    "record_sha256": row["record_sha256"], "signature": row.get("signature"),
                    "cohort": cohort, "migration_slot": None}
                state["mints"].pop(mint, None)
                transitioned = True
        state["tape_cursor"], state["tape_head"], state["tape_offset"] = (
            row["sequence"], row["record_sha256"], end)
        if transitioned:
            _save(state)
    _save(state)
    for mint, candidate in list(state["candidates"].items()):
        _open_candidate(state, mint, candidate, provider)
    # bound epoch state to a rolling 24h working set
    horizon = time.time_ns() - 24 * 3600 * 1_000_000_000
    state["created"] = {m: t for m, t in state["created"].items()
                        if (t >= horizon and m not in state["sampled_mints"]) or m in state["candidates"]}
    state["mints"] = {m: b for m, b in state["mints"].items() if m in state["created"]}
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
            raise RuntimeError("another migration_acceptance runtime owns the instrument") from exc
        return _cycle_unlocked(provider)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN); os.close(descriptor)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--report" in argv:
        print(json.dumps(RT.report_arm(MA.ARM), indent=2, sort_keys=True))
        return 0
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
