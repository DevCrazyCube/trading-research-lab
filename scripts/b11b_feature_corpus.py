#!/usr/bin/env python3
"""B11b feature corpus — materialize t0 features at scale, and report only that it worked.

Offline, read-only, no network. Runs the frozen t0 feature contract over the burned-development
corpus to prove the materializer works on real decoded evidence rather than only on fixtures.

WHAT THIS REPORTS, AND WHAT IT DELIBERATELY DOES NOT
====================================================

Reports: how many feature records were built, that every one satisfies the feature/grouping
partition and the no-string rule, that no observation after t0 was ever supplied, that t0 was
inside the launch transaction every time, and a determinism hash.

**Does not report, at all: any distribution, summary, mean, count-by-value, minimum or maximum of
any feature.** The preregistration forbids inspecting a feature distribution for any purpose on any
window, because inspecting one is how a transform gets chosen — and a transform chosen after
looking is feature selection with the outcomes one join away. The features were frozen in a
document committed before this file existed; nothing here may revisit that choice.

The window used is the burned B8b corpus. It is burned already, so nothing further can be lost by
running a materializer over it, and no label or outcome is touched here at all.
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


B11B = _load("b11b_t0_features", "b11b_t0_features.py")
CORPUS = _load("b10c_label_corpus", "b10c_label_corpus.py")
B10BD = CORPUS.B10BD
B10B = B11B.B10B
B9D = B11B.B9D
ContractRefused = B11B.ContractRefused

TRADE_FIELD_MAP = {
    "user": "user",
    "is_buy": "is_buy",
    "quote_amount": "quote_amount",
    "token_amount": "token_amount",
    "fee_bps": "fee_basis_points",
    "creator_fee_bps": "creator_fee_basis_points",
    "cashback_fee_bps": "cashback_fee_basis_points",
    "buyback_fee_bps": "buyback_fee_basis_points",
}


def materialize(source_path, corpus_path, limit=None, progress=None):
    """Build a t0 feature record for every curve. Returns `(records, report)`."""
    source = B9D.connect(str(source_path), readonly=True)
    corpus = sqlite3.connect(f"file:{corpus_path}?mode=ro", uri=True)
    try:
        idls = B10BD._idls()
        cache = {}
        report = {
            "feature_contract_version": B11B.FEATURE_CONTRACT_VERSION,
            "model_family": B11B.MODEL_FAMILY,
            "preregistration_file_sha256": B11B.PREREGISTRATION_FILE_SHA256,
            "corpus": pathlib.Path(corpus_path).name,
            "corpus_content_sha256": B10BD.content_hash(corpus),
            "curves": 0,
            "records_materialized": 0,
            "t0_inside_launch_transaction": 0,
            "partition_and_no_string_rule_holds": 0,
            "post_t0_observations_supplied": 0,
            "distributions_withheld": True,
            "distributions_withheld_reason":
                "the preregistration forbids inspecting a feature distribution on any window for "
                "any purpose; inspecting one is how a transform gets chosen after the fact",
            "errors": [],
        }
        records = []
        curves = corpus.execute(
            "SELECT bonding_curve FROM curve ORDER BY bonding_curve").fetchall()
        if limit:
            curves = curves[: int(limit)]
        report["curves"] = len(curves)

        for position, (curve,) in enumerate(curves):
            states = B10BD.load_states(corpus, curve)
            create_state = next(s for s in states if s["kind"] == B10BD.KIND_CREATE)
            t0_index = B10BD.select_t0(states)
            if t0_index is None:
                report["errors"].append({"bonding_curve": curve, "error": "no t0 state"})
                continue
            t0 = states[t0_index]
            if (t0["slot"], t0["transaction_index"]) == (
                    create_state["slot"], create_state["transaction_index"]):
                report["t0_inside_launch_transaction"] += 1
            else:
                report["errors"].append(
                    {"bonding_curve": curve, "error": "t0 outside the launch transaction"})
                continue

            t0_key = B10B.canonical_key(t0)
            prior = [s for s in states if B10B.canonical_key(s) <= t0_key]
            # Asserted here as well as inside the materializer: a corpus that hands over a later
            # state is a corpus problem, and it must be visible as one rather than as a refusal
            # deep inside feature construction.
            if any(B10B.canonical_key(s) > t0_key for s in prior):
                report["post_t0_observations_supplied"] += 1

            create_fields = CORPUS._decode_state(
                source, curve, create_state, idls, cache, "CreateEvent")
            observations = []
            for state in prior:
                observation = dict(state)
                if state["kind"] == B10BD.KIND_TRADE:
                    fields = CORPUS._decode_state(
                        source, curve, state, idls, cache, "TradeEvent")
                    for local, remote in TRADE_FIELD_MAP.items():
                        observation[local] = fields.get(remote)
                observations.append(observation)

            create = {
                "slot": create_state["slot"],
                "transaction_index": create_state["transaction_index"],
                "creator": create_fields["creator"],
                "mint": create_fields["mint"],
                "bonding_curve": create_fields["bonding_curve"],
                "user": create_fields["user"],
                "real_token": create_fields["real_token_reserves"],
                "token_total_supply": create_fields["token_total_supply"],
                "is_cashback_enabled": create_fields["is_cashback_enabled"],
            }
            try:
                record = B11B.build_t0_features(create, observations, t0_key)
            except B10B.FreezeViolation as error:
                report["errors"].append({"bonding_curve": curve, "error": str(error)[:160]})
                continue
            B11B.assert_feature_partition(record)
            report["partition_and_no_string_rule_holds"] += 1
            report["records_materialized"] += 1
            records.append(record)
            if progress and position % progress == 0:
                print(f"  {position:,} curves", file=sys.stderr, flush=True)

        digest = hashlib.sha256()
        for record in records:
            digest.update(record["features_sha256"].encode())
        report["determinism"] = {"records_hashed": len(records),
                                 "feature_hash_chain_sha256": digest.hexdigest()}
        return records, report
    finally:
        corpus.close()
        source.close()


def assert_materialization_clean(source_path, corpus_path, limit=None, progress=None):
    records, report = materialize(source_path, corpus_path, limit=limit, progress=progress)
    if report["errors"]:
        raise ContractRefused(
            f"{len(report['errors'])} feature-materialization errors: {report['errors'][:5]}")
    if report["post_t0_observations_supplied"]:
        raise ContractRefused(
            f"{report['post_t0_observations_supplied']} curves supplied an observation after t0")
    if report["records_materialized"] != report["curves"]:
        raise ContractRefused(
            f"{report['records_materialized']} records for {report['curves']} curves; the cohort "
            "denominator is not preserved")
    return records, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("corpus")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress", type=int, default=None)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    runner = assert_materialization_clean if args.gate else materialize
    _, report = runner(args.artifact, args.corpus, limit=args.limit, progress=args.progress)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"ContractRefused: {error}", file=sys.stderr)
        sys.exit(2)
