#!/usr/bin/env python3
"""Classify BPF Upgradeable Loader instructions touching a program's ProgramData.

Read-only: no keys, signing, or transaction submission. Output is JSONL so the
classification can be audited and regenerated.
"""

import argparse
import json
import os
import sys
import tempfile
from collections import Counter

try:
    from b0_inventory import BPF_UPGRADEABLE, PUMP, acct, b58encode, rpc
except ModuleNotFoundError:  # support `python -m scripts.b0_classify_transactions`
    from scripts.b0_inventory import BPF_UPGRADEABLE, PUMP, acct, b58encode, rpc

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {c: i for i, c in enumerate(B58)}

LOADER_INSTRUCTIONS = {
    0: "InitializeBuffer",
    1: "Write",
    2: "DeployWithMaxDataLen",
    3: "Upgrade",
    4: "SetAuthority",
    5: "Close",
    6: "ExtendProgram",
    7: "SetAuthorityChecked",
    8: "Migrate",
}


def b58decode(text: str) -> bytes:
    number = 0
    for char in text:
        number = number * 58 + B58_MAP[char]
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\0" * (len(text) - len(text.lstrip("1"))) + raw


def programdata_for(program_id: str) -> str:
    value = (acct(program_id) or {}).get("value")
    if not value or value["owner"] != BPF_UPGRADEABLE:
        raise RuntimeError("program is missing or not owned by the upgradeable loader")
    import base64

    data = base64.b64decode(value["data"][0])
    if int.from_bytes(data[0:4], "little") != 2:
        raise RuntimeError("unexpected program account variant")
    return b58encode(data[4:36])


def account_key_strings(message: dict, meta: dict) -> list[str]:
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in message["accountKeys"]]
    loaded = meta.get("loadedAddresses") or {}
    keys.extend(loaded.get("writable") or [])
    keys.extend(loaded.get("readonly") or [])
    return keys


def classify(program_id: str, output_path: str | None = None) -> int:
    programdata = programdata_for(program_id)
    signatures = rpc(
        "getSignaturesForAddress",
        [programdata, {"limit": 1000, "commitment": "finalized"}],
    )
    if isinstance(signatures, dict) and "__error__" in signatures:
        raise RuntimeError(signatures["__error__"])

    counts: Counter[str] = Counter()
    errors = 0
    rows: list[dict] = []
    for item in signatures:
        signature = item["signature"]
        tx = rpc(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "json",
                    "commitment": "finalized",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )
        row = {
            "signature": signature,
            "slot": item["slot"],
            "block_time": item.get("blockTime"),
            "transaction_error": item.get("err"),
            "loader_instructions": [],
        }
        if isinstance(tx, dict) and "__error__" in tx:
            row["fetch_error"] = tx["__error__"]
            errors += 1
            rows.append(row)
            continue
        if tx is None:
            row["fetch_error"] = "transaction unavailable from RPC"
            errors += 1
            rows.append(row)
            continue

        message = tx["transaction"]["message"]
        keys = account_key_strings(message, tx["meta"])
        instruction_groups = [("outer", message.get("instructions") or [])]
        for group in tx["meta"].get("innerInstructions") or []:
            instruction_groups.append((f"inner:{group['index']}", group["instructions"]))

        for location, instructions in instruction_groups:
            for instruction in instructions:
                program = instruction.get("programId")
                if program is None and "programIdIndex" in instruction:
                    program = keys[instruction["programIdIndex"]]
                if program != BPF_UPGRADEABLE or "data" not in instruction:
                    continue
                data = b58decode(instruction["data"])
                variant = int.from_bytes(data[0:4], "little") if len(data) >= 4 else None
                name = LOADER_INSTRUCTIONS.get(variant, f"Unknown({variant})")
                accounts = instruction.get("accounts") or []
                resolved_accounts = [keys[a] if isinstance(a, int) else a for a in accounts]
                row["loader_instructions"].append(
                    {
                        "location": location,
                        "variant": variant,
                        "name": name,
                        "accounts": resolved_accounts,
                        "mentions_programdata": programdata in resolved_accounts,
                    }
                )
                counts[name] += 1
        if not row["loader_instructions"]:
            counts["NoLoaderInstruction"] += 1
        rows.append(row)

    summary = {
        "summary": {
            "program_id": program_id,
            "programdata": programdata,
            "signatures": len(signatures),
            "fetch_errors": errors,
            "instruction_counts": dict(sorted(counts.items())),
        }
    }
    lines = [json.dumps(row, separators=(",", ":")) for row in rows]
    lines.append(json.dumps(summary, separators=(",", ":")))
    if output_path:
        destination = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(destination), delete=False
        ) as handle:
            handle.write("\n".join(lines) + "\n")
            temporary = handle.name
        os.replace(temporary, destination)
    else:
        print("\n".join(lines))
    print(json.dumps(summary, separators=(",", ":")), file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("program_id", nargs="?", default=PUMP)
    parser.add_argument("--output")
    arguments = parser.parse_args()
    raise SystemExit(classify(arguments.program_id, arguments.output))
