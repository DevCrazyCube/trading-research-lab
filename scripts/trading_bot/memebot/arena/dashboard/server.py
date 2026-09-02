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
    }


_state_cache = {"exp": 0.0, "val": None}
_state_lock = threading.Lock()


def _build_state() -> dict:
    sol_usd, sol_src = _sol_usd()
    arms = [_arm_view(a) for a in _display_arms()]
    return {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generated_unix": time.time(),
        "helius": bool(_HELIUS_URL),
        "sol_usd": sol_usd,
        "sol_usd_source": sol_src,
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
:root{--bg:#f5f6f8;--card:#ffffff;--ink:#151922;--sub:#5b626c;--faint:#8a919b;--line:#e6e8ec;
--chip:#eef0f4;--pos:#1a9e5f;--neg:#d0453b;--accent:#5b6bd6;--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
@media(prefers-color-scheme:dark){:root{--bg:#0e1116;--card:#161b22;--ink:#e8eaed;--sub:#9aa2ad;
--faint:#6b7280;--line:#232a33;--chip:#1e2530;--pos:#3fca86;--neg:#e8695f;--accent:#7c8cf0}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:13.5px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:22px 18px 70px}
.top{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:6px}
.top h1{font-size:19px;margin:0;letter-spacing:-.3px}
.top .tag{font-size:11.5px;color:var(--sub)}
.bar{display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:11.5px;color:var(--sub);
margin:2px 0 18px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.bar b{color:var(--ink);font-variant-numeric:tabular-nums}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px;vertical-align:1px}
.grid{display:grid;grid-template-columns:1fr;gap:16px}
@media(min-width:840px){.grid{grid-template-columns:1fr 1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 16px 8px;
display:flex;flex-direction:column;min-width:0}
.chead{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:12px}
.chead h2{font-size:14.5px;margin:0 0 3px;letter-spacing:-.2px;word-break:break-word}
.basis{font-size:11px;color:var(--sub)}
.verdict{color:#fff;font-weight:700;font-size:11px;letter-spacing:.04em;padding:5px 11px;border-radius:8px;
white-space:nowrap;flex:none}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:8px 18px;margin-bottom:8px}
.metrics .k{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--sub)}
.metrics .val{font-size:15.5px;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.2px}
.pos{color:var(--pos)}.neg{color:var(--neg)}.muted{color:var(--faint)}
.eqwrap{margin:6px 0 4px}
svg.eq{width:100%;height:118px;display:block}
.zero{stroke:var(--line);stroke-width:1;stroke-dasharray:3 3}
.eqlab{font-size:10.5px;font-weight:600;font-variant-numeric:tabular-nums}
.eqempty{font-size:11px;color:var(--faint);text-align:center;padding:34px 0}
.reason{font-size:11.5px;color:var(--sub);margin:4px 0 10px;min-height:1px}
.sect{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);
margin:8px 0 4px;display:flex;justify-content:space-between}
.tbl{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:11.5px;font-variant-numeric:tabular-nums}
th{text-align:right;color:var(--faint);font-weight:500;font-size:9.5px;text-transform:uppercase;
letter-spacing:.04em;padding:4px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
th.l,td.l{text-align:left}
td{padding:4px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
tr:last-child td{border-bottom:none}
.mint{font-family:var(--mono);cursor:pointer;background:none;border:none;color:var(--ink);
font-size:11px;padding:2px 5px;border-radius:6px;display:inline-flex;align-items:center;gap:5px}
.mint:hover{background:var(--chip)}
.mint .cp{color:var(--faint);font-size:10px}
.mint.copied .cp{color:var(--pos)}
.sym{color:var(--sub);font-size:10.5px;margin-left:4px}
.src{color:var(--faint);font-size:9px;margin-left:3px}
.badge{font-size:9.5px;padding:1px 6px;border-radius:5px;background:var(--chip);color:var(--sub)}
.empty{color:var(--faint);text-align:center;padding:10px 0;font-size:11px}
.reasontag{font-size:9.5px;padding:1px 6px;border-radius:5px;background:var(--chip);color:var(--sub)}
.foot{margin-top:22px;font-size:11px;color:var(--faint);line-height:1.6}
.stale{color:var(--neg)}
</style></head><body><div class="wrap">
<div class="top"><h1>&#127967;&#65039; MEME ARENA</h1>
<span class="tag">frozen multi-arm forward test &middot; honest fills &middot; hash-chained ledgers &middot; paper only</span></div>
<div class="bar" id="statusbar">
  <span><span class="dot" id="livedot" style="background:var(--faint)"></span><span id="livetxt">connecting&hellip;</span></span>
  <span>SOL/USD <b id="solusd">&mdash;</b></span>
  <span>Helius <b id="heliusstat">&mdash;</b></span>
  <span id="updated" class="muted">&mdash;</span>
</div>
<div class="grid" id="cards"></div>
<noscript><p class="foot">This dashboard streams via a small JSON poll; please enable JavaScript. The
underlying numbers are the arena runtime's own (<code>runtime.report_arm</code> + each arm's
hash-chained ledger).</p></noscript>
<div class="foot" id="note"></div>
</div>
<script>
"use strict";
var POLL_MS = 2000;
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function short(m){m=String(m||"");return m.length>13?m.slice(0,6)+"…"+m.slice(-4):m;}
function fmtUsd(v){
  if(v==null||isNaN(v))return "—";
  v=Number(v);
  if(v>=1e9)return "$"+(v/1e9).toFixed(2)+"B";
  if(v>=1e6)return "$"+(v/1e6).toFixed(2)+"M";
  if(v>=1e3)return "$"+(v/1e3).toFixed(1)+"K";
  return "$"+v.toFixed(2);
}
function fmtPrice(v){
  if(v==null||isNaN(v))return "—";
  v=Number(v);
  if(v===0)return "0";
  if(v>=1)return "$"+v.toFixed(4);
  return "$"+v.toPrecision(3);
}
function fmtR(v){if(v==null||isNaN(v))return "—";v=Number(v);return (v>=0?"+":"")+v.toFixed(3)+"R";}
function fmtNum(v,d){if(v==null||isNaN(v))return "—";return Number(v).toFixed(d==null?4:d);}
function fmtMin(v){if(v==null||isNaN(v))return "—";v=Number(v);
  if(v>=60)return (v/60).toFixed(1)+"h";return v.toFixed(0)+"m";}
function fmtHolders(h,exact){if(h==null)return "—";return h+(exact?"":"+");}
function cls(v){if(v==null||isNaN(v))return "muted";return Number(v)>=0?"pos":"neg";}
function srcTag(s){return s?'<span class="src">&middot; '+esc(s)+'</span>':"";}

function equitySvg(eq){
  if(!eq||eq.length<2)return '<div class="eqempty">equity curve appears after 2 resolved trades</div>';
  var W=520,H=118,P=26,vals=eq.map(function(p){return p.cum;});
  var lo=Math.min.apply(null,vals.concat([0])),hi=Math.max.apply(null,vals.concat([0]));
  var rng=(hi-lo)||1;
  function X(i){return P+i/(eq.length-1)*(W-2*P);}
  function Y(v){return H-P-(v-lo)/rng*(H-2*P);}
  var pts=eq.map(function(p,i){return X(i).toFixed(1)+","+Y(p.cum).toFixed(1);}).join(" ");
  var last=vals[vals.length-1],z=Y(0).toFixed(1);
  var col=last>=0?"var(--pos)":"var(--neg)";
  var area="M"+X(0).toFixed(1)+","+z+" L"+pts.replace(/ /g," L")+" L"+X(eq.length-1).toFixed(1)+","+z+" Z";
  return '<svg class="eq" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">'
    +'<path d="'+area+'" fill="'+col+'" opacity="0.10"/>'
    +'<line x1="'+P+'" y1="'+z+'" x2="'+(W-P)+'" y2="'+z+'" class="zero"/>'
    +'<polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="2"'
    +' stroke-linejoin="round" stroke-linecap="round"/>'
    +'<text x="'+(W-P)+'" y="'+(Y(last)-6).toFixed(1)+'" text-anchor="end" class="eqlab" fill="'+col+'">'
    +(last>=0?"+":"")+last.toFixed(3)+'R</text></svg>';
}

function mintCell(m,sym){
  if(!m)return '<span class="muted">—</span>';
  return '<button class="mint" data-mint="'+esc(m)+'" title="'+esc(m)+' (click to copy)">'
    +esc(short(m))+'<span class="cp">copy</span></button>'
    +(sym?'<span class="sym">'+esc(sym)+'</span>':"");
}

function openTable(rows){
  if(!rows||!rows.length)return '<div class="empty">no open positions</div>';
  var h='<div class="tbl"><table><thead><tr>'
    +'<th class="l">mint</th><th>mcap</th><th>holders</th><th>price</th>'
    +'<th>entry</th><th>peak</th><th>age</th><th>net-R</th></tr></thead><tbody>';
  rows.forEach(function(r){
    h+='<tr><td class="l">'+mintCell(r.mint,r.symbol)+srcTag(r.price_source)
      +(r.cohort?' <span class="badge">'+esc(r.cohort)+'</span>':"")+'</td>'
      +'<td>'+fmtUsd(r.market_cap_usd)+'</td>'
      +'<td>'+fmtHolders(r.holders,r.holders_exact)+'</td>'
      +'<td>'+fmtPrice(r.live_price)+'</td>'
      +'<td>'+fmtPrice(r.entry_price)+'</td>'
      +'<td>'+fmtPrice(r.peak)+'</td>'
      +'<td>'+fmtMin(r.age_min)+'</td>'
      +'<td class="'+cls(r.live_net_r)+'">'+(r.live_net_r==null?"—":fmtR(r.live_net_r))+'</td></tr>';
  });
  return h+'</tbody></table></div>';
}

function resolvedTable(rows){
  if(!rows||!rows.length)return '<div class="empty">no resolved trades yet</div>';
  var h='<div class="tbl"><table><thead><tr>'
    +'<th class="l">mint</th><th class="l">reason</th><th>mcap</th><th>price</th>'
    +'<th>entry</th><th>exit</th><th>held</th><th>net-R</th></tr></thead><tbody>';
  rows.forEach(function(r){
    h+='<tr><td class="l">'+mintCell(r.mint,r.symbol)+srcTag(r.price_source)+'</td>'
      +'<td class="l"><span class="reasontag">'+esc(r.reason||"?")+'</span></td>'
      +'<td>'+fmtUsd(r.market_cap_usd)+'</td>'
      +'<td>'+fmtPrice(r.live_price)+'</td>'
      +'<td>'+fmtPrice(r.entry_price)+'</td>'
      +'<td>'+fmtPrice(r.exit_price)+'</td>'
      +'<td>'+fmtMin(r.held_min)+'</td>'
      +'<td class="'+cls(r.net_return)+'">'+fmtR(r.net_return)+'</td></tr>';
  });
  return h+'</tbody></table></div>';
}

function ciStr(a){
  if(a.ci_lo==null)return "—";
  return "["+fmtNum(a.ci_lo,3)+", "+fmtNum(a.ci_hi,3)+"]";
}

function card(a){
  var chain=a.chain_ok?'&#10003; chain':'&#10007; CHAIN BROKEN';
  var extra="";
  if(a.control_mean!=null)extra=' &middot; control '+fmtNum(a.control_mean,3)+' (n='+(a.control_n||0)+')';
  var clu=(a.n_clusters!=null?(' &middot; '+a.n_clusters+' clusters'):"");
  return '<section class="card" data-arm="'+esc(a.instrument)+'">'
    +'<div class="chead"><div><h2>'+esc(a.instrument)+'</h2>'
    +'<span class="basis">'+esc(a.basis)+' fill &middot; '+chain+extra+'</span></div>'
    +'<div class="verdict" style="background:'+a.color+'">'+esc(a.verdict)+'</div></div>'
    +'<div class="metrics">'
    +'<div><span class="k">resolved</span><span class="val">'+a.resolved+' / '+(a.target_n==null?"—":a.target_n)+'</span></div>'
    +'<div><span class="k">open</span><span class="val">'+a.open+'</span></div>'
    +'<div><span class="k">mean net-R</span><span class="val '+cls(a.mean)+'">'+(a.mean==null?"—":fmtNum(a.mean,4))+'</span></div>'
    +'<div><span class="k">bootstrap CI (mint+day)</span><span class="val">'+ciStr(a)+'</span></div>'
    +'</div>'
    +'<div class="eqwrap">'+equitySvg(a.equity)+'</div>'
    +'<div class="reason">'+esc(a.reason||"")+clu+'</div>'
    +'<div class="sect"><span>open positions</span><span>'+a.open+'</span></div>'
    +openTable(a.open_positions)
    +'<div class="sect"><span>recent resolved</span><span>'+a.resolved+' total</span></div>'
    +resolvedTable(a.resolved_recent)
    +'</section>';
}

function render(s){
  var c=document.getElementById("cards");
  c.innerHTML=(s.arms||[]).map(card).join("");
  document.getElementById("solusd").innerHTML=s.sol_usd==null?"—":("$"+Number(s.sol_usd).toFixed(2)
    +(s.sol_usd_source?' <span class="src">'+esc(s.sol_usd_source)+'</span>':""));
  document.getElementById("heliusstat").textContent=s.helius?"live":"key absent";
  document.getElementById("updated").textContent="updated "+esc(s.generated_utc||"");
  document.getElementById("note").textContent=s.note||"";
}

var failCount=0;
function setLive(ok){
  var d=document.getElementById("livedot"),t=document.getElementById("livetxt");
  if(ok){d.style.background="var(--pos)";t.textContent="live";t.className="";}
  else{d.style.background="var(--neg)";t.textContent="reconnecting (showing last data)";t.className="stale";}
}
function poll(){
  fetch("/api/state",{cache:"no-store"}).then(function(r){
    if(!r.ok)throw new Error(r.status);return r.json();
  }).then(function(s){failCount=0;setLive(true);render(s);}).catch(function(){
    failCount++;if(failCount>=2)setLive(false);
  });
}

document.addEventListener("click",function(e){
  var b=e.target.closest?e.target.closest(".mint"):null;
  if(!b)return;
  var m=b.getAttribute("data-mint");
  var done=function(){var cp=b.querySelector(".cp");if(cp){var o=cp.textContent;cp.textContent="copied";
    b.classList.add("copied");setTimeout(function(){cp.textContent=o;b.classList.remove("copied");},1100);}};
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(m).then(done,done);}
  else{try{var ta=document.createElement("textarea");ta.value=m;document.body.appendChild(ta);ta.select();
    document.execCommand("copy");document.body.removeChild(ta);done();}catch(x){}}
});

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
