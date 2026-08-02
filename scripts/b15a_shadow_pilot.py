"""B15a — the live Pump launch shadow pilot. Observes, records, and proposes nothing real.

Implements `research/B15A_SHADOW_PILOT_PREREGISTRATION.json`, which was committed alone before this
file existed. The pilot subscribes to public log notifications, preserves every frame exactly as
delivered, decodes Pump CreateEvents with the pinned IDL, optionally backfills the launch
transaction, and records what the frozen B11b P1 policy would HYPOTHETICALLY have proposed.

It cannot sign, cannot construct a transaction, cannot submit one, and cannot spend. Those are not
merely absent — `assert_no_execution_surface` refuses at startup if this file has grown any of
them, and a test greps for the same thing.

**This is not Geyser fidelity.** Orphan signals, account updates and slot-dead notifications are
structurally absent from this feed, so every count here is a lower bound.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import signal
import sqlite3
import sys
import time
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15a"
RAW_PATH = WORK_DIR / "raw_frames.jsonl"
DB_PATH = WORK_DIR / "shadow.sqlite"
LOCK_PATH = WORK_DIR / "pilot.lock"
LOG_DIR = WORK_DIR / "logs"

PREREG_PATH = ROOT / "research" / "B15A_SHADOW_PILOT_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "0622ba86bd108c7b3f915da81477291c4780affeada9199b823d749c61a71c03"

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EVENT_TAG = bytes.fromhex("e445a52e51cb9a1d")
PROGRAM_DATA_PREFIX = "Program data: "

RPC_ENV_VAR = "SOLANA_RPC_URL"
DEFAULT_COMMITMENT = "confirmed"
PERMITTED_COMMITMENTS = ("processed", "confirmed")

HEARTBEAT_SECONDS = 30
RECONNECT_BACKOFF_SECONDS = (1, 2, 5, 10, 30, 60)

# Paths this pilot may never touch. The frozen corpus and the running collection are out of reach.
FORBIDDEN_PATH_MARKERS = ("research/b11a", "b9a_outcomes", "b9c_signature_inventory",
                          "b9d_transaction_bodies", "b10b_observed_paths")

# Names that would mean an execution surface had appeared here. Checked against this file's own
# source at startup, because "we simply did not write that" stops being true the moment somebody
# writes it.
EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop")

# --------------------------------------------------------------------------------------------
# Populations. The single most important distinction in this module.
#
# A LAUNCH CANDIDATE is a payload whose discriminator IS the CreateEvent discriminator. It either
# decoded or it did not, and either way a launch was observed.
#
# A NON-LAUNCH EVENT is any other Pump event — overwhelmingly TradeEvent — or a payload too short
# to carry a discriminator at all. It is preserved and counted, and it NEVER advances the
# preregistered launch quota.
#
# Conflating them is not a cosmetic error. The frozen stopping rule ends the pilot after 5,000
# observed launches; counting trades as launches ended a 72-hour pilot in minutes, and the census
# said 814 launches when four had been seen.
LAUNCH_CANDIDATE_STATUSES = ("decoded", "decode_failed")
NON_LAUNCH_STATUSES = ("unknown_event", "not_a_create")

DECODE_DECODED = "decoded"
DECODE_UNKNOWN = "unknown_event"
DECODE_FAILED = "decode_failed"
DECODE_NOT_CREATE = "not_a_create"

RESULT_PROPOSED = "shadow_entry_proposed"
RESULT_NO_ENTRY = "no_shadow_entry"

S01_FEED_ONLY_NO_RESERVES = "S01_feed_only_no_reserves"
S02_BACKFILL_UNAVAILABLE = "S02_backfill_unavailable"
S03_DECODE_INCOMPLETE = "S03_decode_incomplete"
S04_VETO = "S04_veto"
S05_RISK_GOVERNOR_REJECTED = "S05_risk_governor_rejected"
S06_STALE_OBSERVATION = "S06_stale_observation"
S07_SESSION_DEGRADED = "S07_session_degraded"
S08_OUTSIDE_PILOT_WINDOW = "S08_outside_pilot_window"

END_STOPPING_RULE = "stopping_rule_reached"
END_OPERATOR_STOP = "operator_stop"
END_FAULT = "fault"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WS = _load("b15a_websocket", "b15a_websocket.py")
B11B = _load("b11b_t0_features", "b11b_t0_features.py")


class PilotRefused(RuntimeError):
    """The pilot will not do what it was asked, and stops rather than improvising."""


# --------------------------------------------------------------------------------------------
# Startup gates
# --------------------------------------------------------------------------------------------

def assert_no_execution_surface(path=None):
    """This file may not contain the machinery to sign, build or submit a transaction.

    Checked against the source rather than asserted in a comment. "We simply did not write that"
    is true until somebody writes it, and this is the moment to find out.
    """
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    source = path.read_text()
    body = source.split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise PilotRefused(
            f"an execution surface appeared in {path.name}: {found}. This pilot observes and "
            "records; it does not hold keys, sign, build or submit anything")
    return True


def assert_isolated(work_dir=WORK_DIR):
    """The pilot writes only under its own root, and never into the frozen corpus."""
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in FORBIDDEN_PATH_MARKERS:
        if marker.replace("/", os.sep) in resolved:
            raise PilotRefused(
                f"the pilot work directory {resolved} touches {marker!r}; a shadow that can write "
                "into the evaluation window is not a shadow")
    if not resolved.endswith(os.sep + "b15a"):
        raise PilotRefused(f"the pilot work directory must be .../b15a, got {resolved}")
    return True


def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    """The freeze this pilot implements must be the one that was committed alone."""
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise PilotRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise PilotRefused(
            f"the pilot preregistration hashes {actual}, pinned {expected}; it was frozen before "
            "this code existed and a changed document is a different pilot")
    return document


def assert_commitment(commitment):
    if commitment not in PERMITTED_COMMITMENTS:
        raise PilotRefused(
            f"{commitment!r} is not a permitted commitment {list(PERMITTED_COMMITMENTS)}")
    return commitment


# --------------------------------------------------------------------------------------------
# Storage — raw frames are append-only and never rewritten
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS session (
  session_id TEXT PRIMARY KEY, endpoint_scheme_host TEXT NOT NULL, commitment TEXT NOT NULL,
  started_wall_unix REAL NOT NULL, started_monotonic_ns INTEGER NOT NULL,
  subscription_id TEXT, ended_wall_unix REAL, end_reason TEXT,
  frames_received INTEGER NOT NULL DEFAULT 0, reconnect_index INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS connection_event (
  event_seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, kind TEXT NOT NULL,
  wall_unix REAL NOT NULL, monotonic_ns INTEGER NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS launch (
  launch_seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
  frame_seq INTEGER NOT NULL, signature TEXT, slot INTEGER, mint TEXT, bonding_curve TEXT,
  creator TEXT, user TEXT, is_mayhem_mode INTEGER, quote_mint TEXT,
  decoded_wall_unix REAL NOT NULL, decoded_monotonic_ns INTEGER NOT NULL,
  decode_status TEXT NOT NULL, decode_error TEXT,
  backfill_status TEXT, backfill_wall_unix REAL, backfill_monotonic_ns INTEGER,
  evidence_sha256 TEXT NOT NULL, create_key TEXT);
CREATE TABLE IF NOT EXISTS decision (
  decision_seq INTEGER PRIMARY KEY AUTOINCREMENT, launch_seq INTEGER NOT NULL,
  policy_id TEXT NOT NULL, decided_wall_unix REAL NOT NULL, decided_monotonic_ns INTEGER NOT NULL,
  observation_to_decision_ns INTEGER NOT NULL, feature_availability TEXT NOT NULL,
  policy_result TEXT NOT NULL, reason_code TEXT, hypothetical_quote_lamports INTEGER,
  simulated_entry TEXT, outcome_placeholder TEXT, evidence_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pump_event (
  event_seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
  frame_seq INTEGER NOT NULL, signature TEXT, slot INTEGER, discriminator TEXT,
  decode_status TEXT NOT NULL, observed_wall_unix REAL NOT NULL,
  observed_monotonic_ns INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS launch_identity ON launch(create_key);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    migrate(connection)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


def migrate(connection):
    """Bring an artifact written by an earlier version up to the current schema.

    `CREATE TABLE IF NOT EXISTS` does nothing to a table that already exists, so the column added
    for launch identity has to be added explicitly. Migrating rather than recreating is the whole
    point: the derived tables are rebuilt from raw evidence by `replay`, and raw evidence is never
    discarded to make a schema change convenient.
    """
    existing = {row[1] for row in connection.execute("PRAGMA table_info(launch)")}
    if existing and "create_key" not in existing:
        connection.execute("ALTER TABLE launch ADD COLUMN create_key TEXT")
        # Pre-migration rows carry no identity key. The unique index would collide them all on
        # NULL — SQLite treats NULLs as distinct, so it does not, but they are also not deduped.
        # `replay` rebuilds the table from raw evidence, which is where the keys come from.
        connection.commit()
    return connection


def record_metadata(connection, document, receipt, commitment):
    for key, value in (
            ("schema_version", SCHEMA_VERSION),
            ("preregistration_id", document["preregistration_id"]),
            ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
            ("endpoint_scheme_host", receipt),
            ("commitment", commitment),
            ("execution_status", "never_executed"),
            ("performance_status", "not_evaluated"),
            ("geyser_fidelity", "false"),
            ("contains_outcomes", "0")):
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, str(value)))
    connection.commit()


class RawLog:
    """Append-only. A line once written is never edited or deleted."""

    def __init__(self, path=RAW_PATH):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = pathlib.Path(path)
        self.handle = open(self.path, "a", encoding="utf-8")
        self.count = sum(1 for _ in self.path.open()) if self.path.exists() else 0

    def append(self, record):
        self.count += 1
        self.handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        # Flushed per frame. A buffered raw log loses the last frames on any hard stop, and those
        # are exactly the frames a fault investigation wants.
        self.handle.flush()
        return self.count

    def close(self):
        self.handle.close()


# --------------------------------------------------------------------------------------------
# Decoding — pinned IDL, shared canonical decoder
# --------------------------------------------------------------------------------------------

def load_pinned_create_type(idl_path=None):
    """The CreateEvent definition from the pinned IDL, through B7d's own decoder helpers.

    `idl_path` is injectable so the two guards below are reachable. With the real pinned file they
    both hold by construction and could never be shown to fire, and a check nobody can provoke is
    a check nobody can show works.
    """
    b7d = _load("b7d_create_enumerator", "b7d_create_enumerator.py")
    idl_path = (ROOT / "research" / "pump_idl_9c82f61.json") if idl_path is None else idl_path
    idl = json.loads(pathlib.Path(idl_path).read_text())
    # Built EXACTLY as b7d builds it — the whole IDL item per name, not the inner `type` — because
    # b7d's own `read_struct` reads `definition["type"]["fields"]`. Paraphrasing that mapping is
    # what made the first fixture run report decode_failed on a payload built from the same IDL:
    # two constructions of the same thing, agreeing until they did not.
    types = {item["name"]: item for item in idl["types"]}
    create = next((entry for entry in idl.get("events", []) if entry["name"] == "CreateEvent"),
                  None)
    if create is None:
        raise PilotRefused("the pinned IDL declares no CreateEvent; refusing to guess its shape")
    discriminator = bytes(create["discriminator"]) if "discriminator" in create else None
    if discriminator is None:
        raise PilotRefused("the pinned CreateEvent carries no discriminator")
    return b7d, discriminator, types["CreateEvent"], types


def program_data_payloads(logs):
    """Every `Program data:` payload in a log array, decoded from base64.

    A line that is not valid base64 is skipped rather than raised on: the provider emits program
    logs from every program on the chain, and one unrelated malformed line must not stop the feed.
    The count of skipped lines is what the caller records.
    """
    import binascii
    payloads, skipped = [], 0
    for line in logs or ():
        if not isinstance(line, str) or not line.startswith(PROGRAM_DATA_PREFIX):
            continue
        try:
            payloads.append(__import__("base64").b64decode(line[len(PROGRAM_DATA_PREFIX):],
                                                           validate=True))
        except (binascii.Error, ValueError):
            skipped += 1
    return payloads, skipped


def decode_create(payload, b7d, discriminator, create_type, types):
    """One payload to a CreateEvent, or a status saying why not. Never a partial guess.

    TWO framings, because the same event reaches us two different ways and only one of them was
    handled at first:

    - **Inner-instruction data** carries the Anchor event-CPI tag `e445a52e51cb9a1d` and then the
      discriminator. That is what B7d reads, because it reads inner instructions.
    - **`Program data:` log lines carry the discriminator directly, with no tag.** This transport
      reads logs, so this is the framing that actually arrives.

    Requiring the tag meant the running pilot examined 739 program-data payloads and matched none
    of them: it recorded everything faithfully and could never have detected a single launch. The
    check that looked strictest was the one that made the pilot blind.
    """
    body = payload[len(EVENT_TAG):] if payload.startswith(EVENT_TAG) else payload
    if len(body) < len(discriminator):
        return DECODE_NOT_CREATE, None, None
    if not body.startswith(discriminator):
        return DECODE_UNKNOWN, None, None
    try:
        fields = b7d.decode_create_payload(body, discriminator, create_type, types)
    except Exception as error:                                            # noqa: BLE001
        return DECODE_FAILED, None, f"{type(error).__name__}: {error}"
    return DECODE_DECODED, fields, None


# --------------------------------------------------------------------------------------------
# The hypothetical decision
# --------------------------------------------------------------------------------------------

# CreateEvent field -> B10b state field. The event names the same quantities differently, and a
# mapping written once here is one place to be wrong instead of several.
CREATE_EVENT_TO_STATE = {
    "virtual_sol_reserves": "virtual_quote",
    "virtual_token_reserves": "virtual_token",
    "real_token_reserves": "real_token",
    "quote_mint": "quote_mint",
    "is_mayhem_mode": "mayhem_mode",
}

# What the CreateEvent structurally cannot supply. Not a bug and not a gap in this code: the event
# carries no real quote reserve and no completion flag, so a t0 state built from the feed alone is
# missing exactly these two. They are what a backfill would have to establish.
STATE_FIELDS_NOT_IN_CREATE_EVENT = ("real_quote", "complete")


def state_from_create_event(fields, slot):
    """A t0 state from the event, and the list of fields it could not supply.

    Nothing is assumed. `real_quote` is not defaulted to zero and `complete` is not defaulted to
    false, even though a freshly launched curve is very probably both — "very probably" is an
    assumption, the freeze forbids assumptions, and a veto set evaluated on one is a veto set
    judging eligibility on a number nobody observed.
    """
    if not fields:
        return {}, list(B10B_STATE_FIELDS)
    state = {target: fields[source] for source, target in CREATE_EVENT_TO_STATE.items()
             if fields.get(source) is not None}
    if slot is not None:
        state["slot"] = slot
    missing = [name for name in B10B_STATE_FIELDS if name not in state]
    return state, missing


B10B_STATE_FIELDS = ("virtual_quote", "virtual_token", "real_quote", "real_token",
                     "quote_mint", "mayhem_mode", "complete", "slot")


def feature_availability(fields, backfill_status, state=None, missing=()):
    """What is knowable at the decision instant, stated rather than assumed."""
    return {
        "identity_from_feed": bool(fields),
        "regime_from_feed": bool(fields) and fields.get("is_mayhem_mode") is not None,
        "quote_mint_from_feed": bool(fields) and fields.get("quote_mint") is not None,
        "state_fields_supplied": sorted(state.keys()) if state else [],
        "state_fields_missing": list(missing),
        "reserves_note": "the CreateEvent supplies most of the t0 state under different names; "
                         "real_quote and complete are structurally absent from it, and nothing "
                         "here substitutes a value for them",
        "backfill_status": backfill_status,
    }


def decide(fields, decode_status, backfill_status, observation_to_decision_ns,
           freshness_bound_ns, session_degraded, state=None):
    """The frozen B11b P1 policy, as far as the available evidence permits.

    Every path that cannot establish an input returns NO SHADOW ENTRY with a reason. There is no
    branch that assumes a value, substitutes a zero, or proceeds on partial evidence — which is
    why this returns a reason code on every negative rather than a bare False.
    """
    if decode_status != DECODE_DECODED:
        return RESULT_NO_ENTRY, S03_DECODE_INCOMPLETE, None
    if session_degraded:
        return RESULT_NO_ENTRY, S07_SESSION_DEGRADED, None
    if observation_to_decision_ns > freshness_bound_ns:
        return RESULT_NO_ENTRY, S06_STALE_OBSERVATION, None
    vetoes = b11b_vetoes(fields, state)
    if vetoes:
        return RESULT_NO_ENTRY, S04_VETO, ",".join(vetoes)
    if backfill_status != "retrieved":
        return RESULT_NO_ENTRY, S02_BACKFILL_UNAVAILABLE, None
    # Reaching here would mean the reserves at the decision instant were established. They cannot
    # be, from this feed — which is why S01 exists and why the veto set above returns
    # V4_incomplete_state on feed-only evidence rather than this line ever being the answer.
    return RESULT_NO_ENTRY, S01_FEED_ONLY_NO_RESERVES, None


def b11b_vetoes(fields, state=None):
    """B11b's hard vetoes, applied UNCHANGED by calling B11b's own function.

    Not reimplemented here. A paraphrase of a frozen veto set is a second veto set that agrees with
    the first until it does not, and the disagreement would be invisible.

    On feed-only evidence `state` is empty, so `V4_incomplete_state` fires — which is the correct
    and honest answer: logs carry no curve reserves, and a veto set that passed without them would
    be judging eligibility on inputs nobody has.
    """
    try:
        return B11B.evaluate_vetoes(
            dict(state or {}), B11B.ORDER_SIZE_LAMPORTS,
            regime_in_regime=True,
            version_supported=bool(fields) and fields.get("quote_mint") is not None)
    except Exception as error:                                            # noqa: BLE001
        # A veto set that cannot be evaluated is not a passed veto set.
        return (f"V4_incomplete_state:{type(error).__name__}",)


# --------------------------------------------------------------------------------------------
# Replay — derived tables rebuilt from the immutable raw log
# --------------------------------------------------------------------------------------------

def replay(raw_path=RAW_PATH, db_path=DB_PATH, freshness_bound_ns=None, backfill=None):
    """Rebuild `launch`, `decision` and `pump_event` from the raw frames. Raw is never touched.

    This is why the raw log is append-only and holds the provider payload exactly as delivered:
    every derived table is a function of it, so a defect in the derivation is repairable without
    losing a single observation. The contaminated census that prompted this was rebuilt, not
    discarded.
    """
    raw = pathlib.Path(raw_path)
    if not raw.exists():
        raise PilotRefused(f"no raw frame log at {raw}; there is nothing to replay from")
    document = verify_preregistration()
    freshness = document["freshness_bound_ns"] if freshness_bound_ns is None else freshness_bound_ns
    connection = open_database(db_path)
    b7d, discriminator, create_type, types = load_pinned_create_type()
    decoder = {"b7d": b7d, "discriminator": discriminator, "create_type": create_type,
               "types": types, "commitment": None}
    # Derived only. `session` and `connection_event` describe the live connection and cannot be
    # reconstructed from payloads, so they are left exactly as recorded.
    connection.execute("DELETE FROM decision")
    connection.execute("DELETE FROM launch")
    connection.execute("DELETE FROM pump_event")
    connection.commit()

    counts = {"frames": 0, "failed_tx": 0, "launch_candidates": 0, "non_launch_events": 0,
              "decoded": 0, "duplicates_ignored": 0}
    with raw.open() as handle:
        for line in handle:
            record = json.loads(line)
            counts["frames"] += 1
            document_in = record["raw_notification_json"]
            params = (document_in.get("params") or {}).get("result") or {}
            value = params.get("value") or {}
            slot = (params.get("context") or {}).get("slot")
            signature = value.get("signature")
            if value.get("err") is not None:
                counts["failed_tx"] += 1
                continue
            payloads, _skipped = program_data_payloads(value.get("logs"))
            for index, payload in enumerate(payloads):
                status_code, fields, error = decode_create(
                    payload, b7d, discriminator, create_type, types)
                if status_code in NON_LAUNCH_STATUSES:
                    counts["non_launch_events"] += 1
                    connection.execute(
                        "INSERT INTO pump_event(session_id,frame_seq,signature,slot,"
                        "discriminator,decode_status,observed_wall_unix,observed_monotonic_ns) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (record["session_id"], record["frame_seq"], signature, slot,
                         payload[:8].hex(), status_code, record["received_wall_unix"],
                         record["received_monotonic_ns"]))
                    continue
                counts["launch_candidates"] += 1
                if status_code == DECODE_DECODED:
                    counts["decoded"] += 1
                key = create_key(signature, slot, index, fields)
                evidence = {"session_id": record["session_id"],
                            "frame_seq": record["frame_seq"], "signature": signature,
                            "slot": slot, "decode_status": status_code, "fields": fields}
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO launch(session_id,frame_seq,signature,slot,mint,"
                    "bonding_curve,creator,user,is_mayhem_mode,quote_mint,decoded_wall_unix,"
                    "decoded_monotonic_ns,decode_status,decode_error,backfill_status,"
                    "evidence_sha256,create_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (record["session_id"], record["frame_seq"], signature, slot,
                     (fields or {}).get("mint"), (fields or {}).get("bonding_curve"),
                     (fields or {}).get("creator"), (fields or {}).get("user"),
                     (fields or {}).get("is_mayhem_mode"), (fields or {}).get("quote_mint"),
                     record["received_wall_unix"], record["received_monotonic_ns"], status_code,
                     error, "not_attempted", evidence_hash(evidence), key))
                if cursor.rowcount == 0:
                    counts["duplicates_ignored"] += 1
                    counts["launch_candidates"] -= 1
                    if status_code == DECODE_DECODED:
                        counts["decoded"] -= 1
                    continue
                launch_seq = cursor.lastrowid
                state, missing = state_from_create_event(fields, slot)
                availability = feature_availability(fields, "not_attempted", state, missing)
                result, reason, detail = decide(fields, status_code, "not_attempted", 0,
                                                freshness, False, state)
                decision = {"launch_seq": launch_seq, "policy_id": B11B.PRIMARY_POLICY,
                            "result": result, "reason": reason, "detail": detail}
                connection.execute(
                    "INSERT INTO decision(launch_seq,policy_id,decided_wall_unix,"
                    "decided_monotonic_ns,observation_to_decision_ns,feature_availability,"
                    "policy_result,reason_code,hypothetical_quote_lamports,simulated_entry,"
                    "outcome_placeholder,evidence_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (launch_seq, B11B.PRIMARY_POLICY, record["received_wall_unix"],
                     record["received_monotonic_ns"], 0,
                     json.dumps(availability, sort_keys=True), result,
                     reason if detail is None else f"{reason}:{detail}",
                     B11B.ORDER_SIZE_LAMPORTS if result == RESULT_PROPOSED else None,
                     None, None, evidence_hash(decision)))
    connection.commit()
    counts["launch_rows"] = connection.execute("SELECT COUNT(*) FROM launch").fetchone()[0]
    counts["decision_rows"] = connection.execute("SELECT COUNT(*) FROM decision").fetchone()[0]
    counts["observed_launches_for_stopping_rule"] = observed_launch_count(connection)
    assert_population_invariants(connection)
    connection.close()
    return counts


def assert_population_invariants(connection):
    """The separation, checked rather than trusted, wherever the tables are written.

    Four statements, each of which was false in the contaminated artifact:
    every launch row is a launch candidate; every launch has exactly one decision; no non-launch
    event is in the launch table; and the stopping-rule counter never exceeds the launch rows.
    """
    stray = connection.execute(
        "SELECT COUNT(*) FROM launch WHERE decode_status NOT IN (?,?)",
        LAUNCH_CANDIDATE_STATUSES).fetchone()[0]
    if stray:
        raise PilotRefused(
            f"{stray} rows in the launch table are not launch candidates. A trade counted as a "
            "launch ends a 72-hour pilot in minutes")
    launches = connection.execute("SELECT COUNT(*) FROM launch").fetchone()[0]
    decisions = connection.execute("SELECT COUNT(*) FROM decision").fetchone()[0]
    if launches != decisions:
        raise PilotRefused(
            f"{launches} launches carry {decisions} decisions; a decision must exist for exactly "
            "one observed launch and a launch must carry exactly one decision")
    orphans = connection.execute(
        "SELECT COUNT(*) FROM decision WHERE launch_seq NOT IN (SELECT launch_seq FROM launch)"
    ).fetchone()[0]
    if orphans:
        raise PilotRefused(f"{orphans} decisions reference no launch")
    # There was a check here that the stopping-rule counter does not exceed the launch rows. It
    # could never fire: the counter is `COUNT(*) FROM launch WHERE decode_status='decoded'`, a SQL
    # subset of the rows it was being compared against. A branch nothing can provoke reads as
    # protection while providing none, so it is gone rather than standing as decoration.
    return True


# --------------------------------------------------------------------------------------------
# Status — redacted by construction
# --------------------------------------------------------------------------------------------

REDACTED_FORBIDDEN_KEYS = ("mint", "bonding_curve", "creator", "user", "signature",
                           "quote_lamports", "simulated_entry")


def status(db_path=DB_PATH, raw_path=RAW_PATH):
    """What an operator may see. No identity, no figure, no credential.

    Aggregates only. A status line is read by people and pasted into places, and a mint address in
    one is a mint address in all of them.
    """
    if not pathlib.Path(db_path).exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started"}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        meta = dict(connection.execute("SELECT key, value FROM metadata"))
        sessions = connection.execute(
            "SELECT session_id, started_wall_unix, ended_wall_unix, end_reason, frames_received, "
            "reconnect_index, subscription_id FROM session ORDER BY started_wall_unix").fetchall()
        events = dict(connection.execute(
            "SELECT kind, COUNT(*) FROM connection_event GROUP BY kind"))
        decodes = dict(connection.execute(
            "SELECT decode_status, COUNT(*) FROM launch GROUP BY decode_status"))
        reasons = dict(connection.execute(
            "SELECT COALESCE(reason_code,'none'), COUNT(*) FROM decision GROUP BY 1"))
        results = dict(connection.execute(
            "SELECT policy_result, COUNT(*) FROM decision GROUP BY 1"))
        launches = connection.execute("SELECT COUNT(*) FROM launch").fetchone()[0]
        decoded_launches = connection.execute(
            "SELECT COUNT(*) FROM launch WHERE decode_status='decoded'").fetchone()[0]
        non_launch = dict(connection.execute(
            "SELECT decode_status, COUNT(*) FROM pump_event GROUP BY 1"))
        top_discriminators = connection.execute(
            "SELECT discriminator, COUNT(*) c FROM pump_event GROUP BY 1 ORDER BY c DESC LIMIT 5"
        ).fetchall()
        backfills = dict(connection.execute(
            "SELECT COALESCE(backfill_status,'none'), COUNT(*) FROM launch GROUP BY 1"))
    finally:
        connection.close()
    current = sessions[-1] if sessions else None
    started = sessions[0][1] if sessions else None
    elapsed = (time.time() - started) if started else 0
    report = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": meta.get("preregistration_id"),
        "endpoint_scheme_host": meta.get("endpoint_scheme_host"),
        "commitment": meta.get("commitment"),
        "geyser_fidelity": False,
        "execution_status": meta.get("execution_status"),
        "performance_status": meta.get("performance_status"),
        "sessions": len(sessions),
        "current_session_id": current[0] if current else None,
        "subscribed": bool(current and current[6]),
        "reconnects": max(0, len(sessions) - 1),
        "uptime_seconds": int(elapsed),
        "frames_received": sum(row[4] for row in sessions),
        "raw_frames_on_disk": sum(1 for _ in open(raw_path)) if pathlib.Path(raw_path).exists()
        else 0,
        "connection_events": events,
        "launch_candidate_records": launches,
        "observed_launches_decoded": decoded_launches,
        "non_launch_event_counts": non_launch,
        "non_launch_events_total": sum(non_launch.values()),
        "top_non_launch_discriminators": [{"discriminator": d, "count": c}
                                          for d, c in top_discriminators],
        "decode_status_counts": decodes,
        "backfill_status_counts": backfills,
        "decision_results": results,
        "decision_reason_counts": reasons,
        "stopping_rule": {"wall_clock_hours": 72, "observed_launch_records": 5000,
                          "hours_elapsed": round(elapsed / 3600, 2),
                          # Decoded creates ONLY. This read said 814 when four launches had been
                          # seen, and would have ended a 72-hour pilot in minutes.
                          "launches_observed": decoded_launches},
        "end_reason": current[3] if current else None,
    }
    assert_redacted(report)
    return report


def assert_redacted(report):
    """No identity and no figure may reach a status line, at any depth."""
    text = json.dumps(report).lower()
    for key in REDACTED_FORBIDDEN_KEYS:
        if f'"{key}"' in text:
            raise PilotRefused(
                f"the status report carries {key!r}; identities and figures do not belong in a "
                "line that gets pasted into places")
    credential = os.environ.get(RPC_ENV_VAR)
    if credential:
        parts = urlsplit(credential)
        for secret in (parts.query, parts.path.strip("/")):
            # Lowered on BOTH sides. The report was lowercased and the secret was not, so a
            # credential with any capital letter — which is most of them — never matched, and the
            # check that exists to catch a leak was blind to exactly the case it exists for.
            if secret and len(secret) >= 8 and secret.lower() in text:
                raise PilotRefused("the status report carries part of the credential")
    return True


# --------------------------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------------------------

def now():
    """Both clocks, together, always. Wall correlates; monotonic measures."""
    return time.time(), time.monotonic_ns()


def session_identity(wall, pid):
    return hashlib.sha256(f"b15a::{pid}::{wall:.6f}".encode()).hexdigest()[:16]


def create_key(signature, slot, payload_index, fields):
    """The identity of one observed launch, independent of when or how often it arrived."""
    mint = (fields or {}).get("mint")
    return hashlib.sha256(
        f"{signature}|{slot}|{payload_index}|{mint}".encode()).hexdigest()


def evidence_hash(record):
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def observed_launch_count(connection):
    """The stopping rule's counter: positively decoded CreateEvents, and nothing else.

    NOT `SELECT COUNT(*) FROM launch`. The rule ends the pilot after 5,000 observed launches, and
    an observed launch is a launch — a CreateEvent that decoded. A trade is not a launch under any
    reading of the frozen document, so counting one toward the quota is not an interpretation of
    the rule, it is a different rule. This is a correction of the counter, not of the rule.
    """
    return connection.execute("SELECT COUNT(*) FROM launch WHERE decode_status=?",
                              (DECODE_DECODED,)).fetchone()[0]


def stopping_rule_reached(document, started_wall, launches):
    """Frozen before the first frame; evaluated here and never widened."""
    rules = document["window_and_stopping_rule"]["runs_until_first_of"]
    hours = next(r["value"] for r in rules if r["rule"] == "wall_clock_hours")
    limit = next(r["value"] for r in rules if r["rule"] == "observed_launch_records")
    if (time.time() - started_wall) >= hours * 3600:
        return "wall_clock_hours"
    if launches >= limit:
        return "observed_launch_records"
    return None


def log_event(connection, session_id, kind, detail=None):
    wall, mono = now()
    connection.execute(
        "INSERT INTO connection_event(session_id,kind,wall_unix,monotonic_ns,detail) "
        "VALUES (?,?,?,?,?)", (session_id, kind, wall, mono, detail))
    connection.commit()


def handle_frame(connection, raw, session_id, frame_seq, message, decoder, freshness_bound_ns,
                 session_degraded, backfill=None):
    """One notification: preserve it, decode it, decide on it. Returns (launches, decisions)."""
    wall, mono = now()
    document = json.loads(message)
    params = (document.get("params") or {}).get("result") or {}
    context = params.get("context") or {}
    value = params.get("value") or {}
    slot = context.get("slot")
    signature = value.get("signature")
    raw.append({
        "frame_seq": frame_seq, "session_id": session_id,
        "subscription_id": (document.get("params") or {}).get("subscription"),
        "received_wall_unix": wall, "received_monotonic_ns": mono,
        "commitment": decoder["commitment"], "slot": slot, "signature": signature,
        "raw_notification_json": document,
        "raw_sha256": hashlib.sha256(message.encode()).hexdigest(),
    })
    if value.get("err") is not None:
        return 0, 0                       # a failed transaction launched nothing
    payloads, _skipped = program_data_payloads(value.get("logs"))
    launches = decisions = 0
    for index, payload in enumerate(payloads):
        status_code, fields, error = decode_create(
            payload, decoder["b7d"], decoder["discriminator"], decoder["create_type"],
            decoder["types"])
        if status_code in NON_LAUNCH_STATUSES:
            # Preserved and counted, in its OWN population. This is the branch that used to fall
            # through into the launch table and put 1,045 trades where ten launches belonged.
            observed_wall, observed_mono = now()
            connection.execute(
                "INSERT INTO pump_event(session_id,frame_seq,signature,slot,discriminator,"
                "decode_status,observed_wall_unix,observed_monotonic_ns) VALUES (?,?,?,?,?,?,?,?)",
                (session_id, frame_seq, signature, slot, payload[:8].hex(), status_code,
                 observed_wall, observed_mono))
            continue
        launches += 1
        decoded_wall, decoded_mono = now()
        record = {"session_id": session_id, "frame_seq": frame_seq, "signature": signature,
                  "slot": slot, "decode_status": status_code, "fields": fields}
        # A launch is identified by what it IS, not by when we happened to see it. The unique index
        # on this key makes a duplicate structurally impossible, so a redelivered notification
        # after a reconnect, or a replay over frames already processed, cannot inflate the count.
        key = create_key(signature, slot, index, fields)
        cursor = connection.execute(
            "INSERT OR IGNORE INTO launch(session_id,frame_seq,signature,slot,mint,bonding_curve,"
            "creator,user,is_mayhem_mode,quote_mint,decoded_wall_unix,decoded_monotonic_ns,"
            "decode_status,decode_error,backfill_status,evidence_sha256,create_key) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, frame_seq, signature, slot,
             (fields or {}).get("mint"), (fields or {}).get("bonding_curve"),
             (fields or {}).get("creator"), (fields or {}).get("user"),
             (fields or {}).get("is_mayhem_mode"), (fields or {}).get("quote_mint"),
             decoded_wall, decoded_mono, status_code, error,
             "not_attempted" if backfill is None else None, evidence_hash(record), key))
        if cursor.rowcount == 0:
            # Already recorded under this identity. Not an error and not a new launch.
            launches -= 1
            continue
        launch_seq = cursor.lastrowid
        backfill_status = "not_attempted"
        if backfill is not None and status_code == DECODE_DECODED and signature:
            backfill_status = backfill(signature)
            back_wall, back_mono = now()
            connection.execute(
                "UPDATE launch SET backfill_status=?,backfill_wall_unix=?,backfill_monotonic_ns=? "
                "WHERE launch_seq=?", (backfill_status, back_wall, back_mono, launch_seq))
        decided_wall, decided_mono = now()
        elapsed = decided_mono - mono
        state, missing = state_from_create_event(fields, slot)
        availability = feature_availability(fields, backfill_status, state, missing)
        result, reason, detail = decide(fields, status_code, backfill_status, elapsed,
                                        freshness_bound_ns, session_degraded, state)
        decision = {"launch_seq": launch_seq, "policy_id": B11B.PRIMARY_POLICY,
                    "result": result, "reason": reason, "detail": detail}
        connection.execute(
            "INSERT INTO decision(launch_seq,policy_id,decided_wall_unix,decided_monotonic_ns,"
            "observation_to_decision_ns,feature_availability,policy_result,reason_code,"
            "hypothetical_quote_lamports,simulated_entry,outcome_placeholder,evidence_sha256) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (launch_seq, B11B.PRIMARY_POLICY, decided_wall, decided_mono, elapsed,
             json.dumps(availability, sort_keys=True), result,
             reason if detail is None else f"{reason}:{detail}",
             # A hypothetical size is recorded ONLY when something was actually proposed. Writing
             # it on a refusal would put a number next to a decision that never happened.
             B11B.ORDER_SIZE_LAMPORTS if result == RESULT_PROPOSED else None,
             None, None, evidence_hash(decision)))
        decisions += 1
    connection.commit()
    assert_population_invariants(connection)
    return launches, decisions


MAX_CONSECUTIVE_BARREN_SESSIONS = 20


def run(commitment=DEFAULT_COMMITMENT, max_frames=None, transport=None, backfill=None,
        work_dir=WORK_DIR, clock=None, max_sessions=None,
        max_barren_sessions=MAX_CONSECUTIVE_BARREN_SESSIONS):
    """Connect, record, decide, reconnect, stop. Fails visibly and preserves everything."""
    assert_no_execution_surface()
    assert_isolated(work_dir)
    document = verify_preregistration()
    assert_commitment(commitment)
    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)

    url = WS.websocket_url_from_env()
    receipt = WS.endpoint_receipt(url)
    connection = open_database(pathlib.Path(work_dir) / "shadow.sqlite")
    raw = RawLog(pathlib.Path(work_dir) / "raw_frames.jsonl")
    record_metadata(connection, document, receipt, commitment)
    b7d, discriminator, create_type, types = load_pinned_create_type()
    decoder = {"b7d": b7d, "discriminator": discriminator, "create_type": create_type,
               "types": types, "commitment": commitment}
    freshness = document["freshness_bound_ns"]

    started_wall = time.time()
    total_launches = observed_launch_count(connection)
    stop = {"requested": False}

    def request_stop(_signum, _frame):
        stop["requested"] = True

    for name in ("SIGTERM", "SIGINT"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), request_stop)
            except ValueError:
                pass                       # not the main thread; the loop still honours max_frames

    reconnect_index = 0
    barren = 0
    end_reason = END_STOPPING_RULE
    try:
        while not stop["requested"]:
            # Two bounds on reconnection, for two different reasons.
            #
            # `max_sessions` exists so an offline fixture can drive the reconnect path and still
            # terminate. Without it the first fixture run spun to 475,805 sessions in 283 seconds.
            #
            # `max_barren_sessions` is the production one, and it is not a convenience: an endpoint
            # that never yields a frame should stop the pilot with a recorded fault, not accumulate
            # half a million empty sessions whose count is then reported as evidence of anything.
            if max_sessions is not None and reconnect_index >= max_sessions:
                end_reason = END_OPERATOR_STOP
                break
            if barren >= max_barren_sessions:
                end_reason = END_FAULT
                break
            wall, mono = now()
            session_id = session_identity(wall, os.getpid())
            connection.execute(
                "INSERT INTO session(session_id,endpoint_scheme_host,commitment,"
                "started_wall_unix,started_monotonic_ns,reconnect_index) VALUES (?,?,?,?,?,?)",
                (session_id, receipt, commitment, wall, mono, reconnect_index))
            connection.commit()
            log_event(connection, session_id, "connect_attempt", f"reconnect={reconnect_index}")
            socket_ = None
            frames = 0
            degraded = reconnect_index > 0
            try:
                socket_ = (transport(url) if transport is not None
                           else WS.WebSocket(url).connect())
                socket_.send_json({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                                   "params": [{"mentions": [PUMP_PROGRAM]},
                                              {"commitment": commitment}]})
                while not stop["requested"]:
                    message = socket_.recv()
                    if message is None:
                        log_event(connection, session_id, "disconnected",
                                  getattr(socket_, "close_reason", "peer closed"))
                        break
                    document_in = json.loads(message)
                    if "result" in document_in and "params" not in document_in:
                        connection.execute("UPDATE session SET subscription_id=? "
                                           "WHERE session_id=?",
                                           (str(document_in["result"]), session_id))
                        connection.commit()
                        log_event(connection, session_id, "subscribed",
                                  str(document_in["result"]))
                        continue
                    if "params" not in document_in:
                        log_event(connection, session_id, "fault", message[:200])
                        continue
                    frames += 1
                    launches, _decisions = handle_frame(
                        connection, raw, session_id, raw.count + 1, message, decoder, freshness,
                        degraded, backfill)
                    total_launches = observed_launch_count(connection)
                    connection.execute("UPDATE session SET frames_received=? WHERE session_id=?",
                                       (frames, session_id))
                    connection.commit()
                    reached = stopping_rule_reached(document, started_wall, total_launches)
                    if reached:
                        log_event(connection, session_id, "fault", f"stopping rule: {reached}")
                        stop["requested"] = True
                        end_reason = END_STOPPING_RULE
                        break
                    if max_frames is not None and frames >= max_frames:
                        stop["requested"] = True
                        end_reason = END_OPERATOR_STOP
                        break
            except Exception as error:                                    # noqa: BLE001
                # Recorded, not swallowed. A fault that leaves no trace is a gap nobody can audit.
                log_event(connection, session_id, "fault", f"{type(error).__name__}: {error}")
                end_reason = END_FAULT
            finally:
                if socket_ is not None:
                    try:
                        socket_.close()
                    except Exception:                                     # noqa: BLE001
                        pass
                connection.execute(
                    "UPDATE session SET ended_wall_unix=?, end_reason=? WHERE session_id=?",
                    (time.time(), end_reason, session_id))
                connection.commit()
            barren = barren + 1 if frames == 0 else 0
            if stop["requested"]:
                break
            delay = RECONNECT_BACKOFF_SECONDS[min(reconnect_index,
                                                  len(RECONNECT_BACKOFF_SECONDS) - 1)]
            log_event(connection, session_id, "reconnect_scheduled", f"after {delay}s")
            reconnect_index += 1
            (clock or time.sleep)(delay)
    finally:
        raw.close()
        connection.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--status", action="store_true", help="redacted operator status")
    parser.add_argument("--contract", action="store_true", help="verify the freeze and the gates")
    parser.add_argument("--watch", action="store_true", help="run the pilot")
    parser.add_argument("--commitment", default=DEFAULT_COMMITMENT,
                        choices=list(PERMITTED_COMMITMENTS))
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
        return 0
    if args.contract:
        document = verify_preregistration()
        assert_no_execution_surface()
        assert_isolated()
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "preregistration_id": document["preregistration_id"],
            "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
            "execution_surface": "absent",
            "isolated_work_dir": str(WORK_DIR),
            "geyser_fidelity": False,
            "permitted_commitments": list(PERMITTED_COMMITMENTS),
        }, indent=2, sort_keys=True))
        return 0
    if args.watch:
        return run(commitment=args.commitment)
    parser.error("nothing to do; --contract, --status or --watch")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PilotRefused as error:
        print(f"PilotRefused: {error}", file=sys.stderr)
        sys.exit(2)
