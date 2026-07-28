#!/usr/bin/env python3
"""Reproducible free logsSubscribe probe with raw-frame preservation."""
import argparse
import base64
import json
import os
import socket
import sys
import tempfile
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from wsmin import WebSocket, WSError  # noqa: E402

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TRADE_EVENT = bytes.fromhex("bddb7fd34ee661ee")


def instruction_names(logs):
    prefix = "Program log: Instruction: "
    return [line[len(prefix):] for line in logs if line.startswith(prefix)]


def count_trade_events(logs):
    count = 0
    invalid_fields = 0
    multi_field_lines = 0
    for line in logs:
        if not line.startswith("Program data: "):
            continue
        fields = line[14:].split()
        multi_field_lines += len(fields) > 1
        for encoded in fields:
            try:
                raw = base64.b64decode(encoded, validate=True)
            except Exception:  # noqa: BLE001
                invalid_fields += 1
                continue
            if raw.startswith(TRADE_EVENT):
                count += 1
    return count, invalid_fields, multi_field_lines


def probe(args):
    ws = WebSocket(args.url, timeout=args.silence_timeout)
    request = {
        "jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
        "params": [{"mentions": [PUMP]}, {"commitment": args.commitment}],
    }
    ws.send_text(json.dumps(request, separators=(",", ":")))
    raw_handle = open(args.raw_output, "ab") if args.raw_output else None
    started = time.monotonic()
    frames = bytes_received = notifications = succeeded = failed = 0
    trade_events = notifications_with_trade_event = invalid_data_fields = 0
    multi_field_data_lines = explicit_truncation = 0
    signatures = set()
    slots = set()
    instructions = Counter()
    error = None
    try:
        while time.monotonic() - started < args.duration:
            try:
                kind, payload, close_code = ws.recv()
            except socket.timeout:
                error = f"silence timeout after {args.silence_timeout}s"
                break
            if kind == "close":
                error = f"server close {close_code}"
                break
            frames += 1
            bytes_received += len(payload)
            if raw_handle:
                raw_handle.write(len(payload).to_bytes(8, "little") + payload)
            try:
                message = json.loads(payload)
            except Exception:  # noqa: BLE001
                continue
            if "error" in message:
                error = repr(message["error"])
                break
            if message.get("method") != "logsNotification":
                continue
            notifications += 1
            result = message["params"]["result"]
            value = result["value"]
            logs = value.get("logs") or []
            signature = value.get("signature")
            if signature:
                signatures.add(signature)
            slots.add(result["context"]["slot"])
            if value.get("err") is None:
                succeeded += 1
            else:
                failed += 1
            events, invalid_fields, multi_fields = count_trade_events(logs)
            trade_events += events
            notifications_with_trade_event += events > 0
            invalid_data_fields += invalid_fields
            multi_field_data_lines += multi_fields
            instructions.update(instruction_names(logs))
            if any("truncat" in line.lower() for line in logs):
                explicit_truncation += 1
    except (WSError, OSError) as exc:
        error = repr(exc)
    finally:
        if raw_handle:
            raw_handle.flush()
            os.fsync(raw_handle.fileno())
            raw_handle.close()
        ws.close()
    elapsed = time.monotonic() - started
    summary = {
        "commitment": args.commitment, "requested_duration_s": args.duration,
        "elapsed_s": elapsed, "frames": frames, "notifications": notifications,
        "unique_signatures": len(signatures), "unique_slots": len(slots),
        "succeeded": succeeded, "failed": failed, "trade_events": trade_events,
        "notifications_with_trade_event": notifications_with_trade_event,
        "successful_without_trade_event": succeeded - notifications_with_trade_event,
        "invalid_program_data_fields": invalid_data_fields,
        "multi_field_program_data_lines": multi_field_data_lines,
        "explicit_truncation_notifications": explicit_truncation,
        "bytes_received": bytes_received, "notifications_per_s": notifications / elapsed,
        "bytes_per_s": bytes_received / elapsed, "instruction_logs": instructions,
        "error": error,
    }
    rendered = json.dumps(summary, indent=2, default=dict)
    if args.summary_output:
        destination = os.path.abspath(args.summary_output)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=os.path.dirname(destination), delete=False) as handle:
            handle.write(rendered + "\n")
            temporary = handle.name
        os.replace(temporary, destination)
    print(rendered)
    return 1 if error else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--commitment", choices=("processed", "confirmed", "finalized"),
                        default="confirmed")
    parser.add_argument("--url", default="wss://api.mainnet-beta.solana.com")
    parser.add_argument("--silence-timeout", type=float, default=15)
    parser.add_argument("--raw-output")
    parser.add_argument("--summary-output")
    raise SystemExit(probe(parser.parse_args()))
