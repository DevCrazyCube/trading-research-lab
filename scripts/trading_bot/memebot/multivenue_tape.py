#!/usr/bin/env python3
"""Multi-venue LAUNCH + GRADUATION collector — a read-only listener with its OWN hash-chained tape.

WHAT THIS IS FOR
----------------
`research/b11a/` established that the binding constraint on this whole line of work is LABELS, not
features: 82 graduations in the pump.fun window, and only 3 inside the floor-priced cohort of 2,975
where a trade could actually pay. No classifier can be fit, cross-validated, or even honestly
feature-ranked on 3 events. Recon A then showed the label wall is not a law of nature — the SAME
constant-product curve runs on LetsBonk/LaunchLab (X = 14.6938 vs pump.fun's 14.6958) at 134x the
label count, with a different toll and half the graduation rate: a natural control, not merely more data.

This process is the forward half of that harvest. It subscribes to every tapeable launchpad program at
once and appends exactly two kinds of row — CREATE and GRADUATION — to its own append-only,
hash-chained JSONL. It does not tape trades: trades are the b11a question that is already closed, and
a trade tape is 325 MB/day. Labels are what is scarce.

WHY A SEPARATE TAPE AND A SEPARATE FILE
---------------------------------------
`ws_data.py` / `helius_tape.py` / `helius_pump_decode.py` are inside the executable closure of the live
arena arms. Editing ANY of them forces a re-activation and a ledger re-epoch of every live arm, which
would discard collection in progress. `ws_data._trade_head()` / `_append_trade()` are also hardwired to
their module-global tape path, so a second tape cannot reuse them without an edit. So this file
RE-IMPLEMENTS the identical chain discipline against its own path, and imports nothing from the arena.
Nothing here touches an existing file, an existing tape, or an existing activation.

CHAIN DISCIPLINE (byte-identical algorithm to ws_data.py)
--------------------------------------------------------
    record_body = {**body, "sequence": prev_seq + 1, "previous_record_sha256": prev_sha}
    record_sha256 = sha256(json.dumps(record_body, sort_keys, separators=(",",":"), ensure_ascii))
Appends are O_APPEND|O_NOFOLLOW + fsync, refuse above a 1 GiB segment bound, and refuse below a 10 GiB
filesystem reserve. `head()` re-verifies the WHOLE chain before any append, so a truncated or edited
tape refuses loudly instead of silently forking. `read_after(offset)` is the incremental byte-offset
read a consumer should use: it returns only COMPLETE newline-terminated lines and leaves a partial
trailing line for the next pass.

READ-ONLY: opens exactly one Helius JSON-RPC websocket, gated by a module-local host allowlist (there is
no shared chokepoint for this — `net.assert_data_ws` allowlists PumpPortal only, and helius_tape opens
its socket directly). No wallet, no orders, nothing written on-chain, and neither the endpoint nor the
API key is ever written to the tape, the health record, or a log line.

Per the project's standing rule a long-lived stream runs as a DETACHED background subprocess, never
inside an agent turn. `--seconds N` gives a bounded, honest connectivity + transport measurement.

    python -m scripts.trading_bot.memebot.multivenue_tape --selftest       # hermetic, no network
    python -m scripts.trading_bot.memebot.multivenue_tape --seconds 90     # bounded live test
    python -m scripts.trading_bot.memebot.multivenue_tape --report         # verify + summarise the tape
    nohup python -m scripts.trading_bot.memebot.multivenue_tape &          # detached collection
"""
from __future__ import annotations

import collections
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import shutil
import tempfile
import time
import urllib.parse

from . import venues as V

try:
    import websocket  # websocket-client
except ImportError:  # pragma: no cover
    websocket = None

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_ENV_PATH = _ROOT / ".env"
CACHE = _ROOT / "research" / "data" / "memebot_cache"

TAPE_PATH = CACHE / "multivenue_launch_tape_v1.jsonl"
LOCK_PATH = CACHE / "multivenue_launch_tape_v1.lock"
HEALTH_PATH = CACHE / "multivenue_stream_health.json"

TAPE_SCHEMA = 1
HEALTH_SCHEMA = 1
SOURCE = "HELIUS_LOGS_READ_ONLY_MULTIVENUE"

_GENESIS = "0" * 64
_MAX_TAPE_BYTES = 1024 * 1024 * 1024          # 1 GiB segment bound, as ws_data
_RESERVE_BYTES = 10 * 1024 * 1024 * 1024      # refuse below a 10 GiB filesystem reserve
_HEALTH_FLUSH_S = 2.0
_RECV_TIMEOUT_S = 30.0
_DEDUP_MAX = 200_000                          # session-local replay guard

# The ONLY websocket hosts this listener may open. There is no shared allowlist covering this path
# (net.assert_data_ws is PumpPortal-only and helius_tape bypasses it), so the allowlist lives here,
# module-local, and is compared as an exact parsed hostname — never a substring.
# `api.mainnet-beta.solana.com` is the FREE public Solana RPC. It is added deliberately: our Helius
# credits are exhausted ("max usage reached"), and the whole point of this collector is to run at $0.
# It is a read-only public JSON-RPC endpoint — no key, no wallet, no write path — so admitting it does
# not widen the trust boundary this allowlist exists to protect (which is: never open a socket to an
# unvetted host, and never a submit endpoint).
ALLOWED_WS_HOSTS = frozenset({"mainnet.helius-rpc.com", "atlas-mainnet.helius-rpc.com",
                              "api.mainnet-beta.solana.com"})


class Refused(Exception):
    """A refusal — this module would rather stop than write something it cannot justify."""


# ---------------------------------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------------------------------
def _env(key: str) -> str | None:
    """Process env first, then the repo .env — a detached subprocess is not guaranteed the shell's vars."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    try:
        for line in _ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None


def assert_allowed_ws(url: str) -> str:
    """wss only, and only an allowlisted Helius read host. Refuses loudly on anything else."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "wss":
        raise Refused(f"the venue listener is wss-only; refusing scheme {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_WS_HOSTS:
        raise Refused(f"{host!r} is not on the venue-listener host allowlist "
                      f"{sorted(ALLOWED_WS_HOSTS)}")
    return url


def _ws_url() -> str:
    # explicit override first: lets the collector run on the free public RPC while Helius is 429
    rpc = _env("MULTIVENUE_RPC_URL") or _env("HELIUS_RPC_URL")
    if not rpc:
        key = _env("HELIUS_API_KEY")
        if key:
            rpc = f"https://mainnet.helius-rpc.com/?api-key={key}"
    if not rpc:
        raise Refused("HELIUS_RPC_URL / HELIUS_API_KEY absent; cannot open the multi-venue tape")
    if rpc.startswith("https://"):
        rpc = "wss://" + rpc[len("https://"):]
    elif rpc.startswith("http://"):
        rpc = "ws://" + rpc[len("http://"):]
    return assert_allowed_ws(rpc)


def _redact(text: str) -> str:
    """Never let an endpoint or api key reach a log line, the tape, or the health record."""
    out = str(text)
    for key in ("HELIUS_RPC_URL", "HELIUS_API_KEY"):
        secret = _env(key)
        if secret:
            out = out.replace(secret, "<redacted>")
            if "api-key=" in secret:
                out = out.replace(secret.split("api-key=", 1)[1], "<redacted>")
    return out


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


# ---------------------------------------------------------------------------------------------------
# the tape
# ---------------------------------------------------------------------------------------------------
class MultiVenueTape:
    """Append-only, hash-chained JSONL. Same chain algorithm as ws_data.py, its own path."""

    def __init__(self, path: pathlib.Path = TAPE_PATH, *,
                 max_bytes: int = _MAX_TAPE_BYTES, reserve_bytes: int = _RESERVE_BYTES):
        self.path = pathlib.Path(path)
        self.max_bytes = max_bytes
        # The filesystem reserve is a REFUSAL, not a warning: a tape that fills the disk corrupts the
        # chain's last row and takes every other collector on this box down with it. Parameterised only
        # so the hermetic self-test can prove both branches on a small tmpfs.
        self.reserve_bytes = reserve_bytes

    # --- verification -------------------------------------------------------------------------------
    def head(self) -> tuple[int, str]:
        """(sequence, previous_record_sha256) after verifying EVERY row. Refuses on any break."""
        if not self.path.exists():
            return 0, _GENESIS
        previous, sequence = _GENESIS, 0
        with self.path.open() as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise Refused(f"multi-venue tape is not JSON at line {line_number}: {exc}") from None
                body = dict(row)
                observed = body.pop("record_sha256", None)
                if (body.get("sequence") != sequence + 1
                        or body.get("previous_record_sha256") != previous
                        or observed != hashlib.sha256(_canonical(body)).hexdigest()):
                    raise Refused(f"multi-venue tape chain refuses at line {line_number}")
                sequence, previous = sequence + 1, observed
        return sequence, previous

    # --- append -------------------------------------------------------------------------------------
    def append(self, body: dict, head: tuple[int, str]) -> tuple[int, str]:
        if self.path.exists() and self.path.stat().st_size >= self.max_bytes:
            raise Refused(f"multi-venue tape reached its frozen {self.max_bytes} byte segment bound")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.path.parent).free < self.reserve_bytes:
            raise Refused(f"multi-venue tape refuses below the {self.reserve_bytes} byte "
                          "filesystem reserve")
        sequence, previous = head
        record_body = {**body, "sequence": sequence + 1, "previous_record_sha256": previous}
        record = {**record_body, "record_sha256": hashlib.sha256(_canonical(record_body)).hexdigest()}
        payload = _canonical(record) + b"\n"
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if os.write(descriptor, payload) != len(payload):
                raise OSError("short multi-venue tape append")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return sequence + 1, record["record_sha256"]

    # --- incremental read ---------------------------------------------------------------------------
    def read_after(self, offset: int = 0) -> tuple[list[dict], int]:
        """Rows after a byte offset, plus the new offset. Only COMPLETE lines are returned; a partial
        trailing line (a write in flight) is left for the next pass — the live incremental pattern."""
        if type(offset) is not int or offset < 0:
            raise Refused("tape offset is invalid")
        if not self.path.exists():
            return [], 0
        rows: list[dict] = []
        with self.path.open("rb") as handle:
            handle.seek(offset)
            buf = handle.read()
        end = buf.rfind(b"\n")
        if end == -1:
            return [], offset                             # nothing but a partial line yet
        complete = buf[:end + 1]
        for chunk in complete.split(b"\n"):
            if chunk.strip():
                rows.append(json.loads(chunk))
        return rows, offset + len(complete)

    @staticmethod
    def verify_row(row: dict, cursor: int, head_sha: str) -> bool:
        """Continuity check a consumer runs per row against its persisted (cursor, head) pair."""
        body = dict(row)
        observed = body.pop("record_sha256", None)
        return (body.get("sequence") == cursor + 1
                and body.get("previous_record_sha256") == head_sha
                and observed == hashlib.sha256(_canonical(body)).hexdigest())


# ---------------------------------------------------------------------------------------------------
# stream health (own writer + own pure assessor; nothing imported from the arena closure)
# ---------------------------------------------------------------------------------------------------
def write_stream_health(record: dict, path: pathlib.Path = HEALTH_PATH) -> None:
    """Atomically persist NON-SECRET stream health. The endpoint and key are never stored."""
    body = {"schema": HEALTH_SCHEMA, **record, "updated_unix_nanos": time.time_ns()}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(body, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def assess_stream_health(record: dict | None, *, now_ns: int | None = None,
                         max_stale_s: float = 60.0) -> dict:
    """Pure, FAIL-CLOSED health verdict. Process-up is not feed-up: a connected socket that has stopped
    delivering must read STALE, never CONNECTED."""
    now_ns = time.time_ns() if now_ns is None else now_ns
    if not isinstance(record, dict) or record.get("schema") != HEALTH_SCHEMA:
        return {"ok": False, "status": "MISSING", "reason": "venue stream health is missing"}
    status = record.get("status")
    if status != "CONNECTED":
        return {"ok": False, "status": status or "UNKNOWN",
                "reason": record.get("reason") or "venue stream is not connected"}
    last = record.get("last_message_unix_nanos")
    if type(last) is not int or last <= 0 or last > now_ns:
        return {"ok": False, "status": "INVALID_CLOCK", "reason": "venue stream clock is invalid"}
    age_s = (now_ns - last) / 1e9
    if age_s > max_stale_s:
        return {"ok": False, "status": "STALE",
                "reason": f"last venue stream message is {age_s:.1f}s old", "age_s": age_s}
    return {"ok": True, "status": "CONNECTED", "reason": "venue stream is fresh", "age_s": age_s,
            "last_event_unix_nanos": record.get("last_event_unix_nanos")}


def stream_health(*, path: pathlib.Path = HEALTH_PATH, max_stale_s: float = 60.0) -> dict:
    try:
        record = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        record = None
    return assess_stream_health(record, max_stale_s=max_stale_s)


# ---------------------------------------------------------------------------------------------------
# the listener
# ---------------------------------------------------------------------------------------------------
def _dedup_key(row: dict) -> tuple:
    return (row.get("signature"), row.get("venue"), row.get("kind"),
            row.get("pool_id") or row.get("mint"))


def run_listener(seconds: float | None = None, *, programs: list | None = None,
                 tape: MultiVenueTape | None = None, verbose: bool = True) -> dict:
    """Subscribe to every tapeable launchpad program and tape CREATE + GRADUATION events.

    `seconds=None` runs until interrupted (the detached-subprocess mode). A finite `seconds` is a
    bounded test that returns a summary — including per-program `program_data_lines` vs `create_seen`,
    which is the HONEST measurement of whether a venue publishes its events on logs at all. Two of the
    four programs (Meteora DBC, Boop) have an UNVERIFIED log transport: if they emit only via anchor
    `emit_cpi!` inner instructions, logsSubscribe cannot see them, and that shows up here as
    program_data_lines > 0 with create_seen == 0 rather than as a silent gap.
    """
    if websocket is None:
        raise Refused("websocket-client is not installed; cannot open the multi-venue tape")
    V.verify_pinned_idls()
    V.reset_event_stats()
    keys = list(programs) if programs else list(V.PROGRAMS)
    unknown = [k for k in keys if k not in V.PROGRAMS]
    if unknown:
        raise Refused(f"unknown venue program(s) {unknown}; known: {sorted(V.PROGRAMS)}")
    url = _ws_url()
    tape = tape or MultiVenueTape()
    head = tape.head()                       # verifies the WHOLE existing chain before we append a byte

    t0 = time.time()
    counters = {"messages": 0, "notifications": 0, "failed_tx_skipped": 0, "rows_taped": 0,
                "creates": 0, "graduations": 0, "duplicates_dropped": 0, "reconnects": 0,
                "append_refusals": 0}
    per_venue: dict[str, dict] = {}
    seen: set = set()
    seen_order: collections.deque = collections.deque()
    samples: list[dict] = []

    health = {"status": "CONNECTING", "reason": "multi-venue tape starting",
              "programs": keys, "reconnects": 0, "last_message_unix_nanos": None,
              "last_event_unix_nanos": None, "rows_taped": 0}
    write_stream_health(health)
    last_flush = 0.0

    def _summary(connected: bool) -> dict:
        return {"connected": connected, "seconds": round(time.time() - t0, 1),
                "programs": {k: {"program_id": V.PROGRAMS[k].program_id,
                                 "transport_verified": V.PROGRAMS[k].transport_verified,
                                 "stats": V.EVENT_STATS.get(k, {})} for k in keys},
                "counters": dict(counters), "per_venue": per_venue,
                "tape_path": str(tape.path), "tape_sequence": head[0],
                "health_path": str(HEALTH_PATH), "samples": samples[:5]}

    def _note(row: dict) -> None:
        slot = per_venue.setdefault(row["venue"], {"create": 0, "graduation": 0})
        slot[row["kind"]] = slot.get(row["kind"], 0) + 1

    while True:
        try:
            ws = websocket.create_connection(url, timeout=30)
            sub_to_program: dict[int, str] = {}
            pending: dict[int, str] = {}
            for i, key in enumerate(keys, start=1):
                pending[i] = key
                ws.send(json.dumps({"jsonrpc": "2.0", "id": i, "method": "logsSubscribe",
                                    "params": [{"mentions": [V.PROGRAMS[key].program_id]},
                                               {"commitment": "confirmed"}]}))
            deadline = time.time() + 30
            while pending and time.time() < deadline:
                ws.settimeout(10)
                try:
                    ack = json.loads(ws.recv())
                except (websocket.WebSocketTimeoutException, json.JSONDecodeError):
                    continue
                if "id" in ack and ack["id"] in pending:
                    if "result" not in ack:
                        raise Refused(f"logsSubscribe refused for {pending[ack['id']]}: "
                                      f"{_redact(json.dumps(ack.get('error')))[:200]}")
                    sub_to_program[ack["result"]] = pending.pop(ack["id"])
            if pending:
                raise Refused(f"no logsSubscribe ack for {sorted(pending.values())}")
            health.update(status="CONNECTED", reason="multi-venue logsSubscribe connected",
                          reconnects=counters["reconnects"], subscriptions=len(sub_to_program))
            write_stream_health(health)
            if verbose:
                print(f"[{_now_iso()}] subscribed: "
                      + ", ".join(f"{k}={V.PROGRAMS[k].program_id[:6]}..." for k in keys), flush=True)

            while True:
                if seconds is not None and time.time() - t0 >= seconds:
                    ws.close()
                    write_stream_health({**health, "status": "STOPPED",
                                         "reason": "bounded run finished"})
                    return _summary(True)
                ws.settimeout(_RECV_TIMEOUT_S)
                try:
                    msg = ws.recv()
                except websocket.WebSocketTimeoutException:
                    # genuinely quiet: do NOT bump last_message — let a real stall age into STALE.
                    continue
                counters["messages"] += 1
                recv_ns = time.time_ns()
                health["last_message_unix_nanos"] = recv_ns
                try:
                    d = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                if d.get("method") != "logsNotification":
                    continue
                params = d.get("params", {})
                key = sub_to_program.get(params.get("subscription"))
                if key is None:
                    continue
                counters["notifications"] += 1
                result = params.get("result", {})
                value = result.get("value", {})
                if value.get("err") is not None:
                    counters["failed_tx_skipped"] += 1
                    continue          # a failed transaction never created or graduated anything
                signature = value.get("signature")
                slot = result.get("context", {}).get("slot")
                try:
                    rows = V.decode_logs(V.PROGRAMS[key].program_id, value.get("logs") or [],
                                         signature=signature, slot=slot)
                except V.VenueRefused:
                    continue
                for row in rows:
                    dk = _dedup_key(row)
                    if dk in seen:
                        counters["duplicates_dropped"] += 1
                        continue
                    seen.add(dk)
                    seen_order.append(dk)
                    if len(seen_order) > _DEDUP_MAX:
                        seen.discard(seen_order.popleft())
                    body = {**row, "tape_schema": TAPE_SCHEMA, "source": SOURCE,
                            "received_unix_nanos": recv_ns,
                            "raw_message_sha256": hashlib.sha256(msg.encode()).hexdigest()}
                    try:
                        head = tape.append(body, head)
                    except Refused as exc:
                        counters["append_refusals"] += 1
                        health.update(status="DEGRADED", reason=_redact(str(exc))[:200])
                        write_stream_health(health)
                        raise
                    counters["rows_taped"] += 1
                    counters["creates" if row["kind"] == "create" else "graduations"] += 1
                    health["last_event_unix_nanos"] = recv_ns
                    health["rows_taped"] = counters["rows_taped"]
                    _note(row)
                    if len(samples) < 5:
                        samples.append({k: row.get(k) for k in
                                        ("venue", "kind", "mint", "pool_id", "symbol", "slot")})
                now = time.monotonic()
                if now - last_flush >= _HEALTH_FLUSH_S:
                    write_stream_health(health)
                    last_flush = now
        except Refused:
            write_stream_health({**health, "status": "REFUSED",
                                 "reason": health.get("reason", "refused")})
            raise
        except KeyboardInterrupt:
            write_stream_health({**health, "status": "STOPPED", "reason": "interrupted"})
            return _summary(True)
        except Exception as exc:  # noqa: BLE001 — transient socket drop; reconnect politely
            counters["reconnects"] += 1
            backoff = min(15.0, 1.0 + counters["reconnects"])
            health.update(status="DISCONNECTED",
                          reason=_redact(f"stream dropped: {exc!r}")[:200],
                          reconnects=counters["reconnects"],
                          next_retry_unix_nanos=time.time_ns() + int(backoff * 1e9))
            write_stream_health(health)
            last_flush = 0.0
            if verbose:
                print(f"[{_now_iso()}] multi-venue tape dropped "
                      f"({_redact(repr(exc))[:160]}); reconnecting in {backoff:.0f}s", flush=True)
            if seconds is not None and time.time() - t0 >= seconds:
                return _summary(counters["messages"] > 0)
            time.sleep(backoff)


# ---------------------------------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------------------------------
def report(tape: MultiVenueTape | None = None) -> dict:
    """Verify the whole chain and summarise what has been collected. Refuses on a broken chain."""
    tape = tape or MultiVenueTape()
    sequence, head_sha = tape.head()
    per: dict[str, dict] = {}
    first_ns = last_ns = None
    graduated_pools: dict[str, set] = {}
    created_pools: dict[str, set] = {}
    if tape.path.exists():
        with tape.path.open() as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                venue, kind = row.get("venue", "?"), row.get("kind", "?")
                slot = per.setdefault(venue, {"create": 0, "graduation": 0})
                slot[kind] = slot.get(kind, 0) + 1
                ident = row.get("pool_id") or row.get("mint")
                if ident:
                    (graduated_pools if kind == "graduation" else created_pools) \
                        .setdefault(venue, set()).add(ident)
                ns = row.get("received_unix_nanos")
                if isinstance(ns, int):
                    first_ns = ns if first_ns is None else min(first_ns, ns)
                    last_ns = ns if last_ns is None else max(last_ns, ns)
    matched = {v: len(graduated_pools.get(v, set()) & created_pools.get(v, set())) for v in per}
    return {"tape_path": str(tape.path), "chain_verified": True, "rows": sequence,
            "head_sha256": head_sha, "per_venue": per,
            "graduations_matched_to_a_taped_create": matched,
            "bytes": tape.path.stat().st_size if tape.path.exists() else 0,
            "first_unix_nanos": first_ns, "last_unix_nanos": last_ns,
            "span_hours": None if not (first_ns and last_ns) else round((last_ns - first_ns) / 3.6e12, 3),
            "health": stream_health()}


# ---------------------------------------------------------------------------------------------------
# offline replay against REAL mainnet logs with independent ground truth
# ---------------------------------------------------------------------------------------------------
B11A = _ROOT / "research" / "b11a"


def replay_b11a(limit: int | None = None) -> dict:
    """Replay the decoder over REAL pump.fun mainnet transaction logs already on disk, and check it
    against labels derived by a completely different pipeline.

    `research/b11a/b11a_bodies.sqlite` holds 326,509 full `getTransaction` responses; their
    `meta.logMessages` are the exact byte-for-byte logs a `logsSubscribe` notification carries. So this
    is the live path, replayed offline, with ground truth:

      * every CreateEvent decoded must reproduce `b11a_identity.identity` (mint AND creator), which was
        built from INSTRUCTION ACCOUNTS, not from the event borsh — an independent derivation;
      * every CompleteEvent decoded must land inside `b11a_paths.curve.complete_slot IS NOT NULL`, the
        82-graduation label set, with NO false positive and NO miss.

    This is the strongest available check that the listener's decoder is correct, and it settles the
    transport question for pump.fun by measurement instead of by documentation. No network, no RPC.
    """
    import sqlite3
    import zlib

    bodies, paths_db, ident_db = (B11A / "b11a_bodies.sqlite", B11A / "b11a_paths.sqlite",
                                  B11A / "b11a_identity.sqlite")
    for db in (bodies, paths_db, ident_db):
        if not db.exists():
            raise Refused(f"{db} is absent; the b11a replay needs the historical window on disk")
    V.verify_pinned_idls()
    V.reset_event_stats()
    con = sqlite3.connect(f"file:{bodies}?mode=ro", uri=True)
    labels = {bc for (bc,) in sqlite3.connect(f"file:{paths_db}?mode=ro", uri=True).execute(
        "select bonding_curve from curve where complete_slot is not null")}
    identity = {bc: (mint, creator) for bc, mint, creator in
                sqlite3.connect(f"file:{ident_db}?mode=ro", uri=True).execute(
                    "select bonding_curve, mint, creator from identity")}

    def _logs(signature: str):
        row = con.execute("select raw_zlib from raw_transaction where signature=?",
                          (signature,)).fetchone()
        if row is None:
            return None
        body = json.loads(zlib.decompress(row[0]))
        return ((body.get("result") or {}).get("meta") or {}).get("logMessages")

    def _sigs(idl_name: str, cap: int | None):
        sql = ("select distinct signature from instruction where program_id=? and idl_name=?"
               + (f" limit {int(cap)}" if cap else ""))
        return [s for (s,) in con.execute(sql, (V.PUMP_PROGRAM, idl_name))]

    out = {"create_txs": 0, "creates_decoded": 0, "creates_matched_identity": 0,
           "creates_mismatched": 0, "creates_outside_cohort": 0, "bodies_missing": 0,
           "graduation_txs": 0, "graduations_decoded": 0, "graduations_false_positive": 0,
           "label_count": len(labels), "labels_recovered": 0}
    for sig in _sigs("event:CreateEvent", limit or 250):
        lg = _logs(sig)
        if not lg:
            out["bodies_missing"] += 1
            continue
        out["create_txs"] += 1
        for row in V.decode_logs(V.PUMP_PROGRAM, lg, signature=sig):
            if row["kind"] != "create":
                continue
            out["creates_decoded"] += 1
            ref = identity.get(row["pool_id"])
            if ref is None:
                out["creates_outside_cohort"] += 1
            elif ref == (row["mint"], row["creator"]):
                out["creates_matched_identity"] += 1
            else:
                out["creates_mismatched"] += 1

    recovered = set()
    for sig in _sigs("event:CompleteEvent", None):     # ALL of them: recall is the point
        lg = _logs(sig)
        if not lg:
            out["bodies_missing"] += 1
            continue
        out["graduation_txs"] += 1
        for row in V.decode_logs(V.PUMP_PROGRAM, lg, signature=sig):
            if row["kind"] != "graduation":
                continue
            out["graduations_decoded"] += 1
            if row["pool_id"] in labels:
                recovered.add(row["pool_id"])
            else:
                out["graduations_false_positive"] += 1
    out["labels_recovered"] = len(recovered)
    out["labels_missed"] = len(labels - recovered)
    out["recall"] = len(recovered) / len(labels) if labels else None
    out["event_stats"] = V.EVENT_STATS.get("pump.fun", {})
    out["verdict"] = ("PASS" if (out["creates_mismatched"] == 0 and out["labels_missed"] == 0
                                 and out["graduations_false_positive"] == 0
                                 and out["creates_matched_identity"] > 0) else "FAIL")
    return out


# ---------------------------------------------------------------------------------------------------
# hermetic self-test — no network, no touching the real tape
# ---------------------------------------------------------------------------------------------------
def _selftest() -> None:
    import base64
    import struct
    import tempfile as tf

    V.verify_pinned_idls()

    with tf.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "tape.jsonl"
        # a small reserve so the chain logic is testable on a tmpfs; both bounds are proven below
        tape = MultiVenueTape(path, reserve_bytes=1024)

        # --- empty tape -----------------------------------------------------------------------------
        assert tape.head() == (0, _GENESIS)
        assert tape.read_after(0) == ([], 0)

        # --- append + chain -------------------------------------------------------------------------
        head = tape.head()
        for i in range(3):
            head = tape.append({"venue": "pump.fun", "kind": "create", "mint": f"m{i}"}, head)
        assert head[0] == 3
        assert tape.head() == head, "re-verification must reproduce the head exactly"
        rows, off = tape.read_after(0)
        assert len(rows) == 3 and off == path.stat().st_size
        assert [r["sequence"] for r in rows] == [1, 2, 3]
        assert rows[0]["previous_record_sha256"] == _GENESIS
        assert rows[1]["previous_record_sha256"] == rows[0]["record_sha256"]

        # --- incremental read resumes at the offset --------------------------------------------------
        head = tape.append({"venue": "letsbonk", "kind": "graduation", "pool_id": "p9"}, head)
        more, off2 = tape.read_after(off)
        assert len(more) == 1 and more[0]["venue"] == "letsbonk" and off2 == path.stat().st_size

        # --- a partial trailing line is NOT returned -------------------------------------------------
        with path.open("a") as fh:
            fh.write('{"sequence": 5, "partial": ')
        partial, off3 = tape.read_after(off2)
        assert partial == [] and off3 == off2, "a half-written line must be left for the next pass"
        with path.open("r+") as fh:                      # roll the partial line back
            fh.truncate(off2)

        # --- consumer continuity check ---------------------------------------------------------------
        allrows, _ = tape.read_after(0)
        assert MultiVenueTape.verify_row(allrows[0], 0, _GENESIS)
        assert not MultiVenueTape.verify_row(allrows[0], 1, _GENESIS)          # wrong cursor
        assert not MultiVenueTape.verify_row(allrows[1], 1, "0" * 64)          # wrong head

        # --- TAMPER: flipping one byte of a taped row must REFUSE ------------------------------------
        raw = path.read_bytes()
        good_head = tape.head()
        idx = raw.index(b'"mint":"m1"') + 10
        path.write_bytes(raw[:idx] + b"X" + raw[idx + 1:])
        try:
            tape.head()
        except Refused:
            pass
        else:
            raise AssertionError("a tampered tape row must refuse")
        try:
            tape.append({"venue": "x", "kind": "create"}, good_head)
        except Refused:
            pass                                          # cannot even re-derive a head to append on
        path.write_bytes(raw)                             # restore
        assert tape.head() == good_head

        # --- TRUNCATION: a lost row must REFUSE ------------------------------------------------------
        lines = raw.decode().splitlines()
        path.write_text("\n".join(lines[:1] + lines[2:]) + "\n")
        try:
            tape.head()
        except Refused:
            pass
        else:
            raise AssertionError("a truncated (sequence-gap) tape must refuse")
        path.write_bytes(raw)

        # --- decode -> tape end to end, on hand-built borsh (no network) ------------------------------
        mint, curve, user = bytes(range(32)), bytes(range(32, 64)), bytes(range(64, 96))
        complete = (V.DISC_PUMP_COMPLETE + user + mint + curve + struct.pack("<q", 5) + bytes(32))
        logs = [f"Program {V.PUMP_PROGRAM} invoke [1]",
                "Program data: " + base64.b64encode(complete).decode(),
                f"Program {V.PUMP_PROGRAM} success"]
        decoded = V.decode_logs(V.PUMP_PROGRAM, logs, signature="sig1", slot=7)
        assert len(decoded) == 1 and decoded[0]["kind"] == "graduation"
        head = tape.head()
        head = tape.append({**decoded[0], "tape_schema": TAPE_SCHEMA, "source": SOURCE,
                            "received_unix_nanos": 1}, head)
        assert tape.head() == head
        rep = report(tape)
        assert rep["rows"] == head[0] and rep["per_venue"]["pump.fun"]["graduation"] == 1, rep

        # --- the size bounds REFUSE, both of them -----------------------------------------------------
        tiny = MultiVenueTape(path, max_bytes=1, reserve_bytes=1024)
        try:
            tiny.append({"venue": "x", "kind": "create"}, tape.head())
        except Refused as exc:
            assert "segment bound" in str(exc), exc
        else:
            raise AssertionError("the segment bound must refuse")
        greedy = MultiVenueTape(path, reserve_bytes=1 << 62)
        try:
            greedy.append({"venue": "x", "kind": "create"}, tape.head())
        except Refused as exc:
            assert "filesystem reserve" in str(exc), exc
        else:
            raise AssertionError("the filesystem reserve must refuse")
        assert tape.head() == head, "a refused append must leave the chain untouched"

        # --- dedup key ------------------------------------------------------------------------------
        assert _dedup_key(decoded[0]) == _dedup_key(dict(decoded[0]))
        other = {**decoded[0], "signature": "sig2"}
        assert _dedup_key(other) != _dedup_key(decoded[0])

    # --- host allowlist: only wss to an allowlisted read host --------------------------------------
    assert assert_allowed_ws("wss://mainnet.helius-rpc.com/?api-key=x")
    # the free public Solana RPC is deliberately admitted (Helius credits exhausted; $0 operation)
    assert assert_allowed_ws("wss://api.mainnet-beta.solana.com/")
    for bad in ("https://mainnet.helius-rpc.com/", "ws://mainnet.helius-rpc.com/",
                "wss://pumpportal.fun/api/data",
                "wss://api.mainnet-beta.solana.com.attacker.tld/",   # suffix-attack on the public host
                "wss://evil.mainnet.helius-rpc.com.attacker.tld/",
                "wss://mainnet.helius-rpc.com.attacker.tld/"):
        try:
            assert_allowed_ws(bad)
        except Refused:
            continue
        raise AssertionError(f"{bad} must be refused by the host allowlist")

    # --- health assessor is FAIL-CLOSED ------------------------------------------------------------
    now = time.time_ns()
    assert assess_stream_health(None)["status"] == "MISSING"
    assert assess_stream_health({"schema": 99})["status"] == "MISSING"
    assert assess_stream_health({"schema": HEALTH_SCHEMA, "status": "DISCONNECTED"})["ok"] is False
    assert assess_stream_health({"schema": HEALTH_SCHEMA, "status": "CONNECTED",
                                 "last_message_unix_nanos": now}, now_ns=now)["ok"] is True
    stale = assess_stream_health({"schema": HEALTH_SCHEMA, "status": "CONNECTED",
                                  "last_message_unix_nanos": now - 120 * 10**9}, now_ns=now)
    assert stale["ok"] is False and stale["status"] == "STALE"
    future = assess_stream_health({"schema": HEALTH_SCHEMA, "status": "CONNECTED",
                                   "last_message_unix_nanos": now + 10**9}, now_ns=now)
    assert future["status"] == "INVALID_CLOCK"

    # --- unknown program refuses --------------------------------------------------------------------
    try:
        run_listener(seconds=0, programs=["not_a_venue"])
    except Refused:
        pass
    else:
        raise AssertionError("an unknown venue program must refuse")

    # --- secrets never leak into a log line ---------------------------------------------------------
    key = _env("HELIUS_API_KEY") or _env("HELIUS_RPC_URL")
    if key:
        assert key not in _redact(f"boom {key} boom"), "the redactor must strip the endpoint/key"

    print("multivenue_tape.py self-check OK: chain append/verify, tamper + truncation refusal, "
          "incremental read, partial-line safety, decode->tape, host allowlist, fail-closed health")



@contextlib.contextmanager
def single_writer():
    """Exclusive, fail-closed single-writer guard for the hash-chained tape.

    Two concurrent collectors each read head() then O_APPEND: their records interleave, the sequence
    numbers collide and the chain is irrecoverably broken from that point. That is not hypothetical —
    it is exactly how `pumpportal_trades_v2.corrupt_tail.20260902T132123Z.jsonl` was produced (993 rows
    discarded, chain truncated back to the last valid prefix). Refuse rather than corrupt.
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise SystemExit(f"REFUSED: another multivenue collector holds {LOCK_PATH}; "
                         "concurrent appends corrupt the hash chain")
    try:
        handle.write(str(os.getpid())); handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


# ---------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="multi-venue launch + graduation collector (read-only)")
    ap.add_argument("--seconds", type=float, default=None, help="bounded connectivity/transport test")
    ap.add_argument("--programs", type=str, default=None,
                    help=f"comma-separated subset of {sorted(V.PROGRAMS)}")
    ap.add_argument("--selftest", action="store_true", help="hermetic self-test, no network")
    ap.add_argument("--report", action="store_true", help="verify + summarise the existing tape")
    ap.add_argument("--replay-b11a", action="store_true",
                    help="offline decoder regression over REAL b11a mainnet logs (no network)")
    ap.add_argument("--limit", type=int, default=250, help="create txs to replay (--replay-b11a)")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    elif args.replay_b11a:
        print(json.dumps(replay_b11a(limit=args.limit), indent=2, default=str))
    elif args.report:
        print(json.dumps(report(), indent=2, default=str))
    else:
        progs = [p.strip() for p in args.programs.split(",")] if args.programs else None
        with single_writer():          # the only path that APPENDS to the tape
            print(json.dumps(run_listener(seconds=args.seconds, programs=progs), indent=2, default=str))
