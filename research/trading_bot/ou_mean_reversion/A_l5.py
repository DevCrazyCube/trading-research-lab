#!/usr/bin/env python3
"""PART A -- L5 CEF discount: per-CEF OU fit on the weekly discount series, Hurst/ADF pooled.
L5 is a cross-sectional DECILE tilt on the discount LEVEL, not a |z| band, so the Bertram
optimal-band comparison does not apply; we instead characterise the reversion clock (half-life)
and confirm the discount level is genuinely mean-reverting (H<0.5, ADF)."""
import json, gzip, sys, pathlib, math
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oulib import fit_ou, adf, adf_verdict, hurst_rs

H = json.load(gzip.open("/home/anont/meme/research/data/t12_cache/history_5Y.json.gz"))
SPLIT = "2024-03-01"     # T12 frozen split; design < SPLIT

half_lives, hursts, adf_t, adf_rej = [], [], [], 0
n_fit = 0
per_examples = {}
sig_frac_rej = 0
for tk, rows in H.items():
    # design-window weekly discount series (percent)
    des = [r for r in rows if r.get("date","") < SPLIT and r.get("discount") is not None]
    if len(des) < 40:
        continue
    disc = np.array([r["discount"] for r in des], float)   # percent, premium>0
    disc = disc[np.isfinite(disc)]
    if disc.size < 40 or disc.std() < 1e-6:
        continue
    ou = fit_ou(disc, dt=1.0)   # dt = 1 week
    hl = ou["half_life"]
    if not (np.isfinite(hl) and 0 < hl < 500):
        continue
    ad = adf(disc); hu = hurst_rs(disc)
    n_fit += 1
    half_lives.append(hl)
    if np.isfinite(hu): hursts.append(hu)
    if np.isfinite(ad["tstat"]):
        adf_t.append(ad["tstat"])
        if ad["tstat"] < -2.86: adf_rej += 1   # 5%
    if len(per_examples) < 6:
        per_examples[tk] = {"half_life_wk": round(hl,2), "hurst": round(hu,3) if np.isfinite(hu) else None,
                            "adf_t": round(ad["tstat"],2), "adf_verdict": adf_verdict(ad["tstat"]),
                            "mean_disc_pct": round(float(disc.mean()),2), "sd_disc_pct": round(float(disc.std()),2),
                            "n_wk": int(disc.size)}

half_lives = np.array(half_lives); hursts = np.array(hursts); adf_t = np.array(adf_t)
out = {"leg":"L5_T12CEF","design_split":SPLIT,"n_cefs_fit":n_fit,
       "half_life_weeks": {"median":round(float(np.median(half_lives)),2),
                           "p25":round(float(np.percentile(half_lives,25)),2),
                           "p75":round(float(np.percentile(half_lives,75)),2),
                           "mean":round(float(half_lives.mean()),2)},
       "half_life_days_median": round(float(np.median(half_lives))*7,1),
       "hurst": {"median":round(float(np.median(hursts)),3),"frac_below_0.5":round(float((hursts<0.5).mean()),3),
                 "p25":round(float(np.percentile(hursts,25)),3),"p75":round(float(np.percentile(hursts,75)),3)},
       "adf": {"median_t":round(float(np.median(adf_t)),2),
               "frac_reject_5pct":round(adf_rej/len(adf_t),3),"n":len(adf_t)},
       "examples": per_examples,
       "note":"L5 uses a widest/narrowest DECILE tilt on the discount LEVEL, not a |z|>=K band; "
              "the Bertram optimal-threshold comparison (A2) does not apply. The OU fit "
              "characterises the discount-convergence CLOCK and confirms mean reversion."}
pathlib.Path("/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/A_l5.json").write_text(json.dumps(out,indent=1,default=float))
print(json.dumps(out,indent=1,default=float))
