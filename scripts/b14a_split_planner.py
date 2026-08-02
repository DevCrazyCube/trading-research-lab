"""B14a — leakage-safe walk-forward split planner. Offline, synthetic only. No fitting, no window.

What this module is
-------------------
A pure planner that turns decision rows into strictly chronological walk-forward folds, and refuses
every arrangement that would let an evaluation see something a training row already knew.

The three leaks it is built against
-----------------------------------
1. **The label window that outlives the boundary.** A training row's t0 can sit safely before a test
   fold while its OUTCOME is still being observed inside it. The row is then labelled by the same
   period it is being evaluated against. This is the leak that a naive "sort by t0 and cut" produces
   every time, and t0 alone cannot see it — the purge is computed on `label_window_end`, never on
   t0.
2. **The actor who spans the cut.** One creator with rows on both sides of a boundary trains the
   model on their own future. Grouping by row is not enough, and grouping by creator is not enough
   either: a creator in one row can be a trader in another, so the identities must be pooled into a
   single space and closed transitively. A—B through a shared creator and B—C through a shared user
   puts A, B and C in one group.
3. **The censored label read as a loss.** A right-censored outcome is not a zero. Recoding it as one
   teaches the model that "we stopped looking" and "it went to nothing" are the same event, and the
   second is much rarer than the first.

What it will not do
-------------------
No default train, validation or test range. No default purge or embargo. Every span is the caller's
and must arrive with a preregistration reference: a split boundary chosen after seeing which side
scored better is the oldest mistake in this field, and a module that supplied one would have made
that choice for everybody.

The exact-identity union here is **exact string equality only**. It never consumes B13b association
evidence, and funding-cluster leakage remains an **open gate**: `publication_grade` and
`model_eligible` are unreachable until a separately calibrated point-in-time cluster artifact
exists. This module can only ever produce `research_plumbing_only`.
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


B13F = _load("b13f_feature_vector", "b13f_feature_vector.py")
B13A = B13F.B13A
B10B = B13F.B10B

SCHEMA_VERSION = "1.0.0"

COORDINATE_FIELDS = B13A.COORDINATE_FIELDS

PURGE_RULE = (
    "A training row may remain in a fold only if its LABEL OBSERVATION WINDOW finishes strictly "
    "before the evaluation segment begins, with the caller's purge span in between: "
    "label_window_end_slot + purge_slots < evaluation_first_slot. The test is on the label window "
    "end and never on t0, because a decision taken safely before a boundary can still be labelled "
    "by the period it is about to be evaluated against.")

EMBARGO_RULE = (
    "A row may enter a training segment that follows an evaluation segment only if its t0 is at "
    "least the caller's embargo span after that evaluation segment ended: "
    "t0_slot >= previous_evaluation_last_slot + embargo_slots. Without it, the rows immediately "
    "after an evaluation period carry its residue into the next training set.")

R5_RULE = (
    "Rows are grouped by the transitive closure of EXACT identity equality over the pooled set of "
    "creator and user addresses. Two rows share a group if they name the same address in any role, "
    "and the closure is transitive: A—B through a shared creator and B—C through a shared user put "
    "A, B and C in one group. A group may appear in exactly one segment; a group spanning two is "
    "excluded whole, and a plan that ships one is refused.")

# --------------------------------------------------------------------------------------------
# Statuses
# --------------------------------------------------------------------------------------------

LABEL_OBSERVED = "observed"
LABEL_RIGHT_CENSORED = "right_censored"
LABEL_UNAVAILABLE = "unavailable"
LABEL_STATUSES = (LABEL_OBSERVED, LABEL_RIGHT_CENSORED, LABEL_UNAVAILABLE)

SEGMENT_TRAIN = "train"
SEGMENT_VALIDATION = "validation"
SEGMENT_TEST = "test"
SEGMENTS = (SEGMENT_TRAIN, SEGMENT_VALIDATION, SEGMENT_TEST)
EVALUATION_SEGMENTS = (SEGMENT_VALIDATION, SEGMENT_TEST)

STATUS_RESEARCH_PLUMBING_ONLY = "research_plumbing_only"
STATUS_PUBLICATION_GRADE = "publication_grade"
STATUS_MODEL_ELIGIBLE = "model_eligible"
PLAN_STATUSES = (STATUS_RESEARCH_PLUMBING_ONLY, STATUS_PUBLICATION_GRADE, STATUS_MODEL_ELIGIBLE)

# The only status this module can produce. The other two are gated on an artifact nobody has.
ATTAINABLE_STATUSES = (STATUS_RESEARCH_PLUMBING_ONLY,)

# Deliberately empty. Not "none supplied" but "no artifact type is acceptable yet".
ACCEPTED_CLUSTER_ARTIFACT_TYPES = ()

CLUSTER_ARTIFACT_REQUIREMENTS = (
    "calibrated against a validation set that is not the one it will be used on",
    "preregistered — the merge rule and its threshold frozen before the cohort was enumerated",
    "complete and point-in-time — every link from evidence at or before each row's own t0",
    "provenanced — naming its inputs, its rule and its hash",
)

# --------------------------------------------------------------------------------------------
# Exclusion and refusal codes
# --------------------------------------------------------------------------------------------

X01_LABEL_NOT_OBSERVED = "X01_label_not_observed"
X02_PURGED_LABEL_WINDOW_OVERLAP = "X02_purged_label_window_overlap"
X03_EMBARGOED_AFTER_EVALUATION = "X03_embargoed_after_evaluation"
X04_GROUP_SPANS_SEGMENTS = "X04_group_spans_segments"
X05_OUTSIDE_EVERY_RANGE = "X05_outside_every_range"
EXCLUSION_CODES = (X01_LABEL_NOT_OBSERVED, X02_PURGED_LABEL_WINDOW_OVERLAP,
                   X03_EMBARGOED_AFTER_EVALUATION, X04_GROUP_SPANS_SEGMENTS,
                   X05_OUTSIDE_EVERY_RANGE)

# --------------------------------------------------------------------------------------------
# Record shapes
# --------------------------------------------------------------------------------------------

ROW_FIELDS = ("row_id", "t0", "label_window_end_slot", "horizon_id", "target_id", "label_status",
              "label_value", "creator", "user", "feature_order_sha256", "preregistration_sha256",
              "source_sha256", "label_sha256")

RANGE_FIELDS = ("first_slot_inclusive", "last_slot_inclusive")

FOLD_SPEC_FIELDS = ("fold_id", "train", "validation", "test")

SPLIT_SPEC_FIELDS = ("target_id", "horizon_id", "folds", "purge_slots", "embargo_slots",
                     "preregistration_reference", "rationale")

PLAN_FIELDS = ("schema_version", "purge_rule", "embargo_rule", "r5_rule", "status", "target_id",
               "horizon_id", "purge_slots", "embargo_slots", "preregistration_reference",
               "folds", "accounting", "exclusions", "row_evidence_sha256", "plan_sha256")


class SplitRefused(B13F.VectorRefused):
    """Raised when a split cannot be planned without letting an evaluation see the future."""


class StatusGated(SplitRefused):
    """Raised when a status is requested that an open gate has not been closed for.

    A separate class because nothing about the plan is wrong: the arithmetic is fine and the gate
    is somebody else's preregistration.
    """


# --------------------------------------------------------------------------------------------
# Gated operations
# --------------------------------------------------------------------------------------------

def _gate_sentence():
    return ("Funding-cluster leakage is an OPEN GATE. Two actors can be one person without sharing "
            "an address, and this planner groups by exact identity only — so a split it calls "
            "clean may still put one operator on both sides. Closing the gate needs a cluster "
            "artifact that is: " + "; ".join(CLUSTER_ARTIFACT_REQUIREMENTS)
            + ". No artifact type is accepted in this pass.")


def require_status(status, cluster_artifact=None):
    """Fail closed on anything above research plumbing."""
    if status not in PLAN_STATUSES:
        raise SplitRefused(f"status {status!r} is not one of {list(PLAN_STATUSES)}")
    if status in ATTAINABLE_STATUSES:
        return True
    if _looks_like_association_ledger(cluster_artifact):
        raise StatusGated(
            "that is a B13b ASSOCIATION EVIDENCE LEDGER, not a cluster artifact. It declares "
            "itself `uncalibrated_evidence_only` and its links explicitly do not assert common "
            "control; using it to close this gate would launder 'we do not know' into a grouping "
            "that decides which rows may see each other. " + _gate_sentence())
    raise StatusGated(f"{status!r} is not attainable. " + _gate_sentence())


def _looks_like_association_ledger(artifact):
    if not isinstance(artifact, dict):
        return False
    if artifact.get("confidence_status") == "uncalibrated_evidence_only":
        return True
    return "links" in artifact and "evidence_hash_chain_sha256" in artifact


def assert_no_association_evidence(record):
    """A ledger used as a grouping would decide which rows may see each other, on evidence that
    explicitly does not support it."""
    def walk(value, path="record"):
        if _looks_like_association_ledger(value):
            raise SplitRefused(
                f"{path} is a B13b ASSOCIATION EVIDENCE LEDGER. Grouping rows by uncalibrated "
                "association would decide which rows may see each other using links that "
                "explicitly do not assert common control")
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
    walk(record)
    return True


def assert_no_float(record):
    for path, value in _walk(record):
        if isinstance(value, float):
            raise SplitRefused(
                f"{path} is the float {value!r}. Slots, spans and counts are exact integers; a "
                "float here is a number somebody computed")
    return True


def _walk(value, path="record"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------

def _integer(label, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise SplitRefused(f"{label} must be an integer, got {value!r}")
    return value


def _non_negative(label, value):
    _integer(label, value)
    if value < 0:
        raise SplitRefused(f"{label} must not be negative, got {value}")
    return value


def _non_empty(label, value):
    if not isinstance(value, str) or not value:
        raise SplitRefused(f"{label} must be a non-empty string, got {value!r}")
    return value


def assert_row(row):
    """One decision row, fully specified."""
    if not isinstance(row, dict):
        raise SplitRefused(f"row must be a mapping, got {type(row).__name__}")
    missing = [field for field in ROW_FIELDS if field not in row]
    if missing:
        raise SplitRefused(f"row does not state {missing}")
    unknown = [field for field in row if field not in ROW_FIELDS]
    if unknown:
        raise SplitRefused(f"row carries undeclared fields {sorted(unknown)}")
    _non_empty("row_id", row["row_id"])
    for field in ("horizon_id", "target_id", "creator", "user", "feature_order_sha256",
                  "preregistration_sha256", "source_sha256", "label_sha256"):
        _non_empty(f"row {field}", row[field])
    coordinate = row["t0"]
    if not isinstance(coordinate, dict) or set(coordinate) != set(COORDINATE_FIELDS):
        raise SplitRefused(f"row t0 must be a full canonical coordinate {list(COORDINATE_FIELDS)}")
    for field in COORDINATE_FIELDS:
        _integer(f"row t0 {field}", coordinate[field])
    _non_negative("row label_window_end_slot", row["label_window_end_slot"])
    if row["label_window_end_slot"] < coordinate["slot"]:
        raise SplitRefused(
            f"row {row['row_id']} has a label window ending at {row['label_window_end_slot']}, "
            f"before its own decision at slot {coordinate['slot']}; an outcome cannot finish being "
            "observed before it starts")
    if row["label_status"] not in LABEL_STATUSES:
        raise SplitRefused(
            f"row label_status {row['label_status']!r} is not one of {list(LABEL_STATUSES)}")
    if row["label_status"] != LABEL_OBSERVED and row["label_value"] is not None:
        # The censored-as-loss leak, refused at the door.
        raise SplitRefused(
            f"row {row['row_id']} is {row['label_status']!r} yet carries the label value "
            f"{row['label_value']!r}. A right-censored outcome is NOT a zero: recoding it teaches "
            "the model that 'we stopped looking' and 'it went to nothing' are the same event, and "
            "the second is far rarer than the first")
    if row["label_value"] is not None and not isinstance(row["label_value"], (int, bool)):
        raise SplitRefused("row label_value must be an integer, a boolean or null")
    return row


def ordered_rows(rows):
    """Canonically ordered and duplicate-free. Arrival order is never trusted."""
    if isinstance(rows, (dict, str, bytes)):
        raise SplitRefused("rows must be a sequence of row mappings")
    decorated, seen = [], set()
    for position, row in enumerate(rows):
        assert_row(row)
        if row["row_id"] in seen:
            raise SplitRefused(
                f"row {position} reuses row_id {row['row_id']!r}; the same decision counted twice "
                "would sit in two folds at once")
        seen.add(row["row_id"])
        decorated.append(((tuple(row["t0"][f] for f in COORDINATE_FIELDS), row["row_id"]), row))
    decorated.sort(key=lambda pair: pair[0])
    return [row for _, row in decorated]


def assert_range(span, label):
    if not isinstance(span, dict) or set(span) != set(RANGE_FIELDS):
        raise SplitRefused(f"{label} must state {list(RANGE_FIELDS)}")
    _non_negative(f"{label} first_slot_inclusive", span["first_slot_inclusive"])
    _non_negative(f"{label} last_slot_inclusive", span["last_slot_inclusive"])
    if span["last_slot_inclusive"] < span["first_slot_inclusive"]:
        raise SplitRefused(f"{label} ends before it begins")
    return span


def assert_split_spec(spec):
    """The caller's ranges and spans. No default is offered for any of them."""
    if not isinstance(spec, dict):
        raise SplitRefused("split spec must be a mapping")
    missing = [field for field in SPLIT_SPEC_FIELDS if field not in spec]
    if missing:
        raise SplitRefused(
            f"split spec does not state {missing}. There is no default train range, no default "
            "purge and no default embargo: a boundary chosen after seeing which side scored better "
            "is the oldest mistake in this field, and a default would make that choice for "
            "everybody")
    unknown = [field for field in spec if field not in SPLIT_SPEC_FIELDS]
    if unknown:
        raise SplitRefused(f"split spec carries undeclared fields {sorted(unknown)}")
    _non_empty("split spec target_id", spec["target_id"])
    _non_empty("split spec horizon_id", spec["horizon_id"])
    _non_negative("purge_slots", spec["purge_slots"])
    _non_negative("embargo_slots", spec["embargo_slots"])
    _non_empty("split spec preregistration_reference", spec["preregistration_reference"])
    _non_empty("split spec rationale", spec["rationale"])
    if not isinstance(spec["folds"], list) or not spec["folds"]:
        raise SplitRefused("a split spec with no folds plans nothing")

    previous = None
    seen_ids = set()
    for position, fold in enumerate(spec["folds"]):
        if not isinstance(fold, dict) or set(fold) != set(FOLD_SPEC_FIELDS):
            raise SplitRefused(f"fold {position} must state {list(FOLD_SPEC_FIELDS)}")
        _non_empty(f"fold {position} fold_id", fold["fold_id"])
        if fold["fold_id"] in seen_ids:
            raise SplitRefused(f"fold id {fold['fold_id']!r} appears twice")
        seen_ids.add(fold["fold_id"])
        for segment in SEGMENTS:
            assert_range(fold[segment], f"fold {fold['fold_id']} {segment}")
        # Strictly chronological, and stated as one comparison chain so no ordering can slip past.
        if not (fold["train"]["last_slot_inclusive"] < fold["validation"]["first_slot_inclusive"]
                <= fold["validation"]["last_slot_inclusive"]
                < fold["test"]["first_slot_inclusive"]):
            raise SplitRefused(
                f"fold {fold['fold_id']} is not strictly chronological: train must end before "
                "validation begins and validation before test. Validation or test preceding "
                "training is training on the answer")
        if previous is not None and fold["test"]["first_slot_inclusive"] <= previous:
            raise SplitRefused(
                f"fold {fold['fold_id']} evaluates at or before the previous fold's test period; "
                "walk-forward means forward")
        previous = fold["test"]["last_slot_inclusive"]
    return spec


# --------------------------------------------------------------------------------------------
# R5 — the exact-identity union graph
# --------------------------------------------------------------------------------------------

def identity_groups(rows):
    """Transitive closure over EXACT identity equality, with creator and user pooled.

    Pooled deliberately. An address that creates one token and trades another is one address, and
    keeping a separate creator-space and user-space would let the same person sit on both sides of
    a boundary under two labels. That is the role-swap leak, and pooling closes it by construction.

    Exact string equality only. No association evidence, no inference, no similarity.
    """
    parent = {}

    def find(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[left] = right

    for row in rows:
        identity_a = ("identity", row["creator"])
        identity_b = ("identity", row["user"])
        node = ("row", row["row_id"])
        union(node, identity_a)
        union(node, identity_b)

    groups = {}
    for row in rows:
        groups.setdefault(find(("row", row["row_id"])), []).append(row["row_id"])
    # Keyed by the sorted member list so the group identifier is a property of the membership and
    # not of whichever root the union-find happened to pick.
    return {group_key(members): sorted(members) for members in groups.values()}


def group_key(members):
    return hashlib.sha256(
        json.dumps(sorted(members), separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def group_of(groups, row_id):
    for key, members in groups.items():
        if row_id in members:
            return key
    raise SplitRefused(f"row {row_id!r} belongs to no identity group")


# --------------------------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------------------------

def _segment_for(row, fold):
    for segment in SEGMENTS:
        span = fold[segment]
        if span["first_slot_inclusive"] <= row["t0"]["slot"] <= span["last_slot_inclusive"]:
            return segment
    return None


def _purge_reason(row, fold, purge_slots):
    """Whether this training row's label window reaches into an evaluation segment.

    Computed on the LABEL WINDOW END, never on t0. A decision taken safely before a boundary can
    still be labelled by the period it is about to be evaluated against, and t0 cannot see that.

    Measured against the EARLIEST evaluation instant rather than each segment in turn. Chronology
    is already enforced, so validation always begins before test and a window reaching test has
    reached validation first; a per-segment loop would have a branch that could never fire.
    """
    segment = min(EVALUATION_SEGMENTS, key=lambda name: fold[name]["first_slot_inclusive"])
    boundary = fold[segment]["first_slot_inclusive"]
    if row["label_window_end_slot"] + purge_slots >= boundary:
        return {
            "reason_code": X02_PURGED_LABEL_WINDOW_OVERLAP,
            "detail": f"label window ends at {row['label_window_end_slot']}; with a purge of "
                      f"{purge_slots} slots it reaches the {segment} segment beginning at "
                      f"{boundary}, the first evaluation instant in this fold. The row would be "
                      "labelled by the period it is evaluated against",
            "segment": segment}
    return None


def _embargo_reason(row, fold, embargo_slots, previous_evaluation_last_slot):
    if previous_evaluation_last_slot is None:
        return None
    threshold = previous_evaluation_last_slot + embargo_slots
    if row["t0"]["slot"] < threshold:
        return {
            "reason_code": X03_EMBARGOED_AFTER_EVALUATION,
            "detail": f"t0 at slot {row['t0']['slot']} is inside the {embargo_slots}-slot embargo "
                      f"after the previous evaluation ended at "
                      f"{previous_evaluation_last_slot}; rows immediately after an evaluation "
                      "period carry its residue into the next training set",
            "segment": SEGMENT_TRAIN}
    return None


def plan_split(rows, spec, status=STATUS_RESEARCH_PLUMBING_ONLY, cluster_artifact=None):
    """One walk-forward plan. Pure: it assigns rows and refuses arrangements, and fits nothing."""
    require_status(status, cluster_artifact)
    assert_no_association_evidence({"rows": rows, "spec": spec, "artifact": cluster_artifact})
    spec = assert_split_spec(spec)
    rows = ordered_rows(rows)

    for row in rows:
        if row["target_id"] != spec["target_id"] or row["horizon_id"] != spec["horizon_id"]:
            # Each horizon and target is planned separately. Mixing them puts rows labelled over
            # different spans into one fold, where a purge computed for one is wrong for the other.
            raise SplitRefused(
                f"row {row['row_id']} is {row['target_id']}/{row['horizon_id']} in a plan for "
                f"{spec['target_id']}/{spec['horizon_id']}. Each target and horizon is planned "
                "separately: one purge span cannot be correct for two different label windows")

    groups = identity_groups(rows)
    by_id = {row["row_id"]: row for row in rows}
    exclusions, folds = [], []
    previous_evaluation_last_slot = None

    for fold in spec["folds"]:
        assignment = {segment: [] for segment in SEGMENTS}
        placed = {}
        for row in rows:
            segment = _segment_for(row, fold)
            if segment is None:
                continue
            if row["label_status"] != LABEL_OBSERVED:
                exclusions.append({
                    "fold_id": fold["fold_id"], "row_id": row["row_id"],
                    "reason_code": X01_LABEL_NOT_OBSERVED,
                    "detail": f"label status is {row['label_status']!r}; a censored or unavailable "
                              "outcome is excluded and is never recoded as a negative",
                    "segment": segment})
                continue
            if segment == SEGMENT_TRAIN:
                purge = _purge_reason(row, fold, spec["purge_slots"])
                if purge:
                    exclusions.append({"fold_id": fold["fold_id"], "row_id": row["row_id"],
                                       **purge})
                    continue
                embargo = _embargo_reason(row, fold, spec["embargo_slots"],
                                          previous_evaluation_last_slot)
                if embargo:
                    exclusions.append({"fold_id": fold["fold_id"], "row_id": row["row_id"],
                                       **embargo})
                    continue
            placed[row["row_id"]] = segment

        # R5: a group may occupy exactly one segment. One spanning two is dropped WHOLE — splitting
        # it would put an actor's own future in their training set, and keeping the larger half
        # would select on which side happened to have more rows.
        by_group = {}
        for row_id, segment in placed.items():
            by_group.setdefault(group_of(groups, row_id), set()).add(segment)
        for group, segments in sorted(by_group.items()):
            if len(segments) > 1:
                for row_id in sorted(placed):
                    if group_of(groups, row_id) == group:
                        exclusions.append({
                            "fold_id": fold["fold_id"], "row_id": row_id,
                            "reason_code": X04_GROUP_SPANS_SEGMENTS,
                            "detail": f"identity group {group} occupies {sorted(segments)}; rows "
                                      "connected through an exact shared creator or user stay in "
                                      "one segment or none",
                            "segment": placed[row_id]})
                        del placed[row_id]

        for row_id, segment in placed.items():
            assignment[segment].append(row_id)
        for segment in SEGMENTS:
            assignment[segment].sort()
        folds.append({
            "fold_id": fold["fold_id"],
            "ranges": {segment: dict(fold[segment]) for segment in SEGMENTS},
            "rows": assignment,
            "row_counts": {segment: len(assignment[segment]) for segment in SEGMENTS},
            "groups": {segment: sorted({group_of(groups, row_id)
                                        for row_id in assignment[segment]})
                       for segment in SEGMENTS},
        })
        previous_evaluation_last_slot = fold["test"]["last_slot_inclusive"]

    plan = {
        "schema_version": SCHEMA_VERSION,
        "purge_rule": PURGE_RULE,
        "embargo_rule": EMBARGO_RULE,
        "r5_rule": R5_RULE,
        "status": status,
        "target_id": spec["target_id"],
        "horizon_id": spec["horizon_id"],
        "purge_slots": spec["purge_slots"],
        "embargo_slots": spec["embargo_slots"],
        "preregistration_reference": spec["preregistration_reference"],
        "folds": folds,
        "accounting": {
            "rows_supplied": len(rows),
            "identity_groups": len(groups),
            "folds_planned": len(folds),
            "rows_assigned": sum(f["row_counts"][s] for f in folds for s in SEGMENTS),
            "rows_excluded": len(exclusions),
            "exclusions_by_reason": {code: sum(1 for e in exclusions
                                               if e["reason_code"] == code)
                                     for code in EXCLUSION_CODES},
        },
        "exclusions": sorted(exclusions, key=lambda e: (e["fold_id"], e["row_id"],
                                                        e["reason_code"])),
        "row_evidence_sha256": row_evidence_hash(rows),
        "plan_sha256": None,
    }
    assert_split_plan(plan, by_id, groups)
    plan["plan_sha256"] = plan_hash(plan)
    return plan


def assert_split_plan(plan, rows_by_id, groups):
    """Every gate on a finished plan, in one call. The backstop for a hand-built one."""
    if not isinstance(plan, dict):
        raise SplitRefused(f"plan must be a mapping, got {type(plan).__name__}")
    missing = [field for field in PLAN_FIELDS if field not in plan]
    if missing:
        raise SplitRefused(f"plan does not carry {missing}")
    unknown = [field for field in plan if field not in PLAN_FIELDS]
    if unknown:
        raise SplitRefused(f"plan carries undeclared fields {sorted(unknown)}")
    for name, rule in (("purge_rule", PURGE_RULE), ("embargo_rule", EMBARGO_RULE),
                       ("r5_rule", R5_RULE)):
        if plan[name] != rule:
            raise SplitRefused(f"the {name} on this plan is not the one this module applies")
    if plan["status"] not in ATTAINABLE_STATUSES:
        raise StatusGated(f"a plan may not ship with status {plan['status']!r}. "
                          + _gate_sentence())

    for fold in plan["folds"]:
        ranges = fold["ranges"]
        if not (ranges["train"]["last_slot_inclusive"] < ranges["validation"]["first_slot_inclusive"]
                <= ranges["validation"]["last_slot_inclusive"]
                < ranges["test"]["first_slot_inclusive"]):
            raise SplitRefused(f"fold {fold['fold_id']} is not strictly chronological")
        # Checked before the range test, and deliberately: a row listed in the wrong segment
        # fails the range test first, so behind it this check could never fire — and it is the
        # more dangerous finding, since a row in two segments is trained and evaluated on at once.
        assigned = [row_id for segment in SEGMENTS for row_id in fold["rows"][segment]]
        if len(assigned) != len(set(assigned)):
            raise SplitRefused(
                f"fold {fold['fold_id']} places a row in two segments at once; it would be "
                "trained on and evaluated against simultaneously")
        for segment in SEGMENTS:
            for row_id in fold["rows"][segment]:
                row = rows_by_id[row_id]
                if not (ranges[segment]["first_slot_inclusive"] <= row["t0"]["slot"]
                        <= ranges[segment]["last_slot_inclusive"]):
                    raise SplitRefused(
                        f"row {row_id} sits in {segment} but its t0 is outside that range")
                if row["label_status"] != LABEL_OBSERVED:
                    raise SplitRefused(
                        f"row {row_id} is {row['label_status']!r} and was assigned to {segment}; "
                        "a censored outcome is excluded, never used and never recoded")

        for row_id in fold["rows"][SEGMENT_TRAIN]:
            row = rows_by_id[row_id]
            for segment in EVALUATION_SEGMENTS:
                boundary = ranges[segment]["first_slot_inclusive"]
                if row["label_window_end_slot"] + plan["purge_slots"] >= boundary:
                    raise SplitRefused(
                        f"training row {row_id}'s label window ends at "
                        f"{row['label_window_end_slot']} and reaches the {segment} segment at "
                        f"{boundary} under a purge of {plan['purge_slots']}; the row would be "
                        "labelled by the period it is evaluated against")

        occupied = {}
        for segment in SEGMENTS:
            for row_id in fold["rows"][segment]:
                occupied.setdefault(group_of(groups, row_id), set()).add(segment)
        spanning = sorted(group for group, segments in occupied.items() if len(segments) > 1)
        if spanning:
            raise SplitRefused(
                f"identity group {spanning[0]} appears in more than one segment of fold "
                f"{fold['fold_id']}. Rows connected through an exact shared creator or user must "
                "stay in one segment; splitting one trains a model on an actor's own future")
    assert_no_float(plan)
    assert_no_association_evidence(plan)
    return plan


def row_evidence_hash(rows):
    """A hash of the ROWS a plan was built from, not merely of their identifiers.

    Without it a plan is a list of row ids and a set of ranges, and the corpus underneath could be
    swapped for a different one — different t0s, different label windows, different labels — while
    the plan hash stayed identical. A plan that cannot say which rows it planned is not provenance.
    """
    digest = hashlib.sha256()
    for row in rows:
        digest.update(B10B.canonical_json(row).encode("utf-8"))
    return digest.hexdigest()


def plan_hash(plan):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in plan.items() if k != "plan_sha256"}).encode("utf-8")).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "purge_rule": PURGE_RULE,
        "embargo_rule": EMBARGO_RULE,
        "r5_rule": R5_RULE,
        "label_statuses": list(LABEL_STATUSES),
        "segments": list(SEGMENTS),
        "plan_statuses": list(PLAN_STATUSES),
        "attainable_statuses": list(ATTAINABLE_STATUSES),
        "accepted_cluster_artifact_types": list(ACCEPTED_CLUSTER_ARTIFACT_TYPES),
        "future_cluster_artifact_requirements": list(CLUSTER_ARTIFACT_REQUIREMENTS),
        "exclusion_codes": list(EXCLUSION_CODES),
        "defaults_offered": [],
        "association_evidence_consumed": False,
        "clusters_inferred": False,
        "model_fitted": False,
        "floats_used": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"SplitRefused: {error}", file=sys.stderr)
        sys.exit(2)
