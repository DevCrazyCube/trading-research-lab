#!/usr/bin/env python3
"""Hostile controls for the V2.1 first-status observation recorder."""
from __future__ import annotations

from collections import deque

from . import pac_v2_calibration as base
from . import pac_v21_calibration as calibration
from . import pac_v21_processed_observer as observer


CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


class Clock:
    def __init__(self):
        self.wall = 2_000_000_000_000
        self.mono = 1_000_000_000_000

    def wall_now(self):
        self.wall += 1_000_000
        return self.wall

    def mono_now(self):
        self.mono += 1_000_000
        return self.mono

    def sleep(self, seconds: float):
        nanos = int(seconds * 1_000_000_000)
        self.wall += nanos; self.mono += nanos


def response(status):
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"context": {"slot": 1}, "value": [status]}}


def run(responses: list[dict], clock: Clock, *, bind_request_id: bool = True):
    queue = deque(responses)
    def rpc(request: dict) -> dict:
        value = queue.popleft()
        return {**value, "id": request["id"]} if bind_request_id else value
    return observer.observe(
        base._b58encode(bytes(range(64))), rpc=rpc,
        decision_monotonic_nanos=clock.mono,
        clock=clock.wall_now, monotonic=clock.mono_now, sleep=clock.sleep)


def main() -> int:
    clock = Clock()
    status = {"slot": 123, "confirmations": 0, "err": None,
              "confirmationStatus": "processed"}
    observed = run([response(None), response(status)], clock)
    check(observed.slot == 123 and observed.confirmation_status == "processed",
          "first processed status is recorded")
    check(len(observed.polls) == 2
          and observed.polls[0]["response_json"]["result"]["value"] == [None],
          "every earlier null response remains in evidence")
    check(all(row["poll_id"] == calibration._sha(
        {key: value for key, value in row.items() if key != "poll_id"})
              for row in observed.polls),
          "every poll is content-addressed")

    confirmed_clock = Clock()
    confirmed = run([response({**status, "confirmationStatus": "confirmed"})], confirmed_clock)
    check(confirmed.confirmation_status == "confirmed",
          "first stronger-than-processed observation is accepted but not relabelled")

    failed_clock = Clock()
    try:
        run([response({**status, "err": {"InstructionError": [0, "Custom"]}})], failed_clock)
    except observer.ProcessedObservationRefused as exc:
        check(len(exc.polls) == 1, "on-chain error refuses with its terminal poll preserved")
    else:
        raise AssertionError("on-chain error must refuse")

    malformed_clock = Clock()
    try:
        run([{"jsonrpc": "2.0", "id": 1, "result": {"value": []}}], malformed_clock)
    except observer.ProcessedObservationRefused as exc:
        check(len(exc.polls) == 1, "malformed status refuses with raw response preserved")
    else:
        raise AssertionError("malformed status must refuse")

    wrong_id_clock = Clock()
    try:
        run([{"jsonrpc": "2.0", "id": 999,
              "result": {"context": {"slot": 1}, "value": [None]}}],
            wrong_id_clock, bind_request_id=False)
    except observer.ProcessedObservationRefused as exc:
        check(len(exc.polls) == 1,
              "mismatched JSON-RPC id refuses with the response preserved")
    else:
        raise AssertionError("mismatched JSON-RPC id must refuse")

    transport_clock = Clock()
    transport_calls = 0
    def transport(request):
        nonlocal transport_calls
        transport_calls += 1
        if transport_calls == 1:
            return {**response(None), "id": request["id"]}
        raise TimeoutError("synthetic")
    try:
        observer.observe(
            base._b58encode(bytes(range(64))), rpc=transport,
            decision_monotonic_nanos=transport_clock.mono,
            clock=transport_clock.wall_now, monotonic=transport_clock.mono_now,
            sleep=transport_clock.sleep)
    except observer.ProcessedTransportFailure as exc:
        check(len(exc.polls) == 1,
              "transport failure preserves every earlier completed poll")
    else:
        raise AssertionError("transport failure must remain a typed refusal")

    invalid_clock = Clock()
    try:
        observer.observe("not-base58", rpc=lambda _request: response(None),
                         decision_monotonic_nanos=invalid_clock.mono,
                         clock=invalid_clock.wall_now, monotonic=invalid_clock.mono_now,
                         sleep=invalid_clock.sleep)
    except observer.ProcessedObservationRefused as exc:
        check(exc.polls == (), "invalid signature refuses before any RPC observation")
    else:
        raise AssertionError("invalid signature must refuse")

    timeout_clock = Clock()
    timeout_clock.mono = 1_000_000_000_000
    calls = 0
    def never(request):
        nonlocal calls
        calls += 1
        return {**response(None), "id": request["id"]}
    try:
        observer.observe(
            base._b58encode(bytes(range(64))), rpc=never,
            decision_monotonic_nanos=timeout_clock.mono,
            clock=timeout_clock.wall_now, monotonic=timeout_clock.mono_now,
            sleep=timeout_clock.sleep)
    except observer.ProcessedObservationRefused as exc:
        check(calls > 1 and len(exc.polls) == calls,
              "deadline refusal returns every completed null poll")
    else:
        raise AssertionError("processed timeout must refuse")

    print(f"PAC V2.1 PROCESSED OBSERVER SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
