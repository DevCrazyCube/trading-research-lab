"""Single-coin watcher: price, liquidity, flow, and paid-attention status, with Telegram alerts.

Alerts on the thresholds established 2026-09-04, not on price alone:
  liq/mcap  -- the structural health metric. Real markets hold 5%+; the factory runs 0.12-0.39%.
  m5 flow   -- buys/sells. Parity at a local high is the distribution signature.
  drawdown  -- distance from the session high.
  liquidity -- absolute drain is the thing that precedes an unexitable move.
New file: touches no arena closure member.
"""
from __future__ import annotations
import contextlib, fcntl, json, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.operator_notify import load_env, send, NotifyRefused

DS = "https://api.dexscreener.com"
CADENCE_S = 90
ALERT_COOLDOWN_S = 1800

def _get(u, t=20):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=t) as x: return json.loads(x.read())
    except Exception: return None

def snap(addr):
    d = _get(f"{DS}/latest/dex/tokens/{addr}")
    ps = sorted(((d or {}).get("pairs") or []),
                key=lambda q: -float((q.get("liquidity") or {}).get("usd") or 0))
    if not ps: return None
    p = ps[0]; t = p.get("txns") or {}; v = p.get("volume") or {}; c = p.get("priceChange") or {}
    liq = sum(float((x.get("liquidity") or {}).get("usd") or 0) for x in ps)
    m5 = t.get("m5") or {}; h1 = t.get("h1") or {}
    mc = float(p.get("marketCap") or 0)
    return {"mc": mc, "liq": liq, "ratio": (liq/mc if mc else 0),
            "m5b": m5.get("buys") or 0, "m5s": m5.get("sells") or 0,
            "h1b": h1.get("buys") or 0, "h1s": h1.get("sells") or 0,
            "chg5": c.get("m5"), "chg1h": c.get("h1"), "vol5": v.get("m5") or 0,
            "pools": len(ps), "sym": (p.get("baseToken") or {}).get("symbol"),
            "quote": (p.get("quoteToken") or {}).get("symbol"), "url": p.get("url")}

def boosted(addr):
    """Paid attention = someone spending real dollars on visibility."""
    for feed in ("token-boosts/latest/v1", "token-boosts/top/v1", "token-profiles/latest/v1"):
        d = _get(f"{DS}/{feed}")
        if isinstance(d, list):
            for x in d:
                if (x.get("tokenAddress") or "").lower() == addr.lower():
                    return {"feed": feed, "amount": x.get("amount"), "total": x.get("totalAmount")}
        time.sleep(0.25)
    return None

def main(addr, label=""):
    load_env()
    lock = ROOT / "research" / "midcap" / f".watch_{addr[-8:]}.lock"
    log = ROOT / "research" / "midcap" / f"watch_{addr[-8:]}.jsonl"
    h = lock.open("w")
    try: fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: raise SystemExit("REFUSED: already watching this coin")
    peak = 0.0; low_mark = None; last_alert = {}; was_boosted = False
    s0 = snap(addr)
    if s0:
        peak = s0["mc"]
        try:
            send(f"[watch] {label or s0['sym']} online\n"
                 f"mcap ${s0['mc']:,.0f} | liq ${s0['liq']:,.0f} ({s0['ratio']*100:.1f}%)\n"
                 f"alerts: liq/mcap<5%, liq drain>20%, m5 flow<0.8, -25% from high, new high")
        except NotifyRefused as e: print(f"telegram: {e}", flush=True)
    prev_liq = s0["liq"] if s0 else 0
    while True:
        t0 = time.time()
        try:
            s = snap(addr)
            if s:
                if s["mc"] > peak: peak = s["mc"]
                if low_mark is None or s["mc"] < low_mark: low_mark = s["mc"]
                dd = (s["mc"]/peak - 1) if peak else 0
                f5 = s["m5b"]/max(1, s["m5s"])
                liqdrop = (s["liq"]/prev_liq - 1) if prev_liq else 0
                bs = boosted(addr)
                fires = []
                if s["ratio"] < 0.05: fires.append(("LIQ_RATIO", f"liq/mcap {s['ratio']*100:.2f}% (<5% = fragile)"))
                if liqdrop < -0.20: fires.append(("LIQ_DRAIN", f"liquidity {liqdrop*100:.0f}% to ${s['liq']:,.0f}"))
                if f5 < 0.80 and s["m5s"] > 30: fires.append(("FLOW", f"m5 buys/sells {s['m5b']}/{s['m5s']} = {f5:.2f}"))
                if dd < -0.25: fires.append(("DRAWDOWN", f"{dd*100:.0f}% from session high ${peak:,.0f}"))
                if s["mc"] >= peak and peak > 0 and s["mc"] > (s0 or {}).get("mc", 0) * 1.2:
                    fires.append(("NEW_HIGH", f"new session high ${s['mc']:,.0f}"))
                # recovery ladder -- ping only on real moves back up, so it can be left overnight
                for mult, tag in ((2.0, "2x"), (4.0, "4x"), (10.0, "10x")):
                    if low_mark and s["mc"] >= low_mark * mult:
                        fires.append((f"RECOVERY_{tag}",
                                      f"{tag} off the ${low_mark:,.0f} low -> ${s['mc']:,.0f}"))
                if s["mc"] >= 10_000_000:
                    fires.append(("TEN_MILLION", f"IT ACTUALLY HIT $10M -- ${s['mc']:,.0f}"))
                if bs and not was_boosted:
                    fires.append(("PAID_ATTENTION", f"appeared in {bs['feed'].split('/')[0]} amount={bs.get('amount')}"))
                was_boosted = bool(bs)
                for kind, why in fires:
                    if t0 - last_alert.get(kind, 0) < ALERT_COOLDOWN_S: continue
                    last_alert[kind] = t0
                    try:
                        send(f"[{kind}] {label or s['sym']}\n{why}\n"
                             f"mcap ${s['mc']:,.0f} ({s['mc']/peak*100:.0f}% of high)\n"
                             f"liq ${s['liq']:,.0f} ({s['ratio']*100:.1f}%)  pools {s['pools']}\n"
                             f"m5 {s['chg5']}% {s['m5b']}/{s['m5s']}  h1 {s['chg1h']}% {s['h1b']}/{s['h1s']}\n"
                             f"{s['url']}")
                        print(f"  ALERT {kind}: {why}", flush=True)
                    except NotifyRefused as e: print(f"  telegram: {e}", flush=True)
                with log.open("a") as fh:
                    fh.write(json.dumps({"ts": int(t0*1000), **s, "peak": peak,
                                         "boosted": bool(bs)}, separators=(",", ":"))+"\n")
                prev_liq = s["liq"]
                print(f"[{time.strftime('%H:%M:%S')}] ${s['mc']:>10,.0f} liq ${s['liq']:>9,.0f} "
                      f"({s['ratio']*100:5.2f}%) m5 {f5:.2f} dd {dd*100:+5.1f}% "
                      f"{'BOOSTED' if bs else ''}", flush=True)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] error: {e}", flush=True)
        time.sleep(max(5.0, CADENCE_S - (time.time()-t0)))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
