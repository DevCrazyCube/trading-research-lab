"""Guards for B17a's shadow rehearsal.

Every test here attacks a property of the COMPOSITION, because that is what B17a exists to assert.
The individual stages have their own suites; what these cover is the seam between them and the two
runtime proofs (no execution surface, no socket) that make the rehearsal a rehearsal.
"""
import ast
import importlib.util
import pathlib
import socket

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B17A = _load("b17a_shadow_rehearsal_under_test", "b17a_shadow_rehearsal.py")
B12A = B17A.B12A


# ----------------------------------------------------------------------------------------------
# The execution-surface scan: it must fire on capability and stay silent on prose
# ----------------------------------------------------------------------------------------------

def _plant(directory, name, source):
    path = pathlib.Path(directory) / name
    path.write_text(source)
    return path


def test_surface_scan_fires_on_a_signing_capability(tmp_path):
    """The whole point. A module that can sign must be refused."""
    _plant(tmp_path, "entry.py", 'method = "signTransaction"\n')
    with pytest.raises(B17A.RehearsalRefused) as refusal:
        B17A.assert_no_execution_surface("entry.py", tmp_path)
    assert "signTransaction" in str(refusal.value)


def test_surface_scan_fires_on_an_attribute_not_only_a_string(tmp_path):
    """A capability reached as `client.sendTransaction` is a capability, string constant or not."""
    _plant(tmp_path, "entry.py", "def go(client):\n    return client.sendTransaction(1)\n")
    with pytest.raises(B17A.RehearsalRefused):
        B17A.assert_no_execution_surface("entry.py", tmp_path)


def test_surface_scan_fires_on_a_bare_name(tmp_path):
    _plant(tmp_path, "entry.py", "def go():\n    return Keypair\n")
    with pytest.raises(B17A.RehearsalRefused):
        B17A.assert_no_execution_surface("entry.py", tmp_path)


def test_surface_scan_is_silent_on_a_docstring_mention(tmp_path):
    """Prose is not capability. A module that DOCUMENTS that it never signs must still pass."""
    _plant(tmp_path, "entry.py",
           '"""This module never calls signTransaction and holds no private_key."""\n'
           "value = 1\n")
    result = B17A.assert_no_execution_surface("entry.py", tmp_path)
    assert result["execution_surface_found"] == {}


def test_surface_scan_is_silent_on_a_comment_mention(tmp_path):
    _plant(tmp_path, "entry.py", "# no sendTransaction anywhere here\nvalue = 1\n")
    assert B17A.assert_no_execution_surface("entry.py", tmp_path)["execution_surface_found"] == {}


def test_surface_scan_is_silent_on_a_declared_denylist(tmp_path):
    """A module declaring what it refuses must not trip on its own vocabulary.

    This is not hypothetical: the scan's first run fired on b12b's own FORBIDDEN_SUBSTRINGS.
    """
    _plant(tmp_path, "entry.py",
           'FORBIDDEN_SUBSTRINGS = ("signTransaction", "private_key")\n'
           "def check(text):\n"
           "    return any(bad in text for bad in FORBIDDEN_SUBSTRINGS)\n")
    assert B17A.assert_no_execution_surface("entry.py", tmp_path)["execution_surface_found"] == {}


def test_denylist_exemption_does_not_extend_to_lowercase_names(tmp_path):
    """`banned = (...)` is a variable, not a declaration. Only ALL-CAPS constants are exempt."""
    _plant(tmp_path, "entry.py", 'banned = ("signTransaction",)\n')
    with pytest.raises(B17A.RehearsalRefused):
        B17A.assert_no_execution_surface("entry.py", tmp_path)


def test_denylist_exemption_does_not_extend_to_a_call(tmp_path):
    """An ALL-CAPS name assigned from a CALL is not a literal denylist and gets no exemption."""
    _plant(tmp_path, "entry.py", 'FORBIDDEN_TOKENS = build("signTransaction")\n')
    with pytest.raises(B17A.RehearsalRefused):
        B17A.assert_no_execution_surface("entry.py", tmp_path)


def test_denylist_exemption_does_not_cover_an_unrelated_capitalised_name(tmp_path):
    """SURFACE/FORBIDDEN/... are the markers. `SETTINGS = (...)` is not a denylist."""
    _plant(tmp_path, "entry.py", 'SETTINGS = ("signTransaction",)\n')
    with pytest.raises(B17A.RehearsalRefused):
        B17A.assert_no_execution_surface("entry.py", tmp_path)


def test_surface_scan_reaches_through_the_closure(tmp_path):
    """A capability one hop away is still reachable, and must be found."""
    _plant(tmp_path, "entry.py", 'DEP = _load("dep", "dep.py")\n')
    _plant(tmp_path, "dep.py", 'method = "sendTransaction"\n')
    with pytest.raises(B17A.RehearsalRefused) as refusal:
        B17A.assert_no_execution_surface("entry.py", tmp_path)
    assert "dep.py" in str(refusal.value)


def test_module_closure_is_transitive_and_terminates_on_a_cycle(tmp_path):
    _plant(tmp_path, "a.py", '_load("b", "b.py")\n')
    _plant(tmp_path, "b.py", '_load("c", "c.py")\n')
    _plant(tmp_path, "c.py", '_load("a", "a.py")\n')
    assert B17A.module_closure("a.py", tmp_path) == ["a.py", "b.py", "c.py"]


def test_the_real_closure_is_clean_and_is_not_trivially_small():
    """The claim that matters, on the code that actually runs.

    The size assertion is the guard against a scan that passes because it looked at nothing.
    """
    result = B17A.assert_no_execution_surface()
    assert result["execution_surface_found"] == {}
    assert len(result["closure"]) >= 5
    assert "b12a_risk_governor.py" in result["closure"]
    assert "b10a_simulator_kernel.py" in result["closure"]


def test_code_string_constants_excludes_docstrings_and_keeps_code(tmp_path):
    path = _plant(tmp_path, "m.py",
                  '"""module doc"""\n'
                  "def f():\n"
                  '    """function doc"""\n'
                  '    return "a code string"\n')
    values = B17A.code_string_constants(path)
    assert "a code string" in values
    assert "module doc" not in values
    assert "function doc" not in values


# ----------------------------------------------------------------------------------------------
# The network proof
# ----------------------------------------------------------------------------------------------

def test_no_network_refuses_a_socket_and_restores_afterwards():
    original = socket.socket
    with B17A.NoNetwork():
        with pytest.raises(B17A.NetworkAttempted):
            socket.socket()
    assert socket.socket is original


def test_no_network_restores_even_when_the_body_raises():
    """A guard that leaks its patch on the error path breaks every later test in the process."""
    original = socket.socket
    with pytest.raises(ValueError):
        with B17A.NoNetwork():
            raise ValueError("something else went wrong")
    assert socket.socket is original


def test_network_attempted_is_a_refusal_not_a_generic_error():
    """It must be caught by anything catching RehearsalRefused, so it cannot pass as a normal fault."""
    assert issubclass(B17A.NetworkAttempted, B17A.RehearsalRefused)


# ----------------------------------------------------------------------------------------------
# Reconciliation: fail-closed on every disagreement
# ----------------------------------------------------------------------------------------------

def _components():
    import copy
    return copy.deepcopy(B17A.B12B.demo_components())


def _good_simulation(quote_lamports=100_000_000):
    return {"lamports_out_of_wallet_at_entry": quote_lamports + 2_144_280,
            "tokens_acquired": 3_564_784_017_626}


def test_reconcile_accepts_a_coherent_position():
    components = _components()
    proposal = B17A.propose(B17A.synthetic_observation(), 100_000_000)
    result = B17A.reconcile(components["portfolio"], proposal, _good_simulation())
    assert result["reconciled"] is True
    assert result["position_is_simulated"] is True
    assert result["projected_total_exposure_lamports"] > 0


def test_reconcile_refuses_an_entry_that_cost_less_than_the_order():
    """Costs are charged on top of the order, so this is arithmetically impossible."""
    components = _components()
    proposal = B17A.propose(B17A.synthetic_observation(), 100_000_000)
    simulation = _good_simulation() | {"lamports_out_of_wallet_at_entry": 99_999_999}
    with pytest.raises(B17A.RehearsalRefused) as refusal:
        B17A.reconcile(components["portfolio"], proposal, simulation)
    assert "less than the order size" in str(refusal.value)


def test_reconcile_refuses_a_position_with_no_tokens():
    components = _components()
    proposal = B17A.propose(B17A.synthetic_observation(), 100_000_000)
    simulation = _good_simulation() | {"tokens_acquired": 0}
    with pytest.raises(B17A.RehearsalRefused) as refusal:
        B17A.reconcile(components["portfolio"], proposal, simulation)
    assert "no tokens" in str(refusal.value)


def test_reconcile_refuses_when_exposure_does_not_rise():
    """A zero-size order would leave exposure flat; the rehearsal must not call that reconciled."""
    components = _components()
    proposal = B17A.propose(B17A.synthetic_observation(), 0)
    with pytest.raises(B17A.RehearsalRefused) as refusal:
        B17A.reconcile(components["portfolio"], proposal, _good_simulation(0))
    assert "did not rise" in str(refusal.value)


def test_reconcile_uses_b12a_exposure_rather_than_its_own_copy():
    """Read from the AST: a second copy of someone else's arithmetic drifts from it.

    My first attempt re-derived exposure by summing `quote_lamports` over open positions, which
    carry `deployed_lamports`, and raised a KeyError. The fix was to call B12a.
    """
    source = (ROOT / "scripts" / "b17a_shadow_rehearsal.py").read_text()
    tree = ast.parse(source)
    reconcile = next(node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef) and node.name == "reconcile")
    calls = {ast.unparse(node.func) for node in ast.walk(reconcile) if isinstance(node, ast.Call)}
    assert "B12A.exposure_snapshot" in calls


# ----------------------------------------------------------------------------------------------
# The seam: a rejected proposal is never priced
# ----------------------------------------------------------------------------------------------

def test_kill_switch_rejects_and_the_report_shows_no_priced_entry():
    report = B17A.rehearse()
    counterexample = report["kill_switch_counterexample"]
    assert counterexample["decision"] == B12A.DECISION_REJECTED
    assert counterexample["primary_reason"] == "R02_KILL_SWITCH_ENGAGED"
    assert counterexample["simulated_round_trip"] is None


def _forcing_decide(**overrides):
    """B12a's REAL decision with only the verdict overridden.

    A hand-built decision dict is not a decision: b12b reads `proposal`, `grouping`,
    `exposure_after` and `decision_sha256` off it, and a fake that omits them tests the fake.
    """
    original = B12A.decide

    def decide(*args, **kwargs):
        return original(*args, **kwargs) | overrides
    return decide


def test_rehearse_raises_if_the_kill_switch_ever_approves(monkeypatch):
    """Neuter the switch and the rehearsal must refuse to produce a report at all."""
    monkeypatch.setattr(B12A, "decide",
                        _forcing_decide(decision=B12A.DECISION_APPROVED, primary_reason=None,
                                        reasons=[]))
    with pytest.raises(B17A.RehearsalRefused) as refusal:
        B17A.rehearse()
    assert "kill switch" in str(refusal.value)


def test_a_rejected_decision_leaves_the_priced_fields_null(monkeypatch):
    """The general seam, not only the kill-switch instance of it."""
    monkeypatch.setattr(B12A, "decide",
                        _forcing_decide(decision=B12A.DECISION_REJECTED,
                                        primary_reason="R01_EVIDENCE_STALE",
                                        reasons=["R01_EVIDENCE_STALE"]))
    report = B17A.rehearse()
    assert report["risk_decision"]["decision"] == B12A.DECISION_REJECTED
    assert report["simulated_round_trip"] is None
    assert report["reconciliation"] is None


def test_simulate_round_trip_refuses_an_exit_it_cannot_price():
    """A rehearsal that cannot close its position has not rehearsed the part that matters.

    A COMPLETED curve is the real structural-unavailability path: B10a refuses it rather than
    inventing a mark or assuming a migration, so the rehearsal must refuse too.
    """
    observation = B17A.synthetic_observation()
    drained = dict(observation, slot=observation["slot"] + 1000, complete=True)
    schedule = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}
    policy = {"base_fee_lamports": 5000, "priority_fee_lamports": 100_000, "tip_lamports": 0,
              "ata_rent_lamports": 2_039_280, "failed_attempts": 0}
    with pytest.raises(B17A.RehearsalRefused) as refusal:
        B17A.simulate_round_trip(observation, drained, schedule, policy, 100_000_000)
    assert "could not be priced" in str(refusal.value)


# ----------------------------------------------------------------------------------------------
# Honesty of the report itself
# ----------------------------------------------------------------------------------------------

def test_the_rehearsal_is_deterministic():
    """Two runs, byte-identical. A rehearsal that wanders is not a baseline for anything."""
    import json
    first = json.dumps(B17A.rehearse(), sort_keys=True)
    second = json.dumps(B17A.rehearse(), sort_keys=True)
    assert first == second


def test_the_report_never_claims_to_be_evaluation_or_execution():
    report = B17A.rehearse()
    assert report["executable"] is False
    assert report["performance_status"] == "not_evaluated"
    assert report["execution_status"] == "never_executed"
    assert "SYNTHETIC" in report["evidence"]
    assert report["simulated_round_trip"]["simulation_only"] is True


def test_the_observation_declares_itself_synthetic():
    """So no reader can mistake this for a window, fresh or burned."""
    assert "SYNTHETIC" in B17A.synthetic_observation()["evidence"]


def test_the_approved_decision_is_marked_simulation_only():
    report = B17A.rehearse()
    assert report["risk_decision"]["decision"] == B12A.DECISION_APPROVED
    assert report["risk_decision"]["approval_is_simulation_only"] is True


def test_propose_contains_no_strategy():
    """`propose` must not choose a size, a threshold or a filter. Read from the AST.

    A plumbing rehearsal is exactly the place a strategy appears by accident, because it is the only
    module that touches every stage.
    """
    source = (ROOT / "scripts" / "b17a_shadow_rehearsal.py").read_text()
    tree = ast.parse(source)
    propose = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef) and node.name == "propose")
    assert not [node for node in ast.walk(propose) if isinstance(node, (ast.If, ast.Compare))], \
        "propose branches on something, which means it is selecting"
    numbers = [node.value for node in ast.walk(propose)
               if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
               and not isinstance(node.value, bool)]
    assert not numbers, f"propose contains a numeric constant {numbers}, which is a parameter"


def test_no_float_appears_in_the_report():
    """Exact integers throughout, as everywhere else in this project."""
    def walk(value, path="report"):
        if isinstance(value, float):
            raise AssertionError(f"a float reached {path}: {value}")
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
    walk(B17A.rehearse())
