#!/usr/bin/env python3
"""MEME ARENA — aggregate selftest for the shared honesty spine. Runs every core module's invariants and
asserts the cross-module honesty contract. Hermetic (no network, no DB). Run:

    python -m scripts.trading_bot.memebot.arena.selftest
"""
from __future__ import annotations

import pathlib
import tempfile

from . import fill as F
from . import scorer as SC
from . import exit_engine as EX
from .chainledger import ChainLedger


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  [ok] {msg}")


def main() -> int:
    print("MEME ARENA selftest — honesty spine")

    # 1. fill: honest causal fill is never better than the marginal comparator; reserve cap bites.
    c = F.causal_fill_cp((30.0, 1e9), (60.0, 0.5e9), size_sol=0.5)
    check(c.net_return < c.net_marginal, "causal fill honest <= marginal (impact is charged)")
    drained = F.causal_fill_cp((30.0, 1e9), (60.0, 0.5e9), size_sol=0.5, real_sol_withdrawable_at_exit=0.05)
    check(drained.real_reserve_bound_hit and drained.net_return < c.net_return,
          "a drained curve caps the exit below the invariant (would catch a fake pump)")
    check(abs(F.honest_fill_snapshot(1.0, 2.0).net_return
              - (2.0 * (1 - F.TOLL_BUY) * (1 - F.TOLL_SELL) - 1)) < 1e-12,
          "snapshot toll is multiplicative two-leg, not gross-0.03")

    # 2. exit: winner trails out positive; a rug is a total loss (F1, both bases).
    p = EX.Position("m", "a", "snapshot", entry_price=1.0, opened_ts=0.0)
    for mark, t in [(1.4, 60), (1.4 * 0.8, 120)]:
        r = EX.exit_signal(p, mark, t)
        if r:
            break
    check(r == "TRAIL" and EX.resolve(p, r, exit_mark=1.4 * 0.8, now_ts=120)["net_return"] > 0,
          "convex trail exits a winner positive")
    check(abs(EX.resolve(EX.Position("m", "a", "snapshot", entry_price=1.0, opened_ts=0.0),
                         "RUG_UNPRICED", now_ts=1)["net_return"] + 1.0) < 1e-9,
          "F1: a rug/unpriced position resolves as a total loss, never a skip")

    # 3. scorer: cluster bootstrap decides PASS/KILL on the frozen rule.
    check(SC.decide([0.05] * 120, [("m%d" % (i % 8), "d") for i in range(120)], 120)["verdict"] == "PASS",
          "scorer PASSes a clean positive book (cluster bootstrap CI-lo > 0)")
    check(SC.decide([-0.1] * 120, [("m", "d")] * 120, 120)["verdict"] == "KILL",
          "scorer KILLs a negative book (CI-hi < 0)")

    # 4. ledger: chain verifies, tamper breaks it, drift refuses to resolve.
    with tempfile.TemporaryDirectory() as d:
        L = ChainLedger(pathlib.Path(d) / "l.jsonl", "a", "code", "pre", "spec")
        L.append_resolved({"mint": "m1", "net_return": 0.1})
        check(L.verify(), "hash-chained ledger verifies")
        drifted = ChainLedger(L.path, "a", "CODE2", "pre", "spec")
        try:
            drifted.append_resolved({"mint": "m2", "net_return": 0.0})
            raise AssertionError("drift should refuse")
        except RuntimeError:
            check(True, "ledger refuses to resolve when code/prereg drifts from genesis")

    print("MEME ARENA selftest: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
