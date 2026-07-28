#!/usr/bin/env python3
"""B6a - measure Pump capture volume to turn a disk budget into a retention window.

Measures, from real finalized blocks, how many bytes per slot a recorder would store at
three subscription breadths. Reports retention at the owner's stated 75-100 GB budget.

Read-only. No keys, no signing, no transactions.
"""
import base64
import json
import sys
import time
import urllib.request

RPC = "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
SLOTS_PER_DAY = 216_000  # 400 ms target slot time


def rpc(method, params, retries=5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                o = json.loads(r.read())
            if "error" in o:
                if a < retries - 1:
                    time.sleep(2.5 * (a + 1)); continue
                return {"__error__": o["error"]}
            return o["result"]
        except Exception as e:  # noqa: BLE001
            if a == retries - 1:
                return {"__error__": str(e)}
            time.sleep(2.5 * (a + 1))
    return {"__error__": "retries"}


def touches(tx, programs):
    msg = tx["transaction"]["message"]
    for ix in msg.get("instructions", []):
        if ix.get("programId") in programs:
            return True
    for g in (tx.get("meta") or {}).get("innerInstructions") or []:
        for ix in g.get("instructions", []):
            if ix.get("programId") in programs:
                return True
    return False


def main():
    nblocks = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    tip = rpc("getSlot", [{"commitment": "finalized"}])
    start = tip - nblocks - 2
    tot = {"all": 0, "pump_ps": 0, "pump": 0}
    cnt = {"all": 0, "pump_ps": 0, "pump": 0}
    b64_pump = 0
    blocks = 0

    print(f"measuring {nblocks} finalized blocks from slot {start}\n")
    for slot in range(start, start + nblocks):
        blk = rpc("getBlock", [slot, {"encoding": "jsonParsed", "transactionDetails": "full",
                                      "rewards": False, "maxSupportedTransactionVersion": 0}])
        if isinstance(blk, dict) and "__error__" in blk or not blk:
            print(f"  slot {slot}: unavailable")
            continue
        blocks += 1
        txs = blk.get("transactions", [])
        a = p = 0
        for tx in txs:
            enc = len(json.dumps(tx, separators=(",", ":")).encode())
            tot["all"] += enc
            cnt["all"] += 1
            if touches(tx, {PUMP, PUMPSWAP}):
                tot["pump_ps"] += enc
                cnt["pump_ps"] += 1
                a += 1
            if touches(tx, {PUMP}):
                tot["pump"] += enc
                cnt["pump"] += 1
                p += 1
        # raw wire proxy: base64 of the block's pump txs is closer to protobuf size
        raw = rpc("getBlock", [slot, {"encoding": "base64", "transactionDetails": "full",
                                      "rewards": False, "maxSupportedTransactionVersion": 0}])
        if raw and not (isinstance(raw, dict) and "__error__" in raw):
            for tx in raw.get("transactions", []):
                b64_pump += len(base64.b64decode(tx["transaction"][0]))
        print(f"  slot {slot}: {len(txs)} txs, {a} touch Pump/PumpSwap, {p} touch Pump")
        time.sleep(0.2)

    if not blocks:
        print("no blocks measured"); return 1

    print(f"\n{'=' * 74}\nmeasured {blocks} blocks, {cnt['all']} transactions\n{'=' * 74}")
    print(f"{'breadth':<34}{'tx/slot':>9}{'KB/slot':>10}{'GB/day':>10}")
    rows = []
    for key, label in (("all", "everything (whole cluster)"),
                       ("pump_ps", "Pump + PumpSwap transactions"),
                       ("pump", "Pump program only")):
        kb = tot[key] / blocks / 1024
        gbday = tot[key] / blocks * SLOTS_PER_DAY / 1024 ** 3
        rows.append((label, gbday))
        print(f"{label:<34}{cnt[key] / blocks:>9.1f}{kb:>10.1f}{gbday:>10.2f}")

    wire_gbday = b64_pump / blocks * SLOTS_PER_DAY / 1024 ** 3
    print(f"\nraw wire-format proxy (whole block, base64-decoded): {wire_gbday:.2f} GB/day")
    print("  JSON figures above are an UPPER bound; Geyser protobuf is materially smaller.")

    print(f"\n{'=' * 74}\nretention at the stated disk budget\n{'=' * 74}")
    for label, gbday in rows:
        if gbday <= 0:
            continue
        print(f"  {label:<34} 75 GB -> {75 / gbday:>7.1f} days    100 GB -> {100 / gbday:>7.1f} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
