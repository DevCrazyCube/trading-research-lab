#!/usr/bin/env python3
"""B2a - exact integer curve-chain verification from consecutive TradeEvents.

The B2 precondition. Two tests, both EXACT (no tolerance, per DECISIONS.md):

  T1 reserve continuity - do consecutive events for one mint chain exactly?
       buy : v_sol[i] + sol_amount[i+1] == v_sol[i+1]
             v_tok[i] - token_amount[i+1] == v_tok[i+1]
       sell: mirrored
     A break means either a missed event, a non-trade state change, or a wrong field.

  T2 constant-product quote - given pre-trade reserves and the input amount, does
     the exact integer formula reproduce the observed output byte-for-byte?
       buy : tok_out = v_tok - floor(k / (v_sol + sol_in)),  k = v_sol * v_tok
       sell: sol_out = v_sol - floor(k / (v_tok + tok_in))
     Both floor and ceil variants are tried; the winning convention is reported.

Read-only. No keys, no signing, no transactions.

Usage: b2a_curve_chain_check.py <pinned-idl.json> [num_blocks]
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
            raise ValueError(f"short read at {self.pos}")
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
        raise ValueError(f"prim {ty}")
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
    raise ValueError(f"type {ty}")


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
                    time.sleep(2.5 * (a + 1)); continue
                return {"__error__": o["error"]}
            return o["result"]
        except Exception as e:  # noqa: BLE001
            if a == retries - 1:
                return {"__error__": str(e)}
            time.sleep(2.5 * (a + 1))
    return {"__error__": "retries"}


def collect(slot, types, te_disc, out):
    blk = rpc("getBlock", [slot, {"encoding": "jsonParsed", "transactionDetails": "full",
                                  "rewards": False, "maxSupportedTransactionVersion": 0}])
    if isinstance(blk, dict) and "__error__" in blk:
        print(f"  slot {slot}: FAIL {str(blk['__error__'])[:80]}")
        return 0
    if not blk:
        return 0
    n = 0
    for tx_index, tx in enumerate(blk.get("transactions", [])):
        if (tx.get("meta") or {}).get("err"):
            continue
        for g in (tx.get("meta") or {}).get("innerInstructions") or []:
            for inner_ix, ix in enumerate(g.get("instructions", [])):
                if ix.get("programId") != PUMP or not ix.get("data"):
                    continue
                raw = b58decode(ix["data"])
                if len(raw) < 16 or raw[:8] != EVENT_TAG or raw[8:16] != te_disc:
                    continue
                cur = Cursor(raw[16:])
                try:
                    ev = read_struct(cur, types["TradeEvent"], types)
                except Exception:  # noqa: BLE001
                    continue
                if cur.remaining:
                    continue
                ev["_order"] = (slot, tx_index, g.get("index", 0), inner_ix)
                out[ev["mint"]].append(ev)
                n += 1
    return n


def main():
    idl = json.load(open(sys.argv[1]))
    nblocks = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    types = {t["name"]: t for t in idl["types"]}
    te_disc = hashlib.sha256(b"event:TradeEvent").digest()[:8]

    tip = rpc("getSlot", [{"commitment": "finalized"}])
    start = tip - nblocks - 2
    print(f"collecting TradeEvents from {nblocks} consecutive blocks starting at slot {start}\n")
    by_mint = defaultdict(list)
    total = 0
    for s in range(start, start + nblocks):
        got = collect(s, types, te_disc, by_mint)
        total += got
        print(f"  slot {s}: {got} TradeEvents")
        time.sleep(0.2)

    print(f"\ntotal {total} events across {len(by_mint)} mints")
    chains = sorted(by_mint.items(), key=lambda kv: -len(kv[1]))
    chains = [(m, sorted(evs, key=lambda e: e["_order"])) for m, evs in chains if len(evs) >= 2]
    if not chains:
        print("no mint had 2+ events; widen the block range")
        return 1
    print(f"{len(chains)} mints have a chain of 2+ events; longest = {len(chains[0][1])}\n")

    t1 = Counter()
    t2 = Counter()
    t3 = Counter()
    residuals = []
    solved = []
    shown = 0
    for mint, evs in chains:
        for a, b in zip(evs, evs[1:]):
            vs0, vt0 = a["virtual_sol_reserves"], a["virtual_token_reserves"]
            vs1, vt1 = b["virtual_sol_reserves"], b["virtual_token_reserves"]
            amt_sol, amt_tok = b["sol_amount"], b["token_amount"]
            # ---- T1 reserve continuity ----
            if b["is_buy"]:
                ok = (vs0 + amt_sol == vs1) and (vt0 - amt_tok == vt1)
            else:
                ok = (vs0 - amt_sol == vs1) and (vt0 + amt_tok == vt1)
            tag = f"{'mayhem' if b['mayhem_mode'] else 'normal'}/{b['ix_name']}"
            t1[f"{'exact' if ok else 'BREAK'}:{tag}"] += 1
            if not ok:
                sol_ok = (vs0 + amt_sol == vs1) if b["is_buy"] else (vs0 - amt_sol == vs1)
                tok_ok = (vt0 - amt_tok == vt1) if b["is_buy"] else (vt0 + amt_tok == vt1)
                t1[f"  side_sol_ok={sol_ok}_tok_ok={tok_ok}"] += 1
                if shown < 4:
                    shown += 1
                    print(f"  T1 BREAK {mint[:12]} {tag} mayhem={b['mayhem_mode']}\n"
                          f"     v_sol {vs0} -> {vs1} (delta {vs1 - vs0}, sol_amount {amt_sol}, sol_ok={sol_ok})\n"
                          f"     v_tok {vt0} -> {vt1} (delta {vt1 - vt0}, token_amount {amt_tok}, tok_ok={tok_ok})")
                continue
            # ---- T2 constant product, only where T1 held (pre-state is trustworthy) ----
            k = vs0 * vt0
            if (vs0 + amt_sol) == 0 or (vt0 + amt_tok) == 0:
                t2["skipped_zero_denominator"] += 1
                continue
            if b["is_buy"]:
                got, pred_f = amt_tok, vt0 - (k // (vs0 + amt_sol))
                pred_c = vt0 - -(-k // (vs0 + amt_sol))
            else:
                got, pred_f = amt_sol, vs0 - (k // (vt0 + amt_tok))
                pred_c = vs0 - -(-k // (vt0 + amt_tok))
            if got == pred_f:
                t2[f"exact_floor_k:{b['ix_name']}"] += 1
            elif got == pred_c:
                t2[f"exact_ceil_k:{b['ix_name']}"] += 1
            else:
                t2[f"MISMATCH:{b['ix_name']}"] += 1
                resid = got - pred_f
                residuals.append((abs(resid) / got if got else 0, resid, b["ix_name"]))
                # Solve for the effective input that reproduces the observed output exactly.
                if b["is_buy"]:
                    lo, hi = 0, amt_sol * 2
                    while lo < hi:
                        mid = (lo + hi) // 2
                        out = vt0 - (k // (vs0 + mid)) if (vs0 + mid) else 0
                        if out < got: lo = mid + 1
                        else: hi = mid
                    s_eff = lo
                    out_chk = vt0 - (k // (vs0 + s_eff)) if (vs0 + s_eff) else None
                    deficit = amt_sol - s_eff
                    solved.append({
                        "ix": b["ix_name"], "sol_amount": amt_sol, "s_eff": s_eff,
                        "deficit": deficit,
                        "deficit_rel": deficit / amt_sol if amt_sol else None,
                        "fee": b["fee"], "creator_fee": b["creator_fee"],
                        "fee_bps": b["fee_basis_points"], "cf_bps": b["creator_fee_basis_points"],
                        "exact_after_solve": out_chk == got,
                    })

            # ---- T3 official IDL buy formulas (kept separate from naive T2) ----
            # Exact-input instructions quote token output directly. Event sol_amount is the
            # reserve-changing net input; spendable input and fees are separate event fields.
            if b["is_buy"] and b["ix_name"] in (
                "buy_exact_sol_in", "buy_exact_quote_in", "buy_exact_quote_in_v2"
            ):
                if amt_sol <= 0:
                    t3[f"skipped_nonpositive_input:{b['ix_name']}"] += 1
                else:
                    predicted_tokens = ((amt_sol - 1) * vt0) // (vs0 + amt_sol - 1)
                    t3[f"{'exact' if predicted_tokens == amt_tok else 'MISMATCH'}:exact_input:{b['ix_name']}"] += 1
            # Exact-token instructions solve the reverse quote. ceil(a/b) is -(-a//b).
            elif b["is_buy"] and b["ix_name"] in ("buy", "buy_v2"):
                denominator = vt0 - amt_tok
                if denominator <= 0:
                    t3[f"skipped_nonpositive_denominator:{b['ix_name']}"] += 1
                else:
                    numerator = amt_tok * vs0
                    candidates = {
                        "ceil_ratio": -(-numerator // denominator),
                        "ceil_ratio_plus_one": -(-numerator // denominator) + 1,
                        "floor_ratio_plus_one": numerator // denominator + 1,
                    }
                    matches = [name for name, value in candidates.items() if value == amt_sol]
                    t3[f"{'+'.join(matches) if matches else 'MISMATCH'}:exact_tokens:{b['ix_name']}"] += 1

    print(f"\n{'=' * 68}")
    print("T1 reserve continuity :")
    for k, v in sorted(t1.items()):
        print(f"    {k:<42} {v}")
    print("T2 constant product   :")
    for k, v in sorted(t2.items()):
        print(f"    {k:<42} {v}")
    print("T3 official IDL buy formulas:")
    for k, v in sorted(t3.items()):
        print(f"    {k:<58} {v}")
    if residuals:
        residuals.sort()
        rel = [r[0] for r in residuals]
        print(f"\n  T2 mismatch relative residuals: n={len(rel)} "
              f"min={rel[0]:.3e} median={rel[len(rel)//2]:.3e} max={rel[-1]:.3e}")
        print("  smallest 3 absolute residuals:", [r[1] for r in residuals[:3]])
    if solved:
        print(f"\n  -- solving for effective buy input (n={len(solved)}) --")
        print(f"  reproduced exactly after solve: {sum(1 for x in solved if x['exact_after_solve'])}/{len(solved)}")
        for x in solved[:8]:
            tot_fee = x["fee"] + x["creator_fee"]
            print(f"    {x['ix']:<20} sol_amount={x['sol_amount']:<14} s_eff={x['s_eff']:<14} "
                  f"deficit={x['deficit']:<10} rel={x['deficit_rel']:.3e}")
            print(f"      {'':<20} fee={x['fee']} + creator_fee={x['creator_fee']} = {tot_fee}  "
                  f"bps={x['fee_bps']}/{x['cf_bps']}  deficit==fees? {x['deficit']==tot_fee}  "
                  f"deficit==fee? {x['deficit']==x['fee']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
