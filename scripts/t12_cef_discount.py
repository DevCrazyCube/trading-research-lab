#!/usr/bin/env python3
"""T12 -- collection + census rig for shortlist candidate #5: closed-end-fund discount
mean reversion.

Frozen rule: research/trading_bot/T12_PREREGISTRATION.md

THIS MODULE COLLECTS AND COUNTS. In `census` mode it computes NO return: no price is ever
divided by another price, no discount is ever differenced, no portfolio exists. That is the
T9 discipline, and it is what lets the pre-registration quote the census as an a-priori fact.

The evaluator lives in `t12_evaluate.py` and refuses to run until the pre-registration's
sha256 is on disk.

Data sources, both read-only:
  * CEFConnect `/api/v3/DailyPricing`        -- the 360-fund LIVE snapshot (universe + statics)
  * CEFConnect `/api/v3/pricinghistory/{t}/{P}` -- price / NAV / discount history, P in
    {1M, 3M, 1Y, 3Y, 5Y}. 1Y is DAILY; 3Y and 5Y are WEEKLY-SAMPLED. This asymmetry is the
    single most important fact about this candidate and the census measures it rather than
    trusting the shortlist's summary of it.
  * Alpaca SIP daily bars + quotes -- for the traded PRICE leg and for the measured spread.
    CEF price history runs 2016->present; it is the NAV that is short.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                        # noqa: E402
from scripts.trading_bot.frozen import Refused                                    # noqa: E402

CACHE = ROOT / "research" / "data" / "t12_cache"
CACHE.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "research" / "trading_bot"

CEF_HOST = "https://www.cefconnect.com"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research/1.0", "Accept": "application/json"}

PERIODS = ("1M", "3M", "1Y", "3Y", "5Y")


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


def _get(url: str, tries: int = 4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as fh:
                return json.loads(fh.read().decode())
        except Exception as exc:                       # noqa: BLE001
            last = exc
            time.sleep(0.6 * (i + 1))
    raise Refused(f"CEFConnect refused {url}: {last}")


# ---------------------------------------------------------------------------
# 1. universe -- the LIVE snapshot, and it is live-only, which is a bias not a detail
# ---------------------------------------------------------------------------

def universe():
    """The 360-fund CEFConnect snapshot. LIVE FUNDS ONLY -- there is no delisted list here.

    This is recorded as a limitation in the census, not smoothed over: a fund that was
    liquidated, merged or converted to an ETF between 2021 and today is absent, and those are
    disproportionately the wide-discount funds whose discount was closed BY that event.
    """
    return cache_json("universe", lambda: _get(f"{CEF_HOST}/api/v3/DailyPricing"))


def history(ticker: str, period: str):
    if period not in PERIODS:
        raise Refused(f"period {period!r} is not one CEFConnect serves ({PERIODS})")
    doc = _get(f"{CEF_HOST}/api/v3/pricinghistory/{ticker}/{period}")
    data = (doc or {}).get("Data") or {}
    rows = data.get("PriceHistory") or []
    return [
        {
            "date": r["DataDateJs"].replace("/", "-"),
            "price": r["Data"],
            "nav": r["NAVData"],
            "discount": r["DiscountData"],
        }
        for r in rows
        if r.get("DataDateJs")
    ]


def all_histories(tickers, period: str):
    def build():
        out = {}

        def work(t):
            try:
                return t, history(t, period)
            except Refused:
                return t, None

        with ThreadPoolExecutor(max_workers=8) as pool:
            for t, rows in pool.map(work, tickers):
                out[t] = rows
        return out

    return cache_json(f"history_{period}", build)


# ---------------------------------------------------------------------------
# 2. the census -- COUNTS ONLY
# ---------------------------------------------------------------------------

def _span(rows):
    if not rows:
        return None, None, 0
    ds = sorted(r["date"] for r in rows)
    return ds[0], ds[-1], len(ds)


def _median_gap_days(rows):
    import datetime as dt
    ds = sorted({r["date"] for r in rows})
    if len(ds) < 3:
        return None
    d = [dt.date.fromisoformat(x) for x in ds]
    gaps = [(b - a).days for a, b in zip(d, d[1:])]
    return statistics.median(gaps)


def census():
    uni = universe()
    tickers = sorted({row["Ticker"] for row in uni if row.get("Ticker")})
    statics = {row["Ticker"]: row for row in uni}

    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "CEFConnect /api/v3/DailyPricing + /api/v3/pricinghistory",
        "universe_live_funds": len(tickers),
        "WARNING_live_only": (
            "CEFConnect serves only funds alive today. There is no delisted/liquidated list. "
            "Funds that merged, liquidated, converted to an ETF or were tendered by an "
            "activist between 2021 and today are ABSENT from every window below. Those are "
            "disproportionately the WIDE-DISCOUNT funds whose discount was closed BY the "
            "event, so the survivorship direction here is NOT obviously conservative."
        ),
        "periods": {},
    }

    for period in ("5Y", "1Y"):
        hist = all_histories(tickers, period)
        spans, ns, gaps = [], [], []
        first_dates, missing = [], 0
        n_disc_missing = 0
        for t in tickers:
            rows = hist.get(t)
            if not rows:
                missing += 1
                continue
            a, b, n = _span(rows)
            first_dates.append(a)
            spans.append((a, b))
            ns.append(n)
            g = _median_gap_days(rows)
            if g is not None:
                gaps.append(g)
            n_disc_missing += sum(1 for r in rows if r.get("discount") is None
                                  or r.get("nav") in (None, 0))
        all_dates = sorted({r["date"] for t in tickers for r in (hist.get(t) or [])})
        out["periods"][period] = {
            "funds_with_history": len(ns),
            "funds_with_no_history": missing,
            "obs_per_fund_min": min(ns) if ns else 0,
            "obs_per_fund_median": statistics.median(ns) if ns else 0,
            "obs_per_fund_max": max(ns) if ns else 0,
            "median_gap_between_obs_days": statistics.median(gaps) if gaps else None,
            "sampling": ("DAILY" if gaps and statistics.median(gaps) <= 2
                         else "WEEKLY" if gaps and statistics.median(gaps) <= 8 else "SPARSER"),
            "union_of_dates": len(all_dates),
            "first_date": all_dates[0] if all_dates else None,
            "last_date": all_dates[-1] if all_dates else None,
            "earliest_fund_start": min(first_dates) if first_dates else None,
            "latest_fund_start": max(first_dates) if first_dates else None,
            "rows_with_missing_nav_or_discount": n_disc_missing,
        }

    # liquidity statics, counts only
    adv = [r.get("AvgDailyVolume") for r in uni if r.get("AvgDailyVolume")]
    px = [r.get("Price") for r in uni if r.get("Price")]
    cap = [r.get("MarketCapUSDm") for r in uni if r.get("MarketCapUSDm")]
    dollar_adv = [r["AvgDailyVolume"] * r["Price"] for r in uni
                  if r.get("AvgDailyVolume") and r.get("Price")]
    out["liquidity_statics_today"] = {
        "n_with_adv": len(adv),
        "price_median": statistics.median(px) if px else None,
        "n_price_below_5": sum(1 for p in px if p < 5),
        "dollar_adv_median_usd": statistics.median(dollar_adv) if dollar_adv else None,
        "n_dollar_adv_above_1m": sum(1 for d in dollar_adv if d > 1e6),
        "n_dollar_adv_above_250k": sum(1 for d in dollar_adv if d > 250e3),
        "market_cap_musd_median": statistics.median(cap) if cap else None,
    }
    out["statics_note"] = (
        "Liquidity statics are TODAY's snapshot; CEFConnect publishes no history of them. "
        "A universe screen built on them is therefore look-ahead by construction and is "
        "declared as such wherever it is used."
    )
    return out, statics


# ---------------------------------------------------------------------------
# 3. shortability and friction -- costs and counts, still no return
# ---------------------------------------------------------------------------

def alpaca_asset_flags(tickers):
    """Alpaca's LIVE tradable/shortable/ETB flags for the CEF universe.

    A live snapshot with no history, exactly as `EDGE_SHORTLIST.md` section 2b records for the
    borrow-fee candidate. It cannot be backtested; it bounds what is EXECUTABLE TODAY, which is
    a different and still decisive question for a strategy with a short leg.
    """
    def build():
        assets = t3._get(t3.TRADING_HOST, "/v2/assets",
                         {"asset_class": "us_equity", "status": "active"})
        idx = {a["symbol"]: a for a in assets}
        return {
            t: (None if t not in idx else
                {k: idx[t].get(k) for k in
                 ("status", "tradable", "shortable", "easy_to_borrow", "fractionable",
                  "exchange")})
            for t in tickers
        }
    return cache_json("alpaca_assets", build)


def measure_cef_half_spread(tickers, dates, *, n_days=12, seed=20260817):
    """Median (ask - bid) / (2 * mid) in [15:59:59, 16:00:00) ET, SIP quotes, on the CEF names.

    Same instrument, window and declared deviation as `t3.measure_half_spread` -- reused rather
    than reinvented -- but sampled on the funds this candidate would actually trade, on dates
    drawn from its own weekly grid.
    """
    import random
    from collections import defaultdict as dd

    rng = random.Random(seed)
    sample = sorted(rng.sample(sorted(dates), min(n_days, len(dates))))

    def work(day):
        off = t3._ny_utc_offset(day)
        start = f"{day}T{15 + off:02d}:59:59Z"
        end = f"{day}T{16 + off:02d}:00:00Z"
        out = []
        for chunk in t3.chunks(sorted(tickers), 100):
            per_sym = dd(list)
            try:
                for block in t3.paged("/v2/stocks/quotes",
                                      {"symbols": ",".join(chunk), "start": start, "end": end,
                                       "limit": t3.PAGE, "feed": "sip"}, "quotes"):
                    for sym, quotes in block.items():
                        for q in quotes:
                            bid, ask = q.get("bp"), q.get("ap")
                            if not bid or not ask or ask <= bid:
                                continue
                            mid = 0.5 * (bid + ask)
                            bp = (ask - bid) / (2 * mid) * 1e4
                            if bp < 1000:
                                per_sym[sym].append(bp)
            except Refused:
                continue
            for sym, vals in per_sym.items():
                vals.sort()
                out.append(vals[len(vals) // 2])
        return out

    def build():
        values = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            for got in pool.map(work, sample):
                values.extend(got)
        values.sort()
        if not values:
            raise Refused("no CEF quotes returned; absence is a refusal, not a zero spread")
        q = lambda p: values[min(len(values) - 1, int(p * len(values)))]   # noqa: E731
        return {
            "n_symbol_days": len(values), "days_sampled": sample, "seed": seed,
            "median_half_spread_bp": q(0.50), "p25": q(0.25), "p75": q(0.75),
            "p90": q(0.90), "p95": q(0.95), "max": values[-1], "min": values[0],
            "window": "[15:59:59, 16:00:00) ET, SIP quotes, median per symbol-day",
        }

    return cache_json("cef_half_spread", build)


def friction_census():
    uni = universe()
    tickers = sorted({r["Ticker"] for r in uni if r.get("Ticker")})
    flags = alpaca_asset_flags(tickers)
    found = {t: v for t, v in flags.items() if v}
    hist = all_histories(tickers, "5Y")
    dates = sorted({r["date"] for rows in hist.values() if rows for r in rows})
    # only dates Alpaca can quote: the last 12 months of the weekly grid, to keep the pull small
    recent = [d for d in dates if d >= "2025-08-01"]
    spread = measure_cef_half_spread(tickers, recent)
    return {
        "alpaca_universe_match": {
            "cef_tickers": len(tickers),
            "found_active_at_alpaca": len(found),
            "not_found": sorted(t for t, v in flags.items() if not v),
            "tradable": sum(1 for v in found.values() if v["tradable"]),
            "shortable": sum(1 for v in found.values() if v["shortable"]),
            "easy_to_borrow": sum(1 for v in found.values() if v["easy_to_borrow"]),
            "shortable_share": round(
                sum(1 for v in found.values() if v["shortable"]) / max(1, len(found)), 4),
            "note": (
                "LIVE FLAGS, NO HISTORY. This bounds what is executable today; it cannot be "
                "backtested and is not applied as a historical universe screen anywhere."
            ),
        },
        "measured_quoted_half_spread": spread,
    }


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "census"
    if cmd == "friction":
        doc = friction_census()
        path = OUT / "T12_FRICTION_CENSUS.json"
        path.write_text(json.dumps(doc, indent=2) + "\n")
        print(json.dumps(doc, indent=2))
        print(f"\nwrote {path}")
    elif cmd == "census":
        doc, _ = census()
        path = OUT / "T12_DATA_CENSUS.json"
        path.write_text(json.dumps(doc, indent=2) + "\n")
        print(json.dumps(doc, indent=2))
        print(f"\nwrote {path}")
    else:
        raise SystemExit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main(sys.argv)
