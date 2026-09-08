import os, json, math, itertools, time
import numpy as np

S = "/home/anont/meme/research/scratch_combo2"
LOG = open(os.path.join(S, "sweep2_log.txt"), "w")
def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

d = np.load(os.path.join(S, "mat.npz"))
X = d["X"]; MID = d["MID"]; HH = d["HH"]; SIGT = d["SIGT"]
ENTT = d["ENTT"]; ENTP = d["ENTP"]; EXTT = d["EXTT"]; EXTP = d["EXTP"]; RES = d["RES"]; ALT = d["ALT"]
meta = json.load(open(os.path.join(S, "mints.json")))
FEATS = meta["feats"]; NF = len(FEATS)

order = np.lexsort((SIGT, MID))
for nm in ("X","MID","HH","SIGT","ENTT","ENTP","EXTT","EXTP","RES","ALT"):
    globals()[nm] = globals()[nm][order]
N = len(MID)

CAP = 3.0
TOLL = 0.0114
def mknet(exp, ext, res, toll=TOLL, drop=-0.30, cap=CAP):
    g = np.minimum(ext / exp - 1.0, cap)
    v = (1.0 + g) * (1.0 - toll) - 1.0
    return np.where(res == 1, v, drop)

NET = {}
NET["t114_d30"]  = mknet(ENTP, EXTP, RES, TOLL, -0.30)
NET["t114_d50"]  = mknet(ENTP, EXTP, RES, TOLL, -0.50)
NET["t114_d100"] = mknet(ENTP, EXTP, RES, TOLL, -1.00)
NET["t250_d30"]  = mknet(ENTP, EXTP, RES, 0.025, -0.30)
NET["uncap"]     = mknet(ENTP, EXTP, RES, TOLL, -0.30, cap=1e18)
for zi, H in enumerate((300, 600, 1800, 3600)):
    NET["H%d" % H] = mknet(ENTP, ALT[:, zi], ALT[:, 8 + zi].astype(int), TOLL, -0.30)
# TP/SL structures inside the 15m window (MFE/MAE based; conservative ordering = SL checked first)
MFE = ALT[:, 12] / ENTP - 1.0
MAE = ALT[:, 13] / ENTP - 1.0
BASE = np.minimum(EXTP / ENTP - 1.0, CAP)
def tp_sl(tp, sl):
    g = np.where(MAE <= -sl, -sl, np.where(MFE >= tp, tp, BASE))
    v = (1.0 + g) * (1.0 - TOLL) - 1.0
    return np.where(RES == 1, v, -0.30)
PRIMARY = "t114_d30"

TR = (HH == 1); VA = (HH == 2)
allrows = np.arange(N)
TRI = allrows[TR]; VAI = allrows[VA]
log("rows", N, "train", len(TRI), "valid", len(VAI), "feats", NF)

def take(idx):
    out = []
    cur = -1; block = -1e18
    for k in idx:
        m = MID[k]
        if m != cur: cur = m; block = -1e18
        if SIGT[k] < block: continue
        block = EXTT[k]; out.append(k)
    return np.asarray(out, dtype=np.int64)

def me(taken, net):
    mids = MID[taken]
    uniq, inv = np.unique(mids, return_inverse=True)
    sums = np.bincount(inv, weights=net[taken], minlength=len(uniq))
    cnts = np.bincount(inv, minlength=len(uniq))
    pm = sums / cnts
    return float(pm.mean()), float(np.median(pm)), pm, len(uniq)

def boot_ci(pm, reps=4000, seed=7):
    if len(pm) < 5: return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    dr = rng.integers(0, len(pm), size=(reps, len(pm)))
    ms = pm[dr].mean(axis=1)
    return float(np.quantile(ms, 0.05)), float(np.quantile(ms, 0.95))

# ---------- baselines ----------
for nm, idxs in (("TRAIN", TRI), ("VALID", VAI)):
    tk = take(idxs)
    m, md, pm, cl = me(tk, NET[PRIMARY])
    log("BASELINE all-bars", nm, "mean", round(m, 4), "med", round(md, 4), "n", len(tk),
        "clusters", cl, "res", round(float(RES[tk].mean()), 4))
rng0 = np.random.default_rng(3)
for nm, idxs in (("TRAIN", TRI), ("VALID", VAI)):
    ms = []
    for r in range(12):
        sel = idxs[rng0.random(len(idxs)) < 0.15]
        tk = take(sel); m, md, pm, cl = me(tk, NET[PRIMARY]); ms.append(m)
    log("RANDOM-15% control", nm, "mean", round(float(np.mean(ms)), 4), "sd", round(float(np.std(ms)), 4))

# ---------- discretisation from TRAIN ----------
QB = {}; DB = {}; VB = {}
QBIN = np.full((N, NF), -1, np.int8); DBIN = np.full((N, NF), -1, np.int8); VBIN = np.full((N, NF), -1, np.int8)
for k in range(NF):
    col = X[TR, k]; col = col[np.isfinite(col)]
    if len(col) < 500: QB[k] = None; continue
    QB[k] = np.quantile(col, [.2, .4, .6, .8]); DB[k] = np.quantile(col, [.1, .9]); VB[k] = np.quantile(col, [.05, .95])
    c = X[:, k]; fin = np.isfinite(c)
    QBIN[fin, k] = np.searchsorted(QB[k], c[fin], side="right").astype(np.int8)
    DBIN[fin & (c <= DB[k][0]), k] = 0; DBIN[fin & (c >= DB[k][1]), k] = 1
    VBIN[fin & (c <= VB[k][0]), k] = 0; VBIN[fin & (c >= VB[k][1]), k] = 1
ARR = {"Q": QBIN, "D": DBIN, "V": VBIN}

MIN_N = 60; MIN_CL = 12
cells = []       # (desc, specA, specB)
for k in range(NF):
    if QB[k] is None: continue
    for kind, nq in (("Q", 5), ("D", 2), ("V", 2)):
        for q in range(nq):
            cells.append(("1|%s %s%d" % (FEATS[k], kind, q), (k, kind, q), None))
pairs = [(a, b) for a, b in itertools.combinations(range(NF), 2) if QB[a] is not None and QB[b] is not None]
for a, b in pairs:
    for qa in range(5):
        for qb in range(5):
            cells.append(("2|%s Q%d & %s Q%d" % (FEATS[a], qa, FEATS[b], qb), (a, "Q", qa), (b, "Q", qb)))
    for ka, na in (("D", 2), ("V", 2)):
        for xa in range(na):
            for xb in range(na):
                cells.append(("2|%s %s%d & %s %s%d" % (FEATS[a], ka, xa, FEATS[b], ka, xb), (a, ka, xa), (b, ka, xb)))
    for ka in ("D", "V"):
        for xa in range(2):
            for qb in range(5):
                cells.append(("2|%s %s%d & %s Q%d" % (FEATS[a], ka, xa, FEATS[b], qb), (a, ka, xa), (b, "Q", qb)))
                cells.append(("2|%s Q%d & %s %s%d" % (FEATS[a], qb, FEATS[b], ka, xa), (a, "Q", qb), (b, ka, xa)))
COMBOS = len(cells)
log("COMBOS DEFINED", COMBOS, "(pairs %d)" % len(pairs))

def mask_of(rows, sa, sb):
    m = ARR[sa[1]][rows, sa[0]] == sa[2]
    if sb is not None:
        m = m & (ARR[sb[1]][rows, sb[0]] == sb[2])
    return m

t0 = time.time()
tab = []
for desc, sa, sb in cells:
    str_ = TRI[mask_of(TRI, sa, sb)]
    if len(str_) < MIN_N: continue
    tk = take(str_)
    if len(tk) < MIN_N: continue
    trm, trmd, trpm, trcl = me(tk, NET[PRIMARY])
    if trcl < MIN_CL: continue
    sva = VAI[mask_of(VAI, sa, sb)]
    if len(sva) < MIN_N: continue
    tkv = take(sva)
    if len(tkv) < MIN_N: continue
    vam, vamd, vapm, vacl = me(tkv, NET[PRIMARY])
    if vacl < MIN_CL: continue
    tab.append((desc, sa, sb, trm, trmd, len(tk), trcl, vam, vamd, len(tkv), vacl, vapm, tkv))
log("cells with size on BOTH splits", len(tab), "t", round(time.time() - t0, 1))

trm = np.array([r[3] for r in tab]); vam = np.array([r[7] for r in tab])
log("--- RESPONSE SURFACE ---")
log("train mean: frac>0 %.4f  q[.01,.1,.25,.5,.75,.9,.99] %s" %
    ((trm > 0).mean(), [round(float(np.quantile(trm, q)), 4) for q in (.01, .1, .25, .5, .75, .9, .99)]))
log("valid mean: frac>0 %.4f  q[.01,.1,.25,.5,.75,.9,.99] %s" %
    ((vam > 0).mean(), [round(float(np.quantile(vam, q)), 4) for q in (.01, .1, .25, .5, .75, .9, .99)]))
both = (trm > 0) & (vam > 0)
log("cells positive on TRAIN: %d (%.3f) | positive on VALID: %d (%.3f) | BOTH: %d (%.4f); "
    "independence would predict %.1f" % ((trm > 0).sum(), (trm > 0).mean(), (vam > 0).sum(),
    (vam > 0).mean(), both.sum(), both.mean(), (trm > 0).mean() * (vam > 0).mean() * len(tab)))
log("corr(train mean, valid mean) = %.4f" % float(np.corrcoef(trm, vam)[0, 1]))
# per-feature marginal deadness
log("--- per-feature: best validate mean over all cells containing that feature ---")
for k in range(NF):
    sub = [r for r in tab if r[1][0] == k or (r[2] is not None and r[2][0] == k)]
    if not sub: continue
    v = np.array([r[7] for r in sub])
    log("  %-10s cells %5d  best_va %7.4f  median_va %7.4f  frac_va>0 %.3f"
        % (FEATS[k], len(sub), float(v.max()), float(np.median(v)), float((v > 0).mean())))

# ---------- candidates: positive on both ----------
cand = [r for r in tab if r[3] > 0 and r[7] > 0]
cand.sort(key=lambda r: -r[7])
log("CANDIDATES positive on train AND validate:", len(cand))

# per-mint eligible rows for matched control
elig_by_mint = {}
for k in VAI:
    elig_by_mint.setdefault(MID[k], []).append(k)
for m in elig_by_mint: elig_by_mint[m] = np.array(sorted(elig_by_mint[m]))

def matched_control(tkv, reps=300, seed=5):
    rng = np.random.default_rng(seed)
    mids, cnts = np.unique(MID[tkv], return_counts=True)
    out = []
    for r in range(reps):
        sel = []
        for m, c in zip(mids, cnts):
            pool = elig_by_mint.get(m)
            if pool is None or len(pool) == 0: continue
            c2 = min(c, len(pool))
            sel.append(rng.choice(pool, size=c2, replace=False))
        if not sel: continue
        sel = np.sort(np.concatenate(sel))
        tk = take(sel)
        if len(tk) < 5: continue
        m_, md_, pm_, cl_ = me(tk, NET[PRIMARY])
        out.append(m_)
    return (float(np.mean(out)), float(np.std(out)), float(np.quantile(out, .95))) if out else (float("nan"),) * 3

log("--- CANDIDATE DETAIL (validate split) ---")
detail = []
for desc, sa, sb, trmn, trmd, trn, trcl, vamn, vamd, van, vacl, vapm, tkv in cand[:80]:
    lo, hi = boot_ci(vapm)
    mc_m, mc_sd, mc_p95 = matched_control(tkv)
    alt = {}
    for key in ("t114_d50", "t114_d100", "t250_d30", "uncap", "H300", "H600", "H1800", "H3600"):
        alt[key] = me(tkv, NET[key])[0]
    tps = {}
    for tp, sl in ((0.05, 0.10), (0.10, 0.15), (0.20, 0.20), (0.30, 0.30)):
        tps["tp%d_sl%d" % (tp * 100, sl * 100)] = me(tkv, tp_sl(tp, sl))[0]
    detail.append((desc, trmn, vamn, vamd, van, vacl, lo, hi, mc_m, mc_p95, alt, tps))
    log("%-50s | tr %7.4f | va mean %7.4f med %7.4f CI[%7.4f,%7.4f] n %5d cl %4d"
        % (desc, trmn, vamn, vamd, lo, hi, van, vacl))
    log("     matched-random-control(same mints,same counts) %7.4f (sd %.4f, p95 %7.4f) -> EDGE %7.4f"
        % (mc_m, mc_sd, mc_p95, vamn - mc_m))
    log("     d50 %7.4f d100 %7.4f toll2.5 %7.4f uncap %9.4f | H5m %7.4f H10m %7.4f H30m %7.4f H60m %7.4f"
        % (alt["t114_d50"], alt["t114_d100"], alt["t250_d30"], alt["uncap"],
           alt["H300"], alt["H600"], alt["H1800"], alt["H3600"]))
    log("     tp/sl: " + " ".join("%s %7.4f" % (k, v) for k, v in tps.items()))

# ---------- TP/SL truncation control on random entries ----------
log("--- TP/SL truncation control: same structures on RANDOM entries (validate) ---")
rng1 = np.random.default_rng(19)
for tp, sl in ((0.05, 0.10), (0.10, 0.15), (0.20, 0.20), (0.30, 0.30)):
    net = tp_sl(tp, sl); ms = []; mds = []
    for r in range(10):
        sel = VAI[rng1.random(len(VAI)) < 0.15]
        tk = take(sel); m_, md_, pm_, cl_ = me(tk, net); ms.append(m_); mds.append(md_)
    log("  RANDOM tp%d/sl%d mean %7.4f median %7.4f" % (tp * 100, sl * 100, float(np.mean(ms)), float(np.mean(mds))))
net = NET[PRIMARY]; ms = []; mds = []
for r in range(10):
    sel = VAI[rng1.random(len(VAI)) < 0.15]
    tk = take(sel); m_, md_, pm_, cl_ = me(tk, net); ms.append(m_); mds.append(md_)
log("  RANDOM plain-15m mean %7.4f median %7.4f" % (float(np.mean(ms)), float(np.mean(mds))))

json.dump({"combos": COMBOS, "sized": len(tab),
           "frac_train_pos": float((trm > 0).mean()), "frac_valid_pos": float((vam > 0).mean()),
           "n_both": int(both.sum()), "expected_both": float((trm > 0).mean() * (vam > 0).mean() * len(tab)),
           "corr": float(np.corrcoef(trm, vam)[0, 1]),
           "detail": [[x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9], x[10], x[11]] for x in detail]},
          open(os.path.join(S, "sweep2_result.json"), "w"), indent=1, default=float)
log("DONE t", round(time.time() - t0, 1))
