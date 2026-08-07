"""B19 strategy-preregistration guards (slice D).

The guards that matter are the ones that would let a preregistration stop being one: text edited
after the fact, a discipline quietly dropped, a threshold that can be moved once an outcome is
known, or a family size that no longer matches the rules it counts.

Two are worth naming because they are the point of the slice rather than boilerplate:

- `test_reformatting_is_not_tampering_but_changing_a_value_is` pins the distinction the whole
  register rests on. A hash over file bytes would fail both and would train a reader to ignore it.
- `test_every_candidate_signal_is_a_boolean_from_the_frozen_contract` machine-checks B19d's central
  claim. B19d asserts threshold tuning is impossible because every signal is a boolean; that is
  either true of the frozen B11b contract or it is a sentence. This decides which, by reading the
  contract.

No network, no artifact, no study is run.
"""
import copy
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B19 = load("b19_preregistration_register", "b19_preregistration_register.py")

B11B = json.loads((ROOT / "research" / "B11B_BASELINE_EVALUATION_PREREGISTRATION.json").read_bytes())


def write_temp(document, case):
    directory = pathlib.Path(tempfile.mkdtemp())
    case.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
    path = directory / "p.json"
    path.write_text(json.dumps(document))
    return path


class TestTheRegisterVerifies(unittest.TestCase):
    def test_every_registered_preregistration_verifies_as_shipped(self):
        documents = B19.verify_all()
        self.assertEqual(set(documents), set(B19.REGISTER))
        for prereg_id, document in documents.items():
            self.assertEqual(document["preregistration_id"], prereg_id)

    def test_the_register_covers_the_three_g5_questions(self):
        self.assertEqual(sorted(B19.REGISTER), [
            "B19B_EXIT_TIMING_POLICY_V1",
            "B19C_CAPACITY_WALL_SIZE_DEPENDENCE_V1",
            "B19D_NON_ISSUANCE_SIGNAL_V1",
        ])

    def test_both_digests_are_recorded_and_correct(self):
        """The canonical pin AND the raw-file digest, so neither can drift unnoticed.

        `verify` deliberately checks only the canonical digest, so reformatting a document does
        not read as tampering. That tolerance has a cost: a reformat silently invalidates any
        `sha256sum` a reader was given. Recording the file digest and checking it HERE rather than
        in `verify` keeps the tolerance while making the reformat fail loudly.

        The digests must differ. If they ever matched, the canonicalisation would be doing
        nothing and the distinction this register rests on would be untested.
        """
        for prereg_id, entry in B19.REGISTER.items():
            with self.subTest(prereg_id=prereg_id):
                path = ROOT / "research" / entry["filename"]
                raw = path.read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["file_sha256"])
                self.assertEqual(B19.canonical_sha256(json.loads(raw)),
                                 entry["canonical_sha256"])
                self.assertNotEqual(entry["file_sha256"], entry["canonical_sha256"])

    def test_an_unregistered_id_refuses_rather_than_passing_by_absence(self):
        with self.assertRaisesRegex(B19.PreregistrationRefused, "not in the B19 register"):
            B19.verify("B19Z_INVENTED_V1")

    def test_a_registered_but_missing_document_refuses(self):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        with self.assertRaisesRegex(B19.PreregistrationRefused, "absent"):
            B19.verify("B19B_EXIT_TIMING_POLICY_V1", directory / "nothing.json")


class TestVerifyAppliesBothChecks(unittest.TestCase):
    def test_a_correctly_pinned_but_non_conforming_document_still_refuses(self):
        """`verify` must apply conformance, not only the hash.

        Every other conformance test calls `assert_conforms` directly, so deleting the call from
        `verify` leaves all of them passing while the register pins documents it does not vouch
        for. That mutant survived a sweep until this test existed, which is the whole reason it
        is written this way: the document below hashes correctly and is still refused.
        """
        temp_id = "B19TEST_CONFORMANCE_V1"
        document = json.loads(
            (ROOT / "research" / "B19B_EXIT_TIMING_POLICY_PREREGISTRATION.json").read_bytes())
        document["preregistration_id"] = temp_id
        document["status_locks"]["executable"] = True

        path = write_temp(document, self)
        B19.REGISTER[temp_id] = {
            "filename": path.name,
            "canonical_sha256": B19.canonical_sha256(document),
            "question": "a deliberately non-conforming document with an honest hash",
        }
        self.addCleanup(B19.REGISTER.pop, temp_id, None)

        with self.assertRaisesRegex(B19.PreregistrationRefused, "executable"):
            B19.verify(temp_id, path)


class TestTamperingRefuses(unittest.TestCase):
    def test_reformatting_is_not_tampering_but_changing_a_value_is(self):
        """The distinction the register exists to draw, both halves in one test."""
        original = json.loads(
            (ROOT / "research" / "B19B_EXIT_TIMING_POLICY_PREREGISTRATION.json").read_bytes())

        reformatted = write_temp(
            json.loads(json.dumps(original, sort_keys=False, indent=4)), self)
        B19.verify("B19B_EXIT_TIMING_POLICY_V1", reformatted)

        changed = copy.deepcopy(original)
        changed["frozen_inputs_unchanged"]["entry_delays_slots"] = [1, 2, 4, 8]
        with self.assertRaisesRegex(B19.PreregistrationRefused, "hashes"):
            B19.verify("B19B_EXIT_TIMING_POLICY_V1", write_temp(changed, self))

    def test_adding_an_exit_rule_after_the_fact_refuses(self):
        document = json.loads(
            (ROOT / "research" / "B19B_EXIT_TIMING_POLICY_PREREGISTRATION.json").read_bytes())
        document["frozen_exit_rules"]["set"].append(
            {"rule_id": "E_TUNED_LATER", "parameters": "chosen from the answer"})
        with self.assertRaisesRegex(B19.PreregistrationRefused, "hashes"):
            B19.verify("B19B_EXIT_TIMING_POLICY_V1", write_temp(document, self))

    def test_dropping_the_signal_whose_result_was_negative_refuses(self):
        """S5's retention is the test of the no-selection rule, so removing it must not be quiet."""
        document = json.loads(
            (ROOT / "research" / "B19D_NON_ISSUANCE_SIGNAL_PREREGISTRATION.json").read_bytes())
        document["candidate_signals_frozen"]["set"] = [
            s for s in document["candidate_signals_frozen"]["set"]
            if s["signal_id"] != "S5_CREATOR_REENTRY_DELAYED_CONFIRMATION"]
        with self.assertRaisesRegex(B19.PreregistrationRefused, "hashes"):
            B19.verify("B19D_NON_ISSUANCE_SIGNAL_V1", write_temp(document, self))

    def test_raising_the_capacity_ceiling_after_the_fact_refuses(self):
        document = json.loads(
            (ROOT / "research"
             / "B19C_CAPACITY_WALL_SIZE_DEPENDENCE_PREREGISTRATION.json").read_bytes())
        document["the_raised_ceiling"]["new_search_ceiling_lamports"] = 50_000_000_000
        with self.assertRaisesRegex(B19.PreregistrationRefused, "hashes"):
            B19.verify("B19C_CAPACITY_WALL_SIZE_DEPENDENCE_V1", write_temp(document, self))


class TestStructuralConformance(unittest.TestCase):
    """assert_conforms is what makes the register a standard rather than a filing cabinet."""

    def base(self):
        return json.loads(
            (ROOT / "research" / "B19B_EXIT_TIMING_POLICY_PREREGISTRATION.json").read_bytes())

    def test_a_document_that_does_not_know_its_own_id_refuses(self):
        document = self.base()
        document["preregistration_id"] = "SOMETHING_ELSE_V1"
        with self.assertRaisesRegex(B19.PreregistrationRefused, "does not know its own identity"):
            B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_each_required_block_is_individually_required(self):
        for block in B19.REQUIRED_BLOCKS:
            with self.subTest(block=block):
                document = self.base()
                del document[block]
                with self.assertRaises(B19.PreregistrationRefused):
                    B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_a_draft_may_not_be_cited_as_a_commitment(self):
        document = self.base()
        document["status"] = "draft, still being discussed"
        with self.assertRaisesRegex(B19.PreregistrationRefused, "not frozen"):
            B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_each_status_lock_is_individually_enforced(self):
        permissive = {"executable": True, "performance_status": "evaluated",
                      "execution_status": "executed"}
        for field, value in permissive.items():
            with self.subTest(field=field):
                document = self.base()
                document["status_locks"][field] = value
                with self.assertRaises(B19.PreregistrationRefused):
                    B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_an_unstated_status_lock_is_not_an_engaged_one(self):
        for field in B19.REQUIRED_STATUS_LOCKS:
            with self.subTest(field=field):
                document = self.base()
                del document["status_locks"][field]
                with self.assertRaisesRegex(B19.PreregistrationRefused, "does not state"):
                    B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_a_document_without_a_b11_disclosure_refuses(self):
        """Without it, a postregistration is indistinguishable from a preregistration."""
        document = self.base()
        del document["known_at_authorship_time"]["b11"]
        with self.assertRaisesRegex(B19.PreregistrationRefused, "b11"):
            B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_an_empty_prohibition_or_refusal_list_is_not_a_permissive_default(self):
        for block in ("prohibitions", "refusal_codes"):
            with self.subTest(block=block):
                document = self.base()
                document[block] = []
                with self.assertRaisesRegex(B19.PreregistrationRefused, "states no"):
                    B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_a_refusal_code_without_a_meaning_refuses(self):
        document = self.base()
        document["refusal_codes"].append({"code": "X_MYSTERY"})
        with self.assertRaisesRegex(B19.PreregistrationRefused, "without both"):
            B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_a_float_anywhere_refuses_and_names_where(self):
        document = self.base()
        document["frozen_inputs_unchanged"]["position_lamports"] = 100000000.0
        with self.assertRaisesRegex(B19.PreregistrationRefused, r"float at.*position_lamports"):
            B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_a_float_nested_in_a_list_is_found_too(self):
        document = self.base()
        document["frozen_inputs_unchanged"]["entry_delays_slots"] = [1, 2.5, 4]
        with self.assertRaisesRegex(B19.PreregistrationRefused, r"float at"):
            B19.assert_conforms(document, "B19B_EXIT_TIMING_POLICY_V1")

    def test_no_shipped_document_carries_a_float(self):
        for prereg_id, document in B19.verify_all().items():
            with self.subTest(prereg_id=prereg_id):
                self.assertEqual(B19._float_paths(document), [])


class TestExitTimingDiscipline(unittest.TestCase):
    def setUp(self):
        self.document = B19.verify("B19B_EXIT_TIMING_POLICY_V1")

    def test_the_family_size_matches_the_rules_and_delays_it_counts(self):
        rules = self.document["frozen_exit_rules"]["set"]
        delays = self.document["frozen_inputs_unchanged"]["entry_delays_slots"]
        self.assertEqual(self.document["multiplicity"]["family_size"], len(rules) * len(delays))

    def test_every_rule_declares_its_parameters_and_none_is_a_free_cut(self):
        """A rule with a free numeric parameter is a threshold waiting to be tuned."""
        for rule in self.document["frozen_exit_rules"]["set"]:
            with self.subTest(rule=rule["rule_id"]):
                parameters = rule["parameters"]
                self.assertTrue(
                    parameters == "none" or "fixed grid" in parameters,
                    f"{rule['rule_id']} parameters {parameters!r} is neither parameter-free nor a "
                    "declared fixed-grid member")

    def test_the_drawdown_grid_members_are_exact_rationals_not_decimals(self):
        grid = [r for r in self.document["frozen_exit_rules"]["set"]
                if r["rule_id"].startswith("E_PEAK_DRAWDOWN")]
        self.assertEqual(len(grid), 3)
        for rule in grid:
            with self.subTest(rule=rule["rule_id"]):
                self.assertRegex(rule["parameters"], r"exact rational \d+/\d+")

    def test_the_capacity_trigger_rule_is_present_because_it_is_the_question(self):
        rule_ids = [r["rule_id"] for r in self.document["frozen_exit_rules"]["set"]]
        self.assertIn("E_FIRST_EXTERNALLY_PAYABLE", rule_ids)

    def test_censoring_is_never_zero(self):
        self.assertIn("never counted as zero", self.document["right_censoring"]["never_zero"])

    def test_no_mean_is_reported(self):
        self.assertIn("NO MEAN", self.document["outcome_reporting"]["statistics"])

    def test_the_study_may_not_select_a_rule(self):
        # Case-folded deliberately: these documents capitalise for emphasis, and a test that
        # breaks when a word is emphasised is testing formatting rather than the commitment.
        joined = " ".join(self.document["prohibitions"]).lower()
        self.assertIn("selected", joined)
        self.assertIn("new preregistration", joined)


class TestCapacityWallDiscipline(unittest.TestCase):
    def setUp(self):
        self.document = B19.verify("B19C_CAPACITY_WALL_SIZE_DEPENDENCE_V1")

    def test_the_new_ceiling_is_exactly_the_stated_multiple_of_the_old(self):
        ceiling = self.document["the_raised_ceiling"]
        self.assertEqual(ceiling["new_search_ceiling_lamports"],
                         100 * ceiling["old_ceiling_lamports"])

    def test_the_old_ceiling_matches_b15m_rather_than_being_restated_from_memory(self):
        b15m = json.loads(
            (ROOT / "research" / "B15M_LIQUIDITY_CAPACITY_PREREGISTRATION.json").read_bytes())
        self.assertEqual(
            self.document["the_raised_ceiling"]["old_ceiling_lamports"],
            b15m["frozen_inputs_unchanged"]["capacity_search_upper_bound_lamports"])

    def test_the_grid_retains_b15m_members_so_the_studies_can_be_read_together(self):
        grid = self.document["the_wall_shape"]["grid_lamports"]
        b15m = json.loads(
            (ROOT / "research" / "B15M_LIQUIDITY_CAPACITY_PREREGISTRATION.json").read_bytes())
        b15m_grid = b15m["secondary_estimand_separately_named"]["grid_lamports"]
        self.assertTrue(set(grid) & set(b15m_grid), "the grids share no member")
        self.assertEqual(grid, sorted(grid))
        self.assertEqual(grid[-1], self.document["the_raised_ceiling"]["new_search_ceiling_lamports"])

    def test_raising_a_measurement_ceiling_is_not_grounds_to_raise_a_position_limit(self):
        joined = " ".join(self.document["prohibitions"])
        self.assertIn("not evidence for raising any POSITION limit", joined)

    def test_a_cap_hit_capacity_is_never_reported_as_the_true_capacity(self):
        self.assertIn("never as equal to it",
                      self.document["the_raised_ceiling"]["it_is_a_ceiling_not_a_target"])


class TestNonIssuanceSignalDiscipline(unittest.TestCase):
    def setUp(self):
        self.document = B19.verify("B19D_NON_ISSUANCE_SIGNAL_V1")
        self.signals = self.document["candidate_signals_frozen"]["set"]

    def test_every_candidate_signal_is_a_boolean_from_the_frozen_contract(self):
        """B19d's central claim, decided against B11b rather than trusted.

        If a signal named an integer field, a cut would exist and could be moved once an outcome
        was known. The claim is only worth making if it is checkable.
        """
        booleans = {f["name"] for f in B11B["feature_contract"]["features"]
                    if f["type"] == "boolean"}
        self.assertTrue(booleans, "the frozen contract exposes no boolean features")
        integers = {f["name"] for f in B11B["feature_contract"]["features"]
                    if f["type"] != "boolean"}

        for signal in self.signals:
            with self.subTest(signal=signal["signal_id"]):
                predicate = signal["predicate"]
                named_integer = [name for name in integers if name in predicate]
                self.assertEqual(
                    named_integer, [],
                    f"{signal['signal_id']} names non-boolean field(s) {named_integer}, which "
                    "would require a cut")
                if not signal["source"].startswith("B16D"):
                    self.assertTrue(
                        any(name in predicate for name in booleans),
                        f"{signal['signal_id']} names no boolean field of the frozen contract")

    def test_every_signal_cites_an_already_frozen_source(self):
        for signal in self.signals:
            with self.subTest(signal=signal["signal_id"]):
                self.assertRegex(signal["source"], r"(?i)^B1[16][BD]")

    def test_the_partition_is_reported_in_full_so_neither_arm_can_be_dropped(self):
        ids = {s["signal_id"] for s in self.signals}
        self.assertIn("S1_CREATOR_INITIAL_BUY_PRESENT", ids)
        self.assertIn("S2_NO_CREATOR_INITIAL_BUY", ids)

    def test_the_known_negative_signal_is_retained_deliberately(self):
        s5 = [s for s in self.signals
              if s["signal_id"] == "S5_CREATOR_REENTRY_DELAYED_CONFIRMATION"]
        self.assertEqual(len(s5), 1)
        self.assertIn("selection on a known outcome", s5[0]["retained_deliberately"])

    def test_the_family_size_matches_the_signals_and_horizons_it_counts(self):
        horizons = self.document["frozen_inputs_unchanged"]["horizons"]
        self.assertEqual(self.document["multiplicity"]["family_size"],
                         len(self.signals) * len(horizons))

    def test_the_horizons_are_b11b_s_four_unchanged(self):
        b11b_horizons = [h["name"] for h in B11B["horizons"]["set"]]
        self.assertEqual(self.document["frozen_inputs_unchanged"]["horizons"], b11b_horizons)

    def test_survives_costs_is_break_even_and_not_a_tuned_cut(self):
        criterion = self.document["what_survives_costs_means_exactly"]
        self.assertIn("STRICTLY GREATER THAN ZERO", criterion["pre_committed_criterion"])
        self.assertIn("not a fitted number", criterion["zero_is_not_a_tuned_threshold"])

    def test_burned_data_may_never_be_reported_as_evaluation(self):
        self.assertIn("DEVELOPMENT ONLY",
                      self.document["evaluation_versus_development"]["burned_corpus_is_development_only"])

    def test_the_deferred_items_each_carry_a_reason(self):
        items = self.document["deliberately_deferred_with_reasons"]["items"]
        self.assertGreaterEqual(len(items), 4)
        for item in items:
            with self.subTest(item=item["item"]):
                self.assertTrue(item["reason"].strip())

    def test_integer_field_signals_are_deferred_rather_than_silently_absent(self):
        """An absence with no reason reads as an oversight; this one is a decision."""
        reasons = " ".join(i["item"] + " " + i["reason"]
                           for i in self.document["deliberately_deferred_with_reasons"]["items"])
        self.assertIn("INTEGER", reasons)
        self.assertIn("no threshold may be chosen before labels exist", reasons)

    def test_issuance_is_out_of_scope_by_decision(self):
        self.assertIn("not recommended as a strategy",
                      self.document["non_issuance_is_the_point"]["why_scoped_this_way"].lower())


class TestGroupWideStandingConstraints(unittest.TestCase):
    """The constraints that hold across the group, checked on every document rather than one."""

    def documents(self):
        return B19.verify_all()

    def test_none_claims_an_evaluation_result(self):
        for prereg_id, document in self.documents().items():
            with self.subTest(prereg_id=prereg_id):
                self.assertEqual(document["status_locks"]["performance_status"], "not_evaluated")
                self.assertEqual(document["status_locks"]["execution_status"], "never_executed")
                self.assertIs(document["status_locks"]["executable"], False)

    def test_each_forbids_reading_b11a_and_touching_the_network(self):
        for prereg_id, document in self.documents().items():
            with self.subTest(prereg_id=prereg_id):
                joined = " ".join(document["prohibitions"]).lower()
                self.assertIn("b11a", joined)
                self.assertIn("network", joined)
                self.assertIn("signing", joined)

    def test_each_forbids_float(self):
        for prereg_id, document in self.documents().items():
            with self.subTest(prereg_id=prereg_id):
                self.assertIn("float", " ".join(document["prohibitions"]).lower())

    def test_each_discloses_that_b11_had_not_produced_its_result(self):
        for prereg_id, document in self.documents().items():
            with self.subTest(prereg_id=prereg_id):
                self.assertIn("NOT", document["known_at_authorship_time"]["b11"])

    def test_each_reports_coverage_before_outcomes(self):
        for prereg_id, document in self.documents().items():
            if prereg_id == "B19C_CAPACITY_WALL_SIZE_DEPENDENCE_V1":
                continue  # capacity is not an outcome; it has no coverage-before-outcome ordering
            with self.subTest(prereg_id=prereg_id):
                self.assertIn("BEFORE", document["denominator_and_coverage"]["reported_first"])


if __name__ == "__main__":
    unittest.main()
