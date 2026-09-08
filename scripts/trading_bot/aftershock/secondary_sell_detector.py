#!/usr/bin/env python3
"""AFTERSHOCK secondary-sell-resilience detector (sealed experiment module).

PURE. No network, no wallet, no strategy state. Loaded by the execution engine BY PATH + BYTE-HASH via the
session seal, and RE-RUN on every decision. Its constants are therefore frozen by the seal — changing any
threshold changes the file hash and refuses.

The rule (handoff 422 direction): do not buy after "many buys". Buy only after the observed curve has
completed TWO sequential reserve-withdrawal/recovery cycles of at least 0.05 SOL each.  The tape does not
identify actor or funding-cluster independence, so this module deliberately makes no such claim.  The
evidence indices returned are exactly [withdraw1, recover1, withdraw2, recover2].  Recovery 2 MUST be the
latest observed event and becomes the DecisionRecord signal; an old completed pattern cannot fire later.

`detector(events, warmup_count) -> tuple[int, ...]`  (empty tuple => no valid setup in this prefix).
Reserve reads use the exact integer `real_quote` (external SOL, lamports) of each observed state.
"""
from __future__ import annotations

# Frozen-by-seal thresholds.
MIN_CYCLE_WITHDRAWAL_LAMPORTS = 50_000_000     # fixed 0.05 SOL observed reserve withdrawal
RECOVER_TO_FRAC_NUM = 1                          # reserve must return to >= 1.0 x its pre-sell level
RECOVER_TO_FRAC_DEN = 1
REQUIRED_CYCLES = 2                              # two proven sell->recover cycles before entry


def position_size_is_covered(q_lamports: int) -> bool:
    """True only when the planned quote input is no larger than each qualifying withdrawal.

    Exact $10 sizing is point-in-time and can exceed 0.05 SOL when SOL/USD < $200.  A future runner must
    call this guard and refuse in that case; the detector never relabels 0.05 SOL as a constant $10.
    """
    return type(q_lamports) is int and 0 < q_lamports <= MIN_CYCLE_WITHDRAWAL_LAMPORTS


def detector(events: tuple, warmup_count: int) -> tuple:
    if type(warmup_count) is not int or warmup_count < 0 or warmup_count >= len(events):
        return ()
    n = len(events)
    signal_index = n - 1                          # recovery 2 must occur on the latest observed event

    cycles = []           # (sell_index, recover_index)
    i = warmup_count
    while i < n:
        pre_q, post_q = events[i].pre_state.real_quote, events[i].post_state.real_quote
        sold = pre_q - post_q                      # external SOL that LEFT the curve at event i (a sell)
        if sold >= MIN_CYCLE_WITHDRAWAL_LAMPORTS:
            target = (pre_q * RECOVER_TO_FRAC_NUM) // RECOVER_TO_FRAC_DEN   # recover to >= pre-sell level
            recover_index = None
            for j in range(i + 1, n):
                if events[j].post_state.real_quote >= target:
                    recover_index = j
                    break
            if recover_index is not None:
                cycles.append((i, recover_index))
                i = recover_index + 1              # the next cycle must be a fresh, later sell
                continue
        i += 1

    if len(cycles) < REQUIRED_CYCLES or cycles[-1][1] != signal_index:
        return ()                                  # not two demonstrated exit+recovery cycles -> no trade

    indices = []
    for sell_i, rec_i in cycles[-REQUIRED_CYCLES:]:
        indices.extend((sell_i, rec_i))
    result = tuple(indices)
    # The engine requires strictly-increasing, post-warmup, no-future evidence with signal=max(evidence).
    if (len(result) != REQUIRED_CYCLES * 2 or result[0] < warmup_count
            or result[-1] != signal_index or any(a >= b for a, b in zip(result, result[1:]))):
        return ()
    return result
