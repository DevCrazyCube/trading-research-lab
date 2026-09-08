#!/usr/bin/env python3
"""INVENT_0822B auction theme -- diagnostics for whatever the sweep ranked top.

For the cells named on the command line (default: top 6 by design |t| in the sweep JSON):
  * per-year gross Sharpe (design AND held-out)
  * INTERVAL DECOMPOSITION -- is the gross return an instant at one print, or an interval?
    the MOO->MOC day is split into  O->P29 | P29->P49 | P49->P59 | P59->C
    the MOC->MOO night is split into C->O only (no free pre-open reference exists)
  * ONE-SESSION-LATER re-entry (the same leg, one trading day later) -- a signal whose alpha
    is entirely gone at +1 session is a same-print artefact, not an interval edge
  * decile monotonicity of the outcome in the signal
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "research" / "data" / "auc0822_cache"
OUTDIR = ROOT / "research" / "trading_bot"
sys.path.insert(0, str(ROOT))
from scripts.auc0822_engine import (  # noqa: E402
    DESIGN_END, HELD_START, MIN_NAMES, MIN_PRICE, MAX_GAP, MAX_DAY,
    lag, roll_mean, roll_std, stats, zscore_rows,
)


def build():
    z = np.load(CACHE / "panel.npz", allow_pickle=False)
    dates = np.array([str(d) for d in z["dates"]])
    p29, p49, p59, po, pc = z["p29"], z["p49"], z["p59"], z["po"], z["pc"]
    ca, in_uni = z["ca"], z["in_uni"]
    with np.errstate(divide="ignore", invalid="ignore"):
        L = {k: np.log(v) for k, v in
             dict(l29=p29, l49=p49, l59=p59, lo=po, lc=pc).items()}
    for a in L.values():
        a[~np.isfinite(a)] = np.nan
    l29, l49, l59, lo, lc = L["l29"], L["l49"], L["l59"], L["lo"], L["lc"]
    base = in_uni & (p59 >= MIN_PRICE) & (~ca) & np.isfinite(l59) & np.isfinite(lc) & np.isfinite(lo)
    d = lc - l59
    e = l59 - l49
    f = l49 - l29
    x = lc - lo
    q = lo - lag(lc, 1)
    u = lo - lag(l59, 1)
    d49 = lc - l49
    ptc = (lc - lag(lc, 1)) - (l59 - lag(l59, 1))
    p49c = l49 - lag(lc, 1)
    guard = (np.abs(np.nan_to_num(q, nan=0.0)) <= MAX_GAP) & \
            (np.abs(np.nan_to_num(x, nan=0.0)) <= MAX_DAY)
    base = base & guard
    d5 = roll_mean(np.where(base, d, np.nan), 5)
    d20 = roll_mean(np.where(base, d, np.nan), 20)
    dsd = roll_std(np.where(base, d, np.nan), 60)
    preds = {
        "S01_d": d, "S02_e": e, "S03_f": f, "S04_e_minus_f": e - f,
        "S05_d_dev5": d - d5, "S06_d_dev20": d - d20,
        "S07_d_volnorm": d / np.where(dsd > 0, dsd, np.nan), "S08_d49": d49,
        "S09_q": q, "S10_u": u, "S11_q_minus_dlag": q - lag(d, 1), "S12_x": x,
        "S13_d_plus_dlag": d + lag(d, 1), "S14_d_shrunk": np.sign(d) * np.sqrt(np.abs(d)),
        "S15_d_change": d - lag(d, 1), "S16_e_plus_d": e + d, "S17_d_mean5": d5,
        "S18_print_vs_cont": ptc,
        "M01_f": f, "M02_dlag": lag(d, 1), "M03_q": q, "M04_q_minus_dlag": q - lag(d, 1),
        "M05_u": u, "M06_d_mean5_lag": lag(d5, 1), "M07_x_lag": lag(x, 1),
        "M08_p49_vs_close": p49c, "M09_dlag_plus_q": lag(d, 1) + q,
    }
    b1 = base & lag(base, -1)
    b2 = base & lag(base, -2) & lag(base, -1)
    legs = {
        # outcome -> (total, [(name, component)], mask, one-session-later total)
        "DAY_t1": (lag(lc - lo, -1),
                   [("O_to_1529", lag(l29 - lo, -1)), ("1529_to_1549", lag(l49 - l29, -1)),
                    ("1549_to_1559", lag(l59 - l49, -1)), ("1559_to_C", lag(lc - l59, -1))],
                   b1, lag(lc - lo, -2)),
        "OO_t1": (lag(lo, -2) - lag(lo, -1),
                  [("O_to_C", lag(lc - lo, -1)), ("C_to_O", lag(lo, -2) - lag(lc, -1))],
                  b2, lag(lo, -3) - lag(lo, -2)),
        "ON_t": (lag(lo, -1) - lc, [("C_to_O", lag(lo, -1) - lc)], b1,
                 lag(lo, -2) - lag(lc, -1)),
        "CC_t": (lag(lc, -1) - lc,
                 [("C_to_O", lag(lo, -1) - lc), ("O_to_C", lag(lc - lo, -1))], b1,
                 lag(lc, -2) - lag(lc, -1)),
    }
    return dates, base, preds, legs


def run_cell(sig, R, rmask, dates, sel):
    m = rmask & np.isfinite(sig)
    ok = m.sum(axis=1) >= MIN_NAMES
    W = zscore_rows(sig, m & ok[:, None])
    Rz = np.nan_to_num(np.where(rmask, R, np.nan), nan=0.0)
    r = np.where(ok, (W * Rz).sum(axis=1), np.nan)
    return stats(np.where(sel, r, np.nan)), r, W, Rz, ok


def deciles(sig, R, rmask, sel, nb=10):
    out = []
    m = rmask & np.isfinite(sig) & np.isfinite(R) & sel[:, None]
    s = np.where(m, sig, np.nan)
    rr = np.where(m, R, np.nan)
    ranks = np.argsort(np.argsort(np.where(np.isfinite(s), s, np.inf), axis=1), axis=1).astype(float)
    n = np.isfinite(s).sum(axis=1)
    frac = np.where(n[:, None] > 0, ranks / np.maximum(n[:, None] - 1, 1), np.nan)
    for b in range(nb):
        sel_b = np.isfinite(s) & (frac >= b / nb) & (frac < (b + 1) / nb + (1e-9 if b == nb - 1 else 0))
        vals = rr[sel_b]
        vals = vals[np.isfinite(vals)]
        out.append(float(vals.mean() * 1e4) if vals.size else float("nan"))
    return out


def main():
    sweep = json.loads((OUTDIR / "INVENT_0822B_auction.json").read_text())
    cells = sys.argv[1:]
    if not cells:
        rank = sorted(sweep["results"].values(),
                      key=lambda r: -abs(r["design"]["t"] if r["design"]["t"] == r["design"]["t"] else 0))
        cells = [r["formula"] for r in rank[:6]]
    dates, base, preds, legs = build()
    des = dates <= DESIGN_END
    hel = dates >= HELD_START
    years = np.array([dd[:4] for dd in dates])

    out = {}
    for cell in cells:
        pname, oname = cell.split("|")
        sig = preds[pname]
        total, comps, rmask, later = legs[oname]
        st_d, r, W, Rz, ok = run_cell(sig, total, rmask, dates, des)
        st_h, _, _, _, _ = run_cell(sig, total, rmask, dates, hel)
        row = {"design": st_d, "held": st_h, "components": {}, "per_year": {}, "deciles": {}}
        for cname, carr in comps:
            sd, _, _, _, _ = run_cell(sig, np.where(rmask, carr, np.nan), rmask, dates, des)
            sh, _, _, _, _ = run_cell(sig, np.where(rmask, carr, np.nan), rmask, dates, hel)
            row["components"][cname] = {"design_bp": sd["mean_bp"], "design_t": sd["t"],
                                        "held_bp": sh["mean_bp"], "held_t": sh["t"]}
        sl_d, _, _, _, _ = run_cell(sig, np.where(rmask, later, np.nan), rmask, dates, des)
        sl_h, _, _, _, _ = run_cell(sig, np.where(rmask, later, np.nan), rmask, dates, hel)
        row["one_session_later"] = {"design": sl_d, "held": sl_h}
        for y in sorted(set(years.tolist())):
            sy = years == y
            row["per_year"][y] = stats(np.where(sy, r, np.nan))["sharpe"]
        row["deciles"]["design_bp"] = deciles(sig, total, rmask, des)
        row["deciles"]["held_bp"] = deciles(sig, total, rmask, hel)
        out[cell] = row
        print(f"\n=== {cell} ===")
        print(f"  design SR {st_d['sharpe']:+.2f} t {st_d['t']:+.2f} | held SR {st_h['sharpe']:+.2f} t {st_h['t']:+.2f}")
        for cname, v in row["components"].items():
            print(f"   comp {cname:14s} des {v['design_bp']:+7.3f}bp t{v['design_t']:+6.2f}"
                  f"  held {v['held_bp']:+7.3f}bp t{v['held_t']:+6.2f}")
        print(f"   +1 session: design t {sl_d['t']:+.2f}  held t {sl_h['t']:+.2f}")
        print("   design deciles bp: " + " ".join(f"{v:+.2f}" for v in row["deciles"]["design_bp"]))
        print("   held   deciles bp: " + " ".join(f"{v:+.2f}" for v in row["deciles"]["held_bp"]))

    (OUTDIR / "INVENT_0822B_auction_DIAG.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
