#!/usr/bin/env python3
"""Hostile controls and causal end-to-end selftest for the PAC V2 challenger."""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import pathlib
import struct
import tempfile
import time

from .execution import ReserveState, RefusedExecution
from . import pac_v2_calibration as calibration
from .pac_v2_calibration import ArtifactPins, CalibrationRefused, load as load_calibration
from . import pac_v2_detector as detector
from . import pac_v2_feed as feed
from . import pac_v2_manifest as manifest
from . import pac_v2_policy as policy
from . import pac_v2_runner as runner
from . import pac_v2_snapshot as snapshot


CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def refuses(exc_type, fn, label: str) -> None:
    try:
        fn()
    except exc_type:
        check(True, label)
    else:
        raise AssertionError(label)


def sha(value: object) -> str:
    return calibration._canonical_sha(value)


def state(real_quote: int) -> ReserveState:
    return ReserveState(30_000_000_000 + real_quote, 1_000_000_000_000_000,
                        real_quote, 720_100_000_000_000, False)


def event(index: int, pre_quote: int, post_quote: int, *, base: int,
          trader: str, side: str) -> feed.ClockedEvent:
    source = base + index * 1_000_000_000
    return feed.ClockedEvent(
        event_id=hashlib.sha256(f"event-{index}".encode()).hexdigest(), collector_epoch="epoch",
        mint="mint", trader=trader, signature=f"sig-{index}", slot=index, side=side,
        source_received_unix_nanos=source, materialized_unix_nanos=source + 10,
        runner_seen_unix_nanos=source + 20, pre_state=state(pre_quote),
        post_state=state(post_quote))


def pac_events(base: int) -> tuple[feed.ClockedEvent, ...]:
    return (
        event(0, 1_000_000_000, 900_000_000, base=base, trader="seller1", side="sell"),
        event(2, 900_000_000, 1_000_000_000, base=base, trader="buyer0", side="buy"),
        event(3, 1_000_000_000, 900_000_000, base=base, trader="seller2", side="sell"),
        event(4, 900_000_000, 1_000_000_000, base=base, trader="buyer1", side="buy"),
        event(5, 1_000_000_000, 1_010_000_000, base=base, trader="buyer2", side="buy"),
        event(6, 1_010_000_000, 1_020_000_000, base=base, trader="buyer3", side="buy"),
    )


def write_json(path: pathlib.Path, value: object) -> str:
    path.write_bytes(calibration._canonical(value) + bytes([10]))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: pathlib.Path, rows: list[dict]) -> str:
    path.write_bytes(b"".join(calibration._canonical(row) + bytes([10]) for row in rows))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calibration_bundle(tmp: pathlib.Path, *, count: int = 100,
                       wrong_attestation_wire: bool = False,
                       wrong_campaign_memo: bool = False) -> tuple[
                           pathlib.Path, pathlib.Path, pathlib.Path, ArtifactPins]:
    tmp.mkdir(parents=True, exist_ok=True)
    started = 1_700_000_000_000_000_000
    campaign_id = hashlib.sha256(b"campaign").hexdigest()
    payer_raw = hashlib.sha256(b"payer").digest()
    payer = calibration._b58encode(payer_raw)
    campaign_body = {
        "schema": calibration.CAMPAIGN_SCHEMA,
        "instrument_id": calibration.INSTRUMENT,
        "campaign_id": campaign_id,
        "seal_sha256": "a" * 64,
        "calibration_fee_payer": payer,
        "submit_endpoint_scheme_host": "https://submit.invalid",
        "verification_endpoint_scheme_host": "https://verify.invalid",
        "started_unix_nanos": started,
        "evidence_mode": "LOCAL_MONOTONIC_PLUS_FINALIZED_INDEPENDENT_RPC",
        "transaction_profile": calibration.TRANSACTION_PROFILE,
        "memo_program_id": calibration.MEMO_PROGRAM_ID,
    }
    campaign_row = {**campaign_body, "campaign_sha256": sha(campaign_body)}
    campaign_path = tmp / "campaign.json"
    campaign_sha = write_json(campaign_path, campaign_row)
    rows: list[dict] = []
    attestations: list[dict] = []
    previous = campaign_id
    for index in range(count):
        signature_raw = hashlib.sha512(f"signature-{index}".encode()).digest()
        signature = calibration._b58encode(signature_raw)
        memo = calibration._campaign_memo(campaign_id, index, previous)
        if wrong_campaign_memo and index == count - 1:
            memo = b"PACV2|" + b"0" * 64
        memo_program = calibration._b58decode(
            "memo program", calibration.MEMO_PROGRAM_ID, exact_length=32)

        def memo_wire(fee_payer: bytes) -> bytes:
            message = (bytes([1, 0, 1, 2]) + fee_payer + memo_program + bytes(32)
                       + bytes([1, 1, 0, len(memo)]) + memo)
            return bytes([1]) + signature_raw + message

        wire = memo_wire(payer_raw)
        wire_b64 = base64.b64encode(wire).decode()
        decision = started + 10_000_000_000 + index * 2_000_000_000
        reaction = (index + 1) * 1_000_000
        mono = 5_000_000_000_000 + index * 2_000_000_000
        wall_clocks = {
            "decision": decision, "build_start": decision + 10,
            "sign_done": decision + 20, "send_start": decision + 30,
            "send_ack": decision + 40, "land_observed": decision + reaction,
        }
        mono_clocks = {
            "decision": mono, "build_start": mono + 10,
            "sign_done": mono + 20, "send_start": mono + 30,
            "send_ack": mono + 40, "land_observed": mono + reaction,
        }
        send_request = {"jsonrpc": "2.0", "id": index + 1, "method": "sendTransaction",
                        "params": [wire_b64, {"encoding": "base64"}]}
        send_response = {"jsonrpc": "2.0", "id": index + 1, "result": signature}
        raw = {
            "wire_transaction_base64": wire_b64,
            "wire_transaction_sha256": hashlib.sha256(wire).hexdigest(),
            "send_request_json": send_request, "send_request_sha256": sha(send_request),
            "send_response_json": send_response, "send_response_sha256": sha(send_response),
        }
        sample_body = {
            "schema": calibration.SAMPLE_SCHEMA,
            "instrument_id": calibration.INSTRUMENT,
            "campaign_id": campaign_id,
            "previous_sample_id": previous,
            "transaction_signature": signature,
            "outcome": "LANDED", "land_slot": index + 1,
            "clocks_unix_nanos": wall_clocks,
            "clocks_monotonic_nanos": mono_clocks,
            "raw_evidence": raw, "raw_evidence_sha256": sha(raw),
        }
        sample = {**sample_body, "sample_id": sha(sample_body)}
        rows.append(sample)
        previous = sample["sample_id"]
        attested_wire = wire
        if wrong_attestation_wire and index == count - 1:
            other_payer = hashlib.sha256(b"other-payer").digest()
            attested_wire = memo_wire(other_payer)
        request = {"jsonrpc": "2.0", "id": index + 1, "method": "getTransaction",
                   "params": [signature, {"commitment": "finalized", "encoding": "base64",
                                          "maxSupportedTransactionVersion": 0}]}
        response = {
            "jsonrpc": "2.0", "id": index + 1,
            "result": {
                "slot": index + 1,
                "blockTime": wall_clocks["land_observed"] // 1_000_000_000,
                "meta": {"err": None},
                "transaction": [base64.b64encode(attested_wire).decode(), "base64"],
            },
        }
        attestation_body = {
            "schema": calibration.ATTESTATION_SCHEMA,
            "instrument_id": calibration.INSTRUMENT,
            "campaign_id": campaign_id,
            "sample_id": sample["sample_id"],
            "transaction_signature": signature,
            "verification_endpoint_scheme_host": "https://verify.invalid",
            "request_started_unix_nanos": wall_clocks["land_observed"] + 1,
            "response_received_unix_nanos": wall_clocks["land_observed"] + 2,
            "request_json": request, "response_json": response,
            "raw_response_sha256": sha(response),
        }
        attestations.append({
            **attestation_body, "attestation_id": sha(attestation_body)})
    calibration_path = tmp / "calibration.jsonl"
    attestation_path = tmp / "attestation.jsonl"
    calibration_sha = write_jsonl(calibration_path, rows)
    attestation_sha = write_jsonl(attestation_path, attestations)
    return campaign_path, calibration_path, attestation_path, ArtifactPins(
        campaign_sha, calibration_sha, attestation_sha)


def fake_calibration(base: int) -> calibration.Calibration:
    return calibration.Calibration(
        artifact_sha256="b" * 64, attestation_sha256="c" * 64,
        campaign_sha256="d" * 64, campaign_id="e" * 64,
        landed_samples=100, failed_samples=0, reaction_p90_nanos=1_000_000,
        first_decision_unix_nanos=base - 3_000_000_000,
        last_land_unix_nanos=base - 2_000_000_000,
        last_attested_unix_nanos=base - 1_500_000_000)


class FakeSnapshots:
    def __init__(self, states: list[ReserveState], *, response_delay: int = 1):
        self.states = list(states)
        self.calls: list[tuple[str, int]] = []
        self.response_delay = response_delay

    def capture(self, mint: str, modeled_target_unix_nanos: int,
                minimum_context_slot: int) -> snapshot.LandingSnapshot:
        self.calls.append((mint, modeled_target_unix_nanos))
        if not self.states:
            raise AssertionError("unexpected snapshot")
        return snapshot.LandingSnapshot(
            mint=mint, bonding_curve="curve", modeled_target_unix_nanos=modeled_target_unix_nanos,
            minimum_context_slot=minimum_context_slot,
            request_started_unix_nanos=modeled_target_unix_nanos,
            response_received_unix_nanos=modeled_target_unix_nanos + self.response_delay,
            context_slot=max(minimum_context_slot, len(self.calls)), state=self.states.pop(0),
            endpoint_scheme_host="https://rpc.invalid",
            raw_response_sha256=hashlib.sha256(f"snapshot-{len(self.calls)}".encode()).hexdigest())


class UnavailableSnapshots:
    def capture(self, mint: str, modeled_target_unix_nanos: int,
                minimum_context_slot: int):
        raise snapshot.SnapshotUnavailable("synthetic RPC outage")


class DecodeRefusalSnapshots:
    def capture(self, mint: str, modeled_target_unix_nanos: int,
                minimum_context_slot: int):
        raise RefusedExecution("synthetic mayhem/layout refusal")


def append_runner_events(events_path: pathlib.Path, receipts_path: pathlib.Path,
                         events: tuple[feed.ClockedEvent, ...]) -> None:
    for item in events:
        body = {
            "schema": feed.SCHEMA, "source": feed.SOURCE,
            "collector_epoch": item.collector_epoch, "mint": item.mint,
            "trader": item.trader, "signature": item.signature, "slot": item.slot,
            "side": item.side, "source_received_unix_nanos": item.source_received_unix_nanos,
            "continuity_proven": True,
            "pre_state": runner.asdict(item.pre_state), "post_state": runner.asdict(item.post_state),
        }
        event_id = feed._canonical_sha(body)
        feed._append(events_path, {**body, "event_id": event_id})
        receipt = {
            "schema": feed.SCHEMA, "event_id": event_id,
            "materialized_unix_nanos": item.materialized_unix_nanos,
            "recovered_after_crash": False,
        }
        feed._append(receipts_path, {
            **receipt, "receipt_sha256": feed._canonical_sha(receipt)})


def make_open_position(base: int) -> tuple[runner.OpenPosition, ReserveState]:
    healthy = state(1_020_000_000)
    accounting = runner.kernel_accounting(
        healthy, runner.OrderIntent(runner.IntentKind.EXACT_QUOTE_BUY, 50_000_000, 1))
    position = runner.OpenPosition(
        mint="open-mint", token_atoms=accounting["out_amount"],
        quote_input_lamports=50_000_000,
        entry_all_in_lamports=-accounting["wallet_delta_lamports"],
        entry_curve_fee_lamports=accounting["curve_fee_lamports"],
        entry_attempt_cost_lamports=accounting["attempt_cost_lamports"],
        ata_rent_lamports=accounting["ata_rent_lamports"],
        entry_unix_nanos=base, peak_net_exit_lamports=0, failed_exit_cost_lamports=0,
        entry_id="f" * 64, last_context_slot=1, last_state=runner.asdict(healthy))
    return position, healthy


def main() -> int:
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = pathlib.Path(raw_tmp)

        campaign_path, calibration_path, attestation_path, pins = calibration_bundle(tmp)
        calibrated = load_calibration(
            calibration_path, attestation_path=attestation_path,
            campaign_path=campaign_path, pins=pins)
        check(calibrated.landed_samples == 100 and calibrated.reaction_p90_nanos == 90_000_000,
              "100 campaign-bound finalized attestations derive exact nearest-rank p90")
        check("now_unix_nanos" not in inspect.signature(runner.run_once).parameters
              and "now" not in inspect.signature(runner.run_once).parameters,
              "production runner API exposes no caller-supplied decision/horizon clock")
        refuses(RefusedExecution, lambda: manifest._require_fresh_activation(
            calibrated.last_land_unix_nanos + manifest.MAX_ACTIVATION_LAG_NANOS + 1,
            calibrated), "stale calibration cannot create an activation")

        forged_path = tmp / "forged.jsonl"
        forged_path.write_text(json.dumps({
            "schema": 1, "instrument_id": calibration.INSTRUMENT,
            "transaction_signature": "tx-0", "clocks": {}}) + "\n")
        forged_pins = ArtifactPins(
            pins.campaign_sha256, hashlib.sha256(forged_path.read_bytes()).hexdigest(),
            pins.attestation_sha256)
        refuses(CalibrationRefused, lambda: load_calibration(
            forged_path, attestation_path=attestation_path,
            campaign_path=campaign_path, pins=forged_pins),
            "hand-written legacy/self-validating calibration REFUSES")

        short_campaign, short_cal, short_att, short_pins = calibration_bundle(
            tmp / "short", count=99)
        refuses(CalibrationRefused, lambda: load_calibration(
            short_cal, attestation_path=short_att,
            campaign_path=short_campaign, pins=short_pins),
            "99 independently attested landed samples REFUSE")

        bad_campaign, bad_cal, bad_att, bad_pins = calibration_bundle(
            tmp / "wrong-wire", wrong_attestation_wire=True)
        refuses(CalibrationRefused, lambda: load_calibration(
            bad_cal, attestation_path=bad_att,
            campaign_path=bad_campaign, pins=bad_pins),
            "attested on-chain wire/fee-payer mismatch REFUSES")

        memo_campaign, memo_cal, memo_att, memo_pins = calibration_bundle(
            tmp / "wrong-campaign-memo", wrong_campaign_memo=True)
        refuses(CalibrationRefused, lambda: load_calibration(
            memo_cal, attestation_path=memo_att,
            campaign_path=memo_campaign, pins=memo_pins),
            "unrelated on-chain transaction without exact campaign challenge REFUSES")

        tampered = calibration_path.read_bytes() + b" "
        tampered_path = tmp / "tampered.jsonl"
        tampered_path.write_bytes(tampered)
        refuses(CalibrationRefused, lambda: load_calibration(
            tampered_path, attestation_path=attestation_path,
            campaign_path=campaign_path, pins=pins),
            "calibration byte tamper REFUSES against out-of-band pin")

        base = time.time_ns() - 10_000_000_000
        events = pac_events(base)
        qualified = detector.qualify(
            events, reaction_p90_nanos=1_000_000_000,
            quote_input_lamports=50_000_000)
        check(qualified is not None and qualified.buyer_breadth == 3,
              "PAC plus p90 dwell, breadth and 6x shock cover qualifies")
        narrow = tuple(item for item in events if item.trader != "buyer3")
        check(detector.qualify(
            narrow, reaction_p90_nanos=1_000_000_000,
            quote_input_lamports=50_000_000) is None,
            "fewer than three observed dwell buyers refuse entry")
        eroded = list(events)
        eroded[-1] = event(
            6, 1_010_000_000, 990_000_000, base=base, trader="buyer3", side="buy")
        check(detector.qualify(
            tuple(eroded), reaction_p90_nanos=1_000_000_000,
            quote_input_lamports=50_000_000) is None,
            "post-recovery reserve erosion refuses entry")
        check(detector.qualify(
            events, reaction_p90_nanos=3_000_000_000,
            quote_input_lamports=50_000_000) is None,
            "insufficient measured-p90 dwell refuses entry")

        position = policy.Position(1, 50_000_000, 1_000, peak_net_exit_lamports=1_000_000_000)
        horizon = policy.decide(
            position, now_unix_nanos=1_000 + policy.MAX_HOLD_NANOS,
            net_exit_lamports=1, real_quote_lamports=1)
        check(horizon.action == policy.ExitAction.EXIT_HORIZON,
              "absolute horizon wins over simultaneous capacity and trail")

        account = (snapshot._DISCRIMINATOR
                   + struct.pack("<5Q", 1_000_000_000_000_000, 31_000_000_000,
                                 720_100_000_000_000, 1_000_000_000, 1_000_000_000_000_000)
                   + bytes([0]) + bytes([1]) * 32 + bytes([0, 0])
                   + snapshot._b58decode(snapshot._ACCOUNT_SOL_QUOTE_MINT))
        decoded = snapshot._decode_state(account)
        check(decoded.real_quote == 1_000_000_000 and not decoded.complete,
              "exact 115-byte native-SOL account snapshot decodes")
        refuses(RefusedExecution, lambda: snapshot._decode_state(account + bytes([0])),
                "account layout suffix drift REFUSES")
        refuses(RefusedExecution, lambda: snapshot.LandingSnapshot(
            mint="mint", bonding_curve="curve", modeled_target_unix_nanos=1,
            minimum_context_slot=1,
            request_started_unix_nanos=1,
            response_received_unix_nanos=1 + snapshot.MAX_SNAPSHOT_STALENESS_NANOS + 1,
            context_slot=1, state=state(1_000_000_000),
            endpoint_scheme_host="https://rpc.invalid", raw_response_sha256="a" * 64),
            "snapshot later than the frozen landing window REFUSES")
        refuses(RefusedExecution, lambda: snapshot.LandingSnapshot(
            mint="mint", bonding_curve="curve", modeled_target_unix_nanos=1,
            minimum_context_slot=2, request_started_unix_nanos=1,
            response_received_unix_nanos=2, context_slot=1,
            state=state(1_000_000_000), endpoint_scheme_host="https://rpc.invalid",
            raw_response_sha256="a" * 64),
            "snapshot context older than decision evidence REFUSES")

        # The first event in an epoch is a seed only; restart cannot fabricate zero impact.
        writer_events = tmp / "writer-events.jsonl"
        writer_receipts = tmp / "writer-receipts.jsonl"
        writer = feed.FeedWriter(
            events_path=writer_events, receipts_path=writer_receipts, epoch="seed-epoch")
        decoded_trade = {
            "mint": "seed-mint", "user": "buyer", "side": "buy",
            "virtual_sol": 31_000_000_000, "virtual_tok": 1_000_000_000_000_000,
            "real_sol": 1_000_000_000, "real_tok": 720_100_000_000_000,
        }
        writer.append_decoded(
            decoded_trade, signature="seed-sig", slot=1,
            source_received_unix_nanos=base)
        seed_cursor = feed.Cursor()
        check(feed.consume(
            seed_cursor, events_path=writer_events, receipts_path=writer_receipts,
            runner_seen_unix_nanos=time.time_ns()) == [],
            "first mint event is continuity seed, never a zero-delta strategy event")
        decoded_trade["real_sol"] = 1_010_000_000
        decoded_trade["virtual_sol"] = 31_010_000_000
        writer.append_decoded(
            decoded_trade, signature="next-sig", slot=2,
            source_received_unix_nanos=base + 200)
        check(len(feed.consume(
            seed_cursor, events_path=writer_events, receipts_path=writer_receipts,
            runner_seen_unix_nanos=time.time_ns())) == 1,
            "second same-epoch event carries proven reserve continuity")

        # A durable event with an interrupted receipt is recovered once and visibly marked.
        crash_events = tmp / "crash-events.jsonl"
        crash_receipts = tmp / "crash-receipts.jsonl"
        event_body = {
            "schema": feed.SCHEMA, "source": feed.SOURCE, "collector_epoch": "crash",
            "mint": "crash-mint", "trader": "buyer", "signature": "crash-sig",
            "slot": 1, "side": "buy", "source_received_unix_nanos": base,
            "continuity_proven": False, "pre_state": None,
            "post_state": runner.asdict(state(1_000_000_000)),
        }
        feed._append(crash_events, {**event_body, "event_id": feed._canonical_sha(event_body)})
        feed.FeedWriter(events_path=crash_events, receipts_path=crash_receipts, epoch="new")
        recovered_receipt = json.loads(crash_receipts.read_text())
        check(recovered_receipt["recovered_after_crash"] is True,
              "event/receipt crash gap is fsync-recovered without backdating")

        # Orphan receipts advance once and stay visible instead of wedging the cursor.
        orphan_events = tmp / "orphan-events.jsonl"
        orphan_receipts = tmp / "orphan-receipts.jsonl"
        orphan = {
            "schema": feed.SCHEMA, "event_id": "f" * 64,
            "materialized_unix_nanos": time.time_ns(),
            "recovered_after_crash": False,
        }
        feed._append(orphan_receipts, {
            **orphan, "receipt_sha256": feed._canonical_sha(orphan)})
        orphan_cursor = feed.Cursor()
        check(feed.consume(
            orphan_cursor, events_path=orphan_events, receipts_path=orphan_receipts,
            runner_seen_unix_nanos=time.time_ns()) == []
            and len(orphan_cursor.rejected_receipts) == 1
            and feed.consume(
                orphan_cursor, events_path=orphan_events, receipts_path=orphan_receipts,
                runner_seen_unix_nanos=time.time_ns()) == [],
            "orphan receipt is advanced and recorded exactly once")

        # Full runner: first fill is committed and not serviced on its older cycle clock.
        run_events = tmp / "run-events.jsonl"
        run_receipts = tmp / "run-receipts.jsonl"
        state_path = tmp / "runner-state.json"
        ledger_path = tmp / "runner-ledger.jsonl"
        proof = runner.RuntimeProof("a" * 64, base - 1_000_000_000, fake_calibration(base))
        fake = FakeSnapshots(
            [state(1_020_000_000), state(1_020_000_000)], response_delay=5_000_000)
        initialized = runner._run_once_at(
            proof, fake, now=base, quote_input_lamports=50_000_000,
            state_path=state_path, ledger_path=ledger_path,
            events_path=run_events, receipts_path=run_receipts, initialize_at_eof=False)
        check(initialized["status"] == "INITIALIZED_NO_BACKFILL",
              "runner initializes without backfill")
        append_runner_events(run_events, run_receipts, events)
        decision_now = time.time_ns()
        decided = runner._run_once_at(
            proof, fake, now=decision_now, quote_input_lamports=50_000_000,
            state_path=state_path, ledger_path=ledger_path,
            events_path=run_events, receipts_path=run_receipts, initialize_at_eof=False)
        check(decided["pending"] == 1 and decided["new_events"] == len(events),
              "entry decision is incremental and persists a future snapshot target")
        entered = runner._run_once_at(
            proof, fake, now=decision_now + 2_000_000,
            quote_input_lamports=50_000_000, state_path=state_path,
            ledger_path=ledger_path, events_path=run_events,
            receipts_path=run_receipts, initialize_at_eof=False)
        stored = json.loads(state_path.read_text())
        entry_time = stored["open_position"]["entry_unix_nanos"]
        check(entered["open"] == 1 and entered["pending"] == 0
              and entry_time > decision_now + 2_000_000
              and sum(json.loads(line)["kind"] == "entry_filled"
                      for line in ledger_path.read_text().splitlines()) == 1,
              "first fill commits once and skips same-tick backward-clock service")

        horizon_now = entry_time + policy.MAX_HOLD_NANOS
        exit_decided = runner._run_once_at(
            proof, fake, now=horizon_now, quote_input_lamports=50_000_000,
            state_path=state_path, ledger_path=ledger_path,
            events_path=run_events, receipts_path=run_receipts, initialize_at_eof=False)
        check(exit_decided["pending"] == 1 and exit_decided["new_events"] == 0,
              "wall-clock horizon decides an exit without another trade")
        resolved = runner._run_once_at(
            proof, fake, now=horizon_now + 2_000_000,
            quote_input_lamports=50_000_000, state_path=state_path,
            ledger_path=ledger_path, events_path=run_events,
            receipts_path=run_receipts, initialize_at_eof=False)
        ledger_rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        check(resolved["open"] == resolved["pending"] == 0
              and sum(row["kind"] == "resolved" for row in ledger_rows) == 1,
              "horizon snapshot resolves without a post-decision trade")

        # Decode-class snapshot refusal is terminal and releases the single-position lock.
        refusal_state_path = tmp / "refusal-state.json"
        refusal_ledger = tmp / "refusal-ledger.jsonl"
        refusal_state = runner._new_state(proof, event_offset=0, receipt_offset=0)
        open_position, _ = make_open_position(base)
        refusal_state["open_position"] = runner.asdict(open_position)
        runner._atomic_write(refusal_state_path, refusal_state)
        runner._run_once_at(
            proof, DecodeRefusalSnapshots(), now=base + policy.MAX_HOLD_NANOS,
            quote_input_lamports=50_000_000, state_path=refusal_state_path,
            ledger_path=refusal_ledger, events_path=tmp / "none-events",
            receipts_path=tmp / "none-receipts", initialize_at_eof=False)
        pending = json.loads(refusal_state_path.read_text())["pending_order"]
        refused = runner._run_once_at(
            proof, DecodeRefusalSnapshots(), now=pending["target_unix_nanos"] + 1,
            quote_input_lamports=50_000_000, state_path=refusal_state_path,
            ledger_path=refusal_ledger, events_path=tmp / "none-events",
            receipts_path=tmp / "none-receipts", initialize_at_eof=False)
        refusal_rows = [json.loads(line) for line in refusal_ledger.read_text().splitlines()]
        check(refused["open"] == refused["pending"] == 0
              and refusal_rows[-1]["reason"] == "EXIT_SNAPSHOT_PERMANENT_REFUSAL"
              and refusal_rows[-1]["unexitable_full_loss"] is True,
              "decode-class snapshot refusal books full loss and releases lock")

        # Transport outage retains retry semantics, then horizon deadline terminates.
        timeout_state_path = tmp / "timeout-state.json"
        timeout_ledger = tmp / "timeout-ledger.jsonl"
        timeout_state = runner._new_state(proof, event_offset=0, receipt_offset=0)
        timeout_position, _ = make_open_position(base)
        timeout_state["open_position"] = runner.asdict(timeout_position)
        runner._atomic_write(timeout_state_path, timeout_state)
        runner._run_once_at(
            proof, UnavailableSnapshots(), now=base + policy.MAX_HOLD_NANOS,
            quote_input_lamports=50_000_000, state_path=timeout_state_path,
            ledger_path=timeout_ledger, events_path=tmp / "none-events",
            receipts_path=tmp / "none-receipts", initialize_at_eof=False)
        timeout_pending = json.loads(timeout_state_path.read_text())["pending_order"]
        terminal = runner._run_once_at(
            proof, UnavailableSnapshots(),
            now=timeout_pending["target_unix_nanos"] + runner.SNAPSHOT_TIMEOUT_NANOS,
            quote_input_lamports=50_000_000, state_path=timeout_state_path,
            ledger_path=timeout_ledger, events_path=tmp / "none-events",
            receipts_path=tmp / "none-receipts", initialize_at_eof=False)
        timeout_rows = [json.loads(line) for line in timeout_ledger.read_text().splitlines()]
        check(terminal["open"] == terminal["pending"] == 0
              and timeout_rows[-1]["reason"] == "HORIZON_SNAPSHOT_DEADLINE_ELAPSED",
              "30-second horizon deadline books full loss and releases lock")

        tampered_state = json.loads(state_path.read_text())
        tampered_state["calibration_sha256"] = "0" * 64
        runner._atomic_write(tmp / "tampered-state.json", tampered_state)
        refuses(RefusedExecution, lambda: runner._run_once_at(
            proof, fake, now=horizon_now + 4_000_000,
            quote_input_lamports=50_000_000, state_path=tmp / "tampered-state.json",
            ledger_path=tmp / "tampered-ledger.jsonl", events_path=run_events,
            receipts_path=run_receipts, initialize_at_eof=False),
            "runtime binding tamper REFUSES before feed or pricing")

        # The repaired closure must be immutable before an authentic campaign may begin.
        check(manifest.anchor_status() == "ANCHORED",
              "repaired PAC V2 closure is sealed and git-anchored")
        refuses(RefusedExecution, manifest.load_runtime_proof,
                "runtime refuses absent post-repair authenticated activation")

    print(f"PAC V2 SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
