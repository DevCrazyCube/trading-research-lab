import sqlite3, json, random, statistics as st, sys
sys.path.insert(0, '/home/anont/meme/research/h69')
from cell import cell_trades, rand_trades, med, pct

c = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
rows = [(m, sorted(json.loads(bj), key=lambda x: x[0]))
        for m, bj in c.execute("select mint,bars_json from ohlcv where status='ok' and bars_json is not null")]

# how long does the "15-minute" hold ACTUALLY last, in wall-clock minutes?
def holds(bars, idxs, hold=15):
    out = []
    for i in idxs:
        if i + 1 >= len(bars): continue
        e = bars[i + 1]
        want = e[0] + 60 * hold
        for k in bars[i + 2:]:
            if k[0] >= want:
                out.append((k[0] - e[0]) / 60.0); break
    return out

rnd = random.Random(4242)
allh = []
for m, b in rows:
    idxs = [rnd.randrange(len(b) - 1) for _ in range(5)] if len(b) > 2 else []
    allh += holds(b, idxs)
allh.sort()
print('RANDOM-BAR realised hold length (minutes) for a nominal 15m hold:')
print('  n=%d p10=%.0f p25=%.0f MED=%.0f p75=%.0f p90=%.0f p99=%.0f max=%.0f'
      % (len(allh), pct(allh, .10), pct(allh, .25), pct(allh, .50), pct(allh, .75),
         pct(allh, .90), pct(allh, .99), allh[-1]))
print('  share of holds longer than 30 min: %.1f%%' % (100 * sum(1 for x in allh if x > 30) / len(allh)))
print('  share of holds longer than 60 min: %.1f%%' % (100 * sum(1 for x in allh if x > 60) / len(allh)))

# and the cell's
ch = []
for m, b in rows:
    ts = {x[0]: k for k, x in enumerate(b)}
    idxs = []
    for i, x in enumerate(b):
        j = ts.get(x[0] - 300)
        if j is None: continue
        if b[j][4] <= 0 or x[4] <= 0: continue
        r = x[4] / b[j][4] - 1
        if 0.048 <= r <= 0.095: idxs.append(i)
    ch += holds(b, idxs)
ch.sort()
print('CELL realised hold length (minutes):')
print('  n=%d p10=%.0f p25=%.0f MED=%.0f p75=%.0f p90=%.0f p99=%.0f'
      % (len(ch), pct(ch, .10), pct(ch, .25), pct(ch, .50), pct(ch, .75), pct(ch, .90), pct(ch, .99)))

# STRICT variant: require the exit bar to be within 15..25 min of entry, else UNRESOLVED
def strict(bars, idxs, hold=15, maxlate=600):
    out = []
    for i in idxs:
        if i + 1 >= len(bars): continue
        e = bars[i + 1]
        if e[1] <= 0: continue
        want = e[0] + 60 * hold
        x = None
        for k in bars[i + 2:]:
            if k[0] >= want:
                x = k if k[0] <= want + maxlate else None
                break
        out.append(x[1] / e[1] - 1.0 if x else None)
    return out

TOLL = 0.0114
for name, sel in (('CELL', 'cell'), ('CTRL', 'rand')):
    per = {}
    for m, b in rows:
        ts = {x[0]: k for k, x in enumerate(b)}
        if sel == 'cell':
            idxs = []
            for i, x in enumerate(b):
                j = ts.get(x[0] - 300)
                if j is None or b[j][4] <= 0 or x[4] <= 0: continue
                r = x[4] / b[j][4] - 1
                if 0.048 <= r <= 0.095: idxs.append(i)
        else:
            idxs = [rnd.randrange(len(b) - 1) for _ in range(6)] if len(b) > 2 else []
        t = strict(b, idxs)
        if t: per[m] = t
    for chg in (-0.30, -0.50, -1.00):
        v = [(x - TOLL) if x is not None else chg for t in per.values() for x in t]
        res = 100 * sum(1 for t in per.values() for x in t if x is not None) / len(v)
        print('STRICT(exit within 15-25m) %s charge %4.0f%%  n=%5d clusters=%3d res=%5.1f%% mean=%+6.2f%% MED=%+6.2f%%'
              % (name, 100 * chg, len(v), len(per), res, 100 * st.mean(v), 100 * med(v)))
