"""POSTURE C2 step 4: power + cost design for the cheapest first RV test in the
least-skewed cross-section (G10 / DM FX).

DISCIPLINE: this file computes ONLY nuisance quantities - the book's daily
volatility and its turnover. It deliberately never computes or prints the book's
mean return. The effect belongs to a separate pre-registered test.
"""
import os

import numpy as np

CACHE = "/home/anont/meme/research/data/c2_cache"
Z = 1.6448536269514722 + 0.8416212335729143     # one-sided a=.05, power .80
RT_BP = 0.431      # CME 6E round trip, computed in c2_costs.py


def load(name):
    z = np.load(os.path.join(CACHE, name + ".npz"), allow_pickle=True)
    return z["dates"], np.array([str(s) for s in z["syms"]]), z["px"]


def rets(name, start=19990104):
    d, s, px = load(name)
    m = d >= start
    d, px = d[m], px[m]
    live = ~np.isnan(px)
    keep = live.sum(0) > 0.5 * len(d)
    px, s, live = px[:, keep], s[keep], live[:, keep]
    dm = live.sum(1) == px.shape[1]           # full cross-section only
    d, px = d[dm], px[dm]
    return d[1:], s, px[1:] / px[:-1] - 1.0


def book(R, lookback, nleg):
    """Dollar-neutral, basket-neutral cross-sectional reversal book.

    Signal: trailing `lookback`-day return relative to the EW basket.
    Long the `nleg` most-lagging, short the `nleg` most-extended, EW, daily reset.
    Returns (weights T x N, book daily return series) - the return series is
    returned for VOLATILITY only.
    """
    T, N = R.shape
    W = np.zeros((T, N))
    for t in range(lookback, T):
        past = np.prod(1.0 + R[t - lookback:t], axis=0) - 1.0
        rel = past - past.mean()
        o = np.argsort(rel)
        W[t, o[:nleg]] = 1.0 / nleg
        W[t, o[-nleg:]] = -1.0 / nleg
    rb = (W * R).sum(1)
    return W, rb


def main():
    d, syms, R = rets("fx_g10")
    print("G10 FX panel: %d currencies (%s), %d complete days, %d..%d"
          % (R.shape[1], " ".join(syms), len(d), d[0], d[-1]))

    print("\n%-6s %-5s %10s %10s %12s %12s %12s"
          % ("look", "nleg", "sd bp/d", "turn/day", "cost bp/d", "MDE bp/d",
             "MDE ann %"))
    for lookback in (1, 5, 21, 63):
        for nleg in (2, 3):
            W, rb = book(R, lookback, nleg)
            use = slice(lookback, len(rb))
            sd = float(np.std(rb[use], ddof=1))
            # one-sided leg turnover per day (sum of |dW|/2 = fraction of the book
            # that must be traded); each unit of turnover pays one round trip
            dW = np.abs(np.diff(W[use], axis=0)).sum(1) / 2.0
            turn = float(dW.mean())
            cost_bp = turn * RT_BP
            T = len(rb[use])
            mde_bp = 1e4 * Z * sd / np.sqrt(T)
            print("%-6d %-5d %10.2f %10.3f %12.4f %12.4f %12.3f"
                  % (lookback, nleg, 1e4 * sd, turn, cost_bp, mde_bp,
                     100.0 * (mde_bp / 1e4) * 252))
    print("\nEFFECT NOT READ: no mean return of any book was computed or printed.")
    print("Round trip used: %.3f bp (CME 6E, 1 tick / notional, see c2_costs.py)"
          % RT_BP)


if __name__ == "__main__":
    main()
