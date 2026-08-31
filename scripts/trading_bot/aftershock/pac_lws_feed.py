#!/usr/bin/env python3
"""PAC Launch-Window Sentinel Scalper — the CREATION-ANCHORED collector (PAPER / READ-ONLY).

Why this module exists
----------------------
The momentum-scalp feed (``pac_v22_feed`` / PumpPortal) observes tokens **mid-life**: the first
trade it captures for a mint is already at roughly ``0.88x`` of fresh reserves for ~96% of mints, so
the *first-60-slots-from-creation* buyer set that the validated B20B deadness screen
(``pac_lws_screen``) needs is MISSED for ~96% of tokens.  A screen that has to see every buyer in
``[t0, t0+60]`` cannot run on a feed that only ever joins after t0.

This collector fixes the anchoring problem at the source.  It subscribes to the pump.fun program log
stream at ``processed`` commitment and, for **every mint**, learns the mint from its own
``CreateEvent`` at slot ``t0`` (``context.slot``).  From that create it SEEDS the per-mint reserve
state with the event's ``real_token_reserves`` (the t0 reserve), so the very first on-chain trade —
frequently the dev buy in the same transaction — reconciles against a known t0 baseline.  A trade
whose reserve movement matches its signed ``token_amount`` proves continuity from creation; one that
does not is marked ``reconciled=false`` and is EXCLUDED from scoring downstream (fail-closed).

What it does NOT do
-------------------
No wallet, no signer, no order path, no ``getAccountInfo``/state-read RPC on the feed thread.  The
only RPC anywhere in this module is a ``getSlot`` head poll on a SEPARATE daemon thread, which drives
a fail-closed head-lag gate (we never admit an event we cannot place near the chain tip).  Every raw
frame is stamped and persisted BEFORE it is decoded, so the raw evidence survives any later defect.

Reuse (all byte-unchanged, by import — no sealed module is edited)
-----------------------------------------------------------------
* ``scripts.b15a_shadow_pilot`` (create decode): ``PUMP_PROGRAM``, ``program_data_payloads``,
  ``load_pinned_create_type`` -> ``(b7d, discriminator, create_type, types)``, ``decode_create`` ->
  ``(status, fields, error)``, ``DECODE_DECODED``, and ``state_from_create_event(fields, slot)``
  which maps ``real_token_reserves`` -> ``real_token`` (the t0 reserve used as the seed).
* ``scripts.trading_bot.sniper.data._common`` (trade decode): ``decode_pump_trades_from_logs`` ->
  per-trade dicts with ``mint, side, user, token_amount`` (ATOMS), ``real_tok`` (post real token
  reserve), ``sol_amount``; and ``read_env`` for the funded Helius credential (never printed).
* ``scripts.b15i_processed_feed``: ``RawLog`` (append-only, per-frame-flushed raw log) and
  ``assert_feed_thread_does_not_call_rpc`` (source-checked guard that the frame handler never awaits
  an RPC).
* ``scripts.b15a_websocket``: ``WebSocket`` / ``WebSocketRefused``.

Outputs (all under ``research/data/aftershock/pac_lws/``)
* ``raw_frames.jsonl``       — every notification, raw, stamped before decode.
* ``creation_registry.jsonl``— one durable row per observed CreateEvent (the t0 anchor).
* ``feed_events.jsonl``      — hash-chained per-trade events, consumable by ``pac_lws_screen``.
* ``reconciliations.jsonl``  — one row per mint's first trade (the reconciliation verdict).
* ``sessions.jsonl``         — one row per collector epoch (a reconnect starts a new epoch).
* ``feed_health.json``       — this collector's own health (id ``AFTERSHOCK_PAC_LWS_FEED``).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid

from scripts import b15a_websocket as ws_client
from scripts import b15a_shadow_pilot as pilot
from scripts import b15i_processed_feed as b15i
from scripts.trading_bot.aftershock.execution import RefusedExecution

# ---- one shared _common instance, loaded by path (repo idiom; see pac_v2_feed) ----------------
ROOT = pathlib.Path(__file__).resolve().parents[3]
_COMMON_PATH = pathlib.Path(__file__).resolve().parents[1] / "sniper" / "data" / "_common.py"
_COMMON_SPEC = importlib.util.spec_from_file_location("pac_lws_sniper_common", _COMMON_PATH)
_COMMON = importlib.util.module_from_spec(_COMMON_SPEC)
sys.modules.setdefault("pac_lws_sniper_common", _COMMON)
_COMMON_SPEC.loader.exec_module(_COMMON)

decode_pump_trades_from_logs = _COMMON.decode_pump_trades_from_logs
read_env = _COMMON.read_env
SOL_USD_DEFAULT = _COMMON.SOL_USD_DEFAULT
PUMP_PROGRAM = pilot.PUMP_PROGRAM

# ---- identity + paths -------------------------------------------------------------------------
INSTRUMENT_ID = "AFTERSHOCK_PAC_LWS_FEED"
SCHEMA = 1
DATA = ROOT / "research" / "data" / "aftershock" / "pac_lws"
RAW = DATA / "raw_frames.jsonl"
CREATION_REGISTRY = DATA / "creation_registry.jsonl"
EVENTS = DATA / "feed_events.jsonl"
RECONCILIATIONS = DATA / "reconciliations.jsonl"
SESSIONS = DATA / "sessions.jsonl"
HEALTH = DATA / "feed_health.json"

GENESIS_HASH = "0" * 64

# ---- head-lag gate constants (fail-closed) ----------------------------------------------------
MAX_HEAD_SLOT_LAG = 32           # the event slot may trail the processed head by at most this many
MAX_HEAD_AGE_NANOS = 5_000_000_000
MAX_HEALTH_AGE_NANOS = 5_000_000_000
HEAD_POLL_SECONDS = 1.0

# ---- reconciliation tolerance -----------------------------------------------------------------
# pump.fun token reserves move by EXACTLY the trade's token_amount (no token-side fee; fees are in
# SOL), so the seeded-create reconciliation is exact.  A tolerance is exposed only so a future
# provider quirk can be measured rather than silently absorbed; it defaults to zero.
RECON_ROUNDING_ATOMS = 0

# Names whose presence would mean an execution/wallet surface had appeared in THIS file. Checked
# against the source at startup, exactly as the sealed observers do — a promise kept in a comment
# stops being true the moment somebody edits the file.
EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")


# ==============================================================================================
# Startup gates
# ==============================================================================================

def assert_no_execution_surface(path: pathlib.Path | None = None) -> bool:
    """This file observes and records; it never holds a key, signs, builds, or submits anything."""
    target = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = target.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise RefusedExecution(f"an execution surface appeared in {target.name}: {found}")
    return True


# ==============================================================================================
# Health writer — this collector's OWN identity and path (never pac_v22_feed.write_health)
# ==============================================================================================

def _canonical_sha(body: dict) -> str:
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _append(path: pathlib.Path, row: dict) -> None:
    """One durable append: fsynced, and the directory fsynced on first create."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError(f"short append {written}/{len(payload)}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if not existed:
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _atomic_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short PAC_LWS health write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _health_body(*, status: str, epoch: str, observed_unix_nanos: int,
                 head_slot: int | None, event_slot: int | None, reason: str | None) -> dict:
    if status not in {"FRESH", "DEGRADED"} or not isinstance(epoch, str) or not epoch:
        raise RefusedExecution("PAC_LWS health identity is invalid")
    if type(observed_unix_nanos) is not int or observed_unix_nanos <= 0:
        raise RefusedExecution("PAC_LWS health clock is invalid")
    for value in (head_slot, event_slot):
        if value is not None and (type(value) is not int or value < 0):
            raise RefusedExecution("PAC_LWS health slot is invalid")
    lag = None if head_slot is None or event_slot is None else max(0, head_slot - event_slot)
    return {
        "schema": SCHEMA, "instrument_id": INSTRUMENT_ID,
        "status": status, "collector_epoch": epoch,
        "observed_unix_nanos": observed_unix_nanos,
        "head_slot": head_slot, "event_slot": event_slot, "head_slot_lag": lag,
        "reason": reason,
    }


def write_health(*, status: str, epoch: str, observed_unix_nanos: int,
                 head_slot: int | None, event_slot: int | None, reason: str | None,
                 path: pathlib.Path = HEALTH) -> dict:
    body = _health_body(status=status, epoch=epoch, observed_unix_nanos=observed_unix_nanos,
                        head_slot=head_slot, event_slot=event_slot, reason=reason)
    row = {**body, "health_sha256": _canonical_sha(body)}
    _atomic_json(path, row)
    return row


def load_health(path: pathlib.Path | None = None, *, now: int | None = None,
                require_fresh: bool = False) -> dict:
    clock = time.time_ns() if now is None else now
    target = HEALTH if path is None else pathlib.Path(path)
    try:
        row = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("PAC_LWS feed health is unreadable") from exc
    if not isinstance(row, dict) or set(row) != {
            "schema", "instrument_id", "status", "collector_epoch", "observed_unix_nanos",
            "head_slot", "event_slot", "head_slot_lag", "reason", "health_sha256"}:
        raise RefusedExecution("PAC_LWS feed health schema is invalid")
    body = {key: value for key, value in row.items() if key != "health_sha256"}
    expected = _health_body(
        status=body["status"], epoch=body["collector_epoch"],
        observed_unix_nanos=body["observed_unix_nanos"], head_slot=body["head_slot"],
        event_slot=body["event_slot"], reason=body["reason"])
    if (body != expected or row["health_sha256"] != _canonical_sha(body)
            or type(clock) is not int or clock < body["observed_unix_nanos"]):
        raise RefusedExecution("PAC_LWS feed health hash/clock refuses")
    if require_fresh and (body["status"] != "FRESH"
                          or clock - body["observed_unix_nanos"] > MAX_HEALTH_AGE_NANOS
                          or body["head_slot_lag"] is None
                          or body["head_slot_lag"] > MAX_HEAD_SLOT_LAG):
        raise RefusedExecution("PAC_LWS feed is stale, degraded, or lagged")
    return row


# ==============================================================================================
# Endpoint — the funded Helius endpoint (Chainstack default is 403-dead). Never print the key.
# ==============================================================================================

def helius_endpoints() -> tuple[str, str]:
    """Return ``(http_url, ws_url)`` for the funded Helius endpoint. The key is read but never
    logged; only ``scheme://host`` is ever safe to print."""
    key = read_env("HELIUS_API_KEY")
    http = read_env("HELIUS_RPC_URL")
    if not key and http:
        key = urllib.parse.parse_qs(urllib.parse.urlsplit(http).query).get("api-key", [None])[0]
    if not key:
        raise RefusedExecution("HELIUS_API_KEY / HELIUS_RPC_URL is not set; the Chainstack "
                               "default is 403-dead and this collector will not run without a "
                               "funded endpoint")
    if not http:
        http = f"https://mainnet.helius-rpc.com/?api-key={key}"
    ws = f"wss://mainnet.helius-rpc.com/?api-key={key}"
    return http, ws


def endpoint_receipt(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}"


# ==============================================================================================
# Head-lag gate — the ONLY getSlot, on a SEPARATE daemon thread. The feed thread never calls it.
# ==============================================================================================

class HeadState:
    """The processed head, as last read by the head daemon. Read by the feed thread, never written
    by it. ``error`` non-None (including the initial ``NOT_STARTED``) means the gate fails closed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.slot: int | None = None
        self.observed_unix_nanos: int | None = None
        self.error: str | None = "NOT_STARTED"

    def update(self, slot: int, observed_unix_nanos: int) -> None:
        if type(slot) is not int or slot < 0 or type(observed_unix_nanos) is not int \
                or observed_unix_nanos <= 0:
            raise RefusedExecution("PAC_LWS head observation is invalid")
        with self._lock:
            self.slot, self.observed_unix_nanos, self.error = slot, observed_unix_nanos, None

    def fail(self, reason: str) -> None:
        with self._lock:
            self.error = str(reason)[:160]

    def snapshot(self) -> tuple[int | None, int | None, str | None]:
        with self._lock:
            return self.slot, self.observed_unix_nanos, self.error


def _get_processed_slot(http_url: str, *, opener=urllib.request.urlopen) -> int:
    request = urllib.request.Request(
        http_url,
        data=b'{"jsonrpc":"2.0","id":1,"method":"getSlot","params":[{"commitment":"processed"}]}',
        headers={"content-type": "application/json"}, method="POST")
    with opener(request, timeout=5.0) as response:
        payload = json.loads(response.read())
    if (not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0"
            or payload.get("id") != 1 or type(payload.get("result")) is not int
            or payload["result"] < 0):
        raise RefusedExecution("PAC_LWS processed-head RPC identity/result refuses")
    return payload["result"]


def _head_loop(state: HeadState, stop: threading.Event, http_url: str,
               *, opener=urllib.request.urlopen) -> None:
    while not stop.is_set():
        try:
            observed = time.time_ns()
            slot = _get_processed_slot(http_url, opener=opener)
            state.update(slot, observed)
        except Exception as exc:  # noqa: BLE001 - the gate stays visibly failed-closed
            state.fail(f"{type(exc).__name__}:{str(exc)[:120]}")
        stop.wait(HEAD_POLL_SECONDS)


def _require_head(state: HeadState, *, event_slot: int, received: int) -> int:
    """Return the processed head, or raise if it is missing, stale, or has fallen behind the event.

    Pure: reads only the shared snapshot, never the network. This is what keeps the feed thread free
    of RPC — the head is filled in elsewhere, and here we only consult it."""
    head, observed, error = state.snapshot()
    if (head is None or observed is None or error is not None or observed > received
            or received - observed > MAX_HEAD_AGE_NANOS
            or head - event_slot > MAX_HEAD_SLOT_LAG):
        raise RefusedExecution("PAC_LWS processed head is missing, stale, or lagged")
    return head


# ==============================================================================================
# The durable writer — creation registry (t0 anchor) + hash-chained trade events + reconciliation
# ==============================================================================================

def _tail_line(path: pathlib.Path, *, window: int = 1_048_576) -> dict | None:
    """The last complete JSON object in a jsonl file, or None. O(1)-ish tail read."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            if size == 0:
                return None
            handle.seek(max(0, size - window))
            payload = handle.read()
    except FileNotFoundError:
        return None
    lines = [line for line in payload.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines[-1]) >= window and size > window:
        raise RefusedExecution("PAC_LWS tail record exceeds recovery window")
    row = json.loads(lines[-1])
    if not isinstance(row, dict):
        raise RefusedExecution("PAC_LWS tail record is not an object")
    return row


class FeedWriter:
    """Owns the per-mint reserve state and every durable output. Single-threaded: only the feed
    thread calls it. The hash chain over ``feed_events.jsonl`` continues across a restart by reading
    the tail; per-mint reserve state is process-local (a mint whose create was in a prior process is
    UNANCHORED in this one, and excluded downstream)."""

    def __init__(self, *, epoch: str | None = None, events_path: pathlib.Path = EVENTS,
                 registry_path: pathlib.Path = CREATION_REGISTRY,
                 reconciliations_path: pathlib.Path = RECONCILIATIONS) -> None:
        self.epoch = epoch or uuid.uuid4().hex
        self.events_path = pathlib.Path(events_path)
        self.registry_path = pathlib.Path(registry_path)
        self.reconciliations_path = pathlib.Path(reconciliations_path)
        # per-mint state
        self.seed: dict[str, int] = {}          # mint -> t0 real_token from the CreateEvent
        self.t0_slot: dict[str, int] = {}       # mint -> create context.slot
        self.previous: dict[str, int] = {}      # mint -> most recent post real_token
        self.reconciled: dict[str, bool | None] = {}   # mint -> True/False (None = no trade yet)
        self.anchored: set[str] = set()         # mints for which a CreateEvent was observed
        self.trade_seen: set[str] = set()       # mints for which >=1 trade was recorded
        # hash chain
        self.seq = 0
        self.prev_hash = GENESIS_HASH
        self._recover_chain()
        # counters
        self.creates = 0
        self.trades = 0
        self.reconciled_true = 0
        self.reconciled_false = 0
        self.unanchored_first_trades = 0

    def _recover_chain(self) -> None:
        tail = _tail_line(self.events_path)
        if tail is None:
            return
        event_hash = tail.get("event_hash")
        body = {key: value for key, value in tail.items() if key != "event_hash"}
        if (tail.get("schema") != SCHEMA or not isinstance(event_hash, str)
                or _canonical_sha(body) != event_hash):
            raise RefusedExecution("PAC_LWS tail event is forged; refusing to extend a broken chain")
        self.prev_hash = event_hash
        self.seq = int(tail.get("seq", -1)) + 1

    # -- creation anchor ------------------------------------------------------------------------

    def register_create(self, fields: dict, *, slot: int, signature: str,
                        observed_unix_nanos: int) -> dict:
        """Durably record a CreateEvent and SEED this mint's reserve state from its t0 reserves.

        The seed is ``state_from_create_event(...)['real_token']`` — the event's own
        ``real_token_reserves`` mapped through the shared, sealed helper — NOT a literal constant, so
        the first real trade reconciles against the exact t0 baseline."""
        mint = fields.get("mint")
        if not isinstance(mint, str) or not mint:
            raise RefusedExecution("PAC_LWS CreateEvent lacks a mint")
        state, _missing = pilot.state_from_create_event(fields, slot)
        seed_real_token = state.get("real_token")
        dev_wallet = fields.get("user") or fields.get("creator")
        create_after_trade = mint in self.trade_seen
        row = {
            "schema": SCHEMA, "instrument_id": INSTRUMENT_ID, "collector_epoch": self.epoch,
            "mint": mint,
            "bonding_curve": fields.get("bonding_curve"),
            "dev_wallet": dev_wallet,
            "creator": fields.get("creator"),
            "user": fields.get("user"),
            "t0_slot": slot,
            "create_signature": signature,
            "create_observed_unix_nanos": observed_unix_nanos,
            "seed_real_token": seed_real_token,
            "seedable": seed_real_token is not None and not create_after_trade,
            "create_after_first_trade": create_after_trade,
        }
        _append(self.registry_path, row)
        self.creates += 1
        # Only anchor/seed a mint whose create arrived BEFORE its first trade and that carries a
        # real_token reserve. A create seen after trades cannot prove continuity from t0.
        if seed_real_token is not None and not create_after_trade:
            self.anchored.add(mint)
            self.seed[mint] = int(seed_real_token)
            self.t0_slot[mint] = slot
            self.previous[mint] = int(seed_real_token)
            self.reconciled.setdefault(mint, None)
        return row

    # -- trade event ----------------------------------------------------------------------------

    def append_trade(self, ev: dict, *, slot: int, signature: str,
                     observed_unix_nanos: int) -> dict:
        """Append one hash-chained trade event and, at a mint's first trade, its reconciliation
        verdict. The event carries everything ``pac_lws_screen.WindowTrade`` consumes."""
        mint, trader, side = ev.get("mint"), ev.get("user"), ev.get("side")
        token_amount, post_real_token, sol_amount = (
            ev.get("token_amount"), ev.get("real_tok"), ev.get("sol_amount"))
        if not (isinstance(mint, str) and mint and isinstance(trader, str) and trader
                and side in {"buy", "sell"}):
            raise RefusedExecution("PAC_LWS decoded trade lacks mint/trader/side")
        if any(type(v) is not int or v < 0 for v in (token_amount, post_real_token, sol_amount)):
            raise RefusedExecution("PAC_LWS decoded trade lacks exact non-negative integer amounts")
        is_buy = side == "buy"
        signed = token_amount if is_buy else -token_amount
        pre_real_token = self.previous.get(mint)
        reserve_delta = None if pre_real_token is None else pre_real_token - post_real_token

        first_trade = mint not in self.trade_seen
        reconciled_flag: bool | None = self.reconciled.get(mint)
        if first_trade:
            if mint in self.anchored:
                seed_val = self.seed[mint]
                ok = (pre_real_token == seed_val
                      and reserve_delta is not None
                      and abs(reserve_delta - signed) <= RECON_ROUNDING_ATOMS)
                reconciled_flag = bool(ok)
                self.reconciled[mint] = reconciled_flag
                self.reconciled_true += int(ok)
                self.reconciled_false += int(not ok)
                self._append_reconciliation(
                    mint=mint, seed_present=True, reconciled=reconciled_flag,
                    seed_real_token=seed_val, first_trade_slot=slot,
                    pre_real_token=pre_real_token, post_real_token=post_real_token,
                    token_amount=token_amount, is_buy=is_buy, signed=signed,
                    reserve_delta_tokens=reserve_delta, observed_unix_nanos=observed_unix_nanos)
            else:
                # UNANCHORED: no create was seen for this mint in this process, so continuity from
                # t0 cannot be proven. reconciled stays None; excluded downstream.
                reconciled_flag = None
                self.unanchored_first_trades += 1
                self._append_reconciliation(
                    mint=mint, seed_present=False, reconciled=None,
                    seed_real_token=None, first_trade_slot=slot,
                    pre_real_token=pre_real_token, post_real_token=post_real_token,
                    token_amount=token_amount, is_buy=is_buy, signed=signed,
                    reserve_delta_tokens=reserve_delta, observed_unix_nanos=observed_unix_nanos)
            self.trade_seen.add(mint)

        body = {
            "schema": SCHEMA, "instrument_id": INSTRUMENT_ID, "collector_epoch": self.epoch,
            "seq": self.seq,
            "mint": mint,
            "slot": slot,
            "trader": trader,
            "is_buy": is_buy,
            "token_amount": token_amount,
            "sol_amount": sol_amount,
            "pre_real_token": pre_real_token,
            "post_real_token": post_real_token,
            # exactly what pac_lws_screen.WindowTrade wants: pre - post (None if pre is unknown).
            "reserve_delta_tokens": reserve_delta,
            "reconciled": reconciled_flag,
            "anchored": mint in self.anchored,
            "t0_slot": self.t0_slot.get(mint),
            "signature": signature,
            "received_unix_nanos": observed_unix_nanos,
            "prev_hash": self.prev_hash,
        }
        event_hash = _canonical_sha(body)
        row = {**body, "event_hash": event_hash}
        _append(self.events_path, row)
        self.prev_hash = event_hash
        self.seq += 1
        self.previous[mint] = post_real_token
        self.trades += 1
        return row

    def _append_reconciliation(self, **kw) -> None:
        row = {"schema": SCHEMA, "instrument_id": INSTRUMENT_ID, "collector_epoch": self.epoch,
               "signed_token_amount": kw.pop("signed"), **kw}
        _append(self.reconciliations_path, row)


# ==============================================================================================
# The feed thread — RAW FIRST, then the head gate, then decode. Never awaits an RPC.
# ==============================================================================================

def handle_frame(message: str, received_unix_nanos: int, raw, writer: FeedWriter,
                 head_state: HeadState, decoder: dict, counts: dict) -> None:
    """One log notification. Order is mandatory and load-bearing:

    1. RAW FIRST — the received time is already stamped (before this call, before ``json.loads``),
       and the whole frame is written to the raw log before anything is decoded, so a crash between
       decode steps still leaves the evidence on disk.
    2. HEAD GATE — fail-closed: if the processed head is missing/stale/lagged we do not admit the
       frame's decoded events (the raw is kept for replay).
    3. CREATE(s) FIRST, then TRADE(s) — so a dev buy in the same transaction as the create seeds
       against, and reconciles to, the t0 reserve.

    This function contains NO RPC call, by construction and by the source-checked guard
    ``assert_feed_thread_does_not_call_rpc``."""
    payload = json.loads(message)
    params = (payload.get("params") or {}).get("result") or {}
    context = params.get("context") or {}
    value = params.get("value") or {}
    slot = context.get("slot")
    signature = value.get("signature")
    # 1. RAW FIRST — always, whatever follows.
    raw.append({"received_unix_nanos": received_unix_nanos, "collector_epoch": writer.epoch,
                "slot": slot, "signature": signature, "raw_notification_json": payload,
                "raw_sha256": hashlib.sha256(message.encode()).hexdigest()})
    counts["frames"] += 1
    if "params" not in payload:            # a subscription ack or other non-notification
        return
    if value.get("err") is not None or type(slot) is not int or not isinstance(signature, str):
        return
    # 2. HEAD GATE — pure consult of the daemon's snapshot; no network here.
    try:
        head = _require_head(head_state, event_slot=slot, received=received_unix_nanos)
    except RefusedExecution as exc:
        counts["head_gated_frames"] += 1
        write_health(status="DEGRADED", epoch=writer.epoch, observed_unix_nanos=received_unix_nanos,
                     head_slot=head_state.snapshot()[0], event_slot=slot,
                     reason=f"{type(exc).__name__}:{str(exc)[:120]}")
        return
    logs = value.get("logs")
    # 3a. CREATES FIRST — seed the t0 anchor before any same-frame trade is reconciled.
    payloads, _skipped = pilot.program_data_payloads(logs)
    for blob in payloads:
        status, fields, _error = pilot.decode_create(
            blob, decoder["b7d"], decoder["discriminator"], decoder["create_type"],
            decoder["types"])
        if status == pilot.DECODE_DECODED:
            writer.register_create(fields, slot=slot, signature=signature,
                                   observed_unix_nanos=received_unix_nanos)
    # 3b. TRADES — decoded off the SAME logs; token_amount/real_tok are atoms.
    for ev in decode_pump_trades_from_logs(logs or [], SOL_USD_DEFAULT):
        writer.append_trade(ev, slot=slot, signature=signature,
                            observed_unix_nanos=received_unix_nanos)
    write_health(status="FRESH", epoch=writer.epoch, observed_unix_nanos=received_unix_nanos,
                 head_slot=head, event_slot=slot, reason=None)


def _subscribe(ws) -> None:
    ws.send_json({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                  "params": [{"mentions": [PUMP_PROGRAM]}, {"commitment": "processed"}]})
    ack = json.loads(ws.recv())
    if (not isinstance(ack, dict) or ack.get("jsonrpc") != "2.0" or ack.get("id") != 1
            or type(ack.get("result")) is not int):
        raise RefusedExecution("PAC_LWS logsSubscribe acknowledgement refuses")


# ==============================================================================================
# Run
# ==============================================================================================

def run_collector(*, seconds: float | None = None, ws_url: str | None = None,
                  http_url: str | None = None, reconnect_pause: float = 2.0) -> dict:
    """Subscribe at processed, write raw, seed creates, chain trades, reconcile. Read-only."""
    assert_no_execution_surface()
    b15i.assert_feed_thread_does_not_call_rpc(path=__file__)   # the feed handler awaits no RPC
    DATA.mkdir(parents=True, exist_ok=True)
    if http_url is None or ws_url is None:
        derived_http, derived_ws = helius_endpoints()
        http_url = http_url or derived_http
        ws_url = ws_url or derived_ws

    b7d, discriminator, create_type, types = pilot.load_pinned_create_type()
    decoder = {"b7d": b7d, "discriminator": discriminator,
               "create_type": create_type, "types": types}
    raw = b15i.RawLog(RAW)                    # reused: append-only, flushed per frame
    writer = FeedWriter()
    counts = {"frames": 0, "head_gated_frames": 0, "faults": 0, "sessions": 0}

    head_state = HeadState()
    stop = threading.Event()
    head_thread = threading.Thread(target=_head_loop, args=(head_state, stop, http_url),
                                   daemon=True)
    head_thread.start()
    # Wait for the daemon to prime the head so the opening burst is not needlessly gated. The only
    # getSlot is still on the daemon thread; the main thread only reads the snapshot.
    primed_deadline = time.monotonic() + 6.0
    while time.monotonic() < primed_deadline and head_state.snapshot()[0] is None:
        time.sleep(0.1)

    deadline = None if seconds is None else time.monotonic() + seconds
    try:
        while deadline is None or time.monotonic() < deadline:
            writer.epoch = uuid.uuid4().hex          # a reconnect starts a new collector epoch
            counts["sessions"] += 1
            session_started = time.time_ns()
            _append(SESSIONS, {"schema": SCHEMA, "instrument_id": INSTRUMENT_ID,
                               "collector_epoch": writer.epoch,
                               "session_index": counts["sessions"] - 1,
                               "started_unix_nanos": session_started,
                               "endpoint": endpoint_receipt(ws_url)})
            ws = None
            try:
                ws = ws_client.WebSocket(ws_url, timeout=30.0).connect()
                _subscribe(ws)
                while deadline is None or time.monotonic() < deadline:
                    message = ws.recv()
                    received = time.time_ns()      # stamped BEFORE json.loads, per the contract
                    if message is None:
                        break
                    handle_frame(message, received, raw, writer, head_state, decoder, counts)
            except Exception as exc:  # noqa: BLE001 - collector retries visibly, never trades
                counts["faults"] += 1
                now = time.time_ns()
                write_health(status="DEGRADED", epoch=writer.epoch, observed_unix_nanos=now,
                             head_slot=head_state.snapshot()[0], event_slot=None,
                             reason=f"{type(exc).__name__}:{str(exc)[:160]}")
                print(f"{dt.datetime.now(dt.timezone.utc).isoformat()} PAC_LWS_FEED_REFUSED "
                      f"{type(exc).__name__}:{str(exc)[:180]}", flush=True)
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:  # noqa: BLE001
                        pass
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(reconnect_pause)
    finally:
        stop.set()
        raw.close()
    head, _, _ = head_state.snapshot()
    return {"counts": counts, "creates": writer.creates, "trades": writer.trades,
            "reconciled_true": writer.reconciled_true, "reconciled_false": writer.reconciled_false,
            "unanchored_first_trades": writer.unanchored_first_trades,
            "final_head_slot": head, "epoch": writer.epoch}


# ==============================================================================================
# Summary — coverage census over the captured files (no network)
# ==============================================================================================

def _iter_jsonl(path: pathlib.Path):
    if not path.exists():
        return
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def summarize(*, registry_path: pathlib.Path = CREATION_REGISTRY,
              events_path: pathlib.Path = EVENTS, health_path: pathlib.Path = HEALTH,
              k_slots: int = 60, midlife_baseline_pct: float = 4.0) -> dict:
    """Coverage census: creates registered, trades decoded, and the fraction of created mints with a
    reconciled first trade and a complete [t0, t0+60] window. Compared to the mid-life baseline this
    collector exists to beat."""
    creates: dict[str, dict] = {}
    for row in _iter_jsonl(registry_path):
        mint = row.get("mint")
        if isinstance(mint, str) and mint not in creates:
            creates[mint] = row

    trades_total = 0
    trades_with_amount = 0
    per_mint: dict[str, dict] = {}
    try:
        final_head = json.loads(health_path.read_text()).get("head_slot")
    except (OSError, json.JSONDecodeError):
        final_head = None

    for ev in _iter_jsonl(events_path):
        mint = ev.get("mint")
        if not isinstance(mint, str):
            continue
        trades_total += 1
        if type(ev.get("token_amount")) is int:
            trades_with_amount += 1
        slot = ev.get("slot")
        m = per_mint.setdefault(mint, {"trades": 0, "reconciled_first": None,
                                       "min_slot": None, "max_slot": None,
                                       "in_window": 0, "t0_slot": ev.get("t0_slot")})
        m["trades"] += 1
        if m["reconciled_first"] is None and ev.get("reconciled") is not None:
            m["reconciled_first"] = bool(ev.get("reconciled"))
        if isinstance(slot, int):
            m["min_slot"] = slot if m["min_slot"] is None else min(m["min_slot"], slot)
            m["max_slot"] = slot if m["max_slot"] is None else max(m["max_slot"], slot)

    reconciled_mints = []
    complete_window_mints = []
    for mint, reg in creates.items():
        m = per_mint.get(mint)
        if not m:
            continue
        t0 = reg.get("t0_slot")
        if m.get("reconciled_first") is True:
            reconciled_mints.append(mint)
            # window is complete iff the collector was live through t0+60: an event at/after t0+60
            # OR the processed head advanced past t0+60 by shutdown.
            reached = ((isinstance(m.get("max_slot"), int) and isinstance(t0, int)
                        and m["max_slot"] >= t0 + k_slots)
                       or (isinstance(final_head, int) and isinstance(t0, int)
                           and final_head >= t0 + k_slots))
            if reached:
                complete_window_mints.append(mint)

    n_creates = len(creates)
    n_reconciled = len(reconciled_mints)
    n_complete = len(complete_window_mints)
    return {
        "creates_registered": n_creates,
        "trades_decoded": trades_total,
        "trades_with_token_amount": trades_with_amount,
        "mints_with_trades": len(per_mint),
        "mints_create_and_reconciled_trade": n_reconciled,
        "mints_create_reconciled_and_complete_window": n_complete,
        "coverage_reconciled_pct": round(100.0 * n_reconciled / n_creates, 1) if n_creates else 0.0,
        "coverage_complete_window_pct": round(100.0 * n_complete / n_creates, 1) if n_creates else 0.0,
        "midlife_baseline_pct": midlife_baseline_pct,
        "final_head_slot": final_head,
    }


def example_mint(*, registry_path: pathlib.Path = CREATION_REGISTRY,
                 events_path: pathlib.Path = EVENTS,
                 reconciliations_path: pathlib.Path = RECONCILIATIONS,
                 k_slots: int = 60) -> dict | None:
    """One worked example: a mint's t0_slot, its first-trade reconciliation, and in-window count."""
    recon = {r.get("mint"): r for r in _iter_jsonl(reconciliations_path)
             if r.get("seed_present") and r.get("reconciled") is True}
    if not recon:
        return None
    events_by_mint: dict[str, list] = {}
    for ev in _iter_jsonl(events_path):
        events_by_mint.setdefault(ev.get("mint"), []).append(ev)
    creates = {r.get("mint"): r for r in _iter_jsonl(registry_path)}
    # prefer a mint that actually reached t0+60
    chosen = None
    for mint, r in recon.items():
        reg = creates.get(mint)
        if not reg:
            continue
        t0 = reg.get("t0_slot")
        evs = events_by_mint.get(mint, [])
        max_slot = max((e.get("slot") for e in evs if isinstance(e.get("slot"), int)), default=None)
        if isinstance(t0, int) and isinstance(max_slot, int) and max_slot >= t0 + k_slots:
            chosen = (mint, reg, r, evs)
            break
    if chosen is None:
        mint, r = next(iter(recon.items()))
        chosen = (mint, creates.get(mint), r, events_by_mint.get(mint, []))
    mint, reg, r, evs = chosen
    t0 = reg.get("t0_slot") if reg else None
    in_window = sum(1 for e in evs if isinstance(e.get("slot"), int) and isinstance(t0, int)
                    and t0 <= e["slot"] <= t0 + k_slots)
    return {
        "mint": mint,
        "t0_slot": t0,
        "dev_wallet": (reg or {}).get("dev_wallet"),
        "seed_real_token": (reg or {}).get("seed_real_token"),
        "first_trade_reconciliation": {
            "reconciled": r.get("reconciled"),
            "pre_real_token": r.get("pre_real_token"),
            "post_real_token": r.get("post_real_token"),
            "reserve_delta_tokens": r.get("reserve_delta_tokens"),
            "signed_token_amount": r.get("signed_token_amount"),
            "first_trade_slot": r.get("first_trade_slot"),
            "is_buy": r.get("is_buy"),
        },
        "in_window_trades_captured": in_window,
        "total_trades_captured": len(evs),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC LWS creation-anchored collector (read-only)")
    parser.add_argument("--seconds", type=float, default=None,
                        help="bounded run length; omit for unbounded")
    parser.add_argument("--summary", action="store_true",
                        help="print the coverage census over the captured files and exit")
    args = parser.parse_args(argv)
    if args.summary:
        print(json.dumps({"summary": summarize(), "example": example_mint()},
                         indent=2, sort_keys=True))
        return 0
    result = run_collector(seconds=args.seconds)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RefusedExecution as error:
        print(f"RefusedExecution: {error}", file=sys.stderr)
        sys.exit(2)
