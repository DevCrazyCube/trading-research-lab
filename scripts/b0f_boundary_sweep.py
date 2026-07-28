#!/usr/bin/env python3
"""Compare observed Pump instruction discriminators around loader upgrades.

For each successful Upgrade row, fetch the upgrade's block, locate the upgrade transaction,
and count Pump outer/inner instruction discriminators before and after it in ledger order.
This is read-only. Results are observations of traffic, not proof that absent instructions
were removed from the program interface.
"""
import argparse
import calendar
import json
import os
import tempfile
import time
import urllib.request
from collections import Counter

RPC = "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {c: i for i, c in enumerate(B58)}


def b58decode(value):
    number = 0
    for char in value:
        number = number * 58 + B58_MAP[char]
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\0" * (len(value) - len(value.lstrip("1"))) + body


def rpc(method, params, retries=8):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                RPC, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read())
            if "error" not in result:
                return result["result"]
            error = result["error"]
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        if attempt == retries - 1:
            raise RuntimeError(f"{method} failed: {error}")
        time.sleep(min(2 ** attempt, 20))


def pump_discriminators(tx):
    outer, inner = Counter(), Counter()
    message = tx["transaction"]["message"]
    for instruction in message.get("instructions", []):
        if instruction.get("programId") == PUMP and instruction.get("data"):
            raw = b58decode(instruction["data"])
            if len(raw) >= 8:
                outer[raw[:8].hex()] += 1
    for group in (tx.get("meta") or {}).get("innerInstructions") or []:
        for instruction in group.get("instructions", []):
            if instruction.get("programId") == PUMP and instruction.get("data"):
                raw = b58decode(instruction["data"])
                if len(raw) >= 8:
                    inner[raw[:8].hex()] += 1
    return outer, inner


def aggregate(transactions):
    outer, inner = Counter(), Counter()
    pump_txs = successful_pump_txs = 0
    for tx in transactions:
        tx_outer, tx_inner = pump_discriminators(tx)
        if tx_outer or tx_inner:
            pump_txs += 1
            if (tx.get("meta") or {}).get("err") is None:
                successful_pump_txs += 1
            outer.update(tx_outer)
            inner.update(tx_inner)
    return {
        "transactions": len(transactions),
        "pump_transactions": pump_txs,
        "successful_pump_transactions": successful_pump_txs,
        "outer": dict(sorted(outer.items())),
        "inner": dict(sorted(inner.items())),
    }


def load_boundaries(path):
    boundaries = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("transaction_error") is not None:
                continue
            if any(ix.get("name") == "Upgrade" for ix in row.get("loader_instructions", [])):
                boundaries.append(row)
    return sorted(boundaries, key=lambda row: row["slot"])


def atomic_jsonl(path, rows):
    destination = os.path.abspath(path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=os.path.dirname(destination), delete=False
    ) as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        temporary = handle.name
    os.replace(temporary, destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="research/b0_classification_2026-07-27.jsonl")
    parser.add_argument("--output", default="research/b0f_boundary_sweep_2026-07-27.jsonl")
    parser.add_argument("--year", type=int)
    args = parser.parse_args()
    boundaries = load_boundaries(args.input)
    if args.year:
        start = calendar.timegm(time.strptime(f"{args.year}-01-01", "%Y-%m-%d"))
        end = calendar.timegm(time.strptime(f"{args.year + 1}-01-01", "%Y-%m-%d"))
        boundaries = [row for row in boundaries if start <= row["block_time"] < end]

    rows = []
    for index, boundary in enumerate(boundaries, 1):
        block = rpc("getBlock", [boundary["slot"], {
            "encoding": "jsonParsed", "transactionDetails": "full", "rewards": False,
            "maxSupportedTransactionVersion": 0,
        }])
        transactions = block.get("transactions", []) if block else []
        upgrade_index = next((i for i, tx in enumerate(transactions)
                              if boundary["signature"] in tx["transaction"]["signatures"]), None)
        if upgrade_index is None:
            row = {"slot": boundary["slot"], "signature": boundary["signature"],
                   "block_time": boundary["block_time"], "error": "upgrade transaction not found"}
        else:
            row = {
                "slot": boundary["slot"], "signature": boundary["signature"],
                "block_time": boundary["block_time"], "upgrade_transaction_index": upgrade_index,
                "block_transactions": len(transactions),
                "before": aggregate(transactions[:upgrade_index]),
                "after": aggregate(transactions[upgrade_index + 1:]),
            }
        rows.append(row)
        atomic_jsonl(args.output, rows)
        print(f"{index}/{len(boundaries)} slot={boundary['slot']} txs={len(transactions)} "
              f"upgrade_index={upgrade_index}", flush=True)
        time.sleep(0.25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
