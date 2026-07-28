#!/usr/bin/env python3
"""B2c - non-SOL quote-pair verification.

B2a's T1/T2 and B2b's official formulas were all tested against the SOL fields
(`sol_amount` / `virtual_sol_reserves`). TradeEvent also carries `quote_mint`,
`quote_amount`, `virtual_quote_reserves`, `real_quote_reserves` for non-SOL pairs, and
none of those paths has been verified. This closes that gap - or reports honestly that
non-SOL pairs are too rare to sample this way.

Tests, all exact-equality (no tolerance):
  T1q  reserve continuity on quote fields
  T3q  official buy arithmetic on quote fields:
         exact-input  : tokens_out = floor((net_quote - 1) * v_tokens / (v_quote + net_quote - 1))
         legacy `buy` : quote_in   = ceil(token_amount * v_quote / (v_tokens - token_amount))
         sell         : quote_out  = v_quote - ceil(k / (v_tokens + tokens_in))

Read-only. No keys, no signing, no transactions.

Usage: b2c_quote_pair_check.py <pinned-idl.json> [num_blocks]
"""
import hashlib
import json
import struct
import sys
import time
import urllib.request
from collections import Counter, defaultdict

RPC = "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EVENT_TAG = bytes.fromhex("e445a52e51cb9a1d")
NATIVE_SOL_SENTINEL = "11111111111111111111111111111111"

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


def rpc(method, params, retries=5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                o = json.loads(r.read())
            if "error" in o:
                if a < retries - 1:
                    time.sleep(2.0 * (a + 1)); continue
                return {"__error__": o["error"]}
            return o["result"]
        except Exception as e:  # noqa: BLE001
            if a == retries - 1:
                return {"__error__": str(e)}
            time.sleep(2.0 * (a + 1))
    return {"__error__": "retries"}


def ceil_div(a, b):
    return -(-a // b)


def main():
    idl = json.load(open(sys.argv[1]))
    nblocks = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    types = {t["name"]: t for t in idl["types"]}
    te = hashlib.sha256(b"event:TradeEvent").digest()[:8]

    tip = rpc("getSlot", [{"commitment": "finalized"}])
    start = tip - nblocks - 2
    by_mint = defaultdict(list)
    quote_mints = Counter()
    total = 0

    print(f"scanning {nblocks} blocks from slot {start} for non-SOL quote pairs\n")
    for slot in range(start, start + nblocks):
        blk = rpc("getBlock", [slot, {"encoding": "jsonParsed", "transactionDetails": "full",
                                      "rewards": False, "maxSupportedTransactionVersion": 0}])
        if isinstance(blk, dict) and "__error__" in blk or not blk:
            continue
        for tx_index, tx in enumerate(blk.get("transactions", [])):
            if (tx.get("meta") or {}).get("err"):
                continue
            for g in (tx.get("meta") or {}).get("innerInstructions") or []:
                for inner_ix, ix in enumerate(g.get("instructions", [])):
                    if ix.get("programId") != PUMP or not ix.get("data"):
                        continue
                    raw = b58decode(ix["data"])
                    if len(raw) < 16 or raw[:8] != EVENT_TAG or raw[8:16] != te:
                        continue
                    cur = Cursor(raw[16:])
                    try:
                        ev = read_struct(cur, types["TradeEvent"], types)
                    except Exception:  # noqa: BLE001
                        continue
                    if cur.remaining:
                        continue
                    ev["_order"] = (slot, tx_index, g.get("index", 0), inner_ix)
                    quote_mints[ev["quote_mint"]] += 1
                    by_mint[(ev["mint"], ev["quote_mint"])].append(ev)
                    total += 1
        time.sleep(0.15)

    print(f"{total} TradeEvents decoded\n-- quote_mint distribution --")
    for qm, c in quote_mints.most_common():
        tag = "native SOL sentinel" if qm == NATIVE_SOL_SENTINEL else "NON-SOL"
        print(f"  {qm}  n={c:<5} {tag}")

    non_sol = {k: v for k, v in by_mint.items() if k[1] != NATIVE_SOL_SENTINEL}
    n_non_sol_events = sum(len(v) for v in non_sol.values())
    print(f"\nnon-SOL events: {n_non_sol_events} across {len(non_sol)} (mint, quote) pairs")
    # Consistency check available even on single events: for SOL pairs the quote and sol
    # fields should mirror each other. Verify that, since it validates the field mapping.
    mirror = Counter()
    for (mint, qm), evs in by_mint.items():
        if qm != NATIVE_SOL_SENTINEL:
            continue
        for e in evs:
            mirror["amount_match" if e["sol_amount"] == e["quote_amount"] else "amount_DIFFER"] += 1
            mirror["vres_match" if e["virtual_sol_reserves"] == e["virtual_quote_reserves"]
                   else "vres_DIFFER"] += 1
            mirror["rres_match" if e["real_sol_reserves"] == e["real_quote_reserves"]
                   else "rres_DIFFER"] += 1
    print(f"\n-- SOL-pair field mirroring (sol_* vs quote_*) --")
    for k, v in sorted(mirror.items()):
        print(f"  {k:<16} {v}")

    if not n_non_sol_events:
        print("\nRESULT: no non-SOL quote pairs observed in this sample.")
        print("The quote_* code paths remain UNVERIFIED. This is a negative sampling result,")
        print("not evidence that non-SOL pairs do not exist or that the fields are unused.")
        return 2

    t1 = Counter()
    t3 = Counter()
    for (mint, qm), evs in sorted(non_sol.items(), key=lambda kv: -len(kv[1])):
        evs.sort(key=lambda e: e["_order"])
        for a, b in zip(evs, evs[1:]):
            vq0, vt0 = a["virtual_quote_reserves"], a["virtual_token_reserves"]
            vq1, vt1 = b["virtual_quote_reserves"], b["virtual_token_reserves"]
            qa, ta = b["quote_amount"], b["token_amount"]
            ok = ((vq0 + qa == vq1 and vt0 - ta == vt1) if b["is_buy"]
                  else (vq0 - qa == vq1 and vt0 + ta == vt1))
            t1[f"{'exact' if ok else 'BREAK'}:{'mayhem' if b['mayhem_mode'] else 'normal'}"] += 1
            if not ok:
                print(f"  T1q BREAK {mint[:10]}/{qm[:10]} {b['ix_name']} "
                      f"vq {vq0}->{vq1} (amt {qa})  vt {vt0}->{vt1} (amt {ta})")
                continue
            name = b["ix_name"]
            if b["is_buy"]:
                if name.startswith("buy_exact"):
                    net = qa
                    pred = ((net - 1) * vt0) // (vq0 + net - 1) if (vq0 + net - 1) else None
                    got = ta
                else:
                    pred = (ceil_div(ta * vq0, vt0 - ta)) if (vt0 - ta) else None
                    got = qa
            else:
                k = vq0 * vt0
                pred = vq0 - ceil_div(k, vt0 + ta) if (vt0 + ta) else None
                got = qa
            if pred is None:
                t3[f"skip_zero_denominator:{name}"] += 1
            elif pred == got:
                t3[f"exact:{name}"] += 1
            else:
                t3[f"MISMATCH:{name}"] += 1
                print(f"  T3q MISMATCH {mint[:10]} {name}: got {got}, pred {pred}, "
                      f"residual {got - pred}")

    print(f"\n{'=' * 66}")
    print(f"T1q quote reserve continuity : {dict(t1)}")
    print(f"T3q quote arithmetic         : {dict(t3)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
