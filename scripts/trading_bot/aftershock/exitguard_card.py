#!/usr/bin/env python3
"""ExitGuard — the B20B exitability "safety card" for a single mint (the product's core value).

Given a pump.fun mint, return an honest card: is it EXITABLE, or is it a concentration rug where one
wallet holds essentially everything bought in the first 60 slots (B20B: "nobody else showed up → no
external money to exit into")? Reuses the leakage-audited, live-validated screen (pac_lws_screen /
b20b) BYTE-FOR-BYTE — no new model. Read-only, no wallet, no orders.

MVP data source: the LOCAL creation-anchored feed we already capture (pac_lws_feed). A mint that just
launched and is in our registry+feed gets an instant card from its true [t0, t0+60] window. Arbitrary
older mints (not in the recent window) return status=UNAVAILABLE — an on-demand Helius backfill for
those is the documented follow-on, not needed to test the funnel.
"""
from __future__ import annotations

import json
import pathlib

from . import pac_lws_screen as screen

ROOT = pathlib.Path(__file__).resolve().parents[3]
FEED_EVENTS = ROOT / "research/data/aftershock/pac_lws/feed_events.jsonl"
CREATION_REGISTRY = ROOT / "research/data/aftershock/pac_lws/creation_registry.jsonl"

# how far back in the append-only feed we look for a pasted mint's window (recent launches only)
_SCAN_BYTES = 64 * 1024 * 1024          # tail of the (large) feed to scan
_VTOK_OFFSET = 279_900_000_000_000
_CURVE_K = 30_000_000_000 * 1_073_000_000_000_000
_TOTAL_SUPPLY_ATOMS = 1_000_000_000_000_000


def _market_cap_sol(real_token) -> float:
    try:
        rt = int(real_token)
        if rt <= 0:
            return 0.0
        vtok = rt + _VTOK_OFFSET
        return (_CURVE_K // vtok / vtok) * _TOTAL_SUPPLY_ATOMS / 1e9
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _registry_lookup(mint: str, path: pathlib.Path = CREATION_REGISTRY) -> dict | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if mint in line:
                    try:
                        row = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if row.get("mint") == mint:
                        return row
    except OSError:
        return None
    return None


def _mint_trades(mint: str, path: pathlib.Path = FEED_EVENTS) -> list[dict]:
    """The mint's decoded trades from the feed tail (recent launches)."""
    out = []
    try:
        with path.open("rb") as fh:
            size = fh.seek(0, 2)
            fh.seek(max(0, size - _SCAN_BYTES))
            data = fh.read()
    except OSError:
        return out
    for raw in data.split(b"\n"):
        if not raw.strip() or mint.encode() not in raw:
            continue
        try:
            row = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if row.get("mint") == mint:
            out.append(row)
    return out


def card(mint: str, *, registry_path: pathlib.Path = CREATION_REGISTRY,
         feed_path: pathlib.Path = FEED_EVENTS) -> dict:
    """Return the exitability card for `mint`. Never raises; returns status=UNAVAILABLE if not captured."""
    if not isinstance(mint, str) or not (32 <= len(mint) <= 48) or not mint.isalnum():
        return {"mint": mint, "status": "INVALID", "message": "That doesn't look like a mint address."}
    reg = _registry_lookup(mint, registry_path)
    if reg is None or not isinstance(reg.get("t0_slot"), int):
        return {"mint": mint, "status": "UNAVAILABLE",
                "message": "Not in the fresh-launch window I track yet. Paste a mint within its first "
                           "minute of launch for an instant exitability check."}
    t0 = reg["t0_slot"]
    trades = _mint_trades(mint, feed_path)
    window = [screen.WindowTrade(slot=e["slot"], trader=e["trader"], is_buy=e["is_buy"],
                                 token_amount=e["token_amount"],
                                 reserve_delta_tokens=e.get("reserve_delta_tokens"))
              for e in trades if isinstance(e.get("slot"), int) and t0 <= e["slot"] <= t0 + screen.K_SLOTS]
    latest_rt = next((e["post_real_token"] for e in reversed(trades)
                      if isinstance(e.get("post_real_token"), int)), None)
    if len(window) < 2 and not any(e["slot"] > t0 + screen.K_SLOTS for e in trades):
        return {"mint": mint, "status": "TOO_FRESH", "t0_slot": t0,
                "message": "Just launched — the 60-slot exitability window (~24s) hasn't closed yet. "
                           "Re-check in about half a minute."}
    v = screen.evaluate(window, t0_slot=t0, dev_wallet=reg.get("dev_wallet"))
    buyers = v.buyers
    top_pct = v.top_share_bps / 100.0
    mcap = round(_market_cap_sol(latest_rt), 1) if latest_rt else None
    tradeable = v.status == screen.SURVIVED
    if v.status == screen.VETO_CONCENTRATION:
        head = "🚫 UNEXITABLE — concentration rug risk"
        body = (f"One wallet holds {top_pct:.1f}% of everything bought in the first 60 slots. "
                f"Nobody else showed up — there is no external money to sell into. B20B flags this as a "
                f"guaranteed-loss trap.")
    elif v.status == screen.SURVIVED:
        head = "✅ EXITABLE — passed the rug screen"
        body = (f"{buyers} distinct early buyers, top wallet {top_pct:.1f}%. It cleared the leakage-audited "
                f"concentration screen — there IS external liquidity to exit into. Not a promise it pumps, "
                f"just that you can get out.")
    elif v.status == screen.UNREADABLE:
        head = "⚠️ UNREADABLE — too few buyers to score"
        body = "Fewer than 2 distinct buyers in the window — the screen can't judge it. Treat as high risk."
    else:
        head = "⚠️ NO NET BUYING"
        body = "No net token accumulation in the window. Nothing to score."
    return {"mint": mint, "status": v.status, "t0_slot": t0, "buyers": buyers,
            "top_share_pct": round(top_pct, 2), "mcap_sol": mcap, "tradeable": tradeable,
            "headline": head,
            "message": f"{head}\n{body}\n\nmint: {mint}"}
