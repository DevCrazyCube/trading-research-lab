import numpy as np, os, json

OUT = '/home/anont/meme/.combo2way'
d = np.load(os.path.join(OUT, 'ds.npz'), allow_pickle=True)
TS, OP, CL = d['TS'], d['OP'], d['CL']
MID, VALID, X, EXIT = d['MID'], d['VALID'], d['X'], d['EXIT']
hh, FEAT, MINTS = d['hh'], list(d['FEAT']), d['mints']
N = len(TS)
NM = len(MINTS)

# ---- precompute, per signal bar i: entry e=i+1 (next REAL bar), exit j, gross ----
ENT = np.arange(N) + 1
GROSS = np.full(N, np.nan)
BLOCK = np.full(N, -1, np.int64)
ok = VALID.copy()
e = np.clip(ENT, 0, N - 1)
same = (MID[e] == MID) & VALID
ok &= same
j = np.where(same, EXIT[e], -1)
res = ok & (j >= 0)
GROSS[res] = CL[j[res]] / np.maximum(OP[e[res]], 1e-300) - 1.0
BLOCK[ok] = np.where(j[ok] >= 0, j[ok], e[ok])
DROP = ok & (j < 0)            # no exit bar within 15 minutes -> dropout
SIG = np.flatnonzero(ok)       # every legal signal bar

TRAIN_M = np.flatnonzero(hh == 1)
VAL_M = np.flatnonzero(hh == 2)
is_train = np.zeros(NM, bool); is_train[TRAIN_M] = True
is_val = np.zeros(NM, bool); is_val[VAL_M] = True
SIG_TR = SIG[is_train[MID[SIG]]]
SIG_VA = SIG[is_val[MID[SIG]]]


def greedy(sel):
    """Contract A (enter next real bar) + B (one open position per mint)."""
    acc = []
    cur = -1
    free = -1
    Mm, Bb = MID, BLOCK
    for i in sel:
        m = Mm[i]
        if m != cur:
            cur = m
            free = -1
        if i <= free:
            continue
        acc.append(i)
        free = Bb[i]
    return np.array(acc, dtype=np.int64)


def score(acc, toll=0.0114, dropcharge=-0.30):
    """Mint-equal weighting (contract C), simple returns (F)."""
    if len(acc) == 0:
        return None
    g = GROSS[acc]
    r = np.where(np.isnan(g), dropcharge, (1.0 + g) * (1.0 - toll) - 1.0)
    m = MID[acc]
    cnt = np.bincount(m, minlength=NM).astype(float)
    tot = np.bincount(m, weights=r, minlength=NM)
    live = cnt > 0
    per_mint = tot[live] / cnt[live]
    return dict(n=int(len(acc)), k=int(live.sum()),
                mean=float(per_mint.mean()),
                median=float(np.median(per_mint)),
                trade_median=float(np.median(r)),
                res=float(np.mean(~np.isnan(g))),
                per_mint=per_mint)


def boot_lo(per_mint, B=2000, seed=0, q=2.5):
    rng = np.random.default_rng(seed)
    k = len(per_mint)
    idx = rng.integers(0, k, size=(B, k))
    means = per_mint[idx].mean(axis=1)
    return float(np.percentile(means, q)), float((means <= 0).mean())


def ev(sel, **kw):
    return score(greedy(sel), **kw)
