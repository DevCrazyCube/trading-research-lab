#!/usr/bin/env python3
"""PAC portfolio convexity scalper — a MULTI-POSITION PAPER-SCENARIO runner (measurement instrument).

There is deliberately no wallet, signer, transaction builder, or sender here.  This fans the proven
single-position PAC honest core out into a book of up to N_MAX concurrent slots so we can grab many
fat-tail shots, cut losers small+fast with a tight hard stop, and let the rare runners run.  Every
fill still lands at the modeled target (decision + calibrated latency) and is priced at the snapshot
observed THEN — the per-slot fill/resolve/cross-venue/ATA-reclaim logic is reused verbatim from
pac_v2_runner, so it stays lookahead-free by construction.  A continuous mark logger records the
intra-trade quote path of every slot so the convexity hinge can be MEASURED forward, not assumed.

Honest status: on current evidence this design's expected book is NEGATIVE (an adversarial workflow
falsified the naive break-even as a lookahead artifact; ~5% of trades are atomic unexitable rugs).
It is run to MEASURE the one unmeasurable-from-history parameter (proactive rug-catch fraction), not
as a proven profit engine.  The scenario ledger + mark log are the only arbiters.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import json
import pathlib
import threading
import time

from .execution import IntentKind, OrderIntent, PriceUnavailable, RefusedExecution, q_lamports_for_usd
from .feasibility import kernel_accounting
from . import pac_v21_calibration as calibration
from . import pac_v22_feed as feed
from . import pac_v2_runner as core
from . import pac_scalp_detector as detector
from . import pac_scalp_policy as policy
from . import pac_scalp_marklog as marklog
from .pac_v2_snapshot import PublicRpcSnapshotProvider, SnapshotUnavailable, snapshot_to_dict
from .pac_v2_pumpswap import PumpSwapProvider
from . import solusd_recorder


INSTRUMENT = "AFTERSHOCK_PAC_SCALP"
SCHEMA = 1
PROBE_USD = "10"
N_MAX = 4
GROSS_NOTIONAL_CAP_LAMPORTS = 800_000_000          # <= 0.80 SOL deployed across the book
REENTRY_COOLDOWN_NANOS = 90_000_000_000
POSITION_REFRESH_INTERVAL_NANOS = 2_000_000_000
CORRELATED_DUMP_WINDOW_NANOS = 30_000_000_000       # >=50% of open slots hard-stopping in 30s...
CORRELATED_DUMP_HALT_NANOS = 300_000_000_000        # ...halts new entries for 5 min (market-rug guard)
SLIPPAGE_BPS = core.SLIPPAGE_BPS
SLIPPAGE_DEN = core.SLIPPAGE_DEN
SCAN_INTERVAL_SECONDS = 0.10
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
STATE = RESEARCH / f"{INSTRUMENT}_RUNNER_STATE.json"
LEDGER = RESEARCH / f"{INSTRUMENT}_SCENARIO_LEDGER.jsonl"
LOCK = RESEARCH / f"{INSTRUMENT}_RUNNER.lock"
MARKS = ROOT / "research" / "data" / "aftershock" / "pac_scalp" / "marks.jsonl"

OpenPosition = core.OpenPosition
_hash = core._hash
_CORE_LOCK = threading.RLock()


@contextmanager
def _configured_core():
    """Stamp core's audited ledger/fill/resolve helpers with the scalp instrument id so every row
    the reused single-position engine emits validates under AFTERSHOCK_PAC_SCALP, not PAC V2."""
    with _CORE_LOCK:
        original = core.INSTRUMENT
        core.INSTRUMENT = INSTRUMENT
        try:
            yield
        finally:
            core.INSTRUMENT = original


@dataclass(frozen=True)
class RuntimeProof:
    seal_sha256: str
    activation_unix_nanos: int
    calibration: calibration.Calibration

    def __post_init__(self) -> None:
        if (not isinstance(self.seal_sha256, str) or len(self.seal_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.seal_sha256)):
            raise RefusedExecution("PAC scalp runtime seal hash is invalid")
        if type(self.activation_unix_nanos) is not int or self.activation_unix_nanos <= 0:
            raise RefusedExecution("PAC scalp activation clock is invalid")
        if not isinstance(self.calibration, calibration.Calibration):
            raise RefusedExecution("PAC scalp runtime lacks typed processed calibration")
        if max(self.calibration.last_processed_unix_nanos,
               self.calibration.last_attested_unix_nanos) >= self.activation_unix_nanos:
            raise RefusedExecution("PAC scalp activation must follow inherited attested calibration")


def _new_state(proof: RuntimeProof, *, event_offset: int, receipt_offset: int) -> dict:
    return {
        "schema": SCHEMA, "instrument_id": INSTRUMENT,
        "seal_sha256": proof.seal_sha256, "activation_unix_nanos": proof.activation_unix_nanos,
        "calibration_sha256": proof.calibration.artifact_sha256,
        "reaction_p90_nanos": proof.calibration.processed_p90_nanos,
        "cursor": {"event_offset": event_offset, "receipt_offset": receipt_offset,
                   "pending": [], "rejected_receipts": []},
        "buffers": {}, "open_positions": {}, "pending_orders": {},
        "entry_watermark_source_unix_nanos": 0, "cooldowns": {}, "recent_stops": [],
        "halt_new_entries_until": 0, "pending_ledger_rows": [], "last_status": None,
    }


def _single_view(state: dict, *, open_position=None, pending_order=None) -> dict:
    """A one-slot state that core's audited fill/resolve/graduation helpers can operate on."""
    return {
        "schema": core.SCHEMA, "instrument_id": INSTRUMENT,
        "seal_sha256": state["seal_sha256"], "activation_unix_nanos": state["activation_unix_nanos"],
        "calibration_sha256": state["calibration_sha256"],
        "reaction_p90_nanos": state["reaction_p90_nanos"],
        "open_position": open_position, "pending_order": pending_order,
        "pending_ledger_rows": [],
    }


BUFFER_RETENTION_NANOS = 180_000_000_000


def _update_buffers(state: dict, events, *, now: int) -> None:
    """Book-wide buffer maintenance: append per-mint events and passively refresh EVERY held slot."""
    held = set(state["open_positions"]) | {o["mint"] for o in state["pending_orders"].values()}
    for event in events:
        if event.source_received_unix_nanos <= state["activation_unix_nanos"]:
            continue
        buffer = state["buffers"].setdefault(event.mint, [])
        if buffer and buffer[-1].get("collector_epoch") != event.collector_epoch:
            buffer.clear()
        buffer.append(core._event_dict(event))
        slot = state["open_positions"].get(event.mint)
        if slot is not None:
            slot["last_state"] = asdict(event.post_state)
            slot["last_context_slot"] = max(slot["last_context_slot"], event.slot)
    cutoff = now - BUFFER_RETENTION_NANOS
    for mint in list(state["buffers"]):
        kept = [it for it in state["buffers"][mint] if it["source_received_unix_nanos"] >= cutoff]
        if mint in held and not kept and state["buffers"][mint]:
            kept = [state["buffers"][mint][-1]]
        if kept:
            state["buffers"][mint] = kept
        else:
            del state["buffers"][mint]


def _quote_input(now: int) -> int:
    observation = solusd_recorder.latest_observation(decision_unix_nanos=now)
    return q_lamports_for_usd(PROBE_USD, observation, decision_unix_nanos=now,
                              max_staleness_nanos=solusd_recorder.MAX_LOCAL_AGE_NANOS)


def _deployed_notional(state: dict) -> int:
    total = sum(p["quote_input_lamports"] for p in state["open_positions"].values())
    total += sum(o["amount"] for o in state["pending_orders"].values() if o["side"] == "ENTRY")
    return total


def _record_mark(position: OpenPosition, *, now: int, net, real_quote, venue: str) -> None:
    marklog.record(
        entry_id=position.entry_id, mint=position.mint, observed_unix_nanos=now,
        context_slot=position.last_context_slot, entry_all_in_lamports=position.entry_all_in_lamports,
        net_exit_lamports=net, real_quote_lamports=real_quote,
        peak_net_exit_lamports=position.peak_net_exit_lamports, venue=venue,
        priceable=net is not None, path=MARKS)


def _complete_pending_orders(state: dict, provider, pumpswap_provider, *, now: int) -> list[dict]:
    """Resolve every landed pending order by delegating to the audited single-position core."""
    rows: list[dict] = []
    for decision_id, pending in list(state["pending_orders"].items()):
        if now < pending["target_unix_nanos"]:
            continue
        mint = pending["mint"]
        slot = state["open_positions"].get(mint)
        view = _single_view(state, open_position=slot, pending_order=pending)
        produced = core._complete_pending(view, provider, pumpswap_provider, now=now)
        rows.extend(produced)
        # Merge the audited outcome back into the book.
        if view["pending_order"] is None:
            state["pending_orders"].pop(decision_id, None)
        else:
            state["pending_orders"][decision_id] = view["pending_order"]
        if view["open_position"] is None:
            if slot is not None and any(r["kind"] == "resolved" for r in produced):
                state["open_positions"].pop(mint, None)
                state["cooldowns"][mint] = now + REENTRY_COOLDOWN_NANOS
                if any(r.get("action") == policy.ExitAction.EXIT_HARD_STOP.value for r in produced):
                    state["recent_stops"].append(now)
        else:
            state["open_positions"][mint] = view["open_position"]
    return rows


def _service_positions(state: dict, provider, pumpswap_provider, *, now: int) -> list[dict]:
    """Convex exit decision per open slot: hard-stop / let-run trail, with mark logging."""
    rows: list[dict] = []
    for mint, raw in list(state["open_positions"].items()):
        if any(o["mint"] == mint for o in state["pending_orders"].values()):
            continue  # this slot already has a landed-exit pending
        position = OpenPosition(**raw)
        if now < position.entry_unix_nanos:
            continue
        # Reuse the audited active on-chain graduation refresh (curve->PumpSwap venue transition).
        view = _single_view(state, open_position=asdict(position))
        transition = core._refresh_and_check_graduation(
            view, position, provider, pumpswap_provider, now=now)
        if view["open_position"] is None and view["pending_order"] is not None:
            # graduated -> a PUMPSWAP venue-transition exit was opened
            rows.extend(transition or [])
            state["pending_orders"][view["pending_order"]["decision_id"]] = view["pending_order"]
            state["open_positions"].pop(mint, None)
            continue
        if transition is not None:
            rows.extend(transition)
            state["open_positions"][mint] = view["open_position"]
            continue
        position = OpenPosition(**view["open_position"])  # last_state/refresh may have advanced
        reserve = feed.ReserveState(**position.last_state)
        intent = OrderIntent(IntentKind.EXACT_TOKEN_SELL, position.token_atoms, 1)
        try:
            quote = kernel_accounting(reserve, intent)
            net = quote["wallet_delta_lamports"]
            if net <= 0:
                net = None
        except PriceUnavailable:
            quote = None
            net = None
        _record_mark(position, now=now, net=net, real_quote=(reserve.real_quote if net is not None else None),
                     venue="CURVE")
        decision_position = policy.Position(
            position.token_atoms, position.quote_input_lamports, position.entry_all_in_lamports,
            position.entry_unix_nanos, position.peak_net_exit_lamports)
        try:
            outcome = policy.decide(decision_position, now_unix_nanos=now, net_exit_lamports=net,
                                    real_quote_lamports=(reserve.real_quote if net is not None else None))
        except ValueError as exc:
            raise RefusedExecution("PAC scalp exit policy refused an invalid causal clock/quote") from exc
        position.peak_net_exit_lamports = outcome.position.peak_net_exit_lamports
        state["open_positions"][mint] = asdict(position)
        if outcome.action == policy.ExitAction.HOLD:
            continue
        if outcome.action == policy.ExitAction.UNEXITABLE_FULL_LOSS:
            state["open_positions"].pop(mint, None)
            state["cooldowns"][mint] = now + REENTRY_COOLDOWN_NANOS
            view = _single_view(state, open_position=asdict(position))
            rows.append(core._resolve_full_loss(view, position, now=now,
                        action=outcome.action.value, reason="OBSERVED_STATE_UNPRICEABLE"))
            continue
        decision_id = _hash({"instrument": INSTRUMENT, "side": "EXIT", "mint": position.mint,
                             "entry_id": position.entry_id, "action": outcome.action.value,
                             "decision_unix_nanos": now, "net_quote": net})
        state["pending_orders"][decision_id] = {
            "side": "EXIT", "mint": position.mint, "amount": position.token_atoms,
            "min_out": max(1, quote["out_amount"] * (SLIPPAGE_DEN - SLIPPAGE_BPS) // SLIPPAGE_DEN),
            "decision_id": decision_id, "decision_unix_nanos": now,
            "target_unix_nanos": now + state["reaction_p90_nanos"],
            "minimum_context_slot": position.last_context_slot,
            "action": outcome.action.value, "entry_id": position.entry_id,
            "observation_failures": 0, "last_observation_failure": None}
        rows.append(core._ledger_row(state, "exit_decision", {
            "mint": position.mint, "entry_id": position.entry_id, "decision_id": decision_id,
            "action": outcome.action.value, "decision_unix_nanos": now,
            "target_unix_nanos": now + state["reaction_p90_nanos"],
            "minimum_context_slot": position.last_context_slot, "decision_net_exit_lamports": net}))
    return rows


def _admit_candidates(state: dict, *, now: int, quote_input_lamports: int) -> list[dict]:
    if now < state.get("halt_new_entries_until", 0):
        return []
    entering = {o["mint"] for o in state["pending_orders"].values() if o["side"] == "ENTRY"}
    free = N_MAX - len(state["open_positions"]) - len(entering)
    if free <= 0:
        return []
    rows: list[dict] = []
    # clean expired cooldowns
    state["cooldowns"] = {m: t for m, t in state["cooldowns"].items() if t > now}
    candidates = []
    for mint, raw_events in state["buffers"].items():
        if mint in state["open_positions"] or mint in entering or mint in state["cooldowns"]:
            continue
        events = tuple(core._event(item) for item in raw_events)
        signal = detector.qualify(events, now_unix_nanos=now, quote_input_lamports=quote_input_lamports)
        if signal is None:
            continue
        if signal.window_end_unix_nanos <= state["entry_watermark_source_unix_nanos"]:
            continue
        candidates.append((signal.window_end_unix_nanos, mint, events, signal))
    candidates.sort(key=lambda c: c[0])
    for signal_source, mint, events, signal in candidates:
        if free <= 0:
            break
        if _deployed_notional(state) + quote_input_lamports > GROSS_NOTIONAL_CAP_LAMPORTS:
            break
        decision_state = events[-1].post_state
        intent = OrderIntent(IntentKind.EXACT_QUOTE_BUY, quote_input_lamports, 1)
        try:
            decision_quote = kernel_accounting(decision_state, intent)
        except PriceUnavailable:
            state["entry_watermark_source_unix_nanos"] = max(
                state["entry_watermark_source_unix_nanos"], signal_source)
            continue
        decision_id = _hash({"instrument": INSTRUMENT, "side": "ENTRY", "mint": mint,
                             "decision_unix_nanos": now, "evidence": list(signal.evidence_event_ids),
                             "quote_input_lamports": quote_input_lamports})
        state["pending_orders"][decision_id] = {
            "side": "ENTRY", "mint": mint, "amount": quote_input_lamports,
            "min_out": max(1, decision_quote["out_amount"] * (SLIPPAGE_DEN - SLIPPAGE_BPS) // SLIPPAGE_DEN),
            "decision_id": decision_id, "decision_unix_nanos": now,
            "target_unix_nanos": now + state["reaction_p90_nanos"], "action": None,
            "minimum_context_slot": max(e.slot for e in events), "entry_id": None,
            "observation_failures": 0, "last_observation_failure": None}
        state["entry_watermark_source_unix_nanos"] = max(
            state["entry_watermark_source_unix_nanos"], signal_source)
        rows.append(core._ledger_row(state, "entry_decision", {
            "mint": mint, "decision_id": decision_id, "decision_unix_nanos": now,
            "target_unix_nanos": now + state["reaction_p90_nanos"],
            "minimum_context_slot": state["pending_orders"][decision_id]["minimum_context_slot"],
            "quote_input_lamports": quote_input_lamports,
            "buyer_breadth": signal.buyer_breadth, "net_quote_inflow": signal.net_quote_inflow,
            "evidence_event_ids": list(signal.evidence_event_ids)}))
        free -= 1
    return rows


def _apply_correlated_breaker(state: dict, *, now: int) -> None:
    window = [t for t in state["recent_stops"] if t > now - CORRELATED_DUMP_WINDOW_NANOS]
    state["recent_stops"] = window
    open_and_recent = len(state["open_positions"]) + len(window)
    if open_and_recent > 0 and len(window) * 2 >= max(1, open_and_recent):
        if len(window) >= 2:
            state["halt_new_entries_until"] = now + CORRELATED_DUMP_HALT_NANOS


def _run_once_at(proof: RuntimeProof, provider, pumpswap_provider, *, now: int,
                 quote_input_lamports: int | None = None, state_path: pathlib.Path = STATE,
                 ledger_path: pathlib.Path = LEDGER, events_path: pathlib.Path = feed.EVENTS,
                 receipts_path: pathlib.Path = feed.RECEIPTS, initialize_at_eof: bool = True) -> dict:
    if (not all(hasattr(proof, a) for a in ("activation_unix_nanos", "calibration", "seal_sha256"))
            or not hasattr(provider, "capture") or not hasattr(pumpswap_provider, "capture")):
        raise RefusedExecution("PAC scalp run requires runtime proof and both venue providers")
    if type(now) is not int or now <= proof.activation_unix_nanos:
        raise RefusedExecution("PAC scalp runner clock is not post-activation")
    state_path = pathlib.Path(state_path); ledger_path = pathlib.Path(ledger_path)
    if not state_path.exists():
        eo = pathlib.Path(events_path).stat().st_size if initialize_at_eof and pathlib.Path(events_path).exists() else 0
        ro = pathlib.Path(receipts_path).stat().st_size if initialize_at_eof and pathlib.Path(receipts_path).exists() else 0
        core._atomic_write(state_path, _new_state(proof, event_offset=eo, receipt_offset=ro))
        return {"status": "INITIALIZED_NO_BACKFILL", "open": 0, "pending": 0, "new_events": 0}
    try:
        state = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("PAC scalp runner state is unreadable") from exc
    if state.get("seal_sha256") != proof.seal_sha256 or state.get("calibration_sha256") != proof.calibration.artifact_sha256:
        raise RefusedExecution("PAC scalp runner state is bound to a different seal/calibration")
    with _configured_core():
        core._flush(state, state_path=state_path, ledger_path=ledger_path)
        cursor = core._cursor(state["cursor"])
        new_events = feed.consume(cursor, events_path=events_path, receipts_path=receipts_path,
                                  runner_seen_unix_nanos=now)
        state["cursor"] = core._cursor_dict(cursor)
        _update_buffers(state, new_events, now=now)
        rows = _complete_pending_orders(state, provider, pumpswap_provider, now=now)
        rows += _service_positions(state, provider, pumpswap_provider, now=now)
        _apply_correlated_breaker(state, now=now)
        q = quote_input_lamports if quote_input_lamports is not None else _quote_input(now)
        if type(q) is not int or q <= 0:
            raise RefusedExecution("PAC scalp quote input is invalid")
        rows += _admit_candidates(state, now=now, quote_input_lamports=q)
        if new_events:
            state["entry_watermark_source_unix_nanos"] = max(
                state["entry_watermark_source_unix_nanos"],
                max(e.source_received_unix_nanos for e in new_events))
        state["last_status"] = (f"BOOK_{len(state['open_positions'])}_OPEN_{len(state['pending_orders'])}_PENDING"
                                if state["open_positions"] or state["pending_orders"] else "SCANNING")
        core._commit(state, rows, state_path=state_path, ledger_path=ledger_path)
    return {"status": state["last_status"], "open": len(state["open_positions"]),
            "pending": len(state["pending_orders"]), "new_events": len(new_events),
            "ledger_rows": len(rows)}


def run_once(proof: RuntimeProof, provider, pumpswap_provider, **kwargs) -> dict:
    return _run_once_at(proof, provider, pumpswap_provider, now=time.time_ns(), **kwargs)


def _lock(path: pathlib.Path = LOCK):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RefusedExecution("another PAC scalp runner owns the state lock") from exc
    return handle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC portfolio convexity scalper (paper-scenario)")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=SCAN_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    try:
        from .pac_scalp_manifest import load_runtime_proof
        proof = load_runtime_proof()
        provider = PublicRpcSnapshotProvider()
        pumpswap_provider = PumpSwapProvider()
        with _lock():
            while True:
                started = time.monotonic()
                try:
                    result = run_once(proof, provider, pumpswap_provider)
                except RefusedExecution as exc:
                    result = {"status": "CYCLE_REFUSED", "reason": str(exc)[:240]}
                print(json.dumps(result, sort_keys=True), flush=True)
                if args.once:
                    break
                remaining = args.interval - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)
        return 0
    except (RefusedExecution, ImportError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
