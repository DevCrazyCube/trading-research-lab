"""Stage 2: exhaustive 2-way quintile-cell sweep, fixed 15m exit, harness contract A-G."""
import numpy as np, itertools, math, json, sys

OUT = open('/home/anont/meme/.c2w/sweep.txt', 'w')
def p(*a): print(*a, file=OUT); OUT.flush()

d = np.load('/home/anont/meme/.c2w/mat.npz', allow_pickle=True)
X = d['X'].astype(np.float64); mint_id = d['mint_id'].astype(np.int32)
ent_ts = d['ent_ts']; exit_ts = d['exit_ts']; ret_g = d['ret_g']
ok = d['ok'].astype(bool); hs = d['hs'].astype(np.int8)
FN = [str(x) for x in d['featnames']]
NF = len(FN)

X = np.where(np.isfinite(X), X, np.nan)
for k in range(NF):
    col = X[:, k]
    m = np.nanmedian(col)
    col[~np.isfinite(col)] = m
    lo_, hi_ = np.nanpercentile(col, [0.2, 99.8])
    X[:, k] = np.clip(col, lo_, hi_)

TOLL_A, TOLL_B = 0.0114, 0.025
def net(toll, drop):
    r = np.where(ok, (1.0 + np.nan_to_num(ret_g)) * (1.0 - toll) - 1.0, drop)
    return r
NETS = {}
for tag, t, dr in [('a30', TOLL_A, -0.30), ('a50', TOLL_A, -0.50), ('a100', TOLL_A, -1.00),
                   ('b30', TOLL_B, -0.30), ('b50', TOLL_B, -0.50), ('b100', TOLL_B, -1.00)]:
    NETS[tag] = net(t, dr)
HEAD = NETS['a30']

# ---- split masks ----
TR = np.nonzero(hs == 1)[0]
VA = np.nonzero(hs == 2)[0]

class Split:
    def __init__(self, idx):
        self.i = idx
        self.mid = mint_id[idx]
        self.ent = ent_ts[idx]
        self.xit = exit_ts[idx]
        self.ok = ok[idx]
        self.nets = {k: v[idx] for k, v in NETS.items()}
        u, inv = np.unique(self.mid, return_inverse=True)
        self.u = u; self.inv = inv; self.nm = len(u)
        self.Xs = X[idx]
S_TR, S_VA = Split(TR), Split(VA)
p("TRAIN bars %d mints %d | VALIDATE bars %d mints %d" % (len(TR), S_TR.nm, len(VA), S_VA.nm))

def greedy(S, mask):
    """Contract B: one open position per mint at a time, chronological greedy."""
    idx = np.nonzero(mask)[0]
    if idx.size == 0: return idx
    sel = []
    cur = -1; last = -1e18
    mid = S.mid; ent = S.ent; xit = S.xit
    for k in idx:
        m = mid[k]
        if m != cur:
            cur = m; last = -1e18
        if ent[k] >= last:
            sel.append(k); last = xit[k]
    return np.array(sel, dtype=np.int64)

def agg(S, sel, tag='a30'):
    """Contract C: mint-equal weighting for every headline number."""
    if sel.size == 0: return None
    inv = S.inv[sel]
    r = S.nets[tag][sel]
    cnt = np.bincount(inv, minlength=S.nm).astype(float)
    tot = np.bincount(inv, weights=r, minlength=S.nm)
    live = cnt > 0
    mm = tot[live] / cnt[live]
    return dict(n=int(sel.size), clusters=int(live.sum()),
                mean=float(mm.mean()), median=float(np.median(mm)),
                res=float(S.ok[sel].mean()), mint_means=mm)

def boot_lo(mm, B=2000, seed=0):
    rs = np.random.default_rng(seed)
    n = len(mm)
    if n < 5: return float('nan')
    draws = rs.integers(0, n, size=(B, n))
    means = mm[draws].mean(axis=1)
    return float(np.percentile(means, 5.0)), float(np.percentile(means, 95.0))

# ---- quintile edges from TRAIN only ----
EDGES = []
for k in range(NF):
    e = np.percentile(S_TR.Xs[:, k], [20, 40, 60, 80])
    e = np.unique(e)
    EDGES.append(e)
BIN_TR = [np.searchsorted(EDGES[k], S_TR.Xs[:, k], side='right') for k in range(NF)]
BIN_VA = [np.searchsorted(EDGES[k], S_VA.Xs[:, k], side='right') for k in range(NF)]
NB = [len(EDGES[k]) + 1 for k in range(NF)]
p("bins per feature: " + ", ".join("%s=%d" % (FN[k], NB[k]) for k in range(NF)))

# ---- unconditional baselines (the random-entry control: every bar is a signal) ----
base = {}
for nm, S, B in (('train', S_TR, BIN_TR), ('valid', S_VA, BIN_VA)):
    sel = greedy(S, np.ones(len(S.i), bool))
    for tag in ('a30', 'a50', 'a100', 'b30'):
        a = agg(S, sel, tag)
        base[(nm, tag)] = a
        p("BASELINE %-5s %-4s n=%d k=%d res=%.3f mean=%+.4f median=%+.4f"
          % (nm, tag, a['n'], a['clusters'], a['res'], a['mean'], a['median']))

BASE_TR = base[('train', 'a30')]['mean']
BASE_VA = base[('valid', 'a30')]['mean']

# ---- CALIBRATION ONLY: all bars, overlap allowed (this is what the stated -2.92%
#      benchmark's n=50,177 / k=453 implies). Never used as a headline. ----
for nm, S in (('train', S_TR), ('valid', S_VA)):
    allsel = np.arange(len(S.i))
    for tag in ('a30', 'a50', 'a100'):
        a = agg(S, allsel, tag)
        p("CALIB(overlapping, all bars) %-5s %-4s n=%d k=%d res=%.3f mean=%+.4f median=%+.4f"
          % (nm, tag, a['n'], a['clusters'], a['res'], a['mean'], a['median']))

# ---- 1-way marginals (context) ----
p("\n=== 1-WAY MARGINALS (train, a30) ===")
oneway = []
n_oneway = 0
for k in range(NF):
    for q in range(NB[k]):
        n_oneway += 1
        sel = greedy(S_TR, BIN_TR[k] == q)
        a = agg(S_TR, sel)
        if a is None: continue
        oneway.append((a['mean'], FN[k], q, a['n'], a['clusters'], a['median']))
oneway.sort(reverse=True)
for t in oneway[:14]:
    p("  %+.4f  %-14s q%d  n=%d k=%d med=%+.4f" % (t[0], t[1], t[2], t[3], t[4], t[5]))
p("  ...")
for t in oneway[-6:]:
    p("  %+.4f  %-14s q%d  n=%d k=%d med=%+.4f" % (t[0], t[1], t[2], t[3], t[4], t[5]))

# ---- exhaustive 2-way sweep on TRAIN ----
p("\n=== 2-WAY SWEEP ON TRAIN ===")
MIN_N, MIN_K = 60, 20
results = []
n_cells = 0
for ka, kb in itertools.combinations(range(NF), 2):
    ba, bb = BIN_TR[ka], BIN_TR[kb]
    for qa in range(NB[ka]):
        ma = (ba == qa)
        if not ma.any():
            n_cells += NB[kb]; continue
        for qb in range(NB[kb]):
            n_cells += 1
            mask = ma & (bb == qb)
            c = int(mask.sum())
            if c < MIN_N: continue
            sel = greedy(S_TR, mask)
            a = agg(S_TR, sel)
            if a is None or a['n'] < MIN_N or a['clusters'] < MIN_K: continue
            results.append((ka, qa, kb, qb, a['mean'], a['median'], a['n'], a['clusters'], a['res']))

p("2-way cells enumerated: %d ; evaluated with support (n>=%d,k>=%d): %d"
  % (n_cells, MIN_N, MIN_K, len(results)))
means = np.array([r[4] for r in results])
p("train cell mean distribution: min=%+.4f p5=%+.4f p25=%+.4f p50=%+.4f p75=%+.4f p95=%+.4f max=%+.4f"
  % tuple(np.percentile(means, [0, 5, 25, 50, 75, 95, 100]).tolist()))
p("cells with train mean > 0        : %d (%.1f%%)" % ((means > 0).sum(), 100.0*(means > 0).mean()))
p("cells with train mean > baseline : %d (%.1f%%)" % ((means > BASE_TR).sum(), 100.0*(means > BASE_TR).mean()))

results.sort(key=lambda r: -r[4])
p("\nTop 30 TRAIN cells (a30, mint-equal):")
for r in results[:30]:
    p("  %+.4f med=%+.4f n=%4d k=%3d res=%.3f | %s q%d & %s q%d"
      % (r[4], r[5], r[6], r[7], r[8], FN[r[0]], r[1], FN[r[2]], r[3]))

# ---- carry every train-positive cell forward to VALIDATE ----
cands = [r for r in results if r[4] > 0]
p("\ntrain-positive cells carried to validate: %d" % len(cands))

surv = []
for r in cands:
    ka, qa, kb, qb = r[0], r[1], r[2], r[3]
    mask = (BIN_VA[ka] == qa) & (BIN_VA[kb] == qb)
    sel = greedy(S_VA, mask)
    a = agg(S_VA, sel)
    if a is None or a['n'] < MIN_N or a['clusters'] < MIN_K:
        continue
    lo, hiq = boot_lo(a['mint_means'], seed=ka*100+kb)
    a50 = agg(S_VA, sel, 'a50'); a100 = agg(S_VA, sel, 'a100'); b30 = agg(S_VA, sel, 'b30')
    surv.append(dict(ka=ka, qa=qa, kb=kb, qb=qb, train_mean=r[4], train_med=r[5],
                     train_n=r[6], train_k=r[7],
                     v_mean=a['mean'], v_med=a['median'], v_n=a['n'], v_k=a['clusters'],
                     v_res=a['res'], lo=lo, hi=hiq,
                     v50=a50['mean'], v100=a100['mean'], vb30=b30['mean'],
                     mm=a['mint_means']))

p("of those, validate had support: %d" % len(surv))
surv.sort(key=lambda s: -s['v_mean'])
p("\nAll train-positive cells re-tested on VALIDATE (sorted by validate mean):")
for s in surv[:40]:
    p("  tr=%+.4f  va=%+.4f med=%+.4f n=%4d k=%3d res=%.3f CI90=[%+.4f,%+.4f] "
      "t2.5%%=%+.4f d50=%+.4f d100=%+.4f | %s q%d & %s q%d"
      % (s['train_mean'], s['v_mean'], s['v_med'], s['v_n'], s['v_k'], s['v_res'], s['lo'], s['hi'],
         s['vb30'], s['v50'], s['v100'], FN[s['ka']], s['qa'], FN[s['kb']], s['qb']))
vm = np.array([s['v_mean'] for s in surv]) if surv else np.array([0.0])
p("\nvalidate means of train-positive cells: p5=%+.4f p50=%+.4f p95=%+.4f ; frac>0 = %.3f ; frac>base = %.3f"
  % (np.percentile(vm,5), np.percentile(vm,50), np.percentile(vm,95),
     float((vm>0).mean()), float((vm>BASE_VA).mean())))

both = [s for s in surv if s['v_mean'] > 0]
p("\ncells positive on BOTH train and validate (no CI requirement): %d" % len(both))
for s in both:
    p("   %s q%d & %s q%d tr=%+.4f va=%+.4f med=%+.4f n=%d k=%d CI90=[%+.4f,%+.4f]"
      % (FN[s['ka']], s['qa'], FN[s['kb']], s['qb'], s['train_mean'], s['v_mean'], s['v_med'],
         s['v_n'], s['v_k'], s['lo'], s['hi']))

# ---- surface shape: best validate cell per feature pair, and per-feature dead-region map ----
p("\n=== SURFACE SHAPE: best TRAIN cell mean per feature (over all its 2-way cells) ===")
bestf = {}
for r in results:
    for kk in (r[0], r[2]):
        if kk not in bestf or r[4] > bestf[kk][0]:
            bestf[kk] = (r[4], FN[r[0]], r[1], FN[r[2]], r[3], r[5])
for kk in sorted(bestf, key=lambda z: -bestf[z][0]):
    b = bestf[kk]
    p("  %-15s best2way=%+.4f (med %+.4f) via %s q%d & %s q%d" % (FN[kk], b[0], b[5], b[1], b[2], b[3], b[4]))

p("\n=== FRACTION OF MINTS WITH POSITIVE MEAN, unconditional (validate) ===")
a = agg(S_VA, greedy(S_VA, np.ones(len(S_VA.i), bool)))
p("  %.3f of %d mints" % (float((a['mint_means'] > 0).mean()), a['clusters']))

# ---- strict survivors ----
strict = [s for s in surv if s['v_mean'] > 0 and s['lo'] > 0 and s['v_mean'] > BASE_VA]
p("\n=== STRICT SURVIVORS (validate mean>0 AND cluster-bootstrap 5%% > 0) : %d ===" % len(strict))
for s in strict:
    p("  %s q%d & %s q%d : tr=%+.4f va=%+.4f med=%+.4f n=%d k=%d res=%.3f CI90=[%+.4f,%+.4f]"
      % (FN[s['ka']], s['qa'], FN[s['kb']], s['qb'], s['train_mean'], s['v_mean'], s['v_med'],
         s['v_n'], s['v_k'], s['v_res'], s['lo'], s['hi']))

# ---- mint-matched random control for strict survivors ----
p("\n=== MINT-MATCHED RANDOM CONTROL (same mints, same trade counts, random bars) ===")
rs = np.random.default_rng(7)
bym = {}
for j in range(len(S_VA.i)):
    bym.setdefault(S_VA.inv[j], []).append(j)
bym = {k: np.array(v) for k, v in bym.items()}
for s in strict:
    mask = (BIN_VA[s['ka']] == s['qa']) & (BIN_VA[s['kb']] == s['qb'])
    sel = greedy(S_VA, mask)
    cnt = np.bincount(S_VA.inv[sel], minlength=S_VA.nm)
    sims = []
    for _ in range(300):
        acc = []
        for m in np.nonzero(cnt)[0]:
            pool = bym[m]
            take = rs.choice(pool, size=min(cnt[m], len(pool)), replace=False)
            acc.append(S_VA.nets['a30'][take].mean())
        sims.append(np.mean(acc))
    sims = np.array(sims)
    s['ctrl'] = float(sims.mean())
    s['ctrl_p'] = float((sims >= s['v_mean']).mean())
    p("  %s q%d & %s q%d : va=%+.4f  matched-random=%+.4f (sd %.4f)  p=%.3f  edge=%+.4f"
      % (FN[s['ka']], s['qa'], FN[s['kb']], s['qb'], s['v_mean'], s['ctrl'], sims.std(),
         s['ctrl_p'], s['v_mean'] - s['ctrl']))

json.dump([{k: (v if not isinstance(v, np.ndarray) else None) for k, v in s.items()} for s in strict],
          open('/home/anont/meme/.c2w/strict.json', 'w'), indent=1, default=float)
json.dump(dict(n_cells=n_cells, n_eval=len(results), n_oneway=n_oneway,
               base_tr=BASE_TR, base_va=BASE_VA, n_cands=len(cands), n_surv=len(surv)),
          open('/home/anont/meme/.c2w/meta.json', 'w'), indent=1, default=float)
p("\nDONE")
OUT.close()
