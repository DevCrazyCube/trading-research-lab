"""B15d — prices delayed hypothetical entries on the frozen direct-RPC shadow route.

Implements `research/B15D_SHADOW_ROUTE_PREREGISTRATION.json`, committed alone before any entry was
priced and before any shadow outcome was read.

For each eligible B15b launch and each frozen (cost scenario x delay) cell, it finds the FIRST
canonical observation of that curve at or after `t0 + delay_slots`, reconstructs the state exactly
from evidence, and prices the unchanged 0.1 SOL P1 order through B10a.

Three things this does not do, each of which would be easy and wrong:

- **It never uses a later or current snapshot as the delayed entry state.** If the state cannot be
  reconstructed exactly, the candidate is `unavailable`. An approximation here is a state that
  never existed being priced as if it had.
- **It never estimates a landing probability.** A cost scenario says what a transaction would have
  cost if it landed. Whether it would have is not modelled, claimed or implied.
- **It never drops a candidate it could not price.** Stale and unavailable rows are recorded, so
  the census is the whole population rather than the subset that happened to work — and the curves
  with no later observation are disproportionately the ones that died immediately.
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

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15d"
DB_PATH = WORK_DIR / "shadow_entries.sqlite"
B15A_RAW = ROOT / "research" / "b15a" / "raw_frames.jsonl"
B15B_DB = ROOT / "research" / "b15b" / "backfill.sqlite"

PREREG_PATH = ROOT / "research" / "B15D_SHADOW_ROUTE_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "63ff57d11842f1689081ac22e3b4b4b3f621da9e8558b694399ced92ac4e67bf"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

STATUS_PRICED = "priced"
STATUS_REFUSED = "refused"
STATUS_STALE = "stale"
STATUS_UNAVAILABLE = "unavailable"
STATUSES = (STATUS_PRICED, STATUS_REFUSED, STATUS_STALE, STATUS_UNAVAILABLE)

LABEL = "SIMULATED_SHADOW"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15C = _load("b15c_cost_calibration", "b15c_cost_calibration.py")
B15B = B15C.B15B
PILOT = B15C.PILOT
B10A = _load("b10a_simulator_kernel", "b10a_simulator_kernel.py")


class ShadowEntryRefused(B15C.CalibrationRefused):
    """The materializer will not price this, and says why rather than approximating."""


# --------------------------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------------------------

def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ShadowEntryRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise ShadowEntryRefused(
            f"the route preregistration hashes {actual}, pinned {expected}. The route, the cost "
            "scenarios and the delays were frozen before any entry was priced, and a changed "
            "document is a different route")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = path.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise ShadowEntryRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_isolated(work_dir=WORK_DIR):
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in ("research/b15a", "research/b15b", "research/b15c", "research/b11a"):
        if marker.replace("/", os.sep) in resolved:
            raise ShadowEntryRefused(
                f"{resolved} would write into {marker!r}; those are read-only evidence here")
    if not resolved.endswith(os.sep + "b15d"):
        raise ShadowEntryRefused(f"the work directory must be .../b15d, got {resolved}")
    return True


def assert_no_float(node, path="$"):
    """Re-raised as THIS module's refusal, not delegated bare.

    B15c's version raises CalibrationRefused, which is this module's PARENT class — so a caller
    written `except ShadowEntryRefused` would not catch it. Sharing an implementation is fine;
    letting a parent-class exception escape a child module's function is how a handler that looks
    correct silently stops applying.
    """
    try:
        return B15C.assert_no_float(node, path)
    except B15C.CalibrationRefused as error:
        raise ShadowEntryRefused(str(error)) from error


# --------------------------------------------------------------------------------------------
# The frozen policy, assembled without collapsing anything
# --------------------------------------------------------------------------------------------

def cost_policy(scenario):
    """The B10a cost policy for one frozen scenario.

    Base and priority stay SEPARATE because B10a sums them itself and also charges the pair again
    per failed attempt. Handing it a combined total would charge the base fee twice on the first
    attempt and once more on every retry.
    """
    for field in ("base_fee_lamports", "priority_fee_lamports", "tip_lamports",
                  "ata_rent_lamports", "failed_attempts"):
        if field not in scenario:
            raise ShadowEntryRefused(
                f"scenario {scenario.get('scenario_id')!r} does not state {field}; absence is not "
                "zero and an unstated cost may not be priced")
        if isinstance(scenario[field], bool) or not isinstance(scenario[field], int):
            raise ShadowEntryRefused(f"{field} must be an exact integer, got {scenario[field]!r}")
    return {field: scenario[field] for field in
            ("base_fee_lamports", "priority_fee_lamports", "tip_lamports", "ata_rent_lamports",
             "failed_attempts")}


def assert_no_double_count(scenario, cost_context):
    """The scenario's priority fee must come from the PRIORITIZATION distribution, not the total.

    Checked rather than trusted, because the two live side by side in the same context artifact and
    reading the wrong one produces a number that looks entirely plausible.
    """
    totals = {value for key, value in cost_context["total_fee_lamports"].items()
              if key.endswith("_lamports") and isinstance(value, int)}
    priorities = {value for key, value in cost_context["prioritization_fee_lamports"].items()
                  if key.endswith("_lamports") and isinstance(value, int)}
    priority = scenario["priority_fee_lamports"]
    if priority in totals and priority not in priorities:
        raise ShadowEntryRefused(
            f"scenario {scenario['scenario_id']!r} takes its priority fee {priority} from the "
            "TOTAL-fee distribution, which already contains the base fee. B10a adds the base fee "
            "itself, so this would charge it twice")
    return True


# --------------------------------------------------------------------------------------------
# Observations — canonical order, from recorded evidence only
# --------------------------------------------------------------------------------------------

def observations_by_mint(raw_path, mints, decoder, trade_discriminator, min_slot_by_mint=None):
    """Every recorded TradeEvent on the curves of interest, in canonical order, in ONE pass.

    Written as one pass on purpose. The obvious shape — a helper that scans the log for a single
    mint, called once per launch — is O(launches x log size), and against a 1.1 GB log and five
    hundred launches it does not finish. Reading the evidence once and bucketing by mint is the
    same answer at a fraction of the work.

    Only mints of interest are retained, and only observations at or after each curve's own
    earliest useful slot, so memory is bounded by the launches being priced rather than by the log.
    """
    mints = set(mints)
    min_slot_by_mint = min_slot_by_mint or {}
    buckets = {mint: {} for mint in mints}
    with pathlib.Path(raw_path).open() as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            params = (record.get("raw_notification_json", {}).get("params") or {}).get("result") \
                or {}
            value = params.get("value") or {}
            if value.get("err") is not None:
                continue
            slot = (params.get("context") or {}).get("slot")
            signature = value.get("signature")
            payloads, _skipped = PILOT.program_data_payloads(value.get("logs"))
            for index, payload in enumerate(payloads):
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
                mint = fields.get("mint")
                if mint not in mints:
                    continue
                floor = min_slot_by_mint.get(mint)
                if floor is not None and slot is not None and slot < floor:
                    continue
                buckets[mint][(slot, signature, index)] = {
                    "slot": slot, "signature": signature, "log_index": index, "fields": fields}
    return {mint: [rows[key] for key in sorted(rows, key=lambda k: (k[0], k[1], k[2]))]
            for mint, rows in buckets.items()}


def curve_observations(raw_path, mint, decoder, trade_discriminator):
    """Every recorded TradeEvent on one curve, in canonical order.

    Canonical means `(slot, transaction_index, outer_index, inner_index)`. The feed gives slot and
    log order; log order within a transaction IS execution order, and frames arrive in slot order.
    Sorting explicitly rather than trusting arrival order is what makes a reconnect or a duplicated
    frame harmless.
    """
    out = {}
    with pathlib.Path(raw_path).open() as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            params = (record.get("raw_notification_json", {}).get("params") or {}).get("result") \
                or {}
            value = params.get("value") or {}
            if value.get("err") is not None:
                continue
            slot = (params.get("context") or {}).get("slot")
            signature = value.get("signature")
            payloads, _skipped = PILOT.program_data_payloads(value.get("logs"))
            for index, payload in enumerate(payloads):
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
                if fields.get("mint") != mint:
                    continue
                # Keyed by identity so a duplicated frame after a reconnect collapses rather than
                # appearing as a second observation at the same coordinate.
                out[(slot, signature, index)] = {
                    "slot": slot, "signature": signature, "log_index": index, "fields": fields}
    return [out[key] for key in sorted(out, key=lambda k: (k[0], k[1], k[2]))]


def state_at_or_after(observations, t0_slot, delay_slots):
    """The FIRST observation at or after `t0 + delay`, and the state it publishes.

    Returns `(state, observation)` or `(None, None)`. The caller records `stale` on None; it does
    not fall back to the newest observation, which is the mistake this function exists to prevent.
    """
    threshold = t0_slot + delay_slots
    for observation in observations:
        if observation["slot"] is None or observation["slot"] < threshold:
            continue
        fields = observation["fields"]
        state = {
            "virtual_quote": fields.get("virtual_quote_reserves",
                                        fields.get("virtual_sol_reserves")),
            "virtual_token": fields.get("virtual_token_reserves"),
            "real_quote": fields.get("real_quote_reserves", fields.get("real_sol_reserves")),
            "real_token": fields.get("real_token_reserves"),
            "quote_mint": fields.get("quote_mint"),
            "mayhem_mode": bool(fields.get("mayhem_mode")),
            "complete": False,
            "slot": observation["slot"],
        }
        if any(state[key] is None for key in
               ("virtual_quote", "virtual_token", "real_quote", "real_token", "quote_mint")):
            return None, observation                # present but incomplete: unavailable, not stale
        return state, observation
    return None, None


def evidence_hash(record):
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# --------------------------------------------------------------------------------------------
# Fee schedule — read per launch from that launch's own evidence
# --------------------------------------------------------------------------------------------

def fee_schedule_from(observation):
    """B10a's fee schedule, from the point-in-time TradeEvent of THIS curve.

    Never from another launch and never from a current config snapshot: the basis points are a
    property of the program version in force at that instant, and B15c saw them take more than one
    value across a single sample.
    """
    fields = observation["fields"]
    schedule = {
        "fee_bps": fields.get("fee_basis_points"),
        "creator_fee_bps": fields.get("creator_fee_basis_points"),
        "cashback_fee_bps": fields.get("cashback_fee_basis_points"),
        "buyback_fee_bps": fields.get("buyback_fee_basis_points"),
    }
    missing = [name for name, value in schedule.items() if value is None]
    if missing:
        raise ShadowEntryRefused(
            f"the observation does not publish {missing}; a fee schedule with an unstated "
            "component may not be priced and is not assumed to be zero")
    return schedule


# --------------------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate (
  signature TEXT NOT NULL, scenario_id TEXT NOT NULL, delay_slots INTEGER NOT NULL,
  mint TEXT, t0_slot INTEGER, observation_slot INTEGER, observation_signature TEXT,
  status TEXT NOT NULL, reason TEXT,
  quote_lamports INTEGER, tokens_out INTEGER, execution_cost_lamports INTEGER,
  total_outlay_lamports INTEGER,
  base_fee_lamports INTEGER, priority_fee_lamports INTEGER, tip_lamports INTEGER,
  ata_rent_lamports INTEGER, failed_attempts INTEGER,
  fee_bps INTEGER, creator_fee_bps INTEGER, cashback_fee_bps INTEGER, buyback_fee_bps INTEGER,
  evidence_sha256 TEXT NOT NULL, priced_at_wall_unix REAL NOT NULL,
  PRIMARY KEY (signature, scenario_id, delay_slots));
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


D_FEED_DEGRADED_AT_T0 = "D_feed_degraded_at_t0"


def feed_degraded_signatures(b15a_path=None):
    """Launches whose FEED-TIME decision was S07_session_degraded.

    Backfill repairs a transaction's CONTENTS. It cannot retroactively prove that the feed was
    continuous at t0, and it cannot erase the fact that it was not. Both facts are kept: the
    backfilled state is real, and the observation it belongs to was taken through a degraded
    session. The safety rule is that degraded defaults to no trade, and no frozen contract permits
    recovery from S07 — B15b's and B15d's preregistrations do not mention it at all.

    An empty set is returned when B15a is unreadable, and the CALLER treats that as unknown rather
    than as clean; see `assert_degraded_source_available`.
    """
    path = (ROOT / "research" / "b15a" / "shadow.sqlite") if b15a_path is None \
        else pathlib.Path(b15a_path)
    if not path.exists():
        return None
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        return {row[0] for row in connection.execute(
            "SELECT l.signature FROM launch l JOIN decision d ON d.launch_seq = l.launch_seq "
            "WHERE d.reason_code LIKE ?", (f"{PILOT.S07_SESSION_DEGRADED}%",))}
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def assert_degraded_source_available(degraded):
    """Unknown degradation is not clean degradation.

    If B15a cannot be read, we do not know which launches were observed through a degraded
    session. Pricing them all as clean would be exactly the substitution this gate exists to
    prevent, so the run refuses instead.
    """
    if degraded is None:
        raise ShadowEntryRefused(
            "the feed-degradation record could not be read from B15a. Unknown is not clean: "
            "without it every entry would be priced as though its feed had been continuous")
    return degraded


def eligible_launches(b15b_path=B15B_DB, limit=None):
    """B15b launches whose t0 state is complete. Read-only; B15b keeps running."""
    connection = sqlite3.connect(f"file:{b15b_path}?mode=ro", uri=True, timeout=30)
    try:
        # The token mint lives on `backfill`, not on `t0_state` — t0_state's `quote_mint` is the
        # SOL sentinel, a different field entirely. Joining rather than assuming which table holds
        # it is what turned a plausible-looking query into one that runs.
        rows = connection.execute(
            "SELECT t.signature, t.slot, b.mint FROM t0_state t "
            "JOIN backfill b ON b.signature = t.signature "
            "WHERE t.missing_fields='[]' AND b.mint IS NOT NULL "
            "ORDER BY t.slot, t.signature").fetchall()
    finally:
        connection.close()
    return rows[:limit] if limit else rows


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------

def run(limit=None, raw_path=B15A_RAW, b15b_path=B15B_DB, work_dir=WORK_DIR,
        cost_context_path=ROOT / "research" / "B15C_COST_CONTEXT.json", b15a_path=None):
    """Price every eligible launch under every frozen cell. Preserves every candidate."""
    assert_no_execution_surface()
    assert_isolated(work_dir)
    document = verify_preregistration()
    cost_context = json.loads(pathlib.Path(cost_context_path).read_text())
    scenarios = document["cost_scenarios"]
    delays = document["delay_scenarios"]["values"]
    order_spec = document["materialization_rules"]["order"]
    for scenario in scenarios:
        assert_no_double_count(scenario, cost_context)

    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)
    connection = open_database(pathlib.Path(work_dir) / "shadow_entries.sqlite")
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("preregistration_id", document["preregistration_id"]),
                       ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                       ("route_id", document["route"]["route_id"]),
                       ("label", LABEL), ("executable", "0"),
                       ("execution_status", "never_executed"),
                       ("performance_status", "not_evaluated"),
                       ("tip_is_route_choice", "1")):
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, str(value)))
    connection.commit()

    decoder = B15B.build_decoder()
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    trade = next(bytes(e["discriminator"]).hex() for e in idl["events"]
                 if e["name"] == "TradeEvent")
    launches = eligible_launches(b15b_path, limit)
    # Read BEFORE anything is priced. A launch observed through a degraded session may not become
    # a priced entry, and an unreadable record is refused rather than treated as clean.
    degraded = assert_degraded_source_available(feed_degraded_signatures(b15a_path))
    # ONE pass over the raw log covering every launch at once. Scanning per launch was
    # O(launches x log size) and did not finish against a 1.1 GB log with five hundred launches.
    smallest_delay = min(delays)
    floors = {}
    for _signature, t0_slot, mint in launches:
        floor = t0_slot + smallest_delay
        floors[mint] = min(floors.get(mint, floor), floor)
    index = observations_by_mint(raw_path, {row[2] for row in launches}, decoder, trade, floors)
    counts = {"launches": len(launches), "cells": 0}
    by_status = {}
    by_cell = {}
    for signature, t0_slot, mint in launches:
        observations = index.get(mint, [])
        for scenario in scenarios:
            policy = cost_policy(scenario)
            for delay in delays:
                counts["cells"] += 1
                cell = f"{scenario['scenario_id']}@{delay}"
                state, observation = state_at_or_after(observations, t0_slot, delay)
                if signature in degraded:
                    # Fail closed. Both facts are preserved: the backfilled state exists and is
                    # recorded upstream, and this observation was taken through a degraded feed.
                    status, reason, priced = (STATUS_REFUSED, D_FEED_DEGRADED_AT_T0,
                                              {"tokens_out": None,
                                               "execution_cost_lamports": None,
                                               "total_outlay_lamports": None, "fee_bps": None,
                                               "creator_fee_bps": None,
                                               "cashback_fee_bps": None,
                                               "buyback_fee_bps": None})
                else:
                    status, reason, priced = _price(state, observation, policy, order_spec)
                by_status[status] = by_status.get(status, 0) + 1
                by_cell.setdefault(cell, {})
                by_cell[cell][status] = by_cell[cell].get(status, 0) + 1
                record = {"signature": signature, "scenario_id": scenario["scenario_id"],
                          "delay_slots": delay, "mint": mint, "t0_slot": t0_slot,
                          "observation_slot": observation["slot"] if observation else None,
                          "observation_signature": observation["signature"] if observation
                          else None,
                          "status": status, "reason": reason,
                          "quote_lamports": order_spec["quote_lamports"]}
                record.update(policy)
                record.update(priced)
                record["evidence_sha256"] = evidence_hash(record)
                record["priced_at_wall_unix"] = time.time()
                _insert(connection, record)
        connection.commit()
    connection.close()
    counts["feed_degraded_launches"] = len(degraded)
    counts["by_status"] = dict(sorted(by_status.items()))
    counts["by_cell"] = {k: dict(sorted(v.items())) for k, v in sorted(by_cell.items())}
    counts["label"] = LABEL
    counts["no_landing_probability_claimed"] = True
    counts["no_profit_or_exit_published"] = True
    return counts


def _price(state, observation, policy, order_spec):
    """One cell. Returns `(status, reason, priced_fields)` and never approximates a state."""
    empty = {"tokens_out": None, "execution_cost_lamports": None, "total_outlay_lamports": None,
             "fee_bps": None, "creator_fee_bps": None, "cashback_fee_bps": None,
             "buyback_fee_bps": None}
    if observation is None:
        # No observation of this curve at or after the delay exists in the recorded evidence. NOT
        # an excuse to price against the newest one we happen to hold.
        return STATUS_STALE, "no_observation_at_or_after_delay", empty
    if state is None:
        return STATUS_UNAVAILABLE, "delayed_state_incomplete", empty
    try:
        schedule = fee_schedule_from(observation)
    except ShadowEntryRefused as error:
        return STATUS_UNAVAILABLE, str(error)[:160], empty
    order = {"side": "buy", "quote_lamports": order_spec["quote_lamports"]}
    try:
        result = B10A.price_entry(state, order, schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        return STATUS_REFUSED, f"{type(error).__name__}: {error}"[:200], dict(empty, **schedule)
    priced = dict(empty)
    priced.update(schedule)
    priced["tokens_out"] = result.get("tokens_out")
    # Read the figures B10a COMPUTED, and refuse if they are absent.
    #
    # The first version summed `result.get("costs") or {}`. B10a's key is `execution_costs`, so the
    # get returned an empty dict, the sum returned 0, and every one of 5,352 priced cells recorded
    # an execution cost of zero — three scenarios costing 2.0, 2.1 and 4.0 million lamports all
    # reported as free, with nothing raised. Summing an absent structure to zero is precisely the
    # zero-by-absence this project refuses everywhere else, and it slipped in through `or {}`.
    costs = result.get("execution_costs")
    if not isinstance(costs, dict) or "total" not in costs:
        raise ShadowEntryRefused(
            "the pricing result carries no execution_costs.total; a missing cost structure is not "
            "a cost of zero")
    if "lamports_out_of_wallet" not in result:
        raise ShadowEntryRefused("the pricing result carries no lamports_out_of_wallet")
    priced["execution_cost_lamports"] = costs["total"]
    # B10a's own total outlay, which includes the curve fees. Re-deriving it as quote + execution
    # would silently drop them.
    priced["total_outlay_lamports"] = result["lamports_out_of_wallet"]
    assert_no_float(priced)
    return STATUS_PRICED, None, priced


def _insert(connection, record):
    columns = ("signature", "scenario_id", "delay_slots", "mint", "t0_slot", "observation_slot",
               "observation_signature", "status", "reason", "quote_lamports", "tokens_out",
               "execution_cost_lamports", "total_outlay_lamports", "base_fee_lamports",
               "priority_fee_lamports", "tip_lamports", "ata_rent_lamports", "failed_attempts",
               "fee_bps", "creator_fee_bps", "cashback_fee_bps", "buyback_fee_bps",
               "evidence_sha256", "priced_at_wall_unix")
    connection.execute(
        f"INSERT OR REPLACE INTO candidate({','.join(columns)}) "
        f"VALUES ({','.join('?' * len(columns))})",
        [record.get(name) for name in columns])


def status(db_path=DB_PATH):
    if not pathlib.Path(db_path).exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started"}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        meta = dict(connection.execute("SELECT key, value FROM metadata"))
        by_status = dict(connection.execute(
            "SELECT status, COUNT(*) FROM candidate GROUP BY 1"))
        by_cell = {}
        for scenario, delay, state, count in connection.execute(
                "SELECT scenario_id, delay_slots, status, COUNT(*) FROM candidate "
                "GROUP BY 1,2,3 ORDER BY 1,2,3"):
            by_cell.setdefault(f"{scenario}@{delay}", {})[state] = count
        reasons = dict(connection.execute(
            "SELECT COALESCE(reason,'none'), COUNT(*) FROM candidate GROUP BY 1 "
            "ORDER BY 2 DESC LIMIT 8"))
        launches = connection.execute(
            "SELECT COUNT(DISTINCT signature) FROM candidate").fetchone()[0]
    finally:
        connection.close()
    report = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": meta.get("preregistration_id"),
        "route_id": meta.get("route_id"),
        "label": meta.get("label"),
        "executable": False,
        "tip_is_an_operator_route_choice": meta.get("tip_is_route_choice") == "1",
        "execution_status": meta.get("execution_status"),
        "performance_status": meta.get("performance_status"),
        "launches_considered": launches,
        "candidates_by_status": by_status,
        "candidates_by_cell": by_cell,
        "top_reasons": reasons,
        "no_landing_probability_claimed": True,
        "no_profit_or_exit_published": True,
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
            "route_id": document["route"]["route_id"],
            "tip_lamports": document["route"]["tip_lamports"],
            "tip_is_an_operator_route_choice": True,
            "delay_slots": document["delay_scenarios"]["values"],
            "scenarios": [s["scenario_id"] for s in document["cost_scenarios"]],
            "label": LABEL, "executable": False,
            "no_landing_probability_claimed": True,
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
