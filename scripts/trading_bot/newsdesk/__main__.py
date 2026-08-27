#!/usr/bin/env python3
"""NEWSDESK CLI -- the agent-driven read-the-world forward paper logger.

    python -m scripts.trading_bot.newsdesk selftest            # hermetic wiring check, no network
    python -m scripts.trading_bot.newsdesk read                # pull today's free event stream (eyes)
    python -m scripts.trading_bot.newsdesk spot SPY AAPL BTC   # current free prices (to size a setup)
    python -m scripts.trading_bot.newsdesk propose FILE.json   # validate+freeze+log agent proposals
    python -m scripts.trading_bot.newsdesk propose --no-trade "reason"   # log the disciplined abstention
    python -m scripts.trading_bot.newsdesk resolve             # mark open setups to realised prices
    python -m scripts.trading_bot.newsdesk score               # honest expectancy scorecard (read-only)
    python -m scripts.trading_bot.newsdesk status              # one dashboard line

Placing NO orders, holding NO position, touching NO account or real money. Free keyless data only.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import Refused
from .frozen import frozen_spec, FRAMING
from . import world_reader, proposer, ledger, resolve as resolver, scoring, prices


def cmd_read(spec, args) -> int:
    stream = world_reader.read_world(spec)
    # Print a compact digest (full event bodies are large); cache nothing to the ledger (eyes only).
    digest = {"pulled_utc": stream["pulled_utc"], "feed_counts": stream["feed_counts"],
              "feed_errors": stream["feed_errors"], "n_events": stream["n_events"],
              "events": stream["events"][:args.limit]}
    json.dump(digest, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_spot(spec, args) -> int:
    out = {}
    for token in args.symbols:
        # Probe the frozen universes: an equity-watchlist ticker is equity, otherwise treat as crypto.
        ac = "equity" if token in spec["equity_watchlist"] else "crypto"
        try:
            iid = proposer._known_instrument(token, ac, spec)
            px = prices.spot_price({"asset_class": ac, "instrument": iid}, spec)
            out[token] = {"asset_class": ac, "instrument": iid, "spot_usd": px}
        except Refused as exc:
            out[token] = {"error": str(exc)}
    json.dump(out, sys.stdout, indent=2, default=str)
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
    n_open = len(ledger.open_setups())
    frozen, rejected = [], []
    for raw in raw_list:
        try:
            validated = proposer.validate_setup(raw, spec, n_open=n_open)
            setup = proposer.freeze_setup(validated)
            record = dict(setup, kind="setup")
            ledger.append_preregistration(record)
            n_open += 1
            frozen.append({"instrument": setup["instrument"], "direction": setup["direction"],
                           "reward_to_risk": setup["reward_to_risk"],
                           "setup_sha256": setup["setup_sha256"],
                           "proposed_utc": setup["proposed_utc"]})
        except Refused as exc:
            rejected.append({"raw": raw, "refused": str(exc)})
    json.dump({"framing": FRAMING, "frozen": frozen, "rejected": rejected,
               "now_open": n_open}, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_resolve(spec, args) -> int:
    ledger.verify_preregistration_hashes(ledger.read_preregistrations())
    state = ledger.load_state(spec)
    open_ss = ledger.open_setups()
    results = []
    for setup in open_ss:
        try:
            rec = resolver.resolve_setup(setup, spec)
        except Refused as exc:
            rec = {"kind": "resolution", "status": "ERROR", "setup_sha256": setup["setup_sha256"],
                   "instrument": setup["instrument"], "refused": str(exc)}
        if rec.get("status") == "RESOLVED":
            ledger.append_resolution(rec)
            if setup["setup_sha256"] not in state["resolved_setup_hashes"]:
                state["resolved_setup_hashes"].append(setup["setup_sha256"])
        results.append({"instrument": rec["instrument"], "status": rec["status"],
                        "realized_r": rec.get("realized_r"),
                        "reason": rec.get("resolution_reason") or rec.get("note") or rec.get("refused"),
                        "null_r": rec.get("null_realized_r")})
    ledger.save_state(state)
    json.dump({"framing": FRAMING, "n_open_before": len(open_ss), "results": results},
              sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_score(spec, args) -> int:
    ledger.verify_preregistration_hashes(ledger.read_preregistrations())
    report = scoring.score(spec, ledger.resolved_r_stream())
    report["open_setups"] = len(ledger.open_setups())
    report["preregistrations_logged"] = len(ledger.read_preregistrations())
    json.dump(report, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_status(spec, args) -> int:
    report = scoring.score(spec, ledger.resolved_r_stream())
    sys.stdout.write(report["status_line"] + f" | open {len(ledger.open_setups())}\n")
    return 0


def cmd_selftest(spec, args) -> int:
    from .selftest import run_selftest
    return run_selftest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="scripts.trading_bot.newsdesk",
                                description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("read", help="pull today's free event stream")
    r.add_argument("--limit", type=int, default=60)
    sp = sub.add_parser("spot", help="current free prices for sizing")
    sp.add_argument("symbols", nargs="+")
    pr = sub.add_parser("propose", help="validate+freeze+log agent proposals (or an abstention)")
    pr.add_argument("file", nargs="?", default=None, help="JSON file of raw proposals")
    pr.add_argument("--no-trade", default=None, help="log a disciplined abstention with this reason")
    sub.add_parser("resolve", help="mark open setups to realised prices")
    sub.add_parser("score", help="honest expectancy scorecard (read-only)")
    sub.add_parser("status", help="one dashboard line")
    sub.add_parser("selftest", help="hermetic wiring check; no network")
    args = p.parse_args(argv)

    spec = frozen_spec()
    dispatch = {"read": cmd_read, "spot": cmd_spot, "propose": cmd_propose, "resolve": cmd_resolve,
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
