"""rules_carry.py — the CARRY family of DESIGN_v2 §4 (FX lanes only).

ANNUALISED CARRY (`common.annualised_carry`). On the FX lanes it is the rate differential
`aux["rates"][ccy] - aux["rates"]["USD"]` (decimal per year, already lagged one business day by the
data layer). Only when `aux["rates"]` is absent is it reconstructed from the accrual panel:
five-print sum of `panel.carry` / calendar days in that span * 360. The per-print accrual itself is
never ranked: it accrues by calendar days, so a Monday print is about three times a Tuesday print.

`carry` is the accrual EARNED by a long position, so a positive value means "long earns": every rule
here is long high carry. Funding carry on CRYPTO-PERP is on the dead ledger and is not in `lanes`.

Each function takes `(panel, **params)` and returns raw signals in [-1, 1], NaN = no view.
"""
from __future__ import annotations

import pandas as pd

from ..panel import PanelBundle
from .common import annualised_carry, ewma, vol_estimate, xs_linear_rank, xs_tercile


def carry_ts(panel: PanelBundle, span: int) -> pd.DataFrame:
    """CARRY.TS.S<span> — vol-adjusted time-series carry:

        signal = clip( EWMA_span( carry_ann / sigma_hat ), -1, +1 )

    carry_ann = annualised carry (rate differential), sigma_hat = `common.vol_estimate` (annualised
    60-print std of excess returns, floored). The RATIO is smoothed and then clipped (Carver's order);
    span = 1 is no smoothing. A carry-to-vol ratio of 1 is a full signal, so typical G10 values are
    small (|s| ~ 0.1-0.3) and the rule is linear in the ratio almost everywhere.
    Causality: lagged rates, a trailing volatility, a causal EWMA.
    Limits: NaN until the volatility (40 prints) and the EWMA (`span` values) exist."""
    ratio = annualised_carry(panel) / vol_estimate(panel)
    return ewma(ratio, span).clip(-1.0, 1.0)


def carry_xs_tercile(panel: PanelBundle, span: int) -> pd.DataFrame:
    """CARRY.XS_TERCILE.S<span> — long the top third / short the bottom third of eligible instruments
    ranked by EWMA_span(annualised carry); span = 1 is the raw rate differential.
    Causality: lagged rates, causal EWMA, per-row ranking (`common.xs_tercile`, ties by column order).
    Limits: zero when fewer than three instruments have a carry."""
    return xs_tercile(ewma(annualised_carry(panel), span), panel.eligible())


def carry_xs_linear(panel: PanelBundle, span: int) -> pd.DataFrame:
    """CARRY.XS_LINEAR.S<span> — weights linear in the cross-sectional rank of EWMA_span(annualised
    carry), mean zero, extremes at +-1 (`common.xs_linear_rank`, ties share the average rank).
    Causality and limits as `carry_xs_tercile`."""
    return xs_linear_rank(ewma(annualised_carry(panel), span), panel.eligible())


#: The change of the annualised carry is rounded to this many decimals (1e-9 = 0.00001 bp a year).
CHANGE_DECIMALS = 9


def carry_change_xs(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """CARRY.XS_CHANGE.L<L> — tercile on the CHANGE of the annualised carry over L prints,
    round(carry_ann_t - carry_ann_{t-L}, 9): long the currencies whose rate differential to USD rose
    most, short those where it fell most.

    Policy rates are step functions, so most currencies have exactly the same change (zero, or minus
    the dollar's own move). Those ties are real and must stay ties: the change is therefore rounded to
    1e-9 — far below any rate move — so that floating-point dust (the two differentials are computed
    with different operands; the 5-print fallback divides sums) cannot rank currencies that did not
    move, and `common.xs_tercile` then shares the slots among the tied (a quiet window is a zero row).
    Causality: carry at t and t-L, elementwise rounding. Limits: NaN until L prints of carry exist."""
    ca = annualised_carry(panel)
    return xs_tercile((ca - ca.shift(lookback)).round(CHANGE_DECIMALS), panel.eligible())
