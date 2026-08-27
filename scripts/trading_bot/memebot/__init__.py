"""MEMEBOT -- a fast, light, reactive PAPER memecoin trading bot.

A SIBLING of NEWSDESK and BASKET1 (`scripts/trading_bot/basket_forward.py`), not a new venue and not
a strategy claim. It is the execution scaffolding for one honest forward question: after the programme
proved memecoin trading is negative-sum by construction (the ~3% toll is the house edge; the best gross
edge measured anywhere was 0.86%; the exit-rule family lost -18.94%/trade even at ZERO cost), can the
ONE survivor -- a loss-AVOIDANCE entry filter (the deadness screen, B20B) plus a checklist of red-flag
filters -- combined with disciplined fixed-fraction sizing and a defined-risk stop/target, produce ANY
positive expectancy running forward on paper?

It places **NO orders, holds NO wallet, touches NO real SOL, writes NOTHING on-chain**. Every position
is a hypothetical mark-to-market, exactly like the newsdesk/basket bots. It reads only a fixed
allowlist of FREE, KEYLESS public data hosts. Each entry is frozen (sha256 + UTC) BEFORE its outcome
is known, so the forward log is lookahead-proof by construction.

The honest prior is ~0 or NEGATIVE. The target is POSITIVE EXPECTANCY -- explicitly NOT "double every
hour" (that is the farmer's bait; a bot chasing it gets rugged, and it is deliberately not encoded as a
goal anywhere in this package). Behaviour below the pre-registered minimum is not evidence.

See `research/trading_bot/memebot/MEMEBOT_PREREGISTRATION.md` for the frozen rules and the kill switch.
"""

from __future__ import annotations


class Refused(RuntimeError):
    """Absence is a refusal, never a silent zero.

    A missing datum, a lookahead, a broken rule, or a real-order/wallet path REFUSES rather than
    fabricating a number that looks like evidence. Locally defined so the memebot never refuses to
    START because an unrelated frozen harness moved.
    """


__all__ = ["Refused"]
