#!/usr/bin/env python3
"""B6f - does free `blockSubscribe` work, and can it keep up with Pump traffic?

Tests Codex's Seq-24 narrowing: F26 disqualified HTTP polling, not every free push
transport. `blockSubscribe` takes a `mentionsAccountOrProgram` filter and carries full
transaction metadata including inner instructions - the fields the TradeEvent decoder needs.

Measures, if it connects at all: notification rate, slot coverage vs chain tip, bytes,
and disconnects. Falls back to reporting the exact server error if the method is disabled.

Read-only. No keys, no signing, no transactions.

Usage: b6f_blocksubscribe_probe.py [seconds] [ws_url]
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from wsmin import WebSocket, WSError  # noqa: E402

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
DEFAULT_WS = "wss://api.mainnet-beta.solana.com"
HTTP = "https://api.mainnet-beta.solana.com"


def http_rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(HTTP, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("result")


def probe(duration, ws_url):
    print(f"connecting: {ws_url}")
    try:
        ws = WebSocket(ws_url, timeout=max(30, duration))
    except (WSError, OSError) as e:
        print(f"CONNECT FAILED: {e}")
        return 1
    print("handshake OK (101 Switching Protocols)\n")

    req = {
        "jsonrpc": "2.0", "id": 1, "method": "blockSubscribe",
        "params": [
            {"mentionsAccountOrProgram": PUMP},
            {"commitment": "confirmed", "encoding": "jsonParsed",
             "transactionDetails": "full", "showRewards": False,
             "maxSupportedTransactionVersion": 0},
        ],
    }
    print("-> blockSubscribe with mentionsAccountOrProgram filter")
    ws.send_text(json.dumps(req))

    started = time.monotonic()
    sub_id = None
    notifications = 0
    total_bytes = 0
    slots = []
    first_at = None
    try:
        while time.monotonic() - started < duration:
            kind, payload, code = ws.recv()
            if kind == "close":
                print(f"\nSERVER CLOSED: code={code} payload={payload[:200]!r}")
                break
            total_bytes += len(payload)
            try:
                msg = json.loads(payload)
            except Exception:  # noqa: BLE001
                continue

            if "error" in msg:
                err = msg["error"]
                print(f"\nSERVER ERROR: code={err.get('code')} message={err.get('message')!r}")
                if err.get("data"):
                    print(f"  data: {str(err['data'])[:300]}")
                ws.close()
                return 2

            if msg.get("id") == 1 and "result" in msg:
                sub_id = msg["result"]
                print(f"<- subscription confirmed, id={sub_id}\n")
                continue

            if msg.get("method") == "blockNotification":
                notifications += 1
                if first_at is None:
                    first_at = time.monotonic()
                val = msg.get("params", {}).get("result", {}).get("value", {})
                slot = val.get("slot")
                blk = val.get("block") or {}
                ntx = len(blk.get("transactions", []) or [])
                if slot:
                    slots.append(slot)
                if notifications <= 5 or notifications % 20 == 0:
                    print(f"  notif #{notifications}: slot {slot}, {ntx} txs, "
                          f"{len(payload)/1024:.0f} KB")
    except (WSError, OSError) as e:
        print(f"\nSTREAM ERROR after {notifications} notifications: {e}")
    finally:
        ws.close()

    el = time.monotonic() - started
    print(f"\n{'=' * 62}")
    if sub_id is None:
        print("blockSubscribe was never confirmed - method unavailable on this endpoint.")
        return 2
    print(f"duration            : {el:.0f}s")
    print(f"notifications       : {notifications} ({notifications/el:.2f}/s vs ~2.5 slots/s produced)")
    print(f"bytes received      : {total_bytes/1024/1024:.2f} MB ({total_bytes/max(el,1)/1024:.0f} KB/s)")
    if slots:
        span = max(slots) - min(slots) + 1
        print(f"slot range          : {min(slots)}..{max(slots)} (span {span})")
        print(f"slot coverage       : {len(set(slots))}/{span} = {100*len(set(slots))/span:.1f}%")
        missing = span - len(set(slots))
        print(f"missing slots       : {missing}")
        tip = http_rpc("getSlot", [{"commitment": "confirmed"}])
        print(f"chain tip now       : {tip}  (lag from last notified: {tip - max(slots)} slots)")
    return 0


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 60
    url = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_WS
    raise SystemExit(probe(dur, url))
