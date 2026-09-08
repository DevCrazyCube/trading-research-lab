#!/usr/bin/env python3
"""PART B -- fresh freeze-then-test: DAILY (multi-day-hold) OU z-fade on the tightest cached
structural ETF-sibling tethers. This is a DIFFERENT horizon from L2 (15-min intraday) -- a daily
convergence trade, structured like L3 -- so it is a genuinely new object, not a re-run of L2.

Discriminator added: rho1(delta-spread). If -> -0.5 the 'mean reversion' is MEASUREMENT-ERROR
bounce (DEEPMINE_crosslist's finding), untradable regardless of Hurst/ADF. A real convergence
tether must have rho1(ds) well ABOVE -0.5.

Costs: per-symbol half-spread (bp) each side, entry+exit both legs, + SEC 0.278 on sales, + borrow
on the short leg for the hold. Multiple-testing bar = sqrt(2 ln N) SE on the per-trade t."""
import json, sys, pathlib, math
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oulib import fit_ou, adf, adf_verdict, hurst_rs

CACHE = pathlib.Path("/home/anont/meme/research/data/rv_cache")
# candidate pairs (A,B): structural tether, both liquid, NOT an existing basket leg
PAIRS = {
    "HYG/JNK":   ("HYG", "JNK"),    # broad USD high-yield credit, overlapping holdings
    "LQD/VCIT":  ("LQD", "VCIT"),   # USD investment-grade credit
    "TLT/VGLT":  ("TLT", "VGLT"),   # long US Treasuries (near-identical bonds)
    "AGG/BND":   ("AGG", "BND"),    # total US bond market
    "EEM/VWO":   ("EEM", "VWO"),    # emerging-market equity
    "GLD/IAU":   ("GLD", "IAU"),    # physical gold (identical claim, metal not index)
    "SLV/SIVR":  ("SLV", "SIVR"),   # physical silver
    "GDX/GDXJ":  ("GDX", "GDXJ"),   # gold miners senior vs junior (LOOSE tether -- control)
    "GLD/GDX":   ("GLD", "GDX"),    # metal vs miners (LOOSE tether -- control)
}
# rough liquid-ETF half-spreads (bp per side); conservative
HS = {"HYG":1.0,"JNK":1.5,"LQD":1.0,"VCIT":1.5,"TLT":0.8,"VGLT":2.0,"AGG":1.0,"BND":1.0,
      "EEM":1.0,"VWO":1.0,"GLD":0.8,"IAU":1.5,"SLV":1.5,"SIVR":3.0,"GDX":1.0,"GDXJ":1.5}
SEC_BP = 0.278
BORROW = 0.0033
DESIGN = ("2021-01-04", "2023-12-31")
HELDOUT = ("2024-01-02", "2026-08-15")
K, EXIT, MAXHOLD, ZWIN = 2.0, 0.5, 20, 60

def daily_close(sym):
    f = CACHE / f"{sym.replace('.','_')}.npz"
    if not f.exists():
        return None
    d = np.load(f)
    import datetime as dt
    t = d["t"]; c = d["c"].astype(float)
    # date (ET) via unix -> group, take last finite close per day
    days = (t - 4*3600) // 86400   # crude ET-day bucket (UTC-4/5; fine for last-of-day)
    out = {}
    for dd, cc in zip(days, c):
        if np.isfinite(cc):
            out[int(dd)] = cc     # overwrites -> last bar of the day
    daykeys = sorted(out)
    dates = [dt.datetime.utcfromtimestamp(int(dk*86400+4*3600)).strftime("%Y-%m-%d") for dk in daykeys]
    return dates, np.array([out[dk] for dk in daykeys])

def run_pair(dates, s, pa, pb, lo, hi):
    """L3-style daily z-fade on log-spread s=ln(pa/pb). Returns list of trade net-bp."""
    idx = [i for i,d in enumerate(dates) if lo<=d<=hi]
    if len(idx)<ZWIN+30: return []
    trades=[]; pos=None; hist=[]
    for i in idx:
        if pos:
            z=None
            if len(hist)>=ZWIN:
                w=np.array(hist[-ZWIN:]); mu=w.mean(); sd=w.std()
                z=(s[i]-mu)/sd if sd>0 else 0.0
            held=i-pos["i"]
            if (z is not None and abs(z)<=EXIT) or held>=MAXHOLD or i==idx[-1]:
                sgn=pos["sgn"]
                ra=pa[i]/pos["pa"]-1; rb=pb[i]/pos["pb"]-1
                gross=sgn*(ra-rb)
                cost=2*(hsA+hsB)*1e-4+2*SEC_BP*1e-4+BORROW*held/252.0
                trades.append((gross-cost)*1e4)
                pos=None
        if not pos and len(hist)>=ZWIN:
            w=np.array(hist[-ZWIN:]); mu=w.mean(); sd=w.std()
            if sd>0:
                z=(s[i]-mu)/sd
                if abs(z)>=K:
                    pos={"i":i,"pa":pa[i],"pb":pb[i],"sgn":-1 if z>0 else 1}
        hist.append(s[i])
    return trades

N=len(PAIRS)
bar_t = math.sqrt(2*math.log(N))   # multiple-testing bar in SE units
rows=[]
for name,(A,B) in PAIRS.items():
    da=daily_close(A); db=daily_close(B)
    if da is None or db is None:
        rows.append({"pair":name,"note":"missing data"}); continue
    da_map=dict(zip(*da)); db_map=dict(zip(*db))
    common=sorted(set(da_map)&set(db_map))
    pa=np.array([da_map[d] for d in common]); pb=np.array([db_map[d] for d in common])
    ok=(pa>0)&(pb>0); common=[c for c,o in zip(common,ok) if o]; pa=pa[ok]; pb=pb[ok]
    s=np.log(pa/pb)
    des=[i for i,d in enumerate(common) if DESIGN[0]<=d<=DESIGN[1]]
    if len(des)<80:
        rows.append({"pair":name,"note":"insufficient design"}); continue
    sd=s[des]
    ou=fit_ou(sd); ad=adf(sd); hu=hurst_rs(sd)
    ds=np.diff(sd); rho1=np.corrcoef(ds[:-1],ds[1:])[0,1] if ds.size>10 else float("nan")
    hsA,hsB=HS.get(A,2.0),HS.get(B,2.0)
    tr_des=run_pair(common,s,pa,pb,*DESIGN)
    tr_hld=run_pair(common,s,pa,pb,*HELDOUT)
    def st(tr):
        if len(tr)<5: return dict(n=len(tr))
        a=np.array(tr); m=a.mean(); sdv=a.std(ddof=1)
        t=m/(sdv/math.sqrt(len(a))) if sdv>0 else float("nan")
        return dict(n=len(a),net_bp=round(m,1),t=round(float(t),2),
                    per_trade_sharpe=round(m/sdv,3) if sdv>0 else None)
    rows.append({"pair":name,"half_life_days":round(ou["half_life"],1),
                 "theta":round(ou["theta"],4),"sigma_eq_pct":round(ou["sigma_eq"]*100,3),
                 "hurst":round(hu,3) if np.isfinite(hu) else None,
                 "adf_t":round(ad["tstat"],2),"adf":adf_verdict(ad["tstat"]),
                 "rho1_dspread":round(float(rho1),3),
                 "meas_err_flag": bool(np.isfinite(rho1) and rho1<-0.35),
                 "design":st(tr_des),"heldout":st(tr_hld)})

out={"leg":"PARTB_daily_sibling_screen","design":list(DESIGN),"heldout":list(HELDOUT),
     "n_candidates":N,"multiple_testing_bar_t":round(bar_t,3),
     "discriminator":"rho1(delta-spread) near -0.5 => measurement-error bounce, untradable",
     "rows":rows}
pathlib.Path("/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/B_screen.json").write_text(json.dumps(out,indent=1,default=float))
print("bar_t (sqrt(2 ln N)):",round(bar_t,2),"  N=",N)
print("%-10s %7s %6s %6s %7s %7s | %-18s %-18s"%("pair","HL(d)","H","ADFt","rho1","measErr","DESIGN","HELDOUT"))
for r in rows:
    if "half_life_days" not in r: print("%-10s  %s"%(r["pair"],r.get("note"))); continue
    d=r["design"]; h=r["heldout"]
    ds="n=%d net=%s t=%s"%(d.get("n",0),d.get("net_bp","-"),d.get("t","-"))
    hs="n=%d net=%s t=%s"%(h.get("n",0),h.get("net_bp","-"),h.get("t","-"))
    print("%-10s %7.1f %6s %6.2f %7.3f %7s | %-20s %-20s"%(
      r["pair"],r["half_life_days"],r["hurst"],r["adf_t"],r["rho1_dspread"],
      r["meas_err_flag"],ds,hs))
