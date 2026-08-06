"""B16b — what is the creator-like positive median made of?

B16a found one cohort with a clearly positive median observed flow: wallets equal to a curve's
`creator` or `create_user` field. This decomposes that figure. It is EXPLORATORY AND DESCRIPTIVE,
it is not a profit measurement, and nothing here recommends issuance as a strategy.

Burned/published artifacts only. No network, no live file, nothing under `research/b11a`.

THE DISTINCTION THAT IS NOT ALLOWED TO BLUR
-------------------------------------------
"Creator-like" means a wallet EQUALS a recorded field on that curve. It does not mean the wallet is
owned by the launch's author, and no clustering, funding-graph or heuristic linkage is attempted. Two
addresses that behave alike are two addresses. Everything below is a statement about field equality.

WHAT THE FLOW DOES AND DOES NOT CONTAIN
---------------------------------------
The flow is a difference of BONDING-CURVE RESERVE deltas: quote the wallet's sells drew out, less
quote its buys put in. It therefore excludes, by construction:

* creator fee collection, cashback and buyback, which move lamports through vaults rather than
  through the curve's reserves;
* the cost of creating the token, the rent it consumes and every execution cost;
* anything the wallet did outside this corpus's program and window.

Those channels are counted SEPARATELY below where the corpus records them, and named as absent where
it does not. A channel that is absent is reported as absent, never as zero.
"""
import argparse
import collections
import importlib.util
import json
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B16A = _load("b16a_operator_archetypes", "b16a_operator_archetypes.py")

# Instructions that move lamports to a creator or user OUTSIDE the bonding-curve reserves. Present in
# the corpus but not in the flow, which is exactly why they are counted separately.
FEE_CHANNEL_NAMES = (
    "collect_creator_fee", "collect_creator_fee_v2", "collect_coin_creator_fee",
    "distribute_creator_fees", "distribute_creator_fees_v2",
    "transfer_creator_fees_to_pump", "transfer_creator_fees_to_pump_v2",
    "claim_cashback", "claim_cashback_v2", "claim_token_incentives",
)
MIGRATION_NAMES = ("migrate", "migrate_v2", "migrate_bonding_curve_creator",
                   "migrate_pool_coin_creator", "create_pool")


class DecompositionRefused(RuntimeError):
    """The evidence cannot support the split, so no figure is produced."""


def create_coordinates(b10b_path=B16A.B10B):
    """The (slot, transaction_index) of each curve's create, so a launch buy can be identified."""
    connection = B16A._read_only(b10b_path, "B10b")
    try:
        return {row[0]: (row[1], row[2]) for row in connection.execute(
            "SELECT bonding_curve, create_slot, create_transaction_index FROM curve")}
    finally:
        connection.close()


def fee_channel_activity(wallets, b9d_path=B16A.B9D):
    """Which non-curve lamport channels the corpus records AT ALL, and for whom.

    Counted by instruction name and by whether any account of the instruction is one of the wallets
    in question. Account membership is not authorship: an address appearing in an instruction is not
    necessarily the party being paid, so this is reported as PRESENCE, never as an amount.
    """
    connection = B16A._read_only(b9d_path, "B9d")
    try:
        names = FEE_CHANNEL_NAMES + MIGRATION_NAMES
        placeholders = ",".join("?" * len(names))
        totals = collections.Counter()
        touching = collections.Counter()
        for name, accounts_json in connection.execute(
                f"SELECT idl_name, accounts_json FROM instruction WHERE idl_name IN "
                f"({placeholders})", names):
            totals[name] += 1
            accounts = set(json.loads(accounts_json))
            if accounts & wallets:
                touching[name] += 1
        return {"instructions_in_corpus": dict(totals),
                "instructions_touching_a_creator_like_wallet": dict(touching)}
    finally:
        connection.close()


SPL_TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


def token_transfer_visibility(b9d_path=B16A.B9D):
    """Are token movements observable? Present but UNDECODED, which is not the same as absent.

    Saying transfers were "invisible" would have been an overclaim, and checking rather than
    asserting is what caught it: the corpus stores instructions from every program a collected
    transaction touched, including both token programs, in their thousands. What it does NOT do is
    decode them -- `idl_name` is null for every non-Pump program, because only the Pump IDL was
    pinned. So counterparties and amounts are not available WITHOUT FURTHER DECODING WORK that this
    audit did not do, rather than being unavailable in principle.
    """
    connection = B16A._read_only(b9d_path, "B9d")
    try:
        counts = dict(connection.execute(
            "SELECT program_id, COUNT(*) FROM instruction WHERE program_id IN (?,?) GROUP BY "
            "program_id", (SPL_TOKEN, TOKEN_2022)))
        decoded = connection.execute(
            "SELECT COUNT(*) FROM instruction WHERE program_id IN (?,?) AND idl_name IS NOT NULL",
            (SPL_TOKEN, TOKEN_2022)).fetchone()[0]
        distinct_programs = connection.execute(
            "SELECT COUNT(DISTINCT program_id) FROM instruction").fetchone()[0]
        return {
            "token_program_instructions_present": counts,
            "token_program_instructions_decoded": decoded,
            "distinct_programs_in_corpus": distinct_programs,
            "transfers_are_recorded_but_not_decoded": True,
            "why": ("only the Pump IDL was pinned, so every non-Pump instruction is stored with a "
                    "null idl_name. The raw material for transfer analysis exists; the decoding "
                    "does not, and this audit did not add it."),
            "consequence": ("a position that looks closed may not be, and one that looks open may "
                            "have been settled elsewhere. No flow figure here is bounded by "
                            "wallet-level inventory."),
        }
    finally:
        connection.close()


def decompose(positions, trades, creates):
    """Split each creator-like position by whether its buying happened in the create transaction."""
    by_pair = collections.defaultdict(list)
    for trade in trades:
        by_pair[(trade["wallet"], trade["bonding_curve"])].append(trade)

    decomposed = []
    for position in positions:
        if position["archetype"] != "creator_like_participant":
            continue
        key = (position["wallet"], position["bonding_curve"])
        rows = by_pair[key]
        create = creates.get(position["bonding_curve"])
        launch_buys, later_buys, sells = [], [], []
        for row in rows:
            if row["direction"] == "sell":
                sells.append(row)
            elif create is not None and (row["slot"], row["transaction_index"]) == create:
                launch_buys.append(row)
            else:
                later_buys.append(row)
        decomposed.append({
            **position,
            "launch_transaction_buys": len(launch_buys),
            "later_buys": len(later_buys),
            "sell_count": len(sells),
            "launch_quote_in_lamports": sum(r["quote_delta_lamports"] for r in launch_buys),
            "later_quote_in_lamports": sum(r["quote_delta_lamports"] for r in later_buys),
            "quote_out_lamports": -sum(r["quote_delta_lamports"] for r in sells),
            "bought_in_the_create_transaction": bool(launch_buys),
        })
    return decomposed


def role_of(position, identities):
    """`creator`, `create_user`, or `both` — field equality, never ownership."""
    row = identities.get(position["bonding_curve"])
    if row is None:
        return "unknown"
    creator, create_user = row
    is_creator = position["wallet"] == creator
    is_create_user = position["wallet"] == create_user
    if is_creator and is_create_user:
        return "both_fields_name_this_wallet"
    if is_creator:
        return "creator_only"
    if is_create_user:
        return "create_user_only"
    return "neither"


def load_identities(identity_path=B16A.B10C_IDENTITY):
    connection = B16A._read_only(identity_path, "B10c identity")
    try:
        return {row[0]: (row[1], row[2]) for row in connection.execute(
            "SELECT bonding_curve, creator, create_user FROM identity")}
    finally:
        connection.close()


def _stats(rows, key):
    return B16A.order_statistics([r[key] for r in rows])


def _flow_with_fee(row):
    return row["observed_quote_flow_lamports"] - B16A._documented_curve_fee(row)


def run(b9d_path=B16A.B9D, b10b_path=B16A.B10B, identity_path=B16A.B10C_IDENTITY):
    B16A.assert_user_index_is_sound(b9d_path, identity_path)
    trades, excluded = B16A.load_trades(b9d_path)
    curves = B16A.load_curves(b10b_path, identity_path)
    positions = B16A.wallet_curve_positions(trades, curves)
    B16A.classify(positions)
    creates = create_coordinates(b10b_path)
    identities = load_identities(identity_path)
    rows = decompose(positions, trades, creates)
    if not rows:
        raise DecompositionRefused("no creator-like positions to decompose")

    resolved = [r for r in rows if not r["inventory_unresolved"]]
    unresolved = [r for r in rows if r["inventory_unresolved"]]
    for row in rows:
        row["role"] = role_of(row, identities)
        row["flow_less_documented_fee"] = _flow_with_fee(row)

    def block(subset, label, note=None):
        entry = {
            "positions": len(subset),
            "distinct_wallets": len({r["wallet"] for r in subset}),
            "distinct_curves": len({r["bonding_curve"] for r in subset}),
            "observed_quote_flow_lamports": _stats(subset, "observed_quote_flow_lamports"),
            "flow_less_documented_fee_lamports": _stats(subset, "flow_less_documented_fee"),
            "quote_in_lamports": _stats(subset, "quote_in_lamports"),
        }
        if note:
            entry["note"] = note
        return {label: entry}

    with_launch = [r for r in resolved if r["bought_in_the_create_transaction"]]
    without_launch = [r for r in resolved if not r["bought_in_the_create_transaction"]]

    roles = collections.Counter(r["role"] for r in rows)
    by_role = {}
    for role in sorted(roles):
        subset = [r for r in resolved if r["role"] == role]
        if subset:
            by_role.update(block(subset, role))

    wallets = {r["wallet"] for r in rows}
    report = {
        "study": "B16B_CREATOR_FLOW_DECOMPOSITION",
        "status": ("EXPLORATORY AND DESCRIPTIVE. Not a profit measurement and not a recommendation "
                   "to issue tokens."),
        "executable": False,
        "performance_status": "not_evaluated",
        "execution_status": "never_executed",
        "wallet_equality_is_not_ownership": (
            "every figure below is about wallets EQUAL to a recorded creator or create_user field. "
            "No clustering, funding graph or heuristic linkage was attempted, and no claim is made "
            "that any two addresses share an owner."),
        "denominators": {
            "creator_like_positions": len(rows),
            "fully_exited": len(resolved),
            "inventory_unresolved_and_therefore_excluded_from_every_flow": len(unresolved),
            "unresolved_share_note": ("a position still holding has no closing price, so it carries "
                                      "no flow figure at all rather than a zero"),
            "trades_excluded_upstream": excluded,
        },
        "headline_being_decomposed": block(resolved, "all_fully_exited")["all_fully_exited"],
        "does_it_survive_excluding_launch_transaction_activity": {
            **block(with_launch, "bought_in_the_create_transaction"),
            **block(without_launch, "did_not_buy_in_the_create_transaction"),
            "reading": ("the two subsets are reported side by side. A result that lives only in the "
                        "first is a statement about buying at the curve's opening reserves, not "
                        "about creators trading well afterwards."),
        },
        "by_role": {
            **by_role,
            "role_tally_over_all_creator_like_positions": dict(roles),
            "limit": ("creator and create_user name the SAME wallet on 1,120 of 1,136 curves, so "
                      "the roles cannot be separated meaningfully in this corpus. The split is "
                      "reported for completeness and its denominators are the point."),
        },
        "channels_outside_the_flow": {
            **fee_channel_activity(wallets, b9d_path),
            "why_separate": ("creator fees, cashback and buyback move lamports through vaults, not "
                             "through the curve reserves, so they are absent from the flow by "
                             "construction. Presence is reported; amounts are not, because an "
                             "address appearing in an instruction is not proof it was paid."),
        },
        "token_transfers": token_transfer_visibility(b9d_path),
        "not_claimed": {
            "profit": ("not claimed. Complete wallet-level costs, inventory and transfers are not "
                       "available, and without all three a flow is not a result."),
            "issuance_as_a_strategy": ("not recommended and not evaluated. This decomposes an "
                                       "observation; it does not endorse the behaviour it describes "
                                       "and says nothing about its legality, ethics or durability."),
        },
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="B16b creator-flow decomposition (offline, burned)")
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
