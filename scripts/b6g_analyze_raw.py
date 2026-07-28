#!/usr/bin/env python3
"""Offline audit of length-framed raw output from b6g_logs_probe.py."""
import argparse
import base64
import json
from collections import Counter

from b6g_logs_probe import TRADE_EVENT, instruction_names


def frames(path):
    with open(path, "rb") as handle:
        while True:
            size_bytes = handle.read(8)
            if not size_bytes:
                return
            if len(size_bytes) != 8:
                raise ValueError("torn length prefix")
            size = int.from_bytes(size_bytes, "little")
            payload = handle.read(size)
            if len(payload) != size:
                raise ValueError("torn payload")
            yield payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    successful_without_event = Counter()
    malformed = Counter()
    notifications = 0
    succeeded = notifications_with_trade_event = trade_events = 0
    for payload in frames(args.path):
        message = json.loads(payload)
        if message.get("method") != "logsNotification":
            continue
        notifications += 1
        value = message["params"]["result"]["value"]
        logs = value.get("logs") or []
        has_event = False
        event_count = 0
        for line in logs:
            if not line.startswith("Program data: "):
                continue
            for encoded in line[14:].split():
                try:
                    raw = base64.b64decode(encoded, validate=True)
                except Exception as exc:  # noqa: BLE001
                    malformed[(type(exc).__name__, len(encoded), encoded[:80])] += 1
                    continue
                if raw.startswith(TRADE_EVENT):
                    has_event = True
                    event_count += 1
        if value.get("err") is None:
            succeeded += 1
            notifications_with_trade_event += has_event
        trade_events += event_count
        if value.get("err") is None and not has_event:
            names = tuple(instruction_names(logs)) or ("<no instruction log>",)
            successful_without_event[names] += 1
    result = {
        "notifications": notifications,
        "succeeded": succeeded,
        "trade_events": trade_events,
        "notifications_with_trade_event": notifications_with_trade_event,
        "successful_without_trade_event_count": succeeded - notifications_with_trade_event,
        "successful_without_trade_event": [
            {"count": count, "instructions": names}
            for names, count in successful_without_event.most_common()
        ],
        "malformed_program_data": [
            {"count": count, "error": key[0], "encoded_length": key[1], "prefix": key[2]}
            for key, count in malformed.most_common()
        ],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
