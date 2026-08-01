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


# Load B9j first and take ITS b9d instance, rather than loading a second one. Loading b9d twice
# yields two module objects and therefore two distinct FreezeViolation CLASSES, so `except
# FreezeViolation` here would not catch what b9j raises -- the undecodable-instruction handler
# below would never fire and the whole run would die on the one transaction it exists to
# categorise. That is exactly what happened on the first full-population run.
B9J = _load("b9j_system_instructions", "b9j_system_instructions.py")
B9L = _load("b9l_token_instructions", "b9l_token_instructions.py")
B9D = B9J.B9D
# One b9d instance across all three, for the reason in the comment above: distinct module objects
# mean distinct FreezeViolation classes and handlers that never fire.
B9L.B9D = B9D
B9L.FreezeViolation = B9D.FreezeViolation
FreezeViolation = B9D.FreezeViolation

CATEGORIES = ("exact", "undecodable_instruction", "unattributed_movement")


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
    # Lamports credited to each account by decoded System instructions during this transaction.
    # An account created and closed in the SAME transaction has a pre-balance of 0 and a
    # post-balance of 0, yet CloseAccount still moves its rent -- so the pre-balance is the wrong
    # basis and the balance vector alone cannot see the movement at all. The funding instruction
    # can.
    credited = {}
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
        credited[accounts[1]] = credited.get(accounts[1], 0) + moved

    # Rent reclaim: CloseAccount sends the closed account's entire balance to accounts[1], and the
    # Token program does it on an account it owns, so no System instruction records it. This is the
    # movement that leaves the residual at exactly -2,039,280 across thousands of transactions.
    for envelope in B9D.envelope_instructions(result):
        if envelope["program_id"] not in B9L.TOKEN_PROGRAMS:
            continue
        try:
            token = B9L.decode_token_instruction(envelope["data"])
        except FreezeViolation as error:
            undecodable.append({"outer_index": envelope["outer_index"],
                                "inner_index": envelope["inner_index"], "reason": str(error)})
            continue
        if not token["moves_lamports"]:
            continue
        source, destination, lamports = B9L.close_account_movement(envelope, keys, pre)
        # Balance at close, not before the transaction: add what decoded System instructions put
        # into the account after it started.
        lamports += credited.pop(source, 0)
        if source == payer:
            sent += lamports
        if destination == payer:
            received += lamports

    attributed = fee + sent - received
    residual = payer_debit - attributed
    if undecodable:
        category = "undecodable_instruction"
    elif residual == 0:
        category = "exact"
    else:
        category = "unattributed_movement"

    # `attributed_*` rather than `system_*`: these now include Token CloseAccount rent reclaim, so
    # naming them after one program would misdescribe what they hold.
    record = {"category": category, "payer_debit": payer_debit, "fee": fee,
              "attributed_sent": sent, "attributed_received": received,
              "attributed": attributed, "residual": residual}
    if category == "undecodable_instruction":
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
