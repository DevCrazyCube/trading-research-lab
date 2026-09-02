#!/usr/bin/env python3
"""MEME ARENA — the RUG arbiter. Fixes the RUG_UNPRICED false-loss bug: a position going unpriceable (3
consecutive no-price / DEAD_SILENCE) was scored as a −100% total loss, but the empirical ground truth is
that the 6 virality "rugs" were DexScreener PRICE-UNAVAILABILITY, not real on-chain rugs.

This is a bounded ONE-SHOT sidecar (never an in-loop crawl): given a mint (and, when known, its liquidity
account — the bonding curve or PumpSwap pool), it asks Helius the only question that matters for honesty —
is the on-chain LIQUIDITY actually gone? It resolves to exactly one of:

  RUG_CONFIRMED       — positively dead: the liquidity account is drained to dust AND there is no recent
                        on-chain trading. Book a real −100% PRIMARY loss (F1 satisfied).
  MEASUREMENT_VOID    — positively alive: recent on-chain trades exist and/or real liquidity remains, so the
                        price feed was down, not the coin. Right-censored, EXCLUDED from primary N.
  INDETERMINATE_VOID  — Helius itself could not read: a measurement failure, never fabricated as a rug.

HONESTY NOTE (must be surfaced, not hidden): right-censoring is NOT independent of outcome — an unpriceable
coin is somewhat more likely to be a genuine rug — so the runtime pre-registers `censored_fraction` as a
validity gate and reports the censored cohort's would-be returns as a sensitivity bound. This arbiter only
decides alive-vs-dead from POSITIVE on-chain evidence in each direction; it never guesses.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.request

LAMPORTS_PER_SOL = 1_000_000_000
DUST_SOL = 0.15                 # liquidity at/below this = drained (a $10 exit cannot land)
LIVE_MIN_TXNS = 3               # this many on-chain txns in the recent window = the market is alive
RECENT_WINDOW_S = 20 * 60       # "recent" = last 20 minutes
RPC_TIMEOUT = 9.0


def _env_key() -> str:
    key = os.environ.get("HELIUS_API_KEY", "").strip()
    if key:
        return key
    try:
        for line in (pathlib.Path(__file__).resolve().parents[4] / ".env").read_text().splitlines():
            if line.startswith("HELIUS_API_KEY="):
                return line.partition("=")[2].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _helius_rpc(method: str, params: list):
    key = _env_key()
    if not key:
        raise RuntimeError("HELIUS_API_KEY absent")
    req = urllib.request.Request(
        "https://mainnet.helius-rpc.com/?api-key=" + key,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=RPC_TIMEOUT) as r:
        return json.loads(r.read()).get("result")


def classify_unpriced(mint: str, liquidity_account: str | None = None,
                      last_good_mark_ns: int | None = None, *, rpc=_helius_rpc, now_ns=None) -> dict:
    """Decide whether an unpriceable position is a real rug or a measurement failure, from Helius. `rpc` is
    injectable for hermetic tests."""
    now_ns = now_ns if now_ns is not None else time.time_ns()
    out = {"mint": mint, "reserve_sol": None, "recent_txns": None}

    # 1. recent on-chain activity on the liquidity account (or the mint) = positively ALIVE
    probe = liquidity_account or mint
    try:
        sigs = rpc("getSignaturesForAddress", [probe, {"limit": 25}]) or []
    except Exception as exc:  # noqa: BLE001 — Helius unreadable is a measurement failure, never a rug
        return {**out, "verdict": "INDETERMINATE_VOID", "reason": f"helius unreadable: {str(exc)[:80]}"}
    cutoff = (now_ns / 1e9) - RECENT_WINDOW_S
    recent = sum(1 for s in sigs if (s.get("blockTime") or 0) >= cutoff)
    out["recent_txns"] = recent
    if recent >= LIVE_MIN_TXNS:
        return {**out, "verdict": "MEASUREMENT_VOID",
                "reason": f"{recent} on-chain txns in the last {RECENT_WINDOW_S//60}min — the coin is alive; "
                          "the price feed was down, not the market"}

    # 2. no recent trading -> is the liquidity actually drained? need the account balance to say RUG.
    if liquidity_account is None:
        return {**out, "verdict": "INDETERMINATE_VOID",
                "reason": "no recent txns but no liquidity account to confirm drain — will not fabricate a rug"}
    try:
        bal = rpc("getBalance", [liquidity_account])
        lamports = bal.get("value") if isinstance(bal, dict) else bal
        reserve_sol = (lamports or 0) / LAMPORTS_PER_SOL
    except Exception as exc:  # noqa: BLE001
        return {**out, "verdict": "INDETERMINATE_VOID", "reason": f"balance unreadable: {str(exc)[:80]}"}
    out["reserve_sol"] = round(reserve_sol, 4)
    if reserve_sol <= DUST_SOL:
        return {**out, "verdict": "RUG_CONFIRMED",
                "reason": f"no recent trades AND liquidity drained to {reserve_sol:.3f} SOL (<= {DUST_SOL}) — "
                          "positively dead"}
    return {**out, "verdict": "MEASUREMENT_VOID",
            "reason": f"quiet but {reserve_sol:.2f} SOL liquidity remains — not a rug; price feed was down"}


if __name__ == "__main__":
    # hermetic: mock the rpc to cover all three verdicts
    def alive_rpc(method, params):
        if method == "getSignaturesForAddress":
            return [{"blockTime": int(time.time()) - 60} for _ in range(5)]   # 5 fresh txns
        return {"value": 20 * LAMPORTS_PER_SOL}
    def dead_rpc(method, params):
        if method == "getSignaturesForAddress":
            return [{"blockTime": int(time.time()) - 9 * 3600}]               # only a stale txn
        return {"value": int(0.02 * LAMPORTS_PER_SOL)}                        # drained to 0.02 SOL
    def broken_rpc(method, params):
        raise RuntimeError("429 rate limited")

    a = classify_unpriced("m", "pool", rpc=alive_rpc)
    assert a["verdict"] == "MEASUREMENT_VOID", a
    d = classify_unpriced("m", "pool", rpc=dead_rpc)
    assert d["verdict"] == "RUG_CONFIRMED" and d["reserve_sol"] <= DUST_SOL, d
    b = classify_unpriced("m", "pool", rpc=broken_rpc)
    assert b["verdict"] == "INDETERMINATE_VOID", b
    n = classify_unpriced("m", None, rpc=dead_rpc)   # no liquidity account + no recent trades -> won't guess
    assert n["verdict"] == "INDETERMINATE_VOID", n
    print("helius_rug_arbiter.py self-check OK: alive->VOID, drained->RUG_CONFIRMED, unreadable->INDETERMINATE, "
          "no-account->won't-fabricate")
