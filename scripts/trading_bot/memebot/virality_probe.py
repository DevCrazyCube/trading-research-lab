#!/usr/bin/env python3
"""Virality probe — map an off-chain viral term to the ONE right Solana mint, then rug/exitability-screen it.

The first, $0, no-wallet build step of the virality-signal thesis: a real viral moment (a meme/name
spiking off-chain) is mapped to the canonical memecoin — NOT the freshest scam-clone — by hard-to-fake
fields (deepest liquidity + real age + demonstrated sellers), then run through the exitability-first
screen (the same "nobody else showed up / what has anyone sold" logic as B20B). Reuses the memebot's
allowlisted free hosts (api.dexscreener.com, api.geckoterminal.com) — no new deps, no key, no spend.

    python -m scripts.trading_bot.memebot.virality_probe "peanut the squirrel"

Prints the ranked candidate swarm, the chosen canonical mint, its PASS/REJECT verdict, or ABSTAIN when
the top two are within margin (the "is this real" ambiguity → do not fire).
"""
from __future__ import annotations

import sys
import time

from . import net
from . import screen

# exitability-first screen spec for the ESTABLISHED-meme regime (weeks-old canonical coin, real depth).
SPEC = {
    "min_fdv_usd": 20_000,
    "min_reserve_usd": 15_000,          # you cannot exit into liquidity that is not there
    "min_unique_buyers": 30,            # B20B "nobody else showed up" proxy
    "honeypot_min_buys": 30,
    "max_buys_per_buyer": 12,           # wash proxy: many buys from few wallets
    "max_pool_age_minutes": 60 * 24 * 30,   # established regime: allow up to ~30 days old
    "min_sellers": 10,                  # exitability: demand demonstrated exits, not "what nobody sold"
    "allowed_dexes": ["raydium", "orca", "meteora", "pumpswap", "raydium-clmm", "raydium clmm"],
}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _dexscreener_swarm(term: str) -> list[dict]:
    """The Solana clone swarm for a viral term, as candidate pairs."""
    url = "https://api.dexscreener.com/latest/dex/search?q=" + net.quote(term) if hasattr(net, "quote") \
        else "https://api.dexscreener.com/latest/dex/search?q=" + term.replace(" ", "%20")
    data = net.http_get_json(url)
    pairs = data.get("pairs") or []
    out = []
    for p in pairs:
        if str(p.get("chainId")) != "solana":
            continue
        liq = _f((p.get("liquidity") or {}).get("usd"))
        created = p.get("pairCreatedAt")            # ms epoch
        age_min = ((time.time() * 1000 - created) / 60000.0) if created else None
        tx = (p.get("txns") or {}).get("h24") or {}
        out.append({
            "mint": (p.get("baseToken") or {}).get("address"),
            "symbol": (p.get("baseToken") or {}).get("symbol"),
            "name": (p.get("baseToken") or {}).get("name"),
            "pair": p.get("pairAddress"),
            "dex": p.get("dexId"),
            "reserve_usd": liq,
            "fdv_usd": _f(p.get("fdv")) or _f(p.get("marketCap")),
            "age_minutes": age_min,
            "buys": int(tx.get("buys") or 0),
            "sells": int(tx.get("sells") or 0),
        })
    return [c for c in out if c["mint"] and c["reserve_usd"] is not None]


def _enrich_buyers(cand: dict) -> None:
    """DexScreener exposes buy/sell COUNTS, not unique wallets; GeckoTerminal's pool detail does.
    Fill buyers/sellers from GeckoTerminal for the canonical pick (best-effort; leaves proxies on fail)."""
    try:
        url = ("https://api.geckoterminal.com/api/v2/networks/solana/pools/"
               + cand["pair"] + "?include=")
        a = (net.http_get_json(url).get("data") or {}).get("attributes") or {}
        tx = (a.get("transactions") or {}).get("h24") or {}
        if "buyers" in tx:
            cand["buyers"] = int(tx.get("buyers") or 0)
        if "sellers" in tx:
            cand["sellers"] = int(tx.get("sellers") or 0)
    except Exception:  # noqa: BLE001 - enrichment is best-effort
        pass


# a real live memecoin market shows two-sided flow; vaults/bridge pools show ~1 buy/1 sell in 24h and
# outrank the real coin on raw liquidity, so filter to ACTIVE markets first, THEN rank by depth.
MIN_ACTIVE_BUYS = 25
MIN_ACTIVE_SELLS = 15


def _is_active_memecoin(c: dict) -> bool:
    return c["buys"] >= MIN_ACTIVE_BUYS and c["sells"] >= MIN_ACTIVE_SELLS


def _canonical_rank(swarm: list[dict]) -> list[dict]:
    """Canonical = a REAL ACTIVE memecoin market (two-sided flow), ranked by depth. Excludes the huge
    non-memecoin vault/bridge pools that fuzzy-name-match and outrank the real coin on raw liquidity."""
    active = [c for c in swarm if _is_active_memecoin(c)]
    pool = active or swarm   # if nothing is active, fall back so the caller can see the swarm
    return sorted(pool, key=lambda c: (round((c["reserve_usd"] or 0) / 1000), -(c["age_minutes"] or 0)),
                  reverse=True)


def probe(term: str) -> dict:
    swarm = _dexscreener_swarm(term)
    if not swarm:
        return {"term": term, "status": "NO_MATCH", "message": "No Solana pair found for that term."}
    ranked = _canonical_rank(swarm)
    if not any(_is_active_memecoin(c) for c in ranked):
        return {"term": term, "status": "NO_ACTIVE_MARKET", "candidates": ranked[:5],
                "message": "No candidate shows real two-sided trading — the term didn't map to a live "
                           "memecoin market (wrong name, or not tradeable). Abstain."}
    top = ranked[0]
    # ABSTAIN if the #1 and #2 are within ~1.5x on liquidity — the "which clone is real" ambiguity.
    if len(ranked) > 1:
        r1, r2 = ranked[0]["reserve_usd"] or 0, ranked[1]["reserve_usd"] or 0
        if r2 > 0 and r1 / r2 < 1.5 and ranked[1]["mint"] != top["mint"]:
            return {"term": term, "status": "ABSTAIN", "top": top, "runner_up": ranked[1],
                    "candidates": ranked[:5],
                    "message": "Two candidates within margin on liquidity — can't cleanly resolve the "
                               "canonical mint. Abstain (do not fire)."}
    # buyers proxy until enriched
    top.setdefault("buyers", top["buys"])
    top.setdefault("sellers", top["sells"])
    _enrich_buyers(top)
    verdict = screen.screen_coin(top, {"screen": SPEC})
    return {"term": term, "status": "RESOLVED", "mint": top["mint"], "symbol": top.get("symbol"),
            "reserve_usd": top["reserve_usd"], "age_days": round((top["age_minutes"] or 0) / 1440, 1),
            "buyers": top.get("buyers"), "sellers": top.get("sellers"),
            "screen": verdict, "candidates": ranked[:5], "top": top}


def _fmt(c: dict) -> str:
    return (f"{(c.get('symbol') or '?'):<10} liq ${(c['reserve_usd'] or 0):>12,.0f}  "
            f"age {(c['age_minutes'] or 0)/1440:>5.1f}d  {c['buys']}b/{c['sells']}s  {c['mint']}")


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print('usage: python -m scripts.trading_bot.memebot.virality_probe "<viral term>"')
        return 2
    term = " ".join(argv)
    r = probe(term)
    print(f"=== VIRALITY PROBE · {term!r} -> {r['status']} ===")
    for c in r.get("candidates", [])[:5]:
        print("  " + _fmt(c))
    if r["status"] == "RESOLVED":
        v = r["screen"]
        print(f"\nCANONICAL MINT: {r['mint']}  ({r.get('symbol')})")
        print(f"  liquidity ${r['reserve_usd']:,.0f} · age {r['age_days']}d · "
              f"buyers {r['buyers']} · sellers {r['sellers']}")
        passed = v.get("verdict") == "PASS" if isinstance(v, dict) else None
        print(f"  SCREEN: {'✅ PASS' if passed else '🚫 REJECT'}")
        for reason in (v.get("reasons") or []):
            print(f"    - {reason}")
    elif r["status"] == "ABSTAIN":
        print(f"\n{r['message']}")
    else:
        print(f"\n{r.get('message','')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
