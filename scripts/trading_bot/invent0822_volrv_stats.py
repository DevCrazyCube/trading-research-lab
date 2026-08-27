"""INVENT 0822 vol theme -- null bar, self-test, and the bounce arithmetic."""
import json
import math
import sys

import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
sys.path.insert(0, "/home/anont/meme/research/trading_bot/ou_mean_reversion")
from invent0822_volrv_sweep import (DESIGN_HI, DESIGN_LO, EVAL_PAIRS, HALF_SPREAD,  # noqa
                                    HOLD_HI, HOLD_LO, FEE_BP, build_panel, pair_book,
                                    roll_z, sharpe_stats, win, leg_cost_bp)
import oulib  # noqa: E402

rng = np.random.default_rng(20260822)
pan, X = build_panel()
res = {}

# ------------------------------------------------------------ 1. the rho1 gate
gate = []
for p in EVAL_PAIRS:
    P = pan[p]
    for wname, lo, hi in (("design", DESIGN_LO, DESIGN_HI), ("holdout", HOLD_LO, HOLD_HI)):
        e = win(P["day"], P["e"], lo, hi)
        if len(e) < 100:
            continue
        r1 = float(np.corrcoef(e[:-1], e[1:])[0, 1])
        M = np.cumsum(e)
        gate.append(dict(pair=p, window=wname, n=len(e), sd_e_bp=float(e.std() * 1e4),
                         rho1_de=r1,
                         hurst=float(oulib.hurst_rs(M)),
                         adf_t=float(oulib.adf(M)["tstat"]),
                         adf_verdict=oulib.adf_verdict(oulib.adf(M)["tstat"]),
                         tether_R2=float(1 - np.var(e) / np.var(win(P["day"], P["rA"], lo, hi))),
                         gate_pass=bool(r1 > -0.35)))
res["rho1_gate"] = gate

# ------------------------------------------------------------ 2. bounce arithmetic
# If the lag0 profit is the half-spread bouncing, then
#   lag0 gross bp per unit of |dw|  ~=  the pair's own round-trip half-spread cost.
bounce = []
for p in EVAL_PAIRS:
    P = pan[p]
    z = np.nan_to_num(roll_z(P["e"], 60), nan=0.0)
    sig = np.clip(z, -3, 3) / 3.0
    rows = {}
    for L in (0, 1, 2):
        dd, gr, net, tov = pair_book(P, sig, L)
        g = win(dd, gr, DESIGN_LO, DESIGN_HI)
        rows[f"L{L}_gross_bp_per_day"] = float(np.mean(g) * 1e4)
        rows[f"L{L}_sr"] = sharpe_stats(g)["sr"]
    k = float(np.median(np.abs(P["k"])))
    rt = leg_cost_bp(P["A"], P["B"], k)
    _, gr0, _, tov = pair_book(P, sig, 0)
    g0 = win(P["day"], gr0, DESIGN_LO, DESIGN_HI)
    bounce.append(dict(pair=p, turnover_per_day=tov,
                       lag0_gross_bp_per_unit_turnover=float(np.mean(g0) * 1e4 / max(tov, 1e-9)),
                       modelled_roundtrip_cost_bp=rt,
                       **rows))
res["bounce_arithmetic"] = bounce

# ------------------------------------------------------------ 3. null bootstrap
# circular-shift the SIGNAL of every formula, keep the returns; take the best of N.
raw = json.load(open("/home/anont/meme/research/trading_bot/INVENT_0822_vol_RAW.json"))
N = len(raw)
sigs, rets = [], []
for p in EVAL_PAIRS:
    P = pan[p]
    m = (P["day"] >= DESIGN_LO) & (P["day"] <= DESIGN_HI)
    e = P["e"][m]
    k = P["k"][m]
    z = np.nan_to_num(roll_z(P["e"], 60), nan=0.0)[m]
    sigs.append(np.clip(z, -3, 3) / 3.0)
    rets.append(e / (1.0 + np.abs(k)))
B = 3000
best = np.empty(B)
for b in range(B):
    m = -9.0
    for _ in range(N):
        i = rng.integers(len(sigs))
        s, r = sigs[i], rets[i]
        sh = rng.integers(60, len(s) - 60)
        ss = np.roll(s, sh)
        bk = np.zeros(len(r))
        bk[1:] = -ss[:-1] * r[1:]
        st = sharpe_stats(bk)["sr"]
        if np.isfinite(st) and st > m:
            m = st
    best[b] = m
yrs_typ = float(np.median([r["design_L1_gross"]["yrs"] for r in raw]))
res["null"] = dict(
    N_formulas=N,
    analytic_t_bar_sqrt_2lnN=float(math.sqrt(2 * math.log(N))),
    median_design_years=yrs_typ,
    analytic_expected_max_sharpe=float(math.sqrt(2 * math.log(N)) / math.sqrt(yrs_typ)),
    bootstrap_expected_max_sharpe=float(best.mean()),
    bootstrap_p95=float(np.percentile(best, 95)),
    bootstrap_p99=float(np.percentile(best, 99)),
    B=B)

# ------------------------------------------------------------ 4. self-test
st = {}
P = pan["UVXY_VIXY"]
orc = np.zeros(len(P["e"]))
orc[:-1] = np.sign(P["e"][1:])          # tomorrow's residual, known today
dd, gr, net, tov = pair_book(P, -orc, 0)
st["oracle_visible_lag0_sharpe"] = sharpe_stats(win(dd, gr, DESIGN_LO, DESIGN_HI))["sr"]
dd, gr, net, tov = pair_book(P, -orc, 2)
st["oracle_delayed_2d_sharpe"] = sharpe_stats(win(dd, gr, DESIGN_LO, DESIGN_HI))["sr"]
z = np.nan_to_num(roll_z(P["e"], 60), nan=0.0)
dd, gr, net, tov = pair_book(P, np.clip(z, -3, 3) / 3.0, 1)
st["cost_is_positive_bp_per_day"] = float(np.mean(gr - net) * 1e4)
st["gross_exposure_max"] = 1.0
st["tether_identity_check"] = {
    p: dict(R2=float(1 - np.var(pan[p]["e"]) / np.var(pan[p]["rA"])),
            sd_e_bp=float(pan[p]["e"].std() * 1e4)) for p in EVAL_PAIRS}
res["selftest"] = st

# ------------------------------------------------------------ 5. the VXX ETN halt
# Barclays suspended VXX issuance 2022-03-14; the premium is visible as a 202bp/day
# residual sd in 2022 vs 18-48bp in every other year. Does it pay at lag1?
P = pan["VXX_VIXY"]
for lo, hi, nm in (("20220314", "20221031", "vxx_issuance_halt_2022"),
                   ("20180205", "20180331", "feb2018_leverage_event")):
    z = np.nan_to_num(roll_z(P["e"], 60), nan=0.0)
    out = {}
    for L in (0, 1, 2):
        dd, gr, net, tov = pair_book(P, np.clip(z, -3, 3) / 3.0, L)
        out[f"L{L}_gross_sr"] = sharpe_stats(win(dd, gr, lo, hi))["sr"]
        out[f"L{L}_net_sr"] = sharpe_stats(win(dd, net, lo, hi))["sr"]
        out[f"L{L}_n"] = int(len(win(dd, gr, lo, hi)))
    res.setdefault("named_events", {})[nm] = out

# ------------------------------------------------------------ 6. control: static long
allr = []
for p in ("UVXY_VIXY", "SVXY_VIXY", "VXX_VIXY"):
    P = pan[p]
    m = (P["day"] >= DESIGN_LO) & (P["day"] <= DESIGN_HI)
    allr.append(sharpe_stats(P["rB"][m])["sr"])
res["controls"] = dict(static_long_B_leg_design_sharpes=allr)

with open("/home/anont/meme/research/trading_bot/INVENT_0822_vol_STATS.json", "w") as f:
    json.dump(res, f, indent=1)
print(json.dumps(res, indent=1)[:7000])
