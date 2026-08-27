#!/usr/bin/env python3
"""MEMEBOT_EVO CLI -- an evolutionary variant engine for the paper memecoin bot.

    python -m scripts.trading_bot.memebot_evo selftest        # hermetic wiring + K-bar demo, NO network
    python -m scripts.trading_bot.memebot_evo seed [--size N] # create the initial population (once)
    python -m scripts.trading_bot.memebot_evo scan            # open frozen paper entries (all genomes)
    python -m scripts.trading_bot.memebot_evo track           # refresh + resolve open positions
    python -m scripts.trading_bot.memebot_evo evolve [--cycles N]  # accumulate + one selection generation
    python -m scripts.trading_bot.memebot_evo status          # population + K-corrected bar (read-only)

PAPER ONLY: no orders, no wallet, no SOL, no on-chain writes -- reuses the memebot's free/keyless feed
and deterministic screen READ-ONLY. Forward-selected, multiple-testing-bounded (sqrt(2 ln K) noise bar),
CPU-only, no GPU, no neural net. Continuous evolution is a DETACHED subprocess (evolve_loop.sh); `evolve
--cycles N` is a bounded in-process run. Real trading is a SEPARATE, owner-gated wallet decision.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import Refused
from . import engine


def _dump(obj) -> int:
    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="scripts.trading_bot.memebot_evo",
                                description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="hermetic wiring + K-bar demo; no network")
    se = sub.add_parser("seed", help="create the initial population (refuses to clobber a running one)")
    se.add_argument("--size", type=int, default=engine.POP_SIZE)
    ex = sub.add_parser("extend", help="inject adaptive-exit vol genomes into the live population "
                                       "IN PLACE (preserves accumulated trades)")
    ex.add_argument("--n-random-vol", type=int, default=3,
                    help="fresh random genomes forced to use_vol_exits=1, on top of VOL_TIGHT/VOL_WIDE")
    exs = sub.add_parser("extend-subminute", help="inject the SUB-MINUTE (tick-resolved) seconds-scale "
                                                  "genomes into the live population IN PLACE (preserves "
                                                  "accumulated trades)")
    exs.add_argument("--n-random-sub", type=int, default=3,
                     help="fresh random genomes forced to use_subminute=1, on top of the 4 SUBMIN_* seeds")
    exm = sub.add_parser("extend-momentum", help="inject the MOMENTUM-ENTRY SCALP genomes (only buy "
                                                 "what is pumping) into the live population IN PLACE "
                                                 "(preserves accumulated trades)")
    exm.add_argument("--n-random-momo", type=int, default=3,
                     help="fresh random genomes forced to use_momentum_entry=1, on top of the 4 MOMO_* seeds")
    sub.add_parser("subminute-report", help="tick-data availability honesty metric for sub-minute genomes")
    sc = sub.add_parser("scan", help="open frozen paper entries across the whole population")
    sc.add_argument("--pages", type=int, default=1)
    sub.add_parser("track", help="refresh + resolve open paper positions")
    ev = sub.add_parser("evolve", help="accumulate forward trades + one selection generation")
    ev.add_argument("--cycles", type=int, default=1, help="live scan/track cycles before selection")
    ev.add_argument("--pages", type=int, default=1)
    ev.add_argument("--offline", action="store_true", help="skip live cycles; just re-select + report")
    sub.add_parser("status", help="population + current K-corrected noise bar (read-only)")
    args = p.parse_args(argv)

    if args.command == "selftest":
        from .selftest import run_selftest
        return run_selftest()
    if args.command == "seed":
        return _dump(engine.seed(size=args.size))
    if args.command == "extend":
        return _dump(engine.extend_population(n_random_vol=args.n_random_vol))
    if args.command == "extend-subminute":
        return _dump(engine.extend_subminute(n_random_sub=args.n_random_sub))
    if args.command == "extend-momentum":
        return _dump(engine.extend_momentum(n_random_momo=args.n_random_momo))
    if args.command == "subminute-report":
        return _dump(engine.subminute_report())
    if args.command == "scan":
        pop, state = engine.load_pop(), engine.load_state()
        out = engine.scan_once(pop, state, pages=args.pages)
        engine.save_state(state)
        return _dump(out)
    if args.command == "track":
        pop, state = engine.load_pop(), engine.load_state()
        out = engine.track_once(pop, state)
        engine.save_state(state)
        return _dump(out)
    if args.command == "evolve":
        return _dump(engine.evolve_generation(cycles=args.cycles, pages=args.pages,
                                              live=not args.offline))
    if args.command == "status":
        return _dump(engine.status())
    p.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
