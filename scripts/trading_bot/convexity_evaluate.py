#!/usr/bin/env python3
"""Mechanical evaluator for CONVEXITY_PREREGISTRATION.md (T31 Deribit + T33 Alpaca forward panels).

Written and sha256-pinned 2026-08-26 15:00 CEST (task T36, CHUNK B durable tick) on day 3 of T31
and day 1 of T33, with ZERO rows read from either forward panel.  The point of this file is that
on 2026-12-23 the verdict is produced MECHANICALLY: nobody chooses a threshold, a window, a leg
or an underlying set after seeing quotes.  The script was developed and tested ONLY against
synthetic panels it generates itself (`--selftest`); the real panels are opened for the first
time by `--evaluate` on or after the pinned reading date.

Frozen rules implemented here (section numbers are CONVEXITY_PREREGISTRATION.md's):

  §2  data windows, T31 day-0 (2026-08-24) and the T33 2026-08-25 partial EXCLUDED (only files
      under snapshots/ with a `clean` ledger entry inside the window are read), T33 per-underlying
      eligibility = fresh_ok on >= 95 % of the first 30 clean trading days, missing-expiry-day
      trades DROPPED, > 10 % dropped => UNDECIDED.
  §3  instrument: nearest listed expiry with 3 <= DTE <= 10; call delta nearest +0.15 and put
      delta nearest -0.15, tolerance +-0.07, both two-sided and stamped on the capture date;
      buy at ask; fees (Deribit 0.0003*index per contract capped at 12.5 % of premium per leg;
      US $0.05/contract); held to expiry; settled at the delivery print (T31) / intrinsic at the
      expiry-day 15:45 ET underlying_price (T33); r = (payoff - P) / P; cluster = (underlying,
      expiry); equal premium weight.
  §4  D1 IV/RV20 <= 0.90; D2 |last return| >= 2.5 x sd(prior 20 returns); D3 ATM IV <= 20th pct
      of trailing 40 snapshots (>= 20 available); C0 unconditional control.  No grid.
  §6  ALIVE iff N >= 40 clusters AND dropped <= 10 % AND mean r > 0 with cluster-robust t >= 2.5
      AND mean r > 99th pct of 1,000 size-matched random-entry placebo draws AND largest positive
      cluster <= 40 % of positive cluster P&L AND no single universe at t <= -2.0.  Otherwise
      UNDECIDED (N_min / drop / concentration / sign-agreement failures) or DEAD (bar failures
      with N_min met).  Verdict written once per reading to CONVEXITY_VERDICT_<date>.json.
  §7  readings: first opens 2026-12-23 (T31 2026-08-25..2026-12-22, T33 2026-08-26..2026-12-22);
      second opens 2027-04-22 (both 2026-12-23..2027-04-21).  No third.

Mechanical resolutions of ambiguities the prose left open (recorded in Amendment A1 of the doc,
none of them a threshold, a design or a date):
  * DTE is the integer calendar-date difference (expiry date - snapshot date) in both universes.
  * ATM IV for D1/D3 = served IV of the call with served delta nearest +0.5 on the chosen expiry;
    if no call on that expiry carries a served delta, the call whose strike is nearest the spot.
    T31 mark_iv is in percent and is divided by 100; T33 iv is a decimal.  IV > 3 is treated as
    percent in either layout.
  * Spot series: T33 = the snapshot's underlying_price; T31 = median index_price of the currency's
    rows (fallback: underlying_price of the nearest expiry).  Realised vol annualises with 252
    (T33, trading days) and 365 (T31, calendar days).
  * D2 on T31 is not evaluated at a snapshot whose predecessor is > 3 calendar days earlier (the
    "last snapshot" return would span several days).  D1/D3 count snapshots regardless of gaps.
  * Burn-in: D1/D2 need >= 20 prior snapshots (D2: 20 prior returns => index >= 21); D3 needs
    >= 40 prior snapshots and >= 20 non-missing ATM IVs inside that window.
  * A trade whose expiry falls AFTER the reading's panel end is "unsettled at reading": it is
    neither counted nor dropped (it belongs to no reading).  Trades whose expiry is inside the
    window but whose settlement print / expiry-day snapshot is absent are DROPPED (§2).
  * Placebo draws sample C0 CLUSTERS without replacement, restricted to the design's underlying
    set, k = the design's cluster count, RNG seed 20261223, 1,000 draws, fixed.
  * T33 fees are charged per contract on entry only; Deribit's fee is charged per leg on entry
    only (no delivery fee), exactly as §3 states.

Usage:
  convexity_evaluate.py --selftest                 synthetic panels only; writes nothing under research/
  convexity_evaluate.py --plan [--reading first]   ledger/manifest dates and counts only; opens no snapshot
  convexity_evaluate.py --evaluate --reading first  refuses before the reading date and on pin drift

Research only.  No network.  No orders.  Never touches the t4 path.
"""
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import sys
import tempfile

import numpy as np

np.seterr(all="ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RT = os.path.join(ROOT, "research", "trading_bot")
T31_DIR = os.path.join(ROOT, "research", "data", "deribit_forward")
T33_DIR = os.path.join(ROOT, "research", "data", "us_options_forward")
SHAFILE = os.path.join(RT, "CONVEXITY_PREREGISTRATION.sha256")
PINNED = ("research/trading_bot/CONVEXITY_PREREGISTRATION.md",
          "scripts/trading_bot/convexity_design_costing.py",
          "research/trading_bot/CONVEXITY_DESIGN_COSTING.json",
          "scripts/trading_bot/convexity_evaluate.py")

READINGS = {
    "first": {"open": "2026-12-23", "t31": ("2026-08-25", "2026-12-22"), "t33": ("2026-08-26", "2026-12-22")},
    "second": {"open": "2027-04-22", "t31": ("2026-12-23", "2027-04-21"), "t33": ("2026-12-23", "2027-04-21")},
}
T33_UNIVERSE = ["SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "XLE", "XLF",
                "NVDA", "TSLA", "AAPL", "AMZN", "MSFT", "AMD"]
T31_UNIVERSE = ["BTC", "ETH"]

# ---- frozen constants (CONVEXITY_PREREGISTRATION.md) --------------------------------------
DELTA_TARGET, DELTA_TOL = 0.15, 0.07
DTE_MIN, DTE_MAX = 3, 10
D1_RATIO, D1_WIN = 0.90, 20
D2_MULT, D2_WIN = 2.5, 20
D3_PCT, D3_WIN, D3_MIN_AVAIL = 20, 40, 20
T_BAR = 2.5
PLACEBO_DRAWS, PLACEBO_PCT, PLACEBO_SEED = 1000, 99, 20261223
CONC_MAX = 0.40
N_MIN_CLUSTERS = 40
DROP_MAX = 0.10
SIGN_T = -2.0
DERIBIT_FEE, DERIBIT_CAP = 0.0003, 0.125
US_FEE, US_MULT = 0.05, 100.0
FRESH_ELIG, ELIG_DAYS = 0.95, 30
T31_GAP_MAX_DAYS = 3
ANN = {"t31": 365.0, "t33": 252.0}
DESIGNS = ("D1", "D2", "D3")


# ---- helpers ------------------------------------------------------------------------------
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fnum(v):
    try:
        if v is None or v == "":
            return None
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path) as fh:
        return json.load(fh)


def read_csv_gz(path):
    with gzip.open(path, "rt", newline="") as fh:
        return list(csv.DictReader(fh))


def norm_iv(v):
    x = fnum(v)
    if x is None or x <= 0:
        return None
    return x / 100.0 if x > 3.0 else x


def d_iso(d):
    return d.isoformat()


def parse_date(s):
    return dt.date.fromisoformat(str(s)[:10])


# ---- panel loading (real or synthetic; identical code path) --------------------------------
def clean_dates(base, start, end):
    ledger = load_json(os.path.join(base, "ledger.json"), {"days": {}})
    manifest = load_json(os.path.join(base, "manifest.json"), {})
    out = []
    for date, day in sorted(ledger.get("days", {}).items()):
        if day.get("status") != "clean" or date not in manifest:
            continue
        if start <= date <= end and os.path.exists(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % date)):
            out.append(date)
    return out, ledger, manifest


def t33_eligibility(base):
    """Underlyings with fresh_ok on >= 95 % of the first 30 clean trading days (all clean days if < 30)."""
    ledger = load_json(os.path.join(base, "ledger.json"), {"days": {}})
    manifest = load_json(os.path.join(base, "manifest.json"), {})
    days = [d for d, x in sorted(ledger.get("days", {}).items()) if x.get("status") == "clean" and d in manifest]
    gate = days[:ELIG_DAYS]
    tally = {}
    for d in gate:
        for und, st in (manifest[d].get("per_underlying") or {}).items():
            ok = st.get("fresh_ok")
            if ok is None:
                ff = fnum(st.get("fresh_frac"))
                ok = ff is None or ff >= 0.70
            tally.setdefault(und, [0, 0])
            tally[und][0] += 1 if ok else 0
            tally[und][1] += 1
    elig = {}
    for und in T33_UNIVERSE:
        ok, n = tally.get(und, [0, 0])
        elig[und] = {"fresh_ok_days": ok, "gate_days": n, "eligible": bool(n > 0 and ok / n >= FRESH_ELIG)}
    return elig, len(gate)


def load_t33(base, start, end, universe):
    """-> {und: [snapshot dict ...]} sorted by date; opens ONLY clean in-window snapshot files."""
    dates, _, _ = clean_dates(base, start, end)
    panel = {u: [] for u in universe}
    for date in dates:
        rows = read_csv_gz(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % date))
        by_und = {}
        for r in rows:
            u = r.get("underlying")
            if u in panel:
                by_und.setdefault(u, []).append(r)
        for u, rr in by_und.items():
            spot = fnum(rr[0].get("underlying_price"))
            chain = []
            sd = parse_date(date)
            for r in rr:
                b, a = fnum(r.get("bid")), fnum(r.get("ask"))
                exp = str(r.get("expiration"))[:10]
                try:
                    dte = (parse_date(exp) - sd).days
                except ValueError:
                    continue
                fresh = str(r.get("quote_ts") or "").startswith(date)
                chain.append({"exp": exp, "dte": dte, "type": str(r.get("type", "")).lower()[:1],
                              "strike": fnum(r.get("strike")), "bid": b, "ask": a,
                              "delta": fnum(r.get("delta")), "iv": norm_iv(r.get("iv")),
                              "two_sided": bool(b and a and b > 0 and a > 0 and a >= b and fresh)})
            panel[u].append({"date": date, "spot": spot, "chain": chain, "universe": "t33"})
    return panel


def load_t31(base, start, end, universe):
    dates, _, _ = clean_dates(base, start, end)
    panel = {u: [] for u in universe}
    for date in dates:
        rows = read_csv_gz(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % date))
        by_cur = {}
        for r in rows:
            cur = str(r.get("symbol", "")).split("-")[0]
            if cur in panel:
                by_cur.setdefault(cur, []).append(r)
        sd = parse_date(date)
        for cur, rr in by_cur.items():
            idx = [fnum(r.get("index_price")) for r in rr]
            idx = [x for x in idx if x]
            chain, near_und = [], None
            for r in rr:
                exp_us = fnum(r.get("expiration"))
                if exp_us is None:
                    continue
                exp_d = dt.datetime.fromtimestamp(exp_us / 1e6, tz=dt.timezone.utc).date()
                dte = (exp_d - sd).days
                b, a = fnum(r.get("bid_price")), fnum(r.get("ask_price"))
                chain.append({"exp": d_iso(exp_d), "dte": dte, "type": str(r.get("type", "")).lower()[:1],
                              "strike": fnum(r.get("strike_price")), "bid": b, "ask": a,
                              "delta": fnum(r.get("delta")), "iv": norm_iv(r.get("mark_iv")),
                              "und_px": fnum(r.get("underlying_price")),
                              "two_sided": bool(b and a and b > 0 and a > 0 and a >= b)})
                if dte >= 0 and (near_und is None or dte < near_und[0]) and fnum(r.get("underlying_price")):
                    near_und = (dte, fnum(r.get("underlying_price")))
            spot = float(np.median(idx)) if idx else (near_und[1] if near_und else None)
            panel[cur].append({"date": date, "spot": spot, "chain": chain, "universe": "t31"})
    return panel


# ---- instrument (§3) ------------------------------------------------------------------------
def choose_expiry(chain):
    cands = sorted({c["exp"]: c["dte"] for c in chain if DTE_MIN <= c["dte"] <= DTE_MAX}.items(), key=lambda kv: kv[1])
    return cands[0][0] if cands else None


def pick_legs(chain, exp):
    calls = [c for c in chain if c["exp"] == exp and c["type"] == "c" and c["two_sided"] and c["delta"] is not None and c["delta"] > 0]
    puts = [c for c in chain if c["exp"] == exp and c["type"] == "p" and c["two_sided"] and c["delta"] is not None and c["delta"] < 0]
    if not calls or not puts:
        return None
    c = min(calls, key=lambda x: abs(x["delta"] - DELTA_TARGET))
    p = min(puts, key=lambda x: abs(-x["delta"] - DELTA_TARGET))
    if abs(c["delta"] - DELTA_TARGET) > DELTA_TOL or abs(-p["delta"] - DELTA_TARGET) > DELTA_TOL:
        return None
    if c["strike"] is None or p["strike"] is None:
        return None
    return c, p


def atm_iv(chain, exp, spot):
    calls = [c for c in chain if c["exp"] == exp and c["type"] == "c" and c["iv"] is not None]
    if not calls:
        return None
    with_delta = [c for c in calls if c["delta"] is not None]
    if with_delta:
        return min(with_delta, key=lambda x: abs(x["delta"] - 0.5))["iv"]
    if spot is None:
        return None
    ks = [c for c in calls if c["strike"] is not None]
    return min(ks, key=lambda x: abs(x["strike"] - spot))["iv"] if ks else None


def price_entry(universe, c, p, spot):
    """Premium paid P in USD per 1 contract of each leg, incl. fees, per §3."""
    if universe == "t31":
        if not spot:
            return None
        fee_c = min(DERIBIT_FEE, DERIBIT_CAP * c["ask"])
        fee_p = min(DERIBIT_FEE, DERIBIT_CAP * p["ask"])
        return (c["ask"] + fee_c + p["ask"] + fee_p) * spot
    return (c["ask"] + p["ask"]) * US_MULT + 2 * US_FEE


def payoff(universe, kc, kp, settle):
    intrinsic = max(settle - kc, 0.0) + max(kp - settle, 0.0)
    return intrinsic if universe == "t31" else intrinsic * US_MULT


# ---- trade book -----------------------------------------------------------------------------
def build_book(panel, universe, settle_fn, panel_end):
    """Return (trades, counters).  trades: list of dicts with r, cluster, und, universe, date, triggers."""
    ann = ANN[universe]
    trades, ctr = [], {"snapshots": 0, "no_expiry": 0, "no_legs": 0, "unsettled_at_reading": 0, "dropped_missing_settlement": 0}
    for und, snaps in panel.items():
        snaps = sorted(snaps, key=lambda s: s["date"])
        n = len(snaps)
        spots = np.array([s["spot"] if s["spot"] else np.nan for s in snaps], dtype=float)
        dates = [parse_date(s["date"]) for s in snaps]
        rets = np.full(n, np.nan)
        for i in range(1, n):
            if spots[i] > 0 and spots[i - 1] > 0:
                rets[i] = math.log(spots[i] / spots[i - 1])
        ivs = np.full(n, np.nan)
        exps = [None] * n
        for i, s in enumerate(snaps):
            exps[i] = choose_expiry(s["chain"])
            if exps[i]:
                v = atm_iv(s["chain"], exps[i], s["spot"])
                if v:
                    ivs[i] = v
        for i, s in enumerate(snaps):
            ctr["snapshots"] += 1
            exp = exps[i]
            if not exp:
                ctr["no_expiry"] += 1
                continue
            legs = pick_legs(s["chain"], exp)
            if not legs:
                ctr["no_legs"] += 1
                continue
            c, p = legs
            P = price_entry(universe, c, p, s["spot"])
            if not P or P <= 0:
                ctr["no_legs"] += 1
                continue
            # triggers, information at or before snapshot i only
            trig = {"C0": True, "D1": False, "D2": False, "D3": False}
            if i >= D1_WIN:
                w = rets[i - D1_WIN + 1:i + 1]
                if np.isfinite(w).all() and np.isfinite(ivs[i]):
                    rv = float(np.std(w, ddof=1)) * math.sqrt(ann)
                    trig["D1"] = rv > 0 and ivs[i] / rv <= D1_RATIO
            if i >= D2_WIN + 1:
                prior = rets[i - D2_WIN:i]
                gap_ok = universe != "t31" or (dates[i] - dates[i - 1]).days <= T31_GAP_MAX_DAYS
                if gap_ok and np.isfinite(prior).all() and np.isfinite(rets[i]):
                    sd = float(np.std(prior, ddof=1))
                    trig["D2"] = sd > 0 and abs(rets[i]) >= D2_MULT * sd
            if i >= D3_WIN:
                w = ivs[i - D3_WIN:i]
                w = w[np.isfinite(w)]
                if len(w) >= D3_MIN_AVAIL and np.isfinite(ivs[i]):
                    trig["D3"] = ivs[i] <= float(np.percentile(w, D3_PCT))
            if exp > panel_end:
                ctr["unsettled_at_reading"] += 1
                continue
            settle = settle_fn(und, exp)
            rec = {"und": und, "universe": universe, "date": s["date"], "exp": exp, "cluster": "%s|%s" % (und, exp),
                   "kc": c["strike"], "kp": p["strike"], "P": P, "trig": trig}
            if settle is None:
                ctr["dropped_missing_settlement"] += 1
                rec["r"] = None
            else:
                rec["r"] = (payoff(universe, c["strike"], p["strike"], settle) - P) / P
            trades.append(rec)
    return trades, ctr


# ---- statistics (§6) ------------------------------------------------------------------------
def cluster_stats(trades):
    r = np.array([t["r"] for t in trades], dtype=float)
    n = len(r)
    if n == 0:
        return {"n": 0, "clusters": 0, "mean": None, "t": None, "win": None, "p95": None, "conc": None}
    mean = float(r.mean())
    cl = {}
    for t in trades:
        cl.setdefault(t["cluster"], []).append(t["r"])
    s = sum((sum(v) - len(v) * mean) ** 2 for v in cl.values())
    se = math.sqrt(s) / n if s > 0 else 0.0
    tstat = mean / se if se > 0 else (float("inf") if mean > 0 else float("-inf") if mean < 0 else 0.0)
    pos = sorted((sum(v) for v in cl.values() if sum(v) > 0), reverse=True)
    conc = (pos[0] / sum(pos)) if pos else 0.0
    return {"n": n, "clusters": len(cl), "mean": mean, "t": float(tstat), "win": float((r > 0).mean()),
            "p95": float(np.percentile(r, 95)), "conc": float(conc)}


def placebo(c0_trades, design_trades, seed=PLACEBO_SEED, draws=PLACEBO_DRAWS):
    unds = {t["und"] for t in design_trades}
    k = len({t["cluster"] for t in design_trades})
    cl = {}
    for t in c0_trades:
        if t["und"] in unds:
            cl.setdefault(t["cluster"], []).append(t["r"])
    keys = sorted(cl)
    if k == 0 or len(keys) < k:
        return None
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    arrs = [np.array(cl[key]) for key in keys]
    for d in range(draws):
        pick = rng.choice(len(keys), size=k, replace=False)
        vals = np.concatenate([arrs[j] for j in pick])
        means[d] = vals.mean()
    return {"p99": float(np.percentile(means, PLACEBO_PCT)), "median": float(np.median(means)),
            "draws": draws, "k_clusters": k, "pool_clusters": len(keys)}


def verdict_for(design, settled, dropped_n, c0_settled):
    st = cluster_stats(settled)
    per_u = {}
    for u in ("t31", "t33"):
        sub = [t for t in settled if t["universe"] == u]
        if sub:
            per_u[u] = cluster_stats(sub)
    total = len(settled) + dropped_n
    drop_frac = dropped_n / total if total else 0.0
    out = {"design": design, "stats": st, "per_universe": per_u, "dropped": dropped_n, "drop_frac": drop_frac,
           "placebo": None, "checks": {}, "verdict": None, "reason": None}
    if st["clusters"] < N_MIN_CLUSTERS or drop_frac > DROP_MAX:
        out["verdict"] = "UNDECIDED"
        out["reason"] = "N_min: %d clusters < %d" % (st["clusters"], N_MIN_CLUSTERS) if st["clusters"] < N_MIN_CLUSTERS \
            else "dropped %.1f%% > %d%%" % (100 * drop_frac, 100 * DROP_MAX)
        return out
    pl = placebo(c0_settled, settled)
    out["placebo"] = pl
    ck = out["checks"]
    ck["mean_pos_t"] = bool(st["mean"] > 0 and st["t"] >= T_BAR)
    ck["placebo"] = bool(pl is not None and st["mean"] > pl["p99"])
    ck["concentration"] = bool(st["conc"] <= CONC_MAX)
    ck["sign_agreement"] = not any(v["t"] is not None and v["t"] <= SIGN_T for v in per_u.values())
    if not (ck["mean_pos_t"] and ck["placebo"]):
        out["verdict"] = "DEAD"
        out["reason"] = "bar: mean %.4f t %.2f (need >0, >=%.1f); placebo p99 %s" % (
            st["mean"], st["t"], T_BAR, "%.4f" % pl["p99"] if pl else "n/a")
    elif not ck["concentration"]:
        out["verdict"] = "UNDECIDED"
        out["reason"] = "concentration %.2f > %.2f" % (st["conc"], CONC_MAX)
    elif not ck["sign_agreement"]:
        out["verdict"] = "UNDECIDED"
        out["reason"] = "one universe at t <= %.1f while pooled passes" % SIGN_T
    else:
        out["verdict"] = "ALIVE"
        out["reason"] = "all §6 conditions met"
    return out


def evaluate_panels(t31_panel, t33_panel, t31_settle, t33_settle, reading):
    R = READINGS[reading]
    books, counters = [], {}
    if t31_panel:
        b, c = build_book(t31_panel, "t31", t31_settle, R["t31"][1])
        books += b
        counters["t31"] = c
    if t33_panel:
        b, c = build_book(t33_panel, "t33", t33_settle, R["t33"][1])
        books += b
        counters["t33"] = c
    settled = [t for t in books if t["r"] is not None]
    c0 = settled
    result = {"reading": reading, "counters": counters, "n_trades_total": len(books), "n_settled": len(settled),
              "C0": {"stats": cluster_stats(c0), "per_universe": {u: cluster_stats([t for t in c0 if t["universe"] == u])
                                                                    for u in ("t31", "t33") if any(t["universe"] == u for t in c0)}},
              "designs": {}}
    for d in DESIGNS:
        ds = [t for t in settled if t["trig"][d]]
        dd = sum(1 for t in books if t["r"] is None and t["trig"][d])
        result["designs"][d] = verdict_for(d, ds, dd, c0)
    result["programme"] = {
        "all_dead_with_nmin": all(v["verdict"] == "DEAD" for v in result["designs"].values()),
        "any_alive": any(v["verdict"] == "ALIVE" for v in result["designs"].values()),
        "any_undecided": any(v["verdict"] == "UNDECIDED" for v in result["designs"].values()),
    }
    return result


def compact(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, dict):
        return {k: compact(x) for k, x in v.items()}
    if isinstance(v, list):
        return [compact(x) for x in v]
    return v


# ---- real-panel settlement sources ---------------------------------------------------------
def t31_settler(base):
    book = load_json(os.path.join(base, "delivery_prices.json"), {})

    def norm(book_idx):
        out = {}
        for k, v in book_idx.items():
            key = str(k)[:10]
            try:
                key = dt.date.fromisoformat(key).isoformat()
            except ValueError:
                try:
                    key = dt.datetime.strptime(str(k), "%d %b %y").date().isoformat()
                except ValueError:
                    continue
            out[key] = fnum(v)
        return out
    idx = {cur: norm(book.get("%s_usd" % cur.lower(), {})) for cur in T31_UNIVERSE}

    def settle(und, exp):
        return idx.get(und, {}).get(exp)
    return settle


def t33_settler(panel):
    spots = {}
    for und, snaps in panel.items():
        for s in snaps:
            if s["spot"]:
                spots[(und, s["date"])] = s["spot"]

    def settle(und, exp):
        return spots.get((und, exp))
    return settle


# ---- pins / gates -----------------------------------------------------------------------------
def read_pins():
    pins = {}
    with open(SHAFILE) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            h, p = line.split(None, 1)
            pins[p.strip()] = h
    return pins


def verify_pins():
    pins = read_pins()
    bad = []
    for rel in PINNED:
        want, have = pins.get(rel), sha256(os.path.join(ROOT, rel))
        if want != have:
            bad.append((rel, want, have))
    return bad


def cmd_plan(reading):
    R = READINGS[reading]
    for name, base in (("t31", T31_DIR), ("t33", T33_DIR)):
        dates, ledger, _ = clean_dates(base, *R[name])
        summ = ledger.get("summary", {})
        print("%s: window %s..%s  clean-in-window %d  ledger summary %s" % (
            name, R[name][0], R[name][1], len(dates), json.dumps(summ, sort_keys=True)))
    elig, n = t33_eligibility(T33_DIR)
    print("t33 eligibility tally over first %d clean days (rule fixes at %d): %s" % (
        n, ELIG_DAYS, ", ".join("%s=%d/%d%s" % (u, e["fresh_ok_days"], e["gate_days"], "" if e["eligible"] else "(X)") for u, e in elig.items())))
    print("opens %s; today %s; verdict file %s" % (R["open"], dt.date.today().isoformat(),
                                                   os.path.join(RT, "CONVEXITY_VERDICT_%s.json" % R["open"])))
    return 0


def cmd_evaluate(reading):
    R = READINGS[reading]
    today = dt.date.today()
    if today < parse_date(R["open"]):
        print("REFUSED: reading '%s' opens %s; today is %s. No forward-panel row is read before the gate." % (
            reading, R["open"], today.isoformat()))
        return 3
    bad = verify_pins()
    if bad:
        for rel, want, have in bad:
            print("PIN MISMATCH %s: pinned %s, on disk %s" % (rel, want, have))
        print("REFUSED: evaluator, pre-registration or costing artefacts drifted from the pinned hash.")
        return 4
    out_path = os.path.join(RT, "CONVEXITY_VERDICT_%s.json" % R["open"])
    if os.path.exists(out_path):
        print("REFUSED: %s exists; a reading is written once (§6: no re-reading)." % out_path)
        return 5
    elig, n_gate = t33_eligibility(T33_DIR)
    t33_unds = [u for u in T33_UNIVERSE if elig[u]["eligible"]]
    t31_panel = load_t31(T31_DIR, *R["t31"], universe=T31_UNIVERSE)
    t33_panel = load_t33(T33_DIR, *R["t33"], universe=t33_unds) if t33_unds else {}
    res = evaluate_panels(t31_panel, t33_panel, t31_settler(T31_DIR), t33_settler(t33_panel), reading)
    res["t33_eligibility"] = {"gate_days": n_gate, "eligible": t33_unds, "detail": elig}
    res["panels"] = {"t31": {"window": R["t31"], "clean_days": {u: len(v) for u, v in t31_panel.items()}},
                     "t33": {"window": R["t33"], "clean_days": {u: len(v) for u, v in t33_panel.items()}}}
    res["pins"] = {rel: sha256(os.path.join(ROOT, rel)) for rel in PINNED}
    res["written_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(out_path, "w") as fh:
        json.dump(compact(res), fh, indent=1, sort_keys=True)
    for d, v in res["designs"].items():
        st = v["stats"]
        print("%s: %s -- %s | n %d clusters %d mean %s t %s" % (
            d, v["verdict"], v["reason"], st["n"], st["clusters"],
            "%.4f" % st["mean"] if st["mean"] is not None else "n/a", "%.2f" % st["t"] if st["t"] is not None else "n/a"))
    print("programme: %s" % json.dumps(res["programme"]))
    print("verdict written: %s" % out_path)
    return 0


# ---- synthetic panels for --selftest (never touch research/) ---------------------------------
def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs(S, K, T, sigma, cp):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0) if cp == "c" else max(K - S, 0.0), (1.0 if (cp == "c" and S > K) else -1.0 if (cp == "p" and S < K) else 0.0)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if cp == "c":
        return S * _ncdf(d1) - K * _ncdf(d2), _ncdf(d1)
    return K * _ncdf(-d2) - S * _ncdf(-d1), _ncdf(d1) - 1.0


def synth_panels(tmp, seed, n_days=170, vol=0.30, iv_prem=1.50, half_spread=0.08, plant=None, t33_unds=None, t31_unds=None):
    """Write T31-like and T33-like directories under tmp with the real column layouts.

    plant: None | ("D2", p_jump, jump_sd) | ("single_cluster", und, exp_date)
      "D2": on shock days the underlying receives an extra +-jump at expiry with prob p_jump.
    Weekly expiries every Friday; snapshots every trading day (t33) / calendar day (t31, with a
    4-day hole once a month to exercise the gap rule).
    """
    rng = np.random.default_rng(seed)
    t33_unds = t33_unds or T33_UNIVERSE
    t31_unds = t31_unds or T31_UNIVERSE
    start = dt.date(2026, 8, 26)
    cal = []
    d = start
    while len(cal) < n_days:
        if d.weekday() < 5:
            cal.append(d)
        d += dt.timedelta(days=1)
    first_friday = next(x for x in cal if x.weekday() == 4)
    fridays = [first_friday + dt.timedelta(days=7 * k) for k in range(60)]
    shocks = {}   # (und, date) -> True when the day was a >=2.5 sd move (for the D2 plant)

    def sim_path(und, days, dvol, ann):
        S = [100.0 * (1 + 0.3 * rng.random())]
        for i in range(1, len(days)):
            dtm = (days[i] - days[i - 1]).days if ann == 365 else 1
            z = rng.standard_normal()
            r = dvol / math.sqrt(ann) * math.sqrt(dtm) * z
            S.append(S[-1] * math.exp(r))
        return np.array(S)

    def chain_rows(univ, und, day, S, ivs):
        rows = []
        for exp in fridays:
            dte = (exp - day).days
            if dte < 0 or dte > 21:
                continue
            T = max(dte, 0.3) / 365.0
            for k in np.arange(0.76, 1.245, 0.03):
                K = round(S * k, 2)
                for cp in ("c", "p"):
                    mid, delta = _bs(S, K, T, ivs, cp)
                    mid = max(mid, 0.01 * S / 100)
                    bid, ask = mid * (1 - half_spread), mid * (1 + half_spread)
                    if univ == "t33":
                        rows.append({"underlying": und, "symbol": "%s%s%s%08d" % (und, exp.strftime("%y%m%d"), cp.upper(), int(K * 1000)),
                                     "root": und, "expiration": exp.isoformat(), "dte": dte, "type": "call" if cp == "c" else "put",
                                     "strike": K, "bid": round(bid, 2), "bid_size": 10, "ask": round(ask, 2), "ask_size": 10,
                                     "quote_ts": day.isoformat() + "T19:45:00.000000000Z", "quote_cond": "",
                                     "last": "", "last_size": "", "last_ts": "", "iv": round(ivs, 4), "delta": round(delta, 4),
                                     "gamma": "", "theta": "", "vega": "", "rho": "", "day_open": "", "day_high": "", "day_low": "",
                                     "day_close": "", "day_volume": "", "underlying_price": round(S, 2),
                                     "underlying_ts": day.isoformat() + "T19:45:00Z", "captured_utc": day.isoformat() + "T19:45:30Z"})
                    else:
                        exp_us = int(dt.datetime(exp.year, exp.month, exp.day, 8, tzinfo=dt.timezone.utc).timestamp() * 1e6)
                        rows.append({"exchange": "deribit", "symbol": "%s-%s-%d-%s" % (und, exp.strftime("%-d%b%y").upper(), int(K), cp.upper()),
                                     "timestamp": exp_us, "local_timestamp": int(dt.datetime(day.year, day.month, day.day, 0, 15, tzinfo=dt.timezone.utc).timestamp() * 1e6),
                                     "type": "call" if cp == "c" else "put", "strike_price": K, "expiration": exp_us, "open_interest": 0,
                                     "last_price": "", "bid_price": round(bid / S, 6), "bid_amount": 1, "bid_iv": "", "ask_price": round(ask / S, 6),
                                     "ask_amount": 1, "ask_iv": "", "mark_price": round(mid / S, 6), "mark_iv": round(ivs * 100, 2),
                                     "underlying_index": "%s-%s" % (und, exp.strftime("%-d%b%y").upper()), "underlying_price": round(S, 2),
                                     "delta": round(delta, 4), "gamma": "", "vega": "", "theta": "", "rho": "",
                                     "source": "order_book", "volume": "", "volume_usd": "", "interest_rate": 0, "index_price": round(S, 2)})
        return rows

    for univ, unds, base in (("t33", t33_unds, os.path.join(tmp, "t33")), ("t31", t31_unds, os.path.join(tmp, "t31"))):
        os.makedirs(os.path.join(base, "snapshots"), exist_ok=True)
        if univ == "t33":
            days = cal
            snap_days = set(cal)
        else:
            days = []
            d = start
            while d <= cal[-1]:
                days.append(d)
                d += dt.timedelta(days=1)
            snap_days = {d for d in days if d.day not in (13, 14, 15)}   # monthly 3-day hole: exercises the gap rule
        ann = 252 if univ == "t33" else 365
        paths, ivs = {}, {}
        for und in unds:
            dvol = vol * (0.7 + 0.6 * rng.random())
            S = sim_path(und, days, dvol, ann)
            # planted D2 effect: after a shock day, the path jumps at the next weekly expiry
            if plant and plant[0] == "D2":
                rets = np.diff(np.log(S))
                for i in range(21, len(days)):
                    sd = np.std(rets[i - 21:i - 1], ddof=1)
                    if abs(rets[i - 1]) >= D2_MULT * sd and rng.random() < plant[1]:
                        exp = next((f for f in fridays if DTE_MIN <= (f - days[i]).days <= DTE_MAX), None)
                        if exp is not None:
                            j = next((k for k, dd in enumerate(days) if dd >= exp), None)
                            if j is not None:
                                S[j:] *= math.exp(plant[2] * (1 if rng.random() < 0.5 else -1))
            if plant and plant[0] == "single_cluster" and und == plant[1]:
                j = next((k for k, dd in enumerate(days) if dd >= plant[2]), None)
                if j is not None:
                    S[j:] *= math.exp(0.6)
            paths[und] = S
            # implied vol: premium over realised, with a slow sine wobble so D1/D3 fire sometimes
            ivs[und] = np.array([dvol * iv_prem * (1 + 0.25 * math.sin(i / 9.0)) for i in range(len(days))])
        ledger, manifest = {"days": {}}, {}
        delivery = {"btc_usd": {}, "eth_usd": {}}
        for i, day in enumerate(days):
            if univ == "t31":
                for und in unds:
                    delivery["%s_usd" % und.lower()][day.isoformat()] = round(float(paths[und][i]), 2)
            if day not in snap_days:
                continue
            rows = []
            for und in unds:
                rows += chain_rows(univ, und, day, float(paths[und][i]), float(ivs[und][i]))
            cols = list(rows[0].keys())
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
            with gzip.open(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % day.isoformat()), "wt") as fh:
                fh.write(buf.getvalue())
            ledger["days"][day.isoformat()] = {"attempts": 1, "status": "clean"}
            manifest[day.isoformat()] = {"rows": len(rows), "per_underlying": {u: {"fresh_ok": not (u == "HYG"), "fresh_frac": 0.6 if u == "HYG" else 0.9} for u in unds}}
        ledger["summary"] = {"days_clean": len(ledger["days"]), "days_attempted": len(ledger["days"])}
        with open(os.path.join(base, "ledger.json"), "w") as fh:
            json.dump(ledger, fh)
        with open(os.path.join(base, "manifest.json"), "w") as fh:
            json.dump(manifest, fh)
        if univ == "t31":
            with open(os.path.join(base, "delivery_prices.json"), "w") as fh:
                json.dump(delivery, fh)
    return cal[0].isoformat(), cal[-1].isoformat()


def run_synthetic(tmp, start, end, t33_unds):
    t31 = load_t31(os.path.join(tmp, "t31"), start, end, T31_UNIVERSE)
    t33 = load_t33(os.path.join(tmp, "t33"), start, end, t33_unds)
    R = {"open": end, "t31": (start, end), "t33": (start, end)}
    READINGS["selftest"] = R
    res = evaluate_panels(t31, t33, t31_settler(os.path.join(tmp, "t31")), t33_settler(t33), "selftest")
    del READINGS["selftest"]
    return res


def cmd_selftest():
    global T_BAR
    fails = []

    def check(cond, msg):
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            fails.append(msg)

    # 1. cluster-robust t against a hand computation
    tr = [{"r": r, "cluster": c, "und": "X", "universe": "t33"} for r, c in
          ((0.5, "a"), (0.3, "a"), (-0.2, "b"), (0.8, "c"), (-0.4, "d"), (0.1, "d"))]
    st = cluster_stats(tr)
    rs = np.array([0.5, 0.3, -0.2, 0.8, -0.4, 0.1])
    m = rs.mean()
    se = math.sqrt(((0.5 + 0.3 - 2 * m) ** 2 + (-0.2 - m) ** 2 + (0.8 - m) ** 2 + (-0.4 + 0.1 - 2 * m) ** 2)) / 6
    print("[1] cluster-robust t: got %.6f expected %.6f; conc %.3f" % (st["t"], m / se, st["conc"]))
    check(abs(st["t"] - m / se) < 1e-9, "cluster t matches hand formula")
    check(abs(st["conc"] - 0.8 / (0.8 + 0.8)) < 1e-9, "concentration = largest positive cluster / sum positive clusters")

    # 2. placebo determinism
    c0 = [{"r": float(np.sin(i)), "cluster": "u%d|e%d" % (i % 5, i // 5), "und": "u%d" % (i % 5), "universe": "t33"} for i in range(200)]
    des = c0[:30]
    p1, p2 = placebo(c0, des), placebo(c0, des)
    check(p1 == p2 and p1["draws"] == PLACEBO_DRAWS, "placebo deterministic under the fixed seed (%d draws)" % PLACEBO_DRAWS)

    with tempfile.TemporaryDirectory() as tmp:
        # 3. NULL panels: IV premium over realised => C0 negative, no design ALIVE
        for seed in (1, 2):
            sub = os.path.join(tmp, "null%d" % seed)
            start, end = synth_panels(sub, seed, n_days=130)
            elig, _ = t33_eligibility(os.path.join(sub, "t33"))
            unds = [u for u in T33_UNIVERSE if elig[u]["eligible"]]
            check("HYG" not in unds and len(unds) == 13, "eligibility rule excludes the synthetic stale underlying (seed %d)" % seed)
            res = run_synthetic(sub, start, end, unds)
            c0 = res["C0"]["stats"]
            vs = {d: v["verdict"] for d, v in res["designs"].items()}
            print("[3] null seed %d: C0 n %d clusters %d mean %.3f t %.2f | %s | counters %s" % (
                seed, c0["n"], c0["clusters"], c0["mean"], c0["t"], vs, json.dumps(res["counters"])))
            check(c0["n"] > 500 and c0["mean"] < 0, "null C0 is negative (bought convexity carry) seed %d" % seed)
            check(all(v != "ALIVE" for v in vs.values()), "no design ALIVE on a null panel (seed %d)" % seed)
            check(all(res["designs"][d]["stats"]["n"] > 0 for d in DESIGNS), "every trigger fires at least once on the null panel (seed %d)" % seed)
            check(res["counters"]["t31"]["dropped_missing_settlement"] == 0 and res["counters"]["t33"]["dropped_missing_settlement"] == 0,
                  "settlement join works on both layouts (seed %d)" % seed)
            check(res["counters"]["t31"]["unsettled_at_reading"] > 0, "expiry-after-window trades are excluded, not dropped (seed %d)" % seed)
            # per-universe stats exist for both universes
            check(set(res["C0"]["per_universe"]) == {"t31", "t33"}, "both universes pooled in one book (seed %d)" % seed)

        # 4. PLANTED D2 edge: shocks are followed by expiry jumps => D2 should be ALIVE, D1/D3 not helped
        sub = os.path.join(tmp, "plant")
        start, end = synth_panels(sub, 7, n_days=200, plant=("D2", 0.9, 0.16))
        elig, _ = t33_eligibility(os.path.join(sub, "t33"))
        unds = [u for u in T33_UNIVERSE if elig[u]["eligible"]]
        res = run_synthetic(sub, start, end, unds)
        d2 = res["designs"]["D2"]
        print("[4] planted D2: %s -- %s | n %d clusters %d mean %.3f t %.2f conc %.2f placebo p99 %s" % (
            d2["verdict"], d2["reason"], d2["stats"]["n"], d2["stats"]["clusters"], d2["stats"]["mean"], d2["stats"]["t"],
            d2["stats"]["conc"], "%.3f" % d2["placebo"]["p99"] if d2["placebo"] else "n/a"))
        for d in ("D1", "D3", "C0"):
            v = res["designs"].get(d) or res["C0"]
            print("    %s: %s mean %.3f t %.2f n %d" % (d, v.get("verdict", "control"), v["stats"]["mean"], v["stats"]["t"], v["stats"]["n"]))
        check(d2["verdict"] == "ALIVE", "planted aftershock edge is detected as ALIVE")
        check(d2["stats"]["mean"] > max(res["designs"]["D1"]["stats"]["mean"], res["designs"]["D3"]["stats"]["mean"], res["C0"]["stats"]["mean"]),
              "the aftershock design carries the largest mean r of D1/D2/D3/C0 (a path-level plant lifts every book; the trigger must lift its own most)")

        # 5. Concentration: the same plant restricted to one cluster => UNDECIDED, never ALIVE
        sub = os.path.join(tmp, "conc")
        start, end = synth_panels(sub, 11, n_days=200, plant=("single_cluster", "SPY", dt.date(2027, 1, 15)))
        elig, _ = t33_eligibility(os.path.join(sub, "t33"))
        unds = [u for u in T33_UNIVERSE if elig[u]["eligible"]]
        res = run_synthetic(sub, start, end, unds)
        print("[5] single-cluster plant: %s" % {d: (v["verdict"], round(v["stats"]["conc"], 2)) for d, v in res["designs"].items()})
        check(all(v["verdict"] != "ALIVE" for v in res["designs"].values()), "a one-cluster windfall never yields ALIVE")

        # 6. Verdict-rule unit checks with hand-built trades
        good = [{"r": 0.4 + 0.05 * (i % 7), "cluster": "u%d|e%d" % (i % 10, i // 10), "und": "u%d" % (i % 10), "universe": "t33", "trig": {}} for i in range(120)]
        pool = good + [{"r": -0.3 + 0.02 * (i % 9), "cluster": "u%d|p%d" % (i % 10, i // 10), "und": "u%d" % (i % 10), "universe": "t33", "trig": {}} for i in range(600)]
        v = verdict_for("D1", good, 0, pool)
        check(v["verdict"] == "ALIVE", "hand-built uniform positive book passes every §6 condition")
        v = verdict_for("D1", good, 20, pool)
        check(v["verdict"] == "UNDECIDED" and "dropped" in v["reason"], "drop fraction > 10 % => UNDECIDED")
        v = verdict_for("D1", good[:35], 0, pool)
        check(v["verdict"] == "UNDECIDED" and "N_min" in v["reason"], "fewer than 40 clusters => UNDECIDED")
        mixed = [dict(t, universe=("t31" if i % 2 else "t33"), r=(-0.9 if i % 2 else 1.5)) for i, t in enumerate(good)]
        v = verdict_for("D1", mixed, 0, pool + mixed)
        check(v["verdict"] == "UNDECIDED" and "universe" in v["reason"], "one universe at t <= -2 while pooled passes => UNDECIDED")

    # 7. CLI gates: --evaluate must refuse today without opening any panel file
    import subprocess
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--evaluate", "--reading", "first"], capture_output=True, text=True)
    print("[7] --evaluate today -> rc %d: %s" % (p.returncode, p.stdout.strip().splitlines()[0] if p.stdout.strip() else p.stderr.strip()[-200:]))
    check(p.returncode == 3 or (p.returncode == 0 and dt.date.today() >= parse_date(READINGS["first"]["open"])),
          "--evaluate refuses before the reading date (rc 3)")

    print("\nSELFTEST %s (%d failures)" % ("PASSED" if not fails else "FAILED", len(fails)))
    for f in fails:
        print("  - " + f)
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true", help="synthetic panels only; touches nothing under research/")
    g.add_argument("--plan", action="store_true", help="ledger/manifest counts and dates only; opens no snapshot")
    g.add_argument("--evaluate", action="store_true", help="the reading; refuses before the pinned date or on pin drift")
    ap.add_argument("--reading", choices=("first", "second"), default="first")
    a = ap.parse_args()
    if a.selftest:
        return cmd_selftest()
    if a.plan:
        return cmd_plan(a.reading)
    return cmd_evaluate(a.reading)


if __name__ == "__main__":
    sys.exit(main())
