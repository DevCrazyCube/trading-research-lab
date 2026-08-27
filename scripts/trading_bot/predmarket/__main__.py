#!/usr/bin/env python3
"""PREDMARKET CLI -- the agent-driven prediction-market forward CALIBRATION tracker.

    python -m scripts.trading_bot.predmarket selftest          # hermetic wiring check, no network
    python -m scripts.trading_bot.predmarket pull              # OPEN politics markets + live p_market
    python -m scripts.trading_bot.predmarket propose FILE.json # validate+freeze+log agent estimates
    python -m scripts.trading_bot.predmarket propose --no-trade "reason"   # log a disciplined abstention
    python -m scripts.trading_bot.predmarket resolve           # settle open estimates (official outcomes)
    python -m scripts.trading_bot.predmarket score             # Brier-vs-market scorecard (read-only)
    python -m scripts.trading_bot.predmarket status            # one dashboard line

Placing NO bets, holding NO position, touching NO account, wallet or real money. Free keyless data only.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import Refused
from .frozen import frozen_spec, FRAMING
from . import venues, proposer, ledger, resolve as resolver, scoring


def cmd_pull(spec, args) -> int:
    pulled = venues.pull_open_markets(spec, min_volume=args.min_volume, poly_limit=args.poly_limit)
    sel = [m for m in pulled["markets"] if m["selectable"]]
    sel.sort(key=lambda m: (m.get("volume") or 0), reverse=True)
    digest = {"pulled_utc": pulled["pulled_utc"], "n_markets": pulled["n_markets"],
              "n_selectable": pulled["n_selectable"], "errors": pulled["errors"],
              "markets": sel[:args.limit]}
    json.dump(digest, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_propose(spec, args) -> int:
    if args.no_trade is not None:
        rec = proposer.no_trade_record(args.no_trade)
        ledger.append_preregistration(rec)
        json.dump({"logged": "no_trade", "record": rec}, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0
    raw_list = json.loads(open(args.file).read())
    if isinstance(raw_list, dict):
        raw_list = [raw_list]
    frozen, rejected = [], []
    for raw in raw_list:
        try:
            validated = proposer.validate_estimate(raw, spec)
            est = proposer.freeze_estimate(validated)
            ledger.append_preregistration(dict(est, kind="estimate"))
            frozen.append({"venue": est["venue"], "market_id": est["market_id"],
                           "p_market": est["p_market"], "q_agent": est["q_agent"],
                           "abs_edge": est["abs_edge"], "round_trip_cost": est["round_trip_cost"],
                           "hypothetical_side": est["hypothetical_side"],
                           "estimate_sha256": est["estimate_sha256"],
                           "proposed_utc": est["proposed_utc"]})
        except Refused as exc:
            rejected.append({"raw": {k: raw.get(k) for k in ("venue", "market_id", "question")},
                             "refused": str(exc)})
    json.dump({"framing": FRAMING, "frozen": frozen, "rejected": rejected,
               "now_open": len(ledger.open_estimates())}, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_resolve(spec, args) -> int:
    ledger.verify_preregistration_hashes(ledger.read_preregistrations())
    state = ledger.load_state(spec)
    open_es = ledger.open_estimates()
    results = []
    for est in open_es:
        try:
            rec = resolver.resolve_estimate(est, spec)
        except Refused as exc:
            rec = {"kind": "resolution", "status": "ERROR", "estimate_sha256": est["estimate_sha256"],
                   "venue": est["venue"], "market_id": est["market_id"], "refused": str(exc)}
        if rec.get("status") == "RESOLVED":
            ledger.append_resolution(rec)
            if est["estimate_sha256"] not in state["resolved_estimate_hashes"]:
                state["resolved_estimate_hashes"].append(est["estimate_sha256"])
        results.append({"market_id": rec["market_id"], "status": rec["status"],
                        "yes_outcome": rec.get("yes_outcome"),
                        "brier_agent": rec.get("brier_agent"), "brier_market": rec.get("brier_market"),
                        "note": rec.get("note") or rec.get("refused")})
    ledger.save_state(state)
    json.dump({"framing": FRAMING, "n_open_before": len(open_es), "results": results},
              sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_score(spec, args) -> int:
    ledger.verify_preregistration_hashes(ledger.read_preregistrations())
    report = scoring.score(spec, ledger.resolved_stream())
    report["open_estimates"] = len(ledger.open_estimates())
    report["preregistrations_logged"] = len(ledger.read_preregistrations())
    json.dump(report, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_status(spec, args) -> int:
    report = scoring.score(spec, ledger.resolved_stream())
    sys.stdout.write(report["status_line"] + f" | open {len(ledger.open_estimates())}\n")
    return 0


def cmd_selftest(spec, args) -> int:
    from .selftest import run_selftest
    return run_selftest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="scripts.trading_bot.predmarket",
                                description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    pl = sub.add_parser("pull", help="pull OPEN politics markets + live implied probability")
    pl.add_argument("--limit", type=int, default=40)
    pl.add_argument("--min-volume", type=float, default=0.0, dest="min_volume")
    pl.add_argument("--poly-limit", type=int, default=40, dest="poly_limit")
    pr = sub.add_parser("propose", help="validate+freeze+log agent estimates (or an abstention)")
    pr.add_argument("file", nargs="?", default=None, help="JSON file of raw estimates")
    pr.add_argument("--no-trade", default=None, help="log a disciplined abstention with this reason")
    sub.add_parser("resolve", help="settle open estimates against official outcomes")
    sub.add_parser("score", help="Brier-vs-market calibration scorecard (read-only)")
    sub.add_parser("status", help="one dashboard line")
    sub.add_parser("selftest", help="hermetic wiring check; no network")
    args = p.parse_args(argv)

    spec = frozen_spec()
    dispatch = {"pull": cmd_pull, "propose": cmd_propose, "resolve": cmd_resolve,
                "score": cmd_score, "status": cmd_status, "selftest": cmd_selftest}
    if args.command == "propose" and args.file is None and args.no_trade is None:
        p.error("propose needs either a JSON file or --no-trade REASON")
    return dispatch[args.command](spec, args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
