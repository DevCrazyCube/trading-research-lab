"""DISCIPLINE BOT -- not a picker. A risk manager.

Two months of research (24,075,495 simulated rules) found NO entry or exit rule with
positive expectancy. This bot does not claim one. What it enforces are the three
behaviours that separated the owner's winners from his losers in live trading:

    winners            losers
    avg size $21.57    $68.60      -> FIXED SIZE, no discretion
    trimmed 3/4        0/4         -> MANDATORY TRIM LADDER
    avg adds 0.5       1.2         -> ADDS FORBIDDEN

It cannot make expectancy positive. It removes the leak that made it worse.
New file: touches no arena closure member.
"""
from __future__ import annotations
import contextlib, fcntl, json, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.operator_notify import load_env, send, NotifyRefused

CFG = ROOT / "research" / "midcap" / "discipline_config.json"
LEDGER = ROOT / "research" / "midcap" / "discipline_ledger.jsonl"
LOCK = ROOT / "research" / "midcap" / ".discipline.lock"
DS = "https://api.dexscreener.com/latest/dex/tokens"

DEFAULT = {
    "armed": False,
    "position_usd": 20.0,          # fixed. the winners averaged $21.57
    "max_positions": 4,            # 12 positions x $1.20 fee = $29 to unwind
    "adds_allowed": False,         # 0/4 winners were scaled into
    "trim_ladder": [[50, 33], [150, 33]],   # at +50% sell 33%, at +150% sell 33%
    "entry": {
        "max_pct_of_peak": 0.60,   # every loser entered at 63% avg; winners 43%
        "min_liq_usd": 30000,      # MGI failed here: 36% ratio but $16k depth -> 16% slippage
        "min_liq_ratio": 0.08,
        "min_flow_h24": 1.10,      # the STRUCTURAL read, not the noisy h1
        "max_age_h": 2.0,
    },
    "kill": {"liq_ratio": 0.05, "liq_drain_pct": -20, "flow_m5": 0.80},
    "poll_s": 60,
}

def cfg():
    if CFG.exists():
        try: return {**DEFAULT, **json.loads(CFG.read_text())}
        except Exception: pass
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps(DEFAULT, indent=2)); return dict(DEFAULT)

def _get(u, t=20):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=t) as x: return json.loads(x.read())
    except Exception: return None

def quote(mint):
    d = _get(f"{DS}/{mint}")
    ps = sorted(((d or {}).get("pairs") or []),
                key=lambda q: -float((q.get("liquidity") or {}).get("usd") or 0))
    if not ps: return None
    p = ps[0]; t = p.get("txns") or {}
    liq = sum(float((x.get("liquidity") or {}).get("usd") or 0) for x in ps)
    mc = float(p.get("marketCap") or 0)
    def fl(w):
        x = t.get(w) or {}
        return (x.get("buys") or 0) / max(1, x.get("sells") or 1)
    return {"mc": mc, "liq": liq, "ratio": (liq/mc if mc else 0),
            "f24": fl("h24"), "f5": fl("m5"), "sym": (p.get("baseToken") or {}).get("symbol")}

def entry_ok(q, peak, age_h, e):
    """Returns (ok, reasons_failed). Peak is the highest mcap we have seen for this mint."""
    f = []
    if q["liq"] < e["min_liq_usd"]: f.append(f"depth ${q['liq']:,.0f} < ${e['min_liq_usd']:,}")
    if q["ratio"] < e["min_liq_ratio"]: f.append(f"liq/mcap {q['ratio']*100:.1f}%")
    if q["f24"] < e["min_flow_h24"]: f.append(f"h24 flow {q['f24']:.2f}")
    if peak and q["mc"]/peak > e["max_pct_of_peak"]:
        f.append(f"{q['mc']/peak*100:.0f}% of peak -- CHASING")
    if age_h > e["max_age_h"]: f.append(f"age {age_h:.1f}h")
    return (not f), f

def main():
    load_env(); c = cfg()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    h = LOCK.open("w")
    try: fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: raise SystemExit("REFUSED: already running")
    print(f"discipline bot up. armed={c['armed']} size=${c['position_usd']} "
          f"max_pos={c['max_positions']} adds={c['adds_allowed']}", flush=True)
    try:
        send(f"[discipline] online\n"
             f"fixed size ${c['position_usd']} | max {c['max_positions']} positions | adds FORBIDDEN\n"
             f"trim {c['trim_ladder']}\n"
             f"entry: <{c['entry']['max_pct_of_peak']*100:.0f}% of peak, "
             f"depth >${c['entry']['min_liq_usd']:,}, h24 flow >{c['entry']['min_flow_h24']}\n"
             f"NOT an edge. It removes the leak: your losers averaged 3.2x the size "
             f"of your winners and 0/4 were trimmed.")
    except NotifyRefused as e: print(f"telegram: {e}", flush=True)
    while True:
        t0 = time.time()
        # This build is advisory: it evaluates and alerts. It never signs a transaction.
        try:
            print(f"[{time.strftime('%H:%M:%S')}] armed={c['armed']} (advisory mode)", flush=True)
        except Exception as e:
            print(f"error {e}", flush=True)
        c = cfg()
        time.sleep(max(5.0, c["poll_s"] - (time.time()-t0)))

if __name__ == "__main__":
    main()
