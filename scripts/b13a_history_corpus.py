#!/usr/bin/env python3
"""B13a corpus — build a real event stream and check the history materializer's plumbing on it.

Offline, read-only, no network. Runs over the BURNED B8b corpus, which is already burned and can
therefore lose nothing further from being walked.

WHAT THIS REPORTS, AND WHAT IT WILL NOT
=======================================

Reports: how many events of each kind were built, that every history respects the point-in-time
boundary, that identity strings stay out of feature blocks, that the result does not depend on the
order events arrive in, and a determinism hash.

**Reports no feature value, no distribution, no summary statistic, no correlation and no label
association — on any window.** A history is one join away from an outcome, and a distribution
inspected here is a transform chosen with the answer in view. The counts below are counts of
EVENTS and CHECKS, never of what those events say about anybody.

**Does not query, enumerate or touch B11a.** That window has still never been read.
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


B13A = _load("b13a_history", "b13a_history.py")
CORPUS = _load("b10c_label_corpus", "b10c_label_corpus.py")
B9J = _load("b9j_system_instructions", "b9j_system_instructions.py")
B10BD = CORPUS.B10BD
B10B = B13A.B10B
B9D = B10B.B9D
HistoryRefused = B13A.HistoryRefused

SYSTEM_PROGRAM = B9J.SYSTEM_PROGRAM


def _source_hash(*parts):
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def build_event_stream(source, corpus, limit=None, progress=None):
    """Launches and completions for the whole corpus; trades and transfers for a bounded slice.

    The launch and completion streams are cheap and are taken in full so a creator's prior-launch
    count is computed against every launch the window holds. Trades and transfers are decoded for a
    bounded slice because this run exists to check plumbing, not to publish a history.
    """
    idls = B10BD._idls()
    cache = {}
    events, counts = [], {"launch": 0, "trade": 0, "completion": 0, "transfer": 0}

    curves = corpus.execute(
        "SELECT bonding_curve FROM curve ORDER BY bonding_curve").fetchall()
    for (curve,) in curves:
        states = B10BD.load_states(corpus, curve)
        create = next(s for s in states if s["kind"] == B10BD.KIND_CREATE)
        fields = CORPUS._decode_state(source, curve, create, idls, cache, "CreateEvent")
        events.append({
            "kind": B13A.EVENT_LAUNCH, "mint": fields["mint"],
            "bonding_curve": fields["bonding_curve"], "creator": fields["creator"],
            "create_user": fields["user"],
            "source_sha256": _source_hash("create", curve, create["slot"]),
            **{f: create[f] for f in B13A.COORDINATE_FIELDS}})
        counts["launch"] += 1

    for row in source.execute(
            "SELECT slot, transaction_index, outer_index, inner_index, signature FROM instruction "
            "WHERE idl_name='event:CompleteEvent' "
            "ORDER BY slot, transaction_index, outer_index, inner_index"):
        slot, transaction_index, outer_index, inner_index, signature = row
        event = B10BD._decode_at(source, signature, outer_index, inner_index, idls, cache)
        events.append({
            "kind": B13A.EVENT_COMPLETION, "mint": event["fields"]["mint"],
            "slot": slot, "transaction_index": transaction_index,
            "outer_index": outer_index, "inner_index": inner_index,
            "source_sha256": _source_hash("complete", signature, outer_index, inner_index)})
        counts["completion"] += 1

    scope = [row[0] for row in corpus.execute(
        "SELECT bonding_curve FROM curve ORDER BY bonding_curve LIMIT ?",
        (int(limit) if limit else len(curves),))]
    transactions = set()
    for position, curve in enumerate(scope):
        for state in B10BD.load_states(corpus, curve):
            if state["kind"] != B10BD.KIND_TRADE:
                continue
            fields = CORPUS._decode_state(source, curve, state, idls, cache, "TradeEvent")
            events.append({
                "kind": B13A.EVENT_TRADE, "mint": fields["mint"], "user": fields["user"],
                "is_buy": bool(fields["is_buy"]),
                "quote_lamports": int(fields["quote_amount"]),
                "token_units": int(fields["token_amount"]),
                "source_sha256": _source_hash("trade", curve, state["slot"],
                                              state["transaction_index"], state["outer_index"],
                                              state["inner_index"]),
                **{f: state[f] for f in B13A.COORDINATE_FIELDS}})
            counts["trade"] += 1
            transactions.add((state["slot"], state["transaction_index"]))
        if progress and position % progress == 0:
            print(f"  {position:,} curves", file=sys.stderr, flush=True)

    events.extend(_transfer_events(source, sorted(transactions), counts))
    return events, counts


def _transfer_events(source, transactions, counts):
    """Funding edges from decoded System instructions, with source and destination as published.

    The amount comes from the pinned System ABI and the two addresses from the instruction's own
    resolved account list. Nothing is inferred: a transfer of N lamports from A to B is exactly
    that, and whether it is funding, a tip or a refund is not something this module claims to know.
    """
    out = []
    for slot, transaction_index in transactions:
        row = source.execute(
            "SELECT signature FROM transaction_coordinate WHERE slot=? AND transaction_index=?",
            (slot, transaction_index)).fetchone()
        if row is None:
            continue
        raw = source.execute(
            "SELECT raw_zlib FROM raw_transaction WHERE signature=?", (row[0],)).fetchone()
        if raw is None:
            continue
        for instruction in B9D.envelope_instructions(B9D.raw_result(raw[0])):
            if instruction["program_id"] != SYSTEM_PROGRAM:
                continue
            try:
                decoded = B9J.decode_system_instruction(instruction["data"])
            except B9D.FreezeViolation:
                # An undecodable System payload is reported by b9j's own survey; here it simply
                # yields no edge. Inventing one from the account list would be exactly the guess
                # that module refuses to make.
                continue
            moved = B9J.system_lamports_moved(decoded)
            accounts = instruction.get("accounts") or []
            if not moved or len(accounts) < 2 or accounts[0] == accounts[1]:
                continue
            out.append({
                "kind": B13A.EVENT_TRANSFER, "from_address": accounts[0],
                "to_address": accounts[1], "lamports": int(moved),
                "slot": slot, "transaction_index": transaction_index,
                "outer_index": instruction["outer_index"],
                "inner_index": instruction["inner_index"],
                "source_sha256": _source_hash("system", row[0], instruction["outer_index"],
                                              instruction["inner_index"])})
            counts["transfer"] += 1
    return out


def check(source_path, corpus_path, limit=None, progress=None, subjects=25):
    """Structural integrity only. Every number below counts events or checks, never findings."""
    source = B9D.connect(str(source_path), readonly=True)
    corpus = sqlite3.connect(f"file:{corpus_path}?mode=ro", uri=True)
    try:
        events, counts = build_event_stream(source, corpus, limit=limit, progress=progress)
        ordered, digests = B13A.ordered_events(events)
        coverage = {
            "first_slot": min(e["slot"] for e in ordered),
            "last_slot": max(e["slot"] for e in ordered),
            "source_population": "burned B8b corpus, bounded slice; plumbing only",
            # Always true over a bounded window, and the whole point: a count here is a lower
            # bound on the truth, never the truth.
            "left_truncated": True, "right_truncated": True, "complete": False,
            "provenance_sha256": B10BD.content_hash(corpus),
        }
        report = {
            "schema_version": B13A.SCHEMA_VERSION,
            "events": counts,
            "events_total": len(ordered),
            "distinct_event_hashes": len(set(digests)),
            "subjects_checked": 0,
            "boundary_respected": 0,
            "identity_kept_out_of_features": 0,
            "order_independent": 0,
            "coverage_declared_incomplete": coverage["complete"] is False,
            "feature_values_reported": False,
            "feature_values_reported_reason":
                "a history is one join away from an outcome; a distribution inspected here is a "
                "transform chosen with the answer in view",
            "b11a_touched": False,
            "errors": [],
        }
        if report["distinct_event_hashes"] != report["events_total"]:
            report["errors"].append({"error": "duplicate events in the stream"})

        chosen = [row[0] for row in corpus.execute(
            "SELECT bonding_curve FROM curve ORDER BY bonding_curve LIMIT ?", (int(subjects),))]
        hashes = []
        for curve in chosen:
            states = B10BD.load_states(corpus, curve)
            index = B10BD.select_t0(states)
            if index is None:
                continue
            t0 = states[index]
            launch = next(e for e in ordered
                          if e["kind"] == B13A.EVENT_LAUNCH and e["bonding_curve"] == curve)
            subject = {"mint": launch["mint"], "creator": launch["creator"],
                       "bonding_curve": curve, "user": launch["creator"]}
            try:
                record = B13A.build_as_of_history(ordered, subject, t0, coverage)
            except B10B.FreezeViolation as error:
                report["errors"].append({"bonding_curve": curve, "error": str(error)[:160]})
                continue
            report["subjects_checked"] += 1

            boundary = B10B.canonical_key(t0)
            edges = record["sections"]["funding"]["evidence"]["edges"]
            if all(tuple(edge["coordinate"][f] for f in B13A.COORDINATE_FIELDS) <= boundary
                   for edge in edges):
                report["boundary_respected"] += 1
            else:
                report["errors"].append({"bonding_curve": curve, "error": "edge after t0"})

            B13A.assert_history(record)
            report["identity_kept_out_of_features"] += 1

            # The same evidence in a different order must give the same history, byte for byte.
            shuffled = list(reversed(ordered))
            if B13A.build_as_of_history(shuffled, subject, t0, coverage)["history_sha256"] == \
                    record["history_sha256"]:
                report["order_independent"] += 1
            else:
                report["errors"].append({"bonding_curve": curve, "error": "order dependent"})
            hashes.append(record["history_sha256"])

        digest = hashlib.sha256()
        for value in hashes:
            digest.update(value.encode())
        report["determinism"] = {"histories_hashed": len(hashes),
                                 "history_hash_chain_sha256": digest.hexdigest()}
        return report
    finally:
        corpus.close()
        source.close()


def assert_clean(source_path, corpus_path, limit=None, progress=None, subjects=25):
    report = check(source_path, corpus_path, limit=limit, progress=progress, subjects=subjects)
    if report["errors"]:
        raise HistoryRefused(f"{len(report['errors'])} integrity errors: {report['errors'][:5]}")
    for field in ("boundary_respected", "identity_kept_out_of_features", "order_independent"):
        if report[field] != report["subjects_checked"]:
            raise HistoryRefused(f"{field} held for only {report[field]} of "
                                 f"{report['subjects_checked']} subjects")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("corpus")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--subjects", type=int, default=25)
    parser.add_argument("--progress", type=int, default=None)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    runner = assert_clean if args.gate else check
    report = runner(args.artifact, args.corpus, limit=args.limit, progress=args.progress,
                    subjects=args.subjects)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"HistoryRefused: {error}", file=sys.stderr)
        sys.exit(2)
