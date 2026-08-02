"""B13b plumbing gate — association ledgers over the burned development corpus. Structural only.

This run exists to prove the ledger's PLUMBING works on real evidence: that the boundary holds, that
every link is witnessed, that counter-evidence is attached, that the record is deterministic, and
that every refusal actually refuses. It publishes counts of links and evidence items and nothing at
all about how those links are distributed.

**No association degree, no degree distribution, no neighbourhood size ranking, no label join.** A
degree distribution inspected here would be the first step of choosing a threshold with the answer
in view, and the threshold is exactly what this phase is forbidden to choose. Read only:
`research/b9d_transaction_bodies.sqlite` and `research/b10b_observed_paths.sqlite`. B11a is never
opened.
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


B13B = _load("b13b_association", "b13b_association.py")
B13A = B13B.B13A
B10B = B13B.B10B
HISTORY = _load("b13a_history_corpus", "b13a_history_corpus.py")
B9D = HISTORY.B9D
B10BD = HISTORY.B10BD


FOCUS_SELECTION_RULE = (
    "first appearance, in canonical coordinate order, among the transfer edges of the bounded "
    "slice. NOT by degree: choosing 'the most connected wallets' would select the population on "
    "the very quantity this ledger measures, which is how a plumbing check turns into a finding. "
    "The transfer slice rather than the whole corpus because funding evidence exists only there, "
    "and an address the run cannot observe would exercise nothing.")


def focus_addresses(ordered, wanted):
    """The addresses this run considers, chosen structurally and never by how connected they are.

    See FOCUS_SELECTION_RULE. First appearance is a property of the window; degree is a property of
    the answer, and selecting on it here would make every count below a consequence of the choice.
    """
    chosen = []
    for event in ordered:
        if event["kind"] != B13A.EVENT_TRANSFER:
            continue
        for address in (event["from_address"], event["to_address"]):
            if address not in chosen and len(chosen) < wanted:
                chosen.append(address)
        if len(chosen) >= wanted:
            break
    return sorted(chosen)


def check(source_path, corpus_path, limit=None, progress=None, addresses=12, instants=5):
    """Structural integrity only. Every number below counts links or checks, never findings."""
    source = B9D.connect(str(source_path), readonly=True)
    corpus = sqlite3.connect(f"file:{corpus_path}?mode=ro", uri=True)
    try:
        events, counts, accounting = HISTORY.build_event_stream(
            source, corpus, limit=limit, progress=progress)
        ordered, _ = B13A.ordered_events(events)
        coverage = {
            "first_slot": min(e["slot"] for e in ordered),
            "last_slot": max(e["slot"] for e in ordered),
            "source_population": "burned B8b corpus, bounded slice; plumbing only",
            # Always true over a bounded window, and the whole point: a link absent here is a link
            # nobody saw, never a link that does not exist.
            "left_truncated": True, "right_truncated": True, "complete": False,
            "provenance_sha256": B10BD.content_hash(corpus),
            "decode_accounting": accounting,
        }
        focus = focus_addresses(ordered, addresses)

        report = {
            "schema_version": B13B.SCHEMA_VERSION,
            "confidence_status": B13B.CONFIDENCE_STATUS,
            "events": counts,
            "events_total": len(ordered),
            "focus_addresses": len(focus),
            "focus_selection_rule": FOCUS_SELECTION_RULE,
            "instants_checked": 0,
            "links_emitted": 0,
            "links_by_relation": {relation: 0 for relation in B13B.RELATION_TYPES},
            "evidence_items": 0,
            "evidence_by_kind": {kind: 0 for kind in B13B.EVIDENCE_KINDS},
            "counter_evidence_codes": {code: 0 for code in B13B.COUNTER_EVIDENCE_CODES},
            "boundary_respected": 0,
            "every_link_witnessed": 0,
            "counter_evidence_on_every_link": 0,
            "identity_kept_out_of_features": 0,
            "order_independent": 0,
            "neighbourhood_refused_for_every_address": 0,
            "addresses_checked_for_completeness": 0,
            "coverage_declared_incomplete": coverage["complete"] is False,
            "unresolved_evidence": len(accounting["unresolved"]),
            "lookback_chosen": B13B.unchosen_lookback()["lookback_chosen"],
            "clusters_inferred": False,
            "transitive_closure_taken": False,
            "refusals_verified": {},
            "association_degree_reported": False,
            "association_degree_reported_reason":
                "a degree distribution inspected here is the first step of choosing a threshold "
                "with the answer in view, and the threshold is what this phase may not choose",
            "b11a_touched": False,
            "errors": [],
        }

        # The instants. Taken from the corpus's own decision points in canonical curve order, so
        # the boundary is exercised at several real coordinates rather than one convenient one.
        curves = [row[0] for row in corpus.execute(
            "SELECT bonding_curve FROM curve ORDER BY bonding_curve LIMIT ?", (int(instants),))]
        hashes = []
        for curve in curves:
            states = B10BD.load_states(corpus, curve)
            index = B10BD.select_t0(states)
            if index is None:
                continue
            t0 = states[index]
            try:
                ledger = B13B.build_association_ledger(ordered, focus, t0, coverage)
            except B10B.FreezeViolation as error:
                report["errors"].append({"bonding_curve": curve, "error": str(error)[:200]})
                continue
            report["instants_checked"] += 1
            report["links_emitted"] += ledger["accounting"]["links_emitted"]
            report["evidence_items"] += ledger["accounting"]["evidence_items"]
            for relation, value in ledger["accounting"]["links_by_relation"].items():
                report["links_by_relation"][relation] += value
            for kind, value in ledger["accounting"]["evidence_by_kind"].items():
                report["evidence_by_kind"][kind] += value

            boundary = B10B.canonical_key(t0)
            after = [item for link in ledger["links"] for item in link["evidence"]
                     for c in item["coordinates"]
                     if tuple(c[f] for f in B13B.COORDINATE_FIELDS) > boundary]
            if after:
                report["errors"].append({"bonding_curve": curve,
                                         "error": f"{len(after)} evidence coordinates after t0"})
            else:
                report["boundary_respected"] += 1

            try:
                B13B.assert_no_transitive_link(ledger)
                report["every_link_witnessed"] += 1
            except B10B.FreezeViolation as error:
                report["errors"].append({"bonding_curve": curve, "error": str(error)[:200]})

            if all(link["counter_evidence"] for link in ledger["links"]):
                report["counter_evidence_on_every_link"] += 1
            elif ledger["links"]:
                report["errors"].append({"bonding_curve": curve,
                                         "error": "a link carries no counter-evidence while no "
                                                  "role has been established"})
            else:
                report["counter_evidence_on_every_link"] += 1
            for link in ledger["links"]:
                for entry in link["counter_evidence"]:
                    report["counter_evidence_codes"][entry["reason_code"]] += 1

            B13B.assert_ledger(ledger)
            report["identity_kept_out_of_features"] += 1

            # The same evidence in a different order must give the same ledger, byte for byte.
            shuffled = B13B.build_association_ledger(
                list(reversed(ordered)), list(reversed(focus)), t0, coverage)
            if shuffled["ledger_sha256"] == ledger["ledger_sha256"]:
                report["order_independent"] += 1
            else:
                report["errors"].append({"bonding_curve": curve, "error": "order dependent"})

            # A truncated window must refuse every policy that needs a whole neighbourhood.
            for address in focus:
                report["addresses_checked_for_completeness"] += 1
                try:
                    B13B.require_complete_neighbourhood(ledger, address)
                    report["errors"].append({"bonding_curve": curve, "address": address,
                                             "error": "a truncated window let a neighbourhood "
                                                      "completeness check pass"})
                except B10B.FreezeViolation:
                    report["neighbourhood_refused_for_every_address"] += 1
            hashes.append(ledger["ledger_sha256"])

        # The refusals, exercised rather than asserted in prose.
        for name in ("cluster_id", "connected_component", "merge_addresses",
                     "association_probability", "cluster_adjusted_concentration"):
            try:
                getattr(B13B, name)("a", "b")
                report["refusals_verified"][name] = False
                report["errors"].append({"error": f"{name} returned instead of refusing"})
            except B13B.ClusterRefused:
                report["refusals_verified"][name] = True

        # Which code paths this corpus actually drove. A gate that stays silent about the kinds it
        # never exercised reads as though it covered them; the unexercised ones are covered by
        # pinned unit tests instead, and saying so is the only way a reader can tell.
        report["evidence_kinds_not_exercised_by_this_corpus"] = sorted(
            kind for kind, value in report["evidence_by_kind"].items() if value == 0)
        report["evidence_kinds_not_exercised_reason"] = (
            "the focus addresses are transfer participants, so launch-role co-signing does not "
            "arise among them; that path is driven by synthetic fixtures in the test suite")

        digest = hashlib.sha256()
        for value in hashes:
            digest.update(value.encode())
        report["determinism"] = {"ledgers_hashed": len(hashes),
                                 "ledger_hash_chain_sha256": digest.hexdigest()}
        return report
    finally:
        corpus.close()
        source.close()


def gate_failures(report):
    """Why this run does not pass the gate. Pure, so the gate's own logic can be tested.

    Extracted from `assert_clean` rather than inlined there: a gate whose conditions can only be
    exercised by running the whole corpus is a gate nobody can show works.
    """
    failures = []
    if report["errors"]:
        failures.append(f"{len(report['errors'])} integrity errors: {report['errors'][:5]}")
    checked = report["instants_checked"]
    for field in ("boundary_respected", "every_link_witnessed", "counter_evidence_on_every_link",
                  "identity_kept_out_of_features", "order_independent"):
        if report[field] != checked:
            failures.append(f"{field} held for only {report[field]} of {checked} instants")
    if (report["neighbourhood_refused_for_every_address"]
            != report["addresses_checked_for_completeness"]):
        failures.append("a truncated window let a neighbourhood completeness check pass")
    if not all(report["refusals_verified"].values()):
        failures.append("an operation that must fail closed did not")
    if report["association_degree_reported"]:
        failures.append("this gate may not publish an association degree")
    if report["clusters_inferred"] or report["transitive_closure_taken"]:
        failures.append("this gate may not infer a cluster or take a transitive closure")
    return failures


def assert_clean(source_path, corpus_path, limit=None, progress=None, addresses=12, instants=5):
    report = check(source_path, corpus_path, limit=limit, progress=progress, addresses=addresses,
                   instants=instants)
    failures = gate_failures(report)
    if failures:
        raise B13B.AssociationRefused("; ".join(failures))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("corpus")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--addresses", type=int, default=12)
    parser.add_argument("--instants", type=int, default=5)
    parser.add_argument("--progress", type=int, default=None)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    runner = assert_clean if args.gate else check
    report = runner(args.artifact, args.corpus, limit=args.limit, progress=args.progress,
                    addresses=args.addresses, instants=args.instants)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"AssociationRefused: {error}", file=sys.stderr)
        sys.exit(2)
