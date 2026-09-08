"""Adversarial causality tests; synthetic names and identities only."""
from dataclasses import replace
import unittest

from scripts.birth_origin import Birth, LOOKBACK, Refused, components, digest, observe, placebo, words


def birth(index, timestamp, *, creator=None, user=None, name="violet", mint=None, txn=None):
    return Birth((index, 0, 0, -1) if txn is None else txn, timestamp,
                 mint or f"m{index}", creator or f"a{index}", user or creator or f"a{index}",
                 words(name, ""), digest([index, timestamp, name]))


def wave():
    return [birth(i, LOOKBACK + i) for i in range(1, 5)]


class BirthOriginTests(unittest.TestCase):
    def run_observer(self, rows):
        return observe(rows, history_start=0)

    def test_four_actor_positive_control(self):
        rows, stats = self.run_observer(wave())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["candidate_mint"], "m1")
        self.assertEqual(rows[0]["groups_before"], 3)
        self.assertEqual(rows[0]["groups_after"], 4)
        self.assertEqual(rows[0]["status"], "NO_TRADE")
        self.assertIsNone(rows[0]["observed_at_unix_nanos"])
        self.assertEqual(stats["births"], 4)

    def test_future_text_cannot_change_prefix(self):
        prefix = wave()
        initial, _ = self.run_observer(prefix)
        extended, _ = self.run_observer(prefix + [birth(5, LOOKBACK + 5, name="violet unicorn")])
        renamed, _ = self.run_observer(prefix + [birth(5, LOOKBACK + 5, name="unrelated")])
        self.assertEqual(initial, extended[:len(initial)])
        self.assertEqual(initial, renamed[:len(initial)])

    def test_future_vocabulary_does_not_retroactively_qualify(self):
        self.assertEqual(self.run_observer(wave()[:3])[0], [])

    def test_one_creator_spam_does_not_cross(self):
        rows = [birth(i, LOOKBACK + i, creator="spam") for i in range(1, 20)]
        self.assertEqual(self.run_observer(rows)[0], [])

    def test_creator_user_bridge_joins_exact_identity_groups(self):
        rows = [birth(1, 1, creator="A", user="B"), birth(2, 2, creator="C", user="B")]
        graph = components(rows)
        self.assertEqual(len(set(graph.values())), 1)

    def test_bridge_on_another_word_is_known_identity_context(self):
        rows = [birth(1, 1, creator="A", user="B", name="unrelated"),
                birth(2, LOOKBACK + 1, creator="A"),
                birth(3, LOOKBACK + 2, creator="B"),
                birth(4, LOOKBACK + 3, creator="C"),
                birth(5, LOOKBACK + 4, creator="D")]
        self.assertEqual(self.run_observer(rows)[0], [])

    def test_future_identity_bridge_does_not_rewrite_a_decision(self):
        initial, _ = self.run_observer(wave())
        later = birth(5, LOOKBACK + 5, creator="a1", user="a2", name="unrelated")
        self.assertEqual(self.run_observer(wave() + [later])[0][:1], initial)

    def test_arrival_linked_to_origin_refuses(self):
        rows = wave()[:3] + [birth(4, LOOKBACK + 4, creator="a1", user="new")]
        self.assertEqual(self.run_observer(rows)[0], [])

    def test_same_transaction_has_no_prior_origin(self):
        rows = [birth(i, LOOKBACK + 1, txn=(1, 0, i, -1)) for i in range(1, 5)]
        out, stats = self.run_observer(rows)
        self.assertEqual(out, [])
        self.assertEqual(stats["no_prior_origin"], 1)

    def test_equal_second_does_not_imply_prior_observation(self):
        rows = [birth(i, LOOKBACK + 1) for i in range(1, 5)]
        self.assertEqual(self.run_observer(rows)[0], [])

    def test_partial_warmup_refuses(self):
        self.assertEqual(self.run_observer([birth(i, i) for i in range(1, 5)])[0], [])

    def test_expired_evidence_cannot_cross(self):
        rows = wave()[:3] + [birth(4, 2 * LOOKBACK + 10)]
        self.assertEqual(self.run_observer(rows)[0], [])

    def test_missing_actor_not_independent(self):
        rows = wave()[:3] + [replace(wave()[3], creator=None)]
        out, stats = self.run_observer(rows)
        self.assertEqual(out, [])
        self.assertEqual(stats["missing_actor"], 1)

    def test_non_native_and_mayhem_excluded_explicitly(self):
        rows = wave()[:3] + [replace(wave()[3], in_scope=False)]
        out, stats = self.run_observer(rows)
        self.assertEqual(out, [])
        self.assertEqual(stats["scope_excluded"], 1)

    def test_two_terms_cannot_emit_same_mint_twice(self):
        rows = [birth(i, LOOKBACK + i, name="violet orchid") for i in range(1, 5)]
        out, stats = self.run_observer(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(stats["duplicate_origin_suppressed"], 1)

    def test_duplicate_mint_refuses(self):
        with self.assertRaisesRegex(Refused, "duplicate mint"):
            self.run_observer(wave() + [birth(5, LOOKBACK + 5, mint="m1")])

    def test_unordered_coordinates_refuse(self):
        with self.assertRaisesRegex(Refused, "unordered"):
            self.run_observer([wave()[1], replace(wave()[0], timestamp=LOOKBACK + 3)])

    def test_backward_clock_refuses(self):
        with self.assertRaisesRegex(Refused, "backward"):
            self.run_observer([wave()[0], birth(2, 1)])

    def test_conflicting_transaction_clock_refuses(self):
        with self.assertRaisesRegex(Refused, "conflicting"):
            self.run_observer([birth(1, LOOKBACK, txn=(1, 0, 0, -1)),
                               birth(2, LOOKBACK + 1, txn=(1, 0, 1, -1))])

    def test_invalid_evidence_refuses(self):
        with self.assertRaisesRegex(Refused, "hash"):
            self.run_observer([replace(wave()[0], source_sha256="invented")])

    def test_fixed_text_rules(self):
        self.assertEqual(words("ＴＨＥ Violet coin 123", "VIOLET"), frozenset({"violet"}))
        with self.assertRaises(Refused):
            words(None, "missing")

    def test_placebo_preserves_actors_clocks_and_reproducibility(self):
        rows = [birth(i, i, creator="A" if i % 2 else "B", name=f"name {['iris','lily','rose'][i % 3]}")
                for i in range(1, 20)]
        shuffled, changed = placebo(rows, 7)
        self.assertGreater(changed, 0)
        self.assertEqual(placebo(rows, 7), (shuffled, changed))
        self.assertEqual([(b.coord, b.timestamp, b.actors) for b in rows],
                         [(b.coord, b.timestamp, b.actors) for b in shuffled])
        for actor in ("A", "B"):
            self.assertEqual(sorted(sorted(b.terms) for b in rows if b.creator == actor),
                             sorted(sorted(b.terms) for b in shuffled if b.creator == actor))


if __name__ == "__main__":
    unittest.main()
