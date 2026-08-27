#!/usr/bin/env python3
"""EXO_0822C panel builder — the PUBLISHED-GAP TETHER.

Builds an event table for corporate actions whose expected price change is
PUBLISHED BY A THIRD PARTY (Alpaca corporate-actions feed, sourced from the
transfer agents / exchanges), against RAW (unadjusted) prints from the
auc0822 panel.

The object of interest:

    g   = ln( P_open(ex) / P_close(cum) )                actual overnight gap
    a   = ln( 1 - D/P_close(cum) )   (cash dividend)     PUBLISHED expected gap
        = ln( old_rate / new_rate )  (split)
    eps = g - a                                          residual

`a` is not a fitted statistic. It is an arithmetic consequence of a number a
third party publishes before the event. That is the lesson-4 condition.

Outputs research/data/exo0822c/events.npz
"""
from __future__ import annotations

import gzip
import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
PANEL = ROOT / "research/data/auc0822_cache/panel.npz"
CA = ROOT / "research/data/t7_cache/corporate_actions_all.json.gz"
OUT = ROOT / "research/data/exo0822c"

MIN_PRICE = 5.0          # raw, point-in-time legal (panel is unadjusted)
MIN_ADV = 1_000_000.0    # $1M ADV floor


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    z = np.load(PANEL, allow_pickle=True)
    dates = z["dates"]
    syms = z["syms"]
    po = z["po"].astype(np.float64)
    pc = z["pc"].astype(np.float64)
    adv = z["advusd"].astype(np.float64)
    inu = z["in_uni"]
    caf = z["ca"]
    cacov = z["ca_covered"]
    nd, ns = po.shape
    di = {d: k for k, d in enumerate(dates)}
    sidx = {s: k for k, s in enumerate(syms)}

    ca = json.load(gzip.open(CA))

    # ------------------------------------------------------------------
    # DATA INTEGRITY: research/data/t7_cache/corporate_actions_all.json.gz
    # contains DUPLICATED records — the same `id` appears twice for 26,038 of
    # 385,845 cash dividends, 37 of 980 forward splits and 207 of 5,637 reverse
    # splits (an overlapping paging window in whatever wrote the cache).
    # Summing the raw records over-states the published dividend by ~2x on 8%
    # of ex-dates and SQUARES the split factor, which manufactures a large fake
    # ex-day residual. Deduplicate on identity first: by `id`, and then by
    # (symbol, ex-date, rate) which also removes the 609 same-rate/different-id
    # re-issues. Distinct rates on one ex-date (e.g. regular + special) are kept
    # and summed, which is correct.
    # ------------------------------------------------------------------
    def dedupe(rows, keyfn):
        seen_id, seen_k, out = set(), set(), []
        for e in rows:
            if e.get("id") in seen_id:
                continue
            k = keyfn(e)
            if k in seen_k:
                continue
            seen_id.add(e.get("id"))
            seen_k.add(k)
            out.append(e)
        return out

    n0 = {k: len(v) for k, v in ca.items()}
    ca["cash_dividends"] = dedupe(
        ca["cash_dividends"],
        lambda e: (e["symbol"], e["ex_date"], round(float(e.get("rate") or 0), 8)))
    for key in ("forward_splits", "reverse_splits"):
        ca[key] = dedupe(ca[key], lambda e: (e["symbol"], e.get("ex_date"),
                                             e["old_rate"], e["new_rate"]))
    print("dedupe:", {k: (n0[k], len(ca[k])) for k in
                      ("cash_dividends", "forward_splits", "reverse_splits")})

    # ---- published-rate matrices -------------------------------------------
    div = np.zeros((nd, ns))          # cash dividend per (old) share, ex-date
    divsp = np.zeros((nd, ns), bool)  # special flag
    ndiv = np.zeros((nd, ns), np.int16)
    for e in ca["cash_dividends"]:
        s, d = e["symbol"], e["ex_date"]
        if s in sidx and d in di and e.get("rate"):
            div[di[d], sidx[s]] += float(e["rate"])
            ndiv[di[d], sidx[s]] += 1
            if e.get("special"):
                divsp[di[d], sidx[s]] = True

    sfac = np.ones((nd, ns))          # multiply ex-date price by this to undo split
    stype = np.zeros((nd, ns), np.int8)  # 1 fwd, 2 rev
    for key, code in (("forward_splits", 1), ("reverse_splits", 2)):
        for e in ca[key]:
            s, d = e["symbol"], e.get("ex_date")
            if s in sidx and d in di:
                o, n = float(e["old_rate"]), float(e["new_rate"])
                if o > 0 and n > 0:
                    sfac[di[d], sidx[s]] *= n / o
                    stype[di[d], sidx[s]] = code

    other = np.zeros((nd, ns), bool)  # actions whose value is NOT published
    for key in ("spin_offs", "rights_distributions", "stock_dividends"):
        for e in ca[key]:
            s = e.get("symbol") or e.get("source_symbol")
            d = e.get("ex_date") or e.get("effective_date")
            if s in sidx and d in di:
                other[di[d], sidx[s]] = True

    # ---- clean TOTAL-RETURN open-to-open matrix ----------------------------
    # R[d,i] = ln( (po[d+1,i]*sfac[d+1,i] + div[d+1,i]) / po[d,i] )
    num = po * sfac + div
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.full((nd, ns), np.nan)
        R[:-1] = np.log(num[1:] / po[:-1])
        # close-to-close total return, same convention
        Rcc = np.full((nd, ns), np.nan)
        Rcc[:-1] = np.log((pc[1:] * sfac[1:] + div[1:]) / pc[:-1])
        # overnight (prev close -> open) total return
        RON = np.full((nd, ns), np.nan)
        RON[1:] = np.log(num[1:] / pc[:-1])
        # intraday (open -> close), no action inside the session
        ROC = np.log(pc / po)
    for M in (R, Rcc, RON, ROC):
        M[~np.isfinite(M)] = np.nan
        M[np.abs(M) > 0.9] = np.nan

    base = inu & cacov[None, :] & (pc > MIN_PRICE) & (adv > MIN_ADV)
    clean = base & ~caf & ~other

    def xsmed(M, mask):
        out = np.full(nd, np.nan)
        for d in range(nd):
            v = M[d][mask[d]]
            v = v[np.isfinite(v)]
            if v.size >= 30:
                out[d] = np.median(v)
        return out

    m_on = xsmed(RON, clean)
    m_oc = xsmed(ROC, clean)
    m_oo = xsmed(R, clean)
    m_cc = xsmed(Rcc, clean)

    # ---- event table -------------------------------------------------------
    is_div = (div > 0) & (ndiv > 0)
    is_split = stype > 0
    ev = (is_div | is_split) & base & ~other
    ev[0] = False
    ev[nd - 1] = False
    # a dividend AND a split on the same day: drop (ambiguous ordering)
    ev &= ~(is_div & is_split)
    # need a cum close and an ex open
    ev &= np.isfinite(pc)
    evd, evs = np.where(ev)
    ok = np.isfinite(pc[evd - 1, evs]) & np.isfinite(po[evd, evs])
    evd, evs = evd[ok], evs[ok]

    pcum = pc[evd - 1, evs]
    popen = po[evd, evs]
    y = div[evd, evs] / pcum                      # dividend yield (0 for splits)
    sf = sfac[evd, evs]
    # PUBLISHED expected overnight gap: dividend drop, and the split price change
    # (price multiplies by old/new = 1/sf).
    a = np.log(np.clip(1.0 - y, 1e-6, None)) - np.log(sf)
    g = np.log(popen / pcum)                      # RAW gap, as printed
    eps = g - a
    keep = np.isfinite(eps) & (np.abs(eps) < 0.5) & (y < 0.5)
    evd, evs, y, a, g, eps = evd[keep], evs[keep], y[keep], a[keep], g[keep], eps[keep]
    pcum = pcum[keep]

    n = evd.size
    typ = np.where(div[evd, evs] > 0, np.where(divsp[evd, evs], 3, 0), stype[evd, evs]).astype(np.int8)
    # 0 = ordinary cash dividend, 3 = special cash dividend, 1 = fwd split, 2 = rev split

    eps_h = eps - m_on[evd]
    oc = ROC[evd, evs] - m_oc[evd]                # ex-day open->close, hedged
    advv = adv[evd, evs]
    prc = pcum

    # regular payer: same symbol had a dividend 40..90 trading days earlier
    prev_ex = np.full(n, -1, np.int32)
    bysym: dict[int, list[int]] = {}
    for k in range(n):
        bysym.setdefault(int(evs[k]), []).append(k)
    for s, ks in bysym.items():
        ks.sort(key=lambda k: evd[k])
        for j in range(1, len(ks)):
            prev_ex[ks[j]] = evd[ks[j - 1]]
    gapd = np.where(prev_ex >= 0, evd - prev_ex, -1)
    regular = (gapd >= 40) & (gapd <= 90)

    # prior-window hedged returns (run-up), close-to-close, ending at the cum close
    def back_ret(k):
        out = np.full(n, np.nan)
        for j in range(n):
            d, i = evd[j], evs[j]
            d0 = d - 1 - k
            if d0 < 0:
                continue
            v = Rcc[d0:d - 1, i]
            m = m_cc[d0:d - 1]
            if np.isfinite(v).all() and np.isfinite(m).all():
                out[j] = v.sum() - m.sum()
        return out

    ru5 = back_ret(5)
    ru20 = back_ret(20)

    # PLACEBO: the same symbol's hedged overnight gap on a nearby NON-event date
    pl = np.full(n, np.nan)
    for j in range(n):
        d, i = evd[j], evs[j]
        for back in (5, 6, 7, 4, 8, 9, 10):
            dd = d - back
            if dd < 1:
                continue
            if caf[dd, i] or other[dd, i] or not base[dd, i]:
                continue
            v = RON[dd, i] - m_on[dd]
            if np.isfinite(v):
                pl[j] = v
                break

    # forward hedged open-to-open cumulative returns from the ex-day open
    HS = (1, 2, 5, 10, 20)
    fwd = np.full((len(HS), n), np.nan)
    for hi, h in enumerate(HS):
        for j in range(n):
            d, i = evd[j], evs[j]
            if d + h >= nd:
                continue
            v = R[d:d + h, i]
            m = m_oo[d:d + h]
            if np.isfinite(v).all() and np.isfinite(m).all():
                fwd[hi, j] = v.sum() - m.sum()

    np.savez_compressed(
        OUT / "events.npz",
        dates=dates, syms=syms,
        evd=evd, evs=evs, y=y, a=a, g=g, eps=eps, eps_h=eps_h, oc=oc,
        typ=typ, regular=regular, gapd=gapd, adv=advv, price=prc,
        ru5=ru5, ru20=ru20, fwd=fwd, HS=np.array(HS), pl=pl,
        m_on=m_on, m_oc=m_oc, m_oo=m_oo, m_cc=m_cc,
        RON=RON.astype(np.float32), ROC=ROC.astype(np.float32),
        R=R.astype(np.float32), clean=clean, base=base,
    )
    print("events", n)
    for c, lab in ((0, "ord div"), (3, "special div"), (1, "fwd split"), (2, "rev split")):
        m = typ == c
        print(f"  {lab:12s} n={m.sum():6d}  mean eps_h={np.nanmean(eps_h[m])*1e4:8.2f} bp  "
              f"median y={np.nanmedian(y[m])*1e4:7.1f} bp")
    print("days with >=1 event:", len(np.unique(evd)))


if __name__ == "__main__":
    main()
