#!/usr/bin/env python3
"""B0d - identify which Anchor events the current Pump program emits via self-CPI.

emit_cpi! payload layout:  [8-byte event-ix tag][8-byte event discriminator][borsh body]

Read-only. Resolves the event discriminator by sha256("event:" + Name)[:8] derivation.
"""
import hashlib
import json
import sys
import time
import urllib.request
from collections import Counter

RPC = "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EVENT_TAG = "e445a52e51cb9a1d"
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 40

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {c: i for i, c in enumerate(B58)}

EVENT_NAMES = [
    "TradeEvent", "CreateEvent", "CompleteEvent", "SetParamsEvent",
    "CompletePumpAmmMigrationEvent", "ExtendAccountEvent", "CollectCreatorFeeEvent",
    "SetCreatorEvent", "UpdateGlobalAuthorityEvent", "SyncUserVolumeAccumulatorEvent",
    "ClaimTokenIncentivesEvent", "SetMetaplexCreatorEvent", "AdminSetCreatorEvent",
    "CloseUserVolumeAccumulatorEvent", "InitUserVolumeAccumulatorEvent",
    "AdminUpdateTokenIncentivesEvent", "SetCoinCreatorEvent", "CollectCoinCreatorFeeEvent",
]


def b58decode(s):
    n = 0
    for ch in s:
        n = n * 58 + B58_MAP[ch]
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + body


def rpc(method, params, retries=6):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                out = json.loads(r.read())
            if "error" in out:
                if a < retries - 1:
                    time.sleep(1.5 * (a + 1)); continue
                return {"__error__": out["error"]}
            return out["result"]
        except Exception as e:  # noqa: BLE001
            if a == retries - 1:
                return {"__error__": str(e)}
            time.sleep(1.5 * (a + 1))
    return {"__error__": "retries"}


def main():
    table = {hashlib.sha256(f"event:{n}".encode()).digest()[:8].hex(): n for n in EVENT_NAMES}
    sigs = rpc("getSignaturesForAddress", [PUMP, {"limit": SAMPLE, "commitment": "finalized"}])
    if isinstance(sigs, dict) and "__error__" in sigs:
        print(f"ERROR: {sigs['__error__']}"); return 1

    events = Counter()
    bodies = {}
    ok = fail = 0
    for s in sigs:
        tx = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed",
                                                    "maxSupportedTransactionVersion": 0,
                                                    "commitment": "finalized"}])
        if isinstance(tx, dict) and "__error__" in tx or not tx:
            continue
        meta = tx.get("meta") or {}
        if meta.get("err"):
            fail += 1
            continue
        ok += 1
        for g in meta.get("innerInstructions") or []:
            for ix in g.get("instructions", []):
                if ix.get("programId") != PUMP or not ix.get("data"):
                    continue
                raw = b58decode(ix["data"])
                if len(raw) < 16 or raw[:8].hex() != EVENT_TAG:
                    continue
                ed = raw[8:16].hex()
                events[ed] += 1
                bodies.setdefault(ed, Counter())[len(raw) - 16] += 1
        time.sleep(0.12)

    print(f"\nsampled {len(sigs)} sigs -> {ok} succeeded, {fail} failed")
    print(f"\nself-CPI events emitted by the CURRENT program version")
    print("-" * 62)
    for ed, c in events.most_common():
        name = table.get(ed)
        mark = "RESOLVED" if name else "UNKNOWN "
        sizes = ", ".join(f"{k}B x{v}" for k, v in bodies[ed].most_common(3))
        print(f"  {mark} {ed} n={c:<4} {name or '(unresolved)':<34} body: {sizes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
