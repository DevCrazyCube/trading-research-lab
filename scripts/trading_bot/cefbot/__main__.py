#!/usr/bin/env python3
"""CEFBOT command line. PAPER ONLY -- no command here can place a real order or spend real money.

    python -m scripts.trading_bot.cefbot selftest    # hermetic: freeze check + engine proof, no ledger write
    python -m scripts.trading_bot.cefbot show         # today's target widest-discount basket (no commit)
    python -m scripts.trading_bot.cefbot run          # advance one weekly cycle (fetch, settle, enter, log)
    python -m scripts.trading_bot.cefbot run-dry       # same, but compute-only: no state/ledger write
    python -m scripts.trading_bot.cefbot evaluate      # the read-only scorecard + verdict
    python -m scripts.trading_bot.cefbot evaluate-json # ... as JSON
    python -m scripts.trading_bot.cefbot proof         # engine replay on cached history (NOT ledger evidence)
    python -m scripts.trading_bot.cefbot status        # one-line status
"""

from __future__ import annotations

import json
import sys

from scripts.trading_bot.cefbot import bot, evaluate as E, strategy as G


def _selftest() -> int:
    G.assert_frozen()
    print(f"[ok] pre-registration frozen: sha256 {G.PREREG_SHA[:16]}...")
    print(f"[ok] frozen rule: decile {G.DECILE}, price>${G.PRICE_MIN}, hedge SHORT "
          f"{G.HEDGE_SYMBOL} beta_h={G.BETA_H}, hold {G.HOLD_WEEKS}wk, weekly cadence")
    pr = bot.proof()
    a = pr["mean_cross_sectional_alpha_bp_per_wk"]
    print(f"[ok] engine proof (cached, NOT ledger evidence): cross-sectional alpha "
          f"{a:+.2f} bp/wk over {pr['n_weekly_obs']} weekly obs, t {pr['t_stat']:+.2f}")
    print(f"     {pr['NOT_LEDGER_EVIDENCE']}")
    print("[ok] selftest passed -- no network, no order, no ledger write.")
    return 0


def main(argv) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "selftest":
        return _selftest()
    if cmd == "show":
        print(json.dumps(bot.peek_first_basket(), indent=2, default=str))
        return 0
    if cmd == "proof":
        print(json.dumps(bot.proof(), indent=2, default=str))
        return 0
    if cmd in ("run", "run-dry"):
        row = bot.run_cycle(dry_run=(cmd == "run-dry"))
        print(json.dumps(row, indent=2, default=str))
        return 0
    if cmd == "evaluate":
        print(E.report())
        return 0
    if cmd == "evaluate-json":
        print(E.report(as_json=True))
        return 0
    if cmd == "status":
        st = bot.load_state()
        settled = E.read_settled()
        print(f"CEFBOT [{st['status']}] inception={st['inception']} "
              f"last_rebalance={st['last_rebalance']} open_book={bool(st['open_book'])} "
              f"settled_obs={len(settled)}  (PAPER; no real orders)")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
