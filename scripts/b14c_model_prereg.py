"""B14c — the validator that makes the model preregistration enforceable.

`research/B14C_MODEL_PREREGISTRATION.json` was committed alone, before this file existed. This
module's job is narrow and entirely negative: it pins that document's canonical hash, refuses a
document that has drifted from it, and refuses to let anything fit.

It contains no model, no fitting code, no metric and no threshold. A validator that could also fit
would be the thing it is supposed to be guarding against.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREG_PATH = ROOT / "research" / "B14C_MODEL_PREREGISTRATION.json"
FEATURE_CONTRACT_PATH = ROOT / "research" / "B13F_FEATURE_CONTRACT_PREREGISTRATION.md"

SCHEMA_VERSION = "1.0.0"

# Pinned from the commit that carried the document alone. The document came first; this constant is
# a record of what was frozen, not a parameter anyone may retune to make a later edit validate.
PREREGISTRATION_CANONICAL_SHA256 = "e74b9b40891ccd3f27207ce414d0de0824c7d555ebb7dd05ad9d9d82e3879d68"

EXPECTED_FEATURE_COUNT = 99
EXPECTED_FAMILY_COUNT = 4
EXPECTED_HORIZON_COUNT = 4
EXPECTED_PAIR_COUNT = 12
EXPECTED_ABSTENTION_CODES = ("A01_vector_unavailable", "A02_required_denominator_zero",
                             "A03_inference_incompatible", "A04_feature_out_of_training_range",
                             "A05_unfitted_null_branch", "A06_window_not_eligible")
EXPECTED_LEAKAGE_CODES = tuple(f"C{index:02d}" for index in range(1, 13))
REQUIRED_STATUS_LOCKS = {"performance_status": "not_evaluated", "publication_grade": False,
                         "model_eligible": False, "eligible_for_b11a": False}

# Names that would mean a fit happened, a window opened, or a line was drawn. Refused by name so an
# invented status has to be invented against an explicit list rather than slipped past an omission.
FORBIDDEN_STATUS_NAMES = ("evaluated", "executable", "profitable", "production_ready", "validated",
                          "live", "publication_grade")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Reached through b14b so the whole chain is ONE module graph. Loading b14a a second time by path
# would give this module a different ArtifactRefused class than b14b raises, and every caller
# written `except EvaluationRefused` would silently stop catching what it was written for. That
# mistake has been made five times in this project; it is cheaper to make it unavailable.
B14B = _load("b14b_evaluation", "b14b_evaluation.py")
ARTIFACT = B14B.ARTIFACT


class ModelPreregRefused(B14B.EvaluationRefused):
    """The model preregistration is not the frozen one, or something asked to act outside it."""


class FitRefused(ModelPreregRefused):
    """Something asked to fit. Nothing may fit: no window is eligible and B11a never will be."""


def canonical_bytes(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def canonical_sha256(document):
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def read_preregistration(path=PREREG_PATH):
    try:
        raw = pathlib.Path(path).read_bytes()
    except OSError as error:
        raise ModelPreregRefused(f"cannot read {path}: {error}") from error
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ModelPreregRefused(f"{path} is not valid JSON: {error}") from error


def contract_feature_names(path=FEATURE_CONTRACT_PATH):
    """The 99 frozen field names, read from B13f itself.

    Parsed from the source document rather than copied into a list here. A copy agrees with itself
    forever while the contract moves on, which is the failure this cross-check exists to catch.
    """
    try:
        text = pathlib.Path(path).read_text()
    except OSError as error:
        raise ModelPreregRefused(f"cannot read the feature contract {path}: {error}") from error
    fields = {int(index): name for index, name in
              re.findall(r"^\|\s*(\d+)\s*\|\s*`([a-z0-9_]+)`\s*\|", text, re.M)}
    if len(fields) != EXPECTED_FEATURE_COUNT:
        raise ModelPreregRefused(
            f"{path} yields {len(fields)} field names, expected {EXPECTED_FEATURE_COUNT}; the "
            "contract this preregistration binds to is not the one it was written against")
    return fields


def _scan_for_floats(node, path="$"):
    """Any float anywhere is refused, including inside a hyperparameter grid.

    A float hyperparameter is the quietest reproducibility failure available: the same value
    serialised on two machines can differ in its last bits.
    """
    if isinstance(node, float):
        raise ModelPreregRefused(
            f"{path} is a float ({node!r}). Every quantity here is an integer or a named "
            "numerator/denominator pair; a float makes two identical models hash differently")
    if isinstance(node, dict):
        for key, value in node.items():
            _scan_for_floats(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _scan_for_floats(value, f"{path}[{index}]")


def verify_preregistration(document=None, feature_names=None, expected_sha256=None):
    """Every structural claim the frozen document makes, checked against itself and against B13f.

    `document`, `feature_names` and `expected_sha256` are injectable so that every branch below is
    reachable. With the real file each guard holds by construction and could never be shown to
    fire, and a check nobody can show works is worse than no check.
    """
    document = read_preregistration() if document is None else document
    expected = PREREGISTRATION_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    actual = canonical_sha256(document)
    if actual != expected:
        raise ModelPreregRefused(
            f"the model preregistration hashes {actual}, pinned {expected}. It was committed alone "
            "and before any implementation; a changed document is a different design")

    _scan_for_floats(document)

    if document.get("preregistration_id") != "B14C_MODEL_AND_SELECTION_V1":
        raise ModelPreregRefused("preregistration_id is not the frozen one")
    for flag in ("committed_before_any_fit", "committed_before_any_outcome_exists"):
        if document.get(flag) is not True:
            raise ModelPreregRefused(f"{flag} is not true; the freeze claims its own ordering")
    for flag in ("b11a_composition_inspected", "burned_outcome_distributions_inspected"):
        if document.get(flag) is not False:
            raise ModelPreregRefused(f"{flag} is not false")

    eligibility = document["eligibility"]
    if eligibility.get("eligible_windows") != []:
        raise ModelPreregRefused(
            "eligible_windows is not empty. A window may only be added by a superseding "
            "preregistration, never by editing this one")
    if eligibility.get("b11a_eligible") is not False:
        raise ModelPreregRefused("b11a_eligible is not false; B13f section 0 makes it permanent")
    if eligibility.get("fitting_permitted") is not False:
        raise ModelPreregRefused("fitting_permitted is not false")

    families = document["candidate_families"]
    if len(families) != EXPECTED_FAMILY_COUNT:
        raise ModelPreregRefused(
            f"{len(families)} candidate families, expected {EXPECTED_FAMILY_COUNT}")
    if [family["index"] for family in families] != list(range(EXPECTED_FAMILY_COUNT)):
        raise ModelPreregRefused(
            "family indices are not 0..n-1 in order; tie-break 3 is 'lower family index', which is "
            "not a total order over indices that repeat or skip")
    if len({family["id"] for family in families}) != len(families):
        raise ModelPreregRefused("two candidate families share an id")
    for family in families:
        enumeration = family.get("grid_enumeration")
        if enumeration is not None and len(enumeration) != family["grid_size"]:
            raise ModelPreregRefused(
                f"{family['id']} declares grid_size {family['grid_size']} but enumerates "
                f"{len(enumeration)}; the enumeration is what gets run and the size is what gets "
                "counted for multiplicity, so they cannot disagree")

    accounting = document["selection"]["family_accounting"]
    per_horizon = sum(family["grid_size"] for family in families)
    if accounting["configurations_per_horizon"] != per_horizon:
        raise ModelPreregRefused(
            f"configurations_per_horizon is {accounting['configurations_per_horizon']}, the grids "
            f"sum to {per_horizon}. An understated family understates the correction")
    horizons = 1 + len(document["target"]["secondary_horizons"])
    if horizons != EXPECTED_HORIZON_COUNT:
        raise ModelPreregRefused(f"{horizons} horizons, expected {EXPECTED_HORIZON_COUNT}")
    if accounting["model_selection_family_size"] != per_horizon * horizons:
        raise ModelPreregRefused(
            f"model_selection_family_size is {accounting['model_selection_family_size']}, expected "
            f"{per_horizon * horizons}")
    if accounting["baseline_family_size"] != 16:
        raise ModelPreregRefused(
            "baseline_family_size is not B11b's frozen 16. A family that shrank between "
            "preregistration and evaluation shrinks the correction with it")
    # There was a further check here that the two family sizes are not equal, guarding against
    # merging them. It could never fire: the baseline is pinned to 16 and the model size to
    # per_horizon * horizons = 60 by the two checks above, so equality is already unreachable. A
    # branch nothing can provoke is a branch nobody can show works, so it is gone rather than
    # standing as decoration.

    selection = document["selection"]
    if selection["test_fold_touches"] != 1:
        raise ModelPreregRefused("the test fold must be touched exactly once")
    if selection["primary_metric"]["direction"] not in ("lower_is_better", "higher_is_better"):
        raise ModelPreregRefused("the primary metric declares no direction")
    forbidden = {entry["name"] for entry in selection["forbidden_selection_metrics"]}
    if selection["primary_metric"]["name"] in forbidden:
        raise ModelPreregRefused(
            f"the primary selection metric {selection['primary_metric']['name']!r} is also on the "
            "forbidden list")
    if len(selection["tie_breaks_in_strict_order"]) < 2:
        raise ModelPreregRefused(
            "fewer than two tie-breaks cannot be a total order, so some tie would be resolved by "
            "enumeration accident")

    calibration = document["calibration"]
    if calibration["is_selectable"] is not False:
        raise ModelPreregRefused(
            "calibration is selectable; that doubles the family and invites choosing it because "
            "it scored better")
    for fold in ("validation folds", "test fold"):
        if fold not in calibration["never_fitted_on"]:
            raise ModelPreregRefused(
                f"calibration does not exclude the {fold}; a probability calibrated on the "
                "evaluation fold is calibrated against the answer")

    codes = tuple(entry["code"] for entry in document["abstention"]["codes"])
    if codes != EXPECTED_ABSTENTION_CODES:
        raise ModelPreregRefused(f"abstention codes are {codes}, expected "
                                 f"{EXPECTED_ABSTENTION_CODES}")
    if document["abstention"]["at_risk"] is not False:
        raise ModelPreregRefused(
            "an abstention is marked at risk; a decision the policy declined risked nothing")
    if document["abstention"]["abstention_rate_is_not_a_knob"] is not True:
        raise ModelPreregRefused("the abstention rate is declared tunable")

    declared_leakage = tuple(entry.split()[0] for entry in document["leakage_constraints"])
    if declared_leakage != EXPECTED_LEAKAGE_CODES:
        raise ModelPreregRefused(
            f"leakage constraints are {declared_leakage}, expected {EXPECTED_LEAKAGE_CODES}")

    comparison = document["comparison_against_b11b"]
    if comparison["primary_comparator"] not in comparison["comparator_policies"]:
        raise ModelPreregRefused("the primary comparator is not among the comparator policies")
    if comparison["forbidden_comparison"]["id"] != "cross_window_comparison":
        raise ModelPreregRefused(
            "cross_window_comparison is not refused by name; comparing a model on one window "
            "against B11b's figures on B11a subtracts two windows and calls it a model")
    if comparison["evidence_statement"]["is_a_pass_fail_gate"] is not False:
        raise ModelPreregRefused("a pass/fail publication gate is preregistered; none is earned")

    locks = document["status_locks"]
    for key, value in REQUIRED_STATUS_LOCKS.items():
        if locks.get(key) != value:
            raise ModelPreregRefused(f"status lock {key} is {locks.get(key)!r}, expected {value!r}")
    for name in FORBIDDEN_STATUS_NAMES:
        if name not in locks["refused_status_names"]:
            raise ModelPreregRefused(f"{name!r} is not refused by name")

    names = contract_feature_names() if feature_names is None else feature_names
    known = set(names.values())
    cited = [field for pair in document["preprocessing"]["rational_pair_handling"]["pairs"]
             for field in pair] + document["missingness"]["field_level"]["governed_by"]
    unknown = sorted(set(cited) - known)
    if unknown:
        raise ModelPreregRefused(
            f"the preregistration cites fields absent from the feature contract: {unknown}. A "
            "design that misnames a field it binds to binds to nothing")
    pairs = document["preprocessing"]["rational_pair_handling"]["pairs"]
    if len(pairs) != EXPECTED_PAIR_COUNT:
        raise ModelPreregRefused(f"{len(pairs)} rational pairs, expected {EXPECTED_PAIR_COUNT}")
    for numerator, denominator in pairs:
        if not numerator.endswith("_numerator") or not denominator.endswith("_denominator"):
            raise ModelPreregRefused(
                f"pair ({numerator}, {denominator}) is not a numerator/denominator pair")
        if numerator[: -len("_numerator")] != denominator[: -len("_denominator")]:
            raise ModelPreregRefused(
                f"pair ({numerator}, {denominator}) joins two different quantities; a share's "
                "numerator over another share's denominator is not a number anyone declared")

    return {"schema_version": SCHEMA_VERSION, "preregistration_canonical_sha256": actual,
            "families": len(families), "configurations_per_horizon": per_horizon,
            "model_selection_family_size": accounting["model_selection_family_size"],
            "eligible_windows": 0, "fitting_permitted": False}


def assert_fit_permitted(document=None, window_id=None, expected_sha256=None):
    """The gate. Nothing may fit, and B11a may never fit under any document.

    Deliberately not a boolean anyone can read and ignore: every path raises, so a caller cannot
    proceed by forgetting to check a return value.
    """
    # B11a is refused FIRST, before the document is even read. The permanent refusal must not
    # depend on the document that carries it: a corrupted, drifted or unparseable preregistration
    # would otherwise fail on its hash and leave the B11a question unanswered, which is the one
    # question that has an answer regardless of what any document says.
    if window_id is not None and "b11a" in str(window_id).lower():
        raise FitRefused(
            f"{window_id} is B11a. The 99-field contract is permanently ineligible there: B11a's "
            "maturity conditions and unlock evidence were written for a no-model baseline over a "
            "17-field contract")
    document = read_preregistration() if document is None else document
    verify_preregistration(document, expected_sha256=expected_sha256)
    # One refusal, because one is all this document can produce. `verify_preregistration` pins
    # `eligible_windows` to empty, so any document reaching here has none — branches for "this
    # window is not on the list" and "the list has one but the gate is shut" could never fire, and
    # dead branches read as coverage while proving nothing. A future window does not arrive by
    # editing this list; it arrives with a SUPERSEDING preregistration carrying its own pin and its
    # own validator, and that validator is where its gate belongs.
    raise FitRefused(
        "no window is eligible, so nothing may be fitted. A window is added by a superseding "
        "preregistration that names it and carries its own split plan, never by editing this "
        "document")


def contract(document=None):
    return verify_preregistration(document)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true", help="verify the freeze and report")
    args = parser.parse_args(argv)
    if args.contract:
        print(json.dumps(contract(), indent=2, sort_keys=True))
    else:
        parser.error("nothing to do; --contract is the only action, because verifying is the only "
                     "thing this module does")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ModelPreregRefused as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
