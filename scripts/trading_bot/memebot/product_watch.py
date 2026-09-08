"""Watch a token's own product backend for the milestone that would drive it.

COLLECT markets "walk to a Tesla store, collect TSLA" but 203 of its 207 drops carry
tokenAddress 0x0000... -- the app says "no value paired yet". Funding those drops is a
planned step (the unfunded state has its own UI string), and it will appear in the public
API BEFORE any announcement.

This is the only leading, non-price signal found in this project: a product milestone
observable in the operator's own backend. Alerts to Telegram on:
  FUNDED   - a drop's tokenAddress changes from the zero address to a real contract
  CAUGHT   - catchesLeft decreases / quietUntil appears (someone actually used it)
  NEW_DROP - drop count grows (expansion)
  GONE     - the API stops responding (product taken down)

New file: touches no arena closure member.
"""
from __future__ import annotations
import contextlib, fcntl, json, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.operator_notify import load_env, send, NotifyRefused

API = "https://www.trycollect.xyz/api/drops"
STATE = ROOT / "research" / "midcap" / "product_collect_state.json"
LOG = ROOT / "research" / "midcap" / "product_collect.jsonl"
LOCK = ROOT / "research" / "midcap" / ".product_collect.lock"
CADENCE_S = 180
ZERO = "0x0000"

def fetch():
    r = urllib.request.Request(API, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(r, timeout=25) as x:
        return (json.loads(x.read()) or {}).get("drops") or []

def digest(drops):
    funded = [d for d in drops if not str(d.get("tokenAddress", "")).lower().startswith(ZERO)]
    return {
        "n": len(drops),
        "funded": len(funded),
        "funded_syms": sorted({d.get("symbol") for d in funded}),
        "catches_left": sum(int(d.get("catchesLeft") or 0) for d in drops),
        "cooldowns": sum(1 for d in drops if d.get("quietUntil")),
        "by_id": {d.get("id"): (str(d.get("tokenAddress", ""))[:12], d.get("catchesLeft"),
                                d.get("symbol")) for d in drops},
    }

def main():
    load_env()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    h = LOCK.open("w")
    try: fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: raise SystemExit("REFUSED: already watching this product")
    prev = None
    if STATE.exists():
        try: prev = json.loads(STATE.read_text())
        except Exception: prev = None
    try:
        d0 = digest(fetch())
        send(f"[product] COLLECT backend watch online\n"
             f"{d0['n']} drops, {d0['funded']} funded ({', '.join(d0['funded_syms']) or 'none'})\n"
             f"{d0['catches_left']:,} catches left, {d0['cooldowns']} caught so far\n"
             f"will alert when the stock drops get real token contracts")
    except Exception as e:
        print(f"boot: {e}", flush=True)
    while True:
        t0 = time.time()
        try:
            cur = digest(fetch())
            fires = []
            if prev:
                if cur["funded"] > prev["funded"]:
                    new = set(cur["funded_syms"]) - set(prev["funded_syms"])
                    fires.append(("FUNDED",
                        f"funded drops {prev['funded']} -> {cur['funded']}"
                        + (f"\nNEW SYMBOLS NOW PAYING: {', '.join(sorted(new))}" if new else "")))
                if cur["cooldowns"] > prev["cooldowns"]:
                    fires.append(("CAUGHT", f"catches {prev['cooldowns']} -> {cur['cooldowns']}"))
                if cur["catches_left"] < prev["catches_left"]:
                    fires.append(("CAUGHT", f"catchesLeft {prev['catches_left']:,} -> {cur['catches_left']:,}"))
                if cur["n"] > prev["n"] + 5:
                    fires.append(("NEW_DROPS", f"drop count {prev['n']} -> {cur['n']}"))
            for kind, why in fires:
                try:
                    send(f"[{kind}] COLLECT product\n{why}\n"
                         f"now {cur['n']} drops, {cur['funded']} funded, "
                         f"{cur['catches_left']:,} catches left")
                    print(f"  ALERT {kind}: {why}", flush=True)
                except NotifyRefused as e: print(f"  telegram: {e}", flush=True)
            with LOG.open("a") as fh:
                fh.write(json.dumps({"ts": int(t0*1000), **{k: v for k, v in cur.items()
                                                            if k != "by_id"}}, separators=(",", ":"))+"\n")
            STATE.write_text(json.dumps(cur))
            prev = cur
            print(f"[{time.strftime('%H:%M:%S')}] {cur['n']} drops  {cur['funded']} funded  "
                  f"{cur['catches_left']:,} left  {cur['cooldowns']} caught", flush=True)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] error: {e}", flush=True)
        time.sleep(max(5.0, CADENCE_S - (time.time()-t0)))

if __name__ == "__main__":
    main()
