#!/usr/bin/env python3
"""The evaluation window: the one fresh corpus the B19 studies are permitted to read, and the
adapter that carries it to them.

WHY THIS IS A SEPARATE MODULE AND NOT AN EDIT TO THE STUDIES. Each of b19b/b19c/b19d carries a test
asserting that its source names no B11a path. That test is what keeps "building the study" and
"running the study" two different acts performed at two different times: a study written after the
data lands still satisfies its preregistration, but its author's innocence is gone and no amount of
care recovers it. The studies were written blind, during the collection. Wiring the window into
them would destroy exactly the property that makes them worth running, so the window comes to them
as an argument instead.

WHAT THIS MODULE MAY AND MAY NOT DO. It assembles paths, t0 features, fee schedules and signal
coordinates, and it hands them over. It computes NO outcome, applies NO threshold and makes NO
choice a study's document has already frozen. Every number a reader will see is produced inside the
study, from the document, against inputs this module only transports.

THE SINGLE-USE LEDGER. A preregistered study gets ONE pass over the fresh window. Without a
recorded, committed ledger, "run it again" costs nothing and a run can be quietly repeated until it
reads well -- which is the failure preregistration exists to prevent, performed by the person
holding the preregistration. The ledger refuses a second pass for a study that already has one.
Superseding requires an explicit reason and KEEPS BOTH ENTRIES; nothing is ever deleted.

NO FLOAT ANYWHERE. Every quantity that reaches a study is an exact integer or a count.
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
WINDOW_DIR = ROOT / "research" / "b11a"
BODIES = WINDOW_DIR / "b11a_bodies.sqlite"
PATHS = WINDOW_DIR / "b11a_paths.sqlite"
IDENTITY = WINDOW_DIR / "b11a_identity.sqlite"
SUBSAMPLE = WINDOW_DIR / "b11a_subsample.sqlite"
LEDGER = ROOT / "research" / "B19_EVALUATION_LEDGER.json"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B9D = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
B10BP = _load("b10b_position_path", "b10b_position_path.py")
B11BC = _load("b11b_feature_corpus", "b11b_feature_corpus.py")
B16A = _load("b16a_operator_archetypes", "b16a_operator_archetypes.py")
B16D = _load("b16d_creator_reentry_signal", "b16d_creator_reentry_signal.py")


class WindowRefused(RuntimeError):
    """The window cannot be assembled or is not entitled to be read."""


# ------------------------------------------------------------------------------------------------
# Freshness. Asserted against the burned range, never assumed from a filename.
# ------------------------------------------------------------------------------------------------

def assert_fresh(paths_path=PATHS, burned=None):
    """No observation may fall inside the burned development range.

    The studies were developed against B8b/B9/B10/B16, whose corpus sits at slots
    433,894,233-434,097,833. An evaluation that touched any of it would be reporting a result on
    data the implementation had already seen -- the exact thing the blind-authorship discipline
    exists to prevent, and undetectable after the fact from the report alone.

    Checked by slot rather than by path name because a filename is a claim and a slot is evidence.
    """
    low, high = B16A.BURNED_RANGE if burned is None else burned
    connection = sqlite3.connect(f"file:{pathlib.Path(paths_path)}?mode=ro", uri=True)
    try:
        overlap = connection.execute(
            "SELECT COUNT(*), MIN(slot), MAX(slot) FROM observation "
            "WHERE slot >= ? AND slot <= ?", (low, high)).fetchone()
        span = connection.execute("SELECT MIN(slot), MAX(slot) FROM observation").fetchone()
    finally:
        connection.close()
    if overlap[0]:
        raise WindowRefused(
            f"{overlap[0]} observations fall inside the burned range {low}-{high} "
            f"(at {overlap[1]}-{overlap[2]}); this is development data and no result may be "
            "reported from it")
    if span[0] is None:
        raise WindowRefused("the window carries no observations at all")
    return {"window_min_slot": span[0], "window_max_slot": span[1],
            "burned_range": [low, high], "overlap_observations": 0}


# ------------------------------------------------------------------------------------------------
# The denominator, stated before anything is computed from it.
# ------------------------------------------------------------------------------------------------

def cohort_census(subsample_path=SUBSAMPLE, paths_path=PATHS):
    """Where the cohort went, as counts that add up. Reported before any outcome.

    3,932 evaluable curves out of 5,000 subsampled is a 21.4% exclusion, and a coverage line
    reading "cohort: 3932" would let a reader take that for the whole cohort. The exclusion is
    legitimate -- b9d's frozen_population skips mayhem-mode curves because the simulator refuses
    them as out of regime, so their bodies were never fetched -- but legitimate is not the same as
    invisible, and an exclusion a reader cannot see is one they cannot weigh.
    """
    subsample = sqlite3.connect(f"file:{pathlib.Path(subsample_path)}?mode=ro&immutable=1", uri=True)
    paths = sqlite3.connect(f"file:{pathlib.Path(paths_path)}?mode=ro", uri=True)
    try:
        mayhem, regular = set(), set()
        for curve, is_mayhem in subsample.execute(
                "SELECT bonding_curve, is_mayhem_mode FROM cohort_identity"):
            (mayhem if is_mayhem else regular).add(curve)
        with_path = {row[0] for row in paths.execute("SELECT bonding_curve FROM curve")}
    finally:
        subsample.close()
        paths.close()

    census = {
        "subsampled": len(mayhem) + len(regular),
        "excluded_out_of_regime_mayhem": len(mayhem),
        "evaluable": len(regular & with_path),
        "in_regime_without_a_path": len(regular - with_path),
        "mayhem_with_a_path": len(mayhem & with_path),
    }
    if census["mayhem_with_a_path"]:
        raise WindowRefused(
            f"{census['mayhem_with_a_path']} mayhem curves carry a path; they are out of regime "
            "and must not be evaluable")
    if census["in_regime_without_a_path"]:
        raise WindowRefused(
            f"{census['in_regime_without_a_path']} in-regime curves have no path; that is "
            "collection loss and it must be explained before any study reads this window")
    if census["subsampled"] != census["excluded_out_of_regime_mayhem"] + census["evaluable"]:
        raise WindowRefused(f"the census does not add up: {census}")
    return census


# ------------------------------------------------------------------------------------------------
# The window itself
# ------------------------------------------------------------------------------------------------

def flatten_features(records):
    """b11b's nested record -> the FLAT block the studies declare, keyed by bonding curve.

    b11b returns {"coordinate": {...}, "features": {...}, "grouping": {...}}; a study reads a flat
    mapping carrying the feature fields and `t0_slot`. Handing over the nested record made every t0
    signal return None for every curve without raising, which the report states as "no admissible
    cells" -- a null result indistinguishable from a real one. b19d now refuses a block missing the
    declared field, so this function is the only thing standing between the corpus and a refusal;
    it is deliberately dumb, and every field it produces is copied, never computed.
    """
    features = {}
    for record in records:
        curve = record["grouping"]["bonding_curve"]
        if curve in features:
            raise WindowRefused(f"{curve} has two feature records; a curve has one t0")
        block = dict(record["features"])
        block["t0_slot"] = record["coordinate"]["slot"]
        block["t0_transaction_index"] = record["coordinate"]["transaction_index"]
        features[curve] = block
    return features


def build(bodies_path=BODIES, paths_path=PATHS, identity_path=IDENTITY,
          subsample_path=SUBSAMPLE, progress=None):
    """Assemble the window. Transport only: nothing here decides anything a document has frozen."""
    freshness = assert_fresh(paths_path)
    census = cohort_census(subsample_path, paths_path)

    paths = B16D.observed_paths(paths_path)
    for curve, path in paths.items():
        B10BP.assert_canonical_order(path, label=f"path[{curve}]")

    schedules, schedule_census = B16D.fee_schedules(bodies_path)

    records, feature_report = B11BC.materialize(bodies_path, paths_path, progress=progress)
    if feature_report["errors"]:
        raise WindowRefused(
            f"{len(feature_report['errors'])} feature errors: {feature_report['errors'][:3]}")
    features = flatten_features(records)

    B16A.assert_user_index_is_sound(bodies_path, identity_path)
    trades, trade_exclusions = B16A.load_trades(bodies_path)
    curves = B16A.load_curves(paths_path, identity_path)
    identities = {curve: {meta["creator"], meta["create_user"]} - {None}
                  for curve, meta in curves.items()}
    reentry, first_non_creator_buy = B16D.signals(trades, curves, identities)

    return {
        "paths": paths,
        "features": features,
        "schedules": schedules,
        "reentry": reentry,
        "first_non_creator_buy": first_non_creator_buy,
        "cohort_size": census["evaluable"],
        "provenance": {
            "freshness": freshness,
            "cohort_census": census,
            "curves_with_a_path": len(paths),
            "curves_with_features": len(features),
            "feature_hash_chain_sha256": feature_report["determinism"]["feature_hash_chain_sha256"],
            "corpus_content_sha256": feature_report["corpus_content_sha256"],
            "fee_schedules": schedule_census,
            "trade_exclusions_upstream": trade_exclusions,
            "curves_with_a_creator_reentry": len(reentry),
            "curves_with_a_non_creator_buy": len(first_non_creator_buy),
        },
    }


def window_digest(window):
    """A digest over what the studies will actually read, so a ledger entry names a specific window.

    Over the transported CONTENT, not over the files: a SQLite file's bytes change when a WAL is
    checkpointed without a single row changing, so a byte hash would report a different window for
    the same data and an identical one for a file rebuilt with different contents at the same size.
    """
    digest = hashlib.sha256()
    for curve in sorted(window["paths"]):
        digest.update(curve.encode())
        for observation in window["paths"][curve]:
            for field in ("slot", "transaction_index", "outer_index", "inner_index",
                          "virtual_quote", "virtual_token", "real_quote", "real_token",
                          "quote_mint", "mayhem_mode", "complete"):
                value = observation[field]
                if isinstance(value, float):
                    raise WindowRefused(f"a float reached the window digest at {curve}.{field}")
                digest.update(str(value).encode())
                digest.update(b"\x1f")
        digest.update(b"\x1e")
    for curve in sorted(window["features"]):
        digest.update(B10BP.canonical_json(window["features"][curve]).encode())
    return digest.hexdigest()


# ------------------------------------------------------------------------------------------------
# The single-use ledger
# ------------------------------------------------------------------------------------------------

def read_ledger(path=LEDGER):
    if not pathlib.Path(path).exists():
        return {"ledger_id": "B19_EVALUATION_LEDGER_V1", "entries": []}
    return json.loads(pathlib.Path(path).read_bytes())


def assert_unused(study_id, path=LEDGER, supersede_reason=None):
    """One pass per study. A second requires an explicit reason and keeps the first."""
    ledger = read_ledger(path)
    prior = [entry for entry in ledger["entries"] if entry["study_id"] == study_id]
    if prior and not supersede_reason:
        raise WindowRefused(
            f"{study_id} has already read the evaluation window "
            f"(entry {prior[-1]['sequence']}, window {prior[-1]['window_sha256'][:16]}). A "
            "preregistered study gets one pass; running it again until it reads well is the "
            "failure the preregistration exists to prevent. Supersede with an explicit reason if "
            "the first pass was faulty -- both entries are kept.")
    return ledger, prior


def record_pass(study_id, window_sha256, result_sha256, path=LEDGER, supersede_reason=None):
    ledger, prior = assert_unused(study_id, path, supersede_reason)
    entry = {
        "sequence": len(ledger["entries"]) + 1,
        "study_id": study_id,
        "window_sha256": window_sha256,
        "result_sha256": result_sha256,
        "supersedes": [p["sequence"] for p in prior],
        "supersede_reason": supersede_reason,
    }
    ledger["entries"].append(entry)
    pathlib.Path(path).write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    return entry


# ------------------------------------------------------------------------------------------------
# The evaluation pass. The study decides everything; this only feeds it and counts.
# ------------------------------------------------------------------------------------------------

def _cells(study, window, coordinate_of, label):
    """Every (delay, horizon, scenario) cell for one signal, as outcomes and refusal counts.

    Coverage is accumulated per cell, never inferred at the end from what survived: a curve that
    produced no signal and a curve whose cell was refused are different facts, and a denominator
    reconstructed from the outcomes alone cannot tell them apart.
    """
    grid = {}
    for horizon in study.HORIZONS:
        for delay in study.ENTRY_DELAYS:
            for scenario in study.SCENARIOS:
                outcomes, refusals, admitted = [], collections.Counter(), set()
                for curve, path in window["paths"].items():
                    signal_slot = coordinate_of(curve)
                    if signal_slot is None:
                        refusals[study.N_NO_SIGNAL] += 1
                        continue
                    try:
                        value = study.evaluate_cell(
                            path, signal_slot, horizon, delay,
                            window["schedules"].get(curve), dict(scenario))
                    except study.SignalRefused as error:
                        refusals[str(error)] += 1
                        continue
                    outcomes.append(value)
                    admitted.add(curve)
                grid[f"{label}|{horizon['name']}|delay_{delay}|{scenario['scenario_id']}"] = (
                    study.summarise(outcomes, refusals, len(admitted), window["cohort_size"]))
    return grid


def evaluate_b19d(window, progress=False):
    """B19D over the window. Every figure is computed inside b19d, from b19d's frozen document."""
    study = _load("b19d_non_issuance_signal", "b19d_non_issuance_signal.py")
    document = study.verify_preregistration()

    grid = {}
    for signal in study.SIGNALS:
        if progress:
            print(f"  {signal['signal_id']}", file=sys.stderr, flush=True)
        grid.update(_cells(
            study, window,
            lambda curve, s=signal: study.signal_coordinate(
                s, curve, window["features"], window["reentry"]),
            signal["signal_id"]))
    for baseline in study.BASELINES:
        if progress:
            print(f"  {baseline}", file=sys.stderr, flush=True)
        grid.update(_cells(
            study, window,
            lambda curve, b=baseline: study.baseline_coordinate(
                b, curve, window["features"], window["first_non_creator_buy"]),
            baseline))

    primary_key = (f"{study.PRIMARY['signal_id']}|{study.PRIMARY['horizon']}"
                   f"|delay_{study.PRIMARY['delay']}|{study.PRIMARY['scenario_id']}")
    if primary_key not in grid:
        raise WindowRefused(f"the pre-committed primary cell {primary_key} was not evaluated")

    census = window["provenance"]["cohort_census"]
    return {
        "study": "B19D_NON_ISSUANCE_SIGNAL",
        "preregistration_canonical_sha256": study.PREREG_CANONICAL_SHA256,
        "label": document.get("status_locks", {}).get("label"),
        "executable": False,
        "execution_status": "never_executed",
        # Coverage FIRST, and the denominator spelled out in three numbers rather than one. A bare
        # "3932" reads as the whole cohort and silently rebases every share below it.
        "denominator": {
            "subsampled": census["subsampled"],
            "excluded_out_of_regime_mayhem": census["excluded_out_of_regime_mayhem"],
            "evaluable": census["evaluable"],
            "statement": (f"{census['subsampled']} curves were subsampled; "
                          f"{census['excluded_out_of_regime_mayhem']} are mayhem-mode and out of "
                          f"the frozen regime, so their transaction bodies were never fetched; "
                          f"{census['evaluable']} are evaluable. Every coverage figure below is "
                          f"out of {census['evaluable']}, not out of {census['subsampled']}."),
        },
        "window_provenance": window["provenance"],
        "multiplicity": {
            "family_size": study.FAMILY_SIZE,
            "cells_reported": len(grid),
            "primary_result_key": primary_key,
            "warning": ("the family is reported in full. A figure selected from it after the fact "
                        "is not the primary result and may not be presented as one."),
        },
        "primary_result": grid[primary_key],
        "family": grid,
        "not_claimed": {
            "return": "no figure here is a return, a profit or an expected value.",
            "edge": ("a median above zero on one window describes that window. It is not a "
                     "demonstration of edge and not grounds to trade."),
            "recommendation": "none is made.",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    prov = subparsers.add_parser(
        "provenance", help="assemble the window and print its provenance; reads no study")
    prov.add_argument("--progress", type=int, default=None)
    subparsers.add_parser("ledger", help="show which studies have spent their pass")
    runner = subparsers.add_parser(
        "run-b19d", help="THE SINGLE PERMITTED EVALUATION PASS for B19D. Spends its ledger entry.")
    runner.add_argument("--out", default=str(ROOT / "research" / "B19D_EVALUATION_RESULT.json"))
    runner.add_argument("--progress", action="store_true")
    runner.add_argument("--supersede-reason", default=None,
                        help="required to re-run a study that already spent its pass; both "
                             "entries are kept and neither is deleted")
    args = parser.parse_args(argv)

    if args.command == "ledger":
        print(json.dumps(read_ledger(), indent=2, sort_keys=True))
        return 0

    if args.command == "provenance":
        window = build(progress=args.progress)
        print(json.dumps({
            "window_sha256": window_digest(window),
            **window["provenance"],
            "note": ("this is provenance only. No study has read the window and no outcome has "
                     "been computed."),
        }, indent=2, sort_keys=True))
        return 0

    # run-b19d. The ledger is checked BEFORE the window is assembled, so an already-spent study
    # refuses in a second rather than after the work -- and, more to the point, so that no outcome
    # is ever computed for a study that was not entitled to compute one.
    study_id = "B19D_NON_ISSUANCE_SIGNAL_V1"
    assert_unused(study_id, supersede_reason=args.supersede_reason)
    window = build(progress=1000 if args.progress else None)
    digest = window_digest(window)
    assert_unused(study_id, supersede_reason=args.supersede_reason)
    result = evaluate_b19d(window, progress=args.progress)
    result["window_sha256"] = digest
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    result_sha256 = hashlib.sha256(payload.encode()).hexdigest()
    pathlib.Path(args.out).write_text(payload)
    entry = record_pass(study_id, digest, result_sha256,
                        supersede_reason=args.supersede_reason)
    print(json.dumps({"wrote": args.out, "ledger_entry": entry,
                      "result_sha256": result_sha256}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
