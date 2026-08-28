#!/usr/bin/env python3
"""Negative controls for the PAC point-in-time SOL/USD recorder."""
from __future__ import annotations

import json
import pathlib
import tempfile
from unittest import mock

from .execution import RefusedExecution
from . import solusd_recorder as recorder

T0 = 2_100_000_000_000_000_000


class _Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def _raises(fn):
    try:
        fn(); return False
    except RefusedExecution:
        return True


def _check(name, value):
    print(f"  [{'ok' if value else 'FAIL'}] {name}")
    return bool(value)


def main() -> int:
    ok = True
    provider = "2036-07-18T13:20:00Z"  # exactly T0 seconds in UTC
    body = json.dumps({"price": "200.00", "time": provider, "trade_id": 1}).encode()
    with tempfile.TemporaryDirectory(prefix="pac_solusd_") as directory:
        path = pathlib.Path(directory) / "quotes.jsonl"
        with mock.patch.object(recorder.urllib.request, "urlopen", return_value=_Response(body)), \
             mock.patch.object(recorder.time, "time_ns", side_effect=[T0 - 1_000_000, T0]):
            record = recorder.fetch_once(output=path)
        observation = recorder.latest_observation(decision_unix_nanos=T0 + 1, output=path)
        ok &= _check("Decimal USD price and local receive clock survive raw-hash reconciliation",
                     observation.value_str == "200.00" and observation.observed_unix_nanos == T0)
        future = dict(record); future["received_unix_nanos"] = T0 + 100
        with path.open("a") as handle:
            handle.write(json.dumps(future) + "\n")
        asof = recorder.latest_observation(decision_unix_nanos=T0 + 1, output=path)
        ok &= _check("reverse hot-path scan skips a later receipt without future leakage",
                     asof.observed_unix_nanos == T0)
        ok &= _check("future decision cannot backfill a stale quote",
                     _raises(lambda: recorder.latest_observation(
                         decision_unix_nanos=T0 + 100 + recorder.MAX_LOCAL_AGE_NANOS + 1,
                         output=path)))
        tampered = json.loads(path.read_text().splitlines()[0])
        tampered["price"] = "999.00"
        path.write_text(json.dumps(tampered) + "\n")
        ok &= _check("tampered derived price refuses against raw response hash/source",
                     _raises(lambda: recorder.latest_observation(decision_unix_nanos=T0 + 1, output=path)))
    ok &= _check("float decision clock refuses",
                 _raises(lambda: recorder.latest_observation(decision_unix_nanos=1.0)))
    print("\nPAC SOLUSD RECORDER SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
