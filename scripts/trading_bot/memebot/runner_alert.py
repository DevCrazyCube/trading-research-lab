"""Continuous early-coin scanner with Telegram alerts.

Alerts on coins that PASS the factory screen while still small -- it does NOT alert on
things that are pumping (measured: a visible run means past peak, -96.42% at 6h).

Screen built from 2026-09-04 measurements:
  REJECT mcap/ath >= 0.90            at/near ATH is reproducibly negative
  REJECT liquidity/mcap < 2.0%       factory runs 0.12-0.39%, organic graduates 4.7-6.1%
  REJECT h1 buys:sells > 5:1         organic tape is 1.0-1.5:1; factory prints 23:1, 56:1, 110:1
  REJECT liquidity < $15k            must be exitable
  REJECT duplicate ticker seen from a different creator (factory signature)
NO PREDICTIVE CLAIM. This is a defensive screen plus a size/age filter. New file: no arena closure.
"""
from __future__ import annotations
import contextlib, fcntl, json, sys, time, urllib.request, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.operator_notify import load_env, send, NotifyRefused

STATE = ROOT / "research" / "midcap" / "runner_alert_state.json"
LOG = ROOT / "research" / "midcap" / "runner_alerts.jsonl"
LOCK = ROOT / "research" / "midcap" / ".runner_alert.lock"
PF = "https://frontend-api-v3.pump.fun/coins"
DS = "https://api.dexscreener.com/latest/dex/tokens"

MAX_MCAP = 1_000_000.0
PREF_MCAP = 500_000.0
MIN_MCAP = 30_000.0
MAX_AGE_H = 24.0
MAX_PCT_ATH = 0.90
MIN_LIQ_RATIO = 0.020
MIN_LIQ_USD = 15_000.0
MAX_BS_RATIO = 5.0
CADENCE_S = 60
MAX_ALERTS_PER_HOUR = 6

def _get(u, t=20):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=t) as x: return json.loads(x.read())
    except Exception: return None

@contextlib.contextmanager
def single_writer():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    h = LOCK.open("w")
    try: fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: raise SystemExit(f"REFUSED: another runner_alert holds {LOCK}")
    try: yield
    finally: fcntl.flock(h.fileno(), fcntl.LOCK_UN); h.close()

def universe():
    out = {}
    for sort in ("created_timestamp", "last_trade_timestamp", "market_cap"):
        for i in range(6):
            b = _get(f"{PF}?offset={i*50}&limit=50&sort={sort}&order=DESC&includeNsfw=true")
            b = b if isinstance(b, list) else (b or {}).get("coins") or []
            if not b: break
            for c in b:
                if c.get("mint") and c.get("usd_market_cap"): out[c["mint"]] = c
            time.sleep(0.2)
    return out

def market(mint):
    d = _get(f"{DS}/{mint}")
    ps = [p for p in ((d or {}).get("pairs") or []) if p.get("chainId") == "solana"]
    if not ps: return None
    liq = sum(float((p.get("liquidity") or {}).get("usd") or 0) for p in ps)
    t = collections.Counter()
    for p in ps:
        for w in ("h1", "h6"):
            d2 = (p.get("txns") or {}).get(w) or {}
            t[w + "b"] += int(d2.get("buys") or 0); t[w + "s"] += int(d2.get("sells") or 0)
    best = max(ps, key=lambda q: float((q.get("liquidity") or {}).get("usd") or 0))
    return {"liq": liq, "b1": t["h1b"], "s1": t["h1s"], "b6": t["h6b"], "s6": t["h6s"],
            "chg": (best.get("priceChange") or {}), "url": best.get("url")}

def screen(c, mk, tickers, now):
    """Return (ok, reasons_failed)."""
    f = []
    mc = float(c.get("usd_market_cap") or 0); ath = float(c.get("ath_market_cap") or 0)
    age = (now - float(c.get("created_timestamp") or now)) / 3.6e6
    if not (MIN_MCAP <= mc <= MAX_MCAP): f.append(f"mcap ${mc:,.0f}")
    if age > MAX_AGE_H: f.append(f"age {age:.1f}h")
    if ath and mc / ath >= MAX_PCT_ATH: f.append(f"{mc/ath*100:.0f}% of ATH")
    if not mk: return False, ["no market data"]
    if mk["liq"] < MIN_LIQ_USD: f.append(f"liq ${mk['liq']:,.0f}")
    if mc > 0 and mk["liq"] / mc < MIN_LIQ_RATIO: f.append(f"liq/mcap {mk['liq']/mc*100:.2f}%")
    if mk["s1"] > 0 and mk["b1"] / max(1, mk["s1"]) > MAX_BS_RATIO:
        f.append(f"buys:sells {mk['b1']}/{mk['s1']}")
    sym = (c.get("symbol") or "").upper()
    if sym and sym in tickers and c.get("creator") not in tickers[sym]:
        f.append(f"dup ticker {sym}")
    return (not f), f

def main():
    load_env()
    seen = set(); alerts = []
    if STATE.exists():
        try: seen = set(json.loads(STATE.read_text()).get("seen", []))
        except Exception: pass
    tickers = collections.defaultdict(set)
    with single_writer():
        print(f"runner_alert up. {len(seen)} mints already alerted.", flush=True)
        try:
            send("[scanner] runner_alert online. Screening for coins under $1M mcap that PASS the "
                 "factory screen (liq/mcap>=2%, not at ATH, organic flow). No predictive claim.")
        except NotifyRefused as e:
            print(f"telegram refused: {e}", flush=True)
        while True:
            t0 = time.time(); now = int(t0 * 1000); nscan = npass = 0
            try:
                uni = universe()
                for m, c in uni.items():
                    s = (c.get("symbol") or "").upper()
                    if s: tickers[s].add(c.get("creator"))
                cands = [c for c in uni.values()
                         if MIN_MCAP <= float(c.get("usd_market_cap") or 0) <= MAX_MCAP
                         and c.get("mint") not in seen
                         and (now - float(c.get("created_timestamp") or now))/3.6e6 <= MAX_AGE_H]
                cands.sort(key=lambda c: float(c["usd_market_cap"]))
                for c in cands[:25]:
                    nscan += 1
                    mk = market(c["mint"]); time.sleep(0.25)
                    ok, why = screen(c, mk, tickers, now)
                    if not ok: continue
                    npass += 1
                    mc = float(c["usd_market_cap"]); age = (now-float(c["created_timestamp"]))/3.6e6
                    ath = float(c.get("ath_market_cap") or 0)
                    alerts = [a for a in alerts if t0-a < 3600]
                    if len(alerts) >= MAX_ALERTS_PER_HOUR: continue
                    tier = "*** UNDER 500K ***" if mc < PREF_MCAP else "under 1M"
                    msg = (f"[{tier}] {c.get('symbol')} — {c.get('name')}\n"
                           f"mcap ${mc:,.0f}  |  liq ${mk['liq']:,.0f} ({mk['liq']/mc*100:.1f}% of mcap)\n"
                           f"age {age:.1f}h  |  {mc/ath*100:.0f}% of ATH\n"
                           f"h1 buys/sells {mk['b1']}/{mk['s1']}  h6 {mk['b6']}/{mk['s6']}\n"
                           f"chg m5 {mk['chg'].get('m5')}% h1 {mk['chg'].get('h1')}% h6 {mk['chg'].get('h6')}%\n"
                           f"mint: {c['mint']}\n{mk.get('url') or ''}\n"
                           f"PASSED the factory screen. NOT a prediction — no validated edge exists.")
                    try:
                        send(msg); alerts.append(t0)
                        print(f"  ALERT {c.get('symbol')} ${mc:,.0f}", flush=True)
                    except NotifyRefused as e:
                        print(f"  refused: {e}", flush=True)
                    seen.add(c["mint"])
                    with LOG.open("a") as fh:
                        fh.write(json.dumps({"ts": now, "mint": c["mint"], "sym": c.get("symbol"),
                                             "mcap": mc, "liq": mk["liq"], "age_h": age,
                                             "pct_ath": (mc/ath if ath else None),
                                             "b1": mk["b1"], "s1": mk["s1"]}, separators=(",", ":"))+"\n")
                STATE.write_text(json.dumps({"seen": sorted(seen)}))
                print(f"[{time.strftime('%H:%M:%S')}] universe={len(uni)} cands={len(cands)} "
                      f"deep-scanned={nscan} passed={npass} alerted_1h={len(alerts)}", flush=True)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] cycle error: {e}", flush=True)
            time.sleep(max(5.0, CADENCE_S - (time.time()-t0)))

if __name__ == "__main__":
    main()
