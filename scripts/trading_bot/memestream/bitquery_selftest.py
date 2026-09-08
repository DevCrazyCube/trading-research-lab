#!/usr/bin/env python3
"""Hermetic guards for the Bitquery reconnect circuit-breaker.  No network is opened."""
from __future__ import annotations

from .bitquery_ingest import QUOTA_RETRY_S, _server_retry_delay


def main() -> int:
    assert _server_retry_delay([{"message": "usage quota reached"}], 2.0) == QUOTA_RETRY_S
    assert _server_retry_delay({"message": "access restricted by traffic limit"}, 60.0) == QUOTA_RETRY_S
    assert _server_retry_delay({"message": "ordinary server failure"}, 7.0) == 7.0
    assert _server_retry_delay(None, 0.1) == 2.0
    print("BITQUERY INGEST SELFTEST: PASS -- quota/traffic refusal=300s; ordinary error=backoff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
