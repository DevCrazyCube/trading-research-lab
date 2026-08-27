#!/usr/bin/env python3
"""AFTERSHOCK — the rug-absorption survivor paper arm (PAPER / READ-ONLY).

Thesis: a long-only sniper cannot profit from coins that go to zero, but it CAN use the ~98-99% failures
as a real-time stress test. Do NOT buy before the rug. Watch each new pump.fun mint's trade tape from
birth; when a creator/early-cluster wallet executes a MATERIAL sell (the first rug-like shock), run an
absorption test: only if external, non-cluster demand demonstrably absorbs it — exit capacity holds,
new independent buyers show up, concentration falls, and the exact position-sized exit-capacity ratio
stays above a frozen stress floor — do we (paper-)enter. Exit on capacity/flow, not a fixed take-profit.

Scored on POT GROWTH: G = Σ ln(1 + position_fraction · stressed_net_return), with an unsellable exit
booked as a full economic loss. The unexitable-dump rate is a hard KILL-GATE, not the score.

Everything here is PAPER: it places NO orders, holds NO wallet, touches NO SOL, writes NOTHING on-chain,
reads only the free PumpPortal trade tape. Real trading is a separate, owner-gated wallet decision.

Curve math is NOT reinvented: the ECR engine wraps the repo's integer-exact pump.fun kernel
(scripts/b10a_simulator_kernel.py + b9i). The freeze/ledger/scoring discipline mirrors memebot, but
AFTERSHOCK keeps its OWN frozen registry (it is deliberately NOT in memebot.frozen.INSTRUMENTS) so the
memebot scanner never snapshot-screens it — its entry is event-driven off the tape, not a periodic screen.
"""
from __future__ import annotations


class Refused(Exception):
    """A freeze/consistency violation: refuse rather than guess or silently skip."""


FRAMING = (
    "AFTERSHOCK — rug-absorption survivor PAPER arm. NO orders, NO wallet, NO SOL, NO on-chain writes, "
    "free tape only. Buys only mints whose first rug-like cluster sell is demonstrably absorbed by "
    "external demand, sized 0.1 SOL, curve-exact ECR-gated. Score = pot growth; dump-rate = kill-gate. "
    "Below the pre-registered minimum this is behaviour, not evidence."
)
