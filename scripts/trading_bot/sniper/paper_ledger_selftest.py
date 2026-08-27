#!/usr/bin/env python3
"""Hermetic checks for the append-only sniper V2 ledger.  No network, wallet or orders."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .execution import DryRunExecutor
from .paper_ledger import (append_event, invalidate_unresolved, ledger_summary,
                           make_entry_event, make_resolution_event)
from .strategy import ConvexityStrategy, PRESETS
from .types import Bar, EntrySignal


def _signal(mint: str, ts: float = 1.0) -> EntrySignal:
    return EntrySignal(mint=mint, ts=ts, ref_price_usd=1.0, surge_bps=300.0,
                       buy_frac=0.9, liq_usd_per_s=5000.0, venue="Pumpfun", reason="selftest")


def _open(strategy: ConvexityStrategy, ex: DryRunExecutor, mint: str):
    sig = _signal(mint)
    intent = strategy.on_signal(sig)
    assert intent is not None
    pos = strategy.apply_fill(ex.execute(intent, liq_usd_per_s=sig.liq_usd_per_s))
    assert pos is not None
    payload = strategy.freeze_payload(intent, pos.meta["frozen_utc"], sig)
    entry = make_entry_event(variant="v2_test", preset="convex_core", position=pos, signal=sig,
                             frozen_payload=payload, strategy_config=strategy.cfg, executor=ex)
    return pos, entry


def run_selftest() -> int:
    path = Path(tempfile.mkdtemp(prefix="sniper_v2_ledger_")) / "events.jsonl"
    clock = lambda: datetime(2026, 8, 27, tzinfo=timezone.utc)  # noqa: E731
    ex = DryRunExecutor()

    s1 = ConvexityStrategy(PRESETS["convex_core"], clock=clock)
    pos1, entry1 = _open(s1, ex, "MINT_RESOLVED")
    assert entry1["commitment_recomputable"] and entry1["full_loss_stress_r"] < -1.0
    append_event(path, entry1)
    bar = Bar(t=30, o=1.0, h=1.0, l=0.3, c=0.3, v=1000.0, buys=1, sells=10,
              buy_vol=10.0, sell_vol=990.0, dex="Pumpfun")
    intent = s1.on_bar(pos1.mint, bar)[0]
    closed = s1.apply_fill(ex.execute(intent, liq_usd_per_s=1000.0))
    append_event(path, make_resolution_event(variant="v2_test", preset="convex_core",
                                             position=closed, entry_event=entry1))

    s2 = ConvexityStrategy(PRESETS["convex_core"], clock=clock)
    _pos2, entry2 = _open(s2, ex, "MINT_RESTARTED")
    append_event(path, entry2)
    added = invalidate_unresolved(path)
    assert len(added) == 1 and added[0]["resolution_reason"] == "INVALID_RESTART_GAP"
    assert invalidate_unresolved(path) == [], "restart invalidation must be idempotent"

    summary = ledger_summary(path)
    assert summary["entries"] == 2 and summary["terminal"] == 2 and summary["open"] == 0
    assert summary["restart_invalidations"] == 1 and summary["commitment_failures"] == 0
    assert len(summary["reported_r"]) == 1 and len(summary["stress_r"]) == 2
    assert summary["adjudication_equity_usd"] < 1000.0
    restored = ConvexityStrategy(PRESETS["convex_core"], clock=clock)
    restored.restore_equity_usd(summary["adjudication_equity_usd"])
    next_intent = restored.on_signal(_signal("MINT_AFTER_RESTART", 50.0))
    assert next_intent is not None and next_intent.usd_size < 20.0
    print("SNIPER V2 LEDGER SELFTEST PASS", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_selftest())
