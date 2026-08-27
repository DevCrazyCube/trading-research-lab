#!/usr/bin/env python3
"""INVENT 0822 crypto-tether: build every tether spread + its OU/rho1 diagnostics."""
from __future__ import annotations
import os, json
import numpy as np
import invent0822_tether_lib as L

OUT = "/home/anont/meme/research/trading_bot"

# ---- family A: stablecoins vs USDT (fair = 1.00, redemption anchor) ------------
STABLES = ["USDCUSDT", "TUSDUSDT", "BUSDUSDT", "USDPUSDT", "PAXUSDT",
           "FDUSDUSDT", "USDEUSDT", "USD1USDT", "SUSDUSDT"]
# ---- family B: wrapped / staked vs underlying --------------------------------
WRAPS = [("WBTCUSDT", "BTCUSDT", "parity"),
         ("WBETHUSDT", "ETHUSDT", "accrual"),
         ("BETHUSDT", "ETHUSDT", "parity"),
         ("BNSOLUSDT", "SOLUSDT", "accrual"),
         ("XAUTUSDT", "PAXGUSDT", "parity")]


def build(P):
    T = P.T
    S = {}   # name -> dict(dev_c=<deviation at close>, ret_o=<open->open spread ret>,
             #              ret_c=<close->close spread ret>, legs=int)
    # ---------------- A ----------------
    for s in STABLES:
        c = P.bn(s, "c"); o = P.bn(s, "o")
        if c is None:
            continue
        dev = np.log(c)                       # fair = log(1.0) = 0
        ro = np.full(T, np.nan); ro[:-1] = np.log(o[1:] / o[:-1])
        rc = np.full(T, np.nan); rc[:-1] = np.log(c[1:] / c[:-1])
        S["A:" + s] = dict(dev_c=dev, ret_o=ro, ret_c=rc, legs=1, fam="A")
    # ---------------- B ----------------
    for a, b, kind in WRAPS:
        ca, cb_ = P.bn(a, "c"), P.bn(b, "c")
        oa, ob = P.bn(a, "o"), P.bn(b, "o")
        if ca is None or cb_ is None:
            continue
        r = np.log(ca) - np.log(cb_)
        ro = np.full(T, np.nan); ro[:-1] = (np.log(oa[1:] / oa[:-1]) - np.log(ob[1:] / ob[:-1]))
        rc = np.full(T, np.nan); rc[:-1] = (np.log(ca[1:] / ca[:-1]) - np.log(cb_[1:] / cb_[:-1]))
        S["B:" + a] = dict(raw=r, dev_c=r.copy(), ret_o=ro, ret_c=rc, legs=2, fam="B", kind=kind)
    # ---------------- C: triangular cross-quote (Binance internal) -------------
    # no-arb identity: P(X/USDT) = P(X/USDC) * P(USDC/USDT)
    usdc = P.bn("USDCUSDT", "c"); usdc_o = P.bn("USDCUSDT", "o")
    tryq = P.xq("USDTTRY", "c"); tryq_o = P.xq("USDTTRY", "o")
    bases_usdc, bases_try = [], []
    for sym in P.xq_syms:
        if sym.endswith("USDC") and sym[:-4] + "USDT" in P.bn_syms:
            bases_usdc.append(sym[:-4])
        if sym.endswith("TRY") and sym[:-3] + "USDT" in P.bn_syms:
            bases_try.append(sym[:-3])
    tri = {}
    for tag, bases, stab_c, stab_o, invert in (("USDC", bases_usdc, usdc, usdc_o, False),
                                               ("TRY", bases_try, tryq, tryq_o, True)):
        G, Gr_o, Gr_c, QV = [], [], [], []
        for b in bases:
            q = b + tag
            u = b + "USDT"
            cq, cu = P.xq(q, "c"), P.bn(u, "c")
            oq, ou = P.xq(q, "o"), P.bn(u, "o")
            qv = P.bn(u, "qv")
            if cq is None or cu is None:
                continue
            # gap = log P_usdt - log P_quote - log(quote/usdt price)
            #   USDC: quote/usdt = USDCUSDT ;  TRY: quote/usdt = 1/USDTTRY
            lq = np.log(stab_c) if not invert else -np.log(stab_c)
            g = np.log(cu) - np.log(cq) - lq
            lqo = np.log(stab_o) if not invert else -np.log(stab_o)
            go = np.log(ou) - np.log(oq) - lqo
            r_o = np.full(T, np.nan); r_o[:-1] = go[1:] - go[:-1]
            r_c = np.full(T, np.nan); r_c[:-1] = g[1:] - g[:-1]
            G.append(g); Gr_o.append(r_o); Gr_c.append(r_c); QV.append(qv)
        tri[tag] = dict(gap=np.array(G), ro=np.array(Gr_o), rc=np.array(Gr_c),
                        qv=np.array(QV), bases=bases)
    # ---------------- D: cross-venue Coinbase vs Binance -----------------------
    cb_btc = P.cb("BTC-USD"); bn_btc = P.bn("BTCUSDT", "c")
    XB, XR, XQV, XN = [], [], [], []
    for s in P.cb_syms:
        base = s.split("-")[0]
        u = base + "USDT"
        if u not in P.bn_syms or base == "BTC":
            continue
        cc, cu = P.cb(s), P.bn(u, "c")
        qv = P.bn(u, "qv")
        b = np.log(cc) - np.log(cu)                       # contains USDT/USD
        nb = b - (np.log(cb_btc) - np.log(bn_btc))        # numeraire-neutral
        r = np.full(T, np.nan); r[:-1] = nb[1:] - nb[:-1]
        XB.append(nb); XR.append(r); XQV.append(qv); XN.append(base)
    xv = dict(nb=np.array(XB), rc=np.array(XR), qv=np.array(XQV), names=XN,
              usdt_usd=-(np.log(cb_btc) - np.log(bn_btc)))
    return S, tri, xv


def main():
    P = L.Panels()
    S, tri, xv = build(P)
    dates = P.dates()
    diags = []
    for k, v in S.items():
        d = L.diag_spread(v["dev_c"], k)
        f = np.isfinite(v["dev_c"])
        if f.sum():
            idx = np.where(f)[0]
            d["first"], d["last"] = int(dates[idx[0]]), int(dates[idx[-1]])
        diags.append(d)
    # aggregate triangular spreads
    for tag in ("USDC", "TRY"):
        g = tri[tag]["gap"]
        agg = np.nanmedian(np.where(np.isfinite(g), g, np.nan), axis=0)
        d = L.diag_spread(agg, f"C:{tag}_AGG_GAP"); d["n_bases"] = int(g.shape[0]); diags.append(d)
        # a representative single-name gap (highest median $vol)
        mv = np.nanmedian(np.where(np.isfinite(tri[tag]["qv"]), tri[tag]["qv"], np.nan), axis=1)
        j = int(np.nanargmax(mv))
        diags.append(L.diag_spread(g[j], f"C:{tag}_{tri[tag]['bases'][j]}_GAP"))
    nb = xv["nb"]
    aggnb = np.nanmedian(np.where(np.isfinite(nb), nb, np.nan), axis=0)
    diags.append(L.diag_spread(aggnb, "D:XVENUE_AGG_NUMNEUT"))
    diags.append(L.diag_spread(xv["usdt_usd"], "D:XVENUE_IMPLIED_USDTUSD"))
    mv = np.nanmedian(np.where(np.isfinite(xv["qv"]), xv["qv"], np.nan), axis=1)
    for j in np.argsort(-np.nan_to_num(mv))[:3]:
        diags.append(L.diag_spread(nb[j], f"D:XVENUE_{xv['names'][j]}"))
    with open(os.path.join(OUT, "INVENT_0822_crypto_tether_DIAG.json"), "w") as fh:
        json.dump(diags, fh, indent=1)
    hdr = f"{'spread':34s} {'n':>5s} {'HL':>8s} {'sd_bp':>8s} {'p01':>8s} {'p99':>8s} {'H':>6s} {'ADF':>7s} {'rho1':>7s} gate"
    print(hdr); print("-" * len(hdr))
    for d in diags:
        if "half_life" not in d:
            print(f"{d['name']:34s} {d['n']:5d}  (too short)"); continue
        print(f"{d['name']:34s} {d['n']:5d} {d['half_life']:8.1f} {d['sd_bp']:8.1f} "
              f"{d['p01_bp']:8.1f} {d['p99_bp']:8.1f} {d['hurst']:6.3f} {d['adf_t']:7.2f} "
              f"{d['rho1_dspread']:7.3f} {'PASS' if d['rho1_gate'] else 'fail'}")


if __name__ == "__main__":
    main()
