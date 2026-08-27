#!/usr/bin/env python3
"""The eyes -- the FREE, KEYLESS new-memecoin feed and the price-refresh probe.

Primary source: GeckoTerminal's public API (no key, free tier ~30 calls/min). Two endpoints:

  * GET /networks/solana/new_pools  -- newest pools across ALL Solana launch venues (pump-fun,
    raydium-launchlab, meteora, ...), not limited to one platform. Each pool carries: creation time,
    base-token price (USD + native), FDV, market cap when known, USD reserve (a liquidity proxy),
    and per-window transaction stats (buys / sells / unique buyers / unique sellers) plus volume.
  * GET /networks/solana/pools/{address} -- the same attributes, refreshed, used to mark an open
    paper position to the latest price without any wallet or on-chain call.

Everything here is READ-ONLY market data. No order, no wallet, no RPC write. Fields absent from the
free feed (per-wallet holdings, the on-chain largest-buyer share the frozen B20B screen wants) are
NOT fabricated -- the screen adapts to the PROXY the feed actually exposes (see screen.py).
"""

from __future__ import annotations

import datetime as dt

from . import Refused
from . import net

GT_BASE = "https://api.geckoterminal.com/api/v2"


def _f(x):
    """Parse a numeric string/None from the feed into float or None -- never a silent zero."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _age_minutes(created_iso: str, now: dt.datetime) -> float | None:
    if not created_iso:
        return None
    try:
        created = dt.datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (now - created).total_seconds() / 60.0


def _normalize(pool: dict, now: dt.datetime) -> dict:
    a = pool.get("attributes", {})
    rel = pool.get("relationships", {})
    dex = (((rel.get("dex") or {}).get("data") or {}).get("id")) or "?"
    base = (((rel.get("base_token") or {}).get("data") or {}).get("id")) or ""
    # The smallest populated window is the freshest read of early participation; m5==h1 for new pools.
    tx = a.get("transactions", {}) or {}
    win = tx.get("m5") or tx.get("m15") or tx.get("h1") or {}
    vol = a.get("volume_usd", {}) or {}
    return {
        "pool_address": a.get("address"),
        "chain": "solana",
        "dex": dex,
        "name": a.get("name"),
        "base_token": base.replace("solana_", ""),
        "price_usd": _f(a.get("base_token_price_usd")),
        "fdv_usd": _f(a.get("fdv_usd")),
        "market_cap_usd": _f(a.get("market_cap_usd")),
        "reserve_usd": _f(a.get("reserve_in_usd")),
        "pool_created_at": a.get("pool_created_at"),
        "age_minutes": _age_minutes(a.get("pool_created_at"), now),
        "buys": int(win.get("buys") or 0),
        "sells": int(win.get("sells") or 0),
        "buyers": int(win.get("buyers") or 0),
        "sellers": int(win.get("sellers") or 0),
        "volume_usd_m5": _f(vol.get("m5")),
        "pulled_utc": now.isoformat(),
    }


def read_new_pools(spec: dict, *, pages: int = 1) -> list[dict]:
    """Pull the newest Solana pools across all launch venues. Light: 1-2 pages, polite throttle."""
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for page in range(1, max(1, pages) + 1):
        # new_pools is the SINGLE highest-value GeckoTerminal call: one request returns ~20 fully
        # screenable coins, and it is the ONLY discovery path that still works when the tier is
        # saturated (the PumpPortal fallback needs per-mint GT enrichment, which 429s too). So it is
        # worth a few BOUNDED, spread-out retries -- 3 tries with a 1s/2s backoff spans several
        # positions of the rolling rate window to catch a free slot -- while still capping at ~11s so
        # a fully-blocked scan gives up quickly instead of the old ~60s hang.
        payload = net.http_get_json(f"{GT_BASE}/networks/solana/new_pools?page={page}",
                                    tries=3, backoff_base=1.0)
        data = payload.get("data")
        if data is None:
            raise Refused(f"new_pools page {page} returned no 'data' -- refusing to invent an empty feed")
        for pool in data:
            snap = _normalize(pool, now)
            if snap["pool_address"]:
                out.append(snap)
    return out


def refresh_pool(spec: dict, pool_address: str) -> dict:
    """Refresh one pool's live attributes to mark an open paper position. Read-only."""
    # Fail fast under contention (see read_new_pools): a 429'd price refresh should fall back to
    # "no live price" quickly so track_once still fires horizon/UNEXITABLE, not hang on backoff.
    payload = net.http_get_json(f"{GT_BASE}/networks/solana/pools/{pool_address}",
                                tries=2, backoff_base=0.5)
    data = payload.get("data")
    if not data:
        raise Refused(f"pool {pool_address} no longer resolves on the feed")
    return _normalize(data, dt.datetime.now(dt.timezone.utc))


def enrich_token(mint: str) -> dict | None:
    """Resolve a token MINT (from the PumpPortal push) to its pool snapshot via GeckoTerminal.

    PumpPortal tells us a mint exists in real time but not its unique-buyer/buys/sells counts; those
    live in the GeckoTerminal pool record once the token has traded. This one already-allowlisted,
    read-only call turns a pushed mint into the SAME normalized snapshot the screen consumes. Returns
    None if GeckoTerminal has not indexed the pool yet (brand-new) -- the caller simply skips it.
    """
    try:
        # Fail fast (1 try, no backoff): enrichment is bounded to a few calls per scan and a 429'd
        # mint is simply skipped -- there is no value in waiting out backoff on a saturated tier.
        payload = net.http_get_json(f"{GT_BASE}/networks/solana/tokens/{mint}/pools",
                                    tries=1)
    except Refused:
        return None
    data = payload.get("data") or []
    if not data:
        return None
    snap = _normalize(data[0], dt.datetime.now(dt.timezone.utc))
    return snap if snap.get("pool_address") else None


def read_pumpportal_candidates(spec, seen, *, max_enrich: int = 6,
                               min_age_min: float = 1.5) -> list[dict]:
    """Discovery from the PumpPortal push buffer: enrich fresh, unseen mints into screen snapshots.

    Bounded to `max_enrich` GeckoTerminal lookups per scan (each throttled) so a scan stays light. Only
    mints received between `min_age_min` (time to accumulate a few buyers and be indexed) and the frozen
    max pool age are considered; anything staler is a trade already in progress. Fails soft -- a mint
    GeckoTerminal has not indexed yet is skipped, not fabricated.

    WHY ENRICHMENT IS STILL REQUIRED (honest field audit, do NOT silently substitute):
    The PumpPortal newToken push carries only {mint, name, symbol, pool, marketCapSol, vSolInBondingCurve,
    initialBuy, solAmount}. It does NOT carry unique-buyer / buys / sellers counts -- those only exist
    once the token has traded and is indexed. The frozen screen's core rules (deadness proxy
    min_unique_buyers, the bundle proxy buys/buyer, and the honeypot proxy) ALL depend on those counts,
    so a PumpPortal-only snapshot would fail every one of them (buyers=0) and can never PASS. The push's
    market_cap_sol is a market cap in SOL (not the USD FDV the screen thresholds on) and vSolInBondingCurve
    is a virtual-curve reserve (not the pool's USD reserve_in_usd), so neither is field-equivalent to the
    GeckoTerminal value the frozen thresholds were set against. We therefore do NOT feed the screen from
    the push directly (that would silently change the data the pre-registered thresholds compare against);
    the push is DISCOVERY only, and the one GeckoTerminal token->pools call per fresh mint supplies the
    real, equivalent screen fields. The fix for the 429 storm is contention reduction + fail-fast above,
    NOT swapping in non-equivalent PumpPortal fields.
    """
    from . import ws_data
    max_age = spec["screen"]["max_pool_age_minutes"]
    buffered = ws_data.read_buffer(max_age_minutes=max_age)
    now = dt.datetime.now(dt.timezone.utc)
    # Freshest first, so we enter as early as the memecoin timescale allows.
    buffered.sort(key=lambda r: r.get("received_utc", ""), reverse=True)
    out, used = [], 0
    for rec in buffered:
        if used >= max_enrich:
            break
        mint = rec.get("mint")
        if not mint:
            continue
        try:
            recv = dt.datetime.fromisoformat(rec["received_utc"])
        except (KeyError, ValueError):
            continue
        age = (now - recv).total_seconds() / 60.0
        if age < min_age_min:
            continue
        snap = enrich_token(mint)
        used += 1
        if snap is None or snap["pool_address"] in seen:
            continue
        snap["discovery_source"] = "pumpportal"
        out.append(snap)
    return out
