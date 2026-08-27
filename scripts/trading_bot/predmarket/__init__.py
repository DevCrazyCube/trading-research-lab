"""PREDMARKET -- the agent-driven prediction-market FORWARD CALIBRATION tracker.

A SIBLING of the Newsdesk (`scripts/trading_bot/newsdesk/`), not a bot and not a bet. It asks one
honest question: is an information-reading agent BETTER CALIBRATED than the crowd on
POLITICS / POLICY / SOFT-NEWS prediction markets? It reads OPEN, unresolved markets on Kalshi and
Polymarket (free, keyless public read APIs), the agent commits its OWN probability estimate `q_agent`
frozen with sha256 + a UTC timestamp BEFORE the market resolves, and the market-implied probability
`p_market` is recorded at the same instant. When the market later settles, the agent's Brier score is
compared to the market's Brier score on the same set.

It places **NO bets, holds NO position, touches NO account, wallet or real money**, and reads only a
fixed allowlist of free, keyless public-data hosts. The PRIMARY metric is CALIBRATION (agent Brier vs
market Brier), not P&L; a hypothetical bet-expectancy net of the fee/spread wall is logged as a noisy
SECONDARY confirmation only.

The instrument is lookahead-proof by construction: an LLM was trained on data through 2026 and has
memorised how resolved markets turned out, so the proposer is NEVER run on a resolved market. It reads
only OPEN markets and commits before the outcome exists.

See `research/trading_bot/predmarket/PREDMARKET_PREREGISTRATION.md` for the frozen rules and the honest
prior (the base case is roughly calibration-competitive but not decisively better, expectancy pinned
near zero by fees), and `research/trading_bot/prediction_markets_scope.md` for the full scoping.
"""

from __future__ import annotations


class Refused(RuntimeError):
    """Absence is a refusal, never a silent zero.

    Locally defined (as in the Newsdesk) so this tracker never refuses to START because an unrelated
    frozen harness moved -- but it carries the identical house meaning: a missing datum, a lookahead,
    or a broken rule REFUSES rather than fabricating a number that looks like evidence.
    """


__all__ = ["Refused"]
