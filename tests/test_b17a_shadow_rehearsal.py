"""Guards for B17a's shadow rehearsal.

Every test here attacks a property of the COMPOSITION, because that is what B17a exists to assert.
The individual stages have their own suites; what these cover is the seam between them and the two
runtime proofs (no execution surface, no socket) that make the rehearsal a rehearsal.

RUNNER
------
`unittest.TestCase`, which 68 of this repository's 75 test files use, so these are discoverable by
BOTH `python -m pytest` and `python -m unittest`. The first draft was bare pytest functions using
`tmp_path`, `monkeypatch` and `pytest.raises`; `python -m unittest` reported zero tests for it, which
means anyone running the standard-library runner would have read this module as unguarded. A test
file invisible to a runner in use is close to no test file at all.
"""
import ast
import copy
import importlib.util
import json
import pathlib
import socket
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B17A = _load("b17a_shadow_rehearsal_under_test", "b17a_shadow_rehearsal.py")
B12A = B17A.B12A


class PlantingTestCase(unittest.TestCase):
    """A scratch scripts directory, so the surface scan can be attacked without touching `scripts/`."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.tmp = pathlib.Path(self._directory.name)

    def plant(self, name, source):
        path = self.tmp / name
        path.write_text(source)
        return path


# ----------------------------------------------------------------------------------------------
# The execution-surface scan: it must fire on capability and stay silent on prose
# ----------------------------------------------------------------------------------------------

class ExecutionSurfaceScanTests(PlantingTestCase):

    def test_fires_on_a_signing_capability(self):
        """The whole point. A module that can sign must be refused."""
        self.plant("entry.py", 'method = "signTransaction"\n')
        with self.assertRaises(B17A.RehearsalRefused) as refusal:
            B17A.assert_no_execution_surface("entry.py", self.tmp)
        self.assertIn("signTransaction", str(refusal.exception))

    def test_fires_on_an_attribute_not_only_a_string(self):
        """A capability reached as `client.sendTransaction` is a capability, string constant or not."""
        self.plant("entry.py", "def go(client):\n    return client.sendTransaction(1)\n")
        with self.assertRaises(B17A.RehearsalRefused):
            B17A.assert_no_execution_surface("entry.py", self.tmp)

    def test_fires_on_a_bare_name(self):
        self.plant("entry.py", "def go():\n    return Keypair\n")
        with self.assertRaises(B17A.RehearsalRefused):
            B17A.assert_no_execution_surface("entry.py", self.tmp)

    def test_is_silent_on_a_docstring_mention(self):
        """Prose is not capability. A module that DOCUMENTS that it never signs must still pass."""
        self.plant("entry.py",
                   '"""This module never calls signTransaction and holds no private_key."""\n'
                   "value = 1\n")
        result = B17A.assert_no_execution_surface("entry.py", self.tmp)
        self.assertEqual(result["execution_surface_found"], {})

    def test_is_silent_on_a_comment_mention(self):
        self.plant("entry.py", "# no sendTransaction anywhere here\nvalue = 1\n")
        result = B17A.assert_no_execution_surface("entry.py", self.tmp)
        self.assertEqual(result["execution_surface_found"], {})

    def test_is_silent_on_a_declared_denylist(self):
        """A module declaring what it refuses must not trip on its own vocabulary.

        Not hypothetical: the scan's first run fired on b12b's own FORBIDDEN_SUBSTRINGS.
        """
        self.plant("entry.py",
                   'FORBIDDEN_SUBSTRINGS = ("signTransaction", "private_key")\n'
                   "def check(text):\n"
                   "    return any(bad in text for bad in FORBIDDEN_SUBSTRINGS)\n")
        result = B17A.assert_no_execution_surface("entry.py", self.tmp)
        self.assertEqual(result["execution_surface_found"], {})

    def test_denylist_exemption_does_not_extend_to_lowercase_names(self):
        """`banned = (...)` is a variable, not a declaration. Only ALL-CAPS constants are exempt."""
        self.plant("entry.py", 'banned = ("signTransaction",)\n')
        with self.assertRaises(B17A.RehearsalRefused):
            B17A.assert_no_execution_surface("entry.py", self.tmp)

    def test_denylist_exemption_does_not_extend_to_a_call(self):
        """An ALL-CAPS name assigned from a CALL is not a literal denylist and gets no exemption."""
        self.plant("entry.py", 'FORBIDDEN_TOKENS = build("signTransaction")\n')
        with self.assertRaises(B17A.RehearsalRefused):
            B17A.assert_no_execution_surface("entry.py", self.tmp)

    def test_denylist_exemption_does_not_cover_an_unrelated_capitalised_name(self):
        """SURFACE/FORBIDDEN/... are the markers. `SETTINGS = (...)` is not a denylist."""
        self.plant("entry.py", 'SETTINGS = ("signTransaction",)\n')
        with self.assertRaises(B17A.RehearsalRefused):
            B17A.assert_no_execution_surface("entry.py", self.tmp)

    def test_a_class_name_reached_by_import_is_caught(self):
        """Class names are matched as identifiers and IMPORTS, so the split leaves no hole."""
        self.plant("entry.py", "from solana.transaction import Transaction\n")
        with self.assertRaises(B17A.RehearsalRefused) as refusal:
            B17A.assert_no_execution_surface("entry.py", self.tmp)
        self.assertIn("Transaction", str(refusal.exception))

    def test_a_class_name_inside_a_longer_rpc_parameter_is_not_a_capability(self):
        """`maxSupportedTransactionVersion` is a getBlock parameter for READING blocks.

        Substring-matching class names against camelCase flagged the recorder for this, which is the
        opposite of a signing capability. Wire names still match as substrings; class names do not.
        """
        self.plant("entry.py",
                   'params = {"maxSupportedTransactionVersion": 0, "transactionDetails": "full"}\n')
        result = B17A.assert_no_execution_surface("entry.py", self.tmp)
        self.assertEqual(result["execution_surface_found"], {})

    def test_a_wire_method_name_is_still_caught_inside_a_longer_string(self):
        """The other half of the split: an RPC method travels AS a string and must still be found."""
        self.plant("entry.py", 'body = {"method": "sendTransaction", "params": []}\n')
        with self.assertRaises(B17A.RehearsalRefused):
            B17A.assert_no_execution_surface("entry.py", self.tmp)

    def test_reaches_through_the_closure(self):
        """A capability one hop away is still reachable, and must be found."""
        self.plant("entry.py", 'DEP = _load("dep", "dep.py")\n')
        self.plant("dep.py", 'method = "sendTransaction"\n')
        with self.assertRaises(B17A.RehearsalRefused) as refusal:
            B17A.assert_no_execution_surface("entry.py", self.tmp)
        self.assertIn("dep.py", str(refusal.exception))

    def test_module_closure_is_transitive_and_terminates_on_a_cycle(self):
        self.plant("a.py", '_load("b", "b.py")\n')
        self.plant("b.py", '_load("c", "c.py")\n')
        self.plant("c.py", '_load("a", "a.py")\n')
        self.assertEqual(B17A.module_closure("a.py", self.tmp), ["a.py", "b.py", "c.py"])

    def test_code_string_constants_excludes_docstrings_and_keeps_code(self):
        path = self.plant("m.py",
                          '"""module doc"""\n'
                          "def f():\n"
                          '    """function doc"""\n'
                          '    return "a code string"\n')
        values = B17A.code_string_constants(path)
        self.assertIn("a code string", values)
        self.assertNotIn("module doc", values)
        self.assertNotIn("function doc", values)


class RealClosureTests(unittest.TestCase):

    def test_the_real_closure_is_clean_and_is_not_trivially_small(self):
        """The claim that matters, on the code that actually runs.

        The size assertion is the guard against a scan that passes because it looked at nothing.
        """
        result = B17A.assert_no_execution_surface()
        self.assertEqual(result["execution_surface_found"], {})
        self.assertGreaterEqual(len(result["closure"]), 5)
        self.assertIn("b12a_risk_governor.py", result["closure"])
        self.assertIn("b10a_simulator_kernel.py", result["closure"])

    def test_the_scan_states_its_scope_and_does_not_claim_the_repository(self):
        """A closure scan is not a repository scan, and the artifact must not read as one.

        This guard exists because the B17c gap map DID read as one and was wrong twice over.
        """
        result = B17A.assert_no_execution_surface()
        self.assertIn("scope", result)
        self.assertIn("closure", result["scope"])
        self.assertIn("not a repository-wide", result["scope"])


# ----------------------------------------------------------------------------------------------
# The network proof
# ----------------------------------------------------------------------------------------------

class NoNetworkTests(unittest.TestCase):

    def test_refuses_a_socket_and_restores_afterwards(self):
        original = socket.socket
        with B17A.NoNetwork():
            with self.assertRaises(B17A.NetworkAttempted):
                socket.socket()
        self.assertIs(socket.socket, original)

    def test_restores_even_when_the_body_raises(self):
        """A guard that leaks its patch on the error path breaks every later test in the process."""
        original = socket.socket
        with self.assertRaises(ValueError):
            with B17A.NoNetwork():
                raise ValueError("something else went wrong")
        self.assertIs(socket.socket, original)

    def test_network_attempted_is_a_refusal_not_a_generic_error(self):
        """It must be caught by anything catching RehearsalRefused, so it cannot pass as a fault."""
        self.assertTrue(issubclass(B17A.NetworkAttempted, B17A.RehearsalRefused))


# ----------------------------------------------------------------------------------------------
# Reconciliation: fail-closed on every disagreement
# ----------------------------------------------------------------------------------------------

def _components():
    return copy.deepcopy(B17A.B12B.demo_components())


def _good_simulation(quote_lamports=100_000_000):
    return {"lamports_out_of_wallet_at_entry": quote_lamports + 2_144_280,
            "tokens_acquired": 3_564_784_017_626}


class ReconciliationTests(unittest.TestCase):

    def setUp(self):
        self.components = _components()
        self.proposal = B17A.propose(B17A.synthetic_observation(), 100_000_000)

    def test_accepts_a_coherent_position(self):
        result = B17A.reconcile(self.components["portfolio"], self.proposal, _good_simulation())
        self.assertIs(result["reconciled"], True)
        self.assertIs(result["position_is_simulated"], True)
        self.assertGreater(result["projected_total_exposure_lamports"], 0)

    def test_refuses_an_entry_that_cost_less_than_the_order(self):
        """Costs are charged on top of the order, so this is arithmetically impossible."""
        simulation = _good_simulation() | {"lamports_out_of_wallet_at_entry": 99_999_999}
        with self.assertRaises(B17A.RehearsalRefused) as refusal:
            B17A.reconcile(self.components["portfolio"], self.proposal, simulation)
        self.assertIn("less than the order size", str(refusal.exception))

    def test_refuses_a_position_with_no_tokens(self):
        simulation = _good_simulation() | {"tokens_acquired": 0}
        with self.assertRaises(B17A.RehearsalRefused) as refusal:
            B17A.reconcile(self.components["portfolio"], self.proposal, simulation)
        self.assertIn("no tokens", str(refusal.exception))

    def test_refuses_when_exposure_does_not_rise(self):
        """A zero-size order leaves exposure flat; the rehearsal must not call that reconciled."""
        proposal = B17A.propose(B17A.synthetic_observation(), 0)
        with self.assertRaises(B17A.RehearsalRefused) as refusal:
            B17A.reconcile(self.components["portfolio"], proposal, _good_simulation(0))
        self.assertIn("did not rise", str(refusal.exception))

    def test_uses_b12a_exposure_rather_than_its_own_copy(self):
        """Read from the AST: a second copy of someone else's arithmetic drifts from it.

        My first attempt re-derived exposure by summing `quote_lamports` over open positions, which
        carry `deployed_lamports`, and raised a KeyError. The fix was to call B12a.
        """
        tree = ast.parse((ROOT / "scripts" / "b17a_shadow_rehearsal.py").read_text())
        reconcile = next(node for node in ast.walk(tree)
                         if isinstance(node, ast.FunctionDef) and node.name == "reconcile")
        calls = {ast.unparse(node.func) for node in ast.walk(reconcile)
                 if isinstance(node, ast.Call)}
        self.assertIn("B12A.exposure_snapshot", calls)


# ----------------------------------------------------------------------------------------------
# The seam: a rejected proposal is never priced
# ----------------------------------------------------------------------------------------------

class RejectionBlocksPricingTests(unittest.TestCase):

    def force_decision(self, **overrides):
        """B12a's REAL decision with only the verdict overridden, restored on cleanup.

        A hand-built decision dict is not a decision: b12b reads `proposal`, `grouping`,
        `exposure_after` and `decision_sha256` off it, and a fake that omits them tests the fake.
        """
        original = B12A.decide
        self.addCleanup(setattr, B12A, "decide", original)
        B12A.decide = lambda *args, **kwargs: original(*args, **kwargs) | overrides

    def test_kill_switch_rejects_and_the_report_shows_no_priced_entry(self):
        counterexample = B17A.rehearse()["kill_switch_counterexample"]
        self.assertEqual(counterexample["decision"], B12A.DECISION_REJECTED)
        self.assertEqual(counterexample["primary_reason"], "R02_KILL_SWITCH_ENGAGED")
        self.assertIsNone(counterexample["simulated_round_trip"])

    def test_rehearse_raises_if_the_kill_switch_ever_approves(self):
        """Neuter the switch and the rehearsal must refuse to produce a report at all."""
        self.force_decision(decision=B12A.DECISION_APPROVED, primary_reason=None, reasons=[])
        with self.assertRaises(B17A.RehearsalRefused) as refusal:
            B17A.rehearse()
        self.assertIn("kill switch", str(refusal.exception))

    def test_a_rejected_decision_leaves_the_priced_fields_null(self):
        """The general seam, not only the kill-switch instance of it."""
        self.force_decision(decision=B12A.DECISION_REJECTED,
                            primary_reason="R01_EVIDENCE_STALE", reasons=["R01_EVIDENCE_STALE"])
        report = B17A.rehearse()
        self.assertEqual(report["risk_decision"]["decision"], B12A.DECISION_REJECTED)
        self.assertIsNone(report["simulated_round_trip"])
        self.assertIsNone(report["reconciliation"])

    def test_simulate_round_trip_refuses_an_exit_it_cannot_price(self):
        """A rehearsal that cannot close its position has not rehearsed the part that matters.

        A COMPLETED curve is the real structural-unavailability path: B10a refuses it rather than
        inventing a mark or assuming a migration, so the rehearsal must refuse too.
        """
        observation = B17A.synthetic_observation()
        drained = dict(observation, slot=observation["slot"] + 1000, complete=True)
        schedule = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0,
                    "buyback_fee_bps": 5000}
        policy = {"base_fee_lamports": 5000, "priority_fee_lamports": 100_000, "tip_lamports": 0,
                  "ata_rent_lamports": 2_039_280, "failed_attempts": 0}
        with self.assertRaises(B17A.RehearsalRefused) as refusal:
            B17A.simulate_round_trip(observation, drained, schedule, policy, 100_000_000)
        self.assertIn("could not be priced", str(refusal.exception))


# ----------------------------------------------------------------------------------------------
# Honesty of the report itself
# ----------------------------------------------------------------------------------------------

class ReportHonestyTests(unittest.TestCase):

    def test_the_rehearsal_is_deterministic(self):
        """Two runs, byte-identical. A rehearsal that wanders is not a baseline for anything."""
        first = json.dumps(B17A.rehearse(), sort_keys=True)
        second = json.dumps(B17A.rehearse(), sort_keys=True)
        self.assertEqual(first, second)

    def test_the_report_never_claims_to_be_evaluation_or_execution(self):
        report = B17A.rehearse()
        self.assertIs(report["executable"], False)
        self.assertEqual(report["performance_status"], "not_evaluated")
        self.assertEqual(report["execution_status"], "never_executed")
        self.assertIn("SYNTHETIC", report["evidence"])
        self.assertIs(report["simulated_round_trip"]["simulation_only"], True)

    def test_the_observation_declares_itself_synthetic(self):
        """So no reader can mistake this for a window, fresh or burned."""
        self.assertIn("SYNTHETIC", B17A.synthetic_observation()["evidence"])

    def test_the_approved_decision_is_marked_simulation_only(self):
        report = B17A.rehearse()
        self.assertEqual(report["risk_decision"]["decision"], B12A.DECISION_APPROVED)
        self.assertIs(report["risk_decision"]["approval_is_simulation_only"], True)

    def test_propose_contains_no_strategy(self):
        """`propose` must not choose a size, a threshold or a filter. Read from the AST.

        A plumbing rehearsal is exactly the place a strategy appears by accident, because it is the
        only module that touches every stage.
        """
        tree = ast.parse((ROOT / "scripts" / "b17a_shadow_rehearsal.py").read_text())
        propose = next(node for node in ast.walk(tree)
                       if isinstance(node, ast.FunctionDef) and node.name == "propose")
        branches = [node for node in ast.walk(propose) if isinstance(node, (ast.If, ast.Compare))]
        self.assertEqual(branches, [], "propose branches on something, so it is selecting")
        numbers = [node.value for node in ast.walk(propose)
                   if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
                   and not isinstance(node.value, bool)]
        self.assertEqual(numbers, [], f"propose holds a numeric constant {numbers}: a parameter")

    def test_no_float_appears_in_the_report(self):
        """Exact integers throughout, as everywhere else in this project."""
        def walk(value, path="report"):
            self.assertNotIsInstance(value, float, f"a float reached {path}")
            if isinstance(value, dict):
                for key, item in value.items():
                    walk(item, f"{path}.{key}")
            if isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, f"{path}[{index}]")
        walk(B17A.rehearse())


if __name__ == "__main__":
    unittest.main()
