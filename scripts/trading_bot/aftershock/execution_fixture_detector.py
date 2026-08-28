#!/usr/bin/env python3
"""Pure synthetic detector used only by ``execution_selftest``.

It deliberately returns every post-warm-up observation visible in the supplied causal prefix, making the
test able to prove that DecisionRecord creation and validation execute a sealed detector over the complete
available prefix. It is not a trading rule and must never appear in a production instrument.
"""
from __future__ import annotations


def all_post_warmup_evidence(events: tuple, warmup_count: int) -> tuple[int, ...]:
    if type(warmup_count) is not int or warmup_count < 0 or warmup_count >= len(events):
        return ()
    return tuple(range(warmup_count, len(events)))
