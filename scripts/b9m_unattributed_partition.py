#!/usr/bin/env python3
"""B9m — mutually exclusive causal partition of the `unattributed_movement` transactions.

Offline, read-only, no network. Provenance in `research/B9M_UNATTRIBUTED_PARTITION.md`.

Wallet-cost reconciliation (B9k) attributes 93.03% of the frozen population exactly. Of the
remainder, 4,962 transactions are `unattributed_movement`: their lamport arithmetic does not close.
This module partitions those into categories that are *causal* rather than descriptive — each names
the specific reason attribution is impossible, and each is decided from decoded evidence.

The categories are ORDERED and the first match wins, which is what makes them mutually exclusive.
The order is not arbitrary: each category names a reason that is sufficient on its own, so a
transaction matching two is assigned to the more fundamental one. A non-native quote cannot be
summed into lamports at all, so that dominates; a transaction with no trade is not a trade whatever
else it contains; and so on down to the residue that uses only pinned programs.

That last category is the important one. It is small and bounded, and it is the only category whose
cause must lie inside semantics already pinned — so it is the only one that can be closed without
pinning a new third-party ABI. Everything above it is blocked on evidence this project does not yet
have, and saying so precisely is the point of this module.

Nothing here attributes lamports. It explains why they are unattributed.
"""
import argparse
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


B9K = _load("b9k_wallet_cost", "b9k_wallet_cost.py")
B9D = B9K.B9D
FreezeViolation = B9D.FreezeViolation

# Programs whose instruction semantics this project has pinned to an authoritative versioned
# source. A transaction built only from these is one whose full lamport movement SHOULD be
# derivable; if it still fails to reconcile, the gap is in our pinned semantics, not in missing
# evidence. That distinction is the whole point of the partition, so this set is deliberately
# narrow: membership means "we have pinned its ABI", not "we recognise the address".
#
# The associated-token-account program is included because it creates accounts exclusively through
# System CPIs that the System decoder already sees. `pfee` is NOT included -- see below.
PINNED_PROGRAMS = frozenset({
    B9D.PUMP_PROGRAM,
    B9D.PUMPSWAP_PROGRAM,
    "11111111111111111111111111111111",                 # System
    "ComputeBudget111111111111111111111111111111",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",      # SPL Token
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",      # Token-2022
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",     # Associated Token Account
    "Sysvar1nstructions1111111111111111111111111",
})

# The Pump fee program. It appears in 100% of unattributed transactions, which looks like a
# smoking gun and is not one: it also appears in 98.3% of the EXACTLY reconciled ones. Its presence
# carries essentially no information about whether a transaction reconciles, so treating it as a
# cause would be a selection artifact. It is named here so that nobody re-derives that dead end,
# and it is deliberately absent from PINNED_PROGRAMS because its ABI genuinely is not pinned.
PUMP_FEE_PROGRAM = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"

# First match wins. See the module docstring for why this order is the one that makes the
# categories mutually exclusive rather than merely disjoint by construction.
NONNATIVE_QUOTE = "nonnative_quote"
NO_TRADE_EVENT = "no_trade_event"
MULTI_TRADE = "multi_trade"
THIRD_PARTY_PROGRAM = "third_party_program"
PINNED_ONLY = "pinned_only"

PARTITION_CATEGORIES = (
    NONNATIVE_QUOTE,
    NO_TRADE_EVENT,
    MULTI_TRADE,
    THIRD_PARTY_PROGRAM,
    PINNED_ONLY,
)

CATEGORY_CAUSE = {
    NONNATIVE_QUOTE: (
        "The trade is quoted in a mint other than native SOL. Its quote amount is in raw token "
        "units, which are not lamports and must never be summed into them, so no lamport "
        "attribution is possible without a price. Deliberately skipped, not failed."),
    NO_TRADE_EVENT: (
        "The transaction emits no TradeEvent at all -- it is a pool or liquidity operation rather "
        "than a trade. The lamports moved are real but belong to no trade this project models."),
    MULTI_TRADE: (
        "More than one TradeEvent. The payer's single lamport delta cannot be split across several "
        "trades without an allocation rule, and inventing one would fabricate per-trade costs."),
    THIRD_PARTY_PROGRAM: (
        "At least one program outside the pinned set participates. A program may move lamports on "
        "accounts it owns with no System instruction recording it -- the same mechanism that hid "
        "sell proceeds until the curve's own semantics were pinned. Closing this needs that "
        "program's ABI pinned to an authoritative source."),
    PINNED_ONLY: (
        "Only pinned programs participate, yet the arithmetic still does not close. This is the "
        "bounded residue: its cause lies in semantics already pinned, so it is the only category "
        "closable without new external evidence."),
}


def transaction_evidence(result, idls):
    """Decode the evidence the partition is decided from. No attribution, no arithmetic."""
    envelopes = B9D.envelope_instructions(result)
    trades = []
    for envelope in envelopes:
        decoded = B9D.decode_anchor_cpi_event(envelope["program_id"], envelope["data"], idls)
        if decoded and decoded["name"] == "TradeEvent":
            trades.append(decoded["fields"])
    programs = {envelope["program_id"] for envelope in envelopes}
    return {
        "trade_count": len(trades),
        "quote_mints": [trade.get("quote_mint") for trade in trades],
        "programs": programs,
        "unpinned_programs": sorted(programs - PINNED_PROGRAMS),
    }


def is_pump_fee_only(evidence):
    """True when `pfee` is the ONLY unpinned program present.

    This is the honest way to surface the tractable residue without weakening PINNED_PROGRAMS.
    `pfee` cannot be called pinned -- its ABI is not -- so these transactions are correctly
    `third_party_program`. But it is also the one program whose presence carries no information
    (98.3% of exactly-reconciled transactions contain it too), so a transaction whose only unpinned
    program is `pfee` is far closer to explicable than one that routes through an aggregator.

    Reported as a sub-count, never as a category, so the partition stays exclusive.
    """
    return evidence["unpinned_programs"] == [PUMP_FEE_PROGRAM]


def classify_unattributed(evidence):
    """Assign exactly one causal category. First match wins; see PARTITION_CATEGORIES."""
    if any(mint != B9D.NATIVE_QUOTE_MINT for mint in evidence["quote_mints"]):
        return NONNATIVE_QUOTE
    if evidence["trade_count"] == 0:
        return NO_TRADE_EVENT
    if evidence["trade_count"] > 1:
        return MULTI_TRADE
    if evidence["unpinned_programs"]:
        return THIRD_PARTY_PROGRAM
    return PINNED_ONLY


def assert_exhaustive(by_category, unattributed):
    """Every unattributed transaction must carry exactly one cause.

    A partition that loses rows understates whichever cause it loses, and it would do so silently:
    the remaining categories still look like a clean breakdown. This is the guard against that.
    """
    total = sum(by_category.values())
    if total != unattributed:
        raise FreezeViolation(
            f"partition assigned {total} of {unattributed} unattributed transactions; the "
            "categories must be exhaustive")
    return True


def partition(database, idls=None, limit=None, progress=None):
    """Partition every `unattributed_movement` transaction in the artifact."""
    idls = idls or B9K.pinned_idls()
    query = "SELECT signature FROM transaction_coordinate ORDER BY signature"
    if limit:
        query += f" LIMIT {int(limit)}"
    report = {"scanned": 0, "unattributed": 0,
              "by_category": {category: 0 for category in PARTITION_CATEGORIES},
              "unpinned_program_counts": {}, "pinned_only_signatures": [],
              "pump_fee_only": 0, "pump_fee_only_signatures": []}
    for (signature,) in database.execute(query):
        raw = database.execute(
            "SELECT raw_zlib FROM raw_transaction WHERE signature=?", (signature,)).fetchone()[0]
        result = B9D.raw_result(raw)
        report["scanned"] += 1
        if B9K.reconcile_transaction(result, idls)["category"] != "unattributed_movement":
            continue
        report["unattributed"] += 1
        evidence = transaction_evidence(result, idls)
        category = classify_unattributed(evidence)
        report["by_category"][category] += 1
        if category == THIRD_PARTY_PROGRAM:
            for program in evidence["unpinned_programs"]:
                report["unpinned_program_counts"][program] = (
                    report["unpinned_program_counts"].get(program, 0) + 1)
            if is_pump_fee_only(evidence):
                report["pump_fee_only"] += 1
                if len(report["pump_fee_only_signatures"]) < 200:
                    report["pump_fee_only_signatures"].append(signature)
        elif category == PINNED_ONLY and len(report["pinned_only_signatures"]) < 200:
            report["pinned_only_signatures"].append(signature)
        if progress and report["scanned"] % progress == 0:
            print(f"  {report['scanned']:,} scanned, {report['unattributed']:,} unattributed",
                  file=sys.stderr, flush=True)
    assert_exhaustive(report["by_category"], report["unattributed"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress", type=int, default=None)
    args = parser.parse_args(argv)
    database = B9D.connect(args.artifact, readonly=True)
    try:
        report = partition(database, limit=args.limit, progress=args.progress)
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
