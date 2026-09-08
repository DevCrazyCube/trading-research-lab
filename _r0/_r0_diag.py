import pickle, json
import numpy as np
OUT = '/home/anont/meme/_r0'
D = pickle.load(open(OUT + '/cache.pkl', 'rb'))
mints = D['mints']
o = open(OUT + '/diag.log', 'w')
def L(*a): o.write(' '.join(str(x) for x in a) + '\n')

# distribution of 15m open->open returns from every bar (no overlap ignored)
rets = []; big = []
for m in mints:
    ts = m['ts']; op = m['o']; n = len(ts)
    tgt = np.searchsorted(ts, ts + 900, 'left')
    ok = tgt < n
    e = np.nonzero(ok)[0]
    if len(e) == 0: continue
    r = op[tgt[e]]/op[e] - 1.0
    rets.append(r)
    for k in np.argsort(r)[:2]:
        big.append((float(r[k]), m['mint'], int(ts[e[k]]), float(op[e[k]]), float(op[tgt[e[k]]])))
    for k in np.argsort(r)[-2:]:
        big.append((float(r[k]), m['mint'], int(ts[e[k]]), float(op[e[k]]), float(op[tgt[e[k]]])))
R = np.concatenate(rets)
L('n', len(R), 'mean %.4f' % R.mean(), 'median %.4f' % np.median(R))
for q in [0.1,1,5,10,25,50,75,90,95,99,99.9]:
    L('  p%-5s %+.4f' % (q, np.percentile(R, q)))
L('frac < -0.9', float((R < -0.9).mean()), 'frac < -0.5', float((R < -0.5).mean()),
  'frac > 1', float((R > 1).mean()), 'frac > 10', float((R > 10).mean()))
big.sort()
L('worst:'); [L('   %+.4f %s ts=%d px %.3e -> %.3e' % b) for b in big[:8]]
L('best:');  [L('   %+.4f %s ts=%d px %.3e -> %.3e' % b) for b in big[-8:]]

# intrabar sanity: how often is open outside [low,high]? how often hi/lo ratio absurd?
bad = 0; tot = 0; hilo = []
for m in mints:
    op, hi, lo, cl = m['o'], m['hi'], m['lo'], m['c']
    tot += len(op)
    bad += int(((op > hi*1.0000001) | (op < lo*0.9999999)).sum())
    hilo.append(hi/np.maximum(lo, 1e-30))
H = np.concatenate(hilo)
L('bars', tot, 'open outside [lo,hi]', bad)
L('hi/lo pctiles', [float(np.percentile(H, q)) for q in (50, 90, 99, 99.9, 100)])

# per-mint total lifetime move
lt = [(float(m['c'][-1]/m['o'][0]-1), len(m['ts']), m['mint']) for m in mints]
lt.sort()
L('lifetime o0->clast: median %+.3f  frac<-0.9 %.3f' % (
    float(np.median([x[0] for x in lt])), float(np.mean([x[0] < -0.9 for x in lt]))))
L('worst lifetimes', lt[:5]); L('best lifetimes', lt[-5:])

# bar spacing
gaps = np.concatenate([np.diff(m['ts']) for m in mints])
L('bar gap secs pctiles', [float(np.percentile(gaps, q)) for q in (50, 75, 90, 99)])
L('bars per mint pctiles', [float(np.percentile([len(m['ts']) for m in mints], q)) for q in (10,25,50,75,90,100)])
o.close()
