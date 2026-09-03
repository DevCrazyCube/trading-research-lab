"""SCALPBOT -- a real memecoin trading bot. Paper mode until a rule is validated.

Honest by construction:
  * entry price is the NEXT price observed after the signal, never the signal's own price
  * toll charged on every completed round trip, including every stop-out
  * append-only trade ledger; positions and cash reconstructable from it alone
  * no rule is hardcoded -- rules live in scalpbot_config.json so a validated spec drops straight in

Runs against the live pump.fun universe. New file: touches no arena closure member.
"""
from __future__ import annotations
import contextlib, fcntl, json, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CFG = ROOT / "research" / "midcap" / "scalpbot_config.json"
LEDGER = ROOT / "research" / "midcap" / "scalpbot_ledger.jsonl"
LOCK = ROOT / "research" / "midcap" / ".scalpbot.lock"
API = "https://frontend-api-v3.pump.fun/coins"

DEFAULT_CFG = {
    "mode": "paper",
    "armed": False,               # master switch; nothing trades until a rule is VALIDATED
    "bankroll_usd": 63.0,
    "position_usd": 5.0,
    "max_open": 5,
    "toll_pct": 3.0,
    "poll_s": 45,
    "entry": {
        "min_age_h": 0.0, "max_age_h": 6.0,
        "min_mcap": 300000.0, "max_mcap": 10000000.0,
        "max_pct_of_ath": 0.80,      # measured: buying at/near ATH was the WORST arm
        "min_gain_15m_pct": None,    # set by a validated spec
    },
    "exit": {"stop_pct": -20.0, "target_pct": 30.0, "max_hold_min": 30},
    "_note": "armed=false means observe-and-log only. A validated spec flips it, nothing else.",
}

def cfg():
    if CFG.exists():
        try: return {**DEFAULT_CFG, **json.loads(CFG.read_text())}
        except Exception: pass
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps(DEFAULT_CFG, indent=2))
    return dict(DEFAULT_CFG)

@contextlib.contextmanager
def single_writer():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    h = LOCK.open("w")
    try: fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: raise SystemExit(f"REFUSED: another scalpbot holds {LOCK}")
    try: yield
    finally: fcntl.flock(h.fileno(), fcntl.LOCK_UN); h.close()

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        return d if isinstance(d, list) else (d.get("coins") or [])
    except Exception:
        return []

def universe():
    out = {}
    for sort, pages in (("market_cap", 12), ("last_trade_timestamp", 8)):
        for i in range(pages):
            b = _get(f"{API}?offset={i*50}&limit=50&sort={sort}&order=DESC&includeNsfw=true")
            if not b: break
            for c in b:
                if c.get("mint") and c.get("usd_market_cap"):
                    out[c["mint"]] = c
            time.sleep(0.2)
    return out

def emit(rec):
    with LEDGER.open("a") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")

def replay():
    """Rebuild open positions + realised pnl from the ledger alone."""
    open_, realised, ntr = {}, 0.0, 0
    if not LEDGER.exists(): return open_, realised, ntr
    with LEDGER.open() as f:
        for line in f:
            try: r = json.loads(line)
            except Exception: continue
            if r.get("ev") == "OPEN": open_[r["mint"]] = r
            elif r.get("ev") == "CLOSE":
                open_.pop(r["mint"], None); realised += r.get("pnl_usd", 0.0); ntr += 1
    return open_, realised, ntr

def mom_5m(hist, mint, now_ms, lo_s=240, hi_s=420):
    """5-minute return from the bot's own poll history. Returns None if no usable ref point."""
    h = hist.get(mint) or []
    ref = None
    for ts, mc in reversed(h):
        age = (now_ms - ts) / 1000.0
        if lo_s <= age <= hi_s:
            ref = mc; break
    if not ref or ref <= 0 or not h: return None
    return h[-1][1] / ref - 1


def entry_ok(c, e, now_ms, hist=None, mint=None):
    try:
        mc = float(c.get("usd_market_cap") or 0); ath = float(c.get("ath_market_cap") or 0)
        ct = float(c.get("created_timestamp") or 0)
        if not (mc and ct): return False
        age_h = (now_ms - ct) / 3.6e6
        if not (e["min_age_h"] <= age_h <= e["max_age_h"]): return False
        if not (e["min_mcap"] <= mc <= e["max_mcap"]): return False
        if ath and e.get("max_pct_of_ath") and mc / ath > e["max_pct_of_ath"]: return False
        if e.get("require_graduated") and not c.get("complete"): return False
        if e.get("min_liq_sol") is not None:
            try: rs = float(c.get("real_sol_reserves") or 0) / 1e9
            except Exception: rs = 0.0
            if not c.get("complete") and rs < e["min_liq_sol"]: return False
        lo, hi = e.get("mom5m_lo"), e.get("mom5m_hi")
        if lo is not None or hi is not None:
            r = mom_5m(hist or {}, mint, now_ms)
            if r is None: return False
            if lo is not None and r < lo: return False
            if hi is not None and r >= hi: return False
        return True
    except Exception:
        return False

def main():
    c = cfg()
    with single_writer():
        emit({"ev": "BOOT", "ts": int(time.time()*1000), "cfg": c})
        print(f"scalpbot up. mode={c['mode']} armed={c['armed']} "
              f"pos=${c['position_usd']} max_open={c['max_open']}", flush=True)
        pending = {}
        hist = {}
        while True:
            t0 = time.time(); now = int(t0 * 1000)
            try:
                uni = universe()
                for _m, _c in uni.items():
                    try: _mc = float(_c.get("usd_market_cap") or 0)
                    except Exception: continue
                    if _mc > 0:
                        hist.setdefault(_m, []).append((now, _mc))
                        if len(hist[_m]) > 40: hist[_m] = hist[_m][-40:]
                open_, realised, ntr = replay()
                # --- exits first ---
                for mint, pos in list(open_.items()):
                    cur = uni.get(mint)
                    if not cur or not cur.get("usd_market_cap"): continue
                    px = float(cur["usd_market_cap"])
                    ret = (px / pos["entry_mcap"] - 1) * 100
                    held = (now - pos["ts"]) / 60000
                    why = ("stop" if ret <= c["exit"]["stop_pct"] else
                           "target" if ret >= c["exit"]["target_pct"] else
                           "maxhold" if held >= c["exit"]["max_hold_min"] else None)
                    if why:
                        net = ret - c["toll_pct"]
                        emit({"ev": "CLOSE", "ts": now, "mint": mint, "sym": pos.get("sym"),
                              "exit_mcap": px, "ret_pct": ret, "net_pct": net, "why": why,
                              "held_min": held, "pnl_usd": c["position_usd"] * net / 100})
                        print(f"  CLOSE {pos.get('sym')} {why} {net:+.1f}% "
                              f"(${c['position_usd']*net/100:+.2f})", flush=True)
                # --- entries: signal now, fill on the NEXT observation ---
                open_, realised, ntr = replay()
                for mint, pos in list(pending.items()):
                    cur = uni.get(mint)
                    if not cur: pending.pop(mint, None); continue
                    if len(open_) >= c["max_open"] or mint in open_:
                        pending.pop(mint, None); continue
                    if c["armed"]:
                        emit({"ev": "OPEN", "ts": now, "mint": mint, "sym": cur.get("symbol"),
                              "entry_mcap": float(cur["usd_market_cap"]),
                              "size_usd": c["position_usd"], "signal_ts": pos["ts"]})
                        print(f"  OPEN  {cur.get('symbol')} @ ${float(cur['usd_market_cap']):,.0f}", flush=True)
                    pending.pop(mint, None)
                open_, realised, ntr = replay()   # re-read AFTER fills so the display is not stale
                cands = [m for m, x in uni.items()
                         if entry_ok(x, c["entry"], now, hist, m)
                         and m not in open_ and m not in pending]
                for m in cands[: max(0, c["max_open"] - len(open_))]:
                    pending[m] = {"ts": now}
                unreal = 0.0
                for mint, pos in open_.items():
                    cur = uni.get(mint)
                    if cur and cur.get("usd_market_cap"):
                        unreal += c["position_usd"] * (
                            float(cur["usd_market_cap"]) / pos["entry_mcap"] - 1)
                print(f"[{time.strftime('%H:%M:%S')}] universe={len(uni)} cand={len(cands)} "
                      f"pending={len(pending)} OPEN={len(open_)} closed={ntr} "
                      f"realised=${realised:+.2f} unreal=${unreal:+.2f} armed={c['armed']}",
                      flush=True)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] cycle error: {e}", flush=True)
            c = cfg()      # hot-reload so arming does not need a restart
            time.sleep(max(5.0, c["poll_s"] - (time.time() - t0)))

if __name__ == "__main__":
    main()
