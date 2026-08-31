#!/usr/bin/env python3
"""Reproducible read-only evaluation of the retired PAC_SCALP baseline.

Every slice is descriptive/post-hoc and therefore burned.  The tool never emits a successor
threshold.  Schema-1 marks cannot support a causal rug-catch estimate because they have no ghost
path or authority/provider clocks; that limitation is reported rather than filled with a guess.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import pathlib
import statistics


ROOT = pathlib.Path(__file__).resolve().parents[3]
LEDGER = ROOT / "research/trading_bot/aftershock/AFTERSHOCK_PAC_SCALP_SCENARIO_LEDGER.jsonl"
MARKS = ROOT / "research/data/aftershock/pac_scalp/marks.jsonl"
ATA_CLOSE_GAS_LAMPORTS = 5_000


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: pathlib.Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{path.name}:{number} malformed") from exc
        if not isinstance(row, dict):
            raise RuntimeError(f"{path.name}:{number} not an object")
        rows.append(row)
    return rows


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(q * len(ordered) + 0.999999) - 1))]


def evaluate(ledger_path: pathlib.Path = LEDGER, marks_path: pathlib.Path = MARKS) -> dict:
    ledger, marks = _rows(ledger_path), _rows(marks_path)
    for number, row in enumerate(ledger, 1):
        event_id = row.get("event_id"); body = dict(row); body.pop("event_id", None)
        if event_id != hashlib.sha256(_canonical(body)).hexdigest():
            raise RuntimeError(f"ledger row {number} self-hash mismatch")
    for number, row in enumerate(marks, 1):
        mark_hash = row.get("mark_sha256"); body = dict(row); body.pop("mark_sha256", None)
        if mark_hash != hashlib.sha256(_canonical(body)).hexdigest():
            raise RuntimeError(f"mark row {number} self-hash mismatch")

    entries = {row["entry_id"]: row for row in ledger if row.get("kind") == "entry_filled"}
    resolved = [row for row in ledger if row.get("kind") == "resolved"]
    resolutions = {row["entry_id"]: row for row in resolved}
    by_entry_marks: dict[str, list[dict]] = defaultdict(list)
    for mark in marks:
        if mark.get("entry_id") in entries:
            by_entry_marks[mark["entry_id"]].append(mark)
    for values in by_entry_marks.values():
        values.sort(key=lambda row: (row["observed_unix_nanos"], row["context_slot"]))

    returns = [row["net_return_num"] / row["net_return_den"] for row in resolved]
    wins = [row for row in resolved if row["net_return_num"] > 0]
    first_raw, first_corrected = [], []
    winner_min_corrected = []
    last_mark_before_full_loss = []
    for entry_id, entry in entries.items():
        path = by_entry_marks.get(entry_id, [])
        if not path:
            continue
        rent = entry["ata_rent_lamports"]
        all_in = entry["entry_all_in_lamports"]
        priceable = [mark for mark in path if isinstance(mark.get("net_exit_lamports"), int)]
        if priceable:
            raw = (priceable[0]["net_exit_lamports"] - all_in) / all_in
            corrected = (priceable[0]["net_exit_lamports"] + rent
                         - ATA_CLOSE_GAS_LAMPORTS - all_in) / all_in
            first_raw.append(raw); first_corrected.append(corrected)
        resolution = resolutions.get(entry_id)
        if resolution and resolution["net_return_num"] > 0 and priceable:
            winner_min_corrected.append(min(
                (mark["net_exit_lamports"] + rent - ATA_CLOSE_GAS_LAMPORTS - all_in) / all_in
                for mark in priceable))
        if resolution and resolution.get("unexitable_full_loss") and priceable:
            last_mark_before_full_loss.append({
                "entry_id": entry_id, "reason": resolution["reason"],
                "last_raw_return": (priceable[-1]["net_exit_lamports"] - all_in) / all_in,
                "max_raw_return": max((mark["net_exit_lamports"] - all_in) / all_in
                                      for mark in priceable),
            })

    stop_slips, stop_latencies = [], []
    decisions_by_entry: dict[str, list[dict]] = defaultdict(list)
    for row in ledger:
        if row.get("kind") == "exit_decision":
            decisions_by_entry[row["entry_id"]].append(row)
    for resolution in resolved:
        if resolution.get("action") != "EXIT_HARD_STOP":
            continue
        decisions = [row for row in decisions_by_entry[resolution["entry_id"]]
                     if row.get("action") == "EXIT_HARD_STOP"
                     and row["decision_unix_nanos"] <= resolution["resolved_unix_nanos"]]
        if not decisions:
            continue
        decision = max(decisions, key=lambda row: row["decision_unix_nanos"])
        entry_all_in = resolution["entry_all_in_lamports"]
        decision_r = (decision["decision_net_exit_lamports"] - entry_all_in) / entry_all_in
        realized_r = resolution["net_return_num"] / resolution["net_return_den"]
        stop_slips.append(realized_r - decision_r)
        stop_latencies.append((resolution["resolved_unix_nanos"]
                              - decision["decision_unix_nanos"]) / 1e9)

    action_stats = []
    for action in sorted({row["action"] for row in resolved}):
        rows = [row for row in resolved if row["action"] == action]
        rs = [row["net_return_num"] / row["net_return_den"] for row in rows]
        action_stats.append({"action": action, "n": len(rows),
                             "wins": sum(row["net_return_num"] > 0 for row in rows),
                             "full_losses": sum(bool(row["unexitable_full_loss"]) for row in rows),
                             "mean_r": statistics.fmean(rs)})
    reason_stats = []
    for reason in sorted({row["reason"] for row in resolved}):
        rows = [row for row in resolved if row["reason"] == reason]
        reason_stats.append({"reason": reason, "n": len(rows),
                             "full_losses": sum(bool(row["unexitable_full_loss"]) for row in rows)})

    return {
        "schema": 1,
        "status": "RETIRED_FALSIFIED_MEASUREMENT_DEFECTS_BURNED_POSTHOC",
        "ledger": {"path": str(ledger_path.relative_to(ROOT)), "sha256": _sha(ledger_path),
                   "bytes": ledger_path.stat().st_size, "rows": len(ledger)},
        "marks": {"path": str(marks_path.relative_to(ROOT)), "sha256": _sha(marks_path),
                  "bytes": marks_path.stat().st_size, "rows": len(marks),
                  "schema_limitation": "NO_AUTHORITY_CHAIN_NO_PROVIDER_CLOCKS_NO_TERMINAL_OR_GHOST_PATH"},
        "outcomes": {"resolved": len(resolved), "wins": len(wins),
                     "losses": len(resolved) - len(wins),
                     "full_losses": sum(bool(row["unexitable_full_loss"]) for row in resolved),
                     "sum_r": sum(returns), "mean_r": statistics.fmean(returns),
                     "median_r": statistics.median(returns), "actions": action_stats,
                     "reasons": reason_stats},
        "toll_diagnostic": {
            "first_priceable_mark_n": len(first_raw),
            "first_raw_median_r": statistics.median(first_raw) if first_raw else None,
            "first_rent_corrected_median_r": statistics.median(first_corrected) if first_corrected else None,
        },
        "winner_early_dip_descriptive": {
            "winner_paths_n": len(winner_min_corrected),
            "crossed_corrected_minus_6pct": sum(value <= -0.06 for value in winner_min_corrected),
            "crossed_corrected_minus_12pct": sum(value <= -0.12 for value in winner_min_corrected),
            "minimum_corrected_r_p10": _quantile(winner_min_corrected, 0.10),
            "not_for_threshold_selection": True,
        },
        "hard_stop_landing": {
            "joined_n": len(stop_slips),
            "decision_to_resolution_seconds_p50": statistics.median(stop_latencies) if stop_latencies else None,
            "decision_to_resolution_seconds_p90": _quantile(stop_latencies, 0.90),
            "realized_minus_decision_r_p50": statistics.median(stop_slips) if stop_slips else None,
            "realized_minus_decision_r_p90_worse": _quantile(stop_slips, 0.10),
        },
        "full_loss_last_mark_descriptive": last_mark_before_full_loss,
        "rug_catch_fraction": None,
        "rug_catch_refusal": "SCHEMA1_HAS_NO_GHOST_PATH_OR_AUTHORITY_BOUND_DECISION_LANDING_PROVIDER_CLOCKS",
        "boundary": "PAPER_SCENARIO_ONLY; POSTHOC_BURNED; NOT_EXECUTABLE_EVIDENCE; NO_PROFIT_CLAIM",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=pathlib.Path, default=LEDGER)
    parser.add_argument("--marks", type=pathlib.Path, default=MARKS)
    args = parser.parse_args(argv)
    print(json.dumps(evaluate(args.ledger, args.marks), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
