#!/usr/bin/env python3
"""T30 day-30 borrow evaluator -- the frozen decision rule of T30_BORROW_FORWARD.md as code.

Written and sha256-pinned 2026-08-26 03:00 CEST (task T35), on day 2 of the collector, BEFORE
any pair-level FEERATE/AVAILABLE has been read by anyone.  The point of this file is that on the
30th clean day the verdict is produced MECHANICALLY: nobody chooses a threshold, a window or a
pair set after seeing rates.

Frozen rule (T30_BORROW_FORWARD.md, verbatim from the agenda, frozen 2026-08-24 00:00):

    KILL-CONDITION: after 30 clean days, if <10 of the 113 pairs have both legs borrowable at
    fee < that pair's measured gross edge, preferred-series RV is PERMANENTLY DEAD and the
    collector downgrades to passive archive.

Protocol as implemented here (numbered as in the doc):

 1. `--evaluate` REFUSES to run unless ledger.summary.days_clean >= 30.  There is no override
    flag.  Until then the only mode that reads an extract is `--format-check`, which reads the
    day-1 file, validates the schema and symbol join, and prints COUNTS ONLY (no rate, no
    availability figure, nothing pair-level).
 2. "Both legs borrowable" = both IBKR SYMs present in the extract with AVAILABLE > 0 on >= 80 %
    of the clean days (denominator = all clean days in the ledger at evaluation time).
    "Fee < gross edge" = median over clean days of max(leg FEERATEs) converted to bp/week as
    FEERATE(%/yr) / 52 * 100, compared with that pair's measured gross weekly edge (bp per
    active week) from the pinned B01 pair record (see --build-edges).
 3. Symbology: alpaca_sym.replace(".PR", " PR").  A pair whose legs cannot both be joined counts
    as NOT borrowable (missing-data conservatism).

The per-pair gross edge is NOT in INVENT_0822_pairtether_B.json (that record is aggregate), so
`--build-edges` rebuilds the 113 B01 pairs deterministically from the frozen design cache
(research/data/inv0822_tether/, the SAME files and SAME screens as invent0822_preftether.py:
coverage >= 70 % of the design grid, median raw price in (5, 40), same issuer root, >= 100
finite spread points in the design window, weekly grid = every 5th session, z52 |z|>=2 -> 0.5,
26-week cap, returns from dividend-adjusted closes, levels from raw closes) and writes
research/trading_bot/T30_B01_PAIR_EDGES.json.  It asserts n_pairs == 113 against the record.
The edge used by the rule is the FULL cached sample (design + held-out, 2018-01 -> 2026-08-14)
mean gross P&L per active week, in bp, per pair; the design-only figure is stored alongside for
transparency but is not used.  Nothing in that file comes from the forward panel.

`--evaluate` verifies the sha256 of this script, the pair-edge file and the protocol doc against
research/trading_bot/T30_BORROW_FORWARD.sha256 before producing a verdict, and writes
research/trading_bot/T30_BORROW_VERDICT.json.

Research only.  No network.  No orders.  Never touches the t4 path.
"""
import argparse
import gzip
import hashlib
import itertools
import json
import os
import re
import sys
import time

import numpy as np

np.seterr(all="ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "research", "data", "borrow_forward")
CACHE = os.path.join(ROOT, "research", "data", "inv0822_tether")
RT = os.path.join(ROOT, "research", "trading_bot")
EDGES = os.path.join(RT, "T30_B01_PAIR_EDGES.json")
SHAFILE = os.path.join(RT, "T30_BORROW_FORWARD.sha256")
VERDICT = os.path.join(RT, "T30_BORROW_VERDICT.json")

# frozen constants (T30_BORROW_FORWARD.md + agenda kill-condition)
MIN_CLEAN_DAYS = 30
AVAIL_FRAC = 0.80
MIN_PAIRS_ALIVE = 10
N_PAIRS_RECORD = 113
# B01 construction constants (invent0822_preftether.py)
DESIGN_END = "2023-12-31"
Z_L, Z_K, Z_X, MAXHOLD = 52, 2.0, 0.5, 26


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ibkr_sym(alpaca_sym):
    return alpaca_sym.replace(".PR", " PR")


def parse_avail(v):
    """AVAILABLE is an int or a string like '>10000000'; anything unparseable is 0."""
    try:
        return int(str(v).strip().lstrip(">").replace(",", "") or 0)
    except ValueError:
        return 0


def parse_fee(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


# ----------------------------------------------------------------------------- pair record
def build_pairs():
    adj = json.load(gzip.open(os.path.join(CACHE, "pref_bars.json.gz")))
    raw = json.load(gzip.open(os.path.join(CACHE, "pref_bars_raw.json.gz")))
    pr = sorted(s for s in raw if re.match(r"^[A-Z]+\.PR[A-Z]$", s))
    days = sorted({d for s in raw.values() for d in s})
    grid = days[::5]
    d0 = sum(1 for d in grid if d <= DESIGN_END)
    T = len(grid)
    syms = []
    for s in pr:
        r = raw[s]
        v = np.array([r.get(d, np.nan) for d in grid[:d0]], float)
        if np.isfinite(v).mean() < 0.70:
            continue
        med = float(np.nanmedian(v))
        if not (5.0 < med < 40.0):
            continue
        syms.append(s)
    si = {s: k for k, s in enumerate(syms)}
    RAW = np.full((T, len(syms)), np.nan)
    ADJ = np.full((T, len(syms)), np.nan)
    for s in syms:
        k = si[s]
        rr, aa = raw[s], adj.get(s, {})
        for t, d in enumerate(grid):
            v = rr.get(d)
            if v:
                RAW[t, k] = v
            v = aa.get(d)
            if v:
                ADJ[t, k] = v
    RET = np.full_like(ADJ, np.nan)
    RET[:-1] = ADJ[1:] / ADJ[:-1] - 1.0

    byroot = {}
    for s in syms:
        byroot.setdefault(s.split(".")[0], []).append(s)
    pairs = []
    for root, ss in sorted(byroot.items()):
        for a, b in itertools.combinations(sorted(ss), 2):
            i, j = si[a], si[b]
            sp = np.log(RAW[:d0, i]) - np.log(RAW[:d0, j])
            if np.isfinite(sp).sum() < 100:
                continue
            pairs.append(dict(i=i, j=j, a=a, b=b, root=root))

    ia = np.array([p["i"] for p in pairs])
    ib = np.array([p["j"] for p in pairs])
    S = np.log(RAW[:, ia]) - np.log(RAW[:, ib])
    Z = np.full_like(S, np.nan)
    import warnings
    warnings.simplefilter("ignore", RuntimeWarning)
    for t in range(Z_L, T):
        w = S[t - Z_L:t, :]
        n = np.isfinite(w).sum(0)
        mu = np.nanmean(np.where(np.isfinite(w), w, np.nan), 0)
        sd = np.nanstd(w, 0, ddof=1)
        Z[t] = np.where((n >= max(8, Z_L // 2)) & (sd > 0), (S[t] - mu) / sd, np.nan)

    # per-pair gross P&L per active week, same state machine as preftether.book(gross=True)
    n = len(pairs)
    w = np.zeros(n)
    age = np.zeros(n, int)
    pnl = np.zeros((T, n))
    act = np.zeros((T, n), bool)
    for t in range(Z_L, T - 1):
        z = Z[t]
        nw = w.copy()
        nw[(w != 0) & np.isfinite(z) & (np.abs(z) <= Z_X)] = 0.0
        nw[(w != 0) & (age >= MAXHOLD)] = 0.0
        rr = RET[t]
        dead = ~np.isfinite(rr[ia]) | ~np.isfinite(rr[ib])
        nw[dead] = 0.0
        en = (nw == 0) & np.isfinite(z) & (np.abs(z) >= Z_K) & ~dead
        nw[en] = -np.sign(z[en])
        a = nw != 0
        pnl[t, a] = (nw * (rr[ia] - rr[ib]))[a]
        act[t] = a
        w, age = nw, np.where(nw != 0, age + 1, 0)

    out = []
    for k, p in enumerate(pairs):
        full = act[:, k]
        des = act[:d0, k]
        out.append(dict(
            a=p["a"], b=p["b"], root=p["root"],
            ibkr_a=ibkr_sym(p["a"]), ibkr_b=ibkr_sym(p["b"]),
            active_weeks_full=int(full.sum()),
            active_weeks_design=int(des.sum()),
            gross_bp_per_active_week_full=float(pnl[full, k].mean() * 1e4) if full.any() else float("nan"),
            gross_bp_per_active_week_design=float(pnl[:d0, k][des].mean() * 1e4) if des.any() else float("nan"),
        ))
    return dict(
        built="2026-08-26",
        source="research/data/inv0822_tether/{pref_bars,pref_bars_raw}.json.gz (frozen INVENT_0822 cache)",
        construction="invent0822_preftether.py B01: coverage>=70% design grid, median raw price in (5,40), "
                     "same issuer root, >=100 finite design spread points, weekly grid days[::5], "
                     "z52 |z|>=2 -> 0.5, 26w cap, returns from adjusted closes, levels from raw closes",
        grid_first=grid[0], grid_last=grid[-1], T=T, design_weeks=d0,
        edge_used_by_rule="gross_bp_per_active_week_full",
        n_pairs=len(out),
        pairs=out,
    )


def cmd_build_edges():
    rec = build_pairs()
    if rec["n_pairs"] != N_PAIRS_RECORD:
        print("FAIL: rebuilt %d pairs, record says %d -- NOT writing" % (rec["n_pairs"], N_PAIRS_RECORD))
        return 2
    with open(EDGES, "w") as fh:
        json.dump(rec, fh, indent=1, sort_keys=True)
    e = np.array([p["gross_bp_per_active_week_full"] for p in rec["pairs"]], float)
    e = e[np.isfinite(e)]
    print("wrote %s: %d pairs, grid %s..%s (T=%d, design %d)" % (
        EDGES, rec["n_pairs"], rec["grid_first"], rec["grid_last"], rec["T"], rec["design_weeks"]))
    print("gross bp/active-week (full sample): median %.1f  p25 %.1f  p75 %.1f  n_positive %d/%d" % (
        np.median(e), np.percentile(e, 25), np.percentile(e, 75), int((e > 0).sum()), len(e)))
    print("sha256 %s" % sha256(EDGES))
    return 0


# ----------------------------------------------------------------------------- data access
def load_ledger():
    with open(os.path.join(DATA, "ledger.json")) as fh:
        return json.load(fh)


def clean_days(ledger):
    return sorted(d for d, v in ledger["days"].items() if v.get("status") == "clean")


def load_extract(date):
    with open(os.path.join(DATA, "extract", "extract_%s.json" % date)) as fh:
        e = json.load(fh)
    for key in ("bof", "date", "n_matched", "n_universe", "rows"):
        if key not in e:
            raise ValueError("extract %s missing key %s" % (date, key))
    for r in e["rows"]:
        for col in ("SYM", "FEERATE", "AVAILABLE"):
            if col not in r:
                raise ValueError("extract %s row missing column %s" % (date, col))
    return e


def load_edges():
    with open(EDGES) as fh:
        return json.load(fh)


# ----------------------------------------------------------------------------- modes
def cmd_format_check():
    """Day-1 schema + join check.  Prints counts only; suppresses every pair-level figure."""
    ledger = load_ledger()
    days = clean_days(ledger)
    if not days:
        print("no clean day in ledger")
        return 2
    day1 = days[0]
    e = load_extract(day1)
    edges = load_edges()
    legs = sorted({p["ibkr_a"] for p in edges["pairs"]} | {p["ibkr_b"] for p in edges["pairs"]})
    present = {r["SYM"] for r in e["rows"]}
    joined = [s for s in legs if s in present]
    pairs_both = sum(1 for p in edges["pairs"] if p["ibkr_a"] in present and p["ibkr_b"] in present)
    n_fee_parse = sum(1 for r in e["rows"] if np.isfinite(parse_fee(r["FEERATE"])))
    print("format check on day-1 extract %s (bof %s): rows %d, universe %d, matched %d" % (
        day1, e["bof"], len(e["rows"]), e["n_universe"], e["n_matched"]))
    print("B01 pair record: %d pairs, %d distinct legs; legs present in extract: %d/%d; "
          "pairs with BOTH legs present: %d/%d" % (
              edges["n_pairs"], len(legs), len(joined), len(legs), pairs_both, edges["n_pairs"]))
    print("FEERATE parseable on %d/%d rows; AVAILABLE parse OK on %d/%d rows" % (
        n_fee_parse, len(e["rows"]),
        sum(1 for r in e["rows"] if parse_avail(r["AVAILABLE"]) >= 0), len(e["rows"])))
    print("ledger: clean %d / attempted %d; evaluate unlocks at %d clean days" % (
        ledger["summary"]["days_clean"], ledger["summary"]["days_attempted"], MIN_CLEAN_DAYS))
    print("no rate or availability figure printed by design.")
    return 0


def verify_pins():
    pins = {}
    with open(SHAFILE) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            h, p = line.split(None, 1)
            pins[p.strip()] = h
    bad = []
    for rel in ("scripts/trading_bot/t30_borrow_evaluate.py",
                "research/trading_bot/T30_B01_PAIR_EDGES.json",
                "research/trading_bot/T30_BORROW_FORWARD.md"):
        want = pins.get(rel)
        have = sha256(os.path.join(ROOT, rel))
        if want != have:
            bad.append((rel, want, have))
    return bad


def cmd_evaluate():
    ledger = load_ledger()
    days = clean_days(ledger)
    if len(days) < MIN_CLEAN_DAYS:
        print("REFUSED: %d clean days < %d. No pair-level number is read before the gate." % (
            len(days), MIN_CLEAN_DAYS))
        return 3
    bad = verify_pins()
    if bad:
        for rel, want, have in bad:
            print("PIN MISMATCH %s: pinned %s, on disk %s" % (rel, want, have))
        print("REFUSED: evaluator, pair record or protocol doc drifted from the pinned hash.")
        return 4
    edges = load_edges()
    key = edges["edge_used_by_rule"]
    n_days = len(days)
    both_ok = np.zeros(edges["n_pairs"], int)
    fee_max = [[] for _ in range(edges["n_pairs"])]
    for d in days:
        e = load_extract(d)
        rows = {r["SYM"]: r for r in e["rows"]}
        for k, p in enumerate(edges["pairs"]):
            ra, rb = rows.get(p["ibkr_a"]), rows.get(p["ibkr_b"])
            if ra is None or rb is None:
                continue
            if parse_avail(ra["AVAILABLE"]) > 0 and parse_avail(rb["AVAILABLE"]) > 0:
                both_ok[k] += 1
            fa, fb = parse_fee(ra["FEERATE"]), parse_fee(rb["FEERATE"])
            if np.isfinite(fa) and np.isfinite(fb):
                fee_max[k].append(max(fa, fb))
    results = []
    for k, p in enumerate(edges["pairs"]):
        borrowable = both_ok[k] / n_days >= AVAIL_FRAC
        fee_pct = float(np.median(fee_max[k])) if fee_max[k] else float("nan")
        fee_bp_wk = fee_pct / 52.0 * 100.0 if np.isfinite(fee_pct) else float("nan")
        edge = p[key]
        fee_ok = np.isfinite(fee_bp_wk) and np.isfinite(edge) and fee_bp_wk < edge
        results.append(dict(a=p["a"], b=p["b"], both_available_frac=both_ok[k] / n_days,
                            borrowable=bool(borrowable), median_max_fee_pct=fee_pct,
                            fee_bp_per_week=fee_bp_wk, gross_edge_bp_per_week=edge,
                            alive=bool(borrowable and fee_ok)))
    n_alive = sum(r["alive"] for r in results)
    n_borrowable = sum(r["borrowable"] for r in results)
    dead = n_alive < MIN_PAIRS_ALIVE
    verdict = dict(
        evaluated_at=time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        clean_days=n_days, first_day=days[0], last_day=days[-1],
        rule="after 30 clean days, if <10 of the 113 pairs have both legs borrowable at fee < "
             "that pair's measured gross edge, preferred-series RV is PERMANENTLY DEAD",
        n_pairs=edges["n_pairs"], n_both_borrowable=n_borrowable, n_alive=n_alive,
        threshold=MIN_PAIRS_ALIVE,
        verdict="PERMANENTLY_DEAD" if dead else "BORROW_WALL_PASSED",
        next_step=("collector downgrades to passive archive" if dead else
                   "B01 remains UNPROMOTABLE on its own record (held-out net t 1.48, dies at 2x spread); "
                   "a revival needs a NEW pre-registration on the >= 30 both-shortable pairs at "
                   "realised half-spread <= 9 bp (INVENT_0822_MASTER 3.1 guard)"),
        pairs=results,
    )
    with open(VERDICT, "w") as fh:
        json.dump(verdict, fh, indent=1, sort_keys=True)
    print("T30 day-%d verdict: both-borrowable %d/%d, alive (borrowable AND fee < gross edge) %d/%d "
          "vs threshold %d -> %s" % (n_days, n_borrowable, edges["n_pairs"], n_alive, edges["n_pairs"],
                                     MIN_PAIRS_ALIVE, verdict["verdict"]))
    print("written %s" % VERDICT)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build-edges", action="store_true",
                   help="rebuild the 113 B01 pairs + per-pair gross edge from the frozen cache (no forward data)")
    g.add_argument("--format-check", action="store_true",
                   help="validate day-1 extract schema + symbol join; counts only, no rates")
    g.add_argument("--evaluate", action="store_true",
                   help="run the frozen day-30 rule; refuses below 30 clean days or on pin mismatch")
    a = ap.parse_args()
    if a.build_edges:
        return cmd_build_edges()
    if a.format_check:
        return cmd_format_check()
    return cmd_evaluate()


if __name__ == "__main__":
    sys.exit(main())
