#!/usr/bin/env python3
"""B10c corpus — t0 identities, and the label materialization run over all 1,136 curves.

Offline, read-only, no network. Builds a reproducible derived table of the grouping identities
published at or before t0, then materializes `b10c_outcome_labels` rows for every curve in the
`b10b` corpus under a caller-supplied preregistration, and validates counts, referential integrity,
arithmetic, determinism and leakage.

WHAT IS VALIDATED HERE, AND WHAT IS DELIBERATELY NOT
====================================================

Validated: that every curve produces exactly one row per horizon; that no observation, curve or
coverage category is dropped; that every number in every row re-derives from its primitive inputs;
that two runs are byte-identical; and that nothing after t0 is reachable from the decision half of
any row.

**Not validated, and not computed: returns.** Every `CreateEvent` in this corpus falls inside the
B8b window that `DECISIONS.md` burned on 2026-07-28, and R3 forbids measuring or tuning a label on
it. The distribution of `net_return_numerator` across these rows is therefore **not reported** by
this runner, deliberately — reporting it would be measuring a label on a burned window whether or
not anybody called the number a finding.

EVERY CURVE PRODUCES ROWS, INCLUDING THE ONES WE WOULD NOT HAVE TRADED
=====================================================================

Out-of-regime curves, curves with no observation after t0, and the curve whose entry the real-
reserve size guard refused all emit `no_decision` rows. Conditioning the label table on evaluability
would select on tradability, and tradability is correlated with exactly the outcomes a later model
would be asked to predict.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B10C = _load("b10c_outcome_labels", "b10c_outcome_labels.py")
B10BD = _load("b10b_path_dataset", "b10b_path_dataset.py")
B10B = B10C.B10B
B10A = B10C.B10A
B9D = B10B.B9D
LabelRefused = B10C.LabelRefused

IDENTITY_VERSION = "1.0.0"

IDENTITY_SCHEMA = """
CREATE TABLE identity (
    bonding_curve TEXT PRIMARY KEY,
    mint TEXT NOT NULL,
    creator TEXT NOT NULL,
    create_user TEXT NOT NULL,
    t0_slot INTEGER NOT NULL,
    t0_transaction_index INTEGER NOT NULL,
    t0_outer_index INTEGER NOT NULL,
    t0_inner_index INTEGER NOT NULL,
    t0_kind TEXT NOT NULL,
    t0_user TEXT
);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# The same order and cost policy the b10b corpus run used. Stated here, never searched: a size
# chosen per curve, or tuned until the label distribution looked better, would turn a plumbing
# check into a fit — on a burned window, which would be worse.
CORPUS_ORDER = dict(B10BD.VALIDATION_ORDER)
CORPUS_SCHEDULE = dict(B10BD.VALIDATION_SCHEDULE)
CORPUS_POLICY = dict(B10BD.VALIDATION_POLICY)


def build_identity(source_path, corpus_path, out_path, progress=None):
    """Decode the grouping identities available at or before t0 for every curve.

    `creator` and `create_user` come from the curve's own `CreateEvent`, which by definition
    precedes t0. `t0_user` comes from the t0 observation itself when that observation is a trade.
    Nothing here is read from after t0, and `identity_row` proves that per row rather than
    asserting it in a comment.
    """
    source = B9D.connect(str(source_path), readonly=True)
    corpus = sqlite3.connect(f"file:{corpus_path}?mode=ro", uri=True)
    out_path = pathlib.Path(out_path)
    if out_path.exists():
        out_path.unlink()
    derived = sqlite3.connect(str(out_path))
    try:
        derived.executescript(IDENTITY_SCHEMA)
        idls = B10BD._idls()
        cutoff = source.execute(
            "SELECT value FROM metadata WHERE key='cutoff_slot'").fetchone()
        if cutoff is None:
            raise LabelRefused(
                "the source artifact states no cutoff_slot; right-censoring is a statement about "
                "window geometry and cannot be made without the window's own end")

        cache, rows = {}, []
        curves = corpus.execute(
            "SELECT bonding_curve FROM curve ORDER BY bonding_curve").fetchall()
        for position, (curve,) in enumerate(curves):
            states = B10BD.load_states(corpus, curve)
            create = [state for state in states if state["kind"] == B10BD.KIND_CREATE]
            if len(create) != 1:
                raise LabelRefused(f"{curve}: {len(create)} CreateEvent states")
            create_fields = _decode_state(source, curve, create[0], idls, cache, "CreateEvent")
            t0_index = B10BD.select_t0(states)
            t0 = states[t0_index] if t0_index is not None else states[0]
            t0_user = None
            if t0["kind"] == B10BD.KIND_TRADE:
                t0_user = _decode_state(source, curve, t0, idls, cache, "TradeEvent")["user"]
            rows.append(identity_row(curve, create[0], t0, create_fields, t0_user))
            if progress and position % progress == 0:
                print(f"  {position:,} curves", file=sys.stderr, flush=True)

        derived.executemany("INSERT INTO identity VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        derived.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("identity_version", IDENTITY_VERSION),
            ("label_schema_version", B10C.SCHEMA_VERSION),
            ("source_artifact", pathlib.Path(source_path).name),
            ("corpus_artifact", pathlib.Path(corpus_path).name),
            ("corpus_content_sha256", B10BD.content_hash(corpus)),
            # Evidence, not an inference: the collection recorded its own end slot.
            ("observation_window_end_slot", cutoff[0]),
            ("curves", str(len(rows))),
        ])
        derived.commit()
        derived.execute(
            "INSERT INTO metadata VALUES ('content_sha256', ?)", (identity_hash(derived),))
        derived.commit()
    finally:
        derived.close()
        corpus.close()
        source.close()
    return out_path


def identity_row(curve, create_state, t0_state, create_fields, t0_user):
    """One identity row, and the ordering proof that makes it admissible.

    The check and the row are the same function on purpose. A separate `assert_...` call beside the
    row construction is one line a later edit can drop while everything still runs; here, dropping
    the check means dropping the row.
    """
    if B10B.canonical_key(create_state) > B10B.canonical_key(t0_state):
        raise LabelRefused(
            f"{create_state['mint']}: the CreateEvent is after t0, so its creator identity would "
            "be a post-decision fact")
    return (curve, t0_state["mint"], create_fields["creator"], create_fields["user"],
            t0_state["slot"], t0_state["transaction_index"], t0_state["outer_index"],
            t0_state["inner_index"], t0_state["kind"], t0_user)


def _decode_state(source, curve, state, idls, cache, expected):
    signature = source.execute(
        "SELECT signature FROM transaction_coordinate WHERE slot=? AND transaction_index=?",
        (state["slot"], state["transaction_index"])).fetchone()
    if signature is None:
        raise LabelRefused(
            f"no preserved transaction at ({state['slot']}, {state['transaction_index']})")
    # Keyed on the bonding curve too: four transactions in this artifact touch two curves at once,
    # and a coordinate-only lookup would take whichever row came back first.
    marker = source.execute(
        "SELECT evidence FROM reserve_observation WHERE bonding_curve=? AND slot=? AND "
        "transaction_index=? AND outer_index=? AND inner_index=?",
        (curve, state["slot"], state["transaction_index"], state["outer_index"],
         state["inner_index"])).fetchone()
    if marker is None:
        raise LabelRefused(f"no reserve evidence at {B10B.canonical_key(state)}")
    evidence = json.loads(marker[0])
    event = B10BD._decode_at(source, signature[0], evidence["event_outer_index"],
                             evidence["event_inner_index"], idls, cache)
    if event["name"] != expected:
        raise LabelRefused(
            f"{signature[0]}: expected {expected}, decoded {event['name']}")
    return event["fields"]


def identity_hash(derived):
    digest = hashlib.sha256()
    for row in derived.execute("SELECT * FROM identity ORDER BY bonding_curve"):
        digest.update(repr(row).encode())
    return digest.hexdigest()


def identity_metadata(derived):
    return dict(derived.execute("SELECT key, value FROM metadata"))


def load_identities(derived):
    return {row[0]: {"bonding_curve": row[0], "mint": row[1], "creator": row[2],
                     "create_user": row[3], "t0_user": row[9]}
            for row in derived.execute("SELECT * FROM identity")}


# --------------------------------------------------------------------------------------------
# Materialization over the whole corpus
# --------------------------------------------------------------------------------------------

REGIME_TO_REASON = {
    B10BD.REGIME_NON_SOL: "out_of_regime_non_sol_quote",
    B10BD.REGIME_MAYHEM: "out_of_regime_mayhem",
    B10BD.REGIME_MIXED: "out_of_regime_mixed_within_curve",
}


def materialize(corpus, identities, preregistration, recorded_window_end_slot,
                limit=None, progress=None):
    """Every curve, every horizon. Returns `(rows, report)`.

    `recorded_window_end_slot` is required rather than optional, and is the end the COLLECTION
    recorded about itself. A preregistration that states a different one is censoring against a
    window that was never collected, so the mismatch is refused here — inside the function that
    does the work — rather than in a caller a later edit can bypass.
    """
    document, preregistration_sha256 = B10C.assert_preregistration(preregistration)
    if document["observation_window_end_slot"] != recorded_window_end_slot:
        raise LabelRefused(
            f"preregistration states observation_window_end_slot "
            f"{document['observation_window_end_slot']} but the artifact recorded "
            f"{recorded_window_end_slot}; right-censoring against an uncollected window would "
            "report geometry that never existed")
    dataset_content_sha256 = B10BD.content_hash(corpus)
    horizons = document["horizons"]
    report = {
        "label_schema_version": B10C.SCHEMA_VERSION,
        "label_kind": B10C.LABEL_KIND,
        "preregistration_id": document["preregistration_id"],
        "preregistration_sha256": preregistration_sha256,
        "window_status": document["window_status"],
        "observation_window_end_slot": document["observation_window_end_slot"],
        "dataset_content_sha256": dataset_content_sha256,
        "horizons": [{"name": h["name"], "kind": h["kind"],
                      "parameter": B10C.horizon_parameter(h)} for h in horizons],
        "order": dict(CORPUS_ORDER),
        "fee_schedule": dict(CORPUS_SCHEDULE),
        "cost_policy": dict(CORPUS_POLICY),
        "curves": {"total": 0, "with_decision": 0, "no_decision": 0},
        "rows": {"total": 0, "expected": 0, "by_status": {}, "by_horizon": {},
                 "by_no_decision_reason": {}, "by_liquidity_state": {}},
        "referential_integrity": {"rows_per_curve_exact": None, "distinct_decisions": 0,
                                  "marks_found_in_corpus": 0, "marks_missing_from_corpus": []},
        "arithmetic": {"rows_checked": 0, "errors": []},
        "leakage": {"decision_blocks_constant_across_horizons": 0,
                    "decision_blocks_with_no_reachable_mark": 0,
                    "field_partition_holds": 0,
                    "slot_horizon_rows_at_or_before_target": 0},
        "returns": "NOT COMPUTED — every CreateEvent here is inside the B8b window burned on "
                   "2026-07-28, and R3 forbids measuring or tuning a label on it",
    }

    curves = corpus.execute(
        "SELECT bonding_curve, regime FROM curve ORDER BY bonding_curve").fetchall()
    if limit:
        curves = curves[:int(limit)]
    report["curves"]["total"] = len(curves)
    report["rows"]["expected"] = len(curves) * len(horizons)

    rows = []
    for position, (curve, regime) in enumerate(curves):
        identity = identities.get(curve)
        if identity is None:
            raise LabelRefused(f"{curve}: no t0 identity; rebuild the identity table")
        states = B10BD.load_states(corpus, curve)
        t0_index = B10BD.select_t0(states)
        fallback = states[t0_index] if t0_index is not None else states[0]

        reason, path_result, t0_state = None, None, fallback
        if regime != B10BD.REGIME_IN:
            reason = REGIME_TO_REASON[regime]
        elif t0_index is None:
            reason = "no_transaction_terminal_state"
        elif not states[t0_index + 1:]:
            reason = "no_later_observation"
        else:
            t0_state = states[t0_index]
            try:
                path_result = B10B.evaluate_position_path(
                    t0_state, states[t0_index + 1:], CORPUS_SCHEDULE, CORPUS_POLICY,
                    mint=identity["mint"], order=CORPUS_ORDER,
                    evidence={"bonding_curve": curve, "source": "b10c_label_corpus"})
            except B10B.FreezeViolation:
                reason, path_result = "entry_refused", None

        if path_result is None:
            curve_rows = B10C.materialize_no_decision(
                identity, document, preregistration_sha256, dataset_content_sha256,
                t0_state, CORPUS_SCHEDULE, CORPUS_POLICY, reason)
            report["curves"]["no_decision"] += 1
        else:
            curve_rows = B10C.materialize_decision(
                path_result, identity, document, preregistration_sha256,
                dataset_content_sha256, t0_state, CORPUS_ORDER, CORPUS_SCHEDULE, CORPUS_POLICY)
            report["curves"]["with_decision"] += 1

        _account(report, curve_rows, path_result, corpus)
        rows.extend(curve_rows)
        if progress and position % progress == 0:
            print(f"  {position:,} curves", file=sys.stderr, flush=True)

    report["rows"]["total"] = len(rows)
    report["referential_integrity"]["rows_per_curve_exact"] = (
        len(rows) == report["rows"]["expected"])
    report["referential_integrity"]["distinct_decisions"] = len(
        {row["decision_sha256"] for row in rows})
    report["determinism"] = {"rows_hashed": len(rows), "row_hash_chain_sha256": B10C.rows_hash(rows)}
    if not report["referential_integrity"]["rows_per_curve_exact"]:
        report["arithmetic"]["errors"].append(
            {"error": "row count does not equal curves times horizons",
             "rows": len(rows), "expected": report["rows"]["expected"]})
    return rows, report


def _account(report, curve_rows, path_result, corpus):
    """Count, check and cross-check one curve's rows. Every check increments a visible counter."""
    B10C._assert_decision_block_invariant(curve_rows)
    report["leakage"]["decision_blocks_constant_across_horizons"] += 1
    for row in curve_rows:
        B10C.assert_field_partition(row)
        report["leakage"]["field_partition_holds"] += 1
        if path_result is not None:
            B10B.assert_no_future_reachable(
                B10C.decision_block(row), path_result["marks"])
        report["leakage"]["decision_blocks_with_no_reachable_mark"] += 1

        status = row["outcome_status"]
        report["rows"]["by_status"][status] = report["rows"]["by_status"].get(status, 0) + 1
        name = row["horizon_name"]
        report["rows"]["by_horizon"].setdefault(name, {})
        report["rows"]["by_horizon"][name][status] = (
            report["rows"]["by_horizon"][name].get(status, 0) + 1)
        if row["no_decision_reason"]:
            report["rows"]["by_no_decision_reason"][row["no_decision_reason"]] = (
                report["rows"]["by_no_decision_reason"].get(row["no_decision_reason"], 0) + 1)
        if row["liquidity_state"]:
            report["rows"]["by_liquidity_state"][row["liquidity_state"]] = (
                report["rows"]["by_liquidity_state"].get(row["liquidity_state"], 0) + 1)

        try:
            B10C.assert_row_arithmetic(row, path_result)
            report["arithmetic"]["rows_checked"] += 1
        except B10C.FreezeViolation as error:
            report["arithmetic"]["errors"].append(
                {"bonding_curve": row["bonding_curve"], "horizon": name, "error": str(error)})

        if status == B10C.OUTCOME_MARKED:
            found = corpus.execute(
                "SELECT COUNT(*) FROM observation WHERE bonding_curve=? AND slot=? AND "
                "transaction_index=? AND outer_index=? AND inner_index=?",
                (row["bonding_curve"], row["mark_slot"], row["mark_transaction_index"],
                 row["mark_outer_index"], row["mark_inner_index"])).fetchone()[0]
            if found == 1:
                report["referential_integrity"]["marks_found_in_corpus"] += 1
            elif len(report["referential_integrity"]["marks_missing_from_corpus"]) < 20:
                report["referential_integrity"]["marks_missing_from_corpus"].append(
                    {"bonding_curve": row["bonding_curve"], "horizon": name, "found": found})
            if row["horizon_kind"] == B10C.HORIZON_SLOT:
                if row["mark_slot"] <= row["horizon_target_slot"]:
                    report["leakage"]["slot_horizon_rows_at_or_before_target"] += 1
                else:
                    report["arithmetic"]["errors"].append(
                        {"bonding_curve": row["bonding_curve"], "horizon": name,
                         "error": "label taken from a state after its own horizon"})


def assert_materialization_clean(corpus, identities, preregistration, recorded_window_end_slot,
                                 limit=None, progress=None):
    """Fail closed on any arithmetic, integrity or coverage error."""
    rows, report = materialize(corpus, identities, preregistration, recorded_window_end_slot,
                               limit=limit, progress=progress)
    if report["arithmetic"]["errors"]:
        raise LabelRefused(
            f"{len(report['arithmetic']['errors'])} errors over the corpus: "
            f"{report['arithmetic']['errors'][:5]}")
    if report["referential_integrity"]["marks_missing_from_corpus"]:
        raise LabelRefused("some labelled marks are not in the corpus they cite")
    if not report["referential_integrity"]["rows_per_curve_exact"]:
        raise LabelRefused("row count does not equal curves times horizons")
    return rows, report


LABEL_TABLE_SCHEMA_HEADER = "CREATE TABLE label ("


def write_labels(rows, out_path):
    """Persist rows to their own artifact, columns in declared decision-then-outcome order."""
    fields = list(B10C.DECISION_FIELDS) + list(B10C.OUTCOME_FIELDS)
    out_path = pathlib.Path(out_path)
    if out_path.exists():
        out_path.unlink()
    database = sqlite3.connect(str(out_path))
    try:
        columns = ", ".join(f'"{field}"' for field in fields)
        database.execute(f"{LABEL_TABLE_SCHEMA_HEADER}{columns})")
        database.executemany(
            f"INSERT INTO label VALUES ({','.join('?' * len(fields))})",
            [tuple(row[field] for field in fields) for row in rows])
        database.commit()
    finally:
        database.close()
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    builder = subparsers.add_parser("build-identity")
    builder.add_argument("artifact")
    builder.add_argument("corpus")
    builder.add_argument("--out", default=str(ROOT / "research" / "b10c_t0_identity.sqlite"))
    builder.add_argument("--progress", type=int, default=None)
    runner = subparsers.add_parser("materialize")
    runner.add_argument("corpus")
    runner.add_argument("identity")
    runner.add_argument("preregistration")
    runner.add_argument("--out", default=str(ROOT / "research" / "b10c_labels.sqlite"))
    runner.add_argument("--limit", type=int, default=None)
    runner.add_argument("--progress", type=int, default=None)
    runner.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "build-identity":
        path = build_identity(args.artifact, args.corpus, args.out, progress=args.progress)
        print(json.dumps({"built": str(path)}, indent=2))
        return 0

    corpus = sqlite3.connect(f"file:{args.corpus}?mode=ro", uri=True)
    identity_db = sqlite3.connect(f"file:{args.identity}?mode=ro", uri=True)
    try:
        document = json.loads(pathlib.Path(args.preregistration).read_text())
        metadata = identity_metadata(identity_db)
        identities = load_identities(identity_db)
        run = assert_materialization_clean if args.gate else materialize
        rows, report = run(corpus, identities, document,
                           int(metadata["observation_window_end_slot"]),
                           limit=args.limit, progress=args.progress)
    finally:
        identity_db.close()
        corpus.close()
    report["labels_written_to"] = str(write_labels(rows, args.out))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"FreezeViolation: {error}", file=sys.stderr)
        sys.exit(2)
