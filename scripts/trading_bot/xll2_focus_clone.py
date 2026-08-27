#!/usr/bin/env python3
"""FOCUSED PASS, chosen AFTER seeing the parent block -- labelled as such, with its own bar.

The only family in the 49-formula intraday sweep whose design gross Sharpe clears the noise bar
by a wide margin is D (clone / dual-listed / same-exposure ETF pairs) and, less so, E
(leveraged-vs-base tracking gap). Both die on cost by 30-100x: breakeven 0.03-0.29 bp per side
against a 1-6 bp tier. The fair last question is whether the gross survives when the turnover is
cut hard, and whether it survives on the ONE clone group where a 1 bp fill is defensible
(SPY/IVV/VOO/SPLG, all >$2B a day).

Held-out numbers are reported here for the survivors because that is the point of the pass.
"""
from __future__ import annotations
import importlib.util, json
import numpy as np

SRC = "/home/anont/meme/scripts/trading_bot/xll2_sweep_intraday.py"
OUT = "/home/anont/meme/research/trading_bot/SWEEP_xll_leadlag_v2_clone_focus.json"
N_NULL = 200


def main():
    spec = importlib.util.spec_from_file_location("xll2", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    c = m.build_ctx()
    I = c.idx
    rng = np.random.default_rng(7)
    T = c.r.shape[1]
    base = rng.integers(m.BARS_PER_DAY, T // 8, size=N_NULL // 2)
    shifts = np.concatenate([base, -base])

    def clonegap(k, groups, sign=+1.0):
        def f(cc):
            W = np.zeros_like(cc.r)
            for g in groups:
                mm = [I[s] for s in g if s in I]
                if len(mm) < 2:
                    continue
                rk = m.roll_k(cc.r[mm], k)
                W[mm] = sign * (rk.mean(0, keepdims=True) - rk) * m.armed(cc, k)
            return m.xs_demean(W, cc.u_clone)
        return f

    BIG = [["SPY", "IVV", "VOO", "SPLG"]]
    ALL = m.CLONES
    cfgs = [
        ("F1_clone_k12_h39", "all clone groups, hourly gap, held 39 bars (half a session)", clonegap(12, ALL), 39),
        ("F2_clone_k39_h39", "all clone groups, half-session gap, held half a session", clonegap(39, ALL), 39),
        ("F3_clone_k39_h78", "all clone groups, half-session gap, held a full session", clonegap(39, ALL), 78),
        ("F4_bigclone_k1_h1", "ONLY the SPY/IVV/VOO/SPLG group (every leg >$2B/day, a 1bp fill is defensible), 5-minute gap", clonegap(1, BIG), 1),
        ("F5_bigclone_k3_h3", "ONLY the SPY/IVV/VOO/SPLG group, 15-minute gap", clonegap(3, BIG), 3),
        ("F6_bigclone_k12_h12", "ONLY the SPY/IVV/VOO/SPLG group, hourly gap", clonegap(12, BIG), 12),
        ("F7_bigclone_k39_h39", "ONLY the SPY/IVV/VOO/SPLG group, half-session gap", clonegap(39, BIG), 39),
        ("F8_clone_ex_illiquid", "all clone groups but only legs above $300M/day (drops SPLG/QQQM/VTWO/SOXX-tier staleness)", None, 3),
    ]

    def clonegap_liquid(k):
        def f(cc):
            W = np.zeros_like(cc.r)
            for g in ALL:
                mm = [I[s] for s in g if s in I]
                if len(mm) < 2:
                    continue
                rk = m.roll_k(cc.r[mm], k)
                W[mm] = (rk.mean(0, keepdims=True) - rk) * m.armed(cc, k)
            liq = cc.adv > 3e8
            return m.xs_demean(np.where(liq, W, 0.0), cc.u_clone & liq)
        return f

    cfgs[7] = ("F8_clone_ex_illiquid", cfgs[7][1], clonegap_liquid(3), 3)

    rows, nulls = [], []
    for name, desc, fn, hold in cfgs:
        W = fn(c)
        res, Wn = m.score(c, W, hold)
        res.update(name=name, formula_desc=desc, hold_bars=hold)
        # cost ladder on the SAME weights
        for bp in (0.5, 1.0, 2.0, 5.0):
            dW = np.abs(Wn - m.lag(Wn, 1)).sum(0).astype(np.float64)
            pr = np.einsum("it,it->t", Wn, c.R).astype(np.float64)
            g = m.sess_pnl(c, pr - dW * bp * 1e-4)
            d = c.sess_design
            res[f"net_sharpe_at_{bp}bp_design"] = float(g[d].mean() / g[d].std() * np.sqrt(252.0))
            res[f"net_sharpe_at_{bp}bp_holdout"] = float(g[~d].mean() / g[~d].std() * np.sqrt(252.0))
        rows.append(res)
        nulls.append(m.null_sharpes(c, Wn, shifts))
        print(f"  {name:22s} gross={res['gross_sharpe']:+6.2f} ho={res['holdout_gross_sharpe']:+6.2f} "
              f"tno/d={res['turnover_per_day']:7.2f} be_d={res['breakeven_bp_per_side_design']:5.3f} "
              f"be_h={res['breakeven_bp_per_side_holdout']:5.3f}", flush=True)
        del W, Wn

    NULL = np.array(nulls)
    mx = NULL.max(axis=0)
    out = dict(block="intraday_clone_pair_FOCUS",
               provenance="POST-HOC: these 8 configs were chosen after seeing the 49-formula parent block. Their own noise bar is reported; they must not be counted as independent discoveries.",
               n_formulas=len(rows),
               null=dict(n_draws=int(NULL.shape[1]), sd_single_config_sharpe=float(NULL.std()),
                         expected_max_sharpe=float(mx.mean()), p95_max_sharpe=float(np.percentile(mx, 95))),
               results=sorted(rows, key=lambda r: -r["gross_sharpe"]))
    json.dump(out, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "results"}, indent=1))
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
