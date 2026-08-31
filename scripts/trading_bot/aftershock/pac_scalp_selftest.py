#!/usr/bin/env python3
"""Controls for the PAC portfolio convexity scalper: momentum gate, convex exit, multi-position book."""
from __future__ import annotations

import hashlib

from .execution import ReserveState
from . import pac_scalp_detector as detector
from . import pac_scalp_policy as policy
from . import pac_scalp_runner as runner
from . import pac_v22_feed as feed


CHECKS = 0


def check(cond: bool, label: str) -> None:
    global CHECKS
    if not cond:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def _state(real_quote: int) -> ReserveState:
    return ReserveState(30_000_000_000 + real_quote, 1_000_000_000_000_000, real_quote,
                        720_100_000_000_000, False)


def _ev(idx: int, pre_q: int, post_q: int, *, base: int, trader: str, side: str) -> feed.ClockedEvent:
    src = base + idx * 500_000_000
    return feed.ClockedEvent(
        event_id=hashlib.sha256(f"e{idx}".encode()).hexdigest(), collector_epoch="ep",
        mint="mintA", trader=trader, signature=f"s{idx}", slot=idx, side=side,
        source_received_unix_nanos=src, materialized_unix_nanos=src + 10,
        runner_seen_unix_nanos=src + 20, pre_state=_state(pre_q), post_state=_state(post_q))


def main() -> int:
    base = 1_700_000_000_000_000_000
    # --- momentum detector ---
    rising = (_ev(0, 1_000_000_000, 1_100_000_000, base=base, trader="b1", side="buy"),
              _ev(1, 1_100_000_000, 1_250_000_000, base=base, trader="b2", side="buy"),
              _ev(2, 1_250_000_000, 1_400_000_000, base=base, trader="b3", side="buy"))
    now = base + 2 * 500_000_000 + 1
    sig = detector.qualify(rising, now_unix_nanos=now, quote_input_lamports=50_000_000)
    check(sig is not None and sig.buyer_breadth >= 3, "momentum: rising curve + 3 buyers + buy>sell qualifies")

    falling = (_ev(0, 1_400_000_000, 1_300_000_000, base=base, trader="s1", side="sell"),
               _ev(1, 1_300_000_000, 1_200_000_000, base=base, trader="s2", side="sell"),
               _ev(2, 1_200_000_000, 1_100_000_000, base=base, trader="s3", side="sell"))
    check(detector.qualify(falling, now_unix_nanos=now, quote_input_lamports=50_000_000) is None,
          "momentum: a falling/net-sell curve is refused")

    two_buyers = (_ev(0, 1_000_000_000, 1_100_000_000, base=base, trader="b1", side="buy"),
                  _ev(1, 1_100_000_000, 1_200_000_000, base=base, trader="b1", side="buy"),
                  _ev(2, 1_200_000_000, 1_300_000_000, base=base, trader="b2", side="buy"))
    check(detector.qualify(two_buyers, now_unix_nanos=now, quote_input_lamports=50_000_000) is None,
          "momentum: fewer than 3 distinct buyers is refused")

    thin = (_ev(0, 100_000_000, 120_000_000, base=base, trader="b1", side="buy"),
            _ev(1, 120_000_000, 140_000_000, base=base, trader="b2", side="buy"),
            _ev(2, 140_000_000, 160_000_000, base=base, trader="b3", side="buy"))
    check(detector.qualify(thin, now_unix_nanos=now, quote_input_lamports=50_000_000) is None,
          "momentum: a curve below the 6x liquidity floor is refused")

    # --- convex policy asymmetry ---
    P = policy.Position(1_000_000, 50_000_000, 100_000_000, 1000, peak_net_exit_lamports=0)
    check(policy.decide(P, now_unix_nanos=2000, net_exit_lamports=94_000_000,
                        real_quote_lamports=10**10).action == policy.ExitAction.EXIT_HARD_STOP,
          "convex: -6% net fires the hard stop")
    check(policy.decide(P, now_unix_nanos=2000, net_exit_lamports=96_000_000,
                        real_quote_lamports=10**10).action == policy.ExitAction.HOLD,
          "convex: a -4% loser is held (only -6% cuts), not trailed")
    check(policy.decide(P, now_unix_nanos=2000, net_exit_lamports=108_000_000,
                        real_quote_lamports=10**10).action == policy.ExitAction.HOLD,
          "convex: an unproven +8% winner is left to run, not clipped")
    Pr = policy.Position(1_000_000, 50_000_000, 100_000_000, 1000, peak_net_exit_lamports=160_000_000)
    check(policy.decide(Pr, now_unix_nanos=2000, net_exit_lamports=130_000_000,
                        real_quote_lamports=10**10).action == policy.ExitAction.HOLD,
          "convex: a proven +60% runner still +30% rides a wide trail")
    check(policy.decide(Pr, now_unix_nanos=2000, net_exit_lamports=115_000_000,
                        real_quote_lamports=10**10).action == policy.ExitAction.EXIT_TRAIL,
          "convex: a proven runner that reverses past the wide trail exits")
    check(policy.decide(P, now_unix_nanos=1000 + policy.MAX_HOLD_NANOS, net_exit_lamports=94_000_000,
                        real_quote_lamports=10**10).action == policy.ExitAction.EXIT_HORIZON,
          "convex: the 12-minute horizon is absolute and first")
    check(policy.decide(P, now_unix_nanos=2000, net_exit_lamports=None,
                        real_quote_lamports=None).action == policy.ExitAction.UNEXITABLE_FULL_LOSS,
          "convex: an unpriceable (no-bid rug) quote is an honest full loss")

    # --- multi-position book caps ---
    st = {"open_positions": {f"m{i}": {"quote_input_lamports": 100_000_000} for i in range(2)},
          "pending_orders": {"d1": {"side": "ENTRY", "amount": 100_000_000, "mint": "m9"}}}
    check(runner._deployed_notional(st) == 300_000_000, "book: deployed notional sums open + pending entries")
    check(runner.N_MAX == 4 and runner.GROSS_NOTIONAL_CAP_LAMPORTS == 800_000_000,
          "book: N_MAX=4 concurrent slots and 0.80 SOL gross notional cap")

    print(f"\nPAC scalp selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
