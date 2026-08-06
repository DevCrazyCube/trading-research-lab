"""B16d — could a follower have used a public creator re-entry as a delayed-confirmation signal?

Implements `research/B16D_CREATOR_REENTRY_SIGNAL_PREREGISTRATION.json`, committed alone at 1a7b49d
before any outcome here was computed.

BURNED DEVELOPMENT DATA. Nothing measured here is an evaluation result. The B11a fresh window is
neither read nor referenced, there is no network call, and no live file is touched.

THE FOLLOWER IS NOT THE CREATOR. B16b and B16c measured what creator-equal wallets did. This asks
whether somebody WATCHING them could have done anything with it, so the outcome is priced entirely
from the follower's own hypothetical entry and exit. The creator wallet's flow never enters the
arithmetic.

WHAT IS REFUSED RATHER THAN ASSUMED
-----------------------------------
* An entry in the signal's OWN SLOT. Ordering within a slot is the leader's, not an observer's, so
  same-slot capture cannot be proven. Those opportunities are counted as inadmissible and reported,
  which is the honest way to show what the observability rule costs.
* A curve whose fee basis points cannot be decoded from its own TradeEvents. A hardcoded schedule
  was a real defect in B15F and is not repeated here.
* A cell with no observation at or after its exit horizon: right-censored, never zero.
* A cell whose observed exit book could not pay for the sale.
"""
import argparse
import collections
import importlib.util
import json
import pathlib
import sqlite3
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREG = ROOT / "research" / "B16D_CREATOR_REENTRY_SIGNAL_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "b2b18193a5a559886d7eb1ea954b299816fe1a7cc78ea95bbdcda3d2a7229585"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B16A = _load("b16a_operator_archetypes", "b16a_operator_archetypes.py")
B15P = _load("b15p_native_fee_backfill", "b15p_native_fee_backfill.py")
B10A = _load("b10a_simulator_kernel", "b10a_simulator_kernel.py")
B15M = _load("b15m_liquidity_capacity", "b15m_liquidity_capacity.py")

B10B = ROOT / "research" / "b10b_observed_paths.sqlite"

DELAYS = (1, 2, 4)
HORIZONS = (("h_1000_slots", 1000), ("h_10000_slots", 10000))
POSITION = 100_000_000
GRID = (1_000_000, 10_000_000, 100_000_000)
SCENARIOS = (
    {"scenario_id": "optimistic", "base_fee_lamports": 5000, "priority_fee_lamports": 1000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 0},
    {"scenario_id": "base", "base_fee_lamports": 5000, "priority_fee_lamports": 100000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 0},
    {"scenario_id": "stressed", "base_fee_lamports": 5000, "priority_fee_lamports": 1000000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 1},
)

D_NO_SIGNAL = "D_NO_SIGNAL"
D_SAME_SLOT_UNPROVABLE = "D_SAME_SLOT_UNPROVABLE"
D_NO_ENTRY_OBSERVATION = "D_NO_ENTRY_OBSERVATION"
D_NO_FEE_SCHEDULE = "D_NO_FEE_SCHEDULE"
D_FEE_SCHEDULE_AMBIGUOUS = "D_FEE_SCHEDULE_AMBIGUOUS"
D_RIGHT_CENSORED = "D_RIGHT_CENSORED"
D_COMPLETE_AT_ENTRY_OR_EXIT = "D_COMPLETE_AT_ENTRY_OR_EXIT"
D_CAPACITY_REFUSED = "D_CAPACITY_REFUSED"
D_ENTRY_UNPRICEABLE = "D_ENTRY_UNPRICEABLE"
D_EXIT_UNPRICEABLE = "D_EXIT_UNPRICEABLE"


class SignalRefused(RuntimeError):
    """The evidence cannot support this cell, so it carries no outcome."""


def verify_preregistration(path=PREREG, expected=PREREG_CANONICAL_SHA256):
    import hashlib
    document = json.loads(pathlib.Path(path).read_bytes())
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise SignalRefused(f"the B16d preregistration hashes {actual}, pinned {expected}")
    return document


def observed_paths(b10b_path=B10B):
    """Every curve's observed reserve path, in canonical order. B10b's own record, unchanged."""
    connection = sqlite3.connect(f"file:{pathlib.Path(b10b_path)}?mode=ro", uri=True)
    try:
        paths = collections.defaultdict(list)
        for row in connection.execute(
                "SELECT bonding_curve, slot, transaction_index, outer_index, inner_index, kind, "
                "virtual_quote, virtual_token, real_quote, real_token, quote_mint, mayhem_mode, "
                "complete FROM observation ORDER BY bonding_curve, slot, transaction_index, "
                "outer_index, inner_index"):
            paths[row[0]].append({
                "slot": row[1], "transaction_index": row[2], "outer_index": row[3],
                "inner_index": row[4], "kind": row[5], "virtual_quote": row[6],
                "virtual_token": row[7], "real_quote": row[8], "real_token": row[9],
                "quote_mint": row[10], "mayhem_mode": bool(row[11]), "complete": bool(row[12]),
            })
        return dict(paths)
    finally:
        connection.close()


def resolve_schedules(seen):
    """One schedule per curve, or none. A curve with two answers has no answer.

    Refused rather than resolved by majority or by first-seen: the schedule is a property of the
    launch, so two decodable answers means the evidence does not determine it, and pricing a cell
    against a guess is exactly the defect B15F shipped.
    """
    schedules, ambiguous = {}, []
    for curve, options in seen.items():
        if len(options) == 1:
            schedules[curve] = json.loads(next(iter(options)))
        else:
            ambiguous.append(curve)
    return schedules, ambiguous


def fee_schedules(b9d_path=B16A.B9D):
    """One decoded schedule per curve, from that curve's OWN TradeEvents. Never a constant.

    A curve whose decodable schedules disagree is refused rather than resolved by majority: the
    schedule is a property of the launch and two answers means the evidence does not determine it.
    """
    pinned = B15P.load_pinned_types()
    connection = B16A._read_only(b9d_path, "B9d")
    try:
        coordinates = dict(connection.execute(
            "SELECT signature, slot || ':' || transaction_index FROM transaction_coordinate"))
        curve_of = {}
        for signature, slot_tx in coordinates.items():
            curve_of[signature] = slot_tx
        by_transaction = {}
        for row in connection.execute(
                "SELECT slot, transaction_index, bonding_curve FROM reserve_observation"):
            by_transaction[(row[0], row[1])] = row[2]
        seen = collections.defaultdict(set)
        refusals = collections.Counter()
        for signature, raw in connection.execute(
                "SELECT signature, raw_zlib FROM raw_transaction"):
            coordinate = coordinates.get(signature)
            if coordinate is None:
                continue
            slot, transaction_index = (int(part) for part in coordinate.split(":"))
            curve = by_transaction.get((slot, transaction_index))
            if curve is None:
                continue
            try:
                payload = json.loads(zlib.decompress(raw))
            except (zlib.error, json.JSONDecodeError):
                continue
            logs = (((payload.get("result") or {}).get("meta") or {}).get("logMessages")) or []
            data, _skipped = B15P.program_data_payloads(logs)
            _create, trade = B15P.decode_events(data, pinned)
            if trade is None:
                continue
            try:
                seen[curve].add(json.dumps(B15P.schedule_from_trade(trade), sort_keys=True))
            except B15P.BackfillRefused:
                refusals["schedule_from_trade_refused"] += 1
        schedules, ambiguous = resolve_schedules(seen)
        return schedules, {"curves_with_a_schedule": len(schedules),
                           "curves_with_disagreeing_schedules": len(ambiguous),
                           **refusals}
    finally:
        connection.close()


def state_at(path, slot):
    """The curve's reserves as of the LAST observation at or before `slot`, or None."""
    chosen = None
    for observation in path:
        if observation["slot"] <= slot:
            chosen = observation
        else:
            break
    return chosen


def first_at_or_after(path, slot):
    for observation in path:
        if observation["slot"] >= slot:
            return observation
    return None


def _state(observation):
    return {"virtual_quote": observation["virtual_quote"],
            "virtual_token": observation["virtual_token"],
            "real_quote": observation["real_quote"], "real_token": observation["real_token"],
            "quote_mint": observation["quote_mint"], "mayhem_mode": observation["mayhem_mode"],
            "complete": observation["complete"], "slot": observation["slot"]}


def price_follower(entry_observation, exit_observation, schedule, policy, size):
    """The FOLLOWER's round trip, priced against the observed book at both ends."""
    if entry_observation["complete"] or exit_observation["complete"]:
        raise SignalRefused(D_COMPLETE_AT_ENTRY_OR_EXIT)
    entry_state = _state(entry_observation)
    exit_state = _state(exit_observation)
    if not B15M.is_admissible(entry_state, exit_state, size):
        raise SignalRefused(D_CAPACITY_REFUSED)
    try:
        bought = B10A.price_entry(entry_state, {"side": B10A.BUY, "quote_lamports": size},
                                  schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        raise SignalRefused(D_ENTRY_UNPRICEABLE) from error
    try:
        sold = B10A.price_exit(exit_state, bought["tokens_out"], schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        raise SignalRefused(D_EXIT_UNPRICEABLE) from error
    if sold.get("status") != B10A.STATUS_PRICED:
        raise SignalRefused(D_EXIT_UNPRICEABLE)
    return sold["lamports_into_wallet"] - bought["lamports_out_of_wallet"]


def signals(trades, curves, identities):
    """One signal per curve: the first creator-like buy strictly after the create."""
    creator_first, other_first = {}, {}
    for trade in trades:
        if trade["direction"] != "buy":
            continue
        curve = trade["bonding_curve"]
        meta = curves.get(curve)
        if meta is None or meta["create_slot"] is None:
            continue
        if trade["slot"] < meta["create_slot"]:
            continue
        roles = identities.get(curve)
        is_creator = roles is not None and trade["wallet"] in roles
        target = creator_first if is_creator else other_first
        if curve not in target:
            target[curve] = trade
    return creator_first, other_first


def evaluate(signal_coordinates, paths, schedules, sizes, label):
    """Every (curve, delay, horizon, scenario, size) cell for one signal family."""
    cells = collections.defaultdict(list)
    refusals = collections.Counter()
    same_slot_only = 0
    for curve, signal in signal_coordinates.items():
        path = paths.get(curve)
        schedule = schedules.get(curve)
        if schedule is None:
            refusals[D_NO_FEE_SCHEDULE] += 1
            continue
        if not path:
            refusals[D_NO_ENTRY_OBSERVATION] += 1
            continue
        later = [o for o in path if o["slot"] > signal["slot"]]
        same = [o for o in path if o["slot"] == signal["slot"]
                and o["transaction_index"] > signal["transaction_index"]]
        if same and not later:
            same_slot_only += 1
            refusals[D_SAME_SLOT_UNPROVABLE] += 1
            continue
        for delay in DELAYS:
            entry_observation = first_at_or_after(path, signal["slot"] + delay)
            if entry_observation is None:
                refusals[D_NO_ENTRY_OBSERVATION] += 1
                continue
            for horizon_name, horizon_slots in HORIZONS:
                exit_slot = entry_observation["slot"] + horizon_slots
                exit_observation = state_at(path, exit_slot)
                if exit_observation is None or not any(o["slot"] >= exit_slot for o in path):
                    refusals[D_RIGHT_CENSORED] += 1
                    continue
                for scenario in SCENARIOS:
                    policy = {k: scenario[k] for k in
                              ("base_fee_lamports", "priority_fee_lamports", "tip_lamports",
                               "ata_rent_lamports", "failed_attempts")}
                    for size in sizes:
                        key = (scenario["scenario_id"], horizon_name, delay, size)
                        try:
                            net = price_follower(entry_observation, exit_observation, schedule,
                                                 policy, size)
                        except SignalRefused as error:
                            refusals[str(error)] += 1
                            continue
                        cells[key].append({"bonding_curve": curve, "net_lamports": net})
    return {"label": label, "cells": dict(cells), "refusals": dict(refusals),
            "same_slot_only_opportunities": same_slot_only}


def summarise_cells(cells):
    out = {}
    for (scenario, horizon, delay, size), rows in sorted(cells.items()):
        values = [r["net_lamports"] for r in rows]
        positives = sorted((v for v in values if v > 0), reverse=True)
        total_positive = sum(positives)
        top = positives[:max(1, len(positives) // 10)] if positives else []
        out[f"{scenario}|{horizon}|delay{delay}|size{size}"] = {
            "cells": len(rows),
            "net_lamports": B16A.order_statistics(values),
            "cells_at_or_below_zero": sum(1 for v in values if v <= 0),
            "positive_cells": len(positives),
            "share_of_positive_total_in_top_decile_numerator": sum(top),
            "share_of_positive_total_in_top_decile_denominator": total_positive,
        }
    return out


def run(b9d_path=B16A.B9D, b10b_path=B10B, identity_path=B16A.B10C_IDENTITY, sizes=GRID):
    document = verify_preregistration()
    B16A.assert_user_index_is_sound(b9d_path, identity_path)
    trades, trade_exclusions = B16A.load_trades(b9d_path)
    curves = B16A.load_curves(b10b_path, identity_path)
    identities = {curve: {meta["creator"], meta["create_user"]} - {None}
                  for curve, meta in curves.items()}
    paths = observed_paths(b10b_path)
    schedules, schedule_census = fee_schedules(b9d_path)
    creator_first, other_first = signals(trades, curves, identities)

    creator_result = evaluate(creator_first, paths, schedules, sizes, "creator_reentry_signal")
    baseline_any = evaluate(other_first, paths, schedules, sizes, "baseline_any_buy")
    create_signal = {}
    for curve, meta in curves.items():
        if meta["create_slot"] is not None:
            create_signal[curve] = {"slot": meta["create_slot"], "transaction_index": -1}
    baseline_launch = evaluate(create_signal, paths, schedules, sizes, "baseline_launch")

    return {
        "study": "B16D_CREATOR_REENTRY_SIGNAL",
        "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
        "status": ("BURNED DEVELOPMENT DATA. Not an evaluation result, not a return, not a "
                   "recommendation."),
        "label": document["status_locks"]["label"],
        "executable": False,
        "performance_status": "not_evaluated",
        "execution_status": "never_executed",
        "assumption": document["status_locks"]["assumption"],
        "the_follower_is_not_the_creator": document["the_follower_is_not_the_creator"]["rule"],
        "selection_coverage": {
            "curves_in_cohort": len(curves),
            "curves_with_a_creator_reentry_signal": len(creator_first),
            "curves_with_a_non_creator_buy_signal": len(other_first),
            "curves_with_a_decodable_fee_schedule": schedule_census["curves_with_a_schedule"],
            "curves_with_disagreeing_schedules": schedule_census["curves_with_disagreeing_schedules"],
            "trade_exclusions_upstream": trade_exclusions,
            "read_before_outcomes": ("coverage is stated first so no outcome can be read without "
                                     "the share of the cohort it came from"),
        },
        "creator_reentry_signal": {
            "same_slot_only_opportunities_refused": creator_result["same_slot_only_opportunities"],
            "refusals": creator_result["refusals"],
            "outcomes": summarise_cells(creator_result["cells"]),
        },
        "baseline_any_buy": {
            "refusals": baseline_any["refusals"],
            "outcomes": summarise_cells(baseline_any["cells"]),
        },
        "baseline_launch": {
            "refusals": baseline_launch["refusals"],
            "outcomes": summarise_cells(baseline_launch["cells"]),
        },
        "not_claimed": {
            "return": "no figure here is a return, a profit or an expected value.",
            "evaluation": "burned development data; nothing here may be reported as an evaluation.",
            "capture": ("whether a follower could capture any effect is answered in the finding "
                        "from the observability refusals and the tail concentration, not asserted."),
            "recommendation": "none is made, to follow any wallet or otherwise.",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="B16d creator re-entry signal (offline, burned)")
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
