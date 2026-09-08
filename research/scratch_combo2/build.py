import os, sys, json, sqlite3, hashlib, math, pickle
import numpy as np

S = "/home/anont/meme/research/scratch_combo2"
LOG = open(os.path.join(S, "build_log.txt"), "w")
def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def h3(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

con = sqlite3.connect("file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro", uri=True)
rows = con.execute("select mint,pool,n_bars,first_ts,last_ts,bars_json,fetched_at,status from ohlcv").fetchall()
log("total ohlcv rows", len(rows))

keep = []
n_holdout = 0
for mint, pool, n_bars, first_ts, last_ts, bj, fetched_at, status in rows:
    hh = h3(mint)
    if hh == 0:
        n_holdout += 1
        continue
    if not bj or not n_bars or n_bars < 8:
        continue
    bars = json.loads(bj)
    bars.sort(key=lambda b: b[0])
    keep.append((mint, hh, bars, fetched_at, last_ts))
log("holdout skipped:", n_holdout, "usable:", len(keep))

# ---- snapshot overlap check ----
snapmints = set()
with open("/home/anont/meme/research/midcap/fresh_snapshots.jsonl") as f:
    for line in f:
        i = line.find('"mint"')
        if i < 0: continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get("mint")
        if m and h3(m) != 0:
            snapmints.add(m)
ohl = set(k[0] for k in keep)
log("snapshot mints(h!=0):", len(snapmints), "overlap with ohlcv:", len(snapmints & ohl))

# ---- creator prior creates ----
creates = []
wc = sqlite3.connect("file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro", uri=True)
for mint, creator, block_time in wc.execute("select mint,creator,block_time from window_label"):
    if not mint or h3(mint) == 0: continue
    if block_time: creates.append((block_time, creator, mint))
creates.sort()
prior_ct = {}; seen = {}
for bt, cr, m in creates:
    prior_ct[m] = seen.get(cr, 0); seen[cr] = seen.get(cr, 0) + 1
create_time = {m: bt for bt, cr, m in creates}
log("window_label rows(h!=0):", len(creates), "ohlcv mints with create_time:",
    sum(1 for m in ohl if m in create_time))

FEATS = ["ret5", "ret15", "ret60", "vol5", "volratio", "volaccel", "rvol", "dd", "age",
         "gap", "maxgap30", "bars30", "logpx", "body", "range15", "vwapdev", "vwapdev60",
         "hilopos", "upfrac", "retlife", "priorcr"]
NF = len(FEATS)

rows_f = []; rows_meta = []; mints = []; alt_rows = []
MARGIN = 120.0
EXIT_H = 900.0
LAG_CAP = 1800.0     # exit bar must be within 30 min of the 15m target, else dropout

for mint, hh, bars, fetched_at, last_ts in keep:
    ts = np.array([b[0] for b in bars], dtype=np.float64)
    op = np.array([b[1] for b in bars], dtype=np.float64)
    hi = np.array([b[2] for b in bars], dtype=np.float64)
    lo = np.array([b[3] for b in bars], dtype=np.float64)
    cl = np.array([b[4] for b in bars], dtype=np.float64)
    vo = np.array([b[5] for b in bars], dtype=np.float64)
    good = (cl > 0) & (op > 0) & (hi > 0) & (lo > 0) & np.isfinite(vo)
    if good.sum() < 10: continue
    ts, op, hi, lo, cl, vo = ts[good], op[good], hi[good], lo[good], cl[good], vo[good]
    n = len(ts)
    horizon = float(fetched_at) if fetched_at else float(ts[-1])

    cum_v = np.concatenate([[0.0], np.cumsum(vo)])
    tp = (hi + lo + cl) / 3.0
    cum_vtp = np.concatenate([[0.0], np.cumsum(vo * tp)])
    runmax = np.maximum.accumulate(hi)
    bret = np.concatenate([[np.nan], cl[1:] / cl[:-1] - 1.0])
    gaps = np.concatenate([[np.nan], ts[1:] - ts[:-1]])

    tcreate = create_time.get(mint)
    if tcreate is None: tcreate = ts[0]
    pcr = float(prior_ct.get(mint, np.nan)) if mint in prior_ct else np.nan
    mid = len(mints); nrow0 = len(rows_meta)

    for i in range(3, n - 1):
        t_i = ts[i]
        entry_ts = ts[i + 1]; entry_px = op[i + 1]
        target = entry_ts + EXIT_H
        if target + MARGIN > horizon: continue
        j = int(np.searchsorted(ts, target, side="left"))
        if j < n and (ts[j] - target) <= LAG_CAP:
            exit_px = op[j]; exit_ts = ts[j]; resolved = 1; lagx = ts[j] - target
        else:
            exit_px = np.nan; exit_ts = target + LAG_CAP; resolved = 0; lagx = np.nan
        alt = []
        for H in (300.0, 600.0, 1800.0, 3600.0):
            tg2 = entry_ts + H
            if tg2 + MARGIN > horizon:
                alt.append((np.nan, tg2 + LAG_CAP, 0)); continue
            j2 = int(np.searchsorted(ts, tg2, side="left"))
            if j2 < n and (ts[j2] - tg2) <= LAG_CAP:
                alt.append((op[j2], ts[j2], 1))
            else:
                alt.append((np.nan, tg2 + LAG_CAP, 0))
        jj = j if (j < n and (ts[j] - target) <= LAG_CAP) else int(np.searchsorted(ts, target + LAG_CAP, side="left"))
        if jj > i + 1:
            seg_hi = float(np.max(hi[i + 1:jj + 1])); seg_lo = float(np.min(lo[i + 1:jj + 1]))
        else:
            seg_hi = float(hi[i + 1]); seg_lo = float(lo[i + 1])
        alt_rows.append([a[0] for a in alt] + [a[1] for a in alt] + [a[2] for a in alt] + [seg_hi, seg_lo])

        k5 = int(np.searchsorted(ts, t_i - 300.0, side="right")) - 1
        k15 = int(np.searchsorted(ts, t_i - 900.0, side="right")) - 1
        k60 = int(np.searchsorted(ts, t_i - 3600.0, side="right")) - 1
        ret5 = cl[i] / cl[k5] - 1.0 if k5 >= 0 else np.nan
        ret15 = cl[i] / cl[k15] - 1.0 if k15 >= 0 else np.nan
        ret60 = cl[i] / cl[k60] - 1.0 if k60 >= 0 else np.nan
        s5 = int(np.searchsorted(ts, t_i - 300.0, side="right"))
        s15 = int(np.searchsorted(ts, t_i - 900.0, side="right"))
        s30 = int(np.searchsorted(ts, t_i - 1800.0, side="right"))
        s60 = int(np.searchsorted(ts, t_i - 3600.0, side="right"))
        vol5 = cum_v[i + 1] - cum_v[s5]
        vol15 = cum_v[i + 1] - cum_v[s15]
        vol60 = cum_v[i + 1] - cum_v[s60]
        volratio = (vol15 / vol60) if vol60 > 0 else np.nan
        volaccel = (vol5 / (vol60 / 12.0)) if vol60 > 0 else np.nan
        seg = bret[max(s15, 1):i + 1]; seg = seg[np.isfinite(seg)]
        rvol = float(np.std(seg)) if len(seg) >= 3 else np.nan
        upfrac = float(np.mean(seg > 0)) if len(seg) >= 3 else np.nan
        dd = cl[i] / runmax[i] - 1.0
        age = (t_i - tcreate) / 60.0
        gap = gaps[i]
        g30 = gaps[max(s30, 1):i + 1]; g30 = g30[np.isfinite(g30)]
        maxgap30 = float(np.max(g30)) if len(g30) else np.nan
        bars30 = float(i + 1 - s30)
        logpx = math.log(cl[i])
        rng = hi[i] - lo[i]
        body = (cl[i] - op[i]) / rng if rng > 0 else 0.0
        h15 = float(np.max(hi[s15:i + 1])); l15 = float(np.min(lo[s15:i + 1]))
        range15 = (h15 - l15) / cl[i]
        hilopos = (cl[i] - l15) / (h15 - l15) if h15 > l15 else np.nan
        vv15 = vol15; vv60 = vol60
        vwapdev = (cl[i] / ((cum_vtp[i + 1] - cum_vtp[s15]) / vv15) - 1.0) if vv15 > 0 else np.nan
        vwapdev60 = (cl[i] / ((cum_vtp[i + 1] - cum_vtp[s60]) / vv60) - 1.0) if vv60 > 0 else np.nan
        retlife = cl[i] / cl[0] - 1.0

        rows_f.append((ret5, ret15, ret60, vol5, volratio, volaccel, rvol, dd, age, gap,
                       maxgap30, bars30, logpx, body, range15, vwapdev, vwapdev60,
                       hilopos, upfrac, retlife, pcr))
        rows_meta.append((mid, hh, t_i, entry_ts, entry_px, exit_ts, exit_px, resolved, lagx))
    if len(rows_meta) > nrow0:
        mints.append(mint)
    else:
        pass

X = np.array(rows_f, dtype=np.float64)
MID = np.array([r[0] for r in rows_meta], dtype=np.int32)
HH = np.array([r[1] for r in rows_meta], dtype=np.int8)
SIGT = np.array([r[2] for r in rows_meta], dtype=np.float64)
ENTT = np.array([r[3] for r in rows_meta], dtype=np.float64)
ENTP = np.array([r[4] for r in rows_meta], dtype=np.float64)
EXTT = np.array([r[5] for r in rows_meta], dtype=np.float64)
EXTP = np.array([r[6] for r in rows_meta], dtype=np.float64)
RES = np.array([r[7] for r in rows_meta], dtype=np.int8)
LAG = np.array([r[8] for r in rows_meta], dtype=np.float64)

log("rows", X.shape, "mints", len(mints))
log("resolved rate", float(RES.mean()))
log("train(h=1) rows", int((HH == 1).sum()), "mints", len(set(MID[HH == 1].tolist())))
log("valid(h=2) rows", int((HH == 2).sum()), "mints", len(set(MID[HH == 2].tolist())))
gross = EXTP / ENTP - 1.0
gf = gross[np.isfinite(gross)]
log("gross mean/median:", float(gf.mean()), float(np.median(gf)))
gs = np.sort(gf)
log("gross quantiles:", [round(float(gs[int(q*(len(gs)-1))]), 4) for q in (0,.01,.05,.25,.5,.75,.95,.99,.999,1)])
for k, f in enumerate(FEATS):
    col = X[:, k]; fin = np.isfinite(col)
    log("feat", f, "finite", int(fin.sum()),
        "q:", [round(float(np.nanquantile(col, q)), 5) for q in (0.05, .25, .5, .75, .95)])

ALT = np.array(alt_rows, dtype=np.float64)
log("ALT shape", ALT.shape)
for zi, H in enumerate((300, 600, 1800, 3600)):
    log("alt H", H, "res rate", round(float(np.nanmean(ALT[:, 8 + zi])), 4))
mfe = ALT[:, 12] / ENTP - 1.0; mae = ALT[:, 13] / ENTP - 1.0
log("MFE q:", [round(float(np.nanquantile(mfe, q)), 4) for q in (.05, .25, .5, .75, .95)])
log("MAE q:", [round(float(np.nanquantile(mae, q)), 4) for q in (.05, .25, .5, .75, .95)])
np.savez_compressed(os.path.join(S, "mat.npz"), X=X, MID=MID, HH=HH, SIGT=SIGT, ENTT=ENTT,
                    ENTP=ENTP, EXTT=EXTT, EXTP=EXTP, RES=RES, LAG=LAG, ALT=ALT)
json.dump({"mints": mints, "feats": FEATS}, open(os.path.join(S, "mints.json"), "w"))
log("SAVED")
