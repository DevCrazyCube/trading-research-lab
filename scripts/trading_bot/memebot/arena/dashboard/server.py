#!/usr/bin/env python3
"""MEME ARENA dashboard — a polished, read-only view of the frozen multi-arm forward measurement.

    python -m scripts.trading_bot.memebot.arena.dashboard.server        # 127.0.0.1:8795

One clean single page (GMGN/Padre style, theme-aware) that mirrors the memebot :8791 dashboard and goes
further for the Arena:

  * a VERDICT card per arm straight from runtime.report_arm (verdict, resolved/target_n, mean net-R, the
    CLUSTER-bootstrap CI, chain-verified badge, fill basis, reason), with an equity curve drawn from that
    arm's own hash-chained ledger.
  * a LIVE MINT panel per arm: every OPEN position and the most-recent RESOLVED trades, each with a
    click-to-COPY mint, live MARKET CAP, HOLDERS, live PRICE, entry/peak, age and net-R.
  * live PRICE / MARKET CAP / HOLDERS come from HELIUS (getAsset for price+supply+symbol,
    getTokenAccounts for holder count). When Helius has no price for a fresh/rugged mint it falls back to
    the arm's own pinned DexScreener pair (the same feed the runtime marks positions on); market cap from
    the position's marketCapSol -> USD (via the live SOL/USD) is the last resort. Nothing is fabricated —
    a genuinely unavailable value renders as an honest "—".
  * a JSON API at /api/state that a tiny vanilla-JS frontend polls every ~2s and applies to the DOM in
    place (no full-page reload); a lightweight server-rendered fallback paints before the first poll and
    stays visible if polling ever fails.

READ-ONLY. There is NO order path, NO wallet, NO real SOL, and NO trading endpoint here by construction —
exactly like the arena runtime it watches. Bound to 127.0.0.1 only. Reuses the arena's OWN modules
(runtime / report_arm / the honest fill / the hash-chained ledger) so every number matches the collector.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import manifest as MF
from .. import runtime as RT
from ... import ws_data


# ---- which arms the dashboard renders -------------------------------------------------------------
# NOT runtime._registered_arms(): that is the CLOSURE registry (virality + the archived V1 bundle/graduation
# controls), so it would both HIDE the live causal V2 arms — which are deliberately kept out of the registry
# so a scorer edit can't drift their closures — AND surface the retired V1 controls as if they were still
# running (the display bug Codex flagged). The honest "what is actually live" set is instead: every arm that
# has an activation file on disk. We key candidate arms by their own .instrument (no hard-coded strings) and
# keep only the activated ones, in a stable display order.
_ARM_MODULES = ("virality_arrival", "bundle_momentum_v2", "migration_acceptance",
                "bundle_momentum", "graduation")
_DISPLAY_ORDER = ("VIRALITY_ARRIVAL_V2_2", "BUNDLE_MOMENTUM_V2", "MIGRATION_ACCEPTANCE_V1")


def _candidate_arms() -> list:
    pkg = __package__.rsplit(".", 1)[0]        # scripts...arena.dashboard -> scripts...arena
    arms = []
    for mod in _ARM_MODULES:
        try:
            arms.append(importlib.import_module(f"{pkg}.arms.{mod}").ARM)
        except Exception:  # noqa: BLE001 — a missing/broken arm module simply isn't shown
            continue
    return arms


def _display_arms() -> list:
    """The arms to render = every arm with an activation file on disk (the honest live set), ordered by
    _DISPLAY_ORDER then instrument. Falls back to the closure registry only when nothing is activated yet,
    so the page is never blank on a cold start."""
    active = []
    for arm in _candidate_arms():
        try:
            if MF.activation_path(arm).exists():
                active.append(arm)
        except Exception:  # noqa: BLE001
            continue
    if not active:
        return RT._registered_arms()

    def _key(a):
        try:
            return (_DISPLAY_ORDER.index(a.instrument), a.instrument)
        except ValueError:
            return (len(_DISPLAY_ORDER), a.instrument)

    return sorted(active, key=_key)

HOST, PORT = "127.0.0.1", 8795
ROOT = pathlib.Path(__file__).resolve().parents[5]
ENV_PATH = ROOT / ".env"

WSOL_MINT = "So11111111111111111111111111111111111111112"

# ---- enrichment cadence / bounds (all read-only Helius calls) ----
PRICE_TTL = 30.0            # a mint's live price/mcap is refreshed no more than this often
HOLDERS_TTL = 300.0        # holder count changes slowly; refresh rarely (paging is the expensive call)
SOL_TTL = 60.0             # SOL/USD refresh cadence
HELIUS_GAP = 0.35          # polite gap between any two Helius calls (single background worker)
HELIUS_TIMEOUT = 9.0
HOLDER_PAGE_LIMIT = 1000
HOLDER_MAX_PAGES = 4       # cap paging; beyond this the count is shown as "N+"
RECENT_RESOLVED = 12       # most-recent resolved trades surfaced per arm
STATE_TTL = 2.5            # server-side memo of the heavy /api/state build (rapid polls reuse it)

VCOL = {"PASS": "#1a9e5f", "PASS_TO_CONFIRMATION": "#1a9e5f", "PASS_PENDING_SENSITIVITY": "#c99a00",
        "COLLECTING": "#5b6bd6", "UNDECIDED_EXTEND": "#c99a00", "BLOCKED_DATA_AUTH": "#c99a00",
        "KILL": "#d0453b", "NOT_ACTIVE": "#7a7f87", "INVALID": "#d0453b", "UNSET": "#7a7f87"}


# ---------------------------------------------------------------- .env + Helius (read-only)
def _read_env(key: str) -> str | None:
    try:
        text = ENV_PATH.read_text()
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return (v.strip().strip('"').strip("'")) or None
    return None


import os  # noqa: E402  (after the stdlib block on purpose; keeps the env helpers together)

HELIUS_KEY = os.environ.get("HELIUS_API_KEY") or _read_env("HELIUS_API_KEY")
_HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}" if HELIUS_KEY else None
_HELIUS_LOCK = threading.Lock()
_helius_last = [0.0]


def _helius_rpc(method: str, params):
    """ONE paced, read-only JSON-RPC call to Helius. Returns the `result`, or None on any failure."""
    if not _HELIUS_URL:
        return None
    with _HELIUS_LOCK:
        wait = HELIUS_GAP - (time.monotonic() - _helius_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
            req = urllib.request.Request(_HELIUS_URL, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=HELIUS_TIMEOUT) as resp:
                out = json.loads(resp.read())
            return out.get("result") if isinstance(out, dict) else None
        except Exception:  # noqa: BLE001 -- transport / plan / rate: fall back to an honest "—"
            return None
        finally:
            _helius_last[0] = time.monotonic()


def _helius_asset(mint: str) -> dict | None:
    """price_per_token (USD), symbol, market cap = price x (supply / 10^decimals) — or None."""
    r = _helius_rpc("getAsset", {"id": mint})
    if not isinstance(r, dict):
        return None
    ti = r.get("token_info") or {}
    price = ((ti.get("price_info") or {}).get("price_per_token"))
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    supply = ti.get("supply")
    dec = ti.get("decimals")
    mcap = None
    try:
        if price is not None and supply is not None and dec is not None:
            ui = float(supply) / (10 ** int(dec))
            mcap = price * ui
    except (TypeError, ValueError):
        mcap = None
    sym = ti.get("symbol") or ((r.get("content") or {}).get("metadata") or {}).get("symbol")
    return {"price_usd": price, "market_cap_usd": mcap, "symbol": sym}


def _helius_holders(mint: str) -> tuple[int | None, bool]:
    """Bounded holder count via DAS getTokenAccounts paging. (count, exact). None if unavailable."""
    total = 0
    for page in range(1, HOLDER_MAX_PAGES + 1):
        r = _helius_rpc("getTokenAccounts",
                        {"mint": mint, "limit": HOLDER_PAGE_LIMIT, "page": page})
        accts = (r or {}).get("token_accounts")
        if not isinstance(accts, list):
            return (None, False) if total == 0 else (total, False)
        total += len(accts)
        if len(accts) < HOLDER_PAGE_LIMIT:
            return total, True            # last page reached -> exact count
    return total, False                    # hit the page cap -> "N+"


# ---------------------------------------------------------------- enrichment cache (background)
_enrich: dict[str, dict] = {}              # mint -> {price_usd, market_cap_usd, symbol, holders,
#                                                     holders_exact, source, price_ts, holders_ts}
_enrich_lock = threading.Lock()
_sol = {"usd": None, "ts": 0.0, "source": None}


def _pinned_fallback(pair: str | None) -> dict | None:
    """When Helius has no price, re-price on the arm's OWN pinned DexScreener pair (honest, in-project)."""
    if not pair:
        return None
    try:
        from ... import virality_tracker as VT
        c = VT._pinned_pair(pair)
    except Exception:  # noqa: BLE001
        return None
    if not c or not c.get("price"):
        return None
    return {"price_usd": c.get("price"), "market_cap_usd": c.get("fdv_usd"),
            "liquidity_usd": c.get("reserve_usd"), "symbol": c.get("symbol")}


def _sol_usd() -> tuple[float | None, str | None]:
    now = time.time()
    if _sol["usd"] is not None and (now - _sol["ts"]) < SOL_TTL:
        return _sol["usd"], _sol["source"]
    a = _helius_asset(WSOL_MINT)
    if a and a.get("price_usd"):
        _sol.update(usd=a["price_usd"], ts=now, source="helius")
    else:
        _sol["ts"] = now                    # avoid hammering on failure; keep last good value
    return _sol["usd"], _sol["source"]


def _enrich_mint(mint: str, pair: str | None, mcap_sol) -> None:
    """Refresh one mint's price/mcap/holders into the shared cache (Helius first, pinned pair fallback,
    marketCapSol->USD as a last resort). Runs only on the background worker; never fabricates a value."""
    now = time.time()
    with _enrich_lock:
        cur = _enrich.get(mint, {})
    price_due = (now - cur.get("price_ts", 0.0)) >= PRICE_TTL
    holders_due = (now - cur.get("holders_ts", 0.0)) >= HOLDERS_TTL
    upd = dict(cur)
    if price_due:
        a = _helius_asset(mint)
        source = None
        price = mcap = symbol = None
        if a and (a.get("price_usd") is not None or a.get("market_cap_usd") is not None):
            price, mcap, symbol, source = a.get("price_usd"), a.get("market_cap_usd"), a.get("symbol"), "helius"
        if price is None:
            fb = _pinned_fallback(pair)
            if fb:
                price = fb.get("price_usd")
                mcap = mcap if mcap is not None else fb.get("market_cap_usd")
                symbol = symbol or fb.get("symbol")
                source = source or "dexscreener"
        if mcap is None and mcap_sol not in (None, "", "None"):
            sol_usd, _ = _sol_usd()
            try:
                if sol_usd is not None:
                    mcap = float(mcap_sol) * float(sol_usd)
                    source = source or "marketCapSol"
            except (TypeError, ValueError):
                pass
        upd.update(price_usd=price, market_cap_usd=mcap,
                   symbol=symbol or cur.get("symbol"), source=source, price_ts=now)
    if holders_due:
        h, exact = _helius_holders(mint)
        upd.update(holders=h, holders_exact=exact, holders_ts=now)
    with _enrich_lock:
        _enrich[mint] = upd


def _wanted_mints() -> list[tuple[str, str | None, object]]:
    """Every mint worth enriching this pass: open positions + recent resolved, across all arms.
    Returns (mint, pinned_pair_or_None, market_cap_sol_or_None)."""
    seen: dict[str, tuple[str | None, object]] = {}
    for arm in _display_arms():
        try:
            state = RT._load(RT.DATA / arm.instrument / "state.json", {"open": {}})
        except Exception:  # noqa: BLE001
            state = {"open": {}}
        for mint, pos in (state.get("open") or {}).items():
            pair = pos.get("pair") if isinstance(pos, dict) else None
            mcs = pos.get("market_cap_sol") or pos.get("marketCapSol") if isinstance(pos, dict) else None
            seen.setdefault(mint, (pair, mcs))
        for row in _raw_resolved(arm)[-RECENT_RESOLVED:]:
            m = row.get("mint")
            if m:
                seen.setdefault(m, (None, None))
    return [(m, p, s) for m, (p, s) in seen.items()]


def _enrich_worker() -> None:
    while True:
        wanted = _wanted_mints()
        if not wanted:
            time.sleep(4.0)
            continue
        _sol_usd()
        for mint, pair, mcs in wanted:
            _enrich_mint(mint, pair, mcs)
        # prune mints no longer wanted so the cache does not grow without bound
        keep = {m for m, _, _ in wanted}
        with _enrich_lock:
            for gone in [m for m in _enrich if m not in keep]:
                _enrich.pop(gone, None)
        time.sleep(2.0)


def _mint_enrichment(mint: str) -> dict:
    with _enrich_lock:
        e = dict(_enrich.get(mint, {}))
    return {"price_usd": e.get("price_usd"), "market_cap_usd": e.get("market_cap_usd"),
            "symbol": e.get("symbol"), "holders": e.get("holders"),
            "holders_exact": e.get("holders_exact"), "price_source": e.get("source")}


# ---------------------------------------------------------------- ledger / state assembly
def _raw_resolved(arm) -> list[dict]:
    """Resolved rows straight from the arm's on-disk ledger file. Read-only, no activation required, so a
    NOT_ACTIVE / diagnostic arm still surfaces whatever it legitimately resolved."""
    path = RT.DATA / arm.instrument / "ledger.jsonl"
    if not path.exists():
        return []
    out = []
    try:
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("kind") == "resolved":
                    out.append(row)
    except OSError:
        return []
    return out


def _equity(arm) -> list[dict]:
    """Cumulative net-R curve over the arm's resolved trades, in ledger order (the arm's own numbers)."""
    cum = 0.0
    curve = []
    for i, r in enumerate(_raw_resolved(arm)):
        try:
            cum += float(r.get("net_return") or 0.0)
        except (TypeError, ValueError):
            continue
        curve.append({"i": i, "cum": round(cum, 6), "net": r.get("net_return")})
    return curve


def _age_min(pos: dict) -> float | None:
    ts = pos.get("opened_ts")
    if ts is None:
        ns = pos.get("entry_unix_nanos") or pos.get("opened_unix_nanos")
        ts = ns / 1e9 if isinstance(ns, (int, float)) else None
    if ts is None:
        return None
    try:
        return max(0.0, (time.time() - float(ts)) / 60.0)
    except (TypeError, ValueError):
        return None


def _live_net_r(basis: str, entry_price, live_price) -> float | None:
    """The arm's OWN honest snapshot fill, marked to the live price. Only meaningful on the snapshot
    basis; the executable (causal_cp / pumpswap) bases need reserves we do not have here -> honest None."""
    if basis != "snapshot":
        return None
    try:
        if entry_price and live_price and float(entry_price) > 0 and float(live_price) >= 0:
            return round(RT.F.honest_fill_snapshot(float(entry_price), float(live_price)).net_return, 4)
    except Exception:  # noqa: BLE001
        return None
    return None


def _open_rows(arm, state: dict) -> list[dict]:
    rows = []
    for mint, pos in (state.get("open") or {}).items():
        if not isinstance(pos, dict):
            continue
        enr = _mint_enrichment(mint)
        entry = pos.get("entry_price")
        rows.append({
            "mint": mint,
            "symbol": enr["symbol"],
            "entry_price": entry,
            "peak": pos.get("peak"),
            "age_min": _age_min(pos),
            "delay_min": pos.get("entry_delay_min"),
            "unpriced_count": pos.get("unpriced_count"),
            "cohort": pos.get("cohort"),
            "live_price": enr["price_usd"],
            "market_cap_usd": enr["market_cap_usd"],
            "holders": enr["holders"],
            "holders_exact": enr["holders_exact"],
            "price_source": enr["price_source"],
            "live_net_r": _live_net_r(arm.fill_basis, entry, enr["price_usd"]),
        })
    rows.sort(key=lambda r: (r["age_min"] if r["age_min"] is not None else 1e12))
    return rows


def _resolved_rows(arm) -> list[dict]:
    rows = []
    for r in _raw_resolved(arm)[-RECENT_RESOLVED:][::-1]:      # newest first
        mint = r.get("mint")
        enr = _mint_enrichment(mint) if mint else {}
        held_s = r.get("held_s")
        rows.append({
            "mint": mint,
            "symbol": enr.get("symbol"),
            "reason": r.get("reason"),
            "net_return": r.get("net_return"),
            "entry_price": r.get("entry_price"),
            "exit_price": r.get("exit_price"),
            "held_min": (round(held_s / 60.0, 1) if isinstance(held_s, (int, float)) else None),
            "delay_min": r.get("minutes_since_first_seen"),
            "cohort": r.get("gate_tier") or r.get("cohort"),
            "live_price": enr.get("price_usd"),
            "market_cap_usd": enr.get("market_cap_usd"),
            "holders": enr.get("holders"),
            "holders_exact": enr.get("holders_exact"),
            "price_source": enr.get("price_source"),
        })
    return rows


# One-line thesis + formula per arm (what the strategy IS), shown in the Formula/thesis panel. These are
# descriptions of the pre-registered design, not profit claims — every arm is EXPECTED to KILL absent a
# proven edge, and the panel says so.
_ARM_THESIS = {
    "VIRALITY_ARRIVAL_V2_2": {
        "formula": "late-boost arrival · snapshot fill · resolve every open",
        "note": "not an edge — measures whether a virality/late-boost signal survives honest, "
                "no-lookahead marking. Diagnostic mean is negative; expected to KILL.",
    },
    "BUNDLE_MOMENTUM_V2": {
        "formula": "coverage-gated bundle · causal constant-product fill · $10 clip · max-2 concurrent",
        "note": "not an edge — harvests early-clump momentum with executable fills (walks the curve for "
                "real size + toll + latency). Grabs often, cuts rugs small. Expected to KILL.",
    },
    "MIGRATION_ACCEPTANCE_V1": {
        "formula": "post-confirmed migration · exit-capacity STRESS test · PumpSwap exact CP",
        "note": "not an edge — only enters a graduated pool that absorbs >=2 position-size sells AND a "
                "full-clip recovery; a fail is STRATEGY_VOID, never a trade. Expected to KILL.",
    },
}


def _arm_stats(arm) -> dict:
    """Aggregate KPIs computed from the arm's OWN resolved ledger (all cohorts): win rate, unexitable full
    losses, a normalized compounding capital index, and its max drawdown. Numbers, not verdicts."""
    resolved = _raw_resolved(arm)
    nets = []
    for r in resolved:
        try:
            nets.append(float(r.get("net_return")))
        except (TypeError, ValueError):
            continue
    wins = sum(1 for n in nets if n > 0)
    losses = sum(1 for n in nets if n <= 0)
    unexitable = sum(1 for n in nets if n <= -0.9)          # a near-total loss = couldn't exit / rug
    # normalized paper index: 100 compounding by each resolved net-R, and its worst peak-to-trough
    idx = 100.0
    curve = [100.0]
    peak = 100.0
    max_dd = 0.0
    for n in nets:
        idx *= (1.0 + n)
        idx = max(idx, 0.0)
        curve.append(round(idx, 4))
        peak = max(peak, idx)
        if peak > 0:
            max_dd = max(max_dd, (peak - idx) / peak)
    return {
        "n_resolved_all": len(nets),
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / len(nets)) if nets else None,
        "unexitable": unexitable,
        "mean_all": (sum(nets) / len(nets)) if nets else None,
        "capital_index": round(idx, 4) if nets else None,
        "max_drawdown": round(max_dd, 4) if nets else None,
        "index_curve": curve,
    }


def _arm_view(arm) -> dict:
    rep = RT.report_arm(arm)
    verdict = rep.get("verdict", "UNSET")
    reason = rep.get("reason", "")
    # code + prereg are frozen but no paid trade key -> say so plainly instead of a bare NOT_ACTIVE.
    if verdict == "NOT_ACTIVE" and getattr(arm, "requires_trade_data", False) \
            and not ws_data.trade_data_authorized():
        verdict = "BLOCKED_DATA_AUTH"
        reason = ("code/prereg frozen; dedicated paid PumpPortal data key absent — no trade tape, no "
                  "activation, no fabricated evidence")
    try:
        state = RT._load(RT.DATA / arm.instrument / "state.json", {"open": {}})
    except Exception:  # noqa: BLE001
        state = {"open": {}}
    open_rows = _open_rows(arm, state)
    return {
        "instrument": arm.instrument,
        "basis": rep.get("basis", getattr(arm, "fill_basis", "?")),
        "verdict": verdict,
        "color": VCOL.get(verdict, "#7a7f87"),
        "reason": reason,
        "resolved": rep.get("resolved", 0),
        "target_n": rep.get("target_n", getattr(arm, "target_n", None)),
        "open": len(open_rows),
        "open_reported": rep.get("open", 0),
        "mean": rep.get("mean"),
        "ci_lo": rep.get("ci_lo"),
        "ci_hi": rep.get("ci_hi"),
        "n_clusters": rep.get("n_clusters"),
        "chain_ok": bool(rep.get("chain_ok")),
        "distinct_mints": rep.get("distinct_mints"),
        "pending": rep.get("pending"),
        "control_mean": rep.get("control_mean"),
        "control_n": rep.get("control_n"),
        "equity": _equity(arm),
        "open_positions": open_rows,
        "resolved_recent": _resolved_rows(arm),
        "stats": _arm_stats(arm),
        "thesis": _ARM_THESIS.get(arm.instrument, {"formula": rep.get("basis", ""), "note": ""}),
    }


_state_cache = {"exp": 0.0, "val": None}
_state_lock = threading.Lock()


def _build_state() -> dict:
    sol_usd, sol_src = _sol_usd()
    arms = [_arm_view(a) for a in _display_arms()]
    feed = ws_data.stream_health()
    if not feed["ok"]:
        for arm in arms:
            if arm["instrument"] in {"BUNDLE_MOMENTUM_V2", "MIGRATION_ACCEPTANCE_V1"}:
                arm["verdict"] = f"FEED_{feed['status']}"
                arm["color"] = "#ff5c5c"
                arm["reason"] = feed["reason"]
    return {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generated_unix": time.time(),
        "helius": bool(_HELIUS_URL),
        "sol_usd": sol_usd,
        "sol_usd_source": sol_src,
        "trade_feed": feed,
        "arms": arms,
        "note": ("READ-ONLY paper forward measurement. No orders, no wallet, no real SOL. A number below "
                 "the pre-registered target is an input, not a verdict; a KILL is decisive, a PASS earns "
                 "only a stricter causal test."),
    }


def state_view() -> dict:
    now = time.time()
    if _state_cache["val"] is not None and _state_cache["exp"] > now:
        return _state_cache["val"]
    with _state_lock:
        if _state_cache["val"] is not None and _state_cache["exp"] > time.time():
            return _state_cache["val"]
        val = _build_state()
        _state_cache["val"] = val
        _state_cache["exp"] = time.time() + STATE_TTL
        return val


# ---------------------------------------------------------------- the single page (HTML/CSS/JS)
PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MEME ARENA</title><style>
:root{
--bg:#0a0b0e;--bg2:#0d0f12;--panel:#0f1216;--panel2:#12161b;--row:#111419;
--line:#1b1f26;--line2:#242a33;
--text:#d5dbe3;--text2:#8a93a0;--text3:#59616d;
--mint:#3ee08f;--mint-dim:#2ba86b;--mint-bg:rgba(62,224,143,.10);
--red:#ff4d4d;--red-bg:rgba(255,77,77,.10);
--amber:#e8b153;--amber-bg:rgba(232,177,83,.10);
--mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,"DejaVu Sans Mono",Consolas,monospace;
--sans:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
*{box-sizing:border-box;border-radius:0!important}
html,body{margin:0;min-height:100%}
body{background:var(--bg);color:var(--text);font:12.5px/1.45 var(--sans);-webkit-font-smoothing:antialiased}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
a{color:inherit;text-decoration:none}
::-webkit-scrollbar{width:9px;height:9px}::-webkit-scrollbar-thumb{background:var(--line2)}
::-webkit-scrollbar-track{background:transparent}
.shell{display:flex;flex-direction:column;min-height:100vh}
/* topbar + tabs */
.topbar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:0 16px;min-height:46px;
background:var(--bg2);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:40}
.brand{display:flex;align-items:baseline;gap:8px}
.brand .logo{color:var(--mint);font-size:15px;position:relative;top:1px}
.brand .bt{font-weight:800;letter-spacing:1px;font-size:13px;color:var(--text)}
.nav{display:inline-flex;border:1px solid var(--line2);flex-wrap:wrap}
.navlink{display:inline-flex;align-items:center;gap:7px;font:700 10px var(--mono);letter-spacing:.6px;
color:var(--text2);padding:7px 12px;border-right:1px solid var(--line2);cursor:pointer}
.navlink:last-child{border-right:0}
.navlink:hover{color:var(--text)}
.navlink.on{background:var(--mint-bg);color:var(--text)}
.navlink .nd{width:7px;height:7px;flex:none;box-shadow:0 0 6px currentColor}
.navlink .nv{font-size:8.5px;font-weight:700;opacity:.85}
.grow{flex:1}
.live{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--text2)}
.ld{width:7px;height:7px;background:var(--text3);transition:background .3s}
.ld.on{background:var(--mint);box-shadow:0 0 6px var(--mint)}.ld.err{background:var(--red)}
.sbit{font-size:11px;color:var(--text2)}.sbit b{color:var(--text)}
.upd{font-size:10.5px;color:var(--text3)}
main{flex:1}
/* strip */
.strip{display:flex;flex-wrap:wrap;border-bottom:1px solid var(--line);background:var(--bg2)}
.strip .cell{flex:1 1 150px;padding:10px 16px;border-right:1px solid var(--line);min-width:0}
.strip .cell:last-child{border-right:0}
.strip .lbl{font-size:9px;letter-spacing:.9px;text-transform:uppercase;color:var(--text3);margin-bottom:4px;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.strip .val{font:600 17px/1 var(--mono);font-variant-numeric:tabular-nums;color:var(--text)}
.strip .sub{font-size:10px;color:var(--text2);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pos{color:var(--mint)}.neg{color:var(--red)}.muted{color:var(--text3)}.warn{color:var(--amber)}
/* layout */
.layout{display:grid;grid-template-columns:minmax(0,2fr) minmax(300px,.8fr);border-bottom:1px solid var(--line)}
@media(max-width:950px){.layout{grid-template-columns:1fr}}
.chartcard{min-width:0;background:linear-gradient(180deg,var(--panel),var(--bg));border-right:1px solid var(--line)}
@media(max-width:950px){.chartcard{border-right:0;border-bottom:1px solid var(--line)}}
.cardhead{display:flex;align-items:flex-end;justify-content:space-between;padding:15px 18px 5px;gap:12px}
.eyebrow{font:700 9px var(--mono);letter-spacing:1px;color:var(--text3)}
.cardhead h3{margin:3px 0 0;font:700 14px var(--sans);color:var(--text)}
.last{font:700 24px/1 var(--mono);font-variant-numeric:tabular-nums}
.chart{height:290px;padding:0 10px;position:relative}
.chart svg{width:100%;height:100%;overflow:visible}
.gridline{stroke:var(--line);stroke-width:1}.axis{fill:var(--text3);font:9px var(--mono)}
.baseline{stroke:var(--amber);stroke-width:1;stroke-dasharray:5 5;opacity:.7}
.area{opacity:.08}.area.up{fill:var(--mint)}.area.down{fill:var(--red)}
.eline{fill:none;stroke-width:2;vector-effect:non-scaling-stroke}.eline.up{stroke:var(--mint)}.eline.down{stroke:var(--red)}
.epoint.up{fill:var(--mint)}.epoint.down{fill:var(--red)}
.wait{fill:var(--text2);font:700 11px var(--mono);letter-spacing:.5px}
.chartnote{padding:2px 18px 14px;color:var(--text3);font:10px/1.45 var(--mono)}
.side{background:var(--panel);display:flex;flex-direction:column}
.panel{padding:15px 16px;border-bottom:1px solid var(--line)}.panel:last-child{border-bottom:0}
.ptitle{font:700 9px var(--mono);letter-spacing:1px;color:var(--text3)}
.formula{font:700 15px var(--mono);color:var(--mint);padding:9px 0 5px;line-height:1.5;word-break:break-word}
.fnote{font-size:10.5px;color:var(--text2);line-height:1.5}
.gates{margin-top:8px;display:flex;flex-direction:column;gap:1px}
.gate{display:grid;grid-template-columns:8px 96px 1fr;align-items:center;gap:8px;padding:6px 0;
border-bottom:1px solid var(--line);font:10px var(--mono);color:var(--text2)}
.gate:last-child{border-bottom:0}
.gate strong{font-weight:600;text-align:right;color:var(--text)}
.gate .dot{width:6px;height:6px}.gate .dot.ok{background:var(--mint);box-shadow:0 0 4px var(--mint)}
.gate .dot.bad{background:var(--red)}.gate .dot.warn{background:var(--amber)}
/* section header + pills + tables */
.pagehd{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:9px 16px;border-bottom:1px solid var(--line);background:var(--panel)}
.pagehd h3{margin:0;font:700 13px var(--sans);color:var(--text)}
.pill{font:700 9px var(--mono);letter-spacing:.6px;text-transform:uppercase;color:var(--text2);
background:var(--panel2);border:1px solid var(--line2);padding:4px 9px}
.pill b{color:var(--text)}
.tablewrap{overflow:auto;max-height:60vh}
table.grid{width:100%;border-collapse:separate;border-spacing:0;font-size:12px}
table.grid thead th{position:sticky;top:0;background:var(--bg2);z-index:20;text-align:right;
font:700 9.5px var(--sans);letter-spacing:.5px;text-transform:uppercase;color:var(--text3);
padding:8px 12px;border-bottom:1px solid var(--line2);white-space:nowrap;box-shadow:0 1px 0 var(--line2)}
table.grid thead th.l{text-align:left}
table.grid tbody td{padding:7px 12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;
font-family:var(--mono);font-variant-numeric:tabular-nums;color:var(--text)}
table.grid tbody td.l{text-align:left;font-family:var(--sans)}
table.grid tbody tr:hover{background:var(--row)}
table.grid tbody tr:hover .sym{color:var(--mint)}
.coin{display:flex;align-items:center;gap:9px;min-width:0}
.ic{width:22px;height:22px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;
font:700 10px var(--mono);border:1px solid var(--line2)}
.coin .nm{min-width:0}
.coin .sym{font-weight:700;color:var(--text);font-size:12px;line-height:1.15;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.coin .sym .cp{font:700 8px var(--mono);color:var(--text3)}
.coin .sym:hover .cp{color:var(--mint)}
.coin .full{color:var(--text3);font-size:9.5px;line-height:1.15;overflow:hidden;text-overflow:ellipsis;max-width:150px}
.vtag{font:700 9px var(--mono);color:var(--text2);background:var(--panel2);border:1px solid var(--line2);padding:2px 6px;letter-spacing:.3px}
.badge{display:inline-block;font:700 9px var(--mono);padding:2px 7px;letter-spacing:.4px;text-transform:uppercase;border:1px solid transparent}
.b-open{background:var(--mint-bg);color:var(--mint);border-color:rgba(62,224,143,.25)}
.b-void{background:var(--amber-bg);color:var(--amber);border-color:rgba(232,177,83,.3)}
.b-loss{background:var(--red-bg);color:var(--red)}
.b-done{background:var(--panel2);color:var(--text2);border-color:var(--line2)}
.rtag{font:9.5px var(--mono);color:var(--text2)}
.empty{padding:26px 16px;color:var(--text3);font-size:12px;text-align:center}
.foot{padding:11px 16px 20px;color:var(--text3);font-size:10px;text-align:center;border-top:1px solid var(--line);margin-top:auto}
.stale{color:var(--red)}
</style></head><body><div class="shell">
<div class="topbar">
  <div class="brand"><span class="logo">&#9670;</span><span class="bt">MEME ARENA</span></div>
  <nav class="nav" id="tabs"></nav>
  <span class="grow"></span>
  <span class="live"><span class="ld" id="livedot"></span><span id="livetxt">connecting&hellip;</span></span>
  <span class="sbit">SOL/USD <b class="num" id="solusd">&mdash;</b></span>
  <span class="sbit">feed <b id="feedstat">&mdash;</b></span>
  <span class="upd" id="updated">&mdash;</span>
</div>
<main id="page"><div class="empty">loading&hellip;</div></main>
<footer class="foot num" id="foot">memebot arena dashboard &middot; read-only evidence feeds and frozen ledgers &middot; no wallet / no orders &middot; 127.0.0.1:8795</footer>
</div>
<noscript><div class="empty">This dashboard needs JavaScript; it polls a small read-only JSON feed. Numbers are the arena runtime's own (runtime.report_arm + each arm's hash-chained ledger).</div></noscript>
<script>
"use strict";
var POLL_MS=2000,STATE=null,ACTIVE=null;
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function short(m){m=String(m||"");return m.length>13?m.slice(0,5)+"…"+m.slice(-4):m;}
function fmtUsd(v){if(v==null||isNaN(v))return "—";v=Number(v);var a=Math.abs(v);
  if(a>=1e9)return "$"+(v/1e9).toFixed(2)+"B";if(a>=1e6)return "$"+(v/1e6).toFixed(2)+"M";
  if(a>=1e3)return "$"+(v/1e3).toFixed(1)+"K";return "$"+v.toFixed(2);}
function fmtPrice(v){if(v==null||isNaN(v))return "—";v=Number(v);
  if(v===0)return "$0";if(Math.abs(v)>=1)return "$"+v.toFixed(4);return "$"+v.toPrecision(3);}
function fmtR(v){if(v==null||isNaN(v))return "—";v=Number(v);return (v>=0?"+":"")+v.toFixed(2)+"R";}
function fmtPct(v){if(v==null||isNaN(v))return "—";v=Number(v)*100;return (v>=0?"+":"")+v.toFixed(1)+"%";}
function fmtPctRaw(v){if(v==null||isNaN(v))return "—";return (Number(v)*100).toFixed(1)+"%";}
function fmtN(v,d){if(v==null||isNaN(v))return "—";return Number(v).toFixed(d==null?3:d);}
function fmtAge(min){if(min==null||isNaN(min))return "—";min=Number(min);
  if(min>=1440)return (min/1440).toFixed(1)+"d";if(min>=60)return (min/60).toFixed(1)+"h";
  if(min>=1)return min.toFixed(0)+"m";return Math.round(min*60)+"s";}
function fmtHolders(h,ex){if(h==null)return "—";return h+(ex?"":"+");}
function sgn(v){if(v==null||isNaN(v))return "muted";v=Number(v);return v>0?"pos":(v<0?"neg":"muted");}
function icon(sym,mint){
  var raw=(sym||mint||"?"),ch=(raw.replace(/[^A-Za-z0-9]/g,"")||"?").charAt(0).toUpperCase();
  var str=mint||sym||"x",h=0,i;for(i=0;i<str.length;i++){h=(h*31+str.charCodeAt(i))>>>0;}
  var hue=h%360;
  return '<span class="ic" style="background:hsl('+hue+',18%,20%);color:hsl('+hue+',34%,68%)">'+esc(ch)+'</span>';}

function cell(lbl,val,cls,sub){return '<div class="cell"><div class="lbl">'+lbl+'</div><div class="val '
  +(cls||"")+'">'+val+'</div><div class="sub">'+sub+'</div></div>';}
function strip(a){
  var s=a.stats||{};
  return '<div class="strip">'
    +cell("Capital index",s.capital_index==null?"—":s.capital_index.toFixed(2),
        s.capital_index==null?"muted":(s.capital_index>=100?"pos":"neg"),"normalized paper index")
    +cell("Mean all-cost R",s.mean_all==null?"—":((s.mean_all>=0?"+":"")+fmtN(s.mean_all,3)),sgn(s.mean_all),(s.n_resolved_all||0)+" fully reconciled")
    +cell("Win rate",s.win_rate==null?"—":fmtPctRaw(s.win_rate),"",(s.wins||0)+" wins · "+(s.losses||0)+" losses")
    +cell("Unexitable",s.unexitable==null?"—":s.unexitable,(s.unexitable>0?"neg":"muted"),"near-total losses")
    +cell("Max drawdown",s.max_drawdown==null?"—":fmtPctRaw(s.max_drawdown),(s.max_drawdown>0?"warn":"muted"),"normalized 100-index")
    +cell("Discovery",a.resolved+" / "+(a.target_n==null?"—":a.target_n),"","PRIMARY paper outcomes")
    +cell("Pending",a.pending==null?0:a.pending,(a.pending?"warn":""),a.pending?"awaiting causal fill":"no order waiting")
    +cell("Open",a.open,(a.open?"pos":""),"live filled positions")
    +cell("Seal",a.chain_ok?"ANCHORED":"BROKEN",a.chain_ok?"pos":"neg",esc(a.verdict))
    +'</div>';}

function chart(a){
  var vals=((a.stats&&a.stats.index_curve)||[]).map(Number).filter(isFinite);
  var data=vals.length?vals:[100],single=data.length<2;
  var w=920,h=250,L=58,R=18,T=18,B=34,iW=w-L-R,iH=h-T-B;
  var mn=Math.min(100,Math.min.apply(null,data)),mx=Math.max(100,Math.max.apply(null,data));
  var pad=Math.max(1,(mx-mn)*0.18);mn-=pad;mx+=pad;
  function Y(v){return T+(mx-v)/(mx-mn)*iH;}
  function X(i){return L+(single?0:i/(data.length-1)*iW);}
  var pts=single?(L+","+Y(data[0])+" "+(w-R)+","+Y(data[0])):data.map(function(v,i){return X(i)+","+Y(v);}).join(" ");
  var last=data[data.length-1],up=last>=100,cl=up?"up":"down",base=Y(100);
  var area=L+","+base+" "+pts+" "+(w-R)+","+base;
  var grid=[0,.25,.5,.75,1].map(function(f){var yy=T+f*iH,gv=mx-f*(mx-mn);
    return '<line x1="'+L+'" y1="'+yy+'" x2="'+(w-R)+'" y2="'+yy+'" class="gridline"/>'
      +'<text x="'+(L-9)+'" y="'+(yy+4)+'" text-anchor="end" class="axis">'+gv.toFixed(1)+'</text>';}).join("");
  var waitLabel=(a.verdict==="COLLECTING")?"COLLECTING · EQUITY MOVES ON ANCHORED RESOLUTIONS":"PERFORMANCE REFUSED BY EVIDENCE GATE";
  var wait=single?'<text x="'+(L+iW/2)+'" y="'+(T+iH/2)+'" text-anchor="middle" class="wait">'+esc(waitLabel)+'</text>':"";
  return '<svg viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none" role="img" aria-label="normalized performance index">'
    +grid+'<line x1="'+L+'" y1="'+base+'" x2="'+(w-R)+'" y2="'+base+'" class="baseline"/>'
    +'<polygon points="'+area+'" class="area '+cl+'"/><polyline points="'+pts+'" class="eline '+cl+'"/>'
    +'<circle cx="'+(single?w-R:X(data.length-1))+'" cy="'+Y(last)+'" r="4" class="epoint '+cl+'"/>'
    +'<text x="'+L+'" y="'+(h-10)+'" class="axis">start</text>'
    +'<text x="'+(w-R)+'" y="'+(h-10)+'" text-anchor="end" class="axis">'+Math.max(0,data.length-1)+' resolved</text>'
    +wait+'</svg>';}

function gate(state,label,val){return '<div class="gate"><span class="dot '+state+'"></span><span>'
  +label+'</span><strong>'+val+'</strong></div>';}
function ci(a){if(a.ci_lo==null)return "measuring";return "["+fmtN(a.ci_lo,3)+", "+fmtN(a.ci_hi,3)+"]";}
function side(a,s){
  var f=a.thesis||{},feedOk=s.trade_feed&&s.trade_feed.ok;
  var last=(a.stats&&a.stats.capital_index);
  var gates=gate(a.chain_ok?"ok":"bad","seal",a.chain_ok?"ANCHORED":"UNANCHORED")
    +gate(a.chain_ok?"ok":"bad","ledger chain",a.chain_ok?"verified":"BROKEN")
    +gate(s.sol_usd?"ok":"warn","SOL/USD",s.sol_usd?("fresh · $"+Number(s.sol_usd).toFixed(2)):"refused")
    +gate(feedOk?"ok":"bad","trade feed",feedOk?(s.trade_feed.status||"CONNECTED"):(s.trade_feed?s.trade_feed.status:"?"))
    +gate(a.distinct_mints?"ok":"warn","distinct mints",a.distinct_mints?"clean":"dup risk")
    +gate((a.n_clusters!=null&&a.n_clusters>0)?"ok":"warn","cluster CI",a.n_clusters!=null&&a.n_clusters>0?(a.n_clusters+" · "+ci(a)):"measuring")
    +gate("warn","promotion","MEASURING_NOT_A_PROFIT_CLAIM");
  return '<aside class="side">'
    +'<section class="panel"><div class="ptitle">Formula</div>'
    +'<div class="formula">'+esc(f.formula||a.basis||"")+'</div><div class="fnote">'+esc(f.note||"")+'</div></section>'
    +'<section class="panel"><div class="ptitle">Measurement gates</div><div class="gates">'+gates+'</div></section>'
    +'</aside>';}

function tok(mint,sym){
  var name=sym||short(mint);
  return '<div class="coin">'+icon(sym,mint)+'<div class="nm">'
    +'<span class="sym" data-mint="'+esc(mint||"")+'" title="'+esc(mint||"")+' (click to copy)">'+esc(name)+' <span class="cp">copy</span></span>'
    +'<div class="full num">'+esc(short(mint))+'</div></div></div>';}

function positions(a){
  var rows=a.open_positions||[];
  var head='<div class="pagehd"><h3>Live positions</h3>'
    +'<span class="pill"><b>'+rows.length+'</b> open · <b>'+(a.pending||0)+'</b> pending · basis <b>'+esc(a.basis)+'</b></span></div>';
  if(!rows.length)return head+'<div class="empty">no open positions right now — the arm opens only when a candidate clears every frozen gate</div>';
  var h='<div class="tablewrap"><table class="grid"><thead><tr><th class="l">Token</th><th class="l">Var</th>'
    +'<th>Entry</th><th>Price</th><th>P&amp;L %</th><th>R</th><th>MCap</th><th>Holders</th><th>Age</th><th class="l">Status</th></tr></thead><tbody>';
  rows.forEach(function(r){
    var pl=(r.live_price!=null&&r.entry_price)?(r.live_price/r.entry_price-1):null;
    h+='<tr><td class="l">'+tok(r.mint,r.symbol)+'</td>'
      +'<td class="l"><span class="vtag">'+esc(r.cohort||a.basis||"—")+'</span></td>'
      +'<td>'+fmtPrice(r.entry_price)+'</td><td>'+fmtPrice(r.live_price)+'</td>'
      +'<td class="'+sgn(pl)+'">'+fmtPct(pl)+'</td><td class="'+sgn(r.live_net_r)+'">'+fmtR(r.live_net_r)+'</td>'
      +'<td class="muted">'+fmtUsd(r.market_cap_usd)+'</td><td class="muted">'+fmtHolders(r.holders,r.holders_exact)+'</td>'
      +'<td class="muted">'+fmtAge(r.age_min)+'</td>'
      +'<td class="l"><span class="badge b-open">OPEN</span></td></tr>';
  });
  return head+h+'</tbody></table></div>';}

function scenario(a){
  var rows=a.resolved_recent||[],s=a.stats||{};
  var head='<div class="pagehd"><h3>Scenario activity</h3>'
    +'<span class="pill"><b>'+(a.pending||0)+'</b> pending · <b>'+a.open+'</b> open · <b>'+(s.n_resolved_all||a.resolved)+'</b> resolved · <b>'+(s.wins||0)+'</b> wins</span></div>';
  if(!rows.length)return head+'<div class="empty">no resolved forward trade yet — the index moves only on anchored, fully-costed resolutions</div>';
  var h='<div class="tablewrap"><table class="grid"><thead><tr><th class="l">Token</th><th class="l">State</th>'
    +'<th>All-cost R</th><th>P&amp;L %</th><th>Entry</th><th>Exit</th><th>Held</th><th class="l">Reason</th></tr></thead><tbody>';
  rows.forEach(function(r){
    var bc=(r.net_return!=null&&r.net_return<=-0.9)?"b-loss":(r.net_return>0?"b-open":"b-done");
    var bl=(r.net_return!=null&&r.net_return<=-0.9)?"RUG":(r.net_return>0?"WIN":"LOSS");
    h+='<tr><td class="l">'+tok(r.mint,r.symbol)+'</td>'
      +'<td class="l"><span class="badge '+bc+'">'+bl+'</span> <span class="vtag">'+esc(r.cohort||"—")+'</span></td>'
      +'<td class="'+sgn(r.net_return)+'">'+fmtR(r.net_return)+'</td><td class="'+sgn(r.net_return)+'">'+fmtPct(r.net_return)+'</td>'
      +'<td class="muted">'+fmtPrice(r.entry_price)+'</td><td class="muted">'+fmtPrice(r.exit_price)+'</td>'
      +'<td class="muted">'+fmtAge(r.held_min)+'</td>'
      +'<td class="l"><span class="rtag">'+esc(r.reason||"resolved")+'</span></td></tr>';
  });
  return head+h+'</tbody></table></div>';}

function renderTabs(s){
  var t=document.getElementById("tabs"),arms=s.arms||[];
  if(!ACTIVE||!arms.some(function(a){return a.instrument===ACTIVE;}))
    ACTIVE=decodeURIComponent(location.hash.slice(1))||(arms[0]&&arms[0].instrument)||null;
  t.innerHTML=arms.map(function(a){
    var c=a.color||"#8a93a0",on=a.instrument===ACTIVE?" on":"";
    return '<a class="navlink'+on+'" href="#'+encodeURIComponent(a.instrument)+'" data-arm="'+esc(a.instrument)+'">'
      +'<span class="nd" style="color:'+c+';background:'+c+'"></span>'+esc(a.instrument)
      +' <span class="nv" style="color:'+c+'">'+esc(a.verdict)+'</span></a>';}).join("");}

function renderPage(s){
  var arms=s.arms||[],a=null,i;
  for(i=0;i<arms.length;i++)if(arms[i].instrument===ACTIVE){a=arms[i];break;}
  if(!a)a=arms[0];
  var p=document.getElementById("page");
  if(!a){p.innerHTML='<div class="empty">no active arms</div>';return;}
  var last=(a.stats&&a.stats.capital_index);
  var lastCls=last==null?"muted":(last>=100?"pos":"neg");
  p.innerHTML=strip(a)
    +'<div class="layout"><section class="chartcard">'
    +'<div class="cardhead"><div><span class="eyebrow">PERFORMANCE</span><h3>Normalized discovery capital</h3></div>'
    +'<div class="last '+lastCls+'">'+(last==null?"—":last.toFixed(2))+'</div></div>'
    +'<div class="chart">'+chart(a)+'</div>'
    +'<div class="chartnote">'+esc(a.reason||"")+'</div></section>'
    +side(a,s)+'</div>'
    +positions(a)+scenario(a);}

function render(s){STATE=s;renderTabs(s);renderPage(s);
  document.getElementById("solusd").innerHTML=s.sol_usd==null?"—":("$"+Number(s.sol_usd).toFixed(2));
  var f=s.trade_feed||{},fs=document.getElementById("feedstat");
  fs.textContent=f.ok?(f.status||"connected"):(f.status||"down");fs.className=f.ok?"pos":"neg";
  document.getElementById("updated").textContent="updated "+esc((s.generated_utc||"").replace("T"," ").replace("Z"," UTC"));}

var failCount=0;
function setLive(ok){var d=document.getElementById("livedot"),t=document.getElementById("livetxt");
  if(ok){d.className="ld on";t.textContent="live";t.className="";}
  else{d.className="ld err";t.textContent="reconnecting";t.className="stale";}}
function poll(){fetch("/api/state",{cache:"no-store"}).then(function(r){
    if(!r.ok)throw 0;return r.json();}).then(function(s){failCount=0;setLive(true);render(s);})
  .catch(function(){failCount++;if(failCount>=2)setLive(false);});}

window.addEventListener("hashchange",function(){var h=decodeURIComponent(location.hash.slice(1));
  if(h){ACTIVE=h;if(STATE)render(STATE);}});
document.addEventListener("click",function(e){
  var nm=e.target.closest?e.target.closest(".sym"):null;if(!nm)return;
  var m=nm.getAttribute("data-mint");if(!m)return;
  var cp=nm.querySelector(".cp"),o=cp?cp.textContent:"";
  var done=function(){if(cp){cp.textContent="copied";cp.style.color="var(--mint)";
    setTimeout(function(){cp.textContent=o;cp.style.color="";},1100);}};
  if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(m).then(done,done);
  else{try{var ta=document.createElement("textarea");ta.value=m;document.body.appendChild(ta);ta.select();
    document.execCommand("copy");document.body.removeChild(ta);done();}catch(x){}}});
poll();setInterval(poll,POLL_MS);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def do_GET(self):  # noqa: N802
        route = self.path.split("?", 1)[0].rstrip("/")
        if route in ("", "/index.html"):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif route == "/api/state":
            try:
                body = json.dumps(state_view()).encode()
            except Exception as exc:  # noqa: BLE001 -- never 500 the poll; report the error honestly
                body = json.dumps({"error": str(exc)[:200],
                                   "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                   "arms": []}).encode()
            self._send(200, body, "application/json")
        elif route == "/api/health":
            self._send(200, json.dumps({"ok": True, "helius": bool(_HELIUS_URL)}).encode(),
                       "application/json")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, *a):  # silence default request logging
        pass


def main() -> int:
    threading.Thread(target=_enrich_worker, daemon=True).start()
    print(f"MEME ARENA dashboard: http://{HOST}:{PORT}  (Helius: {'on' if _HELIUS_URL else 'off'})",
          flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
