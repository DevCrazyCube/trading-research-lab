#!/usr/bin/env python3
"""M0 -- is the auction rail free? A MEASUREMENT, not a strategy.

THE QUESTION
============
Shortlist candidates #1 (T3, pressure reversal) and #2 (T7, ex-dividend drop-off) both priced
at least one leg at ZERO spread on the grounds that a single-price call auction has no bid-ask
to cross. `costs.py` carries that as `SlippageProvenance.EXCHANGE_MECHANISM_UNVERIFIED_FILL`
and says in as many words that it is legitimate ONLY while the order actually fills AT the
print, and that this is M0 and UNPERFORMED. This script performs it.

WHAT IS ACTUALLY MEASURABLE FROM HISTORY, AND WHAT IS NOT
=========================================================
Not measurable from a SIP tape: whether *our* order would have been accepted, queued and
matched. That needs live orders and accrues over real sessions (see the SECONDARY plan in the
result document). What IS measurable, and is what the backtests actually leaned on:

  1. **Does an official auction print exist at all** for the name on the day? A MOC that has no
     auction to clear in is not a zero-cost fill, it is an unfilled order that becomes a market
     order the next morning. Measured as an availability rate per liquidity tier.
  2. **Where does the print sit relative to the last free reference price** -- the closing-second
     NBBO midpoint, and the volume-weighted closing minute? A trader submitting MOC before the
     cutoff knows the midpoint; they do not know the print. The gap between them is the price
     risk the zero-spread assumption denies exists.
  3. **Does that gap revert?** A dislocation that reverts overnight is a genuine cost to whoever
     had to transact in the auction; a permanent one is just the price discovering.
  4. **How big is the auction?** A print of 400 shares is not a free liquidity event.

Sign convention throughout: `dev_bp = (print - reference) / reference * 1e4`. Positive means the
print cleared ABOVE the reference, which is adverse to a BUYER and favourable to a SELLER.

DISCLOSED SELECTION
===================
Symbols are ranked on month m-1 dollar volume (point-in-time) but are additionally required to
have a monthly bar IN month m, so that a delisted ticker is not requested. That is a lookahead
on *which names get measured*, not on any measured quantity, and it is declared here rather than
left implicit.

Transport, throttling, paging and the calendar/asset caches are IMPORTED from the T3 rig
(`scripts/t3_pressure_reversal.py`), never reimplemented -- same rule the statistics follow.
"""

from __future__ import annotations

import gzip
import json
import math
import pathlib
import random
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.t3_pressure_reversal import (  # noqa: E402
    PAGE, THROTTLE, _ny_utc_offset, calendar, chunks, monthly_bars, paged,
)
from scripts.trading_bot.frozen import Refused  # noqa: E402

CACHE = ROOT / "research" / "data" / "m0_cache"
CACHE.mkdir(parents=True, exist_ok=True)

SEED = 20260817
N_DAYS = 40
PER_TIER = 15
MIN_PRICE = 3.0

# ADV-rank bands. A is mega-cap; F is the kind of name a cross-sectional screen reaches when it
# is asked for 3,000 stocks. The point of the ladder is that "the auction is free" is a claim
# about a mechanism, so it has to hold across the mechanism's whole domain or it is a claim
# about mega-caps only.
TIERS = (
    ("A_rank_1_50", 1, 50),
    ("B_rank_51_200", 51, 200),
    ("C_rank_201_500", 201, 500),
    ("D_rank_501_1500", 501, 1500),
    ("E_rank_1501_3000", 1501, 3000),
    ("F_rank_3001_6000", 3001, 6000),
)

OFFICIAL_CLOSE_CONDITIONS = {"6"}      # official closing print, primary listing venue
OFFICIAL_OPEN_CONDITIONS = {"O"}       # official opening print, primary listing venue


# ---------------------------------------------------------------------------
# universe
# ---------------------------------------------------------------------------

def build_tiers():
    """month 'YYYY-MM' -> {tier: [symbols]}, ranked on month m-1 raw dollar volume."""
    monthly = monthly_bars(None)          # cache hit; refuses to rebuild silently if absent
    if not monthly:
        raise Refused("monthly_bars cache is empty; run the T3 collection first")
    cal = calendar()
    days_in_month = defaultdict(int)
    for row in cal:
        days_in_month[row["date"][:7]] += 1

    present = defaultdict(set)            # month -> symbols with a bar that month
    by_month = defaultdict(list)          # month -> [(dollar_adv, symbol)]
    for sym, rows in monthly.items():
        for month, close, vol, vw in rows:
            present[month].add(sym)
            nd = days_in_month.get(month, 0)
            if nd == 0 or close is None or close <= MIN_PRICE or not vol:
                continue
            by_month[month].append(((vw or close) * vol / nd, sym))

    out = {}
    for month in sorted(by_month):
        nxt = _next_month(month)
        ranked = [s for _, s in sorted(by_month[month], reverse=True)]
        alive = present.get(nxt, set())
        ranked = [s for s in ranked if s in alive]     # disclosed selection, see docstring
        tiers = {}
        for name, lo, hi in TIERS:
            tiers[name] = ranked[lo - 1:hi]
        out[nxt] = tiers
    return out


def _next_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    m += 1
    if m == 13:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


def sample_days(n_days: int, seed: int):
    """`n_days` trading days, stratified so every calendar year is represented."""
    cal = [r["date"] for r in calendar() if "2016-01-04" <= r["date"] <= "2026-08-14"]
    by_year = defaultdict(list)
    for d in cal:
        by_year[d[:4]].append(d)
    rng = random.Random(seed)
    years = sorted(by_year)
    per_year = max(1, n_days // len(years))
    picked = []
    for y in years:
        picked.extend(rng.sample(by_year[y], min(per_year, len(by_year[y]))))
    rest = [d for d in cal if d not in set(picked)]
    while len(picked) < n_days and rest:
        picked.append(rest.pop(rng.randrange(len(rest))))
    return sorted(picked[:n_days]), cal


# ---------------------------------------------------------------------------
# per-day collection
# ---------------------------------------------------------------------------

def _official(prints, codes):
    """The official print: the largest-size record carrying an official condition code."""
    cands = [p for p in (prints or []) if p.get("c") in codes and p.get("p")]
    if not cands:
        return None
    return max(cands, key=lambda p: p.get("s", 0))


def fetch_auctions(symbols, day, next_day):
    """{symbol: {day: {'close': rec, 'open': rec, 'n_close_prints': k}}} for two dates."""
    out = defaultdict(dict)
    for chunk in chunks(symbols, 40):
        for block in paged("/v2/stocks/auctions",
                           {"symbols": ",".join(chunk), "start": day, "end": next_day,
                            "limit": PAGE, "feed": "sip"}, "auctions"):
            for sym, days in block.items():
                for d in days:
                    out[sym][d["d"]] = {
                        "close": _official(d.get("c"), OFFICIAL_CLOSE_CONDITIONS),
                        "open": _official(d.get("o"), OFFICIAL_OPEN_CONDITIONS),
                        "n_close_records": len(d.get("c") or []),
                        "n_open_records": len(d.get("o") or []),
                    }
    return out


def fetch_minute(symbols, day, hhmm):
    """The single 1-minute RAW bar starting at `hhmm` ET -> {symbol: bar}."""
    off = _ny_utc_offset(day)
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    total = (h + off) * 60 + m
    start = f"{day}T{total // 60:02d}:{total % 60:02d}:00Z"
    end = f"{day}T{(total + 1) // 60:02d}:{(total + 1) % 60:02d}:00Z"
    out = {}
    for chunk in chunks(symbols, 200):
        for block in paged("/v2/stocks/bars",
                           {"symbols": ",".join(chunk), "timeframe": "1Min",
                            "start": start, "end": end, "limit": PAGE,
                            "feed": "sip", "adjustment": "raw"}, "bars"):
            for sym, bars in block.items():
                if bars:
                    out[sym] = bars[0]
    return out


def _quote_ok(q):
    bid, ask = q.get("bp"), q.get("ap")
    if not bid or not ask or ask <= bid:
        return False
    return (ask - bid) / (0.5 * (bid + ask)) < 0.10      # a 10% NBBO is a crossed/stale book


def fetch_quotes(symbols, day, start_utc, end_utc):
    """{symbol: [quote, ...]} NBBO records inside the window, chronological."""
    out = defaultdict(list)
    for chunk in chunks(symbols, 60):
        for block in paged("/v2/stocks/quotes",
                           {"symbols": ",".join(chunk), "start": f"{day}T{start_utc}Z",
                            "end": f"{day}T{end_utc}Z", "limit": PAGE, "feed": "sip"},
                          "quotes"):
            for sym, quotes in block.items():
                out[sym].extend(q for q in quotes if _quote_ok(q))
    for sym in out:
        out[sym].sort(key=lambda q: q["t"])
    return out


def _hh(day, h, m, s="00"):
    off = _ny_utc_offset(day)
    return f"{h + off:02d}:{m:02d}:{s}"


def collect_day(day, next_day, symbols_by_tier):
    symbols = sorted({s for v in symbols_by_tier.values() for s in v})
    auct = fetch_auctions(symbols, day, next_day)
    bar_close = fetch_minute(symbols, day, "15:59")
    bar_pre = fetch_minute(symbols, day, "15:49")
    bar_open = fetch_minute(symbols, day, "09:30")

    # Closing NBBO: the last second before 16:00. Names with no quote in that second are
    # re-requested over the last five minutes -- they are illiquid by construction, so the
    # wider window is cheap, and dropping them instead would bias the sample toward names
    # that quote continuously (which is exactly the population the claim is doubtful for).
    qc = fetch_quotes(symbols, day, _hh(day, 15, 59, "59"), _hh(day, 16, 0))
    missing = [s for s in symbols if not qc.get(s)]
    if missing:
        wide = fetch_quotes(missing, day, _hh(day, 15, 55), _hh(day, 16, 0))
        for s, v in wide.items():
            qc[s] = v

    # Opening NBBO: 09:29:59 -> 09:30:06, split at the symbol's own print timestamp.
    qo = fetch_quotes(symbols, day, _hh(day, 9, 29, "59"), _hh(day, 9, 30, "06"))
    missing_o = [s for s in symbols if not qo.get(s)]
    if missing_o:
        wide = fetch_quotes(missing_o, day, _hh(day, 9, 29), _hh(day, 9, 31))
        for s, v in wide.items():
            qo[s] = v

    tier_of = {s: t for t, syms in symbols_by_tier.items() for s in syms}
    rows = []
    for sym in symbols:
        a = auct.get(sym, {}).get(day, {})
        nxt = auct.get(sym, {}).get(next_day, {})
        c_print, o_print = a.get("close"), a.get("open")
        rec = {
            "d": day, "sym": sym, "tier": tier_of[sym],
            "has_close_print": bool(c_print), "has_open_print": bool(o_print),
            "n_close_records": a.get("n_close_records", 0),
            "n_open_records": a.get("n_open_records", 0),
            "in_auction_response": sym in auct,
        }
        bc, bo = bar_close.get(sym), bar_open.get(sym)
        rec["bar_1559"] = None if not bc else {"vw": bc.get("vw"), "v": bc.get("v"),
                                               "c": bc.get("c"), "n": bc.get("n")}
        rec["bar_0930"] = None if not bo else {"vw": bo.get("vw"), "v": bo.get("v"),
                                               "c": bo.get("c"), "n": bo.get("n")}
        bp_ = bar_pre.get(sym)
        rec["bar_1549"] = None if not bp_ else {"c": bp_.get("c")}
        if c_print:
            rec["close_print"] = {"p": c_print["p"], "s": c_print.get("s"),
                                  "x": c_print.get("x"), "t": c_print.get("t")}
            q = qc.get(sym) or []
            if q:
                last = q[-1]
                rec["nbbo_close"] = {"bp": last["bp"], "ap": last["ap"], "t": last["t"]}
        if o_print:
            rec["open_print"] = {"p": o_print["p"], "s": o_print.get("s"),
                                 "x": o_print.get("x"), "t": o_print.get("t")}
            q = qo.get(sym) or []
            pre = [x for x in q if x["t"] < f"{day}T{_hh(day, 9, 30)}Z"]
            post = [x for x in q if x["t"] > o_print["t"]]
            if pre:
                rec["nbbo_preopen"] = {"bp": pre[-1]["bp"], "ap": pre[-1]["ap"],
                                       "t": pre[-1]["t"]}
            if post:
                rec["nbbo_postopen"] = {"bp": post[0]["bp"], "ap": post[0]["ap"],
                                        "t": post[0]["t"]}
        nxt_open = (nxt or {}).get("open")
        if nxt_open:
            rec["next_open_print"] = {"p": nxt_open["p"], "d": next_day}
        rows.append(rec)
    return rows


def collect(n_days=N_DAYS, seed=SEED):
    days, cal = sample_days(n_days, seed)
    tiers_by_month = build_tiers()
    rng = random.Random(seed ^ 0x5f5f)
    nxt_of = {d: cal[i + 1] for i, d in enumerate(cal[:-1])}

    jobs = []
    for day in days:
        month_tiers = tiers_by_month.get(day[:7])
        if not month_tiers or day not in nxt_of:
            continue
        picked = {}
        for name, _lo, _hi in TIERS:
            pool = month_tiers.get(name) or []
            if not pool:
                continue
            picked[name] = rng.sample(pool, min(PER_TIER, len(pool)))
        jobs.append((day, nxt_of[day], picked))

    out = []
    done = [0]

    def work(job):
        day, nxt, picked = job
        try:
            rows = collect_day(day, nxt, picked)
        except Refused as exc:
            print(f"  {day} REFUSED: {exc}", flush=True)
            return []
        done[0] += 1
        print(f"  {day}: {len(rows)} rows  ({done[0]}/{len(jobs)}, "
              f"throttle {THROTTLE.interval:.2f}s, {THROTTLE.hits} 429s)", flush=True)
        return rows

    with ThreadPoolExecutor(max_workers=4) as pool:
        for rows in pool.map(work, jobs):
            out.extend(rows)

    payload = {"seed": seed, "n_days_requested": n_days, "days": days,
               "per_tier": PER_TIER, "tiers": [t[0] for t in TIERS], "rows": out}
    with gzip.open(CACHE / "records.json.gz", "wt") as fh:
        json.dump(payload, fh)
    print(f"wrote {len(out)} symbol-days to {CACHE / 'records.json.gz'}")
    return payload


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------

def _pct(values, q):
    if not values:
        return None
    v = sorted(values)
    i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
    return v[i]


def _dist(values, label):
    if not values:
        return {"label": label, "n": 0}
    return {"label": label, "n": len(values),
            "mean": statistics.fmean(values),
            "median": _pct(values, 0.5),
            "p05": _pct(values, 0.05), "p25": _pct(values, 0.25),
            "p75": _pct(values, 0.75), "p95": _pct(values, 0.95),
            "sd": statistics.pstdev(values) if len(values) > 1 else 0.0}


def _t_stat(values):
    if len(values) < 2:
        return None
    m = statistics.fmean(values)
    sd = statistics.pstdev(values) * math.sqrt(len(values) / (len(values) - 1))
    if sd == 0:
        return None
    return m / (sd / math.sqrt(len(values)))


def analyse(payload):
    # Early closes are excluded, the same exclusion T3 and T7 applied. On a 13:00 close the
    # auction print still exists but the 15:59 reference windows sit AFTER it, so every
    # comparison on those days would be measuring a stale post-close quote against the print.
    cal = {r["date"]: r for r in calendar()}
    early = {d for d in payload["days"] if cal.get(d, {}).get("close", "16:00") != "16:00"}
    rows = [r for r in payload["rows"] if r["d"] not in early]
    payload = dict(payload, excluded_early_close_days=sorted(early),
                   excluded_rows=len(payload["rows"]) - len(rows))
    per_tier = defaultdict(lambda: defaultdict(list))
    counts = defaultdict(lambda: defaultdict(int))
    pairs = defaultdict(list)          # tier -> [(dev_close_bp, overnight_bp)]
    triples = []                       # (r10_bp, dev_close_bp, overnight_bp) -- diagnostic D3

    for r in rows:
        t = r["tier"]
        counts[t]["symbol_days"] += 1
        counts[t]["close_print"] += int(r["has_close_print"])
        counts[t]["open_print"] += int(r["has_open_print"])
        counts[t]["both_prints"] += int(r["has_close_print"] and r["has_open_print"])

        cp, nb = r.get("close_print"), r.get("nbbo_close")
        if cp and nb:
            mid = 0.5 * (nb["bp"] + nb["ap"])
            half = (nb["ap"] - nb["bp"]) / (2 * mid) * 1e4
            dev = (cp["p"] - mid) / mid * 1e4
            if abs(dev) < 5000:
                per_tier[t]["close_dev_signed_bp"].append(dev)
                per_tier[t]["close_dev_abs_bp"].append(abs(dev))
                per_tier[t]["close_half_spread_bp"].append(half)
                if half > 0:
                    per_tier[t]["close_dev_over_half"].append(abs(dev) / half)
                nxo = r.get("next_open_print")
                if nxo and nxo["p"] and cp["p"]:
                    on = (nxo["p"] - cp["p"]) / cp["p"] * 1e4
                    if abs(on) < 2000:
                        pairs[t].append((dev, on))
                        pre = (r.get("bar_1549") or {}).get("c")
                        last = (r.get("bar_1559") or {}).get("c")
                        if pre and last:
                            r10 = (last - pre) / pre * 1e4
                            if abs(r10) < 2000:
                                triples.append((r10, dev, on))
        # The T3 entry price is the 15:59 minute-bar LAST TRADE, charged one half-spread. These
        # two series check that charge directly: where does the last trade sit relative to the
        # closing mid, and how far is the print from the price the backtest entered at?
        last_trade = (r.get("bar_1559") or {}).get("c")
        if last_trade and nb:
            mid = 0.5 * (nb["bp"] + nb["ap"])
            half = (nb["ap"] - nb["bp"]) / (2 * mid) * 1e4
            d_lt = (last_trade - mid) / mid * 1e4
            if abs(d_lt) < 5000:
                per_tier[t]["last_trade_vs_mid_abs_bp"].append(abs(d_lt))
                if half > 0:
                    per_tier[t]["last_trade_vs_mid_over_half"].append(abs(d_lt) / half)
            if cp:
                d_pl = (cp["p"] - last_trade) / last_trade * 1e4
                if abs(d_pl) < 5000:
                    per_tier[t]["print_vs_last_trade_signed_bp"].append(d_pl)
                    per_tier[t]["print_vs_last_trade_abs_bp"].append(abs(d_pl))
        if cp and r.get("bar_1559", {}) and (r.get("bar_1559") or {}).get("vw"):
            vw = r["bar_1559"]["vw"]
            per_tier[t]["close_vs_minute_vwap_bp"].append((cp["p"] - vw) / vw * 1e4)
            per_tier[t]["close_vs_minute_vwap_abs_bp"].append(abs((cp["p"] - vw) / vw * 1e4))
        if cp and cp.get("s"):
            per_tier[t]["close_auction_notional_usd"].append(cp["s"] * cp["p"])
            v = (r.get("bar_1559") or {}).get("v")
            if v:
                per_tier[t]["close_auction_over_last_minute"].append(cp["s"] / v)

        op, nbo = r.get("open_print"), r.get("nbbo_postopen")
        if op and nbo:
            mid = 0.5 * (nbo["bp"] + nbo["ap"])
            half = (nbo["ap"] - nbo["bp"]) / (2 * mid) * 1e4
            dev = (op["p"] - mid) / mid * 1e4
            if abs(dev) < 5000:
                per_tier[t]["open_dev_signed_bp"].append(dev)
                per_tier[t]["open_dev_abs_bp"].append(abs(dev))
                per_tier[t]["open_half_spread_bp"].append(half)
        if op and (r.get("bar_0930") or {}).get("vw"):
            vw = r["bar_0930"]["vw"]
            per_tier[t]["open_vs_minute_vwap_bp"].append((op["p"] - vw) / vw * 1e4)
            per_tier[t]["open_vs_minute_vwap_abs_bp"].append(abs((op["p"] - vw) / vw * 1e4))
        if op and r.get("nbbo_preopen"):
            nbp = r["nbbo_preopen"]
            mid = 0.5 * (nbp["bp"] + nbp["ap"])
            dev = (op["p"] - mid) / mid * 1e4
            if abs(dev) < 5000:
                per_tier[t]["open_dev_vs_preopen_mid_bp"].append(dev)
                per_tier[t]["open_dev_vs_preopen_mid_abs_bp"].append(abs(dev))
        if op and op.get("s"):
            per_tier[t]["open_auction_notional_usd"].append(op["s"] * op["p"])

    report = {"tiers": {}, "all": {}}
    for t in sorted(counts):
        n = counts[t]["symbol_days"]
        report["tiers"][t] = {
            "symbol_days": n,
            "close_print_rate": counts[t]["close_print"] / n if n else None,
            "open_print_rate": counts[t]["open_print"] / n if n else None,
            "both_print_rate": counts[t]["both_prints"] / n if n else None,
            "dists": {k: _dist(v, k) for k, v in per_tier[t].items()},
        }
        pr = pairs[t]
        if len(pr) > 30:
            report["tiers"][t]["reversion"] = _reversion(pr)

    pooled = defaultdict(list)
    for t in per_tier:
        for k, v in per_tier[t].items():
            pooled[k].extend(v)
    all_pairs = [p for t in pairs for p in pairs[t]]
    report["all"] = {
        "symbol_days": sum(counts[t]["symbol_days"] for t in counts),
        "close_print_rate": (sum(counts[t]["close_print"] for t in counts)
                             / max(1, sum(counts[t]["symbol_days"] for t in counts))),
        "open_print_rate": (sum(counts[t]["open_print"] for t in counts)
                            / max(1, sum(counts[t]["symbol_days"] for t in counts))),
        "dists": {k: _dist(v, k) for k, v in pooled.items()},
        "reversion": _reversion(all_pairs) if len(all_pairs) > 30 else None,
    }
    for k, v in pooled.items():
        if k.endswith("_signed_bp"):
            report["all"]["dists"][k]["t_stat"] = _t_stat(v)
    if len(triples) > 100:
        report["D3_pressure_diagnostic"] = _pressure_diagnostic(triples)
    report["placement"] = _placement(rows)
    report["excluded_early_close_days"] = payload["excluded_early_close_days"]
    report["excluded_rows"] = payload["excluded_rows"]
    report["non_fill_provision_bp"] = _provision(report)
    return report


def _placement(rows):
    """Where does the closing print sit inside the closing NBBO? The single most direct test of
    'the auction is the midpoint and it is free'."""
    out = defaultdict(lambda: defaultdict(int))
    for r in rows:
        cp, nb = r.get("close_print"), r.get("nbbo_close")
        if not (cp and nb):
            continue
        b, a, x = nb["bp"], nb["ap"], cp["p"]
        mid = 0.5 * (b + a)
        if x < b:
            k = "below_bid"
        elif x > a:
            k = "above_ask"
        elif abs(x - b) < 1e-9:
            k = "at_bid"
        elif abs(x - a) < 1e-9:
            k = "at_ask"
        elif abs(x - mid) < 1e-9:
            k = "at_mid"
        else:
            k = "inside_not_mid"
        out[r["tier"]][k] += 1
        out["ALL"][k] += 1
    return {t: {"n": sum(c.values()),
                **{k: v / sum(c.values()) for k, v in c.items()}}
            for t, c in out.items()}


def _provision(report):
    """Expected cost of an MOC that has no auction to clear in: P(no official close print) x a
    full quoted spread to unwind by hand. A FLOOR -- it excludes the overnight gap risk of
    carrying an unintended position, which is not priced here."""
    out = {}
    for t, v in report["tiers"].items():
        half = (v["dists"].get("close_half_spread_bp") or {}).get("median")
        rate = v.get("close_print_rate")
        if half is None or rate is None:
            continue
        out[t] = {"p_no_print": 1 - rate, "median_half_spread_bp": half,
                  "provision_bp": (1 - rate) * 2 * half}
    return out


def _ols(y, X):
    """Least squares with an intercept, by normal equations. Returns coefs and t-stats."""
    n, k = len(y), len(X[0]) + 1
    A = [[1.0] + list(row) for row in X]
    XtX = [[sum(A[i][a] * A[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    Xty = [sum(A[i][a] * y[i] for i in range(n)) for a in range(k)]
    # Gauss-Jordan inverse; k is 2 or 3 so this is exact enough and needs no dependency.
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(k)] for i, row in enumerate(XtX)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        M[c] = [v / pv for v in M[c]]
        for r in range(k):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    inv = [row[k:] for row in M]
    beta = [sum(inv[a][b] * Xty[b] for b in range(k)) for a in range(k)]
    resid = [y[i] - sum(beta[a] * A[i][a] for a in range(k)) for i in range(n)]
    s2 = sum(r * r for r in resid) / max(1, n - k)
    se = [math.sqrt(max(0.0, s2 * inv[a][a])) for a in range(k)]
    return {"n": n, "beta": beta, "se": se,
            "t": [(beta[a] / se[a]) if se[a] else None for a in range(k)]}


def _pressure_diagnostic(triples):
    """EXPLORATORY, NOT PRE-REGISTERED. Does the closing print's deviation from the closing
    NBBO midpoint carry the same information the T3 pressure-reversal signal trades on?

    T3's fade-buy leg buys the names that FELL in the last ten minutes and marks the position
    out at the next opening print. A name that has been sold into the close has a closing print
    that sits nearer the BID, i.e. a NEGATIVE deviation from the mid; if that deviation is a
    transient auction dislocation rather than a price, it unwinds by the open and shows up as a
    positive overnight return that has nothing to do with any predictable reversal.

    Three regressions, all in bp:
      P1  dev  ~ r10                 -- does the print lean the way the last ten minutes leaned?
      P2  overnight ~ r10            -- the raw pressure-reversal effect, unconditional
      P3  overnight ~ r10 + dev      -- does dev absorb r10's coefficient?
    If P3 leaves r10 with a coefficient indistinguishable from zero while dev keeps a strongly
    negative one, the effect is the auction print reverting, not a reversal of the move.
    """
    r10 = [t[0] for t in triples]
    dev = [t[1] for t in triples]
    on = [t[2] for t in triples]
    q = sorted(range(len(r10)), key=lambda i: r10[i])
    nq = 5
    buckets = []
    for b in range(nq):
        idx = q[b * len(q) // nq:(b + 1) * len(q) // nq]
        buckets.append({
            "quintile": b + 1, "n": len(idx),
            "mean_r10_bp": statistics.fmean(r10[i] for i in idx),
            "mean_dev_bp": statistics.fmean(dev[i] for i in idx),
            "mean_overnight_bp": statistics.fmean(on[i] for i in idx),
        })
    return {
        "n": len(triples),
        "P1_dev_on_r10": _ols(dev, [[x] for x in r10]),
        "P2_overnight_on_r10": _ols(on, [[x] for x in r10]),
        "P3_overnight_on_r10_and_dev": _ols(on, [[a, b] for a, b in zip(r10, dev)]),
        "quintiles_by_r10": buckets,
        "note": "coefficient order is [intercept, r10, dev]; EXPLORATORY, not pre-registered",
    }


def _reversion(pairs):
    """Does the print's deviation from the closing mid revert by the next opening print?

    Regression of the overnight return (close print -> next open print, bp) on the deviation
    (print - closing mid, bp). A slope of -1 means the whole dislocation unwinds and the auction
    price was pure noise around the mid; a slope of 0 means the print WAS the fair price and the
    deviation is information, not cost.
    """
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return None
    slope = sxy / sxx
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    s2 = sum(r * r for r in resid) / max(1, n - 2)
    se = math.sqrt(s2 / sxx) if sxx > 0 else None
    syy = sum((y - my) ** 2 for y in ys)
    return {"n": n, "slope": slope, "se": se,
            "t": (slope / se) if se else None,
            "intercept_bp": intercept,
            "r2": (sxy * sxy / (sxx * syy)) if syy > 0 else None,
            "implied_reverted_bp_per_1bp_dev": -slope,
            "mean_abs_dev_bp": statistics.fmean(abs(x) for x in xs),
            "expected_cost_bp_if_direction_random": None}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if cmd == "collect":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else N_DAYS
        collect(n)
    elif cmd == "report":
        with gzip.open(CACHE / "records.json.gz", "rt") as fh:
            payload = json.load(fh)
        rep = analyse(payload)
        rep["provenance"] = {"seed": payload["seed"], "days": payload["days"],
                             "per_tier": payload["per_tier"],
                             "rows": len(payload["rows"])}
        out = ROOT / "research" / "trading_bot" / "M0_AUCTION_FILLS.json"
        out.write_text(json.dumps(rep, indent=2))
        print(json.dumps(rep["all"], indent=2)[:4000])
        print(f"wrote {out}")
    else:
        raise SystemExit(f"unknown command {cmd!r}")
