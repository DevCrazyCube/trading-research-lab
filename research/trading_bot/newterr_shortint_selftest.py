#!/usr/bin/env python3
"""Harness self-test. Must pass before any design number is believed.

1) PLANTED EDGE: score = the return the position will actually earn (t+LAG+1..t+LAG+H).
   Must produce a large positive net Sharpe. If it does not, the plumbing is wrong.
2) SIGN FLIP: the negated planted score must produce the mirror-image Sharpe.
3) RANDOM NULL: 40 iid random scores. |t| must look like N(0,1): mean |t| ~ 0.8,
   and max|t| must be near sqrt(2 ln 40) = 2.72, not far above it.
4) NO-LOOKAHEAD: the planted edge must COLLAPSE when the plant is shifted so that it
   describes a window the position no longer holds.
"""
import json, numpy as np, sys
sys.path.insert(0, "/home/anont/meme/research/trading_bot")
import newterr_shortint_sweep as SW

P = SW.load()
B = SW.build_bases(P)
dates = B["dates"]
d0, d1 = SW.WINDOWS["design"]
j0 = max(int(np.searchsorted(dates, d0)), SW.WARMUP + 30)
j1 = int(np.searchsorted(dates, d1, side="right")) - 1
print("selftest window", dates[j0], dates[j1], j1 - j0 + 1)

R1 = np.nan_to_num(B["R1"], nan=0.0).astype(np.float64)
D = B["D"]
CR = np.concatenate([np.zeros((B["S"], 1)), np.cumsum(R1, 1)], 1)

out = {}
H, LAG = 5, 1


def fwd_panel(off):
    """cumulative return over sessions (t+off+1 .. t+off+H), as an (S,D) panel."""
    F = np.full((B["S"], D), np.nan, np.float64)
    for t in range(D):
        a, b = t + off + 1, t + off + H
        if b < D:
            F[:, t] = CR[:, b + 1] - CR[:, a]
    return F


def run_score(F, label):
    fn = lambda t, m, _F=F: SW.xrank(_F[:, t], m)
    W, nu, nd = SW.weights(B, fn, j0 - 40, j1)
    net, g, tc, bc = SW.simulate(B, W, H, LAG, j0, j1)
    sh = net.mean() / net.std() * np.sqrt(252)
    t, _ = SW.nw_t(net, H + 1)
    print(f"  {label:28s} net SR {sh:+7.2f}  t {t:+8.2f}  univ {nu:.0f}")
    return float(sh), float(t)


print("1) planted edge (perfect foresight over the exact held window)")
F = fwd_panel(LAG)
out["planted"] = run_score(F, "planted +")
print("2) sign flip")
out["planted_flip"] = run_score(-F, "planted -")
print("4) no-lookahead: plant shifted back so it describes an already-past window")
out["planted_shift_back"] = run_score(fwd_panel(LAG - 3 * H), "plant on a past window")

print("3) random null, 40 draws x 4 horizons -- GROSS t (the multiple-testing statistic)")
rng = np.random.default_rng(20260820)
null = {}
for HH in SW.HORIZONS:
    tg, tn, cost = [], [], []
    for i in range(40):
        Z = rng.standard_normal((B["S"], D))
        fn = lambda t, m, _Z=Z: SW.xrank(_Z[:, t], m)
        W, nu, nd = SW.weights(B, fn, j0 - 40, j1)
        net, g, tc, bc = SW.simulate(B, W, HH, LAG, j0, j1)
        a, _ = SW.nw_t(g, HH + 1)
        b, _ = SW.nw_t(net, HH + 1)
        tg.append(float(a)); tn.append(float(b)); cost.append(float((tc + bc).mean() * 1e4))
    tg, tn = np.array(tg), np.array(tn)
    print(f"  H={HH:2d} GROSS |t| mean {np.abs(tg).mean():.2f} max {np.abs(tg).max():.2f} "
          f"| NET t mean {tn.mean():+.2f} | cost {np.mean(cost):.2f} bp/day")
    null[HH] = {"gross_mean_abs_t": float(np.abs(tg).mean()), "gross_max_abs_t": float(np.abs(tg).max()),
                "gross_sd_t": float(tg.std()), "net_mean_t": float(tn.mean()),
                "cost_bp_day": float(np.mean(cost))}
out["null_by_horizon"] = null
out["null_note"] = ("The NET t-stat is NOT a null-centred statistic: a random formula pays a "
                    "deterministic turnover cost, so its net t is large and NEGATIVE. The "
                    "multiple-testing bar sqrt(2 ln N) is therefore applied to the GROSS t, and "
                    "profitability is gated separately on net mean > 0. The first run of this "
                    "self-test applied the bar to the net t and the null came back at |t|=13; "
                    "that is what caught it.")
gm = max(v["gross_mean_abs_t"] for v in null.values())
gx = max(v["gross_max_abs_t"] for v in null.values())
out["verdict"] = {
    "planted_positive": bool(out["planted"][0] > 3),
    "sign_flip_mirrors": bool(out["planted"][0] * out["planted_flip"][0] < 0),
    "shifted_plant_collapses": bool(abs(out["planted_shift_back"][0]) < 0.35 * abs(out["planted"][0])),
    "gross_null_behaves": bool(gm < 1.6 and gx < 4.0),
    "gross_null_mean_abs_t": round(gm, 3), "gross_null_max_abs_t": round(gx, 3),
}
print(json.dumps(out["verdict"], indent=1))
json.dump(out, open("/home/anont/meme/research/trading_bot/NEWTERR_shortint_SELFTEST.json", "w"), indent=1)
