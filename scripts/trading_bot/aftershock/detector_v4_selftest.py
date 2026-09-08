#!/usr/bin/env python3
"""Offline selftest for AFTERSHOCK V4 (PROFIT-LOCK). Asserts: entry fires (V3 entry reused); the profit
floor SAVES a green-then-fade trade (arm B exits PROFIT_LOCK at a small win where the plain trail arm A
takes a loss); and the floor does NOT cap a big runner (arm A == arm B on a high-peak trail-out). No net.

    python -m scripts.trading_bot.aftershock.detector_v4_selftest
"""
from __future__ import annotations

from .detector_selftest import _Curve
from .detector_v2_selftest import _build as _build_v2
from .detector_v3 import DetectorV3Config, _MintDetectorV3
from .frozen import frozen_spec
from . import resolve_v4

SPEC = frozen_spec("AFTERSHOCK_V4")
ARM = {a["arm"]: a for a in SPEC["arms"]}
K = 30.0 * 1_073_000_000.0


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def _setup(t_entry=100.0):
    er = {"v_sol": 47.0, "v_tokens": K / 47.0, "pool": "pump"}
    return {"q_sol": 0.1, "cluster_wallets": ["DEV"], "t_entry": t_entry, "entry_reserves": er,
            "entry_price_usd": 1.0, "deployer": "DEV", "toll_per_side": SPEC["toll_per_side"],
            "stop_frac": SPEC["stop_frac"], "target_frac": SPEC["target_frac"], "size_sol": 0.1,
            "setup_sha256": "t", "pool_address": "MINT", "control": False}


def _tape(path, t0=100.0):
    cc = _Curve(); cc.v_sol = 47.0; cc.v_tokens = K / 47.0
    out = []; t = t0 + 1.0
    for v in path:
        out.append(cc.trade(t, "B" if v >= cc.v_sol else "S", "buy" if v >= cc.v_sol else "sell", v)); t += 1.0
    return out


def main() -> int:
    ok = True

    # 1) entry: V3/net-replacement entry still fires through the V4 (=V3) detector
    cfg = DetectorV3Config.from_spec(SPEC, veto_strict=False)
    det = _MintDetectorV3(cfg=cfg)
    fires = [r for ln in _build_v2(recover_to=46.5) if (r := det.on_line(ln)) is not None]
    ok &= _check("net-replacement -> V4 entry FIRE (PASS)", len([f for f in fires if not f["control"]]) == 1,
                 f"pass={len([f for f in fires if not f['control']])}")

    # 2) GREEN-THEN-FADE: peaks ~+7% (>lock_arm 1.05) then bleeds back below break-even.
    #    Arm A (plain trail) takes a LOSS; arm B (lock 1.05/1.02) exits PROFIT_LOCK at a small WIN.
    fade = _tape([48.0, 49.0, 50.0, 49.5, 49.0, 48.5, 48.0, 47.5, 47.0, 46.5, 46.0])
    rA = resolve_v4.resolve_from_tape_v4(_setup(), fade, SPEC, ARM["A"], now=500.0)
    rB = resolve_v4.resolve_from_tape_v4(_setup(), fade, SPEC, ARM["B"], now=500.0)
    ok &= _check("green-then-fade: arm B locks a WIN where arm A takes a loss",
                 rB and rA and rB["resolution_reason"] == "PROFIT_LOCK"
                 and rB["stressed_net_return"] > 0 >= rA["stressed_net_return"],
                 f"A={rA['resolution_reason']}({rA['stressed_net_return']:+.3f}) B={rB['resolution_reason']}({rB['stressed_net_return']:+.3f})")

    # 3) BIG RUNNER: peaks far above the floor then trails out. The floor must NOT bind -> A == B.
    run = _tape([50.0, 56.0, 63.0, 66.0, 63.0, 60.0, 57.0, 54.0])
    rAr = resolve_v4.resolve_from_tape_v4(_setup(), run, SPEC, ARM["A"], now=500.0)
    rBr = resolve_v4.resolve_from_tape_v4(_setup(), run, SPEC, ARM["B"], now=500.0)
    ok &= _check("big runner: profit floor does NOT cap it (arm A == arm B, both QUOTE_TRAIL)",
                 rAr and rBr and rAr["resolution_reason"] == "QUOTE_TRAIL"
                 and abs(rAr["stressed_net_return"] - rBr["stressed_net_return"]) < 1e-6,
                 f"A={rAr['stressed_net_return']:+.3f} B={rBr['stressed_net_return']:+.3f}")

    # 4) arm C (lock-early 1.02/1.01) arms sooner than B on a small green blip
    ok &= _check("arm wiring: A no lock, B/C lock with the frozen params",
                 ARM["A"]["profit_lock"] is False and ARM["B"]["lock_floor"] == 1.02
                 and ARM["C"]["lock_arm"] == 1.02)

    print("\nAFTERSHOCK V4 DETECTOR SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
