#!/usr/bin/env python3
"""POSTURE B.2: MEASURE the adverse-selection cost of resting quotes.

Binance USD-M 5m klines WITH real intrabar HIGH/LOW, so a fill is a genuine
touch. That matters: it captures BOTH informed and uninformed fills, so this is
not the pessimistic "only filled when run over" proxy.

DECLARED BEFORE COUNTING:
  GATE 1 minima : >=10 symbols, >=200,000 filled quotes, >=300 date clusters.
  GATE 2        : MDE at alpha=0.05 one-sided, power=0.80, ICC=0.3, clustered by DATE.
  GATE 3        : cluster bootstrap by DATE, 5000 draws, seed 20260903.
  KILL LINE     : a resting quote is worth posting only if mean markout exceeds
                  the maker fee actually payable by a $10k-$1M account.
                  Binance USD-M VIP0 maker = 0.0200% = 2.0 bp (sourced).
                  PASS requires bootstrap CI-lo > 2.0 bp.

The quote model is DELIBERATELY OPTIMISTIC in the maker's favour: front of
queue, filled on any touch, no queue position, no inventory cap, no latency,
no cancel/replace cost. If it still loses under these assumptions, it loses.
"""
import os, glob, zipfile, math, json
import numpy as np

ROOT = "/home/anont/meme/research/data/orphanflush_cache/raw/klines5m"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT", "AVAXUSDT",
        "LINKUSDT", "DOGEUSDT", "LTCUSDT", "DOTUSDT", "NEARUSDT", "UNIUSDT",
        "AAVEUSDT", "ATOMUSDT"]
MONTHS_FROM = "2025-01"
SPREADS_BP = [1.0, 2.0, 5.0, 10.0]
HORIZONS = [1, 3, 6, 12]          # 5, 15, 30, 60 minutes
MAKER_FEE_BP = 2.0                # Binance USD-M VIP0 maker, sourced
SEED, NBOOT = 20260903, 5000
Z_A, Z_B, ICC = 1.6448536269514722, 0.8416212335729143, 0.30
MIN_SYM, MIN_FILLS, MIN_CLUST = 10, 200_000, 300


def load(sym):
    out = []
    for z in sorted(glob.glob(f"{ROOT}/{sym}/{sym}-5m-*.zip")):
        mon = os.path.basename(z)[:-4][-7:]
        if mon < MONTHS_FROM:
            continue
        try:
            with zipfile.ZipFile(z) as zf:
                raw = zf.read(zf.namelist()[0]).decode()
        except Exception:
            continue
        for line in raw.splitlines():
            p = line.split(",")
            if not p[0].strip().isdigit():
                continue
            out.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4])))
    if not out:
        return None
    out.sort()
    return np.array(out)


data = {}
for s in SYMS:
    a = load(s)
    if a is None or len(a) < 5000:
        print(f"  {s}: insufficient, skipped")
        continue
    data[s] = a
    print(f"  {s}: {len(a):,} bars")
print(f"\nsymbols loaded = {len(data)}")


def cluster_boot(day, val, nboot, seed):
    """vectorised cluster bootstrap by DATE (resample whole dates with replacement)"""
    u, inv = np.unique(day, return_inverse=True)
    nc = len(u)
    csum = np.bincount(inv, weights=val, minlength=nc)
    ccnt = np.bincount(inv, minlength=nc).astype(float)
    rng = np.random.default_rng(seed)
    pk = rng.integers(0, nc, size=(nboot, nc))
    return csum[pk].sum(1) / ccnt[pk].sum(1), nc


maxh = max(HORIZONS)
print("=" * 108)
print(f"{'spread':>8s} {'horiz':>7s} {'n fills':>12s} {'dates':>7s} {'markout bp':>11s} "
      f"{'95% CI (cluster boot)':>24s} {'MDE':>8s} {'net of 2bp fee':>15s}")
print("=" * 108)
res = {}
for s in SPREADS_BP:
    for hz in HORIZONS:
        D, M = [], []
        for sym, a in data.items():
            ts, o, h, l, c = a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]
            n = len(o)
            idx = np.arange(n - maxh)
            day = (ts // 86400000).astype(np.int64)[idx]
            f = s / 1e4
            pb = o[idx] * (1 - f)
            pa = o[idx] * (1 + f)
            fut = c[idx + hz]
            mb = (fut - pb) / pb * 1e4          # bid fill -> long
            ma = (pa - fut) / pa * 1e4          # ask fill -> short
            kb = l[idx] <= pb
            ka = h[idx] >= pa
            if kb.any():
                D.append(day[kb]); M.append(mb[kb])
            if ka.any():
                D.append(day[ka]); M.append(ma[ka])
        d = np.concatenate(D); m = np.concatenate(M)
        b, nc = cluster_boot(d, m, NBOOT, SEED)
        lo, hi = np.percentile(b, [2.5, 97.5])
        mbar = len(m) / nc
        DE = 1 + (mbar - 1) * ICC
        MDE = (Z_A + Z_B) * m.std(ddof=1) / math.sqrt(len(m) / DE)
        print(f"{s:7.1f}bp {hz*5:6d}m {len(m):12,} {nc:7,} {m.mean():+11.4f} "
              f"[{lo:+9.4f},{hi:+9.4f}] {MDE:8.4f} {m.mean()-MAKER_FEE_BP:+15.4f}")
        res[f"{s}_{hz}"] = dict(n=int(len(m)), clusters=int(nc), mean=float(m.mean()),
                                lo=float(lo), hi=float(hi), mde=float(MDE))
print("=" * 108)
ok = (len(data) >= MIN_SYM
      and min(v["n"] for v in res.values()) >= MIN_FILLS
      and min(v["clusters"] for v in res.values()) >= MIN_CLUST)
print(f"GATE 1 (>= {MIN_SYM} syms, >= {MIN_FILLS:,} fills, >= {MIN_CLUST} clusters): "
      f"{'PASS' if ok else 'FAIL'}")
best = max(res.values(), key=lambda v: v["lo"])
print(f"GATE 3 KILL LINE: best-case CI-lo across all (spread,horizon) = {best['lo']:+.4f} bp "
      f"vs 2.0 bp maker fee -> {'PASS' if best['lo'] > MAKER_FEE_BP else 'FAIL'}")
json.dump(res, open("/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/makeout.json", "w"), indent=1)
