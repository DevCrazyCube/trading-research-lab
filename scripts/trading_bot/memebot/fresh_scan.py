"""Fresh Solana memecoin collector -- the ACTUAL trending universe.

Supersedes midcap_scan.py, whose DexScreener name-search enumerator returned only
old established tokens (BONK/DOGE/PEPE) and could never surface an hours-old mover.
Enumerates pump.fun directly, which is where the trending tab's coins live.

Collection only; computes no verdict. New file: touches no arena closure member.
"""
from __future__ import annotations
import contextlib, fcntl, json, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "midcap" / "fresh_snapshots.jsonl"
LOCK = ROOT / "research" / "midcap" / ".fresh.lock"
SEEN = ROOT / "research" / "midcap" / "fresh_seen.json"

API = "https://frontend-api-v3.pump.fun/coins"
MAX_AGE_H = 72.0
MIN_MCAP_USD = 100_000.0
CADENCE_S = 180
PAGES_MCAP = 24          # offset 0..1150 by market cap
PAGES_RECENT = 10        # offset 0..450 by last trade

def _get(url, timeout=20.0):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d if isinstance(d, list) else (d.get("coins") or [])
    except Exception:
        return []

@contextlib.contextmanager
def single_writer():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    h = LOCK.open("w")
    try:
        fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(f"REFUSED: another fresh collector holds {LOCK}")
    try:
        yield
    finally:
        fcntl.flock(h.fileno(), fcntl.LOCK_UN); h.close()

def harvest():
    coins = {}
    for sort, pages in (("market_cap", PAGES_MCAP), ("last_trade_timestamp", PAGES_RECENT)):
        for i in range(pages):
            batch = _get(f"{API}?offset={i*50}&limit=50&sort={sort}"
                         f"&order=DESC&includeNsfw=true")
            if not batch:
                break
            for c in batch:
                if c.get("mint"):
                    coins[c["mint"]] = c
            time.sleep(0.2)
    return coins

def usable(c, now_ms):
    try:
        ct = c.get("created_timestamp")
        if not ct:
            return False
        if (now_ms - float(ct)) / 3_600_000.0 > MAX_AGE_H:
            return False
        return float(c.get("usd_market_cap") or 0) >= MIN_MCAP_USD
    except Exception:
        return False

def row(c, now_ms):
    def f(k):
        v = c.get(k)
        try: return float(v) if v is not None else None
        except Exception: return None
    return {
        "ts_ms": now_ms, "mint": c.get("mint"), "sym": c.get("symbol"),
        "name": c.get("name"),
        "mcap": f("usd_market_cap"), "ath": f("ath_market_cap"),
        "ath_ts": c.get("ath_market_cap_timestamp"),
        "created_ms": c.get("created_timestamp"),
        "last_trade_ms": c.get("last_trade_timestamp"),
        "complete": bool(c.get("complete")), "live": bool(c.get("is_currently_live")),
        "replies": c.get("reply_count"), "creator": c.get("creator"),
        "vsol": f("virtual_sol_reserves"), "rsol": f("real_sol_reserves"),
        "vtok": f("virtual_token_reserves"), "rtok": f("real_token_reserves"),
        "has_x": bool(c.get("twitter")), "has_tg": bool(c.get("telegram")),
        "has_web": bool(c.get("website")), "pool": c.get("pump_swap_pool"),
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
                coins = harvest()
                rows = [row(c, now_ms) for c in coins.values() if usable(c, now_ms)]
                cur = {r["mint"] for r in rows}
                gone = sorted(seen - cur); seen |= cur
                with OUT.open("a") as fh:
                    for r in rows:
                        fh.write(json.dumps(r, separators=(",", ":")) + "\n")
                    fh.write(json.dumps({"ts_ms": now_ms, "_meta": "cycle", "n": len(rows),
                                         "n_raw": len(coins), "vanished": gone[:300]},
                                        separators=(",", ":")) + "\n")
                SEEN.write_text(json.dumps(sorted(seen)))
                ages = sorted((now_ms - float(r["created_ms"])) / 3.6e6 for r in rows if r["created_ms"])
                med = ages[len(ages)//2] if ages else -1
                print(f"[{time.strftime('%H:%M:%S')}] {len(rows)} fresh / {len(coins)} raw, "
                      f"median age {med:.1f}h, {len(gone)} vanished", flush=True)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] cycle error: {e}", flush=True)
            time.sleep(max(5.0, CADENCE_S - (time.time() - t0)))

if __name__ == "__main__":
    main()
