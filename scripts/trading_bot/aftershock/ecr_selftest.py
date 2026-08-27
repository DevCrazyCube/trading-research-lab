#!/usr/bin/env python3
"""Offline selftest for the ECR engine. No network. Verifies the pinned offsets against the known launch
state, the coverage-ratio gate, and the curve-exact round trip (winner / loser / migrated / drained).

    python -m scripts.trading_bot.aftershock.ecr_selftest
"""
from __future__ import annotations

from . import ecr


def _line(v_sol, v_tokens, ts, pool="pump"):
    return {"v_sol": v_sol, "v_tokens": v_tokens, "ts": ts, "pool": pool}


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def main() -> int:
    ok = True

    # 1. The pinned offsets reproduce the known pump.fun launch reserves exactly.
    launch = ecr.reserves_from_tape(_line(30.0, 1_073_000_000.0, 1.0))
    ok &= _check("launch real_quote == 0 (virtual 30 SOL - 30 SOL offset)", launch["real_quote"] == 0,
                 str(launch["real_quote"]))
    ok &= _check("launch real_token == 793_100_000_000_000 (verified CreateEvent value)",
                 launch["real_token"] == 793_100_000_000_000, str(launch["real_token"]))
    ok &= _check("launch quote_mint is native SOL & not complete",
                 launch["quote_mint"] == ecr.NATIVE_QUOTE_MINT and launch["complete"] is False)

    # 2. coverage_ratio = real external SOL / q. At v_sol=50 -> real 20 SOL; q=0.1 -> 200x.
    cov = ecr.coverage_ratio(_line(50.0, 643_800_000.0, 2.0), 0.1)
    ok &= _check("coverage_ratio(v_sol=50, q=0.1) == 200x (20 real SOL / 0.1)", abs(cov - 200.0) < 1e-6,
                 f"{cov:.3f}")

    # Curve invariant k = 30 * 1_073_000_000 = 32_190_000_000 (whole units); v_tokens = k / v_sol.
    K = 30.0 * 1_073_000_000.0
    entry = _line(50.0, K / 50.0, 100.0)          # entered when 20 real SOL in the curve

    # 3. WINNER: exit at higher price (more real SOL) -> positive stressed return.
    win = ecr.ecr_roundtrip(entry, _line(80.0, K / 80.0, 200.0), 0.1)
    ok &= _check("winner: exit at higher price -> positive stressed return, exitable",
                 (not win["unexitable"]) and win["stressed_net_return"] > 0,
                 f"r={win['stressed_net_return']:.4f}")

    # 4. LOSER-BUT-EXITABLE: exit slightly below entry, curve still holds real SOL -> small negative.
    los = ecr.ecr_roundtrip(entry, _line(45.0, K / 45.0, 200.0), 0.1)
    ok &= _check("loser-but-exitable: negative but NOT full loss (> -1.0)",
                 (not los["unexitable"]) and -1.0 < los["stressed_net_return"] < 0,
                 f"r={los['stressed_net_return']:.4f}")

    # 5. MIGRATED: exit pool != pump -> unsellable -> full loss.
    mig = ecr.ecr_roundtrip(entry, _line(80.0, K / 80.0, 200.0, pool="pumpswap"), 0.1)
    ok &= _check("migrated pool at exit -> unexitable, stressed return == -1.0",
                 mig["unexitable"] and mig["stressed_net_return"] == -1.0)

    # 6. DRAINED: exit reserves almost back to launch (real_quote ~0) -> curve cannot pay -> full loss.
    drn = ecr.ecr_roundtrip(_line(80.0, K / 80.0, 100.0), _line(30.02, K / 30.02, 200.0), 0.5)
    ok &= _check("drained curve (real SOL ~0) cannot pay position -> unexitable, -1.0",
                 drn["unexitable"] and drn["stressed_net_return"] == -1.0,
                 f"r={drn['stressed_net_return']}")

    # 7. Loss floor: stressed_net_return never below -1.0.
    ok &= _check("stressed return is floored at -1.0 across all cases",
                 all(x["stressed_net_return"] >= -1.0 for x in (win, los, mig, drn)))

    print("\nECR SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
