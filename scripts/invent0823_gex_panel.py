#!/usr/bin/env python3
"""INVENT-0823 gamma panel builder.

Turns the per-expiry option-volume cache into a (name, day) feature panel.

For each underlying u and trading day t:
  * front monthly E1 (first monthly expiry > t) and next monthly E2
  * per-strike cumulative traded volume through the close of t, calls and puts
  * ATM implied vol backed out from the nearest-to-money call/put closes on t
  * Black-Scholes gamma / charm / vanna at that flat IV
  * net dealer GEX (convention: dealers long calls, short puts) and the derived
    pin strike, gamma-flip level, walls, OI skew.

Writes research/data/inv0823_gex/panel.json.gz
"""
import gzip
import json
import math
import os
import sys
from datetime import date, timedelta

ROOT = "/home/anont/meme"
OUT = os.path.join(ROOT, "research/data/inv0823_gex")
STOCKD = os.path.join(OUT, "_stock")
PANEL = os.path.join(OUT, "panel.json.gz")

SQ2PI = math.sqrt(2.0 * math.pi)


def npdf(x):
    return math.exp(-0.5 * x * x) / SQ2PI


def ncdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def bs_price(S, K, T, sig, cp, r=0.04):
    if T <= 0 or sig <= 0:
        iv = max(0.0, (S - K) if cp == "C" else (K - S))
        return iv
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    df = math.exp(-r * T)
    if cp == "C":
        return S * ncdf(d1) - K * df * ncdf(d2)
    return K * df * ncdf(-d2) - S * ncdf(-d1)


def implied_vol(px, S, K, T, cp, r=0.04):
    if T <= 0 or px <= 0:
        return None
    lo, hi = 0.01, 4.0
    if bs_price(S, K, T, hi, cp, r) < px:
        return None
    if bs_price(S, K, T, lo, cp, r) > px:
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, mid, cp, r) < px:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def greeks(S, K, T, sig, cp, r=0.04):
    """returns (gamma, charm, vanna) per contract per 1 share."""
    if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
        return 0.0, 0.0, 0.0
    st = sig * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / st
    d2 = d1 - st
    g = npdf(d1) / (S * st)
    # charm = d(delta)/d(t)  (per year; sign per Haug)
    charm = -npdf(d1) * (2 * r * T - d2 * st) / (2 * T * st)
    if cp == "P":
        charm = charm  # same functional form up to the carry term (r=q=0 carry)
    vanna = -npdf(d1) * d2 / sig
    return g, charm, vanna


def third_fridays(a, b):
    out = []
    y, m = a.year, a.month
    while date(y, m, 1) <= b:
        d = date(y, m, 15)
        while d.weekday() != 4:
            d += timedelta(days=1)
        if a <= d <= b:
            out.append(d.isoformat())
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def main():
    unds = sorted(d for d in os.listdir(OUT)
                  if os.path.isdir(os.path.join(OUT, d)) and not d.startswith("_"))
    exps = third_fridays(date(2024, 2, 1), date(2026, 8, 21))
    panel = {}
    for und in unds:
        sp = os.path.join(STOCKD, und + ".json")
        if not os.path.exists(sp):
            continue
        sb = json.load(open(sp))
        raw = {b["t"][:10]: b for b in sb["raw"]}
        adj = {b["t"][:10]: b for b in sb["adj"]}
        days = sorted(adj)
        # dollar ADV (20d) from adjusted bars
        advd = {}
        vals = []
        for i, d in enumerate(days):
            b = adj[d]
            vals.append(b["c"] * b["v"])
            if i >= 20:
                vals.pop(0)
            advd[d] = sum(vals) / len(vals)

        # load per-expiry ladders  ->  cum[exp][day][K] = (callvol, putvol, cclose, pclose)
        expdata = {}
        for e in exps:
            p = os.path.join(OUT, und, e + ".json")
            if not os.path.exists(p):
                continue
            rec = json.load(open(p))
            per = {}   # day -> {K: [cv, pv, cclose, pclose]}
            for sym, rows in rec["bars"].items():
                cp = sym[-9]
                K = int(sym[-8:]) / 1000.0
                for r in rows:
                    d = r[0]
                    slot = per.setdefault(d, {}).setdefault(K, [0.0, 0.0, None, None])
                    if cp == "C":
                        slot[0] += r[1]
                        slot[2] = r[2]
                    else:
                        slot[1] += r[1]
                        slot[3] = r[2]
            expdata[e] = per

        rows = []
        for i, d in enumerate(days):
            if d < "2024-02-01" or d > "2026-08-21":
                continue
            nxt = [e for e in exps if e > d]
            if len(nxt) < 2:
                continue
            E1, E2 = nxt[0], nxt[1]
            S = raw[d]["c"]
            if S <= 0:
                continue
            legs = []
            for E in (E1, E2):
                per = expdata.get(E)
                if not per:
                    continue
                # cumulative volume through close of d
                cum = {}
                closes = {}
                for dd in sorted(per):
                    if dd > d:
                        break
                    for K, v in per[dd].items():
                        s = cum.setdefault(K, [0.0, 0.0])
                        s[0] += v[0]
                        s[1] += v[1]
                        if dd == d:
                            closes[K] = (v[2], v[3])
                if not cum:
                    continue
                T = (date.fromisoformat(E) - date.fromisoformat(d)).days / 365.0
                if T <= 0:
                    continue
                # ATM IV from the nearest-to-money contract that traded today
                iv = None
                for K in sorted(closes, key=lambda k: abs(k - S)):
                    cpx, ppx = closes[K]
                    cands = []
                    if cpx:
                        v = implied_vol(cpx, S, K, T, "C")
                        if v:
                            cands.append(v)
                    if ppx:
                        v = implied_vol(ppx, S, K, T, "P")
                        if v:
                            cands.append(v)
                    if cands:
                        iv = sum(cands) / len(cands)
                        break
                if not iv or iv <= 0:
                    continue
                legs.append((E, T, iv, cum))
            if not legs:
                continue

            # ---- aggregate gamma / charm / vanna ----
            cg = pg = 0.0        # call / put gamma-$ per 1% move
            ccharm = pcharm = 0.0
            cvan = pvan = 0.0
            cvol = pvol = 0.0
            gamma_by_K = {}
            put_surge_num = call_surge_num = 0.0
            otm_call_g = otm_put_g = 0.0
            for (E, T, iv, cum) in legs:
                for K, (cv, pv) in cum.items():
                    g, ch, va = greeks(S, K, T, iv, "C")
                    dg = g * 100.0 * S * S * 0.01     # $ gamma per 1% move, per contract
                    cg += dg * cv
                    pg += dg * pv
                    ccharm += ch * cv * 100.0
                    pcharm += ch * pv * 100.0
                    cvan += va * cv * 100.0
                    pvan += va * pv * 100.0
                    cvol += cv
                    pvol += pv
                    tot = gamma_by_K.get(K, [0.0, 0.0])
                    tot[0] += dg * cv
                    tot[1] += dg * pv
                    gamma_by_K[K] = tot
                    if 0.90 * S <= K <= 0.97 * S:
                        put_surge_num += pv
                    if 1.03 * S <= K <= 1.10 * S:
                        call_surge_num += cv
                    if K > S:
                        otm_call_g += dg * cv
                    if K < S:
                        otm_put_g += dg * pv
            if cg + pg <= 0:
                continue
            net_gex = cg - pg
            gross_gex = cg + pg

            # pin strike = strike carrying the most total gamma-$
            Kpin = max(gamma_by_K, key=lambda k: gamma_by_K[k][0] + gamma_by_K[k][1])
            # walls
            calls_above = [(k, gamma_by_K[k][0]) for k in gamma_by_K if k > S]
            puts_below = [(k, gamma_by_K[k][1]) for k in gamma_by_K if k < S]
            Kcw = max(calls_above, key=lambda x: x[1])[0] if calls_above else None
            Kpw = max(puts_below, key=lambda x: x[1])[0] if puts_below else None

            # gamma-flip: re-price the net-gamma profile at hypothetical spots
            flip = None
            grid = [S * (1 + z / 100.0) for z in range(-10, 11)]
            near = [(T, iv, [(K, cv - pv) for K, (cv, pv) in cum.items()
                             if 0.70 * S < K < 1.30 * S])
                    for (E, T, iv, cum) in legs]
            prof = []
            for Sx in grid:
                v = 0.0
                for (T, iv, ks) in near:
                    st = iv * math.sqrt(T)
                    c = 100.0 * Sx * 0.01 / st
                    drift = (0.04 + 0.5 * iv * iv) * T
                    for K, nq in ks:
                        d1 = (math.log(Sx / K) + drift) / st
                        v += npdf(d1) * c * nq
                prof.append(v)
            for j in range(1, len(grid)):
                if prof[j - 1] == 0:
                    continue
                if (prof[j - 1] < 0) != (prof[j] < 0):
                    w = abs(prof[j - 1]) / (abs(prof[j - 1]) + abs(prof[j]) + 1e-12)
                    flip = grid[j - 1] + w * (grid[j] - grid[j - 1])
                    break

            b = adj[d]
            rows.append({
                "d": d, "S": S, "adj_c": b["c"], "adj_o": b["o"],
                "adj_h": b["h"], "adj_l": b["l"], "adv": advd[d],
                "net_gex": net_gex, "gross_gex": gross_gex,
                "cg": cg, "pg": pg, "cvol": cvol, "pvol": pvol,
                "charm": ccharm - pcharm, "vanna": cvan - pvan,
                "Kpin": Kpin, "Kcw": Kcw, "Kpw": Kpw, "flip": flip,
                "otm_call_g": otm_call_g, "otm_put_g": otm_put_g,
                "put_surge_raw": put_surge_num, "call_surge_raw": call_surge_num,
                "iv1": legs[0][2], "dte1": round(legs[0][1] * 365),
                "front_gex": None, "E1": legs[0][0],
            })
            # front-monthly-only net gex (leg 0)
            E, T, iv, cum = legs[0]
            fg = 0.0
            for K, (cv, pv) in cum.items():
                g, _, _ = greeks(S, K, T, iv, "C")
                fg += g * 100.0 * S * S * 0.01 * (cv - pv)
            rows[-1]["front_gex"] = fg
        panel[und] = rows
        print(f"panel {und}: {len(rows)} rows", flush=True)
    with gzip.open(PANEL, "wt") as f:
        json.dump(panel, f)
    print("WROTE", PANEL, flush=True)


if __name__ == "__main__":
    main()
