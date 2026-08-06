"""B16c — reconcile wallet token inventory from evidence already preserved in the raw bodies.

B16a inferred a wallet's holding from the reserve deltas of its own trades, which cannot see anything
that happened outside those trades. B16b then had to say that no flow figure was bounded by
wallet-level inventory. This closes that gap using evidence that was already collected and never
read: the `meta.preTokenBalances` and `meta.postTokenBalances` of every stored `getTransaction`.

WHY THIS IS THE NARROWEST CORRECT METHOD
----------------------------------------
No SPL Token or Token-2022 instruction layout is decoded here, and none needs to be. The RPC already
reports, per token account touched by a transaction, its `owner`, its `mint`, its `programId`, and
the exact integer `amount` with `decimals`, before and after. Decoding instruction data would be a
second, weaker derivation of something the primary source already states — and it would need account
keys resolved through `loadedAddresses` for lookup-table transactions, which the RPC has likewise
already done. The provenance is therefore the stored response itself, and no third-party layout
enters the chain of custody.

ABSOLUTE BALANCES BEAT DELTAS, AND THE DIFFERENCE IS THE POINT
--------------------------------------------------------------
Summing deltas over collected transactions reproduces B16a's blind spot: activity outside the
collected set is simply missing. Reading the ABSOLUTE post-balance answers the question directly — a
wallet whose last observed balance is zero is flat at that moment however it got there, transfers
included.

Better still, the two together MEASURE the blind spot. Between consecutive observations of one token
account, the earlier `post` must equal the later `pre`. Where it does not, something moved that
balance in a transaction this corpus never collected. Those discrepancies are counted rather than
assumed away, so the coverage limit becomes a number instead of a caveat.

WHAT IS STILL REFUSED
---------------------
* An account whose `owner` changes between pre and post is ambiguous and is refused, not attributed.
* A balance entry missing `owner`, `mint`, `amount` or `decimals` is refused.
* A failed transaction is excluded: it moved no tokens.
* Shared ownership is never inferred. Two addresses holding the same mint are two addresses.
* Nothing here is called profit. This bounds INVENTORY; it does not price anything.
"""
import argparse
import collections
import importlib.util
import json
import pathlib
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B16A = _load("b16a_operator_archetypes", "b16a_operator_archetypes.py")

# The two token programs whose balances the RPC reports. Recorded as provenance: this module reads
# what the RPC stated about them and decodes neither program's instruction layout.
TOKEN_PROGRAMS = ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                  "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")


class InventoryRefused(RuntimeError):
    """The evidence is ambiguous, so no inventory figure is produced for it."""


def _entry(balance):
    """Normalise one balance entry, refusing anything incomplete rather than defaulting it."""
    amount = (balance.get("uiTokenAmount") or {})
    for field, value in (("accountIndex", balance.get("accountIndex")),
                         ("owner", balance.get("owner")), ("mint", balance.get("mint")),
                         ("amount", amount.get("amount")),
                         ("decimals", amount.get("decimals"))):
        if value is None:
            raise InventoryRefused(f"a token balance entry is missing {field}")
    return {"account_index": balance["accountIndex"], "owner": balance["owner"],
            "mint": balance["mint"], "amount": int(amount["amount"]),
            "decimals": amount["decimals"], "program_id": balance.get("programId")}


def transaction_balance_changes(meta):
    """Per token ACCOUNT: its owner, mint and the exact before/after amounts.

    Paired by `accountIndex`, never by owner: one owner may hold several accounts of the same mint,
    and pairing on owner would silently net them together. An account absent from `pre` did not
    exist or held nothing, so its before-amount is zero; absent from `post`, likewise after.
    """
    pre, post = {}, {}
    for balance in meta.get("preTokenBalances") or []:
        entry = _entry(balance)
        pre[entry["account_index"]] = entry
    for balance in meta.get("postTokenBalances") or []:
        entry = _entry(balance)
        post[entry["account_index"]] = entry
    changes = []
    for index in sorted(set(pre) | set(post)):
        before, after = pre.get(index), post.get(index)
        reference = after or before
        if before and after and before["owner"] != after["owner"]:
            raise InventoryRefused(
                f"token account at index {index} changed owner within one transaction; which "
                f"wallet held the balance is not determined by this evidence")
        if before and after and before["mint"] != after["mint"]:
            raise InventoryRefused(f"token account at index {index} changed mint")
        changes.append({
            "account_index": index, "owner": reference["owner"], "mint": reference["mint"],
            "decimals": reference["decimals"], "program_id": reference["program_id"],
            "amount_before": before["amount"] if before else 0,
            "amount_after": after["amount"] if after else 0,
            "account_created": before is None, "account_closed": after is None,
        })
    return changes


def observations(b9d_path=B16A.B9D, limit=None):
    """Every token-account observation, in canonical (slot, transaction_index) order."""
    connection = B16A._read_only(b9d_path, "B9d")
    try:
        coordinates = dict(connection.execute(
            "SELECT signature, slot || ':' || transaction_index FROM transaction_coordinate"))
        query = "SELECT signature, raw_zlib FROM raw_transaction"
        if limit:
            query += f" LIMIT {int(limit)}"
        rows = []
        census = collections.Counter()
        for signature, raw in connection.execute(query):
            census["transactions"] += 1
            try:
                payload = json.loads(zlib.decompress(raw))
            except (zlib.error, json.JSONDecodeError):
                census["unreadable_body"] += 1
                continue
            result = payload.get("result") or {}
            meta = result.get("meta") or {}
            if not meta:
                census["no_meta"] += 1
                continue
            if meta.get("err") is not None:
                census["failed_transaction_excluded"] += 1
                continue
            if "preTokenBalances" not in meta or "postTokenBalances" not in meta:
                census["no_token_balance_arrays"] += 1
                continue
            coordinate = coordinates.get(signature)
            if coordinate is None:
                census["no_canonical_coordinate"] += 1
                continue
            slot, transaction_index = (int(part) for part in coordinate.split(":"))
            try:
                changes = transaction_balance_changes(meta)
            except InventoryRefused:
                census["refused_ambiguous_account"] += 1
                continue
            census["transactions_used"] += 1
            for change in changes:
                census["account_observations"] += 1
                rows.append({**change, "slot": slot, "transaction_index": transaction_index,
                             "signature": signature})
        rows.sort(key=lambda r: (r["slot"], r["transaction_index"], r["account_index"]))
        return rows, dict(census)
    finally:
        connection.close()


def reconcile(rows):
    """Per (owner, mint): the last observed balance, and how much moved where we could not see.

    The gap is the measurement that matters. Consecutive observations of ONE token account must
    chain -- the earlier `after` is the later `before` -- and where they do not, a transaction this
    corpus never collected moved that balance. Counting those is how the coverage limit stops being
    a caveat and becomes a number.
    """
    # Grouped by (owner, mint) PER TRANSACTION. `accountIndex` is an index into one transaction's
    # account keys, NOT a stable identifier for a token account: the same account appears at index
    # 4, then 2, then 3 in three different transactions. Treating it as an identity split one
    # account into three and summed their last values, which inflated the final balance and inverted
    # the holding verdict. The index is right for pairing pre against post WITHIN a transaction and
    # wrong for anything across them.
    per_transaction = collections.defaultdict(
        lambda: {"before": 0, "after": 0, "accounts": 0, "closed": 0})
    for row in rows:
        key = (row["owner"], row["mint"], row["slot"], row["transaction_index"])
        entry = per_transaction[key]
        entry["before"] += row["amount_before"]
        entry["after"] += row["amount_after"]
        entry["accounts"] += 1
        entry["closed"] += int(row["account_closed"])

    by_wallet_mint = collections.defaultdict(list)
    for (owner, mint, slot, transaction_index), entry in per_transaction.items():
        by_wallet_mint[(owner, mint)].append(
            {"slot": slot, "transaction_index": transaction_index, **entry})

    summary = {}
    for key, series in by_wallet_mint.items():
        series.sort(key=lambda r: (r["slot"], r["transaction_index"]))
        gaps, gap_total = 0, 0
        for earlier, later in zip(series, series[1:]):
            if earlier["after"] != later["before"]:
                gaps += 1
                gap_total += abs(later["before"] - earlier["after"])
        summary[key] = {
            "observations": len(series),
            "final_amount": series[-1]["after"],
            "final_slot": series[-1]["slot"],
            "max_accounts_in_one_transaction": max(r["accounts"] for r in series),
            "uncollected_gaps": gaps,
            "uncollected_gap_amount": gap_total,
        }
    return summary


def reassess_positions(positions, curves, inventory):
    """Replace B16a's trade-derived holding test with the observed balance, where one exists."""
    reassessed = []
    for position in positions:
        mint = (curves.get(position["bonding_curve"]) or {}).get("mint")
        key = (position["wallet"], mint)
        entry = inventory.get(key)
        if mint is None:
            status = "no_mint_recorded"
        elif entry is None:
            # The wallet traded the curve but never appears in a collected transaction's token
            # balances. That is a gap in the evidence, not a zero balance.
            status = "no_balance_evidence"
        elif entry["final_amount"] == 0:
            status = "flat_at_last_observation"
        else:
            status = "still_holding_at_last_observation"
        reassessed.append({
            **position, "mint": mint, "inventory_status": status,
            "final_amount": None if entry is None else entry["final_amount"],
            "uncollected_gaps": None if entry is None else entry["uncollected_gaps"],
            "balance_observations": None if entry is None else entry["observations"],
            "trade_derived_unresolved": position["inventory_unresolved"],
        })
    return reassessed


def summarise(reassessed, census, inventory):
    by_archetype = collections.defaultdict(collections.Counter)
    disagreements = collections.Counter()
    for row in reassessed:
        archetype = row["archetype"]
        by_archetype[archetype][row["inventory_status"]] += 1
        by_archetype[archetype]["positions"] += 1
        if row["uncollected_gaps"]:
            by_archetype[archetype]["positions_with_an_uncollected_gap"] += 1
        trade_says_holding = row["trade_derived_unresolved"]
        balance_says_holding = row["inventory_status"] == "still_holding_at_last_observation"
        if row["inventory_status"] in ("flat_at_last_observation",
                                       "still_holding_at_last_observation"):
            if trade_says_holding != balance_says_holding:
                disagreements[f"{archetype}:trade={trade_says_holding}:balance={balance_says_holding}"] += 1

    # The flow figures B16a and B16b published rested on the trade-derived holding test. Recomputed
    # here on the stricter denominator -- balance observed flat AND no uncollected gap -- so a reader
    # can see whether the conclusion depended on the weaker test. Still not profit: this changes
    # WHICH positions are counted, not what the number means.
    flow_comparison = {}
    for archetype in sorted({row["archetype"] for row in reassessed}):
        subset = [r for r in reassessed if r["archetype"] == archetype]
        trade_resolved = [r for r in subset if not r["trade_derived_unresolved"]]
        balance_resolved = [r for r in subset
                            if r["inventory_status"] == "flat_at_last_observation"
                            and not r["uncollected_gaps"]]

        def net(rows_):
            return B16A.order_statistics(
                [r["observed_quote_flow_lamports"] - B16A._documented_curve_fee(r)
                 for r in rows_])

        flow_comparison[archetype] = {
            "on_trade_derived_resolved": {"positions": len(trade_resolved),
                                          "flow_less_documented_fee": net(trade_resolved)},
            "on_balance_flat_with_no_gap": {"positions": len(balance_resolved),
                                            "flow_less_documented_fee": net(balance_resolved)},
        }

    gaps = sum(1 for entry in inventory.values() if entry["uncollected_gaps"])
    return {
        "study": "B16C_WALLET_INVENTORY",
        "status": ("EXPLORATORY AND DESCRIPTIVE. Bounds inventory only; prices nothing and claims no "
                   "profit."),
        "executable": False,
        "performance_status": "not_evaluated",
        "execution_status": "never_executed",
        "method": {
            "source": ("meta.preTokenBalances and meta.postTokenBalances of the stored "
                       "getTransaction responses in b9d.raw_transaction"),
            "no_layout_decoded": ("no SPL Token or Token-2022 instruction layout is decoded. The RPC "
                                  "already states owner, mint, programId, exact integer amount and "
                                  "decimals per token account, and has already resolved lookup-table "
                                  "addresses, so decoding would be a weaker second derivation."),
            "token_programs_observed": list(TOKEN_PROGRAMS),
            "paired_by": ("accountIndex, never owner: one owner may hold several accounts of one "
                          "mint and pairing on owner would net them together silently"),
            "canonical_order": "slot, transaction_index, accountIndex",
        },
        "coverage": {
            **census,
            "wallet_mint_pairs": len(inventory),
            "wallet_mint_pairs_with_an_uncollected_gap": gaps,
            "what_a_gap_means": ("consecutive observations of one token account must chain. Where "
                                 "the earlier `after` differs from the later `before`, a "
                                 "transaction this corpus never collected moved that balance. The "
                                 "corpus holds only transactions that touched a bonding curve, so a "
                                 "pure wallet-to-wallet transfer is exactly the kind of thing that "
                                 "would appear here as a gap."),
        },
        "inventory_by_archetype": {name: dict(counter)
                                   for name, counter in sorted(by_archetype.items())},
        "flow_recomputed_on_the_stricter_denominator": {
            **flow_comparison,
            "reading": ("the same flow figure on two denominators. Where they agree the conclusion "
                        "did not rest on the weaker holding test; where they differ, the "
                        "balance-derived denominator is the better one."),
            "still_not_profit": ("this changes which positions are counted, not what the number "
                                 "means. Costs beyond the documented curve fee remain unrecorded."),
        },
        "trade_derived_versus_balance_derived": {
            "disagreements": dict(disagreements),
            "reading": ("B16a inferred holding from its own trades alone. Where the two disagree, "
                        "the balance evidence is the better one: it sees everything the collected "
                        "transactions saw, including movements the wallet's own trades do not "
                        "explain."),
        },
        "not_claimed": {
            "profit": "not claimed. This bounds inventory; it prices nothing.",
            "shared_ownership": ("never inferred. Two addresses holding one mint are two "
                                 "addresses, and no clustering was attempted."),
            "completeness": ("a zero final balance means flat AT THE LAST COLLECTED OBSERVATION, "
                             "not for all time. Anything after the corpus's last collected "
                             "transaction for that account is unobserved."),
        },
    }


def run(b9d_path=B16A.B9D, b10b_path=B16A.B10B, identity_path=B16A.B10C_IDENTITY, limit=None):
    B16A.assert_user_index_is_sound(b9d_path, identity_path)
    trades, _excluded = B16A.load_trades(b9d_path)
    curves = B16A.load_curves(b10b_path, identity_path)
    positions = B16A.wallet_curve_positions(trades, curves)
    B16A.classify(positions)
    rows, census = observations(b9d_path, limit=limit)
    inventory = reconcile(rows)
    reassessed = reassess_positions(positions, curves, inventory)
    return summarise(reassessed, census, inventory)


def main(argv=None):
    parser = argparse.ArgumentParser(description="B16c wallet inventory (offline, burned)")
    parser.add_argument("--output", default=None)
    arguments = parser.parse_args(argv)
    report = run()
    text = json.dumps(report, indent=1, sort_keys=True)
    if arguments.output:
        pathlib.Path(arguments.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(arguments.output).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
