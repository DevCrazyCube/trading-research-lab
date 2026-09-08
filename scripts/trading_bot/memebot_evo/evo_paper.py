#!/usr/bin/env python3
"""Paper execution for one genome -- entry freeze + mark-to-market resolve, with the flow-following
exit the base memebot cannot supply.

This is a minimal COPY-AND-EXTEND of `..memebot.paper` (the memebot's resolve_position has no
flow-reversal exit to import, so per the build constraint we wrap the logic here rather than edit it).
The stop/target/dead-exit/horizon behaviour is byte-for-byte the same idea; the ONE addition is
FLOW_EXIT: after a minimum hold, if selling pressure has overtaken buying by the genome's ratio, exit
at the live mark. The freeze fingerprint (sha256 + UTC) is reused from memebot.frozen so every genome
entry is lookahead-proof exactly like the base bot.

NO real order, NO wallet, NO SOL, NO on-chain write. The ~3% round-trip toll is charged on every
paper trade so reported expectancy is NET.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import pathlib

from . import Refused
from ..memebot.frozen import canonical_sha256   # READ-ONLY reuse of the base freeze hash
from ..memestream.candles import get_candles    # READ-ONLY local candle cache (free data)

# ---- SUB-MINUTE tick resolution (Bitquery 1s OHLCV+flow candles) ---------------------------------
# A sub-minute genome resolves on the per-MINT 1-second candle file written by the live Bitquery
# ingester, joined on the entry's `base_token` (the Solana Currency.MintAddress). Each bar is
# {t (epoch sec), o,h,l,c, v (usd), buys, sells, buy_vol (usd), sell_vol (usd)}.
BITQUERY_CANDLE_DIR = pathlib.Path(__file__).resolve().parents[3] / \
    "research" / "data" / "memebot_cache" / "bitquery_candles"
# Grace window past the horizon before we DECLARE a position unpriced: give the async ingester a
# little slack to write the bars that cover the hold before calling the mint absent from the feed.
SUBMIN_UNPRICED_GRACE_S = 120
# Entry-data validity, not a trading knob.  Both live writers flush every 4--8 seconds, so a last
# observed trade older than 10 seconds cannot support a seconds-scale entry.  Fail closed instead of
# opening a paper position that is already known to have no executable tick oracle.
SUBMIN_ENTRY_MAX_TICK_AGE_S = 10.0


def _load_tick_bars(mint: str | None) -> list | None:
    """Return this mint's 1s bars sorted by time, or None if the coin is not in the tick feed at all
    (no candle file). An existing-but-empty file returns []."""
    if not mint:
        return None
    p = BITQUERY_CANDLE_DIR / f"{mint}.jsonl"
    if not p.exists():
        return None
    bars = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            b = json.loads(line)
        except Exception:
            continue
        # Require a fully positive OHLC bar. A zero/negative high/low/close is a data glitch (a missing
        # print), not a real trade price; letting it through would fabricate a fake gap-through dump and
        # bias the loss-tail pessimistically for the WRONG reason. Honest in both directions.
        if ("t" in b and b.get("c", 0) > 0 and b.get("o", 0) > 0
                and b.get("h", 0) > 0 and b.get("l", 0) > 0 and b["h"] >= b["l"]):
            bars.append(b)
    bars.sort(key=lambda b: b["t"])
    return bars


def tick_entry_data_ready(bars: list | None, decision_epoch: float, *,
                          max_age_s: float = SUBMIN_ENTRY_MAX_TICK_AGE_S) -> tuple[bool, dict]:
    """Whether a seconds-scale entry has a causal, fresh tick at decision time.

    Future bars never qualify.  A missing, non-numeric, future-only, or stale stream refuses before an
    entry is written; this is deliberately stricter than resolving it as ``UNPRICED`` minutes later.
    """
    diag = {"reason": None, "last_tick_t": None, "tick_age_s": None,
            "max_tick_age_s": max_age_s}
    if not isinstance(decision_epoch, (int, float)) or isinstance(decision_epoch, bool) \
            or not math.isfinite(float(decision_epoch)):
        diag["reason"] = "invalid_decision_time"
        return False, diag
    if not isinstance(max_age_s, (int, float)) or isinstance(max_age_s, bool) \
            or not math.isfinite(float(max_age_s)) or max_age_s < 0:
        diag["reason"] = "invalid_max_age"
        return False, diag
    diag["max_tick_age_s"] = float(max_age_s)
    causal = [b for b in (bars or [])
              if isinstance(b, dict) and isinstance(b.get("t"), (int, float))
              and not isinstance(b.get("t"), bool) and math.isfinite(float(b["t"]))
              and float(b["t"]) <= float(decision_epoch)]
    if not causal:
        diag["reason"] = "missing_or_future_only"
        return False, diag
    last_t = max(float(b["t"]) for b in causal)
    age = float(decision_epoch) - last_t
    diag.update(last_tick_t=last_t, tick_age_s=age)
    if age > float(max_age_s):
        diag["reason"] = "stale"
        return False, diag
    diag["reason"] = "ready"
    return True, diag

# ---- MOMENTUM-ENTRY qualification (owner's thesis: only buy what is ALREADY moving) --------------
def momentum_entry_qualifies(bars: list | None, entry_epoch: float, spec: dict) -> tuple[bool, dict]:
    """True iff, using ONLY tick bars at/before entry_epoch (no lookahead), the coin shows a genuine
    surge: price up >= entry_surge_bps over the last entry_window_s, buy-vol fraction >=
    entry_min_buyfrac, and >= entry_min_trades trades in the window. Returns (ok, diagnostics).
    No tick data (or empty window) -> NOT qualified: we never buy a surge we cannot confirm."""
    surge_bps = float(spec.get("entry_surge_bps", 300.0))
    window_s = int(spec.get("entry_window_s", 20))
    min_buyfrac = float(spec.get("entry_min_buyfrac", 0.60))
    min_trades = int(spec.get("entry_min_trades", 5))
    diag = {"surge_bps": None, "buyfrac": None, "trades": None, "bars_in_window": 0,
            "req_surge_bps": surge_bps, "req_buyfrac": min_buyfrac, "req_trades": min_trades,
            "req_window_s": window_s}
    if not bars:
        return False, diag
    past = [b for b in bars if b["t"] <= entry_epoch]
    if not past:
        return False, diag
    last_t = past[-1]["t"]
    window = [b for b in past if b["t"] >= last_t - window_s]
    diag["bars_in_window"] = len(window)
    if len(window) < 2:
        return False, diag
    start_c = window[0]["c"]
    end_c = window[-1]["c"]
    surge = (end_c / start_c - 1.0) * 1e4 if start_c > 0 else 0.0
    bv = sum((b.get("buy_vol", 0.0) or 0.0) for b in window)
    sv = sum((b.get("sell_vol", 0.0) or 0.0) for b in window)
    buyfrac = (bv / (bv + sv)) if (bv + sv) > 0 else 0.0
    trades = sum(int(b.get("buys", 0) or 0) + int(b.get("sells", 0) or 0) for b in window)
    diag.update(surge_bps=round(surge, 1), buyfrac=round(buyfrac, 4), trades=trades)
    ok = (surge >= surge_bps) and (buyfrac >= min_buyfrac) and (trades >= min_trades)
    return ok, diag


# ---- Adaptive-exit volatility unit (honest, free-data-only) --------------------------------------
# When a genome sets use_vol_exits=1 we size the stop/target off the COIN'S OWN recent volatility
# instead of a fixed %. The volatility unit is an ATR-like fraction of price:
#
#     vol = mean over recent 1m candles of (high - low) / close
#
# measured from the LOCAL memestream candle cache over the last VOL_LOOKBACK_SECS. It is a pure
# fraction of price (dimensionless), so stop_vol_mult/target_vol_mult are unitless multipliers.
# A calm coin (small mean range) yields a small vol -> a tight stop; a wild coin a large vol -> a
# wide stop. If there are fewer than VOL_MIN_CANDLES usable candles (a brand-new / illiquid coin) or
# the result is degenerate (<=0), measure_vol returns None and the caller FALLS BACK to the genome's
# fixed stop_frac/target_frac -- never a crash, never a degenerate 0-width stop.
VOL_TIMEFRAME = "1m"
VOL_LOOKBACK_SECS = 1800     # 30 minutes of recent candles
VOL_MIN_CANDLES = 5          # need at least this many usable candles, else fall back to fixed
# Structural floor: a stop can never sit INSIDE the pinned round-trip toll (2 x TOLL_PER_SIDE ~= 3%),
# because a stop tighter than the toll is a guaranteed loss the instant it is hit. This is an economic
# invariant (the toll is a pinned constant), NOT a fit to observed data.
VOL_STOP_FRAC_FLOOR = 0.03


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def measure_vol(pool: str | None) -> float | None:
    """Robust recent volatility for a coin as a FRACTION of price (ATR-like), or None if too little
    data. See the module comment for the exact formula. Reads only the local free candle cache."""
    if not pool:
        return None
    try:
        candles = get_candles(pool, VOL_TIMEFRAME, lookback_secs=VOL_LOOKBACK_SECS)
    except Exception:
        return None
    ranges = [(c["h"] - c["l"]) / c["c"]
              for c in candles if c.get("c", 0) > 0 and c.get("h", 0) >= c.get("l", 0)]
    if len(ranges) < VOL_MIN_CANDLES:
        return None
    vol = sum(ranges) / len(ranges)
    return vol if vol > 0 else None


def build_entry(coin: dict, screen_result: dict, spec: dict, *, control: bool = False) -> dict:
    """Freeze one paper entry BEFORE its outcome. `control=True` = null (screen-REJECT) benchmark."""
    entry_price = coin.get("price_usd")
    if entry_price is None or entry_price <= 0:
        raise Refused(f"{coin.get('pool_address')} has no positive price; cannot freeze a paper entry")

    size_sol = round(spec["bankroll_sol"] * spec["position_fraction"], 6)

    # Exit sizing, FROZEN at entry (pre-committed, never recomputed during tracking): either the fixed
    # genome percentages, or -- when use_vol_exits=1 and the coin's volatility is measurable -- a stop
    # and target scaled to THIS coin's own recent volatility unit.
    measured_vol = None
    exit_mode = "fixed"
    stop_frac = spec["stop_frac"]
    target_frac = spec["target_frac"]
    if spec.get("use_vol_exits"):
        measured_vol = measure_vol(coin.get("pool_address"))
        if measured_vol is not None:
            stop_frac = max(VOL_STOP_FRAC_FLOOR, spec["stop_vol_mult"] * measured_vol)
            target_frac = spec["target_vol_mult"] * measured_vol
            exit_mode = "vol"
        # else: too little candle data -> keep the fixed fallback above.

    setup = {
        "instrument_id": spec["instrument_id"],
        "genome_id": spec["genome_id"],
        "kind": "entry",
        "control": bool(control),
        "pool_address": coin["pool_address"],
        "base_token": coin.get("base_token"),
        "name": coin.get("name"),
        "dex": coin.get("dex"),
        "direction": "long",
        "entry_price_usd": entry_price,
        "stop_price_usd": entry_price * (1.0 - stop_frac),
        "target_price_usd": entry_price * (1.0 + target_frac),
        "size_sol": size_sol,
        "stop_frac": stop_frac,          # EFFECTIVE stop distance actually used (fixed or vol-scaled)
        "target_frac": target_frac,      # EFFECTIVE target distance actually used
        "exit_mode": exit_mode,          # "vol" if adaptive fired, else "fixed" (fallback)
        "measured_vol": measured_vol,    # the coin's ATR-like vol fraction at entry (None if unmeasured)
        "use_vol_exits": int(spec.get("use_vol_exits", 0)),
        "stop_vol_mult": spec.get("stop_vol_mult"),
        "target_vol_mult": spec.get("target_vol_mult"),
        "toll_per_side": spec["toll_per_side"],
        "horizon_minutes": spec["horizon_minutes"],
        # ---- SUB-MINUTE genes, FROZEN into the entry (resolved on the Bitquery 1s tick feed) --------
        "use_subminute": int(spec.get("use_subminute", 0)),
        "horizon_seconds": spec.get("horizon_seconds"),
        "momentum_window_s": spec.get("momentum_window_s"),
        "momentum_exit_bps": spec.get("momentum_exit_bps"),
        "flowflip_min_seconds": spec.get("flowflip_min_seconds"),
        "flowflip_buy_frac": spec.get("flowflip_buy_frac"),
        "use_tick_momentum": int(spec.get("use_tick_momentum", 0)),
        "use_tick_flowflip": int(spec.get("use_tick_flowflip", 0)),
        "dead_exit": spec.get("dead_exit"),
        "flow_exit": spec.get("flow_exit"),          # <-- the evo-only exit gene, frozen into the entry
        "screen_verdict": screen_result["verdict"],
        "screen_reasons": screen_result["reasons"],
        "feed_snapshot": {k: coin.get(k) for k in
                          ("fdv_usd", "reserve_usd", "buyers", "buys", "sellers", "age_minutes")},
        "decided_utc": _now_iso(),
        "pool_created_at": coin.get("pool_created_at"),
    }
    setup["setup_sha256"] = canonical_sha256(setup)
    return setup


def _is_dead(setup: dict, current: dict, price: float, entry: float, age_min: float) -> bool:
    de = setup.get("dead_exit")
    if not de or age_min < de["after_minutes"]:
        return False
    buys, sells = current.get("buys"), current.get("sells")
    if buys is None or sells is None:
        return False
    if int(buys) + int(sells) > de["max_recent_trades"]:
        return False
    if entry <= 0 or abs(price / entry - 1.0) > de["flat_band"]:
        return False
    return True


def _flow_reversed(setup: dict, current: dict, age_min: float) -> bool:
    """FLOW_EXIT: after the minimum hold, has selling pressure overtaken buying by the genome ratio?

    Requires confirmed activity in the feed window (buys/sells present) and at least one sell -- we
    never exit on ABSENCE of data, only on confirmed reversal. sells/max(buys,1) >= ratio."""
    fe = setup.get("flow_exit")
    if not fe or age_min < fe["after_minutes"]:
        return False
    buys, sells = current.get("buys"), current.get("sells")
    if buys is None or sells is None or int(sells) <= 0:
        return False
    return (int(sells) / max(int(buys), 1)) >= fe["sell_buy_ratio"]


def _realized_r(entry_price: float, exit_price: float, toll: float, stop_frac: float) -> float:
    net_return = (exit_price / entry_price - 1.0) - 2.0 * toll   # toll on entry AND exit leg
    return net_return / stop_frac


def resolve_position(setup: dict, current: dict, spec: dict) -> dict | None:
    """Mark an open paper position to a refreshed snapshot. Returns a resolution or None if still open.

    Priority: no-price timeout -> STOP -> TARGET -> FLOW_EXIT -> DEAD_EXIT -> HORIZON_MARK. Stop/target
    take precedence (defined risk); the flow reversal and dead-coin rules are early exits before the
    horizon elapses."""
    price = current.get("price_usd")
    entry = setup["entry_price_usd"]
    now = dt.datetime.now(dt.timezone.utc)
    decided = dt.datetime.fromisoformat(setup["decided_utc"])
    age_min = (now - decided).total_seconds() / 60.0

    if price is None or price <= 0:
        if age_min >= setup["horizon_minutes"]:
            if current.get("_data_unavailable"):
                # Provider refusal/budget exhaustion is not evidence that the market itself was
                # unexitable. Close terminally so the book drains, label the distinction, and let the
                # V2 stress fitness charge the full-loss bound rather than silently exclude it.
                return {
                    "kind": "resolution", "status": "RESOLVED",
                    "genome_id": setup.get("genome_id"), "control": setup.get("control", False),
                    "setup_sha256": setup["setup_sha256"], "pool_address": setup["pool_address"],
                    "name": setup.get("name"), "screen_verdict": setup.get("screen_verdict"),
                    "entry_price_usd": entry, "exit_price_usd": None,
                    "resolution_reason": "UNPRICED_PROVIDER_UNAVAILABLE", "realized_r": None,
                    "data_reason": current.get("_data_reason"), "held_minutes": round(age_min, 1),
                    "resolved_utc": now.isoformat(),
                }
            exit_price, reason = setup["stop_price_usd"], "UNEXITABLE_TIMEOUT"
        else:
            return None
    elif price <= setup["stop_price_usd"]:
        exit_price, reason = setup["stop_price_usd"], "STOP"
    elif price >= setup["target_price_usd"]:
        exit_price, reason = setup["target_price_usd"], "TARGET"
    elif _flow_reversed(setup, current, age_min):
        exit_price, reason = price, "FLOW_EXIT"
    elif _is_dead(setup, current, price, entry, age_min):
        exit_price, reason = price, "DEAD_EXIT"
    elif age_min >= setup["horizon_minutes"]:
        exit_price, reason = price, "HORIZON_MARK"
    else:
        return None

    r = _realized_r(entry, exit_price, setup["toll_per_side"], setup["stop_frac"])
    return {
        "kind": "resolution",
        "status": "RESOLVED",
        "genome_id": setup.get("genome_id"),
        "control": setup.get("control", False),
        "setup_sha256": setup["setup_sha256"],
        "pool_address": setup["pool_address"],
        "name": setup.get("name"),
        "screen_verdict": setup.get("screen_verdict"),
        "entry_price_usd": entry,
        "exit_price_usd": exit_price,
        "resolution_reason": reason,
        "realized_r": round(r, 4),
        "held_minutes": round(age_min, 1),
        "resolved_utc": now.isoformat(),
    }


# ---- Sub-minute (tick) resolution ----------------------------------------------------------------
def _unpriced_record(setup: dict, now: dt.datetime, reason: str, *, had_file: bool,
                     age_s: float) -> dict:
    """A TERMINAL record for a sub-minute entry that could not be priced on the tick feed. status is
    RESOLVED (so the position closes and is not retried forever) but realized_r is None (so it is
    EXCLUDED from every R statistic). These are counted separately as the tick-availability honesty
    metric -- if most sub-minute entries land here, the family is underpowered and we SAY so."""
    return {
        "kind": "resolution", "status": "RESOLVED", "genome_id": setup.get("genome_id"),
        "control": setup.get("control", False), "setup_sha256": setup["setup_sha256"],
        "pool_address": setup.get("pool_address"), "base_token": setup.get("base_token"),
        "name": setup.get("name"), "screen_verdict": setup.get("screen_verdict"),
        "subminute": True, "tick_data_available": False,
        "entry_price_usd": setup["entry_price_usd"], "exit_price_usd": None,
        "resolution_reason": reason, "realized_r": None,
        "had_candle_file": bool(had_file), "held_seconds": round(age_s, 1),
        "resolved_utc": now.isoformat(),
    }


def resolve_subminute(setup: dict, spec: dict, *, now: dt.datetime | None = None) -> dict | None:
    """Resolve a SUB-MINUTE paper position on the coin's Bitquery 1s tick candles. Returns a resolution,
    an UNPRICED terminal record, or None (still open -- wait for more bars).

    The position is re-anchored to the tick oracle: the effective entry is the close of the FIRST 1s bar
    at/after the entry time (chosen without hindsight -- the earliest available bar), and the FROZEN
    stop_frac/target_frac are applied to it. This keeps the whole price path on ONE oracle instead of
    mixing the ~40s GeckoTerminal entry mark with per-second Bitquery prices. Walk order per bar
    (conservative): TICK_STOP (low<=stop) -> TICK_TARGET (high>=target) -> TICK_MOMENTUM (window gain
    >= momentum_exit_bps) -> TICK_FLOWFLIP (rolling buy-vol fraction < flowflip_buy_frac after min hold)
    -> TICK_HORIZON (elapsed >= horizon_seconds). The pinned ~3% round-trip toll is charged on the R."""
    now = now or dt.datetime.now(dt.timezone.utc)
    mint = setup.get("base_token")
    decided = dt.datetime.fromisoformat(setup["decided_utc"])
    entry_epoch = decided.timestamp()
    horizon_s = int(setup.get("horizon_seconds") or spec.get("horizon_seconds") or 60)
    age_s = (now - decided).total_seconds()

    bars = _load_tick_bars(mint)
    fwd = [b for b in bars if b["t"] >= entry_epoch] if bars else []
    if not fwd:
        # No usable tick bars covering the hold. Give the async ingester a grace window; only past
        # horizon+grace do we DECLARE the coin absent from the tick feed (honest UNPRICED).
        if age_s >= horizon_s + SUBMIN_UNPRICED_GRACE_S:
            return _unpriced_record(setup, now, "UNPRICED_NO_TICKDATA",
                                    had_file=bars is not None, age_s=age_s)
        return None

    anchor = fwd[0]
    tick_entry = anchor["c"]
    stop_frac = setup["stop_frac"]
    target_frac = setup["target_frac"]
    stop_px = tick_entry * (1.0 - stop_frac)
    target_px = tick_entry * (1.0 + target_frac)
    window_s = int(setup.get("momentum_window_s") or 10)
    mom_bps = float(setup.get("momentum_exit_bps") or 150.0)
    use_mom = int(setup.get("use_tick_momentum", 0))
    use_flip = int(setup.get("use_tick_flowflip", 0))
    flip_min_s = float(setup.get("flowflip_min_seconds") or 20.0)
    flip_buy_frac = float(setup.get("flowflip_buy_frac") or 0.35)

    recent: list = [anchor]          # rolling window of bars within the last window_s seconds
    exit_px = reason = None
    bars_walked = 0
    for b in fwd[1:]:
        bars_walked += 1
        t = b["t"]
        elapsed = t - entry_epoch
        # prune the rolling window, then append current bar
        recent = [x for x in recent if x["t"] >= t - window_s]
        recent.append(b)
        if b["l"] <= stop_px:
            # PESSIMISTIC stop fill: if the breaching bar CLOSED below the stop, the price gapped
            # THROUGH the stop and you realistically fill at that worse close, not the intended stop
            # (an "unexitable" dump). Only when the bar merely wicked below but closed at/above the
            # stop do you get the stop price. Never optimistic. This is the honest loss-tail model.
            exit_px, reason = min(stop_px, b["c"]), "TICK_STOP"; break
        if b["h"] >= target_px:
            exit_px, reason = target_px, "TICK_TARGET"; break
        if use_mom:
            wstart_c = recent[0]["c"]
            if wstart_c > 0 and (b["c"] / wstart_c - 1.0) * 1e4 >= mom_bps:
                exit_px, reason = b["c"], "TICK_MOMENTUM"; break
        if use_flip and elapsed >= flip_min_s:
            bv = sum(x.get("buy_vol", 0.0) or 0.0 for x in recent)
            sv = sum(x.get("sell_vol", 0.0) or 0.0 for x in recent)
            if bv + sv > 0 and (bv / (bv + sv)) < flip_buy_frac:
                exit_px, reason = b["c"], "TICK_FLOWFLIP"; break
        if elapsed >= horizon_s:
            exit_px, reason = b["c"], "TICK_HORIZON"; break
    else:
        # ran out of bars without a trigger
        if age_s >= horizon_s:
            # wall-clock is past the horizon but the tick stream ended early -> mark at last known bar
            exit_px, reason = fwd[-1]["c"], "TICK_HORIZON_DATAEND"
        else:
            return None   # still inside the horizon; more 1s bars may still arrive

    r = _realized_r(tick_entry, exit_px, setup["toll_per_side"], stop_frac)
    held_s = min(age_s, float(horizon_s)) if reason.startswith("TICK_HORIZON") else \
        (fwd[bars_walked]["t"] - entry_epoch if bars_walked < len(fwd) else age_s)
    return {
        "kind": "resolution", "status": "RESOLVED", "genome_id": setup.get("genome_id"),
        "control": setup.get("control", False), "setup_sha256": setup["setup_sha256"],
        "pool_address": setup.get("pool_address"), "base_token": mint,
        "name": setup.get("name"), "screen_verdict": setup.get("screen_verdict"),
        "subminute": True, "tick_data_available": True,
        "entry_price_usd": setup["entry_price_usd"],       # the GeckoTerminal mark frozen at entry
        "tick_entry_price_usd": tick_entry,                # the tick-oracle anchor R is computed on
        "exit_price_usd": exit_px,
        "resolution_reason": reason,
        "realized_r": round(r, 4),
        "held_seconds": round(max(0.0, held_s), 1),
        "bars_used": bars_walked,
        "first_bar_t": anchor["t"], "last_bar_t": fwd[-1]["t"],
        "resolved_utc": now.isoformat(),
    }
