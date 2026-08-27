#!/usr/bin/env python3
"""EXO_0822C — is the ex-day residual a withholding-tax / ADR artefact?

The Alpaca cash-dividend record carries a `foreign` flag. For a foreign issue the
published gross rate is NOT what a US holder receives, so the "published tether" is
mis-stated for exactly those names and any residual there is arithmetic, not demand.
This splits the matched-control estimator on that flag, and on multi-record ex-dates.
"""
from __future__ import annotations

import gzip
import json

import numpy as np

from exo0822c_sweep import OUTDIR, Panel, real_returns, shuffle_rate
from exo0822c_diag import clustered_t

ROOTD = OUTDIR.parent


def main():
    P = Panel()
    z = np.load(ROOTD / "data/exo0822c/events.npz", allow_pickle=True)
    clean = z["clean"]
    dates, syms = z["dates"], z["syms"]
    di = {d: k for k, d in enumerate(dates)}
    si = {s: k for k, s in enumerate(syms)}

    ca = json.load(gzip.open(ROOTD / "data/t7_cache/corporate_actions_all.json.gz"))
    foreign = np.zeros((len(dates), len(syms)), bool)
    nrec = np.zeros((len(dates), len(syms)), np.int16)
    for e in ca["cash_dividends"]:
        s, d = e["symbol"], e["ex_date"]
        if s in si and d in di:
            nrec[di[d], si[s]] += 1
            if e.get("foreign"):
                foreign[di[d], si[s]] = True

    r = real_returns(P, shuffle_rate(P.y, P.evd, np.random.default_rng(7)))
    eps = r["eps_h"]
    d, i = P.evd, P.evs
    ON = P.ON
    acc = np.zeros(d.size)
    cnt = np.zeros(d.size)
    for k in [x for x in range(-15, 16) if abs(x) >= 3]:
        dd = np.clip(d + k, 0, P.nd - 1)
        ok = (d + k >= 1) & (d + k < P.nd)
        v = ON[dd, i]
        g = ok & np.isfinite(v) & clean[dd, i]
        acc += np.where(g, v, 0.0)
        cnt += g
    ctrl = np.where(cnt >= 8, acc / np.maximum(cnt, 1), np.nan)
    diff = eps - ctrl

    fo = foreign[d, i]
    nr = nrec[d, i]
    ordinary = P.typ == 0
    out = {}
    for win, sel in (("design", d < P.cut), ("holdout", d >= P.cut)):
        base = ordinary & sel & np.isfinite(diff)
        row = {}
        for lab, m in (("all", base),
                       ("domestic", base & ~fo),
                       ("foreign", base & fo),
                       ("single_record", base & (nr == 1)),
                       ("multi_record", base & (nr > 1))):
            if m.sum() < 5:
                continue
            a, t, nd_ = clustered_t(diff[m], d[m])
            row[lab] = {"bp": a, "t": t, "n": int(m.sum()), "n_days": nd_}
        out[win] = row
    json.dump(out, open(OUTDIR / "INVENT_0822C_gaptether_FOREIGN.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
