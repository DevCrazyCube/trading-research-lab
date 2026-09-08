#!/usr/bin/env python3
"""Offline selftest for AFTERSHOCK V5 (SCALE-OUT). Asserts: entry fires (V3 entry reused); on a SPIKE-
THEN-GAP trade the scale-out arm banks a gap-proof gain and BEATS the plain trail; on a clean RUNNER the
scale-out gives up some upside (plain trail >= scale-out) — the honest tradeoff; and a trade that never
reaches tp_level resolves identically to the plain trail. No network.

    python -m scripts.trading_bot.aftershock.detector_v5_selftest
"""
from __future__ import annotations

from .detector_selftest import _Curve
from .detector_v2_selftest import _build as _build_v2
from .detector_v3 import DetectorV3Config, _MintDetectorV3
from .frozen import frozen_spec
from .resolve_v2 import _exit_quote_value
from . import resolve_v5

SPEC = frozen_spec("AFTERSHOCK_V5")
ARM = {a["arm"]: a for a in SPEC["arms"]}
K = 30.0 * 1_073_000_000.0


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def _setup(t0=100.0):
    er = {"v_sol": 47.0, "v_tokens": K / 47.0, "pool": "pump"}
    return {"q_sol": 0.1, "cluster_wallets": ["DEV"], "t_entry": t0, "entry_reserves": er,
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

    # 1) entry still fires through the V5 (=V3) detector
    cfg = DetectorV3Config.from_spec(SPEC, veto_strict=False)
    det = _MintDetectorV3(cfg=cfg)
    fires = [r for ln in _build_v2(recover_to=46.5) if (r := det.on_line(ln)) is not None]
    ok &= _check("net-replacement -> V5 entry FIRE (PASS)", len([f for f in fires if not f["control"]]) == 1)

    # confirm the spike reaches tp_level 1.50 so leg-1 can fire
    er = _setup()["entry_reserves"]
    spike_q = _exit_quote_value(er, {"v_sol": 60.0, "v_tokens": K / 60.0, "pool": "pump"}, 0.1)

    # 2) SPIKE-THEN-GAP: quote spikes past +50% then a single tick craters it. Scale-out (B) banks half
    #    at +50%; plain trail (A) round-trips to a loss.
    gap = _tape([52.0, 60.0, 44.0, 43.0])
    rA = resolve_v5.resolve_from_tape_v5(_setup(), gap, SPEC, ARM["A"], now=500.0)
    rB = resolve_v5.resolve_from_tape_v5(_setup(), gap, SPEC, ARM["B"], now=500.0)
    ok &= _check("spike-then-gap: scale-out arm B BEATS plain trail A (banks the peak)",
                 spike_q >= 1.50 and rB and rA and rB["stressed_net_return"] > rA["stressed_net_return"],
                 f"spike_q={spike_q:.2f} A={rA['stressed_net_return']:+.3f} B={rB['stressed_net_return']:+.3f}({rB['resolution_reason']})")

    # 3) MONSTER RUNNER (peak >> tp): the full position riding the trail catches the moonshot, while the
    #    scale-out banked half at +50% and missed it -> plain trail A > scale-out B (the honest cost).
    run = _tape([55.0, 70.0, 90.0, 115.0, 140.0, 125.0, 110.0])
    rAr = resolve_v5.resolve_from_tape_v5(_setup(), run, SPEC, ARM["A"], now=500.0)
    rBr = resolve_v5.resolve_from_tape_v5(_setup(), run, SPEC, ARM["B"], now=500.0)
    ok &= _check("monster runner: plain trail A > scale-out B (scale-out caps the moonshot)",
                 rAr and rBr and rAr["stressed_net_return"] > rBr["stressed_net_return"],
                 f"A={rAr['stressed_net_return']:+.3f} B={rBr['stressed_net_return']:+.3f}")

    # 4) tp never reached -> V5 arm B == plain trail arm A
    modest = _tape([48.0, 49.0, 49.5, 48.0, 46.0, 43.0])   # never reaches +50%, but trail fires
    ra = resolve_v5.resolve_from_tape_v5(_setup(), modest, SPEC, ARM["A"], now=500.0)
    rb = resolve_v5.resolve_from_tape_v5(_setup(), modest, SPEC, ARM["B"], now=500.0)
    ok &= _check("tp never hit -> scale-out == plain trail",
                 ra and rb and abs(ra["stressed_net_return"] - rb["stressed_net_return"]) < 1e-9,
                 f"A={ra['stressed_net_return']:+.3f} B={rb['stressed_net_return']:+.3f}")

    ok &= _check("arm wiring: A no scale-out, B tp1.50/frac0.5, C tp2.00/frac0.5",
                 ARM["A"]["scale_out"] is False and ARM["B"]["tp_level"] == 1.50
                 and ARM["C"]["tp_level"] == 2.00 and ARM["B"]["scale_frac"] == 0.5)

    # 5) BOTH-legs cost: a scaled trade charges the SECOND sell's exit gas (review fix). The recorded R is
    #    ~0.2% below the naive blend, and the record carries the gas charge.
    rb2 = resolve_v5.resolve_from_tape_v5(_setup(), gap, SPEC, ARM["B"], now=500.0)
    naive = 0.5 * rb2["scale_out_leg1_R"] + 0.5 * rb2["runner_leg2_R"]
    ok &= _check("scale-out charges the 2nd leg's exit gas (BOTH legs costed)",
                 rb2["second_leg_exit_gas"] > 0 and abs((naive - rb2["stressed_net_return"]) - rb2["second_leg_exit_gas"]) < 1e-6,
                 f"gas={rb2['second_leg_exit_gas']:.4f} naive-blend={naive:+.4f} recorded={rb2['stressed_net_return']:+.4f}")

    print("\nAFTERSHOCK V5 DETECTOR SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
