#!/usr/bin/env python3
"""Paper execution -- hypothetical sizing, defined-risk stop/target, and lookahead-proof freezing.

NO real order, NO wallet, NO SOL, NO on-chain write. `build_entry` produces a frozen paper-entry
record (sha256 + UTC committed BEFORE any outcome); `resolve_position` marks an open position to a
strictly-later price and returns a realised R-multiple net of the venue toll.

Sizing is a FIXED fraction of a paper bankroll -- never a martingale, never a double-down. Risk is
defined: the stop is a fixed fraction below entry, the target a larger fixed fraction above (asymmetric
by construction). The ~3% round-trip venue toll the research measured as the irreducible house edge is
charged on every paper trade, so the expectancy this bot reports is NET, not a gross fantasy.
"""

from __future__ import annotations

import datetime as dt

from . import Refused
from .frozen import canonical_sha256


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def build_entry(coin: dict, screen_result: dict, spec: dict, *, control: bool = False) -> dict:
    """Freeze one paper entry BEFORE its outcome. `control=True` marks a null (screen-REJECT) position.

    The null is the honest benchmark the task asks for: the SAME sizing/stop/target applied to coins the
    screen REJECTED. Comparing PASS expectancy to control expectancy is the forward test of whether the
    screen adds value -- the B20B 'passed rate vs base rate' comparison, run live on paper.
    """
    entry_price = coin.get("price_usd")
    if entry_price is None or entry_price <= 0:
        raise Refused(f"{coin.get('pool_address')} has no positive price; cannot freeze a paper entry")

    size_sol = round(spec["bankroll_sol"] * spec["position_fraction"], 6)
    stop_frac = spec["stop_frac"]
    target_frac = spec["target_frac"]

    setup = {
        "instrument_id": spec["instrument_id"],
        "kind": "entry",
        "control": bool(control),                       # True = null benchmark (screen said REJECT)
        "pool_address": coin["pool_address"],
        "base_token": coin.get("base_token"),
        "name": coin.get("name"),
        "dex": coin.get("dex"),
        "direction": "long",                            # bonding-curve venue is long-only
        "entry_price_usd": entry_price,
        "stop_price_usd": entry_price * (1.0 - stop_frac),
        "target_price_usd": entry_price * (1.0 + target_frac),
        "size_sol": size_sol,
        "stop_frac": stop_frac,
        "target_frac": target_frac,
        "toll_per_side": spec["toll_per_side"],
        "horizon_minutes": spec["horizon_minutes"],
        # Dead-coin early-exit spec (None on the 180-min base; set on MEMEBOT_FAST). Frozen INTO the
        # entry so each variant's exit rule is part of its lookahead-proof commitment.
        "dead_exit": spec.get("dead_exit"),
        "screen_verdict": screen_result["verdict"],
        "screen_reasons": screen_result["reasons"],
        "feed_snapshot": {k: coin.get(k) for k in
                          ("fdv_usd", "reserve_usd", "buyers", "buys", "sellers", "age_minutes")},
        "decided_utc": _now_iso(),
        "pool_created_at": coin.get("pool_created_at"),
    }
    # New execution assumptions are opt-in fields so older frozen instruments retain byte-identical
    # setup commitments.  An improvement is a new instrument, never a silent rewrite of old evidence.
    if "unexitable_loss_frac" in spec:
        setup["unexitable_loss_frac"] = spec["unexitable_loss_frac"]
    if "gap_fill_mode" in spec:
        setup["gap_fill_mode"] = spec["gap_fill_mode"]
    setup["setup_sha256"] = canonical_sha256(setup)
    return setup


def _is_dead(setup: dict, current: dict, price: float, entry: float, age_min: float) -> bool:
    """MEMEBOT_FAST dead-coin test: a flat price AND ~zero recent trades after a short hold.

    A frozen corpse -- no new buys/sells in the feed's recent window and a price that has barely moved
    from entry -- has no exit liquidity forming; holding it just burns the horizon. Requires ALL of:
    held >= after_minutes, recent trade count <= max_recent_trades, |price/entry - 1| <= flat_band.
    Returns False on the base variant (dead_exit is None) and whenever the feed cannot confirm activity
    (missing buys/sells) -- we never KILL on absence, only on confirmed deadness.
    """
    de = setup.get("dead_exit")
    if not de:
        return False
    if age_min < de["after_minutes"]:
        return False
    buys = current.get("buys")
    sells = current.get("sells")
    if buys is None or sells is None:
        return False
    recent_trades = int(buys) + int(sells)
    if recent_trades > de["max_recent_trades"]:
        return False
    if entry <= 0:
        return False
    if abs(price / entry - 1.0) > de["flat_band"]:
        return False
    return True


def _realized_r(entry_price: float, exit_price: float, spec_toll: float, stop_frac: float) -> float:
    """R-multiple net of the round-trip toll. Risk unit = size*stop_frac, so R = net_return/stop_frac."""
    gross_return = (exit_price / entry_price) - 1.0
    net_return = gross_return - 2.0 * spec_toll        # toll charged on entry AND exit leg
    return net_return / stop_frac


def _resolution_record(setup: dict, exit_price: float, reason: str, held_min: float,
                       source: str) -> dict:
    """Build the append-only resolution record shared by the live-mark and candle-history paths."""
    r = _realized_r(setup["entry_price_usd"], exit_price, setup["toll_per_side"], setup["stop_frac"])
    return {
        "kind": "resolution",
        "status": "RESOLVED",
        "control": setup.get("control", False),
        "setup_sha256": setup["setup_sha256"],
        "pool_address": setup["pool_address"],
        "name": setup.get("name"),
        "screen_verdict": setup.get("screen_verdict"),
        "entry_price_usd": setup["entry_price_usd"],
        "exit_price_usd": exit_price,
        "resolution_reason": reason,
        "realized_r": round(r, 4),
        "held_minutes": round(held_min, 1),
        "resolved_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "price_source": source,   # "live_mark" (GT refresh) | "local_candles" (memestream/Bitquery)
    }


def resolve_position(setup: dict, current: dict, spec: dict) -> dict | None:
    """Mark an open paper position to a refreshed snapshot. Returns a resolution or None if still open.

    Discrete polling: we only see the prices we poll, so we resolve at the stop/target level when a poll
    shows the price has crossed it, and at the live mark when the horizon elapses. This is conservative
    and matches what a real reactive poller could actually act on (documented in the PREREGISTRATION).
    """
    price = current.get("price_usd")
    entry = setup["entry_price_usd"]
    now = dt.datetime.now(dt.timezone.utc)
    decided = dt.datetime.fromisoformat(setup["decided_utc"])
    age_min = (now - decided).total_seconds() / 60.0

    if price is None or price <= 0:
        # Feed shows no live price -- on a bonding curve that is the 'never traded again' = unexitable
        # case. Once past horizon, resolve it as a near-total loss (exit at the stop floor, net toll).
        if age_min >= setup["horizon_minutes"]:
            loss_frac = float(setup.get("unexitable_loss_frac", setup["stop_frac"]))
            exit_price = max(0.0, entry * (1.0 - loss_frac))
            reason = "UNEXITABLE_TIMEOUT"
        else:
            return None
    elif price <= setup["stop_price_usd"]:
        exit_price = (min(setup["stop_price_usd"], price)
                      if setup.get("gap_fill_mode") == "worse_observed" else setup["stop_price_usd"])
        reason = "STOP"
    elif price >= setup["target_price_usd"]:
        exit_price, reason = setup["target_price_usd"], "TARGET"
    elif _is_dead(setup, current, price, entry, age_min):
        # MEMEBOT_FAST only: a flat corpse with ~zero recent trades. Don't hold a frozen bag for the
        # rest of the horizon -- exit NOW at the live mark (net toll), memecoin timescale.
        exit_price, reason = price, "DEAD_EXIT"
    elif age_min >= setup["horizon_minutes"]:
        exit_price, reason = price, "HORIZON_MARK"
    else:
        return None

    return _resolution_record(setup, exit_price, reason, age_min, "live_mark")


def _recent_trades(window: list, t: int, lookback_secs: int = 300) -> tuple[int, int]:
    """Buys/sells over the ~5-min window ending at candle second ``t`` (the FAST dead-exit's activity
    proxy, reconstructed from the local candle series to mirror the GT feed's recent-window count)."""
    lo = t - lookback_secs
    buys = sum(int(b.get("buys") or 0) for b in window if lo < b["t"] <= t)
    sells = sum(int(b.get("sells") or 0) for b in window if lo < b["t"] <= t)
    return buys, sells


def resolve_position_from_candles(setup: dict, bars: list, spec: dict) -> dict | None:
    """Reconstruct the frozen exit from a local candle HISTORY -- no network, no fantasy mark.

    Walk 1s/1m candles (memestream or the Bitquery cache; {t,o,h,l,c,...}, oldest-first) from the entry
    second forward and resolve at the FIRST bar that crosses the frozen level: low <= stop -> STOP, high
    >= target -> TARGET, each at the FROZEN stop/target PRICE (exactly what the discrete poller of the
    frozen rule would have sold at -- NOT the +6000% tick the price ran to afterwards). The FAST dead-exit
    is re-evaluated with the EXACT frozen ``_is_dead`` test on candle-derived recent activity. If no level
    is crossed within the horizon, mark to the last-known candle close once the horizon has elapsed; while
    still inside the horizon with no crossing, the position stays OPEN (returns None).

    This is faithful plumbing: it reconstructs the outcome the frozen rule would have produced had every
    second been polled, using the free local price series instead of a per-position GeckoTerminal call.
    Returns a resolution record, or None if the position is still open / the candles carry no usable price.
    """
    if not bars:
        return None
    entry = setup["entry_price_usd"]
    stop = setup["stop_price_usd"]
    target = setup["target_price_usd"]
    entry_epoch = dt.datetime.fromisoformat(setup["decided_utc"]).timestamp()
    horizon_epoch = entry_epoch + setup["horizon_minutes"] * 60.0
    now_epoch = dt.datetime.now(dt.timezone.utc).timestamp()

    window = [b for b in bars
              if b.get("t") is not None and entry_epoch <= b["t"] <= horizon_epoch]
    last_mark = None
    for b in window:
        held = (b["t"] - entry_epoch) / 60.0
        lo, hi, close = b.get("l"), b.get("h"), b.get("c")
        # Priority mirrors resolve_position: stop before target within a bar (conservative for a long).
        if lo is not None and lo <= stop:
            exit_price = stop
            if setup.get("gap_fill_mode") == "worse_observed":
                observed = close if close is not None and close > 0 else lo
                if observed is not None:
                    exit_price = min(stop, observed)
            return _resolution_record(setup, exit_price, "STOP", held, "local_candles")
        if hi is not None and hi >= target:
            return _resolution_record(setup, target, "TARGET", held, "local_candles")
        if close is not None and close > 0:
            buys, sells = _recent_trades(window, b["t"])
            if _is_dead(setup, {"buys": buys, "sells": sells}, close, entry, held):
                return _resolution_record(setup, close, "DEAD_EXIT", held, "local_candles")
            last_mark = close
    if now_epoch >= horizon_epoch and last_mark is not None:
        held = (min(now_epoch, horizon_epoch) - entry_epoch) / 60.0
        return _resolution_record(setup, last_mark, "HORIZON_MARK", held, "local_candles")
    return None
