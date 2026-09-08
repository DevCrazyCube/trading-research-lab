#!/usr/bin/env python3
"""T3 -- collection + test rig for shortlist candidate #1: end-of-day pressure reversal,
held overnight on the auction rail.

Frozen rule: research/trading_bot/T3_PREREGISTRATION.md
             sha256 401fd377ce1a6e3d60d618a86c36a7834bdafe81c0240e11540b9c038fe4f29f

This script COLLECTS and EVALUATES. Every parameter it can vary is one of the eight declared in
the pre-registration grid; nothing else is reachable from the CLI.

Statistics are imported from the T2 harness (scripts/trading_bot/stats.py), never reimplemented:
`deflated_sharpe`, `sharpe_variance_from_trials`, `permutation_test`, `moments`,
`annualised_sharpe`, `max_drawdown`, `cagr`. The label permutation described in the
pre-registration is cross-sectional and has no equivalent in the T2 module, so it lives here and
its construction is spelled out at the definition.
"""

from __future__ import annotations

import gzip
import json
import math
import pathlib
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.trading_bot.data import load_env_credentials, assert_data_host  # noqa: E402
from scripts.trading_bot.frozen import ALPACA_DATA_HOST, Refused  # noqa: E402

CACHE = ROOT / "research" / "data" / "t3_cache"
CACHE.mkdir(parents=True, exist_ok=True)

TRADING_HOST = "https://paper-api.alpaca.markets"   # read-only endpoints only (assets, calendar)
PAGE = 10_000
EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}

import re  # noqa: E402
_TICKER = re.compile(r"[A-Z]{1,5}(\.[A-Z]{1,2})?")
_DROPPED_SYMBOLS: set = set()

START = "2016-01-04"
END = "2026-08-14"
DESIGN_END = "2021-12-31"
TEST_START = "2022-01-03"

KEY, SECRET = load_env_credentials()
HEADERS = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET, "Accept": "application/json"}


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------

class _Throttle:
    """One global token bucket, adaptive on 429.

    A 429 is not a transient network blip: it means the whole process is going too fast, so the
    correction has to be global, not per-request. The interval widens on every 429 and decays
    back slowly, so a burst of rate limits does not permanently halve throughput.
    """

    def __init__(self, interval: float = 0.12):
        import threading
        self.lock = threading.Lock()
        self.floor = interval
        self.interval = interval
        self.next_at = 0.0
        self.hits = 0
        self.calls = 0

    def wait(self):
        while True:
            with self.lock:
                now = time.monotonic()
                if now >= self.next_at:
                    self.next_at = max(now, self.next_at) + self.interval
                    self.calls += 1
                    self.interval = max(self.floor, self.interval * 0.99)
                    return
                sleep_for = self.next_at - now
            time.sleep(sleep_for)

    def penalise(self):
        with self.lock:
            self.hits += 1
            self.interval = min(0.6, self.interval * 1.3 + 0.01)
            self.next_at = time.monotonic() + self.interval * 2


THROTTLE = _Throttle()


def _get(host: str, path: str, params: dict, tries: int = 12) -> dict:
    url = f"{host}{path}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(tries):
        THROTTLE.wait()
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            last = f"HTTP {exc.code}: {body}"
            if exc.code == 429:
                THROTTLE.penalise()
                continue
            if exc.code in (500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise Refused(f"{path}: {last}")
        except Exception as exc:                                    # noqa: BLE001
            last = repr(exc)
            time.sleep(1.5 * (attempt + 1))
    raise Refused(f"{path} failed after {tries} attempts: {last}")


def data_get(path: str, params: dict) -> dict:
    return _get(assert_data_host(ALPACA_DATA_HOST), path, params)


def paged(path: str, params: dict, key: str):
    """Every page. A truncated response is a wrong answer, not a small one (B22B rule)."""
    token, pages = None, 0
    params = dict(params)
    while True:
        p = dict(params)
        if token:
            p["page_token"] = token
        try:
            payload = data_get(path, p)
        except Refused as exc:
            # One bad ticker must not blind a whole chunk. Drop exactly the named symbol and
            # retry; anything else is a real refusal and propagates.
            m = re.search(r"invalid symbol: ([^\"\\}]+)", str(exc))
            if m and "symbols" in params:
                bad = m.group(1).strip()
                kept = [s for s in params["symbols"].split(",") if s != bad]
                if len(kept) < len(params["symbols"].split(",")) and kept:
                    params["symbols"] = ",".join(kept)
                    _DROPPED_SYMBOLS.add(bad)
                    continue
            raise
        block = payload.get(key)
        if block is None:
            raise Refused(f"{path}: response has no {key!r} key; that is not zero rows")
        yield block
        token = payload.get("next_page_token")
        pages += 1
        if not token:
            return
        if pages > 20_000:
            raise Refused("paging did not terminate")


def chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


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
# 1. calendar and asset pool
# ---------------------------------------------------------------------------

def calendar():
    def build():
        # Starts one month BEFORE START: the universe screen for January 2016 is computed from
        # December 2015, and a month with no calendar entry has no trading-day count to divide
        # a month's dollar volume by -- which silently emptied the first month of the sample.
        rows = _get(TRADING_HOST, "/v2/calendar", {"start": "2015-12-01", "end": END})
        return [{"date": r["date"], "open": r["open"], "close": r["close"]} for r in rows]
    return cache_json("calendar", build)


def asset_pool():
    def build():
        out = {}
        for status in ("active", "inactive"):
            rows = _get(TRADING_HOST, "/v2/assets",
                        {"status": status, "asset_class": "us_equity"})
            for a in rows:
                # Alpaca's asset list contains CUSIP-shaped placeholders ("0029900E0") that the
                # data API rejects outright. A ticker is letters, with at most one dotted class
                # suffix; anything else is dropped here rather than 400-ing a whole chunk.
                if not _TICKER.fullmatch(a["symbol"]):
                    continue
                if a.get("exchange") in EXCHANGES:
                    out[a["symbol"]] = {"exchange": a["exchange"], "status": status,
                                        "shortable": a.get("shortable", False)}
        return out
    return cache_json("asset_pool", build)


# ---------------------------------------------------------------------------
# 2. universe: monthly RAW bars -> point-in-time screen
# ---------------------------------------------------------------------------

def monthly_bars(symbols):
    """RAW monthly bars for the whole pool. Levels must be point-in-time (data.py docstring)."""
    def build():
        out = defaultdict(list)
        todo = list(chunks(list(symbols), 200))
        done = [0]

        def work(job):
            i, chunk = job
            local = defaultdict(list)
            for block in paged("/v2/stocks/bars",
                               {"symbols": ",".join(chunk), "timeframe": "1Month",
                                "start": "2015-12-01", "end": END, "limit": PAGE,
                                "feed": "sip", "adjustment": "raw"}, "bars"):
                for sym, bars in block.items():
                    for b in bars:
                        local[sym].append([b["t"][:7], b["c"], b["v"], b.get("vw") or b["c"]])
            done[0] += 1
            print(f"    monthly chunk {done[0]}/{len(todo)} "
                  f"(throttle {THROTTLE.interval:.2f}s, {THROTTLE.hits} 429s)", flush=True)
            return local

        with ThreadPoolExecutor(max_workers=8) as pool:
            for local in pool.map(work, list(enumerate(todo))):
                for sym, rows in local.items():
                    out[sym].extend(rows)
        return {k: v for k, v in out.items()}
    return cache_json("monthly_bars", build)


def build_universe(top_n: int):
    """month 'YYYY-MM' -> ordered list of symbols eligible to TRADE in that month.

    Screen inputs are month m-1's raw close and dollar ADV; the set trades in month m. No value
    from month m or later touches the selection.
    """
    pool = asset_pool()
    monthly = monthly_bars(sorted(pool))
    cal = calendar()
    days_in_month = defaultdict(int)
    for row in cal:
        days_in_month[row["date"][:7]] += 1

    by_month = defaultdict(list)                       # month -> [(adv, symbol)]
    for sym, rows in monthly.items():
        for month, close, vol, vw in rows:
            nd = days_in_month.get(month, 0)
            if nd == 0 or close is None or close <= 5.0:
                continue
            adv = (vw * vol) / nd
            if adv <= 20e6:
                continue
            by_month[month].append((adv, sym))

    months = sorted(by_month)
    universe = {}
    for i, month in enumerate(months):
        nxt = _next_month(month)
        ranked = sorted(by_month[month], reverse=True)[:top_n]
        universe[nxt] = [s for _, s in ranked]
    return universe


def _next_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    m += 1
    if m == 13:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


# ---------------------------------------------------------------------------
# 3. auctions, corporate actions, minute bars
# ---------------------------------------------------------------------------

def auctions(symbols):
    """(symbol, date) -> {'o': official opening print, 'c': official closing print} (RAW prices).

    Official = condition code 'O' (open) / '6' (close); if several, the largest size wins.
    """
    def build():
        out = {}

        def work(chunk):
            local = {}
            for block in paged("/v2/stocks/auctions",
                               {"symbols": ",".join(chunk), "start": START, "end": END,
                                "limit": PAGE, "feed": "sip"}, "auctions"):
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
            for local in pool.map(work, list(chunks(symbols, 40))):
                out.update(local)
        return out
    return cache_json("auctions", build)


def corporate_action_dates(symbols):
    """symbol -> set of dates on which ANY corporate action lands (ex_date / process_date)."""
    def build():
        out = defaultdict(set)
        years = [(f"{y}-01-01", f"{y}-12-31") for y in range(2016, 2027)]

        def work(args):
            chunk, (s, e) = args
            local = defaultdict(set)
            for block in paged("/v1/corporate-actions",
                               {"symbols": ",".join(chunk), "start": s, "end": e,
                                "limit": 1000}, "corporate_actions"):
                for _kind, events in block.items():
                    for ev in events:
                        sym = ev.get("symbol") or ev.get("target_symbol") or \
                            ev.get("new_symbol") or ev.get("old_symbol")
                        if not sym:
                            continue
                        for field in ("ex_date", "process_date", "effective_date",
                                      "payable_date", "record_date"):
                            if ev.get(field):
                                local[sym].add(ev[field])
            return local

        jobs = [(c, yr) for c in chunks(symbols, 50) for yr in years]
        with ThreadPoolExecutor(max_workers=6) as pool:
            for local in pool.map(work, jobs):
                for sym, dates in local.items():
                    out[sym].update(dates)
        return {k: sorted(v) for k, v in out.items()}
    return cache_json("corporate_actions", build)


MINUTES_WANTED = ("15:29", "15:49", "15:59")


def minute_slice(day: str, symbols):
    """{symbol: {'15:29': c, '15:49': c, '15:59': c}} -- RAW SIP 1-minute closes.

    The 15:59 bar covers [15:59, 16:00) and therefore EXCLUDES the closing auction print. The
    entry decision cannot see the print it is meant to precede.
    """
    ny_offset = _ny_utc_offset(day)
    start = f"{day}T{15 - 0 + ny_offset:02d}:29:00Z"
    end = f"{day}T{16 + ny_offset:02d}:00:00Z"
    out = defaultdict(dict)
    for block in paged("/v2/stocks/bars",
                       {"symbols": ",".join(symbols), "timeframe": "1Min",
                        "start": start, "end": end, "limit": PAGE,
                        "feed": "sip", "adjustment": "raw"}, "bars"):
        for sym, bars in block.items():
            for b in bars:
                hhmm = b["t"][11:16]
                local = f"{int(hhmm[:2]) - ny_offset:02d}:{hhmm[3:5]}"
                if local in MINUTES_WANTED:
                    out[sym][local] = b["c"]
    return {k: v for k, v in out.items()}


def _ny_utc_offset(day: str) -> int:
    """UTC offset of America/New_York on `day`, as hours to ADD to local to get UTC (4 or 5)."""
    import datetime
    import zoneinfo
    d = datetime.date.fromisoformat(day)
    tz = zoneinfo.ZoneInfo("America/New_York")
    dt = datetime.datetime(d.year, d.month, d.day, 12, 0, tzinfo=tz)
    return -int(dt.utcoffset().total_seconds() // 3600)


def collect_minutes(universe_by_month, trading_days):
    """One cached file per calendar year, so a crash costs at most a year of pulls."""
    by_year = defaultdict(list)
    for day in trading_days:
        by_year[day[:4]].append(day)

    for year, days in sorted(by_year.items()):
        def build(days=days):
            res = {}

            def work(day):
                syms = universe_by_month.get(day[:7], [])
                if not syms:
                    return day, {}
                return day, minute_slice(day, syms)

            with ThreadPoolExecutor(max_workers=6) as pool:
                for day, rows in pool.map(work, days):
                    res[day] = rows
            return res
        # Yielded a year at a time and dropped after use: holding all 2,648 days of 500-symbol
        # minute slices at once is ~1 GB of Python dicts for no reason.
        yield year, cache_json(f"minutes_{year}", build)


# ---------------------------------------------------------------------------
# 4. panel assembly
# ---------------------------------------------------------------------------

def build_panel():
    """Per (day, symbol): the two signal returns and the realised overnight return.

    Every exclusion in pre-registration section 4 is applied here, once, identically for the
    design and the test period.
    """
    cal = calendar()
    full_days = [r["date"] for r in cal if r["close"] == "16:00"]
    all_days = [r["date"] for r in cal]
    close_by_day = {r["date"]: r["close"] for r in cal}
    nxt = {all_days[i]: all_days[i + 1] for i in range(len(all_days) - 1)}

    uni500 = build_universe(500)
    union = sorted({s for syms in uni500.values() for s in syms})
    print(f"universe union across all months: {len(union)} symbols", flush=True)

    auct = auctions(union)
    print(f"auction records: {len(auct)}", flush=True)
    ca = corporate_action_dates(union)
    ca = {k: set(v) for k, v in ca.items()}
    print(f"symbols with corporate actions: {len(ca)}", flush=True)

    panel = {}
    stats = defaultdict(int)
    for year, minutes in collect_minutes(uni500, [d for d in full_days if d >= START]):
      print(f"  minutes {year}: {len(minutes)} days", flush=True)
      for day in sorted(minutes):
        if day < START or day > END:
            continue
        nd = nxt.get(day)
        if nd is None or close_by_day.get(nd) != "16:00":
            stats["day_dropped_early_close_or_last"] += 1
            continue
        syms = uni500.get(day[:7], [])
        mins = minutes.get(day, {})
        rows = []
        for sym in syms:
            m = mins.get(sym)
            if not m or "15:59" not in m or "15:49" not in m or "15:29" not in m:
                stats["sym_dropped_missing_minute"] += 1
                continue
            key = f"{sym}|{nd}"
            a = auct.get(key)
            if not a or "o" not in a:
                stats["sym_dropped_missing_open_auction"] += 1
                continue
            if nd in ca.get(sym, ()):                       # corporate action on the exit date
                stats["sym_dropped_corporate_action"] += 1
                continue
            p59, p49, p29, po = m["15:59"], m["15:49"], m["15:29"], a["o"]
            if min(p59, p49, p29, po) <= 0:
                stats["sym_dropped_nonpositive_price"] += 1
                continue
            rows.append([sym, p59 / p49 - 1.0, p59 / p29 - 1.0, po / p59 - 1.0])
            stats["sym_kept"] += 1
        if len(rows) < 100:
            stats["day_dropped_thin"] += 1
            continue
        panel[day] = rows
        stats["day_kept"] += 1
    return panel, dict(stats), uni500


# ---------------------------------------------------------------------------
# 5. the strategy -- the eight declared configurations and nothing else
# ---------------------------------------------------------------------------

SIGNAL_WINDOWS = (10, 30)
CUTS = (0.10, 0.20)
UNIVERSES = (300, 500)


def run_config(panel, uni_by_month, *, window: int, cut: float, top_n: int,
               half_spread_bp: float, exit_spread_bp: float = 0.0,
               borrow_annual_bp: float = 30.0, day_filter=None):
    """One night per observation: 50% long the fade-buy decile, 50% short the fade-sell decile.

    Returns (dates, net_returns, gross_returns, control_returns, per-day membership).
    """
    idx = 1 if window == 10 else 2
    dates, net, gross, control, members, legs = [], [], [], [], [], []
    ordered_days = sorted(panel)
    for day in ordered_days:
        if day_filter and not day_filter(day):
            continue
        allowed = set(uni_by_month.get(day[:7], [])[:top_n])
        rows = [r for r in panel[day] if r[0] in allowed]
        if len(rows) < 100:
            continue
        rows.sort(key=lambda r: r[idx])
        k = max(1, int(len(rows) * cut))
        longs = rows[:k]                       # most negative last-window move -> fade by buying
        shorts = rows[-k:]                     # most positive -> fade by selling
        r_long = sum(r[3] for r in longs) / k
        r_short = sum(r[3] for r in shorts) / k
        g = 0.5 * r_long - 0.5 * r_short
        # entry crosses the spread on 100% of capital; exit is the single-price auction.
        cost = (half_spread_bp + exit_spread_bp) / 1e4
        # borrow accrues on the 50% short notional over the calendar days held.
        cost += 0.5 * (borrow_annual_bp / 1e4) * _calendar_gap(day, ordered_days) / 365.25
        dates.append(day)
        gross.append(g)
        net.append(g - cost)
        control.append(sum(r[3] for r in rows) / len(rows))
        members.append((day, [r[3] for r in rows], k))
        legs.append((r_long, r_short))
    return dates, net, gross, control, members, legs


_GAP_CACHE = {}


def _calendar_gap(day, all_days):
    """Calendar days between this night's entry and its exit -- 1 midweek, 3 over a weekend."""
    if not _GAP_CACHE:
        import datetime
        for i, d in enumerate(all_days[:-1]):
            a = datetime.date.fromisoformat(d)
            b = datetime.date.fromisoformat(all_days[i + 1])
            _GAP_CACHE[d] = max(1, (b - a).days)
    return _GAP_CACHE.get(day, 1)


# ---------------------------------------------------------------------------
# 6. the cross-sectional label permutation (pre-registration section 7)
# ---------------------------------------------------------------------------

def label_permutation_fast(members, *, trials: int = 10_000, seed: int = 20260816):
    """numpy version of `label_permutation`; identical null, identical statistic.

    Per night, draw 2k of that night's overnight returns without replacement and split them into
    a pseudo-long and a pseudo-short group. That is exactly what shuffling the labels and taking
    the first/last k does, and it costs 2k draws instead of a full shuffle.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    obs_terms, null = [], np.zeros(trials)
    for _day, overnight, k in members:
        arr = np.asarray(overnight, dtype=float)
        obs_terms.append(0.5 * arr[:k].mean() - 0.5 * arr[-k:].mean())
        n = arr.size
        # argpartition of uniform noise draws 2k distinct indices per trial in O(n), which is
        # the same null as a full shuffle at a fraction of the cost: which 2k are selected is
        # uniform, and the split into the two halves is independent of the returns.
        pick = np.argpartition(rng.random((trials, n)), 2 * k - 1, axis=1)[:, :2 * k]
        drawn = arr[pick]
        null += 0.5 * drawn[:, :k].mean(axis=1) - 0.5 * drawn[:, k:].mean(axis=1)
    null /= len(members)
    obs = float(np.mean(obs_terms))
    ge = int((null >= obs).sum())
    return {"observed_mean": obs, "trials": trials, "seed": seed,
            "p_right_tail": (ge + 1) / (trials + 1),
            "null_mean": float(null.mean()), "null_sd": float(null.std(ddof=1)),
            "null_p95": float(np.quantile(null, 0.95))}


def label_permutation(members, *, cut: float, trials: int = 10_000, seed: int = 20260816):
    """Shuffle WHICH stock gets which signal label, within each day.

    Every permutation trades the same nights, holds the same number of names long and short,
    and draws them from the same surviving cross-section. Only the assignment of the label to
    the stock changes -- so the null is precisely 'the last-window move carries no information',
    and nothing about market direction, drift or day selection is disturbed.

    Add-one corrected, per stats.permutation_test's convention.
    """
    observed = []
    for _day, overnight, k in members:
        # `members` rows are already sorted by signal, so the first/last k are the real deciles.
        observed.append(0.5 * (sum(overnight[:k]) / k) - 0.5 * (sum(overnight[-k:]) / k))
    obs = sum(observed) / len(observed)

    rng = random.Random(seed)
    ge = 0
    pools = [(list(o), k) for _d, o, k in members]
    for _ in range(trials):
        total = 0.0
        for overnight, k in pools:
            rng.shuffle(overnight)
            total += 0.5 * (sum(overnight[:k]) / k) - 0.5 * (sum(overnight[k:2 * k]) / k)
        if total / len(pools) >= obs:
            ge += 1
    return {"observed_mean": obs, "trials": trials, "seed": seed,
            "p_right_tail": (ge + 1) / (trials + 1)}


# ---------------------------------------------------------------------------
# 7. half-spread measurement (pre-registration section 5)
# ---------------------------------------------------------------------------

def measure_half_spread(panel, uni_by_month, period_days, *, n_days=40, seed=20260816):
    """Median (ask-bid)/(2*mid) from SIP quotes in the LAST SECOND before the close.

    DECLARED DEVIATION from pre-registration section 5, which named the window
    [15:59:00, 16:00:00). That minute is not payable: the quotes endpoint is symbol-major, so a
    truncated page set covers only the alphabetically-first symbols, and paging it in full is
    ~30,000 quotes per liquid symbol per minute -- hundreds of thousands of requests. The window
    is narrowed to [15:59:59, 16:00:00), which is (a) inside the pre-registered window, (b) the
    instant T1 section 5.1 actually specified for the entry ("~15:59:5x"), and (c) the
    CONSERVATIVE end of it, because quoted spreads widen into the close. The deviation and its
    direction are recorded in the result document rather than left in the code.
    """
    rng = random.Random(seed)
    days = sorted(period_days)
    sample = sorted(rng.sample(days, min(n_days, len(days))))

    def work(day):
        syms = uni_by_month.get(day[:7], [])
        off = _ny_utc_offset(day)
        start = f"{day}T{15 + off:02d}:59:59Z"
        end = f"{day}T{16 + off:02d}:00:00Z"
        out = []
        for chunk in chunks(syms, 100):
            per_sym = defaultdict(list)
            for block in paged("/v2/stocks/quotes",
                               {"symbols": ",".join(chunk), "start": start, "end": end,
                                "limit": PAGE, "feed": "sip"}, "quotes"):
                for sym, quotes in block.items():
                    for q in quotes:
                        bid, ask = q.get("bp"), q.get("ap")
                        if not bid or not ask or ask <= bid:
                            continue
                        mid = 0.5 * (bid + ask)
                        out_bp = (ask - bid) / (2 * mid) * 1e4
                        if out_bp < 1000:            # a 10% quoted spread is a crossed/stale book
                            per_sym[sym].append(out_bp)
            for sym, vals in per_sym.items():
                vals.sort()
                out.append(vals[len(vals) // 2])
        return out

    values = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for got in pool.map(work, sample):
            values.extend(got)
    values.sort()
    if not values:
        raise Refused("no quotes sampled; refusing to assume a spread")
    return {"median_half_spread_bp": values[len(values) // 2],
            "p25": values[len(values) // 4], "p75": values[3 * len(values) // 4],
            "p95": values[int(0.95 * (len(values) - 1))],
            "mean_half_spread_bp": sum(values) / len(values),
            "n_symbol_days": len(values), "sample_days": len(sample), "seed": seed,
            "window": "[15:59:59, 16:00:00) ET -- declared deviation, see docstring"}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "panel"
    if cmd == "panel":
        panel, stats, uni = build_panel()
        print(json.dumps(stats, indent=2))
        print("days in panel:", len(panel))
        with gzip.open(CACHE / "panel.json.gz", "wt") as fh:
            json.dump({"panel": panel, "stats": stats}, fh)
        print("panel written")
