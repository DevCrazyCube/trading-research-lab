#!/usr/bin/env python3
"""The estimate proposer -- shape of a frozen probability commitment + hard enforcement of discipline.

The discretionary component (part 5, "read the world") is the agent's own probability `q_agent` for an
OPEN market. This module does NOT form that judgement; it specifies the shape a commitment must take
and MECHANICALLY enforces the non-negotiable rules so a reckless or lookahead read cannot reach the
ledger:

  * FORWARD-ONLY   the market snapshot must claim it is OPEN with a close/resolution date strictly in
                   the future -- the proposer is NEVER run on a resolved market (the lookahead trap).
  * CALIBRATION    q_agent must be a real probability in (0,1); p_market at freeze is recorded beside it.
  * EDGE FLOOR     for a HYPOTHETICAL bet to be logged, |q_agent - p_market| must exceed the measured
                   round-trip cost c (fee + half-spread). Below the floor the estimate is still frozen
                   for CALIBRATION scoring but its side is "abstain" (abstention is the default skill).
  * THESIS         a one-paragraph falsifiable reason tied to the specific question is mandatory.

A proposal is a plain dict (an agent emits JSON). `validate_estimate` returns a normalized, enforced
estimate or raises Refused with the exact reason. Nothing here looks at any outcome.

REQUIRED PROPOSAL FIELDS
========================
    venue          : "kalshi" | "polymarket"
    market_id      : the venue's market id/ticker (an OPEN market)
    question       : the market question text (frozen for the record)
    p_market       : float in (0,1) -- the market-implied YES probability captured NOW, at freeze
    q_agent        : float in (0,1) -- the agent's OWN YES probability estimate
    close_time     : ISO8601 -- the market's close/resolution date (must be in the future)
    thesis         : str -- one paragraph tying the estimate to the specific question / live context
    confidence     : float in (0,1]
    spread         : float, optional -- measured ask-bid; used with p_market for the cost floor
    yes_bid, yes_ask : float, optional -- the live book at freeze (for the hypothetical entry price)
    category       : str, optional -- for the record
    event_refs     : list[str], optional -- ids/urls of the news/context the read rests on
"""

from __future__ import annotations

import datetime as dt

from . import Refused
from .frozen import canonical_sha256
from .venues import round_trip_cost, _is_efficient_market, _parse_dt


def _now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _prob(raw: dict, key: str) -> float:
    if key not in raw or raw[key] is None:
        raise Refused(f"proposal is missing required probability field {key!r}")
    try:
        v = float(raw[key])
    except (TypeError, ValueError):
        raise Refused(f"proposal field {key!r} is not a number: {raw[key]!r}")
    if not (0.0 < v < 1.0):
        raise Refused(f"{key} must be a probability strictly in (0,1); got {v}")
    return v


def validate_estimate(raw: dict, spec: dict, *, now_utc: str = None) -> dict:
    """Enforce every frozen rule and return a normalized estimate dict, or raise Refused. No freeze."""
    rules = spec["rules"]
    venue = raw.get("venue")
    if venue not in spec["venues"]:
        raise Refused(f"venue must be one of {sorted(spec['venues'])}, got {venue!r}")
    market_id = str(raw.get("market_id", "")).strip()
    if not market_id:
        raise Refused("proposal is missing market_id")
    question = str(raw.get("question", "")).strip()
    if len(question) < 8:
        raise Refused("proposal is missing a usable question string")

    # Concentrate on rank-1 categories: refuse an efficient macro/crypto market outright (scope §7).
    if _is_efficient_market(question):
        raise Refused("this looks like an efficient macro-print / crypto-threshold market (scope ranks "
                      "4-5). The forward test concentrates on politics/policy/soft-news; skip this.")

    p_market = _prob(raw, "p_market")
    q_agent = _prob(raw, "q_agent")

    # FORWARD-ONLY: refuse anything that is not an OPEN market resolving strictly in the future.
    now = now_utc or _now_utc_iso()
    close = _parse_dt(str(raw.get("close_time", "")))
    if close is None:
        raise Refused("proposal is missing a parseable close_time; a forward commitment needs a future "
                      "resolution date the outcome cannot predate")
    if close <= _parse_dt(now):
        raise Refused(f"close_time {raw.get('close_time')} is not in the future. The proposer must "
                      "NEVER run on a market at/after resolution -- that is the memorised-outcome "
                      "lookahead this instrument exists to defeat.")

    thesis = str(raw.get("thesis", "")).strip()
    if len(thesis) < 40:
        raise Refused("thesis too thin: a falsifiable estimate must state a one-paragraph reason tied "
                      "to the specific question and its live context")
    confidence = float(raw.get("confidence", 0.0))
    if not (0.0 < confidence <= 1.0):
        raise Refused(f"confidence {confidence} must be in (0, 1]")

    # EDGE FLOOR: measure the round-trip cost from the live book and decide the hypothetical side.
    spread = float(raw.get("spread", 0.0) or 0.0)
    cost = round_trip_cost(venue, p_market, spread, spec)
    edge = q_agent - p_market
    if abs(edge) > cost:
        side = "yes" if edge > 0 else "no"
    else:
        side = "abstain"  # frozen for CALIBRATION, but no hypothetical bet clears the fee/spread wall

    # Hypothetical entry price (the crossed price) -- recorded only, never an order.
    yes_bid = raw.get("yes_bid")
    yes_ask = raw.get("yes_ask")
    entry_price = None
    if side == "yes" and yes_ask is not None:
        entry_price = float(yes_ask)
    elif side == "no" and yes_bid is not None:
        entry_price = round(1.0 - float(yes_bid), 4)  # buy NO ~= 1 - yes_bid crossed

    return {
        "venue": venue, "market_id": market_id, "question": question,
        "category": str(raw.get("category", "") or ""),
        "p_market": round(p_market, 4), "q_agent": round(q_agent, 4),
        "abs_edge": round(abs(edge), 4), "round_trip_cost": round(cost, 4),
        "clears_edge_floor": abs(edge) > cost, "hypothetical_side": side,
        "hypothetical_entry_price": entry_price,
        "yes_bid": (float(yes_bid) if yes_bid is not None else None),
        "yes_ask": (float(yes_ask) if yes_ask is not None else None),
        "spread": round(spread, 4),
        "close_time": str(raw.get("close_time")),
        "thesis": thesis, "confidence": confidence,
        "event_refs": list(raw.get("event_refs", [])),
    }


def freeze_estimate(validated: dict, *, proposed_utc: str = None) -> dict:
    """Stamp a validated estimate with proposed_utc and its canonical sha256 -- the forward commitment.

    The hash is computed over the full spec (INCLUDING p_market and q_agent at freeze) together with
    proposed_utc, so the commitment is tamper-evident and provably predates the resolution.
    """
    body = dict(validated)
    body["proposed_utc"] = proposed_utc or _now_utc_iso()
    body["estimate_sha256"] = canonical_sha256(body)
    body["status"] = "OPEN"
    return body


def no_trade_record(reason: str, *, market_id: str = None) -> dict:
    """The disciplined abstention -- logged as behaviour (not betting is the skill)."""
    return {"kind": "no_trade", "proposed_utc": _now_utc_iso(),
            "reason": reason, "market_id": market_id}
