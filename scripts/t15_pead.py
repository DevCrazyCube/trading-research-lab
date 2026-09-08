#!/usr/bin/env python3
"""T15 -- collection + POWER CENSUS for shortlist candidate #12: PEAD.

STEP 1 IS A CENSUS, NOT A BACKTEST (FINDINGS.md 5g, the T9 lesson).
====================================================================
This module contains, in its `census` path, NO arithmetic that divides one price of a
signal-sorted portfolio by another.  It counts events, it measures point-in-time data
availability lags, and it measures the DISPERSION of event-window returns and their
WITHIN-SEASON correlation.  Those are structural quantities: they do not depend on the SUE
sort and cannot be tuned into an effect.  The power number is therefore computed BEFORE any
signal exists, exactly as T9 did, and it can kill the candidate before a harness is written.

POINT-IN-TIME DISCIPLINE (guardrail 1)
======================================
Two dates, never confused:

  * `acceptanceDateTime` of an 8-K carrying item 2.02 -- the moment the earnings release hit
    EDGAR, to the second, in UTC.  Converted to ET and classified pre-open / intraday /
    post-close with no timing assumption.
  * `filed` on every XBRL fact -- the day that number first became public in structured form.
    A SUE may only use facts whose `filed` is STRICTLY BEFORE the entry decision.  Restated
    values are excluded by taking, for each (cik, period), the EARLIEST-filed fact and never a
    later revision.

The classic PEAD leakage is to compute the surprise from a database whose EPS was restated, or
to key the event to a later-known announcement date.  Both are structurally impossible here:
the panel is keyed on `filed`, and the announcement timestamp comes from the filing itself.

WHAT THIS SCRIPT DOES NOT DO
============================
No orders.  Read-only endpoints.  Free SEC + the Alpaca market-data host already used by T3.
"""

from __future__ import annotations

import gzip
import json
import math
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.trading_bot.data import load_env_credentials  # noqa: E402
from scripts.trading_bot.frozen import ALPACA_DATA_HOST, Refused  # noqa: E402

CACHE = ROOT / "research" / "data" / "t15_cache"
CACHE.mkdir(parents=True, exist_ok=True)
T3_CACHE = ROOT / "research" / "data" / "t3_cache"
OUT = ROOT / "research" / "trading_bot"

SEC_UA = "meme-research (contact officialjoy04@gmail.com)"
START = "2016-01-04"
END = "2026-08-14"
DESIGN_END = "2021-12-31"
TEST_START = "2022-01-03"
TOP_N = 500

PAGE = 10_000
KEY, SECRET = load_env_credentials()
ALPACA_HEADERS = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET,
                  "Accept": "application/json"}


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------

class _Throttle:
    """One global token bucket, LOCKED.

    An unsynchronised version of this class is what stalled the first collection run: six
    threads read the same `_next`, all slept to the same instant, all fired together, and the
    resulting bursts drew 403s whose back-off widened the interval until throughput collapsed
    to ~1 req/s.  The reservation must be atomic with the read, so the slot is claimed under a
    lock and only the sleeping happens outside it.
    """

    def __init__(self, interval: float):
        import threading
        self.base = interval
        self.interval = interval
        self._next = 0.0
        self._lock = threading.Lock()
        self.hits = 0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self.interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def penalise(self):
        with self._lock:
            self.hits += 1
            self.interval = min(self.interval * 1.3, 1.0)

    def relax(self):
        with self._lock:
            self.interval = max(self.base, self.interval * 0.98)


SEC_THROTTLE = _Throttle(0.13)      # SEC asks for <= 10 req/s; this is ~7.7/s
ALPACA_THROTTLE = _Throttle(0.12)


HTTP_ERRORS: dict = {}


def _fetch(url: str, headers: dict, throttle: _Throttle, tries: int = 8):
    last = None
    for attempt in range(tries):
        throttle.wait()
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
                enc = (r.headers.get("Content-Encoding") or "").lower()
            # urllib does NOT decompress. Asking for gzip and then calling .decode() on the
            # body is how the first collection run "hung": every response raised
            # UnicodeDecodeError, every request burned its eight retries, and the failure
            # looked exactly like rate limiting. Decompress on the declared encoding.
            if enc == "gzip":
                raw = gzip.decompress(raw)
            elif enc == "deflate":
                import zlib
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            throttle.relax()
            return json.loads(raw.decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 403, 503):
                throttle.penalise()
            HTTP_ERRORS[e.code] = HTTP_ERRORS.get(e.code, 0) + 1
            last = e
        except Exception as e:                                  # noqa: BLE001
            HTTP_ERRORS[type(e).__name__] = HTTP_ERRORS.get(type(e).__name__, 0) + 1
            last = e
        time.sleep(min(0.5 * (attempt + 1), 4))
    raise Refused(f"GET {url} failed after {tries} tries: {last!r}")


def sec_get(url: str):
    return _fetch(url, {"User-Agent": SEC_UA, "Accept-Encoding": "gzip, deflate"},
                  SEC_THROTTLE)


def cache_json(name: str, build):
    path = CACHE / f"{name}.json.gz"
    if path.exists():
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    print(f"  building {name} ...", flush=True)
    obj = build()
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as fh:
        json.dump(obj, fh)
    tmp.rename(path)
    return obj


def resumable(name: str, keys, work, *, workers: int = 6):
    """Fetch `keys` with `work`, appending each result to a JSONL log so a kill is cheap.

    Collection over thousands of SEC endpoints is minutes of network, and losing all of it
    to one interruption is how a cheap census becomes an expensive one.  The log is the
    cache; the caller re-runs and only the missing keys are fetched.
    """
    log = CACHE / f"{name}.jsonl"
    have = {}
    if log.exists():
        with log.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    k, v = json.loads(line)
                except Exception:                                 # noqa: BLE001
                    continue
                have[str(k)] = v
    todo = [k for k in keys if str(k) not in have]
    if todo:
        print(f"    {name}: {len(have)} cached, {len(todo)} to fetch", flush=True)
        done = [0]
        with log.open("a") as fh, ThreadPoolExecutor(max_workers=workers) as pool:
            for k, v in pool.map(lambda k: (k, work(k)), todo):
                have[str(k)] = v
                fh.write(json.dumps([k, v]) + "\n")
                done[0] += 1
                if done[0] % 50 == 0:
                    fh.flush()
                    print(f"      {name} {done[0]}/{len(todo)} "
                          f"(throttle {SEC_THROTTLE.interval:.2f}s, "
                          f"errors {HTTP_ERRORS})", flush=True)
    return have


def t3_cached(name: str):
    path = T3_CACHE / f"{name}.json.gz"
    if not path.exists():
        raise Refused(f"{path} absent; T3's collection must have run first")
    with gzip.open(path, "rt") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# 1. universe -- reused verbatim from T3, point-in-time, screened on RAW levels
# ---------------------------------------------------------------------------

def _next_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    m += 1
    if m == 13:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


def build_universe(top_n: int = TOP_N):
    monthly = t3_cached("monthly_bars")
    cal = t3_cached("calendar")
    days_in_month = defaultdict(int)
    for row in cal:
        days_in_month[row["date"][:7]] += 1
    by_month = defaultdict(list)
    for sym, rows in monthly.items():
        for month, close, vol, vw in rows:
            nd = days_in_month.get(month, 0)
            if nd == 0 or close is None or close <= 5.0:
                continue
            adv = (vw * vol) / nd
            if adv <= 20e6:
                continue
            by_month[month].append((adv, sym))
    universe = {}
    for month in sorted(by_month):
        ranked = sorted(by_month[month], reverse=True)[:top_n]
        universe[_next_month(month)] = [s for _, s in ranked]
    return universe


# ---------------------------------------------------------------------------
# 2. ticker -> CIK
# ---------------------------------------------------------------------------

_SUFFIX = re.compile(
    r"\b(COMMON STOCK|CLASS [A-Z]|COM|INC|CORP|CORPORATION|CO|LTD|LIMITED|PLC|LP|LLC|"
    r"HOLDINGS?|GROUP|THE|NEW|COMPANY|SA|NV|AG)\b")
_ETF = re.compile(
    r"\b(ETF|ETN|FUND|TRUST|INDEX|SHARES|PORTFOLIO|SPDR|ISHARES|VANGUARD|PROSHARES|"
    r"POWERSHARES|INVESCO|DIREXION|WISDOMTREE|VELOCITYSHARES|CURRENCYSHARES|NOTES|"
    r"SELECT SECTOR|MSCI|BARCLAYS|IPATH|ULTRA|BULL|BEAR)\b", re.I)


def _norm_name(s: str) -> str:
    s = re.sub(r"[^A-Z0-9 ]", " ", s.upper())
    return " ".join(_SUFFIX.sub(" ", s).split())


def company_tickers():
    def build():
        url = "https://www.sec.gov/files/company_tickers.json"
        return _fetch(url, {"User-Agent": SEC_UA}, SEC_THROTTLE)
    return cache_json("company_tickers", build)


def cik_lookup_names():
    """Every company NAME ever seen by EDGAR -> CIK.  Covers delisted issuers."""
    path = CACHE / "cik_lookup.txt.gz"
    if not path.exists():
        print("  downloading cik-lookup-data.txt (~40 MB) ...", flush=True)
        req = urllib.request.Request(
            "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt",
            headers={"User-Agent": SEC_UA})
        SEC_THROTTLE.wait()
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
        with gzip.open(path, "wb") as fh:
            fh.write(raw)
    out = {}
    with gzip.open(path, "rt", encoding="latin-1") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.rsplit(":", 2)
            if len(parts) < 2:
                continue
            key = _norm_name(parts[0])
            if key and key not in out:
                out[key] = int(parts[1])
    return out


def asset_names():
    path = ROOT / "research" / "data" / "t11_cache" / "asset_names.json.gz"
    if not path.exists():
        raise Refused(f"{path} absent; T11's /v2/assets dump is the name source")
    with gzip.open(path, "rt") as fh:
        return json.load(fh)


def symbol_to_cik(symbols):
    """Returns (mapping, diagnostics).  Ticker match first, issuer-name match second."""
    def build():
        ct = company_tickers()
        by_ticker = {v["ticker"].replace("-", "."): v["cik_str"] for v in ct.values()}
        names = asset_names()
        look = cik_lookup_names()
        mapping, how, unmapped = {}, {}, []
        for sym in sorted(symbols):
            if sym in by_ticker:
                mapping[sym] = by_ticker[sym]
                how[sym] = "ticker"
                continue
            nm = (names.get(sym) or "").strip()
            key = _norm_name(nm) if nm else ""
            if key and key in look:
                mapping[sym] = look[key]
                how[sym] = "name"
                continue
            unmapped.append(sym)
        etf_shaped = [s for s in unmapped if _ETF.search(names.get(s) or "")]
        nameless = [s for s in unmapped if not (names.get(s) or "").strip()]
        return {"cik": mapping, "how": how, "unmapped": unmapped,
                "unmapped_etf_shaped": etf_shaped, "unmapped_nameless": nameless}
    return cache_json("symbol_to_cik", build)


# ---------------------------------------------------------------------------
# 3. SEC filings: 8-K item 2.02 with acceptanceDateTime
# ---------------------------------------------------------------------------

def _submission_rows(cik: int):
    """All filings for a CIK, recent block + every archived block."""
    base = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    head = sec_get(base)
    if head is None:
        return None
    blocks = [head["filings"]["recent"]]
    for extra in head["filings"].get("files", []):
        more = sec_get(f"https://data.sec.gov/submissions/{extra['name']}")
        if more:
            blocks.append(more)
    return blocks


def earnings_8k(ciks):
    """cik -> [[filingDate, acceptanceDateTime, items, accession], ...] for item 2.02."""
    def work(cik):
        try:
            blocks = _submission_rows(cik)
        except Refused:
            return None
        if blocks is None:
            return None
        rows = []
        for b in blocks:
            items = b.get("items") or []
            n = len(b.get("form", []))
            for i in range(n):
                if b["form"][i] != "8-K":
                    continue
                it = items[i] if i < len(items) else ""
                if "2.02" not in it:
                    continue
                rows.append([b["filingDate"][i], b["acceptanceDateTime"][i], it,
                             b["accessionNumber"][i]])
        return rows

    have = resumable("earnings_8k", sorted(set(ciks)), work)
    out = {k: v for k, v in have.items() if v is not None}
    failed = [k for k, v in have.items() if v is None]
    return {"by_cik": out, "failed": failed}


# ---------------------------------------------------------------------------
# 4. SEC XBRL: EarningsPerShareDiluted, every fact with its `filed` date
# ---------------------------------------------------------------------------

def eps_facts(ciks, tag: str = "EarningsPerShareDiluted"):
    def work(cik):
        url = (f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/"
               f"us-gaap/{tag}.json")
        try:
            d = sec_get(url)
        except Refused:
            return None
        if d is None:
            return None
        rows = []
        for unit, facts in d.get("units", {}).items():
            if "shares" not in unit.lower():
                continue
            for f in facts:
                if not f.get("start") or not f.get("end"):
                    continue
                rows.append([f["start"], f["end"], f["val"], f["filed"],
                             f.get("form", ""), f.get("fy"), f.get("fp"),
                             f.get("frame", "")])
        return rows

    have = resumable(f"eps_{tag}", sorted(set(ciks)), work)
    out = {k: v for k, v in have.items() if v is not None}
    missing = [k for k, v in have.items() if v is None]
    return {"by_cik": out, "missing": missing}


# ---------------------------------------------------------------------------
# 5. prices: adjusted daily bars (total return) for the universe
# ---------------------------------------------------------------------------

def _alpaca_paged(path: str, params: dict, key: str):
    token = None
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        url = f"{ALPACA_DATA_HOST}{path}?" + urllib.parse.urlencode(q)
        d = _fetch(url, ALPACA_HEADERS, ALPACA_THROTTLE)
        yield d.get(key) or {}
        token = d.get("next_page_token")
        if not token:
            return


def daily_bars(symbols):
    """symbol -> [[date, close], ...], adjustment=all (total return; see data.py docstring)."""
    def build():
        out = defaultdict(list)
        syms = sorted(set(symbols))
        chunks = [syms[i:i + 150] for i in range(0, len(syms), 150)]
        done = [0]

        def work(chunk):
            local = defaultdict(list)
            for block in _alpaca_paged("/v2/stocks/bars",
                                       {"symbols": ",".join(chunk), "timeframe": "1Day",
                                        "start": "2015-10-01", "end": END, "limit": PAGE,
                                        "feed": "sip", "adjustment": "all"}, "bars"):
                for sym, bars in block.items():
                    for b in bars:
                        local[sym].append([b["t"][:10], b["c"]])
            done[0] += 1
            print(f"    bars chunk {done[0]}/{len(chunks)}", flush=True)
            return local

        with ThreadPoolExecutor(max_workers=6) as pool:
            for local in pool.map(work, chunks):
                for sym, rows in local.items():
                    out[sym].extend(rows)
        return {k: sorted(v) for k, v in out.items()}
    return cache_json("daily_bars", build)


import urllib.parse  # noqa: E402  (after the helpers that reference it by name)


# ---------------------------------------------------------------------------
# 6. THE CENSUS.  Counts, availability lags, dispersion, season clustering.
#    NOTHING here is sorted on a surprise.  See the module docstring.
# ---------------------------------------------------------------------------

HOLD_SESSIONS = 60          # Foster-Olsen-Shevlin / Martineau BHAR[2,60]
HORIZONS = (5, 21, 60)      # Martineau's [2,5] / a month / the canonical 60
DECILE = 10


def _dst_offset_hours(day: str) -> int:
    """UTC offset of New York on `day`.  -4 in EDT, -5 in EST.

    US rule since 2007: DST starts the 2nd Sunday in March, ends the 1st Sunday in November.
    """
    d = date.fromisoformat(day)
    mar = date(d.year, 3, 1)
    start = mar + timedelta(days=(6 - mar.weekday()) % 7 + 7)      # 2nd Sunday
    nov = date(d.year, 11, 1)
    end = nov + timedelta(days=(6 - nov.weekday()) % 7)            # 1st Sunday
    return -4 if start <= d < end else -5


def _et_naive(acceptance: str) -> datetime:
    """`acceptanceDateTime` -> naive ET datetime.  UTC stamps carry an explicit Z."""
    s = acceptance.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        # EDGAR historically emitted a naive stamp that is already ET.
        return dt
    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    guess = (dt + timedelta(hours=_dst_offset_hours(dt.date().isoformat())))
    return guess


def trading_days():
    cal = t3_cached("calendar")
    return [r["date"] for r in cal if START <= r["date"] <= END]


def _quarter_of(day: str) -> str:
    y, m = int(day[:4]), int(day[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def _duration_days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def build_events():
    """Every 8-K item 2.02 by a point-in-time universe member, with its entry session.

    Placement is decided by the acceptance TIMESTAMP, never by the filing date alone:
    a release accepted at 16:30 ET is not tradeable at that day's close.
    """
    uni = cache_json("universe", lambda: build_universe(TOP_N))
    m = symbol_to_cik(sorted({s for v in uni.values() for s in v}))
    sym2cik = m["cik"]
    ek = earnings_8k(sorted(set(sym2cik.values())))["by_cik"]
    days = trading_days()
    day_index = {d: i for i, d in enumerate(days)}
    day_set = set(days)

    by_month = {mo: set(v) for mo, v in uni.items()}
    events, placement, dropped = [], defaultdict(int), defaultdict(int)

    import bisect

    for sym, cik in sorted(sym2cik.items()):
        rows = ek.get(str(cik))
        if not rows:
            dropped["no_8k_2.02_for_cik"] += 1
            continue
        # De-duplicate FIRST, on the full filing history, before any other filter.  Doing it
        # after the universe screen would compare a filing against the last KEPT one and let
        # a re-issue through whenever the original happened to be screened out.
        deduped, last_seen = [], None
        for filing_date, acceptance, items, accession in sorted(rows):
            if not (START <= filing_date <= END):
                continue
            if last_seen and _duration_days(last_seen, filing_date) < 45:
                dropped["duplicate_within_45d"] += 1
                continue
            last_seen = filing_date
            deduped.append((filing_date, acceptance, items, accession))

        for filing_date, acceptance, items, accession in deduped:
            ts = _et_naive(acceptance)
            stamp_day = ts.date().isoformat()
            minutes = ts.hour * 60 + ts.minute
            if stamp_day in day_set and minutes < 9 * 60 + 30:
                where, react_day = "pre_open", stamp_day
            elif stamp_day in day_set and minutes < 16 * 60:
                where, react_day = "intraday", stamp_day
            else:
                where = "post_close" if stamp_day in day_set else "non_session"
                j = bisect.bisect_right(days, stamp_day)
                react_day = days[j] if j < len(days) else None
            if react_day is None:
                dropped["no_session_after_stamp"] += 1
                continue
            if react_day not in day_index:
                dropped["react_day_outside_window"] += 1
                continue
            if sym not in by_month.get(react_day[:7], ()):    # point-in-time membership
                dropped["not_in_universe_that_month"] += 1
                continue
            i = day_index[react_day]
            if i + HOLD_SESSIONS >= len(days):
                dropped["hold_runs_past_data_end"] += 1
                continue
            placement[where] += 1
            events.append({
                "symbol": sym, "cik": cik, "filing_date": filing_date,
                "acceptance": acceptance, "et": ts.isoformat(sep=" "),
                "placement": where, "entry_day": react_day,
                "exit_day": days[i + HOLD_SESSIONS],
                "exit_days": {str(h): days[i + h] for h in HORIZONS},
                "season": _quarter_of(react_day),
                "period": "design" if react_day <= DESIGN_END else "test",
            })
    return events, dict(placement), dict(dropped)


def eps_panel():
    """cik -> {period_end: (earliest_filed, value, form)} for QUARTERLY EPS facts only.

    EARLIEST filed wins, always.  A later fact for the same period is a RESTATEMENT and
    using it is precisely the leakage guardrail 1 forbids.
    """
    uni = cache_json("universe", lambda: build_universe(TOP_N))
    m = symbol_to_cik(sorted({s for v in uni.values() for s in v}))
    facts = eps_facts(sorted(set(m["cik"].values())))["by_cik"]
    out = {}
    for cik, rows in facts.items():
        best = {}
        for start, end, val, filed, form, fy, fp, frame in rows:
            n = _duration_days(start, end)
            if not (80 <= n <= 100):                 # a fiscal quarter, not a half or a year
                continue
            cur = best.get(end)
            if cur is None or filed < cur[0]:
                best[end] = (filed, val, form)
        out[cik] = best
    return out


def sue_availability(events, panel):
    """For every event: when did the ANNOUNCED quarter's EPS first exist in XBRL?

    This is the measurement the whole candidate turns on.  An 8-K item 2.02 carries the
    number in a press-release exhibit that is NOT XBRL-tagged; the structured fact normally
    arrives with the 10-Q.  If that lag is large, a point-in-time seasonal-random-walk SUE
    simply does not exist at the announcement, and the drift cannot be entered on it.
    """
    lags, forms, matched, unmatched = [], defaultdict(int), 0, 0
    computable_at_entry = 0
    full_sue_at_entry = 0
    gap_hist = defaultdict(int)
    for ev in events:
        best = panel.get(str(ev["cik"])) or {}
        f = ev["filing_date"]
        # The announced quarter is the one whose period END is the most recent date strictly
        # before the announcement.  A US issuer files item 2.02 within ~60 days of the period
        # end; a nearest quarterly fact FURTHER back than that means the announced quarter is
        # NOT tagged with this concept at all -- which is what happens to fiscal Q4, where the
        # 10-K tags the ANNUAL period and no 90-day fact for the quarter is ever filed.
        cands = [e for e in best if 0 < _duration_days(e, f) <= 60]
        if not cands:
            unmatched += 1
            gap_hist["no_quarterly_fact_within_60d_of_the_8K"] += 1
            continue
        end = max(cands)
        filed, val, form = best[end]
        matched += 1
        lag = _duration_days(f, filed)
        lags.append(lag)
        forms[form] += 1
        if filed <= ev["entry_day"]:
            computable_at_entry += 1
            # seasonal random walk also needs the same quarter one year earlier, and eight
            # prior quarters for the scaling standard deviation -- all filed before entry
            prior = sorted(e for e in best if e < end and best[e][0] <= ev["entry_day"])
            year_ago = [e for e in prior if 330 <= _duration_days(e, end) <= 400]
            if year_ago and len(prior) >= 8:
                full_sue_at_entry += 1
    lags.sort()

    def pct(p):
        if not lags:
            return None
        return lags[min(len(lags) - 1, int(p * len(lags)))]

    return {
        "events_matched_to_a_quarter": matched,
        "events_with_no_matching_quarter": unmatched,
        "xbrl_filed_minus_8k_filed_days": {
            "n": len(lags), "min": lags[0] if lags else None, "p05": pct(0.05),
            "p25": pct(0.25), "median": pct(0.50), "p75": pct(0.75), "p95": pct(0.95),
            "max": lags[-1] if lags else None,
            "mean": (sum(lags) / len(lags)) if lags else None,
            "share_le_0": sum(1 for x in lags if x <= 0) / len(lags) if lags else None,
            "share_le_1": sum(1 for x in lags if x <= 1) / len(lags) if lags else None,
            "share_le_5": sum(1 for x in lags if x <= 5) / len(lags) if lags else None,
        },
        "first_form_carrying_the_fact": dict(sorted(forms.items(), key=lambda kv: -kv[1])),
        "match_failure_reasons": dict(gap_hist),
        "announced_quarter_eps_public_by_entry_day": computable_at_entry,
        "full_point_in_time_SUE_by_entry_day": full_sue_at_entry,
    }


def abnormal_returns(events):
    """Market-adjusted buy-and-hold return, entry close -> exit close, per event.

    UNCONDITIONAL: no surprise, no sort, no ranking.  This is the dispersion input to the
    power calculation and nothing else.  Adjusted (total-return) closes on both legs.
    """
    bars = daily_bars(sorted({e["symbol"] for e in events}))
    spy = json.loads(gzip.open(
        ROOT / "research" / "data" / "t11_cache" / "adjusted_bars.json.gz", "rt").read())["SPY"]
    px = {s: dict(rows) for s, rows in bars.items()}
    kept, missing = [], 0
    for ev in events:
        p = px.get(ev["symbol"]) or {}
        a = p.get(ev["entry_day"])
        sa = spy.get(ev["entry_day"])
        if not a or not sa or a <= 0 or sa <= 0:
            missing += 1
            continue
        hs = {}
        for h, day in ev["exit_days"].items():
            b, sb = p.get(day), spy.get(day)
            if b and sb:
                hs[h] = (b / a) - (sb / sa)
        if str(HOLD_SESSIONS) not in hs:
            missing += 1
            continue
        ev = dict(ev)
        ev["bhar_by_h"] = hs
        ev["bhar"] = hs[str(HOLD_SESSIONS)]
        kept.append(ev)
    return kept, missing


def _book_from_scores(by_season, score, decile=DECILE):
    """Long top decile / short bottom decile WITHIN each season, on an arbitrary score.

    Returns season -> (book return, pair count).  `score(ev)` returns a float.
    """
    out = {}
    for season, rows in by_season.items():
        n = len(rows)
        k = n // decile
        if k < 1:
            continue
        order = sorted(range(n), key=lambda i: score(rows[i]))
        longs = [rows[i]["bhar"] for i in order[-k:]]
        shorts = [rows[i]["bhar"] for i in order[:k]]
        out[season] = ((sum(longs) / k) - (sum(shorts) / k), k)
    return out


def _rank_beta_parts(by_season, score):
    """Per-season (numerator, denominator) of the within-season rank regression.

    The pooled slope is `sum(num) / sum(den)`, which makes a season block bootstrap a sum
    over the chosen seasons rather than a refit -- the only reason this is affordable.
    The regressor is the uniform within-season rank on [0, 1], so the slope IS the fitted
    top-minus-bottom spread.  Martineau's Equation (5) without the fixed effects, and the
    MOST powerful framing available because it uses every event rather than a fifth of them
    -- so it is the framing the power gate is charitable enough to also report.
    """
    parts = {}
    for season, rows in by_season.items():
        n = len(rows)
        if n < 20:
            continue
        order = sorted(range(n), key=lambda i: score(rows[i]))
        u = [0.0] * n
        for pos, i in enumerate(order):
            u[i] = pos / (n - 1)
        ubar = sum(u) / n
        ybar = sum(r["bhar"] for r in rows) / n
        num = den = 0.0
        for i, r in enumerate(rows):
            du = u[i] - ubar
            num += du * (r["bhar"] - ybar)
            den += du * du
        parts[season] = (num, den)
    return parts


def power_census(events, *, boots=4000, block_seasons=(1, 2, 4), seed=20260817,
                 placebo_draws=200):
    import random
    rng = random.Random(seed)
    by_season = defaultdict(list)
    for ev in events:
        by_season[ev["season"]].append(ev)
    seasons = sorted(by_season)
    firms = sorted({ev["symbol"] for ev in events})

    xs = [ev["bhar"] for ev in events]
    n = len(xs)
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    n_pairs = sum(len(by_season[s]) // DECILE for s in seasons)
    naive_se = sd * math.sqrt(2.0) / math.sqrt(n_pairs)

    # ---- placebo score families -------------------------------------------------------
    # IID: a fresh random score per event.  A decile book built on it is factor-neutral
    #      within the season BY CONSTRUCTION, so the season-common shock cancels and this
    #      understates the clustering a real SUE sort suffers.
    # PERSISTENT: one random score per FIRM, reused every season.  SUE is autocorrelated
    #      (Bernard & Thomas 1989), so the real book holds many of the same names quarter
    #      after quarter; a persistent placebo reproduces that overlap and the cross-season
    #      correlation it creates.  This is the honest one.
    def iid_scores():
        return {id(ev): rng.random() for ev in events}

    def persistent_scores():
        base = {f: rng.random() for f in firms}
        return {id(ev): base[ev["symbol"]] for ev in events}

    def pooled(book, chosen):
        num = den = 0.0
        for s in chosen:
            if s not in book:
                continue
            r, k = book[s]
            num += r * k
            den += k
        return (num / den) if den else None

    def block_choices(L):
        starts = list(range(0, max(1, len(seasons) - L + 1)))
        nblocks = max(1, math.ceil(len(seasons) / L))
        chosen = []
        for _ in range(nblocks):
            s0 = rng.choice(starts)
            chosen.extend(seasons[s0:s0 + L])
        return chosen

    result = {}
    for label, maker in (("iid", iid_scores), ("persistent", persistent_scores)):
        books, parts = [], []
        for _ in range(placebo_draws):
            sc = maker()
            f = lambda ev, sc=sc: sc[id(ev)]                      # noqa: E731
            books.append(_book_from_scores(by_season, f))
            parts.append(_rank_beta_parts(by_season, f))
        se_by_L, beta_se_by_L = {}, {}
        for L in block_seasons:
            stats, bstats = [], []
            for b in range(boots):
                chosen = block_choices(L)
                v = pooled(books[b % len(books)], chosen)
                if v is not None:
                    stats.append(v)
                p = parts[b % len(parts)]
                num = sum(p[s][0] for s in chosen if s in p)
                den = sum(p[s][1] for s in chosen if s in p)
                if den:
                    bstats.append(num / den)
            m = sum(stats) / len(stats)
            se_by_L[L] = math.sqrt(sum((x - m) ** 2 for x in stats) / (len(stats) - 1))
            mb = sum(bstats) / len(bstats)
            beta_se_by_L[L] = math.sqrt(
                sum((x - mb) ** 2 for x in bstats) / (len(bstats) - 1))
        result[label] = {
            "decile_book_season_block_SE": {str(k): v for k, v in se_by_L.items()},
            "rank_regression_slope_season_block_SE": {str(k): v
                                                      for k, v in beta_se_by_L.items()},
        }

    z = 2.8016                                  # 80% power, two-sided 5%
    out = {
        "events": n,
        "seasons": len(seasons),
        "season_list": seasons,
        "events_per_season": {s: len(by_season[s]) for s in seasons},
        "decile_pairs_total": n_pairs,
        "per_event_abnormal_return_sd": sd,
        "per_event_abnormal_return_mean": mu,
        "naive_independent_event_SE_decile_book": naive_se,
        "naive_independent_event_MDE_decile_book": z * naive_se,
        "z_for_80pct_power_5pct_two_sided": z,
        "placebo": result,
    }
    for label in result:
        out["placebo"][label]["decile_book_season_block_MDE"] = {
            k: z * v for k, v in result[label]["decile_book_season_block_SE"].items()}
        out["placebo"][label]["rank_regression_MDE_on_full_rank_range"] = {
            k: z * v for k, v in
            result[label]["rank_regression_slope_season_block_SE"].items()}
        out["placebo"][label]["effective_independent_decile_pairs"] = {
            k: (naive_se / v) ** 2 * n_pairs
            for k, v in result[label]["decile_book_season_block_SE"].items()}
    return out


def census():
    print("== T15 POWER CENSUS ==", flush=True)
    uni = cache_json("universe", lambda: build_universe(TOP_N))
    syms = sorted({s for v in uni.values() for s in v})
    m = symbol_to_cik(syms)
    names = asset_names()
    unmapped_operating = [s for s in m["unmapped"]
                          if not _ETF.search(names.get(s) or "")]

    events, placement, dropped = build_events()
    print(f"  raw usable events: {len(events)}", flush=True)

    panel = eps_panel()
    avail = sue_availability(events, panel)
    print(f"  XBRL lag median: {avail['xbrl_filed_minus_8k_filed_days']['median']} days",
          flush=True)

    priced, missing_px = abnormal_returns(events)
    print(f"  priced events: {len(priced)} (missing prices {missing_px})", flush=True)

    design = [e for e in priced if e["period"] == "design"]
    test = [e for e in priced if e["period"] == "test"]
    pw_all = power_census(priced)
    pw_test = power_census(test)

    # The power gate must not depend on one horizon choice, so it is computed at all three.
    by_horizon = {}
    for h in HORIZONS:
        rows = [dict(e, bhar=e["bhar_by_h"][str(h)]) for e in test
                if str(h) in e["bhar_by_h"]]
        by_horizon[str(h)] = power_census(rows)

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "window": {"start": START, "end": END, "design_end": DESIGN_END,
                   "test_start": TEST_START},
        "hold_sessions": HOLD_SESSIONS,
        "universe": {
            "rule": "point-in-time top-500 by prior-month dollar ADV, raw close > $5, "
                    "ADV > $20M, from T3's cached monthly bars",
            "months": len(uni), "distinct_symbols": len(syms),
            "mapped_to_cik": len(m["cik"]),
            "unmapped": len(m["unmapped"]),
            "unmapped_etf_shaped": len(m["unmapped_etf_shaped"]),
            "unmapped_operating_companies": len(unmapped_operating),
            "unmapped_operating_list": sorted(unmapped_operating),
            "cik_match_method": {"ticker": sum(1 for v in m["how"].values() if v == "ticker"),
                                 "issuer_name": sum(1 for v in m["how"].values()
                                                    if v == "name")},
        },
        "events": {
            "total": len(events), "priced": len(priced),
            "missing_prices": missing_px,
            "design": len(design), "test": len(test),
            "placement_by_acceptance_timestamp": placement,
            "dropped": dropped,
        },
        "point_in_time_sue_availability": avail,
        "power_full_sample": pw_all,
        "power_heldout_only": pw_test,
        "power_heldout_by_horizon": by_horizon,
    }
    path = OUT / "T15_POWER_CENSUS.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=False))
    print(f"  wrote {path}")
    return out


# ---------------------------------------------------------------------------
# 7. THE VERDICT.  Reads the frozen gate and the census; adds nothing new.
# ---------------------------------------------------------------------------

GATE_PATH = OUT / "T15_POWER_GATE.md"
GATE_SHA = "76f712f7d03af75b65f193bb74f5c6f312a30c03be03d520ab09ecbf90de2b89"
BENCHMARK = 0.0090          # T15_POWER_GATE.md section 3: Martineau (2021) pooled full-sample
                            # random-walk-surprise decile spread, all-but-microcap, BHAR[2,60]

# Friction, per event, for the trade the gate describes: one MOC in, one MOC out, 60 sessions.
SEC31_FRACTION = 278 / 10 ** 7      # 0.278 bp of SALE notional, top of the 2016-2026 range
TAF_PER_SHARE = 0.000166            # FINRA TAF, $/share sold
BORROW_ANNUAL = 0.0033              # B22G measured ETB general collateral, 33 bp/yr


def verdict():
    import hashlib

    gate_text = GATE_PATH.read_bytes()
    digest = hashlib.sha256(gate_text).hexdigest()
    if digest != GATE_SHA:
        raise Refused(
            f"{GATE_PATH.name} hashes {digest}, not the frozen {GATE_SHA}. The gate this "
            "verdict cites is not the gate that was frozen; refusing rather than reporting "
            "against a threshold that may have moved after the number existed."
        )
    census = json.loads((OUT / "T15_POWER_CENSUS.json").read_text())
    p = census["power_heldout_only"]
    z = p["z_for_80pct_power_5pct_two_sided"]
    se_naive = p["naive_independent_event_SE_decile_book"]
    se_block = p["placebo"]["persistent"]["decile_book_season_block_SE"]["1"]
    mde = z * se_block
    n, pairs, seasons = p["events"], p["decile_pairs_total"], p["seasons"]
    sd = p["per_event_abnormal_return_sd"]
    scale = (mde / BENCHMARK) ** 2
    held_out_years = 4.62                     # 2022-01-03 -> 2026-08-14

    # friction on the M0 auction rail: half-spread 0 per leg, one sale leg per event,
    # borrow on the short half of the book only.
    borrow_bp = BORROW_ANNUAL * (87 / 365) * 1e4
    friction_rail_bp = SEC31_FRACTION * 1e4 + (TAF_PER_SHARE / 100.0) * 1e4 + borrow_bp / 2
    friction_spread_bp = friction_rail_bp + 2 * 1.43          # T3 test-period half-spread/leg

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "gate_file": str(GATE_PATH.relative_to(ROOT)),
        "gate_sha256": digest,
        "gate_threshold_MDE": BENCHMARK,
        "gate_threshold_source": "Martineau (2021) Critical Finance Review Table 4 Panel B, "
                                 "all-but-microcap, random-walk surprise decile rank, "
                                 "BHAR[2,60], pooled 1973-2019: beta 0.001 x 9 ranks",
        "held_out": {"window": ["2022-01-03", "2026-08-14"], "years": held_out_years,
                     "events": n, "seasons": seasons, "decile_pairs": pairs,
                     "per_event_abnormal_return_sd": sd},
        "MDE": {
            "primary_decile_book_persistent_placebo_block1": mde,
            "naive_every_event_independent": z * se_naive,
            "season_clustering_variance_inflation": (se_block / se_naive) ** 2,
            "most_powerful_framing_rank_regression":
                z * p["placebo"]["persistent"]
                     ["rank_regression_slope_season_block_SE"]["1"],
            "by_horizon": {h: (z * v["placebo"]["persistent"]
                                 ["decile_book_season_block_SE"]["1"])
                           for h, v in census["power_heldout_by_horizon"].items()},
        },
        "GATE": {
            "threshold": BENCHMARK, "observed": mde,
            "fails_by_factor": mde / BENCHMARK,
            "passes": mde <= BENCHMARK,
        },
        "what_would_be_needed": {
            "variance_scale": scale,
            "decile_pairs_required": pairs * scale,
            "events_required": n * scale,
            "events_per_year_observed": n / held_out_years,
            "years_of_collection_at_this_universe_width": scale * held_out_years,
            "universe_width_required_names": 500 * scale,
        },
        "detectability_of_the_literature": {
            "detectable_at_80pct_power": mde,
            "Foster_Olsen_Shevlin_1984_classic_60d_decile_spread": 0.05,
            "Martineau_1973_1990_all_but_microcap_random_walk": 0.027,
            "Martineau_pooled_1973_2019_all_but_microcap_random_walk": 0.009,
            "Chordia_2009_most_liquid_quintile_three_months": 0.0012,
        },
        "friction_per_event_bp": {
            "auction_rail_M0": friction_rail_bp,
            "plus_one_measured_half_spread_per_leg": friction_spread_bp,
            "per_event_dispersion_bp": sd * 1e4,
            "dispersion_over_friction_rail": (sd * 1e4) / friction_rail_bp,
        },
        "point_in_time_sue_availability": census["point_in_time_sue_availability"],
        "verdict": ("DEAD-BY-INSUFFICIENT-POWER" if mde > BENCHMARK else "POWERED"),
    }
    path = OUT / "T15_RESULT.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["GATE"], indent=2))
    print(f"  wrote {path}")
    return out


# ---------------------------------------------------------------------------
# entry point for the collection stage
# ---------------------------------------------------------------------------

def collect():
    print("[1/5] universe (point-in-time top-%d ADV, from T3's cached monthly bars)" % TOP_N)
    uni = cache_json("universe", lambda: build_universe(TOP_N))
    syms = sorted({s for v in uni.values() for s in v})
    print(f"      {len(uni)} months, {len(syms)} distinct symbols")

    print("[2/5] symbol -> CIK")
    m = symbol_to_cik(syms)
    print(f"      mapped {len(m['cik'])}, unmapped {len(m['unmapped'])} "
          f"({len(m['unmapped_etf_shaped'])} ETF-shaped, "
          f"{len(m['unmapped_nameless'])} nameless/delisted)")

    ciks = sorted(set(m["cik"].values()))
    print(f"[3/5] 8-K item 2.02 for {len(ciks)} CIKs")
    ek = earnings_8k(ciks)
    n8k = sum(len(v) for v in ek["by_cik"].values())
    print(f"      {n8k} item-2.02 8-Ks, {len(ek['failed'])} CIKs failed")

    print(f"[4/5] XBRL EarningsPerShareDiluted for {len(ciks)} CIKs")
    eps = eps_facts(ciks)
    nf = sum(len(v) for v in eps["by_cik"].values())
    print(f"      {nf} facts, {len(eps['missing'])} CIKs with no such tag")

    print(f"[5/5] adjusted daily bars for {len(syms)} symbols")
    bars = daily_bars(syms)
    print(f"      {len(bars)} symbols, {sum(len(v) for v in bars.values())} bars")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if cmd == "collect":
        collect()
    elif cmd == "census":
        census()
    elif cmd == "verdict":
        verdict()
    else:
        raise SystemExit(f"unknown command {cmd!r}")
