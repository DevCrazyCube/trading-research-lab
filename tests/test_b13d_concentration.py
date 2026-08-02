"""Tests for the B13d exact point-in-time concentration foundation.

Synthetic fixtures only. Nothing here queries an RPC, opens the burned corpus or touches B11a.

The arithmetic is checked against `fractions.Fraction` rather than against itself. An oracle from
the standard library is independent of the implementation, which a hand-copied expected value is
not.

One module graph is loaded for the whole file: loading the same module twice by path creates two
distinct exception classes, and an `assertRaises` on the wrong one never matches.
"""
import copy
import importlib.util
import pathlib
import unittest
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURES = _load("b13d_concentration_fixtures", "b13d_concentration_fixtures.py")
B13D = FIXTURES.B13D
B13C = B13D.B13C
B10B = B13D.B10B

MINT = FIXTURES.MINT
CREATOR = FIXTURES.CREATOR
at = FIXTURES.at
account = FIXTURES.account


def fraction(rational):
    return Fraction(rational["numerator"], rational["denominator"])


def corpus(name):
    return FIXTURES.build_fixture_corpus()[name]


def snapshot(accounts, supply=1_000_000_000, **kwargs):
    return FIXTURES.snapshot("test", accounts, supply, **kwargs)


TOTAL = B13D.DENOMINATOR_TOTAL_SUPPLY
CIRCULATING = B13D.DENOMINATOR_CIRCULATING_USER


# --------------------------------------------------------------------------------------------

class ExactArithmeticTests(unittest.TestCase):
    """Checked against Fraction, which knows nothing about this implementation."""

    def setUp(self):
        self.snapshot = corpus("curve_dominant")
        self.record = B13D.compute_concentration(self.snapshot)

    def units(self, roles=None):
        return [a["raw_units"] for a in self.snapshot["accounts"]
                if roles is None or a["role"] in roles]

    def test_top_k_shares_match_an_independent_oracle(self):
        cases = {TOTAL: (None, self.snapshot["declared_supply_units"]),
                 CIRCULATING: (B13D.CIRCULATING_USER_ROLES,
                               sum(self.units(B13D.CIRCULATING_USER_ROLES)))}
        for name, (roles, denominator) in cases.items():
            ranked = sorted(self.units(roles), reverse=True)
            for k in B13D.TOP_K:
                with self.subTest(denominator=name, k=k):
                    expected = Fraction(sum(ranked[:k]), denominator)
                    got = self.record["shares"]["by_account"][name][f"top_{k}"]["share"]
                    self.assertEqual(fraction(got), expected)

    def test_the_herfindahl_matches_an_independent_oracle(self):
        cases = {TOTAL: (None, self.snapshot["declared_supply_units"]),
                 CIRCULATING: (B13D.CIRCULATING_USER_ROLES,
                               sum(self.units(B13D.CIRCULATING_USER_ROLES)))}
        for name, (roles, denominator) in cases.items():
            with self.subTest(denominator=name):
                expected = sum((Fraction(u, denominator) ** 2 for u in self.units(roles)),
                               Fraction(0))
                got = self.record["shares"]["by_account"][name]["herfindahl"]
                self.assertEqual(fraction(got), expected)

    def test_every_published_rational_is_in_lowest_terms(self):
        """Two equal shares must have equal representations, or a hash comparison says they differ."""
        import math
        for grouping in ("by_account", "by_owner"):
            for name, block in self.record["shares"][grouping].items():
                if not block.get("defined"):
                    continue
                for field in [f"top_{k}" for k in B13D.TOP_K]:
                    with self.subTest(grouping=grouping, denominator=name, field=field):
                        share = block[field]["share"]
                        self.assertEqual(
                            math.gcd(abs(share["numerator"]), share["denominator"]), 1)

    def test_no_float_appears_anywhere_in_the_record(self):
        self.assertTrue(B13D.assert_no_float(self.record))
        broken = copy.deepcopy(self.record)
        broken["shares"]["by_account"][TOTAL]["top_1"]["share"]["numerator"] = 0.8
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "does not survive a double"):
            B13D.assert_no_float(broken)

    def test_a_rational_is_never_built_over_a_non_positive_denominator(self):
        for denominator in (0, -1):
            with self.subTest(denominator=denominator):
                with self.assertRaisesRegex(B13D.ConcentrationRefused, "undefined, not zero"):
                    B13D.rational(1, denominator)

    def test_rationals_compare_by_cross_multiplication(self):
        self.assertEqual(B13D.compare_rationals(B13D.rational(1, 3), B13D.rational(2, 6)), 0)
        self.assertEqual(B13D.compare_rationals(B13D.rational(1, 3), B13D.rational(1, 4)), 1)
        self.assertEqual(B13D.compare_rationals(B13D.rational(1, 4), B13D.rational(1, 3)), -1)

    def test_a_rational_not_in_lowest_terms_is_refused(self):
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "lowest terms"):
            B13D.assert_rational({"numerator": 2, "denominator": 4}, "share")


class DenominatorTests(unittest.TestCase):
    """Concentration is whatever the denominator says it is, so both are always published."""

    def test_both_denominators_are_always_published(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        for grouping in ("by_account", "by_owner"):
            with self.subTest(grouping=grouping):
                self.assertEqual(set(record["shares"][grouping]), set(B13D.DENOMINATORS))

    def test_a_record_publishing_only_one_denominator_is_refused(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        del record["shares"]["by_account"][CIRCULATING]
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "made on the reader's behalf"):
            B13D.assert_concentration(record)

    def test_the_two_denominators_genuinely_disagree(self):
        """The whole reason both are published. A curve holding 80% makes every user look small
        under total supply and large under circulating user, and both figures are true."""
        record = B13D.compute_concentration(corpus("curve_dominant"))
        under_total = fraction(record["shares"]["by_account"][TOTAL]["top_1"]["share"])
        under_user = fraction(record["shares"]["by_account"][CIRCULATING]["top_1"]["share"])
        self.assertNotEqual(under_total, under_user)

    def test_the_circulating_denominator_is_a_sum_of_inclusions_not_a_subtraction(self):
        """A sum names what it included; a subtraction hides what it removed. Here the difference
        is visible: the residual and the excluded roles do not have to reconcile to the
        denominator, but the user balances do."""
        record = B13D.compute_concentration(corpus("every_role"))
        published = record["shares"]["by_account"][CIRCULATING]["denominator_units"]
        self.assertEqual(published, record["by_role"][B13D.ROLE_USER]["units"])

    def test_swapping_a_denominator_is_caught(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        record["shares"]["by_account"][CIRCULATING]["denominator_units"] = \
            record["accounting"]["declared_supply_units"]
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "how an exclusion hides"):
            B13D.assert_concentration(record)

    def test_a_total_supply_denominator_that_is_not_the_supply_is_caught(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        record["shares"]["by_account"][TOTAL]["denominator_units"] += 1
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "not the declared supply"):
            B13D.assert_concentration(record)

    def test_each_view_states_which_balances_it_ranked(self):
        """The two views differ in NUMERATOR as well as denominator, and a reader given the ratio
        without the scope cannot tell which they have."""
        record = B13D.compute_concentration(corpus("curve_dominant"))
        self.assertEqual(record["shares"]["by_account"][TOTAL]["scope_roles"], list(B13D.ROLES))
        self.assertEqual(record["shares"]["by_account"][CIRCULATING]["scope_roles"],
                         list(B13D.CIRCULATING_USER_ROLES))

    def test_an_empty_denominator_is_undefined_not_zero(self):
        record = B13D.compute_concentration(corpus("no_circulating"))
        block = record["shares"]["by_account"][CIRCULATING]
        self.assertFalse(block["defined"])
        self.assertNotIn("top_1", block)
        self.assertIn("no share of it exists", block["undefined_reason"])


class RoleTests(unittest.TestCase):
    """Unknown is never a user, and no balance escapes the accounting."""

    def test_every_role_is_published_even_when_empty(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        self.assertEqual(set(record["by_role"]), set(B13D.ROLES))
        self.assertEqual(record["by_role"][B13D.ROLE_BURN], {"account_count": 0, "units": 0})

    def test_the_roles_account_for_every_unit_and_every_account(self):
        for name in ("curve_dominant", "every_role", "zero_balance"):
            with self.subTest(snapshot=name):
                record = B13D.compute_concentration(corpus(name))
                self.assertEqual(sum(b["units"] for b in record["by_role"].values()),
                                 record["accounting"]["units_held_in_accounts"])
                self.assertEqual(sum(b["account_count"] for b in record["by_role"].values()),
                                 record["accounting"]["accounts_enumerated"])

    def test_an_unknown_role_is_not_counted_as_a_user(self):
        """Counting unknown as user would enlarge the denominator and shrink every share — the
        flattering direction, and therefore the one to refuse by construction."""
        self.assertNotIn(B13D.ROLE_UNKNOWN, B13D.CIRCULATING_USER_ROLES)
        record = B13D.compute_concentration(corpus("every_role"))
        self.assertEqual(record["shares"]["by_account"][CIRCULATING]["denominator_units"],
                         100_000_000)
        self.assertEqual(record["by_role"][B13D.ROLE_UNKNOWN]["units"], 40_000_000)

    def test_the_curve_balance_cannot_be_silently_excluded(self):
        """It is published as its own role and included in the total-supply ranking; dropping it
        would change both the denominator and the top-1 holder."""
        record = B13D.compute_concentration(corpus("curve_dominant"))
        self.assertEqual(record["by_role"][B13D.ROLE_BONDING_CURVE]["units"], 800_000_000)
        top = record["shares"]["by_account"][TOTAL]["top_1"]
        self.assertEqual(top["units"], 800_000_000)

    def test_a_role_missing_from_the_accounting_is_refused(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        del record["by_role"][B13D.ROLE_BURN]
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "nobody has to explain"):
            B13D.assert_concentration(record)

    def test_a_role_balance_that_belongs_to_no_role_is_refused(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        record["by_role"][B13D.ROLE_BONDING_CURVE]["units"] -= 1
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "an exclusion could hide"):
            B13D.assert_concentration(record)

    def test_a_role_account_count_that_does_not_add_up_is_refused(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        record["by_role"][B13D.ROLE_USER]["account_count"] -= 1
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "every enumerated account"):
            B13D.assert_concentration(record)

    def test_an_undeclared_role_is_refused(self):
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "must be said out loud"):
            snapshot([account("a", 1, role="probably_a_user")])

    def test_a_role_without_evidence_is_refused(self):
        broken = account("a", 1)
        broken["role_evidence"] = ""
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "read as a fact"):
            snapshot([broken])


class OwnerVersusAccountTests(unittest.TestCase):
    """One owner can hold many accounts, so collapsing changes every figure here."""

    def test_collapsing_changes_the_answer_which_is_why_both_are_published(self):
        record = B13D.compute_concentration(corpus("owner_split"))
        by_account = fraction(record["shares"]["by_account"][TOTAL]["top_1"]["share"])
        by_owner = fraction(record["shares"]["by_owner"][TOTAL]["top_1"]["share"])
        self.assertEqual(by_account, Fraction(300_000_000, 1_000_000_000))
        self.assertEqual(by_owner, Fraction(400_000_000, 1_000_000_000))
        self.assertGreater(by_owner, by_account)

    def test_one_unresolved_account_blocks_collapsing_entirely(self):
        """That account could be the largest holder's, so a top-1 without it is a lower bound
        wearing the costume of a measurement."""
        record = B13D.compute_concentration(corpus("unresolved_owner"))
        self.assertFalse(record["accounting"]["owner_grouping_available"])
        self.assertIn("lower bound", record["accounting"]["owner_grouping_unavailable_reason"])
        for name in B13D.DENOMINATORS:
            with self.subTest(denominator=name):
                self.assertFalse(record["shares"]["by_owner"][name]["defined"])

    def test_holder_counts_are_published_per_grouping(self):
        record = B13D.compute_concentration(corpus("owner_split"))
        self.assertEqual(record["shares"]["by_account"][TOTAL]["holder_count"], 7)
        self.assertEqual(record["shares"]["by_owner"][TOTAL]["holder_count"], 4)

    def test_an_unresolved_account_may_not_name_an_owner(self):
        broken = account("a", 1, resolved=False)
        broken["owner"] = "OwnerWeGuessed"
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "not a name we happen to have"):
            snapshot([broken])

    def test_exact_owner_evidence_must_actually_be_stated(self):
        broken = account("a", 1)
        broken["owner_evidence"] = ""
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "not that we are confident"):
            snapshot([broken])

    def test_duplicate_owner_accounts_are_summed_never_double_counted(self):
        owner = "OwnerWithTwoAccounts11111111111111111111"
        record = B13D.compute_concentration(snapshot([
            account("acct-1", 300_000_000, owner=owner),
            account("acct-2", 200_000_000, owner=owner),
            account("acct-3", 500_000_000)]))
        self.assertEqual(record["shares"]["by_owner"][TOTAL]["holder_count"], 2)
        self.assertEqual(record["shares"]["by_owner"][TOTAL]["top_1"]["units"], 500_000_000)
        self.assertEqual(record["shares"]["by_owner"][TOTAL]["top_5"]["units"], 1_000_000_000)

    def test_the_same_token_account_twice_is_refused(self):
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "both errors point the same way"):
            snapshot([account("acct-1", 100), account("acct-1", 200)])


class TopKTests(unittest.TestCase):
    """A top-k that takes the wrong number of entries understates concentration."""

    def test_top_k_takes_exactly_min_of_k_and_available(self):
        record = B13D.compute_concentration(corpus("fewer_than_k"))
        block = record["shares"]["by_account"][TOTAL]
        self.assertEqual(block["top_1"]["entries_counted"], 1)
        self.assertEqual(block["top_5"]["entries_counted"], 3)
        self.assertEqual(block["top_10"]["entries_counted"], 3)
        self.assertEqual(block["top_10"]["entries_available"], 3)

    def test_a_short_top_k_says_so_rather_than_looking_like_a_full_one(self):
        """A "top 10" over three accounts is the whole set, and a reader not told that will compare
        it against a genuine top 10 somewhere else."""
        block = B13D.compute_concentration(corpus("fewer_than_k"))["shares"]["by_account"][TOTAL]
        self.assertLess(block["top_10"]["entries_counted"], 10)
        self.assertEqual(fraction(block["top_10"]["share"]), Fraction(1))

    def test_a_top_k_counting_more_than_k_is_refused(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        record["shares"]["by_account"][TOTAL]["top_1"]["entries_counted"] = 2
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "is not a top-"):
            B13D.assert_concentration(record)

    def test_a_top_k_counting_fewer_than_available_is_refused(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        record["shares"]["by_account"][TOTAL]["top_5"]["entries_counted"] = 4
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "silently understates"):
            B13D.assert_concentration(record)

    def test_top_k_must_be_monotone(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        record["shares"]["by_account"][TOTAL]["top_1"]["share"] = B13D.rational(1, 1)
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "arithmetically impossible"):
            B13D.assert_concentration(record)

    def test_ties_rank_deterministically(self):
        """Driven directly on the ranking, because the published sums are equal under ties either
        way. The tiebreak exists so that a future reader of the ranking — or a future field that
        publishes it — gets the same order every time, and a sort key nobody can observe today is
        a sort key that silently stops working tomorrow."""
        self.assertEqual(B13D._sorted_balances([("b", 5), ("a", 5), ("c", 9)]),
                         [("c", 9), ("a", 5), ("b", 5)])
        self.assertEqual(B13D._sorted_balances([("a", 5), ("b", 5)]),
                         B13D._sorted_balances([("b", 5), ("a", 5)]))
        accounts = [account(f"tie-{i}", 250_000_000) for i in range(4)]
        first = B13D.compute_concentration(snapshot(accounts))
        second = B13D.compute_concentration(snapshot(list(reversed(accounts))))
        self.assertEqual(first["shares"], second["shares"])

    def test_zero_balance_accounts_are_kept_but_not_counted_as_holders(self):
        record = B13D.compute_concentration(corpus("zero_balance"))
        self.assertEqual(record["accounting"]["accounts_enumerated"], 3)
        self.assertEqual(record["accounting"]["accounts_with_positive_balance"], 2)
        self.assertEqual(record["accounting"]["zero_balance_account_count_observed"], 1)
        self.assertEqual(record["shares"]["by_account"][TOTAL]["holder_count"], 2)

    def test_the_holder_count_must_match_the_ranked_balances(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        record["shares"]["by_account"][TOTAL]["holder_count"] += 1
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "disagrees with the number"):
            B13D.assert_concentration(record)


class ReconciliationTests(unittest.TestCase):
    """Every unit is accounted for, or the snapshot is refused."""

    def test_a_negative_balance_is_refused_rather_than_clamped(self):
        """A negative raw balance means the decode is wrong; clamping it would turn a broken parse
        into a plausible holder."""
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "must not be negative"):
            snapshot([account("a", -1)])

    def test_accounts_holding_more_than_the_supply_are_refused(self):
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "a shortfall of"):
            snapshot([account("a", 2_000_000_000)], supply=1_000_000_000)

    def test_a_complete_enumeration_must_sum_to_the_supply(self):
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "unaccounted for"):
            snapshot([account("a", 400_000_000)], supply=1_000_000_000)

    def test_an_incomplete_enumeration_publishes_its_residual(self):
        record = B13D.compute_concentration(corpus("incomplete"))
        self.assertFalse(record["accounting"]["enumeration_complete"])
        self.assertEqual(record["accounting"]["supply_residual_units"], 500_000_000)
        self.assertEqual(record["accounting"]["units_held_in_accounts"]
                         + record["accounting"]["supply_residual_units"],
                         record["accounting"]["declared_supply_units"])

    def test_an_incomplete_enumeration_may_not_be_promoted_to_complete(self):
        record = B13D.compute_concentration(corpus("incomplete"))
        record["accounting"]["enumeration_complete"] = True
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "every unit is accounted for"):
            B13D.assert_concentration(record)

    def test_the_residual_may_not_be_absorbed(self):
        record = B13D.compute_concentration(corpus("incomplete"))
        record["accounting"]["supply_residual_units"] = 0
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "every unit is somewhere"):
            B13D.assert_concentration(record)

    def test_the_enumeration_count_must_match_the_accounts_present(self):
        accounts = [account("a", 1_000_000_000)]
        broken = FIXTURES.completeness(accounts)
        broken["accounts_enumerated"] = 5
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "disagrees with its own output"):
            B13D.build_snapshot(MINT, 6, at(1), "provenance", accounts, 1_000_000_000, broken,
                                source_sha256="x")

    def test_an_enumeration_must_name_its_sources(self):
        accounts = [account("a", 1_000_000_000)]
        broken = FIXTURES.completeness(accounts)
        broken["source_hashes"] = []
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "cannot name its source"):
            B13D.build_snapshot(MINT, 6, at(1), "provenance", accounts, 1_000_000_000, broken,
                                source_sha256="x")

    def test_a_second_mint_in_the_enumeration_is_refused(self):
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "concentration figure about neither"):
            snapshot([account("a", 500_000_000),
                      account("b", 500_000_000, mint=FIXTURES.OTHER_MINT)])

    def test_mixed_decimals_are_refused(self):
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "power of ten"):
            snapshot([account("a", 500_000_000),
                      account("b", 500_000_000, decimals=9)])

    def test_the_positive_and_zero_counts_must_sum_to_the_enumeration(self):
        record = B13D.compute_concentration(corpus("zero_balance"))
        record["accounting"]["zero_balance_account_count_observed"] = 0
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "quietly left the holder set"):
            B13D.assert_concentration(record)


class PointInTimeTests(unittest.TestCase):
    """A later holder state cannot be backfilled into an earlier decision."""

    def test_a_snapshot_at_t0_is_available(self):
        self.assertTrue(B13D.available_at(corpus("curve_dominant"), at(430_000_000)))

    def test_a_snapshot_after_t0_is_not(self):
        later = corpus("later_state")
        self.assertFalse(B13D.available_at(later, at(430_000_000)))
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "encode the outcome in the input"):
            B13D.require_available_at(later, at(430_000_000))

    def test_the_boundary_is_exclusive_one_coordinate_later(self):
        snap = corpus("curve_dominant")
        self.assertTrue(B13D.available_at(snap, at(430_000_000, 0, 0, 0)))
        self.assertFalse(B13D.available_at(snap, at(429_999_999, 9, 9, 9)))

    def test_selection_returns_the_latest_snapshot_actually_available(self):
        everything = list(FIXTURES.build_fixture_corpus().values())
        early = B13D.select_snapshot(everything, at(430_000_000))
        self.assertTrue(B13D.available_at(early, at(430_000_000)))
        self.assertNotEqual(early["snapshot_sha256"], corpus("later_state")["snapshot_sha256"])
        late = B13D.select_snapshot(everything, at(430_009_999))
        self.assertEqual(late["snapshot_sha256"], corpus("later_state")["snapshot_sha256"])

    def test_no_snapshot_at_all_is_absent_and_not_a_low_concentration(self):
        result = B13D.select_snapshot(list(FIXTURES.build_fixture_corpus().values()), at(1))
        self.assertTrue(B13D.is_absent(result))
        self.assertIn("not the same as it being low", result.detail)
        with self.assertRaises(B13C.ObservationRefused):
            bool(result)

    def test_the_rule_travels_on_every_record(self):
        snap = copy.deepcopy(corpus("curve_dominant"))
        snap["point_in_time_rule"] = "roughly before t0"
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "not the one this module applies"):
            B13D.assert_snapshot(snap)

    def test_both_rules_travel_on_the_computed_record(self):
        """A record that restated either rule loosely would be read under the loose one."""
        record = B13D.compute_concentration(corpus("curve_dominant"))
        self.assertEqual(record["point_in_time_rule"], B13D.POINT_IN_TIME_RULE)
        self.assertEqual(record["denominator_rule"], B13D.DENOMINATOR_RULE)
        for field in ("point_in_time_rule", "denominator_rule"):
            with self.subTest(field=field):
                broken = copy.deepcopy(record)
                broken[field] = "whichever denominator suits"
                with self.assertRaisesRegex(B13D.ConcentrationRefused, "not this module's"):
                    B13D.assert_concentration(broken)


class CreatorShareTests(unittest.TestCase):
    """A creator share attributed on a guess is worse than none."""

    def test_an_exact_binding_yields_a_share_under_both_denominators(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        for name, denominator in ((TOTAL, 1_000_000_000), (CIRCULATING, 200_000_000)):
            with self.subTest(denominator=name):
                block = record["creator"][name]
                self.assertTrue(block["defined"])
                self.assertEqual(block["units"], 120_000_000)
                self.assertEqual(fraction(block["share"]),
                                 Fraction(120_000_000, denominator))

    def test_the_creator_numerator_is_scoped_like_its_denominator(self):
        """A creator holding through an excluded role would otherwise contribute to the numerator
        but not the denominator, and produce a share above one."""
        record = B13D.compute_concentration(snapshot(
            [account("creator-vault", 900_000_000, role=B13D.ROLE_VAULT, owner=CREATOR),
             account("user-1", 100_000_000)], creator_binding=FIXTURES.exact_creator()))
        block = record["creator"][CIRCULATING]
        self.assertEqual(block["units"], 0)
        self.assertLessEqual(fraction(block["share"]), Fraction(1))
        self.assertEqual(record["creator"][TOTAL]["units"], 900_000_000)

    def test_no_binding_means_no_share(self):
        record = B13D.compute_concentration(corpus("owner_split"))
        for name in B13D.DENOMINATORS:
            with self.subTest(denominator=name):
                self.assertFalse(record["creator"][name]["defined"])
                self.assertIn("worse than no share", record["creator"][name]["undefined_reason"])

    def test_an_unverified_binding_yields_no_share(self):
        binding = {"status": B13D.CREATOR_BINDING_UNVERIFIED, "address": CREATOR,
                   "evidence": "a name that looked right"}
        record = B13D.compute_concentration(snapshot(
            [account("a", 1_000_000_000, owner=CREATOR)], creator_binding=binding))
        self.assertFalse(record["creator"][TOTAL]["defined"])

    def test_an_unresolved_account_blocks_the_creator_share(self):
        record = B13D.compute_concentration(snapshot(
            [account("a", 500_000_000, owner=CREATOR), account("b", 500_000_000, resolved=False)],
            creator_binding=FIXTURES.exact_creator()))
        self.assertFalse(record["creator"][TOTAL]["defined"])
        self.assertIn("lower bound", record["creator"][TOTAL]["undefined_reason"])

    def test_an_exact_binding_must_show_its_evidence(self):
        binding = {"status": B13D.CREATOR_BINDING_EXACT, "address": CREATOR, "evidence": ""}
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "published as a creator share"):
            snapshot([account("a", 1_000_000_000)], creator_binding=binding)

    def test_an_absent_binding_may_not_name_an_address(self):
        binding = {"status": B13D.CREATOR_BINDING_ABSENT, "address": CREATOR, "evidence": None}
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "we do not have one"):
            snapshot([account("a", 1_000_000_000)], creator_binding=binding)

    def test_the_creator_share_is_published_under_both_denominators_or_refused(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        del record["creator"][CIRCULATING]
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "under both denominators"):
            B13D.assert_concentration(record)


class ClusterRefusalTests(unittest.TestCase):
    """The most dangerous number this project could publish, and it is structurally unavailable."""

    def test_no_artifact_type_is_accepted(self):
        self.assertEqual(B13D.ACCEPTED_CLUSTER_ARTIFACT_TYPES, ())

    def test_a_cluster_adjusted_figure_always_refuses(self):
        for artifact in (None, {}, {"type": "anything"}, {"clusters": [["a", "b"]]}):
            with self.subTest(artifact=artifact):
                with self.assertRaises(B13D.ClusterAdjustmentRefused):
                    B13D.cluster_adjusted_concentration(corpus("curve_dominant"), artifact)

    def test_a_b13b_association_ledger_gets_its_own_refusal(self):
        """Passing it here would launder an explicit "we do not know" into a merge, and the reader
        needs to be told which mistake they made."""
        ledger = {"confidence_status": "uncalibrated_evidence_only", "links": [],
                  "evidence_hash_chain_sha256": "0" * 64}
        with self.assertRaisesRegex(B13D.ClusterAdjustmentRefused, "ASSOCIATION EVIDENCE LEDGER"):
            B13D.cluster_adjusted_concentration(corpus("curve_dominant"), ledger)

    def test_each_recognition_path_stands_on_its_own(self):
        """A ledger is recognised by its self-declaration OR by its shape. Either alone must be
        enough, because a caller stripping one of them is exactly how a ledger gets mistaken for a
        cluster map."""
        by_declaration = {"confidence_status": "uncalibrated_evidence_only"}
        by_shape = {"links": [], "evidence_hash_chain_sha256": "0" * 64}
        for artifact in (by_declaration, by_shape):
            with self.subTest(artifact=sorted(artifact)):
                self.assertTrue(B13D._looks_like_association_ledger(artifact))
                with self.assertRaisesRegex(B13D.ClusterAdjustmentRefused,
                                            "ASSOCIATION EVIDENCE LEDGER"):
                    B13D.cluster_adjusted_concentration(corpus("curve_dominant"), artifact)
        for artifact in (None, {}, {"clusters": [["a"]]}, "not a mapping"):
            with self.subTest(artifact=artifact):
                self.assertFalse(B13D._looks_like_association_ledger(artifact))

    def test_a_real_b13b_ledger_is_recognised(self):
        b13b = _load("b13b_association", "b13b_association.py")
        events = [{"slot": 100, "transaction_index": 0, "outer_index": 0, "inner_index": 0,
                   "kind": b13b.B13A.EVENT_TRANSFER, "from_address": "AAAa", "to_address": "BBBb",
                   "lamports": 5, "source_sha256": "src-1"}]
        coverage = {"first_slot": 1, "last_slot": 200, "source_population": "synthetic",
                    "left_truncated": False, "right_truncated": False, "complete": True,
                    "provenance_sha256": "p" * 10,
                    "decode_accounting": {
                        "transactions_required": 0, "transactions_with_body": 0,
                        "transactions_missing_body": 0, "transactions_missing_coordinate": 0,
                        "system_instructions_total": 0, "decoded_moving": 0,
                        "decoded_non_moving": 0, "undecodable": 0, "edges_emitted": 0,
                        "moving_self_transfer": 0, "moving_without_addresses": 0,
                        "unresolved": []}}
        ledger = b13b.build_association_ledger(
            events, ["AAAa", "BBBb"],
            {"slot": 200, "transaction_index": 0, "outer_index": 0, "inner_index": 0}, coverage)
        self.assertTrue(B13D._looks_like_association_ledger(ledger))
        with self.assertRaisesRegex(B13D.ClusterAdjustmentRefused,
                                    "do not assert common control"):
            B13D.cluster_adjusted_concentration(corpus("curve_dominant"), ledger)

    def test_connected_components_refuses(self):
        with self.assertRaisesRegex(B13D.ClusterAdjustmentRefused, "never an A—C link"):
            B13D.connected_components([])

    def test_the_refusal_names_what_a_future_artifact_would_need(self):
        try:
            B13D.cluster_adjusted_concentration(corpus("curve_dominant"), {})
        except B13D.ClusterAdjustmentRefused as error:
            for requirement in ("calibrated", "preregistered", "point-in-time", "provenanced"):
                with self.subTest(requirement=requirement):
                    self.assertIn(requirement, str(error))

    def test_the_record_carries_no_cluster_field_at_all(self):
        """B13b's judgement, unchanged: a field named for a quantity we refuse to compute teaches
        the next reader that we compute it."""
        record = B13D.compute_concentration(corpus("curve_dominant"))
        text = B10B.canonical_json(record).lower()
        for banned in ("cluster", "adjusted", "threshold", "veto", "rug"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, text)

    def test_a_judgement_field_name_is_refused_wherever_it_appears(self):
        for name in ("cluster_id", "adjusted_share", "rug_probability", "risk_score",
                     "concentration_threshold", "veto", "profitability_class", "predicted"):
            with self.subTest(field=name):
                record = B13D.compute_concentration(corpus("curve_dominant"))
                record["accounting"][name] = 1
                with self.assertRaisesRegex(B13D.ConcentrationRefused, "everything downstream"):
                    B13D.assert_no_judgement(record)

    def test_a_cluster_refusal_is_distinguishable_from_a_malformed_snapshot(self):
        self.assertTrue(issubclass(B13D.ClusterAdjustmentRefused, B13D.ConcentrationRefused))


class DeterminismTests(unittest.TestCase):
    """Identical balances in any order give a byte-identical record."""

    def test_account_order_does_not_change_the_result(self):
        snap = corpus("curve_dominant")
        shuffled = dict(snap, accounts=list(reversed(snap["accounts"])))
        shuffled["snapshot_sha256"] = B13D.snapshot_hash(shuffled)
        self.assertEqual(B13D.compute_concentration(snap)["shares"],
                         B13D.compute_concentration(shuffled)["shares"])

    def test_rebuilding_the_corpus_is_byte_identical(self):
        self.assertEqual(B10B.canonical_json(FIXTURES.build_fixture_corpus()),
                         B10B.canonical_json(FIXTURES.build_fixture_corpus()))

    def test_source_hash_drift_is_caught(self):
        snap = copy.deepcopy(corpus("curve_dominant"))
        snap["source_sha256"] = "f" * 64
        self.assertNotEqual(B13D.snapshot_hash(snap), snap["snapshot_sha256"])

    def test_changing_one_balance_changes_every_downstream_hash(self):
        base = B13D.compute_concentration(corpus("curve_dominant"))
        snap = copy.deepcopy(corpus("curve_dominant"))
        snap["accounts"][1]["raw_units"] -= 1
        snap["declared_supply_units"] -= 1
        snap["snapshot_sha256"] = B13D.snapshot_hash(snap)
        self.assertNotEqual(B13D.compute_concentration(snap)["concentration_sha256"],
                            base["concentration_sha256"])

    def test_the_record_hash_covers_everything_but_itself(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        self.assertEqual(record["concentration_sha256"], B13D.concentration_hash(record))

    def test_an_undeclared_top_level_field_is_refused(self):
        record = B13D.compute_concentration(corpus("curve_dominant"))
        record["notes"] = "just a note"
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "undeclared fields"):
            B13D.assert_concentration(record)

    def test_an_undeclared_snapshot_field_is_refused(self):
        snap = copy.deepcopy(corpus("curve_dominant"))
        snap["extra"] = 1
        with self.assertRaisesRegex(B13D.ConcentrationRefused, "nobody reviewed"):
            B13D.assert_snapshot(snap)


class ContractAndGateTests(unittest.TestCase):
    """What the module says about itself, and the report's own conditions."""

    def test_the_contract_declares_what_it_does_not_do(self):
        import io, contextlib, json
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            B13D.main(["--contract"])
        contract = json.loads(buffer.getvalue())
        self.assertFalse(contract["cluster_adjustment_available"])
        self.assertFalse(contract["connected_components_inferred"])
        self.assertFalse(contract["floats_used"])
        self.assertEqual(contract["thresholds_chosen"], [])
        self.assertEqual(contract["accepted_cluster_artifact_types"], [])
        self.assertEqual(contract["denominators"], list(B13D.DENOMINATORS))

    def clean_report(self):
        return {"errors": [], "snapshots": 9, "snapshots_reconciled": 9,
                "concentrations_computed": 9, "both_denominators_published": 9,
                "shares_are_exact_rationals": 9, "top_k_monotone": 9,
                "roles_account_for_every_unit": 9, "hashes_stable": 9, "order_independent": 9,
                "future_snapshot_refused": 3, "point_in_time_selections": 3,
                "owner_grouping_refused_count": 1, "zero_balance_accounts_preserved": 1,
                "undefined_denominator_not_reported_as_zero": 1, "residual_published": 1,
                "cluster_adjustment_refused": True,
                "association_ledger_rejected_as_cluster_map": True,
                "connected_components_refused": True,
                "concentration_values_reported": False, "thresholds_chosen": [],
                "rpc_queried": False, "burned_corpus_touched": False, "b11a_touched": False}

    def test_a_clean_report_passes(self):
        self.assertEqual(FIXTURES.gate_failures(self.clean_report()), [])

    def test_every_gate_condition_can_fail(self):
        cases = {
            "integrity errors": {"errors": [{"error": "x"}]},
            "snapshots_reconciled": {"snapshots_reconciled": 8},
            "both_denominators_published": {"both_denominators_published": 8},
            "shares_are_exact_rationals": {"shares_are_exact_rationals": 8},
            "top_k_monotone": {"top_k_monotone": 8},
            "roles_account_for_every_unit": {"roles_account_for_every_unit": 8},
            "hashes_stable": {"hashes_stable": 8},
            "order_independent": {"order_independent": 8},
            "later holder state": {"future_snapshot_refused": 2},
            "collapse accounts to owners": {"owner_grouping_refused_count": 0},
            "zero-balance preservation": {"zero_balance_accounts_preserved": 0},
            "undefined denominator": {"undefined_denominator_not_reported_as_zero": 0},
            "supply residual": {"residual_published": 0},
            "cluster_adjustment_refused": {"cluster_adjustment_refused": False},
            "association_ledger_rejected_as_cluster_map":
                {"association_ledger_rejected_as_cluster_map": False},
            "connected_components_refused": {"connected_components_refused": False},
            "concentration value": {"concentration_values_reported": True},
            "chooses no threshold": {"thresholds_chosen": ["top1>0.3"]},
            "queries nothing": {"rpc_queried": True},
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
        self.assertFalse(report["rpc_queried"])
        self.assertFalse(report["burned_corpus_touched"])
        self.assertFalse(report["b11a_touched"])

    def test_the_report_publishes_no_concentration_value(self):
        """A share published here would be read as a finding about a token that does not exist."""
        report = FIXTURES.check()
        self.assertFalse(report["concentration_values_reported"])
        for path, value in B13D._walk(report):
            if isinstance(value, dict) and set(value) == {"numerator", "denominator"}:
                self.fail(f"{path} publishes a share")


if __name__ == "__main__":
    unittest.main()
