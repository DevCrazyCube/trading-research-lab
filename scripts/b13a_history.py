#!/usr/bin/env python3
"""B13a — point-in-time actor and token history. Phase 3 foundation, plumbing only.

Offline, read-only, no network. Pure library: no server, no UI, no model, no signal, no cluster
inference, no wallet, no signing, no live RPC. Schema in `docs/HISTORY_SCHEMA.md`.

Produces an AS-OF-t0 history for the creator, the trading user, the token, and the funding edges
around them, from an immutable canonical event stream. Nothing in it is a feature vector for a
model yet; it is the evidence a feature vector would later be built from, with the point-in-time
boundary already enforced.

THE ONE RULE EVERYTHING ELSE SERVES
===================================

**Only events whose canonical coordinate is at or before t0 may enter.** The comparison is on
`(slot, transaction_index, outer_index, inner_index)` — never on database insertion order, which
records when a collector wrote a row and says nothing about when the chain produced it.

The boundary is INCLUSIVE at t0 and exclusive one coordinate later. An event sharing t0's exact
coordinate is part of the state the decision was made against; an event one inner index later is
not, however tempting the fact that it sits in the same transaction.

WHY EVERY COUNT IS A LOWER BOUND, AND SAYS SO IN ITS NAME
========================================================

A history computed over a bounded window cannot know what happened before the window opened. A
creator with no launches in the window has `prior_launch_count_observed == 0`, and that is a fact
about the window, NOT the statement "this creator has never launched before". Presenting the second
as the first is the single most damaging thing this module could do, because it would turn a
collection artefact into a feature that looks like knowledge.

So every count carries `_observed`, every section publishes `counts_are_lower_bounds`, and
`require_complete_history` fails closed for any policy that needs the true count rather than the
observed one. There is no field in this module that states a total.

WHAT IT DOES NOT DO
===================

No cluster inference: funding edges are published as raw source, destination, amount, coordinate and
provenance, and nothing is joined into an entity. Funding-cluster leakage remains an open gate.
No identity string ever reaches a feature block. No model, no threshold, no label.
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


B10B = _load("b10b_position_path", "b10b_position_path.py")

SCHEMA_VERSION = "1.0.0"

COORDINATE_FIELDS = B10B.CANONICAL_ORDER

BOUNDARY_RULE = (
    "An event enters the history if and only if its canonical coordinate "
    "(slot, transaction_index, outer_index, inner_index) is <= t0's. Inclusive at t0, exclusive one "
    "coordinate later. Database insertion order is never consulted. NOTE for review: a looser "
    "reading would admit the remainder of t0's own transaction, since that transaction is complete "
    "before any order of ours could land. This module takes the STRICTER reading, because an event "
    "it wrongly drops costs information while an event it wrongly admits costs correctness.")

EVENT_LAUNCH = "launch"
EVENT_TRADE = "trade"
EVENT_COMPLETION = "completion"
EVENT_TRANSFER = "transfer"
EVENT_KINDS = (EVENT_LAUNCH, EVENT_TRADE, EVENT_COMPLETION, EVENT_TRANSFER)

# Every event carries where it happened and what evidence produced it. `source_sha256` is not
# decoration: a history is a claim about the past, and a claim about the past that cannot name its
# source is an assertion.
COMMON_EVENT_FIELDS = COORDINATE_FIELDS + ("kind", "source_sha256")
EVENT_FIELDS = {
    EVENT_LAUNCH: ("mint", "bonding_curve", "creator", "create_user"),
    EVENT_TRADE: ("mint", "user", "is_buy", "quote_lamports", "token_units"),
    EVENT_COMPLETION: ("mint",),
    EVENT_TRANSFER: ("from_address", "to_address", "lamports"),
}

COVERAGE_FIELDS = ("first_slot", "last_slot", "source_population", "left_truncated",
                   "right_truncated", "complete", "provenance_sha256", "decode_accounting")

# --------------------------------------------------------------------------------------------
# Decode accounting: the seam where absence of evidence becomes evidence of absence
# --------------------------------------------------------------------------------------------
#
# A funding edge that could not be decoded looks exactly like a funding edge that does not exist.
# Window geometry cannot tell the two apart, so a window that is untruncated but partially
# undecodable would publish `complete: True` and let a policy read a missing edge as "this wallet
# was never funded". That is the seam this accounting closes: every System instruction is placed in
# exactly one bucket, the buckets are asserted to sum, and anything unresolved is carried with its
# coordinate so completeness can be judged PER SUBJECT rather than per window.

D01_UNDECODABLE_SYSTEM_PAYLOAD = "D01_undecodable_system_payload"
D02_MOVING_TRANSFER_WITHOUT_ADDRESSES = "D02_moving_transfer_without_addresses"
D03_MISSING_RAW_BODY = "D03_missing_raw_body"
D04_MISSING_TRANSACTION_COORDINATE = "D04_missing_transaction_coordinate"
UNRESOLVED_REASON_CODES = (D01_UNDECODABLE_SYSTEM_PAYLOAD,
                           D02_MOVING_TRANSFER_WITHOUT_ADDRESSES,
                           D03_MISSING_RAW_BODY,
                           D04_MISSING_TRANSACTION_COORDINATE)

DECODE_ACCOUNTING_FIELDS = (
    "transactions_required", "transactions_with_body", "transactions_missing_body",
    "transactions_missing_coordinate",
    "system_instructions_total", "decoded_moving", "decoded_non_moving", "undecodable",
    "edges_emitted", "moving_self_transfer", "moving_without_addresses",
    "unresolved",
)

# A transaction-level failure has no instruction coordinate, because the instructions are exactly
# what is missing. It is recorded at (slot, transaction_index, -1, -1), which sorts before every
# instruction in that transaction — the conservative placement, since a body we cannot read may
# have contained an edge at any point within it.
TRANSACTION_LEVEL_OUTER_INDEX = -1
TRANSACTION_LEVEL_INNER_INDEX = -1

C01_WINDOW_LEFT_TRUNCATED = "C01_window_left_truncated"
C02_WINDOW_RIGHT_TRUNCATED = "C02_window_right_truncated"
C03_DECODE_ACCOUNTING_ABSENT = "C03_decode_accounting_absent"
C04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0 = "C04_unresolved_evidence_at_or_before_t0"
COMPLETENESS_REASON_CODES = (C01_WINDOW_LEFT_TRUNCATED, C02_WINDOW_RIGHT_TRUNCATED,
                             C03_DECODE_ACCOUNTING_ABSENT,
                             C04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0)

SECTIONS = ("creator", "user", "token", "funding")

# Identity strings live here and nowhere else. Same rule as the b11b feature contract, for the same
# reason: a rule that is checkable without knowing which strings happen to be identities is a rule
# that still works the week nobody is looking.
IDENTITY_FIELDS = {
    "creator": ("creator",),
    "user": ("user",),
    "token": ("mint", "bonding_curve", "creator"),
    "funding": ("subject_address",),
}

FEATURE_FIELDS = {
    "creator": (
        "actor_seen_in_window", "counts_are_lower_bounds",
        "prior_launch_count_observed", "prior_completion_count_observed",
        "prior_launch_with_creator_buy_count_observed",
        "prior_creator_buy_quote_lamports_observed",
        "first_observed_launch_slot", "previous_observed_launch_slot",
        "slots_since_previous_observed_launch",
    ),
    "user": (
        "actor_seen_in_window", "counts_are_lower_bounds",
        "prior_trade_count_observed", "prior_buy_count_observed", "prior_sell_count_observed",
        "prior_quote_in_lamports_observed", "prior_quote_out_lamports_observed",
        "prior_token_in_units_observed", "prior_token_out_units_observed",
        "prior_distinct_mint_count_observed",
        "first_observed_trade_slot", "last_observed_trade_slot",
    ),
    "token": (
        "actor_seen_in_window", "counts_are_lower_bounds",
        "launch_observed_in_window", "launch_slot",
        "slots_since_launch",
        "launch_transaction_trade_count_observed",
        "launch_transaction_creator_buy_present",
        "launch_transaction_creator_buy_quote_lamports_observed",
        "prior_trade_count_observed", "prior_buy_count_observed", "prior_sell_count_observed",
        "prior_quote_in_lamports_observed", "prior_quote_out_lamports_observed",
        "prior_distinct_user_count_observed",
        "completed_before_t0",
    ),
    "funding": (
        "actor_seen_in_window", "counts_are_lower_bounds",
        "inbound_edge_count_observed", "outbound_edge_count_observed",
        "inbound_lamports_observed", "outbound_lamports_observed",
        "distinct_counterparty_count_observed",
    ),
}

HISTORY_FIELDS = ("schema_version", "boundary_rule", "as_of", "subject", "coverage",
                  "sections", "source_hash_chain_sha256", "history_sha256")


class HistoryRefused(B10B.FreezeViolation):
    """Raised when a point-in-time history cannot be built without asserting something untrue."""


# --------------------------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------------------------

def _non_negative_int(label, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoryRefused(f"{label} must be a non-negative integer, got {value!r}")
    return value


def assert_event(event):
    """One event, fully specified. Absence is refusal, never a default."""
    if not isinstance(event, dict):
        raise HistoryRefused(f"event must be a mapping, got {type(event).__name__}")
    kind = event.get("kind")
    if kind not in EVENT_KINDS:
        raise HistoryRefused(f"event kind {kind!r} is not one of {list(EVENT_KINDS)}")
    required = COMMON_EVENT_FIELDS + EVENT_FIELDS[kind]
    missing = [field for field in required if field not in event]
    if missing:
        raise HistoryRefused(f"{kind} event does not state {missing}")
    unknown = [field for field in event if field not in required]
    if unknown:
        raise HistoryRefused(
            f"{kind} event carries undeclared fields {sorted(unknown)}; an event shape nobody "
            "declared is an event nobody reviewed")
    B10B.canonical_key(event)
    if not isinstance(event["source_sha256"], str) or not event["source_sha256"]:
        raise HistoryRefused(
            f"{kind} event has no source_sha256; a claim about the past that cannot name its "
            "source is an assertion")
    if kind == EVENT_TRADE:
        if not isinstance(event["is_buy"], bool):
            raise HistoryRefused("trade is_buy must be a boolean")
        _non_negative_int("trade quote_lamports", event["quote_lamports"])
        _non_negative_int("trade token_units", event["token_units"])
    if kind == EVENT_TRANSFER:
        _non_negative_int("transfer lamports", event["lamports"])
        if event["from_address"] == event["to_address"]:
            raise HistoryRefused("a transfer from an address to itself is not a funding edge")
    for field in EVENT_FIELDS[kind]:
        value = event[field]
        if field in ("is_buy", "quote_lamports", "token_units", "lamports"):
            continue
        if not isinstance(value, str) or not value:
            raise HistoryRefused(f"{kind} event {field} must be a non-empty string")
    return event


def event_hash(event):
    return hashlib.sha256(B10B.canonical_json(event).encode("utf-8")).hexdigest()


def ordered_events(events):
    """Canonically ordered, duplicate-free. The input order is never trusted.

    Sorting here rather than requiring a sorted input is deliberate: a caller who happened to read
    rows in insertion order would otherwise get a different history from the same evidence, and the
    difference would be invisible. Equal coordinates are broken by the event's own hash, so two
    curves touched by one transaction still order deterministically.
    """
    if isinstance(events, (dict, str, bytes)):
        raise HistoryRefused("events must be a sequence of event mappings")
    decorated, seen = [], set()
    for position, event in enumerate(events):
        assert_event(event)
        digest = event_hash(event)
        if digest in seen:
            raise HistoryRefused(
                f"event {position} is a duplicate of an earlier one ({digest[:12]}); counting the "
                "same observation twice inflates every total derived from it")
        seen.add(digest)
        decorated.append((B10B.canonical_key(event), digest, event))
    decorated.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in decorated], [item[1] for item in decorated]


def at_or_before(events, t0_key):
    """The boundary. Inclusive at t0, exclusive one coordinate later."""
    boundary = tuple(t0_key)
    return [event for event in events if B10B.canonical_key(event) <= boundary]


# --------------------------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------------------------

def assert_decode_accounting(accounting):
    """Every System instruction in exactly one bucket, and the buckets must sum.

    Asserted rather than trusted, because the failure this guards against is silent by
    construction: an instruction that quietly falls out of the walk produces no edge, and no edge
    is indistinguishable from no funding.
    """
    if not isinstance(accounting, dict):
        raise HistoryRefused(
            f"decode accounting must be a mapping, got {type(accounting).__name__}")
    missing = [field for field in DECODE_ACCOUNTING_FIELDS if field not in accounting]
    if missing:
        raise HistoryRefused(f"decode accounting does not state {missing}")
    unknown = [field for field in accounting if field not in DECODE_ACCOUNTING_FIELDS]
    if unknown:
        raise HistoryRefused(f"decode accounting carries undeclared fields {sorted(unknown)}")
    for field in DECODE_ACCOUNTING_FIELDS:
        if field == "unresolved":
            continue
        _non_negative_int(f"decode accounting {field}", accounting[field])

    transactions = (accounting["transactions_with_body"]
                    + accounting["transactions_missing_body"]
                    + accounting["transactions_missing_coordinate"])
    if transactions != accounting["transactions_required"]:
        raise HistoryRefused(
            f"transaction accounting sums to {transactions} but "
            f"{accounting['transactions_required']} were required; a body that is neither present "
            "nor recorded missing is one nobody will look for")
    instructions = (accounting["decoded_moving"] + accounting["decoded_non_moving"]
                    + accounting["undecodable"])
    if instructions != accounting["system_instructions_total"]:
        raise HistoryRefused(
            f"instruction accounting sums to {instructions} but "
            f"{accounting['system_instructions_total']} System instructions were seen")
    moving = (accounting["edges_emitted"] + accounting["moving_self_transfer"]
              + accounting["moving_without_addresses"])
    if moving != accounting["decoded_moving"]:
        raise HistoryRefused(
            f"lamport-moving accounting sums to {moving} but {accounting['decoded_moving']} "
            "instructions moved lamports; a movement that produced neither an edge nor a recorded "
            "reason is an edge that vanished")

    unresolved = accounting["unresolved"]
    if not isinstance(unresolved, list):
        raise HistoryRefused("decode accounting unresolved must be a list")
    expected = (accounting["undecodable"] + accounting["moving_without_addresses"]
                + accounting["transactions_missing_body"]
                + accounting["transactions_missing_coordinate"])
    if len(unresolved) != expected:
        raise HistoryRefused(
            f"{len(unresolved)} unresolved items recorded but the counts imply {expected}; the "
            "evidence for a failure is the only thing that lets a later reader judge it")
    for position, item in enumerate(unresolved):
        if not isinstance(item, dict):
            raise HistoryRefused(f"unresolved[{position}] is not a mapping")
        if item.get("reason_code") not in UNRESOLVED_REASON_CODES:
            raise HistoryRefused(
                f"unresolved[{position}] reason {item.get('reason_code')!r} is not one of "
                f"{list(UNRESOLVED_REASON_CODES)}")
        if not isinstance(item.get("detail"), str) or not item["detail"]:
            raise HistoryRefused(f"unresolved[{position}] states no detail")
        coordinate = item.get("coordinate")
        if not isinstance(coordinate, dict) or set(coordinate) != set(COORDINATE_FIELDS):
            raise HistoryRefused(
                f"unresolved[{position}] must carry a full canonical coordinate, so a subject "
                "whose decision predates the failure is not poisoned by it")
        for field in COORDINATE_FIELDS:
            value = coordinate[field]
            if isinstance(value, bool) or not isinstance(value, int):
                raise HistoryRefused(f"unresolved[{position}] coordinate {field} is not an integer")
    return accounting


def unresolved_before(accounting, boundary):
    """Unresolved evidence at or before `boundary`. Everything later cannot poison this subject."""
    return [item for item in accounting["unresolved"]
            if tuple(item["coordinate"][field] for field in COORDINATE_FIELDS) <= tuple(boundary)]


def assert_coverage(coverage):
    """What the window can and cannot know, stated by the caller and never inferred."""
    if not isinstance(coverage, dict):
        raise HistoryRefused(f"coverage must be a mapping, got {type(coverage).__name__}")
    missing = [field for field in COVERAGE_FIELDS if field not in coverage]
    if missing:
        raise HistoryRefused(
            f"coverage does not state {missing}. A history whose window is undescribed cannot say "
            "whether a count of zero means 'none' or 'none that we saw'")
    for field in ("first_slot", "last_slot"):
        _non_negative_int(f"coverage {field}", coverage[field])
    if coverage["last_slot"] < coverage["first_slot"]:
        raise HistoryRefused("coverage ends before it begins")
    for field in ("left_truncated", "right_truncated", "complete"):
        if not isinstance(coverage[field], bool):
            raise HistoryRefused(f"coverage {field} must be a boolean")
    if coverage["complete"] and (coverage["left_truncated"] or coverage["right_truncated"]):
        raise HistoryRefused(
            "coverage claims to be complete while also truncated; a truncated window is exactly "
            "the one whose counts are lower bounds")
    accounting = assert_decode_accounting(coverage["decode_accounting"])
    if coverage["complete"] and accounting["unresolved"]:
        raise HistoryRefused(
            f"coverage claims to be complete while {len(accounting['unresolved'])} pieces of "
            "evidence are unresolved. Untruncated geometry is not completeness: an instruction "
            "that would not decode produces no edge, and no edge is indistinguishable from no "
            "funding")
    if not isinstance(coverage["source_population"], str) or not coverage["source_population"]:
        raise HistoryRefused("coverage must name its source population")
    if not isinstance(coverage["provenance_sha256"], str) or not coverage["provenance_sha256"]:
        raise HistoryRefused("coverage must carry a provenance hash")
    return coverage


def completeness_failures(record):
    """Stable reason codes for why this SUBJECT's history does not rest on complete evidence.

    Per subject, not per window, and deliberately so. A decode failure at a coordinate after this
    decision cannot have removed anything this decision could have seen, so it must not poison it —
    while any unresolved instruction at or before t0 must, because the edge it would have produced
    is exactly the one the history is missing.

    Codes rather than a bare False: "incomplete" tells an operator nothing about what to fix.
    """
    coverage, failures = record["coverage"], []
    if coverage["left_truncated"]:
        failures.append({"reason_code": C01_WINDOW_LEFT_TRUNCATED,
                         "detail": "the window does not reach back far enough to know what "
                                   "preceded it"})
    if coverage["right_truncated"]:
        failures.append({"reason_code": C02_WINDOW_RIGHT_TRUNCATED,
                         "detail": "the window ends before the population it describes"})
    accounting = coverage.get("decode_accounting")
    if not accounting:
        failures.append({"reason_code": C03_DECODE_ACCOUNTING_ABSENT,
                         "detail": "no decode accounting, so silent evidence loss cannot be "
                                   "ruled out"})
        return failures
    boundary = tuple(record["as_of"][field] for field in COORDINATE_FIELDS)
    poisoning = unresolved_before(accounting, boundary)
    if poisoning:
        failures.append({
            "reason_code": C04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0,
            "detail": f"{len(poisoning)} pieces of evidence at or before t0 could not be resolved, "
                      "so an edge this history should contain may be missing",
            "first_unresolved": poisoning[0]})
    return failures


def require_complete_history(record):
    """Fail closed for any policy that needs a true count rather than an observed one.

    Deliberately a separate call. Building a history over a truncated or partially undecodable
    window is legitimate and useful; USING one as though its counts were totals is not, and the
    difference has to be an explicit act rather than an omission.
    """
    failures = completeness_failures(record)
    if failures:
        raise HistoryRefused(
            "this history does not rest on complete evidence, so every count in it is a lower "
            "bound and a policy needing the true count cannot use it: "
            + "; ".join(f"{f['reason_code']} — {f['detail']}" for f in failures))
    return True


# --------------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------------

def _section(name, identity, features, evidence, lower_bounds):
    section = {
        "identity": dict(identity),
        "features": dict(features),
        "evidence": dict(evidence),
    }
    section["features"]["counts_are_lower_bounds"] = lower_bounds
    return section


def _creator_section(events, subject, coverage):
    creator = subject["creator"]
    subject_launch = next(
        (e for e in events if e["kind"] == EVENT_LAUNCH and e["mint"] == subject["mint"]), None)
    boundary = (B10B.canonical_key(subject_launch) if subject_launch is not None else None)

    # Strictly before the subject's own launch, so the launch being decided about can never count
    # as one of its creator's prior launches.
    launches = [e for e in events
                if e["kind"] == EVENT_LAUNCH and e["creator"] == creator
                and e["mint"] != subject["mint"]
                and (boundary is None or B10B.canonical_key(e) < boundary)]
    launched_mints = {e["mint"] for e in launches}
    completions = [e for e in events
                   if e["kind"] == EVENT_COMPLETION and e["mint"] in launched_mints]

    creator_buys = [e for e in events
                    if e["kind"] == EVENT_TRADE and e["user"] == creator and e["is_buy"]
                    and e["mint"] in launched_mints]
    mints_with_creator_buy = {e["mint"] for e in creator_buys}

    slots = sorted(e["slot"] for e in launches)
    previous = slots[-1] if slots else None
    features = {
        "actor_seen_in_window": bool(launches),
        "prior_launch_count_observed": len(launches),
        "prior_completion_count_observed": len(completions),
        "prior_launch_with_creator_buy_count_observed": len(mints_with_creator_buy),
        "prior_creator_buy_quote_lamports_observed": sum(
            e["quote_lamports"] for e in creator_buys),
        "first_observed_launch_slot": slots[0] if slots else None,
        "previous_observed_launch_slot": previous,
        "slots_since_previous_observed_launch": (
            None if previous is None or subject_launch is None
            else subject_launch["slot"] - previous),
    }
    return _section("creator", {"creator": creator}, features,
                    {"prior_launch_mints": sorted(launched_mints)},
                    coverage["left_truncated"])


def _user_section(events, subject, coverage):
    user = subject.get("user")
    if user is None:
        return _section("user", {"user": None},
                        {name: None for name in FEATURE_FIELDS["user"]
                         if name != "counts_are_lower_bounds"},
                        {"note": "no trading user is associated with this decision"},
                        coverage["left_truncated"])
    trades = [e for e in events if e["kind"] == EVENT_TRADE and e["user"] == user]
    buys = [e for e in trades if e["is_buy"]]
    sells = [e for e in trades if not e["is_buy"]]
    slots = [e["slot"] for e in trades]
    features = {
        "actor_seen_in_window": bool(trades),
        "prior_trade_count_observed": len(trades),
        "prior_buy_count_observed": len(buys),
        "prior_sell_count_observed": len(sells),
        # Direction is kept exact and separate. A net figure would hide a wallet that cycled a
        # hundred SOL through the same curve behind one that never traded.
        "prior_quote_in_lamports_observed": sum(e["quote_lamports"] for e in buys),
        "prior_quote_out_lamports_observed": sum(e["quote_lamports"] for e in sells),
        "prior_token_in_units_observed": sum(e["token_units"] for e in buys),
        "prior_token_out_units_observed": sum(e["token_units"] for e in sells),
        "prior_distinct_mint_count_observed": len({e["mint"] for e in trades}),
        "first_observed_trade_slot": min(slots) if slots else None,
        "last_observed_trade_slot": max(slots) if slots else None,
    }
    return _section("user", {"user": user}, features,
                    {"prior_traded_mints": sorted({e["mint"] for e in trades})},
                    coverage["left_truncated"])


def _token_section(events, subject, t0_key, coverage):
    mint = subject["mint"]
    launch = next((e for e in events if e["kind"] == EVENT_LAUNCH and e["mint"] == mint), None)
    trades = [e for e in events if e["kind"] == EVENT_TRADE and e["mint"] == mint]
    buys = [e for e in trades if e["is_buy"]]
    sells = [e for e in trades if not e["is_buy"]]
    completed = any(e["kind"] == EVENT_COMPLETION and e["mint"] == mint for e in events)

    launch_transaction_trades = []
    if launch is not None:
        launch_transaction_trades = [
            e for e in trades
            if (e["slot"], e["transaction_index"]) == (launch["slot"], launch["transaction_index"])]
    creator_launch_buys = [e for e in launch_transaction_trades
                           if launch is not None and e["user"] == launch["creator"] and e["is_buy"]]

    features = {
        "actor_seen_in_window": bool(trades) or launch is not None,
        "launch_observed_in_window": launch is not None,
        "launch_slot": launch["slot"] if launch is not None else None,
        "slots_since_launch": (None if launch is None else t0_key[0] - launch["slot"]),
        "launch_transaction_trade_count_observed": len(launch_transaction_trades),
        "launch_transaction_creator_buy_present": bool(creator_launch_buys),
        "launch_transaction_creator_buy_quote_lamports_observed": sum(
            e["quote_lamports"] for e in creator_launch_buys),
        "prior_trade_count_observed": len(trades),
        "prior_buy_count_observed": len(buys),
        "prior_sell_count_observed": len(sells),
        "prior_quote_in_lamports_observed": sum(e["quote_lamports"] for e in buys),
        "prior_quote_out_lamports_observed": sum(e["quote_lamports"] for e in sells),
        "prior_distinct_user_count_observed": len({e["user"] for e in trades}),
        # Only when the completion is itself at or before t0. A token that completes later has not
        # completed as far as this decision is concerned, and recording it would be the plainest
        # possible outcome leak.
        "completed_before_t0": completed,
    }
    identity = {"mint": mint, "bonding_curve": subject.get("bonding_curve"),
                "creator": launch["creator"] if launch is not None else subject.get("creator")}
    return _section("token", identity, features, {}, coverage["left_truncated"])


def _funding_section(events, subject, coverage):
    address = subject.get("funding_subject_address") or subject.get("creator")
    transfers = [e for e in events if e["kind"] == EVENT_TRANSFER]
    inbound = [e for e in transfers if e["to_address"] == address]
    outbound = [e for e in transfers if e["from_address"] == address]
    counterparties = ({e["from_address"] for e in inbound}
                      | {e["to_address"] for e in outbound})
    features = {
        "actor_seen_in_window": bool(inbound or outbound),
        "inbound_edge_count_observed": len(inbound),
        "outbound_edge_count_observed": len(outbound),
        "inbound_lamports_observed": sum(e["lamports"] for e in inbound),
        "outbound_lamports_observed": sum(e["lamports"] for e in outbound),
        "distinct_counterparty_count_observed": len(counterparties),
    }
    # Raw edges, published as evidence rather than joined into anything. Cluster inference is a
    # later task and funding-cluster leakage remains an open gate; a "cluster id" here would be a
    # judgement wearing the costume of a fact.
    edges = [{
        "direction": "in" if edge["to_address"] == address else "out",
        "from_address": edge["from_address"], "to_address": edge["to_address"],
        "lamports": edge["lamports"],
        "coordinate": {field: edge[field] for field in COORDINATE_FIELDS},
        "source_sha256": edge["source_sha256"],
    } for edge in sorted(inbound + outbound, key=lambda e: (B10B.canonical_key(e), event_hash(e)))]
    return _section("funding", {"subject_address": address}, features,
                    {"edges": edges,
                     "clusters_not_inferred": "raw edges only; no entity resolution is performed"},
                    coverage["left_truncated"])


# --------------------------------------------------------------------------------------------
# Assembly and validation
# --------------------------------------------------------------------------------------------

def assert_disjoint_contract(name, identity_fields, feature_fields):
    """No field may be declared as both an identity and a feature.

    Takes the field sets as arguments rather than reading the module constants, so the check is
    reachable: with the shipped tuples it can never fire, and a guard nobody can make fire is a
    guard nobody can show works.
    """
    overlap = set(identity_fields) & set(feature_fields)
    if overlap:
        raise HistoryRefused(
            f"{name}: {sorted(overlap)} is both an identity and a feature; an identity that is "
            "also a feature is an identity used for prediction")
    return True


def assert_section(name, section):
    """Identity and feature blocks are disjoint, declared, and the feature side holds no string."""
    declared_identity = set(IDENTITY_FIELDS[name])
    declared_features = set(FEATURE_FIELDS[name])
    assert_disjoint_contract(name, IDENTITY_FIELDS[name], FEATURE_FIELDS[name])
    if set(section["identity"]) != declared_identity:
        raise HistoryRefused(
            f"{name} identity block is {sorted(section['identity'])}, contract says "
            f"{sorted(declared_identity)}")
    if set(section["features"]) != declared_features:
        raise HistoryRefused(
            f"{name} feature block is {sorted(section['features'])}, contract says "
            f"{sorted(declared_features)}")
    for field, value in section["features"].items():
        if isinstance(value, str):
            raise HistoryRefused(
                f"{name} feature {field!r} is the string {value!r}. NO STRING MAY APPEAR IN A "
                "FEATURE BLOCK — that is what keeps an identity out of a model without anyone "
                "having to notice which strings are identities")
        if value is not None and not isinstance(value, (int, bool)):
            raise HistoryRefused(
                f"{name} feature {field!r} is a {type(value).__name__}; features are integers, "
                "booleans or null")
    return True


def assert_history(record):
    """Every gate, in one call."""
    if not isinstance(record, dict):
        raise HistoryRefused(f"history must be a mapping, got {type(record).__name__}")
    missing = [field for field in HISTORY_FIELDS if field not in record]
    if missing:
        raise HistoryRefused(f"history does not carry {missing}")
    unknown = [field for field in record if field not in HISTORY_FIELDS]
    if unknown:
        raise HistoryRefused(f"history carries undeclared fields {sorted(unknown)}")
    if set(record["sections"]) != set(SECTIONS):
        raise HistoryRefused(
            f"history sections are {sorted(record['sections'])}, contract says {sorted(SECTIONS)}")
    assert_coverage(record["coverage"])
    for name in SECTIONS:
        assert_section(name, record["sections"][name])
        if (record["sections"][name]["features"]["counts_are_lower_bounds"]
                != record["coverage"]["left_truncated"]):
            raise HistoryRefused(
                f"{name} disagrees with coverage about whether its counts are lower bounds; the "
                "one place a truncated window could be mistaken for a complete one")
    if record["boundary_rule"] != BOUNDARY_RULE:
        raise HistoryRefused("the boundary rule on this record is not the one this module applies")
    return record


def build_as_of_history(events, subject, t0, coverage):
    """One point-in-time history, as of exactly t0.

    `events` may arrive in any order; they are canonically sorted here and every event after t0 is
    discarded before a single figure is computed, so no code path downstream can see one.
    """
    assert_coverage(coverage)
    for field in ("mint", "creator"):
        if not isinstance(subject.get(field), str) or not subject[field]:
            raise HistoryRefused(f"subject must name a non-empty {field}")
    t0_key = B10B.canonical_key(t0)

    ordered, _ = ordered_events(events)
    visible = at_or_before(ordered, t0_key)
    _assert_subject_consistent(visible, subject)
    source_chain = hashlib.sha256()
    for event in visible:
        source_chain.update(event["source_sha256"].encode())

    record = {
        "schema_version": SCHEMA_VERSION,
        "boundary_rule": BOUNDARY_RULE,
        "as_of": {field: t0[field] for field in COORDINATE_FIELDS},
        "subject": {"mint": subject["mint"], "creator": subject["creator"],
                    "bonding_curve": subject.get("bonding_curve"),
                    "user": subject.get("user"),
                    "funding_subject_address": subject.get("funding_subject_address")
                                               or subject["creator"]},
        "coverage": dict(coverage),
        "sections": {
            "creator": _creator_section(visible, subject, coverage),
            "user": _user_section(visible, subject, coverage),
            "token": _token_section(visible, subject, t0_key, coverage),
            "funding": _funding_section(visible, subject, coverage),
        },
        "source_hash_chain_sha256": source_chain.hexdigest(),
        "history_sha256": None,
    }
    assert_history(record)
    record["history_sha256"] = history_hash(record)
    return record


def _assert_subject_consistent(events, subject):
    """The subject's declared creator must be the one its launch event names.

    A caller that passes the wrong creator would otherwise get a perfectly well-formed history full
    of zeros — the most convincing possible way to be wrong, because nothing about the record would
    look unusual.
    """
    launch = next((e for e in events
                   if e["kind"] == EVENT_LAUNCH and e["mint"] == subject["mint"]), None)
    if launch is None:
        return True                    # the launch may simply predate the window; that is coverage
    if launch["creator"] != subject["creator"]:
        raise HistoryRefused(
            f"subject names creator {subject['creator']} but {subject['mint']}'s launch names "
            f"{launch['creator']}; a history built on the wrong creator is all zeros and looks fine")
    if subject.get("bonding_curve") and subject["bonding_curve"] != launch["bonding_curve"]:
        raise HistoryRefused(
            f"subject names bonding curve {subject['bonding_curve']} but the launch names "
            f"{launch['bonding_curve']}")
    return True


def history_hash(record):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in record.items() if k != "history_sha256"}).encode()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "boundary_rule": BOUNDARY_RULE,
        "event_kinds": list(EVENT_KINDS),
        "event_fields": {kind: list(COMMON_EVENT_FIELDS + fields)
                         for kind, fields in EVENT_FIELDS.items()},
        "coverage_fields": list(COVERAGE_FIELDS),
        "sections": list(SECTIONS),
        "identity_fields": {k: list(v) for k, v in IDENTITY_FIELDS.items()},
        "feature_fields": {k: list(v) for k, v in FEATURE_FIELDS.items()},
        "clusters_inferred": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"HistoryRefused: {error}", file=sys.stderr)
        sys.exit(2)
