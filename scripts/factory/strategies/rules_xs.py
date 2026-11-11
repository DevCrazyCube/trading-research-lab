"""rules_xs.py — the XSMOM family of DESIGN_v2 §4 (cross-sectional momentum, all lanes).

LEVEL SERIES. "Return" means the return of the causal EXCESS-RETURN INDEX X (`common.excess_index`:
price return + carry, compounded, X = 1.0 on the first valid print) — what a holder actually earned —
not the spot return. The 252-print HIGH is the high of the same index.

Every rule ranks the ELIGIBLE instruments of a row (`panel.eligible()`); fewer than three ranked
instruments give a zero signal.

VOL-SCALED SCORES (conductor ruling of 2026-11-10). The tercile, skip-month and linear-rank rules rank
the window's excess return in units of the instrument's own volatility,

    score = ( X_{t-skip} / X_{t-L} - 1 ) / ( sigma_daily,t * sqrt(L - skip) )    (`common.vol_scaled_return`)

sigma_daily = `vol_estimate / sqrt(periods_per_year)` at the row. Ranking raw returns across bonds,
equities and commodities would put the most volatile instruments in both legs whatever their trend —
a volatility sort, not a momentum sort. Residual momentum (already beta-adjusted) and proximity to the
high (already scale-free) are unchanged.
Each function takes `(panel, **params)` and returns raw signals in [-1, 1], NaN = no view.
"""
from __future__ import annotations

import pandas as pd

from ..panel import PanelBundle
from .common import excess_index, excess_returns, vol_scaled_return, xs_linear_rank, xs_tercile


def xsmom_tercile(panel: PanelBundle, lookback: int, skip: int = 0) -> pd.DataFrame:
    """XSMOM.TERCILE.L<L> / XSMOM.TERCILE.L252_SKIP21 — long the top third, short the bottom third by
    the VOL-SCALED excess return from print t-L to print t-skip:

        score = ( X_{t-skip} / X_{t-L} - 1 ) / ( sigma_daily,t * sqrt(L - skip) )

    (skip = 21 drops the most recent month, the classic 12-1; its window is 231 prints long).
    Causality: two non-negative shifts of the index, a trailing volatility, per-row ranking.
    Limits: NaN until L prints and the volatility estimate (40 returns) exist."""
    return xs_tercile(vol_scaled_return(panel, lookback, skip), panel.eligible())


def xsmom_linear(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """XSMOM.LINEAR.L<L> — weights linear in the cross-sectional rank of the VOL-SCALED L-print excess
    return (X_t / X_{t-L} - 1) / (sigma_daily,t * sqrt(L)), mean zero, extremes at +-1
    (`common.xs_linear_rank`). Causality and limits as `xsmom_tercile`."""
    return xs_linear_rank(vol_scaled_return(panel, lookback), panel.eligible())


def residual_momentum(panel: PanelBundle, lookback: int = 252) -> pd.DataFrame:
    """XSMOM.RESIDUAL.L<L> — momentum of the beta-adjusted return against the lane's equal-weight basket.

        b_t     = mean of the excess returns of the instruments eligible at t          (the basket)
        beta_i  = Cov(e_i, b) / Var(b)            over the L prints t-L+1..t
        score_i = sum_{window} ( e_i - beta_i * b ) = L * ( mean(e_i) - beta_i * mean(b) )

    i.e. L times the instrument's alpha against the basket over the window; tercile on the score.
    Causality: the basket of row s uses row s only; trailing rolling moments.
    Limits: NaN until the instrument has L consecutive excess returns; the instrument is part of its own
    basket (with nine currencies that is an 11 % weight); the score is NOT divided by the residual
    volatility (Blitz-Huij-Martens standardise; §4 says "beta-adjusted" only)."""
    e = excess_returns(panel)
    eligible = panel.eligible()
    basket = e.where(eligible).mean(axis=1)
    roll = dict(window=lookback, min_periods=lookback)
    mean_e = e.rolling(**roll).mean()
    mean_b = basket.rolling(**roll).mean()
    mean_bb = (basket * basket).rolling(**roll).mean()
    mean_eb = e.mul(basket, axis=0).rolling(**roll).mean()
    var_b = mean_bb - mean_b * mean_b
    beta = mean_eb.sub(mean_e.mul(mean_b, axis=0)).div(var_b.where(var_b > 0), axis=0)
    score = lookback * (mean_e - beta.mul(mean_b, axis=0))
    return xs_tercile(score, eligible)


def high_proximity(panel: PanelBundle, lookback: int = 252) -> pd.DataFrame:
    """XSMOM.HIGH_PROXIMITY.L<L> — tercile on X_t / max(X_{t-L+1..t}), the distance of the excess-return
    index from its own L-print high (George-Hwang): long the third nearest its high, short the third
    furthest below it.
    Causality: a trailing maximum that includes t. Limits: NaN until L prints exist; instruments AT their
    high all score exactly 1.0 and share the long leg equally (`common.xs_tercile` tie rule)."""
    x = excess_index(panel)
    return xs_tercile(x / x.rolling(lookback, min_periods=lookback).max(), panel.eligible())
