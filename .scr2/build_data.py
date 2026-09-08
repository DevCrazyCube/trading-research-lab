"""Build cached feature+bar data for the deployer-identity sweep.
HOLDOUT RULE: bars are loaded ONLY for mints with md5(mint)%3 in (1,2).
window_label CREATE rows (no return information whatsoever) are read for all
creates because creator-history counts are a property of the creator, not of
any reserved mint's price path.  No price/return data is ever read for h==0.
"""
import sqlite3, json, hashlib, collections, pickle, os

SCR = '/home/anont/meme/.scr2'
def H(m): return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

log = []
def p(*a): log.append(" ".join(str(x) for x in a))

# ---------- window labels (create metadata only) ----------
wl = sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
rows = wl.execute("select mint,creator,create_slot,block_time,complete,bonding_curve from window_label").fetchall()
wl.close()

meta = {}
for m, cr, slot, bt, comp, bc in rows:
    meta[m] = dict(creator=cr, slot=slot, bt=bt, complete=comp, bc=bc)

bycre = collections.defaultdict(list)
for m, cr, slot, bt, comp, bc in rows:
    bycre[cr].append((bt, slot, m, comp))
for k in bycre:
    bycre[k].sort()

# ---------- bars (h in 1,2 ONLY) ----------
oh = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
bars = {}
nread = 0
for mint, bj, nb in oh.execute("select mint,bars_json,n_bars from ohlcv where status='ok' and n_bars>0"):
    if H(mint) == 0:
        continue           # RESERVED - never touched
    b = json.loads(bj)
    b.sort(key=lambda r: r[0])
    # drop degenerate bars
    b = [r for r in b if r[1] and r[1] > 0 and r[4] and r[4] > 0 and r[2] > 0 and r[3] > 0]
    if len(b) < 3:
        continue
    bars[mint] = b
    nread += 1
oh.close()
p("bars loaded (h1/h2 only):", nread, "total bars", sum(len(v) for v in bars.values()))
p("h split:", collections.Counter(H(m) for m in bars))

# ---------- forward-return table for prior-outcome features (h1/h2 only) ----------
def fwd_ret(mint, horizon_s):
    b = bars.get(mint)
    if not b: return None
    t0 = b[0][0]; px0 = b[0][1]
    tgt = t0 + horizon_s
    for r in b:
        if r[0] >= tgt:
            return r[1] / px0 - 1.0
    return None

fwd15 = {m: fwd_ret(m, 900) for m in bars}
fwd60 = {m: fwd_ret(m, 3600) for m in bars}

# ---------- creator features, strictly chronological ----------
feat = {}
for mint in bars:
    mi = meta.get(mint)
    if not mi:
        continue
    cr = mi['creator']; t = mi['bt']; sl = mi['slot']
    prior = [x for x in bycre[cr] if (x[0], x[1]) < (t, sl)]
    n = len(prior)
    f = {}
    f['nprior'] = n
    f['prior_grad'] = sum(1 for x in prior if x[3] == 1)
    f['prior_gradrate'] = (f['prior_grad'] / n) if n else -1.0
    # lag-safe graduation view: only prior coins created >=1h before -> their
    # graduation status is very likely already resolved at t
    pl = [x for x in prior if x[0] <= t - 3600]
    f['nprior_lag'] = len(pl)
    f['prior_grad_lag'] = sum(1 for x in pl if x[3] == 1)
    f['prior_gradrate_lag'] = (f['prior_grad_lag'] / len(pl)) if pl else -1.0
    # launch burst
    for w in (300, 600, 1800, 3600, 7200):
        f['burst%d' % w] = sum(1 for x in prior if x[0] >= t - w)
    f['gap'] = (t - prior[-1][0]) if prior else 10 ** 9
    f['age_creator'] = (t - prior[0][0]) if prior else 0
    f['rate_per_h'] = (n / max(1.0, f['age_creator'] / 3600.0)) if n else 0.0
    # prior-coin realised outcomes, resolved BEFORE t, h1/h2 coins only
    for tag, tbl, hz in (('o15', fwd15, 900), ('o60', fwd60, 3600)):
        vals = [tbl[x[2]] for x in prior
                if x[2] in tbl and tbl[x[2]] is not None and x[0] + hz <= t]
        f['n_' + tag] = len(vals)
        f['mean_' + tag] = (sum(vals) / len(vals)) if vals else None
        f['max_' + tag] = max(vals) if vals else None
    feat[mint] = f

p("feature rows:", len(feat))
p("nprior dist:", sorted(collections.Counter(min(feat[m]['nprior'], 60) for m in feat).items()))
p("with n_o15>0:", sum(1 for m in feat if feat[m]['n_o15'] > 0))
p("with prior_grad>=1:", sum(1 for m in feat if feat[m]['prior_grad'] >= 1))

with open(SCR + '/data.pkl', 'wb') as fh:
    pickle.dump(dict(bars=bars, feat=feat,
                     meta={m: meta[m] for m in bars if m in meta}), fh)
open(SCR + '/build_data.out', 'w').write("\n".join(log))
