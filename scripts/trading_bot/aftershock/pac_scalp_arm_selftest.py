#!/usr/bin/env python3
"""Selftest for the PAC scalp anti-exhaustion entry arms (paper-scenario).

Covers the two new entry detectors (dip-reclaim, early-curve) -- that they FIRE on their intended
setup, REFUSE the exhaustion/late/rug/degenerate cases, and never read a future event (no lookahead)
-- plus the arm wiring (registry consistency, matched exit policy reuse).  This file is inside every
arm's seal dependency closure, so a behavioural change here re-seals the arms rather than passing
silently.
"""
from __future__ import annotations

import types

from . import pac_scalp_detector_dip as dip
from . import pac_scalp_detector_early as early
from . import pac_scalp_arm_runner as arm_runner
from . import pac_scalp_arm_manifest as arm_manifest
from . import pac_scalp_policy as policy


_Q = 100_000_000          # 0.10 SOL notional -> coverage floor 0.60 SOL
_NOW = 100_000_000_000


def _ev(recv, pre_rq, post_rq, side, trader, eid, slot=1, mint="MINT"):
    rs = lambda rq: types.SimpleNamespace(real_quote=int(rq))
    return types.SimpleNamespace(source_received_unix_nanos=int(recv), pre_state=rs(pre_rq),
                                 post_state=rs(post_rq), side=side, trader=trader,
                                 event_id=eid, slot=slot, mint=mint)


def _seq(points, base):
    return tuple(_ev(base + int(dt * 1e9), int(pre * 1e9), int(post * 1e9), s, t, f"e{i}")
                for i, (dt, pre, post, s, t) in enumerate(points))


def _checks():
    yield "modules import", callable(dip.qualify) and callable(early.qualify)

    # ---- dip-reclaim ----
    base = _NOW - 11_000_000_000
    reclaim = _seq([(0, 6, 7, "buy", "a"), (1, 7, 8, "buy", "b"), (2, 8, 10, "buy", "c"),
                    (3, 10, 9.2, "sell", "x"), (4, 9.2, 8.5, "sell", "y"),
                    (5, 8.5, 8.8, "buy", "d"), (6, 8.8, 9.0, "buy", "e"), (7, 9.0, 9.2, "buy", "f")], base)
    sig = dip.qualify(reclaim, now_unix_nanos=_NOW, quote_input_lamports=_Q)
    yield "dip fires on reclaim", sig is not None
    yield "dip pullback>=800bps", sig is not None and sig.pullback_bps >= dip.PULLBACK_MIN_BPS
    yield "dip trough<entry<peak", (sig is not None
                                    and sig.trough_real_quote < sig.entry_real_quote < sig.peak_real_quote)
    spike = _seq([(i, 6 + i, 7 + i, "buy", chr(97 + i)) for i in range(6)], base)
    yield "dip refuses pure spike", dip.qualify(spike, now_unix_nanos=_NOW, quote_input_lamports=_Q) is None
    ath = _seq([(0, 6, 9, "buy", "c"), (3, 9, 8, "sell", "y"), (5, 8, 9, "buy", "d"),
                (6, 9, 10, "buy", "e"), (7, 10, 11, "buy", "f")], base)
    yield "dip refuses new-ATH breakout", dip.qualify(ath, now_unix_nanos=_NOW, quote_input_lamports=_Q) is None
    shallow = _seq([(0, 6, 10, "buy", "c"), (3, 10, 8.5, "sell", "y"), (5, 8.5, 8.65, "buy", "d"),
                    (6, 8.65, 8.66, "buy", "e"), (7, 8.66, 8.67, "buy", "f")], base)
    yield "dip refuses shallow reclaim", dip.qualify(shallow, now_unix_nanos=_NOW, quote_input_lamports=_Q) is None
    future = reclaim + (_ev(_NOW + int(1e9), int(9.2e9), int(20e9), "buy", "z", "future"),)
    yield "dip ignores future event", dip.qualify(future, now_unix_nanos=_NOW, quote_input_lamports=_Q) is not None

    # ---- early-curve ----
    b2 = _NOW - 3_000_000_000
    acc = _seq([(0, 2.0, 2.4, "buy", "a"), (1, 2.4, 2.7, "buy", "b"),
                (2, 2.7, 2.9, "buy", "c"), (3, 2.9, 3.1, "buy", "d")], b2)
    esig = early.qualify(acc, now_unix_nanos=_NOW, quote_input_lamports=_Q)
    yield "early fires on low-reserve accumulation", esig is not None
    yield "early reserve within band", esig is not None and esig.entry_real_quote <= early.EARLY_MAX_QUOTE_LAMPORTS
    late = _seq([(i, 18 + i, 19 + i, "buy", chr(97 + i)) for i in range(4)], b2)
    yield "early refuses late (20 SOL)", early.qualify(late, now_unix_nanos=_NOW, quote_input_lamports=_Q) is None
    dump = _seq([(0, 2.0, 2.4, "buy", "a"), (1, 2.4, 2.6, "buy", "b"),
                 (2, 2.6, 2.8, "buy", "c"), (3, 3.2, 2.3, "sell", "w")], b2)
    yield "early rug-guard trips on whale dump", early.qualify(dump, now_unix_nanos=_NOW, quote_input_lamports=_Q) is None
    efuture = acc + (_ev(_NOW + int(1e9), int(3.1e9), int(3.5e9), "buy", "z", "ef"),)
    yield "early ignores future event", early.qualify(efuture, now_unix_nanos=_NOW, quote_input_lamports=_Q) is not None

    # ---- arm wiring ----
    yield "arm registry matches manifest", set(i for i, _ in arm_runner.ARMS.values()) == set(arm_manifest.ARM_DETECTORS)
    yield "both arms distinct instruments", len({i for i, _ in arm_runner.ARMS.values()}) == 2
    yield "arms reuse the sealed exit policy", hasattr(policy, "decide")
    yield "arm detectors match runner", all(
        (arm_runner.ARMS[a][1].__name__.endswith(arm_manifest.ARM_DETECTORS[arm_runner.ARMS[a][0]].split("/")[-1][:-3]))
        for a in arm_runner.ARMS)


def run() -> int:
    failed = []
    for name, ok in _checks():
        if not ok:
            failed.append(name)
    if failed:
        print("PAC SCALP ARM SELFTEST FAILED: " + "; ".join(failed))
        return 1
    print("PAC SCALP ARM SELFTEST OK")
    return 0


def main(argv=None) -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
