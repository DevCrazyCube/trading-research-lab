#!/usr/bin/env python3
"""T9 -- collection rig for shortlist candidate #4: spin-off forced-selling drift.

Frozen rule: research/trading_bot/T9_PREREGISTRATION.md

This module COLLECTS and CENSUSES. It computes no return and no verdict; the verdict lives in
`t9_evaluate.py`, which refuses to run without a frozen pre-registration hash on disk.

Reuse rather than reimplementation: the trading calendar, the HTTP transport, the paging rule
and the official-auction-print reader all come from `scripts/t3_pressure_reversal.py` unchanged,
and the universe-wide corporate-actions sweep comes from the cache
`research/data/t7_cache/corporate_actions_all.json.gz` that T7 already paid for.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                       # noqa: E402
from scripts.trading_bot.frozen import Refused                                   # noqa: E402

CACHE = ROOT / "research" / "data" / "t9_cache"
CACHE.mkdir(parents=True, exist_ok=True)

NON_TICKER_DROPPED = []
T7_CACHE = ROOT / "research" / "data" / "t7_cache" / "corporate_actions_all.json.gz"

START, END = t3.START, t3.END
DESIGN_END, TEST_START = t3.DESIGN_END, t3.TEST_START
HEDGE = "SPY"


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
# 1. the events
# ---------------------------------------------------------------------------

def spinoff_events():
    """Every unique `spin_off` record, 2016-01-04 .. 2026-08-14, universe-wide.

    Deduplication is on the provider's own `id`, then on (source_symbol, new_symbol, ex_date):
    the raw feed repeats a record when it is restated, and FINDINGS.md section 8 records that a
    key made of field values is not an identity.
    """
    with gzip.open(T7_CACHE, "rt") as fh:
        ca = json.load(fh)
    if "spin_offs" not in ca:
        raise Refused("corporate-actions cache has no spin_offs key; that is not zero rows")
    by_id, by_key = {}, {}
    for ev in ca["spin_offs"]:
        by_id[ev["id"]] = ev
    for ev in by_id.values():
        by_key[(ev.get("source_symbol"), ev.get("new_symbol"), ev.get("ex_date"))] = ev
    out = [ev for ev in by_key.values() if ev.get("ex_date") and START <= ev["ex_date"] <= END]
    return sorted(out, key=lambda e: (e["ex_date"], e["new_symbol"]))


TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")


def is_tradeable_stub(ev) -> bool:
    """A `spin_off` record whose `new_symbol` is not a ticker is not a spin-off stub.

    The feed types contingent value rights (`...CVR...`), contingent/escrow entitlements
    (`...CNT...`, `...ESC...`) and bare CUSIPs as `spin_off`. They are merger consideration, not
    a distributed equity stub, and nothing quotes them. Excluding them is a definition, applied
    identically in both periods, and the count it removes is reported.
    """
    return bool(TICKER.match(ev.get("new_symbol") or ""))


# ---------------------------------------------------------------------------
# 2. prices
# ---------------------------------------------------------------------------

def daily_bars(symbols, name="daily_bars"):
    """symbol -> {date: {o,h,l,c,v,vw}} RAW (unadjusted) SIP daily bars."""
    def build():
        out = defaultdict(dict)

        def work(chunk):
            local = defaultdict(dict)
            for block in t3.paged("/v2/stocks/bars",
                                  {"symbols": ",".join(chunk), "start": START, "end": END,
                                   "timeframe": "1Day", "adjustment": "raw",
                                   "limit": t3.PAGE, "feed": "sip"}, "bars"):
                for sym, rows in block.items():
                    for r in rows:
                        local[sym][r["t"][:10]] = {
                            "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"],
                            "v": r["v"], "vw": r.get("vw"),
                        }
            return local

        with ThreadPoolExecutor(max_workers=6) as pool:
            for local in pool.map(work, list(t3.chunks(sorted(set(symbols)), 40))):
                for sym, rows in local.items():
                    out[sym].update(rows)
        return dict(out)
    return cache_json(name, build)


def stub_auctions(symbols):
    """(symbol|date) -> {'o','c'} official auction prints, for the stub names."""
    def build():
        out = {}

        def work(chunk):
            local = {}
            for block in t3.paged("/v2/stocks/auctions",
                                  {"symbols": ",".join(chunk), "start": START, "end": END,
                                   "limit": t3.PAGE, "feed": "sip"}, "auctions"):
                for sym, days in block.items():
                    for d in days:
                        rec = {}
                        for leg, code in (("o", "O"), ("c", "6")):
                            prints = [p for p in (d.get(leg) or []) if p.get("c") == code]
                            if prints:
                                best = max(prints, key=lambda p: p.get("s", 0))
                                rec[leg] = best["p"]
                        if rec:
                            local[f"{sym}|{d['d']}"] = rec
            return local

        with ThreadPoolExecutor(max_workers=6) as pool:
            for local in pool.map(work, list(t3.chunks(sorted(set(symbols)), 40))):
                out.update(local)
        return out
    return cache_json("stub_auctions", build)


# ---------------------------------------------------------------------------
# 3. census -- COUNTS ONLY. No return is computed anywhere in this file.
# ---------------------------------------------------------------------------

def census():
    all_events = spinoff_events()
    events = [e for e in all_events if is_tradeable_stub(e)]
    global NON_TICKER_DROPPED
    NON_TICKER_DROPPED = [e for e in all_events if not is_tradeable_stub(e)]
    stubs = sorted({e["new_symbol"] for e in events})
    parents = sorted({e["source_symbol"] for e in events
                      if e.get("source_symbol") and TICKER.match(e["source_symbol"])})
    bars = daily_bars(stubs + parents + [HEDGE])
    auct = stub_auctions(stubs + [HEDGE])
    cal = [r["date"] for r in t3.calendar() if r["date"] >= "2016-01-01"]
    idx = {d: i for i, d in enumerate(cal)}

    rows = []
    for e in events:
        sym, ex = e["new_symbol"], e["ex_date"]
        b = bars.get(sym, {})
        i = idx.get(ex)
        rec = {
            "ex_date": ex, "stub": sym, "parent": e.get("source_symbol"),
            "period": "design" if ex <= DESIGN_END else "test",
            "has_bar_on_ex": ex in b,
            "n_bars_after_60": 0, "entry_close": None, "entry_dollar_vol": None,
            "has_auction_close_on_ex": f"{sym}|{ex}" in auct and "c" in auct.get(f"{sym}|{ex}", {}),
        }
        if i is not None:
            fwd = [d for d in cal[i:i + 130] if d in b]
            rec["n_bars_after_60"] = sum(1 for d in cal[i:i + 61] if d in b)
            rec["n_bars_after_126"] = sum(1 for d in cal[i:i + 127] if d in b)
            if ex in b:
                rec["entry_close"] = b[ex]["c"]
                rec["entry_dollar_vol"] = (b[ex].get("vw") or b[ex]["c"]) * b[ex]["v"]
            rec["first_bar_on_or_after_ex"] = fwd[0] if fwd else None
        rows.append(rec)
    return rows


def main():
    rows = census()
    out = ROOT / "research" / "trading_bot" / "T9_EVENT_CENSUS.json"
    design = [r for r in rows if r["period"] == "design"]
    test = [r for r in rows if r["period"] == "test"]

    def summarise(rs):
        return {
            "n_events": len(rs),
            "n_with_bar_on_ex_date": sum(1 for r in rs if r["has_bar_on_ex"]),
            "n_with_auction_close_on_ex_date": sum(1 for r in rs if r["has_auction_close_on_ex"]),
            "n_with_60_forward_sessions": sum(1 for r in rs if r.get("n_bars_after_60", 0) >= 55),
            "n_with_126_forward_sessions": sum(1 for r in rs if r.get("n_bars_after_126", 0) >= 115),
            "n_entry_dollar_vol_gt_1m": sum(1 for r in rs
                                            if (r["entry_dollar_vol"] or 0) > 1_000_000),
            "n_entry_price_gt_5": sum(1 for r in rs if (r["entry_close"] or 0) > 5.0),
        }

    payload = {
        "generated_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "source": "research/data/t7_cache/corporate_actions_all.json.gz (universe-wide sweep)",
        "note": "COUNTS ONLY. No return, no signal, no portfolio is computed in this file.",
        "by_year": dict(sorted(__import__("collections").Counter(
            r["ex_date"][:4] for r in rows).items())),
        "non_ticker_records_dropped": len(NON_TICKER_DROPPED),
        "non_ticker_by_year": dict(sorted(__import__("collections").Counter(
            e["ex_date"][:4] for e in NON_TICKER_DROPPED).items())),
        "design_2016_2021": summarise(design),
        "test_2022_2026": summarise(test),
        "all": summarise(rows),
        "events": rows,
    }
    out.write_text(json.dumps(payload, indent=1))
    print(json.dumps({k: v for k, v in payload.items() if k != "events"}, indent=1))


if __name__ == "__main__":
    main()
