#!/usr/bin/env python3
"""Negative + positive controls for the PAC V2 send tool (B3), the ed25519 wire check (B2a), and the
live finalized-RPC verification wired into activation (B2b). No network: the RPC is a local mock."""
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .execution import RefusedExecution
from . import pac_v2_calibration as cal
from . import pac_v2_calibration_attestation as att
from . import pac_v2_send as send

OK = True

# a mock DNS resolver returning a globally-routable address so tests stay hermetic (no real DNS)
def _GLOBAL(host, port, **k):
    return [(2, 1, 6, "", ("93.184.216.34", port or 443))]


def check(cond: bool, label: str) -> None:
    global OK
    OK = OK and bool(cond)
    print(f"  [{'ok' if cond else 'FAIL'}] {label}")


def refuses(fn, label: str) -> None:
    try:
        fn()
        check(False, label + " (did not refuse)")
    except (RefusedExecution, cal.CalibrationRefused):
        check(True, label)


def _key(seed: bytes) -> tuple[Ed25519PrivateKey, bytes, str]:
    k = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed).digest())
    pub = k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return k, pub, cal._b58encode(pub)


class _Resp:
    def __init__(self, body: dict):
        self._b = json.dumps(body).encode()
        self.status = 200
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _fixture(tmp: pathlib.Path, count: int, key, pub, payer_b58) -> tuple:
    """Write a campaign + a `count`-sample calibration of REAL signed memo txs. Returns
    (campaign_path, campaign_sha, calibration_path, calibration_sha, {signature: (wire_b64, slot)})."""
    campaign_id = hashlib.sha256(b"campaign-fixture").hexdigest()
    body = {"schema": cal.CAMPAIGN_SCHEMA, "instrument_id": cal.INSTRUMENT, "campaign_id": campaign_id,
            "seal_sha256": "a" * 64, "calibration_fee_payer": payer_b58,
            "submit_endpoint_scheme_host": "https://submit.example.com",
            "verification_endpoint_scheme_host": "https://verify.example.com",
            "started_unix_nanos": 1_700_000_000_000_000_000,
            "evidence_mode": "LOCAL_MONOTONIC_PLUS_FINALIZED_INDEPENDENT_RPC",
            "transaction_profile": cal.TRANSACTION_PROFILE, "memo_program_id": cal.MEMO_PROGRAM_ID}
    campaign_row = {**body, "campaign_sha256": cal._canonical_sha(body)}
    cpath = tmp / "campaign.json"
    cpath.write_bytes(cal._canonical(campaign_row) + b"\n")
    csha = hashlib.sha256(cpath.read_bytes()).hexdigest()
    names = ("decision", "build_start", "sign_done", "send_start", "send_ack", "land_observed")
    rows = []
    onchain = {}
    previous = campaign_id
    for i in range(count):
        memo = cal._campaign_memo(campaign_id, i, previous)
        wire_b64, signature = send.build_signed_memo(key, payer_b58, memo, bytes(32))
        wire = base64.b64decode(wire_b64)
        slot = i + 1
        dec = 1_700_000_010_000_000_000 + i * 2_000_000_000
        land = dec + (i + 1) * 1_000_000
        wall = {n: dec + j for j, n in enumerate(names[:-1])}; wall["land_observed"] = land
        mono = {n: 5_000_000_000_000 + i * 2_000_000_000 + j for j, n in enumerate(names[:-1])}
        mono["land_observed"] = 5_000_000_000_000 + i * 2_000_000_000 + (i + 1) * 1_000_000
        req = {"jsonrpc": "2.0", "id": i + 1, "method": "sendTransaction",
               "params": [wire_b64, {"encoding": "base64"}]}
        resp = {"jsonrpc": "2.0", "id": i + 1, "result": signature}
        raw = {"wire_transaction_base64": wire_b64, "wire_transaction_sha256": hashlib.sha256(wire).hexdigest(),
               "send_request_json": req, "send_request_sha256": cal._canonical_sha(req),
               "send_response_json": resp, "send_response_sha256": cal._canonical_sha(resp)}
        sb = {"schema": cal.SAMPLE_SCHEMA, "instrument_id": cal.INSTRUMENT, "campaign_id": campaign_id,
              "previous_sample_id": previous, "transaction_signature": signature, "outcome": "LANDED",
              "land_slot": slot, "clocks_unix_nanos": wall, "clocks_monotonic_nanos": mono,
              "raw_evidence": raw, "raw_evidence_sha256": cal._canonical_sha(raw)}
        row = {**sb, "sample_id": cal._canonical_sha(sb)}
        rows.append(row)
        onchain[signature] = (wire_b64, slot, land)
        previous = row["sample_id"]
    calpath = tmp / "calibration.jsonl"
    calpath.write_bytes(b"".join(cal._canonical(r) + b"\n" for r in rows))
    calsha = hashlib.sha256(calpath.read_bytes()).hexdigest()
    return cpath, csha, calpath, calsha, onchain


def _make_opener(onchain: dict, *, break_slot=False, missing=False):
    def opener(request, timeout=None):
        body = json.loads(request.data)
        sig = body["params"][0]
        wire_b64, slot, land = onchain[sig]
        if missing:
            return _Resp({"jsonrpc": "2.0", "id": 1, "result": None})
        result = {"slot": slot + (1000 if break_slot else 0),
                  "blockTime": land // 1_000_000_000, "meta": {"err": None},
                  "transaction": [wire_b64, "base64"]}
        return _Resp({"jsonrpc": "2.0", "id": 1, "result": result})
    return opener


class _FakeChain:
    """A stateful mock RPC: answers getLatestBlockhash / sendTransaction / getTransaction so the send
    tool's broadcast path runs end-to-end without real network. Counts how many txs it 'sent'."""
    def __init__(self):
        self.by_sig = {}
        self.slot = 1000
    def __call__(self, request, timeout=None):
        body = json.loads(request.data)
        method = body["method"]
        if method == "getLatestBlockhash":
            return _Resp({"result": {"value": {"blockhash": cal._b58encode(bytes(range(32)))}}})
        if method == "sendTransaction":
            wire_b64 = body["params"][0]
            sig = cal._b58encode(base64.b64decode(wire_b64)[1:65])
            self.slot += 1
            self.by_sig[sig] = (wire_b64, self.slot)
            return _Resp({"result": sig})
        if method == "getTransaction":
            wire_b64, slot = self.by_sig[body["params"][0]]
            return _Resp({"result": {"slot": slot, "blockTime": 1_700_000_000, "meta": {"err": None},
                                     "transaction": [wire_b64, "base64"]}})
        return _Resp({"error": {"message": "unknown method"}})


def _clocks():
    import itertools
    wc = itertools.count(1_700_000_000_000_000_000, 1000)
    mc = itertools.count(5_000_000_000_000, 1000)
    return (lambda: next(wc)), (lambda: next(mc))


def main() -> int:
    key, pub, payer = _key(b"pac-v2-send-selftest-payer")
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)

        # B2a: a forged (non-ed25519) signature is refused by the sealed wire parser
        memo = cal._campaign_memo("a" * 64, 0, "b" * 64)
        wire_b64, sig = send.build_signed_memo(key, payer, memo, bytes(32))
        raw = bytearray(base64.b64decode(wire_b64)); raw[1:65] = bytes(64)
        refuses(lambda: cal._wire_identity(base64.b64encode(bytes(raw)).decode(), expected_memo=memo),
                "B2a forged/zeroed signature is refused by ed25519")

        # B3 builder: a real memo tx round-trips through the sealed validator
        _w, s2, fp = cal._wire_identity(wire_b64, expected_memo=memo)
        check(fp == payer and s2 == sig, "B3 built memo tx round-trips (memo-only + valid signature)")

        # B3 rails: budget count + lamport caps refuse
        refuses(lambda: send.BudgetGuard(max_transactions=0, max_lamports=10_000),
                "B3 budget guard refuses a non-positive tx cap")
        g = send.BudgetGuard(max_transactions=1, max_lamports=10_000)
        g.admit(); g.charge()
        refuses(g.admit, "B3 budget guard refuses beyond the tx-count cap")
        g2 = send.BudgetGuard(max_transactions=100, max_lamports=send.DEFAULT_FEE_LAMPORTS)
        g2.admit(); g2.charge()
        refuses(g2.admit, "B3 budget guard refuses beyond the lamport cap")

        # B3 broadcast default-OFF: dry-run must not touch the network
        def _explode(*a, **k):
            raise AssertionError("dry-run must not open the network")
        cpath, csha, calpath, calsha, onchain = _fixture(tmp, 100, key, pub, payer)
        res = send.run(campaign_path=cpath, campaign_sha256=csha, keypair_path=_kpfile(tmp, key, pub),
                       out_path=tmp / "out.jsonl", max_transactions=100, max_lamports=1_000_000,
                       broadcast=False, submit_rpc_url=None, count=5, opener=_explode)
        check(res["broadcast"] is False and res["dry_run_built"] == 5 and res["spent_lamports"] == 0,
              "B3 dry-run builds+verifies without broadcasting or spending")

        # B3 fee-payer mismatch: a different keypair than the campaign fee payer refuses
        other_k, other_pub, _ = _key(b"pac-v2-send-selftest-other")
        refuses(lambda: send.run(campaign_path=cpath, campaign_sha256=csha,
                                 keypair_path=_kpfile(tmp, other_k, other_pub), out_path=tmp / "o.jsonl",
                                 max_transactions=100, max_lamports=1_000_000, broadcast=False,
                                 submit_rpc_url=None, count=1),
                "B3 refuses a keypair that is not the campaign fee payer")

        # B2b live_verify: a real bundle whose txs 'landed' on the mock RPC passes
        good = att.live_verify(campaign_path=cpath, campaign_sha256=csha, calibration_path=calpath,
                               calibration_sha256=calsha, rpc_url="https://verify.example.com",
                               opener=_make_opener(onchain), resolver=_GLOBAL)
        check(good["verified"] == 100, "B2b live_verify confirms 100 on-chain landings via the mock RPC")

        # B2b forgery: a never-broadcast bundle (getTransaction -> null) is refused
        refuses(lambda: att.live_verify(campaign_path=cpath, campaign_sha256=csha,
                                        calibration_path=calpath, calibration_sha256=calsha,
                                        rpc_url="https://verify.example.com",
                                        opener=_make_opener(onchain, missing=True), resolver=_GLOBAL),
                "B2b live_verify refuses a never-broadcast (null getTransaction) bundle")

        # B2b slot mismatch: on-chain slot != sampled slot is refused
        refuses(lambda: att.live_verify(campaign_path=cpath, campaign_sha256=csha,
                                        calibration_path=calpath, calibration_sha256=calsha,
                                        rpc_url="https://verify.example.com",
                                        opener=_make_opener(onchain, break_slot=True), resolver=_GLOBAL),
                "B2b live_verify refuses an on-chain slot that differs from the sample")

        # B2b origin: a verifier origin equal to the submit origin is refused
        refuses(lambda: att.live_verify(campaign_path=cpath, campaign_sha256=csha,
                                        calibration_path=calpath, calibration_sha256=calsha,
                                        rpc_url="https://submit.example.com", opener=_make_opener(onchain), resolver=_GLOBAL),
                "B2b live_verify refuses when verify origin is not the pre-committed verification origin")

        # HIGH regression: non-canonical loopback IPv4 + reserved/private hosts are rejected as RPC origins
        for bad in ("127.0.0.1", "127.1", "127.0.1", "0177.0.0.1", "0x7f.0.0.1", "2130706433",
                    "localhost", "10.0.0.5", "169.254.0.1", "foo.invalid", "rpc.local", "::1"):
            check(not cal._is_public_rpc_host(bad), f"loopback/private/reserved host rejected: {bad}")
        for good in ("api.mainnet-beta.solana.com", "verify.example.com", "8.8.8.8"):
            check(cal._is_public_rpc_host(good), f"genuine public host accepted: {good}")
        # a host that RESOLVES to loopback is rejected at the network layer even if it looks public
        refuses(lambda: att._scheme_host("https://sneaky-fake-rpc.com",
                                         resolver=lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))]),
                "B2b/host: a public-looking host resolving to loopback is refused")

        # B3 RESUME + campaign-wide budget (Codex handoff 442): a broadcast that stops must resume from
        # persisted samples, never re-send, never lose landed work, and never reset the budget cap.
        rtmp = tmp / "resume"; rtmp.mkdir()
        rk, rpub, rpayer = _key(b"pac-v2-resume-payer")
        rcpath, rcsha, _c, _cs, _o = _fixture(rtmp, 1, rk, rpub, rpayer)   # only the campaign is reused
        rkp = _kpfile(rtmp, rk, rpub)
        rout = rtmp / "resume_calibration.jsonl"
        chain = _FakeChain()
        clk, mon = _clocks()

        def _broadcast(count, max_tx=8, max_lam=1_000_000):
            return send.run(campaign_path=rcpath, campaign_sha256=rcsha, keypair_path=rkp, out_path=rout,
                            max_transactions=max_tx, max_lamports=max_lam, broadcast=True,
                            submit_rpc_url="https://submit.example.com", count=count, opener=chain,
                            clock=clk, monotonic=mon, sleep=lambda *_: None)

        r1 = _broadcast(3)
        n_after_3 = len(chain.by_sig)
        check(r1["landed"] == 3 and r1["resumed_from"] == 0 and n_after_3 == 3
              and len(rout.read_text().splitlines()) == 3,
              "B3 resume: first run persists 3 samples incrementally")
        r2 = _broadcast(3)
        check(r2["landed"] == 3 and r2["resumed_from"] == 3 and len(chain.by_sig) == 3,
              "B3 resume: re-run at the same count re-sends NOTHING (idempotent)")
        r3 = _broadcast(5)
        check(r3["landed"] == 5 and r3["resumed_from"] == 3 and len(chain.by_sig) == 5
              and r3["spent_lamports"] == 5 * send.DEFAULT_FEE_LAMPORTS,
              "B3 resume: a later run continues the chain and only sends the missing 2")
        # persisted chain still validates as a loadable calibration bundle prefix
        refuses(lambda: _broadcast(5, max_tx=4),
                "B3 campaign-wide budget: persisted sends count toward the cap (over-cap refused)")
        # tamper a persisted sample -> resume refuses (chain integrity)
        lines = rout.read_text().splitlines(); lines[1] = lines[1].replace('"outcome":"LANDED"', '"outcome":"FAILED"', 1)
        rout.write_text("\n".join(lines) + "\n")
        refuses(lambda: _broadcast(5), "B3 resume: a tampered persisted sample refuses to resume")

    print("PAC V2 send/attest selftest:", "PASS" if OK else "FAIL")
    return 0 if OK else 1


def _kpfile(tmp: pathlib.Path, key: Ed25519PrivateKey, pub: bytes) -> pathlib.Path:
    seed = key.private_bytes_raw()
    path = tmp / f"kp_{pub.hex()[:8]}.json"
    path.write_text(json.dumps(list(seed + pub)))
    return path


if __name__ == "__main__":
    raise SystemExit(main())
