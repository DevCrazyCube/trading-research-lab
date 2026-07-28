#!/usr/bin/env python3
"""B6j - can free-endpoint `getTransaction` backfill keep up with Pump trade volume?

The logs feed carries TradeEvent but NOT fees paid, compute units, tips, account keys or
balance deltas. Cost reconstruction (F12/B4-style) therefore needs a follow-up
`getTransaction` per transaction of interest. This measures whether the free public endpoint
can sustain that rate, and if not, what sampling fraction it can sustain.

Method: ramp offered concurrency, measure achieved throughput and error/rate-limit response
at each step. Reports the sustainable rate against the measured demand.

Read-only. No keys, no signing, no transactions.

Usage: b6j_backfill_capacity.py [seconds_per_step]
"""
import json
import argparse
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
STEPS = [1, 2, 4, 8, 16]


def get_signatures(rpc_url, limit=1000):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                       "params": [PUMP, {"limit": limit, "commitment": "finalized"}]}).encode()
    req = urllib.request.Request(rpc_url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return [s["signature"] for s in json.loads(r.read()).get("result", [])]


def worker(q, res, stop, rpc_url):
    while not stop.is_set():
        try:
            sig = q.get(timeout=0.5)
        except queue.Empty:
            return
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                           "params": [sig, {"encoding": "jsonParsed",
                                            "maxSupportedTransactionVersion": 0,
                                            "commitment": "finalized"}]}).encode()
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(rpc_url, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = r.read()
            obj = json.loads(payload)
            if "error" in obj:
                res.append(("rpc_error", time.monotonic() - t0, len(payload),
                            str(obj["error"].get("code"))))
            else:
                res.append(("ok", time.monotonic() - t0, len(payload), None))
        except urllib.error.HTTPError as e:
            res.append(("http_%d" % e.code, time.monotonic() - t0, 0, None))
        except Exception as e:  # noqa: BLE001
            res.append(("exc", time.monotonic() - t0, 0, type(e).__name__))


def run_step(sigs, concurrency, seconds, rpc_url=DEFAULT_RPC):
    q = queue.Queue()
    for s in sigs:
        q.put(s)
    res, stop = [], threading.Event()
    threads = [threading.Thread(target=worker, args=(q, res, stop, rpc_url), daemon=True)
               for _ in range(concurrency)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    while time.monotonic() - t0 < seconds and any(t.is_alive() for t in threads):
        time.sleep(0.2)
    stop.set()
    for t in threads:
        t.join(timeout=10)
    el = time.monotonic() - t0
    ok = [r for r in res if r[0] == "ok"]
    rate_limited = [r for r in res if r[0].startswith("http_429") or r[0] == "rpc_error"]
    other_err = [r for r in res if r not in ok and r not in rate_limited]
    lat = sorted(r[1] for r in ok)
    return {
        "concurrency": concurrency, "elapsed": el, "attempts": len(res),
        "ok": len(ok), "rate_limited": len(rate_limited), "other_err": len(other_err),
        "ok_per_s": len(ok) / el if el else 0,
        "p50_ms": lat[len(lat)//2] * 1000 if lat else None,
        "p90_ms": lat[int(len(lat)*0.9)] * 1000 if lat else None,
        "bytes_per_tx": (sum(r[2] for r in ok) / len(ok)) if ok else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("seconds_per_step", nargs="?", type=float, default=20)
    parser.add_argument("--rpc-env", default="SOLANA_RPC_URL",
                        help="environment variable containing RPC URL; never persisted/printed")
    args = parser.parse_args()
    per_step = args.seconds_per_step
    rpc_url = os.environ.get(args.rpc_env, DEFAULT_RPC)
    endpoint_ref = "public-mainnet" if rpc_url == DEFAULT_RPC else "configured-mainnet"
    print(f"endpoint: {endpoint_ref} (URL redacted)")
    print("fetching a signature pool...")
    pool = get_signatures(rpc_url, 1000)
    print(f"pool: {len(pool)} signatures\n")
    print(f"{'conc':>5}{'ok':>7}{'ok/s':>8}{'429/err':>9}{'other':>7}{'p50 ms':>9}{'p90 ms':>9}{'KB/tx':>8}")
    rows = []
    for c in STEPS:
        r = run_step(list(pool), c, per_step, rpc_url)
        rows.append(r)
        print(f"{r['concurrency']:>5}{r['ok']:>7}{r['ok_per_s']:>8.2f}"
              f"{r['rate_limited']:>9}{r['other_err']:>7}"
              f"{(r['p50_ms'] or 0):>9.0f}{(r['p90_ms'] or 0):>9.0f}"
              f"{r['bytes_per_tx']/1024:>8.1f}")
        time.sleep(3)

    best = max(rows, key=lambda r: r["ok_per_s"])
    print(f"\nbest sustained: {best['ok_per_s']:.2f} tx/s at concurrency {best['concurrency']}")
    print(f"  (rate-limited/errored at that step: {best['rate_limited']}/{best['attempts']})")

    # Demand: measured successful Pump transactions per second from the logs feed.
    demand_ok_tx_per_s = 1080 / 90          # B6h logs adapter run
    demand_all_tx_per_s = 15164 / 90
    print(f"\ndemand from B6h logs run:")
    print(f"  successful Pump txs : {demand_ok_tx_per_s:.1f}/s")
    print(f"  all Pump-mentioning : {demand_all_tx_per_s:.1f}/s")
    if best["ok_per_s"] > 0:
        print(f"\nfeasible backfill coverage at best rate:")
        print(f"  of successful txs   : {min(100, 100*best['ok_per_s']/demand_ok_tx_per_s):.1f}%")
        print(f"  of all Pump txs     : {min(100, 100*best['ok_per_s']/demand_all_tx_per_s):.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
