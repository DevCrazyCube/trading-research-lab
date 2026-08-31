#!/usr/bin/env python3
"""PAC V2.5 premise-bound paper runner.

This successor keeps the sealed causal execution engine and V2.4 all-cost accounting.  It adds a
pure paid-overshoot/runway detector, lifetime one-fill-per-mint admission, an executable
premise-break exit, and a fail-safe cross-venue transition for every unpriceable curve path.
There is no wallet, signer, sender or order submission in this module.
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
from types import SimpleNamespace

from .execution import IntentKind, OrderIntent, PriceUnavailable, RefusedExecution
from .feasibility import kernel_accounting
from . import pac_detector
from . import pac_v21_calibration as calibration
from . import pac_v22_feed as feed
from . import pac_v25_detector
from . import pac_v25_policy
from . import pac_v2_runner as core


INSTRUMENT = "AFTERSHOCK_PAC_V25"
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
STATE = RESEARCH / f"{INSTRUMENT}_RUNNER_STATE.json"
LEDGER = RESEARCH / f"{INSTRUMENT}_SCENARIO_LEDGER.jsonl"
LOCK = RESEARCH / f"{INSTRUMENT}_RUNNER.lock"
SCAN_INTERVAL_SECONDS = core.SCAN_INTERVAL_SECONDS
_CONFIG_LOCK = threading.RLock()
_SEEN_FILLED_MINTS: frozenset[str] = frozenset()
_ACTIVE_LEDGER = LEDGER


@dataclass(frozen=True)
class RuntimeProof:
    seal_sha256: str
    activation_unix_nanos: int
    calibration: calibration.Calibration

    def __post_init__(self) -> None:
        if (not isinstance(self.seal_sha256, str) or len(self.seal_sha256) != 64
                or any(char not in "0123456789abcdef" for char in self.seal_sha256)):
            raise RefusedExecution("PAC V2.5 runtime seal hash is invalid")
        if type(self.activation_unix_nanos) is not int or self.activation_unix_nanos <= 0:
            raise RefusedExecution("PAC V2.5 activation clock is invalid")
        if not isinstance(self.calibration, calibration.Calibration):
            raise RefusedExecution("PAC V2.5 runtime lacks typed processed calibration")
        if max(self.calibration.last_processed_unix_nanos,
               self.calibration.last_attested_unix_nanos) >= self.activation_unix_nanos:
            raise RefusedExecution("PAC V2.5 activation must follow inherited attested calibration")


class _DetectorAdapter:
    pac_detector = pac_detector

    @staticmethod
    def qualify(events, *, reaction_p90_nanos: int, quote_input_lamports: int):
        if events and events[0].mint in _SEEN_FILLED_MINTS:
            return None
        feed.load_health(require_fresh=True)
        result = pac_v25_detector.qualify(
            events, processed_p90_nanos=reaction_p90_nanos,
            quote_input_lamports=quote_input_lamports)
        if result is None:
            return None
        return SimpleNamespace(
            evidence_indices=result.evidence_indices,
            evidence_event_ids=result.evidence_event_ids,
            dwell_nanos=result.dwell_nanos,
            buyer_breadth=result.buyer_breadth_ex_seller,
            largest_observed_sell_lamports=result.shock_lamports,
            reserve_cover_lamports=result.reserve_cover_lamports,
        )


_DETECTOR = _DetectorAdapter()


def _history(path: pathlib.Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RefusedExecution(f"PAC V2.5 ledger line {number} is malformed") from exc
        core._validate_ledger(row)
        rows.append(row)
    return rows


def _premise_floor(entry_id: str) -> int:
    rows = _history(_ACTIVE_LEDGER)
    fill = next((row for row in reversed(rows)
                 if row.get("kind") == "entry_filled" and row.get("entry_id") == entry_id), None)
    if fill is None:
        raise RefusedExecution("PAC V2.5 premise lookup lacks entry fill")
    decision = next((row for row in reversed(rows)
                     if row.get("kind") == "entry_decision"
                     and row.get("decision_id") == fill.get("decision_id")), None)
    floor = None if decision is None else decision.get("reserve_cover_lamports")
    if type(floor) is not int or floor <= 0:
        raise RefusedExecution("PAC V2.5 premise lookup lacks an exact reserve floor")
    return floor


def _open_premise_exit(state: dict, position: core.OpenPosition, reserve,
                       quote: dict, net: int, *, now: int, floor: int) -> list[dict]:
    action = pac_v25_policy.ExitAction.EXIT_PREMISE_BREAK.value
    decision_id = core._hash({
        "instrument": INSTRUMENT, "side": "EXIT", "mint": position.mint,
        "entry_id": position.entry_id, "action": action, "decision_unix_nanos": now,
        "state": position.last_state, "net_quote": net, "premise_floor": floor})
    state["pending_order"] = {
        "side": "EXIT", "mint": position.mint, "amount": position.token_atoms,
        "min_out": max(1, quote["out_amount"] * (core.SLIPPAGE_DEN - core.SLIPPAGE_BPS)
                       // core.SLIPPAGE_DEN),
        "decision_id": decision_id, "decision_unix_nanos": now,
        "target_unix_nanos": now + state["reaction_p90_nanos"],
        "minimum_context_slot": position.last_context_slot,
        "action": action, "entry_id": position.entry_id,
        "observation_failures": 0, "last_observation_failure": None,
    }
    return [core._ledger_row(state, "exit_decision", {
        "mint": position.mint, "entry_id": position.entry_id,
        "decision_id": decision_id, "action": action, "decision_unix_nanos": now,
        "target_unix_nanos": state["pending_order"]["target_unix_nanos"],
        "minimum_context_slot": position.last_context_slot,
        "decision_net_exit_lamports": net, "premise_floor_lamports": floor,
        "observed_real_quote_lamports": reserve.real_quote})]


def _v25_service_position(state: dict, provider, pumpswap_provider, *, now: int) -> list[dict]:
    if state["open_position"] is None or state["pending_order"] is not None:
        return []
    position = core.OpenPosition(**state["open_position"])
    if now < position.entry_unix_nanos:
        return []
    graduation = core._refresh_and_check_graduation(
        state, position, provider, pumpswap_provider, now=now)
    if graduation is not None:
        return graduation
    position = core.OpenPosition(**state["open_position"])
    reserve = feed.ReserveState(**position.last_state)
    try:
        quote = kernel_accounting(
            reserve, OrderIntent(IntentKind.EXACT_TOKEN_SELL, position.token_atoms, 1))
        net = quote["wallet_delta_lamports"]
        if net <= 0:
            raise PriceUnavailable("non-positive full-position curve exit")
    except PriceUnavailable:
        # A throttled refresh may have returned without proving the curve live.  Never resolve from
        # the stale curve state: every unpriceable path first gets the bounded PumpSwap route test.
        if position.graduated_first_seen_unix_nanos == 0:
            position.graduated_first_seen_unix_nanos = now
            state["open_position"] = asdict(position)
        return core._open_venue_transition(state, position, now=now)
    floor = _premise_floor(position.entry_id)
    if reserve.real_quote < floor:
        return _open_premise_exit(state, position, reserve, quote, net, now=now, floor=floor)
    return _ORIGINAL_SERVICE(state, provider, pumpswap_provider, now=now)


def _v25_complete_pending(state: dict, provider, pumpswap_provider, *, now: int) -> list[dict]:
    pending = state.get("pending_order")
    prior_open = state.get("open_position")
    rows = _ORIGINAL_COMPLETE(state, provider, pumpswap_provider, now=now)
    if (pending is None or pending.get("side") != "EXIT" or pending.get("venue") is not None
            or prior_open is None):
        return rows
    bypass_reasons = {
        "EXIT_SNAPSHOT_PERMANENT_REFUSAL", "UNAVAILABLE_OR_NET_NEGATIVE_DUST"}
    if not any(row.get("kind") == "resolved" and row.get("reason") in bypass_reasons
               for row in rows):
        return rows
    # Restore the still-owned paper position and route the causal failure through PumpSwap.  The
    # discarded terminal row has not been committed yet, so no ledger history is rewritten.
    position = core.OpenPosition(**prior_open)
    position.graduated_first_seen_unix_nanos = (
        position.graduated_first_seen_unix_nanos or now)
    state["open_position"] = asdict(position)
    state["pending_order"] = None
    return core._open_venue_transition(state, position, now=now)


_ORIGINAL_SERVICE = core._service_position
_ORIGINAL_COMPLETE = core._complete_pending


def _bridge(proof: RuntimeProof):
    if not isinstance(proof, RuntimeProof):
        raise RefusedExecution("PAC V2.5 runner requires manifest-derived runtime proof")
    authority = SimpleNamespace(
        artifact_sha256=proof.calibration.artifact_sha256,
        reaction_p90_nanos=proof.calibration.processed_p90_nanos,
        last_land_unix_nanos=proof.calibration.last_processed_unix_nanos,
        last_attested_unix_nanos=proof.calibration.last_attested_unix_nanos)
    return SimpleNamespace(seal_sha256=proof.seal_sha256,
                           activation_unix_nanos=proof.activation_unix_nanos,
                           calibration=authority)


@contextmanager
def _configured_core():
    with _CONFIG_LOCK:
        originals = (core.INSTRUMENT, core.detector, core.feed, core.policy,
                     core._service_position, core._complete_pending)
        core.INSTRUMENT, core.detector, core.feed, core.policy = (
            INSTRUMENT, _DETECTOR, feed, pac_v25_policy)
        core._service_position = _v25_service_position
        core._complete_pending = _v25_complete_pending
        try:
            yield
        finally:
            (core.INSTRUMENT, core.detector, core.feed, core.policy,
             core._service_position, core._complete_pending) = originals


def _run_once_at(proof: RuntimeProof, provider, pumpswap_provider, *, now: int,
                 quote_input_lamports: int | None = None,
                 state_path: pathlib.Path = STATE, ledger_path: pathlib.Path = LEDGER,
                 events_path: pathlib.Path = feed.EVENTS,
                 receipts_path: pathlib.Path = feed.RECEIPTS,
                 initialize_at_eof: bool = True) -> dict:
    global _SEEN_FILLED_MINTS, _ACTIVE_LEDGER
    with _configured_core():
        _ACTIVE_LEDGER = pathlib.Path(ledger_path)
        _SEEN_FILLED_MINTS = frozenset(
            row["mint"] for row in _history(_ACTIVE_LEDGER)
            if row.get("kind") == "entry_filled")
        return core._run_once_at(
            _bridge(proof), provider, pumpswap_provider, now=now,
            quote_input_lamports=quote_input_lamports,
            state_path=pathlib.Path(state_path), ledger_path=_ACTIVE_LEDGER,
            events_path=pathlib.Path(events_path), receipts_path=pathlib.Path(receipts_path),
            initialize_at_eof=initialize_at_eof)


def run_once(proof: RuntimeProof, provider, pumpswap_provider, **kwargs) -> dict:
    return _run_once_at(proof, provider, pumpswap_provider, now=time.time_ns(), **kwargs)


def _lock(path: pathlib.Path = LOCK):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RefusedExecution("another PAC V2.5 runner owns the state lock") from exc
    return handle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2.5 premise-bound paper runner")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=SCAN_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    try:
        from .pac_v25_manifest import load_runtime_proof
        proof = load_runtime_proof()
        provider = core.PublicRpcSnapshotProvider()
        pumpswap_provider = core.PumpSwapProvider()
        with _lock():
            while True:
                started = time.monotonic()
                try:
                    result = run_once(proof, provider, pumpswap_provider)
                except RefusedExecution as exc:
                    result = {"status": "CYCLE_REFUSED", "reason": str(exc)[:240]}
                    print(json.dumps(result, sort_keys=True), flush=True)
                    if args.once:
                        return 2
                else:
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
