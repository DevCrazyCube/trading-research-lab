#!/usr/bin/env python3
"""Mark-to-market resolver -- the forward-only, lookahead-proof half (mirror of basket_forward marks).

For each frozen OPEN setup, this walks the realised free-price path that occurred STRICTLY AFTER the
freeze, decides whether the stop, the target, or the horizon was reached first, and records the
realised R-multiple. Two things make it honest:

  1. FORWARD-ONLY ASSERTION. `_assert_forward` discards every bar at or before `proposed_utc` and
     refuses if a resolution would otherwise rest on a bar the agent could have seen at freeze. A
     setup scored on a bar it saw at freeze is the exact lookahead this instrument exists to defeat.
  2. ADVERSE TIE-BREAK. If a single bar's range spans BOTH the stop and the target, the STOP is
     assumed hit first (the pessimistic, B22B-style adverse convention) -- never the favourable one.

Alongside the real R it computes a RANDOM-DIRECTION NULL R on the SAME path (same instrument, risk
distance, R:R, horizon; direction chosen by a deterministic coin seeded from the setup's own sha256),
so the agent's read can be benchmarked against same-instrument random entry.
"""

from __future__ import annotations

import datetime as dt

from . import Refused
from .prices import path_for


def _epoch(iso_utc: str) -> int:
    s = iso_utc.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


def _assert_forward(bars: list, freeze_epoch: int, instrument: str) -> list:
    """Keep only bars strictly after the freeze; refuse if any earlier bar sneaks through."""
    fwd = [b for b in bars if b[0] > freeze_epoch]
    for b in bars:
        if b[0] <= freeze_epoch and b in fwd:
            raise Refused(f"LOOKAHEAD in {instrument}: a bar at/before the freeze reached resolution")
    return fwd


def _levels(direction: str, entry: float, stop: float, target: float):
    return (stop, target)


def _walk(direction: str, entry: float, stop: float, target: float, risk: float,
          bars: list, tie_break: str):
    """Return (realized_R, reason, exit_price, exit_ts) walking bars in time order.

    long : stop hit if low<=stop; target hit if high>=target.
    short: stop hit if high>=stop; target hit if low<=target.
    tie (both in one bar): adverse -> stop.
    """
    for (ts, hi, lo, cl) in bars:
        if direction == "long":
            hit_stop = lo <= stop
            hit_tgt = hi >= target
        else:
            hit_stop = hi >= stop
            hit_tgt = lo <= target
        if hit_stop and hit_tgt:
            # Frozen adverse convention: one bar spanning both levels resolves to the STOP.
            return (-1.0, "stop_adverse_tie", stop, ts)
        if hit_stop:
            return (-1.0, "stop", stop, ts)
        if hit_tgt:
            r = (target - entry) / risk if direction == "long" else (entry - target) / risk
            return (r, "target", target, ts)
    # Neither touched within the supplied (horizon-bounded) path -> mark at the last close.
    if not bars:
        return (None, "no_forward_bars", None, None)
    ts, _, _, cl = bars[-1]
    r = (cl - entry) / risk if direction == "long" else (entry - cl) / risk
    return (r, "horizon_mark", cl, ts)


def resolve_setup(setup: dict, spec: dict, *, now_utc: str = None) -> dict:
    """Resolve one OPEN setup against its realised forward path. Returns a resolution record.

    A setup stays OPEN (returns status 'PENDING') until its horizon has fully elapsed OR a stop/target
    is touched -- a phantom mark is never fabricated before the path exists.
    """
    now = now_utc or dt.datetime.now(dt.timezone.utc).isoformat()
    freeze_iso = setup["proposed_utc"]
    freeze_epoch = _epoch(freeze_iso)
    horizon_end_epoch = freeze_epoch + setup["horizon_hours"] * 3600
    horizon_end_iso = dt.datetime.fromtimestamp(horizon_end_epoch, dt.timezone.utc).isoformat()
    now_epoch = _epoch(now)

    # Fetch the path from just before freeze up to min(now, horizon_end); the assertion trims to >freeze.
    until_iso = horizon_end_iso if now_epoch >= horizon_end_epoch else now
    path = path_for(setup, freeze_iso, until_iso, spec)
    bars = _assert_forward(path["bars"], freeze_epoch, setup["instrument"])

    direction, entry = setup["direction"], setup["entry_ref"]
    stop, target, risk = setup["stop"], setup["target"], setup["risk_per_unit"]
    tie = spec["rules"]["adverse_tie_break"]

    realized_r, reason, exit_px, exit_ts = _walk(direction, entry, stop, target, risk, bars, tie)

    # Still open? Only settle a horizon_mark once the horizon has actually elapsed.
    horizon_elapsed = now_epoch >= horizon_end_epoch
    if reason in ("horizon_mark", "no_forward_bars") and not horizon_elapsed:
        return {"kind": "resolution", "status": "PENDING", "setup_sha256": setup["setup_sha256"],
                "instrument": setup["instrument"], "proposed_utc": freeze_iso,
                "horizon_end_utc": horizon_end_iso, "n_forward_bars": len(bars),
                "note": "horizon not yet elapsed and no stop/target touched; leaving OPEN"}

    # Random-direction null on the SAME path: same distances, flipped-by-coin direction.
    seed = int(setup["setup_sha256"][:8], 16)
    null_dir = "long" if seed % 2 == 0 else "short"
    if null_dir == "long":
        null_stop, null_target = entry - risk, entry + setup["reward_per_unit"]
    else:
        null_stop, null_target = entry + risk, entry - setup["reward_per_unit"]
    null_r, null_reason, _, _ = _walk(null_dir, entry, null_stop, null_target, risk, bars, tie)

    return {
        "kind": "resolution", "status": "RESOLVED",
        "setup_sha256": setup["setup_sha256"], "instrument": setup["instrument"],
        "asset_class": setup["asset_class"], "direction": direction,
        "proposed_utc": freeze_iso, "resolved_utc": now, "horizon_end_utc": horizon_end_iso,
        "entry_ref": entry, "stop": stop, "target": target, "reward_to_risk": setup["reward_to_risk"],
        "realized_r": round(realized_r, 4) if realized_r is not None else None,
        "resolution_reason": reason, "exit_price": exit_px, "exit_ts_epoch": exit_ts,
        "null_direction": null_dir, "null_realized_r": round(null_r, 4) if null_r is not None else None,
        "null_reason": null_reason,
        "n_forward_bars": len(bars), "price_source": path["source"],
        "price_granularity": path["granularity"], "price_interval": path["interval"],
        "NOT_EVIDENCE_YET": ("one hypothetical R-multiple, no order placed; the honest prior is that "
                             "the news was already priced in"),
    }
