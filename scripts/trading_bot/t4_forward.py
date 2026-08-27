#!/usr/bin/env python3
"""T4 -- the paper forward test of the T13 volatility-targeting overlay.

WHAT THIS IS, AND WHAT IT IS NOT
================================
This is **not a validated money-maker and this file may not be read as one.** It is the
instrument T13 said was the only honest next step for the one thread that programme left
standing.

T13 froze two risk-shaping families on 1929-1989 and tested them on 1990-2026.
**Both are dead on the frozen gate** (`research/trading_bot/T13_RESULT.md`). The volatility
overlay's headline `+7.25 pp` of drawdown against the ex-post vol-matched buy-and-hold null
carries `p = 0.233` and `DSR = 0.355`; it fails G1's significance half and G5 outright.
What survived was **behaviour, not statistics**: the sign is positive in all four decades and
all eight declared configurations, it is cheap (0.86 round trips/yr), and it is structurally
motivated. What killed it is **power**: a drawdown claim gets one observation per *crash*, the
held-out window contained three usable ones, and the `+7.25 pp` is essentially 2008 alone.

**1990-2026 is burned for this rule.** It cannot be re-run on history without re-using the
window that produced the number. So the only remaining honest instrument is a **prospective**
test, and this bot is that test: it runs the frozen rule forward, on a PAPER account, and
accrues a log. **The log is the evidence. It is not yet evidence of anything.**

At one crash per nine years, three usable crash observations is a ~27-year commitment. That
is stated here rather than buried, because a forward test whose horizon is not stated reads
after six months as though six months were the horizon. See
`research/trading_bot/T4_FORWARD_PREREGISTRATION.md` for the decision rule and for the list of
claims this log is NOT allowed to support.

THE RULE, WHICH IS LOADED AND NEVER RETYPED
===========================================
`w = min(w_max, target / realised_vol_L)`, `L = 60`, `target = 0.10`/yr, `w_max = 1.0`,
realised vol = annualised stdev of the last L daily simple returns. The parameters are read
from `research/trading_bot/T13_FROZEN_CONFIG.json`, whose `preregistration_sha256` is verified
against `T13_PREREGISTRATION.md` at load time -- a rule that can be edited is not frozen.

The arithmetic itself is **imported from `scripts/t13_risk_shaping.py`** (`vol_exposure`), the
same function that produced the held-out result, and then **cross-checked against an
independent recomputation in this file**. A disagreement refuses. Two implementations that
agree are a weak proof; one implementation is no proof at all.

TIMING (T13-L1), AND WHY THE LIVE SCHEDULE MATCHES IT EXACTLY
=============================================================
T13-L1: the exposure applied to the close-to-close return of day `t` uses closes through
`t-2` only. The live schedule that reproduces this without a single line of special-casing:

    run during session D, in the final minutes before the bell
      -> the newest close available is close(D-1)
      -> compute w from the 60 returns ending at close(D-1)
      -> place a MARKET order, so the weight is established at ~close(D)
      -> that weight earns the return of session D+1, i.e. close(D) -> close(D+1)
      -> and (D+1) - 2 = D-1.  T13-L1 holds by construction, not by assertion.

The bot therefore cannot front-run its own signal: the close that sets the weight has already
printed when the order is decided, and the fill happens at the end of a later session.

EXECUTION AND COST -- AND WHY THE MECHANISM CHANGED ON 2026-08-18
=================================================================
**The original design placed a market-on-close order (`time_in_force = "cls"`), and on the
Alpaca PAPER account that order does not execute: it EXPIRES.** This was not a modelling
assumption, it was measured on the live paper account. The T4 bot submitted a 93-share SPY
`tif=cls` BUY at 2026-08-17T13:50:54Z; at 2026-08-17T20:00:56Z, the close, the broker returned
`status="expired"`, `filled_qty=0`, `filled_avg_price=null`. Alpaca's paper simulator does not
participate in the closing auction. A forward test whose every order expires accrues nothing,
so the mechanism -- and ONLY the mechanism -- was changed.

**What replaced it:** a plain `type="market", time_in_force="day"` order submitted inside
`ACTION_WINDOW_ET`, the last few minutes of the regular session. A market DAY order fills
immediately against the paper simulator's book while the market is open. The weight is
therefore established a few minutes BEFORE the closing print rather than IN it.

**The rule did not change.** The target weight, the reference close, the sizing arithmetic and
the whole-share rounding are byte-identical to what the MOC version computed; only the order
type and the minute it is sent moved. See `ACTION_WINDOW_ET` and `place_near_close_market`.

**The cost consequence is stated rather than absorbed.** M0 (`M0_AUCTION_FILLS.md`) measured
that an official closing print exists on 99.89 % of ADV-tier-A symbol-days and clears a median
$37 M, so a retail-sized ON-CLOSE order is not the auction and does not move it; the primary
cost model here is `measured_auction_leg(..., "A_rank_1_50")` on BOTH sides, per side, as T6
requires. **That model was measured for the auction, and this bot no longer trades the
auction.** A near-close market order crosses the spread and eats a few minutes of price drift.
Both are omitted by the auction rail's MEASURED zero half-spread, so the auction-rail cost is
now a LOWER BOUND that the executed rail does not honour, and the taker counterfactual already
logged beside every session (`cost_if_taker_rail`, `retail_taker_costs()`, 2.5 bp/side) is the
better model of what is actually being paid.

The primary cost model is NOT switched here, because that would restate an accrual the owner is
evaluating, and because the frozen protocol already has the machinery for exactly this: FG4
measures `shortfall_bp_adverse_positive` -- now the gap between the near-close market fill and
the official closing print -- and T4 prereg 5 says that if FG4 fails, **the entire accrual is
restated at the taker rail before FG1 is read.** The measurement decides it, not this comment.
`costs.rail_note` in every record says the same thing so no reader can miss it.

Two charges M0's auction rail does NOT cover are added explicitly rather than inherited as
zeros: the **SEC Section 31 fee** and the **FINRA TAF**, both sell-side only. In
`retail_taker_costs()` these are described as folded into the half-spread's round-up; the
auction model's half-spread is measured at ZERO, so there is nothing to fold them into and
they must be charged by name. See `_regulatory_sell_side_bp`.

WHAT IS OWNER-GATED, AND WHAT IS NOT
====================================
* The LIVE endpoint is unreachable from this file by construction (`PaperBroker`'s hostname
  guard, reused rather than re-implemented). There is no flag that reaches it.
* **Order submission -- even to the paper endpoint -- is gated on an authorisation file the
  owner creates**, `research/trading_bot/T4_OWNER_AUTHORISATION.json`. `paper.py` states that
  explicit owner sign-off is required "before any order leaves this process, paper or
  otherwise", and this bot does not get to overrule that on its own authority. Deleting the
  file is the stop switch.
* `--mode dry-run` (the default) computes, sizes, prices and logs the identical order and
  submits nothing. It is the mode this file was developed and verified in.

USAGE
=====
    python -m scripts.trading_bot.t4_forward selftest
    python -m scripts.trading_bot.t4_forward session --dry-run --equity 100000
    python -m scripts.trading_bot.t4_forward session --dry-run --account-source broker
    python -m scripts.trading_bot.t4_forward session --mode submit          # owner-gated
    python -m scripts.trading_bot.t4_forward report
    python -m scripts.trading_bot.t4_forward status

See `scripts/trading_bot/T4_FORWARD.md` for start/stop and for how to read the accruing log.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from fractions import Fraction

from .costs import (CostComponent, CostModel, SlippageProvenance, measured_auction_leg,
                    measured_borrow_annual, retail_taker_costs, split_turnover)
from .data import load_bars, load_env_credentials
from .frozen import Refused, MICROS, et_offset_hours, pin_report, to_micros
from .paper import Order, OrderType, PaperBroker, Side, orders_for_target

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "research" / "trading_bot"

# `scripts/` is a namespace package, and the frozen T13 arithmetic is imported from it by name
# rather than copied. Putting the repository root on the path here means that holds however this
# module is entered -- `python -m`, a test import, or a cron entrypoint.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

T13_PREREG = RESEARCH / "T13_PREREGISTRATION.md"
T13_FROZEN = RESEARCH / "T13_FROZEN_CONFIG.json"

T4_PREREG = RESEARCH / "T4_FORWARD_PREREGISTRATION.md"
LEDGER_PATH = RESEARCH / "T4_FORWARD_LOG.jsonl"
STATE_PATH = RESEARCH / "T4_FORWARD_STATE.json"
CASH_PATH = RESEARCH / "T4_CASH_RATE.csv"
AUTHORISATION_PATH = RESEARCH / "T4_OWNER_AUTHORISATION.json"

T13_CASH_SEED = ROOT / "research" / "data" / "t13_cache" / "cash.csv"

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Frozen operating parameters. Every one of these is a claim about what is being
# tested, so each is a module constant that a diff will show, not a default
# buried in a signature.
# ---------------------------------------------------------------------------

SYMBOL = "SPY"                  # T13's confirmatory instrument; ^SP500TR is not tradeable
TIMEFRAME = "1Day"
FEED = "sip"
ADJUSTMENT = "all"              # total return: the return an investor actually earned
ADV_TIER = "A_rank_1_50"        # M0 tier for the execution rail; SPY is above rank 1 by dollar volume

# The ACTION window in US/Eastern wall clock: the minutes in which the session is decided,
# sized, logged and (if authorised) sent.
#
# It used to be 09:45-15:45, because the order was a market-on-close and the only thing that
# mattered was landing before the venue's 15:50 MOC cutoff. That order type EXPIRES UNFILLED on
# the Alpaca paper account (measured 2026-08-17, see the module docstring), so the mechanism is
# now a market DAY order and the window's job is the opposite one: be as LATE as possible, so
# the fill is as near the closing print as possible, while leaving enough room that the order
# cannot land after the bell.
#
# 15:50-15:58 is that trade-off, chosen against measured numbers rather than guessed:
#   * the INSTALLED crontab is `*/10 12-23 * * 1-5`, which fires on the ten-minute mark. 15:50
#     is the last such mark before the bell, so this lower bound is what makes the window
#     reachable BY THE SCHEDULER THAT IS ACTUALLY RUNNING. A window of 15:55-15:58 would be
#     tighter to the close and never fire at all -- a fix that needs a second, uninstalled fix
#     is not a fix. Narrowing the cron to `50-58 12-23 * * 1-5` gives nine attempts instead of
#     one and is recommended in T4_FORWARD.md; this window supports both schedules.
#   * a full broker session run (data fetch, clock, account, position, POST) measures ~2.3 s,
#     so even a run STARTED at 15:58 has ~2 minutes of slack before 16:00;
#   * ~10 minutes of price drift to the close is the cost, and it is UNBIASED -- it widens
#     shortfall_bp's dispersion, not its median, which is what FG4's 2 bp threshold gates on.
ACTION_WINDOW_ET = ((15, 50), (15, 58))

# Independent of the window, and deliberately not derived from it. A market DAY order that
# reaches the broker after 16:00 does not fill today: it queues to the NEXT open, which would
# establish the weight one session late at a price from the wrong session. That is the one
# execution failure that would corrupt the ledger rather than merely miss a day, so it gets its
# own named guard that a future widening of ACTION_WINDOW_ET cannot silently defeat.
SUBMIT_HARD_CUTOFF_ET = (15, 59)

# Sell-side regulatory pass-throughs. See _regulatory_sell_side_bp for why these are charged
# by name here and not in retail_taker_costs().
SEC_31_BP_SELL = Fraction("0.278")          # $27.80 per $1,000,000 of sale proceeds
FINRA_TAF_MICROS_PER_SHARE_SELL = 166        # $0.000166/share sold, $8.30 cap (uncapped here)

CASH_STALE_REFUSE_DAYS = 45
MIN_HISTORY_BARS = 90                        # 60 returns + slack; a short series refuses

FRED_DTB3 = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"


# ---------------------------------------------------------------------------
# The frozen rule
# ---------------------------------------------------------------------------

def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_rule() -> dict:
    """The T13 vol-targeting parameters, with the pre-registration hash verified.

    Refuses if the pre-registration has been edited since the freeze. A parameter set whose
    defining document can move is not a frozen rule, and a forward test of an unfrozen rule
    measures nothing.
    """
    for path in (T13_PREREG, T13_FROZEN):
        if not path.exists():
            raise Refused(f"{path} is missing; the frozen rule cannot be loaded")
    frozen = json.loads(T13_FROZEN.read_text())
    expected = frozen.get("preregistration_sha256")
    actual = _sha256(T13_PREREG)
    if not expected:
        raise Refused("T13_FROZEN_CONFIG.json carries no preregistration_sha256")
    if actual != expected:
        raise Refused(
            "T13_PREREGISTRATION.md has changed since the freeze.\n"
            f"  frozen config expects: {expected}\n"
            f"  on disk:               {actual}\n"
            "Restore the document. Do not update the hash: the point of the hash is that the "
            "rule this bot runs forward is the rule that was frozen before the held-out test."
        )
    vol = frozen.get("frozen_vol") or {}
    for key in ("L", "target", "wmax"):
        if key not in vol:
            raise Refused(f"frozen_vol is missing {key!r}; absent is a refusal, never a default")
    return {
        "rule_id": f"T13-VOL-L{int(vol['L'])}-T{vol['target']}-WMAX{vol['wmax']}",
        "L": int(vol["L"]),
        "target": float(vol["target"]),
        "wmax": float(vol["wmax"]),
        "timing_convention": frozen.get("timing_convention"),
        "t13_preregistration_sha256": actual,
        "t13_frozen_config_sha256": _sha256(T13_FROZEN),
        "heldout_window": frozen.get("heldout_window"),
        "status": (
            "DEAD ON T13's FROZEN GATE. Positive-signed in every decade and configuration, "
            "p = 0.233 on the drawdown gate, DSR = 0.355. Run forward because it cannot "
            "honestly be re-run backward, not because it was certified."
        ),
    }


def _independent_target_weight(closes, L: int, target: float, wmax: float) -> tuple:
    """Recomputation of the frozen weight, written independently of `vol_exposure`.

    This exists to disagree. `t13_target_weight` calls the frozen T13 implementation with an
    index window, and an off-by-one there would silently shift the whole forward test by a day.
    A second implementation with a different shape catches that; a single implementation
    catches nothing.
    """
    if len(closes) < L + 1:
        raise Refused(f"need {L + 1} closes for an L={L} realised vol; got {len(closes)}")
    window = closes[-(L + 1):]
    rets = [window[i] / window[i - 1] - 1.0 for i in range(1, len(window))]
    if len(rets) != L:
        raise Refused(f"return window is {len(rets)} long, expected {L}")
    mean = sum(rets) / L
    var = max(0.0, sum(r * r for r in rets) / L - mean * mean)
    rv = math.sqrt(var) * math.sqrt(252.0)
    if rv <= 0:
        raise Refused("zero realised volatility; refusing rather than dividing")
    return rv, min(wmax, target / rv)


def t13_target_weight(closes, rule: dict) -> dict:
    """The frozen weight for the session AFTER the one whose close we are about to trade at.

    `closes[-1]` must be the most recent PRINTED close. Under T13-L1 the exposure applied to
    a session's return may use closes through two sessions before it; the order placed on the
    close of session D establishes the weight that earns session D+1's return, and closes(D-1)
    is exactly two sessions before D+1.
    """
    L, target, wmax = rule["L"], rule["target"], rule["wmax"]
    if len(closes) < MIN_HISTORY_BARS:
        raise Refused(
            f"{len(closes)} closes is not enough history for an L={L} rule with warm-up; "
            f"{MIN_HISTORY_BARS} required. Refusing rather than sizing on a short window."
        )

    # The frozen implementation, consumed rather than copied. `a = n + 1` addresses the
    # session two ahead of the last printed close, which is the one the near-close order
    # establishes.
    from scripts.t13_risk_shaping import vol_exposure  # noqa: PLC0415 -- path import, see below

    n = len(closes)
    frozen_w = vol_exposure(list(closes), L, target, wmax, n + 1, n + 2, lag=2)[0]
    rv, local_w = _independent_target_weight(closes, L, target, wmax)

    if abs(frozen_w - local_w) > 1e-12:
        raise Refused(
            "the frozen T13 vol_exposure and this file's independent recomputation disagree "
            f"({frozen_w!r} vs {local_w!r}). One of them is wrong and neither may be trusted "
            "to size a position. Refusing."
        )
    return {
        "realised_vol_annual": rv,
        "target_weight": frozen_w,
        "lookback_returns": L,
        "reference_close_index": n - 1,
        "cross_check": "scripts.t13_risk_shaping.vol_exposure == local recomputation",
    }


# ---------------------------------------------------------------------------
# Cost model: T6 per-side structure, M0 auction rail, regulatory legs by name
# ---------------------------------------------------------------------------

def _regulatory_sell_side_bp(price_micros: int) -> Fraction:
    """SEC 31 + FINRA TAF on a SELL, in bp of the notional sold.

    `retail_taker_costs()` folds these into a 2.5 bp half-spread's round-up and says so. The
    M0 auction model's half-spread is a MEASURED zero -- there is no round-up to hide them in
    -- so charging them here by name is the difference between a lower bound and an omission.

    TAF is per share; at a $650 SPY it is ~0.0026 bp, which is small and is charged anyway,
    because "too small to matter" is how a cost model starts accumulating silent zeros. The
    $8.30 per-order TAF cap is NOT applied: leaving it off is the adverse side, and this
    accounting has no per-order dollar dimension to apply a cap in (see CostModel's note on
    min_commission_micros).
    """
    if price_micros <= 0:
        raise Refused("cannot price a regulatory fee at a non-positive price")
    taf_bp = Fraction(FINRA_TAF_MICROS_PER_SHARE_SELL, price_micros) * 10_000
    return SEC_31_BP_SELL + taf_bp


def m0_auction_cost_model() -> CostModel:
    """The rail this accrual is PRICED on: M0 auction, both sides, ADV tier A, per side.

    NOTE, and see the module docstring: since 2026-08-18 this is no longer the rail the bot
    EXECUTES on. tif=cls expires unfilled on the paper account, so the fills are near-close
    market DAY orders, which cross the spread and take a few minutes of drift -- neither of
    which this measured-zero half-spread contains. Kept as the primary model so the accrual is
    not restated mid-flight; FG4 measures the gap and prereg 5 decides what to do about it.

    `measured_auction_leg` refuses outside the tiers M0 measured, so a future edit that points
    this bot at an illiquid symbol cannot quietly inherit a zero half-spread.
    """
    entry_half, entry_extra = measured_auction_leg("entry", ADV_TIER)
    exit_half, exit_extra = measured_auction_leg("exit", ADV_TIER)
    return CostModel(
        entry_half_spread=entry_half,
        entry_extra_slippage=entry_extra,
        exit_half_spread=exit_half,
        exit_extra_slippage=exit_extra,
        commission_per_share=CostComponent(
            "commission_per_share", Fraction(0), "micro-dollars per share",
            SlippageProvenance.BROKER_SCHEDULE,
            "Alpaca charges no per-share commission on US equity orders. The sell-side "
            "regulatory pass-throughs (SEC 31, FINRA TAF) are NOT zero and are charged "
            "separately by _regulatory_sell_side_bp, because this model's half-spread is a "
            "measured zero and cannot absorb them the way retail_taker_costs()'s does.",
        ),
        borrow_annual=measured_borrow_annual("etb_general_collateral"),
    )


def stress_cost_model() -> CostModel:
    """The conservative counterfactual logged beside every accrual: a plain taker round trip.

    If the auction rail ever fails to be what M0 measured -- and since 2026-08-18 it is known
    not to be, because the executed rail is a near-close market order and not the auction
    across the spread -- the cost is nearer this. Logging both means the track record carries
    its own sensitivity to the one cost assumption it leans on.
    """
    return retail_taker_costs()


def _cost_fraction(model: CostModel, prev_w: float, new_w: float, price_micros: int) -> dict:
    """Cost of moving exposure prev_w -> new_w, as a fraction of equity. Per side."""
    entry_turnover, exit_turnover = split_turnover(Fraction(prev_w).limit_denominator(10 ** 9),
                                                   Fraction(new_w).limit_denominator(10 ** 9))
    base = model.trade_cost_fraction(price_micros, entry_turnover=entry_turnover,
                                     exit_turnover=exit_turnover)
    regulatory = exit_turnover * _regulatory_sell_side_bp(price_micros) / 10_000
    total = base + regulatory
    if total < 0:
        raise Refused("negative total trade cost; the sign convention has been violated")
    return {
        "entry_turnover": float(entry_turnover),
        "exit_turnover": float(exit_turnover),
        "rail_fraction": float(base),
        "regulatory_sell_fraction": float(regulatory),
        "total_fraction": float(total),
        "total_bp": float(total * 10_000),
    }


# ---------------------------------------------------------------------------
# Cash leg
# ---------------------------------------------------------------------------

def _read_cash_csv(path: pathlib.Path) -> list:
    rows = []
    with path.open() as handle:
        for rec in csv.reader(handle):
            if not rec or rec[0] == "date":
                continue
            rows.append((rec[0], float(rec[1]), rec[2] if len(rec) > 2 else "unknown"))
    return sorted(rows)


def _seed_cash_file() -> None:
    if CASH_PATH.exists():
        return
    if not T13_CASH_SEED.exists():
        raise Refused(
            f"no cash-rate series at {CASH_PATH} and no T13 seed at {T13_CASH_SEED}. "
            "Run `python scripts/t13_data.py build`, or accept the ex-cash curve only."
        )
    rows = _read_cash_csv(T13_CASH_SEED)[-800:]
    CASH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CASH_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "annual_pct", "source"])
        writer.writerows(rows)


def refresh_cash_rates() -> dict:
    """Best-effort FRED DTB3 refresh into the bot's OWN file. Never mutates the T13 artifact.

    A failure here is recorded, not fatal: a bot that cannot place an order because a
    macro-data website is down has a fragility the strategy does not. Staleness is carried
    into every ledger record instead, and `_cash_rate_for` refuses outright past
    CASH_STALE_REFUSE_DAYS.
    """
    _seed_cash_file()
    try:
        request = urllib.request.Request(FRED_DTB3, headers={"User-Agent": "t4-forward/1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8")
    except Exception as exc:                                  # noqa: BLE001 -- recorded, not raised
        return {"refreshed": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}

    rows = []
    for rec in csv.DictReader(text.splitlines()):
        keys = list(rec.keys())
        date, value = rec[keys[0]], rec[keys[1]]
        if value in (".", "", None):
            continue
        rows.append((date, float(value), "FRED_DTB3"))
    if not rows:
        return {"refreshed": False, "reason": "FRED DTB3 returned no usable rows"}

    existing = {row[0]: row for row in _read_cash_csv(CASH_PATH)}
    added = 0
    for row in rows:
        if row[0] not in existing:
            added += 1
        existing[row[0]] = row
    merged = sorted(existing.values())[-2000:]
    with CASH_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "annual_pct", "source"])
        writer.writerows(merged)
    return {"refreshed": True, "rows_added": added, "latest": merged[-1][0]}


def _cash_rate_for(date: str) -> dict:
    """Annualised percent yield in force on `date`, held flat from the last publication."""
    _seed_cash_file()
    rows = _read_cash_csv(CASH_PATH)
    current = None
    for stamp, rate, source in rows:
        if stamp <= date:
            current = (stamp, rate, source)
        else:
            break
    if current is None:
        raise Refused(f"no cash rate published on or before {date}; refusing to use zero")
    stale = (dt.date.fromisoformat(date) - dt.date.fromisoformat(current[0])).days
    if stale > CASH_STALE_REFUSE_DAYS:
        raise Refused(
            f"the newest cash rate is {current[0]}, {stale} days before {date}. Past "
            f"{CASH_STALE_REFUSE_DAYS} days this stops being 'held flat' and starts being "
            "a guess. Refresh the series or run with --no-cash-leg."
        )
    return {"as_of": current[0], "annual_pct": current[1], "source": current[2],
            "stale_days": stale}


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

def _session_date(ts_ns: int) -> str:
    """Session date of a daily bar. Alpaca stamps daily bars at 00:00 ET (04:00/05:00Z)."""
    stamp = dt.datetime.fromtimestamp(ts_ns // 1_000_000_000, tz=dt.timezone.utc)
    return stamp.date().isoformat()


def load_daily_closes(*, session_date: str, lookback_days: int = 400,
                      allow_network: bool = True, cache_dir=None) -> dict:
    """SPY daily total-return closes strictly BEFORE `session_date`, newest last.

    The request window ends the calendar day before the session, and that is doing two jobs at
    once. It is what T13-L1 permits -- the weight established at today's close may use closes
    through the previous session and no later -- so the timing convention is enforced by the
    fetch rather than by a downstream check that someone could remove. It also keeps the
    request off the SIP feed's recency window, which a data subscription without real-time SIP
    refuses with an HTTP 403; that refusal would otherwise look like a market-data outage.

    `adjustment=all` is the right convention for a RETURN series and is what T13 used. The
    known consequence is recorded rather than hidden: adjusted price LEVELS are retroactive,
    so nothing here may filter on a level, and the equity curves are advanced INCREMENTALLY
    (one session's return at a time, at the time) so that a later dividend adjustment cannot
    silently rewrite a return this bot already logged.
    """
    end_date = (dt.date.fromisoformat(session_date) - dt.timedelta(days=1)).isoformat()
    start = (dt.date.fromisoformat(end_date) - dt.timedelta(days=lookback_days)).isoformat()
    bars, manifest = load_bars(
        SYMBOL, start, end_date, TIMEFRAME, feed=FEED, adjustment=ADJUSTMENT,
        cache_dir=cache_dir, allow_network=allow_network,
    )
    dates = [_session_date(bar.ts_ns) for bar in bars]
    closes = [bar.close_micros / MICROS for bar in bars]
    close_micros = [bar.close_micros for bar in bars]
    if len(dates) != len(set(dates)):
        raise Refused("duplicate session dates in the daily series; refusing")
    for prev, cur in zip(dates, dates[1:]):
        if cur <= prev:
            raise Refused(f"daily series is not strictly increasing at {prev} -> {cur}")
    return {"dates": dates, "closes": closes, "close_micros": close_micros,
            "manifest": manifest}


# ---------------------------------------------------------------------------
# The paper endpoint. Reads and (owner-gated) writes.
# ---------------------------------------------------------------------------

class PaperAccount:
    """Reads and orders against `paper-api.alpaca.markets` ONLY.

    The hostname guard is `PaperBroker`'s, constructed rather than re-implemented, so the live
    endpoint is refused here for exactly the same reason and in exactly the same place it is
    refused in the backtest rig.

    `place_near_close_market` is gated twice: the guard above, and `assert_owner_authorised()`.
    """

    def __init__(self, host: str = None):
        broker = PaperBroker() if host is None else PaperBroker(host)
        self.host = broker.host
        self._key, self._secret = load_env_credentials()

    # -- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, body: dict = None) -> dict:
        url = f"{self.host}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers={
            "APCA-API-KEY-ID": self._key,
            "APCA-API-SECRET-KEY": self._secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise Refused(f"HTTP {exc.code} {method} {path}: {_scrub(detail, self._key, self._secret)}") from exc
        return json.loads(text) if text.strip() else {}

    # -- reads -------------------------------------------------------------

    def clock(self) -> dict:
        return self._request("GET", "/v2/clock")

    def account(self) -> dict:
        raw = self._request("GET", "/v2/account")
        for key in ("equity", "cash", "status"):
            if key not in raw:
                raise Refused(f"account response has no {key!r}; refusing to assume one")
        return {
            "equity": float(raw["equity"]),
            "cash": float(raw["cash"]),
            "status": raw["status"],
            "account_number_sha256": hashlib.sha256(
                str(raw.get("account_number", "")).encode()).hexdigest()[:16],
            "pattern_day_trader": raw.get("pattern_day_trader"),
        }

    def position(self, symbol: str) -> dict:
        try:
            raw = self._request("GET", f"/v2/positions/{symbol}")
        except Refused as exc:
            if "HTTP 404" in str(exc):
                return {"qty": 0, "market_value": 0.0, "avg_entry_price": None}
            raise
        return {"qty": int(float(raw["qty"])), "market_value": float(raw["market_value"]),
                "avg_entry_price": float(raw["avg_entry_price"])}

    def order(self, order_id: str) -> dict:
        return self._request("GET", f"/v2/orders/{order_id}")

    # -- the gated write ---------------------------------------------------

    def place_near_close_market(self, order: Order, *, client_order_id: str) -> dict:
        """One market DAY order, sent in the final minutes of the session.

        `time_in_force` is `"day"`, NOT `"cls"`. That is the whole of the 2026-08-18 fix and it
        is worth stating plainly next to the payload it changes: on the Alpaca PAPER account a
        `tif="cls"` market-on-close order is accepted, sits all day, and EXPIRES unfilled at the
        close -- measured, order 3a5487f8-b9bc-46b2-89a1-f19ba46e964c, 2026-08-17. The paper
        simulator does not run the closing auction. A DAY market order fills against its book
        immediately, so the position is established a few minutes before the print instead of
        never.

        `client_order_id` makes a retry idempotent AT THE BROKER. The window between the POST
        landing and this process recording it is the one place a crash could produce an order
        with no ledger entry, and a naive retry would then double the position. Alpaca rejects a
        duplicate `client_order_id`, so the retry refuses instead -- the broker holds the
        idempotency key, which is the only place it is safe to hold it.
        """
        assert_owner_authorised()
        if order.order_type is not OrderType.MARKET:
            raise Refused("the T4 rail is a near-close market order; a non-market type is a bug")
        payload = {
            "symbol": order.symbol,
            "qty": str(order.quantity_shares),
            "side": order.side.value,
            "type": "market",
            "time_in_force": "day",         # NOT "cls": see the docstring. cls expires on paper.
            "extended_hours": False,
            "client_order_id": client_order_id,
        }
        return self._request("POST", "/v2/orders", payload)


def _scrub(text: str, *secrets: str) -> str:
    """A credential must never reach a log, a ledger, or an exception message."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***REDACTED***")
    return text


def assert_owner_authorised() -> dict:
    """The gate. An order leaves this process only if the owner has written the file.

    `paper.py` records the standing position that explicit owner sign-off is required before
    any order leaves the process, **paper or otherwise**. This bot does not get to overrule
    that because its own task brief was convenient. So the gate is a file the owner creates,
    outside this code, and deleting it is the stop switch.

    Creating this file authorises PAPER orders only. There is no file, flag, or environment
    variable anywhere in this rig that reaches the live endpoint; that is enforced by
    hostname, not by policy.
    """
    if not AUTHORISATION_PATH.exists():
        raise Refused(
            "PAPER ORDER SUBMISSION IS NOT AUTHORISED.\n"
            f"  expected: {AUTHORISATION_PATH}\n"
            "  containing: {\"paper_order_submission_authorised\": true, "
            "\"authorised_by\": \"<owner>\", \"authorised_utc\": \"<iso8601>\"}\n"
            "\n"
            "This is the owner's decision, not the bot's, and not the supervising agent's. "
            "`scripts/trading_bot/paper.py` records that explicit owner sign-off is required "
            "before any order leaves this process, paper or otherwise. Until the file exists, "
            "run `--dry-run`: it computes, sizes, prices and logs the identical order and "
            "submits nothing.\n"
            "Deleting the file is the stop switch."
        )
    try:
        blob = json.loads(AUTHORISATION_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise Refused(f"{AUTHORISATION_PATH} is not valid JSON: {exc}") from exc
    if blob.get("paper_order_submission_authorised") is not True:
        raise Refused(
            f"{AUTHORISATION_PATH} exists but paper_order_submission_authorised is not "
            "exactly true. A malformed authorisation is not an authorisation."
        )
    return blob


# ---------------------------------------------------------------------------
# State and ledger
# ---------------------------------------------------------------------------

def _blank_state(rule: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "rule": rule,
        "symbol": SYMBOL,
        "inception_date": None,
        # session date -> the weight that TOOK EFFECT at that session. The weight in force on
        # any later session is the most recent change at or before it, because a position
        # persists until something moves it. Storing changes rather than a value per session
        # is what makes a missed run correct instead of silently rewriting history: if the bot
        # does not run, no order is placed, and the previous weight really did stay in force.
        "weight_changes": {},
        "pending_weights": {},      # decided at a close, not yet bound to the session it earns
        "pending_order": None,      # submitted, not yet reconciled against the official print
        "last_settled_date": None,
        "prev_weight": 0.0,
        "curves": {"model_withcash": 1.0, "model_excash": 1.0, "benchmark": 1.0},
        "peaks": {"model_withcash": 1.0, "model_excash": 1.0, "benchmark": 1.0},
        "maxdd": {"model_withcash": 0.0, "model_excash": 0.0, "benchmark": 0.0},
        "benchmark_entered": False,
        "cum_cost_fraction": 0.0,
        "sessions_settled": 0,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def load_state(rule: dict, path: pathlib.Path = None) -> dict:
    path = path or STATE_PATH
    if not path.exists():
        return _blank_state(rule)
    state = json.loads(path.read_text())
    if state.get("schema_version") != SCHEMA_VERSION:
        raise Refused(
            f"state file {path} is schema {state.get('schema_version')}, this bot writes "
            f"{SCHEMA_VERSION}. Migrate it deliberately; do not let a forward test's ledger "
            "change meaning mid-run."
        )
    stored = (state.get("rule") or {}).get("rule_id")
    if stored != rule["rule_id"]:
        raise Refused(
            f"the state file was written under rule {stored!r} and the frozen rule is now "
            f"{rule['rule_id']!r}. A forward test whose rule changed mid-flight is two "
            "half-tests. Start a new ledger, and say so in the pre-registration."
        )
    return state


def save_state(state: dict, path: pathlib.Path = None) -> None:
    path = path or STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(path)


def append_ledger(record: dict, path: pathlib.Path = None) -> None:
    path = path or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def read_ledger(path: pathlib.Path = None) -> list:
    path = path or LEDGER_PATH
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Settlement -- the arithmetic that turns fills into a track record
# ---------------------------------------------------------------------------

def settle(state: dict, series: dict, *, cost_model: CostModel, stress_model: CostModel,
           use_cash_leg: bool = True) -> list:
    """Advance every curve over each session whose close has now printed.

    Mirrors `t13_risk_shaping.run` exactly: the cost of moving from `w_{t-1}` to `w_t` is
    charged on day `t`, the first day the new weight is in force, and the net return is
    `(1 + r_portfolio) * (1 - cost) - 1`.

    Curves advance INCREMENTALLY and are never recomputed from history. That is deliberate:
    `adjustment=all` retroactively revises past closes at each dividend, so a curve rebuilt
    from scratch tomorrow would not equal the curve logged today, and a forward test whose
    past silently moves is not a forward test.
    """
    changes = {d: float(w) for d, w in (state.get("weight_changes") or {}).items()}
    if not changes:
        return []
    inception = min(changes)
    settled = []

    for i, date in enumerate(series["dates"]):
        if i == 0 or date < inception:
            continue
        if state["last_settled_date"] is not None and date <= state["last_settled_date"]:
            continue
        # the weight in force is the most recent change at or before this session. A session
        # the bot did not run on inherits the previous weight, because that is what the
        # account actually held.
        applicable = [d for d in changes if d <= date]
        w = changes[max(applicable)]
        prev_w = float(state["prev_weight"])
        px_prev, px_now = series["closes"][i - 1], series["closes"][i]
        r_index = px_now / px_prev - 1.0

        cost = _cost_fraction(cost_model, prev_w, w, series["close_micros"][i - 1])
        stress = _cost_fraction(stress_model, prev_w, w, series["close_micros"][i - 1])

        cash = None
        r_cash_leg = 0.0
        if use_cash_leg:
            cash = _cash_rate_for(series["dates"][i - 1])
            caldays = (dt.date.fromisoformat(date)
                       - dt.date.fromisoformat(series["dates"][i - 1])).days
            if caldays < 0:
                raise Refused("negative calendar gap between sessions; series is out of order")
            r_cash_leg = (cash["annual_pct"] / 100.0) * caldays / 365.0

        r_withcash = (1.0 + w * r_index + (1.0 - w) * r_cash_leg) * (1.0 - cost["total_fraction"]) - 1.0
        r_excash = (1.0 + w * r_index) * (1.0 - cost["total_fraction"]) - 1.0

        # The benchmark is un-overlaid buy-and-hold, and it pays for its one entry.
        if not state["benchmark_entered"]:
            bench_cost = _cost_fraction(cost_model, 0.0, 1.0, series["close_micros"][i - 1])
            r_bench = (1.0 + r_index) * (1.0 - bench_cost["total_fraction"]) - 1.0
            state["benchmark_entered"] = True
        else:
            r_bench = r_index

        moves = {"model_withcash": r_withcash, "model_excash": r_excash, "benchmark": r_bench}
        for name, r in moves.items():
            state["curves"][name] *= (1.0 + r)
            state["peaks"][name] = max(state["peaks"][name], state["curves"][name])
            dd = (state["peaks"][name] - state["curves"][name]) / state["peaks"][name]
            state["maxdd"][name] = max(state["maxdd"][name], dd)

        state["cum_cost_fraction"] += cost["total_fraction"]
        state["prev_weight"] = w
        state["last_settled_date"] = date
        state["sessions_settled"] += 1

        settled.append({
            "date": date, "status": "settled",
            "weight_in_force": w, "weight_previous": prev_w,
            "index_close": px_now, "index_close_prev": px_prev, "r_index": r_index,
            "cash_leg": cash, "r_cash_accrual": r_cash_leg,
            "cost": cost, "cost_if_taker_rail": stress,
            "r_model_withcash": r_withcash, "r_model_excash": r_excash, "r_benchmark": r_bench,
            "equity": dict(state["curves"]),
            "drawdown_now": {k: (state["peaks"][k] - state["curves"][k]) / state["peaks"][k]
                             for k in state["curves"]},
            "maxdd_running": dict(state["maxdd"]),
        })
    return settled


# ---------------------------------------------------------------------------
# One session
# ---------------------------------------------------------------------------

def _et_now(now_utc: dt.datetime) -> dt.datetime:
    """US/Eastern wall clock as a naive datetime. The offset is per day, from the frozen rule.

    Naive on purpose: keeping a UTC tzinfo on a shifted clock is how a log ends up saying
    `15:30+00:00` for half past three in New York.
    """
    shifted = now_utc + dt.timedelta(hours=et_offset_hours(now_utc.date()))
    return shifted.replace(tzinfo=None)


def _within_action_window(now_et: dt.datetime) -> bool:
    (lo_h, lo_m), (hi_h, hi_m) = ACTION_WINDOW_ET
    minutes = now_et.hour * 60 + now_et.minute
    return lo_h * 60 + lo_m <= minutes <= hi_h * 60 + hi_m


def _past_submit_cutoff(now_et: dt.datetime) -> bool:
    """True once it is too late to trust a market DAY order to fill in TODAY's session."""
    cut_h, cut_m = SUBMIT_HARD_CUTOFF_ET
    return now_et.hour * 60 + now_et.minute >= cut_h * 60 + cut_m


def run_session(*, mode: str, account_source: str, simulated_equity: float,
                now_utc: dt.datetime = None, allow_network: bool = True,
                use_cash_leg: bool = True, refresh_cash: bool = False,
                state_path: pathlib.Path = None, ledger_path: pathlib.Path = None,
                cache_dir=None, force: bool = False) -> dict:
    """Compute, settle, size, (optionally) submit, and log exactly one session.

    Idempotent by session date: a second run on the same date refuses unless `--force`. A
    forward test that can double-log a day can also double-size a position.
    """
    if mode not in ("dry-run", "submit"):
        raise Refused(f"mode must be 'dry-run' or 'submit', not {mode!r}")
    if account_source not in ("simulated", "broker"):
        raise Refused(f"account-source must be 'simulated' or 'broker', not {account_source!r}")
    if mode == "submit" and account_source != "broker":
        raise Refused("submitting an order against a simulated account size is meaningless")

    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    now_et = _et_now(now_utc)
    session_date = now_et.date().isoformat()

    rule = frozen_rule()
    state = load_state(rule, state_path)

    ledger = read_ledger(ledger_path)
    if not force and any(rec.get("session_date") == session_date
                         and rec.get("kind") == "session" for rec in ledger):
        raise Refused(
            f"a session record for {session_date} is already in the ledger. Refusing to log "
            "or size the same session twice. Use --force only if you know why."
        )

    cash_refresh = {"refreshed": False, "reason": "not requested"}
    if use_cash_leg and refresh_cash:
        cash_refresh = refresh_cash_rates()

    # ---- market data -----------------------------------------------------
    series = load_daily_closes(session_date=session_date, allow_network=allow_network,
                               cache_dir=cache_dir)
    last_close_date = series["dates"][-1]
    if last_close_date >= session_date:
        # Belt and braces: the fetch window already ends before the session, so this can only
        # fire if a bar is mis-stamped. A bar dated on or after the session it is supposed to
        # predate is exactly the shape of a lookahead, so it refuses rather than warns.
        raise Refused(
            f"the newest daily bar is {last_close_date}, which is not before the session date "
            f"{session_date}. This bot decides DURING a session against the PREVIOUS close; "
            "a bar dated at or after the session would make the weight depend on the return "
            "it is about to earn. Refusing."
        )

    # ---- clock / venue ---------------------------------------------------
    venue = {"broker_clock_checked": False,
             "within_action_window": _within_action_window(now_et),
             "action_window_et": ACTION_WINDOW_ET,
             "past_submit_hard_cutoff": _past_submit_cutoff(now_et),
             "submit_hard_cutoff_et": SUBMIT_HARD_CUTOFF_ET,
             "order_mechanism": "market / time_in_force=day, sent in the final minutes",
             "note": ("the window is recorded even in dry-run, so a record made outside it "
                      "cannot be read later as an order that was placeable at that moment. "
                      "Field renamed from within_moc_entry_window/moc_entry_window_et on "
                      "2026-08-18 when the mechanism stopped being market-on-close.")}
    account_obj = None
    if account_source == "broker":
        account_obj = PaperAccount()
        clock = account_obj.clock()
        venue.update({"broker_clock_checked": True, "is_open": bool(clock.get("is_open")),
                      "next_close": clock.get("next_close"),
                      "timestamp": clock.get("timestamp")})
        if mode == "submit":
            if not venue["is_open"]:
                raise Refused(
                    "the market is closed. A market DAY order sent now would not fill now: it "
                    "would queue to the NEXT open and establish the weight one session late, "
                    "at a price from the wrong session. Refusing."
                )
            if not _within_action_window(now_et):
                raise Refused(
                    f"{now_et:%H:%M} ET is outside the action window "
                    f"{ACTION_WINDOW_ET[0][0]:02d}:{ACTION_WINDOW_ET[0][1]:02d}-"
                    f"{ACTION_WINDOW_ET[1][0]:02d}:{ACTION_WINDOW_ET[1][1]:02d}. The weight is "
                    "meant to be established at ~the close, so an order sent hours earlier "
                    "would be a different execution rail from the one being measured. Refusing."
                )
            if _past_submit_cutoff(now_et):
                raise Refused(
                    f"{now_et:%H:%M} ET is at or past the hard submit cutoff "
                    f"{SUBMIT_HARD_CUTOFF_ET[0]:02d}:{SUBMIT_HARD_CUTOFF_ET[1]:02d} ET. A "
                    "market DAY order that reaches the broker after the bell queues to the "
                    "next open and would establish the weight one session late. Refusing "
                    "rather than sending an order that fills in the wrong session."
                )

    # ---- resolve the previous order, then settle what has printed -------
    fill = {"reconciled": False, "reason": "no broker connection this run"}
    if account_obj is not None:
        fill = reconcile_fill(state, series, account_obj)

    # Yesterday's on-close decision was made before the calendar had named the session it
    # would apply to. Bind it first, then settle: the order of these two is what keeps the
    # weight attached to the return it actually earned.
    bind_pending_weight(state, series)
    cost_model, stress_model = m0_auction_cost_model(), stress_cost_model()
    settled = settle(state, series, cost_model=cost_model, stress_model=stress_model,
                     use_cash_leg=use_cash_leg)

    # ---- the decision ----------------------------------------------------
    weight = t13_target_weight(series["closes"], rule)
    target_w = weight["target_weight"]

    # ---- account and sizing ---------------------------------------------
    price_micros = series["close_micros"][-1]
    if account_source == "broker":
        account = account_obj.account()
        position = account_obj.position(SYMBOL)
        equity = account["equity"]
        held_shares = position["qty"]
        held_notional = position["market_value"]
    else:
        account = {"equity": float(simulated_equity), "cash": float(simulated_equity),
                   "status": "SIMULATED", "account_number_sha256": None,
                   "note": "no broker was contacted; sizing is against a stated notional"}
        equity = float(simulated_equity)
        # a simulated account holds what the previous session's weight implied
        held_notional = equity * float(state["prev_weight"])
        held_shares = int(held_notional / (price_micros / MICROS)) if price_micros else 0
        position = {"qty": held_shares, "market_value": held_notional,
                    "avg_entry_price": None}

    if equity <= 0:
        raise Refused("non-positive account equity; refusing to size a position")

    current_fraction = Fraction(held_notional).limit_denominator(10 ** 9) / \
        Fraction(equity).limit_denominator(10 ** 9)
    orders = orders_for_target(
        SYMBOL,
        Fraction(target_w).limit_denominator(10 ** 9),
        current_fraction,
        equity_micros=to_micros(equity),
        price_micros=price_micros,
        ts_ns=int(now_utc.timestamp()) * 1_000_000_000,
    )
    intended = None
    if orders:
        order = orders[0]
        intended = {"symbol": order.symbol, "side": order.side.value,
                    "type": "market", "time_in_force": "day",
                    "mechanism": "near-close market order",
                    "quantity_shares": order.quantity_shares}

    projected_shares = held_shares + (
        0 if not orders else (orders[0].quantity_shares
                              if orders[0].side is Side.BUY else -orders[0].quantity_shares))
    projected_notional = projected_shares * price_micros / MICROS
    achieved_w = projected_notional / equity

    # ---- submission (owner-gated) ---------------------------------------
    execution = {"submitted": False, "reason": "dry-run: nothing left this process"}
    if mode == "submit":
        if not orders:
            execution = {"submitted": False, "reason": "no whole-share change was required"}
        else:
            authorisation = assert_owner_authorised()
            # One order per session by construction: a retry after a crash collides with this
            # id at the broker and is rejected, rather than doubling the position.
            client_order_id = f"t4-{rule['rule_id']}-{session_date}".replace(".", "_")
            response = account_obj.place_near_close_market(
                orders[0], client_order_id=client_order_id)
            execution = {
                "submitted": True,
                "order_id": response.get("id"),
                "client_order_id": response.get("client_order_id") or client_order_id,
                "status": response.get("status"),
                "submitted_at": response.get("submitted_at"),
                "order_type": "market",
                "time_in_force": "day",
                "submitted_at_et": now_et.isoformat(),
                "authorised_by": authorisation.get("authorised_by"),
                "endpoint": account_obj.host,
                "note": ("PAPER account. No real money. Market DAY order sent inside the "
                         "final-minutes action window; tif=cls (market-on-close) is NOT used "
                         "because it expires unfilled on the paper account. The fill price is "
                         "reconciled against the official close on the next run."),
            }
            state["pending_order"] = {
                "order_id": response.get("id"),
                "session_date": session_date,
                "side": orders[0].side.value,
                "qty": orders[0].quantity_shares,
            }

    # ---- record ----------------------------------------------------------
    record = {
        "kind": "session",
        "schema_version": SCHEMA_VERSION,
        "session_date": session_date,
        "run_utc": now_utc.isoformat(),
        "run_et": now_et.isoformat(),
        "mode": mode,
        "account_source": account_source,
        "rule": rule,
        "framing": FRAMING,
        "data": {
            "symbol": SYMBOL, "feed": FEED, "adjustment": ADJUSTMENT,
            "reference_close_date": last_close_date,
            "reference_close": series["closes"][-1],
            "bars_available": len(series["dates"]),
            "manifest_source": series["manifest"].get("source"),
        },
        "decision": {
            **weight,
            "weight_previous": float(state["prev_weight"]),
            "weight_applies_from_session_after": session_date,
            "timing": ("weight computed from closes through the previous session; established "
                       "at today's close; earns the NEXT session's return. T13-L1 holds by "
                       "construction."),
        },
        "account": account,
        "position_before": position,
        "sizing": {
            "equity": equity,
            "price_used": price_micros / MICROS,
            "current_fraction": float(current_fraction),
            "target_weight": target_w,
            "intended_order": intended,
            "projected_shares": projected_shares,
            "projected_weight_after_rounding": achieved_w,
            "rounding_note": ("whole shares, rounded DOWN in absolute value: under-filling "
                              "takes less risk than the sizing authorised, over-filling takes "
                              "more."),
        },
        "execution": execution,
        "fill_reconciliation": fill,
        "venue": venue,
        "settled_sessions": settled,
        "track_record_after": track_record(state),
        "costs": {
            "rail": cost_model.to_report(),
            "stress_rail": stress_model.to_report(),
            "regulatory_sell_side_bp": float(_regulatory_sell_side_bp(price_micros)),
            "adv_tier": ADV_TIER,
            "rail_note": (
                "READ THIS BEFORE READING ANY COST NUMBER IN THIS RECORD. As of 2026-08-18 the "
                "bot no longer trades the closing auction: tif=cls EXPIRES UNFILLED on the "
                "Alpaca paper account (measured, order 3a5487f8, 2026-08-17), so the mechanism "
                "is a market DAY order sent in the final minutes. `rail` below is still M0's "
                "AUCTION model, which was measured for a rail this bot no longer uses, and its "
                "MEASURED-ZERO half-spread omits both the crossed spread and the few minutes of "
                "drift to the print. It is therefore a LOWER BOUND, not the executed cost. "
                "`stress_rail` (retail taker, 2.5 bp/side) is the better model of what is "
                "actually being paid. The primary model is NOT switched here because that would "
                "restate an accrual mid-flight; the frozen protocol already decides this -- FG4 "
                "measures the realised shortfall and T4 prereg 5 restates the ENTIRE accrual at "
                "the taker rail if FG4 fails. Owner call, on the measurement, not on this note."),
            "note": ("M0 measured the auction rail for ADV tiers A-D; SPY sits above rank 1 "
                     "by dollar volume, so tier A is the least favourable of the measured "
                     "tiers that can apply to it, not an extrapolation downward. SEC 31 and "
                     "FINRA TAF are charged separately because the auction half-spread is a "
                     "measured ZERO and cannot absorb them."),
        },
        "cash_leg": {"enabled": use_cash_leg, "refresh": cash_refresh},
        "provenance": pin_report(),
    }

    # The weight decided today takes effect at the NEXT session, whose date the calendar has
    # not yet given us. Queue it; a later run binds it once that session has printed.
    state.setdefault("pending_weights", {})
    state["pending_weights"][session_date] = {
        "weight": target_w, "reference_close_date": last_close_date,
    }
    if state["inception_date"] is None:
        state["inception_date"] = session_date

    record["state_after"] = {k: state.get(k) for k in
                             ("curves", "peaks", "maxdd", "prev_weight", "last_settled_date",
                              "sessions_settled", "pending_weights", "pending_order",
                              "inception_date")}

    _assert_clean(record)
    append_ledger(record, ledger_path)
    save_state(state, state_path)
    return record


def reconcile_fill(state: dict, series: dict, account: "PaperAccount") -> dict:
    """Resolve the order placed at the PREVIOUS session's close against the official close.

    This is the measurement the forward test gets for free and should not waste. The whole
    accrual leans on one assumption -- M0's auction rail, a MEASURED zero half-spread for an
    on-close order in ADV tier A. That assumption covers the auction; what it explicitly does
    NOT cover is whether the broker's on-close order joins the cross at all
    (`measured_auction_leg`: "the live half of M0 and is not claimed here").

    Every fill this bot places answers exactly that question. `shortfall_bp` is signed ADVERSE
    -- positive means the fill was worse than the official close -- so a rail that is not what
    was assumed shows up as a drift away from zero rather than as a wash.

    AN ORDER THAT DID NOT FILL CANCELS ITS OWN DECISION. This is the second half of the
    2026-08-18 fix and it matters more than the first. The 08-17 MOC order expired with
    `filled_qty=0`, and nothing in the original code noticed: the decision it was supposed to
    execute sat in `pending_weights`, and two runs later `bind_pending_weight` would have filed
    a 0.724 weight into `weight_changes` and `settle` would have accrued a curve for a position
    the account never held. That is a fabricated track record -- the exact failure this
    programme exists to not commit -- and it is invisible in the PnL, because a phantom weight
    looks like a real one. So a terminal non-fill now DROPS the pending weight, and the previous
    weight stays in force, which is what the account actually did.
    """
    pending = state.get("pending_order")
    if not pending:
        return {"reconciled": False, "reason": "no order was outstanding"}
    raw = account.order(pending["order_id"])
    status = raw.get("status")
    filled_qty = int(float(raw.get("filled_qty") or 0))
    filled_price = raw.get("filled_avg_price")
    filled_price = float(filled_price) if filled_price not in (None, "") else None

    official = None
    for date, close in zip(series["dates"], series["closes"]):
        if date == pending["session_date"]:
            official = close
    shortfall_bp = None
    if filled_price is not None and official:
        sign = 1.0 if pending["side"] == "buy" else -1.0
        shortfall_bp = sign * (filled_price - official) / official * 10_000.0

    out = {
        "reconciled": True,
        "order_id": pending["order_id"],
        "placed_for_session": pending["session_date"],
        "side": pending["side"],
        "qty_ordered": pending["qty"],
        "status": status,
        "filled_qty": filled_qty,
        "filled_avg_price": filled_price,
        "official_close": official,
        "shortfall_bp_adverse_positive": shortfall_bp,
        "note": ("shortfall is the LIVE half of M0 that the cost model does not claim. A "
                 "persistent positive drift means on-close fills are not landing at the "
                 "official print and the whole accrual must be restated at the taker rail."),
    }
    if official is None:
        out["note"] = ("the session this order was placed in has not printed a daily bar yet; "
                       "the shortfall cannot be computed and is left null rather than zeroed.")

    qty_ordered = int(pending.get("qty") or 0)
    out["position_established"] = filled_qty > 0
    out["fill_completeness"] = (filled_qty / qty_ordered) if qty_ordered else None

    if filled_qty > 0:
        # A partial fill leaves the account holding less than the decision authorised. The
        # binding still files the TARGET weight, as it always has; recording the discrepancy
        # here rather than silently re-deriving the weight keeps the fidelity question visible
        # (forward_eval's FG3) instead of absorbing it into the curve.
        if filled_qty < qty_ordered:
            out["partial_fill_warning"] = (
                f"{filled_qty} of {qty_ordered} shares filled. The weight filed against this "
                "session is the TARGET weight, so the ledger is momentarily more exposed than "
                "the account. Not silently corrected: read it as an FG3 fidelity item.")
        state["pending_order"] = None
    elif status in NON_FILL_TERMINAL_STATUSES:
        dropped = (state.get("pending_weights") or {}).pop(pending["session_date"], None)
        out["decision_cancelled_by_non_fill"] = {
            "dropped_pending_weight": (dropped or {}).get("weight"),
            "for_session": pending["session_date"],
            "weight_still_in_force": float(state.get("prev_weight") or 0.0),
            "why": ("the order reached a terminal state with zero shares filled, so NO position "
                    "was established and no weight change occurred. The decision is dropped "
                    "rather than bound, because binding it would accrue a curve for a position "
                    "the account never held."),
        }
        state["pending_order"] = None
    else:
        # Not terminal and not filled -- still live at the broker. Leave BOTH the order and its
        # decision outstanding and re-ask next run. Dropping either one here would be guessing.
        out["still_outstanding"] = True
        out["note"] = (f"order status {status!r} is neither a fill nor terminal; the order and "
                       "its pending weight are left outstanding and re-checked next run.")
    return out


# Broker statuses that mean this order will never fill. `filled` and `partially_filled` are
# deliberately absent: those are handled by the filled_qty branch above.
NON_FILL_TERMINAL_STATUSES = frozenset({
    "expired", "canceled", "cancelled", "rejected", "done_for_day", "stopped", "suspended",
    "replaced",
})


def bind_pending_weight(state: dict, series: dict) -> dict:
    """File each on-close decision against the session it actually took effect in.

    A decision made during session D is established by the near-close order at ~close(D) and takes
    effect at session D+1. At run time on D the calendar has not printed D+1, and at run time
    on D+1 it still has not (the newest bar is D's) -- so a decision is normally bound two runs
    after it is made.

    **Every unbound decision is kept, not just the newest.** An earlier version held a single
    `pending_weight` and each run overwrote it, which silently dropped every decision before
    the last one and left the ledger with nothing to settle. Decisions are a queue.
    """
    pending = dict(state.get("pending_weights") or {})
    if not pending:
        return state
    remaining = {}
    for decided_on, entry in sorted(pending.items()):
        later = [d for d in series["dates"] if d > decided_on]
        if later:
            state["weight_changes"][later[0]] = float(entry["weight"])
        else:
            remaining[decided_on] = entry
    state["pending_weights"] = remaining
    return state


FRAMING = (
    "FORWARD TEST OF AN UNCERTIFIED RISK-SHAPING OVERLAY. T13 froze this rule on 1929-1989 and "
    "it is DEAD on the frozen held-out gate (drawdown p = 0.233, DSR = 0.355). It is run "
    "forward because 1990-2026 is burned for it, not because it was certified. Nothing in this "
    "log is a return claim, a profit forecast, or evidence of edge. PAPER ACCOUNT ONLY."
)


def _assert_clean(record: dict) -> None:
    """No credential may reach the ledger. Checked, not assumed."""
    key = os.environ.get("ALPACA_API_KEY_ID", "")
    secret = os.environ.get("ALPACA_API_SECRET_KEY", "")
    try:
        env_key, env_secret = load_env_credentials()
    except Refused:
        env_key = env_secret = ""
    text = json.dumps(record, default=str)
    for candidate in (key, secret, env_key, env_secret):
        if candidate and len(candidate) >= 8 and candidate in text:
            raise Refused(
                "a ledger record contains an API credential. Refusing to write it. This is a "
                "bug in whatever added the field, not something to redact and move on from."
            )


# ---------------------------------------------------------------------------
# Reading the track record
# ---------------------------------------------------------------------------

CRASH_YEARS_APART = 9.0          # T13: eight crashes in 36.6 held-out years
CRASHES_REQUIRED = 3             # the held-out window had three usable ones and still failed


def track_record(state: dict) -> dict:
    """The accruing numbers, with the reason they are not yet evidence attached to them.

    Every field that could be misread as a performance claim is shipped beside
    `certifiable`, `claims_licensed`, and `why_not_yet`. A number in this programme travels
    with what it is allowed to support.
    """
    n = state["sessions_settled"]
    years = n / 252.0
    curves, maxdd = state["curves"], state["maxdd"]
    return {
        "sessions_settled": n,
        "years_elapsed": years,
        "equity": dict(curves),
        "max_drawdown": dict(maxdd),
        "delta_maxdd_vs_benchmark_pp": (maxdd["benchmark"] - maxdd["model_withcash"]) * 100.0,
        "cumulative_cost_fraction": state["cum_cost_fraction"],
        "current_weight": state["prev_weight"],
        "certifiable": False,
        "why_not_yet": (
            f"{years:.2f} years elapsed. The T13 arithmetic that killed the in-sample version "
            f"applies unchanged here: a drawdown claim gets ONE observation per crash, crashes "
            f"arrive roughly one per {CRASH_YEARS_APART:.0f} years, and {CRASHES_REQUIRED} "
            f"usable crash comparisons is roughly {CRASH_YEARS_APART * CRASHES_REQUIRED:.0f} "
            "years. Until then this log records behaviour, not evidence."
        ),
        "claims_licensed": [],
        "claims_explicitly_not_licensed": [
            "the overlay makes money",
            "the overlay beats buy-and-hold",
            "the overlay reduces the drawdown you will live through",
            "any CAGR, Sharpe, or p-value computed on this sample",
        ],
        "benchmark_definition": (
            "un-overlaid buy-and-hold of the same instrument, same start, same cost model, "
            "one entry charged. NOTE: this is NOT the null that decides the question. T13's "
            "G1 null is a CONSTANT weight vol-matched to the strategy (de-risked buy-and-hold) "
            "and it is the gate that killed both families. It cannot be computed until the "
            "forward sample has a realised volatility worth matching."
        ),
    }


def report(ledger_path: pathlib.Path = None, state_path: pathlib.Path = None) -> dict:
    rule = frozen_rule()
    state = load_state(rule, state_path)
    records = read_ledger(ledger_path)
    sessions = [r for r in records if r.get("kind") == "session"]
    weights = [r["decision"]["target_weight"] for r in sessions if "decision" in r]
    submitted = [r for r in sessions if r.get("execution", {}).get("submitted")]
    return {
        "framing": FRAMING,
        "rule": rule,
        "runs_logged": len(sessions),
        "orders_submitted": len(submitted),
        "first_run": sessions[0]["session_date"] if sessions else None,
        "last_run": sessions[-1]["session_date"] if sessions else None,
        "weight_summary": {
            "n": len(weights),
            "min": min(weights) if weights else None,
            "max": max(weights) if weights else None,
            "mean": (sum(weights) / len(weights)) if weights else None,
            "latest": weights[-1] if weights else None,
        },
        "track_record": track_record(state),
        "how_to_read": HOW_TO_READ,
    }


HOW_TO_READ = [
    "1. START WITH THE DENOMINATOR, NOT THE EQUITY. `years_elapsed` is the only number that "
    "moves this from behaviour to evidence. Under ten years it is behaviour.",
    "2. THE COMPARISON THAT MATTERS IS NOT THE ONE IN `equity`. Beating buy-and-hold is not "
    "the question. T13's G1 null -- a CONSTANT weight vol-matched to whatever the overlay "
    "actually realised -- is the question, and it is what killed the in-sample version. It "
    "needs a forward sample long enough to have a realised volatility.",
    "3. `delta_maxdd_vs_benchmark_pp` IS A DIAGNOSTIC, NOT A RESULT. It compares against "
    "100% exposure, which is the easy comparison. Reporting it alone is exactly the error "
    "T13 §5i records about G3.",
    "4. A GOOD STRETCH WITHOUT A CRASH IS NOT INFORMATION ABOUT CRASHES. The whole claim "
    "under test is about the left tail. Calm-market outperformance is noise on that question, "
    "and calm-market underperformance is the KNOWN cost of the overlay (mean exposure ~0.74), "
    "not a surprise.",
    "5. CHECK `cost.total_bp` AGAINST `cost_if_taker_rail.total_bp` ON EVERY SETTLED SESSION. "
    "The auction-rail cost model is the one leaned-on assumption. If the realised fills stop "
    "matching the official close, the cheap rail was the wrong model and the accrual must be "
    "restated at the taker rail.",
    "6. CHECK THAT `weight_in_force` MOVED WHEN VOLATILITY DID. The overlay's whole behaviour "
    "is de-risking into rising realised vol. If it does not do that in the log, the "
    "implementation is broken and the accrual is meaningless regardless of its PnL.",
    "7. NOTHING HERE IS A REASON TO FUND A LIVE ACCOUNT. Live execution is owner-gated and "
    "this log cannot promote itself.",
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _selftest() -> int:
    """Wiring check on synthetic data. No network, no credentials, no ledger written."""
    rule = frozen_rule()

    # A deterministic series whose volatility doubles halfway: the weight MUST fall.
    closes, price = [], 100.0
    for i in range(400):
        step = (1 if (i * 7) % 3 else -1) * (0.004 if i < 200 else 0.010)
        price *= (1.0 + step)
        closes.append(price)
    calm = t13_target_weight(closes[:250], rule)
    wild = t13_target_weight(closes, rule)

    cost = m0_auction_cost_model()
    stress = stress_cost_model()
    move = _cost_fraction(cost, 0.72, 0.60, to_micros(650.0))
    move_stress = _cost_fraction(stress, 0.72, 0.60, to_micros(650.0))

    out = {
        "framing": FRAMING,
        "rule": rule,
        "weight_calm_regime": calm,
        "weight_high_vol_regime": wild,
        "weight_fell_with_volatility": wild["target_weight"] < calm["target_weight"],
        "cost_rail_bp_on_12pct_derisk": move["total_bp"],
        "cost_taker_rail_bp_on_12pct_derisk": move_stress["total_bp"],
        "rail_round_trip_bp": float(cost.round_trip_bp()),
        "taker_round_trip_bp": float(stress.round_trip_bp()),
        "authorisation_present": AUTHORISATION_PATH.exists(),
        "provenance": pin_report(),
    }
    if not out["weight_fell_with_volatility"]:
        raise Refused(
            "the selftest's volatility doubled and the target weight did not fall. The rule "
            "is mis-wired; refusing to report a pass."
        )
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.trading_bot.t4_forward",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("selftest", help="synthetic wiring check; no network, no ledger")
    sub.add_parser("status", help="print the frozen rule, the gate state, and the track record")
    sub.add_parser("report", help="the accruing track record, with the reading protocol")

    run = sub.add_parser("session", help="run one session")
    run.add_argument("--mode", default="dry-run", choices=("dry-run", "submit"))
    run.add_argument("--dry-run", action="store_true",
                     help="alias for --mode dry-run; the default")
    run.add_argument("--account-source", default="simulated", choices=("simulated", "broker"))
    run.add_argument("--equity", type=float, default=100_000.0,
                     help="notional to size against when --account-source simulated")
    run.add_argument("--no-cash-leg", action="store_true",
                     help="drop the T-bill accrual on the unexposed fraction; the ex-cash "
                          "curve is logged either way")
    run.add_argument("--refresh-cash", action="store_true",
                     help="best-effort FRED DTB3 refresh before settling")
    run.add_argument("--offline", action="store_true", help="cache only; never touch the network")
    run.add_argument("--force", action="store_true",
                     help="re-run a session date that is already in the ledger")
    run.add_argument("--skip-if-logged", action="store_true",
                     help="exit 0 instead of refusing when this session is already logged. "
                          "Lets a repeating scheduler retry harmlessly all afternoon.")
    run.add_argument("--skip-outside-window", action="store_true",
                     help="exit 0 when the clock is outside the final-minutes action window, "
                          "so a per-minute cron is a no-op except in the minutes that matter")

    args = parser.parse_args(argv)

    if args.command == "selftest":
        return _selftest()

    if args.command in ("status", "report"):
        payload = report()
        if args.command == "status":
            payload = {"framing": payload["framing"], "rule": payload["rule"],
                       "paper_submission_authorised": AUTHORISATION_PATH.exists(),
                       "ledger": str(LEDGER_PATH), "state": str(STATE_PATH),
                       "runs_logged": payload["runs_logged"],
                       "orders_submitted": payload["orders_submitted"],
                       "track_record": payload["track_record"]}
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    mode = "dry-run" if args.dry_run else args.mode

    # The two scheduler affordances. Both are SKIPS, never silent successes: each prints what
    # it did and why, so a log full of them cannot be mistaken for a log full of sessions.
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_et = _et_now(now_utc)
    if args.skip_outside_window and not _within_action_window(now_et):
        json.dump({"skipped": "outside the final-minutes action window",
                   "et_now": now_et.isoformat(), "window": ACTION_WINDOW_ET},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.skip_if_logged:
        session_date = now_et.date().isoformat()
        if any(rec.get("session_date") == session_date and rec.get("kind") == "session"
               for rec in read_ledger()):
            json.dump({"skipped": "this session is already in the ledger",
                       "session_date": session_date}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0

    record = run_session(
        mode=mode,
        account_source=args.account_source,
        simulated_equity=args.equity,
        allow_network=not args.offline,
        use_cash_leg=not args.no_cash_leg,
        refresh_cash=args.refresh_cash,
        force=args.force,
    )
    json.dump(record, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    try:
        sys.exit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
