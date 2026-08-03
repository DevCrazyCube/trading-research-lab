"""B15p — launch-transaction fee schedules for the frozen B15O 5,000, from a clean path.

Implements `research/B15P_NATIVE_FEE_BACKFILL_PREREGISTRATION.json`, committed alone before any
getTransaction request was sent.

**Why this exists.** B15O closed correctly and produced zero priced cells: 79,779 refusals for a
missing fee schedule. B15L decodes fees from B15b's preserved launch transactions, B15b's pending set
reads B15a's shadow database, and B15a closed at 5,000 launches whose last slot is 64,475 slots
before B15O's first member. That was my error in a document I wrote: B15O forbade b15a and b15f
artifact *paths*, and the dependency runs one hop further back through b15b.

**A path-string scan is not enough, and the measurement says so.** B15h builds its exchange-log path
as `ROOT / "research" / "b15b" / "rpc_exchanges.jsonl"`, so the literal `b15b/rpc_exchanges.jsonl`
never appears in any source file. So the static audit here walks the transitive module closure and
looks for forbidden DIRECTORY tokens — and the real check is at runtime, where every path this study
opens is recorded and a forbidden one refuses. A manifest states an intention; the runtime record
states what happened, and it does not care how a path was spelled.

**It computes no strategy quantity.** It ends at fee schedules.
"""
import argparse
import builtins
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15p"
DB_PATH = WORK_DIR / "fee_schedules.sqlite"
RAW_PATH = WORK_DIR / "rpc_exchanges.jsonl"
LOCK_PATH = WORK_DIR / "backfill.lock"

B15O_ARTIFACT = ROOT / "research" / "b15o" / "replication.json"
B15N_DB = ROOT / "research" / "b15n" / "exit_checkpoints.sqlite"
B15I_DB = ROOT / "research" / "b15i" / "processed_feed.sqlite"
PINNED_IDL = ROOT / "research" / "pump_idl_9c82f61.json"

PREREG_PATH = ROOT / "research" / "B15P_NATIVE_FEE_BACKFILL_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "72af534e22cdd5389074d2d9c41dc647464df7414166dd32956f1aaef99b65ec"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

# Credential material only. A provider's HOST NAME is not a secret, and the preregistration
# explicitly requires recording the endpoint's scheme and host — so a token list containing the host
# forbade the very thing the freeze mandates and refused the first live record.
SECRET_TOKENS = ("api-key", "api_key", "apikey", "authorization", "bearer ", "secret")

# Directory TOKENS, not assembled path strings. This is the whole lesson of B15O.
FORBIDDEN_DIRECTORY_TOKENS = ("b15a", "b15b", "b15f")

P_ARTIFACT_DRIFT = "P_ARTIFACT_DRIFT"
P_MEMBER_SET_DRIFT = "P_MEMBER_SET_DRIFT"
P_NOT_CONFIRMED = "P_NOT_CONFIRMED"
P_FORBIDDEN_DEPENDENCY = "P_FORBIDDEN_DEPENDENCY"
P_NOT_FOUND = "P_NOT_FOUND"
P_RPC_FAILED = "P_RPC_FAILED"
P_NO_CREATE_EVENT = "P_NO_CREATE_EVENT"
P_NO_TRADE_EVENT = "P_NO_TRADE_EVENT"
P_IDENTITY_MISMATCH = "P_IDENTITY_MISMATCH"
P_SCHEDULE_CONFLICT = "P_SCHEDULE_CONFLICT"
P_INCOMPLETE_SCHEDULE = "P_INCOMPLETE_SCHEDULE"
P_REPLAY_DIVERGED = "P_REPLAY_DIVERGED"
P_LOCK_HELD = "P_LOCK_HELD"
P_SECRET_IN_OUTPUT = "P_SECRET_IN_OUTPUT"

STATE_RETRIEVED = "retrieved"
STATE_NOT_FOUND = "not_found"
STATE_FAILED = "failed"
STATE_REFUSED = "refused"
TERMINAL_STATES = (STATE_RETRIEVED, STATE_NOT_FOUND, STATE_REFUSED)

LABEL = "NATIVE_FEE_BACKFILL"
PROGRAM_DATA_PREFIX = "Program data: "
RPC_ENV_VAR = "SOLANA_RPC_URL"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The pinned struct decoder, and the only clean root in the project's closure.
B7D = _load("b7d_create_enumerator", "b7d_create_enumerator.py")


class BackfillRefused(RuntimeError):
    """Nothing is written, and the reason is recorded rather than worked around."""


# --------------------------------------------------------------------------------------------
# The dependency audit — static closure, and the runtime record that actually decides
# --------------------------------------------------------------------------------------------

def module_closure(entry):
    """Every module reachable through the project's `_load` convention, transitively."""
    seen, stack = set(), [entry]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        path = SCRIPTS / name
        if not path.exists():
            continue
        stack.extend(re.findall(r'_load\(\s*"[^"]+"\s*,\s*"([^"]+\.py)"', path.read_text()))
    return seen


def code_string_constants(path):
    """Every string constant in a module's CODE, excluding comments and docstrings.

    Read from the AST rather than the text, and this distinction is the point. A directory name in a
    code string literal is a dependency; the same word in a comment or a docstring is documentation.
    A text scan cannot tell them apart, and on its first run this one flagged its own docstring for
    explaining the very dependency it exists to forbid.

    Comments are absent from the AST entirely. Docstrings are the leading string expression of a
    module, class or function, and are skipped explicitly.
    """
    import ast
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def _declared_token_literals(path):
    """The tokens a module declares AS FORBIDDEN are not a dependency on them."""
    import ast
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return set()
    declared = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if not names & {"FORBIDDEN_DIRECTORY_TOKENS", "FORBIDDEN_SOURCE_ARTIFACTS",
                        "FORBIDDEN_PATH_MARKERS", "SECRET_TOKENS",
                        "EXECUTION_SURFACE_TOKENS"}:
            continue
        for child in ast.walk(node.value):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                declared.add(child.value)
    return declared


def static_dependency_audit(entry="b15p_native_fee_backfill.py", document=None):
    """Report every forbidden DIRECTORY token in the transitive closure, and refuse the undeclared.

    Directory tokens rather than assembled paths, because B15h writes its b15b dependency as
    `ROOT / "research" / "b15b" / "rpc_exchanges.jsonl"` and no literal path string exists to find.
    That is precisely how B15O shipped with the dependency intact.
    """
    document = verify_preregistration() if document is None else document
    declared = {row["module"]: set(row["forbidden_references"])
                for row in document["forbidden_dependencies"]["static_audit"][
                    "declared_manifest"]}
    findings, undeclared = {}, {}
    for name in sorted(module_closure(entry)):
        path = SCRIPTS / name
        if not path.exists():
            continue
        declared_here = _declared_token_literals(path)
        literals = [value for value in code_string_constants(path)
                    if value not in declared_here]
        hits = sorted({token for token in FORBIDDEN_DIRECTORY_TOKENS
                       if any(token == value or f"/{token}/" in value or
                              value.endswith(f"/{token}") for value in literals)})
        if not hits:
            continue
        findings[name] = hits
        if name not in declared or not set(hits) <= declared[name]:
            undeclared[name] = hits
    if undeclared:
        raise BackfillRefused(
            f"{P_FORBIDDEN_DEPENDENCY}: undeclared forbidden references in the closure "
            f"{undeclared}; every one must be declared with the reason no data flows")
    # A declared module is only safe while this study never calls the function that reads.
    own = (SCRIPTS / entry).read_text()
    for row in document["forbidden_dependencies"]["static_audit"]["declared_manifest"]:
        alias = row["module"].removesuffix(".py")
        for function in row.get("forbidden_functions_never_called", ()):
            if re.search(rf'\b\w*{re.escape(alias.split("_")[0].upper())}\w*\.{function}\(', own):
                raise BackfillRefused(
                    f"{P_FORBIDDEN_DEPENDENCY}: this study calls {alias}.{function}, which the "
                    f"manifest declares it never calls")
    return {"closure": sorted(module_closure(entry)), "forbidden_references": findings,
            "all_declared": True}


class PathGuard:
    """Record every path this study opens, and refuse a forbidden one immediately.

    This is the check that would have caught B15O. A static manifest states an intention; this
    states what happened, and it does not care whether a path was spelled as a literal or assembled
    one component at a time.
    """

    def __init__(self, forbidden=FORBIDDEN_DIRECTORY_TOKENS):
        self.forbidden = tuple(forbidden)
        self.opened = []
        self._open = None
        self._io_open = None
        self._connect = None

    def _check(self, path):
        text = str(path)
        for token in self.forbidden:
            if f"research/{token}/" in text or f"research{os.sep}{token}{os.sep}" in text:
                raise BackfillRefused(
                    f"{P_FORBIDDEN_DEPENDENCY}: this study opened {text}, which lies under "
                    f"research/{token}; no data may flow from a closed recorder")
        self.opened.append(text)

    def __enter__(self):
        # `io.open` as well as `builtins.open`, because pathlib holds its own reference to io.open
        # and every Path.read_text and Path.write_text in this codebase would otherwise sail
        # straight past the guard. Found by a test that opened a file and saw nothing recorded.
        import io
        guard = self
        self._open, self._io_open, self._connect = builtins.open, io.open, sqlite3.connect

        def guarded_open(file, *args, **kwargs):
            guard._check(file)
            return guard._open(file, *args, **kwargs)

        def guarded_io_open(file, *args, **kwargs):
            guard._check(file)
            return guard._io_open(file, *args, **kwargs)

        def guarded_connect(database, *args, **kwargs):
            guard._check(database)
            return guard._connect(database, *args, **kwargs)

        builtins.open = guarded_open
        io.open = guarded_io_open
        sqlite3.connect = guarded_connect
        return self

    def __exit__(self, *_):
        import io
        builtins.open, io.open, sqlite3.connect = self._open, self._io_open, self._connect
        return False


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
        raise BackfillRefused(f"the backfill preregistration hashes {actual}, pinned {expected}")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    text = path.read_text()
    marker = "FORBIDDEN_DIRECTORY_TOKENS = (" if "FORBIDDEN_DIRECTORY_TOKENS = (" in text \
        else "EXECUTION_SURFACE_TOKENS = ("
    body = text.split(marker, 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise BackfillRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def scan_for_secrets(text, where):
    """Credential material, and a query string on any recorded endpoint.

    The positive check matters more than the token list: a receipt is scheme and host, so a "?" or an
    "=" in one means a query string survived, whatever its parameter happened to be called.
    """
    lowered = str(text).lower()
    found = sorted({token for token in SECRET_TOKENS if token in lowered})
    if found:
        raise BackfillRefused(f"{P_SECRET_IN_OUTPUT}: {where} contains {found}")
    import re as _re
    for receipt in _re.findall(r'"endpoint_scheme_host"\s*:\s*"([^"]*)"', str(text)):
        if "?" in receipt or "=" in receipt:
            raise BackfillRefused(
                f"{P_SECRET_IN_OUTPUT}: {where} records the endpoint as {receipt!r}, which carries "
                f"a query string; a receipt is scheme and host only")
    return True


def rpc_url():
    """From the environment only. A credential on a command line is visible to every user."""
    url = os.environ.get(RPC_ENV_VAR)
    if not url:
        raise BackfillRefused(
            f"{RPC_ENV_VAR} is not set; the credential is sourced from the environment and never "
            f"passed as an argument")
    return url


def endpoint_receipt(url):
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}"


# --------------------------------------------------------------------------------------------
# The pinned decode — same logic as B15h and B15L, applied to our own preserved responses
# --------------------------------------------------------------------------------------------

def load_pinned_types(idl_path=PINNED_IDL):
    """The pinned IDL's types and the two event discriminators, built exactly as B7d reads them.

    `{item["name"]: item}` — the whole IDL item per name, NOT the inner `type` — because b7d's
    `read_struct` reads `definition["type"]["fields"]`. B15a's own comment records what paraphrasing
    that mapping cost: two constructions of the same thing, agreeing until they did not.
    """
    try:
        idl = json.loads(pathlib.Path(idl_path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise BackfillRefused(f"cannot read the pinned IDL {idl_path}: {error}") from error
    types = {item["name"]: item for item in idl["types"]}
    events = {entry["name"]: entry for entry in idl.get("events", [])}
    for name in ("CreateEvent", "TradeEvent"):
        if name not in events or "discriminator" not in events[name]:
            raise BackfillRefused(
                f"the pinned IDL declares no {name} discriminator; refusing to guess its shape")
    return {"types": types,
            "create_discriminator": bytes(events["CreateEvent"]["discriminator"]),
            "trade_discriminator": bytes(events["TradeEvent"]["discriminator"]),
            "create_type": types["CreateEvent"], "trade_type": types["TradeEvent"]}


def program_data_payloads(logs):
    """Every `Program data:` payload, base64-decoded. A malformed line is skipped, not raised on.

    The provider emits logs from every program on the chain, so one unrelated malformed line must
    not stop a transaction from being read.
    """
    import base64
    import binascii
    payloads, skipped = [], 0
    for line in logs or ():
        if not isinstance(line, str) or not line.startswith(PROGRAM_DATA_PREFIX):
            continue
        try:
            payloads.append(base64.b64decode(line[len(PROGRAM_DATA_PREFIX):], validate=True))
        except (binascii.Error, ValueError):
            skipped += 1
    return payloads, skipped


def decode_events(payloads, pinned):
    """The CreateEvent and the fee-bearing TradeEvent from one transaction's log payloads.

    Both framings are handled: inner-instruction data carries the Anchor event-CPI tag before the
    discriminator, while `Program data:` lines carry the discriminator directly. Requiring the tag
    is what once made a live pilot examine 739 payloads and match none of them.
    """
    tag = bytes.fromhex("e445a52e51cb9a1d")
    create = trade = None
    for payload in payloads:
        body = payload[len(tag):] if payload.startswith(tag) else payload
        if create is None and body.startswith(pinned["create_discriminator"]):
            try:
                create = B7D.read_struct(
                    B7D.Cursor(body[len(pinned["create_discriminator"]):]),
                    pinned["create_type"], pinned["types"])
            except Exception:                                             # noqa: BLE001
                create = None
        elif trade is None and body.startswith(pinned["trade_discriminator"]):
            try:
                trade = B7D.read_struct(
                    B7D.Cursor(body[len(pinned["trade_discriminator"]):]),
                    pinned["trade_type"], pinned["types"])
            except Exception:                                             # noqa: BLE001
                trade = None
    return create, trade


def schedule_from_trade(trade):
    """The four fee fields, or a refusal. No default is ever substituted for a missing one."""
    schedule = {"fee_bps": trade.get("fee_basis_points"),
                "creator_fee_bps": trade.get("creator_fee_basis_points"),
                "cashback_fee_bps": trade.get("cashback_fee_basis_points"),
                "buyback_fee_bps": trade.get("buyback_fee_basis_points")}
    missing = sorted(name for name, value in schedule.items() if value is None)
    if missing:
        raise BackfillRefused(
            f"{P_INCOMPLETE_SCHEDULE}: the TradeEvent does not publish {missing}; B15C observed "
            f"fee_basis_points taking more than one value in a single sample, so no default exists")
    return schedule


def assert_identity(member, response, create, signature):
    """The transaction must be the member's, on all of signature, slot and mint.

    A transaction retrieved under one signature but describing another launch would attach one
    launch's fees to another, and nothing downstream could detect it.
    """
    result = response.get("result") or {}
    signatures = ((result.get("transaction") or {}).get("signatures")) or []
    if signature not in signatures:
        raise BackfillRefused(
            f"{P_IDENTITY_MISMATCH}: the response's signatures {signatures[:1]} do not include "
            f"{signature}")
    slot = result.get("slot")
    if slot != member["t0_slot"]:
        raise BackfillRefused(
            f"{P_IDENTITY_MISMATCH}: the transaction is at slot {slot} and the member is at "
            f"{member['t0_slot']}")
    if create is None:
        raise BackfillRefused(f"{P_NO_CREATE_EVENT}: no exactly decoded CreateEvent")
    if create.get("mint") != member["mint"]:
        raise BackfillRefused(
            f"{P_IDENTITY_MISMATCH}: the CreateEvent mints {create.get('mint')} and the member is "
            f"{member['mint']}")
    return True


# --------------------------------------------------------------------------------------------
# Membership — the artifact's, verified on three points and then pinned by hash
# --------------------------------------------------------------------------------------------

def member_set_hash(members):
    return hashlib.sha256(
        json.dumps(members, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_members(document=None, artifact_path=B15O_ARTIFACT, b15n_path=B15N_DB, b15i_path=B15I_DB):
    """The frozen 5,000, re-derived under the artifact's rule and verified against it.

    The artifact records the ordering rule, the size, the first member and the last member — not the
    roster. Three independent constraints on a deterministic derivation leave exactly one roster, and
    from the moment it is hashed the hash is the authority rather than the derivation.
    """
    document = verify_preregistration() if document is None else document
    frozen = document["the_frozen_member_set"]
    artifact_bytes = pathlib.Path(artifact_path).read_bytes()
    actual = hashlib.sha256(artifact_bytes).hexdigest()
    if actual != frozen["b15o_artifact_sha256"]:
        raise BackfillRefused(
            f"{P_ARTIFACT_DRIFT}: the B15O artifact hashes {actual}, pinned "
            f"{frozen['b15o_artifact_sha256']}")
    artifact = json.loads(artifact_bytes)
    population = artifact["population"]
    activation = 436_984_352
    connection = sqlite3.connect(f"file:{b15n_path}?mode=ro", uri=True, timeout=30)
    try:
        rows = connection.execute(
            "SELECT signature, MIN(t0_slot), MIN(mint) FROM schedule WHERE t0_slot > ? "
            "GROUP BY signature", (activation,)).fetchall()
    finally:
        connection.close()
    ordered = sorted(rows, key=lambda row: (row[1], row[0], row[2] or ""))
    members = [{"signature": r[0], "t0_slot": r[1], "mint": r[2]}
               for r in ordered[:population["members"]]]
    if len(members) != frozen["size"]:
        raise BackfillRefused(
            f"{P_MEMBER_SET_DRIFT}: derived {len(members)} members, pinned {frozen['size']}")
    for label, derived, claimed in (("first", members[0], population["first_member"]),
                                    ("last", members[-1], population["last_member"])):
        if derived != claimed:
            raise BackfillRefused(
                f"{P_MEMBER_SET_DRIFT}: the {label} derived member {derived} disagrees with the "
                f"artifact's {claimed}")
    digest = member_set_hash(members)
    if digest != frozen["member_set_sha256"]:
        raise BackfillRefused(
            f"{P_MEMBER_SET_DRIFT}: the roster hashes {digest}, pinned "
            f"{frozen['member_set_sha256']}")
    # Confirmed in B15i, or refused rather than fetched.
    connection = sqlite3.connect(f"file:{b15i_path}?mode=ro", uri=True, timeout=30)
    try:
        confirmed = {row[0] for row in connection.execute(
            "SELECT signature FROM observation WHERE fork_state='confirmed'")}
    finally:
        connection.close()
    unconfirmed = [m["signature"] for m in members if m["signature"] not in confirmed]
    return members, {"member_set_sha256": digest, "unconfirmed": unconfirmed}


# --------------------------------------------------------------------------------------------
# Storage and the single writer
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS fee_schedule (
  signature TEXT PRIMARY KEY, t0_slot INTEGER NOT NULL, mint TEXT NOT NULL,
  state TEXT NOT NULL, reason TEXT,
  fee_bps INTEGER, creator_fee_bps INTEGER, cashback_fee_bps INTEGER, buyback_fee_bps INTEGER,
  raw_sha256 TEXT, attempts INTEGER NOT NULL DEFAULT 0, latency_ns INTEGER,
  recorded_at_wall_unix REAL NOT NULL);
CREATE INDEX IF NOT EXISTS fee_state ON fee_schedule(state);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


class SingleWriter:
    """One backfill per work directory, or none.

    Two writers over one member set would interleave and neither could be resumed from, so the
    second refuses rather than taking its chances.
    """

    def __init__(self, path=LOCK_PATH):
        self.path = pathlib.Path(path)
        self.handle = None

    def __enter__(self):
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            self.handle = None
            raise BackfillRefused(
                f"{P_LOCK_HELD}: another writer holds {self.path}") from error
        return self

    def __exit__(self, *_):
        import fcntl
        if self.handle is not None:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
        return False


class RawLog:
    """Append-only. Every exchange lands here BEFORE any field of it is decoded."""

    def __init__(self, path=RAW_PATH):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = pathlib.Path(path)
        self.handle = open(self.path, "a", encoding="utf-8")

    def append(self, record):
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        scan_for_secrets(line, "raw exchange record")
        self.handle.write(line + "\n")
        self.handle.flush()
        return hashlib.sha256(line.encode()).hexdigest()

    def close(self):
        self.handle.close()


# --------------------------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------------------------

def _one_attempt(url, body, opener=None):
    """One HTTP round trip. Never raises upward: every failure is a returned outcome."""
    import urllib.error
    import urllib.request
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


def fetch_member(member, url, document, raw, opener=None, sleeper=time.sleep):
    """One getTransaction at confirmed. The exchange is preserved before the answer is judged."""
    retrieval = document["retrieval"]
    body = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [member["signature"],
                       {"commitment": retrieval["commitment"],
                        "maxSupportedTransactionVersion":
                            retrieval["max_supported_transaction_version"],
                        "encoding": "json"}]}
    started = time.monotonic_ns()
    outcome = payload = None
    attempts = 0
    raw_sha256 = None
    for attempt in range(retrieval["max_attempts_per_signature"]):
        attempts = attempt + 1
        outcome, status, payload = _one_attempt(url, body, opener)
        raw_sha256 = raw.append({
            "method": "getTransaction", "signature": member["signature"],
            "t0_slot": member["t0_slot"], "mint": member["mint"], "attempt": attempts,
            "outcome": outcome, "http_status": status,
            "endpoint_scheme_host": endpoint_receipt(url),
            "request_json": body, "response_json_or_error": payload,
            "at_wall_unix": time.time()})
        if outcome in ("retrieved", "not_found"):
            break
        if attempts < retrieval["max_attempts_per_signature"]:
            sleeper(1.0 / retrieval["max_requests_per_second"])
    return {"outcome": outcome, "payload": payload, "attempts": attempts,
            "raw_sha256": raw_sha256, "latency_ns": time.monotonic_ns() - started}


def schedule_for_member(member, fetched, pinned):
    """The member's fee schedule, or a refusal naming exactly what failed."""
    if fetched["outcome"] == "not_found":
        raise BackfillRefused(
            f"{P_NOT_FOUND}: the node has no confirmed transaction for {member['signature']}")
    if fetched["outcome"] != "retrieved":
        raise BackfillRefused(
            f"{P_RPC_FAILED}: {fetched['outcome']} after {fetched['attempts']} attempts")
    response = fetched["payload"]
    logs = (((response.get("result") or {}).get("meta") or {}).get("logMessages")) or []
    payloads, _skipped = program_data_payloads(logs)
    create, trade = decode_events(payloads, pinned)
    assert_identity(member, response, create, member["signature"])
    if trade is None:
        raise BackfillRefused(
            f"{P_NO_TRADE_EVENT}: no TradeEvent carrying fee basis points in the launch transaction")
    return schedule_from_trade(trade)


# --------------------------------------------------------------------------------------------
# The run, resumable and idempotent
# --------------------------------------------------------------------------------------------

def record(connection, member, state, reason=None, schedule=None, fetched=None):
    """One terminal row per member. A repeat of a terminal member is ignored, never overwritten."""
    existing = connection.execute(
        "SELECT state, fee_bps, creator_fee_bps, cashback_fee_bps, buyback_fee_bps "
        "FROM fee_schedule WHERE signature=?", (member["signature"],)).fetchone()
    if existing is not None and existing[0] in TERMINAL_STATES:
        if state == STATE_RETRIEVED and existing[0] == STATE_RETRIEVED and schedule is not None:
            previous = {"fee_bps": existing[1], "creator_fee_bps": existing[2],
                        "cashback_fee_bps": existing[3], "buyback_fee_bps": existing[4]}
            if previous != schedule:
                # Two disagreeing schedules for one member. Neither is chosen.
                raise BackfillRefused(
                    f"{P_SCHEDULE_CONFLICT}: {member['signature']} already has {previous} and this "
                    f"read gives {schedule}")
        return False
    connection.execute(
        "INSERT OR REPLACE INTO fee_schedule(signature,t0_slot,mint,state,reason,fee_bps,"
        "creator_fee_bps,cashback_fee_bps,buyback_fee_bps,raw_sha256,attempts,latency_ns,"
        "recorded_at_wall_unix) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (member["signature"], member["t0_slot"], member["mint"], state, reason,
         (schedule or {}).get("fee_bps"), (schedule or {}).get("creator_fee_bps"),
         (schedule or {}).get("cashback_fee_bps"), (schedule or {}).get("buyback_fee_bps"),
         (fetched or {}).get("raw_sha256"), (fetched or {}).get("attempts", 0),
         (fetched or {}).get("latency_ns"), time.time()))
    connection.commit()
    return True


def pending_members(connection, members):
    """Members with no terminal record yet, in the frozen order. Resume reads this and nothing else."""
    done = {row[0] for row in connection.execute(
        "SELECT signature FROM fee_schedule WHERE state IN (?,?,?)", TERMINAL_STATES)}
    return [member for member in members if member["signature"] not in done]


def run(work_dir=WORK_DIR, url=None, document=None, limit=None, opener=None, sleeper=time.sleep,
        artifact_path=B15O_ARTIFACT, b15n_path=B15N_DB, b15i_path=B15I_DB, guard=True):
    """Backfill the pending members at the frozen rate. Every outcome lands in the database."""
    assert_no_execution_surface()
    document = verify_preregistration() if document is None else document
    audit = static_dependency_audit(document=document)
    members, meta = load_members(document, artifact_path, b15n_path, b15i_path)
    unconfirmed = set(meta["unconfirmed"])
    pinned = load_pinned_types()
    work_dir = pathlib.Path(work_dir)
    url = url or rpc_url()
    rate = document["retrieval"]["max_requests_per_second"]
    counts = {"members": len(members), "requests": 0, "member_set_sha256":
              meta["member_set_sha256"], "dependency_audit_clean": not audit[
                  "forbidden_references"]}
    with SingleWriter(work_dir / "backfill.lock"):
        connection = open_database(work_dir / "fee_schedules.sqlite")
        raw = RawLog(work_dir / "rpc_exchanges.jsonl")
        for key, value in (("schema_version", SCHEMA_VERSION),
                           ("preregistration_id", document["preregistration_id"]),
                           ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                           ("b15o_artifact_sha256",
                            document["the_frozen_member_set"]["b15o_artifact_sha256"]),
                           ("member_set_sha256", meta["member_set_sha256"]),
                           ("rpc_endpoint_receipt", endpoint_receipt(url)),
                           ("label", LABEL)):
            connection.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)",
                               (key, value))
        connection.commit()
        try:
            pending = pending_members(connection, members)
            counts["pending_at_start"] = len(pending)
            if limit is not None:
                pending = pending[:limit]
            for index, member in enumerate(pending):
                if member["signature"] in unconfirmed:
                    record(connection, member, STATE_REFUSED,
                           f"{P_NOT_CONFIRMED}: B15i fork_state is not confirmed")
                    counts[P_NOT_CONFIRMED] = counts.get(P_NOT_CONFIRMED, 0) + 1
                    continue
                if index:
                    sleeper(1.0 / rate)
                fetched = fetch_member(member, url, document, raw, opener, sleeper)
                counts["requests"] += fetched["attempts"]
                try:
                    schedule = schedule_for_member(member, fetched, pinned)
                except BackfillRefused as error:
                    code = str(error).split(":", 1)[0]
                    state = STATE_NOT_FOUND if code == P_NOT_FOUND else (
                        STATE_FAILED if code == P_RPC_FAILED else STATE_REFUSED)
                    record(connection, member, state, str(error)[:240], None, fetched)
                    counts[code] = counts.get(code, 0) + 1
                    continue
                record(connection, member, STATE_RETRIEVED, None, schedule, fetched)
                counts[STATE_RETRIEVED] = counts.get(STATE_RETRIEVED, 0) + 1
        finally:
            raw.close()
            report = census(connection, members)
            connection.close()
    return counts, report


def census(connection, members=None):
    """Coverage only. No strategy quantity of any kind, and a test greps for one."""
    def query(sql, args=()):
        return connection.execute(sql, args).fetchall()

    total = len(members) if members is not None else None
    states = dict(query("SELECT state, COUNT(*) FROM fee_schedule GROUP BY state"))
    terminal = sum(count for state, count in states.items() if state in TERMINAL_STATES)
    report = {"schema_version": SCHEMA_VERSION, "label": LABEL, "executable": False,
              "performance_status": "not_evaluated", "execution_status": "never_executed",
              "members": total, "states": states, "terminal": terminal,
              "remaining": (total - terminal) if total is not None else None,
              "complete": (total is not None and terminal == total),
              "refusals": dict(query(
                  "SELECT substr(reason,1,instr(reason||':',':')-1), COUNT(*) FROM fee_schedule "
                  "WHERE reason IS NOT NULL GROUP BY 1")),
              "distinct_schedules": [
                  {"fee_bps": row[0], "creator_fee_bps": row[1], "cashback_fee_bps": row[2],
                   "buyback_fee_bps": row[3], "members": row[4]}
                  for row in query(
                      "SELECT fee_bps, creator_fee_bps, cashback_fee_bps, buyback_fee_bps, "
                      "COUNT(*) FROM fee_schedule WHERE state=? GROUP BY 1,2,3,4 "
                      "ORDER BY 5 DESC", (STATE_RETRIEVED,))]}
    latency = query("SELECT MIN(latency_ns), CAST(AVG(latency_ns) AS INTEGER), MAX(latency_ns) "
                    "FROM fee_schedule WHERE latency_ns IS NOT NULL")
    report["latency_ns"] = ({"min": latency[0][0], "mean_floor": latency[0][1],
                             "max": latency[0][2]} if latency and latency[0][0] is not None
                            else None)
    return report


def replay_schedules(raw_path=RAW_PATH, pinned=None):
    """Rebuild every schedule from the preserved raw responses alone."""
    pinned = load_pinned_types() if pinned is None else pinned
    path = pathlib.Path(raw_path)
    if not path.exists():
        raise BackfillRefused(f"no raw exchange log at {path} to replay from")
    rebuilt = {}
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("outcome") != "retrieved":
                continue
            response = entry.get("response_json_or_error")
            if not isinstance(response, dict):
                continue
            logs = (((response.get("result") or {}).get("meta") or {}).get("logMessages")) or []
            payloads, _skipped = program_data_payloads(logs)
            _create, trade = decode_events(payloads, pinned)
            if trade is None:
                continue
            try:
                rebuilt[entry["signature"]] = schedule_from_trade(trade)
            except BackfillRefused:
                continue
    return rebuilt


def assert_complete_and_replayable(work_dir=WORK_DIR, document=None, artifact_path=B15O_ARTIFACT,
                                  b15n_path=B15N_DB, b15i_path=B15I_DB):
    """Completeness, the member-set hash, and a replay of every schedule from raw. Fail-closed."""
    document = verify_preregistration() if document is None else document
    members, meta = load_members(document, artifact_path, b15n_path, b15i_path)
    connection = open_database(pathlib.Path(work_dir) / "fee_schedules.sqlite")
    try:
        report = census(connection, members)
        stored = {row[0]: {"fee_bps": row[1], "creator_fee_bps": row[2],
                           "cashback_fee_bps": row[3], "buyback_fee_bps": row[4]}
                  for row in connection.execute(
                      "SELECT signature, fee_bps, creator_fee_bps, cashback_fee_bps, "
                      "buyback_fee_bps FROM fee_schedule WHERE state=?", (STATE_RETRIEVED,))}
    finally:
        connection.close()
    if not report["complete"]:
        raise BackfillRefused(
            f"the backfill is not complete: {report['terminal']} of {report['members']} members "
            f"terminal, {report['remaining']} remaining")
    rebuilt = replay_schedules(pathlib.Path(work_dir) / "rpc_exchanges.jsonl")
    diverged = {signature: {"stored": schedule, "rebuilt": rebuilt.get(signature)}
                for signature, schedule in stored.items() if rebuilt.get(signature) != schedule}
    if diverged:
        example = dict(list(diverged.items())[:2])
        raise BackfillRefused(
            f"{P_REPLAY_DIVERGED}: {len(diverged)} schedules could not be rebuilt from the "
            f"preserved responses, for example {example}")
    report["member_set_sha256"] = meta["member_set_sha256"]
    report["replayed_schedules"] = len(rebuilt)
    return report


def status(work_dir=WORK_DIR, document=None, artifact_path=B15O_ARTIFACT, b15n_path=B15N_DB,
           b15i_path=B15I_DB):
    path = pathlib.Path(work_dir) / "fee_schedules.sqlite"
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started", "label": LABEL}
    document = verify_preregistration() if document is None else document
    members, meta = load_members(document, artifact_path, b15n_path, b15i_path)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        report = census(connection, members)
    finally:
        connection.close()
    report["member_set_sha256"] = meta["member_set_sha256"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B15p B15i-native fee backfill (read-only against the chain, no strategy figure)")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--verify", action="store_true", help="completeness, hash and replay gate")
    parser.add_argument("--audit", action="store_true", help="the transitive dependency audit")
    parser.add_argument("--limit", type=int, default=None)
    arguments = parser.parse_args(argv)
    if arguments.audit:
        print(json.dumps(static_dependency_audit(), indent=2, sort_keys=True))
        return 0
    if arguments.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
        return 0
    if arguments.verify:
        try:
            print(json.dumps(assert_complete_and_replayable(), indent=2, sort_keys=True))
        except BackfillRefused as error:
            print(json.dumps({"refused": str(error)}, indent=2, sort_keys=True))
            return 1
        return 0
    # The runtime path guard wraps the whole run: a forbidden path opened anywhere refuses.
    with PathGuard():
        counts, report = run(limit=arguments.limit)
    print(json.dumps({"counts": counts, "census": report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
