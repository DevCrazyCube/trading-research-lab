#!/usr/bin/env python3
"""Negative controls for slot-independent PAC LWS eligibility recording."""
from __future__ import annotations

import json
import pathlib
import tempfile

from .execution import RefusedExecution
from . import pac_lws_eligibility as subject
from . import pac_lws_feed as feed


NOW = 2_000_000_000_000_000_000
T0 = 1000
MINT = "mint-A"


def _write(path, rows, *, partial=b""):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True).encode() + b"\n")
        handle.write(partial)


def _registry(mint=MINT):
    return {"mint": mint, "t0_slot": T0, "create_observed_unix_nanos": NOW,
            "seedable": True, "create_after_first_trade": False, "dev_wallet": "dev"}


def _event(slot, trader, amount, post, *, mint=MINT):
    return {"mint": mint, "slot": slot, "received_unix_nanos": NOW + slot,
            "trader": trader, "is_buy": True, "token_amount": amount,
            "post_real_token": post, "reserve_delta_tokens": amount,
            "anchored": True, "reconciled": True}


def _chain(rows):
    output = []; previous = subject.GENESIS
    for seq, row in enumerate(rows):
        body = {"schema": feed.SCHEMA, "instrument_id": feed.INSTRUMENT_ID,
                "collector_epoch": "test", "seq": seq, "sol_amount": 1,
                "pre_real_token": None, "t0_slot": T0, "signature": f"sig-{seq}",
                "prev_hash": previous, **row}
        observed = feed._canonical_sha(body)
        output.append({**body, "event_hash": observed}); previous = observed
    return output


def _health(path, head):
    feed.write_health(status="FRESH", epoch="test", observed_unix_nanos=NOW,
                      head_slot=head, event_slot=head, reason=None, path=path)


def _check(name, value):
    print(f"  [{'ok' if value else 'FAIL'}] {name}")
    return bool(value)


def _raises(fn):
    try:
        fn(); return False
    except RefusedExecution:
        return True


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory(prefix="pac_lws_elig_") as directory:
        root = pathlib.Path(directory); reg = root / "registry.jsonl"; events = root / "events.jsonl"
        state = root / "state.json"; ledger = root / "ledger.jsonl"; health = root / "health.json"
        feed_health = root / "feed_health.json"
        _write(reg, []); _write(events, []); _health(feed_health, T0)
        subject.run_once(
            now=NOW, quote_input_lamports=10_000_000, state_path=state, ledger_path=ledger,
            health_path=health, registry_path=reg, events_path=events,
            feed_health_path=feed_health, initialize_at_eof=False)
        _write(reg, [_registry()])
        # Only in-window events: the global head, not a same-mint post-window trade, closes eligibility.
        first_events = [_event(T0 + 1, "a", 60, 700_000_000_000_000),
                        _event(T0 + 5, "b", 40, 699_000_000_000_000)]
        _write(events, _chain(first_events))
        _health(feed_health, T0 + 63)
        result = subject.run_once(
            now=NOW + 20_000, quote_input_lamports=10_000_000, state_path=state,
            ledger_path=ledger, health_path=health, registry_path=reg, events_path=events,
            feed_health_path=feed_health, initialize_at_eof=False)
        row = json.loads(ledger.read_text())
        ok &= _check("global head closes a mint without a post-window same-mint event",
                     result["emitted_cycle"] == 1 and row["filter"] == "SCREEN_SURVIVED")
        ok &= _check("same causal record defines both arms and is independent of book capacity",
                     row["base_eligible"] and row["veto_eligible"]
                     and "open_positions" not in row and "portfolio_capacity" not in row)
        info = {"mint": MINT, "t0_slot": T0, "create_observed_unix_nanos": NOW,
                "dev_wallet": "dev"}
        post = _event(T0 + 500, "later", 1, 100_000_000_000_000)
        before = subject._record(info, first_events, head_slot=T0 + 600,
                                 decided_ns=NOW + 100_000, quote_input_lamports=10_000_000,
                                 previous_hash=subject.GENESIS)
        after = subject._record(info, first_events + [post], head_slot=T0 + 600,
                                decided_ns=NOW + 100_000, quote_input_lamports=10_000_000,
                                previous_hash=subject.GENESIS)
        ok &= _check("post-window outcome cannot change coverage eligibility",
                     before["real_quote_lamports"] == after["real_quote_lamports"]
                     and before["base_eligible"] == after["base_eligible"])
        snapshot = json.loads(state.read_text()); snapshot["event_offset"] += 1
        state.write_text(json.dumps(snapshot))
        ok &= _check("unhashed cursor mutation refuses",
                     _raises(lambda: subject._load_state(state)))
        state.write_text(json.dumps(subject._seal_state({
            k: v for k, v in snapshot.items() if k != "state_sha256"})))
        ok &= _check("runtime notional drift refuses",
                     _raises(lambda: subject.run_once(
                         now=NOW + 25_000, quote_input_lamports=10_000_001,
                         state_path=state, ledger_path=ledger, health_path=health,
                         registry_path=reg, events_path=events,
                         feed_health_path=feed_health, initialize_at_eof=False)))
        # restore the correct cursor/state before restart reconciliation
        snapshot["event_offset"] -= 1
        state.write_text(json.dumps(subject._seal_state({
            k: v for k, v in snapshot.items() if k != "state_sha256"})))
        # Simulate power loss after ledger fsync but before state replace: stale state still thinks the
        # mint is pending. Restart must reconcile by mint from the validated append chain.
        stale = json.loads(state.read_text())
        stale["pending"][MINT] = {"mint": MINT, "t0_slot": T0,
            "create_observed_unix_nanos": NOW, "dev_wallet": "dev",
            "events": [_event(T0 + 1, "a", 60, 700_000_000_000_000),
                       _event(T0 + 5, "b", 40, 699_000_000_000_000)]}
        stale["last_record_hash"] = subject.GENESIS; stale["emitted"] = 0
        state.write_text(json.dumps(subject._seal_state(stale)))
        again = subject.run_once(
            now=NOW + 30_000, quote_input_lamports=10_000_000, state_path=state,
            ledger_path=ledger, health_path=health, registry_path=reg, events_path=events,
            feed_health_path=feed_health, initialize_at_eof=False)
        ok &= _check("append-first crash restart is idempotent", again["emitted_cycle"] == 0
                     and len(ledger.read_text().splitlines()) == 1)

        # A single buyer is unreadable and excluded from both arms.
        mint2 = "mint-B"; _write(reg, [_registry(), _registry(mint2)])
        _write(events, _chain(first_events + [
            _event(T0 + 2, "solo", 100, 699_000_000_000_000, mint=mint2)]))
        result2 = subject.run_once(
            now=NOW + 40_000, quote_input_lamports=10_000_000, state_path=state,
            ledger_path=ledger, health_path=health, registry_path=reg, events_path=events,
            feed_health_path=feed_health, initialize_at_eof=False)
        row2 = json.loads(ledger.read_text().splitlines()[-1])
        ok &= _check("UNREADABLE is never tradeable in either arm",
                     result2["emitted_cycle"] == 1 and row2["filter"] == "UNREADABLE"
                     and not row2["base_eligible"] and not row2["veto_eligible"])

        # Partial writer tail is not consumed; completing it later makes exactly one record visible.
        p = root / "partial.jsonl"; good = json.dumps({"x": 1}).encode()
        _write(p, [], partial=good[:5])
        rows, offset = subject._consume(p, 0)
        ok &= _check("partial JSON tail does not advance cursor", rows == [] and offset == 0)
        with p.open("ab") as handle:
            handle.write(good[5:] + b"\n")
        rows, offset = subject._consume(p, offset)
        ok &= _check("completed tail becomes one record", rows == [{"x": 1}] and offset == p.stat().st_size)
        bad = root / "bad.jsonl"; bad.write_bytes(b"{bad}\n")
        ok &= _check("malformed complete input refuses visibly",
                     _raises(lambda: subject._consume(bad, 0)))
        future = root / "future.jsonl"
        _write(future, [{"received_unix_nanos": NOW + 1}])
        rows, offset = subject._consume(
            future, 0, now=NOW, clock_field="received_unix_nanos")
        ok &= _check("future receipt defers without advancing input cursor",
                     rows == [] and offset == 0)
    print("PAC LWS ELIGIBILITY SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
