#!/usr/bin/env python3
"""Performance statistics, and the two significance tests this programme trusts.

THE RULE, LIFTED VERBATIM FROM research/FINDINGS.md SECTION 5c
==============================================================

    DSR for anything with a return series that came out of a sweep.
    Permutation for classifiers.
    Paired differences whenever a common market move would otherwise dominate.

That rule was earned by getting it wrong twice, in both directions, and both failure modes
are guarded here in code rather than left to the operator's memory:

**False PASS -- wrong benchmark.** DSR on the crash filter's own returns gave 1.000 at every
trial count, because holding BTC through a 74,000% run answers "is this Sharpe non-zero" yes
regardless of the filter. The paired difference against buy-and-hold is the correct
instrument, and it failed (0.224). So `evaluate()` computes DSR on the PAIRED EXCESS series
and marks that as the decision instrument, while reporting the raw-series DSR beside it
explicitly labelled as the one that flatters.

**False FAIL -- wrong object.** The deadness screen is a classifier with no return series;
deflating it would report a failure that does not exist. So `deflated_sharpe` refuses a
zero-variance series rather than returning a number, which is exactly what a
self-differenced or constant series is.

TRIALS ARE NOT OPTIONAL
=======================
`deflated_sharpe` requires the number of trials and the cross-trial Sharpe variance, or an
explicit declaration that exactly one configuration was ever run. It will not guess. The
whole point of the deflation is to charge for the search, and a rig that defaults the search
size to 1 hands back an undeflated number under a deflated name.

FLOAT
=====
This module is float throughout, and it is the only part of the rig that is. Prices, fills,
costs and per-bar returns are exact upstream; statistics are estimates by nature.
"""

from __future__ import annotations

import math
import random
from fractions import Fraction

from .frozen import Refused

EULER_MASCHERONI = 0.5772156649015328606
TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = 365.25
NS_PER_DAY = 86_400 * 1_000_000_000


# ---------------------------------------------------------------------------
# Normal distribution, stdlib only (no scipy in this environment)
# ---------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF: Acklam's rational approximation plus one Halley step.

    The refinement step matters. Acklam alone is accurate to ~1.15e-9, which is fine, but the
    Halley correction takes it to full double precision and costs one `erfc` call -- and this
    function sits inside the expected-max-Sharpe term that decides whether a strategy passes.
    A benchmark that is slightly wrong in the flattering direction is the exact failure this
    programme keeps finding.
    """
    if not 0.0 < p < 1.0:
        raise Refused(f"norm_ppf requires 0 < p < 1; got {p}")

    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    lo, hi = 0.02425, 1 - 0.02425

    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    elif p <= hi:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    else:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)

    err = norm_cdf(x) - p
    pdf = math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)
    if pdf > 0:
        u = err / pdf
        x = x - u / (1 + x * u / 2)
    return x


# ---------------------------------------------------------------------------
# Moments
# ---------------------------------------------------------------------------

def _as_floats(returns, what="returns") -> list:
    values = [float(r) for r in returns]
    if len(values) < 2:
        raise Refused(f"{what}: need at least 2 observations, got {len(values)}")
    return values


def moments(returns) -> dict:
    """Mean, sample sd, skew and NON-EXCESS kurtosis.

    Non-excess (i.e. 3.0 for a normal) because that is what Bailey & Lopez de Prado's DSR
    formula takes. Passing excess kurtosis there silently shifts the denominator and, for a
    right-tailed payoff like this programme's, in the flattering direction. B19Q measured
    skew +20.2 and kurtosis 521 on our own data, which is why this is spelled out.
    """
    values = _as_floats(returns)
    n = len(values)
    mean = sum(values) / n
    centred = [v - mean for v in values]
    var = sum(c * c for c in centred) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0.0:
        return {"n": n, "mean": mean, "sd": 0.0, "skew": 0.0, "kurtosis": 0.0, "degenerate": True}
    m2 = sum(c * c for c in centred) / n
    m3 = sum(c ** 3 for c in centred) / n
    m4 = sum(c ** 4 for c in centred) / n
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "skew": m3 / (m2 ** 1.5),
        "kurtosis": m4 / (m2 * m2),
        "degenerate": False,
    }


def sharpe_per_observation(returns, risk_free_per_observation: float = 0.0) -> float:
    m = moments(returns)
    if m["degenerate"]:
        raise Refused(
            "Sharpe of a zero-variance series is undefined, not infinite and not zero. "
            "A constant series (including a series differenced against itself) has no Sharpe."
        )
    return (m["mean"] - risk_free_per_observation) / m["sd"]


def annualised_sharpe(returns, periods_per_year: int, risk_free_annual: float = 0.0) -> float:
    """Annualise by sqrt(periods_per_year). `periods_per_year` is REQUIRED, never inferred."""
    if periods_per_year is None or periods_per_year <= 0:
        raise Refused(
            "periods_per_year must be given explicitly and be positive. Inferring it from bar "
            "spacing is how a 30-minute series gets annualised as if it were daily."
        )
    rf = risk_free_annual / periods_per_year
    return sharpe_per_observation(returns, rf) * math.sqrt(periods_per_year)


def max_drawdown(equity_curve) -> dict:
    if len(equity_curve) < 2:
        raise Refused("a drawdown needs at least 2 equity points")
    peak = equity_curve[0]
    worst, peak_i, trough_i, cur_peak_i = 0.0, 0, 0, 0
    for i, value in enumerate(equity_curve):
        if value > peak:
            peak, cur_peak_i = value, i
        if peak <= 0:
            raise Refused("equity reached zero or below; drawdown fraction is undefined there")
        dd = value / peak - 1.0
        if dd < worst:
            worst, peak_i, trough_i = dd, cur_peak_i, i
    return {"max_drawdown": worst, "peak_index": peak_i, "trough_index": trough_i}


def cagr(equity_curve, first_ts_ns: int, last_ts_ns: int) -> float:
    """Compound annual growth rate over the CALENDAR span the curve actually covers.

    Calendar, not trading days: a strategy that is flat for six months has still consumed six
    months of the investor's life, and annualising by bar count would hide that.
    """
    if len(equity_curve) < 2:
        raise Refused("CAGR needs at least 2 equity points")
    if equity_curve[0] <= 0 or equity_curve[-1] <= 0:
        raise Refused("CAGR is undefined for non-positive equity (total ruin is not a rate)")
    span_ns = last_ts_ns - first_ts_ns
    if span_ns <= 0:
        raise Refused("CAGR needs a positive calendar span; timestamps are out of order")
    years = span_ns / (NS_PER_DAY * CALENDAR_DAYS_PER_YEAR)
    return (equity_curve[-1] / equity_curve[0]) ** (1.0 / years) - 1.0


# ---------------------------------------------------------------------------
# Deflated Sharpe (Bailey & Lopez de Prado 2014)
# ---------------------------------------------------------------------------

def expected_max_sharpe(trials: int, sharpe_variance: float) -> float:
    """E[max SR] under the null that every trial has true Sharpe zero.

    Per-observation units, matching `sharpe_per_observation`. This is the chance ceiling: the
    Sharpe you expect to see from the best of `trials` worthless strategies. FINDINGS records
    two of this programme's own results dying against exactly this quantity (0.01114 observed
    against 0.01854 expected-max at only ten trials).
    """
    if trials < 1:
        raise Refused(f"trials must be >= 1; got {trials}")
    if sharpe_variance < 0:
        raise Refused("sharpe_variance must be non-negative")
    if trials == 1:
        return 0.0
    if sharpe_variance == 0:
        raise Refused(
            "expected-max Sharpe with zero cross-trial variance is zero by arithmetic, which "
            "would silently turn a deflated Sharpe back into an undeflated one. Supply the "
            "observed spread of Sharpes across the trials, or declare trials=1."
        )
    z1 = norm_ppf(1.0 - 1.0 / trials)
    z2 = norm_ppf(1.0 - 1.0 / (trials * math.e))
    return math.sqrt(sharpe_variance) * ((1 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)


def sharpe_variance_from_trials(trial_sharpes) -> float:
    """Sample variance of the per-observation Sharpes actually tried. The honest input."""
    values = _as_floats(trial_sharpes, "trial_sharpes")
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)


def deflated_sharpe(
    returns,
    *,
    trials: int,
    sharpe_variance: float | None = None,
    benchmark_sharpe: float | None = None,
) -> dict:
    """P(true Sharpe > benchmark), corrected for non-normality and for the size of the search.

    With `trials == 1` and no benchmark this reduces to the Probabilistic Sharpe Ratio
    against zero, and the report says so rather than calling it deflated.

    Refuses on a degenerate series -- which is precisely what a series differenced against
    itself is, and precisely the case FINDINGS 5c calls the "wrong object" failure.
    """
    m = moments(returns)
    if m["degenerate"]:
        raise Refused(
            "deflated Sharpe of a zero-variance return series is undefined. If this is a "
            "paired excess series that came out identically zero, the two legs are the same "
            "strategy and there is nothing to test. If it is a classifier, DSR is the wrong "
            "instrument entirely -- use a label permutation (FINDINGS 5c)."
        )

    sr = m["mean"] / m["sd"]
    if benchmark_sharpe is not None:
        sr0 = float(benchmark_sharpe)
        basis = "explicit benchmark Sharpe"
    else:
        sr0 = expected_max_sharpe(trials, 0.0 if trials == 1 else float(sharpe_variance or 0.0))
        basis = "expected-max Sharpe under the null" if trials > 1 else "zero (single trial)"

    denom_sq = 1.0 - m["skew"] * sr + (m["kurtosis"] - 1.0) / 4.0 * sr * sr
    if denom_sq <= 0:
        raise Refused(
            f"DSR variance term is non-positive ({denom_sq:.6g}); with skew {m['skew']:.3f} and "
            f"kurtosis {m['kurtosis']:.1f} the asymptotic approximation does not hold here. "
            "Refusing rather than returning a number that looks like a probability."
        )
    z = (sr - sr0) * math.sqrt(m["n"] - 1) / math.sqrt(denom_sq)
    return {
        "dsr": norm_cdf(z),
        "name": "deflated Sharpe" if trials > 1 else "probabilistic Sharpe (single trial)",
        "observed_sharpe_per_observation": sr,
        "benchmark_sharpe_per_observation": sr0,
        "benchmark_basis": basis,
        "trials": trials,
        "sharpe_variance": sharpe_variance,
        "n": m["n"],
        "skew": m["skew"],
        "kurtosis_non_excess": m["kurtosis"],
        "z": z,
        "passes_at_0p95": norm_cdf(z) >= 0.95,
    }


# ---------------------------------------------------------------------------
# Permutation
# ---------------------------------------------------------------------------

def permutation_test(
    positions,
    market_returns,
    *,
    trials: int = 10_000,
    seed: int = 20260816,
    statistic: str = "mean",
) -> dict:
    """Does the TIMING of the exposure carry information, or would any ordering do as well?

    The exposure path is shuffled against a fixed market return series, so the permuted
    strategies hold exactly the same positions for exactly the same number of bars -- only
    when they hold them changes. Anything that survives has timing information; anything that
    does not was harvesting the asset's drift.

    A constant exposure (buy-and-hold) permutes to itself, so p = 1.0. That is the correct
    answer and a useful wiring check: buy-and-hold has no timing information by definition.
    """
    pos = [float(p) for p in positions]
    mkt = [float(r) for r in market_returns]
    if len(pos) != len(mkt):
        raise Refused(f"positions ({len(pos)}) and market returns ({len(mkt)}) must align 1:1")
    if len(pos) < 2:
        raise Refused("a permutation test needs at least 2 aligned observations")
    if trials < 100:
        raise Refused(f"{trials} permutations cannot resolve a p-value usefully; use >= 100")

    def stat(exposure):
        pnl = [e * r for e, r in zip(exposure, mkt)]
        if statistic == "mean":
            return sum(pnl) / len(pnl)
        if statistic == "sharpe":
            m = moments(pnl)
            return 0.0 if m["degenerate"] else m["mean"] / m["sd"]
        raise Refused(f"unknown statistic {statistic!r}")

    observed = stat(pos)
    rng = random.Random(seed)
    shuffled = list(pos)
    ge = le = 0
    null = []
    for _ in range(trials):
        rng.shuffle(shuffled)
        value = stat(shuffled)
        null.append(value)
        if value >= observed:
            ge += 1
        if value <= observed:
            le += 1

    # Add-one correction: a permutation p-value of exactly 0 overstates what n permutations
    # can resolve. The observed arrangement is itself one of the arrangements.
    p_right = (ge + 1) / (trials + 1)
    p_left = (le + 1) / (trials + 1)
    null.sort()
    return {
        "observed": observed,
        "statistic": statistic,
        "trials": trials,
        "seed": seed,
        "p_right_tail": p_right,
        "p_left_tail": p_left,
        "p_two_tailed": min(1.0, 2 * min(p_right, p_left)),
        "null_p05": null[int(0.05 * (trials - 1))],
        "null_p50": null[int(0.50 * (trials - 1))],
        "null_p95": null[int(0.95 * (trials - 1))],
        "degenerate_exposure": len(set(pos)) == 1,
        "note": (
            "Exposure is shuffled against fixed market returns, so every permutation holds the "
            "same positions for the same number of bars. Only the timing changes. A constant "
            "exposure permutes to itself and correctly yields p = 1.0."
        ),
    }


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def paired_excess(strategy_returns, benchmark_returns) -> list:
    """Strategy minus benchmark, bar by bar. The instrument FINDINGS 5c says to use.

    A paired difference cancels the common asset move. FINDINGS 5: 'A paired comparison
    cancels asset variance; an absolute mean does not.'
    """
    if len(strategy_returns) != len(benchmark_returns):
        raise Refused(
            f"paired excess needs aligned series; got {len(strategy_returns)} and "
            f"{len(benchmark_returns)}. Unaligned pairing is worse than no pairing."
        )
    return [Fraction(a) - Fraction(b) for a, b in zip(strategy_returns, benchmark_returns)]


def summarise(result, periods_per_year: int) -> dict:
    """CAGR / Sharpe / maxDD / turnover for one backtest result."""
    curve = result.equity_curve()
    out = {
        "n_segments": result.n_segments,
        "periods_per_year": periods_per_year,
        "final_equity": curve[-1],
        "total_return": curve[-1] - 1.0,
        "cagr": cagr(curve, result.bar_timestamps_ns[0], result.bar_timestamps_ns[-1]),
        "annualised_sharpe": annualised_sharpe(result.returns, periods_per_year),
        "annualised_vol": moments(result.returns)["sd"] * math.sqrt(periods_per_year),
        "total_cost_fraction": float(result.total_cost_fraction()),
        "total_turnover": float(result.total_turnover()),
    }
    out.update(max_drawdown(curve))
    try:
        out["gross_annualised_sharpe"] = annualised_sharpe(result.gross_returns, periods_per_year)
    except Refused:
        out["gross_annualised_sharpe"] = None
    return out


def evaluate(
    result,
    benchmark_result,
    *,
    periods_per_year: int,
    trials: int,
    sharpe_variance: float | None = None,
    permutation_trials: int = 10_000,
    seed: int = 20260816,
) -> dict:
    """The full significance report, with the paired instrument marked as the decision.

    `benchmark_result` is a second `BacktestResult` -- normally buy-and-hold on the same bars
    under the same cost model -- and is REQUIRED. FINDINGS 5c's false-PASS mode is exactly
    what happens when a return series is deflated without one.
    """
    if benchmark_result is None:
        raise Refused(
            "evaluate() requires a benchmark result. Deflating a strategy's own returns "
            "without one is the false-PASS failure recorded in FINDINGS 5c: it asks 'is this "
            "Sharpe non-zero', which any long exposure to a rising asset answers yes."
        )
    if result.n_segments != benchmark_result.n_segments:
        raise Refused(
            f"strategy has {result.n_segments} segments, benchmark {benchmark_result.n_segments}. "
            "They must be run over the same bars for the pairing to cancel anything."
        )

    excess = paired_excess(result.returns, benchmark_result.returns)
    report = {
        "strategy": summarise(result, periods_per_year),
        "benchmark": summarise(benchmark_result, periods_per_year),
        "lookahead_audit": result.lookahead_audit,
        "decision_instrument": "paired_excess_dsr",
        "rule": (
            "FINDINGS 5c: DSR for a return series out of a sweep; permutation for a "
            "classifier; a PAIRED DIFFERENCE whenever a common market move would dominate."
        ),
    }

    # Separate try blocks: a refusal from the deflation must not discard a paired Sharpe that
    # was computed correctly, and each refusal must report its OWN cause rather than a shared
    # canned one.
    report["paired_excess"] = {
        "annualised_excess_return": report["strategy"]["cagr"] - report["benchmark"]["cagr"],
        "mean_per_bar": float(sum(excess, Fraction(0))) / len(excess),
    }
    try:
        report["paired_excess"]["annualised_sharpe"] = annualised_sharpe(
            excess, periods_per_year
        )
    except Refused as exc:
        report["paired_excess"]["annualised_sharpe"] = {
            "refused": str(exc),
            "meaning": "the excess series is constant: the strategy IS the benchmark here.",
        }
    try:
        report["paired_excess_dsr"] = deflated_sharpe(
            excess, trials=trials, sharpe_variance=sharpe_variance,
        )
    except Refused as exc:
        report["paired_excess_dsr"] = {
            "refused": str(exc),
            "why_this_is_correct_behaviour": (
                "Either the excess series is zero-variance -- the strategy IS the benchmark, "
                "FINDINGS 5c's 'wrong object', and returning a probability would invent a "
                "difference that does not exist -- or a trial count above 1 was declared with "
                "no cross-trial Sharpe variance to build the chance ceiling from. The message "
                "above says which."
            ),
        }

    try:
        report["raw_dsr_DO_NOT_DECIDE_ON_THIS"] = dict(
            deflated_sharpe(result.returns, trials=trials, sharpe_variance=sharpe_variance),
            warning=(
                "This is the FALSE-PASS instrument from FINDINGS 5c. It asks only whether the "
                "Sharpe is non-zero, which long exposure to a rising asset answers yes to "
                "regardless of skill. It is reported for completeness and must not be the "
                "basis of a decision."
            ),
        )
    except Refused as exc:
        report["raw_dsr_DO_NOT_DECIDE_ON_THIS"] = {"refused": str(exc)}

    # The market series is recorded exactly by the engine (each bar's own open-to-open move),
    # never reconstructed by dividing gross return by position -- that division is undefined
    # wherever the strategy was flat, and "undefined is not zero" (FINDINGS 8).
    report["permutation"] = permutation_test(
        result.positions[:len(result.market_returns)], result.market_returns,
        trials=permutation_trials, seed=seed, statistic="mean",
    )
    return report


__all__ = [
    "norm_cdf", "norm_ppf", "moments", "sharpe_per_observation", "annualised_sharpe",
    "max_drawdown", "cagr", "expected_max_sharpe", "sharpe_variance_from_trials",
    "deflated_sharpe", "permutation_test", "paired_excess", "summarise", "evaluate",
    "TRADING_DAYS_PER_YEAR",
]
