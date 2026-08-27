#!/usr/bin/env python3
"""End-to-end AFTERSHOCK selftest: frozen_spec loads + verifies; a real detector FIRE freezes into a
hash-verifiable entry; the entry resolves on the tape; the resolution scores. No network, no ledger writes.

    python -m scripts.trading_bot.aftershock.integration_selftest
"""
from __future__ import annotations

from . import frozen, entry, resolve, scoring
from .detector import Detector, DetectorConfig
from .frozen import canonical_sha256

K = 30.0 * 1_073_000_000.0


class _Curve:
    def __init__(self, mint="MINT"):
        self.mint, self.v_sol, self.v_tokens = mint, 30.0, K / 30.0

    def trade(self, ts, trader, side, new_v_sol):
        tok = abs(K / new_v_sol - self.v_tokens)
        sol = abs(new_v_sol - self.v_sol)
        self.v_sol, self.v_tokens = new_v_sol, K / new_v_sol
        return {"ts": ts, "mint": self.mint, "trader": trader, "side": side, "sol_amount": sol,
                "token_amount": tok, "v_sol": new_v_sol, "v_tokens": K / new_v_sol, "pool": "pump"}


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def main() -> int:
    ok = True

    # 1. frozen_spec loads and the prereg hash verifies.
    try:
        spec = frozen.frozen_spec("AFTERSHOCK")
        ok &= _check("frozen_spec loads + prereg sha256 verifies", True,
                     f"horizon_slots={spec['exit']['max_hold_slots']} q={spec['detector']['q_sol']}")
    except Exception as e:  # noqa: BLE001
        return 1 if not _check("frozen_spec loads", False, str(e)) else 1

    # 2. Drive a real absorbing shock through the detector -> FIRE.
    det = Detector(DetectorConfig.from_spec(spec["detector"]))
    c = _Curve()
    lines = [c.trade(0.0, "DEV", "buy", 36.0), c.trade(2.0, "E1", "buy", 40.0),
             c.trade(4.0, "E2", "buy", 43.0), c.trade(6.0, "E3", "buy", 45.0),
             c.trade(8.0, "X1", "buy", 45.5), c.trade(10.0, "X2", "buy", 46.0),
             c.trade(30.0, "DEV", "sell", 42.0),
             c.trade(32.0, "N1", "buy", 44.0), c.trade(38.0, "N2", "buy", 46.0),
             c.trade(44.0, "N3", "buy", 47.0), c.trade(50.0, "N1", "buy", 47.2),
             c.trade(52.0, "N2", "buy", 47.4), c.trade(55.0, "X3", "buy", 47.5)]
    fire = None
    for ln in lines:
        r = det.on_line(ln)
        if r is not None and not r["control"]:
            fire = r
    ok &= _check("detector produced a PASS fire from the absorbing shock", fire is not None)
    if fire is None:
        print("\nINTEGRATION SELFTEST: FAIL")
        return 1

    # 3. Freeze the entry (no ledger write) and verify the fingerprint covers the reserves.
    rec = entry.build_entry(fire, spec)
    ok &= _check("entry hash verifies (canonical_sha256 reproduces setup_sha256)",
                 canonical_sha256(rec) == rec["setup_sha256"])
    ok &= _check("entry froze the reserves + cluster BEFORE outcome",
                 rec["entry_reserves"]["v_sol"] == fire["entry_line"]["v_sol"]
                 and rec["deployer"] == "DEV" and rec["screen_verdict"] == "PASS")
    # tamper -> hash breaks
    tampered = dict(rec, entry_reserves={"v_sol": 999, "v_tokens": 1, "pool": "pump"})
    ok &= _check("tampering the frozen reserves breaks the hash",
                 canonical_sha256(tampered) != rec["setup_sha256"])

    # 4. Resolve on a post-entry tape that pumps then gives back 12% -> TRAIL_STOP winner.
    t_e = rec["t_entry"]
    post = [c.trade(t_e + 1, "N4", "buy", 90.0), c.trade(t_e + 2, "N5", "sell", 84.3)]
    res = resolve.resolve_from_tape(rec, post, spec)
    ok &= _check("resolves to a priced record with a stressed return",
                 res is not None and "stressed_net_return" in res and res["realized_r"] is not None,
                 (f"{res['resolution_reason']} sr={res['stressed_net_return']}" if res else "None"))

    # 5. Score the single resolution (below N_min -> NO VERDICT, but the body computes).
    rep = scoring.score(spec, [res])
    body = rep.get("inputs_that_are_not_results", rep)
    ok &= _check("scoring produces pot-growth G + dump rate", "log_growth_G" in body,
                 f"G={body.get('log_growth_G')} dump={body.get('dump',{}).get('dump_rate')}")

    print("\nINTEGRATION SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
