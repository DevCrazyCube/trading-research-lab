#!/usr/bin/env python3
"""CEFBOT -- the paper execution + position manager.

One cycle per invocation. It NEVER places a real order, never touches a trading endpoint, never
spends real money. It: (1) pulls the weekly CEFConnect discount snapshot (keyless, cached),
(2) settles the book that has completed its 1-week hold, marking to REALISED PRICE only,
(3) forms this week's widest-discount decile (ranked on a >=1-session-LAGGED snapshot, per the
PIT-NAV rule) and its SPY hedge, (4) appends an honest ledger row. A weekly-cadence guard makes
extra invocations no-ops.

Mirrors scripts/trading_bot/basket_forward.py's L5 leg: same CEFConnect fetch, same "mark to
Price, never NAV" discipline, same overlapping-settle shape -- but as a dedicated standalone bot
with its own frozen rule, ledger and kill switch.
"""

from __future__ import annotations

import json
import math
import time
import urllib.request
from datetime import date, timedelta

import scripts.t3_pressure_reversal as t3
from scripts.trading_bot.frozen import Refused
from scripts.trading_bot.cefbot import strategy as G


# ---------------------------------------------------------------------------
# data access -- both read-only, both free
# ---------------------------------------------------------------------------

def cef_snapshot(as_of_day: str, *, allow_network: bool = True) -> list:
    """CEFConnect /api/v3/DailyPricing, cached one file per day. ONE keyless GET (~620 KB)."""
    G.SNAP_CACHE.mkdir(parents=True, exist_ok=True)
    path = G.SNAP_CACHE / f"{as_of_day}.json"
    if path.exists():
        return json.loads(path.read_text())
    if not allow_network:
        raise Refused(f"no cached CEF snapshot for {as_of_day} and allow_network=False")
    url = f"{G.CEF_HOST}/api/v3/DailyPricing"
    last = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=G.CEF_UA)
            with urllib.request.urlopen(req, timeout=45) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
            if not isinstance(rows, list) or not rows:
                raise Refused("CEFConnect returned no rows; absence is a refusal, not zero funds")
            path.write_text(json.dumps(rows))
            return rows
        except Refused:
            raise
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
            time.sleep(0.8 * (attempt + 1))
    raise Refused(f"CEFConnect /api/v3/DailyPricing failed after retries: {last}")


def _is_recent_sip_embargo(exc: Exception) -> bool:
    """The free-tier 'subscription does not permit querying recent SIP data' 403 -- an embargo on
    the most recent ~15 min, NOT a hard failure (basket_forward.py's same guard)."""
    m = repr(exc).lower()
    return ("403" in m) or ("recent sip data" in m) or ("subscription does not permit" in m)


def spy_close(as_of_day: str) -> tuple:
    """(close, close_date): SPY's official daily close on the most recent COMPLETED session that
    SIP will serve as of `as_of_day`. Read-only market data on the programme's existing rail --
    no trading endpoint is called. The free tier embargoes the last ~15 min of SIP, so an
    embargoed same-day request is stepped back to the last available session (basket_forward guard).
    """
    start = (date.fromisoformat(as_of_day) - timedelta(days=12)).isoformat()
    for back in range(0, 6):
        end = (date.fromisoformat(as_of_day) - timedelta(days=back)).isoformat()
        try:
            best, best_d = None, None
            for block in t3.paged("/v2/stocks/bars",
                                  {"symbols": G.HEDGE_SYMBOL, "start": start, "end": end,
                                   "timeframe": "1Day", "limit": t3.PAGE, "feed": "sip"}, "bars"):
                for bar in block.get(G.HEDGE_SYMBOL, []):
                    d = bar["t"][:10]
                    if d <= end:
                        best, best_d = bar["c"], d
            if best is not None:
                return float(best), best_d
        except Refused as exc:
            if _is_recent_sip_embargo(exc):
                continue
            raise
    raise Refused(f"no SPY close available on/before {as_of_day}; hedge cannot be marked (rail failure)")


def sessions_since(prev_day: str | None, session_date: str) -> int:
    """Trading sessions in (prev_day, session_date], approximated by US business days (Mon-Fri).

    Counting weekdays rather than reading the Alpaca calendar keeps the weekly-cadence guard
    correct for LIVE dates: the cached t3 calendar is frozen at a past END and returns 0 for recent
    gaps. A holiday makes this over-count by at most one, which cannot change a >=5-session ("about
    a week has passed") decision. Returns a large number when there is no prior rebalance.
    """
    if not prev_day:
        return 10 ** 6
    a = date.fromisoformat(prev_day)
    b = date.fromisoformat(session_date)
    if b <= a:
        return 0
    n = 0
    d = a + timedelta(days=1)
    while d <= b:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


# ---------------------------------------------------------------------------
# state + ledger
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if G.STATE.exists():
        return json.loads(G.STATE.read_text())
    return {"status": "RUNNING", "inception": None, "last_rebalance": None,
            "open_book": None, "signal_snapshots": []}


def save_state(state: dict) -> None:
    G.STATE.write_text(json.dumps(state, indent=2) + "\n")


def append_log(row: dict) -> None:
    with G.LOG.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# cost of one settled weekly tranche (pre-registration section 4)
# ---------------------------------------------------------------------------

def _tranche_cost(long_turnover: float, hold_days: float) -> dict:
    """Half-spread on realised turnover both legs + SEC31 on sales + SPY borrow. Fraction of gross."""
    cef = G.CEF_HALF_SPREAD_BP / 1e4 * long_turnover        # entry+exit implied by turnover
    spy = G.SPY_HALF_SPREAD_BP / 1e4 * (G.BETA_H * 2.0)     # open+close the hedge
    sec31 = G.SEC31_BP / 1e4 * (long_turnover / 2.0 + G.BETA_H)   # CEF sells + SPY short-open
    borrow = G.SPY_BORROW_ANNUAL_BP / 1e4 * G.BETA_H * hold_days / 365.25
    total = cef + spy + sec31 + borrow
    return {"cef_spread": cef, "spy_spread": spy, "sec31": sec31, "borrow": borrow, "total": total}


def _turnover(prev_longs: dict | None, new_longs: dict) -> float:
    """Round-trip turnover fraction of the long leg: names leaving + names entering, weight 1.0."""
    if not prev_longs:
        return 2.0                      # inception: full entry, and the exit is charged at settle
    prev, new = set(prev_longs), set(new_longs)
    # weights are equal within the leg; approximate turnover by the symmetric difference share
    leaving = len(prev - new) / len(prev)
    entering = len(new - prev) / len(new)
    return leaving + entering


# ---------------------------------------------------------------------------
# the one cycle
# ---------------------------------------------------------------------------

def run_cycle(session_date: str | None = None, *, allow_network: bool = True,
              dry_run: bool = False) -> dict:
    """Advance the bot by one session. Returns the ledger row (also appended unless dry_run)."""
    G.assert_frozen()
    session_date = session_date or date.today().isoformat()
    state = load_state()

    if str(state["status"]).startswith("HALTED"):
        return {"session": session_date, "phase": "halted", "status": state["status"],
                "note": "kill rule fired earlier; the ledger is closed (ITERATION_PROTOCOL.md §7)."}

    rows = cef_snapshot(session_date, allow_network=allow_network)

    # ---- weekly cadence guard -------------------------------------------------
    last_reb = state["last_rebalance"]
    if last_reb == session_date:
        return {"session": session_date, "phase": "already_rebalanced_today", "status": state["status"]}
    if last_reb is not None and sessions_since(last_reb, session_date) < G.REBAL_MIN_SESSIONS:
        return {"session": session_date, "phase": "not_a_rebalance_session",
                "status": state["status"], "sessions_since_last": sessions_since(last_reb, session_date),
                "open_book": bool(state["open_book"])}

    px_now = {r["Ticker"]: r.get("Price") for r in rows if r.get("Ticker")}

    # ---- 1. settle the maturing book (mark to realised PRICE only) -------------
    settled = None
    ob = state["open_book"]
    if ob is not None:
        spy_exit, spy_exit_date = spy_close(session_date)
        lr = [px_now[s] / p0 - 1.0 for s, p0 in ob["long"].items()
              if px_now.get(s) and p0]
        ur = [px_now[s] / p0 - 1.0 for s, p0 in ob["universe"].items()
              if px_now.get(s) and p0]
        if lr and ur:
            long_ret = sum(lr) / len(lr)
            universe_ret = sum(ur) / len(ur)
            spy_ret = spy_exit / ob["spy_entry"] - 1.0
            hedge_ret = -G.BETA_H * spy_ret
            gross = long_ret + hedge_ret
            hold_days = (date.fromisoformat(session_date)
                         - date.fromisoformat(ob["entry_date"])).days
            cost = _tranche_cost(ob["long_turnover"], hold_days)
            net = gross - cost["total"]
            settled = {
                "entry_date": ob["entry_date"], "exit_date": session_date,
                "signal_date": ob["signal_date"], "hold_days": hold_days,
                "n_long": len(lr), "n_universe": len(ur),
                "long_ret": long_ret, "universe_ret": universe_ret,
                "cross_sectional_alpha": long_ret - universe_ret,
                "spy_ret": spy_ret, "hedge_ret": hedge_ret, "spy_exit_date": spy_exit_date,
                "gross": gross, "cost": cost, "net": net,
                "inception_same_day_signal": ob.get("inception_same_day_signal", False),
                "mark": "realised Price only (NAV never marks; discount is signal-only)",
            }
        else:
            settled = {"entry_date": ob["entry_date"], "exit_date": session_date,
                       "phase": "unmarkable", "note": "too few prices returned to settle"}

    # ---- 1b. pre-registered KILL switch (prereg §6) ---------------------------
    # Evaluate the settled history INCLUDING the tranche just marked; if a kill condition has
    # fired, close the ledger and enter NO new book. Detection lives in evaluate.kill_check; the
    # bot is what acts on it, at run time, before committing (ITERATION_PROTOCOL.md §2/§6).
    from scripts.trading_bot.cefbot import evaluate as E  # noqa: PLC0415
    hist = E.read_settled()
    if settled and isinstance(settled.get("net"), (int, float)):
        hist = hist + [settled]
    kill = E.kill_check(hist)
    if kill["halt"]:
        row = {"session": session_date, "phase": "halted-this-session",
               "status": f"HALTED - {kill['verdict']}", "settled": settled,
               "kill": kill, "paper": True, "NO_REAL_ORDER": True,
               "note": "kill rule fired; ledger closed, no new book entered."}
        if not dry_run:
            state["status"] = f"HALTED - {kill['verdict']}"
            state["open_book"] = None
            state["last_rebalance"] = session_date
            save_state(state)
            append_log(row)
        return row

    # ---- 2. form this week's book on a >=1-session-LAGGED signal ---------------
    lagged = [d for d in state["signal_snapshots"] if d < session_date]
    inception_same_day = False
    if lagged:
        signal_date = max(lagged)
        signal_rows = cef_snapshot(signal_date, allow_network=False)
    else:
        # inception: no earlier snapshot exists. Take the inaugural book on today's snapshot and
        # flag it -- a transparent one-time same-day-signal concession (prereg §2f); every later
        # rebalance uses the lag. All P&L remains Price-only regardless.
        signal_date = session_date
        signal_rows = rows
        inception_same_day = True

    book = G.long_book(signal_rows)
    spy_entry, spy_entry_date = spy_close(session_date)
    prev_longs = ob["long"] if ob else None
    turn = _turnover(prev_longs, book["long"])
    # entry prices are TODAY's realised prices (we act on this session's price, per §2f)
    long_entry = {t: px_now[t] for t in book["long"] if px_now.get(t)}
    uni_entry = {t: px_now[t] for t in book["universe"] if px_now.get(t)}
    new_book = {
        "entry_date": session_date, "signal_date": signal_date,
        "long": long_entry, "universe": uni_entry, "spy_entry": spy_entry,
        "spy_entry_date": spy_entry_date,
        "long_turnover": turn, "n_long": len(long_entry), "n_universe": len(uni_entry),
        "inception_same_day_signal": inception_same_day,
    }

    row = {
        "session": session_date, "phase": "rebalanced", "status": state["status"],
        "settled": settled,
        "entered": {
            "entry_date": session_date, "signal_date": signal_date,
            "n_long": len(long_entry), "n_universe": book["n_universe"],
            "long_turnover": round(turn, 4),
            "widest_discount_decile": [
                {"ticker": t, "discount_pct": round(d, 2),
                 "entry_price": px_now.get(t)} for t, d in book["widest"]],
            "hedge": {"symbol": G.HEDGE_SYMBOL, "beta_h": G.BETA_H, "spy_entry": spy_entry,
                      "spy_entry_date": spy_entry_date},
            "inception_same_day_signal": inception_same_day,
        },
        "asof": {"signal": f"discount snapshot {signal_date} (lagged)",
                 "mark": "realised Price only"},
        "paper": True,
        "NO_REAL_ORDER": True,
    }

    if not dry_run:
        state["open_book"] = new_book
        state["last_rebalance"] = session_date
        if state["inception"] is None:
            state["inception"] = session_date
        if session_date not in state["signal_snapshots"]:
            state["signal_snapshots"].append(session_date)
            state["signal_snapshots"] = sorted(state["signal_snapshots"])[-8:]
        save_state(state)
        append_log(row)

    return row


def proof() -> dict:
    """Engine self-check: replay the S2 discount-LEVEL long-widest-decile-vs-universe cross-
    sectional alpha over the CACHED T12 weekly history (CEFConnect, no network, no SPY needed).

    This is NOT ledger evidence: it runs on the live-only (survivorship-biased) t12 cache, so it
    is a selection-inflated UPPER BOUND on the signal, exactly as basket_forward.l5_proof warns.
    Its only job is to show the frozen ranking + Price-only marking reproduce a positive
    cross-sectional discount tilt at roughly the backtest magnitude.
    """
    import gzip as _gz
    import statistics as _st
    cache = G.ROOT / "research" / "data" / "t12_cache" / "history_5Y.json.gz"
    if not cache.exists():
        raise Refused(f"no cached T12 history at {cache}; run scripts/t12_cef_discount.py first")
    with _gz.open(cache, "rt") as fh:
        hist = json.load(fh)
    alldates = sorted({r["date"] for t in hist if hist[t] for r in hist[t]})

    def asof(t, d):
        best = None
        for r in (hist.get(t) or []):
            if r["date"] <= d and r.get("price") and r.get("discount") is not None:
                best = r
            elif r["date"] > d:
                break
        return best

    def book(d):
        cand = []
        for t in hist:
            pd = asof(t, d)
            if not pd or pd["price"] <= G.PRICE_MIN:
                continue
            cand.append((t, pd["discount"], pd["price"]))
        if len(cand) < 20:
            return None
        cand.sort(key=lambda x: x[1])
        n = max(1, round(len(cand) * G.DECILE))
        return cand[:n], cand

    alphas = []
    for i in range(len(alldates) - 1):
        d0, d1 = alldates[i], alldates[i + 1]
        b = book(d0)
        if not b:
            continue
        longs, universe = b
        lr = [asof(t, d1)["price"] / p0 - 1 for t, _dd, p0 in longs if asof(t, d1)]
        ur = [asof(t, d1)["price"] / p0 - 1 for t, _dd, p0 in universe if asof(t, d1)]
        if lr and ur:
            alphas.append(_st.fmean(lr) - _st.fmean(ur))
    m = _st.fmean(alphas) if alphas else None
    sd = _st.stdev(alphas) if len(alphas) > 1 else None
    return {"engine": "CEFBOT S2 long-widest-decile vs universe (cross-sectional alpha)",
            "n_weekly_obs": len(alphas),
            "mean_cross_sectional_alpha_bp_per_wk": (m * 1e4) if m is not None else None,
            "t_stat": (m / (sd / math.sqrt(len(alphas)))) if sd else None,
            "NOT_LEDGER_EVIDENCE": ("cached live-only t12 history (survivorship-biased); "
                                    "selection-inflated UPPER BOUND, not a forward result.")}


def peek_first_basket(session_date: str | None = None, *, allow_network: bool = True) -> dict:
    """Show TODAY's target widest-discount basket without committing anything (the runnable-now
    demo / `show` command). Pure ranking on the live snapshot; no marks, no state, no order."""
    G.assert_frozen()
    session_date = session_date or date.today().isoformat()
    rows = cef_snapshot(session_date, allow_network=allow_network)
    book = G.long_book(rows)
    return {"session": session_date, "n_eligible": book["n_universe"], "n_long": book["n_long"],
            "widest_discount_decile": [
                {"ticker": t, "discount_pct": round(d, 2)} for t, d in book["widest"]],
            "hedge": {"symbol": G.HEDGE_SYMBOL, "beta_h": G.BETA_H},
            "paper": True, "NO_REAL_ORDER": True}
