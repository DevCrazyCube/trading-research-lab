"""Focused tests for B7k decoder common-mode validation.

These pin the properties the preregistration froze, and - the point of the exercise - they
demonstrate the instrument is capable of FAILING before it is pointed at real data. A validator
that cannot fail proves nothing when it passes.

Fixtures are synthetic payloads with layouts known by construction, so a check that passes here
passes for a reason we control.
"""
import importlib.util
import json
import pathlib
import struct
import sys
import unittest

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "b7k", ROOT / "scripts" / "b7k_decoder_common_mode.py")
B7K = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B7K)
IDL = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
TYPES = {item["name"]: item for item in IDL["types"]}

BLOCK_TIME = 1785166729


def pubkey(seed):
    """A deterministic 32-byte pubkey and its base58 form."""
    raw = bytes([seed]) * 32
    return raw, B7K.b7d.b58encode(raw)


def complete_event_payload(user, mint, curve, timestamp, quote):
    """CompleteEvent by construction: disc(8) user mint bonding_curve timestamp quote_mint."""
    return (B7K.event_discriminator("CompleteEvent") + user + mint + curve
            + struct.pack("<q", timestamp) + quote)


def transaction_with(keys, version=None, lookups=False, loaded=None):
    message = {"accountKeys": [{"pubkey": k} for k in keys]}
    if lookups:
        message["addressTableLookups"] = [{"accountKey": "T" * 32}]
    transaction = {"transaction": {"message": message, "signatures": ["sig"]},
                   "meta": {"err": None}, "blockTime": BLOCK_TIME}
    if version is not None:
        transaction["version"] = version
    if loaded is not None:
        transaction["meta"]["loadedAddresses"] = loaded
    return transaction


class GraduationChecks(unittest.TestCase):
    def setUp(self):
        self.user, self.user_b58 = pubkey(1)
        self.mint, self.mint_b58 = pubkey(2)
        self.curve, self.curve_b58 = pubkey(3)
        self.quote, self.quote_b58 = pubkey(4)
        self.payload = complete_event_payload(self.user, self.mint, self.curve,
                                              BLOCK_TIME, self.quote)
        self.transaction = transaction_with(
            [self.user_b58, self.mint_b58, self.curve_b58])

    def test_well_formed_event_passes_every_load_bearing_check(self):
        result = B7K.check_event("CompleteEvent", self.payload, self.transaction,
                                 BLOCK_TIME, TYPES)
        self.assertTrue(result["c1_membership"], result["detail"])
        self.assertTrue(result["c2_timestamp"], result["detail"])
        self.assertTrue(result["c3_exact_consumption"], result["detail"])
        self.assertIsNone(result["unresolvable"])
        self.assertEqual(result["quote_mint"], self.quote_b58)

    def test_shifted_offset_FAILS(self):
        """The instrument-can-fail test.

        Insert one byte after the discriminator so every subsequent field is misaligned - exactly
        the common-mode error class this whole task exists to detect. If this ever passes, B7k is
        not measuring anything.
        """
        corrupted = self.payload[:8] + b"\x00" + self.payload[8:]
        result = B7K.check_event("CompleteEvent", corrupted, self.transaction,
                                 BLOCK_TIME, TYPES)
        self.assertFalse(result["c1_membership"] and result["c2_timestamp"]
                         and result["c3_exact_consumption"],
                         "a one-byte offset shift must not pass every check")

    def test_wrong_timestamp_fails_c2(self):
        payload = complete_event_payload(self.user, self.mint, self.curve,
                                         BLOCK_TIME + 1, self.quote)
        result = B7K.check_event("CompleteEvent", payload, self.transaction,
                                 BLOCK_TIME, TYPES)
        self.assertFalse(result["c2_timestamp"])
        self.assertTrue(result["c1_membership"])

    def test_pubkey_absent_from_account_keys_fails_c1(self):
        stranger, _ = pubkey(9)
        payload = complete_event_payload(self.user, stranger, self.curve,
                                         BLOCK_TIME, self.quote)
        result = B7K.check_event("CompleteEvent", payload, self.transaction,
                                 BLOCK_TIME, TYPES)
        self.assertFalse(result["c1_membership"])
        self.assertIn("mint=", " ".join(result["detail"]))

    def test_trailing_bytes_fail_c3(self):
        result = B7K.check_event("CompleteEvent", self.payload + b"\x07",
                                 self.transaction, BLOCK_TIME, TYPES)
        self.assertFalse(result["c3_exact_consumption"])

    def test_quote_mint_absence_from_account_keys_is_not_a_failure(self):
        """C4 is frozen as reported-only. quote_mint may name a mint the transaction never
        touches, so its absence must not be scored against C1."""
        self.assertNotIn("quote_mint", B7K.MEMBERSHIP_FIELDS["CompleteEvent"])
        result = B7K.check_event("CompleteEvent", self.payload, self.transaction,
                                 BLOCK_TIME, TYPES)
        self.assertTrue(result["c1_membership"])

    def test_transposed_pubkeys_still_pass_c1_known_limitation(self):
        """Asserted so the preregistered limitation cannot silently change.

        C1 is membership, not identity: swapping two pubkey fields leaves both in the account-key
        set. B7k does not detect this and the preregistration says so.
        """
        payload = complete_event_payload(self.mint, self.user, self.curve,
                                         BLOCK_TIME, self.quote)
        result = B7K.check_event("CompleteEvent", payload, self.transaction,
                                 BLOCK_TIME, TYPES)
        self.assertTrue(result["c1_membership"],
                        "transposition passing C1 is the documented residual weakness")


class Resolvability(unittest.TestCase):
    def test_unresolved_lookup_table_is_unresolvable_not_a_pass(self):
        user, user_b58 = pubkey(1)
        mint, mint_b58 = pubkey(2)
        curve, curve_b58 = pubkey(3)
        quote, _ = pubkey(4)
        payload = complete_event_payload(user, mint, curve, BLOCK_TIME, quote)
        transaction = transaction_with([user_b58, mint_b58, curve_b58],
                                       version=0, lookups=True)
        result = B7K.check_event("CompleteEvent", payload, transaction,
                                 BLOCK_TIME, TYPES)
        self.assertIsNotNone(result["unresolvable"])
        self.assertIsNone(result["c1_membership"])

    def test_jsonparsed_inlined_lookup_addresses_are_resolved(self):
        """Regression for a defect found at first contact with real data.

        Under jsonParsed encoding the RPC resolves address-table entries into accountKeys tagged
        source='lookupTable', and meta.loadedAddresses is absent as a result. The first version of
        the guard read that absence as failure and scored all four real graduation events
        UNRESOLVABLE. Every B7j reference transaction has this exact shape.
        """
        user, user_b58 = pubkey(1)
        mint, mint_b58 = pubkey(2)
        curve, curve_b58 = pubkey(3)
        quote, _ = pubkey(4)
        payload = complete_event_payload(user, mint, curve, BLOCK_TIME, quote)
        transaction = {
            "version": 0,
            "blockTime": BLOCK_TIME,
            "meta": {"err": None},
            "transaction": {"signatures": ["sig"], "message": {
                "accountKeys": [{"pubkey": user_b58, "source": "transaction"},
                                {"pubkey": mint_b58, "source": "lookupTable"},
                                {"pubkey": curve_b58, "source": "lookupTable"}],
                "addressTableLookups": [{"accountKey": "T" * 32}]}}}
        result = B7K.check_event("CompleteEvent", payload, transaction, BLOCK_TIME, TYPES)
        self.assertIsNone(result["unresolvable"])
        self.assertTrue(result["c1_membership"], result["detail"])

    def test_lookups_with_no_resolution_are_still_unresolvable(self):
        """The guard must not have been weakened into never firing."""
        user, user_b58 = pubkey(1)
        mint, _ = pubkey(2)
        curve, _ = pubkey(3)
        quote, _ = pubkey(4)
        payload = complete_event_payload(user, mint, curve, BLOCK_TIME, quote)
        transaction = {
            "version": 0, "blockTime": BLOCK_TIME, "meta": {"err": None},
            "transaction": {"signatures": ["sig"], "message": {
                "accountKeys": [user_b58],
                "addressTableLookups": [{"accountKey": "T" * 32}]}}}
        result = B7K.check_event("CompleteEvent", payload, transaction, BLOCK_TIME, TYPES)
        self.assertIsNotNone(result["unresolvable"])

    def test_loaded_addresses_are_included_in_the_resolved_set(self):
        user, user_b58 = pubkey(1)
        mint, mint_b58 = pubkey(2)
        curve, curve_b58 = pubkey(3)
        quote, _ = pubkey(4)
        payload = complete_event_payload(user, mint, curve, BLOCK_TIME, quote)
        transaction = transaction_with([user_b58], version=0, lookups=True,
                                       loaded={"writable": [mint_b58],
                                               "readonly": [curve_b58]})
        result = B7K.check_event("CompleteEvent", payload, transaction,
                                 BLOCK_TIME, TYPES)
        self.assertIsNone(result["unresolvable"])
        self.assertTrue(result["c1_membership"], result["detail"])


class VerdictRule(unittest.TestCase):
    def test_empty_set_is_inconclusive_never_pass(self):
        self.assertEqual(B7K.verdict([], "graduation")["verdict"], "INCONCLUSIVE")

    def test_any_load_bearing_failure_is_fail(self):
        results = [{"c1_membership": True, "c2_timestamp": True,
                    "c3_exact_consumption": True},
                   {"c1_membership": False, "c2_timestamp": True,
                    "c3_exact_consumption": True, "detail": []}]
        self.assertEqual(B7K.verdict(results, "graduation")["verdict"], "FAIL")

    def test_unresolvable_blocks_a_pass(self):
        results = [{"c1_membership": None, "c2_timestamp": None,
                    "c3_exact_consumption": True, "unresolvable": "lookup table"}]
        self.assertEqual(B7K.verdict(results, "graduation")["verdict"], "INCONCLUSIVE")

    def test_all_clean_is_pass(self):
        results = [{"c1_membership": True, "c2_timestamp": True,
                    "c3_exact_consumption": True}] * 3
        outcome = B7K.verdict(results, "graduation")
        self.assertEqual(outcome["verdict"], "PASS")
        self.assertEqual(outcome["n"], 3)


class FrozenScope(unittest.TestCase):
    def test_membership_fields_match_the_preregistration(self):
        self.assertEqual(B7K.MEMBERSHIP_FIELDS["CompleteEvent"],
                         ("user", "mint", "bonding_curve"))
        self.assertEqual(B7K.MEMBERSHIP_FIELDS["CompletePumpAmmMigrationEvent"],
                         ("user", "mint", "bonding_curve", "pool"))
        self.assertEqual(B7K.MEMBERSHIP_FIELDS["TradeEvent"], ("mint", "user"))

    def test_decoder_under_test_is_the_shared_one(self):
        """B7k must exercise the decoder it is validating, not a private copy."""
        self.assertIs(B7K.b7d.read_struct.__code__,
                      __import__("b7d_create_enumerator").read_struct.__code__)


if __name__ == "__main__":
    unittest.main()
