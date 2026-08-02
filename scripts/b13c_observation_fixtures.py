"""B13c fixture corpus and offline report — synthetic observations only. No network, no vendors.

Every observation below is invented. Nothing was fetched, no provider was contacted, no credential
exists and no vendor has been selected. The providers are called `provider-alpha` and
`provider-beta` precisely so that nobody can mistake this for a description of a real feed.

The corpus exists to exercise the seams that only show up in combination: a correction arriving
after a decision, a deletion arriving after a decision, an article published before t0 but fetched
after it, a ticker that collides with another token, a quote in the wrong unit, and a monotonic
clock running backwards inside one session.

The report counts observations, chains and checks. It reports **no content, no distribution and no
derived quantity of any kind**, and it never opens the burned corpus or B11a.
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


B13C = _load("b13c_observations", "b13c_observations.py")
B10B = B13C.B10B

SECOND = 1_000_000_000
# An arbitrary fixed epoch offset so the numbers read like instants without being any real date.
BASE = 1_700_000_000 * SECOND

MINT_A = "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
MINT_B = "MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
SHARED_TICKER = "$DOG"

QUERY_SPEC = hashlib.sha256(b"synthetic query specification, no vendor").hexdigest()
FETCH_PROVENANCE = hashlib.sha256(b"synthetic fetch session, nothing was fetched").hexdigest()


def _observation(identifier, kind, published_s, received_s, monotonic, **kwargs):
    """One synthetic observation. Times are seconds after BASE, for readability."""
    kwargs.setdefault("license_status", B13C.LICENSE_PERMITS_STORAGE)
    kwargs.setdefault("retention_status", B13C.RETENTION_RAW_RETAINED)
    kwargs.setdefault("raw_payload", f"synthetic payload for {identifier}")
    publication = kwargs.pop("publication_time", None) or B13C.time_claim(
        BASE + published_s * SECOND, 0, "provider-stated publication instant")
    receipt = kwargs.pop("receipt_time", None) or B13C.time_claim(
        BASE + received_s * SECOND, 0, "our own wall clock at receipt")
    return B13C.build_observation(
        kwargs.pop("provider", "provider-alpha"), identifier, kind, QUERY_SPEC,
        kwargs.pop("fetch_session_id", "session-1"), FETCH_PROVENANCE,
        "synthetic-decoder", "1.0.0", receipt, publication, monotonic, **kwargs)


def build_fixture_corpus():
    """A deterministic synthetic corpus, one entry per seam worth exercising."""
    corpus = {}

    # 1. A news article corrected after it was first published, then corrected again. The middle
    #    version is the one a decision between the two corrections actually saw.
    create = _observation(
        "news-1", B13C.KIND_NEWS_ARTICLE, published_s=100, received_s=110, monotonic=1_000,
        raw_payload="original wording of the synthetic article",
        mapping=B13C.exact_binding(mint=MINT_A, binding_evidence="mint address quoted in body"),
        evidence={"headline": "synthetic headline", "url": "https://example.invalid/news-1"})
    edit = _observation(
        "news-1", B13C.KIND_NEWS_ARTICLE, published_s=100, received_s=300, monotonic=3_000,
        raw_payload="corrected wording of the synthetic article",
        revision_kind=B13C.REVISION_EDIT, revision_index=1,
        supersedes=create["observation_sha256"],
        mapping=B13C.exact_binding(mint=MINT_A, binding_evidence="mint address quoted in body"),
        evidence={"headline": "synthetic headline", "url": "https://example.invalid/news-1"})
    edit_two = _observation(
        "news-1", B13C.KIND_NEWS_ARTICLE, published_s=100, received_s=500, monotonic=5_000,
        raw_payload="second corrected wording of the synthetic article",
        revision_kind=B13C.REVISION_EDIT, revision_index=2,
        supersedes=edit["observation_sha256"],
        mapping=B13C.exact_binding(mint=MINT_A, binding_evidence="mint address quoted in body"),
        evidence={"headline": "synthetic headline", "url": "https://example.invalid/news-1"})
    corpus["corrected_article"] = [create, edit, edit_two]

    # 2. A social post later deleted. A decision before the deletion arrived saw the post, and the
    #    deletion must not reach back and remove it.
    post = _observation(
        "post-1", B13C.KIND_SOCIAL_POST, published_s=200, received_s=205, monotonic=2_050,
        raw_payload="synthetic post text",
        mapping=B13C.exact_binding(account="AcctSynthetic1111111111111111111111111111",
                                   binding_evidence="account address in the post metadata"),
        evidence={"author_handle": "@synthetic", "text": "synthetic post text"})
    deletion = _observation(
        "post-1", B13C.KIND_SOCIAL_POST, published_s=200, received_s=400, monotonic=4_000,
        raw_payload="synthetic post text",
        revision_kind=B13C.REVISION_DELETE, revision_index=1,
        supersedes=post["observation_sha256"],
        mapping=B13C.exact_binding(account="AcctSynthetic1111111111111111111111111111",
                                   binding_evidence="account address in the post metadata"),
        evidence={"deletion_notice": "the provider reported this item withdrawn"})
    corpus["deleted_post"] = [post, deletion]

    # 3. Published long before t0 but fetched long after it. The backfill case, and the reason the
    #    rule needs both clocks.
    corpus["backfilled_article"] = [_observation(
        "news-2", B13C.KIND_NEWS_ARTICLE, published_s=50, received_s=9_000, monotonic=90_000,
        raw_payload="an article published early and fetched much later",
        mapping=B13C.exact_binding(mint=MINT_A, binding_evidence="mint address quoted in body"))]

    # 4. A provider item dated in the future relative to its own receipt.
    corpus["future_dated_post"] = [_observation(
        "post-2", B13C.KIND_SOCIAL_POST, published_s=8_000, received_s=210, monotonic=2_100,
        raw_payload="a post the provider dates in the future",
        mapping=B13C.exact_binding(account="AcctSynthetic2222222222222222222222222222",
                                   binding_evidence="account address in the post metadata"))]

    # 5. A ticker collision: the same symbol, two different mints, and no address anywhere.
    corpus["ticker_collision"] = [
        _observation("post-3", B13C.KIND_SOCIAL_POST, published_s=150, received_s=160,
                     monotonic=1_600, raw_payload=f"a post mentioning {SHARED_TICKER}",
                     mapping=B13C.ticker_mapping(SHARED_TICKER, mint=MINT_A,
                                                 detail="symbol match only"),
                     evidence={"text": f"a post mentioning {SHARED_TICKER}"}),
        _observation("post-4", B13C.KIND_SOCIAL_POST, published_s=155, received_s=165,
                     monotonic=1_650, raw_payload=f"another post mentioning {SHARED_TICKER}",
                     mapping=B13C.ticker_mapping(SHARED_TICKER, mint=MINT_B,
                                                 detail="symbol match only"),
                     evidence={"text": f"another post mentioning {SHARED_TICKER}"}),
    ]

    # 6. A provider's bare claim of a mapping, unchecked.
    corpus["claimed_mapping"] = [_observation(
        "meta-1", B13C.KIND_TOKEN_METADATA, published_s=90, received_s=95, monotonic=950,
        raw_payload="synthetic metadata record",
        mapping=B13C.claimed_mapping(mint=MINT_A, detail="the provider asserts this mapping"))]

    # 7. A date with no time: a whole-day claim, usable only from the end of the day it covers.
    day = 86_400 * SECOND
    corpus["day_precision_article"] = [_observation(
        "news-3", B13C.KIND_NEWS_ARTICLE, published_s=0, received_s=120, monotonic=1_200,
        publication_time=B13C.time_claim(BASE, day, "a date with no time of day"),
        raw_payload="an article dated to the day only",
        mapping=B13C.exact_binding(mint=MINT_A, binding_evidence="mint address quoted in body"))]

    # 8. A timestamp we have but cannot bound at all.
    corpus["ambiguous_article"] = [_observation(
        "news-4", B13C.KIND_NEWS_ARTICLE, published_s=0, received_s=130, monotonic=1_300,
        publication_time=B13C.ambiguous_time(BASE, "a local time with no zone stated"),
        raw_payload="an article whose timestamp has no timezone",
        mapping=B13C.exact_binding(mint=MINT_A, binding_evidence="mint address quoted in body"))]

    # 9. Two quotes in different units. Comparing them without a rate is the mixing error.
    corpus["quotes"] = [
        _observation("quote-1", B13C.KIND_FINANCIAL_QUOTE, published_s=180, received_s=181,
                     monotonic=1_810, raw_payload="synthetic quote in lamports",
                     mapping=B13C.exact_binding(mint=MINT_A, binding_evidence="mint in the quote"),
                     measurement={"value_numerator": 123_456_789, "value_denominator": 1,
                                  "unit": "lamports", "quote_asset": "SOL",
                                  "effective_time": B13C.time_claim(
                                      BASE + 180 * SECOND, 0, "provider effective instant"),
                                  "measurement_basis": "last traded price"}),
        _observation("quote-2", B13C.KIND_FINANCIAL_QUOTE, published_s=182, received_s=183,
                     monotonic=1_830, raw_payload="synthetic quote in micro-USD",
                     mapping=B13C.exact_binding(mint=MINT_A, binding_evidence="mint in the quote"),
                     measurement={"value_numerator": 4_200, "value_denominator": 1,
                                  "unit": "micro_usd", "quote_asset": "USD",
                                  "effective_time": B13C.time_claim(
                                      BASE + 182 * SECOND, 0, "provider effective instant"),
                                  "measurement_basis": "last traded price"}),
    ]

    # 10. A configuration fact, retained as a hash only under an unknown licence.
    corpus["config_fact"] = [_observation(
        "config-1", B13C.KIND_CONFIG_FACT, published_s=10, received_s=12, monotonic=120,
        raw_payload=None, payload_sha256=hashlib.sha256(b"synthetic config").hexdigest(),
        payload_reference="reference-only handle to a synthetic config record",
        license_status=B13C.LICENSE_UNKNOWN, retention_status=B13C.RETENTION_HASH_ONLY,
        mapping=B13C.unmapped("a global configuration fact belongs to no token"))]

    # 11. A second provider reporting the same underlying story under its own identifier. Two
    #     observations, never merged: an identifier belongs to the provider that issued it.
    corpus["second_provider"] = [_observation(
        "beta-77", B13C.KIND_NEWS_ARTICLE, published_s=100, received_s=115, monotonic=1_150,
        provider="provider-beta", fetch_session_id="session-2",
        raw_payload="a second provider's wording of the same synthetic story",
        mapping=B13C.exact_binding(mint=MINT_A, binding_evidence="mint address quoted in body"))]

    return corpus


def decision_instant(seconds_after_base, slot=430_000_000):
    return {"wall_ns": BASE + seconds_after_base * SECOND,
            "coordinate": {"slot": slot, "transaction_index": 0, "outer_index": 0,
                           "inner_index": 0},
            "wall_clock_provenance": "synthetic fixture instant; no slot-to-wall join was performed"}


# The instants the report replays. Chosen to straddle each seam rather than to make the numbers
# look good: before the first correction, between the two, after the deletion, and late.
REPLAY_INSTANTS = (150, 250, 450, 600, 1_000)


def check():
    """Structural integrity only. Every number below counts records or checks, never content."""
    corpus = build_fixture_corpus()
    everything = [observation for group in corpus.values() for observation in group]
    # A revision chain is every observation sharing one PROVIDER IDENTIFIER — not whatever the
    # fixture happened to group together. Two quotes from one provider are two items, and validating
    # them as one chain would be asserting a relationship the identifiers deny.
    chains = {}
    for observation in B13C.ordered_observations(everything):
        chains.setdefault(B13C.chain_key(observation), []).append(observation)
    report = {
        "schema_version": B13C.SCHEMA_VERSION,
        "availability_rule": B13C.AVAILABILITY_RULE,
        "network_collection_performed": False,
        "vendors_selected": [],
        "llm_in_decision_path": B13C.LLM_IN_DECISION_PATH,
        "observations": len(everything),
        "chains": len(chains),
        "observations_by_kind": {kind: 0 for kind in B13C.OBSERVATION_KINDS},
        "observations_by_mapping_status": {status: 0 for status in B13C.MAPPING_STATUSES},
        "observations_by_revision_kind": {kind: 0 for kind in B13C.REVISION_KINDS},
        "observations_by_retention": {status: 0 for status in B13C.RETENTION_STATUSES},
        "instants_replayed": 0,
        "eligibility_by_reason": {code: 0 for code in B13C.INELIGIBILITY_CODES},
        "eligible_observation_instants": 0,
        "ineligible_observation_instants": 0,
        "chains_validated": 0,
        "identifier_collisions_refused": False,
        "order_independent": 0,
        "hashes_stable": 0,
        "backfill_refused_at_every_instant": 0,
        "deletion_did_not_rewrite_history": 0,
        "prior_versions_preserved": 0,
        "unit_mixing_refused": False,
        "refusals_verified": {},
        "content_reported": False,
        "content_reported_reason":
            "this ledger records that an item existed and when we learned of it; publishing what it "
            "said would put unlicensed content in a report and invite a transform nobody registered",
        "derived_quantities_computed": [],
        "burned_corpus_touched": False,
        "b11a_touched": False,
        "errors": [],
    }
    for observation in everything:
        report["observations_by_kind"][observation["identity"]["observation_kind"]] += 1
        report["observations_by_mapping_status"][observation["mapping"]["status"]] += 1
        report["observations_by_revision_kind"][observation["revision"]["revision_kind"]] += 1
        report["observations_by_retention"][observation["retention_status"]] += 1
        if B13C.observation_hash(observation) == observation["observation_sha256"]:
            report["hashes_stable"] += 1
        else:
            report["errors"].append({"observation": observation["identity"], "error": "hash drift"})

    for key, chain in sorted(chains.items()):
        try:
            B13C.assert_revision_chain(chain)
            report["chains_validated"] += 1
        except B10B.FreezeViolation as error:
            report["errors"].append({"chain": list(key), "error": str(error)[:200]})

    try:
        B13C.assert_no_identifier_collision(everything)
    except B10B.FreezeViolation:
        report["errors"].append({"error": "the synthetic corpus itself reuses an identifier"})
    # The collision refusal, exercised on a case built to trip it rather than asserted in prose.
    first = corpus["corrected_article"][0]
    twin = dict(first)
    twin["payload"] = dict(first["payload"], payload_sha256="0" * 64, raw_payload=None)
    twin["retention_status"] = B13C.RETENTION_HASH_ONLY
    twin["features"] = dict(first["features"], raw_payload_retained=False)
    twin["observation_sha256"] = B13C.observation_hash(twin)
    try:
        B13C.assert_no_identifier_collision(everything + [twin])
        report["errors"].append({"error": "a reused identifier with different content was accepted"})
    except B10B.FreezeViolation:
        report["identifier_collisions_refused"] = True

    backfilled = corpus["backfilled_article"][0]
    for seconds in REPLAY_INSTANTS:
        instant = decision_instant(seconds)
        report["instants_replayed"] += 1
        for observation in everything:
            reasons = B13C.ineligibility(observation, instant)
            if reasons:
                report["ineligible_observation_instants"] += 1
                for reason in reasons:
                    report["eligibility_by_reason"][reason["reason_code"]] += 1
            else:
                report["eligible_observation_instants"] += 1

        codes = {r["reason_code"] for r in B13C.ineligibility(backfilled, instant)}
        if B13C.A01_RECEIVED_AFTER_T0 in codes:
            report["backfill_refused_at_every_instant"] += 1
        else:
            report["errors"].append({"instant": seconds, "error": "a backfilled article was "
                                                                  "admitted"})

        # The deletion arrives at 400 s. Before that, as-of replay must still return the post.
        resolved = B13C.as_of(corpus["deleted_post"], instant)
        deleted = B13C.is_absent(resolved) and resolved.reason == B13C.ABSENT_DELETED
        if deleted == (seconds >= 400):
            report["deletion_did_not_rewrite_history"] += 1
        else:
            report["errors"].append({"instant": seconds,
                                     "error": "a deletion changed what an earlier decision saw"})

        # Every version received by this instant is still there, and the current one is the last.
        history = B13C.version_history_as_of(corpus["corrected_article"], instant)
        expected = len([o for o in corpus["corrected_article"]
                        if not B13C.ineligibility(o, instant)])
        current = B13C.as_of(corpus["corrected_article"], instant)
        if len(history) == expected and (
                B13C.is_absent(current) if not history else current is history[-1]):
            report["prior_versions_preserved"] += 1
        else:
            report["errors"].append({"instant": seconds, "error": "as-of replay lost a version"})

        shuffled = list(reversed(everything))
        if (B10B.canonical_json(B13C.ordered_observations(shuffled))
                == B10B.canonical_json(B13C.ordered_observations(everything))):
            report["order_independent"] += 1
        else:
            report["errors"].append({"instant": seconds, "error": "order dependent"})

    try:
        B13C.assert_comparable(corpus["quotes"][0]["measurement"],
                               corpus["quotes"][1]["measurement"])
        report["errors"].append({"error": "two quotes in different units compared cleanly"})
    except B10B.FreezeViolation:
        report["unit_mixing_refused"] = True

    for name in ("sentiment", "embedding", "engagement_score", "source_credibility", "market_cap",
                 "call_language_model"):
        try:
            getattr(B13C, name)("anything")
            report["refusals_verified"][name] = False
            report["errors"].append({"error": f"{name} returned instead of refusing"})
        except B13C.DerivedQuantityRefused:
            report["refusals_verified"][name] = True

    digest = hashlib.sha256()
    for observation in B13C.ordered_observations(everything):
        digest.update(observation["observation_sha256"].encode())
    report["determinism"] = {"observations_hashed": len(everything),
                             "observation_hash_chain_sha256": digest.hexdigest()}
    return report


def gate_failures(report):
    """Why this run does not pass the gate. Pure, so the gate's own logic can be tested.

    Extracted rather than inlined: a gate whose conditions can only be exercised by running the
    whole corpus is a gate nobody can show works.
    """
    failures = []
    if report["errors"]:
        failures.append(f"{len(report['errors'])} integrity errors: {report['errors'][:5]}")
    if report["hashes_stable"] != report["observations"]:
        failures.append(f"only {report['hashes_stable']} of {report['observations']} hashes stable")
    if report["chains_validated"] != report["chains"]:
        failures.append(
            f"only {report['chains_validated']} of {report['chains']} chains validated")
    replayed = report["instants_replayed"]
    for field in ("order_independent", "backfill_refused_at_every_instant",
                  "deletion_did_not_rewrite_history", "prior_versions_preserved"):
        if report[field] != replayed:
            failures.append(f"{field} held for only {report[field]} of {replayed} instants")
    if not report["identifier_collisions_refused"]:
        failures.append("a reused provider identifier with different content was accepted")
    if not report["unit_mixing_refused"]:
        failures.append("measurements in different units were treated as comparable")
    if not all(report["refusals_verified"].values()):
        failures.append("a computation that must fail closed did not")
    if report["derived_quantities_computed"]:
        failures.append("this gate may not compute a derived quantity")
    if report["network_collection_performed"] or report["vendors_selected"]:
        failures.append("this pass performs no collection and selects no vendor")
    if report["llm_in_decision_path"]:
        failures.append("no language model may be in the decision path")
    return failures


def assert_clean():
    report = check()
    failures = gate_failures(report)
    if failures:
        raise B13C.ObservationRefused("; ".join(failures))
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
        print(f"ObservationRefused: {error}", file=sys.stderr)
        sys.exit(2)
