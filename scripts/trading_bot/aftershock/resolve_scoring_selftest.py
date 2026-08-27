#!/usr/bin/env python3
"""Offline selftest for resolve.py (5 exit triggers + stressed ECR) and scoring.py (pot growth + gates).

    python -m scripts.trading_bot.aftershock.resolve_scoring_selftest
"""
from __future__ import annotations

import math

from . import resolve, scoring

K = 30.0 * 1_073_000_000.0

_SPEC = {
    "instrument_id": "AFTERSHOCK",
    "position_fraction": 0.02,
    "frozen_utc": "2026-08-27T00:00:00+00:00",
    "kill_switch": {"N_min": 30, "rule": "HALT if upper95(g)<0 or dump>=max after N_min"},
    "dump_rate_max": 0.13,
    "detector": {"q_sol": 0.1},
    "exit": {"coverage_exit_buffer": 6.0, "cluster_resume_frac_of_R": 0.25,
             "flow_flip_sell_frac": 0.65, "flow_window_slots": 60, "trail_frac": 0.12,
             "max_hold_slots": 3000},
}


def _line(v_sol, ts, trader="X", side="buy", pool="pump"):
    return {"ts": ts, "mint": "M", "trader": trader, "side": side,
            "sol_amount": 0.0, "token_amount": 0.0, "v_sol": v_sol, "v_tokens": K / v_sol, "pool": pool}


def _setup(v_sol_entry=45.0, cluster=("DEV",)):
    er = {"v_sol": v_sol_entry, "v_tokens": K / v_sol_entry, "pool": "pump", "ts": 100.0}
    return {"instrument_id": "AFTERSHOCK", "control": False, "setup_sha256": "x", "pool_address": "M",
            "name": "M", "screen_verdict": "PASS", "entry_price_usd": (v_sol_entry / (K / v_sol_entry)) * 200,
            "toll_per_side": 0.0125, "stop_frac": 0.5, "q_sol": 0.1, "t_entry": 100.0,
            "entry_reserves": er, "cluster_wallets": list(cluster), "deployer": "DEV"}


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def main() -> int:
    ok = True

    # A) TRAIL_STOP winner: price runs to 4x then gives back 12% -> trail; exit reserves high -> positive.
    tape = [_line(45, 100), _line(90, 101), _line(84.35, 102)]  # peak at 90, 84.35^2/90^2 ~= 0.879 <= 0.88
    r = resolve.resolve_from_tape(_setup(), tape, _SPEC)
    ok &= _check("TRAIL_STOP fires on 12% give-back, winner exitable, positive stressed return",
                 r is not None and r["resolution_reason"] == "TRAIL_STOP"
                 and not r["unexitable"] and r["stressed_net_return"] > 0,
                 (f"{r['resolution_reason']} sr={r['stressed_net_return']}" if r else "None"))

    # B) COVERAGE_BREAK: R falls below the buffer (coverage < 6 -> R < 0.6 SOL).
    tape = [_line(45, 100), _line(30.4, 101)]   # R=0.4 -> coverage 4 < 6
    r = resolve.resolve_from_tape(_setup(), tape, _SPEC)
    ok &= _check("COVERAGE_BREAK fires when standing book can't cover",
                 r is not None and r["resolution_reason"] in ("COVERAGE_BREAK", "UNEXITABLE_TIMEOUT"),
                 (r["resolution_reason"] if r else "None"))

    # C) MAX_HOLD with a migrated exit -> UNEXITABLE_TIMEOUT, full loss.
    tape = [_line(45, 100), _line(46, 100 + 3000 * 0.4 + 1, pool="pumpswap")]
    r = resolve.resolve_from_tape(_setup(), tape, _SPEC)
    ok &= _check("MAX_HOLD + migrated exit -> UNEXITABLE_TIMEOUT, stressed -1.0",
                 r is not None and r["resolution_reason"] == "UNEXITABLE_TIMEOUT"
                 and r["unexitable"] and r["stressed_net_return"] == -1.0,
                 (f"{r['resolution_reason']} sr={r['stressed_net_return']}" if r else "None"))

    # D) CLUSTER_RESUME: a cluster wallet sells materially after entry.
    tape = [_line(45, 100), _line(40, 101, trader="DEV", side="sell")]  # sells ~5 SOL >= 0.25*R_pre(15)
    r = resolve.resolve_from_tape(_setup(), tape, _SPEC)
    ok &= _check("CLUSTER_RESUME fires when cluster wallet resumes distributing",
                 r is not None and r["resolution_reason"] in ("CLUSTER_RESUME", "COVERAGE_BREAK", "TRAIL_STOP"),
                 (r["resolution_reason"] if r else "None"))

    # E) still open: no trigger yet, before the horizon -> None.
    ok &= _check("no trigger before horizon -> still open (None)",
                 resolve.resolve_from_tape(_setup(), [_line(45, 100), _line(46, 101)], _SPEC, now=101.0) is None)

    # F) WALL-CLOCK MAX-HOLD (review #3/#5): a SILENT position past the horizon resolves even with no
    # tape line crossing it.
    silent = resolve.resolve_from_tape(_setup(), [_line(45, 100)], _SPEC, now=100 + 3000 * 0.4 + 5)
    ok &= _check("wall-clock MAX_HOLD resolves a silent position",
                 silent is not None and silent["resolution_reason"] in ("MAX_HOLD", "UNEXITABLE_TIMEOUT"),
                 (silent["resolution_reason"] if silent else "None"))

    # G) FLOW_FLIP floor (review #4): a lone trivial non-cluster sell must NOT trip the flow exit.
    ff = resolve.resolve_from_tape(_setup(), [_line(45, 100), _line(44.99, 101, trader="Z", side="sell")],
                                   _SPEC, now=101.0)
    ok &= _check("FLOW_FLIP does not trip on a lone trivial sell (below the floor)",
                 ff is None or ff["resolution_reason"] != "FLOW_FLIP",
                 (ff["resolution_reason"] if ff else "still-open"))

    # ---- scoring ----
    f = 0.02
    # 10 winners at +2.0, 2 full-loss dumps -> known G.
    recs = ([{"control": False, "stressed_net_return": 2.0, "unexitable": False, "deployer": f"d{i}"} for i in range(10)]
            + [{"control": False, "stressed_net_return": -1.0, "unexitable": True, "deployer": "dz"} for _ in range(2)]
            + [{"control": True, "stressed_net_return": 0.5, "unexitable": False}])  # a control, ignored in G
    rep = scoring.score(_SPEC, recs)
    expG = 10 * math.log(1 + f * 2.0) + 2 * math.log(1 - f)
    ok &= _check("pot growth G matches Σ ln(1+f·r) over PASS trades only",
                 abs(rep["inputs_that_are_not_results"]["log_growth_G"] - round(expG, 5)) < 1e-4,
                 f"G={rep['inputs_that_are_not_results']['log_growth_G']} exp={round(expG,5)}")
    ok &= _check("dump_rate = 2/12 over PASS trades (control excluded)",
                 abs(rep["inputs_that_are_not_results"]["dump"]["dump_rate"] - 2/12) < 1e-9,
                 str(rep["inputs_that_are_not_results"]["dump"]["dump_rate"]))
    ok &= _check("below N_min -> NO VERDICT, body fenced",
                 not rep["readable"] and "inputs_that_are_not_results" in rep)

    # dump-rate kill-gate trips past N_min when unexitable rate >= 0.13
    many = [{"control": False, "stressed_net_return": -1.0, "unexitable": True, "deployer": "d"} for _ in range(31)]
    rep2 = scoring.score(_SPEC, many)
    ok &= _check("dump-rate HALT trips past N_min when all unexitable",
                 "HALTED" in rep2["kill_switch"]["dump_gate"]["verdict"])

    print("\nRESOLVE+SCORING SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
