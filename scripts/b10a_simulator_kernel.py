#!/usr/bin/env python3
"""B10a — deterministic direct-Pump simulator kernel. Phase 2, first bounded slice.

Offline, read-only, no network. Pure library: no server, no UI, no model, no signal, no wallet, no
signing, no live RPC. Schema in `docs/SIMULATOR_RESULT_SCHEMA.md`.

Prices ONE hypothetical direct Pump bonding-curve round trip against decision-time canonical state.
It reuses the integer curve and fee functions from `b9i`, which reproduce the frozen artifact
exactly, rather than carrying its own copy -- a simulator with a private formula drifts from the
gate that validates it, and the drift is invisible until it matters.

THREE THINGS THIS KERNEL REFUSES TO DO, because each is a way a backtest lies to its author:

1. **It never invents an execution parameter.** Priority fee, tip, landing probability, latency and
   slippage are unmeasured in this project. A missing one yields `incomplete_scenario`, never a
   default. Zero is not a neutral choice -- it is the most optimistic one.
2. **It never reads post-decision state as an entry feature.** Entry pricing takes exactly one
   curve state and cannot see the exit state; that is structural, not a convention.
3. **It never labels a result executable.** Every result carries `SIMULATED`. `PLAN.md` Phase 2
   holds landing and fill distributions to forward observations, and none exist yet.
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


B9I = _load("b9i_quote_reproduction", "b9i_quote_reproduction.py")
B9D = B9I.B9D
FreezeViolation = B9D.FreezeViolation

# Bumped when the result shape changes in a way a reader must notice. Consumers pin it.
SCHEMA_VERSION = "1.0.0"

# Every result carries this. There is no code path that emits anything else, and none may be added
# until forward landing/fill observations exist (`PLAN.md` Phase 2 gate).
OUTCOME_SIMULATED = "SIMULATED"

# No scenario in this kernel is calibrated against measured forward data. Names like "optimistic" or
# "stressed" would imply a measured distribution behind them; this constant travels with every
# result so a reader cannot mistake a caller's label for evidence.
CALIBRATION_UNCALIBRATED = "uncalibrated"

BUY, SELL = "buy", "sell"

STATUS_PRICED = "priced"
STATUS_INCOMPLETE_SCENARIO = "incomplete_scenario"
STATUS_EXIT_UNAVAILABLE = "exit_unavailable"
STATUSES = (STATUS_PRICED, STATUS_INCOMPLETE_SCENARIO, STATUS_EXIT_UNAVAILABLE)

# Liquidity conditions, named as in `docs/EXECUTABLE_RETURN.md` §3.
L3_CURVE_COMPLETE = "L3_structural_unavailable"

# Every cost the caller must state. Absence is never zero: a policy missing `priority_fee_lamports`
# has not chosen zero priority fee, it has failed to choose, and pricing it as zero silently adopts
# the most optimistic execution assumption available.
REQUIRED_POLICY_FIELDS = (
    "base_fee_lamports",
    "priority_fee_lamports",
    "tip_lamports",
    "ata_rent_lamports",
    "failed_attempts",
)

# The fee rates the curve applies. Read from decision-time config, never assumed: `fee_basis_points`
# is 95 across the whole frozen artifact, but a tier crossing would change it and a hard-coded 95
# would not notice.
REQUIRED_FEE_FIELDS = (
    "fee_bps", "creator_fee_bps", "cashback_fee_bps", "buyback_fee_bps")

# Canonical order. Database insertion order is not an ordering: it reflects when rows were written,
# which is a property of the collector run and not of the chain.
CANONICAL_ORDER = ("slot", "transaction_index", "outer_index", "inner_index")


class SimulationRefused(FreezeViolation):
    """Raised when the kernel cannot price a decision from the evidence it was given."""


def _positive_int(label, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SimulationRefused(
            f"{label} must be a non-negative integer, got {value!r}; the kernel does not coerce "
            "or default numeric inputs")
    return value


def assert_cost_policy(policy):
    """Every execution cost must be stated explicitly. Returns the policy unchanged."""
    if not isinstance(policy, dict):
        raise SimulationRefused(f"cost policy must be a mapping, got {type(policy).__name__}")
    missing = [field for field in REQUIRED_POLICY_FIELDS if field not in policy]
    if missing:
        raise SimulationRefused(
            f"cost policy does not state {missing}. These are unmeasured in this project, so the "
            "kernel refuses to choose them -- absence is not zero, it is an unmade decision")
    for field in REQUIRED_POLICY_FIELDS:
        _positive_int(f"cost policy {field}", policy[field])
    return policy


def assert_fee_schedule(schedule):
    """Fee rates come from decision-time config, never from a constant in this file."""
    if not isinstance(schedule, dict):
        raise SimulationRefused(f"fee schedule must be a mapping, got {type(schedule).__name__}")
    missing = [field for field in REQUIRED_FEE_FIELDS if field not in schedule]
    if missing:
        raise SimulationRefused(f"fee schedule does not state {missing}")
    for field in REQUIRED_FEE_FIELDS:
        value = _positive_int(f"fee schedule {field}", schedule[field])
        if value > 10000:
            raise SimulationRefused(
                f"fee schedule {field} is {value}, outside 0..10000 basis points")
    return schedule


def assert_eligible_state(state, *, when):
    """The frozen regime, as point-in-time predicates. Every failure is a refusal, never a skip."""
    required = ("virtual_quote", "virtual_token", "real_quote", "real_token",
                "quote_mint", "mayhem_mode", "complete", "slot")
    missing = [field for field in required if field not in state]
    if missing:
        raise SimulationRefused(
            f"{when} curve state is incomplete: missing {missing}; a quote from partial state is a "
            "guess wearing integer precision")
    for field in ("virtual_quote", "virtual_token", "slot"):
        _positive_int(f"{when} {field}", state[field])
    if state["virtual_quote"] <= 0 or state["virtual_token"] <= 0:
        raise SimulationRefused(
            f"{when} virtual reserves are non-positive "
            f"({state['virtual_quote']}, {state['virtual_token']}); the curve is undefined")
    if state["quote_mint"] != B9D.NATIVE_QUOTE_MINT:
        raise SimulationRefused(
            f"{when} quote mint {state['quote_mint']} is not native SOL; the frozen regime is "
            "SOL-paired only and raw token units are not lamports")
    if state["mayhem_mode"]:
        raise SimulationRefused(
            f"{when} curve is in Mayhem mode, whose mechanics are outside the frozen regime")
    return True


def curve_fees(quote_lamports, schedule):
    """The fee components on one trade, from the pinned rounding rules.

    `buyback_fee` is reported, NOT charged: it is a split of the protocol fee, not an addition to
    it. The pinned gross identity is `quote + fee + creator_fee + cashback`, with no buyback term,
    so adding it to the total would double-charge the user by half the protocol fee.
    """
    assert_fee_schedule(schedule)
    _positive_int("quote_lamports", quote_lamports)
    fee = B9I.ceil_div(quote_lamports * schedule["fee_bps"], 10000)
    creator_fee = B9I.ceil_div(quote_lamports * schedule["creator_fee_bps"], 10000)
    cashback = B9I.ceil_div(quote_lamports * schedule["cashback_fee_bps"], 10000)
    buyback = (fee * schedule["buyback_fee_bps"]) // 10000
    return {"fee": fee, "creator_fee": creator_fee, "cashback": cashback,
            "buyback_fee_reported_not_charged": buyback,
            "charged_total": fee + creator_fee + cashback}


def price_entry(state, order, schedule, policy):
    """Price a direct Pump entry against decision-time state.

    Takes exactly ONE curve state and has no parameter through which a later observation could
    reach it. That is the leakage boundary, made structural rather than promised.
    """
    assert_eligible_state(state, when="entry")
    assert_cost_policy(policy)
    if state["complete"]:
        raise SimulationRefused(
            "entry refused: the bonding curve is already complete at the decision instant, so "
            "there is no curve trade to make")
    if order.get("side") != BUY:
        raise SimulationRefused(f"entry order side must be {BUY!r}, got {order.get('side')!r}")
    quote_in = _positive_int("order quote_lamports", order.get("quote_lamports"))
    if quote_in <= 0:
        raise SimulationRefused("entry order must spend a positive quote amount")

    tokens_out = B9I.tokens_out_for_exact_quote_in(
        state["virtual_quote"], state["virtual_token"], quote_in)
    if tokens_out <= 0:
        raise SimulationRefused(
            f"entry of {quote_in} lamports buys zero tokens at these reserves; the order is below "
            "the curve's resolution rather than merely small")
    # The binding constraint is the REAL token reserve, not the virtual one. The curve formula
    # approaches the virtual reserve asymptotically and never reaches it, so a virtual-reserve
    # check never fires however large the order -- it looks like a size guard and is not one.
    if tokens_out > state["real_token"]:
        raise SimulationRefused(
            f"entry would take {tokens_out} tokens but the curve holds {state['real_token']}; the "
            "order exceeds available reserves")

    fees = curve_fees(quote_in, schedule)
    execution = (policy["base_fee_lamports"] + policy["priority_fee_lamports"]
                 + policy["tip_lamports"] + policy["ata_rent_lamports"]
                 + policy["failed_attempts"]
                 * (policy["base_fee_lamports"] + policy["priority_fee_lamports"]))
    return {
        "side": BUY,
        "quote_lamports": quote_in,
        "tokens_out": tokens_out,
        "curve_fees": fees,
        # ATA rent is charged on entry and NOT refunded on exit, by contract. The reclaim is real
        # but conditional on closing the account, and crediting it here would understate cost.
        "execution_costs": {
            "base_fee": policy["base_fee_lamports"],
            "priority_fee": policy["priority_fee_lamports"],
            "tip": policy["tip_lamports"],
            "ata_rent_charged_never_refunded": policy["ata_rent_lamports"],
            "failed_attempts": policy["failed_attempts"],
            "failed_attempt_cost": policy["failed_attempts"]
                                   * (policy["base_fee_lamports"] + policy["priority_fee_lamports"]),
            "total": execution,
        },
        "lamports_out_of_wallet": quote_in + fees["charged_total"] + execution,
        "state_slot": state["slot"],
    }


def price_exit(state, tokens_in, schedule, policy):
    """Price a direct Pump exit against the reserves in force at exit time.

    A completed curve makes the exit UNAVAILABLE rather than receiving an invented mark or an
    assumed migration (`DECISIONS.md` exit boundary).
    """
    assert_eligible_state(state, when="exit")
    assert_cost_policy(policy)
    _positive_int("tokens_in", tokens_in)
    if state["complete"]:
        return {"side": SELL, "status": STATUS_EXIT_UNAVAILABLE, "liquidity": L3_CURVE_COMPLETE,
                "tokens_in": tokens_in, "quote_lamports": None,
                "lamports_into_wallet": None, "state_slot": state["slot"]}

    quote_out = B9I.quote_out_for_tokens_in(
        state["virtual_quote"], state["virtual_token"], tokens_in)
    # The curve cannot pay out more quote than it actually holds. Pricing an exit above the real
    # reserve would report proceeds no counterparty exists for -- the L1/L2 failure that
    # `docs/EXECUTABLE_RETURN.md` §3 exists to name.
    if quote_out > state["real_quote"]:
        raise SimulationRefused(
            f"exit would draw {quote_out} lamports but the curve holds {state['real_quote']}; "
            "refusing to price proceeds the reserves cannot pay")
    fees = curve_fees(quote_out, schedule)
    execution = (policy["base_fee_lamports"] + policy["priority_fee_lamports"]
                 + policy["tip_lamports"]
                 + policy["failed_attempts"]
                 * (policy["base_fee_lamports"] + policy["priority_fee_lamports"]))
    net = quote_out - fees["charged_total"] - execution
    return {
        "side": SELL,
        "status": STATUS_PRICED,
        "tokens_in": tokens_in,
        "quote_lamports": quote_out,
        "curve_fees": fees,
        "execution_costs": {
            "base_fee": policy["base_fee_lamports"],
            "priority_fee": policy["priority_fee_lamports"],
            "tip": policy["tip_lamports"],
            "failed_attempts": policy["failed_attempts"],
            "failed_attempt_cost": policy["failed_attempts"]
                                   * (policy["base_fee_lamports"] + policy["priority_fee_lamports"]),
            "total": execution,
        },
        # May be negative when costs exceed proceeds. That is a real outcome on a small position and
        # is reported rather than clamped -- clamping to zero would hide the case that matters most.
        "lamports_into_wallet": net,
        "state_slot": state["slot"],
    }


def simulate_round_trip(entry_state, exit_state, order, schedule, policy, evidence=None):
    """One entry and one later exit. Returns a versioned, read-only result record.

    `exit_state` is an OUTCOME observed after the decision instant. It reaches `price_exit` only,
    never `price_entry`, and the kernel refuses an exit state that does not strictly follow entry.
    """
    if exit_state["slot"] <= entry_state["slot"]:
        raise SimulationRefused(
            f"exit state at slot {exit_state['slot']} does not follow entry at slot "
            f"{entry_state['slot']}; an exit priced at or before the decision instant is "
            "post-decision information entering the decision")

    entry = price_entry(entry_state, order, schedule, policy)
    exit_leg = price_exit(exit_state, entry["tokens_out"], schedule, policy)

    if exit_leg["status"] == STATUS_EXIT_UNAVAILABLE:
        net = None
        status = STATUS_EXIT_UNAVAILABLE
    else:
        net = exit_leg["lamports_into_wallet"] - entry["lamports_out_of_wallet"]
        status = STATUS_PRICED
    return {
        "schema_version": SCHEMA_VERSION,
        "outcome_label": OUTCOME_SIMULATED,
        "calibration": CALIBRATION_UNCALIBRATED,
        "status": status,
        "evidence": evidence or {},
        "entry": entry,
        "exit": exit_leg,
        "entry_slot": entry_state["slot"],
        "exit_slot": exit_state["slot"],
        "net_lamports": net,
        "fee_schedule": dict(schedule),
        "cost_policy": dict(policy),
    }


def replay_observation(before_quote, before_token, fields):
    """Re-price one observed trade through the kernel's own arithmetic.

    The validation gate: if the kernel's forward functions do not reproduce what the chain did, it
    is not modelling the venue. Returns `(component, predicted, observed)`.
    """
    return B9I.reproduce_trade(before_quote, before_token, fields)


def replay_gate(database, limit=None, progress=None):
    """Replay every eligible observed direct Pump trade at exact integer precision.

    Rows are read in CANONICAL order -- slot, transaction index, then instruction coordinates --
    never database insertion order.
    """
    # Both target IDLs: the decoder refuses an event from a program it has no pin for, and
    # PumpSwap events occur in the artifact even though PumpSwap is not an entry venue.
    idls = {B9D.PUMP_PROGRAM: B9D.load_pinned_idl(
                B9D.PUMP_IDL_PATH, B9D.PUMP_IDL_SHA256, B9D.PUMP_PROGRAM),
            B9D.PUMPSWAP_PROGRAM: B9D.load_pinned_idl(
                B9D.PUMPSWAP_IDL_PATH, B9D.PUMPSWAP_IDL_SHA256, B9D.PUMPSWAP_PROGRAM)}
    report = {"schema_version": SCHEMA_VERSION, "observations": 0,
              "by_component": {}, "mismatches": [], "mismatch_by_direction": {}}
    # An observation is paired with its event by the coordinates the evidence marker itself names,
    # and the pairing must resolve to exactly one instruction. Matching on the outer index alone
    # mispairs bundled transactions that carry several trades under one outer instruction -- which
    # produced a spurious "mismatch" of 389,217,712 lamports on the first run of this gate.
    query = (
        "SELECT r.virtual_quote_before, r.virtual_token_before, r.evidence, c.signature, "
        "r.slot, r.transaction_index "
        "FROM reserve_observation r "
        "JOIN transaction_coordinate c ON c.slot=r.slot AND c.transaction_index=r.transaction_index "
        "WHERE r.virtual_quote_before IS NOT NULL "
        "ORDER BY r.slot, r.transaction_index, r.outer_index, r.inner_index")
    if limit:
        query += f" LIMIT {int(limit)}"
    for quote_before, token_before, evidence, signature, slot, transaction_index in (
            database.execute(query)):
        marker = json.loads(evidence)
        if marker.get("kind") != "anchor_cpi:TradeEvent":
            continue                       # anchors carry no trade quantities to replay
        raw = database.execute(
            "SELECT raw_zlib FROM raw_transaction WHERE signature=?", (signature,)).fetchone()[0]
        result = B9D.raw_result(raw)
        located = [e for e in B9D.envelope_instructions(result)
                   if e["outer_index"] == marker["event_outer_index"]
                   and e["inner_index"] == marker["event_inner_index"]]
        if len(located) != 1:
            raise SimulationRefused(
                f"{signature}: reserve evidence names event coordinates resolving to "
                f"{len(located)} instructions")
        event = B9D.decode_anchor_cpi_event(
            located[0]["program_id"], located[0]["data"], idls)
        if event is None or event["name"] != "TradeEvent":
            raise SimulationRefused(f"{signature}: reserve evidence does not name a TradeEvent")
        fields = event["fields"]
        # Only the regime this kernel prices. Skipped observations are counted, never silently
        # dropped, so the denominator stays honest.
        if fields.get("quote_mint") != B9D.NATIVE_QUOTE_MINT or fields.get("mayhem_mode"):
            report["skipped_out_of_regime"] = report.get("skipped_out_of_regime", 0) + 1
            continue
        report["observations"] += 1
        component, predicted, observed = replay_observation(quote_before, token_before, fields)
        bucket = report["by_component"].setdefault(component, {"n": 0, "exact": 0})
        bucket["n"] += 1
        if predicted == observed:
            bucket["exact"] += 1
        else:
            direction = "over" if predicted > observed else "under"
            report["mismatch_by_direction"][direction] = (
                report["mismatch_by_direction"].get(direction, 0) + 1)
            if len(report["mismatches"]) < 50:
                report["mismatches"].append({
                    "signature": signature, "slot": slot,
                    "transaction_index": transaction_index, "component": component,
                    "predicted": predicted, "observed": observed,
                    "delta": predicted - observed, "ix_name": fields.get("ix_name")})
        if progress and report["observations"] % progress == 0:
            print(f"  {report['observations']:,} replayed", file=sys.stderr, flush=True)
    return report


def assert_replay_exact(database, limit=None, progress=None):
    """Fail closed unless every eligible observation replays exactly."""
    report = replay_gate(database, limit=limit, progress=progress)
    bad = sum(bucket["n"] - bucket["exact"] for bucket in report["by_component"].values())
    if bad:
        raise SimulationRefused(
            f"{bad} of {report['observations']} observations did not replay exactly; the kernel "
            "does not reproduce the venue it claims to model")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress", type=int, default=None)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    database = B9D.connect(args.artifact, readonly=True)
    try:
        report = (assert_replay_exact if args.gate else replay_gate)(
            database, limit=args.limit, progress=args.progress)
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
