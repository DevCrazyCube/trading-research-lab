#!/usr/bin/env python3
"""B12a — deterministic, fail-closed portfolio risk governor.

Offline, read-only, no network. Pure library: no server, no UI, no model, no signal, no wallet, no
signing, no submission, no live RPC. Schema in `docs/RISK_DECISION_SCHEMA.md`.

Given an immutable candidate order, the exact direct-Pump state, a portfolio/exposure snapshot, a
system-health snapshot and an explicit `RiskConfig`, this decides ONE thing: may that exact order be
placed, or not. **It never produces an order, never resizes one, and never submits anything.**

WHY IT MAY NOT RESIZE, WHICH IS THE WHOLE DESIGN
================================================

A governor that quietly shrinks an order to fit a limit changes the thing being evaluated. The
policy proposed 0.1 SOL, the book received 0.03 SOL, and every return, drawdown and capacity figure
downstream now describes a strategy nobody wrote. So the answer is **approve the exact order, or
reject it with reasons** — never a third option. The evaluation stays honest because the governor
cannot edit it.

FAIL CLOSED, IN THREE SPECIFIC SENSES
=====================================

1. **Default is no trade.** An approval requires every control to pass; the empty reason list is the
   only thing that approves. There is no path that returns approved while holding a reason.
2. **Absence is refusal, never a permissive default.** A missing config field, limit, state field,
   health flag or portfolio field raises. **No financial limit defaults to zero or to infinity** —
   zero would silently disable trading and infinity would silently disable the limit, and both are
   decisions nobody made.
3. **An unexpected failure raises rather than approving.** Every internal error becomes a
   `RiskRefused`, so a bug can stop the system but can never open it.

WHAT IT DOES NOT DECIDE
=======================

Whether the order is a good idea. It has no model, no signal, no view. It also does not choose its
own limits: every cap is caller-supplied and the config must declare itself `operator_unratified`
until a treasury/risk authorization exists, which is recorded on every decision.
"""
import argparse
import copy
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


B11B = _load("b11b_t0_features", "b11b_t0_features.py")
# Reused rather than reimplemented: `reduce_rational` is the project's one exact-rational
# reduction, and a second copy would be a second place for a sign or gcd bug to live.
METRICS = _load("b11b_baseline_metrics", "b11b_baseline_metrics.py")
B10B = B11B.B10B
B10A = B11B.B10A

SCHEMA_VERSION = "1.0.0"

# Stamped on every record. This module has no wallet, no key, no transport and no submission path,
# and the field exists so an operator UI can display that rather than infer it.
NO_SIGNING_OR_SUBMISSION = (
    "This decision authorises nothing. B12a holds no wallet, no key and no transport; it neither "
    "signs nor submits, and an approval here is a risk clearance for a simulated order only.")

# The only ratification state this project can honestly declare today. Adding a value requires a
# treasury/risk authorization recorded in DECISIONS.md, so the enum is the gate rather than a
# comment asking for one.
RATIFICATION_OPERATOR_UNRATIFIED = "operator_unratified"
ALLOWED_RATIFICATION = (RATIFICATION_OPERATOR_UNRATIFIED,)

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"

# --------------------------------------------------------------------------------------------
# Reason codes, in FROZEN PRECEDENCE ORDER — most severe first
# --------------------------------------------------------------------------------------------
#
# Two separate things: the code EVALUATES controls grouped by concern, and the record ORDERS them by
# severity. Those orders differ on purpose, so that emitting reasons in the order they were computed
# produces visibly wrong output rather than accidentally-correct output.

R01_EMERGENCY_STATE = "R01_EMERGENCY_STATE"
R02_KILL_SWITCH_ENGAGED = "R02_KILL_SWITCH_ENGAGED"
R03_EVIDENCE_INCOMPLETE = "R03_EVIDENCE_INCOMPLETE"
R04_EVIDENCE_CONFLICTING = "R04_EVIDENCE_CONFLICTING"
R05_PROGRAM_VERSION_UNSUPPORTED = "R05_PROGRAM_VERSION_UNSUPPORTED"
R06_EVIDENCE_STALE_SLOTS = "R06_EVIDENCE_STALE_SLOTS"
R07_EVIDENCE_STALE_SECONDS = "R07_EVIDENCE_STALE_SECONDS"
R08_NON_SOL_QUOTE = "R08_NON_SOL_QUOTE"
R09_MAYHEM_MODE = "R09_MAYHEM_MODE"
R10_CURVE_COMPLETE = "R10_CURVE_COMPLETE"
R11_CURVE_STATE_INCOMPLETE = "R11_CURVE_STATE_INCOMPLETE"
R12_MIXED_REGIME_WITHIN_CURVE = "R12_MIXED_REGIME_WITHIN_CURVE"
R13_ORDER_EXCEEDS_RESERVE_CAPACITY = "R13_ORDER_EXCEEDS_RESERVE_CAPACITY"
R14_ORDER_BUYS_ZERO_TOKENS = "R14_ORDER_BUYS_ZERO_TOKENS"
R15_ORDER_EXCEEDS_MAX_ORDER_LAMPORTS = "R15_ORDER_EXCEEDS_MAX_ORDER_LAMPORTS"
R16_TOTAL_EXPOSURE_LIMIT_EXCEEDED = "R16_TOTAL_EXPOSURE_LIMIT_EXCEEDED"
R17_OPEN_POSITION_LIMIT_EXCEEDED = "R17_OPEN_POSITION_LIMIT_EXCEEDED"
R18_CREATOR_EXPOSURE_LIMIT_EXCEEDED = "R18_CREATOR_EXPOSURE_LIMIT_EXCEEDED"
R19_CREATOR_POSITION_LIMIT_EXCEEDED = "R19_CREATOR_POSITION_LIMIT_EXCEEDED"
R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED = "R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED"
R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED = "R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED"
R22_PORTFOLIO_DRAWDOWN_UNVERIFIABLE = "R22_PORTFOLIO_DRAWDOWN_UNVERIFIABLE"
R23_PENDING_EXPOSURE_LIMIT_EXCEEDED = "R23_PENDING_EXPOSURE_LIMIT_EXCEEDED"
R24_DUPLICATE_PENDING_PROPOSAL = "R24_DUPLICATE_PENDING_PROPOSAL"

REASON_PRECEDENCE = (
    R01_EMERGENCY_STATE, R02_KILL_SWITCH_ENGAGED, R03_EVIDENCE_INCOMPLETE,
    R04_EVIDENCE_CONFLICTING, R05_PROGRAM_VERSION_UNSUPPORTED, R06_EVIDENCE_STALE_SLOTS,
    R07_EVIDENCE_STALE_SECONDS, R08_NON_SOL_QUOTE, R09_MAYHEM_MODE, R10_CURVE_COMPLETE,
    R11_CURVE_STATE_INCOMPLETE, R12_MIXED_REGIME_WITHIN_CURVE,
    R13_ORDER_EXCEEDS_RESERVE_CAPACITY, R14_ORDER_BUYS_ZERO_TOKENS,
    R15_ORDER_EXCEEDS_MAX_ORDER_LAMPORTS, R16_TOTAL_EXPOSURE_LIMIT_EXCEEDED,
    R17_OPEN_POSITION_LIMIT_EXCEEDED, R18_CREATOR_EXPOSURE_LIMIT_EXCEEDED,
    R19_CREATOR_POSITION_LIMIT_EXCEEDED, R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED,
    R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED, R22_PORTFOLIO_DRAWDOWN_UNVERIFIABLE,
    R23_PENDING_EXPOSURE_LIMIT_EXCEEDED, R24_DUPLICATE_PENDING_PROPOSAL,
)

# b11b's veto codes, mapped rather than re-derived. Reusing that function keeps the governor's
# eligibility IDENTICAL to the evaluation contract's: a governor that admitted a different set of
# curves would make every evaluated result unachievable in practice.
VETO_TO_REASON = {
    B11B.V1_NON_SOL_QUOTE: R08_NON_SOL_QUOTE,
    B11B.V2_MAYHEM_MODE: R09_MAYHEM_MODE,
    B11B.V3_CURVE_COMPLETE_AT_T0: R10_CURVE_COMPLETE,
    B11B.V4_INCOMPLETE_STATE: R11_CURVE_STATE_INCOMPLETE,
    B11B.V5_MIXED_REGIME_WITHIN_CURVE: R12_MIXED_REGIME_WITHIN_CURVE,
    B11B.V6_ORDER_EXCEEDS_REAL_TOKEN_RESERVE: R13_ORDER_EXCEEDS_RESERVE_CAPACITY,
    B11B.V7_ORDER_BUYS_ZERO_TOKENS: R14_ORDER_BUYS_ZERO_TOKENS,
    B11B.V8_UNSUPPORTED_PROGRAM_VERSION: R05_PROGRAM_VERSION_UNSUPPORTED,
}

# --------------------------------------------------------------------------------------------
# Required inputs. Every field listed; absence raises.
# --------------------------------------------------------------------------------------------

CONFIG_FIELDS = (
    "config_version", "ratification",
    "max_order_lamports", "max_total_exposure_lamports", "max_open_positions",
    "max_creator_exposure_lamports", "max_creator_positions",
    "max_daily_realised_loss_lamports", "max_portfolio_drawdown_ratio",
    "max_pending_exposure_lamports", "max_evidence_age_slots", "max_evidence_age_seconds",
)
CONFIG_INTEGER_LIMITS = (
    "max_order_lamports", "max_total_exposure_lamports", "max_open_positions",
    "max_creator_exposure_lamports", "max_creator_positions",
    "max_daily_realised_loss_lamports", "max_pending_exposure_lamports",
    "max_evidence_age_slots", "max_evidence_age_seconds",
)

HEALTH_FIELDS = (
    "kill_switch_engaged", "emergency_state", "evidence_complete", "evidence_conflicting",
    "program_version_supported", "curve_regime_consistent",
    "evidence_slot", "current_slot", "evidence_unix", "current_unix", "provenance",
)

PORTFOLIO_FIELDS = (
    "open_positions", "pending_orders", "realised_pnl_today_lamports",
    "peak_realizable_portfolio_lamports", "current_realizable_portfolio_lamports",
)

PROPOSAL_FIELDS = ("proposal_id", "mint", "bonding_curve", "creator", "side", "quote_lamports")

# Identities are provenance and grouping, never quantities. The exposure block is asserted to hold
# no string, exactly as b11b's feature block is — same rule, same reason.
GROUPING_FIELDS = ("mint", "bonding_curve", "creator")


class RiskRefused(B10B.FreezeViolation):
    """Raised when a decision cannot be made from the evidence and configuration given.

    Deliberately distinct from a rejection. A rejection is an answer; this is the absence of one,
    and the caller must never be able to mistake the second for an approval.
    """


# --------------------------------------------------------------------------------------------
# Validation — absence is refusal
# --------------------------------------------------------------------------------------------

def _non_negative_int(label, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RiskRefused(
            f"{label} must be a non-negative integer, got {value!r}; the governor does not coerce "
            "or default a limit")
    return value


def assert_config(config):
    """Every limit is stated by the operator. Returns the config unchanged.

    No limit has a default. A defaulted zero silently disables trading and a defaulted infinity
    silently disables the limit; both are decisions nobody made, and the second is the one that
    loses money.
    """
    if not isinstance(config, dict):
        raise RiskRefused(f"risk config must be a mapping, got {type(config).__name__}")
    missing = [field for field in CONFIG_FIELDS if field not in config]
    if missing:
        raise RiskRefused(
            f"risk config does not state {missing}. Every limit is caller-supplied and none may be "
            "defaulted to zero or to infinity")
    unknown = [field for field in config if field not in CONFIG_FIELDS]
    if unknown:
        raise RiskRefused(
            f"risk config carries unknown fields {sorted(unknown)}; a misspelled limit is an absent "
            "limit wearing a plausible name")
    if config["ratification"] not in ALLOWED_RATIFICATION:
        raise RiskRefused(
            f"ratification {config['ratification']!r} is not one of {list(ALLOWED_RATIFICATION)}. "
            "No treasury or risk authorization exists yet, so no other value can be true")
    if not isinstance(config["config_version"], str) or not config["config_version"].strip():
        raise RiskRefused("risk config must carry a non-empty config_version")
    for field in CONFIG_INTEGER_LIMITS:
        _non_negative_int(f"risk config {field}", config[field])
    ratio = config["max_portfolio_drawdown_ratio"]
    if (not isinstance(ratio, (list, tuple)) or len(ratio) != 2):
        raise RiskRefused(
            "max_portfolio_drawdown_ratio must be an exact [numerator, denominator] pair; a "
            "percentage in floating point is a different number from the one it prints as")
    _non_negative_int("max_portfolio_drawdown_ratio numerator", ratio[0])
    if isinstance(ratio[1], bool) or not isinstance(ratio[1], int) or ratio[1] <= 0:
        raise RiskRefused(
            f"max_portfolio_drawdown_ratio denominator must be a positive integer, got {ratio[1]!r}")
    return config


def assert_health(health):
    if not isinstance(health, dict):
        raise RiskRefused(f"health snapshot must be a mapping, got {type(health).__name__}")
    missing = [field for field in HEALTH_FIELDS if field not in health]
    if missing:
        raise RiskRefused(
            f"health snapshot does not state {missing}. An unstated health flag is not a healthy "
            "one, and an unstated clock cannot show freshness")
    for field in ("kill_switch_engaged", "emergency_state", "evidence_complete",
                  "evidence_conflicting", "program_version_supported",
                  "curve_regime_consistent"):
        if not isinstance(health[field], bool):
            raise RiskRefused(f"health {field} must be a boolean, got {health[field]!r}")
    for field in ("evidence_slot", "current_slot", "evidence_unix", "current_unix"):
        _non_negative_int(f"health {field}", health[field])
    if not isinstance(health["provenance"], dict):
        raise RiskRefused("health provenance must be a mapping of source to identifier")
    return health


def assert_portfolio(portfolio):
    if not isinstance(portfolio, dict):
        raise RiskRefused(f"portfolio must be a mapping, got {type(portfolio).__name__}")
    missing = [field for field in PORTFOLIO_FIELDS if field not in portfolio]
    if missing:
        raise RiskRefused(
            f"portfolio snapshot does not state {missing}. An absent exposure is not a zero one")
    for name, key in (("open position", "open_positions"), ("pending order", "pending_orders")):
        entries = portfolio[key]
        if isinstance(entries, (dict, str, bytes)) or not hasattr(entries, "__iter__"):
            raise RiskRefused(f"{key} must be a sequence of {name} mappings")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise RiskRefused(f"{key}[{index}] is {type(entry).__name__}, not a mapping")
            for field in ("mint", "creator"):
                if not isinstance(entry.get(field), str) or not entry[field]:
                    raise RiskRefused(f"{key}[{index}] has no {field}")
            amount = "deployed_lamports" if key == "open_positions" else "quote_lamports"
            _non_negative_int(f"{key}[{index}] {amount}", entry.get(amount))
            if key == "pending_orders" and not entry.get("proposal_id"):
                raise RiskRefused(f"pending_orders[{index}] has no proposal_id")
    pnl = portfolio["realised_pnl_today_lamports"]
    if isinstance(pnl, bool) or not isinstance(pnl, int):
        raise RiskRefused(
            f"realised_pnl_today_lamports must be an integer (it may be negative), got {pnl!r}")
    for field in ("peak_realizable_portfolio_lamports", "current_realizable_portfolio_lamports"):
        value = portfolio[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise RiskRefused(f"portfolio {field} must be an integer, got {value!r}")
    return portfolio


def assert_proposal(proposal):
    if not isinstance(proposal, dict):
        raise RiskRefused(f"proposal must be a mapping, got {type(proposal).__name__}")
    missing = [field for field in PROPOSAL_FIELDS if field not in proposal]
    if missing:
        raise RiskRefused(f"proposal does not state {missing}")
    for field in ("proposal_id", "mint", "bonding_curve", "creator"):
        if not isinstance(proposal[field], str) or not proposal[field]:
            raise RiskRefused(f"proposal {field} must be a non-empty string")
    if proposal["side"] != B10A.BUY:
        raise RiskRefused(
            f"proposal side must be {B10A.BUY!r}; this regime enters long on the curve only")
    if _non_negative_int("proposal quote_lamports", proposal["quote_lamports"]) <= 0:
        raise RiskRefused("proposal quote_lamports must be positive; a zero order is not an order")
    return proposal


# --------------------------------------------------------------------------------------------
# Exposure arithmetic — integers only
# --------------------------------------------------------------------------------------------

def exposure_snapshot(portfolio, creator):
    """Current exposure, in integer lamports, with pending orders counted as real.

    Pending orders are counted because they will become positions. A governor that ignored them
    would approve two orders that individually fit and together do not, which is precisely the
    failure a concurrency-aware limit exists to prevent.
    """
    open_positions = list(portfolio["open_positions"])
    pending = list(portfolio["pending_orders"])
    return {
        "open_position_count": len(open_positions),
        "pending_order_count": len(pending),
        "position_count": len(open_positions) + len(pending),
        "open_deployed_lamports": sum(p["deployed_lamports"] for p in open_positions),
        "pending_exposure_lamports": sum(o["quote_lamports"] for o in pending),
        "total_exposure_lamports": (sum(p["deployed_lamports"] for p in open_positions)
                                    + sum(o["quote_lamports"] for o in pending)),
        "creator_position_count": (sum(1 for p in open_positions if p["creator"] == creator)
                                   + sum(1 for o in pending if o["creator"] == creator)),
        "creator_exposure_lamports": (
            sum(p["deployed_lamports"] for p in open_positions if p["creator"] == creator)
            + sum(o["quote_lamports"] for o in pending if o["creator"] == creator)),
    }


def _projected(before, quote_lamports):
    return {
        "position_count": before["position_count"] + 1,
        "total_exposure_lamports": before["total_exposure_lamports"] + quote_lamports,
        "pending_exposure_lamports": before["pending_exposure_lamports"] + quote_lamports,
        "creator_position_count": before["creator_position_count"] + 1,
        "creator_exposure_lamports": before["creator_exposure_lamports"] + quote_lamports,
    }


def current_drawdown(portfolio):
    """`(peak - current) / peak` as an exact reduced pair, or None when unverifiable."""
    peak = portfolio["peak_realizable_portfolio_lamports"]
    current = portfolio["current_realizable_portfolio_lamports"]
    if peak <= 0 or current > peak:
        return None
    return list(METRICS.reduce_rational(peak - current, peak))


def drawdown_reason(portfolio, config):
    """The realizable-portfolio drawdown control, in exact rationals.

    Returns a reason code or None. An unverifiable drawdown REJECTS: a limit that cannot be checked
    is not a limit that has been passed, and a peak of zero is not evidence of no decline.
    """
    peak = portfolio["peak_realizable_portfolio_lamports"]
    current = portfolio["current_realizable_portfolio_lamports"]
    if peak <= 0 or current > peak:
        return R22_PORTFOLIO_DRAWDOWN_UNVERIFIABLE
    numerator, denominator = config["max_portfolio_drawdown_ratio"]
    # (peak - current) / peak > numerator / denominator, by cross-multiplication. Both denominators
    # are positive, so the inequality direction is preserved and no float is involved.
    if (peak - current) * denominator > numerator * peak:
        return R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED
    return None


# --------------------------------------------------------------------------------------------
# The controls
# --------------------------------------------------------------------------------------------

def order_reasons(codes, precedence=REASON_PRECEDENCE):
    """Reasons in FROZEN PRECEDENCE order, deduplicated.

    `precedence` is a parameter rather than a module constant read directly, so a test can hand it a
    permuted order and prove the sort is by that tuple rather than by insertion or by alphabet. A
    sort nobody can distinguish from an accident is not a specified sort.
    """
    unknown = [code for code in codes if code not in precedence]
    if unknown:
        raise RiskRefused(
            f"reason code(s) {sorted(unknown)} are not in the declared precedence; an unordered "
            "reason would make the record's ordering depend on evaluation order")
    return tuple(code for code in precedence if code in set(codes))


def _health_reasons(health, config):
    reasons = set()
    if health["emergency_state"]:
        reasons.add(R01_EMERGENCY_STATE)
    if health["kill_switch_engaged"]:
        reasons.add(R02_KILL_SWITCH_ENGAGED)
    if not health["evidence_complete"]:
        reasons.add(R03_EVIDENCE_INCOMPLETE)
    if health["evidence_conflicting"]:
        reasons.add(R04_EVIDENCE_CONFLICTING)
    if health["current_slot"] - health["evidence_slot"] > config["max_evidence_age_slots"]:
        reasons.add(R06_EVIDENCE_STALE_SLOTS)
    if health["current_unix"] - health["evidence_unix"] > config["max_evidence_age_seconds"]:
        reasons.add(R07_EVIDENCE_STALE_SECONDS)
    if health["evidence_slot"] > health["current_slot"] or (
            health["evidence_unix"] > health["current_unix"]):
        # Evidence from the future is not fresh evidence, it is a broken clock or a mislabelled
        # snapshot. Either way the freshness control cannot be evaluated.
        reasons.add(R04_EVIDENCE_CONFLICTING)
    return reasons


def _exposure_reasons(before, projected, portfolio, config, proposal):
    reasons = set()
    if proposal["quote_lamports"] > config["max_order_lamports"]:
        reasons.add(R15_ORDER_EXCEEDS_MAX_ORDER_LAMPORTS)
    if projected["total_exposure_lamports"] > config["max_total_exposure_lamports"]:
        reasons.add(R16_TOTAL_EXPOSURE_LIMIT_EXCEEDED)
    if projected["position_count"] > config["max_open_positions"]:
        reasons.add(R17_OPEN_POSITION_LIMIT_EXCEEDED)
    if projected["creator_exposure_lamports"] > config["max_creator_exposure_lamports"]:
        reasons.add(R18_CREATOR_EXPOSURE_LIMIT_EXCEEDED)
    if projected["creator_position_count"] > config["max_creator_positions"]:
        reasons.add(R19_CREATOR_POSITION_LIMIT_EXCEEDED)
    if -portfolio["realised_pnl_today_lamports"] > config["max_daily_realised_loss_lamports"]:
        reasons.add(R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED)
    if projected["pending_exposure_lamports"] > config["max_pending_exposure_lamports"]:
        reasons.add(R23_PENDING_EXPOSURE_LIMIT_EXCEEDED)
    drawdown = drawdown_reason(portfolio, config)
    if drawdown:
        reasons.add(drawdown)
    if any(order["proposal_id"] == proposal["proposal_id"]
           for order in portfolio["pending_orders"]):
        reasons.add(R24_DUPLICATE_PENDING_PROPOSAL)
    return reasons


def _state_reasons(state, health, proposal):
    """Eligibility, delegated to b11b so the governor and the evaluator admit the same curves."""
    vetoes = B11B.evaluate_vetoes(
        state, proposal["quote_lamports"],
        regime_in_regime=health["curve_regime_consistent"],
        version_supported=health["program_version_supported"])
    return {VETO_TO_REASON[code] for code in vetoes}


# --------------------------------------------------------------------------------------------
# The decision
# --------------------------------------------------------------------------------------------

def decide(proposal, state, portfolio, health, config, *, precedence=REASON_PRECEDENCE):
    """Approve this exact order, or reject it with every reason that applies.

    There is no third outcome. The order is never resized, never partially filled, never deferred
    with a suggestion — a governor that edits the order changes the thing being evaluated, and every
    downstream return then describes a strategy nobody wrote.

    Controls are evaluated GROUPED BY CONCERN and reported ORDERED BY SEVERITY; the two orders
    differ so that emitting reasons in computation order produces visibly wrong output.
    """
    try:
        assert_config(config)
        assert_health(health)
        assert_portfolio(portfolio)
        assert_proposal(proposal)

        before = exposure_snapshot(portfolio, proposal["creator"])
        projected = _projected(before, proposal["quote_lamports"])

        reasons = set()
        reasons |= _exposure_reasons(before, projected, portfolio, config, proposal)
        reasons |= _state_reasons(state, health, proposal)
        reasons |= _health_reasons(health, config)

        ordered = order_reasons(reasons, precedence)
        approved = not ordered
        record = {
            "schema_version": SCHEMA_VERSION,
            "decision": DECISION_APPROVED if approved else DECISION_REJECTED,
            "approval_is_simulation_only": True,
            "NO_SIGNING_OR_SUBMISSION": NO_SIGNING_OR_SUBMISSION,
            "proposal": copy.deepcopy(proposal),
            "grouping": {field: proposal[field] for field in GROUPING_FIELDS},
            "reasons": list(ordered),
            "primary_reason": ordered[0] if ordered else None,
            "order_was_resized": False,
            "resizing_is_not_available":
                "the governor approves the exact proposed order or rejects it; silently resizing "
                "would change the thing being evaluated",
            "evidence": {
                "evidence_slot": health["evidence_slot"],
                "current_slot": health["current_slot"],
                "age_slots": health["current_slot"] - health["evidence_slot"],
                "evidence_unix": health["evidence_unix"],
                "current_unix": health["current_unix"],
                "age_seconds": health["current_unix"] - health["evidence_unix"],
                "max_age_slots": config["max_evidence_age_slots"],
                "max_age_seconds": config["max_evidence_age_seconds"],
                "provenance": copy.deepcopy(health["provenance"]),
                "kill_switch_engaged": health["kill_switch_engaged"],
                "emergency_state": health["emergency_state"],
            },
            "exposure_before": before,
            # The loss and drawdown controls read portfolio-level figures that appear nowhere in
            # the exposure block. Without them an operator can see THAT those controls passed but
            # not against what, and the decision hash would be blind to a change in either — so a
            # different book could produce a byte-identical record.
            "portfolio_risk": {
                "realised_pnl_today_lamports": portfolio["realised_pnl_today_lamports"],
                "max_daily_realised_loss_lamports": config["max_daily_realised_loss_lamports"],
                "peak_realizable_portfolio_lamports":
                    portfolio["peak_realizable_portfolio_lamports"],
                "current_realizable_portfolio_lamports":
                    portfolio["current_realizable_portfolio_lamports"],
                "current_drawdown_ratio": current_drawdown(portfolio),
                "max_portfolio_drawdown_ratio": list(config["max_portfolio_drawdown_ratio"]),
            },
            # Only on approval. Publishing a projected book for a rejected order would put a number
            # on an operator's screen that describes a state that will never exist.
            "exposure_after": projected if approved else None,
            "config_version": config["config_version"],
            "config_ratification": config["ratification"],
            "config_sha256": config_hash(config),
            "decision_sha256": None,
        }
        _assert_record_consistent(record)
        record["decision_sha256"] = _sha256_of(
            {k: v for k, v in record.items() if k != "decision_sha256"})
        return record
    except B10B.FreezeViolation:
        raise
    except Exception as error:                       # noqa: BLE001 - deliberate, see below
        # Any unexpected failure becomes a refusal, never an approval. A bug must be able to stop
        # this system and must never be able to open it.
        raise RiskRefused(
            f"the governor could not complete a decision ({type(error).__name__}: {error}); "
            "refusing rather than returning a verdict it did not reach") from error


def _assert_record_consistent(record):
    """The invariants an operator would otherwise have to take on trust."""
    if record["decision"] == DECISION_APPROVED and record["reasons"]:
        raise RiskRefused(
            "a record is approved while holding rejection reasons; the empty reason list is the "
            "only thing that approves")
    if record["decision"] == DECISION_REJECTED and not record["reasons"]:
        raise RiskRefused("a record is rejected with no reason; an unexplained refusal is not one")
    if record["decision"] == DECISION_REJECTED and record["exposure_after"] is not None:
        raise RiskRefused("a rejected order published a projected book that will never exist")
    if record["order_was_resized"]:
        raise RiskRefused("the governor does not resize orders")
    for name, value in record["exposure_before"].items():
        if isinstance(value, str) or not isinstance(value, int) or isinstance(value, bool):
            raise RiskRefused(
                f"exposure field {name} is {value!r}; the exposure block holds integer lamports and "
                "counts only, and identities live in the grouping block")
    return True


def _sha256_of(value):
    return hashlib.sha256(B10B.canonical_json(value).encode("utf-8")).hexdigest()


def config_hash(config):
    """Stable across key order, so an operator can compare two configs by one string."""
    return _sha256_of(dict(config))


def apply_approved(portfolio, record):
    """A NEW portfolio snapshot with the approved order added to pending. Never mutates the input.

    The governor holds no state of its own: no module-level book, no cache, no counter. Threading
    the snapshot through the caller is what makes two concurrent proposals accountable — the second
    call sees the first as pending, or the caller has a bug that this design makes visible instead
    of absorbing.
    """
    if record["decision"] != DECISION_APPROVED:
        raise RiskRefused("only an approved decision may be applied to a portfolio")
    updated = copy.deepcopy(portfolio)
    updated["pending_orders"] = list(updated["pending_orders"]) + [{
        "proposal_id": record["proposal"]["proposal_id"],
        "mint": record["proposal"]["mint"],
        "creator": record["proposal"]["creator"],
        "quote_lamports": record["proposal"]["quote_lamports"],
    }]
    return updated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "decisions": [DECISION_APPROVED, DECISION_REJECTED],
        "reason_precedence": list(REASON_PRECEDENCE),
        "required_config_fields": list(CONFIG_FIELDS),
        "required_health_fields": list(HEALTH_FIELDS),
        "required_portfolio_fields": list(PORTFOLIO_FIELDS),
        "required_proposal_fields": list(PROPOSAL_FIELDS),
        "allowed_ratification": list(ALLOWED_RATIFICATION),
        "veto_reuse": {veto: reason for veto, reason in VETO_TO_REASON.items()},
        "NO_SIGNING_OR_SUBMISSION": NO_SIGNING_OR_SUBMISSION,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"RiskRefused: {error}", file=sys.stderr)
        sys.exit(2)
