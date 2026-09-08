#!/usr/bin/env python3
"""PART A -- L3 dual-class RV: OU fit, Hurst/ADF, Bertram optimal band, (K,EXIT) OOS grid."""
import json, sys, pathlib, math
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, "/home/anont/meme/scripts/t28_dualclass")
from oulib import fit_ou, adf, adf_verdict, hurst_rs, bertram_optimal
import dc_test as m
import dc_run as run

# frozen L3 universe (16 pairs) and ETB whitelist (exclude these symbols entirely)
FROZEN = [("GOOGL","GOOG"),("BRK.A","BRK.B"),("FOXA","FOX"),("NWSA","NWS"),("UAA","UA"),
          ("HEI","HEI.A"),("CWEN","CWEN.A"),("LGF.A","LGF.B"),("CENTA","CENT"),
          ("LBRDA","LBRDK"),("LSXMA","LSXMK"),("FWONA","FWONK"),("Z","ZG"),
          ("DISCA","DISCK"),("PBR","PBR.A"),("LILA","LILAK")]
ETB_EXCL = {"BRK.A","CWEN.A","LGF.A","LGF.B","LSXMA","LSXMK","DISCA","DISCK"}
# ETB-guarded pairs: both legs easy-to-borrow (so either short side is executable)
ETB_PAIRS = [(a,b) for a,b in FROZEN if a not in ETB_EXCL and b not in ETB_EXCL]
DESIGN, HELDOUT = m.DESIGN, m.HELDOUT

def design_logspread(pair):
    rows = m.build(pair, *DESIGN)
    d = [r["d"] for r in rows]; s = np.array([r["s"] for r in rows])
    return np.array(d), s

# ---- OU / Hurst / ADF per frozen pair on DESIGN, breaks removed ----
per_pair = {}
pooled_hl = []
for pair in FROZEN:
    d, s = design_logspread(pair)
    if s.size < 60:
        per_pair[f"{pair[0]}/{pair[1]}"] = {"n": int(s.size), "note": "insufficient"}
        continue
    # AR1 fit excluding structural-break transitions (|ds|>0.15)
    ds = np.diff(s)
    keep = np.abs(ds) <= 0.15
    x = s[:-1][keep]; y = s[1:][keep]
    xm, ym = x.mean(), y.mean()
    b = np.sum((x-xm)*(y-ym))/np.sum((x-xm)**2)
    a = ym - b*xm
    resid = y-(a+b*x); sigeps = resid.std(ddof=2)
    bb = min(max(b,1e-8),0.999999999)
    theta = -math.log(bb); mu = a/(1-bb)
    sigma_eq = sigeps/math.sqrt(1-bb*bb)
    hl = math.log(2)/theta
    # ADF / Hurst on the level (breaks left in but they are rare)
    ad = adf(s); hu = hurst_rs(s)
    etb = "ETB" if (pair[0] not in ETB_EXCL and pair[1] not in ETB_EXCL) else "HTB-excl"
    per_pair[f"{pair[0]}/{pair[1]}"] = {
        "n_design": int(s.size), "half_life_days": round(hl,2),
        "theta_per_day": round(theta,4), "mu_logspread": round(mu,4),
        "sigma_eq_pct": round(sigma_eq*100,3), "phi_ar1": round(bb,4),
        "hurst": round(hu,3) if np.isfinite(hu) else None,
        "adf_t": round(ad["tstat"],2), "adf_verdict": adf_verdict(ad["tstat"]),
        "etb": etb}
    if etb == "ETB" and np.isfinite(hl) and hl < 500:
        pooled_hl.append(hl)

# ---- Bertram optimal band from a representative (median-ETB) OU fit ----
# use the median ETB pair's theta & sigma_eq; cost = frozen round-trip (2*(hsA+hsB)+2*SEC+borrow)
etb_fits = [(v["theta_per_day"], v["sigma_eq_pct"]/100.0) for k,v in per_pair.items()
            if v.get("etb")=="ETB" and "theta_per_day" in v and v["half_life_days"]<500]
theta_med = float(np.median([t for t,_ in etb_fits]))
sigeq_med = float(np.median([s for _,s in etb_fits]))
# representative round-trip cost for an ETB pair: use design NBBO quotes half-spread sum
sp_des = run.spread_map(DESIGN)
hs_sum = []
for a,b in ETB_PAIRS:
    if a in sp_des and b in sp_des:
        hs_sum.append(sp_des[a]+sp_des[b])   # full spreads; entry+exit crosses -> 2*(hsA/2+hsB/2)=hsA+hsB per RT...
rt_cost = float(np.median(hs_sum)) if hs_sum else 0.004   # fraction, round trip both legs both directions ~= full spread sum
# add SEC (2 sales) + borrow(mean hold ~ maxhold/2 days at 33bp/yr) -- small
rt_cost_total = rt_cost + 2*m.SEC_FEE_BP*1e-4 + m.BORROW_ANNUAL*(10/252.0)
bert = bertram_optimal(theta_med, sigeq_med, rt_cost_total,
                       entry_grid=np.linspace(0.5,3.5,61), exit_grid=np.linspace(0.0,1.5,31))

# ---- OOS (K,EXIT) grid on ETB-guarded frozen pairs; design-select, then held-out ----
def grid_run(window, K, EXIT):
    s,_,_ = run.run(window, f"K{K}X{EXIT}", pairs=ETB_PAIRS, K=K, EXIT=EXIT)
    return {"n": s.get("n",0), "net_bp": s.get("net_bp",float("nan")),
            "t": s.get("t",float("nan")), "book_sharpe": s.get("book_sharpe",float("nan")),
            "mean_hold": s.get("mean_hold",float("nan"))}

Kgrid = [1.5, 2.0, 2.5, 3.0]
EXITgrid = [0.0, 0.5, 1.0]
design_grid = {}; heldout_grid = {}
for K in Kgrid:
    for X in EXITgrid:
        design_grid[f"K{K}_X{X}"] = grid_run(DESIGN, K, X)
        heldout_grid[f"K{K}_X{X}"] = grid_run(HELDOUT, K, X)
# design-optimal by book_sharpe (min n=25)
cand = [(kk, vv) for kk,vv in design_grid.items() if vv["n"]>=25 and np.isfinite(vv["book_sharpe"])]
dstar = max(cand, key=lambda kv: kv[1]["book_sharpe"])[0] if cand else None

out = {"leg":"L3_DUALCLASS","design":list(DESIGN),"heldout":list(HELDOUT),
       "frozen":"K2.0_X0.5","etb_pairs":[f"{a}/{b}" for a,b in ETB_PAIRS],
       "per_pair_ou":per_pair,
       "pooled_median_half_life_days":round(float(np.median(pooled_hl)),2) if pooled_hl else None,
       "bertram_input":{"theta_med":round(theta_med,4),"sigma_eq_pct":round(sigeq_med*100,3),
                        "rt_cost_bp":round(rt_cost_total*1e4,2),"half_life_days":round(math.log(2)/theta_med,2)},
       "bertram_optimal":{k:(round(v,4) if isinstance(v,float) else v) for k,v in bert.items()} if bert else None,
       "design_optimal_cell":dstar,
       "design_grid":design_grid,"heldout_grid":heldout_grid}
pathlib.Path("/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/A_l3.json").write_text(json.dumps(out,indent=1,default=float))
print("ETB pairs:",out["etb_pairs"])
print("pooled median HL(d):",out["pooled_median_half_life_days"])
print("Bertram input:",out["bertram_input"])
print("Bertram optimal:",out["bertram_optimal"])
print("design-optimal cell:",dstar)
print("\nFROZEN K2.0_X0.5  design:",design_grid["K2.0_X0.5"],"\n           heldout:",heldout_grid["K2.0_X0.5"])
