#!/usr/bin/env python3
"""B0b - current-regime Pump interface probe.

Answers, against live mainnet and the CURRENT deployed program version:

  1. Which Anchor instruction discriminators are actually in use right now?
  2. Do Pump transactions emit events as self-CPI inner instructions (C2's premise),
     or would a decoder have to read logMessages?
  3. Are logs actually truncated in the wild, and how often?

Read-only. No keys, no signing, no transactions.
"""
import base64
import json
import sys
import time
import urllib.request
from collections import Counter

RPC = "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 60

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {c: i for i, c in enumerate(B58)}


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + B58_MAP[ch]
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\0" * pad + body


def rpc(method, params, retries=6):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                out = json.loads(r.read())
            if "error" in out:
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return {"__error__": out["error"]}
            return out["result"]
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                return {"__error__": str(e)}
            time.sleep(1.5 * (attempt + 1))
    return {"__error__": "exhausted retries"}


def main():
    print(f"Sampling up to {SAMPLE} recent Pump transactions from {RPC}\n")
    sigs = rpc("getSignaturesForAddress", [PUMP, {"limit": SAMPLE, "commitment": "finalized"}])
    if isinstance(sigs, dict) and "__error__" in sigs:
        print(f"ERROR fetching signatures: {sigs['__error__']}")
        return 1
    print(f"got {len(sigs)} signatures; slots {sigs[-1]['slot']} .. {sigs[0]['slot']}")
    bt = rpc("getBlockTime", [sigs[0]["slot"]])
    if isinstance(bt, int):
        print(f"newest sampled slot time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(bt))}")
    print(f"(last program upgrade was slot 433095571, 2026-07-15 16:11:40 UTC)\n")

    outer_disc = Counter()
    inner_disc = Counter()
    self_cpi_tx = 0
    no_self_cpi_tx = 0
    truncated = 0
    fetched = 0
    failed_tx = 0
    outer_accounts = {}
    inner_data_len = Counter()
    errors = 0

    for i, s in enumerate(sigs):
        tx = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed",
                                                     "maxSupportedTransactionVersion": 0,
                                                     "commitment": "finalized"}])
        if isinstance(tx, dict) and "__error__" in tx:
            errors += 1
            continue
        if not tx:
            errors += 1
            continue
        fetched += 1
        meta = tx.get("meta") or {}
        if meta.get("err"):
            failed_tx += 1

        logs = meta.get("logMessages") or []
        if any("truncated" in ln.lower() for ln in logs):
            truncated += 1

        # outer instructions calling Pump
        msg = tx["transaction"]["message"]
        for ix in msg.get("instructions", []):
            if ix.get("programId") != PUMP:
                continue
            data = ix.get("data")
            if not data:
                continue
            raw = b58decode(data)
            d = raw[:8].hex()
            outer_disc[d] += 1
            outer_accounts.setdefault(d, Counter())[len(ix.get("accounts", []))] += 1

        # inner instructions: self-CPI back into Pump = Anchor emit_cpi! event
        found_self_cpi = False
        for group in meta.get("innerInstructions") or []:
            for ix in group.get("instructions", []):
                if ix.get("programId") != PUMP:
                    continue
                data = ix.get("data")
                if not data:
                    continue
                raw = b58decode(data)
                sh = ix.get("stackHeight")
                # Anchor emit_cpi! writes 8-byte global ix discriminator + 8-byte event
                # discriminator + borsh event body.
                inner_disc[raw[:8].hex()] += 1
                inner_data_len[len(raw)] += 1
                if len(raw) > 16:
                    found_self_cpi = True
                    if sh is not None and sh < 2:
                        print(f"  note: self-CPI-looking ix at stackHeight={sh} in {s['signature'][:16]}")
        if found_self_cpi:
            self_cpi_tx += 1
        else:
            no_self_cpi_tx += 1

        if (i + 1) % 10 == 0:
            print(f"  ...{i + 1}/{len(sigs)}")
        time.sleep(0.12)

    print(f"\n{'=' * 70}\nRESULTS  (fetched {fetched}, rpc errors {errors}, failed txs {failed_tx})\n{'=' * 70}")

    print("\n-- outer Pump instruction discriminators (first 8 bytes) --")
    for d, c in outer_disc.most_common():
        accts = ", ".join(f"{k} accts x{v}" for k, v in outer_accounts[d].most_common())
        print(f"  {d}  count={c:<5} [{accts}]")

    print("\n-- inner (self-CPI) Pump instruction discriminators --")
    for d, c in inner_disc.most_common():
        print(f"  {d}  count={c}")

    print("\n-- inner self-CPI payload sizes (bytes) --")
    for ln, c in sorted(inner_data_len.items()):
        print(f"  {ln:>5} bytes  x{c}")

    print(f"\n-- C2 verdict inputs --")
    print(f"  transactions WITH a Pump self-CPI inner instruction : {self_cpi_tx}")
    print(f"  transactions WITHOUT                                : {no_self_cpi_tx}")
    if fetched:
        print(f"  self-CPI coverage                                   : {100.0 * self_cpi_tx / fetched:.1f}%")
    print(f"  transactions whose logs contain 'truncated'         : {truncated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
