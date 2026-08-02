"""B14c — synthetic fixtures and the end-to-end gate.

Every row here is invented by this file. There is no chain, no B11a composition, no outcome and no
burned distribution anywhere in it: the labels are a declared deterministic function of the
features, chosen so the mechanics can be exercised, not so any family looks good.

`python scripts/b14c_model_fixtures.py --gate` runs the whole pipeline — fit every configuration,
calibrate, select on validation, score the test segment once, serialize and hash — and then checks
the properties that matter:

- **byte determinism under row permutation**: the artifact hashes identically when the rows arrive
  in a different order;
- **no float anywhere**, in the artifact or the report;
- every refusal fires: floats, leakage, a second look at the test fold, cross-window comparison,
  and fitting while no real window is eligible.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENGINE = _load("b14c_model_engine", "b14c_model_engine.py")
PREREG = ENGINE.PREREG

# A small, entirely invented feature space. Two plain integers, one boolean, one rational pair and
# one optional field governed by an availability flag — enough to exercise every mechanic the
# freeze declares, and nothing resembling a real cohort.
FEATURE_ORDER = ("synthetic_count_a", "synthetic_count_b", "synthetic_flag",
                 "synthetic_share_numerator", "synthetic_share_denominator",
                 "synthetic_optional_available", "synthetic_optional_units")
RATIONAL_PAIRS = {"synthetic_share_numerator": "synthetic_share_denominator"}

# Sized so the mechanics are actually exercised rather than merely executed. The first version had
# 240 fit rows and 120 calibration rows, and EVERY configuration scored an identical Brier — with
# min_calibration_bin at 64, PAVA merged 120 rows into one block, so every model was flattened to
# the base rate and the whole ranking was the same number fifteen times. A fixture that cannot tell
# the families apart cannot show that selection works. The fit segment also clears 2*512, so the
# largest min_samples_leaf in the frozen grid is a real constraint rather than an impossible one.
SEGMENT_PLAN = (("fit", 0, 1100), ("calibration", 1150, 1750), ("validation", 1800, 2200),
                ("test", 2250, 2650))


def _deterministic(index, modulus):
    """A reproducible pseudo-value with no RNG.

    Not `random`: a seeded RNG still makes the fixture depend on an implementation detail of the
    standard library, and two Python versions could disagree. Integer arithmetic cannot.
    """
    return (index * 2654435761) % modulus


def build_corpus(size_per_segment=None):
    """The synthetic corpus. Labels are a declared function of the features, stated in the open."""
    rows = []
    row_index = 0
    for segment, start, end in SEGMENT_PLAN:
        # Segments are separated by a gap so chronology is strict and no boundary touches.
        for offset in range(end - start):
            row_index += 1
            slot = (start + offset) * 10
            count_a = _deterministic(row_index, 97)
            count_b = _deterministic(row_index + 7, 53)
            flag = _deterministic(row_index, 5) == 0
            numerator = _deterministic(row_index + 3, 41)
            denominator = 41
            available = _deterministic(row_index, 11) != 0
            optional = _deterministic(row_index + 11, 29) if available else None
            # The declared label rule. Deliberately learnable and deliberately noisy: a rule the
            # families can partly capture exercises selection, and a rule they capture perfectly
            # would make every configuration tie and hide the tie-breaks.
            label = (count_a > 48) != (count_b > 40 and flag)
            rows.append({
                "row_id": f"synthetic-{row_index:05d}",
                "t0_slot": slot,
                "segment": segment,
                "label_status": "observed",
                "label_value": bool(label),
                "vector_available": True,
                "features": {
                    "synthetic_count_a": count_a,
                    "synthetic_count_b": count_b,
                    "synthetic_flag": flag,
                    "synthetic_share_numerator": numerator,
                    "synthetic_share_denominator": denominator,
                    "synthetic_optional_available": available,
                    "synthetic_optional_units": optional,
                },
            })
    rows.extend(_abstention_rows(rows))
    corpus = {
        "window_id": "synthetic-b14c-fixture",
        "provenance": ENGINE.SYNTHETIC_CORPUS_MARKER,
        "feature_order": list(FEATURE_ORDER),
        "rational_pairs": dict(RATIONAL_PAIRS),
        "min_calibration_bin": 64,
        "rows": rows,
    }
    corpus["row_evidence_sha256"] = row_evidence(rows)
    return corpus


def _abstention_rows(rows):
    """Four test rows, each engineered to trigger exactly one abstention code.

    Without these the gate would report zero abstentions and prove nothing about A01, A02, A04 or
    A05 — the codes would exist, be serialized, and never once fire.
    """
    last = max(row["t0_slot"] for row in rows)
    base = {"segment": "test", "label_status": "observed", "label_value": True,
            "vector_available": True}
    template = {"synthetic_count_a": 10, "synthetic_count_b": 10, "synthetic_flag": False,
                "synthetic_share_numerator": 3, "synthetic_share_denominator": 41,
                "synthetic_optional_available": True, "synthetic_optional_units": 4}
    return [
        # A01 — the vector does not exist for this subject at all.
        dict(base, row_id="synthetic-abstain-a01", t0_slot=last + 10, vector_available=False,
             features=dict(template)),
        # A02 — the share's denominator is zero, so the share does not exist. Not zero: absent.
        dict(base, row_id="synthetic-abstain-a02", t0_slot=last + 20,
             features=dict(template, synthetic_share_denominator=0)),
        # A04 — a value beyond anything the training folds contained, so any leaf reaching it is
        # extrapolating from support that never existed.
        dict(base, row_id="synthetic-abstain-a04", t0_slot=last + 30,
             features=dict(template, synthetic_count_a=10 ** 6)),
        # A05 — a null in a feature whose training rows contained none, so no branch was fitted.
        dict(base, row_id="synthetic-abstain-a05", t0_slot=last + 40,
             features=dict(template, synthetic_count_b=None)),
    ]


def row_evidence(rows):
    """Hashes the ROWS, not their identifiers: a corpus that cannot say which rows is not evidence."""
    canonical = json.dumps(ENGINE.canonical_rows(rows), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def permuted(corpus):
    """The same corpus with the rows in a different order. Canonical ordering must absorb this."""
    rows = list(corpus["rows"])
    rows = rows[::-1][: len(rows) // 2] + rows[: len(rows) // 2][::-1] + rows[len(rows) // 2 * 2:]
    return dict(corpus, rows=rows)


# --------------------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------------------

def check_determinism(corpus):
    findings = []
    first = ENGINE.select(corpus)
    second = ENGINE.select(permuted(corpus))
    first_artifact = ENGINE.serialize_artifact(corpus, first["selected"])
    second_artifact = ENGINE.serialize_artifact(permuted(corpus), second["selected"])
    if first_artifact["artifact_sha256"] != second_artifact["artifact_sha256"]:
        findings.append(
            "the artifact hash changes when the rows are permuted; the model depends on the order "
            "they arrived in and nobody can reproduce it")
    if first["selected"]["configuration"] != second["selected"]["configuration"]:
        findings.append("a different configuration is selected under permutation")
    if row_evidence(corpus["rows"]) != row_evidence(permuted(corpus)["rows"]):
        findings.append("row evidence depends on arrival order")
    return findings, first, first_artifact


def check_refusals(corpus):
    """Every refusal the brief names must actually fire."""
    findings = []

    def expect(label, exception, thunk):
        try:
            thunk()
        except exception:
            return
        except Exception as error:                                        # noqa: BLE001
            findings.append(f"{label}: raised {type(error).__name__}, not {exception.__name__}")
            return
        findings.append(f"{label}: did NOT refuse")

    expect("a float rational", ENGINE.ModelEngineRefused,
           lambda: ENGINE.rational(0.5))
    expect("a float in an artifact", ENGINE.ModelEngineRefused,
           lambda: ENGINE.assert_no_float({"leaf": {"value": 0.5}}))
    expect("a zero denominator", ENGINE.ModelEngineRefused,
           lambda: ENGINE.rational(1, 0))
    expect("touching segments", ENGINE.LeakageRefused,
           lambda: ENGINE.assert_chronology(_touching(corpus)))
    expect("fitting a real window", PREREG.FitRefused,
           lambda: ENGINE.assert_synthetic({"window_id": "some-real-window"}))
    expect("fitting B11a", PREREG.FitRefused,
           lambda: ENGINE.assert_synthetic({"window_id": "b11a-fresh-cohort-2026-08-02"}))
    expect("a cross-window comparison", ENGINE.ModelEngineRefused,
           lambda: ENGINE.refuse_cross_window_comparison("w-model", "b11a"))
    expect("a censored label read as a value", ENGINE.ModelEngineRefused,
           lambda: ENGINE.label_of({"row_id": "x", "label_status": "right_censored"}))
    return findings


def check_abstentions_are_reachable(corpus, selection):
    """Every abstention code must be shown to FIRE, not merely to be spelled correctly.

    A01, A04 and A05 fire against whichever model wins, because they do not depend on which
    features it uses. A02 does: the freeze scopes it to "a denominator required by a split on the
    selected model's path", so a model that never splits on the share can never raise it. That is
    correct behaviour and it is exactly why it needs its own check — otherwise the code sits in the
    vocabulary, gets serialized, and never once runs.
    """
    findings = []
    pairs = corpus["rational_pairs"]
    fitted = selection["selected"]["fitted"]
    rows = {row["row_id"]: row for row in ENGINE.segment_rows(corpus, "test")}
    for code, row_id in ((ENGINE.ABSTAIN_VECTOR_UNAVAILABLE, "synthetic-abstain-a01"),
                         (ENGINE.ABSTAIN_OUT_OF_RANGE, "synthetic-abstain-a04"),
                         (ENGINE.ABSTAIN_UNFITTED_NULL, "synthetic-abstain-a05")):
        _probability, raised = ENGINE.predict(fitted, rows[row_id], pairs)
        if raised != code:
            findings.append(f"{row_id} raised {raised!r}, expected {code}")

    # A02, against a model forced to use the share. Built here rather than hoped for.
    share_model = dict(fitted, used_features={"synthetic_share_numerator"},
                       training_ranges={"synthetic_share_numerator":
                                        (Fraction(0), Fraction(40, 41))},
                       training_null_features=set())
    _probability, raised = ENGINE.predict(share_model, rows["synthetic-abstain-a02"], pairs)
    if raised != ENGINE.ABSTAIN_DENOMINATOR_ZERO:
        findings.append(f"a zero share denominator raised {raised!r}, expected "
                        f"{ENGINE.ABSTAIN_DENOMINATOR_ZERO}")

    # A06 is the window gate, which is not a per-row condition: it refuses before any row is read.
    try:
        ENGINE.assert_synthetic({"window_id": "any-real-window"})
        findings.append("a real window was accepted for fitting")
    except PREREG.FitRefused:
        pass
    return findings


def _touching(corpus):
    """The same corpus with the validation segment starting where fit ends."""
    rows = [dict(row) for row in corpus["rows"]]
    fit_last = max(row["t0_slot"] for row in rows if row["segment"] == "fit")
    for row in rows:
        if row["segment"] == "calibration":
            row["t0_slot"] = fit_last
    return dict(corpus, rows=rows)


def check_test_fold_touched_once(corpus, selection):
    findings = []
    receipt = set()
    result = ENGINE.score_test_once(corpus, selection, receipt)
    try:
        ENGINE.score_test_once(corpus, selection, receipt)
    except ENGINE.LeakageRefused:
        return findings, result
    findings.append("the test segment was scored twice without refusal")
    return findings, result


def gate(corpus=None):
    corpus = build_corpus() if corpus is None else corpus
    findings = []
    determinism, selection, artifact = check_determinism(corpus)
    findings += determinism
    findings += check_refusals(corpus)
    once, test_result = check_test_fold_touched_once(corpus, selection)
    findings += once
    findings += check_abstentions_are_reachable(corpus, selection)

    ENGINE.assert_no_float(artifact)
    ENGINE.assert_no_float(test_result)

    ranking = [{"family": entry["configuration"]["family"],
                "grid_index": entry["configuration"]["grid_index"],
                "parameter_count": entry["parameter_count"],
                "validation_brier": ENGINE.pair(entry["brier"]),
                "validation_evaluated": entry["evaluated"]}
               for entry in selection["ranking"]]
    if len(ranking) != 15:
        findings.append(f"{len(ranking)} configurations scored, the frozen grid declares 15")

    report = {
        "schema_version": ENGINE.SCHEMA_VERSION,
        "corpus": {"window_id": corpus["window_id"], "provenance": corpus["provenance"],
                   "rows": len(corpus["rows"]),
                   "row_evidence_sha256": corpus["row_evidence_sha256"]},
        "configurations_scored": len(ranking),
        "ranking": ranking,
        "selected": {"family": selection["selected"]["configuration"]["family"],
                     "grid_index": selection["selected"]["configuration"]["grid_index"],
                     "hyperparameters": selection["selected"]["configuration"]["hyperparameters"]},
        "artifact_sha256": artifact["artifact_sha256"],
        "deterministic_under_permutation": not determinism,
        "test_segment": test_result,
        "abstention_codes_shown_to_fire": [ENGINE.ABSTAIN_VECTOR_UNAVAILABLE,
                                           ENGINE.ABSTAIN_DENOMINATOR_ZERO,
                                           ENGINE.ABSTAIN_OUT_OF_RANGE,
                                           ENGINE.ABSTAIN_UNFITTED_NULL,
                                           ENGINE.ABSTAIN_WINDOW_INELIGIBLE],
        "calibration_bins": len(selection["selected"]["fitted"]["calibration"]),
        "eligible_for_b11a": False,
        "performance_status": "not_evaluated",
        "real_window_fitting_permitted": False,
        "findings": findings,
        "passed": not findings,
    }
    ENGINE.assert_no_float(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gate", action="store_true", help="exit non-zero on any finding")
    args = parser.parse_args(argv)
    report = gate()
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.gate and not report["passed"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
