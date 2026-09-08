#!/usr/bin/env python3
"""Hermetic checks for the all-ledger census and loss-attribution arithmetic."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trading_bot.memecoin_loss_diagnostics import (
    _maximum_unavailable_rate_for_break_even,
    _reason_attribution,
)
from scripts.trading_bot.memecoin_trade_audit import audit_genomes


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj) + "\n")


def _write_ledger(path: Path, gid: str, realized_r: float) -> None:
    entry = {
        "kind": "entry", "setup_sha256": f"{gid}-setup", "genome_id": gid,
        "control": False, "dex": "pump-fun", "stop_frac": 0.25,
        "toll_per_side": 0.015, "size_sol": 0.2,
    }
    outcome = {
        "kind": "resolution", "status": "RESOLVED", "setup_sha256": f"{gid}-setup",
        "genome_id": gid, "control": False, "resolution_reason": "TARGET",
        "realized_r": realized_r,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry) + "\n" + json.dumps(outcome) + "\n")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pkg = root / "scripts" / "trading_bot" / "memebot_evo"
        for directory in (pkg, pkg / "v1_archive"):
            _write_json(directory / "population.json", {
                "genomes": {"gdup": {}}, "active": ["gdup"],
            })
            _write_json(directory / "evo_state.json", {
                "K_all_genome_ids_ever": ["gdup"], "candidates": {},
                "falsified_on_fresh_slice": {},
            })
        _write_ledger(pkg / "ledgers" / "gdup.jsonl", "gdup", 1.0)
        _write_ledger(pkg / "v1_archive" / "ledgers" / "gdup.jsonl", "gdup", 2.0)
        audit = audit_genomes(root)
        assert set(audit["experiments"]) == {"v1_archive", "v2_current"}
        assert audit["ledger_genomes"] == 2
        assert audit["distinct_genome_ids_across_experiments"] == 1
        assert set(audit["genomes"]) == {"v1_archive:gdup", "v2_current:gdup"}
        assert audit["resolved_pass_priced_across_arms"] == 2

    attribution = _reason_attribution([
        {"reason": "A", "stress_r": -1.0},
        {"reason": "B", "stress_r": -3.0},
        {"reason": "B", "stress_r": 2.0},
    ])
    assert attribution["A"]["share_of_all_negative_R"] == 0.25
    assert attribution["B"]["share_of_all_negative_R"] == 0.75

    # EXIT_V2 snapshot: executable mean 4.4039/12 and unavailable = -4.12R.
    boundary = _maximum_unavailable_rate_for_break_even(4.4039 / 12.0, -4.12)
    assert abs(boundary - 0.0818) < 0.0002
    print("MEMECOIN AUDIT SELFTEST PASS", {"break_even_unavailable_rate": round(boundary, 6)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
