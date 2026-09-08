#!/usr/bin/env python3
"""The setup proposer -- deterministic scaffolding + hard enforcement of parts 2/3/4.

THE INTERFACE (the agent brain fills this in at run time)
=========================================================
Part 5 of the edge -- the contextual READ of the world -- is a discretionary judgement made by an LLM
agent at run time, given the world-reader's event stream. This module does NOT make that judgement; it
specifies the shape a proposal must take and then MECHANICALLY enforces the non-negotiable rules so a
weak or reckless read cannot reach the ledger:

  * asymmetry  (part 2): reward:risk >= 2.0, a real stop is mandatory;
  * risk sizing (part 3): <= 1.0% account risk to the stop; size = 0.01*account/|entry-stop|;
  * discipline  (part 4): <= 5 concurrent open setups, direction consistency, horizon bounds,
                          liquid free-priceable instruments only, and "no trade today" is allowed.

A proposal is a plain dict (so an agent can emit JSON); `validate_setup` returns a normalized,
enforced setup or raises Refused with the exact reason. Nothing here looks at any outcome.

REQUIRED PROPOSAL FIELDS
========================
    instrument     : symbol -- a watchlist equity/ETF ticker, or a crypto id/symbol in the universe
    asset_class    : "equity" | "crypto"
    direction      : "long" | "short"
    entry_ref      : float  -- the reference price the setup is committed to enter at (live, at freeze)
    stop           : float  -- defines the 1% risk; long: stop<entry; short: stop>entry
    target         : float  -- enforces R:R>=2; long: target>entry; short: target<entry
    horizon_hours  : int in [1, 240]
    thesis         : str    -- one paragraph tying the trade to the SPECIFIC event(s)
    confidence     : float in (0, 1]
    event_ids      : list[str] -- ids of the world-reader events that triggered it (>=1)
    account_risk_pct : float, optional (default 1.0), must be <= 1.0
"""

from __future__ import annotations

import json

import datetime as dt

from . import Refused
from .frozen import canonical_sha256


def _now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _num(raw: dict, key: str) -> float:
    if key not in raw or raw[key] is None:
        raise Refused(f"proposal is missing required numeric field {key!r}")
    try:
        return float(raw[key])
    except (TypeError, ValueError):
        raise Refused(f"proposal field {key!r} is not a number: {raw[key]!r}")


def _known_instrument(instrument: str, asset_class: str, spec: dict) -> str:
    """Refuse anything but a liquid, free-priceable symbol from the frozen universes."""
    if asset_class == "equity":
        if instrument not in spec["equity_watchlist"]:
            raise Refused(f"{instrument!r} is not in the frozen equity watchlist; only liquid, "
                          "free-priceable US equities/ETFs may be proposed")
        return instrument
    if asset_class == "crypto":
        by_id = spec["crypto_universe"]
        by_sym = {v.upper(): k for k, v in by_id.items()}
        if instrument in by_id:
            return instrument                       # already a coingecko id
        if instrument.upper() in by_sym:
            return by_sym[instrument.upper()]       # normalize symbol -> id
        raise Refused(f"{instrument!r} is not in the frozen crypto universe {sorted(by_id)}")
    raise Refused(f"asset_class {asset_class!r} not in {spec['rules']['allowed_asset_classes']}")


def validate_setup(raw: dict, spec: dict, *, n_open: int = 0) -> dict:
    """Enforce every §6 rule and return a normalized setup dict, or raise Refused. No freeze here."""
    rules = spec["rules"]
    asset_class = raw.get("asset_class")
    if asset_class not in rules["allowed_asset_classes"]:
        raise Refused(f"asset_class must be one of {rules['allowed_asset_classes']}, got {asset_class!r}")
    instrument = _known_instrument(str(raw.get("instrument", "")), asset_class, spec)

    direction = raw.get("direction")
    if direction not in ("long", "short"):
        raise Refused(f"direction must be 'long' or 'short', got {direction!r}")

    entry = _num(raw, "entry_ref")
    stop = _num(raw, "stop")
    target = _num(raw, "target")
    if entry <= 0 or stop <= 0 or target <= 0:
        raise Refused("entry/stop/target must be positive prices")

    # Direction consistency + a real (non-degenerate) stop -- part 2/4.
    if direction == "long":
        if not (stop < entry < target):
            raise Refused(f"long setup requires stop < entry < target; got stop={stop}, "
                          f"entry={entry}, target={target}")
        risk = entry - stop
        reward = target - entry
    else:
        if not (target < entry < stop):
            raise Refused(f"short setup requires target < entry < stop; got target={target}, "
                          f"entry={entry}, stop={stop}")
        risk = stop - entry
        reward = entry - target
    if risk <= 0:
        raise Refused("degenerate stop: risk distance is zero; a setup with no real stop is rejected")

    rr = reward / risk
    if rr < rules["min_reward_to_risk"] - 1e-9:
        raise Refused(f"reward:risk {rr:.3f} < the frozen floor {rules['min_reward_to_risk']}. "
                      "A setup without >=2:1 asymmetry is rejected before it can reach the ledger.")

    # Risk sizing -- part 3.
    acct_risk_pct = float(raw.get("account_risk_pct", rules["max_account_risk_pct"]))
    if acct_risk_pct <= 0 or acct_risk_pct > rules["max_account_risk_pct"] + 1e-9:
        raise Refused(f"account_risk_pct {acct_risk_pct} must be in (0, {rules['max_account_risk_pct']}]")
    account = float(spec.get("notional_account_usd", 100000.0))
    size_units = (acct_risk_pct / 100.0) * account / risk  # notional units; account is nominal

    # Discipline -- part 4.
    hz = int(raw.get("horizon_hours", 0))
    if not (rules["horizon_hours_min"] <= hz <= rules["horizon_hours_max"]):
        raise Refused(f"horizon_hours {hz} outside frozen bounds "
                      f"[{rules['horizon_hours_min']}, {rules['horizon_hours_max']}]")
    if n_open >= rules["max_concurrent_open"]:
        raise Refused(f"{n_open} setups already open; the frozen concurrency cap is "
                      f"{rules['max_concurrent_open']}. Discipline = not over-trading; refusing a 6th.")

    thesis = str(raw.get("thesis", "")).strip()
    if len(thesis) < 40:
        raise Refused("thesis too thin: a falsifiable setup must state a one-paragraph reason tied to "
                      "the specific event(s)")
    event_ids = list(raw.get("event_ids", []))
    if not event_ids:
        raise Refused("a setup must cite >=1 world-reader event id (the read it is expressing)")
    confidence = float(raw.get("confidence", 0.0))
    if not (0.0 < confidence <= 1.0):
        raise Refused(f"confidence {confidence} must be in (0, 1]")

    return {
        "instrument": instrument, "asset_class": asset_class, "direction": direction,
        "entry_ref": entry, "stop": stop, "target": target,
        "risk_per_unit": risk, "reward_per_unit": reward, "reward_to_risk": round(rr, 4),
        "account_risk_pct": acct_risk_pct, "size_units": size_units, "horizon_hours": hz,
        "thesis": thesis, "confidence": confidence, "event_ids": event_ids,
        "entry_model": rules["entry_model"],
    }


def freeze_setup(validated: dict, *, proposed_utc: str = None) -> dict:
    """Stamp a validated setup with proposed_utc and its canonical sha256 -- the forward commitment.

    This is the lookahead-proof anchor: the hash is computed over the full spec (INCLUDING the entry
    reference price and the triggering event ids) together with proposed_utc, so the commitment is
    tamper-evident and provably predates any outcome.
    """
    body = dict(validated)
    body["proposed_utc"] = proposed_utc or _now_utc_iso()
    # T56: the coverage of the tape this setup was reasoned over is part of the frozen commitment,
    # not a footnote -- it goes INSIDE the hashed body.
    body["tape_coverage"] = tape_coverage()
    body["setup_sha256"] = canonical_sha256(body)
    body["status"] = "OPEN"
    return body


def tape_coverage() -> dict:
    """The coverage receipt of the most recent `newsdesk read` -- see __main__._tape_receipt (T56).

    A MISSING receipt is itself the disclosure: it means this proposal/abstention was made without a
    preceding read of the tape, which the ledger should say out loud rather than leave inferable.
    """
    from .__main__ import RECEIPT_PATH
    if not RECEIPT_PATH.exists():
        return {"receipt": "MISSING", "note": "no `newsdesk read` receipt on disk; tape unread or pre-T56"}
    try:
        rec = json.loads(RECEIPT_PATH.read_text())
    except (ValueError, OSError) as exc:
        return {"receipt": "UNREADABLE", "note": str(exc)}
    rec["receipt"] = "OK"
    rec.pop("shown_counts", None)
    rec.pop("feed_counts_raw_prededupe", None)
    # A receipt from an old read is a STALE tape, which is a different (and worse) claim than a fresh
    # one. State the age rather than leaving it inferable from pulled_utc -- same lesson as T52.
    try:
        pulled = dt.datetime.fromisoformat(rec["pulled_utc"])
        age = (dt.datetime.now(dt.timezone.utc) - pulled).total_seconds() / 3600.0
        rec["receipt_age_h"] = round(age, 2)
        if age > 3.0:
            rec["receipt"] = "STALE"
    except (KeyError, ValueError, TypeError):
        rec["receipt_age_h"] = None
    return rec


def no_trade_record(reason: str, *, event_stream_id: str = None) -> dict:
    """The disciplined abstention. Logged as an observation of behaviour (not trading is the skill)."""
    return {"kind": "no_trade", "proposed_utc": _now_utc_iso(),
            "reason": reason, "event_stream_id": event_stream_id,
            "tape_coverage": tape_coverage()}
