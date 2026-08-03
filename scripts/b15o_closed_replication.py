"""B15o — B15L and B15M replicated on a mechanically closed population, or nothing at all.

Implements `research/B15O_CLOSED_REPLICATION_PREREGISTRATION.json`, committed alone before any B15N
strategy quantity was read.

**The population is drawn, not chosen.** The first 5,000 distinct launches B15N scheduled, in
canonical (t0_slot, signature, mint) order. Membership is a function of the schedule table and that
ordering and nothing else — not of a curve, not of reserves, not of any outcome. The boundary is
never moved or shortened, because a population trimmed to what happened to mature is a population
chosen after its outcomes were visible.

**The gate is fail-closed and needs all three conditions.** The count alone would materialize before
the last horizons were read; the slot alone while attempts were still in flight; terminality alone on
a population that is not yet 5,000. Absence of evidence is never closure.

**Nothing is replicated except which artifact supplies the exits.** Both estimands, both labels,
every threshold, grid, delay, horizon, cost scenario and refusal code are the published ones, bound
by their preregistrations' canonical hashes.

**The comparison is descriptive.** No tolerance, no agreement criterion, no verdict. A threshold
invented now would be one chosen with the V1 numbers already known.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15o"
B15I_DB = ROOT / "research" / "b15i" / "processed_feed.sqlite"
B15N_DB = ROOT / "research" / "b15n" / "exit_checkpoints.sqlite"

PREREG_PATH = ROOT / "research" / "B15O_CLOSED_REPLICATION_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "92092e51c6fee7f6822faeb30ad1dbab7533c04c1dda1a8fa537a8f6330ade07"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

# Artifact paths whose appearance would mean this population descends from the recorder it exists to
# escape. Checked against the source, because that is the entire premise of the study.
FORBIDDEN_SOURCE_ARTIFACTS = ("b15a/shadow.sqlite", "b15f/checkpoints.sqlite")

O_POPULATION_OPEN = "O_POPULATION_OPEN"
O_NOT_MATURE = "O_NOT_MATURE"
O_ATTEMPTS_IN_FLIGHT = "O_ATTEMPTS_IN_FLIGHT"
O_ALREADY_MATERIALIZED = "O_ALREADY_MATERIALIZED"
O_FORBIDDEN_SOURCE = "O_FORBIDDEN_SOURCE"
O_EVIDENCE_INSUFFICIENT = "O_EVIDENCE_INSUFFICIENT"
O_MEMBERSHIP_UNSTABLE = "O_MEMBERSHIP_UNSTABLE"
O_PUBLISHED_FIGURE_MISSING = "O_PUBLISHED_FIGURE_MISSING"

LABEL = "CLOSED_POPULATION_REPLICATION"
TERMINAL_STATES = ("checkpointed", "refused", "not_scheduled")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15L = _load("b15l_counterfactual_roundtrip", "b15l_counterfactual_roundtrip.py")
B15M = _load("b15m_liquidity_capacity", "b15m_liquidity_capacity.py")
B15N = _load("b15n_native_exit_checkpoints", "b15n_native_exit_checkpoints.py")
B15F = B15N.B15F


class ReplicationRefused(RuntimeError):
    """Nothing is materialized, and the reason is recorded rather than worked around."""


def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ReplicationRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise ReplicationRefused(
            f"the replication preregistration hashes {actual}, pinned {expected}")
    # Both replicated documents are bound by hash. If either has changed, what would be replicated
    # is not what was published, and the comparison would be against a different study.
    for key, module in (("b15l", B15L), ("b15m", B15M)):
        bound = document["replicated_verbatim"][key]
        theirs = module.verify_preregistration()
        if theirs["preregistration_id"] != bound["preregistration_id"]:
            raise ReplicationRefused(
                f"this document replicates {bound['preregistration_id']} but the module verifies "
                f"{theirs['preregistration_id']}")
        actual_bound = hashlib.sha256(
            json.dumps(theirs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if actual_bound != bound["canonical_sha256"]:
            raise ReplicationRefused(
                f"{bound['preregistration_id']} hashes {actual_bound} and this document binds "
                f"{bound['canonical_sha256']}; the published study has changed")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    text = path.read_text()
    marker = "FORBIDDEN_SOURCE_ARTIFACTS = (" if "FORBIDDEN_SOURCE_ARTIFACTS = (" in text \
        else "EXECUTION_SURFACE_TOKENS = ("
    body = text.split(marker, 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise ReplicationRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_no_forbidden_source(path=None):
    """The population must not descend from B15a or B15f. Checked, because it is the whole premise."""
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    text = path.read_text()
    body = text.split("FORBIDDEN_SOURCE_ARTIFACTS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in FORBIDDEN_SOURCE_ARTIFACTS if token in body})
    if found:
        raise ReplicationRefused(
            f"{O_FORBIDDEN_SOURCE}: {path.name} refers to {found}; this population exists precisely "
            f"because it does not descend from those recorders")
    return True


def _read_only(path, label):
    """Read-only, and a missing artifact refuses rather than being created.

    No separate existence check: opening a missing file with `mode=ro` already raises
    OperationalError, which the handler below turns into the same refusal with the same code. A
    preceding `path.exists()` read as an extra safeguard and was a branch whose removal changed
    nothing — the mutation sweep found it surviving, which is exactly what that looks like.
    """
    path = pathlib.Path(path)
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error as error:
        raise ReplicationRefused(
            f"{O_EVIDENCE_INSUFFICIENT}: no readable {label} artifact at {path}: {error}") from error


# --------------------------------------------------------------------------------------------
# Membership — drawn, never chosen
# --------------------------------------------------------------------------------------------

def draw_members(b15n_path=B15N_DB, size=None, activation_slot=None, document=None):
    """The first `size` distinct launches in canonical (t0_slot, signature, mint) order.

    Ordered in SQL and in Python by the same key, so the ordering does not depend on the database's
    row order. A membership that varied with insertion order would not be a drawn population.
    """
    document = verify_preregistration() if document is None else document
    population = document["the_closed_population"]
    size = population["size"] if size is None else size
    activation = population["activation_boundary"]["activation_slot"] if activation_slot is None \
        else activation_slot
    connection = _read_only(b15n_path, "B15N")
    try:
        rows = connection.execute(
            "SELECT signature, MIN(t0_slot), MIN(mint) FROM schedule WHERE t0_slot > ? "
            "GROUP BY signature", (activation,)).fetchall()
    except sqlite3.Error as error:
        raise ReplicationRefused(
            f"{O_EVIDENCE_INSUFFICIENT}: cannot read B15N's schedule: {error}") from error
    finally:
        connection.close()
    ordered = sorted(rows, key=lambda row: (row[1], row[0], row[2] or ""))
    members = [{"signature": row[0], "t0_slot": row[1], "mint": row[2]} for row in ordered[:size]]
    return members, len(ordered)


def assert_membership_stable(b15n_path=B15N_DB, document=None):
    """Drawn twice over the same evidence, it must be the same population."""
    first, _total = draw_members(b15n_path, document=document)
    second, _total = draw_members(b15n_path, document=document)
    if [m["signature"] for m in first] != [m["signature"] for m in second]:
        raise ReplicationRefused(
            f"{O_MEMBERSHIP_UNSTABLE}: the membership differed between two draws over the same "
            f"evidence")
    return True


# --------------------------------------------------------------------------------------------
# The closure gate — all three conditions, or nothing
# --------------------------------------------------------------------------------------------

def closure_state(b15n_path=B15N_DB, document=None, current_slot=None):
    """Whether the population is closed, and exactly what is still missing.

    Reports the locked state without computing a single estimand quantity, which is the point: a
    watcher that had to price a cell to know whether it may price a cell would have priced it.
    """
    document = verify_preregistration() if document is None else document
    population = document["the_closed_population"]
    size = population["size"]
    members, total = draw_members(b15n_path, document=document)
    state = {"label": LABEL, "locked": True, "size_required": size,
             "distinct_launches_available": total, "members_drawn": len(members),
             "reasons": []}
    if total < size:
        state["reasons"].append(O_POPULATION_OPEN)
        state["launches_remaining"] = size - total
        return state
    last = members[-1]
    delays = B15L.verify_preregistration()[
        "frozen_inputs_taken_from_earlier_freezes_unchanged"]["entry_delays_slots"]
    horizons = B15N.verify_preregistration()["target_geometry"]["exit_horizons"]
    tolerance = B15N.verify_preregistration()["account_read"][
        "inherited_verbatim_from_b15f"]["max_lateness_slots"]
    deadline = last["t0_slot"] + max(delays) + max(h["slots"] for h in horizons) + tolerance
    state["last_member_t0_slot"] = last["t0_slot"]
    state["last_deadline_slot"] = deadline
    state["current_slot"] = current_slot
    if current_slot is None or current_slot < deadline:
        state["reasons"].append(O_NOT_MATURE)
        if current_slot is not None:
            state["slots_remaining"] = deadline - current_slot
    signatures = {member["signature"] for member in members}
    connection = _read_only(b15n_path, "B15N")
    try:
        in_flight = sum(
            1 for (signature, row_state) in connection.execute(
                "SELECT signature, state FROM schedule")
            if signature in signatures and row_state not in TERMINAL_STATES)
    finally:
        connection.close()
    state["attempts_in_flight"] = in_flight
    if in_flight:
        state["reasons"].append(O_ATTEMPTS_IN_FLIGHT)
    state["locked"] = bool(state["reasons"])
    return state


def assert_closed(b15n_path=B15N_DB, document=None, current_slot=None):
    """Fail-closed. Every condition, or nothing is materialized."""
    state = closure_state(b15n_path, document, current_slot)
    if state["locked"]:
        raise ReplicationRefused(
            f"{state['reasons'][0]}: the population is locked ({state['reasons']}); "
            f"{state['distinct_launches_available']} of {state['size_required']} launches, "
            f"{state.get('attempts_in_flight', 0)} attempts in flight")
    return state


# --------------------------------------------------------------------------------------------
# Loading the closed population's checkpoints
# --------------------------------------------------------------------------------------------

def load_entries(members, b15i_path=B15I_DB):
    """B15i entry checkpoints for the member launches. Same shape B15L and B15M already consume."""
    signatures = {member["signature"] for member in members}
    connection = _read_only(b15i_path, "B15i")
    try:
        rows = connection.execute(
            "SELECT t.signature, t.delay_slots, t.bonding_curve, o.mint, t.context_slot, "
            "t.lateness_slots, t.virtual_quote, t.virtual_token, t.real_quote, t.real_token, "
            "t.quote_mint, t.mayhem_mode, t.complete "
            "FROM target t JOIN observation o ON o.signature = t.signature "
            "WHERE t.state='captured' AND o.fork_state='confirmed'").fetchall()
    except sqlite3.Error as error:
        raise ReplicationRefused(
            f"{O_EVIDENCE_INSUFFICIENT}: cannot read B15i's entry checkpoints: {error}") from error
    finally:
        connection.close()
    fields = ("signature", "delay_slots", "bonding_curve", "mint", "context_slot",
              "lateness_slots", "virtual_quote", "virtual_token", "real_quote", "real_token",
              "quote_mint", "mayhem_mode", "complete")
    entries = {}
    for row in rows:
        record = dict(zip(fields, row))
        if record["signature"] not in signatures:
            continue
        record["mayhem_mode"] = bool(record["mayhem_mode"])
        record["complete"] = bool(record["complete"])
        entries[(record["signature"], record["delay_slots"])] = record
    return entries


def load_exits(members, b15n_path=B15N_DB):
    """B15N exit checkpoints for the member launches, keyed exactly as B15L and B15M expect.

    Only ADMISSIBLE rows: a checkpoint whose launch has no explicit chain confirmation is recorded by
    B15N and withheld, and this study honours that rather than quietly widening it.
    """
    signatures = {member["signature"] for member in members}
    connection = _read_only(b15n_path, "B15N")
    try:
        rows = connection.execute(
            "SELECT c.signature, c.delay_slots, c.horizon, s.bonding_curve, s.mint, "
            "c.context_slot, c.lateness_slots, c.virtual_quote, c.virtual_token, c.real_quote, "
            "c.real_token, c.quote_mint, c.mayhem_mode, c.complete, c.fork_state_at_read, "
            "c.chain_verdict FROM checkpoint c JOIN schedule s ON s.signature = c.signature "
            "AND s.delay_slots = c.delay_slots AND s.horizon = c.horizon").fetchall()
    except sqlite3.Error as error:
        raise ReplicationRefused(
            f"{O_EVIDENCE_INSUFFICIENT}: cannot read B15N's exit checkpoints: {error}") from error
    finally:
        connection.close()
    fields = ("signature", "delay_slots", "horizon", "bonding_curve", "mint", "context_slot",
              "lateness_slots", "virtual_quote", "virtual_token", "real_quote", "real_token",
              "quote_mint", "mayhem_mode", "complete", "fork_state_at_read", "chain_verdict")
    exits, withheld = {}, 0
    for row in rows:
        record = dict(zip(fields, row))
        if record["signature"] not in signatures:
            continue
        if not B15N.admissible_downstream(record["fork_state_at_read"], record["chain_verdict"]):
            withheld += 1
            continue
        record["mayhem_mode"] = bool(record["mayhem_mode"])
        record["complete"] = bool(record["complete"])
        exits[(record["signature"], record["delay_slots"], record["horizon"])] = record
    return exits, withheld


# --------------------------------------------------------------------------------------------
# The published operands — read from their committed findings so they cannot drift
# --------------------------------------------------------------------------------------------

PUBLISHED = {
    "b15l": ROOT / "research" / "B15L_COUNTERFACTUAL_FINDING.md",
    "b15m": ROOT / "research" / "B15M_LIQUIDITY_CAPACITY_FINDING.md",
}


def published_operand(key):
    """The V1 figures, read from the committed finding rather than retyped here.

    A number retyped into this module could drift from what was published; reading the document
    means the comparison operand is the published one by construction.
    """
    path = PUBLISHED[key]
    if not path.exists():
        raise ReplicationRefused(
            f"{O_PUBLISHED_FIGURE_MISSING}: {path} is absent, so there is nothing to compare against")
    return {"document": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "note": "the V1 operand is this committed document; figures are quoted from it and not "
                    "retyped into code"}


# --------------------------------------------------------------------------------------------
# Materialization — exactly once
# --------------------------------------------------------------------------------------------

def artifact_path(work_dir=WORK_DIR):
    return pathlib.Path(work_dir) / "replication.json"


def materialize(work_dir=WORK_DIR, b15i_path=B15I_DB, b15n_path=B15N_DB, document=None,
                current_slot=None, force_recompute=False, schedules=None):
    """Draw, replicate both studies verbatim, write once. Refuses while the population is locked."""
    assert_no_execution_surface()
    assert_no_forbidden_source()
    document = verify_preregistration() if document is None else document
    target = artifact_path(work_dir)
    if target.exists() and not force_recompute:
        # Reported, never recomputed: a second run that produced a different number would mean the
        # study had two answers.
        return {"already_materialized": True, "artifact": str(target),
                "report": json.loads(target.read_text()),
                "note": f"{O_ALREADY_MATERIALIZED}: the existing artifact is reported rather than "
                        f"recomputed, so no output can differ between readings"}
    closure = assert_closed(b15n_path, document, current_slot)
    assert_membership_stable(b15n_path, document)
    members, total = draw_members(b15n_path, document=document)
    entries = load_entries(members, b15i_path)
    exits, withheld = load_exits(members, b15n_path)
    # Decoded from the launch transactions, exactly as B15L does. Injectable only so a synthetic
    # fixture can reach the gates that lie BEYOND the fee-schedule check.
    if schedules is None:
        schedules = B15L.fee_schedules({member["signature"] for member in members})

    counterfactual = B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules,
                              validate_rule=True)
    capacity = B15M.run(entries=entries, exits=exits, schedules=schedules)
    report = {
        "schema_version": SCHEMA_VERSION, "label": LABEL, "executable": False,
        "performance_status": "not_evaluated", "execution_status": "never_executed",
        "population": {
            "size_required": document["the_closed_population"]["size"],
            "members": len(members), "distinct_launches_available": total,
            "first_member": members[0], "last_member": members[-1],
            "canonical_order": "t0_slot, signature, mint",
            "entry_checkpoints": len(entries), "exit_checkpoints": len(exits),
            "exit_checkpoints_withheld_pending_confirmation": withheld,
            "fee_schedules": len(schedules)},
        "closure": closure,
        "replicated": {"b15l_counterfactual": counterfactual, "b15m_capacity": capacity},
        "published_operands": {key: published_operand(key) for key in PUBLISHED},
        "comparison": {
            "nature": "DESCRIPTIVE ONLY",
            "no_pass_threshold": "no tolerance, agreement criterion, verdict or hypothesis test "
                                 "exists in this study",
            "no_pooling": "the two populations are never combined, averaged or presented as one",
            "quantities": document["predeclared_comparison"][
                "quantities_compared_and_fixed_here"]},
        "materialized_at_wall_unix": time.time(),
    }
    B15L.assert_no_forbidden_words(report["replicated"]["b15l_counterfactual"])
    B15M.assert_no_forbidden_words(report["replicated"]["b15m_capacity"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True))
    return {"already_materialized": False, "artifact": str(target), "report": report}


def status(work_dir=WORK_DIR, b15n_path=B15N_DB, document=None, current_slot=None):
    """Locked or closed, and what remains. No estimand quantity while locked."""
    document = verify_preregistration() if document is None else document
    target = artifact_path(work_dir)
    state = closure_state(b15n_path, document, current_slot)
    state["materialized"] = target.exists()
    state["artifact"] = str(target) if target.exists() else None
    state["reports_no_estimand_while_locked"] = True
    return state


def watch(work_dir=WORK_DIR, b15i_path=B15I_DB, b15n_path=B15N_DB, poll_seconds=300, ticks=None,
          slot_source=None, sleeper=time.sleep, opener=None, document=None, schedules=None):
    """Report locked until the gate opens, then materialize exactly once and keep reporting.

    Read-only against the chain: one getSlot per poll, and nothing else. The evidence it replicates
    is already on disk, which is why no other network call appears here.
    """
    assert_no_execution_surface()
    assert_no_forbidden_source()
    # The document is a PARAMETER, defaulting to the verified freeze. Without it the watcher
    # verified its own copy and ignored the caller's, so no fixture could exercise it past closure —
    # the one behaviour a watcher exists to perform.
    document = verify_preregistration() if document is None else document
    url = None
    tick = 0
    last = None
    while ticks is None or tick < ticks:
        if tick:
            sleeper(poll_seconds)
        tick += 1
        # ONE protected path for both sources. Guarding only the real call left the injected seam
        # behaving differently from production, which is how a test comes to exercise something the
        # deployed code does not do.
        try:
            if slot_source is not None:
                current = slot_source()
            else:
                url = url or B15N.B15B.rpc_url()
                current = B15F.current_slot(url, opener)
        except Exception as error:                                        # noqa: BLE001
            # A transient endpoint fault must not end a watcher whose whole job is to wait.
            last = {"label": LABEL, "locked": True, "slot_unavailable": True,
                    "error": f"{type(error).__name__}: {error}"[:200]}
            print(json.dumps(last, sort_keys=True), flush=True)
            continue
        try:
            outcome = materialize(work_dir, b15i_path, b15n_path, document, current,
                                  schedules=schedules)
            last = {"label": LABEL, "locked": False, "materialized": True,
                    "artifact": outcome["artifact"],
                    "already_materialized": outcome["already_materialized"]}
        except ReplicationRefused as error:
            last = status(work_dir, b15n_path, document, current)
            last["refusal"] = str(error)[:300]
        print(json.dumps(last, sort_keys=True), flush=True)
    return last


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B15o closed-population replication (offline, read-only, no strategy figure "
                    "while locked)")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--ticks", type=int, default=None)
    arguments = parser.parse_args(argv)
    current = None
    try:
        current = B15F.current_slot(B15N.B15B.rpc_url())
    except Exception:                                                     # noqa: BLE001
        current = None
    if arguments.watch:
        watch(poll_seconds=arguments.poll_seconds, ticks=arguments.ticks)
        return 0
    if arguments.status:
        print(json.dumps(status(current_slot=current), indent=2, sort_keys=True))
        return 0
    try:
        outcome = materialize(current_slot=current)
    except ReplicationRefused as error:
        print(json.dumps({"refused": str(error), "status": status(current_slot=current)},
                         indent=2, sort_keys=True))
        return 1
    print(json.dumps(outcome["report"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
