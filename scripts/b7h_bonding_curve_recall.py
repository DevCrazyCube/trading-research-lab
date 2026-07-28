#!/usr/bin/env python3
"""Cross-check bonding-curve-history TradeEvent recall against exact block decoding.

The reference is every successful Pump TradeEvent for fixed cohort mints in a half-open block
window. Progress is resumable in SQLite. SOLANA_RPC_URL is read only from the environment.
"""
import argparse
import base64
import concurrent.futures as cf
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

try:
    import b7d_create_enumerator as b7d
except ModuleNotFoundError:
    from scripts import b7d_create_enumerator as b7d


def load_decoder(idl_path):
    raw = open(idl_path, "rb").read()
    idl = json.loads(raw)
    types = {item["name"]: item for item in idl["types"]}
    disc = hashlib.sha256(b"event:TradeEvent").digest()[:8]
    return types, types["TradeEvent"], disc, hashlib.sha256(raw).hexdigest()


def extract_trade_events(slot, block, cohort, types, trade_type, trade_disc):
    rows, errors = [], []
    for tx_index, transaction in enumerate(block.get("transactions", [])):
        meta = transaction.get("meta") or {}
        if meta.get("err") is not None:
            continue
        signature = transaction["transaction"]["signatures"][0]
        for group in meta.get("innerInstructions") or []:
            outer = group["index"]
            for inner, instruction in enumerate(group.get("instructions", [])):
                if instruction.get("programId") != b7d.PUMP or not instruction.get("data"):
                    continue
                encoded = b7d.b58decode(instruction["data"])
                if (len(encoded) < 16 or encoded[:8] != b7d.EVENT_TAG
                        or encoded[8:16] != trade_disc):
                    continue
                payload = encoded[8:]
                try:
                    cursor = b7d.Cursor(payload[8:])
                    fields = b7d.read_struct(cursor, trade_type, types)
                    if cursor.remaining:
                        raise ValueError(f"{cursor.remaining} trailing bytes")
                    if fields["mint"] in cohort:
                        rows.append((signature, fields["mint"], slot, tx_index, outer, inner,
                                     base64.b64encode(payload).decode()))
                except Exception as error:  # noqa: BLE001
                    errors.append((slot, signature, outer, inner,
                                   f"{type(error).__name__}: {error}"))
    return rows, errors


RATE_LIMIT_PREFIX = "RATE_LIMIT"


def is_rate_limited(error_text):
    """True when a slot_scan error row was caused by provider throttling, not by chain data."""
    return bool(error_text) and str(error_text).startswith(RATE_LIMIT_PREFIX)


def rpc_block_batch(url, slots, retries):
    """Fetch several independent getBlock calls in one JSON-RPC HTTP round trip.

    Provider throttling (HTTP 403/429) is NOT retried here. Retrying a throttle burns quota and
    was measured to make things worse: a prior run drove 403s from 60 to 148 while advancing
    exactly one slot. Throttles are surfaced to the scheduler, which stops the run cleanly.
    """
    requests = [{"jsonrpc": "2.0", "id": slot, "method": "getBlock", "params": [slot, {
        "encoding": "jsonParsed", "transactionDetails": "full", "rewards": False,
        "maxSupportedTransactionVersion": 0}]} for slot in slots]
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, data=json.dumps(requests).encode(),
                                             headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read())
            if not isinstance(payload, list):
                raise ValueError("batch RPC response is not a list")
            by_id = {item.get("id"): item for item in payload}
            results = []
            for slot in slots:
                item = by_id.get(slot)
                if not item:
                    results.append((slot, "error", None, "missing batch response"))
                elif "error" not in item and item.get("result") is not None:
                    results.append((slot, "retrieved", item["result"], None))
                elif "error" not in item:
                    results.append((slot, "skipped", None, "null result"))
                elif item["error"].get("code") in (-32007, -32009):
                    error = item["error"]
                    results.append((slot, "skipped", None,
                                    f"{error.get('code')}: {error.get('message')}"))
                else:
                    error = item["error"]
                    results.append((slot, "error", None,
                                    f"{error.get('code')}: {error.get('message')}"))
            return results
        except urllib.error.HTTPError as error:
            if error.code in (403, 429):
                text = f"{RATE_LIMIT_PREFIX} HTTP {error.code}"
                return [(slot, "error", None, text) for slot in slots]
            last_error = f"HTTPError {error.code}"
            if attempt + 1 < retries:
                time.sleep(min(0.5 * 2 ** attempt, 8))
        except Exception as error:  # noqa: BLE001
            last_error = f"{type(error).__name__}: {error}"
            if attempt + 1 < retries:
                time.sleep(min(0.5 * 2 ** attempt, 8))
    return [(slot, "error", None, last_error or "unknown batch RPC failure") for slot in slots]


def scan_batches(batches, workers, max_inflight, retries, rate_limit_stop, consume,
                 fetcher=rpc_block_batch, url=None, progress=None):
    """Bounded in-flight scheduler.

    At most `max_inflight` requests exist at any moment and completed futures are consumed as
    soon as they finish, rather than in submission order. The previous version submitted every
    batch up front and then read futures in order, so finished work was pinned waiting on earlier
    slots and a throttle storm could not be noticed until the whole run drained.

    Returns (completed, stop_reason). `stop_reason` is non-None when the run halted early because
    the provider was throttling; the caller must then refuse to draw a conclusion.
    """
    if workers < 1:
        raise ValueError("workers must be >= 1")
    if max_inflight < workers:
        raise ValueError(
            f"max_inflight ({max_inflight}) must be >= workers ({workers}); a smaller bound "
            f"cannot keep the pool fed and previously would have been silently raised")
    queue = list(batches)
    completed = 0
    consecutive = 0
    stop_reason = None
    with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        inflight = set()
        while (queue or inflight) and stop_reason is None:
            while queue and len(inflight) < max_inflight and stop_reason is None:
                inflight.add(executor.submit(fetcher, url, queue.pop(0), retries))
            if not inflight:
                break
            done, inflight = cf.wait(inflight, return_when=cf.FIRST_COMPLETED)
            for future in done:
                for result in future.result():
                    consume(result)
                    completed += 1
                    consecutive = consecutive + 1 if is_rate_limited(result[3]) else 0
                if consecutive >= rate_limit_stop:
                    stop_reason = (f"stopped after {consecutive} consecutive rate-limited "
                                   f"responses; quota or backoff needed")
            if progress:
                progress(completed)
        for future in inflight:
            future.cancel()
    return completed, stop_reason


def connect(path):
    db = sqlite3.connect(path)
    db.executescript("""
        PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS slot_scan(
          slot INTEGER PRIMARY KEY,status TEXT NOT NULL,error TEXT,scanned_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS block_event(
          signature TEXT NOT NULL,mint TEXT NOT NULL,slot INTEGER NOT NULL,
          transaction_index INTEGER NOT NULL,outer_instruction_index INTEGER NOT NULL,
          inner_instruction_index INTEGER NOT NULL,event_payload_base64 TEXT NOT NULL,
          PRIMARY KEY(signature,outer_instruction_index,inner_instruction_index));
        CREATE TABLE IF NOT EXISTS decode_error(
          slot INTEGER,signature TEXT,outer_instruction_index INTEGER,
          inner_instruction_index INTEGER,error TEXT NOT NULL);
    """)
    return db


def initialize(db, start, end, idl_hash, lifecycle_path):
    expected = {"start_slot": str(start), "end_slot": str(end), "idl_sha256": idl_hash,
                "lifecycle_database": os.path.abspath(lifecycle_path)}
    present = dict(db.execute("SELECT key,value FROM metadata"))
    if present and present != expected:
        raise RuntimeError("recall database metadata mismatch")
    with db:
        if not present:
            db.executemany("INSERT INTO metadata VALUES (?,?)", expected.items())
        db.executemany("INSERT OR IGNORE INTO slot_scan VALUES (?,'pending',NULL,?)",
                       ((slot, time.time()) for slot in range(start, end)))


def store_result(db, result, cohort, types, trade_type, trade_disc):
    slot, status, block, error = result
    with db:
        db.execute("DELETE FROM block_event WHERE slot=?", (slot,))
        db.execute("DELETE FROM decode_error WHERE slot=?", (slot,))
        if status == "retrieved":
            rows, errors = extract_trade_events(slot, block, cohort, types, trade_type, trade_disc)
            db.executemany("INSERT INTO block_event VALUES (?,?,?,?,?,?,?)", rows)
            db.executemany("INSERT INTO decode_error VALUES (?,?,?,?,?)", errors)
            status = "decode_error" if errors else "retrieved"
            error = "; ".join(row[-1] for row in errors) if errors else None
        db.execute("UPDATE slot_scan SET status=?,error=?,scanned_at=? WHERE slot=?",
                   (status, error, time.time(), slot))


def reconcile_skips(db, url, start, end, retries):
    produced, error = b7d.rpc_produced_slots(url, start, end - 1, retries)
    if error:
        raise RuntimeError(f"getBlocks reconciliation failed: {error}")
    with db:
        for slot, status in db.execute("SELECT slot,status FROM slot_scan"):
            if status == "skipped" and slot in produced:
                db.execute("UPDATE slot_scan SET status='error',error=? WHERE slot=?",
                           ("getBlocks lists produced slot", slot))
            elif status == "skipped":
                db.execute("UPDATE slot_scan SET status='verified_skipped' WHERE slot=?", (slot,))


def compare(db, lifecycle_path, start, end):
    source = sqlite3.connect(lifecycle_path)
    block_rows = set(db.execute("""SELECT signature,mint,outer_instruction_index,
        inner_instruction_index,event_payload_base64 FROM block_event"""))
    history_rows = set(source.execute("""SELECT signature,mint,outer_instruction_index,
        inner_instruction_index,event_payload_base64 FROM lifecycle_event
        WHERE event_name='TradeEvent' AND slot>=? AND slot<?""", (start, end)))
    source.close()
    return block_rows, history_rows, block_rows - history_rows, history_rows - block_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-slot", type=int, required=True)
    parser.add_argument("--end-slot", type=int, required=True)
    parser.add_argument("--lifecycle-database", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--idl", default="research/pump_idl_9c82f61.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=1,
                        help="getBlock calls per JSON-RPC request. Default 1. Values >1\n                             pack multi-megabyte blocks into one response and were\n                             measured to return HTTP 413; requires --allow-unsafe-batch.")
    parser.add_argument("--allow-unsafe-batch", action="store_true",
                        help="permit --batch-size >1 despite the measured 413 risk")
    parser.add_argument("--retries", type=int, default=7)
    parser.add_argument("--max-inflight", type=int, default=8)
    parser.add_argument("--rate-limit-stop", type=int, default=25)
    args = parser.parse_args()
    if args.batch_size > 1 and not args.allow_unsafe_batch:
        parser.error(
            f"unsafe batch size {args.batch_size}: multi-block JSON-RPC responses measured "
            f"HTTP 413 on this provider (1,187 slots failed that way). Use --batch-size 1, "
            f"or pass --allow-unsafe-batch to override deliberately.")
    if args.end_slot <= args.start_slot:
        parser.error("end slot must exceed start slot")
    types, trade_type, trade_disc, idl_hash = load_decoder(args.idl)
    source = sqlite3.connect(args.lifecycle_database)
    cohort = {row[0] for row in source.execute("SELECT mint FROM member")}
    source.close()
    url = os.environ.get("SOLANA_RPC_URL", b7d.DEFAULT_RPC)
    db = connect(args.database)
    initialize(db, args.start_slot, args.end_slot, idl_hash, args.lifecycle_database)
    pending = [row[0] for row in db.execute(
        "SELECT slot FROM slot_scan WHERE status IN ('pending','error') ORDER BY slot")]
    batches = [pending[index:index + args.batch_size]
               for index in range(0, len(pending), args.batch_size)]
    def consume(result):
        store_result(db, result, cohort, types, trade_type, trade_disc)
        db.commit()          # durable per slot: a kill loses at most one slot

    def progress(done):
        if done % 100 == 0:
            print(f"blocks {done}/{len(pending)}", flush=True)

    completed, stop_reason = scan_batches(
        batches, args.workers, args.max_inflight, args.retries, args.rate_limit_stop,
        consume, url=url, progress=progress)
    print(f"blocks {completed}/{len(pending)}", flush=True)
    if stop_reason:
        # Fail visibly. A partial scan must never be reported as if it were complete.
        remaining = db.execute("SELECT COUNT(*) FROM slot_scan WHERE status IN "
                               "('pending','error')").fetchone()[0]
        print(json.dumps({"stopped_early": True, "reason": stop_reason,
                          "slots_processed_this_run": completed,
                          "slots": dict(db.execute(
                              "SELECT status,COUNT(*) FROM slot_scan GROUP BY status")),
                          "still_unresolved": remaining,
                          "recall_conclusion": "NOT DRAWN - window incomplete"},
                         sort_keys=True), flush=True)
        db.close()
        return 2
    reconcile_skips(db, url, args.start_slot, args.end_slot, args.retries)
    bad = db.execute("SELECT status,COUNT(*) FROM slot_scan WHERE status NOT IN "
                     "('retrieved','verified_skipped') GROUP BY status").fetchall()
    decode_errors = db.execute("SELECT COUNT(*) FROM decode_error").fetchone()[0]
    block_rows, history_rows, missing, extra = compare(
        db, args.lifecycle_database, args.start_slot, args.end_slot)
    print(json.dumps({"slots": dict(db.execute(
        "SELECT status,COUNT(*) FROM slot_scan GROUP BY status")),
        "block_events": len(block_rows), "history_events": len(history_rows),
        "missing_from_history": len(missing), "extra_in_history": len(extra),
        "decode_errors": decode_errors}, sort_keys=True))
    db.close()
    if bad or decode_errors or not block_rows or missing or extra:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
