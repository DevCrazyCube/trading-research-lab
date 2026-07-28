#!/usr/bin/env python3
"""Reconstruct exact Pump lifecycle events for every member of a B7d launch cohort.

Membership comes only from the launch database. Bonding-curve address histories are paginated
without filtering by outcome or affordability, bounded by an explicit per-member cap. Successful
transactions through the frozen observation cutoff are fetched, stored as compressed raw JSON,
and decoded against the pinned IDL. Partial/capped members remain visible and block cohort-level
conclusions.

RPC URL comes from SOLANA_RPC_URL only and is never persisted. Read-only.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import sqlite3
import tempfile
import time
import urllib.error
import urllib.request
import zlib

try:
    import b7d_create_enumerator as b7d
except ModuleNotFoundError:  # Imported as a repository module by tests.
    from scripts import b7d_create_enumerator as b7d

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
EVENT_NAMES = ("TradeEvent", "CompleteEvent", "CompletePumpAmmMigrationEvent")
SCHEMA_VERSION = "b7e-v1"


def rpc(url, method, params, retries=7):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read())
            if "error" not in result:
                return result.get("result"), None
            error = result["error"]
            last_error = f"{error.get('code')}: {error.get('message')}"
            if error.get("code") not in (-32005, -32429, 429):
                return None, last_error
        except urllib.error.HTTPError as error:
            last_error = f"HTTP {error.code}"
            if error.code != 429:
                return None, last_error
        except Exception as error:  # noqa: BLE001
            last_error = f"{type(error).__name__}: {error}"
        if attempt + 1 < retries:
            time.sleep(min(0.5 * 2 ** attempt, 8))
    return None, last_error or "unknown RPC failure"


def address_history(url, address, launch_slot, cutoff_slot, cap, retries):
    """Return rows within [launch_slot, cutoff_slot], status, and pages fetched."""
    rows, before, pages, examined = [], None, 0, 0
    while examined < cap:
        options = {"limit": min(1000, cap - examined), "commitment": "finalized"}
        if before:
            options["before"] = before
        page, error = rpc(url, "getSignaturesForAddress", [address, options], retries)
        if error:
            return rows, "rpc_error", pages, examined, error
        pages += 1
        if not page:
            return rows, "complete", pages, examined, None
        examined += len(page)
        for row in page:
            if launch_slot <= row["slot"] <= cutoff_slot:
                rows.append(row)
        if page[-1]["slot"] < launch_slot or len(page) < options["limit"]:
            return rows, "complete", pages, examined, None
        before = page[-1]["signature"]
    return rows, "capped", pages, examined, f"reached cap {cap} before launch slot"


def connect(path):
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS member (
            mint TEXT PRIMARY KEY, bonding_curve TEXT NOT NULL, launch_slot INTEGER NOT NULL,
            launch_transaction_index INTEGER NOT NULL, launch_block_time INTEGER,
            history_status TEXT NOT NULL DEFAULT 'pending', history_pages INTEGER,
            signatures_examined INTEGER, signatures_in_window INTEGER,
            history_error TEXT, history_updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS signature (
            signature TEXT PRIMARY KEY, mint TEXT NOT NULL, slot INTEGER NOT NULL,
            block_time INTEGER, chain_error_json TEXT, fetch_status TEXT NOT NULL,
            fetch_error TEXT, raw_transaction_zlib BLOB,
            FOREIGN KEY(mint) REFERENCES member(mint)
        );
        CREATE INDEX IF NOT EXISTS signature_member_slot ON signature(mint, slot);
        CREATE TABLE IF NOT EXISTS lifecycle_event (
            signature TEXT NOT NULL, mint TEXT NOT NULL, event_name TEXT NOT NULL,
            slot INTEGER NOT NULL, transaction_index INTEGER,
            outer_instruction_index INTEGER NOT NULL, inner_instruction_index INTEGER NOT NULL,
            event_ordinal INTEGER NOT NULL, fields_json TEXT NOT NULL,
            event_payload_base64 TEXT NOT NULL,
            PRIMARY KEY(signature, outer_instruction_index, inner_instruction_index, event_ordinal)
        );
        CREATE TABLE IF NOT EXISTS decode_error (
            signature TEXT PRIMARY KEY, mint TEXT NOT NULL, error TEXT NOT NULL
        );
    """)
    return connection


def initialize(connection, launch_db, cutoff_slot, idl_hash, endpoint_ref):
    launch_path = os.path.abspath(launch_db)
    expected = {
        "schema_version": SCHEMA_VERSION, "launch_database": launch_path,
        "observation_cutoff_slot": str(cutoff_slot), "idl_sha256": idl_hash,
        "endpoint_ref": endpoint_ref,
    }
    present = dict(connection.execute("SELECT key,value FROM metadata"))
    if present and any(present.get(key) != value for key, value in expected.items()):
        raise RuntimeError("lifecycle database metadata mismatch")
    if not present:
        connection.executemany("INSERT INTO metadata VALUES (?,?)", expected.items())
    source = sqlite3.connect(launch_db)
    launch_rows = source.execute("""
        SELECT mint, bonding_curve, slot, transaction_index, block_time
        FROM create_event ORDER BY slot, transaction_index,
             outer_instruction_index, inner_instruction_index
    """).fetchall()
    source.close()
    with connection:
        connection.executemany("""
            INSERT OR IGNORE INTO member(mint,bonding_curve,launch_slot,
                launch_transaction_index,launch_block_time) VALUES (?,?,?,?,?)
        """, launch_rows)
    return len(launch_rows)


def store_history(connection, mint, rows, status, pages, examined, error):
    with connection:
        for row in rows:
            fetch_status = "chain_failed" if row.get("err") is not None else "pending"
            connection.execute("""
                INSERT OR IGNORE INTO signature(signature,mint,slot,block_time,chain_error_json,
                                                 fetch_status)
                VALUES (?,?,?,?,?,?)
            """, (row["signature"], mint, row["slot"], row.get("blockTime"),
                  json.dumps(row.get("err"), separators=(",", ":")), fetch_status))
        connection.execute("""
            UPDATE member SET history_status=?,history_pages=?,signatures_examined=?,
                signatures_in_window=?,history_error=?,history_updated_at=? WHERE mint=?
        """, (status, pages, examined, len(rows), error, time.time(), mint))


def decode_transaction(raw_json, expected_mint, event_discs, event_types, types):
    transaction = json.loads(raw_json)
    meta = transaction.get("meta") or {}
    events, errors = [], []
    for group in meta.get("innerInstructions") or []:
        outer_index = group["index"]
        for inner_index, instruction in enumerate(group.get("instructions", [])):
            if instruction.get("programId") != b7d.PUMP or not instruction.get("data"):
                continue
            raw = b7d.b58decode(instruction["data"])
            if len(raw) < 16 or raw[:8] != b7d.EVENT_TAG:
                continue
            name = event_discs.get(raw[8:16])
            if not name:
                continue
            payload = raw[8:]
            cursor = b7d.Cursor(payload[8:])
            try:
                fields = b7d.read_struct(cursor, event_types[name], types)
                if cursor.remaining:
                    raise ValueError(f"{cursor.remaining} trailing bytes")
                if fields.get("mint") != expected_mint:
                    continue
                events.append((name, outer_index, inner_index, 0, fields,
                               __import__("base64").b64encode(payload).decode()))
            except Exception as error:  # noqa: BLE001
                errors.append(f"{name}@{outer_index}/{inner_index}: {type(error).__name__}: {error}")
    return events, errors


def fetch_transaction(url, signature, retries):
    result, error = rpc(url, "getTransaction", [signature, {
        "encoding": "jsonParsed", "commitment": "finalized",
        "maxSupportedTransactionVersion": 0,
    }], retries)
    if error or result is None:
        return signature, None, error or "null transaction"
    raw = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    return signature, raw, None


def store_transaction(connection, signature, raw, error, event_discs, event_types, types):
    mint, slot = connection.execute(
        "SELECT mint,slot FROM signature WHERE signature=?", (signature,)).fetchone()
    if error:
        with connection:
            connection.execute("UPDATE signature SET fetch_status='error',fetch_error=? WHERE signature=?",
                               (error, signature))
        return
    events, errors = decode_transaction(raw, mint, event_discs, event_types, types)
    with connection:
        connection.execute("DELETE FROM lifecycle_event WHERE signature=?", (signature,))
        connection.execute("DELETE FROM decode_error WHERE signature=?", (signature,))
        connection.execute("""
            UPDATE signature SET fetch_status=?,fetch_error=NULL,raw_transaction_zlib=?
            WHERE signature=?
        """, ("decode_error" if errors else "complete", zlib.compress(raw, 6), signature))
        for name, outer, inner, ordinal, fields, payload in events:
            connection.execute("INSERT INTO lifecycle_event VALUES (?,?,?,?,?,?,?,?,?,?)", (
                signature, mint, name, slot, None, outer, inner, ordinal,
                json.dumps(fields, sort_keys=True, separators=(",", ":")), payload))
        if errors:
            connection.execute("INSERT INTO decode_error VALUES (?,?,?)",
                               (signature, mint, "; ".join(errors)))


def export_summary(connection, path):
    summary = {
        "metadata": dict(connection.execute("SELECT key,value FROM metadata")),
        "members": dict(connection.execute(
            "SELECT history_status,COUNT(*) FROM member GROUP BY history_status")),
        "signatures": dict(connection.execute(
            "SELECT fetch_status,COUNT(*) FROM signature GROUP BY fetch_status")),
        "events": dict(connection.execute(
            "SELECT event_name,COUNT(*) FROM lifecycle_event GROUP BY event_name")),
        "decode_errors": connection.execute("SELECT COUNT(*) FROM decode_error").fetchone()[0],
    }
    destination = os.path.abspath(path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(destination), delete=False) as handle:
        json.dump(summary, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-database", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--cutoff-slot", type=int, required=True)
    parser.add_argument("--idl", default="research/pump_idl_9c82f61.json")
    parser.add_argument("--history-cap", type=int, default=100000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=7)
    parser.add_argument("--max-transaction-fetches", type=int, default=0,
                        help="progress cap per invocation; 0 means all pending")
    parser.add_argument("--summary-json")
    args = parser.parse_args()

    with open(args.idl, "rb") as handle:
        idl_bytes = handle.read()
    idl = json.loads(idl_bytes)
    types = {item["name"]: item for item in idl["types"]}
    event_types = {name: types[name] for name in EVENT_NAMES}
    event_discs = {hashlib.sha256(f"event:{name}".encode()).digest()[:8]: name
                   for name in EVENT_NAMES}
    url = os.environ.get("SOLANA_RPC_URL", DEFAULT_RPC)
    endpoint_ref = "public-mainnet" if url == DEFAULT_RPC else "configured-mainnet"
    connection = connect(args.database)
    members = initialize(connection, args.launch_database, args.cutoff_slot,
                         hashlib.sha256(idl_bytes).hexdigest(), endpoint_ref)
    print(f"members={members} endpoint={endpoint_ref} cutoff={args.cutoff_slot}", flush=True)

    pending_members = connection.execute("""
        SELECT mint,bonding_curve,launch_slot FROM member
        WHERE history_status IN ('pending','rpc_error') ORDER BY launch_slot,launch_transaction_index
    """).fetchall()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(address_history, url, curve, launch, args.cutoff_slot,
                                   args.history_cap, args.retries)
                   for _, curve, launch in pending_members]
        for index, ((mint, _, _), future) in enumerate(zip(pending_members, futures), 1):
            rows, status, pages, examined, error = future.result()
            store_history(connection, mint, rows, status, pages, examined, error)
            if index % 10 == 0 or status != "complete" or index == len(pending_members):
                print(f"history {index}/{len(pending_members)} mint={mint[:12]} status={status} "
                      f"in_window={len(rows)} examined={examined}", flush=True)

    pending = connection.execute("""
        SELECT signature FROM signature WHERE fetch_status IN ('pending','error')
        ORDER BY slot,signature
    """).fetchall()
    if args.max_transaction_fetches:
        pending = pending[:args.max_transaction_fetches]
    with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(fetch_transaction, url, row[0], args.retries) for row in pending]
        for index, future in enumerate(futures, 1):
            signature, raw, error = future.result()
            store_transaction(connection, signature, raw, error, event_discs, event_types, types)
            if index % 100 == 0 or error or index == len(pending):
                print(f"transactions {index}/{len(pending)} last_error={bool(error)}", flush=True)

    if args.summary_json:
        export_summary(connection, args.summary_json)
    history_counts = dict(connection.execute(
        "SELECT history_status,COUNT(*) FROM member GROUP BY history_status"))
    fetch_counts = dict(connection.execute(
        "SELECT fetch_status,COUNT(*) FROM signature GROUP BY fetch_status"))
    event_counts = dict(connection.execute(
        "SELECT event_name,COUNT(*) FROM lifecycle_event GROUP BY event_name"))
    print(f"history={history_counts} fetch={fetch_counts} events={event_counts}")
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
