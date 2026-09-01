#!/usr/bin/env python3
"""BUNDLE_MOMENTUM_V1 definition and exact first-six entry predicate."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import pathlib

from ..arm import Arm, closure_sha256

K_BUYS = 6
CLUMP_NS = 1_000_000_000
CONCENTRATION_NUM = 95
CONCENTRATION_DEN = 100
SIZE_SOL = 0.5
LATENCY_S = 0.9
ENTRY_BOUNDARY_TIMEOUT_S = 60
EXIT_BOUNDARY_TIMEOUT_S = 60
DEAD_SILENCE_S = 600
PREREG = pathlib.Path(__file__).with_name("BUNDLE_MOMENTUM_PREREGISTRATION.md")
SPEC = {"K_BUYS": K_BUYS, "CLUMP_NS": CLUMP_NS, "CONCENTRATION_NUM": CONCENTRATION_NUM,
        "CONCENTRATION_DEN": CONCENTRATION_DEN, "SIZE_SOL": SIZE_SOL,
        "LATENCY_S": LATENCY_S, "ENTRY_BOUNDARY_TIMEOUT_S": ENTRY_BOUNDARY_TIMEOUT_S,
        "EXIT_BOUNDARY_TIMEOUT_S": EXIT_BOUNDARY_TIMEOUT_S, "DEAD_SILENCE_S": DEAD_SILENCE_S,
        "target_n": 120, "extended_cap": 240}


def _canonical_spec() -> str:
    return repr(sorted(SPEC.items()))


def amount(row: dict) -> Decimal:
    try:
        value = Decimal(row["token_amount"])
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise ValueError("bundle tape token amount is invalid") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("bundle tape token amount must be positive")
    return value


def first_six_signal(rows: list[dict]) -> dict | None:
    ordered = sorted(rows, key=lambda r: (r["received_unix_nanos"], r["sequence"]))
    buys = [row for row in ordered if row.get("tx_type") == "buy"]
    if len(buys) < K_BUYS:
        return None
    sixth = buys[K_BUYS - 1]
    first = buys[0]
    if sixth["received_unix_nanos"] - first["received_unix_nanos"] > CLUMP_NS:
        return None
    held: dict[str, Decimal] = defaultdict(Decimal)
    for row in ordered:
        if (row["received_unix_nanos"], row["sequence"]) > (
                sixth["received_unix_nanos"], sixth["sequence"]):
            break
        if row.get("tx_type") not in {"buy", "sell"}:
            continue
        trader = row.get("trader")
        if not isinstance(trader, str) or not trader:
            return None
        qty = amount(row)
        held[trader] += qty if row.get("tx_type") == "buy" else -qty
    positive = [value for value in held.values() if value > 0]
    total = sum(positive, Decimal(0))
    if len(positive) < 2 or total <= 0:
        return None
    top = max(positive)
    if top * CONCENTRATION_DEN >= total * CONCENTRATION_NUM:
        return None
    return {"decision_unix_nanos": sixth["received_unix_nanos"],
            "decision_sequence": sixth["sequence"], "clump_ns": sixth["received_unix_nanos"]
            - first["received_unix_nanos"], "top_share_bps": int(top * 10_000 / total),
            "evidence_record_sha256": sixth["record_sha256"]}


class BundleMomentum(Arm):
    instrument = "BUNDLE_MOMENTUM_V1"
    fill_basis = "causal_cp"
    service_kind = "trade_tape"
    requires_trade_data = True
    target_n = 120
    extended_cap = 240

    def code_sha256(self):
        arena = pathlib.Path(__file__).resolve().parents[1]
        return closure_sha256([pathlib.Path(__file__)] + [arena / name for name in (
            "arm.py", "bundle_runtime.py", "chainledger.py", "exit_engine.py", "fill.py",
            "manifest.py", "runtime.py", "scorer.py")]
            + [arena.parent / "ws_data.py"])

    def prereg_sha256(self):
        return hashlib.sha256(PREREG.read_bytes()).hexdigest()

    def spec_sha256(self):
        return hashlib.sha256(_canonical_spec().encode()).hexdigest()

    def candidates(self, feed):
        return []

    def entry_ok(self, candidate, history):
        return first_six_signal(history + [candidate]) is not None

    def final_verdict(self, decision, rows, all_rows):
        if decision.get("verdict") == "PASS":
            return {**decision, "verdict": "PASS_PENDING_SENSITIVITY",
                    "reason": "positive primary CI; preregistered latency/clump replay still required"}
        return decision


ARM = BundleMomentum()


def _selftest() -> None:
    rows = []
    for index in range(6):
        rows.append({"received_unix_nanos": 1_000_000_000 + index * 100_000_000,
                     "sequence": index + 1, "tx_type": "buy",
                     "trader": "a" if index < 3 else "b", "token_amount": "10",
                     "record_sha256": f"{index + 1:064x}"})
    signal = first_six_signal(rows)
    assert signal and signal["top_share_bps"] == 5000
    concentrated = [dict(row, trader="a") for row in rows]
    assert first_six_signal(concentrated) is None
    stale = [dict(row) for row in rows]; stale[-1]["received_unix_nanos"] += CLUMP_NS
    assert first_six_signal(stale) is None
    print("BUNDLE_MOMENTUM_V1 selftest: PASS")


if __name__ == "__main__":
    _selftest()
