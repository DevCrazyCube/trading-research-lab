import os, json, math, itertools, time, random
import numpy as np

S = "/home/anont/meme/research/scratch_combo2"
LOG = open(os.path.join(S, "sweep_log.txt"), "w")
def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

d = np.load(os.path.join(S, "mat.npz"))
X = d["X"]; MID = d["MID"]; HH = d["HH"]; SIGT = d["SIGT"]
ENTT = d["ENTT"]; ENTP = d["ENTP"]; EXTT = d["EXTT"]; EXTP = d["EXTP"]; RES = d["RES"]
meta = json.load(open(os.path.join(S, "mints.json")))
FEATS = meta["feats"]; NF = len(FEATS)

# sort rows by (mint, signal time)
order = np.lexsort((SIGT, MID))
X = X[order]; MID = MID[order]; HH = HH[order]; SIGT = SIGT[order]
ENTT = ENTT[order]; ENTP = ENTP[order]; EXTT = EXTT[order]; EXTP = EXTP[order]; RES = RES[order]
N = len(MID)

GROSS = np.where(RES == 1, EXTP / ENTP - 1.0, np.nan)
CAP = 3.0     # +300% fill-realism cap on a 15m exit print
GROSS_C = np.minimum(GROSS, CAP)

def netvec(toll, drop, capped=True):
    g = GROSS_C if capped else GROSS
    v = (1.0 + g) * (1.0 - toll) - 1.0
    return np.where(RES == 1, v, drop)

TOLL_A, TOLL_B = 0.0114, 0.025
NET = {}
for tn, toll in (("t114", TOLL_A), ("t250", TOLL_B)):
    for dn, dr in (("d30", -0.30), ("d50", -0.50), ("d100", -1.00)):
        NET[tn + "_" + dn] = netvec(toll, dr, True)
NET_UNCAP = netvec(TOLL_A, -0.30, False)
PRIMARY = "t114_d30"

TR = (HH == 1); VA = (HH == 2)
log("rows", N, "train", int(TR.sum()), "valid", int(VA.sum()), "feats", NF)

# ---------------- non-overlap simulator ----------------
def simulate(idx, net):
    """idx: row indices (must be ascending in (mint,sigt) order). Greedy one-position-per-mint.
    Returns per-mint list of taken returns."""
    per = {}
    cur_mint = -1; block = -1e18
    sg = SIGT; ex = EXTT; mi = MID
    for k in idx:
        m = mi[k]
        if m != cur_mint:
            cur_mint = m; block = -1e18
        s = sg[k]
        if s < block:
            continue
        block = ex[k]
        per.setdefault(m, []).append(net[k])
    return per

def headline(per):
    if not per: return None
    per_mean = np.array([np.mean(v) for v in per.values()])
    ntr = sum(len(v) for v in per.values())
    return float(per_mean.mean()), float(np.median(per_mean)), ntr, len(per), per_mean

def evaluate(idx, netkey=PRIMARY):
    per = simulate(idx, NET[netkey])
    return headline(per), per

def sim_stats(idx):
    """full stats under the primary config plus alternates + resolution rate."""
    out = {}
    per = simulate(idx, NET[PRIMARY])
    if not per: return None
    # rebuild taken-row set to compute alternates consistently
    taken = []
    cur_mint = -1; block = -1e18
    for k in idx:
        m = MID[k]
        if m != cur_mint: cur_mint = m; block = -1e18
        if SIGT[k] < block: continue
        block = EXTT[k]; taken.append(k)
    taken = np.array(taken, dtype=np.int64)
    mids = MID[taken]
    uniq, inv = np.unique(mids, return_inverse=True)
    def me(vals):
        sums = np.bincount(inv, weights=vals, minlength=len(uniq))
        cnts = np.bincount(inv, minlength=len(uniq))
        pm = sums / cnts
        return float(pm.mean()), float(np.median(pm)), pm
    for key in NET:
        m_, md_, pm_ = me(NET[key][taken])
        out[key] = (m_, md_)
        if key == PRIMARY: out["_pm"] = pm_
    m_, md_, _ = me(NET_UNCAP[taken])
    out["uncap_t114_d30"] = (m_, md_)
    out["n"] = int(len(taken)); out["clusters"] = int(len(uniq))
    out["res"] = float(RES[taken].mean())
    out["taken"] = taken
    return out

def boot_ci(pm, reps=3000, seed=7):
    rng = np.random.default_rng(seed)
    k = len(pm)
    if k < 5: return (float("nan"), float("nan"))
    draws = rng.integers(0, k, size=(reps, k))
    ms = pm[draws].mean(axis=1)
    return float(np.quantile(ms, 0.05)), float(np.quantile(ms, 0.95))

# ---------------- baselines: all eligible rows ----------------
allrows = np.arange(N)
for nm, mask in (("TRAIN", TR), ("VALID", VA), ("ALL", np.ones(N, bool))):
    st = sim_stats(allrows[mask])
    log("BASELINE(all eligible bars, non-overlap)", nm, "mean", round(st[PRIMARY][0], 4),
        "median", round(st[PRIMARY][1], 4), "n", st["n"], "clusters", st["clusters"],
        "res", round(st["res"], 4), "| d50", round(st["t114_d50"][0], 4),
        "d100", round(st["t114_d100"][0], 4), "| toll2.5", round(st["t250_d30"][0], 4),
        "| uncapped", round(st["uncap_t114_d30"][0], 4))

# random-bar control: sample a random 20% of eligible bars as signals
rng0 = np.random.default_rng(11)
for nm, mask in (("TRAIN", TR), ("VALID", VA)):
    idxm = allrows[mask]
    accs = []
    for rep in range(8):
        sel = idxm[rng0.random(len(idxm)) < 0.20]
        st = sim_stats(sel)
        accs.append((st[PRIMARY][0], st[PRIMARY][1], st["n"], st["clusters"]))
    a = np.array([x[0] for x in accs]); b = np.array([x[1] for x in accs])
    log("RANDOM-20% control", nm, "mean", round(float(a.mean()), 4), "+-", round(float(a.std()), 4),
        "median", round(float(b.mean()), 4), "n~", int(np.mean([x[2] for x in accs])),
        "clusters~", int(np.mean([x[3] for x in accs])))

# ---------------- discretisation (breakpoints from TRAIN only) ----------------
QB = {}; DB = {}; VB = {}
for k in range(NF):
    col = X[TR, k]; col = col[np.isfinite(col)]
    if len(col) < 500:
        QB[k] = None; continue
    QB[k] = np.quantile(col, [0.2, 0.4, 0.6, 0.8])
    DB[k] = np.quantile(col, [0.1, 0.9])
    VB[k] = np.quantile(col, [0.05, 0.95])

QBIN = np.full((N, NF), -1, dtype=np.int8)
DBIN = np.full((N, NF), -1, dtype=np.int8)   # 0 = bottom decile, 1 = top decile, -1 otherwise
VBIN = np.full((N, NF), -1, dtype=np.int8)
for k in range(NF):
    if QB[k] is None: continue
    col = X[:, k]; fin = np.isfinite(col)
    b = np.searchsorted(QB[k], col[fin], side="right")
    QBIN[fin, k] = b.astype(np.int8)
    lo, hi = DB[k]; DBIN[fin & (col <= lo), k] = 0; DBIN[fin & (col >= hi), k] = 1
    lo, hi = VB[k]; VBIN[fin & (col <= lo), k] = 0; VBIN[fin & (col >= hi), k] = 1

TRI = allrows[TR]; VAI = allrows[VA]

MIN_N = 60; MIN_CL = 12
results = []
t0 = time.time()
combos = 0

def add_cell(desc, trmask_fn):
    """trmask_fn(rows) -> boolean over those rows"""
    global combos
    combos += 1
    sel_tr = TRI[trmask_fn(TRI)]
    if len(sel_tr) < MIN_N: return
    st = sim_stats(sel_tr)
    if st is None or st["n"] < MIN_N or st["clusters"] < MIN_CL: return
    results.append((desc, st[PRIMARY][0], st[PRIMARY][1], st["n"], st["clusters"], trmask_fn))

# ---- singles (quintile + decile + ventile) ----
single_specs = []
for k in range(NF):
    if QB[k] is None: continue
    for q in range(5):
        single_specs.append(("Q", k, q))
    for dq in range(2):
        single_specs.append(("D", k, dq))
        single_specs.append(("V", k, dq))

def mk_single(kind, k, q):
    if kind == "Q": arr = QBIN
    elif kind == "D": arr = DBIN
    else: arr = VBIN
    return lambda rows, arr=arr, k=k, q=q: arr[rows, k] == q

for kind, k, q in single_specs:
    add_cell("1|%s|%s=%d" % (FEATS[k], kind, q), mk_single(kind, k, q))
log("singles done", combos, "kept", len(results), "t", round(time.time() - t0, 1))

# ---- 2-way ----
def mk_pair(kA, kqA, qA, kB, kqB, qB):
    aA = {"Q": QBIN, "D": DBIN, "V": VBIN}[kqA]
    aB = {"Q": QBIN, "D": DBIN, "V": VBIN}[kqB]
    return lambda rows: (aA[rows, kA] == qA) & (aB[rows, kB] == qB)

pairs = [(a, b) for a, b in itertools.combinations(range(NF), 2) if QB[a] is not None and QB[b] is not None]
log("feature pairs", len(pairs))
for a, b in pairs:
    # 5x5 quintile grid
    for qa in range(5):
        for qb in range(5):
            add_cell("2|%s Q%d & %s Q%d" % (FEATS[a], qa, FEATS[b], qb),
                     mk_pair(a, "Q", qa, b, "Q", qb))
    # decile-extreme x decile-extreme
    for da in range(2):
        for db in range(2):
            add_cell("2|%s D%d & %s D%d" % (FEATS[a], da, FEATS[b], db),
                     mk_pair(a, "D", da, b, "D", db))
    # ventile-extreme x ventile-extreme (tails)
    for da in range(2):
        for db in range(2):
            add_cell("2|%s V%d & %s V%d" % (FEATS[a], da, FEATS[b], db),
                     mk_pair(a, "V", da, b, "V", db))
    # decile-extreme x quintile (both orders)
    for da in range(2):
        for qb in range(5):
            add_cell("2|%s D%d & %s Q%d" % (FEATS[a], da, FEATS[b], qb),
                     mk_pair(a, "D", da, b, "Q", qb))
            add_cell("2|%s Q%d & %s D%d" % (FEATS[a], qb, FEATS[b], da),
                     mk_pair(a, "Q", qb, b, "D", da))
log("COMBOS SWEPT", combos, "cells meeting size floor", len(results), "t", round(time.time() - t0, 1))

results.sort(key=lambda r: -r[1])
log("--- train mean distribution ---")
tm = np.array([r[1] for r in results])
log("n cells", len(tm), "frac train mean>0", round(float((tm > 0).mean()), 4),
    "frac >0.02", round(float((tm > 0.02).mean()), 4), "frac >0.05", round(float((tm > 0.05).mean()), 4),
    "quantiles", [round(float(np.quantile(tm, q)), 4) for q in (0.01, .1, .25, .5, .75, .9, .99)])

log("--- top 40 on TRAIN ---")
for r in results[:40]:
    log("  %-52s trmean %7.4f trmed %7.4f n %5d cl %4d" % (r[0], r[1], r[2], r[3], r[4]))

# ---------------- validate stage ----------------
THRESH = 0.02
cands = [r for r in results if r[1] > THRESH]
log("cells passing TRAIN filter (mean > %.2f, n>=%d, clusters>=%d): %d" % (THRESH, MIN_N, MIN_CL, len(cands)))

surv = []
for desc, trm, trmd, trn, trcl, fn in cands:
    sel_va = VAI[fn(VAI)]
    if len(sel_va) < MIN_N: continue
    st = sim_stats(sel_va)
    if st is None or st["n"] < MIN_N or st["clusters"] < MIN_CL: continue
    surv.append((desc, trm, trmd, trn, trcl, st))
log("cells with enough VALIDATE support:", len(surv))
vm = np.array([s[5][PRIMARY][0] for s in surv]) if surv else np.array([])
if len(vm):
    log("validate mean of train-positive cells: frac>0", round(float((vm > 0).mean()), 4),
        "mean", round(float(vm.mean()), 4), "median", round(float(np.median(vm)), 4))

surv.sort(key=lambda s: -s[5][PRIMARY][0])
log("--- top 60 by VALIDATE mean ---")
for desc, trm, trmd, trn, trcl, st in surv[:60]:
    lo, hi = boot_ci(st["_pm"])
    log("  %-52s tr %7.4f | va mean %7.4f med %7.4f CI[%7.4f,%7.4f] n %5d cl %4d res %.3f | d50 %7.4f d100 %7.4f toll2.5 %7.4f uncap %8.4f"
        % (desc, trm, st[PRIMARY][0], st[PRIMARY][1], lo, hi, st["n"], st["clusters"], st["res"],
           st["t114_d50"][0], st["t114_d100"][0], st["t250_d30"][0], st["uncap_t114_d30"][0]))

# ---------------- strict survivors ----------------
strict = []
for desc, trm, trmd, trn, trcl, st in surv:
    lo, hi = boot_ci(st["_pm"])
    if st[PRIMARY][0] > 0 and lo > 0 and st["t114_d100"][0] > 0 and st["t250_d30"][0] > 0:
        strict.append((desc, trm, trmd, trn, trcl, st, lo, hi))
log("STRICT survivors (validate mean>0, bootstrap CI-lo>0, survives -100%% dropout AND 2.5%% toll):", len(strict))
for desc, trm, trmd, trn, trcl, st, lo, hi in strict:
    log("  STRICT %-52s tr %7.4f va %7.4f med %7.4f CI[%7.4f,%7.4f] n %5d cl %4d uncap %8.4f"
        % (desc, trm, st[PRIMARY][0], st[PRIMARY][1], lo, hi, st["n"], st["clusters"],
           st["uncap_t114_d30"][0]))

json.dump({"combos": combos, "n_cells_sized": len(results), "n_train_pass": len(cands),
           "n_valid_support": len(surv), "n_strict": len(strict),
           "strict": [[s[0], s[1], s[5][PRIMARY][0], s[5][PRIMARY][1], s[5]["n"], s[5]["clusters"], s[6], s[7]] for s in strict],
           "top_validate": [[s[0], s[1], s[5][PRIMARY][0], s[5][PRIMARY][1], s[5]["n"], s[5]["clusters"]] for s in surv[:60]]},
          open(os.path.join(S, "sweep_result.json"), "w"), indent=1)
log("DONE t", round(time.time() - t0, 1))
