"""Stage 3: robustness on the handful of cells positive on both halves +
   a full swapped-split (h2 train / h1 validate) sweep for direction-independence."""
import numpy as np, itertools, json
OUT = open('/home/anont/meme/.c2w/verify.txt', 'w')
def p(*a): print(*a, file=OUT); OUT.flush()

d = np.load('/home/anont/meme/.c2w/mat.npz', allow_pickle=True)
X = d['X'].astype(np.float64); mint_id = d['mint_id'].astype(np.int32)
ent_ts = d['ent_ts']; exit_ts = d['exit_ts']; ret_g = d['ret_g']
ok = d['ok'].astype(bool); hs = d['hs'].astype(np.int8)
FN = [str(x) for x in d['featnames']]; NF = len(FN)
X = np.where(np.isfinite(X), X, np.nan)
for k in range(NF):
    c = X[:, k]; m = np.nanmedian(c); c[~np.isfinite(c)] = m
    a, b = np.nanpercentile(c, [0.2, 99.8]); X[:, k] = np.clip(c, a, b)

NET = np.where(ok, (1.0 + np.nan_to_num(ret_g)) * (1.0 - 0.0114) - 1.0, -0.30)

class S:
    def __init__(s, idx):
        s.i = idx; s.mid = mint_id[idx]; s.ent = ent_ts[idx]; s.xit = exit_ts[idx]
        s.ok = ok[idx]; s.net = NET[idx]; s.X = X[idx]
        u, inv = np.unique(s.mid, return_inverse=True); s.u = u; s.inv = inv; s.nm = len(u)
A = S(np.nonzero(hs == 1)[0]); B = S(np.nonzero(hs == 2)[0])

def greedy(s, mask):
    idx = np.nonzero(mask)[0]
    if idx.size == 0: return idx
    sel = []; cur = -1; last = -1e18
    for k in idx:
        m = s.mid[k]
        if m != cur: cur = m; last = -1e18
        if s.ent[k] >= last: sel.append(k); last = s.xit[k]
    return np.array(sel, np.int64)

def mintmeans(s, sel):
    inv = s.inv[sel]; r = s.net[sel]
    cnt = np.bincount(inv, minlength=s.nm).astype(float)
    tot = np.bincount(inv, weights=r, minlength=s.nm)
    live = cnt > 0
    return tot[live] / cnt[live], int(sel.size), int(live.sum()), np.nonzero(live)[0], cnt[live]

def edges_from(s):
    E = [np.unique(np.percentile(s.X[:, k], [20, 40, 60, 80])) for k in range(NF)]
    return E
def binz(s, E):
    return [np.searchsorted(E[k], s.X[:, k], side='right') for k in range(NF)]

# ================= part 1: robustness of the both-positive cells =================
CELLS = [('vol_share15',3,'mdd15',4), ('age_min',2,'mdd15',4), ('accel_5_15',0,'mdd15',4),
         ('bar_range',4,'age_min',2), ('r5',2,'r15',0), ('cumvol60',2,'up_frac15',3),
         ('age_min',2,'dd60',2)]
E = edges_from(A); BA = binz(A, E); BB = binz(B, E)
rs = np.random.default_rng(11)
bym = {}
for j in range(len(B.i)): bym.setdefault(B.inv[j], []).append(j)
bym = {k: np.array(v) for k, v in bym.items()}

p("=== ROBUSTNESS OF THE 7 CELLS POSITIVE ON BOTH TRAIN AND VALIDATE ===")
p("(validate = h2; toll 1.14%, dropout -30%; mint-equal)")
for fa, qa, fb, qb in CELLS:
    ka, kb = FN.index(fa), FN.index(fb)
    sel = greedy(B, (BB[ka] == qa) & (BB[kb] == qb))
    mm, n, k, mids, cnts = mintmeans(B, sel)
    mean = mm.mean()
    # jackknife: drop the single most favourable mint
    contrib = mm - mean
    j = int(np.argmax(contrib))
    mm2 = np.delete(mm, j)
    # drop top 2 and top 3
    ordr = np.argsort(mm)
    d1 = np.delete(mm, ordr[-1]).mean(); d2 = np.delete(mm, ordr[-2:]).mean(); d3 = np.delete(mm, ordr[-3:]).mean()
    fracpos = float((mm > 0).mean())
    # mint-matched random control
    cnt_full = np.bincount(B.inv[sel], minlength=B.nm)
    sims = []
    for _ in range(400):
        acc = []
        for m in np.nonzero(cnt_full)[0]:
            pool = bym[m]
            take = rs.choice(pool, size=min(cnt_full[m], len(pool)), replace=False)
            acc.append(B.net[take].mean())
        sims.append(np.mean(acc))
    sims = np.array(sims)
    pv = float((sims >= mean).mean())
    p("\n  %s q%d & %s q%d   n=%d k=%d" % (fa, qa, fb, qb, n, k))
    p("    validate mean=%+.4f median=%+.4f  frac mints>0 = %.3f" % (mean, np.median(mm), fracpos))
    p("    top mint contributes %+.4f of the mean (its own mean %+.2f, %d trades)"
      % (contrib[j]/len(mm), mm[j], cnts[j]))
    p("    drop top-1 mint: %+.4f | drop top-2: %+.4f | drop top-3: %+.4f" % (d1, d2, d3))
    p("    mint-matched random control: %+.4f (sd %.4f)  p(random>=rule)=%.3f  edge=%+.4f"
      % (sims.mean(), sims.std(), pv, mean - sims.mean()))

# ================= part 2: swapped-split full sweep =================
p("\n\n=== SWAPPED SPLIT: train on h2, validate on h1 (full re-sweep) ===")
E2 = edges_from(B); B2 = binz(B, E2); A2 = binz(A, E2)
MIN_N, MIN_K = 60, 20
res2 = []; ncell2 = 0
for ka, kb in itertools.combinations(range(NF), 2):
    ba, bb = B2[ka], B2[kb]
    nba = ba.max() + 1; nbb = bb.max() + 1
    for qa in range(nba):
        ma = (ba == qa)
        if not ma.any(): ncell2 += nbb; continue
        for qb in range(nbb):
            ncell2 += 1
            mask = ma & (bb == qb)
            if mask.sum() < MIN_N: continue
            sel = greedy(B, mask)
            if sel.size < MIN_N: continue
            mm, n, k, _, _ = mintmeans(B, sel)
            if k < MIN_K: continue
            res2.append((ka, qa, kb, qb, float(mm.mean()), float(np.median(mm)), n, k))
means2 = np.array([r[4] for r in res2])
p("cells enumerated %d ; evaluated %d ; frac>0 = %.3f" % (ncell2, len(res2), float((means2 > 0).mean())))
pos2 = [r for r in res2 if r[4] > 0]
p("train(h2)-positive cells: %d" % len(pos2))
out2 = []
for r in pos2:
    ka, qa, kb, qb = r[:4]
    sel = greedy(A, (A2[ka] == qa) & (A2[kb] == qb))
    if sel.size < MIN_N: continue
    mm, n, k, _, _ = mintmeans(A, sel)
    if k < MIN_K: continue
    out2.append((r[4], float(mm.mean()), float(np.median(mm)), n, k, FN[ka], qa, FN[kb], qb))
out2.sort(key=lambda z: -z[1])
vm2 = np.array([o[1] for o in out2]) if out2 else np.array([0.0])
p("validated(h1) with support: %d ; frac>0 = %.3f" % (len(out2), float((vm2 > 0).mean())))
p("top 15 by validate(h1) mean:")
for o in out2[:15]:
    p("   tr(h2)=%+.4f va(h1)=%+.4f med=%+.4f n=%d k=%d | %s q%d & %s q%d"
      % (o[0], o[1], o[2], o[3], o[4], o[5], o[6], o[7], o[8]))

both2 = set((o[5], o[6], o[7], o[8]) for o in out2 if o[1] > 0)
both1 = set(CELLS)
p("\ncells positive in BOTH directions of the split: %s" % sorted(both1 & both2))
p("\nDONE")
OUT.close()
