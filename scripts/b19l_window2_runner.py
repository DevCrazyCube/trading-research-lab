#!/usr/bin/env python3
"""B19L — the window-2 runner, written BEFORE the window exists.

This file is pinned by hash inside B19L_WINDOW2_PREREGISTRATION.json. Every previous study in this
programme was written blind to its OUTCOME; this is the first written blind to its DATA as well,
because the document and this code both precede the collection. Editing this file after the
collection starts breaks the pin and the preregistration refuses.

WHAT IT COMPUTES. One pre-named cell: B19K's best, take-profit at +6% of position with a 100-slot
abandon deadline, on curves selected by a launch-transaction deposit of at least 3 SOL. Its output
is the ASYMMETRY TRIPLE — hit rate, median win, median abandon loss — which the document classifies
against a frozen decision map. Everything else it reports is declared non-decisional.

NOTHING HERE CHOOSES ANYTHING. No threshold is searched, no cell is selected, no rule is ranked.
The single cell was fixed in B19K before this window was collected.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Frozen in B19K and not re-derived here.
POSITION = 100_000_000
TAKE_PROFIT_LAMPORTS = 6_000_000          # +6% of position, B19K's p10 ceiling quantile
DEADLINE_SLOTS = 100                       # B19K's frozen deadline for that cell
SELECTION_DEPOSIT = 3_000_000_000          # 3 SOL launch-transaction deposit

# Window-1 / burned anchors, frozen. Window 2 is compared against THESE, never against itself.
ANCHOR_HIT_RATE_PCT = 53.3
ANCHOR_MEDIAN_WIN = 6_000_000
ANCHOR_MEDIAN_ABANDON = -31_705_105
BREAKEVEN_HIT_RATE_PCT = 84.1              # at the anchored win/loss
BREAKEVEN_ABANDON_LOSS = -6_839_718        # at the anchored hit rate


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def self_sha256():
    """This file's own hash, so the preregistration can pin the implementation."""
    return hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()


def median(values):
    """Exact integer median by index. Never a mean, and never an interpolation."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def build(paths_db, bodies_db):
    """Every selected curve's entry, and its net-outcome sequence. No rule applied yet."""
    B10A = _load("b10a_simulator_kernel", "b10a_simulator_kernel.py")
    B19D = _load("b19d_non_issuance_signal", "b19d_non_issuance_signal.py")
    B16D = _load("b16d_creator_reentry_signal", "b16d_creator_reentry_signal.py")
    paths = B16D.observed_paths(paths_db)
    schedules, schedule_census = B16D.fee_schedules(bodies_db)
    policy = dict(B19D.SCENARIOS[1])

    rows, census = [], {"paths": len(paths), "no_schedule": 0, "no_entry": 0,
                        "entry_unpriceable": 0, "selected": 0, "unselected": 0}
    for curve, path in paths.items():
        schedule = schedules.get(curve)
        if schedule is None:
            census["no_schedule"] += 1
            continue
        launch_slot, launch_tx = path[0]["slot"], path[0]["transaction_index"]
        # t0 is the LAST transaction-terminal state inside the launch transaction, which is where
        # the creator's own buy lands. path[0] is the CreateEvent and its real quote is zero.
        t0 = [o for o in path
              if o["slot"] == launch_slot and o["transaction_index"] == launch_tx][-1]
        # ENTRY FRAME, named: first observation in a slot STRICTLY AFTER t0. Same-slot entry is
        # unprovable — ordering inside a slot is the leader's, not an observer's.
        entry = next((o for o in path if o["slot"] > launch_slot), None)
        if entry is None:
            census["no_entry"] += 1
            continue
        try:
            buy = B10A.price_entry(B19D._state(entry),
                                   {"side": B10A.BUY, "quote_lamports": POSITION},
                                   schedule, policy)
        except Exception:                                                 # noqa: BLE001
            census["entry_unpriceable"] += 1
            continue
        cost, tokens = buy["lamports_out_of_wallet"], buy["tokens_out"]
        sequence = []
        for observation in path:
            if observation["slot"] <= entry["slot"]:
                continue
            try:
                sell = B10A.price_exit(B19D._state(observation), tokens, schedule, policy)
                sequence.append((observation["slot"],
                                 sell["lamports_into_wallet"] - cost
                                 if sell.get("status") == B10A.STATUS_PRICED else None))
            except Exception:                                             # noqa: BLE001
                sequence.append((observation["slot"], None))
        # Sell-back floor: the position's own deposit is in the curve, so this is always payable.
        final = dict(B19D._state(path[-1]))
        final["real_quote"] += POSITION
        final["real_token"] -= tokens
        final["virtual_quote"] += POSITION
        final["virtual_token"] -= tokens
        try:
            sellback = B10A.price_exit(final, tokens, schedule, policy)["lamports_into_wallet"] - cost
        except Exception:                                                 # noqa: BLE001
            sellback = -cost
        selected = t0["real_quote"] >= SELECTION_DEPOSIT
        census["selected" if selected else "unselected"] += 1
        rows.append({"selected": selected, "cost": cost, "entry_slot": entry["slot"],
                     "sequence": sequence, "sellback": sellback})
    return rows, census, schedule_census


def evaluate_cell(rows):
    """The pre-named cell. Returns the asymmetry triple and both stuck-position conventions."""
    wins, abandons, pessimistic, sellback = [], [], [], []
    unpriceable = 0
    deadline_offset = DEADLINE_SLOTS
    for row in rows:
        limit = row["entry_slot"] + deadline_offset
        outcome, hit, last = None, False, None
        for slot, value in row["sequence"]:
            if value is None:
                continue
            if slot > limit:
                break
            if value >= TAKE_PROFIT_LAMPORTS:
                outcome, hit = value, True
                break
            last = value
        if hit:
            wins.append(outcome)
            pessimistic.append(outcome)
            sellback.append(outcome)
        elif last is not None:
            abandons.append(last)
            pessimistic.append(last)
            sellback.append(last)
        else:
            unpriceable += 1
            pessimistic.append(-row["cost"])
            sellback.append(row["sellback"])
    total = len(rows)
    return {
        "cells": total,
        "hit_count": len(wins),
        "hit_rate_pct": round(100 * len(wins) / total, 2) if total else None,
        "median_win": median(wins),
        "median_abandon_loss": median(abandons),
        "abandon_count": len(abandons),
        "never_priceable": unpriceable,
        "mean_pessimistic": sum(pessimistic) // total if total else None,
        "median_pessimistic": median(pessimistic),
        "mean_sellback": sum(sellback) // total if total else None,
        "median_sellback": median(sellback),
    }


def classify(cell):
    """The frozen three-outcome decision map. This function makes the call, not the reader.

    (c) LIVE is the only outcome that reopens anything, and it requires clearing B19K's own bar:
    mean AND median positive under BOTH stuck conventions.
    """
    live = (cell["mean_pessimistic"] is not None and cell["mean_pessimistic"] > 0
            and cell["median_pessimistic"] > 0
            and cell["mean_sellback"] > 0 and cell["median_sellback"] > 0)
    if live:
        return "LIVE", ("the pre-named cell clears B19K's bar out-of-sample on data that did not "
                        "exist when the family was frozen. This is the only outcome that reopens "
                        "the trading question, and it triggers the execution conversation.")
    moved = (abs((cell["hit_rate_pct"] or 0) - ANCHOR_HIT_RATE_PCT) > 10
             or (cell["median_abandon_loss"] is not None
                 and abs(cell["median_abandon_loss"] - ANCHOR_MEDIAN_ABANDON)
                 > abs(ANCHOR_MEDIAN_ABANDON) // 3))
    if moved:
        return "MOVED_BUT_DEAD", ("the asymmetry differs materially from the anchors, so "
                                  "regime-dependence exists — and the cell's outcome is still "
                                  "negative, so it does not matter. The close stands, scoped to "
                                  "the regimes observed.")
    return "STRUCTURAL_CLOSE", ("the asymmetry reproduces within the declared bands on data that "
                               "did not exist when the family was frozen. The close generalises "
                               "and the trading programme ends properly.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", required=True)
    parser.add_argument("--bodies", required=True)
    parser.add_argument("--out", default=str(ROOT / "research" / "B19L_WINDOW2_RESULT.json"))
    parser.add_argument("--self-hash", action="store_true",
                        help="print this file's sha256 for the preregistration pin, and exit")
    args = parser.parse_args(argv)
    if args.self_hash:
        print(self_sha256())
        return 0

    rows, census, schedule_census = build(args.paths, args.bodies)
    selected = [r for r in rows if r["selected"]]
    unselected = [r for r in rows if not r["selected"]]
    primary = evaluate_cell(selected)
    verdict, reason = classify(primary)
    report = {
        "study": "B19L_WINDOW2_OUT_OF_SAMPLE",
        "runner_sha256": self_sha256(),
        "coverage_first": {"census": census, "fee_schedules": schedule_census},
        "frozen_cell": {"take_profit_lamports": TAKE_PROFIT_LAMPORTS,
                        "deadline_slots": DEADLINE_SLOTS,
                        "selection_deposit_lamports": SELECTION_DEPOSIT,
                        "position_lamports": POSITION},
        "anchors": {"hit_rate_pct": ANCHOR_HIT_RATE_PCT, "median_win": ANCHOR_MEDIAN_WIN,
                    "median_abandon_loss": ANCHOR_MEDIAN_ABANDON,
                    "breakeven_hit_rate_pct": BREAKEVEN_HIT_RATE_PCT,
                    "breakeven_abandon_loss": BREAKEVEN_ABANDON_LOSS},
        "primary_asymmetry_triple": primary,
        "control_unselected": evaluate_cell(unselected),
        "verdict": verdict,
        "verdict_reason": reason,
        "not_claimed": {
            "return": "no figure here is a return, a profit or an expected value.",
            "recommendation": "none is made, at any size, on any signal.",
        },
    }
    pathlib.Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"wrote": args.out, "verdict": verdict,
                      "primary": primary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
