#!/usr/bin/env python3
"""Measure processed/confirmed public-RPC arrival deltas without window bias.

Both subscriptions acknowledge before a shared capture window starts. New processed
cohort members are admitted only during that window; both streams remain open for a grace
interval so confirmations near the right edge are not falsely censored.

This is client-observed arrival difference, not cluster commitment latency or event-to-client
decision latency. Read-only: no keys, signing, or transactions.
"""
import json
import statistics
import sys
import threading
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from wsmin import WebSocket, WSError  # noqa: E402

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WS = "wss://api.mainnet-beta.solana.com"


def percentile(values, q):
    return values[min(int(q * len(values)), len(values) - 1)]


def summarize(seen, start_ns, end_ns):
    p, confirmed = seen["processed"], seen["confirmed"]
    cohort = {sig for sig, (at, _) in p.items() if start_ns <= at < end_ns}
    matched = cohort & set(confirmed)
    deltas = sorted((confirmed[sig][0] - p[sig][0]) / 1e6 for sig in matched)
    confirmed_core = {sig for sig, (at, _) in confirmed.items() if start_ns <= at < end_ns}
    return cohort, matched, deltas, confirmed_core - set(p)


def reader(commitment, ready, start, end_ns, grace_ns, seen, stats, errors, lock):
    ws = None
    try:
        ws = WebSocket(WS, timeout=45)
        ws.send_text(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
            "params": [{"mentions": [PUMP]}, {"commitment": commitment}]}))
        while True:
            kind, payload, code = ws.recv()
            if kind == "close":
                raise WSError(f"closed before acknowledgement code={code}")
            msg = json.loads(payload)
            if msg.get("id") == 1 and "result" in msg:
                break
            if "error" in msg:
                raise WSError(f"subscription error: {msg['error']}")
        ready.wait()
        start.wait()
        deadline = end_ns[0] + grace_ns
        while time.monotonic_ns() < deadline:
            kind, payload, code = ws.recv()
            now = time.monotonic_ns()
            if kind == "close":
                errors[commitment] = f"closed code={code}"
                break
            msg = json.loads(payload)
            if msg.get("method") != "logsNotification":
                continue
            val = msg["params"]["result"]["value"]
            sig = val.get("signature")
            if not sig:
                continue
            with lock:
                stats[commitment]["n"] += 1
                stats[commitment]["err"] += bool(val.get("err"))
                seen[commitment].setdefault(sig, (now, bool(val.get("err"))))
    except (WSError, OSError, ValueError, KeyError, threading.BrokenBarrierError) as exc:
        errors[commitment] = str(exc)
        try:
            ready.abort()
        except threading.BrokenBarrierError:
            pass
        start.set()
    finally:
        if ws is not None:
            ws.close()


def main():
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    grace = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    ready, start, end_ns = threading.Barrier(3), threading.Event(), [0]
    seen = {"processed": {}, "confirmed": {}}
    stats = {c: {"n": 0, "err": 0} for c in ("processed", "confirmed")}
    errors, lock = {}, threading.Lock()
    threads = [threading.Thread(target=reader, args=(
        c, ready, start, end_ns, int(grace * 1e9), seen, stats, errors, lock), daemon=True)
        for c in ("processed", "confirmed")]
    print(f"arming processed + confirmed; capture={duration:.0f}s grace={grace:.1f}s")
    for thread in threads:
        thread.start()
    try:
        ready.wait(timeout=30)
    except threading.BrokenBarrierError:
        start.set()
        for thread in threads:
            thread.join(timeout=5)
        print(f"subscription setup failed: {errors}")
        return 1
    capture_start_ns = time.monotonic_ns()
    end_ns[0] = capture_start_ns + int(duration * 1e9)
    start.set()
    for thread in threads:
        thread.join(timeout=duration + grace + 50)
    if any(thread.is_alive() for thread in threads):
        print("reader did not stop cleanly")
        return 1

    cohort, matched, deltas, confirmed_only = summarize(seen, capture_start_ns, end_ns[0])
    for commitment, error in errors.items():
        print(f"  {commitment} stream error: {error}")
    print("=" * 62)
    for commitment in ("processed", "confirmed"):
        st = stats[commitment]
        print(f"{commitment:<10} notifications {st['n']:>7}  unique "
              f"{len(seen[commitment]):>7}  failed {100*st['err']/max(st['n'],1):.1f}%")
    print(f"\nprocessed cohort admitted during capture: {len(cohort)}")
    print(f"matched by end of {grace:.1f}s grace: {len(matched)}")
    print(f"unmatched after grace: {len(cohort - matched)}")
    print(f"confirmed-core without any processed observation (diagnostic): {len(confirmed_only)}")
    if not deltas:
        print("no correlated signatures")
        return 1
    negative = sum(delta < 0 for delta in deltas)
    print(f"\npublic-endpoint arrival delta, processed -> confirmed (ms), n={len(deltas)}")
    print(f"  min {deltas[0]:9.1f}  p10 {percentile(deltas,.10):9.1f}  "
          f"median {statistics.median(deltas):9.1f}")
    print(f"  p90 {percentile(deltas,.90):9.1f}  p99 {percentile(deltas,.99):9.1f}  "
          f"max {deltas[-1]:9.1f}  mean {statistics.fmean(deltas):9.1f}")
    print(f"  negative arrivals: {negative} ({100*negative/len(deltas):.2f}%)")
    print("\nConfirmed-only is not a proven processed-stream miss: independent public-RPC "
          "fanout has no completeness oracle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
