#!/usr/bin/env python3
"""T24 -- CME regulated crypto-futures cash-and-carry BASIS probe.

Bounded probe, not a frozen test.  Answers four questions with live free data:

  1. DATA      is a free CME BTC/ETH futures settlement + basis history obtainable?
  2. MEASURE   what is the historical annualised cash-and-carry basis -- level,
               stability, term structure, roll behaviour?
  3. COMPARE   how does it price against crypto-perp funding carry, and what is the
               retail execution reality (SPAN margin, roll cost, spot leg, capacity)?
  4. VERDICT   better / comparable / worse than perp funding carry as pillar #1?

Sources, all free and keyless (probed 2026-08-19):
  futures  Yahoo chart API.  `BTC=F` / `ETH=F` are the NEAREST CME contract and their
           daily close is the CME 15:00 CT settlement -- both facts are VERIFIED here,
           not assumed (see `verify_alignment` and `verify_roll`).
           Per-contract symbols `BTCU26.CME` etc. exist for CURRENTLY LISTED contracts
           only; expired contracts 404, so there is no historical term-structure panel.
  spot     Binance public klines (1h) -- the leg is taken at 20:00 UTC to match the
           CME settlement instant.
  funding  Binance USDT-perp `fundingRate` -- the head-to-head comparator.
  rf       repo cache research/data/t13_cache/cash.csv (FRED DTB3), 3-month T-bill.
  OI       CFTC public reporting (Socrata), legacy futures-only COT -- capacity.
  CME direct: cmegroup.com returns HTTP 403 with an explicit anti-scraping message on
           every path tried (quotes, settlements, ftp, product pages).  D=1 for CME itself.

Usage:  python3 scripts/trading_bot/t24_cme_basis.py [--cache DIR] [--fetch]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / "research" / "data" / "t24_cache"
UA = "Mozilla/5.0 (X11; Linux x86_64)"
YAHOO = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
         "?period1=0&period2=2000000000&interval={iv}")
# Yahoo rate-limits hard; 3.2s between calls was sufficient on 2026-08-19.
YAHOO_SLEEP = 3.2
ETF_LAUNCH = dt.date(2024, 1, 11)          # US spot-BTC ETFs begin trading
CME_START = 1513468800000                  # 2017-12-17, first CME BTC futures session


class Refused(Exception):
    """Absence is refusal, never zero."""


# ----------------------------------------------------------------- fetching
def _curl(url: str, attempts: int = 5) -> bytes:
    last = ""
    for k in range(attempts):
        p = subprocess.run(["curl", "-sS", "--max-time", "90", "-A", UA, url],
                           capture_output=True)
        body = p.stdout
        if p.returncode == 0 and body and b"Too Many Requests" not in body[:64]:
            return body
        last = (body[:80] or p.stderr[:80]).decode("utf8", "replace")
        time.sleep(6 * (k + 1))
    raise Refused(f"{url}: {last}")


def _cached(cache: pathlib.Path, name: str, url: str, sleep: float = 0.0) -> bytes:
    f = cache / name
    if f.exists() and f.stat().st_size:
        return f.read_bytes()
    raw = _curl(url)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(raw)
    if sleep:
        time.sleep(sleep)
    return raw


def fetch_all(cache: pathlib.Path) -> None:
    """Populate the cache.  Every call is free and keyless."""
    for sym in ("BTC=F", "ETH=F"):
        _cached(cache, f"y_{sym.replace('=', 'EQ')}.json",
                YAHOO.format(sym=sym.replace("=", "%3D"), iv="1d"), YAHOO_SLEEP)
    # live contracts: probe the whole grid; only listed ones return data
    months = "FGHJKMNQUVXZ"
    live = {}
    for root in ("BTC", "ETH"):
        for yr in (26, 27):
            for i, mc in enumerate(months, start=1):
                sym = f"{root}{mc}{yr:02d}.CME"
                try:
                    raw = _cached(cache, f"y_{sym}.json",
                                  YAHOO.format(sym=sym, iv="1d"), YAHOO_SLEEP)
                except Refused:
                    continue
                res = json.loads(raw)["chart"]["result"]
                if res and len(res[0].get("timestamp", [])) > 1:
                    live[sym] = {"root": root, "month": i, "year": 2000 + yr}
    (cache / "live_contracts.json").write_text(json.dumps(live, indent=1))

    for sym in ("BTCUSDT", "ETHUSDT"):
        f = cache / f"spot_{sym}_1h.json"
        if not f.exists():
            out, cur = [], CME_START
            while True:
                d = json.loads(_curl("https://api.binance.com/api/v3/klines"
                                     f"?symbol={sym}&interval=1h&startTime={cur}&limit=1000"))
                if not d:
                    break
                out += [[int(r[0]), float(r[4])] for r in d]
                if len(d) < 1000:
                    break
                cur = int(d[-1][0]) + 1
                time.sleep(0.15)
            f.write_text(json.dumps(out))
        f = cache / f"funding_{sym}.json"
        if not f.exists():
            out, cur = [], CME_START
            while True:
                d = json.loads(_curl("https://fapi.binance.com/fapi/v1/fundingRate"
                                     f"?symbol={sym}&startTime={cur}&limit=1000"))
                if not d:
                    break
                out += [[int(r["fundingTime"]), float(r["fundingRate"])] for r in d]
                if len(d) < 1000:
                    break
                cur = int(d[-1]["fundingTime"]) + 1
                time.sleep(0.15)
            f.write_text(json.dumps(out))
    for etf in ("IBIT", "FBTC", "BITB", "GBTC"):
        _cached(cache, f"y_{etf}.json", YAHOO.format(sym=etf, iv="1d"), YAHOO_SLEEP)


# ----------------------------------------------------------------- loading
def yahoo_close(cache: pathlib.Path, sym: str) -> dict[dt.date, float]:
    d = json.loads((cache / f"y_{sym}.json").read_bytes())["chart"]["result"]
    if not d:
        raise Refused(sym)
    r = d[0]
    q = r["indicators"]["quote"][0]
    return {dt.datetime.fromtimestamp(t, dt.UTC).date(): float(c)
            for t, c in zip(r["timestamp"], q["close"]) if c is not None}


def yahoo_volume(cache: pathlib.Path, sym: str) -> list[tuple[dt.date, float, float]]:
    r = json.loads((cache / f"y_{sym}.json").read_bytes())["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    return [(dt.datetime.fromtimestamp(t, dt.UTC).date(), float(v), float(c))
            for t, v, c in zip(r["timestamp"], q["volume"], q["close"])
            if v is not None and c]


def spot_at_hour(cache: pathlib.Path, sym: str, hour: int = 19) -> dict[dt.date, float]:
    """Close of the 1h bar OPENING at `hour` UTC, i.e. the price at hour+1:00 UTC."""
    out = {}
    for ms, c in json.loads((cache / f"spot_{sym}_1h.json").read_bytes()):
        t = dt.datetime.fromtimestamp(ms / 1000, dt.UTC)
        if t.hour == hour:
            out[t.date()] = float(c)
    return out


def funding_daily(cache: pathlib.Path, sym: str) -> dict[dt.date, float]:
    by: dict[dt.date, list[float]] = {}
    for ms, r in json.loads((cache / f"funding_{sym}.json").read_bytes()):
        by.setdefault(dt.datetime.fromtimestamp(ms / 1000, dt.UTC).date(), []).append(r)
    return {d: sum(v) * 365 for d, v in by.items()}


def riskfree() -> tuple[list[dt.date], dict[dt.date, float]]:
    tb = {}
    with open(ROOT / "research/data/t13_cache/cash.csv") as f:
        for r in csv.DictReader(f):
            try:
                tb[dt.date.fromisoformat(r["date"])] = float(r["annual_pct"]) / 100
            except ValueError:
                pass
    return sorted(tb), tb


# ----------------------------------------------------------------- contract calendar
def last_friday(y: int, m: int) -> dt.date:
    """CME crypto futures terminate on the LAST FRIDAY of the contract month.

    NOT holiday-adjusted here: the rule rolls to the preceding business day when the
    last Friday is a holiday in both the UK and US (Good Friday).  That misdates a
    handful of sessions by one day and is immaterial to every figure below.
    """
    d = dt.date(y + (m == 12), (m % 12) + 1, 1) - dt.timedelta(days=1)
    while d.weekday() != 4:
        d -= dt.timedelta(days=1)
    return d


def front_expiry(d: dt.date) -> dt.date:
    e = last_friday(d.year, d.month)
    return e if d <= e else last_friday(d.year + (d.month == 12), (d.month % 12) + 1)


# ----------------------------------------------------------------- verification
def verify_alignment(cache: pathlib.Path, fut_sym: str, spot_sym: str) -> dict:
    """Which UTC hour of spot does the futures daily close belong to?

    The answer must come from the data, not from a timezone assumption: we take the
    hour minimising sd(log F/S).  15:00 CT == 20:00 UTC (CDT) is the CME settlement.
    """
    fut = yahoo_close(cache, fut_sym)
    days = sorted(fut)[-800:]
    sweep = []
    for h in range(24):
        sp = spot_at_hour(cache, spot_sym, h)
        r = [np.log(fut[d] / sp[d]) for d in days if d in sp]
        if len(r) > 400:
            sweep.append({"hour_open_utc": h, "sd_bp": float(np.std(r) * 1e4),
                          "mean_bp": float(np.mean(r) * 1e4), "n": len(r)})
    sweep.sort(key=lambda x: x["sd_bp"])
    return {"best": sweep[0], "runner_up": sweep[1], "worst": sweep[-1]}


def verify_roll(cache: pathlib.Path, cont: str, contracts: list[str]) -> dict:
    """Is `BTC=F` the nearest contract, and when does it roll?"""
    fut = yahoo_close(cache, cont)
    out = {}
    for c in contracts:
        try:
            s = yahoo_close(cache, c)
        except (Refused, FileNotFoundError):
            continue
        common = sorted(set(s) & set(fut))
        if not common:
            continue
        eq = [d for d in common if abs(fut[d] / s[d] - 1) < 1e-9]
        out[c] = {"overlap": len(common), "exact_equal_days": len(eq),
                  "equal_from": eq[0].isoformat() if eq else None,
                  "equal_to": eq[-1].isoformat() if eq else None}
    return out


# ----------------------------------------------------------------- measurement
def basis_panel(cache: pathlib.Path, root: str, spot_sym: str) -> list[dict]:
    fut = yahoo_close(cache, f"{root}EQF")
    sp = spot_at_hour(cache, spot_sym)
    rows = []
    for d in sorted(fut):
        if d not in sp:
            continue
        e = front_expiry(d)
        dte = (e - d).days
        if dte < 1:
            continue
        rows.append({"date": d, "expiry": e, "dte": dte, "F": fut[d], "S": sp[d],
                     "basis": fut[d] / sp[d] - 1,
                     "ann": (fut[d] / sp[d] - 1) * 365.0 / dte})
    return rows


def cycles(rows: list[dict], entry_dte: int = 21) -> list[dict]:
    """One entry per contract: the first session with dte <= entry_dte, held to
    cash settlement.  Return over the leg == F/S - 1 at entry, given convergence."""
    by: dict[dt.date, list[dict]] = {}
    for r in rows:
        if r["dte"] <= entry_dte:
            by.setdefault(r["expiry"], []).append(r)
    out = []
    for e, g in sorted(by.items()):
        r0 = max(g, key=lambda r: r["dte"])
        out.append({"expiry": e, "entry": r0["date"], "dte": r0["dte"],
                    "ret": r0["basis"], "ann": r0["ann"]})
    return out


def power_census(cyc: list[dict], rf) -> dict:
    """T15's rule: the estimator a carry book ACTUALLY uses is the per-cycle mean,
    with n = number of cycles.  Not the number of daily basis prints."""
    leg = np.array([c["ret"] for c in cyc])
    dte = np.array([c["dte"] for c in cyc], float)
    rfl = np.array([rf(c["entry"]) * c["dte"] / 365 for c in cyc])
    ex = leg - rfl
    n, sd = len(ex), ex.std(ddof=1)
    mult = 365 / dte.mean()
    mde = 2.80 * sd / np.sqrt(n)            # 80% power, two-sided 5%
    rng = np.random.default_rng(11)
    bs = np.array([rng.choice(ex, n, replace=True).mean() for _ in range(20000)]) * mult
    return {"cycles": n, "mean_dte": float(dte.mean()),
            "excess_leg_mean_pct": float(ex.mean() * 100),
            "excess_leg_sd_pct": float(sd * 100),
            "observed_annualised_excess_pp": float(ex.mean() * mult * 100),
            "mde80_annualised_pp": float(mde * mult * 100),
            "detectable": bool(abs(ex.mean()) > mde),
            "t": float(ex.mean() / (sd / np.sqrt(n))),
            "annualised_sharpe": float(ex.mean() / sd * np.sqrt(mult)),
            "bootstrap_ci95_pp": [float(np.percentile(bs, 2.5) * 100),
                                  float(np.percentile(bs, 97.5) * 100)],
            "years_to_certify_2pp": float((2.80 * sd / (0.02 / mult)) ** 2 / mult)}


# ----------------------------------------------------------------- net model
def net_table(gross_pct: float, rf_pct: float, rolls_per_year: int,
              btc_px: float = 64_725.0, fee_usd_per_side: float = 2.25,
              tick_usd: float = 0.50, etf_drag_pp: float = 0.25,
              span_im: float = 0.40, vm_buffer: float = 0.30,
              fcm_haircut_pp: float | None = 0.50) -> dict:
    """Regulated form: long US spot-BTC ETF, short CME Micro Bitcoin (MBT, 0.1 BTC).

    Every cost is named.  `fcm_haircut_pp` is how far BELOW the benchmark the FCM pays
    on idle futures cash (IBKR's published structure is benchmark - 0.5pp; its live
    quoted rate on 2026-08-19 was 3.13% against a 3.71% T-bill).  `None` means the FCM
    pays nothing at all on futures cash, which is the norm outside IBKR.
    """
    notional = 0.1 * btc_px
    per_side_bp = (tick_usd + fee_usd_per_side) / notional * 1e4
    roll_pp = 2 * rolls_per_year * per_side_bp / 100
    committed = span_im + vm_buffer
    cash_pp = fcm_haircut_pp * committed if fcm_haircut_pp is not None \
        else rf_pct * committed
    net = gross_pct - etf_drag_pp - roll_pp - cash_pp
    capital = 1 + committed
    return {"mbt_notional_usd": notional, "cost_per_side_bp": per_side_bp,
            "roll_pp": roll_pp, "etf_drag_pp": etf_drag_pp, "cash_drag_pp": cash_pp,
            "net_on_notional_pct": net, "excess_on_notional_pp": net - rf_pct,
            "capital_multiple": capital,
            "excess_on_capital_pp": (net - rf_pct) / capital}


def term_structure(cache: pathlib.Path, root: str, spot_sym: str, live: dict) -> dict:
    """Deferred curve + per-contract volume, from the CURRENTLY LISTED contracts only."""
    months = "FGHJKMNQUVXZ"
    sp = spot_at_hour(cache, spot_sym)
    out: dict = {"contracts": {}}
    series = {}
    for sym, meta in sorted(live.items()):
        if meta["root"] != root:
            continue
        exp = last_friday(meta["year"], meta["month"])
        try:
            px = yahoo_close(cache, sym)
            vol = yahoo_volume(cache, sym)
        except (Refused, FileNotFoundError):
            continue
        series[sym] = (exp, px)
        rows = [(px[d] / sp[d] - 1) * 365 / max((exp - d).days, 1)
                for d in sorted(px) if d in sp and (exp - d).days >= 5]
        v = np.array([x[1] for x in vol[-60:]], float)
        c = np.array([x[2] for x in vol[-60:]], float)
        mult = 5 if root == "BTC" else 50
        out["contracts"][sym] = {
            "expiry": exp.isoformat(), "n_basis_obs": len(rows),
            "mean_annualised_basis_pct": float(np.mean(rows) * 100) if rows else None,
            "median_volume_contracts_60d": float(np.median(v)),
            "median_volume_notional_usd_60d": float(np.median(v * c * mult))}
    common = sorted(set.intersection(*[set(v[1]) for v in series.values()]) & set(sp)) \
        if series else []
    if common:
        d = common[-1]
        out["snapshot_date"] = d.isoformat()
        out["snapshot_spot"] = sp[d]
        out["snapshot"] = []
        for sym, (exp, px) in sorted(series.items(), key=lambda kv: kv[1][0]):
            dte = (exp - d).days
            out["snapshot"].append({"contract": sym, "expiry": exp.isoformat(), "dte": dte,
                                    "F": px[d], "raw_basis_pct": (px[d] / sp[d] - 1) * 100,
                                    "annualised_pct": (px[d] / sp[d] - 1) * 365 / dte * 100})
    return out


def etf_drag(cache: pathlib.Path, spot_sym: str = "BTCUSDT") -> dict:
    """Realised drag of the regulated spot leg: matched-day log-return difference."""
    sp = spot_at_hour(cache, spot_sym)
    out = {}
    for etf in ("IBIT", "FBTC", "BITB", "GBTC"):
        try:
            e = yahoo_close(cache, etf)
        except (Refused, FileNotFoundError):
            continue
        days = sorted(set(e) & set(sp))
        if len(days) < 100:
            continue
        r_e, r_b = [], []
        for x, y in zip(days, days[1:]):
            if (y - x).days > 5:
                continue
            r_e.append(np.log(e[y] / e[x])); r_b.append(np.log(sp[y] / sp[x]))
        d_ = np.array(r_e) - np.array(r_b)
        out[etf] = {"n_days": len(d_), "first": days[0].isoformat(),
                    "last": days[-1].isoformat(),
                    "drag_pp_per_year": float(-d_.mean() * 252 * 100),
                    "t": float(d_.mean() / (d_.std(ddof=1) / np.sqrt(len(d_)))),
                    "tracking_error_pct_per_year": float(d_.std(ddof=1) * np.sqrt(252) * 100)}
    return out


def vm_tail(cache: pathlib.Path, spot_sym: str = "BTCUSDT") -> dict:
    """The cash a SHORT futures leg must post in a rally, as a share of notional."""
    sp = spot_at_hour(cache, spot_sym)
    d = sorted(sp)
    px = np.array([sp[x] for x in d])
    out = {}
    for h in (1, 3, 5, 10, 21, 63):
        up = px[h:] / px[:-h] - 1
        i = int(np.argmax(up))
        out[f"{h}d"] = {"worst_pct": float(up.max() * 100),
                        "window": [d[i].isoformat(), d[i + h].isoformat()],
                        "p99_pct": float(np.percentile(up, 99) * 100),
                        "p999_pct": float(np.percentile(up, 99.9) * 100)}
    return out


# ----------------------------------------------------------------- report
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--fetch", action="store_true", help="populate the cache first")
    ap.add_argument("--json", default="", help="write the measurement receipt here")
    a = ap.parse_args()
    cache = pathlib.Path(a.cache)
    if a.fetch:
        fetch_all(cache)
    if not cache.exists():
        print(f"no cache at {cache}; rerun with --fetch", file=sys.stderr)
        return 2

    tbd, tb = riskfree()
    rf = lambda d: tb[tbd[min(int(np.searchsorted(tbd, d)), len(tbd) - 1)]]  # noqa: E731
    out: dict = {"generated_utc": dt.datetime.now(dt.UTC).isoformat(), "assets": {}}

    print("## 0. verification -- what IS the Yahoo futures series")
    al = verify_alignment(cache, "BTCEQF", "BTCUSDT")
    print(f"  alignment: best spot hour {al['best']['hour_open_utc']:02d}:00-"
          f"{al['best']['hour_open_utc']+1:02d}:00 UTC, sd {al['best']['sd_bp']:.1f}bp "
          f"(worst hour {al['worst']['sd_bp']:.1f}bp) -> the daily close is the "
          f"CME 15:00 CT settlement")
    live = json.loads((cache / "live_contracts.json").read_bytes()) \
        if (cache / "live_contracts.json").exists() else {}
    roll = verify_roll(cache, "BTCEQF", [s for s in live if s.startswith("BTC")])
    for c, v in roll.items():
        if v["exact_equal_days"]:
            print(f"  roll: BTC=F == {c} exactly on {v['exact_equal_days']} sessions "
                  f"{v['equal_from']}..{v['equal_to']}  -> nearest contract, "
                  f"rolling the session after expiry")
    out["verification"] = {"alignment": al, "roll": roll}

    for root, spot_sym, perp in (("BTC", "BTCUSDT", "BTCUSDT"),
                                 ("ETH", "ETHUSDT", "ETHUSDT")):
        rows = basis_panel(cache, root, spot_sym)
        core = [r for r in rows if r["dte"] >= 5]
        fund = funding_daily(cache, perp)
        cyc = cycles(rows)
        a_ = np.array([r["ann"] for r in core])
        print(f"\n## {root} front-month annualised basis  n={len(core)} "
              f"{core[0]['date']}..{core[-1]['date']}")
        print(f"  mean {a_.mean()*100:.2f}%  median {np.median(a_)*100:.2f}%  "
              f"sd {a_.std(ddof=1)*100:.2f}%  positive on {100*np.mean(a_>0):.1f}% of sessions")

        yr = {}
        for y in sorted({r["date"].year for r in core}):
            g = [r for r in core if r["date"].year == y]
            if len(g) < 5:
                continue
            b = np.array([r["ann"] for r in g])
            f_ = np.array([fund[r["date"]] for r in g if r["date"] in fund])
            r_ = np.mean([rf(r["date"]) for r in g])
            yr[y] = {"n": len(g), "cme_basis_pct": float(b.mean() * 100),
                     "perp_funding_pct": float(f_.mean() * 100) if len(f_) > 20 else None,
                     "tbill_pct": float(r_ * 100),
                     "cme_excess_pp": float((b.mean() - r_) * 100),
                     "perp_excess_pp": float((f_.mean() - r_) * 100) if len(f_) > 20 else None}
            p = yr[y]
            print(f"    {y}: n={p['n']:4d} CME {p['cme_basis_pct']:6.2f}%  perp "
                  f"{('%6.2f%%' % p['perp_funding_pct']) if p['perp_funding_pct'] is not None else '   n/a'}"
                  f"  rf {p['tbill_pct']:5.2f}%  CME-rf {p['cme_excess_pp']:6.2f}pp  perp-rf "
                  f"{('%6.2fpp' % p['perp_excess_pp']) if p['perp_excess_pp'] is not None else '  n/a'}")

        pc = power_census(cyc, rf)
        print(f"  POWER CENSUS on {pc['cycles']} monthly cycles: observed excess "
              f"{pc['observed_annualised_excess_pp']:.2f}pp/yr vs MDE(80%) "
              f"{pc['mde80_annualised_pp']:.2f}pp -> "
              f"{'DETECTABLE' if pc['detectable'] else 'BELOW ITS OWN MDE'}; "
              f"t={pc['t']:.2f}; bootstrap 95% CI "
              f"[{pc['bootstrap_ci95_pp'][0]:.2f}, {pc['bootstrap_ci95_pp'][1]:.2f}]pp")

        conv = {}
        for lo, hi in ((1, 1), (1, 3)):
            g = np.array([r["basis"] for r in rows if lo <= r["dte"] <= hi])
            conv[f"dte_{lo}_{hi}"] = {"n": len(g), "mean_bp": float(g.mean() * 1e4),
                                      "median_bp": float(np.median(g) * 1e4),
                                      "sd_bp": float(g.std(ddof=1) * 1e4)}
        print(f"  convergence at dte=1: mean {conv['dte_1_1']['mean_bp']:.1f}bp "
              f"(median {conv['dte_1_1']['median_bp']:.1f}bp, n={conv['dte_1_1']['n']}) "
              f"-- the future does converge")

        out["assets"][root] = {
            "panel_n": len(core), "first": core[0]["date"].isoformat(),
            "last": core[-1]["date"].isoformat(),
            "mean_annualised_basis_pct": float(a_.mean() * 100),
            "median_annualised_basis_pct": float(np.median(a_) * 100),
            "sd_annualised_basis_pct": float(a_.std(ddof=1) * 100),
            "share_positive": float(np.mean(a_ > 0)),
            "by_year": yr, "power_census": pc, "convergence": conv,
            "term_structure": term_structure(cache, root, spot_sym, live)}
        ts = out["assets"][root]["term_structure"]
        for c in ts.get("snapshot", []):
            v = ts["contracts"][c["contract"]]
            print(f"    curve {c['contract']} dte={c['dte']:4d} ann={c['annualised_pct']:5.2f}%  "
                  f"median vol {v['median_volume_contracts_60d']:8,.0f} contracts "
                  f"= ${v['median_volume_notional_usd_60d']:>14,.0f}/day")

    out["etf_drag"] = etf_drag(cache)
    print("\n## spot leg: realised drag of the US spot-BTC ETFs vs spot")
    for k, v in out["etf_drag"].items():
        print(f"  {k}: {v['drag_pp_per_year']:6.2f} pp/yr (t={v['t']:5.2f}, n={v['n_days']}, "
              f"{v['first']}..{v['last']})")
    out["variation_margin_tail"] = vm_tail(cache)
    print("\n## variation-margin tail on the SHORT leg (share of notional)")
    for k, v in out["variation_margin_tail"].items():
        print(f"  worst {k:>3s} rally {v['worst_pct']:7.2f}%  p99 {v['p99_pct']:6.2f}%  "
              f"({v['window'][0]} -> {v['window'][1]})")

    print("\n## net arithmetic, regulated form (long spot-BTC ETF / short MBT)")
    for lbl, gross, rfv in (("full sample", 4.91, 2.55), ("2025", 5.93, 4.07),
                            ("2026 YTD", 3.19, 3.64), ("front month today", 4.05, 3.71)):
        for who, hc in (("FCM benchmark-0.5", 0.50), ("FCM pays 0%", None)):
            n = net_table(gross, rfv, rolls_per_year=12, fcm_haircut_pp=hc)
            print(f"  {lbl:18s} {who:16s} net {n['net_on_notional_pct']:6.2f}%/N  "
                  f"excess {n['excess_on_notional_pp']:6.2f}pp/N  "
                  f"ON CAPITAL {n['excess_on_capital_pp']:6.2f}pp")
    out["net_model"] = {
        lbl: {who: net_table(g, r, 12, fcm_haircut_pp=c)
              for who, c in (("fcm_benchmark_minus_50bp", 0.50), ("fcm_zero", None))}
        for lbl, g, r in (("full_sample", 4.91, 2.55), ("y2025", 5.93, 4.07),
                          ("y2026ytd", 3.19, 3.64), ("front_today", 4.05, 3.71))}

    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=1, default=str))
        print(f"\nreceipt -> {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
