"""B14a — immutable model artifact envelope. Offline. No weights, no algorithm, no fitting.

What this module is
-------------------
The envelope a model would have to arrive in, and the compatibility check inference would have to
pass. It binds an artifact to the exact feature contract, label preregistration, split plan, target,
horizon, algorithm identifier, explicit hyperparameters, seed, train-only transforms, training rows,
code revision and environment it was produced from.

It is **not** a model. There is no algorithm here, no weights, no training loop and no metric. The
envelope's whole job is to make an incompatible artifact impossible to use by accident.

Why an envelope at all
----------------------
A fitted model is a claim about a specific matrix: these columns, in this order, labelled this way,
over these rows. Every one of those is invisible in the weights. A model handed a matrix whose
columns were reordered produces numbers with no error and no meaning, and a model whose scaler was
fitted on the validation fold produces numbers that are better than it deserves. Both are silent,
and both are caught here by comparing hashes rather than by hoping.

Three refusals
--------------
1. **No default anything.** No algorithm, no hyperparameter, no transform, no metric, no threshold.
   Every hyperparameter must be declared by name before it may carry a value, so a parameter that
   appears later is an undeclared one rather than a new default.
2. **No transform fitted outside training.** Every transform names the folds it was fitted on, and
   any fold that is not a training fold of the bound split plan is refused.
3. **No performance claim.** `performance_status` is locked to `not_evaluated`. An artifact that
   called itself executable or profitable would be making a claim nothing in this project has
   earned, and it is refused by name.
"""
import argparse
import hashlib
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


B14A_SPLIT = _load("b14a_split_planner", "b14a_split_planner.py")
B13F = B14A_SPLIT.B13F
B10B = B14A_SPLIT.B10B

SCHEMA_VERSION = "1.0.0"

PERFORMANCE_NOT_EVALUATED = "not_evaluated"
# Declared so they can be refused by name rather than by omission. A status nobody listed is a
# status somebody invents.
PERFORMANCE_CLAIM_STATUSES = ("evaluated", "executable", "profitable", "production_ready",
                              "validated", "live")
PERFORMANCE_STATUSES = (PERFORMANCE_NOT_EVALUATED,) + PERFORMANCE_CLAIM_STATUSES
ATTAINABLE_PERFORMANCE_STATUSES = (PERFORMANCE_NOT_EVALUATED,)

TRANSFORM_FIELDS = ("transform_id", "fitted_on_fold_ids", "fit_row_hashes_sha256",
                    "parameters_sha256")

CALIBRATION_FIELDS = ("method_id", "fitted_on_fold_ids", "fit_row_hashes_sha256",
                      "parameters_sha256")

ENVIRONMENT_FIELDS = ("code_revision", "environment_manifest_sha256", "interpreter_id")

ARTIFACT_FIELDS = (
    "schema_version", "artifact_id",
    "feature_contract_sha256", "feature_order_sha256", "feature_contract_version",
    "label_preregistration_sha256", "split_plan_sha256", "split_status",
    "target_id", "horizon_id",
    "algorithm_id", "declared_hyperparameter_names", "hyperparameters", "random_seed",
    "transforms", "calibration",
    "training_row_ids_sha256", "training_evidence_sha256", "training_fold_ids",
    "environment", "performance_status", "eligible_for_b11a", "artifact_sha256",
)

# What an inference request must carry to be checked against an artifact.
REQUEST_FIELDS = ("feature_contract_sha256", "feature_order_sha256", "feature_contract_version",
                  "target_id", "horizon_id", "split_plan_sha256", "hyperparameters",
                  "random_seed", "transforms")

I01_FEATURE_CONTRACT_MISMATCH = "I01_feature_contract_mismatch"
I02_FEATURE_ORDER_MISMATCH = "I02_feature_order_mismatch"
I03_VERSION_MISMATCH = "I03_version_mismatch"
I04_TARGET_OR_HORIZON_MISMATCH = "I04_target_or_horizon_mismatch"
I05_SPLIT_PLAN_MISMATCH = "I05_split_plan_mismatch"
I06_UNDECLARED_HYPERPARAMETER = "I06_undeclared_hyperparameter"
I07_HYPERPARAMETER_VALUE_MISMATCH = "I07_hyperparameter_value_mismatch"
I08_SEED_MISMATCH = "I08_seed_mismatch"
I09_TRANSFORM_MISMATCH = "I09_transform_mismatch"
I10_TRANSFORM_FITTED_OUTSIDE_TRAINING = "I10_transform_fitted_outside_training"
I11_PERFORMANCE_CLAIM = "I11_performance_claim"
I12_B11A_ELIGIBILITY_CLAIM = "I12_b11a_eligibility_claim"
INCOMPATIBILITY_CODES = (I01_FEATURE_CONTRACT_MISMATCH, I02_FEATURE_ORDER_MISMATCH,
                         I03_VERSION_MISMATCH, I04_TARGET_OR_HORIZON_MISMATCH,
                         I05_SPLIT_PLAN_MISMATCH, I06_UNDECLARED_HYPERPARAMETER,
                         I07_HYPERPARAMETER_VALUE_MISMATCH, I08_SEED_MISMATCH,
                         I09_TRANSFORM_MISMATCH, I10_TRANSFORM_FITTED_OUTSIDE_TRAINING,
                         I11_PERFORMANCE_CLAIM, I12_B11A_ELIGIBILITY_CLAIM)


class ArtifactRefused(B14A_SPLIT.SplitRefused):
    """Raised when a model artifact cannot be sealed or used without asserting something untrue."""


class IncompatibleArtifact(ArtifactRefused):
    """Raised when an artifact does not match the request it is being used for.

    A separate class because the artifact may be perfectly well formed and simply be the wrong one,
    which is a different thing for a caller to handle.
    """


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------

def _non_empty(label, value):
    if not isinstance(value, str) or not value:
        raise ArtifactRefused(f"{label} must be a non-empty string, got {value!r}")
    return value


def _integer(label, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArtifactRefused(f"{label} must be an integer, got {value!r}")
    return value


def assert_no_float(record):
    """No float anywhere, hyperparameters included.

    A float hyperparameter is the quietest reproducibility failure available: the same value
    serialised on two machines can differ in its last bits, so two artifacts that are the same model
    hash differently — or worse, two different models hash the same. Rationals travel as named
    integer pairs.
    """
    for path, value in B14A_SPLIT._walk(record):
        if isinstance(value, float):
            raise ArtifactRefused(
                f"{path} is the float {value!r}. Every value in an artifact is an integer, a "
                "boolean, a string or null; a rational travels as a numerator/denominator pair, so "
                "two machines cannot disagree about what the artifact says")
    return True


def assert_hyperparameters(declared, values):
    """Every hyperparameter declared by name before it may carry a value.

    Declaration first, deliberately. Without it, a parameter that appears in a later version looks
    like a new default rather than an undeclared one, and nobody can tell which run used it.
    """
    if not isinstance(declared, list) or any(not isinstance(n, str) or not n for n in declared):
        raise ArtifactRefused("declared_hyperparameter_names must be a list of non-empty strings")
    if len(set(declared)) != len(declared):
        raise ArtifactRefused("declared_hyperparameter_names lists a name twice")
    if not isinstance(values, dict):
        raise ArtifactRefused("hyperparameters must be a mapping")
    undeclared = sorted(set(values) - set(declared))
    if undeclared:
        raise ArtifactRefused(
            f"{undeclared} carry values but were never declared. There is no default "
            "hyperparameter here: a value nobody declared is one nobody reviewed")
    missing = sorted(set(declared) - set(values))
    if missing:
        raise ArtifactRefused(
            f"{missing} were declared but carry no value; a declared parameter with no value is a "
            "default hiding in the algorithm")
    for name, value in sorted(values.items()):
        if isinstance(value, float):
            raise ArtifactRefused(
                f"hyperparameter {name!r} is a float; express it as an integer numerator and "
                "denominator so two machines cannot disagree about it")
        if value is not None and not isinstance(value, (int, bool, str, dict, list)):
            raise ArtifactRefused(
                f"hyperparameter {name!r} is a {type(value).__name__}; values are integers, "
                "booleans, strings, null, or a mapping/list of those")
    return True


def assert_transform(transform, training_fold_ids, label="transform"):
    """A transform names the folds it was fitted on, and every one must be a training fold."""
    if not isinstance(transform, dict) or set(transform) != set(TRANSFORM_FIELDS):
        raise ArtifactRefused(f"{label} must state {list(TRANSFORM_FIELDS)}")
    _non_empty(f"{label} transform_id", transform["transform_id"])
    _non_empty(f"{label} fit_row_hashes_sha256", transform["fit_row_hashes_sha256"])
    _non_empty(f"{label} parameters_sha256", transform["parameters_sha256"])
    folds = transform["fitted_on_fold_ids"]
    if not isinstance(folds, list) or not folds:
        raise ArtifactRefused(
            f"{label} does not name the folds it was fitted on; a transform that cannot say where "
            "it was fitted cannot be shown to have been fitted on training data")
    outside = sorted(set(folds) - set(training_fold_ids))
    if outside:
        raise ArtifactRefused(
            f"{label} was fitted on {outside}, which {'is' if len(outside) == 1 else 'are'} not "
            "training fold(s) of the bound split plan. A scaler fitted on validation produces "
            "numbers better than the model deserves, and nothing downstream can tell")
    return transform


def assert_artifact(artifact):
    """Every gate on one artifact, in one call."""
    if not isinstance(artifact, dict):
        raise ArtifactRefused(f"artifact must be a mapping, got {type(artifact).__name__}")
    missing = [field for field in ARTIFACT_FIELDS if field not in artifact]
    if missing:
        raise ArtifactRefused(f"artifact does not carry {missing}")
    unknown = [field for field in artifact if field not in ARTIFACT_FIELDS]
    if unknown:
        raise ArtifactRefused(
            f"artifact carries undeclared fields {sorted(unknown)}; an envelope shape nobody "
            "declared is one nobody reviewed")
    for field in ("artifact_id", "feature_contract_sha256", "feature_order_sha256",
                  "feature_contract_version", "label_preregistration_sha256", "split_plan_sha256",
                  "target_id", "horizon_id", "algorithm_id", "training_row_ids_sha256",
                  "training_evidence_sha256"):
        _non_empty(f"artifact {field}", artifact[field])
    _integer("artifact random_seed", artifact["random_seed"])

    if artifact["split_status"] not in B14A_SPLIT.ATTAINABLE_STATUSES:
        raise B14A_SPLIT.StatusGated(
            f"the bound split plan claims status {artifact['split_status']!r}. "
            + B14A_SPLIT._gate_sentence())

    if artifact["performance_status"] not in PERFORMANCE_STATUSES:
        raise ArtifactRefused(
            f"performance status {artifact['performance_status']!r} is not one of "
            f"{list(PERFORMANCE_STATUSES)}")
    if artifact["performance_status"] not in ATTAINABLE_PERFORMANCE_STATUSES:
        raise ArtifactRefused(
            f"an artifact may not ship claiming {artifact['performance_status']!r}. Nothing in "
            "this project has evaluated a model, so `not_evaluated` is the only honest status and "
            "the only attainable one; an executable or profitability claim here would be a claim "
            "nobody has earned")
    if artifact["eligible_for_b11a"]:
        raise ArtifactRefused(
            "an artifact may not claim B11a eligibility. B11a's evaluation was frozen as a "
            "NO-MODEL baseline; a model there would evaluate something nobody preregistered")

    folds = artifact["training_fold_ids"]
    if not isinstance(folds, list) or not folds:
        raise ArtifactRefused("an artifact must name the training folds it was fitted on")
    if len(set(folds)) != len(folds):
        raise ArtifactRefused("training_fold_ids lists a fold twice")

    assert_hyperparameters(artifact["declared_hyperparameter_names"], artifact["hyperparameters"])

    if not isinstance(artifact["transforms"], list):
        raise ArtifactRefused("artifact transforms must be a list")
    seen = set()
    for position, transform in enumerate(artifact["transforms"]):
        assert_transform(transform, folds, f"transform[{position}]")
        if transform["transform_id"] in seen:
            raise ArtifactRefused(f"transform {transform['transform_id']!r} appears twice")
        seen.add(transform["transform_id"])

    calibration = artifact["calibration"]
    if calibration is not None:
        if not isinstance(calibration, dict) or set(calibration) != set(CALIBRATION_FIELDS):
            raise ArtifactRefused(f"calibration must state {list(CALIBRATION_FIELDS)}")
        _non_empty("calibration method_id", calibration["method_id"])
        _non_empty("calibration fit_row_hashes_sha256", calibration["fit_row_hashes_sha256"])
        _non_empty("calibration parameters_sha256", calibration["parameters_sha256"])
        outside = sorted(set(calibration["fitted_on_fold_ids"]) - set(folds))
        if outside or not calibration["fitted_on_fold_ids"]:
            raise ArtifactRefused(
                f"calibration was fitted on {outside or 'nothing'}; calibration data is restricted "
                "to training folds, because a probability calibrated on the evaluation fold is "
                "calibrated against the answer")

    environment = artifact["environment"]
    if not isinstance(environment, dict) or set(environment) != set(ENVIRONMENT_FIELDS):
        raise ArtifactRefused(f"environment must state {list(ENVIRONMENT_FIELDS)}")
    for field in ENVIRONMENT_FIELDS:
        _non_empty(f"environment {field}", environment[field])

    assert_no_float(artifact)
    B14A_SPLIT.assert_no_association_evidence(artifact)
    return artifact


def seal_artifact(artifact_id, feature_contract_sha256, feature_order_sha256,
                  feature_contract_version, label_preregistration_sha256, split_plan_sha256,
                  split_status, target_id, horizon_id, algorithm_id,
                  declared_hyperparameter_names, hyperparameters, random_seed, training_fold_ids,
                  training_row_ids_sha256, training_evidence_sha256, environment,
                  transforms=None, calibration=None):
    """Assemble and validate one artifact. Every argument is required; none has a default."""
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "feature_contract_sha256": feature_contract_sha256,
        "feature_order_sha256": feature_order_sha256,
        "feature_contract_version": feature_contract_version,
        "label_preregistration_sha256": label_preregistration_sha256,
        "split_plan_sha256": split_plan_sha256,
        "split_status": split_status,
        "target_id": target_id,
        "horizon_id": horizon_id,
        "algorithm_id": algorithm_id,
        "declared_hyperparameter_names": list(declared_hyperparameter_names),
        "hyperparameters": dict(hyperparameters),
        "random_seed": random_seed,
        "transforms": [dict(t) for t in (transforms or [])],
        "calibration": dict(calibration) if calibration else None,
        "training_row_ids_sha256": training_row_ids_sha256,
        "training_evidence_sha256": training_evidence_sha256,
        "training_fold_ids": list(training_fold_ids),
        "environment": dict(environment),
        # Locked. The envelope cannot be sealed with any other value.
        "performance_status": PERFORMANCE_NOT_EVALUATED,
        "eligible_for_b11a": False,
        "artifact_sha256": None,
    }
    assert_artifact(artifact)
    artifact["artifact_sha256"] = artifact_hash(artifact)
    return artifact


def artifact_hash(artifact):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in artifact.items() if k != "artifact_sha256"}).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------
# Inference compatibility
# --------------------------------------------------------------------------------------------

def incompatibilities(artifact, request):
    """Every reason this artifact may not serve this request. Empty means it may."""
    assert_artifact(artifact)
    if artifact["artifact_sha256"] != artifact_hash(artifact):
        return [{"reason_code": I01_FEATURE_CONTRACT_MISMATCH,
                 "detail": "the artifact does not hash to what it claims; something in the "
                           "envelope changed after it was sealed"}]
    if not isinstance(request, dict):
        raise ArtifactRefused("request must be a mapping")
    missing = [field for field in REQUEST_FIELDS if field not in request]
    if missing:
        raise ArtifactRefused(
            f"request does not state {missing}; a compatibility check that skips a field is a "
            "check that passes for the wrong reason")

    reasons = []
    if request["feature_contract_sha256"] != artifact["feature_contract_sha256"]:
        reasons.append({"reason_code": I01_FEATURE_CONTRACT_MISMATCH,
                        "detail": "the feature contract is not the one this artifact was fitted "
                                  "against"})
    if request["feature_order_sha256"] != artifact["feature_order_sha256"]:
        reasons.append({
            "reason_code": I02_FEATURE_ORDER_MISMATCH,
            "detail": "the feature ORDER differs. The same columns in different positions is a "
                      "different matrix, and a model handed one produces numbers with no error and "
                      "no meaning"})
    if request["feature_contract_version"] != artifact["feature_contract_version"]:
        reasons.append({"reason_code": I03_VERSION_MISMATCH,
                        "detail": "the feature contract version differs"})
    if (request["target_id"] != artifact["target_id"]
            or request["horizon_id"] != artifact["horizon_id"]):
        reasons.append({"reason_code": I04_TARGET_OR_HORIZON_MISMATCH,
                        "detail": "the target or horizon differs; a model fitted for one horizon "
                                  "predicts nothing about another"})
    if request["split_plan_sha256"] != artifact["split_plan_sha256"]:
        reasons.append({"reason_code": I05_SPLIT_PLAN_MISMATCH,
                        "detail": "the split plan differs, so the rows this artifact never saw are "
                                  "not the rows the caller thinks"})

    requested = request["hyperparameters"]
    if not isinstance(requested, dict):
        raise ArtifactRefused("request hyperparameters must be a mapping")
    undeclared = sorted(set(requested) - set(artifact["declared_hyperparameter_names"]))
    if undeclared:
        reasons.append({"reason_code": I06_UNDECLARED_HYPERPARAMETER,
                        "detail": f"{undeclared} were never declared on this artifact"})
    for name in sorted(set(requested) & set(artifact["hyperparameters"])):
        if requested[name] != artifact["hyperparameters"][name]:
            reasons.append({"reason_code": I07_HYPERPARAMETER_VALUE_MISMATCH,
                            "detail": f"hyperparameter {name!r} differs from the fitted value"})
    if request["random_seed"] != artifact["random_seed"]:
        reasons.append({
            "reason_code": I08_SEED_MISMATCH,
            "detail": "the random seed differs. A seed is part of what produced the weights, and "
                      "a run that cannot reproduce them cannot be said to have checked them"})

    artifact_transforms = {t["transform_id"]: t for t in artifact["transforms"]}
    requested_transforms = {t["transform_id"]: t for t in request["transforms"]}
    if set(requested_transforms) != set(artifact_transforms):
        reasons.append({"reason_code": I09_TRANSFORM_MISMATCH,
                        "detail": f"transforms differ: artifact has "
                                  f"{sorted(artifact_transforms)}, request has "
                                  f"{sorted(requested_transforms)}"})
    for name in sorted(set(requested_transforms) & set(artifact_transforms)):
        if requested_transforms[name]["parameters_sha256"] \
                != artifact_transforms[name]["parameters_sha256"]:
            reasons.append({"reason_code": I09_TRANSFORM_MISMATCH,
                            "detail": f"transform {name!r} has different fitted parameters"})
        outside = sorted(set(requested_transforms[name]["fitted_on_fold_ids"])
                         - set(artifact["training_fold_ids"]))
        if outside:
            reasons.append({"reason_code": I10_TRANSFORM_FITTED_OUTSIDE_TRAINING,
                            "detail": f"transform {name!r} claims a fit on {outside}, which are "
                                      "not training folds"})

    if artifact["performance_status"] != PERFORMANCE_NOT_EVALUATED:
        reasons.append({"reason_code": I11_PERFORMANCE_CLAIM,
                        "detail": "the artifact carries a performance claim"})
    if artifact["eligible_for_b11a"] or request.get("window_id", "").lower().startswith("b11a"):
        reasons.append({"reason_code": I12_B11A_ELIGIBILITY_CLAIM,
                        "detail": "B11a was frozen as a no-model baseline and no model may be "
                                  "scored against it"})
    return reasons


def require_compatible(artifact, request):
    """Fail closed. An incompatible artifact used anyway produces numbers with no error."""
    reasons = incompatibilities(artifact, request)
    if reasons:
        raise IncompatibleArtifact(
            "this artifact may not serve this request: "
            + "; ".join(f"{r['reason_code']} — {r['detail']}" for r in reasons))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "artifact_fields": list(ARTIFACT_FIELDS),
        "request_fields": list(REQUEST_FIELDS),
        "performance_statuses": list(PERFORMANCE_STATUSES),
        "attainable_performance_statuses": list(ATTAINABLE_PERFORMANCE_STATUSES),
        "incompatibility_codes": list(INCOMPATIBILITY_CODES),
        "default_algorithm": None,
        "default_hyperparameters": {},
        "default_transform": None,
        "default_metric": None,
        "default_threshold": None,
        "model_fitted": False,
        "weights_stored": False,
        "eligible_for_b11a": False,
        "floats_used": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"ArtifactRefused: {error}", file=sys.stderr)
        sys.exit(2)
