#!/usr/bin/env python3
"""ExitGuard Telegram bot — paste a mint, get the honest B20B exitability card; on a PASS, a
referral-coded one-click Buy deep-link. The free rug-check card is the value + the forwardable object;
the referral fee-share on swaps-that-happen-anyway is the revenue. Read-only: no wallet, no orders, no
custody — the Buy happens inside the user's own trading bot via a deep-link.

Stdlib only (urllib long-poll of the Telegram Bot API). Runs ONLY when the operator supplies their own
credentials via env — nothing outward-facing happens without them:
    EXITGUARD_BOT_TOKEN   — from @BotFather (create a bot, 2 min, free)
    EXITGUARD_REF_TEMPLATE — the Buy deep-link template for the operator's referral, with {mint} and
                             {ref}, e.g. "https://t.me/solana_trojanbot?start={ref}-{mint}"
    EXITGUARD_REF_CODE    — the operator's referral code registered with that bot (free, no KYC)

The card leads with the honest safety verdict; the Buy CTA appears only on a SURVIVED (exitable) card,
never on a VETO/UNREADABLE — we do not route a buy into a token our own screen calls a rug.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

from . import exitguard_card as eg

API = "https://api.telegram.org/bot{token}/{method}"
_MINT_CHARS = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")   # base58


def _call(token: str, method: str, params: dict, timeout: float = 65.0) -> dict:
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API.format(token=token, method=method), data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:  # noqa: BLE001 — a transient network hiccup must not kill the loop
        return {"ok": False, "error": str(exc)[:160]}


def _find_mint(text: str) -> str | None:
    """Extract a plausible base58 Solana mint from a pasted message."""
    for token in text.replace("\n", " ").split():
        token = token.strip().strip(".,!?()[]<>\"'")
        if 32 <= len(token) <= 48 and all(c in _MINT_CHARS for c in token):
            return token
    return None


def _buy_cta(mint: str) -> str:
    template = os.environ.get("EXITGUARD_REF_TEMPLATE")
    ref = os.environ.get("EXITGUARD_REF_CODE", "")
    if not template:
        return ""
    try:
        link = template.format(mint=mint, ref=ref)
    except (KeyError, IndexError):
        return ""
    return f"\n\n➡️ One-click Buy (exitable): {link}"


def _reply_for(text: str) -> str | None:
    mint = _find_mint(text or "")
    if mint is None:
        if text and text.strip().lower() in ("/start", "start", "help", "/help"):
            return ("👋 ExitGuard — free t0 rug-exitability check.\n"
                    "Paste any fresh pump.fun mint and I'll tell you, from the first 60 slots on-chain, "
                    "whether one wallet holds everything (an unexitable rug) or there's real liquidity to "
                    "get out of. Leakage-audited B20B screen, no hype.")
        return None
    c = eg.card(mint)
    msg = c.get("message", "Couldn't read that mint.")
    if c.get("tradeable"):
        msg = msg.rstrip() + _buy_cta(mint)
    return msg


def run(token: str) -> int:
    offset = 0
    print("ExitGuard bot: long-polling Telegram (Ctrl-C to stop)", flush=True)
    while True:
        upd = _call(token, "getUpdates", {"offset": offset, "timeout": 55}, timeout=65.0)
        if not upd.get("ok"):
            time.sleep(3)
            continue
        for u in upd.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message") or u.get("channel_post") or {}
            chat = (msg.get("chat") or {}).get("id")
            text = msg.get("text") or ""
            if chat is None:
                continue
            reply = _reply_for(text)
            if reply:
                _call(token, "sendMessage",
                      {"chat_id": chat, "text": reply, "disable_web_page_preview": "true"})


def main() -> int:
    token = os.environ.get("EXITGUARD_BOT_TOKEN")
    if not token:
        print("EXITGUARD_BOT_TOKEN is not set. Create a bot with @BotFather (free, ~2 min), then run:\n"
              "  EXITGUARD_BOT_TOKEN=... EXITGUARD_REF_TEMPLATE='https://t.me/<bot>?start={ref}-{mint}' "
              "EXITGUARD_REF_CODE=... python3 -m scripts.trading_bot.aftershock.exitguard_bot")
        return 2
    return run(token) or 0


if __name__ == "__main__":
    raise SystemExit(main())
