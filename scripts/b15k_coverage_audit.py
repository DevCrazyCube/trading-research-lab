"""B15k — why does the processed feed see launches the confirmed recorder does not?

Implements `research/B15K_COVERAGE_AUDIT_PREREGISTRATION.json`, committed alone before any
comparison was computed and before any confirmation query was sent.

Two explanations fit the same observation and they are opposites. Either processed carries
transactions that confirmed never accepted — a property of the chain — or B15a under-records
launches that did confirm — a defect in our own instrument. The first would make the missing cells
correctly excluded; the second would mean we are discarding real launches and reporting the
discard as a fork rate.

**Only inside an interval both recorders have passed.** Outside it, absence from a recorder means
nothing except that the recorder has not got there yet. Comparing across an open edge measures lag
and calls it a miss, which is exactly how 112 launches were once marked orphaned.

**Absence is never renamed.** `ABSENT_FROM_B15A` stays an open question with a name until an
independent query answers it. An orphan is a claim about the chain; an absence is a fact about our
recorder, and letting the second become the first turns an instrument defect into a finding.
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

WORK_DIR = ROOT / "research" / "b15k"
B15A_DB = ROOT / "research" / "b15a" / "shadow.sqlite"
B15I_DB = ROOT / "research" / "b15i" / "processed_feed.sqlite"

PREREG_PATH = ROOT / "research" / "B15K_COVERAGE_AUDIT_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "7a3d79487838ce368819203523eb12d077d3212ef0b17521a936193ccfe1f5f8"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

K_INTERVAL_EMPTY = "K_INTERVAL_EMPTY"
K_RECORDER_UNREADABLE = "K_RECORDER_UNREADABLE"
K_OUTSIDE_INTERVAL = "K_OUTSIDE_INTERVAL"
K_QUERY_FAILED = "K_QUERY_FAILED"
K_SAMPLE_NOT_DETERMINISTIC = "K_SAMPLE_NOT_DETERMINISTIC"

CORROBORATED = "CORROBORATED"
B15A_DECODE_FAILED = "B15A_DECODE_FAILED"
B15A_SAW_NON_LAUNCH = "B15A_SAW_NON_LAUNCH"
ABSENT_FROM_B15A = "ABSENT_FROM_B15A"

CONFIRMED_ON_CHAIN = "CONFIRMED_ON_CHAIN"
NOT_FOUND_AT_CONFIRMED = "NOT_FOUND_AT_CONFIRMED"
QUERY_FAILED = "QUERY_FAILED"

COVERAGE_STATEMENT = ("every coverage figure is conditional on the observing feed; neither "
                      "recorder establishes what neither saw")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15B = _load("b15b_backfill", "b15b_backfill.py")


class CoverageRefused(RuntimeError):
    """The audit will not conclude, and says what is missing rather than assuming it."""


def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise CoverageRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise CoverageRefused(f"the coverage preregistration hashes {actual}, pinned {expected}")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = path.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise CoverageRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def _read_only(path):
    path = pathlib.Path(path)
    if not path.exists():
        raise CoverageRefused(f"{K_RECORDER_UNREADABLE}: no recorder at {path}")
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error as error:
        raise CoverageRefused(f"{K_RECORDER_UNREADABLE}: {path}: {error}") from error


# --------------------------------------------------------------------------------------------
# The common closed interval
# --------------------------------------------------------------------------------------------

def recorder_extent(connection, queries):
    """(min, max) slot this recorder demonstrably covers, across every table that carries slots.

    The MAXIMUM is taken across tables because a recorder that has seen a million trades and no
    launches has still reached that slot. Using the launch table alone would understate B15a's
    progress and manufacture a miss out of a quiet stretch.
    """
    lows, highs = [], []
    for query in queries:
        try:
            low, high = connection.execute(query).fetchone()
        except sqlite3.Error:
            continue
        if low is not None:
            lows.append(low)
        if high is not None:
            highs.append(high)
    if not lows or not highs:
        return None, None
    return min(lows), max(highs)


def common_closed_interval(b15i_extent, b15a_extent, margin):
    """[lo, hi] both recorders have passed, or a refusal. Never an open edge."""
    if None in b15i_extent or None in b15a_extent:
        raise CoverageRefused(
            f"{K_INTERVAL_EMPTY}: a recorder reports no slots at all "
            f"(b15i={b15i_extent}, b15a={b15a_extent})")
    low = max(b15i_extent[0], b15a_extent[0]) + margin
    high = min(b15i_extent[1], b15a_extent[1]) - margin
    if high <= low:
        raise CoverageRefused(
            f"{K_INTERVAL_EMPTY}: after a {margin}-slot closure margin the recorders share no "
            f"interval (b15i={b15i_extent}, b15a={b15a_extent}). Comparing anyway would measure "
            f"lag and report it as a miss.")
    return low, high


# --------------------------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------------------------

def b15a_index(connection):
    """What B15a knows about each signature: decoded, decode-failed, or non-launch only."""
    launches = {}
    for signature, status in connection.execute(
            "SELECT signature, decode_status FROM launch"):
        # A decoded row wins over a failed one for the same signature; the launch WAS read.
        if launches.get(signature) != "decoded":
            launches[signature] = status
    events = set()
    try:
        events = {row[0] for row in connection.execute(
            "SELECT DISTINCT signature FROM pump_event")}
    except sqlite3.Error:
        pass
    return launches, events


def classify(signature, slot, interval, launches, events):
    low, high = interval
    if not low <= slot <= high:
        raise CoverageRefused(
            f"{K_OUTSIDE_INTERVAL}: slot {slot} is outside the common closed interval "
            f"[{low}, {high}]; absence there says nothing about either recorder")
    status = launches.get(signature)
    if status == "decoded":
        return CORROBORATED
    if status is not None:
        return B15A_DECODE_FAILED
    if signature in events:
        return B15A_SAW_NON_LAUNCH
    # Not renamed. An orphan is a claim about the chain; this is a fact about our recorder.
    return ABSENT_FROM_B15A


def select_sample(signatures, size):
    """Deterministic, reproducible, and fixed before any result was seen.

    Ordered by SHA-256 of the signature so the choice is independent of slot, arrival time and
    base58 prefix clustering. Re-running on the same population selects the same launches.
    """
    ordered = sorted(set(signatures), key=lambda s: hashlib.sha256(s.encode()).hexdigest())
    return ordered[:size]


# --------------------------------------------------------------------------------------------
# Independent confirmation — bounded, rate limited, raw preserved
# --------------------------------------------------------------------------------------------

def confirm_signature(signature, url, policy, exchanges, opener=None, sleeper=time.sleep):
    """Did this transaction reach CONFIRMED commitment? Asked of the chain, not of B15a.

    The raw exchange is written before the answer is judged, so a later disagreement about what
    the node said is settled by the record rather than by memory.
    """
    body = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [signature, {"commitment": policy["commitment"],
                                   "maxSupportedTransactionVersion":
                                       policy["max_supported_transaction_version"],
                                   "encoding": "json"}]}
    outcome = payload = None
    for attempt in range(policy["max_attempts_per_signature"]):
        started = time.monotonic_ns()
        outcome, status, payload = B15B._one_attempt(url, body, opener)
        exchanges.append({"method": "getTransaction", "signature": signature,
                          "attempt": attempt + 1, "outcome": outcome, "http_status": status,
                          "round_trip_ns": time.monotonic_ns() - started, "response": payload})
        if outcome in ("retrieved", "not_found"):
            break
        sleeper(1.0 / policy["rate_limit_requests_per_second"])
    if outcome == "retrieved":
        return CONFIRMED_ON_CHAIN, payload
    if outcome == "not_found":
        # The node has no confirmed transaction. CONSISTENT WITH a processed-only fork, and
        # reported as that rather than as proof of one: a node can also simply not have it.
        return NOT_FOUND_AT_CONFIRMED, payload
    return QUERY_FAILED, payload


# --------------------------------------------------------------------------------------------
# The audit
# --------------------------------------------------------------------------------------------

def audit(document=None, b15i_path=B15I_DB, b15a_path=B15A_DB, work_dir=WORK_DIR, url=None,
          opener=None, sleeper=time.sleep, sample_size=None, query=True):
    assert_no_execution_surface()
    document = verify_preregistration() if document is None else document
    margin = document["the_common_closed_interval"]["closure_margin_slots"]
    sampling = document["independent_confirmation_sample"]
    policy = sampling["query"]        # the query settings are nested; the sample size is not
    size = sampling["sample_size"] if sample_size is None else sample_size

    processed = _read_only(b15i_path)
    confirmed = _read_only(b15a_path)
    try:
        b15i_extent = recorder_extent(processed, ("SELECT MIN(t0_slot), MAX(t0_slot) "
                                                  "FROM observation",))
        b15a_extent = recorder_extent(confirmed, ("SELECT MIN(slot), MAX(slot) FROM launch",
                                                  "SELECT MIN(slot), MAX(slot) FROM pump_event"))
        interval = common_closed_interval(b15i_extent, b15a_extent, margin)
        launches, events = b15a_index(confirmed)
        comparable = processed.execute(
            "SELECT signature, t0_slot FROM observation WHERE t0_slot BETWEEN ? AND ?",
            interval).fetchall()
    finally:
        processed.close()
        confirmed.close()

    classes, absent = {}, []
    for signature, slot in comparable:
        label = classify(signature, slot, interval, launches, events)
        classes[label] = classes.get(label, 0) + 1
        if label == ABSENT_FROM_B15A:
            absent.append(signature)

    report = {"schema_version": SCHEMA_VERSION, "label": document["status_locks"]["label"],
              "b15i_extent": list(b15i_extent), "b15a_extent": list(b15a_extent),
              "closure_margin_slots": margin, "common_closed_interval": list(interval),
              "comparable_launches": len(comparable), "classes": classes,
              "coverage_statement": COVERAGE_STATEMENT,
              "performance_status": "not_evaluated", "execution_status": "never_executed"}

    sample = select_sample(absent, size)
    report["absent_population"] = len(absent)
    report["sample_size"] = len(sample)
    report["sample_selection"] = "ascending sha256 of the signature, first N"
    if not query or not sample:
        report["sample_outcomes"] = {}
        report["conclusion"] = "not_queried"
        return report

    work_dir = pathlib.Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    exchanges = B15B.ExchangeLog(work_dir / "rpc_exchanges.jsonl")
    url = url or B15B.rpc_url()
    report["rpc_endpoint_receipt"] = B15B.endpoint_receipt(url)
    outcomes, evidence = {}, []
    interval_seconds = 1.0 / policy["rate_limit_requests_per_second"]
    for index, signature in enumerate(sample):
        if index:
            sleeper(interval_seconds)      # bounded rate: B15h was killed by HTTP 429
        outcome, _payload = confirm_signature(signature, url, policy, exchanges, opener, sleeper)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        evidence.append({"signature": signature, "outcome": outcome})
    report["sample_outcomes"] = outcomes
    report["conclusion"] = conclude(outcomes)
    (work_dir / "sample_outcomes.json").write_text(
        json.dumps({"report": report, "evidence": evidence}, indent=2, sort_keys=True))
    return report


def conclude(outcomes):
    """What the sample licenses, and nothing more."""
    decided = outcomes.get(CONFIRMED_ON_CHAIN, 0) + outcomes.get(NOT_FOUND_AT_CONFIRMED, 0)
    if not decided:
        return "undecided: no query completed"
    confirmed_share = outcomes.get(CONFIRMED_ON_CHAIN, 0) / decided
    if confirmed_share >= 0.9:
        return ("b15a_under_records: the sampled launches DID confirm on chain, so B15a must not "
                "be the sole confirmation oracle")
    if confirmed_share <= 0.1:
        return ("processed_only: the sampled launches have no confirmed transaction, consistent "
                "with processed-only forks; B15a is behaving correctly")
    return ("mixed: both a confirmed-feed miss and a processed-only population are present; both "
            "counts are published and no single explanation is asserted")


def main(argv=None):
    parser = argparse.ArgumentParser(description="B15k coverage audit (read-only, no execution)")
    parser.add_argument("--no-query", action="store_true", help="classify only, send nothing")
    parser.add_argument("--sample-size", type=int, default=None)
    arguments = parser.parse_args(argv)
    report = audit(sample_size=arguments.sample_size, query=not arguments.no_query)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
