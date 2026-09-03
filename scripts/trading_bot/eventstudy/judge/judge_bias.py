#!/usr/bin/env python3
"""Is the post-hoc 'momentum' survivor a FUNDING signal, or just a long-bias artifact
of using the cross-sectional MEDIAN as the control for a right-skewed MEAN?"""
import numpy as np, judge_panel as J

syms, days, close, qv, fund = J.load()
lr, med, cnt = J.market_control(close)
S, D = close.shape
medf = np.where(np.isfinite(med), med, 0.0)
cmed = np.concatenate([[0.0], np.cumsum(medf)])
lclose = np.log(close)
RT = 0.241

def excess(h):
    out = np.full((S, D), np.nan)
    ctrl = cmed[1+h:D+1] - cmed[1:D+1-h]
    out[:, :D-h] = (lclose[:, h:] - lclose[:, :D-h]) - ctrl[None, :]
    return out * 100.0

elig = (qv >= 1e6) & np.isfinite(fund) & np.isfinite(close)
formable = (elig.sum(axis=0) >= 30) & np.isfinite(med)

print("=" * 78)
print("PLACEBO: mean market-controlled excess of the ENTIRE eligible universe")
print("(no funding signal used at all -- pure 'be long a liquid alt perp')")
print("=" * 78)
for h in (1, 3, 7):
    ex = excess(h)
    vals, cls, symi = [], [], []
    topv, topc, botv, botc = [], [], [], []
    for d in range(D):
        if not formable[d]: continue
        idx = np.where(elig[:, d])[0]
        e = ex[idx, d]; m = np.isfinite(e)
        vals.append(e[m]); cls.append(np.full(m.sum(), d)); symi.append(idx[m])
        f = fund[idx, d]; k = max(1, int(round(len(idx) * 0.10)))
        o = np.argsort(f, kind="stable")
        t, b = idx[o[-k:]], idx[o[:k]]
        et = ex[t, d]; mt = np.isfinite(et); topv.append(et[mt]); topc.append(np.full(mt.sum(), d))
        eb = ex[b, d]; mb = np.isfinite(eb); botv.append(eb[mb]); botc.append(np.full(mb.sum(), d))
    v = np.concatenate(vals); c = np.concatenate(cls)
    tv = np.concatenate(topv); tc = np.concatenate(topc)
    bv = np.concatenate(botv); bc = np.concatenate(botc)
    bs = J.boot_cluster(v, c)
    print(f"\nh={h}  ALL ELIGIBLE (placebo long): n={len(v)} clusters={len(np.unique(c))}")
    print(f"      mean={v.mean():+.4f}pp  median={np.median(v):+.4f}pp  "
          f"CI=[{np.percentile(bs,2.5):+.4f},{np.percentile(bs,97.5):+.4f}]")
    print(f"      LONG top-funding decile  mean={tv.mean():+.4f}pp   (the 'survivor')")
    print(f"      LONG bottom-funding decile mean={bv.mean():+.4f}pp")
    print(f"      >>> SIGNAL = top - placebo = {tv.mean()-v.mean():+.4f}pp   "
          f"(this is what funding actually adds)")
    # dollar-neutral decile spread: long top, short bottom -- removes the universal long bias
    sv = np.concatenate([tv, -bv]); sc = np.concatenate([tc, bc])
    sb = J.boot_cluster(sv, sc)
    sp = tv.mean() - bv.mean()
    print(f"      DOLLAR-NEUTRAL spread (long top / short bottom) = {sp:+.4f}pp"
          f"  CI=[{np.percentile(sb,2.5)*2:+.4f},{np.percentile(sb,97.5)*2:+.4f}]")
    print(f"      spread NET of 2x round trip ({2*RT:.3f}pp, two legs) = {sp-2*RT:+.4f}pp"
          f"  ratio={sp/(2*RT):.2f}x")
