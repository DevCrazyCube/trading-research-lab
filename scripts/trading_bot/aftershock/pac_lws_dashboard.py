#!/usr/bin/env python3
"""
AFTERSHOCK · PAC / LWS — "Quiet Desk" live paper-trade dashboard.

A single self-contained http.server (Python standard library ONLY) that serves
one calm, focused trading view at http://127.0.0.1:8793/ :

  1. a stat strip (6 tiles),
  2. ONE hero graph  — the cumulative net-SOL equity curve, LWS vs NULL,
  3. ONE live tape   — the newest buys/sells from the feed.

It reads five LOCAL files (no network, no auth) and computes the curve / tiles /
tape server-side, returning one JSON blob to a ~2s client poll:

  research/trading_bot/aftershock/AFTERSHOCK_PAC_LWS_SCENARIO_LEDGER.jsonl
  research/trading_bot/aftershock/AFTERSHOCK_PAC_LWS_NULL_SCENARIO_LEDGER.jsonl
  research/data/aftershock/pac_lws/feed_events.jsonl
  research/data/aftershock/pac_lws/creation_registry.jsonl
  research/data/aftershock/pac_lws/feed_health.json

The two scenario ledgers MAY NOT EXIST YET or be EMPTY (the runner is being
built in parallel). Every read is guarded: a missing/empty ledger yields empty
arrays and zeroed / "—" tiles, and the page renders the honest empty state
("Awaiting first resolved trade") instead of crashing.

Run:
    python3 scripts/trading_bot/aftershock/pac_lws_dashboard.py
    # then open http://127.0.0.1:8793/
"""

from __future__ import annotations

import json
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths — resolve the repo root from this file's location so the dashboard can
# be launched from anywhere. scripts/trading_bot/aftershock/<this> -> parents[3]
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[3]

LEDGER_LWS = ROOT / "research/trading_bot/aftershock/AFTERSHOCK_PAC_LWS_SCENARIO_LEDGER.jsonl"
LEDGER_NULL = ROOT / "research/trading_bot/aftershock/AFTERSHOCK_PAC_LWS_NULL_SCENARIO_LEDGER.jsonl"
FEED_EVENTS = ROOT / "research/data/aftershock/pac_lws/feed_events.jsonl"
CREATION_REGISTRY = ROOT / "research/data/aftershock/pac_lws/creation_registry.jsonl"
FEED_HEALTH = ROOT / "research/data/aftershock/pac_lws/feed_health.json"
ELIGIBILITY = ROOT / "research/data/aftershock/pac_lws/eligibility_v2.jsonl"
ELIGIBILITY_HEALTH = ROOT / "research/data/aftershock/pac_lws/eligibility_v2_health.json"
ELIGIBILITY_SUSPENSION = ROOT / "research/trading_bot/aftershock/AFTERSHOCK_PAC_LWS_ELIGIBILITY_V2_SUSPENSION.json"

HOST = "127.0.0.1"   # localhost only — never bind 0.0.0.0
PORT = 8793

LAMPORTS_PER_SOL = 1_000_000_000
TAPE_ROWS = 48       # newest feed rows sent to the client (not a firehose)
MINT_ROWS = 16       # most-recently-active mints shown in the mint list
MINT_SCAN = 3500     # feed rows scanned (tail) to aggregate the mint list

import time as _time

from . import pac_lws_feed as _feed
import threading as _threading
_TTL_CACHE: dict = {}
_TTL_LOCK = _threading.Lock()


def _ttl(key: str, ttl: float, fn):
    """Recompute fn() at most once per `ttl` seconds — keeps the ~2s poll snappy for the slow
    whole-feed scans (coverage, feed_count) that change only slowly, while the tail-based equity/
    tape/mints stay live every poll."""
    now = _time.time()
    hit = _TTL_CACHE.get(key)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]
    with _TTL_LOCK:
        hit = _TTL_CACHE.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
        val = fn()
        _TTL_CACHE[key] = (now, val)
        return val

# pump.fun bonding-curve market-cap constants (pinned; match scripts/.../ecr.py + runner reconstruction)
_VTOK_OFFSET = 279_900_000_000_000       # virtual_token = real_token + this
_CURVE_K = 30_000_000_000 * 1_073_000_000_000_000   # constant product from the initial virtual reserves
_TOTAL_SUPPLY_ATOMS = 1_000_000_000_000_000          # 1e9 tokens * 1e6 decimals


def _market_cap_sol(real_token) -> float:
    """pump.fun market cap in SOL from the token-side reserve: price(SOL/atom) * total supply.
    price = virtual_quote / virtual_token, virtual_token = real_token + offset, virtual_quote = K/vtok.
    A fresh curve (~793.1e12 real_token) returns ~28 SOL, exactly as the curve implies. 0 if unusable."""
    try:
        rt = int(real_token)
        if rt <= 0:
            return 0.0
        vtok = rt + _VTOK_OFFSET
        vq = _CURVE_K // vtok
        return (vq / vtok) * _TOTAL_SUPPLY_ATOMS / LAMPORTS_PER_SOL
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0

# --------------------------------------------------------------------------- #
# Tiny stat-keyed cache so a growing file is not fully re-parsed every poll.
# Keyed on (size, mtime_ns); recomputed only when the file actually changes.
# --------------------------------------------------------------------------- #
_CACHE: dict[str, tuple] = {}


def _cached(path: Path, builder):
    """Return builder(path) memoized on the file's (size, mtime). Guarded."""
    try:
        st = path.stat()
        key = (st.st_size, st.st_mtime_ns)
    except OSError:
        return builder(None)  # missing file -> let builder return its empty shape
    prev = _CACHE.get(str(path))
    if prev is not None and prev[0] == key:
        return prev[1]
    value = builder(path)
    _CACHE[str(path)] = (key, value)
    return value


def _iter_json_lines(path: Path):
    """Yield parsed JSON objects from a .jsonl file; skip blanks/garbage."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except (ValueError, TypeError):
                    continue
    except OSError:
        return


def _tail_lines(path: Path, n: int) -> list[str]:
    """Return the last n non-empty lines of a file, cheaply, via a backward seek."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            end = fh.tell()
            block = 65536
            pos = end
            data = b""
            # read backward until we have more than n newlines, or hit the start
            while pos > 0 and data.count(b"\n") <= n:
                step = min(block, pos)
                pos -= step
                fh.seek(pos)
                data = fh.read(step) + data
            lines = [ln for ln in data.split(b"\n") if ln.strip()]
            return [ln.decode("utf-8", "replace") for ln in lines[-n:]]
    except OSError:
        return []


def _count_lines(path: Path) -> int:
    """Fast newline count over a file; 0 if missing/unreadable."""
    def build(p):
        if p is None:
            return 0
        try:
            total = 0
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    total += chunk.count(b"\n")
            return total
        except OSError:
            return 0
    return _cached(path, build)


# --------------------------------------------------------------------------- #
# Ledger reduction — one pass -> the equity curve points + funnel counts.
# --------------------------------------------------------------------------- #
def _read_ledger(path: Path) -> dict:
    """
    Reduce one scenario ledger to everything the dashboard needs.

    Returns:
        points:      [{"t": <sec>, "net": <cumulative net SOL>}, ...] over resolved rows
        net_sol:     final cumulative net SOL (0.0 if none)
        resolved:    count of kind=="resolved"
        filled:      count of kind=="entry_filled"
        decisions:   count of kind=="entry_decision"
        vetoed:      count of kind in {entry_vetoed, entry_rejected}
        unexitable:  count of resolved rows with unexitable_full_loss==True
    """
    def build(p):
        empty = {
            "points": [], "net_sol": 0.0, "resolved": 0, "filled": 0,
            "decisions": 0, "vetoed": 0, "unexitable": 0,
        }
        if p is None:
            return empty
        resolved_rows = []
        filled = decisions = vetoed = unexitable = 0
        for obj in _iter_json_lines(p):
            kind = obj.get("kind")
            if kind == "resolved":
                ts = obj.get("resolved_unix_nanos")
                num = obj.get("net_return_num")
                if ts is None or num is None:
                    continue
                resolved_rows.append((ts, num, bool(obj.get("unexitable_full_loss"))))
            elif kind == "entry_filled":
                filled += 1
            elif kind == "entry_decision":
                decisions += 1
            elif kind == "entry_vetoed":
                vetoed += 1

        resolved_rows.sort(key=lambda r: r[0])
        points = []
        running = 0
        for ts, num, unex in resolved_rows:
            running += num
            if unex:
                unexitable += 1
            points.append({"t": ts / 1e9, "net": running / LAMPORTS_PER_SOL})

        return {
            "points": points,
            "net_sol": (running / LAMPORTS_PER_SOL) if resolved_rows else 0.0,
            "resolved": len(resolved_rows),
            "filled": filled,
            "decisions": decisions,
            "vetoed": vetoed,
            "unexitable": unexitable,
        }
    return _cached(path, build)


def _read_coverage(registry_path: Path, feed_path: Path) -> tuple[int, int]:
    """(reconciled distinct mints, total created distinct mints). The `reconciled` flag lives on the
    FEED events (a mint's first trade reconciled to its seeded t0 state), not on the registry — so
    coverage = distinct mints with a reconciled trade / distinct created mints. (0, 0) if missing."""
    creates = set()
    for obj in _iter_json_lines(registry_path):
        m = obj.get("mint")
        if m:
            creates.add(m)
    recon = set()
    for obj in _iter_json_lines(feed_path):
        if obj.get("reconciled") is True:
            m = obj.get("mint")
            if m:
                recon.add(m)
    return (len(recon & creates), len(creates))


def _tail_feed_count(path: Path) -> int:
    """The hash-chained feed carries a monotonic seq; do not rescan a multi-GB file in HTTP."""
    lines = _tail_lines(path, 2)
    for line in reversed(lines):
        try:
            seq = json.loads(line).get("seq")
        except (ValueError, TypeError):
            continue
        if isinstance(seq, int) and seq >= 0:
            return seq + 1
    return 0


def _read_eligibility(path: Path) -> dict:
    def build(candidate):
        total = base = veto = unreadable = 0; previous = "0" * 64; valid = True
        if candidate is not None:
            try:
                with candidate.open() as handle:
                    for line in handle:
                        if not line.strip(): continue
                        row = json.loads(line); body = dict(row); observed = body.pop("record_hash", None)
                        expected = hashlib.sha256(json.dumps(
                            body, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True).encode()).hexdigest()
                        if (body.get("previous_record_hash") != previous or observed != expected):
                            raise ValueError("eligibility chain mismatch")
                        previous = observed; total += 1
                        base += int(row.get("base_eligible") is True)
                        veto += int(row.get("veto_eligible") is True)
                        unreadable += int(row.get("filter") in ("UNREADABLE", "NO_NET_TOKENS"))
            except (OSError, ValueError, TypeError):
                valid = False; total = base = veto = unreadable = 0
        status = "SUSPENDED_AUTHORITY_INCOMPLETE" if ELIGIBILITY_SUSPENSION.exists() else "ACTIVE"
        return {"total": total, "base": base, "veto": veto,
                "unreadable": unreadable, "valid": valid, "status": status}
    return _cached(path, build)


def _read_tape(path: Path) -> list[dict]:
    """Newest-first list of the last TAPE_ROWS feed events (lean projection)."""
    rows = []
    for line in _tail_lines(path, TAPE_ROWS):
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        ts = obj.get("received_unix_nanos")
        rows.append({
            "is_buy": bool(obj.get("is_buy")),
            "sol": (obj.get("sol_amount") or 0) / LAMPORTS_PER_SOL,
            "mint": obj.get("mint") or "",
            "slot": obj.get("slot"),
            "t": (ts / 1e9) if ts else None,
            "anchored": bool(obj.get("anchored")),
            "reconciled": obj.get("reconciled") is True,
        })
    rows.reverse()  # newest on top
    return rows


def _read_bot_mints(ledger_path: Path) -> tuple[set, set]:
    """Which mints the bot actually acted on: (entered, vetoed). Lets the mint list show the bot's
    own footprint — a green 'BOUGHT' or a muted 'VETOED' tag next to the launches it decided on."""
    entered, vetoed = set(), set()
    for obj in _iter_json_lines(ledger_path):
        m = obj.get("mint")
        if not m:
            continue
        kind = obj.get("kind")
        if kind in ("entry_filled", "entry_decision"):
            entered.add(m)
        elif kind == "entry_vetoed":
            vetoed.add(m)
    return entered, vetoed


def _read_mints(path: Path, entered: set = frozenset(), vetoed: set = frozenset()) -> list[dict]:
    """Per-mint rollup over the feed tail: distinct buyers, buy/sell counts, and the live market cap
    from the latest token reserve. Most-recently-active first. The owner's requested mint list —
    tagged with whether the bot bought or vetoed each launch."""
    agg: dict = {}
    for line in _tail_lines(path, MINT_SCAN):
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        mint = obj.get("mint")
        if not mint:
            continue
        m = agg.get(mint)
        if m is None:
            m = agg[mint] = {"mint": mint, "buyers": set(), "buys": 0, "sells": 0,
                             "last_rt": None, "last_ns": None, "anchored": False}
        is_buy = bool(obj.get("is_buy"))
        if is_buy:
            m["buys"] += 1
            trader = obj.get("trader")
            if trader:
                m["buyers"].add(trader)
        else:
            m["sells"] += 1
        rt = obj.get("post_real_token")
        if isinstance(rt, int):
            m["last_rt"] = rt
        ns = obj.get("received_unix_nanos")
        if ns and (m["last_ns"] is None or ns > m["last_ns"]):
            m["last_ns"] = ns
        if obj.get("anchored"):
            m["anchored"] = True
    rows = []
    for m in agg.values():
        mint = m["mint"]
        rows.append({
            "mint": mint,
            "buyers": len(m["buyers"]),
            "buys": m["buys"],
            "sells": m["sells"],
            "trades": m["buys"] + m["sells"],
            "mcap_sol": round(_market_cap_sol(m["last_rt"]), 1) if m["last_rt"] else 0.0,
            "t": (m["last_ns"] / 1e9) if m["last_ns"] else None,
            "anchored": m["anchored"],
            "bot": "bought" if mint in entered else ("vetoed" if mint in vetoed else None),
        })
    rows.sort(key=lambda r: (r["t"] or 0), reverse=True)   # most-recently-active first
    return rows[:MINT_ROWS]


def _read_health() -> dict:
    """Project the feed's authenticated health contract; forged/future rows never render green."""
    try:
        obj = _feed.load_health(FEED_HEALTH, now=_time.time_ns(), require_fresh=False)
    except Exception:  # read-only presentation: invalid authority degrades visibly
        present = FEED_HEALTH.exists()
        return {"present": present, "status": "INVALID" if present else "STALE", "lag": None,
                "observed_sec": None, "instrument_id": None}
    try:
        _feed.load_health(FEED_HEALTH, now=_time.time_ns(), require_fresh=True)
        status = "FRESH"
    except Exception:
        status = "STALE" if obj.get("status") == "FRESH" else obj.get("status", "DEGRADED")
    if not isinstance(obj, dict):
        return {"present": False, "status": "STALE", "lag": None,
                "observed_sec": None, "instrument_id": None}
    obs = obj.get("observed_unix_nanos")
    observed_sec = (obs / 1e9) if type(obs) is int else None
    return {
        "present": True,
        "status": status,
        "lag": obj.get("head_slot_lag"),
        "observed_sec": observed_sec,
        "instrument_id": obj.get("instrument_id"),
    }


# --------------------------------------------------------------------------- #
# /api/state — assemble the single JSON blob for the client poll.
# --------------------------------------------------------------------------- #
def build_state() -> dict:
    lws = _read_ledger(LEDGER_LWS)
    null = _read_ledger(LEDGER_NULL)
    # Never scan the multi-GB feed from an HTTP request. Eligibility is a small incremental ledger;
    # feed volume comes from the tail's monotonic seq.
    eligibility = _read_eligibility(ELIGIBILITY)
    tape = _read_tape(FEED_EVENTS)
    feed_count = _tail_feed_count(FEED_EVENTS)
    health = _read_health()
    if not eligibility["valid"]:
        health = {**health, "status": "DEGRADED"}

    open_book = max(lws["filled"] - lws["resolved"], 0)
    # veto rate = B20B vetoes / (vetoes + admitted decisions); entry_rejected (coverage floor) is not a veto
    veto_attempts = lws["vetoed"] + lws["decisions"]
    veto_rate = (lws["vetoed"] / veto_attempts * 100.0) if veto_attempts else None
    coverage = (eligibility["veto"] / eligibility["total"] * 100.0
                if eligibility["total"] else None)
    unex_pct = (lws["unexitable"] / lws["resolved"] * 100.0) if lws["resolved"] else 0.0

    # The PRIMARY arm = whichever is actually trading, so the hero number/line is never confusingly
    # blank while a live arm quietly works. Prefer the veto arm (LWS); fall back to the control (NULL).
    lws_live = lws["resolved"] > 0 or lws["filled"] > 0
    null_live = null["resolved"] > 0 or null["filled"] > 0
    if lws_live or not null_live:
        prim, other = lws, null
        prim_label, other_label = "veto arm", "control"
    else:
        prim, other = null, lws
        prim_label, other_label = "control arm", "veto"
    prim_open = max(prim["filled"] - prim["resolved"], 0)
    prim_unex_pct = (prim["unexitable"] / prim["resolved"] * 100.0) if prim["resolved"] else 0.0

    tiles = {
        "net_sol": prim["net_sol"],                 # the LIVE book — the hero number
        "primary_label": prim_label,
        "other_label": other_label,
        "net_sol_other": other["net_sol"],
        "vs_other": prim["net_sol"] - other["net_sol"],
        "resolved": prim["resolved"],
        "open": prim_open,
        "unexitable": prim["unexitable"],
        "unexitable_pct": prim_unex_pct,
        "veto_rate": veto_rate,                     # veto is an LWS property; None until the veto arm decides
        "veto_v": lws["vetoed"],
        "veto_d": veto_attempts,
        "coverage": coverage,
        "coverage_r": eligibility["veto"],
        "coverage_c": eligibility["total"],
    }

    return {
        "equity_primary": prim["points"],
        "equity_secondary": other["points"],
        "primary_label": prim_label,
        "other_label": other_label,
        "tape": tape,
        "mints": _ttl("mints", 3.0, lambda: _read_mints(FEED_EVENTS, *_read_bot_mints(LEDGER_LWS))),
        "feed_count": feed_count,
        "tiles": tiles,
        "health": health,
        "eligibility": eligibility,
    }


# --------------------------------------------------------------------------- #
# The single static page — Quiet Desk. Inline HTML + CSS + JS, no build step,
# no external chart lib (inline SVG), no external network.
# --------------------------------------------------------------------------- #
PAGE = r"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AFTERSHOCK · PAC / LWS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{
    --ground:#0E1116; --panel:#161A21; --panel-2:#1B2028; --hair:#242A33; --hair-lit:#3A434F;
    --muted:#7E8794; --muted-2:#9AA3AF; --ink:#EAEDF2;
    --amber:#E0B266; --amber-dim:rgba(224,178,102,.13); --buy:#5BC08F; --sell:#D3746E;
    --row-hover:rgba(255,255,255,.028);
    --inter:'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    --ease:cubic-bezier(.2,.6,.2,1);
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{
    margin:0; color:var(--ink);
    background:
      radial-gradient(120% 80% at 50% -8%, rgba(224,178,102,.045), transparent 55%),
      var(--ground);
    font-family:var(--inter); font-size:14px; letter-spacing:.005em;
    -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
  }
  .num{font-family:var(--mono); font-variant-numeric:tabular-nums; font-feature-settings:"tnum" 1;}
  ::selection{background:rgba(224,178,102,.24);}
  /* quiet scrollbars everywhere */
  *::-webkit-scrollbar{width:9px; height:9px;}
  *::-webkit-scrollbar-thumb{background:var(--hair); border-radius:8px; border:2px solid transparent; background-clip:content-box;}
  *::-webkit-scrollbar-thumb:hover{background:var(--hair-lit); background-clip:content-box;}
  *::-webkit-scrollbar-track{background:transparent;}

  /* ---- desk frame: centered, capped, single-screen ---------------------- */
  .desk{
    max-width:1560px; margin:0 auto; height:100vh;
    /* chrome, strip, HERO (dominant 1fr — the graph), mints, tape */
    display:grid; grid-template-rows:auto auto minmax(0,1fr) minmax(0,23vh) minmax(0,23vh);
  }

  /* ---- 1. chrome -------------------------------------------------------- */
  .chrome{
    display:flex; align-items:center; justify-content:space-between;
    padding:15px 32px; gap:16px;
  }
  .wm{display:flex; align-items:center; gap:11px;}
  .wm .mark{font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--muted-2); font-weight:500;}
  .pill{
    font-size:9.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--muted);
    border:1px solid var(--hair); border-radius:999px; padding:3px 10px; white-space:nowrap;
  }
  .pill.seal{color:var(--amber); border-color:rgba(224,178,102,.32);}
  .live{display:flex; align-items:center; gap:9px; font-size:11px; letter-spacing:.05em;
        text-transform:uppercase; color:var(--muted); font-family:var(--mono);}
  .dot{width:8px; height:8px; border-radius:50%; background:var(--amber);
       box-shadow:0 0 0 0 rgba(224,178,102,.5); animation:breathe 3.2s var(--ease) infinite;}
  .dot.stale{background:var(--sell); animation:none;}
  @keyframes breathe{
    0%,100%{box-shadow:0 0 0 0 rgba(224,178,102,.42);}
    55%{box-shadow:0 0 0 6px rgba(224,178,102,0);}
  }

  /* ---- 2. stat strip ---------------------------------------------------- */
  .strip{display:flex; border-top:1px solid var(--hair);}
  .tile{
    flex:1 1 0; padding:15px 26px; min-width:0;
    display:flex; flex-direction:column; gap:4px;
    transition:background .18s var(--ease);
  }
  .tile:hover{background:var(--row-hover);}
  .tile + .tile{border-left:1px solid var(--hair);}
  .tile .val{font-family:var(--mono); font-variant-numeric:tabular-nums; font-weight:400;
             font-size:29px; line-height:1.02; color:var(--ink); letter-spacing:-.01em;
             transition:color .2s var(--ease);}
  .tile:first-child .val{font-size:33px;}
  .tile .val.amber{color:var(--amber);}
  .tile .val.sell{color:var(--sell);}
  .tile .val.pos{color:var(--buy);}
  .tile .lab{font-size:10px; text-transform:uppercase; letter-spacing:.1em; color:var(--muted); font-weight:500;}
  .tile .sub{font-family:var(--mono); font-variant-numeric:tabular-nums;
             font-size:11px; color:var(--muted); letter-spacing:0;}

  /* ---- 3. hero curve ---------------------------------------------------- */
  .hero{border-top:1px solid var(--hair); padding:16px 32px 10px; display:flex;
        flex-direction:column; min-height:0;}
  .hero-head{display:flex; align-items:baseline; justify-content:space-between; gap:16px; margin-bottom:2px;}
  .kick{font-size:10.5px; text-transform:uppercase; letter-spacing:.11em; color:var(--muted); font-weight:500;}
  .hero-key{display:flex; align-items:center; gap:18px; font-size:10.5px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em;}
  .hero-key .k{display:flex; align-items:center; gap:7px;}
  .swatch{width:15px; height:2px; border-radius:2px; display:inline-block;}
  .swatch.lws{background:var(--amber); box-shadow:0 0 6px rgba(224,178,102,.5);}
  .swatch.null{background:transparent; height:0; border-top:2px dashed var(--muted);}
  #chart{flex:1 1 auto; min-height:0; position:relative;
         background:linear-gradient(180deg, rgba(255,255,255,.008), transparent 40%);
         border-radius:6px;}
  #chart svg{display:block; width:100%; height:100%;}

  /* ---- shared: section shells (mints, tape) ----------------------------- */
  .mints,.tape{border-top:1px solid var(--hair); display:flex; flex-direction:column; min-height:0;
               padding:0 32px 12px;}
  .mints-head,.tape-head{display:flex; align-items:center; justify-content:space-between;
             padding:12px 0 8px; font-size:10.5px; letter-spacing:.09em;
             text-transform:uppercase; color:var(--muted); font-weight:500;}
  .mints-head .split,.tape-head .split{font-family:var(--mono); font-variant-numeric:tabular-nums; color:var(--muted-2);}
  .mints-body,.tape-body{flex:1 1 auto; overflow-y:auto; min-height:0; background:var(--panel);
              border:1px solid var(--hair); border-radius:7px;}

  /* mint list — live buyers & market cap + the bot's own footprint */
  .mrow{display:grid; grid-template-columns:minmax(0,1.5fr) .9fr 1.15fr 1fr 16px;
        align-items:center; gap:14px; padding:9px 15px; font-family:var(--mono);
        font-variant-numeric:tabular-nums; border-bottom:1px solid var(--hair); font-size:12.5px;
        transition:background .14s var(--ease);}
  .mrow:last-child{border-bottom:none;}
  .mrow:hover{background:var(--row-hover);}
  .m-name{display:flex; align-items:center; gap:9px; min-width:0;}
  .m-mint{color:var(--ink); white-space:nowrap;}
  .copyable{cursor:pointer; transition:color .12s var(--ease); border-bottom:1px dashed transparent;}
  .copyable:hover{color:var(--amber); border-bottom-color:rgba(224,178,102,.4);}
  .copyable.copied{color:var(--buy); border-bottom-color:transparent;}
  .m-bot{font-size:8.5px; letter-spacing:.08em; text-transform:uppercase; padding:2px 6px;
         border-radius:4px; white-space:nowrap; font-family:var(--inter); font-weight:600;}
  .m-bot.bought{color:var(--buy); background:rgba(91,192,143,.12);}
  .m-bot.vetoed{color:var(--muted); background:rgba(255,255,255,.05);}
  .m-cell{display:flex; flex-direction:column; gap:1px; text-align:right;}
  .m-cell .v{color:var(--ink);}
  .m-cell .k{font-size:8.5px; letter-spacing:.05em; text-transform:uppercase; color:var(--muted);}
  .m-buyers .v{color:var(--amber);}
  .m-bs{text-align:right; color:var(--muted);}
  .m-bs .b{color:var(--buy);} .m-bs .s{color:var(--sell);}
  .m-anchor{width:7px; height:7px; border-radius:50%; border:1px solid var(--hair-lit);
                  justify-self:center;}
  .m-anchor.on{background:var(--muted); border-color:var(--muted);}

  /* tape */
  .tape-empty{display:flex; align-items:center; justify-content:center; height:100%;
              color:var(--muted); font-size:12px; letter-spacing:.04em;}
  .row{
    display:grid; grid-template-columns:14px 44px 84px minmax(0,1fr) 58px 12px;
    align-items:center; gap:12px; height:30px; padding:0 15px;
    font-family:var(--mono); font-variant-numeric:tabular-nums; font-size:12.5px;
    color:var(--muted); transition:background .14s var(--ease);
  }
  .row:hover{background:var(--row-hover);}
  .row .tick{width:8px; height:8px; border-radius:2px; justify-self:center;}
  .row.buy .side{color:var(--buy);} .row.buy .tick{background:var(--buy);}
  .row.sell .side{color:var(--sell);} .row.sell .tick{background:var(--sell);}
  .row .side{font-size:10.5px; letter-spacing:.06em; font-weight:500;}
  .row .sol{text-align:right; color:var(--ink);}
  .row .mint{color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
  .row .rt{text-align:right; color:var(--muted); font-size:11px;}
  .row .integ{width:7px; height:7px; border-radius:50%; justify-self:center;
              border:1px solid var(--hair-lit);}
  .row .integ.on{background:var(--muted); border-color:var(--muted);}
  .row.dust{opacity:.5;}
  .row.fresh{animation:slidein .16s var(--ease);}
  @keyframes slidein{from{opacity:0; transform:translateY(-7px);} to{opacity:1; transform:none;}}

  /* ---- narrow ----------------------------------------------------------- */
  @media (max-width:820px){
    .desk{height:auto; grid-template-rows:none; display:block;}
    .strip{flex-wrap:wrap;}
    .tile{flex:1 1 33%; border-top:1px solid var(--hair);}
    .tile + .tile{border-left:none;}
    .hero{height:52vh;} .mints{height:40vh;} .tape{height:44vh;}
  }
  @media (prefers-reduced-motion:reduce){ *{animation:none!important; transition:none!important;} }
</style>
</head>
<body>
<div class="desk">

  <!-- 1. chrome -->
  <header class="chrome">
    <div class="wm">
      <span class="mark">AFTERSHOCK · PAC / LWS</span>
      <span class="pill">PAPER · READ-ONLY</span>
      <span class="pill seal">EXECUTORS RETIRED · DATA LIVE</span>
    </div>
    <div class="live"><span class="dot" id="dot"></span><span id="liveline">connecting…</span></div>
  </header>

  <!-- 2. stat strip -->
  <section class="strip" id="strip">
    <div class="tile"><div class="val amber num" id="t-net">—</div><div class="lab" id="t-net-lab">Net SOL</div><div class="sub" id="t-net-sub">no trades yet</div></div>
    <div class="tile"><div class="val num" id="t-resolved">0</div><div class="lab">Resolved</div><div class="sub" id="t-resolved-sub">0 open</div></div>
    <div class="tile"><div class="val num" id="t-unex">0</div><div class="lab">Unexitable</div><div class="sub" id="t-unex-sub">0% of resolved</div></div>
    <div class="tile"><div class="val num" id="t-open">0</div><div class="lab">Censored</div><div class="sub">open at retirement</div></div>
    <div class="tile"><div class="val num" id="t-veto">—</div><div class="lab">B20B Veto</div><div class="sub" id="t-veto-sub">0 / 0 decisions</div></div>
    <div class="tile"><div class="val num" id="t-cov">—</div><div class="lab">V2 eligible</div><div class="sub" id="t-cov-sub">0 / 0 classified</div></div>
  </section>

  <!-- 3. hero curve -->
  <section class="hero">
    <div class="hero-head">
      <span class="kick">Cumulative Net SOL · retired paper books (immutable)</span>
      <div class="hero-key">
        <span class="k"><span class="swatch lws"></span><span id="key-prim">live</span></span>
        <span class="k" id="key-null"><span class="swatch null"></span><span id="key-other">control</span></span>
      </div>
    </div>
    <div id="chart"></div>
  </section>

  <!-- 4. mints -->
  <section class="mints">
    <div class="mints-head"><span>Mints · live buyers &amp; market cap</span><span class="split" id="mints-count">—</span></div>
    <div class="mints-body" id="mints-body">
      <div class="tape-empty">no mints yet · awaiting launches</div>
    </div>
  </section>

  <!-- 5. tape -->
  <section class="tape">
    <div class="tape-head"><span>Live Tape · buys / sells</span><span class="split" id="tape-split">—</span></div>
    <div class="tape-body" id="tape-body">
      <div class="tape-empty">tape idle · awaiting events</div>
    </div>
  </section>

</div>

<script>
"use strict";
// --------- palette (mirrors CSS so the SVG stays in the same grammar) ------
const C = {
  ground:'#0E1116', panel:'#161A21', hair:'#242A33', hairLit:'#3A434F',
  muted:'#7E8794', ink:'#EAEDF2', amber:'#E0B266', buy:'#5BC08F', sell:'#D3746E'
};
const SVGNS='http://www.w3.org/2000/svg';
let CHART=null;          // last-drawn scale params, for the hover crosshair
let lastFirstT=null;     // track newest tape row so only genuinely new rows animate

// --------- formatting helpers ---------------------------------------------
function fmtSigned(v,dp){ const s=v>=0?'+':'−'; return s+Math.abs(v).toFixed(dp); }
function fmtSol(v){ return fmtSigned(v,3); }
function shortMint(m){ return (m&&m.length>10)? m.slice(0,4)+'…'+m.slice(-4) : (m||'—'); }
// click a mint address to copy the FULL address to the clipboard (localhost is a secure context)
function copyText(txt, elm){
  if(!txt) return;
  const flash=()=>{ if(!elm) return; const orig=elm.textContent; elm.textContent='copied ✓';
    elm.classList.add('copied'); setTimeout(()=>{ elm.textContent=orig; elm.classList.remove('copied'); }, 900); };
  const fallback=()=>{ const ta=document.createElement('textarea'); ta.value=txt;
    ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta); ta.select();
    try{ document.execCommand('copy'); }catch(e){} document.body.removeChild(ta); flash(); };
  try{ if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(txt).then(flash, fallback); } else { fallback(); } }
  catch(e){ fallback(); }
}
function copyableMint(fullMint){
  const s=el('span','m-mint copyable', shortMint(fullMint));
  s.title=(fullMint||'')+' · click to copy';
  s.addEventListener('click', (ev)=>{ ev.stopPropagation(); copyText(fullMint, s); });
  return s;
}
function pad2(n){ return (n<10?'0':'')+n; }
function hhmm(sec){ const d=new Date(sec*1000); return pad2(d.getHours())+':'+pad2(d.getMinutes()); }
function relTime(sec){
  if(sec==null) return '';
  let d=Math.max(0,(Date.now()/1000)-sec);
  if(d<60) return Math.floor(d)+'s';
  if(d<3600) return Math.floor(d/60)+'m';
  if(d<86400) return Math.floor(d/3600)+'h';
  return Math.floor(d/86400)+'d';
}
function el(tag,cls,txt){ const e=document.createElement(tag); if(cls)e.className=cls; if(txt!=null)e.textContent=txt; return e; }

// --------- nice axis scaling ----------------------------------------------
function niceNum(range,round){
  if(range<=0) return 1;
  const exp=Math.floor(Math.log10(range)), f=range/Math.pow(10,exp);
  let nf; if(round){ nf=f<1.5?1:f<3?2:f<7?5:10; } else { nf=f<=1?1:f<=2?2:f<=5?5:10; }
  return nf*Math.pow(10,exp);
}
function niceScale(lo,hi,n){
  if(lo===hi){ lo-=1; hi+=1; }
  const range=niceNum(hi-lo,false), step=niceNum(range/Math.max(1,n-1),true);
  const nlo=Math.floor(lo/step)*step, nhi=Math.ceil(hi/step)*step;
  const ticks=[];
  for(let v=nlo; v<=nhi+step*0.5; v+=step) ticks.push(+v.toFixed(9));
  return {lo:nlo,hi:nhi,step:step,ticks:ticks};
}

// --------- the hero curve --------------------------------------------------
function drawChart(state){
  const host=document.getElementById('chart');
  const W=host.clientWidth||800, H=host.clientHeight||300;
  const L=58,R=98,T=22,B=30, plotW=Math.max(10,W-L-R), plotH=Math.max(10,H-T-B);
  // amber line = the PRIMARY (live-trading) arm; muted dashed = the secondary control
  const lws=state.equity_primary||[], nul=state.equity_secondary||[];
  const primTag=(state.primary_label||'live').split(' ')[0].toUpperCase();
  const otherTag=(state.other_label||'').split(' ')[0].toUpperCase();
  const hasData = lws.length>0 || nul.length>0;

  // x/y domains ---------------------------------------------------------
  let t0,t1,vlo,vhi;
  if(hasData){
    let ts=[], vs=[0];
    for(const p of lws){ ts.push(p.t); vs.push(p.net); }
    for(const p of nul){ ts.push(p.t); vs.push(p.net); }
    t0=Math.min.apply(null,ts); t1=Math.max.apply(null,ts);
    if(t0===t1){ t0-=30; t1+=30; }
    vlo=Math.min.apply(null,vs); vhi=Math.max.apply(null,vs);
  } else {
    const now=Date.now()/1000; t0=now-300; t1=now; vlo=-1; vhi=1;
  }
  const ys=niceScale(vlo,vhi,4);
  const xOf=t=> L+(t-t0)/((t1-t0)||1)*plotW;
  const yOf=v=> T+(ys.hi-v)/((ys.hi-ys.lo)||1)*plotH;
  CHART={L,R,T,B,W,H,plotW,plotH,t0,t1,ys,xOf,yOf,lws,nul};

  const svg=document.createElementNS(SVGNS,'svg');
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio','none');

  // defs: soft amber area fill
  const defs=document.createElementNS(SVGNS,'defs');
  defs.innerHTML='<linearGradient id="fillA" x1="0" y1="0" x2="0" y2="1">'+
    '<stop offset="0%" stop-color="'+C.amber+'" stop-opacity="0.14"/>'+
    '<stop offset="100%" stop-color="'+C.amber+'" stop-opacity="0"/></linearGradient>';
  svg.appendChild(defs);

  const mk=(tag,attrs)=>{ const e=document.createElementNS(SVGNS,tag);
    for(const k in attrs) e.setAttribute(k,attrs[k]); return e; };

  // horizontal gridlines (no vertical grid) + y ticks
  for(const v of ys.ticks){
    const y=yOf(v), zero=Math.abs(v)<1e-9;
    svg.appendChild(mk('line',{x1:L,y1:y,x2:W-R,y2:y,
      stroke: zero?C.hairLit:C.hair, 'stroke-width': zero?1.4:1}));
    const lab=mk('text',{x:L-10,y:y+3.5,'text-anchor':'end','font-size':11,fill:C.muted});
    lab.setAttribute('font-family','JetBrains Mono, monospace');
    lab.style.fontVariantNumeric='tabular-nums';
    lab.textContent=(v>=0?'':'−')+Math.abs(v).toFixed(2);
    svg.appendChild(lab);
  }
  // x ticks (~4 sparse HH:MM)
  const XT=4;
  for(let i=0;i<=XT;i++){
    const t=t0+(t1-t0)*i/XT, x=xOf(t);
    const lab=mk('text',{x:x,y:H-10,'text-anchor':i===0?'start':(i===XT?'end':'middle'),
      'font-size':11,fill:C.muted});
    lab.setAttribute('font-family','JetBrains Mono, monospace');
    lab.textContent=hhmm(t);
    svg.appendChild(lab);
  }

  function pathD(pts){
    if(!pts.length) return '';
    let d='M '+xOf(pts[0].t).toFixed(1)+' '+yOf(pts[0].net).toFixed(1);
    for(let i=1;i<pts.length;i++) d+=' L '+xOf(pts[i].t).toFixed(1)+' '+yOf(pts[i].net).toFixed(1);
    return d;
  }

  if(hasData){
    // NULL first (muted, dashed, behind)
    if(nul.length){
      svg.appendChild(mk('path',{d:pathD(nul),fill:'none',stroke:C.muted,
        'stroke-width':1.5,'stroke-dasharray':'4 3','opacity':0.75,
        'stroke-linejoin':'round'}));
    }
    // PRIMARY (amber) area fill + a soft halo behind a crisp line
    if(lws.length){
      const d=pathD(lws);
      const area=d+` L ${xOf(lws[lws.length-1].t).toFixed(1)} ${yOf(ys.lo).toFixed(1)}`+
                 ` L ${xOf(lws[0].t).toFixed(1)} ${yOf(ys.lo).toFixed(1)} Z`;
      svg.appendChild(mk('path',{d:area,fill:'url(#fillA)',stroke:'none'}));
      svg.appendChild(mk('path',{d:d,fill:'none',stroke:C.amber,'stroke-width':5,
        'opacity':0.16,'stroke-linejoin':'round','stroke-linecap':'round'}));   // halo
      svg.appendChild(mk('path',{d:d,fill:'none',stroke:C.amber,'stroke-width':2,
        'stroke-linejoin':'round','stroke-linecap':'round'}));
    }
    // endpoints + floating chips
    endpoint(svg,mk,lws,C.amber,primTag);
    endpoint(svg,mk,nul,C.muted,otherTag);
  } else {
    // honest empty state — framed chart, centered message + live sub-line
    const cx=L+plotW/2, cy=T+plotH/2;
    const m=mk('text',{x:cx,y:cy-4,'text-anchor':'middle','font-size':14,fill:C.muted});
    m.setAttribute('font-family','Inter, sans-serif');
    m.textContent='Awaiting first resolved trade';
    svg.appendChild(m);
    const sub=mk('text',{x:cx,y:cy+18,'text-anchor':'middle','font-size':11.5,fill:C.muted});
    sub.setAttribute('font-family','JetBrains Mono, monospace');
    sub.setAttribute('opacity','0.8');
    sub.textContent=emptySubline(state);
    svg.appendChild(sub);
  }

  // hover layer -----------------------------------------------------------
  const cross=mk('g',{}); cross.style.display='none'; svg.appendChild(cross);
  const cline=mk('line',{y1:T,y2:H-B,stroke:C.amber,'stroke-width':1,'opacity':0.6});
  cross.appendChild(cline);
  const readBg=mk('rect',{rx:3,fill:C.panel,stroke:C.hair,'stroke-width':1,height:22});
  const readTx=mk('text',{'font-size':11,fill:C.ink,y:T+14});
  readTx.setAttribute('font-family','JetBrains Mono, monospace');
  readTx.style.fontVariantNumeric='tabular-nums';
  cross.appendChild(readBg); cross.appendChild(readTx);

  const hit=mk('rect',{x:L,y:T,width:plotW,height:plotH,fill:'transparent'});
  hit.style.cursor='crosshair';
  hit.addEventListener('mousemove',ev=>{
    if(!hasData){ return; }
    const r=svg.getBoundingClientRect();
    const sx=(ev.clientX-r.left)*(W/r.width);
    const t=t0+(sx-L)/plotW*(t1-t0);
    const a=nearest(lws,t), b=nearest(nul,t);
    const x=Math.max(L,Math.min(W-R,sx));
    cline.setAttribute('x1',x); cline.setAttribute('x2',x);
    let parts=[hhmm(t)];
    if(a) parts.push(primTag+' '+fmtSol(a.net));
    if(b) parts.push(otherTag+' '+fmtSol(b.net));
    if(a&&b) parts.push('Δ '+fmtSol(a.net-b.net));
    readTx.textContent=parts.join('  ·  ');
    // position readout box, kept inside the plot
    const tw=readTx.getComputedTextLength?readTx.getComputedTextLength():parts.join('  ·  ').length*6.4;
    let bx=Math.min(x+8, W-R-tw-14); bx=Math.max(L+2,bx);
    readBg.setAttribute('x',bx-6); readBg.setAttribute('y',T+2);
    readBg.setAttribute('width',tw+12);
    readTx.setAttribute('x',bx);
    cross.style.display='';
  });
  hit.addEventListener('mouseleave',()=>{ cross.style.display='none'; });
  svg.appendChild(hit);

  host.innerHTML=''; host.appendChild(svg);
}

function endpoint(svg,mk,pts,color,label){
  if(!pts.length) return;
  const last=pts[pts.length-1];
  const x=CHART.xOf(last.t), y=CHART.yOf(last.net);
  const isL=(color===C.amber);   // the primary (amber) arm gets the pulse + coloured chip border
  if(isL){
    const ring=mk('circle',{cx:x,cy:y,r:3.4,fill:'none',stroke:color,'stroke-width':1.4,opacity:0.5});
    ring.innerHTML='<animate attributeName="r" values="3.4;11" dur="1.9s" repeatCount="indefinite"/>'+
                   '<animate attributeName="opacity" values="0.5;0" dur="1.9s" repeatCount="indefinite"/>';
    svg.appendChild(ring);
  }
  svg.appendChild(mk('circle',{cx:x,cy:y,r:3.4,fill:color}));
  // floating chip on the panel gutter at the right edge
  const txt=fmtSol(last.net)+' SOL';
  const w=txt.length*6.6+16, cx=CHART.W-CHART.R+10;
  let cy=Math.max(CHART.T+11, Math.min(CHART.H-CHART.B-11, y));
  svg.appendChild(mk('rect',{x:cx,y:cy-11,rx:3,width:w,height:22,
    fill:C.panel,stroke:isL?color:C.hair,'stroke-width':1}));
  const tx=mk('text',{x:cx+8,y:cy+4,'font-size':11.5,fill:isL?color:C.muted});
  tx.setAttribute('font-family','JetBrains Mono, monospace');
  tx.style.fontVariantNumeric='tabular-nums';
  tx.textContent=txt;
  svg.appendChild(tx);
}

function nearest(pts,t){
  if(!pts.length) return null;
  let best=pts[0],bd=Math.abs(pts[0].t-t);
  for(const p of pts){ const d=Math.abs(p.t-t); if(d<bd){bd=d;best=p;} }
  return best;
}

function emptySubline(state){
  const fc=(state.feed_count||0).toLocaleString('en-US');
  const open=(state.tiles&&state.tiles.open)||0;
  if(open>0) return open+' positions open · awaiting first exit';
  return 'feed live · '+fc+' buys/sells observed · 0 positions resolved';
}

// --------- tiles -----------------------------------------------------------
function drawTiles(t){
  const set=(id,v)=>{ const e=document.getElementById(id); if(e)e.textContent=v; };
  const cls=(id,c)=>{ const e=document.getElementById(id); if(e)e.className='val num'+(c?(' '+c):''); };

  // 1 NET SOL — the LIVE trading arm (never blank while an arm is working)
  const netLab=document.getElementById('t-net-lab');
  if(netLab) netLab.textContent='Net SOL · '+(t.primary_label||'live');
  if(t.resolved>0){
    set('t-net',fmtSol(t.net_sol));
    cls('t-net', t.net_sol<0 ? 'sell' : 'amber');
    set('t-net-sub', (t.other_label||'other')+' '+fmtSol(t.net_sol_other));
  } else {
    set('t-net','—'); cls('t-net','amber'); set('t-net-sub','no trades yet');
  }
  // 2 RESOLVED
  set('t-resolved',String(t.resolved)); set('t-resolved-sub',t.open+' open');
  // 3 UNEXITABLE
  set('t-unex',String(t.unexitable));
  cls('t-unex', t.unexitable>0 ? 'sell' : '');
  set('t-unex-sub', (t.resolved>0? t.unexitable_pct.toFixed(0):'0')+'% of resolved');
  // 4 OPEN BOOK
  set('t-open',String(t.open));
  // 5 B20B VETO
  set('t-veto', t.veto_rate==null ? '—' : t.veto_rate.toFixed(1)+'%');
  set('t-veto-sub', t.veto_v+' / '+t.veto_d+' decisions');
  // 6 COVERAGE
  set('t-cov', t.coverage==null ? '—' : t.coverage.toFixed(0)+'%');
  set('t-cov-sub', t.coverage_r+' / '+t.coverage_c+' classified');

  // graph key labels — reflect which arm is the live (amber) line vs the control
  const kp=document.getElementById('key-prim'); if(kp) kp.textContent=(t.primary_label||'live');
  const ko=document.getElementById('key-other'); if(ko) ko.textContent=(t.other_label||'control');
}

// --------- tape ------------------------------------------------------------
function drawTape(tape){
  const body=document.getElementById('tape-body');
  const split=document.getElementById('tape-split');
  if(!tape || tape.length===0){
    body.innerHTML='<div class="tape-empty">tape idle · awaiting events</div>';
    split.textContent='—'; lastFirstT=null; return;
  }
  let buys=0,sells=0;
  for(const e of tape){ if(e.is_buy)buys++; else sells++; }
  split.textContent=buys+' buys · '+sells+' sells';

  const newestT = tape[0].t;
  const frag=document.createDocumentFragment();
  for(const e of tape){
    const dust = e.sol < 0.0005;
    const r=el('div','row '+(e.is_buy?'buy':'sell')+(dust?' dust':''));
    if(lastFirstT!=null && e.t!=null && e.t>lastFirstT) r.classList.add('fresh');
    r.appendChild(el('span','tick'));
    r.appendChild(el('span','side',e.is_buy?'BUY':'SELL'));
    r.appendChild(el('span','sol',e.sol.toFixed(3)));
    const mintEl=el('span','mint copyable',shortMint(e.mint));
    mintEl.title=(e.mint||'')+' · click to copy';
    mintEl.addEventListener('click',(ev)=>{ ev.stopPropagation(); copyText(e.mint,mintEl); });
    r.appendChild(mintEl);
    r.appendChild(el('span','rt',relTime(e.t)));
    const integ=el('span','integ'+((e.anchored||e.reconciled)?' on':''));
    r.appendChild(integ);
    frag.appendChild(r);
  }
  body.innerHTML=''; body.appendChild(frag);
  lastFirstT=newestT;
}

// --------- mint list — live buyers & market cap ---------------------------
function drawMints(mints){
  const body=document.getElementById('mints-body');
  const count=document.getElementById('mints-count');
  if(!body) return;
  if(!mints || !mints.length){
    body.innerHTML='<div class="tape-empty">no mints yet · awaiting launches</div>';
    if(count) count.textContent='—';
    return;
  }
  if(count) count.textContent=mints.length+' active';
  const frag=document.createDocumentFragment();
  for(const m of mints){
    const r=el('div','mrow');
    const name=el('div','m-name');
    name.appendChild(copyableMint(m.mint));
    if(m.bot){ name.appendChild(el('span','m-bot '+m.bot, m.bot==='bought'?'bought':'vetoed')); }
    r.appendChild(name);
    const b=el('div','m-cell m-buyers');
    b.appendChild(el('span','v',String(m.buyers)));
    b.appendChild(el('span','k','buyers'));
    r.appendChild(b);
    const mc=el('div','m-cell');
    mc.appendChild(el('span','v', (m.mcap_sol!=null? m.mcap_sol.toFixed(1):'—')+' ◎'));
    mc.appendChild(el('span','k','mcap sol'));
    r.appendChild(mc);
    const bs=el('div','m-bs');
    const bb=el('span','b',String(m.buys)); const sl=el('span','s',String(m.sells));
    bs.appendChild(bb); bs.appendChild(document.createTextNode(' / ')); bs.appendChild(sl);
    r.appendChild(bs);
    r.appendChild(el('span','m-anchor'+(m.anchored?' on':'')));
    frag.appendChild(r);
  }
  body.innerHTML=''; body.appendChild(frag);
}

// --------- chrome liveness -------------------------------------------------
function drawHealth(h){
  const line=document.getElementById('liveline');
  const dot=document.getElementById('dot');
  if(!h || !h.present){
    line.textContent='FEED STALE'; if(dot) dot.classList.add('stale'); return;
  }
  const fresh = (h.status==='FRESH');
  const ago = h.observed_sec!=null ? relTime(h.observed_sec) : '—';
  const lag = h.lag!=null ? h.lag : '—';
  line.textContent = fresh
    ? ('FEED FRESH · lag '+lag+' · updated '+ago+' ago')
    : ('FEED '+(h.status||'STALE')+' · updated '+ago+' ago');
  if(dot) dot.classList.toggle('stale', !fresh);
}

// --------- poll loop -------------------------------------------------------
async function poll(){
  try{
    const res=await fetch('/api/state',{cache:'no-store'});
    if(!res.ok) throw new Error('http '+res.status);
    const s=await res.json();
    window.__last=s;                       // kept for resize redraws
    drawHealth(s.health);
    drawTiles(s.tiles||{});
    drawChart(s);
    drawMints(s.mints||[]);
    drawTape(s.tape||[]);
  }catch(e){
    const line=document.getElementById('liveline');
    if(line) line.textContent='reconnecting…';
  }
}
// redraw only the curve on resize (cheap; tiles/tape unaffected by width)
window.addEventListener('resize',()=>{ if(window.__last) drawChart(window.__last); });
poll();
setInterval(poll,2000);
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# HTTP server
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            try:
                body = json.dumps(build_state()).encode("utf-8")
            except Exception as exc:  # never 500 the poll — return an empty shell
                body = json.dumps({
                    "equity_primary": [], "equity_secondary": [], "tape": [], "mints": [],
                    "feed_count": 0, "tiles": {}, "health": {"present": False},
                    "error": str(exc),
                }).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, *args):  # keep the console quiet / calm
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"AFTERSHOCK · PAC / LWS — Quiet Desk dashboard")
    print(f"  serving   http://{HOST}:{PORT}/")
    print(f"  repo root {ROOT}")
    print(f"  ledgers   {'present' if LEDGER_LWS.exists() else 'absent (empty state)'} · "
          f"feed {'present' if FEED_EVENTS.exists() else 'absent'}")
    print("  Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
