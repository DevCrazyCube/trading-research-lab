#!/usr/bin/env python3
"""B7a - lifecycle scan: Mayhem mutability, completion vs migration, launch attributes.

Answers the open questions in docs/DEFINITIONS.md against live chain data:
  Q1 does `CompleteEvent` co-occur with `CompletePumpAmmMigrationEvent`, or can a token
     sit completed-but-not-migrated (state T1b)?
  Q2 do the admin instructions that could mutate a live curve actually fire?
  Q3 what are launch attributes (is_mayhem_mode, quote_mint) at CreateEvent time?

RPC endpoint comes only from an environment variable and is never printed or persisted.
Read-only. No keys used for signing, no transactions.

Usage: b7a_lifecycle_scan.py [num_blocks]
"""
import base64
import concurrent.futures as cf
import hashlib
import json
import os
import struct
import sys
import time
import urllib.request
from collections import Counter

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EVENT_TAG = bytes.fromhex("e445a52e51cb9a1d")
URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {c: i for i, c in enumerate(B58)}


def b58decode(s):
    n = 0
    for ch in s:
        n = n * 58 + B58_MAP[ch]
    return b"\0" * (len(s) - len(s.lstrip("1"))) + (n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b"")


def b58encode(b):
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + out


class Cursor:
    def __init__(self, buf):
        self.buf, self.pos = buf, 0

    def take(self, n):
        if self.pos + n > len(self.buf):
            raise ValueError("short read")
        o = self.buf[self.pos:self.pos + n]
        self.pos += n
        return o

    @property
    def remaining(self):
        return len(self.buf) - self.pos


PRIMS = {
    "u8": (1, lambda b: b[0]), "i8": (1, lambda b: struct.unpack("<b", b)[0]),
    "u16": (2, lambda b: struct.unpack("<H", b)[0]), "i16": (2, lambda b: struct.unpack("<h", b)[0]),
    "u32": (4, lambda b: struct.unpack("<I", b)[0]), "i32": (4, lambda b: struct.unpack("<i", b)[0]),
    "u64": (8, lambda b: struct.unpack("<Q", b)[0]), "i64": (8, lambda b: struct.unpack("<q", b)[0]),
    "u128": (16, lambda b: int.from_bytes(b, "little")),
    "i128": (16, lambda b: int.from_bytes(b, "little", signed=True)),
    "bool": (1, lambda b: bool(b[0])), "pubkey": (32, b58encode),
}


def read_type(cur, ty, types):
    if isinstance(ty, str):
        if ty in PRIMS:
            n, fn = PRIMS[ty]
            return fn(cur.take(n))
        if ty == "string":
            return cur.take(struct.unpack("<I", cur.take(4))[0]).decode("utf-8", "replace")
        raise ValueError(ty)
    if "vec" in ty:
        return [read_type(cur, ty["vec"], types) for _ in range(struct.unpack("<I", cur.take(4))[0])]
    if "option" in ty:
        return read_type(cur, ty["option"], types) if cur.take(1)[0] else None
    if "array" in ty:
        inner, ln = ty["array"]
        return [read_type(cur, inner, types) for _ in range(ln)]
    if "defined" in ty:
        nm = ty["defined"]["name"] if isinstance(ty["defined"], dict) else ty["defined"]
        return read_struct(cur, types[nm], types)
    raise ValueError(ty)


def read_struct(cur, tdef, types):
    return {f["name"]: read_type(cur, f["type"], types) for f in tdef["type"]["fields"]}


def rpc(method, params, retries=4):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                o = json.loads(r.read())
            if "error" in o:
                if a < retries - 1:
                    time.sleep(1.0 * (a + 1)); continue
                return None
            return o["result"]
        except Exception:  # noqa: BLE001
            if a == retries - 1:
                return None
            time.sleep(1.0 * (a + 1))
    return None


def main():
    nblocks = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    idl = json.load(open("research/pump_idl_9c82f61.json"))
    types = {t["name"]: t for t in idl["types"]}
    ixname = {bytes(i["discriminator"]).hex(): i["name"] for i in idl["instructions"]}
    evname = {hashlib.sha256(f"event:{e['name']}".encode()).digest()[:8].hex(): e["name"]
              for e in idl["events"]}
    watch = {"toggle_mayhem_mode", "set_mayhem_virtual_params", "set_virtual_quote_reserves",
             "set_params", "migrate", "migrate_v2", "toggle_cashback_enabled", "toggle_create_v2"}

    tip = rpc("getSlot", [{"commitment": "finalized"}])
    slots = list(range(tip - nblocks - 2, tip - 2))
    print(f"scanning {len(slots)} blocks from slot {slots[0]} via {URL.split('//')[1].split('/')[0]}\n")

    outer_ix = Counter()
    events = Counter()
    watch_hits = []
    complete_txs = []          # (sig, has_migration_in_same_tx)
    launches = []
    got = 0

    def fetch(s):
        return s, rpc("getBlock", [s, {"encoding": "jsonParsed", "transactionDetails": "full",
                                       "rewards": False, "maxSupportedTransactionVersion": 0}])

    with cf.ThreadPoolExecutor(4) as ex:
        for slot, blk in ex.map(fetch, slots):
            if not blk:
                continue
            got += 1
            for tx in blk.get("transactions", []):
                meta = tx.get("meta") or {}
                if meta.get("err"):
                    continue
                sig = tx["transaction"]["signatures"][0]
                for ix in tx["transaction"]["message"].get("instructions", []):
                    if ix.get("programId") != PUMP or not ix.get("data"):
                        continue
                    d = b58decode(ix["data"])[:8].hex()
                    nm = ixname.get(d, f"unknown:{d}")
                    outer_ix[nm] += 1
                    if nm in watch:
                        watch_hits.append((slot, nm, sig))
                names_here = set()
                decoded_here = {}
                for g in meta.get("innerInstructions") or []:
                    for ix in g.get("instructions", []):
                        if ix.get("programId") != PUMP or not ix.get("data"):
                            continue
                        raw = b58decode(ix["data"])
                        if len(raw) >= 16 and raw[:8] == EVENT_TAG:
                            en = evname.get(raw[8:16].hex())
                            if not en:
                                continue
                            events[en] += 1
                            names_here.add(en)
                            if en in ("CompleteEvent", "CreateEvent",
                                      "CompletePumpAmmMigrationEvent"):
                                try:
                                    cur = Cursor(raw[16:])
                                    decoded_here[en] = read_struct(cur, types[en], types)
                                except Exception:  # noqa: BLE001
                                    pass
                        else:
                            d = raw[:8].hex()
                            nm = ixname.get(d)
                            if nm in watch:
                                watch_hits.append((slot, f"{nm} (inner)", sig))
                if "CompleteEvent" in names_here:
                    complete_txs.append((sig, "CompletePumpAmmMigrationEvent" in names_here,
                                         decoded_here.get("CompleteEvent")))
                if "CreateEvent" in decoded_here:
                    launches.append(decoded_here["CreateEvent"])

    print(f"blocks retrieved: {got}/{len(slots)}\n")
    print("outer Pump instructions:")
    for n, c in outer_ix.most_common(14):
        print(f"  {n:<34} {c}")
    print("\nevents emitted:")
    for n, c in events.most_common(14):
        print(f"  {n:<34} {c}")

    print(f"\n--- Q2: curve-mutating / admin instructions observed ---")
    if watch_hits:
        for slot, nm, sig in watch_hits[:20]:
            print(f"  slot {slot}  {nm:<34} {sig[:24]}...")
        print(f"  total: {len(watch_hits)}")
    else:
        print(f"  NONE observed in {got} blocks")

    print(f"\n--- Q1: CompleteEvent -> migration co-occurrence ---")
    if complete_txs:
        same = sum(1 for _, m, _ in complete_txs if m)
        print(f"  CompleteEvent transactions: {len(complete_txs)}")
        print(f"    with CompletePumpAmmMigrationEvent in the SAME transaction: {same}")
        print(f"    without (candidate T1b, completed-not-migrated):           {len(complete_txs)-same}")
        for sig, m, ev in complete_txs[:5]:
            mint = (ev or {}).get("mint", "?")
            print(f"      {sig[:22]}...  migrated_same_tx={m}  mint={mint}")
    else:
        print(f"  no CompleteEvent in {got} blocks")

    print(f"\n--- Q3: launch attributes at CreateEvent ---")
    if launches:
        mh = Counter(l["is_mayhem_mode"] for l in launches)
        qm = Counter(l["quote_mint"] for l in launches)
        cb = Counter(l.get("is_cashback_enabled") for l in launches)
        print(f"  launches observed: {len(launches)}  ({len(launches)/max(got,1):.2f}/block)")
        print(f"    is_mayhem_mode      : {dict(mh)}")
        print(f"    is_cashback_enabled : {dict(cb)}")
        print(f"    quote_mint          : {dict(qm)}")
    else:
        print(f"  no CreateEvent in {got} blocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
