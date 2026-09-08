#!/usr/bin/env python3
"""T7 -- collection rig for shortlist candidate #2: ex-dividend drop-off, executed
close-to-close in the auctions.

Frozen rule: research/trading_bot/T7_PREREGISTRATION.md
             sha256 7bd072a7565a27b39d83a35afa659fb4c80bdf700dcb84e1100ea0e1816c7cdd

This module COLLECTS and builds the panel. It computes no verdict and knows nothing about the
eight declared configurations -- that lives in `t7_evaluate.py`, which cannot run the held-out
period without a frozen-config file on disk.

Reuse rather than reimplementation, deliberately: the calendar, the asset pool, the
point-in-time monthly universe screen and the official auction prints all come from
`scripts/t3_pressure_reversal.py` unchanged. They are the same verified objects the T3 run used,
and their caches are already on disk. The only new pull is the universe-wide corporate-actions
sweep, which T3 cached as DATES ONLY and this candidate needs RATES from.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                       # noqa: E402
from scripts.trading_bot.frozen import Refused                                   # noqa: E402

CACHE = ROOT / "research" / "data" / "t7_cache"
CACHE.mkdir(parents=True, exist_ok=True)

PREREG_SHA = "7bd072a7565a27b39d83a35afa659fb4c80bdf700dcb84e1100ea0e1816c7cdd"

START, END = t3.START, t3.END
DESIGN_END, TEST_START = t3.DESIGN_END, t3.TEST_START

HEDGE = "SPY"
MAX_YIELD = 0.20          # pre-registration section 5.5: above this it is a partial liquidation


def cache_json(name: str, build):
    path = CACHE / f"{name}.json.gz"
    if path.exists():
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    value = build()
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as fh:
        json.dump(value, fh)
    tmp.rename(path)
    return value


# ---------------------------------------------------------------------------
# 1. corporate actions, universe-wide, WITH RATES
# ---------------------------------------------------------------------------

def _months(start: str, end: str):
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= end[:7]:
        nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((f"{y:04d}-{m:02d}-01", f"{nm_y:04d}-{nm_m:02d}-01"))
        y, m = nm_y, nm_m
    return out


def corporate_actions_all():
    """Every corporate action of every type, universe-wide, month by month, fully paged.

    The endpoint serves the WHOLE market when no `symbols` parameter is given, which is both
    cheaper and less error-prone than chunking by symbol: a symbol chunk that silently 400s
    would look like "this name paid no dividends".
    """
    def build():
        out = defaultdict(list)

        def work(window):
            s, e = window
            local = defaultdict(list)
            for block in t3.paged("/v1/corporate-actions",
                                  {"start": s, "end": e, "limit": 1000}, "corporate_actions"):
                for kind, events in block.items():
                    local[kind].extend(events)
            return local

        windows = _months(START, END)
        with ThreadPoolExecutor(max_workers=6) as pool:
            for i, local in enumerate(pool.map(work, windows)):
                for kind, events in local.items():
                    out[kind].extend(events)
                if (i + 1) % 12 == 0:
                    print(f"    corporate actions: {i + 1}/{len(windows)} months", flush=True)
        return {k: v for k, v in out.items()}
    return cache_json("corporate_actions_all", build)


def split_actions(ca_all):
    """(cash dividends, non-cash action dates by symbol).

    A cash dividend is the EVENT. Everything else -- splits, stock dividends, spin-offs, mergers,
    redemptions, name changes -- is a reason to DROP an event, because a raw price series shows a
    mechanical gap across it and this test measures a raw price change against a raw dividend.
    """
    dividends, blocked = [], defaultdict(set)
    for kind, events in ca_all.items():
        for ev in events:
            if kind == "cash_dividends":
                if ev.get("symbol") and ev.get("ex_date") and ev.get("rate") is not None:
                    dividends.append({"symbol": ev["symbol"], "ex_date": ev["ex_date"],
                                      "rate": float(ev["rate"]),
                                      "special": bool(ev.get("special", False))})
                continue
            for field in ("symbol", "target_symbol", "new_symbol", "old_symbol",
                          "acquirer_symbol", "source_symbol", "initiating_symbol"):
                sym = ev.get(field)
                if not sym:
                    continue
                for datefield in ("ex_date", "process_date", "effective_date", "payable_date"):
                    if ev.get(datefield):
                        blocked[sym].add(ev[datefield])
    return dividends, {k: v for k, v in blocked.items()}


# ---------------------------------------------------------------------------
# 2. the panel
# ---------------------------------------------------------------------------

def build_panel():
    """day -> {spy, cum, events, control}. Every exclusion of section 5 applied once, here.

    `events`  : [symbol, p_cum, p_ex, rate, special]  -- the real ex-dividend names
    `control` : [symbol, price_return]                -- every OTHER universe member that had
                both closing auction prints and no corporate action on either day. This is the
                permutation's draw pool and the second pairing, and it is built with exactly the
                same price-availability and corporate-action filters as the events, so the two
                populations differ ONLY in whether a dividend went ex.
    """
    cal = t3.calendar()
    cal = [r for r in cal if r["date"] >= "2016-01-01"]
    days = [r["date"] for r in cal]
    close_by_day = {r["date"]: r["close"] for r in cal}
    prev = {days[i]: days[i - 1] for i in range(1, len(days))}

    uni500 = t3.build_universe(500)
    union = sorted({s for syms in uni500.values() for s in syms})
    month_sets = {m: set(v) for m, v in uni500.items()}
    print(f"universe union: {len(union)} symbols", flush=True)

    auct = t3.auctions(union)
    print(f"auction records: {len(auct)}", flush=True)

    ca_all = corporate_actions_all()
    print("corporate action types: "
          + ", ".join(f"{k}={len(v)}" for k, v in sorted(ca_all.items())), flush=True)
    dividends, blocked = split_actions(ca_all)
    print(f"cash dividends universe-wide: {len(dividends)}", flush=True)

    # ---- SPY's own ex-dates: a short hedge held across one owes the dividend (section 5.7)
    spy_ex = {d["ex_date"] for d in dividends if d["symbol"] == HEDGE}
    if not spy_ex:
        raise Refused("no SPY cash dividends found; a hedge exclusion that never fires is a bug, "
                      "not a clean hedge")

    # ---- group dividends by ex_date, summing same-day rates for one symbol (section 3)
    by_day = defaultdict(dict)
    for d in dividends:
        if not (START <= d["ex_date"] <= END):
            continue
        slot = by_day[d["ex_date"]].setdefault(d["symbol"], {"rate": 0.0, "special": False})
        slot["rate"] += d["rate"]
        slot["special"] = slot["special"] or d["special"]

    stats = defaultdict(int)
    panel = {}
    trading = set(days)

    for ex_date in sorted(by_day):
        if ex_date not in trading:
            stats["day_dropped_ex_date_not_a_trading_day"] += 1
            continue
        cum = prev.get(ex_date)
        if cum is None:
            stats["day_dropped_no_previous_trading_day"] += 1
            continue
        if close_by_day.get(cum) != "16:00" or close_by_day.get(ex_date) != "16:00":
            stats["day_dropped_early_close"] += 1
            continue
        if cum in spy_ex or ex_date in spy_ex:
            stats["day_dropped_spy_own_ex_date"] += 1
            continue
        spy_c, spy_e = auct.get(f"{HEDGE}|{cum}"), auct.get(f"{HEDGE}|{ex_date}")
        if not spy_c or not spy_e or "c" not in spy_c or "c" not in spy_e:
            stats["day_dropped_missing_spy_auction"] += 1
            continue
        if spy_c["c"] <= 0 or spy_e["c"] <= 0:
            stats["day_dropped_nonpositive_spy"] += 1
            continue

        eligible = month_sets.get(cum[:7], set()) & month_sets.get(ex_date[:7], set())
        ex_names = by_day[ex_date]

        def prints(sym):
            a, b = auct.get(f"{sym}|{cum}"), auct.get(f"{sym}|{ex_date}")
            if not a or not b or "c" not in a or "c" not in b:
                return None
            if a["c"] <= 0 or b["c"] <= 0:
                return None
            return a["c"], b["c"]

        def action_blocked(sym):
            hits = blocked.get(sym)
            return bool(hits) and (cum in hits or ex_date in hits)

        events = []
        for sym, info in sorted(ex_names.items()):
            if sym not in eligible:
                stats["event_dropped_not_in_universe"] += 1
                continue
            if info["rate"] <= 0:
                stats["event_dropped_nonpositive_rate"] += 1
                continue
            if action_blocked(sym):
                stats["event_dropped_other_corporate_action"] += 1
                continue
            pair = prints(sym)
            if pair is None:
                stats["event_dropped_missing_auction_print"] += 1
                continue
            p_cum, p_ex = pair
            if info["rate"] / p_cum > MAX_YIELD:
                stats["event_dropped_yield_above_20pct"] += 1
                continue
            events.append([sym, p_cum, p_ex, info["rate"], bool(info["special"])])
            stats["event_kept"] += 1

        if not events:
            stats["day_dropped_no_surviving_event"] += 1
            continue

        control = []
        for sym in eligible:
            if sym in ex_names or sym == HEDGE:
                continue
            if action_blocked(sym):
                continue
            pair = prints(sym)
            if pair is None:
                continue
            control.append([sym, pair[1] / pair[0] - 1.0])

        panel[ex_date] = {
            "cum": cum,
            "spy": spy_e["c"] / spy_c["c"] - 1.0,
            "spy_price": spy_c["c"],
            "events": events,
            "control": control,
        }
        stats["day_kept"] += 1

    return panel, dict(stats)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "panel"
    if cmd == "panel":
        panel, stats = build_panel()
        print(json.dumps(stats, indent=2))
        print("event-days in panel:", len(panel))
        print("events kept:", sum(len(v["events"]) for v in panel.values()))
        with gzip.open(CACHE / "panel.json.gz", "wt") as fh:
            json.dump({"panel": panel, "stats": stats,
                       "preregistration_sha256": PREREG_SHA}, fh)
        print("panel written")
