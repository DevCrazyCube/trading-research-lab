#!/usr/bin/env python3
"""memestream CLI.

    python -m scripts.trading_bot.memestream listen [--seconds N] [--pool P]  # ingestion loop (detach!)
    python -m scripts.trading_bot.memestream holdings                         # list held pools
    python -m scripts.trading_bot.memestream verify [--seconds N]             # short live ingest + sample
    python -m scripts.trading_bot.memestream sample [--pool P] [--tf 1s]      # print cached candles+flow

The long-lived ``listen`` MUST run detached (setsid nohup ...), never inline in an agent turn.
"""

from __future__ import annotations

import json
import sys

from . import candles, ingest, sources


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def cmd_holdings() -> int:
    held = sources.read_holdings()
    print(f"{len(held)} held pool(s):")
    for h in held:
        print(f"  {h['pool']}  mint={h.get('mint')}  {h.get('name')}")
    return 0


def cmd_sample(argv) -> int:
    pool = _arg(argv, "--pool")
    tf = _arg(argv, "--tf", "1s")
    pools = [pool] if pool else candles.cached_pools()
    if not pools:
        print("no candle cache yet -- run 'listen' or 'verify' first")
        return 0
    for p in pools:
        cs = candles.get_candles(p, timeframe=tf, lookback_secs=600)
        flow = candles.get_flow(p, window_secs=120)
        print(f"\n== {p} == {len(cs)} {tf} candle(s)")
        for c in cs[-5:]:
            print("   ", json.dumps(c))
        print("   flow(120s):", json.dumps(flow))
    return 0


def cmd_verify(argv) -> int:
    secs = float(_arg(argv, "--seconds", "70"))
    print(f"live verify: ingesting held pools for {secs:.0f}s ...")
    summary = ingest.run(seconds=secs, holdings_refresh_secs=1e9)
    print("ingest summary:", json.dumps(summary))
    pools = candles.cached_pools()
    print(f"\ncached pools now: {len(pools)}")
    # show the most active cached pool
    best = None
    for p in pools:
        f = candles.get_flow(p, window_secs=3600)
        if best is None or f["trades"] > best[1]["trades"]:
            best = (p, f)
    if best:
        p, _ = best
        cs = candles.get_candles(p, timeframe="1s", lookback_secs=3600)
        print(f"\nmost active pool {p}: {len(cs)} 1s candles")
        for c in cs[-8:]:
            print("   ", json.dumps(c))
        print("   get_flow(60s): ", json.dumps(candles.get_flow(p, window_secs=60)))
        print("   get_candles(5s):", json.dumps(candles.get_candles(p, "5s", lookback_secs=3600)[-3:]))
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "listen":
        return ingest.main(rest)
    if cmd == "holdings":
        return cmd_holdings()
    if cmd == "verify":
        return cmd_verify(rest)
    if cmd == "sample":
        return cmd_sample(rest)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
