#!/usr/bin/env python3
"""B6-lite raw capture recorder - implements docs/schema/RAW_CAPTURE_SPEC.md v0.3.

The polling adapter reconstructs filtered block JSON because JSON-RPC has no equivalent
server-side Pump transaction filter. Those payloads are therefore explicitly marked
`b6-lite-normalized-v1`; they validate recorder mechanics but are not byte-identical provider
frames. A Geyser adapter must store the received protobuf bytes unchanged.

Source is polling `getBlock` on a public RPC. Per agent_discussion.md Seq 18 this validates
framing, sessions, gaps, crash recovery, clock samples, compression and duty cycle. It
CANNOT provide provider sequence numbers, heartbeats, commitment transitions, latency, or
dead-slot notifications; those remain Geyser-phase gates.

Read-only against the network. No keys, no signing, no transactions.

  run    : recorder.py run --root DIR [--duration SEC] [--simulate-crash-after N]
  report : recorder.py report --root DIR
"""
import argparse
import base64
import binascii
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
import urllib.request
import zlib

SPEC_VERSION = "0.3"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
SEGMENT_ROLL_BYTES = 64 * 1024 * 1024

# ---------------------------------------------------------------- CRC32C (Castagnoli)
_CRC32C_POLY = 0x82F63B78
_CRC32C_TABLE = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ (_CRC32C_POLY if _c & 1 else 0)
    _CRC32C_TABLE.append(_c)


def crc32c(data: bytes, crc: int = 0) -> int:
    crc ^= 0xFFFFFFFF
    for b in data:
        crc = (crc >> 8) ^ _CRC32C_TABLE[(crc ^ b) & 0xFF]
    return crc ^ 0xFFFFFFFF


# ---------------------------------------------------------------- small helpers
def now_wall_ns() -> int:
    return time.time_ns()


def now_mono_ns() -> int:
    return time.monotonic_ns()


def ulid() -> str:
    """Return a 26-character Crockford-base32 ULID (48-bit ms time + 80-bit randomness)."""
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    value = ((time.time_ns() // 1_000_000) << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        value, remainder = divmod(value, 32)
        chars.append(alphabet[remainder])
    return "".join(reversed(chars))


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def append_jsonl(path, obj):
    """Append one record and fsync. meta/ rows are not rebuildable, so they are durable."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "ab") as f:
        f.write(json.dumps(obj, separators=(",", ":")).encode() + b"\n")
        f.flush()
        os.fsync(f.fileno())


def clock_sample(root, recorder_id, clock_domain_id):
    state, offset = "unknown", None
    try:
        out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            state = "synchronized" if out.stdout.strip() == "yes" else "unsynchronized"
    except Exception:  # noqa: BLE001 - absence of the tool is itself 'unknown', never fatal
        pass
    append_jsonl(f"{root}/meta/clock_samples.jsonl", {
        "recorder_id": recorder_id, "clock_domain_id": clock_domain_id,
        "sampled_at_wall_ns": now_wall_ns(), "sampled_at_mono_ns": now_mono_ns(),
        "sync_state": state, "est_offset_ns": offset, "est_error_ns": None,
        "source": "os_report",
    })
    return state


# ---------------------------------------------------------------- segment writer
class SegmentWriter:
    """Append-only CRC-framed segments. Sealed segments get a fsynced .sha256 sidecar.

    Record layout (little-endian), per spec v0.2:
        u32 record_len | u32 header_len | u64 seq_in_session | u32 crc32c
        header_json (header_len) | payload (record_len)
    """
    HDR = struct.Struct("<IIQI")

    def __init__(self, root, recorder_id, session_id):
        self.dir = f"{root}/segments/{recorder_id}/{session_id}"
        os.makedirs(self.dir, exist_ok=True)
        self.f = None
        self.path = None
        self.seq_lo = None
        self.written = 0

    def _open(self, seq):
        self.seq_lo = seq
        self.path = f"{self.dir}/{seq:012d}-open.seg"
        self.f = open(self.path, "ab")
        self.written = 0

    def write(self, seq, header: dict, payload: bytes):
        if self.f is None:
            self._open(seq)
        hj = json.dumps(header, separators=(",", ":")).encode()
        crc = crc32c(hj + payload)
        rec = self.HDR.pack(len(payload), len(hj), seq, crc) + hj + payload
        self.f.write(rec)
        self.written += len(rec)
        if self.written >= SEGMENT_ROLL_BYTES:
            self.seal(seq)

    def seal(self, seq_hi):
        if self.f is None:
            return None
        self.f.flush()
        os.fsync(self.f.fileno())
        self.f.close()
        final = f"{self.dir}/{self.seq_lo:012d}-{seq_hi:012d}.seg"
        os.rename(self.path, final)
        h = hashlib.sha256()
        with open(final, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        with open(final + ".sha256", "w") as fh:
            fh.write(h.hexdigest() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        fsync_dir(self.dir)
        self.f = None
        self.path = None
        return final


def scan_segment(path):
    """Return (valid_record_count, valid_byte_length, last_seq). Stops at first bad record."""
    n, off, last = 0, 0, None
    with open(path, "rb") as handle:
        data = handle.read()
    while off + SegmentWriter.HDR.size <= len(data):
        rl, hl, seq, crc = SegmentWriter.HDR.unpack_from(data, off)
        end = off + SegmentWriter.HDR.size + hl + rl
        if end > len(data):
            break                                   # torn tail
        body = data[off + SegmentWriter.HDR.size:end]
        if crc32c(body) != crc:
            break                                   # corrupt record
        n += 1
        last = seq
        off = end
    return n, off, last


# ---------------------------------------------------------------- crash recovery (I3)
def recover(root):
    """Any session opened without a close is a crash: truncate, seal, close, emit a gap."""
    sess_path = f"{root}/meta/sessions.jsonl"
    if not os.path.exists(sess_path):
        return []
    opened, closed = {}, set()
    with open(sess_path, encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            if r["event"] == "open":
                opened[r["session_id"]] = r
            else:
                closed.add(r["session_id"])
    recovered = []
    for sid, rec in opened.items():
        if sid in closed:
            continue
        sdir = f"{root}/segments/{rec['recorder_id']}/{sid}"
        last_seq, truncated = None, 0
        if os.path.isdir(sdir):
            for name in sorted(os.listdir(sdir)):
                if not name.endswith("-open.seg"):
                    continue
                p = f"{sdir}/{name}"
                cnt, good_len, last_seq = scan_segment(p)
                full = os.path.getsize(p)
                truncated = full - good_len
                if truncated:
                    with open(p, "r+b") as f:
                        f.truncate(good_len)
                        f.flush()
                        os.fsync(f.fileno())
                sw = SegmentWriter(root, rec["recorder_id"], sid)
                sw.f = open(p, "ab")
                sw.path = p
                sw.seq_lo = int(name.split("-")[0])
                sw.seal(last_seq if last_seq is not None else sw.seq_lo)
        append_jsonl(sess_path, {
            "event": "close", "session_id": sid, "recorder_id": rec["recorder_id"],
            "closed_at_wall_ns": now_wall_ns(), "closed_at_mono_ns": None,
            "close_reason": "crash", "frames_received": None,
            "recovered_last_seq": last_seq, "truncated_bytes": truncated,
        })
        # I3: recovery MUST emit a gap. Silent truncation would leave a file that
        # looks complete and is not.
        append_jsonl(f"{root}/meta/gaps.jsonl", {
            "gap_id": ulid(), "session_id": sid, "detected_by": "crash_recovery",
            "first_missing_hint": last_seq + 1 if last_seq is not None else None,
            "last_missing_hint": None,
            "detected_at_wall_ns": now_wall_ns(),
            "note": f"unclean shutdown; truncated {truncated} torn bytes",
        })
        recovered.append((sid, last_seq, truncated))
    return recovered


# ---------------------------------------------------------------- RPC
def rpc(url, method, params, retries=4):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
            o = json.loads(raw)
            if "error" in o:
                if a < retries - 1:
                    time.sleep(1.5 * (a + 1))
                    continue
                return None, o["error"]
            return o["result"], None
        except Exception as e:  # noqa: BLE001
            if a == retries - 1:
                return None, str(e)
            time.sleep(1.5 * (a + 1))
    return None, "retries exhausted"


def touches_pump(tx):
    msg = tx.get("transaction", {}).get("message", {})
    for ix in msg.get("instructions", []):
        if ix.get("programId") == PUMP:
            return True
    for g in (tx.get("meta") or {}).get("innerInstructions") or []:
        for ix in g.get("instructions", []):
            if ix.get("programId") == PUMP:
                return True
    return False


# ---------------------------------------------------------------- run
def run(args):
    root = args.root
    os.makedirs(f"{root}/meta", exist_ok=True)
    os.makedirs(f"{root}/index", exist_ok=True)

    for sid, last, trunc in recover(root):
        print(f"[recovery] session {sid[:12]}: sealed at seq {last}, truncated {trunc} torn bytes, gap recorded")

    recorder_id, session_id, clock_domain_id = ulid(), ulid(), ulid()
    endpoint_ref = "public-mainnet" if args.rpc == DEFAULT_RPC else "configured-rpc"
    sub_spec = {"source": "rpc_poll_getblock", "endpoint_ref": endpoint_ref,
                "program_filter": [PUMP],
                "encoding": "jsonParsed", "commitment": "finalized",
                "transactionDetails": "full", "spec_version": SPEC_VERSION}
    spec_hash = hashlib.sha256(json.dumps(sub_spec, sort_keys=True).encode()).hexdigest()

    append_jsonl(f"{root}/meta/sessions.jsonl", {
        "event": "open", "session_id": session_id, "recorder_id": recorder_id,
        "provider_kind": "rpc_http", "endpoint_ref": endpoint_ref,  # opaque; never a credential
        "subscription_spec": sub_spec, "subscription_spec_sha256": spec_hash,
        "opened_at_wall_ns": now_wall_ns(), "opened_at_mono_ns": now_mono_ns(),
        "spec_version": SPEC_VERSION,
    })
    clock_sample(root, recorder_id, clock_domain_id)

    seg = SegmentWriter(root, recorder_id, session_id)
    seq = 0
    frames = 0
    last_slot = None
    started = time.monotonic()
    close_reason = "clean"
    stats = {"blocks": 0, "skipped": 0, "errors": 0, "pump_txs": 0, "payload_bytes": 0}

    print(f"[run] root={root} session={session_id[:12]} duration={args.duration}s")
    try:
        while time.monotonic() - started < args.duration:
            tip, err = rpc(args.rpc, "getSlot", [{"commitment": "finalized"}])
            if err or tip is None:
                stats["errors"] += 1
                append_jsonl(f"{root}/meta/gaps.jsonl", {
                    "gap_id": ulid(), "session_id": session_id, "detected_by": "session_down",
                    "first_missing_hint": last_slot + 1 if last_slot is not None else None,
                    "last_missing_hint": None,
                    "detected_at_wall_ns": now_wall_ns(), "note": f"getSlot failed: {err}"})
                time.sleep(2)
                continue

            if last_slot is None:
                last_slot = tip - 1
            # Falling behind is real data loss and must be recorded, not hidden.
            if tip - last_slot > args.max_lag:
                append_jsonl(f"{root}/meta/gaps.jsonl", {
                    "gap_id": ulid(), "session_id": session_id, "detected_by": "slot_discontinuity",
                    "first_missing_hint": last_slot + 1,
                    "last_missing_hint": tip - args.max_lag,
                    "detected_at_wall_ns": now_wall_ns(),
                    "note": "poller could not keep up with chain tip"})
                last_slot = tip - args.max_lag

            for slot in range(last_slot + 1, tip + 1):
                if time.monotonic() - started >= args.duration:
                    break
                t0 = now_mono_ns()
                blk, err = rpc(args.rpc, "getBlock", [slot, {
                    "encoding": "jsonParsed", "transactionDetails": "full",
                    "rewards": False, "maxSupportedTransactionVersion": 0}])
                recv_mono, recv_wall = now_mono_ns(), now_wall_ns()

                if err is not None:
                    kind, status = ("error", "dead_or_skipped") if "skipped" in str(err).lower() \
                        else ("error", None)
                    if status:
                        stats["skipped"] += 1
                    else:
                        stats["errors"] += 1
                    payload = json.dumps({"slot": slot, "rpc_error": err},
                                         separators=(",", ":")).encode()
                    header = {"recorder_id": recorder_id, "session_id": session_id,
                              "seq_in_session": seq, "provider_seq": None,
                              "provider_message_id": None,
                              "received_at_mono_ns": recv_mono, "received_at_wall_ns": recv_wall,
                              "payload_encoding": "json",
                              "payload_schema_version": "b6-lite-normalized-v1",
                              "provider_kind": "rpc_http", "subscription_id": spec_hash[:16]}
                    seg.write(seq, header, payload)
                    append_jsonl(f"{root}/index/frame_index.jsonl", {
                        "recorder_id": recorder_id, "session_id": session_id,
                        "seq_in_session": seq, "message_kind": kind, "slot": slot,
                        "commitment": "finalized", "signature": None})
                    if status:
                        append_jsonl(f"{root}/index/slot_observation.jsonl", {
                            "recorder_id": recorder_id, "session_id": session_id,
                            "seq_in_session": seq, "slot": slot, "parent_slot": None,
                            "status": status, "observed_at_mono_ns": recv_mono,
                            "observed_at_wall_ns": recv_wall})
                    seq += 1
                    frames += 1
                    last_slot = slot
                    continue

                if blk is None:
                    last_slot = slot
                    continue

                # Subscription filter (structural, not semantic): keep Pump-touching txs.
                txs = [t for t in blk.get("transactions", []) if touches_pump(t)]
                payload = json.dumps({
                    "slot": slot, "parent_slot": blk.get("parentSlot"),
                    "blockhash": blk.get("blockhash"), "block_time": blk.get("blockTime"),
                    "transactions": txs}, separators=(",", ":")).encode()

                header = {"recorder_id": recorder_id, "session_id": session_id,
                          "seq_in_session": seq, "provider_seq": None,
                          "provider_message_id": None,
                          "received_at_mono_ns": recv_mono, "received_at_wall_ns": recv_wall,
                          "fetch_duration_ns": recv_mono - t0,
                          "payload_encoding": "json",
                          "payload_schema_version": "b6-lite-normalized-v1",
                          "provider_kind": "rpc_http", "subscription_id": spec_hash[:16]}
                seg.write(seq, header, payload)

                append_jsonl(f"{root}/index/frame_index.jsonl", {
                    "recorder_id": recorder_id, "session_id": session_id,
                    "seq_in_session": seq, "message_kind": "block_meta", "slot": slot,
                    "commitment": "finalized", "signature": None})
                append_jsonl(f"{root}/index/slot_observation.jsonl", {
                    "recorder_id": recorder_id, "session_id": session_id,
                    "seq_in_session": seq, "slot": slot,
                    "parent_slot": blk.get("parentSlot"), "status": "finalized",
                    "observed_at_mono_ns": recv_mono, "observed_at_wall_ns": recv_wall})

                stats["blocks"] += 1
                stats["pump_txs"] += len(txs)
                stats["payload_bytes"] += len(payload)
                seq += 1
                frames += 1
                last_slot = slot

                if args.simulate_crash_after and frames >= args.simulate_crash_after:
                    # Hard kill: no seal, no close record, deliberately torn tail.
                    seg.f.write(b"\xde\xad\xbe\xef")
                    seg.f.flush()
                    print(f"[crash-test] hard exit after {frames} frames, torn tail written")
                    os._exit(9)

            clock_sample(root, recorder_id, clock_domain_id)
    except KeyboardInterrupt:
        close_reason = "recorder_shutdown"

    seg.seal(max(seq - 1, 0))
    append_jsonl(f"{root}/meta/sessions.jsonl", {
        "event": "close", "session_id": session_id, "recorder_id": recorder_id,
        "closed_at_wall_ns": now_wall_ns(), "closed_at_mono_ns": now_mono_ns(),
        "close_reason": close_reason, "frames_received": frames})

    el = time.monotonic() - started
    print(f"\n[done] {frames} frames in {el:.0f}s | blocks={stats['blocks']} "
          f"skipped={stats['skipped']} errors={stats['errors']} pump_txs={stats['pump_txs']}")
    if stats["blocks"]:
        print(f"       payload {stats['payload_bytes'] / 1024 / stats['blocks']:.1f} KB/block, "
              f"{stats['blocks'] / el:.2f} blocks/s captured vs ~2.5 slots/s produced")
    return 0


# ---------------------------------------------------------------- report
def report(args):
    root = args.root
    print(f"=== capture report: {root} ===\n")
    segs, raw_total = [], 0
    segdir = f"{root}/segments"
    for dirpath, _, files in os.walk(segdir):
        for name in sorted(files):
            if not name.endswith(".seg"):
                continue
            p = os.path.join(dirpath, name)
            size = os.path.getsize(p)
            raw_total += size
            cnt, good, last = scan_segment(p)
            sealed = os.path.exists(p + ".sha256")
            integrity = "n/a"
            if sealed:
                h = hashlib.sha256()
                with open(p, "rb") as fh:
                    for c in iter(lambda: fh.read(1 << 20), b""):
                        h.update(c)
                integrity = "OK" if h.hexdigest() == open(p + ".sha256").read().strip() else "MISMATCH"
            segs.append((p, size, cnt, good == size, sealed, integrity))
            print(f"  {name}  {size/1024/1024:7.2f} MB  {cnt:5d} records  "
                  f"{'clean' if good == size else 'TORN TAIL'}  "
                  f"{'sealed' if sealed else 'ACTIVE'}  sha256={integrity}")

    for label, path in (("sessions", "meta/sessions.jsonl"), ("gaps", "meta/gaps.jsonl"),
                        ("clock samples", "meta/clock_samples.jsonl"),
                        ("frame_index", "index/frame_index.jsonl"),
                        ("slot_observation", "index/slot_observation.jsonl")):
        p = f"{root}/{path}"
        n = sum(1 for _ in open(p)) if os.path.exists(p) else 0
        print(f"\n{label:18} {n} rows")
        if label == "gaps" and n:
            for line in open(p):
                r = json.loads(line)
                print(f"    {r['detected_by']:<20} {r.get('note', '')}")

    if raw_total:
        blob = b"".join(open(p, "rb").read() for p, *_ in segs)
        for lvl, name in ((6, "zlib-6"), (9, "zlib-9")):
            c = len(zlib.compress(blob, lvl))
            print(f"\ncompression {name}: {raw_total/1024/1024:.2f} MB -> {c/1024/1024:.2f} MB "
                  f"({raw_total/c:.2f}x)")
        try:
            import lzma
            c = len(lzma.compress(blob, preset=1))
            print(f"compression lzma-1 : {raw_total/1024/1024:.2f} MB -> {c/1024/1024:.2f} MB "
                  f"({raw_total/c:.2f}x)")
        except Exception:  # noqa: BLE001
            pass
    return 0


# ---------------------------------------------------------------- logsSubscribe adapter
DEFAULT_WS = "wss://api.mainnet-beta.solana.com"


def run_logs(args):
    """Capture `logsSubscribe`, storing WebSocket application payloads byte-identically.

    Unlike the polling adapter — whose payloads are reconstructed and are therefore labelled
    `b6-lite-normalized-v1` — every byte written here is exactly what the server sent. This
    RFC 6455 framing/control bytes are consumed by ``wsmin`` and are not stored.

    Reconnects are gaps: a dropped socket means unobserved traffic, and per spec v0.2 that is
    recorded, never inferred away.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from wsmin import WebSocket, WSError  # noqa: PLC0415 - optional dependency-free client

    root = args.root
    os.makedirs(f"{root}/meta", exist_ok=True)
    os.makedirs(f"{root}/index", exist_ok=True)
    for sid, last, trunc in recover(root):
        print(f"[recovery] session {sid[:12]}: sealed at seq {last}, truncated {trunc}, gap recorded")

    recorder_id, clock_domain_id = ulid(), ulid()
    endpoint_ref = "public-mainnet-ws" if args.ws == DEFAULT_WS else "configured-ws"
    sub_spec = {"source": "ws_logs_subscribe", "endpoint_ref": endpoint_ref,
                "program_filter": [PUMP], "commitment": args.commitment,
                "payload_fidelity": "verbatim-websocket-message-payload", "spec_version": SPEC_VERSION}
    spec_hash = hashlib.sha256(json.dumps(sub_spec, sort_keys=True).encode()).hexdigest()

    started = time.monotonic()
    stats = {"notifications": 0, "events": 0, "event_txs": 0, "failed_tx": 0,
             "ok_tx": 0, "truncation_markers": 0, "reconnects": 0, "bytes": 0}
    te_disc = hashlib.sha256(b"event:TradeEvent").digest()[:8]
    print(f"[run-logs] root={root} commitment={args.commitment} duration={args.duration}s")

    while time.monotonic() - started < args.duration:
        session_id = ulid()
        seg = SegmentWriter(root, recorder_id, session_id)
        seq = 0
        close_reason = "clean"
        append_jsonl(f"{root}/meta/sessions.jsonl", {
            "event": "open", "session_id": session_id, "recorder_id": recorder_id,
            "provider_kind": "ws_json_rpc", "endpoint_ref": endpoint_ref,
            "subscription_spec": sub_spec, "subscription_spec_sha256": spec_hash,
            "opened_at_wall_ns": now_wall_ns(), "opened_at_mono_ns": now_mono_ns(),
            "spec_version": SPEC_VERSION})
        clock_sample(root, recorder_id, clock_domain_id)
        ws = None
        try:
            ws = WebSocket(args.ws, timeout=45)
            ws.send_text(json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                "params": [{"mentions": [PUMP]}, {"commitment": args.commitment}]}))
            while time.monotonic() - started < args.duration:
                kind, payload, code = ws.recv()
                recv_mono, recv_wall = now_mono_ns(), now_wall_ns()
                if kind == "close":
                    close_reason = "remote_close"
                    break
                stats["bytes"] += len(payload)

                # Persist the provider bytes UNCHANGED before any interpretation.
                header = {"recorder_id": recorder_id, "session_id": session_id,
                          "seq_in_session": seq, "provider_seq": None,
                          "provider_message_id": None,
                          "received_at_mono_ns": recv_mono, "received_at_wall_ns": recv_wall,
                          "payload_encoding": "json", "payload_schema_version": "unknown",
                          "provider_kind": "ws_json_rpc", "subscription_id": spec_hash[:16],
                          "payload_fidelity": "verbatim"}
                seg.write(seq, header, payload)

                message_kind, slot, signature = "unknown", None, None
                try:
                    msg = json.loads(payload)
                except Exception:  # noqa: BLE001 - unparseable frames are stored and counted
                    msg = None
                if msg is not None:
                    if msg.get("method") == "logsNotification":
                        message_kind = "transaction"
                        res = msg.get("params", {}).get("result", {})
                        slot = (res.get("context") or {}).get("slot")
                        val = res.get("value") or {}
                        signature = val.get("signature")
                        stats["notifications"] += 1
                        if val.get("err"):
                            stats["failed_tx"] += 1
                        else:
                            stats["ok_tx"] += 1
                        logs = val.get("logs") or []
                        # Truncation is an explicit marker. Per Codex Seq 28, a successful
                        # transaction with no TradeEvent is NOT truncation - it is ordinary
                        # non-trade traffic (cashback, accumulators, creator fees, migration).
                        if any("log truncated" in ln.lower() for ln in logs):
                            stats["truncation_markers"] += 1
                            append_jsonl(f"{root}/meta/gaps.jsonl", {
                                "gap_id": ulid(), "session_id": session_id,
                                "detected_by": "log_truncated",
                                "first_missing_hint": None, "last_missing_hint": None,
                                "detected_at_wall_ns": recv_wall,
                                "note": f"truncated logs for signature {signature}"})
                        n_ev = 0
                        for ln in logs:
                            if not ln.startswith("Program data:"):
                                continue
                            for field in ln.split("Program data:", 1)[1].split():
                                try:
                                    raw = base64.b64decode(field, validate=True)
                                except Exception:  # noqa: BLE001
                                    continue
                                if raw[:8] == te_disc:
                                    n_ev += 1
                        if n_ev:
                            stats["events"] += n_ev
                            stats["event_txs"] += 1
                    elif "result" in msg and msg.get("id") == 1:
                        message_kind = "unknown"  # subscription ack, not a heartbeat
                    elif "error" in msg:
                        message_kind = "error"
                        print(f"  server error: {msg['error']}")

                append_jsonl(f"{root}/index/frame_index.jsonl", {
                    "recorder_id": recorder_id, "session_id": session_id,
                    "seq_in_session": seq, "message_kind": message_kind, "slot": slot,
                    "commitment": args.commitment, "signature": signature})
                if slot is not None:
                    append_jsonl(f"{root}/index/slot_observation.jsonl", {
                        "recorder_id": recorder_id, "session_id": session_id,
                        "seq_in_session": seq, "slot": slot, "parent_slot": None,
                        "status": args.commitment, "observed_at_mono_ns": recv_mono,
                        "observed_at_wall_ns": recv_wall})
                seq += 1
        except KeyboardInterrupt:
            close_reason = "recorder_shutdown"
        except (WSError, OSError) as e:
            close_reason = "error"
            print(f"  stream error at seq {seq}: {e}")
        finally:
            if ws is not None:
                ws.close()
            seg.seal(max(seq - 1, 0))
            append_jsonl(f"{root}/meta/sessions.jsonl", {
                "event": "close", "session_id": session_id, "recorder_id": recorder_id,
                "closed_at_wall_ns": now_wall_ns(), "closed_at_mono_ns": now_mono_ns(),
                "close_reason": close_reason, "frames_received": seq})

        if close_reason == "recorder_shutdown" or time.monotonic() - started >= args.duration:
            break
        # A reconnect means traffic went unobserved. Record it; never infer it away.
        stats["reconnects"] += 1
        append_jsonl(f"{root}/meta/gaps.jsonl", {
            "gap_id": ulid(), "session_id": session_id, "detected_by": "session_down",
            "first_missing_hint": None, "last_missing_hint": None,
            "detected_at_wall_ns": now_wall_ns(),
            "note": f"disconnect ({close_reason}); reconnecting"})
        time.sleep(2)  # total reconnect count must not become permanent backoff state

    el = time.monotonic() - started
    n = stats["notifications"]
    print(f"\n[done] {el:.0f}s | {n} notifications ({n/max(el,1):.1f}/s) | "
          f"reconnects={stats['reconnects']}")
    print(f"  succeeded/failed : {stats['ok_tx']}/{stats['failed_tx']} "
          f"({100*stats['failed_tx']/max(n,1):.1f}% failed)")
    print(f"  TradeEvents      : {stats['events']} in {stats['event_txs']} event-bearing txs")
    if stats["ok_tx"]:
        print(f"  event-bearing tx coverage: {100*stats['event_txs']/stats['ok_tx']:.1f}% "
              f"of successful txs  (transaction units, not event units)")
    print(f"  truncation markers: {stats['truncation_markers']}")
    print(f"  bytes            : {stats['bytes']/1024/1024:.2f} MB "
          f"({stats['bytes']/max(el,1)*86400/1024**3:.1f} GB/day projected)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("run-logs")
    lg.add_argument("--root", required=True)
    lg.add_argument("--ws", default=DEFAULT_WS)
    lg.add_argument("--commitment", default="confirmed",
                    choices=["processed", "confirmed", "finalized"])
    lg.add_argument("--duration", type=float, default=120)
    lg.set_defaults(fn=run_logs)
    r = sub.add_parser("run")
    r.add_argument("--root", required=True)
    r.add_argument("--rpc", default=DEFAULT_RPC)
    r.add_argument("--duration", type=float, default=120)
    r.add_argument("--max-lag", type=int, default=20)
    r.add_argument("--simulate-crash-after", type=int, default=0)
    r.set_defaults(fn=run)
    p = sub.add_parser("report")
    p.add_argument("--root", required=True)
    p.set_defaults(fn=report)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
