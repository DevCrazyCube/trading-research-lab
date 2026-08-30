#!/usr/bin/env python3
"""Negative controls for the read-only PAC dashboard adapter."""
from __future__ import annotations

import json
import hashlib
import pathlib
import tempfile
import time
from unittest.mock import patch

from . import pac_dashboard as dash
from .execution import ReserveState
from .pac_v2_feed import ClockedEvent


def _write(path: pathlib.Path, obj) -> None:
    path.write_text(json.dumps(obj) + "\n")


def _check(label, condition):
    print(f"  [{'ok' if condition else 'FAIL'}] {label}")
    return bool(condition)


def _status(anchored=True, calibrated=False):
    return {"status": "NOT_ACTIVE", "strategy_process": False,
            "seal": "ANCHORED" if anchored else "UNANCHORED",
            "activation": "ANCHORED" if anchored else "ABSENT_OR_UNANCHORED",
            "dependency_count": 25, "open_gates": [],
            "latency_calibration": ("CALIBRATED_FORWARD_CLOCKS" if calibrated
                                    else "CALIBRATION_UNCALIBRATED")}


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


def _unavailable_exit_pair(i=3):
    attempt_id = f"unavailable-exit-{i}"
    attempt = _seal({"kind": "attempt_cost", "side": "EXIT", "mint": f"M{i}",
                     "attempt_id": attempt_id, "entry_attempt_id": f"entry-{i}",
                     "outcome": "SCENARIO_UNAVAILABLE", "attempt_cost_lamports": 0,
                     "cost_observed": False, "denominator_lamports": 10_000_000,
                     "labels": []})
    resolved = _resolved(i, 0, full_loss=True)
    resolved["exit_attempt_id"] = attempt_id
    resolved["exit_outcome"] = "SCENARIO_UNAVAILABLE"
    resolved = _seal({key: value for key, value in resolved.items()
                      if key not in {"schema_version", "instrument_id", "seal_sha256",
                                     "session_event_sha256", "activation_root_sha256", "event_id"}})
    return attempt, resolved


def _candidate_event(index: int, *, mint: str, base: int,
                     pre_quote: int = 1_000_000_000,
                     post_quote: int = 1_010_000_000,
                     trader: str | None = None, side: str = "buy") -> ClockedEvent:
    source = base + index * 1_000_000_000
    pre = ReserveState(30_000_000_000 + pre_quote, 1_000_000_000_000_000,
                       pre_quote, 720_100_000_000_000, False)
    post = ReserveState(30_000_000_000 + post_quote, 1_000_000_000_000_000,
                        post_quote, 720_100_000_000_000, False)
    return ClockedEvent(
        event_id=hashlib.sha256(f"candidate-{mint}-{index}".encode()).hexdigest(),
        collector_epoch="epoch", mint=mint, trader=trader or f"buyer-{index}",
        signature=f"signature-{index}", slot=index + 1, side=side,
        source_received_unix_nanos=source, materialized_unix_nanos=source + 1,
        runner_seen_unix_nanos=source + 2, pre_state=pre, post_state=post)


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
                     good["evidence_status"] == "VALID_UNCALIBRATED_PAPER_SCENARIO"
                     and good["performance"]["equity_curve"]
                     == ["100.0000", "102.0000", "101.9000", "91.9000"]
                     and good["performance"]["full_losses"] == 1
                     and good["performance"]["failed_attempt_cost_events"] == 1
                     and good["performance"]["scenario_resolved"] == 2
                     and good["performance"]["promotion_discovery_resolved"] == 0)

        calibrated = dash.snapshot(
            ledger_path=ledger, state_path=state, status_snapshot=_status(True, calibrated=True))
        ok &= _check("only measured forward-clock rows increment promotion discovery",
                     calibrated["evidence_status"] == "VALID_PAPER_SCENARIO"
                     and calibrated["performance"]["promotion_discovery_resolved"] == 2
                     and calibrated["performance"]["discovery_progress"] == "0.0200")

        unavailable_attempt, unavailable_resolution = _unavailable_exit_pair()
        unavailable_rows = [_opened(3), unavailable_attempt, unavailable_resolution]
        ledger.write_text("".join(json.dumps(row) + "\n" for row in unavailable_rows))
        unavailable = dash.snapshot(
            ledger_path=ledger, state_path=state, status_snapshot=_status(True))
        ok &= _check("one unavailable EXIT attempt may cause one matching full-loss resolution",
                     unavailable["evidence_status"] == "VALID_UNCALIBRATED_PAPER_SCENARIO"
                     and unavailable["performance"]["resolved"] == 1
                     and unavailable["performance"]["full_losses"] == 1
                     and unavailable["performance"]["failed_attempt_cost_events"] == 1)

        wrong_pair = dict(unavailable_resolution)
        wrong_pair["mint"] = "ANOTHER-MINT"
        wrong_pair = _seal({key: value for key, value in wrong_pair.items()
                            if key not in {"schema_version", "instrument_id", "seal_sha256",
                                           "session_event_sha256", "activation_root_sha256", "event_id"}})
        ledger.write_text("".join(json.dumps(row) + "\n"
                                  for row in [_opened(3), unavailable_attempt, wrong_pair]))
        wrong = dash.snapshot(ledger_path=ledger, state_path=state, status_snapshot=_status(True))
        ok &= _check("unavailable attempt reuse across another mint REFUSES",
                     wrong["evidence_status"] == "REFUSED_LEDGER_INTEGRITY")

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

        solusd_path = root / "solusd.jsonl"
        received = time.time_ns()
        raw = json.dumps({"price": "123.45", "time": "2026-08-29T00:00:00Z"},
                         separators=(",", ":"))
        _write(solusd_path, {
            "source": dash.solusd_recorder.SOURCE, "quote_currency": "USD",
            "price": "123.45", "provider_trade_time": "2026-08-29T00:00:00Z",
            "received_unix_nanos": received, "raw_response_utf8": raw,
            "raw_response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        })
        original_output = dash.solusd_recorder.OUTPUT
        try:
            dash.solusd_recorder.OUTPUT = solusd_path
            displayed = dash._latest_solusd_status()
        finally:
            dash.solusd_recorder.OUTPUT = original_output
        ok &= _check("fresh reconciled SOL/USD is displayed instead of hidden as unavailable",
                     displayed["status"] == "FRESH" and displayed["price"] == "123.45")

        base = time.time_ns() - 2_000_000_000
        candidate = _candidate_event(0, mint="VISIBLE-MINT", base=base)
        funnel = dash._v2_candidate_funnel(
            {candidate.mint: [dash.pac_v2_runner._event_dict(candidate)]},
            reaction_p90_nanos=12_000_000_000, quote_input_lamports=100_000_000,
            now=base + 1_000_000_000)
        ok &= _check("live V2 mint buffers remain visible before any entry decision",
                     funnel["summary"]["buffered_mints"] == 1
                     and funnel["summary"]["eligible_events"] == 1
                     and funnel["candidates"][0]["mint"] == "VISIBLE-MINT"
                     and funnel["candidates"][0]["gate"] == "NO_PAC_CORE")

        qualifying = (
            _candidate_event(0, mint="QUALIFIED-MINT", base=base,
                             pre_quote=1_000_000_000, post_quote=900_000_000,
                             trader="seller-1", side="sell"),
            _candidate_event(2, mint="QUALIFIED-MINT", base=base,
                             pre_quote=900_000_000, post_quote=1_000_000_000,
                             trader="buyer-0"),
            _candidate_event(3, mint="QUALIFIED-MINT", base=base,
                             pre_quote=1_000_000_000, post_quote=900_000_000,
                             trader="seller-2", side="sell"),
            _candidate_event(4, mint="QUALIFIED-MINT", base=base,
                             pre_quote=900_000_000, post_quote=1_000_000_000,
                             trader="buyer-1"),
            _candidate_event(5, mint="QUALIFIED-MINT", base=base,
                             pre_quote=1_000_000_000, post_quote=1_010_000_000,
                             trader="buyer-2"),
            _candidate_event(6, mint="QUALIFIED-MINT", base=base,
                             pre_quote=1_010_000_000, post_quote=1_020_000_000,
                             trader="buyer-3"),
        )
        qualified_funnel = dash._v2_candidate_funnel(
            {"QUALIFIED-MINT": [dash.pac_v2_runner._event_dict(item)
                                for item in qualifying]},
            reaction_p90_nanos=1_000_000_000, quote_input_lamports=50_000_000,
            now=base + 7_000_000_000)
        ok &= _check("dashboard gate trace reaches QUALIFIED iff frozen detector does",
                     qualified_funnel["summary"]["qualified_mints"] == 1
                     and qualified_funnel["candidates"][0]["gate"] == "QUALIFIED"
                     and qualified_funnel["candidates"][0]["buyer_breadth"] == 3)

        v21_qualifying = (
            _candidate_event(0, mint="V21-QUALIFIED-MINT", base=base,
                             pre_quote=1_200_000_000, post_quote=1_050_000_000,
                             trader="seller", side="sell"),
            _candidate_event(1, mint="V21-QUALIFIED-MINT", base=base,
                             pre_quote=1_050_000_000, post_quote=1_120_000_000,
                             trader="buyer-1"),
            _candidate_event(2, mint="V21-QUALIFIED-MINT", base=base,
                             pre_quote=1_120_000_000, post_quote=1_200_000_000,
                             trader="buyer-2"),
            _candidate_event(3, mint="V21-QUALIFIED-MINT", base=base,
                             pre_quote=1_200_000_000, post_quote=1_240_000_000,
                             trader="buyer-3"),
            _candidate_event(4, mint="V21-QUALIFIED-MINT", base=base,
                             pre_quote=1_240_000_000, post_quote=1_260_000_000,
                             trader="buyer-3"),
        )
        v21_funnel = dash._v21_candidate_funnel(
            {"V21-QUALIFIED-MINT": [dash.pac_v2_runner._event_dict(item)
                                    for item in v21_qualifying]},
            processed_p90_nanos=2_000_000_000,
            quote_input_lamports=100_000_000,
            now=base + 5_000_000_000)
        ok &= _check("V2.1 dashboard trace matches the sealed single-shock detector",
                     v21_funnel["summary"]["qualified_mints"] == 1
                     and v21_funnel["summary"]["pac_core_mints"] == 1
                     and v21_funnel["candidates"][0]["gate"] == "QUALIFIED"
                     and v21_funnel["candidates"][0]["buyer_breadth"] == 3
                     and v21_funnel["candidates"][0]["largest_observed_sell_lamports"]
                     == 150_000_000)

        short_v21_rows = [dash.pac_v2_runner._event_dict(item)
                          for item in v21_qualifying[:4]]
        short_v21 = dash._v21_candidate_funnel(
            {"V21-QUALIFIED-MINT": short_v21_rows},
            processed_p90_nanos=2_000_000_000,
            quote_input_lamports=100_000_000,
            now=base + 4_000_000_000)
        later_wall_clock = dash._v21_candidate_funnel(
            {"V21-QUALIFIED-MINT": short_v21_rows},
            processed_p90_nanos=2_000_000_000,
            quote_input_lamports=100_000_000,
            now=base + 10_000_000_000)
        short_row = short_v21["candidates"][0]
        ok &= _check("V2.1 UI shows observed buyers before dwell while wall time cannot fake dwell",
                     short_row["gate"] == "P90_DWELL"
                     and short_row["buyer_breadth"] == 3
                     and short_row["dwell_nanos"] == 1_000_000_000
                     and short_row["dwell_clock"] == "SAME_MINT_EVENT_TIME_NOT_WALL_CLOCK"
                     and later_wall_clock["candidates"][0]["dwell_nanos"]
                     == short_row["dwell_nanos"]
                     and later_wall_clock["candidates"][0]["age_millis"]
                     > short_row["age_millis"])

        future = _candidate_event(2, mint="FUTURE-MINT", base=base)
        try:
            dash._v2_candidate_funnel(
                {future.mint: [dash.pac_v2_runner._event_dict(future)]},
                reaction_p90_nanos=12_000_000_000, quote_input_lamports=100_000_000,
                now=base + 1_000_000_000)
        except dash.RefusedExecution:
            refused_future = True
        else:
            refused_future = False
        ok &= _check("candidate diagnostics refuse future evidence", refused_future)

        v21_campaign, v21_activation = root / "v21-campaign.json", root / "v21-activation.json"
        with (patch.object(dash.pac_v21_manifest, "anchor_status", return_value="ANCHORED"),
              patch.object(dash.pac_v21_manifest, "CAMPAIGN", v21_campaign),
              patch.object(dash.pac_v21_manifest, "ACTIVATION", v21_activation)):
            successor = dash._v21_successor_status()
            ok &= _check("anchored V2.1 seal is visible without inventing campaign or performance",
                         successor["status"] == "SEALED_DEFAULT_OFF_AWAITING_OWNER_CAMPAIGN"
                         and successor["campaign"] == "ABSENT"
                         and successor["activation"] == "ABSENT")

            v21_campaign.write_text("{}\n")
            with patch.object(dash.pac_v21_manifest, "_git_clean", return_value=True):
                successor = dash._v21_successor_status()
            ok &= _check("anchored campaign remains visibly gated on calibration and attestation",
                         successor["status"]
                         == "CAMPAIGN_ANCHORED_CALIBRATION_AND_ATTESTATION_REQUIRED")

        with (patch.object(dash, "_v21_successor_status",
                           return_value={"activation": "ANCHORED"}),
              patch.object(dash, "v21_snapshot",
                           return_value={"instrument_id": "AFTERSHOCK_PAC_V21"})):
            focused = dash.focus_snapshot()
        ok &= _check("anchored V2.1 activation selects V2.1 as the dashboard focus",
                     focused["instrument_id"] == "AFTERSHOCK_PAC_V21")

        with (patch.object(dash, "_v21_successor_status",
                           return_value={"activation": "ABSENT"}),
              patch.object(dash, "v2_snapshot",
                           return_value={"instrument_id": "AFTERSHOCK_PAC_V2"})):
            focused = dash.focus_snapshot()
        ok &= _check("dashboard keeps V2 control focused before V2.1 activation",
                     focused["instrument_id"] == "AFTERSHOCK_PAC_V2")

    print("PAC DASHBOARD SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
