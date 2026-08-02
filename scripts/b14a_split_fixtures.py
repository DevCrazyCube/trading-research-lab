"""B14a fixture corpus and structural report — synthetic rows only. No fitting, no metrics.

Every row below is invented. No model was fitted, no window is eligible, no corpus was read and
B11a was never touched. The report publishes **fold counts, exclusion counts and hashes** — no
metric, no score, no performance figure of any kind, because there is nothing to measure and a
number here would be read as one.

The corpus exists to exercise the seams that only appear in combination: a label window that reaches
across a boundary while its t0 sits safely behind it, an actor bridge A—B—C that a per-row split
would tear apart, an address that is a creator in one row and a trader in another, and censored
outcomes that must be excluded rather than recoded.
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


# ONE module graph. Loading the planner separately would give a second, distinct set of exception
# classes, so `except SPLIT.SplitRefused` would not catch what ARTIFACT raises — and the gate below
# would report clean while silently missing every artifact refusal.
ARTIFACT = _load("b14a_model_artifact", "b14a_model_artifact.py")
SPLIT = ARTIFACT.B14A_SPLIT
B10B = SPLIT.B10B

TARGET = "synthetic_target_a"
HORIZON = "synthetic_horizon_600_slots"
LABEL_SPAN = 600

# Ranges chosen to be readable, not tuned. They are the fixture's own and stand in for what a real
# preregistration would freeze.
PURGE = 50
EMBARGO = 100


def at(slot, index=0, outer=0, inner=0):
    return {"slot": slot, "transaction_index": index, "outer_index": outer, "inner_index": inner}


def row(row_id, slot, creator, user, label_span=LABEL_SPAN, status=SPLIT.LABEL_OBSERVED,
        value=None, target=TARGET, horizon=HORIZON):
    return {
        "row_id": row_id,
        "t0": at(slot),
        "label_window_end_slot": slot + label_span,
        "horizon_id": horizon,
        "target_id": target,
        "label_status": status,
        "label_value": value if status == SPLIT.LABEL_OBSERVED else None,
        "creator": creator,
        "user": user,
        "feature_order_sha256": "f" * 64,
        "preregistration_sha256": "p" * 64,
        "source_sha256": hashlib.sha256(row_id.encode()).hexdigest(),
        "label_sha256": hashlib.sha256((row_id + "label").encode()).hexdigest(),
    }


def build_fixture_corpus():
    """A deterministic synthetic corpus, one entry per seam worth exercising."""
    rows = []

    # 1. Ordinary training rows, well clear of every boundary.
    for index in range(6):
        rows.append(row(f"train-{index}", 1_000 + index * 100,
                        f"CreatorTrain{index}", f"UserTrain{index}", value=1))

    # 2. A row whose t0 sits safely in training but whose LABEL WINDOW reaches the validation
    #    segment. The purge exists for exactly this row, and t0 alone cannot see it.
    rows.append(row("train-overlaps-validation", 1_950, "CreatorOverlap", "UserOverlap", value=1))

    # 3. Censored and unavailable outcomes. Excluded, never recoded as a negative.
    rows.append(row("train-censored", 1_300, "CreatorCensored", "UserCensored",
                    status=SPLIT.LABEL_RIGHT_CENSORED))
    rows.append(row("train-unavailable", 1_400, "CreatorUnavailable", "UserUnavailable",
                    status=SPLIT.LABEL_UNAVAILABLE))

    # 4. The actor bridge. A and B share a creator; B and C share a user; nothing links A to C
    #    directly, and all three must end up in one group.
    rows.append(row("bridge-a", 1_100, "BridgeCreator", "BridgeUserA", value=1))
    rows.append(row("bridge-b", 1_200, "BridgeCreator", "BridgeUserB", value=1))
    rows.append(row("bridge-c", 1_250, "BridgeCreatorC", "BridgeUserB", value=1))

    # 5. The role swap. One address creates in the training period and trades in the validation
    #    period. Pooled identities put both rows in one group, which then spans two segments and is
    #    dropped whole.
    rows.append(row("role-swap-train", 1_500, "RoleSwapAddress", "UserRoleSwapA", value=1))
    rows.append(row("role-swap-validation", 2_600, "CreatorRoleSwapB", "RoleSwapAddress", value=1))

    # 6. Clean validation and test rows.
    for index in range(4):
        rows.append(row(f"validation-{index}", 2_700 + index * 50,
                        f"CreatorValidation{index}", f"UserValidation{index}", value=1))
    for index in range(4):
        rows.append(row(f"test-{index}", 4_000 + index * 50,
                        f"CreatorTest{index}", f"UserTest{index}", value=1))

    return rows


def build_spec():
    return {
        "target_id": TARGET,
        "horizon_id": HORIZON,
        "purge_slots": PURGE,
        "embargo_slots": EMBARGO,
        "preregistration_reference": "synthetic fixture; stands in for a frozen preregistration",
        "rationale": "fixture ranges chosen for readability, not fitted to any result; no real "
                     "window is named and none is eligible",
        "folds": [
            {"fold_id": "fold-1",
             "train": {"first_slot_inclusive": 1_000, "last_slot_inclusive": 2_000},
             "validation": {"first_slot_inclusive": 2_500, "last_slot_inclusive": 3_000},
             "test": {"first_slot_inclusive": 4_000, "last_slot_inclusive": 4_500}},
        ],
    }


def build_artifact(plan):
    return ARTIFACT.seal_artifact(
        artifact_id="synthetic-artifact-1",
        feature_contract_sha256="c" * 64,
        feature_order_sha256="o" * 64,
        feature_contract_version="1.0.0",
        label_preregistration_sha256="l" * 64,
        split_plan_sha256=plan["plan_sha256"],
        split_status=plan["status"],
        target_id=TARGET,
        horizon_id=HORIZON,
        algorithm_id="synthetic-algorithm-identifier-only",
        declared_hyperparameter_names=["depth", "shrinkage_numerator", "shrinkage_denominator"],
        hyperparameters={"depth": 3, "shrinkage_numerator": 1, "shrinkage_denominator": 10},
        random_seed=20260802,
        training_fold_ids=[fold["fold_id"] for fold in plan["folds"]],
        training_row_ids_sha256="t" * 64,
        training_evidence_sha256="e" * 64,
        environment={"code_revision": "synthetic-revision",
                     "environment_manifest_sha256": "m" * 64,
                     "interpreter_id": "synthetic-interpreter"},
        transforms=[{"transform_id": "synthetic-transform",
                     "fitted_on_fold_ids": [plan["folds"][0]["fold_id"]],
                     "fit_row_hashes_sha256": "r" * 64,
                     "parameters_sha256": "q" * 64}],
        calibration={"method_id": "synthetic-calibration",
                     "fitted_on_fold_ids": [plan["folds"][0]["fold_id"]],
                     "fit_row_hashes_sha256": "r" * 64,
                     "parameters_sha256": "k" * 64})


def compatible_request(artifact):
    return {"feature_contract_sha256": artifact["feature_contract_sha256"],
            "feature_order_sha256": artifact["feature_order_sha256"],
            "feature_contract_version": artifact["feature_contract_version"],
            "target_id": artifact["target_id"], "horizon_id": artifact["horizon_id"],
            "split_plan_sha256": artifact["split_plan_sha256"],
            "hyperparameters": dict(artifact["hyperparameters"]),
            "random_seed": artifact["random_seed"],
            "transforms": [dict(t) for t in artifact["transforms"]]}


def check():
    """Structural counts and checks only. No metric, no score, no performance figure."""
    rows = build_fixture_corpus()
    spec = build_spec()
    plan = SPLIT.plan_split(rows, spec)
    groups = SPLIT.identity_groups(SPLIT.ordered_rows(rows))
    artifact = build_artifact(plan)

    report = {
        "schema_version": SPLIT.SCHEMA_VERSION,
        "status": plan["status"],
        "rows_supplied": len(rows),
        "identity_groups": len(groups),
        "largest_group_size": max(len(members) for members in groups.values()),
        "folds_planned": len(plan["folds"]),
        "row_counts_by_segment": {segment: sum(fold["row_counts"][segment]
                                               for fold in plan["folds"])
                                  for segment in SPLIT.SEGMENTS},
        "rows_excluded": plan["accounting"]["rows_excluded"],
        "exclusions_by_reason": dict(plan["accounting"]["exclusions_by_reason"]),
        "order_independent": False,
        "groups_never_span_segments": False,
        "purge_holds_for_every_training_row": False,
        "censored_rows_excluded": False,
        "artifact_sealed": False,
        "artifact_compatible_with_its_own_request": False,
        "gated_statuses_refused": {},
        "association_ledger_refused_as_cluster_artifact": False,
        "metrics_reported": False,
        "metrics_reported_reason":
            "nothing has been fitted or evaluated, so any number here would be read as a "
            "performance figure for a model that does not exist",
        "model_fitted": False,
        "b11a_touched": False,
        "errors": [],
    }

    shuffled = SPLIT.plan_split(list(reversed(rows)), spec)
    report["order_independent"] = shuffled["plan_sha256"] == plan["plan_sha256"]
    if not report["order_independent"]:
        report["errors"].append({"error": "the plan depends on row insertion order"})

    spanning = 0
    for fold in plan["folds"]:
        occupied = {}
        for segment in SPLIT.SEGMENTS:
            for group in fold["groups"][segment]:
                occupied.setdefault(group, set()).add(segment)
        spanning += sum(1 for segments in occupied.values() if len(segments) > 1)
    report["groups_never_span_segments"] = spanning == 0
    if spanning:
        report["errors"].append({"error": f"{spanning} identity groups span segments"})

    by_id = {r["row_id"]: r for r in rows}
    violations = 0
    for fold in plan["folds"]:
        for row_id in fold["rows"][SPLIT.SEGMENT_TRAIN]:
            for segment in SPLIT.EVALUATION_SEGMENTS:
                boundary = fold["ranges"][segment]["first_slot_inclusive"]
                if by_id[row_id]["label_window_end_slot"] + PURGE >= boundary:
                    violations += 1
    report["purge_holds_for_every_training_row"] = violations == 0
    if violations:
        report["errors"].append({"error": f"{violations} training rows reach an evaluation segment"})

    assigned = {row_id for fold in plan["folds"] for segment in SPLIT.SEGMENTS
                for row_id in fold["rows"][segment]}
    censored = {r["row_id"] for r in rows if r["label_status"] != SPLIT.LABEL_OBSERVED}
    report["censored_rows_excluded"] = not (censored & assigned)
    if censored & assigned:
        report["errors"].append({"error": "a censored row was assigned to a fold"})

    report["artifact_sealed"] = bool(artifact["artifact_sha256"])
    try:
        ARTIFACT.require_compatible(artifact, compatible_request(artifact))
        report["artifact_compatible_with_its_own_request"] = True
    except SPLIT.SplitRefused as error:
        report["errors"].append({"error": f"the artifact rejects its own request: {error}"[:200]})

    for status in (SPLIT.STATUS_PUBLICATION_GRADE, SPLIT.STATUS_MODEL_ELIGIBLE):
        try:
            SPLIT.require_status(status)
            report["gated_statuses_refused"][status] = False
            report["errors"].append({"error": f"{status} was granted"})
        except SPLIT.StatusGated:
            report["gated_statuses_refused"][status] = True

    ledger = {"confidence_status": "uncalibrated_evidence_only", "links": [],
              "evidence_hash_chain_sha256": "0" * 64}
    try:
        SPLIT.require_status(SPLIT.STATUS_MODEL_ELIGIBLE, ledger)
        report["errors"].append({"error": "an association ledger closed the cluster gate"})
    except SPLIT.StatusGated as error:
        report["association_ledger_refused_as_cluster_artifact"] = \
            "ASSOCIATION EVIDENCE" in str(error)
        if not report["association_ledger_refused_as_cluster_artifact"]:
            report["errors"].append({"error": "the ledger was refused generically, so nobody is "
                                               "told what they actually passed"})

    report["determinism"] = {"plan_sha256": plan["plan_sha256"],
                             "artifact_sha256": artifact["artifact_sha256"]}
    return report


def gate_failures(report):
    """Why this run does not pass the gate. Pure, so the gate's own logic can be tested."""
    failures = []
    if report["errors"]:
        failures.append(f"{len(report['errors'])} integrity errors: {report['errors'][:5]}")
    for field in ("order_independent", "groups_never_span_segments",
                  "purge_holds_for_every_training_row", "censored_rows_excluded",
                  "artifact_sealed", "artifact_compatible_with_its_own_request",
                  "association_ledger_refused_as_cluster_artifact"):
        if not report[field]:
            failures.append(f"{field} did not hold")
    if not all(report["gated_statuses_refused"].values()):
        failures.append("a gated status was granted")
    if report["status"] not in SPLIT.ATTAINABLE_STATUSES:
        failures.append("the plan shipped with an unattainable status")
    if report["metrics_reported"] or report["model_fitted"] or report["b11a_touched"]:
        failures.append("this pass reports no metric, fits no model and does not touch B11a")
    if not report["exclusions_by_reason"].get(SPLIT.X02_PURGED_LABEL_WINDOW_OVERLAP):
        failures.append("no fixture exercised the purge")
    if not report["exclusions_by_reason"].get(SPLIT.X04_GROUP_SPANS_SEGMENTS):
        failures.append("no fixture exercised a group spanning segments")
    if not report["exclusions_by_reason"].get(SPLIT.X01_LABEL_NOT_OBSERVED):
        failures.append("no fixture exercised a censored label")
    return failures


def assert_clean():
    report = check()
    failures = gate_failures(report)
    if failures:
        raise SPLIT.SplitRefused("; ".join(failures))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    report = assert_clean() if args.gate else check()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"SplitRefused: {error}", file=sys.stderr)
        sys.exit(2)
