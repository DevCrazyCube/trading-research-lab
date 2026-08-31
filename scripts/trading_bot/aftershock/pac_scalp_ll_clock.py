#!/usr/bin/env python3
"""Causal decision-clock helpers shared by entry, exit and calibration tests."""
from __future__ import annotations

from collections.abc import Callable, Iterable

from .execution import RefusedExecution


def decision_after_evidence(clock: Callable[[], int], evidence_receipts: Iterable[int]) -> int:
    receipts = tuple(evidence_receipts)
    if not receipts or any(type(value) is not int or value < 0 for value in receipts):
        raise RefusedExecution("decision requires exact evidence receipt clocks")
    decision = clock()
    if type(decision) is not int or decision < max(receipts):
        raise RefusedExecution("decision clock predates evidence used by the decision")
    return decision


def landing_target(*, decision_unix_nanos: int, calibrated_p90_nanos: int) -> int:
    if (type(decision_unix_nanos) is not int or decision_unix_nanos < 0
            or type(calibrated_p90_nanos) is not int or calibrated_p90_nanos <= 0):
        raise RefusedExecution("landing target inputs are invalid")
    return decision_unix_nanos + calibrated_p90_nanos
