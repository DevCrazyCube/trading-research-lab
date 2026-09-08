import pickle, numpy as np
import panelA as A

P = pickle.load(open('/home/anont/meme/.fm3work/panelA.pkl', 'rb'))
M, NC = P['M'], P['NC']; h = P['h']
out = open('/home/anont/meme/.fm3work/null2_out.txt', 'w')
pr = lambda *a: print(*a, file=out)
SPL2 = np.tile((h == 2)[:, None], (1, NC))
Hc = 20
g, r, fl, b, el = A.exits(P, Hc)
net = A.netarr(g, r, 0.0114, -0.30)
base = el & SPL2
ref = A.refmeans(base, net)
MAR = (P['mar'] >= 0.95) & (P['mar'] < 0.995)
STALE = (P['stale'] >= 0) & (P['stale'] < 30)
XM = np.tile(P['X'][:, None], (1, NC))
obs = A.cellstat(base & XM & MAR & STALE, net, r, b, base, ref)
pr('observed VALIDATE cell mean = %+.4f  (n=%d k=%d)' % (obs['mean'], obs['n'], obs['k']))

# NULL 1: shuffle the has_x label across mints (keeps the bar-level mar/stale structure)
rng = np.random.default_rng(11)
sims = []
for _ in range(3000):
    p = rng.permutation(M)
    xm = np.tile(P['X'][p][:, None], (1, NC))
    o = A.cellstat(base & xm & MAR & STALE, net, r, b, base, ref)
    if o is not None and o['k'] >= 5:
        sims.append(o['mean'])
sims = np.array(sims)
pr('NULL1 shuffle has_x across mints, n_sims=%d: p(>=obs)=%.4f  null med=%+.4f p95=%+.4f'
   % (len(sims), (sims >= obs['mean']).mean(), np.median(sims), np.percentile(sims, 95)))

# NULL 2: same mints, same trade counts, RANDOM eligible entry cycles (matched random control)
sel = obs['mints']
cnts = {}
for i in sel:
    m = (base & XM & MAR & STALE)[i]
    js = np.flatnonzero(m)
    c = 0; nf = -1
    for j in js:
        if j < nf:
            continue
        c += 1; nf = b[i, j]
    cnts[i] = c
rng = np.random.default_rng(12)
sims2 = []
for _ in range(3000):
    pm = []
    for i in sel:
        elig = np.flatnonzero(base[i])
        if len(elig) == 0:
            continue
        want = cnts[i]; got = []
        order = rng.permutation(elig)
        occ = []
        for j in order:
            if any(j >= s and j < e for s, e in occ):
                continue
            occ.append((j, b[i, j]))
            got.append(j)
            if len(got) >= want:
                break
        if got:
            pm.append(np.mean([net[i, j] for j in got]))
    if pm:
        sims2.append(np.mean(pm))
sims2 = np.array(sims2)
pr('NULL2 same 9 mints, same trade counts, random entry cycles, n_sims=%d:' % len(sims2))
pr('   p(>=obs)=%.4f  null mean=%+.4f med=%+.4f p95=%+.4f'
   % ((sims2 >= obs['mean']).mean(), sims2.mean(), np.median(sims2), np.percentile(sims2, 95)))
pr('   => edge over matched random control = %+.4f' % (obs['mean'] - sims2.mean()))
out.close()
print('done')
