#!/usr/bin/env python3
"""B0e - IDL-driven Borsh decode of live Pump TradeEvents, with exact-consumption proof.

Decodes real mainnet self-CPI event payloads against the pinned official IDL and asserts
that parsing consumes the buffer EXACTLY. A trailing byte or a short read is a failure,
not a warning: per DECISIONS.md, deterministic quantities reconcile exactly or not at all.

Read-only. No keys, no signing, no transactions.

Usage: b0e_tradeevent_decode.py <path-to-pinned-pump.json> [sample_size]
"""
import hashlib
import json
import struct
import sys
import time
import urllib.request
from collections import Counter

RPC = "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EVENT_TAG = bytes.fromhex("e445a52e51cb9a1d")

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {c: i for i, c in enumerate(B58)}


def b58decode(s):
    n = 0
    for ch in s:
        n = n * 58 + B58_MAP[ch]
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + body


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
            raise ValueError(f"short read: need {n} at {self.pos}, have {len(self.buf) - self.pos}")
        out = self.buf[self.pos:self.pos + n]
        self.pos += n
        return out

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
            ln = struct.unpack("<I", cur.take(4))[0]
            return cur.take(ln).decode("utf-8", "replace")
        raise ValueError(f"unsupported primitive {ty!r}")
    if "vec" in ty:
        ln = struct.unpack("<I", cur.take(4))[0]
        return [read_type(cur, ty["vec"], types) for _ in range(ln)]
    if "option" in ty:
        return read_type(cur, ty["option"], types) if cur.take(1)[0] else None
    if "array" in ty:
        inner, ln = ty["array"]
        return [read_type(cur, inner, types) for _ in range(ln)]
    if "defined" in ty:
        name = ty["defined"]["name"] if isinstance(ty["defined"], dict) else ty["defined"]
        return read_struct(cur, types[name], types)
    raise ValueError(f"unsupported type {ty!r}")


def read_struct(cur, tdef, types):
    kind = tdef["type"]
    if kind.get("kind") != "struct":
        raise ValueError(f"non-struct type {tdef['name']}")
    return {f["name"]: read_type(cur, f["type"], types) for f in kind.get("fields", [])}


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


def ceil_div(a, b):
    return -(-a // b)


def check_fee_invariant(ev, sig, tally):
    """Exact integer test: is fee == ceil(quote_amount * bps / 10000)?

    Deterministic economics reconcile exactly or not at all (DECISIONS.md). Any
    mismatch is reported with its residual rather than tolerated.
    """
    for amount_field, bps_field, fee_field in (
        ("quote_amount", "fee_basis_points", "fee"),
        ("quote_amount", "creator_fee_basis_points", "creator_fee"),
    ):
        amt, bps, fee = ev.get(amount_field), ev.get(bps_field), ev.get(fee_field)
        if amt is None or bps is None or fee is None:
            tally[f"{fee_field}:missing_field"] += 1
            continue
        if bps == 0:
            tally[f"{fee_field}:zero_bps_fee_{'zero' if fee == 0 else 'NONZERO'}"] += 1
            continue
        expect_ceil = ceil_div(amt * bps, 10000)
        expect_floor = (amt * bps) // 10000
        if fee == expect_ceil:
            tally[f"{fee_field}:exact_ceil"] += 1
        elif fee == expect_floor:
            tally[f"{fee_field}:exact_floor"] += 1
        else:
            tally[f"{fee_field}:MISMATCH"] += 1
            print(f"  FEE MISMATCH {sig[:20]} {fee_field}: got {fee}, "
                  f"ceil {expect_ceil}, floor {expect_floor}, residual {fee - expect_ceil}")


def main():
    idl_path = sys.argv[1]
    sample = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    raw_idl = open(idl_path, "rb").read()
    print(f"IDL: {idl_path}")
    print(f"IDL sha256: {hashlib.sha256(raw_idl).hexdigest()}")
    idl = json.loads(raw_idl)
    types = {t["name"]: t for t in idl["types"]}
    te_disc = hashlib.sha256(b"event:TradeEvent").digest()[:8]
    print(f"TradeEvent discriminator (derived): {te_disc.hex()}")
    print(f"TradeEvent fields in IDL: {len(types['TradeEvent']['type']['fields'])}\n")

    sigs = rpc("getSignaturesForAddress", [PUMP, {"limit": sample, "commitment": "finalized"}])
    if isinstance(sigs, dict) and "__error__" in sigs:
        print(f"ERROR: {sigs['__error__']}"); return 1

    exact = short = trailing = failed_decode = 0
    ok_tx = 0
    ix_names = Counter()
    fee_check = Counter()
    body_size_by_ixname = {}
    samples = []
    for s in sigs:
        tx = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed",
                                                    "maxSupportedTransactionVersion": 0,
                                                    "commitment": "finalized"}])
        if isinstance(tx, dict) and "__error__" in tx or not tx:
            continue
        meta = tx.get("meta") or {}
        if meta.get("err"):
            continue
        ok_tx += 1
        for g in meta.get("innerInstructions") or []:
            for ix in g.get("instructions", []):
                if ix.get("programId") != PUMP or not ix.get("data"):
                    continue
                raw = b58decode(ix["data"])
                if len(raw) < 16 or raw[:8] != EVENT_TAG or raw[8:16] != te_disc:
                    continue
                cur = Cursor(raw[16:])
                try:
                    ev = read_struct(cur, types["TradeEvent"], types)
                except Exception as e:  # noqa: BLE001
                    failed_decode += 1
                    print(f"  DECODE FAILURE {s['signature'][:20]}: {e}")
                    continue
                if cur.remaining == 0:
                    exact += 1
                    ix_names[ev["ix_name"]] += 1
                    check_fee_invariant(ev, s["signature"], fee_check)
                    body_size_by_ixname.setdefault(ev["ix_name"], set()).add(len(raw))
                    if len(samples) < 3:
                        samples.append((s["signature"], len(raw), ev))
                else:
                    trailing += 1
                    print(f"  TRAILING {cur.remaining}B in {s['signature'][:20]}")
        time.sleep(0.12)

    print(f"\n{'=' * 68}\nsuccessful txs scanned: {ok_tx}")
    print(f"TradeEvents decoded EXACTLY (zero bytes left over): {exact}")
    print(f"  short reads: {short}   trailing bytes: {trailing}   decode failures: {failed_decode}")
    print(f"\nix_name distribution (from inside the event): {dict(ix_names)}")
    print("\n-- exact integer fee invariant  fee == ceil(quote_amount*bps/10000) --")
    for k, v in sorted(fee_check.items()):
        print(f"    {k:<42} {v}")
    print("\n-- payload size by ix_name (explains the size variation) --")
    for k, v in sorted(body_size_by_ixname.items()):
        print(f"    {k:<22} len(ix_name)={len(k):<3} sizes={sorted(v)}")

    for sig, size, ev in samples:
        print(f"\n--- {sig[:32]}...  payload {size}B  ix_name={ev['ix_name']!r} ---")
        for k in ("mint", "is_buy", "sol_amount", "token_amount",
                  "virtual_sol_reserves", "virtual_token_reserves",
                  "real_sol_reserves", "real_token_reserves",
                  "fee_basis_points", "fee", "creator_fee_basis_points", "creator_fee",
                  "mayhem_mode", "quote_mint", "quote_amount"):
            if k in ev:
                print(f"    {k:<26} {ev[k]}")
        print(f"    shareholders               {len(ev.get('shareholders') or [])} entry(ies)")
    return 0 if (trailing == 0 and failed_decode == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
