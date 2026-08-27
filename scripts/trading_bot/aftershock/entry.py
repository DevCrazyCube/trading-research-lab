#!/usr/bin/env python3
"""AFTERSHOCK entry freezing — turns a detector FIRE into a frozen, lookahead-proof paper entry.

The record is a SUPERSET: all memebot-compatible fields (so ledger/dashboard/verify read it unchanged)
PLUS the AFTERSHOCK context — crucially `entry_reserves`, the exact curve state at the fire instant,
frozen BEFORE the outcome so the ECR engine prices the stressed exit against it later. The whole record
(including the AFTERSHOCK fields) is fingerprinted with memebot.frozen.canonical_sha256, so the frozen
commitment covers the reserves too. PAPER only; append via memebot.ledger.append_entry.
"""
from __future__ import annotations

import datetime as dt

from .frozen import canonical_sha256
from scripts.trading_bot.memebot import ledger as _ledger

SOL_USD = 200.0


def _price_usd(v_sol: float, v_tokens: float) -> float:
    return (float(v_sol) / float(v_tokens)) * SOL_USD if v_tokens else 0.0


def build_entry(fire: dict, spec: dict) -> dict:
    """Build the frozen superset entry record from a detector fire dict (control flag carried on it)."""
    line = fire["entry_line"]
    v_sol, v_tokens, pool = line["v_sol"], line["v_tokens"], line.get("pool", "pump")
    entry_price = _price_usd(v_sol, v_tokens)
    size_sol = float(spec["bankroll_sol"]) * float(spec["position_fraction"])
    q_sol = float(spec["detector"]["q_sol"])
    control = bool(fire.get("control"))
    horizon_min = spec["exit"]["max_hold_slots"] * 0.4 / 60.0

    record = {
        # ---- memebot-compatible shape ----
        "instrument_id": spec["instrument_id"],
        "kind": "entry",
        "control": control,
        "pool_address": fire["mint"],
        "name": line.get("symbol") or fire["mint"][:10],
        "direction": "long",
        "entry_price_usd": entry_price,
        "stop_price_usd": entry_price * (1.0 - float(spec["stop_frac"])),
        "target_price_usd": entry_price * (1.0 + float(spec["target_frac"])),
        "size_sol": round(size_sol, 6),
        "stop_frac": float(spec["stop_frac"]),
        "target_frac": float(spec["target_frac"]),
        "toll_per_side": float(spec["toll_per_side"]),
        "horizon_minutes": round(horizon_min, 2),
        "dead_exit": None,
        "screen_verdict": "CONTROL" if control else "PASS",
        "screen_reasons": ["absorption confirmed" if not control else "shock NOT absorbed (control null)"],
        "feed_snapshot": {"v_sol": v_sol, "v_tokens": v_tokens, "pool": pool},
        "decided_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        # ---- AFTERSHOCK frozen context (part of the fingerprint) ----
        "entry_reserves": {"v_sol": v_sol, "v_tokens": v_tokens, "pool": pool, "ts": line.get("ts")},
        "q_sol": q_sol,
        "position_fraction": float(spec["position_fraction"]),
        "cluster_wallets": fire.get("cluster_wallets"),
        "deployer": fire.get("deployer"),
        "k60_at_fire": fire.get("k60_at_fire"),
        "t_shock": fire.get("t_shock"),
        "sell_sol": fire.get("sell_sol"),
        "r_pre": fire.get("r_pre"),
        "r_at_fire": fire.get("r_at_fire"),
        "coverage_at_fire": fire.get("coverage_at_fire"),
        "t_entry": float(line.get("ts")),
        "conditions": fire.get("conditions"),
    }
    record["setup_sha256"] = canonical_sha256(record)
    return record


def freeze_and_append(fire: dict, spec: dict) -> dict:
    """Build + append the frozen entry to the AFTERSHOCK ledger. Returns the record."""
    record = build_entry(fire, spec)
    _ledger.append_entry(spec, record)
    return record
