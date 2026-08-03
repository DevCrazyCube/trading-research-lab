"""B15l — an exact counterfactual round trip on a book that does not react.

Implements `research/B15L_COUNTERFACTUAL_ROUNDTRIP_PREREGISTRATION.json`, committed alone before any
quantity here was computed.

**Nothing here is a return.** Every row carries `COUNTERFACTUAL_UNREACTING_BOOK` and the assumption
`UNREACTING_ORDER_FLOW`, and that assumption is false by construction: the external reserve changes
carried into the counterfactual were produced by traders facing the reserves our order would have
moved. Some of their orders would have executed differently and some would not have landed at all.

**This does not reverse B10b.** B10b refused counterfactual replay because validity cannot be proven
by trade variant — under shifted reserves an exact-token buy costs more than the `max_sol_cost` the
trader signed, and in that case the transaction would not have landed and the observation would not
exist. That refusal stands. What B15L adds is the magnitude of the term B10b declined to model,
computed under an assumption it names rather than hides.

**The arithmetic is not reimplemented.** B9I's three pinned formulas and B10a's `price_entry`,
`price_exit` and `curve_fees` are called directly. A second copy would drift from the gate that
validated them against 92,510 observed trades.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15l"
B15I_DB = ROOT / "research" / "b15i" / "processed_feed.sqlite"
B15F_DB = ROOT / "research" / "b15f" / "checkpoints.sqlite"
B15B_DB = ROOT / "research" / "b15b" / "backfill.sqlite"
B10B_DB = ROOT / "research" / "b10b_observed_paths.sqlite"

PREREG_PATH = ROOT / "research" / "B15L_COUNTERFACTUAL_ROUNDTRIP_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "a1d3c51b76c8a10d048f7c22a2d0c72b69d3024e85d3e7eaa8c2837ded570cfe"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

# Words this study's output may never contain. Checked against the emitted report, because a label
# in a document elsewhere does not stop a column called `profit` from being read as one.
FORBIDDEN_OUTPUT_WORDS = ("return", "profit", "pnl", "p_and_l", "expected_value", "roi",
                          "performance", "gain", "earnings", "yield")

# The two mandated status locks, exempted BY EXACT NAME. Not by prefix: `performance_status` is a
# disclaimer this study is required to carry, while `performance_summary` would be the thing the
# scan exists to stop, and a prefix rule could not tell them apart.
STATUS_LOCK_KEYS = ("performance_status", "execution_status")

L_NOT_CONFIRMED = "L_NOT_CONFIRMED"
L_NO_ENTRY_CHECKPOINT = "L_NO_ENTRY_CHECKPOINT"
L_NO_EXIT_CHECKPOINT = "L_NO_EXIT_CHECKPOINT"
L_NO_FEE_SCHEDULE = "L_NO_FEE_SCHEDULE"
L_NON_NATIVE_QUOTE = "L_NON_NATIVE_QUOTE"
L_MAYHEM = "L_MAYHEM"
L_COMPLETE_AT_ENTRY = "L_COMPLETE_AT_ENTRY"
L_COMPLETE_BY_EXIT = "L_COMPLETE_BY_EXIT"
L_IDENTITY_MISMATCH = "L_IDENTITY_MISMATCH"
L_TIME_ORDER = "L_TIME_ORDER"
L_STALE_CHECKPOINT = "L_STALE_CHECKPOINT"
L_IMPOSSIBLE_RESERVES = "L_IMPOSSIBLE_RESERVES"
L_TRANSPORT_INDEFENSIBLE = "L_TRANSPORT_INDEFENSIBLE"
L_ENTRY_UNPRICEABLE = "L_ENTRY_UNPRICEABLE"
L_EXIT_UNPRICEABLE = "L_EXIT_UNPRICEABLE"
L_FLOAT_PRESENT = "L_FLOAT_PRESENT"
L_UPDATE_RULE_UNVALIDATED = "L_UPDATE_RULE_UNVALIDATED"

LABEL = "COUNTERFACTUAL_UNREACTING_BOOK"
ASSUMPTION = "UNREACTING_ORDER_FLOW"

CENSORING_STATEMENT = (
    "conditioned on cells where BOTH an entry and an exit account checkpoint exist; B15f schedules "
    "from B15a, which B15k measured holding 29% of the launches B15i observes, so this population "
    "is censored by the recorders and not by the market")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B10A = _load("b10a_simulator_kernel", "b10a_simulator_kernel.py")
B9I = _load("b9i_quote_reproduction", "b9i_quote_reproduction.py")

# Taken from the module that pins it, never transcribed. In this regime the native quote mint is the
# SYSTEM PROGRAM address, not the wrapped-SOL mint; a hand-copied literal refused all 22,620
# perfectly native checkpoints on the first run and looked like a data problem.
NATIVE_QUOTE_MINT = B10A.B9D.NATIVE_QUOTE_MINT


class CounterfactualRefused(RuntimeError):
    """This cell is not priced, and the reason is recorded rather than worked around."""


def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise CounterfactualRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise CounterfactualRefused(
            f"the counterfactual preregistration hashes {actual}, pinned {expected}")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    text = path.read_text()
    marker = "FORBIDDEN_OUTPUT_WORDS = (" if "FORBIDDEN_OUTPUT_WORDS = (" in text \
        else "EXECUTION_SURFACE_TOKENS = ("
    body = text.split(marker, 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise CounterfactualRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_integer(label, value):
    """Exact integers only. A float here is not a rounding question, it is a different number."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CounterfactualRefused(f"{L_FLOAT_PRESENT}: {label} is {value!r}, not an integer")
    return value


def _keys(node):
    """Every mapping key in the report, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _keys(value)


def assert_no_forbidden_words(report):
    """No FIELD may be named after a return. Prose that says what this is not is exempt.

    Keys only, split on underscores. An earlier version regex-matched the whole serialised report
    with a `(?<![a-z_])` lookbehind, which excluded `net_return` — the exact name it existed to
    catch — while firing on any disclaimer containing the word.
    """
    found = set()
    for key in _keys(report):
        if key in STATUS_LOCK_KEYS:
            continue
        parts = set(str(key).lower().split("_"))
        for word in FORBIDDEN_OUTPUT_WORDS:
            if set(word.split("_")) <= parts:
                found.add(word)
    if found:
        raise CounterfactualRefused(
            f"the report names a field after {sorted(found)}; no output of this study is a return")
    return True


# --------------------------------------------------------------------------------------------
# The reserve update rule — validated before it is used, or the study refuses
# --------------------------------------------------------------------------------------------

def validate_update_rule(path=B10B_DB, limit=None):
    """A trade moves virtual and real by the SAME delta on each side. Checked, not assumed.

    The whole counterfactual rests on this. If the chain did not behave this way, every transported
    exit state would be wrong in a way no later check would notice, so the rule is reproduced over
    consecutive canonical observations and must hold for every pair it is checked on.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise CounterfactualRefused(
            f"{L_UPDATE_RULE_UNVALIDATED}: no frozen corpus at {path} to validate the rule against")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        rows = connection.execute(
            "SELECT bonding_curve, slot, transaction_index, outer_index, inner_index, "
            "virtual_quote, virtual_token, real_quote, real_token FROM observation "
            "ORDER BY bonding_curve, slot, transaction_index, outer_index, inner_index"
            + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    finally:
        connection.close()
    pairs = mismatches = 0
    previous = None
    for row in rows:
        if previous is not None and previous[0] == row[0]:
            pairs += 1
            if (row[5] - previous[5]) != (row[7] - previous[7]) or \
                    (row[6] - previous[6]) != (row[8] - previous[8]):
                mismatches += 1
        previous = row
    if pairs == 0:
        raise CounterfactualRefused(
            f"{L_UPDATE_RULE_UNVALIDATED}: no consecutive observation pairs to check the rule on")
    if mismatches:
        raise CounterfactualRefused(
            f"{L_UPDATE_RULE_UNVALIDATED}: the virtual and real deltas disagree on {mismatches} of "
            f"{pairs} pairs. Additive transport rests on this rule; a rule that mostly holds is not "
            f"a rule this study may use.")
    return {"pairs_checked": pairs, "mismatches": 0, "rule": "d_virtual == d_real on both sides"}


# --------------------------------------------------------------------------------------------
# The counterfactual state
# --------------------------------------------------------------------------------------------

def assert_transportable(entry, exit_state):
    """The conditions under which carrying an observed delta into the counterfactual is defensible.

    Every one of these is a way the observed world and the counterfactual world stop being
    comparable, rather than a tolerance on how different they may be.
    """
    if entry["bonding_curve"] != exit_state["bonding_curve"] or entry["mint"] != exit_state["mint"]:
        raise CounterfactualRefused(
            f"{L_IDENTITY_MISMATCH}: entry names {entry['bonding_curve']}/{entry['mint']} and exit "
            f"names {exit_state['bonding_curve']}/{exit_state['mint']}")
    for label, state in (("entry", entry), ("exit", exit_state)):
        if state["quote_mint"] != NATIVE_QUOTE_MINT:
            raise CounterfactualRefused(
                f"{L_NON_NATIVE_QUOTE}: the {label} checkpoint quotes in {state['quote_mint']}")
        if state["mayhem_mode"]:
            raise CounterfactualRefused(f"{L_MAYHEM}: the {label} checkpoint is in mayhem mode")
    if entry["complete"]:
        raise CounterfactualRefused(f"{L_COMPLETE_AT_ENTRY}: the curve is already complete")
    if exit_state["complete"]:
        # Completion depends on the real token reserve reaching its floor, and our order moves WHEN
        # that happens. The observed completion instant is not the counterfactual one, so there is
        # no honest exit state to price against.
        raise CounterfactualRefused(
            f"{L_COMPLETE_BY_EXIT}: the curve is complete at the exit checkpoint; our order would "
            f"have moved the instant it completed, so the observed one is not ours")
    if exit_state["context_slot"] < entry["context_slot"]:
        raise CounterfactualRefused(
            f"{L_TIME_ORDER}: exit context {exit_state['context_slot']} precedes entry context "
            f"{entry['context_slot']}")
    return True


def counterfactual_exit_state(entry, exit_state, tokens_out, quote_in):
    """entry + our delta + the observed external delta, component by component.

    Our delta moves virtual and real by the same amount on each side, which is the rule
    `validate_update_rule` reproduced over 93,253 consecutive observations with no exception.
    """
    for label, value in (("tokens_out", tokens_out), ("quote_in", quote_in)):
        assert_integer(label, value)
    external = {}
    for field in ("virtual_quote", "virtual_token", "real_quote", "real_token"):
        assert_integer(f"entry {field}", entry[field])
        assert_integer(f"exit {field}", exit_state[field])
        external[field] = exit_state[field] - entry[field]
    ours = {"virtual_quote": quote_in, "real_quote": quote_in,
            "virtual_token": -tokens_out, "real_token": -tokens_out}
    state = {field: entry[field] + ours[field] + external[field] for field in ours}
    # The external delta was produced by traders facing the ORIGINAL reserves. If carrying it in
    # takes more tokens than the counterfactual curve holds, that trader's order could not have
    # executed as observed, and no adjustment here can invent what they would have done instead.
    if state["real_token"] < 0:
        raise CounterfactualRefused(
            f"{L_TRANSPORT_INDEFENSIBLE}: the observed external flow removes more tokens than the "
            f"counterfactual curve holds ({state['real_token']} left); somebody else's trade could "
            f"not have executed as observed and this study will not guess what they did instead")
    if state["virtual_quote"] <= 0 or state["virtual_token"] <= 0 or state["real_quote"] < 0:
        raise CounterfactualRefused(
            f"{L_IMPOSSIBLE_RESERVES}: the counterfactual exit reserves are impossible {state}")
    state.update({"quote_mint": exit_state["quote_mint"], "mayhem_mode": exit_state["mayhem_mode"],
                  "complete": exit_state["complete"], "slot": exit_state["context_slot"]})
    return state, external, ours


def price_cell(entry, exit_state, schedule, policy, position_lamports, exit_pricer=None):
    """One (launch, delay, horizon, scenario). Returns the counterfactual and its naive comparison.

    The naive figure prices the same sale against the OBSERVED exit state, with no self-impact. It
    exists only so the size of the self-impact term is visible, and it is never a selection
    criterion and never the headline.
    """
    assert_transportable(entry, exit_state)
    entry_state = {"virtual_quote": entry["virtual_quote"], "virtual_token": entry["virtual_token"],
                   "real_quote": entry["real_quote"], "real_token": entry["real_token"],
                   "quote_mint": entry["quote_mint"], "mayhem_mode": entry["mayhem_mode"],
                   "complete": entry["complete"], "slot": entry["context_slot"]}
    try:
        bought = B10A.price_entry(
            entry_state, {"side": B10A.BUY, "quote_lamports": position_lamports}, schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        raise CounterfactualRefused(f"{L_ENTRY_UNPRICEABLE}: {error}") from error
    tokens = bought["tokens_out"]
    transported, external, ours = counterfactual_exit_state(
        entry, exit_state, tokens, position_lamports)
    # `exit_pricer` is injectable so the status guard below is REACHABLE. B10a returns a non-priced
    # status only for a complete curve, which assert_transportable has already refused, so with the
    # real pricer the branch can never fire — and a check nobody can provoke is worse than none.
    pricer = B10A.price_exit if exit_pricer is None else exit_pricer
    try:
        sold = pricer(transported, tokens, schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        raise CounterfactualRefused(f"{L_EXIT_UNPRICEABLE}: {error}") from error
    if sold.get("status") != B10A.STATUS_PRICED:
        raise CounterfactualRefused(f"{L_EXIT_UNPRICEABLE}: {sold.get('liquidity')}")

    naive_state = {"virtual_quote": exit_state["virtual_quote"],
                   "virtual_token": exit_state["virtual_token"],
                   "real_quote": exit_state["real_quote"], "real_token": exit_state["real_token"],
                   "quote_mint": exit_state["quote_mint"],
                   "mayhem_mode": exit_state["mayhem_mode"], "complete": exit_state["complete"],
                   "slot": exit_state["context_slot"]}
    naive = None
    try:
        candidate = B10A.price_exit(naive_state, tokens, schedule, policy)
        if candidate.get("status") == B10A.STATUS_PRICED:
            naive = candidate["lamports_into_wallet"]
    except Exception:                                                     # noqa: BLE001
        naive = None      # a naive figure that refuses is absent, never zero

    counterfactual_net = sold["lamports_into_wallet"] - bought["lamports_out_of_wallet"]
    row = {
        "label": LABEL, "assumption": ASSUMPTION, "executable": False,
        "landing_probability": "unmeasured", "competitor_response": "unmeasured",
        "tokens_acquired": tokens,
        "lamports_out_of_wallet_at_entry": bought["lamports_out_of_wallet"],
        "lamports_into_wallet_at_exit": sold["lamports_into_wallet"],
        "counterfactual_net_lamports": counterfactual_net,
        "naive_unreacting_exit_net_lamports": naive,
        "self_impact_lamports": (None if naive is None
                                 else sold["lamports_into_wallet"] - naive),
        "entry_curve_fees": bought["curve_fees"]["charged_total"],
        "exit_curve_fees": sold["curve_fees"]["charged_total"],
        "entry_execution_lamports": bought["execution_costs"]["total"],
        "exit_execution_lamports": sold["execution_costs"]["total"],
        "ata_rent_charged_never_refunded": bought["execution_costs"][
            "ata_rent_charged_never_refunded"],
        "external_delta": external, "our_delta": ours,
        "entry_context_slot": entry["context_slot"], "exit_context_slot": exit_state["context_slot"],
    }
    for key, value in row.items():
        if isinstance(value, int) and not isinstance(value, bool):
            assert_integer(key, value)
    return row


# --------------------------------------------------------------------------------------------
# Loading the population
# --------------------------------------------------------------------------------------------

def _read_only(path, label):
    path = pathlib.Path(path)
    if not path.exists():
        raise CounterfactualRefused(f"no {label} artifact at {path}")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)


def load_entries(b15i_path=B15I_DB):
    """B15i entry checkpoints whose launch is chain-confirmed. Keyed (signature, delay)."""
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
        record["mayhem_mode"] = bool(record["mayhem_mode"])
        record["complete"] = bool(record["complete"])
        entries[(record["signature"], record["delay_slots"])] = record
    return entries


def load_exits(b15f_path=B15F_DB):
    """B15f exit checkpoints. Keyed (signature, delay, horizon)."""
    connection = _read_only(b15f_path, "B15f")
    try:
        # The identity columns live on `schedule`, not on `checkpoint`. Joining rather than
        # assuming: a curve address taken from the wrong row is exactly the identity mismatch the
        # gate below exists to catch, and it would catch nothing if both sides came from one guess.
        rows = connection.execute(
            "SELECT c.entry_signature, c.delay_slots, c.horizon, s.bonding_curve, s.mint, "
            "c.context_slot, c.lateness_slots, c.virtual_quote, c.virtual_token, c.real_quote, "
            "c.real_token, c.quote_mint, c.mayhem_mode, c.complete "
            "FROM checkpoint c JOIN schedule s ON s.entry_signature = c.entry_signature "
            "AND s.delay_slots = c.delay_slots AND s.horizon = c.horizon").fetchall()
    finally:
        connection.close()
    fields = ("signature", "delay_slots", "horizon", "bonding_curve", "mint", "context_slot",
              "lateness_slots", "virtual_quote", "virtual_token", "real_quote", "real_token",
              "quote_mint", "mayhem_mode", "complete")
    exits = {}
    for row in rows:
        record = dict(zip(fields, row))
        record["mayhem_mode"] = bool(record["mayhem_mode"])
        record["complete"] = bool(record["complete"])
        exits[(record["signature"], record["delay_slots"], record["horizon"])] = record
    return exits


def assert_fresh(record, tolerance, label):
    lateness = record.get("lateness_slots")
    if lateness is None or lateness > tolerance:
        raise CounterfactualRefused(
            f"{L_STALE_CHECKPOINT}: the {label} checkpoint is {lateness} slots late against a "
            f"{tolerance}-slot tolerance")
    return True


# --------------------------------------------------------------------------------------------
# The study
# --------------------------------------------------------------------------------------------

def run(document=None, b15i_path=B15I_DB, b15f_path=B15F_DB, schedules=None, tolerance=150,
        validate_rule=True, b10b_path=B10B_DB):
    """Every cell, every scenario, every horizon. Nothing aggregated across either."""
    assert_no_execution_surface()
    document = verify_preregistration() if document is None else document
    frozen = document["frozen_inputs_taken_from_earlier_freezes_unchanged"]
    position = frozen["position_lamports"]
    delays = frozen["entry_delays_slots"]
    horizons = frozen["exit_horizons"]
    scenarios = frozen["cost_scenarios"]
    report = {"schema_version": SCHEMA_VERSION, "label": LABEL, "assumption": ASSUMPTION,
              "executable": False, "landing_probability": "unmeasured",
              "competitor_response": "unmeasured", "performance_status": "not_evaluated",
              "execution_status": "never_executed",
              "censoring_statement": CENSORING_STATEMENT,
              "position_lamports": position, "delays": delays, "horizons": horizons,
              "by_scenario_horizon_delay": {}, "refusals": {}}
    report["update_rule"] = (validate_update_rule(b10b_path) if validate_rule
                             else {"skipped": "caller supplied states directly"})

    entries = load_entries(b15i_path) if isinstance(b15i_path, (str, pathlib.Path)) else b15i_path
    exits = load_exits(b15f_path) if isinstance(b15f_path, (str, pathlib.Path)) else b15f_path
    schedules = {} if schedules is None else schedules

    def refuse(code):
        report["refusals"][code] = report["refusals"].get(code, 0) + 1

    # Deterministic iteration: sorted keys, never dictionary or arrival order.
    for scenario in scenarios:
        policy = {"base_fee_lamports": scenario["base_fee_lamports"],
                  "priority_fee_lamports": scenario["priority_fee_lamports"],
                  "tip_lamports": scenario["tip_lamports"],
                  "ata_rent_lamports": scenario["ata_rent_lamports"],
                  "failed_attempts": scenario["failed_attempts"]}
        for horizon in horizons:
            for delay in delays:
                priced = []
                for key in sorted(k for k in exits if k[1] == delay and k[2] == horizon):
                    signature = key[0]
                    entry = entries.get((signature, delay))
                    if entry is None:
                        refuse(L_NO_ENTRY_CHECKPOINT)
                        continue
                    schedule = schedules.get(signature)
                    if schedule is None:
                        refuse(L_NO_FEE_SCHEDULE)
                        continue
                    try:
                        assert_fresh(entry, tolerance, "entry")
                        assert_fresh(exits[key], tolerance, "exit")
                        priced.append(price_cell(entry, exits[key], schedule, policy, position))
                    except CounterfactualRefused as error:
                        refuse(str(error).split(":", 1)[0])
                report["by_scenario_horizon_delay"][
                    f"{scenario['scenario_id']}|{horizon}|{delay}"] = summarise(priced)
    report["population"] = {"entry_checkpoints": len(entries), "exit_checkpoints": len(exits),
                            "fee_schedules": len(schedules)}
    assert_no_forbidden_words(report)
    return report


def summarise(rows):
    """Counts and an exact distribution. No mean, because a mean of a censored set invites reading
    it as an expectation, and this study publishes no expectation."""
    if not rows:
        return {"priced_cells": 0, "label": LABEL, "assumption": ASSUMPTION}
    net = sorted(row["counterfactual_net_lamports"] for row in rows)
    impacts = sorted(row["self_impact_lamports"] for row in rows
                     if row["self_impact_lamports"] is not None)

    def quantile(values, numerator, denominator):
        if not values:
            return None
        index = (len(values) - 1) * numerator // denominator
        return values[index]

    return {
        "priced_cells": len(rows),
        "label": LABEL, "assumption": ASSUMPTION, "executable": False,
        "counterfactual_net_lamports": {
            "min": net[0], "p25": quantile(net, 1, 4), "median": quantile(net, 1, 2),
            "p75": quantile(net, 3, 4), "max": net[-1],
            "cells_at_or_below_zero": sum(1 for value in net if value <= 0)},
        "self_impact_lamports_diagnostic": ({
            "min": impacts[0], "median": quantile(impacts, 1, 2), "max": impacts[-1],
            "cells": len(impacts),
            "note": "the difference our own order makes to the exit; a diagnostic, never a "
                    "selection criterion"} if impacts else None),
    }


def fee_schedules(signatures, exchange_path=None):
    """Fee basis points decoded EXACTLY from each launch transaction, via B15h's own loader.

    Never a constant. The BondingCurve account publishes no fee fields, B15c observed
    fee_basis_points taking more than one value in a single sample, and a hardcoded 95/5/0/0 was a
    real defect in B15f. A launch whose schedule cannot be decoded is refused, not priced.
    """
    b15h = _load("b15h_prospective_entry", "b15h_prospective_entry.py")
    b7d, discriminator, create_type, types = b15h.PILOT.load_pinned_create_type()
    decoder = {"b7d": b7d, "discriminator": discriminator, "create_type": create_type,
               "types": types}
    return b15h.fee_schedules_from_launch_transactions(signatures, decoder, exchange_path)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B15l counterfactual round trip on an unreacting book (offline, read-only)")
    parser.add_argument("--no-rule-check", action="store_true",
                        help="skip the reserve-update validation (not permitted for publication)")
    parser.add_argument("--out", default=None)
    arguments = parser.parse_args(argv)
    entries = load_entries()
    exits = load_exits()
    schedules = fee_schedules({key[0] for key in exits})
    report = run(b15i_path=entries, b15f_path=exits, schedules=schedules,
                 validate_rule=not arguments.no_rule_check)
    text = json.dumps(report, indent=2, sort_keys=True)
    if arguments.out:
        target = pathlib.Path(arguments.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
