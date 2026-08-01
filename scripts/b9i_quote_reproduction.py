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
        "SELECT r.virtual_quote_before,r.virtual_token_before,r.evidence,c.signature "
        "FROM reserve_observation r "
        "JOIN transaction_coordinate c ON c.slot=r.slot AND c.transaction_index=r.transaction_index "
        "WHERE r.virtual_quote_before IS NOT NULL "
        "ORDER BY r.slot,r.transaction_index,r.outer_index,r.inner_index")
    if limit:
        query += f" LIMIT {int(limit)}"

    report = {"observations": 0, "quote_exact": 0, "quote_mismatch": 0,
              "by_path": {}, "fees": {}, "unestablished": {}}
    for index, (vq, vt, evidence, signature) in enumerate(database.execute(query)):
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

        for component, (pred, obs) in reproduce_fees(fields).items():
            # The denominator here is legacy buy + sell only, never `observations`. Labelled in the
            # report so nobody reads a fee's n as coverage of the whole population.
            bucket = report["fees"].setdefault(
                component, {"n": 0, "exact": 0, "scope": "legacy buy and sell only"})
            bucket["n"] += 1
            bucket["exact"] += pred == obs

        # Reported, never certified.
        fee_bps, fee = fields.get("fee_basis_points"), fields.get("fee")
        if fields.get("ix_name") in EXACT_INPUT_BUYS and isinstance(fee, int):
            bucket = report["unestablished"].setdefault(
                "fee_exact_input", {"n": 0, "matches_net_form": 0})
            bucket["n"] += 1
            bucket["matches_net_form"] += fee == ceil_div(fields["quote_amount"] * fee_bps, 10000)
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
    report["exact"] = True
    return report


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
