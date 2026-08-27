#!/usr/bin/env python3
"""CEFBOT -- the FROZEN strategy: CEF discount-LEVEL tilt, long widest-discount decile vs a
short broad-equity-index hedge. Paper / hypothetical only.

Frozen rule: research/trading_bot/cefbot/CEFBOT_PREREGISTRATION.md
             sha256 4e2cdbcfe2375525e192292093b2d22a15dc3902bb40967f5da3c8e347b8c2b6

Nothing in this module is tunable at run time. Every constant below is a quotation of a clause in
the pre-registration, and `assert_frozen()` refuses to let the bot run if that document has moved
since the freeze. This is the T12 discipline (`scripts/t12_evaluate.py`) applied to a forward bot.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.trading_bot.frozen import Refused  # noqa: E402

# --- paths -----------------------------------------------------------------
PKG = pathlib.Path(__file__).resolve().parent
DOCS = ROOT / "research" / "trading_bot" / "cefbot"
PREREG = DOCS / "CEFBOT_PREREGISTRATION.md"
PREREG_SHA = "4e2cdbcfe2375525e192292093b2d22a15dc3902bb40967f5da3c8e347b8c2b6"
LOG = DOCS / "CEFBOT_LOG.jsonl"
STATE = DOCS / "CEFBOT_STATE.json"
SNAP_CACHE = ROOT / "research" / "data" / "cefbot_cache" / "snapshots"

# --- the frozen rule (pre-registration section 2) --------------------------
DECILE = 0.10                 # 2d: widest-discount decile
PRICE_MIN = 5.0               # 2b.2
BETA_H = 0.50                 # 2e: FROZEN, unfitted market-hedge ratio
HEDGE_SYMBOL = "SPY"          # 2e: one deep, easy-to-borrow index ETF -- never individual CEFs
HOLD_WEEKS = 1                # 2f
REBAL_MIN_SESSIONS = 5        # 2f: >= 5 trading sessions between rebalances
WEEKS_PER_YEAR = 52

# --- costs (pre-registration section 4), all in bp of the leg's notional ---
CEF_HALF_SPREAD_BP = 11.53    # T12 first-party measured median
SPY_HALF_SPREAD_BP = 0.116    # programme measured SPY half-spread
SEC31_BP = 0.278              # of sale notional
TAF_PER_SHARE = 0.000166      # $/share sold
SPY_BORROW_ANNUAL_BP = 33.0   # ETB general-collateral floor

# --- benchmarks (pre-registration section 3) -------------------------------
BENCH_TBILL_ANNUAL = 0.043    # refreshable input (current ~3M T-bill); default 4.30%/yr
BENCH_ALPHA_ANNUAL = 0.01     # FROZEN +1.00 pp/yr hurdle

# --- gates / kill rule (pre-registration section 6) ------------------------
VERDICT_MIN_N = 123           # programme power floor before SURVIVES is even readable
KILL_MIN_N = 26               # a significant negative is killable this early
KILL_T = -2.0                 # ... if t_net <= -2.0 with cumulative net < 0
DRAWDOWN_HALT = 0.25          # realised peak-to-trough >= 25% -> HALT

CEF_HOST = "https://www.cefconnect.com"
CEF_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research/1.0",
          "Accept": "application/json"}


def assert_frozen() -> None:
    """Refuse to run against a moved target (T12 discipline)."""
    got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if got != PREREG_SHA:
        raise Refused(
            f"CEFBOT pre-registration hash mismatch: {got} != {PREREG_SHA}. The frozen rule has "
            "changed since the freeze; refusing to trade against a rule that moved. Restore the "
            "document -- never update the hash (ITERATION_PROTOCOL.md forbidden move #7)."
        )


def eligible(rows: list) -> list:
    """(ticker, discount_pct, price) for every fund passing section 2b, unsorted."""
    out = []
    for r in rows:
        t = r.get("Ticker")
        disc = r.get("Discount")
        nav = r.get("NAV")
        px = r.get("Price")
        if not t or disc is None or nav is None or px is None:
            continue
        if float(nav) <= 0 or float(px) <= PRICE_MIN:
            continue
        out.append((t, float(disc), float(px)))
    return out


def long_book(rows: list) -> dict:
    """Section 2c-2d: rank eligible funds ascending on discount LEVEL, LONG the widest decile.

    Returns the equal-weight long book AND the whole eligible universe (the buy-and-hold null),
    each as {ticker: entry_price}. No return is computed here -- this is signal + prices only.
    """
    cand = eligible(rows)
    if len(cand) < 20:
        raise Refused(f"only {len(cand)} eligible CEFs; refusing to form a decile below 20")
    cand.sort(key=lambda x: x[1])            # most-negative discount (widest) first
    n_long = max(1, round(len(cand) * DECILE))
    longs = {t: p for t, _d, p in cand[:n_long]}
    universe = {t: p for t, _d, p in cand}
    widest = [(t, d) for t, d, _p in cand[:n_long]]
    return {"long": longs, "universe": universe, "n_universe": len(cand),
            "n_long": n_long, "widest": widest}
