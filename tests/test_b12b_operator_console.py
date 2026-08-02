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

    def test_an_approval_while_the_kill_switch_is_engaged_is_refused(self):
        snapshot = demo()
        self.assertGreater(snapshot["overview"]["opportunities_approved"], 0)
        snapshot["evidence"] = dict(snapshot["evidence"], kill_switch_engaged=True)
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
        limits = {limit["name"]: limit for limit in demo()["portfolio"]["limits"]}
        self.assertIsNone(limits["max_order_lamports"]["used"])
        self.assertIsNone(limits["max_order_lamports"]["utilisation"])


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
            " formatRatio(null), formatBoolean(null), truncateIdentity(null), formatInteger(0)]));")
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

    def test_identity_truncation_keeps_both_ends(self):
        output = self.run_js(
            "console.log(JSON.stringify([truncateIdentity('short'),"
            " truncateIdentity('MintSynth1111111111111111111111111111111111')]));")
        values = json.loads(output)
        self.assertEqual(values[0], "short")
        self.assertTrue(values[1].startswith("MintSynt"))
        self.assertTrue(values[1].endswith("111111"))


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
