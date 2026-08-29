#!/usr/bin/env python3
"""Negative controls for the PAC V2.1 processed-observation calibration contract."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import pathlib
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from . import pac_v2_calibration as v2
from . import pac_v2_send as send
from . import pac_v21_calibration as calibration


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
    except calibration.CalibrationRefused:
        check(True, label)
    else:
        raise AssertionError(label)


def write_json(path: pathlib.Path, value: object) -> str:
    path.write_bytes(calibration._canonical(value) + b"\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: pathlib.Path, rows: list[dict]) -> str:
    path.write_bytes(b"".join(calibration._canonical(row) + b"\n" for row in rows))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def poll(signature: str, poll_index: int, *, sw: int, rw: int, sm: int, rm: int,
         status: dict | None) -> dict:
    request = {"jsonrpc": "2.0", "id": poll_index + 1,
               "method": "getSignatureStatuses",
               "params": [[signature], {"searchTransactionHistory": True}]}
    response = {"jsonrpc": "2.0", "id": poll_index + 1,
                "result": {"context": {"slot": 1}, "value": [status]}}
    body = {
        "request_started_unix_nanos": sw, "response_received_unix_nanos": rw,
        "request_started_monotonic_nanos": sm, "response_received_monotonic_nanos": rm,
        "request_json": request, "response_json": response,
        "raw_response_sha256": calibration._sha(response),
    }
    return {**body, "poll_id": calibration._sha(body)}


def bundle(root: pathlib.Path, count: int = 100) -> tuple[
        pathlib.Path, pathlib.Path, pathlib.Path, calibration.Pins, list[dict], list[dict]]:
    private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"v21-calibration-key").digest())
    payer_raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    payer = v2._b58encode(payer_raw)
    campaign_id = hashlib.sha256(b"v21-campaign").hexdigest()
    started = 1_800_000_000_000_000_000
    campaign_body = {
        "schema": calibration.CAMPAIGN_SCHEMA,
        "instrument_id": calibration.INSTRUMENT,
        "campaign_id": campaign_id,
        "seal_sha256": "a" * 64,
        "calibration_fee_payer": payer,
        "submit_endpoint_scheme_host": "https://submit.example.com",
        "verification_endpoint_scheme_host": "https://verify.example.com",
        "started_unix_nanos": started,
        "max_transactions": 100,
        "max_lamports": 500_000,
        "poll_interval_nanos": calibration.POLL_INTERVAL_NANOS,
        "processed_deadline_nanos": calibration.PROCESSED_DEADLINE_NANOS,
        "evidence_mode": calibration.EVIDENCE_MODE,
        "transaction_profile": calibration.TRANSACTION_PROFILE,
        "memo_program_id": calibration.MEMO_PROGRAM_ID,
    }
    campaign = {**campaign_body, "campaign_sha256": calibration._sha(campaign_body)}
    campaign_path = root / "campaign.json"
    campaign_pin = write_json(campaign_path, campaign)
    samples, attestations = [], []
    previous = campaign_id
    for index in range(count):
        memo = v2._campaign_memo(campaign_id, index, previous)
        blockhash = hashlib.sha256(f"blockhash-{index}".encode()).digest()
        wire_b64, signature = send.build_signed_memo(private, payer, memo, blockhash)
        wire = base64.b64decode(wire_b64)
        decision = started + 1_000_000_000 + index * 2_000_000_000
        reaction = 500_000_000 + index * 1_000_000
        mono_decision = 9_000_000_000_000 + index * 2_000_000_000
        wall = {
            "decision": decision, "build_start": decision + 10,
            "sign_done": decision + 20, "send_start": decision + 30,
            "send_ack": decision + 40, "processed_observed": decision + reaction,
        }
        mono = {
            "decision": mono_decision, "build_start": mono_decision + 10,
            "sign_done": mono_decision + 20, "send_start": mono_decision + 30,
            "send_ack": mono_decision + 40,
            "processed_observed": mono_decision + reaction,
        }
        first = poll(signature, 0, sw=decision + 100_000_000, rw=decision + 110_000_000,
                     sm=mono_decision + 100_000_000, rm=mono_decision + 110_000_000,
                     status=None)
        slot = index + 100
        status = {"slot": slot, "confirmations": 0, "err": None,
                  "confirmationStatus": "processed"}
        second = poll(signature, 1, sw=decision + 210_000_000,
                      rw=wall["processed_observed"], sm=mono_decision + 210_000_000,
                      rm=mono["processed_observed"], status=status)
        send_request = {"jsonrpc": "2.0", "id": index + 1, "method": "sendTransaction",
                        "params": [wire_b64, {"encoding": "base64", "skipPreflight": False,
                                              "preflightCommitment": "processed"}]}
        send_response = {"jsonrpc": "2.0", "id": index + 1, "result": signature}
        raw = {
            "wire_transaction_base64": wire_b64,
            "wire_transaction_sha256": hashlib.sha256(wire).hexdigest(),
            "send_request_json": send_request,
            "send_request_sha256": calibration._sha(send_request),
            "send_response_json": send_response,
            "send_response_sha256": calibration._sha(send_response),
        }
        sample_body = {
            "schema": calibration.SAMPLE_SCHEMA, "instrument_id": calibration.INSTRUMENT,
            "campaign_id": campaign_id, "previous_sample_id": previous,
            "transaction_signature": signature, "outcome": "PROCESSED",
            "processed_slot": slot, "confirmation_status": "processed",
            "clocks_unix_nanos": wall, "clocks_monotonic_nanos": mono,
            "raw_evidence": raw, "raw_evidence_sha256": calibration._sha(raw),
            "status_polls": [first, second],
        }
        sample = {**sample_body, "sample_id": calibration._sha(sample_body)}
        samples.append(sample); previous = sample["sample_id"]
        request = {"jsonrpc": "2.0", "id": index + 1, "method": "getTransaction",
                   "params": [signature, {"commitment": "finalized", "encoding": "base64",
                                          "maxSupportedTransactionVersion": 0}]}
        response = {"jsonrpc": "2.0", "id": index + 1,
                    "result": {"slot": slot, "blockTime": wall["processed_observed"] // 1_000_000_000,
                               "meta": {"err": None, "fee": 5_000},
                               "transaction": [wire_b64, "base64"]}}
        attestation_body = {
            "schema": calibration.ATTESTATION_SCHEMA,
            "instrument_id": calibration.INSTRUMENT, "campaign_id": campaign_id,
            "sample_id": sample["sample_id"], "transaction_signature": signature,
            "verification_endpoint_scheme_host": "https://verify.example.com",
            "request_started_unix_nanos": wall["processed_observed"] + 1,
            "response_received_unix_nanos": wall["processed_observed"] + 2,
            "request_json": request, "response_json": response,
            "raw_response_sha256": calibration._sha(response),
        }
        attestations.append({**attestation_body,
                             "attestation_id": calibration._sha(attestation_body)})
    samples_path, attestations_path = root / "samples.jsonl", root / "attestations.jsonl"
    sample_pin = write_jsonl(samples_path, samples)
    attestation_pin = write_jsonl(attestations_path, attestations)
    return (campaign_path, samples_path, attestations_path,
            calibration.Pins(campaign_pin, sample_pin, attestation_pin), samples, attestations)


def reseal_poll(value: dict) -> None:
    body = dict(value); body.pop("poll_id", None); value["poll_id"] = calibration._sha(body)


def reseal_sample(value: dict) -> None:
    body = dict(value); body.pop("sample_id", None); value["sample_id"] = calibration._sha(body)


def reseal_attestation(value: dict) -> None:
    body = dict(value); body.pop("attestation_id", None)
    value["attestation_id"] = calibration._sha(body)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pac_v21_cal_") as temporary:
        root = pathlib.Path(temporary)
        campaign_path, sample_path, attestation_path, pins, samples, attestations = bundle(root)
        loaded = calibration.load(campaign_path=campaign_path, samples_path=sample_path,
                                  attestations_path=attestation_path, pins=pins)
        check(loaded.processed_samples == 100 and loaded.failed_samples == 0,
              "100 processed samples require 100 independent finalized attestations")
        check(loaded.processed_p90_nanos == 589_000_000,
              "nearest-rank processed p90 is derived from monotonic decision-to-first-status clocks")

        short_samples, short_attestations = samples[:99], attestations[:99]
        short_sample_path, short_att_path = root / "short-samples", root / "short-attest"
        short_pins = calibration.Pins(
            pins.campaign_sha256, write_jsonl(short_sample_path, short_samples),
            write_jsonl(short_att_path, short_attestations))
        refuses(lambda: calibration.load(
            campaign_path=campaign_path, samples_path=short_sample_path,
            attestations_path=short_att_path, pins=short_pins),
            "99 processed samples refuse")

        earlier = deepcopy(samples)
        status = {"slot": earlier[-1]["processed_slot"], "confirmations": 0,
                  "err": None, "confirmationStatus": "processed"}
        earlier[-1]["status_polls"][0]["response_json"]["result"]["value"][0] = status
        earlier[-1]["status_polls"][0]["raw_response_sha256"] = calibration._sha(
            earlier[-1]["status_polls"][0]["response_json"])
        reseal_poll(earlier[-1]["status_polls"][0]); reseal_sample(earlier[-1])
        earlier_path = root / "earlier.jsonl"
        earlier_pins = calibration.Pins(
            pins.campaign_sha256, write_jsonl(earlier_path, earlier), pins.attestations_sha256)
        refuses(lambda: calibration.load(
            campaign_path=campaign_path, samples_path=earlier_path,
            attestations_path=attestation_path, pins=earlier_pins),
            "an ignored earlier non-null status refuses")

        fast = deepcopy(samples)
        terminal = fast[-1]["status_polls"][-1]
        terminal["request_started_unix_nanos"] = fast[-1]["status_polls"][0][
            "response_received_unix_nanos"] + calibration.POLL_INTERVAL_NANOS - 1
        terminal["request_started_monotonic_nanos"] = fast[-1]["status_polls"][0][
            "response_received_monotonic_nanos"] + calibration.POLL_INTERVAL_NANOS - 1
        reseal_poll(terminal); reseal_sample(fast[-1])
        fast_path = root / "fast.jsonl"
        fast_pins = calibration.Pins(
            pins.campaign_sha256, write_jsonl(fast_path, fast), pins.attestations_sha256)
        refuses(lambda: calibration.load(
            campaign_path=campaign_path, samples_path=fast_path,
            attestations_path=attestation_path, pins=fast_pins),
            "polling faster than the frozen 100ms cadence refuses")

        float_clock = deepcopy(samples)
        float_clock[-1]["clocks_monotonic_nanos"]["processed_observed"] = 1.5
        reseal_sample(float_clock[-1]); float_path = root / "float.jsonl"
        float_pins = calibration.Pins(
            pins.campaign_sha256, write_jsonl(float_path, float_clock), pins.attestations_sha256)
        refuses(lambda: calibration.load(
            campaign_path=campaign_path, samples_path=float_path,
            attestations_path=attestation_path, pins=float_pins),
            "float processed clock refuses")

        wrong_slot = deepcopy(attestations)
        wrong_slot[-1]["response_json"]["result"]["slot"] += 1
        wrong_slot[-1]["raw_response_sha256"] = calibration._sha(wrong_slot[-1]["response_json"])
        reseal_attestation(wrong_slot[-1]); wrong_slot_path = root / "wrong-slot.jsonl"
        wrong_slot_pins = calibration.Pins(
            pins.campaign_sha256, pins.samples_sha256,
            write_jsonl(wrong_slot_path, wrong_slot))
        refuses(lambda: calibration.load(
            campaign_path=campaign_path, samples_path=sample_path,
            attestations_path=wrong_slot_path, pins=wrong_slot_pins),
            "finalized slot differing from processed observation refuses")

        wrong_rpc = deepcopy(samples)
        wrong_rpc[-1]["status_polls"][-1]["response_json"]["id"] = 999
        wrong_rpc[-1]["status_polls"][-1]["raw_response_sha256"] = calibration._sha(
            wrong_rpc[-1]["status_polls"][-1]["response_json"])
        reseal_poll(wrong_rpc[-1]["status_polls"][-1]); reseal_sample(wrong_rpc[-1])
        wrong_rpc_path = root / "wrong-rpc.jsonl"
        wrong_rpc_pins = calibration.Pins(
            pins.campaign_sha256, write_jsonl(wrong_rpc_path, wrong_rpc),
            pins.attestations_sha256)
        refuses(lambda: calibration.load(
            campaign_path=campaign_path, samples_path=wrong_rpc_path,
            attestations_path=attestation_path, pins=wrong_rpc_pins),
            "mismatched status JSON-RPC id refuses")

        over_budget = deepcopy(attestations)
        over_budget[-1]["response_json"]["result"]["meta"]["fee"] = 5_001
        over_budget[-1]["raw_response_sha256"] = calibration._sha(
            over_budget[-1]["response_json"])
        reseal_attestation(over_budget[-1]); over_budget_path = root / "over-budget.jsonl"
        over_budget_pins = calibration.Pins(
            pins.campaign_sha256, pins.samples_sha256,
            write_jsonl(over_budget_path, over_budget))
        refuses(lambda: calibration.load(
            campaign_path=campaign_path, samples_path=sample_path,
            attestations_path=over_budget_path, pins=over_budget_pins),
            "finalized aggregate fee above campaign budget refuses")

        campaign = json.loads(campaign_path.read_text())
        campaign["verification_endpoint_scheme_host"] = campaign["submit_endpoint_scheme_host"]
        body = dict(campaign); body.pop("campaign_sha256"); campaign["campaign_sha256"] = calibration._sha(body)
        same_origin_path = root / "same-origin.json"
        same_origin_pin = write_json(same_origin_path, campaign)
        refuses(lambda: calibration.load_campaign(
            same_origin_path, expected_sha256=same_origin_pin),
            "same submit/verifier origin refuses")

        bad_port = deepcopy(json.loads(campaign_path.read_text()))
        bad_port["submit_endpoint_scheme_host"] = "https://submit.example.com:bad"
        body = dict(bad_port); body.pop("campaign_sha256")
        bad_port["campaign_sha256"] = calibration._sha(body)
        bad_port_path = root / "bad-port.json"
        bad_port_pin = write_json(bad_port_path, bad_port)
        refuses(lambda: calibration.load_campaign(
            bad_port_path, expected_sha256=bad_port_pin),
            "malformed RPC port refuses with a typed calibration error")

        check(v2.INSTRUMENT != calibration.INSTRUMENT,
              "V2 finalized-latency artifacts cannot masquerade as V2.1 processed calibration")

    print(f"PAC V2.1 CALIBRATION SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
