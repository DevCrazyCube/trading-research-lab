#!/usr/bin/env python3
"""B10b dataset — the canonical observed-state path corpus, and the validation run over it.

Offline, read-only against the frozen artifact, no network. Builds a reproducible derived corpus of
observed curve states in canonical order, then evaluates `b10b_position_path` over the whole
1,136-curve population and reports coverage, ordering, arithmetic and determinism.

TWO THINGS THIS FILE IS CAREFUL ABOUT
=====================================

**The state an exit of ours could actually face is the state at the END of another party's
transaction, not part-way through it.** Our exit is its own transaction; it cannot land inside
somebody else's. So a curve that receives two trades in one transaction publishes two reserve
observations, and only the second is a state we could have traded against. Every observation is
marked `is_transaction_terminal` and the evaluator prices only those. 1,121 transactions in this
artifact carry more than one observation on the same curve, so this is measured, not hypothetical.

**Completion applies from its transaction, not from its instruction.** `CompleteEvent` fires at an
inner index after the trade that completed the curve. A trade observation in that same transaction
therefore describes a curve that is complete before any transaction of ours could follow it, and it
is marked complete accordingly. Comparing on the full instruction coordinate instead would report
one tradable state that never existed for us.

NOTHING HERE SELECTS AN ENTRY OR COMPUTES A STRATEGY RETURN. The validation order is a single fixed
size stated in this file, applied to every eligible curve without exception, so that the corpus
exercises the evaluator rather than searching it for a profitable rule.
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


B10B = _load("b10b_position_path", "b10b_position_path.py")
B10A = B10B.B10A
B9D = B10B.B9D
PathRefused = B10B.PathRefused

DATASET_VERSION = "1.0.0"

KIND_CREATE = "CreateEvent"
KIND_TRADE = "TradeEvent"

REGIME_IN = "in_regime"
REGIME_NON_SOL = "out_of_regime_non_sol_quote"
REGIME_MAYHEM = "out_of_regime_mayhem"
REGIME_MIXED = "out_of_regime_mixed_within_curve"

SCHEMA = """
CREATE TABLE curve (
    bonding_curve TEXT PRIMARY KEY,
    mint TEXT NOT NULL,
    create_slot INTEGER NOT NULL,
    create_transaction_index INTEGER NOT NULL,
    create_outer_index INTEGER NOT NULL,
    create_inner_index INTEGER NOT NULL,
    complete_slot INTEGER,
    complete_transaction_index INTEGER,
    trade_observations INTEGER NOT NULL,
    regime TEXT NOT NULL
);
CREATE TABLE observation (
    bonding_curve TEXT NOT NULL,
    slot INTEGER NOT NULL,
    transaction_index INTEGER NOT NULL,
    outer_index INTEGER NOT NULL,
    inner_index INTEGER NOT NULL,
    mint TEXT NOT NULL,
    kind TEXT NOT NULL,
    virtual_quote INTEGER NOT NULL,
    virtual_token INTEGER NOT NULL,
    real_quote INTEGER NOT NULL,
    real_token INTEGER NOT NULL,
    quote_mint TEXT NOT NULL,
    mayhem_mode INTEGER NOT NULL,
    complete INTEGER NOT NULL,
    is_transaction_terminal INTEGER NOT NULL,
    PRIMARY KEY (bonding_curve, slot, transaction_index, outer_index, inner_index)
);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _idls():
    return {B9D.PUMP_PROGRAM: B9D.load_pinned_idl(
                B9D.PUMP_IDL_PATH, B9D.PUMP_IDL_SHA256, B9D.PUMP_PROGRAM),
            B9D.PUMPSWAP_PROGRAM: B9D.load_pinned_idl(
                B9D.PUMPSWAP_IDL_PATH, B9D.PUMPSWAP_IDL_SHA256, B9D.PUMPSWAP_PROGRAM)}


def _decode_at(source, signature, outer_index, inner_index, idls, cache):
    """Decode the anchor CPI event at exactly these coordinates, or refuse.

    The pairing must resolve to exactly one instruction. Matching on the outer index alone mispairs
    bundled transactions carrying several trades under one outer instruction — the defect that
    produced a spurious 389,217,712-lamport mismatch on b10a's first gate run.
    """
    if cache.get("signature") != signature:
        raw = source.execute(
            "SELECT raw_zlib FROM raw_transaction WHERE signature=?", (signature,)).fetchone()
        if raw is None:
            raise PathRefused(f"{signature}: no preserved transaction body")
        cache.clear()
        cache["signature"] = signature
        cache["instructions"] = B9D.envelope_instructions(B9D.raw_result(raw[0]))
    located = [e for e in cache["instructions"]
               if e["outer_index"] == outer_index and e["inner_index"] == inner_index]
    if len(located) != 1:
        raise PathRefused(
            f"{signature}: event coordinates ({outer_index}, {inner_index}) resolve to "
            f"{len(located)} instructions")
    event = B9D.decode_anchor_cpi_event(located[0]["program_id"], located[0]["data"], idls)
    if event is None:
        raise PathRefused(f"{signature}: instruction at ({outer_index}, {inner_index}) is not a "
                          "decodable anchor CPI event")
    return event


def completion_coordinates(source, idls):
    """bonding_curve -> (slot, transaction_index) of its `CompleteEvent`.

    Keyed on the transaction, not the instruction, because our exit is a separate transaction: a
    curve that completes at inner index 7 is already complete for every transaction that follows,
    including one carrying a trade at inner index 5 of the SAME transaction, which we could never
    have got in front of.
    """
    out, cache = {}, {}
    rows = source.execute(
        "SELECT slot, transaction_index, outer_index, inner_index, signature FROM instruction "
        "WHERE idl_name='event:CompleteEvent' "
        "ORDER BY slot, transaction_index, outer_index, inner_index").fetchall()
    for slot, transaction_index, outer_index, inner_index, signature in rows:
        event = _decode_at(source, signature, outer_index, inner_index, idls, cache)
        if event["name"] != "CompleteEvent":
            raise PathRefused(f"{signature}: expected CompleteEvent, decoded {event['name']}")
        curve = event["fields"].get("bonding_curve")
        if not curve:
            raise PathRefused(f"{signature}: CompleteEvent names no bonding curve")
        # Earliest wins. A second completion on one curve would be a protocol fact this project has
        # not established, so it is refused rather than overwritten.
        if curve in out:
            raise PathRefused(
                f"{curve}: two CompleteEvents, at {out[curve]} and "
                f"({slot}, {transaction_index}); completion is assumed once per curve")
        out[curve] = (slot, transaction_index)
    return out


def is_complete_at(slot, transaction_index, complete_at):
    """Is the curve complete, as far as a transaction of OURS following this one is concerned?

    Compared at TRANSACTION granularity, and the comparison is inclusive. `CompleteEvent` fires at
    an inner index after the trade that completed the curve, so a trade observation in the
    completing transaction describes a curve that is already finished before anything of ours could
    follow it. An exclusive comparison, or one on the full instruction coordinate, would publish one
    tradable state per completed curve that never existed for us — and it would be the most
    valuable-looking state on the whole path, because it sits at the top of the curve.
    """
    if complete_at is None:
        return False
    return (slot, transaction_index) >= tuple(complete_at)


def build(source_path, out_path, progress=None):
    """Decode the whole reserve corpus into a derived, reproducible observed-state dataset."""
    source = B9D.connect(str(source_path), readonly=True)
    out_path = pathlib.Path(out_path)
    if out_path.exists():
        out_path.unlink()
    derived = sqlite3.connect(str(out_path))
    try:
        derived.executescript(SCHEMA)
        idls = _idls()
        completions = completion_coordinates(source, idls)

        rows = source.execute(
            "SELECT r.bonding_curve, r.slot, r.transaction_index, r.outer_index, r.inner_index, "
            "r.evidence, r.virtual_quote_after, r.virtual_token_after, r.real_quote_after, "
            "r.real_token_after, c.signature "
            "FROM reserve_observation r "
            "JOIN transaction_coordinate c "
            "  ON c.slot=r.slot AND c.transaction_index=r.transaction_index "
            "ORDER BY r.slot, r.transaction_index, r.outer_index, r.inner_index, r.bonding_curve")

        cache, records, counts = {}, [], {"decoded": 0}
        for (curve, slot, transaction_index, outer_index, inner_index, evidence,
             virtual_quote, virtual_token, real_quote, real_token, signature) in rows:
            marker = json.loads(evidence)
            event = _decode_at(source, signature, marker["event_outer_index"],
                               marker["event_inner_index"], idls, cache)
            fields = event["fields"]
            if event["name"] == "CreateEvent":
                kind = KIND_CREATE
                mayhem = bool(fields["is_mayhem_mode"])
            elif event["name"] == "TradeEvent":
                kind = KIND_TRADE
                mayhem = bool(fields["mayhem_mode"])
            else:
                raise PathRefused(
                    f"{signature}: reserve evidence names a {event['name']}, which carries no "
                    "curve state this dataset knows how to read")
            if fields.get("bonding_curve") not in (None, curve):
                raise PathRefused(
                    f"{signature}: event names curve {fields['bonding_curve']} but the reserve row "
                    f"names {curve}")
            complete = is_complete_at(slot, transaction_index, completions.get(curve))
            records.append((curve, slot, transaction_index, outer_index, inner_index,
                            fields["mint"], kind, virtual_quote, virtual_token, real_quote,
                            real_token, fields["quote_mint"], int(mayhem), int(complete), 0))
            if complete and event["name"] == "TradeEvent":
                counts["trades_in_or_after_the_completing_transaction"] = counts.get(
                    "trades_in_or_after_the_completing_transaction", 0) + 1
            counts["decoded"] += 1
            if progress and counts["decoded"] % progress == 0:
                print(f"  {counts['decoded']:,} decoded", file=sys.stderr, flush=True)

        # Transaction terminality, in canonical order: the last observation for a curve within one
        # transaction is the only state a following transaction of ours could have faced.
        terminal_by_transaction = {}
        for index, record in enumerate(records):
            terminal_by_transaction[(record[0], record[1], record[2])] = index
        terminal_indices = set(terminal_by_transaction.values())
        records = [record[:14] + (int(index in terminal_indices),)
                   for index, record in enumerate(records)]

        derived.executemany(
            "INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", records)

        for curve, in derived.execute(
                "SELECT DISTINCT bonding_curve FROM observation ORDER BY bonding_curve"):
            _insert_curve(derived, curve, completions.get(curve))

        derived.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("dataset_version", DATASET_VERSION),
            ("path_schema_version", B10B.SCHEMA_VERSION),
            ("source_artifact", pathlib.Path(source_path).name),
            ("observations", str(len(records))),
            ("curves", str(derived.execute("SELECT COUNT(*) FROM curve").fetchone()[0])),
            ("completions", str(len(completions))),
            ("canonical_order", ",".join(B10B.CANONICAL_ORDER)),
        ])
        derived.commit()
        derived.execute(
            "INSERT INTO metadata VALUES ('content_sha256', ?)", (content_hash(derived),))
        derived.commit()
    finally:
        derived.close()
        source.close()
    return out_path


def _insert_curve(derived, curve, complete_at):
    create = derived.execute(
        "SELECT slot, transaction_index, outer_index, inner_index, mint FROM observation "
        "WHERE bonding_curve=? AND kind=? "
        "ORDER BY slot, transaction_index, outer_index, inner_index",
        (curve, KIND_CREATE)).fetchall()
    if len(create) != 1:
        raise PathRefused(
            f"{curve}: {len(create)} CreateEvent observations; cohort membership is fixed at "
            "CreateEvent (DEFINITIONS.md C3) and cannot be fixed by zero or two of them")
    quote_mints = [row[0] for row in derived.execute(
        "SELECT DISTINCT quote_mint FROM observation WHERE bonding_curve=?", (curve,))]
    mayhems = [row[0] for row in derived.execute(
        "SELECT DISTINCT mayhem_mode FROM observation WHERE bonding_curve=?", (curve,))]
    if len(quote_mints) > 1 or len(mayhems) > 1:
        regime = REGIME_MIXED
    elif quote_mints[0] != B9D.NATIVE_QUOTE_MINT:
        regime = REGIME_NON_SOL
    elif mayhems[0]:
        regime = REGIME_MAYHEM
    else:
        regime = REGIME_IN
    trades = derived.execute(
        "SELECT COUNT(*) FROM observation WHERE bonding_curve=? AND kind=?",
        (curve, KIND_TRADE)).fetchone()[0]
    derived.execute(
        "INSERT INTO curve VALUES (?,?,?,?,?,?,?,?,?,?)",
        (curve, create[0][4], create[0][0], create[0][1], create[0][2], create[0][3],
         None if complete_at is None else complete_at[0],
         None if complete_at is None else complete_at[1],
         trades, regime))


def content_hash(derived):
    """A hash over the derived content in canonical order, independent of storage layout."""
    digest = hashlib.sha256()
    for table, order in (("curve", "bonding_curve"),
                         ("observation",
                          "bonding_curve, slot, transaction_index, outer_index, inner_index")):
        digest.update(table.encode())
        for row in derived.execute(f"SELECT * FROM {table} ORDER BY {order}"):
            digest.update(repr(row).encode())
    return digest.hexdigest()


# --------------------------------------------------------------------------------------------
# Validation over the whole population
# --------------------------------------------------------------------------------------------

# One fixed order for every eligible curve. Stated here, not searched: a size chosen per curve, or
# tuned until the aggregate looked better, would turn a corpus exercise into a strategy fit.
VALIDATION_ORDER = {"side": B10A.BUY, "quote_lamports": 100_000_000}
# Every rate and cost is stated. `b10a` refuses a policy that omits one, and nothing here supplies
# a default. These are the artifact's observed rates and a plainly-stated cost stack, NOT measured
# landing costs — no priority fee or tip in this project has been calibrated against forward data.
VALIDATION_SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0,
                       "buyback_fee_bps": 5000}
VALIDATION_POLICY = {"base_fee_lamports": 5_000, "priority_fee_lamports": 100_000,
                     "tip_lamports": 0, "ata_rent_lamports": 2_039_280, "failed_attempts": 0}
VALIDATION_RULES = (
    {"name": "h_1000_slots", "kind": B10B.RULE_SLOT_HORIZON, "slots": 1_000},
    {"name": "h_10000_slots", "kind": B10B.RULE_SLOT_HORIZON, "slots": 10_000},
    {"name": "h_10_observations", "kind": B10B.RULE_OBSERVATION_HORIZON, "count": 10},
    {"name": "first_full_size_exit", "kind": B10B.RULE_FIRST_FULL_SIZE_EXIT},
    {"name": "terminal_observation", "kind": B10B.RULE_TERMINAL_OBSERVATION},
)


# The buckets every observation must land in exactly once.
COVERAGE_BUCKETS = ("on_out_of_regime_curves", "on_curves_without_a_later_observation",
                    "on_curves_where_entry_was_refused", "at_or_before_t0_on_evaluated_curves",
                    "supplied_to_evaluator")


def select_t0(states):
    """Index of the decision state: the first state a transaction of OURS could have faced.

    Extracted so that every consumer selects t0 the same way. A second module choosing t0 by its
    own rule would silently label a different decision than the one the path priced.
    """
    return next((i for i, state in enumerate(states) if state["is_transaction_terminal"]), None)


def coverage_partition_error(coverage):
    """`None` when the buckets partition the corpus, an error record when they do not.

    A pure function rather than an inline comparison because a gate that reports on its own
    completeness is only worth as much as a test that can make it report failure. This one can be
    handed a deliberately unbalanced count and asked what it says.
    """
    partition = sum(coverage[key] for key in COVERAGE_BUCKETS)
    if partition != coverage["observations_total"]:
        return {"error": "coverage partition does not sum to the observation total",
                "partition": partition, "total": coverage["observations_total"]}
    return None


def load_curve_rows(derived):
    return derived.execute(
        "SELECT bonding_curve, mint, regime, trade_observations, complete_slot "
        "FROM curve ORDER BY bonding_curve").fetchall()


def load_states(derived, curve):
    """Every observed state for one curve, in canonical order. Never insertion order."""
    rows = derived.execute(
        "SELECT slot, transaction_index, outer_index, inner_index, mint, kind, virtual_quote, "
        "virtual_token, real_quote, real_token, quote_mint, mayhem_mode, complete, "
        "is_transaction_terminal FROM observation WHERE bonding_curve=? "
        "ORDER BY slot, transaction_index, outer_index, inner_index", (curve,)).fetchall()
    return [{"slot": r[0], "transaction_index": r[1], "outer_index": r[2], "inner_index": r[3],
             "mint": r[4], "kind": r[5], "virtual_quote": r[6], "virtual_token": r[7],
             "real_quote": r[8], "real_token": r[9], "quote_mint": r[10],
             "mayhem_mode": bool(r[11]), "complete": bool(r[12]),
             "is_transaction_terminal": bool(r[13])} for r in rows]


def validate(derived, limit=None, progress=None):
    """Coverage, ordering, arithmetic and determinism over the whole population."""
    report = {
        "dataset_version": DATASET_VERSION,
        "path_schema_version": B10B.SCHEMA_VERSION,
        "outcome_label": B10B.OUTCOME_SIMULATED_OBSERVED_PATH,
        "canonical_order": list(B10B.CANONICAL_ORDER),
        "validation_order": dict(VALIDATION_ORDER),
        "fee_schedule": dict(VALIDATION_SCHEDULE),
        "cost_policy": dict(VALIDATION_POLICY),
        "curves": {"total": 0, "by_regime": {}, "evaluated": 0, "no_later_observation": 0,
                   "no_transaction_terminal_state": 0, "without_any_trade_observation": 0,
                   "t0_advanced_past_mid_transaction_launch": 0, "entry_refused": {}},
        "observations": {"total": 0, "create": 0, "trade": 0, "transaction_terminal": 0,
                         "supplied_to_evaluator": 0, "evaluated": 0,
                         "recorded_not_evaluated": 0, "dropped_after_completion": 0},
        "ordering": {"curves_checked": 0, "strictly_increasing": 0},
        # A partition, not a set of counters. Every observation in the corpus lands in exactly one
        # bucket and the buckets are asserted to sum to the total, so an observation cannot go
        # missing between "we have 94,389" and "we evaluated 91,296" without the gate saying so.
        "coverage": {"observations_total": 0, "on_out_of_regime_curves": 0,
                     "on_curves_without_a_later_observation": 0,
                     "on_curves_where_entry_was_refused": 0,
                     "at_or_before_t0_on_evaluated_curves": 0, "supplied_to_evaluator": 0,
                     "partition_total": None, "partition_sums_to_total": None},
        "liquidity": {}, "terminal_state": {}, "rule_outcomes": {},
        "arithmetic": {"paths_checked": 0, "errors": []},
        "completions": {"curves_with_complete_event": 0, "reached_in_path": 0},
    }
    for row in derived.execute("SELECT kind, COUNT(*) FROM observation GROUP BY kind"):
        report["observations"][row[0].lower().replace("event", "")] = row[1]
        report["observations"]["total"] += row[1]
    report["observations"]["transaction_terminal"] = derived.execute(
        "SELECT COUNT(*) FROM observation WHERE is_transaction_terminal=1").fetchone()[0]

    curves = load_curve_rows(derived)
    if limit:
        curves = curves[:int(limit)]
    report["curves"]["total"] = len(curves)
    hashes = []
    for position, (curve, mint, regime, trades, complete_slot) in enumerate(curves):
        report["curves"]["by_regime"][regime] = report["curves"]["by_regime"].get(regime, 0) + 1
        if complete_slot is not None:
            report["completions"]["curves_with_complete_event"] += 1
        states = load_states(derived, curve)

        report["ordering"]["curves_checked"] += 1
        keys = [B10B.canonical_key(state) for state in states]
        if all(a < b for a, b in zip(keys, keys[1:])):
            report["ordering"]["strictly_increasing"] += 1
        else:
            report["arithmetic"]["errors"].append(
                {"bonding_curve": curve, "error": "observations are not strictly increasing"})

        report["coverage"]["observations_total"] += len(states)
        if trades == 0:
            report["curves"]["without_any_trade_observation"] += 1
        if regime != REGIME_IN:
            report["coverage"]["on_out_of_regime_curves"] += len(states)
            continue
        # t0 must itself be a state we could have traded against, for the same reason every mark
        # must be: a launch transaction that also carries the creator's own first buy publishes a
        # mid-transaction launch state that no transaction of ours could ever have faced.
        t0_position = select_t0(states)
        if t0_position is None:
            report["curves"]["no_transaction_terminal_state"] += 1
            report["coverage"]["on_curves_without_a_later_observation"] += len(states)
            continue
        if t0_position != 0:
            report["curves"]["t0_advanced_past_mid_transaction_launch"] += 1
        t0, later = states[t0_position], states[t0_position + 1:]
        if not later:
            report["curves"]["no_later_observation"] += 1
            report["coverage"]["on_curves_without_a_later_observation"] += len(states)
            continue
        try:
            result = B10B.evaluate_position_path(
                t0, later, VALIDATION_SCHEDULE, VALIDATION_POLICY, mint=mint,
                order=VALIDATION_ORDER, exit_rules=VALIDATION_RULES,
                evidence={"bonding_curve": curve, "source": "b10b_path_dataset"})
        except B10B.FreezeViolation as error:
            key = str(error).split(";")[0][:120]
            report["curves"]["entry_refused"][key] = (
                report["curves"]["entry_refused"].get(key, 0) + 1)
            report["coverage"]["on_curves_where_entry_was_refused"] += len(states)
            continue

        report["coverage"]["at_or_before_t0_on_evaluated_curves"] += t0_position + 1
        report["coverage"]["supplied_to_evaluator"] += len(later)
        B10B.assert_path_arithmetic(result)
        report["arithmetic"]["paths_checked"] += 1
        report["curves"]["evaluated"] += 1
        report["observations"]["supplied_to_evaluator"] += result["observations_supplied"]
        report["observations"]["evaluated"] += result["observations_evaluated"]
        report["observations"]["recorded_not_evaluated"] += (
            result["observations_recorded_not_evaluated"])
        report["observations"]["dropped_after_completion"] += (
            result["observations_dropped_after_completion"])
        for mark in result["marks"]:
            bucket = mark["liquidity"] or mark["reason"]
            report["liquidity"][bucket] = report["liquidity"].get(bucket, 0) + 1
        report["terminal_state"][result["terminal_state"]] = (
            report["terminal_state"].get(result["terminal_state"], 0) + 1)
        if result["terminal_state"] == B10B.TERMINAL_STRUCTURAL_UNAVAILABILITY:
            report["completions"]["reached_in_path"] += 1
        for rule in result["exit_rules"]:
            outcomes = report["rule_outcomes"].setdefault(rule["name"], {})
            outcomes[rule["outcome"]] = outcomes.get(rule["outcome"], 0) + 1
        hashes.append(B10B.record_hash(result))
        if progress and position % progress == 0:
            print(f"  {position:,} curves", file=sys.stderr, flush=True)

    coverage = report["coverage"]
    coverage["partition_total"] = sum(coverage[key] for key in COVERAGE_BUCKETS)
    mismatch = coverage_partition_error(coverage)
    coverage["partition_sums_to_total"] = mismatch is None
    if mismatch is not None:
        report["arithmetic"]["errors"].append(mismatch)

    digest = hashlib.sha256()
    for value in hashes:
        digest.update(value.encode())
    report["determinism"] = {"path_records_hashed": len(hashes),
                             "path_record_hash_chain_sha256": digest.hexdigest()}
    report["dataset_content_sha256"] = content_hash(derived)
    return report


def assert_validation_clean(derived, limit=None, progress=None):
    """Fail closed on any ordering or arithmetic error."""
    report = validate(derived, limit=limit, progress=progress)
    if report["arithmetic"]["errors"]:
        raise PathRefused(
            f"{len(report['arithmetic']['errors'])} unexplained errors over the corpus: "
            f"{report['arithmetic']['errors'][:5]}")
    if report["ordering"]["curves_checked"] != report["ordering"]["strictly_increasing"]:
        raise PathRefused("some curves are not in strictly increasing canonical order")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    builder = subparsers.add_parser("build")
    builder.add_argument("artifact")
    builder.add_argument("--out", default=str(ROOT / "research" / "b10b_observed_paths.sqlite"))
    builder.add_argument("--progress", type=int, default=None)
    validator = subparsers.add_parser("validate")
    validator.add_argument("dataset")
    validator.add_argument("--limit", type=int, default=None)
    validator.add_argument("--progress", type=int, default=None)
    validator.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "build":
        path = build(args.artifact, args.out, progress=args.progress)
        print(json.dumps({"built": str(path)}, indent=2))
        return 0
    derived = sqlite3.connect(f"file:{args.dataset}?mode=ro", uri=True)
    try:
        runner = assert_validation_clean if args.gate else validate
        report = runner(derived, limit=args.limit, progress=args.progress)
    finally:
        derived.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"FreezeViolation: {error}", file=sys.stderr)
        sys.exit(2)
