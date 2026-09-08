"""Replay a CLOSED birth-stream session; optionally reconcile a bounded pilot over RPC.

Never modifies the source. RPC responses are saved before parsing. Matching observed
transactions is not a census of unobserved creations or independent-provider proof.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import urllib.error
import urllib.request
import zlib

from scripts import b9d_transaction_bodies as B9D
from scripts.birth_origin import ROOT, Refused, canonical, write_new
from scripts.birth_stream import COMMITMENT, SOURCE, decode_notification, load_idl

RPC = "https://api.mainnet-beta.solana.com"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        manifest_json, end_json = db.execute("SELECT manifest_json,end_json FROM session WHERE id=1").fetchone()
        if end_json is None:
            raise Refused("only a closed session can be attested")
        manifest, end = json.loads(manifest_json), json.loads(end_json)
        if manifest["idl_sha256"] != B9D.PUMP_IDL_SHA256:
            raise Refused("session IDL does not match replay IDL")
        if manifest["schema"] not in {"birth-stream-v1", "birth-stream-v2", "birth-stream-v3-batched"}:
            raise Refused("unknown recorder schema")
        version2 = manifest["schema"] in {"birth-stream-v2", "birth-stream-v3-batched"}
        epochs, gaps = {}, []
        if version2:
            next_sequence = 1
            for epoch in db.execute("SELECT * FROM connection_epoch ORDER BY id"):
                if (epoch["id"] != len(epochs) + 1 or epoch["first_sequence"] != next_sequence
                        or epoch["end_sequence"] is None or epoch["end_sequence"] < next_sequence - 1
                        or epoch["ended_unix_nanos"] is None):
                    raise Refused("connection epochs are incomplete or overlap")
                next_sequence = epoch["end_sequence"] + 1
                epochs[epoch["id"]] = dict(epoch)
            gaps = [dict(gap) for gap in db.execute("SELECT * FROM capture_gap ORDER BY id")]
            if next_sequence != end["frames"] + 1 or end["connection_epochs"] != len(epochs) or end["unrepaired_gaps"] != len(gaps):
                raise Refused("epoch/gap accounting disagrees with session summary")
            for gap in gaps:
                if gap["coverage"] != "UNKNOWN_UNREPAIRED":
                    raise Refused("reconnection cannot repair coverage")
                if gap["before_epoch"] not in epochs or gap["after_sequence"] != epochs[gap["before_epoch"]]["end_sequence"]:
                    raise Refused("gap boundary is not a connection end")
                if gap["resumed_sequence"] is not None:
                    raw = db.execute("SELECT * FROM raw_frame WHERE sequence=?", (gap["resumed_sequence"],)).fetchone()
                    if (raw is None or raw["connection_epoch"] != gap["resumed_epoch"]
                            or raw["received_unix_nanos"] != gap["resumed_unix_nanos"]
                            or gap["resumed_epoch"] <= gap["before_epoch"]):
                        raise Refused("gap resumption does not match a later receipt")
                    message = json.loads(zlib.decompress(raw["raw_zlib"]))
                    if (message.get("method") != "logsNotification" or raw["decode_status"] != "CLASSIFIED"
                            or message["params"]["result"]["context"]["slot"] != gap["resumed_slot"]):
                        raise Refused("acknowledgement is not notification resumption")
            for epoch in list(epochs.values())[:-1]:
                if epoch["outcome"] != "TRANSPORT_GAP" or not any(
                        g["before_epoch"] <= epoch["id"] and (g["resumed_epoch"] is None or g["resumed_epoch"] > epoch["id"])
                        for g in gaps):
                    raise Refused("reconnection has no explicit gap")
        idl, subscription, previous, count = load_idl(), None, "0" * 64, 0
        current_epoch = None
        observations, stats_all, refusals = [], Counter(), 0
        expected_rows = {}
        for row in db.execute("SELECT * FROM raw_frame ORDER BY sequence"):
            count += 1
            if row["sequence"] != count or row["previous_sha256"] != previous:
                raise Refused("raw sequence or hash-chain gap")
            raw = zlib.decompress(row["raw_zlib"])
            body = {key: row[key] for key in ("sequence", "received_unix_nanos",
                "received_monotonic_nanos", "raw_sha256", "raw_bytes", "previous_sha256")}
            if version2:
                body["connection_epoch"] = row["connection_epoch"]
                epoch = epochs.get(row["connection_epoch"])
                if epoch is None or not epoch["first_sequence"] <= count <= epoch["end_sequence"]:
                    raise Refused("raw frame is outside its recorded connection epoch")
                if current_epoch != epoch["id"]:
                    current_epoch, subscription = epoch["id"], None
            if sha(raw) != row["raw_sha256"] or len(raw) != row["raw_bytes"] or sha(canonical(body)) != row["record_sha256"]:
                raise Refused("raw payload or receipt hash mismatch")
            previous = row["record_sha256"]
            try:
                message = json.loads(raw)
                if subscription is None:
                    if message.get("id") != 1 or type(message.get("result")) is not int:
                        raise Refused("subscription was not acknowledged")
                    subscription, births, stats = message["result"], [], {"subscription_ack": 1}
                else:
                    births, stats = decode_notification(message, idl, subscription)
            except Exception:
                if row["decode_status"] != "REFUSED":
                    raise Refused("replay refused a frame not recorded as refused")
                if not db.execute("SELECT 1 FROM issue WHERE sequence=? AND kind='DECODE_REFUSED'", (count,)).fetchone():
                    raise Refused("refused raw frame has no issue")
                refusals += 1
                continue
            if row["decode_status"] != "CLASSIFIED" or json.loads(row["accounting_json"]) != stats:
                raise Refused("frame classification does not reproduce")
            if version2 and stats == {"subscription_ack": 1} and (
                    epoch["ack_sequence"] != count or epoch["subscription_id"] != subscription):
                raise Refused("epoch subscription does not match its raw acknowledgement")
            stats_all.update(stats)
            for birth in births:
                event_time = birth["fields"]["timestamp"] * 1_000_000_000
                evidence = {**birth, "source": SOURCE, "commitment_at_observation": COMMITMENT,
                    "provenance": "observed_live", "received_unix_nanos": row["received_unix_nanos"],
                    "received_monotonic_nanos": row["received_monotonic_nanos"], "frame_sequence": count,
                    "event_time_unix_nanos": event_time,
                    "publication_not_after_receipt": event_time <= row["received_unix_nanos"], "status": "NO_TRADE"}
                if version2:
                    evidence["connection_epoch"] = row["connection_epoch"]
                expected_rows[(count, birth["log_index"])] = (birth["signature"], birth["slot"],
                    int(birth["transaction_succeeded"]), birth["event_payload_sha256"], canonical(evidence).decode())
                observations.append(evidence)
        actual = {(r[0], r[1]): tuple(r)[2:] for r in db.execute("SELECT * FROM create_observation")}
        if actual != expected_rows:
            raise Refused("materialized creates do not reproduce exactly from raw frames")
        if manifest["schema"] == "birth-stream-v3-batched":
            next_sequence = 1
            for batch in db.execute("SELECT * FROM flush_batch ORDER BY first_sequence"):
                if (batch["first_sequence"] != next_sequence or batch["last_sequence"] < next_sequence
                        or batch["raw_committed_unix_nanos"] is None or batch["derived_committed_unix_nanos"] is None
                        or batch["derived_committed_unix_nanos"] < batch["raw_committed_unix_nanos"]):
                    raise Refused("raw/derived batch durability timing is incomplete")
                latest_receipt = db.execute("SELECT max(received_unix_nanos) FROM raw_frame WHERE sequence BETWEEN ? AND ?",
                    (batch["first_sequence"], batch["last_sequence"])).fetchone()[0]
                if latest_receipt is None or batch["raw_committed_unix_nanos"] < latest_receipt:
                    raise Refused("batch claims durability before its receipt")
                next_sequence = batch["last_sequence"] + 1
            if next_sequence != count + 1:
                raise Refused("raw frame has no durability batch")
        issues = db.execute("SELECT count(*) FROM issue").fetchone()[0]
        if (end["frames"] != count or end["frame_chain_tail"] != previous
                or end["create_observations"] != len(observations) or end["issues"] != issues):
            raise Refused("closed-session counts or tail disagree")
        report = {"raw_replay": "EXACT", "source": str(path), "source_manifest": manifest,
            "source_end": end, "frames": count, "creates": len(observations), "refused_frames": refusals,
            "issues": issues, "event_accounting": dict(stats_all), "tail": previous,
            "duplicate_create_observations": len(observations) - len({(o["signature"], o["event_payload_sha256"]) for o in observations}),
            "observations_sha256": sha(canonical(observations)), "coverage": "UNMEASURED_SINGLE_SOURCE",
            "status": "NO_TRADE", "replay_code_sha256": sha(Path(__file__).read_bytes())}
        if version2:
            report.update(connection_epochs=list(epochs.values()), unrepaired_gaps=gaps)
        return report, observations
    finally:
        db.close()


class EvidenceRPC:
    """Public, credential-free, bounded requests. No retry or alternate source hidden."""
    def __init__(self, out):
        self.out, self.sequence = out, 0

    def call(self, method, params):
        if method not in {"getTransaction", "getBlock", "getSlot"}:
            raise Refused("read-only RPC method not allowed")
        self.sequence += 1
        request = {"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params}
        prefix = self.out / f"rpc_{self.sequence:04d}"
        before_wall, before_mono = time.time_ns(), time.monotonic_ns()
        receipt = {"endpoint": RPC, "request": request, "sent_unix_nanos": before_wall,
                   "sent_monotonic_nanos": before_mono}
        try:
            req = urllib.request.Request(RPC, data=canonical(request), headers={"Content-Type": "application/json"})
            try:
                response = urllib.request.urlopen(req, timeout=15)
            except urllib.error.HTTPError as error:
                response = error  # retain error body too
            with response:
                raw = response.read(16 * 1024 ** 2 + 1)
                receipt.update(http_status=response.status, received_unix_nanos=time.time_ns(),
                               received_monotonic_nanos=time.monotonic_ns())
            with prefix.with_suffix(".response").open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            receipt.update(response_sha256=sha(raw), response_bytes=len(raw))
            write_new(prefix.with_suffix(".json"), receipt)
            if len(raw) > 16 * 1024 ** 2 or receipt["http_status"] != 200:
                raise Refused("HTTP error or oversized RPC response")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            receipt.update(transport_error=type(error).__name__ + ": " + str(error), finished_unix_nanos=time.time_ns())
            if not prefix.with_suffix(".json").exists():
                write_new(prefix.with_suffix(".json"), receipt)
            raise
        reply = json.loads(raw)
        if reply.get("id") != self.sequence or reply.get("error") or reply.get("result") is None:
            raise Refused("RPC error, unavailable result, or response identity mismatch")
        return reply["result"]


class ReplayRPC:
    """Reproduce RPC-derived rows without making another network request."""
    def __init__(self, source):
        self.records = {}
        for path in sorted(source.glob("rpc_*.json")):
            receipt = json.loads(path.read_bytes())
            if "response_sha256" not in receipt:
                continue
            raw = path.with_suffix(".response").read_bytes()
            if sha(raw) != receipt["response_sha256"] or len(raw) != receipt["response_bytes"]:
                raise Refused("preserved RPC bytes do not match receipt")
            request = receipt["request"]
            key = canonical([request["method"], request["params"]])
            if key in self.records:
                raise Refused("ambiguous repeated RPC request; choose one preserved attempt explicitly")
            self.records[key] = (receipt, json.loads(raw))

    def call(self, method, params):
        receipt, reply = self.records.get(canonical([method, params]), (None, None))
        if receipt is None:
            raise Refused("requested RPC evidence was not preserved")
        if (receipt["endpoint"] != RPC or receipt["http_status"] != 200
                or reply.get("id") != receipt["request"]["id"] or reply.get("error")
                or reply.get("result") is None):
            raise Refused("preserved RPC request/response did not succeed")
        return reply["result"]


def reconcile_one(observation, transaction, block, idls):
    """Canonical coordinates are event-CPI indexes, matching B7d create_event schema."""
    slot, signature = observation["slot"], observation["signature"]
    if transaction.get("slot") != slot:
        raise Refused("transaction slot mismatch")
    signatures = block.get("signatures")
    if not isinstance(signatures, list):
        raise Refused("missing block signature census")
    index = B9D.transaction_coordinates(slot, signatures, [signature])[signature]
    encoded = transaction.get("transaction")
    if not isinstance(encoded, list) or len(encoded) != 2 or encoded[1] != "base64":
        raise Refused("wrong transaction encoding")
    wire = base64.b64decode(encoded[0], validate=True)
    sig_count, offset = B9D.compact_u16(wire, 0)
    if sig_count < 1 or len(wire) < offset + sig_count * 64 or B9D.base58(wire[offset:offset + 64]) != signature:
        raise Refused("wire signature mismatch")
    meta = transaction.get("meta") or {}
    if "err" not in meta or (meta["err"] is None) != observation["transaction_succeeded"]:
        raise Refused("transaction success mismatch")
    if meta["err"] is not None:
        return {"status": "FAILED_TRANSACTION_NOT_A_BIRTH", "signature": signature, "slot": slot,
                "transaction_index": index, "frame_sequence": observation["frame_sequence"]}
    if type(block.get("blockTime")) is not int or transaction.get("blockTime") != block["blockTime"]:
        raise Refused("block clock missing or inconsistent")
    matches = []
    for parent, event, decoded in B9D.associate_cpi_events(B9D.envelope_instructions(transaction), idls):
        if event["program_id"] != B9D.PUMP_PROGRAM or decoded["name"] != "CreateEvent":
            continue
        payload = event["data"][len(B9D.ANCHOR_EVENT_CPI_TAG):]
        if sha(payload) != observation["event_payload_sha256"]:
            continue
        if parent["program_id"] != B9D.PUMP_PROGRAM or decoded["fields"] != observation["fields"]:
            raise Refused("creation parent or fields mismatch")
        matches.append((event, decoded["fields"]))
    if len(matches) != 1:
        raise Refused("creation payload does not have one exact CPI match")
    event, fields = matches[0]
    canonical_row = {"slot": slot, "transaction_index": index,
        "outer_instruction_index": event["outer_index"], "inner_instruction_index": event["inner_index"],
        "signature": signature, "block_time": block["blockTime"],
        **{key: fields[key] for key in ("mint", "bonding_curve", "creator", "user", "quote_mint")},
        **{key: int(fields[key]) for key in ("is_mayhem_mode", "is_cashback_enabled")},
        "fields_json": canonical(fields).decode(), "event_payload_base64": observation["event_payload_base64"]}
    return {"status": "OBSERVED_CREATE_RECONCILED", "canonical_create_event": canonical_row,
        "frame_sequence": observation["frame_sequence"], "log_index": observation["log_index"],
        "first_received_unix_nanos": observation["received_unix_nanos"],
        "receipt_not_replaced_by_backfill": True, "trade_status": "NO_TRADE"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rpc", action="store_true", help="at most 20 observed transactions, 40 read-only requests")
    mode.add_argument("--rpc-evidence", type=Path, help="replay saved RPC bytes; NO network")
    args = parser.parse_args()
    if args.out.exists():
        raise Refused("new output directory required")
    report, observations = verify(args.source)
    signatures = {o["signature"] for o in observations}
    if args.rpc and len(signatures) > 20:
        raise Refused("pilot RPC bound exceeded; no outcome-based subsampling")
    args.out.mkdir(parents=True)
    write_new(args.out / "raw_replay.json", report)
    if args.rpc or args.rpc_evidence:
        idls = {B9D.PUMP_PROGRAM: load_idl(), B9D.PUMPSWAP_PROGRAM:
            B9D.load_pinned_idl(B9D.PUMPSWAP_IDL_PATH, B9D.PUMPSWAP_IDL_SHA256, B9D.PUMPSWAP_PROGRAM)}
        rpc = ReplayRPC(args.rpc_evidence) if args.rpc_evidence else EvidenceRPC(args.out)
        transactions, blocks, rows, failures = {}, {}, [], []
        for observation in observations:
            signature, slot = observation["signature"], observation["slot"]
            try:
                if signature not in transactions:
                    transactions[signature] = rpc.call("getTransaction", [signature,
                        {"encoding": "base64", "commitment": "finalized", "maxSupportedTransactionVersion": 0}])
                if slot not in blocks:
                    blocks[slot] = rpc.call("getBlock", [slot, {"transactionDetails": "signatures",
                        "rewards": False, "commitment": "finalized", "maxSupportedTransactionVersion": 0}])
                rows.append(reconcile_one(observation, transactions[signature], blocks[slot], idls))
            except Exception as error:
                failures.append({"signature": signature, "frame_sequence": observation["frame_sequence"],
                                 "error": type(error).__name__ + ": " + str(error)})
                # A provider failure is not a token failure; preserve partial work, do not hammer RPC.
                break
            if args.rpc:
                time.sleep(0.3)
        report["reconciliation"] = {"rows": rows, "failures": failures,
            "observations": len(observations), "completed": len(rows),
            "unattempted_after_failure": len(observations) - len(rows) - len(failures),
            "status": "ALL_OBSERVED_MATCHED" if len(rows) == len(observations) and rows else "INCOMPLETE",
            "rpc_evidence_source": str(args.rpc_evidence or args.out),
            "independent_provider": False, "unobserved_creation_recall": "UNMEASURED",
            "program_deployment_boundary": "NOT_ATTESTED; exact payload compatibility only"}
    write_new(args.out / "result.json", report)
    print(json.dumps({"output": str(args.out), "raw_replay": report["raw_replay"], "frames": report["frames"],
        "creates": report["creates"], "reconciliation": report.get("reconciliation", {}).get("status", "NOT_REQUESTED"),
        "status": "NO_TRADE"}), flush=True)


if __name__ == "__main__":
    main()
