#!/usr/bin/env python3
"""Negative controls for the PAC causal tape adapter."""
from __future__ import annotations

from .execution import RefusedExecution, Source
from .pac_feed import causal_events_from_lines


def _line(ns, v_sol, *, source="public_rpc_processed", sig="SIG", mint="M"):
    return {"ts": ns / 1e9 if ns is not None else 1.0, "received_unix_nanos": ns,
            "observation_source": source, "mint": mint, "trader": "T", "side": "buy",
            "sol_amount": 0.1, "token_amount": 1.0, "v_sol": v_sol,
            "v_tokens": 1_000_000_000.0, "pool": "pump", "sig": sig}


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
    legacy = _line(None, 45.0); legacy.pop("received_unix_nanos")
    lines = [legacy, _line(101, 44.9), _line(102, 45.0)]
    events = causal_events_from_lines(lines, after_unix_nanos=100)
    ok &= _check("legacy row seeds prior reserve but never becomes evidence",
                 len(events) == 2 and events[0].pre_state.real_quote > events[0].post_state.real_quote)
    ok &= _check("PAC source is explicit public-RPC processed scenario",
                 all(event.source is Source.PUBLIC_RPC_PROCESSED for event in events))
    ok &= _check("pre-boundary rows never enter the decision stream",
                 len(causal_events_from_lines(lines, after_unix_nanos=101)) == 1)
    ok &= _check("missing signature refuses", _raises(lambda: causal_events_from_lines(
        [_line(101, 45.0, sig=None)], after_unix_nanos=100)))
    ok &= _check("wrong/missing provenance refuses", _raises(lambda: causal_events_from_lines(
        [_line(101, 45.0, source="pumpportal")], after_unix_nanos=100)))
    ok &= _check("duplicate receive clocks refuse", _raises(lambda: causal_events_from_lines(
        [_line(101, 45.0), _line(101, 45.1)], after_unix_nanos=100)))
    ok &= _check("cross-mint decision stream refuses", _raises(lambda: causal_events_from_lines(
        [_line(101, 45.0), _line(102, 45.1, mint="N")], after_unix_nanos=100)))
    print("\nPAC FEED SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
