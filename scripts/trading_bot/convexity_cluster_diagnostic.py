#!/usr/bin/env python3
"""T63 -- ADDITIVE cluster diagnostic for the frozen T35 convexity reading.

Pre-registered and sha256-pinned 2026-09-07 12:00 CEST, BLIND: 107 days before the first
reading (2026-12-23), with zero rows read from either forward panel.  It changes NOTHING in
CONVEXITY_PREREGISTRATION.md: every threshold, design, date, exit rule and verdict of
convexity_evaluate.py runs exactly as pinned.  This script runs AFTER that evaluator has
written its verdict file and reports one thing the frozen rule cannot see.

THE DEFECT IT MEASURES.  The frozen standard error clusters on (underlying, expiry).  A bought
strangle on SPY, QQQ, IWM, XLF, AAPL, MSFT, AMZN, NVDA, AMD, TSLA into the SAME week is not ten
independent bets -- it is one market-wide vol bet counted ten times.  D2 (aftershock) makes this
worst: a market-wide shock fires every name on the same day, so the pre-registration's own power
note ("~40-60 clusters across 15-16 underlyings") describes roughly THREE independent events
meeting an N_min of 40.  With m names equicorrelated at rho in a week, Var(mean) is understated
by ~1+(m-1)rho, so t is inflated by ~sqrt of that -- a true t of 0.9 can read as 2.5.

The error is ONE-SIDED: cross-sectional clustering can only inflate t and dilute the §6.4
concentration guard (one shock week splits into m clusters, each ~1/m of positive P&L, so the
40 % cap passes on a book that is one event).  It can never manufacture a DEAD verdict.  So a
frozen DEAD stands untouched; only a PASS is at risk, and only a PASS is re-read here.

FROZEN INTERPRETATION TABLE (fixed now, blind):

  frozen verdict   | week-clustered evidence                            | cluster verdict
  -----------------|----------------------------------------------------|----------------------
  DEAD             | --                                                 | DEAD_UNAFFECTED
  UNDECIDED        | --                                                 | UNDECIDED_UNAFFECTED
  ALIVE            | t_week >= 2.5 AND weeks >= 12 AND max_week <= 0.40 | BROAD_PASS
  ALIVE            | anything else                                      | CLUSTERED_PASS

BROAD_PASS = report the survivor as the frozen rule reports it.  CLUSTERED_PASS = NOT
fork-relevant survival: the book is a handful of correlated calendar events wearing the costume
of 40+ clusters, and it does not license a spend decision.

Why weeks >= 12: the first reading's panel is 2026-08-26 -> 2026-12-22, ~17 calendar weeks.  A
40-unit floor is unattainable on independent time units by construction (that is itself the
finding), so the floor is set at a majority of the weeks the panel can contain.  Fixed here,
blind, before any panel row exists.

Why entry-WEEK is the clustering unit, pooled across BOTH universes: the correlated object is
the calendar event, not the ticker.  BTC/ETH are pooled into the same week as the US names
deliberately -- D2's own mechanism claim is that cascade regimes are cross-asset, so treating a
cascade week as one unit is the honest null for the claim being made.

Usage:
  convexity_cluster_diagnostic.py --check                  pre-gate; opens no panel, no verdict
  convexity_cluster_diagnostic.py --diagnose [--reading first]

Research only.  No network.  No orders.  Never touches the t4 path.  Writes exactly one file:
research/trading_bot/CONVEXITY_CLUSTER_DIAGNOSTIC_<open>.json
"""
import argparse
import datetime as dt
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convexity_evaluate as CE  # noqa: E402

WEEKS_MIN = 12
T_BAR_WEEK = 2.5
MAX_WEEK_SHARE = 0.40
SELF_REL = "scripts/trading_bot/convexity_cluster_diagnostic.py"
PIN_FILE = os.path.join(CE.RT, "CONVEXITY_CLUSTER_DIAGNOSTIC.sha256")


def verdict_path(reading):
    return os.path.join(CE.RT, "CONVEXITY_VERDICT_%s.json" % CE.READINGS[reading]["open"])


def out_path(reading):
    return os.path.join(CE.RT, "CONVEXITY_CLUSTER_DIAGNOSTIC_%s.json" % CE.READINGS[reading]["open"])


def iso_week(datestr):
    y, w, _ = CE.parse_date(datestr).isocalendar()
    return "%04d-W%02d" % (y, w)


def week_stats(trades):
    """Cluster-robust stats with cluster = calendar entry-week, pooled over both universes."""
    if not trades:
        return {"n": 0, "weeks": 0, "mean": None, "t_week": None, "max_week_share": None,
                "weeks_list": [], "per_week_n": {}}
    n = len(trades)
    mean = sum(t["r"] for t in trades) / n
    by = {}
    for t in trades:
        by.setdefault(iso_week(t["date"]), []).append(t["r"])
    s = sum((sum(v) - len(v) * mean) ** 2 for v in by.values())
    se = math.sqrt(s) / n if s > 0 else 0.0
    tw = mean / se if se > 0 else (float("inf") if mean > 0 else float("-inf") if mean < 0 else 0.0)
    pos = sorted((sum(v) for v in by.values() if sum(v) > 0), reverse=True)
    share = (pos[0] / sum(pos)) if pos else 0.0
    return {"n": n, "weeks": len(by), "mean": float(mean), "t_week": float(tw),
            "max_week_share": float(share), "weeks_list": sorted(by),
            "per_week_n": {k: len(v) for k, v in sorted(by.items())}}


def classify(frozen, ws):
    if frozen == "DEAD":
        return "DEAD_UNAFFECTED"
    if frozen == "UNDECIDED":
        return "UNDECIDED_UNAFFECTED"
    if frozen != "ALIVE":
        return "UNKNOWN_FROZEN_VERDICT"
    broad = (ws["t_week"] is not None and ws["t_week"] >= T_BAR_WEEK
             and ws["weeks"] >= WEEKS_MIN
             and ws["max_week_share"] is not None and ws["max_week_share"] <= MAX_WEEK_SHARE)
    return "BROAD_PASS" if broad else "CLUSTERED_PASS"


def cmd_check(reading):
    vp = verdict_path(reading)
    print(json.dumps({
        "state": "PENDING_VERDICT",
        "reading": reading,
        "reading_opens": CE.READINGS[reading]["open"],
        "today": dt.date.today().isoformat(),
        "frozen_verdict_file": vp,
        "frozen_verdict_exists": os.path.exists(vp),
        "panel_rows_read": 0,
        "thresholds": {"weeks_min": WEEKS_MIN, "t_bar_week": T_BAR_WEEK,
                       "max_week_share": MAX_WEEK_SHARE},
        "note": "additive; reads the frozen verdict only after convexity_evaluate.py writes it",
    }, indent=1, sort_keys=True))
    return 0


def cmd_diagnose(reading):
    vp = verdict_path(reading)
    if not os.path.exists(vp):
        print("REFUSED: %s does not exist. This diagnostic never precedes the frozen reading." % vp)
        return 3
    bad = CE.verify_pins()
    if bad:
        for rel, want, have in bad:
            print("PIN MISMATCH %s: pinned %s, on disk %s" % (rel, want, have))
        print("REFUSED: the frozen pre-registration/evaluator drifted.")
        return 4
    op = out_path(reading)
    if os.path.exists(op):
        print("REFUSED: %s exists; the diagnostic is written once." % op)
        return 5

    frozen = json.load(open(vp))
    R = CE.READINGS[reading]
    elig, n_gate = CE.t33_eligibility(CE.T33_DIR)
    t33_unds = [u for u in CE.T33_UNIVERSE if elig[u]["eligible"]]
    t31_panel = CE.load_t31(CE.T31_DIR, *R["t31"], universe=CE.T31_UNIVERSE)
    t33_panel = CE.load_t33(CE.T33_DIR, *R["t33"], universe=t33_unds) if t33_unds else {}
    books = []
    if t31_panel:
        b, _ = CE.build_book(t31_panel, "t31", CE.t31_settler(CE.T31_DIR), R["t31"][1])
        books += b
    if t33_panel:
        b, _ = CE.build_book(t33_panel, "t33", CE.t33_settler(t33_panel), R["t33"][1])
        books += b
    settled = [t for t in books if t["r"] is not None]

    out = {"reading": reading, "reading_opens": R["open"], "frozen_verdict_file": vp,
           "designs": {}, "n_settled_rebuilt": len(settled),
           "thresholds": {"weeks_min": WEEKS_MIN, "t_bar_week": T_BAR_WEEK,
                          "max_week_share": MAX_WEEK_SHARE},
           "written_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    for d in CE.DESIGNS:
        fv = frozen.get("designs", {}).get(d, {})
        ds = [t for t in settled if t["trig"][d]]
        ws = week_stats(ds)
        fstats = fv.get("stats", {})
        out["designs"][d] = {
            "frozen_verdict": fv.get("verdict"),
            "frozen_clusters_und_expiry": fstats.get("clusters"),
            "frozen_t": fstats.get("t"),
            "frozen_conc": fstats.get("conc"),
            "week_clustered": ws,
            "rebuild_matches_frozen_n": (fstats.get("n") == ws["n"]),
            "cluster_verdict": classify(fv.get("verdict"), ws),
        }
    out["summary"] = {d: v["cluster_verdict"] for d, v in out["designs"].items()}
    out["any_clustered_pass"] = any(v == "CLUSTERED_PASS" for v in out["summary"].values())
    with open(op, "w") as fh:
        json.dump(CE.compact(out), fh, indent=1, sort_keys=True)
    for d, v in out["designs"].items():
        ws = v["week_clustered"]
        print("%s: frozen %s -> %s | clusters(und,exp) %s vs weeks %d | t %s -> t_week %s | max_week %s" % (
            d, v["frozen_verdict"], v["cluster_verdict"], v["frozen_clusters_und_expiry"], ws["weeks"],
            "%.2f" % v["frozen_t"] if isinstance(v["frozen_t"], float) else "n/a",
            "%.2f" % ws["t_week"] if ws["t_week"] is not None else "n/a",
            "%.2f" % ws["max_week_share"] if ws["max_week_share"] is not None else "n/a"))
    print("written: %s" % op)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="pre-gate state; opens no panel")
    g.add_argument("--diagnose", action="store_true", help="run after the frozen evaluator wrote its verdict")
    ap.add_argument("--reading", choices=("first", "second"), default="first")
    a = ap.parse_args()
    return cmd_check(a.reading) if a.check else cmd_diagnose(a.reading)


if __name__ == "__main__":
    sys.exit(main())
