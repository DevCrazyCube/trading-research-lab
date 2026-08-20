#!/usr/bin/env python3
"""Sign-stability surface. Run AFTER the held-out read, on the held-out window, over a
parameter grid around whichever formulas survived. NOTHING is selected from this -- it only
answers 'is the sign an isolated cell or a plateau?'"""
import json, pathlib, sys
import numpy as np
sys.path.insert(0, "/home/anont/meme")
from scripts.t29_crosslist.xl_run import WINDOWS, OUT
from scripts.t29_crosslist.xl_panel import build_panel, half_spreads, CACHE
from scripts.t29_crosslist.xl_engine import xsec
from scripts.t29_crosslist.xl_formulas import FULL, PART, NONE

BLOCS = {"CA": ("CA",), "FULL": FULL, "PART": PART, "NONE": NONE,
         "ALL": FULL + PART + NONE}


def main(which):
    lo, hi = WINDOWS[which]
    names, census, us_dates, us_raw, us_adj = build_panel()
    dates = [d for d in us_dates if lo <= d <= hi]
    W = {}
    for u, nm in names.items():
        keep = [i for i, d in enumerate(nm["d"]) if lo <= d <= hi]
        if len(keep) < 250:
            continue
        W[u] = {k: (np.asarray([nm[k][i] for i in keep]) if k != "d"
                    else [nm["d"][i] for i in keep])
                for k in ("d", "s", "px_adj", "dv", "px_raw", "stale")}
        W[u]["region"] = nm["region"]
    quotes = json.loads((CACHE / "quotes.json").read_text())
    hs = half_spreads(us_raw, sorted(W), lo, hi, quotes=quotes)
    ef = json.loads((CACHE / "etb_flags.json").read_text())["flags"]
    bs = {}
    for k, v in ef.items():
        bs[k] = ("unknown" if not v or v.get("status") != "active"
                 else "etb" if v.get("shortable") and v.get("easy_to_borrow")
                 else "unknown" if v.get("shortable") else "htb")
    rows = []
    for bname, regs in BLOCS.items():
        syms = [u for u, v in W.items() if v["region"] in regs]
        if len(syms) < 6:
            continue
        for L in (20, 60, 120, 250):
            for h in (1, 3, 5, 10, 20):
                for frac in (0.1, 0.2, 0.33):
                    st, _ = xsec(W, syms, dates, hs, bs, mode="z", L=L, h=h, frac=frac,
                                 region_neutral=len(regs) > 1,
                                 label=f"{bname} L={L} h={h} f={frac}")
                    if st.get("n", 0) >= 8:
                        rows.append({"bloc": bname, "L": L, "h": h, "frac": frac,
                                     "n": st["n"], "net_bp": st["net_bp"],
                                     "t": st["t"], "sharpe": st["sharpe"]})
                        print(rows[-1], flush=True)
    p = OUT / f"DEEPMINE_crosslist_GRID_{which.upper()}.json"
    pos = [r for r in rows if (r["sharpe"] or 0) > 0]
    p.write_text(json.dumps({"window": which, "n_cells": len(rows),
                             "frac_positive_sharpe": round(len(pos) / max(len(rows), 1), 3),
                             "cells": rows}, indent=1))
    print("wrote", p, len(rows), "cells", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "holdout")
