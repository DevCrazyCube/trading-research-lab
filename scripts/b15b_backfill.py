"""B15b — selective, read-only backfill of B15a decoded launch transactions.

Implements `research/B15B_BACKFILL_PREREGISTRATION.json`, committed alone before this file existed
and before a single transaction was fetched.

It fetches each decoded launch's transaction once, preserves the exchange immutably, and derives t0
state ONLY from events inside that transaction using the pinned IDL. It reads B15a read-only while
B15a keeps recording, writes nothing outside `research/b15b`, and holds no key, signs nothing,
builds no transaction and submits nothing.

The determination that shapes everything here was made offline, before any fetch:

- **`real_quote` is provable only when the launch transaction carries a TradeEvent** on the curve.
  `TradeEvent` publishes `real_quote_reserves`; `CreateEvent` publishes neither it nor
  `real_sol_reserves`. With no trade, it is unavailable — not zero.
- **`complete` is provable**, by B10b's own rule: absence of a `CompleteEvent` means false, and
  here that is evidence rather than convention, because the curve is CREATED in this transaction so
  no earlier one could have completed it.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15b"
EXCHANGE_PATH = WORK_DIR / "rpc_exchanges.jsonl"
DB_PATH = WORK_DIR / "backfill.sqlite"
B15A_DB = ROOT / "research" / "b15a" / "shadow.sqlite"

PREREG_PATH = ROOT / "research" / "B15B_BACKFILL_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "61cfe8a51792f4fa3f490d25d23911867e0e782010327d686c2f802dec463192"

RPC_ENV_VAR = "SOLANA_RPC_URL"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

STATUS_RETRIEVED = "retrieved"
STATUS_UNAVAILABLE = "unavailable"
STATUS_FAILED = "failed"

U01_REAL_QUOTE_NOT_PUBLISHED = "U01_real_quote_not_published"
U02_COMPLETION_AMBIGUOUS = "U02_completion_ambiguous"
U03_RPC_EXHAUSTED = "U03_rpc_exhausted"
U04_COST_INPUTS_UNSTATED = "U04_cost_inputs_unstated"

F01_SIGNATURE_MISMATCH = "F01_signature_mismatch"
F02_SLOT_MISMATCH = "F02_slot_mismatch"
F03_MINT_MISMATCH = "F03_mint_mismatch"
F04_TRANSACTION_FAILED = "F04_transaction_failed"
F05_NO_CREATE_EVENT = "F05_no_create_event"
F06_CONFLICTING_EVENTS = "F06_conflicting_events"
F07_STALE_RESPONSE = "F07_stale_response"
F08_DATABASE_LOCKED = "F08_database_locked"
F09_UNKNOWN_DISCRIMINATOR = "F09_unknown_discriminator_in_curve_events"

BASIS_FEED_ONLY = "feed_only"
BASIS_BACKFILLED = "backfilled_transaction"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PILOT = _load("b15a_shadow_pilot", "b15a_shadow_pilot.py")
B11B = PILOT.B11B


class BackfillRefused(PILOT.PilotRefused):
    """The worker will not do what it was asked, and fails visibly rather than improvising."""


# --------------------------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------------------------

def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise BackfillRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise BackfillRefused(
            f"the backfill preregistration hashes {actual}, pinned {expected}; the rate policy and "
            "the provability determination were frozen before any request and a changed document "
            "is a different worker")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = path.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise BackfillRefused(
            f"an execution surface appeared in {path.name}: {found}. This worker reads; it does "
            "not hold keys, sign, build, simulate or submit anything")
    return True


def assert_isolated(work_dir=WORK_DIR):
    """Writes only under its own root. B15a and B11a are read-only or out of reach entirely."""
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in ("research/b15a", "research/b11a"):
        if marker.replace("/", os.sep) in resolved:
            raise BackfillRefused(
                f"{resolved} would write into {marker!r}; B15a is append-only evidence being "
                "written by a live recorder and this worker may only read it")
    if not resolved.endswith(os.sep + "b15b"):
        raise BackfillRefused(f"the work directory must be .../b15b, got {resolved}")
    return True


# --------------------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS backfill (
  signature TEXT PRIMARY KEY, launch_seq INTEGER, slot INTEGER, mint TEXT, bonding_curve TEXT,
  attempts INTEGER NOT NULL, status TEXT NOT NULL, unavailable_reason TEXT, latency_ns INTEGER,
  context_slot INTEGER, commitment TEXT, evidence_sha256 TEXT NOT NULL,
  backfilled_at_wall_unix REAL NOT NULL);
CREATE TABLE IF NOT EXISTS t0_state (
  signature TEXT PRIMARY KEY, virtual_quote INTEGER, virtual_token INTEGER, real_quote INTEGER,
  real_token INTEGER, quote_mint TEXT, mayhem_mode INTEGER, complete INTEGER, slot INTEGER,
  trade_count_in_launch_tx INTEGER NOT NULL, provenance TEXT NOT NULL, missing_fields TEXT NOT NULL,
  evidence_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decision_v2 (
  decision_seq INTEGER PRIMARY KEY AUTOINCREMENT, launch_seq INTEGER NOT NULL,
  signature TEXT NOT NULL, version INTEGER NOT NULL, supersedes_decision_seq INTEGER,
  policy_id TEXT NOT NULL, decided_wall_unix REAL NOT NULL, decided_monotonic_ns INTEGER NOT NULL,
  evidence_basis TEXT NOT NULL, feature_availability TEXT NOT NULL, policy_result TEXT NOT NULL,
  reason_code TEXT, hypothetical_quote_lamports INTEGER, simulated_entry TEXT,
  outcome_placeholder TEXT, evidence_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS decision_current ON decision_v2(signature, version);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(path, timeout=30)
        connection.executescript(SCHEMA)
        connection.commit()
    except sqlite3.OperationalError as error:
        raise BackfillRefused(f"{F08_DATABASE_LOCKED}: {error}") from error
    return connection


class ExchangeLog:
    """Append-only. Every request and every response or error, exactly as they happened."""

    def __init__(self, path=EXCHANGE_PATH):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = pathlib.Path(path)
        self.handle = open(self.path, "a", encoding="utf-8")
        self.count = sum(1 for _ in self.path.open()) if self.path.exists() else 0

    def append(self, record):
        self.count += 1
        record = dict(record, exchange_seq=self.count)
        self.handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self.handle.flush()
        return self.count

    def close(self):
        self.handle.close()


# --------------------------------------------------------------------------------------------
# The pending set — read from B15a, read-only, while it keeps recording
# --------------------------------------------------------------------------------------------

def pending_signatures(b15a_path=B15A_DB, db_path=DB_PATH, limit=None):
    """Decoded launches B15a has recorded that this worker has not resolved.

    B15a is opened READ-ONLY. It is being appended to by a live recorder, and a worker that could
    write to it would be able to corrupt the only immutable evidence in the system.
    """
    source = sqlite3.connect(f"file:{b15a_path}?mode=ro", uri=True, timeout=30)
    try:
        rows = source.execute(
            "SELECT launch_seq, signature, slot, mint, bonding_curve FROM launch "
            "WHERE decode_status=? AND signature IS NOT NULL ORDER BY launch_seq",
            (PILOT.DECODE_DECODED,)).fetchall()
    finally:
        source.close()
    done = set()
    if pathlib.Path(db_path).exists():
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
        try:
            done = {row[0] for row in connection.execute(
                "SELECT signature FROM backfill WHERE status IN (?,?)",
                (STATUS_RETRIEVED, STATUS_UNAVAILABLE))}
        finally:
            connection.close()
    pending = [row for row in rows if row[1] not in done]
    return pending[:limit] if limit else pending


# --------------------------------------------------------------------------------------------
# Transport — read-only getTransaction, rate limited, bounded retries
# --------------------------------------------------------------------------------------------

def endpoint_receipt(url):
    parts = urlsplit(url)
    if not parts.scheme or not parts.hostname:
        raise BackfillRefused("endpoint has no scheme or host")
    return f"{parts.scheme}://{parts.hostname}"


def rpc_url():
    url = os.environ.get(RPC_ENV_VAR)
    if not url:
        raise BackfillRefused(
            f"{RPC_ENV_VAR} is not set. Credentials are environment-only and this process never "
            "reads one from a file it wrote")
    return url


def is_retryable(text, markers):
    lowered = str(text).lower()
    return any(marker in lowered for marker in markers)


def fetch_transaction(signature, url, policy, exchanges, opener=None, sleeper=time.sleep):
    """One transaction, with bounded retries. Every attempt is preserved before it is judged."""
    receipt = endpoint_receipt(url)
    body = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [signature, {"encoding": "jsonParsed",
                                   "maxSupportedTransactionVersion": 0,
                                   "commitment": policy["transport"]["commitment"]}]}
    attempts = policy["rate_and_stopping_policy"]["max_attempts_per_signature"]
    backoff = policy["rate_and_stopping_policy"]["backoff_seconds"]
    markers = policy["rate_and_stopping_policy"]["retryable_markers"]
    last = None
    for attempt in range(1, attempts + 1):
        requested_wall, requested_mono = time.time(), time.monotonic_ns()
        outcome, status_code, payload = _one_attempt(url, body, opener)
        received_wall, received_mono = time.time(), time.monotonic_ns()
        exchanges.append({
            "signature": signature, "attempt": attempt, "endpoint_scheme_host": receipt,
            # The request is recorded WITHOUT the endpoint: the URL carries the credential in its
            # query and the receipt above is the whole of what may be retained.
            "request_json": body, "requested_wall_unix": requested_wall,
            "requested_monotonic_ns": requested_mono, "received_wall_unix": received_wall,
            "received_monotonic_ns": received_mono, "http_status": status_code,
            "response_json_or_error": payload,
            "raw_sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest(),
            "outcome": outcome,
        })
        last = (outcome, payload, received_mono - requested_mono)
        if outcome == "retrieved":
            return last
        if outcome == "not_found":
            return last
        if not is_retryable(payload, markers) or attempt == attempts:
            return last
        sleeper(backoff[min(attempt - 1, len(backoff) - 1)])
    return last


def _one_attempt(url, body, opener):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        handle = (opener or urllib.request.urlopen)(request, timeout=30)
    except urllib.error.HTTPError as error:
        return "rpc_error", error.code, f"HTTPError {error.code}: {error.reason}"
    except Exception as error:                                            # noqa: BLE001
        return "transport_error", None, f"{type(error).__name__}: {error}"
    with handle:
        raw = handle.read().decode()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        return "transport_error", getattr(handle, "status", None), f"invalid JSON: {error}"
    if "error" in document:
        return "rpc_error", getattr(handle, "status", None), document["error"]
    if document.get("result") is None:
        return "not_found", getattr(handle, "status", None), document
    return "retrieved", getattr(handle, "status", None), document


# --------------------------------------------------------------------------------------------
# Derivation — only from events inside the launch transaction
# --------------------------------------------------------------------------------------------

def curve_events(response, decoder):
    """Every Pump event in the transaction, decoded with the pinned IDL, in canonical order.

    Log order is the canonical order within one transaction: the runtime emits program data in
    execution order, so the last TradeEvent in the list is the last one that happened.
    """
    result = response.get("result") or {}
    meta = result.get("meta") or {}
    logs = meta.get("logMessages") or []
    payloads, _skipped = PILOT.program_data_payloads(logs)
    events = []
    for index, payload in enumerate(payloads):
        body = payload[len(PILOT.EVENT_TAG):] if payload.startswith(PILOT.EVENT_TAG) else payload
        if len(body) < 8:
            continue
        discriminator = body[:8]
        name = decoder["by_discriminator"].get(discriminator.hex())
        if name is None:
            events.append({"index": index, "name": None, "discriminator": discriminator.hex(),
                           "fields": None})
            continue
        try:
            fields = decoder["b7d"].read_struct(
                decoder["b7d"].Cursor(body[8:]), decoder["types"][name], decoder["types"])
        except Exception as error:                                        # noqa: BLE001
            raise BackfillRefused(f"{F09_UNKNOWN_DISCRIMINATOR}: {name} did not decode: {error}")
        events.append({"index": index, "name": name, "discriminator": discriminator.hex(),
                       "fields": fields})
    return events


def derive_t0_state(events, expected_mint, slot):
    """The t0 state, from transaction evidence only. Missing fields are named, never filled.

    `real_quote` comes from the LAST TradeEvent on this curve, because t0 is the transaction's
    terminal state. With no TradeEvent it is absent and stays absent.
    """
    creates = [e for e in events if e["name"] == "CreateEvent"
               and (e["fields"] or {}).get("mint") == expected_mint]
    if not creates:
        raise BackfillRefused(f"{F05_NO_CREATE_EVENT}: no CreateEvent for {expected_mint}")
    if len(creates) > 1:
        raise BackfillRefused(f"{F06_CONFLICTING_EVENTS}: {len(creates)} CreateEvents for one mint")
    create = creates[0]["fields"]
    # F03_mint_mismatch is NOT checked again here. `creates` is already filtered on
    # fields["mint"] == expected_mint, so a second comparison could never be false — a mint that
    # disagrees produces an empty list and F05 above, which is the honest code for it. A branch
    # nothing can provoke reads as protection while providing none.

    completions = [e for e in events if e["name"] == "CompleteEvent"
                   and (e["fields"] or {}).get("mint") == expected_mint]
    if len(completions) > 1:
        raise BackfillRefused(
            f"{F06_CONFLICTING_EVENTS}: {len(completions)} CompleteEvents for one curve")
    trades = [e for e in events if e["name"] == "TradeEvent"
              and (e["fields"] or {}).get("mint") == expected_mint]

    state = {
        "virtual_quote": create.get("virtual_sol_reserves"),
        "virtual_token": create.get("virtual_token_reserves"),
        "real_token": create.get("real_token_reserves"),
        "quote_mint": create.get("quote_mint"),
        "mayhem_mode": create.get("is_mayhem_mode"),
        # Provable here, and by B10b's own rule: the curve is CREATED in this transaction, so no
        # earlier transaction could have completed it. Absence in the only transaction that could
        # carry a CompleteEvent is evidence, not an assumption.
        "complete": bool(completions),
        "slot": slot,
    }
    if trades:
        last = trades[-1]["fields"]
        # The terminal state of the transaction: the LAST trade's post-trade reserves.
        state["virtual_quote"] = last.get("virtual_quote_reserves", last.get(
            "virtual_sol_reserves", state["virtual_quote"]))
        state["virtual_token"] = last.get("virtual_token_reserves", state["virtual_token"])
        state["real_token"] = last.get("real_token_reserves", state["real_token"])
        state["real_quote"] = last.get("real_quote_reserves", last.get("real_sol_reserves"))
    missing = [name for name in PILOT.B10B_STATE_FIELDS
               if state.get(name) is None]
    return state, missing, len(trades)


def build_decoder():
    """The pinned IDL, indexed by discriminator, through B7d's own helpers."""
    b7d, discriminator, create_type, types = PILOT.load_pinned_create_type()
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    by_discriminator = {}
    for event in idl.get("events", []):
        if "discriminator" in event:
            by_discriminator[bytes(event["discriminator"]).hex()] = event["name"]
    return {"b7d": b7d, "create_discriminator": discriminator, "types": types,
            "by_discriminator": by_discriminator}


def validate_response(response, signature, slot):
    """Every failure rule that can be judged from the response itself, before anything is derived."""
    result = response.get("result") or {}
    transaction = result.get("transaction") or {}
    signatures = transaction.get("signatures") or []
    if signatures and signatures[0] != signature:
        raise BackfillRefused(f"{F01_SIGNATURE_MISMATCH}: {signatures[0]} != {signature}")
    if result.get("slot") is not None and slot is not None and result["slot"] != slot:
        raise BackfillRefused(f"{F02_SLOT_MISMATCH}: {result['slot']} != {slot}")
    meta = result.get("meta") or {}
    if meta.get("err") is not None:
        raise BackfillRefused(f"{F04_TRANSACTION_FAILED}: a failed transaction launched nothing")
    context_slot = (response.get("context") or {}).get("slot")
    if context_slot is not None and slot is not None and context_slot < slot:
        raise BackfillRefused(f"{F07_STALE_RESPONSE}: context slot {context_slot} precedes {slot}")
    return result.get("slot")


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------

def evidence_hash(record):
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def record_decision(connection, launch_seq, signature, state, missing, trades, availability):
    """A NEW decision at version 2. The feed-only decision is never rewritten."""
    wall, mono = time.time(), time.monotonic_ns()
    if missing:
        result, reason = PILOT.RESULT_NO_ENTRY, U01_REAL_QUOTE_NOT_PUBLISHED
        detail = ",".join(missing)
    else:
        vetoes = PILOT.b11b_vetoes({"quote_mint": state.get("quote_mint")}, state)
        if vetoes:
            result, reason, detail = PILOT.RESULT_NO_ENTRY, PILOT.S04_VETO, ",".join(vetoes)
        else:
            # Every t0 input is present and no veto fired. The entry is still NOT priced, because
            # fee, priority fee, tip and latency were not stated by any caller and the freeze
            # forbids defaulting them: a default cost is a number nobody measured standing where a
            # measurement belongs.
            result, reason, detail = PILOT.RESULT_NO_ENTRY, U04_COST_INPUTS_UNSTATED, None
    previous = connection.execute(
        "SELECT decision_seq FROM decision_v2 WHERE signature=? ORDER BY version DESC LIMIT 1",
        (signature,)).fetchone()
    record = {"launch_seq": launch_seq, "signature": signature, "result": result,
              "reason": reason, "detail": detail, "state": state}
    connection.execute(
        "INSERT OR IGNORE INTO decision_v2(launch_seq,signature,version,supersedes_decision_seq,"
        "policy_id,decided_wall_unix,decided_monotonic_ns,evidence_basis,feature_availability,"
        "policy_result,reason_code,hypothetical_quote_lamports,simulated_entry,"
        "outcome_placeholder,evidence_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (launch_seq, signature, 2, previous[0] if previous else None, B11B.PRIMARY_POLICY,
         wall, mono, BASIS_BACKFILLED, json.dumps(availability, sort_keys=True), result,
         reason if detail is None else f"{reason}:{detail}",
         B11B.ORDER_SIZE_LAMPORTS if result == PILOT.RESULT_PROPOSED else None,
         None, None, evidence_hash(record)))
    return result, reason


def run(limit=None, b15a_path=B15A_DB, work_dir=WORK_DIR, opener=None, sleeper=time.sleep,
        url=None):
    """Backfill every pending decoded launch, once each, within the frozen rate policy."""
    assert_no_execution_surface()
    assert_isolated(work_dir)
    document = verify_preregistration()
    policy = document
    rate = document["rate_and_stopping_policy"]
    url = rate and (url or rpc_url())
    receipt = endpoint_receipt(url)
    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)
    connection = open_database(pathlib.Path(work_dir) / "backfill.sqlite")
    exchanges = ExchangeLog(pathlib.Path(work_dir) / "rpc_exchanges.jsonl")
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("preregistration_id", document["preregistration_id"]),
                       ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                       ("endpoint_scheme_host", receipt),
                       ("execution_status", "never_executed"),
                       ("performance_status", "not_evaluated")):
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, str(value)))
    connection.commit()

    decoder = build_decoder()
    budget = min(rate["max_requests_per_run"], limit or rate["max_requests_per_run"])
    pending = pending_signatures(b15a_path, pathlib.Path(work_dir) / "backfill.sqlite", budget)
    interval = rate["min_interval_ms"] / 1000.0
    counts = {"attempted": 0, "retrieved": 0, "unavailable": 0, "failed": 0,
              "state_complete": 0, "hypothetical_entries": 0}
    latencies = []
    reasons = {}
    last_request = None
    try:
        for launch_seq, signature, slot, mint, curve in pending:
            if last_request is not None:
                # Conservative and fixed before any throughput was observed.
                elapsed = time.monotonic() - last_request
                if elapsed < interval:
                    sleeper(interval - elapsed)
            last_request = time.monotonic()
            counts["attempted"] += 1
            outcome, payload, latency_ns = fetch_transaction(
                signature, url, policy, exchanges, opener=opener, sleeper=sleeper)
            latencies.append(latency_ns)
            status_value = STATUS_FAILED
            reason = None
            state = missing = None
            trades = 0
            context_slot = None
            try:
                if outcome != "retrieved":
                    status_value = STATUS_UNAVAILABLE
                    reason = U03_RPC_EXHAUSTED
                else:
                    context_slot = validate_response(payload, signature, slot)
                    events = curve_events(payload, decoder)
                    state, missing, trades = derive_t0_state(events, mint, slot)
                    status_value = STATUS_RETRIEVED if not missing else STATUS_UNAVAILABLE
                    reason = None if not missing else U01_REAL_QUOTE_NOT_PUBLISHED
            except BackfillRefused as error:
                # Fails VISIBLY: the exchange is already preserved, the code is recorded, and the
                # decision is not advanced.
                status_value = STATUS_FAILED
                reason = str(error).split(":", 1)[0]
            counts[status_value if status_value in counts else "failed"] += 1
            reasons[reason or "none"] = reasons.get(reason or "none", 0) + 1
            connection.execute(
                "INSERT OR REPLACE INTO backfill(signature,launch_seq,slot,mint,bonding_curve,"
                "attempts,status,unavailable_reason,latency_ns,context_slot,commitment,"
                "evidence_sha256,backfilled_at_wall_unix) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (signature, launch_seq, slot, mint, curve, 1, status_value, reason, latency_ns,
                 context_slot, document["transport"]["commitment"],
                 evidence_hash({"signature": signature, "status": status_value,
                                "reason": reason}), time.time()))
            if state is not None:
                if not missing:
                    counts["state_complete"] += 1
                connection.execute(
                    "INSERT OR REPLACE INTO t0_state(signature,virtual_quote,virtual_token,"
                    "real_quote,real_token,quote_mint,mayhem_mode,complete,slot,"
                    "trade_count_in_launch_tx,provenance,missing_fields,evidence_sha256) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (signature, state.get("virtual_quote"), state.get("virtual_token"),
                     state.get("real_quote"), state.get("real_token"), state.get("quote_mint"),
                     int(bool(state.get("mayhem_mode"))), int(bool(state.get("complete"))),
                     state.get("slot"), trades, "launch_transaction_events",
                     json.dumps(sorted(missing)), evidence_hash(state)))
                availability = {"state_fields_supplied": sorted(k for k, v in state.items()
                                                                if v is not None),
                                "state_fields_missing": sorted(missing),
                                "trade_count_in_launch_tx": trades,
                                "evidence_basis": BASIS_BACKFILLED}
                result, _reason = record_decision(connection, launch_seq, signature, state,
                                                  missing, trades, availability)
                if result == PILOT.RESULT_PROPOSED:
                    counts["hypothetical_entries"] += 1
            connection.commit()
    finally:
        exchanges.close()
        connection.close()
    latencies.sort()
    counts["latency_ns"] = _summary(latencies)
    counts["reasons"] = dict(sorted(reasons.items()))
    counts["endpoint_scheme_host"] = receipt
    return counts


def _summary(values):
    """Exact integer order statistics. No float, no interpolation between neighbours."""
    if not values:
        return {"count": 0}
    def at(fraction_numerator, fraction_denominator):
        index = (len(values) - 1) * fraction_numerator // fraction_denominator
        return values[index]
    return {"count": len(values), "min": values[0], "p50": at(1, 2), "p90": at(9, 10),
            "p99": at(99, 100), "max": values[-1]}


def status(db_path=DB_PATH):
    if not pathlib.Path(db_path).exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started"}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        meta = dict(connection.execute("SELECT key, value FROM metadata"))
        statuses = dict(connection.execute(
            "SELECT status, COUNT(*) FROM backfill GROUP BY 1"))
        reasons = dict(connection.execute(
            "SELECT COALESCE(unavailable_reason,'none'), COUNT(*) FROM backfill GROUP BY 1"))
        decisions = dict(connection.execute(
            "SELECT COALESCE(reason_code,'none'), COUNT(*) FROM decision_v2 GROUP BY 1"))
        states = connection.execute("SELECT COUNT(*) FROM t0_state").fetchone()[0]
        complete_states = connection.execute(
            "SELECT COUNT(*) FROM t0_state WHERE missing_fields='[]'").fetchone()[0]
        with_trade = connection.execute(
            "SELECT COUNT(*) FROM t0_state WHERE trade_count_in_launch_tx > 0").fetchone()[0]
        latencies = [row[0] for row in connection.execute(
            "SELECT latency_ns FROM backfill WHERE latency_ns IS NOT NULL ORDER BY latency_ns")]
    finally:
        connection.close()
    report = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": meta.get("preregistration_id"),
        "endpoint_scheme_host": meta.get("endpoint_scheme_host"),
        "execution_status": meta.get("execution_status"),
        "performance_status": meta.get("performance_status"),
        "backfill_status_counts": statuses,
        "unavailable_reason_counts": reasons,
        "decision_reason_counts": decisions,
        "t0_states_derived": states,
        "t0_states_complete": complete_states,
        "launches_with_a_trade_in_the_launch_tx": with_trade,
        "latency_ns": _summary(latencies),
        "reads_only": True,
    }
    PILOT.assert_redacted(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true", help="verify the freeze and the gates")
    parser.add_argument("--status", action="store_true", help="redacted backfill status")
    parser.add_argument("--run", action="store_true", help="backfill the pending launches")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    if args.contract:
        document = verify_preregistration()
        assert_no_execution_surface()
        assert_isolated()
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "preregistration_id": document["preregistration_id"],
            "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
            "execution_surface": "absent",
            "reads_only": True,
            "real_quote_provable_when": document["provability_determination"]["real_quote"][
                "provable_when"],
            "complete_provable": document["provability_determination"]["complete"]["provable"],
        }, indent=2, sort_keys=True))
        return 0
    if args.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
        return 0
    if args.run:
        print(json.dumps(run(limit=args.limit), indent=2, sort_keys=True))
        return 0
    parser.error("nothing to do; --contract, --status or --run")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PILOT.PilotRefused as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
