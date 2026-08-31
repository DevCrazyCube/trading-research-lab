#!/usr/bin/env python3
"""Integrity selftest for the Launch-Window Sentinel Scalper (PAC_LWS / PAC_LWS_NULL).

Grows with the build. Current coverage: the deadness/insider screen (pac_lws_screen) — byte-identical
to the validated b20b.score, no-lookahead, cross-check coverage loss, shadow footprint signals. Feed /
runner / manifest gates are added as those modules land.
"""
from __future__ import annotations

import random

from . import pac_lws_screen as screen


def _b20b_flag(window):
    """b20b.score's exact net-holding flag, re-implemented locally as the oracle."""
    held = {}
    for _slot, user, is_buy, amount in window:
        held[user] = held.get(user, 0) + (amount if is_buy else -amount)
    total = sum(v for v in held.values() if v > 0)
    if total <= 0:
        return None
    return max(held.values()) * 100 >= total * screen.CONCENTRATION_THRESHOLD


def _checks():
    yield "frozen rule pinned 60/95/2", (
        screen.K_SLOTS == 60 and screen.CONCENTRATION_THRESHOLD == 95
        and screen.MIN_BUYERS_TO_SCORE == 2)

    # byte-identical agreement with the validated b20b flag over random windows
    rng = random.Random(1234)
    scored = mism = 0
    for _ in range(500):
        t0 = rng.randint(1000, 2000)
        window = [(t0 + rng.randint(0, 60), f"w{rng.randint(0, 6)}",
                   rng.random() < 0.75, rng.randint(1, 10_000_000))
                  for _ in range(rng.randint(2, 14))]
        v = screen.evaluate([screen.WindowTrade(slot=s, trader=u, is_buy=b, token_amount=a)
                             for s, u, b, a in window], t0_slot=t0)
        ref = _b20b_flag(window)
        buyers = len({u for s, u, b, a in window if b})
        if buyers < 2 or ref is None:
            if v.status in (screen.SURVIVED, screen.VETO_CONCENTRATION):
                mism += 1
            continue
        scored += 1
        if v.flagged != ref:
            mism += 1
    yield f"screen matches b20b on {scored} scored windows", mism == 0

    veto = [screen.WindowTrade(100, "whale", True, 96), screen.WindowTrade(101, "b", True, 4)]
    yield "veto fires at >=95% concentration", screen.evaluate(veto, t0_slot=100).status == screen.VETO_CONCENTRATION
    surv = [screen.WindowTrade(100, "a", True, 60), screen.WindowTrade(101, "b", True, 40)]
    sv = screen.evaluate(surv, t0_slot=100)
    yield "screen survives 60/40 split", sv.status == screen.SURVIVED and sv.enter_allowed and sv.top_share_bps == 6000
    yield "single buyer is unreadable (refuse)", (
        screen.evaluate([screen.WindowTrade(100, "a", True, 99)], t0_slot=100).status == screen.UNREADABLE)
    la = surv + [screen.WindowTrade(200, "whale", True, 100000)]   # after t0+60
    yield "no lookahead: post-window whale ignored", screen.evaluate(la, t0_slot=100).status == screen.SURVIVED
    cc = [screen.WindowTrade(100, "a", True, 60, reserve_delta_tokens=60),
          screen.WindowTrade(101, "b", True, 40, reserve_delta_tokens=999)]
    cv = screen.evaluate(cc, t0_slot=100)
    yield "cross-check drops a mismatched trade", cv.dropped_crosscheck == 1
    bund = [screen.WindowTrade(100, "j1", True, 30), screen.WindowTrade(100, "j2", True, 30),
            screen.WindowTrade(105, "r", True, 40)]
    yield "shadow same-slot bundle is detected (non-decisional)", (
        screen.evaluate(bund, t0_slot=100).shadow.get("same_slot_wallets") == 2)
    yield "no execution surface imported", not any(
        m in screen.__dict__ for m in ("sendTransaction", "load_fee_payer", "build_signed_memo"))


def run() -> int:
    failed = [name for name, ok in _checks() if not ok]
    if failed:
        print("PAC_LWS SELFTEST FAILED: " + "; ".join(failed))
        return 1
    print("PAC_LWS SELFTEST OK")
    return 0


def main(argv=None) -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
