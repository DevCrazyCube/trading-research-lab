#!/usr/bin/env python3
"""CONVEXITY PROBE -- in-sample mechanism check on the real Bitquery 1s tick candles.

PAPER ONLY. No orders, no wallet, no money, no git-commit. Frozen memebot + dashboard untouched.
This script does NOT import or mutate engine.py / evo_paper.py / genome.py; it REPLICATES the two
pure primitives it needs (_load_tick_bars, momentum_entry_qualifies) byte-faithfully and PINS the
toll to the genome's constant (TOLL_PER_SIDE = 0.015) so the honesty economics are identical.

The question (owner): the earlier momentum-scalp tests were ALL net-negative for TWO measured reasons
    (1) CAPPED take-profits barely above the ~3% round-trip toll (toll dominated the winners), and
    (2) PRICE-STOP exits that gapped THROUGH 100% of the time (losers unbounded).
This probe tests the UNTESTED convexity config that attacks both:
    - LET WINNERS RUN (no tp cap; ride the occasional multi-x)
    - exit on FLOW REVERSAL from tick flow (sell when buy-pressure flips) instead of a price stop
    - a LIQUIDITY GATE so we only enter coins with enough throughput that an exit can fill
Three exit policies are compared head-to-head on the SAME entries:
    (A) capped tp/sl                      -- the old baseline
    (B) flow-reversal only, UNCAPPED winner
    (C) flow-reversal + wide catastrophe backstop (-60%), UNCAPPED winner

Metrics are reported convention-free (NET RETURN PER TRADE = exit/entry - 1 - 2*toll, the real money
quantity) and additionally as R against a SINGLE fixed risk unit U (R_UNIT) held constant across all
three policies so the R distributions and the right tail are directly comparable.
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics
from dataclasses import dataclass, field

# ---- Pinned economics (identical to genome.py; NEVER weakened) -----------------------------------
TOLL_PER_SIDE = 0.015            # ~3% round trip -- the irreducible house edge, pinned
R_UNIT = 0.10                    # fixed nominal risk unit for the comparable R metric (10%)

BITQUERY_CANDLE_DIR = pathlib.Path(__file__).resolve().parents[3] / \
    "research" / "data" / "memebot_cache" / "bitquery_candles"


# ---- Replicated pure primitives (byte-faithful to evo_paper.py) ----------------------------------
_BAR_CACHE: dict[str, list] = {}


def load_tick_bars(mint: str) -> list:
    """This mint's tick bars sorted by time; drops glitch bars (non-positive OHLC / h<l). [] if none.
    Faithful copy of evo_paper._load_tick_bars, with an in-process cache (read-only data)."""
    cached = _BAR_CACHE.get(mint)
    if cached is not None:
        return cached
    p = BITQUERY_CANDLE_DIR / f"{mint}.jsonl"
    if not p.exists():
        _BAR_CACHE[mint] = []
        return []
    bars = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            b = json.loads(line)
        except Exception:
            continue
        if ("t" in b and b.get("c", 0) > 0 and b.get("o", 0) > 0
                and b.get("h", 0) > 0 and b.get("l", 0) > 0 and b["h"] >= b["l"]):
            bars.append(b)
    bars.sort(key=lambda b: b["t"])
    _BAR_CACHE[mint] = bars
    return bars


def momentum_entry_qualifies(bars: list, entry_epoch: float, cfg: "Config") -> tuple[bool, dict]:
    """True iff, using ONLY bars at/before entry_epoch (no lookahead), the coin shows a genuine surge.
    Faithful copy of evo_paper.momentum_entry_qualifies, plus a LIQUIDITY GATE on window throughput.

    Liquidity proxy (documented honestly): the candle carries NO reserve/pool depth, so we proxy
    'exitable liquidity' by USD THROUGHPUT over the entry window = total window USD volume / window
    seconds. A coin trading $X/second can absorb a market exit better than one trading $0.10/second.
    This is a FLOW proxy, not a depth measurement: it can be fooled by a burst of wash prints, and it
    says nothing about the bid stack. It is the best free-data proxy available on this feed."""
    surge_bps = cfg.entry_surge_bps
    window_s = cfg.entry_window_s
    min_buyfrac = cfg.entry_min_buyfrac
    min_trades = cfg.entry_min_trades
    diag = {"surge_bps": None, "buyfrac": None, "trades": None, "bars_in_window": 0, "liq_usd_per_s": None}
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
    # Liquidity throughput proxy over the actual span the window covers (>=1s to avoid /0).
    span_s = max(1.0, float(window[-1]["t"] - window[0]["t"]))
    usdvol = sum((b.get("v", 0.0) or 0.0) for b in window)
    liq_usd_per_s = usdvol / span_s
    diag.update(surge_bps=round(surge, 1), buyfrac=round(buyfrac, 4), trades=trades,
                liq_usd_per_s=round(liq_usd_per_s, 3))
    ok = ((surge >= surge_bps) and (buyfrac >= min_buyfrac) and (trades >= min_trades)
          and (liq_usd_per_s >= cfg.min_liq_usd_per_s))
    return ok, diag


# ---- Config --------------------------------------------------------------------------------------
@dataclass
class Config:
    # Entry (momentum surge) gate
    entry_surge_bps: float = 300.0
    entry_window_s: int = 20
    entry_min_buyfrac: float = 0.60
    entry_min_trades: int = 5
    # Liquidity gate (USD throughput per second over the entry window)
    min_liq_usd_per_s: float = 0.0
    # Exit policy: 'A' capped tp/sl | 'B' flow-only uncapped | 'C' flow + catastrophe backstop
    policy: str = "A"
    # Policy A params
    tp_bps: float = 300.0
    sl_bps: float = 200.0
    # Flow-reversal params (B/C)
    flip_window_s: int = 20
    flip_buy_frac: float = 0.45
    flip_K: int = 2                 # consecutive qualifying bars below the buy-frac threshold
    backstop_frac: float = 0.60     # C only: hard catastrophe floor
    # Shared time cap (B/C let winners run within this; A cuts fast). Big for B/C.
    max_hold_s: int = 300
    # Pessimistic EXTRA exit slippage (bps) on any MARKET-style exit (stop/flip/backstop/horizon/dataend).
    # NOT applied to a limit TARGET fill. Charged ON TOP of the pinned round-trip toll.
    exit_slip_bps: float = 150.0
    toll_per_side: float = TOLL_PER_SIDE


def _net_return(entry_px: float, exit_px: float, toll: float) -> float:
    return (exit_px / entry_px - 1.0) - 2.0 * toll


def _slip(px: float, cfg: Config) -> float:
    return px * (1.0 - cfg.exit_slip_bps / 1e4)


# ---- Exit walkers (all pessimistic; no lookahead beyond the entry anchor) -------------------------
def walk_exit(fwd: list, entry_epoch: float, cfg: Config) -> dict | None:
    """Walk forward bars (t > entry_epoch is NOT required; fwd[0] is the entry anchor bar). Returns a
    resolution dict or None if no forward bars. fwd must start at the anchor bar (entry price = its c)."""
    if not fwd:
        return None
    anchor = fwd[0]
    entry_px = anchor["c"]
    toll = cfg.toll_per_side
    max_hold = cfg.max_hold_s

    if cfg.policy == "A":
        stop_px = entry_px * (1.0 - cfg.sl_bps / 1e4)
        target_px = entry_px * (1.0 + cfg.tp_bps / 1e4)
        exit_px = reason = None
        walked = 0
        for b in fwd[1:]:
            walked += 1
            elapsed = b["t"] - entry_epoch
            if b["l"] <= stop_px:
                # pessimistic: gap-through fills at the worse close
                exit_px, reason = _slip(min(stop_px, b["c"]), cfg), "STOP"; break
            if b["h"] >= target_px:
                exit_px, reason = target_px, "TARGET"; break   # limit fill, no extra slip
            if elapsed >= max_hold:
                exit_px, reason = _slip(b["c"], cfg), "HORIZON"; break
        else:
            exit_px, reason = _slip(fwd[-1]["c"], cfg), "DATAEND"
            walked = len(fwd) - 1
        held_s = (fwd[min(walked, len(fwd)-1)]["t"] - entry_epoch)
        return _resolution(entry_px, exit_px, reason, walked, held_s, toll)

    # Policies B and C: flow-reversal, UNCAPPED winner, optional catastrophe backstop (C).
    use_backstop = (cfg.policy == "C")
    backstop_px = entry_px * (1.0 - cfg.backstop_frac) if use_backstop else None
    win = cfg.flip_window_s
    thr = cfg.flip_buy_frac
    K = cfg.flip_K
    recent = [anchor]
    below_streak = 0
    exit_px = reason = None
    walked = 0
    for b in fwd[1:]:
        walked += 1
        t = b["t"]
        elapsed = t - entry_epoch
        recent = [x for x in recent if x["t"] >= t - win]
        recent.append(b)
        # C: catastrophe backstop first (defined-risk floor), pessimistic gap-through fill.
        if use_backstop and b["l"] <= backstop_px:
            exit_px, reason = _slip(min(backstop_px, b["c"]), cfg), "BACKSTOP"; break
        # Flow-reversal: rolling buy-vol fraction over the window; K consecutive bars below thr -> flip.
        bv = sum(x.get("buy_vol", 0.0) or 0.0 for x in recent)
        sv = sum(x.get("sell_vol", 0.0) or 0.0 for x in recent)
        buyfrac = (bv / (bv + sv)) if (bv + sv) > 0 else 0.0
        if buyfrac < thr:
            below_streak += 1
        else:
            below_streak = 0
        if below_streak >= K:
            exit_px, reason = _slip(b["c"], cfg), "FLOWFLIP"; break
        if elapsed >= max_hold:
            exit_px, reason = _slip(b["c"], cfg), "HORIZON"; break
    else:
        exit_px, reason = _slip(fwd[-1]["c"], cfg), "DATAEND"
        walked = len(fwd) - 1
    held_s = (fwd[min(walked, len(fwd)-1)]["t"] - entry_epoch)
    return _resolution(entry_px, exit_px, reason, walked, held_s, toll)


def _resolution(entry_px, exit_px, reason, walked, held_s, toll) -> dict:
    nr = _net_return(entry_px, exit_px, toll)
    return {
        "entry_px": entry_px, "exit_px": exit_px, "reason": reason,
        "bars_walked": walked, "held_s": round(float(held_s), 1),
        "net_return": nr, "R": nr / R_UNIT,
        "gross_mult": exit_px / entry_px,
    }


# ---- Entry generation over the whole tick cache --------------------------------------------------
def generate_entries(cfg: Config, mints: list[str], max_entries_per_coin: int = 50) -> list[dict]:
    """Non-overlapping momentum+liquidity-gated entries across all coins. After an entry opens we walk
    its exit (policy-independent entry set: entries are decided by the ENTRY gate only) and resume
    scanning from the bar AFTER the entry to avoid pyramiding the same surge. Entry anchor = the bar at
    which the gate fires (its close is the fill). No lookahead: qualification uses only bars <= t."""
    entries = []
    for mint in mints:
        bars = load_tick_bars(mint)
        if len(bars) < 3:
            continue
        i = 1
        n_coin = 0
        while i < len(bars) - 1 and n_coin < max_entries_per_coin:
            t = bars[i]["t"]
            ok, diag = momentum_entry_qualifies(bars[:i+1], t, cfg)
            if ok:
                entries.append({"mint": mint, "entry_idx": i, "entry_epoch": t, "diag": diag,
                                "fwd_from": i})
                n_coin += 1
                # skip past this surge: jump forward until the entry window no longer overlaps,
                # a light cooldown of entry_window_s seconds so we don't re-fire on the same bars.
                j = i + 1
                while j < len(bars) and bars[j]["t"] < t + cfg.entry_window_s:
                    j += 1
                i = max(j, i + 1)
            else:
                i += 1
    return entries


def resolve_all(cfg: Config, entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        bars = load_tick_bars(e["mint"])
        fwd = bars[e["fwd_from"]:]
        res = walk_exit(fwd, e["entry_epoch"], cfg)
        if res is None:
            continue
        res = dict(res)
        res["mint"] = e["mint"]
        res["entry_epoch"] = e["entry_epoch"]
        res["liq_usd_per_s"] = e["diag"]["liq_usd_per_s"]
        out.append(res)
    return out


# ---- Stats ---------------------------------------------------------------------------------------
def _pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1))))
    return sorted_vals[k]


def summarize(res: list[dict]) -> dict:
    if not res:
        return {"n": 0}
    nrs = [r["net_return"] for r in res]
    Rs = sorted(r["R"] for r in res)
    nrs_sorted = sorted(nrs)
    wins = [x for x in nrs if x > 0]
    losses = [x for x in nrs if x <= 0]
    reasons = {}
    for r in res:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    return {
        "n": len(res),
        "mean_net_return": statistics.mean(nrs),
        "median_net_return": statistics.median(nrs),
        "mean_R": statistics.mean([r["R"] for r in res]),
        "median_R": statistics.median([r["R"] for r in res]),
        "win_rate": len(wins) / len(nrs),
        "mean_win_net": statistics.mean(wins) if wins else 0.0,
        "mean_loss_net": statistics.mean(losses) if losses else 0.0,
        "worst_net": min(nrs), "best_net": max(nrs),
        "worst_R": Rs[0], "best_R": Rs[-1],
        "p05_net": _pct(nrs_sorted, 0.05), "p50_net": _pct(nrs_sorted, 0.50),
        "p90_R": _pct(Rs, 0.90), "p95_R": _pct(Rs, 0.95), "p99_R": _pct(Rs, 0.99),
        "sum_net_return": sum(nrs),
        "reasons": reasons,
    }


def all_mints() -> list[str]:
    return sorted(p.stem for p in BITQUERY_CANDLE_DIR.glob("*.jsonl"))
