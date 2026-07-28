#!/usr/bin/env python3
"""B7l - close B7k's C1 gap: test decoded pubkey field IDENTITY, not membership.

B7k's C1 proved a decoded pubkey is *one of* the accounts a transaction touched. That is
membership, and B7k stated plainly that **two transposed pubkey fields would still pass**.

Anchor declares a fixed account ORDER per instruction, and `jsonParsed` returns the outer
instruction's `accounts` as an ordered list. So each decoded pubkey field can be compared against
the account at its declared INDEX. `mint` sits at index 2 and `bonding_curve` at index 3 in
buy/sell, so a transposition is positionally detectable - which is exactly the power C1 lacked.

Entirely offline. Zero RPC. The B7j database is opened strictly read-only; it holds the primary
evidence behind the B7j PASS and is owned elsewhere.

Usage: b7l_field_identity.py [--database PATH] [--idl PATH] [--limit N]
"""
import argparse
import hashlib
import json
import sqlite3
import zlib
from collections import Counter

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
NATIVE_SOL_SENTINEL = "11111111111111111111111111111111"          # System Program
WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"  # canonical wSOL SPL mint
EVENT_TAG = bytes.fromhex("e445a52e51cb9a1d")


def values_equivalent(field, decoded, account):
    """Frozen rule S2: exact equality, plus ONE directional exception for `quote_mint`.

    An event's `quote_mint` carries the native-SOL sentinel; the instruction account slot must
    hold a real SPL mint, so it carries wrapped SOL. Both denote SOL. The exception admits
    exactly that ordered pair, so a decoder emitting wSOL where the sentinel belongs - or any
    third value - still fails. A non-SOL quote mint must match exactly.
    """
    if decoded == account:
        return True
    return (field == "quote_mint"
            and decoded == NATIVE_SOL_SENTINEL
            and account == WRAPPED_SOL_MINT)

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


import struct  # noqa: E402


class Cursor:
    def __init__(self, buf):
        self.buf, self.pos = buf, 0

    def take(self, n):
        if self.pos + n > len(self.buf):
            raise ValueError("short read")
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


def load_idl(path):
    raw = open(path, "rb").read()
    idl = json.loads(raw)
    types = {t["name"]: t for t in idl["types"]}
    ix_accounts = {i["name"]: [a["name"] for a in i.get("accounts", [])] for i in idl["instructions"]}
    disc_to_ix = {bytes(i["discriminator"]).hex(): i["name"] for i in idl["instructions"]}
    ev_disc = {hashlib.sha256(f"event:{e['name']}".encode()).digest()[:8]: e["name"]
               for e in idl["events"]}
    return types, ix_accounts, disc_to_ix, ev_disc, hashlib.sha256(raw).hexdigest()


def pubkey_fields(types, event_name):
    return [f["name"] for f in types[event_name]["type"]["fields"] if f["type"] == "pubkey"]


def check_transaction(tx, types, ix_accounts, disc_to_ix, ev_disc, transpose=None):
    """Positional identity check for one transaction.

    `transpose` is the negative control: a (field_a, field_b) pair swapped after decoding, to
    prove the check can actually detect a transposition.
    """
    results, unchecked, errors = Counter(), Counter(), []
    meta = tx.get("meta") or {}
    if meta.get("err") is not None:
        return results, unchecked, errors
    message = tx["transaction"]["message"]
    outer = list(message.get("instructions", []))

    # Map each inner-instruction group index to its outer Pump instruction.
    for group in meta.get("innerInstructions") or []:
        idx = group.get("index")
        if idx is None or idx >= len(outer):
            continue
        parent = outer[idx]
        if parent.get("programId") != PUMP or not parent.get("data"):
            continue
        ix_name = disc_to_ix.get(b58decode(parent["data"])[:8].hex())
        if ix_name is None or ix_name not in ix_accounts:
            continue
        account_order = ix_accounts[ix_name]
        accounts = parent.get("accounts", [])

        for ins in group.get("instructions", []):
            if ins.get("programId") != PUMP or not ins.get("data"):
                continue
            raw = b58decode(ins["data"])
            if len(raw) < 16 or raw[:8] != EVENT_TAG:
                continue
            name = ev_disc.get(raw[8:16])
            if name is None or name not in types:
                continue
            try:
                cur = Cursor(raw[16:])
                fields = read_struct(cur, types[name], types)
                if cur.remaining:
                    raise ValueError(f"{cur.remaining} trailing bytes")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                continue

            if transpose:
                a, b = transpose
                if a in fields and b in fields:
                    fields[a], fields[b] = fields[b], fields[a]

            for field in pubkey_fields(types, name):
                if field not in account_order:
                    unchecked[f"{name}.{field}"] += 1
                    continue
                position = account_order.index(field)
                if position >= len(accounts):
                    unchecked[f"{name}.{field}(position>{len(accounts)})"] += 1
                    continue
                expected = accounts[position]
                got = fields.get(field)
                key = f"{name}.{field}"
                ok = values_equivalent(field, got, expected)
                tag = "MATCH"
                if ok and got != expected:
                    tag = "MATCH_SOL_EQUIV"      # counted as a pass, reported distinctly
                elif not ok:
                    tag = "MISMATCH"
                results[f"{key}:{tag}"] += 1
    return results, unchecked, errors


def per_type(counter):
    """Fold a results Counter into {event_type: {"pass": n, "fail": n}}."""
    out = {}
    for key, count in counter.items():
        name, _, tag = key.partition(".")
        bucket = out.setdefault(name, {"pass": 0, "fail": 0})
        bucket["fail" if tag.endswith(":MISMATCH") else "pass"] += count
    return out


def checked_fields(counter):
    """{event_type: {field, ...}} for fields that were actually compared, from the real run."""
    out = {}
    for key in counter:
        name, _, rest = key.partition(".")
        out.setdefault(name, set()).add(rest.rsplit(":", 1)[0])
    return out


def find_effective_control(rows, event_name, types, ix_accounts, disc_to_ix, ev_disc, baseline,
                           eligible):
    """Frozen rule S4: a control that cannot perturb an event type proves nothing for it.

    B7l's single mint<->bonding_curve transposition could not touch `TradeEvent`, which has no
    `bonding_curve` field, so the arm carrying the volume had no control at all. Here each type
    gets its own pair, and a pair only counts if it actually raises that type's mismatch count.
    """
    # Frozen rule S4 requires BOTH members of the pair to be checkable for this type. Swapping a
    # checked field with an unchecked one would still raise the mismatch count, but it would only
    # show that a foreign value lands wrong - not that a genuine TRANSPOSITION is detected, which is
    # the specific weakness C1 had. Restricting to checked fields keeps the control honest.
    fields = [f for f in pubkey_fields(types, event_name) if f in eligible]
    for i, a in enumerate(fields):
        for b in fields[i + 1:]:
            totals = Counter()
            for tx in rows:
                r, _, _ = check_transaction(tx, types, ix_accounts, disc_to_ix, ev_disc,
                                            transpose=(a, b))
                totals.update(r)
            mutated = per_type(totals).get(event_name, {"fail": 0})["fail"]
            if mutated > baseline:
                return (a, b), baseline, mutated
    return None, baseline, baseline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--database",
                    default="research/b7j_positive_control_435564885_435565324.sqlite")
    ap.add_argument("--idl", default="research/pump_idl_9c82f61.json")
    ap.add_argument("--limit", type=int, default=0, help="0 = all stored transactions")
    args = ap.parse_args()

    types, ix_accounts, disc_to_ix, ev_disc, idl_hash = load_idl(args.idl)
    print(f"IDL sha256 {idl_hash}")
    # Read-only: this database holds primary B7j evidence and is owned elsewhere.
    db = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    query = "SELECT raw_zlib FROM raw_payload"
    if args.limit:
        query += f" LIMIT {args.limit}"

    rows = [json.loads(zlib.decompress(blob)) for (blob,) in db.execute(query)]
    totals, unchecked_all, errors_all = Counter(), Counter(), []
    for tx in rows:
        r, u, e = check_transaction(tx, types, ix_accounts, disc_to_ix, ev_disc)
        totals.update(r); unchecked_all.update(u); errors_all.extend(e)

    print(f"transactions examined: {len(rows)}\n")
    print("C1i-corrected — positional identity, with the frozen SOL equivalence:")
    for key in sorted(totals):
        print(f"   {key:<52} {totals[key]}")
    matches = sum(v for k, v in totals.items() if not k.endswith(":MISMATCH"))
    mismatches = sum(v for k, v in totals.items() if k.endswith(":MISMATCH"))
    equiv = sum(v for k, v in totals.items() if k.endswith(":MATCH_SOL_EQUIV"))
    print(f"   TOTAL pass {matches} (of which SOL-equivalence {equiv})   mismatch {mismatches}")

    print("\nNEGATIVE CONTROLS — one per observed event type (frozen rule S4):")
    observed = sorted(per_type(totals))
    eligible = checked_fields(totals)
    controls = {}
    for name in observed:
        base = per_type(totals).get(name, {"fail": 0})["fail"]
        pair, before, after = find_effective_control(rows, name, types, ix_accounts,
                                                     disc_to_ix, ev_disc, base,
                                                     eligible.get(name, set()))
        controls[name] = pair
        if pair:
            print(f"   {name:<34} {pair[0]}<->{pair[1]:<16} mismatches {before} -> {after}  POWER")
        else:
            print(f"   {name:<34} {'no effective pair found':<30} NO POWER")

    if unchecked_all:
        print("\nUNCHECKED (no same-named account; reported, never counted as passes):")
        for key in sorted(unchecked_all):
            print(f"   {key:<52} {unchecked_all[key]}")
    if errors_all:
        print(f"\nDECODE ERRORS: {len(errors_all)}")
        for e in errors_all[:5]:
            print(f"   {e}")

    powerless = [n for n, pair in controls.items() if pair is None]
    if not matches:
        verdict = "INCONCLUSIVE — nothing checkable"
    elif mismatches or errors_all:
        verdict = "FAIL"
    elif powerless:
        verdict = f"INCONCLUSIVE — no effective control for {powerless}"
    else:
        verdict = "PASS"
    print(f"\nVERDICT: {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
