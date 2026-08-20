#!/usr/bin/env python3
"""Self-test for the ETF-structural deep mine, run BEFORE the design sweep is believed.

Three probes, on synthetic panels with the real panel's calendar and symbol list:

  NULL       every symbol is an independent geometric random walk, vwap == close.
             Nothing is cointegrated with anything, so every config's BEFORE-COST Sharpe must
             sit inside the sampling noise of zero. A config that shines here is a bug.

  LOOKAHEAD  the same random walks, but vwap[t] is the GEOMETRIC MIDPOINT of close[t-1] and
             close[t] -- i.e. the fill happens halfway through the bar whose close the signal
             is not allowed to know. A rule that peeks one bar ahead now converts that peek
             into free money and lights up enormously. This is the probe that can actually
             catch an off-by-one, which the NULL probe cannot: with vwap == close a one-bar
             leak is invisible on a random walk.

  PLANTED    XLK's log price is its members' equal-weighted log basket PLUS a mean-reverting
             OU deviation. N02 (the plain level z-score against the component sum) must find
             it, and must REVERSE when the plant is negated. A harness that scores the planted
             edge and the sign-flipped plant the same way is measuring its own wiring.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from trading_bot import deepmine_etfstruct as D  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
RNG = np.random.default_rng(7717)
SIG_BAR = 0.0009          # ~20 %/yr at 78 bars/day


class SynthPanel(D.Panel):
    def __init__(self, mode: str, n_days: int = 500):
        z = np.load(D.CACHE / "panel.npz", allow_pickle=False)
        day = z["day"].astype(np.int64)
        keep = day < n_days
        self.day = day[keep]
        self.slot = z["slot"].astype(np.int64)[keep]
        self.daykey = z["daykey"].astype(str)[keep]
        self.syms = [s.replace("_", ".") if s == "BRK_B" else s for s in z["syms"].astype(str)]
        self.idx = {s: i for i, s in enumerate(self.syms)}
        T, S = self.day.size, len(self.syms)
        self.T, self.S = T, S
        first = np.zeros(T, dtype=bool)
        first[0] = True
        first[1:] = self.day[1:] != self.day[:-1]

        L = np.cumsum(RNG.normal(0.0, SIG_BAR, size=(T, S)), axis=0) + np.log(100.0)
        if mode == "planted":
            etf, members = "XLK", D.SYNTH_BASKETS["XLK"]
            ie = self.idx[etf]
            cols = [self.idx[m] for m in members]
            basket = L[:, cols].mean(axis=1)
            theta, ou_sd = 0.05, 0.0025      # half-life ~14 bars
            ou = np.empty(T)
            ou[0] = 0.0
            e = RNG.normal(0.0, ou_sd, size=T)
            for t in range(1, T):
                ou[t] = (1 - theta) * ou[t - 1] + e[t]
            self.plant = ou
            L[:, ie] = basket + ou
        close = np.exp(L)
        if mode == "lookahead":
            vwap = np.exp(0.5 * (L + np.vstack([L[:1], L[:-1]])))
        else:
            vwap = close
        with np.errstate(invalid="ignore"):
            self.logc = np.log(close)
        self.dvol = np.full((T, S), 1e7, dtype=np.float32)
        self.tradable = np.ones((T, S), dtype=bool)
        self.fwd_ret = np.full((T, S), np.nan)
        self.fwd_ret[:-1] = vwap[1:] / vwap[:-1] - 1.0
        r = np.full((T, S), np.nan)
        r[1:] = self.logc[1:] - self.logc[:-1]
        same = np.zeros(T, dtype=bool)
        same[1:] = self.day[1:] == self.day[:-1]
        r[~same] = np.nan
        self.r = r
        self.same_day_back = same
        self.first_bar = first
        last = np.zeros(T, dtype=bool)
        last[:-1] = self.day[1:] != self.day[:-1]
        last[-1] = True
        self.last_bar = last
        self.day_gap = np.ones(int(self.day.max()) + 1)
        self.n_days = int(self.day.max()) + 1


def sweep(P, cfgs, hs_bp):
    rows = []
    mask = np.ones(P.T, dtype=bool)
    for cfg in cfgs:
        W = D.build(P, cfg)
        if W is None:
            continue
        if cfg.get("hold"):
            W = D._norm(D._hold_every(W, P.day, P.slot, cfg["hold"]))
        net, diag = D.evaluate(P, W, mask, hs_bp, bool(cfg.get("overnight")))
        rows.append({"name": cfg["name"], "gross": D.sharpe(diag["gross"]),
                     "net": D.sharpe(net), "turn": diag["daily_turnover"]})
        del W
    return rows


def leak_controls(P):
    """Two DELIBERATELY leaky rules: identical to N02 and O02 except the signal is read at bar
    t instead of bar t-1. They calibrate the LOOKAHEAD probe -- without them, 'the worst config
    scored 2.0' is a number with no scale attached. With them, the reader can see what an
    actual one-bar peek is worth on this panel."""
    out = {}
    T, S = P.T, P.S
    n = D.BARS_PER_DAY * 5

    W = np.zeros((T, S))
    for etf, members in D.SYNTH_BASKETS.items():
        ie, cols = P.col(etf), P.cols(members)
        if ie is None or len(cols) < 2:
            continue
        lb, wts = D._basket_logprice(P, cols, "eq")
        sp = P.logc[:, ie] - lb
        mu, sd = D._nan_roll(sp[:, None], n)
        z = np.clip((sp - mu[:, 0]) / sd[:, 0], -3, 3)      # NO _shift: this is the leak
        s = np.where(np.isfinite(z), -z, 0.0)
        wts = np.where(np.isfinite(wts), wts, 0.0)
        W[:, ie] += s
        W[:, cols] -= s[:, None] * wts
    out["LEAK_N02_no_shift"] = D._norm(W)

    W = np.zeros((T, S))
    for a, b in D.OVERLAP_PAIRS:
        ia, ib = P.col(a), P.col(b)
        if ia is None or ib is None:
            continue
        beta = D._shift(D._rolling_beta(P.r[:, ia], P.r[:, ib], D.BARS_PER_DAY * 20), 1)
        resid = P.r[:, ia] - beta * P.r[:, ib]
        cum = np.cumsum(np.where(np.isfinite(resid), resid, 0.0))
        mu, sd = D._nan_roll(cum[:, None], n)
        z = np.clip((cum - mu[:, 0]) / sd[:, 0], -3, 3)     # NO _shift: this is the leak
        s = np.where(np.isfinite(z) & np.isfinite(beta), -z, 0.0)
        W[:, ia] += s
        W[:, ib] -= s * np.where(np.isfinite(beta), beta, 0.0)
    out["LEAK_O02_no_shift"] = D._norm(W)
    return out


def main():
    cfgs = D.config_list()
    S = len(np.load(D.CACHE / "panel.npz", allow_pickle=False)["syms"])
    hs_bp = np.full(S, 1.0)
    report = {"n_configs": len(cfgs), "probes": {}}

    for mode in ("null", "lookahead"):
        P = SynthPanel(mode)
        rows = sweep(P, cfgs, hs_bp)
        g = np.array([r["gross"] for r in rows if np.isfinite(r["gross"])])
        yrs = P.n_days / 252.0
        se = 1.0 / np.sqrt(yrs)
        worst = sorted(rows, key=lambda r: -(r["gross"] if np.isfinite(r["gross"]) else -9))[:5]
        leaks = {}
        mask = np.ones(P.T, dtype=bool)
        for nm, Wl in leak_controls(P).items():
            _, dg = D.evaluate(P, Wl, mask, hs_bp, False)
            leaks[nm] = round(D.sharpe(dg["gross"]), 3)
        report["probes"][mode] = {
            "leak_controls_gross_sharpe": leaks,
            "n_scored": int(g.size), "years": round(yrs, 2), "one_se_of_sharpe": round(se, 3),
            "gross_mean": float(g.mean()), "gross_sd": float(g.std(ddof=1)),
            "gross_max": float(g.max()), "gross_max_in_se_units": float(g.max() / se),
            "top5": worst,
        }
        print(f"[{mode}] n={g.size} mean={g.mean():+.3f} max={g.max():+.3f} "
              f"({g.max()/se:.1f} SE)  top={worst[0]['name']}  leak_controls={leaks}", flush=True)
        del P

    Pp = SynthPanel("planted")
    hs0 = np.zeros(S)
    base = {r["name"]: r for r in sweep(Pp, [c for c in cfgs if c["name"].startswith("N0")], hs0)}
    Pn = SynthPanel("planted")
    ie = Pn.idx["XLK"]
    Pn.logc[:, ie] -= 2.0 * Pn.plant                      # negate the plant
    Pn.r[1:, ie] = Pn.logc[1:, ie] - Pn.logc[:-1, ie]
    Pn.r[Pn.first_bar, ie] = np.nan
    flip = {r["name"]: r for r in sweep(Pn, [c for c in cfgs if c["name"].startswith("N0")], hs0)}
    report["probes"]["planted"] = {
        "note": "gross Sharpe with zero costs; the plant is an OU deviation of XLK from its own "
                "equal-weighted component basket, half-life ~14 bars",
        "with_plant": {k: round(v["gross"], 3) for k, v in base.items()},
        "with_plant_negated": {k: round(v["gross"], 3) for k, v in flip.items()},
    }
    n2 = base.get("N02_synth_eq_lvl_z390", {}).get("gross", float("nan"))
    print(f"[planted] N02 gross={n2:+.2f}  negated={flip.get('N02_synth_eq_lvl_z390',{}).get('gross',float('nan')):+.2f}",
          flush=True)

    p = OUT / "DEEPMINE_etf_structural_rv_selftest.json"
    p.write_text(json.dumps(report, indent=1))
    print("wrote", p, flush=True)


if __name__ == "__main__":
    main()
