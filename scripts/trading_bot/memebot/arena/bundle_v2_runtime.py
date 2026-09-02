#!/usr/bin/env python3
"""Event-driven causal paper runtime for BUNDLE_MOMENTUM_V2. No signer or order path.

Evolved from ``bundle_runtime.py`` (V1): same WAL, same tape cursor/head continuity, same
``causal_fill_cp`` executable fills, same primary + flat-10 comparator on one causal entry. What V2 adds,
and ONLY what it adds:

  1. COVERAGE gate inside the entry decision — ``helius_coverage.coverage_ok`` runs at the s6 signal,
     BEFORE a pending entry is created. A truncated capture (create->first-buy gap) is a COVERAGE_VOID
     strategy void, never a trade.
  2. The shared $10 money-book clip — the SOL size is frozen at the fill boundary from the causal SOL/USD
     recorder via ``sizer.clip_sol``, and stored per-open (``size_sol``), replacing V1's constant 0.5.
  3. The GLOBAL primary slot — ``sizer.try_acquire_primary`` at the OPEN site (<=2 primaries across ALL
     arms, flock'd over one shared portfolio.json), released at the ``_drain`` resolved/void pop, and
     ``reconcile_slots`` at cycle start to heal the acquire-side leak.
  4. The RUG arbiter on BOTH RUG_UNPRICED sites — ``helius_rug_arbiter.classify_unpriced`` decides real
     death from measurement failure; only RUG_CONFIRMED books a -100% primary, everything else is a
     right-censored MEASUREMENT_FAILURE void.
  5. The boot-closure guard (handoff 460) — the arm's closure sha is captured at import; a cycle refuses
     "BOOT CLOSURE DRIFT" if the on-disk closure changed, so a stale process never runs old code under a
     freshly-written activation.

V1's instrument dir/ledger is untouched: this writes only under research/data/arena/BUNDLE_MOMENTUM_V2/.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
import pathlib
import sys
import time

from . import exit_engine as EX
from . import fill as F
from . import runtime as RT
from . import manifest as MF
from .arms import bundle_momentum_v2 as BM2
from .chainledger import ChainLedger
from .helius_coverage import coverage_ok
from .helius_rug_arbiter import classify_unpriced
from .sizer import (CLIP_USD, clip_sol, exit_capacity_ok, try_acquire_primary, release_primary,
                    reconcile_slots)
from .. import ws_data
from ...aftershock import solusd_recorder
from ...aftershock.execution import PriceUnavailable
from ...aftershock.pac_v2_pumpswap import PumpSwapProvider, PumpSwapUnavailable, sell_quote

MIN_POLL_SECONDS = 0.25       # base cadence while the tape is actively producing rows
ACTIVE_POLL_SECONDS = 0.5     # positions open/pending, no new rows — still service wall-clock deadlines promptly
MAX_POLL_SECONDS = 4.0        # idle ceiling: nothing open/pending and no rows arriving (exponential backoff)
REVERIFY_INTERVAL_S = 60.0    # re-run the git-anchored activation + closure-drift check at least this often
STATE_SCHEMA = 1
INSTRUMENT = BM2.ARM.instrument
# One shared portfolio.json across ALL arms (the global <=2 PRIMARY slot file). NOT per-instrument.
PORTFOLIO_PATH = RT.DATA / "portfolio.json"

# Boot-closure guard (handoff 460, CRITICAL): capture the closure sha of the code ACTUALLY LOADED at import
# (= process boot). require_activation and code_sha256() both read the CURRENT disk files, so after a commit
# they would agree with a freshly-written activation even though this long-lived process still runs the OLD
# resolver from memory. Comparing the live disk sha to this boot capture refuses that stale run.
_BOOT_CLOSURE_SHA = BM2.ARM.code_sha256()


def _boot_guard() -> None:
    live = BM2.ARM.code_sha256()
    if live != _BOOT_CLOSURE_SHA:
        raise RuntimeError(
            f"{INSTRUMENT}: BOOT CLOSURE DRIFT — this process loaded code {_BOOT_CLOSURE_SHA[:8]} but the "
            f"on-disk closure is now {live[:8]}. A stale process must NOT run its old resolver under a "
            "freshly-written activation (handoff 460). Restart the runtime.")


# The set-once, git-anchored activation authority is immutable within a run; verify it once and reuse,
# re-checking every REVERIFY_INTERVAL_S so a genuine code/prereg/spec drift is still refused on a bounded lag.
_AUTHORITY: dict | None = None
_AUTHORITY_VERIFIED_MONOTONIC = 0.0


def _verified_authority() -> dict:
    global _AUTHORITY, _AUTHORITY_VERIFIED_MONOTONIC
    now = time.monotonic()
    if _AUTHORITY is None or now - _AUTHORITY_VERIFIED_MONOTONIC >= REVERIFY_INTERVAL_S:
        _AUTHORITY = MF.require_activation(BM2.ARM)
        _AUTHORITY_VERIFIED_MONOTONIC = now
    return _AUTHORITY


def _state_path() -> pathlib.Path:
    return RT.DATA / INSTRUMENT / "state.json"


def _ledger() -> ChainLedger:
    authority = _verified_authority()
    return ChainLedger(RT.DATA / INSTRUMENT / "ledger.jsonl", INSTRUMENT,
                       authority["code_sha256"], authority["prereg_sha256"],
                       authority["spec_sha256"], authority["activation_sha256"])


def _new_state(authority: dict) -> dict:
    return {"schema": STATE_SCHEMA, "instrument": INSTRUMENT,
            "activation_unix_nanos": authority["activated_unix_nanos"],
            "tape_cursor": authority["tape_sequence"],
            "tape_head": authority["tape_head_sha256"], "tape_offset": authority["tape_offset"],
            "mints": {}, "pending_entries": {}, "open": {},
            "sampled_mints": {}, "pending_ledger": [], "voids": 0, "cycles": 0}


def _load_state() -> tuple[dict, bool]:
    authority = _verified_authority()
    path = _state_path(); fresh = not path.exists()
    state = RT._load(path, _new_state(authority))
    required = {"schema", "instrument", "activation_unix_nanos", "tape_cursor", "tape_head",
                "tape_offset",
                "mints", "pending_entries", "open", "sampled_mints", "pending_ledger",
                "voids", "cycles"}
    if (not isinstance(state, dict) or set(state) != required or state["schema"] != STATE_SCHEMA
            or state["instrument"] != INSTRUMENT or type(state["tape_cursor"]) is not int
            or type(state["tape_offset"]) is not int or state["tape_offset"] < 0
            or not all(isinstance(state[k], dict) for k in (
                "mints", "pending_entries", "open", "sampled_mints"))
            or not isinstance(state["pending_ledger"], list)):
        raise RuntimeError("bundle v2 runtime state refuses")
    if state["activation_unix_nanos"] != authority["activated_unix_nanos"]:
        raise RuntimeError("bundle v2 state activation does not match authority")
    return state, fresh


def _save(state: dict) -> None:
    RT._save(_state_path(), state)


def _drain(state: dict) -> None:
    """State-first WAL drain. A resolved row or an open-position void pops the open AND releases that mint's
    global primary slot (release_primary is idempotent, so a candidate void that never took a slot is a
    no-op). An `opened` row never releases; the slot is taken at the open site."""
    ledger = _ledger()
    while state["pending_ledger"]:
        event = state["pending_ledger"][0]
        if event["kind"] == "opened":
            ledger.append_opened(event["row"])
        elif event["kind"] == "resolved":
            ledger.append_resolved(event["row"])
            mint = event["row"]["mint"]
            state["open"].pop(mint, None)
            release_primary(INSTRUMENT, mint, PORTFOLIO_PATH)
        elif event["kind"] == "void":
            ledger.append_void(event["row"])
            mint = event["row"].get("mint")
            if mint is not None:
                state["open"].pop(mint, None)
                release_primary(INSTRUMENT, mint, PORTFOLIO_PATH)
        else:
            raise RuntimeError("bundle v2 pending ledger kind refuses")
        state["pending_ledger"].pop(0); _save(state)


def _decimal(row: dict, key: str, *aliases: str) -> Decimal:
    label = key
    for candidate in (key, *aliases):
        if candidate in row and row[candidate] is not None:
            try:
                value = Decimal(str(row[candidate]))
            except (InvalidOperation, TypeError) as exc:
                raise RuntimeError(f"bundle reserve {label} invalid") from exc
            if not value.is_finite() or value <= 0:
                raise RuntimeError(f"bundle reserve {label} nonpositive")
            return value
    raise RuntimeError(f"bundle reserve {label} invalid")


def _reserves(row: dict) -> tuple[float, float, float]:
    virtual_sol = _decimal(row, "virtual_sol", "vSolInBondingCurve")
    virtual_tokens = _decimal(row, "virtual_tokens", "vTokensInBondingCurve")
    return float(virtual_sol), float(virtual_tokens), float(max(Decimal(0), virtual_sol - Decimal(30)))


def _entry_token_atoms(reserves: tuple[float, float, float], size_sol: float) -> int:
    sol, tokens = (Decimal(str(reserves[0])), Decimal(str(reserves[1])))
    effective = Decimal(str(size_sol)) * (Decimal(1) - Decimal(str(F.TOLL_BUY)))
    output = tokens * effective / (sol + effective)
    atoms = int(output * Decimal(1_000_000))
    if atoms <= 0:
        raise RuntimeError("bundle entry token output is unavailable")
    return atoms


def _created_after_activation(state: dict) -> dict[str, int]:
    """Post-activation CREATE mints and their create-receive nanoseconds (the coverage gate's t0)."""
    output: dict[str, int] = {}
    for row in ws_data.read_buffer():
        ns = row.get("received_unix_nanos")
        if type(ns) is int and ns > state["activation_unix_nanos"] and isinstance(row.get("mint"), str):
            output.setdefault(row["mint"], ns)
    return output


def _position(mint: str, raw: dict, variant: str) -> EX.Position:
    value = raw[variant]
    return EX.Position(mint, INSTRUMENT, "causal_cp", raw["entry_price"],
                       raw["opened_unix_nanos"] / 1e9, peak=value["peak"],
                       peak_net_return=value.get("peak_net_return", -1.0),
                       size_sol=raw["size_sol"], entry_reserves=tuple(raw["entry_reserves"]))


def _signal_variant(raw: dict, variant: str, row: dict) -> None:
    value = raw[variant]
    if value.get("result") is not None or value.get("pending") is not None:
        return
    reserves = _reserves(row)
    current = F.causal_fill_cp(tuple(raw["entry_reserves"]), reserves[:2], raw["size_sol"],
                               latency_s=BM2.LATENCY_S,
                               real_sol_withdrawable_at_exit=reserves[2])
    p = _position(raw["mint"], raw, variant)
    mark = reserves[0] / reserves[1]
    if variant == "primary":
        reason = EX.exit_signal(p, mark, row["received_unix_nanos"] / 1e9,
                                all_cost_net_return=current.net_return)
    else:
        p.peak = max(p.peak, mark)
        reason = "HARD_STOP" if current.net_return <= -EX.HARD_STOP else None
        if reason is None and mark <= p.peak * 0.90:
            reason = "FLAT_10_TRAIL"
        if reason is None and row["received_unix_nanos"] - raw["opened_unix_nanos"] > EX.HORIZON_S * 1e9:
            reason = "HORIZON"
    value["peak"], value["peak_net_return"] = p.peak, p.peak_net_return
    if reason:
        value["pending"] = {"reason": reason,
                            "target_ns": row["received_unix_nanos"] + int(BM2.LATENCY_S * 1e9),
                            "deadline_ns": row["received_unix_nanos"]
                            + int((BM2.LATENCY_S + BM2.EXIT_BOUNDARY_TIMEOUT_S) * 1e9),
                            "trigger_record_sha256": row["record_sha256"]}


def _land_variant(raw: dict, variant: str, row: dict) -> None:
    value = raw[variant]; pending = value.get("pending")
    if not pending or row["received_unix_nanos"] < pending["target_ns"]:
        return
    reserves = _reserves(row)
    p = _position(raw["mint"], raw, variant)
    result = EX.resolve(p, pending["reason"], exit_reserves=reserves[:2],
                        real_sol_withdrawable=reserves[2], latency_s=BM2.LATENCY_S,
                        now_ts=row["received_unix_nanos"] / 1e9)
    result["landing_record_sha256"] = row["record_sha256"]
    value["result"], value["pending"] = result, None


def _maybe_finish(state: dict, mint: str) -> None:
    raw = state["open"].get(mint)
    if not raw or any(raw[v].get("result") is None for v in ("primary", "comparator")):
        return
    primary, comparator = raw["primary"]["result"], raw["comparator"]["result"]
    resolution_id = RT._sha({"entry_id": raw["entry_id"],
                             "primary": primary["landing_record_sha256"],
                             "comparator": comparator["landing_record_sha256"]})
    row = {**primary, "entry_id": raw["entry_id"], "resolution_id": resolution_id,
           "entry_day": raw["entry_day"], "minutes_since_first_seen": 0,
           "cohort": "PRIMARY", "size_sol": raw["size_sol"], "clip_usd": CLIP_USD,
           "comparator_net_return": comparator["net_return"],
           "comparator_reason": comparator["reason"],
           "top_share_bps": raw["top_share_bps"], "clump_ns": raw["clump_ns"]}
    state["pending_ledger"].append({"kind": "resolved", "row": row}); _save(state); _drain(state)


def _classify(mint: str, raw: dict) -> dict:
    """The RUG arbiter, best-effort liquidity account (the PumpSwap pool if a migrate/trade row carried one,
    else the arbiter probes the mint itself). An arbiter exception is a measurement failure, never a rug."""
    try:
        return classify_unpriced(mint, raw.get("pool"))
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "INDETERMINATE_VOID", "reason": f"arbiter error: {str(exc)[:80]}"}


def _measurement_void(state: dict, mint: str, raw: dict, arb: dict, trigger_sha: str) -> None:
    """A would-be -100% that the arbiter did NOT positively confirm as a rug: a right-censored measurement
    failure for the WHOLE open (both variants). One void row; the drain pops the open and releases the slot.
    Never a -100% resolved."""
    void_id = RT._sha({"entry_id": raw["entry_id"], "kind": "measurement_void"})
    state["pending_ledger"].append({"kind": "void", "row": {
        "void_id": void_id, "entry_id": raw["entry_id"], "mint": mint,
        "reason": "MEASUREMENT_FAILURE", "cohort": "PRIMARY", "entry_day": raw["entry_day"],
        "arbiter_verdict": arb["verdict"], "arbiter_reason": arb.get("reason"),
        "decision_unix_nanos": raw["opened_unix_nanos"], "trigger_record_sha256": trigger_sha}})
    state["voids"] += 1; _save(state); _drain(state)


def _rug_variant(raw: dict, variant: str, mint: str, now_ns: int, trigger_sha: str) -> None:
    p = _position(mint, raw, variant)
    result = EX.resolve(p, "RUG_UNPRICED", latency_s=BM2.LATENCY_S, now_ts=now_ns / 1e9)
    result["landing_record_sha256"] = trigger_sha
    raw[variant]["result"], raw[variant]["pending"] = result, None


def _migration_result(raw: dict, variant: str, observation) -> dict:
    quote = sell_quote(raw["token_atoms"], observation.reserves)
    exit_sol = quote["net_quote_lamports"] / 1_000_000_000
    fixed_sol = 2_250_000 / 1_000_000_000
    net = (exit_sol - raw["size_sol"] - fixed_sol) / raw["size_sol"]
    tokens = raw["token_atoms"] / 1_000_000
    return {"mint": raw["mint"], "arm": INSTRUMENT, "reason": "MIGRATION_EXIT",
            "basis": "pumpswap_exact_cp", "entry_price": raw["entry_price"],
            "exit_price": (exit_sol / tokens if tokens else 0.0),
            "gross_return": round(exit_sol / raw["size_sol"] - 1.0, 6),
            "net_return": round(net, 6), "net_marginal": None,
            "real_reserve_bound_hit": False,
            "held_s": int((observation.response_received_unix_nanos
                           - raw["opened_unix_nanos"]) / 1e9),
            "decomposition": {"venue": "PUMPSWAP", "variant": variant,
                              "quote": quote, "fixed_cost_sol": fixed_sol},
            "landing_record_sha256": observation.raw_response_sha256}


def _service_migration(state: dict, mint: str, raw: dict, provider: PumpSwapProvider,
                       now_ns: int) -> None:
    pending = raw.get("migration")
    if not pending or now_ns < pending["target_ns"]:
        return
    try:
        observation = provider.capture(mint, pending["minimum_context_slot"])
        for variant in ("primary", "comparator"):
            if raw[variant].get("result") is None:
                raw[variant]["result"] = _migration_result(raw, variant, observation)
                raw[variant]["pending"] = None
        raw["migration"] = None
        _maybe_finish(state, mint)
    except (PumpSwapUnavailable, PriceUnavailable):
        if now_ns < pending["deadline_ns"]:
            return
        # Would-be -100%: the migrated pool is unpriceable. Route through the arbiter (RUG site #1).
        arb = _classify(mint, raw)
        if arb["verdict"] == "RUG_CONFIRMED":
            for variant in ("primary", "comparator"):
                if raw[variant].get("result") is None:
                    _rug_variant(raw, variant, mint, now_ns, pending["trigger_record_sha256"])
            raw["migration"] = None
            _maybe_finish(state, mint)
        else:
            raw["migration"] = None
            _measurement_void(state, mint, raw, arb, pending["trigger_record_sha256"])


def _size_clip(landing_ns: int) -> tuple[float, float]:
    """The shared $10 money-book clip, in SOL, frozen at the fill boundary from the causal SOL/USD recorder.
    Raises if no fresh causal SOL/USD observation exists (the caller then strategy-voids rather than size blind)."""
    observation = solusd_recorder.latest_observation(decision_unix_nanos=landing_ns)
    sol_usd = float(observation.value_str)
    return clip_sol(sol_usd), sol_usd


def _emit_candidate_void(state: dict, mint: str, entry_id: str, reason: str,
                         decision_ns: int, detail: str | None = None) -> None:
    """A STRATEGY VOID at the entry/land site — the strategy declined to trade (coverage, sizing, or the
    global slot). No open exists yet, so no slot to release. The mint is marked sampled so it is not
    re-attempted from every subsequent tape row."""
    void_id = RT._sha({"instrument": INSTRUMENT, "entry_id": entry_id, "reason": reason})
    row = {"void_id": void_id, "entry_id": entry_id, "mint": mint, "reason": reason,
           "decision_unix_nanos": decision_ns}
    if detail is not None:
        row["detail"] = detail
    state["pending_ledger"].append({"kind": "void", "row": row})
    state["sampled_mints"][mint] = entry_id
    state["pending_entries"].pop(mint, None)
    state["voids"] += 1; _save(state); _drain(state)


def _buffer_first_buys(rows: list[dict], k: int) -> list[dict]:
    ordered = sorted(rows, key=lambda r: (r["received_unix_nanos"], r["sequence"]))
    buys = [r for r in ordered if r.get("tx_type") == "buy"]
    return [{"received_unix_nanos": b["received_unix_nanos"], "signature": b.get("signature")}
            for b in buys[:k]]


def _process_row(state: dict, row: dict, created: dict[str, int]) -> None:
    mint = row["mint"]
    if mint not in created:
        state["tape_cursor"], state["tape_head"] = row["sequence"], row["record_sha256"]
        _save(state); return
    raw = state["open"].get(mint)
    if raw is not None:
        raw["last_event_ns"] = row["received_unix_nanos"]
        raw["last_record_sha256"] = row["record_sha256"]
        if row.get("pool"):
            raw["pool"] = row["pool"]                # best-effort liquidity account for the arbiter
        if row.get("tx_type") in {"migrate", "migration"}:
            raw["migration"] = {"target_ns": row["received_unix_nanos"] + int(BM2.LATENCY_S * 1e9),
                                "deadline_ns": row["received_unix_nanos"]
                                + int((BM2.LATENCY_S + BM2.EXIT_BOUNDARY_TIMEOUT_S) * 1e9),
                                "minimum_context_slot": (row.get("slot")
                                                         if type(row.get("slot")) is int else 0),
                                "trigger_record_sha256": row["record_sha256"]}
            state["tape_cursor"], state["tape_head"] = row["sequence"], row["record_sha256"]
            _save(state)
            return
        raw["last_reserves"] = list(_reserves(row))
        for variant in ("primary", "comparator"):
            _land_variant(raw, variant, row)
            _signal_variant(raw, variant, row)
        _maybe_finish(state, mint)
    pending = state["pending_entries"].get(mint)
    if pending is not None and row["received_unix_nanos"] >= pending["target_ns"]:
        reserves = _reserves(row)
        entry_id = pending["entry_id"]
        landing_ns = row["received_unix_nanos"]
        # (2) SIZE the shared $10 clip at the fill boundary. No causal SOL/USD => strategy void, not blind size.
        try:
            size_sol, sol_usd = _size_clip(landing_ns)
        except Exception as exc:  # noqa: BLE001
            _emit_candidate_void(state, mint, entry_id, "SOL_USD_UNAVAILABLE",
                                 pending["decision_ns"], detail=str(exc)[:120])
            state["tape_cursor"], state["tape_head"] = row["sequence"], row["record_sha256"]
            _save(state); return
        # The shared money-book contract says the clip may consume at most 5% of exit capacity. The real
        # withdrawable SOL at the causal landing boundary is the hardest observable upper bound on that
        # capacity; unknown or insufficient capacity is a strategy void, never a small-pool gamble.
        capacity_usd = reserves[2] * sol_usd
        capacity_ok, capacity_reason = exit_capacity_ok(CLIP_USD, capacity_usd)
        if not capacity_ok:
            _emit_candidate_void(state, mint, entry_id, "EXIT_CAPACITY_VOID",
                                 pending["decision_ns"], detail=capacity_reason)
            state["tape_cursor"], state["tape_head"] = row["sequence"], row["record_sha256"]
            _save(state); return
        # (3) Take one of the <=2 GLOBAL primary slots. Full => strategy void (never a blind over-limit trade).
        if not try_acquire_primary(INSTRUMENT, mint, PORTFOLIO_PATH):
            _emit_candidate_void(state, mint, entry_id, "PORTFOLIO_SLOTS_FULL", pending["decision_ns"])
            state["tape_cursor"], state["tape_head"] = row["sequence"], row["record_sha256"]
            _save(state); return
        entry_math = F.causal_fill_cp(reserves[:2], reserves[:2], size_sol,
                                      latency_s=BM2.LATENCY_S,
                                      real_sol_withdrawable_at_exit=reserves[2])
        state["open"][mint] = {"mint": mint, "entry_id": entry_id, "size_sol": size_sol,
            "entry_reserves": list(reserves[:2]), "entry_price": entry_math.entry_price,
            "opened_unix_nanos": landing_ns, "entry_day": RT._day(time.time()),
            "entry_exit_capacity_usd": capacity_usd,
            "last_event_ns": landing_ns, "last_reserves": list(reserves),
            "last_record_sha256": row["record_sha256"], "pool": row.get("pool"),
            "token_atoms": _entry_token_atoms(reserves, size_sol), "migration": None,
            "top_share_bps": pending["top_share_bps"], "clump_ns": pending["clump_ns"],
            "primary": {"peak": entry_math.entry_price, "peak_net_return": entry_math.net_return,
                        "pending": None, "result": None},
            "comparator": {"peak": entry_math.entry_price, "peak_net_return": entry_math.net_return,
                           "pending": None, "result": None}}
        del state["pending_entries"][mint]
        open_row = {"entry_id": entry_id, "mint": mint, "entry_day": RT._day(time.time()),
                    "entry_price": entry_math.entry_price, "size_sol": size_sol, "clip_usd": CLIP_USD,
                    "entry_exit_capacity_usd": capacity_usd,
                    "decision_unix_nanos": pending["decision_ns"],
                    "landing_unix_nanos": landing_ns,
                    "evidence_sha256": pending["evidence_sha256"],
                    "landing_evidence_sha256": row["record_sha256"],
                    "gate_tier": "AT_S6_CONCENTRATION_PROXY_COVERAGE_OK", "basis": "causal_cp"}
        state["pending_ledger"].append({"kind": "opened", "row": open_row}); _save(state); _drain(state)
    mint_state = state["mints"].setdefault(mint, {"rows": []})
    if mint not in state["sampled_mints"] and mint not in state["pending_entries"]:
        mint_state["rows"].append(row)
        signal = BM2.first_six_signal(mint_state["rows"])
        if signal:
            entry_id = RT._sha({"instrument": INSTRUMENT, "mint": mint,
                                "decision_sequence": signal["decision_sequence"],
                                "evidence": signal["evidence_record_sha256"]})
            # (1) COVERAGE gate INSIDE the entry decision, BEFORE any pending entry. A truncated capture
            # (create->first-buy gap, or too-few captured buys) is a COVERAGE_VOID strategy void.
            cov = coverage_ok(created.get(mint), _buffer_first_buys(mint_state["rows"], BM2.COVERAGE_K),
                              BM2.COVERAGE_K)
            if not cov["ok"]:
                _emit_candidate_void(state, mint, entry_id, "COVERAGE_VOID",
                                     signal["decision_unix_nanos"], detail=cov["reason"])
            else:
                state["sampled_mints"][mint] = entry_id
                state["pending_entries"][mint] = {"entry_id": entry_id,
                    "decision_ns": signal["decision_unix_nanos"],
                    "target_ns": signal["decision_unix_nanos"] + int(BM2.LATENCY_S * 1e9),
                    "deadline_ns": signal["decision_unix_nanos"]
                    + int((BM2.LATENCY_S + BM2.ENTRY_BOUNDARY_TIMEOUT_S) * 1e9),
                    "top_share_bps": signal["top_share_bps"], "clump_ns": signal["clump_ns"],
                    "evidence_sha256": signal["evidence_record_sha256"]}
    state["tape_cursor"], state["tape_head"] = row["sequence"], row["record_sha256"]
    _save(state)


def _timeouts(state: dict, now_ns: int, provider: PumpSwapProvider) -> None:
    for mint, pending in list(state["pending_entries"].items()):
        if now_ns >= pending["deadline_ns"]:
            void_id = RT._sha({"entry_id": pending["entry_id"], "reason": "VOID_NO_ENTRY_BOUNDARY"})
            state["pending_ledger"].append({"kind": "void", "row": {
                "void_id": void_id, "entry_id": pending["entry_id"], "mint": mint,
                "reason": "VOID_NO_ENTRY_BOUNDARY", "decision_unix_nanos": pending["decision_ns"]}})
            del state["pending_entries"][mint]; state["voids"] += 1; _save(state); _drain(state)
    for mint, raw in list(state["open"].items()):
        if raw.get("migration"):
            _service_migration(state, mint, raw, provider, now_ns)
            if mint not in state["open"] or raw.get("migration"):
                continue
        # DEAD_SILENCE: a same-mint silence opens a dead-coin exit (a pending, not yet a resolution).
        for variant in ("primary", "comparator"):
            value = raw[variant]
            if (value.get("result") is None and value.get("pending") is None
                    and now_ns - raw["last_event_ns"] >= BM2.DEAD_SILENCE_S * 1e9):
                value["pending"] = {"reason": "DEAD_SILENCE",
                    "target_ns": now_ns + int(BM2.LATENCY_S * 1e9),
                    "deadline_ns": now_ns + int((BM2.LATENCY_S + BM2.EXIT_BOUNDARY_TIMEOUT_S) * 1e9),
                    "trigger_record_sha256": raw.get("last_record_sha256", "0" * 64)}
        # RUG site #2: a pending exit whose fill boundary never arrived is a would-be -100%. Route through
        # the arbiter ONCE for the whole open. Only a positively-dead coin books a -100% primary; anything
        # else is a right-censored MEASUREMENT_FAILURE void of the whole open.
        prim = raw["primary"]; prim_pending = prim.get("pending")
        if prim.get("result") is None and prim_pending and now_ns >= prim_pending["deadline_ns"]:
            arb = _classify(mint, raw)
            if arb["verdict"] == "RUG_CONFIRMED":
                for variant in ("primary", "comparator"):
                    if raw[variant].get("result") is None:
                        _rug_variant(raw, variant, mint, now_ns, prim_pending["trigger_record_sha256"])
                _maybe_finish(state, mint)
            else:
                _measurement_void(state, mint, raw, arb, prim_pending["trigger_record_sha256"])
                continue                                 # open removed
        # The comparator is a CONTROL and cannot decide the open's fate. If it alone goes unpriceable after
        # a clean primary, book its -100% only when the arbiter confirms a rug; otherwise censor it (null
        # control return) so the real primary sample still finishes.
        comp = raw["comparator"]; comp_pending = comp.get("pending")
        if comp.get("result") is None and comp_pending and now_ns >= comp_pending["deadline_ns"]:
            arb = _classify(mint, raw)
            if arb["verdict"] == "RUG_CONFIRMED":
                _rug_variant(raw, "comparator", mint, now_ns, comp_pending["trigger_record_sha256"])
            else:
                comp["result"] = {"mint": mint, "arm": INSTRUMENT, "reason": "MEASUREMENT_VOID",
                                  "basis": "causal_cp", "net_return": None, "gross_return": None,
                                  "net_marginal": None, "real_reserve_bound_hit": False,
                                  "arbiter_verdict": arb["verdict"],
                                  "landing_record_sha256": comp_pending["trigger_record_sha256"]}
                comp["pending"] = None
        _maybe_finish(state, mint)
    _save(state)


def _new_tape_rows(state: dict) -> list[tuple[dict, int]]:
    path = ws_data.TRADE_BUFFER_PATH
    if not path.exists():
        if state["tape_offset"] != 0:
            raise RuntimeError("bundle tape disappeared below persisted cursor")
        return []
    if path.stat().st_size < state["tape_offset"]:
        raise RuntimeError("bundle tape truncated below persisted cursor")
    rows = []
    with path.open("rb") as handle:
        handle.seek(state["tape_offset"])
        while True:
            start = handle.tell(); raw = handle.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                handle.seek(start); break
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError("bundle tape has a malformed complete row") from exc
            rows.append((row, handle.tell()))
    return rows


def _cycle_unlocked(provider: PumpSwapProvider) -> dict:
    if not ws_data.trade_data_authorized():
        raise RuntimeError("bundle v2 arm refuses without an authorized realtime trade-data endpoint")
    _boot_guard()                                        # a stale process refuses before it touches anything
    ws_data.require_trade_stream_fresh()                 # process-up is not feed-up; stale/403 means NO EVIDENCE
    state, fresh = _load_state(); _ledger().ensure_genesis(); _drain(state)
    # Startup self-heal for the acquire-side slot leak: release any of OUR OWN portfolio slots whose mint is
    # not in this arm's live open set (a crash between acquire and the open fsync orphans the slot).
    reconcile_slots(INSTRUMENT, list(state["open"].keys()), PORTFOLIO_PATH)
    created = _created_after_activation(state)
    rows = _new_tape_rows(state)
    for row, end_offset in rows:
        body = dict(row); observed_hash = body.pop("record_sha256", None)
        if (row.get("sequence") != state["tape_cursor"] + 1
                or row.get("previous_record_sha256") != state["tape_head"]
                or observed_hash != hashlib.sha256(ws_data._canonical(body)).hexdigest()):
            raise RuntimeError("bundle tape cursor/head continuity refuses")
        _process_row(state, row, created)
        state["tape_offset"] = end_offset; _save(state)
    _timeouts(state, time.time_ns(), provider); state["cycles"] += 1; _save(state)
    return {"fresh": fresh, "rows": len(rows), "open": len(state["open"]),
            "pending": len(state["pending_entries"]), "voids": state["voids"]}


def cycle(provider: PumpSwapProvider | None = None) -> dict:
    provider = provider or PumpSwapProvider(
        exchange_path=RT.DATA / INSTRUMENT / "pumpswap_exchanges.jsonl")
    lock_path = RT.DATA / INSTRUMENT / "runtime.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another bundle v2 runtime owns the instrument") from exc
        return _cycle_unlocked(provider)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN); os.close(descriptor)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--activate" in argv:
        # set-once, git-anchored activation for this standalone instrument (mirrors `manifest write`, which
        # only enumerates the arms registered in the snapshot runtime). Caller commits the record separately.
        print(json.dumps(MF.write_activation(BM2.ARM), sort_keys=True))
        return 0
    if "--report" in argv:
        print(json.dumps(RT.report_arm(BM2.ARM), indent=2))
        return 0
    once = "--once" in argv
    delay = MIN_POLL_SECONDS
    while True:
        result = None
        try:
            result = cycle()
            print(json.dumps({"instrument": INSTRUMENT, **result}, sort_keys=True), flush=True)
        except Exception as exc:
            print(json.dumps({"instrument": INSTRUMENT, "error": str(exc)[:240]}), flush=True)
        if once:
            return 0
        if result is not None and result.get("rows"):
            delay = MIN_POLL_SECONDS
        elif result is not None and (result.get("open") or result.get("pending")):
            delay = ACTIVE_POLL_SECONDS
        else:
            delay = min(max(delay, MIN_POLL_SECONDS) * 2, MAX_POLL_SECONDS)
        time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(main())
