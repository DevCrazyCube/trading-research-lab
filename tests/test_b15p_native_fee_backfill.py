"""B15p tests. The dependency audit is proven by making it catch the module that caused B15O.

The claim worth breaking is that no data flows from a closed recorder. So the static audit is aimed
at the real offender and must refuse it, and the runtime guard is given a forbidden path to open. A
manifest that only ever passes proves nothing.
"""
import base64
import importlib.util
import json
import pathlib
import random
import shutil
import sqlite3
import struct
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


B15P = _load("b15p_native_fee_backfill", "b15p_native_fee_backfill.py")
# Imported by the TESTS only, to prove decode equivalence. The study itself must not depend on it,
# and the audit below asserts exactly that.
B15H = _load("b15h_prospective_entry", "b15h_prospective_entry.py")
PILOT = B15H.PILOT
FIXTURES = _load("b15a_shadow_fixtures", "b15a_shadow_fixtures.py")

ARTIFACT_SHA = "394eeb5a62b05471569c8d6406e18fd4a8f7fd7e454925186628ce294e958e5b"
MEMBER_SET_SHA = "661f953a3aa995abe9a013e69da080f71bad212666a40610d859764b2855a296"
SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}


def encode_field(type_name, types):
    """The project's fixture encoder, extended for the vec the TradeEvent actually carries.

    `shareholders` is a `vec` of a defined struct and the existing encoder refuses to guess at it,
    which is correct of it. An empty vec is a four-byte zero length in Borsh, so the fixture supplies
    that rather than teaching the shared encoder a new type it does not need.
    """
    if isinstance(type_name, dict) and "vec" in type_name:
        return (0).to_bytes(4, "little")
    return FIXTURES._encode(type_name, types)


def trade_payload(schedule=None, tagged=False):
    """A real TradeEvent under the pinned IDL, carrying the given fee basis points."""
    schedule = SCHEDULE if schedule is None else schedule
    pinned = B15P.load_pinned_types()
    types = pinned["types"]
    body = bytearray(pinned["trade_discriminator"])
    field_to_key = {"fee_basis_points": "fee_bps", "creator_fee_basis_points": "creator_fee_bps",
                    "cashback_fee_basis_points": "cashback_fee_bps",
                    "buyback_fee_basis_points": "buyback_fee_bps"}
    for field in types["TradeEvent"]["type"]["fields"]:
        key = field_to_key.get(field["name"])
        if key is not None:
            body += int(schedule[key]).to_bytes(8, "little")     # every fee field is u64
        else:
            body += encode_field(field["type"], types)
    tag = bytes.fromhex("e445a52e51cb9a1d")
    return (tag + bytes(body)) if tagged else bytes(body)


def create_payload(tagged=False):
    payload = FIXTURES.create_payload()          # already carries the event tag
    tag = bytes.fromhex("e445a52e51cb9a1d")
    return payload if tagged else payload[len(tag):]


def decoded_mint():
    pinned = B15P.load_pinned_types()
    create, _trade = B15P.decode_events([create_payload()], pinned)
    return create["mint"]


def log_lines(*payloads):
    return [f"Program data: {base64.b64encode(p).decode()}" for p in payloads]


def transaction(signature, slot, payloads, signatures=None):
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"slot": slot,
                       "transaction": {"signatures": signatures or [signature]},
                       "meta": {"logMessages": log_lines(*payloads)}}}


def opener_for(responses):
    queue = list(responses)

    def opener(request, timeout=None):
        payload = queue.pop(0) if len(queue) > 1 else queue[0]

        class Handle:
            status = 200

            def read(self_inner):
                if isinstance(payload, Exception):
                    raise payload
                return json.dumps(payload).encode()

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *_):
                return False
        if isinstance(payload, Exception):
            raise payload
        return Handle()
    return opener


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b15p_"))
        self.document = B15P.verify_preregistration()
        self.pinned = B15P.load_pinned_types()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def member(self, signature="Sig1", slot=436_984_368, mint=None):
        return {"signature": signature, "t0_slot": slot,
                "mint": mint if mint is not None else decoded_mint()}

    def small_document(self, members):
        """A freeze copy pinned to a synthetic roster, so fixtures need no live evidence."""
        document = json.loads(json.dumps(self.document))
        document["the_frozen_member_set"]["size"] = len(members)
        document["the_frozen_member_set"]["member_set_sha256"] = B15P.member_set_hash(members)
        return document


class TestFreeze(Base):
    def test_the_freeze_is_pinned(self):
        self.assertEqual(self.document["preregistration_id"], "B15P_NATIVE_FEE_BACKFILL_V1")
        self.assertTrue(self.document["committed_before_any_rpc"])

    def test_the_artifact_and_roster_hashes_are_the_measured_ones(self):
        frozen = self.document["the_frozen_member_set"]
        self.assertEqual(frozen["b15o_artifact_sha256"], ARTIFACT_SHA)
        self.assertEqual(frozen["member_set_sha256"], MEMBER_SET_SHA)
        self.assertEqual(frozen["size"], 5000)

    def test_a_tampered_freeze_refuses(self):
        altered = self.directory / "altered.json"
        document = json.loads(B15P.PREREG_PATH.read_bytes())
        document["retrieval"]["max_requests_per_second"] = 50
        altered.write_text(json.dumps(document))
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.verify_preregistration(altered)
        self.assertIn("pinned", str(caught.exception))

    def test_an_unreadable_freeze_refuses(self):
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.verify_preregistration(self.directory / "absent.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_no_execution_surface(self):
        self.assertTrue(B15P.assert_no_execution_surface())

    def test_an_execution_surface_is_caught(self):
        poisoned = self.directory / "poisoned.py"
        poisoned.write_text("FORBIDDEN_DIRECTORY_TOKENS = ()\nx = 'sendTransaction'\n")
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.assert_no_execution_surface(poisoned)
        self.assertIn("sendTransaction", str(caught.exception))

    def test_the_rate_ceiling_is_two_per_second(self):
        self.assertEqual(self.document["retrieval"]["max_requests_per_second"], 2)


class TestDependencyAudit(Base):
    """A manifest that only ever passes proves nothing, so it is aimed at the real offender."""

    def test_this_study_has_a_clean_two_module_closure(self):
        audit = B15P.static_dependency_audit()
        self.assertEqual(audit["forbidden_references"], {})
        self.assertEqual(sorted(audit["closure"]),
                         ["b15p_native_fee_backfill.py", "b7d_create_enumerator.py"])

    def test_the_audit_catches_the_module_that_caused_b15o(self):
        """B15L is what B15O used for fee schedules; it must refuse."""
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.static_dependency_audit("b15l_counterfactual_roundtrip.py")
        self.assertIn(B15P.P_FORBIDDEN_DEPENDENCY, str(caught.exception))
        self.assertIn("b15b_backfill.py", str(caught.exception))

    def test_the_audit_catches_b15b_reaching_b15a(self):
        """The transitive hop a path-string scan misses."""
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.static_dependency_audit("b15b_backfill.py")
        message = str(caught.exception)
        self.assertIn("b15b_backfill.py", message)
        self.assertIn("b15a", message)

    def test_b15h_is_caught_too(self):
        with self.assertRaises(B15P.BackfillRefused):
            B15P.static_dependency_audit("b15h_prospective_entry.py")

    def test_a_directory_token_in_a_docstring_is_not_a_dependency(self):
        """Comments and docstrings are documentation. This module's own docstring names b15b."""
        module = ROOT / "scripts" / "b15p_native_fee_backfill.py"
        self.assertIn("b15b", module.read_text())
        self.assertEqual(B15P.static_dependency_audit()["forbidden_references"], {})

    def test_a_directory_token_in_a_code_literal_is_a_dependency(self):
        probe = ROOT / "scripts" / "b15p_probe_tmp.py"
        try:
            probe.write_text('SOURCE = "research" + "/" + "b15b" + "/x.jsonl"\n')
            audit = B15P.code_string_constants(probe)
            self.assertIn("b15b", audit)
        finally:
            probe.unlink(missing_ok=True)

    def test_the_runtime_guard_records_what_was_opened(self):
        """Including pathlib, which routes through io.open and once bypassed the guard entirely."""
        with B15P.PathGuard() as guard:
            (self.directory / "ok.txt").write_text("x")
            (self.directory / "ok.txt").read_text()
            open(self.directory / "plain.txt", "w").close()
        self.assertTrue(any("ok.txt" in path for path in guard.opened))
        self.assertTrue(any("plain.txt" in path for path in guard.opened))

    def test_the_runtime_guard_refuses_a_forbidden_pathlib_read(self):
        """The path B15O actually used: pathlib, not builtins.open."""
        with self.assertRaises(B15P.BackfillRefused) as caught:
            with B15P.PathGuard():
                (ROOT / "research" / "b15b" / "rpc_exchanges.jsonl").read_text()
        self.assertIn(B15P.P_FORBIDDEN_DEPENDENCY, str(caught.exception))
        self.assertIn("b15b", str(caught.exception))

    def test_the_runtime_guard_refuses_a_forbidden_path(self):
        """The check that would actually have caught B15O, whatever the path was spelled like."""
        for token in ("b15a", "b15b", "b15f"):
            with self.subTest(token=token):
                with self.assertRaises(B15P.BackfillRefused) as caught:
                    with B15P.PathGuard():
                        assembled = str(ROOT / "research" / token / "anything.jsonl")
                        open(assembled)
                self.assertIn(B15P.P_FORBIDDEN_DEPENDENCY, str(caught.exception))
                self.assertIn(token, str(caught.exception))

    def test_the_runtime_guard_refuses_a_forbidden_sqlite_connect(self):
        with self.assertRaises(B15P.BackfillRefused) as caught:
            with B15P.PathGuard():
                sqlite3.connect(str(ROOT / "research" / "b15b" / "backfill.sqlite"))
        self.assertIn(B15P.P_FORBIDDEN_DEPENDENCY, str(caught.exception))

    def test_the_guard_restores_the_builtins_afterwards(self):
        import builtins, io
        original_open, original_io, original_connect = builtins.open, io.open, sqlite3.connect
        with B15P.PathGuard():
            pass
        self.assertIs(builtins.open, original_open)
        self.assertIs(io.open, original_io)
        self.assertIs(sqlite3.connect, original_connect)

    def test_the_guard_restores_even_when_it_refuses(self):
        import builtins
        original_open = builtins.open
        try:
            with B15P.PathGuard():
                open(str(ROOT / "research" / "b15a" / "x"))
        except B15P.BackfillRefused:
            pass
        self.assertIs(builtins.open, original_open)


class TestDecodeEquivalence(Base):
    """The same logic as B15h, proven on the same payload rather than asserted in a comment."""

    def test_the_pinned_types_load_both_discriminators(self):
        self.assertEqual(len(self.pinned["create_discriminator"]), 8)
        self.assertEqual(len(self.pinned["trade_discriminator"]), 8)
        self.assertNotEqual(self.pinned["create_discriminator"],
                            self.pinned["trade_discriminator"])

    def test_the_types_map_is_built_as_b7d_reads_it(self):
        """The whole IDL item per name, not the inner type: B15a's comment records what else costs."""
        self.assertIn("type", self.pinned["types"]["TradeEvent"])
        self.assertIn("fields", self.pinned["types"]["TradeEvent"]["type"])

    def test_the_schedule_matches_b15hs_decode_on_the_same_transaction(self):
        signature, slot = "SigEquiv", 436_984_400
        response = transaction(signature, slot, [create_payload(), trade_payload()])
        mine = B15P.schedule_for_member(
            {"signature": signature, "t0_slot": slot, "mint": decoded_mint()},
            {"outcome": "retrieved", "payload": response, "attempts": 1}, self.pinned)
        # B15h's loader over an exchange log holding the identical response.
        log = self.directory / "exchanges.jsonl"
        log.write_text(json.dumps({"signature": signature,
                                   "response_json_or_error": response}) + "\n")
        b7d, discriminator, create_type, types = PILOT.load_pinned_create_type()
        theirs = B15H.fee_schedules_from_launch_transactions(
            {signature}, {"b7d": b7d, "discriminator": discriminator,
                          "create_type": create_type, "types": types}, log)
        self.assertEqual(theirs[signature], mine)

    def test_both_event_framings_decode(self):
        """Program data lines carry the discriminator directly; inner data carries the tag first."""
        for tagged in (False, True):
            with self.subTest(tagged=tagged):
                create, trade = B15P.decode_events(
                    [create_payload(tagged), trade_payload(tagged=tagged)], self.pinned)
                self.assertIsNotNone(create)
                self.assertIsNotNone(trade)
                self.assertEqual(B15P.schedule_from_trade(trade), SCHEDULE)

    def test_a_fee_variant_is_decoded_as_it_is_and_never_defaulted(self):
        for variant in ({"fee_bps": 95, "creator_fee_bps": 0, "cashback_fee_bps": 30,
                         "buyback_fee_bps": 5000},
                        {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0,
                         "buyback_fee_bps": 0},
                        {"fee_bps": 100, "creator_fee_bps": 1, "cashback_fee_bps": 2,
                         "buyback_fee_bps": 3}):
            with self.subTest(variant=variant):
                _create, trade = B15P.decode_events(
                    [trade_payload(variant)], self.pinned)
                self.assertEqual(B15P.schedule_from_trade(trade), variant)

    def test_an_incomplete_schedule_refuses_rather_than_defaulting(self):
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.schedule_from_trade({"fee_basis_points": 95})
        self.assertIn(B15P.P_INCOMPLETE_SCHEDULE, str(caught.exception))
        self.assertIn("no default exists", str(caught.exception))

    def test_no_default_schedule_exists_in_the_module(self):
        source = (ROOT / "scripts" / "b15p_native_fee_backfill.py").read_text()
        for forbidden in ('"fee_bps": 95', "fee_bps=95", "DEFAULT_SCHEDULE"):
            self.assertNotIn(forbidden, source)

    def test_an_unknown_instruction_yields_no_trade_event_rather_than_a_guess(self):
        unknown = bytes.fromhex("00112233445566778899")
        _create, trade = B15P.decode_events([unknown], self.pinned)
        self.assertIsNone(trade)

    def test_a_malformed_log_line_is_skipped_not_raised_on(self):
        payloads, skipped = B15P.program_data_payloads(
            ["Program data: not-base64!!", "Program log: unrelated",
             f"Program data: {base64.b64encode(trade_payload()).decode()}"])
        self.assertEqual(len(payloads), 1)
        self.assertEqual(skipped, 1)


class TestIdentity(Base):
    def test_a_matching_transaction_passes(self):
        signature, slot = "SigOk", 436_984_400
        response = transaction(signature, slot, [create_payload(), trade_payload()])
        create, _trade = B15P.decode_events([create_payload()], self.pinned)
        self.assertTrue(B15P.assert_identity(
            {"signature": signature, "t0_slot": slot, "mint": create["mint"]},
            response, create, signature))

    def test_a_signature_not_in_the_response_refuses(self):
        response = transaction("SigOther", 436_984_400, [], signatures=["SigOther"])
        create, _t = B15P.decode_events([create_payload()], self.pinned)
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.assert_identity(self.member("SigWanted", 436_984_400), response, create,
                                 "SigWanted")
        self.assertIn(B15P.P_IDENTITY_MISMATCH, str(caught.exception))

    def test_a_slot_disagreement_refuses(self):
        signature = "SigSlot"
        response = transaction(signature, 999, [])
        create, _t = B15P.decode_events([create_payload()], self.pinned)
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.assert_identity(self.member(signature, 436_984_400), response, create, signature)
        self.assertIn(B15P.P_IDENTITY_MISMATCH, str(caught.exception))

    def test_a_mint_disagreement_refuses(self):
        signature, slot = "SigMint", 436_984_400
        response = transaction(signature, slot, [])
        create, _t = B15P.decode_events([create_payload()], self.pinned)
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.assert_identity(self.member(signature, slot, mint="SomeOtherMint"),
                                 response, create, signature)
        self.assertIn(B15P.P_IDENTITY_MISMATCH, str(caught.exception))

    def test_a_missing_create_event_refuses(self):
        signature, slot = "SigNoCreate", 436_984_400
        response = transaction(signature, slot, [])
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.assert_identity(self.member(signature, slot), response, None, signature)
        self.assertIn(B15P.P_NO_CREATE_EVENT, str(caught.exception))

    def test_a_transaction_without_a_trade_event_refuses(self):
        signature, slot = "SigNoTrade", 436_984_400
        response = transaction(signature, slot, [create_payload()])
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.schedule_for_member(self.member(signature, slot),
                                     {"outcome": "retrieved", "payload": response, "attempts": 1},
                                     self.pinned)
        self.assertIn(B15P.P_NO_TRADE_EVENT, str(caught.exception))


class TestMembership(Base):
    def test_the_live_roster_matches_the_pinned_hash(self):
        members, meta = B15P.load_members()
        self.assertEqual(len(members), 5000)
        self.assertEqual(meta["member_set_sha256"], MEMBER_SET_SHA)
        self.assertEqual(meta["unconfirmed"], [])

    def test_the_roster_hash_is_stable_under_a_shuffled_read(self):
        members, _meta = B15P.load_members()
        shuffled = list(members)
        random.Random(9).shuffle(shuffled)
        canonical = sorted(shuffled, key=lambda m: (m["t0_slot"], m["signature"], m["mint"] or ""))
        self.assertEqual(B15P.member_set_hash(canonical), MEMBER_SET_SHA)

    def test_all_five_thousand_members_are_fixed(self):
        first, _ = B15P.load_members()
        second, _ = B15P.load_members()
        self.assertEqual([m["signature"] for m in first], [m["signature"] for m in second])
        self.assertEqual(len(set(m["signature"] for m in first)), 5000)

    def test_a_drifted_artifact_refuses(self):
        altered = self.directory / "replication.json"
        artifact = json.loads((ROOT / "research" / "b15o" / "replication.json").read_text())
        artifact["population"]["members"] = 4999
        altered.write_text(json.dumps(artifact))
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.load_members(self.document, altered)
        self.assertIn(B15P.P_ARTIFACT_DRIFT, str(caught.exception))

    def test_a_drifted_roster_hash_refuses(self):
        document = json.loads(json.dumps(self.document))
        document["the_frozen_member_set"]["member_set_sha256"] = "0" * 64
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.load_members(document)
        self.assertIn(B15P.P_MEMBER_SET_DRIFT, str(caught.exception))

    def test_a_size_disagreement_refuses(self):
        document = json.loads(json.dumps(self.document))
        document["the_frozen_member_set"]["size"] = 4999
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.load_members(document)
        self.assertIn(B15P.P_MEMBER_SET_DRIFT, str(caught.exception))


class TestCrossChecksThatOnlyFireOnDisagreement(Base):
    """Checks that compare two independent sources. Unreachable in normal operation, and kept.

    They exist for the case where one source has been altered, so a fixture supplies that case
    rather than leaving a branch nobody can provoke.
    """

    def test_a_first_member_disagreement_refuses(self):
        import hashlib
        artifact = json.loads((ROOT / "research" / "b15o" / "replication.json").read_text())
        artifact["population"]["first_member"] = {"signature": "NotTheFirst", "t0_slot": 1,
                                                  "mint": "NotTheMint"}
        doctored = self.directory / "doctored.json"
        doctored.write_bytes(json.dumps(artifact).encode())
        document = json.loads(json.dumps(self.document))
        # Pin the doctored file's own hash, so the artifact-drift gate passes and the cross-check
        # is the thing that has to fire.
        document["the_frozen_member_set"]["b15o_artifact_sha256"] = hashlib.sha256(
            doctored.read_bytes()).hexdigest()
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.load_members(document, doctored)
        self.assertIn(B15P.P_MEMBER_SET_DRIFT, str(caught.exception))
        self.assertIn("first", str(caught.exception))

    def test_a_last_member_disagreement_refuses(self):
        import hashlib
        artifact = json.loads((ROOT / "research" / "b15o" / "replication.json").read_text())
        artifact["population"]["last_member"] = {"signature": "NotTheLast", "t0_slot": 2,
                                                 "mint": "NotTheMint"}
        doctored = self.directory / "doctored.json"
        doctored.write_bytes(json.dumps(artifact).encode())
        document = json.loads(json.dumps(self.document))
        document["the_frozen_member_set"]["b15o_artifact_sha256"] = hashlib.sha256(
            doctored.read_bytes()).hexdigest()
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.load_members(document, doctored)
        self.assertIn("last", str(caught.exception))

    def test_a_manifest_entry_whose_function_is_called_refuses(self):
        """A declared module is only safe while this study never calls what reads."""
        document = json.loads(json.dumps(self.document))
        document["forbidden_dependencies"]["static_audit"]["declared_manifest"] = [
            {"module": "b7d_create_enumerator.py", "forbidden_references": [],
             "role": "probe", "why_no_data_flows": "probe",
             "forbidden_functions_never_called": ["read_struct"]}]
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.static_dependency_audit(document=document)
        self.assertIn("which the", str(caught.exception))
        self.assertIn("read_struct", str(caught.exception))

    def test_an_idl_without_a_discriminator_refuses_rather_than_guessing(self):
        for missing in ("CreateEvent", "TradeEvent"):
            with self.subTest(missing=missing):
                idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
                idl["events"] = [entry for entry in idl["events"] if entry["name"] != missing]
                doctored = self.directory / f"idl_{missing}.json"
                doctored.write_text(json.dumps(idl))
                with self.assertRaises(B15P.BackfillRefused) as caught:
                    B15P.load_pinned_types(doctored)
                self.assertIn(missing, str(caught.exception))
                self.assertIn("refusing to guess", str(caught.exception))

    def test_an_unreadable_idl_refuses(self):
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.load_pinned_types(self.directory / "absent.json")
        self.assertIn("cannot read the pinned IDL", str(caught.exception))


class TestRetrieval(Base):
    def _raw(self):
        return B15P.RawLog(self.directory / "raw.jsonl")

    def test_the_request_asks_at_confirmed_for_the_members_signature(self):
        seen = {}

        def opener(request, timeout=None):
            seen.update(json.loads(request.data))

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps(transaction("SigA", 1, [])).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        raw = self._raw()
        B15P.fetch_member(self.member("SigA"), "https://example.invalid/?api-key=x", self.document,
                          raw, opener, lambda _s: None)
        raw.close()
        self.assertEqual(seen["method"], "getTransaction")
        self.assertEqual(seen["params"][0], "SigA")
        self.assertEqual(seen["params"][1]["commitment"], "confirmed")

    def test_the_exchange_is_preserved_before_the_answer_is_judged(self):
        raw = self._raw()
        response = transaction("SigB", 436_984_400, [create_payload(), trade_payload()])
        B15P.fetch_member(self.member("SigB"), "https://example.invalid", self.document, raw,
                          opener_for([response]), lambda _s: None)
        raw.close()
        lines = (self.directory / "raw.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["outcome"], "retrieved")
        self.assertEqual(entry["signature"], "SigB")

    def test_only_the_endpoint_scheme_and_host_are_recorded(self):
        raw = self._raw()
        B15P.fetch_member(self.member("SigC"), "https://node.example.invalid/?api-key=SECRET",
                          self.document, raw, opener_for([transaction("SigC", 1, [])]),
                          lambda _s: None)
        raw.close()
        text = (self.directory / "raw.jsonl").read_text()
        self.assertIn("https://node.example.invalid", text)
        self.assertNotIn("SECRET", text)

    def test_a_credential_in_a_record_refuses(self):
        raw = self._raw()
        with self.assertRaises(B15P.BackfillRefused) as caught:
            raw.append({"endpoint": "https://x/?api-key=abc"})
        raw.close()
        self.assertIn(B15P.P_SECRET_IN_OUTPUT, str(caught.exception))

    def test_the_endpoint_receipt_drops_the_query(self):
        self.assertEqual(B15P.endpoint_receipt("https://host.example/?api-key=abc"),
                         "https://host.example")

    def test_a_missing_env_credential_refuses_rather_than_taking_an_argument(self):
        import os
        previous = os.environ.pop(B15P.RPC_ENV_VAR, None)
        try:
            with self.assertRaises(B15P.BackfillRefused) as caught:
                B15P.rpc_url()
            self.assertIn("never", str(caught.exception))
        finally:
            if previous is not None:
                os.environ[B15P.RPC_ENV_VAR] = previous

    def test_a_null_result_is_not_found(self):
        raw = self._raw()
        fetched = B15P.fetch_member(self.member("SigD"), "https://example.invalid", self.document,
                                    raw, opener_for([{"jsonrpc": "2.0", "id": 1, "result": None}]),
                                    lambda _s: None)
        raw.close()
        self.assertEqual(fetched["outcome"], "not_found")
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.schedule_for_member(self.member("SigD"), fetched, self.pinned)
        self.assertIn(B15P.P_NOT_FOUND, str(caught.exception))

    def test_a_transport_error_is_retried_to_the_frozen_bound_then_refused(self):
        calls = []

        def opener(request, timeout=None):
            calls.append(1)
            raise OSError("endpoint down")

        raw = self._raw()
        fetched = B15P.fetch_member(self.member("SigE"), "https://example.invalid", self.document,
                                    raw, opener, lambda _s: None)
        raw.close()
        self.assertEqual(len(calls),
                         self.document["retrieval"]["max_attempts_per_signature"])
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.schedule_for_member(self.member("SigE"), fetched, self.pinned)
        self.assertIn(B15P.P_RPC_FAILED, str(caught.exception))


class TestRunAndResume(Base):
    def _members(self, count=3):
        return [{"signature": f"Sig{index:04d}", "t0_slot": 436_984_400 + index,
                 "mint": decoded_mint()} for index in range(count)]

    def _run(self, members, responses, **kwargs):
        document = self.small_document(members)
        original = B15P.load_members
        B15P.load_members = lambda *a, **k: (members, {
            "member_set_sha256": B15P.member_set_hash(members), "unconfirmed":
                kwargs.pop("unconfirmed", [])})
        try:
            return B15P.run(work_dir=self.directory, url="https://example.invalid",
                            document=document, opener=opener_for(responses),
                            sleeper=lambda _s: None, **kwargs)
        finally:
            B15P.load_members = original

    def test_every_member_gets_a_terminal_record(self):
        members = self._members()
        responses = [transaction(m["signature"], m["t0_slot"],
                                 [create_payload(), trade_payload()]) for m in members]
        counts, report = self._run(members, responses)
        self.assertEqual(counts[B15P.STATE_RETRIEVED], 3)
        self.assertEqual(report["terminal"], 3)
        self.assertTrue(report["complete"])
        self.assertEqual(report["remaining"], 0)

    def test_a_resume_does_not_refetch_a_terminal_member(self):
        members = self._members()
        responses = [transaction(m["signature"], m["t0_slot"],
                                 [create_payload(), trade_payload()]) for m in members]
        self._run(members, responses)
        counts, _report = self._run(members, responses)
        self.assertEqual(counts["pending_at_start"], 0)
        self.assertEqual(counts["requests"], 0)

    def test_a_crash_midway_resumes_from_the_database(self):
        members = self._members(4)
        responses = [transaction(m["signature"], m["t0_slot"],
                                 [create_payload(), trade_payload()]) for m in members]
        first, _ = self._run(members, responses, limit=2)
        self.assertEqual(first[B15P.STATE_RETRIEVED], 2)
        second, report = self._run(members, responses)
        self.assertEqual(second["pending_at_start"], 2)
        self.assertTrue(report["complete"])

    def test_an_unconfirmed_member_is_refused_and_never_fetched(self):
        members = self._members(2)
        calls = []

        def opener(request, timeout=None):
            calls.append(1)

            class Handle:
                status = 200

                def read(self_inner):
                    return json.dumps(transaction(members[1]["signature"],
                                                  members[1]["t0_slot"],
                                                  [create_payload(), trade_payload()])).encode()

                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *_):
                    return False
            return Handle()

        document = self.small_document(members)
        original = B15P.load_members
        B15P.load_members = lambda *a, **k: (members, {
            "member_set_sha256": B15P.member_set_hash(members),
            "unconfirmed": [members[0]["signature"]]})
        try:
            counts, report = B15P.run(work_dir=self.directory, url="https://example.invalid",
                                      document=document, opener=opener, sleeper=lambda _s: None)
        finally:
            B15P.load_members = original
        self.assertEqual(counts[B15P.P_NOT_CONFIRMED], 1)
        self.assertEqual(len(calls), 1)          # only the confirmed member was fetched
        self.assertEqual(report["terminal"], 2)

    def test_a_disagreeing_second_schedule_for_one_member_refuses(self):
        members = self._members(1)
        connection = B15P.open_database(self.directory / "fee_schedules.sqlite")
        try:
            B15P.record(connection, members[0], B15P.STATE_RETRIEVED, None, SCHEDULE)
            other = dict(SCHEDULE, fee_bps=100)
            with self.assertRaises(B15P.BackfillRefused) as caught:
                B15P.record(connection, members[0], B15P.STATE_RETRIEVED, None, other)
            self.assertIn(B15P.P_SCHEDULE_CONFLICT, str(caught.exception))
        finally:
            connection.close()

    def test_a_repeat_of_an_identical_schedule_is_ignored_not_duplicated(self):
        members = self._members(1)
        connection = B15P.open_database(self.directory / "fee_schedules.sqlite")
        try:
            self.assertTrue(B15P.record(connection, members[0], B15P.STATE_RETRIEVED, None,
                                        SCHEDULE))
            self.assertFalse(B15P.record(connection, members[0], B15P.STATE_RETRIEVED, None,
                                         SCHEDULE))
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM fee_schedule").fetchone()[0], 1)
        finally:
            connection.close()

    def test_a_second_writer_is_refused(self):
        with B15P.SingleWriter(self.directory / "lock"):
            with self.assertRaises(B15P.BackfillRefused) as caught:
                with B15P.SingleWriter(self.directory / "lock"):
                    pass
            self.assertIn(B15P.P_LOCK_HELD, str(caught.exception))
        with B15P.SingleWriter(self.directory / "lock"):
            pass

    def test_the_census_publishes_no_strategy_quantity(self):
        members = self._members()
        responses = [transaction(m["signature"], m["t0_slot"],
                                 [create_payload(), trade_payload()]) for m in members]
        _counts, report = self._run(members, responses)
        text = json.dumps(report).lower()
        for banned in ("capacity", "counterfactual", "net_lamports", "self_impact", "priced",
                       "return", "profit"):
            self.assertNotIn(banned, text)
        self.assertEqual(report["label"], "NATIVE_FEE_BACKFILL")
        self.assertEqual(report["performance_status"], "not_evaluated")

    def test_the_distinct_schedules_are_reported_with_their_frequencies(self):
        members = self._members(2)
        variants = [SCHEDULE, dict(SCHEDULE, creator_fee_bps=0, cashback_fee_bps=30)]
        responses = [transaction(m["signature"], m["t0_slot"],
                                 [create_payload(), trade_payload(v)])
                     for m, v in zip(members, variants)]
        _counts, report = self._run(members, responses)
        self.assertEqual(len(report["distinct_schedules"]), 2)
        self.assertEqual(sum(row["members"] for row in report["distinct_schedules"]), 2)


class TestCompletenessAndReplay(Base):
    def _members(self, count=2):
        return [{"signature": f"Sig{index:04d}", "t0_slot": 436_984_400 + index,
                 "mint": decoded_mint()} for index in range(count)]

    def _complete(self, members):
        document = self.small_document(members)
        responses = [transaction(m["signature"], m["t0_slot"],
                                 [create_payload(), trade_payload()]) for m in members]
        original = B15P.load_members
        B15P.load_members = lambda *a, **k: (members, {
            "member_set_sha256": B15P.member_set_hash(members), "unconfirmed": []})
        try:
            B15P.run(work_dir=self.directory, url="https://example.invalid", document=document,
                     opener=opener_for(responses), sleeper=lambda _s: None)
            return B15P.assert_complete_and_replayable(self.directory, document)
        finally:
            B15P.load_members = original

    def test_a_complete_backfill_replays_from_raw_alone(self):
        members = self._members()
        report = self._complete(members)
        self.assertTrue(report["complete"])
        self.assertEqual(report["replayed_schedules"], len(members))

    def test_an_incomplete_backfill_refuses_completeness(self):
        members = self._members(3)
        document = self.small_document(members)
        responses = [transaction(m["signature"], m["t0_slot"],
                                 [create_payload(), trade_payload()]) for m in members]
        original = B15P.load_members
        B15P.load_members = lambda *a, **k: (members, {
            "member_set_sha256": B15P.member_set_hash(members), "unconfirmed": []})
        try:
            B15P.run(work_dir=self.directory, url="https://example.invalid", document=document,
                     opener=opener_for(responses), sleeper=lambda _s: None, limit=1)
            with self.assertRaises(B15P.BackfillRefused) as caught:
                B15P.assert_complete_and_replayable(self.directory, document)
            self.assertIn("not complete", str(caught.exception))
        finally:
            B15P.load_members = original

    def test_a_replay_that_diverges_refuses(self):
        members = self._members(1)
        self._complete(members)
        # Rewrite the stored schedule so it no longer matches the preserved response.
        connection = B15P.open_database(self.directory / "fee_schedules.sqlite")
        connection.execute("UPDATE fee_schedule SET fee_bps=1 WHERE state=?",
                           (B15P.STATE_RETRIEVED,))
        connection.commit()
        connection.close()
        document = self.small_document(members)
        original = B15P.load_members
        B15P.load_members = lambda *a, **k: (members, {
            "member_set_sha256": B15P.member_set_hash(members), "unconfirmed": []})
        try:
            with self.assertRaises(B15P.BackfillRefused) as caught:
                B15P.assert_complete_and_replayable(self.directory, document)
            self.assertIn(B15P.P_REPLAY_DIVERGED, str(caught.exception))
        finally:
            B15P.load_members = original

    def test_replaying_a_missing_raw_log_refuses(self):
        with self.assertRaises(B15P.BackfillRefused) as caught:
            B15P.replay_schedules(self.directory / "absent.jsonl", self.pinned)
        self.assertIn("no raw exchange log", str(caught.exception))

    def test_status_on_an_unstarted_backfill_says_so(self):
        report = B15P.status(self.directory / "unstarted")
        self.assertEqual(report["state"], "not_started")


if __name__ == "__main__":
    unittest.main(verbosity=2)
