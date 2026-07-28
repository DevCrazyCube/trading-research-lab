#!/usr/bin/env python3
"""B7b - derive D_dead (the abandonment threshold) from a THROWAWAY sample.

docs/DEFINITIONS.md requires D_dead to be frozen a priori, because choosing it after seeing
which value flatters a result is optimising on the evaluation set. This derives it from a
sample that is explicitly BURNED: the slot range used here is recorded and must never appear
in any training, validation or test set.

Principle: D_dead should be a silence long enough that resumption is rare. So we measure, for
each observed gap between consecutive activity timestamps, the empirical
    P(token is active again later | it has already been silent for >= g)
and pick the g where that resumption probability collapses.

Activity proxy: signatures on the mint address. This OVER-counts trading (it includes
transfers, ATA creation, etc.), so gaps measured here are a LOWER bound on true trade
silence, and a D_dead chosen from it is conservative in the safe direction.

RPC from SOLANA_RPC_URL, never printed or persisted. Read-only, no signing.

Usage: b7b_dead_threshold.py [num_tokens]
"""
import concurrent.futures as cf
import argparse
import json
import os
import sys
import time
import urllib.request
from collections import Counter

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EVENT_TAG = bytes.fromhex("e445a52e51cb9a1d")
URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {c: i for i, c in enumerate(B58)}


def b58decode(s):
    n = 0
    for ch in s:
        n = n * 58 + B58_MAP[ch]
    return b"\0" * (len(s) - len(s.lstrip("1"))) + (n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b"")


def b58encode(b):
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + out


def rpc(method, params, retries=4):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                o = json.loads(r.read())
            if "error" in o:
                if a < retries - 1:
                    time.sleep(1.0 * (a + 1)); continue
                return None
            return o["result"]
        except Exception:  # noqa: BLE001
            if a == retries - 1:
                return None
            time.sleep(1.0 * (a + 1))
    return None


def history(mint, max_pages):
    """Signature history for an address, newest first, with explicit cap status."""
    out, before = [], None
    for _ in range(max_pages):
        p = {"limit": 1000, "commitment": "finalized"}
        if before:
            p["before"] = before
        r = rpc("getSignaturesForAddress", [mint, p])
        if not r:
            break
        out.extend(r)
        if len(r) < 1000:
            return out, False
        before = r[-1]["signature"]
    return out, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokens", type=int, default=30)
    parser.add_argument("--burn-lo", type=int)
    parser.add_argument("--burn-hi", type=int, help="exclusive upper slot")
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args()
    ntok = args.tokens
    if (args.burn_lo is None) != (args.burn_hi is None):
        parser.error("--burn-lo and --burn-hi must be supplied together")
    if args.burn_lo is None:
        tip = rpc("getSlot", [{"commitment": "finalized"}])
        burn_lo, burn_hi = tip - 40, tip - 2
    else:
        burn_lo, burn_hi = args.burn_lo, args.burn_hi
    print("=" * 70)
    print("THROWAWAY SAMPLE - this slot range is BURNED and must never be used")
    print(f"for training, validation or test:  slots {burn_lo}..{burn_hi}")
    print("=" * 70)

    # Collect distinct mints from TradeEvents in the burn range.
    import hashlib
    te = hashlib.sha256(b"event:TradeEvent").digest()[:8]
    mints = []
    seen = set()

    def fetch(s):
        return rpc("getBlock", [s, {"encoding": "jsonParsed", "transactionDetails": "full",
                                    "rewards": False, "maxSupportedTransactionVersion": 0}])

    with cf.ThreadPoolExecutor(4) as ex:
        for blk in ex.map(fetch, range(burn_lo, burn_hi)):
            if not blk:
                continue
            for tx in blk.get("transactions", []):
                if (tx.get("meta") or {}).get("err"):
                    continue
                for g in (tx.get("meta") or {}).get("innerInstructions") or []:
                    for ix in g.get("instructions", []):
                        if ix.get("programId") != PUMP or not ix.get("data"):
                            continue
                        raw = b58decode(ix["data"])
                        if len(raw) < 48 or raw[:8] != EVENT_TAG or raw[8:16] != te:
                            continue
                        m = b58encode(raw[16:48])
                        if m not in seen:
                            seen.add(m)
                            mints.append(m)
    print(f"\ndistinct mints observed trading in burn range: {len(mints)}")
    sample = mints[:ntok]
    print(f"pulling full history for {len(sample)} of them...\n")

    all_gaps = []
    per_token = []
    with cf.ThreadPoolExecutor(4) as ex:
        results = ex.map(lambda mint: history(mint, args.max_pages), sample)
        for mint, (sigs, capped) in zip(sample, results):
            times = sorted(s["blockTime"] for s in sigs if s.get("blockTime"))
            if len(times) < 3:
                continue
            gaps = [times[i + 1] - times[i] for i in range(len(times) - 1)]
            all_gaps.extend(gaps)
            per_token.append((mint, len(sigs), times[-1] - times[0], gaps, capped))

    if not all_gaps:
        print("no usable histories")
        return 1

    all_gaps.sort()
    n = len(all_gaps)
    def pct(q):
        return all_gaps[min(int(q * n), n - 1)]

    print(f"tokens with usable history : {len(per_token)}")
    print(f"histories capped at {args.max_pages * 1000:>6}: "
          f"{sum(capped for *_, capped in per_token)}")
    print(f"total inter-activity gaps  : {n}")
    print(f"\ninter-activity gap distribution (seconds):")
    for q in (0.5, 0.9, 0.99, 0.999, 0.9999):
        print(f"  p{q*100:<7.4g} {pct(q):>10.0f} s  = {pct(q)/60:>8.1f} min = {pct(q)/3600:>6.2f} h")
    print(f"  max      {all_gaps[-1]:>10.0f} s  = {all_gaps[-1]/3600:>6.2f} h")

    # Resumption curve: of gaps >= g, these are by construction followed by more activity
    # (they are interior gaps). Compare against each token's FINAL silence.
    print(f"\nresumption analysis:")
    print(f"  every gap above is INTERIOR - the token did resume afterwards.")
    print(f"  so the largest interior gap is a lower bound on 'silence that still resumed'.")
    print(f"  largest interior gap observed: {all_gaps[-1]:.0f} s = {all_gaps[-1]/3600:.2f} h")
    for thresh_h in (1, 6, 12, 24, 48, 72):
        t = thresh_h * 3600
        survived = sum(1 for g in all_gaps if g >= t)
        affected = sum(1 for _, _, _, gaps, _ in per_token if any(g >= t for g in gaps))
        print(f"    gaps >= {thresh_h:>2}h that still resumed: {survived:>6}  "
              f"({100*survived/n:.4f}% of all gaps); distinct tokens: {affected:>3}/"
              f"{len(per_token)} ({100*affected/len(per_token):.1f}%)")

    print(f"\n  -> D_dead must exceed the largest silence from which tokens routinely resume,")
    print(f"     otherwise live-but-quiet tokens are misclassified as abandoned.")
    print(f"\nBURNED RANGE (record this): slots {burn_lo}..{burn_hi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
