#!/usr/bin/env python3
"""Enrich B0f same-block boundary observations with adjacent blocks."""
import argparse
import json

from b0f_boundary_sweep import aggregate, atomic_jsonl, rpc


def merge_stats(left, right):
    merged = {
        "transactions": left["transactions"] + right["transactions"],
        "pump_transactions": left["pump_transactions"] + right["pump_transactions"],
        "successful_pump_transactions": (
            left["successful_pump_transactions"] + right["successful_pump_transactions"]
        ),
    }
    for field in ("outer", "inner"):
        counts = dict(left[field])
        for discriminator, count in right[field].items():
            counts[discriminator] = counts.get(discriminator, 0) + count
        merged[field] = dict(sorted(counts.items()))
    return merged


def fetch_block(slot):
    block = rpc("getBlock", [slot, {
        "encoding": "jsonParsed", "transactionDetails": "full", "rewards": False,
        "maxSupportedTransactionVersion": 0,
    }])
    return (block or {}).get("transactions", [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="research/b0f_boundary_sweep_2026-07-27.jsonl")
    parser.add_argument("--output", default="research/b0g_boundary_neighbors_2026-07-27.jsonl")
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as handle:
        source = [json.loads(line) for line in handle]
    rows = []
    for index, row in enumerate(source, 1):
        previous = aggregate(fetch_block(row["slot"] - 1))
        following = aggregate(fetch_block(row["slot"] + 1))
        enriched = dict(row)
        enriched["previous_block"] = previous
        enriched["following_block"] = following
        enriched["pre_window"] = merge_stats(previous, row["before"])
        enriched["post_window"] = merge_stats(row["after"], following)
        rows.append(enriched)
        atomic_jsonl(args.output, rows)
        print(f"{index}/{len(source)} slot={row['slot']} "
              f"pre_pump={enriched['pre_window']['pump_transactions']} "
              f"post_pump={enriched['post_window']['pump_transactions']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
