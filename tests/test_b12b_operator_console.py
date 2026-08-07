"""B12b — the operator snapshot adapter, the read-only console, and the preview server.

A console is where a research system's honesty gets spent. Everything upstream can be exact,
censored properly and labelled SIMULATED, and a page that prints 0 for a figure it does not have,
or renders a mint through innerHTML, or quietly grows a button that submits something, undoes it
in one screenshot.

So the tests here are about what the page CANNOT do — reach the network, execute anything, show an
executable claim, turn unknown into zero — as much as about what it shows.

The pure JavaScript helpers are exercised through `node` when it is available and skipped when it is
not, so no dependency is added either way. Everything else is asserted structurally against the
file itself.
"""
import http.client
import importlib.util
import copy
import ast
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "ui" / "operator_console.html"
DEMO_JSON = ROOT / "ui" / "demo_snapshot.json"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B12B = _load("b12b_operator_snapshot", "b12b_operator_snapshot.py")
PREVIEW = _load("b12b_preview_server", "b12b_preview_server.py")
B12A = B12B.B12A
B11B = B12B.B11B
B10B = B12B.B10B

HTML = CONSOLE.read_text()
SCRIPT = re.search(r'<script>\n(.*?)\n</script>', HTML, re.S).group(1)


def strip_comments(text, script=False):
    """The file's own prose names the things it refuses to do, which is the point of the prose.

    A scanner that reads comments therefore reports the page as unsafe precisely because the page
    documents its own safety. So the scanners run over CODE ONLY, and this strips the commentary
    that would otherwise make the strictest file look like the worst one.
    """
    without_html = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    if not script:
        return without_html
    without_block = re.sub(r"/\*.*?\*/", " ", without_html, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", without_block, flags=re.M)


HTML_CODE = strip_comments(HTML)
SCRIPT_CODE = strip_comments(SCRIPT, script=True)


def demo():
    return B12B.build_demo_snapshot()


class SnapshotContractTests(unittest.TestCase):

    def test_the_demo_snapshot_passes_every_gate(self):
        self.assertTrue(B12B.assert_snapshot(demo()))

    def test_the_snapshot_is_deterministic_and_self_hashing(self):
        first, second = demo(), demo()
        self.assertEqual(B10B.canonical_json(first), B10B.canonical_json(second))
        self.assertEqual(first["snapshot_sha256"], B12B.snapshot_hash(first))

    def test_a_changed_field_moves_the_hash(self):
        snapshot = demo()
        moved = dict(snapshot)
        moved["overview"] = dict(snapshot["overview"], open_positions=99)
        self.assertNotEqual(B12B.snapshot_hash(snapshot), B12B.snapshot_hash(moved))

    def test_an_undeclared_field_is_refused(self):
        with self.assertRaisesRegex(B12B.SnapshotRefused, "undeclared fields"):
            B12B.assert_snapshot(dict(demo(), extra_panel={"looks": "useful"}))

    def test_a_missing_section_is_refused(self):
        for field in B12B.SNAPSHOT_FIELDS:
            with self.subTest(field=field):
                trimmed = {k: v for k, v in demo().items() if k != field}
                with self.assertRaisesRegex(B12B.SnapshotRefused, "does not carry"):
                    B12B.assert_snapshot(trimmed)

    def test_no_float_reaches_a_snapshot(self):
        self.assertTrue(B12B.assert_no_float(demo()))
        snapshot = demo()
        snapshot["portfolio"]["risk"]["current_drawdown_ratio"] = 0.06
        with self.assertRaisesRegex(B12B.SnapshotRefused, "a float reached"):
            B12B.assert_snapshot(snapshot)

    def test_a_deeply_nested_float_is_still_caught(self):
        snapshot = demo()
        snapshot["opportunities"][0]["quote_lamports"] = 1.0
        with self.assertRaisesRegex(B12B.SnapshotRefused, "a float reached"):
            B12B.assert_snapshot(snapshot)

    def test_credential_shaped_strings_are_refused(self):
        for value in ("my api-key is 123", "PRIVATE_KEY=xyz", "Bearer abc", "the secret sauce"):
            with self.subTest(value=value):
                snapshot = demo()
                snapshot["provenance"] = dict(snapshot["provenance"], leak=value)
                with self.assertRaises(B12B.SnapshotRefused):
                    B12B.assert_snapshot(snapshot)

    def test_a_secret_nested_inside_a_list_is_still_found(self):
        """Most strings in a snapshot live in lists — warnings, reasons, positions — so a scanner
        that only walks mappings would miss the places text actually accumulates."""
        snapshot = demo()
        snapshot["windows"] = dict(snapshot["windows"],
                                   warnings=list(snapshot["windows"]["warnings"])
                                   + ["rotate the api-key before launch"])
        with self.assertRaises(B12B.SnapshotRefused):
            B12B.assert_snapshot(snapshot)

    def test_a_url_with_embedded_credentials_is_refused(self):
        snapshot = demo()
        snapshot["provenance"] = dict(snapshot["provenance"],
                                      endpoint="https://user:pass@rpc.example.org/")
        with self.assertRaisesRegex(B12B.SnapshotRefused, "embedded credentials"):
            B12B.assert_snapshot(snapshot)

    def test_a_plain_endpoint_reference_is_still_allowed(self):
        snapshot = demo()
        snapshot["provenance"] = dict(snapshot["provenance"], endpoint="https://rpc.example.org/")
        self.assertTrue(B12B.assert_snapshot(snapshot))


class ExecutableClaimTests(unittest.TestCase):
    """Nothing in this project has ever been executable, and a banner is where that gets lost."""

    def test_the_allowed_levels_do_not_include_executable(self):
        self.assertEqual(B12B.ALLOWED_STATUS_LEVELS, ("RESEARCH", "SIMULATED"))
        self.assertNotIn(B12B.FORBIDDEN_STATUS_LEVEL, B12B.ALLOWED_STATUS_LEVELS)

    def test_an_executable_banner_is_refused(self):
        snapshot = demo()
        snapshot["status_banner"] = dict(snapshot["status_banner"], level="EXECUTABLE")
        with self.assertRaisesRegex(B12B.SnapshotRefused, "not one of"):
            B12B.assert_snapshot(snapshot)

    def test_an_executable_flag_is_refused_even_under_a_safe_level(self):
        snapshot = demo()
        snapshot["status_banner"] = dict(snapshot["status_banner"], executable=True)
        with self.assertRaisesRegex(B12B.SnapshotRefused, "must be exactly False"):
            B12B.assert_snapshot(snapshot)

    def test_an_unknown_outcome_status_is_refused(self):
        snapshot = demo()
        snapshot["simulated_positions"][0]["outcome_status"] = "profit_realised"
        with self.assertRaisesRegex(B12B.SnapshotRefused, "known simulated outcome"):
            B12B.assert_snapshot(snapshot)

    def test_the_demo_banner_is_simulated_and_says_so(self):
        banner = demo()["status_banner"]
        self.assertEqual(banner["level"], "SIMULATED")
        self.assertFalse(banner["executable"])
        self.assertIn("SYNTHETIC", banner["detail"])


class ConsistencyTests(unittest.TestCase):
    """The contradictions a console must never be asked to render."""

    def test_a_snapshot_that_calls_itself_fresh_while_stale_is_refused(self):
        snapshot = demo()
        snapshot["evidence"] = dict(snapshot["evidence"], age_slots=10_000)
        with self.assertRaisesRegex(B12B.SnapshotRefused, "calls itself fresh"):
            B12B.assert_snapshot(snapshot)

    def test_either_clock_alone_makes_a_fresh_claim_false(self):
        """Slots stop advancing during an outage while the wall clock keeps running, and a stalled
        provider can replay an old slot under a fresh timestamp. A gate that reads one clock is a
        gate that reads neither."""
        for field, maximum in (("age_slots", "max_age_slots"),
                               ("age_seconds", "max_age_seconds")):
            with self.subTest(clock=field):
                snapshot = demo()
                snapshot["evidence"] = dict(snapshot["evidence"],
                                            **{field: snapshot["evidence"][maximum] + 1})
                with self.assertRaisesRegex(B12B.SnapshotRefused, "calls itself fresh"):
                    B12B.assert_snapshot(snapshot)

    def test_an_approval_while_the_kill_switch_is_engaged_is_refused(self):
        snapshot = demo()
        self.assertGreater(snapshot["overview"]["opportunities_approved"], 0)
        snapshot["evidence"] = dict(snapshot["evidence"], kill_switch_engaged=True)
        with self.assertRaisesRegex(B12B.SnapshotRefused, "halted or stale"):
            B12B.assert_snapshot(snapshot)

    def test_an_approval_while_the_emergency_stop_is_set_is_refused(self):
        snapshot = demo()
        self.assertGreater(snapshot["overview"]["opportunities_approved"], 0)
        snapshot["evidence"] = dict(snapshot["evidence"], emergency_state=True)
        with self.assertRaisesRegex(B12B.SnapshotRefused, "halted or stale"):
            B12B.assert_snapshot(snapshot)

    def test_an_approval_while_stale_is_refused(self):
        snapshot = demo()
        snapshot["evidence"] = dict(snapshot["evidence"], is_stale=True,
                                    age_slots=snapshot["evidence"]["max_age_slots"] + 1)
        with self.assertRaisesRegex(B12B.SnapshotRefused, "halted or stale"):
            B12B.assert_snapshot(snapshot)

    def test_an_approved_opportunity_carrying_reasons_is_refused(self):
        snapshot = demo()
        approved = next(o for o in snapshot["opportunities"] if o["decision"] == "approved")
        approved["reasons"] = [{"code": "R09_MAYHEM_MODE", "label": "x"}]
        with self.assertRaisesRegex(B12B.SnapshotRefused, "approved opportunity carries"):
            B12B.assert_snapshot(snapshot)

    def test_a_rejected_opportunity_with_no_reason_is_refused(self):
        snapshot = demo()
        rejected = next(o for o in snapshot["opportunities"] if o["decision"] == "rejected")
        rejected["reasons"] = []
        with self.assertRaisesRegex(B12B.SnapshotRefused, "no reason"):
            B12B.assert_snapshot(snapshot)

    def test_an_overview_count_that_disagrees_with_the_list_is_refused(self):
        snapshot = demo()
        snapshot["overview"] = dict(snapshot["overview"], opportunities_approved=99)
        with self.assertRaisesRegex(B12B.SnapshotRefused, "approval count disagrees"):
            B12B.assert_snapshot(snapshot)

    def test_an_overview_total_that_disagrees_with_the_list_is_refused(self):
        """A headline count nobody can tie back to the rows underneath is the number an operator
        reads and the list is the number that is true."""
        snapshot = demo()
        snapshot["overview"] = dict(snapshot["overview"], opportunities_total=99)
        with self.assertRaisesRegex(B12B.SnapshotRefused, "total disagrees"):
            B12B.assert_snapshot(snapshot)

    def test_results_shown_unlocked_with_requirements_unmet_is_refused(self):
        snapshot = demo()
        snapshot["strategy"] = dict(snapshot["strategy"], results_locked=False)
        with self.assertRaisesRegex(B12B.SnapshotRefused, "unlocked while unlock"):
            B12B.assert_snapshot(snapshot)

    def test_a_named_model_without_a_frozen_artifact_hash_is_refused(self):
        snapshot = demo()
        snapshot["strategy"] = dict(snapshot["strategy"], model_family="gbm")
        with self.assertRaisesRegex(B12B.SnapshotRefused, "model artifact hash"):
            B12B.assert_snapshot(snapshot)


class LabelMappingTests(unittest.TestCase):

    def test_every_risk_reason_code_has_a_plain_language_label(self):
        self.assertEqual(set(B12B.REASON_LABELS), set(B12A.REASON_PRECEDENCE))
        for code, label in B12B.REASON_LABELS.items():
            with self.subTest(code=code):
                self.assertTrue(label and label[0].isupper() and label.endswith("."))
                self.assertNotIn("_", label, "a label that still contains the code is not a label")

    def test_a_reason_travels_with_its_raw_code(self):
        rejected = next(o for o in demo()["opportunities"] if o["decision"] == "rejected")
        for reason in rejected["reasons"]:
            self.assertIn(reason["code"], B12A.REASON_PRECEDENCE)
            self.assertEqual(reason["label"], B12B.REASON_LABELS[reason["code"]])

    def test_an_unrecognised_code_is_labelled_visibly_rather_than_dropped(self):
        self.assertEqual(B12B.label_for("R99_FROM_THE_FUTURE", B12B.REASON_LABELS),
                         "Unrecognised code (R99_FROM_THE_FUTURE)")
        self.assertIsNone(B12B.label_for(None, B12B.REASON_LABELS))

    def test_outcome_and_liquidity_codes_cover_what_the_pipeline_emits(self):
        self.assertEqual(set(B12B.OUTCOME_LABELS), set(B12A.METRICS.B10C.OUTCOME_STATUSES))
        for state in (B10B.L0_FULL, B10B.L2_SIZE_CONSTRAINED, B10B.L1M_NO_EXECUTABLE_SIZE,
                      B10B.L3_STRUCTURAL_UNAVAILABLE):
            self.assertIn(state, B12B.LIQUIDITY_LABELS)


class UnknownIsNotZeroTests(unittest.TestCase):

    def test_an_absent_realisable_value_stays_null_and_is_not_zeroed(self):
        positions = demo()["portfolio"]["positions"]
        unknown = [p for p in positions if p["realizable_net_lamports"] is None]
        self.assertTrue(unknown, "the demo must exercise the unknown case")
        for entry in unknown:
            self.assertIsNotNone(entry["deployed_lamports"])

    def test_a_censored_position_reports_no_value_rather_than_zero(self):
        censored = [p for p in demo()["simulated_positions"]
                    if p["outcome_status"] != "marked_at_horizon"]
        self.assertTrue(censored)
        for entry in censored:
            self.assertIsNone(entry["net_return"])
            self.assertIsNone(entry["max_drawdown_ratio"])
            self.assertTrue(entry["censoring_reason"])

    def test_a_limit_with_no_meaningful_usage_is_null_not_zero(self):
        """A per-order cap bounds the NEXT order, not a running total. Publishing zero used here
        would invite reading it as headroom."""
        limits = {limit["name"]: limit for limit in demo()["portfolio"]["limits"]}
        self.assertIsNone(limits["max_single_order"]["used_lamports"])
        self.assertIsNone(limits["max_single_order"]["used_sol_display"])
        self.assertIsNone(limits["max_single_order"]["utilisation"])
        self.assertIsNone(limits["max_single_order"]["utilisation_percent_display"])


class DisplayFormattingTests(unittest.TestCase):
    """Display strings exist so the operator is not the one doing the division in their head.

    They are derived by integer arithmetic, versioned, hashed with everything else, and always sit
    beside the raw value that remains authoritative.
    """

    def test_sol_amounts_are_exact_and_never_rounded(self):
        cases = {
            0: "0.000000000 SOL",
            1: "0.000000001 SOL",
            -1: "-0.000000001 SOL",
            999_999_999: "0.999999999 SOL",
            1_000_000_000: "1.000000000 SOL",
            1_000_000_001: "1.000000001 SOL",
            103_394_280: "0.103394280 SOL",
            -12_500_000: "-0.012500000 SOL",
            10 ** 18: "1,000,000,000.000000000 SOL",
        }
        for lamports, expected in cases.items():
            with self.subTest(lamports=lamports):
                self.assertEqual(B12B.format_sol(lamports), expected)

    def test_one_lamport_always_changes_the_sol_string(self):
        for base in (0, 1, 999_999_999, 1_000_000_000, 10 ** 18, -1, -1_000_000_000):
            with self.subTest(base=base):
                self.assertNotEqual(B12B.format_sol(base), B12B.format_sol(base + 1))

    def test_an_unknown_amount_has_no_sol_string_rather_than_a_zero_one(self):
        self.assertIsNone(B12B.format_sol(None))
        self.assertIsNone(B12B.format_percent(None))

    def test_a_non_integer_amount_is_refused_rather_than_coerced(self):
        for bad in (1.0, "100", True):
            with self.subTest(bad=bad):
                with self.assertRaises(B12B.SnapshotRefused):
                    B12B.format_sol(bad)

    def test_percentages_are_truncated_toward_zero_and_marked_approximate(self):
        cases = {
            (1, 4): "\u2248 25.00%",
            (0, 1): "\u2248 0.00%",
            (1, 3): "\u2248 33.33%",
            (-1, 3): "\u2248 -33.33%",
            (2, 3): "\u2248 66.66%",
            (-2, 3): "\u2248 -66.66%",
            (-7, 100): "\u2248 -7.00%",
            (1, 1_000_000): "\u2248 0.00%",
            (10 ** 18, 3): "\u2248 33,333,333,333,333,333,333.33%",
        }
        for pair, expected in cases.items():
            with self.subTest(pair=pair):
                self.assertEqual(B12B.format_percent(list(pair)), expected)

    def test_truncation_never_overstates_the_magnitude(self):
        """The stated bound: |displayed| <= |exact| < |displayed| + 0.01. Checked by integer
        cross-multiplication so the test itself uses no float either."""
        for numerator, denominator in ((1, 3), (2, 3), (-2, 3), (99_999, 100_000), (1, 7),
                                       (123_456_789, 1_000_000_007)):
            with self.subTest(pair=(numerator, denominator)):
                shown = B12B.format_percent([numerator, denominator])
                digits = shown.replace("\u2248 ", "").replace("%", "").replace(",", "")
                whole, fraction = digits.lstrip("-").split(".")
                hundredths = int(whole) * 100 + int(fraction)
                self.assertLessEqual(hundredths * abs(denominator),
                                     abs(numerator) * 10_000)
                self.assertGreater((hundredths + 1) * abs(denominator),
                                   abs(numerator) * 10_000)

    def test_a_zero_denominator_has_no_percent(self):
        with self.assertRaises(B12B.SnapshotRefused):
            B12B.format_percent([1, 0])

    def test_the_formatting_rule_is_versioned_and_travels_with_the_snapshot(self):
        rules = demo()["display_format"]
        self.assertEqual(rules["version"], B12B.DISPLAY_FORMAT_VERSION)
        self.assertIn("exact", rules["sol"])
        self.assertIn("NOT exact", rules["percent"])
        self.assertIn("the raw value is correct", rules["raw_is_authoritative"])
        self.assertIn("authoritative", rules["percent"])

    def test_display_strings_are_inside_the_hash(self):
        snapshot = demo()
        tampered = json.loads(B10B.canonical_json(snapshot))
        tampered["portfolio"]["risk"]["realised_pnl_today_sol_display"] = "0.000000000 SOL"
        self.assertNotEqual(B12B.snapshot_hash(snapshot), B12B.snapshot_hash(tampered))

    def test_every_display_string_re_derives_from_the_value_beside_it(self):
        self.assertTrue(B12B.assert_display_consistent(demo()))

    def test_a_display_string_that_disagrees_with_its_raw_value_is_refused(self):
        snapshot = demo()
        snapshot["portfolio"]["positions"][0]["deployed_sol_display"] = "9.999999999 SOL"
        with self.assertRaisesRegex(B12B.SnapshotRefused, "authoritative and they disagree"):
            B12B.assert_snapshot(snapshot)

    def test_a_percent_that_disagrees_with_its_exact_pair_is_refused(self):
        snapshot = demo()
        snapshot["portfolio"]["risk"]["current_drawdown_percent_display"] = "\u2248 99.00%"
        with self.assertRaisesRegex(B12B.SnapshotRefused, "disagrees with the exact pair"):
            B12B.assert_snapshot(snapshot)

    def test_a_raw_value_with_no_display_string_beside_it_is_refused(self):
        snapshot = demo()
        del snapshot["portfolio"]["positions"][0]["deployed_sol_display"]
        with self.assertRaisesRegex(B12B.SnapshotRefused, "has no deployed_sol_display"):
            B12B.assert_snapshot(snapshot)

    def test_a_display_string_with_no_raw_value_behind_it_is_refused(self):
        snapshot = demo()
        snapshot["overview"]["invented_sol_display"] = "1.000000000 SOL"
        with self.assertRaisesRegex(B12B.SnapshotRefused, "to be derived from"):
            B12B.assert_snapshot(snapshot)

    def test_the_page_shows_the_raw_value_beside_every_display_string(self):
        self.assertIn('raw.className = "raw"', SCRIPT_CODE)
        self.assertIn(".raw::before { content: \"raw \"", HTML)


class EmbeddedDemoTests(unittest.TestCase):

    def test_the_console_ships_exactly_the_snapshot_the_adapter_builds(self):
        """One source of truth. A hand-maintained copy would agree until somebody changed one."""
        self.assertEqual(B12B.embedded_demo(CONSOLE), demo())

    def test_the_standalone_demo_file_matches_too(self):
        self.assertEqual(json.loads(DEMO_JSON.read_text()), demo())

    def test_embedding_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = pathlib.Path(directory) / "console.html"
            shutil.copy(CONSOLE, copy)
            first = B12B.embed_demo(copy)
            body = copy.read_text()
            second = B12B.embed_demo(copy)
            self.assertEqual(first, second)
            self.assertEqual(body, copy.read_text())

    def test_building_a_snapshot_validates_it_before_hashing_it(self):
        """Otherwise the hash certifies a record nothing checked. Every other validation test calls
        the checker directly, so only this one proves the builder calls it too."""
        components = B12B.demo_components()
        components["strategy"] = dict(components["strategy"], model_family="gbm")
        with self.assertRaisesRegex(B12B.SnapshotRefused, "model artifact hash"):
            B12B.build_snapshot(**components)

    def test_embedding_refuses_a_payload_that_could_close_the_script_element(self):
        """A closing tag inside the JSON would end the element early and turn data into markup —
        the one way this page could execute something it was handed."""
        with tempfile.TemporaryDirectory() as directory:
            copy = pathlib.Path(directory) / "console.html"
            shutil.copy(CONSOLE, copy)
            hostile = demo()
            hostile["windows"] = dict(hostile["windows"],
                                      warnings=["</script><script>alert(1)</script>"])
            with self.assertRaises(B12B.SnapshotRefused):
                B12B.embed_demo(copy, hostile)
            self.assertEqual(B12B.embedded_demo(copy), demo(), "the page must be left untouched")

    def test_the_embedded_payload_cannot_close_the_script_element(self):
        raw = HTML.split('<script type="application/json" id="demo-snapshot">')[1]
        payload = raw.split("</script>")[0]
        self.assertNotIn("</", payload)
        self.assertIsInstance(json.loads(payload), dict)


class ConsoleCannotReachTheNetworkTests(unittest.TestCase):
    """The property that makes the page's safety readable rather than trusted."""

    def test_no_network_primitive_appears_anywhere_in_the_file(self):
        lowered = HTML_CODE.lower()
        for forbidden in ("fetch(", "xmlhttprequest", "websocket", "eventsource",
                          "navigator.sendbeacon", "importscripts", "new worker",
                          "serviceworker", "document.domain"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_nothing_is_loaded_from_outside_the_file(self):
        for pattern in (r'src\s*=\s*["\']http', r'href\s*=\s*["\']http',
                        r'@import', r'url\(\s*["\']?http'):
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, HTML, re.I))
        self.assertNotIn("<script src", HTML.lower())
        self.assertNotIn("<link rel=\"stylesheet\"", HTML.lower())

    def test_there_is_no_form_and_nothing_that_could_submit(self):
        self.assertNotIn("<form", HTML.lower())
        self.assertNotIn("type=\"submit\"", HTML.lower())
        for button in re.findall(r"<button[^>]*>", HTML, re.I):
            self.assertIn('type="button"', button)

    def test_no_control_offers_to_execute_approve_sign_or_send(self):
        """A read-only console must not contain a control that even LOOKS actionable."""
        interactive = re.findall(r"<(?:button|a|input)[^>]*>.*?(?:</(?:button|a)>)?", HTML, re.I)
        for element in interactive:
            lowered = element.lower()
            for verb in ("submit", "approve", "sign", "execute", "buy now", "sell",
                         "connect wallet", "send", "cancel order", "place order"):
                with self.subTest(verb=verb, element=lowered[:60]):
                    self.assertNotIn(verb, lowered)

    def test_no_wallet_or_key_surface_exists(self):
        lowered = HTML_CODE.lower()
        for forbidden in ("window.solana", "phantom", "walletconnect", "keypair", "privatekey",
                          "private_key", "signtransaction", "sendtransaction", "secret"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_no_analytics_or_telemetry(self):
        lowered = HTML_CODE.lower()
        for forbidden in ("gtag", "analytics", "datalayer", "posthog", "sentry", "mixpanel"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)


class ConsoleRendersSafelyTests(unittest.TestCase):

    def test_data_never_reaches_the_page_as_markup(self):
        """A mint, a creator or a censoring reason is data from a file, and data is not markup."""
        lowered = SCRIPT_CODE.lower()
        self.assertNotIn("innerhtml", lowered)
        self.assertNotIn("outerhtml", lowered)
        self.assertNotIn("insertadjacenthtml", lowered)
        self.assertNotIn("document.write", lowered)
        self.assertNotIn("eval(", lowered)
        self.assertIn("textContent", SCRIPT_CODE)

    def test_the_script_does_not_build_html_from_strings(self):
        self.assertIsNone(
            re.search(r"[\"'`]\s*<\s*(div|span|td|tr|table|a|script)\b", SCRIPT_CODE, re.I))

    def test_the_page_computes_nothing_on_snapshot_data(self):
        """Ratios arrive exact and are displayed as pairs; a browser-side division would be a
        second implementation of a research metric."""
        self.assertIn("formatRatio", SCRIPT_CODE)
        for forbidden in ("toFixed", "Math.round", "parseFloat", "* 100", "/ 100"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, SCRIPT_CODE)


class AccessibilityAndResponsivenessTests(unittest.TestCase):

    def test_semantic_landmarks_exist(self):
        for marker in ("<header role=\"banner\"", "<nav class=\"sections\" aria-label=",
                       "<main id=\"main\"", "<footer role=\"contentinfo\""):
            with self.subTest(marker=marker):
                self.assertIn(marker, HTML)

    def test_every_section_is_labelled_by_its_heading(self):
        sections = re.findall(r'<section id="([^"]+)" aria-labelledby="([^"]+)"', HTML)
        self.assertGreaterEqual(len(sections), 7)
        for _, labelled_by in sections:
            with self.subTest(labelled_by=labelled_by):
                self.assertIn(f'id="{labelled_by}"', HTML)

    def test_every_table_has_a_caption_and_column_scopes(self):
        tables = re.findall(r"<table[^>]*>(.*?)</table>", HTML, re.S)
        self.assertGreaterEqual(len(tables), 6)
        for table in tables:
            self.assertIn("<caption>", table)
            self.assertIn('scope="col"', table)

    def test_row_headers_are_marked_up_as_headers(self):
        self.assertIn('th.setAttribute("scope", "row")', SCRIPT)

    def test_there_is_a_skip_link_and_a_visible_focus_style(self):
        self.assertIn('class="skip" href="#main"', HTML)
        self.assertIn(":focus-visible", HTML)
        self.assertIn(".skip:focus", HTML)

    def test_reduced_motion_is_respected(self):
        self.assertIn("prefers-reduced-motion: reduce", HTML)

    def test_the_layout_is_responsive_and_stacks_on_a_narrow_screen(self):
        self.assertIn('name="viewport"', HTML)
        self.assertIn("max-width: 720px", HTML)
        self.assertIn("table.stack tr { display: block", HTML)
        self.assertIn('content: attr(data-label)', HTML)

    def test_a_stacked_label_sits_above_its_value_rather_than_beside_it(self):
        """A multi-line value — a wrapped mint, a two-line reason — otherwise leaves its label
        floating against the middle of a block. Found by rendering at 390px, not by reading."""
        self.assertIn("content: attr(data-label); display: block;", HTML)

    def test_identifiers_have_a_width_floor_as_well_as_a_ceiling(self):
        """Without a floor a neighbouring column squeezes a 44-character mint into four ragged
        lines. Also found by rendering rather than by reading."""
        self.assertIn("code.ident { display: inline-block; min-width: 20ch; max-width: 26ch;",
                      HTML)

    def test_values_break_at_natural_points_rather_than_mid_token(self):
        self.assertNotIn("word-break: break-all", HTML)
        self.assertIn("overflow-wrap: anywhere", HTML)

    def test_stacked_cells_carry_the_label_they_will_display(self):
        """Without `data-label` on every cell the mobile layout shows values with no headings."""
        self.assertIn('td.setAttribute("data-label", label)', SCRIPT)
        self.assertIn('th.setAttribute("data-label", label)', SCRIPT)

    def test_both_colour_schemes_are_defined(self):
        self.assertIn("prefers-color-scheme: light", HTML)
        self.assertIn("--unknown:", HTML)

    def test_the_live_region_announces_the_status_banner(self):
        self.assertIn('id="banner" role="status" aria-live="polite"', HTML)


NODE = shutil.which("node")


@unittest.skipIf(NODE is None, "node is not available; the pure helpers are skipped, not faked")
class ConsoleBehaviourTests(unittest.TestCase):
    """The pure helpers, actually executed. A source-text assertion is weaker than running it."""

    def run_js(self, body):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "check.js"
            path.write_text(SCRIPT + "\n" + body)
            result = subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                self.fail(f"node failed: {result.stderr.strip()}")
            return result.stdout.strip()

    def test_unknown_is_never_rendered_as_zero(self):
        output = self.run_js(
            "console.log(JSON.stringify([formatInteger(null), formatInteger(undefined),"
            " formatRatio(null), formatBoolean(null), identityText(null), formatInteger(0)]));")
        values = json.loads(output)
        self.assertEqual(values[:5], ["unknown"] * 5)
        self.assertEqual(values[5], "0", "a real zero must still print as zero")

    def test_integers_are_grouped_and_negatives_survive(self):
        output = self.run_js(
            "console.log(JSON.stringify([formatInteger(1), formatInteger(1000),"
            " formatInteger(103394280), formatInteger(-12500000)]));")
        self.assertEqual(json.loads(output), ["1", "1,000", "103,394,280", "-12,500,000"])

    def test_ratios_are_shown_as_exact_pairs_and_never_divided(self):
        output = self.run_js("console.log(JSON.stringify([formatRatio([1,4]),"
                             " formatRatio([-7,100]), formatRatio([1,20])]));")
        self.assertEqual(json.loads(output), ["1 / 4", "-7 / 100", "1 / 20"])

    def test_an_unrecognised_code_is_shown_not_dropped(self):
        output = self.run_js(
            "console.log(JSON.stringify([describeCode('R99_NEW', undefined),"
            " describeCode('R09_MAYHEM_MODE', 'Mayhem mode.'), describeCode(null, null),"
            " localLabel('brand_new_kind'), localLabel('approved')]));")
        values = json.loads(output)
        self.assertEqual(values[0], "Unrecognised code (R99_NEW)")
        self.assertEqual(values[1], "Mayhem mode.")
        self.assertEqual(values[2], "unknown")
        self.assertEqual(values[3], "brand_new_kind (unrecognised)")
        self.assertEqual(values[4], "Approved by the risk governor")

    def test_the_page_refuses_to_render_an_executable_claim(self):
        output = self.run_js(
            "var bad = {status_banner:{executable:true, level:'SIMULATED'}, overview:{},"
            " evidence:{}};"
            "var worse = {status_banner:{executable:false, level:'EXECUTABLE'}, overview:{},"
            " evidence:{}};"
            "console.log(JSON.stringify([snapshotProblem(bad), snapshotProblem(worse),"
            " snapshotProblem(null)]));")
        problems = json.loads(output)
        self.assertIn("claims to be executable", problems[0])
        self.assertIn("unknown status level", problems[1])
        self.assertIn("not a snapshot", problems[2])

    def test_the_real_demo_snapshot_passes_the_client_side_gate(self):
        payload = json.dumps(demo())
        output = self.run_js(
            f"var snap = {payload};\nconsole.log(JSON.stringify(snapshotProblem(snap)));")
        self.assertEqual(json.loads(output), None)

    def test_identifiers_are_shown_in_full_and_never_ellipsised(self):
        """A truncated mint cannot be copied, pasted into an explorer, or compared against
        anything. The only reason to shorten one is to make a table look tidier than the data is."""
        mint = "MintSynth1111111111111111111111111111111111"
        output = self.run_js(
            "console.log(JSON.stringify([identityText('short'), identityText('" + mint + "'),"
            " identityText(null)]));")
        values = json.loads(output)
        self.assertEqual(values[0], "short")
        self.assertEqual(values[1], mint)
        self.assertEqual(values[2], "unknown")
        self.assertNotIn("\u2026", SCRIPT_CODE, "no ellipsis may survive in the renderer")


DOM_STUB = """
var __ids = {};
function __el(tag) {
  var node = {
    tagName: tag, children: [], attributes: {}, _text: "",
    style: {}, classList: { _set: [],
      add: function () { for (var i = 0; i < arguments.length; i++) { this._set.push(arguments[i]); } } },
    appendChild: function (child) { this.children.push(child); return child; },
    removeChild: function (child) { this.children.splice(this.children.indexOf(child), 1); },
    setAttribute: function (k, v) { this.attributes[k] = v; },
    addEventListener: function () {},
    querySelector: function () {
      if (!this._tbody) { this._tbody = __el("tbody"); }
      return this._tbody;
    }
  };
  Object.defineProperty(node, "textContent", {
    get: function () { return this._text; },
    set: function (value) {
      if (typeof value !== "string") { throw new Error("textContent must be a string"); }
      this._text = value;
    }
  });
  Object.defineProperty(node, "firstChild", {
    get: function () { return this.children.length ? this.children[0] : null; }
  });
  Object.defineProperty(node, "className", {
    get: function () { return this.classList._set.join(" "); },
    set: function (value) { this.classList._set = String(value).split(" "); }
  });
  return node;
}
var document = {
  getElementById: function (id) {
    if (!__ids[id]) { __ids[id] = __el("div"); }
    return __ids[id];
  },
  createElement: __el,
  createTextNode: function (value) { var n = __el("#text"); n.textContent = value; return n; }
};
function __collect(node, out) {
  out.push(node);
  node.children.forEach(function (child) { __collect(child, out); });
  return out;
}
"""


@unittest.skipIf(NODE is None, "node is not available; the render check is skipped, not faked")
class ConsoleRenderTests(unittest.TestCase):
    """The console is actually run against a minimal DOM. Source scanning cannot catch a typo in
    an element id, and a console that throws on load shows an operator nothing at all."""

    def render(self, extra=""):
        payload = json.dumps(B12B.embedded_demo(CONSOLE))
        program = (DOM_STUB
                   + SCRIPT.replace("if (typeof document !== \"undefined\") { boot(); }", "")
                   + "\ndocument.getElementById('demo-snapshot').textContent = "
                   + json.dumps(payload) + ";\n"
                   + "boot();\n" + extra)
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "render.js"
            path.write_text(program)
            result = subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                self.fail(f"the console threw while rendering: {result.stderr.strip()}")
            return result.stdout.strip()

    def test_the_console_renders_the_demo_without_throwing(self):
        self.assertEqual(self.render("console.log('rendered');"), "rendered")

    def test_every_element_the_script_addresses_exists_in_the_page(self):
        """A mistyped id silently yields null and the section stays blank."""
        for identifier in sorted(set(re.findall(r'\$\("([a-z0-9-]+)"\)', SCRIPT))):
            with self.subTest(identifier=identifier):
                self.assertIn(f'id="{identifier}"', HTML)

    def test_the_banner_shows_the_status_and_says_not_executable(self):
        output = self.render("console.log(__ids['banner-level'].textContent);")
        self.assertIn("SIMULATED", output)
        self.assertIn("NOT EXECUTABLE", output)

    def test_every_table_body_receives_rows(self):
        output = self.render(
            "var names = ['pipeline-table','opportunities-table','positions-table',"
            "'limits-table','positions-held-table','provenance-table'];"
            "console.log(JSON.stringify(names.map(function (n) {"
            "  return __ids[n]._tbody ? __ids[n]._tbody.children.length : 0; })));")
        counts = json.loads(output)
        for index, count in enumerate(counts):
            self.assertGreater(count, 0, f"table {index} rendered no rows")

    def test_an_unknown_value_renders_as_the_word_unknown_and_never_as_zero(self):
        output = self.render(
            "var nodes = __collect(__ids['positions-held-table']._tbody, []);"
            "var unknowns = nodes.filter(function (n) {"
            "  return n.classList._set.indexOf('unknown') >= 0; });"
            "console.log(JSON.stringify(unknowns.map(function (n) { return n.textContent; })));")
        values = json.loads(output)
        self.assertIn("unknown", values)
        self.assertNotIn("0", values)

    def test_the_kill_switch_pills_are_rendered_for_every_halt_flag(self):
        output = self.render(
            "console.log(JSON.stringify(__ids['halts'].children.map(function (p) {"
            "  return [p.className, p.children.length]; })));")
        pills = json.loads(output)
        self.assertEqual(len(pills), 4)
        for className, _ in pills:
            self.assertTrue(className.startswith("pill "))

    def reload_with(self, snapshot, tail):
        """Re-seed the embedded block and boot again — the same path a user takes, and it needs no
        test-only hook inside the production script."""
        payload = json.dumps(json.dumps(snapshot))
        return self.render(
            "document.getElementById('demo-snapshot').textContent = " + payload + ";"
            "boot();" + tail)

    def test_a_stale_and_halted_snapshot_shows_the_halt_state(self):
        halted = B12B.embedded_demo(CONSOLE)
        halted["evidence"]["kill_switch_engaged"] = True
        halted["evidence"]["is_stale"] = True
        output = self.reload_with(
            halted,
            "console.log(JSON.stringify(__ids['halts'].children.map(function (p) {"
            "  return p.className; })));")
        classes = json.loads(output)
        self.assertEqual(sum(1 for c in classes if "on" in c.split()), 3,
                         "kill switch, stale evidence and locked results must all read as on")

    def test_every_display_string_is_rendered_with_its_raw_value_beneath_it(self):
        """The display string is a convenience; the raw value is the evidence. Both on screen."""
        output = self.render(
            "var nodes = __collect(__ids['positions-held-table']._tbody, []);"
            "console.log(JSON.stringify(nodes.filter(function (n) {"
            "  return n.classList._set.indexOf('raw') >= 0; })"
            "  .map(function (n) { return n.textContent; })));")
        raws = json.loads(output)
        self.assertIn("103,394,280 lamports", raws)
        self.assertTrue(any("96,100,000" in value for value in raws))

    def test_sol_and_percent_strings_reach_the_page(self):
        output = self.render(
            "var nodes = __collect(__ids['limits-table']._tbody, []);"
            "console.log(JSON.stringify(nodes.map(function (n) { return n.textContent; })));")
        texts = " ".join(json.loads(output))
        self.assertIn("1.000000000 SOL", texts)
        self.assertIn("\u2248 30.67%", texts)
        self.assertIn("306,788,560 lamports", texts)

    def test_identifiers_reach_the_page_in_full(self):
        mint = "MintSynth1111111111111111111111111111111111"
        output = self.render(
            "var nodes = __collect(__ids['positions-held-table']._tbody, []);"
            "console.log(JSON.stringify(nodes.map(function (n) { return n.textContent; })));")
        self.assertIn(mint, json.loads(output))

    def test_a_snapshot_claiming_to_be_executable_is_refused_at_render_time(self):
        bad = B12B.embedded_demo(CONSOLE)
        bad["status_banner"]["executable"] = True
        output = self.reload_with(
            bad,
            "console.log(__ids['banner-level'].textContent + '|' + "
            "__ids['banner-headline'].textContent);")
        self.assertIn("CANNOT RENDER", output)
        self.assertIn("claims to be executable", output)

    def test_a_rejected_opportunity_shows_its_plain_language_reasons(self):
        output = self.render(
            "var rows = __ids['opportunities-table']._tbody.children;"
            "var texts = rows.map(function (r) {"
            "  return __collect(r, []).map(function (n) { return n.textContent; }).join(' '); });"
            "console.log(JSON.stringify(texts));")
        rows = json.loads(output)
        joined = " ".join(rows)
        self.assertIn("Too many positions would be held on this one creator.", joined)
        self.assertIn("R19_CREATOR_POSITION_LIMIT_EXCEEDED", joined)
        self.assertIn("Approved by the risk governor", joined)


class PreviewServerTests(unittest.TestCase):
    """A preview, not an API — and it must be unable to become one by accident."""

    def setUp(self):
        self.server = PREVIEW.build_server(port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[0], self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_it_binds_loopback_only(self):
        self.assertEqual(PREVIEW.LOOPBACK, "127.0.0.1")
        self.assertEqual(self.host, "127.0.0.1")

    def test_the_console_is_served(self):
        status, body, _ = self.request("GET", "/operator_console.html")
        self.assertEqual(status, 200)
        self.assertIn(b"Operator console", body)

    def test_every_mutating_method_is_refused(self):
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                status, _, _ = self.request(method, "/operator_console.html")
                self.assertEqual(status, 405)

    def test_there_is_no_route_outside_the_ui_directory(self):
        for path in ("/../DECISIONS.md", "/..%2fDECISIONS.md", "/../../etc/passwd",
                     "/../scripts/b12a_risk_governor.py"):
            with self.subTest(path=path):
                status, body, _ = self.request("GET", path)
                self.assertNotEqual(status, 200)
                self.assertNotIn(b"DECISIONS", body)
                self.assertNotIn(b"risk governor", body)

    def test_security_headers_are_sent(self):
        _, _, headers = self.request("GET", "/operator_console.html")
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("form-action 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")

    def test_the_module_declares_no_write_or_api_endpoint(self):
        source = (ROOT / "scripts" / "b12b_preview_server.py").read_text()
        self.assertNotIn("def do_POST(self):\n        self.send_response(200", source)
        for forbidden in ("sqlite3", "open(", "write_text", "subprocess", "os.system"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_it_uses_only_the_standard_library(self):
        source = (ROOT / "scripts" / "b12b_preview_server.py").read_text()
        imports = re.findall(r"^import (\w+)", source, re.M)
        self.assertEqual(set(imports),
                         {"argparse", "functools", "http", "pathlib", "sys"})


class ScopeTests(unittest.TestCase):
    """This handoff must not read B11a, compute its composition, or unlock anything."""

    def test_the_demo_is_synthetic_and_says_so(self):
        snapshot = demo()
        self.assertIn("SYNTHETIC", snapshot["provenance"]["note"])
        self.assertEqual(snapshot["provenance"]["synthetic"], "true")
        for opportunity in snapshot["opportunities"]:
            self.assertTrue(opportunity["mint"].startswith("MintSynth"))

    def test_nothing_in_this_area_reads_the_fresh_window(self):
        """Naming the frozen window boundaries is fine — they are already public in DECISIONS and
        PLAN, and an operator needs to see them. READING the window is what is forbidden, so the
        check is for artifact and database access, not for the string "b11a"."""
        for name in ("b12b_operator_snapshot.py", "b12b_preview_server.py"):
            source = (ROOT / "scripts" / name).read_text().lower()
            with self.subTest(name=name):
                for forbidden in ("sqlite", "research/", "b9d_transaction_bodies",
                                  "b10b_observed_paths", "b10c_labels", "getslot", "urllib"):
                    self.assertNotIn(forbidden, source)

    def test_b11a_results_remain_locked_and_b11b_unchanged(self):
        self.assertEqual(B11B.MODEL_FAMILY, "none")
        report = B11B.evaluate_unlock_evidence({
            "b11b_prereg_file_sha256": B11B.PREREGISTRATION_FILE_SHA256,
            "b11b_prereg_canonical_sha256": B11B.PREREGISTRATION_CANONICAL_SHA256,
            "recorded_in_decisions": True, "model_family": "none",
            "collection_complete": False, "gates_passed": False,
            "b11a_prereg_file_sha256": B11B.B11A_PREREGISTRATION_FILE_SHA256,
            "decisions_unlock_entry": "none"})
        self.assertFalse(report["unlocked"])
        self.assertIn("U3", report["unmet"])

    def test_the_console_states_it_is_read_only_and_holds_no_wallet(self):
        self.assertIn("read-only", HTML.lower())
        self.assertIn("cannot sign, submit, cancel or modify anything", HTML)
        self.assertIn("NOT EXECUTABLE", HTML)


if __name__ == "__main__":
    unittest.main()


class EmergencyOwnerWiringTests(unittest.TestCase):
    """G6's last step: the console's kill switch now comes from something that owns it.

    Before this, `build_snapshot` rendered whatever the caller put in `health`, and nothing produced
    it -- b12a REFUSES a health snapshot omitting the field, so every caller had to invent an answer.
    The switch was mandatory and unwritten.
    """

    def setUp(self):
        self.components = copy.deepcopy(B12B.demo_components())

    def verdict(self, engaged, reason="E09_EXPLICITLY_ENGAGED"):
        return {"kill_switch_engaged": engaged, "emergency_state": engaged,
                "reason_code": reason, "generation": 3, "detail": None}

    def build(self, emergency=None, decisions=None, **health_overrides):
        components = copy.deepcopy(self.components)
        components["health"].update(health_overrides)
        if decisions is not None:
            components["risk_decisions"] = decisions
        return B12B.build_snapshot(**components, emergency=emergency)

    def build_halted(self, emergency, **health_overrides):
        """Engaging means no approvals may be shown, so the fixture carries none.

        b12b already refuses "1 opportunities are approved while the system is halted"; that guard
        is correct and it is a real consequence of this wiring. The verdict and the decisions in a
        snapshot must come from the SAME MOMENT -- an owner that says engaged cannot be rendered
        beside approvals made while it said clear, because the snapshot is a coherent whole rather
        than a collection of independently true panels.
        """
        return self.build(emergency=emergency, decisions=[], **health_overrides)

    def test_without_a_verdict_the_snapshot_is_unchanged(self):
        """The wiring is additive: existing callers keep working and the block is null."""
        snapshot = self.build()
        self.assertIsNone(snapshot["emergency"])
        self.assertFalse(snapshot["overview"]["kill_switch_engaged"])

    def test_the_owners_verdict_is_what_the_snapshot_renders(self):
        snapshot = self.build_halted(self.verdict(True), kill_switch_engaged=False,
                                     emergency_state=False)
        self.assertTrue(snapshot["overview"]["kill_switch_engaged"])
        self.assertTrue(snapshot["evidence"]["kill_switch_engaged"])
        self.assertTrue(snapshot["overview"]["emergency_state"])
        self.assertEqual(snapshot["emergency"]["owner"], "scripts/b20a_emergency_state.py")

    def test_a_disagreement_renders_engaged_rather_than_refusing(self):
        """B19a's rule, and the asymmetry is the reason: refusing would blind the operator
        entirely, and showing clear when it is engaged costs whatever the halt was preventing."""
        snapshot = self.build_halted(self.verdict(True), kill_switch_engaged=False,
                                     emergency_state=False)
        self.assertTrue(snapshot["emergency"]["sources_disagree"])
        self.assertTrue(snapshot["overview"]["kill_switch_engaged"])
        self.assertIn("ENGAGED", snapshot["emergency"]["disagreement_note"])

    def test_a_supplied_engagement_is_never_downgraded_by_an_owner_saying_clear(self):
        """The other direction of the same rule. Either source engaging is enough."""
        snapshot = self.build_halted(self.verdict(False, "E00_CLEARED"),
                                     kill_switch_engaged=True, emergency_state=True)
        self.assertTrue(snapshot["emergency"]["sources_disagree"])
        # BOTH fields. Asserting only the kill switch left a mutant alive that downgraded
        # emergency_state alone -- the two are separate flags and each needs its own claim.
        self.assertTrue(snapshot["overview"]["kill_switch_engaged"])
        self.assertTrue(snapshot["overview"]["emergency_state"])
        self.assertTrue(snapshot["evidence"]["emergency_state"])

    def test_agreement_reports_no_disagreement_and_no_note(self):
        """A guard that always fires is a stop, not a check."""
        snapshot = self.build(emergency=self.verdict(False, "E00_CLEARED"),
                              kill_switch_engaged=False, emergency_state=False)
        self.assertFalse(snapshot["emergency"]["sources_disagree"])
        self.assertIsNone(snapshot["emergency"]["disagreement_note"])
        self.assertFalse(snapshot["overview"]["kill_switch_engaged"])

    def test_both_sources_are_shown_not_just_the_resolved_value(self):
        """An operator who sees `engaged` without being told the sources disagree will go looking
        for a halt nobody ordered."""
        snapshot = self.build_halted(self.verdict(True), kill_switch_engaged=False,
                                     emergency_state=False)
        self.assertEqual(snapshot["emergency"]["health_said"],
                         {"kill_switch_engaged": False, "emergency_state": False})
        self.assertTrue(snapshot["emergency"]["kill_switch_engaged"])

    def test_an_engaged_verdict_beside_approvals_is_refused(self):
        """The coherence guard, which this wiring makes reachable in a new way. Not a bug: a
        snapshot is a whole, and approvals made while the switch said clear cannot be shown
        beside an owner that now says engaged."""
        with self.assertRaises(B12B.SnapshotRefused) as refusal:
            self.build(emergency=self.verdict(True), kill_switch_engaged=False,
                       emergency_state=False)
        self.assertIn("approved while the system is halted", str(refusal.exception))

    def test_the_block_says_the_console_may_not_mutate_it(self):
        snapshot = self.build_halted(self.verdict(True))
        self.assertFalse(snapshot["emergency"]["console_may_mutate_this"])

    def test_build_snapshot_does_no_file_reading(self):
        """It assembles components each validated by their owner. Reading state it does not own
        would make it a second reader, and two readers of one file disagree eventually."""
        tree = ast.parse((ROOT / "scripts" / "b12b_operator_snapshot.py").read_text())
        builder = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "build_snapshot")
        calls = {ast.unparse(n.func) for n in ast.walk(builder) if isinstance(n, ast.Call)}
        self.assertNotIn("B20A.read_verdict", calls)
        self.assertNotIn("read_emergency", calls)
        self.assertIn("emergency_block", calls)

    def test_the_reader_exists_and_delegates_to_the_owner(self):
        """The literal gap G6 named: b12b could not ask anything what the switch said."""
        tree = ast.parse((ROOT / "scripts" / "b12b_operator_snapshot.py").read_text())
        reader = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == "read_emergency")
        calls = {ast.unparse(n.func) for n in ast.walk(reader) if isinstance(n, ast.Call)}
        self.assertIn("B20A.read_verdict", calls)

    def test_this_module_imports_no_write_operation_from_the_owner(self):
        """A snapshot builder that could engage or clear would be a control surface."""
        source = (ROOT / "scripts" / "b12b_operator_snapshot.py").read_text()
        for operation in ("B20A.engage", "B20A.clear", "B20A.heartbeat", "B20A._write"):
            with self.subTest(operation=operation):
                self.assertNotIn(operation, source)

    def test_the_console_and_preview_server_still_never_mention_the_owner(self):
        """The codex seat's guard, re-asserted from my side because my change is what could break
        it. The demo carries `emergency: null`, so no owner name reaches the page."""
        for path in (ROOT / "ui" / "operator_console.html",
                     ROOT / "scripts" / "b12b_preview_server.py",
                     ROOT / "ui" / "demo_snapshot.json"):
            with self.subTest(path=path.name):
                self.assertNotIn("b20a", path.read_text())
