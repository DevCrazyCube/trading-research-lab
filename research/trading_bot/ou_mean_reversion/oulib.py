#!/usr/bin/env python3
"""Pure-numpy OU / ADF / Hurst / Bertram library for the mean-reversion audit.
No scipy/statsmodels available, so everything is implemented from scratch."""
from __future__ import annotations
import numpy as np


# ----------------------------------------------------------------- OU fit (AR1/MLE)
def fit_ou(s, dt=1.0):
    """Fit OU dX = theta*(mu - X)dt + sigma dW to an evenly-sampled series s (spacing dt).
    Exact discrete MLE via the AR(1) representation:
        X_{t+1} = a + b X_t + eps,  b = exp(-theta*dt),
        eps var = sigma_eq^2 (1-b^2),  sigma_eq^2 = sigma^2/(2 theta).
    Returns dict with theta, mu, sigma (diffusion), sigma_eq (stationary sd),
    half_life (in units of dt), phi=b, resid sd, n."""
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    n = s.size
    x = s[:-1]
    y = s[1:]
    xm = x.mean(); ym = y.mean()
    Sxx = np.sum((x - xm) ** 2)
    Sxy = np.sum((x - xm) * (y - ym))
    b = Sxy / Sxx
    a = ym - b * xm
    resid = y - (a + b * x)
    sigeps = resid.std(ddof=2)
    b = min(max(b, 1e-8), 0.999999999)  # keep in (0,1) for a reverting fit
    theta = -np.log(b) / dt
    mu = a / (1.0 - b)
    sigma_eq = sigeps / np.sqrt(1.0 - b * b) if b < 1 else float("nan")
    sigma = sigma_eq * np.sqrt(2.0 * theta)
    half_life = np.log(2.0) / theta
    return dict(theta=float(theta), mu=float(mu), sigma=float(sigma),
                sigma_eq=float(sigma_eq), half_life=float(half_life),
                phi=float(b), resid_sd=float(sigeps), n=int(n))


# ----------------------------------------------------------------- ADF test
def adf(s, maxlag=None):
    """Augmented Dickey-Fuller with a constant (no trend). Returns (tstat, used_lag, n).
    Regression: dX_t = c + rho*X_{t-1} + sum_i gamma_i dX_{t-i} + e.
    t-stat on rho. Compare to MacKinnon constant-only critical values:
        1% -3.43, 5% -2.86, 10% -2.57 (asymptotic)."""
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    n0 = s.size
    dx = np.diff(s)
    if maxlag is None:
        maxlag = int(np.floor(12 * (n0 / 100.0) ** 0.25))
        maxlag = min(maxlag, n0 // 3)
    # pick lag by minimizing BIC over 0..maxlag (cheap)
    best = None
    for lag in range(0, maxlag + 1):
        T = dx.size - lag
        if T < 20:
            continue
        Y = dx[lag:]
        cols = [np.ones(T), s[lag:-1] if lag > 0 else s[:-1]]
        # X_{t-1} aligned to dX_t: level at index (t-1). dx index i corresponds to level s[i].
        lvl = s[lag:-1]
        cols = [np.ones(T), lvl]
        for i in range(1, lag + 1):
            cols.append(dx[lag - i: -i] if i != 0 else dx)
        X = np.column_stack(cols)
        beta, res, rank, sv = np.linalg.lstsq(X, Y, rcond=None)
        resid = Y - X @ beta
        rss = np.sum(resid ** 2)
        k = X.shape[1]
        sigma2 = rss / T
        bic = T * np.log(sigma2 + 1e-300) + k * np.log(T)
        if best is None or bic < best[0]:
            # t-stat on rho (2nd coef)
            XtX_inv = np.linalg.inv(X.T @ X)
            se = np.sqrt(sigma2 * T / (T - k) * XtX_inv[1, 1])
            tstat = beta[1] / se
            best = (bic, float(tstat), lag, T)
    if best is None:
        return dict(tstat=float("nan"), lag=0, n=0)
    return dict(tstat=best[1], lag=best[2], n=best[3])


ADF_CV = {"1%": -3.43, "5%": -2.86, "10%": -2.57}


def adf_verdict(t):
    if not np.isfinite(t):
        return "n/a"
    if t < ADF_CV["1%"]:
        return "reject@1%"
    if t < ADF_CV["5%"]:
        return "reject@5%"
    if t < ADF_CV["10%"]:
        return "reject@10%"
    return "FAIL(unit root)"


# ----------------------------------------------------------------- Hurst exponent
def hurst_rs(s, min_win=8, max_frac=0.5):
    """Rescaled-range (R/S) Hurst exponent on the series' increments.
    H<0.5 mean-reverting, 0.5 random walk, >0.5 trending."""
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    x = np.diff(s)  # increments; R/S on increments measures persistence of the level
    N = x.size
    if N < 4 * min_win:
        return float("nan")
    max_win = int(N * max_frac)
    wins = np.unique(np.floor(np.logspace(np.log10(min_win),
                                          np.log10(max_win), 12)).astype(int))
    logn, logrs = [], []
    for w in wins:
        if w < min_win or w > N:
            continue
        nseg = N // w
        rs_vals = []
        for k in range(nseg):
            seg = x[k * w:(k + 1) * w]
            m = seg.mean()
            y = np.cumsum(seg - m)
            R = y.max() - y.min()
            S = seg.std()
            if S > 0:
                rs_vals.append(R / S)
        if rs_vals:
            logn.append(np.log(w))
            logrs.append(np.log(np.mean(rs_vals)))
    if len(logn) < 4:
        return float("nan")
    A = np.column_stack([np.ones(len(logn)), logn])
    coef, *_ = np.linalg.lstsq(A, np.array(logrs), rcond=None)
    return float(coef[1])


# ----------------------------------------------------------------- OU first-passage time
def ou_mfpt(a, m, theta, sigma_eq, ngrid=4001):
    """Mean first-passage time for the OU (mean 0, stationary sd sigma_eq, rate theta)
    starting at level a to reach level m, a>m>=0 (upper->lower toward the mean) OR
    the symmetric a<m case. Uses the scale/speed-density double integral.
    dX = -theta X dt + sigma dW,  sigma = sigma_eq*sqrt(2 theta).
    s(y)=exp(theta y^2 / sigma_eq^2 /... ) ; computed in z=X/sigma_eq units where it is a
    standard OU with rate theta and diffusion sqrt(2 theta): mfpt scales as 1/theta * f(a_z,m_z)."""
    # work in z units: az=a/sigma_eq, mz=m/sigma_eq ; standard OU dz=-theta z dt + sqrt(2 theta) dW
    # scale density  s(y)=exp(y^2/2)   speed density  m(y)=exp(-y^2/2)/(2 theta)
    # UPWARD passage x->b (b>x):   E = 2 int_x^b s(y) [int_{-inf}^y m(z)dz] dy
    # DOWNWARD passage x->b (b<x): E = 2 int_b^x s(y) [int_y^{+inf} m(z)dz] dy
    az = a / sigma_eq
    mz = m / sigma_eq
    lo, hi = min(az, mz), max(az, mz)
    yy = np.linspace(lo, hi, ngrid)
    sfun = np.exp(yy ** 2 / 2.0)
    zz = np.linspace(-14.0, 14.0, 8001)
    dens = np.exp(-zz ** 2 / 2.0) / (2.0 * theta)
    # cumulative from -inf and complementary from +inf
    cum = np.concatenate([[0.0], np.cumsum((dens[1:] + dens[:-1]) / 2.0 * np.diff(zz))])
    if az > mz:  # DOWNWARD (start hi=az, target lo=mz): inner = int_y^{+inf}
        inner = cum[-1] - np.interp(yy, zz, cum)
    else:        # UPWARD (start lo=az, target hi=mz): inner = int_{-inf}^y
        inner = np.interp(yy, zz, cum)
    T = np.trapezoid(2.0 * sfun * inner, yy)
    return float(T)


def bertram_optimal(theta, sigma_eq, cost_frac, exit_grid=None, entry_grid=None):
    """Numerically maximize expected NET return per unit time over (entry a, exit m) for an
    OU trade that enters short at +a (or long at -a), holds until the spread reverts to +m.
    Distances in the spread's own units. cost_frac = round-trip cost as a fraction (same units
    as the spread, i.e. log-spread). Returns best (a_z, m_z, obj, e_time_yrs, net_per_trade).
    a_z,m_z are in sigma_eq (z-score) units. Objective = net_per_trade / E[time]."""
    cz = cost_frac / sigma_eq
    if entry_grid is None:
        entry_grid = np.linspace(0.5, 4.0, 60)
    if exit_grid is None:
        exit_grid = np.linspace(0.0, 1.5, 25)
    best = None
    for a in entry_grid:
        for m in exit_grid:
            if m >= a:
                continue
            gross_z = (a - m)               # captured reversion in z units
            net_z = gross_z - cz
            if net_z <= 0:
                continue
            # E[time] from a down to m for standard OU, real time = mfpt(z)/theta already in theta units
            Et = ou_mfpt(a * sigma_eq, m * sigma_eq, theta, sigma_eq)
            if Et <= 0:
                continue
            obj = net_z / Et                # per unit (dt) time, in z units
            if best is None or obj > best["obj"]:
                best = dict(a_z=float(a), m_z=float(m), obj=float(obj),
                            E_time_dt=float(Et), net_per_trade_frac=float(net_z * sigma_eq))
    return best


if __name__ == "__main__":
    # self-test on a synthetic OU with known half-life
    rng = np.random.default_rng(0)
    theta_true, mu_true, sigeq_true = 0.2, 0.0, 0.05
    phi = np.exp(-theta_true)
    sige = sigeq_true * np.sqrt(1 - phi * phi)
    n = 6000
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = mu_true + phi * (x[t - 1] - mu_true) + rng.normal(0, sige)
    f = fit_ou(x)
    print("fit:", {k: round(v, 4) for k, v in f.items()})
    print("true half-life:", round(np.log(2) / theta_true, 3), "fitted:", round(f["half_life"], 3))
    print("ADF:", adf(x), adf_verdict(adf(x)["tstat"]))
    print("Hurst:", round(hurst_rs(x), 3))
    print("Bertram:", bertram_optimal(f["theta"], f["sigma_eq"], cost_frac=0.002))
