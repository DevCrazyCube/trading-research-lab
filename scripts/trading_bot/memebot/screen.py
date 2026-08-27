#!/usr/bin/env python3
"""The screen -- a fast, deterministic red-flag filter. PASS / REJECT + reasons. No LLM per coin.

This is the loss-AVOIDANCE half of the thesis, and the ONLY part of the whole memecoin programme that
survived a leakage audit: B20B, the deadness screen. B20B's exact rule is:

    At t0+60 slots, the single largest buyer's share of all tokens bought so far >= 0.95 -> DO NOT
    ENTER (nobody else showed up; there is no external money to exit into).

That rule needs a per-wallet on-chain decode (pump TradeEvent amounts + buyer identity) which the free
REST feed does NOT expose. So this module does NOT claim to run frozen-B20B; it runs a documented
PROXY for its mechanism -- "did anybody else show up?" -- from the fields the free feed does give
(unique buyers, buys, sellers), plus the trader's-checklist red flags (min market cap, min liquidity,
bundle/wash proxy, honeypot proxy). Frozen-B20B stays the gold standard, running out-of-sample via the
b11m window-2 decode; this proxy is the tradable-today stand-in, and README/PREREG say so plainly.

Deterministic and cheap: pure arithmetic on one feed snapshot, no network, no model.
"""

from __future__ import annotations


def screen_coin(coin: dict, spec: dict) -> dict:
    """Return {verdict: PASS|REJECT, reasons: [...], metrics: {...}} for one feed snapshot."""
    s = spec["screen"]
    reasons: list[str] = []

    fdv = coin.get("fdv_usd")
    reserve = coin.get("reserve_usd")
    buyers = coin.get("buyers") or 0
    buys = coin.get("buys") or 0
    sellers = coin.get("sellers") or 0
    age = coin.get("age_minutes")
    dex = str(coin.get("dex") or "").strip().lower()

    buys_per_buyer = (buys / buyers) if buyers > 0 else (float("inf") if buys > 0 else 0.0)

    # 0. Optional experiment scope.  A venue exclusion is not a failed trade and must not enter the
    # control-null either; bot.scan_once treats this reason as an out-of-scope observation.  EXIT_V2 uses
    # it because its predecessor accidentally selected 100% non-Pump PASS trades and therefore did not
    # test the Pump.fun question at all.
    allowed_dexes = {str(x).strip().lower() for x in s.get("allowed_dexes", [])}
    if allowed_dexes and dex not in allowed_dexes:
        reasons.append(f"REJECT_OUT_OF_SCOPE_VENUE: dex {dex or 'missing'} not in "
                       f"{sorted(allowed_dexes)}")

    # 1. Min market cap (checklist ~$7k). A sub-floor FDV is a not-yet-real / dust launch.
    if fdv is None:
        reasons.append("REJECT_NO_FDV: feed exposes no FDV; refuse rather than guess")
    elif fdv < s["min_fdv_usd"]:
        reasons.append(f"REJECT_MIN_FDV: fdv ${fdv:,.0f} < floor ${s['min_fdv_usd']:,.0f}")

    # 2. Min liquidity -- you cannot exit into a reserve that is not there.
    if reserve is None:
        reasons.append("REJECT_NO_RESERVE: feed exposes no USD reserve; refuse rather than guess")
    elif reserve < s["min_reserve_usd"]:
        reasons.append(f"REJECT_MIN_LIQUIDITY: reserve ${reserve:,.0f} < floor ${s['min_reserve_usd']:,.0f}")

    # 3. DEADNESS PROXY (the B20B mechanism, adapted): "did anybody else show up?" Too few UNIQUE
    #    buyers means you would be an early lone bag-holder with no external money to exit into --
    #    exactly the unexitability B20B's largest-buyer-share catches on-chain.
    if buyers < s["min_unique_buyers"]:
        reasons.append(f"REJECT_DEADNESS_PROXY: only {buyers} unique buyers < "
                       f"{s['min_unique_buyers']} (proxy for B20B 'nobody else showed up')")

    # 4. BUNDLE / WASH proxy (fee-vs-mcap mismatch analog): many buys concentrated in few wallets is
    #    the signature of a bundled/self-funded launch the checklist warns about.
    if buys_per_buyer > s["max_buys_per_buyer"]:
        reasons.append(f"REJECT_BUNDLE_PROXY: {buys_per_buyer:.1f} buys/buyer > "
                       f"{s['max_buys_per_buyer']} (few wallets, many buys)")

    # 5. HONEYPOT proxy: sustained buying with NObody able/willing to sell = a one-way trap.
    if buys >= s["honeypot_min_buys"] and sellers == 0:
        reasons.append(f"REJECT_HONEYPOT_PROXY: {buys} buys but 0 sellers (no exit observed)")

    # 6. Only enter FRESH launches -- the edge (if any) is in the first minutes; stale pools are
    #    someone else's trade already in progress.
    if age is not None and age > s["max_pool_age_minutes"]:
        reasons.append(f"REJECT_STALE: pool age {age:.0f}m > {s['max_pool_age_minutes']}m")

    # 7. EXITABILITY-FIRST (optional; only enforced when the spec sets it). The unexitable dump is where
    #    the money dies (verified on-chain: silent coins drain to ~0 liquidity, -64% to -100%). The
    #    honeypot rule (5) only catches the ZERO-seller extreme; this is the positive form: DON'T BUY
    #    WHAT NOBODY HAS SOLD. Requiring >= min_sellers demonstrated exits is the free-feed, tradable-
    #    today stand-in for B20B's "is there external money to exit into?" -- if N wallets already sold
    #    successfully, an exit path exists right now. Pair with a high reserve floor (rule 2) for depth.
    min_sellers = s.get("min_sellers")
    if min_sellers is not None and sellers < min_sellers:
        reasons.append(f"REJECT_NOT_EXITABLE: only {sellers} sellers < {min_sellers} "
                       f"(no proven exit path -- don't buy what nobody has sold)")

    verdict = "PASS" if not reasons else "REJECT"
    return {
        "verdict": verdict,
        "reasons": reasons or ["PASS: no red flag on the free-feed proxies"],
        "metrics": {
            "fdv_usd": fdv, "reserve_usd": reserve, "buyers": buyers, "buys": buys,
            "sellers": sellers, "dex": dex or None, "buys_per_buyer": round(buys_per_buyer, 3)
            if buys_per_buyer != float("inf") else None, "age_minutes": age,
        },
    }
