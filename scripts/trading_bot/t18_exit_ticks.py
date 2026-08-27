#!/usr/bin/env python3
"""T18 -- the EXIT leg of the ORB rule, measured at TICK level. The never-measured half.

WHAT THIS IS AND WHY IT EXISTS
==============================
T17 ran the Zarattini/Barbon/Aziz opening-range-breakout rule through the honest harness and
died on the deflated-Sharpe gate -- but with an error bar that spans a held-out Sharpe of
+1.09 to -8.36. Two quantities, and only two, carry that spread:

  1. **The EXIT leg has never been measured.** B22B measured what a stop-order ENTRY actually
     fills at, tick by tick, and is FROZEN entry-only by design. The exit -- a stop-loss MARKET
     order mid-session, and an end-of-day market-on-close -- is priced in `costs.py` by
     `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG`: the entry's own magnitude charged again, plus a
     2.5 bp half-spread. That is a stand-in, and it says so in its own source string.
  2. **The entry-bar stop tie-break.** R is ~0.32 % of price on this universe and a one-minute
     bar in a top-relative-volume name routinely spans that, so on the bar that triggers the
     entry the bar's own low is often already through the stop -- but most of that low happened
     BEFORE the position existed. The frozen rule deems the stop hit only if the bar CLOSES
     through it (`close`); the maximally adverse reading (`full_bar`) charges the whole bar and
     takes the held-out Sharpe to -8.36. One-minute bars cannot say which is right. Ticks can.

This module measures both, from SIP trades and quotes, on a pinned sample of the stock-days
T17's held-out run actually traded.

WHAT IT DELIBERATELY DOES NOT DO
================================
It does not touch `scripts/b22b_slippage_harness.py`, whose sha256 is pinned in
`research/B22B_SLIPPAGE_PREREGISTRATION.json`. It IMPORTS that module and re-uses its
arithmetic -- the float boundary, the RFC3339 nanosecond parser, the prevailing-quote lookup,
the integer-index percentiles, the ATR/R units and the DST-derived session bounds -- and
asserts the pinned hash at import time, so a modified harness refuses rather than silently
changing a published number. The exit measurement is a NEW routine because B22B's scope limit
is structural: its own docstring says the exit is not measured and must not be inferred from
the entry.

THE MEASUREMENT, STATED AS A CHAIN
==================================
For one selected stock-day (symbol, day, direction, opening-range levels, ATR(14)), all in
integer micro-dollars, all from the SAME cached selection the T17 held-out run traded:

  E1  entry trigger  = the FIRST SIP trade at or through the opening-range level, at or after
                       09:35:00 ET. (B22B's rule, carried across.)
  E2  entry fill     = the prevailing NBBO ASK (long) / BID (short) at trigger + latency.
                       A stop order becomes a market order and crosses.
  E3  stop level     = entry fill -/+ R, R = 10 % of ATR(14). The paper's own stop.
  X1  exit trigger   = the FIRST SIP trade at or through the STOP level, strictly AFTER the
                       entry fill timestamp. This is the instant the broker's stop fires.
  X2  exit fill      = the prevailing NBBO BID (long) / ASK (short) at that trigger + latency.
                       A stop-loss is a MARKET order: it hits the bid / lifts the offer.
  X3  exit slippage  = stop level - exit fill (long) / exit fill - stop level (short).
                       POSITIVE IS ADVERSE, asserted, never assumed.
  C1  if the stop never fires, the position is held to the close and exits MOC. The realised
      fill is the OFFICIAL CLOSING PRINT (SIP condition '6', largest size where several venues
      print -- M0's convention, re-used not re-invented). The backtest credits the last
      1-minute bar's CLOSE. The gap between them, signed adverse, is the MOC exit slippage.
  C2  if there is NO official closing print, the MOC does not fill. The honest reading is that
      the position is unwound by hand across the closing spread: the fill is priced at the last
      NBBO BID (long) / ASK (short) before 16:00:00 ET. Absence is charged, never zeroed.

THE ENTRY-BAR TIE-BREAK, MEASURED THE SAME WAY
==============================================
For the SAME stop level (E3), three readings of "was the stop hit during the entry minute":

  close     -- the 1-minute bar containing the entry trigger CLOSES through the stop (frozen).
  full_bar  -- that bar's LOW/HIGH is through the stop (maximally adverse).
  TICK      -- a trade printed at or through the stop AFTER the entry fill timestamp and
               inside that same minute. This is the truth the other two approximate.

The disputed set is the stock-days where `full_bar` says hit and `close` says not. The measured
conditional rate on that set -- P(tick says hit | disputed) -- is the single number that
collapses the +1.09/-8.36 spread, and it is reported with its exact numerator and denominator.

FAIL-CLOSED, AND THE DIRECTION OF EVERY DEFAULT
===============================================
Absence is refusal, never zero (B22B's rule). No prevailing quote at a trigger is a refusal,
not a free fill. A stock-day whose entry never triggered is NOT a zero-slippage observation and
is kept in its own bucket. Missing bars, missing ATR, a non-positive R: refusals.

DECONTAMINATION. SIP trades include odd-lot and out-of-sequence prints, so a dislocated print
can trigger a level nobody could trade at. B22B/T6 handle this by dropping observations whose
TRIGGER PRINT is more than 0.1 ATR(14) -- one whole R -- beyond the level. The same rung, the
same direction, is applied here to BOTH the entry and the exit trigger, and the unfiltered
distribution is reported alongside so the filter cannot hide anything.

ARITHMETIC. Integer micro-dollars throughout, via B22B's `to_micros`, which is the only float
boundary. Percentiles by integer index, no interpolation. Sums and counts are recorded so that
a mean is derivable exactly.

USAGE
    python3 scripts/trading_bot/t18_exit_ticks.py sample        # print the pinned day sample
    python3 scripts/trading_bot/t18_exit_ticks.py plumbing      # DESIGN-window smoke test
    python3 scripts/trading_bot/t18_exit_ticks.py collect [n]   # the held-out measurement
    python3 scripts/trading_bot/t18_exit_ticks.py analyse       # distributions -> result JSON
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import random
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.t3_pressure_reversal import data_get, paged  # noqa: E402
from trading_bot.frozen import Refused  # noqa: E402

# --------------------------------------------------------------------------- pinned import

B22B_PATH = ROOT / "scripts" / "b22b_slippage_harness.py"
B22B_PINNED_SHA256 = "a0f1b4c434d89fe54edb4f835f7c5401a5dbc2ca023d155fd9aefad1d8b57baf"


def _load_pinned_b22b():
    """Import the frozen harness, refusing if its hash moved. Never edited, only consumed."""
    digest = hashlib.sha256(B22B_PATH.read_bytes()).hexdigest()
    if digest != B22B_PINNED_SHA256:
        raise Refused(
            f"{B22B_PATH} hashes {digest}, not the pinned {B22B_PINNED_SHA256} recorded in "
            "research/B22B_SLIPPAGE_PREREGISTRATION.json. The harness is frozen; a T18 number "
            "computed against a changed harness is not comparable to the B22B entry it is "
            "supposed to complete."
        )
    spec = importlib.util.spec_from_file_location("b22b_pinned", B22B_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B22B = _load_pinned_b22b()

to_micros = B22B.to_micros
to_shares = B22B.to_shares
parse_rfc3339_ns = B22B.parse_rfc3339_ns
quote_at = B22B.quote_at
percentile_by_index = B22B.percentile_by_index
distribution_summary = B22B.distribution_summary
session_bound_ns = B22B.session_bound_ns
et_offset_hours = B22B.et_offset_hours
r_unit_micros = B22B.r_unit_micros
MICROS = B22B.MICROS

# --------------------------------------------------------------------------- frozen constants

CACHE_T17 = ROOT / "research" / "data" / "t17_cache"
CACHE = ROOT / "research" / "data" / "t18_cache"
OUT = ROOT / "research" / "trading_bot"

# The T17 windows, imported rather than retyped, so the sample cannot drift off the held-out set.
from trading_bot import t17_orb as ORB  # noqa: E402

HELDOUT_START, HELDOUT_END = ORB.HELDOUT_START, ORB.HELDOUT_END
DESIGN_START, DESIGN_END = ORB.DESIGN_START, ORB.DESIGN_END

SAMPLE_SEED = 20260818            # pinned before the sample is drawn
N_SESSIONS = 50                   # ~1,000 stock-days, against B22B's 429 entry observations
PLUMBING_SESSIONS = 6             # DESIGN-window only; never enters a held-out statistic

LATENCY_LADDER_MS = B22B.LATENCY_LADDER_MS       # (0, 100, 500, 1000)
VERDICT_LATENCY_MS = 100                          # B22B's verdict rung, carried across
DECONTAMINATION_ATR = 0.1                         # the T6/T17 rung: one whole R
OFFICIAL_CLOSE_CONDITIONS = {"6"}                 # M0's convention for the official close print

QUOTE_WINDOW_BEFORE_NS = 5_000_000_000            # 5 s of quote history before a trigger
QUOTE_WINDOW_AFTER_NS = 3_000_000_000             # 3 s after, to cover the whole latency ladder
QUOTE_WIDENING_NS = (5_000_000_000, 60_000_000_000, 900_000_000_000, 25_200_000_000_000)
CLOSING_QUOTE_WINDOW_NS = 60_000_000_000          # last minute, for the no-print fallback

WORKERS = 8


# --------------------------------------------------------------------------- sample

def sample_sessions(days: list, n: int, seed: int) -> list:
    """A year-stratified sample of sessions, drawn from a pinned seed.

    Stratified rather than uniform so that no single regime can dominate by luck of the draw:
    the allocation per calendar year is proportional to that year's share of the sessions, with
    the remainder handed out largest-fraction-first and ties broken on the year label. A
    uniform draw of 50 from 1,158 has a real chance of putting a third of the sample in one
    year, and this measurement is about a microstructure that changed over the window.
    """
    if n > len(days):
        raise Refused(f"asked for {n} sessions, only {len(days)} available")
    by_year = defaultdict(list)
    for d in days:
        by_year[d[:4]].append(d)
    years = sorted(by_year)
    exact = {y: n * len(by_year[y]) / len(days) for y in years}
    alloc = {y: int(exact[y]) for y in years}
    remainder = n - sum(alloc.values())
    for y in sorted(years, key=lambda y: (-(exact[y] - int(exact[y])), y))[:remainder]:
        alloc[y] += 1
    rng = random.Random(seed)
    out = []
    for y in years:
        k = min(alloc[y], len(by_year[y]))
        out.extend(rng.sample(sorted(by_year[y]), k))
    return sorted(out)


def heldout_sessions() -> list:
    selection = json.loads((CACHE_T17 / "selection.json").read_text())
    return [d for d in sorted(selection) if HELDOUT_START <= d <= HELDOUT_END]


def design_sessions() -> list:
    selection = json.loads((CACHE_T17 / "selection.json").read_text())
    return [d for d in sorted(selection) if DESIGN_START <= d <= DESIGN_END]


# --------------------------------------------------------------------------- tick primitives

def sorted_trades(rows: list) -> list:
    """(ns, price_micros, size, conditions) in canonical time order."""
    out = [(parse_rfc3339_ns(t["t"]), to_micros(t["p"]), to_shares(t["s"]),
            tuple(t.get("c") or ())) for t in rows]
    out.sort(key=lambda r: r[0])
    return out


def sorted_quotes(rows: list) -> list:
    """B22B's quote tuple shape, so `quote_at` can be re-used unmodified."""
    out = [(parse_rfc3339_ns(q["t"]), to_micros(q["bp"]), to_shares(q["bs"]),
            to_micros(q["ap"]), to_shares(q["as"])) for q in rows]
    out.sort(key=lambda r: r[0])
    return out


def first_through(trades: list, level: int, side: str, after_ns: int, strictly_after: bool):
    """First trade at or through `level`. `side` 'up' means price >= level, 'down' means <=.

    Returns None when the level is never touched. None is NOT a zero-slippage observation --
    the caller keeps it in its own bucket, which is B22B's rule and the reason its median is
    honest.
    """
    if side not in ("up", "down"):
        raise Refused(f"side must be 'up' or 'down', got {side!r}")
    for ns, price, size, cond in trades:
        if ns < after_ns or (strictly_after and ns == after_ns):
            continue
        if (price >= level) if side == "up" else (price <= level):
            return {"ns": ns, "price": price, "size": size, "conditions": cond}
    return None


def fill_at(quotes: list, at_ns: int, take: str):
    """The price a MARKET order pays at `at_ns`: 'ask' lifts the offer, 'bid' hits the bid."""
    stamp_ns, bid, bid_size, ask, ask_size = quote_at(quotes, at_ns)
    if take == "ask":
        return {"fill": ask, "resting": ask_size, "spread": ask - bid,
                "quote_age_ns": at_ns - stamp_ns}
    if take == "bid":
        return {"fill": bid, "resting": bid_size, "spread": ask - bid,
                "quote_age_ns": at_ns - stamp_ns}
    raise Refused(f"take must be 'bid' or 'ask', got {take!r}")


def quotes_around(quotes_for, at_ns: int) -> list:
    """NBBO covering `at_ns`, widening the lookback until a quote actually precedes it.

    A thin name can go minutes without a quote update, and a 5-second window that happens to
    contain none is a property of MY window, not of the market: there WAS a prevailing quote.
    So the lookback widens 5 s -> 1 min -> 15 min -> the whole session before giving up, and
    only then refuses. Widening is not a default: the quote returned is still the last one
    published at or before the instant, exactly as B22B's `quote_at` defines it.
    """
    for widen in QUOTE_WIDENING_NS:
        rows = quotes_for(at_ns - widen, at_ns + QUOTE_WINDOW_AFTER_NS)
        if rows and rows[0][0] <= at_ns:
            return rows
    raise Refused("no quote published at or before the trigger anywhere in the session; "
                  "refusing to synthesise a fill")


def adverse(direction: str, leg: str, reference: int, fill: int) -> int:
    """Signed so POSITIVE IS ALWAYS WORSE FOR THE TRADER. Asserted, not assumed.

    entry: a long buys, so paying ABOVE the reference is adverse; a short sells, so filling
    BELOW it is adverse. exit: a long SELLS out, so filling BELOW the reference is adverse; a
    short BUYS back, so filling ABOVE it is adverse. Getting this backwards is exactly how a
    cost is reported as a benefit, so both legs are written out rather than shared.
    """
    if leg == "entry":
        return fill - reference if direction == "long" else reference - fill
    if leg == "exit":
        return reference - fill if direction == "long" else fill - reference
    raise Refused(f"leg must be 'entry' or 'exit', got {leg!r}")


def in_r_bp(slip_micros: int, atr_micros: int) -> int:
    """Slippage in basis points of R, R = 10 % of ATR(14). B22B's headline unit, its formula."""
    if atr_micros <= 0:
        raise Refused("R is undefined without a positive ATR")
    return (slip_micros * 100_000) // atr_micros


def in_centibp(slip_micros: int, price_micros: int) -> int:
    """Slippage in CENTI-basis-points of notional. Whole bp truncate this measurement to zero."""
    if price_micros <= 0:
        raise Refused("a notional fraction needs a positive price")
    return (slip_micros * 1_000_000) // price_micros


def close_reference_ns(day: str, last_bar_ns: int) -> int:
    """The instant the closing NBBO is read at: 16:00:00 ET, or the last bar + 1 minute if the
    session ended early. A half-day's 15:59 reference would otherwise sit hours after its own
    close and price the unwind against a stale after-hours quote -- the same trap M0 excluded
    early closes for."""
    import datetime
    regular = session_bound_ns(datetime.date.fromisoformat(day), B22B.SESSION_CLOSE)
    return min(regular, last_bar_ns + 60_000_000_000)


def official_close_print(auction_rows: list):
    """The official closing print: SIP condition '6', largest size where several venues print."""
    prints = [p for p in auction_rows or []
              if str(p.get("c")) in OFFICIAL_CLOSE_CONDITIONS]
    if not prints:
        return None
    best = max(prints, key=lambda p: to_shares(p["s"]))
    return {"price": to_micros(best["p"]), "size": to_shares(best["s"]),
            "ns": parse_rfc3339_ns(best["t"]), "venue": best.get("x")}


# --------------------------------------------------------------------------- the measurement

def measure_stock_day(*, symbol, day, direction, entry_level, atr_micros, bars,
                      trades, quotes_for, auction_rows, close_quotes):
    """One selected stock-day, measured from ticks. Returns the record, or a refusal.

    `bars` are the cached 1-minute SIP bars from 09:35, as [iso, o, h, l, c, v] with float
    prices -- the SAME series the T17 backtest ran on, so the bar rules being compared are the
    ones that were actually used. `quotes_for(ns_lo, ns_hi)` fetches NBBO in a window; it is a
    callback so that the measurement code is testable without a network.
    """
    if direction not in ("long", "short"):
        raise Refused(f"direction must be long or short, got {direction!r}")
    r_micros = r_unit_micros(atr_micros)
    if r_micros <= 0:
        raise Refused(f"{symbol} {day}: non-positive R")
    if not bars:
        raise Refused(f"{symbol} {day}: no bars; a stock-day with no data is missing, not flat")

    up = direction == "long"
    bar_ns = [parse_rfc3339_ns(b[0]) for b in bars]
    session_first_ns = bar_ns[0]
    session_last_ns = bar_ns[-1]

    rec = {"symbol": symbol, "day": day, "direction": direction,
           "entry_level_micros": entry_level, "atr_micros": atr_micros,
           "r_micros": r_micros,
           "bar_close_mark_micros": to_micros(bars[-1][4]),
           "n_trades_seen": len(trades)}

    entry = first_through(trades, entry_level, "up" if up else "down",
                          session_first_ns, strictly_after=False)
    if entry is None:
        rec["outcome"] = "NO_TRIGGER"
        return rec

    rec["entry_trigger_ns"] = entry["ns"]
    rec["entry_trigger_price_micros"] = entry["price"]
    # How far THROUGH the level the triggering print was, in ATR -- the decontamination axis.
    through = (entry["price"] - entry_level) if up else (entry_level - entry["price"])
    rec["entry_through_atr"] = max(0, through) / atr_micros

    eq = quotes_around(quotes_for, entry["ns"])

    rec["entry"] = {}
    for ms in LATENCY_LADDER_MS:
        f = fill_at(eq, entry["ns"] + ms * 1_000_000, "ask" if up else "bid")
        slip = adverse(direction, "entry", entry_level, f["fill"])
        rec["entry"][str(ms)] = {
            "fill_micros": f["fill"], "slippage_micros": slip,
            "slippage_r_bp": in_r_bp(slip, atr_micros),
            "slippage_centibp": in_centibp(slip, f["fill"]),
            "spread_micros": f["spread"], "resting_shares": f["resting"],
            "quote_age_ns": f["quote_age_ns"]}

    fill = rec["entry"][str(VERDICT_LATENCY_MS)]["fill_micros"]
    stop_level = fill - r_micros if up else fill + r_micros
    rec["stop_level_micros"] = stop_level
    rec["entry_fill_micros"] = fill

    # ---- the entry BAR, and the three readings of "was the stop hit inside it"
    entry_bar_index = max(i for i, ns in enumerate(bar_ns) if ns <= entry["ns"])
    entry_bar = bars[entry_bar_index]
    entry_bar_end_ns = bar_ns[entry_bar_index] + 60_000_000_000
    rec["entry_bar_index"] = entry_bar_index
    rec["entry_bar_close_rule_hit"] = bool(
        to_micros(entry_bar[4]) <= stop_level if up else to_micros(entry_bar[4]) >= stop_level)
    rec["entry_bar_full_bar_rule_hit"] = bool(
        to_micros(entry_bar[3]) <= stop_level if up else to_micros(entry_bar[2]) >= stop_level)

    # ---- the MOC leg, measured on EVERY stock-day, not only the ones that reached the close.
    # The gap between the official closing print and the last-bar mark the backtest credits is a
    # property of the stock-day, not of this particular position's outcome. Measuring it only on
    # the stock-days whose stop happened not to fire would (a) throw away most of the sample and
    # (b) condition the MOC cost on the position having been a winner, which is exactly the kind
    # of selection this programme is required to avoid. It is recorded here for all of them and
    # is the EXIT only when the stop never fires.
    mark = rec["bar_close_mark_micros"]
    print_row = official_close_print(auction_rows)
    if print_row is not None:
        slip = adverse(direction, "exit", mark, print_row["price"])
        rec["close_print"] = print_row
        rec["moc"] = {"basis": "official_close_print",
                      "fill_micros": print_row["price"], "slippage_micros": slip,
                      "slippage_r_bp": in_r_bp(slip, atr_micros),
                      "slippage_centibp": in_centibp(slip, print_row["price"]),
                      "print_size": print_row["size"]}
    else:
        # C2 -- no official print: the MOC does not fill and the position is unwound by hand.
        ref_ns = close_reference_ns(day, session_last_ns)
        cq = (close_quotes if (close_quotes and close_quotes[0][0] <= ref_ns)
              else quotes_around(quotes_for, ref_ns))
        f = fill_at(cq, ref_ns, "bid" if up else "ask")
        slip = adverse(direction, "exit", mark, f["fill"])
        rec["close_print"] = None
        rec["moc"] = {"basis": "no_official_print_unwound_at_nbbo",
                      "fill_micros": f["fill"], "slippage_micros": slip,
                      "slippage_r_bp": in_r_bp(slip, atr_micros),
                      "slippage_centibp": in_centibp(slip, f["fill"]),
                      "spread_micros": f["spread"]}

    # ---- the exit trigger: the first print at or through the stop AFTER the entry fill.
    # The position does not exist until the entry fills, so the search starts at the FILL
    # instant (trigger + the verdict latency), not at the trigger. Counting a breach that
    # happened in the routing window would stop out a position nobody held yet -- adverse, but
    # adverse in a way that is simply wrong. Any such breach is recorded instead.
    fill_ns = entry["ns"] + VERDICT_LATENCY_MS * 1_000_000
    in_flight = first_through(trades, stop_level, "down" if up else "up",
                              entry["ns"], strictly_after=True)
    rec["stop_breached_before_fill"] = bool(in_flight is not None and in_flight["ns"] < fill_ns)
    exit_trigger = first_through(trades, stop_level, "down" if up else "up",
                                 fill_ns, strictly_after=False)
    rec["entry_bar_tick_rule_hit"] = bool(
        exit_trigger is not None and exit_trigger["ns"] < entry_bar_end_ns)

    if exit_trigger is not None:
        rec["outcome"] = "STOPPED"
        rec["exit_trigger_ns"] = exit_trigger["ns"]
        rec["exit_trigger_price_micros"] = exit_trigger["price"]
        rec["seconds_entry_to_stop"] = (exit_trigger["ns"] - entry["ns"]) / 1e9
        xthrough = ((stop_level - exit_trigger["price"]) if up
                    else (exit_trigger["price"] - stop_level))
        rec["exit_through_atr"] = max(0, xthrough) / atr_micros
        xq = quotes_around(quotes_for, exit_trigger["ns"])
        rec["exit"] = {}
        for ms in LATENCY_LADDER_MS:
            f = fill_at(xq, exit_trigger["ns"] + ms * 1_000_000, "bid" if up else "ask")
            slip = adverse(direction, "exit", stop_level, f["fill"])
            rec["exit"][str(ms)] = {
                "fill_micros": f["fill"], "slippage_micros": slip,
                "slippage_r_bp": in_r_bp(slip, atr_micros),
                "slippage_centibp": in_centibp(slip, f["fill"]),
                "spread_micros": f["spread"], "resting_shares": f["resting"],
                "quote_age_ns": f["quote_age_ns"]}
        return rec

    # ---- no stop: the position is held to the close and exits MOC, already priced above.
    rec["outcome"] = "CLOSE"
    rec["moc_is_the_exit"] = True
    return rec


# --------------------------------------------------------------------------- collection

def _iso(ns: int) -> str:
    import datetime
    return (datetime.datetime.fromtimestamp(ns // 1_000_000_000, datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S") + f".{ns % 1_000_000_000:09d}Z")


def fetch_trades(symbol: str, start_ns: int, end_ns: int) -> list:
    rows = []
    for block in paged("/v2/stocks/trades",
                       {"symbols": symbol, "start": _iso(start_ns), "end": _iso(end_ns),
                        "feed": "sip", "limit": 10000}, "trades"):
        rows.extend(block.get(symbol) or [])
    return rows


def fetch_quotes(symbol: str, start_ns: int, end_ns: int) -> list:
    rows = []
    for block in paged("/v2/stocks/quotes",
                       {"symbols": symbol, "start": _iso(start_ns), "end": _iso(end_ns),
                        "feed": "sip", "limit": 10000}, "quotes"):
        rows.extend(block.get(symbol) or [])
    return rows


def fetch_auctions(symbols: list, day: str) -> dict:
    out = {}
    payload = data_get("/v2/stocks/auctions",
                       {"symbols": ",".join(symbols), "start": day, "end": day,
                        "feed": "sip", "limit": 10000})
    for sym, rows in (payload.get("auctions") or {}).items():
        for row in rows:
            if row.get("d") == day:
                out[sym] = row.get("c") or []
    return out


def collect_day(day: str, picks: list, paths: dict) -> list:
    """Every selected name on one session. Refusals are recorded, never swallowed silently."""
    auctions = fetch_auctions([p[1] for p in picks], day)
    records = []

    def work(item):
        rank, (relvol, sym, cdir, or_high, or_low, atr) = item
        if cdir not in ("long", "short"):
            return {"symbol": sym, "day": day, "outcome": "NO_DIRECTION"}
        path = paths.get(sym)
        if not path:
            return {"symbol": sym, "day": day, "outcome": "NO_PATH"}
        bars = path
        start_ns = parse_rfc3339_ns(bars[0][0])
        end_ns = parse_rfc3339_ns(bars[-1][0]) + 120_000_000_000
        trades = sorted_trades(fetch_trades(sym, start_ns, end_ns))
        if not trades:
            return {"symbol": sym, "day": day, "outcome": "NO_TRADES"}
        cache = {}

        def quotes_for(lo, hi):
            key = (lo // 1_000_000_000, hi // 1_000_000_000)
            if key not in cache:
                cache[key] = sorted_quotes(fetch_quotes(sym, lo, hi))
            return cache[key]

        last_bar_ns = parse_rfc3339_ns(bars[-1][0])
        ref_ns = close_reference_ns(day, last_bar_ns)
        closing = sorted_quotes(fetch_quotes(sym, ref_ns - CLOSING_QUOTE_WINDOW_NS, ref_ns))
        try:
            rec = measure_stock_day(
                symbol=sym, day=day, direction=cdir,
                entry_level=(or_high if cdir == "long" else or_low),
                atr_micros=atr, bars=bars, trades=trades, quotes_for=quotes_for,
                auction_rows=auctions.get(sym), close_quotes=closing)
        except (Refused, B22B.Refused) as exc:
            # The pinned harness defines its OWN Refused; catching only ours would let a
            # legitimate refusal escape as a crash and lose a whole session's work.
            return {"symbol": sym, "day": day, "outcome": "REFUSED", "reason": str(exc)}
        rec["rank"] = rank
        rec["relvol"] = relvol
        return rec

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for rec in pool.map(work, list(enumerate(picks))):
            records.append(rec)
    return records


def collect(days: list, tag: str):
    CACHE.mkdir(parents=True, exist_ok=True)
    selection = json.loads((CACHE_T17 / "selection.json").read_text())
    done = 0
    for day in days:
        out_path = CACHE / f"{tag}_{day}.json"
        if out_path.exists():
            done += 1
            continue
        picks = selection.get(day) or []
        path_file = CACHE_T17 / "paths" / f"{day}.json"
        if not picks or not path_file.exists():
            out_path.write_text(json.dumps({"day": day, "records": [],
                                            "note": "no selection or no path file"}))
            continue
        paths = json.loads(path_file.read_text())
        records = collect_day(day, picks, paths)
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"day": day, "records": records}))
        tmp.rename(out_path)
        done += 1
        counts = defaultdict(int)
        for r in records:
            counts[r.get("outcome")] += 1
        print(f"{tag} {day}: {dict(counts)}  ({done}/{len(days)})", flush=True)


# --------------------------------------------------------------------------- analysis

def _summary(values: list) -> dict:
    if not values:
        return {"n": 0}
    s = distribution_summary(values)
    s["mean_float"] = s["sum"] / s["n"]
    s["adverse"] = sum(1 for v in values if v > 0)
    s["exactly_zero"] = sum(1 for v in values if v == 0)
    s["favourable"] = sum(1 for v in values if v < 0)
    return s


def load_records(tag: str) -> list:
    rows = []
    for path in sorted(CACHE.glob(f"{tag}_*.json")):
        rows.extend(json.loads(path.read_text())["records"])
    return rows


def analyse(tag: str = "heldout") -> dict:
    records = load_records(tag)
    triggered = [r for r in records if r.get("outcome") in ("STOPPED", "CLOSE")]
    clean_entry = [r for r in triggered
                   if r.get("entry_through_atr", 9e9) <= DECONTAMINATION_ATR]
    stopped = [r for r in triggered if r["outcome"] == "STOPPED"]
    stopped_clean = [r for r in stopped
                     if r.get("exit_through_atr", 9e9) <= DECONTAMINATION_ATR
                     and r.get("entry_through_atr", 9e9) <= DECONTAMINATION_ATR]
    closed = [r for r in triggered if r["outcome"] == "CLOSE"]

    report = {
        "tag": tag,
        "sessions": len({r["day"] for r in records}),
        "stock_days": len(records),
        "outcomes": dict(sorted(
            (k, sum(1 for r in records if r.get("outcome") == k))
            for k in {r.get("outcome") for r in records})),
        "decontamination_atr": DECONTAMINATION_ATR,
        "verdict_latency_ms": VERDICT_LATENCY_MS,
    }

    # --- the EXIT stop leg, the thing nobody had measured
    exit_stop = {}
    for ms in LATENCY_LADDER_MS:
        key = str(ms)
        exit_stop[key] = {
            "r_bp": _summary([r["exit"][key]["slippage_r_bp"] for r in stopped]),
            "r_bp_decontaminated": _summary(
                [r["exit"][key]["slippage_r_bp"] for r in stopped_clean]),
            "centibp": _summary([r["exit"][key]["slippage_centibp"] for r in stopped]),
            "centibp_decontaminated": _summary(
                [r["exit"][key]["slippage_centibp"] for r in stopped_clean]),
            "spread_bp": _summary([in_centibp(r["exit"][key]["spread_micros"],
                                              r["exit"][key]["fill_micros"]) for r in stopped]),
            "resting_shares": _summary([r["exit"][key]["resting_shares"] for r in stopped]),
        }
    report["exit_stop_leg"] = exit_stop

    # --- the ENTRY leg, recomputed here only as a CONSISTENCY CHECK against B22B
    entry_check = {}
    for ms in LATENCY_LADDER_MS:
        key = str(ms)
        entry_check[key] = {
            "r_bp": _summary([r["entry"][key]["slippage_r_bp"] for r in triggered]),
            "r_bp_decontaminated": _summary(
                [r["entry"][key]["slippage_r_bp"] for r in clean_entry]),
            "centibp_decontaminated": _summary(
                [r["entry"][key]["slippage_centibp"] for r in clean_entry]),
        }
    report["entry_leg_consistency_check"] = entry_check

    # --- the MOC leg, over EVERY triggered stock-day (see measure_stock_day), with the subset
    # that actually exited MOC broken out.
    moc_all = [r for r in triggered if "moc" in r]
    with_print = [r for r in moc_all if r.get("close_print")]
    no_print = [r for r in moc_all if r.get("moc", {}).get("basis")
                == "no_official_print_unwound_at_nbbo"]
    report["moc_leg"] = {
        "n_stock_days_priced": len(moc_all),
        "n_close_exits": len(closed),
        "close_exit_only_r_bp": _summary([r["moc"]["slippage_r_bp"] for r in closed
                                          if "moc" in r]),
        "n_with_official_print": len(with_print),
        "official_print_rate": (len(with_print) / len(moc_all)) if moc_all else None,
        "r_bp": _summary([r["moc"]["slippage_r_bp"] for r in moc_all]),
        "centibp": _summary([r["moc"]["slippage_centibp"] for r in moc_all]),
        "r_bp_decontaminated": _summary(
            [r["moc"]["slippage_r_bp"] for r in moc_all
             if r.get("entry_through_atr", 9e9) <= DECONTAMINATION_ATR]),
        "centibp_decontaminated": _summary(
            [r["moc"]["slippage_centibp"] for r in moc_all
             if r.get("entry_through_atr", 9e9) <= DECONTAMINATION_ATR]),
        "r_bp_with_print": _summary([r["moc"]["slippage_r_bp"] for r in with_print]),
        "centibp_with_print": _summary([r["moc"]["slippage_centibp"] for r in with_print]),
        "r_bp_no_print": _summary([r["moc"]["slippage_r_bp"] for r in no_print]),
        "print_notional_usd_p50": (
            percentile_by_index(sorted(r["close_print"]["size"] * r["close_print"]["price"]
                                       // MICROS for r in with_print), 50, 100)
            if with_print else None),
    }

    # --- the entry-bar tie-break
    def flag(r, name):
        return bool(r.get(name))
    disputed = [r for r in triggered
                if flag(r, "entry_bar_full_bar_rule_hit") and not flag(r, "entry_bar_close_rule_hit")]
    agree_hit = [r for r in triggered
                 if flag(r, "entry_bar_full_bar_rule_hit") and flag(r, "entry_bar_close_rule_hit")]
    neither = [r for r in triggered if not flag(r, "entry_bar_full_bar_rule_hit")]
    def quote_confirmed(r):
        """A breach print is CONFIRMED when the NBBO moved with it.

        A single out-of-sequence print can be through a level nobody could trade at -- the
        plumbing pass found a short whose stop was 'breached' by a print 7 R away while the ask
        sat 1.3 R on the other side of it. That print is not a stop-out. The confirmation is
        that the fill a market order would actually receive is itself at or through the stop,
        i.e. the measured exit slippage is not favourable. Reported ALONGSIDE the raw rule, never
        instead of it, because the raw rule is the adverse one and the choice between them is a
        finding, not a preference."""
        ex = r.get("exit", {}).get(str(VERDICT_LATENCY_MS))
        return bool(ex is not None and ex["slippage_micros"] >= 0)

    report["entry_bar_tie_break"] = {
        "n_triggered": len(triggered),
        "n_tick_says_hit_quote_confirmed": sum(
            1 for r in triggered if flag(r, "entry_bar_tick_rule_hit") and quote_confirmed(r)),
        "disputed_quote_confirmed": {
            "n": len([r for r in triggered if flag(r, "entry_bar_full_bar_rule_hit")
                      and not flag(r, "entry_bar_close_rule_hit")]),
            "tick_hit": sum(1 for r in triggered
                            if flag(r, "entry_bar_full_bar_rule_hit")
                            and not flag(r, "entry_bar_close_rule_hit")
                            and flag(r, "entry_bar_tick_rule_hit") and quote_confirmed(r)),
        },
        "n_full_bar_says_hit": sum(1 for r in triggered if flag(r, "entry_bar_full_bar_rule_hit")),
        "n_close_says_hit": sum(1 for r in triggered if flag(r, "entry_bar_close_rule_hit")),
        "n_tick_says_hit": sum(1 for r in triggered if flag(r, "entry_bar_tick_rule_hit")),
        "disputed": {
            "n": len(disputed),
            "tick_hit": sum(1 for r in disputed if flag(r, "entry_bar_tick_rule_hit")),
            "p_tick_hit": (sum(1 for r in disputed if flag(r, "entry_bar_tick_rule_hit"))
                           / len(disputed)) if disputed else None,
        },
        "both_rules_say_hit": {
            "n": len(agree_hit),
            "tick_hit": sum(1 for r in agree_hit if flag(r, "entry_bar_tick_rule_hit")),
        },
        "neither_rule_says_hit": {
            "n": len(neither),
            "tick_hit": sum(1 for r in neither if flag(r, "entry_bar_tick_rule_hit")),
        },
        "seconds_entry_to_stop_p50": (
            percentile_by_index(sorted(int(r["seconds_entry_to_stop"] * 1000)
                                       for r in stopped), 50, 100) / 1000.0 if stopped else None),
    }

    # --- tick truth vs the bar simulation's own outcome mix
    entry_bar_stops = [r for r in stopped if r.get("entry_bar_tick_rule_hit")]
    report["outcome_mix_tick_truth"] = {
        "stopped": len(stopped), "close": len(closed),
        "stopped_share": len(stopped) / len(triggered) if triggered else None,
        "no_trigger": sum(1 for r in records if r.get("outcome") == "NO_TRIGGER"),
        "stopped_inside_the_entry_minute": len(entry_bar_stops),
        "stopped_contaminated_trigger_excluded": len(stopped) - len(stopped_clean),
        "stop_trigger_quote_confirmed": sum(
            1 for r in stopped
            if r["exit"][str(VERDICT_LATENCY_MS)]["slippage_micros"] >= 0),
    }
    # --- TICK TRUTH, per trade, in the strategy's own unit.
    # entry fill -> exit fill, both measured, no bar approximation anywhere in the chain. This
    # is not a Sharpe (50 sessions cannot carry one) and it is not the verdict; it is the
    # per-trade edge the re-cost has to be consistent with.
    def net_r(r):
        sign = 1 if r["direction"] == "long" else -1
        ex = (r["exit"][str(VERDICT_LATENCY_MS)]["fill_micros"] if r["outcome"] == "STOPPED"
              else r["moc"]["fill_micros"])
        return (sign * (ex - r["entry_fill_micros"]) * 10_000) // r["r_micros"]

    clean_all = [r for r in triggered
                 if r.get("entry_through_atr", 9e9) <= DECONTAMINATION_ATR
                 and (r["outcome"] != "STOPPED"
                      or r.get("exit_through_atr", 9e9) <= DECONTAMINATION_ATR)]
    report["tick_truth_per_trade_r_bp"] = {
        "all_triggered": _summary([net_r(r) for r in triggered]),
        "decontaminated": _summary([net_r(r) for r in clean_all]),
        "stopped_only": _summary([net_r(r) for r in stopped_clean]),
        "close_only": _summary([net_r(r) for r in closed
                                if r.get("entry_through_atr", 9e9) <= DECONTAMINATION_ATR]),
        "unit_note": "basis points of R; 10000 = +1R. Entry fill to exit fill, both measured. "
                     "SIGN: here positive is PROFIT, not cost -- so the 'adverse'/'favourable' "
                     "counters that _summary attaches read backwards in THIS block only, and "
                     "are left in place rather than silently relabelled.",
    }

    # The exit pool split, because a stop that fires seconds after the entry and one that fires
    # hours later are not obviously the same measurement.
    key = str(VERDICT_LATENCY_MS)
    report["exit_pool_composition"] = {
        "entry_minute_stops_r_bp": _summary(
            [r["exit"][key]["slippage_r_bp"] for r in stopped_clean
             if r.get("entry_bar_tick_rule_hit")]),
        "later_stops_r_bp": _summary(
            [r["exit"][key]["slippage_r_bp"] for r in stopped_clean
             if not r.get("entry_bar_tick_rule_hit")]),
    }
    return report


def main(argv):
    what = argv[1] if len(argv) > 1 else "sample"
    if what == "sample":
        days = sample_sessions(heldout_sessions(), N_SESSIONS, SAMPLE_SEED)
        by_year = defaultdict(int)
        for d in days:
            by_year[d[:4]] += 1
        print(json.dumps({"seed": SAMPLE_SEED, "n": len(days), "by_year": dict(by_year),
                          "days": days}, indent=1))
    elif what == "plumbing":
        days = sample_sessions(design_sessions(), PLUMBING_SESSIONS, SAMPLE_SEED)
        print(f"PLUMBING on DESIGN-window days {days} -- never enters a held-out statistic")
        collect(days, "plumbing")
        print(json.dumps(analyse("plumbing"), indent=1)[:4000])
    elif what == "collect":
        # Optional "i/k" slice: the SAME pinned day list, split across processes so a long pull
        # is not a long wait. Slicing is by index into the pinned list and changes no day.
        days = sample_sessions(heldout_sessions(), N_SESSIONS, SAMPLE_SEED)
        if len(argv) > 2 and "/" in argv[2]:
            i, k = (int(x) for x in argv[2].split("/"))
            days = [d for j, d in enumerate(days) if j % k == i]
        elif len(argv) > 2:
            days = days[:int(argv[2])]
        collect(days, "heldout")
    elif what == "analyse":
        report = analyse("heldout")
        (OUT / "T18_EXIT_MEASUREMENT.json").write_text(json.dumps(report, indent=1))
        print(json.dumps(report, indent=1)[:6000])
    else:
        raise SystemExit(f"unknown stage {what!r}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except (Refused, B22B.Refused) as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
