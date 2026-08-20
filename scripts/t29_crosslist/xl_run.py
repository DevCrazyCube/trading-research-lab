#!/usr/bin/env python3
import json, math, pathlib, sys, time
import numpy as np
sys.path.insert(0, "/home/anont/meme")
from scripts.t29_crosslist.xl_panel import build_panel, half_spreads, CACHE
from scripts.t29_crosslist.xl_engine import xsec, pair_rv, BORROW_ETB, BORROW_HTB
from scripts.t29_crosslist.xl_formulas import FORMULAS
from scripts.t29_crosslist.xl_universe import US_US_PAIRS

WINDOWS = {"design": ("2016-01-04", "2021-12-31"),
           "holdout": ("2022-01-03", "2026-08-18")}
OUT = pathlib.Path("/home/anont/meme/research/trading_bot")

DLC = [p for p in US_US_PAIRS if p[2].startswith("DLC")]
ADRCLASS = [p for p in US_US_PAIRS if not p[2].startswith("DLC")]
SUBSETS = {"all": US_US_PAIRS, "dlc": DLC, "adrclass": ADRCLASS}


def run(which, extra=False):
    lo, hi = WINDOWS[which]
    names, census, us_dates, us_raw, us_adj = build_panel()
    dates = [d for d in us_dates if lo <= d <= hi]
    # window-local panel slices
    W = {}
    for u, nm in names.items():
        keep = [i for i, d in enumerate(nm["d"]) if lo <= d <= hi]
        if len(keep) < 250:
            continue
        W[u] = {k: (np.asarray([nm[k][i] for i in keep]) if k != "d"
                    else [nm["d"][i] for i in keep]) for k in
                ("d", "s", "px_adj", "dv", "px_raw", "stale")}
        W[u]["region"] = nm["region"]
    qpath = CACHE / "quotes.json"
    quotes = json.loads(qpath.read_text()) if qpath.exists() else {}
    hsdet = {}
    hs = half_spreads(us_raw, sorted(set(W) | {s for p in US_US_PAIRS for s in p[:2]}),
                      lo, hi, quotes=quotes, detail=hsdet)
    eflags = json.loads((CACHE / "etb_flags.json").read_text())["flags"]
    etb = {}
    for k, v in eflags.items():
        if not v or v.get("status") != "active":
            etb[k] = "unknown"          # delisted today; borrow then is unknowable
        elif v.get("shortable") and v.get("easy_to_borrow"):
            etb[k] = "etb"
        elif v.get("shortable"):
            etb[k] = "unknown"          # shortable but not ETB -> priced at the HTB rate
        else:
            etb[k] = "htb"              # live and flagged not-shortable -> excluded

    results = []
    for f in FORMULAS:
        t0 = time.time()
        if f["fam"] == "pair":
            st, _ = pair_rv(us_raw, us_adj, SUBSETS[f["subset"]], lo, hi, hs, etb,
                            L=f["L"], K=f["K"], EXIT=f["EXIT"], MAXHOLD=f["MAXHOLD"],
                            label=f["id"])
        else:
            syms = [u for u, v in W.items() if v["region"] in f["regions"]]
            kw = {k: v for k, v in f.items()
                  if k in ("mode", "L", "L2", "hl", "frac", "h", "zgate", "region_neutral",
                           "weighting", "entry_lag", "etb_only")}
            st, _ = xsec(W, syms, dates, hs, etb, label=f["id"], **kw)
            st["universe_n"] = len(syms)
        st["id"] = f["id"]
        st["spec"] = {k: (list(v) if isinstance(v, tuple) else v)
                      for k, v in f.items() if k != "id"}
        st.pop("per_pair", None) if f["fam"] != "pair" else None
        st["secs"] = round(time.time() - t0, 1)
        results.append(st)
        print(f"{f['id']:>4} n={st.get('n')} net={st.get('net_bp')} "
              f"t={st.get('t')} S={st.get('sharpe')}", flush=True)

    # ---- diagnostics. The placebo set is PRE-SPECIFIED (not picked off the results).
    diags = []
    BYID = {f["id"]: f for f in FORMULAS}
    for fid in ("B2", "B13", "B16", "B19", "B21"):
        f = BYID[fid]
        syms = [u for u, v in W.items() if v["region"] in f["regions"]]
        kw = {k: v for k, v in f.items()
              if k in ("mode", "L", "L2", "hl", "frac", "h", "zgate", "region_neutral",
                       "weighting", "entry_lag", "etb_only")}
        for pl in ("flip", "shuffle"):
            st, _ = xsec(W, syms, dates, hs, etb, label=f"{fid}:{pl}", placebo=pl, **kw)
            st["kind"] = "placebo"
            diags.append(st)
    # cost stress + HTB borrow, on every formula that clears the design noise bar
    years0 = len(dates) / 252.0
    bar = math.sqrt(2 * math.log(len(FORMULAS))) / math.sqrt(years0)
    stress = []
    for r in results:
        if (r.get("sharpe") or -9) < bar or r["spec"]["fam"] != "xsec":
            continue
        f = BYID[r["id"]]
        syms = [u for u, v in W.items() if v["region"] in f["regions"]]
        kw = {k: v for k, v in f.items()
              if k in ("mode", "L", "L2", "hl", "frac", "h", "zgate", "region_neutral",
                       "weighting", "entry_lag", "etb_only")}
        for mult, bor, tag in ((1.5, BORROW_ETB, "hs x1.5"), (2.0, BORROW_ETB, "hs x2.0"),
                               (3.0, BORROW_ETB, "hs x3.0"),
                               (1.0, BORROW_HTB, "HTB borrow 10.28%/yr")):
            st, _ = xsec(W, syms, dates, hs, etb, label=f"{r['id']}: {tag}",
                         hs_mult=mult, borrow=bor, **kw)
            stress.append(st)

    years = sum(1 for _ in dates) / 252.0
    N = len(FORMULAS)
    bar_t = math.sqrt(2 * math.log(N))
    payload = {"window": which, "range": [lo, hi], "trading_days": len(dates),
               "years": round(years, 2), "n_formulas": N,
               "expected_max_t_under_null": round(bar_t, 3),
               "expected_max_sharpe_under_null": round(bar_t / math.sqrt(years), 3),
               "results": results,
               "placebos": diags,
               "cost_stress": stress,
               "census": census,
               "half_spread_detail_bp": hsdet,
               "borrow_state": etb}
    p = OUT / f"DEEPMINE_crosslist_{which.upper()}.json"
    p.write_text(json.dumps(payload, indent=1, default=str))
    print("wrote", p, flush=True)
    return payload


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "design")
