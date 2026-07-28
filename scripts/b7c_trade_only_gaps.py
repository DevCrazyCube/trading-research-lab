#!/usr/bin/env python3
"""B7c - trade-only silence intervals, with the proxy distortion measured rather than assumed.

Codex's audit of B7b established two defects:
  1. the mint-signature proxy SPLITS true trade-silence intervals with non-trade activity, so a
     threshold derived from it is too SHORT - anti-conservative, the opposite of B7b's claim;
  2. B7b silently capped histories at six pages (6,000 signatures), distorting the percentiles.

This script fixes both and, rather than merely asserting a bound, MEASURES the distortion: for
each token it computes gaps twice - once over all address signatures, once over decoded
`TradeEvent` timestamps only - so the ratio between them is an observed quantity.

Every pagination or selection cap is reported explicitly. Read-only, no signing.
RPC from SOLANA_RPC_URL; never printed or persisted.

Usage: b7c_trade_only_gaps.py --burn-lo N --burn-hi N [--tokens K] [--max-sigs M]
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import time
import urllib.request

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EVENT_TAG = bytes.fromhex("e445a52e51cb9a1d")
TE_DISC = hashlib.sha256(b"event:TradeEvent").digest()[:8]
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


def full_history(addr, max_sigs):
    """All signatures for an address. Returns (list, hit_cap)."""
    out, before = [], None
    while len(out) < max_sigs:
        p = {"limit": 1000, "commitment": "finalized"}
        if before:
            p["before"] = before
        r = rpc("getSignaturesForAddress", [addr, p])
        if not r:
            return out, False
        out.extend(r)
        if len(r) < 1000:
            return out, False
        before = r[-1]["signature"]
    return out, True


def is_trade(sig):
    """Fetch one transaction and report whether it emits a Pump TradeEvent, with its timestamp."""
    tx = rpc("getTransaction", [sig, {"encoding": "jsonParsed",
                                      "maxSupportedTransactionVersion": 0,
                                      "commitment": "finalized"}])
    if not tx:
        return None
    meta = tx.get("meta") or {}
    if meta.get("err"):
        return (False, tx.get("blockTime"))
    for g in meta.get("innerInstructions") or []:
        for ix in g.get("instructions", []):
            if ix.get("programId") != PUMP or not ix.get("data"):
                continue
            raw = b58decode(ix["data"])
            if len(raw) >= 16 and raw[:8] == EVENT_TAG and raw[8:16] == TE_DISC:
                return (True, tx.get("blockTime"))
    return (False, tx.get("blockTime"))


def gapstats(times):
    t = sorted(x for x in times if x)
    return [t[i + 1] - t[i] for i in range(len(t) - 1)] if len(t) > 1 else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--burn-lo", type=int, required=True)
    ap.add_argument("--burn-hi", type=int, required=True, help="exclusive")
    ap.add_argument("--tokens", type=int, default=8)
    ap.add_argument("--max-sigs", type=int, default=100000)
    ap.add_argument("--min-hist", type=int, default=40)
    ap.add_argument("--max-hist", type=int, default=700,
                    help="skip tokens larger than this so every tx can be decoded")
    a = ap.parse_args()

    print("=" * 74)
    print("THROWAWAY SAMPLE - BURNED, never for training/validation/test")
    print(f"slots {a.burn_lo}..{a.burn_hi} (exclusive upper)")
    print("=" * 74)

    mints, seen = [], set()

    def fetch(s):
        return rpc("getBlock", [s, {"encoding": "jsonParsed", "transactionDetails": "full",
                                    "rewards": False, "maxSupportedTransactionVersion": 0}])

    with cf.ThreadPoolExecutor(4) as ex:
        for blk in ex.map(fetch, range(a.burn_lo, a.burn_hi)):
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
                        if len(raw) < 48 or raw[:8] != EVENT_TAG or raw[8:16] != TE_DISC:
                            continue
                        m = b58encode(raw[16:48])
                        if m not in seen:
                            seen.add(m)
                            mints.append(m)
    print(f"\ndistinct mints trading in burn range: {len(mints)}")

    # Size histories first, then pick tokens small enough to decode EXHAUSTIVELY.
    sized, capped_any = [], 0
    with cf.ThreadPoolExecutor(4) as ex:
        for m, (sigs, capped) in zip(mints[:60],
                                     ex.map(lambda x: full_history(x, a.max_sigs), mints[:60])):
            capped_any += capped
            sized.append((m, sigs, capped))
    eligible = [(m, s, c) for m, s, c in sized if a.min_hist <= len(s) <= a.max_hist]
    print(f"histories sized: {len(sized)}   hit --max-sigs cap: {capped_any}")
    print(f"eligible for exhaustive decode ({a.min_hist}-{a.max_hist} sigs): {len(eligible)}")
    chosen = eligible[:a.tokens]
    total_tx = sum(len(s) for _, s, _ in chosen)
    print(f"decoding ALL transactions for {len(chosen)} tokens ({total_tx} transactions)\n")

    rows = []
    for mint, sigs, capped in chosen:
        siglist = [s["signature"] for s in sigs]
        with cf.ThreadPoolExecutor(4) as ex:
            res = list(ex.map(is_trade, siglist))
        got = [r for r in res if r]
        trade_times = [t for ok, t in got if ok and t]
        all_times = [t for _, t in got if t]
        g_all, g_trade = gapstats(all_times), gapstats(trade_times)
        rows.append({
            "mint": mint, "sigs": len(sigs), "decoded": len(got),
            "trades": len(trade_times),
            "trade_frac": len(trade_times) / max(len(got), 1),
            "g_all": g_all, "g_trade": g_trade, "capped": capped,
        })
        print(f"  {mint[:14]}...  sigs={len(sigs):>4}  trades={len(trade_times):>4} "
              f"({100*rows[-1]['trade_frac']:.0f}%)  max_gap_all="
              f"{(max(g_all)/3600 if g_all else 0):.2f}h  max_gap_trade="
              f"{(max(g_trade)/3600 if g_trade else 0):.2f}h")

    all_g = sorted(g for r in rows for g in r["g_all"])
    trd_g = sorted(g for r in rows for g in r["g_trade"])
    if not trd_g:
        print("\nno trade gaps"); return 1

    def pct(v, q):
        return v[min(int(q * len(v)), len(v) - 1)]

    print(f"\n{'=' * 74}")
    print(f"tokens: {len(rows)}   all-signature gaps: {len(all_g)}   TRADE-ONLY gaps: {len(trd_g)}")
    print(f"median trade fraction: {sorted(r['trade_frac'] for r in rows)[len(rows)//2]:.3f}")
    print(f"\n{'quantile':>10}{'all-sig (s)':>14}{'trade-only (s)':>16}{'ratio':>9}")
    for q in (0.5, 0.9, 0.99, 0.999, 0.9999):
        av, tv = pct(all_g, q), pct(trd_g, q)
        print(f"{'p'+format(q*100,'.4g'):>10}{av:>14.0f}{tv:>16.0f}{(tv/av if av else 0):>9.2f}")
    print(f"{'max':>10}{all_g[-1]:>14.0f}{trd_g[-1]:>16.0f}"
          f"{(trd_g[-1]/all_g[-1] if all_g[-1] else 0):>9.2f}")

    print(f"\n--- incidence at candidate thresholds (TRADE-ONLY gaps) ---")
    print(f"{'thresh':>8}{'gaps':>8}{'% gaps':>10}{'tokens':>9}{'% tokens':>10}")
    for h in (1, 6, 12, 24, 48, 72, 168):
        t = h * 3600
        ng = sum(1 for g in trd_g if g >= t)
        nt = sum(1 for r in rows if any(g >= t for g in r["g_trade"]))
        print(f"{str(h)+'h':>8}{ng:>8}{100*ng/len(trd_g):>9.4f}%{nt:>9}"
              f"{100*nt/len(rows):>9.1f}%")

    print(f"\nCAPS APPLIED (all reported, none silent):")
    print(f"  --max-sigs {a.max_sigs} : histories hitting it = {sum(r['capped'] for r in rows)}")
    print(f"  --max-hist {a.max_hist} : tokens excluded as too large to decode exhaustively")
    print(f"  --min-hist {a.min_hist} : tokens excluded as too small")
    print(f"  token count capped at {a.tokens}; discovery scanned first 60 mints")
    print(f"\nBURNED: slots {a.burn_lo}..{a.burn_hi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
