#!/usr/bin/env python3
"""Negative controls for the read-only PAC dashboard adapter."""
from __future__ import annotations

import json
import hashlib
import pathlib
import tempfile

from . import pac_dashboard as dash


def _write(path: pathlib.Path, obj) -> None:
    path.write_text(json.dumps(obj) + "\n")


def _check(label, condition):
    print(f"  [{'ok' if condition else 'FAIL'}] {label}")
    return bool(condition)


def _status(anchored=True):
    return {"status": "NOT_ACTIVE", "strategy_process": False,
            "seal": "ANCHORED" if anchored else "UNANCHORED",
            "activation": "ANCHORED" if anchored else "ABSENT_OR_UNANCHORED",
            "dependency_count": 25, "open_gates": []}


def _seal(body):
    row = {"schema_version": 2, "instrument_id": "AFTERSHOCK_PAC_V1",
           "seal_sha256": "a" * 64, "session_event_sha256": "b" * 64,
           "activation_root_sha256": "c" * 64, **body}
    raw = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    row["event_id"] = hashlib.sha256(raw.encode()).hexdigest()
    return row


def _state():
    state = dash.pac_runner._new_state()
    state["session_event_sha256"] = "b" * 64
    state["activation_root_sha256"] = "c" * 64
    return state


def _opened(i):
    return _seal({"kind": "opened", "mint": f"M{i}",
            "token_atoms": 1000, "quote_input_lamports": 9_700_000,
            "entry_curve_fee_lamports": 100_000, "entry_attempt_cost_lamports": 100_000,
            "ata_rent_lamports": 100_000,
            "entry_all_in_lamports": 10_000_000, "entry_decision_id": f"d{i}",
            "entry_attempt_id": f"entry-{i}", "entry_observation_unix_nanos": 100 + i})


def _resolved(i, exit_net, *, full_loss=False):
    return _seal({"kind": "resolved", "mint": f"M{i}",
            "action": "UNEXITABLE_FULL_LOSS" if full_loss else "ATTEMPT_FULL_EXIT_TRAIL",
            "entry_attempt_id": f"entry-{i}", "exit_attempt_id": None if full_loss else f"exit-{i}",
            "entry_all_in_lamports": 10_000_000, "exit_net_proceeds_lamports": exit_net,
            "exit_gross_quote_lamports": 0 if full_loss else exit_net + 200_000,
            "exit_curve_fee_lamports": 0 if full_loss else 100_000,
            "exit_attempt_cost_lamports": 0 if full_loss else 100_000,
            "net_return_num": exit_net - 10_000_000, "net_return_den": 10_000_000,
            "entry_observation_unix_nanos": 100 + i,
            "exit_boundary_observation_unix_nanos": None if full_loss else 200 + i,
            "unexitable_full_loss": full_loss})


def _attempt_cost():
    return _seal({"kind": "attempt_cost", "side": "ENTRY", "mint": "MX",
                  "attempt_id": "failed-entry", "entry_attempt_id": None,
                  "outcome": "SCENARIO_FAILED_SLIPPAGE", "attempt_cost_lamports": 100_000,
                  "cost_observed": True, "denominator_lamports": 10_000_000, "labels": []})


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory(prefix="pac_dash_") as td:
        root = pathlib.Path(td)
        ledger, state = root / "ledger.jsonl", root / "state.json"
        empty = dash.snapshot(ledger_path=ledger, state_path=state, status_snapshot=_status(False))
        ok &= _check("empty unanchored book shows NO evidence, not fake zero performance",
                     empty["evidence_status"] == "NO_FORWARD_EVIDENCE"
                     and empty["performance"]["equity_curve"] == ["100.0000"])

        rows = [_opened(1), _resolved(1, 12_000_000), _attempt_cost(),
                _opened(2), _resolved(2, 0, full_loss=True)]
        ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
        _write(state, _state())
        good = dash.snapshot(ledger_path=ledger, state_path=state, status_snapshot=_status(True))
        ok &= _check("all-cost rows include failed-attempt gas in the portfolio curve",
                     good["evidence_status"] == "VALID_PAPER_SCENARIO"
                     and good["performance"]["equity_curve"]
                     == ["100.0000", "102.0000", "101.9000", "91.9000"]
                     and good["performance"]["full_losses"] == 1
                     and good["performance"]["failed_attempt_cost_events"] == 1)

        legacy = dict(rows[1]); legacy.pop("entry_all_in_lamports")
        ledger.write_text(json.dumps(rows[0]) + "\n" + json.dumps(legacy) + "\n")
        bad = dash.snapshot(ledger_path=ledger, state_path=state, status_snapshot=_status(True))
        ok &= _check("gross/incomplete cost rows REFUSE instead of becoming a chart",
                     bad["evidence_status"] == "REFUSED_LEDGER_INTEGRITY"
                     and bad["performance"]["resolved"] == 0)

        duplicate_row = dict(_resolved(1, 12_000_000))
        duplicate_row["event_id"] = _opened(1)["event_id"]
        duplicate = [_opened(1), duplicate_row]
        ledger.write_text("".join(json.dumps(row) + "\n" for row in duplicate))
        dup = dash.snapshot(ledger_path=ledger, state_path=state, status_snapshot=_status(True))
        ok &= _check("duplicate event ids REFUSE", dup["evidence_status"] == "REFUSED_LEDGER_INTEGRITY")

        ledger.write_text(json.dumps(_opened(1)) + "\n")
        mismatch = dash.snapshot(ledger_path=ledger, state_path=state, status_snapshot=_status(True))
        ok &= _check("state/ledger open-book mismatch REFUSES",
                     mismatch["evidence_status"] == "REFUSED_LEDGER_INTEGRITY")

        pending_state = _state(); pending_state["pending_ledger_rows"] = [_opened(9)]
        _write(state, pending_state)
        pending = dash.snapshot(ledger_path=root / "absent", state_path=state,
                                status_snapshot=_status(True))
        ok &= _check("pending two-phase ledger transaction REFUSES dashboard performance",
                     pending["evidence_status"] == "REFUSED_LEDGER_INTEGRITY")

        _write(state, _state())
        ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
        unanchored = dash.snapshot(ledger_path=ledger, state_path=state, status_snapshot=_status(False))
        ok &= _check("unanchored rows never become evidence",
                     unanchored["evidence_status"] == "REFUSED_UNANCHORED_EVIDENCE"
                     and unanchored["performance"]["resolved"] == 0)

    print("PAC DASHBOARD SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
