"""mtest.py — the multiple-testing toolkit (DESIGN_v2 §3.3). Supersedes the v1 draft `nulls.py`.

    bh_fdr, by_fdr, holm        p-value adjustments (FDR under independence / any dependence; FWER)
    spa, stepm                  Hansen's SPA test and the Romano-Wolf step-down, on `arch.bootstrap.SPA`
    white_reality_check         White's (2000) reality check (un-studentized, full recentring)
    pbo_cscv                    probability of backtest overfitting (Bailey, Borwein, Lopez de Prado, Zhu 2017)
    circular_shift_null         the max-statistic null from circularly shifted positions, windowed
    sharpe_ci_bootstrap         re-exported from stats.py (stationary-bootstrap CI of a Sharpe)

SIGN CONVENTION OF `spa` / `stepm` / `white_reality_check` — read this before trusting a result
  This module takes RETURNS: `returns` is a (T x K) frame of per-print returns, bigger = better, and
  "superior" means "mean return significantly ABOVE the benchmark's".
  `arch.bootstrap.SPA` / `StepM` take LOSSES (smaller = better) and work on
  `loss_diff = benchmark_losses - model_losses`, declaring a model superior when the mean of that
  difference is significantly positive. We therefore hand arch
        benchmark_losses = 0            models_losses = -(returns - benchmark)
  so that `loss_diff = returns - benchmark`. Passing returns where arch expects losses silently
  selects the WORST strategies; tests/test_mtest.py plants one winner and one loser among noise and
  asserts the winner — and only the winner — comes back.

RESULTS ARE LABELS
  `superior`, `steps[i]["rejected"]`, `best`, `degenerate` and the index of `t_stat` / `mean` are the
  column names of `returns`. arch's `SPA.better_models()` returns integer POSITIONS; those never
  leave this module. (A bare 2-D array has no names: its labels are 0..K-1.)

BLOCK LENGTH
  `block` is the mean block length of the stationary bootstrap, in prints: an explicit argument.
  Left at None it is `stats.default_block_length(T)` = ceil(2 * T^(1/3)) (16 at T = 500, 22 at
  1,250, 33 at 4,400) — never arch's own fallback int(sqrt(T)). The rate and the factor are
  justified, with the measurements below, in that function's docstring. The block actually used is
  returned (`block`, `block_source`).

THREE FACTS FOUND BY READING arch 8.0.0's SOURCE AND BY MEASUREMENT (2026-11-10)
  1. `studentize=True` DOES NOT STUDENTIZE. In `arch/bootstrap/multiple_comparison.py` the flag is
     stored and printed, but the statistic is always the raw mean loss differential; the variance
     is used only for the "consistent" recentring threshold. Identical p-values and critical values
     come back for studentize=True and =False. Un-studentized, the strategy with the largest
     variance sets the critical value and a real low-volatility edge is never found.
     HERE: with `studentize=True` (default) each column of `returns - benchmark` is divided by its
     own SAMPLE STANDARD DEVIATION (ddof=1) before arch sees it, so the statistic is
     sqrt(T) * mean_k / sd_k and the bootstrap law is that of the same scaled means. The scale is
     a per-column constant; serial dependence is handled by the stationary bootstrap itself.
     WHY sd AND NOT HANSEN'S omega (the long-run standard deviation, `stationary_long_run_variance`):
     omega-hat is noisy (its ratio to the truth has a standard deviation of 18 % at T = 500,
     block 10), the bootstrap holds it fixed, and the extra tail weight of sqrt(T) mean / omega-hat
     is then missing from the bootstrap law. MEASURED on the SAME all-noise panels (50 strategies x
     500 prints, block 10, share with p_consistent < 5 %): omega-scaling 8.5 %, sd-scaling 4.0 %,
     none 3.0 % (400 white-noise panels); 9.3 % / 5.3 % / 4.0 % (300 AR(1) 0.3 panels).
     `t_stat_longrun` (sqrt(T) mean / omega-hat) is still reported, for information only.
     (This is NOT the Romano-Wolf variant that re-estimates the standard error inside every
     bootstrap sample.)
  2. THE STATIONARY BOOTSTRAP UNDERSTATES THE VARIANCE OF A MEAN in finite samples. Its implied
     variance is the long-run estimate omega-hat^2, and centring on the sample mean biases every
     sample autocovariance down by about omega^2 / T; summed over the kernel that is
           E[omega-hat^2] ~ omega^2 * (1 - (2 * block - 1) / T)            (white noise; checked by
     simulation: 0.9675 at T = 500, block = 10 against a predicted 0.962; 0.905 / 0.902 at block 25;
     0.984 / 0.985 at T = 1250). Critical values are then too low by half that, which the far tail
     of a max-of-K statistic amplifies.
     HERE: with `bias_correction=True` (default) the critical values are inflated by
           c = sqrt(T / (T - 2 * block + 1))        (block 16: 1.0325 at T = 500; block 22: 1.0177 at T = 1250)
     — implemented by shrinking each column's sample MEAN by 1/c before arch sees it, which leaves
     the bootstrap law of the centred means untouched. It only ever makes the test more
     conservative. It does not cure kernel truncation under serial dependence (AR(1) 0.3, block 10:
     the bootstrap variance is 90 % of the truth); a longer block does, and the correction is what
     makes a longer block affordable. MEASURED family-wise error of StepM at a nominal 5 %, 30-50
     noise strategies x 500 prints, 1,000 panels per cell (SE 0.7 %), same panels raw / corrected:
                                  block  8                 block 16 (the default at T = 500)
           white noise          5.8 % / 5.2 %                    6.2 % / 4.0 %
           AR(1) 0.1            6.8 % / 5.8 %                         -
           AR(1) 0.3            8.7 % / 7.9 %                    7.2 % / 5.8 %
     and, on a second independent set of 1,000 panels per cell, the shipped defaults (block 16,
     corrected) gave 5.5 % (white noise), 5.5 % (AR 0.1), 6.0 % (AR 0.3).
     (block 10, raw: 6.3 % white noise, 6.8 % AR 0.1, 10.1 % AR 0.3; at T = 2,000, block 20, AR 0.3:
     5.3 %.) So: at the defaults the error is within about one point of nominal up to an AR(1) of
     0.3; it is NOT guaranteed at 5 % for more persistent return series in short samples.
     `bias_correction=False` gives the raw arch numbers.
  3. `StepM.compute()` RAISES "zero-size array to reduction operation maximum" when every model
     ends up rejected over more than one step. HERE: the step-down loop is re-implemented on top of
     `SPA.subset()` / `SPA.better_models()` with the loop guard fixed; where arch's own `StepM` does
     not crash the two return the same set (tests).

STATED LIMITS
  * Bootstrap tests are asymptotic; the measured rates above are for Gaussian toys. Fat tails and
    volatility clustering are not covered by those measurements.
  * All routines need a COMPLETE (T x K) matrix: no NaN. Pass the window-restricted net returns
    (a flat strategy has 0.0, not NaN).
  * A column with no variation (a strategy that never traded in the window, a copy of the
    benchmark) cannot be tested. It is listed in `degenerate`, left OUT of the bootstrap and never
    declared superior; if EVERY column is degenerate the p-values are NaN. (Left in, a constant
    column ties the bootstrap maximum with the observed one and arch's strict '>' reports p = 0:
    "a flat strategy and a losing one" would read as a significant family.)
"""
from __future__ import annotations

import itertools
import math
from typing import Dict, List, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd
from arch.bootstrap import SPA

from .engine import CostSpec, Refused, backtest
from .panel import PanelBundle
from .stats import Window, default_block_length, newey_west_t, sharpe_ci_bootstrap, window_mask

PValues = Union[pd.Series, np.ndarray, Sequence[float]]


# --------------------------------------------------------------------------------------------------
# p-value adjustments
# --------------------------------------------------------------------------------------------------
def _p_array(p: PValues, level: float, level_name: str) -> np.ndarray:
    arr = np.asarray(p, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        raise ValueError("no p-values given")
    ok = arr[~np.isnan(arr)]
    if ((ok < 0.0) | (ok > 1.0)).any():
        raise ValueError("p-values must lie in [0, 1]")
    if not (0.0 < level < 1.0):
        raise ValueError(f"{level_name} must be in (0, 1); got {level!r}")
    return arr


def _wrap(p: PValues, reject: np.ndarray, adjusted: np.ndarray, **extra) -> Dict[str, object]:
    if isinstance(p, pd.Series):
        reject_out: object = pd.Series(reject, index=p.index, name="reject")
        adj_out: object = pd.Series(adjusted, index=p.index, name="p_adjusted")
    else:
        reject_out, adj_out = reject, adjusted
    return {"reject": reject_out, "p_adjusted": adj_out, "n_reject": int(reject.sum()), **extra}


def _step_up(p: PValues, q: float, c_m: float, method: str) -> Dict[str, object]:
    """Shared BH / BY step-up at level q / c_m."""
    arr = _p_array(p, q, "q")
    m = len(arr)                                   # NaN p-values COUNT in m: they were declared tests
    valid = np.flatnonzero(~np.isnan(arr))
    order = valid[np.argsort(arr[valid], kind="mergesort")]
    sorted_p = arr[order]
    ranks = np.arange(1, len(order) + 1)
    line = ranks * q / (m * c_m)
    below = np.flatnonzero(sorted_p <= line)
    k = int(below[-1]) + 1 if len(below) else 0
    reject = np.zeros(m, dtype=bool)
    reject[order[:k]] = True
    adjusted = np.full(m, np.nan)
    if len(order):
        raw = np.minimum(sorted_p * m * c_m / ranks, 1.0)
        adjusted[order] = np.minimum.accumulate(raw[::-1])[::-1]
    return _wrap(p, reject, adjusted, threshold=float(line[k - 1]) if k else 0.0, m=int(m), q=float(q),
                 method=method)


def bh_fdr(p: PValues, q: float = 0.10) -> Dict[str, object]:
    """Benjamini-Hochberg (1995) step-up at FDR level `q`.

    Sort the m p-values; with k = max{i : p_(i) <= i q / m}, reject the k smallest. Controls the FDR
    at q under independence or positive regression dependence (PRDS).
    Returns {'reject', 'p_adjusted', 'n_reject', 'threshold', 'm', 'q', 'method'}: `reject` and
    `p_adjusted` keep the input's order (and index, for a Series); `p_adjusted_(i)` =
    min_{j>=i} min(1, m p_(j) / j); `threshold` is k q / m (0.0 when nothing is rejected).
    A NaN p-value (a test that could not be computed) COUNTS in m and is never rejected.
    """
    return _step_up(p, q, 1.0, "benjamini-hochberg")


def by_fdr(p: PValues, q: float = 0.10) -> Dict[str, object]:
    """Benjamini-Yekutieli (2001): BH at level q / c(m), c(m) = SUM_{i=1..m} 1/i. Controls the FDR
    at q under ARBITRARY dependence, at the price of power. Same return as `bh_fdr`."""
    m = len(np.asarray(p, dtype=np.float64).reshape(-1))
    c_m = float(np.sum(1.0 / np.arange(1, m + 1))) if m else 1.0
    return _step_up(p, q, c_m, "benjamini-yekutieli")


def holm(p: PValues, alpha: float = 0.05) -> Dict[str, object]:
    """Holm (1979) step-down at FWER level `alpha` (valid under any dependence).

    Sort the m p-values; reject p_(1), p_(2), ... while p_(i) <= alpha / (m - i + 1); stop at the
    first failure. `p_adjusted_(i)` = max_{j<=i} min(1, (m - j + 1) p_(j)).
    Returns {'reject', 'p_adjusted', 'n_reject', 'm', 'alpha', 'method'}. NaN p-values count in m
    and are never rejected.
    """
    arr = _p_array(p, alpha, "alpha")
    m = len(arr)
    valid = np.flatnonzero(~np.isnan(arr))
    order = valid[np.argsort(arr[valid], kind="mergesort")]
    sorted_p = arr[order]
    factor = m - np.arange(len(order))                                  # m, m-1, ...
    passed = sorted_p <= alpha / factor
    k = int(np.argmin(passed)) if not passed.all() else len(order)      # index of the first failure
    reject = np.zeros(m, dtype=bool)
    reject[order[:k]] = True
    adjusted = np.full(m, np.nan)
    if len(order):
        adjusted[order] = np.maximum.accumulate(np.minimum(sorted_p * factor, 1.0))
    return _wrap(p, reject, adjusted, m=int(m), alpha=float(alpha), method="holm")


# --------------------------------------------------------------------------------------------------
# SPA / StepM / Reality Check on arch.bootstrap
# --------------------------------------------------------------------------------------------------
def stationary_long_run_variance(d: np.ndarray, block: float) -> np.ndarray:
    """omega_k^2 = Var-hat( sqrt(T) * mean(d_k) ) under the stationary bootstrap with mean block
    length `block` (Politis & Romano 1994; Hansen 2005):

        omega^2 = g_0 + 2 SUM_{i=1}^{T-1} kappa(T, i) g_i,     g_i = (1/T) SUM_t dm_t dm_{t+i},
        kappa(T, i) = ((T - i)/T) (1 - q)^i + (i/T) (1 - q)^(T - i),     q = 1/block,  dm = d - mean.

    `d` is (T, K); returns (K,). Autocovariances are computed by FFT (O(K T log T)).
    """
    d = np.asarray(d, dtype=np.float64)
    if d.ndim != 2:
        raise ValueError("d must be (T, K)")
    t = d.shape[0]
    if not np.isfinite(block) or block < 1:
        raise ValueError(f"block must be >= 1; got {block!r}")
    dm = d - d.mean(axis=0)
    q = 1.0 / float(block)
    i = np.arange(t)
    kappa = ((t - i) / t) * (1.0 - q) ** i + (i / t) * (1.0 - q) ** (t - i)
    weights = 2.0 * kappa
    weights[0] = 1.0
    out = np.empty(d.shape[1])
    nfft = 2 * t
    for lo in range(0, d.shape[1], 256):                                # bound the FFT workspace
        f = np.fft.rfft(dm[:, lo:lo + 256], n=nfft, axis=0)
        acov = np.fft.irfft(f * np.conj(f), n=nfft, axis=0)[:t] / t
        out[lo:lo + 256] = weights @ acov
    return out


def _excess_matrix(returns, benchmark) -> tuple:
    """(d as a (T, K) float array, column ids). d = returns - benchmark; no NaN allowed."""
    if isinstance(returns, pd.DataFrame):
        ids = list(returns.columns)
        r = returns.to_numpy(dtype=np.float64)
    else:
        r = np.asarray(returns, dtype=np.float64)
        if r.ndim != 2:
            raise ValueError("returns must be a (T x K) DataFrame or 2-D array")
        ids = list(range(r.shape[1]))
    if len(set(ids)) != len(ids):
        raise ValueError("returns has duplicate column ids")
    if r.shape[1] < 1 or r.shape[0] < 10:
        raise ValueError(f"returns must have >= 1 column and >= 10 rows; got {r.shape}")
    if benchmark is None:
        d = r.copy()
    else:
        if isinstance(benchmark, pd.Series) and isinstance(returns, pd.DataFrame):
            if not benchmark.index.equals(returns.index):
                raise ValueError("benchmark.index must equal returns.index")
        b = np.asarray(benchmark, dtype=np.float64).reshape(-1)
        if len(b) != r.shape[0]:
            raise ValueError("benchmark must have one value per row of returns")
        d = r - b[:, None]
    if not np.isfinite(d).all():
        raise ValueError("returns / benchmark contain NaN or inf; pass complete window-restricted series")
    return d, ids


def variance_bias_factor(n_obs: int, block: float) -> float:
    """c = sqrt(T / (T - 2 * block + 1)): the factor by which stationary-bootstrap critical values of a
    mean are too LOW in a sample of T prints (module docstring, fact 2). Refuses T <= 2 * block."""
    if n_obs <= 2 * block:
        raise ValueError(f"T = {n_obs} is too short for a mean block length of {block}: need T > 2 * block")
    return math.sqrt(n_obs / (n_obs - 2.0 * block + 1.0))


def _prepare_spa(returns, benchmark, block, reps, seed, studentize: bool, bias_correction: bool = True):
    """Build the arch SPA object on (optionally studentized) excess returns. See the module docstring.
    Returns (arch SPA or None, d, ids, (t_stat, t_stat_longrun), degenerate mask, critical-value multiplier,
    block). The SPA object is built on the NON-degenerate columns only — arch positions index
    `np.flatnonzero(~degenerate)` — and is None when every column is degenerate."""
    d, ids = _excess_matrix(returns, benchmark)
    if block is None:
        block = default_block_length(d.shape[0])   # ceil(2 T^(1/3)) — never arch's sqrt(T) fallback
    if isinstance(block, bool) or not isinstance(block, (int, np.integer)) or block < 1:
        raise ValueError(f"block must be an integer >= 1 (mean block length in prints) or None; got {block!r}")
    block = int(block)
    if isinstance(reps, bool) or not isinstance(reps, (int, np.integer)) or reps < 100:
        raise ValueError(f"reps must be an integer >= 100; got {reps!r}")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError(f"seed must be an integer; got {seed!r}")
    t = d.shape[0]
    sd = d.std(axis=0, ddof=1)
    # A column with no variation (always flat, identical to the benchmark, or a constant) cannot be tested.
    # It is reported in `degenerate` and LEFT OUT of the bootstrap: a constant column would tie the bootstrap
    # maximum with the observed one, and arch's strict '>' then turns "nothing happened" into p = 0.
    degenerate = ~(sd > 1e-12 * np.maximum(np.abs(d).max(axis=0), 1e-300))
    safe_sd = np.where(degenerate, 1.0, sd)
    scaled = (d / safe_sd if studentize else d)[:, ~degenerate]
    c = variance_bias_factor(t, block) if bias_correction else 1.0
    if c != 1.0:
        centre = scaled.mean(axis=0)
        scaled = (scaled - centre) + centre / c    # same centred series, sample mean shrunk by 1/c
    obj = None
    if scaled.shape[1]:
        # arch works on LOSSES: loss_diff = benchmark_losses - model_losses = 0 - (-scaled) = scaled.
        obj = SPA(benchmark=np.zeros(t), models=-scaled, block_size=int(block), reps=int(reps),
                  bootstrap="stationary", studentize=False, nested=False, seed=int(seed))
    omega = np.sqrt(np.maximum(stationary_long_run_variance(d, block), 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        t_stat = np.where(degenerate, np.nan, math.sqrt(t) * d.mean(axis=0) / safe_sd)
        t_long = np.where(omega > 0, math.sqrt(t) * d.mean(axis=0) / np.where(omega > 0, omega, 1.0), np.nan)
    return obj, d, ids, (t_stat, t_long), degenerate, c * (math.sqrt(t) if studentize else 1.0), block


def _common(d, ids, t_stats, degenerate, block, reps, seed, studentize, bias_correction) -> Dict[str, object]:
    t_stat, t_long = t_stats
    return {
        "bias_correction": bool(bias_correction),
        "critical_value_inflation": variance_bias_factor(d.shape[0], block) if bias_correction else 1.0,
        "t_stat": pd.Series(t_stat, index=ids, name="t_stat"),
        "t_stat_longrun": pd.Series(t_long, index=ids, name="t_stat_longrun"),
        "mean": pd.Series(d.mean(axis=0), index=ids, name="mean"),
        "degenerate": [ids[i] for i in np.flatnonzero(degenerate)],
        "n_obs": int(d.shape[0]), "n_models": int(d.shape[1]),
        "block": int(block), "reps": int(reps), "seed": int(seed), "studentized": bool(studentize),
        "sign_convention": "inputs are RETURNS (bigger is better); arch is fed losses = -(returns - benchmark)",
    }


def spa(returns, benchmark=None, *, block: Optional[int] = None, reps: int = 1000, seed: int, studentize: bool = True,
        bias_correction: bool = True) -> Dict[str, object]:
    """Hansen's (2005) test of Superior Predictive Ability: H0 "no strategy beats the benchmark".

    returns    (T x K) per-print returns of K strategies (DataFrame, or 2-D array -> ids 0..K-1).
    benchmark  (T,) per-print benchmark returns, or None = 0 (the returns are already EXCESS returns,
               so the question is "is any mean excess return > 0").
    block      mean block length of the stationary bootstrap, in prints. None (default) =
               `stats.default_block_length(T)` = ceil(2 T^(1/3)) — NOT arch's sqrt(T) fallback (the
               factor is justified, with measured error rates, in that function's docstring); the
               value used is returned as `block`, with `block_source` saying whether it was given.
    reps       bootstrap replications.   seed  required integer.
    studentize True (default): each column is scaled by its own sample standard deviation, so the
               statistic is sqrt(T) * mean / sd (module docstring, fact 1). False: raw means, as arch.
    bias_correction  True (default): offset the bootstrap's finite-sample variance bias (fact 2).

    Returns {'p_lower', 'p_consistent', 'p_upper', 'best', 't_stat', 't_stat_longrun', 'mean',
    'degenerate', ...}.
    The three p-values are arch's raw bootstrap frequencies for the three recentring rules (lower:
    worse-than-benchmark models keep their negative mean; consistent: Hansen's log-log threshold;
    upper: every model recentred = White's reality check). They can be exactly 0.0, which means
    "< 1/reps". `p_consistent` is the one to report (`p_lower` is a liberal bound: measured 6-7 % at
    a nominal 5 %). `t_stat` is sqrt(T) * mean / sd per strategy (the statistic tested when
    studentized); `t_stat_longrun` divides by the stationary-bootstrap long-run sd instead and is
    informational. Both are reported whether or not `studentize` is set.
    """
    block_source = "given" if block is not None else "default ceil(2*T^(1/3))"
    obj, d, ids, t_stats, degenerate, _, block = _prepare_spa(returns, benchmark, block, reps, seed, studentize,
                                                              bias_correction)
    t_stat = t_stats[0]
    if obj is None:                                # nothing varies: there is no test (arch would return p = 0)
        out = {"p_lower": float("nan"), "p_consistent": float("nan"), "p_upper": float("nan"), "best": None,
               "block_source": block_source}
        out.update(_common(d, ids, t_stats, degenerate, block, reps, seed, studentize, bias_correction))
        return out
    obj.compute()
    pv = obj.pvalues
    stat = np.where(degenerate, np.nan, t_stat if studentize else d.mean(axis=0))
    best = ids[int(np.nanargmax(stat))] if np.isfinite(stat).any() else None
    out = {"p_lower": float(pv["lower"]), "p_consistent": float(pv["consistent"]), "p_upper": float(pv["upper"]),
           "best": best, "block_source": block_source}
    out.update(_common(d, ids, t_stats, degenerate, block, reps, seed, studentize, bias_correction))
    return out


def stepm(returns, benchmark=None, *, alpha: float = 0.05, block: Optional[int] = None, reps: int = 1000, seed: int,
          studentize: bool = True, bias_correction: bool = True) -> Dict[str, object]:
    """Romano-Wolf (2005) step-down multiple testing (StepM) at FWER level `alpha`, with Hansen's
    consistent recentring (the "Step-SPA" of Hsu, Hsu & Kuan 2010) — the set of strategies whose
    mean return is significantly ABOVE the benchmark's, controlling the probability of ANY false
    inclusion at `alpha`.

    Arguments as `spa`. Results are LABELS: `superior`, `steps[i]["rejected"]`, `degenerate` and the
    index of `t_stat` / `mean` are the column names of `returns` (arch's `better_models()` returns
    integer positions; they never leave this module). A bare 2-D array gets the labels 0..K-1.
    Step 1 rejects every strategy whose (studentized) mean exceeds the 1-alpha
    quantile of the bootstrap maximum over ALL strategies; the maximum is then recomputed over the
    survivors only and the test repeated until nothing new is rejected.

    Returns {'superior': [ids, in column order], 'steps': [{'n_tested', 'critical_value',
    'rejected'}], 't_stat', 't_stat_longrun', 'mean', 'degenerate', 'alpha', ...}. `critical_value`
    is in t-statistic units when studentized (comparable with `t_stat` = sqrt(T) mean / sd), else in
    mean-return units, and already includes the bias-correction inflation: a strategy is rejected at
    a step exactly when its statistic exceeds that step's `critical_value`.
    """
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1); got {alpha!r}")
    block_source = "given" if block is not None else "default ceil(2*T^(1/3))"
    obj, d, ids, t_stats, degenerate, crit_scale, block = _prepare_spa(returns, benchmark, block, reps, seed,
                                                                       studentize, bias_correction)
    kept = np.flatnonzero(~degenerate)             # arch position -> column position (degenerates are left out)
    selector = np.ones(len(kept), dtype=bool)
    rejected: List[int] = []
    steps = []
    while selector.any():                          # arch's own loop tests len(last batch) < k and can run dry
        obj.subset(selector.copy())
        obj.compute()
        crit = float(obj.critical_values(pvalue=alpha)["consistent"])
        new = [int(i) for i in obj.better_models(pvalue=alpha, pvalue_type="consistent")]
        steps.append({"n_tested": int(selector.sum()), "critical_value": crit * crit_scale,
                      "rejected": [ids[kept[i]] for i in new]})
        if not new:
            break
        rejected.extend(int(kept[i]) for i in new)
        selector[new] = False
    out = {"superior": [ids[i] for i in sorted(rejected)], "steps": steps, "alpha": float(alpha),
           "block_source": block_source}
    out.update(_common(d, ids, t_stats, degenerate, block, reps, seed, studentize, bias_correction))
    return out


def white_reality_check(returns, benchmark=None, *, block: Optional[int] = None, reps: int = 1000,
                        seed: int) -> Dict[str, object]:
    """White's (2000) Reality Check p-value for H0 "the best strategy does not beat the benchmark".

    The statistic is the UN-studentized max_k sqrt(T) mean(returns_k - benchmark) and every model
    is recentred — arch's SPA "upper" p-value on raw differentials. Kept for reference: it is
    conservative when the family contains poor strategies and is driven by the most volatile one;
    prefer `spa` (studentized, consistent). No studentization and no bias correction are applied
    here: this is the literal test. Returns {'p_value', 'best', 't_stat', 'mean', ...}.
    """
    block_source = "given" if block is not None else "default ceil(2*T^(1/3))"
    obj, d, ids, t_stats, degenerate, _, block = _prepare_spa(returns, benchmark, block, reps, seed, studentize=False,
                                                              bias_correction=False)
    if obj is None:                                # nothing varies: there is no test
        out = {"p_value": float("nan"), "best": None, "block_source": block_source}
        out.update(_common(d, ids, t_stats, degenerate, block, reps, seed, False, False))
        return out
    obj.compute()
    out = {"p_value": float(obj.pvalues["upper"]),
           "best": ids[int(np.nanargmax(np.where(degenerate, np.nan, d.mean(axis=0))))], "block_source": block_source}
    out.update(_common(d, ids, t_stats, degenerate, block, reps, seed, False, False))
    return out


# --------------------------------------------------------------------------------------------------
# Probability of backtest overfitting (CSCV)
# --------------------------------------------------------------------------------------------------
def pbo_cscv(returns, S: int = 16) -> Dict[str, object]:
    """Probability of Backtest Overfitting by combinatorially symmetric cross-validation
    (Bailey, Borwein, Lopez de Prado & Zhu 2017, "The probability of backtest overfitting").

    1. `returns` (T x N, per-print returns of N strategy configurations, N >= 2, no NaN) is cut into
       `S` (even) consecutive blocks of floor(T / S) rows; the EARLIEST T mod S rows are dropped.
    2. For every way of choosing S/2 blocks as the in-sample (IS) set — C(S, S/2) combinations,
       12,870 for S = 16 — the other S/2 blocks are the out-of-sample (OOS) set.
    3. Performance is the per-print Sharpe mean / std(ddof=1). Let n* be the IS-best configuration,
       r its OOS rank among the N (1 = worst, N = best; ties share the average rank),
       w = r / (N + 1) and the logit lambda = ln(w / (1 - w)).
    4. PBO = the share of combinations with lambda <= 0: the IS-best is at or below the OOS median.
       (<= rather than <: an exact tie with the median counts as overfit — the conservative side.)
    5. Performance degradation: the OLS line  OOS Sharpe of n* = intercept + slope * IS Sharpe of n*
       across combinations. A negative slope says the harder a configuration was fitted in-sample,
       the worse it did out of sample.

    Returns {'pbo', 'logits' (array, one per combination), 'slope', 'intercept', 'prob_oos_loss'
    (share of combinations where n* has a negative OOS Sharpe), 'is_best_counts' ({id: how often it
    was the IS-best}), 'n_combinations', 'n_strategies', 'rows_per_block', 'n_rows_dropped', 'S'}.

    LIMITS: a configuration with zero variance on an IS (OOS) set has no Sharpe; it is treated as the
    worst there. Pure noise gives PBO around 0.5 only ON AVERAGE: the combinations of one sample are
    heavily dependent, so a single PBO is a noisy number. PBO says nothing about whether the best
    configuration is profitable, only whether choosing by IS rank carried over.
    """
    if isinstance(returns, pd.DataFrame):
        ids = list(returns.columns)
        m = returns.to_numpy(dtype=np.float64)
    else:
        m = np.asarray(returns, dtype=np.float64)
        if m.ndim != 2:
            raise ValueError("returns must be a (T x N) DataFrame or 2-D array")
        ids = list(range(m.shape[1]))
    if isinstance(S, bool) or not isinstance(S, (int, np.integer)) or S < 2 or S % 2:
        raise ValueError(f"S must be an even integer >= 2; got {S!r}")
    t, n = m.shape
    if n < 2:
        raise ValueError("PBO needs at least two strategy configurations")
    if not np.isfinite(m).all():
        raise ValueError("returns contain NaN or inf")
    rows = t // S
    if rows < 2:
        raise ValueError(f"T = {t} gives {rows} row(s) per block with S = {S}; need >= 2")
    dropped = t - rows * S
    blocks = m[dropped:].reshape(S, rows, n)
    b_sum = blocks.sum(axis=1)                                          # (S, N)
    b_sq = (blocks * blocks).sum(axis=1)
    tot_sum, tot_sq = b_sum.sum(axis=0), b_sq.sum(axis=0)
    half = S // 2
    n_half = half * rows
    combos = np.array(list(itertools.combinations(range(S), half)), dtype=np.intp)

    def sharpe(s: np.ndarray, sq: np.ndarray) -> np.ndarray:
        """Per-print Sharpe from block sums; -inf ("worst") where the variance is zero up to rounding."""
        mean = s / n_half
        var = (sq - n_half * mean * mean) / (n_half - 1)
        has_var = var > 1e-12 * (sq / n_half)                           # relative: sums of squares cancel
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(has_var, mean / np.sqrt(np.where(has_var, var, 1.0)), -np.inf)

    logits = np.empty(len(combos))
    is_best_sr = np.empty(len(combos))
    oos_best_sr = np.empty(len(combos))
    best = np.empty(len(combos), dtype=np.intp)
    chunk = max(1, 2_000_000 // n)                                      # <= ~16 MB of float64 per work array
    for lo in range(0, len(combos), chunk):
        sel = np.zeros((len(combos[lo:lo + chunk]), S))
        np.put_along_axis(sel, combos[lo:lo + chunk], 1.0, axis=1)
        is_sum, is_sq = sel @ b_sum, sel @ b_sq
        sr_is = sharpe(is_sum, is_sq)
        sr_oos = sharpe(tot_sum - is_sum, tot_sq - is_sq)
        star = sr_is.argmax(axis=1)
        rows_i = np.arange(len(star))
        mine = sr_oos[rows_i, star]
        less = (sr_oos < mine[:, None]).sum(axis=1)
        equal = (sr_oos == mine[:, None]).sum(axis=1)                   # includes n* itself
        rank = less + (equal + 1) / 2.0
        w = rank / (n + 1.0)
        logits[lo:lo + chunk] = np.log(w / (1.0 - w))
        is_best_sr[lo:lo + chunk] = sr_is[rows_i, star]
        oos_best_sr[lo:lo + chunk] = mine
        best[lo:lo + chunk] = star

    ok = np.isfinite(is_best_sr) & np.isfinite(oos_best_sr)
    slope = intercept = float("nan")
    if ok.sum() >= 2 and np.ptp(is_best_sr[ok]) > 1e-12 * max(1.0, float(np.abs(is_best_sr[ok]).max())):
        slope, intercept = (float(v) for v in np.polyfit(is_best_sr[ok], oos_best_sr[ok], 1))
    counts = np.bincount(best, minlength=n)
    return {
        "pbo": float((logits <= 0.0).mean()),
        "logits": logits,
        "slope": slope,
        "intercept": intercept,
        "prob_oos_loss": float((oos_best_sr < 0.0).mean()),
        "is_best_counts": {ids[i]: int(c) for i, c in enumerate(counts) if c},
        "n_combinations": int(len(combos)),
        "n_strategies": int(n),
        "rows_per_block": int(rows),
        "n_rows_dropped": int(dropped),
        "S": int(S),
    }


# --------------------------------------------------------------------------------------------------
# Circular-shift max-statistic null (adapted from the v1 draft nulls.py)
# --------------------------------------------------------------------------------------------------
def circular_shift_null(
    panel: PanelBundle,
    w_by_id: Mapping[str, pd.DataFrame],
    *,
    window: Window,
    cost_bp_side: CostSpec,
    seed: int,
    n_rep: int = 500,
    min_shift: Optional[int] = None,
    lag: int = 1,
    hold_cost_long_bp_year: CostSpec = 0.0,
    hold_cost_short_bp_year: CostSpec = 0.0,
    exec_prices: Optional[pd.DataFrame] = None,
    extra_lag: int = 0,
    hac_lags: int = 5,
    max_bytes: int = 1_500_000_000,
    turnover_model: str = "drift",
) -> Dict[str, object]:
    """The max-statistic null obtained by circularly shifting every formula's positions in time.

    WHAT IT TESTS: timing. In each replicate the positions actually held inside the scoring window
    are rolled by ONE random offset u, the SAME for every formula, against the unshifted returns
    and carry. That preserves each formula's position autocorrelation, turnover and costs, the
    cross-formula correlation, and the returns' own dynamics; it destroys only the alignment
    between WHEN a position was held and WHAT the market then did. The distribution of the maximum
    statistic over formulas across replicates is the bar a best-of-K formula must clear.

    EXACTLY:
      1. Each formula is run through `engine.backtest` on the FULL panel (warm-up included) with the
         given costs, `missing_return="zero"` and the given `turnover_model` (default "drift", the
         engine's default, so the observed statistics are the ledger's). Its `held` matrix H
         (T_w x N), its per-print cost + hold cost C (T_w) and its net are cut to the scoring
         `window` (T_w rows). Statistics are computed ONLY on those rows.
      2. x = returns + carry on the window rows, NaN -> 0 (T_w x N).
      3. Replicate j draws u_j uniformly from {min_shift, ..., T_w - min_shift} and scores
             net'_t = SUM_i H[(t - u) mod T_w, i] * x[t, i]  -  C[(t - u) mod T_w]
         i.e. positions AND the costs they incurred move together, so every replicate pays exactly
         the real total cost and no artificial trade appears at the seam.
      4. Per replicate: the Newey-West t (`hac_lags`) and the annualised Sharpe of every formula's
         net'; the maximum over formulas of each, and which formula attained it.

    Returns a dict with `p95_max_hac_t`, `p50_max_hac_t`, `p95_max_sharpe`, `p50_max_sharpe`, the
    distributions `max_hac_t` / `max_sharpe` (arrays of length n_rep), `argmax_hac_t_ids` /
    `argmax_sharpe_ids`, the `offsets`, the observed (unshifted) `observed_hac_t` / `observed_sharpe`
    per formula, `observed_max_hac_t`, `observed_argmax_id`, `p_value_max_hac_t`
    = (1 + #{max_t* >= observed max}) / (1 + n_rep), the single-step max-T adjusted p-value of every
    formula `adjusted_p` = (1 + #{max_t* >= t_obs_f}) / (1 + n_rep), and bookkeeping.

    STATED LIMITS
      * A static or slowly varying exposure that earns a persistent premium (carry, a long-only
        book in excess returns) is IN this null by construction: shifting a constant position
        changes nothing (exactly nothing under turnover_model="target"; under "drift" only its
        small re-balancing costs land on other prints, moving the statistic in the fifth digit).
        Clearing this bar is evidence of timing skill, failing it is not evidence that a premium
        is absent. Read it beside StepM/SPA, not instead of them.
      * A rolled position can land where the instrument has no return (not yet listed, delisted);
        it earns 0 there. `mean_frac_exposure_on_missing` reports how much of the rolled exposure
        that is; on panels with many listings the replicates are less invested than the real book.
      * `min_shift` (default: one year of prints) keeps a shifted book from overlapping its own
        momentum; the window must hold at least 2 * min_shift prints.
    """
    if not w_by_id:
        raise Refused("circular_shift_null needs at least one formula")
    if isinstance(n_rep, bool) or not isinstance(n_rep, (int, np.integer)) or n_rep < 1:
        raise Refused(f"n_rep must be an integer >= 1; got {n_rep!r}")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise Refused(f"seed must be an integer; got {seed!r}")
    if window is None:
        raise Refused("window is required: pass (start, end) — (None, None) scores every row, explicitly")
    ids = list(w_by_id)
    cols = list(panel.prices.columns)
    ppy = float(panel.periods_per_year)
    mask = window_mask(panel.prices.index, window)
    tw = int(mask.sum())
    if min_shift is None:
        min_shift = int(round(ppy))
    if isinstance(min_shift, bool) or not isinstance(min_shift, (int, np.integer)) or min_shift < 1:
        raise Refused(f"min_shift must be an integer >= 1; got {min_shift!r}")
    if tw < 2 * min_shift:
        raise Refused(
            f"the scoring window has {tw} prints; the offset range [{min_shift}, {tw - min_shift}] is empty. "
            f"The null needs at least 2 * min_shift = {2 * min_shift} prints."
        )
    need = len(ids) * tw * len(cols) * 8
    if need > max_bytes:
        raise Refused(
            f"{len(ids)} formulas x {tw} prints x {len(cols)} instruments needs {need / 1e9:.2f} GB for the "
            f"held stack (> max_bytes = {max_bytes / 1e9:.2f} GB). Run the null in batches of formulas with "
            f"the SAME seed and take the per-replicate maximum across batches."
        )

    H = np.empty((len(ids), tw, len(cols)), dtype=np.float64)
    C = np.empty((len(ids), tw), dtype=np.float64)
    obs_net = np.empty((len(ids), tw), dtype=np.float64)
    n_nan_w = 0
    priced_on = "prices"
    for f, name in enumerate(ids):
        res = backtest(panel, w_by_id[name], lag=lag, cost_bp_side=cost_bp_side,
                       hold_cost_long_bp_year=hold_cost_long_bp_year,
                       hold_cost_short_bp_year=hold_cost_short_bp_year, exec_prices=exec_prices,
                       extra_lag=extra_lag, missing_return="zero", turnover_model=turnover_model)
        H[f] = res.held.to_numpy()[mask]
        C[f] = (res.cost.to_numpy() + res.hold_cost.to_numpy())[mask]
        obs_net[f] = res.net.to_numpy()[mask]
        n_nan_w += res.meta["n_nan_w"]
        priced_on = res.meta["priced_on"]
        shift = res.meta["shift"]

    px = (panel.prices if exec_prices is None else exec_prices[cols]).to_numpy(dtype=np.float64)
    r = np.full(px.shape, np.nan)
    r[1:] = px[1:] / px[:-1] - 1.0
    r = r[mask]
    missing = np.isnan(r)
    x = np.where(missing, 0.0, r)
    if panel.carry is not None:
        c = panel.carry[cols].to_numpy(dtype=np.float64)[mask]
        x = x + np.where(np.isnan(c), 0.0, c)
    sqrt_ppy = math.sqrt(ppy)

    def score(net: np.ndarray) -> tuple:
        """(hac_t[F], sharpe[F]) of an (F, T_w) net matrix."""
        t_stat = np.asarray(newey_west_t(net.T, hac_lags), dtype=np.float64).reshape(-1)
        sd = net.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sh = np.where(sd > 0, net.mean(axis=1) / sd * sqrt_ppy, np.nan)
        return t_stat, sh

    obs_t, obs_sh = score(obs_net)

    rng = np.random.default_rng(int(seed))
    offsets = rng.integers(min_shift, tw - min_shift, size=int(n_rep), endpoint=True)
    max_t = np.full(int(n_rep), np.nan)
    max_sh = np.full(int(n_rep), np.nan)
    arg_t: List[Optional[str]] = [None] * int(n_rep)
    arg_sh: List[Optional[str]] = [None] * int(n_rep)
    abs_h = np.abs(H).sum(axis=0)                                       # (T_w, N) exposure summed over formulas
    total_exposure = float(abs_h.sum())
    frac_missing = np.zeros(int(n_rep))
    for j, u in enumerate(offsets):
        u = int(u)
        # net'[f, t] = SUM_i H[f, t-u, i] x[t, i] - C[f, t-u]: roll x back by u, contract, roll the result forward by u
        g = np.einsum("ftn,tn->ft", H, np.roll(x, -u, axis=0))
        t_stat, sh = score(np.roll(g - C, u, axis=1))
        if np.isfinite(t_stat).any():
            k = int(np.nanargmax(t_stat))
            max_t[j], arg_t[j] = t_stat[k], ids[k]
        if np.isfinite(sh).any():
            k = int(np.nanargmax(sh))
            max_sh[j], arg_sh[j] = sh[k], ids[k]
        if total_exposure > 0:
            frac_missing[j] = float((abs_h * np.roll(missing, -u, axis=0)).sum()) / total_exposure

    fin_t = max_t[np.isfinite(max_t)]
    fin_sh = max_sh[np.isfinite(max_sh)]
    obs_max = float(np.nanmax(obs_t)) if np.isfinite(obs_t).any() else float("nan")

    def adj(t_value: float) -> float:
        return float((1 + (fin_t >= t_value).sum()) / (1 + len(fin_t))) if np.isfinite(t_value) else float("nan")

    def quant(a: np.ndarray, q: float) -> float:
        return float(np.quantile(a, q)) if len(a) else float("nan")

    win_idx = panel.prices.index[mask]
    return {
        "p95_max_hac_t": quant(fin_t, 0.95),
        "p50_max_hac_t": quant(fin_t, 0.50),
        "p95_max_sharpe": quant(fin_sh, 0.95),
        "p50_max_sharpe": quant(fin_sh, 0.50),
        "max_hac_t": max_t,
        "max_sharpe": max_sh,
        "argmax_hac_t_ids": arg_t,
        "argmax_sharpe_ids": arg_sh,
        "offsets": offsets,
        "observed_hac_t": {i: float(v) for i, v in zip(ids, obs_t)},
        "observed_sharpe": {i: float(v) for i, v in zip(ids, obs_sh)},
        "observed_max_hac_t": obs_max,
        "observed_argmax_id": ids[int(np.nanargmax(obs_t))] if np.isfinite(obs_t).any() else None,
        "p_value_max_hac_t": adj(obs_max),
        "adjusted_p": {i: adj(float(v)) for i, v in zip(ids, obs_t)},
        "n_rep": int(n_rep),
        "n_rep_finite": int(len(fin_t)),
        "seed": int(seed),
        "min_shift": int(min_shift),
        "offset_range": (int(min_shift), int(tw - min_shift)),
        "window": (win_idx[0].isoformat(), win_idx[-1].isoformat()),
        "n_window_rows": tw,
        "n_formulas": len(ids),
        "n_instruments": len(cols),
        "hac_lags": int(hac_lags),
        "shift": int(shift),
        "priced_on": priced_on,
        "turnover_model": turnover_model,
        "n_nan_w_zeroed": int(n_nan_w),
        "n_nan_return_cells_in_window": int(missing.sum()),
        "mean_frac_exposure_on_missing": float(frac_missing.mean()) if total_exposure > 0 else 0.0,
        "missing_return_policy": "zero",
        "method": (
            "per replicate ONE offset u ~ U{min_shift..T_w-min_shift} shared by all formulas; the held matrix "
            "and the cost series of the scoring window are rolled by u against unshifted returns + carry; "
            "max over formulas of the Newey-West t and of the Sharpe; quantiles by np.quantile (linear)"
        ),
    }


__all__ = [
    "bh_fdr", "by_fdr", "holm", "spa", "stepm", "white_reality_check", "stationary_long_run_variance",
    "variance_bias_factor",
    "pbo_cscv", "circular_shift_null", "sharpe_ci_bootstrap",
]
