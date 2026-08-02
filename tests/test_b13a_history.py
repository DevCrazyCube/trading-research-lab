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


def accounting(**overrides):
    """A fully resolved decode accounting: every System instruction placed, nothing unresolved."""
    base = {"transactions_required": 3, "transactions_with_body": 3,
            "transactions_missing_body": 0, "transactions_missing_coordinate": 0,
            "system_instructions_total": 5, "decoded_moving": 3, "decoded_non_moving": 2,
            "undecodable": 0, "edges_emitted": 2, "moving_self_transfer": 1,
            "moving_without_addresses": 0, "unresolved": []}
    base.update(overrides)
    return base


def unresolved_item(reason=None, slot=150, tx=0, outer=0, inner=-1, detail="synthetic failure"):
    return {"reason_code": reason or B13A.D01_UNDECODABLE_SYSTEM_PAYLOAD,
            "coordinate": {"slot": slot, "transaction_index": tx, "outer_index": outer,
                           "inner_index": inner},
            "detail": detail}


def coverage(**overrides):
    base = {"first_slot": 100, "last_slot": 900, "source_population": "synthetic fixture",
            "left_truncated": True, "right_truncated": False, "complete": False,
            "provenance_sha256": "c" * 64, "decode_accounting": accounting()}
    base.update(overrides)
    return base


def complete_coverage(**overrides):
    base = coverage(left_truncated=False, right_truncated=False, complete=True)
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
        record = build(cover=complete_coverage())
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
        self.assertTrue(B13A.require_complete_history(build(cover=complete_coverage())))

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


class DecodeCompletenessTests(unittest.TestCase):
    """The seam where absence of evidence becomes evidence of absence.

    A funding edge that could not be decoded looks exactly like a funding edge that does not exist.
    Window geometry cannot tell the two apart, so untruncated geometry alone must never be allowed
    to mean complete.
    """

    def test_the_accounting_partition_must_sum(self):
        cases = {
            "transactions": accounting(transactions_with_body=2),
            "instructions": accounting(decoded_non_moving=1),
            "lamport movements": accounting(edges_emitted=1),
        }
        for label, broken in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(B13A.HistoryRefused):
                    B13A.assert_decode_accounting(broken)

    def test_a_resolved_accounting_passes(self):
        self.assertTrue(B13A.assert_decode_accounting(accounting()))

    def test_every_accounting_field_is_required(self):
        for field in B13A.DECODE_ACCOUNTING_FIELDS:
            with self.subTest(field=field):
                broken = {k: v for k, v in accounting().items() if k != field}
                with self.assertRaisesRegex(B13A.HistoryRefused, "does not state"):
                    B13A.assert_decode_accounting(broken)

    def test_the_unresolved_list_must_match_the_counts(self):
        with self.assertRaisesRegex(B13A.HistoryRefused, "unresolved items recorded"):
            B13A.assert_decode_accounting(accounting(undecodable=1, system_instructions_total=6))

    def test_every_unresolved_item_carries_a_coordinate_and_a_reason(self):
        base = accounting(undecodable=1, system_instructions_total=6,
                          unresolved=[unresolved_item()])
        self.assertTrue(B13A.assert_decode_accounting(base))
        for mangle in ({"reason_code": "D99_invented"}, {"detail": ""},
                       {"coordinate": {"slot": 1}}):
            with self.subTest(mangle=sorted(mangle)):
                broken = accounting(undecodable=1, system_instructions_total=6,
                                    unresolved=[dict(unresolved_item(), **mangle)])
                with self.assertRaises(B13A.HistoryRefused):
                    B13A.assert_decode_accounting(broken)

    def test_untruncated_geometry_alone_cannot_claim_completeness(self):
        """The exact defect this pass closed: a window with perfect geometry and a payload that
        would not decode used to publish complete, and a missing edge then reads as no funding."""
        with self.assertRaisesRegex(B13A.HistoryRefused, "Untruncated geometry is not completeness"):
            B13A.assert_coverage(complete_coverage(
                decode_accounting=accounting(undecodable=1, system_instructions_total=6,
                                             unresolved=[unresolved_item()])))

    def test_a_history_with_no_decode_accounting_is_refused(self):
        with self.assertRaisesRegex(B13A.HistoryRefused, "does not state"):
            B13A.assert_coverage({k: v for k, v in coverage().items()
                                  if k != "decode_accounting"})

    def test_coverage_validates_the_accounting_it_carries(self):
        """Requiring the field is not the same as checking it. A coverage carrying an accounting
        whose buckets do not sum must be refused by `assert_coverage` itself."""
        with self.assertRaisesRegex(B13A.HistoryRefused, "instruction accounting sums"):
            B13A.assert_coverage(coverage(decode_accounting=accounting(decoded_non_moving=1)))

    def test_an_absent_accounting_is_its_own_completeness_failure(self):
        """Reached by a hand-built record rather than a built one, because `assert_coverage`
        refuses to let a built record get here — which is the point of having both checks."""
        record = build()
        record["coverage"] = {k: v for k, v in record["coverage"].items()
                              if k != "decode_accounting"}
        codes = [f["reason_code"] for f in B13A.completeness_failures(record)]
        self.assertIn(B13A.C03_DECODE_ACCOUNTING_ABSENT, codes)
        with self.assertRaisesRegex(B13A.HistoryRefused, "C03_decode_accounting_absent"):
            B13A.require_complete_history(record)

    def test_each_kind_of_incompleteness_reports_its_own_code(self):
        """A generic failure tells an operator nothing about what to fix, so the codes have to be
        distinguishable and not merely present in the declared set."""
        cases = {
            B13A.C01_WINDOW_LEFT_TRUNCATED: coverage(left_truncated=True, right_truncated=False),
            B13A.C02_WINDOW_RIGHT_TRUNCATED: coverage(left_truncated=False, right_truncated=True),
        }
        for expected, cover in cases.items():
            with self.subTest(expected=expected):
                codes = [f["reason_code"] for f in B13A.completeness_failures(build(cover=cover))]
                self.assertEqual(codes, [expected])

    def test_an_unresolved_instruction_at_or_before_t0_poisons_the_subject(self):
        poisoned = complete_coverage(
            complete=False,
            decode_accounting=accounting(
                undecodable=1, system_instructions_total=6,
                unresolved=[unresolved_item(slot=450)]))
        record = build(cover=poisoned)
        codes = [f["reason_code"] for f in B13A.completeness_failures(record)]
        self.assertEqual(codes, [B13A.C04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0])
        with self.assertRaisesRegex(B13A.HistoryRefused, "C04_unresolved"):
            B13A.require_complete_history(record)

    def test_an_unresolved_instruction_after_t0_cannot_poison_the_subject(self):
        """A failure at a coordinate after this decision cannot have removed anything the decision
        could have seen. Letting it fail the subject would make one late corruption unusable
        evidence for every earlier decision in the window."""
        later = complete_coverage(
            complete=False,
            decode_accounting=accounting(
                undecodable=1, system_instructions_total=6,
                unresolved=[unresolved_item(slot=800)]))
        record = build(cover=later)
        self.assertEqual(B13A.completeness_failures(record), [])
        self.assertTrue(B13A.require_complete_history(record))

    def test_the_boundary_for_poisoning_is_inclusive_at_t0(self):
        at_t0 = unresolved_item(slot=500, tx=0, outer=4, inner=-1)
        one_after = unresolved_item(slot=500, tx=0, outer=4, inner=0)
        for item, expected in ((at_t0, [B13A.C04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0]),
                               (one_after, [])):
            with self.subTest(coordinate=item["coordinate"]):
                record = build(cover=complete_coverage(
                    complete=False,
                    decode_accounting=accounting(undecodable=1, system_instructions_total=6,
                                                 unresolved=[item])))
                self.assertEqual([f["reason_code"] for f in B13A.completeness_failures(record)],
                                 expected)

    def test_failures_are_reported_as_stable_codes_not_a_bare_false(self):
        record = build()
        failures = B13A.completeness_failures(record)
        self.assertTrue(failures)
        for failure in failures:
            self.assertIn(failure["reason_code"], B13A.COMPLETENESS_REASON_CODES)
            self.assertTrue(failure["detail"])

    def test_a_zero_edge_but_fully_decoded_history_is_complete(self):
        """No funding edges AND nothing unresolved is a real finding: this actor was not funded
        within the window. That is the case the seam exists to keep distinguishable."""
        events = [e for e in stream() if e["kind"] != B13A.EVENT_TRANSFER]
        record = build(events, cover=complete_coverage(
            decode_accounting=accounting(edges_emitted=0, decoded_moving=1,
                                         moving_self_transfer=1,
                                         system_instructions_total=3)))
        funding = record["sections"]["funding"]["features"]
        self.assertEqual(funding["inbound_edge_count_observed"], 0)
        self.assertEqual(funding["outbound_edge_count_observed"], 0)
        self.assertFalse(funding["actor_seen_in_window"])
        self.assertFalse(funding["counts_are_lower_bounds"])
        self.assertTrue(B13A.require_complete_history(record))

    def test_the_decode_accounting_travels_inside_the_history_hash(self):
        baseline = build()
        moved = build(cover=coverage(decode_accounting=accounting(
            undecodable=1, system_instructions_total=6, unresolved=[unresolved_item(slot=800)])))
        self.assertNotEqual(baseline["history_sha256"], moved["history_sha256"])

    def test_a_transaction_level_failure_sorts_before_every_instruction_in_it(self):
        """A body we cannot read may have held an edge at any point inside it, so it is recorded at
        outer -1 and poisons any subject at or after that transaction."""
        missing = unresolved_item(reason=B13A.D03_MISSING_RAW_BODY, slot=500, tx=0,
                                  outer=B13A.TRANSACTION_LEVEL_OUTER_INDEX,
                                  inner=B13A.TRANSACTION_LEVEL_INNER_INDEX,
                                  detail="no preserved body")
        record = build(cover=complete_coverage(
            complete=False,
            decode_accounting=accounting(transactions_required=4, transactions_missing_body=1,
                                         unresolved=[missing])))
        self.assertEqual([f["reason_code"] for f in B13A.completeness_failures(record)],
                         [B13A.C04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0])


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


class TransferExtractionTests(unittest.TestCase):
    """The two failure buckets real data has never produced, and the two the database can.

    A path that never runs is a path nobody notices breaking, so both are driven directly.
    """

    def setUp(self):
        self.corpus = _load("b13a_history_corpus", "b13a_history_corpus.py")

    def test_a_moving_transfer_is_bucketed_by_its_account_list(self):
        classify = self.corpus.classify_moving_instruction
        self.assertEqual(classify([]), self.corpus.MOVING_WITHOUT_ADDRESSES)
        self.assertEqual(classify(["only-one"]), self.corpus.MOVING_WITHOUT_ADDRESSES)
        self.assertEqual(classify(["same", "same"]), self.corpus.MOVING_SELF_TRANSFER)
        self.assertEqual(classify(["from", "to"]), self.corpus.MOVING_WITH_EDGE)
        self.assertEqual(classify(["from", "to", "extra"]), self.corpus.MOVING_WITH_EDGE)

    def test_every_bucket_is_a_declared_accounting_field(self):
        for bucket in (self.corpus.MOVING_WITH_EDGE, self.corpus.MOVING_SELF_TRANSFER,
                       self.corpus.MOVING_WITHOUT_ADDRESSES):
            self.assertIn(bucket, B13A.DECODE_ACCOUNTING_FIELDS)

    def empty_source(self, with_coordinate=False):
        import sqlite3
        database = sqlite3.connect(":memory:")
        database.executescript(
            "CREATE TABLE transaction_coordinate (signature TEXT, slot INTEGER,"
            " transaction_index INTEGER);"
            "CREATE TABLE raw_transaction (signature TEXT, raw_zlib BLOB);")
        if with_coordinate:
            database.execute("INSERT INTO transaction_coordinate VALUES ('sigA', 500, 7)")
        return database

    def test_a_missing_raw_body_is_recorded_not_skipped(self):
        edges, acc = self.corpus._transfer_events(self.empty_source(True), [(500, 7)])
        self.assertEqual(edges, [])
        self.assertTrue(B13A.assert_decode_accounting(acc))
        self.assertEqual(acc["transactions_missing_body"], 1)
        self.assertEqual(len(acc["unresolved"]), 1)
        item = acc["unresolved"][0]
        self.assertEqual(item["reason_code"], B13A.D03_MISSING_RAW_BODY)
        self.assertEqual(item["coordinate"]["slot"], 500)
        self.assertEqual(item["coordinate"]["outer_index"],
                         B13A.TRANSACTION_LEVEL_OUTER_INDEX)

    def test_a_missing_transaction_coordinate_is_recorded_not_skipped(self):
        edges, acc = self.corpus._transfer_events(self.empty_source(False), [(500, 7)])
        self.assertEqual(edges, [])
        self.assertTrue(B13A.assert_decode_accounting(acc))
        self.assertEqual(acc["transactions_missing_coordinate"], 1)
        self.assertEqual(acc["unresolved"][0]["reason_code"],
                         B13A.D04_MISSING_TRANSACTION_COORDINATE)

    def test_a_transaction_level_failure_is_recorded_before_every_instruction_in_it(self):
        """A body we cannot read may have held an edge anywhere inside it, so it must sort before
        the transaction's first instruction rather than after it."""
        self.assertEqual(B13A.TRANSACTION_LEVEL_OUTER_INDEX, -1)
        self.assertEqual(B13A.TRANSACTION_LEVEL_INNER_INDEX, -1)
        _, acc = self.corpus._transfer_events(self.empty_source(True), [(500, 7)])
        failure = acc["unresolved"][0]["coordinate"]
        self.assertLess(
            tuple(failure[f] for f in B13A.COORDINATE_FIELDS), (500, 7, 0, -1))


class KnownUndecodableTests(unittest.TestCase):
    """The two real anomalies, pinned so they cannot quietly disappear.

    `b9j` measured exactly two undecodable System instructions across 412,028 in the whole
    artifact, both padded `CreateAccount` payloads carrying four trailing bytes, both in one
    transaction. They are the concrete instance of the seam Codex found: before this pass they
    produced no edge and no record, which is indistinguishable from there being no edge to produce.
    """

    ARTIFACT = ROOT / "research" / "b9d_transaction_bodies.sqlite"
    SIGNATURE = ("5nYDQmEz8ZdjB1YHyZxqxq5wab2r1YarQtEkJTadxy9EWfS1PP7PymUJ349TAzoYfVUo7"
                 "cmCdMWohvTDnUw6xY4U")
    COORDINATE = (433_968_746, 858)
    UNDECODABLE_AT = ((2, 0), (2, 2))

    def setUp(self):
        if not self.ARTIFACT.exists():
            self.skipTest("frozen artifact not present")
        self.corpus = _load("b13a_history_corpus", "b13a_history_corpus.py")

    def test_the_two_padded_create_accounts_are_recorded_not_dropped(self):
        source = self.corpus.B9D.connect(str(self.ARTIFACT), readonly=True)
        try:
            edges, accounting = self.corpus._transfer_events(source, [self.COORDINATE])
        finally:
            source.close()
        self.assertTrue(B13A.assert_decode_accounting(accounting))
        self.assertEqual(accounting["undecodable"], 2)
        undecodable = [item for item in accounting["unresolved"]
                       if item["reason_code"] == B13A.D01_UNDECODABLE_SYSTEM_PAYLOAD]
        self.assertEqual(len(undecodable), 2)
        found = {(item["coordinate"]["outer_index"], item["coordinate"]["inner_index"])
                 for item in undecodable}
        self.assertEqual(found, set(self.UNDECODABLE_AT))
        for item in undecodable:
            self.assertEqual(item["coordinate"]["slot"], self.COORDINATE[0])
            self.assertIn("trailing byte", item["detail"])
            self.assertIn(self.SIGNATURE, item["detail"])

    def test_the_extractor_catches_the_class_b9j_actually_raises(self):
        """Every module here loads its own dependency graph by path, so the same-named exception is
        a DIFFERENT class object depending on which chain you reach it through. An `except` on the
        wrong one never matches and the decode failure escapes as a crash — which is what the
        pinned fixture above found."""
        source = (ROOT / "scripts" / "b13a_history_corpus.py").read_text()
        self.assertIn("except B9J.FreezeViolation as error:", source)
        self.assertNotIn("except B9D.FreezeViolation as error:", source)
        self.assertIsNot(self.corpus.B9J.FreezeViolation, self.corpus.B9D.FreezeViolation)

    def test_a_window_containing_them_can_never_be_declared_complete(self):
        source = self.corpus.B9D.connect(str(self.ARTIFACT), readonly=True)
        try:
            _, accounting = self.corpus._transfer_events(source, [self.COORDINATE])
        finally:
            source.close()
        with self.assertRaisesRegex(B13A.HistoryRefused, "Untruncated geometry is not completeness"):
            B13A.assert_coverage(complete_coverage(decode_accounting=accounting))

    def test_a_subject_deciding_after_them_is_refused_a_completeness_claim(self):
        source = self.corpus.B9D.connect(str(self.ARTIFACT), readonly=True)
        try:
            _, accounting = self.corpus._transfer_events(source, [self.COORDINATE])
        finally:
            source.close()
        after = event(B13A.EVENT_TRADE, self.COORDINATE[0] + 1, mint=SUBJECT_MINT, user=USER,
                      is_buy=True, quote_lamports=1, token_units=1)
        record = B13A.build_as_of_history(
            [launch(self.COORDINATE[0] - 1, SUBJECT_MINT, source="u")], SUBJECT, after,
            complete_coverage(complete=False, first_slot=1, last_slot=10 ** 9,
                              decode_accounting=accounting))
        self.assertEqual([f["reason_code"] for f in B13A.completeness_failures(record)],
                         [B13A.C04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0])

    def test_a_subject_deciding_before_them_is_not_poisoned(self):
        source = self.corpus.B9D.connect(str(self.ARTIFACT), readonly=True)
        try:
            _, accounting = self.corpus._transfer_events(source, [self.COORDINATE])
        finally:
            source.close()
        before = event(B13A.EVENT_TRADE, self.COORDINATE[0] - 1, mint=SUBJECT_MINT, user=USER,
                       is_buy=True, quote_lamports=1, token_units=1)
        record = B13A.build_as_of_history(
            [launch(self.COORDINATE[0] - 2, SUBJECT_MINT, source="u")], SUBJECT, before,
            complete_coverage(complete=False, first_slot=1, last_slot=10 ** 9,
                              decode_accounting=accounting))
        self.assertEqual(B13A.completeness_failures(record), [])
        self.assertTrue(B13A.require_complete_history(record))


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
