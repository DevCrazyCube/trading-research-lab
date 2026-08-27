#!/usr/bin/env python3
"""INVENT_0822 forced/mechanical-flow — PRE-REGISTERED formula list and runner.

Design window : events with R-date in 2016-01-04 .. 2021-12-31
Held-out      : events with R-date in 2022-01-01 .. 2026-08-14   (untouched until the design
                pass is written to disk)

Signs are fixed BY THE MECHANISM before any number is looked at:
  * an index ADD is forced BUYING into the rebalance close -> price is pushed UP into R and
    should give back after R.  Pre-R sign +1, post-R sign -1.
  * an index DELETE is forced SELLING -> pushed DOWN into R, rebound after.  Pre-R -1, post +1.
  * an IPO lockup expiry is a supply cliff -> pre-expiry sign -1, post-expiry rebound +1.
  * a 424B5 shelf takedown is a discounted placement -> post-filing rebound +1.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from trading_bot.inv0822_flow_engine import (BARS, FLOW, Panel, evaluate,  # noqa: E402
                                             dstr_to_int)

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"

DESIGN = ("2016-01-04", "2021-12-31")
HELDOUT = ("2022-01-01", "2026-08-14")


def load_events():
    ev = json.loads((FLOW / "raw" / "index_changes.json").read_text())
    ev = [e for e in ev if e["date"] >= "2016-01-05"]
    # migrations: same ticker, same date, add in one index and delete in another
    by = {}
    for e in ev:
        by.setdefault((e["ticker"], e["date"]), []).append(e)
    rank = {"SP600": 0, "SP400": 1, "SP500": 2}
    promo, demote = [], []
    for (tk, d), grp in by.items():
        adds = [g for g in grp if g["side"] == "add"]
        dels = [g for g in grp if g["side"] == "delete"]
        if adds and dels:
            hi_add = max(rank[a["index"]] for a in adds)
            hi_del = max(rank[x["index"]] for x in dels)
            rec = dict(adds[0])
            a_idx = max(adds, key=lambda z: rank[z["index"]])["index"]
            d_idx = max(dels, key=lambda z: rank[z["index"]])["index"]
            rec["_trans"] = f"{d_idx}->{a_idx}"
            if hi_add > hi_del:
                promo.append(rec)
            elif hi_del > hi_add:
                demote.append(rec)
    return ev, promo, demote


# Passive ownership fraction of float market cap, by index.  Order of magnitude only, and it
# is the ORDERING that carries the argument, not the second digit:
#   S&P 500 : ~$10T of index-tracking AUM against ~$50T of float  -> ~20% of every added name
#   S&P 400 : ~$0.13T against ~$3.2T                              -> ~4%
#   S&P 600 : ~$0.09T against ~$1.3T                              -> ~7%
# A MIGRATION therefore trades (passive_new - passive_old) x market cap, and its SIGN is not
# "up is buying".  400->500 buys ~20% and sells ~4% = a huge NET BUY; 600->400 buys ~4% and
# sells ~7% = a modest NET SELL.  Pooling promotions together mixes the two opposite signs,
# which is what block 2 did wrong.
PASSIVE = {"SP500": 0.20, "SP400": 0.04, "SP600": 0.07}


def net_flow_sign(trans: str) -> int:
    d, a = trans.split("->")
    diff = PASSIVE[a] - PASSIVE[d]
    return 1 if diff > 0 else -1          # +1 = mandated NET BUY, -1 = mandated NET SELL


def load_corp_events():
    """IPO lockup expiries (424B4 + 180 calendar days) and 424B5 shelf takedowns."""
    p = FLOW / "raw" / "edgar_424.json"
    if not p.exists():
        return [], []
    rows = json.loads(p.read_text())
    import datetime as dt
    # IPO = a company's FIRST 424B4 in the file (later 424B4s are follow-ons)
    first4: dict[str, str] = {}
    for r in rows:
        if r["form"] == "424B4":
            first4.setdefault(r["ticker"], r["date"])
    lock = []
    for tk, d in first4.items():
        if d < "2016-04-01":
            continue  # need a genuine first observation, not a left-censored one
        y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
        exp = dt.date(y, m, dd) + dt.timedelta(days=180)
        lock.append({"index": "IPO", "date": exp.isoformat(), "ticker": tk, "ipo": d})
    # secondary offerings: 424B5, one per ticker-date, drop tickers that spam the shelf
    import collections
    cnt = collections.Counter(r["ticker"] for r in rows if r["form"] == "424B5")
    sec = [{"index": "SEC", "date": r["date"], "ticker": r["ticker"]}
           for r in rows if r["form"] == "424B5" and cnt[r["ticker"]] <= 25]
    seen = set()
    sec = [s for s in sec if not (s["ticker"], s["date"]) in seen
           and not seen.add((s["ticker"], s["date"]))]
    return lock, sec


def annotate(panel, events):
    """Attach two MAGNITUDE measures, both observable AT THE R CLOSE (no lookahead):

      _relvol : $volume on R divided by the median $volume of R-40..R-9  -- the size of the
                forced print that actually went through the rebalance auction;
      _runup  : the hedged R-5 -> R return -- the size of the price pressure already paid.

    This is event-INTENSITY sorting, not regime gating: it conditions on how big THIS event's
    mandated flow was, which is the quantity the theme says must be large.
    """
    import numpy as np
    from trading_bot.inv0822_flow_engine import BENCH
    out = []
    for e in events:
        got = panel.get(e["ticker"])
        if got is None:
            continue
        c, dv = got
        ted = panel.day_index_on_or_after(dstr_to_int(e["date"]))
        if ted <= 0:
            continue
        R = ted - 1
        base = dv[max(0, R - 40):max(0, R - 8)]
        base = base[np.isfinite(base)]
        if base.size < 15 or np.median(base) <= 0 or R >= dv.size or not np.isfinite(dv[R]):
            continue
        rel = float(dv[R] / np.median(base))
        bcc = panel.get(BENCH.get(e["index"], "SPY"))[0]
        ru = float("nan")
        if R - 5 >= 0 and np.isfinite(c[R - 5]) and np.isfinite(c[R]):
            ru = (c[R] / c[R - 5] - 1.0) - (bcc[R] / bcc[R - 5] - 1.0)
        out.append(dict(e, _relvol=rel, _runup=ru))
    return out


def top_tercile(events, key, frac=1 / 3.0, high=True):
    import numpy as np
    vals = [e[key] for e in events if e.get(key) == e.get(key)]
    if len(vals) < 30:
        return []
    cut = float(np.quantile(vals, 1 - frac if high else frac))
    if high:
        return [e for e in events if e.get(key) == e.get(key) and e[key] >= cut]
    return [e for e in events if e.get(key) == e.get(key) and e[key] <= cut]


def build_formulas(panel):
    ev, promo, demote = load_events()

    def sel(idx=None, side=None):
        return [e for e in ev
                if (idx is None or e["index"] == idx) and (side is None or e["side"] == side)]

    lock, sec = load_corp_events()

    pair = ([dict(e, _sign=-1) for e in sel(side="add")]
            + [dict(e, _sign=+1) for e in sel(side="delete")])

    F = [
        # id, description, events, a, b, sign, hedged, tradability flag
        ("F01_SP500ADD_RUNUP5", "S&P500 add: long from R-5 close to the rebalance close R",
         sel("SP500", "add"), -5, 0, +1, True, "ANN"),
        ("F02_SP500ADD_LAST1", "S&P500 add: long R-1 close to R close (the flow day itself)",
         sel("SP500", "add"), -1, 0, +1, True, "ANN-mild"),
        ("F03_SP500ADD_REV5", "S&P500 add: SHORT R close to R+5 (give-back of the forced bid)",
         sel("SP500", "add"), 0, 5, -1, True, "CLEAN"),
        ("F04_SP500ADD_REV20", "S&P500 add: SHORT R close to R+20",
         sel("SP500", "add"), 0, 20, -1, True, "CLEAN"),
        ("F05_SP500ADD_REV60", "S&P500 add: SHORT R close to R+60",
         sel("SP500", "add"), 0, 60, -1, True, "CLEAN"),
        ("F06_SP500DEL_DOWN5", "S&P500 delete: SHORT R-5 to R (forced selling into the close)",
         sel("SP500", "delete"), -5, 0, -1, True, "ANN"),
        ("F07_SP500DEL_REB10", "S&P500 delete: LONG R close to R+10 (post-deletion rebound)",
         sel("SP500", "delete"), 0, 10, +1, True, "CLEAN"),
        ("F08_SP500DEL_REB60", "S&P500 delete: LONG R close to R+60",
         sel("SP500", "delete"), 0, 60, +1, True, "CLEAN"),
        ("F09_SP400ADD_RUNUP5", "S&P400 add: long R-5 to R",
         sel("SP400", "add"), -5, 0, +1, True, "ANN"),
        ("F10_SP400ADD_REV20", "S&P400 add: SHORT R to R+20",
         sel("SP400", "add"), 0, 20, -1, True, "CLEAN"),
        ("F11_SP400DEL_REB20", "S&P400 delete: LONG R to R+20",
         sel("SP400", "delete"), 0, 20, +1, True, "CLEAN"),
        ("F12_SP600ADD_RUNUP5", "S&P600 add: long R-5 to R",
         sel("SP600", "add"), -5, 0, +1, True, "ANN"),
        ("F13_SP600ADD_REV20", "S&P600 add: SHORT R to R+20",
         sel("SP600", "add"), 0, 20, -1, True, "CLEAN"),
        ("F14_SP600DEL_REB20", "S&P600 delete: LONG R to R+20",
         sel("SP600", "delete"), 0, 20, +1, True, "CLEAN"),
        ("F15_PROMOTE_RUNUP5", "index MIGRATION UP (600->400, 400->500): long R-5 to R",
         promo, -5, 0, +1, True, "ANN"),
        ("F16_PROMOTE_REV20", "index MIGRATION UP: SHORT R to R+20",
         promo, 0, 20, -1, True, "CLEAN"),
        ("F17_DEMOTE_REB20", "index MIGRATION DOWN (500->400, 400->600): LONG R to R+20",
         demote, 0, 20, +1, True, "CLEAN"),
        ("F18_ALLADD_REV20", "ALL S&P adds pooled: SHORT R to R+20",
         sel(side="add"), 0, 20, -1, True, "CLEAN"),
        ("F19_ALLDEL_REB20", "ALL S&P deletes pooled: LONG R to R+20",
         sel(side="delete"), 0, 20, +1, True, "CLEAN"),
        ("F20_ALLADD_LAST1", "ALL S&P adds pooled: long R-1 to R",
         sel(side="add"), -1, 0, +1, True, "ANN-mild"),
        ("F21_ALLADD_REV3", "ALL S&P adds pooled: SHORT R to R+3",
         sel(side="add"), 0, 3, -1, True, "CLEAN"),
        ("F22_ALLDEL_REB3", "ALL S&P deletes pooled: LONG R to R+3",
         sel(side="delete"), 0, 3, +1, True, "CLEAN"),
        ("F23_PAIR_REV20", "self-hedged flow pair: LONG deletes / SHORT adds, R to R+20",
         pair, 0, 20, 0, False, "CLEAN"),
        ("F24_LOCKUP_PRE", "IPO lockup expiry (424B4+180d): SHORT L-5 to L-1",
         lock, -5, -1, -1, True, "CLEAN"),
        ("F25_LOCKUP_REB10", "IPO lockup expiry: LONG L to L+10 (supply cleared)",
         lock, 0, 10, +1, True, "CLEAN"),
        ("F26_LOCKUP_CROSS", "IPO lockup expiry: SHORT L-10 to L (anticipation)",
         lock, -10, 0, -1, True, "CLEAN"),
        ("F27_SEC424B5_REB5", "424B5 shelf takedown: LONG F to F+5 (overhang cleared)",
         sec, 0, 5, +1, True, "CLEAN"),
        ("F28_SEC424B5_REB20", "424B5 shelf takedown: LONG F to F+20",
         sec, 0, 20, +1, True, "CLEAN"),
        ("F29_SEC424B5_PRE", "424B5: SHORT F-5 to F-1 (marketing-period pressure)",
         sec, -5, -1, -1, True, "NOT-TRADABLE(filing date unknown ex-ante)"),
    ]
    F = [tuple(list(f) + [None]) for f in F]

    # ---- MAGNITUDE-CONDITIONED variants.  The conditioner is the size of THIS event's
    # mandated flow, read off the rebalance close itself -- not a market-regime gate.
    adds_a = annotate(panel, sel(side="add"))
    dels_a = annotate(panel, sel(side="delete"))
    pair_a = ([dict(e, _sign=-1) for e in adds_a] + [dict(e, _sign=+1) for e in dels_a])
    hi_vol = lambda evs: top_tercile(evs, "_relvol", high=True)
    hi_run = lambda evs: top_tercile(evs, "_runup", high=True)
    lo_run = lambda evs: top_tercile(evs, "_runup", high=False)
    F += [
        ("F30_ADD_REV20_BIGFLOW",
         "adds whose rebalance-close $volume spike is in the top tercile: SHORT R to R+20",
         adds_a, 0, 20, -1, True, "CLEAN", hi_vol),
        ("F31_DEL_REB20_BIGFLOW",
         "deletes with a top-tercile rebalance-close $volume spike: LONG R to R+20",
         dels_a, 0, 20, +1, True, "CLEAN", hi_vol),
        ("F32_ADD_REV20_BIGRUNUP",
         "adds with the largest hedged R-5->R run-up: SHORT R to R+20",
         adds_a, 0, 20, -1, True, "CLEAN", hi_run),
        ("F33_DEL_REB20_BIGDROP",
         "deletes with the largest hedged R-5->R DROP: LONG R to R+20",
         dels_a, 0, 20, +1, True, "CLEAN", lo_run),
        ("F34_PAIR_REV20_BIGFLOW",
         "self-hedged flow pair restricted to top-tercile rebalance-close volume spikes",
         pair_a, 0, 20, 0, False, "CLEAN", hi_vol),
    ]

    # ---- BLOCK 2: the migration mechanism, with the sign CORRECTED.
    # F15/F16/F17 assumed "promotion = net forced BUY".  That was wrong, and the design data
    # says so: a company promoted 600->400 is a LARGE weight in the index it leaves and a TINY
    # weight in the index it joins, so the mandated trade is a NET SELL.  These four re-test
    # that corrected mechanism and are counted in N as four additional tests (which is why the
    # relevant bar for them is the TWO-SIDED sqrt(2 ln 2N)).
    migpair = ([dict(e, _sign=+1) for e in promo] + [dict(e, _sign=-1) for e in demote])
    F += [
        ("F35_MIGPAIR_REB5",
         "index MIGRATION pair, corrected sign: LONG promoted / SHORT demoted, R to R+5",
         migpair, 0, 5, 0, False, "CLEAN", None),
        ("F36_MIGPAIR_REB20", "index MIGRATION pair, corrected sign: R to R+20",
         migpair, 0, 20, 0, False, "CLEAN", None),
        ("F37_PROMOTE_REB5",
         "promoted (600->400, 400->500) LONG R to R+5 -- rebound from net forced selling",
         promo, 0, 5, +1, True, "CLEAN", None),
        ("F38_DEMOTE_FADE5",
         "demoted (500->400, 400->600) SHORT R to R+5 -- fade of net forced buying",
         demote, 0, 5, -1, True, "CLEAN", None),
    ]

    # ---- BLOCK 3: separate the TERMINAL deletes from the LIVE ones.
    # A deletion "because the company was acquired" has no post-event stock -- the tracker sells
    # into a cash tender and the name stops existing, so any post-R measurement on that subset is
    # a survivorship-shaped sample.  A deletion for "market capitalization change" / "no longer
    # representative" is the pure forced sale of a stock that keeps trading: the single largest
    # clean mandated sell in the whole theme.  Same idea on the add side: an add that is NOT a
    # migration is brand-new index demand rather than a weight transfer.
    #
    # CAVEAT, stated because it limits what F39-F41 can prove: S&P changes CASCADE, and the
    # reason text records the ROOT of the cascade, not what happened to this ticker.  "SSD
    # replaced Delphi Technologies after BorgWarner acquired Delphi" describes SSD being
    # PROMOTED, not acquired.  So this keyword filter is a coarse instrument, and the residual
    # requirement that a price exists at R+b remains a survivorship-shaped selection.  The
    # clean, lookahead-free version of "a forced sale of a stock that keeps trading" is the
    # MIGRATION set (F35-F38), where still-listed is true by construction and known at R.
    ma = ("acquir", "acquisition", "merg", "was bought", "taken private", "privatis",
          "privatiz", "tender offer")

    def live_delete(e):
        r = e.get("reason", "").lower()
        return not any(k in r for k in ma)

    mig_keys = {(e["ticker"], e["date"]) for e in promo} | {(e["ticker"], e["date"])
                                                            for e in demote}
    dels_live = [e for e in sel(side="delete") if live_delete(e)]
    adds_fresh = [e for e in sel(side="add") if (e["ticker"], e["date"]) not in mig_keys]
    F += [
        ("F39_DELLIVE_REB5",
         "deletes NOT caused by M&A (the stock keeps trading): LONG R to R+5",
         dels_live, 0, 5, +1, True, "CLEAN", None),
        ("F40_DELLIVE_REB20", "deletes NOT caused by M&A: LONG R to R+20",
         dels_live, 0, 20, +1, True, "CLEAN", None),
        ("F41_ADDFRESH_REV5",
         "adds that are NOT index migrations (brand-new index demand): SHORT R to R+5",
         adds_fresh, 0, 5, -1, True, "CLEAN", None),
    ]

    # ---- BLOCK 4: the four migration TYPES, each with the sign the passive-ownership
    # arithmetic dictates.  Temporary price pressure means the post-R move OPPOSES the
    # mandated flow: a net BUY is faded (short), a net SELL rebounds (long).
    mig = promo + demote
    by_t = {}
    for e in mig:
        by_t.setdefault(e["_trans"], []).append(e)
    ordered = ["SP400->SP500", "SP500->SP400", "SP600->SP400", "SP400->SP600"]
    for i, tr in enumerate(ordered):
        s = -net_flow_sign(tr)   # fade a forced buy, ride the rebound from a forced sell
        F.append((f"F{42+i}_MIG_{tr.replace('SP','').replace('->','to')}_R5",
                  f"migration {tr}: mandated net "
                  f"{'BUY' if net_flow_sign(tr) > 0 else 'SELL'} -> "
                  f"{'SHORT' if s < 0 else 'LONG'} R to R+5",
                  by_t.get(tr, []), 0, 5, s, True, "CLEAN", None))
    # and the pooled net-flow-signed version: one book, every migration, signed by arithmetic
    signed = [dict(e, _sign=-net_flow_sign(e["_trans"])) for e in mig]
    F.append(("F46_MIG_NETFLOW_R5",
              "ALL migrations in one self-hedged book, each signed by the passive-ownership "
              "differential (fade the net buys, buy the net sells), R to R+5",
              signed, 0, 5, 0, False, "CLEAN", None))
    F.append(("F47_MIG_NETFLOW_R20", "same book, R to R+20",
              signed, 0, 20, 0, False, "CLEAN", None))
    return F


def window(events, lo, hi):
    return [e for e in events if lo <= e["date"] <= hi]


def run(tag, lo, hi):
    panel = Panel()
    F = build_formulas(panel)
    out = {}
    for fid, desc, evs, a, b, sign, hedged, flag, post in F:
        sub = window(evs, lo, hi)
        if post is not None:
            sub = post(sub)          # tercile cut computed INSIDE the window
        r = evaluate(panel, sub, a, b, sign, hedged) if sub else None
        if r is None:
            r = {"n_events": 0}
        r.update({"desc": desc, "a": a, "b": b, "sign": sign, "hedged": hedged,
                  "tradability": flag})
        out[fid] = r
        print(f"{fid:24s} n={r.get('n_events',0):5d} mean_bp={r.get('mean_bp')!s:>9} "
              f"t={r.get('t_clustered')!s:>7} SR={r.get('sharpe_portfolio')!s:>7} "
              f"hit={r.get('hit_rate')!s:>6}  [{flag}]", flush=True)
    n = len(F)
    meta = {"window": [lo, hi], "n_formulas": n,
            "expected_max_t_under_null_onesided": round(math.sqrt(2 * math.log(n)), 3)}
    blob = {"meta": meta, "formulas": out}
    (OUT / f"INVENT_0822_forcedflow_{tag}.json").write_text(json.dumps(blob, indent=1))
    print(f"\nN={n}  E[max|t|] under null ~ sqrt(2 ln N) = {meta['expected_max_t_under_null_onesided']}")
    return blob


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "design"
    lo, hi = DESIGN if which == "design" else HELDOUT
    run(which, lo, hi)
