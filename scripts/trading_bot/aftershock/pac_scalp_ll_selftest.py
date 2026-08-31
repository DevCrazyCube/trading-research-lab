#!/usr/bin/env python3
"""Negative-control battery for the low-latency PAC measurement foundation."""
from __future__ import annotations

import json
import base64
import hashlib
from dataclasses import replace
import pathlib
import tempfile
import time
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .execution import RefusedExecution, ReserveState
from . import pac_scalp_ll_accounting as accounting
from . import pac_scalp_ll_clock as clocking
from . import pac_scalp_ll_ledger as ledger
from . import pac_scalp_ll_engine as engine
from . import pac_scalp_ll_marklog as marks
from . import pac_scalp_ll_policy as policy
from . import pac_scalp_ll_route as routes
from . import pac_scalp_ll_venue as venue
from . import pac_scalp_ll_tx as tx
from .pac_v2_snapshot import LandingSnapshot, SnapshotUnavailable
from .pac_v2_pumpswap import PumpSwapObservation, PumpSwapReserves


CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def refuses(fn, label: str) -> None:
    try:
        fn()
    except (RefusedExecution, ValueError):
        check(True, label)
        return
    raise AssertionError(label)


def _authority() -> marks.Authority:
    return marks.Authority("AFTERSHOCK_PAC_SCALP_LL", "a" * 64, 1_000,
                           "b" * 64, "c" * 64)


def _record_fields(**updates) -> dict:
    base = {
        "lifecycle": "OPEN", "route_arm": routes.PUBLIC_CONTROL,
        "provider_id": "public-mainnet", "venue": "PUMP_CURVE",
        "entry_id": "d" * 64, "mint": "mintA", "evidence_source": "processed_account",
        "raw_evidence_sha256": "e" * 64, "source_received_unix_nanos": None,
        "request_started_unix_nanos": 1_100, "evidence_received_unix_nanos": 1_200,
        "decision_unix_nanos": 1_201, "target_unix_nanos": 2_001,
        "context_slot": 44,
        "reserve_state": {"virtual_quote": 30, "virtual_token": 100,
                          "real_quote": 20, "real_token": 90, "complete": False},
        "entry_all_in_lamports": 100,
        "wallet_proceeds_lamports": 90, "ata_rent_reclaim_lamports": 15,
        "ata_close_cost_lamports": 5, "failed_attempt_cost_lamports": 2,
        "liquidation_equity_lamports": 98,
        "peak_liquidation_equity_lamports": 110, "priceable": True,
        "decision_id": "f" * 64, "attempt_id": None, "terminal_reason": None,
    }
    base.update(updates)
    return base


def main() -> int:
    # One exact equity convention everywhere.
    eq = accounting.liquidation_equity(
        wallet_proceeds_lamports=90, ata_rent_lamports=15,
        ata_close_cost_lamports=5, failed_attempt_cost_lamports=2)
    check(eq.equity_lamports == 98, "equity includes conditional rent and every known cost once")
    check(accounting.return_fraction(equity_lamports=98, entry_all_in_lamports=100) == (-2, 100),
          "terminal return uses the same equity numerator")
    no_close = accounting.settled_equity(
        wallet_proceeds_lamports=90, ata_rent_lamports=15,
        ata_close_cost_lamports=5, failed_attempt_cost_lamports=2,
        ata_close_succeeded=False)
    check(no_close.equity_lamports == 83 and no_close.ata_rent_reclaim_lamports == 0,
          "failed ATA close spends its cost and never invents rent reclaim")
    refuses(lambda: accounting.liquidation_equity(
        wallet_proceeds_lamports=0, ata_rent_lamports=15,
        ata_close_cost_lamports=5, failed_attempt_cost_lamports=0),
        "net-nonpositive exit cannot invent liquidation equity")
    refuses(lambda: accounting.liquidation_equity(
        wallet_proceeds_lamports=90, ata_rent_lamports=4,
        ata_close_cost_lamports=5, failed_attempt_cost_lamports=0),
        "ATA close cost cannot exceed reclaimed rent")

    position = policy.Position(100, 1_000, 50, 0)
    check(policy.decide(position, decision_unix_nanos=1_001,
                        liquidation_equity_lamports=88, real_quote_lamports=1_000).action
          == policy.ExitAction.EXIT_HARD_STOP, "fresh all-cost -12% stop fires")
    check(policy.decide(position, decision_unix_nanos=1_001,
                        liquidation_equity_lamports=89, real_quote_lamports=1_000).action
          == policy.ExitAction.HOLD, "-11% remains above the a-priori stop")
    check(policy.decide(position, decision_unix_nanos=1_000 + policy.MAX_HOLD_NANOS,
                        liquidation_equity_lamports=87, real_quote_lamports=1_000).action
          == policy.ExitAction.EXIT_HORIZON, "absolute horizon precedes simultaneous stop")
    check(policy.decide(position, decision_unix_nanos=1_001,
                        liquidation_equity_lamports=None, real_quote_lamports=None).action
          == policy.ExitAction.HOLD, "unavailable curve quote routes elsewhere, not directly to rug")

    check(clocking.decision_after_evidence(lambda: 301, [100, 300]) == 301,
          "decision clock is sampled after newest evidence")
    refuses(lambda: clocking.decision_after_evidence(lambda: 299, [100, 300]),
            "back-dated decision refuses")
    check(clocking.landing_target(decision_unix_nanos=301, calibrated_p90_nanos=800) == 1_101,
          "landing target is strictly decision plus calibration")

    campaign = "9" * 64
    for pair in range(8):
        assigned = {routes.assigned_arm(campaign, pair, member) for member in (0, 1)}
        check(assigned == routes.ARMS, f"matched pair {pair} contains exactly one sample per arm")

    env = {
        "PAC_SCALP_LL_PUBLIC_SUBMIT_RPC_URL": "https://api.mainnet-beta.solana.com",
        "PAC_SCALP_LL_PUBLIC_OBSERVE_RPC_URL": "https://api.mainnet-beta.solana.com",
        "PAC_SCALP_LL_PUBLIC_PROVIDER_ID": "solana-public", "PAC_SCALP_LL_PUBLIC_REGION": "global",
        "PAC_SCALP_LL_INTERVENTION_SUBMIT_RPC_URL": "https://amsterdam.example.net/submit?key=secret",
        "PAC_SCALP_LL_INTERVENTION_OBSERVE_RPC_URL": "https://observe-amsterdam.example.net/rpc?key=secret",
        "PAC_SCALP_LL_INTERVENTION_PROVIDER_ID": "paid-test", "PAC_SCALP_LL_INTERVENTION_REGION": "ams",
    }
    env["PAC_SCALP_LL_PUBLIC_CONFIG_FINGERPRINT_SHA256"] = routes.derived_config_fingerprint(
        provider_id="solana-public", region="global",
        submit_url=env["PAC_SCALP_LL_PUBLIC_SUBMIT_RPC_URL"],
        observe_url=env["PAC_SCALP_LL_PUBLIC_OBSERVE_RPC_URL"])
    env["PAC_SCALP_LL_INTERVENTION_CONFIG_FINGERPRINT_SHA256"] = routes.derived_config_fingerprint(
        provider_id="paid-test", region="ams",
        submit_url=env["PAC_SCALP_LL_INTERVENTION_SUBMIT_RPC_URL"],
        observe_url=env["PAC_SCALP_LL_INTERVENTION_OBSERVE_RPC_URL"])
    with patch.dict("os.environ", env, clear=True):
        public, paid = routes.load_routes_from_env()
        check(public.arm == routes.PUBLIC_CONTROL and paid.arm == routes.LOW_LATENCY_INTERVENTION,
              "both explicit route arms load atomically")
        check("secret" not in paid.submit_endpoint_identity,
              "persisted endpoint identity never contains URL credentials")
    missing = dict(env); missing.pop("PAC_SCALP_LL_INTERVENTION_SUBMIT_RPC_URL")
    with patch.dict("os.environ", missing, clear=True):
        refuses(routes.load_routes_from_env, "missing paid route refuses instead of public fallback")
    same = dict(env)
    same["PAC_SCALP_LL_INTERVENTION_SUBMIT_RPC_URL"] = env["PAC_SCALP_LL_PUBLIC_SUBMIT_RPC_URL"]
    with patch.dict("os.environ", same, clear=True):
        refuses(routes.load_routes_from_env, "shared control/intervention submit endpoint refuses")
    same_observe = dict(env)
    same_observe["PAC_SCALP_LL_INTERVENTION_OBSERVE_RPC_URL"] = env["PAC_SCALP_LL_PUBLIC_OBSERVE_RPC_URL"]
    with patch.dict("os.environ", same_observe, clear=True):
        refuses(routes.load_routes_from_env, "shared control/intervention observe endpoint refuses")
    changed_secret = dict(env)
    changed_secret["PAC_SCALP_LL_INTERVENTION_SUBMIT_RPC_URL"] = \
        "https://amsterdam.example.net/submit?key=changed"
    with patch.dict("os.environ", changed_secret, clear=True):
        refuses(routes.load_routes_from_env,
                "credential/path mutation cannot retain the old safe route fingerprint")
    refuses(lambda: routes.assigned_arm(campaign, 0, True), "boolean member index refuses")

    authority = _authority()
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "marks.jsonl"
        built = marks.build_record(authority, marks.JournalHead(), **_record_fields())
        check(built["lifecycle"] == "OPEN", "mark semantic builder validates an open mark")
        refuses(lambda: marks.append(path, authority, marks.JournalHead(), **_record_fields()),
                "standalone mark authority is disabled in favour of unified evidence journal")

    refuses(lambda: marks.build_record(authority, marks.JournalHead(), **_record_fields(
        decision_unix_nanos=1_199)), "mark decision cannot predate its evidence receipt")
    refuses(lambda: marks.build_record(authority, marks.JournalHead(), **_record_fields(
        priceable=False)), "unpriceable mark cannot retain invented proceeds/equity")
    refuses(lambda: marks.build_record(authority, marks.JournalHead(), **_record_fields(
        liquidation_equity_lamports=99)), "mark equity must reconcile exactly")
    refuses(lambda: marks.build_record(authority, marks.JournalHead(), **_record_fields(
        lifecycle="TERMINAL", terminal_reason=None)), "terminal mark requires a typed reason")
    refuses(lambda: marks.build_record(authority, marks.JournalHead(), **_record_fields(
        source_received_unix_nanos=1_300)), "source receipt cannot follow trusted evidence receipt")
    refuses(lambda: marks.build_record(authority, marks.JournalHead(), **_record_fields(
        peak_liquidation_equity_lamports=97)), "peak equity cannot be below observed equity")
    refuses(lambda: marks.build_record(authority, marks.JournalHead(), **_record_fields(
        lifecycle="TERMINAL", terminal_reason="X", attempt_id="1" * 64,
        decision_unix_nanos=1_300, target_unix_nanos=2_300)),
        "terminal evidence cannot predate its landing target")
    refuses(lambda: marks.build_record(authority, marks.JournalHead(), **_record_fields(
        wallet_proceeds_lamports=0, ata_rent_reclaim_lamports=105,
        ata_close_cost_lamports=5, liquidation_equity_lamports=98)),
        "zero wallet proceeds cannot be rescued into a priceable mark by rent")

    cost = routes.AttemptCost(5_000, 100_000, 10_000, 5_000, 1_000_000, 100)
    check(cost.onchain_lamports == 120_000,
          "priority fee, tip and failed attempts are all explicit route costs")

    private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"pac-scalp-ll-test").digest())
    profile = tx.Profile(100_000, 200_000, tx.MIN_SWQOS_TIP_LAMPORTS,
                         tx.TIP_ACCOUNTS[0])
    memo = tx.campaign_memo("9" * 64, routes.PUBLIC_CONTROL, 0)
    encoded, signature, payer = tx.build(
        private, recent_blockhash=bytes(range(32)), memo=memo, profile=profile)
    parsed = tx.verify(encoded, expected_memo=memo, expected_profile=profile)
    check(parsed["signature"] == signature and parsed["fee_payer"] == payer,
          "calibration-only tip+priority+memo wire self-parses and signature-verifies")
    damaged_wire = bytearray(base64.b64decode(encoded)); damaged_wire[-1] ^= 1
    refuses(lambda: tx.verify(base64.b64encode(damaged_wire).decode(),
                              expected_memo=memo, expected_profile=profile),
            "calibration wire mutation cannot masquerade as the frozen no-trade profile")
    refuses(lambda: tx.Profile(100_000, 200_000, tx.MIN_SWQOS_TIP_LAMPORTS - 1,
                               tx.TIP_ACCOUNTS[0]),
            "submit intervention profile refuses a below-provider-minimum tip")

    with tempfile.TemporaryDirectory() as directory:
        state_path = pathlib.Path(directory) / "state.json"
        ledger_path = pathlib.Path(directory) / "ledger.jsonl"
        state = {"instrument_id": "AFTERSHOCK_PAC_SCALP_LL", "seal_sha256": "a" * 64,
                 "activation_unix_nanos": 1_000, "ledger_head": ledger.genesis(),
                 "calibration_sha256": "b" * 64, "campaign_sha256": "c" * 64,
                 "pending_ledger_rows": [], "ledger_semantic_state": ledger.semantic_genesis()}

        def event_body(*, entry_id, payload, event_unix_nanos=2_000):
            return {"entry_id": entry_id, "mint": "m1", "arm": routes.PUBLIC_CONTROL,
                    "provider_id": "public", "event_unix_nanos": event_unix_nanos,
                    "submit_endpoint_identity": "https://submit.example",
                    "observe_endpoint_identity": "https://observe.example",
                    "config_fingerprint_sha256": "3" * 64,
                    "entry_cost_profile_sha256": "4" * 64,
                    "exit_cost_profile_sha256": "5" * 64,
                    "ata_close_cost_profile_sha256": "6" * 64,
                    "payload": payload}

        entry_decision_payload = {
            "decision_id": "d" * 64, "evidence_sha256": "e" * 64,
            "quote_input_lamports": 50, "min_tokens_out": 1,
            "decision_unix_nanos": 1_100, "target_unix_nanos": 1_900,
            "minimum_context_slot": 1}
        entry_fill_payload = {
            "decision_id": "d" * 64, "attempt_id": "f" * 64,
            "snapshot_sha256": "1" * 64, "landing_unix_nanos": 2_000,
            "token_atoms": 10, "quote_input_lamports": 50,
            "curve_fee_lamports": 20, "route_cost_lamports": 10,
            "ata_rent_lamports": 20, "entry_all_in_lamports": 100}
        row1 = ledger.make_row(state, "ENTRY_DECISION", event_body(
            entry_id=None, payload=entry_decision_payload, event_unix_nanos=1_100))
        state["pending_ledger_rows"].append(row1)
        row2 = ledger.make_row(state, "ENTRY_FILLED", event_body(
            entry_id="2" * 64, payload=entry_fill_payload))
        state["pending_ledger_rows"].clear()
        # Build the real two-row chain in one crash-safe transaction.
        row1 = ledger.make_row(state, "ENTRY_DECISION", event_body(
            entry_id=None, payload=entry_decision_payload, event_unix_nanos=1_100))
        state["pending_ledger_rows"].append(row1)
        row2 = ledger.make_row(state, "ENTRY_FILLED", event_body(
            entry_id="2" * 64, payload=entry_fill_payload))
        state["pending_ledger_rows"].clear()
        ledger.commit(state, [row1, row2], state_path=state_path, ledger_path=ledger_path)
        verified = ledger.verify(ledger_path, instrument_id=state["instrument_id"],
                                 seal_sha256=state["seal_sha256"],
                                 activation_unix_nanos=state["activation_unix_nanos"],
                                 calibration_sha256=state["calibration_sha256"],
                                 campaign_sha256=state["campaign_sha256"])
        check(verified == state["ledger_head"] and verified["sequence"] == 2,
              "ledger appends new rows once and verifies the full authority chain")
        forged_state = {**state, "ledger_head": ledger.genesis(),
                        "pending_ledger_rows": [],
                        "ledger_semantic_state": ledger.semantic_genesis()}
        forged_decision = ledger.make_row(
            forged_state, "ENTRY_DECISION", event_body(
                entry_id=None, payload=entry_decision_payload, event_unix_nanos=1_100))
        forged_state["pending_ledger_rows"].append(forged_decision)
        forged_fill_body = event_body(entry_id="2" * 64, payload=entry_fill_payload)
        forged_fill_body["arm"] = routes.LOW_LATENCY_INTERVENTION
        forged_fill = ledger.make_row(forged_state, "ENTRY_FILLED", forged_fill_body)
        forged_state["pending_ledger_rows"].clear()
        with tempfile.TemporaryDirectory() as forged_directory:
            refuses(lambda: ledger.commit(
                forged_state, [forged_decision, forged_fill],
                state_path=pathlib.Path(forged_directory) / "state.json",
                ledger_path=pathlib.Path(forged_directory) / "ledger.jsonl"),
                "rehash-valid entry fill cannot switch provider arm after decision")
        stale = dict(state); stale["ledger_head"] = ledger.genesis()
        refuses(lambda: ledger.flush(stale, state_path=state_path, ledger_path=ledger_path),
                "stale ledger offset refuses instead of duplicating rows")
        lines = ledger_path.read_text().splitlines()
        damaged = json.loads(lines[0]); damaged["mint"] = "tampered"
        lines[0] = json.dumps(damaged, sort_keys=True, separators=(",", ":"))
        ledger_path.write_text("\n".join(lines) + "\n")
        refuses(lambda: ledger.verify(ledger_path, instrument_id=state["instrument_id"],
                                      seal_sha256=state["seal_sha256"],
                                      activation_unix_nanos=state["activation_unix_nanos"],
                                      calibration_sha256=state["calibration_sha256"],
                                      campaign_sha256=state["campaign_sha256"]),
                "historical ledger tampering breaks startup verification")

    reserved_state = {"instrument_id": "AFTERSHOCK_PAC_SCALP_LL", "seal_sha256": "a" * 64,
                      "activation_unix_nanos": 1_000, "ledger_head": ledger.genesis(),
                      "calibration_sha256": "b" * 64, "campaign_sha256": "c" * 64,
                      "pending_ledger_rows": [],
                      "ledger_semantic_state": ledger.semantic_genesis()}
    refuses(lambda: ledger.make_row(reserved_state, "ENTRY_DECISION", {"kind": "overridden"}),
            "ledger body cannot override kind/authority/chain fields")
    with tempfile.TemporaryDirectory() as directory:
        state_path = pathlib.Path(directory) / "state.json"
        ledger_path = pathlib.Path(directory) / "ledger.jsonl"
        state = dict(reserved_state); state["pending_ledger_rows"] = []
        row = ledger.make_row(state, "ENTRY_DECISION", event_body(
            entry_id=None, payload=entry_decision_payload, event_unix_nanos=1_100))
        real_write = ledger.os.write

        def short_write(descriptor, payload):
            prefix = payload[:17]
            real_write(descriptor, prefix)
            return len(prefix)

        try:
            with patch.object(ledger.os, "write", side_effect=short_write):
                ledger.commit(state, [row], state_path=state_path, ledger_path=ledger_path)
        except OSError:
            check(True, "injected mid-record short write is visible")
        else:
            raise AssertionError("injected short write did not fail")
        ledger.flush(state, state_path=state_path, ledger_path=ledger_path)
        check(ledger.verify(ledger_path, instrument_id=state["instrument_id"],
                            seal_sha256=state["seal_sha256"],
                            activation_unix_nanos=state["activation_unix_nanos"],
                            calibration_sha256=state["calibration_sha256"],
                            campaign_sha256=state["campaign_sha256"])["sequence"] == 1,
              "restart completes only the exact state-pinned partial payload")
        lock_path = ledger_path.with_name(ledger_path.name + ".writer.lock")
        with lock_path.open("a+b") as held:
            ledger.fcntl.flock(held.fileno(), ledger.fcntl.LOCK_EX | ledger.fcntl.LOCK_NB)
            refuses(lambda: ledger.flush(
                state, state_path=state_path, ledger_path=ledger_path),
                "a second writer cannot enter the ledger append/state CAS")
            ledger.fcntl.flock(held.fileno(), ledger.fcntl.LOCK_UN)

    def route(arm=routes.PUBLIC_CONTROL, provider="public", host="public.example") -> routes.Route:
        submit, observe = f"https://{host}/submit", f"https://observe-{host}/rpc"
        fingerprint = routes.derived_config_fingerprint(
            provider_id=provider, region="ams", submit_url=submit, observe_url=observe)
        return routes.Route(arm, provider, "ams", submit, observe, f"https://{host}",
                            f"https://observe-{host}", fingerprint)

    exit_cost = routes.AttemptCost(1, 2, 3, 4, 100, 100)
    close_cost = routes.AttemptCost(1, 0, 0, 0, 0, 1)

    def runtime(arm=routes.PUBLIC_CONTROL, provider="public", host="public.example"):
        bound = route(arm, provider, host)
        return engine.ArmRuntime(
            arm, provider, 800, "3" * 64, "4" * 64,
            bound.submit_endpoint_identity, bound.observe_endpoint_identity,
            bound.config_fingerprint_sha256, exit_cost, exit_cost, close_cost)

    def open_position(mint: str = "mintA", arm=routes.PUBLIC_CONTROL,
                      provider="public") -> engine.Position:
        bound_runtime = runtime(arm, provider,
                                "public.example" if arm == routes.PUBLIC_CONTROL else "paid.example")
        # 50 quote + 20 fee + 10 attempt + 20 rent = 100 all-in.
        return engine.Position(
            mint=mint, token_atoms=1_000, quote_input_lamports=50,
            entry_curve_fee_lamports=20, entry_attempt_cost_lamports=10,
            ata_rent_lamports=20, entry_all_in_lamports=100,
            entry_unix_nanos=1_000, peak_liquidation_equity_lamports=0,
            failed_exit_cost_lamports=0, entry_id="2" * 64,
            last_context_slot=10,
            last_state={"virtual_quote": 1_000, "virtual_token": 10_000,
                        "real_quote": 900, "real_token": 9_000, "complete": False},
            arm=arm, provider_id=provider, calibration_sha256="3" * 64,
            campaign_sha256="4" * 64,
            submit_endpoint_identity=bound_runtime.submit_endpoint_identity,
            observe_endpoint_identity=bound_runtime.observe_endpoint_identity,
            config_fingerprint_sha256=bound_runtime.config_fingerprint_sha256,
            entry_cost_profile_sha256=engine.cost_profile_sha256(bound_runtime.entry_attempt_cost),
            exit_cost_profile_sha256=engine.cost_profile_sha256(bound_runtime.exit_attempt_cost),
            ata_close_cost_profile_sha256=engine.cost_profile_sha256(
                bound_runtime.ata_close_attempt_cost))

    public_runtime = runtime()

    def snap(mint: str = "mintA", *, complete: bool = False, receipt: int = 1_200) -> LandingSnapshot:
        return LandingSnapshot(
            mint=mint, bonding_curve="curve", modeled_target_unix_nanos=1_050,
            minimum_context_slot=10, request_started_unix_nanos=1_100,
            response_received_unix_nanos=receipt, context_slot=11,
            state=ReserveState(1_000, 10_000, 900, 9_000, complete),
            endpoint_scheme_host="https://observe-public.example", raw_response_sha256="5" * 64)

    complete_decision = engine.evaluate_snapshot(
        open_position(), public_runtime, snap(complete=True),
        request_clock=engine.ClockStamp(1_100, 100, "boot"),
        evidence_clock=engine.ClockStamp(1_200, 200, "boot"),
        decision_clock=engine.ClockStamp(1_201, 201, "boot"))
    check(complete_decision.action == "VENUE_TRANSITION_REQUIRED",
          "complete/zeroed curve routes to cross-venue before any full loss")
    cached = LandingSnapshot(
        mint="mintA", bonding_curve="curve", modeled_target_unix_nanos=1,
        minimum_context_slot=10, request_started_unix_nanos=1,
        response_received_unix_nanos=999, context_slot=11,
        state=ReserveState(1_000, 10_000, 900, 9_000, True),
        endpoint_scheme_host="https://observe-public.example", raw_response_sha256="5" * 64)
    refuses(lambda: engine.evaluate_snapshot(
        open_position(), public_runtime, cached,
        request_clock=engine.ClockStamp(1_100, 100, "boot"),
        evidence_clock=engine.ClockStamp(1_200, 200, "boot"),
        decision_clock=engine.ClockStamp(1_201, 201, "boot")),
        "cached provider snapshot requested before trusted wrapper call refuses")
    check(all(engine.curve_failure_requires_cross_venue(reason)
              for reason in engine.CURVE_FAILURES_REQUIRING_CROSS_VENUE),
          "every known curve full-loss shortcut is classified cross-venue-first")
    refuses(lambda: engine.evaluate_snapshot(
        open_position(), public_runtime, snap(),
        request_clock=engine.ClockStamp(1_100, 100, "boot"),
        evidence_clock=engine.ClockStamp(1_200, 200, "boot"),
        decision_clock=engine.ClockStamp(1_199, 201, "boot")),
            "service decision cannot predate blocking snapshot receipt")
    wrong_endpoint = LandingSnapshot(
        mint="mintA", bonding_curve="curve", modeled_target_unix_nanos=1_050,
        minimum_context_slot=10, request_started_unix_nanos=1_100,
        response_received_unix_nanos=1_200, context_slot=11,
        state=ReserveState(1_000, 10_000, 900, 9_000, True),
        endpoint_scheme_host="https://public.example", raw_response_sha256="5" * 64)
    refuses(lambda: engine.evaluate_snapshot(
        open_position(), public_runtime, wrong_endpoint,
        request_clock=engine.ClockStamp(1_100, 100, "boot"),
        evidence_clock=engine.ClockStamp(1_200, 200, "boot"),
        decision_clock=engine.ClockStamp(1_201, 201, "boot")),
        "snapshot endpoint must match the assigned observe route")
    refuses(lambda: engine.ArmRuntime(
        "NOT_AN_ARM", "", 800, "3" * 64, "4" * 64,
        "https://x", "https://y", "8" * 64, exit_cost, exit_cost, close_cost),
        "unknown arm and empty provider refuse")

    class SlowProvider:
        def __init__(self, fail: bool = False, delay: float = 0.04,
                     endpoint: str = "https://observe-public.example"):
            self.fail = fail
            self.delay = delay
            self.endpoint = endpoint

        def capture(self, mint, target, minimum_slot):
            time.sleep(self.delay)
            if self.fail:
                raise SnapshotUnavailable("fixture unavailable")
            return LandingSnapshot(
                mint=mint, bonding_curve="curve", modeled_target_unix_nanos=target,
                minimum_context_slot=minimum_slot, request_started_unix_nanos=target,
                response_received_unix_nanos=target + 1, context_slot=minimum_slot,
                state=ReserveState(1_000, 10_000, 900, 9_000, False),
                endpoint_scheme_host=self.endpoint, raw_response_sha256="6" * 64)

    positions = {f"mint{i}": (open_position(f"mint{i}"), public_runtime) for i in range(4)}
    public_binding = engine.ProviderBinding(route(), "3" * 64, "4" * 64, SlowProvider())
    started = time.monotonic()
    decisions = engine.service_concurrently(
        positions, {routes.PUBLIC_CONTROL: public_binding}, max_workers=4)
    elapsed = time.monotonic() - started
    check(len(decisions) == 4 and elapsed < 0.14,
          "four position observations run concurrently instead of serial RPC dwell")
    failed = engine.service_concurrently(
        {"mintF": (open_position("mintF"), public_runtime)},
        {routes.PUBLIC_CONTROL: engine.ProviderBinding(
            route(), "3" * 64, "4" * 64, SlowProvider(fail=True))})
    check(failed["mintF"].action == "VENUE_TRANSITION_REQUIRED",
          "provider refusal opens venue transition rather than atomic-rug classification")
    paid_runtime = runtime(routes.LOW_LATENCY_INTERVENTION, "paid", "paid.example")
    paid_position = open_position("mintP", routes.LOW_LATENCY_INTERVENTION, "paid")
    refuses(lambda: engine.service_concurrently(
        {"mintP": (paid_position, paid_runtime)},
        {routes.LOW_LATENCY_INTERVENTION: public_binding}),
        "paid runtime bound to public provider/route refuses")
    paid_binding = engine.ProviderBinding(
        route(routes.LOW_LATENCY_INTERVENTION, "paid", "paid.example"),
        "3" * 64, "4" * 64,
        SlowProvider(delay=0.01, endpoint="https://observe-paid.example"))
    slow_public = engine.ProviderBinding(
        route(), "3" * 64, "4" * 64, SlowProvider(delay=0.30))
    started = time.monotonic()
    stream = engine.iter_service_concurrently(
        {"slow": (open_position("slow"), public_runtime),
         "mintP": (paid_position, paid_runtime)},
        {routes.PUBLIC_CONTROL: slow_public,
         routes.LOW_LATENCY_INTERVENTION: paid_binding}, max_workers=2)
    first_mint, first_decision = next(stream)
    first_elapsed = time.monotonic() - started
    mixed = dict([(first_mint, first_decision), *list(stream)])
    total = time.monotonic() - started
    fast_scheduler_delay = ((mixed["mintP"].decision_clock.wall_unix_nanos
                             - mixed["mintP"].evidence_clock.wall_unix_nanos) / 1e9)
    check(first_mint == "mintP" and first_elapsed < 0.05
          and total >= 0.25 and fast_scheduler_delay < 0.05,
          "fast intervention decision is yielded for dispatch before slow control completes")
    check(mixed["mintP"].arm == routes.LOW_LATENCY_INTERVENTION
          and mixed["mintP"].provider_id == "paid"
          and mixed["mintP"].calibration_sha256 == "3" * 64,
          "service decision persists arm/provider/calibration identity end-to-end")

    big_state = ReserveState(60_000_000_000, 700_000_000_000_000,
                             30_000_000_000, 420_000_000_000_000, False)
    big_position = engine.Position(
        mint="mintBig", token_atoms=1_000_000_000, quote_input_lamports=97_000_000,
        entry_curve_fee_lamports=500_000, entry_attempt_cost_lamports=460_000,
        ata_rent_lamports=2_040_000, entry_all_in_lamports=100_000_000,
        entry_unix_nanos=1_000, peak_liquidation_equity_lamports=0,
        failed_exit_cost_lamports=0, entry_id="9" * 64, last_context_slot=10,
        last_state={"virtual_quote": big_state.virtual_quote,
                    "virtual_token": big_state.virtual_token,
                    "real_quote": big_state.real_quote, "real_token": big_state.real_token,
                    "complete": False}, arm=routes.PUBLIC_CONTROL, provider_id="public",
        calibration_sha256="3" * 64, campaign_sha256="4" * 64,
        submit_endpoint_identity=public_runtime.submit_endpoint_identity,
        observe_endpoint_identity=public_runtime.observe_endpoint_identity,
        config_fingerprint_sha256=public_runtime.config_fingerprint_sha256,
        entry_cost_profile_sha256=engine.cost_profile_sha256(public_runtime.entry_attempt_cost),
        exit_cost_profile_sha256=engine.cost_profile_sha256(public_runtime.exit_attempt_cost),
        ata_close_cost_profile_sha256=engine.cost_profile_sha256(
            public_runtime.ata_close_attempt_cost))
    big_snapshot = LandingSnapshot(
        mint="mintBig", bonding_curve="curve", modeled_target_unix_nanos=1_050,
        minimum_context_slot=10, request_started_unix_nanos=1_100,
        response_received_unix_nanos=1_200, context_slot=11, state=big_state,
        endpoint_scheme_host="https://observe-public.example", raw_response_sha256="a" * 64)
    cheap = runtime()
    expensive_exit = routes.AttemptCost(1_001, 2, 3, 4, 100, 100)
    expensive = engine.ArmRuntime(
        cheap.arm, cheap.provider_id, cheap.calibrated_p90_nanos,
        cheap.calibration_sha256, cheap.campaign_sha256,
        cheap.submit_endpoint_identity, cheap.observe_endpoint_identity,
        cheap.config_fingerprint_sha256, cheap.entry_attempt_cost,
        expensive_exit, cheap.ata_close_attempt_cost)
    evidence_clock = engine.ClockStamp(1_200, 200, "boot")
    decision_clock = engine.ClockStamp(1_201, 201, "boot")
    cheap_decision = engine.evaluate_snapshot(
        big_position, cheap, big_snapshot,
        request_clock=engine.ClockStamp(1_100, 100, "boot"),
        evidence_clock=evidence_clock, decision_clock=decision_clock)
    refuses(lambda: engine.evaluate_snapshot(
        big_position, expensive, big_snapshot,
        request_clock=engine.ClockStamp(1_100, 100, "boot"),
        evidence_clock=evidence_clock, decision_clock=decision_clock),
        "position refuses post-entry route/cost-profile drift")
    check(expensive_exit.attempt_cost_lamports - exit_cost.attempt_cost_lamports == 1_000,
          "attempt comparison isolates exact on-chain route-cost delta without reallocating infra")
    dust_exit = routes.AttemptCost(1_000, 0, 0, 0, 0, 1)
    dust_runtime = engine.ArmRuntime(
        cheap.arm, cheap.provider_id, cheap.calibrated_p90_nanos,
        cheap.calibration_sha256, cheap.campaign_sha256,
        cheap.submit_endpoint_identity, cheap.observe_endpoint_identity,
        cheap.config_fingerprint_sha256, cheap.entry_attempt_cost,
        dust_exit, cheap.ata_close_attempt_cost)
    dust_position = replace(
        open_position(),
        exit_cost_profile_sha256=engine.cost_profile_sha256(dust_exit))
    dust_decision = engine.evaluate_snapshot(
        dust_position, dust_runtime, snap(),
        request_clock=engine.ClockStamp(1_100, 100, "boot"),
        evidence_clock=engine.ClockStamp(1_200, 200, "boot"),
        decision_clock=engine.ClockStamp(1_201, 201, "boot"))
    check(dust_decision.action == "VENUE_TRANSITION_REQUIRED"
          and dust_decision.reason == "UNAVAILABLE_OR_NET_NEGATIVE_DUST",
          "net-negative curve dust opens cross-venue instead of wedging the position")

    entry_evidence = engine.ClockStamp(100, 100, "boot")
    entry_decision_clock = engine.ClockStamp(101, 101, "boot")
    entry_order = engine.make_entry_order(
        mint="mintEntry", quote_input_lamports=10_000_000, decision_state=big_state,
        minimum_context_slot=10, evidence_sha256="1" * 64,
        evidence_clock=entry_evidence, decision_clock=entry_decision_clock,
        runtime=public_runtime)
    entry_snapshot = LandingSnapshot(
        mint="mintEntry", bonding_curve="curve",
        modeled_target_unix_nanos=entry_order.target_unix_nanos,
        minimum_context_slot=10,
        request_started_unix_nanos=entry_order.target_unix_nanos,
        response_received_unix_nanos=entry_order.target_unix_nanos + 10,
        context_slot=11, state=big_state,
        endpoint_scheme_host="https://observe-public.example",
        raw_response_sha256="2" * 64)
    landed_position = engine.land_entry(
        entry_order, public_runtime, entry_snapshot,
        request_clock=engine.ClockStamp(entry_order.target_unix_nanos, 150, "boot"),
        evidence_clock=engine.ClockStamp(entry_order.target_unix_nanos + 10, 200, "boot"),
        landing_clock=engine.ClockStamp(entry_order.target_unix_nanos + 11, 201, "boot"))
    check(landed_position.entry_unix_nanos == entry_order.target_unix_nanos + 11
          and landed_position.entry_attempt_cost_lamports
          == public_runtime.entry_attempt_cost.all_cost_lamports,
          "entry fills only on its assigned post-target snapshot with route-specific cost")
    refuses(lambda: engine.land_entry(
        entry_order, public_runtime, entry_snapshot,
        request_clock=engine.ClockStamp(entry_order.target_unix_nanos, 150, "other-boot"),
        evidence_clock=engine.ClockStamp(entry_order.target_unix_nanos + 10, 200, "other-boot"),
        landing_clock=engine.ClockStamp(entry_order.target_unix_nanos + 11, 201, "other-boot")),
        "pending entry cannot land across a reboot without a fresh decision")
    refuses(lambda: replace(entry_order, target_unix_nanos=1),
            "typed entry order cannot forge a pre-decision landing target")
    wrong_target_snapshot = LandingSnapshot(
        mint="mintEntry", bonding_curve="curve",
        modeled_target_unix_nanos=entry_order.target_unix_nanos + 1,
        minimum_context_slot=10,
        request_started_unix_nanos=entry_order.target_unix_nanos + 1,
        response_received_unix_nanos=entry_order.target_unix_nanos + 10,
        context_slot=11, state=big_state,
        endpoint_scheme_host="https://observe-public.example",
        raw_response_sha256="2" * 64)
    refuses(lambda: engine.land_entry(
        entry_order, public_runtime, wrong_target_snapshot,
        request_clock=engine.ClockStamp(entry_order.target_unix_nanos, 150, "boot"),
        evidence_clock=engine.ClockStamp(entry_order.target_unix_nanos + 10, 200, "boot"),
        landing_clock=engine.ClockStamp(entry_order.target_unix_nanos + 11, 201, "boot")),
        "entry snapshot cannot be relabelled to a different landing target")

    exit_observed_at = landed_position.entry_unix_nanos + policy.MAX_HOLD_NANOS
    horizon_snapshot = LandingSnapshot(
        mint="mintEntry", bonding_curve="curve", modeled_target_unix_nanos=exit_observed_at,
        minimum_context_slot=11, request_started_unix_nanos=exit_observed_at,
        response_received_unix_nanos=exit_observed_at, context_slot=12, state=big_state,
        endpoint_scheme_host="https://observe-public.example",
        raw_response_sha256="3" * 64)
    horizon_decision = engine.evaluate_snapshot(
        landed_position, public_runtime, horizon_snapshot,
        request_clock=engine.ClockStamp(exit_observed_at, 250, "boot"),
        evidence_clock=engine.ClockStamp(exit_observed_at, 300, "boot"),
        decision_clock=engine.ClockStamp(exit_observed_at + 1, 301, "boot"))
    curve_order = engine.make_curve_exit_order(landed_position, horizon_decision)
    curve_fill_snapshot = LandingSnapshot(
        mint="mintEntry", bonding_curve="curve",
        modeled_target_unix_nanos=curve_order.target_unix_nanos,
        minimum_context_slot=12, request_started_unix_nanos=curve_order.target_unix_nanos,
        response_received_unix_nanos=curve_order.target_unix_nanos + 10,
        context_slot=13, state=big_state,
        endpoint_scheme_host="https://observe-public.example",
        raw_response_sha256="4" * 64)
    curve_sale = engine.land_curve_exit(
        curve_order, public_runtime, curve_fill_snapshot,
        request_clock=engine.ClockStamp(curve_order.target_unix_nanos, 350, "boot"),
        evidence_clock=engine.ClockStamp(curve_order.target_unix_nanos + 10, 400, "boot"),
        landing_clock=engine.ClockStamp(curve_order.target_unix_nanos + 11, 401, "boot"),
        attempt_id="5" * 64, close_decision_id="6" * 64)
    curve_settled = engine.settle_curve_sale(
        curve_sale, public_runtime, engine.CurveCloseEvidence(
            mint="mintEntry", entry_id=landed_position.entry_id,
            full_sale_token_atoms=landed_position.token_atoms,
            close_decision_id="6" * 64, close_attempt_id="7" * 64,
            target_unix_nanos=curve_sale.close_target_unix_nanos,
            landed_clock=engine.ClockStamp(curve_sale.close_target_unix_nanos + 1, 500, "boot"),
            succeeded=True))
    check(curve_settled.ata_rent_reclaim_lamports == 0,
          "paper curve close scenario cannot improve primary P&L with invented rent")
    refuses(lambda: engine.settle_curve_sale(
        curve_sale, public_runtime, engine.CurveCloseEvidence(
            mint="mintEntry", entry_id=landed_position.entry_id,
            full_sale_token_atoms=landed_position.token_atoms - 1,
            close_decision_id="6" * 64, close_attempt_id="8" * 64,
            target_unix_nanos=curve_sale.close_target_unix_nanos,
            landed_clock=engine.ClockStamp(curve_sale.close_target_unix_nanos + 1, 500, "boot"),
            succeeded=True)),
        "curve partial-sale evidence cannot reclaim ATA rent")

    # Cross-venue exit is a real two-landing state machine: discovery -> sell -> ATA close.
    transition = venue.begin(open_position(), public_runtime, complete_decision)
    check(transition.state == venue.VenueState.AWAITING_POOL,
          "typed curve failure opens bounded PumpSwap discovery")

    def pool_obs(receipt: int, raw: str = "7" * 64) -> PumpSwapObservation:
        return PumpSwapObservation(
            mint="mintA", pool="pool", base_vault="base", quote_vault="quote",
            reserves=PumpSwapReserves(10_000, 10_000, 0, 0, 0), context_slot=12,
            request_started_unix_nanos=receipt - 10,
            response_received_unix_nanos=receipt,
            endpoint_scheme_host="https://observe-public.example",
            raw_response_sha256=raw)

    refuses(lambda: venue.pool_observed(
        transition, public_runtime, pool_obs(2_000),
        request_clock=engine.ClockStamp(1_990, 250, "boot"),
        evidence_clock=engine.ClockStamp(2_000, 300, "boot"),
        decision_clock=engine.ClockStamp(2_001, 301, "boot"), decision_id="a" * 64),
        "PumpSwap discovery before the curve-decision target cannot become evidence")
    sell_decided = venue.pool_observed(
        transition, public_runtime, pool_obs(2_100),
        request_clock=engine.ClockStamp(2_090, 250, "boot"),
        evidence_clock=engine.ClockStamp(2_100, 300, "boot"),
        decision_clock=engine.ClockStamp(2_101, 301, "boot"), decision_id="a" * 64)
    check(sell_decided.state == venue.VenueState.SELL_DECIDED
          and sell_decided.sell_target_unix_nanos == 2_901,
          "pool discovery creates a separate calibrated sell landing target")
    refuses(lambda: venue.sell_landed(
        sell_decided, public_runtime, pool_obs(2_900, "8" * 64),
        request_clock=engine.ClockStamp(2_890, 350, "boot"),
        evidence_clock=engine.ClockStamp(2_900, 400, "boot"),
        decision_clock=engine.ClockStamp(2_901, 401, "boot"), close_decision_id="b" * 64),
        "PumpSwap sell cannot fill on a snapshot before its target")
    switched_pool = replace(pool_obs(3_000, "8" * 64), pool="attacker-pool")
    refuses(lambda: venue.sell_landed(
        sell_decided, public_runtime, switched_pool,
        request_clock=engine.ClockStamp(2_990, 350, "boot"),
        evidence_clock=engine.ClockStamp(3_000, 400, "boot"),
        decision_clock=engine.ClockStamp(3_001, 401, "boot"), close_decision_id="b" * 64),
        "PumpSwap sell cannot switch pool identity after its decision")
    regressed_slot = replace(pool_obs(3_000, "8" * 64), context_slot=11)
    refuses(lambda: venue.sell_landed(
        sell_decided, public_runtime, regressed_slot,
        request_clock=engine.ClockStamp(2_990, 350, "boot"),
        evidence_clock=engine.ClockStamp(3_000, 400, "boot"),
        decision_clock=engine.ClockStamp(3_001, 401, "boot"), close_decision_id="b" * 64),
        "PumpSwap sell cannot regress below its discovery slot")
    sold = venue.sell_landed(
        sell_decided, public_runtime, pool_obs(3_000, "8" * 64),
        request_clock=engine.ClockStamp(2_990, 350, "boot"),
        evidence_clock=engine.ClockStamp(3_000, 400, "boot"),
        decision_clock=engine.ClockStamp(3_001, 401, "boot"), close_decision_id="b" * 64)
    check(sold.state == venue.VenueState.AWAITING_ATA_CLOSE
          and sold.close_target_unix_nanos == 3_801
          and sold.wallet_proceeds_lamports == 899,
          "full-token PumpSwap fill uses a fresh post-target quote and exact route cost")
    sold_timeout = venue.expire(sold, decision_unix_nanos=sold.deadline_unix_nanos)
    check(sold_timeout.terminal_equity_lamports == sold.wallet_proceeds_lamports
          and sold_timeout.terminal_reason == "PUMPSWAP_SOLD_ATA_CLOSE_TIMEOUT_RENT_LOCKED",
          "ATA-close timeout preserves already-landed sale proceeds and only strands rent")
    refuses(lambda: venue.close_landed(
        sold, public_runtime, venue.CloseEvidence(
            "mintA", "2" * 64, 999, "b" * 64, "c" * 64, 3_801,
            engine.ClockStamp(3_900, 500, "boot"), True)),
        "partial-token evidence cannot unlock ATA rent")
    closed = venue.close_landed(
        sold, public_runtime, venue.CloseEvidence(
            "mintA", "2" * 64, 1_000, "b" * 64, "c" * 64, 3_801,
            engine.ClockStamp(3_900, 500, "boot"), True))
    close_failed = venue.close_landed(
        sold, public_runtime, venue.CloseEvidence(
            "mintA", "2" * 64, 1_000, "b" * 64, "d" * 64, 3_801,
            engine.ClockStamp(3_900, 500, "boot"), False))
    check(closed.terminal_equity_lamports == close_failed.terminal_equity_lamports
          and closed.modeled_close_equity_lamports
          - close_failed.modeled_close_equity_lamports == 20
          and not closed.ata_rent_reclaimed and not close_failed.ata_rent_reclaimed,
          "modeled ATA close is supplementary and cannot improve primary paper P&L")
    refuses(lambda: venue.close_landed(
        closed, public_runtime, venue.CloseEvidence(
            "mintA", "2" * 64, 1_000, "b" * 64, "e" * 64, 3_801,
            engine.ClockStamp(4_000, 600, "boot"), True)),
        "terminal cross-venue settlement cannot run twice")
    failed_sell = venue.record_failed_sell_attempt(
        sell_decided, public_runtime,
        landed_clock=engine.ClockStamp(3_000, 400, "boot"))
    check(failed_sell.state == venue.VenueState.AWAITING_POOL
          and failed_sell.failed_attempt_cost_lamports == exit_cost.attempt_cost_lamports,
          "landed-but-unfilled sell charges one route attempt before retry")
    refuses(lambda: venue.expire(
        failed_sell, decision_unix_nanos=failed_sell.deadline_unix_nanos - 1),
        "cross-venue full loss cannot be declared before frozen horizon")
    expired = venue.expire(
        failed_sell, decision_unix_nanos=failed_sell.deadline_unix_nanos)
    check(expired.state == venue.VenueState.TERMINAL
          and expired.terminal_equity_lamports == 0
          and not expired.ata_rent_reclaimed,
          "only bounded cross-venue deadline can settle an unsold position at full loss")

    print(f"\nPAC SCALP LL selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
