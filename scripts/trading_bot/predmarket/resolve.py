#!/usr/bin/env python3
"""Forward-only settlement resolver -- reads only the venue's OFFICIAL, strictly-later resolution.

For each frozen OPEN estimate this fetches the market's official settlement from the venue's free read
API and, ONLY if the market has actually resolved, records:

  * the YES outcome in {0,1} (a strictly-later world-fact the agent could not have seen at freeze);
  * BRIER_agent = (q_agent - outcome)^2  and  BRIER_market = (p_market - outcome)^2 -- the PRIMARY,
    calibration metric. The agent has a per-market edge iff brier_agent < brier_market;
  * a HYPOTHETICAL bet P&L net of the modeled fee, on the subset where the estimate cleared the edge
    floor (side in {yes,no}) -- the NOISY SECONDARY. Abstentions carry no P&L.

Two things make it honest and lookahead-proof:
  1. The proposer is never run on a resolved market (enforced in `proposer.validate_estimate`), so a
     frozen estimate always predates its outcome.
  2. Here, an estimate stays OPEN (status PENDING) until the venue reports a DEFINITE settlement. A
     phantom outcome is never fabricated before the market officially resolves.
"""

from __future__ import annotations

import datetime as dt
import math

from . import Refused
from .net import http_get_json

KALSHI_MARKET = "https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}"
POLY_MARKET = "https://gamma-api.polymarket.com/markets/{id}"


def _kalshi_fee_roundtrip(p: float, spec: dict) -> float:
    coeff = spec["cost_model"]["kalshi_fee_coeff"]
    return 2.0 * math.ceil(coeff * p * (1.0 - p) * 100.0) / 100.0


def fee_only(venue: str, p: float, spec: dict) -> float:
    """The exchange FEE component only (no spread) for the hypothetical P&L accounting."""
    if venue == "kalshi":
        return _kalshi_fee_roundtrip(p, spec)
    if venue == "polymarket":
        return spec["cost_model"]["polymarket_fee"]
    raise Refused(f"unknown venue {venue!r}")


def fetch_settlement(venue: str, market_id: str) -> dict:
    """Return {'resolved': bool, 'yes_outcome': 0|1|None, 'raw_status': str, 'settled_utc': str|None}.

    Two failure shapes are reported as flags instead of raised, so the pass can log them (T43,
    "never silently dropped"): `vanished` (the venue read API 404s the id) and `ambiguous_close`
    (the venue says closed/settled but the outcome cannot be read as a definite YES/NO)."""
    if venue == "kalshi":
        try:
            data = http_get_json(KALSHI_MARKET.format(ticker=market_id))
        except Refused as exc:
            if "HTTP 404" in str(exc):
                return {"resolved": False, "yes_outcome": None, "vanished": True,
                        "raw_status": "HTTP 404 -- market vanished from the venue read API",
                        "settled_utc": None}
            raise
        m = data.get("market", {})
        status = m.get("status")
        result = (m.get("result") or "").lower()
        resolved = status in ("settled", "finalized", "closed") and result in ("yes", "no")
        yes_outcome = (1 if result == "yes" else 0) if result in ("yes", "no") else None
        ambiguous = status in ("settled", "finalized") and result not in ("yes", "no")
        return {"resolved": bool(resolved), "yes_outcome": yes_outcome, "raw_status": status,
                "ambiguous_close": ambiguous,
                "settled_utc": m.get("expiration_time") or m.get("close_time")}
    if venue == "polymarket":
        try:
            m = http_get_json(POLY_MARKET.format(id=market_id))
        except Refused as exc:
            if "HTTP 404" in str(exc):
                return {"resolved": False, "yes_outcome": None, "vanished": True,
                        "raw_status": "HTTP 404 -- market vanished from the venue read API",
                        "settled_utc": None}
            raise
        closed = bool(m.get("closed"))
        import json as _json
        try:
            prices = _json.loads(m.get("outcomePrices") or "[]")
        except (TypeError, ValueError):
            prices = []
        yes_outcome = None
        if len(prices) == 2:
            try:
                yp = float(prices[0])
                if yp >= 0.99:
                    yes_outcome = 1
                elif yp <= 0.01:
                    yes_outcome = 0
            except (TypeError, ValueError):
                yes_outcome = None
        resolved = closed and yes_outcome is not None
        uma = (m.get("umaResolutionStatus") or "").lower()
        ambiguous = closed and yes_outcome is None and uma in ("resolved", "settled")
        return {"resolved": bool(resolved), "yes_outcome": yes_outcome,
                "ambiguous_close": ambiguous,
                "raw_status": m.get("umaResolutionStatus") or ("closed" if closed else "open"),
                "settled_utc": m.get("closedTime") or m.get("endDate")}
    raise Refused(f"unknown venue {venue!r} for settlement")


def _hypothetical_pnl(estimate: dict, outcome: int, spec: dict):
    """Net P&L per $1 contract for the frozen side, net of the exchange fee. None for abstentions."""
    side = estimate.get("hypothetical_side")
    if side not in ("yes", "no"):
        return None, None
    entry = estimate.get("hypothetical_entry_price")
    if entry is None:
        entry = estimate["p_market"]  # fall back to mid if no book was frozen
    fee = fee_only(estimate["venue"], estimate["p_market"], spec)
    if side == "yes":
        gross = outcome - entry            # buy YES at `entry`, receive `outcome`
    else:
        gross = (1 - outcome) - entry      # buy NO at `entry`, receive 1-outcome
    return round(gross - fee, 4), round(fee, 4)


def resolve_estimate(estimate: dict, spec: dict, *, now_utc: str = None, settlement: dict = None) -> dict:
    """Resolve one OPEN estimate against the venue's official settlement. Returns a resolution record.

    `settlement` lets `resolve_pass` share one fetch across duplicate freezes of the same market."""
    now = now_utc or dt.datetime.now(dt.timezone.utc).isoformat()
    settle = settlement if settlement is not None \
        else fetch_settlement(estimate["venue"], estimate["market_id"])

    if not settle["resolved"]:
        return {"kind": "resolution", "status": "PENDING",
                "estimate_sha256": estimate["estimate_sha256"], "venue": estimate["venue"],
                "market_id": estimate["market_id"], "raw_status": settle["raw_status"],
                "vanished": bool(settle.get("vanished")),
                "ambiguous_close": bool(settle.get("ambiguous_close")),
                "note": "market not yet officially resolved; leaving OPEN"}

    outcome = int(settle["yes_outcome"])
    q, p = estimate["q_agent"], estimate["p_market"]
    brier_agent = round((q - outcome) ** 2, 6)
    brier_market = round((p - outcome) ** 2, 6)
    pnl, fee = _hypothetical_pnl(estimate, outcome, spec)

    return {
        "kind": "resolution", "status": "RESOLVED",
        "estimate_sha256": estimate["estimate_sha256"], "venue": estimate["venue"],
        "market_id": estimate["market_id"], "question": estimate["question"],
        "proposed_utc": estimate["proposed_utc"], "resolved_utc": now,
        "settled_utc": settle["settled_utc"], "raw_status": settle["raw_status"],
        "yes_outcome": outcome, "q_agent": q, "p_market": p,
        "brier_agent": brier_agent, "brier_market": brier_market,
        "brier_edge": round(brier_market - brier_agent, 6),  # >0 == agent beat the market here
        "hypothetical_side": estimate.get("hypothetical_side"),
        "hypothetical_entry_price": estimate.get("hypothetical_entry_price"),
        "hypothetical_pnl_net_fee": pnl, "modeled_fee": fee,
        "NOT_EVIDENCE_YET": ("one resolved market, no bet placed; the honest prior is the agent is "
                             "calibration-competitive but not decisively better, expectancy near zero "
                             "by fees"),
    }


def resolve_pass(spec: dict) -> dict:
    """The mechanical settlement-harvesting pass (T43). Runs from `resolve` AND, first, from `pull`,
    so every tick that looks at markets settles the open book before proposing anything -- resolution
    no longer depends on an agent choosing to run it.

    One settlement fetch per unique (venue, market_id); duplicate freezes share it. A market that
    VANISHED from the venue read API (HTTP 404) or closed with an unreadable outcome gets ONE dated
    UNRESOLVABLE_NOTE in the resolution log -- never silently dropped -- and stays OPEN for retry."""
    from . import ledger
    ledger.verify_preregistration_hashes(ledger.read_preregistrations())
    state = ledger.load_state(spec)
    open_es = ledger.open_estimates()
    noted = {r["estimate_sha256"] for r in ledger.read_resolutions()
             if r.get("status") == "UNRESOLVABLE_NOTE"}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    cache: dict = {}
    results, n_new = [], 0
    for est in open_es:
        key = (est["venue"], est["market_id"])
        if key not in cache:
            try:
                cache[key] = fetch_settlement(est["venue"], est["market_id"])
            except Refused as exc:
                cache[key] = exc
        settle = cache[key]
        if isinstance(settle, Refused):
            rec = {"kind": "resolution", "status": "ERROR", "estimate_sha256": est["estimate_sha256"],
                   "venue": est["venue"], "market_id": est["market_id"], "refused": str(settle)}
        else:
            rec = resolve_estimate(est, spec, settlement=settle)
        if rec.get("status") == "RESOLVED":
            ledger.append_resolution(rec)
            n_new += 1
            if est["estimate_sha256"] not in state["resolved_estimate_hashes"]:
                state["resolved_estimate_hashes"].append(est["estimate_sha256"])
        elif rec.get("status") == "PENDING" and (rec.get("vanished") or rec.get("ambiguous_close")) \
                and est["estimate_sha256"] not in noted:
            note = {"kind": "resolution", "status": "UNRESOLVABLE_NOTE", "noted_utc": now,
                    "estimate_sha256": est["estimate_sha256"], "venue": est["venue"],
                    "market_id": est["market_id"], "raw_status": rec["raw_status"],
                    "note": ("market vanished from the venue read API" if rec.get("vanished") else
                             "venue reports the market closed/settled but the outcome is unreadable"),
                    "consequence": "estimate stays OPEN and is retried every pass; not silently dropped"}
            ledger.append_resolution(note)
            noted.add(est["estimate_sha256"])
        results.append({"market_id": rec["market_id"], "status": rec["status"],
                        "yes_outcome": rec.get("yes_outcome"),
                        "brier_agent": rec.get("brier_agent"), "brier_market": rec.get("brier_market"),
                        "note": rec.get("note") or rec.get("refused")})
    ledger.save_state(state)
    return {"n_open_before": len(open_es), "n_newly_resolved": n_new,
            "n_unique_markets_checked": len(cache),
            "n_unresolvable_noted": len(noted), "results": results}
