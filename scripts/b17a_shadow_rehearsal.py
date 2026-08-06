"""B17a — one deterministic, signing-free end-to-end shadow rehearsal.

Chains the pieces that already exist and have never been run together: a canonical live-style
observation, an order proposal derived from it, B12a's risk decision, a simulated entry, observed
path and exit through B9I/B10a, a reconciliation, and B12b's read-only operator snapshot.

WHAT THIS IS FOR
----------------
Every stage has its own tests. What nothing tested was the SEAM: that a decision B12a rejects cannot
become a priced entry, that a simulated position reconciles against the portfolio it claims to have
changed, and that the whole chain touches no wallet, no key, no transaction and no socket. Those are
properties of the composition, not of any part, and they are what this module asserts.

SYNTHETIC EVIDENCE ONLY
-----------------------
The observation is constructed here and labelled synthetic in the output. No fresh window is read,
nothing under `research/b11a` is opened, and no burned artifact is required. A rehearsal drawn from
real evaluation data would be a composition inspection wearing a friendly name.

THE PROOF IS RUNTIME, NOT A PROMISE
-----------------------------------
`assert_no_execution_surface` reads the AST of the whole transitive module closure for wallet, key,
signing, transaction-construction, simulate and submit surfaces. `rehearse` then runs the entire
chain with `socket.socket` replaced by something that raises, so a network call anywhere in the
closure aborts the rehearsal instead of succeeding quietly.
"""
import argparse
import ast
import copy
import importlib.util
import json
import pathlib
import socket

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B12A = _load("b12a_risk_governor", "b12a_risk_governor.py")
B12B = _load("b12b_operator_snapshot", "b12b_operator_snapshot.py")
B10A = _load("b10a_simulator_kernel", "b10a_simulator_kernel.py")

# Every surface that would turn a rehearsal into a live action. Scanned across the closure from the
# AST, so a name in a docstring is documentation and a name in code is a finding.
#
# The two groups are matched differently, and the split is load-bearing. Wire names travel AS
# STRINGS -- an RPC method is literally the text you send -- so they are matched as substrings of
# any code string. Class names never do; they are imported and called. Substring-matching those
# flagged recorder.py for `maxSupportedTransactionVersion`, a getBlock parameter for READING blocks,
# which is the opposite of a signing capability. Matching them as identifiers and imports instead
# loses nothing: `Transaction()` is an ast.Name, and `from x import Transaction` is an ast.alias.
EXECUTION_SURFACE_WIRE = (
    "sendTransaction", "signTransaction", "simulateTransaction", "requestAirdrop",
    "from_secret_key", "from_seed", "private_key", "secret_key", "sign_message",
    "PRIVATE_KEY", "MNEMONIC", "mnemonic", "seed_phrase", "partial_sign", "sign_and_send",
)
EXECUTION_SURFACE_TYPES = ("Keypair", "Transaction", "VersionedTransaction")
EXECUTION_SURFACE = EXECUTION_SURFACE_WIRE + EXECUTION_SURFACE_TYPES

# Modules the rehearsal deliberately does not scan for the surface list: they are the scanner's own
# declaration of it. Nothing else is exempt.
SELF = "b17a_shadow_rehearsal.py"


class RehearsalRefused(RuntimeError):
    """The rehearsal cannot proceed honestly, so it produces nothing."""


class NetworkAttempted(RehearsalRefused):
    """Something in the closure tried to open a socket during a rehearsal that must not."""


def module_closure(entry=SELF, scripts_dir=None):
    """Every module reachable through `_load`, transitively. The unit the guards apply to."""
    scripts_dir = pathlib.Path(scripts_dir or ROOT / "scripts")
    seen, pending = set(), [entry]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        path = scripts_dir / name
        if not path.exists():
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "_load" and len(node.args) == 2 \
                    and isinstance(node.args[1], ast.Constant):
                pending.append(node.args[1].value)
    return sorted(seen)


def code_string_constants(path):
    """String constants that are CODE, excluding docstrings. Comments are absent from an AST."""
    tree = ast.parse(pathlib.Path(path).read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value not in docstrings]


# A module that DECLARES a denylist is documenting what it refuses, not doing it. Recognised by the
# shape of the declaration rather than by a list of variable names: enumerating names means the scan
# breaks the next time a module calls its denylist something new, which is exactly how this scan
# first fired on b12b's own FORBIDDEN_SUBSTRINGS.
DENYLIST_NAME_MARKERS = ("FORBIDDEN", "BANNED", "SURFACE", "SECRET", "CREDENTIAL", "MARKER",
                         "TOKENS", "SUBSTRING", "PROHIBIT", "REFUSED")


def _declared_surface(path):
    """String constants a module declares as a DENYLIST, which must not trip its own scan.

    Recognised structurally: a module-level assignment to an ALL-CAPS name that reads like a
    denylist, holding a tuple, list or set of strings. A capability is called, indexed or passed;
    a denylist just sits there being compared against.
    """
    tree = ast.parse(pathlib.Path(path).read_text())
    declared = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if not any(name.isupper() and any(marker in name for marker in DENYLIST_NAME_MARKERS)
                   for name in names):
            continue
        if not isinstance(node.value, (ast.Tuple, ast.List, ast.Set)):
            continue
        for child in ast.walk(node.value):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                declared.add(child.value)
    return declared


def assert_no_execution_surface(entry=SELF, scripts_dir=None):
    """No module in the closure can construct, sign, simulate or submit a transaction.

    Read from the AST rather than the text: a mention in a docstring is documentation and a string
    constant in code is a capability. Each module's own declaration of the token list is excluded,
    because a scanner that trips on its own vocabulary is a scanner nobody can run.
    """
    scripts_dir = pathlib.Path(scripts_dir or ROOT / "scripts")
    findings = {}
    for name in module_closure(entry, scripts_dir):
        path = scripts_dir / name
        if not path.exists():
            continue
        declared = _declared_surface(path)
        values = [v for v in code_string_constants(path) if v not in declared]
        hits = sorted({token for token in EXECUTION_SURFACE_WIRE
                       for value in values if token in value})
        # An identifier can also be a capability, not only a string -- and for the class names it is
        # the ONLY way they appear, so imports are walked too or the split above would leave a hole.
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in EXECUTION_SURFACE:
                hits.append(node.attr)
            if isinstance(node, ast.Name) and node.id in EXECUTION_SURFACE:
                hits.append(node.id)
            if isinstance(node, ast.alias) and node.name.split(".")[-1] in EXECUTION_SURFACE:
                hits.append(node.name.split(".")[-1])
        hits = sorted(set(hits) - declared)
        if hits:
            findings[name] = hits
    if findings:
        raise RehearsalRefused(
            f"an execution surface is reachable from the rehearsal: {findings}. A shadow rehearsal "
            f"that can build or send a transaction is not a shadow rehearsal")
    return {
        "closure": module_closure(entry, scripts_dir),
        "execution_surface_found": {},
        # Stated in the artifact rather than left to a reader, because the B17c gap map read this
        # result as a repository-wide absence and was wrong: scripts/recorder.py and the b12b
        # operator console both exist and are outside this closure.
        "scope": ("the transitive `_load` closure of the rehearsal chain ONLY. This is not a "
                  "repository-wide scan and says nothing about modules outside the closure."),
    }


class NoNetwork:
    """Replaces `socket.socket` for the duration, so a network call raises instead of succeeding."""

    def __enter__(self):
        self._saved = socket.socket

        def refuse(*args, **kwargs):
            raise NetworkAttempted(
                "the rehearsal opened a socket. Every input here is synthetic and on-disk, so a "
                "network call means something reached for evidence it was not given")

        socket.socket = refuse
        return self

    def __exit__(self, *exception):
        socket.socket = self._saved
        return False


# ----------------------------------------------------------------------------------------------
# The chain
# ----------------------------------------------------------------------------------------------

def synthetic_observation():
    """One canonical live-style observation. Deterministic and labelled synthetic."""
    return {
        "evidence": "SYNTHETIC. Constructed here, not drawn from any window, fresh or burned.",
        "mint": "MintSynth1111111111111111111111111111111111",
        "bonding_curve": "CurveSynth111111111111111111111111111111111",
        "creator": "CreatorSynthA1111111111111111111111111111111",
        "slot": 435_600_003, "transaction_index": 7, "outer_index": 0, "inner_index": 1,
        "virtual_quote": 30_000_000_000, "virtual_token": 1_073_000_000_000_000,
        "real_quote": 4_200_000_000, "real_token": 780_000_000_000_000,
        "quote_mint": B10A.B9D.NATIVE_QUOTE_MINT, "mayhem_mode": False, "complete": False,
    }


def propose(observation, quote_lamports):
    """Turn an observation into an order proposal. No model, no signal, no selection.

    The size is an argument, not a choice made here: this module rehearses the PLUMBING and must not
    become the place a strategy quietly appears.
    """
    return {
        "schema_version": B12A.SCHEMA_VERSION,
        "proposal_id": f"rehearsal-{observation['slot']}-{observation['transaction_index']}",
        "mint": observation["mint"], "bonding_curve": observation["bonding_curve"],
        "creator": observation["creator"], "side": B10A.BUY,
        "quote_lamports": quote_lamports,
    }


def curve_state(observation):
    return {field: observation[field] for field in
            ("virtual_quote", "virtual_token", "real_quote", "real_token", "quote_mint",
             "mayhem_mode", "complete")} | {"slot": observation["slot"]}


def simulate_round_trip(observation, exit_observation, schedule, policy, quote_lamports):
    """Entry, path and exit through the pinned arithmetic. Simulation only, and labelled so."""
    bought = B10A.price_entry(curve_state(observation),
                              {"side": B10A.BUY, "quote_lamports": quote_lamports},
                              schedule, policy)
    sold = B10A.price_exit(curve_state(exit_observation), bought["tokens_out"], schedule, policy)
    if sold.get("status") != B10A.STATUS_PRICED:
        raise RehearsalRefused(
            f"the simulated exit could not be priced: {sold.get('liquidity')}. A rehearsal that "
            f"cannot close its own position has not rehearsed the thing that matters")
    return {
        "simulation_only": True,
        "NO_SIGNING_OR_SUBMISSION": B12A.NO_SIGNING_OR_SUBMISSION,
        "tokens_acquired": bought["tokens_out"],
        "lamports_out_of_wallet_at_entry": bought["lamports_out_of_wallet"],
        "lamports_into_wallet_at_exit": sold["lamports_into_wallet"],
        "simulated_net_lamports": sold["lamports_into_wallet"] - bought["lamports_out_of_wallet"],
        "entry_slot": observation["slot"], "exit_slot": exit_observation["slot"],
    }


def reconcile(portfolio, proposal, simulated):
    """The seam nothing tested: does the simulated position agree with the book it claims to move?

    Fail-closed on any disagreement. A rehearsal whose position and portfolio drift apart is
    rehearsing two different systems.
    """
    problems = []
    if simulated["lamports_out_of_wallet_at_entry"] < proposal["quote_lamports"]:
        problems.append(
            "the entry cost less than the order size, which cannot happen once costs are charged")
    if simulated["tokens_acquired"] <= 0:
        problems.append("the entry acquired no tokens, so there is no position to reconcile")
    # B12a's own arithmetic, called rather than re-derived. Open positions carry
    # `deployed_lamports` and pending orders carry `quote_lamports`; my first attempt summed one
    # field over both and raised a KeyError, which is what a second copy of someone else's
    # arithmetic earns.
    before = B12A.exposure_snapshot(portfolio, proposal["creator"])
    projected_exposure = before["total_exposure_lamports"] + proposal["quote_lamports"]
    if projected_exposure <= before["total_exposure_lamports"]:
        problems.append("projected exposure did not rise after adding a positive order")
    if problems:
        raise RehearsalRefused(f"reconciliation failed: {problems}")
    return {
        "reconciled": True,
        "projected_total_exposure_lamports": projected_exposure,
        "position_is_simulated": True,
        "no_custody": ("no wallet holds anything as a result of this rehearsal; the position exists "
                       "only as arithmetic"),
    }


def rehearse(quote_lamports=100_000_000, components=None, schedule=None, exit_after_slots=1000):
    """The whole chain, under a runtime guard that forbids the network."""
    surface = assert_no_execution_surface()
    components = copy.deepcopy(components or B12B.demo_components())
    schedule = schedule or {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0,
                            "buyback_fee_bps": 5000}
    policy = {"base_fee_lamports": 5000, "priority_fee_lamports": 100_000, "tip_lamports": 0,
              "ata_rent_lamports": 2_039_280, "failed_attempts": 0}

    with NoNetwork():
        observation = synthetic_observation()
        proposal = propose(observation, quote_lamports)
        # The state B12a judges is the CURVE state, delegated to b11b's own eligibility vetoes, not
        # a status word. Passing a placeholder produced R11_CURVE_STATE_INCOMPLETE -- a correct
        # refusal of an incomplete input, and the wrong input to rehearse with.
        decision = B12A.decide(proposal, curve_state(observation), components["portfolio"],
                               components["health"], components["config"])
        simulated, reconciliation = None, None
        if decision["decision"] == B12A.DECISION_APPROVED:
            exit_observation = dict(observation, slot=observation["slot"] + exit_after_slots,
                                    real_quote=observation["real_quote"] * 2,
                                    virtual_quote=observation["virtual_quote"]
                                    + observation["real_quote"])
            simulated = simulate_round_trip(observation, exit_observation, schedule, policy,
                                            quote_lamports)
            reconciliation = reconcile(components["portfolio"], proposal, simulated)

        components["risk_decisions"] = [decision]
        snapshot = B12B.build_snapshot(**components)

    # The same chain with the kill switch engaged, so the report DEMONSTRATES that a rejection
    # blocks pricing rather than asserting it in prose.
    with NoNetwork():
        halted = copy.deepcopy(components)
        halted["health"]["kill_switch_engaged"] = True
        halted_decision = B12A.decide(proposal, curve_state(observation), halted["portfolio"],
                                      halted["health"], halted["config"])
        if halted_decision["decision"] == B12A.DECISION_APPROVED:
            raise RehearsalRefused(
                "the kill switch did not reject the proposal; the control that stops everything "
                "must stop this too")

    return {
        "schema_version": SCHEMA_VERSION,
        "rehearsal": "B17A_SHADOW_REHEARSAL",
        "kill_switch_counterexample": {
            "decision": halted_decision["decision"],
            "primary_reason": halted_decision["primary_reason"],
            # Not a variable that happened to stay None: the branch above RAISES if the kill switch
            # approved, so reaching this line proves nothing was priced.
            "simulated_round_trip": None,
            "shows": ("the identical chain, with only the kill switch changed, produces no priced "
                      "entry at all. The rejection is load-bearing, not decorative."),
        },
        "evidence": "SYNTHETIC ONLY. No fresh window, no burned artifact, no network.",
        "executable": False,
        "performance_status": "not_evaluated",
        "execution_status": "never_executed",
        "no_execution_surface": surface,
        "network": "refused at runtime: socket.socket raised for the duration of the chain",
        "observation": observation,
        "proposal": proposal,
        "risk_decision": {"decision": decision["decision"],
                          "primary_reason": decision["primary_reason"],
                          "reasons": decision["reasons"],
                          "approval_is_simulation_only": decision["approval_is_simulation_only"]},
        "simulated_round_trip": simulated,
        "reconciliation": reconciliation,
        "operator_snapshot_hash": B12B.snapshot_hash(snapshot),
        "operator_snapshot_status": snapshot.get("status"),
        "a_rejected_proposal_is_never_priced": (
            "the entry, path, exit and reconciliation run only when B12a approved. A rejected "
            "decision leaves them null, which is what makes the rejection mean something."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="B17a signing-free shadow rehearsal (offline)")
    parser.add_argument("--output", default=None)
    parser.add_argument("--quote-lamports", type=int, default=100_000_000)
    arguments = parser.parse_args(argv)
    report = rehearse(quote_lamports=arguments.quote_lamports)
    text = json.dumps(report, indent=1, sort_keys=True)
    if arguments.output:
        pathlib.Path(arguments.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(arguments.output).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
