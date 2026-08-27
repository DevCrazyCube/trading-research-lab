#!/usr/bin/env python3
"""INVENT_0822C -- build a per-leg DAILY net-return panel for the sized basket legs.

Legs (frozen specs, no re-fit):
  T3        daily overnight XS reversal      (cached: research/data/invent_r3/t3_daily.json)
  T7D1      ex-div cum-close -> ex-open      (cached: research/data/invent_r3/t7d1_daily.json)
  CEF       T12 S2 discount-level H=4 weekly (cached: research/data/invent_r3/t12_all.json)
  ETFRV     ETF-sibling 15:45 z-fade -> MOC  (rebuilt from research/data/rv_cache 5-min bars)
  DUALCLASS dual-class z-fade, daily MTM     (rebuilt from research/data/t28_dualclass_cache)
  ORB       opening-range breakout -> MOC    (rebuilt from research/data/t17_cache)

Output: research/data/inv0822c_cache/legs_daily.json
  {leg: {"dates": [...], "net": [...], "gross": [...]}}
Every series is a per-SESSION net return on $1 of that leg's own gross book;
non-trading sessions are absent (the overlay layer fills 0.0).
"""
from __future__ import annotations
import json, math, pathlib, statistics as st, sys, datetime as dt
from zoneinfo import ZoneInfo

ROOT = pathlib.Path("/home/anont/meme")
R3 = ROOT / "research/data/invent_r3"
OUT = ROOT / "research/data/inv0822c_cache"
OUT.mkdir(parents=True, exist_ok=True)
ET = ZoneInfo("America/New_York")


# ------------------------------------------------------------------ ETFRV
ETFRV_PAIRS = [("IVV", "SPY"), ("VOO", "SPY"), ("QQQM", "QQQ"), ("VTWO", "IWM"), ("IJH", "MDY")]
ETFRV_HS = {"SPY": 0.13, "IVV": 0.35, "VOO": 0.35, "QQQ": 0.15, "QQQM": 0.5,
            "IWM": 0.2, "VTWO": 0.5, "MDY": 0.4, "IJH": 0.4}
SEC31 = 0.278


def etfrv_prices(sym):
    import numpy as np
    z = np.load(ROOT / "research/data/rv_cache" / f"{sym}.npz")
    t = z["t"].astype("int64"); o = z["o"].astype(float); c = z["c"].astype(float)
    px1545, pxclose = {}, {}
    for i in range(len(t)):
        d = dt.datetime.fromtimestamp(int(t[i]), ET)
        key = d.strftime("%Y-%m-%d")
        hm = d.hour * 60 + d.minute
        if hm == 15 * 60 + 45:
            px1545[key] = o[i]
        if 15 * 60 + 30 <= hm <= 16 * 60:
            pxclose[key] = c[i]      # last bar at/after 15:30 -> session close
    return px1545, pxclose


def build_etfrv():
    P = {}
    for s in sorted({x for p in ETFRV_PAIRS for x in p}):
        P[s] = etfrv_prices(s)
        print("  etfrv prices", s, len(P[s][0]), file=sys.stderr)
    per_day_net, per_day_gross = {}, {}
    rho_num, rho_den = [], []
    for a, b in ETFRV_PAIRS:
        p45a, pca = P[a]; p45b, pcb = P[b]
        days = sorted(set(p45a) & set(p45b) & set(pca) & set(pcb))
        s = [math.log(p45a[d] / p45b[d]) for d in days]
        ds = [s[i] - s[i - 1] for i in range(1, len(s))]
        if len(ds) > 60:
            m = st.fmean(ds)
            num = sum((ds[i] - m) * (ds[i - 1] - m) for i in range(1, len(ds)))
            den = sum((x - m) ** 2 for x in ds)
            rho_num.append((f"{a}/{b}", num / den if den else float("nan")))
        cost = (ETFRV_HS[a] + ETFRV_HS[b] + 2 * SEC31) * 1e-4
        for i in range(60, len(days)):
            win = s[i - 60:i]
            mu = st.fmean(win); sd = st.pstdev(win)
            if sd <= 0:
                continue
            z = (s[i] - mu) / sd
            if abs(z) < 1.5:
                continue
            sgn = -1.0 if z > 0 else 1.0
            d = days[i]
            ra = pca[d] / p45a[d] - 1.0
            rb = pcb[d] / p45b[d] - 1.0
            g = sgn * (ra - rb)
            per_day_gross.setdefault(d, []).append(g)
            per_day_net.setdefault(d, []).append(g - cost)
    ds_ = sorted(per_day_net)
    return ({"dates": ds_,
             "net": [st.fmean(per_day_net[d]) for d in ds_],
             "gross": [st.fmean(per_day_gross[d]) for d in ds_]},
            dict(rho_num))


# -------------------------------------------------------------- DUALCLASS
DC_PAIRS = [("GOOGL", "GOOG"), ("BRK.A", "BRK.B"), ("FOXA", "FOX"), ("NWSA", "NWS"),
            ("UAA", "UA"), ("HEI", "HEI.A"), ("CWEN", "CWEN.A"), ("LGF.A", "LGF.B"),
            ("CENTA", "CENT"), ("LBRDA", "LBRDK"), ("LSXMA", "LSXMK"), ("FWONA", "FWONK"),
            ("Z", "ZG"), ("DISCA", "DISCK"), ("PBR", "PBR.A"), ("LILA", "LILAK")]
DC_HS = {"GOOGL": .42, "GOOG": .52, "BRK.A": 4.02, "BRK.B": 1.13, "FOXA": 1.54, "FOX": 1.73,
         "NWSA": 1.93, "NWS": 1.83, "UAA": 6.98, "UA": 7.71, "HEI": 4.84, "HEI.A": 6.76,
         "CWEN": 2.33, "CWEN.A": 3.62, "LGF.A": 5.58, "LGF.B": 5.98, "CENTA": 6.69,
         "CENT": 9.66, "LBRDA": 5.98, "LBRDK": 3.1, "LSXMA": 1.89, "LSXMK": 1.66,
         "FWONA": 8.42, "FWONK": 3.03, "Z": 1.51, "ZG": 3.37, "PBR": 3.44, "PBR.A": 3.78,
         "LILA": 6.34, "LILAK": 6.33}
DC_BORROW = 0.0033


def build_dualclass():
    sys.path.insert(0, str(ROOT))
    from scripts.t28_dualclass import dc_test as dc
    day_net, day_gross, rho = {}, {}, {}
    for a, b in DC_PAIRS:
        rows = dc.build((a, b), "2016-01-04", "2026-08-18")
        if len(rows) < 300:
            print("  dc skip", a, b, len(rows), file=sys.stderr); continue
        s = [r["s"] for r in rows]
        dsp = [s[i] - s[i - 1] for i in range(1, len(s))]
        m = st.fmean(dsp)
        num = sum((dsp[i] - m) * (dsp[i - 1] - m) for i in range(1, len(dsp)))
        den = sum((x - m) ** 2 for x in dsp)
        rho[f"{a}/{b}"] = num / den if den else float("nan")
        hs = (DC_HS.get(a, 5.0) + DC_HS.get(b, 5.0)) * 1e-4
        entry_cost = hs + SEC31 * 1e-4          # crossing in + the short sale fee
        exit_cost = hs + SEC31 * 1e-4
        pos = None; hist = []
        for i, r in enumerate(rows):
            if i > 0 and abs(r["s"] - rows[i - 1]["s"]) > 0.15:
                hist = []; pos = None
            if pos is not None:
                sgn = pos["sgn"]
                ra = r["pa"] / rows[i - 1]["pa"] - 1.0
                rb = r["pb"] / rows[i - 1]["pb"] - 1.0
                g = sgn * (ra - rb)
                c = DC_BORROW / 252.0
                day_gross.setdefault(r["d"], []).append(g)
                day_net.setdefault(r["d"], []).append(g - c)
                z = None
                if len(hist) >= 250:
                    mu = st.fmean(hist[-250:]); sd = st.pstdev(hist[-250:])
                    z = (r["s"] - mu) / sd if sd > 0 else 0.0
                held = i - pos["i"]
                if (z is not None and abs(z) <= 0.5) or held >= 20 or i == len(rows) - 1:
                    day_net[r["d"]][-1] -= exit_cost
                    pos = None
            if pos is None and len(hist) >= 250:
                mu = st.fmean(hist[-250:]); sd = st.pstdev(hist[-250:])
                if sd > 0:
                    z = (r["s"] - mu) / sd
                    if abs(z) >= 2.0 and r["dv"] >= 1e6 and min(r["px_a"], r["px_b"]) >= 2.0:
                        pos = {"i": i, "sgn": -1 if z > 0 else 1}
                        day_net.setdefault(r["d"], []).append(-entry_cost)
                        day_gross.setdefault(r["d"], []).append(0.0)
            hist.append(r["s"])
    ds_ = sorted(day_net)
    # book return = SUM over pairs / 16 (fixed slot count: a $1 book split 16 ways)
    n = len(DC_PAIRS)
    return ({"dates": ds_,
             "net": [sum(day_net[d]) / n for d in ds_],
             "gross": [sum(day_gross[d]) / n for d in ds_]}, rho)


# -------------------------------------------------------------------- ORB
ORB_COST = 0.000902 + 0.000028


def build_orb():
    T17 = ROOT / "research/data/t17_cache"
    sel = json.load(open(T17 / "selection.json"))
    dates, net, gross = [], [], []
    for d in sorted(k for k, v in sel.items() if v):
        pth = T17 / "paths" / f"{d}.json"
        if not pth.exists():
            continue
        try:
            paths = json.load(open(pth))
        except Exception:
            continue
        rs_n, rs_g = [], []
        for row in sel[d]:
            _, sym, side, orh, orl, _ = row
            bars = paths.get(sym)
            if not bars:
                continue
            lvl = (orh if side == "long" else orl) / 1e6
            if lvl <= 0:
                continue
            fired = False
            for b in bars:
                if side == "long" and b[2] >= lvl:
                    fired = True; break
                if side == "short" and b[3] <= lvl:
                    fired = True; break
            if not fired:
                continue
            close = bars[-1][4]
            g = (close - lvl) / lvl * (1 if side == "long" else -1)
            rs_g.append(g); rs_n.append(g - ORB_COST)
        if rs_n:
            dates.append(d); net.append(st.fmean(rs_n)); gross.append(st.fmean(rs_g))
    return {"dates": dates, "net": net, "gross": gross}


def main():
    legs, diag = {}, {}
    t3 = json.load(open(R3 / "t3_daily.json"))
    legs["T3"] = {"dates": t3["dates"], "net": t3["net"], "gross": t3["gross"]}
    t7 = json.load(open(R3 / "t7d1_daily.json"))
    legs["T7D1"] = {"dates": t7["dates"], "net": t7["net"], "gross": t7["gross"]}
    cef = json.load(open(R3 / "t12_all.json"))["S2_LNone_H4"]
    legs["CEF"] = {"dates": cef["dates"], "net": cef["net"],
                   "gross": cef.get("gross", cef["net"]), "weekly": True}
    print("ETFRV...", file=sys.stderr)
    legs["ETFRV"], diag["rho1_etfrv"] = build_etfrv()
    print("DUALCLASS...", file=sys.stderr)
    legs["DUALCLASS"], diag["rho1_dualclass"] = build_dualclass()
    print("ORB...", file=sys.stderr)
    legs["ORB"] = build_orb()
    for k, v in legs.items():
        print(k, len(v["dates"]), v["dates"][0], v["dates"][-1],
              "mean_bp=%.3f" % (st.fmean(v["net"]) * 1e4), file=sys.stderr)
    (OUT / "legs_daily.json").write_text(json.dumps({"legs": legs, "diag": diag}))
    print("wrote", OUT / "legs_daily.json", file=sys.stderr)


if __name__ == "__main__":
    main()
