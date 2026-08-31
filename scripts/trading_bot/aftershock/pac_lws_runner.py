#!/usr/bin/env python3
"""PAC Launch-Window Sentinel Scalper — a MULTI-POSITION PAPER-SCENARIO runner (measurement instrument).

There is deliberately no wallet, signer, transaction builder, or sender here.  This fans the proven
single-position PAC honest core out into a book of up to N_MAX concurrent slots, but — unlike the
momentum scalper — it enters the *surviving fresh-mint population*, not a momentum signal.  Every mint
is seen from its own CreateEvent (t0) by the creation-anchored ``pac_lws_feed`` collector; admission
is a live-bid coverage floor ONLY (real_quote >= 6x our notional), plus — on the veto arm — the sealed
B20B deadness screen over the strictly-past [t0, t0+60] window.  The null arm is byte-identical except
it admits regardless of the screen verdict (still logged as a shadow), so the two ledgers isolate the
screen's marginal effect.

Reuse (all byte-unchanged, by import — no sealed module is edited):
  * ``pac_lws_screen.evaluate``      — the sealed B20B veto (defense, not edge).
  * ``pac_scalp_policy.decide``      — the convex exit (cut losers small+fast, let winners run).
  * ``pac_scalp_marklog.record``     — the continuous intra-trade mark logger.
  * ``pac_v2_runner`` (as ``core``)  — the audited single-position fill/resolve/graduation/ledger engine
    (``_complete_pending`` / ``_refresh_and_check_graduation`` / ``_complete_pumpswap_exit`` /
    ``_resolve_full_loss`` / ``_ledger_row`` / ``_validate_ledger`` / ``_atomic_write`` / ``_flush`` /
    ``_commit`` / ``OpenPosition``).  Every fill lands at decision + inherited processed_p90 and is
    priced at the reserve state observed THEN — lookahead-free by construction.

The feed carries only the TOKEN reserve (``real_token``).  The audited engine prices off the SOL
reserve (``real_quote``), so this runner RECONSTRUCTS the full ``execution.ReserveState`` from
``real_token`` using the pinned pump.fun curve constants in ``ecr`` (constant-product; real and virtual
reserves differ by a launch-fixed offset).  At t0 the reconstruction is exact against
``state_from_create_event`` (asserted in the selftest).

Honest status: like every PAC scalp variant, this design's expected book is not proven positive; B20B
itself states that screening out dead tokens does not make the survivors profitable.  The instrument
exists to MEASURE the screen's marginal book (veto vs null) on the honest fresh-mint population.  The
scenario ledgers + mark log are the only arbiters.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import pathlib
import threading
import time

from .execution import (IntentKind, OrderIntent, PriceUnavailable, RefusedExecution, ReserveState,
                        q_lamports_for_usd)
from .feasibility import kernel_accounting
from . import ecr
from . import pac_v21_calibration as calibration
from . import pac_v2_runner as core
from . import pac_lws_screen as screen
from . import pac_scalp_policy as policy
from . import pac_scalp_marklog as marklog
from .pac_v2_snapshot import LandingSnapshot, SnapshotUnavailable, SOURCE as SNAPSHOT_SOURCE
from . import solusd_recorder


INSTRUMENT = "AFTERSHOCK_PAC_LWS"
SCHEMA = 1
PROBE_USD = "10"
N_MAX = 4
GROSS_NOTIONAL_CAP_LAMPORTS = 800_000_000          # <= 0.80 SOL deployed across the book
REENTRY_COOLDOWN_NANOS = 90_000_000_000
COVERAGE_MULTIPLE = 6                               # admission clause 4: real_quote >= 6x notional
K_SLOTS = screen.K_SLOTS                            # the B20B window length (60 slots), pinned via the screen
ENTRY_MARGIN_SLOTS = 2                              # entry only after the head advances past t0+60+margin
CORRELATED_DUMP_WINDOW_NANOS = 30_000_000_000
CORRELATED_DUMP_HALT_NANOS = 300_000_000_000
BUFFER_RETENTION_NANOS = 300_000_000_000            # keep the whole [t0,t0+60] window alive to entry time
EVENT_GRID_STEP_NANOS = 250_000_000                 # replay consumes events on this coarse grid
SLIPPAGE_BPS = core.SLIPPAGE_BPS
SLIPPAGE_DEN = core.SLIPPAGE_DEN
SCAN_INTERVAL_SECONDS = 0.10
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
DATA = ROOT / "research" / "data" / "aftershock" / "pac_lws"
FEED_EVENTS = DATA / "feed_events.jsonl"
FEED_REGISTRY = DATA / "creation_registry.jsonl"

OpenPosition = core.OpenPosition
_hash = core._hash
_CORE_LOCK = threading.RLock()

# --- pinned pump.fun bonding-curve constants, taken from the sealed ecr module (never re-guessed) ----
_VTOK_OFFSET = ecr.VIRTUAL_TOKEN_OFFSET            # virtual_token = real_token + this
_VQUOTE_OFFSET = ecr.VIRTUAL_QUOTE_OFFSET          # real_quote   = virtual_quote - this
_LAUNCH_REAL_TOKEN = 793_100_000_000_000           # pump.fun launch real_token (ecr pinned; all creates match)
_LAUNCH_VIRTUAL_QUOTE = _VQUOTE_OFFSET             # launch real_quote is 0, so virtual_quote == the offset
_LAUNCH_VIRTUAL_TOKEN = _LAUNCH_REAL_TOKEN + _VTOK_OFFSET
_CURVE_K = _LAUNCH_VIRTUAL_QUOTE * _LAUNCH_VIRTUAL_TOKEN   # constant-product invariant on the virtual reserves


def reconstruct_reserve_state(real_token: int) -> ReserveState:
    """Recover the full ``execution.ReserveState`` from the feed's ``real_token`` via the pinned curve.

    virtual_token = real_token + VIRTUAL_TOKEN_OFFSET ; virtual_quote = K // virtual_token (constant
    product) ; real_quote = virtual_quote - VIRTUAL_QUOTE_OFFSET.  Exact at t0 by construction (see the
    selftest's reconstruct-equals-create assertion); a sub-lamport floor residue accumulates over a
    life of trades, which is immaterial to the SOL-book pricing this feeds and is inherent to the
    reconstruction the feed's token-only payload permits."""
    if type(real_token) is not int or real_token < 0:
        raise RefusedExecution("PAC_LWS reserve reconstruction requires a non-negative integer real_token")
    virtual_token = real_token + _VTOK_OFFSET
    virtual_quote = _CURVE_K // virtual_token
    real_quote = virtual_quote - _VQUOTE_OFFSET
    if real_quote < 0:
        real_quote = 0
    return ReserveState(virtual_quote=virtual_quote, virtual_token=virtual_token,
                        real_quote=real_quote, real_token=real_token, complete=False)


@contextmanager
def _configured_core():
    """Stamp core's audited ledger/fill/resolve helpers with THIS instrument id so every row the reused
    single-position engine emits validates under AFTERSHOCK_PAC_LWS(_NULL), not PAC V2."""
    with _CORE_LOCK:
        original = core.INSTRUMENT
        core.INSTRUMENT = INSTRUMENT
        try:
            yield
        finally:
            core.INSTRUMENT = original


@dataclass(frozen=True)
class RuntimeProof:
    seal_sha256: str
    activation_unix_nanos: int
    calibration: calibration.Calibration

    def __post_init__(self) -> None:
        if (not isinstance(self.seal_sha256, str) or len(self.seal_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.seal_sha256)):
            raise RefusedExecution("PAC_LWS runtime seal hash is invalid")
        if type(self.activation_unix_nanos) is not int or self.activation_unix_nanos <= 0:
            raise RefusedExecution("PAC_LWS activation clock is invalid")
        if not isinstance(self.calibration, calibration.Calibration):
            raise RefusedExecution("PAC_LWS runtime lacks typed processed calibration")
        if max(self.calibration.last_processed_unix_nanos,
               self.calibration.last_attested_unix_nanos) >= self.activation_unix_nanos:
            raise RefusedExecution("PAC_LWS activation must follow inherited attested calibration")


# ==============================================================================================
# Replay curve-snapshot provider — reconstructs the landing reserve state from the captured feed.
# No network.  It is the deterministic stand-in for PublicRpcSnapshotProvider: given a modeled
# landing target and the virtual clock ``now``, it returns the reconstructed ReserveState of the
# latest feed event received by ``now`` (the state observed THEN — no lookahead).
# ==============================================================================================

class _NullPumpSwapProvider:
    """A never-graduates PumpSwap stand-in for replay (the curve feed is pre-graduation).  It carries
    the ``capture`` attribute the engine checks for; if ever called it fails closed as unavailable."""

    def capture(self, mint: str, minimum_context_slot: int):
        from .pac_v2_pumpswap import PumpSwapUnavailable
        raise PumpSwapUnavailable("PAC_LWS replay has no PumpSwap venue (curve feed is pre-graduation)")


class ReplayCurveSnapshotProvider:
    """Reconstruct the landing curve state from the captured feed events.  Not a live RPC read.

    The sealed ``LandingSnapshot`` type fixes ``source`` to the RPC snapshot label; that field is left
    at its default and ``endpoint_scheme_host`` is stamped ``replay://pac_lws_captured_feed`` so the
    provenance is unambiguous in every ledger row.  The whole ledger is a paper SCENARIO."""

    ENDPOINT = "replay://pac_lws_captured_feed"

    def __init__(self, events_by_mint: dict[str, list[dict]], bonding_curve_by_mint: dict[str, str]):
        # events_by_mint[mint] = ascending-by-received list of {"received": ns, "slot": int, "real_token": int}
        self._events = events_by_mint
        self._curve = bonding_curve_by_mint
        self.now = 0

    def capture(self, mint: str, modeled_target_unix_nanos: int,
                minimum_context_slot: int) -> LandingSnapshot:
        if (not isinstance(mint, str) or not mint or type(modeled_target_unix_nanos) is not int
                or modeled_target_unix_nanos < 0 or type(minimum_context_slot) is not int
                or minimum_context_slot < 0):
            raise RefusedExecution("PAC_LWS replay snapshot request is malformed")
        started = self.now
        if type(started) is not int or started < modeled_target_unix_nanos:
            raise RefusedExecution("PAC_LWS replay snapshot requested before modeled landing target")
        latest = None
        for event in self._events.get(mint, ()):
            if event["received"] <= self.now:
                latest = event
            else:
                break
        if latest is None:
            raise SnapshotUnavailable("PAC_LWS replay has no observed state for this mint yet")
        if latest["slot"] < minimum_context_slot:
            raise SnapshotUnavailable("PAC_LWS replay state predates the decision evidence slot")
        state = reconstruct_reserve_state(latest["real_token"])
        curve = self._curve.get(mint)
        if not curve:
            curve = _pseudo_curve(mint)
        raw_sha = hashlib.sha256(json.dumps(
            {"mint": mint, "slot": latest["slot"], "real_token": latest["real_token"],
             "now": self.now}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return LandingSnapshot(
            mint=mint, bonding_curve=curve, modeled_target_unix_nanos=modeled_target_unix_nanos,
            minimum_context_slot=minimum_context_slot, request_started_unix_nanos=started,
            response_received_unix_nanos=self.now, context_slot=latest["slot"], state=state,
            endpoint_scheme_host=self.ENDPOINT, raw_response_sha256=raw_sha, source=SNAPSHOT_SOURCE)


def _pseudo_curve(mint: str) -> str:
    """A stable, non-empty placeholder bonding-curve id for a mint whose registry row lacks one.
    Used only to satisfy the LandingSnapshot identity in replay; never an on-chain address."""
    return "replaycurve" + hashlib.sha256(mint.encode()).hexdigest()[:32]


# ==============================================================================================
# State
# ==============================================================================================

def _new_state(proof: RuntimeProof, *, veto_enabled: bool, event_offset: int) -> dict:
    return {
        "schema": SCHEMA, "instrument_id": INSTRUMENT,
        "seal_sha256": proof.seal_sha256, "activation_unix_nanos": proof.activation_unix_nanos,
        "calibration_sha256": proof.calibration.artifact_sha256,
        "reaction_p90_nanos": proof.calibration.processed_p90_nanos,
        "veto_enabled": bool(veto_enabled),
        "cursor": {"event_offset": event_offset},
        "buffers": {}, "creation": {}, "open_positions": {}, "pending_orders": {},
        "cooldowns": {}, "recent_stops": [], "halt_new_entries_until": 0,
        "decided_mints": [], "pending_ledger_rows": [], "last_status": None,
    }


def _single_view(state: dict, *, open_position=None, pending_order=None) -> dict:
    """A one-slot state that core's audited fill/resolve/graduation helpers can operate on."""
    return {
        "schema": core.SCHEMA, "instrument_id": INSTRUMENT,
        "seal_sha256": state["seal_sha256"], "activation_unix_nanos": state["activation_unix_nanos"],
        "calibration_sha256": state["calibration_sha256"],
        "reaction_p90_nanos": state["reaction_p90_nanos"],
        "open_position": open_position, "pending_order": pending_order,
        "pending_ledger_rows": [],
    }


# ==============================================================================================
# Feed consumption — the pac_lws creation-anchored feed (NOT pac_v22).  Incremental, clock-bounded.
# ==============================================================================================

def _load_registry(registry_path: pathlib.Path) -> dict[str, dict]:
    creation: dict[str, dict] = {}
    if not pathlib.Path(registry_path).exists():
        return creation
    with pathlib.Path(registry_path).open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            mint = row.get("mint")
            if isinstance(mint, str) and mint not in creation:
                creation[mint] = {
                    "t0_slot": row.get("t0_slot"), "dev_wallet": row.get("dev_wallet"),
                    "bonding_curve": row.get("bonding_curve"),
                    "seedable": bool(row.get("seedable")),
                }
    return creation


def _consume(state: dict, *, now: int, events_path: pathlib.Path) -> list[dict]:
    """Read new feed events with received_unix_nanos <= now, advancing the byte cursor only past them.

    Returns the list of consumed pac_lws event dicts (minimal, screen/pricing-ready).  Relies on the
    feed being appended in non-decreasing received order (the collector stamps receive time before
    decode), exactly as a live tail would see it."""
    events_path = pathlib.Path(events_path)
    if not events_path.exists():
        return []
    consumed: list[dict] = []
    offset = state["cursor"]["event_offset"]
    with events_path.open("rb") as handle:
        handle.seek(offset)
        while True:
            line_start = handle.tell()
            raw = handle.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                # a partial final line (writer mid-append): stop, do not advance past it
                handle.seek(line_start)
                break
            text = raw.strip()
            if not text:
                offset = handle.tell()
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                offset = handle.tell()
                continue
            received = row.get("received_unix_nanos")
            if type(received) is not int:
                offset = handle.tell()
                continue
            if received > now:
                handle.seek(line_start)
                break
            offset = handle.tell()
            consumed.append({
                "mint": row.get("mint"), "slot": row.get("slot"), "trader": row.get("trader"),
                "is_buy": bool(row.get("is_buy")), "token_amount": row.get("token_amount"),
                "post_real_token": row.get("post_real_token"),
                "pre_real_token": row.get("pre_real_token"),
                "reserve_delta_tokens": row.get("reserve_delta_tokens"),
                "reconciled": row.get("reconciled"), "anchored": bool(row.get("anchored")),
                "t0_slot": row.get("t0_slot"), "received_unix_nanos": received,
            })
    state["cursor"]["event_offset"] = offset
    return consumed


def _update_buffers(state: dict, events: list[dict], creation: dict[str, dict], *, now: int) -> None:
    """Append per-mint events, learn creation anchors, and passively refresh every held slot's state."""
    for event in events:
        mint = event.get("mint")
        if not isinstance(mint, str) or not mint:
            continue
        if mint in creation and mint not in state["creation"]:
            state["creation"][mint] = creation[mint]
        state["buffers"].setdefault(mint, []).append(event)
        slot = state["open_positions"].get(mint)
        if slot is not None and isinstance(event.get("post_real_token"), int):
            slot["last_state"] = asdict(reconstruct_reserve_state(event["post_real_token"]))
            if isinstance(event.get("slot"), int):
                slot["last_context_slot"] = max(slot["last_context_slot"], event["slot"])
    held = set(state["open_positions"]) | {o["mint"] for o in state["pending_orders"].values()}
    decided = set(state["decided_mints"])
    cutoff = now - BUFFER_RETENTION_NANOS
    for mint in list(state["buffers"]):
        # Once a mint has been decided (admitted/vetoed) or is held, the full [t0,t0+60] window is no
        # longer needed — only the latest event, for the open slot's last_state refresh.  Keeping the
        # whole window for every mint forever is what makes the rewritten state O(all events); this cap
        # keeps the persisted state small without ever discarding a window before it is scored.
        if mint in held or mint in decided:
            state["buffers"][mint] = [state["buffers"][mint][-1]] if state["buffers"][mint] else []
            continue
        kept = [it for it in state["buffers"][mint]
                if it.get("received_unix_nanos", 0) >= cutoff]
        if kept:
            state["buffers"][mint] = kept
        else:
            del state["buffers"][mint]
            state["creation"].pop(mint, None)


def _window_trades(events: list[dict], t0_slot: int) -> list[screen.WindowTrade]:
    """Decode the [t0, t0+K_SLOTS] buffer into screen.WindowTrade (the veto reads only this window)."""
    trades: list[screen.WindowTrade] = []
    for event in events:
        slot = event.get("slot")
        if type(slot) is not int or not (t0_slot <= slot <= t0_slot + K_SLOTS):
            continue
        token_amount = event.get("token_amount")
        trader = event.get("trader")
        if type(token_amount) is not int or not isinstance(trader, str) or not trader:
            continue
        trades.append(screen.WindowTrade(
            slot=slot, trader=trader, is_buy=bool(event.get("is_buy")),
            token_amount=token_amount,
            reserve_delta_tokens=event.get("reserve_delta_tokens")))
    return trades


# ==============================================================================================
# Fill / service — delegate byte-identically to the audited single-position core.
# ==============================================================================================

def _complete_pending_orders(state: dict, provider, pumpswap_provider, *, now: int) -> list[dict]:
    rows: list[dict] = []
    for decision_id, pending in list(state["pending_orders"].items()):
        if now < pending["target_unix_nanos"]:
            continue
        mint = pending["mint"]
        slot = state["open_positions"].get(mint)
        view = _single_view(state, open_position=slot, pending_order=pending)
        produced = core._complete_pending(view, provider, pumpswap_provider, now=now)
        rows.extend(produced)
        if view["pending_order"] is None:
            state["pending_orders"].pop(decision_id, None)
        else:
            state["pending_orders"][decision_id] = view["pending_order"]
        if view["open_position"] is None:
            if slot is not None and any(r["kind"] == "resolved" for r in produced):
                state["open_positions"].pop(mint, None)
                state["cooldowns"][mint] = now + REENTRY_COOLDOWN_NANOS
                if any(r.get("action") == policy.ExitAction.EXIT_HARD_STOP.value for r in produced):
                    state["recent_stops"].append(now)
        else:
            state["open_positions"][mint] = view["open_position"]
    return rows


def _record_mark(position: OpenPosition, *, now: int, net, real_quote, venue: str,
                 marks_path: pathlib.Path) -> None:
    marklog.record(
        entry_id=position.entry_id, mint=position.mint, observed_unix_nanos=now,
        context_slot=position.last_context_slot, entry_all_in_lamports=position.entry_all_in_lamports,
        net_exit_lamports=net, real_quote_lamports=real_quote,
        peak_net_exit_lamports=position.peak_net_exit_lamports, venue=venue,
        priceable=net is not None, path=marks_path)


def _service_positions(state: dict, provider, pumpswap_provider, *, now: int,
                       marks_path: pathlib.Path) -> list[dict]:
    rows: list[dict] = []
    for mint, raw in list(state["open_positions"].items()):
        if any(o["mint"] == mint for o in state["pending_orders"].values()):
            continue
        position = OpenPosition(**raw)
        if now < position.entry_unix_nanos:
            continue
        view = _single_view(state, open_position=asdict(position))
        transition = core._refresh_and_check_graduation(
            view, position, provider, pumpswap_provider, now=now)
        if view["open_position"] is None and view["pending_order"] is not None:
            rows.extend(transition or [])
            state["pending_orders"][view["pending_order"]["decision_id"]] = view["pending_order"]
            state["open_positions"].pop(mint, None)
            continue
        if transition is not None:
            rows.extend(transition)
            state["open_positions"][mint] = view["open_position"]
            continue
        position = OpenPosition(**view["open_position"])
        reserve = ReserveState(**position.last_state)
        intent = OrderIntent(IntentKind.EXACT_TOKEN_SELL, position.token_atoms, 1)
        try:
            quote = kernel_accounting(reserve, intent)
            net = quote["wallet_delta_lamports"]
            if net <= 0:
                net = None
        except PriceUnavailable:
            quote = None
            net = None
        _record_mark(position, now=now, net=net,
                     real_quote=(reserve.real_quote if net is not None else None),
                     venue="CURVE", marks_path=marks_path)
        decision_position = policy.Position(
            position.token_atoms, position.quote_input_lamports, position.entry_all_in_lamports,
            position.entry_unix_nanos, position.peak_net_exit_lamports)
        try:
            outcome = policy.decide(decision_position, now_unix_nanos=now, net_exit_lamports=net,
                                    real_quote_lamports=(reserve.real_quote if net is not None else None))
        except ValueError as exc:
            raise RefusedExecution("PAC_LWS exit policy refused an invalid causal clock/quote") from exc
        position.peak_net_exit_lamports = outcome.position.peak_net_exit_lamports
        state["open_positions"][mint] = asdict(position)
        if outcome.action == policy.ExitAction.HOLD:
            continue
        if outcome.action == policy.ExitAction.UNEXITABLE_FULL_LOSS:
            state["open_positions"].pop(mint, None)
            state["cooldowns"][mint] = now + REENTRY_COOLDOWN_NANOS
            view = _single_view(state, open_position=asdict(position))
            rows.append(core._resolve_full_loss(view, position, now=now,
                        action=outcome.action.value, reason="OBSERVED_STATE_UNPRICEABLE"))
            continue
        decision_id = _hash({"instrument": INSTRUMENT, "side": "EXIT", "mint": position.mint,
                             "entry_id": position.entry_id, "action": outcome.action.value,
                             "decision_unix_nanos": now, "net_quote": net})
        state["pending_orders"][decision_id] = {
            "side": "EXIT", "mint": position.mint, "amount": position.token_atoms,
            "min_out": max(1, quote["out_amount"] * (SLIPPAGE_DEN - SLIPPAGE_BPS) // SLIPPAGE_DEN),
            "decision_id": decision_id, "decision_unix_nanos": now,
            "target_unix_nanos": now + state["reaction_p90_nanos"],
            "minimum_context_slot": position.last_context_slot,
            "action": outcome.action.value, "entry_id": position.entry_id,
            "observation_failures": 0, "last_observation_failure": None}
        rows.append(core._ledger_row(state, "exit_decision", {
            "mint": position.mint, "entry_id": position.entry_id, "decision_id": decision_id,
            "action": outcome.action.value, "decision_unix_nanos": now,
            "target_unix_nanos": now + state["reaction_p90_nanos"],
            "minimum_context_slot": position.last_context_slot, "decision_net_exit_lamports": net}))
    return rows


# ==============================================================================================
# Admission — coverage floor (clause 4) ONLY, plus the B20B veto on the veto arm.
# ==============================================================================================

def _deployed_notional(state: dict) -> int:
    total = sum(p["quote_input_lamports"] for p in state["open_positions"].values())
    total += sum(o["amount"] for o in state["pending_orders"].values() if o["side"] == "ENTRY")
    return total


def _admit_candidates(state: dict, *, now: int, quote_input_lamports: int) -> list[dict]:
    if now < state.get("halt_new_entries_until", 0):
        return []
    entering = {o["mint"] for o in state["pending_orders"].values() if o["side"] == "ENTRY"}
    free = N_MAX - len(state["open_positions"]) - len(entering)
    if free <= 0:
        return []
    state["cooldowns"] = {m: t for m, t in state["cooldowns"].items() if t > now}
    rows: list[dict] = []
    decided = set(state["decided_mints"])
    candidates = []
    for mint, events in state["buffers"].items():
        if (mint in state["open_positions"] or mint in entering or mint in state["cooldowns"]
                or mint in decided):
            continue
        info = state["creation"].get(mint)
        if not info or not info.get("seedable"):
            continue
        t0 = info.get("t0_slot")
        if type(t0) is not int:
            continue
        # fail-closed: the mint's continuity from t0 must be proven (anchored + first-trade reconciled).
        if any((not e.get("anchored")) or (e.get("reconciled") is False) for e in events):
            continue
        if any(e.get("reconciled") is None for e in events):
            continue
        max_slot = max((e["slot"] for e in events if isinstance(e.get("slot"), int)), default=None)
        if max_slot is None or max_slot <= t0 + K_SLOTS + ENTRY_MARGIN_SLOTS:
            continue  # window not yet strictly closed with margin -> no entry (and no lookahead)
        # the decision event: the latest post-window event we have actually observed.
        post_window = [e for e in events
                       if isinstance(e.get("slot"), int) and e["slot"] > t0 + K_SLOTS
                       and isinstance(e.get("post_real_token"), int)]
        if not post_window:
            continue
        candidates.append((max(e["received_unix_nanos"] for e in post_window), mint, events, info,
                           post_window[-1], t0))
    candidates.sort(key=lambda c: c[0])
    for _src, mint, events, info, decision_event, t0 in candidates:
        if free <= 0:
            break
        # --- the B20B veto (computed on both arms; DECISIONAL only when veto_enabled) ---
        window_trades = _window_trades(events, t0)
        verdict = screen.evaluate(window_trades, t0_slot=t0, dev_wallet=info.get("dev_wallet"))
        veto_body = {"filter": verdict.status, "flagged": verdict.flagged,
                     "buyers": verdict.buyers, "top_share_bps": verdict.top_share_bps,
                     "window_trades": len(window_trades), "dropped_crosscheck": verdict.dropped_crosscheck,
                     "shadow": verdict.shadow, "veto_enabled": state["veto_enabled"]}
        state["decided_mints"].append(mint)
        if state["veto_enabled"] and not verdict.enter_allowed:
            rows.append(core._ledger_row(state, "entry_vetoed", {
                "mint": mint, "t0_slot": t0, "decision_unix_nanos": now, **veto_body}))
            continue
        # --- admission clause 4 ONLY: live-bid exit-impact coverage floor ---
        decision_state = reconstruct_reserve_state(decision_event["post_real_token"])
        if decision_state.real_quote < COVERAGE_MULTIPLE * quote_input_lamports:
            rows.append(core._ledger_row(state, "entry_rejected", {
                "mint": mint, "t0_slot": t0, "decision_unix_nanos": now,
                "reason": "COVERAGE_FLOOR", "real_quote_lamports": decision_state.real_quote,
                "coverage_floor_lamports": COVERAGE_MULTIPLE * quote_input_lamports, **veto_body}))
            continue
        if _deployed_notional(state) + quote_input_lamports > GROSS_NOTIONAL_CAP_LAMPORTS:
            state["decided_mints"].remove(mint)   # not decided; the book is simply full this cycle
            break
        intent = OrderIntent(IntentKind.EXACT_QUOTE_BUY, quote_input_lamports, 1)
        try:
            decision_quote = kernel_accounting(decision_state, intent)
        except PriceUnavailable:
            rows.append(core._ledger_row(state, "entry_rejected", {
                "mint": mint, "t0_slot": t0, "decision_unix_nanos": now,
                "reason": "DECISION_STATE_UNPRICEABLE", **veto_body}))
            continue
        decision_id = _hash({"instrument": INSTRUMENT, "side": "ENTRY", "mint": mint,
                             "decision_unix_nanos": now, "t0_slot": t0,
                             "quote_input_lamports": quote_input_lamports})
        state["pending_orders"][decision_id] = {
            "side": "ENTRY", "mint": mint, "amount": quote_input_lamports,
            "min_out": max(1, decision_quote["out_amount"] * (SLIPPAGE_DEN - SLIPPAGE_BPS) // SLIPPAGE_DEN),
            "decision_id": decision_id, "decision_unix_nanos": now,
            "target_unix_nanos": now + state["reaction_p90_nanos"], "action": None,
            "minimum_context_slot": max(e["slot"] for e in events if isinstance(e.get("slot"), int)),
            "entry_id": None, "observation_failures": 0, "last_observation_failure": None}
        rows.append(core._ledger_row(state, "entry_decision", {
            "mint": mint, "decision_id": decision_id, "decision_unix_nanos": now, "t0_slot": t0,
            "target_unix_nanos": now + state["reaction_p90_nanos"],
            "minimum_context_slot": state["pending_orders"][decision_id]["minimum_context_slot"],
            "quote_input_lamports": quote_input_lamports,
            "coverage_real_quote_lamports": decision_state.real_quote, **veto_body}))
        free -= 1
    return rows


def _apply_correlated_breaker(state: dict, *, now: int) -> None:
    window = [t for t in state["recent_stops"] if t > now - CORRELATED_DUMP_WINDOW_NANOS]
    state["recent_stops"] = window
    open_and_recent = len(state["open_positions"]) + len(window)
    if open_and_recent > 0 and len(window) * 2 >= max(1, open_and_recent):
        if len(window) >= 2:
            state["halt_new_entries_until"] = now + CORRELATED_DUMP_HALT_NANOS


# ==============================================================================================
# One cycle
# ==============================================================================================

def _run_once_at(proof: RuntimeProof, provider, pumpswap_provider, *, now: int,
                 veto_enabled: bool, quote_input_lamports: int,
                 state_path: pathlib.Path, ledger_path: pathlib.Path,
                 marks_path: pathlib.Path, events_path: pathlib.Path = FEED_EVENTS,
                 registry_path: pathlib.Path = FEED_REGISTRY,
                 initialize_at_eof: bool = True) -> dict:
    if (not all(hasattr(proof, a) for a in ("activation_unix_nanos", "calibration", "seal_sha256"))
            or not hasattr(provider, "capture") or not hasattr(pumpswap_provider, "capture")):
        raise RefusedExecution("PAC_LWS run requires runtime proof and both venue providers")
    if type(now) is not int or now <= proof.activation_unix_nanos:
        raise RefusedExecution("PAC_LWS runner clock is not post-activation")
    if type(quote_input_lamports) is not int or quote_input_lamports <= 0:
        raise RefusedExecution("PAC_LWS quote input is invalid")
    state_path = pathlib.Path(state_path); ledger_path = pathlib.Path(ledger_path)
    if not state_path.exists():
        eo = (pathlib.Path(events_path).stat().st_size
              if initialize_at_eof and pathlib.Path(events_path).exists() else 0)
        core._atomic_write(state_path, _new_state(proof, veto_enabled=veto_enabled, event_offset=eo))
        return {"status": "INITIALIZED_NO_BACKFILL", "open": 0, "pending": 0, "new_events": 0}
    try:
        state = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("PAC_LWS runner state is unreadable") from exc
    if (state.get("seal_sha256") != proof.seal_sha256
            or state.get("calibration_sha256") != proof.calibration.artifact_sha256):
        raise RefusedExecution("PAC_LWS runner state is bound to a different seal/calibration")
    if bool(state.get("veto_enabled")) != bool(veto_enabled):
        raise RefusedExecution("PAC_LWS runner state veto flag does not match the activation")
    creation = _load_registry(registry_path)
    with _configured_core():
        core._flush(state, state_path=state_path, ledger_path=ledger_path)
        new_events = _consume(state, now=now, events_path=events_path)
        _update_buffers(state, new_events, creation, now=now)
        rows = _complete_pending_orders(state, provider, pumpswap_provider, now=now)
        rows += _service_positions(state, provider, pumpswap_provider, now=now, marks_path=marks_path)
        _apply_correlated_breaker(state, now=now)
        rows += _admit_candidates(state, now=now, quote_input_lamports=quote_input_lamports)
        state["last_status"] = (
            f"BOOK_{len(state['open_positions'])}_OPEN_{len(state['pending_orders'])}_PENDING"
            if state["open_positions"] or state["pending_orders"] else "SCANNING")
        core._commit(state, rows, state_path=state_path, ledger_path=ledger_path)
    return {"status": state["last_status"], "open": len(state["open_positions"]),
            "pending": len(state["pending_orders"]), "new_events": len(new_events),
            "ledger_rows": len(rows)}


# ==============================================================================================
# Replay — feed the captured events through _run_once_at on a monotonic virtual clock (NO network).
# ==============================================================================================

def replay(*, events_path: pathlib.Path, registry_path: pathlib.Path, veto_enabled: bool,
           state_path: pathlib.Path, ledger_path: pathlib.Path, marks_path: pathlib.Path,
           quote_input_lamports: int, processed_p90_nanos: int = 3_788_307_712) -> dict:
    """Deterministic replay over the captured feed.  Produces a real, hash-chained ledger."""
    events_path = pathlib.Path(events_path); registry_path = pathlib.Path(registry_path)
    for stale in (state_path, ledger_path, marks_path):
        pathlib.Path(stale).unlink(missing_ok=True)

    rows = [json.loads(l) for l in events_path.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if isinstance(r.get("received_unix_nanos"), int)]
    rows.sort(key=lambda r: (r["received_unix_nanos"], r.get("seq", 0)))
    if not rows:
        raise RefusedExecution("PAC_LWS replay: the captured feed has no usable events")
    registry = _load_registry(registry_path)

    events_by_mint: dict[str, list[dict]] = {}
    for r in rows:
        mint = r.get("mint")
        if isinstance(mint, str) and isinstance(r.get("slot"), int) and isinstance(r.get("post_real_token"), int):
            events_by_mint.setdefault(mint, []).append(
                {"received": r["received_unix_nanos"], "slot": r["slot"],
                 "real_token": r["post_real_token"]})
    for series in events_by_mint.values():
        series.sort(key=lambda e: e["received"])
    bonding_curve_by_mint = {m: info.get("bonding_curve") for m, info in registry.items()
                             if info.get("bonding_curve")}

    provider = ReplayCurveSnapshotProvider(events_by_mint, bonding_curve_by_mint)
    pumpswap = _NullPumpSwapProvider()

    first_received = rows[0]["received_unix_nanos"]
    activation = first_received - 1_000_000_000
    if activation <= 0:
        activation = 1
    calib = calibration.Calibration(
        artifact_sha256=hashlib.sha256(b"PAC_LWS_REPLAY_CALIBRATION").hexdigest(),
        attestation_sha256=hashlib.sha256(b"PAC_LWS_REPLAY_ATTEST").hexdigest(),
        campaign_sha256=hashlib.sha256(b"PAC_LWS_REPLAY_CAMPAIGN").hexdigest(),
        campaign_id="pac_lws_replay", processed_samples=1, failed_samples=0,
        processed_p90_nanos=int(processed_p90_nanos),
        first_decision_unix_nanos=activation - 3, last_processed_unix_nanos=activation - 2,
        last_attested_unix_nanos=activation - 2)
    proof = RuntimeProof(seal_sha256=hashlib.sha256(b"PAC_LWS_REPLAY_SEAL").hexdigest(),
                         activation_unix_nanos=activation, calibration=calib)

    common = dict(veto_enabled=veto_enabled, quote_input_lamports=quote_input_lamports,
                  state_path=state_path, ledger_path=ledger_path, marks_path=marks_path,
                  events_path=events_path, registry_path=registry_path, initialize_at_eof=False)
    provider.now = activation + 1
    _run_once_at(proof, provider, pumpswap, now=activation + 1, **common)   # initialize at offset 0

    # The reused core fsyncs state+ledger every cycle, so ticking at each of the thousands of distinct
    # event receive-times is needlessly slow.  Consume events on a coarse grid (a decision is only
    # quantised to this step, an honest sub-second rounding), while pending fills still land on their
    # own fine target+margin ticks below — so the decision->fill gap stays governed by processed_p90.
    first = rows[0]["received_unix_nanos"]; last = rows[-1]["received_unix_nanos"]
    step = EVENT_GRID_STEP_NANOS
    event_times = sorted(set(range(first, last + step, step)) | {last})
    margin = 1_000
    idx = 0
    last_now = activation + 1
    cycles = 0
    guard = 20 * len(event_times) + 400_000
    while True:
        cycles += 1
        if cycles > guard:
            break
        state = json.loads(pathlib.Path(state_path).read_text())
        pending = list(state["pending_orders"].values())
        opens = list(state["open_positions"].values())
        nexts: list[int] = []
        if idx < len(event_times):
            nexts.append(event_times[idx])
        for po in pending:
            nexts.append(po["target_unix_nanos"] + margin)
        if opens:
            nexts.append(min(p["entry_unix_nanos"] + policy.MAX_HOLD_NANOS for p in opens) + margin)
        nexts = [t for t in nexts if t > last_now]
        if not nexts:
            if idx >= len(event_times) and not pending and not opens:
                break
            nexts = [last_now + max(1, int(processed_p90_nanos))]
        now = min(nexts)
        provider.now = now
        _run_once_at(proof, provider, pumpswap, now=now, **common)
        while idx < len(event_times) and event_times[idx] <= now:
            idx += 1
        last_now = now
        state = json.loads(pathlib.Path(state_path).read_text())
        if (idx >= len(event_times) and not state["pending_orders"]
                and not state["open_positions"]):
            break
    return book_from_ledger(ledger_path)


def book_from_ledger(ledger_path: pathlib.Path) -> dict:
    """Census the produced ledger: admissions, vetoes, resolutions, and the net-SOL book."""
    ledger_path = pathlib.Path(ledger_path)
    counts = {"entry_decision": 0, "entry_filled": 0, "entry_vetoed": 0, "entry_rejected": 0,
              "exit_decision": 0, "resolved": 0}
    veto_by_filter: dict[str, int] = {}
    reject_by_reason: dict[str, int] = {}
    net_return_lamports = 0
    full_losses = 0
    resolved_actions: dict[str, int] = {}
    if ledger_path.exists():
        for line in ledger_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            kind = row.get("kind")
            if kind in counts:
                counts[kind] += 1
            if kind == "entry_vetoed":
                veto_by_filter[row.get("filter")] = veto_by_filter.get(row.get("filter"), 0) + 1
            if kind == "entry_rejected":
                reject_by_reason[row.get("reason")] = reject_by_reason.get(row.get("reason"), 0) + 1
            if kind == "resolved":
                net_return_lamports += int(row.get("net_return_num", 0))
                full_losses += int(bool(row.get("unexitable_full_loss")))
                resolved_actions[row.get("action")] = resolved_actions.get(row.get("action"), 0) + 1
    return {
        "counts": counts, "veto_by_filter": veto_by_filter, "reject_by_reason": reject_by_reason,
        "resolved_actions": resolved_actions, "unexitable_full_losses": full_losses,
        "net_book_lamports": net_return_lamports,
        "net_book_sol": round(net_return_lamports / 1_000_000_000, 6),
    }


def _quote_input(now: int) -> int:
    observation = solusd_recorder.latest_observation(decision_unix_nanos=now)
    return q_lamports_for_usd(PROBE_USD, observation, decision_unix_nanos=now,
                              max_staleness_nanos=solusd_recorder.MAX_LOCAL_AGE_NANOS)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC Launch-Window Sentinel Scalper (paper-scenario)")
    sub = parser.add_subparsers(dest="command")
    rp = sub.add_parser("replay", help="deterministic replay over a captured feed (no network)")
    rp.add_argument("events_path")
    rp.add_argument("registry_path")
    rp.add_argument("--veto", dest="veto", action="store_true", help="veto arm (LWS)")
    rp.add_argument("--no-veto", dest="veto", action="store_false", help="null arm (LWS_NULL)")
    rp.set_defaults(veto=True)
    rp.add_argument("--quote-lamports", type=int, default=50_000_000)
    rp.add_argument("--out-dir", default=str(DATA / "replay"))
    args = parser.parse_args(argv)
    if args.command != "replay":
        parser.print_help()
        return 2
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = "AFTERSHOCK_PAC_LWS" if args.veto else "AFTERSHOCK_PAC_LWS_NULL"
    result = replay(
        events_path=pathlib.Path(args.events_path), registry_path=pathlib.Path(args.registry_path),
        veto_enabled=args.veto, quote_input_lamports=args.quote_lamports,
        state_path=out / f"{tag}_RUNNER_STATE.json",
        ledger_path=out / f"{tag}_SCENARIO_LEDGER.jsonl",
        marks_path=out / f"marks_{tag}.jsonl")
    print(json.dumps({"instrument": tag, "veto_enabled": args.veto, **result},
                     indent=2, sort_keys=True))
    return 0


def _lock(path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RefusedExecution("another PAC_LWS runner owns the state lock") from exc
    return handle


if __name__ == "__main__":
    raise SystemExit(main())
