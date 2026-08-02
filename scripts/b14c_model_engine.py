"""B14c — the frozen model mechanics, exact and synthetic-only.

Implements what `research/B14C_MODEL_PREREGISTRATION.json` froze: four candidate families, exact
rational arithmetic throughout, training-only threshold generation, rational-pair comparison by
cross-multiplication, a dedicated missing branch, exact PAVA calibration, deterministic Brier
selection with total tie-breaks, abstention codes A01-A06, and canonical no-float serialization.

**No window is eligible and nothing here may be fitted on real data.** Every entry point that
fits calls `b14c_model_prereg.assert_fit_permitted` unless it is handed a corpus that declares
itself synthetic, and that gate refuses every real window and refuses B11a permanently.

Two properties this module exists to make true rather than to claim:

- **No float anywhere.** Not in a threshold, a leaf, a probability, a metric or an artifact.
  `Fraction` is exact; every serialized rational is a named integer pair. A single float would make
  two identical models hash differently, and the artifact hash is what every compatibility refusal
  rests on.
- **Byte determinism under row permutation.** The corpus is canonically ordered before anything
  reads it, and every search resolves ties by a declared total order. A model that depends on the
  order rows arrived in is a model nobody can reproduce.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# One module graph, through the validator, so every refusal below is catchable as the project base.
PREREG = _load("b14c_model_prereg", "b14c_model_prereg.py")


class ModelEngineRefused(PREREG.ModelPreregRefused):
    """The engine was asked to do something the freeze does not allow."""


class LeakageRefused(ModelEngineRefused):
    """Something reached across a fold boundary."""


SYNTHETIC_CORPUS_MARKER = "synthetic_fixture_only"

FAMILY_CONSTANT = "F1_constant_prior"
FAMILY_STUMP = "F2_single_threshold_stump"
FAMILY_CART = "F3_depth_limited_cart"
FAMILY_BOOSTED = "F4_rational_gradient_boosted_stumps"
FAMILY_ORDER = (FAMILY_CONSTANT, FAMILY_STUMP, FAMILY_CART, FAMILY_BOOSTED)

QUANTISATION_DENOMINATOR = 1000000000000

SEGMENTS = ("fit", "calibration", "validation", "test")

ABSTAIN_VECTOR_UNAVAILABLE = "A01_vector_unavailable"
ABSTAIN_DENOMINATOR_ZERO = "A02_required_denominator_zero"
ABSTAIN_INCOMPATIBLE = "A03_inference_incompatible"
ABSTAIN_OUT_OF_RANGE = "A04_feature_out_of_training_range"
ABSTAIN_UNFITTED_NULL = "A05_unfitted_null_branch"
ABSTAIN_WINDOW_INELIGIBLE = "A06_window_not_eligible"

MISSING = None


# --------------------------------------------------------------------------------------------
# Exact arithmetic and canonical serialization
# --------------------------------------------------------------------------------------------

def rational(numerator, denominator=1):
    """An exact rational. Refuses a float at the door rather than rounding one quietly."""
    for value, role in ((numerator, "numerator"), (denominator, "denominator")):
        if isinstance(value, float):
            raise ModelEngineRefused(
                f"{role} {value!r} is a float. Every quantity here is exact; a float is the "
                "quietest reproducibility failure available")
    if denominator == 0:
        raise ModelEngineRefused("a rational with a zero denominator is not a number")
    return Fraction(numerator, denominator)


def pair(value):
    """A rational as the named integer pair that goes on the wire. Never a decimal."""
    if isinstance(value, float):
        raise ModelEngineRefused(f"{value!r} is a float and may not be serialized")
    value = Fraction(value)
    return {"numerator": value.numerator, "denominator": value.denominator}


def quantise(value, denominator=QUANTISATION_DENOMINATOR):
    """Round half to even against the fixed denominator.

    Boosting compounds exact rationals, so without this the denominators grow without bound and the
    artifact becomes both enormous and slow to compare. Half-to-even is chosen because half-up is
    biased away from zero, and a bias applied every round accumulates in one direction.
    """
    value = Fraction(value)
    scaled = value * denominator
    floor = scaled.numerator // scaled.denominator
    remainder = scaled - floor
    if remainder > Fraction(1, 2):
        floor += 1
    elif remainder == Fraction(1, 2) and floor % 2 != 0:
        floor += 1
    return Fraction(floor, denominator)


def canonical_bytes(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def canonical_sha256(document):
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def assert_no_float(node, path="$"):
    if isinstance(node, float):
        raise ModelEngineRefused(f"{path} is a float ({node!r}); no float may appear anywhere")
    if isinstance(node, dict):
        for key, value in node.items():
            assert_no_float(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            assert_no_float(value, f"{path}[{index}]")


# --------------------------------------------------------------------------------------------
# The corpus
# --------------------------------------------------------------------------------------------

def canonical_rows(rows):
    """Rows in canonical order, never the order they arrived in.

    Sorted by (t0_slot, row_id). Everything downstream reads this and only this, which is what
    makes byte determinism under permutation a property of the design rather than a hope.
    """
    ordered = sorted(rows, key=lambda row: (row["t0_slot"], row["row_id"]))
    identifiers = [row["row_id"] for row in ordered]
    if len(set(identifiers)) != len(identifiers):
        raise ModelEngineRefused("two rows share a row_id; the canonical order is not total")
    return ordered


def assert_synthetic(corpus):
    """The only corpus this engine may fit. Everything else goes through the frozen gate."""
    if corpus.get("provenance") != SYNTHETIC_CORPUS_MARKER:
        # No fallback raise after this call, deliberately. `assert_fit_permitted` raises on every
        # path — there is a test pinning that it contains no `return True`/`return False` — so a
        # second raise here could never execute, and a line that cannot run reads as protection
        # while providing none.
        PREREG.assert_fit_permitted(window_id=corpus.get("window_id"))
    return True


def segment_rows(corpus, segment):
    if segment not in SEGMENTS:
        raise ModelEngineRefused(f"{segment!r} is not one of {SEGMENTS}")
    return [row for row in canonical_rows(corpus["rows"]) if row["segment"] == segment]


def assert_chronology(corpus):
    """fit < calibration < validation < test, strictly, with no touching boundaries.

    Touching is refused for the same reason B14a refuses it: a training segment ending on the slot
    validation begins is not a boundary, it is an overlap that happens to be one slot wide.
    """
    spans = {}
    for segment in SEGMENTS:
        rows = segment_rows(corpus, segment)
        if not rows:
            raise ModelEngineRefused(f"segment {segment!r} is empty; every segment must be used")
        spans[segment] = (rows[0]["t0_slot"], rows[-1]["t0_slot"])
    for earlier, later in zip(SEGMENTS, SEGMENTS[1:]):
        if spans[earlier][1] >= spans[later][0]:
            raise LeakageRefused(
                f"{earlier} ends at slot {spans[earlier][1]} and {later} begins at "
                f"{spans[later][0]}; segments that touch or overlap are not a boundary")
    return spans


def label_of(row):
    if row.get("label_status") != "observed":
        raise ModelEngineRefused(
            f"row {row['row_id']} has label_status {row.get('label_status')!r} and no usable "
            "label. A censored row is excluded, never recoded")
    return bool(row["label_value"])


# --------------------------------------------------------------------------------------------
# Feature access
# --------------------------------------------------------------------------------------------

def feature_value(row, feature, pairs):
    """The exact value of one feature, as a Fraction, or MISSING.

    A rational pair is ONE feature: the numerator alone is not a quantity, so the pair is read
    together and compared by cross-multiplication. A zero denominator is MISSING, never zero — the
    share does not exist, which is a different fact from a share of nothing.
    """
    if feature in pairs:
        numerator = row["features"].get(feature)
        denominator = row["features"].get(pairs[feature])
        if numerator is None or denominator is None or denominator == 0:
            return MISSING
        return rational(numerator, denominator)
    value = row["features"].get(feature)
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return Fraction(int(value))
    return rational(value)


def usable_features(corpus):
    """Feature names a model may split on: every declared field except a pair's denominator half.

    The denominator is not dropped from the data, only from the split menu. It is read as half of
    its pair, and offering it separately would let a model split on a scale factor as if it were a
    quantity.
    """
    pairs = corpus["rational_pairs"]
    denominators = set(pairs.values())
    return tuple(name for name in corpus["feature_order"] if name not in denominators)


# --------------------------------------------------------------------------------------------
# Threshold candidates — training folds only
# --------------------------------------------------------------------------------------------

def feature_matrix(rows, features, pairs):
    """Every feature value, read once.

    The split search visits each (feature, threshold, row) triple, so recomputing a value inside
    the innermost loop makes the whole fit quadratic in work that never changes. Reading each value
    once here is not an optimisation detail: it is what makes a fixture large enough to exercise
    the mechanics affordable to run in a test.
    """
    return {feature: {row["row_id"]: feature_value(row, feature, pairs) for row in rows}
            for feature in features}


def threshold_candidates(rows, feature, pairs, matrix=None):
    """Midpoints between consecutive DISTINCT observed values, exact.

    The quietest leak in tree fitting: candidates derived from all rows let the evaluation fold
    choose where the model is allowed to cut. `rows` must be training rows, and every caller here
    passes the fit segment.
    """
    if matrix is None:
        values = {feature_value(row, feature, pairs) for row in rows}
    else:
        column = matrix[feature]
        values = {column[row["row_id"]] for row in rows}
    values = sorted(values - {MISSING})
    return [(low + high) / 2 for low, high in zip(values, values[1:])]


def training_ranges(rows, features, pairs):
    """The closed interval each feature occupied in training, for the A04 out-of-range rule."""
    ranges = {}
    for feature in features:
        values = sorted({feature_value(row, feature, pairs) for row in rows} - {MISSING})
        ranges[feature] = (values[0], values[-1]) if values else None
    return ranges


def training_null_features(rows, features, pairs):
    """Features that actually took a null in training, so a null branch was fitted for them."""
    return {feature for feature in features
            if any(feature_value(row, feature, pairs) is MISSING for row in rows)}


# --------------------------------------------------------------------------------------------
# Splitting
# --------------------------------------------------------------------------------------------

def partition(rows, feature, threshold, pairs, matrix=None):
    low, high, missing = [], [], []
    column = None if matrix is None else matrix[feature]
    for row in rows:
        value = feature_value(row, feature, pairs) if column is None else column[row["row_id"]]
        if value is MISSING:
            missing.append(row)
        elif value <= threshold:
            low.append(row)
        else:
            high.append(row)
    return low, high, missing


def gini(rows):
    """Exact rational Gini impurity. No float comparison at any split."""
    if not rows:
        return Fraction(0)
    positives = sum(1 for row in rows if label_of(row))
    total = len(rows)
    p = Fraction(positives, total)
    return 2 * p * (1 - p)


def weighted_impurity(parts):
    total = sum(len(part) for part in parts)
    if total == 0:
        return Fraction(0)
    return sum(Fraction(len(part), total) * gini(part) for part in parts)


def best_split(rows, features, pairs, min_samples_leaf, matrix=None):
    """The impurity-minimising split, with ties broken by a declared total order.

    Ties are common with integer features and small leaves, and resolving them by "whichever came
    first" makes the model depend on enumeration order. The order here is: lowest impurity, then
    lowest feature index in the frozen feature order, then smallest threshold. Total, and
    independent of how the rows or the candidates were enumerated.
    """
    best = None
    for index, feature in enumerate(features):
        present, missing = _sorted_column(rows, feature, pairs, matrix)
        if len(present) < 2 * min_samples_leaf:
            continue
        missing_impurity = gini(missing)
        total = len(rows)
        low_positive = 0
        for boundary, threshold in _boundaries(present):
            low_positive += boundary["positives"]
            low_count = boundary["index"]
            high_count = len(present) - low_count
            if low_count < min_samples_leaf or high_count < min_samples_leaf:
                continue
            high_positive = boundary["cumulative_positives"] - low_positive + boundary["remaining"]
            score = (Fraction(low_count, total) * _gini_from_counts(low_positive, low_count)
                     + Fraction(high_count, total) * _gini_from_counts(high_positive, high_count)
                     + Fraction(len(missing), total) * missing_impurity)
            key = (score, index, threshold)
            if best is None or key < best[0]:
                low, high, _m = partition(rows, feature, threshold, pairs, matrix)
                best = (key, feature, threshold, low, high, missing)
    return best


def _sorted_column(rows, feature, pairs, matrix):
    """Rows carrying a value for one feature, sorted by it, plus the rows that carry none.

    Sorting once per feature is what turns the split search from O(thresholds x rows) into one
    sweep. Ties in value are ordered by row_id so the sweep itself cannot depend on arrival order.
    """
    column = None if matrix is None else matrix[feature]
    present, missing = [], []
    for row in rows:
        value = feature_value(row, feature, pairs) if column is None else column[row["row_id"]]
        (missing if value is MISSING else present).append((value, row["row_id"], row))
    present.sort(key=lambda item: (item[0], item[1]))
    return present, [item[2] for item in missing]


def _boundaries(present):
    """Each midpoint between consecutive DISTINCT values, with the counts to its left.

    Yields the same candidate thresholds as `threshold_candidates`, in the same increasing order,
    so the tie-break "smallest threshold" resolves identically to the naive search.
    """
    total_positives = sum(1 for _value, _key, row in present if label_of(row))
    index = 0
    positives_since_last = 0
    for position in range(len(present) - 1):
        _value, _key, row = present[position]
        if label_of(row):
            positives_since_last += 1
        index += 1
        if present[position][0] != present[position + 1][0]:
            threshold = (present[position][0] + present[position + 1][0]) / 2
            yield ({"index": index, "positives": positives_since_last,
                    "cumulative_positives": total_positives, "remaining": 0}, threshold)
            positives_since_last = 0


def _gini_from_counts(positives, total):
    if total == 0:
        return Fraction(0)
    p = Fraction(positives, total)
    return 2 * p * (1 - p)


def leaf_value(rows):
    """The exact rate in this leaf. Undefined over no rows rather than zero."""
    if not rows:
        return None
    return Fraction(sum(1 for row in rows if label_of(row)), len(rows))


def grow(rows, features, pairs, depth, max_depth, min_samples_leaf, matrix=None):
    if depth >= max_depth or len(rows) < 2 * min_samples_leaf:
        return {"kind": "leaf", "value": leaf_value(rows), "support": len(rows)}
    found = best_split(rows, features, pairs, min_samples_leaf, matrix)
    if found is None:
        return {"kind": "leaf", "value": leaf_value(rows), "support": len(rows)}
    _key, feature, threshold, low, high, missing = found
    # The missing branch is FITTED, not defaulted: it goes to whichever side its own rows resemble.
    # A null routed by a hardcoded default is an imputation wearing a different name.
    missing_direction = None
    if missing:
        missing_direction = "low" if abs(leaf_value(missing) - (leaf_value(low) or Fraction(0))) <= \
            abs(leaf_value(missing) - (leaf_value(high) or Fraction(0))) else "high"
    return {
        "kind": "node", "feature": feature, "threshold": threshold,
        "missing_direction": missing_direction, "support": len(rows),
        "low": grow(low, features, pairs, depth + 1, max_depth, min_samples_leaf, matrix),
        "high": grow(high, features, pairs, depth + 1, max_depth, min_samples_leaf, matrix),
    }


def tree_features(node, seen=None):
    seen = set() if seen is None else seen
    if node["kind"] == "node":
        seen.add(node["feature"])
        tree_features(node["low"], seen)
        tree_features(node["high"], seen)
    return seen


def tree_predict(node, row, pairs):
    """A prediction, or an abstention code. Never a guess dressed as a prediction."""
    while node["kind"] == "node":
        value = feature_value(row, node["feature"], pairs)
        if value is MISSING:
            if node["missing_direction"] is None:
                return None, ABSTAIN_UNFITTED_NULL
            node = node[node["missing_direction"]]
        else:
            node = node["low"] if value <= node["threshold"] else node["high"]
    if node["value"] is None:
        return None, ABSTAIN_INCOMPATIBLE
    return node["value"], None


def serialize_tree(node):
    if node["kind"] == "leaf":
        return {"kind": "leaf", "support": node["support"],
                "value": None if node["value"] is None else pair(node["value"])}
    return {"kind": "node", "feature": node["feature"], "threshold": pair(node["threshold"]),
            "missing_direction": node["missing_direction"], "support": node["support"],
            "low": serialize_tree(node["low"]), "high": serialize_tree(node["high"])}


# --------------------------------------------------------------------------------------------
# The four families
# --------------------------------------------------------------------------------------------

def fit_constant(rows, features, pairs, hyperparameters, matrix=None):
    value = leaf_value(rows)
    return {"family": FAMILY_CONSTANT, "hyperparameters": {}, "value": value,
            "parameter_count": 1}


def fit_stump(rows, features, pairs, hyperparameters, matrix=None):
    found = best_split(rows, features, pairs, 1, matrix)
    if found is None:
        raise ModelEngineRefused(
            "no admissible split exists, so a stump cannot be fitted. Refused rather than silently "
            "degraded to a constant, which would report one family's number under another's name")
    tree = grow(rows, features, pairs, 0, 1, 1, matrix)
    return {"family": FAMILY_STUMP, "hyperparameters": {}, "tree": tree, "parameter_count": 3}


def fit_cart(rows, features, pairs, hyperparameters, matrix=None):
    tree = grow(rows, features, pairs, 0, hyperparameters["max_depth"],
                hyperparameters["min_samples_leaf"], matrix)
    return {"family": FAMILY_CART, "hyperparameters": dict(hyperparameters), "tree": tree,
            "parameter_count": _count_parameters(tree)}


def _count_parameters(node):
    if node["kind"] == "leaf":
        return 1
    return 3 + _count_parameters(node["low"]) + _count_parameters(node["high"])


def fit_boosted(rows, features, pairs, hyperparameters, matrix=None):
    """Additive stumps over exact rational residuals, quantised every round."""
    shrinkage = rational(hyperparameters["shrinkage_numerator"],
                         hyperparameters["shrinkage_denominator"])
    base = quantise(leaf_value(rows))
    current = {row["row_id"]: base for row in rows}
    columns = {feature: _sorted_column(rows, feature, pairs, matrix) for feature in features}
    stumps = []
    for _round in range(hyperparameters["rounds"]):
        residuals = {row["row_id"]: Fraction(int(label_of(row))) - current[row["row_id"]]
                     for row in rows}
        stump = _residual_stump(rows, features, pairs, residuals,
                                hyperparameters["min_samples_leaf"], matrix, columns)
        if stump is None:
            break
        stumps.append(stump)
        for row in rows:
            increment = _residual_stump_value(stump, row, pairs, matrix)
            current[row["row_id"]] = quantise(current[row["row_id"]] + shrinkage * increment)
    return {"family": FAMILY_BOOSTED, "hyperparameters": dict(hyperparameters), "base": base,
            "stumps": stumps, "shrinkage": shrinkage, "parameter_count": 1 + 3 * len(stumps)}


def _residual_stump(rows, features, pairs, residuals, min_samples_leaf, matrix=None,
                    columns=None):
    """One stump minimising squared residual error, exactly, ties broken by the same total order.

    `columns` is the sorted-column cache. Boosting searches the same rows every round and only the
    residuals change, so re-sorting each column per round is the same work repeated a hundred
    times over data that never moves.
    """
    best = None
    for index, feature in enumerate(features):
        present, missing = (columns[feature] if columns is not None
                            else _sorted_column(rows, feature, pairs, matrix))
        if len(present) < 2 * min_samples_leaf:
            continue
        # Residuals are `label - quantised score`, so every one is an exact multiple of 1/Q and
        # scales to an INTEGER. Accumulating them as Fractions instead means squaring values with
        # a 10^12 denominator and gcd-reducing a 10^24 numerator on every row of every round; the
        # arithmetic is identical either way, and the integer form is the one that finishes.
        scaled = _scaled_residuals(residuals, rows)
        missing_sum = sum(scaled[row["row_id"]] for row in missing)
        missing_square = sum(scaled[row["row_id"]] ** 2 for row in missing)
        missing_error = (missing_square - Fraction(missing_sum ** 2, len(missing))
                         if missing else Fraction(0))
        values = [scaled[row["row_id"]] for _value, _key, row in present]
        total_sum = sum(values)
        total_square = sum(value * value for value in values)
        low_sum = 0
        low_square = 0
        for position in range(len(present) - 1):
            low_sum += values[position]
            low_square += values[position] * values[position]
            low_count = position + 1
            high_count = len(present) - low_count
            if present[position][0] == present[position + 1][0]:
                continue
            if low_count < min_samples_leaf or high_count < min_samples_leaf:
                continue
            threshold = (present[position][0] + present[position + 1][0]) / 2
            # Sum of squared deviations without materialising either side: the identity
            # sum((r - mean)^2) = sum(r^2) - sum(r)^2 / n. Scaled by Q^2 uniformly across every
            # candidate, so comparisons and the tie-break order are unchanged.
            high_sum = total_sum - low_sum
            error = (total_square - Fraction(low_sum * low_sum, low_count)
                     - Fraction(high_sum * high_sum, high_count) + missing_error)
            key = (error, index, threshold)
            if best is None or key < best[0]:
                best = (key, {"feature": feature, "threshold": threshold,
                              "low": quantise(Fraction(low_sum,
                                                       low_count * QUANTISATION_DENOMINATOR)),
                              "high": quantise(Fraction(high_sum,
                                                        high_count * QUANTISATION_DENOMINATOR)),
                              "missing": None if not missing else quantise(
                                  Fraction(missing_sum,
                                           len(missing) * QUANTISATION_DENOMINATOR))})
    return None if best is None else best[1]


def _scaled_residuals(residuals, rows):
    """Residuals as exact integers over the fixed denominator. Refuses anything that is not."""
    scaled = {}
    for row in rows:
        value = Fraction(residuals[row["row_id"]]) * QUANTISATION_DENOMINATOR
        if value.denominator != 1:
            raise ModelEngineRefused(
                f"residual for {row['row_id']} is not an exact multiple of 1/"
                f"{QUANTISATION_DENOMINATOR}; the boosting invariant that every score is "
                "quantised has been broken somewhere upstream")
        scaled[row["row_id"]] = value.numerator
    return scaled


def _mean(residuals, rows):
    if not rows:
        return Fraction(0)
    return sum(residuals[row["row_id"]] for row in rows) / len(rows)


def _sse(residuals, rows, mean):
    return sum((residuals[row["row_id"]] - mean) ** 2 for row in rows)


def _residual_stump_value(stump, row, pairs, matrix=None):
    if matrix is None:
        value = feature_value(row, stump["feature"], pairs)
    else:
        value = matrix[stump["feature"]][row["row_id"]]
    if value is MISSING:
        return Fraction(0) if stump["missing"] is None else stump["missing"]
    return stump["low"] if value <= stump["threshold"] else stump["high"]


def boosted_predict(model, row, pairs):
    total = model["base"]
    for stump in model["stumps"]:
        value = feature_value(row, stump["feature"], pairs)
        if value is MISSING and stump["missing"] is None:
            return None, ABSTAIN_UNFITTED_NULL
        total = quantise(total + model["shrinkage"] * _residual_stump_value(stump, row, pairs))
    # A boosted score is an additive sum and can leave [0, 1]; clamping is exact and declared,
    # not a calibration. The calibrator is a separate, fold-restricted step.
    return min(max(total, Fraction(0)), Fraction(1)), None


FAMILY_FITTERS = {FAMILY_CONSTANT: fit_constant, FAMILY_STUMP: fit_stump,
                  FAMILY_CART: fit_cart, FAMILY_BOOSTED: fit_boosted}


def predict_raw(model, row, pairs):
    if model["family"] == FAMILY_CONSTANT:
        return model["value"], None
    if model["family"] == FAMILY_BOOSTED:
        return boosted_predict(model, row, pairs)
    return tree_predict(model["tree"], row, pairs)


def model_features(model):
    if model["family"] == FAMILY_CONSTANT:
        return set()
    if model["family"] == FAMILY_BOOSTED:
        return {stump["feature"] for stump in model["stumps"]}
    return tree_features(model["tree"])


# --------------------------------------------------------------------------------------------
# Calibration — exact PAVA, on the calibration segment only
# --------------------------------------------------------------------------------------------

def fit_calibration(model, rows, pairs, min_bin):
    """Pool-adjacent-violators over exact rationals. Monotone by construction.

    Fitted on the calibration segment and nowhere else. A probability calibrated on the evaluation
    fold is calibrated against the answer, and the mistake is invisible in the output.
    """
    observations = []
    for row in rows:
        score, code = predict_raw(model, row, pairs)
        if code is None:
            observations.append((score, int(label_of(row))))
    observations.sort(key=lambda item: item[0])
    blocks = [{"low": score, "high": score, "sum": label, "count": 1}
              for score, label in observations]
    while True:
        for index in range(len(blocks) - 1):
            left, right = blocks[index], blocks[index + 1]
            if Fraction(left["sum"], left["count"]) > Fraction(right["sum"], right["count"]):
                blocks[index:index + 2] = [{"low": left["low"], "high": right["high"],
                                            "sum": left["sum"] + right["sum"],
                                            "count": left["count"] + right["count"]}]
                break
        else:
            break
    # Blocks below the declared minimum are merged forward rather than published: a bin of three
    # rows reports a rate of 0, 1/3, 2/3 or 1, and none of those is an estimate of anything.
    merged = []
    for block in blocks:
        if merged and merged[-1]["count"] < min_bin:
            previous = merged.pop()
            block = {"low": previous["low"], "high": block["high"],
                     "sum": previous["sum"] + block["sum"],
                     "count": previous["count"] + block["count"]}
        merged.append(block)
    while len(merged) > 1 and merged[-1]["count"] < min_bin:
        last = merged.pop()
        previous = merged.pop()
        merged.append({"low": previous["low"], "high": last["high"],
                       "sum": previous["sum"] + last["sum"],
                       "count": previous["count"] + last["count"]})
    return [{"low": block["low"], "high": block["high"],
             "value": Fraction(block["sum"], block["count"]), "count": block["count"]}
            for block in merged]


def apply_calibration(calibration, score):
    for block in calibration:
        if score <= block["high"]:
            return block["value"]
    return calibration[-1]["value"]


# --------------------------------------------------------------------------------------------
# Prediction with abstention
# --------------------------------------------------------------------------------------------

def predict(fitted, row, pairs):
    """A calibrated probability, or an abstention code. Never both, never neither."""
    if row.get("vector_available") is False:
        return None, ABSTAIN_VECTOR_UNAVAILABLE
    used = fitted["used_features"]
    for feature in sorted(used):
        value = feature_value(row, feature, pairs)
        if value is MISSING:
            if feature in pairs and row["features"].get(pairs[feature]) == 0:
                return None, ABSTAIN_DENOMINATOR_ZERO
            if feature not in fitted["training_null_features"]:
                return None, ABSTAIN_UNFITTED_NULL
            continue
        span = fitted["training_ranges"].get(feature)
        if span is None or value < span[0] or value > span[1]:
            return None, ABSTAIN_OUT_OF_RANGE
    score, code = predict_raw(fitted["model"], row, pairs)
    if code is not None:
        return None, code
    return apply_calibration(fitted["calibration"], score), None


# --------------------------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------------------------

def brier(fitted, rows, pairs):
    """Exact Brier, summed as ONE rational over a common denominator.

    Returns `(score, evaluated)`. Undefined over no evaluated rows rather than zero, because a
    configuration that abstained on everything has not scored perfectly.
    """
    total = Fraction(0)
    evaluated = 0
    for row in rows:
        probability, code = predict(fitted, row, pairs)
        if code is not None:
            continue
        evaluated += 1
        total += (probability - Fraction(int(label_of(row)))) ** 2
    if evaluated == 0:
        return None, 0
    return total / evaluated, evaluated


def grid(document):
    """Every configuration, in the frozen enumeration order. Order is part of tie-break 4."""
    configurations = []
    for family in document["candidate_families"]:
        enumeration = family.get("grid_enumeration")
        if enumeration is None:
            if family["id"] == FAMILY_CART:
                enumeration = [{"max_depth": depth, "min_samples_leaf": leaf}
                               for depth in family["grid"]["max_depth"]
                               for leaf in family["grid"]["min_samples_leaf"]]
            else:
                enumeration = [{}]
        for index, hyperparameters in enumerate(enumeration):
            configurations.append({"family": family["id"], "family_index": family["index"],
                                   "grid_index": index, "hyperparameters": hyperparameters})
    return configurations


def fit_one(corpus, configuration):
    """Fit on the fit segment, calibrate on the calibration segment. Nothing else is read."""
    assert_synthetic(corpus)
    assert_chronology(corpus)
    pairs = corpus["rational_pairs"]
    features = usable_features(corpus)
    fit_segment = segment_rows(corpus, "fit")
    calibration_segment = segment_rows(corpus, "calibration")
    matrix = feature_matrix(fit_segment, features, pairs)
    model = FAMILY_FITTERS[configuration["family"]](
        fit_segment, features, pairs, configuration["hyperparameters"], matrix)
    used = model_features(model)
    fitted = {
        "configuration": configuration, "model": model, "used_features": used,
        "training_ranges": training_ranges(fit_segment, used, pairs),
        "training_null_features": training_null_features(fit_segment, used, pairs),
        "calibration": None,
    }
    fitted["calibration"] = fit_calibration(model, calibration_segment, pairs,
                                            corpus["min_calibration_bin"])
    return fitted


def select(corpus, document=None):
    """Fit every configuration, score on validation, apply the frozen tie-breaks.

    The test segment is not read here and is not reachable from here.
    """
    document = PREREG.read_preregistration() if document is None else document
    PREREG.verify_preregistration(document)
    pairs = corpus["rational_pairs"]
    validation = segment_rows(corpus, "validation")
    scored = []
    for configuration in grid(document):
        fitted = fit_one(corpus, configuration)
        score, evaluated = brier(fitted, validation, pairs)
        if score is None:
            continue
        scored.append({
            "configuration": configuration, "fitted": fitted, "brier": score,
            "evaluated": evaluated,
            "parameter_count": fitted["model"]["parameter_count"],
        })
    if not scored:
        raise ModelEngineRefused(
            "no configuration produced a validation score; there is nothing to select between")
    # The frozen tie-break order, as one total key: lower Brier, fewer parameters, lower family
    # index, lower grid index. Nothing is resolved at random or by enumeration accident.
    scored.sort(key=lambda entry: (entry["brier"], entry["parameter_count"],
                                   entry["configuration"]["family_index"],
                                   entry["configuration"]["grid_index"]))
    return {"selected": scored[0], "ranking": scored}


def score_test_once(corpus, selection, receipt=None):
    """The single permitted read of the test segment.

    `receipt` is a mutable set the caller owns. A second call with the same receipt is refused: the
    freeze says the test fold is touched once, and a rule enforced only by everyone remembering it
    is not enforced.
    """
    receipt = set() if receipt is None else receipt
    key = canonical_sha256(serialize_artifact(corpus, selection["selected"]))
    if key in receipt:
        raise LeakageRefused(
            "the test segment has already been scored for this artifact. It is touched once, with "
            "one configuration; a second look is selection wearing the word evaluation")
    receipt.add(key)
    pairs = corpus["rational_pairs"]
    rows = segment_rows(corpus, "test")
    fitted = selection["selected"]["fitted"]
    score, evaluated = brier(fitted, rows, pairs)
    abstentions = {}
    for row in rows:
        _probability, code = predict(fitted, row, pairs)
        if code is not None:
            abstentions[code] = abstentions.get(code, 0) + 1
    return {"brier": None if score is None else pair(score), "evaluated": evaluated,
            "rows": len(rows), "abstentions": dict(sorted(abstentions.items()))}


# --------------------------------------------------------------------------------------------
# The artifact
# --------------------------------------------------------------------------------------------

def serialize_model(model):
    if model["family"] == FAMILY_CONSTANT:
        return {"family": model["family"], "value": pair(model["value"])}
    if model["family"] == FAMILY_BOOSTED:
        return {"family": model["family"], "base": pair(model["base"]),
                "shrinkage": pair(model["shrinkage"]),
                "stumps": [{"feature": stump["feature"], "threshold": pair(stump["threshold"]),
                            "low": pair(stump["low"]), "high": pair(stump["high"]),
                            "missing": None if stump["missing"] is None else pair(stump["missing"])}
                           for stump in model["stumps"]]}
    return {"family": model["family"], "tree": serialize_tree(model["tree"])}


def serialize_artifact(corpus, entry):
    """Canonical, exact, and hashable. Everything a later reader needs to refuse a mismatch."""
    fitted = entry["fitted"]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_canonical_sha256": PREREG.PREREGISTRATION_CANONICAL_SHA256,
        "feature_order_sha256": hashlib.sha256(
            "\n".join(corpus["feature_order"]).encode()).hexdigest(),
        "feature_count": len(corpus["feature_order"]),
        "window_id": corpus["window_id"],
        "provenance": corpus["provenance"],
        "eligible_for_b11a": False,
        "performance_status": "not_evaluated",
        "configuration": {"family": entry["configuration"]["family"],
                          "family_index": entry["configuration"]["family_index"],
                          "grid_index": entry["configuration"]["grid_index"],
                          "hyperparameters": dict(sorted(
                              entry["configuration"]["hyperparameters"].items()))},
        "model": serialize_model(fitted["model"]),
        "parameter_count": fitted["model"]["parameter_count"],
        "used_features": sorted(fitted["used_features"]),
        "training_ranges": {name: None if span is None else
                            {"low": pair(span[0]), "high": pair(span[1])}
                            for name, span in sorted(fitted["training_ranges"].items())},
        "training_null_features": sorted(fitted["training_null_features"]),
        "calibration": [{"low": pair(block["low"]), "high": pair(block["high"]),
                         "value": pair(block["value"]), "count": block["count"]}
                        for block in fitted["calibration"]],
        "calibration_fitted_on": "calibration",
        "row_evidence_sha256": corpus["row_evidence_sha256"],
    }
    assert_no_float(artifact)
    artifact["artifact_sha256"] = canonical_sha256(artifact)
    return artifact


def refuse_cross_window_comparison(model_window, baseline_window):
    """Two figures from two windows do not subtract into a statement about a model."""
    if model_window != baseline_window:
        raise ModelEngineRefused(
            f"a model scored on {model_window!r} may not be compared against a baseline scored on "
            f"{baseline_window!r}. That subtraction measures the difference between two windows "
            "and attributes it to the model")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true", help="report what this engine binds to")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("nothing to do; --contract reports the binding. Fitting requires a corpus, "
                     "and no real window is eligible")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "families": list(FAMILY_ORDER),
        "quantisation_denominator": QUANTISATION_DENOMINATOR,
        "segments": list(SEGMENTS),
        "abstention_codes": [ABSTAIN_VECTOR_UNAVAILABLE, ABSTAIN_DENOMINATOR_ZERO,
                             ABSTAIN_INCOMPATIBLE, ABSTAIN_OUT_OF_RANGE, ABSTAIN_UNFITTED_NULL,
                             ABSTAIN_WINDOW_INELIGIBLE],
        "preregistration_canonical_sha256": PREREG.PREREGISTRATION_CANONICAL_SHA256,
        "fitting_permitted_on_real_windows": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PREREG.ModelPreregRefused as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
