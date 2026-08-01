"""B9m causal partition of the unattributed transactions.

The property that matters is that the categories are mutually exclusive AND exhaustive: every
unattributed transaction gets exactly one cause, and no transaction falls through. A partition that
silently drops rows would understate whichever cause it drops, which is the failure this module
exists to prevent.
"""
import importlib.util
import itertools
import pathlib
import unittest

import tests.test_b9d_transaction_bodies as B9DT

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9m_unattributed_partition", ROOT / "scripts" / "b9m_unattributed_partition.py")
B9M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9M)

B9D = B9M.B9D
NATIVE = B9D.NATIVE_QUOTE_MINT
SOME_UNPINNED = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"


def evidence(trade_count=1, quote_mints=None, unpinned=()):
    if quote_mints is None:
        quote_mints = [NATIVE] * trade_count
    return {"trade_count": trade_count, "quote_mints": quote_mints,
            "programs": set(), "unpinned_programs": list(unpinned)}


class ExclusivityTests(unittest.TestCase):

    def test_every_combination_of_evidence_lands_in_exactly_one_category(self):
        """Exhaustive over the evidence space, not a sample of it.

        If a future category is added without an ordering rule, some combination will either match
        none or be ambiguous, and this fails.
        """
        for count, mint, unpinned in itertools.product(
                (0, 1, 2, 3), (NATIVE, "So11111111111111111111111111111111111111112"),
                ((), (SOME_UNPINNED,))):
            with self.subTest(count=count, mint=mint, unpinned=bool(unpinned)):
                category = B9M.classify_unattributed(
                    evidence(count, [mint] * count, unpinned))
                self.assertIn(category, B9M.PARTITION_CATEGORIES)

    def test_a_nonnative_quote_dominates_every_other_signal(self):
        """Raw token units are not lamports. Whatever else is true, they cannot be summed."""
        for count, unpinned in itertools.product((1, 2), ((), (SOME_UNPINNED,))):
            with self.subTest(count=count, unpinned=bool(unpinned)):
                self.assertEqual(
                    B9M.classify_unattributed(evidence(count, ["OTHER"] * count, unpinned)),
                    B9M.NONNATIVE_QUOTE)

    def test_each_category_is_reachable(self):
        """A category nothing can reach is a category that explains nothing."""
        reached = {
            B9M.classify_unattributed(evidence(1, ["OTHER"])),
            B9M.classify_unattributed(evidence(0, [])),
            B9M.classify_unattributed(evidence(2)),
            B9M.classify_unattributed(evidence(1, unpinned=(SOME_UNPINNED,))),
            B9M.classify_unattributed(evidence(1)),
        }
        self.assertEqual(reached, set(B9M.PARTITION_CATEGORIES))

    def test_only_pinned_programs_yields_the_bounded_residue(self):
        self.assertEqual(B9M.classify_unattributed(evidence(1)), B9M.PINNED_ONLY)

    def test_every_category_states_its_cause(self):
        """A category name without a stated cause is a label, not an explanation."""
        for category in B9M.PARTITION_CATEGORIES:
            with self.subTest(category=category):
                self.assertIn(category, B9M.CATEGORY_CAUSE)
                self.assertGreater(len(B9M.CATEGORY_CAUSE[category]), 80)


class PinnedProgramTests(unittest.TestCase):

    def test_the_pump_fee_program_is_not_treated_as_pinned(self):
        """It appears in 100% of unattributed transactions and 98.3% of exact ones.

        Its presence is nearly constant across the whole population, so it discriminates nothing.
        Adding it to PINNED_PROGRAMS would silently move transactions into the bounded residue on
        the strength of a program whose ABI is not actually pinned.
        """
        self.assertNotIn(B9M.PUMP_FEE_PROGRAM, B9M.PINNED_PROGRAMS)
        self.assertEqual(
            B9M.classify_unattributed(evidence(1, unpinned=(B9M.PUMP_FEE_PROGRAM,))),
            B9M.THIRD_PARTY_PROGRAM)

    def test_the_pinned_set_is_exactly_the_abis_this_project_has_pinned(self):
        """Membership means 'we pinned its ABI', not 'we recognise the address'.

        Widening this set is how the bounded residue would quietly grow to include transactions
        whose lamport movement nobody can actually derive.
        """
        self.assertIn(B9D.PUMP_PROGRAM, B9M.PINNED_PROGRAMS)
        self.assertIn("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", B9M.PINNED_PROGRAMS)
        self.assertEqual(len(B9M.PINNED_PROGRAMS), 8)

    def test_the_pump_fee_only_subcount_does_not_become_a_category(self):
        """It is reported alongside the partition, never as a member of it.

        Promoting it to a category would make `pfee` behave as if it were pinned, which is exactly
        the conclusion the 98.3% base rate forbids.
        """
        pfee_only = evidence(1, unpinned=(B9M.PUMP_FEE_PROGRAM,))
        self.assertTrue(B9M.is_pump_fee_only(pfee_only))
        self.assertEqual(B9M.classify_unattributed(pfee_only), B9M.THIRD_PARTY_PROGRAM)
        self.assertNotIn("pump_fee_only", B9M.PARTITION_CATEGORIES)

    def test_pump_fee_alongside_another_program_is_not_the_tractable_residue(self):
        """One aggregator in the transaction is enough to put the lamports out of reach."""
        self.assertFalse(B9M.is_pump_fee_only(
            evidence(1, unpinned=(B9M.PUMP_FEE_PROGRAM, SOME_UNPINNED))))
        self.assertFalse(B9M.is_pump_fee_only(evidence(1, unpinned=(SOME_UNPINNED,))))

    def test_an_unrecognised_program_makes_a_transaction_third_party(self):
        self.assertEqual(
            B9M.classify_unattributed(evidence(1, unpinned=("SomeUnknownProgram11111",))),
            B9M.THIRD_PARTY_PROGRAM)


class DirectRouteTests(unittest.TestCase):
    """The direct route is what the simulator can submit; measured at 99.716% exact."""

    def route(self, programs):
        return {"trade_count": 1, "quote_mints": [NATIVE], "programs": set(programs),
                "unpinned_programs": sorted(set(programs) - B9M.PINNED_PROGRAMS)}

    def test_a_pump_only_transaction_is_on_the_direct_route(self):
        self.assertTrue(B9M.is_direct_route(self.route(
            {B9D.PUMP_PROGRAM, "11111111111111111111111111111111", B9M.PUMP_FEE_PROGRAM})))

    def test_an_aggregator_takes_a_transaction_off_the_direct_route(self):
        """Jupiter and the other 61 unpinned programs never appear inside a Pump trade subtree, so
        their presence means the transaction routed around the path we would submit."""
        self.assertFalse(B9M.is_direct_route(self.route(
            {B9D.PUMP_PROGRAM, SOME_UNPINNED, B9M.PUMP_FEE_PROGRAM})))

    def test_pfee_does_not_take_a_transaction_off_the_direct_route(self):
        """Measured: pfee executes inside 93,448 of 93,448 Pump trade CPI subtrees.

        Pump invokes it itself, so treating its presence as 'routed' would classify every Pump
        trade in existence as off-route and make the direct route empty.
        """
        self.assertIn(B9M.PUMP_FEE_PROGRAM, B9M.DIRECT_ROUTE_PROGRAMS)
        self.assertTrue(B9M.is_direct_route(self.route({B9D.PUMP_PROGRAM, B9M.PUMP_FEE_PROGRAM})))

    def test_being_on_the_direct_route_does_not_make_pfee_pinned(self):
        """The two sets must stay distinct. pfee is unavoidable AND unpinned -- that combination is
        the top evidence gap, and collapsing the sets would hide it."""
        self.assertNotIn(B9M.PUMP_FEE_PROGRAM, B9M.PINNED_PROGRAMS)
        self.assertTrue(B9M.DIRECT_ROUTE_PROGRAMS - B9M.PINNED_PROGRAMS)


class ExhaustivenessTests(unittest.TestCase):

    def test_a_partition_that_loses_a_transaction_is_refused(self):
        """A dropped row is invisible -- the remaining counts still look like a clean breakdown."""
        counts = {category: 1 for category in B9M.PARTITION_CATEGORIES}
        self.assertTrue(B9M.assert_exhaustive(counts, len(B9M.PARTITION_CATEGORIES)))
        with self.assertRaisesRegex(B9D.FreezeViolation, "must be exhaustive"):
            B9M.assert_exhaustive(counts, len(B9M.PARTITION_CATEGORIES) + 1)

    def test_double_counting_a_transaction_is_refused_too(self):
        """Exclusivity fails in the other direction as well, and inflates a cause."""
        counts = {category: 1 for category in B9M.PARTITION_CATEGORIES}
        with self.assertRaisesRegex(B9D.FreezeViolation, "must be exhaustive"):
            B9M.assert_exhaustive(counts, len(B9M.PARTITION_CATEGORIES) - 1)


if __name__ == "__main__":
    unittest.main()
