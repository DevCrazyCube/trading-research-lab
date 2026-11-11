"""stats.py — per-series statistics (DESIGN_v2 §3.2). Pure float64 functions; nothing here runs a backtest.

The engine computes no statistics. The runner calls `summarize(result.net, window=(start, end), ...)`
on an EXPLICIT date window, so warm-up rows (where the book is flat because its lookbacks are not
yet filled) are never scored — they would dilute every mean and every t-statistic.

Every definition is written out, because a Sharpe without its definition is not a number.
`x` is the per-print net return inside the scored window, `n` its length, `ppy` = periods_per_year.

  n_obs        n
  start, end   first / last scored timestamp (ISO-8601 string; None for a bare array)
  ann_return   mean(x) * ppy                       ARITHMETIC, not compounded
  cagr         (PROD(1 + x))^(ppy / n) - 1         -1.0 if the curve touches zero or below
  ann_vol      std(x, ddof=1) * sqrt(ppy)
  sharpe       mean(x) / std(x, ddof=1) * sqrt(ppy)          NaN if std = 0 or n < 2
  hac_t        Newey-West t-statistic of mean(x): Bartlett kernel, `hac_lags` lags,
               S = g_0 + 2 SUM_{l=1..L} (1 - l/(L+1)) g_l,  g_l = (1/n) SUM_{t>l} d_t d_{t-l},  d = x - mean,
               t = mean / sqrt(S / n). No small-sample correction. This equals statsmodels
               OLS(x ~ 1).fit(cov_type="HAC", cov_kwds={"maxlags": L, "use_correction": False}) — the
               statsmodels default — to ~1e-12 (tests/test_stats.py). NaN if n <= L + 1.
  p_one_sided  1 - Phi(hac_t): the normal one-sided p-value of H0 "mean <= 0"
  sortino      mean(x) / sqrt(mean(min(x, 0)^2)) * sqrt(ppy)   (target 0; downside deviation over ALL n)
  max_drawdown min_t (E_t / max_{s<=t} E_s - 1) on E = cumprod(1 + x) WITH E_{-1} = 1 included as a
               peak; a NEGATIVE fraction (0.0 = never under water, floor -1.0)
  calmar       cagr / |max_drawdown|                NaN if max_drawdown = 0
  skew         m3 / m2^1.5        (population moments, i.e. scipy.stats.skew(bias=True))
  excess_kurt  m4 / m2^2 - 3      (population moments; 0 for a normal)
  hit_rate     #{x > 0} / #{x != 0}: the share of NON-FLAT prints that made money (flat prints carry
               no information about the rule); NaN if every print is flat
  worst_print  min(x)
  worst_21     min over every 21 consecutive prints of PROD(1 + x) - 1; NaN if n < 21
  avg_gross_leverage      mean of the engine's `gross_leverage` over the window (NaN if not given)
  turnover_sides_per_year mean of the engine's `turnover` * ppy               (NaN if not given).
               `result.turnover` is the turnover the engine CHARGED (drift model by default);
               pass `result.turnover_target` for the change of the target alone.
  breakeven_cost_bp_side  1e4 * mean(gross) / mean(turnover): the per-side cost in bp that would
               consume the whole gross return. `gross` is price + carry BEFORE trading and hold costs,
               so with non-zero hold costs the cost at which NET = 0 is lower by
               1e4 * mean(hold_cost) / mean(turnover); pass `gross - hold_cost` for that reading.
               NaN without gross and turnover, or when mean turnover is 0.
  beta, alpha_ann, alpha_t   OLS x_t = a + b * benchmark_t + e_t on the window, HAC covariance with the
               same kernel and lags (no small-sample correction; = statsmodels HAC to ~1e-10);
               alpha_ann = a * ppy, alpha_t = a / se_HAC(a). NaN without a benchmark.
  psr0         Probabilistic Sharpe Ratio against a true Sharpe of 0 (Bailey & Lopez de Prado 2012):
               Phi( sr * sqrt(n - 1) / sqrt(1 - skew * sr + (kurt - 1)/4 * sr^2) ), sr = mean/std
               PER PRINT, kurt = excess_kurt + 3.

STATED LIMITS
  * Degenerate statistics (n too small, zero variance) are NaN, never an exception. STRUCTURAL
    errors raise ValueError: a NaN inside the scored window, a companion series that does not cover
    the window, a window on a series without a tz-aware DatetimeIndex.
  * `hac_lags` is a fixed integer (5 by contract), not a data-driven bandwidth.
  * The normal p-value ignores the sampling error of the HAC variance; with few effective
    observations it is optimistic. The bootstrap and the multiple-testing layer (`mtest.py`) exist
    for that reason.
"""
from __future__ import annotations

import math
from typing import Dict, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from scipy import stats as sps

EULER_GAMMA = 0.5772156649015329
BLOCK_FACTOR = 2.0             # default mean block length = ceil(BLOCK_FACTOR * T^(1/3)); see default_block_length
ArrayLike = Union[pd.Series, np.ndarray, Sequence[float]]
Window = Optional[Tuple[object, object]]

STAT_KEYS = (
    "n_obs", "start", "end", "ann_return", "cagr", "ann_vol", "sharpe", "hac_t", "p_one_sided", "sortino",
    "max_drawdown", "calmar", "skew", "excess_kurt", "hit_rate", "worst_print", "worst_21",
    "avg_gross_leverage", "turnover_sides_per_year", "breakeven_cost_bp_side", "beta", "alpha_ann", "alpha_t",
    "psr0",
)
NAN = float("nan")


# --------------------------------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------------------------------
def _bound(x, *, end_of_day: bool) -> pd.Timestamp:
    """A window bound as a UTC timestamp, with EXACTLY the semantics of `PanelBundle.window`:
    a date-only bound (a 'YYYY-MM-DD' string, or any midnight timestamp used as an END) covers the
    whole UTC day. Pinned to `PanelBundle.window` in tests/test_stats.py."""
    ts = pd.Timestamp(x)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    date_only = isinstance(x, str) and len(x.strip()) <= 10
    if end_of_day and (date_only or ts == ts.normalize()):
        ts = ts.normalize() + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return ts


def window_mask(index: pd.Index, window: Window) -> np.ndarray:
    """Boolean mask of the rows with start <= t <= end (inclusive; either bound may be None = open).

    `window=None` selects every row. Otherwise `index` must be a tz-aware DatetimeIndex.
    """
    n = len(index)
    if window is None:
        return np.ones(n, dtype=bool)
    if not isinstance(window, (tuple, list)) or len(window) != 2:
        raise ValueError(f"window must be (start, end); got {window!r}")
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("a date window needs a series with a tz-aware DatetimeIndex")
    start, end = window
    mask = np.ones(n, dtype=bool)
    lo = hi = None
    if start is not None:
        lo = _bound(start, end_of_day=False)
        mask &= np.asarray(index >= lo)
    if end is not None:
        hi = _bound(end, end_of_day=True)
        mask &= np.asarray(index <= hi)
    if lo is not None and hi is not None and lo > hi:
        raise ValueError(f"window start {lo} is after its end {hi}")
    return mask


def _scored(net: ArrayLike, window: Window) -> Tuple[np.ndarray, Optional[pd.Index], np.ndarray]:
    """(values inside the window, their index or None, the mask over the original rows)."""
    if isinstance(net, pd.Series):
        mask = window_mask(net.index, window)
        vals = net.to_numpy(dtype=np.float64)[mask]
        idx: Optional[pd.Index] = net.index[mask]
    else:
        if window is not None:
            raise ValueError("a date window needs a pandas Series with a tz-aware DatetimeIndex")
        vals = np.asarray(net, dtype=np.float64).reshape(-1)
        mask = np.ones(len(vals), dtype=bool)
        idx = None
    if not np.isfinite(vals).all():
        raise ValueError("net has NaN/inf inside the scored window; statistics refuse to skip prints silently")
    return vals, idx, mask


def _companion(x, name: str, net: ArrayLike, idx: Optional[pd.Index], mask: np.ndarray) -> Optional[np.ndarray]:
    """A series that must cover the scored window (gross, turnover, leverage, benchmark) as an array."""
    if x is None:
        return None
    if isinstance(x, pd.Series) and idx is not None:
        if not x.index.is_unique:
            raise ValueError(f"{name} has a non-unique index")
        missing = idx.difference(x.index)
        if len(missing):
            raise ValueError(f"{name} does not cover the scored window: {len(missing)} prints missing, first {missing[0]}")
        vals = x.reindex(idx).to_numpy(dtype=np.float64)
    else:
        arr = np.asarray(x, dtype=np.float64).reshape(-1)
        if len(arr) != len(mask):
            raise ValueError(f"{name} has {len(arr)} rows but net has {len(mask)}")
        vals = arr[mask]
    if not np.isfinite(vals).all():
        raise ValueError(f"{name} has NaN/inf inside the scored window")
    return vals


# --------------------------------------------------------------------------------------------------
# Newey-West
# --------------------------------------------------------------------------------------------------
def newey_west_t(x: ArrayLike, lags: int = 5) -> Union[float, np.ndarray]:
    """Newey-West t-statistic of the mean (Bartlett kernel), vectorised over columns.

    x: (T,) or (T, F). Per column: d = x - mean, g_l = (1/T) SUM_{t>l} d_t d_{t-l},
    S = g_0 + 2 SUM_{l=1}^{L} (1 - l/(L+1)) g_l, t = mean / sqrt(S / T). No small-sample correction
    (statsmodels' `use_correction=False`, its default for HAC). NaN where T <= L + 1 or S <= 0.
    """
    lags = int(lags)
    if lags < 0:
        raise ValueError(f"lags must be >= 0; got {lags}")
    arr = np.asarray(x, dtype=np.float64)
    one_d = arr.ndim == 1
    if one_d:
        arr = arr[:, None]
    T = arr.shape[0]
    out = np.full(arr.shape[1], np.nan)
    if T <= lags + 1:
        return float(out[0]) if one_d else out
    m = arr.mean(axis=0)
    d = arr - m
    S = (d * d).sum(axis=0) / T
    for l in range(1, lags + 1):
        S = S + 2.0 * (1.0 - l / (lags + 1.0)) * (d[l:] * d[:-l]).sum(axis=0) / T
    with np.errstate(divide="ignore", invalid="ignore"):
        se = np.sqrt(S / T)
        t = np.where(se > 0, m / se, np.nan)
    return float(t[0]) if one_d else t


def hac_ols(y: ArrayLike, X: np.ndarray, lags: int = 5) -> Tuple[np.ndarray, np.ndarray]:
    """OLS coefficients and their Newey-West (Bartlett, `lags`, no small-sample correction) covariance.

    beta = (X'X)^-1 X'y ; u = y - X beta ; g_t = X_t u_t ;
    S = G_0 + SUM_{l=1..L} (1 - l/(L+1)) (G_l + G_l'),  G_l = SUM_{t>l} g_t g_{t-l}' ;
    cov = (X'X)^-1 S (X'X)^-1. Equals statsmodels OLS(...).fit(cov_type="HAC", cov_kwds={"maxlags": L}).
    """
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 2 or X.shape[0] != len(y):
        raise ValueError("X must be (n, k) with n = len(y)")
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    g = X * (y - X @ beta)[:, None]
    S = g.T @ g
    for l in range(1, int(lags) + 1):
        G = g[l:].T @ g[:-l]
        S = S + (1.0 - l / (lags + 1.0)) * (G + G.T)
    return beta, xtx_inv @ S @ xtx_inv


def beta_alpha(net: ArrayLike, benchmark: ArrayLike, periods_per_year: float, hac_lags: int = 5) -> Dict[str, float]:
    """OLS net_t = a + b * bench_t with HAC(hac_lags): {'beta', 'alpha_ann', 'alpha_t'}.

    alpha_ann = a * periods_per_year; alpha_t = a / se_HAC(a). All NaN if n <= hac_lags + 2 or the
    benchmark is constant; alpha_t is NaN if the fit is exact (zero residual variance).
    """
    y = np.asarray(net, dtype=np.float64).reshape(-1)
    b = np.asarray(benchmark, dtype=np.float64).reshape(-1)
    out = {"beta": NAN, "alpha_ann": NAN, "alpha_t": NAN}
    n = len(y)
    if len(b) != n:
        raise ValueError("net and benchmark must have the same length")
    if n <= hac_lags + 2 or not np.isfinite(y).all() or not np.isfinite(b).all() or np.ptp(b) == 0.0:
        return out
    coef, cov = hac_ols(y, np.column_stack([np.ones(n), b]), hac_lags)
    out["beta"] = float(coef[1])
    out["alpha_ann"] = float(coef[0] * periods_per_year)
    se = math.sqrt(cov[0, 0]) if cov[0, 0] > 0 else 0.0
    resid_scale = float(np.abs(y - coef[0] - coef[1] * b).max())
    if se > 0 and resid_scale > 1e-14 * max(1.0, float(np.abs(y).max())):
        out["alpha_t"] = float(coef[0] / se)
    return out


# --------------------------------------------------------------------------------------------------
# Plain performance numbers
# --------------------------------------------------------------------------------------------------
def sharpe_ratio(x: ArrayLike, periods_per_year: float) -> float:
    """mean / std(ddof=1) * sqrt(periods_per_year); NaN if n < 2, non-finite input or std == 0."""
    arr = np.asarray(x, dtype=np.float64).reshape(-1)
    if len(arr) < 2 or not np.isfinite(arr).all():
        return NAN
    sd = arr.std(ddof=1)
    if sd == 0.0:
        return NAN
    return float(arr.mean() / sd * math.sqrt(periods_per_year))


def equity_curve(net: ArrayLike) -> np.ndarray:
    """E_t = PROD_{s<=t} (1 + net_s), t = 0..n-1 (the starting equity E_{-1} = 1 is NOT in the array)."""
    return np.cumprod(1.0 + np.asarray(net, dtype=np.float64).reshape(-1))


def max_drawdown(net: ArrayLike) -> float:
    """min_t (E_t / max_{s<=t} E_s - 1) on the compounded curve, the starting equity 1.0 counting as
    a peak. <= 0; 0.0 = never under water; -1.0 once the curve touches zero or below.

    (The v1 draft took the running peak over E_0.. only, so a book that lost from its very first
    print reported a drawdown of 0.)
    """
    arr = np.asarray(net, dtype=np.float64).reshape(-1)
    if len(arr) == 0 or not np.isfinite(arr).all():
        return NAN
    eq = np.concatenate([[1.0], equity_curve(arr)])
    if (eq <= 0.0).any():
        return -1.0
    return float(min((eq / np.maximum.accumulate(eq) - 1.0).min(), 0.0))


def cagr(net: ArrayLike, periods_per_year: float) -> float:
    """(E_n)^(ppy/n) - 1; -1.0 if the curve touches zero or below at any print; NaN if n = 0."""
    arr = np.asarray(net, dtype=np.float64).reshape(-1)
    n = len(arr)
    if n == 0 or not np.isfinite(arr).all():
        return NAN
    eq = equity_curve(arr)
    if (eq <= 0.0).any():
        return -1.0
    return float(eq[-1] ** (periods_per_year / n) - 1.0)


def worst_window(net: ArrayLike, k: int = 21) -> float:
    """The worst compounded return over any `k` consecutive prints: min_t PROD_{s=t-k+1..t}(1+x_s) - 1.
    NaN if n < k."""
    arr = np.asarray(net, dtype=np.float64).reshape(-1)
    if len(arr) < k or not np.isfinite(arr).all():
        return NAN
    windows = np.lib.stride_tricks.sliding_window_view(1.0 + arr, k)
    return float(windows.prod(axis=1).min() - 1.0)


def _moments(x: np.ndarray) -> Tuple[float, float]:
    """(skew, Pearson kurtosis) from population moments; NaN if n < 2 or the variance is 0."""
    if len(x) < 2:
        return NAN, NAN
    d = x - x.mean()
    m2 = float((d * d).mean())
    if m2 <= 0.0:
        return NAN, NAN
    return float((d ** 3).mean() / m2 ** 1.5), float((d ** 4).mean() / m2 ** 2)


# --------------------------------------------------------------------------------------------------
# Probabilistic / deflated Sharpe (Bailey & Lopez de Prado 2012, 2014)
# --------------------------------------------------------------------------------------------------
def psr(sr: float, sr0: float, n: int, skew: float, kurt: float) -> float:
    """Probabilistic Sharpe Ratio: P[true SR > sr0] given an estimate `sr` over `n` prints.

    PSR = Phi[(sr - sr0) sqrt(n - 1) / sqrt(1 - skew*sr + (kurt - 1)/4 * sr^2)]. `sr`, `sr0` are PER
    PRINT (not annualised); `kurt` is Pearson kurtosis (3 for a normal). NaN if n < 2, an input is
    not finite, or the variance term is not positive.
    """
    if n < 2 or not all(np.isfinite([sr, sr0, skew, kurt])):
        return NAN
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0.0:
        return NAN
    return float(sps.norm.cdf((sr - sr0) * math.sqrt(n - 1.0) / math.sqrt(denom)))


def expected_max_sharpe(n_trials: int, var_sharpe: float) -> float:
    """E[max of `n_trials` independent zero-skill Sharpe estimates] (Bailey & Lopez de Prado 2014):
    sqrt(V) * ((1 - g) * Phi^-1(1 - 1/N) + g * Phi^-1(1 - 1/(N e))), g = Euler-Mascheroni.

    `var_sharpe` (V) is the cross-trial variance of the ESTIMATED Sharpes, in the SAME units as the
    Sharpe being deflated (per print for `deflated_sharpe`). N <= 1 or V <= 0 -> 0.0 (no selection).
    LIMIT: assumes independent trials; correlated trials have a smaller effective N, so this is an
    upper bound on the hurdle when the trials are positively correlated.
    """
    n = int(n_trials)
    if n <= 1 or not np.isfinite(var_sharpe) or var_sharpe <= 0.0:
        return 0.0
    z1 = sps.norm.ppf(1.0 - 1.0 / n)
    z2 = sps.norm.ppf(1.0 - 1.0 / (n * math.e))
    return float(math.sqrt(var_sharpe) * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def deflated_sharpe(
    net: ArrayLike,
    *,
    n_trials: int,
    var_sharpe_trials: Optional[float] = None,
    window: Window = None,
) -> Dict[str, object]:
    """Deflated Sharpe Ratio of `net` after `n_trials` trials: PSR against SR0 = expected_max_sharpe.

    `var_sharpe_trials` is the variance, ACROSS the trials, of their estimated PER-PRINT Sharpes —
    the runner knows it once the grid has run and should pass it. If it is None the function says
    so in `var_source` and uses 1/(n-1), the sampling variance of a per-print Sharpe under a true
    Sharpe of 0 and normal returns, i.e. "all trials are zero-skill and independent". That
    understates V when the trials' true Sharpes are dispersed (SR0 too low, DSR too high).

    Returns {'dsr', 'sr_per_print', 'sr0_per_print', 'var_sharpe_used', 'var_source', 'n_trials',
    'n_obs', 'skew', 'kurt'}; 'dsr' is NaN for a degenerate series.
    """
    x, _, _ = _scored(net, window)
    n = len(x)
    out: Dict[str, object] = {
        "dsr": NAN, "sr_per_print": NAN, "sr0_per_print": NAN, "var_sharpe_used": NAN,
        "var_source": "supplied" if var_sharpe_trials is not None else "assumed_1_over_n_minus_1",
        "n_trials": int(n_trials), "n_obs": int(n), "skew": NAN, "kurt": NAN,
    }
    if n < 3 or x.std(ddof=1) == 0.0:
        return out
    sr = float(x.mean() / x.std(ddof=1))
    skew, kurt = _moments(x)
    var_used = float(var_sharpe_trials) if var_sharpe_trials is not None else 1.0 / (n - 1.0)
    sr0 = expected_max_sharpe(n_trials, var_used)
    out.update({"dsr": psr(sr, sr0, n, skew, kurt), "sr_per_print": sr, "sr0_per_print": sr0,
                "var_sharpe_used": var_used, "skew": skew, "kurt": kurt})
    return out


def min_track_record_length(sr: float, sr0: float = 0.0, *, skew: float = 0.0, kurt: float = 3.0,
                            alpha: float = 0.05) -> float:
    """Minimum number of PRINTS for PSR(sr0) to reach 1 - alpha (Bailey & Lopez de Prado 2012):

        MinTRL = 1 + (1 - skew*sr + (kurt - 1)/4 * sr^2) * (Phi^-1(1 - alpha) / (sr - sr0))^2

    `sr`, `sr0` per print; `kurt` Pearson (3 = normal). inf if sr <= sr0; NaN on non-finite input or
    a non-positive variance term.
    """
    if not all(np.isfinite([sr, sr0, skew, kurt, alpha])) or not (0.0 < alpha < 1.0):
        return NAN
    if sr <= sr0:
        return float("inf")
    v = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if v <= 0.0:
        return NAN
    return float(1.0 + v * (sps.norm.ppf(1.0 - alpha) / (sr - sr0)) ** 2)


# --------------------------------------------------------------------------------------------------
# The ledger row
# --------------------------------------------------------------------------------------------------
def summarize(
    net: ArrayLike,
    *,
    periods_per_year: float,
    window: Window = None,
    gross: Optional[ArrayLike] = None,
    turnover: Optional[ArrayLike] = None,
    gross_leverage: Optional[ArrayLike] = None,
    benchmark: Optional[ArrayLike] = None,
    hac_lags: int = 5,
) -> Dict[str, object]:
    """One statistics row for the per-print net return `net`, scored ONLY inside `window`.

    net             Series on a tz-aware DatetimeIndex (required when `window` is given) or an array.
    window          (start, end), inclusive, either bound None = open; a date-only bound covers the
                    whole UTC day, exactly as `PanelBundle.window`. None = every row of `net`.
    gross, turnover, gross_leverage   the engine's series (same index); the dependent keys are NaN
                    when they are not supplied.
    benchmark       per-print return of the benchmark on the same prints (for beta / alpha).

    Returns a dict with exactly the keys of `STAT_KEYS`, defined in the module docstring. An empty
    window returns n_obs = 0 and NaN statistics.
    """
    ppy = float(periods_per_year)
    if not np.isfinite(ppy) or ppy <= 0:
        raise ValueError(f"periods_per_year must be > 0; got {periods_per_year!r}")
    x, idx, mask = _scored(net, window)
    g = _companion(gross, "gross", net, idx, mask)
    to = _companion(turnover, "turnover", net, idx, mask)
    lev = _companion(gross_leverage, "gross_leverage", net, idx, mask)
    bench = _companion(benchmark, "benchmark", net, idx, mask)
    n = len(x)

    def stamp(i: int):
        if idx is None or n == 0:
            return None
        v = idx[i]
        return v.isoformat() if isinstance(v, pd.Timestamp) else str(v)

    out: Dict[str, object] = {k: NAN for k in STAT_KEYS}
    out.update({"n_obs": int(n), "start": stamp(0), "end": stamp(-1)})
    if n == 0:
        return out

    mean = float(x.mean())
    sd = float(x.std(ddof=1)) if n > 1 else NAN
    out["ann_return"] = mean * ppy
    out["cagr"] = cagr(x, ppy)
    out["ann_vol"] = sd * math.sqrt(ppy) if n > 1 else NAN
    out["sharpe"] = sharpe_ratio(x, ppy)
    out["hac_t"] = float(newey_west_t(x, hac_lags))
    out["p_one_sided"] = float(sps.norm.sf(out["hac_t"])) if np.isfinite(out["hac_t"]) else NAN
    downside = math.sqrt(float((np.minimum(x, 0.0) ** 2).mean()))
    out["sortino"] = mean / downside * math.sqrt(ppy) if downside > 0 else NAN
    out["max_drawdown"] = max_drawdown(x)
    mdd = out["max_drawdown"]
    out["calmar"] = out["cagr"] / abs(mdd) if np.isfinite(mdd) and mdd < 0 else NAN
    skew, kurt = _moments(x)
    out["skew"] = skew
    out["excess_kurt"] = kurt - 3.0 if np.isfinite(kurt) else NAN
    n_active = int((x != 0.0).sum())
    out["hit_rate"] = float((x > 0.0).sum() / n_active) if n_active else NAN
    out["worst_print"] = float(x.min())
    out["worst_21"] = worst_window(x, 21)
    if lev is not None:
        out["avg_gross_leverage"] = float(lev.mean())
    if to is not None:
        out["turnover_sides_per_year"] = float(to.mean() * ppy)
        if g is not None and to.mean() > 0.0:
            out["breakeven_cost_bp_side"] = float(1e4 * g.mean() / to.mean())
    if bench is not None:
        out.update(beta_alpha(x, bench, ppy, hac_lags))
    if n > 1 and sd > 0 and np.isfinite(skew):
        out["psr0"] = psr(mean / sd, 0.0, n, skew, kurt)
    return out


def evidence_table(
    net: ArrayLike,
    windows: Mapping[str, Tuple[object, object]],
    ppy: float,
    *,
    gross: Optional[ArrayLike] = None,
    turnover: Optional[ArrayLike] = None,
    gross_leverage: Optional[ArrayLike] = None,
    benchmark: Optional[ArrayLike] = None,
    hac_lags: int = 5,
) -> pd.DataFrame:
    """`summarize` once per named window: a DataFrame indexed by window name (in the given order)
    with the `STAT_KEYS` columns. `windows` maps a label to (start, end); None bounds are open, so
    FULL = (design_start, None) and LAST-5 = (last - 5 years, None) are written by the caller.
    """
    if not windows:
        raise ValueError("evidence_table needs at least one window")
    rows = {
        name: summarize(net, periods_per_year=ppy, window=tuple(win), gross=gross, turnover=turnover,
                        gross_leverage=gross_leverage, benchmark=benchmark, hac_lags=hac_lags)
        for name, win in windows.items()
    }
    table = pd.DataFrame.from_dict(rows, orient="index", columns=list(STAT_KEYS))
    table.index.name = "window"
    return table


# --------------------------------------------------------------------------------------------------
# Stationary bootstrap (Politis & Romano 1994)
# --------------------------------------------------------------------------------------------------
def default_block_length(n_obs: int, factor: float = BLOCK_FACTOR) -> int:
    """The default MEAN block length of the stationary bootstrap: ceil(factor * T^(1/3)), factor = 2.

    WHY T^(1/3): the mean-squared-error-optimal block length for estimating the variance of a mean
    grows like T^(1/3) (Politis & White 2004; Patton, Politis & White 2009). arch's own fallback,
    sqrt(T), grows too fast: at T = 4,400 it gives 66 against 33 here, and the bootstrap's variance
    estimate is biased down by about (2 * block - 1) / T (see mtest.py): 3.0 % against 1.5 %.
    WHY factor 2: for an AR(1) return series with coefficient rho the optimum is
        b* = (2 rho / (1 - rho^2))^(2/3) * T^(1/3),
    i.e. 0.34 T^(1/3) at rho = 0.1, 0.76 at rho = 0.3, 1.0 at rho = 0.41 and 2.0 at rho = 0.71. Daily
    net returns of the books scored here have a first-order autocorrelation of a few hundredths to
    perhaps 0.3, so 2 is deliberately on the LONG side, because the two errors are not symmetric:
    a block that is too long costs a known centring bias, which `mtest` corrects; a block that is
    too short leaves kernel-truncation bias under serial dependence, which is unknown, uncorrected
    and anti-conservative. MEASURED 2026-11-10 (family-wise error of the bias-corrected StepM at a
    nominal 5 %, 30-50 noise strategies x 500 prints, 1,000 panels per figure, SE 0.7 %; two figures
    = two independent sets of panels):
                              white noise      AR(1) 0.1      AR(1) 0.3
        factor 1 (block  8)      5.2 %           5.8 %          7.9 %
        factor 2 (block 16)   4.0 % / 5.5 %      5.5 %       5.8 % / 6.0 %
    Factor 2 keeps the error within about one point of nominal across that range; factor 1 does not.
    Values: T = 500 -> 16, 1,250 -> 22, 4,400 -> 33. It is a default, not an estimate: pass `block`
    explicitly (e.g. from arch.bootstrap.optimal_block_length) when more is known about a series.
    """
    if isinstance(n_obs, (bool, np.bool_)) or not isinstance(n_obs, (int, np.integer)) or n_obs < 1:
        raise ValueError(f"n_obs must be an integer >= 1; got {n_obs!r}")
    if isinstance(factor, (bool, np.bool_)) or not np.isfinite(factor) or factor <= 0:
        raise ValueError(f"factor must be > 0; got {factor!r}")
    # -1e-9: a perfect cube must not be pushed up by a float cube root that lands a hair above the integer
    return max(1, int(math.ceil(factor * n_obs ** (1.0 / 3.0) - 1e-9)))


def indices_from_draws(new_block: np.ndarray, starts: np.ndarray, n: int) -> np.ndarray:
    """Turn raw draws into stationary-bootstrap indices, shape (R, n).

    new_block (R, n) bool — does a new block start at this position? (column 0 is forced True)
    starts    (R, n) int  — the start index drawn for a block that begins at this position
    Position t reads `starts` at the position where its block began, plus its offset inside the
    block, modulo n (blocks wrap around the end of the sample).
    """
    new_block = np.array(new_block, dtype=bool, copy=True)
    new_block[:, 0] = True
    pos = np.arange(new_block.shape[1])
    began = np.maximum.accumulate(np.where(new_block, pos, 0), axis=1)
    return (np.take_along_axis(np.asarray(starts), began, axis=1) + pos - began) % n


def stationary_bootstrap_indices(n: int, block: float, reps: int, rng: np.random.Generator) -> np.ndarray:
    """(reps, n) resampling indices: block lengths are geometric with MEAN `block` (a new block
    starts with probability 1/block at every position), start points uniform, blocks wrap around.
    `block = 1` is the iid bootstrap; a very large `block` is a single circular shift per replicate.
    """
    if n < 1 or reps < 1:
        raise ValueError("n and reps must be >= 1")
    if not np.isfinite(block) or block < 1:
        raise ValueError(f"block (the mean block length) must be >= 1; got {block!r}")
    new_block = rng.random((reps, n)) < 1.0 / float(block)
    starts = rng.integers(0, n, size=(reps, n))
    return indices_from_draws(new_block, starts, n)


def sharpe_ci_bootstrap(
    net: ArrayLike,
    *,
    periods_per_year: float,
    block: Optional[float] = None,
    reps: int = 2000,
    ci: float = 0.90,
    seed: int = 0,
    window: Window = None,
) -> Dict[str, object]:
    """Percentile confidence interval of the annualised Sharpe by the stationary bootstrap.

    Each replicate resamples the scored prints with `stationary_bootstrap_indices` (mean block
    length `block`, in prints; None = `default_block_length(n)` = ceil(2 n^(1/3)), reported in the
    result) and recomputes mean / std(ddof=1) * sqrt(ppy). The interval is the
    [(1-ci)/2, (1+ci)/2] quantiles of the replicates (plain percentile method: no bias correction).
    Seedable and deterministic: the same `seed` gives the same interval.

    Returns {'sharpe', 'lo', 'hi', 'ci', 'se', 'frac_le_zero', 'block', 'reps', 'seed', 'n_obs',
    'n_degenerate'}; `frac_le_zero` is the share of replicates with Sharpe <= 0 (a percentile-
    method tail, NOT a multiplicity-adjusted p-value); `n_degenerate` counts zero-variance replicates
    (excluded from the quantiles).
    LIMITS: `block` is a choice, not estimated (arch.bootstrap.optimal_block_length can inform it);
    the percentile interval is first-order accurate only.
    """
    x, _, _ = _scored(net, window)
    n = len(x)
    ppy = float(periods_per_year)
    if not (0.0 < ci < 1.0):
        raise ValueError(f"ci must be in (0, 1); got {ci!r}")
    if block is None:
        block = default_block_length(max(n, 1))
    out: Dict[str, object] = {"sharpe": sharpe_ratio(x, ppy), "lo": NAN, "hi": NAN, "ci": float(ci), "se": NAN,
                              "frac_le_zero": NAN, "block": float(block), "reps": int(reps), "seed": int(seed),
                              "n_obs": int(n), "n_degenerate": 0}
    if n < 3 or not np.isfinite(out["sharpe"]):
        return out
    rng = np.random.default_rng(seed)
    chunk = max(1, min(int(reps), 2_000_000 // n))        # at most ~2e6 cells (16 MB) per array at a time
    boots = []
    done = 0
    while done < reps:
        r = min(chunk, reps - done)
        sample = x[stationary_bootstrap_indices(n, block, r, rng)]
        sd = sample.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            boots.append(np.where(sd > 0, sample.mean(axis=1) / sd * math.sqrt(ppy), np.nan))
        done += r
    b = np.concatenate(boots)
    ok = b[np.isfinite(b)]
    out["n_degenerate"] = int(len(b) - len(ok))
    if len(ok) >= 2:
        out["lo"] = float(np.quantile(ok, (1.0 - ci) / 2.0))
        out["hi"] = float(np.quantile(ok, (1.0 + ci) / 2.0))
        out["se"] = float(ok.std(ddof=1))
        out["frac_le_zero"] = float((ok <= 0.0).mean())
    return out


# --------------------------------------------------------------------------------------------------
# Concentration
# --------------------------------------------------------------------------------------------------
def contribution_by_instrument(result, window: Window = None) -> pd.DataFrame:
    """Each instrument's contribution to the book's net P&L inside `window`.

    `result` is an `engine.BacktestResult` (its `net_by_instrument`: price + carry - trading cost -
    hold cost per instrument and print). Returns a DataFrame indexed by instrument, sorted by `net`
    descending:
        net        SUM over the window of the instrument's per-print net contribution (arithmetic,
                   in fractions of equity — the same units as SUM of result.net)
        share      net_i / SUM_j net_j: the signed share of the TOTAL. NaN if the total is 0. With
                   offsetting winners and losers a share can exceed 1 or be negative — which is
                   itself the warning that the total rests on few names.
        abs_share  |net_i| / SUM_j |net_j|: always in [0, 1], the concentration measure that stays
                   meaningful when the total is small.
    """
    frame = getattr(result, "net_by_instrument", None)
    if frame is None:
        raise ValueError("result.net_by_instrument is missing; contributions need an engine.BacktestResult")
    mask = window_mask(frame.index, window)
    sums = frame.loc[mask].sum(axis=0)
    total = float(sums.sum())
    abs_total = float(sums.abs().sum())
    out = pd.DataFrame({
        "net": sums,
        "share": sums / total if total != 0.0 else np.nan,
        "abs_share": sums.abs() / abs_total if abs_total != 0.0 else np.nan,
    })
    out.index.name = "instrument"
    return out.sort_values("net", ascending=False, kind="mergesort")


__all__ = [
    "STAT_KEYS", "EULER_GAMMA", "summarize", "evidence_table", "window_mask", "newey_west_t", "hac_ols",
    "beta_alpha", "sharpe_ratio", "equity_curve", "max_drawdown", "cagr", "worst_window", "psr",
    "expected_max_sharpe", "deflated_sharpe", "min_track_record_length", "default_block_length", "BLOCK_FACTOR",
    "indices_from_draws",
    "stationary_bootstrap_indices", "sharpe_ci_bootstrap", "contribution_by_instrument",
]
