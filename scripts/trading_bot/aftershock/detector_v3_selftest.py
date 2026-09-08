#!/usr/bin/env python3
"""Offline selftest for AFTERSHOCK V3 (QUOTE-HARVEST). Asserts: entry fires on net-replacement with the
break-even condition present (veto removed); the break-even gate rejects an unsellable/doomed entry; and
the three exit modes harvest in the right order on a rising-then-falling quote (rollover >= ratchet >=
plain trail, i.e. C exits nearer the peak). No network.

    python -m scripts.trading_bot.aftershock.detector_v3_selftest
"""
from __future__ import annotations

from .detector_selftest import _Curve
from .detector_v2_selftest import _build as _build_v2   # same window geometry; reused for the entry tape
from .detector_v3 import DetectorV3Config, _MintDetectorV3
from .frozen import frozen_spec
from .resolve_v2 import _exit_quote_value
from . import resolve_v3

SPEC = frozen_spec("AFTERSHOCK_V3")
ARM = {a["arm"]: a for a in SPEC["arms"]}
K = 30.0 * 1_073_000_000.0


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def _play_v3(lines):
    cfg = DetectorV3Config.from_spec(SPEC, veto_strict=False)
    det = _MintDetectorV3(cfg=cfg)
    fires = []
    for ln in lines:
        r = det.on_line(ln)
        if r is not None:
            fires.append(r)
    return fires


def main() -> int:
    ok = True

    # 1) entry: net-replacement absorption fires PASS through the V3 detector; break-even condition present
    fires = _play_v3(_build_v2(recover_to=46.5))
    passed = [f for f in fires if not f["control"]]
    ok &= _check("net-replacement -> V3 entry FIRE (PASS)", len(passed) == 1,
                 f"fires={len(fires)} pass={len(passed)}")
    if passed:
        c = passed[0]["conditions"]
        ok &= _check("break-even condition present + ok, veto not applied",
                     c.get("breakeven", {}).get("ok") is True and c.get("breakeven", {}).get("entry_quote", 0) > 0.9
                     and c.get("entry_veto", {}).get("strict") is False,
                     str(c.get("breakeven")))

    # 2) break-even gate LOGIC: an unsellable (migrated pool) entry quote is 0 < min -> would reject
    migrated = {"v_sol": 47.0, "v_tokens": K / 47.0, "pool": "pumpswap"}
    q0 = _exit_quote_value(migrated, migrated, 0.1)
    ok &= _check("break-even: unsellable/migrated entry quote == 0 (< 0.90 floor)", q0 == 0.0, f"quote={q0}")
    healthy = {"v_sol": 47.0, "v_tokens": K / 47.0, "pool": "pump"}
    qh = _exit_quote_value(healthy, healthy, 0.1)
    ok &= _check("break-even: healthy entry quote clears floor", qh >= SPEC["detector"]["breakeven_min_quote"],
                 f"quote={round(qh,4)}")

    # 3) exit modes on a rising-then-falling quote. Entry v_sol=47; quote peaks then declines.
    entry_reserves = {"v_sol": 47.0, "v_tokens": K / 47.0, "pool": "pump"}
    setup = {"q_sol": 0.1, "cluster_wallets": ["DEV"], "t_entry": 100.0, "entry_reserves": entry_reserves,
             "entry_price_usd": 1.0, "deployer": "DEV", "toll_per_side": SPEC["toll_per_side"],
             "stop_frac": SPEC["stop_frac"], "target_frac": SPEC["target_frac"], "size_sol": 0.1,
             "setup_sha256": "t", "pool_address": "MINT", "control": False}
    cc = _Curve(); cc.v_sol = 47.0; cc.v_tokens = K / 47.0
    tp = []
    t = 101.0
    for v in [50.0, 55.0, 60.0, 64.0, 62.0, 60.0, 58.0, 55.0, 52.0, 49.0, 46.0]:  # rise to 64 peak, then fall
        tp.append(cc.trade(t, "B" if v >= cc.v_sol else "S", "buy" if v >= cc.v_sol else "sell", v)); t += 1.0
    recs = {}
    for a in ("A", "B", "C"):
        recs[a] = resolve_v3.resolve_from_tape_v3(setup, tp, SPEC, ARM[a], now=500.0)
    for a in ("A", "B", "C"):
        ok &= _check(f"arm {a} resolves", recs[a] is not None,
                     str(recs[a] and recs[a].get("resolution_reason")))
    if all(recs.values()):
        rA = recs["A"]["stressed_net_return"]; rB = recs["B"]["stressed_net_return"]; rC = recs["C"]["stressed_net_return"]
        ok &= _check("harvest order: rollover(C) >= ratchet(B) >= trail(A)  (C harvests nearer the peak)",
                     rC >= rB - 1e-6 and rB >= rA - 1e-6,
                     f"A={rA:+.3f}({recs['A']['resolution_reason']}) B={rB:+.3f}({recs['B']['resolution_reason']}) C={rC:+.3f}({recs['C']['resolution_reason']})")

    # 4) REGRESSION (review-confirmed arming bug): a MODEST peak between (1+arm_profit)*entry_quote and the
    #    absolute (1+arm_profit) must still ARM the ratchet. Under the old absolute-1.10 test it would not,
    #    and arm B would fall back to the 12% trail. entry_quote~0.948 -> spec arms at ~1.043; peak here ~1.095.
    cc2 = _Curve(); cc2.v_sol = 47.0; cc2.v_tokens = K / 47.0
    tp2 = []
    t = 201.0
    for v in [48.0, 49.0, 50.0, 50.5, 50.0, 49.5, 49.0, 48.5, 48.0, 47.5, 47.0, 46.5]:  # peak ~1.095, then fall
        tp2.append(cc2.trade(t, "B" if v >= cc2.v_sol else "S", "buy" if v >= cc2.v_sol else "sell", v)); t += 1.0
    setup2 = dict(setup); setup2["t_entry"] = 201.0
    peak_q = max(_exit_quote_value(entry_reserves, ln, 0.1) for ln in tp2)
    recA = resolve_v3.resolve_from_tape_v3(setup2, tp2, SPEC, ARM["A"], now=600.0)
    recB = resolve_v3.resolve_from_tape_v3(setup2, tp2, SPEC, ARM["B"], now=600.0)
    ok &= _check("modest peak is in the bug window (arm_profit*entry_quote < peak < 1.10)",
                 1.0428 < peak_q < 1.10, f"peak_quote={peak_q:.4f}")
    ok &= _check("modest-peak ratchet ARMS (RATCHET_TRAIL, not the 12% base trail)",
                 recB and recB["resolution_reason"] == "RATCHET_TRAIL"
                 and recB["stressed_net_return"] > recA["stressed_net_return"],
                 f"A={recA['resolution_reason']}({recA['stressed_net_return']:+.3f}) B={recB['resolution_reason']}({recB['stressed_net_return']:+.3f})")

    print("\nAFTERSHOCK V3 DETECTOR SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
