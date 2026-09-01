#!/usr/bin/env python3
"""MEME ARENA — the runtime driver. ONE feed pull per cycle, fanned out to every registered arm; each arm
services its open positions (mark -> convex exit -> honest fill -> hash-chained ledger) and then opens new
positions its frozen entry predicate accepts. No wallet, no orders — a paper forward measurement whose
verdict is the cluster-bootstrap scorer's PASS/KILL per arm.

    python -m scripts.trading_bot.memebot.arena.runtime            # loop (detached via the watchdog)
    python -m scripts.trading_bot.memebot.arena.runtime --once     # one cycle
    python -m scripts.trading_bot.memebot.arena.runtime --report   # per-arm verdict
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import time

from . import exit_engine as EX
from . import scorer as SC
from .chainledger import ChainLedger
from .hub import Hub

ROOT = pathlib.Path(__file__).resolve().parents[4]
DATA = ROOT / "research" / "data" / "arena"
POLL_SECONDS = 150
HISTORY = 6


def _registered_arms():
    from .arms.virality_arrival import ARM as VIRALITY
    return [VIRALITY]                      # ARM 2 (Codex) / ARM 3 (owner-gated) register here when built


def _load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value))
    tmp.replace(path)


def _ledger(arm) -> ChainLedger:
    return ChainLedger(DATA / arm.instrument / "ledger.jsonl", arm.instrument,
                       arm.code_sha256(), arm.prereg_sha256(), arm.spec_sha256())


def _day(ts: float) -> str:
    return dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def service_arm(arm, feed: dict, hub: Hub) -> dict:
    state = _load(DATA / arm.instrument / "state.json", {"open": {}, "hist": {}, "first_seen": {}})
    ledger = _ledger(arm)
    ledger.ensure_genesis()
    now = time.time()
    opened = closed = 0

    # 1. service open positions on their own pinned market
    for mint, pos in list(state["open"].items()):
        c = hub.refresh_pair(pos["pair"]) if pos.get("pair") else feed.get(mint)
        mark = c["price"] if (c and c.get("price")) else None
        p = EX.Position(mint=mint, arm=arm.instrument, basis=arm.fill_basis,
                        entry_price=pos["entry_price"], opened_ts=pos["opened_ts"], peak=pos["peak"])
        reason = EX.exit_signal(p, mark, now)
        pos["peak"] = p.peak                                   # persist the updated peak
        if reason is None and mark is None:
            reason = "RUG_UNPRICED" if now - pos["opened_ts"] > 3 * 3600 else None
        if reason:
            row = EX.resolve(p, reason, exit_mark=mark, now_ts=now)
            row["entry_day"] = pos.get("entry_day")
            row["minutes_since_first_seen"] = pos.get("entry_delay_min")   # F6 mirage split
            ledger.append_resolved(row)
            del state["open"][mint]
            closed += 1

    # 2. update per-mint history + first-seen
    for mint, c in feed.items():
        state["first_seen"].setdefault(mint, now)
        h = state["hist"].setdefault(mint, [])
        h.append({"t": now, "m5_buys": c.get("m5_buys", 0), "m5_sells": c.get("m5_sells", 0),
                  "price": c.get("price")})
        del h[:-HISTORY]

    # 3. offer candidates to the frozen entry predicate
    for c in arm.candidates(feed):
        mint = c["mint"]
        if mint in state["open"]:
            continue
        hist = state["hist"].get(mint, [])[:-1]                # exclude the just-appended current obs
        if arm.entry_ok(c, hist):
            state["open"][mint] = {
                "entry_price": c["price"], "peak": c["price"], "opened_ts": now, "pair": c.get("pair"),
                "entry_day": _day(now),
                "entry_delay_min": round((now - state["first_seen"].get(mint, now)) / 60.0, 1)}
            opened += 1

    # prune stale history
    state["hist"] = {m: h for m, h in state["hist"].items() if h and now - h[-1]["t"] < 6 * 3600}
    state["first_seen"] = {m: t for m, t in state["first_seen"].items() if now - t < 24 * 3600
                           or m in state["open"]}
    _save(DATA / arm.instrument / "state.json", state)
    return {"arm": arm.instrument, "open": len(state["open"]), "opened": opened, "closed": closed}


def report_arm(arm) -> dict:
    ledger = _ledger(arm)
    res = ledger.resolved()
    rets = [r["net_return"] for r in res]
    clusters = [(r.get("mint"), r.get("entry_day")) for r in res]
    d = SC.decide(rets, clusters, arm.target_n, extended_cap=arm.extended_cap)
    state = _load(DATA / arm.instrument / "state.json", {"open": {}})
    return {"arm": arm.instrument, "resolved": len(res), "open": len(state.get("open", {})),
            "chain_ok": ledger.verify(), "basis": arm.fill_basis, **d}


def run_once(hub: Hub | None = None) -> list[dict]:
    hub = hub or Hub()
    feed = hub.snapshot()
    return [service_arm(arm, feed, hub) for arm in _registered_arms()]


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--report" in argv:
        print(json.dumps([report_arm(a) for a in _registered_arms()], indent=2))
        return 0
    once = "--once" in argv
    print(f"MEME ARENA runtime: {[a.instrument for a in _registered_arms()]} (poll {POLL_SECONDS}s)",
          flush=True)
    hub = Hub()
    while True:
        try:
            svc = run_once(hub)
            print(json.dumps({"ts": int(time.time()), "cycle": svc,
                              "report": [report_arm(a) for a in _registered_arms()]},
                             separators=(",", ":")), flush=True)
        except Exception as exc:  # noqa: BLE001 — a bad cycle must not kill the collector
            print(json.dumps({"cycle_error": str(exc)[:200]}), flush=True)
        if once:
            break
        time.sleep(POLL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
