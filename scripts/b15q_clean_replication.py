"""B15q — B15L and B15M on the frozen 5,000, with fee schedules from each launch's own transaction.

Implements `research/B15Q_CLEAN_REPLICATION_PREREGISTRATION.json`, committed alone while B15P was
still incomplete and before any strategy quantity here was read.

**B15O is not touched.** Its zero-priced-cell result is the record of what a population without fee
schedules yields, and deleting it would delete the finding. B15Q is a new artifact beside it.

**B15L and B15M are imported and their closures are dirty.** They transitively load
`b15a_shadow_pilot`, `b15b_backfill` and `b15f_checkpoint`. That is admissible here only because
every input reaches them by INJECTION as in-memory mappings, so neither opens an artifact, and
`B15L.fee_schedules` — the function that reads B15b's exchange log, and the direct cause of B15O's
empty result — is never called. The runtime path guard wraps the whole materialization, so a
forbidden open would refuse on the spot rather than be discovered later.

**A missing t0 fee schedule is coverage, not failure, and is never filled.** About 17% of members
publish no fee basis points in their launch transaction. Taking the fee in force at a later trade
would price the entry with a number that could only be known after the decision instant.
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

WORK_DIR = ROOT / "research" / "b15q"
ARTIFACT = WORK_DIR / "replication.json"

B15O_ARTIFACT = ROOT / "research" / "b15o" / "replication.json"
B15I_DB = ROOT / "research" / "b15i" / "processed_feed.sqlite"
B15N_DB = ROOT / "research" / "b15n" / "exit_checkpoints.sqlite"
B15P_DIR = ROOT / "research" / "b15p"

PREREG_PATH = ROOT / "research" / "B15Q_CLEAN_REPLICATION_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "cebdea05a7b389b53f6915ec086416933e5593f0906bd3916a70057cd22384e7"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

Q_B15P_INCOMPLETE = "Q_B15P_INCOMPLETE"
Q_B15P_MANIFEST_FAILED = "Q_B15P_MANIFEST_FAILED"
Q_HASH_DRIFT = "Q_HASH_DRIFT"
Q_MEMBER_SET_DRIFT = "Q_MEMBER_SET_DRIFT"
Q_FORBIDDEN_DEPENDENCY = "Q_FORBIDDEN_DEPENDENCY"
Q_NO_T0_FEE_SCHEDULE = "Q_NO_T0_FEE_SCHEDULE"
Q_FUTURE_LEAKAGE = "Q_FUTURE_LEAKAGE"
Q_SCHEDULE_NOT_UNIQUE = "Q_SCHEDULE_NOT_UNIQUE"
Q_JOIN_IDENTITY = "Q_JOIN_IDENTITY"
Q_EVIDENCE_INSUFFICIENT = "Q_EVIDENCE_INSUFFICIENT"
Q_ALREADY_MATERIALIZED = "Q_ALREADY_MATERIALIZED"

LABEL = "CLEAN_CLOSED_REPLICATION"

PUBLISHED = {
    "b15l_v1": ROOT / "research" / "B15L_COUNTERFACTUAL_FINDING.md",
    "b15m_v1": ROOT / "research" / "B15M_LIQUIDITY_CAPACITY_FINDING.md",
    "b15o": B15O_ARTIFACT,
}


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15P = _load("b15p_native_fee_backfill", "b15p_native_fee_backfill.py")
B15L = _load("b15l_counterfactual_roundtrip", "b15l_counterfactual_roundtrip.py")
B15M = _load("b15m_liquidity_capacity", "b15m_liquidity_capacity.py")


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
        raise ReplicationRefused(f"the B15Q preregistration hashes {actual}, pinned {expected}")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    text = path.read_text()
    marker = "EXECUTION_SURFACE_TOKENS = ("
    body = text.split(marker, 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise ReplicationRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def verify_bound_hashes(document=None, artifact_path=B15O_ARTIFACT):
    """Every bound document, by canonical hash. Drift stops the study."""
    document = verify_preregistration() if document is None else document
    bound = document["bound_hashes"]
    drift = {}
    actual = hashlib.sha256(pathlib.Path(artifact_path).read_bytes()).hexdigest()
    if actual != bound["b15o_artifact_sha256"]:
        drift["b15o_artifact"] = {"actual": actual, "bound": bound["b15o_artifact_sha256"]}
    for key, name in (("b15p_preregistration_canonical_sha256",
                       "B15P_NATIVE_FEE_BACKFILL_PREREGISTRATION.json"),
                      ("b15l_preregistration_canonical_sha256",
                       "B15L_COUNTERFACTUAL_ROUNDTRIP_PREREGISTRATION.json"),
                      ("b15m_preregistration_canonical_sha256",
                       "B15M_LIQUIDITY_CAPACITY_PREREGISTRATION.json")):
        source = json.loads((ROOT / "research" / name).read_bytes())
        computed = hashlib.sha256(
            json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if computed != bound[key]:
            drift[name] = {"actual": computed, "bound": bound[key]}
    if drift:
        raise ReplicationRefused(f"{Q_HASH_DRIFT}: {drift}")
    return True


def assert_dependencies_declared(document=None):
    """B15P's static closure audit, over THIS module. Every forbidden reference must be declared.

    B15L and B15M carry dirty closures by construction, so the static audit cannot come back clean
    here as it did for B15P. What it can do is refuse anything undeclared, and leave the decisive
    check to the runtime guard.
    """
    document = verify_preregistration() if document is None else document
    findings = {}
    for name in sorted(B15P.module_closure("b15q_clean_replication.py")):
        path = ROOT / "scripts" / name
        if not path.exists():
            continue
        declared_here = B15P._declared_token_literals(path)
        literals = [value for value in B15P.code_string_constants(path)
                    if value not in declared_here]
        hits = sorted({token for token in B15P.FORBIDDEN_DIRECTORY_TOKENS
                       if any(token == value or f"/{token}/" in value or
                              value.endswith(f"/{token}") for value in literals)})
        if hits:
            findings[name] = hits
    expected = set(document["inputs"][
        "b15l_and_b15m_are_imported_and_their_closures_are_dirty"].keys())
    if "declared_manifest_required" not in expected:
        raise ReplicationRefused(
            f"{Q_FORBIDDEN_DEPENDENCY}: the freeze declares no manifest requirement")
    # Every finding must be a module the freeze anticipated: the B15L/B15M families only.
    permitted_prefixes = ("b15a_", "b15b_", "b15c_", "b15d_", "b15e_", "b15f_", "b15g_",
                          "b15h_", "b15j_", "b15l_", "b15m_")
    undeclared = {name: hits for name, hits in findings.items()
                  if not name.startswith(permitted_prefixes)}
    if undeclared:
        raise ReplicationRefused(
            f"{Q_FORBIDDEN_DEPENDENCY}: undeclared forbidden references {undeclared}; the freeze "
            f"anticipates only the B15L and B15M families")
    return {"forbidden_references": findings, "all_declared": True,
            "decisive_check": "the runtime path guard"}


def assert_fee_schedules_reader_never_called(path=None):
    """B15L.fee_schedules reads B15b's exchange log and is the direct cause of B15O's empty result."""
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    source = path.read_text()
    marker = "def assert_fee_schedules_reader_never_called"
    body = source.split(marker, 1)[-1]
    body = body.split("\ndef ", 1)[-1] if "\ndef " in body else body
    for token in ("B15L.fee_schedules(", "fee_schedules_from_launch_transactions("):
        if token in source.split(marker)[0] or token in body:
            raise ReplicationRefused(
                f"{Q_FORBIDDEN_DEPENDENCY}: this study calls {token}, which reads a closed "
                f"recorder and is the direct cause of B15O's empty result")
    return True


def _read_only(path, label):
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error as error:
        raise ReplicationRefused(
            f"{Q_EVIDENCE_INSUFFICIENT}: no readable {label} artifact at {path}: {error}") from error


# --------------------------------------------------------------------------------------------
# The B15P gate — complete, and its schedules still derivable from raw
# --------------------------------------------------------------------------------------------

def b15p_state(b15p_dir=B15P_DIR, expected=None):
    """Whether B15P is complete, and exactly what is missing. Computes no strategy quantity.

    `expected` is the size of the roster re-derived under the B15O artifact's own ordering rule, and
    not a literal 5,000: a gate that counted against a hardcoded number would report a roster of any
    other size as complete the moment it reached 5,000 terminal records, or never at all. An expected
    size that could not be derived is INCOMPLETE, because unknown is not complete.
    """
    path = pathlib.Path(b15p_dir) / "fee_schedules.sqlite"
    state = {"complete": False, "reasons": [Q_B15P_INCOMPLETE], "terminal": 0,
             "members": expected, "remaining": None}
    if expected is None:
        state["detail"] = ("the roster size could not be derived from the B15O artifact, so "
                           "completeness is unknown; unknown is not complete")
        return state
    if not path.exists():
        state["detail"] = "B15P has not started"
        state["remaining"] = expected
        return state
    connection = _read_only(path, "B15P")
    try:
        states = dict(connection.execute(
            "SELECT state, COUNT(*) FROM fee_schedule GROUP BY state"))
        reasons = dict(connection.execute(
            "SELECT substr(reason,1,instr(reason||':',':')-1), COUNT(*) FROM fee_schedule "
            "WHERE reason IS NOT NULL GROUP BY 1"))
    finally:
        connection.close()
    terminal = sum(count for state, count in states.items()
                   if state in B15P.TERMINAL_STATES)
    state.update({"complete": terminal >= expected, "terminal": terminal, "states": states,
                  "b15p_refusals": reasons, "remaining": max(0, expected - terminal)})
    state["reasons"] = [] if state["complete"] else [Q_B15P_INCOMPLETE]
    return state


def verify_b15p_manifest(b15p_dir=B15P_DIR):
    """B15P's own completeness and replay gate, run here rather than trusted.

    A count says every member was attempted; the replay says every schedule kept can still be
    derived from the evidence it came from. A backfill can be complete and wrong.
    """
    try:
        return B15P.assert_complete_and_replayable(pathlib.Path(b15p_dir))
    except B15P.BackfillRefused as error:
        raise ReplicationRefused(f"{Q_B15P_MANIFEST_FAILED}: {error}") from error


def load_fee_schedules(b15p_dir=B15P_DIR):
    """One schedule per member, from that member's OWN launch transaction. Nothing is filled in.

    Only rows B15P recorded `retrieved`. A member refused for want of a TradeEvent has no schedule
    here and gains one from nowhere: the fee in force at a later trade is evidence from after the
    decision instant.
    """
    path = pathlib.Path(b15p_dir) / "fee_schedules.sqlite"
    connection = _read_only(path, "B15P")
    try:
        # One schedule per member is guaranteed by B15P's store, not by a scan here: `signature` is
        # the table's primary key, so a second row could never have been written and a duplicate
        # check over the rows could never fire. What CAN be checked, and is, is that the guarantee is
        # still in force — if the key were ever dropped, this reader could no longer establish
        # uniqueness and must refuse rather than assume it.
        declaration = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='fee_schedule'").fetchone()
        normalized = " ".join((declaration[0] if declaration else "").split()).lower()
        if "signature text primary key" not in normalized:
            raise ReplicationRefused(
                f"{Q_SCHEDULE_NOT_UNIQUE}: B15P's fee_schedule table no longer declares signature "
                f"as its primary key, so one schedule per member is not guaranteed by the store")
        rows = connection.execute(
            "SELECT signature, fee_bps, creator_fee_bps, cashback_fee_bps, buyback_fee_bps, "
            "state, reason FROM fee_schedule").fetchall()
    finally:
        connection.close()
    schedules, unavailable = {}, {}
    for signature, fee, creator, cashback, buyback, state, reason in rows:
        if state != B15P.STATE_RETRIEVED:
            code = (reason or "").split(":", 1)[0] or state
            unavailable[signature] = code
            continue
        schedules[signature] = {"fee_bps": fee, "creator_fee_bps": creator,
                                "cashback_fee_bps": cashback, "buyback_fee_bps": buyback}
    return schedules, unavailable


def assert_no_future_leakage(schedules, members, b15p_dir=B15P_DIR):
    """Every schedule must belong to a member and come from B15P's retrieved rows only.

    A schedule for a signature that is not a member, or one present here while B15P refused it,
    could only have arrived from somewhere other than that member's own launch transaction.
    """
    roster = {member["signature"] for member in members}
    strays = sorted(set(schedules) - roster)
    if strays:
        raise ReplicationRefused(
            f"{Q_FUTURE_LEAKAGE}: {len(strays)} schedules belong to no member, for example "
            f"{strays[:3]}; a schedule may come only from the member's own launch transaction")
    path = pathlib.Path(b15p_dir) / "fee_schedules.sqlite"
    connection = _read_only(path, "B15P")
    try:
        retrieved = {row[0] for row in connection.execute(
            "SELECT signature FROM fee_schedule WHERE state=?", (B15P.STATE_RETRIEVED,))}
    finally:
        connection.close()
    invented = sorted(set(schedules) - retrieved)
    if invented:
        raise ReplicationRefused(
            f"{Q_FUTURE_LEAKAGE}: {len(invented)} schedules are not among B15P's retrieved rows, "
            f"for example {invented[:3]}; they were filled from outside the launch transaction")
    return True


# --------------------------------------------------------------------------------------------
# The joined population
# --------------------------------------------------------------------------------------------

def load_entries(members, b15i_path=B15I_DB):
    signatures = {member["signature"] for member in members}
    connection = _read_only(b15i_path, "B15i")
    try:
        rows = connection.execute(
            "SELECT t.signature, t.delay_slots, t.bonding_curve, o.mint, t.context_slot, "
            "t.lateness_slots, t.virtual_quote, t.virtual_token, t.real_quote, t.real_token, "
            "t.quote_mint, t.mayhem_mode, t.complete "
            "FROM target t JOIN observation o ON o.signature = t.signature "
            "WHERE t.state='captured' AND o.fork_state='confirmed'").fetchall()
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


def admissible_exit(fork_state_at_read, chain_verdict):
    """Only an explicitly chain-confirmed launch. Absence of confirmation is never confirmation.

    The criterion is stated in this study's own freeze — a checkpoint is withheld while its launch is
    unconfirmed — and applied here rather than by importing B15N, whose module carries bare
    forbidden-directory literals in its own isolation guard and would therefore have to be declared
    as a dependency it is not. A test cross-checks this against B15N's predicate on every state
    combination, so the two cannot drift apart unnoticed.
    """
    return fork_state_at_read == "confirmed" or chain_verdict == "confirmed"


def load_exits(members, b15n_path=B15N_DB):
    """Admissible exit checkpoints only: B15N withholds an unconfirmed launch's, and so does this."""
    signatures = {member["signature"] for member in members}
    connection = _read_only(b15n_path, "B15N")
    try:
        rows = connection.execute(
            "SELECT c.signature, c.delay_slots, c.horizon, s.bonding_curve, s.mint, "
            "c.context_slot, c.lateness_slots, c.virtual_quote, c.virtual_token, c.real_quote, "
            "c.real_token, c.quote_mint, c.mayhem_mode, c.complete, c.fork_state_at_read, "
            "c.chain_verdict FROM checkpoint c JOIN schedule s ON s.signature = c.signature "
            "AND s.delay_slots = c.delay_slots AND s.horizon = c.horizon").fetchall()
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
        if not admissible_exit(record["fork_state_at_read"], record["chain_verdict"]):
            withheld += 1
            continue
        record["mayhem_mode"] = bool(record["mayhem_mode"])
        record["complete"] = bool(record["complete"])
        exits[(record["signature"], record["delay_slots"], record["horizon"])] = record
    return exits, withheld


def assert_join_identity(entries, exits):
    """An entry and an exit for one member must name the same curve and mint."""
    mismatched = []
    for (signature, delay, _horizon), exit_state in exits.items():
        entry = entries.get((signature, delay))
        if entry is None:
            continue
        if entry["bonding_curve"] != exit_state["bonding_curve"] or \
                entry["mint"] != exit_state["mint"]:
            mismatched.append(signature)
    if mismatched:
        raise ReplicationRefused(
            f"{Q_JOIN_IDENTITY}: {len(mismatched)} cells join an entry and an exit that name "
            f"different curves or mints, for example {mismatched[:3]}")
    return True


# --------------------------------------------------------------------------------------------
# Materialization — locked until B15P is complete, then exactly once
# --------------------------------------------------------------------------------------------

TRUTHFUL_CENSORING = (
    "conditioned on B15O's frozen 5,000 launches, which descend from B15i's own observations and "
    "from no closed recorder; a cell is absent when its B15i entry checkpoint is missing, when its "
    "B15N exit checkpoint is missing or withheld pending chain confirmation, or when its launch "
    "transaction published no fee basis points at t0 and therefore has no admissible fee schedule")


def correct_censoring(block, document=None):
    """Replace the inherited censoring prose, PRESERVING the false one rather than deleting it.

    B15L and B15M say the population is censored because B15f schedules from B15a. For this
    population that is false — it descends from neither. Their own documents are not edited: their
    prose is correct for the population they ran on, and correcting a finished study retroactively is
    not a correction. So the inherited sentence is kept, marked false, and superseded in place.
    """
    document = verify_preregistration() if document is None else document
    corrected = dict(block)
    inherited = corrected.get("censoring_statement")
    if inherited is not None:
        corrected["inherited_censoring_statement_superseded"] = {
            "statement": inherited,
            "false_for_this_population": True,
            "why": "it names B15f scheduling from B15a; the B15Q population descends from neither"}
    corrected["censoring_statement"] = document["the_censoring_statement_is_corrected"][
        "the_truthful_statement"]
    return corrected


def published_operands(published=None):
    """The comparison operands, by sha256, so none of them can drift."""
    out = {}
    for key, path in (PUBLISHED if published is None else published).items():
        if not path.exists():
            raise ReplicationRefused(
                f"{Q_EVIDENCE_INSUFFICIENT}: the operand {path} is absent, so there is nothing to "
                f"compare against")
        out[key] = {"document": str(path.relative_to(ROOT)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return out


def lock_state(document=None, artifact_path=B15O_ARTIFACT, b15n_path=B15N_DB, b15p_dir=B15P_DIR,
               work_dir=WORK_DIR):
    """Locked or not, and what remains. NO strategy quantity while B15P is incomplete."""
    document = verify_preregistration() if document is None else document
    state = {"label": LABEL, "locked": True, "reasons": [],
             "reports_no_strategy_quantity_while_locked": True}
    try:
        verify_bound_hashes(document, artifact_path)
    except ReplicationRefused as error:
        state["reasons"].append(str(error).split(":", 1)[0])
        state["hash_drift"] = str(error)[:240]
    try:
        members, meta = B15P.load_members(
            json.loads(json.dumps(B15P.verify_preregistration())), artifact_path, b15n_path)
        state["members"] = len(members)
        state["member_set_sha256"] = meta["member_set_sha256"]
        if meta["member_set_sha256"] != document["bound_hashes"]["member_set_sha256"]:
            state["reasons"].append(Q_MEMBER_SET_DRIFT)
    except B15P.BackfillRefused as error:
        state["reasons"].append(Q_MEMBER_SET_DRIFT)
        state["member_set_error"] = str(error)[:240]
    # Counted against the roster actually derived from the bound artifact, never against a literal.
    backfill = b15p_state(b15p_dir, state.get("members"))
    state["b15p"] = backfill
    state["reasons"].extend(backfill["reasons"])
    state["materialized"] = (pathlib.Path(work_dir) / "replication.json").exists()
    state["locked"] = bool(state["reasons"])
    return state


def materialize(work_dir=WORK_DIR, document=None, artifact_path=B15O_ARTIFACT, b15i_path=B15I_DB,
                b15n_path=B15N_DB, b15p_dir=B15P_DIR, force_recompute=False, verify_manifest=True):
    """Replicate both studies on the frozen 5,000 and write once. Refuses while B15P is incomplete."""
    assert_no_execution_surface()
    assert_fee_schedules_reader_never_called()
    document = verify_preregistration() if document is None else document
    audit = assert_dependencies_declared(document)
    target = pathlib.Path(work_dir) / "replication.json"
    if target.exists() and not force_recompute:
        return {"already_materialized": True, "artifact": str(target),
                "report": json.loads(target.read_text()),
                "note": f"{Q_ALREADY_MATERIALIZED}: the existing artifact is reported rather than "
                        f"recomputed, so no two readings can differ"}
    state = lock_state(document, artifact_path, b15n_path, b15p_dir, work_dir)
    if state["locked"]:
        raise ReplicationRefused(
            f"{state['reasons'][0]}: the study is locked ({state['reasons']}); B15P has "
            f"{state['b15p']['terminal']} of {state['b15p']['members']} members terminal")
    manifest = verify_b15p_manifest(b15p_dir) if verify_manifest else {"skipped": True}

    members, meta = B15P.load_members(
        json.loads(json.dumps(B15P.verify_preregistration())), artifact_path, b15n_path)
    schedules, unavailable = load_fee_schedules(b15p_dir)
    assert_no_future_leakage(schedules, members, b15p_dir)
    entries = load_entries(members, b15i_path)
    exits, withheld = load_exits(members, b15n_path)
    assert_join_identity(entries, exits)

    counterfactual = correct_censoring(
        B15L.run(b15i_path=entries, b15f_path=exits, schedules=schedules, validate_rule=True),
        document)
    capacity = correct_censoring(
        B15M.run(entries=entries, exits=exits, schedules=schedules), document)

    report = {
        "schema_version": SCHEMA_VERSION, "label": LABEL, "executable": False,
        "performance_status": "not_evaluated", "execution_status": "never_executed",
        "population": {
            "members": len(members), "member_set_sha256": meta["member_set_sha256"],
            "first_member": members[0], "last_member": members[-1],
            "entry_checkpoints": len(entries), "exit_checkpoints": len(exits),
            "exit_checkpoints_withheld_pending_confirmation": withheld,
            "fee_schedules": len(schedules),
            "members_without_a_t0_fee_schedule": len(unavailable),
            "members_without_a_t0_fee_schedule_share_pct":
                (100 * len(unavailable)) // len(members) if members else None,
            "t0_fee_unavailable_by_reason": {
                code: sum(1 for value in unavailable.values() if value == code)
                for code in sorted(set(unavailable.values()))},
            "t0_fee_unavailability_is_coverage_not_failure": (
                "these launches published no fee basis points in their own launch transaction, so no "
                "retry can supply one; a fee from a later trade would be evidence from after the "
                "decision instant and is never used")},
        "b15p_manifest": manifest,
        "dependency_audit": audit,
        "replicated": {"b15l_counterfactual": counterfactual, "b15m_capacity": capacity},
        "published_operands": published_operands(),
        "comparison": {
            "nature": "DESCRIPTIVE ONLY",
            "no_pass_threshold": "no tolerance, agreement criterion or hypothesis test exists here",
            "no_pooling": "the populations are never combined, averaged or presented as one",
            "operands": ["B15L V1", "B15M V1", "B15O (zero priced cells)"],
            "quantities": document["predeclared_comparison"][
                "quantities_compared_and_fixed_here"]},
        "b15o_is_untouched": "B15O is a separate artifact and is neither edited, replaced nor re-run",
        "materialized_at_wall_unix": time.time(),
    }
    B15L.assert_no_forbidden_words(report["replicated"]["b15l_counterfactual"])
    B15M.assert_no_forbidden_words(report["replicated"]["b15m_capacity"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True))
    return {"already_materialized": False, "artifact": str(target), "report": report}


def status(work_dir=WORK_DIR, document=None, artifact_path=B15O_ARTIFACT, b15n_path=B15N_DB,
           b15p_dir=B15P_DIR):
    document = verify_preregistration() if document is None else document
    state = lock_state(document, artifact_path, b15n_path, b15p_dir, work_dir)
    target = pathlib.Path(work_dir) / "replication.json"
    state["artifact"] = str(target) if target.exists() else None
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B15q clean closed replication (offline, read-only, locked until B15P completes)")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--audit", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.audit:
        print(json.dumps(assert_dependencies_declared(), indent=2, sort_keys=True))
        return 0
    if arguments.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
        return 0
    # The runtime path guard wraps the whole materialization: a forbidden open refuses on the spot.
    try:
        with B15P.PathGuard() as guard:
            outcome = materialize()
    except ReplicationRefused as error:
        print(json.dumps({"refused": str(error), "status": status()}, indent=2, sort_keys=True))
        return 1
    outcome["report"]["runtime_paths_opened"] = len(guard.opened)
    print(json.dumps(outcome["report"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
