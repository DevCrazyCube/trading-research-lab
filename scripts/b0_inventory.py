#!/usr/bin/env python3
"""B0 - Pump program upgrade inventory.

Reads only. Enumerates BPF-upgradeable deploy/upgrade history for a program by
inspecting its ProgramData account and the signatures that touched it.

No keys, no writes, no transactions.
"""
import base64
import json
import sys
import time
import urllib.request

RPC = "https://api.mainnet-beta.solana.com"
BPF_UPGRADEABLE = "BPFLoaderUpgradeab1e11111111111111111111111"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + out


def rpc(method, params, retries=5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read())
            if "error" in out:
                # rate limit -> back off; anything else is a real error
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return {"__error__": out["error"]}
            return out["result"]
        except Exception as e:  # noqa: BLE001 - surface, never swallow
            if attempt == retries - 1:
                return {"__error__": str(e)}
            time.sleep(2 * (attempt + 1))
    return {"__error__": "exhausted retries"}


def acct(pubkey):
    return rpc("getAccountInfo", [pubkey, {"encoding": "base64", "commitment": "finalized"}])


def inventory(name, program_id):
    print(f"\n{'=' * 70}\n{name}: {program_id}\n{'=' * 70}")
    info = acct(program_id)
    if isinstance(info, dict) and "__error__" in info:
        print(f"  ERROR: {info['__error__']}")
        return
    val = (info or {}).get("value")
    if not val:
        print("  ERROR: account not found")
        return

    owner = val["owner"]
    data = base64.b64decode(val["data"][0])
    print(f"  owner            : {owner}")
    print(f"  executable       : {val['executable']}")
    print(f"  program acct len : {len(data)}")

    if owner != BPF_UPGRADEABLE:
        print("  NOT upgradeable-loader owned -> no ProgramData upgrade history to read.")
        return

    # Program account layout: u32 enum (2 = Program) + Pubkey programdata
    kind = int.from_bytes(data[0:4], "little")
    pd_addr = b58encode(data[4:36])
    print(f"  loader enum      : {kind} (2 = Program)")
    print(f"  programdata addr : {pd_addr}")

    pd = acct(pd_addr)
    if isinstance(pd, dict) and "__error__" in pd:
        print(f"  ERROR reading programdata: {pd['__error__']}")
        return
    pdval = (pd or {}).get("value")
    if not pdval:
        print("  ERROR: programdata account not found")
        return
    pdata = base64.b64decode(pdval["data"][0])
    # ProgramData layout: u32 enum (3) + u64 slot + Option<Pubkey> authority + bytecode
    pd_kind = int.from_bytes(pdata[0:4], "little")
    last_slot = int.from_bytes(pdata[4:12], "little")
    has_auth = pdata[12]
    auth = b58encode(pdata[13:45]) if has_auth == 1 else None
    print(f"  programdata enum : {pd_kind} (3 = ProgramData)")
    print(f"  last deploy slot : {last_slot}")
    print(f"  upgrade authority: {auth if auth else 'NONE (immutable)'}")
    print(f"  programdata len  : {len(pdata)} bytes")

    bt = rpc("getBlockTime", [last_slot])
    if isinstance(bt, int):
        print(f"  last deploy time : {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(bt))}")
    else:
        print(f"  last deploy time : unavailable ({bt})")

    # Upgrade history = signatures touching the ProgramData account.
    print("\n  --- signatures touching ProgramData (newest first) ---")
    sigs = rpc("getSignaturesForAddress", [pd_addr, {"limit": 1000, "commitment": "finalized"}])
    if isinstance(sigs, dict) and "__error__" in sigs:
        print(f"  ERROR: {sigs['__error__']}")
        return
    if not sigs:
        print("  none returned (public RPC history is NOT archival - absence is not evidence)")
        return
    print(f"  returned {len(sigs)} signature(s); oldest slot {sigs[-1]['slot']}, newest {sigs[0]['slot']}")
    for s in sigs:
        ts = s.get("blockTime")
        when = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts)) if ts else "?"
        err = "FAILED" if s.get("err") else "ok"
        print(f"    slot {s['slot']:>12}  {when}  {err}  {s['signature']}")


if __name__ == "__main__":
    targets = [("Pump", PUMP)]
    for extra in sys.argv[1:]:
        name, _, pid = extra.partition("=")
        targets.append((name or "extra", pid or name))
    for n, p in targets:
        inventory(n, p)
