#!/usr/bin/env python3
"""PART A -- L2 ETF-sibling RV: OU fit, Hurst/ADF, and entry-threshold OOS test.
Uses the frozen 15:45 log-spread signal and the same-session 15:45->16:00 fade P&L."""
import json, sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oulib import fit_ou, adf, adf_verdict, hurst_rs

CACHE = pathlib.Path("/home/anont/meme/research/data/rv_cache")
PAIRS = [("IVV", "SPY"), ("VOO", "SPY"), ("QQQM", "QQQ"), ("VTWO", "IWM"), ("IJH", "MDY")]
# frozen 15:45 per-symbol half-spreads (bp)
HS = {"SPY": 0.13, "IVV": 0.35, "VOO": 0.35, "QQQ": 0.15, "QQQM": 0.50,
      "IWM": 0.20, "VTWO": 0.50, "MDY": 0.40, "IJH": 0.40}
SEC_BP = 0.278
DESIGN = ("2021-01-04", "2024-12-31")
HELDOUT = ("2025-01-02", "2026-08-15")
SLOT_1545 = 75          # (15:45 = minute 945): (945-570)//5
SLOT_CLOSE = 77         # last 5-min bar (15:55-16:00)
ZWIN = 60               # trailing-60 session standardization (frozen)

z = np.load(CACHE / "panel_rv.npz", allow_pickle=False)
syms = list(z["syms"].astype(str))
idx = {s: i for i, s in enumerate(syms)}
day = z["day"].astype(int)
slot = z["slot"].astype(int)
daykey = z["daykey"].astype(str)
close = z["close"].astype(float)
opn = z["open"].astype(float)

# per-day arrays: date -> price at 15:45 (slot75 close) and 16:00 (slot77 close) per symbol
days = np.unique(day)
date_of_day = {}
for d in days:
    date_of_day[d] = daykey[day == d][0]

def series_at_slot(sym, s):
    col = idx[sym]
    out = {}
    m = slot == s
    dd = day[m]; cc = close[m, col]
    for di, cv in zip(dd, cc):
        if np.isfinite(cv):
            out[date_of_day[di]] = cv
    return out

def in_win(d, w):
    return w[0] <= d <= w[1]

results = {}
for A, B in PAIRS:
    pa45 = series_at_slot(A, SLOT_1545); pb45 = series_at_slot(B, SLOT_1545)
    pa16 = series_at_slot(A, SLOT_CLOSE); pb16 = series_at_slot(B, SLOT_CLOSE)
    alldays = sorted(set(pa45) & set(pb45) & set(pa16) & set(pb16))
    # daily 15:45 log-spread
    dates = [d for d in alldays if pa45[d] > 0 and pb45[d] > 0]
    spread = np.array([np.log(pa45[d] / pb45[d]) for d in dates])
    dser = np.array(dates)
    des_mask = np.array([in_win(d, DESIGN) for d in dates])
    hld_mask = np.array([in_win(d, HELDOUT) for d in dates])
    sp_des = spread[des_mask]
    # ---- OU / Hurst / ADF on DESIGN spread ----
    ou = fit_ou(sp_des)
    ad = adf(sp_des)
    hu = hurst_rs(sp_des)
    # spread sd in bp
    sd_bp = np.std(sp_des) * 1e4
    results[f"{A}/{B}"] = {
        "n_design_days": int(des_mask.sum()),
        "ou_theta_per_day": round(ou["theta"], 4),
        "half_life_days": round(ou["half_life"], 3),
        "ou_mu_logspread": round(ou["mu"], 6),
        "sigma_eq_bp": round(ou["sigma_eq"] * 1e4, 2),
        "phi_ar1": round(ou["phi"], 4),
        "hurst": round(hu, 3) if np.isfinite(hu) else None,
        "adf_t": round(ad["tstat"], 2), "adf_verdict": adf_verdict(ad["tstat"]),
        "spread_sd_bp": round(sd_bp, 2),
    }

    # ---- realized fade P&L per session (design + heldout), then entry-threshold sweep ----
    # z_t = (s_t - mean_60(prev))/sd_60(prev); fire if |z|>=K; fade: sign(-z)*(retA-retB); cost.
    retA = np.array([pa16[d] / pa45[d] - 1 for d in dates])
    retB = np.array([pb16[d] / pb45[d] - 1 for d in dates])
    cost = (HS[A] + HS[B] + SEC_BP) * 1e-4      # entry both half-spreads + SEC on sold (auction exit=0)
    zs = np.full(len(dates), np.nan)
    for i in range(len(dates)):
        if i < ZWIN:
            continue
        w = spread[i - ZWIN:i]
        mu = w.mean(); sd = w.std()
        if sd > 0:
            zs[i] = (spread[i] - mu) / sd
    fade_ret = np.sign(-zs) * (retA - retB) - cost   # per-pair net if it fires
    results[f"{A}/{B}"]["_fade"] = dict(dates=dser, z=zs, ret=fade_ret,
                                        des=des_mask, hld=hld_mask)

# ---- portfolio entry-threshold sweep: each session = mean over fired pairs ----
def portfolio_net(Kthr, win_key):
    # collect per session across pairs
    byday = {}
    for A, B in PAIRS:
        f = results[f"{A}/{B}"]["_fade"]
        m = f[win_key]
        for d, zz, r in zip(f["dates"][m], f["z"][m], f["ret"][m]):
            if np.isfinite(zz) and abs(zz) >= Kthr and np.isfinite(r):
                byday.setdefault(d, []).append(r)
    if not byday:
        return None
    daily = np.array([np.mean(v) for v in byday.values()])
    n = daily.size
    mean_bp = daily.mean() * 1e4
    sd = daily.std(ddof=1) if n > 1 else np.nan
    t = daily.mean() / (sd / np.sqrt(n)) if n > 1 and sd > 0 else np.nan
    sharpe = daily.mean() / sd * np.sqrt(252) if sd > 0 else np.nan  # ~1 obs/session
    return dict(K=Kthr, n_sessions=int(n), mean_bp=round(mean_bp, 3),
                t=round(float(t), 2), sharpe=round(float(sharpe), 2))

Kgrid = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
design_sweep = [portfolio_net(k, "des") for k in Kgrid]
heldout_sweep = [portfolio_net(k, "hld") for k in Kgrid]
# design-optimal K by Sharpe
valid = [d for d in design_sweep if d and d["n_sessions"] >= 30]
Kstar = max(valid, key=lambda d: (d["sharpe"] if np.isfinite(d["sharpe"]) else -9))["K"] if valid else None

out = {"leg": "L2_ETFRV", "design": list(DESIGN), "heldout": list(HELDOUT),
       "per_pair_ou": {k: {kk: vv for kk, vv in v.items() if kk != "_fade"}
                       for k, v in results.items()},
       "frozen_K": 1.5, "design_optimal_K": Kstar,
       "design_sweep": design_sweep, "heldout_sweep": heldout_sweep}
pathlib.Path("/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/A_l2.json").write_text(json.dumps(out, indent=1, default=float))
print(json.dumps(out, indent=1, default=float))
