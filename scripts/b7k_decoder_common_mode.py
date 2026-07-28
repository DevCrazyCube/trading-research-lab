#!/usr/bin/env python3
"""B7k - decoder common-mode validation. Offline, zero RPC.

Preregistration: research/B7K_DECODER_COMMON_MODE_PREREGISTRATION.md
SHA-256 05704fc910b680c3136187b9326901faab8eae0283e2121181d0f36644334a07

B7h and B7j each compared two independent DISCOVERY paths that shared one decoder and one pinned
IDL. A wrong field offset is invisible to both and still reports exact agreement. This checks the
decoded VALUES against evidence the validator produced - resolved account keys, block time, and
balance deltas - none of which derive from the IDL.

The decoder under test is imported, never reimplemented: b7d.Cursor / b7d.read_struct, the same
code path b7j_positive_control.decode_events uses.
"""
import argparse
import base64
import hashlib
import json
import os
import sqlite3
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import b7d_create_enumerator as b7d
except ModuleNotFoundError:
    from scripts import b7d_create_enumerator as b7d

GRADUATION_EVENTS = ("CompleteEvent", "CompletePumpAmmMigrationEvent")
TRADE_EVENT = "TradeEvent"

# Frozen by the preregistration, check C1. Pubkey fields with an independent witness.
# quote_mint is deliberately absent: it may legitimately name a mint the transaction never
# touches, so requiring membership would manufacture a failure unrelated to decoding.
MEMBERSHIP_FIELDS = {
    "CompleteEvent": ("user", "mint", "bonding_curve"),
    "CompletePumpAmmMigrationEvent": ("user", "mint", "bonding_curve", "pool"),
    "TradeEvent": ("mint", "user"),
}


def event_discriminator(name):
    return hashlib.sha256(f"event:{name}".encode()).digest()[:8]


def load_idl(path):
    idl = json.load(open(path))
    types = {t["name"]: t for t in idl.get("types", [])}
    return idl, types


def account_key_set(transaction):
    """Resolved account keys. Returns (keys, unresolved_reason).

    An address-lookup-table transaction whose loaded addresses are not present in the stored
    payload cannot be resolved offline. That is reported as UNRESOLVABLE, never as a pass -
    silently treating a missing key set as an empty one would turn every membership test into a
    failure for a reason that has nothing to do with decoding.
    """
    message = transaction["transaction"]["message"]
    keys = []
    inlined_from_lookup = False
    for entry in message.get("accountKeys") or []:
        if isinstance(entry, dict):
            keys.append(entry["pubkey"])
            # jsonParsed encoding resolves address-table entries INTO accountKeys and tags them
            # source='lookupTable'. meta.loadedAddresses is then absent - not because resolution
            # failed, but because it already happened. Treating that as unresolvable would have
            # scored every v0 transaction as inconclusive for no real reason.
            if entry.get("source") == "lookupTable":
                inlined_from_lookup = True
        else:
            keys.append(entry)
    meta = transaction.get("meta") or {}
    loaded = meta.get("loadedAddresses")
    if loaded:
        keys.extend(loaded.get("writable") or [])
        keys.extend(loaded.get("readonly") or [])
    lookups = message.get("addressTableLookups") or []
    if lookups and not loaded and not inlined_from_lookup:
        # Genuinely unresolvable: the transaction references a lookup table and the stored payload
        # carries neither resolution form. Reported as UNRESOLVABLE, never as a pass.
        return set(keys), "address table lookups present with no resolved addresses in payload"
    return set(keys), None


def decode_one(payload_bytes, name, types):
    """Run the decoder under test. Returns (fields, trailing_bytes) or raises."""
    cursor = b7d.Cursor(payload_bytes[8:])
    fields = b7d.read_struct(cursor, types[name], types)
    return fields, cursor.remaining


def check_event(name, payload_bytes, transaction, block_time, types):
    """Apply the frozen checks to one event. Returns a result dict."""
    result = {"event_name": name, "c1_membership": None, "c2_timestamp": None,
              "c3_exact_consumption": None, "quote_mint": None,
              "unresolvable": None, "detail": []}
    try:
        fields, trailing = decode_one(payload_bytes, name, types)
    except Exception as error:  # noqa: BLE001
        result["c3_exact_consumption"] = False
        result["detail"].append(f"decode raised {type(error).__name__}: {error}")
        return result

    # C3 - exact payload consumption, re-verified per event rather than inherited from B0e.
    result["c3_exact_consumption"] = (trailing == 0)
    if trailing:
        result["detail"].append(f"{trailing} trailing bytes")

    # C1 - pubkey account-key membership.
    keys, unresolved = account_key_set(transaction)
    if unresolved:
        result["unresolvable"] = unresolved
        return result
    misses = []
    for field in MEMBERSHIP_FIELDS.get(name, ()):
        value = fields.get(field)
        if value is None:
            misses.append(f"{field}=<absent>")
        elif value not in keys:
            misses.append(f"{field}={value}")
    result["c1_membership"] = not misses
    if misses:
        result["detail"].append("not in account keys: " + ", ".join(misses))

    # C2 - decoded timestamp must equal the validator's blockTime exactly.
    stamp = fields.get("timestamp")
    if stamp is None or block_time is None:
        result["c2_timestamp"] = None
        result["detail"].append(f"timestamp={stamp} blockTime={block_time}")
    else:
        result["c2_timestamp"] = (int(stamp) == int(block_time))
        if not result["c2_timestamp"]:
            result["detail"].append(f"timestamp {stamp} != blockTime {block_time}")

    result["quote_mint"] = fields.get("quote_mint")
    result["fields"] = {k: v for k, v in fields.items()}
    return result


def graduation_arm(db, types):
    """Arm 1 - the two frozen B7j event types, from stored reference events."""
    results = []
    rows = db.execute(
        "SELECT signature, event_name, event_payload_base64 FROM event_row "
        "WHERE side='reference' ORDER BY slot, signature, outer_instruction_index, "
        "inner_instruction_index, event_ordinal").fetchall()
    for signature, name, payload_b64 in rows:
        raw = db.execute(
            "SELECT raw_zlib FROM raw_payload WHERE signature=? ORDER BY side LIMIT 1",
            (signature,)).fetchone()
        if raw is None:
            results.append({"event_name": name, "signature": signature,
                            "unresolvable": "no stored transaction payload",
                            "c1_membership": None, "c2_timestamp": None,
                            "c3_exact_consumption": None, "detail": []})
            continue
        transaction = json.loads(zlib.decompress(raw[0]))
        block_time = transaction.get("blockTime")
        outcome = check_event(name, base64.b64decode(payload_b64), transaction, block_time, types)
        outcome["signature"] = signature
        results.append(outcome)
    return results


def trade_arm(db, types, limit=None):
    """Arm 2 - TradeEvent at scale, decoded from the stored full blocks."""
    disc = event_discriminator(TRADE_EVENT)
    results = []
    for slot, blob in db.execute("SELECT slot, raw_zlib FROM raw_block ORDER BY slot"):
        block = json.loads(zlib.decompress(blob))
        block_time = block.get("blockTime")
        for transaction in block.get("transactions") or []:
            meta = transaction.get("meta") or {}
            if meta.get("err") is not None:
                continue
            for group in meta.get("innerInstructions") or []:
                for instruction in group.get("instructions") or []:
                    if instruction.get("programId") != b7d.PUMP or not instruction.get("data"):
                        continue
                    encoded = b7d.b58decode(instruction["data"])
                    if len(encoded) < 16 or encoded[:8] != b7d.EVENT_TAG:
                        continue
                    if encoded[8:16] != disc:
                        continue
                    outcome = check_event(TRADE_EVENT, encoded[8:], transaction,
                                          block_time, types)
                    outcome["slot"] = slot
                    # C2's effective independent-sample count is distinct TRANSACTIONS, not
                    # events, so the signature must survive even though the fields do not.
                    outcome["signature"] = transaction["transaction"]["signatures"][0]
                    outcome.pop("fields", None)      # keep the report small
                    results.append(outcome)
                    if limit and len(results) >= limit:
                        return results
    return results


def verdict(results, arm_name):
    """Frozen verdict rule. An empty set is INCONCLUSIVE, never a pass."""
    n = len(results)
    unresolvable = [r for r in results if r.get("unresolvable")]
    if n == 0:
        return {"arm": arm_name, "verdict": "INCONCLUSIVE", "n": 0,
                "reason": "empty event set"}
    counts = {}
    failures = []
    for check in ("c1_membership", "c2_timestamp", "c3_exact_consumption"):
        passed = sum(1 for r in results if r.get(check) is True)
        failed = [r for r in results if r.get(check) is False]
        counts[check] = {"pass": passed, "fail": len(failed),
                         "not_applicable": n - passed - len(failed)}
        failures.extend(failed)
    if unresolvable:
        result = "INCONCLUSIVE"
    elif failures:
        result = "FAIL"
    elif all(counts[c]["pass"] == n for c in ("c1_membership", "c2_timestamp",
                                              "c3_exact_consumption")):
        result = "PASS"
    else:
        result = "INCONCLUSIVE"
    return {"arm": arm_name, "verdict": result, "n": n, "checks": counts,
            "unresolvable": len(unresolvable),
            "failure_examples": [
                {k: v for k, v in f.items() if k != "fields"} for f in failures[:5]],
            "distinct_transactions": len({r.get("signature") for r in results
                                          if r.get("signature")}) or None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--idl", required=True)
    parser.add_argument("--trade-limit", type=int, default=None)
    parser.add_argument("--output")
    args = parser.parse_args()

    _, types = load_idl(args.idl)
    for name in GRADUATION_EVENTS + (TRADE_EVENT,):
        if name not in types:
            print(json.dumps({"result": "FAIL",
                              "reason": f"pinned IDL has no type {name}"}))
            return 2

    db = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)

    graduation = graduation_arm(db, types)
    trade = trade_arm(db, types, args.trade_limit)

    quote_mints = sorted({r.get("quote_mint") for r in graduation
                          if r.get("quote_mint")})
    report = {
        "preregistration_sha256":
            "05704fc910b680c3136187b9326901faab8eae0283e2121181d0f36644334a07",
        "graduation_arm": verdict(graduation, "graduation"),
        "trade_arm": verdict(trade, "trade_event"),
        "c4_quote_mint_distinct": quote_mints,
        "c4_quote_mint_consistent": len(quote_mints) <= 1,
        "graduation_detail": graduation,
    }
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(text)
    if args.output:
        open(args.output, "w").write(text + "\n")
    both = {report["graduation_arm"]["verdict"], report["trade_arm"]["verdict"]}
    return 0 if both == {"PASS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
