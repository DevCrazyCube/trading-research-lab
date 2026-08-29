#!/usr/bin/env python3
"""Crash, resume, budget, and default-off controls for the PAC V2.1 sender journal."""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import tempfile
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .execution import RefusedExecution
from . import pac_v2_calibration as wire_schema
from . import pac_v21_calibration as calibration
from . import pac_v21_send as sender


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
    except RefusedExecution:
        check(True, label)
    else:
        raise AssertionError(label)


class Clock:
    def __init__(self):
        self.wall = 1_900_000_000_000_000_000
        self.mono = 1_000_000_000_000

    def wall_now(self) -> int:
        self.wall += 1_000_000
        return self.wall

    def mono_now(self) -> int:
        self.mono += 1_000_000
        return self.mono

    def sleep(self, seconds: float) -> None:
        nanos = int(seconds * 1_000_000_000)
        self.wall += nanos; self.mono += nanos


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class Rpc:
    def __init__(self, journal: pathlib.Path, *, interrupt_at: str | None = None):
        self.journal = journal
        self.interrupt_at = interrupt_at
        self.sent: list[str] = []
        self.signed_was_durable = True

    def __call__(self, request, timeout=None):
        del timeout
        row = json.loads(request.data)
        method = row["method"]
        if method == "getLatestBlockhash":
            value = {"jsonrpc": "2.0", "id": row["id"], "result": {"value": {
                "blockhash": wire_schema._b58encode(hashlib.sha256(
                    f"block-{len(self.sent)}".encode()).digest())}}}
        elif method == "getFeeForMessage":
            value = {"jsonrpc": "2.0", "id": row["id"],
                     "result": {"context": {"slot": 41}, "value": 5_000}}
        elif method == "sendTransaction":
            if self.interrupt_at == "send":
                self.interrupt_at = None
                raise KeyboardInterrupt("synthetic send crash")
            durable = json.loads(self.journal.read_text())
            self.signed_was_durable &= durable["attempts"][-1]["stage"] == "SIGNED"
            _wire, signature, _payer = wire_schema._wire_identity(row["params"][0])
            self.sent.append(signature)
            value = {"jsonrpc": "2.0", "id": row["id"], "result": signature}
        elif method == "getSignatureStatuses":
            if self.interrupt_at == "status":
                self.interrupt_at = None
                raise KeyboardInterrupt("synthetic post-ack crash")
            signature = row["params"][0][0]
            value = {"jsonrpc": "2.0", "id": row["id"], "result": {
                "context": {"slot": 42}, "value": [{
                    "slot": 42, "confirmations": 0, "err": None,
                    "confirmationStatus": "processed", "signature": signature,
                }]}}
        else:
            raise AssertionError(method)
        return Response(calibration._canonical(value))


def campaign(root: pathlib.Path, *, budget: int = 500_000) -> tuple[pathlib.Path, str, pathlib.Path]:
    private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"pac-v21-sender").digest())
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    payer = wire_schema._b58encode(public)
    keypair = root / "keypair.json"
    keypair.write_text(json.dumps(list(hashlib.sha256(b"pac-v21-sender").digest() + public)))
    body = {
        "schema": calibration.CAMPAIGN_SCHEMA, "instrument_id": calibration.INSTRUMENT,
        "campaign_id": hashlib.sha256(b"v21-send-campaign").hexdigest(),
        "seal_sha256": "a" * 64, "calibration_fee_payer": payer,
        "submit_endpoint_scheme_host": "https://submit.example.com",
        "verification_endpoint_scheme_host": "https://verify.example.com",
        "started_unix_nanos": 1, "max_transactions": 100, "max_lamports": budget,
        "poll_interval_nanos": calibration.POLL_INTERVAL_NANOS,
        "processed_deadline_nanos": calibration.PROCESSED_DEADLINE_NANOS,
        "evidence_mode": calibration.EVIDENCE_MODE,
        "transaction_profile": calibration.TRANSACTION_PROFILE,
        "memo_program_id": calibration.MEMO_PROGRAM_ID,
    }
    row = {**body, "campaign_sha256": calibration._sha(body)}
    path = root / "campaign.json"
    path.write_bytes(calibration._canonical(row) + b"\n")
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), keypair


def invoke(root: pathlib.Path, campaign_path: pathlib.Path, campaign_sha: str,
           keypair: pathlib.Path, rpc: Rpc, clock: Clock, *, successes: int = 1,
           boot_id: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", broadcast: bool = True):
    # Synthetic campaigns live in a temporary non-git repository. Production has no bypass: this
    # scoped mock exists only in the selftest and lets the remaining crash-state machine execute.
    with patch.object(sender, "_require_campaign_authority"):
        return sender.run(
            campaign_path=campaign_path, campaign_sha256=campaign_sha,
            keypair_path=keypair, journal_path=rpc.journal,
            samples_path=root / "samples.jsonl", successful_samples=successes,
            broadcast=broadcast, submit_rpc_url="https://submit.example.com/rpc" if broadcast else None,
            opener=rpc, clock=clock.wall_now, monotonic=clock.mono_now,
            sleep=clock.sleep, boot_id=boot_id)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pac_v21_send_") as temporary:
        root = pathlib.Path(temporary)
        campaign_path, campaign_sha, keypair = campaign(root)
        dry_journal = root / "dry-journal.json"
        dry_rpc = Rpc(dry_journal)
        dry = sender.run(
            campaign_path=campaign_path, campaign_sha256=campaign_sha,
            keypair_path=keypair, journal_path=dry_journal,
            samples_path=root / "dry-samples", successful_samples=2,
            broadcast=False, submit_rpc_url=None)
        check(dry["dry_run_built"] == 2 and not dry_journal.exists() and dry_rpc.sent == [],
              "default-off dry-run builds verified memos and writes/sends nothing")

        refuses(lambda: sender.run(
            campaign_path=campaign_path, campaign_sha256=campaign_sha,
            keypair_path=keypair, journal_path=dry_journal,
            samples_path=root / "never-samples", successful_samples=1,
            broadcast=True, submit_rpc_url="https://submit.example.com/rpc"),
            "unanchored or non-manifest campaign cannot broadcast")

        journal = root / "journal.json"
        rpc, clock = Rpc(journal), Clock()
        complete = invoke(root, campaign_path, campaign_sha, keypair, rpc, clock, successes=2)
        loaded_campaign = calibration.load_campaign(campaign_path, expected_sha256=campaign_sha)
        loaded = sender.load_journal(journal, loaded_campaign)
        check(complete["processed"] == 2 and complete["failed"] == 0
              and len(rpc.sent) == 2 and rpc.signed_was_durable,
              "every wire is durable before send and two processed samples complete")
        check(len((root / "samples.jsonl").read_text().splitlines()) == 2
              and all(item["stage"] == "PROCESSED" for item in loaded["attempts"]),
              "materialized samples derive exactly from terminal journal attempts")

        ack_root = root / "ack-resume"; ack_root.mkdir()
        ack_campaign, ack_sha, ack_key = campaign(ack_root)
        ack_journal = ack_root / "journal.json"
        ack_rpc, ack_clock = Rpc(ack_journal, interrupt_at="status"), Clock()
        try:
            invoke(ack_root, ack_campaign, ack_sha, ack_key, ack_rpc, ack_clock)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("post-ack crash fixture did not interrupt")
        check(json.loads(ack_journal.read_text())["attempts"][-1]["stage"] == "ACKED",
              "post-ack crash leaves one durable ACKED attempt")
        resumed = invoke(ack_root, ack_campaign, ack_sha, ack_key, ack_rpc, ack_clock)
        check(resumed["processed"] == 1 and len(ack_rpc.sent) == 1,
              "same-boot ACKED resume observes status without resending")

        signed_root = root / "signed-resume"; signed_root.mkdir()
        signed_campaign, signed_sha, signed_key = campaign(signed_root)
        signed_journal = signed_root / "journal.json"
        signed_rpc, signed_clock = Rpc(signed_journal, interrupt_at="send"), Clock()
        try:
            invoke(signed_root, signed_campaign, signed_sha, signed_key,
                   signed_rpc, signed_clock)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("pre-ack crash fixture did not interrupt")
        check(json.loads(signed_journal.read_text())["attempts"][-1]["stage"] == "SIGNED",
              "pre-ack crash leaves the exact signed wire durable")
        signed_done = invoke(signed_root, signed_campaign, signed_sha, signed_key,
                             signed_rpc, signed_clock)
        signed_loaded = json.loads(signed_journal.read_text())["attempts"]
        sender.load_journal(
            signed_journal,
            calibration.load_campaign(signed_campaign, expected_sha256=signed_sha))
        check(signed_done["processed"] == 1 and signed_done["failed"] == 1
              and [item["stage"] for item in signed_loaded] == ["FAILED", "PROCESSED"],
              "uncertain pre-ack signature becomes visible failure and is never reused")

        boot_root = root / "boot-resume"; boot_root.mkdir()
        boot_campaign, boot_sha, boot_key = campaign(boot_root)
        boot_journal = boot_root / "journal.json"
        boot_rpc, boot_clock = Rpc(boot_journal, interrupt_at="status"), Clock()
        try:
            invoke(boot_root, boot_campaign, boot_sha, boot_key, boot_rpc, boot_clock,
                   boot_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        except KeyboardInterrupt:
            pass
        boot_done = invoke(
            boot_root, boot_campaign, boot_sha, boot_key, boot_rpc, boot_clock,
            boot_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        check(boot_done["failed"] == 1 and boot_done["processed"] == 1
              and len(boot_rpc.sent) == 2,
              "boot-epoch change refuses old monotonic latency and uses a new signature")

        cap_root = root / "cap"; cap_root.mkdir()
        cap_campaign, cap_sha, cap_key = campaign(cap_root, budget=5_000)
        cap_journal = cap_root / "journal.json"
        cap_rpc, cap_clock = Rpc(cap_journal), Clock()
        refuses(lambda: invoke(
            cap_root, cap_campaign, cap_sha, cap_key, cap_rpc, cap_clock, successes=2),
            "second exact fee quote cannot cross the campaign lamport cap")

        tampered = json.loads(journal.read_text())
        tampered["attempts"][0]["quoted_fee_lamports"] += 1
        tampered_path = root / "tampered.json"
        tampered_path.write_text(json.dumps(tampered))
        refuses(lambda: sender.load_journal(tampered_path, loaded_campaign),
                "journal byte/content tampering refuses before resume")

    print(f"PAC V2.1 SEND SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
