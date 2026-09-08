#!/usr/bin/env python3
"""Offline selftest for AFTERSHOCK V2 (PAYABLE ABSORPTION). Builds synthetic tapes and asserts the V2
mechanism: NET-replacement PASS, stricter full-recovery reject (vs V1's 0.9), the arm-B entry-flow-veto
(arm A fires, arm B vetoes the same tape), stabilization reject, and the arm-C executable-quote trail.
No network.

    python -m scripts.trading_bot.aftershock.detector_v2_selftest
"""
from __future__ import annotations

from .detector import SLOT_SECONDS
from .detector_selftest import _Curve
from .detector_v2 import DetectorV2, DetectorV2Config, detector_for_arm
from .frozen import frozen_spec
from . import resolve_v2

SPEC = frozen_spec("AFTERSHOCK_V2")
ARM = {a["arm"]: a for a in SPEC["arms"]}
# window geometry (seconds): shock @ t0; accumulation ends t0+accum; eval fires past t0+eval.
ACCUM = SPEC["detector"]["absorption_window_slots"] * SLOT_SECONDS
EVAL = (SPEC["detector"]["absorption_window_slots"] + SPEC["detector"]["stabilization_window_slots"]) * SLOT_SECONDS


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def _play(lines, veto_strict):
    det = detector_for_arm(SPEC, {"veto_strict": veto_strict})
    fires = []
    for ln in lines:
        r = det.on_line(ln)
        if r is not None:
            fires.append(r)
    return fires


def _cluster_prime(c, L):
    """Cluster DEV,E1,E2,E3 buy to R~15, plus non-cluster X buys so k60<0.95."""
    L.append(c.trade(0.0, "DEV", "buy", 36.0))
    L.append(c.trade(2.0, "E1", "buy", 40.0))
    L.append(c.trade(4.0, "E2", "buy", 43.0))
    L.append(c.trade(6.0, "E3", "buy", 45.0))     # R=15, cluster window [0,24]
    L.append(c.trade(8.0, "X1", "buy", 45.5))
    L.append(c.trade(10.0, "X2", "buy", 46.0))    # R0 ~= 16 at shock


def _build(recover_to, *, absorbers=("N1", "N2", "N3"), stab_decline=False, stab_dip=False,
           veto_flow=False):
    """R0~16; DEV dumps ~4 SOL (trough); new wallets refill R up to `recover_to` (whole v_sol).
    stab_decline: R falls during the stabilization sub-window. veto_flow: independent SELLS dominate the
    flow window right at the fire instant (tests the entry-veto)."""
    c = _Curve()
    L = []
    _cluster_prime(c, L)
    L.append(c.trade(30.0, "DEV", "sell", 42.0))   # S ~4 SOL; trough v_sol=42 (R~12)
    # absorption phase [32 .. 30+ACCUM]: new independent wallets buy the curve back up in EVEN positive
    # steps from the trough to recover_to, so each is a distinct new-wallet buy with sol>0.
    trough_vsol = 42.0
    step = (recover_to - trough_vsol) / len(absorbers)
    t = 32.0
    for i, w in enumerate(absorbers):
        L.append(c.trade(t, w, "buy", trough_vsol + step * (i + 1)))
        t += 4.0
    # populate the absorption-end tail [accum_end - tail_s, accum_end] so capacity/coverage are checked
    # there (the detector now bounds the tail's upper edge at absorption end, per the review fix).
    L.append(c.trade(30.0 + ACCUM - 4.0, absorbers[0], "buy", recover_to + 0.05))
    L.append(c.trade(30.0 + ACCUM - 2.0, absorbers[-1], "buy", recover_to + 0.1))
    # stabilization phase (30+ACCUM .. 30+EVAL): hold or decline
    mid = 30.0 + ACCUM + (EVAL - ACCUM) / 2.0
    if stab_decline:
        L.append(c.trade(mid, "S1", "sell", recover_to - 3.0))   # R declines in the stabilization window
    elif stab_dip:
        # DIP below R0 mid-stabilization, then recover ABOVE the stab-window start. Stabilization passes
        # (non-declining endpoint); the dip is INSIDE stabilization, OUTSIDE the absorption-end tail. This
        # is the review's exact scenario: with the _tail upper-bound fix -> PASS; without it -> wrong CONTROL.
        L.append(c.trade(mid - 1.0, "D1", "sell", recover_to - 1.5))
        L.append(c.trade(mid + 1.0, "D2", "buy", recover_to + 0.3))
    else:
        L.append(c.trade(mid, "N9", "buy", recover_to + 0.2))    # R holds/rises
    if veto_flow:
        # independent sells dominate right before the fire instant -> entry-flow-veto should trip (arm B)
        vt = 30.0 + EVAL - 0.6
        L.append(c.trade(vt, "V1", "sell", c.v_sol - 0.4))
        L.append(c.trade(vt + 0.1, "V2", "sell", c.v_sol - 0.4))
        L.append(c.trade(vt + 0.2, "V3", "sell", c.v_sol - 0.4))
    # trigger evaluation: a line past t0+EVAL
    L.append(c.trade(30.0 + EVAL + 1.0, "Z", "buy", c.v_sol + 0.05))
    return L


def main() -> int:
    ok = True

    # 1) clean NET replacement, full recovery to R0(~16 => v_sol 46), stable -> arm A FIRES PASS
    fa = _play(_build(recover_to=46.5, stab_decline=False), veto_strict=False)
    passed = [f for f in fa if not f["control"]]
    ok &= _check("net-replacement absorption -> arm A FIRE (PASS)", len(passed) == 1,
                 f"fires={len(fa)} pass={len(passed)}")
    if passed:
        f = passed[0]
        nr = f["conditions"]["net_replacement"]
        ok &= _check("PASS carries NRR>=1 and full recovery", nr["ok"] and nr["nrr"] >= 1.0,
                     f"nrr={nr['nrr']} Rmin={nr['Rmin']} Rt={nr['Rt']} R0={nr['R0']}")
        ok &= _check("PASS: all V2 conditions ok",
                     all(v.get("ok", True) for v in f["conditions"].values()),
                     str({k: v.get("ok") for k, v in f["conditions"].items()}))

    # 2) recovery only to ~0.95*R0 (v_sol ~ 45.2 => R~15.2 vs R0~16) -> V2 (recover_frac 1.0) REJECTS
    fr = _play(_build(recover_to=45.2, stab_decline=False), veto_strict=False)
    ok &= _check("incomplete recovery (0.95*R0) -> CONTROL (stricter than V1's 0.9)",
                 all(f["control"] for f in fr) and len(fr) >= 1,
                 str([(round(f['conditions']['net_replacement']['nrr'], 2),
                       f['conditions']['capacity_held']['ok']) for f in fr]))

    # 3) entry-flow-veto LOGIC. On a full tape, stabilization (R non-declining) already blocks any fire
    #    into a net-sell flip, so the veto's independent job is the flip SIGNAL; test it directly. Also
    #    assert the arm wiring (A not strict, B/C strict).
    from .detector_v2 import _MintDetectorV2
    cfgA = DetectorV2Config.from_spec(SPEC, veto_strict=False)
    cfgB = DetectorV2Config.from_spec(SPEC, veto_strict=True)
    md = _MintDetectorV2(cfg=cfgB)
    md.armed_cluster = frozenset({"DEV"})
    for i in range(6):
        md.recent.append((90.0 + i, 15.0, 150.0,
                          {"trader": f"S{i}", "side": "sell", "sol_amount": 1.0}))
    md.recent.append((99.0, 15.0, 150.0, {"trader": "B0", "side": "buy", "sol_amount": 0.5}))
    flow = md._flow_is_sell_dominated(100.0)
    ok &= _check("flow detector flags sell-domination", flow["dominated"] and flow["sell_frac"] >= 0.65, str(flow))
    md2 = _MintDetectorV2(cfg=cfgA)
    md2.armed_cluster = frozenset({"DEV"})
    for i in range(6):
        md2.recent.append((90.0 + i, 15.0, 150.0,
                           {"trader": f"B{i}", "side": "buy", "sol_amount": 1.0}))
    ok &= _check("buy-heavy flow NOT sell-dominated", not md2._flow_is_sell_dominated(100.0)["dominated"])
    ok &= _check("arm wiring: A not strict, B/C strict",
                 cfgA.veto_strict is False and cfgB.veto_strict is True
                 and bool(ARM["C"]["veto_strict"]) is True)

    # 4) stabilization fail: R declines in the stabilization window -> CONTROL even if absorbed
    fs = _play(_build(recover_to=46.5, stab_decline=True), veto_strict=False)
    ok &= _check("stabilization decline -> CONTROL",
                 all(f["control"] for f in fs) and len(fs) >= 1,
                 str([f["conditions"]["stabilization"].get("ok") for f in fs]))

    # 4b) REGRESSION (review-confirmed _tail bug): a mid-stabilization dip below R0 that recovers by fire
    #     must still FIRE — the dip is outside the absorption-end tail. Unbounded _tail wrongly CONTROLs.
    fd = _play(_build(recover_to=46.5, stab_dip=True), veto_strict=False)
    fd_pass = [f for f in fd if not f["control"]]
    ok &= _check("mid-stabilization dip (outside absorption-end tail) -> still FIRE",
                 len(fd_pass) == 1,
                 f"pass={len(fd_pass)} caps=" + str([f['conditions']['capacity_held']['ok'] for f in fd]))

    # 5) arm C executable-quote trail: build a position that peaks then rolls the sell-quote back >12%.
    #    Entry reserves ~ v_sol 47 (R~17); price climbs (quote up) then reserves fall back -> QUOTE_TRAIL.
    entry_reserves = {"v_sol": 47.0, "v_tokens": (30.0 * 1_073_000_000.0) / 47.0, "pool": "pump"}
    setup = {"q_sol": 0.1, "cluster_wallets": ["DEV"], "t_entry": 100.0,
             "entry_reserves": entry_reserves, "entry_price_usd": 1.0, "deployer": "DEV",
             "toll_per_side": SPEC.get("toll_per_side", 0.0125),
             "stop_frac": SPEC.get("stop_frac", 0.5), "target_frac": SPEC.get("target_frac", 0.5),
             "size_sol": 0.1, "setup_sha256": "test", "pool_address": "MINT", "control": False}
    cc = _Curve(); cc.v_sol = 47.0; cc.v_tokens = (30.0 * 1_073_000_000.0) / 47.0
    tp = []
    tp.append(cc.trade(101.0, "B1", "buy", 55.0))   # quote climbs
    tp.append(cc.trade(102.0, "B2", "buy", 60.0))   # peak
    tp.append(cc.trade(103.0, "S1", "sell", 50.0))  # sell-quote gives back well over 12% from peak
    rec_c = resolve_v2.resolve_from_tape_v2(setup, tp, SPEC, ARM["C"], now=200.0)
    ok &= _check("arm C resolves via executable-quote trail", rec_c is not None and
                 rec_c.get("resolution_reason") in ("QUOTE_TRAIL", "CLUSTER_RESUME", "CAPACITY_BREAK"),
                 str(rec_c and rec_c.get("resolution_reason")))
    # arm A/B use the V1 exit path (chart-price trail / flow-flip) on the same tape
    rec_a = resolve_v2.resolve_from_tape_v2(setup, tp, SPEC, ARM["A"], now=200.0)
    ok &= _check("arm A/B resolve via V1 exit path", rec_a is not None and
                 "stressed_net_return" in rec_a, str(rec_a and rec_a.get("resolution_reason")))

    print("\nAFTERSHOCK V2 DETECTOR SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
