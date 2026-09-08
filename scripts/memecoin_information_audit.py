"""Read-only evidence census for the owner's three unsearched information gaps.

No entry rules, returns, or old strategy grids are evaluated. Results are reproducible
from logical SQL/prefix hashes; output directories must be new. Never reads .env.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import zlib

from scripts import b9d_transaction_bodies as B9D
from scripts.birth_origin import ROOT, Refused, canonical, digest, write_new


def ro(path):
    c = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA temp_store=MEMORY")
    c.execute("BEGIN")
    return c


def snapshot_audit(path):
    limit = path.stat().st_size
    hashed = hashlib.sha256()
    first = {}
    counts = Counter()
    observed_times = []
    with path.open("rb") as handle:
        remaining = limit
        while remaining:
            line = handle.readline(remaining)
            remaining -= len(line)
            hashed.update(line)
            if not line.endswith(b"\n"):
                counts["partial_tail"] += 1
                break
            row = json.loads(line)
            if row.get("_meta"):
                counts["cycle_rows"] += 1
                continue
            counts["snapshot_rows"] += 1
            if not row.get("mint") or not isinstance(row.get("ts_ms"), (int, float)):
                raise Refused("snapshot lacks mint or collection clock")
            observed_times.append(row["ts_ms"])
            m = row["mint"]
            if m not in first or row["ts_ms"] < first[m]["ts_ms"]:
                first[m] = row
    ages = [(r["ts_ms"] - r["created_ms"]) / 1000 for r in first.values()
            if isinstance(r.get("created_ms"), (int, float))]
    return {"file": str(path.relative_to(ROOT)), "prefix_bytes": limit,
            "prefix_sha256": hashed.hexdigest(), "counts": dict(counts),
            "distinct_mints": len(first), "first_cycle_ms": min(observed_times),
            "last_cycle_ms": max(observed_times),
            "first_sighting_age_seconds": {"n": len(ages), "median": statistics.median(ages),
               "negative": sum(a < 0 for a in ages), "within_60s": sum(0 <= a <= 60 for a in ages)},
            "first_seen_mcap_ge_100k": sum((r.get("mcap") or 0) >= 100000 for r in first.values()),
            "clock_limitation": "ts_ms is sampled BEFORE network harvest, not individual response receipt",
            "birth_census_eligible": False}


def lp_burn_amount(instruction, lp_mint, token_program):
    """Strict SPL Burn/BurnChecked decode, then bind to the migration's LP mint.

    Official source: solana-program/token-2022 interface/src/instruction.rs,
    TokenInstruction::unpack tags 8/15, accounts[1] is mint. Accessed 2026-09-08.
    """
    data, accounts = instruction["data"], instruction["accounts"]
    if instruction["program_id"] != token_program or len(accounts) < 3 or accounts[1] != lp_mint:
        return None
    if not data or data[0] not in (8, 15):
        return None
    if len(data) != (9 if data[0] == 8 else 10):
        raise Refused("LP burn instruction has an unknown payload layout")
    return int.from_bytes(data[1:9], "little")


def corpus_audit():
    bodies = ro(ROOT / "research/b11a/b11a_bodies.sqlite")
    labels = ro(ROOT / "research/b11a/window_labels.sqlite")
    bars_db = ro(ROOT / "research/midcap/grad_ohlcv.sqlite")
    idl_raw = (ROOT / B9D.PUMP_IDL_PATH).read_bytes()
    if hashlib.sha256(idl_raw).hexdigest() != B9D.PUMP_IDL_SHA256:
        raise Refused("Pump IDL hash mismatch")
    idl = json.loads(idl_raw)
    layouts = {r["name"]: [a["name"] for a in r["accounts"]] for r in idl["instructions"]}
    label_rows = [dict(r) for r in labels.execute("SELECT mint,bonding_curve,complete,create_slot,block_time FROM window_label ORDER BY mint")]
    label_map = {r["bonding_curve"]: r for r in label_rows}
    bars = [dict(r) for r in bars_db.execute("SELECT * FROM ohlcv ORDER BY mint")]
    bar_map = {r["mint"]: r for r in bars}
    statuses = Counter(r["status"] for r in bars)
    bar_faults = Counter()
    for r in bars:
        raw_bars = json.loads(r["bars_json"]) if r["bars_json"] else []
        if len(raw_bars) != r["n_bars"]:
            bar_faults["count_mismatch"] += 1
        if len({b[0] for b in raw_bars}) != len(raw_bars):
            bar_faults["duplicate_timestamps"] += 1
    reserve_rows = [dict(r) for r in bodies.execute("SELECT bonding_curve,count(*) AS observations,min(slot) AS first_slot,max(slot) AS last_slot FROM reserve_observation GROUP BY bonding_curve ORDER BY bonding_curve")]
    overlap = []
    for r in reserve_rows:
        label = label_map.get(r["bonding_curve"])
        if not label or label["complete"] != 1:
            continue
        bar = bar_map.get(label["mint"])
        overlap.append({**r, "mint": label["mint"], "bar_status": bar["status"] if bar else "NO_ROW",
                        "n_bars": bar["n_bars"] if bar else 0})
    swap_counts = {r[0]: r[1] for r in bodies.execute("SELECT idl_name,count(*) FROM instruction WHERE program_id=? GROUP BY idl_name", (B9D.PUMPSWAP_PROGRAM,))}
    migrations = [dict(r) for r in bodies.execute("SELECT slot,transaction_index,outer_index,inner_index,signature,idl_name,accounts_json FROM instruction WHERE program_id=? AND idl_name IN ('migrate','migrate_v2') ORDER BY slot,transaction_index,outer_index,inner_index", (B9D.PUMP_PROGRAM,))]
    migration_evidence = []
    for row in migrations:
        names = layouts[row["idl_name"]]
        values = json.loads(row["accounts_json"])
        if len(values) < len(names):
            raise Refused("short migration account list")
        accounts = dict(zip(names, values))
        mint = accounts.get("mint") or accounts["base_mint"]
        blob_row = bodies.execute("SELECT response_sha256,raw_zlib FROM raw_transaction WHERE signature=?", (row["signature"],)).fetchone()
        if blob_row is None:
            raise Refused("migration has no retained transaction body")
        raw = zlib.decompress(blob_row["raw_zlib"])
        if hashlib.sha256(raw).hexdigest() != blob_row["response_sha256"]:
            raise Refused("migration raw-response hash mismatch")
        tx = json.loads(raw)["result"]
        if tx["slot"] != row["slot"] or tx["meta"]["err"] is not None:
            raise Refused("migration transaction slot/success mismatch")
        instructions = B9D.envelope_instructions(tx)
        parent = [i for i in instructions if (i["outer_index"], i["inner_index"]) == (row["outer_index"], row["inner_index"])]
        if len(parent) != 1 or parent[0]["accounts"] != values or parent[0]["program_id"] != B9D.PUMP_PROGRAM:
            raise Refused("cached migration does not reconcile with raw envelope")
        discriminator = next(i["discriminator"] for i in idl["instructions"] if i["name"] == row["idl_name"])
        if parent[0]["data"][:8] != bytes(discriminator):
            raise Refused("migration discriminator does not match pinned IDL")
        burns = []
        for instruction in instructions:
            amount = lp_burn_amount(instruction, accounts["lp_mint"], accounts["token_2022_program"])
            # Same transaction evidence only, not a guessed inner-CPI ancestry.
            if amount is not None:
                burns.append({"outer_index": instruction["outer_index"], "inner_index": instruction["inner_index"],
                              "amount_raw": amount})
        bar = bar_map.get(mint)
        migration_evidence.append({"mint": mint, "pool": accounts["pool"], "lp_mint": accounts["lp_mint"],
            "slot": row["slot"], "signature": row["signature"], "response_sha256": blob_row["response_sha256"],
            "raw_lp_burns": burns, "ohlcv_status": bar["status"] if bar else "NO_ROW",
            "ohlcv_pool_matches_migration": bool(bar and bar["pool"] == accounts["pool"]),
            "interpretation": "positive LP burn evidence at migration; no later withdrawal coverage claim"})
    for c in (bodies, labels, bars_db):
        c.close()
    return {"labels": {"n": len(label_rows), "complete": sum(r["complete"] == 1 for r in label_rows),
                        "rows_sha256": digest(label_rows)},
            "ohlcv": {"rows": len(bars), "bars": sum(r["n_bars"] for r in bars), "statuses": dict(statuses),
                      "faults": dict(bar_faults), "rows_sha256": digest(bars),
                      "collection_limitation": "pools[0] at later fetch; at most one 1000-bar request; no retained raw HTTP pool response"},
            "reserve_curves": len(reserve_rows), "graduate_overlap": overlap,
            "graduate_overlap_with_bars": sum(r["n_bars"] > 0 for r in overlap),
            "pumpswap_instruction_counts": swap_counts,
            "confirmed_withdrawal_instructions_in_this_cache": swap_counts.get("withdraw", 0),
            "post_graduation_withdrawal_coverage": "UNKNOWN_NOT_A_POOL_CENSUS",
            "migrations": migration_evidence,
            "migration_count": len(migration_evidence),
            "migration_positive_lp_burn_count": sum(any(b["amount_raw"] > 0 for b in r["raw_lp_burns"]) for r in migration_evidence),
            "ohlcv_pool_matches_migration_count": sum(r["ohlcv_pool_matches_migration"] for r in migration_evidence),
            "migration_rows_sha256": digest(migrations),
            "pump_idl_sha256": B9D.PUMP_IDL_SHA256,
            "envelope_decoder_sha256": hashlib.sha256((ROOT / "scripts/b9d_transaction_bodies.py").read_bytes()).hexdigest()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise Refused("output path already exists")
    snapshots = snapshot_audit(ROOT / "research/midcap/fresh_snapshots.jsonl")
    corpus = corpus_audit()
    report = {"status": "EVIDENCE_AUDIT_ONLY", "performance_evaluated": False,
              "snapshots": snapshots, "corpus": corpus,
              "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.out.mkdir(parents=True)
    write_new(args.out / "result.json", report)
    print(json.dumps({"output": str(args.out), "snapshot_distinct_mints": snapshots["distinct_mints"],
       "median_first_sighting_age_seconds": snapshots["first_sighting_age_seconds"]["median"],
       "graduate_overlap_with_bars": corpus["graduate_overlap_with_bars"],
       "migration_count": corpus["migration_count"],
       "migration_positive_lp_burn_count": corpus["migration_positive_lp_burn_count"],
       "ohlcv_pool_matches_migration_count": corpus["ohlcv_pool_matches_migration_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
