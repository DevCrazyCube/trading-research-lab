#!/usr/bin/env python3
"""Continuous intra-trade mark logger for the PAC portfolio scalper (the measurement instrument).

The existing ledgers record only entry + terminal exit, so the ONE parameter that decides whether the
convex scalp is net-positive -- the fraction of atomic/gradual rugs a proactive stop actually catches
BEFORE the mint goes unexitable, and how often proto-runners dip through the stop before running -- is
unmeasurable from them.  This logs every observed full-position net-exit quote for every open slot on
every refresh, durably and append-only, so the hinge can be measured FORWARD from honest data instead
of assumed by lookahead.  It never prices anything itself; it records the quotes the runner already
computes.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time


ROOT = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_PATH = ROOT / "research" / "data" / "aftershock" / "pac_scalp" / "marks.jsonl"
SCHEMA = 1


def _append(path: pathlib.Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError(f"short mark append {written}/{len(payload)}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def record(*, entry_id: str, mint: str, observed_unix_nanos: int, context_slot: int,
           entry_all_in_lamports: int, net_exit_lamports: int | None, real_quote_lamports: int | None,
           peak_net_exit_lamports: int, venue: str, priceable: bool,
           path: pathlib.Path = DEFAULT_PATH) -> None:
    """Append one intra-trade mark.  net_exit/real_quote are None when the position is unpriceable at
    this observation (candidate rug / no bid) -- exactly the signal the hinge analysis needs."""
    gain_bps = None
    if isinstance(net_exit_lamports, int) and entry_all_in_lamports:
        gain_bps = (net_exit_lamports - entry_all_in_lamports) * 10_000 // entry_all_in_lamports
    row = {
        "schema": SCHEMA, "entry_id": entry_id, "mint": mint,
        "observed_unix_nanos": observed_unix_nanos, "context_slot": context_slot,
        "entry_all_in_lamports": entry_all_in_lamports,
        "net_exit_lamports": net_exit_lamports, "real_quote_lamports": real_quote_lamports,
        "peak_net_exit_lamports": peak_net_exit_lamports, "gain_bps": gain_bps,
        "venue": venue, "priceable": bool(priceable),
    }
    row["mark_sha256"] = hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    _append(pathlib.Path(path), row)
