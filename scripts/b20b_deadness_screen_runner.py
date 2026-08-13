#!/usr/bin/env python3
"""B20B — the deadness-screen runner, written BEFORE the window-2 data exists.

This file is pinned by hash inside B20B_DEADNESS_SCREEN_PREREGISTRATION.json. Editing it after the
collection starts breaks the pin and the preregistration refuses. It is the second implementation in
this programme written blind to its DATA as well as to its outcome; the first was B19L's.

WHAT IT COMPUTES. One frozen rule, decided before any window-2 bar was collected:

    at t0 + 60 slots, compute the share of all tokens bought so far that is held by the single
    largest buyer. Flag the token if that share is >= 0.95.

and one frozen label, the same one B20B measured on burned data:

    a token is UNEXITABLE if a 0.1 SOL position could not have recovered half its cost from
    EXTERNAL money at any point after t0 + 60 -- i.e. the curve's real quote reserve never
    reached 50,000,000 lamports after the decision point.

Its output is the PRIMARY CONTRAST -- unexitable rate among flagged versus passed tokens -- which
`classify()` turns into a verdict against a decision map fixed here, in code, before the data.

NOTHING HERE CHOOSES ANYTHING. No threshold is searched, no K is tuned, no feature is selected. The
0.95 and the 60 were fixed on burned data and are frozen. The threshold plateau is reported as a
SECONDARY, declared non-decisional, precisely so that a better-looking threshold in window 2 cannot
be promoted after the fact.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- the frozen rule
K_SLOTS = 60                    # decision point: t0 + 60 slots
CONCENTRATION_THRESHOLD = 95    # flag when top buyer holds >= 95/100 of tokens bought
POSITION_LAMPORTS = 100_000_000                 # the 0.1 SOL position the label is defined against
EXIT_RECOVERY_LAMPORTS = POSITION_LAMPORTS // 2  # "half its cost", 50,000,000
MIN_BUYERS_TO_SCORE = 2         # with one buyer concentration is 1.0 by construction: unreadable

# Burned-data PRIOR. Recorded so the window-2 result can be compared to what was expected, and
# labelled a prior rather than a result. Neither figure may be quoted as an outcome of this study.
PRIOR = {
    "fresh_window1": {"n": 2062, "base_rate_pct": 35.3, "flagged_pct": 69.7, "passed_pct": 13.0,
                      "lift_pp": 56.7, "permutation_p": 0.002},
    "burned_corpus": {"n": 606, "base_rate_pct": 32.7, "lift_pp": 46.0, "permutation_p": 0.000},
    "cost_at_threshold": {"exitable_discarded_pct": 18.0},
}


def self_sha256():
    """This file's own hash, so the preregistration can pin the implementation."""
    return hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- extraction


def trade_events(bodies_db, b9d):
    """Every TradeEvent, keyed by mint, in canonical coordinate order.

    Paired to its envelope BY COORDINATE rather than by field values. A key made of values is not
    an identity -- that error produced three different event counts for one quantity in B19N, and
    it is not repeated here.
    """
    database = sqlite3.connect(f"file:{pathlib.Path(bodies_db).resolve()}?mode=ro&immutable=1",
                               uri=True)
    idl = {b9d.PUMP_PROGRAM: b9d.load_pinned_idl(b9d.PUMP_IDL_PATH, b9d.PUMP_IDL_SHA256,
                                                 b9d.PUMP_PROGRAM)}
    by_mint, cache = collections.defaultdict(list), {}
    for signature, slot, tx_index, outer, inner in database.execute(
            "SELECT signature, slot, transaction_index, outer_index, inner_index FROM instruction "
            "WHERE program_id=? AND idl_name='event:TradeEvent' "
            "ORDER BY slot, transaction_index, outer_index, inner_index", (b9d.PUMP_PROGRAM,)):
        if signature not in cache:
            if len(cache) > 4000:
                cache.clear()                       # evict BEFORE inserting, never after
            row = database.execute("SELECT raw_zlib FROM raw_transaction WHERE signature=?",
                                   (signature,)).fetchone()
            cache[signature] = {
                (e.get("outer_index"), e.get("inner_index")): e
                for e in b9d.envelope_instructions(b9d.raw_result(row[0]))
                if e.get("program_id") == b9d.PUMP_PROGRAM} if row else {}
        envelope = cache[signature].get((outer, inner))
        if envelope is None:
            continue
        event = b9d.decode_anchor_cpi_event(b9d.PUMP_PROGRAM, envelope.get("data"), idl)
        if not event or event["name"] != "TradeEvent":
            continue
        fields = event["fields"]
        by_mint[str(fields["mint"])].append(
            (slot, str(fields["user"]), bool(fields["is_buy"]), fields["token_amount"] or 0))
    database.close()
    return by_mint


def reserves(paths_db):
    """Real quote reserve over time, per mint. This is the EXTERNAL money the label depends on."""
    database = sqlite3.connect(f"file:{pathlib.Path(paths_db).resolve()}?mode=ro&immutable=1",
                               uri=True)
    series = collections.defaultdict(list)
    for mint, slot, real_quote in database.execute(
            "SELECT mint, slot, real_quote FROM observation "
            "ORDER BY slot, transaction_index, outer_index, inner_index"):
        series[mint].append((slot, real_quote))
    database.close()
    return series


def launch_slots(identity_db):
    database = sqlite3.connect(f"file:{pathlib.Path(identity_db).resolve()}?mode=ro&immutable=1",
                               uri=True)
    out = {row[0]: row[1] for row in database.execute("SELECT mint, t0_slot FROM identity")}
    database.close()
    return out


# --------------------------------------------------------------------------- the frozen rule


def score(trades, reserve_series, t0_slots):
    """Apply the frozen rule and the frozen label. Returns rows and a census."""
    rows, census = [], collections.Counter()
    for mint, events in trades.items():
        if mint not in t0_slots:
            census["no_t0"] += 1
            continue
        if mint not in reserve_series:
            census["no_reserve_series"] += 1
            continue
        t0 = t0_slots[mint]
        events = sorted(events)
        window = [e for e in events if t0 <= e[0] <= t0 + K_SLOTS]
        buyers = {e[1] for e in window if e[2]}
        if len(buyers) < MIN_BUYERS_TO_SCORE:
            census["unreadable_fewer_than_2_buyers"] += 1
            continue
        series = reserve_series[mint]
        at_decision = [o for o in series if o[0] <= t0 + K_SLOTS]
        after = [o for o in series if o[0] > t0 + K_SLOTS]
        if not at_decision:
            census["no_state_at_decision"] += 1
            continue

        # THE FEATURE, from the window alone. Net position per wallet, then the largest share.
        held = collections.Counter()
        for _slot, user, is_buy, amount in window:
            held[user] += amount if is_buy else -amount
        total = sum(v for v in held.values() if v > 0)
        if total <= 0:
            census["no_net_tokens_bought"] += 1
            continue
        top = max(held.values())
        # exact integer comparison: top/total >= 95/100  <=>  top*100 >= total*95
        flagged = top * 100 >= total * CONCENTRATION_THRESHOLD

        # THE LABEL, strictly after the decision point. "Never traded again" is correctly
        # UNEXITABLE rather than safe -- which is the whole reason this label was chosen.
        best_external = max((o[1] for o in after), default=0)
        unexitable = best_external < EXIT_RECOVERY_LAMPORTS

        rows.append({"mint": mint, "flagged": flagged, "unexitable": unexitable,
                     "top_share_bps": (top * 10000) // total,
                     "external_peak_lamports": best_external})
        census["scored"] += 1
    return rows, census


def contrast(rows):
    """The primary estimand: unexitable rate among flagged versus passed."""
    flagged = [r for r in rows if r["flagged"]]
    passed = [r for r in rows if not r["flagged"]]
    def rate(subset):
        if not subset:
            return None
        return (100 * sum(1 for r in subset if r["unexitable"])) / len(subset)
    bad = sum(1 for r in rows if r["unexitable"])
    caught = sum(1 for r in flagged if r["unexitable"])
    return {
        "n": len(rows),
        "base_rate_pct": rate(rows),
        "flagged_n": len(flagged), "flagged_unexitable_pct": rate(flagged),
        "passed_n": len(passed), "passed_unexitable_pct": rate(passed),
        "lift_pp": (rate(flagged) - rate(passed)) if flagged and passed else None,
        "recall_pct": (100 * caught / bad) if bad else None,
        "precision_pct": (100 * caught / len(flagged)) if flagged else None,
        "exitable_discarded_pct": ((100 * sum(1 for r in flagged if not r["unexitable"]))
                                   / max(1, sum(1 for r in rows if not r["unexitable"]))),
    }


def threshold_plateau(rows):
    """SECONDARY and explicitly NON-DECISIONAL.

    Reported so the burned-data plateau can be compared, and declared non-decisional so that a
    threshold which happens to look better in window 2 cannot be promoted after the fact. The rule
    is 0.95 whatever this table says.
    """
    out = {}
    for cut in (70, 80, 85, 90, 95, 99, 100):
        flagged = [r for r in rows if r["top_share_bps"] >= cut * 100]
        passed = [r for r in rows if r["top_share_bps"] < cut * 100]
        if not flagged or not passed:
            continue
        out[f"{cut/100:.2f}"] = {
            "flagged_pct_of_population": (100 * len(flagged)) // len(rows),
            "passed_unexitable_pct": (100 * sum(1 for r in passed if r["unexitable"])) / len(passed),
        }
    return out


def classify(primary):
    """The frozen decision map. This function makes the call, not the reader."""
    lift = primary["lift_pp"]
    passed = primary["passed_unexitable_pct"]
    base = primary["base_rate_pct"]
    if lift is None or passed is None:
        return "NOT_EVALUABLE", ("the window produced no flagged or no passed tokens, so the "
                                 "contrast does not exist. This is a refusal, not a null result.")
    if lift >= 30 and passed < base:
        return "CONFIRMED", ("the screen reproduces out-of-sample on data that did not exist when "
                             "the rule was frozen. The deadness screen generalises.")
    if lift >= 10:
        return "WEAKENED", ("the screen separates but materially less than the burned-data prior "
                            "of ~50pp. It is real and smaller; the burned figures must not be "
                            "quoted going forward.")
    return "FAILED", ("the screen does not separate out-of-sample. The burned-data result was a "
                      "property of that window and the rule should not be used.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bodies")
    parser.add_argument("--paths")
    parser.add_argument("--identity")
    parser.add_argument("--out", default=str(ROOT / "research" / "B20B_WINDOW2_RESULT.json"))
    parser.add_argument("--self-hash", action="store_true",
                        help="print this file's sha256 for the preregistration pin, and exit")
    args = parser.parse_args(argv)
    if args.self_hash:
        print(self_sha256())
        return 0
    if not (args.bodies and args.paths and args.identity):
        parser.error("--bodies, --paths and --identity are required unless --self-hash is given")

    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    rows, census = score(trade_events(args.bodies, b9d), reserves(args.paths),
                         launch_slots(args.identity))
    primary = contrast(rows)
    verdict, reason = classify(primary)
    report = {
        "study": "B20B_DEADNESS_SCREEN_WINDOW2",
        "runner_sha256": self_sha256(),
        "frozen_rule": {"k_slots": K_SLOTS,
                        "concentration_threshold": CONCENTRATION_THRESHOLD / 100,
                        "position_lamports": POSITION_LAMPORTS,
                        "exit_recovery_lamports": EXIT_RECOVERY_LAMPORTS},
        "coverage_first": dict(census),
        "primary_contrast": primary,
        "secondary_non_decisional": {"threshold_plateau": threshold_plateau(rows)},
        "burned_data_prior_NOT_a_result": PRIOR,
        "verdict": verdict,
        "verdict_reason": reason,
        "not_claimed": {
            "edge": "this screen creates no edge. It avoids a class of losses and nothing more.",
            "fraud": "it predicts unexitability, not fraud or intent.",
            "return": "no figure here is a return, a profit or an expected value.",
        },
    }
    pathlib.Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"wrote": args.out, "verdict": verdict, "primary": primary},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
