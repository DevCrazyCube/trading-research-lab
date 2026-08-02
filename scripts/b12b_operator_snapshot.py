#!/usr/bin/env python3
"""B12b — the read-only operator snapshot: one versioned, canonical view of the whole pipeline.

Offline, read-only, no network. Pure library: no server, no model, no signal, no wallet, no signing,
no submission, no live RPC. Schema in `docs/OPERATOR_SNAPSHOT_SCHEMA.md`.

Combines pipeline and gate status, simulator/path outcome labels, candidate proposals, B12a risk
decisions, portfolio aggregates and positions, evidence freshness, config ratification and
provenance hashes into ONE record that a local console can render without computing anything.

WHY THE ADAPTER EXISTS AT ALL
=============================

Because the alternative is a browser recomputing research figures. Every number a console shows
should have been derived, checked and hashed by the code that owns it; a UI that divides two
integers to show a percentage has quietly become a second implementation of the metric, and the two
will disagree on the day it matters. So this module assembles, validates and hashes, and the console
only formats.

WHAT IT REFUSES TO ASSEMBLE
===========================

1. **An executable claim.** The banner may say RESEARCH or SIMULATED and nothing else. No outcome
   label outside the known simulated set survives, and `executable` is asserted false.
2. **An approval that contradicts the system's own state.** If the kill switch is engaged, the
   emergency state is set, or the evidence is stale, an approved opportunity is a contradiction and
   the snapshot is refused rather than displayed.
3. **A stale snapshot that calls itself fresh.** `is_stale` is recomputed from the clocks and the
   configured maxima; a snapshot whose flag disagrees with its own numbers is refused.
4. **A float, an unknown field, or a secret.** Floats because every figure here is an exact integer
   or an exact rational pair; unknown fields because a console cannot render what it has no contract
   for; secrets because a snapshot is the artifact most likely to be pasted into a chat window.

UNKNOWN IS NOT ZERO
===================

Every optional numeric field is present and explicitly `null` when unknown, never omitted and never
substituted with zero. The console renders null as a visible "unknown" rather than as a number, and
that only works if the adapter never quietly supplies one.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B12A = _load("b12a_risk_governor", "b12a_risk_governor.py")
B11B = B12A.B11B
B10B = B12A.B10B

SCHEMA_VERSION = "1.0.0"

# The only two levels this project can honestly display. `EXECUTABLE` is deliberately absent: the
# stochastic half of the Phase 2 gate is uncalibrated, so nothing here has ever been executable, and
# a banner is exactly where that would first be forgotten.
STATUS_RESEARCH = "RESEARCH"
STATUS_SIMULATED = "SIMULATED"
ALLOWED_STATUS_LEVELS = (STATUS_RESEARCH, STATUS_SIMULATED)
FORBIDDEN_STATUS_LEVEL = "EXECUTABLE"

SNAPSHOT_FIELDS = (
    "snapshot_schema_version", "status_banner", "overview", "pipeline", "windows", "strategy",
    "opportunities", "simulated_positions", "portfolio", "evidence", "config", "provenance",
    "snapshot_sha256",
)

# Substrings that must never appear in any string a snapshot carries. A snapshot is the artifact
# most likely to be pasted into a chat window, an issue tracker or a screenshot.
FORBIDDEN_SUBSTRINGS = ("api-key", "api_key", "apikey", "private_key", "secret", "password",
                        "authorization", "bearer ", "seed phrase", "mnemonic")


class SnapshotRefused(B10B.FreezeViolation):
    """Raised when a snapshot cannot be assembled without asserting something untrue."""


# --------------------------------------------------------------------------------------------
# Stable code -> plain language. Deterministic, total, and the raw code always travels with it.
# --------------------------------------------------------------------------------------------

REASON_LABELS = {
    B12A.R01_EMERGENCY_STATE:
        "Emergency stop is active. Nothing is approved while it is set.",
    B12A.R02_KILL_SWITCH_ENGAGED:
        "The kill switch is engaged, so all new entries are blocked.",
    B12A.R03_EVIDENCE_INCOMPLETE:
        "The evidence behind this decision is incomplete.",
    B12A.R04_EVIDENCE_CONFLICTING:
        "Two sources of evidence disagree, or evidence is dated after the current instant.",
    B12A.R05_PROGRAM_VERSION_UNSUPPORTED:
        "The on-chain program version at this slot is not one this system has pinned.",
    B12A.R06_EVIDENCE_STALE_SLOTS:
        "The evidence is older than the allowed number of slots.",
    B12A.R07_EVIDENCE_STALE_SECONDS:
        "The evidence is older than the allowed wall-clock age.",
    B12A.R08_NON_SOL_QUOTE:
        "This curve is not SOL-paired, which is outside the regime this system trades.",
    B12A.R09_MAYHEM_MODE:
        "This curve is in Mayhem mode, whose mechanics are outside the frozen regime.",
    B12A.R10_CURVE_COMPLETE:
        "The bonding curve has already completed, so there is no curve trade to make.",
    B12A.R11_CURVE_STATE_INCOMPLETE:
        "The curve state is missing a field, so it cannot be priced.",
    B12A.R12_MIXED_REGIME_WITHIN_CURVE:
        "This curve's own history disagrees about its quote mint or Mayhem mode.",
    B12A.R13_ORDER_EXCEEDS_RESERVE_CAPACITY:
        "The order would take more tokens than the curve actually holds.",
    B12A.R14_ORDER_BUYS_ZERO_TOKENS:
        "At these reserves the order buys zero tokens; it is below the curve's resolution.",
    B12A.R15_ORDER_EXCEEDS_MAX_ORDER_LAMPORTS:
        "The order is larger than the configured maximum single order.",
    B12A.R16_TOTAL_EXPOSURE_LIMIT_EXCEEDED:
        "Placing this order would push total exposure past its limit.",
    B12A.R17_OPEN_POSITION_LIMIT_EXCEEDED:
        "Placing this order would exceed the maximum number of open positions.",
    B12A.R18_CREATOR_EXPOSURE_LIMIT_EXCEEDED:
        "Too much capital would be exposed to this one creator.",
    B12A.R19_CREATOR_POSITION_LIMIT_EXCEEDED:
        "Too many positions would be held on this one creator.",
    B12A.R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED:
        "Today's realised loss has passed its limit, so new entries are blocked.",
    B12A.R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED:
        "The portfolio's realisable drawdown is past its limit.",
    B12A.R22_PORTFOLIO_DRAWDOWN_UNVERIFIABLE:
        "The drawdown limit could not be checked, so it is treated as not passed.",
    B12A.R23_PENDING_EXPOSURE_LIMIT_EXCEEDED:
        "Orders already pending would push pending exposure past its limit.",
    B12A.R24_DUPLICATE_PENDING_PROPOSAL:
        "This exact proposal is already pending; it will not be counted twice.",
}

OUTCOME_LABELS = {
    "marked_at_horizon": "Valued at the horizon from an observed state",
    "right_censored": "Not observable within the window — censored, not a loss",
    "structural_exit_unavailable": "Curve completed; no exit venue in this regime",
    "no_observed_state_in_window": "Nothing traded inside the window, so no value is reported",
    "no_decision": "No position was taken on this curve",
}

LIQUIDITY_LABELS = {
    "L0_full_size_executable": "Whole position could be sold at this state",
    "L2_size_constrained": "Only part of the position could be sold",
    "L1m_no_executable_size": "Nothing could be sold for even one lamport",
    "L3_structural_unavailable": "Curve trading has ended",
}


def label_for(code, mapping):
    """A label, or an explicit unrecognised marker. Never blank, never a dropped row.

    A console that silently omits a code it does not know shows an operator a shorter list than the
    truth, which is the one failure mode worse than showing them a code.
    """
    if code is None:
        return None
    return mapping.get(code, f"Unrecognised code ({code})")


def _coded(code, mapping):
    return None if code is None else {"code": code, "label": label_for(code, mapping)}


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------

def assert_no_float(node, where="snapshot"):
    """Every figure is an exact integer or an exact rational pair. A float is a different number."""
    if isinstance(node, float):
        raise SnapshotRefused(
            f"a float reached the snapshot at {where}: {node!r}. Every figure here is an exact "
            "integer or an exact [numerator, denominator] pair")
    if isinstance(node, dict):
        for key, value in node.items():
            assert_no_float(value, f"{where}.{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            assert_no_float(value, f"{where}[{index}]")
    return True


def assert_no_secret(node, where="snapshot"):
    """No credential-shaped string, and no URL carrying credentials."""
    if isinstance(node, str):
        lowered = node.lower()
        for needle in FORBIDDEN_SUBSTRINGS:
            if needle in lowered:
                raise SnapshotRefused(
                    f"{where} contains {needle!r}. A snapshot is the artifact most likely to be "
                    "pasted into a chat window, so it may not carry anything credential-shaped")
        if "://" in lowered and "@" in lowered.split("://", 1)[1].split("/", 1)[0]:
            raise SnapshotRefused(f"{where} contains a URL with embedded credentials")
    elif isinstance(node, dict):
        for key, value in node.items():
            assert_no_secret(str(key), f"{where}.<key>")
            assert_no_secret(value, f"{where}.{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            assert_no_secret(value, f"{where}[{index}]")
    return True


def assert_no_executable_claim(snapshot):
    banner = snapshot["status_banner"]
    if banner["level"] not in ALLOWED_STATUS_LEVELS:
        raise SnapshotRefused(
            f"status level {banner['level']!r} is not one of {list(ALLOWED_STATUS_LEVELS)}. "
            "Nothing in this project has ever been executable, and the banner is exactly where "
            "that would first be forgotten")
    if banner.get("executable") is not False:
        raise SnapshotRefused("status_banner.executable must be exactly False")
    for position in snapshot["simulated_positions"]:
        if position["outcome_status"] not in OUTCOME_LABELS:
            raise SnapshotRefused(
                f"outcome status {position['outcome_status']!r} is not a known simulated outcome")
    return True


def assert_consistent(snapshot):
    """The contradictions a console must never be asked to render."""
    evidence, overview = snapshot["evidence"], snapshot["overview"]
    computed_stale = (evidence["age_slots"] > evidence["max_age_slots"]
                      or evidence["age_seconds"] > evidence["max_age_seconds"])
    if evidence["is_stale"] != computed_stale:
        raise SnapshotRefused(
            f"evidence claims is_stale={evidence['is_stale']} but its own clocks say "
            f"{computed_stale}; a snapshot that calls itself fresh while its numbers disagree is "
            "the one an operator would trust and should not")

    blocked = (evidence["kill_switch_engaged"] or evidence["emergency_state"]
               or evidence["is_stale"])
    approved = [o for o in snapshot["opportunities"] if o["decision"] == B12A.DECISION_APPROVED]
    if blocked and approved:
        raise SnapshotRefused(
            f"{len(approved)} opportunities are approved while the system is halted or stale; a "
            "console showing that would be showing an approval that cannot be true")
    for opportunity in snapshot["opportunities"]:
        if opportunity["decision"] == B12A.DECISION_APPROVED and opportunity["reasons"]:
            raise SnapshotRefused("an approved opportunity carries rejection reasons")
        if opportunity["decision"] == B12A.DECISION_REJECTED and not opportunity["reasons"]:
            raise SnapshotRefused("a rejected opportunity carries no reason")
    if overview["opportunities_approved"] != len(approved):
        raise SnapshotRefused("the overview approval count disagrees with the opportunity list")
    if overview["opportunities_total"] != len(snapshot["opportunities"]):
        raise SnapshotRefused("the overview total disagrees with the opportunity list")

    strategy = snapshot["strategy"]
    if strategy["unmet_unlock_requirements"] and not strategy["results_locked"]:
        raise SnapshotRefused(
            "results are shown unlocked while unlock requirements are unmet")
    if strategy["model_family"] != "none" and not strategy.get("model_artifact_sha256"):
        raise SnapshotRefused(
            "a model family is named without a frozen model artifact hash")
    return True


def assert_snapshot(snapshot):
    """Every gate, in one call. Returns the snapshot unchanged."""
    if not isinstance(snapshot, dict):
        raise SnapshotRefused(f"snapshot must be a mapping, got {type(snapshot).__name__}")
    missing = [field for field in SNAPSHOT_FIELDS if field not in snapshot]
    if missing:
        raise SnapshotRefused(f"snapshot does not carry {missing}")
    unknown = [field for field in snapshot if field not in SNAPSHOT_FIELDS]
    if unknown:
        raise SnapshotRefused(
            f"snapshot carries undeclared fields {sorted(unknown)}; a console cannot render what "
            "it has no contract for, and a field nobody declared is a field nobody reviewed")
    assert_no_float(snapshot)
    assert_no_secret(snapshot)
    assert_no_executable_claim(snapshot)
    assert_consistent(snapshot)
    return snapshot


# --------------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------------

def _utilisation(used, limit):
    """`used / limit` as an exact reduced pair, or None when the limit is zero.

    Not a percentage. The console formats; this module refuses to hand it a float that a reader
    would then have to trust was rounded the way they expect.
    """
    if limit == 0:
        return None
    return list(B12A.METRICS.reduce_rational(used, limit))


def build_snapshot(*, risk_decisions, portfolio, config, health, pipeline, windows, strategy,
                   simulated_positions, provenance, status_detail):
    """Assemble one canonical snapshot from components that were each validated by their owner."""
    B12A.assert_config(config)
    B12A.assert_health(health)
    B12A.assert_portfolio(portfolio)

    age_slots = health["current_slot"] - health["evidence_slot"]
    age_seconds = health["current_unix"] - health["evidence_unix"]
    is_stale = (age_slots > config["max_evidence_age_slots"]
                or age_seconds > config["max_evidence_age_seconds"])

    opportunities = []
    for decision in risk_decisions:
        if decision["schema_version"] != B12A.SCHEMA_VERSION:
            raise SnapshotRefused(
                f"risk decision schema {decision['schema_version']} is not "
                f"{B12A.SCHEMA_VERSION}; the console would render fields it cannot vouch for")
        opportunities.append({
            "proposal_id": decision["proposal"]["proposal_id"],
            "mint": decision["grouping"]["mint"],
            "bonding_curve": decision["grouping"]["bonding_curve"],
            "creator": decision["grouping"]["creator"],
            "quote_lamports": decision["proposal"]["quote_lamports"],
            "decision": decision["decision"],
            "reasons": [_coded(code, REASON_LABELS) for code in decision["reasons"]],
            "primary_reason": _coded(decision["primary_reason"], REASON_LABELS),
            "exposure_after_lamports": (
                None if decision["exposure_after"] is None
                else decision["exposure_after"]["total_exposure_lamports"]),
            "decision_sha256": decision["decision_sha256"],
        })

    exposure = B12A.exposure_snapshot(portfolio, creator="")
    limits = [
        {"name": "total_exposure_lamports", "limit": config["max_total_exposure_lamports"],
         "used": exposure["total_exposure_lamports"],
         "utilisation": _utilisation(exposure["total_exposure_lamports"],
                                     config["max_total_exposure_lamports"])},
        {"name": "pending_exposure_lamports", "limit": config["max_pending_exposure_lamports"],
         "used": exposure["pending_exposure_lamports"],
         "utilisation": _utilisation(exposure["pending_exposure_lamports"],
                                     config["max_pending_exposure_lamports"])},
        {"name": "open_positions", "limit": config["max_open_positions"],
         "used": exposure["position_count"],
         "utilisation": _utilisation(exposure["position_count"],
                                     config["max_open_positions"])},
        {"name": "max_order_lamports", "limit": config["max_order_lamports"],
         "used": None, "utilisation": None},
    ]

    positions = [{
        "mint": entry["mint"], "creator": entry["creator"],
        "deployed_lamports": entry["deployed_lamports"],
        # Realisable value is a research figure that the portfolio snapshot may or may not carry.
        # Absent means unknown, and unknown is rendered as unknown rather than as zero.
        "realizable_net_lamports": entry.get("realizable_net_lamports"),
    } for entry in portfolio["open_positions"]]

    marked = []
    for entry in simulated_positions:
        marked.append({
            "mint": entry["mint"],
            "horizon_name": entry["horizon_name"],
            "outcome_status": entry["outcome_status"],
            "outcome_label": label_for(entry["outcome_status"], OUTCOME_LABELS),
            "liquidity_state": entry.get("liquidity_state"),
            "liquidity_label": label_for(entry.get("liquidity_state"), LIQUIDITY_LABELS),
            "net_return": entry.get("net_return"),
            "max_drawdown_ratio": entry.get("max_drawdown_ratio"),
            "censoring_reason": entry.get("censoring_reason"),
        })

    snapshot = {
        "snapshot_schema_version": SCHEMA_VERSION,
        "status_banner": {
            "level": STATUS_SIMULATED if strategy["results_locked"] else STATUS_RESEARCH,
            "executable": False,
            "headline": "Simulated research output. Nothing here has been executed.",
            "detail": status_detail,
        },
        "overview": {
            "opportunities_total": len(opportunities),
            "opportunities_approved": sum(
                1 for o in opportunities if o["decision"] == B12A.DECISION_APPROVED),
            "opportunities_rejected": sum(
                1 for o in opportunities if o["decision"] == B12A.DECISION_REJECTED),
            "open_positions": exposure["open_position_count"],
            "pending_orders": exposure["pending_order_count"],
            "results_locked": strategy["results_locked"],
            "kill_switch_engaged": health["kill_switch_engaged"],
            "emergency_state": health["emergency_state"],
        },
        "pipeline": list(pipeline),
        "windows": dict(windows),
        "strategy": dict(strategy),
        "opportunities": opportunities,
        "simulated_positions": marked,
        "portfolio": {
            "aggregates": exposure,
            "positions": positions,
            "limits": limits,
            "risk": {
                "realised_pnl_today_lamports": portfolio["realised_pnl_today_lamports"],
                "max_daily_realised_loss_lamports":
                    config["max_daily_realised_loss_lamports"],
                "peak_realizable_portfolio_lamports":
                    portfolio["peak_realizable_portfolio_lamports"],
                "current_realizable_portfolio_lamports":
                    portfolio["current_realizable_portfolio_lamports"],
                "current_drawdown_ratio": B12A.current_drawdown(portfolio),
                "max_portfolio_drawdown_ratio": list(config["max_portfolio_drawdown_ratio"]),
            },
        },
        "evidence": {
            "evidence_slot": health["evidence_slot"], "current_slot": health["current_slot"],
            "age_slots": age_slots, "max_age_slots": config["max_evidence_age_slots"],
            "evidence_unix": health["evidence_unix"], "current_unix": health["current_unix"],
            "age_seconds": age_seconds,
            "max_age_seconds": config["max_evidence_age_seconds"],
            "is_stale": is_stale,
            "evidence_complete": health["evidence_complete"],
            "evidence_conflicting": health["evidence_conflicting"],
            "program_version_supported": health["program_version_supported"],
            "kill_switch_engaged": health["kill_switch_engaged"],
            "emergency_state": health["emergency_state"],
        },
        "config": {
            "config_version": config["config_version"],
            "ratification": config["ratification"],
            "config_sha256": B12A.config_hash(config),
        },
        "provenance": dict(provenance),
        "snapshot_sha256": None,
    }
    assert_snapshot(snapshot)
    snapshot["snapshot_sha256"] = hashlib.sha256(
        B10B.canonical_json(
            {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}).encode()).hexdigest()
    return snapshot


SYNTHETIC_NOTE = (
    "SYNTHETIC DEMONSTRATION DATA. Every mint, creator, position and figure below is invented for "
    "interface development. No B11a composition was read and no outcome was computed.")


def build_demo_snapshot():
    """A fully synthetic snapshot that exercises every state the console must render.

    Synthetic on purpose and labelled as such in the record itself: the fresh evaluation window has
    never been queried, and a demo fixture drawn from real data would be a composition inspection
    wearing a friendly name.
    """
    creator_a = "CreatorSynthA1111111111111111111111111111111"
    creator_b = "CreatorSynthB2222222222222222222222222222222"
    config = {
        "config_version": "demo-unratified-1", "ratification": "operator_unratified",
        "max_order_lamports": 100_000_000, "max_total_exposure_lamports": 1_000_000_000,
        "max_open_positions": 5, "max_creator_exposure_lamports": 300_000_000,
        "max_creator_positions": 2, "max_daily_realised_loss_lamports": 500_000_000,
        "max_portfolio_drawdown_ratio": [1, 4],
        "max_pending_exposure_lamports": 400_000_000,
        "max_evidence_age_slots": 10, "max_evidence_age_seconds": 5,
    }
    health = {
        "kill_switch_engaged": False, "emergency_state": False, "evidence_complete": True,
        "evidence_conflicting": False, "program_version_supported": True,
        "curve_regime_consistent": True, "evidence_slot": 435_600_000,
        "current_slot": 435_600_003, "evidence_unix": 1_785_600_000,
        "current_unix": 1_785_600_002, "provenance": {},
    }
    portfolio = {
        "open_positions": [
            {"mint": "MintSynth1111111111111111111111111111111111", "creator": creator_a,
             "deployed_lamports": 103_394_280, "realizable_net_lamports": 96_100_000},
            # Realisable value deliberately absent: the console must show it as unknown, not zero.
            {"mint": "MintSynth2222222222222222222222222222222222", "creator": creator_b,
             "deployed_lamports": 103_394_280},
        ],
        "pending_orders": [
            {"proposal_id": "demo-pending-1",
             "mint": "MintSynth3333333333333333333333333333333333",
             "creator": creator_b, "quote_lamports": 100_000_000},
        ],
        "realised_pnl_today_lamports": -12_500_000,
        "peak_realizable_portfolio_lamports": 1_000_000_000,
        "current_realizable_portfolio_lamports": 940_000_000,
    }
    state = {"virtual_quote": 30_000_000_000, "virtual_token": 1_073_000_000_000_000,
             "real_quote": 5_000_000_000, "real_token": 793_100_000_000_000,
             "quote_mint": B11B.NATIVE_QUOTE_MINT, "mayhem_mode": False, "complete": False,
             "slot": 435_600_000}

    def propose(identifier, mint, creator, quote=100_000_000):
        return {"proposal_id": identifier, "mint": mint, "bonding_curve": f"Curve{mint[4:]}",
                "creator": creator, "side": B12A.B10A.BUY, "quote_lamports": quote}

    decisions = [
        B12A.decide(propose("demo-1", "MintSynth4444444444444444444444444444444444", creator_a),
                    state, portfolio, health, config),
        # Rejected on concentration: this creator already holds a position and a pending order.
        B12A.decide(propose("demo-2", "MintSynth5555555555555555555555555555555555", creator_b),
                    state, portfolio, health,
                    dict(config, max_creator_positions=1)),
        # Rejected on regime: a completed curve.
        B12A.decide(propose("demo-3", "MintSynth6666666666666666666666666666666666", creator_a),
                    dict(state, complete=True), portfolio, health, config),
    ]
    strategy = {
        "model_family": "none", "learned_parameters": 0, "fitted_thresholds": 0,
        "primary_policy": B11B.PRIMARY_POLICY, "primary_horizon": B11B.PRIMARY_HORIZON,
        "primary_metric": B11B.PRIMARY_METRIC,
        "label_semantics": B11B.LABEL_SEMANTICS,
        "results_locked": True, "unmet_unlock_requirements": ["U3"],
        "unlock_note": "B11a collection is not complete, so no result may be computed on it.",
    }
    windows = {
        "burned_range_count": 7,
        "fresh_window": {"launch_first_slot": 435_569_150, "launch_last_slot": 435_772_750,
                         "observation_cutoff_slot": 437_211_659, "status": "fresh_preregistered",
                         "queried": False},
        "warnings": [
            "The development corpus is the burned B8b cohort; no return may be measured on it.",
            "The fresh evaluation window has never been queried and is locked until every unlock "
            "requirement is met.",
        ],
    }
    simulated = [
        {"mint": "MintSynth1111111111111111111111111111111111",
         "horizon_name": "h_1000_slots", "outcome_status": "marked_at_horizon",
         "liquidity_state": "L0_full_size_executable", "net_return": [-7, 100],
         "max_drawdown_ratio": [1, 20], "censoring_reason": None},
        {"mint": "MintSynth2222222222222222222222222222222222",
         "horizon_name": "h_1000_slots", "outcome_status": "right_censored",
         "liquidity_state": None, "net_return": None, "max_drawdown_ratio": None,
         "censoring_reason": "The horizon lies beyond the recorded observation window."},
        {"mint": "MintSynth3333333333333333333333333333333333",
         "horizon_name": "h_1000_slots", "outcome_status": "structural_exit_unavailable",
         "liquidity_state": "L3_structural_unavailable", "net_return": None,
         "max_drawdown_ratio": None,
         "censoring_reason": "The curve completed before the horizon."},
    ]
    pipeline = [
        {"stage": "enumerate_creates", "kind": "collection", "runnable": False,
         "blocked_reason": "the frozen observation cutoff is not mature",
         "numbers_withheld": True},
        {"stage": "transaction_bodies", "kind": "collection", "runnable": False,
         "blocked_reason": "the frozen observation cutoff is not mature",
         "numbers_withheld": True},
        {"stage": "reserve_coverage_gate", "kind": "gate", "runnable": False,
         "blocked_reason": "the frozen observation cutoff is not mature",
         "numbers_withheld": True},
        {"stage": "simulator_replay_gate", "kind": "gate", "runnable": False,
         "blocked_reason": "the frozen observation cutoff is not mature",
         "numbers_withheld": True},
        {"stage": "position_paths", "kind": "results", "runnable": False,
         "blocked_reason": "results are locked until every unlock requirement is met",
         "numbers_withheld": True},
        {"stage": "outcome_labels", "kind": "results", "runnable": False,
         "blocked_reason": "results are locked until every unlock requirement is met",
         "numbers_withheld": True},
    ]
    return build_snapshot(
        risk_decisions=decisions, portfolio=portfolio, config=config, health=health,
        pipeline=pipeline, windows=windows, strategy=strategy,
        simulated_positions=simulated,
        provenance={"synthetic": "true", "note": SYNTHETIC_NOTE,
                    "simulator_schema": "b10a-1.0.0", "path_schema": "b10b-1.0.0",
                    "label_schema": "b10c-1.0.0", "risk_schema": "b12a-1.0.0"},
        status_detail=SYNTHETIC_NOTE)


EMBED_OPEN = '<script type="application/json" id="demo-snapshot">'
EMBED_CLOSE = "</script>"


def embed_demo(html_path, snapshot=None):
    """Rewrite the console's embedded demo block so the fixture cannot drift from the page.

    One source of truth: `build_demo_snapshot`. A hand-maintained copy inside the HTML would agree
    with the adapter exactly until the first time somebody changed one of them.
    """
    snapshot = snapshot if snapshot is not None else build_demo_snapshot()
    path = pathlib.Path(html_path)
    html = path.read_text()
    start = html.find(EMBED_OPEN)
    if start < 0:
        raise SnapshotRefused(f"{path} has no embedded demo block to rewrite")
    body_start = start + len(EMBED_OPEN)
    end = html.find(EMBED_CLOSE, body_start)
    if end < 0:
        raise SnapshotRefused(f"{path} has an unterminated embedded demo block")
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    if "</" in payload:
        # A closing tag inside the payload would end the script element early and turn data into
        # markup. It cannot happen with the current fields, and it must never start happening.
        raise SnapshotRefused("the demo snapshot contains a closing tag sequence")
    path.write_text(html[:body_start] + payload + html[end:])
    return snapshot["snapshot_sha256"]


def embedded_demo(html_path):
    """Parse the demo the console actually ships with."""
    html = pathlib.Path(html_path).read_text()
    start = html.find(EMBED_OPEN)
    if start < 0:
        raise SnapshotRefused(f"{html_path} has no embedded demo block")
    body_start = start + len(EMBED_OPEN)
    end = html.find(EMBED_CLOSE, body_start)
    return json.loads(html[body_start:end])


def snapshot_hash(snapshot):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}).encode()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    parser.add_argument("--demo", metavar="PATH", default=None,
                        help="write the synthetic demonstration snapshot to PATH")
    parser.add_argument("--embed", metavar="HTML", default=None,
                        help="rewrite the embedded demo block inside the operator console")
    args = parser.parse_args(argv)
    if args.embed:
        digest = embed_demo(args.embed)
        print(json.dumps({"embedded_in": args.embed, "snapshot_sha256": digest}, indent=2))
        return 0
    if args.demo:
        snapshot = build_demo_snapshot()
        pathlib.Path(args.demo).write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"written": args.demo,
                          "snapshot_sha256": snapshot["snapshot_sha256"]}, indent=2))
        return 0
    if not args.contract:
        parser.error("this module is a library; run `--contract` or `--demo PATH`")
    print(json.dumps({
        "snapshot_schema_version": SCHEMA_VERSION,
        "fields": list(SNAPSHOT_FIELDS),
        "allowed_status_levels": list(ALLOWED_STATUS_LEVELS),
        "forbidden_status_level": FORBIDDEN_STATUS_LEVEL,
        "reason_codes_labelled": len(REASON_LABELS),
        "outcome_codes_labelled": len(OUTCOME_LABELS),
        "liquidity_codes_labelled": len(LIQUIDITY_LABELS),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"SnapshotRefused: {error}", file=sys.stderr)
        sys.exit(2)
