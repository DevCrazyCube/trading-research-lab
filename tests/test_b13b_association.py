"""Tests for the B13b association evidence ledger.

The whole point of this module is what it refuses to conclude, so most of these tests are about
refusals. One module graph is loaded for the whole file: loading the same module twice by path
creates two distinct exception classes, and an `assertRaises` on the wrong one never matches.
"""
import copy
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B13B = _load("b13b_association", "b13b_association.py")
B13A = B13B.B13A
B10B = B13B.B10B

ALICE, BOB, CAROL, FUNDER = "AAAAalice", "BBBBbob", "CCCCcarol", "FFFFfunder"


# --------------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------------

def accounting(**overrides):
    base = {"transactions_required": 0, "transactions_with_body": 0, "transactions_missing_body": 0,
            "transactions_missing_coordinate": 0, "system_instructions_total": 0,
            "decoded_moving": 0, "decoded_non_moving": 0, "undecodable": 0, "edges_emitted": 0,
            "moving_self_transfer": 0, "moving_without_addresses": 0, "unresolved": []}
    base.update(overrides)
    return base


def coverage(**overrides):
    base = {"first_slot": 100, "last_slot": 900, "source_population": "synthetic fixture",
            "left_truncated": False, "right_truncated": False, "complete": True,
            "provenance_sha256": "cov" * 10, "decode_accounting": accounting()}
    base.update(overrides)
    return base


def at(slot, index=0, outer=0, inner=0):
    return {"slot": slot, "transaction_index": index, "outer_index": outer, "inner_index": inner}


def transfer(slot, sender, recipient, lamports=1_000, index=0, outer=0, inner=0, source=None):
    return {**at(slot, index, outer, inner), "kind": B13A.EVENT_TRANSFER,
            "from_address": sender, "to_address": recipient, "lamports": lamports,
            "source_sha256": source or f"src-{slot}-{index}-{outer}-{inner}-{sender}-{recipient}"}


def launch(slot, mint="MINT1", creator=ALICE, create_user=BOB, index=0, outer=0, inner=0):
    return {**at(slot, index, outer, inner), "kind": B13A.EVENT_LAUNCH, "mint": mint,
            "bonding_curve": f"curve-{mint}", "creator": creator, "create_user": create_user,
            "source_sha256": f"launch-{slot}-{mint}"}


def trade(slot, user=ALICE, mint="MINT1", is_buy=True, index=0, outer=0, inner=0):
    return {**at(slot, index, outer, inner), "kind": B13A.EVENT_TRADE, "mint": mint, "user": user,
            "is_buy": is_buy, "quote_lamports": 500, "token_units": 900,
            "source_sha256": f"trade-{slot}-{index}-{outer}-{inner}-{user}"}


def evidence_item(**overrides):
    base = {"kind": B13B.E01_DIRECT_TRANSFER, "direction": B13B.DIRECTION_A_TO_B,
            "witness_addresses": sorted([ALICE, BOB]), "coordinates": [at(200)],
            "source_sha256_list": ["src-200"], "facts": {"lamports": 7},
            "detail": "a transfer between the endpoints"}
    base.update(overrides)
    return base


DEFAULT_T0 = at(900, 9, 9, 9)


def build(events=None, focus=(ALICE, BOB), t0=None, cover=None, **kwargs):
    return B13B.build_association_ledger(
        events if events is not None else [transfer(200, ALICE, BOB)],
        focus, t0 or DEFAULT_T0, cover or coverage(), **kwargs)


def a_link(ledger, address_a=ALICE, address_b=BOB):
    return next(link for link in ledger["links"]
                if link["grouping"]["address_a"] == address_a
                and link["grouping"]["address_b"] == address_b)


# --------------------------------------------------------------------------------------------

class RefusedOperationTests(unittest.TestCase):
    """The operations that exist in order to say no.

    Absence would invite a caller to write their own; a refusal tells them why they should not.
    """

    def test_every_clustering_operation_fails_closed(self):
        for name in ("cluster_id", "connected_component", "merge_addresses",
                     "association_probability", "cluster_adjusted_concentration"):
            with self.subTest(operation=name):
                with self.assertRaises(B13B.ClusterRefused):
                    getattr(B13B, name)(ALICE, BOB)

    def test_a_cluster_refusal_is_distinguishable_from_a_malformed_input(self):
        """"Fix your input" and "this question has not been earned yet" are different problems."""
        self.assertTrue(issubclass(B13B.ClusterRefused, B13B.AssociationRefused))
        with self.assertRaises(B13B.AssociationRefused):
            B13B.cluster_id(ALICE)
        try:
            B13B.merge_addresses(ALICE, BOB)
        except B13B.ClusterRefused as error:
            self.assertIn("preregistered", str(error).lower())

    def test_the_component_refusal_names_the_transitivity_it_refuses(self):
        with self.assertRaisesRegex(B13B.ClusterRefused, "never an A—C link"):
            B13B.connected_component(ALICE)

    def test_the_contract_declares_what_it_does_not_do(self):
        import io, contextlib, json
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            B13B.main(["--contract"])
        contract = json.loads(buffer.getvalue())
        self.assertFalse(contract["clusters_inferred"])
        self.assertFalse(contract["transitive_closure_taken"])
        self.assertFalse(contract["probability_emitted"])
        self.assertEqual(contract["confidence_status"], "uncalibrated_evidence_only")
        self.assertEqual(len(contract["refusing_operations"]), 5)


class NonTransitivityTests(unittest.TestCase):
    """A—B plus B—C may never manufacture A—C, and the data structure is what prevents it."""

    def test_two_links_through_a_common_endpoint_do_not_produce_a_third(self):
        events = [transfer(200, ALICE, BOB), transfer(300, BOB, CAROL)]
        ledger = build(events, focus=(ALICE, BOB, CAROL))
        pairs = {(link["grouping"]["address_a"], link["grouping"]["address_b"])
                 for link in ledger["links"]}
        self.assertIn((ALICE, BOB), pairs)
        self.assertIn((BOB, CAROL), pairs)
        self.assertNotIn((ALICE, CAROL), pairs)

    def test_a_link_whose_evidence_does_not_name_both_endpoints_is_refused(self):
        """The structural mechanism, driven directly: evidence witnessing {A,B} cannot support A—C."""
        item = evidence_item(witness_addresses=sorted([ALICE, BOB]))
        with self.assertRaisesRegex(B13B.AssociationRefused, "witnessed by evidence naming BOTH"):
            B13B.build_link(B13B.RELATION_ASSOCIATION_EVIDENCE, ALICE, CAROL, [item],
                            B10B.canonical_key(DEFAULT_T0))

    def test_a_manufactured_link_is_caught_after_assembly_too(self):
        """A closure applied to a finished ledger must not survive validation either."""
        ledger = build([transfer(200, ALICE, BOB), transfer(300, BOB, CAROL)],
                       focus=(ALICE, BOB, CAROL))
        forged = copy.deepcopy(a_link(ledger, ALICE, BOB))
        forged["grouping"]["address_b"] = CAROL
        ledger["links"].append(forged)
        with self.assertRaisesRegex(B13B.AssociationRefused, "witnessed by no single observation"):
            B13B.assert_no_transitive_link(ledger)

    def test_the_whole_ledger_rejects_a_manufactured_link(self):
        """`assert_ledger` refuses it too, via the strictly stronger per-item rule: every item must
        witness both endpoints, not merely one of them."""
        ledger = build([transfer(200, ALICE, BOB), transfer(300, BOB, CAROL)],
                       focus=(ALICE, BOB, CAROL))
        forged = copy.deepcopy(a_link(ledger, ALICE, BOB))
        forged["grouping"]["address_b"] = CAROL
        forged["link_sha256"] = B13B.link_hash(forged)
        ledger["links"].append(forged)
        ledger["accounting"]["links_emitted"] += 1
        ledger["accounting"]["links_by_relation"][B13B.RELATION_ASSOCIATION_EVIDENCE] += 1
        for item in forged["evidence"]:
            ledger["accounting"]["evidence_by_kind"][item["kind"]] += 1
        ledger["accounting"]["evidence_items"] += len(forged["evidence"])
        with self.assertRaisesRegex(B13B.AssociationRefused, "incapable of manufacturing A—C"):
            B13B.assert_ledger(ledger)

    def test_a_shared_funder_witnesses_the_pair_it_actually_links(self):
        """The funder is named as a witness, but only the two endpoints it paid become a link."""
        events = [transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB),
                  transfer(220, FUNDER, CAROL)]
        ledger = build(events, focus=(ALICE, BOB, CAROL))
        for link in ledger["links"]:
            kinds = {item["kind"] for item in link["evidence"]}
            self.assertIn(B13B.E02_SHARED_FUNDER, kinds)
            shared = next(i for i in link["evidence"] if i["kind"] == B13B.E02_SHARED_FUNDER)
            self.assertIn(FUNDER, shared["witness_addresses"])
        # The funder itself is not a focus address, so it forms no link of its own.
        endpoints = {a for link in ledger["links"]
                     for a in (link["grouping"]["address_a"], link["grouping"]["address_b"])}
        self.assertNotIn(FUNDER, endpoints)


class IdentityVersusAssociationTests(unittest.TestCase):
    """Exact equality is the only relation here that asserts sameness."""

    def test_identity_equality_requires_one_address(self):
        item = evidence_item(kind=B13B.E00_EXACT_ADDRESS_EQUALITY,
                             direction=B13B.DIRECTION_NONE, witness_addresses=[ALICE],
                             facts={"roles_observed": ["creator", "trader"]})
        with self.assertRaisesRegex(B13B.AssociationRefused, "two different strings"):
            B13B.build_link(B13B.RELATION_IDENTITY_EQUALITY, ALICE, BOB, [item],
                            B10B.canonical_key(DEFAULT_T0))

    def test_association_evidence_may_not_live_inside_an_identity_claim(self):
        with self.assertRaisesRegex(B13B.AssociationRefused, "'they transacted' becomes"):
            B13B.build_link(B13B.RELATION_IDENTITY_EQUALITY, ALICE, ALICE,
                            [evidence_item(witness_addresses=[ALICE])],
                            B10B.canonical_key(DEFAULT_T0))

    def test_exact_equality_may_not_live_inside_an_association(self):
        item = evidence_item(kind=B13B.E00_EXACT_ADDRESS_EQUALITY,
                             direction=B13B.DIRECTION_NONE, facts={})
        with self.assertRaisesRegex(B13B.AssociationRefused, "different relation type"):
            B13B.build_link(B13B.RELATION_ASSOCIATION_EVIDENCE, ALICE, BOB, [item],
                            B10B.canonical_key(DEFAULT_T0))

    def test_one_address_in_two_roles_is_recorded_as_identity_not_association(self):
        ledger = build([launch(200, creator=ALICE, create_user=BOB), trade(300, user=ALICE)],
                       focus=(ALICE, BOB))
        identity = [link for link in ledger["links"]
                    if link["relation_type"] == B13B.RELATION_IDENTITY_EQUALITY]
        self.assertEqual(len(identity), 1)
        self.assertEqual(identity[0]["grouping"]["address_a"], ALICE)
        self.assertEqual(identity[0]["grouping"]["address_b"], ALICE)
        self.assertEqual(identity[0]["evidence"][0]["facts"]["roles_observed"],
                         ["creator", "trader"])

    def test_a_direct_transfer_never_becomes_an_identity_claim(self):
        """The single most tempting upgrade in this whole module, and it must not happen."""
        ledger = build([transfer(200, ALICE, BOB)], focus=(ALICE, BOB))
        for link in ledger["links"]:
            self.assertEqual(link["relation_type"], B13B.RELATION_ASSOCIATION_EVIDENCE)
        meaning = B13B.EVIDENCE_MEANING[B13B.E01_DIRECT_TRANSFER]
        self.assertIn("nothing else", meaning)

    def test_association_endpoints_are_distinct_and_canonically_ordered(self):
        for pair in ((BOB, ALICE), (ALICE, ALICE)):
            with self.subTest(pair=pair):
                with self.assertRaisesRegex(B13B.AssociationRefused, "canonically ordered"):
                    B13B.build_link(B13B.RELATION_ASSOCIATION_EVIDENCE, pair[0], pair[1],
                                    [evidence_item(witness_addresses=sorted(set(pair)))],
                                    B10B.canonical_key(DEFAULT_T0))


class DirectionTests(unittest.TestCase):
    """Direction is preserved everywhere, because a dropped direction changes the conclusion."""

    def test_the_direction_of_a_transfer_survives_into_the_link(self):
        forward = build([transfer(200, ALICE, BOB, lamports=77)])
        backward = build([transfer(200, BOB, ALICE, lamports=77)])
        self.assertEqual(a_link(forward)["features"]["lamports_a_to_b_observed"], 77)
        self.assertEqual(a_link(forward)["features"]["lamports_b_to_a_observed"], 0)
        self.assertEqual(a_link(backward)["features"]["lamports_a_to_b_observed"], 0)
        self.assertEqual(a_link(backward)["features"]["lamports_b_to_a_observed"], 77)

    def test_reversing_a_direction_changes_the_record(self):
        self.assertNotEqual(build([transfer(200, ALICE, BOB)])["ledger_sha256"],
                            build([transfer(200, BOB, ALICE)])["ledger_sha256"])

    def test_flows_are_never_netted(self):
        ledger = build([transfer(200, ALICE, BOB, lamports=100),
                        transfer(300, BOB, ALICE, lamports=100)])
        features = a_link(ledger)["features"]
        self.assertEqual(features["lamports_a_to_b_observed"], 100)
        self.assertEqual(features["lamports_b_to_a_observed"], 100)

    def test_a_directional_kind_may_not_record_no_direction(self):
        for kind in B13B.DIRECTIONAL_KINDS:
            with self.subTest(kind=kind):
                item = evidence_item(kind=kind, direction=B13B.DIRECTION_NONE)
                with self.assertRaisesRegex(B13B.AssociationRefused, "dropped direction"):
                    B13B.assert_evidence_item(item, (ALICE, BOB),
                                              B10B.canonical_key(DEFAULT_T0))

    def test_a_non_directional_kind_may_not_invent_one(self):
        item = evidence_item(kind=B13B.E02_SHARED_FUNDER, direction=B13B.DIRECTION_A_TO_B)
        with self.assertRaisesRegex(B13B.AssociationRefused, "invented direction"):
            B13B.assert_evidence_item(item, (ALICE, BOB), B10B.canonical_key(DEFAULT_T0))

    def test_repeated_counterparty_records_which_way_the_repetition_ran(self):
        ledger = build([transfer(200, ALICE, BOB), transfer(300, ALICE, BOB),
                        transfer(400, BOB, ALICE)])
        repeated = next(i for i in a_link(ledger)["evidence"]
                        if i["kind"] == B13B.E03_REPEATED_COUNTERPARTY)
        self.assertEqual(repeated["direction"], B13B.DIRECTION_BOTH)
        self.assertEqual(repeated["facts"]["a_to_b_count_observed"], 2)
        self.assertEqual(repeated["facts"]["b_to_a_count_observed"], 1)

    def test_a_one_way_repetition_is_not_recorded_as_two_way(self):
        """"They kept paying each other" and "one of them kept paying the other" are different
        facts, and only the second is true here."""
        cases = {B13B.DIRECTION_A_TO_B: [transfer(200, ALICE, BOB), transfer(300, ALICE, BOB)],
                 B13B.DIRECTION_B_TO_A: [transfer(200, BOB, ALICE), transfer(300, BOB, ALICE)]}
        for expected, events in cases.items():
            with self.subTest(direction=expected):
                repeated = next(i for i in a_link(build(events))["evidence"]
                                if i["kind"] == B13B.E03_REPEATED_COUNTERPARTY)
                self.assertEqual(repeated["direction"], expected)


class BoundaryTests(unittest.TestCase):
    """The same inclusive boundary as everywhere else in this project."""

    def test_evidence_after_t0_never_enters(self):
        ledger = build([transfer(200, ALICE, BOB), transfer(950, ALICE, BOB)], t0=at(900, 9, 9, 9))
        self.assertEqual(a_link(ledger)["features"]["direct_transfer_count_observed"], 1)
        self.assertEqual(ledger["accounting"]["events_discarded_after_t0"], 1)

    def test_the_boundary_is_inclusive_at_t0(self):
        t0 = at(500, 3, 2, 1)
        ledger = build([transfer(500, ALICE, BOB, index=3, outer=2, inner=1)], t0=t0)
        self.assertEqual(a_link(ledger)["features"]["direct_transfer_count_observed"], 1)

    def test_the_boundary_is_exclusive_one_coordinate_later(self):
        t0 = at(500, 3, 2, 1)
        ledger = build([transfer(500, ALICE, BOB, index=3, outer=2, inner=2)], t0=t0,
                       focus=(ALICE, BOB))
        self.assertEqual(ledger["links"], [])

    def test_a_hand_built_item_from_the_future_is_refused(self):
        item = evidence_item(coordinates=[at(5_000)])
        with self.assertRaisesRegex(B13B.AssociationRefused, "assembled from the future"):
            B13B.assert_evidence_item(item, (ALICE, BOB), B10B.canonical_key(DEFAULT_T0))

    def test_the_ledger_carries_the_boundary_rule_it_applies(self):
        self.assertEqual(build()["boundary_rule"], B13A.BOUNDARY_RULE)
        ledger = build()
        ledger["boundary_rule"] = "anything before t0, roughly"
        with self.assertRaisesRegex(B13B.AssociationRefused, "not the one this module applies"):
            B13B.assert_ledger(ledger)


class ServiceRoleTests(unittest.TestCase):
    """A shared service wallet is the obvious false link, so it is named on every record."""

    def register(self, address, role=B13B.ROLE_EXCHANGE):
        return {address: {"role": role, "provenance_sha256": "prov" * 8,
                          "established_by": "a pinned roster with a citation"}}

    def test_an_unknown_role_raises_the_flag_rather_than_lowering_it(self):
        codes = {entry["reason_code"] for entry in a_link(build())["counter_evidence"]}
        self.assertIn(B13B.X01_ENDPOINT_ROLE_UNKNOWN, codes)

    def test_counter_evidence_is_never_empty_while_a_role_is_unknown(self):
        ledger = build([transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB)])
        for link in ledger["links"]:
            self.assertTrue(link["counter_evidence"])
            self.assertTrue(link["features"]["counter_evidence_present"])

    def test_an_unknown_intermediary_is_flagged_separately_from_an_endpoint(self):
        ledger = build([transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB)])
        codes = {e["reason_code"] for e in a_link(ledger)["counter_evidence"]}
        self.assertIn(B13B.X03_INTERMEDIARY_ROLE_UNKNOWN, codes)
        intermediary = next(e for e in a_link(ledger)["counter_evidence"]
                            if e["reason_code"] == B13B.X03_INTERMEDIARY_ROLE_UNKNOWN)
        self.assertEqual(intermediary["addresses"], [FUNDER])

    def test_a_known_service_intermediary_is_called_what_it_is(self):
        register = self.register(FUNDER)
        register.update(self.register(ALICE, B13B.ROLE_NOT_A_SERVICE))
        register.update(self.register(BOB, B13B.ROLE_NOT_A_SERVICE))
        ledger = build([transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB)],
                       role_register=register)
        codes = {e["reason_code"] for e in a_link(ledger)["counter_evidence"]}
        self.assertIn(B13B.X04_INTERMEDIARY_IS_KNOWN_SERVICE, codes)
        self.assertNotIn(B13B.X01_ENDPOINT_ROLE_UNKNOWN, codes)
        self.assertNotIn(B13B.X03_INTERMEDIARY_ROLE_UNKNOWN, codes)

    def test_a_known_service_endpoint_is_flagged(self):
        register = self.register(BOB)
        register.update(self.register(ALICE, B13B.ROLE_NOT_A_SERVICE))
        ledger = build([transfer(200, ALICE, BOB)], role_register=register)
        codes = {e["reason_code"] for e in a_link(ledger)["counter_evidence"]}
        self.assertEqual(codes, {B13B.X02_ENDPOINT_IS_KNOWN_SERVICE})

    def test_a_role_asserted_without_provenance_is_refused(self):
        for field in ("provenance_sha256", "established_by"):
            with self.subTest(missing=field):
                register = self.register(BOB)
                del register[BOB][field]
                with self.assertRaisesRegex(B13B.AssociationRefused, f"states no {field}"):
                    B13B.assert_role_register(register)

    def test_unknown_may_not_be_registered_explicitly(self):
        """Nobody can establish that a role is unknown; unknown is what absence already means."""
        with self.assertRaisesRegex(B13B.AssociationRefused, "nobody can establish"):
            B13B.assert_role_register(self.register(BOB, B13B.ROLE_UNKNOWN))

    def test_an_undeclared_role_is_refused(self):
        with self.assertRaisesRegex(B13B.AssociationRefused, "is not one of"):
            B13B.assert_role_register(self.register(BOB, "probably_an_exchange"))

    def test_losing_a_service_role_changes_the_record(self):
        register = self.register(FUNDER)
        register.update(self.register(ALICE, B13B.ROLE_NOT_A_SERVICE))
        register.update(self.register(BOB, B13B.ROLE_NOT_A_SERVICE))
        events = [transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB)]
        with_roles = build(events, role_register=register)
        without = build(events)
        self.assertNotEqual(with_roles["ledger_sha256"], without["ledger_sha256"])
        self.assertNotEqual(with_roles["role_register_provenance"]["register_sha256"],
                            without["role_register_provenance"]["register_sha256"])

    def test_the_counter_evidence_block_must_agree_with_the_feature_flag(self):
        ledger = build()
        link = a_link(ledger)
        link["counter_evidence"] = []
        with self.assertRaisesRegex(B13B.AssociationRefused, "quietly forgotten"):
            B13B.assert_link(link, B10B.canonical_key(DEFAULT_T0))


class CompletenessTests(unittest.TestCase):
    """Incompleteness propagates from B13a and fails closed here, exactly as it does there."""

    def test_no_lookback_means_no_complete_neighbourhood(self):
        ledger = build()
        codes = [f["reason_code"] for f in B13B.neighbourhood_failures(ledger, ALICE)]
        self.assertIn(B13B.G02_LOOKBACK_NOT_CHOSEN, codes)
        with self.assertRaisesRegex(B13B.AssociationRefused, "G02_lookback_not_chosen"):
            B13B.require_complete_neighbourhood(ledger, ALICE)

    def test_an_address_outside_the_focus_set_reports_its_own_code(self):
        ledger = build()
        codes = [f["reason_code"] for f in B13B.neighbourhood_failures(ledger, CAROL)]
        self.assertIn(B13B.G03_ENDPOINT_HISTORY_ABSENT, codes)

    def test_a_focus_address_with_no_links_is_not_reported_as_absent(self):
        """"Seen and unconnected" and "never looked at" are different facts."""
        ledger = build([transfer(200, ALICE, BOB)], focus=(ALICE, BOB, CAROL))
        codes = [f["reason_code"] for f in B13B.neighbourhood_failures(ledger, CAROL)]
        self.assertNotIn(B13B.G03_ENDPOINT_HISTORY_ABSENT, codes)

    def test_unresolved_evidence_at_or_before_t0_poisons_the_neighbourhood(self):
        unresolved = [{"reason_code": B13A.D01_UNDECODABLE_SYSTEM_PAYLOAD,
                       "coordinate": at(300), "detail": "a payload the pinned ABI refuses"}]
        cover = coverage(complete=False, decode_accounting=accounting(
            system_instructions_total=1, undecodable=1, unresolved=unresolved))
        ledger = build(cover=cover)
        codes = [f["reason_code"] for f in B13B.neighbourhood_failures(ledger, ALICE)]
        self.assertIn(B13B.G04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0, codes)

    def test_unresolved_evidence_after_t0_does_not_poison_it(self):
        unresolved = [{"reason_code": B13A.D01_UNDECODABLE_SYSTEM_PAYLOAD,
                       "coordinate": at(880), "detail": "a payload the pinned ABI refuses"}]
        cover = coverage(complete=False, decode_accounting=accounting(
            system_instructions_total=1, undecodable=1, unresolved=unresolved))
        ledger = build(t0=at(400), cover=cover)
        codes = [f["reason_code"] for f in B13B.neighbourhood_failures(ledger, ALICE)]
        self.assertNotIn(B13B.G04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0, codes)

    def test_a_truncated_window_makes_every_endpoint_a_lower_bound(self):
        ledger = build(cover=coverage(left_truncated=True, complete=False))
        link = a_link(ledger)
        self.assertTrue(link["features"]["counts_are_lower_bounds"])
        codes = {e["reason_code"] for e in link["counter_evidence"]}
        self.assertIn(B13B.X05_EVIDENCE_FROM_INCOMPLETE_HISTORY, codes)

    def test_a_link_may_not_disagree_with_coverage_about_lower_bounds(self):
        ledger = build(cover=coverage(left_truncated=True, complete=False))
        a_link(ledger)["completeness"]["counts_are_lower_bounds"] = False
        with self.assertRaisesRegex(B13B.AssociationRefused, "mistaken for a complete one"):
            B13B.assert_ledger(ledger)

    def test_an_incomplete_history_may_not_be_promoted_to_complete(self):
        ledger = build(cover=coverage(left_truncated=True, complete=False))
        link = a_link(ledger)
        link["features"]["neighbourhood_complete"] = True
        link["completeness"]["neighbourhood_complete"] = True
        with self.assertRaisesRegex(B13B.AssociationRefused, "quietest way for a lower bound"):
            B13B.assert_link(link, B10B.canonical_key(DEFAULT_T0))

    def test_the_features_and_completeness_blocks_must_agree(self):
        link = a_link(build())
        link["features"]["neighbourhood_complete"] = True
        with self.assertRaisesRegex(B13B.AssociationRefused, "disagree with its completeness"):
            B13B.assert_link(link, B10B.canonical_key(DEFAULT_T0))


class LookbackTests(unittest.TestCase):
    """Not chosen here, and the record says so rather than defaulting to something."""

    def test_the_shipped_lookback_is_unchosen_and_says_why(self):
        lookback = B13B.unchosen_lookback()
        self.assertFalse(lookback["lookback_chosen"])
        self.assertIsNone(lookback["lookback_slots"])
        self.assertIn("NOT CHOSEN", lookback["rationale"])

    def test_a_number_nobody_chose_is_refused(self):
        lookback = B13B.unchosen_lookback()
        lookback["lookback_slots"] = 432_000
        with self.assertRaisesRegex(B13B.AssociationRefused, "number nobody chose"):
            B13B.assert_lookback(lookback)

    def test_a_chosen_lookback_must_name_its_preregistration(self):
        lookback = {"lookback_slots": 432_000, "lookback_chosen": True,
                    "preregistration_reference": None, "rationale": "felt about right"}
        with self.assertRaisesRegex(B13B.AssociationRefused, "picked for its results"):
            B13B.assert_lookback(lookback)

    def test_a_properly_preregistered_lookback_is_accepted(self):
        lookback = {"lookback_slots": 432_000, "lookback_chosen": True,
                    "preregistration_reference": "research/B13C_PREREG.md#lookback",
                    "rationale": "one operational day, frozen before any actor was enumerated"}
        self.assertTrue(B13B.assert_lookback(lookback))

    def test_no_repetition_threshold_is_applied(self):
        ledger = build([transfer(200, ALICE, BOB), transfer(300, ALICE, BOB)])
        repeated = next(i for i in a_link(ledger)["evidence"]
                        if i["kind"] == B13B.E03_REPEATED_COUNTERPARTY)
        self.assertFalse(repeated["facts"]["repetition_threshold_applied"])
        self.assertEqual(repeated["facts"]["transfer_count_observed"], 2)


class CalibrationRefusalTests(unittest.TestCase):
    """No probability, no score, no cluster — enforced by name and by type."""

    def test_every_link_and_the_ledger_declare_themselves_uncalibrated(self):
        ledger = build()
        self.assertEqual(ledger["confidence_status"], "uncalibrated_evidence_only")
        for link in ledger["links"]:
            self.assertEqual(link["confidence_status"], "uncalibrated_evidence_only")

    def test_a_ledger_claiming_any_other_status_is_refused(self):
        ledger = build()
        ledger["confidence_status"] = "calibrated"
        with self.assertRaisesRegex(B13B.AssociationRefused, "has earned anything but"):
            B13B.assert_ledger(ledger)

    def test_a_link_claiming_any_other_status_is_refused(self):
        link = a_link(build())
        link["confidence_status"] = "high"
        with self.assertRaisesRegex(B13B.AssociationRefused, "has earned any other"):
            B13B.assert_link(link, B10B.canonical_key(DEFAULT_T0))

    def test_a_forbidden_field_name_is_refused_wherever_it_appears(self):
        for name in ("cluster_id", "probability", "same_owner", "component_id", "merge_target",
                     "confidence_score", "posterior", "entity_id", "calibration", "p_same_owner"):
            with self.subTest(field=name):
                ledger = build()
                a_link(ledger)["evidence"][0]["facts"][name] = 1
                with self.assertRaisesRegex(B13B.AssociationRefused, "asserts a cluster"):
                    B13B.assert_uncalibrated(ledger)

    def test_a_forbidden_name_is_refused_even_holding_an_innocent_value(self):
        """The damage is done the moment a later reader sees the name."""
        ledger = build()
        ledger["accounting"]["cluster_count"] = 0
        with self.assertRaisesRegex(B13B.AssociationRefused, "cluster"):
            B13B.assert_uncalibrated(ledger)

    def test_no_float_may_appear_anywhere(self):
        ledger = build()
        a_link(ledger)["evidence"][0]["facts"]["lamports"] = 7.0
        with self.assertRaisesRegex(B13B.AssociationRefused, "No float may appear"):
            B13B.assert_no_float(ledger)

    def test_a_clean_ledger_passes_both_scans(self):
        ledger = build([transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB),
                        transfer(300, ALICE, BOB), launch(400, creator=ALICE, create_user=BOB)])
        self.assertTrue(B13B.assert_uncalibrated(ledger))
        self.assertTrue(B13B.assert_no_float(ledger))


class IdentityLeakageTests(unittest.TestCase):
    """Addresses live in grouping and evidence. Never in a feature block."""

    def test_no_string_may_appear_in_a_feature_block(self):
        for value in (ALICE, "", "0"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(B13B.AssociationRefused, "NO STRING MAY APPEAR"):
                    B13B.assert_no_identity_in_features({"evidence_item_count_observed": value})

    def test_every_shipped_feature_is_an_integer_or_boolean(self):
        ledger = build([transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB),
                        transfer(300, ALICE, BOB)])
        for link in ledger["links"]:
            for field, value in link["features"].items():
                with self.subTest(field=field):
                    self.assertIsInstance(value, (int, bool))

    def test_grouping_and_feature_fields_are_disjoint_and_the_check_is_reachable(self):
        self.assertTrue(B13B.assert_disjoint_blocks(B13B.GROUPING_FIELDS,
                                                    B13B.LINK_FEATURE_FIELDS))
        with self.assertRaisesRegex(B13B.AssociationRefused, "identity used for prediction"):
            B13B.assert_disjoint_blocks(("address_a",), ("address_a", "count_observed"))

    def test_the_feature_contract_is_exactly_what_is_shipped(self):
        link = a_link(build())
        self.assertEqual(set(link["features"]), set(B13B.LINK_FEATURE_FIELDS))
        link["features"]["invented"] = 1
        with self.assertRaisesRegex(B13B.AssociationRefused, "contract says"):
            B13B.assert_link(link, B10B.canonical_key(DEFAULT_T0))

    def test_grouping_must_agree_with_the_link_about_its_relation(self):
        link = a_link(build())
        link["grouping"]["relation_type"] = B13B.RELATION_IDENTITY_EQUALITY
        with self.assertRaisesRegex(B13B.AssociationRefused, "grouping disagrees"):
            B13B.assert_link(link, B10B.canonical_key(DEFAULT_T0))


class EvidenceIntegrityTests(unittest.TestCase):
    """Duplicated evidence reads as corroboration; drifting provenance reads as the same evidence."""

    def test_the_same_observation_twice_is_refused(self):
        item = evidence_item()
        with self.assertRaisesRegex(B13B.AssociationRefused, "looks like two independent ones"):
            B13B.build_link(B13B.RELATION_ASSOCIATION_EVIDENCE, ALICE, BOB,
                            [item, copy.deepcopy(item)], B10B.canonical_key(DEFAULT_T0))

    def test_a_duplicate_smuggled_in_after_assembly_is_caught(self):
        link = a_link(build())
        link["evidence"].append(copy.deepcopy(link["evidence"][0]))
        with self.assertRaisesRegex(B13B.AssociationRefused, "same evidence item twice"):
            B13B.assert_link(link, B10B.canonical_key(DEFAULT_T0))

    def test_a_link_with_no_evidence_is_an_assertion(self):
        with self.assertRaisesRegex(B13B.AssociationRefused, "no evidence is an assertion"):
            B13B.build_link(B13B.RELATION_ASSOCIATION_EVIDENCE, ALICE, BOB, [],
                            B10B.canonical_key(DEFAULT_T0))

    def test_evidence_must_name_a_source_for_every_coordinate(self):
        item = evidence_item(coordinates=[at(200), at(300)], source_sha256_list=["only-one"])
        with self.assertRaisesRegex(B13B.AssociationRefused, "must name the evidence it came from"):
            B13B.assert_evidence_item(item, (ALICE, BOB), B10B.canonical_key(DEFAULT_T0))

    def test_an_empty_source_hash_is_refused(self):
        item = evidence_item(source_sha256_list=[""])
        with self.assertRaisesRegex(B13B.AssociationRefused, "empty source hash"):
            B13B.assert_evidence_item(item, (ALICE, BOB), B10B.canonical_key(DEFAULT_T0))

    def test_evidence_hash_drift_changes_the_chain_and_the_ledger(self):
        base = build([transfer(200, ALICE, BOB, source="original")])
        drifted = build([transfer(200, ALICE, BOB, source="re-collected")])
        self.assertNotEqual(base["evidence_hash_chain_sha256"],
                            drifted["evidence_hash_chain_sha256"])
        self.assertNotEqual(base["ledger_sha256"], drifted["ledger_sha256"])

    def test_the_hash_chain_covers_only_evidence_inside_the_boundary(self):
        inside = build([transfer(200, ALICE, BOB)])
        with_future = build([transfer(200, ALICE, BOB), transfer(950, ALICE, BOB)])
        self.assertEqual(inside["evidence_hash_chain_sha256"],
                         with_future["evidence_hash_chain_sha256"])

    def test_evidence_without_a_coordinate_is_refused(self):
        with self.assertRaisesRegex(B13B.AssociationRefused, "cannot say where"):
            B13B.assert_evidence_item(evidence_item(coordinates=[]), (ALICE, BOB),
                                      B10B.canonical_key(DEFAULT_T0))

    def test_an_undeclared_evidence_field_is_refused(self):
        with self.assertRaisesRegex(B13B.AssociationRefused, "undeclared fields"):
            B13B.assert_evidence_item(evidence_item(smuggled=1), (ALICE, BOB),
                                      B10B.canonical_key(DEFAULT_T0))

    def test_witness_addresses_must_be_sorted(self):
        item = evidence_item(witness_addresses=[BOB, ALICE])
        with self.assertRaisesRegex(B13B.AssociationRefused, "must be sorted"):
            B13B.assert_evidence_item(item, (ALICE, BOB), B10B.canonical_key(DEFAULT_T0))


class DeterminismTests(unittest.TestCase):
    """Identical evidence in any order gives a byte-identical record."""

    def events(self):
        return [transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB),
                transfer(300, ALICE, BOB), transfer(310, BOB, ALICE),
                launch(400, creator=ALICE, create_user=BOB), trade(500, user=ALICE)]

    def test_arrival_order_does_not_change_the_ledger(self):
        events = self.events()
        first = build(events, focus=(ALICE, BOB, CAROL))
        second = build(list(reversed(events)), focus=(CAROL, BOB, ALICE))
        self.assertEqual(first["ledger_sha256"], second["ledger_sha256"])

    def test_rebuilding_is_byte_identical(self):
        self.assertEqual(B10B.canonical_json(build(self.events())),
                         B10B.canonical_json(build(self.events())))

    def test_two_events_at_one_coordinate_still_order_deterministically(self):
        """One transaction can name a launch and a trade at the same coordinate."""
        events = [launch(400, creator=ALICE, create_user=BOB, index=1),
                  trade(400, user=ALICE, index=1)]
        first = build(events, focus=(ALICE, BOB))
        second = build(list(reversed(events)), focus=(ALICE, BOB))
        self.assertEqual(first["ledger_sha256"], second["ledger_sha256"])

    def test_links_are_emitted_in_canonical_order(self):
        """Not merely deterministic — canonical. Two ledgers over the same evidence must present
        their links in the same order, or a reader diffing them sees changes that are not there."""
        ledger = build(self.events(), focus=(ALICE, BOB, CAROL, FUNDER))
        keys = [(link["grouping"]["address_a"], link["grouping"]["address_b"],
                 link["relation_type"], link["link_sha256"]) for link in ledger["links"]]
        self.assertEqual(keys, sorted(keys))
        self.assertGreater(len(keys), 1)

    def test_evidence_derivation_does_not_depend_on_the_order_it_is_handed(self):
        """Driven below `build_association_ledger`, which pre-sorts: the derivation must be stable
        on its own, or the tiebreak that makes it so is a guard nobody can show works."""
        events = [launch(400, creator=ALICE, create_user=BOB, index=1),
                  trade(400, user=ALICE, index=1), transfer(400, ALICE, BOB, index=1)]
        t0 = B10B.canonical_key(DEFAULT_T0)
        forward = B13B._pair_evidence(events, ALICE, BOB, t0)
        backward = B13B._pair_evidence(list(reversed(events)), ALICE, BOB, t0)
        self.assertEqual(B10B.canonical_json(forward), B10B.canonical_json(backward))

    def test_every_link_carries_its_own_hash(self):
        ledger = build(self.events(), focus=(ALICE, BOB))
        for link in ledger["links"]:
            self.assertEqual(link["link_sha256"], B13B.link_hash(link))

    def test_changing_one_evidence_item_changes_the_link_hash(self):
        base = a_link(build([transfer(200, ALICE, BOB, lamports=1)]))
        other = a_link(build([transfer(200, ALICE, BOB, lamports=2)]))
        self.assertNotEqual(base["link_sha256"], other["link_sha256"])


class AccountingTests(unittest.TestCase):
    """The accounting must describe the links it ships with, not something else."""

    def test_the_accounting_matches_the_links(self):
        ledger = build([transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB),
                        transfer(300, ALICE, BOB), launch(400, creator=ALICE, create_user=BOB)],
                       focus=(ALICE, BOB, CAROL))
        self.assertEqual(ledger["accounting"]["links_emitted"], len(ledger["links"]))
        self.assertEqual(ledger["accounting"]["evidence_items"],
                         sum(len(link["evidence"]) for link in ledger["links"]))
        self.assertEqual(ledger["accounting"]["pairs_considered"], 3)
        self.assertEqual(ledger["accounting"]["focus_addresses"], 3)

    def test_an_accounting_that_disagrees_with_the_evidence_is_refused(self):
        ledger = build()
        ledger["accounting"]["evidence_by_kind"][B13B.E02_SHARED_FUNDER] += 1
        with self.assertRaisesRegex(B13B.AssociationRefused, "accounting of something else"):
            B13B.assert_ledger(ledger)

    def test_an_accounting_that_miscounts_links_is_refused(self):
        ledger = build()
        ledger["accounting"]["links_emitted"] += 1
        with self.assertRaisesRegex(B13B.AssociationRefused, "how many there are"):
            B13B.assert_ledger(ledger)

    def test_a_relation_miscount_is_refused(self):
        ledger = build()
        ledger["accounting"]["links_by_relation"][B13B.RELATION_IDENTITY_EQUALITY] += 1
        with self.assertRaisesRegex(B13B.AssociationRefused, "about relation types"):
            B13B.assert_ledger(ledger)

    def test_two_links_for_the_same_pair_are_refused(self):
        ledger = build()
        ledger["links"].append(copy.deepcopy(a_link(ledger)))
        with self.assertRaisesRegex(B13B.AssociationRefused, "reads as two findings"):
            B13B.assert_ledger(ledger)

    def test_an_undeclared_top_level_field_is_refused(self):
        ledger = build()
        ledger["notes"] = "just a note"
        with self.assertRaisesRegex(B13B.AssociationRefused, "undeclared fields"):
            B13B.assert_ledger(ledger)

    def test_the_ledger_reports_what_it_discarded(self):
        ledger = build([transfer(200, ALICE, BOB), transfer(950, ALICE, BOB),
                        transfer(960, ALICE, BOB)])
        self.assertEqual(ledger["accounting"]["events_supplied"], 3)
        self.assertEqual(ledger["accounting"]["events_visible"], 1)
        self.assertEqual(ledger["accounting"]["events_discarded_after_t0"], 2)


class GateTests(unittest.TestCase):
    """The plumbing gate's own conditions, exercised without running the corpus."""

    def setUp(self):
        self.corpus = _load("b13b_association_corpus", "b13b_association_corpus.py")

    def clean_report(self):
        return {
            "errors": [], "instants_checked": 5, "boundary_respected": 5,
            "every_link_witnessed": 5, "counter_evidence_on_every_link": 5,
            "identity_kept_out_of_features": 5, "order_independent": 5,
            "neighbourhood_refused_for_every_address": 60,
            "addresses_checked_for_completeness": 60,
            "refusals_verified": {"cluster_id": True}, "association_degree_reported": False,
            "clusters_inferred": False, "transitive_closure_taken": False,
        }

    def test_a_clean_report_passes(self):
        self.assertEqual(self.corpus.gate_failures(self.clean_report()), [])

    def test_every_gate_condition_can_fail(self):
        cases = {
            "integrity errors": {"errors": [{"error": "x"}]},
            "boundary_respected": {"boundary_respected": 4},
            "every_link_witnessed": {"every_link_witnessed": 4},
            "counter_evidence_on_every_link": {"counter_evidence_on_every_link": 4},
            "identity_kept_out_of_features": {"identity_kept_out_of_features": 4},
            "order_independent": {"order_independent": 4},
            "completeness check pass": {"neighbourhood_refused_for_every_address": 59},
            "fail closed did not": {"refusals_verified": {"cluster_id": False}},
            "association degree": {"association_degree_reported": True},
            "transitive closure": {"clusters_inferred": True},
        }
        for expected, override in cases.items():
            with self.subTest(condition=expected):
                report = self.clean_report()
                report.update(override)
                failures = self.corpus.gate_failures(report)
                self.assertTrue(any(expected in failure for failure in failures),
                                f"{expected!r} not in {failures}")

    def test_focus_addresses_come_from_transfers_in_first_appearance_order(self):
        """Not by degree. Selecting on how connected a wallet is would make every count in the
        report a consequence of the choice rather than a property of the data."""
        events, _ = B13A.ordered_events([
            launch(100, creator="ZZZZcreator", create_user="ZZZZcreator"),
            transfer(200, "BBBfirst", "AAAsecond"),
            transfer(300, "AAAsecond", "CCCthird"),
            transfer(400, "DDDfourth", "BBBfirst"),
        ])
        self.assertEqual(self.corpus.focus_addresses(events, 3),
                         sorted(["BBBfirst", "AAAsecond", "CCCthird"]))
        self.assertNotIn("ZZZZcreator", self.corpus.focus_addresses(events, 4))

    def test_the_focus_rule_is_published_with_the_report(self):
        self.assertIn("NOT by degree", self.corpus.FOCUS_SELECTION_RULE)


class EvidenceDerivationTests(unittest.TestCase):
    """What each kind is actually derived from."""

    def test_a_shared_funder_needs_two_edges_from_one_address(self):
        alone = build([transfer(200, FUNDER, ALICE)], focus=(ALICE, BOB))
        self.assertEqual(alone["links"], [])
        both = build([transfer(200, FUNDER, ALICE), transfer(210, FUNDER, BOB)])
        self.assertEqual(a_link(both)["features"]["shared_funder_count_observed"], 1)
        self.assertEqual(a_link(both)["features"]["distinct_shared_funder_count_observed"], 1)

    def test_an_endpoint_funding_the_other_is_not_a_shared_funder(self):
        ledger = build([transfer(200, ALICE, BOB), transfer(210, ALICE, ALICE.replace("a", "z"))])
        self.assertEqual(a_link(ledger)["features"]["shared_funder_count_observed"], 0)

    def test_co_signing_needs_two_different_launch_roles(self):
        ledger = build([launch(400, creator=ALICE, create_user=BOB)])
        self.assertEqual(a_link(ledger)["features"]["co_signing_count_observed"], 1)
        self.assertEqual(build([launch(400, creator=ALICE, create_user=ALICE)],
                               focus=(ALICE, BOB))["links"], [])

    def test_co_occurrence_overlaps_other_kinds_and_says_so(self):
        """Overlapping evidence is not independent evidence, which is one more reason these
        counts may never be added into a score."""
        ledger = build([transfer(200, ALICE, BOB)])
        link = a_link(ledger)
        self.assertEqual(link["features"]["direct_transfer_count_observed"], 1)
        self.assertEqual(link["features"]["co_occurrence_count_observed"], 1)
        co = next(i for i in link["evidence"]
                  if i["kind"] == B13B.E04_CO_OCCURRENCE_IN_TRANSACTION)
        self.assertTrue(co["facts"]["overlaps_other_evidence_kinds"])

    def test_a_pair_that_shares_nothing_produces_no_link(self):
        ledger = build([transfer(200, ALICE, "ZZZZother"), transfer(300, BOB, "YYYYother")],
                       focus=(ALICE, BOB))
        self.assertEqual(ledger["links"], [])
        self.assertEqual(ledger["accounting"]["pairs_considered"], 1)

    def test_a_single_role_is_not_an_identity_link(self):
        ledger = build([trade(300, user=ALICE)], focus=(ALICE, BOB))
        self.assertEqual(ledger["links"], [])

    def test_focus_addresses_must_be_a_collection_not_a_string(self):
        with self.assertRaisesRegex(B13B.AssociationRefused, "must be a collection"):
            B13B.build_association_ledger([], ALICE, DEFAULT_T0, coverage())


if __name__ == "__main__":
    unittest.main()
