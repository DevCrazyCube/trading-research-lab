#!/usr/bin/env python3
"""MEMEBOT CLI -- the fast, light, reactive PAPER memecoin bot (TWO parallel frozen variants).

    python -m scripts.trading_bot.memebot selftest         # hermetic wiring check, NO network
    python -m scripts.trading_bot.memebot listen [--seconds N]  # official Pump events via Helius
    python -m scripts.trading_bot.memebot feed [--limit N] # the eyes: today's free new-coin stream
    python -m scripts.trading_bot.memebot scan             # screen the feed, open frozen paper entries
    python -m scripts.trading_bot.memebot track            # refresh + resolve open paper positions
    python -m scripts.trading_bot.memebot run [--cycles N --interval S]   # track+scan (optional loop)
    python -m scripts.trading_bot.memebot positions        # list open paper positions (both variants)
    python -m scripts.trading_bot.memebot score            # honest expectancy scorecard (both variants)
    python -m scripts.trading_bot.memebot status           # one dashboard line per variant

Two frozen instruments run in parallel on the SAME live coins: MEMEBOT1 (180-min horizon) and
MEMEBOT_FAST (~25-min horizon + dead-coin early exit). Placing NO orders, holding NO wallet, touching
NO real SOL, writing NOTHING on-chain. Free keyless data only. The PumpPortal `listen` stream opens ONLY
the read-only data websocket -- no trading endpoint is reachable. Real trading is a SEPARATE,
owner-gated wallet decision, not reachable from here.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import Refused
from .frozen import frozen_spec, active_specs, FRAMING
from . import feed, screen as screen_mod, bot, ledger, scoring, ws_data


def _dump(obj) -> int:
    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_feed(spec, args) -> int:
    coins = feed.read_new_pools(spec, pages=args.pages)
    rows = []
    for c in coins[: args.limit]:
        res = screen_mod.screen_coin(c, spec)
        rows.append({"name": c["name"], "dex": c["dex"], "fdv_usd": c["fdv_usd"],
                     "reserve_usd": c["reserve_usd"], "buyers": c["buyers"], "buys": c["buys"],
                     "sellers": c["sellers"], "age_min": round(c["age_minutes"], 1)
                     if c["age_minutes"] is not None else None,
                     "verdict": res["verdict"], "reasons": res["reasons"]})
    return _dump({"pulled": len(coins), "shown": len(rows),
                  "pumpportal_buffered": len(ws_data.read_buffer()), "coins": rows})


def cmd_listen(spec, args) -> int:
    # PumpPortal IP-banned us (403 on the whole domain, 2026-09-02). The tape now comes from the pump.fun
    # program's own on-chain anchor events via our FUNDED Helius logsSubscribe (helius_tape), written into
    # the SAME hash-chained buffers so every downstream consumer is unchanged. See helius_tape.py.
    from . import helius_tape
    summary = helius_tape.run_listener(seconds=args.seconds)
    return _dump(summary)


def cmd_scan(spec, args) -> int:
    return _dump(bot.scan_once(active_specs(), pages=args.pages))


def cmd_track(spec, args) -> int:
    return _dump(bot.track_once(active_specs()))


def cmd_run(spec, args) -> int:
    specs = active_specs()
    if args.cycles <= 1:
        return _dump(bot.run_cycle(specs, pages=args.pages))
    return _dump(bot.run_loop(specs, cycles=args.cycles, interval_s=args.interval, pages=args.pages))


def cmd_positions(spec, args) -> int:
    out = {}
    for sp in active_specs():
        op = ledger.open_positions(sp)
        # Read the SAME open_positions() source `status` counts, and use .get() throughout so ONE
        # malformed/legacy entry can never crash the whole command into an apparent "0 positions"
        # while `status` still reports the real open count -- the two must never disagree.
        out[sp["instrument_id"]] = {
            "open_positions": len(op),
            "positions": [{"name": s.get("name"), "pool_address": s.get("pool_address"),
                           "control": s.get("control"), "entry_price_usd": s.get("entry_price_usd"),
                           "stop_price_usd": s.get("stop_price_usd"),
                           "target_price_usd": s.get("target_price_usd"), "size_sol": s.get("size_sol"),
                           "horizon_minutes": s.get("horizon_minutes"),
                           "dead_exit": s.get("dead_exit"), "decided_utc": s.get("decided_utc")}
                          for s in op]}
    return _dump(out)


def cmd_score(spec, args) -> int:
    out = {}
    for sp in active_specs():
        ledger.verify_entry_hashes(ledger.read_entries(sp))
        report = scoring.score(sp, ledger.resolved_r_stream(sp))
        report["open_positions"] = len(ledger.open_positions(sp))
        report["entries_logged"] = len(ledger.read_entries(sp))
        out[sp["instrument_id"]] = report
    return _dump(out)


def cmd_status(spec, args) -> int:
    for sp in active_specs():
        report = scoring.score(sp, ledger.resolved_r_stream(sp))
        sys.stdout.write(report["status_line"] + f" | open {len(ledger.open_positions(sp))}\n")
    return 0


def cmd_selftest(spec, args) -> int:
    from .selftest import run_selftest
    return run_selftest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="scripts.trading_bot.memebot",
                                description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("feed", help="pull today's free new-coin stream (with screen verdicts)")
    f.add_argument("--limit", type=int, default=40)
    f.add_argument("--pages", type=int, default=1)
    ln = sub.add_parser("listen", help="official Pump event stream via Helius (read-only websocket)")
    ln.add_argument("--seconds", type=float, default=None,
                    help="bounded test duration; omit to run until interrupted (detached mode)")
    sc = sub.add_parser("scan", help="screen the feed and open frozen paper entries (both variants)")
    sc.add_argument("--pages", type=int, default=1)
    sub.add_parser("track", help="refresh + resolve open paper positions (both variants)")
    r = sub.add_parser("run", help="one reactive cycle (track+scan); optional bounded loop")
    r.add_argument("--cycles", type=int, default=1)
    r.add_argument("--interval", type=float, default=90.0, help="seconds between cycles")
    r.add_argument("--pages", type=int, default=1)
    sub.add_parser("positions", help="list open paper positions (both variants)")
    sub.add_parser("score", help="honest expectancy scorecard, both variants (read-only)")
    sub.add_parser("status", help="one dashboard line per variant")
    sub.add_parser("selftest", help="hermetic wiring check; no network")
    args = p.parse_args(argv)

    # `listen` and `feed` use the base spec only; the rest fan out over every active variant.
    spec = frozen_spec("MEMEBOT1")
    dispatch = {"feed": cmd_feed, "listen": cmd_listen, "scan": cmd_scan, "track": cmd_track,
                "run": cmd_run, "positions": cmd_positions, "score": cmd_score, "status": cmd_status,
                "selftest": cmd_selftest}
    return dispatch[args.command](spec, args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
