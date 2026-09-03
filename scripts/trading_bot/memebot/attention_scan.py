"""Exogenous paid-attention event collector.

The last untried information class: a third party spending REAL DOLLARS at a known
timestamp (DexScreener paid boosts / claimed profiles / pump.fun live streams). Every
one of the 248 hypotheses tested endogenous tape features; all inverted or vanished.

Collection only -- computes no verdict. Records each event's FIRST SIGHT plus a
time/mcap/age-matched CONTROL token, because without the control this measures
"boosted coins are coins that move", which is circular.

Governed by research/midcap/EXOGENOUS_ATTENTION_PREREGISTRATION.md (sha cf7e51c6).
New file: touches no arena closure member.
"""
from __future__ import annotations
import contextlib, fcntl, json, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "midcap" / "attention.jsonl"
LOCK = ROOT / "research" / "midcap" / ".attention.lock"
STATE = ROOT / "research" / "midcap" / "attention_seen.json"

DS = "https://api.dexscreener.com"
PF = "https://frontend-api-v3.pump.fun/coins"
CADENCE_S = 90
TRACK_S = 6 * 3600           # follow each event token for 6h
FEEDS = ("token-boosts/latest/v1", "token-boosts/top/v1", "token-profiles/latest/v1")

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None

@contextlib.contextmanager
def single_writer():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    h = LOCK.open("w")
    try: fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: raise SystemExit(f"REFUSED: another attention collector holds {LOCK}")
    try: yield
    finally: fcntl.flock(h.fileno(), fcntl.LOCK_UN); h.close()

def price_of(mint):
    """Best (deepest) pair for a mint -> price, liquidity, mcap, pair age."""
    d = _get(f"{DS}/latest/dex/tokens/{mint}")
    ps = [p for p in ((d or {}).get("pairs") or []) if p.get("chainId") == "solana"]
    if not ps: return None
    p = max(ps, key=lambda q: float((q.get("liquidity") or {}).get("usd") or 0))
    try: px = float(p.get("priceUsd") or 0)
    except Exception: px = 0.0
    if px <= 0: return None
    return {"px": px, "liq": float((p.get("liquidity") or {}).get("usd") or 0),
            "mcap": p.get("marketCap"), "created_ms": p.get("pairCreatedAt"),
            "sym": (p.get("baseToken") or {}).get("symbol")}

def universe():
    """Candidate pool for matched controls: fresh pump.fun coins with mcap."""
    out = {}
    for sort in ("market_cap", "last_trade_timestamp"):
        for i in range(6):
            b = _get(f"{PF}?offset={i*50}&limit=50&sort={sort}&order=DESC&includeNsfw=true")
            b = b if isinstance(b, list) else (b or {}).get("coins") or []
            if not b: break
            for c in b:
                if c.get("mint") and c.get("usd_market_cap") and c.get("created_timestamp"):
                    out[c["mint"]] = c
            time.sleep(0.2)
    return out

def match_control(ev_mcap, ev_age_h, uni, used):
    """Closest non-event token by log-mcap and age. This is the whole test."""
    import math
    best, bd = None, 1e18
    for m, c in uni.items():
        if m in used: continue
        try:
            mc = float(c["usd_market_cap"]); ag = (time.time()*1000 - float(c["created_timestamp"]))/3.6e6
            if mc <= 0: continue
            d = (math.log(mc) - math.log(max(1.0, ev_mcap)))**2 + ((ag - ev_age_h)/12.0)**2
        except Exception: continue
        if d < bd: bd, best = d, m
    return best

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen, tracking = set(), {}
    if STATE.exists():
        try:
            s = json.loads(STATE.read_text()); seen = set(s.get("seen", []))
            tracking = s.get("tracking", {})
        except Exception: pass
    with single_writer():
        print(f"attention collector up. {len(seen)} tokens already seen.", flush=True)
        while True:
            t0 = time.time(); now = int(t0 * 1000)
            try:
                fresh = []
                for feed in FEEDS:
                    d = _get(f"{DS}/{feed}")
                    for x in (d if isinstance(d, list) else [d] if d else []):
                        if x and x.get("chainId") == "solana" and x.get("tokenAddress"):
                            if x["tokenAddress"] not in seen:
                                fresh.append((x["tokenAddress"], feed, x.get("amount"),
                                              x.get("totalAmount")))
                    time.sleep(0.3)
                uni = universe() if fresh else {}
                for mint, feed, amt, tot in fresh:
                    seen.add(mint)
                    info = price_of(mint)
                    if not info: continue
                    age_h = ((now - float(info["created_ms"]))/3.6e6) if info.get("created_ms") else -1
                    ctrl = match_control(float(info.get("mcap") or 0), age_h, uni, seen)
                    cinfo = price_of(ctrl) if ctrl else None
                    rec = {"ev": "EVENT", "ts_ms": now, "mint": mint, "feed": feed,
                           "amount": amt, "total": tot, "sym": info.get("sym"),
                           "px": info["px"], "liq": info["liq"], "mcap": info.get("mcap"),
                           "created_ms": info.get("created_ms"), "age_h": age_h,
                           "control": ctrl, "control_px": (cinfo or {}).get("px"),
                           "control_mcap": (cinfo or {}).get("mcap")}
                    with OUT.open("a") as f: f.write(json.dumps(rec, separators=(",", ":"))+"\n")
                    tracking[mint] = {"t0": now, "ctrl": ctrl}
                    print(f"  EVENT {info.get('sym')} {feed.split('/')[0]} amt={amt} "
                          f"mcap=${(info.get('mcap') or 0):,.0f} ctrl={str(ctrl)[:8]}", flush=True)
                    time.sleep(0.3)
                # follow every tracked token (and its control) for TRACK_S
                for mint, meta in list(tracking.items()):
                    if (now - meta["t0"])/1000 > TRACK_S: tracking.pop(mint, None); continue
                    a = price_of(mint); time.sleep(0.25)
                    c = price_of(meta["ctrl"]) if meta.get("ctrl") else None
                    if c: time.sleep(0.25)
                    if a:
                        with OUT.open("a") as f:
                            f.write(json.dumps({"ev": "TICK", "ts_ms": now, "mint": mint,
                                "t0": meta["t0"], "px": a["px"], "liq": a["liq"],
                                "ctrl": meta.get("ctrl"),
                                "ctrl_px": (c or {}).get("px")}, separators=(",", ":"))+"\n")
                STATE.write_text(json.dumps({"seen": sorted(seen), "tracking": tracking}))
                print(f"[{time.strftime('%H:%M:%S')}] new={len(fresh)} tracking={len(tracking)} "
                      f"seen={len(seen)}", flush=True)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] cycle error: {e}", flush=True)
            time.sleep(max(5.0, CADENCE_S - (time.time() - t0)))

if __name__ == "__main__":
    main()
