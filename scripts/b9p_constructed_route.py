#!/usr/bin/env python3
"""B9p — the exact transaction we would construct, and a causal audit of every residual against it.

Offline, read-only, no network. Provenance in `research/B9P_CONSTRUCTED_ROUTE_AUDIT.md`.

B9n called a transaction "direct route" when every program in it was pinned. That predicate is too
loose in two ways, and both mattered:

1. It admits transactions containing **no Pump trade at all** — a creator harvesting fees uses only
   pinned programs and is not an instance of our route.
2. It admits **companion instructions** the observed trader bundled alongside the trade — closing a
   volume accumulator, claiming cashback, tipping, transferring tokens. We would submit none of
   them, so their lamport effects are not our costs.

Our constructed transaction is exactly: compute-budget, optional ATA creation, **exactly one** Pump
trade with its CPI subtree, and optionally closing our own ATA on exit. This module states that
shape, and attributes each residual to the companion instruction that causes it.

Nothing here filters the evaluation population. Which historical decisions are eligible is a
point-in-time predicate on the token; this module only decides which lamport movements are OURS.
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
B9L = B9K.B9L
B9J = B9K.B9J
FreezeViolation = B9D.FreezeViolation

COMPUTE_BUDGET = "ComputeBudget111111111111111111111111111111"
ASSOCIATED_TOKEN = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
SYSTEM_PROGRAM = "11111111111111111111111111111111"

# The Pump trade instructions. Our constructed transaction contains EXACTLY ONE of these.
TRADE_INSTRUCTIONS = frozenset({
    "buy", "buy_exact_sol_in", "buy_v2", "buy_exact_quote_in_v2", "sell", "sell_v2"})

# The companion that causes every explained residual in this artifact: it closes the user's volume
# accumulator PDA and sends its whole balance to the user. Accounts, from the pinned Pump IDL:
# [0] user (writable, signer) receives; [1] user_volume_accumulator (writable) is closed.
CLOSE_ACCUMULATOR = "close_user_volume_accumulator"
CLOSE_ACCUMULATOR_TARGET = 1

# The second companion credit source, and the only one outside the accumulator lifecycle: a creator
# harvesting accrued PumpSwap fees. Its event states the amount exactly, so it is reconciled rather
# than estimated. Doubly outside our route -- PumpSwap is not an entry venue at all.
COIN_CREATOR_FEE_EVENT = "CollectCoinCreatorFeeEvent"
COIN_CREATOR_FEE_FIELD = "coin_creator_fee"

CONSTRUCTED, COMPANION = "constructed", "companion"

# Audit outcomes. Deliberately named after what they license, not after how they feel.
CASE_A_OUTSIDE_ROUTE = "A_outside_constructed_route"
CASE_B_IN_TRADE_SUBTREE = "B_inside_trade_subtree"
CASE_C_INSUFFICIENT = "C_insufficient_evidence"
AUDIT_CASES = (CASE_A_OUTSIDE_ROUTE, CASE_B_IN_TRADE_SUBTREE, CASE_C_INSUFFICIENT)


def idl_maps(idls):
    return {program: B9D.idl_instruction_map(idl) for program, idl in idls.items()}


def outer_instruction_role(envelope, maps):
    """Classify one OUTER instruction as part of our constructed transaction, or a companion.

    Returns `(role, label)`. The default is COMPANION: an instruction this function does not
    recognise is something we would not submit, and calling it constructed would silently adopt a
    stranger's cost as our own.
    """
    program, data = envelope["program_id"], envelope["data"]
    if program == COMPUTE_BUDGET:
        return CONSTRUCTED, "computebudget"
    if program == ASSOCIATED_TOKEN:
        return CONSTRUCTED, "ata_create"
    if program in (B9L.TOKEN_PROGRAM, B9L.TOKEN_2022_PROGRAM):
        try:
            name = B9L.decode_token_instruction(data)["name"]
        except FreezeViolation:
            return COMPANION, "token:undecodable"
        # Closing our own token account is part of an exit. Every other token instruction at outer
        # level -- transfers especially -- is the trader moving their own funds around.
        if name == "CloseAccount":
            return CONSTRUCTED, "token:CloseAccount"
        return COMPANION, f"token:{name}"
    if program in (B9D.PUMP_PROGRAM, B9D.PUMPSWAP_PROGRAM):
        _, name, discriminator, _ = B9D.classify_instruction(program, data, maps)
        if program == B9D.PUMP_PROGRAM and name in TRADE_INSTRUCTIONS:
            return CONSTRUCTED, f"pump:{name}"
        prefix = "pump" if program == B9D.PUMP_PROGRAM else "pumpswap"
        return COMPANION, f"{prefix}:{name or discriminator}"
    return COMPANION, f"other:{program}"


def constructed_trades(envelopes, maps):
    """The Pump trade instructions at outer level. Our route holds exactly one."""
    return [envelope for envelope in envelopes
            if envelope["inner_index"] == -1
            and outer_instruction_role(envelope, maps)[0] == CONSTRUCTED
            and outer_instruction_role(envelope, maps)[1].startswith("pump:")]


def is_constructed_route(envelopes, maps):
    """A transaction has our route's SHAPE only if it carries exactly one Pump trade.

    A fee-harvest transaction touches only pinned programs and contains no trade at all; B9n's
    program-only predicate admitted one, and its 11.115 SOL residual then dominated a
    trade-cost diagnostic by 18x. Shape is decided by the trade, not by the program set.
    """
    return len(constructed_trades(envelopes, maps)) == 1


def accumulator_closure_credit(result, idls, maps):
    """Lamports the payer receives because a companion closed their volume accumulator.

    The account's ENTIRE balance at close reaches the user, so the amount is its balance *at that
    moment* -- not its pre-transaction balance. An accumulator created inside the same transaction
    has a pre-balance of zero while still refunding full rent, which is the same trap that made
    `CloseAccount` rent wrong when it was read from pre-balances.

    Balance at close is therefore reconstructed from pinned semantics: pre-balance, plus System
    lamports credited to it, plus cashback the trade paid into it. Returns 0 when no accumulator is
    closed. Order-independent: it reads amounts and account identities, never instruction sequence.
    """
    meta = result.get("meta") or {}
    keys = B9D.resolve_account_keys(
        B9D.parse_message(B9D.base64.b64decode(result["transaction"][0])), meta)
    index = {key: position for position, key in enumerate(keys)}
    pre = meta["preBalances"]
    envelopes = B9D.envelope_instructions(result)

    closed = set()
    for envelope in envelopes:
        if envelope["program_id"] != B9D.PUMP_PROGRAM:
            continue
        _, name, _, _ = B9D.classify_instruction(
            envelope["program_id"], envelope["data"], maps)
        if name != CLOSE_ACCUMULATOR:
            continue
        if len(envelope["accounts"]) <= CLOSE_ACCUMULATOR_TARGET:
            raise FreezeViolation(
                f"{CLOSE_ACCUMULATOR} carries {len(envelope['accounts'])} accounts; the pinned IDL "
                "gives it a user and a user_volume_accumulator")
        closed.add(envelope["accounts"][CLOSE_ACCUMULATOR_TARGET])
    if not closed:
        return 0

    balance = sum(pre[index[account]] for account in closed if account in index)
    credits = []
    for envelope in envelopes:
        if envelope["program_id"] != SYSTEM_PROGRAM or len(envelope["accounts"]) < 2:
            continue
        try:
            decoded = B9J.decode_system_instruction(envelope["data"])
        except FreezeViolation:
            continue
        moved = B9J.system_lamports_moved(decoded)
        if moved is not None and envelope["accounts"][1] in closed:
            credits.append(moved)

    cashback = 0
    for envelope in envelopes:
        event = B9D.decode_anchor_cpi_event(
            envelope["program_id"], envelope["data"], idls)
        if event and event["name"] == "TradeEvent":
            cashback += event["fields"].get("cashback", 0)
    # The trade's cashback reaches the accumulator by exactly ONE mechanism per transaction: either
    # an explicit System credit, which the loop above already counted, or Pump moving it directly.
    # Adding both would double-count it -- observed on 3 of the 92.
    if cashback and cashback in credits:
        cashback = 0
    return balance + sum(credits) + cashback


def coin_creator_fee_credit(result, idls):
    """Lamports the payer receives from harvesting accrued PumpSwap creator fees.

    The event states the amount, so this is read from pinned evidence rather than inferred from
    balances. Nothing in our route collects creator fees -- we are not the creator of the tokens we
    trade, and PumpSwap is not an entry venue -- so this is always a companion.
    """
    total = 0
    for envelope in B9D.envelope_instructions(result):
        event = B9D.decode_anchor_cpi_event(
            envelope["program_id"], envelope["data"], idls)
        if event and event["name"] == COIN_CREATOR_FEE_EVENT:
            total += event["fields"][COIN_CREATOR_FEE_FIELD]
    return total


def companion_credit(result, idls, maps):
    """Every lamport the payer receives from instructions our route would not contain."""
    return (accumulator_closure_credit(result, idls, maps)
            + coin_creator_fee_credit(result, idls))


def audit_residual(result, idls, maps):
    """Attribute one unattributed residual to a cause. Returns a record carrying its case.

    Case A requires EXACT reconciliation -- the residual must equal the companion credit to the
    lamport. Anything else is B or C; neither is allowed to pass as explained.
    """
    record = B9K.reconcile_transaction(result, idls)
    residual = record["residual"]
    envelopes = B9D.envelope_instructions(result)
    shaped = is_constructed_route(envelopes, maps)
    credit = companion_credit(result, idls, maps)
    if credit and residual == -credit:
        case = CASE_A_OUTSIDE_ROUTE
    elif not shaped:
        # No single trade, so it is not an instance of our route at all and its lamports are not
        # our costs. Recorded as its own outcome rather than quietly dropped.
        case = CASE_C_INSUFFICIENT
    else:
        # A residual inside a transaction shaped like ours, not explained by any companion, is a
        # divergence in the route we would actually submit. That is a Phase 1 blocker.
        case = CASE_B_IN_TRADE_SUBTREE
    return {"case": case, "residual": residual, "companion_credit": -credit,
            "has_constructed_shape": shaped}


def audit(database, limit=None, progress=None):
    """Audit every `unattributed_movement` transaction whose programs are all pinned."""
    idls = B9K.pinned_idls()
    maps = idl_maps(idls)
    B9M = _load("b9m_unattributed_partition", "b9m_unattributed_partition.py")
    direct = set(B9M.DIRECT_ROUTE_PROGRAMS)
    query = "SELECT signature FROM transaction_coordinate ORDER BY signature"
    if limit:
        query += f" LIMIT {int(limit)}"
    report = {"scanned": 0, "audited": 0,
              "by_case": {case: 0 for case in AUDIT_CASES}, "blockers": []}
    for (signature,) in database.execute(query):
        raw = database.execute(
            "SELECT raw_zlib FROM raw_transaction WHERE signature=?", (signature,)).fetchone()[0]
        result = B9D.raw_result(raw)
        report["scanned"] += 1
        if {e["program_id"] for e in B9D.envelope_instructions(result)} - direct:
            continue
        if B9K.reconcile_transaction(result, idls)["category"] != "unattributed_movement":
            continue
        report["audited"] += 1
        outcome = audit_residual(result, idls, maps)
        report["by_case"][outcome["case"]] += 1
        if outcome["case"] == CASE_B_IN_TRADE_SUBTREE:
            report["blockers"].append(dict(outcome, signature=signature))
        if progress and report["scanned"] % progress == 0:
            print(f"  {report['scanned']:,} scanned, {report['audited']:,} audited",
                  file=sys.stderr, flush=True)
    total = sum(report["by_case"].values())
    if total != report["audited"]:
        raise FreezeViolation(
            f"audit assigned {total} of {report['audited']} residuals; the cases must be "
            "exhaustive")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress", type=int, default=None)
    args = parser.parse_args(argv)
    database = B9D.connect(args.artifact, readonly=True)
    try:
        report = audit(database, limit=args.limit, progress=args.progress)
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
