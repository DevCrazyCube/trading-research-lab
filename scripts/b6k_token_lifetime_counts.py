#!/usr/bin/env python3
"""Measure signature-history size for launch-time-selected Pump token mints.

Discovery scans recent Pump transactions newest-to-oldest and decodes CreateEvent mint fields.
The first N distinct mints form the cohort before their address histories are queried. For each
mint, getSignaturesForAddress is paginated to a configured cap. Counts at the cap are explicitly
right-censored and never reported as complete lifetimes.

The RPC URL comes only from an environment variable and is never printed or persisted.
Read-only: no keys, signing, or transactions.
"""
import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CREATE_DISC = hashlib.sha256(b"event:CreateEvent").digest()[:8]


def rpc(url, method, params, retries=8):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as response:
                obj = json.loads(response.read())
            if "error" not in obj:
                return obj.get("result")
            if obj["error"].get("code") not in (-32005, -32429, 429):
                raise RuntimeError(f"RPC error {obj['error'].get('code')}: {obj['error'].get('message')}")
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
        time.sleep(min(0.5 * 2 ** attempt, 8))
    raise RuntimeError(f"rate limit persisted for {method}")


def create_mints(tx):
    mints = set()
    logs = ((tx or {}).get("meta") or {}).get("logMessages") or []
    for line in logs:
        if not line.startswith("Program data:"):
            continue
        for field in line.split("Program data:", 1)[1].split():
            try:
                raw = base64.b64decode(field, validate=True)
            except ValueError:
                continue
            if raw[:8] != CREATE_DISC:
                continue
            # Pinned official IDL: discriminator, three Borsh strings, then mint Pubkey.
            offset = 8
            valid = True
            for _ in range(3):
                if offset + 4 > len(raw):
                    valid = False
                    break
                length = int.from_bytes(raw[offset:offset + 4], "little")
                offset += 4 + length
                if offset > len(raw):
                    valid = False
                    break
            if valid and offset + 32 <= len(raw):
                mints.add(base58(raw[offset:offset + 32]))
    return mints


def base58(raw):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    value = int.from_bytes(raw, "big")
    out = ""
    while value:
        value, remainder = divmod(value, 58)
        out = alphabet[remainder] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + (out or "")


def discover(url, count, scan_limit, workers):
    signatures = rpc(url, "getSignaturesForAddress", [PUMP, {
        "limit": scan_limit, "commitment": "finalized"}]) or []
    cohort = []
    tx_options = {
        "encoding": "json", "commitment": "finalized", "maxSupportedTransactionVersion": 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        window = workers * 2
        for start in range(0, len(signatures), window):
            rows = signatures[start:start + window]
            futures = [executor.submit(rpc, url, "getTransaction",
                                       [row["signature"], tx_options]) for row in rows]
            for offset, future in enumerate(futures, 1):
                index = start + offset
                for mint in sorted(create_mints(future.result())):
                    if mint not in cohort:
                        cohort.append(mint)
                        print(f"discovered {len(cohort):>3}/{count} after {index} Pump signatures",
                              flush=True)
                        if len(cohort) >= count:
                            return cohort
    return cohort


def count_history(url, mint, cap):
    total, before, oldest_time = 0, None, None
    while total < cap:
        options = {"limit": min(1000, cap - total), "commitment": "finalized"}
        if before:
            options["before"] = before
        page = rpc(url, "getSignaturesForAddress", [mint, options]) or []
        if not page:
            return total, False, oldest_time
        total += len(page)
        before = page[-1]["signature"]
        oldest_time = page[-1].get("blockTime")
        if len(page) < options["limit"]:
            return total, False, oldest_time
    return total, True, oldest_time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokens", type=int, default=20)
    parser.add_argument("--cap", type=int, default=10000)
    parser.add_argument("--scan-limit", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--rpc-env", default="SOLANA_RPC_URL")
    args = parser.parse_args()
    url = os.environ.get(args.rpc_env, DEFAULT_RPC)
    print("endpoint: public-mainnet" if url == DEFAULT_RPC else "endpoint: configured-mainnet")
    if not 1 <= args.workers <= 32:
        parser.error("--workers must be between 1 and 32")
    cohort = discover(url, args.tokens, args.scan_limit, args.workers)
    if len(cohort) < args.tokens:
        print(f"warning: only discovered {len(cohort)} tokens")
    rows = []
    for index, mint in enumerate(cohort, 1):
        count, censored, oldest = count_history(url, mint, args.cap)
        rows.append((count, censored))
        mark = ">=" if censored else "="
        print(f"{index:>3} {mint} signatures {mark}{count} oldest_block_time={oldest}", flush=True)
    uncapped = sorted(count for count, capped in rows if not capped)
    print(f"\ncohort={len(rows)} uncapped={len(uncapped)} capped_at_{args.cap}="
          f"{sum(censored for _, censored in rows)}")
    if uncapped:
        summary = f"observed-to-date uncapped counts: min={uncapped[0]} max={uncapped[-1]}"
        if len(uncapped) >= 3:
            summary += f" median={uncapped[len(uncapped)//2]}"
        if len(uncapped) >= 10:
            summary += f" p90={uncapped[int(.9*(len(uncapped)-1))]}"
        print(summary)
    print("These are all address signatures observed to the current cutoff, not Pump-trade-only "
          "counts or completed token lifetimes; every recent launch is future-right-censored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
