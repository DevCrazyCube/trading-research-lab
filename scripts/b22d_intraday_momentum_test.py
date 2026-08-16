#!/usr/bin/env python3
"""B22D -- Gao/Han/Li/Zhou market intraday momentum, run out of sample on SPY.

THE RULE, taken verbatim from the paper and not modified:

    r1 = return from the previous session's 16:00 close to today's 10:00 ET price.
    At 15:30 ET take a LONG position if r1 > 0, a SHORT position if r1 < 0.
    Exit at the 16:00 close.

Zero free parameters. There is no threshold, no lookback, no stop. The only decision is
the SIGN of r1, and that sign is computed by INTEGER comparison of exact micro-dollar
prices, so it involves no float and no tolerance.

WHAT MAKES THIS OUT OF SAMPLE
    The paper's data ends in 2013 and it published in 2018. Alpaca's history starts in
    2016, so every observation here is after the paper's sample and after publication.

COST MODEL
    Entry at 15:30 is a marketable order and pays the half-spread.
    Exit at 16:00 is a market-on-close order, filled in the closing auction at a single
    clearing price for all buys and sells, and therefore pays NO spread. This is the
    paper's own treatment and it is a property of market structure, not an assumption:
    "Since the closing of the SPY is uniquely traded at the market clearing price for all
    the buys and sells, there will be no bid/ask spread effect for the price at 4:00pm."

    Costs are swept across a ladder rather than fixed at one favourable value.

PRE-COMMITTED INTERPRETATION (research/B22D_INTRADAY_MOMENTUM_CANDIDATE.md, section 5)
    Over ~10 out-of-sample years a true Sharpe of 1.07 gives t ~= 3.5 and a true Sharpe of
    0.45 (the McLean-Pontiff post-publication haircut) gives t ~= 1.4. The test can
    therefore show the effect INTACT or DEAD, but cannot certify a decayed-but-alive
    version. An ambiguous result is to be reported as ambiguous.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone

MICROS = 1_000_000
DATA_HOST = "https://data.alpaca.markets"
CACHE = "research/data/spy_30min_bars.json"

SESSION_FIRST_BAR = time(9, 30)    # 09:30-10:00 bar; its CLOSE is the 10:00 price
SESSION_LAST_BAR = time(15, 30)    # 15:30-16:00 bar; OPEN is 15:30, CLOSE is the 16:00 close

# Half-spread charged on the 15:30 entry, in basis points. The paper measures SPY's
# proportional spread stabilising at ~1.2 bps after 2005, so 0.6 bps is the matching
# half-spread. The ladder exists so the result is never reported at a single flattering value.
HALF_SPREAD_BP_LADDER = (0.0, 0.6, 1.0, 2.0, 5.0)

TRADING_DAYS_PER_YEAR = 252


class Refused(Exception):
    """Raised when a fact cannot be established. Never caught to produce a default."""


def to_micros(value) -> int:
    if value is None:
        raise Refused("price absent; refusing to substitute zero")
    return int(round(float(value) * MICROS))


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def et_offset_hours(day: date) -> int:
    """UTC offset of US Eastern time. Derived per day, never passed in.

    Same function as the B22B harness, for the same reason: a single per-run offset would
    silently shift every bar by an hour across a DST boundary.
    """
    if day.year < 2007:
        raise Refused(f"pre-2007 DST rules differ; refusing to guess for {day}")
    return -4 if _nth_weekday(day.year, 3, 6, 2) <= day < _nth_weekday(day.year, 11, 6, 1) else -5


def credentials() -> tuple[str, str]:
    env = {}
    if os.path.exists(".env"):
        for line in open(".env"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v.strip().strip('"').strip("'")
    kid = os.environ.get("ALPACA_API_KEY_ID") or env.get("ALPACA_API_KEY_ID")
    sec = os.environ.get("ALPACA_API_SECRET_KEY") or env.get("ALPACA_API_SECRET_KEY")
    if not kid or not sec:
        raise Refused("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not found")
    return kid, sec


def fetch_bars(start: str, end: str) -> list[dict]:
    """All SPY 30-minute bars in the window. Fully paged -- a truncated page is a wrong answer."""
    kid, sec = credentials()
    out, token = [], None
    while True:
        params = {
            "symbols": "SPY", "timeframe": "30Min", "start": start, "end": end,
            "limit": 10000, "feed": "sip", "adjustment": "all",
        }
        if token:
            params["page_token"] = token
        url = f"{DATA_HOST}/v2/stocks/bars?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                payload = json.loads(r.read().decode())
        except urllib.error.HTTPError as exc:
            raise Refused(f"HTTP {exc.code}: {exc.read().decode()[:300]}") from exc
        out.extend(payload.get("bars", {}).get("SPY", []))
        token = payload.get("next_page_token")
        if not token:
            return out


def session_table(bars: list[dict]) -> list[dict]:
    """Group bars into sessions and extract the four prices the rule needs.

    A session is kept only if BOTH the 09:30 and 15:30 regular-session bars are present.
    A day missing either one is dropped and counted -- never patched from a neighbouring
    bar, which would fabricate the very price the rule keys on.
    """
    by_day: dict[date, dict[time, dict]] = {}
    for bar in bars:
        stamp = datetime.strptime(bar["t"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        # Convert to ET using the offset for the UTC date, then re-derive from the ET date
        # so a bar near midnight is attributed to the right session.
        et = stamp + timedelta(hours=et_offset_hours(stamp.date()))
        by_day.setdefault(et.date(), {})[et.time()] = bar

    sessions, dropped = [], 0
    for day in sorted(by_day):
        slots = by_day[day]
        first, last = slots.get(SESSION_FIRST_BAR), slots.get(SESSION_LAST_BAR)
        if first is None or last is None:
            dropped += 1
            continue
        sessions.append({
            "day": day,
            "p_1000": to_micros(first["c"]),   # close of the 09:30-10:00 bar
            "p_1530": to_micros(last["o"]),    # open of the 15:30-16:00 bar
            "p_1600": to_micros(last["c"]),    # close of the 15:30-16:00 bar = official close
        })
    return sessions, dropped


def build_observations(sessions: list[dict]) -> list[dict]:
    """One observation per session that has a prior session to measure r1 against.

    The first session in the sample has NO prior close, so r1 is UNDEFINED for it and it is
    excluded. It is not treated as r1 = 0.
    """
    obs = []
    for i in range(1, len(sessions)):
        prev, cur = sessions[i - 1], sessions[i]
        # THE DECISION: integer comparison of exact prices. No float, no tolerance.
        if cur["p_1000"] > prev["p_1600"]:
            direction = 1
        elif cur["p_1000"] < prev["p_1600"]:
            direction = -1
        else:
            direction = 0          # exactly flat: stand aside. Not "long".
        obs.append({
            "day": cur["day"],
            "direction": direction,
            "r1": cur["p_1000"] / prev["p_1600"] - 1.0,
            "last_half_hour": cur["p_1600"] / cur["p_1530"] - 1.0,
            "close_to_close": cur["p_1600"] / prev["p_1600"] - 1.0,
        })
    return obs


def stats(returns: list[float]) -> dict:
    n = len(returns)
    if n < 2:
        raise Refused("need at least two observations")
    mean = statistics.fmean(returns)
    sd = statistics.stdev(returns)
    ann_ret = mean * TRADING_DAYS_PER_YEAR
    ann_vol = sd * math.sqrt(TRADING_DAYS_PER_YEAR)
    return {
        "n": n,
        "ann_return_pct": ann_ret * 100,
        "ann_vol_pct": ann_vol * 100,
        "sharpe": ann_ret / ann_vol if ann_vol else None,
        # t-stat of the mean daily return against zero. This is the number the
        # pre-committed power calculation is about.
        "t_stat": mean / (sd / math.sqrt(n)),
        "success_rate_pct": 100.0 * sum(1 for r in returns if r >= 0) / n,
        "total_return_pct": (math.prod(1 + r for r in returns) - 1) * 100,
    }


def run(half_spread_bp: float, obs: list[dict]) -> list[float]:
    """Strategy returns net of the entry half-spread. The MOC exit pays no spread."""
    cost = half_spread_bp / 10_000.0
    out = []
    for o in obs:
        if o["direction"] == 0:
            out.append(0.0)                                  # stood aside
        else:
            out.append(o["direction"] * o["last_half_hour"] - cost)
    return out


def main() -> int:
    start, end = "2016-01-01T00:00:00Z", datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")

    if os.path.exists(CACHE):
        bars = json.load(open(CACHE))
        print(f"cache: {len(bars)} bars from {CACHE}")
    else:
        print(f"fetching SPY 30-min bars {start[:10]} .. {end[:10]} ...")
        bars = fetch_bars(start, end)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(bars, open(CACHE, "w"))
        print(f"fetched and cached {len(bars)} bars")

    sessions, dropped = session_table(bars)
    obs = build_observations(sessions)
    print(f"sessions: {len(sessions)} complete, {dropped} dropped for a missing 09:30 or 15:30 bar")
    print(f"observations: {len(obs)} (first session excluded -- r1 undefined without a prior close)")
    print(f"range: {obs[0]['day']} .. {obs[-1]['day']}")
    longs = sum(1 for o in obs if o["direction"] == 1)
    shorts = sum(1 for o in obs if o["direction"] == -1)
    flats = sum(1 for o in obs if o["direction"] == 0)
    print(f"direction split: {longs} long, {shorts} short, {flats} flat")

    print("\n" + "=" * 78)
    print("COST LADDER -- strategy net of the 15:30 entry half-spread")
    print("=" * 78)
    print(f"{'half-spread':>12} {'ann ret':>9} {'ann vol':>9} {'Sharpe':>8} {'t-stat':>8} {'win%':>7} {'total%':>10}")
    for bp in HALF_SPREAD_BP_LADDER:
        s = stats(run(bp, obs))
        print(f"{bp:>10.1f}bp {s['ann_return_pct']:>8.2f}% {s['ann_vol_pct']:>8.2f}% "
              f"{s['sharpe']:>8.2f} {s['t_stat']:>8.2f} {s['success_rate_pct']:>6.1f}% "
              f"{s['total_return_pct']:>9.1f}%")

    print("\n" + "=" * 78)
    print("BENCHMARKS")
    print("=" * 78)
    always_long = [o["last_half_hour"] for o in obs]
    buy_hold = [o["close_to_close"] for o in obs]
    for name, rets in (("always long 15:30-16:00", always_long), ("SPY close-to-close", buy_hold)):
        s = stats(rets)
        print(f"{name:>26}: ann {s['ann_return_pct']:>7.2f}%  vol {s['ann_vol_pct']:>6.2f}%  "
              f"Sharpe {s['sharpe']:>6.2f}  t {s['t_stat']:>6.2f}  win {s['success_rate_pct']:.1f}%")

    print("\n" + "=" * 78)
    print("YEAR BY YEAR at 0.6bp half-spread -- the real diagnostic")
    print("=" * 78)
    net = run(0.6, obs)
    years = sorted({o["day"].year for o in obs})
    print(f"{'year':>6} {'n':>5} {'strategy':>10} {'always-long':>12} {'buy&hold':>10} {'win%':>7}")
    for y in years:
        idx = [i for i, o in enumerate(obs) if o["day"].year == y]
        sr = [net[i] for i in idx]
        al = [obs[i]["last_half_hour"] for i in idx]
        bh = [obs[i]["close_to_close"] for i in idx]
        tot = lambda xs: (math.prod(1 + x for x in xs) - 1) * 100
        win = 100.0 * sum(1 for x in sr if x >= 0) / len(sr)
        print(f"{y:>6} {len(idx):>5} {tot(sr):>9.2f}% {tot(al):>11.2f}% {tot(bh):>9.2f}% {win:>6.1f}%")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
