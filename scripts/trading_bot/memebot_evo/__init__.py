"""MEMEBOT_EVO -- an EVOLUTIONARY variant engine for the paper memecoin bot.

A CPU-only, rule-based, forward-selected POPULATION of strategy variants (genomes) that breed
(mutation + crossover) and are selected by FORWARD paper P&L, under strict multiple-testing
discipline so the search does NOT overfit.

It is a SEPARATE package that REUSES the memebot's primitives READ-ONLY -- its free/keyless data
feed (`..memebot.feed`), its deterministic screen (`..memebot.screen`), and its canonical freeze
hash (`..memebot.frozen.canonical_sha256`). It does NOT edit any memebot file. Paper execution with
the extra flow-following exit gene is copied/extended locally in `evo_paper.py` because the memebot's
`paper.resolve_position` has no flow-reversal exit to import.

HARD LIMITS (identical to the memebot, plus the anti-overfitting core):
  * PAPER ONLY -- NO real orders, NO wallet, NO SOL, NO on-chain write. Every position is a
    hypothetical mark-to-market frozen (sha256 + UTC) BEFORE its outcome.
  * FORWARD-SELECTED, NEVER backtest-optimized. A genome is ranked only on forward trades it was NOT
    bred on. A "real" survivor must beat the K-corrected expected-max-under-null bar (~sqrt(2 ln K)
    in SE units, K = cumulative genomes ever evaluated) AND then hold on a FRESH out-of-sample slice.
  * CPU-ONLY, deterministic rule evolution. NO GPU, NO neural nets, NO training, NO external ML deps
    -- pure stdlib arithmetic.
  * Evolution cannot CREATE an edge. If memecoin trading is negative-sum (the programme's finding),
    the population converges to ~flat/negative and THAT is the honest answer. Below the pre-registered
    minimum there is NO VERDICT: population expectancy is behaviour, not evidence. Honest prior ~0 or
    negative.
"""

from __future__ import annotations


class Refused(RuntimeError):
    """Absence is a refusal, never a silent zero -- mirrors ..memebot.Refused (locally defined so the
    evo engine never refuses to START because an unrelated harness moved)."""


__all__ = ["Refused"]
