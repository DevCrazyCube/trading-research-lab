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
DOWNSET_PROOF = ROOT / "research" / "B15M_PAYABILITY_DOWNSET_PROOF.md"

# The historical-universe studies. Each pins its OWN document and the document it inherits from.
B19F_PREREG = ROOT / "research" / "B19F_EXIT_TIMING_HISTORICAL_V2_PREREGISTRATION.json"
B19F_SHA256 = "f860cd75fcef159f036c303a20abf095af5411d3b1eb8c809214cde330573644"
B19G_PREREG = ROOT / "research" / "B19G_CAPACITY_WALL_HISTORICAL_V3_PREREGISTRATION.json"
B19G_SHA256 = "6397ebfe71510a7f9ce3150bc4175cb9d3340b808cd121b53f423f7315f682e6"
B15H_PREREG = ROOT / "research" / "B15H_PROSPECTIVE_ENTRY_PREREGISTRATION.json"


def max_lateness_slots(path=B15H_PREREG):
    """B15L's own tolerance, READ from B15H's frozen document rather than restated as 150.

    A hardcoded 150 here would be a fourth copy of a number that already exists in a frozen
    document, and every hand-maintained copy drifts from the thing it describes. More to the point,
    a copy is a number this study could quietly widen; a read is not. Widening the lateness
    tolerance is on B15H's own prohibitions list.
    """
    document = json.loads(pathlib.Path(path).read_bytes())
    for block in document.values():
        if isinstance(block, dict) and "max_lateness_slots" in block:
            value = block["max_lateness_slots"]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise WindowRefused(f"max_lateness_slots is {value!r}, not a non-negative integer")
            return value
    raise WindowRefused(
        f"{path.name} declares no max_lateness_slots; the population's lateness bound is inherited "
        "from it and must not be assumed")


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
B19B_M = _load("b19b_exit_timing_policy", "b19b_exit_timing_policy.py")
B19D_M = _load("b19d_non_issuance_signal", "b19d_non_issuance_signal.py")
B15M_M = _load("b15m_liquidity_capacity", "b15m_liquidity_capacity.py")


class WindowRefused(RuntimeError):
    """The window cannot be assembled or is not entitled to be read."""


# ------------------------------------------------------------------------------------------------
# Freshness. Asserted against the burned range, never assumed from a filename.
# ------------------------------------------------------------------------------------------------

BURNED_PATHS = ROOT / "research" / "b10b_observed_paths.sqlite"


def burned_extent(burned_paths=BURNED_PATHS, declared=None):
    """How far the burned corpus ACTUALLY reaches, derived from it rather than restated.

    B16A.BURNED_RANGE is (433,894,233, 434,097,833) and describes the window the burned CREATES
    were drawn from. The burned OBSERVATIONS run to 435,536,000, because a curve keeps trading long
    after it launches. Checking freshness against the create window alone would therefore accept a
    window overlapping 1.4 million slots of data the studies were developed against, and it would
    pass for the wrong reason rather than fail.

    Every hand-maintained copy of a bound drifts from the thing it describes. This reads the bound
    off the artifact, and falls back to the declared constant only when the burned corpus is absent
    -- announcing that fallback in the return value, because a freshness check that silently
    weakened itself is worse than none.
    """
    low, high = B16A.BURNED_RANGE if declared is None else declared
    path = pathlib.Path(burned_paths)
    if not path.exists():
        return {"low": low, "high": high, "source": "declared_constant_only",
                "warning": ("the burned path corpus is absent, so the extent could not be derived; "
                            "this bound is the CREATE window and is narrower than the data")}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        observed_low, observed_high = connection.execute(
            "SELECT MIN(slot), MAX(slot) FROM observation").fetchone()
    finally:
        connection.close()
    if observed_low is None:
        return {"low": low, "high": high, "source": "declared_constant_only",
                "warning": "the burned path corpus carries no observations"}
    return {"low": min(low, observed_low), "high": max(high, observed_high),
            "source": "derived_from_the_burned_corpus",
            "declared_create_window": [low, high],
            "observed_extent": [observed_low, observed_high]}


def assert_fresh(paths_path=PATHS, burned=None):
    """No observation may fall inside the burned development range.

    The studies were developed against B8b/B9/B10/B16. An evaluation that touched any of it would
    be reporting a result on data the implementation had already seen -- the exact thing the
    blind-authorship discipline exists to prevent, and undetectable after the fact from the report
    alone.

    Checked by slot rather than by path name because a filename is a claim and a slot is evidence.
    """
    extent = burned_extent() if burned is None else {"low": burned[0], "high": burned[1],
                                                     "source": "supplied"}
    low, high = extent["low"], extent["high"]
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
            "burned_range": [low, high], "burned_extent": extent,
            "clear_of_burned_by_slots": span[0] - high, "overlap_observations": 0}


# ------------------------------------------------------------------------------------------------
# The denominator, stated before anything is computed from it.
# ------------------------------------------------------------------------------------------------

def assert_burned(paths_path, burned=None):
    """The INVERSE of assert_fresh: a REHEARSAL must run on development data and nothing else.

    Written as its own assertion rather than as `not assert_fresh(...)`. A rehearsal exists to
    prove the machinery runs end to end before the single permitted pass is spent, and it writes no
    ledger entry -- so a rehearsal that silently pointed at the fresh window would read the
    evaluation data without recording that it had. The ledger would still say the pass was unspent,
    and it would be wrong.

    Every observation must lie inside the burned extent. One that does not means this is not the
    development corpus, whatever the filename says.
    """
    extent = burned_extent() if burned is None else {"low": burned[0], "high": burned[1],
                                                     "source": "supplied"}
    connection = sqlite3.connect(f"file:{pathlib.Path(paths_path)}?mode=ro", uri=True)
    try:
        outside, span = connection.execute(
            "SELECT COUNT(*), MIN(slot) FROM observation WHERE slot < ? OR slot > ?",
            (extent["low"], extent["high"])).fetchone()
        total = connection.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    finally:
        connection.close()
    if not total:
        raise WindowRefused("the rehearsal corpus carries no observations")
    if outside:
        raise WindowRefused(
            f"{outside} observations lie outside the burned extent "
            f"{extent['low']}-{extent['high']} (first at {span}); a rehearsal must not read the "
            "evaluation window, because it records no ledger entry for having done so")
    return {"rehearsal_observations": total, "burned_extent": extent}


def cohort_census(subsample_path=SUBSAMPLE, paths_path=PATHS, table="cohort_identity"):
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
                f"SELECT bonding_curve, is_mayhem_mode FROM {table}"):
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


BURNED_BODIES = ROOT / "research" / "b9d_transaction_bodies.sqlite"
BURNED_IDENTITY = ROOT / "research" / "b10c_t0_identity.sqlite"
BURNED_COHORT = ROOT / "research" / "b9a_outcomes.sqlite"


def build(bodies_path=BODIES, paths_path=PATHS, identity_path=IDENTITY,
          subsample_path=SUBSAMPLE, progress=None, rehearsal=False,
          cohort_table="cohort_identity"):
    """Assemble the window. Transport only: nothing here decides anything a document has frozen.

    `rehearsal=True` asserts the corpus IS burned rather than that it is fresh, so the two modes
    cannot be confused by pointing the wrong paths at the wrong flag: each refuses the other's data.
    """
    freshness = (assert_burned(paths_path) if rehearsal else assert_fresh(paths_path))
    census = cohort_census(subsample_path, paths_path, table=cohort_table)

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


def structural_ceilings(study, window):
    """What each signal COULD reach before any outcome exists. Computed first, on purpose.

    Every number here is fixed by the window's shape, not by any cell's result: how many curves can
    produce a coordinate at all, and how many carry a fee schedule to be priced against. Stating
    them after the outcomes would let a thin result be read as a weak signal when it is a small
    denominator, and would let the author choose which ceiling to mention once the outcomes were
    known.

    The signal-versus-baseline divergence is the one a reader is most likely to miss. S1-S4 can
    reach every curve with a feature block; baseline_any_buy can only reach curves that had a
    non-creator buy; S5 only those with a creator re-entry. The document runs them on the same
    denominator and the same machinery, and they do -- but a reader comparing a signal to a
    baseline is comparing across different admissibility, and that has to be visible.
    """
    priceable = {curve for curve in window["paths"] if window["schedules"].get(curve) is not None}
    ceilings = {}
    for signal in study.SIGNALS:
        reachable = {curve for curve in window["paths"]
                     if study.signal_coordinate(
                         signal, curve, window["features"], window["reentry"]) is not None}
        ceilings[signal["signal_id"]] = {
            "curves_that_can_produce_a_coordinate": len(reachable),
            "of_those_priceable": len(reachable & priceable),
        }
    for baseline in study.BASELINES:
        reachable = {curve for curve in window["paths"]
                     if study.baseline_coordinate(
                         baseline, curve, window["features"],
                         window["first_non_creator_buy"]) is not None}
        ceilings[baseline] = {
            "curves_that_can_produce_a_coordinate": len(reachable),
            "of_those_priceable": len(reachable & priceable),
        }
    return {
        "evaluable_cohort": window["cohort_size"],
        "curves_with_a_decodable_fee_schedule": len(priceable),
        "curves_without_one": window["cohort_size"] - len(priceable),
        "per_signal": ceilings,
        "statement": (
            "these are ceilings, not results. A cell can only be admitted for a curve that both "
            "produces a coordinate and carries a fee schedule, so no signal below can exceed its "
            "`of_those_priceable` count no matter what the outcomes are. They differ between "
            "signals and baselines, so a signal-versus-baseline comparison is across different "
            "admissibility and not a like-for-like contrast."),
    }


def assert_ceilings_bind(ceilings, grid):
    """No cell may admit more curves than its own signal could possibly reach.

    A ceiling that bounds nothing is decoration that reads as a constraint. Asserted on the live
    run rather than checked by hand on the rehearsal, because the rehearsal is the run that does
    not matter and this is the one that does.
    """
    for key, cell in grid.items():
        signal_id = key.split("|")[0]
        ceiling = ceilings["per_signal"][signal_id]["of_those_priceable"]
        admitted = cell["coverage"]["curves_admitted"]
        if admitted > ceiling:
            raise WindowRefused(
                f"{key}: {admitted} curves admitted but at most {ceiling} could produce both a "
                "coordinate and a fee schedule. Either the ceiling or the cell is wrong, and "
                "neither may be reported until it is known which")


def assert_complements_partition(study, ceilings, window):
    """Two signals that are complements over one field must together reach every curve.

    S1 and S2 are `creator_initial_buy_present` True and False. Every curve with a feature block
    answers that question one way or the other, so their coordinate counts must sum to exactly the
    number of curves carrying a block.

    This is the invariant the feature-block defect would have broken, and the reason it is asserted
    rather than eyeballed: with b11b's nested record BOTH counts were zero, and zero plus zero is
    also internally consistent. A partition check that only compared the two counts to each other
    would have passed on a study that could not fire at all.

    The pair is derived from SIGNALS rather than named, so a document that reorders or renames its
    signals does not silently stop being checked.
    """
    by_field = collections.defaultdict(dict)
    for signal in study.SIGNALS:
        if signal["kind"] == "t0_boolean":
            by_field[signal["field"]][bool(signal["expect"])] = signal["signal_id"]
    total = len(window["features"])
    checked = 0
    for field, pair in by_field.items():
        if set(pair) != {True, False}:
            continue
        counts = {expect: ceilings["per_signal"][name]["curves_that_can_produce_a_coordinate"]
                  for expect, name in pair.items()}
        if sum(counts.values()) != total:
            raise WindowRefused(
                f"{pair[True]} ({counts[True]}) and {pair[False]} ({counts[False]}) are "
                f"complements over {field!r} and must partition the {total} curves carrying a "
                f"feature block, but they sum to {sum(counts.values())}. A curve answering neither "
                "means the block did not carry the field, and the study would be reporting silence "
                "as a negative")
        checked += 1
    if not checked:
        raise WindowRefused(
            "no complementary signal pair was found to check the partition against; this guard "
            "must not pass by finding nothing to test")
    return {"complement_pairs_checked": checked, "curves_partitioned": total}


def evaluate_b19d(window, progress=False):
    """B19D over the window. Every figure is computed inside b19d, from b19d's frozen document."""
    study = _load("b19d_non_issuance_signal", "b19d_non_issuance_signal.py")
    document = study.verify_preregistration()
    ceilings = structural_ceilings(study, window)

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
    assert_ceilings_bind(ceilings, grid)
    assert_complements_partition(study, ceilings, window)

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
        # Before the family, and before the primary. Fixed by the window's shape, not by any result.
        "structural_ceilings_known_before_any_outcome": ceilings,
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


def declared_study_id(path, expected, inherited_module):
    """The study id the DOCUMENT declares, never a literal written beside it.

    The ledger's single-use guarantee is keyed on this string. A literal drifts: B19F's documents
    were superseded V1 -> V2 and the constant here was not updated, so the ledger recorded the
    spent pass under V1 while the run had verified V2 -- which left V2 reading as UNSPENT and
    runnable again. A guard keyed on a name that can disagree with the thing it names is not a
    guard. Derived here so the two cannot diverge.
    """
    return verify_historical(path, expected, inherited_module)["preregistration_id"]


def verify_historical(path, expected, inherited_module):
    """Verify BOTH pins: this document, and the document it inherits its rules from.

    A study that inherits by pin has two ways to become something other than what it says. Its own
    document can change, and the document it points at can change underneath it. Checking only the
    first would let every exit rule move while the study still verified clean, which is worse than
    not pinning at all -- it would carry a proof of integrity it no longer had.
    """
    document = json.loads(pathlib.Path(path).read_bytes())
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise WindowRefused(
            f"{path.name}: canonical sha256 {actual} does not match the pin {expected}; a study "
            "does not evaluate against an unpinned specification")
    inherited = document["everything_else_is_inherited_by_pin_not_restated"]
    if inherited["canonical_sha256"] != inherited_module.PREREG_CANONICAL_SHA256:
        raise WindowRefused(
            f"{path.name} inherits from {inherited['source']} at "
            f"{inherited['canonical_sha256']}, but that module pins "
            f"{inherited_module.PREREG_CANONICAL_SHA256}. The inherited rules are not the rules "
            "this document says it inherits")
    inherited_module.verify_preregistration()
    return document


def evaluate_b19f(window, progress=False):
    """B19B over the window. Every figure is computed inside b19b, from b19b's frozen document.

    THE ENTRY COORDINATE IS DERIVED, NOT CHOSEN. B19B's population is "the IDENTICAL admissible
    cell universe as B15M, which is itself B15L's universe, by the same conditions in the same
    order". B15L's universe is built from B15i capture checkpoints, which exist only for the live
    shadow period and not for a historical window -- so the literal rows cannot be reused, and the
    document says conditions rather than rows.

    The condition is stated in code, not inferred by me: b15h_prospective_entry.entry_target_slot
    is `t0_slot + delay_slots`. The universe's entry is therefore launch-plus-delay, and the
    faithful historical analogue is signal_slot = the curve's t0 slot, with b19b's own evaluate_cell
    adding the delay exactly as it always did. B15M's admissibility is applied per cell by b19b
    itself, so the universe's conditions are enforced where they always were rather than
    re-implemented here.
    """
    study = _load("b19b_exit_timing_policy", "b19b_exit_timing_policy.py")
    document = verify_historical(B19F_PREREG, B19F_SHA256, study)
    b15h = _load("b15h_prospective_entry", "b15h_prospective_entry.py")

    priceable = {curve for curve in window["paths"] if window["schedules"].get(curve) is not None}
    with_t0 = {curve for curve in window["paths"]
               if window["features"].get(curve, {}).get("t0_slot") is not None}
    ceilings = {
        "evaluable_cohort": window["cohort_size"],
        "curves_with_a_t0_coordinate": len(with_t0),
        "curves_with_a_decodable_fee_schedule": len(priceable),
        "curves_that_could_yield_a_cell": len(with_t0 & priceable),
        "entry_coordinate_rule": (
            "signal_slot = t0_slot; b19b adds the delay. Derived from "
            "b15h_prospective_entry.entry_target_slot(t0_slot, delay_slots) = t0_slot + "
            "delay_slots, which is the universe's own definition, not a choice made here."),
        "statement": ("these are ceilings, not results. No cell count below can exceed "
                      f"{len(with_t0 & priceable)} however the rules behave."),
    }
    # Asserted rather than trusted: if the inherited definition ever stopped being launch+delay,
    # every cell in this study would silently enter somewhere else.
    lateness = max_lateness_slots()
    ceilings["max_lateness_slots_inherited"] = lateness
    if b15h.entry_target_slot(1_000, 7) != 1_007:
        raise WindowRefused(
            "b15h.entry_target_slot is no longer t0_slot + delay_slots; B19B's entry coordinate "
            "is inherited from it and must not be assumed")

    grid = {}
    for rule in study.EXIT_RULES:
        if progress:
            print(f"  {rule['rule_id']}", file=sys.stderr, flush=True)
        for delay in study.ENTRY_DELAYS:
            for scenario in study.SCENARIOS:
                outcomes, refusals = [], collections.Counter()
                for curve, path in window["paths"].items():
                    block = window["features"].get(curve)
                    if block is None or block.get("t0_slot") is None:
                        refusals[study.X_NOT_IN_B15M_UNIVERSE] += 1
                        continue
                    entry = B19B_M.first_at_or_after(path, block["t0_slot"] + delay)
                    if entry is None:
                        refusals[study.X_NO_ENTRY_OBSERVATION] += 1
                        continue
                    if entry["slot"] - (block["t0_slot"] + delay) > lateness:
                        # B15L's assert_fresh, applied to the historical analogue: an entry this
                        # late is one B15L refuses as a stale checkpoint, and admitting it would
                        # widen the population beyond the one condition this study drops.
                        refusals[study.X_NOT_IN_B15M_UNIVERSE] += 1
                        continue
                    try:
                        value = study.evaluate_cell(
                            rule, path, block["t0_slot"], delay,
                            window["schedules"].get(curve), dict(scenario))
                    except study.ExitRefused as error:
                        refusals[str(error)] += 1
                        continue
                    outcomes.append(value)
                grid[f"{rule['rule_id']}|delay_{delay}|{scenario['scenario_id']}"] = (
                    study.summarise(outcomes, refusals, window["cohort_size"]))

    for key, cell in grid.items():
        admitted = cell["coverage"]["cells_admitted"]
        if admitted > ceilings["curves_that_could_yield_a_cell"]:
            raise WindowRefused(
                f"{key}: {admitted} cells admitted but at most "
                f"{ceilings['curves_that_could_yield_a_cell']} curves carry both a t0 coordinate "
                "and a fee schedule")

    census = window["provenance"]["cohort_census"]
    return {
        "study": "B19F_EXIT_TIMING_HISTORICAL",
        "preregistration_canonical_sha256": B19F_SHA256,
        "rules_inherited_from": {"source": "B19B_EXIT_TIMING_POLICY_V1",
                                 "canonical_sha256": study.PREREG_CANONICAL_SHA256},
        "label": document["status_locks"]["label"],
        "population_rule": document["population"]["rule"],
        "the_one_condition_dropped": document["population"][
            "exactly_one_condition_of_b15ls_is_dropped_and_it_is_named"],
        "what_this_population_is_not": document["population"]["what_this_population_is_not"],
        "executable": False,
        "execution_status": "never_executed",
        "denominator": {
            "subsampled": census["subsampled"],
            "excluded_out_of_regime_mayhem": census["excluded_out_of_regime_mayhem"],
            "evaluable": census["evaluable"],
            "statement": (f"{census['subsampled']} curves were subsampled; "
                          f"{census['excluded_out_of_regime_mayhem']} are mayhem-mode and out of "
                          f"the frozen regime; {census['evaluable']} are evaluable. Every coverage "
                          f"figure is out of {census['evaluable']}."),
        },
        "structural_ceilings_known_before_any_outcome": ceilings,
        "window_provenance": window["provenance"],
        "multiplicity": {
            "family_size": study.FAMILY_SIZE,
            "cells_reported": len(grid),
            "primary": study.PRIMARY,
            "warning": ("the family is reported in full. No rule is selected, and a rule picked "
                        "from it after the fact is not a result."),
        },
        "family": grid,
        "not_claimed": {
            "return": "no figure here is a return, a profit or an expected value.",
            "recommendation": "no exit rule is recommended; the grid is reported, never chosen from.",
        },
    }


HORIZON_SLOTS = {"h_1000_slots": 1_000, "h_10000_slots": 10_000}


def select_cell(path, t0_slot, delay, horizon_slots):
    """The (entry, exit) pair a cell is formed from, by AGREEMENT between two implementations.

    B19C takes an entry and an exit state as arguments; it does not select them, so somebody must.
    That somebody must not be this adapter inventing a third definition of B10c STATE-IN-FORCE --
    an adapter that decides where a cell begins and ends has stopped transporting and started
    doing the study's work.

    B19B and B19D each implement the semantics independently, from the same B10c rule, without
    sharing code. This calls BOTH and refuses on any disagreement. Two independent implementations
    agreeing is evidence; one of them being called by name is only a citation. The refusal also
    means a future edit to either study that changes the semantics stops this study rather than
    silently re-forming its cells.
    """
    entry_b, entry_d = (B19B_M.first_at_or_after(path, t0_slot + delay),
                        B19D_M.first_at_or_after(path, t0_slot + delay))
    if entry_b is not entry_d:
        raise WindowRefused(
            f"b19b and b19d disagree on the entry observation at t0={t0_slot} delay={delay}; "
            "the cell boundary is not determined and no capacity may be measured across it")
    if entry_b is None:
        return None, None
    target = entry_b["slot"] + horizon_slots
    exit_b, exit_d = B19B_M.state_in_force(path, target), B19D_M.state_in_force(path, target)
    if exit_b is not exit_d:
        raise WindowRefused(
            f"b19b and b19d disagree on the state in force at slot {target}")
    return entry_b, exit_b


def proof_binding_state():
    """Whether the pinned bodies still match, recorded IN the result.

    If this says False the run fell back to the scan, and a reader must be able to see that from
    the artifact rather than infer it from how long the run took.
    """
    intact, drifted = B15M_M.proof_binding_intact()
    return {"intact": intact, "drifted": sorted(drifted)}


def proof_status(path=DOWNSET_PROOF):
    """The proof document's OWN status line, read rather than restated.

    B19G's result rests on this argument, so the report carries the argument's standing verbatim
    from the document -- including that it was refuted once. A summary written here would drift
    from the document, and the direction it would drift is obvious: toward dropping the
    embarrassing clause.
    """
    text = pathlib.Path(path).read_text()
    if "**Status.**" not in text:
        raise WindowRefused(f"{pathlib.Path(path).name} carries no status line to quote")
    body = text.split("**Status.**", 1)[1].split("\n\n", 1)[0]
    status = " ".join(body.split())
    for required in ("REFUTED ONCE", "REVIEWED", "ACCEPTED"):
        if required not in status:
            raise WindowRefused(
                f"the proof's status no longer states {required!r}; this study reports that "
                "standing and will not report a softened one")
    return status


def evaluate_b19g(window, progress=False):
    """B19G over the window. Capacity is computed inside b19c, which computes it via B15M."""
    study = _load("b19c_capacity_wall", "b19c_capacity_wall.py")
    document = verify_historical(B19G_PREREG, B19G_SHA256, study)

    priceable = {curve for curve in window["paths"] if window["schedules"].get(curve) is not None}
    with_t0 = {curve for curve in window["paths"]
               if window["features"].get(curve, {}).get("t0_slot") is not None}
    lateness = max_lateness_slots()
    ceilings = {
        "evaluable_cohort": window["cohort_size"],
        "curves_with_a_t0_coordinate": len(with_t0),
        "curves_with_a_decodable_fee_schedule": len(priceable),
        "curves_that_could_yield_a_cell": len(with_t0 & priceable),
        "max_lateness_slots_inherited": lateness,
        "entry_coordinate_rule": (
            "signal_slot = t0_slot, delay added by the same launch-plus-delay rule B15M's "
            "universe uses (b15h_prospective_entry.entry_target_slot); exit is B10c STATE-IN-FORCE "
            "at entry + horizon, taken by agreement between b19b's and b19d's independent "
            "implementations."),
    }

    grid = {}
    for horizon in study.EXIT_HORIZONS:
        if progress:
            print(f"  {horizon}", file=sys.stderr, flush=True)
        for delay in study.ENTRY_DELAYS:
            capacities, refusals = [], collections.Counter()
            executability = collections.Counter()
            cells = 0
            for curve, path in window["paths"].items():
                block = window["features"].get(curve)
                if block is None or block.get("t0_slot") is None:
                    refusals["W_NOT_IN_B15M_UNIVERSE"] += 1
                    continue
                entry, exit_state = select_cell(
                    path, block["t0_slot"], delay, HORIZON_SLOTS[horizon])
                if entry is None or exit_state is None:
                    refusals["W_NO_ENTRY_OBSERVATION"] += 1
                    continue
                if entry["slot"] - (block["t0_slot"] + delay) > lateness:
                    refusals["W_NOT_IN_B15M_UNIVERSE"] += 1
                    continue
                entry_state, exit_full = B19D_M._state(entry), B19D_M._state(exit_state)
                try:
                    # V3 selects the proof-backed check EXPLICITLY. b19c's default is still the
                    # scan, so B19C is untouched. If any proven body has drifted, this call falls
                    # back to the scan by itself and the cell simply becomes slow rather than
                    # unverified.
                    value = study.capacity(
                        entry_state, exit_full,
                        prefix_check=B15M_M.assert_prefix_shape_by_theorem)
                except Exception as error:                                    # noqa: BLE001
                    refusals[f"W_CAPACITY_ERROR:{type(error).__name__}"] += 1
                    continue
                capacities.append(value)
                cells += 1
                for size, ok in study.grid_executability(entry_state, exit_full).items():
                    if ok:
                        executability[str(size)] += 1
            grid[f"{horizon}|delay_{delay}"] = {
                "summary": study.summarise(capacities, refusals, dict(executability)),
                "cells_measured": cells,
            }

    census = window["provenance"]["cohort_census"]
    return {
        "study": "B19G_CAPACITY_WALL_HISTORICAL",
        "preregistration_canonical_sha256": B19G_SHA256,
        "rules_inherited_from": {"source": "B19C_CAPACITY_WALL_SIZE_DEPENDENCE_V1",
                                 "canonical_sha256": study.PREREG_CANONICAL_SHA256},
        "label": document["status_locks"]["label"],
        "population_rule": document["population"]["rule"],
        "the_one_condition_dropped": document["population"][
            "exactly_one_condition_of_b15ls_is_dropped_and_it_is_named"],
        "what_this_population_is_not": document["population"]["what_this_population_is_not"],
        "previously_cap_hit_subgroup": document[
            "everything_else_is_inherited_by_pin_not_restated"]["what_is_NOT_inherited"],
        "executable": False,
        "execution_status": "never_executed",
        "denominator": {
            "subsampled": census["subsampled"],
            "excluded_out_of_regime_mayhem": census["excluded_out_of_regime_mayhem"],
            "evaluable": census["evaluable"],
            "statement": (f"{census['subsampled']} subsampled; "
                          f"{census['excluded_out_of_regime_mayhem']} mayhem-mode and out of "
                          f"regime; {census['evaluable']} evaluable."),
        },
        "structural_ceilings_known_before_any_outcome": ceilings,
        "monotonicity_established_by": {
            "method": "proof, bound by hash to the source it certifies, per B19G_V3",
            "proof": "research/B15M_PAYABILITY_DOWNSET_PROOF.md",
            "proof_status": proof_status(),
            "binding_intact_at_run_time": proof_binding_state(),
        },
        "window_provenance": window["provenance"],
        "grid_lamports": list(study.GRID),
        "family": grid,
        "not_claimed": {
            "return": "capacity is what the observed book could absorb, not a return.",
            "recommendation": "no size is selected, ranked or called optimal; the grid is reported.",
        },
    }


def render_result(result_path):
    """Print a spent result in reading order. READS ONLY -- the artifact is never rewritten.

    `json.dumps(sort_keys=True)` serialises the top level alphabetically, so a person reading the
    file top to bottom meets `family` before `structural_ceilings` and `primary_result`. The
    coverage-before-outcome discipline is intact in substance -- every cell carries its own
    coverage and the denominator and ceilings are top-level -- but the intended reading order is
    defeated by the alphabet.

    Fixed HERE and not in the artifact, deliberately. The ledger pins the result's sha256, so
    adding a `read_order` key to make it read better would silently break the one record proving
    what the spent pass produced. Editing the producer would be worse: the code would no longer
    reproduce the committed bytes, and a later supersede on identical data would yield a different
    hash, leaving nobody able to tell a presentation change from a substantive one. Presentation
    belongs outside the sealed object.
    """
    result = json.loads(pathlib.Path(result_path).read_bytes())
    order = ("study", "label", "denominator", "structural_ceilings_known_before_any_outcome",
             "window_provenance", "multiplicity", "primary_result", "family", "not_claimed")
    missing = [key for key in result if key not in order]
    for key in order:
        if key not in result:
            continue
        print(f"\n{'=' * 96}\n{key}\n{'=' * 96}")
        print(json.dumps(result[key], indent=2, sort_keys=True))
    if missing:
        # Announced rather than dropped: a renderer that silently omits a key it did not expect
        # would hide exactly the field someone added because it mattered.
        print(f"\n{'=' * 96}\nnot in the declared reading order (shown last, nothing omitted)\n"
              f"{'=' * 96}")
        for key in missing:
            print(f"\n-- {key}")
            print(json.dumps(result[key], indent=2, sort_keys=True))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    prov = subparsers.add_parser(
        "provenance", help="assemble the window and print its provenance; reads no study")
    prov.add_argument("--progress", type=int, default=None)
    subparsers.add_parser("ledger", help="show which studies have spent their pass")
    render = subparsers.add_parser(
        "render", help="print a spent result in reading order. Reads the artifact, never edits it.")
    render.add_argument("result")
    runner = subparsers.add_parser(
        "run-b19d", help="THE SINGLE PERMITTED EVALUATION PASS for B19D. Spends its ledger entry.")
    runner.add_argument("--out", default=str(ROOT / "research" / "B19D_EVALUATION_RESULT.json"))
    runner.add_argument("--progress", action="store_true")
    runner.add_argument("--supersede-reason", default=None,
                        help="required to re-run a study that already spent its pass; both "
                             "entries are kept and neither is deleted")
    rehearsal = subparsers.add_parser(
        "rehearse-b19d",
        help="run B19D end to end on the BURNED development corpus. Spends no ledger entry, and "
             "its output may never be reported as an evaluation.")
    rehearsal.add_argument("--out", default=str(
        ROOT / "research" / "B19D_REHEARSAL_BURNED_NOT_A_RESULT.json"))
    rehearsal.add_argument("--progress", action="store_true")
    runner_b = subparsers.add_parser(
        "run-b19f", help="THE SINGLE PERMITTED EVALUATION PASS for B19B. Spends its ledger entry.")
    runner_b.add_argument("--out", default=str(ROOT / "research" / "B19F_EVALUATION_RESULT.json"))
    runner_b.add_argument("--progress", action="store_true")
    runner_b.add_argument("--supersede-reason", default=None)
    rehearsal_b = subparsers.add_parser(
        "rehearse-b19f", help="run B19B end to end on the BURNED corpus. Spends no ledger entry.")
    rehearsal_b.add_argument("--out", default=str(
        ROOT / "research" / "B19F_REHEARSAL_BURNED_NOT_A_RESULT.json"))
    rehearsal_b.add_argument("--progress", action="store_true")
    runner_c = subparsers.add_parser(
        "run-b19g", help="THE SINGLE PERMITTED EVALUATION PASS for B19C. Spends its ledger entry.")
    runner_c.add_argument("--out", default=str(ROOT / "research" / "B19G_EVALUATION_RESULT.json"))
    runner_c.add_argument("--progress", action="store_true")
    runner_c.add_argument("--supersede-reason", default=None)
    rehearsal_c = subparsers.add_parser(
        "rehearse-b19g", help="run B19C end to end on the BURNED corpus. Spends no ledger entry.")
    rehearsal_c.add_argument("--out", default=str(
        ROOT / "research" / "B19G_REHEARSAL_BURNED_NOT_A_RESULT.json"))
    rehearsal_c.add_argument("--progress", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "ledger":
        print(json.dumps(read_ledger(), indent=2, sort_keys=True))
        return 0

    if args.command == "render":
        return render_result(args.result)

    if args.command == "provenance":
        window = build(progress=args.progress)
        print(json.dumps({
            "window_sha256": window_digest(window),
            **window["provenance"],
            "note": ("this is provenance only. No study has read the window and no outcome has "
                     "been computed."),
        }, indent=2, sort_keys=True))
        return 0

    if args.command in ("rehearse-b19g", "run-b19g"):
        rehearsing = args.command == "rehearse-b19g"
        study_id = declared_study_id(
            B19G_PREREG, B19G_SHA256,
            _load("b19c_capacity_wall", "b19c_capacity_wall.py"))
        if not rehearsing:
            assert_unused(study_id, supersede_reason=args.supersede_reason)
        window = build(
            bodies_path=BURNED_BODIES if rehearsing else BODIES,
            paths_path=BURNED_PATHS if rehearsing else PATHS,
            identity_path=BURNED_IDENTITY if rehearsing else IDENTITY,
            subsample_path=BURNED_COHORT if rehearsing else SUBSAMPLE,
            cohort_table="outcome" if rehearsing else "cohort_identity",
            rehearsal=rehearsing, progress=1000 if args.progress else None)
        result = evaluate_b19g(window, progress=args.progress)
        result["window_sha256"] = window_digest(window)
        if rehearsing:
            result["status"] = ("BURNED DEVELOPMENT DATA. Not an evaluation result. Proves the "
                                "machinery executes; spends no ledger entry.")
            pathlib.Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"wrote": args.out, "status": result["status"],
                              "cells": len(result["family"])}, indent=2, sort_keys=True))
            return 0
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        result_sha256 = hashlib.sha256(payload.encode()).hexdigest()
        pathlib.Path(args.out).write_text(payload)
        entry = record_pass(study_id, result["window_sha256"], result_sha256,
                            supersede_reason=args.supersede_reason)
        print(json.dumps({"wrote": args.out, "ledger_entry": entry,
                          "result_sha256": result_sha256}, indent=2, sort_keys=True))
        return 0

    if args.command in ("rehearse-b19f", "run-b19f"):
        rehearsing = args.command == "rehearse-b19f"
        study_id = declared_study_id(
            B19F_PREREG, B19F_SHA256,
            _load("b19b_exit_timing_policy", "b19b_exit_timing_policy.py"))
        if not rehearsing:
            assert_unused(study_id, supersede_reason=args.supersede_reason)
        window = build(
            bodies_path=BURNED_BODIES if rehearsing else BODIES,
            paths_path=BURNED_PATHS if rehearsing else PATHS,
            identity_path=BURNED_IDENTITY if rehearsing else IDENTITY,
            subsample_path=BURNED_COHORT if rehearsing else SUBSAMPLE,
            cohort_table="outcome" if rehearsing else "cohort_identity",
            rehearsal=rehearsing, progress=1000 if args.progress else None)
        result = evaluate_b19f(window, progress=args.progress)
        result["window_sha256"] = window_digest(window)
        if rehearsing:
            result["status"] = ("BURNED DEVELOPMENT DATA. Not an evaluation result. Proves the "
                                "machinery executes; spends no ledger entry.")
            pathlib.Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"wrote": args.out, "status": result["status"],
                              "cells": result["multiplicity"]["cells_reported"]},
                             indent=2, sort_keys=True))
            return 0
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        result_sha256 = hashlib.sha256(payload.encode()).hexdigest()
        pathlib.Path(args.out).write_text(payload)
        entry = record_pass(study_id, result["window_sha256"], result_sha256,
                            supersede_reason=args.supersede_reason)
        print(json.dumps({"wrote": args.out, "ledger_entry": entry,
                          "result_sha256": result_sha256}, indent=2, sort_keys=True))
        return 0

    if args.command == "rehearse-b19d":
        window = build(bodies_path=BURNED_BODIES, paths_path=BURNED_PATHS,
                       identity_path=BURNED_IDENTITY, subsample_path=BURNED_COHORT,
                       cohort_table="outcome", rehearsal=True,
                       progress=1000 if args.progress else None)
        result = evaluate_b19d(window, progress=args.progress)
        result["status"] = ("BURNED DEVELOPMENT DATA. Not an evaluation result, not a return, not "
                            "a recommendation. This run exists only to prove the machinery "
                            "executes end to end, and it spends no ledger entry.")
        result["window_sha256"] = window_digest(window)
        pathlib.Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"wrote": args.out, "status": result["status"],
                          "primary_coverage": result["primary_result"]["coverage"]},
                         indent=2, sort_keys=True))
        return 0

    # run-b19d. The ledger is checked BEFORE the window is assembled, so an already-spent study
    # refuses in a second rather than after the work -- and, more to the point, so that no outcome
    # is ever computed for a study that was not entitled to compute one.
    # Derived from b19d's own document for the same reason as B19F and B19G: a literal here can
    # drift from the study it names, and the ledger's single-use guarantee is keyed on it. B19D's
    # document has not been superseded and the literal still happened to match -- which is luck,
    # not a property.
    study_id = _load("b19d_non_issuance_signal",
                     "b19d_non_issuance_signal.py").verify_preregistration()["preregistration_id"]
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
