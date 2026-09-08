"""H69: apply the FROZEN pump.fun cell to LetsBonk/LaunchLab migrated tokens.

Cell: prior 5-min simple return in [+4.8%, +9.5%] -> enter NEXT REAL bar's open -> 15m hold.
Control: same mints, uniformly random entry bars, identical entry/exit machinery.
SIMPLE returns. Cluster-bootstrap by MINT. Dropouts charged at -30/-50/-100%.
"""
import sqlite3, json, random, statistics as st, sys, argparse
sys.path.insert(0, '/home/anont/meme/research/h69')
from cell import cell_trades, rand_trades, summarize, boot_diff, boot_mean, pct, med

ap = argparse.ArgumentParser()
ap.add_argument('--db', default='/home/anont/meme/research/h69/h69_ohlcv.sqlite')
ap.add_argument('--pumpfun', action='store_true')
ap.add_argument('--toll', type=float, default=0.030)
ap.add_argument('--draws', type=int, default=2000)
ap.add_argument('--minbars', type=int, default=0)
a = ap.parse_args()

if a.pumpfun:
    c = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
    q = "select mint,bars_json from ohlcv where status='ok' and bars_json is not null"
else:
    c = sqlite3.connect('file:%s?mode=ro' % a.db, uri=True)
    q = "select mint,bars_json from t where status='ok' and bars_json is not null"

rows = []
for m, bj in c.execute(q):
    b = sorted(json.loads(bj), key=lambda x: x[0])
    if len(b) >= a.minbars:
        rows.append((m, b))
print('mints with bars: %d   median bars/mint: %s   total bars: %d'
      % (len(rows), med([len(b) for _, b in rows]), sum(len(b) for _, b in rows)))

# how many mints are even eligible (have any bar with a real bar exactly 5 min earlier)
for MODE in ('time', 'bars'):
    for GAP in (None, 900):
        rnd = random.Random(4242)
        A, B = {}, {}
        for m, b in rows:
            t = cell_trades(b, gap_tol=GAP, mode=MODE)
            if t:
                A[m] = t
        for m, b in rows:
            if m in A:
                B[m] = rand_trades(b, max(3, len(A[m])), rnd, gap_tol=GAP, mode=MODE)
        if not A:
            print('\n=== exit=%s entry_gap_tol=%s : NO TRADES ===' % (MODE, GAP)); continue
        print('\n=== exit=%s  entry_gap_tol=%s  TOLL=%.2f%% RT ==='
              % (MODE, GAP, 100 * a.toll))
        for ch in (-0.30, -0.50, -1.00):
            v, res, tot = summarize(A, ch, a.toll)
            vr, _, _ = summarize(B, ch, a.toll)
            bd = boot_diff(A, B, ch, a.toll, draws=a.draws)
            bm = boot_mean(A, ch, a.toll, draws=a.draws)
            print('  charge %4.0f%%  n=%5d clusters=%3d res=%5.1f%%  CELL mean=%+7.2f%% MED=%+7.2f%% meanCI95[%+7.2f,%+7.2f]'
                  % (100 * ch, tot, len(A), res, 100 * st.mean(v), 100 * med(v),
                     100 * pct(bm, .025), 100 * pct(bm, .975)))
            print('                                            CTRL mean=%+7.2f%% MED=%+7.2f%%   (CELL-CTRL) CI95[%+7.2f,%+7.2f]'
                  % (100 * st.mean(vr), 100 * med(vr), 100 * pct(bd, .025), 100 * pct(bd, .975)))
