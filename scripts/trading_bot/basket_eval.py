#!/usr/bin/env python3
"""BASKET1 -- the read-only EVALUATE half of the imperfect-edge basket forward test.

WHAT THIS IS
============
A **read-only** evaluator over the append-only forward log written by
`scripts/trading_bot/basket_forward.py`. It reconstructs each leg's settled net-return stream and
the combined book series, applies the frozen per-leg **kill switch**, states how far the sample is
from licensing any claim, and refuses to compute the edge gates before the pre-registered minimum.

WHAT IT MUST NEVER DO, AND WHY THAT IS ENFORCED HERE
====================================================
The failure this programme exists to prevent is "the last few days looked bad, so we tuned the rule".
So, exactly as `forward_eval.py`:

* This module **never opens a ledger, state file, register or pre-registration for writing.**
  `_refuse_if_protected()` guards every write.
* It **verifies the pre-registration hash** on every run (through `basket_forward.frozen_spec`, which
  refuses if the .md moved) and reuses the frozen `kill_check` rather than re-deriving it.
* Improvement is out of scope by construction: there is no code path here that changes a rule. The
  honest-iterate answer is always a NEW frozen forward test (`ITERATION_PROTOCOL.md`).

Every number that could be misread as a result travels inside `inputs_that_are_not_results` with the
reason it is not evidence, the same discipline the logger uses.

USAGE
=====
    python -m scripts.trading_bot.basket_eval report              # human-readable
    python -m scripts.trading_bot.basket_eval report --json       # machine-readable
    python -m scripts.trading_bot.basket_eval status-line         # one line for a dashboard
    python -m scripts.trading_bot.basket_eval selftest            # hermetic wiring check
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .frozen import Refused
from . import basket_forward as bf
from .stats import deflated_sharpe, annualised_sharpe

TRADING_DAYS = 252.0

FRAMING = (
    "READ-ONLY EVALUATION OF A FORWARD PAPER LOGGER THAT HAS CERTIFIED NOTHING. No orders, no real "
    "money, no position -- every P&L is hypothetical mark-to-market. This report is evidence about "
    "what the frozen rules WOULD have realised, never a forecast, and it licenses no return claim "
    "before the pre-registered minimum. Every backtested number behind these legs is a selection-"
    "inflated UPPER BOUND; improvement is a NEW frozen test, never an edit to a running one."
)

_PROTECTED_SUFFIXES = ("_LOG.jsonl", "_STATE.json", "_FROZEN.json", "_PREREGISTRATION.md",
                       "_PREREGISTRATION.json", "FORWARD_REGISTER.json")


def _refuse_if_protected(path: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(path)
    for suffix in _PROTECTED_SUFFIXES:
        if path.name.endswith(suffix):
            raise Refused(f"refusing to write {path}: the evaluator is READ-ONLY over ledgers, "
                          "state, freezes and pre-registrations. If an evaluation makes you want to "
                          "change one, the answer is a NEW frozen forward test.")
    return path


# ---------------------------------------------------------------------------
# Reconstructing the settled streams from the ledger
# ---------------------------------------------------------------------------

LEG_IDS = ("T3", "ETFRV", "DUALCLASS", "T7", "T12CEF", "ORB", "XS_GLSR_Z", "XS_SMART", "CEFMUNIEQ",
           "ETFRV_Z20", "DUALCLASS_EXIT10", "CRYPTO_LOWVOL", "SKEW_TILT", "SKEW_TILT_CRUDE")


def _leg_settled_returns(record: dict, leg_id: str):
    """List of (exit_key, net_return) this record settled for `leg_id` (may be empty or multiple).

    L1 (T3) and L4 (T7) settle via `settled_from_pending`; L2 (ETFRV), L5 (T12CEF), L6 (ORB) settle
    inline via `settled`; L3 (DUALCLASS) can close several round-trips in one session via `marks`."""
    leg = (record.get("legs") or {}).get(leg_id) or {}
    if leg_id in ("T3", "T7"):
        s = (leg.get("settled_from_pending") or {}).get("settled")
        if not s:
            return []
        key = s.get("exit_session") or s.get("ex_date")
        return [(key, s["net_return"])]
    if leg_id in ("DUALCLASS", "DUALCLASS_EXIT10"):
        out = []
        for m in leg.get("marks", []) or []:
            out.append((f"{m['pair']}|{m['d_out']}", m["net_bp"] / 1e4))
        return out
    s = leg.get("settled")
    if not s:
        return []
    if leg_id == "T12CEF":
        return [(s["exit_date"], s["net_return_4wk"])]
    if leg_id == "CEFMUNIEQ":
        return [(s["exit_date"], s["net_return_1wk"])]
    return [(s["exit_session"], s["net_return"])]


def leg_streams(records: list) -> dict:
    """leg_id -> [(exit_key, net_return)], de-duplicated by exit key (first wins)."""
    out = {lid: [] for lid in LEG_IDS}
    seen = {lid: set() for lid in LEG_IDS}
    for rec in records:
        for lid in out:
            for key, ret in _leg_settled_returns(rec, lid):
                if key is not None and key not in seen[lid]:
                    seen[lid].add(key)
                    out[lid].append((key, ret))
    for lid in out:
        out[lid].sort()
    return out


def combined_series(records: list) -> list:
    """[(session_date, r_combined_net, r_benchmark)] over sessions whose combined block settled."""
    seen, out = set(), []
    for rec in records:
        c = rec.get("combined")
        d = rec.get("session_date")
        if c and c.get("r_combined_net") is not None and d not in seen:
            seen.add(d)
            out.append((d, float(c["r_combined_net"]), float(c["r_benchmark"])))
    out.sort()
    return out


# ---------------------------------------------------------------------------
# Per-leg evaluation (kill switch + fenced power inputs)
# ---------------------------------------------------------------------------

def eval_leg(leg_id: str, stream: list, spec: dict) -> dict:
    leg = bf.leg_by_id(spec, leg_id)
    rets = [r for _, r in stream]
    n = len(rets)
    kill = bf.kill_check(rets, spec)
    out = {"leg_id": leg_id, "name": leg["name"], "family": leg["family"],
           "status_at_freeze": leg["status"],
           "logged_unsized": leg["status"] == "ACTIVE_UNSIZED",
           "settled_observations": n,
           "declared_trials_in_leg_family": leg.get("declared_trials_in_leg_family"),
           "kill_switch": kill, "prior_verdict_backtest": leg.get("prior_verdict"),
           "minimum_before_verdict": spec["minimum_before_verdict"]["per_leg_settled_observations"]}
    if n >= 2:
        mean = statistics.fmean(rets)
        sd = statistics.stdev(rets)
        se = sd / math.sqrt(n)
        inputs = {"DISCLAIMER": (
            "NOT RESULTS. T4/basket prereg forbids quoting a Sharpe/CAGR/p-value before the minimum "
            f"({out['minimum_before_verdict']} settled obs). Shown so the power can be sized and the "
            "kill switch audited, fenced so they cannot be lifted out as an edge."),
            "mean_net_bp_per_obs": mean * 1e4, "sd_bp": sd * 1e4,
            "t_stat_per_obs": (mean / se) if se > 0 else None,
            "annualised_sharpe": annualised_sharpe(rets, int(TRADING_DAYS)) if n >= 2 else None}
        try:
            dsr = deflated_sharpe(rets, trials=leg.get("declared_trials_in_leg_family") or 1)
            inputs["deflated_sharpe_at_declared_trials"] = dsr.get("dsr", dsr)
        except Refused as exc:
            inputs["deflated_sharpe_at_declared_trials"] = f"not computable: {exc}"
        out["power_inputs_that_are_not_results"] = inputs
    return out


# ---------------------------------------------------------------------------
# Combined evaluation vs T-bills
# ---------------------------------------------------------------------------

def eval_combined(series: list, spec: dict) -> dict:
    n = len(series)
    minimum = spec["minimum_before_verdict"]["combined_settled_sessions"]
    out = {"settled_sessions": n, "minimum_before_verdict": minimum,
           "benchmark": spec["benchmark"]["definition"],
           "hurdle_pp_per_year": spec["benchmark"]["hurdle_to_count_pp_per_year"],
           "readable": n >= minimum,
           "verdict": ("NO VERDICT -- below the pre-registered combined minimum. Behaviour, not "
                       "evidence." if n < minimum else "MINIMUM MET -- read the combined gate.")}
    if n >= 1:
        eq_c, eq_b = 1.0, 1.0
        excess = []
        for _, rc, rb in series:
            eq_c *= (1.0 + rc)
            eq_b *= (1.0 + rb)
            excess.append(rc - rb)
        out["equity"] = {"combined": eq_c, "benchmark_tbills": eq_b}
        out["cumulative_return_pct"] = {"combined": (eq_c - 1) * 100, "benchmark_tbills": (eq_b - 1) * 100}
        out["inputs_that_are_not_results"] = {
            "DISCLAIMER": ("NOT RESULTS -- no annualisation or Sharpe is licensed before the "
                           f"{minimum}-session minimum. The combined gate is net excess > 0 at "
                           "t > 2.80 AND DSR >= 0.95 at the declared trial count, read only after "
                           "the minimum."),
            "mean_daily_excess_bp": (statistics.fmean(excess) * 1e4) if excess else None,
            "n_excess": len(excess)}
        if n >= 30:
            try:
                dsr = deflated_sharpe(excess, trials=spec["combined_gate"]["declared_trials_now"])
                out["inputs_that_are_not_results"]["combined_excess_dsr"] = dsr.get("dsr", dsr)
            except Refused as exc:
                out["inputs_that_are_not_results"]["combined_excess_dsr"] = f"n/a: {exc}"
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def evaluate(ledger_path: pathlib.Path = None) -> dict:
    spec = bf.frozen_spec()  # verifies the pre-registration hash; refuses if it moved
    records = [r for r in bf.read_ledger(ledger_path) if r.get("kind") == "session"]
    streams = leg_streams(records)
    legs = {lid: eval_leg(lid, streams[lid], spec) for lid in LEG_IDS
            if any(l["id"] == lid and l["status"] in ("ACTIVE", "ACTIVE_UNSIZED")
                   for l in spec["legs"])}
    combined = eval_combined(combined_series(records), spec)
    report = {
        "framing": FRAMING,
        "basket_id": spec["basket_id"],
        "freeze": {"utc": spec["frozen_utc"],
                   "preregistration_sha256": spec["preregistration_sha256"][:16], "verified": True},
        "active_legs": [l["id"] for l in spec["legs"] if l["status"] == "ACTIVE"],
        "unsized_loggers": [l["id"] for l in spec["legs"] if l["status"] == "ACTIVE_UNSIZED"],
        "pending_slots": [{"id": l["id"], "name": l["name"], "status": l["status"]}
                          for l in spec["legs"] if l["status"] == "PENDING_SPEC"],
        "runs_logged": len(records),
        "legs": legs,
        "combined_vs_tbills": combined,
        "kill_switch_rule": spec["kill_switch"],
        "claims_never_licensed": [
            "any leg or the basket makes money",
            "the basket beats T-bills (before the minimum)",
            "any Sharpe/CAGR/p-value computed before the minimum",
            "a calm stretch is evidence about a leg's edge",
            "this paper log is a reason to fund a live account (it places no orders and is owner-gated)"],
        "iteration_protocol": ("research/trading_bot/ITERATION_PROTOCOL.md -- a new idea is a SEPARATE "
                               "frozen forward test; nothing here may modify a running rule."),
    }
    report["status_line"] = status_line(report)
    return report


def status_line(report: dict) -> str:
    n = report["runs_logged"]
    parts = []
    for lid, leg in report["legs"].items():
        parts.append(f"{lid} n={leg['settled_observations']} {leg['kill_switch']['verdict'].split('--')[0].strip()}")
    comb = report["combined_vs_tbills"]
    return (f"BASKET1 PAPER-LOGGER (no orders) | runs {n} | " + " | ".join(parts)
            + f" | combined {comb['settled_sessions']}/{comb['minimum_before_verdict']} sessions "
            f"-> {comb['verdict'].split('--')[0].strip()}")


def render_text(rep: dict) -> str:
    L = []
    a = L.append
    a("=" * 78)
    a(f"BASKET FORWARD EVALUATION -- {rep['basket_id']}  (LOGGER, no orders, no real money)")
    a("=" * 78)
    a(rep["framing"])
    a("")
    a(f"  freeze sha256 (verified) : {rep['freeze']['preregistration_sha256']}...")
    a(f"  runs logged              : {rep['runs_logged']}")
    a(f"  active legs              : {rep['active_legs']}")
    a(f"  pending slots            : {[p['id'] for p in rep['pending_slots']]}")
    a("")
    for lid, leg in rep["legs"].items():
        a(f"-- LEG {lid}: {leg['name']} " + "-" * max(0, 50 - len(leg['name'])))
        a(f"   settled observations : {leg['settled_observations']}  "
          f"(kill needs n>={leg['minimum_before_verdict']})")
        a(f"   kill switch          : {leg['kill_switch']['verdict']}")
        pin = leg.get("power_inputs_that_are_not_results")
        if pin:
            a(f"   [not a result] mean {pin['mean_net_bp_per_obs']:+.3f} bp/obs, "
              f"t {pin['t_stat_per_obs']:+.2f}" if pin.get("t_stat_per_obs") is not None
              else "   [not a result] mean n/a")
        a(f"   prior (backtest)     : {leg['prior_verdict_backtest'][:96]}...")
        a("")
    c = rep["combined_vs_tbills"]
    a("-- COMBINED vs T-BILLS " + "-" * 54)
    a(f"   settled sessions      : {c['settled_sessions']} (minimum {c['minimum_before_verdict']})")
    a(f"   verdict               : {c['verdict']}")
    if c.get("cumulative_return_pct"):
        a(f"   [not a result] cum    : combined {c['cumulative_return_pct']['combined']:+.4f}% vs "
          f"T-bills {c['cumulative_return_pct']['benchmark_tbills']:+.4f}%")
    a("")
    a(rep["status_line"])
    return "\n".join(L)


def _selftest() -> int:
    spec = bf.frozen_spec()
    # synthetic ledger: T3 a steady loser past N_min (should kill), ETFRV a steady winner
    recs = []
    for i in range(45):
        d = f"2026-09-{i+1:02d}"
        wob = 0.0002 * (1 if i % 2 else -1)   # variance so Sharpe/DSR are defined
        recs.append({
            "kind": "session", "session_date": d,
            "legs": {"T3": {"settled_from_pending": {"settled": {"exit_session": d, "net_return": -0.0009 + wob}}},
                     "ETFRV": {"settled": {"exit_session": d, "net_return": 0.0006 + wob}}},
            "combined": {"r_combined_net": 0.0001 + wob, "r_benchmark": 0.00011}})
    streams = leg_streams(recs)
    t3 = eval_leg("T3", streams["T3"], spec)
    etf = eval_leg("ETFRV", streams["ETFRV"], spec)
    out = {"framing": FRAMING,
           "T3_kill": t3["kill_switch"]["verdict"], "ETFRV_kill": etf["kill_switch"]["verdict"],
           "combined": eval_combined(combined_series(recs), spec)["verdict"],
           "write_guard_fires": None}
    if not out["T3_kill"].startswith("DEAD"):
        raise Refused("evaluator failed to kill a steady net loser past N_min")
    if out["ETFRV_kill"].startswith("DEAD"):
        raise Refused("evaluator wrongly killed a steady net winner")
    try:
        _refuse_if_protected(bf.LEDGER_PATH)
    except Refused:
        out["write_guard_fires"] = True
    if not out["write_guard_fires"]:
        raise Refused("the read-only write guard did not fire on the ledger path")
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.trading_bot.basket_eval",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("report", help="the full read-only evaluation")
    r.add_argument("--json", action="store_true")
    r.add_argument("--ledger", default=None, help="evaluate an alternate ledger path (read-only)")
    sub.add_parser("status-line", help="one line for a dashboard")
    sub.add_parser("selftest", help="hermetic wiring check; no network, no ledger written")
    args = parser.parse_args(argv)
    if args.command == "selftest":
        return _selftest()
    ledger = pathlib.Path(args.ledger) if getattr(args, "ledger", None) else None
    rep = evaluate(ledger)
    if args.command == "status-line":
        sys.stdout.write(rep["status_line"] + "\n")
        return 0
    if getattr(args, "json", False):
        json.dump(rep, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(rep) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
