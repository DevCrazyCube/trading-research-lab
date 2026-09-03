"""Did momentum-buying graduated pump.fun coins make money? Survivorship-free.

Universe: every complete=1 mint in the b11a chain-enumerated window, INCLUDING the ones
that pumped and died. Minute OHLCV from GeckoTerminal.

Tests the owner's actual strategy: see a coin running, buy it, hold, sell.
Charged the repo's measured 3% memecoin round trip. Entry at the NEXT bar's open after
the signal bar closes -- never the signal bar itself (that would be lookahead).
"""
from __future__ import annotations
import json, math, random, sqlite3, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "research" / "midcap" / "grad_ohlcv.sqlite"
TOLL = 0.030

def load():
    c = sqlite3.connect(DB)
    out = {}
    for mint, bj in c.execute("select mint,bars_json from ohlcv where n_bars>0"):
        try: b = json.loads(bj)
        except Exception: continue
        b = sorted(b, key=lambda x: x[0])
        b = [x for x in b if x[1] and x[4] and x[1] > 0 and x[4] > 0]
        if len(b) >= 30: out[mint] = b
    return out

def trades(bars, lookback, thresh, hold):
    """Signal on bar i (closed), enter at open of bar i+1, exit at close of i+1+hold."""
    o = []
    for i in range(lookback, len(bars) - hold - 1):
        p_then, p_now = bars[i - lookback][4], bars[i][4]
        if p_then <= 0: continue
        if (p_now / p_then - 1) < thresh: continue
        entry = bars[i + 1][1]                      # next bar OPEN -- no lookahead
        exit_ = bars[min(i + 1 + hold, len(bars) - 1)][4]
        if entry <= 0 or exit_ <= 0: continue
        o.append(math.log(exit_ / entry))
    return o

def summarize(rets, label):
    if len(rets) < 50:
        print(f"  {label:<34} n={len(rets)} too few"); return
    gross = st.mean(rets); net = gross - TOLL
    med = st.median(rets)
    win = sum(1 for r in rets if r > TOLL) / len(rets)
    random.seed(20260903)
    boot = sorted(st.mean(random.choices(rets, k=len(rets))) for _ in range(2000))
    lo, hi = (boot[50] - TOLL) * 100, (boot[-50] - TOLL) * 100
    print(f"  {label:<34} n={len(rets):6d}  gross {gross*100:+7.2f}%  NET {net*100:+7.2f}%  "
          f"CI[{lo:+.2f},{hi:+.2f}]  med {med*100:+6.2f}%  win>toll {win:5.1%}")

def main():
    data = load()
    if len(data) < 20:
        print(f"only {len(data)} coins with bars -- crawl still running"); return
    tot = sum(len(v) for v in data.values())
    print(f"SURVIVORSHIP-FREE graduate cohort: {len(data)} coins, {tot:,} minute bars\n")
    # Baseline: buy at first bar, hold to last (what "buying every graduate" does)
    bh = []
    for b in data.values():
        if b[0][1] > 0 and b[-1][4] > 0: bh.append(math.log(b[-1][4] / b[0][1]))
    if bh:
        print(f"  BASELINE buy-and-hold every graduate: n={len(bh)}  "
              f"mean {st.mean(bh)*100:+.1f}%  MEDIAN {st.median(bh)*100:+.1f}%  "
              f"frac>0 {sum(1 for x in bh if x>0)/len(bh):.0%}")
        print(f"    (log-returns; mean is tail-carried, median is the typical coin)\n")
    print("  MOMENTUM ENTRY -- signal bar closes, enter NEXT bar's open, hold H minutes:")
    for lb, th in ((5, 0.20), (5, 0.50), (15, 0.30), (15, 1.00), (30, 0.50), (60, 1.00)):
        for hold in (5, 15, 60):
            r = trades_all(data, lb, th, hold)
            summarize(r, f"up>{th:.0%} in {lb}m, hold {hold}m")
        print()

def trades_all(data, lb, th, hold):
    o = []
    for b in data.values(): o += trades(b, lb, th, hold)
    return o

if __name__ == "__main__":
    main()
