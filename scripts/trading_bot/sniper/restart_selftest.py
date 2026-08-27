#!/usr/bin/env python3
"""Offline selftest for the RESTART-PROOF open book (P0): a persisted OPEN entry is REOPENED after a
restart (not censored/charged a full-loss gap), with peak/flow restored, and resolves against live bars.

    python -m scripts.trading_bot.sniper.restart_selftest
"""
from __future__ import annotations

import tempfile
import pathlib

from .strategy import ConvexityStrategy, PRESETS
from .execution import DryRunExecutor
from .types import EntrySignal, Bar
from . import paper_ledger as PL


def _open_one(strat, ex, mint="MINT", price=1e-6):
    sig = EntrySignal(mint=mint, ts=100.0, ref_price_usd=price, surge_bps=400, buy_frac=0.7,
                      liq_usd_per_s=100.0, venue="pumpfun", reason="test-surge")
    intent = strat.on_signal(sig)
    fill = ex.execute(intent, liq_usd_per_s=sig.liq_usd_per_s)
    pos = strat.apply_fill(fill)
    return pos, sig, intent


def _entry_event(pos, sig, intent, strat, ex):
    payload = strat.freeze_payload(intent, str(pos.meta["frozen_utc"]), sig)
    return PL.make_entry_event(variant="t", preset="convex_core", position=pos, signal=sig,
                               frozen_payload=payload, strategy_config=strat.cfg, executor=ex)


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def main() -> int:
    ok = True
    ex = DryRunExecutor()

    # Build a real open position + its persisted entry event.
    s1 = ConvexityStrategy(config=PRESETS["convex_core"])
    pos, sig, intent = _open_one(s1, ex)
    ev = _entry_event(pos, sig, intent, s1, ex)
    entry_price = pos.entry.price_usd

    # 1. Reopen into a fresh strategy (no mark) -> at entry price, flagged reopened.
    s2 = ConvexityStrategy(config=PRESETS["convex_core"])
    s2.restore_equity_usd(1000.0)
    r = s2.reopen_position(ev, None)
    ok &= _check("reopen (no mark) -> in book at entry price, reopened",
                 r is not None and r.mint in s2._open and abs(r.peak_price - entry_price) < 1e-18
                 and r.meta["reopened"], (f"peak={r.peak_price}" if r else "None"))

    # 2. Reopen WITH a mark (peak up, flow streak 3) -> peak + streak restored.
    pos.peak_price = entry_price * 2.0
    pos.meta["flow_below_streak"] = 3
    mark = PL.make_mark_event(variant="t", preset="convex_core", position=pos)
    s3 = ConvexityStrategy(config=PRESETS["convex_core"])
    s3.restore_equity_usd(1000.0)
    r3 = s3.reopen_position(ev, mark)
    ok &= _check("reopen WITH mark -> peak + flow streak restored",
                 r3 is not None and abs(r3.peak_price - entry_price * 2.0) < 1e-18
                 and r3.meta["flow_below_streak"] == 3)

    # 3. Idempotency: a second reopen for the same mint returns None.
    ok &= _check("reopen is idempotent (same mint twice -> None)",
                 s3.reopen_position(ev, mark) is None)

    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "live_events_t.jsonl"
        # 4. reload_open_entries: entry + mark -> one open record with the mark; +resolution -> zero.
        PL.append_event(path, ev)
        PL.append_event(path, mark)
        recs = PL.reload_open_entries(path)
        ok &= _check("reload_open_entries: open entry paired with its mark",
                     len(recs) == 1 and recs[0]["mark"] is not None
                     and recs[0]["entry"]["frozen_sha256"] == ev["frozen_sha256"])
        PL.append_event(path, {"schema_version": 2, "kind": "resolution", "status": "RESOLVED",
                               "frozen_sha256": ev["frozen_sha256"], "realized_r": 1.0,
                               "stress_realized_r": 1.0, "event_id": "x"})
        ok &= _check("reload_open_entries: resolved entry no longer returned",
                     len(PL.reload_open_entries(path)) == 0)

        # 5. Restart-gap honesty: a malformed entry can't reopen -> narrowed invalidate charges ONLY it.
        bad = dict(ev, entry_fill={"bogus": 1}, frozen_sha256="BAD" + ev["frozen_sha256"][:8])
        path2 = pathlib.Path(td) / "live_events_bad.jsonl"
        PL.append_event(path2, ev)      # a reconstructable sibling
        PL.append_event(path2, bad)     # the malformed one
        s4 = ConvexityStrategy(config=PRESETS["convex_core"]); s4.restore_equity_usd(1000.0)
        failed = []
        for rec in PL.reload_open_entries(path2):
            if s4.reopen_position(rec["entry"], rec["mark"]) is None:
                failed.append(str(rec["entry"].get("frozen_sha256")))
        added = PL.invalidate_unresolved(path2, only=set(failed))
        ok &= _check("malformed entry -> reopen None -> narrowed invalidate charges only it",
                     len(added) == 1 and added[0]["frozen_sha256"] == bad["frozen_sha256"]
                     and added[0]["resolution_reason"] == "INVALID_RESTART_GAP",
                     f"failed={failed} added={len(added)}")

    # 6. Round-trip: a reopened position resolves against live bars (a catastrophe bar trips an exit).
    s5 = ConvexityStrategy(config=PRESETS["convex_core"]); s5.restore_equity_usd(1000.0)
    s5.reopen_position(ev, None)
    crash = Bar(t=200, o=entry_price, h=entry_price, l=entry_price * 0.1, c=entry_price * 0.1,
                v=100.0, buys=1, sells=9, buy_vol=10.0, sell_vol=90.0)
    intents = s5.on_bar("MINT", crash)
    ok &= _check("reopened position resolves against live bars (exit intent on a crash bar)",
                 len(intents) >= 1 and intents[0].side == "sell")

    print("\nRESTART SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
