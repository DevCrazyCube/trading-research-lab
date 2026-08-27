#!/usr/bin/env python3
"""T17 DATA COLLECTION ONLY. No strategy logic, no fitting, no verdict.

This file fetches and caches market data. It is deliberately separate from the frozen
strategy artifact (`t17_orb.py`) so that "what data exists" and "what rule is under test"
cannot contaminate each other: the rule is hashed before this has produced a single trade.

ENDPOINT SAFETY (guardrail 3). Only `data.alpaca.markets` is contacted. Order submission
does not exist in this file and the live-trading host is not referenced.

POINT-IN-TIME DISCIPLINE.
  * `adjustment=raw` everywhere. The universe screen filters on PRICE LEVELS (open >= $5)
    and on ATR in DOLLARS (>= $0.50), and an adjusted level is retroactive -- the adjusted
    2016 price of a stock that later split 10:1 is not the price the filter would have
    seen. `scripts/trading_bot/data.py` states this rule; this module obeys it.
    Consequence, stated rather than hidden: a raw daily series has a jump on a split date,
    so ATR(14) is overstated for up to 14 sessions after a split. That widens R, which
    SHRINKS the position and WIDENS the stop -- it does not manufacture profit. The frozen
    B22B runner used raw daily bars with no split guard and this matches it.
  * The strategy is intraday: every position opens and closes inside one session, so no
    dividend or split ever falls between entry and exit.

SURVIVORSHIP. The symbol master is built from Alpaca `/v2/assets` with BOTH
`status=active` and `status=inactive`, so names that have since delisted are present. This
is a mitigation, not a cure: Alpaca's inactive list is what Alpaca still carries, and a
symbol it dropped entirely is invisible to us. Recorded in the manifest.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from trading_bot.data import load_env_credentials  # noqa: E402
from trading_bot.frozen import Refused  # noqa: E402

DATA_HOST = "https://data.alpaca.markets"
BROKER_HOST = "https://paper-api.alpaca.markets"   # /v2/assets only; never /v2/orders
CACHE = ROOT / "research" / "data" / "t17_cache"
CACHE.mkdir(parents=True, exist_ok=True)

KEY, SECRET = load_env_credentials()
HEADERS = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET, "Accept": "application/json"}

# Alpaca reports X-Ratelimit-Limit: 200 (per minute) on this account. Stay under it.
# Divided across concurrent workers via T17_RATE (requests/minute for THIS process), so the
# sum over processes stays under the account limit.
_MIN_INTERVAL = 60.0 / float(os.environ.get("T17_RATE", "190"))
_last_call = [0.0]


def _throttle():
    wait = _MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def api_get(host: str, path: str, params: dict, tries: int = 6):
    """One GET, fully error-checked. A transport failure retries; an absent field never
    becomes a zero."""
    url = host + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for attempt in range(tries):
        _throttle()
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            if exc.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise Refused(f"HTTP {exc.code} for {path}: {body}")
        except Exception as exc:  # transport reset / timeout
            if attempt < tries - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise Refused(f"transport failure for {path}: {exc!r}")
    raise Refused(f"exhausted retries for {path}")


def api_get_paged(path: str, params: dict, key: str):
    """Every page. A truncated response is a wrong answer, not a small one (B22B's rule)."""
    token, out = None, {}
    while True:
        p = dict(params)
        if token:
            p["page_token"] = token
        d = api_get(DATA_HOST, path, p)
        chunk = d.get(key) or {}
        if isinstance(chunk, dict):
            for sym, bars in chunk.items():
                out.setdefault(sym, []).extend(bars)
        else:
            out.setdefault("_", []).extend(chunk)
        token = d.get("next_page_token")
        if not token:
            return out


# ---------------------------------------------------------------- symbol master

EXCHANGES = ("NASDAQ", "NYSE", "ARCA", "BATS", "AMEX")   # OTC excluded: not the paper's tape

# Alpaca's asset list contains rows that are not tradeable tickers at all -- CUSIP stubs
# ("0029900E0", "294UNT019"), placeholder names ("ABCD_DELISTED"), contingent-value-right
# stubs. The bars endpoint rejects the whole request with HTTP 400 if one is present, so
# they are excluded by SHAPE rather than by name. The shape is the standard US listed
# ticker: 1-5 letters, optionally a one/two letter class suffix after '.' or '-'.
TICKER_RE = __import__("re").compile(r"^[A-Z]{1,5}([.\-][A-Z]{1,2})?$")


def build_symbol_master() -> list:
    path = CACHE / "symbol_master.json"
    if path.exists():
        return json.loads(path.read_text())["symbols"]
    syms, seen = [], set()
    for status in ("active", "inactive"):
        rows = api_get(BROKER_HOST, "/v2/assets",
                       {"asset_class": "us_equity", "status": status})
        for r in rows:
            if r.get("exchange") not in EXCHANGES:
                continue
            s = r.get("symbol")
            if not s or s in seen or not TICKER_RE.match(s):
                continue
            seen.add(s)
            syms.append(s)
    syms.sort()
    path.write_text(json.dumps({
        "built": time.strftime("%Y-%m-%d"),
        "exchanges": list(EXCHANGES),
        "statuses": ["active", "inactive"],
        "survivorship": ("MITIGATED, NOT CURED. Inactive (delisted) symbols are included, so "
                         "the universe is not today's listings only. A symbol Alpaca has "
                         "dropped from its asset list entirely remains invisible."),
        "n": len(syms), "symbols": syms}, indent=1))
    return syms


# ---------------------------------------------------------------- daily bars

DAILY_START = "2015-11-01"     # >= 15 sessions of warm-up before 2016-01-04
DAILY_END = "2026-08-15"


def daily_chunk_path(i: int) -> pathlib.Path:
    return CACHE / "daily" / f"chunk_{i:04d}.json"


def fetch_daily(symbols: list, workers_arg: str = "0/1"):
    (CACHE / "daily").mkdir(exist_ok=True)
    idx, nworkers = (int(x) for x in workers_arg.split("/"))
    chunks = [symbols[i:i + 100] for i in range(0, len(symbols), 100)]
    for ci, chunk in enumerate(chunks):
        if ci % nworkers != idx:
            continue
        p = daily_chunk_path(ci)
        if p.exists():
            continue
        live = list(chunk)
        dropped = []
        while True:
            try:
                bars = api_get_paged("/v2/stocks/bars", {
                    "symbols": ",".join(live), "timeframe": "1Day",
                    "start": DAILY_START, "end": DAILY_END,
                    "feed": "sip", "adjustment": "raw", "limit": 10000}, "bars")
                break
            except Refused as exc:
                # "invalid symbol: X" rejects the WHOLE request. Drop the named symbol and
                # retry; record it rather than losing the other 99 silently.
                m = __import__("re").search(r"invalid symbol: ([^\"}]+)", str(exc))
                if not m or m.group(1) not in live:
                    raise
                dropped.append(m.group(1))
                live.remove(m.group(1))
        # keep only what the screen needs, as compact rows: [date, o, h, l, c, v]
        slim = {s: [[b["t"][:10], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in v]
                for s, v in bars.items() if v}
        tmp = p.with_suffix(".partial")
        tmp.write_text(json.dumps(slim))
        os.replace(tmp, p)
        print(f"chunk {ci}/{len(chunks)}: {len(slim)} symbols with data", flush=True)


# ---------------------------------------------------------------- intraday

CHUNK_SYMBOLS = 700          # measured: one request serves 800 symbols; 700 leaves headroom


def _iso_ns(ns: int) -> str:
    import datetime
    return (datetime.datetime.fromtimestamp(ns // 1_000_000_000, datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"))


def fetch_opening(workers_arg: str = "0/1", start: str = "2016-01-01", end: str = "2026-12-31"):
    """The [09:30, 09:35) 5-minute bar for every screen passer, every session.

    The set fetched on session e is the UNION of the screen's passers over sessions
    [e, e+14]. That is not padding: the relative-volume denominator is a stock's own average
    opening volume over the 14 sessions BEFORE the one it is selected on, so a session's
    opening bar is needed by every one of the next 14 sessions' decisions. Fetching only the
    days a stock passed the screen would compute the denominator from high-volume days only
    and bias every relative volume DOWNWARD.
    """
    import trading_bot.frozen as P
    from datetime import date
    (CACHE / "opening").mkdir(exist_ok=True)
    screen = json.loads((CACHE / "screen.json").read_text())
    # The FULL session list -- the 15-session union below must not be truncated by the
    # --start/--end work range, or a partial run would compute a different (smaller) need
    # set than a full one and the cache would be silently inconsistent between the two.
    days = sorted(screen)
    idx, nworkers = (int(x) for x in workers_arg.split("/"))
    for di, day in enumerate(days):
        if di % nworkers != idx or not (start <= day <= end):
            continue
        p = CACHE / "opening" / f"{day}.json"
        if p.exists():
            continue
        need = set()
        for d2 in days[di:di + 15]:
            need.update(r[0] for r in screen[d2])
        need = sorted(need)
        d = date.fromisoformat(day)
        o_ns = P.session_bound_ns(d, P.SESSION_OPEN)
        out = {}
        for i in range(0, len(need), CHUNK_SYMBOLS):
            live = need[i:i + CHUNK_SYMBOLS]
            while True:
                try:
                    bars = api_get_paged("/v2/stocks/bars", {
                        "symbols": ",".join(live), "timeframe": "5Min",
                        "start": _iso_ns(o_ns), "end": _iso_ns(o_ns + 300 * 10 ** 9),
                        "feed": "sip", "adjustment": "raw", "limit": 10000}, "bars")
                    break
                except Refused as exc:
                    m = __import__("re").search(r"invalid symbol: ([^\"}]+)", str(exc))
                    if not m or m.group(1) not in live:
                        raise
                    live.remove(m.group(1))
            for sym, bl in bars.items():
                # Only the bar that STARTS at 09:30. Alpaca's `end` is inclusive of a bar that
                # starts exactly at it, so a 09:35 bar can come back; it is not the opening
                # range and is dropped rather than merged.
                first = [b for b in bl if P.parse_rfc3339_ns(b["t"]) == o_ns]
                if first:
                    b = first[0]
                    out[sym] = [b["o"], b["h"], b["l"], b["c"], b["v"]]
        tmp = p.with_suffix(".partial")
        tmp.write_text(json.dumps(out))
        os.replace(tmp, p)
        print(f"{day}: needed {len(need)}, got {len(out)}", flush=True)


def fetch_paths(workers_arg: str = "0/1"):
    """1-minute bars 09:35 -> 16:00 ET for the 20 selected names of each session.

    Reads the selection produced by `t17_select.py`, which is itself produced by the FROZEN
    rule. Nothing here chooses a symbol.
    """
    import trading_bot.frozen as P
    from datetime import date
    (CACHE / "paths").mkdir(exist_ok=True)
    sel = json.loads((CACHE / "selection.json").read_text())
    days = sorted(sel)
    idx, nworkers = (int(x) for x in workers_arg.split("/"))
    for di, day in enumerate(days):
        if di % nworkers != idx:
            continue
        p = CACHE / "paths" / f"{day}.json"
        if p.exists():
            continue
        syms = sorted({row[1] for row in sel[day]})
        if not syms:
            p.write_text(json.dumps({}))
            continue
        d = date.fromisoformat(day)
        o_ns = P.session_bound_ns(d, P.SESSION_OPEN)
        bars = api_get_paged("/v2/stocks/bars", {
            "symbols": ",".join(syms), "timeframe": "1Min",
            "start": _iso_ns(o_ns + 300 * 10 ** 9),
            "end": _iso_ns(P.session_bound_ns(d, P.SESSION_CLOSE)),
            "feed": "sip", "adjustment": "raw", "limit": 10000}, "bars")
        out = {s: [[b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in v]
               for s, v in bars.items() if v}
        tmp = p.with_suffix(".partial")
        tmp.write_text(json.dumps(out))
        os.replace(tmp, p)
        print(f"{day}: {len(out)}/{len(syms)} paths", flush=True)


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "opening":
        fetch_opening(sys.argv[2] if len(sys.argv) > 2 else "0/1",
                      *(sys.argv[3:5] if len(sys.argv) > 4 else []))
    elif what == "paths":
        fetch_paths(sys.argv[2] if len(sys.argv) > 2 else "0/1")
    elif what == "master":
        s = build_symbol_master()
        print(f"{len(s)} symbols")
    elif what == "daily":
        s = build_symbol_master()
        fetch_daily(s, sys.argv[2] if len(sys.argv) > 2 else "0/1")
    else:
        raise SystemExit(f"unknown stage {what!r}")
