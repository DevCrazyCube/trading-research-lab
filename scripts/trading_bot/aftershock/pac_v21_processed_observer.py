#!/usr/bin/env python3
"""First-status observation recorder for PAC V2.1 processed-inclusion calibration.

There is no RPC URL, signer, sender, wallet, or CLI in this module. A campaign sender must inject one
authenticated request function and persist either the returned observation or the complete refusal polls.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from . import pac_v2_calibration as base
from . import pac_v21_calibration as calibration


class ProcessedObservationRefused(RuntimeError):
    def __init__(self, reason: str, polls: tuple[dict, ...]):
        super().__init__(reason)
        self.polls = polls


class ProcessedTransportFailure(ProcessedObservationRefused):
    """A status request produced no complete RPC response; prior completed polls remain attached."""


@dataclass(frozen=True)
class ProcessedObservation:
    slot: int
    confirmation_status: str
    response_received_unix_nanos: int
    response_received_monotonic_nanos: int
    polls: tuple[dict, ...]


def observe(signature: str, *, rpc: Callable[[dict], dict],
            decision_monotonic_nanos: int,
            clock: Callable[[], int] = time.time_ns,
            monotonic: Callable[[], int] = time.monotonic_ns,
            sleep: Callable[[float], None] = time.sleep) -> ProcessedObservation:
    """Record every successful status response until the first non-null processed-or-stronger status.

    Transport-level request failures are propagated to the campaign sender, which must persist its
    attempt journal. RPC/program/schema failures raise ``ProcessedObservationRefused`` with all prior
    complete polls attached; none can silently become a latency sample.
    """
    try:
        base._b58decode("transaction signature", signature, exact_length=64)
    except base.CalibrationRefused as exc:
        raise ProcessedObservationRefused(str(exc), ()) from exc
    if type(decision_monotonic_nanos) is not int or decision_monotonic_nanos <= 0 or not callable(rpc):
        raise ProcessedObservationRefused("processed observer input is invalid", ())
    deadline = decision_monotonic_nanos + calibration.PROCESSED_DEADLINE_NANOS
    polls: list[dict] = []
    while monotonic() < deadline:
        poll_index = len(polls)
        request = {"jsonrpc": "2.0", "id": poll_index + 1,
                   "method": "getSignatureStatuses",
                   "params": [[signature], {"searchTransactionHistory": True}]}
        start_wall, start_mono = clock(), monotonic()
        try:
            response = rpc(request)
        except Exception as exc:
            raise ProcessedTransportFailure(
                f"processed status transport failed: {type(exc).__name__}", tuple(polls)) from exc
        end_wall, end_mono = clock(), monotonic()
        body = {
            "request_started_unix_nanos": start_wall,
            "response_received_unix_nanos": end_wall,
            "request_started_monotonic_nanos": start_mono,
            "response_received_monotonic_nanos": end_mono,
            "request_json": request,
            "response_json": response,
            "raw_response_sha256": calibration._sha(response),
        }
        row = {**body, "poll_id": calibration._sha(body)}
        polls.append(row)
        if (not isinstance(response, dict)
                or set(response) != {"jsonrpc", "id", "result"}
                or response.get("jsonrpc") != "2.0"
                or response.get("id") != poll_index + 1
                or not isinstance(response.get("result"), dict)
                or set(response["result"]) != {"context", "value"}
                or not isinstance(response["result"].get("context"), dict)
                or type(response["result"]["context"].get("slot")) is not int
                or response["result"]["context"]["slot"] <= 0
                or not isinstance(response["result"].get("value"), list)
                or len(response["result"]["value"]) != 1):
            raise ProcessedObservationRefused(
                "processed status JSON-RPC envelope/context is invalid", tuple(polls))
        value = response["result"]["value"]
        status = value[0]
        if status is None:
            sleep(calibration.POLL_INTERVAL_NANOS / 1_000_000_000)
            continue
        confirmation = status.get("confirmationStatus") if isinstance(status, dict) else None
        slot = status.get("slot") if isinstance(status, dict) else None
        if (not isinstance(status, dict) or status.get("err") is not None
                or type(slot) is not int or slot <= 0
                or confirmation not in {"processed", "confirmed", "finalized"}):
            raise ProcessedObservationRefused(
                "first non-null transaction status is not a successful processed observation",
                tuple(polls))
        if end_mono > deadline:
            raise ProcessedObservationRefused(
                "processed status arrived after the frozen deadline", tuple(polls))
        return ProcessedObservation(
            slot=slot, confirmation_status=confirmation,
            response_received_unix_nanos=end_wall,
            response_received_monotonic_nanos=end_mono,
            polls=tuple(polls),
        )
    raise ProcessedObservationRefused(
        "no processed status before the frozen deadline", tuple(polls))
