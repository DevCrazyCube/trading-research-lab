#!/usr/bin/env python3
"""MEME ARENA — the coverage-VOID gate (BUNDLE_MOMENTUM_V2 must-fix #1). The single PumpPortal listener
subscribes to a mint's trades only AFTER it sees the CREATE, so a subscription-race or reconnect gap can
drop the true early buys. MEASURED: ~41% of bundle candidates show create->first-captured-buy > 5s —
implausible for a real pump.fun launch, meaning on-chain buys 4..9 get scored as buys 1..6, corrupting
BOTH the clump timing AND the wallet-concentration set. That is a pure measurement artifact that reads as
a tradable bundle.

This gate refuses to trade a mint whose first-K buys are not provably complete:
  1. CHEAP buffer gate ($0, no RPC): the buffer's first captured buy must be within MAX_CREATE_GAP_S of the
     create — otherwise the early buys were missed. This alone kills the 41% truncation tail.
  2. RIGOROUS on-chain gate (Helius, at a t0+Δ settlement delay so the early block is indexed): reconstruct
     the true ordered first-K buys on the bonding curve and require the buffer's first-K signatures to match.
Called INSIDE entry_ok, BEFORE any pending entry — a mismatch is a STRATEGY VOID (COVERAGE_VOID), never a trade.
Pure logic + an injectable rpc; hermetically testable.
"""
from __future__ import annotations

MAX_CREATE_GAP_S = 3.0            # buffer's first buy must land within this of the create (subscribe-race guard)
SETTLEMENT_DELAY_S = 8.0         # wait this long after create before trusting a Helius first-K read (indexing lag)


def buffer_gap_ok(create_ns: int | None, first_buy_ns: int | None) -> tuple[bool, str]:
    """The cheap $0 completeness proxy: a real launch's first captured buy is within MAX_CREATE_GAP_S of the
    create. A larger gap means the subscription missed the opening buys."""
    if create_ns is None or first_buy_ns is None:
        return False, "missing create/first-buy timestamp — cannot prove coverage, VOID"
    gap = (first_buy_ns - create_ns) / 1e9
    if gap < 0:
        return False, "first buy precedes create — malformed, VOID"
    if gap <= MAX_CREATE_GAP_S:
        return True, f"create->first-buy gap {gap:.2f}s (<= {MAX_CREATE_GAP_S}s)"
    return False, f"create->first-buy gap {gap:.2f}s (> {MAX_CREATE_GAP_S}s) — subscribe-race dropped early buys, VOID"


def onchain_first_k(bonding_curve: str, k: int, rpc, before: str | None = None) -> list[str]:
    """The true first K signatures on the bonding curve, oldest-first. getSignaturesForAddress returns
    newest-first, so page to the tail and reverse. Returns [] on any read failure (caller treats as VOID)."""
    try:
        collected = []
        cursor = before
        for _ in range(20):                       # bounded pagination
            batch = rpc("getSignaturesForAddress",
                        [bonding_curve, {"limit": 1000, **({"before": cursor} if cursor else {})}]) or []
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < 1000:
                break
            cursor = batch[-1]["signature"]
        ordered = list(reversed(collected))       # oldest-first
        return [s["signature"] for s in ordered[:k]]
    except Exception:  # noqa: BLE001 — a read failure is not coverage; the caller VOIDs
        return []


def coverage_ok(create_ns: int | None, buffer_first_buys: list[dict], k: int,
                bonding_curve: str | None = None, *, rpc=None, now_ns: int | None = None) -> dict:
    """Combined gate. `buffer_first_buys` are the mint's first buys AS CAPTURED (each has received_unix_nanos
    + signature). Returns {ok, reason, checked_onchain}. If `rpc` is given and enough settlement time has
    passed, also require the on-chain first-K to match the buffer's first-K (order-insensitive set match)."""
    if len(buffer_first_buys) < k:
        return {"ok": False, "reason": f"only {len(buffer_first_buys)}/{k} first-buys captured — VOID",
                "checked_onchain": False}
    first_ns = buffer_first_buys[0].get("received_unix_nanos")
    ok, reason = buffer_gap_ok(create_ns, first_ns)
    if not ok:
        return {"ok": False, "reason": reason, "checked_onchain": False}
    # rigorous on-chain cross-check, only once the early block is indexed
    if rpc is not None and bonding_curve and now_ns is not None and create_ns is not None \
            and (now_ns - create_ns) / 1e9 >= SETTLEMENT_DELAY_S:
        chain = set(onchain_first_k(bonding_curve, k, rpc))
        if not chain:
            return {"ok": False, "reason": "on-chain first-K unreadable at settlement — VOID", "checked_onchain": True}
        buf = {b.get("signature") for b in buffer_first_buys[:k]}
        if buf != chain:
            return {"ok": False, "reason": "buffer first-K != on-chain first-K — truncated capture, VOID",
                    "checked_onchain": True}
        return {"ok": True, "reason": "buffer first-K matches on-chain first-K", "checked_onchain": True}
    return {"ok": True, "reason": reason + " (buffer-gate only; on-chain check deferred)", "checked_onchain": False}


if __name__ == "__main__":
    GAP = int(MAX_CREATE_GAP_S * 1e9)
    # cheap gate
    assert buffer_gap_ok(1_000_000_000_000, 1_000_000_000_000 + GAP - 1)[0]        # within gap
    assert not buffer_gap_ok(1_000_000_000_000, 1_000_000_000_000 + GAP + 10 ** 9)[0]  # > gap -> VOID
    assert not buffer_gap_ok(None, 1)[0]
    # too few buys -> VOID
    assert not coverage_ok(1_000, [{"received_unix_nanos": 1_000, "signature": "a"}], 6)["ok"]
    # buffer gate passes, no rpc -> ok (on-chain deferred)
    buys = [{"received_unix_nanos": 1_000_000_000_000 + i, "signature": f"s{i}"} for i in range(6)]
    r = coverage_ok(1_000_000_000_000, buys, 6)
    assert r["ok"] and not r["checked_onchain"], r
    # on-chain MATCH -> ok
    now = 1_000_000_000_000 + int(SETTLEMENT_DELAY_S * 1e9) + 1
    def match_rpc(meth, params): return [{"signature": f"s{i}"} for i in range(5, -1, -1)]   # newest-first
    rm = coverage_ok(1_000_000_000_000, buys, 6, "bc", rpc=match_rpc, now_ns=now)
    assert rm["ok"] and rm["checked_onchain"], rm
    # on-chain MISMATCH: the buffer MISSED the true early buys (it captured s4..s9; chain's first are s0..s9)
    trunc_buys = [{"received_unix_nanos": 1_000_000_000_000 + i, "signature": f"s{i}"} for i in range(4, 10)]
    def trunc_rpc(meth, params): return [{"signature": f"s{i}"} for i in range(9, -1, -1)]   # 10 real, oldest s0
    rt = coverage_ok(1_000_000_000_000, trunc_buys, 6, "bc", rpc=trunc_rpc, now_ns=now)
    assert not rt["ok"] and rt["checked_onchain"], rt   # chain first-6 {s0..s5} != buffer {s4..s9}
    print("helius_coverage.py self-check OK: create-gap VOID, too-few VOID, on-chain first-K match/mismatch")
