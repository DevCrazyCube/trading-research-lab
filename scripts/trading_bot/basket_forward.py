#!/usr/bin/env python3
"""BASKET1 -- the forward paper LOGGER for the imperfect-edge basket.

WHAT THIS IS, AND WHAT IT IS NOT
================================
This is a **LOGGER**, not a trading bot. It computes each frozen leg's signal from data available
as-of a session close, marks the resulting HYPOTHETICAL position to the next realised prices, and
appends a per-leg + combined mark-to-market P&L row to an append-only forward log. It is the
T16-panel pattern: pure forward recording.

**It places NO orders -- not live, not paper.** There is no broker-auth file, no order endpoint, no
`submit` mode anywhere in this file. The only network it touches is the Alpaca MARKET-DATA host
(read-only), through the same `data.py` guard the backtest rig uses. **No real money. No position is
ever held.** Every P&L number is hypothetical-but-honest: "if the frozen rule had traded this session
at the modelled prices and costs, this is the net it would have realised." The log is the evidence;
it is not yet evidence of anything.

**The purpose is to measure realised out-of-sample edge to defeat selection bias.** Every backtested
number attached to these legs is a selection-inflated UPPER BOUND. The honest prior for the realised
combined forward Sharpe is ~0.3-0.6 and it could be zero. See
`research/trading_bot/BASKET_FORWARD_PREREGISTRATION.md` for the frozen spec and the honest caveats,
and `IMPERFECT_BASKET.md` for the audit that produced the candidate set.

THE FROZEN SPEC IS LOADED AND VERIFIED, NEVER RETYPED
=====================================================
The legs, universes, signals, execution assumptions, cost models, sizing sleeve, benchmark and
kill switch are read from `BASKET_FORWARD_FROZEN.json`, whose `preregistration_sha256` is checked
against the .md at load time. A rule that can be edited is not frozen, and a forward test of an
unfrozen rule measures nothing. The T13 vol overlay arithmetic is consumed from
`scripts.t13_risk_shaping.vol_exposure` and cross-checked against an independent recomputation.

AS-OF DISCIPLINE
================
Per prereg section 2: every leg asserts `max(signal_timestamp) < min(mark_timestamp)` and refuses on
violation; the vol overlay uses SPY closes through t-2 (enforced by the fetch window); no forward row
is logged for a session dated before the freeze (that would be in-sample -- use `proof`, which never
writes the ledger).

USAGE
=====
    python -m scripts.trading_bot.basket_forward selftest      # hermetic wiring check, no network
    python -m scripts.trading_bot.basket_forward proof         # real run on the most-recent COMPLETE
                                                               #   session; labelled, NOT written to the ledger
    python -m scripts.trading_bot.basket_forward session       # log one forward session (freeze-forward only)
    python -m scripts.trading_bot.basket_forward status
    python -m scripts.trading_bot.basket_forward report
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .data import assert_data_host, load_env_credentials
from .frozen import ALPACA_DATA_HOST, Refused, pin_report
from .t4_forward import load_daily_closes, t13_target_weight, _cash_rate_for, refresh_cash_rates

RESEARCH = ROOT / "research" / "trading_bot"
CACHE = ROOT / "research" / "data" / "basket_cache"
ETF_1545_CACHE = CACHE / "etfrv_1545"
CEF_SNAP_CACHE = CACHE / "cef_snapshots"           # L5: one keyless CEFConnect snapshot per week
T12_CACHE = ROOT / "research" / "data" / "t12_cache"
T28_CACHE = ROOT / "research" / "data" / "t28_dualclass_cache"
T17_CACHE = ROOT / "research" / "data" / "t17_cache"
T7_CACHE = ROOT / "research" / "data" / "t7_cache"

CEF_HOST = "https://www.cefconnect.com"            # L5 free data host (keyless; not the trading host)
CEF_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research/1.0", "Accept": "application/json"}

FROZEN_PATH = RESEARCH / "BASKET_FORWARD_FROZEN.json"
PREREG_PATH = RESEARCH / "BASKET_FORWARD_PREREGISTRATION.md"
LEDGER_PATH = RESEARCH / "BASKET_FORWARD_LOG.jsonl"
STATE_PATH = RESEARCH / "BASKET_FORWARD_STATE.json"

SCHEMA_VERSION = 1
TRADING_DAYS = 252.0

FRAMING = (
    "FORWARD PAPER LOGGER of the imperfect-edge basket (positive-but-unproven Pile B). It places "
    "NO orders, holds NO position, and reads only the market-data host. Every P&L number is "
    "HYPOTHETICAL mark-to-market. Every backtested estimate behind these legs is a selection-"
    "inflated UPPER BOUND; the honest realised-Sharpe prior is ~0.3-0.6 and could be zero. This "
    "log measures realised out-of-sample edge to DEFEAT selection bias. It is not evidence of "
    "anything yet."
)

# A polite global throttle for the read-only data calls, so a single-session pull never looks like
# an aggressive crawl. This logger fetches ONE session's data per run, not a multi-year history.
_LAST_CALL = [0.0]
_MIN_INTERVAL = 0.12


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Frozen spec
# ---------------------------------------------------------------------------

def frozen_spec() -> dict:
    """Load the frozen basket spec, refusing if the pre-registration has moved since the freeze."""
    for path in (FROZEN_PATH, PREREG_PATH):
        if not path.exists():
            raise Refused(f"{path} is missing; the frozen basket cannot be loaded")
    spec = json.loads(FROZEN_PATH.read_text())
    expected = spec.get("preregistration_sha256")
    actual = _sha256(PREREG_PATH)
    if not expected:
        raise Refused("BASKET_FORWARD_FROZEN.json carries no preregistration_sha256")
    if actual != expected:
        raise Refused(
            "BASKET_FORWARD_PREREGISTRATION.md changed since the freeze.\n"
            f"  frozen expects: {expected}\n  on disk:        {actual}\n"
            "Restore the document. Do NOT update the hash: the point of the hash is that the rule "
            "this logger runs forward is the rule frozen before the first forward observation."
        )
    spec["_preregistration_sha256_verified"] = actual
    spec["_frozen_json_sha256"] = _sha256(FROZEN_PATH)
    verify_leg_hashes(spec)
    return spec


def _leg_spec_sha256(leg: dict) -> str:
    """Canonical SHA-256 of a leg's frozen spec, EXCLUDING its own spec_sha256 field.

    A leg that carries `spec_sha256` is a v2 follow-up-freeze leg (L3-L6): its spec is frozen
    independently of the document hash, and this recomputation is what makes each new leg's freeze
    tamper-evident on its own. The hash MUST be computed exactly as `build_frozen` wrote it:
    sorted keys, compact separators, over the object with the hash field removed.
    """
    body = {k: v for k, v in leg.items() if k != "spec_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_leg_hashes(spec: dict) -> None:
    """Refuse if any leg that declares a `spec_sha256` does not match its own canonical spec."""
    for leg in spec["legs"]:
        want = leg.get("spec_sha256")
        if not want:
            continue  # L1/L2 (v1) carry no per-leg hash and are intentionally unchanged
        got = _leg_spec_sha256(leg)
        if got != want:
            raise Refused(
                f"leg {leg['id']!r} spec_sha256 mismatch: the frozen spec for this leg was edited "
                f"since its freeze.\n  frozen expects: {want}\n  on disk:        {got}\n"
                "A forward test of an edited leg measures nothing. Restore the leg spec; do NOT "
                "update the hash.")


def leg_freeze_date(spec: dict, leg: dict) -> str:
    """The date on and after which this leg may write forward rows (its own freeze, else basket)."""
    return (leg.get("freeze_utc") or spec["frozen_utc"])[:10]


def freeze_date(spec: dict) -> str:
    return spec["frozen_utc"][:10]


def leg_by_id(spec: dict, leg_id: str) -> dict:
    for leg in spec["legs"]:
        if leg["id"] == leg_id:
            return leg
    raise Refused(f"no leg {leg_id!r} in the frozen spec")


# ---------------------------------------------------------------------------
# Read-only market-data helpers (NO trading host is reachable from here)
# ---------------------------------------------------------------------------

def _data_get(path: str, params: dict, tries: int = 8) -> dict:
    key, secret = load_env_credentials()
    host = assert_data_host(ALPACA_DATA_HOST)
    url = f"{host}{path}?{urllib.parse.urlencode(params)}"
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "Accept": "application/json"}
    last = None
    for attempt in range(tries):
        wait = _MIN_INTERVAL - (time.monotonic() - _LAST_CALL[0])
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL[0] = time.monotonic()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            last = f"HTTP {exc.code}: {body}"
            if exc.code == 429 or exc.code in (500, 502, 503, 504):
                time.sleep(1.0 * (attempt + 1))
                continue
            raise Refused(f"{path}: {last}")
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
            time.sleep(1.0 * (attempt + 1))
    raise Refused(f"{path} failed after {tries} attempts: {last}")


def _data_get_paged(path: str, params: dict, key: str):
    token, out, pages = None, [], 0
    while True:
        p = dict(params)
        if token:
            p["page_token"] = token
        payload = _data_get(path, p)
        block = payload.get(key)
        if block is None:
            raise Refused(f"{path}: response has no {key!r} key; that is not zero rows")
        out.append(block)
        token = payload.get("next_page_token")
        pages += 1
        if not token:
            return out
        if pages > 5000:
            raise Refused("paging did not terminate")


def _ny_offset(day: str) -> int:
    """Hours to ADD to New York local to reach UTC on `day` (4 in DST, 5 in EST)."""
    import zoneinfo
    d = dt.date.fromisoformat(day)
    stamp = dt.datetime(d.year, d.month, d.day, 12, tzinfo=zoneinfo.ZoneInfo("America/New_York"))
    return -int(stamp.utcoffset().total_seconds() // 3600)


def _minute_closes(day: str, symbols: list, minutes_wanted: tuple) -> dict:
    """{sym: {'HH:MM': close}} for the requested ET minutes, RAW SIP. Fully paged."""
    off = _ny_offset(day)
    start = f"{day}T{15 + off:02d}:29:00Z"
    end = f"{day}T{16 + off:02d}:00:00Z"
    key, _ = load_env_credentials()
    out = {}
    for blocks in _data_get_paged("/v2/stocks/bars", {
            "symbols": ",".join(symbols), "timeframe": "1Min", "start": start, "end": end,
            "limit": 10000, "feed": "sip", "adjustment": "raw"}, "bars"):
        for sym, bars in blocks.items():
            for b in bars:
                hhmm = b["t"][11:16]
                local = f"{int(hhmm[:2]) - off:02d}:{hhmm[3:5]}"
                if local in minutes_wanted:
                    out.setdefault(sym, {})[local] = b["c"]
    return out


def _auctions(day: str, symbols: list) -> dict:
    """{sym: {'o': open_print, 'c': close_print}} for `day`, code-agnostic largest-size record.

    Per ORIGINAL_STRATEGY_SHORTLIST_BROAD.md 3.2a: the official-close condition code is NOT stable
    (6 in 2019, M in 2026); a 6-only filter silently drops a leg and manufactures a fake dislocation.
    So we take the largest-size print in each leg's list, restricted to the requested date.
    """
    out = {}
    for blocks in _data_get_paged("/v2/stocks/auctions", {
            "symbols": ",".join(symbols), "start": day, "end": day, "limit": 10000,
            "feed": "sip"}, "auctions"):
        for sym, days in blocks.items():
            for d in days:
                if d.get("d") != day:
                    continue
                rec = out.setdefault(sym, {})
                for leg in ("o", "c"):
                    prints = d.get(leg) or []
                    if prints:
                        rec[leg] = max(prints, key=lambda p: p.get("s", 0))["p"]
    return out


def _daily_bars(symbols: list, start: str, end: str, adjustment: str,
                *, allow_network: bool = True) -> dict:
    """{sym: [{'d':date,'c':close,'v':vol}]} daily bars in [start,end], one adjustment. Read-only SIP.

    Used by L3 (dual-class close-to-close): 'raw' for the signal level, 'all' for the P&L mark.
    """
    if not allow_network:
        raise Refused("daily bars requested with allow_network=False and no cache path")
    out = {}
    for blocks in _data_get_paged("/v2/stocks/bars", {
            "symbols": ",".join(symbols), "timeframe": "1Day", "start": start, "end": end,
            "limit": 10000, "feed": "sip", "adjustment": adjustment}, "bars"):
        for sym, bars in blocks.items():
            for b in bars:
                out.setdefault(sym, []).append({"d": b["t"][:10], "c": b["c"], "v": b.get("v", 0)})
    return out


def _cef_snapshot(as_of_day: str, *, allow_network: bool = True) -> list:
    """The CEFConnect /api/v3/DailyPricing snapshot for the week of `as_of_day`, cached per day.

    ONE keyless GET (~620 KB, ~1 s) -- inline-safe, not a crawl, no account/key. This is the ONLY
    non-Alpaca host the logger touches, and it is read-only free data. Returns the raw list of fund
    rows (each carrying Ticker, Discount, NAV, Price, AvgDailyVolume, ...).
    """
    CEF_SNAP_CACHE.mkdir(parents=True, exist_ok=True)
    path = CEF_SNAP_CACHE / f"{as_of_day}.json"
    if path.exists():
        return json.loads(path.read_text())
    if not allow_network:
        raise Refused(f"no cached CEF snapshot for {as_of_day} and allow_network=False")
    url = f"{CEF_HOST}/api/v3/DailyPricing"
    last = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=CEF_UA)
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


# ---------------------------------------------------------------------------
# Vol overlay + cash
# ---------------------------------------------------------------------------

def vol_overlay(session_date: str, spec: dict, *, allow_network: bool = True,
                cache_dir=None) -> dict:
    ov = spec["vol_overlay"]
    rule = {"rule_id": ov["rule_id"], "L": ov["L"], "target": ov["target"], "wmax": ov["wmax"]}
    series = load_daily_closes(session_date=session_date, allow_network=allow_network,
                               cache_dir=cache_dir)
    w = t13_target_weight(series["closes"], rule)  # cross-checks frozen vs independent, refuses on gap
    return {"rule_id": ov["rule_id"], "reference_close_date": series["dates"][-1],
            "realised_vol_annual": w["realised_vol_annual"], "w_vol": w["target_weight"],
            "cross_check": w["cross_check"], "spy_sessions": series["dates"]}


def cash_leg(reference_date: str) -> dict:
    c = _cash_rate_for(reference_date)
    return {"as_of": c["as_of"], "annual_pct": c["annual_pct"], "source": c["source"],
            "stale_days": c["stale_days"]}


# ---------------------------------------------------------------------------
# L2 -- ETF-sibling RV (Arm B): intraday, settles the same session
# ---------------------------------------------------------------------------

def _etf_symbols(leg: dict) -> list:
    seen = []
    for a, b in leg["pairs"]:
        for s in (a, b):
            if s not in seen:
                seen.append(s)
    return seen


def _etf_1545_snapshot(day: str, symbols: list, *, allow_network: bool = True) -> dict:
    """{sym: price at the 15:45 ET one-minute close} for `day`, cached per day."""
    ETF_1545_CACHE.mkdir(parents=True, exist_ok=True)
    path = ETF_1545_CACHE / f"{day}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        if all(s in cached for s in symbols):
            return {s: cached[s] for s in symbols}
    if not allow_network:
        raise Refused(f"no cached 15:45 snapshot for {day} and allow_network=False")
    got = _minute_closes(day, symbols, ("15:45",))
    snap = {s: got[s]["15:45"] for s in symbols if s in got and "15:45" in got[s]}
    merged = {}
    if path.exists():
        merged.update(json.loads(path.read_text()))
    merged.update(snap)
    path.write_text(json.dumps(merged, sort_keys=True))
    return snap


def etfrv_settle(session_date: str, leg: dict, spine_before: list, *,
                 allow_network: bool = True) -> dict:
    """Compute L2's fired-pair book for `session_date` and mark it to the same-day close print.

    Signal at 15:45(t), mark at 16:00(t) -- one intraday session, no overnight gap. `spine_before`
    is the list of prior trading-session dates (strictly before session_date), newest last, used to
    build the trailing-60 15:45 log-spread. Returns a settled leg record (or a no-trade record).
    """
    symbols = _etf_symbols(leg)
    trigger = leg["signal"]["trigger_abs_z"]
    hs = leg["cost_bp"]["entry_half_spread_by_symbol"]
    sec31 = leg["cost_bp"]["sec31_bp_on_sold"]

    trailing = spine_before[-60:]
    if len(trailing) < 60:
        raise Refused(f"need 60 prior sessions for the L2 z-score; have {len(trailing)}")

    # Trailing 15:45 snapshots (cached per day). Missing a day's snapshot for a symbol drops that
    # symbol's history point rather than fabricating one.
    hist = {}
    for d in trailing:
        snap = _etf_1545_snapshot(d, symbols, allow_network=allow_network)
        hist[d] = snap
    today45 = _etf_1545_snapshot(session_date, symbols, allow_network=allow_network)
    todayclose = _auctions(session_date, symbols, ) if allow_network else {}
    close = {s: (todayclose.get(s) or {}).get("c") for s in symbols}

    asof_signal_et = (session_date, "15:45")
    asof_mark_et = (session_date, "16:00")
    _assert_asof(asof_signal_et, asof_mark_et, "ETFRV")

    fired = []
    for a, b in leg["pairs"]:
        # trailing log-spread series, only sessions where both legs printed a 15:45 bar
        series = [math.log(hist[d][a] / hist[d][b])
                  for d in trailing if a in hist[d] and b in hist[d]
                  and hist[d][a] > 0 and hist[d][b] > 0]
        if len(series) < 40:
            continue
        if a not in today45 or b not in today45 or close.get(a) is None or close.get(b) is None:
            continue
        mean = sum(series) / len(series)
        var = sum((x - mean) ** 2 for x in series) / (len(series) - 1)
        sd = math.sqrt(var)
        if sd <= 0:
            continue
        s_now = math.log(today45[a] / today45[b])
        z = (s_now - mean) / sd
        if abs(z) < trigger:
            continue
        side = -1.0 if z > 0 else 1.0  # fade: if A rich (z>0) short A long B => side on (A-B) is -1
        rA = close[a] / today45[a] - 1.0
        rB = close[b] / today45[b] - 1.0
        gross = side * (rA - rB)
        # entry crosses both legs' half-spread; exit auction zero; SEC31 on the sold notional (~2 legs)
        cost = (hs[a] + hs[b]) / 1e4 + 2.0 * sec31 / 1e4
        fired.append({"pair": [a, b], "z": z, "side": side, "gross": gross,
                      "net": gross - cost, "cost_bp": (hs[a] + hs[b] + 2.0 * sec31)})

    if not fired:
        return {"status": leg["status"], "phase": "no_trade", "settled": None,
                "pairs_fired": [], "asof": {"signal_et": asof_signal_et, "mark_et": asof_mark_et},
                "note": "no pair cleared |z|>=1.5 this session; leg flat, contributes cash only"}
    net = sum(f["net"] for f in fired) / len(fired)
    gross = sum(f["gross"] for f in fired) / len(fired)
    return {"status": leg["status"], "phase": "settled",
            "settled": {"exit_session": session_date, "net_return": net, "gross_return": gross,
                        "n_pairs": len(fired), "observation": "one intraday pair-book session"},
            "pairs_fired": fired, "asof": {"signal_et": asof_signal_et, "mark_et": asof_mark_et}}


def etfrv_variant_from_base(base: dict, leg: dict, session_date: str) -> dict:
    """Derive an ETF-sibling RV entry-band VARIANT (L10 ETFRV_Z20, |z|>=2.0) from L2's already-
    computed fired-pair book -- NO new fetch, NO new data source.

    The variant's entry band (2.0) is strictly HIGHER than L2's (1.5), so its fired set is exactly
    the SUBSET of L2's fired pairs clearing the higher band. L2 already crossed each pair's
    half-spread and marked it to the same-session close under identical prices/costs, so re-filtering
    that book by |z| is an EXACT reproduction of the variant. This is a logging-only unsized leg; it
    never enters `contributions` and never touches the combined book. Lookahead was already asserted
    inside etfrv_settle (same 15:45 signal / 16:00 mark), and the base asof is carried through.
    """
    trigger = leg["signal"]["trigger_abs_z"]
    asof = base.get("asof")
    fired = [f for f in base.get("pairs_fired", []) if abs(f["z"]) >= trigger]
    if not fired:
        return {"status": leg["status"], "phase": "no_trade", "settled": None, "pairs_fired": [],
                "asof": asof, "logged_unsized": True,
                "note": f"no pair cleared |z|>={trigger} this session (unsized variant of L2)"}
    net = sum(f["net"] for f in fired) / len(fired)
    gross = sum(f["gross"] for f in fired) / len(fired)
    return {"status": leg["status"], "phase": "settled", "logged_unsized": True,
            "settled": {"exit_session": session_date, "net_return": net, "gross_return": gross,
                        "n_pairs": len(fired),
                        "observation": "one intraday pair-book session (|z|>=2.0 band variant, unsized)"},
            "pairs_fired": fired, "asof": asof}


# ---------------------------------------------------------------------------
# L1 -- T3 pressure reversal: overnight, signal at close(t), mark at open(t+1)
# ---------------------------------------------------------------------------

def _t3_universe(session_date: str) -> dict:
    """month -> [symbols] point-in-time top-300 ADV screen, from the cached T3 monthly data."""
    import scripts.t3_pressure_reversal as t3  # noqa: PLC0415
    return t3.build_universe(300)


def t3_signal(session_date: str, universe_map: dict, *, allow_network: bool = True) -> dict:
    """The fade deciles decided at close(session_date), to be marked at the next open auction."""
    syms = universe_map.get(session_date[:7], [])
    if not syms:
        raise Refused(f"no top-300 universe for month {session_date[:7]}; monthly cache may need a "
                      "refresh (maintenance) before this session can be logged")
    mins = _minute_closes(session_date, syms, ("15:49", "15:59"))
    rows = []
    for s in syms:
        m = mins.get(s)
        if not m or "15:49" not in m or "15:59" not in m:
            continue
        p49, p59 = m["15:49"], m["15:59"]
        if min(p49, p59) <= 0:
            continue
        rows.append((s, p59 / p49 - 1.0, p59))
    if len(rows) < 100:
        raise Refused(f"only {len(rows)} names have the 15:49/15:59 minutes; T3 needs >=100")
    rows.sort(key=lambda r: r[1])
    k = max(1, int(len(rows) * 0.10))
    longs = rows[:k]      # most-negative r10 -> fade by buying
    shorts = rows[-k:]    # most-positive r10 -> fade by selling
    return {"signal_session": session_date, "k": k, "n_names": len(rows),
            "long": [(s, p59) for s, _, p59 in longs],
            "short": [(s, p59) for s, _, p59 in shorts],
            "signal_et": (session_date, "15:59")}


def t3_mark(signal: dict, exit_session: str, leg: dict, *, allow_network: bool = True) -> dict:
    """Mark the queued fade book at `exit_session`'s opening auction. Returns a settled record."""
    _assert_asof(signal["signal_et"], (exit_session, "09:30"), "T3")
    syms = [s for s, _ in signal["long"]] + [s for s, _ in signal["short"]]
    au = _auctions(exit_session, syms)
    # corporate-action exclusion on the exit date, and missing-open exclusion
    import scripts.t3_pressure_reversal as t3  # noqa: PLC0415
    ca = t3.corporate_action_dates(sorted(set(syms)))
    ca = {s: set(v) for s, v in ca.items()}

    def leg_ret(book):
        vals = []
        for s, p59 in book:
            if exit_session in ca.get(s, ()):
                continue
            po = (au.get(s) or {}).get("o")
            if po is None or po <= 0:
                continue
            vals.append(po / p59 - 1.0)
        return vals

    long_r, short_r = leg_ret(signal["long"]), leg_ret(signal["short"])
    if len(long_r) < 1 or len(short_r) < 1:
        raise Refused(f"no priced open-auction legs for T3 night {signal['signal_session']} exiting "
                      f"{exit_session}; leaving pending rather than fabricating a mark")
    gross = 0.5 * (sum(long_r) / len(long_r)) - 0.5 * (sum(short_r) / len(short_r))
    c = leg["cost_bp"]
    gap = max(1, (dt.date.fromisoformat(exit_session)
                  - dt.date.fromisoformat(signal["signal_session"])).days)
    cost = (c["entry_half_spread"] + c["exit_auction"] + c["regulatory_round_trip"]) / 1e4
    cost += c["short_fraction"] * (c["borrow_annual_bp_on_short"] / 1e4) * gap / 365.25
    return {"status": leg["status"], "phase": "settled",
            "settled": {"signal_session": signal["signal_session"], "exit_session": exit_session,
                        "net_return": gross - cost, "gross_return": gross,
                        "n_long": len(long_r), "n_short": len(short_r), "calendar_gap": gap,
                        "observation": "one overnight (close->open) night"},
            "asof": {"signal_et": signal["signal_et"], "mark_et": (exit_session, "09:30")}}


# ---------------------------------------------------------------------------
# L3 -- DUALCLASS voting-premium RV: two-timescale z-fade, multi-day round-trips
# ---------------------------------------------------------------------------

def _dc_etb_ok(sym: str, leg: dict) -> bool:
    return sym in set(leg["guard_mandatory"]["etb_whitelist"])


def _dc_series(session_date: str, syms: list, *, allow_network: bool, cached_only: bool):
    """Per-symbol {date: {'raw':c,'adj':c,'v':vol}} up to and including session_date.

    cached_only reads the frozen t28 cache (proof); otherwise pulls trailing daily bars live.
    """
    if cached_only:
        raw = json.loads((T28_CACHE / "bars_raw.json").read_text())
        adj = json.loads((T28_CACHE / "bars_all.json").read_text())
        out = {}
        for s in syms:
            m = {}
            for b in raw.get(s, []):
                if b["t"][:10] <= session_date:
                    m.setdefault(b["t"][:10], {})["raw"] = b["c"]; m[b["t"][:10]]["v"] = b.get("v", 0)
            for b in adj.get(s, []):
                if b["t"][:10] <= session_date and b["t"][:10] in m:
                    m[b["t"][:10]]["adj"] = b["c"]
            out[s] = {d: v for d, v in m.items() if "raw" in v and "adj" in v}
        return out
    start = (dt.date.fromisoformat(session_date) - dt.timedelta(days=520)).isoformat()
    rawb = _daily_bars(syms, start, session_date, "raw", allow_network=allow_network)
    adjb = _daily_bars(syms, start, session_date, "all", allow_network=allow_network)
    out = {}
    for s in syms:
        m = {}
        for b in rawb.get(s, []):
            m.setdefault(b["d"], {})["raw"] = b["c"]; m[b["d"]]["v"] = b["v"]
        for b in adjb.get(s, []):
            if b["d"] in m:
                m[b["d"]]["adj"] = b["c"]
        out[s] = {d: v for d, v in m.items() if "raw" in v and "adj" in v}
    return out


def _dc_pair_rows(series: dict, a: str, b: str):
    days = sorted(set(series.get(a, {})) & set(series.get(b, {})))
    rows = []
    for d in days:
        ra, rb = series[a][d], series[b][d]
        if ra["raw"] <= 0 or rb["raw"] <= 0:
            continue
        rows.append({"d": d, "s": math.log(ra["raw"] / rb["raw"]),
                     "pa": ra["adj"], "pb": rb["adj"], "px_a": ra["raw"], "px_b": rb["raw"],
                     "dv": min(ra["raw"] * ra["v"], rb["raw"] * rb["v"])})
    return rows


def _dc_z_at(rows, i, L):
    """z at row i using the break-reset trailing-L window ending at i-1 (population sd)."""
    hist = []
    for j in range(i):
        if j > 0 and abs(rows[j]["s"] - rows[j - 1]["s"]) > 0.15:
            hist = []
        hist.append(rows[j]["s"])
    if len(hist) < L:
        return None
    w = hist[-L:]
    mu = sum(w) / L
    sd = math.sqrt(sum((x - mu) ** 2 for x in w) / L)
    return 0.0 if sd <= 0 else (rows[i]["s"] - mu) / sd


def dualclass_live_step(session_date: str, leg: dict, state_l3: dict, *,
                        allow_network: bool = True, cached_only: bool = False,
                        series: dict = None) -> dict:
    """Advance each pair's state machine to `session_date`; book any round-trip that closes today.

    State per pair (`state_l3['pos'][pairkey]`): {d_in, pa_in, pb_in, sgn, z_in, i_in}. Returns a
    record and the list of net returns settled THIS session (each a completed round-trip observation).

    `series` (optional) is a precomputed per-symbol daily-bar series (from `_dc_series`); when given
    it is used verbatim and NO fetch is made. This lets the SIZED L3 leg and its band-variant sibling
    L11 (DUALCLASS_EXIT10, exit |z|~1.0) share one series -- identical universe -> no second fetch.
    Passing `series=None` (the default) reproduces the original behaviour byte-for-byte.
    """
    sig = leg["signal"]
    L, K, EXIT, MAXH = sig["L"], sig["K_entry_abs_z"], sig["exit_abs_z"], sig["max_hold_days"]
    hs = leg["cost_bp"]["half_spread_by_symbol"]
    sec = leg["cost_bp"]["sec31_bp_per_sale"]
    borrow = leg["cost_bp"]["borrow_annual_bp_on_short"] / 1e4
    syms = sorted({s for p in leg["pairs"] for s in p})
    if series is None:
        series = _dc_series(session_date, syms, allow_network=allow_network, cached_only=cached_only)
    pos = state_l3.setdefault("pos", {})
    settled, opened, marks = [], [], []
    for a, b in leg["pairs"]:
        key = f"{a}/{b}"
        rows = _dc_pair_rows(series, a, b)
        if not rows or rows[-1]["d"] != session_date:
            continue  # this pair did not print today; leave its state untouched
        i = len(rows) - 1
        z = _dc_z_at(rows, i, L)
        if z is None:
            continue
        held_pos = pos.get(key)
        if held_pos:
            held = sum(1 for r in rows if r["d"] > held_pos["d_in"])
            if abs(z) <= EXIT or held >= MAXH:
                sgn = held_pos["sgn"]
                ra_ = rows[i]["pa"] / held_pos["pa_in"] - 1.0
                rb_ = rows[i]["pb"] / held_pos["pb_in"] - 1.0
                gross = sgn * (ra_ - rb_)
                cost = 2 * (hs[a] / 1e4 + hs[b] / 1e4) + 2 * sec / 1e4 + borrow * held / 252.0
                net = gross - cost
                settled.append(net)
                marks.append({"pair": key, "d_in": held_pos["d_in"], "d_out": session_date,
                              "held": held, "net_bp": net * 1e4, "z_in": held_pos["z_in"]})
                pos.pop(key, None)
                continue
        if not held_pos and abs(z) >= K and rows[i]["dv"] >= sig["min_dollar_volume"] \
                and min(rows[i]["px_a"], rows[i]["px_b"]) >= sig["min_price"]:
            short_sym = a if z > 0 else b
            if not _dc_etb_ok(short_sym, leg):
                opened.append({"pair": key, "skipped": "short leg not easy-to-borrow (guard)",
                               "short_sym": short_sym})
                continue
            pos[key] = {"d_in": session_date, "pa_in": rows[i]["pa"], "pb_in": rows[i]["pb"],
                        "sgn": -1 if z > 0 else 1, "z_in": z, "i_in": i}
            opened.append({"pair": key, "opened": True, "sgn": pos[key]["sgn"], "z": round(z, 2)})
    return {"status": leg["status"], "settled_here": settled, "marks": marks,
            "opened": opened, "open_positions": len(pos)}


def dualclass_proof(leg: dict) -> dict:
    """PROOF: run the frozen engine over the cached t28 held-out window with the ETB guard applied.

    Reproduces the frozen prior; every number is a selection-inflated upper bound, NOT ledger evidence.
    """
    import statistics as _st
    quotes = json.loads((T28_CACHE / "quotes.json").read_text())
    lo, hi = "2022-01-03", "2026-08-18"
    acc = {}
    for d, row in quotes.items():
        if lo <= d <= hi:
            for s, v in row.items():
                acc.setdefault(s, []).append(v)
    sp = {s: (_st.median(v) / 1e4) if len(v) >= 3 else None for s, v in acc.items()}
    syms = sorted({s for p in leg["pairs"] for s in p})
    series = _dc_series(hi, syms, allow_network=False, cached_only=True)
    sig = leg["signal"]
    L, K, EXIT, MAXH = sig["L"], sig["K_entry_abs_z"], sig["exit_abs_z"], sig["max_hold_days"]
    sec = leg["cost_bp"]["sec31_bp_per_sale"]
    borrow = leg["cost_bp"]["borrow_annual_bp_on_short"] / 1e4
    nets, n_raw = [], 0
    for a, b in leg["pairs"]:
        if sp.get(a) is None or sp.get(b) is None:
            continue
        rows = [r for r in _dc_pair_rows(series, a, b) if lo <= r["d"] <= hi]
        if len(rows) < L + 30:
            continue
        hist, pos = [], None
        for i, r in enumerate(rows):
            if i > 0 and abs(r["s"] - rows[i - 1]["s"]) > 0.15:
                hist = []
                pos = None
            z = None
            if len(hist) >= L:
                w = hist[-L:]; mu = sum(w) / L
                sd = math.sqrt(sum((x - mu) ** 2 for x in w) / L)
                z = 0.0 if sd <= 0 else (r["s"] - mu) / sd
            if pos and z is not None:
                held = i - pos["i"]
                if abs(z) <= EXIT or held >= MAXH or i == len(rows) - 1:
                    gross = pos["sgn"] * ((r["pa"] / pos["pa"] - 1) - (r["pb"] / pos["pb"] - 1))
                    cost = 2 * (sp[a] / 2 + sp[b] / 2) + 2 * sec / 1e4 + borrow * held / 252.0
                    n_raw += 1
                    if _dc_etb_ok(a if pos["z"] > 0 else b, leg):
                        nets.append(gross - cost)
                    pos = None
            if not pos and len(hist) >= L and z is not None and abs(z) >= K \
                    and r["dv"] >= sig["min_dollar_volume"] \
                    and min(r["px_a"], r["px_b"]) >= sig["min_price"]:
                pos = {"i": i, "pa": r["pa"], "pb": r["pb"], "sgn": -1 if z > 0 else 1, "z": z}
            hist.append(r["s"])
    n = len(nets)
    mean = sum(nets) / n if n else None
    sd = math.sqrt(sum((x - mean) ** 2 for x in nets) / (n - 1)) if n > 1 else None
    return {"leg": "DUALCLASS", "window": [lo, hi], "n_round_trips_etb_screened": n,
            "n_round_trips_before_screen": n_raw,
            "mean_net_bp_per_round_trip": (mean * 1e4) if mean is not None else None,
            "t_stat": (mean / (sd / math.sqrt(n))) if sd else None,
            "NOT_LEDGER_EVIDENCE": "cached held-out window; selection-inflated upper bound"}


# ---------------------------------------------------------------------------
# L4 -- T7 ex-open dividend residual: cum-close(t) -> ex-open(t+1), 50% short SPY
# ---------------------------------------------------------------------------

def _t7_universe(top_n: int):
    import scripts.t7_evaluate as ev  # noqa: PLC0415
    return ev.universe_sets(top_n)


def _t7_dividends():
    """{ex_date: [(symbol, rate, special)]} cash dividends from the frozen t7 corp-actions cache."""
    import gzip as _gz  # noqa: PLC0415
    with _gz.open(T7_CACHE / "corporate_actions_all.json.gz", "rt") as fh:
        doc = json.load(fh)
    out = {}
    for rec in doc.get("cash_dividends", []):
        ex, sym, rate = rec.get("ex_date"), rec.get("symbol"), rec.get("rate")
        if ex and sym and rate is not None:
            out.setdefault(ex, []).append((sym, float(rate), bool(rec.get("special"))))
    return out


def t7_mark_exdate(ex_date: str, cum_date: str, leg: dict, *, allow_network: bool = True) -> dict:
    """Settle L4 for one ex-date: fetch cum-close + ex-open auctions, compute the portfolio net."""
    _assert_asof((cum_date, "16:00"), (ex_date, "09:30"), "T7")
    uni = _t7_universe(leg["universe"]["top_n"])
    allowed = uni.get(cum_date[:7], set()) & uni.get(ex_date[:7], set())
    divs = _t7_dividends().get(ex_date, [])
    max_y = leg["universe"]["max_yield"]
    names = sorted({s for s, _r, _sp in divs if s in allowed})
    if not names:
        return {"phase": "no_events", "settled": None, "note": "no eligible ex-div names this date"}
    au = _auctions(ex_date, names + ["SPY"])
    au_cum = _auctions(cum_date, names + ["SPY"])
    spy_c = (au_cum.get("SPY") or {}).get("c")
    spy_o = (au.get("SPY") or {}).get("o")
    if not spy_c or not spy_o:
        raise Refused(f"missing SPY auction print for L4 {cum_date}->{ex_date}; leaving pending")
    r_spy = spy_o / spy_c - 1.0
    rate_by = {}
    for s, r, sp in divs:
        rate_by[s] = rate_by.get(s, 0.0) + r
    rows, prices = [], []
    for s in names:
        p_cum = (au_cum.get(s) or {}).get("c")
        o = (au.get(s) or {}).get("o")
        rate = rate_by.get(s, 0.0)
        if not p_cum or p_cum <= 0 or not o or o <= 0 or rate / p_cum > max_y:
            continue
        rows.append((o - p_cum + rate) / p_cum)
        prices.append((p_cum, o))
    if not rows:
        raise Refused(f"no priced ex-div legs for L4 {ex_date}; leaving pending, not fabricating")
    k = len(rows)
    g = 0.5 * sum(rows) / k - 0.5 * r_spy
    c = leg["cost_bp"]
    gap = max(1, (dt.date.fromisoformat(ex_date) - dt.date.fromisoformat(cum_date)).days)
    taf = c["taf_micros_per_share"] / 1e6
    inv_buy = sum(1.0 / p[0] for p in prices) / k
    inv_sell = sum(1.0 / p[1] for p in prices) / k
    cost = c["sec31_bp_on_sold"] / 1e4 + taf * 0.5 * (inv_buy + inv_sell) \
        + taf * 1.0 / spy_c + c["short_fraction"] * (c["borrow_annual_bp_on_spy_short"] / 1e4) \
        * gap / 365.25
    return {"phase": "settled", "settled": {"cum_date": cum_date, "ex_date": ex_date,
            "n_events": k, "gross_return": g, "net_return": g - cost, "calendar_gap": gap,
            "observation": "one ex-date event-day portfolio (long ex-div names, 50% short SPY)"},
            "asof": {"signal_et": (cum_date, "16:00"), "mark_et": (ex_date, "09:30")}}


def t7_proof(spine: list, *, allow_network: bool = True) -> dict:
    """PROOF: settle the most-recent COMPLETE ex-date present in the frozen t7 panel. One noisy obs."""
    import gzip as _gz  # noqa: PLC0415
    with _gz.open(T7_CACHE / "panel.json.gz", "rt") as fh:
        panel = json.load(fh)["panel"]
    complete = set(spine)
    for ex in sorted(panel, reverse=True):
        cum = panel[ex].get("cum")
        if ex in complete and cum in complete and panel[ex].get("events"):
            marked = t7_mark_exdate(ex, cum, leg_by_id(frozen_spec(), "T7"),
                                    allow_network=allow_network)
            marked["proof_note"] = ("one recent ex-date, noisy; frozen held-out reference is "
                                    "+3.347 bp/event-day, t 2.96, n 1018 (NOT ledger evidence)")
            return marked
    raise Refused("no complete ex-date in the t7 panel intersects the session spine for an L4 proof")


# ---------------------------------------------------------------------------
# L5 -- T12 CEF discount-level tilt: weekly snapshot, 4-week overlapping tranches
# ---------------------------------------------------------------------------

def _l5_flags():
    import gzip as _gz  # noqa: PLC0415
    with _gz.open(T12_CACHE / "alpaca_assets.json.gz", "rt") as fh:
        return json.load(fh)


def l5_book_from_rows(rows: list, flags: dict, leg: dict) -> dict:
    """Rank the borrowable price>$5 CEF snapshot by discount -> {long:[(sym,price)], short:[...]}. """
    n = leg["signal"]["n_side"]
    pmin = leg["universe"]["price_min"]
    cand = []
    for r in rows:
        t = r.get("Ticker"); disc = r.get("Discount"); px = r.get("Price")
        if not t or disc is None or px is None or px <= pmin:
            continue
        if not (flags.get(t) or {}).get("easy_to_borrow"):
            continue  # borrowable-short screen (applies to the whole ranked universe)
        cand.append((t, float(disc), float(px)))
    cand.sort(key=lambda x: x[1])            # most-negative discount (widest) first
    longs = [(t, p) for t, _d, p in cand[:n]]
    shorts = [(t, p) for t, _d, p in cand[-n:]]
    return {"long": longs, "short": shorts, "n_universe": len(cand)}


def _l5_costs(leg: dict, turnover_frac: float, hold_days: float) -> float:
    c = leg["cost_bp"]
    g = leg["guard_mandatory"]
    hs = c["half_spread_bp"] / 1e4
    borrow = g["borrow_annual_bp_on_short_realised"] / 1e4
    # half-spread on realised turnover (both entry+exit implied by turnover), SEC31 on sold,
    # borrow realised on the short leg over the hold
    return hs * turnover_frac + c["sec31_bp_on_sold"] / 1e4 + borrow * hold_days / 365.25


def l5_live_step(session_date: str, leg: dict, state_l5: dict, spine_before: list, *,
                 allow_network: bool = True) -> dict:
    """Weekly rebalance on the live CEFConnect snapshot; overlapping 4-week tranches; settle the
    tranche completing its hold. At inception this enters tranche 1 and settles nothing."""
    hold_wk = leg["signal"]["hold_weeks"]
    tranches = state_l5.setdefault("tranches", [])
    last_reb = state_l5.get("last_rebalance")
    # weekly cadence: rebalance if >=5 trading sessions since the last L5 rebalance (or first ever)
    since = len([d for d in spine_before if last_reb and d > last_reb]) if last_reb else 999
    if last_reb == session_date:
        return {"status": leg["status"], "phase": "already_rebalanced_today", "settled_here": None}
    if last_reb is not None and since < 5:
        return {"status": leg["status"], "phase": "not_a_rebalance_session", "settled_here": None,
                "open_tranches": len(tranches)}
    rows = _cef_snapshot(session_date, allow_network=allow_network)
    flags = _l5_flags()
    book = l5_book_from_rows(rows, flags, leg)
    px_now = {r["Ticker"]: r.get("Price") for r in rows if r.get("Ticker")}
    settled_here = None
    # settle the oldest tranche if it has completed hold_wk rebalances
    matured = [t for t in tranches if t["age"] + 1 >= hold_wk]
    if matured:
        tr = matured[0]
        lr, sr = [], []
        for s, p0 in tr["long"]:
            p1 = px_now.get(s)
            if p1 and p0:
                lr.append(p1 / p0 - 1.0)
        for s, p0 in tr["short"]:
            p1 = px_now.get(s)
            if p1 and p0:
                sr.append(p1 / p0 - 1.0)
        if lr and sr:
            gross = sum(lr) / len(lr) - sum(sr) / len(sr)
            cost = _l5_costs(leg, turnover_frac=2.0, hold_days=hold_wk * 7)  # full round trip / tranche
            net4wk = gross - cost
            settled_here = {"entry_date": tr["entry_date"], "exit_date": session_date,
                            "hold_weeks": hold_wk, "net_return_4wk": net4wk,
                            "net_return_per_week_equiv": net4wk / hold_wk,
                            "n_long": len(lr), "n_short": len(sr),
                            "observation": "one 4-week overlapping tranche book"}
        tranches.remove(tr)
    for t in tranches:
        t["age"] += 1
    tranches.append({"entry_date": session_date, "age": 0,
                     "long": book["long"], "short": book["short"]})
    state_l5["last_rebalance"] = session_date
    return {"status": leg["status"], "phase": "rebalanced", "settled_here": settled_here,
            "open_tranches": len(tranches), "book_universe": book["n_universe"],
            "asof": {"signal": "discount snapshot at entry", "mark": "realised Price only (no NAV)"}}


def l5_proof(leg: dict) -> dict:
    """PROOF: run the overlapping-tranche engine over the cached t12 weekly discount history."""
    import gzip as _gz, statistics as _st  # noqa: PLC0415
    with _gz.open(T12_CACHE / "history_1Y.json.gz", "rt") as fh:
        hist = json.load(fh)
    flags = _l5_flags()
    n = leg["signal"]["n_side"]
    pmin = leg["universe"]["price_min"]
    alldates = sorted({r["date"] for t in hist if hist[t] for r in hist[t]})
    weekly = alldates[::5]

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
            if not (flags.get(t) or {}).get("easy_to_borrow"):
                continue
            pd = asof(t, d)
            if not pd or pd["price"] <= pmin:
                continue
            cand.append((t, pd["discount"], pd["price"]))
        cand.sort(key=lambda x: x[1])
        return cand[:n], cand[-n:]

    H = leg["signal"]["hold_weeks"]
    nets, i = [], 0
    while i + H < len(weekly):
        d0, d1 = weekly[i], weekly[i + H]
        longs, shorts = book(d0)
        lr = [asof(t, d1)["price"] / p0 - 1 for t, _dd, p0 in longs if asof(t, d1)]
        sr = [asof(t, d1)["price"] / p0 - 1 for t, _dd, p0 in shorts if asof(t, d1)]
        if lr and sr:
            gross = _st.fmean(lr) - _st.fmean(sr)
            cost = _l5_costs(leg, turnover_frac=2.0, hold_days=H * 7)
            nets.append(gross - cost)
        i += H
    m = _st.fmean(nets) if nets else None
    sd = _st.stdev(nets) if len(nets) > 1 else None
    return {"leg": "T12CEF", "n_nonoverlap_4wk_obs": len(nets),
            "mean_net_bp_per_4wk_obs": (m * 1e4) if m is not None else None,
            "mean_net_bp_per_week": (m * 1e4 / H) if m is not None else None,
            "t_stat": (m / (sd / math.sqrt(len(nets)))) if sd else None,
            "NOT_LEDGER_EVIDENCE": ("cached live-only t12 history (survivorship); the live leg uses "
                                    "the weekly CEFConnect snapshot. Selection-inflated upper bound.")}


# ---------------------------------------------------------------------------
# L6 -- ORB no-stop residual: opening-range breakout, exit MOC, same session
# ---------------------------------------------------------------------------

def _l6_selection(session_date: str):
    """The frozen top-20 'Stocks in Play' for a session from the t17 cache, or None if not built."""
    sel = json.loads((T17_CACHE / "selection.json").read_text())
    return sel.get(session_date)


def _l6_paths_cached(session_date: str):
    p = T17_CACHE / "paths" / f"{session_date}.json"
    return json.loads(p.read_text()) if p.exists() else None


def l6_settle(session_date: str, leg: dict, *, allow_network: bool = True,
              cached_only: bool = False) -> dict:
    """Compute L6's net return for `session_date`: breakout at the OR level, exit MOC, equal-weight
    over FIRED names. Uses the frozen selection (t17 cache) + the intraday path (cache or live)."""
    sel = _l6_selection(session_date)
    if not sel:
        return {"status": leg["status"], "phase": "no_selection",
                "note": ("the t17 'Stocks in Play' selection is not built for this session; it is a "
                         "maintained cache (like T3's monthly universe). Run the t17 collector for "
                         "this date before it can be logged."), "settled": None}
    paths = _l6_paths_cached(session_date)
    if paths is None:
        if cached_only:
            return {"status": leg["status"], "phase": "no_path_cache", "settled": None,
                    "note": "no cached 1-min path for this session"}
        syms = [row[1] for row in sel]
        paths = _l6_intraday_live(session_date, syms, allow_network=allow_network)
    entry_slip = leg["cost_bp"]["entry_slippage_bp"] / 1e4 + leg["cost_bp"]["sec_taf_bp"] / 1e4
    rets, fired = [], 0
    for relvol, sym, direction, or_hi, or_lo, atr in sel:
        bars = paths.get(sym)
        if not bars:
            continue
        orh, orl = or_hi / 1e6, or_lo / 1e6
        triggered = False
        for b in bars:               # rows [t,o,h,l,c,v]
            h, l = b[2], b[3]
            if direction == "long" and h >= orh:
                triggered = True; break
            if direction == "short" and l <= orl:
                triggered = True; break
        if not triggered:
            continue                 # NO_TRIGGER: no position (not a zero)
        level = orh if direction == "long" else orl
        if level <= 0:
            continue
        exitp = bars[-1][4]          # MOC official close (16:00 minute bar close = the cross)
        sign = 1.0 if direction == "long" else -1.0
        rets.append(sign * (exitp - level) / level - entry_slip)
        fired += 1
    if not fired:
        return {"status": leg["status"], "phase": "no_trigger_all_day", "settled": None,
                "n_selected": len(sel)}
    net = sum(rets) / len(rets)
    return {"status": leg["status"], "phase": "settled",
            "settled": {"exit_session": session_date, "net_return": net, "n_fired": fired,
                        "n_selected": len(sel), "observation": "one intraday ORB session (equal-wt over fired)"},
            "asof": {"signal_et": (session_date, "09:35"), "mark_et": (session_date, "16:00")}}


def _l6_intraday_live(session_date: str, syms: list, *, allow_network: bool = True) -> dict:
    """{sym: [[t,o,h,l,c,v]]} 1-min bars 09:35->16:00 ET for the selected names (live path)."""
    off = _ny_offset(session_date)
    start = f"{session_date}T{9 + off:02d}:35:00Z"
    end = f"{session_date}T{16 + off:02d}:01:00Z"
    out = {}
    for blocks in _data_get_paged("/v2/stocks/bars", {
            "symbols": ",".join(syms), "timeframe": "1Min", "start": start, "end": end,
            "limit": 10000, "feed": "sip", "adjustment": "raw"}, "bars"):
        for sym, bars in blocks.items():
            for b in bars:
                out.setdefault(sym, []).append([b["t"], b["o"], b["h"], b["l"], b["c"], b.get("v", 0)])
    return out


def l6_proof(leg: dict) -> dict:
    """PROOF: run the frozen ORB spec over the cached t17 held-out window (offline, no network)."""
    import statistics as _st  # noqa: PLC0415
    sel = json.loads((T17_CACHE / "selection.json").read_text())
    days = sorted(d for d in sel if "2022-01-03" <= d <= "2026-08-14")
    daily = []
    for d in days:
        rec = l6_settle(d, leg, allow_network=False, cached_only=True)
        if rec.get("settled"):
            daily.append(rec["settled"]["net_return"])
    n = len(daily)
    m = _st.fmean(daily) if n else None
    sd = _st.stdev(daily) if n > 1 else None
    return {"leg": "ORB", "sessions": n,
            "mean_net_bp_per_day": (m * 1e4) if m is not None else None,
            "t_stat": (m / (sd / math.sqrt(n))) if sd else None,
            "ann_sharpe": (m / sd * math.sqrt(TRADING_DAYS)) if sd else None,
            "NOT_LEDGER_EVIDENCE": "cached held-out window; post-hoc variant, selection-inflated upper bound"}


# ---------------------------------------------------------------------------
# L7 -- XS_GLSR_Z crypto-perp account-positioning fade (+ L8 XS_SMART, unsized sibling)
# ---------------------------------------------------------------------------
# L7/L8 read ONE added read-only LOCAL cache: the frozen 1h Binance USD-M perp panel
# (research/data/perpmicro_cache/panel1h.npz, built by perpmicro_panel.py from the orphanflush
# cache). NO crypto venue, NO key, NO order -- only the already-downloaded panel. The frozen engine
# that produced the dossier (scripts.trading_bot.perpmicro_sweep) is reused verbatim, driven entirely
# by the frozen leg spec (top_n, quantile, min_names, cost, sign); nothing is re-typed.

PERP_PANEL = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h.npz"


def _perp_heldout_record(leg: dict) -> dict:
    """PROOF: run the FROZEN perp-sweep engine on the cached 1h panel over the held-out window, on
    this leg's frozen TOP-N universe with its frozen SIGN. Reproduces the dossier's DEPLOYABLE number.

    Every value is a selection-inflated UPPER BOUND on a single held-out regime -- NOT ledger evidence.
    The +34.5%/yr / net Sharpe 2.38 headline is the top-120 FULL-UNIVERSE bound; the deployable top-50
    net Sharpe (~0.73 for L7) is the honest one and is what this reproduces.
    """
    import numpy as np  # noqa: PLC0415
    import scripts.trading_bot.perpmicro_sweep as sw  # noqa: PLC0415
    if not PERP_PANEL.exists():
        raise Refused(f"perp panel cache {PERP_PANEL} is missing; L7/L8 cannot compute. Rebuilding it "
                      "(perpmicro_panel.py from the orphanflush cache) is maintenance, not an edit to "
                      "the frozen leg.")
    u, sig = leg["universe"], leg["signal"]
    sw.TOP_N = u["top_n"]                          # frozen deployable universe (top-50)
    sw.MIN_NAMES = u["min_names"]
    sw.QUANTILE = sig["quantile"]
    sw.COST_SIDE_BP = leg["cost_bp"]["cost_side_bp"]
    pan = np.load(sw.PANEL, allow_pickle=True)
    p = sw.build_features(pan)
    F = [f for f in sw.catalogue(p) if f[0] == leg["id"]]
    if not F:
        raise Refused(f"formula {leg['id']!r} is not in the frozen perp catalogue")
    signs = {leg["id"]: float(sig["sign"])}        # sign FROZEN in the leg spec, never re-searched
    hmask = sw.window_mask(p.t, *sw.HELDOUT)
    hres, _ = sw.run_window(F, p, hmask, signs=signs)
    x = hres[0]
    return {"leg": leg["id"], "universe_top_n": u["top_n"],
            "cost_side_bp": leg["cost_bp"]["cost_side_bp"],
            "heldout_window": list(sw.HELDOUT), "n_days": int(x["ndays"]),
            "sign_frozen": float(sig["sign"]),
            "deployable_top50_heldout_net_sharpe": float(x["sharpe_net"]),
            "heldout_gross_sharpe": float(x["sharpe_gross"]),
            "heldout_ann_net_pct": float(x["ann_ret_net"]) * 100.0,
            "breakeven_cost_bp_per_side": float(x["breakeven_cost_bp_per_side"]),
            "mean_daily_net_return": float(x["ann_ret_net"]) / 365.0,
            "turnover_per_day": float(x["turnover_per_day"]),
            "NOT_LEDGER_EVIDENCE": (
                "cached top-N held-out window (single regime, sign frozen from design); "
                "selection-inflated upper bound, not forward evidence. Deployable top-50 is the "
                "honest number; the top-120 full-universe figure is the upper bound.")}


def _perp_live_step(session_date: str, leg: dict) -> dict:
    """Forward settlement of a perp leg for a UTC session. The frozen 1h panel ends where the Binance
    metrics feed dies (2024-12); a forward row needs the panel extended to `session_date`. Until then
    -- exactly like L6/ORB with an unbuilt selection -- record the gate and contribute NOTHING; a
    phantom mark is never fabricated. Freeze precedes observation; backfill only from freeze forward.
    """
    if not PERP_PANEL.exists():
        return {"status": leg["status"], "phase": "no_perp_panel", "settled": None,
                "note": "perp panel cache absent; L7/L8 forward settlement pending a panel rebuild"}
    import numpy as np  # noqa: PLC0415
    pan = np.load(PERP_PANEL, allow_pickle=True)
    last_day = dt.datetime.fromtimestamp(int(pan["t"][-1]) / 1000, dt.timezone.utc).date().isoformat()
    if session_date > last_day:
        return {"status": leg["status"], "phase": "no_forward_panel", "settled": None,
                "note": (f"the frozen 1h perp panel ends {last_day} (Binance metrics feed dies "
                         f"2024-12); forward settlement for {session_date} is pending a maintained "
                         "panel extension. No phantom mark is fabricated.")}
    return {"status": leg["status"], "phase": "in_panel_pre_freeze", "settled": None,
            "note": "session lies inside the frozen design/held-out panel; not a forward row"}


# ---------------------------------------------------------------------------
# L9 -- CEFMUNIEQ muni+equity CEF discount-LEVEL tilt (Y05, H=1 week, satellite)
# ---------------------------------------------------------------------------
# Reuses the L5 CEFConnect fetch (_cef_snapshot) + the L5 easy-to-borrow flags (_l5_flags), plus the
# frozen CEFConnect category statics (t12_cache/universe.json.gz) to restrict to MUNI+EQUITY. Marking
# is on Alpaca distribution-adjusted daily closes (adjustment=all), lagged one trading day.

_CEF_TAXFI = (
    "Morningstar US CEF High Yield", "Morningstar US CEF Senior Loans",
    "Morningstar US CEF Investment Grade", "Morningstar US CEF Preferreds",
    "Morningstar US CEF Multi-Sector", "Morningstar US CEF Global Income",
    "Morningstar US CEF Convertibles", "Morningstar US CEF Limited Duration",
    "Morningstar US CEF Emerging Market Income")


def _cef_group(cat: str) -> str:
    """Mirror scripts.trading_bot.deepmine_cefnav.group(): MUNI / TAXFI / HYBRID / EQUITY."""
    c = cat or ""
    if "Municipal" in c or "Taxable Muni" in c:
        return "MUNI"
    if c in _CEF_TAXFI:
        return "TAXFI"
    if "Allocation" in c:
        return "HYBRID"
    return "EQUITY"


def _cefmunieq_statics() -> dict:
    """{ticker: CategoryName} from the frozen CEFConnect statics (reused from the t12 cache)."""
    import gzip as _gz  # noqa: PLC0415
    with _gz.open(T12_CACHE / "universe.json.gz", "rt") as fh:
        uni = json.load(fh)
    return {r["Ticker"]: (r.get("CategoryName") or "?") for r in uni if r.get("Ticker")}


def cefmunieq_book_from_rows(rows: list, flags: dict, statics: dict, leg: dict) -> dict:
    """MUNI+EQUITY, price>$5, decile long widest-discount / short narrowest (ETB-screened)."""
    frac = leg["signal"]["frac"]
    pmin = leg["universe"]["price_min"]
    cand = []
    for r in rows:
        t = r.get("Ticker"); disc = r.get("Discount"); px = r.get("Price")
        if not t or disc is None or px is None or px <= pmin:
            continue
        if _cef_group(statics.get(t)) not in ("MUNI", "EQUITY"):
            continue  # signal-defining restriction: taxable-credit excluded
        cand.append((t, float(disc), float(px)))
    cand.sort(key=lambda x: x[1])                 # most-negative discount (widest) first = LONG
    n = max(1, int(round(len(cand) * frac)))
    longs = [t for t, _d, _p in cand[:n]]
    shorts = [t for t, _d, _p in cand[-n:]
              if (flags.get(t) or {}).get("easy_to_borrow")]   # short leg must be borrowable
    return {"long": longs, "short": shorts, "n_universe": len(cand)}


def cefmunieq_live_step(session_date: str, leg: dict, state_l9: dict, spine_before: list, *,
                        allow_network: bool = True) -> dict:
    """Weekly H=1 rebalance on the 1-day-LAGGED CEFConnect discount snapshot, marked on Alpaca
    distribution-adjusted closes. One open tranche at a time (H=1). Settles the tranche completing
    its 1-week hold. p90 (27.25 bp) half-spread both legs on realised turnover + 200 bp/yr borrow."""
    last_reb = state_l9.get("last_rebalance")
    if last_reb == session_date:
        return {"status": leg["status"], "phase": "already_rebalanced_today", "settled_here": None}
    since = len([d for d in spine_before if last_reb and d > last_reb]) if last_reb else 999
    if last_reb is not None and since < 5:
        return {"status": leg["status"], "phase": "not_a_rebalance_session", "settled_here": None,
                "open_tranche": bool(state_l9.get("open_tranche"))}
    # MANDATORY 1-trading-day implementation lag: the signal is the snapshot cached for the PRIOR
    # session (CEFConnect publishes NAV after the close). Only a cached prior snapshot is used --
    # never a same-day fetch pretending to be yesterday's.
    signal_day = spine_before[-1] if spine_before else None
    sp = (CEF_SNAP_CACHE / f"{signal_day}.json") if signal_day else None
    if not signal_day or sp is None or not sp.exists():
        if allow_network:
            _cef_snapshot(session_date, allow_network=allow_network)  # seed today's for a future lag
        return {"status": leg["status"], "phase": "warmup_no_lagged_snapshot", "settled_here": None,
                "note": ("the mandatory 1-trading-day lag needs the prior session's cached CEF "
                         "snapshot; none on disk yet -- seeding today's, settling/entering nothing.")}
    rows = json.loads(sp.read_text())
    flags = _l5_flags()
    statics = _cefmunieq_statics()
    book = cefmunieq_book_from_rows(rows, flags, statics, leg)
    if len(book["long"]) < 3 or len(book["short"]) < 1:
        return {"status": leg["status"], "phase": "thin_book", "settled_here": None,
                "book_universe": book["n_universe"]}
    prev = state_l9.get("open_tranche")
    need = sorted(set(book["long"]) | set(book["short"]) | set((prev or {}).get("W", {})))
    start = (dt.date.fromisoformat(session_date) - dt.timedelta(days=20)).isoformat()
    bars = _daily_bars(need, start, session_date, "all", allow_network=allow_network)

    def adj_close(sym):
        vals = [b["c"] for b in (bars.get(sym) or [])
                if b["d"] <= session_date and b["c"] and b["c"] > 0]
        return vals[-1] if vals else None

    nl, ns = len(book["long"]), len(book["short"])
    Wk = {t: 0.5 / nl for t in book["long"]}
    for t in book["short"]:
        Wk[t] = Wk.get(t, 0.0) - 0.5 / ns
    prevW = state_l9.get("prev_W") or {}
    turn = sum(abs(Wk.get(t, 0.0) - prevW.get(t, 0.0)) for t in set(Wk) | set(prevW))
    hs = leg["cost_bp"]["half_spread_bp"] / 1e4
    sec = leg["cost_bp"]["sec31_bp_on_sold"] / 1e4
    entry_cost = turn * hs + 0.5 * turn * sec
    entry_px = {t: adj_close(t) for t in Wk}

    settled_here = None
    if prev:
        gross = 0.0
        for t, w in prev["W"].items():
            p0 = (prev.get("entry_px") or {}).get(t)
            p1 = adj_close(t)
            if p0 and p1:
                gross += w * (p1 / p0 - 1.0)
        borrow = sum(-w for w in prev["W"].values() if w < 0) \
            * (leg["cost_bp"]["borrow_annual_bp_on_short_realised"] / 1e4) * 7.0 / 365.0
        net = gross - prev.get("entry_cost", 0.0) - borrow
        settled_here = {"entry_date": prev["entry_date"], "exit_date": session_date,
                        "hold_weeks": leg["signal"]["hold_weeks"], "gross_return": gross,
                        "net_return_1wk": net,
                        "n_long": sum(1 for w in prev["W"].values() if w > 0),
                        "n_short": sum(1 for w in prev["W"].values() if w < 0),
                        "observation": "one 1-week muni+equity CEF decile tranche"}

    state_l9["open_tranche"] = {"entry_date": session_date, "W": Wk, "entry_px": entry_px,
                                "entry_cost": entry_cost}
    state_l9["prev_W"] = Wk
    state_l9["last_rebalance"] = session_date
    return {"status": leg["status"], "phase": "rebalanced", "settled_here": settled_here,
            "open_tranche": True, "book_universe": book["n_universe"],
            "asof": {"signal": f"lagged discount snapshot {signal_day}",
                     "mark": "distribution-adjusted close only (never NAV)"}}


def cefmunieq_proof(leg: dict) -> dict:
    """PROOF: reproduce the frozen Y05 muni+equity H=1 held-out numbers on the cached CEFConnect
    panel via the deepmine_cefnav engine. The STRESSED number (1-day lag + p90 27.25bp both legs +
    200bp borrow) is the honest one. Selection-inflated upper bound -- NOT ledger evidence."""
    import math as _m  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    import scripts.trading_bot.deepmine_cefnav as dm  # noqa: PLC0415
    pnl = dm.build_panel()
    grid, D, grp = pnl["grid"], pnl["D"], pnl["grp"]
    T, _N = D.shape
    split_k = next(k for k, d in enumerate(grid) if d >= dm.SPLIT)
    k_end = T - 1
    mask = np.tile((grp == "MUNI") | (grp == "EQUITY"), (T, 1))
    H = leg["signal"]["hold_weeks"]
    W, counts = dm.book_from_score(-D, pnl, H=H, mask=mask, frac=leg["signal"]["frac"])
    hs_p90 = leg["cost_bp"]["half_spread_bp"]

    def stats(x):
        v = x[:, 1]; v = v[np.isfinite(v)]
        if len(v) < 2:
            return (0, None, None, None)
        m = float(v.mean()); sd = float(v.std(ddof=1))
        sh = (m / sd * _m.sqrt(52)) if sd else None
        t = (m / (sd / _m.sqrt(len(v)))) if sd else None
        return (len(v), m, sh, t)

    des = dm.net_series(W, pnl, 0, split_k, rkey="R", half_spread_bp=11.53)
    hmeas = dm.net_series(W, pnl, max(0, split_k), k_end, rkey="R", half_spread_bp=11.53)
    hstr = dm.net_series(W, pnl, max(0, split_k), k_end, rkey="R_LAG1", half_spread_bp=hs_p90)
    nd, md, shd, td = stats(des)
    nm, mm, shm, tm = stats(hmeas)
    ns_, ms, shs, ts = stats(hstr)
    return {"leg": "CEFMUNIEQ", "hold_weeks": H, "split": dm.SPLIT,
            "median_book_long_short": [int(np.median([c[0] for c in counts])),
                                       int(np.median([c[1] for c in counts]))],
            "design_net_bp_per_wk_at_11p53": (md * 1e4) if md is not None else None,
            "design_ann_sharpe": shd, "design_t": td, "design_n_wk": nd,
            "heldout_net_bp_per_wk_at_11p53_nolag": (mm * 1e4) if mm is not None else None,
            "heldout_ann_sharpe": shm, "heldout_t": tm,
            "heldout_STRESSED_net_bp_per_wk": (ms * 1e4) if ms is not None else None,
            "heldout_STRESSED_ann_sharpe": shs, "heldout_STRESSED_t": ts, "heldout_STRESSED_n_wk": ns_,
            "mean_net_bp_per_week": (ms * 1e4) if ms is not None else None,
            "NOT_LEDGER_EVIDENCE": (
                "cached CEFConnect design/held-out panel (Y05 muni+equity decile, H=1). The STRESSED "
                "number (mandatory 1-trading-day lag + p90 27.25bp both legs + 200bp/yr borrow) is the "
                "honest one; the +33.26 bp/wk figure is the pre-stress upper bound. Selection-inflated; "
                "the live leg fetches the weekly CEFConnect snapshot forward.")}


# ---------------------------------------------------------------------------
# L12 -- CRYPTO_LOWVOL: cross-sectional realised-vol on Binance spot USDT top-50 (UNSIZED)
# ---------------------------------------------------------------------------
# L12 reads ONE added read-only LOCAL cache: the frozen Binance spot daily panel
# (research/data/xspot_cache/spot_daily.npz, built by the inv0822b crypto-spot fetch/sweep). NO
# crypto venue, NO key, NO order -- only the already-downloaded panel, exactly as L7/L8 read the
# frozen perp panel. The frozen engine that produced the dossier (scripts.trading_bot.inv0822b_xs_lib
# + inv0822b_xs_forms) is reused verbatim, driven entirely by the frozen leg spec (top_n, extreme_k,
# adv_floor, adv_lookback, hold_days, sign, cost); nothing is re-typed.

SPOT_PANEL = ROOT / "research" / "data" / "xspot_cache" / "spot_daily.npz"
_INV0822B_DIR = str(ROOT / "scripts" / "trading_bot")


def _lowvol_engine():
    """Import the frozen inv0822b crypto-XS engine (added to sys.path once)."""
    if _INV0822B_DIR not in sys.path:
        sys.path.insert(0, _INV0822B_DIR)
    import inv0822b_xs_lib as lib       # noqa: PLC0415
    import inv0822b_xs_forms as forms   # noqa: PLC0415
    return lib, forms


def _lowvol_book(leg: dict):
    """Build L12's frozen signed book on the cached spot panel. Returns (lib, dates, sw, R) where
    sw is the FINAL signed weight matrix (sw>0 = LONG low-vol, sw<0 = SHORT high-vol) and R is the
    VWAP(t)->VWAP(t+1) return panel. Every parameter is read from the frozen leg spec."""
    import numpy as np  # noqa: PLC0415
    if not SPOT_PANEL.exists():
        raise Refused(f"spot panel cache {SPOT_PANEL} is missing; L12 cannot compute. Rebuilding it "
                      "(the inv0822b crypto-spot fetch) is maintenance, not an edit to the frozen "
                      "leg, and MUST run as a detached background subprocess, never inline.")
    lib, forms = _lowvol_engine()
    u, sig_spec = leg["universe"], leg["signal"]
    P = lib.load(str(SPOT_PANEL))
    F = lib.features(P)
    U = lib.universe(P, F, top=u["top_n"], adv_floor=u["adv_floor_usd"],
                     lookback=u["adv_lookback_days"])
    btc = int(np.where(P["syms"] == "BTCUSDT")[0][0])
    R = lib.fwd_ret(F)
    fam, sig = forms.build(P, F, U, btc)["S1_VOL30"]
    w1 = lib.extremes_book(sig, U, k=u["extreme_k"])
    w = lib.tranche(w1, sig_spec["hold_days"])
    sw = float(sig_spec["sign"]) * w                    # LONG low-vol (+), SHORT high-vol (-)
    return lib, P["dates"], sw, R


def _lowvol_stats(lib, sw, R, mask, cost_side_bp: float) -> dict:
    """Net/gross Sharpe over `mask`, plus the LONG (low-vol) and SHORT (high-vol) sleeves logged
    SEPARATELY (so the gate-4 short-leg-fraction kill-switch is computable). Mirrors the sweep's
    evaluate(): cost = fee_bp * sum|dw| on turnover."""
    import numpy as np  # noqa: PLC0415
    Rn = np.nan_to_num(R)
    gross = (sw * Rn).sum(0)
    dw = np.abs(np.diff(np.nan_to_num(sw), axis=1, prepend=0.0)).sum(0)
    net = gross - dw * cost_side_bp * 1e-4
    long_pnl = (np.where(sw > 0, sw, 0.0) * Rn).sum(0)
    short_pnl = (np.where(sw < 0, sw, 0.0) * Rn).sum(0)
    gl = float(long_pnl[mask].sum())
    gs = float(short_pnl[mask].sum())
    denom = abs(gl) + abs(gs)
    return {"net_sharpe": lib.sharpe(net[mask]), "net_t": lib.tstat(net[mask]),
            "gross_sharpe": lib.sharpe(gross[mask]),
            "long_sleeve_sharpe": lib.sharpe(long_pnl[mask]),
            "short_sleeve_sharpe": lib.sharpe(short_pnl[mask]),
            "long_sleeve_ann_ret_pct": float(long_pnl[mask].mean() * 365.0 * 100.0),
            "short_sleeve_ann_ret_pct": float(short_pnl[mask].mean() * 365.0 * 100.0),
            "short_leg_gross_fraction": (abs(gs) / denom) if denom > 0 else None,
            "net_ann_ret_pct": float(net[mask].mean() * 365.0 * 100.0),
            "turnover_per_day": float(dw[mask].mean()),
            "n_days": int(mask.sum())}


def _lowvol_heldout_record(leg: dict) -> dict:
    """PROOF: run the FROZEN inv0822b crypto-XS engine on the cached spot panel over the held-out
    window (2023-01-01..2026-08-01), reproducing the dossier's DEPLOYABLE S1_VOL30|H20 number, with
    the LONG and SHORT sleeves separated. Every value is a selection-inflated UPPER BOUND on a spent
    single window (sign frozen from design) -- NOT ledger evidence."""
    import datetime as _dt  # noqa: PLC0415
    lib, dates, sw, R = _lowvol_book(leg)
    d1, h1 = _dt.date(2023, 1, 1), _dt.date(2026, 8, 1)
    hmask = (dates >= d1) & (dates < h1)
    cost = leg["cost_bp"]["cost_side_bp"]
    st = _lowvol_stats(lib, sw, R, hmask, cost)
    st20 = _lowvol_stats(lib, sw, R, hmask, 20.0)   # 20 bp/side cost shock
    return {"leg": leg["id"], "universe_top_n": leg["universe"]["top_n"],
            "extreme_k": leg["universe"]["extreme_k"], "hold_days": leg["signal"]["hold_days"],
            "sign_frozen": float(leg["signal"]["sign"]), "cost_side_bp": cost,
            "heldout_window": [str(d1), str(h1)], "n_days": st["n_days"],
            "deployable_heldout_net_sharpe": st["net_sharpe"], "heldout_net_t": st["net_t"],
            "heldout_gross_sharpe": st["gross_sharpe"], "heldout_net_ann_ret_pct": st["net_ann_ret_pct"],
            "heldout_net_sharpe_at_20bp_shock": st20["net_sharpe"],
            "long_sleeve_low_vol": {"sharpe": st["long_sleeve_sharpe"],
                                    "ann_ret_pct": st["long_sleeve_ann_ret_pct"]},
            "short_sleeve_high_vol": {"sharpe": st["short_sleeve_sharpe"],
                                      "ann_ret_pct": st["short_sleeve_ann_ret_pct"]},
            "short_leg_gross_fraction": st["short_leg_gross_fraction"],
            "short_leg_gross_fraction_gate": 0.70,
            "short_leg_gate_passes": (st["short_leg_gross_fraction"] is not None
                                      and st["short_leg_gross_fraction"] >= 0.70),
            "turnover_per_day": st["turnover_per_day"],
            "NOT_LEDGER_EVIDENCE": (
                "cached held-out window (single spent regime, sign frozen from design); "
                "selection-inflated upper bound, not forward evidence. Quoted BEFORE any short "
                "borrow -- the entire premium is the short high-vol sleeve, which no free feed "
                "prices (gate 1). Found published factor, not an invention.")}


def _lowvol_live_step(session_date: str, leg: dict) -> dict:
    """Forward settlement of L12 for a UTC session. The frozen spot panel is a research SNAPSHOT that
    ends in the past; a forward row needs it extended to `session_date`. Until then -- exactly like
    L7/L8 off the frozen perp panel, or L6/ORB with an unbuilt selection -- record the gate and
    contribute NOTHING; a phantom mark is never fabricated. Freeze precedes observation; any panel
    extension is a DETACHED background maintenance fetch, never inline."""
    if not SPOT_PANEL.exists():
        return {"status": leg["status"], "phase": "no_spot_panel", "settled": None,
                "note": "spot panel cache absent; L12 forward settlement pending a panel rebuild"}
    import numpy as np  # noqa: PLC0415
    z = np.load(SPOT_PANEL, allow_pickle=False)
    import datetime as _dt  # noqa: PLC0415
    last_day = _dt.datetime.fromtimestamp(int(z["days"][-1]) / 1000,
                                          _dt.timezone.utc).date().isoformat()
    if session_date > last_day:
        return {"status": leg["status"], "phase": "no_forward_panel", "settled": None,
                "note": (f"the frozen spot panel ends {last_day} (research snapshot, not maintained "
                         f"forward); forward settlement for {session_date} is pending a maintained "
                         "panel extension (a DETACHED background fetch, never inline). No phantom "
                         "mark is fabricated.")}
    return {"status": leg["status"], "phase": "in_panel_pre_freeze", "settled": None,
            "note": "session lies inside the frozen design/held-out panel; not a forward row"}


# ---------------------------------------------------------------------------
# L13 (SKEW_TILT) + L14 (SKEW_TILT_CRUDE): single-name options order-flow imbalance (UNSIZED)
# ---------------------------------------------------------------------------
# L13/L14 read ONE added read-only LOCAL cache: the frozen expired-OPRA daily-bar OPTIONS PANEL
# (research/data/inv0823_gex/panel.json.gz, built by scripts/invent0823_gex_{fetch,panel}.py from
# Alpaca expired-OPRA daily bars). NO options venue is hit forward, NO key, NO order -- only the
# already-downloaded local panel, exactly as L7/L8 read the frozen perp panel and L12 the frozen
# spot panel. The frozen engine that produced the gamma dossier (scripts.invent0823_gex_eval) is
# reused VERBATIM -- its build_signals / returns / book / stats / turnover_of -- driven entirely by
# each leg's frozen fields (single-name universe, formula id, 'day' horizon, cost). Nothing re-typed.

GEX_PANEL = ROOT / "research" / "data" / "inv0823_gex" / "panel.json.gz"


def _gex_engine():
    """Import the frozen INVENT-0823 gamma sweep engine (scripts/invent0823_gex_eval.py)."""
    import scripts.invent0823_gex_eval as ge  # noqa: PLC0415
    return ge


def _skewtilt_signal_matrix(ge, F, leg):
    """The leg's frozen signal matrix over the panel, restricted to the frozen SINGLE-NAME universe.

    L13 SKEW_TILT       -> S6 = (OTM call gamma-OI - OTM put gamma-OI)/total gamma-OI, exactly the
                           gamma engine's build_signals()['S6_SKEW_TILT'] (BS gamma-weighting, OTM
                           split, /gross normaliser).
    L14 SKEW_TILT_CRUDE -> the pre-registered greeks-free competitor (callVol - putVol)/(callVol +
                           putVol), computed directly from the panel's cvol/pvol -- NO greeks, NO
                           moneyness split, NO gamma weighting.
    Both are masked to the frozen single-name cross-section (the sector-ETF half is DEAD: held-out
    Sharpe 0.55, net -0.01) before the book is formed, then rank-normalised long-top/short-bottom.
    """
    import numpy as np  # noqa: PLC0415
    unds = F["_unds"]
    singles = set(leg["universe"]["single_names"])
    sn = np.array([u in singles for u in unds])
    if leg["signal"]["formula"] == "S6_SKEW_TILT":
        sigmat = ge.build_signals(F)[0]["S6_SKEW_TILT"]
    else:  # SKEW_TILT_CRUDE: greeks-free call/put volume imbalance
        cv, pv = F["cvol"], F["pvol"]
        denom = cv + pv
        sigmat = (cv - pv) / np.where(denom > 0, denom, np.nan)
    return np.where(sn[None, :], sigmat, np.nan)


def _skewtilt_heldout_record(leg: dict) -> dict:
    """PROOF: run the FROZEN gamma engine on the cached OPRA panel over the held-out window, on this
    leg's frozen single-name universe / formula / 'day' horizon, with the one-day-GAP re-entry
    placebo alongside. Reproduces the dossier's held-out single-name number.

    Every value is a selection-inflated UPPER BOUND on 260 held-out sessions of MONTHLY-EXPIRY-ONLY
    OPRA history (2.5y total; volume-not-OI proxy) -- NOT ledger evidence.
    """
    import numpy as np  # noqa: PLC0415
    if not GEX_PANEL.exists():
        raise Refused(
            f"OPRA options panel cache {GEX_PANEL} is missing; L13/L14 cannot compute. Rebuilding it "
            "(invent0823_gex_fetch/panel from Alpaca expired-OPRA daily bars) is maintenance and MUST "
            "run as a DETACHED background subprocess, never inline -- not an edit to the frozen leg.")
    ge = _gex_engine()
    F = ge.load()
    rets = ge.returns(F)
    sigmat = _skewtilt_signal_matrix(ge, F, leg)
    days = np.array(F["_days"])

    def win_stats(lo, hi, ret_key):
        win = (days >= lo) & (days <= hi)
        xs = np.where(win[:, None], sigmat, np.nan)
        w, pnl, act = ge.book(xs, rets[ret_key])
        st = ge.stats(pnl, act, ge.turnover_of(w, "day"))
        return {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                for k, v in st.items()} if st else None

    des = win_stats(*ge.DESIGN, "day")
    held = win_stats(*ge.HELDOUT, "day")
    held_gap = win_stats(*ge.HELDOUT, "gap_day")
    return {
        "leg": leg["id"], "formula": leg["signal"]["formula"], "horizon": "day",
        "universe": "single_names_only", "n_single_names": len(leg["universe"]["single_names"]),
        "cost_side_bp_primary": leg["cost_bp"]["cost_side_bp_primary"],
        "design_window": list(ge.DESIGN), "heldout_window": list(ge.HELDOUT),
        "design": des, "heldout": held,
        "heldout_gap_placebo_sharpe": (held_gap or {}).get("sharpe"),
        "heldout_net_sharpe_at_3bp": (held or {}).get("net_sr_3.0"),
        "heldout_gross_sharpe": (held or {}).get("sharpe"),
        "heldout_breakeven_bp_per_side": (held or {}).get("breakeven_bp"),
        "panel_last_day": F["_days"][-1],
        "NOT_LEDGER_EVIDENCE": (
            "cached expired-OPRA design/held-out panel (single-name S6/crude, 'day' horizon, sign "
            "frozen from the gamma design table). 2.5y of MONTHLY-EXPIRY-ONLY history, volume-not-OI "
            "proxy; the named dealer-gamma mechanism is mis-named (a raw put/call volume imbalance "
            "does as well); S6 carries an open vol-exposure risk. Selection-inflated upper bound, "
            "not forward evidence; the live leg needs the panel extended forward.")}


def _skewtilt_live_step(session_date: str, leg: dict) -> dict:
    """Forward settlement of L13/L14 for a session. The frozen OPRA panel is a research SNAPSHOT that
    ends in the past; a forward row needs it extended to `session_date` with fresh expired-OPRA daily
    bars. Until then -- exactly like L7/L8 off the frozen perp panel and L12 off the frozen spot
    panel -- record the data-availability gate and contribute NOTHING; a phantom mark is never
    fabricated. Freeze precedes observation; any panel extension is a DETACHED background maintenance
    fetch, never inline.
    """
    if not GEX_PANEL.exists():
        return {"status": leg["status"], "phase": "no_options_panel", "settled": None,
                "note": "OPRA options panel cache absent; L13/L14 forward settlement pending a panel rebuild"}
    ge = _gex_engine()
    last_day = ge.load()["_days"][-1]
    if session_date > last_day:
        return {"status": leg["status"], "phase": "no_forward_panel", "settled": None,
                "note": (f"the frozen OPRA options panel ends {last_day} (research snapshot, not "
                         f"maintained forward); forward settlement for {session_date} is pending a "
                         "maintained panel extension (a DETACHED background expired-OPRA fetch, never "
                         "inline). No phantom mark is fabricated.")}
    return {"status": leg["status"], "phase": "in_panel_pre_freeze", "settled": None,
            "note": "session lies inside the frozen design/held-out panel; not a forward row"}


# ---------------------------------------------------------------------------
# As-of / lookahead assertion
# ---------------------------------------------------------------------------

def _assert_asof(signal_et: tuple, mark_et: tuple, leg: str) -> None:
    """Refuse if a signal timestamp is not strictly earlier than the mark it earns."""
    if tuple(signal_et) >= tuple(mark_et):
        raise Refused(
            f"LOOKAHEAD in leg {leg}: signal timestamp {signal_et} is not strictly before the mark "
            f"timestamp {mark_et}. A signal that peeks at the price it earns is the exact failure "
            "this programme exists to prevent. Refusing."
        )


# ---------------------------------------------------------------------------
# State + ledger
# ---------------------------------------------------------------------------

def _blank_state(spec: dict) -> dict:
    legs = {leg["id"]: {"status": leg["status"], "settled": []}
            for leg in spec["legs"] if leg["status"] == "ACTIVE"}
    return {
        "schema_version": SCHEMA_VERSION,
        "basket_id": spec["basket_id"],
        "freeze": {"utc": spec["frozen_utc"], "preregistration_sha256": spec["preregistration_sha256"]},
        "inception_session": None,
        "last_session": None,
        "l1_pending": {},               # signal_session -> t3_signal dict (awaiting next open)
        "l3_state": {"pos": {}},        # L3 DUALCLASS: open round-trip positions per pair
        "l11_state": {"pos": {}},       # L11 DUALCLASS_EXIT10 (unsized exit-band variant): own positions
        "l4_pending": {},               # L4 T7: cum_date -> {ex_date, ...} awaiting ex-open
        "l5_state": {"tranches": [], "last_rebalance": None},   # L5 CEF: overlapping 4-week tranches
        "l9_state": {"open_tranche": None, "prev_W": None, "last_rebalance": None},  # L9 CEFMUNIEQ H=1
        "legs": legs,                   # id -> {status, settled:[{...}]}
        "curves": {"combined": 1.0, "benchmark": 1.0},
        "peaks": {"combined": 1.0, "benchmark": 1.0},
        "maxdd": {"combined": 0.0, "benchmark": 0.0},
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def load_state(spec: dict, path: pathlib.Path = None) -> dict:
    path = path or STATE_PATH
    if not path.exists():
        return _blank_state(spec)
    state = json.loads(path.read_text())
    if state.get("schema_version") != SCHEMA_VERSION:
        raise Refused(f"state {path} is schema {state.get('schema_version')}, this logger writes "
                      f"{SCHEMA_VERSION}")
    if state.get("freeze", {}).get("preregistration_sha256") != spec["preregistration_sha256"]:
        raise Refused("the state file was written under a different freeze hash than the current "
                      "frozen spec. A forward test whose freeze changed mid-flight is two half-tests. "
                      "Start a new ledger under a new freeze.")
    return state


def save_state(state: dict, path: pathlib.Path = None) -> None:
    path = path or STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(path)


def append_ledger(record: dict, path: pathlib.Path = None) -> None:
    path = path or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def read_ledger(path: pathlib.Path = None) -> list:
    path = path or LEDGER_PATH
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------

def kill_check(returns: list, spec: dict) -> dict:
    """Evaluate the frozen per-leg kill switch on a stream of settled net returns."""
    ks = spec["kill_switch"]
    n = len(returns)
    out = {"n": n, "N_min": ks["N_min"], "rule": ks["rule"], "verdict": "ALIVE"}
    if n < 2:
        out["mean"] = returns[0] if returns else None
        out["reason_not_evaluable"] = "need >=2 settled observations for a standard error"
        return out
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    se = math.sqrt(var / n)
    upper95 = mean + 1.645 * se
    out.update({"mean": mean, "se": se, "one_sided_upper_95_bound": upper95,
                "t_stat": (mean / se) if se > 0 else None})
    if n >= ks["N_min"] and upper95 < 0:
        out["verdict"] = "DEAD -- significantly negative forward"
    elif n < ks["N_min"]:
        out["verdict"] = f"ALIVE -- kill not evaluable below N_min={ks['N_min']} (n={n})"
    return out


# ---------------------------------------------------------------------------
# Lag-aware session selection -- the free-data horizon
# ---------------------------------------------------------------------------
# The free Alpaca tier will NOT serve the current day's (and, for a session or two, recent)
# SIP/auction data: a query returns HTTP 403 "subscription does not permit querying recent SIP
# data". So "log today" is wrong -- the logger must target the most-recent session whose FULL
# settlement data is already free-tier-accessible. We find that horizon EMPIRICALLY: walk back one
# session at a time and probe the auction endpoint, treating the 403 as "still embargoed".
#
# Settlement cadence is respected by construction, because run_session logs ONE session_date and all
# legs settle relative to it:
#   * same-session legs (L2 ETFRV 15:45->close, L6 ORB open->MOC) need session_date's intraday+close
#     prints -- exactly what the auction/SIP probe on session_date verifies;
#   * overnight legs (L1 T3, L4 T7) record their observation on the row for the EXIT session (open of
#     S+1), which needs S+1's open auction (again gated by the probe on the logged session) and the
#     S signal already queued in state from the prior in-order run -- so probing the logged session's
#     data is the correct and sufficient gate;
#   * weekly/multi-day legs (L5, L9 CEF; L3 dual-class) advance their own state machines per session
#     and only settle when a tranche/round-trip completes; they need the logged session's data free
#     plus their own prior cached snapshots, both already handled.

def _is_embargo_refusal(exc) -> bool:
    """True if a Refused looks like the free-tier recent-SIP 403 embargo, not a hard failure."""
    m = str(exc).lower()
    return ("403" in m) or ("recent sip data" in m) or ("subscription does not permit" in m)


def _session_data_is_free(day: str, *, allow_network: bool = True) -> bool:
    """Probe whether the free tier will serve `day`'s recent-SIP settlement data.

    Uses SPY's official close auction as a cheap, universally-present witness for the whole session's
    SIP availability (auctions and minute bars share the same recent-data embargo). Catches the
    free-tier 403 as 'still embargoed' and returns False; re-raises any other Refused.
    """
    if not allow_network:
        return True  # offline: the local cache is the only arbiter; per-leg code refuses if absent
    try:
        au = _auctions(day, ["SPY"])
    except Refused as exc:
        if _is_embargo_refusal(exc):
            return False
        raise
    return (au.get("SPY") or {}).get("c") is not None


def _free_data_horizon_session(sessions: list, *, allow_network: bool = True,
                               max_probe: int = 15) -> str:
    """The latest session in `sessions` whose recent-SIP data clears the free-tier embargo, or None.

    Walks back from the newest session (at most `max_probe`), returning the first one the free tier
    actually serves. `max_probe` bounds the walk so a long backlog or an outage cannot turn one run
    into a crawl; the embargo is only a session or two, so 15 is ample.
    """
    for day in reversed(sessions[-max_probe:]):
        if _session_data_is_free(day, allow_network=allow_network):
            return day
    return None


def _no_forward_session_record(spec: dict, spine: list, candidates: list, now_utc: dt.datetime,
                               fdate: str, *, allow_network: bool = True) -> dict:
    """A clean, NON-writing record explaining why no forward row is loggable this run.

    Two honest reasons: (a) no post-freeze session is yet complete-and-unlogged, or (b) every such
    session is still inside the free-tier recent-SIP embargo. Neither is a crash and neither
    fabricates a mark; the row will be written as soon as a post-freeze session's data goes free.
    """
    latest_free = _free_data_horizon_session(spine, allow_network=allow_network) if spine else None
    today = now_utc.date().isoformat()
    if not candidates:
        reason = (
            f"no complete post-freeze session to log yet: the freeze date is {fdate} and the "
            f"most-recent COMPLETE trading session is {spine[-1] if spine else None} (the spine "
            f"excludes today, {today}). The freeze-day session becomes loggable once it is a "
            f"complete past session AND its recent-SIP data clears the free-tier embargo (~1-2 "
            f"days). Logging nothing today is correct, not a failure.")
    else:
        reason = (
            f"every post-freeze un-logged session in {candidates[0]}..{candidates[-1]} is still "
            f"inside the free-tier recent-SIP embargo (latest free session on the whole spine: "
            f"{latest_free}). The free Alpaca tier will not serve these sessions' auction/SIP data "
            f"yet; a real forward row is written automatically as soon as the embargo clears "
            f"(~1-2 days). No phantom mark is fabricated.")
    return {
        "kind": "no_session", "basket_id": spec["basket_id"], "schema_version": SCHEMA_VERSION,
        "run_utc": now_utc.isoformat(), "mode": "forward", "wrote_ledger_row": False,
        "freeze_date": fdate, "today": today,
        "latest_complete_session": spine[-1] if spine else None,
        "latest_free_session": latest_free,
        "post_freeze_unlogged_candidates": candidates,
        "reason": reason, "framing": FRAMING,
    }


# ---------------------------------------------------------------------------
# One forward session
# ---------------------------------------------------------------------------

def run_session(*, session_date: str = None, now_utc: dt.datetime = None,
                allow_network: bool = True, write: bool = True, refresh_cash: bool = False,
                cache_dir=None, force: bool = False) -> dict:
    """Compute, settle, size and log exactly one forward session.

    `write=False` is the `proof` mode: everything runs against real data but nothing is written to
    the ledger or the state, and the pre-freeze guard is relaxed so the pipeline can be demonstrated
    on the most-recent COMPLETE session. A proof record is explicitly labelled not-evidence.
    """
    spec = frozen_spec()
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    fdate = freeze_date(spec)

    # session spine from SPY daily closes (one source of truth for trading sessions). Always probed
    # from TODAY so the spine reaches the most-recent complete session -- including the session a
    # back-dated proof needs as its L1 exit. load_daily_closes ends its window before its argument.
    today = now_utc.date().isoformat()
    ser = load_daily_closes(session_date=today, allow_network=allow_network, cache_dir=cache_dir)
    spine = ser["dates"]                    # trading sessions strictly before today
    if session_date is None:
        if not write:
            # PROOF: the most-recent session the free tier actually serves (falls back to spine[-1]
            # so an offline/edge case still demonstrates the pipeline); pre-freeze is allowed here.
            session_date = _free_data_horizon_session(spine, allow_network=allow_network) or spine[-1]
        else:
            # LAG-AWARE FORWARD SELECTION: log the latest post-freeze, not-yet-logged session whose
            # FULL settlement data clears the free-tier recent-SIP embargo. If none is available yet,
            # refuse GRACEFULLY (no crash, no phantom row) -- the row is written once the data frees.
            logged = {r.get("session_date") for r in read_ledger()
                      if r.get("kind") == "session"}
            candidates = [d for d in spine if d >= fdate and d not in logged]
            session_date = _free_data_horizon_session(candidates, allow_network=allow_network)
            if session_date is None:
                return _no_forward_session_record(spec, spine, candidates, now_utc, fdate,
                                                  allow_network=allow_network)
    # For the ledger, the session must be freeze-forward. For proof (write=False) we allow the
    # most-recent complete session even if it predates the freeze -- it is a wiring check, not evidence.
    if write and session_date < fdate:
        raise Refused(f"session {session_date} is before the freeze {fdate}. A pre-freeze row is "
                      "in-sample. Use `proof` (which never writes the ledger) to demonstrate the "
                      "pipeline on an earlier session.")

    state = load_state(spec)
    if write and not force:
        for rec in read_ledger():
            if rec.get("session_date") == session_date and rec.get("kind") == "session":
                raise Refused(f"session {session_date} is already logged; refusing to double-log. "
                              "Use --force only if you know why.")

    if refresh_cash and allow_network:
        try:
            refresh_cash_rates()
        except Exception:  # noqa: BLE001 -- best effort; staleness is carried, not fatal
            pass

    # sessions strictly before this one (for the L2 trailing window), and an ordered session list
    # that INCLUDES this session (for resolving an L1 pending night's exit). `spine` ends before
    # today, so today is appended: when we run ON the exit session, that session is today itself.
    spine_before = [d for d in spine if d < session_date]
    sessions_incl = spine_before + [session_date]

    ov = vol_overlay(session_date, spec, allow_network=allow_network, cache_dir=cache_dir)
    cash = cash_leg(ov["reference_close_date"])
    r_cash_day = (cash["annual_pct"] / 100.0) * 1.0 / 365.0  # one session's T-bill accrual (approx 1 cal day)

    legs_out = {}
    contributions = {}   # leg_id -> settled net return attributed to THIS session, or None
    etf_marked = None        # L2's fired-pair book, reused by the unsized L10 variant (no re-fetch)
    dc_series_shared = None  # L3's daily-bar series, reused by the unsized L11 variant (no re-fetch)

    # ---- L1 (T3): settle any pending night that exits at THIS session's open, then decide today
    t3_leg = leg_by_id(spec, "T3")
    if t3_leg["status"] == "ACTIVE":
        t3_state = state["legs"].setdefault("T3", {"status": "ACTIVE", "settled": []})
        t3_rec = {"status": t3_state["status"]}
        # settle pending nights whose exit session is <= this session (open has printed)
        settled_here = None
        if not str(t3_state["status"]).startswith("DEAD"):
            for sig_session in sorted(state.get("l1_pending", {})):
                if sig_session >= session_date:
                    continue
                # the exit session is the first trading session AFTER the signal session, resolved
                # against the session list that includes today (the spine ends before today)
                later = [d for d in sessions_incl if d > sig_session]
                if not later:
                    continue
                exit_session = later[0]
                if exit_session != session_date:
                    continue  # this pending night exits on a different session
                sig = state["l1_pending"][sig_session]
                marked = t3_mark(sig, exit_session, t3_leg, allow_network=allow_network)
                settled_here = marked["settled"]
                t3_rec["settled_from_pending"] = marked
                break
        # decide today's fade book (queued pending; exits next open)
        if not str(t3_state["status"]).startswith("DEAD"):
            try:
                universe = _t3_universe(session_date)
                sig_today = t3_signal(session_date, universe, allow_network=allow_network)
                t3_rec["signal_today"] = {k: sig_today[k] for k in ("signal_session", "k", "n_names")}
                if write:
                    state.setdefault("l1_pending", {})[session_date] = sig_today
                    t3_rec["phase_today"] = "signal_logged (exits next open, mark pending)"
                else:
                    # PROOF MODE ONLY: demonstrate the full L1 round trip in one shot by marking the
                    # fresh signal against the next trading session's open, which already printed for
                    # a most-recent-complete signal session. This never touches the ledger.
                    t3_rec["phase_today"] = "signal_logged (proof: attempting immediate next-open mark)"
                    # the exit is the first trading session AFTER the signal session. Prefer one that
                    # already prints in the spine (a COMPLETE session, not today's embargoed one).
                    later_sessions = [d for d in spine if d > session_date]
                    exit_guess = later_sessions[0] if later_sessions else now_utc.date().isoformat()
                    if exit_guess > session_date:
                        try:
                            marked = t3_mark(sig_today, exit_guess, t3_leg,
                                             allow_network=allow_network)
                            t3_rec["settled_proof_next_open"] = marked
                            if settled_here is None:
                                settled_here = marked["settled"]
                        except Refused as exc:
                            t3_rec["proof_mark_error"] = str(exc)
            except Refused as exc:
                t3_rec["signal_today_error"] = str(exc)
        legs_out["T3"] = t3_rec
        contributions["T3"] = settled_here["net_return"] if settled_here else None
        if settled_here and write:
            t3_state["settled"].append({"exit_session": session_date,
                                        "net": settled_here["net_return"]})

    # ---- L2 (ETF-RV): intraday, settles same session
    # v9: DE-SIZED to ACTIVE_UNSIZED (E1: 15:45-signal/15:45-fill shared-price artefact). It still
    # SETTLES and LOGS, accrues its kill-switch stream, and still feeds the L10 band variant -- but it
    # carries ZERO budget and is DELIBERATELY kept out of `contributions`, so it never touches the
    # combined book. Its signal/execution spec is unchanged; only status/sizing moved.
    etf_leg = leg_by_id(spec, "ETFRV")
    if etf_leg["status"] in ("ACTIVE", "ACTIVE_UNSIZED"):
        etf_unsized = etf_leg["status"] == "ACTIVE_UNSIZED"
        etf_state = state["legs"].setdefault("ETFRV", {"status": etf_leg["status"], "settled": []})
        if str(etf_state["status"]).startswith("DEAD"):
            legs_out["ETFRV"] = {"status": etf_state["status"], "phase": "killed"}
            if not etf_unsized:
                contributions["ETFRV"] = None
        else:
            marked = etfrv_settle(session_date, etf_leg, spine_before, allow_network=allow_network)
            etf_marked = marked      # reused by the unsized L10 ETFRV_Z20 variant (no re-fetch)
            legs_out["ETFRV"] = {**marked, "logged_unsized": etf_unsized}
            if not etf_unsized:
                contributions["ETFRV"] = (marked["settled"]["net_return"]
                                          if marked.get("settled") else None)
            if marked.get("settled") and write and session_date >= leg_freeze_date(spec, etf_leg):
                etf_state["settled"].append({"exit_session": session_date,
                                             "net": marked["settled"]["net_return"]})

    # ---- L3 (DUALCLASS): multi-day RV; a round-trip contributes when it closes -------------
    dc_leg = leg_by_id(spec, "DUALCLASS")
    if dc_leg["status"] == "ACTIVE":
        dc_state = state["legs"].setdefault("DUALCLASS", {"status": "ACTIVE", "settled": []})
        if str(dc_state["status"]).startswith("DEAD"):
            legs_out["DUALCLASS"] = {"status": dc_state["status"], "phase": "killed"}
            contributions["DUALCLASS"] = None
        elif not write:
            pr = dualclass_proof(dc_leg)
            legs_out["DUALCLASS"] = {"status": "ACTIVE", "phase": "proof", "proof": pr}
            m = pr.get("mean_net_bp_per_round_trip")
            contributions["DUALCLASS"] = (m / 1e4) if m is not None else None
        else:
            l3s = state.setdefault("l3_state", {"pos": {}})
            # compute the daily-bar series ONCE and share it with the unsized L11 variant (identical
            # universe): passing it in means no second fetch. On failure fall back to None so
            # dualclass_live_step recomputes (and its own try/except handles the refusal) as before.
            _dc_syms = sorted({s for p in dc_leg["pairs"] for s in p})
            try:
                dc_series_shared = _dc_series(session_date, _dc_syms,
                                              allow_network=allow_network, cached_only=False)
            except Refused:
                dc_series_shared = None
            try:
                rec = dualclass_live_step(session_date, dc_leg, l3s, allow_network=allow_network,
                                          series=dc_series_shared)
                nets = rec.get("settled_here") or []
            except Refused as exc:
                rec, nets = {"status": "ACTIVE", "error": str(exc), "marks": []}, []
            legs_out["DUALCLASS"] = {k: rec.get(k) for k in
                                     ("status", "marks", "opened", "open_positions", "error") if k in rec}
            contributions["DUALCLASS"] = (sum(nets) / len(nets)) if nets else None
            if nets and session_date >= leg_freeze_date(spec, dc_leg):
                for mk in rec.get("marks", []):
                    dc_state["settled"].append({"exit_session": session_date, "net": mk["net_bp"] / 1e4})

    # ---- L4 (T7): overnight ex-open; settle pending cum-days, queue new ones ----------------
    # v9: DE-SIZED to ACTIVE_UNSIZED. Its held-out prior was an artefact of duplicated dividend
    # records (doubled rate on ~8% of ex-dates); on the deduplicated cache the edge collapses to
    # t 0.81 and is negative at any real half-spread. It still SETTLES and LOGS, accrues its
    # kill-switch stream, and reads the now-deduplicated dividends -- but it carries ZERO budget and
    # is DELIBERATELY kept out of `contributions`, so it never touches the combined book.
    t7_leg = leg_by_id(spec, "T7")
    if t7_leg["status"] in ("ACTIVE", "ACTIVE_UNSIZED"):
        t7_unsized = t7_leg["status"] == "ACTIVE_UNSIZED"
        t7_state = state["legs"].setdefault("T7", {"status": t7_leg["status"], "settled": []})
        if str(t7_state["status"]).startswith("DEAD"):
            legs_out["T7"] = {"status": t7_state["status"], "phase": "killed"}
            if not t7_unsized:
                contributions["T7"] = None
        elif not write:
            try:
                pr = t7_proof(spine, allow_network=allow_network)
                legs_out["T7"] = {"status": t7_leg["status"], "phase": "proof",
                                  "logged_unsized": t7_unsized, "proof": pr}
                if not t7_unsized:
                    s = pr.get("settled")
                    contributions["T7"] = s["net_return"] if s else None
            except Refused as exc:
                legs_out["T7"] = {"status": t7_leg["status"], "phase": "proof_error",
                                  "logged_unsized": t7_unsized, "error": str(exc)}
                if not t7_unsized:
                    contributions["T7"] = None
        else:
            l4p = state.setdefault("l4_pending", {})
            settled_t7 = None
            rec = {"status": t7_leg["status"]}
            # settle any pending cum-day whose ex-date is this session
            for cum in sorted(list(l4p)):
                if l4p[cum]["ex_date"] != session_date:
                    continue
                try:
                    marked = t7_mark_exdate(session_date, cum, t7_leg, allow_network=allow_network)
                    if marked.get("settled"):
                        settled_t7 = marked["settled"]
                        rec["settled_from_pending"] = marked
                        l4p.pop(cum, None)
                except Refused as exc:
                    rec["mark_error"] = str(exc)
                break
            # queue names going ex on the NEXT trading session (today is their cum-day)
            later = [d for d in spine if d > session_date]
            next_sess = later[0] if later else None
            if next_sess:
                divs = _t7_dividends().get(next_sess, [])
                if divs:
                    l4p[session_date] = {"ex_date": next_sess, "n_div": len(divs)}
                    rec["queued_cum_day"] = {"cum": session_date, "ex_date": next_sess,
                                             "n_div_names": len(divs)}
            rec["logged_unsized"] = t7_unsized
            legs_out["T7"] = rec
            if not t7_unsized:
                contributions["T7"] = settled_t7["net_return"] if settled_t7 else None
            if settled_t7 and session_date >= leg_freeze_date(spec, t7_leg):
                t7_state["settled"].append({"exit_session": session_date, "net": settled_t7["net_return"]})

    # ---- L5 (T12CEF): weekly rebalance, 4-week overlapping tranches -------------------------
    cef_leg = leg_by_id(spec, "T12CEF")
    if cef_leg["status"] == "ACTIVE":
        cef_state = state["legs"].setdefault("T12CEF", {"status": "ACTIVE", "settled": []})
        if str(cef_state["status"]).startswith("DEAD"):
            legs_out["T12CEF"] = {"status": cef_state["status"], "phase": "killed"}
            contributions["T12CEF"] = None
        elif not write:
            pr = l5_proof(cef_leg)
            legs_out["T12CEF"] = {"status": "ACTIVE", "phase": "proof", "proof": pr}
            m = pr.get("mean_net_bp_per_week")
            contributions["T12CEF"] = (m / 1e4) if m is not None else None
        else:
            l5s = state.setdefault("l5_state", {"tranches": [], "last_rebalance": None})
            try:
                rec = l5_live_step(session_date, cef_leg, l5s, spine_before, allow_network=allow_network)
            except Refused as exc:
                rec = {"status": "ACTIVE", "phase": "error", "error": str(exc), "settled_here": None}
            legs_out["T12CEF"] = {k: rec.get(k) for k in
                                  ("status", "phase", "open_tranches", "book_universe", "error") if k in rec}
            sh = rec.get("settled_here")
            # weekly-equivalent return feeds the combined book; the 4-week net is the kill-stream obs
            contributions["T12CEF"] = sh["net_return_per_week_equiv"] if sh else None
            if sh:
                legs_out["T12CEF"]["settled"] = sh
                if session_date >= leg_freeze_date(spec, cef_leg):
                    cef_state["settled"].append({"exit_session": session_date, "net": sh["net_return_4wk"]})

    # ---- L6 (ORB): intraday, settles same session ------------------------------------------
    orb_leg = leg_by_id(spec, "ORB")
    if orb_leg["status"] == "ACTIVE":
        orb_state = state["legs"].setdefault("ORB", {"status": "ACTIVE", "settled": []})
        if str(orb_state["status"]).startswith("DEAD"):
            legs_out["ORB"] = {"status": orb_state["status"], "phase": "killed"}
            contributions["ORB"] = None
        elif not write:
            pr = l6_proof(orb_leg)
            legs_out["ORB"] = {"status": "ACTIVE", "phase": "proof", "proof": pr}
            m = pr.get("mean_net_bp_per_day")
            contributions["ORB"] = (m / 1e4) if m is not None else None
        else:
            try:
                rec = l6_settle(session_date, orb_leg, allow_network=allow_network)
            except Refused as exc:
                rec = {"status": "ACTIVE", "phase": "error", "error": str(exc), "settled": None}
            legs_out["ORB"] = {k: rec.get(k) for k in ("status", "phase", "settled", "note") if k in rec}
            s = rec.get("settled")
            contributions["ORB"] = s["net_return"] if s else None
            if s and session_date >= leg_freeze_date(spec, orb_leg):
                orb_state["settled"].append({"exit_session": session_date, "net": s["net_return"]})

    # ---- L7 (XS_GLSR_Z) + L8 (XS_SMART): crypto-perp cross-sectional positioning fades ------
    # BOTH are UNSIZED logging-only as of the v4 freeze: L7 was DEMOTED from sized (0.12) because
    # perp taker slippage is unmeasured and its deployable top-50 margin is thin (single regime,
    # +0.73 net Sharpe / -1.19 at the 15 bp/side cascade stress). Both are LOGGED (proof + forward)
    # but DELIBERATELY excluded from `contributions`, so neither ever touches the combined book.
    for perp_id in ("XS_GLSR_Z", "XS_SMART"):
        perp_leg = leg_by_id(spec, perp_id)
        if perp_leg["status"] != "ACTIVE_UNSIZED":
            continue
        perp_state = state["legs"].setdefault(perp_id, {"status": "ACTIVE_UNSIZED", "settled": []})
        if str(perp_state["status"]).startswith("DEAD"):
            legs_out[perp_id] = {"status": perp_state["status"], "phase": "killed"}
        elif not write:
            pr = _perp_heldout_record(perp_leg)
            legs_out[perp_id] = {"status": "ACTIVE_UNSIZED", "phase": "proof",
                                 "logged_unsized": True, "risk_budget": 0.0, "proof": pr}
        else:
            rec = _perp_live_step(session_date, perp_leg)
            legs_out[perp_id] = {"status": "ACTIVE_UNSIZED", "logged_unsized": True,
                                 **{k: rec.get(k) for k in ("phase", "settled", "note") if k in rec}}
            s = rec.get("settled")
            if s and session_date >= leg_freeze_date(spec, perp_leg):
                perp_state["settled"].append({"exit_session": session_date, "net": s["net_return"]})
        # never added to `contributions`: zero risk budget, never touches the combined book.

    # ---- L9 (CEFMUNIEQ): muni+equity CEF discount-LEVEL H=1 tilt, weekly ---------------------
    # UNSIZED logging-only as of the v5 freeze: DE-SIZED from the v4 satellite (0.08) to 0.0 because
    # Y05/CEFMUNIEQ FAILS the conservative multiple-testing bar (stressed alpha 0.94x of
    # sqrt(2 ln 132)=3.125) and is structurally adjacent to L5 T12CEF (shared CEFConnect NAV feed /
    # failure space). Like the two perp loggers it is still LOGGED forward and kill-switched, but it
    # is DELIBERATELY kept out of `contributions`, so it carries NO allocation and never touches the
    # combined book. Its SIGNAL/execution spec is unchanged from v4; only its sizing/status moved.
    cme_leg = leg_by_id(spec, "CEFMUNIEQ")
    if cme_leg["status"] in ("ACTIVE", "ACTIVE_UNSIZED"):
        cme_unsized = cme_leg["status"] == "ACTIVE_UNSIZED"
        cme_state = state["legs"].setdefault("CEFMUNIEQ", {"status": cme_leg["status"], "settled": []})
        if str(cme_state["status"]).startswith("DEAD"):
            legs_out["CEFMUNIEQ"] = {"status": cme_state["status"], "phase": "killed"}
            if not cme_unsized:
                contributions["CEFMUNIEQ"] = None
        elif not write:
            pr = cefmunieq_proof(cme_leg)
            legs_out["CEFMUNIEQ"] = {"status": cme_leg["status"], "phase": "proof",
                                     "logged_unsized": cme_unsized, "proof": pr}
            if not cme_unsized:
                m = pr.get("mean_net_bp_per_week")
                contributions["CEFMUNIEQ"] = (m / 1e4) if m is not None else None
        else:
            l9s = state.setdefault("l9_state", {"open_tranche": None, "prev_W": None,
                                                "last_rebalance": None})
            try:
                rec = cefmunieq_live_step(session_date, cme_leg, l9s, spine_before,
                                          allow_network=allow_network)
            except Refused as exc:
                rec = {"status": cme_leg["status"], "phase": "error", "error": str(exc),
                       "settled_here": None}
            legs_out["CEFMUNIEQ"] = {k: rec.get(k) for k in
                                     ("status", "phase", "open_tranche", "book_universe", "error") if k in rec}
            legs_out["CEFMUNIEQ"]["logged_unsized"] = cme_unsized
            sh = rec.get("settled_here")
            if not cme_unsized:
                contributions["CEFMUNIEQ"] = sh["net_return_1wk"] if sh else None
            if sh:
                legs_out["CEFMUNIEQ"]["settled"] = sh
                if session_date >= leg_freeze_date(spec, cme_leg):
                    cme_state["settled"].append({"exit_session": session_date,
                                                 "net": sh["net_return_1wk"]})

    # ---- L10 (ETFRV_Z20) + L11 (DUALCLASS_EXIT10): UNSIZED band variants (v7 freeze) --------
    # ADDITIVE logging-only. L10 = L2's ETF-sibling RV at entry |z|>=2.0; L11 = L3's dual-class RV
    # at exit |z|~1.0 -- the OU-recommended bands. Because those bands were CHOSEN on the held-out
    # window, re-freezing the SIZED L2/L3 to them would be in-sample selection; instead the variants
    # are logged UNSIZED (zero risk budget) and kill-switched so genuinely-FORWARD data adjudicates.
    # Both are DELIBERATELY excluded from `contributions` and never touch the combined book. L10
    # reuses L2's fired-pair book (its fired set is the subset clearing |z|>=2.0) and L11 reuses L3's
    # daily-bar series -- no new data source, no re-fetch.
    v10_leg = leg_by_id(spec, "ETFRV_Z20")
    if v10_leg["status"] == "ACTIVE_UNSIZED":
        v10_state = state["legs"].setdefault("ETFRV_Z20", {"status": "ACTIVE_UNSIZED", "settled": []})
        if str(v10_state["status"]).startswith("DEAD"):
            legs_out["ETFRV_Z20"] = {"status": v10_state["status"], "phase": "killed"}
        elif etf_marked is None:
            legs_out["ETFRV_Z20"] = {"status": "ACTIVE_UNSIZED", "logged_unsized": True,
                                     "phase": "no_base", "settled": None,
                                     "note": ("parent L2 ETFRV did not settle (killed/unavailable); "
                                              "the |z|>=2.0 variant needs L2's fired-pair book")}
        else:
            rec = etfrv_variant_from_base(etf_marked, v10_leg, session_date)
            legs_out["ETFRV_Z20"] = rec
            s = rec.get("settled")
            if s and write and session_date >= leg_freeze_date(spec, v10_leg):
                v10_state["settled"].append({"exit_session": session_date, "net": s["net_return"]})

    v11_leg = leg_by_id(spec, "DUALCLASS_EXIT10")
    if v11_leg["status"] == "ACTIVE_UNSIZED":
        v11_state = state["legs"].setdefault("DUALCLASS_EXIT10",
                                             {"status": "ACTIVE_UNSIZED", "settled": []})
        if str(v11_state["status"]).startswith("DEAD"):
            legs_out["DUALCLASS_EXIT10"] = {"status": v11_state["status"], "phase": "killed"}
        elif not write:
            pr = dualclass_proof(v11_leg)
            legs_out["DUALCLASS_EXIT10"] = {"status": "ACTIVE_UNSIZED", "phase": "proof",
                                            "logged_unsized": True, "proof": pr}
        else:
            l11s = state.setdefault("l11_state", {"pos": {}})
            if dc_series_shared is None:
                _v11_syms = sorted({s for p in v11_leg["pairs"] for s in p})
                try:
                    dc_series_shared = _dc_series(session_date, _v11_syms,
                                                  allow_network=allow_network, cached_only=False)
                except Refused:
                    dc_series_shared = None
            try:
                rec = dualclass_live_step(session_date, v11_leg, l11s, allow_network=allow_network,
                                          series=dc_series_shared)
            except Refused as exc:
                rec = {"status": "ACTIVE_UNSIZED", "error": str(exc), "marks": []}
            legs_out["DUALCLASS_EXIT10"] = {k: rec.get(k) for k in
                                            ("status", "marks", "opened", "open_positions", "error")
                                            if k in rec}
            legs_out["DUALCLASS_EXIT10"]["logged_unsized"] = True
            if session_date >= leg_freeze_date(spec, v11_leg):
                for mk in rec.get("marks", []):
                    v11_state["settled"].append({"exit_session": session_date,
                                                 "net": mk["net_bp"] / 1e4})

    # ---- L12 (CRYPTO_LOWVOL): Binance spot cross-sectional realised-vol (v8 freeze) ----------
    # ADDITIVE logging-only. UNSIZED (0.0 budget): the premium is entirely the SHORT high-vol
    # alt-bleed leg whose borrow no free feed prices (gate 1), capacity is low single-digit $M
    # (gate 2), and its P&L overlap with L7 XS_GLSR_Z is unmeasured (gate 3). LOGGED (proof +
    # forward) but DELIBERATELY excluded from `contributions`, so it never touches the combined
    # book. The LONG (low-vol) and SHORT (high-vol) sleeves are separated in the proof so the
    # gate-4 short-leg-fraction kill-switch is computable. Reads ONLY the frozen local spot panel.
    lv_leg = leg_by_id(spec, "CRYPTO_LOWVOL")
    if lv_leg["status"] == "ACTIVE_UNSIZED":
        lv_state = state["legs"].setdefault("CRYPTO_LOWVOL",
                                            {"status": "ACTIVE_UNSIZED", "settled": []})
        if str(lv_state["status"]).startswith("DEAD"):
            legs_out["CRYPTO_LOWVOL"] = {"status": lv_state["status"], "phase": "killed"}
        elif not write:
            try:
                pr = _lowvol_heldout_record(lv_leg)
                legs_out["CRYPTO_LOWVOL"] = {"status": "ACTIVE_UNSIZED", "phase": "proof",
                                             "logged_unsized": True, "risk_budget": 0.0, "proof": pr}
            except Refused as exc:
                legs_out["CRYPTO_LOWVOL"] = {"status": "ACTIVE_UNSIZED", "phase": "proof_error",
                                             "logged_unsized": True, "error": str(exc)}
        else:
            rec = _lowvol_live_step(session_date, lv_leg)
            legs_out["CRYPTO_LOWVOL"] = {"status": "ACTIVE_UNSIZED", "logged_unsized": True,
                                         **{k: rec.get(k) for k in ("phase", "settled", "note")
                                            if k in rec}}
            s = rec.get("settled")
            if s and session_date >= leg_freeze_date(spec, lv_leg):
                lv_state["settled"].append({"exit_session": session_date, "net": s["net_return"]})
        # never added to `contributions`: zero risk budget, never touches the combined book.

    # ---- L13 (SKEW_TILT) + L14 (SKEW_TILT_CRUDE): single-name options order-flow imbalance -----
    # ADDITIVE logging-only (v10 freeze). BOTH UNSIZED (0.0 budget): the strong invention survivor
    # S6_SKEW_TILT (single-name held-out net Sharpe +3.06 at the 3 bp rail, gap-placebo +3.53) and
    # its pre-registered greeks-free competitor (the Black-Scholes apparatus turned out to be
    # decoration -- a raw call/put VOLUME imbalance does as well or better OOS). Caveats: only 2.5y of
    # MONTHLY-EXPIRY-ONLY OPRA history, the named dealer-gamma mechanism is mis-named, and S6 carries
    # an OPEN vol-exposure risk. Per the crude guard, if the CRUDE book matches/beats S6 forward, the
    # CRUDE is the promotion candidate (simpler = less overfit). LOGGED (proof + forward) but
    # DELIBERATELY excluded from `contributions`, so neither ever touches the combined book. Reads
    # ONLY the frozen local OPRA panel; forward settlement records a data-availability gate until the
    # panel is extended (a DETACHED background fetch, never inline).
    for skew_id in ("SKEW_TILT", "SKEW_TILT_CRUDE"):
        skew_leg = leg_by_id(spec, skew_id)
        if skew_leg["status"] != "ACTIVE_UNSIZED":
            continue
        skew_state = state["legs"].setdefault(skew_id, {"status": "ACTIVE_UNSIZED", "settled": []})
        if str(skew_state["status"]).startswith("DEAD"):
            legs_out[skew_id] = {"status": skew_state["status"], "phase": "killed"}
        elif not write:
            try:
                pr = _skewtilt_heldout_record(skew_leg)
                legs_out[skew_id] = {"status": "ACTIVE_UNSIZED", "phase": "proof",
                                     "logged_unsized": True, "risk_budget": 0.0, "proof": pr}
            except Refused as exc:
                legs_out[skew_id] = {"status": "ACTIVE_UNSIZED", "phase": "proof_error",
                                     "logged_unsized": True, "error": str(exc)}
        else:
            rec = _skewtilt_live_step(session_date, skew_leg)
            legs_out[skew_id] = {"status": "ACTIVE_UNSIZED", "logged_unsized": True,
                                 **{k: rec.get(k) for k in ("phase", "settled", "note") if k in rec}}
            s = rec.get("settled")
            if s and session_date >= leg_freeze_date(spec, skew_leg):
                skew_state["settled"].append({"exit_session": s["exit_session"],
                                              "net": s["net_return"]})
        # never added to `contributions`: zero risk budget, never touches the combined book.

    # ---- combined book (equal-risk across sources; v9: NO vol overlay -- unlevered) ---------
    budgets = (spec.get("risk_budgets_active_v11") or spec.get("risk_budgets_active_v10")
               or spec.get("risk_budgets_active_v9") or spec.get("risk_budgets_active_v8")
               or spec.get("risk_budgets_active_v7") or spec.get("risk_budgets_active_v6") or {})
    budgets = {leg["id"]: (budgets.get(leg["id"]) if leg["id"] in budgets
                           else leg.get("risk_budget_fraction_active", 0.0))
               for leg in spec["legs"] if leg["status"] == "ACTIVE"}
    # v9 (N1): the T13 SPY vol overlay is REMOVED from the combined book -- on the dollar-neutral book
    # it costs Sharpe in every window (validated on a LONG-SPY book; wmax=1.0 makes it a one-sided
    # drag). The book is now UNLEVERED (effective weight 1.0). The overlay weight is still computed and
    # recorded as a NON-APPLIED reference so the forward row carries the book WITH and WITHOUT it.
    overlay_removed = bool((spec.get("vol_overlay") or {}).get("removed_from_combined_book_v9"))
    w_apply = 1.0 if overlay_removed else ov["w_vol"]
    deployed = 0.0
    r_book = 0.0
    for lid, r in contributions.items():
        if r is None:
            continue
        b = budgets.get(lid, 0.0)
        deployed += w_apply * b
        r_book += w_apply * b * r
    idle = max(0.0, 1.0 - deployed)
    r_combined = r_book + idle * r_cash_day
    any_settled = any(r is not None for r in contributions.values())
    combined = None
    if any_settled:
        combined = {"deployed_gross": deployed, "idle_fraction": idle,
                    "r_combined_net": r_combined, "r_benchmark": r_cash_day,
                    "leg_contributions": contributions, "w_vol": w_apply,
                    "w_vol_applied": w_apply, "w_vol_overlay_reference": ov["w_vol"],
                    "vol_overlay_removed": overlay_removed}
        if write:
            for name, r in (("combined", r_combined), ("benchmark", r_cash_day)):
                state["curves"][name] *= (1.0 + r)
                state["peaks"][name] = max(state["peaks"][name], state["curves"][name])
                dd = (state["peaks"][name] - state["curves"][name]) / state["peaks"][name]
                state["maxdd"][name] = max(state["maxdd"][name], dd)
            combined["equity_after"] = dict(state["curves"])
            combined["maxdd_after"] = dict(state["maxdd"])

    # ---- kill-switch status per leg (evaluated on the settled streams) ---------------------
    kill = {}
    for lid in ("T3", "ETFRV", "DUALCLASS", "T7", "T12CEF", "ORB", "XS_GLSR_Z", "XS_SMART",
                "CEFMUNIEQ", "ETFRV_Z20", "DUALCLASS_EXIT10", "CRYPTO_LOWVOL",
                "SKEW_TILT", "SKEW_TILT_CRUDE"):
        st = state["legs"].get(lid)
        if not st:
            continue
        stream = [s["net"] for s in st["settled"]]
        k = kill_check(stream, spec)
        kill[lid] = k
        if write and k["verdict"].startswith("DEAD"):
            st["status"] = k["verdict"]

    record = {
        "kind": "session", "schema_version": SCHEMA_VERSION, "basket_id": spec["basket_id"],
        "session_date": session_date, "run_utc": now_utc.isoformat(),
        "mode": "proof (NOT ledger evidence)" if not write else "forward",
        "framing": FRAMING,
        "freeze": {"utc": spec["frozen_utc"], "preregistration_sha256": spec["preregistration_sha256"]},
        "vol_overlay": {k: ov[k] for k in ("rule_id", "reference_close_date",
                                           "realised_vol_annual", "w_vol", "cross_check")},
        "cash": cash, "r_cash_day": r_cash_day,
        "legs": legs_out, "combined": combined, "kill_switch": kill,
        "provenance": pin_report(),
    }

    if write:
        if state["inception_session"] is None and any_settled:
            state["inception_session"] = session_date
        state["last_session"] = session_date
        record["state_after"] = {k: state[k] for k in
                                 ("curves", "maxdd", "l1_pending", "legs", "inception_session")}
        append_ledger(record)
        save_state(state)
    return record


# ---------------------------------------------------------------------------
# Selftest -- hermetic, no network
# ---------------------------------------------------------------------------

def _selftest() -> int:
    spec = frozen_spec()
    out = {"framing": FRAMING, "freeze_verified": spec["_preregistration_sha256_verified"][:16],
           "checks": {}}

    # 1. lookahead assertion fires when a signal is not before its mark
    fired = False
    try:
        _assert_asof(("2026-08-20", "16:00"), ("2026-08-20", "16:00"), "TEST")
    except Refused:
        fired = True
    out["checks"]["lookahead_assertion_fires"] = fired
    if not fired:
        raise Refused("the lookahead assertion did not fire on a signal timestamp == mark timestamp")

    # 2. kill switch: a significantly-negative stream past N_min kills; a flat/positive one does not
    neg = [-0.001] * 45          # steady loser, n>N_min
    pos = [0.0005] * 45          # steady winner
    flat = [0.0, 0.0, 0.0]       # too few
    out["checks"]["kill_negative"] = kill_check(neg, spec)["verdict"]
    out["checks"]["kill_positive"] = kill_check(pos, spec)["verdict"]
    out["checks"]["kill_short_sample"] = kill_check(flat, spec)["verdict"]
    if not out["checks"]["kill_negative"].startswith("DEAD"):
        raise Refused("kill switch failed to kill a steady net loser past N_min")
    if out["checks"]["kill_positive"].startswith("DEAD"):
        raise Refused("kill switch wrongly killed a steady net winner")

    # 3. combined arithmetic: overlay scales the deployed gross, idle earns cash
    w_vol, b1, b2, r1, r2, rc = 0.8, 0.5, 0.5, 0.0006, 0.0002, 0.00011
    deployed = w_vol * (b1 + b2)
    r_comb = w_vol * b1 * r1 + w_vol * b2 * r2 + (1 - deployed) * rc
    out["checks"]["combined_example"] = {"w_vol": w_vol, "deployed_gross": deployed,
                                         "r_combined_net": r_comb, "r_benchmark": rc,
                                         "beats_cash": r_comb > rc}

    # 4. after the v9 corrective freeze the frozen spec exposes 4 SIZED ACTIVE legs + 8 UNSIZED
    #    loggers (L2 ETFRV and L4 T7 were DE-SIZED to ACTIVE_UNSIZED), no PENDING slots.
    active = [l["id"] for l in spec["legs"] if l["status"] == "ACTIVE"]
    unsized = [l["id"] for l in spec["legs"] if l["status"] == "ACTIVE_UNSIZED"]
    pending = [l["id"] for l in spec["legs"] if l["status"] == "PENDING_SPEC"]
    out["checks"]["active_legs"] = active
    out["checks"]["unsized_loggers"] = unsized
    out["checks"]["pending_slots"] = pending
    if active != ["T3", "DUALCLASS", "T12CEF", "ORB"]:
        raise Refused(f"expected 4 SIZED ACTIVE legs (L1 T3, L3 DUALCLASS, L5 T12CEF, L6 ORB) after "
                      f"the v9 de-sizings, got {active}")
    if unsized != ["ETFRV", "T7", "XS_GLSR_Z", "XS_SMART", "CEFMUNIEQ", "ETFRV_Z20",
                   "DUALCLASS_EXIT10", "CRYPTO_LOWVOL", "SKEW_TILT", "SKEW_TILT_CRUDE"]:
        raise Refused("expected ten UNSIZED loggers ETFRV (L2, v9), T7 (L4, v9), XS_GLSR_Z, "
                      "XS_SMART, CEFMUNIEQ, ETFRV_Z20, DUALCLASS_EXIT10, CRYPTO_LOWVOL, and the two "
                      "v10 options-flow challengers SKEW_TILT (L13), SKEW_TILT_CRUDE (L14), got "
                      f"{unsized}")
    if pending:
        raise Refused(f"expected no PENDING slots after the v9 freeze, got {pending}")

    # 5. every v2/v3/v4 leg's own spec_sha256 verifies; L1/L2 carry none and are unchanged
    hashes = {}
    for leg in spec["legs"]:
        h = leg.get("spec_sha256")
        if h:
            recomputed = _leg_spec_sha256(leg)
            if recomputed != h:
                raise Refused(f"leg {leg['id']} spec_sha256 does not verify in selftest")
            hashes[leg["id"]] = h[:16]
    out["checks"]["per_leg_spec_sha256_verified"] = hashes
    if set(hashes) != {"DUALCLASS", "T7", "T12CEF", "ORB", "XS_GLSR_Z", "XS_SMART", "CEFMUNIEQ",
                       "ETFRV_Z20", "DUALCLASS_EXIT10", "CRYPTO_LOWVOL",
                       "SKEW_TILT", "SKEW_TILT_CRUDE"}:
        raise Refused("expected per-leg hashes on the 4 v2 + 2 v3 + 1 v5 + 2 v7 + 1 v8 + 2 v10 legs, "
                      f"got {sorted(hashes)}")
    if "spec_sha256" in spec["legs"][0] or "spec_sha256" in spec["legs"][1]:
        raise Refused("L1/L2 must NOT carry a per-leg hash (they are unchanged from v1)")
    # the band variants' spec_sha256 are pinned; a drift means the frozen variant was edited. v9
    # recomputed both: L10 was marked fake-until-respecced (guard note), L11 had BRK.A/BRK.B dropped.
    if leg_by_id(spec, "ETFRV_Z20")["spec_sha256"] != \
            "b572b0a65e2d8a81e060751edf16d99f66ced99c4b2af31f05ce2ef209b6111a":
        raise Refused("L10 ETFRV_Z20 spec_sha256 drifted from its v9 freeze")
    if leg_by_id(spec, "DUALCLASS_EXIT10")["spec_sha256"] != \
            "1e0ab117d9440829e77b81b29344c6e9fd155a0d2ae7af0a239fed7997d2ab51":
        raise Refused("L11 DUALCLASS_EXIT10 spec_sha256 drifted from its v9 freeze")
    # the v8 leg's spec_sha256 is pinned; a drift means the frozen L12 spec was edited
    if leg_by_id(spec, "CRYPTO_LOWVOL")["spec_sha256"] != \
            "08f7e5a11b22872e549a1f1de99247ba001d6663baa06e9792e041bcc2ec7059":
        raise Refused("L12 CRYPTO_LOWVOL spec_sha256 drifted from its v8 freeze")
    # the v10 options-flow legs' spec_sha256 are pinned; a drift means a frozen L13/L14 spec was edited
    if leg_by_id(spec, "SKEW_TILT")["spec_sha256"] != \
            "51b1d87e5474172656f6cfc2b6289548ab40be5b41be8e6aabdf881c0ada1ed6":
        raise Refused("L13 SKEW_TILT spec_sha256 drifted from its v10 freeze")
    if leg_by_id(spec, "SKEW_TILT_CRUDE")["spec_sha256"] != \
            "b3f61b8f1813a46e9680d9a1dedceb09d109b9ddab3cf660e548cac4a3b94837":
        raise Refused("L14 SKEW_TILT_CRUDE spec_sha256 drifted from its v10 freeze")

    # 6. the mandatory per-leg guard is present on each v2/v3/v5/v7/v8/v10 leg
    for lid in ("DUALCLASS", "T7", "T12CEF", "ORB", "XS_GLSR_Z", "XS_SMART", "CEFMUNIEQ",
                "ETFRV_Z20", "DUALCLASS_EXIT10", "CRYPTO_LOWVOL", "SKEW_TILT", "SKEW_TILT_CRUDE"):
        if "guard_mandatory" not in leg_by_id(spec, lid):
            raise Refused(f"leg {lid} is missing its mandatory guard block")
    # L11 must retain L3's FUNCTIONAL easy-to-borrow whitelist (the engine reads it) byte-identical
    if leg_by_id(spec, "DUALCLASS_EXIT10")["guard_mandatory"]["etb_whitelist"] != \
            leg_by_id(spec, "DUALCLASS")["guard_mandatory"]["etb_whitelist"]:
        raise Refused("L11 DUALCLASS_EXIT10 must keep L3's ETB whitelist byte-identical")
    out["checks"]["guards_present"] = True

    # 7. EQUAL-WEIGHT budgets (zero-parameter -- the round-3 anti-fitting lesson, fitting cost -0.48
    #    Sharpe OOS). v9: the deployed dict is risk_budgets_active_v11 -- after DE-SIZING L2 ETFRV and
    #    L4 T7, FOUR
    # SIZED legs remain (T3, DUALCLASS, T12CEF, ORB) at equal 1/4; the eight logging-only legs carry
    # ZERO; the CEF class stays under its retained cap.
    active_dict = spec.get("risk_budgets_active_v11") or {}
    if not active_dict:
        raise Refused("risk_budgets_active_v11 is missing; the v9 re-normalisation must publish it")
    bsum = sum(v for k, v in active_dict.items() if k != "note")
    out["checks"]["risk_budget_v11_sum"] = round(bsum, 6)
    if abs(bsum - 1.0) > 1e-9:
        raise Refused(f"risk_budgets_active_v11 must sum to 1.0, got {bsum}")
    # the demoted (L2 ETFRV, L4 T7) and pre-existing unsized loggers carry ZERO in the deployed dict.
    for z in ("ETFRV", "T7", "XS_GLSR_Z", "XS_SMART", "CEFMUNIEQ"):
        if active_dict.get(z, None) != 0.0:
            raise Refused(f"unsized logger {z} must carry ZERO risk budget in v11, got {active_dict.get(z)}")
    for z in ("ETFRV", "T7", "CEFMUNIEQ"):
        if leg_by_id(spec, z)["risk_budget_fraction_active"] != 0.0:
            raise Refused(f"demoted/unsized leg {z} must carry ZERO leg-spec risk budget")
    # the ADDITIVE band/factor/options-flow loggers (L10/L11/L12/L13/L14) carry ZERO leg-spec budget
    # and are absent from the deployed dict by design (never in the combined book).
    for z in ("ETFRV_Z20", "DUALCLASS_EXIT10", "CRYPTO_LOWVOL", "SKEW_TILT", "SKEW_TILT_CRUDE"):
        if leg_by_id(spec, z)["risk_budget_fraction_active"] != 0.0:
            raise Refused(f"additive unsized logger {z} must carry ZERO leg-spec risk budget")
        if z in active_dict:
            raise Refused(f"additive unsized logger {z} must NOT appear in the deployed "
                          "risk_budgets_active_v11 (it never touches the combined book)")
    # the four SIZED legs carry EQUAL risk budgets (zero-parameter equal-dollar): spread is zero.
    sized = ("T3", "DUALCLASS", "T12CEF", "ORB")
    sized_budgets = [active_dict[k] for k in sized]
    out["checks"]["sized_leg_budgets"] = {k: active_dict[k] for k in sized}
    if max(sized_budgets) - min(sized_budgets) > 1e-9:
        raise Refused(f"the four SIZED legs must carry EQUAL risk budgets (equal-weight), got "
                      f"{dict(zip(sized, sized_budgets))}")
    expected_each = 1.0 / len(sized)
    if abs(sized_budgets[0] - expected_each) > 1e-9:
        raise Refused(f"each SIZED leg must carry 1/{len(sized)}={expected_each}, got {sized_budgets[0]}")
    cef_class = active_dict.get("T12CEF", 0.0) + active_dict.get("CEFMUNIEQ", 0.0)
    out["checks"]["cef_class_deployed"] = round(cef_class, 6)
    cap = leg_by_id(spec, "CEFMUNIEQ")["guard_mandatory"]["combined_cef_cap_fraction"]
    if cef_class > cap + 1e-9:
        raise Refused(f"combined CEF class {cef_class} exceeds the mandatory cap {cap}")

    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report() -> dict:
    spec = frozen_spec()
    state = load_state(spec)
    records = [r for r in read_ledger() if r.get("kind") == "session"]
    legs = {}
    for lid in ("T3", "ETFRV", "DUALCLASS", "T7", "T12CEF", "ORB", "XS_GLSR_Z", "XS_SMART",
                "CEFMUNIEQ", "ETFRV_Z20", "DUALCLASS_EXIT10", "CRYPTO_LOWVOL",
                "SKEW_TILT", "SKEW_TILT_CRUDE"):
        leg = leg_by_id(spec, lid)
        st = state["legs"].get(lid, {"status": leg["status"], "settled": []})
        stream = [s["net"] for s in st["settled"]]
        legs[lid] = {"status": st["status"], "settled_observations": len(stream),
                     "logged_unsized": leg.get("status") == "ACTIVE_UNSIZED",
                     "kill_switch": kill_check(stream, spec)}
    return {
        "framing": FRAMING,
        "basket_id": spec["basket_id"],
        "freeze": {"utc": spec["frozen_utc"], "preregistration_sha256": spec["preregistration_sha256"][:16]},
        "active_legs": [l["id"] for l in spec["legs"] if l["status"] == "ACTIVE"],
        "unsized_loggers": [l["id"] for l in spec["legs"] if l["status"] == "ACTIVE_UNSIZED"],
        "pending_slots": [l["id"] for l in spec["legs"] if l["status"] == "PENDING_SPEC"],
        "runs_logged": len(records),
        "inception_session": state["inception_session"],
        "last_session": state["last_session"],
        "combined_equity": state["curves"], "combined_maxdd": state["maxdd"],
        "legs": legs,
        "minimum_before_verdict": spec["minimum_before_verdict"],
        "how_to_read": HOW_TO_READ,
    }


HOW_TO_READ = [
    "1. THIS IS A LOGGER. No orders, no position, no real money. Every P&L is hypothetical.",
    "2. START WITH THE DENOMINATOR. Below the per-leg N_min (40) and the combined 252-session "
    "minimum, this records behaviour, not evidence. No Sharpe/CAGR/p-value is licensed early.",
    "3. THE BENCHMARK IS T-BILLS, not zero. An unlevered market-neutral book must beat T-bills + "
    "1 pp/yr to count.",
    "4. THE KILL SWITCH ONLY FIRES ON A SIGNIFICANTLY-NEGATIVE LEG (one-sided upper 95% bound < 0 "
    "past N_min). A merely-flat leg is not killed; it is retired UNPROVEN only at N_max=500.",
    "5. A killed leg's budget is NOT reallocated. Reallocating on a forward outcome is a search.",
    "6. EVERY BACKTESTED NUMBER BEHIND THESE LEGS IS A SELECTION-INFLATED UPPER BOUND. The realised "
    "forward number is the only evidence, and the honest prior is a Sharpe well below the 1.0-1.3 "
    "backtest.",
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.trading_bot.basket_forward",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="hermetic wiring check; no network, no ledger")
    sub.add_parser("status", help="the frozen spec, the legs live vs pending, the track record")
    sub.add_parser("report", help="the accruing per-leg + combined track record with the reading protocol")
    p = sub.add_parser("proof", help="real run on the most-recent COMPLETE session; NOT written to the ledger")
    p.add_argument("--session", default=None, help="override the session date (YYYY-MM-DD)")
    s = sub.add_parser("session", help="log one forward session (freeze-forward only)")
    s.add_argument("--session", default=None, help="override the session date (YYYY-MM-DD)")
    s.add_argument("--offline", action="store_true", help="cache only; never touch the network")
    s.add_argument("--refresh-cash", action="store_true", help="best-effort FRED DTB3 refresh")
    s.add_argument("--force", action="store_true", help="re-log a session already in the ledger")

    args = parser.parse_args(argv)
    if args.command == "selftest":
        return _selftest()
    if args.command in ("status", "report"):
        payload = report()
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0
    if args.command == "proof":
        rec = run_session(session_date=args.session, write=False, allow_network=True)
        json.dump(rec, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0
    # session
    rec = run_session(session_date=args.session, write=True, allow_network=not args.offline,
                      refresh_cash=args.refresh_cash, force=args.force)
    json.dump(rec, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
