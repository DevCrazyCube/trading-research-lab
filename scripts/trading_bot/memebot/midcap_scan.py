"""Solana mid-cap memecoin flow collector.

Snapshots the active Solana memecoin universe from DexScreener on a fixed cadence and
appends to a single-writer, append-only JSONL. Collection only -- computes no verdict.
Governed by research/midcap/MIDCAP_FLOW_PREREGISTRATION.md (sha 3f235481...).

New file by construction: touches no arena closure member.
"""
from __future__ import annotations
import contextlib, fcntl, json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "midcap" / "snapshots.jsonl"
LOCK = ROOT / "research" / "midcap" / ".collector.lock"
SEEN = ROOT / "research" / "midcap" / "seen_pairs.json"

MIN_LIQ_USD = 20_000.0
MIN_AGE_MS = 3_600_000
MIN_VOL24_USD = 50_000.0   # activity gate: dead pools quote huge "liquidity" with ~0 txns
MIN_TXNS24 = 100
MAX_LIQ_USD = 100_000_000.0
CADENCE_S = 300
API = "https://api.dexscreener.com"

# Fixed query list, frozen with the prereg. No discretion, no mid-run edits.
QUERIES = [
    "bonk","wif","pepe","doge","cat","dog","moon","pump","meme","inu","shib","frog","baby",
    "elon","trump","ai","agent","sol","usdc","gm","wojak","chad","fartcoin","popcat",
    "mog","brett","giga","spx","turbo","goat","act","pnut","moodeng","chillguy","neiro","ponke",
    "coin","token","king","god","boy","girl","man","bear","bull","ape","monkey","bird","fish",
    "rock","fire","ice","star","sun","gold","green","red","blue","black","white","big","little",
    "new","old","good","bad","hot","cool","fast","rich","money","bank","trade","win","lucky",
    "happy","sad","mad","love","hate","life","dead","zero","one","two","x","z","q",
]

def _get(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"User-Agent": "midcap-scan/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

@contextlib.contextmanager
def single_writer():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    h = LOCK.open("w")
    try:
        fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(f"REFUSED: another midcap collector holds {LOCK}")
    try:
        yield
    finally:
        fcntl.flock(h.fileno(), fcntl.LOCK_UN); h.close()

def harvest():
    """Return {pairAddress: pair} for the active Solana universe."""
    pairs = {}
    addrs = []
    for feed in ("token-boosts/latest/v1", "token-boosts/top/v1", "token-profiles/latest/v1"):
        d = _get(f"{API}/{feed}")
        if isinstance(d, list):
            addrs += [b.get("tokenAddress") for b in d
                      if b.get("chainId") == "solana" and b.get("tokenAddress")]
        time.sleep(0.25)
    addrs = list(dict.fromkeys(addrs))
    for a in addrs[:60]:
        d = _get(f"{API}/latest/dex/tokens/{a}")
        for p in (d or {}).get("pairs") or []:
            if p.get("chainId") == "solana" and p.get("pairAddress"):
                pairs[p["pairAddress"]] = p
        time.sleep(0.25)
    for q in QUERIES:
        d = _get(f"{API}/latest/dex/search?q={q}")
        for p in (d or {}).get("pairs") or []:
            if p.get("chainId") == "solana" and p.get("pairAddress"):
                pairs[p["pairAddress"]] = p
        time.sleep(0.25)
    return pairs

def usable(p):
    """Liquidity + age + ACTIVITY. Without the activity gate the search endpoint returns
    dead/bridge pools quoting billions in liquidity against ~1 txn/hour."""
    try:
        liq = float((p.get("liquidity") or {}).get("usd") or 0)
        if liq < MIN_LIQ_USD or liq > MAX_LIQ_USD:
            return False
        ts = p.get("pairCreatedAt")
        if not ts or (time.time() * 1000 - float(ts)) < MIN_AGE_MS:
            return False
        if float((p.get("volume") or {}).get("h24") or 0) < MIN_VOL24_USD:
            return False
        t24 = (p.get("txns") or {}).get("h24") or {}
        if int(t24.get("buys") or 0) + int(t24.get("sells") or 0) < MIN_TXNS24:
            return False
        # garbage guard: brand-new/broken pools quote absurd priceChange (+507154%)
        ch = p.get("priceChange") or {}
        for w in ("m5", "h1", "h6", "h24"):
            try:
                if ch.get(w) is not None and abs(float(ch[w])) > 5000.0:
                    return False
            except Exception:
                return False
        return bool(p.get("priceUsd"))
    except Exception:
        return False

def row(p, now_ms):
    t = p.get("txns") or {}; v = p.get("volume") or {}; c = p.get("priceChange") or {}
    def tx(w):
        d = t.get(w) or {}
        return int(d.get("buys") or 0), int(d.get("sells") or 0)
    return {
        "ts_ms": now_ms,
        "pair": p.get("pairAddress"),
        "mint": (p.get("baseToken") or {}).get("address"),
        "sym": (p.get("baseToken") or {}).get("symbol"),
        "dex": p.get("dexId"),
        "price_usd": float(p.get("priceUsd") or 0) or None,
        "liq_usd": float((p.get("liquidity") or {}).get("usd") or 0),
        "mcap": p.get("marketCap"), "fdv": p.get("fdv"),
        "created_ms": p.get("pairCreatedAt"),
        "buys": {w: tx(w)[0] for w in ("m5", "h1", "h6", "h24")},
        "sells": {w: tx(w)[1] for w in ("m5", "h1", "h6", "h24")},
        "vol": {w: v.get(w) for w in ("m5", "h1", "h6", "h24")},
        "chg": {w: c.get(w) for w in ("m5", "h1", "h6", "h24")},
    }

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if SEEN.exists():
        try: seen = set(json.loads(SEEN.read_text()))
        except Exception: seen = set()
    with single_writer():
        while True:
            t0 = time.time(); now_ms = int(t0 * 1000)
            try:
                pairs = harvest()
                rows = [row(p, now_ms) for p in pairs.values() if usable(p)]
                cur = {r["pair"] for r in rows}
                # kill-risk 3: record pairs that VANISHED, so survivorship is measurable
                gone = sorted(seen - cur)
                seen = (seen | cur)
                with OUT.open("a") as f:
                    for r in rows:
                        f.write(json.dumps(r, separators=(",", ":")) + "\n")
                    f.write(json.dumps({"ts_ms": now_ms, "_meta": "cycle",
                                        "n": len(rows), "n_raw": len(pairs),
                                        "vanished": gone[:200]}, separators=(",", ":")) + "\n")
                SEEN.write_text(json.dumps(sorted(seen)))
                print(f"[{time.strftime('%H:%M:%S')}] {len(rows)} usable / {len(pairs)} raw, "
                      f"{len(gone)} vanished", flush=True)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] cycle error: {e}", flush=True)
            time.sleep(max(5.0, CADENCE_S - (time.time() - t0)))

if __name__ == "__main__":
    main()
