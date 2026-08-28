#!/usr/bin/env python3
"""Read-only point-in-time SOL/USD recorder for AFTERSHOCK PAC.

Source: Coinbase Exchange public ``SOL-USD`` ticker. The response is market data only and requires no
key. Both provider trade time and the local response-receive clock are retained. Consumers size from the
latest causal local receipt and fail closed on stale provider/local time or malformed Decimal price.

Primary documentation (accessed 2026-08-28):
https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import pathlib
import time
import urllib.error
import urllib.request

from .execution import RefusedExecution, SolUsdObservation


ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "research" / "data" / "aftershock" / "solusd_coinbase.jsonl"
URL = "https://api.exchange.coinbase.com/products/SOL-USD/ticker"
SOURCE = "coinbase-exchange:SOL-USD:last-trade"
POLL_SECONDS = 2.0
MAX_LOCAL_AGE_NANOS = 5_000_000_000
MAX_PROVIDER_AGE_AT_RECEIPT_NANOS = 30_000_000_000
MAX_PROVIDER_FUTURE_SKEW_NANOS = 5_000_000_000


def _provider_nanos(value: object) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RefusedExecution("Coinbase ticker time must be an explicit UTC string")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RefusedExecution("Coinbase ticker time is malformed") from exc
    return int(parsed.timestamp() * 1_000_000_000)


def _price_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RefusedExecution("Coinbase ticker price must be a Decimal string")
    try:
        price = Decimal(value)
    except InvalidOperation as exc:
        raise RefusedExecution("Coinbase ticker price is malformed") from exc
    if not price.is_finite() or price <= 0:
        raise RefusedExecution("Coinbase ticker price must be finite and positive")
    return value


def fetch_once(*, output: pathlib.Path = OUTPUT) -> dict:
    request_started = time.time_ns()
    request = urllib.request.Request(URL, headers={"User-Agent": "aftershock-pac-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RefusedExecution(f"SOL/USD public market-data request failed: {type(exc).__name__}") from exc
    received = time.time_ns()
    if status != 200:
        raise RefusedExecution(f"SOL/USD endpoint returned HTTP {status}")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RefusedExecution("SOL/USD endpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RefusedExecution("SOL/USD ticker response must be an object")
    price = _price_string(payload.get("price"))
    provider_ns = _provider_nanos(payload.get("time"))
    if provider_ns > received + MAX_PROVIDER_FUTURE_SKEW_NANOS:
        raise RefusedExecution("SOL/USD provider trade time is implausibly in the future")
    if received - provider_ns > MAX_PROVIDER_AGE_AT_RECEIPT_NANOS:
        raise RefusedExecution("SOL/USD provider last trade is stale at receipt")
    record = {
        "schema_version": 1,
        "source": SOURCE,
        "source_url": URL,
        "product": "SOL-USD",
        "quote_currency": "USD",
        "price": price,
        "provider_trade_time": payload["time"],
        "provider_trade_unix_nanos": provider_ns,
        "request_started_unix_nanos": request_started,
        "received_unix_nanos": received,
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_response_utf8": raw.decode("utf-8"),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
    return record


def latest_observation(*, decision_unix_nanos: int, output: pathlib.Path = OUTPUT,
                       max_local_age_nanos: int = MAX_LOCAL_AGE_NANOS) -> SolUsdObservation:
    if type(decision_unix_nanos) is not int or type(max_local_age_nanos) is not int:
        raise RefusedExecution("SOL/USD decision and freshness clocks must be exact integers")
    if decision_unix_nanos < 0 or max_local_age_nanos < 0 or not output.is_file():
        raise RefusedExecution("no causal SOL/USD observation file is available")
    candidate = None
    # The recorder is append-only and receive clocks are monotonic. Read backwards so a multi-day
    # archive does not sit on the entry hot path. Any malformed row encountered before the causal
    # candidate still fails closed; older rows are preserved for independent archive reconciliation.
    try:
        with output.open("rb") as handle:
            handle.seek(0, 2)
            position = handle.tell()
            remainder = b""
            while position > 0 and candidate is None:
                size = min(65_536, position)
                position -= size
                handle.seek(position)
                block = handle.read(size) + remainder
                pieces = block.split(b"\n")
                remainder = pieces[0]
                for raw_line in reversed(pieces[1:]):
                    if not raw_line.strip():
                        continue
                    try:
                        record = json.loads(raw_line)
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        raise RefusedExecution("SOL/USD record contains invalid JSON") from exc
                    received = record.get("received_unix_nanos")
                    if type(received) is int and received <= decision_unix_nanos:
                        candidate = record
                        break
            if candidate is None and remainder.strip():
                try:
                    record = json.loads(remainder)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise RefusedExecution("SOL/USD record contains invalid JSON") from exc
                received = record.get("received_unix_nanos")
                if type(received) is int and received <= decision_unix_nanos:
                    candidate = record
    except OSError as exc:
        raise RefusedExecution("SOL/USD observation file is unreadable") from exc
    if not isinstance(candidate, dict):
        raise RefusedExecution("no SOL/USD observation existed at the decision clock")
    received = candidate.get("received_unix_nanos")
    if decision_unix_nanos - received > max_local_age_nanos:
        raise RefusedExecution("latest causal SOL/USD observation is stale")
    raw = candidate.get("raw_response_utf8")
    digest = candidate.get("raw_response_sha256")
    if not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != digest:
        raise RefusedExecution("SOL/USD raw response hash does not reconcile")
    try:
        raw_payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RefusedExecution("SOL/USD preserved raw response is invalid JSON") from exc
    if (not isinstance(raw_payload, dict)
            or _price_string(raw_payload.get("price")) != candidate.get("price")
            or raw_payload.get("time") != candidate.get("provider_trade_time")
            or _provider_nanos(raw_payload.get("time")) != candidate.get("provider_trade_unix_nanos")):
        raise RefusedExecution("SOL/USD derived fields do not reconcile to preserved raw bytes")
    if candidate.get("source") != SOURCE or candidate.get("quote_currency") != "USD":
        raise RefusedExecution("SOL/USD record source/numeraire mismatch")
    price = _price_string(candidate.get("price"))
    return SolUsdObservation(price, received, SOURCE, digest)


def run_loop() -> None:
    while True:
        try:
            record = fetch_once()
            print(json.dumps({"received_unix_nanos": record["received_unix_nanos"],
                              "price": record["price"]}), flush=True)
        except Exception as exc:  # fail visibly; the consumer independently refuses stale data
            print(f"SOLUSD recorder error: {type(exc).__name__}: {str(exc)[:180]}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_loop()
