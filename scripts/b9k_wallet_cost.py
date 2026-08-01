#!/usr/bin/env python3
"""B9k — transaction-level wallet-cost reconciliation.

Offline, read-only, no network. Transaction level only: no cost is ever divided across the trades
inside a transaction, because nothing in the evidence says how to divide it.

The question is what left the fee payer's account, and the only honest way to answer it is to
attribute every lamport to an instruction that says so. The identity is:

    payer_debit  ==  meta.fee
                   + lamports the payer sent via decoded System instructions
                   - lamports the payer received via decoded System instructions

A transaction where that holds exactly is `exact`. Everything else is categorised by evidence and
reported; nothing is tolerated, rounded, or apportioned.

WHAT LIMITS COVERAGE, measured rather than assumed: a program may move lamports on accounts it owns
without any System instruction. SPL Token `CloseAccount` returning rent to the payer is the common
case, and it is invisible here because the SPL Token ABI is not pinned in this repository. Those
transactions are categorised `unattributed_movement` with their residual and the accounts carrying
it, never silently absorbed.

For a simulator, that distinction is the deliverable: the components below marked exact are safe to
model, and rent RECLAIM is not yet one of them.
"""
import argparse
import base64
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B9D = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
B9J = _load("b9j_system_instructions", "b9j_system_instructions.py")
FreezeViolation = B9D.FreezeViolation

CATEGORIES = ("exact", "undecodable_system", "unattributed_movement")


def reconcile_transaction(result):
    """Attribute the fee payer's lamport delta. Returns a category and the evidence behind it."""
    meta = result.get("meta") or {}
    pre, post = meta.get("preBalances"), meta.get("postBalances")
    if not isinstance(pre, list) or not isinstance(post, list) or len(pre) != len(post) or not pre:
        raise FreezeViolation("transaction has no usable balance vectors")
    keys = B9D.resolve_account_keys(
        B9D.parse_message(base64.b64decode(result["transaction"][0])), meta)
    if len(keys) != len(pre):
        raise FreezeViolation(
            f"{len(keys)} resolved account keys against {len(pre)} balances")

    payer = keys[0]
    payer_debit = pre[0] - post[0]
    fee = meta.get("fee")
    if not isinstance(fee, int) or fee < 0:
        raise FreezeViolation(f"transaction fee is not a non-negative integer: {fee!r}")

    sent = received = 0
    undecodable = []
    for envelope in B9D.envelope_instructions(result):
        if envelope["program_id"] != B9J.SYSTEM_PROGRAM:
            continue
        try:
            decoded = B9J.decode_system_instruction(envelope["data"])
        except FreezeViolation as error:
            undecodable.append({"outer_index": envelope["outer_index"],
                                "inner_index": envelope["inner_index"], "reason": str(error)})
            continue
        moved = B9J.system_lamports_moved(decoded)
        if moved is None:
            continue
        accounts = envelope["accounts"]
        if len(accounts) < 2:
            raise FreezeViolation(
                f"{decoded['name']} moves lamports with {len(accounts)} account(s); the pinned ABI "
                "gives it a funder and a recipient")
        # accounts[0] funds, accounts[1] receives, for every lamport-moving variant in the pin.
        if accounts[0] == payer:
            sent += moved
        if accounts[1] == payer:
            received += moved

    attributed = fee + sent - received
    residual = payer_debit - attributed
    if undecodable:
        category = "undecodable_system"
    elif residual == 0:
        category = "exact"
    else:
        category = "unattributed_movement"

    record = {"category": category, "payer_debit": payer_debit, "fee": fee,
              "system_sent": sent, "system_received": received,
              "attributed": attributed, "residual": residual}
    if category == "undecodable_system":
        record["undecodable"] = undecodable
    elif category == "unattributed_movement":
        # Name the accounts carrying the unattributed movement. A residual with no accounts behind
        # it is a number; with them it is a lead. Closed accounts are called out because SPL Token
        # `CloseAccount` returning rent is the shape this category is dominated by.
        record["carriers"] = sorted(
            ({"account": keys[index], "delta": post[index] - pre[index],
              "closed": post[index] == 0 and pre[index] > 0,
              "created": pre[index] == 0 and post[index] > 0}
             for index in range(1, len(pre)) if post[index] != pre[index]),
            key=lambda entry: -abs(entry["delta"]))[:8]
    return record


def reconcile_artifact(database, limit=None, progress=None):
    """Reconcile every preserved transaction. Categories are exhaustive; nothing is dropped."""
    B9J.assert_abi_source_pinned()
    query = "SELECT signature FROM transaction_coordinate ORDER BY signature"
    if limit:
        query += f" LIMIT {int(limit)}"
    report = {"transactions": 0, "by_category": {name: 0 for name in CATEGORIES},
              "residual_histogram": {}, "examples": {}}
    for (signature,) in database.execute(query):
        raw = database.execute(
            "SELECT raw_zlib FROM raw_transaction WHERE signature=?", (signature,)).fetchone()[0]
        record = reconcile_transaction(B9D.raw_result(raw))
        report["transactions"] += 1
        report["by_category"][record["category"]] += 1
        if record["category"] != "exact":
            key = str(record["residual"])
            report["residual_histogram"][key] = report["residual_histogram"].get(key, 0) + 1
            report["examples"].setdefault(record["category"], dict(record, signature=signature))
        if progress and report["transactions"] % progress == 0:
            print(f"  {report['transactions']:,} transactions", file=sys.stderr, flush=True)
    total = report["transactions"]
    if not total:
        raise FreezeViolation("no transactions to reconcile; the measurement would be vacuous")
    if sum(report["by_category"].values()) != total:
        raise FreezeViolation("categories do not account for every transaction")
    report["exact_fraction"] = report["by_category"]["exact"] / total
    # Only the largest few residual values are worth printing; the tail is reported by count.
    report["residual_histogram"] = dict(
        sorted(report["residual_histogram"].items(), key=lambda kv: -kv[1])[:12])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress", type=int, default=None)
    args = parser.parse_args(argv)
    database = B9D.connect(args.artifact, readonly=True)
    try:
        report = reconcile_artifact(database, args.limit, args.progress)
    finally:
        database.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FreezeViolation as error:
        print(f"FreezeViolation: {error}", file=sys.stderr)
        sys.exit(2)
