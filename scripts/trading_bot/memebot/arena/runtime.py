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
import fcntl
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import time

from . import exit_engine as EX
from . import fill as F
from . import scorer as SC
from .chainledger import ChainLedger
from .hub import Hub
from . import manifest as MF

ROOT = pathlib.Path(__file__).resolve().parents[4]
DATA = ROOT / "research" / "data" / "arena"
POLL_SECONDS = 150
HISTORY = 6
STATE_SCHEMA = 2
MAX_MARK_AGE_NS = 330_000_000_000


def _registered_arms():
    from .arms.virality_arrival import ARM as VIRALITY
    from .arms.bundle_momentum import ARM as BUNDLE
    from .arms.graduation import ARM as GRADUATION
    return [VIRALITY, BUNDLE, GRADUATION]


# Boot-closure guard (handoff 460): the closure sha of the code ACTUALLY LOADED, captured at import time
# (= process boot). `arm.code_sha256()` and `require_activation` both read the current DISK files, so after
# a commit they match a new on-disk activation even though this long-lived process still runs the OLD
# resolver from memory (exactly the bug that made virality's 11 rows -100% with no arbiter). Comparing the
# current disk sha to this boot capture catches that: a stale process refuses instead of trading old code.
_BOOT_SHAS = {arm.instrument: arm.code_sha256() for arm in _registered_arms()}


def _boot_guard(arm) -> None:
    boot = _BOOT_SHAS.get(arm.instrument)
    if boot is not None and arm.code_sha256() != boot:
        raise RuntimeError(
            f"{arm.instrument}: BOOT CLOSURE DRIFT — this process loaded code {boot[:8]} but the on-disk "
            f"closure is now {arm.code_sha256()[:8]}. A stale process must NOT run its old resolver under a "
            "freshly-written activation (handoff 460). Restart the runtime.")


def _load(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"arena state is malformed: {path}") from exc


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".arena_state_", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _new_state(activation_ns: int) -> dict:
    return {"schema": STATE_SCHEMA, "activation_unix_nanos": activation_ns, "open": {}, "hist": {},
            "first_seen": {}, "sampled_mints": {}, "pending_events": [], "cycles": 0}


def _validate_state(state: dict) -> None:
    if (not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA
            or type(state.get("activation_unix_nanos")) is not int
            or state["activation_unix_nanos"] <= 0
            or not all(isinstance(state.get(k), dict) for k in (
                "open", "hist", "first_seen", "sampled_mints"))
            or not isinstance(state.get("pending_events"), list)
            or type(state.get("cycles")) is not int or state["cycles"] < 0):
        raise RuntimeError("arena state schema refuses")


def _drain_pending(state: dict, ledger: ChainLedger, state_path: pathlib.Path) -> None:
    """State-first WAL: replay the exact event idempotently, then apply its final state transition."""
    while state["pending_events"]:
        pending = state["pending_events"][0]
        if not isinstance(pending, dict) or set(pending) != {"kind", "row", "finalize"}:
            raise RuntimeError("arena pending event is malformed")
        if pending["kind"] == "opened":
            ledger.append_opened(pending["row"])
        elif pending["kind"] == "resolved":
            ledger.append_resolved(pending["row"])
            mint = pending["finalize"].get("remove_open_mint")
            if mint:
                state["open"].pop(mint, None)
        elif pending["kind"] == "void":
            ledger.append_void(pending["row"])
            mint = pending["finalize"].get("remove_open_mint")
            if mint:
                state["open"].pop(mint, None)
        else:
            raise RuntimeError("arena pending event kind refuses")
        state["pending_events"].pop(0)
        _save(state_path, state)


def _ledger(arm) -> ChainLedger:
    _boot_guard(arm)                      # a stale process refuses before it can touch the ledger (460)
    authority = MF.require_activation(arm)
    return ChainLedger(DATA / arm.instrument / "ledger.jsonl", arm.instrument,
                       arm.code_sha256(), arm.prereg_sha256(), arm.spec_sha256(),
                       authority["activation_sha256"])


def _day(ts: float) -> str:
    return dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def service_arm(arm, feed: dict, hub: Hub) -> dict:
    state_path = DATA / arm.instrument / "state.json"
    lock_path = DATA / arm.instrument / "runtime.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(lock_fd)
        raise RuntimeError(f"{arm.instrument}: another runtime owns the arm") from exc
    try:
        return _service_arm_unlocked(arm, feed, hub, state_path=state_path)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _service_arm_unlocked(arm, feed: dict, hub: Hub, *, state_path: pathlib.Path) -> dict:
    authority = MF.require_activation(arm)
    initialized = not state_path.exists()
    now_ns = time.time_ns()
    state = _load(state_path, _new_state(authority["activated_unix_nanos"]))
    _validate_state(state)
    if state["activation_unix_nanos"] != authority["activated_unix_nanos"]:
        raise RuntimeError(f"{arm.instrument}: state activation does not match authority")
    ledger = _ledger(arm)
    ledger.ensure_genesis()
    _drain_pending(state, ledger, state_path)
    now = now_ns / 1_000_000_000
    opened = closed = 0

    # 1. service open positions on their own pinned market
    for mint, pos in list(state["open"].items()):
        c = hub.refresh_pair(pos["pair"]) if pos.get("pair") else feed.get(mint)
        receipt_ns = c.get("observed_unix_nanos") if isinstance(c, dict) else None
        fresh = (type(receipt_ns) is int and state["activation_unix_nanos"] < receipt_ns <= now_ns
                 and now_ns - receipt_ns <= MAX_MARK_AGE_NS)
        mark = c["price"] if (fresh and c.get("price")) else None
        p = EX.Position(mint=mint, arm=arm.instrument, basis=arm.fill_basis,
                        entry_price=pos["entry_price"], opened_ts=pos["opened_ts"], peak=pos["peak"],
                        peak_net_return=pos.get("peak_net_return", -1.0))
        current_fill = F.honest_fill_snapshot(pos["entry_price"], mark) if mark is not None else None
        reason = EX.exit_signal(
            p, mark, now,
            all_cost_net_return=(current_fill.net_return if current_fill is not None else None))
        pos["peak"] = p.peak                                   # persist the updated peak
        pos["peak_net_return"] = p.peak_net_return
        pos["unpriced_count"] = 0 if mark is not None else pos.get("unpriced_count", 0) + 1
        if reason is None and mark is None:
            reason = "RUG_UNPRICED" if pos["unpriced_count"] >= 3 else None
        if reason == "RUG_UNPRICED":
            # an unpriceable position is NOT auto a -100% rug (that fabricated virality's 6 false rugs).
            # Ask Helius: only a positively-dead coin is a real loss; an alive coin is a measurement VOID.
            from .helius_rug_arbiter import classify_unpriced
            try:
                arb = classify_unpriced(mint, pos.get("pair"))
            except Exception as exc:  # noqa: BLE001 — arbiter failure is a measurement failure, not a rug
                arb = {"verdict": "INDETERMINATE_VOID", "reason": f"arbiter error: {str(exc)[:80]}"}
            if arb["verdict"] != "RUG_CONFIRMED":
                void_row = {"mint": mint, "arm": arm.instrument, "reason": "MEASUREMENT_FAILURE",
                            "cohort": pos.get("cohort", "PRIMARY"), "entry_day": pos.get("entry_day"),
                            "arbiter_verdict": arb["verdict"], "arbiter_reason": arb.get("reason"),
                            "entry_id": pos["entry_id"],
                            "void_id": _sha({"entry_id": pos["entry_id"], "kind": "measurement_void"})}
                state["pending_events"].append({
                    "kind": "void", "row": void_row, "finalize": {"remove_open_mint": mint}})
                _save(state_path, state)
                _drain_pending(state, ledger, state_path)
                closed += 1
                continue
            reason = "RUG_CONFIRMED"     # positively dead on-chain -> a real -100% primary loss
        if reason:
            row = EX.resolve(p, reason, exit_mark=mark, now_ts=now)
            row["entry_day"] = pos.get("entry_day")
            row["minutes_since_first_seen"] = pos.get("entry_delay_min")   # F6 mirage split
            row["entry_id"] = pos["entry_id"]
            row["resolution_id"] = _sha({"entry_id": pos["entry_id"], "reason": reason,
                                           "evidence": c.get("normalized_evidence_sha256") if c else None,
                                           "receipt": receipt_ns})
            state["pending_events"].append({
                "kind": "resolved", "row": row, "finalize": {"remove_open_mint": mint}})
            _save(state_path, state)
            _drain_pending(state, ledger, state_path)
            closed += 1

    # 2. update per-mint history + first-seen
    for mint, c in feed.items():
        receipt_ns = c.get("observed_unix_nanos")
        if (type(receipt_ns) is not int or receipt_ns <= state["activation_unix_nanos"]
                or receipt_ns > now_ns):
            continue
        state["first_seen"].setdefault(mint, receipt_ns)
        h = state["hist"].setdefault(mint, [])
        h.append({"received_ns": receipt_ns, "m5_buys": c.get("m5_buys", 0),
                  "m5_sells": c.get("m5_sells", 0), "price": c.get("price"),
                  "normalized_evidence_sha256": c.get("normalized_evidence_sha256")})
        del h[:-HISTORY]

    # 3. offer candidates to the frozen entry predicate
    for c in arm.candidates(feed):
        mint = c["mint"]
        if mint in state["open"] or (arm.one_sample_per_mint and mint in state["sampled_mints"]):
            continue
        hist = state["hist"].get(mint, [])[:-1]                # exclude the just-appended current obs
        receipt_ns = c.get("observed_unix_nanos")
        previous_ns = hist[-1].get("received_ns") if hist else None
        cadence_ok = (type(receipt_ns) is int and type(previous_ns) is int
                      and 0 < receipt_ns - previous_ns <= int(arm.history_max_gap_s * 1e9))
        if not initialized and cadence_ok and arm.entry_ok(c, hist):
            entry_id = _sha({"instrument": arm.instrument, "mint": mint,
                             "decision_unix_nanos": receipt_ns,
                             "evidence": c.get("normalized_evidence_sha256"),
                             "previous_evidence": hist[-1].get("normalized_evidence_sha256")})
            state["open"][mint] = {
                "entry_price": c["price"], "peak": c["price"], "opened_ts": now, "pair": c.get("pair"),
                "entry_day": _day(now),
                "entry_delay_min": round((receipt_ns - state["first_seen"].get(mint, receipt_ns))
                                         / 60_000_000_000, 1),
                "entry_id": entry_id, "peak_net_return": -1.0, "unpriced_count": 0}
            state["sampled_mints"][mint] = entry_id
            open_row = {"entry_id": entry_id, "mint": mint, "entry_day": _day(now),
                        "entry_price": c["price"], "decision_unix_nanos": receipt_ns,
                        "evidence_sha256": c.get("normalized_evidence_sha256"),
                        "previous_evidence_sha256": hist[-1].get("normalized_evidence_sha256"),
                        "gate_tier": "TIER1_COUNT_PROXY", "basis": arm.fill_basis}
            state["pending_events"].append(
                {"kind": "opened", "row": open_row, "finalize": {}})
            _save(state_path, state)
            _drain_pending(state, ledger, state_path)
            opened += 1

    # prune stale history
    state["hist"] = {m: h for m, h in state["hist"].items()
                     if h and now_ns - h[-1]["received_ns"] < 6 * 3600 * 1_000_000_000}
    state["first_seen"] = {m: t for m, t in state["first_seen"].items()
                           if now_ns - t < 24 * 3600 * 1_000_000_000
                           or m in state["open"]}
    state["cycles"] += 1
    _save(state_path, state)
    return {"arm": arm.instrument, "open": len(state["open"]), "opened": opened, "closed": closed}


def report_arm(arm) -> dict:
    try:
        authority = MF.require_activation(arm)
    except RuntimeError as exc:
        return {"arm": arm.instrument, "resolved": 0, "open": 0, "pending": 0,
                "distinct_mints": True, "chain_ok": False, "basis": arm.fill_basis,
                "verdict": "NOT_ACTIVE", "reason": str(exc), "mean": None, "ci_lo": None,
                "ci_hi": None, "target_n": arm.target_n}
    ledger = _ledger(arm)
    all_res = ledger.resolved()
    void_rows = [r for r in ledger._rows() if r.get("kind") == "void"]
    from . import cohorts as CH
    coh = CH.split_cohorts(all_res, void_rows)
    res = [row for row in all_res if arm.include_resolution(row)]
    rets = [r["net_return"] for r in res]
    clusters = [(r.get("mint"), r.get("entry_day")) for r in res]
    state = _load(DATA / arm.instrument / "state.json",
                  _new_state(authority["activated_unix_nanos"]))
    chain_ok = ledger.verify()
    distinct = len({r.get("mint") for r in res}) == len(res)
    pending = len(state.get("pending_events", []))
    elapsed_weeks = max(1 / 7, (time.time_ns() - state["activation_unix_nanos"])
                        / (7 * 24 * 3600 * 1e9))
    events_per_week = len(res) / elapsed_weeks
    d = SC.decide(rets, clusters, arm.target_n,
                  events_per_week=(events_per_week if len(res) and arm.service_kind == "snapshot" else None),
                  extended_cap=arm.extended_cap)
    if not chain_ok or not distinct or pending:
        d = {**d, "verdict": "INVALID", "reason": "chain/distinct-mint/pending lifecycle gate refuses"}
    if len(res) >= arm.target_n and not coh["censored_valid"]:
        d = {**d, "verdict": "INVALID", "reason": f"censored fraction {coh['censored_fraction']:.0%} "
             f"> {CH.CENSORED_FRACTION_LIMIT:.0%} — too many unpriceable positions to read honestly"}
    if len(res) >= arm.target_n and arm.service_kind == "snapshot":
        delayed = sorted((float(r.get("minutes_since_first_seen") or 0), r["net_return"])
                         for r in res)
        buckets = [delayed[i * len(delayed) // 3:(i + 1) * len(delayed) // 3] for i in range(3)]
        means = [sum(v for _, v in bucket) / len(bucket) for bucket in buckets if bucket]
        if len(means) == 3 and means[0] > means[1] > means[2] and means[2] < 0:
            d = {**d, "verdict": "KILL", "reason": "predeclared lagging-entry exhaustion split"}
        rugs = [r for r in res if r.get("reason") == "RUG_UNPRICED"]
        nonrugs = [r["net_return"] for r in res if r.get("reason") != "RUG_UNPRICED"]
        if rugs and sum(rets) / len(rets) < 0 and nonrugs and sum(nonrugs) / len(nonrugs) >= 0:
            d = {**d, "verdict": "KILL", "reason": "full-loss rug tail carries the negative sign"}
    d = arm.final_verdict(d, res, all_res)
    return {"arm": arm.instrument, "resolved": len(res), "open": len(state.get("open", {})),
            "pending": pending, "distinct_mints": distinct, "chain_ok": chain_ok,
            "basis": arm.fill_basis, "control_n": coh["control_n"],
            "measurement_failures": coh["measurement_failure_n"], "strategy_voids": coh["strategy_void_n"],
            "censored_fraction": coh["censored_fraction"], **d}


def run_once(hub: Hub | None = None) -> list[dict]:
    hub = hub or Hub()
    feed = hub.snapshot()
    return [service_arm(arm, feed, hub) for arm in _registered_arms()
            if arm.service_kind == "snapshot"]


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
