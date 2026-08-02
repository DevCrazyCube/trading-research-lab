"""Tests for the B13c external observation ledger.

Synthetic fixtures only. Nothing here touches a network, a provider, the burned corpus or B11a.

One module graph is loaded for the whole file: loading the same module twice by path creates two
distinct exception classes, and an `assertRaises` on the wrong one never matches.
"""
import copy
import hashlib
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURES = _load("b13c_observation_fixtures", "b13c_observation_fixtures.py")
B13C = FIXTURES.B13C
B10B = B13C.B10B

SECOND = FIXTURES.SECOND
BASE = FIXTURES.BASE
MINT_A, MINT_B = FIXTURES.MINT_A, FIXTURES.MINT_B


def instant(seconds):
    return FIXTURES.decision_instant(seconds)


def stated(seconds, precision_ns=0, source="fixture"):
    return B13C.time_claim(BASE + seconds * SECOND, precision_ns, source)


def observation(**overrides):
    """One well-formed observation, with everything the caller did not override."""
    kwargs = {
        "provider": "provider-alpha", "provider_observation_id": "id-1",
        "kind": B13C.KIND_NEWS_ARTICLE, "query_spec_sha256": "q" * 64,
        "fetch_session_id": "session-1", "fetch_provenance_sha256": "f" * 64,
        "decoder_name": "synthetic-decoder", "decoder_version": "1.0.0",
        "receipt_time": stated(110), "publication_time": stated(100),
        "receipt_monotonic_ns": 1_000, "raw_payload": "synthetic body",
        "license_status": B13C.LICENSE_PERMITS_STORAGE,
        "retention_status": B13C.RETENTION_RAW_RETAINED,
        "mapping": B13C.exact_binding(mint=MINT_A, binding_evidence="mint quoted in body"),
    }
    kwargs.update(overrides)
    return B13C.build_observation(**kwargs)


# --------------------------------------------------------------------------------------------

class AvailabilityRuleTests(unittest.TestCase):
    """Both clocks, and neither implies the other."""

    def test_an_item_received_and_published_before_t0_is_eligible(self):
        self.assertTrue(B13C.feature_eligible(observation(), instant(200)))

    def test_an_item_fetched_after_t0_is_refused_however_old_it_is(self):
        """The backfill. An article published last week but fetched today was not available last
        week, and nothing about the article says so."""
        backfilled = observation(publication_time=stated(10), receipt_time=stated(900))
        codes = [r["reason_code"] for r in B13C.ineligibility(backfilled, instant(200))]
        self.assertEqual(codes, [B13C.A01_RECEIVED_AFTER_T0])
        with self.assertRaisesRegex(B13C.ObservationRefused, "cannot be backfilled"):
            B13C.require_eligible(backfilled, instant(200))

    def test_an_item_published_after_t0_is_refused_however_early_it_arrived(self):
        future = observation(publication_time=stated(900), receipt_time=stated(110))
        codes = [r["reason_code"] for r in B13C.ineligibility(future, instant(200))]
        self.assertEqual(codes, [B13C.A02_PUBLISHED_AFTER_T0])

    def test_neither_clock_alone_is_enough(self):
        """The whole reason the rule needs two clocks, stated as a table."""
        cases = {
            (10, 20): [],
            (10, 900): [B13C.A01_RECEIVED_AFTER_T0],
            (900, 20): [B13C.A02_PUBLISHED_AFTER_T0],
            (900, 900): [B13C.A02_PUBLISHED_AFTER_T0, B13C.A01_RECEIVED_AFTER_T0],
        }
        for (published, received), expected in cases.items():
            with self.subTest(published=published, received=received):
                item = observation(publication_time=stated(published),
                                   receipt_time=stated(received))
                codes = {r["reason_code"] for r in B13C.ineligibility(item, instant(200))}
                self.assertEqual(codes, set(expected))

    def test_the_boundary_is_inclusive_at_t0(self):
        exact = observation(publication_time=stated(200), receipt_time=stated(200))
        self.assertTrue(B13C.feature_eligible(exact, instant(200)))

    def test_the_boundary_is_exclusive_one_nanosecond_later(self):
        item = observation(publication_time=stated(100),
                           receipt_time=B13C.time_claim(BASE + 200 * SECOND + 1, 0, "fixture"))
        self.assertFalse(B13C.feature_eligible(item, instant(200)))

    def test_an_unavailable_clock_is_never_eligible(self):
        for clock in ("publication_time", "receipt_time"):
            with self.subTest(clock=clock):
                item = observation(**{clock: B13C.unavailable_time("the provider omitted it")})
                self.assertFalse(B13C.feature_eligible(item, instant(9_000)))

    def test_an_ambiguous_clock_is_never_eligible_and_is_not_the_same_as_missing(self):
        """"We have a value we cannot bound" and "we have no value" are different facts, and both
        are unusable. Guessing a timezone would invent the very thing being checked."""
        item = observation(publication_time=B13C.ambiguous_time(BASE, "no timezone stated"))
        codes = [r["reason_code"] for r in B13C.ineligibility(item, instant(9_000))]
        self.assertEqual(codes, [B13C.A04_PUBLICATION_TIME_UNAVAILABLE])
        self.assertNotEqual(B13C.ambiguous_time(BASE, "x")["status"],
                            B13C.unavailable_time("x")["status"])

    def test_a_day_precision_claim_becomes_usable_only_at_the_end_of_its_day(self):
        """A date with no time covers a whole day, and the only safe reading is its last instant."""
        day = 86_400
        item = observation(publication_time=B13C.time_claim(BASE, day * SECOND, "date only"),
                           receipt_time=stated(0))
        self.assertFalse(B13C.feature_eligible(item, instant(day - 1)))
        self.assertTrue(B13C.feature_eligible(item, instant(day)))

    def test_the_rule_travels_on_every_record(self):
        self.assertEqual(observation()["availability_rule"], B13C.AVAILABILITY_RULE)
        item = observation()
        item["availability_rule"] = "anything before t0, roughly"
        with self.assertRaisesRegex(B13C.ObservationRefused, "not the one this module applies"):
            B13C.assert_observation(item)

    def test_a_prohibited_licence_or_purged_payload_is_refused(self):
        cases = {
            B13C.A06_LICENSE_PROHIBITS_USE: {"license_status": B13C.LICENSE_PROHIBITED,
                                             "retention_status": B13C.RETENTION_HASH_ONLY,
                                             "raw_payload": None,
                                             "payload_sha256": "a" * 64},
            B13C.A07_PAYLOAD_PURGED: {"license_status": B13C.LICENSE_PERMITS_STORAGE,
                                      "retention_status": B13C.RETENTION_PURGED,
                                      "raw_payload": None, "payload_sha256": "a" * 64},
        }
        for expected, overrides in cases.items():
            with self.subTest(expected=expected):
                codes = [r["reason_code"]
                         for r in B13C.ineligibility(observation(**overrides), instant(200))]
                self.assertIn(expected, codes)


class DecisionInstantTests(unittest.TestCase):
    """A chain coordinate carries no wall time, and this module refuses to invent the join."""

    def test_both_clocks_and_the_join_must_be_declared(self):
        for field in B13C.DECISION_INSTANT_FIELDS:
            with self.subTest(missing=field):
                broken = {k: v for k, v in instant(200).items() if k != field}
                with self.assertRaisesRegex(B13C.ObservationRefused, "does not state"):
                    B13C.assert_decision_instant(broken)

    def test_an_instant_without_provenance_for_its_wall_time_is_refused(self):
        broken = dict(instant(200), wall_clock_provenance="")
        with self.assertRaisesRegex(B13C.ObservationRefused, "where its wall time came from"):
            B13C.assert_decision_instant(broken)

    def test_an_observation_may_bind_to_a_chain_coordinate_or_to_none(self):
        """Some external facts land on-chain — a config change, an oracle write — and those carry a
        coordinate. Most do not, and a partial one would join to the wrong instant."""
        full = {"slot": 5, "transaction_index": 1, "outer_index": 0, "inner_index": 0}
        self.assertEqual(observation(effective_coordinate=full)["times"]["effective_coordinate"],
                         full)
        self.assertIsNone(observation()["times"]["effective_coordinate"])
        for broken in ({"slot": 5}, {**full, "extra": 1}, "430000000"):
            with self.subTest(broken=broken):
                with self.assertRaisesRegex(B13C.ObservationRefused,
                                            "full canonical coordinate or null"):
                    observation(effective_coordinate=broken)

    def test_the_instant_carries_a_full_canonical_coordinate(self):
        broken = dict(instant(200), coordinate={"slot": 1})
        with self.assertRaisesRegex(B13C.ObservationRefused, "full canonical coordinate"):
            B13C.assert_decision_instant(broken)


class RevisionTests(unittest.TestCase):
    """Corrections and deletions create new observations. History is never rewritten."""

    def chain(self):
        return FIXTURES.build_fixture_corpus()["corrected_article"]

    def test_as_of_returns_the_version_actually_known_then(self):
        chain = self.chain()
        cases = {150: 0, 350: 1, 600: 2}
        for seconds, expected_index in cases.items():
            with self.subTest(seconds=seconds):
                current = B13C.as_of(chain, instant(seconds))
                self.assertEqual(current["revision"]["revision_index"], expected_index)

    def test_a_correction_that_had_not_arrived_yet_is_invisible(self):
        current = B13C.as_of(self.chain(), instant(150))
        self.assertIn("original", current["payload"]["raw_payload"])

    def test_every_prior_version_is_preserved(self):
        chain = self.chain()
        history = B13C.version_history_as_of(chain, instant(600))
        self.assertEqual([o["revision"]["revision_index"] for o in history], [0, 1, 2])
        self.assertEqual(len(chain), 3)

    def test_a_deletion_does_not_reach_back_into_an_earlier_decision(self):
        """The subtle one. A deletion received after t0 removing the text a decision was made on
        would be leakage wearing the costume of data hygiene."""
        chain = FIXTURES.build_fixture_corpus()["deleted_post"]
        before = B13C.as_of(chain, instant(300))
        self.assertFalse(B13C.is_absent(before))
        self.assertEqual(before["revision"]["revision_index"], 0)
        after = B13C.as_of(chain, instant(450))
        self.assertTrue(B13C.is_absent(after))
        self.assertEqual(after.reason, B13C.ABSENT_DELETED)

    def test_nothing_known_yet_is_its_own_kind_of_absence(self):
        absent = B13C.as_of(self.chain(), instant(50))
        self.assertTrue(B13C.is_absent(absent))
        self.assertEqual(absent.reason, B13C.ABSENT_NOT_YET_KNOWN)
        self.assertNotEqual(absent.reason, B13C.ABSENT_DELETED)

    def test_a_chain_must_link(self):
        chain = self.chain()
        chain[2]["revision"]["supersedes_observation_sha256"] = "0" * 64
        with self.assertRaisesRegex(B13C.ObservationRefused, "chain that rewrote something"):
            B13C.assert_revision_chain(chain)

    def test_a_gap_in_the_chain_is_refused(self):
        chain = self.chain()
        with self.assertRaisesRegex(B13C.ObservationRefused, "a version nobody kept"):
            B13C.assert_revision_chain([chain[0], chain[2]])

    def test_a_chain_must_begin_with_a_create(self):
        chain = self.chain()
        with self.assertRaisesRegex(B13C.ObservationRefused, "must begin with a create"):
            B13C.assert_revision_chain(chain[1:])

    def test_a_second_create_in_one_chain_is_refused(self):
        chain = self.chain()
        twin = copy.deepcopy(chain[0])
        twin["revision"]["revision_index"] = 1
        twin["features"]["revision_index"] = 1
        with self.assertRaisesRegex(B13C.ObservationRefused, "silently merges two histories"):
            B13C.assert_revision_chain([chain[0], twin])

    def test_a_create_may_not_supersede_anything(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "wearing the wrong label"):
            observation(revision_kind=B13C.REVISION_CREATE, revision_index=0, supersedes="a" * 64)

    def test_an_edit_must_name_what_it_corrects(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "rewrites history instead"):
            observation(revision_kind=B13C.REVISION_EDIT, revision_index=1, supersedes=None)

    def test_the_monotonic_receipt_clock_may_not_run_backwards_in_one_session(self):
        """A wall clock can legitimately jump — NTP, a suspend, a timezone mistake — so it cannot
        detect reordering. That is exactly why both clocks are recorded."""
        create = observation(receipt_monotonic_ns=5_000)
        edit = observation(revision_kind=B13C.REVISION_EDIT, revision_index=1,
                           supersedes=create["observation_sha256"], receipt_monotonic_ns=1_000,
                           raw_payload="corrected body")
        with self.assertRaisesRegex(B13C.ObservationRefused, "monotonic receipt clock ran backwards"):
            B13C.assert_revision_chain([create, edit])

    def test_a_wall_clock_jump_alone_does_not_invalidate_a_chain(self):
        create = observation(receipt_time=stated(300), receipt_monotonic_ns=1_000)
        edit = observation(revision_kind=B13C.REVISION_EDIT, revision_index=1,
                           supersedes=create["observation_sha256"], receipt_time=stated(250),
                           receipt_monotonic_ns=2_000, raw_payload="corrected body")
        self.assertTrue(B13C.assert_revision_chain([create, edit]))

    def test_different_sessions_do_not_constrain_each_other(self):
        create = observation(fetch_session_id="session-1", receipt_monotonic_ns=9_000)
        edit = observation(revision_kind=B13C.REVISION_EDIT, revision_index=1,
                           supersedes=create["observation_sha256"], fetch_session_id="session-2",
                           receipt_monotonic_ns=1, raw_payload="corrected body")
        self.assertTrue(B13C.assert_revision_chain([create, edit]))


class IdentifierCollisionTests(unittest.TestCase):
    """One identifier, different content, no revision relationship — that is two items."""

    def test_a_reused_identifier_with_different_content_is_refused(self):
        first = observation()
        second = observation(raw_payload="entirely different body")
        with self.assertRaisesRegex(B13C.ObservationRefused, "attributes one source's words"):
            B13C.assert_no_identifier_collision([first, second])

    def test_a_genuine_revision_chain_is_not_a_collision(self):
        create = observation()
        edit = observation(revision_kind=B13C.REVISION_EDIT, revision_index=1,
                           supersedes=create["observation_sha256"], raw_payload="corrected body")
        self.assertTrue(B13C.assert_no_identifier_collision([create, edit]))

    def test_the_same_identifier_from_two_providers_is_two_items(self):
        """An identifier belongs to the provider that issued it; they do not share a namespace."""
        alpha = observation(provider="provider-alpha")
        beta = observation(provider="provider-beta", raw_payload="a different body entirely")
        self.assertTrue(B13C.assert_no_identifier_collision([alpha, beta]))
        self.assertEqual(len(B13C.revision_chain([alpha, beta], "provider-alpha", "id-1")), 1)


class MappingTests(unittest.TestCase):
    """A ticker is not a token."""

    def test_a_ticker_match_is_not_an_exact_binding(self):
        item = observation(mapping=B13C.ticker_mapping("$DOG", mint=MINT_A))
        self.assertFalse(item["features"]["mapping_is_exact_binding"])
        with self.assertRaisesRegex(B13C.ObservationRefused, "not an exact binding"):
            B13C.require_exact_binding(item)

    def test_two_tokens_sharing_a_ticker_stay_two_tokens(self):
        collision = FIXTURES.build_fixture_corpus()["ticker_collision"]
        mints = {o["mapping"]["mint"] for o in collision}
        self.assertEqual(mints, {MINT_A, MINT_B})
        for item in collision:
            with self.subTest(mint=item["mapping"]["mint"]):
                self.assertEqual(item["mapping"]["status"], B13C.MAPPING_UNVERIFIED)
                self.assertIn(B13C.A05_MAPPING_NOT_EXACT,
                              [r["reason_code"] for r in B13C.ineligibility(item, instant(300))])

    def test_a_providers_bare_claim_is_labelled_a_claim(self):
        item = observation(mapping=B13C.claimed_mapping(mint=MINT_A))
        self.assertEqual(item["mapping"]["status"], B13C.MAPPING_SOURCE_CLAIM)
        with self.assertRaisesRegex(B13C.ObservationRefused, "still a claim"):
            B13C.require_exact_binding(item)

    def test_an_exact_binding_must_show_where_the_address_was_found(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "must show where the address"):
            observation(mapping={"status": B13C.MAPPING_EXACT_BINDING, "mint": MINT_A,
                                 "account": None, "matched_text": None, "binding_evidence": "",
                                 "detail": ""})

    def test_an_exact_binding_must_name_an_address(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "not that we are confident"):
            observation(mapping=B13C.exact_binding(binding_evidence="somewhere in the body"))

    def test_a_weaker_status_may_not_carry_binding_evidence(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "disagrees with itself"):
            observation(mapping={"status": B13C.MAPPING_SOURCE_CLAIM, "mint": MINT_A,
                                 "account": None, "matched_text": None,
                                 "binding_evidence": "looks right", "detail": ""})

    def test_an_unverified_mapping_must_say_what_matched(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "see the collision risk"):
            observation(mapping={"status": B13C.MAPPING_UNVERIFIED, "mint": MINT_A,
                                 "account": None, "matched_text": None, "binding_evidence": None,
                                 "detail": ""})

    def test_binding_may_be_waived_explicitly_for_a_question_that_is_not_about_a_token(self):
        """A global config fact belongs to no token; requiring a binding would refuse it forever."""
        item = observation(kind=B13C.KIND_CONFIG_FACT, mapping=B13C.unmapped("global fact"))
        self.assertFalse(B13C.feature_eligible(item, instant(200)))
        self.assertTrue(B13C.feature_eligible(item, instant(200), require_binding=False))


class MeasurementTests(unittest.TestCase):
    """A value and its unit, together, or nothing."""

    def quote(self, **overrides):
        measurement = {"value_numerator": 1_000, "value_denominator": 1, "unit": "lamports",
                       "quote_asset": "SOL", "effective_time": stated(150),
                       "measurement_basis": "last traded price"}
        measurement.update(overrides)
        return observation(kind=B13C.KIND_FINANCIAL_QUOTE, measurement=measurement)

    def test_a_measured_value_never_appears_in_the_feature_block(self):
        """A number that can be separated from its unit eventually will be, and lamports read as
        SOL is off by a factor of a billion."""
        item = self.quote()
        self.assertNotIn("value_numerator", item["features"])
        self.assertIn("value_numerator", item["measurement"])
        self.assertIn("unit", item["measurement"])

    def test_a_quote_must_name_its_unit_quote_asset_basis_and_effective_time(self):
        for field in ("unit", "quote_asset", "measurement_basis"):
            with self.subTest(missing=field):
                with self.assertRaisesRegex(B13C.ObservationRefused, "non-empty string"):
                    self.quote(**{field: ""})

    def test_a_quote_with_an_unstated_effective_time_is_refused(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "cannot be placed on any timeline"):
            self.quote(effective_time=B13C.unavailable_time("the provider omitted it"))

    def test_a_non_quote_may_not_carry_a_measurement(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "only financial_quote"):
            observation(kind=B13C.KIND_NEWS_ARTICLE,
                        measurement={"value_numerator": 1, "value_denominator": 1,
                                     "unit": "lamports", "quote_asset": "SOL",
                                     "effective_time": stated(1), "measurement_basis": "mid"})

    def test_a_quote_must_carry_one(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "must carry a measurement"):
            observation(kind=B13C.KIND_FINANCIAL_QUOTE, measurement=None)

    def test_mixing_units_fails_closed_rather_than_converting(self):
        """Converting would need a rate, and a rate is itself a timestamped observation nobody
        supplied here."""
        for field, other in (("unit", "micro_usd"), ("quote_asset", "USD"),
                             ("measurement_basis", "mid price")):
            with self.subTest(differing=field):
                with self.assertRaisesRegex(B13C.ObservationRefused, "not comparable"):
                    B13C.assert_comparable(self.quote()["measurement"],
                                           self.quote(**{field: other})["measurement"])

    def test_identical_units_compare_cleanly(self):
        self.assertTrue(B13C.assert_comparable(self.quote()["measurement"],
                                               self.quote(value_numerator=9)["measurement"]))

    def test_a_value_is_an_exact_rational_never_a_float(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "must be an integer"):
            self.quote(value_numerator=1.5)
        with self.assertRaisesRegex(B13C.ObservationRefused, "denominator must be positive"):
            self.quote(value_denominator=0)

    def test_staleness_is_measured_and_the_bound_belongs_to_the_caller(self):
        item = self.quote()
        self.assertEqual(B13C.staleness_ns(item["measurement"], instant(200)), 50 * SECOND)
        self.assertTrue(B13C.require_fresh(item["measurement"], instant(200), 60 * SECOND,
                                           "a caller's stated tolerance"))
        with self.assertRaisesRegex(B13C.ObservationRefused, "beyond the caller's bound"):
            B13C.require_fresh(item["measurement"], instant(200), 10 * SECOND, "a tighter bound")

    def test_a_freshness_bound_must_arrive_with_a_reason(self):
        """An unexplained threshold is one nobody can review, and this project preregisters them."""
        with self.assertRaisesRegex(B13C.ObservationRefused, "reason it was chosen"):
            B13C.require_fresh(self.quote()["measurement"], instant(200), 60 * SECOND, "")

    def test_a_value_effective_after_the_decision_is_refused(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "value from the future"):
            B13C.require_fresh(self.quote(effective_time=stated(900))["measurement"],
                               instant(200), 10 ** 18, "generous")

    def test_an_unmeasurable_age_cannot_be_shown_to_be_fresh(self):
        measurement = dict(self.quote()["measurement"],
                           effective_time=B13C.ambiguous_time(BASE, "no timezone"))
        with self.assertRaisesRegex(B13C.ObservationRefused, "cannot be shown to be fresh"):
            B13C.require_fresh(measurement, instant(200), 10 ** 18, "generous")


class AbsenceTests(unittest.TestCase):
    """Unknown, unavailable and deleted are three facts, and none of them is zero."""

    def test_an_absent_value_refuses_to_be_a_truth_value(self):
        value = B13C.absent(B13C.ABSENT_UNAVAILABLE, "no price was ever received")
        with self.assertRaisesRegex(B13C.ObservationRefused, "Absence is not falsity"):
            bool(value)
        with self.assertRaises(B13C.ObservationRefused):
            if value:                                       # noqa: F631 - the point of the test
                pass

    def test_absence_is_not_zero_and_not_false(self):
        value = B13C.absent(B13C.ABSENT_UNKNOWN, "nobody asked")
        self.assertNotEqual(value, 0)
        self.assertNotEqual(value, False)
        self.assertNotEqual(value, None)

    def test_the_reasons_are_distinguishable(self):
        pairs = [(B13C.ABSENT_UNKNOWN, B13C.ABSENT_UNAVAILABLE),
                 (B13C.ABSENT_UNAVAILABLE, B13C.ABSENT_DELETED),
                 (B13C.ABSENT_DELETED, B13C.ABSENT_NOT_YET_KNOWN)]
        for first, second in pairs:
            with self.subTest(first=first, second=second):
                self.assertNotEqual(B13C.absent(first, "a"), B13C.absent(second, "b"))

    def test_an_undeclared_absence_reason_is_refused(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "is not one of"):
            B13C.absent("probably_missing", "a guess")

    def test_a_claim_may_not_be_ambiguous_and_precise_at_once(self):
        """A claim whose width is known is not ambiguous — state it, and let the boundary
        arithmetic use it instead of discarding the item."""
        claim = dict(B13C.ambiguous_time(BASE, "no zone"), precision_ns=0)
        with self.assertRaisesRegex(B13C.ObservationRefused, "is ambiguous yet states a precision"):
            B13C.assert_time_claim(claim, "publication_time")

    def test_an_unavailable_clock_may_not_carry_a_reading(self):
        """"We have no reading" and "here is the reading" cannot both be true, and a value hiding
        behind an unavailable status is a value something will eventually read."""
        for field in ("value_ns", "precision_ns"):
            with self.subTest(field=field):
                claim = dict(B13C.unavailable_time("omitted"), **{field: BASE})
                with self.assertRaisesRegex(B13C.ObservationRefused, "has no reading"):
                    B13C.assert_time_claim(claim, "publication_time")

    def test_a_stated_claim_must_carry_an_integer_value_and_width(self):
        for override in ({"value_ns": None}, {"precision_ns": None}, {"precision_ns": -1}):
            with self.subTest(override=override):
                with self.assertRaises(B13C.ObservationRefused):
                    B13C.assert_time_claim(dict(stated(100), **override), "publication_time")

    def test_an_undeclared_time_status_is_refused(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "is not one of"):
            B13C.assert_time_claim(dict(stated(100), status="probably"), "publication_time")

    def test_an_unbounded_time_claim_returns_an_absent_rather_than_a_guess(self):
        for claim in (B13C.unavailable_time("omitted"), B13C.ambiguous_time(BASE, "no zone")):
            with self.subTest(status=claim["status"]):
                self.assertTrue(B13C.is_absent(B13C.latest_possible(claim)))


class LicenceAndRetentionTests(unittest.TestCase):
    """What we are allowed to keep, and what we actually kept, checked against each other."""

    def test_a_licence_may_not_sit_beside_a_payload_it_forbids(self):
        for status in (B13C.LICENSE_REFERENCE_ONLY, B13C.LICENSE_PROHIBITED,
                       B13C.LICENSE_UNKNOWN):
            with self.subTest(license=status):
                with self.assertRaisesRegex(B13C.ObservationRefused, "nobody is honouring"):
                    observation(license_status=status,
                                retention_status=B13C.RETENTION_RAW_RETAINED)

    def test_only_an_explicit_permission_allows_keeping_the_bytes(self):
        self.assertEqual(B13C.LICENSE_PERMITS[B13C.LICENSE_PERMITS_STORAGE][0],
                         B13C.RETENTION_RAW_RETAINED)
        for status in (B13C.LICENSE_UNKNOWN, B13C.LICENSE_REFERENCE_ONLY,
                       B13C.LICENSE_PROHIBITED):
            with self.subTest(license=status):
                self.assertNotIn(B13C.RETENTION_RAW_RETAINED, B13C.LICENSE_PERMITS[status])

    def test_a_hash_only_record_may_not_carry_the_bytes(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "disagree about what we kept"):
            item = observation()
            item["retention_status"] = B13C.RETENTION_HASH_ONLY
            item["features"]["raw_payload_retained"] = False
            B13C.assert_observation(item)

    def test_a_record_claiming_retention_must_actually_hold_the_bytes(self):
        item = observation()
        item["payload"]["raw_payload"] = None
        with self.assertRaisesRegex(B13C.ObservationRefused, "but none is present"):
            B13C.assert_observation(item)

    def test_an_observation_always_carries_a_digest_even_with_nothing_kept(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "must carry a payload digest"):
            observation(raw_payload=None, payload_sha256=None,
                        retention_status=B13C.RETENTION_HASH_ONLY)


class PayloadDriftTests(unittest.TestCase):
    """The bytes and the digest must still agree."""

    def test_drifting_bytes_are_caught(self):
        item = observation()
        item["payload"]["raw_payload"] = "quietly edited body"
        with self.assertRaisesRegex(B13C.ObservationRefused, "no way to tell which"):
            B13C.assert_observation(item)

    def test_a_drifting_digest_is_caught(self):
        item = observation()
        item["payload"]["payload_sha256"] = hashlib.sha256(b"something else").hexdigest()
        with self.assertRaisesRegex(B13C.ObservationRefused, "no way to tell which"):
            B13C.assert_observation(item)

    def test_a_drifting_length_is_caught(self):
        item = observation()
        item["payload"]["payload_byte_length"] += 1
        item["features"]["payload_byte_length"] += 1
        with self.assertRaisesRegex(B13C.ObservationRefused, "length disagrees"):
            B13C.assert_observation(item)

    def test_changing_any_field_changes_the_observation_hash(self):
        base = observation()
        for changed in (observation(raw_payload="a different body"),
                        observation(receipt_time=stated(111)),
                        observation(publication_time=stated(101)),
                        observation(decoder_version="1.0.1"),
                        observation(mapping=B13C.exact_binding(mint=MINT_B,
                                                               binding_evidence="quoted"))):
            with self.subTest(field=changed["observation_sha256"][:8]):
                self.assertNotEqual(base["observation_sha256"], changed["observation_sha256"])


class FeatureBlockTests(unittest.TestCase):
    """Raw text, URLs and handles live in evidence. Never in a feature block."""

    def test_no_string_may_appear_in_a_feature_block(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "NO STRING MAY APPEAR"):
            B13C.assert_no_string_in_features({"payload_byte_length": "https://example.invalid"})

    def test_raw_text_smuggled_into_the_features_is_refused(self):
        item = observation(evidence={"text": "synthetic body", "url": "https://example.invalid"})
        item["features"]["payload_byte_length"] = item["evidence"]["text"]
        with self.assertRaisesRegex(B13C.ObservationRefused, "NO STRING MAY APPEAR"):
            B13C.assert_observation(item)

    def test_every_shipped_feature_is_an_integer_or_boolean(self):
        for item in [o for group in FIXTURES.build_fixture_corpus().values() for o in group]:
            for field, value in item["features"].items():
                with self.subTest(field=field):
                    self.assertIsInstance(value, (int, bool))

    def test_the_numeric_view_may_not_disagree_with_the_record(self):
        cases = ("publication_time_available", "receipt_time_available",
                 "mapping_is_exact_binding", "is_deletion", "raw_payload_retained")
        for field in cases:
            with self.subTest(field=field):
                item = observation()
                item["features"][field] = not item["features"][field]
                with self.assertRaisesRegex(B13C.ObservationRefused, "quietly disagree"):
                    B13C.assert_observation(item)

    def test_the_feature_contract_is_exactly_what_is_shipped(self):
        item = observation()
        self.assertEqual(set(item["features"]), set(B13C.FEATURE_FIELDS))
        item["features"]["invented"] = 1
        with self.assertRaisesRegex(B13C.ObservationRefused, "contract says"):
            B13C.assert_observation(item)

    def test_a_missing_feature_is_refused_rather_than_defaulted(self):
        item = observation()
        del item["features"]["mapping_is_exact_binding"]
        with self.assertRaisesRegex(B13C.ObservationRefused, "contract says"):
            B13C.assert_observation(item)

    def test_evidence_and_feature_fields_are_disjoint_and_the_check_is_reachable(self):
        self.assertTrue(B13C.assert_disjoint_blocks(("text", "url"), B13C.FEATURE_FIELDS))
        with self.assertRaisesRegex(B13C.ObservationRefused, "raw text used for prediction"):
            B13C.assert_disjoint_blocks(("revision_index",), B13C.FEATURE_FIELDS)

    def test_an_evidence_key_colliding_with_a_feature_name_is_refused(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "raw text used for prediction"):
            observation(evidence={"revision_index": "smuggled"})


class DerivedQuantityTests(unittest.TestCase):
    """This ledger records facts. Judgements are somebody else's preregistration."""

    def test_every_derived_computation_fails_closed(self):
        for name in ("sentiment", "embedding", "engagement_score", "source_credibility",
                     "market_cap", "call_language_model"):
            with self.subTest(computation=name):
                with self.assertRaises(B13C.DerivedQuantityRefused):
                    getattr(B13C, name)("anything")

    def test_no_language_model_is_in_the_decision_path(self):
        self.assertFalse(B13C.LLM_IN_DECISION_PATH)
        with self.assertRaisesRegex(B13C.DerivedQuantityRefused, "unreproducible"):
            B13C.call_language_model("summarise this")

    def test_a_forbidden_field_name_is_refused_wherever_it_appears(self):
        for name in ("sentiment_score", "embedding", "engagement", "popularity_rank",
                     "source_credibility", "market_cap_usd", "price_change_pct", "llm_summary",
                     "bullish", "confidence"):
            with self.subTest(field=name):
                item = observation()
                item["evidence"][name] = 1
                with self.assertRaises(B13C.DerivedQuantityRefused):
                    B13C.assert_no_derived_quantity(item)

    def test_a_forbidden_name_is_refused_even_holding_an_innocent_value(self):
        item = observation()
        item["evidence"]["sentiment"] = None
        with self.assertRaisesRegex(B13C.DerivedQuantityRefused, "sentiment"):
            B13C.assert_no_derived_quantity(item)

    def test_no_float_may_appear_anywhere(self):
        item = observation()
        item["evidence"]["ratio"] = 0.5
        with self.assertRaisesRegex(B13C.ObservationRefused, "No float may appear"):
            B13C.assert_no_float(item)

    def test_a_refusal_of_scope_is_distinguishable_from_a_malformed_input(self):
        self.assertTrue(issubclass(B13C.DerivedQuantityRefused, B13C.ObservationRefused))


class DeterminismTests(unittest.TestCase):
    """Identical evidence in any order gives a byte-identical answer."""

    def everything(self):
        return [o for group in FIXTURES.build_fixture_corpus().values() for o in group]

    def test_arrival_order_does_not_change_the_ordering(self):
        forward = B13C.ordered_observations(self.everything())
        backward = B13C.ordered_observations(list(reversed(self.everything())))
        self.assertEqual(B10B.canonical_json(forward), B10B.canonical_json(backward))

    def test_arrival_order_does_not_change_an_as_of_answer(self):
        chain = FIXTURES.build_fixture_corpus()["corrected_article"]
        forward = B13C.as_of(chain, instant(350))
        reordered = B13C.as_of(B13C.revision_chain(list(reversed(chain)), "provider-alpha",
                                                   "news-1"), instant(350))
        self.assertEqual(forward["observation_sha256"], reordered["observation_sha256"])

    def test_duplicate_observations_are_refused(self):
        item = observation()
        with self.assertRaisesRegex(B13C.ObservationRefused, "counted twice"):
            B13C.ordered_observations([item, copy.deepcopy(item)])

    def test_rebuilding_the_corpus_is_byte_identical(self):
        self.assertEqual(B10B.canonical_json(FIXTURES.build_fixture_corpus()),
                         B10B.canonical_json(FIXTURES.build_fixture_corpus()))

    def test_observations_must_be_a_sequence(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "must be a sequence"):
            B13C.ordered_observations(observation())


class ContractTests(unittest.TestCase):
    """What the module says about itself."""

    def test_the_contract_declares_what_it_does_not_do(self):
        import io, contextlib, json
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            B13C.main(["--contract"])
        contract = json.loads(buffer.getvalue())
        self.assertFalse(contract["llm_in_decision_path"])
        self.assertFalse(contract["network_collection_performed"])
        self.assertEqual(contract["vendors_selected"], [])
        self.assertEqual(len(contract["refusing_computations"]), 6)

    def test_the_taxonomy_names_no_vendor(self):
        """A kind called `tweet` would bake one product into the schema and stop describing the
        next one."""
        banned = ("tweet", "twitter", "x_com", "telegram", "discord", "reddit", "coingecko",
                  "birdeye", "dexscreener", "helius")
        text = " ".join(B13C.OBSERVATION_KINDS).lower()
        for name in banned:
            with self.subTest(vendor=name):
                self.assertNotIn(name, text)

    def test_an_undeclared_top_level_field_is_refused(self):
        item = observation()
        item["notes"] = "just a note"
        with self.assertRaisesRegex(B13C.ObservationRefused, "undeclared fields"):
            B13C.assert_observation(item)

    def test_an_undeclared_observation_kind_is_refused(self):
        with self.assertRaisesRegex(B13C.ObservationRefused, "is not one of"):
            observation(kind="tweet")

    def test_provenance_is_complete_or_the_record_is_refused(self):
        for field in B13C.PROVENANCE_FIELDS:
            with self.subTest(missing=field):
                item = observation()
                item["provenance"][field] = ""
                with self.assertRaisesRegex(B13C.ObservationRefused, "non-empty string"):
                    B13C.assert_observation(item)


class GateTests(unittest.TestCase):
    """The offline report's own conditions, exercised without rebuilding the corpus."""

    def clean_report(self):
        return {
            "errors": [], "observations": 16, "hashes_stable": 16, "chains": 13,
            "chains_validated": 13, "instants_replayed": 5, "order_independent": 5,
            "backfill_refused_at_every_instant": 5, "deletion_did_not_rewrite_history": 5,
            "prior_versions_preserved": 5, "identifier_collisions_refused": True,
            "unit_mixing_refused": True, "refusals_verified": {"sentiment": True},
            "derived_quantities_computed": [], "network_collection_performed": False,
            "vendors_selected": [], "llm_in_decision_path": False,
        }

    def test_a_clean_report_passes(self):
        self.assertEqual(FIXTURES.gate_failures(self.clean_report()), [])

    def test_every_gate_condition_can_fail(self):
        cases = {
            "integrity errors": {"errors": [{"error": "x"}]},
            "hashes stable": {"hashes_stable": 15},
            "chains validated": {"chains_validated": 12},
            "order_independent": {"order_independent": 4},
            "backfill_refused_at_every_instant": {"backfill_refused_at_every_instant": 4},
            "deletion_did_not_rewrite_history": {"deletion_did_not_rewrite_history": 4},
            "prior_versions_preserved": {"prior_versions_preserved": 4},
            "reused provider identifier": {"identifier_collisions_refused": False},
            "different units": {"unit_mixing_refused": False},
            "fail closed did not": {"refusals_verified": {"sentiment": False}},
            "derived quantity": {"derived_quantities_computed": ["sentiment"]},
            "no collection": {"network_collection_performed": True},
            "selects no vendor": {"vendors_selected": ["someone"]},
            "language model": {"llm_in_decision_path": True},
        }
        for expected, override in cases.items():
            with self.subTest(condition=expected):
                report = self.clean_report()
                report.update(override)
                failures = FIXTURES.gate_failures(report)
                self.assertTrue(any(expected in failure for failure in failures),
                                f"{expected!r} not in {failures}")

    def test_the_shipped_corpus_passes_its_own_gate(self):
        report = FIXTURES.assert_clean()
        self.assertEqual(report["errors"], [])
        self.assertFalse(report["content_reported"])
        self.assertFalse(report["burned_corpus_touched"])
        self.assertFalse(report["b11a_touched"])

    def test_the_report_publishes_no_content(self):
        """A report that quoted the payloads would put unlicensed text in a file and invite a
        transform nobody registered."""
        report = FIXTURES.check()
        text = B10B.canonical_json(report)
        for phrase in ("original wording", "synthetic post text", "$DOG", "example.invalid"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
