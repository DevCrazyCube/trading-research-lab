import sys, numpy as np
sys.path.insert(0, '/home/anont/meme/.scr_fc3')
from engine import build_hold, evaluate, MINTS, BARS, GATE_SIG

STR, CAND = build_hold(15)
st = STR[('time', 'flat')]
allr = []
permint = {}
for m in MINTS:
    s = st.get(m)
    if not s:
        continue
    sig, bankA, bankW, openR, openW, epx, dropv, exitbar = s
    r = np.where(dropv, -0.5, openR * epx * (1 - 0.0114) - 1.0)
    allr.append(r)
    permint[m] = r
allr = np.concatenate(allr)
print('pooled every-bar 15m net: n=%d mean=%+.4f med=%+.4f' % (len(allr), allr.mean(), np.median(allr)))
q = np.percentile(allr, [0.5, 1, 5, 25, 50, 75, 95, 99, 99.5])
print('pctiles', ' '.join('%+.3f' % x for x in q))
print('top 10', np.sort(allr)[-10:])
print('bottom 10', np.sort(allr)[:10])
# per-mint mean of every-bar (overlapping) -- contract violation, only a diagnostic
pm = np.array([permint[m].mean() for m in permint])
print('per-mint mean of all-bar 15m: mean=%+.4f med=%+.4f' % (pm.mean(), np.median(pm)))
worst = sorted(permint, key=lambda m: permint[m].mean())
print('worst mint mean', permint[worst[0]].mean(), len(BARS[worst[0]]))
best = worst[-1]
print('best mint mean', permint[best].mean(), len(BARS[best]))
a = BARS[best]
print('best mint first 5 bars', a[:5].tolist())
i = int(np.argmax(permint[best]))
print('best trade idx', i, 'bars around:', a[max(0, i - 1):i + 4].tolist())
