"""B16a — can the burned corpus distinguish operator archetypes, and what does it show?

EXPLORATORY AND DESCRIPTIVE. This is hypothesis-generating, not a preregistered estimand. Nothing
here is a performance claim, a profitability figure or a recommendation, and no threshold below was
tuned against an outcome.

Sources are burned/published artifacts ONLY -- the B8b/B9d corpus (slots 433,894,233..434,097,833,
permanently excluded from evaluation), B10b's observed paths, B10c's t0 identities. It reads nothing
under `research/b11a`, opens no network connection and touches no live process.

WHAT MAKES A WALLET RECOVERABLE AT ALL
--------------------------------------
The trader is the `user` account of a `buy`/`sell` instruction, at a position fixed by the IDL. The
stored account list for v1 instructions is LONGER than the IDL declares (18 stored against 16 for
`buy`), so the position is validated rather than assumed: `assert_user_index_is_sound` re-derives the
wallet for curves whose `t0_user` B10c established independently, and refuses unless every one agrees.

WHAT IS DELIBERATELY REFUSED
----------------------------
* A transaction carrying more than one trade instruction is EXCLUDED, not guessed at. Pairing a
  wallet to a reserve delta needs one of each; 0.6% of transactions have more and are reported as
  excluded rather than resolved by assumption.
* Identity ownership is never inferred. "creator-like" means the wallet EQUALS the creator or
  create_user field of that curve in B10c, which is an observation about a field, not a claim that
  two wallets are one person.
* Profitability is never computed. A buy with no observed sell is UNRESOLVED INVENTORY, reported as
  such and never treated as a gain or a loss. Token transfers out of a wallet are invisible to this
  corpus, so even an observed sell does not bound what a wallet actually did.
* Advertised bot capabilities are not evidence and appear nowhere in this module. Only observed
  on-chain behaviour is measured.
"""
import argparse
import collections
import json
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]

B9D = ROOT / "research" / "b9d_transaction_bodies.sqlite"
B10B = ROOT / "research" / "b10b_observed_paths.sqlite"
B10C_IDENTITY = ROOT / "research" / "b10c_t0_identity.sqlite"

# The burned B8b/B9d corpus. Stated so a reader can see the audit is confined to it.
BURNED_RANGE = (433_894_233, 434_097_833)

# The `user` account position for each trade instruction, by IDL account order. Validated at run
# time against B10c's independently derived `t0_user`; a disagreement refuses the whole audit.
USER_INDEX = {
    "buy": 6, "sell": 6, "buy_exact_sol_in": 6, "sell_exact_token_in": 6,
    "buy_v2": 13, "sell_v2": 13, "buy_exact_quote_in_v2": 13, "sell_exact_base_in_v2": 13,
}
BUY_NAMES = {"buy", "buy_exact_sol_in", "buy_v2", "buy_exact_quote_in_v2"}
SELL_NAMES = {"sell", "sell_exact_token_in", "sell_v2", "sell_exact_base_in_v2"}

# Archetype boundaries. Declared here as round numbers chosen for legibility BEFORE any distribution
# was inspected, and reported alongside the sensitivity band so a reader can see they are not doing
# the work. None of them was moved after seeing a result.
IMMEDIATE_SLOTS = 1          # entry within one slot of the create
EARLY_SLOTS = 4              # "early" for the purpose of counting repeat early entrants
DELAYED_SLOTS = 30           # entry this far out is a different behaviour, not a slow snipe
REPEAT_CURVES = 5            # distinct curves entered early before a wallet is called repeat


class AuditRefused(RuntimeError):
    """The evidence cannot support the question, so no figure is produced."""


def _read_only(path, label):
    path = pathlib.Path(path)
    if not path.exists():
        raise AuditRefused(f"no {label} artifact at {path}")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def assert_user_index_is_sound(b9d_path=B9D, identity_path=B10C_IDENTITY, limit=400):
    """Re-derive the wallet where B10c already knows it, and refuse on any disagreement.

    The stored account list is longer than the IDL declares, so a positional read is a claim that
    needs evidence. B10c's `t0_user` was derived by a different route -- decoding the TradeEvent
    payload -- which makes it an independent check rather than a restatement.
    """
    b9d = _read_only(b9d_path, "B9d")
    identity = _read_only(identity_path, "B10c identity")
    try:
        rows = identity.execute(
            "SELECT bonding_curve, t0_slot, t0_transaction_index, t0_outer_index, t0_user "
            "FROM identity WHERE t0_user IS NOT NULL LIMIT ?", (limit,)).fetchall()
        if not rows:
            raise AuditRefused("no t0_user rows to validate the account position against")
        names = tuple(USER_INDEX)
        checked = disagreed = unresolved = 0
        for _curve, slot, transaction_index, outer_index, expected in rows:
            found = None
            # Matched on the OUTER INDEX as well, and ordered. A launch transaction routinely
            # bundles a create with several buys -- one observed case carries three `buy`
            # instructions at outer 4, 6 and 8, each with its own TradeEvent. Selecting on
            # (slot, transaction_index) alone returns all three in no defined order, and taking
            # the first compares t0's wallet against a DIFFERENT trade's account list. That reads
            # as "the account position is wrong" when the position is right and the instruction is
            # wrong, and on the fresh window it refused the whole audit over one such bundle.
            # This is the same mispairing b10b's `_decode_at` documents costing a spurious
            # 389,217,712-lamport mismatch on b10a's first gate run.
            for name, accounts_json in b9d.execute(
                    "SELECT idl_name, accounts_json FROM instruction WHERE slot=? AND "
                    "transaction_index=? AND outer_index=? AND idl_name IN "
                    f"({','.join('?' * len(names))}) ORDER BY outer_index, inner_index",
                    (slot, transaction_index, outer_index, *names)):
                accounts = json.loads(accounts_json)
                index = USER_INDEX[name]
                if index < len(accounts):
                    found = accounts[index]
                    break
            if found is None:
                unresolved += 1
            elif found != expected:
                disagreed += 1
            else:
                checked += 1
        if disagreed or unresolved:
            raise AuditRefused(
                f"the user account position is not sound: {disagreed} disagreed and {unresolved} "
                f"could not be resolved out of {len(rows)}; a positional read that is wrong "
                f"anywhere is wrong everywhere and no archetype may rest on it")
        return {"validated_against_t0_user": checked, "disagreed": 0, "unresolved": 0}
    finally:
        b9d.close()
        identity.close()


def load_trades(b9d_path=B9D):
    """One row per unambiguous trade: wallet, curve, canonical coordinate, direction, lamport delta.

    Ambiguity is excluded rather than resolved. A transaction with two trade instructions has two
    wallets and two reserve deltas and no evidence saying which belongs to which, so it is dropped
    and counted.
    """
    b9d = _read_only(b9d_path, "B9d")
    try:
        names = tuple(USER_INDEX)
        placeholders = ",".join("?" * len(names))
        per_transaction = collections.Counter()
        instructions = []
        for row in b9d.execute(
                f"SELECT slot, transaction_index, outer_index, inner_index, signature, idl_name, "
                f"accounts_json FROM instruction WHERE idl_name IN ({placeholders})", names):
            per_transaction[(row[0], row[1])] += 1
            instructions.append(row)
        reserves = {}
        duplicated = set()
        for row in b9d.execute(
                "SELECT slot, transaction_index, bonding_curve, real_quote_before, "
                "real_quote_after, real_token_before, real_token_after FROM reserve_observation"):
            key = (row[0], row[1])
            if key in reserves:
                duplicated.add(key)
            reserves[key] = row[2:]
    finally:
        b9d.close()

    trades, excluded = [], collections.Counter()
    for slot, transaction_index, outer, inner, signature, name, accounts_json in instructions:
        key = (slot, transaction_index)
        if per_transaction[key] != 1:
            excluded["multiple_trade_instructions"] += 1
            continue
        if key in duplicated:
            excluded["multiple_reserve_observations"] += 1
            continue
        if key not in reserves:
            excluded["no_reserve_observation"] += 1
            continue
        curve, quote_before, quote_after, token_before, token_after = reserves[key]
        accounts = json.loads(accounts_json)
        index = USER_INDEX[name]
        if index >= len(accounts):
            excluded["account_list_too_short"] += 1
            continue
        direction = "buy" if name in BUY_NAMES else "sell"
        quote_delta = quote_after - quote_before
        token_delta = token_after - token_before
        # The reserve delta must agree with the instruction's own name. A buy that removed quote
        # from the curve is not a buy that this audit understands, and guessing which of the two
        # is right would be inventing evidence.
        if (direction == "buy" and quote_delta <= 0) or (direction == "sell" and quote_delta >= 0):
            excluded["direction_contradicts_reserve_delta"] += 1
            continue
        trades.append({
            "wallet": accounts[index], "bonding_curve": curve, "slot": slot,
            "transaction_index": transaction_index, "outer_index": outer, "inner_index": inner,
            "signature": signature, "instruction": name, "direction": direction,
            "quote_delta_lamports": quote_delta, "token_delta": token_delta,
        })
    trades.sort(key=lambda t: (t["slot"], t["transaction_index"], t["outer_index"],
                               t["inner_index"]))
    return trades, dict(excluded)


def load_curves(b10b_path=B10B, identity_path=B10C_IDENTITY):
    """Create and completion coordinates, plus the creator/create_user fields B10c recorded."""
    b10b = _read_only(b10b_path, "B10b")
    identity = _read_only(identity_path, "B10c identity")
    try:
        curves = {}
        for curve, mint, create_slot, complete_slot, regime in b10b.execute(
                "SELECT bonding_curve, mint, create_slot, complete_slot, regime FROM curve"):
            curves[curve] = {"mint": mint, "create_slot": create_slot,
                             "complete_slot": complete_slot, "regime": regime,
                             "creator": None, "create_user": None}
        for curve, creator, create_user in identity.execute(
                "SELECT bonding_curve, creator, create_user FROM identity"):
            if curve in curves:
                curves[curve]["creator"] = creator
                curves[curve]["create_user"] = create_user
        return curves
    finally:
        b10b.close()
        identity.close()


def wallet_curve_positions(trades, curves):
    """Per (wallet, curve): entry timing, size, exit evidence and whether inventory is unresolved."""
    grouped = collections.defaultdict(list)
    for trade in trades:
        grouped[(trade["wallet"], trade["bonding_curve"])].append(trade)
    positions = []
    for (wallet, curve), rows in grouped.items():
        meta = curves.get(curve)
        if meta is None or meta["create_slot"] is None:
            continue
        buys = [r for r in rows if r["direction"] == "buy"]
        sells = [r for r in rows if r["direction"] == "sell"]
        if not buys:
            continue
        first_buy = buys[0]
        bought = sum(r["quote_delta_lamports"] for r in buys)
        sold = -sum(r["quote_delta_lamports"] for r in sells)
        # SIGNS ARE FROM THE CURVE'S POINT OF VIEW. A buy moves quote INTO the curve and tokens OUT
        # of it, so `token_delta` is negative on a buy and positive on a sell. The wallet's holding
        # is therefore the NEGATED delta. Getting this backwards made every position look resolved,
        # which is the opposite of the truth for a wallet that bought and never sold.
        tokens_in = -sum(r["token_delta"] for r in buys)
        tokens_out = sum(r["token_delta"] for r in sells)
        entry_delay = first_buy["slot"] - meta["create_slot"]
        positions.append({
            "wallet": wallet, "bonding_curve": curve,
            "entry_slot": first_buy["slot"], "create_slot": meta["create_slot"],
            "entry_delay_slots": entry_delay,
            "same_transaction_as_create": entry_delay == 0,
            "buys": len(buys), "sells": len(sells),
            "quote_in_lamports": bought, "quote_out_lamports": sold,
            "tokens_acquired": tokens_in, "tokens_disposed": tokens_out,
            # Never called profit. Quote out minus quote in is an OBSERVED FLOW inside one window on
            # one curve; the wallet may hold, may have moved tokens elsewhere, and pays costs this
            # corpus does not record.
            "observed_quote_flow_lamports": sold - bought,
            "inventory_unresolved": tokens_in > tokens_out,
            "exit_delay_slots": (sells[-1]["slot"] - first_buy["slot"]) if sells else None,
            "creator_like": wallet in (meta["creator"], meta["create_user"]),
            "after_completion": (meta["complete_slot"] is not None
                                 and first_buy["slot"] >= meta["complete_slot"]),
        })
    positions.sort(key=lambda p: (p["entry_slot"], p["bonding_curve"], p["wallet"]))
    return positions


def classify(positions):
    """Assign each position ONE archetype, by rules applied in a fixed order.

    Ordered because the categories overlap in reality: a creator who also snipes is recorded as
    creator-like, because that is the more specific observation. The order is part of the definition
    and is reported with the counts.
    """
    early_curves = collections.Counter()
    for position in positions:
        if position["entry_delay_slots"] <= EARLY_SLOTS:
            early_curves[position["wallet"]] += 1
    repeat_wallets = {w for w, n in early_curves.items() if n >= REPEAT_CURVES}
    curves_per_wallet = collections.Counter(p["wallet"] for p in positions)

    for position in positions:
        wallet = position["wallet"]
        if position["creator_like"]:
            archetype = "creator_like_participant"
        elif position["after_completion"]:
            archetype = "migration_trader"
        elif wallet in repeat_wallets:
            archetype = "repeat_early_entrant"
        elif position["entry_delay_slots"] <= IMMEDIATE_SLOTS:
            archetype = "immediate_launch_sniper"
        elif position["entry_delay_slots"] >= DELAYED_SLOTS:
            archetype = "delayed_entrant"
        elif curves_per_wallet[wallet] == 1:
            archetype = "incidental_trader"
        else:
            archetype = "unclassified_mid_window"
        position["archetype"] = archetype
        position["distinct_curves_for_wallet"] = curves_per_wallet[wallet]
    return {"repeat_wallets": len(repeat_wallets), "wallets": len(curves_per_wallet)}


def order_statistics(values):
    """Exact integer order statistics. No mean: this is a heavy-tailed, censored population."""
    if not values:
        return None
    ordered = sorted(values)

    def at(numerator, denominator):
        return ordered[(len(ordered) - 1) * numerator // denominator]

    return {"n": len(ordered), "min": ordered[0], "p10": at(1, 10), "p25": at(1, 4),
            "median": at(1, 2), "p75": at(3, 4), "p90": at(9, 10), "max": ordered[-1]}


def summarise(positions, trades, excluded, validation, curves):
    by_archetype = collections.defaultdict(list)
    for position in positions:
        by_archetype[position["archetype"]].append(position)

    archetypes = {}
    for name, rows in sorted(by_archetype.items()):
        resolved = [r for r in rows if not r["inventory_unresolved"]]
        archetypes[name] = {
            "positions": len(rows),
            "distinct_wallets": len({r["wallet"] for r in rows}),
            "distinct_curves": len({r["bonding_curve"] for r in rows}),
            "entry_delay_slots": order_statistics([r["entry_delay_slots"] for r in rows]),
            "quote_in_lamports": order_statistics([r["quote_in_lamports"] for r in rows]),
            "positions_with_any_sell": sum(1 for r in rows if r["sells"]),
            "positions_with_unresolved_inventory": sum(
                1 for r in rows if r["inventory_unresolved"]),
            "exit_delay_slots_where_fully_exited": order_statistics(
                [r["exit_delay_slots"] for r in resolved if r["exit_delay_slots"] is not None]),
            "observed_quote_flow_lamports_where_fully_exited": order_statistics(
                [r["observed_quote_flow_lamports"] for r in resolved]),
            "flow_is_not_profit": ("observed quote flow is one window on one curve, before costs "
                                   "this corpus does not record, and says nothing about the "
                                   "wallet's result"),
            "flow_less_documented_curve_fee_where_fully_exited": order_statistics(
                [r["observed_quote_flow_lamports"] - _documented_curve_fee(r)
                 for r in resolved]),
        }

    curves_per_wallet = collections.Counter(p["wallet"] for p in positions)
    ranked = sorted(curves_per_wallet.values(), reverse=True)
    total_positions = len(positions)
    concentration = {
        "distinct_wallets": len(curves_per_wallet),
        "positions": total_positions,
        "curves_per_wallet": order_statistics(list(curves_per_wallet.values())),
        "share_of_positions_top_1_pct_of_wallets": _share(ranked, total_positions, 0.01),
        "share_of_positions_top_10_pct_of_wallets": _share(ranked, total_positions, 0.10),
        "wallets_on_one_curve_only": sum(1 for n in curves_per_wallet.values() if n == 1),
    }

    return {
        "study": "B16A_OPERATOR_ARCHETYPES",
        "status": "EXPLORATORY AND DESCRIPTIVE. Hypothesis-generating, not a preregistered estimand.",
        "executable": False,
        "performance_status": "not_evaluated",
        "execution_status": "never_executed",
        "source": {
            "corpus": "burned B8b/B9d window",
            "burned_slot_range": list(BURNED_RANGE),
            "artifacts": ["research/b9d_transaction_bodies.sqlite",
                          "research/b10b_observed_paths.sqlite",
                          "research/b10c_t0_identity.sqlite"],
            "reads_no_b11a": True, "network": "none",
        },
        "wallet_recovery": {
            "method": "the `user` account of the trade instruction, at the IDL account position",
            "validation": validation,
            "why_validated": ("the stored account list is longer than the IDL declares, so the "
                              "position is a claim; B10c derived t0_user by decoding the event "
                              "payload, which makes it an independent check"),
        },
        "coverage": {
            "trades_usable": len(trades),
            "positions": total_positions,
            "curves_with_a_create_coordinate": len(curves),
            "excluded_from_trades": excluded,
            "exclusions_are_refusals": ("a transaction with more than one trade instruction has no "
                                        "evidence pairing wallet to reserve delta, so it is dropped "
                                        "and counted rather than resolved by assumption"),
        },
        "archetype_rules": {
            "applied_in_this_order": ["creator_like_participant", "migration_trader",
                                      "repeat_early_entrant", "immediate_launch_sniper",
                                      "delayed_entrant", "incidental_trader",
                                      "unclassified_mid_window"],
            "immediate_slots": IMMEDIATE_SLOTS, "early_slots": EARLY_SLOTS,
            "delayed_slots": DELAYED_SLOTS, "repeat_curves": REPEAT_CURVES,
            "thresholds_were_not_tuned": ("round numbers chosen for legibility before any "
                                          "distribution was inspected, and none was moved after "
                                          "seeing a result"),
        },
        "archetypes": archetypes,
        "concentration": concentration,
        "not_measurable_here": NOT_MEASURABLE,
    }


# B15Q decoded a fee schedule from every one of its 4,096 launch transactions and found
# `fee_bps` = 95 in ALL of them, while the creator, cashback and buyback splits varied. 95 bps is
# therefore the documented headline rate in an adjacent population -- NOT a measured rate for these
# curves, whose per-launch schedules this corpus does not record. It is applied here only as a
# clearly-labelled sensitivity, because a flow reported before any fee is easy to misread as a
# result, and the fee is the same order of magnitude as the flows themselves.
DOCUMENTED_FEE_BPS = 95


def _documented_curve_fee(position):
    """Both legs at the documented headline rate. A lower bound on cost, not a cost measurement.

    A lower bound because it omits execution costs entirely -- base fee, priority fee and the ATA
    rent that is charged on entry and never refunded -- all of which B15D froze and B15Q applied,
    and none of which this corpus records per wallet.
    """
    notional = position["quote_in_lamports"] + position["quote_out_lamports"]
    return notional * DOCUMENTED_FEE_BPS // 10_000


def _share(ranked_descending, total, fraction):
    if not ranked_descending or not total:
        return None
    take = max(1, int(len(ranked_descending) * fraction))
    return {"wallets": take, "positions": sum(ranked_descending[:take]),
            "share_pct_numerator": sum(ranked_descending[:take]), "share_pct_denominator": total}


NOT_MEASURABLE = {
    "profitability": ("not computed and not computable here. A position's observed quote flow "
                      "covers one curve inside one window, before the curve fees and execution "
                      "costs this corpus does not record, and a wallet may have moved tokens out."),
    "token_transfers": ("invisible. Only Pump program instructions are collected, so a wallet that "
                        "sent its tokens elsewhere looks identical to one still holding."),
    "identity_ownership": ("never inferred. `creator_like` means a wallet equals a recorded field, "
                           "not that two wallets are one operator."),
    "wallet_history_outside_the_window": ("absent. A wallet's first appearance here is not its "
                                          "first trade, and its last is not its last."),
    "executable_cost_and_capacity_per_wallet": (
        "not available in this corpus: the per-launch fee basis points are not recorded here, which "
        "is exactly the gap B15P existed to fill for a different population. B15Q's published "
        "capacity and cost figures describe ITS OWN 5,000-launch population and are not transferable "
        "to these curves."),
    "advertised_bot_features": ("out of scope by construction. This module measures observed "
                                "on-chain behaviour only and makes no claim about what any tool "
                                "advertises."),
}


def run(b9d_path=B9D, b10b_path=B10B, identity_path=B10C_IDENTITY):
    validation = assert_user_index_is_sound(b9d_path, identity_path)
    trades, excluded = load_trades(b9d_path)
    curves = load_curves(b10b_path, identity_path)
    positions = wallet_curve_positions(trades, curves)
    classify(positions)
    return summarise(positions, trades, excluded, validation, curves)


def main(argv=None):
    parser = argparse.ArgumentParser(description="B16a operator archetype audit (offline, burned)")
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
