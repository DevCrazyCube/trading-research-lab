#!/usr/bin/env python3
"""T11 -- collection rig for shortlist candidate #7: cash-merger arbitrage spread.

Frozen rule: research/trading_bot/T11_PREREGISTRATION.md

This module COLLECTS and CENSUSES. It computes no return, no spread and no verdict; the verdict
lives in `t11_evaluate.py`, which refuses to run without the frozen pre-registration hash on disk.

Reuse rather than reimplementation: the trading calendar, HTTP transport, paging rule and the
official-auction-print reader come from `scripts/t3_pressure_reversal.py` unchanged, and the
universe-wide corporate-actions sweep comes from the cache
`research/data/t7_cache/corporate_actions_all.json.gz` that T7 already paid for.

TWO THINGS THIS FILE MEASURES THAT DECIDE THE DESIGN, AND BOTH ARE COUNTS:

1. **Announcement-date recoverability.** `/v1/corporate-actions` supplies the merger's EFFECTIVE
   date and cash rate but not its ANNOUNCEMENT date. `announcement_probe()` measures how often a
   deterministic headline rule recovers one from the Benzinga news endpoint, on a random sample.
   The number it returns is the reason the traded rule in the pre-registration does not use an
   announcement date at all.

2. **Survivorship.** Every record in `cash_mergers` is a merger that COMPLETED. A deal that was
   announced and then broke leaves no corporate action of any kind. The census reports what the
   feed contains; it cannot report what the feed structurally cannot contain, and the
   pre-registration is built around that fact rather than around a hope.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import random
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                        # noqa: E402
from scripts.trading_bot.frozen import Refused                                    # noqa: E402

CACHE = ROOT / "research" / "data" / "t11_cache"
CACHE.mkdir(parents=True, exist_ok=True)

T7_CACHE = ROOT / "research" / "data" / "t7_cache" / "corporate_actions_all.json.gz"

START, END = t3.START, t3.END
DESIGN_END, TEST_START = t3.DESIGN_END, t3.TEST_START
RISK_FREE_PROXY = "BIL"          # 1-3 month T-bill ETF; the null's benchmark
MARKET = "SPY"                   # control-basket market leg only

TICKER = re.compile(r"^[A-Z]{1,5}$")


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

def cash_merger_events():
    """Every unique `cash_merger` record, 2016-01-04 .. 2026-08-14, universe-wide.

    Deduplicated on the provider's own `id` first, then on
    (acquiree_symbol, effective_date, rate) -- FINDINGS.md section 8 records that a key made of
    field values is not an identity, so the id comes first and the value key only collapses
    genuine restatements.
    """
    with gzip.open(T7_CACHE, "rt") as fh:
        ca = json.load(fh)
    if "cash_mergers" not in ca:
        raise Refused("corporate-actions cache has no cash_mergers key; that is not zero rows")
    by_id = {ev["id"]: ev for ev in ca["cash_mergers"]}
    by_key = {}
    for ev in by_id.values():
        by_key[(ev.get("acquiree_symbol"), ev.get("effective_date"), ev.get("rate"))] = ev
    out = [ev for ev in by_key.values()
           if ev.get("effective_date") and START <= ev["effective_date"] <= END]
    return sorted(out, key=lambda e: (e["effective_date"], e.get("acquiree_symbol") or ""))


def is_ticker_shaped(ev) -> bool:
    """A `cash_merger` record whose acquiree is a bare CUSIP is not a listed-equity event."""
    return bool(TICKER.match(ev.get("acquiree_symbol") or ""))


# ---------------------------------------------------------------------------
# 2. prices
# ---------------------------------------------------------------------------

def daily_bars(symbols, name="daily_bars"):
    """symbol -> {date: {o,h,l,c,v,vw}} RAW (unadjusted) SIP daily bars.

    RAW is mandatory here and not a preference: the merger `rate` is a cash amount per share as
    of the effective date, and dividing it by a split/dividend-adjusted price is a category
    error that would manufacture a spread out of the adjustment factor.
    """
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


def target_auctions(symbols, name="target_auctions"):
    """(symbol|date) -> {'o','c'} official auction prints for the acquiree names."""
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
    return cache_json(name, build)


# ---------------------------------------------------------------------------
# 3. announcement-date recoverability -- the cheap first step EDGE_SHORTLIST asked for
# ---------------------------------------------------------------------------

# The LOOSE rule: any acquisition-shaped phrase in a headline tagged to the acquiree.
LOOSE_ANN = re.compile(
    r"(to be acquired|to acquire|acquisition of|agrees? to (be )?acqui|"
    r"definitive (merger )?agreement|merger agreement|buyout|take[- ]private|"
    r"go(ing)?[- ]private|tender offer|/share in cash|per share in cash|cash offer|"
    r"agreed to be acquired|enters into .{0,40}merger)", re.I)

# The STRICT rule: the same, but the acquiree must appear in the OBJECT position of the
# acquisition -- otherwise "PAE to Acquire CENTRA Technology" reads as PAE being acquired.
_OBJECT = re.compile(
    r"(to acquire|to buy|acquisition of|acquires|agrees to (buy|acquire)|will acquire|"
    r"to purchase|tender offer (for|to acquire))\s+", re.I)
_PASSIVE = (r"to be acquired", r"agreed to be acquired", r"to be taken private",
            r"go(ing)? private", r"per share in cash", r"/share in cash",
            r"all[- ]cash (deal|transaction|merger)")

_NAME_STOP = {
    'inc', 'corp', 'corporation', 'co', 'company', 'ltd', 'llc', 'plc', 'holdings', 'holding',
    'group', 'the', 'of', 'and', 'international', 'technologies', 'technology',
    'pharmaceuticals', 'pharma', 'bancorp', 'bancshares', 'financial', 'systems', 'sciences',
    'therapeutics', 'resources', 'energy', 'industries', 'solutions', 'partners', 'trust',
    'acquisition', 'common', 'stock', 'class', 'a', 'usd', 'ordinary', 'shares', 'american',
    'depositary',
}


def asset_names():
    """symbol -> issuer name, active AND inactive. Used only by the announcement probe."""
    def build():
        out = {}
        for status in ("active", "inactive"):
            rows = t3._get("https://paper-api.alpaca.markets", "/v2/assets",
                           {"asset_class": "us_equity", "status": status})
            for a in rows:
                out.setdefault(a["symbol"], a.get("name") or "")
        return out
    return cache_json("asset_names", build)


def _core_token(name: str):
    toks = [t for t in re.findall(r"[A-Za-z][A-Za-z'&-]+", name or "")
            if t.lower() not in _NAME_STOP]
    return toks[0] if toks else None


def _strict_hit(headline: str, target_token: str) -> bool:
    if not target_token:
        return False
    hl, t = headline.lower(), target_token.lower()
    if t not in hl:
        return False
    for m in _OBJECT.finditer(headline):
        if t in hl[m.end():m.end() + 70]:
            return True
    for pat in _PASSIVE:
        for m in re.finditer(pat, hl):
            if t in hl[:m.start()]:
                return True
    return False


def announcement_probe(sample_n: int = 80, seed: int = 20260817, lookback_days: int = 760):
    """Measure, on a random sample of completed cash mergers, how often the announcement date
    can be recovered from Benzinga headlines under a LOOSE and a STRICT deterministic rule.

    Returns counts only. No price is read anywhere in this function.
    """
    def build():
        events = [e for e in cash_merger_events() if is_ticker_shaped(e)]
        names = asset_names()
        rng = random.Random(seed)
        sample = rng.sample(events, min(sample_n, len(events)))
        rows = []
        for ev in sample:
            sym, eff = ev["acquiree_symbol"], ev["effective_date"]
            nm = names.get(sym, "")
            tok = _core_token(nm)
            eff_d = date.fromisoformat(eff)
            start = (eff_d - timedelta(days=lookback_days)).isoformat()
            loose = strict = None
            pages, seen, token = 0, 0, None
            while True:
                params = {"symbols": sym, "start": start, "end": eff,
                          "limit": 50, "sort": "asc"}
                if token:
                    params["page_token"] = token
                try:
                    payload = t3.data_get("/v1beta1/news", params)
                except Refused:
                    break
                pages += 1
                items = payload.get("news") or []
                seen += len(items)
                for n in items:
                    h = n.get("headline") or ""
                    if loose is None and LOOSE_ANN.search(h):
                        loose = {"ts": n["created_at"], "headline": h[:120]}
                    if strict is None and _strict_hit(h, tok):
                        strict = {"ts": n["created_at"], "headline": h[:120]}
                if loose is not None and strict is not None:
                    break
                token = payload.get("next_page_token")
                if not token or pages > 25:
                    break
            rows.append({
                "symbol": sym, "effective_date": eff, "issuer_name": nm,
                "name_known": bool(nm), "news_items_seen": seen, "pages": pages,
                "loose": loose, "strict": strict,
                "loose_lag_days": (eff_d - date.fromisoformat(loose["ts"][:10])).days
                                  if loose else None,
                "strict_lag_days": (eff_d - date.fromisoformat(strict["ts"][:10])).days
                                   if strict else None,
            })
        return rows
    return cache_json(f"announcement_probe_{sample_n}_{seed}", build)


# ---------------------------------------------------------------------------
# 4. census -- COUNTS ONLY. No return is computed anywhere in this file.
# ---------------------------------------------------------------------------

MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 1_000_000.0
STOPS_TRADING_WITHIN = 10        # sessions after effective_date; see prereg section 4


def census(horizons=(5, 21, 63)):
    all_events = cash_merger_events()
    events = [e for e in all_events if is_ticker_shaped(e)]
    syms = sorted({e["acquiree_symbol"] for e in events})
    bars = daily_bars(syms + [RISK_FREE_PROXY, MARKET])
    auct = target_auctions(syms + [RISK_FREE_PROXY, MARKET])
    cal = [r["date"] for r in t3.calendar() if r["date"] >= "2016-01-01"]
    idx = {d: i for i, d in enumerate(cal)}

    rows = []
    for e in events:
        sym, eff = e["acquiree_symbol"], e["effective_date"]
        b = bars.get(sym, {})
        rec = {
            "effective_date": eff, "symbol": sym, "rate": e.get("rate"),
            "acquirer": e.get("acquirer_symbol"),
            "period": "design" if eff <= DESIGN_END else "test",
            "n_bars": len(b),
            "has_any_bar": bool(b),
            "rate_positive": bool(e.get("rate") and e["rate"] > 0),
        }
        # last session with a bar at or before the effective date
        prior = [d for d in b if d <= eff]
        rec["last_bar_on_or_before_eff"] = max(prior) if prior else None
        after = [d for d in b if d > eff]
        rec["n_bars_after_eff"] = len(after)
        if rec["last_bar_on_or_before_eff"] and rec["last_bar_on_or_before_eff"] in idx:
            j = idx[rec["last_bar_on_or_before_eff"]]
            # does the name stop trading? a recycled ticker keeps printing bars
            cut = cal[min(j + STOPS_TRADING_WITHIN, len(cal) - 1)]
            rec["stops_trading"] = not any(d > cut for d in after)
            for h in horizons:
                k = j - h
                if k < 0:
                    rec[f"entry_{h}"] = None
                    continue
                d0 = cal[k]
                key = f"{sym}|{d0}"
                has_auc = "c" in (auct.get(key) or {})
                bar = b.get(d0)
                rec[f"entry_{h}"] = {
                    "date": d0,
                    "has_bar": bar is not None,
                    "has_auction_close": has_auc,
                    "close": bar["c"] if bar else None,
                    "dollar_vol": ((bar.get("vw") or bar["c"]) * bar["v"]) if bar else None,
                }
        else:
            rec["stops_trading"] = None
            for h in horizons:
                rec[f"entry_{h}"] = None
        rows.append(rec)
    return rows, {"raw_records": len(all_events), "ticker_shaped": len(events)}


def _summarise(rows, h):
    c = Counter()
    c["events"] = len(rows)
    for r in rows:
        if not r["rate_positive"]:
            continue
        c["rate_positive"] += 1
        if not r["has_any_bar"]:
            continue
        c["has_bars"] += 1
        if not r["stops_trading"]:
            continue
        c["stops_trading"] += 1
        e = r.get(f"entry_{h}")
        if not e or not e["has_bar"]:
            continue
        c["entry_bar"] += 1
        if not e["has_auction_close"]:
            continue
        c["entry_auction_close"] += 1
        if e["close"] is None or e["close"] <= MIN_PRICE:
            continue
        c["price_gt_5"] += 1
        if not e["dollar_vol"] or e["dollar_vol"] <= MIN_DOLLAR_VOL:
            continue
        c["dollar_vol_gt_1m"] += 1
    return dict(c)


def main():
    rows, raw = census()
    by_year = Counter(r["effective_date"][:4] for r in rows)
    design = [r for r in rows if r["period"] == "design"]
    test = [r for r in rows if r["period"] == "test"]
    probe = announcement_probe()

    loose = sum(1 for p in probe if p["loose"])
    strict = sum(1 for p in probe if p["strict"])
    named = sum(1 for p in probe if p["name_known"])

    out = {
        "raw": raw,
        "by_year": dict(sorted(by_year.items())),
        "funnel": {
            str(h): {"design": _summarise(design, h), "test": _summarise(test, h)}
            for h in (5, 21, 63)
        },
        "announcement_probe": {
            "n": len(probe),
            "issuer_name_available": named,
            "loose_rule_matched": loose,
            "strict_rule_matched": strict,
            "loose_lag_days": sorted(p["loose_lag_days"] for p in probe if p["loose"]),
            "strict_lag_days": sorted(p["strict_lag_days"] for p in probe if p["strict"]),
            "note": (
                "LOOSE matches any acquisition-shaped phrase on a headline tagged to the "
                "acquiree and is contaminated by the acquiree ACQUIRING someone else; STRICT "
                "requires the acquiree in the object position and depends on an issuer name "
                "the asset endpoint often does not have for a delisted symbol. Neither is an "
                "announcement-date feed."
            ),
        },
        "survivorship_note": (
            "Every record counted here is a merger that COMPLETED. An announced deal that broke "
            "leaves no corporate action of any type, so the break tail is not merely rare in "
            "this census -- it is structurally absent."
        ),
    }
    path = ROOT / "research" / "trading_bot" / "T11_EVENT_CENSUS.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out["raw"]))
    print(json.dumps(out["by_year"]))
    for h in ("5", "21", "63"):
        print(h, json.dumps(out["funnel"][h]))
    print(json.dumps(out["announcement_probe"], indent=1)[:1200])
    print("wrote", path)


if __name__ == "__main__":
    main()
