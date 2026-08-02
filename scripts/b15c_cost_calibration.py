"""B15c — contemporaneous execution-cost calibration from observed Pump buys. Read-only.

Implements `research/B15C_COST_CALIBRATION_PREREGISTRATION.json`, committed alone before any cost
transaction was fetched and before any scenario value existed.

It samples successful Pump buys deterministically from B15a's append-only raw log, fetches each
sampled transaction once, and decomposes its cost into exact integer components. Nothing is
constructed, simulated or sent, and no key is held.

**The observed cost of another trader's transaction is not the cost of a route we might choose.**
A quantile of what others paid is calibration evidence, not a quote and not a landing probability.
Every scenario this produces is labelled SIMULATED_SHADOW and is non-executable.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15c"
EXCHANGE_PATH = WORK_DIR / "rpc_exchanges.jsonl"
DB_PATH = WORK_DIR / "calibration.sqlite"
B15A_RAW = ROOT / "research" / "b15a" / "raw_frames.jsonl"

PREREG_PATH = ROOT / "research" / "B15C_COST_CALIBRATION_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "53a26143486e1d62eeefa985460b96ee438451e4ad843a646d4dde89012eeea9"

LAMPORTS_PER_SIGNATURE = 5000
MICRO_LAMPORTS_PER_LAMPORT = 1_000_000

COMPUTE_BUDGET_PROGRAM = "ComputeBudget111111111111111111111111111111"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
# ComputeBudget instruction discriminators, single leading byte.
CB_SET_UNIT_LIMIT = 0x02
CB_SET_UNIT_PRICE = 0x03

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

C01_TRANSACTION_FAILED = "C01_transaction_failed"
C02_NO_BUY_TRADE_EVENT = "C02_no_buy_trade_event"
C03_COMPUTE_BUDGET_UNDECODABLE = "C03_compute_budget_undecodable"
C04_RPC_EXHAUSTED = "C04_rpc_exhausted"
C05_DECOMPOSITION_MISMATCH = "C05_decomposition_mismatch"
C06_DUPLICATE_SIGNATURE = "C06_duplicate_signature"
C07_RESPONSE_INCONSISTENT = "C07_response_inconsistent"

SCENARIO_LABEL = "SIMULATED_SHADOW"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15B = _load("b15b_backfill", "b15b_backfill.py")
PILOT = B15B.PILOT


class CalibrationRefused(B15B.BackfillRefused):
    """The calibrator will not do what it was asked, and says so rather than improvising."""


# --------------------------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------------------------

def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise CalibrationRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise CalibrationRefused(
            f"the calibration preregistration hashes {actual}, pinned {expected}. The sampling "
            "rule and the stopping rule were frozen before any fetch, and a changed document is a "
            "different sample")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = path.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise CalibrationRefused(
            f"an execution surface appeared in {path.name}: {found}. This worker reads and counts")
    return True


def assert_isolated(work_dir=WORK_DIR):
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in ("research/b15a", "research/b15b", "research/b11a"):
        if marker.replace("/", os.sep) in resolved:
            raise CalibrationRefused(
                f"{resolved} would write into {marker!r}; those are read-only evidence here")
    if not resolved.endswith(os.sep + "b15c"):
        raise CalibrationRefused(f"the work directory must be .../b15c, got {resolved}")
    return True


def assert_no_float(node, path="$"):
    """No float anywhere. Every cost is an integer number of lamports."""
    if isinstance(node, float):
        raise CalibrationRefused(
            f"{path} is a float ({node!r}); a lamport is an integer and a fee expressed as a float "
            "is a fee nobody can reconcile")
    if isinstance(node, dict):
        for key, value in node.items():
            assert_no_float(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            assert_no_float(value, f"{path}[{index}]")
    return True


# --------------------------------------------------------------------------------------------
# Sampling — deterministic, time-neutral, reproducible from the signature alone
# --------------------------------------------------------------------------------------------

def is_sampled(signature, modulus, seed="b15c:"):
    """The frozen selector. Reproducible by anyone holding the signature and this constant."""
    digest = hashlib.sha256(f"{seed}{signature}".encode()).hexdigest()
    return int(digest, 16) % modulus == 0


def population(raw_path=B15A_RAW, decoder=None, limit_frames=None):
    """Successful Pump transactions carrying at least one BUY TradeEvent, in canonical order.

    Read from the append-only raw log while B15a keeps writing to it. Reading a file another
    process appends to is safe: lines already written never change, and a partial final line is
    skipped rather than guessed at.
    """
    decoder = decoder or B15B.build_decoder()
    trade_discriminator = None
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    for event in idl.get("events", []):
        if event["name"] == "TradeEvent":
            trade_discriminator = bytes(event["discriminator"]).hex()
    seen = set()
    out = []
    with pathlib.Path(raw_path).open() as handle:
        for index, line in enumerate(handle):
            if limit_frames is not None and index >= limit_frames:
                break
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # A partial final line, because B15a is appending right now. Skipped, not guessed.
                continue
            params = (record.get("raw_notification_json", {}).get("params") or {}).get("result") \
                or {}
            value = params.get("value") or {}
            if value.get("err") is not None:
                continue
            signature = value.get("signature")
            if not signature or signature in seen:
                continue
            payloads, _skipped = PILOT.program_data_payloads(value.get("logs"))
            for payload in payloads:
                body = payload[len(PILOT.EVENT_TAG):] \
                    if payload.startswith(PILOT.EVENT_TAG) else payload
                if len(body) < 8 or body[:8].hex() != trade_discriminator:
                    continue
                try:
                    fields = decoder["b7d"].read_struct(
                        decoder["b7d"].Cursor(body[8:]), decoder["types"]["TradeEvent"],
                        decoder["types"])
                except Exception:                                         # noqa: BLE001
                    continue
                if fields.get("is_buy"):
                    seen.add(signature)
                    out.append({"signature": signature,
                                "slot": (params.get("context") or {}).get("slot")})
                    break
    return out


# --------------------------------------------------------------------------------------------
# Cost decomposition — exact integers, and absence is never zero
# --------------------------------------------------------------------------------------------

def compute_budget_settings(result):
    """The requested unit limit and unit price, from the ComputeBudget instructions.

    Returns `(limit, price, present, reason)`. `present` distinguishes the two cases that look the
    same in a number: no compute-budget instruction at all, which PROVES no prioritization fee
    because the fee is defined by those instructions; and an instruction we could not parse, which
    proves nothing.
    """
    transaction = result.get("transaction") or {}
    message = transaction.get("message") or {}
    instructions = message.get("instructions") or []
    limit = price = None
    present = False
    for instruction in instructions:
        if instruction.get("programId") != COMPUTE_BUDGET_PROGRAM:
            continue
        present = True
        raw = instruction.get("data")
        if not raw:
            return None, None, True, C03_COMPUTE_BUDGET_UNDECODABLE
        try:
            data = _b58decode(raw)
        except Exception:                                                 # noqa: BLE001
            return None, None, True, C03_COMPUTE_BUDGET_UNDECODABLE
        if not data:
            return None, None, True, C03_COMPUTE_BUDGET_UNDECODABLE
        kind = data[0]
        if kind == CB_SET_UNIT_LIMIT and len(data) >= 5:
            limit = int.from_bytes(data[1:5], "little")
        elif kind == CB_SET_UNIT_PRICE and len(data) >= 9:
            price = int.from_bytes(data[1:9], "little")
    return limit, price, present, None


def _b58decode(value):
    b7d = _load("b7d_create_enumerator", "b7d_create_enumerator.py")
    return b7d.b58decode(value)


def prioritization_fee(limit, price, present):
    """`ceil(price * limit / 1e6)`, exactly, or an explicit unavailability.

    Returns `(fee_or_None, provable, reason)`. With no compute-budget instruction present the fee
    is zero AND provably so. With one present but a component missing, it is unavailable.
    """
    if not present:
        return 0, True, "no_compute_budget_instruction"
    if limit is None or price is None:
        return None, False, C03_COMPUTE_BUDGET_UNDECODABLE
    # Integer ceiling; no float division anywhere near a lamport.
    return -((-price * limit) // MICRO_LAMPORTS_PER_LAMPORT), True, None


def tip_lamports(result, tip_accounts):
    """Tips, only under an explicit declared tip-account set.

    With an empty set the answer is UNAVAILABLE, not zero. Guessing which addresses are tip
    accounts would turn an unknown into a number, and the number would be wrong in whichever
    direction nobody checked.
    """
    if not tip_accounts:
        return None, False, "tip_account_set_not_declared"
    transaction = result.get("transaction") or {}
    message = transaction.get("message") or {}
    total = 0
    for instruction in (message.get("instructions") or []):
        if instruction.get("programId") != SYSTEM_PROGRAM:
            continue
        parsed = instruction.get("parsed") or {}
        if parsed.get("type") != "transfer":
            continue
        info = parsed.get("info") or {}
        if info.get("destination") in tip_accounts:
            total += int(info.get("lamports", 0))
    return total, True, None


def pump_fees(result, decoder):
    """The protocol's own fee fields, from the TradeEvent, as exact integers."""
    meta = result.get("meta") or {}
    payloads, _skipped = PILOT.program_data_payloads(meta.get("logMessages") or [])
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    trade = next(bytes(e["discriminator"]).hex() for e in idl["events"]
                 if e["name"] == "TradeEvent")
    for payload in payloads:
        body = payload[len(PILOT.EVENT_TAG):] if payload.startswith(PILOT.EVENT_TAG) else payload
        if len(body) < 8 or body[:8].hex() != trade:
            continue
        fields = decoder["b7d"].read_struct(
            decoder["b7d"].Cursor(body[8:]), decoder["types"]["TradeEvent"], decoder["types"])
        if not fields.get("is_buy"):
            continue
        return {
            "pump_protocol_fee_lamports": fields.get("fee"),
            "pump_fee_basis_points": fields.get("fee_basis_points"),
            "pump_creator_fee_lamports": fields.get("creator_fee"),
            "pump_creator_fee_basis_points": fields.get("creator_fee_basis_points"),
            "pump_cashback_lamports": fields.get("cashback"),
            "pump_buyback_fee_lamports": fields.get("buyback_fee"),
            "quote_amount": fields.get("quote_amount"),
            "sol_amount": fields.get("sol_amount"),
        }
    return None


def decompose(response, signature, slot, decoder, tip_accounts=()):
    """Every cost component this transaction publishes, and a named reason for each it does not."""
    result = response.get("result") or {}
    meta = result.get("meta") or {}
    transaction = result.get("transaction") or {}
    signatures = transaction.get("signatures") or []
    if signatures and signatures[0] != signature:
        raise CalibrationRefused(f"{C07_RESPONSE_INCONSISTENT}: signature disagrees")
    if slot is not None and result.get("slot") is not None and result["slot"] != slot:
        raise CalibrationRefused(f"{C07_RESPONSE_INCONSISTENT}: slot disagrees")
    if meta.get("err") is not None:
        raise CalibrationRefused(f"{C01_TRANSACTION_FAILED}: a failed transaction paid a fee for "
                                 "nothing and is not a cost observation for a buy")
    fees = pump_fees(result, decoder)
    if fees is None:
        raise CalibrationRefused(f"{C02_NO_BUY_TRADE_EVENT}: no buy TradeEvent in this transaction")

    limit, price, present, reason = compute_budget_settings(result)
    priority, priority_provable, priority_reason = prioritization_fee(limit, price, present)
    if reason == C03_COMPUTE_BUDGET_UNDECODABLE:
        priority, priority_provable, priority_reason = None, False, reason
    tip, tip_provable, tip_reason = tip_lamports(result, tip_accounts)

    signature_count = len(signatures)
    base = LAMPORTS_PER_SIGNATURE * signature_count if signature_count else None
    total = meta.get("fee")
    record = {
        "signature": signature,
        "slot": result.get("slot"),
        "total_fee_lamports": total,
        "signature_count": signature_count or None,
        "base_fee_lamports": base,
        "compute_units_consumed": meta.get("computeUnitsConsumed"),
        "compute_unit_limit": limit,
        "compute_unit_price_micro_lamports": price,
        "prioritization_fee_lamports": priority,
        "prioritization_provable": priority_provable,
        "prioritization_reason": priority_reason,
        "tip_lamports": tip,
        "tip_provable": tip_provable,
        "tip_reason": tip_reason,
    }
    record.update(fees)
    # The empirical answer to what meta.fee contains. Checked, not assumed, and a disagreement
    # excludes the row rather than being adjusted away.
    record["decomposition_checked"] = bool(
        base is not None and priority is not None and total is not None)
    record["decomposition_agrees"] = (
        record["decomposition_checked"] and base + priority == total)
    assert_no_float(record)
    return record


# --------------------------------------------------------------------------------------------
# Exact order statistics
# --------------------------------------------------------------------------------------------

def order_statistic(values, numerator, denominator):
    """The value at a quantile INDEX. Never interpolated between neighbours."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) * numerator // denominator]


def scenarios_from(values):
    """p10, p50, p90 of the observed distribution. Exact, integer, and labelled for what they are."""
    if not values:
        return {"observations": 0, "note": "no observation; a scenario over nothing is not a "
                                           "scenario", "label": SCENARIO_LABEL}
    return {
        "observations": len(values),
        "optimistic_p10_lamports": order_statistic(values, 1, 10),
        "base_p50_lamports": order_statistic(values, 1, 2),
        "stressed_p90_lamports": order_statistic(values, 9, 10),
        "minimum_lamports": min(values),
        "maximum_lamports": max(values),
        "label": SCENARIO_LABEL,
        "executable": False,
        "meaning": "the observed cost of OTHER traders' transactions. Calibration evidence, not a "
                   "quote, not a landing probability, and not a price we are promised.",
    }


# --------------------------------------------------------------------------------------------
# Storage and the run
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS observation (
  signature TEXT PRIMARY KEY, slot INTEGER, total_fee_lamports INTEGER, signature_count INTEGER,
  base_fee_lamports INTEGER, compute_units_consumed INTEGER, compute_unit_limit INTEGER,
  compute_unit_price_micro_lamports INTEGER, prioritization_fee_lamports INTEGER,
  prioritization_provable INTEGER NOT NULL, prioritization_reason TEXT,
  tip_lamports INTEGER, tip_provable INTEGER NOT NULL, tip_reason TEXT,
  pump_protocol_fee_lamports INTEGER, pump_fee_basis_points INTEGER,
  pump_creator_fee_lamports INTEGER, pump_creator_fee_basis_points INTEGER,
  pump_cashback_lamports INTEGER, pump_buyback_fee_lamports INTEGER,
  quote_amount INTEGER, sol_amount INTEGER,
  decomposition_checked INTEGER NOT NULL, decomposition_agrees INTEGER NOT NULL,
  latency_ns INTEGER, evidence_sha256 TEXT NOT NULL, observed_at_wall_unix REAL NOT NULL);
CREATE TABLE IF NOT EXISTS exclusion (
  signature TEXT PRIMARY KEY, code TEXT NOT NULL, detail TEXT, excluded_at_wall_unix REAL NOT NULL);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


def run(limit=None, raw_path=B15A_RAW, work_dir=WORK_DIR, opener=None, sleeper=time.sleep,
        url=None, tip_accounts=()):
    """Sample, fetch, decompose. The scenario is computed only after the sample completes."""
    assert_no_execution_surface()
    assert_isolated(work_dir)
    document = verify_preregistration()
    sampling = document["sampling_rule"]
    stopping = document["stopping_rule"]
    rate = document["rate_policy"]
    url = url or B15B.rpc_url()
    receipt = B15B.endpoint_receipt(url)
    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)
    connection = open_database(pathlib.Path(work_dir) / "calibration.sqlite")
    exchanges = B15B.ExchangeLog(pathlib.Path(work_dir) / "rpc_exchanges.jsonl")
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("preregistration_id", document["preregistration_id"]),
                       ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                       ("endpoint_scheme_host", receipt),
                       ("scenario_label", SCENARIO_LABEL),
                       ("execution_status", "never_executed"),
                       ("tip_accounts_declared", str(len(tip_accounts)))):
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, str(value)))
    connection.commit()

    decoder = B15B.build_decoder()
    target = min(stopping["sample_target"], limit or stopping["sample_target"])
    already = {row[0] for row in connection.execute("SELECT signature FROM observation")} | \
              {row[0] for row in connection.execute("SELECT signature FROM exclusion")}
    candidates = [row for row in population(raw_path, decoder)
                  if is_sampled(row["signature"], sampling["sampling_modulus"],
                                sampling["seed_string"])]
    counts = {"in_population": None, "sampled": len(candidates), "fetched": 0, "included": 0,
              "excluded": 0, "duplicates_skipped": 0}
    exclusions = {}
    latencies = []
    interval = rate["min_interval_ms"] / 1000.0
    last = None
    policy = {"transport": {"commitment": "confirmed"},
              "rate_and_stopping_policy": {
                  "max_attempts_per_signature": rate["max_attempts_per_signature"],
                  "backoff_seconds": rate["backoff_seconds"],
                  "retryable_markers": B15B.verify_preregistration()[
                      "rate_and_stopping_policy"]["retryable_markers"]}}
    try:
        for row in candidates:
            if counts["included"] >= target:
                break
            signature = row["signature"]
            if signature in already:
                counts["duplicates_skipped"] += 1
                continue
            already.add(signature)
            if last is not None:
                elapsed = time.monotonic() - last
                if elapsed < interval:
                    sleeper(interval - elapsed)
            last = time.monotonic()
            counts["fetched"] += 1
            outcome, payload, latency_ns = B15B.fetch_transaction(
                signature, url, policy, exchanges, opener=opener, sleeper=sleeper)
            latencies.append(latency_ns)
            if outcome != "retrieved":
                _exclude(connection, signature, C04_RPC_EXHAUSTED, str(outcome), counts,
                         exclusions)
                continue
            try:
                record = decompose(payload, signature, row["slot"], decoder, tip_accounts)
            except CalibrationRefused as error:
                _exclude(connection, signature, str(error).split(":", 1)[0], str(error)[:200],
                         counts, exclusions)
                continue
            if record["decomposition_checked"] and not record["decomposition_agrees"]:
                # Excluded, not adjusted. A row bent to fit the identity is a row that no longer
                # tests it.
                _exclude(connection, signature, C05_DECOMPOSITION_MISMATCH,
                         f"base+priority != fee", counts, exclusions)
                continue
            record["latency_ns"] = latency_ns
            record["evidence_sha256"] = hashlib.sha256(
                json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()
            record["observed_at_wall_unix"] = time.time()
            _insert(connection, record)
            counts["included"] += 1
            connection.commit()
    finally:
        exchanges.close()
        totals = [r[0] for r in connection.execute(
            "SELECT total_fee_lamports FROM observation WHERE total_fee_lamports IS NOT NULL")]
        connection.close()
    counts["exclusions"] = dict(sorted(exclusions.items()))
    counts["latency_ns"] = B15B._summary(sorted(latencies))
    counts["scenarios"] = scenarios_from(totals)
    counts["endpoint_scheme_host"] = receipt
    assert_no_float({k: v for k, v in counts.items() if k != "scenarios"})
    return counts


def _exclude(connection, signature, code, detail, counts, exclusions):
    connection.execute(
        "INSERT OR REPLACE INTO exclusion(signature,code,detail,excluded_at_wall_unix) "
        "VALUES (?,?,?,?)", (signature, code, detail, time.time()))
    connection.commit()
    counts["excluded"] += 1
    exclusions[code] = exclusions.get(code, 0) + 1


def _insert(connection, record):
    columns = ("signature", "slot", "total_fee_lamports", "signature_count", "base_fee_lamports",
               "compute_units_consumed", "compute_unit_limit",
               "compute_unit_price_micro_lamports", "prioritization_fee_lamports",
               "prioritization_provable", "prioritization_reason", "tip_lamports", "tip_provable",
               "tip_reason", "pump_protocol_fee_lamports", "pump_fee_basis_points",
               "pump_creator_fee_lamports", "pump_creator_fee_basis_points",
               "pump_cashback_lamports", "pump_buyback_fee_lamports", "quote_amount",
               "sol_amount", "decomposition_checked", "decomposition_agrees", "latency_ns",
               "evidence_sha256", "observed_at_wall_unix")
    values = []
    for name in columns:
        value = record.get(name)
        values.append(int(value) if isinstance(value, bool) else value)
    connection.execute(
        f"INSERT OR REPLACE INTO observation({','.join(columns)}) "
        f"VALUES ({','.join('?' * len(columns))})", values)


def status(db_path=DB_PATH):
    if not pathlib.Path(db_path).exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started"}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        meta = dict(connection.execute("SELECT key, value FROM metadata"))
        included = connection.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
        exclusions = dict(connection.execute("SELECT code, COUNT(*) FROM exclusion GROUP BY 1"))
        totals = [r[0] for r in connection.execute(
            "SELECT total_fee_lamports FROM observation WHERE total_fee_lamports IS NOT NULL")]
        checked, agreed = connection.execute(
            "SELECT SUM(decomposition_checked), SUM(decomposition_agrees) FROM observation"
        ).fetchone()
        priority_unavailable = connection.execute(
            "SELECT COUNT(*) FROM observation WHERE prioritization_provable=0").fetchone()[0]
        tips_unavailable = connection.execute(
            "SELECT COUNT(*) FROM observation WHERE tip_provable=0").fetchone()[0]
        latencies = [r[0] for r in connection.execute(
            "SELECT latency_ns FROM observation WHERE latency_ns IS NOT NULL")]
    finally:
        connection.close()
    report = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": meta.get("preregistration_id"),
        "endpoint_scheme_host": meta.get("endpoint_scheme_host"),
        "execution_status": meta.get("execution_status"),
        "scenario_label": meta.get("scenario_label"),
        "observations_included": included,
        "exclusions_by_code": exclusions,
        "decomposition_checked": checked or 0,
        "decomposition_agreed": agreed or 0,
        "prioritization_unavailable": priority_unavailable,
        "tips_unavailable": tips_unavailable,
        "tip_accounts_declared": int(meta.get("tip_accounts_declared", 0)),
        "latency_ns": B15B._summary(sorted(latencies)),
        "scenarios": scenarios_from(totals),
        "reads_only": True,
    }
    PILOT.assert_redacted(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--run", action="store_true")
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
            "sampling_modulus": document["sampling_rule"]["sampling_modulus"],
            "sample_target": document["stopping_rule"]["sample_target"],
            "scenario_label": SCENARIO_LABEL,
            "reads_only": True,
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
