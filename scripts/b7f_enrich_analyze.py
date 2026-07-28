#!/usr/bin/env python3
"""Enrich B7e lifecycle events with transaction indices, then analyze complete cohorts.

`getTransaction` omits transaction index, so canonical order requires a getBlock reconciliation for
each event-bearing slot. Analysis refuses pending/capped/error histories, pending/error/decode-error
transactions, unresolved transaction indices, or a missing cutoff block time.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sqlite3
import tempfile

try:
    import b7d_create_enumerator as b7d
    import b7e_lifecycle_reconstruct as b7e
except ModuleNotFoundError:
    from scripts import b7d_create_enumerator as b7d
    from scripts import b7e_lifecycle_reconstruct as b7e


def ensure_schema(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS slot_enrichment (
            slot INTEGER PRIMARY KEY, status TEXT NOT NULL, event_count INTEGER NOT NULL,
            resolved_count INTEGER NOT NULL, error TEXT
        );
    """)


def reconcile_slot(connection, slot, status, block, error):
    event_rows = connection.execute(
        "SELECT DISTINCT signature FROM lifecycle_event WHERE slot=?", (slot,)).fetchall()
    expected = {row[0] for row in event_rows}
    resolved = {}
    if status == "retrieved":
        for index, transaction in enumerate(block.get("transactions", [])):
            for signature in transaction["transaction"]["signatures"]:
                if signature in expected:
                    resolved[signature] = index
        missing = sorted(expected - resolved.keys())
        if missing:
            status = "reconciliation_error"
            error = f"{len(missing)} event signatures absent from block"
    else:
        status = "error"
    with connection:
        for signature, index in resolved.items():
            connection.execute(
                "UPDATE lifecycle_event SET transaction_index=? WHERE slot=? AND signature=?",
                (index, slot, signature))
        connection.execute("INSERT OR REPLACE INTO slot_enrichment VALUES (?,?,?,?,?)", (
            slot, status, len(expected), len(resolved), error))


def percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(int(quantile * len(ordered)), len(ordered) - 1)]


def analyze(connection, cutoff_time, require_indices=True):
    member_status = dict(connection.execute(
        "SELECT history_status,COUNT(*) FROM member GROUP BY history_status"))
    fetch_status = dict(connection.execute(
        "SELECT fetch_status,COUNT(*) FROM signature GROUP BY fetch_status"))
    enrichment_status = dict(connection.execute(
        "SELECT status,COUNT(*) FROM slot_enrichment GROUP BY status"))
    blockers = []
    if set(member_status) != {"complete"}:
        blockers.append(f"member histories: {member_status}")
    if any(status not in ("complete", "chain_failed") for status in fetch_status):
        blockers.append(f"transaction fetches: {fetch_status}")
    if require_indices and set(enrichment_status) - {"retrieved"}:
        blockers.append(f"slot enrichment: {enrichment_status}")
    unresolved = connection.execute(
        "SELECT COUNT(*) FROM lifecycle_event WHERE transaction_index IS NULL").fetchone()[0]
    if require_indices and unresolved:
        blockers.append(f"unresolved transaction indices: {unresolved}")
    decode_errors = connection.execute("SELECT COUNT(*) FROM decode_error").fetchone()[0]
    if decode_errors:
        blockers.append(f"decode errors: {decode_errors}")
    if blockers:
        raise RuntimeError("analysis blocked: " + "; ".join(blockers))

    members = [row[0] for row in connection.execute("SELECT mint FROM member ORDER BY launch_slot")]
    trade_times = {mint: [] for mint in members}
    completion_times, migration_times = {}, {}
    for mint, name, fields_json in connection.execute("""
        SELECT mint,event_name,fields_json FROM lifecycle_event
        ORDER BY slot,transaction_index,outer_instruction_index,inner_instruction_index,event_ordinal
    """):
        fields = json.loads(fields_json)
        timestamp = fields.get("timestamp")
        if name == "TradeEvent" and timestamp is not None:
            trade_times[mint].append(timestamp)
        elif name == "CompleteEvent" and timestamp is not None:
            completion_times.setdefault(mint, timestamp)
        elif name == "CompletePumpAmmMigrationEvent" and timestamp is not None:
            migration_times.setdefault(mint, timestamp)

    gaps_by_mint = {}
    all_gaps = []
    final_silences = []
    for mint, times in trade_times.items():
        # Event timestamps are the exact quantity used for silence intervals. Sorting them directly
        # makes the interval multiset independent of same-slot transaction order; equal timestamps
        # produce zero gaps. This does not claim a globally canonical event export.
        times.sort()
        gaps = [later - earlier for earlier, later in zip(times, times[1:])]
        if any(gap < 0 for gap in gaps):
            raise RuntimeError(f"negative canonical timestamp gap for {mint}")
        gaps_by_mint[mint] = gaps
        all_gaps.extend(gaps)
        if times:
            final_silences.append(max(0, cutoff_time - times[-1]))

    thresholds = {}
    for hours in (1, 6, 12, 24, 48, 72, 168):
        seconds = hours * 3600
        gap_count = sum(gap >= seconds for gap in all_gaps)
        token_count = sum(any(gap >= seconds for gap in gaps) for gaps in gaps_by_mint.values())
        thresholds[str(hours)] = {
            "interior_gap_count": gap_count,
            "interior_gap_fraction": gap_count / len(all_gaps) if all_gaps else None,
            "token_count": token_count,
            "token_fraction": token_count / len(members) if members else None,
        }

    migration_delays = [migration_times[mint] - completed
                        for mint, completed in completion_times.items()
                        if mint in migration_times]
    return {
        "member_count": len(members), "member_status": member_status,
        "canonical_transaction_indices_complete": unresolved == 0,
        "unresolved_transaction_indices": unresolved,
        "signature_status": fetch_status, "slot_enrichment_status": enrichment_status,
        "trade_event_count": sum(len(times) for times in trade_times.values()),
        "tokens_with_trades": sum(bool(times) for times in trade_times.values()),
        "interior_gap_count": len(all_gaps),
        "interior_gap_seconds": {
            "p50": percentile(all_gaps, .5), "p90": percentile(all_gaps, .9),
            "p99": percentile(all_gaps, .99), "p999": percentile(all_gaps, .999),
            "max": max(all_gaps) if all_gaps else None,
        },
        "threshold_incidence_hours": thresholds,
        "right_censored_final_silence_seconds": {
            "count": len(final_silences), "p50": percentile(final_silences, .5),
            "p90": percentile(final_silences, .9), "max": max(final_silences) if final_silences else None,
        },
        "completed_tokens": len(completion_times), "migrated_tokens": len(migration_times),
        "completed_and_migrated": len(migration_delays),
        "migration_delay_seconds": {
            "p50": percentile(migration_delays, .5),
            "p90": percentile(migration_delays, .9),
            "max": max(migration_delays) if migration_delays else None,
        },
        "observation_cutoff_time": cutoff_time,
    }


def atomic_json(path, value):
    destination = os.path.abspath(path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(destination), delete=False) as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cutoff-block-time", type=int, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=7)
    parser.add_argument("--skip-index-enrichment", action="store_true",
                        help="analyze timestamp intervals without claiming global canonical order")
    args = parser.parse_args()
    connection = sqlite3.connect(args.database)
    ensure_schema(connection)
    url = os.environ.get("SOLANA_RPC_URL", b7e.DEFAULT_RPC)
    if not args.skip_index_enrichment:
        completed = {row[0] for row in connection.execute(
            "SELECT slot FROM slot_enrichment WHERE status='retrieved'")}
        slots = [row[0] for row in connection.execute(
            "SELECT DISTINCT slot FROM lifecycle_event ORDER BY slot") if row[0] not in completed]
        print(f"event_slots={len(slots)+len(completed)} complete={len(completed)} pending={len(slots)}")
        with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = executor.map(lambda slot: b7d.rpc_block(url, slot, args.retries), slots)
            for index, result in enumerate(futures, 1):
                reconcile_slot(connection, *result)
                if index % 50 == 0 or result[1] != "retrieved" or index == len(slots):
                    print(f"slots {index}/{len(slots)} last_status={result[1]}", flush=True)
    result = analyze(connection, args.cutoff_block_time,
                     require_indices=not args.skip_index_enrichment)
    atomic_json(args.output, result)
    print(json.dumps(result, sort_keys=True))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
