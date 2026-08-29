#!/usr/bin/env python3
"""PAC V2 calibration send tool — build/sign/broadcast the frozen memo-only campaign transactions.

SAFETY RAILS (all enforced in code, none optional):
  * BROADCAST IS DEFAULT-OFF. Without ``--broadcast`` the tool builds + signs + self-verifies every
    transaction and sends NOTHING (dry-run). Nothing leaves this machine unless ``--broadcast`` is passed.
  * HARD BUDGET CAP. ``--max-transactions`` and ``--max-lamports`` bound the campaign; the tool refuses to
    build or send beyond either, and refuses before any send whose cumulative fee would exceed the cap.
  * MEMO-ONLY BY CONSTRUCTION. Every transaction is the frozen LEGACY_SINGLE_SIGNER_CAMPAIGN_MEMO_ONLY
    profile, re-parsed through the sealed calibration validator (which also ed25519-verifies the signature
    and the exact campaign memo) before it may be sent. No code path here emits any other instruction.
  * EXPLICIT FEE-PAYER KEYPAIR. The signer is loaded from an explicit ``--keypair`` file and its derived
    public key MUST equal the pre-committed campaign fee payer, or the tool refuses.

It holds no default wallet, hardcodes no key, and cannot trade — the only instruction it can emit is a
campaign-bound SPL memo. Real p90 latency comes only from a ``--broadcast`` run against a funded fee payer.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .execution import RefusedExecution
from . import pac_v2_calibration as calibration

ENV_SUBMIT = "PAC_V2_SUBMIT_RPC_URL"
DEFAULT_FEE_LAMPORTS = 5_000          # one signature; the campaign never adds priority fee
TIMEOUT_SECONDS = 20.0
FINALIZE_POLL_SECONDS = 1.0
FINALIZE_DEADLINE_SECONDS = 120.0


class SendRefused(RefusedExecution):
    pass


# ----------------------------- fee-payer keypair -----------------------------
def load_fee_payer(path: pathlib.Path) -> tuple[Ed25519PrivateKey, str]:
    """Load an explicit ed25519 fee payer. Accepts a Solana 64-int JSON array (seed||pubkey) or a raw
    32-byte seed / 64-byte secret file. Returns (private_key, base58_public_key)."""
    try:
        payload = pathlib.Path(path).read_bytes()
    except OSError as exc:
        raise SendRefused(f"fee-payer keypair unavailable: {exc}") from exc
    secret: bytes
    declared_pub: bytes | None = None
    text = payload.strip()
    if text[:1] in (b"[", b"{"):
        try:
            arr = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SendRefused("fee-payer keypair JSON is invalid") from exc
        if (not isinstance(arr, list) or len(arr) not in (32, 64)
                or any(type(v) is not int or v < 0 or v > 255 for v in arr)):
            raise SendRefused("fee-payer keypair must be a 32- or 64-byte integer array")
        raw = bytes(arr)
        secret = raw[:32]
        declared_pub = raw[32:64] if len(raw) == 64 else None
    elif len(text) in (32, 64):
        secret = text[:32]
        declared_pub = text[32:64] if len(text) == 64 else None
    else:
        raise SendRefused("fee-payer keypair file is not a recognised 32/64-byte secret")
    try:
        private = Ed25519PrivateKey.from_private_bytes(secret)
    except ValueError as exc:
        raise SendRefused("fee-payer seed is not a valid ed25519 private key") from exc
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    if declared_pub is not None and declared_pub != public:
        raise SendRefused("fee-payer keypair public half does not match its secret half")
    return private, calibration._b58encode(public)


# ----------------------------- wire construction -----------------------------
def _shortvec_encode(value: int) -> bytes:
    if value < 0:
        raise SendRefused("shortvec length cannot be negative")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def build_signed_memo(private: Ed25519PrivateKey, fee_payer_b58: str, memo: bytes,
                      recent_blockhash: bytes) -> tuple[str, str]:
    """Build + sign one frozen single-signer memo-only legacy transaction, then re-parse it through the
    sealed calibration validator (memo-binding + ed25519 signature check) before returning it."""
    fee_payer = calibration._b58decode("fee payer", fee_payer_b58, exact_length=32)
    memo_program = calibration._b58decode("memo program id", calibration.MEMO_PROGRAM_ID, exact_length=32)
    if len(recent_blockhash) != 32:
        raise SendRefused("recent blockhash must be 32 bytes")
    header = bytes([1, 0, 1])                                   # 1 required signer, 0 ro-signed, 1 ro-unsigned
    accounts = _shortvec_encode(2) + fee_payer + memo_program
    instruction = bytes([1]) + _shortvec_encode(0) + _shortvec_encode(len(memo)) + memo
    message = header + accounts + recent_blockhash + _shortvec_encode(1) + instruction
    signature = private.sign(message)
    wire = _shortvec_encode(1) + signature + message
    encoded = base64.b64encode(wire).decode("ascii")
    # Self-verify against the SEALED validator: proves memo-only profile + a valid ed25519 signature by the
    # declared fee payer. If this raises, the tool refuses to emit the transaction.
    _wire, wire_signature, wire_fee_payer = calibration._wire_identity(encoded, expected_memo=memo)
    if wire_fee_payer != fee_payer_b58:
        raise SendRefused("built transaction fee payer does not match the campaign fee payer")
    return encoded, wire_signature


# ----------------------------- budget rail -----------------------------
@dataclass
class BudgetGuard:
    max_transactions: int
    max_lamports: int
    fee_lamports_per_tx: int = DEFAULT_FEE_LAMPORTS

    def __post_init__(self) -> None:
        if self.max_transactions < 1 or self.max_transactions > 100_000:
            raise SendRefused("max transactions must be a sane positive bound")
        if self.max_lamports < self.fee_lamports_per_tx:
            raise SendRefused("max lamport budget is below one transaction fee")
        self.sent = 0
        self.spent = 0

    def admit(self) -> None:
        if self.sent >= self.max_transactions:
            raise SendRefused("campaign transaction-count cap reached")
        if self.spent + self.fee_lamports_per_tx > self.max_lamports:
            raise SendRefused("campaign lamport budget cap reached")

    def charge(self) -> None:
        self.sent += 1
        self.spent += self.fee_lamports_per_tx


# ----------------------------- RPC (broadcast path only) -----------------------------
_RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0, 8.0, 12.0)
_TRANSIENT_HTTP = (429, 500, 502, 503, 504)


def _rpc(url: str, request_json: dict, *, opener=None) -> dict:
    """One submit-RPC call, resilient to transient 429/5xx/network failures. getLatestBlockhash and
    getTransaction are reads; sendTransaction is idempotent by signature (a retried identical wire
    dedupes to the same on-chain transaction), so retrying is safe and cannot double-spend fees."""
    data = calibration._canonical(request_json)
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            response = (opener or urllib.request.urlopen)(request, timeout=TIMEOUT_SECONDS)
            with response:
                payload = response.read()
            result = json.loads(payload)
        except urllib.error.HTTPError as exc:
            if exc.code in _TRANSIENT_HTTP and attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt]); continue
            raise SendRefused("PAC V2 submit RPC failed: HTTPError") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt]); continue
            raise SendRefused(f"PAC V2 submit RPC failed: {type(exc).__name__}") from exc
        except json.JSONDecodeError as exc:
            raise SendRefused("PAC V2 submit RPC returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise SendRefused("PAC V2 submit RPC returned a non-object")
        return result
    raise SendRefused("PAC V2 submit RPC exhausted retries")


def _clock_pair(names: tuple[str, ...], wall: list[int], mono: list[int]) -> tuple[dict, dict]:
    return ({name: wall[i] for i, name in enumerate(names)},
            {name: mono[i] for i, name in enumerate(names)})


def run(*, campaign_path: pathlib.Path, campaign_sha256: str, keypair_path: pathlib.Path,
        out_path: pathlib.Path, max_transactions: int, max_lamports: int,
        broadcast: bool, submit_rpc_url: str | None, count: int, opener=None,
        clock=time.time_ns, monotonic=time.monotonic_ns, sleep=time.sleep) -> dict:
    campaign = calibration.load_campaign(pathlib.Path(campaign_path), expected_sha256=campaign_sha256)
    private, fee_payer_b58 = load_fee_payer(keypair_path)
    if fee_payer_b58 != campaign.calibration_fee_payer:
        raise SendRefused("loaded keypair is not the pre-committed campaign fee payer")
    if count < 1 or count > max_transactions:
        raise SendRefused("requested count must be between 1 and max-transactions")
    guard = BudgetGuard(max_transactions=max_transactions, max_lamports=max_lamports)
    names = ("decision", "build_start", "sign_done", "send_start", "send_ack", "land_observed")

    if broadcast:
        if not submit_rpc_url:
            raise SendRefused(f"broadcast requires {ENV_SUBMIT}")
        # the submit URL's origin must equal the committed submit origin (already distinct from verify)
        import urllib.parse as _u
        parsed = _u.urlsplit(submit_rpc_url)
        port = f":{parsed.port}" if parsed.port is not None else ""
        if (parsed.scheme != "https" or not parsed.hostname
                or f"https://{parsed.hostname}{port}" != campaign.submit_endpoint_scheme_host):
            raise SendRefused("submit RPC origin differs from the pre-committed campaign submit origin")

    if not broadcast:
        # DRY-RUN: build + self-verify `count` memo txs with a placeholder blockhash; send nothing.
        for index in range(count):
            guard.admit()
            memo = calibration._campaign_memo(campaign.campaign_id, index, campaign.campaign_id)
            build_signed_memo(private, fee_payer_b58, memo, bytes(32))
            guard.charge()
        return {"broadcast": False, "dry_run_built": count, "spent_lamports": 0,
                "note": "no transaction was sent; pass --broadcast with a funded fee payer to sample latency"}

    # BROADCAST: resume from any already-persisted samples so a crash/stop never re-sends, loses landed
    # work, or resets the budget. The budget is CAMPAIGN-WIDE — prior sends count toward the same cap.
    out = pathlib.Path(out_path)
    samples = _load_existing_samples(out, campaign)
    guard.sent = len(samples)
    guard.spent = len(samples) * guard.fee_lamports_per_tx
    if guard.sent > guard.max_transactions or guard.spent > guard.max_lamports:
        raise SendRefused("already-persisted samples exceed the campaign budget cap")
    resumed_from = len(samples)
    previous = samples[-1]["sample_id"] if samples else campaign.campaign_id
    for index in range(len(samples), count):
        guard.admit()                                              # campaign-wide cap, seeded from disk
        memo = calibration._campaign_memo(campaign.campaign_id, index, previous)
        decision_w, decision_m = clock(), monotonic()
        blockhash = _b58decode_blockhash(_latest_blockhash(submit_rpc_url, opener=opener))
        build_w, build_m = clock(), monotonic()
        wire_b64, signature = build_signed_memo(private, fee_payer_b58, memo, blockhash)
        sign_w, sign_m = clock(), monotonic()
        request_json = {"jsonrpc": "2.0", "id": index + 1, "method": "sendTransaction",
                        "params": [wire_b64, {"encoding": "base64", "skipPreflight": False,
                                              "preflightCommitment": "processed"}]}
        send_w, send_m = clock(), monotonic()
        response_json = _rpc(submit_rpc_url, request_json, opener=opener)
        ack_w, ack_m = clock(), monotonic()
        if response_json.get("result") != signature or response_json.get("error") is not None:
            raise SendRefused(f"sample {index} send was not acknowledged with its signature")
        land_slot, land_w, land_m = _await_finalized(
            submit_rpc_url, signature, opener=opener, clock=clock, monotonic=monotonic, sleep=sleep)
        wall_map, mono_map = _clock_pair(
            names, [decision_w, build_w, sign_w, send_w, ack_w, land_w],
            [decision_m, build_m, sign_m, send_m, ack_m, land_m])
        wire_sha = hashlib.sha256(base64.b64decode(wire_b64)).hexdigest()
        raw_evidence = {
            "wire_transaction_base64": wire_b64, "wire_transaction_sha256": wire_sha,
            "send_request_json": request_json,
            "send_request_sha256": calibration._canonical_sha(request_json),
            "send_response_json": response_json,
            "send_response_sha256": calibration._canonical_sha(response_json)}
        body = {
            "schema": calibration.SAMPLE_SCHEMA, "instrument_id": calibration.INSTRUMENT,
            "campaign_id": campaign.campaign_id, "previous_sample_id": previous,
            "transaction_signature": signature, "outcome": "LANDED", "land_slot": land_slot,
            "clocks_unix_nanos": wall_map, "clocks_monotonic_nanos": mono_map,
            "raw_evidence": raw_evidence,
            "raw_evidence_sha256": calibration._canonical_sha(raw_evidence)}
        sample = {**body, "sample_id": calibration._canonical_sha(body)}
        samples.append(sample)
        _atomic_write_jsonl(out, samples)          # crash-safe persist AFTER each finalized send
        guard.charge()
        previous = sample["sample_id"]
    return {"broadcast": True, "landed": len(samples), "resumed_from": resumed_from,
            "out": str(out), "spent_lamports": guard.spent}


def _load_existing_samples(out_path: pathlib.Path, campaign) -> list[dict]:
    """Resume support: read the samples already landed+persisted for THIS campaign and validate they chain
    correctly, so a re-run continues from where it stopped instead of re-sending or losing budget."""
    path = pathlib.Path(out_path)
    if not path.exists():
        return []
    samples: list[dict] = []
    previous = campaign.campaign_id
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SendRefused(f"persisted calibration line {number} is corrupt JSON") from exc
        if (not isinstance(row, dict) or row.get("campaign_id") != campaign.campaign_id
                or row.get("previous_sample_id") != previous or row.get("outcome") != "LANDED"
                or not isinstance(row.get("sample_id"), str)):
            raise SendRefused(f"persisted calibration sample {number} does not chain to this campaign")
        body = {k: v for k, v in row.items() if k != "sample_id"}
        if calibration._canonical_sha(body) != row["sample_id"]:
            raise SendRefused(f"persisted calibration sample {number} self-hash mismatch")
        samples.append(row)
        previous = row["sample_id"]
    return samples


def _latest_blockhash(url: str, *, opener=None) -> str:
    result = _rpc(url, {"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash",
                        "params": [{"commitment": "finalized"}]}, opener=opener)
    value = (result.get("result") or {}).get("value") or {}
    blockhash = value.get("blockhash")
    if not isinstance(blockhash, str):
        raise SendRefused("submit RPC did not return a recent blockhash")
    return blockhash


def _b58decode_blockhash(blockhash: str) -> bytes:
    return calibration._b58decode("recent blockhash", blockhash, exact_length=32)


def _await_finalized(url: str, signature: str, *, opener, clock, monotonic, sleep) -> tuple[int, int, int]:
    deadline = monotonic() + int(FINALIZE_DEADLINE_SECONDS * 1_000_000_000)
    while monotonic() < deadline:
        result = _rpc(url, {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                            "params": [signature, {"commitment": "finalized", "encoding": "base64",
                                                   "maxSupportedTransactionVersion": 0}]}, opener=opener)
        landed = result.get("result") if result.get("error") is None else None
        if isinstance(landed, dict) and type(landed.get("slot")) is int:
            meta = landed.get("meta")
            if not isinstance(meta, dict) or meta.get("err") is not None:
                raise SendRefused("sample landed with an on-chain error")
            return landed["slot"], clock(), monotonic()
        sleep(FINALIZE_POLL_SECONDS)
    raise SendRefused("sample was not finalized before the deadline")


def _atomic_write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pac_v2_send_", suffix=".jsonl")
    try:
        with os.fdopen(fd, "wb") as handle:
            for row in rows:
                handle.write(calibration._canonical(row) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2 memo-only calibration sender (broadcast default-OFF)")
    parser.add_argument("--campaign", required=True, type=pathlib.Path)
    parser.add_argument("--campaign-sha256", required=True)
    parser.add_argument("--keypair", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--count", required=True, type=int)
    parser.add_argument("--max-transactions", required=True, type=int)
    parser.add_argument("--max-lamports", required=True, type=int)
    parser.add_argument("--broadcast", action="store_true",
                        help="ACTUALLY send transactions (default OFF: dry-run build+verify only)")
    args = parser.parse_args(argv)
    submit_rpc_url = os.environ.get(ENV_SUBMIT) if args.broadcast else None
    try:
        result = run(campaign_path=args.campaign, campaign_sha256=args.campaign_sha256,
                     keypair_path=args.keypair, out_path=args.out,
                     max_transactions=args.max_transactions, max_lamports=args.max_lamports,
                     broadcast=args.broadcast, submit_rpc_url=submit_rpc_url, count=args.count)
    except RefusedExecution as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True))
        return 2
    print(json.dumps({"status": "OK", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
