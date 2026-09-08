import os, json, sqlite3, hashlib, math
import numpy as np
S = "/home/anont/meme/research/scratch_combo2"
L = open(os.path.join(S, "diag_log.txt"), "w")
def log(*a): L.write(" ".join(str(x) for x in a) + "\n"); L.flush()

def h3(m): return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3
con = sqlite3.connect("file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro", uri=True)
rows = con.execute("select mint,n_bars,first_ts,last_ts,bars_json,fetched_at from ohlcv").fetchall()

spans = []; totrets = []; nb = []
per_mint_mean_oo = []; per_mint_med_oo = []; per_mint_mean_cc = []
per_mint_mean_oo_cap = []
allret_oo = []
gapstat = []
opencloses = []
for mint, n_bars, first_ts, last_ts, bj, fetched_at in rows:
    if h3(mint) == 0 or not bj or not n_bars or n_bars < 20: continue
    b = json.loads(bj); b.sort(key=lambda r: r[0])
    ts = np.array([r[0] for r in b], float); op = np.array([r[1] for r in b], float)
    hi = np.array([r[2] for r in b], float); lo = np.array([r[3] for r in b], float)
    cl = np.array([r[4] for r in b], float)
    g = (cl > 0) & (op > 0)
    ts, op, hi, lo, cl = ts[g], op[g], hi[g], lo[g], cl[g]
    n = len(ts)
    if n < 20: continue
    nb.append(n); spans.append((ts[-1] - ts[0]) / 3600.0); totrets.append(cl[-1] / cl[0] - 1)
    gapstat.append(float(np.median(np.diff(ts))))
    opencloses.append(float(np.median(cl / op - 1)))
    # ALL overlapping 15m open->open returns (entry at bar k open, exit at first bar >= ts[k]+900)
    r_oo = []; r_cc = []
    for k in range(n - 1):
        j = int(np.searchsorted(ts, ts[k] + 900.0, side="left"))
        if j >= n or ts[j] - (ts[k] + 900.0) > 1800: continue
        r_oo.append(op[j] / op[k] - 1.0)
        r_cc.append(cl[j] / cl[k] - 1.0)
    if len(r_oo) < 5: continue
    r_oo = np.array(r_oo); r_cc = np.array(r_cc)
    allret_oo.append(r_oo)
    per_mint_mean_oo.append(r_oo.mean()); per_mint_med_oo.append(np.median(r_oo))
    per_mint_mean_oo_cap.append(np.minimum(r_oo, 3.0).mean())
    per_mint_mean_cc.append(r_cc.mean())

def q(a, name):
    a = np.array(a); s = np.sort(a)
    log(name, "n", len(a), "mean", round(float(a.mean()), 4),
        "q:", [round(float(s[int(x*(len(s)-1))]), 4) for x in (0, .05, .25, .5, .75, .95, 1)])

log("mints", len(nb))
q(nb, "bars_per_mint"); q(spans, "span_hours"); q(totrets, "total_close_return")
q(gapstat, "median_bar_gap_s"); q(opencloses, "median (close/open-1) per mint")
q(per_mint_mean_oo, "PER-MINT mean 15m open->open (uncapped)")
q(per_mint_mean_oo_cap, "PER-MINT mean 15m open->open (cap +300%)")
q(per_mint_med_oo, "PER-MINT median 15m open->open")
q(per_mint_mean_cc, "PER-MINT mean 15m close->close (uncapped)")
allr = np.concatenate(allret_oo)
q(allr, "POOLED all 15m open->open")
log("pooled mean capped", round(float(np.minimum(allr, 3.0).mean()), 4),
    "pooled median", round(float(np.median(allr)), 4))
log("mint-equal mean of capped per-mint means:", round(float(np.mean(per_mint_mean_oo_cap)), 4),
    "median:", round(float(np.median(per_mint_mean_oo_cap)), 4))

# how much does open-vs-close entry/exit matter?
log("--- open->open vs close->close per-mint mean diff:",
    round(float(np.mean(per_mint_mean_oo) - np.mean(per_mint_mean_cc)), 4))
