"""B13a — point-in-time actor and token history.

A history is the most dangerous artifact in this pipeline, because it is the one that looks
harmless. Every figure in it is about the past, so nobody thinks to check the boundary — and one
event on the wrong side of t0 turns a feature into a peek at the answer, silently, in a field that
will still be there three phases later.

So the tests here are about the boundary, the naming that keeps a lower bound from being read as a
total, and the eight other ways this specific shape of thing goes wrong.
"""
import copy
import importlib.util
import json
import pathlib
import random
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B13A = _load("b13a_history", "b13a_history.py")
B10B = B13A.B10B

CREATOR = "CreatorAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
OTHER_CREATOR = "CreatorBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
DEPLOYER = "DeployerCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
USER = "UserDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD"
FUNDER = "FunderEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE"
SUBJECT_MINT = "MintSubject11111111111111111111111111111111"
PRIOR_MINT = "MintPrior2222222222222222222222222222222222"


def event(kind, slot, *, tx=0, outer=0, inner=-1, source="s", **fields):
    record = {"kind": kind, "slot": slot, "transaction_index": tx, "outer_index": outer,
              "inner_index": inner,
              "source_sha256": (source * 64)[:64]}
    record.update(fields)
    return record


def launch(slot, mint, creator=CREATOR, create_user=None, **kw):
    return event(B13A.EVENT_LAUNCH, slot, mint=mint, bonding_curve="Curve" + mint[4:],
                 creator=creator, create_user=create_user or creator, **kw)


def trade(slot, mint, user, *, is_buy=True, quote=1_000_000, tokens=10, **kw):
    return event(B13A.EVENT_TRADE, slot, mint=mint, user=user, is_buy=is_buy,
                 quote_lamports=quote, token_units=tokens, **kw)


def transfer(slot, sender, recipient, lamports, **kw):
    return event(B13A.EVENT_TRANSFER, slot, from_address=sender, to_address=recipient,
                 lamports=lamports, **kw)


def coverage(**overrides):
    base = {"first_slot": 100, "last_slot": 900, "source_population": "synthetic fixture",
            "left_truncated": True, "right_truncated": False, "complete": False,
            "provenance_sha256": "c" * 64}
    base.update(overrides)
    return base


T0 = event(B13A.EVENT_TRADE, 500, outer=4, mint=SUBJECT_MINT, user=USER, is_buy=True,
           quote_lamports=1, token_units=1)

# The bonding curve must be the one the launch event names; the subject-consistency check caught
# this fixture disagreeing with itself the moment it was added.
SUBJECT = {"mint": SUBJECT_MINT, "creator": CREATOR,
           "bonding_curve": "Curve" + SUBJECT_MINT[4:], "user": USER}


def stream():
    """A window holding: a prior launch that completed, the subject launch with a creator buy,
    later trades, a funding edge in and one out, and one event after t0."""
    return [
        transfer(150, FUNDER, CREATOR, 2_000_000_000, source="t"),
        launch(200, PRIOR_MINT, source="p"),
        trade(210, PRIOR_MINT, CREATOR, quote=5_000_000, tokens=70, source="q"),
        event(B13A.EVENT_COMPLETION, 300, mint=PRIOR_MINT, source="r"),
        launch(400, SUBJECT_MINT, source="u"),
        trade(400, SUBJECT_MINT, CREATOR, outer=4, quote=50_000_000, tokens=900, source="v"),
        trade(450, SUBJECT_MINT, USER, quote=3_000_000, tokens=40, source="w"),
        transfer(460, CREATOR, FUNDER, 100_000, source="x"),
        # After t0: must never appear in any figure.
        trade(600, SUBJECT_MINT, USER, is_buy=False, quote=9_000_000, tokens=80, source="y"),
    ]


def build(events=None, subject=None, t0=None, cover=None):
    return B13A.build_as_of_history(
        stream() if events is None else events,
        SUBJECT if subject is None else subject,
        T0 if t0 is None else t0,
        coverage() if cover is None else cover)


class BoundaryTests(unittest.TestCase):
    """One event on the wrong side of t0 turns a feature into a peek at the answer."""

    def test_an_event_at_exactly_t0_is_included(self):
        events = stream() + [trade(500, SUBJECT_MINT, USER, outer=4, quote=7_000_000, tokens=1,
                                   source="z")]
        # Same coordinate as t0 itself, distinguished only by its payload.
        token = build(events)["sections"]["token"]["features"]
        self.assertEqual(token["prior_quote_in_lamports_observed"], 50_000_000 + 3_000_000 + 7_000_000)

    def test_an_event_one_coordinate_after_t0_is_excluded(self):
        leak = trade(500, SUBJECT_MINT, USER, outer=4, inner=0, quote=999_000_000, tokens=1,
                     source="z")
        self.assertGreater(B10B.canonical_key(leak), B10B.canonical_key(T0))
        base = build()["sections"]["token"]["features"]
        leaked = build(stream() + [leak])["sections"]["token"]["features"]
        self.assertEqual(base, leaked, "one inner index later is still the future")

    def test_the_event_after_t0_in_the_fixture_never_appears(self):
        token = build()["sections"]["token"]["features"]
        self.assertEqual(token["prior_sell_count_observed"], 0)
        self.assertEqual(token["prior_quote_out_lamports_observed"], 0)

    def test_a_later_slot_is_excluded_however_large_the_amount(self):
        whale = trade(501, SUBJECT_MINT, USER, quote=10 ** 15, tokens=1, source="z")
        self.assertEqual(build()["history_sha256"],
                         build(stream() + [whale])["history_sha256"])

    def test_the_boundary_rule_is_published_on_every_record(self):
        record = build()
        self.assertEqual(record["boundary_rule"], B13A.BOUNDARY_RULE)
        self.assertIn("insertion order is never consulted", record["boundary_rule"])
        record["boundary_rule"] = "whatever seems reasonable"
        with self.assertRaisesRegex(B13A.HistoryRefused, "boundary rule"):
            B13A.assert_history(record)

    def test_at_or_before_is_inclusive_and_nothing_else(self):
        key = (500, 0, 4, -1)
        events, _ = B13A.ordered_events(stream())
        visible = B13A.at_or_before(events, key)
        self.assertTrue(all(B10B.canonical_key(e) <= key for e in visible))
        self.assertEqual(len(visible), len(events) - 1)


class PastOutcomeTests(unittest.TestCase):
    """A completion recorded after t0 has not happened as far as this decision is concerned."""

    def test_a_completion_before_t0_counts(self):
        self.assertEqual(
            build()["sections"]["creator"]["features"]["prior_completion_count_observed"], 1)

    def test_a_completion_after_t0_does_not_count(self):
        events = [e for e in stream() if e["kind"] != B13A.EVENT_COMPLETION]
        events.append(event(B13A.EVENT_COMPLETION, 700, mint=PRIOR_MINT, source="r"))
        self.assertEqual(
            build(events)["sections"]["creator"]["features"]["prior_completion_count_observed"], 0)

    def test_the_subject_token_completing_after_t0_is_not_reported_as_completed(self):
        events = stream() + [event(B13A.EVENT_COMPLETION, 800, mint=SUBJECT_MINT, source="r")]
        self.assertFalse(build(events)["sections"]["token"]["features"]["completed_before_t0"])

    def test_the_subject_token_completing_before_t0_is_reported(self):
        events = stream() + [event(B13A.EVENT_COMPLETION, 480, mint=SUBJECT_MINT, source="r")]
        self.assertTrue(build(events)["sections"]["token"]["features"]["completed_before_t0"])


class SelfInclusionTests(unittest.TestCase):

    def test_the_subject_launch_is_not_one_of_its_creators_prior_launches(self):
        creator = build()["sections"]["creator"]["features"]
        self.assertEqual(creator["prior_launch_count_observed"], 1)
        self.assertNotIn(SUBJECT_MINT,
                         build()["sections"]["creator"]["evidence"]["prior_launch_mints"])

    def test_a_launch_after_the_subject_launch_is_not_prior_either(self):
        events = stream() + [launch(450, "MintLater333333333333333333333333333333333",
                                    source="l")]
        self.assertEqual(
            build(events)["sections"]["creator"]["features"]["prior_launch_count_observed"], 1)

    def test_another_creators_completion_is_not_counted(self):
        """A completion is a fact about a token, and a token belongs to one creator. Counting
        every completion in the window would hand every creator the whole window's graduations."""
        events = stream() + [
            launch(180, "MintOther44444444444444444444444444444444",
                   creator=OTHER_CREATOR, source="o"),
            event(B13A.EVENT_COMPLETION, 250, mint="MintOther44444444444444444444444444444444",
                  source="n"),
        ]
        creator = build(events)["sections"]["creator"]["features"]
        self.assertEqual(creator["prior_completion_count_observed"], 1)

    def test_another_creators_launches_are_not_counted(self):
        events = stream() + [launch(150, "MintOther44444444444444444444444444444444",
                                    creator=OTHER_CREATOR, source="o")]
        self.assertEqual(
            build(events)["sections"]["creator"]["features"]["prior_launch_count_observed"], 1)


class LowerBoundTests(unittest.TestCase):
    """A count over a bounded window is not a total, and must not be readable as one."""

    def test_every_count_is_named_observed(self):
        for section in B13A.SECTIONS:
            for name in B13A.FEATURE_FIELDS[section]:
                with self.subTest(section=section, name=name):
                    if name == "counts_are_lower_bounds":
                        continue          # a flag about the counts, not a count
                    if "count" in name or "lamports" in name or "units" in name:
                        self.assertTrue(
                            name.endswith("_observed"),
                            f"{name} states a total; over a bounded window there are none")

    def test_no_field_states_a_total(self):
        for section in B13A.SECTIONS:
            for name in B13A.FEATURE_FIELDS[section]:
                with self.subTest(name=name):
                    self.assertNotIn("total_", name)
                    self.assertFalse(name.startswith("all_"))

    def test_a_truncated_window_says_its_counts_are_lower_bounds(self):
        record = build()
        for section in B13A.SECTIONS:
            self.assertTrue(record["sections"][section]["features"]["counts_are_lower_bounds"])

    def test_a_complete_window_says_its_counts_are_not(self):
        record = build(cover=coverage(left_truncated=False, right_truncated=False, complete=True))
        for section in B13A.SECTIONS:
            self.assertFalse(record["sections"][section]["features"]["counts_are_lower_bounds"])

    def test_a_section_disagreeing_with_coverage_is_refused(self):
        record = build()
        record["sections"]["creator"]["features"]["counts_are_lower_bounds"] = False
        with self.assertRaisesRegex(B13A.HistoryRefused, "lower bounds"):
            B13A.assert_history(record)

    def test_a_policy_needing_a_true_count_fails_closed_on_a_truncated_window(self):
        with self.assertRaisesRegex(B13A.HistoryRefused, "lower bound"):
            B13A.require_complete_history(build())

    def test_the_same_policy_passes_on_a_complete_window(self):
        self.assertTrue(B13A.require_complete_history(
            build(cover=coverage(left_truncated=False, right_truncated=False, complete=True))))

    def test_an_unseen_actor_is_marked_unseen_rather_than_reported_as_zero_activity(self):
        """Zero observed is a fact about the window. 'Never done this' is a claim about the world,
        and this module is never in a position to make it."""
        stranger = dict(SUBJECT, user="UserUnseenFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF")
        user = build(subject=stranger)["sections"]["user"]["features"]
        self.assertFalse(user["actor_seen_in_window"])
        self.assertEqual(user["prior_trade_count_observed"], 0)
        self.assertTrue(user["counts_are_lower_bounds"])
        self.assertIsNone(user["first_observed_trade_slot"])

    def test_coverage_cannot_claim_to_be_complete_and_truncated_at_once(self):
        with self.assertRaisesRegex(B13A.HistoryRefused, "complete while also truncated"):
            B13A.assert_coverage(coverage(complete=True, left_truncated=True))

    def test_every_coverage_field_is_required(self):
        for field in B13A.COVERAGE_FIELDS:
            with self.subTest(field=field):
                broken = {k: v for k, v in coverage().items() if k != field}
                with self.assertRaisesRegex(B13A.HistoryRefused, "does not state"):
                    B13A.assert_coverage(broken)


class IdentityLeakageTests(unittest.TestCase):

    def test_no_string_appears_in_any_feature_block(self):
        record = build()
        for section in B13A.SECTIONS:
            for name, value in record["sections"][section]["features"].items():
                with self.subTest(section=section, name=name):
                    self.assertNotIsInstance(value, str)
                    self.assertTrue(value is None or isinstance(value, (int, bool)))

    def test_a_string_smuggled_into_a_feature_block_is_refused(self):
        record = build()
        record["sections"]["creator"]["features"]["prior_launch_count_observed"] = CREATOR
        with self.assertRaisesRegex(B13A.HistoryRefused, "NO STRING MAY APPEAR"):
            B13A.assert_history(record)

    def test_identity_and_feature_blocks_are_disjoint_and_declared(self):
        for section in B13A.SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    set(B13A.IDENTITY_FIELDS[section]) & set(B13A.FEATURE_FIELDS[section]), set())
                self.assertTrue(B13A.assert_disjoint_contract(
                    section, B13A.IDENTITY_FIELDS[section], B13A.FEATURE_FIELDS[section]))

    def test_a_field_declared_as_both_an_identity_and_a_feature_is_refused(self):
        """With the shipped tuples this can never fire, so the check takes its field sets as
        arguments — a guard nobody can make fire is a guard nobody can show works."""
        with self.assertRaisesRegex(B13A.HistoryRefused, "both an identity and a feature"):
            B13A.assert_disjoint_contract("creator", ("creator",), ("creator", "x"))

    def test_an_added_feature_field_is_refused(self):
        record = build()
        record["sections"]["token"]["features"]["creator_hash_bucket"] = 7
        with self.assertRaisesRegex(B13A.HistoryRefused, "feature block is"):
            B13A.assert_history(record)

    def test_identities_are_present_where_they_belong(self):
        record = build()
        self.assertEqual(record["sections"]["creator"]["identity"]["creator"], CREATOR)
        self.assertEqual(record["sections"]["user"]["identity"]["user"], USER)
        self.assertEqual(record["sections"]["token"]["identity"]["mint"], SUBJECT_MINT)
        blob = json.dumps({s: record["sections"][s]["features"] for s in B13A.SECTIONS})
        for identity in (CREATOR, USER, SUBJECT_MINT, FUNDER):
            self.assertNotIn(identity, blob)


class RoleConfusionTests(unittest.TestCase):
    """The creator and the wallet that signed the launch are different fields and often different
    wallets. Conflating them attributes a stranger's launches to a creator."""

    def deployed(self):
        return [
            launch(200, PRIOR_MINT, creator=CREATOR, create_user=DEPLOYER, source="p"),
            launch(400, SUBJECT_MINT, creator=CREATOR, create_user=DEPLOYER, source="u"),
            trade(400, SUBJECT_MINT, CREATOR, outer=4, quote=50_000_000, tokens=900, source="v"),
            trade(410, PRIOR_MINT, DEPLOYER, quote=1_000_000, tokens=5, source="d"),
        ]

    def test_prior_launches_key_off_the_creator_not_the_signing_wallet(self):
        """Both launches were signed by DEPLOYER and created by CREATOR. Keying off the signer
        would still find two — so the count alone cannot distinguish the two implementations, and
        the discriminating case is a launch whose signer differs from another launch's signer."""
        events = self.deployed() + [
            launch(300, "MintThird5555555555555555555555555555555555",
                   creator=CREATOR, create_user=OTHER_CREATOR, source="e")]
        creator = build(events)["sections"]["creator"]["features"]
        self.assertEqual(creator["prior_launch_count_observed"], 2)
        self.assertEqual(
            sorted(build(events)["sections"]["creator"]["evidence"]["prior_launch_mints"]),
            sorted([PRIOR_MINT, "MintThird5555555555555555555555555555555555"]))

    def test_claiming_the_signing_wallet_as_the_creator_is_refused_outright(self):
        """Better than returning zeros: a history built on the wrong actor looks entirely normal."""
        with self.assertRaisesRegex(B13A.HistoryRefused, "launch names"):
            build(self.deployed(), subject=dict(SUBJECT, creator=DEPLOYER))

    def test_a_creator_buy_is_attributed_to_the_creator_not_the_signer(self):
        token = build(self.deployed())["sections"]["token"]["features"]
        self.assertTrue(token["launch_transaction_creator_buy_present"])
        self.assertEqual(token["launch_transaction_creator_buy_quote_lamports_observed"],
                         50_000_000)

    def test_a_launch_transaction_buy_by_the_signer_is_not_a_creator_buy(self):
        events = [
            launch(400, SUBJECT_MINT, creator=CREATOR, create_user=DEPLOYER, source="u"),
            trade(400, SUBJECT_MINT, DEPLOYER, outer=4, quote=50_000_000, tokens=900, source="v"),
        ]
        token = build(events)["sections"]["token"]["features"]
        self.assertEqual(token["launch_transaction_trade_count_observed"], 1)
        self.assertFalse(token["launch_transaction_creator_buy_present"])
        self.assertEqual(token["launch_transaction_creator_buy_quote_lamports_observed"], 0)

    def test_the_user_section_keys_off_the_trading_user(self):
        user = build()["sections"]["user"]["features"]
        self.assertEqual(user["prior_trade_count_observed"], 1)
        as_creator = build(subject=dict(SUBJECT, user=CREATOR))["sections"]["user"]["features"]
        self.assertEqual(as_creator["prior_trade_count_observed"], 2)


class FlowDirectionTests(unittest.TestCase):
    """Direction is the whole point. A net figure hides a wallet that cycled a hundred SOL."""

    def test_buy_and_sell_flows_are_kept_separate(self):
        events = [
            launch(400, SUBJECT_MINT, source="u"),
            trade(410, SUBJECT_MINT, USER, is_buy=True, quote=7_000_000, tokens=90, source="a"),
            trade(420, SUBJECT_MINT, USER, is_buy=False, quote=6_000_000, tokens=80, source="b"),
        ]
        user = build(events)["sections"]["user"]["features"]
        self.assertEqual(user["prior_quote_in_lamports_observed"], 7_000_000)
        self.assertEqual(user["prior_quote_out_lamports_observed"], 6_000_000)
        self.assertEqual(user["prior_token_in_units_observed"], 90)
        self.assertEqual(user["prior_token_out_units_observed"], 80)
        self.assertEqual(user["prior_buy_count_observed"], 1)
        self.assertEqual(user["prior_sell_count_observed"], 1)

    def test_funding_direction_is_not_reversible(self):
        funding = build()["sections"]["funding"]["features"]
        self.assertEqual(funding["inbound_lamports_observed"], 2_000_000_000)
        self.assertEqual(funding["outbound_lamports_observed"], 100_000)
        self.assertEqual(funding["inbound_edge_count_observed"], 1)
        self.assertEqual(funding["outbound_edge_count_observed"], 1)
        self.assertNotEqual(funding["inbound_lamports_observed"],
                            funding["outbound_lamports_observed"])

    def test_each_edge_publishes_its_own_direction_and_provenance(self):
        edges = build()["sections"]["funding"]["evidence"]["edges"]
        self.assertEqual([edge["direction"] for edge in edges], ["in", "out"])
        for edge in edges:
            self.assertTrue(edge["source_sha256"])
            self.assertEqual(set(edge["coordinate"]), set(B13A.COORDINATE_FIELDS))

    def test_a_transfer_to_itself_is_not_a_funding_edge(self):
        with self.assertRaisesRegex(B13A.HistoryRefused, "to itself"):
            B13A.assert_event(transfer(100, CREATOR, CREATOR, 5))

    def test_no_cluster_is_inferred(self):
        evidence = build()["sections"]["funding"]["evidence"]
        self.assertIn("clusters_not_inferred", evidence)
        blob = json.dumps(build())
        for forbidden in ("cluster_id", "cluster_confidence", "entity_id", "same_entity"):
            self.assertNotIn(forbidden, blob)


class EventStreamTests(unittest.TestCase):

    def test_a_duplicate_event_is_refused(self):
        duplicated = stream()
        duplicated.append(copy.deepcopy(duplicated[1]))
        with self.assertRaisesRegex(B13A.HistoryRefused, "duplicate"):
            B13A.ordered_events(duplicated)

    def test_two_events_at_one_coordinate_are_fine_when_they_differ(self):
        """Four transactions in the real artifact touch two curves at once; that is not a
        duplicate, and refusing it would refuse the corpus."""
        pair = [launch(400, SUBJECT_MINT, source="u"),
                launch(400, PRIOR_MINT, source="p")]
        ordered, digests = B13A.ordered_events(pair)
        self.assertEqual(len(ordered), 2)
        self.assertEqual(len(set(digests)), 2)

    def test_the_result_does_not_depend_on_the_order_events_arrive_in(self):
        baseline = build()["history_sha256"]
        for seed in range(8):
            shuffled = stream()
            random.Random(seed).shuffle(shuffled)
            with self.subTest(seed=seed):
                self.assertEqual(build(shuffled)["history_sha256"], baseline)

    def test_two_events_at_one_coordinate_order_deterministically(self):
        """Sorting by coordinate alone leaves ties to whatever order the caller happened to read
        rows in — the exact insertion-order dependence this module exists to remove."""
        collide = [
            launch(400, SUBJECT_MINT, source="u"),
            trade(400, SUBJECT_MINT, CREATOR, quote=11_000_000, tokens=1, source="a"),
            trade(400, SUBJECT_MINT, USER, quote=22_000_000, tokens=2, source="b"),
            trade(400, SUBJECT_MINT, USER, quote=33_000_000, tokens=3, source="c"),
        ]
        keys = {B10B.canonical_key(e) for e in collide[1:]}
        self.assertEqual(len(keys), 1, "the fixture must actually collide")
        baseline = None
        for seed in range(10):
            shuffled = list(collide)
            random.Random(seed).shuffle(shuffled)
            ordered, digests = B13A.ordered_events(shuffled)
            if baseline is None:
                baseline = digests
            with self.subTest(seed=seed):
                self.assertEqual(digests, baseline)

    def test_every_event_field_is_required(self):
        for kind, extra in B13A.EVENT_FIELDS.items():
            for field in B13A.COMMON_EVENT_FIELDS + extra:
                with self.subTest(kind=kind, field=field):
                    sample = {"kind": kind, "slot": 1, "transaction_index": 0, "outer_index": 0,
                              "inner_index": -1, "source_sha256": "a" * 64}
                    for name in extra:
                        sample[name] = (True if name == "is_buy"
                                        else 1 if name in ("quote_lamports", "token_units",
                                                           "lamports")
                                        else f"value_{name}")
                    del sample[field]
                    with self.assertRaises(B13A.HistoryRefused):
                        B13A.assert_event(sample)

    def test_an_undeclared_event_field_is_refused(self):
        with self.assertRaisesRegex(B13A.HistoryRefused, "undeclared fields"):
            B13A.assert_event(dict(launch(100, PRIOR_MINT), hint="looks useful"))

    def test_an_unknown_event_kind_is_refused(self):
        with self.assertRaisesRegex(B13A.HistoryRefused, "is not one of"):
            B13A.assert_event(dict(launch(100, PRIOR_MINT), kind="rumour"))


class SourceHashTests(unittest.TestCase):
    """A claim about the past that cannot name its source is an assertion."""

    def test_an_event_without_a_source_hash_is_refused(self):
        broken = launch(100, PRIOR_MINT)
        broken["source_sha256"] = ""
        with self.assertRaisesRegex(B13A.HistoryRefused, "source_sha256"):
            B13A.assert_event(broken)

    def test_changing_one_source_hash_changes_the_chain_and_the_history(self):
        baseline = build()
        drifted = stream()
        drifted[1] = dict(drifted[1], source_sha256="0" * 64)
        moved = build(drifted)
        self.assertNotEqual(baseline["source_hash_chain_sha256"],
                            moved["source_hash_chain_sha256"])
        self.assertNotEqual(baseline["history_sha256"], moved["history_sha256"])

    def test_the_chain_covers_only_events_inside_the_boundary(self):
        """An event after t0 must not even reach the provenance chain, or the chain would prove
        the history saw something it did not use."""
        self.assertEqual(build()["source_hash_chain_sha256"],
                         build(stream() + [trade(700, SUBJECT_MINT, USER, source="z")])[
                             "source_hash_chain_sha256"])


class RecordContractTests(unittest.TestCase):

    def test_the_record_is_deterministic_and_self_hashing(self):
        first, second = build(), build()
        self.assertEqual(B10B.canonical_json(first), B10B.canonical_json(second))
        self.assertEqual(first["history_sha256"], B13A.history_hash(first))

    def test_an_undeclared_top_level_field_is_refused(self):
        with self.assertRaisesRegex(B13A.HistoryRefused, "undeclared fields"):
            B13A.assert_history(dict(build(), extra="useful"))

    def test_a_missing_top_level_field_is_refused(self):
        for field in B13A.HISTORY_FIELDS:
            with self.subTest(field=field):
                trimmed = {k: v for k, v in build().items() if k != field}
                with self.assertRaisesRegex(B13A.HistoryRefused, "does not carry"):
                    B13A.assert_history(trimmed)

    def test_a_subject_without_a_mint_or_creator_is_refused(self):
        for field in ("mint", "creator"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(B13A.HistoryRefused, f"non-empty {field}"):
                    build(subject={k: v for k, v in SUBJECT.items() if k != field})

    def test_a_subject_naming_the_wrong_creator_is_refused(self):
        """Otherwise the caller gets a perfectly well-formed history full of zeros, which is the
        most convincing possible way to be wrong."""
        with self.assertRaisesRegex(B13A.HistoryRefused, "launch names"):
            build(subject=dict(SUBJECT, creator=OTHER_CREATOR))

    def test_a_subject_naming_the_wrong_bonding_curve_is_refused(self):
        with self.assertRaisesRegex(B13A.HistoryRefused, "bonding curve"):
            build(subject=dict(SUBJECT, bonding_curve="CurveWrong"))

    def test_a_subject_whose_launch_predates_the_window_is_allowed(self):
        """That is coverage, not an error: the launch may simply be older than the corpus."""
        events = [e for e in stream() if not (e["kind"] == B13A.EVENT_LAUNCH
                                              and e["mint"] == SUBJECT_MINT)]
        record = build(events)
        self.assertFalse(record["sections"]["token"]["features"]["launch_observed_in_window"])
        self.assertIsNone(record["sections"]["token"]["features"]["launch_slot"])

    def test_the_as_of_coordinate_is_published(self):
        record = build()
        self.assertEqual(record["as_of"],
                         {field: T0[field] for field in B13A.COORDINATE_FIELDS})

    def test_no_model_threshold_or_cluster_appears_anywhere(self):
        """Scanned over CODE ONLY. The module's prose names the things it refuses to do, so a
        scanner that read comments would report the strictest file as the worst one."""
        import re
        source = (ROOT / "scripts" / "b13a_history.py").read_text()
        code = re.sub(r'"""!?.*?"""', " ", source, flags=re.S)
        code = re.sub(r"^\s*#.*$", " ", code, flags=re.M).lower()
        for forbidden in ("sklearn", "numpy", "np.", "def fit", "threshold =", "cluster_id",
                          "def predict", "score("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class CorpusRunnerTests(unittest.TestCase):
    """The runner exists to check plumbing, and must be unable to publish a finding."""

    RUNNER = ROOT / "scripts" / "b13a_history_corpus.py"

    def test_it_declares_that_it_reports_no_feature_value(self):
        source = self.RUNNER.read_text()
        self.assertIn('"feature_values_reported": False', source)
        self.assertIn("no feature value, no distribution", source)

    def test_it_does_not_touch_b11a(self):
        source = self.RUNNER.read_text().lower()
        for forbidden in ("435569150", "437211659", "b11a_fresh", "b11a_window_freeze"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_it_declares_its_window_incomplete(self):
        source = self.RUNNER.read_text()
        self.assertIn('"left_truncated": True, "right_truncated": True, "complete": False', source)


if __name__ == "__main__":
    unittest.main()
