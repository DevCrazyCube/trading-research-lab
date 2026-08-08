"""Measure the endpoint's sustainable getTransaction rate. Read-only, bounded, abort-on-429.

WHY THIS EXISTS. b9d's collector paces at calls_per_second=2.5, a default chosen for a study whose
population was 1,601 curves. B11a's window carries 33,866 -- 21x -- and b11c never passes the flag,
so stage 5 would inherit 2.5/s for an extrapolated ~2.8M calls: about thirteen days. Neither 2.5 nor
any higher number is currently justified by measurement against THIS endpoint, so this measures it.

WHY IT RAMPS UP AND STOPS RATHER THAN FINDING THE CEILING. This project has already had a provider
return 429 on every request from this credential, including signatures it had previously served. The
goal is a rate we can defend, not the maximum the endpoint will tolerate before it refuses us. So:
small bursts, gentle ramp, and the FIRST 429 or 403 ends the whole probe and reports the last clean
rate. Backing off is the result, not a failure of the measurement.

WHAT IT DOES NOT DO. It writes nothing into research/b11a, stores no response, and never prints the
credential -- only scheme://host, through the same `endpoint_identity` contract the pipeline uses.
Probe targets are real create-transaction signatures read READ-ONLY out of the existing enumeration,
so the calls are representative of stage 5's actual work rather than a synthetic getSlot.

Latency here is float, deliberately and only here: this is a measurement of the world, not the
pipeline's arithmetic, and nothing it produces is ever an input to a quantity the study reports.
"""
import importlib.util
import json
import os
import pathlib
import sqlite3
import statistics
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path("/home/anont/meme")
BURST = 25                 # calls per rate step
RATES = (2.5, 5, 10, 20, 40)
TOTAL_CAP = 150            # hard ceiling on calls, whatever the ramp decides
TIMEOUT = 20


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HTTP = _load("rpc_http_identity", "rpc_http_identity.py")


def endpoint():
    """From the environment if the operator sourced it, else from .env, never printed."""
    url = os.environ.get("SOLANA_RPC_URL")
    if url:
        return url
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line.startswith("SOLANA_RPC_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("REFUSING: SOLANA_RPC_URL is not available")


def signatures(limit):
    """Real create signatures, read-only, from the enumeration that already exists."""
    db = sqlite3.connect(f"file:{ROOT}/research/b11a/b11a_creates.sqlite?mode=ro", uri=True)
    try:
        rows = [r[0] for r in db.execute(
            "SELECT signature FROM create_event ORDER BY slot, transaction_index LIMIT ?",
            (limit,))]
    finally:
        db.close()
    return rows


def one_call(url, signature):
    """Returns (ok, status_or_None, seconds). Never raises for an HTTP status."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                       "params": [signature, {"encoding": "json",
                                              "commitment": "finalized",
                                              "maxSupportedTransactionVersion": 0}]}).encode()
    request = HTTP.json_rpc_request(url, body)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            response.read()
            return True, response.status, time.monotonic() - started
    except urllib.error.HTTPError as error:
        return False, error.code, time.monotonic() - started
    except Exception as error:                      # transport fault, not a status
        return False, type(error).__name__, time.monotonic() - started


def main():
    url = endpoint()
    print(f"endpoint      {HTTP.endpoint_identity(url)}")
    targets = signatures(TOTAL_CAP)
    print(f"probe targets {len(targets)} real create signatures, read-only from the enumeration")
    print(f"method        getTransaction (what stage 5 actually calls)")
    print(f"policy        burst={BURST}, cap={TOTAL_CAP}, ABORT on first 429/403\n")

    spent, results, stopped = 0, [], None
    for rate in RATES:
        if spent + BURST > TOTAL_CAP:
            print(f"  (cap reached before {rate}/s)")
            break
        interval = 1.0 / rate
        latencies, failures = [], []
        started = time.monotonic()
        for index in range(BURST):
            due = started + index * interval
            delay = due - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            ok, status, seconds = one_call(url, targets[(spent + index) % len(targets)])
            spent += 1
            latencies.append(seconds)
            if not ok:
                failures.append(status)
                if status in (429, 403):
                    stopped = (rate, status)
                    break
        elapsed = time.monotonic() - started
        achieved = len(latencies) / elapsed if elapsed else 0.0
        row = {"requested_rate": rate, "achieved_rate": round(achieved, 2),
               "calls": len(latencies), "failures": failures,
               "p50_ms": round(statistics.median(latencies) * 1000),
               "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95) - 1] * 1000)}
        results.append(row)
        print(f"  {rate:>5}/s requested -> {achieved:>5.2f}/s achieved, "
              f"{len(latencies)} calls, p50 {row['p50_ms']}ms p95 {row['p95_ms']}ms, "
              f"failures={failures or 'none'}")
        if stopped:
            print(f"\n  *** ABORTED at {stopped[0]}/s on HTTP {stopped[1]}. "
                  f"Backing off is the result. ***")
            break

    clean = [r for r in results if not r["failures"]]
    print("\nHIGHEST CLEAN REQUESTED RATE:",
          f"{max(r['requested_rate'] for r in clean)}/s" if clean else "none")
    print("TOTAL CALLS SPENT:", spent)
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if out:
        out.write_text(json.dumps({"endpoint": HTTP.endpoint_identity(url),
                                   "steps": results, "aborted": stopped,
                                   "calls_spent": spent}, indent=2) + "\n")
        print("written to", out)


if __name__ == "__main__":
    main()
