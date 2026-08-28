#!/usr/bin/env python3
"""The raw per-mint trade TAPE — AFTERSHOCK's native substrate. PAPER, read-only consumers.

The central broker (memestream.pumpportal_broker) writes one JSONL line per pump.fun trade to
`research/data/memebot_cache/tape/{mint}.jsonl`, and one line per new-token create to `_creates.jsonl`.
Every line carries the exact post-trade bonding-curve reserves and the taker wallet — the fields the
detector/resolver/ECR need and the candle cache does NOT carry. This module is the schema + a bounded
writer + the readers.

Tape line schema for new causal observations (all present, never fabricated):
    {ts (epoch s display only), received_unix_nanos (local receive clock), observation_source, mint, trader,
     side ("buy"|"sell"), sol_amount, token_amount, v_sol, v_tokens, pool, sig}
Legacy lines without ``received_unix_nanos`` remain readable by legacy diagnostics but are INELIGIBLE for
the causal execution engine; consumers must refuse rather than derive a receive clock from ``ts``.
Create line schema:
    {ts, mint, symbol, pool}
"""
from __future__ import annotations

import json
import pathlib
import time

_ROOT = pathlib.Path(__file__).resolve().parents[3]
TAPE_DIR = _ROOT / "research" / "data" / "memebot_cache" / "tape"
CREATES_PATH = TAPE_DIR / "_creates.jsonl"

_MAX_TAPE_LINES = 4000      # per mint; a pump.fun coin's whole life fits far under this
_MAX_CREATES_LINES = 20000
TAPE_FIELDS = ("ts", "received_unix_nanos", "observation_source", "mint", "trader", "side", "sol_amount",
               "token_amount", "v_sol", "v_tokens", "pool", "sig")


def _mint_path(mint: str) -> pathlib.Path:
    # mints are base58 (filesystem-safe); guard against path separators defensively
    safe = "".join(ch for ch in str(mint) if ch.isalnum())
    return TAPE_DIR / f"{safe}.jsonl"


def append_trade(line: dict) -> None:
    """Append one tape line for its mint (called by the broker; atomic short append)."""
    mint = line.get("mint")
    if not mint:
        return
    TAPE_DIR.mkdir(parents=True, exist_ok=True)
    rec = {k: line.get(k) for k in TAPE_FIELDS}
    with _mint_path(mint).open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def append_create(rec: dict) -> None:
    TAPE_DIR.mkdir(parents=True, exist_ok=True)
    with CREATES_PATH.open("a") as fh:
        fh.write(json.dumps({k: rec.get(k) for k in ("ts", "mint", "symbol", "pool")}) + "\n")


def read_tape(mint: str, since_ts: float | None = None) -> list:
    """All tape lines for a mint (optionally only ts >= since_ts), in file (time) order."""
    p = _mint_path(mint)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text().splitlines():
        if not ln.strip():
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if since_ts is not None and (rec.get("ts") or 0) < since_ts:
            continue
        out.append(rec)
    return out


def read_creates(since_ts: float | None = None) -> list:
    if not CREATES_PATH.exists():
        return []
    out = []
    for ln in CREATES_PATH.read_text().splitlines():
        if not ln.strip():
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if since_ts is not None and (rec.get("ts") or 0) < since_ts:
            continue
        out.append(rec)
    return out


def trim_mint(mint: str) -> None:
    """Bound one mint's tape file to the last _MAX_TAPE_LINES lines."""
    p = _mint_path(mint)
    if not p.exists():
        return
    lines = p.read_text().splitlines()
    if len(lines) > _MAX_TAPE_LINES:
        p.write_text("\n".join(lines[-_MAX_TAPE_LINES:]) + "\n")


def trim_creates() -> None:
    """Bound _creates.jsonl to the last _MAX_CREATES_LINES lines (review #10: it grew unbounded)."""
    if not CREATES_PATH.exists():
        return
    lines = CREATES_PATH.read_text().splitlines()
    if len(lines) > _MAX_CREATES_LINES:
        CREATES_PATH.write_text("\n".join(lines[-_MAX_CREATES_LINES:]) + "\n")


def reap(max_age_s: float = 3600.0) -> int:
    """Delete tape files whose last write is older than max_age_s (dead coins). Returns count removed."""
    if not TAPE_DIR.exists():
        return 0
    now = time.time()
    removed = 0
    for p in TAPE_DIR.glob("*.jsonl"):
        if p.name.startswith("_"):
            continue
        try:
            if now - p.stat().st_mtime > max_age_s:
                p.unlink()
                removed += 1
        except OSError:
            pass
    return removed
