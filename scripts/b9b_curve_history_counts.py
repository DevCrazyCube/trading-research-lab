#!/usr/bin/env python3
"""B9b — count B8b bonding-curve address histories before reconstructing reserve paths.

This is a bounded sizing measurement, not trade reconstruction. Address signatures include
non-trades and failures. Each curve is paginated to ``--cap`` and a row at the cap is explicitly
right-censored. The B9a cohort artifact is opened read-only. Results commit once per curve so an
interrupted run resumes truthfully.

Read-only RPC only. SOLANA_RPC_URL is required and is never printed or persisted.
"""
import argparse
import concurrent.futures
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request


def rpc(url, method, params, retries=8):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.load(response)
            if "error" not in payload:
                return payload.get("result")
            code = payload["error"].get("code")
            if code not in (-32005, -32429, 429):
                raise RuntimeError(
                    f"RPC error {code}: {payload['error'].get('message', 'unknown error')}")
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            if attempt == retries - 1:
                raise
        if attempt == retries - 1:
            break
        time.sleep(min(0.5 * (2 ** attempt), 12))
    raise RuntimeError(f"rate limit or transport failure persisted for {method}")


def count_history(url, address, cap, retries=8, rpc_fn=rpc):
    """Return (count, censored, pages, oldest slot/time) through the observation cutoff."""
    if cap < 1:
        raise ValueError("cap must be positive")
    total = pages = 0
    before = None
    oldest_slot = oldest_time = None
    while total < cap:
        limit = min(1000, cap - total)
        options = {"limit": limit, "commitment": "finalized"}
        if before is not None:
            options["before"] = before
        page = rpc_fn(url, "getSignaturesForAddress", [address, options], retries) or []
        pages += 1
        if not page:
            return total, False, pages, oldest_slot, oldest_time
        if len(page) > limit:
            raise RuntimeError(f"RPC returned {len(page)} rows for limit {limit}")
        total += len(page)
        oldest = page[-1]
        before = oldest.get("signature")
        oldest_slot = oldest.get("slot")
        oldest_time = oldest.get("blockTime")
        if not before:
            raise RuntimeError("signature history row lacks signature pagination cursor")
        if len(page) < limit:
            return total, False, pages, oldest_slot, oldest_time
    return total, True, pages, oldest_slot, oldest_time


def initialize(database, source_path, cap):
    database.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS curve_history_count (
            mint TEXT PRIMARY KEY,
            bonding_curve TEXT NOT NULL UNIQUE,
            signature_count INTEGER NOT NULL CHECK(signature_count >= 0),
            capped INTEGER NOT NULL CHECK(capped IN (0, 1)),
            pages INTEGER NOT NULL CHECK(pages >= 1),
            oldest_slot INTEGER,
            oldest_block_time INTEGER,
            observed_at_unix REAL NOT NULL
        );
    """)
    existing = dict(database.execute("SELECT key, value FROM metadata"))
    expected = {"source_artifact": source_path, "signature_cap": str(cap)}
    for key, value in expected.items():
        if key in existing and existing[key] != value:
            raise RuntimeError(
                f"REFUSING: existing database {key}={existing[key]!r}, requested {value!r}")
    missing = [(key, value) for key, value in expected.items() if key not in existing]
    if missing:
        with database:
            database.executemany("INSERT INTO metadata VALUES (?, ?)", missing)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="research/b9a_outcomes.sqlite")
    parser.add_argument("--database", default="research/b9b_curve_history_counts.sqlite")
    parser.add_argument("--cap", type=int, default=10000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=8)
    arguments = parser.parse_args()
    if arguments.cap < 1:
        parser.error("--cap must be positive")
    if not 1 <= arguments.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    url = os.environ.get("SOLANA_RPC_URL")
    if not url:
        raise SystemExit("REFUSING: SOLANA_RPC_URL is not set. Source .env silently first.")

    source = sqlite3.connect(f"file:{arguments.source}?mode=ro", uri=True)
    members = source.execute(
        "SELECT mint, bonding_curve FROM outcome ORDER BY launch_slot, mint").fetchall()
    source.close()
    if len(members) != 1601 or len({row[1] for row in members}) != len(members):
        raise SystemExit(
            f"REFUSING: expected 1,601 rows with distinct curves, got {len(members)} rows")

    output = sqlite3.connect(arguments.database)
    initialize(output, arguments.source, arguments.cap)
    done = {row[0] for row in output.execute("SELECT mint FROM curve_history_count")}
    pending = [row for row in members if row[0] not in done]
    print(f"cohort={len(members):,} already_counted={len(done):,} pending={len(pending):,}")

    def measure(member):
        mint, curve = member
        result = count_history(url, curve, arguments.cap, arguments.retries)
        return mint, curve, *result, time.time()

    completed = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=arguments.workers) as executor:
            futures = {executor.submit(measure, row): row for row in pending}
            for future in concurrent.futures.as_completed(futures):
                row = future.result()  # fail visibly; incomplete curves remain absent and resumable
                with output:
                    output.execute(
                        "INSERT INTO curve_history_count VALUES (?,?,?,?,?,?,?,?)", row)
                completed += 1
                if completed % 25 == 0 or completed == len(pending):
                    print(f"measured={completed:,}/{len(pending):,}", flush=True)
    finally:
        output.close()

    check = sqlite3.connect(f"file:{arguments.database}?mode=ro", uri=True)
    count, signatures, capped, pages = check.execute(
        "SELECT COUNT(*), SUM(signature_count), SUM(capped), SUM(pages) "
        "FROM curve_history_count").fetchone()
    integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    check.close()
    if count != len(members) or integrity != "ok":
        raise SystemExit(f"REFUSING publication: rows={count}, integrity={integrity}")
    print(f"complete curves={count:,} signatures={signatures:,} capped={capped:,} rpc_pages={pages:,}")
    print("Counts are address signatures, not Pump trades or executable fills.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
