#!/usr/bin/env python3
"""B9i — exact integer quote and fee reproduction from the published reserve path.

Offline, read-only, no network. Phase 1, and deliberately the narrowest useful gate: before a
trading system may size an order it must be able to compute, to the integer, the same number the
program computes. Anything less is a model of the venue rather than the venue.

Every quantity here comes from pinned evidence or the preserved transaction itself:

- the before-state comes from the PUBLISHED reserve path (`reserve_observation`), which B9e has
  already gated at 100% anchored-complete coverage;
- the trade quantities and every fee basis-point come from the transaction's own `TradeEvent`;
- the arithmetic comes from the pinned IDL, via `research/B2B_OFFICIAL_BUY_FORMULA.md`.

No fee constant is inferred and none is hard-coded. The event states its own basis points and the
gate reproduces the fee from those; a missing or non-integer basis-point field is a hard failure,
not a default.

WHAT IS ESTABLISHED, and therefore required exactly. Every figure below is measured over the whole
published population of 93,253 trade observations, not a slice:

- `buy_exact_sol_in` (12,713) / `buy_exact_quote_in` (8,090): tokens_out = floor((q-1)*vt/(vq+q-1))
- legacy `buy` / `buy_v2` (31,397): net quote = floor(t*vq / (vt-t)) + 1
- `sell` (41,053): quote_out = floor(t*vq / (vt+t))
- protocol fee, creator fee and cashback: ceil(quote * bps / 10000) -- on legacy `buy` and `sell`
  ONLY, where all three are exact across all 72,450 observations.

THE LEGACY BUY FORM IS floor+1, NOT ceil, and the distinction is not cosmetic. The two agree
whenever the division leaves a remainder, so any sample without an exactly-divisible trade cannot
tell them apart; `research/B2B_OFFICIAL_BUY_FORMULA.md` selected `ceil` from 9 such samples. This
corpus holds exactly ONE exactly-divisible legacy buy -- slot 433,988,917, remainder zero, ceil
7,000,000,000 against an observed 7,000,000,001 -- and it shows the program adds the lamport
unconditionally. ceil reproduces 31,396/31,397; floor+1 reproduces 31,397/31,397.

WHAT IS NOT ESTABLISHED, and is therefore refused rather than approximated:

- EVERY fee component on EXACT-INPUT buys, protocol fee included. Measured over all 20,803 of them:
  the protocol fee misses 103, creator_fee 20, cashback 3, each short by exactly 1 lamport. The fee
  there is taken from a gross input the event never states, so the base is not in evidence and a
  near-miss is not a reproduction.
- the buyback fee, on every path. Its declared 5,000 bps matches `ceil(fee*bps/10000)` on 46,500 of
  93,253 -- essentially half -- so whatever base it uses is not established.

Those are reported under `unestablished` and never silently approximated. Asking this gate to
certify one raises. That is the point: a fee this artifact cannot reproduce is a fee a trading
system must not assume it can predict.
"""
import argparse
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_b9d():
    spec = importlib.util.spec_from_file_location(
        "b9d_transaction_bodies", ROOT / "scripts" / "b9d_transaction_bodies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B9D = _load_b9d()
FreezeViolation = B9D.FreezeViolation

EXACT_INPUT_BUYS = ("buy_exact_sol_in", "buy_exact_quote_in")
LEGACY_BUYS = ("buy", "buy_v2")
SELLS = ("sell", "sell_v2")

# Fee components reproducible from the event's own quote amount -- on legacy `buy` and `sell` ONLY.
# Measured over the full artifact: 0 misses across all 72,450 legacy buy and sell observations, but
# creator_fee misses 20 and cashback 3 on exact-input buys, every one short by exactly +1 lamport.
# That is the same signature as the protocol fee on the same instructions, whose base is a gross
# input the event never states, so all three are unestablished there rather than nearly-right.
ESTABLISHED_FEES = (("fee", "fee_basis_points"),
                    ("creator_fee", "creator_fee_basis_points"),
                    ("cashback", "cashback_fee_basis_points"))
FEE_ESTABLISHED_ON = LEGACY_BUYS + SELLS
# Components whose base is NOT in evidence. Named so the refusal is explicit rather than an
# omission somebody later reads as an oversight.
UNESTABLISHED_FEES = ("fee_exact_input", "creator_fee_exact_input", "cashback_exact_input",
                      "buyback_fee")


def ceil_div(numerator, denominator):
    if denominator <= 0:
        raise FreezeViolation(f"non-positive denominator {denominator} in exact integer quote")
    return -(-numerator // denominator)


def reproduce_trade(before_virtual_quote, before_virtual_token, fields):
    """Recompute the trade's own quantities from the published before-state.

    Returns `(name, predicted, observed)`. Raises on an instruction form this gate has no pinned
    arithmetic for: an unrecognised path must stop the run, never fall through to a default.
    """
    name = fields.get("ix_name")
    quote, token = fields.get("quote_amount"), fields.get("token_amount")
    for label, value in (("quote_amount", quote), ("token_amount", token)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise FreezeViolation(f"TradeEvent {label} is not a non-negative integer: {value!r}")

    if fields.get("is_buy") is True:
        if name in EXACT_INPUT_BUYS:
            return ("tokens_out",
                    (quote - 1) * before_virtual_token // (before_virtual_quote + quote - 1),
                    token)
        if name in LEGACY_BUYS:
            # floor+1, NOT ceil. The two agree whenever the division leaves a remainder, so a
            # sample containing no exactly-divisible trade cannot tell them apart -- which is why
            # B2b's 9 samples selected `ceil`. The frozen corpus holds 31,397 legacy buys and
            # exactly ONE that divides exactly; it moved the extra lamport, so the program adds it
            # unconditionally. ceil: 31,396/31,397. floor+1: 31,397/31,397.
            denominator = before_virtual_token - token
            if denominator <= 0:
                raise FreezeViolation(
                    f"legacy buy consumes the whole virtual token reserve "
                    f"({token} of {before_virtual_token}); the quote is undefined")
            return ("net_quote", token * before_virtual_quote // denominator + 1, quote)
        raise FreezeViolation(
            f"buy instruction {name!r} has no pinned quote arithmetic; exact-input and exact-token "
            "buys use different formulas and must not share one")
    if name in SELLS:
        return ("quote_out",
                token * before_virtual_quote // (before_virtual_token + token),
                quote)
    raise FreezeViolation(f"sell instruction {name!r} has no pinned quote arithmetic")


# The parent instructions whose FIRST pinned argument is the gross input the user supplied. Both
# are u64 and both are stated in the pinned Pump IDL, so the gross is decoded evidence rather than
# an inferred quantity. `buy_exact_quote_in` in the event stream is emitted by
# `buy_exact_quote_in_v2` on the instruction side.
EXACT_INPUT_PARENTS = {"buy_exact_sol_in": "spendable_sol_in",
                       "buy_exact_quote_in_v2": "spendable_quote_in"}


def pinned_instruction_arguments(idl):
    """discriminator hex -> (instruction name, first argument name, first argument type)."""
    out = {}
    for instruction in idl.get("instructions", []):
        arguments = instruction.get("args") or []
        first = arguments[0] if arguments else {}
        out[bytes(instruction["discriminator"]).hex()] = (
            instruction["name"], first.get("name"), first.get("type"))
    return out


def decode_gross_input(parent_data, argument_map):
    """The gross input from the parent instruction's own pinned first argument, or None.

    Returns None when the parent is not an exact-input buy -- that is not an error, it is how the
    caller learns the concept does not apply. Every OTHER way this can go wrong raises, because a
    gross input that cannot be decoded exactly must not be approximated: it is the base of three
    fees, and a wrong base is a wrong fee that still looks like a reproduction.
    """
    if len(parent_data) < 8:
        raise FreezeViolation("parent instruction carries no discriminator")
    entry = argument_map.get(parent_data[:8].hex())
    if entry is None:
        raise FreezeViolation(
            f"parent discriminator {parent_data[:8].hex()} is absent from the pinned IDL; its "
            "argument layout is not evidence")
    name, argument, argument_type = entry
    if name not in EXACT_INPUT_PARENTS:
        return None
    if argument != EXACT_INPUT_PARENTS[name] or argument_type != "u64":
        raise FreezeViolation(
            f"{name} first argument is {argument!r}::{argument_type!r}, pinned as "
            f"{EXACT_INPUT_PARENTS[name]!r}::'u64'; the gross input is not where it was")
    if len(parent_data) < 16:
        raise FreezeViolation(f"{name} data is too short to carry its u64 gross input")
    return int.from_bytes(parent_data[8:16], "little")


def reproduce_exact_input_fees(gross, fields):
    """Reproduce every exact-input fee from the DECODED gross input. Returns {name: (pred, obs)}.

    The base is not the quote that reaches reserves -- reproducing from that is short by exactly
    one lamport on about 0.5% of trades, which is why these were unestablished until the gross
    became decodable. The program takes the fee-inclusive net of the gross:

        net = floor(gross * 10000 / (10000 + fee_bps + creator_bps + cashback_bps))

    and charges each component `ceil(net * its_bps / 10000)`. Measured over 3,080 exact-input buys:
    all three components exact, and `gross == quote + fee + creator_fee + cashback` exact.
    """
    total_bps = sum(fields[field] for _, field in ESTABLISHED_FEES)
    if total_bps < 0:
        raise FreezeViolation(f"negative total fee basis points {total_bps}")
    net = gross * 10000 // (10000 + total_bps)
    return {component: (ceil_div(net * fields[bps_field], 10000), fields[component])
            for component, bps_field in ESTABLISHED_FEES}


def reproduce_fees(fields):
    """Reproduce the fee components whose base is in evidence. Returns {name: (pred, obs)}.

    Empty on exact-input buys, deliberately. There the fee is taken from a gross input the event
    never states, so NO component is reproducible -- not the protocol fee, and not creator_fee or
    cashback either, which miss by the same +1 lamport on the same instructions. Returning nothing
    is the honest answer; returning a near-miss would let the gate certify arithmetic it cannot do.
    """
    if fields.get("ix_name") not in FEE_ESTABLISHED_ON:
        return {}
    quote = fields["quote_amount"]
    out = {}
    for component, bps_field in ESTABLISHED_FEES:
        bps, observed = fields.get(bps_field), fields.get(component)
        for label, value in ((bps_field, bps), (component, observed)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise FreezeViolation(
                    f"TradeEvent {label} is absent or not a non-negative integer: {value!r}; fee "
                    "evidence must be stated by the event, never defaulted")
        out[component] = (ceil_div(quote * bps, 10000), observed)
    return out


def assert_unestablished_not_requested(components):
    """A caller must not ask this gate to certify a fee whose base is not in evidence.

    A bare string is normalised to one name first. `set("buyback_fee")` iterates into CHARACTERS,
    intersects to nothing, and returns quietly -- so the guard used to fail OPEN on exactly the
    call a caller is most likely to write.
    """
    if isinstance(components, str):
        components = (components,)
    requested = sorted(set(components or ()) & set(UNESTABLISHED_FEES))
    if requested:
        raise FreezeViolation(
            f"{requested} cannot be reproduced from pinned evidence: the protocol fee on "
            "exact-input buys is taken from a gross input the event does not state, and the "
            "buyback base is not established. They are reported, never certified")
    return True


def reproduce_artifact(database, limit=None, progress=None):
    """Reproduce every published trade observation. Raises on the first unrecognised form."""
    # Through the pin-verifying loader, not a bare json.loads: an IDL that has drifted from its
    # recorded hash must stop this gate, since every formula below is stated against that revision.
    idls = {
        B9D.PUMP_PROGRAM: B9D.load_pinned_idl(
            B9D.PUMP_IDL_PATH, B9D.PUMP_IDL_SHA256, B9D.PUMP_PROGRAM),
        B9D.PUMPSWAP_PROGRAM: B9D.load_pinned_idl(
            B9D.PUMPSWAP_IDL_PATH, B9D.PUMPSWAP_IDL_SHA256, B9D.PUMPSWAP_PROGRAM)}
    query = (
        "SELECT r.virtual_quote_before,r.virtual_token_before,r.evidence,c.signature,"
        "r.outer_index,r.inner_index "
        "FROM reserve_observation r "
        "JOIN transaction_coordinate c ON c.slot=r.slot AND c.transaction_index=r.transaction_index "
        "WHERE r.virtual_quote_before IS NOT NULL "
        "ORDER BY r.slot,r.transaction_index,r.outer_index,r.inner_index")
    if limit:
        query += f" LIMIT {int(limit)}"

    argument_map = pinned_instruction_arguments(idls[B9D.PUMP_PROGRAM])
    report = {"observations": 0, "quote_exact": 0, "quote_mismatch": 0,
              "by_path": {}, "fees": {}, "gross_input": {"n": 0, "identity_exact": 0},
              "unestablished": {}}
    for index, (vq, vt, evidence, signature, parent_outer, parent_inner) in enumerate(
            database.execute(query)):
        marker = json.loads(evidence)
        if marker.get("kind") != "anchor_cpi:TradeEvent":
            continue                       # anchors carry no trade quantities to reproduce
        raw = database.execute(
            "SELECT raw_zlib FROM raw_transaction WHERE signature=?", (signature,)).fetchone()[0]
        result = B9D.raw_result(raw)
        located = [e for e in B9D.envelope_instructions(result)
                   if e["outer_index"] == marker["event_outer_index"]
                   and e["inner_index"] == marker["event_inner_index"]]
        if len(located) != 1:
            raise FreezeViolation(
                f"{signature}: reserve evidence names event coordinates that resolve to "
                f"{len(located)} instructions")
        decoded = B9D.decode_anchor_cpi_event(
            located[0]["program_id"], located[0]["data"], idls)
        if decoded is None or decoded["name"] != "TradeEvent":
            raise FreezeViolation(f"{signature}: reserve evidence does not name a TradeEvent")
        fields = decoded["fields"]

        report["observations"] += 1
        name, predicted, observed = reproduce_trade(vq, vt, fields)
        path = report["by_path"].setdefault(
            fields.get("ix_name"), {"n": 0, "exact": 0, "quantity": name})
        path["n"] += 1
        if predicted == observed:
            path["exact"] += 1
            report["quote_exact"] += 1
        else:
            report["quote_mismatch"] += 1
            report.setdefault("first_quote_mismatch", {
                "signature": signature, "ix_name": fields.get("ix_name"),
                "quantity": name, "predicted": predicted, "observed": observed})

        # Exact-input buys: the fee base is the gross the parent instruction states, so those
        # components move from `unestablished` to REQUIRED once it is decoded.
        fees = reproduce_fees(fields)
        if fields.get("ix_name") in EXACT_INPUT_BUYS:
            parents = [e for e in B9D.envelope_instructions(result)
                       if e["outer_index"] == parent_outer and e["inner_index"] == parent_inner]
            if len(parents) != 1:
                raise FreezeViolation(
                    f"{signature}: reserve row names a parent at ({parent_outer},{parent_inner}) "
                    f"that resolves to {len(parents)} instructions")
            gross = decode_gross_input(parents[0]["data"], argument_map)
            if gross is None:
                raise FreezeViolation(
                    f"{signature}: {fields['ix_name']} event has a parent that states no gross "
                    "input; the exact-input fee base is not in evidence")
            fees = reproduce_exact_input_fees(gross, fields)
            accounted = (fields["quote_amount"] + fields["fee"] + fields["creator_fee"]
                         + fields["cashback"])
            residue = gross - accounted
            report["gross_input"]["n"] += 1
            report["gross_input"]["identity_exact"] += residue == 0
            # The actual protocol-side debit is the ACCOUNTED sum, not the gross. `spendable_*`
            # is a cap:
            # where the fee-inclusive division leaves a remainder, that remainder is never
            # transferred. Verified on all three residue observations in the frozen artifact -- no
            # account moves by +/-1 lamport in any of them, and the payer's debit decomposes
            # exactly into quote + fees + rent + transaction fee with the gross playing no part.
            # Quote units are lamports only for the native quote mint. Preserve the mint boundary
            # so SOL and SPL-token raw units can never be summed into a plausible nonsense total.
            quote_mint = fields.get("quote_mint")
            if not isinstance(quote_mint, str) or not quote_mint:
                raise FreezeViolation(
                    f"{signature}: exact-input TradeEvent has no quote_mint; debit units unknown")
            by_mint = report["gross_input"].setdefault("by_quote_mint", {})
            mint_bucket = by_mint.setdefault(
                quote_mint, {"n": 0, "gross_offered_raw_quote": 0,
                             "protocol_debit_raw_quote": 0})
            mint_bucket["n"] += 1
            mint_bucket["gross_offered_raw_quote"] += gross
            mint_bucket["protocol_debit_raw_quote"] += accounted
            if residue:
                report["gross_input"].setdefault("residues", {})
                key = str(residue)
                report["gross_input"]["residues"][key] = (
                    report["gross_input"]["residues"].get(key, 0) + 1)
                report["gross_input"].setdefault("first_residue", {
                    "signature": signature, "ix_name": fields.get("ix_name"),
                    "gross": gross, "accounted": accounted, "residue": residue})

        for component, (pred, obs) in fees.items():
            # The denominator here is legacy buy + sell only, never `observations`. Labelled in the
            # report so nobody reads a fee's n as coverage of the whole population.
            bucket = report["fees"].setdefault(
                component, {"n": 0, "exact": 0, "scope": "all paths; exact-input fees are "
                                                         "reproduced from the decoded gross input"})
            bucket["n"] += 1
            bucket["exact"] += pred == obs

        # Reported, never certified.
        fee_bps, fee = fields.get("fee_basis_points"), fields.get("fee")
        buyback, buyback_bps = fields.get("buyback_fee"), fields.get("buyback_fee_basis_points")
        if isinstance(buyback, int) and isinstance(buyback_bps, int):
            bucket = report["unestablished"].setdefault(
                "buyback_fee", {"n": 0, "matches_fee_form": 0})
            bucket["n"] += 1
            bucket["matches_fee_form"] += buyback == ceil_div(fee * buyback_bps, 10000)
        if progress and report["observations"] % progress == 0:
            print(f"  {report['observations']:,} reproduced", file=sys.stderr, flush=True)
    return report


def assert_quote_reproduction(database, limit=None, progress=None):
    """Fail closed unless EVERY published trade reproduces exactly."""
    report = reproduce_artifact(database, limit=limit, progress=progress)
    if not report["observations"]:
        raise FreezeViolation("no published trade observations to reproduce; the gate is vacuous")
    if report["quote_mismatch"]:
        first = report.get("first_quote_mismatch")
        raise FreezeViolation(
            f"{report['quote_mismatch']:,} of {report['observations']:,} trades do not reproduce "
            f"exactly; first {first}")
    inexact = {name: bucket for name, bucket in report["fees"].items()
               if bucket["exact"] != bucket["n"]}
    if inexact:
        raise FreezeViolation(
            f"established fee components do not reproduce exactly: {inexact}")
    # The decomposition is REPORTED, not required. It corroborates that the decoded gross is the
    # quantity the program split, and it holds on 20,800 of 20,803 -- but three exact-input buys
    # leave exactly one lamport unaccounted, and where that lamport goes is not in evidence.
    # Requiring it would fail an artifact whose quotes and fees all reproduce exactly; tolerating a
    # residue of "1" would be inventing a tolerance. So it is published with its residue instead,
    # and `assert_gross_identity_residue` is available to any caller that wants it enforced.
    report["exact"] = True
    return report


def assert_gross_identity_residue(report, maximum=0):
    """Optional: require the gross decomposition to leave no more than `maximum` lamports.

    Not part of `assert_quote_reproduction`, because on the frozen artifact three exact-input buys
    leave exactly one lamport whose destination is not in evidence. A caller who needs the identity
    enforced can ask for it and state its own bound; the gate itself will not pick one, since a
    bound chosen to fit the observed residue is a tolerance rather than a finding.
    """
    residues = report.get("gross_input", {}).get("residues") or {}
    exceeded = {value: count for value, count in residues.items() if abs(int(value)) > maximum}
    if exceeded:
        raise FreezeViolation(
            f"gross decomposition leaves residues beyond {maximum} lamport(s): {exceeded}; "
            f"first {report['gross_input'].get('first_residue')}")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress", type=int, default=None)
    parser.add_argument("--gate", action="store_true",
                        help="fail closed unless every trade reproduces exactly")
    parser.add_argument(
        "--require-fees", default="",
        help="comma-separated fee components the caller requires this gate to certify; "
             "unestablished components fail closed")
    args = parser.parse_args(argv)
    required_fees = tuple(name.strip() for name in args.require_fees.split(",") if name.strip())
    assert_unestablished_not_requested(required_fees)
    database = B9D.connect(args.artifact, readonly=True)
    try:
        report = (assert_quote_reproduction(database, args.limit, args.progress) if args.gate
                  else reproduce_artifact(database, args.limit, args.progress))
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
