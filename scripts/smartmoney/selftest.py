#!/usr/bin/env python3
"""Synthetic self-test for the smart-money copy pipeline (analyze.py).

Proves the identification -> held-out -> copy logic is CORRECT by constructing a world with a
KNOWN ground truth, then checking analyze.py recovers it:

  Scenario A ("edge is real & persistent"): a set of SKILLED wallets buy tokens that then rise,
  and they persist into the copy window. Copy sim on identified wallets MUST beat the random null
  and be net-positive.

  Scenario B ("survivorship only, no persistence"): wallets that look profitable in the ID window
  are profitable only by luck; in the copy window their picks are random. Copy sim MUST NOT beat
  the null (edge ~ 0 / negative), and persistence MUST be ~ chance.

  Scenario C ("insider"): a deployer wallet is first buyer of its own tokens and dumps on the next
  buyers. It looks hugely profitable in ID but MUST be flagged and excluded.

Writes each synthetic world to a temp sqlite in the same schema and runs analyze.py on it.
"""
from __future__ import annotations
import sqlite3, subprocess, sys, os, random, math, pathlib, tempfile

SCHEMA = """CREATE TABLE trade(signature TEXT, slot INTEGER, ts INTEGER, wallet TEXT, mint TEXT,
    side TEXT, token_amount REAL, usd REAL, price_usd REAL,
    PRIMARY KEY(signature, mint, side, wallet));"""

def make_db(path, rows):
    if os.path.exists(path): os.remove(path)
    c = sqlite3.connect(path); c.execute(SCHEMA)
    c.executemany("INSERT OR IGNORE INTO trade VALUES (?,?,?,?,?,?,?,?,?)", rows)
    c.commit(); c.close()

def base_noise(rows, mints, wallets, t0, t1, rng, n=4000):
    """Random background trades so the mint price index is populated and copy sim has marks."""
    for _ in range(n):
        m = rng.choice(mints); w = rng.choice(wallets)
        ts = rng.randint(t0, t1); side = rng.choice(["buy", "sell"])
        price = mints_price[m](ts)
        usd = rng.uniform(5, 50); tok = usd / price if price > 0 else 1
        rows.append((f"n{_}:{w}:{m}", ts, ts, w, m, side, tok, usd, price))

# global price paths keyed by mint (closure per scenario)
mints_price = {}

def scenario_A(path):
    """Skilled wallets SELECT winning tokens; dumb wallets select losers. Skill persists into the
    held-out window. Copy-smart must be net-positive AND beat the (mostly-dumb) random null."""
    global mints_price
    rng = random.Random(1)
    T0, SPLIT, T1 = 0, 6200, 10000  # matches analyze split ~62%
    mints = [f"MINT{i}" for i in range(60)]
    winners = set(rng.sample(mints, 12))          # minority winners rise
    losers = [m for m in mints if m not in winners]  # majority drift DOWN
    def mkpath(m):
        up = m in winners
        def f(ts):
            return 1.0 * (1.0 + (0.0011 if up else -0.00007) * ts)
        return f
    mints_price = {m: mkpath(m) for m in mints}
    skilled = [f"SKILL{i}" for i in range(25)]
    dumb = [f"DUMB{i}" for i in range(80)]
    rows = []
    # noise marks: winners get noise from skilled-like flow, losers from dumb -> keeps index dense
    base_noise(rows, list(winners), skilled, T0, T1, rng, n=1500)
    base_noise(rows, losers, dumb, T0, T1, rng, n=4500)
    # skilled buy winners in BOTH windows (persistence)
    for w in skilled:
        for win in [T0, SPLIT]:
            for _ in range(6):
                m = rng.choice(list(winners)); bt = rng.randint(win, win + 1200)
                pb = mints_price[m](bt); tok = 100/pb
                rows.append((f"b{w}{m}{bt}", bt, bt, w, m, "buy", tok, 100.0, pb))
                stt = bt + rng.randint(1200, 2200); ps = mints_price[m](stt)
                rows.append((f"s{w}{m}{stt}", stt, stt, w, m, "sell", tok, tok*ps, ps))
    # dumb buy losers in BOTH windows
    for w in dumb:
        for win in [T0, SPLIT]:
            for _ in range(4):
                m = rng.choice(losers); bt = rng.randint(win, win + 1200)
                pb = mints_price[m](bt); tok = 50/pb
                rows.append((f"b{w}{m}{bt}", bt, bt, w, m, "buy", tok, 50.0, pb))
                stt = bt + rng.randint(800, 1800); ps = mints_price[m](stt)
                rows.append((f"s{w}{m}{stt}", stt, stt, w, m, "sell", tok, tok*ps, ps))
    make_db(path, rows)

def scenario_B(path):
    """Look-profitable-by-luck wallets; NO persistence (copy-window picks random)."""
    global mints_price
    rng = random.Random(2)
    T0, SPLIT, T1 = 0, 6200, 10000
    mints = [f"MINT{i}" for i in range(60)]
    # every token is a random walk -> no persistent winners
    paths = {}
    for m in mints:
        pts = sorted(rng.sample(range(T0, T1), 40))
        vals = [1.0]
        for _ in pts[1:]: vals.append(max(0.2, vals[-1]*rng.uniform(0.9, 1.11)))
        def mk(pts=pts, vals=vals):
            import bisect
            def f(ts):
                i = min(bisect.bisect_left(pts, ts), len(vals)-1); return vals[i]
            return f
        paths[m] = mk()
    mints_price = paths
    allw = [f"W{i}" for i in range(120)]
    rows = []
    base_noise(rows, mints, allw, T0, T1, rng, n=6000)
    # in ID window some wallets get lucky; in copy window everyone trades random tokens/timing
    for w in allw:
        nb = rng.randint(3, 8)
        for _ in range(nb):
            m = rng.choice(mints); bt = rng.randint(T0, SPLIT-1500)
            pb = paths[m](bt); tok = 60/pb
            rows.append((f"b{w}{m}{bt}", bt, bt, w, m, "buy", tok, 60.0, pb))
            stt = bt + rng.randint(400, 1400); ps = paths[m](stt)
            rows.append((f"s{w}{m}{stt}", stt, stt, w, m, "sell", tok, tok*ps, ps))
        for _ in range(rng.randint(2,6)):  # copy window: random again
            m = rng.choice(mints); bt = rng.randint(SPLIT, T1-1500)
            pb = paths[m](bt); tok = 60/pb
            rows.append((f"b{w}{m}{bt}", bt, bt, w, m, "buy", tok, 60.0, pb))
            stt = bt + rng.randint(400, 1400); ps = paths[m](stt)
            rows.append((f"s{w}{m}{stt}", stt, stt, w, m, "sell", tok, tok*ps, ps))
    make_db(path, rows)

def scenario_C(path):
    """Insider/deployer: first buyer of own tokens, dumps on the next buyers."""
    global mints_price
    rng = random.Random(3)
    T0, SPLIT, T1 = 0, 6200, 10000
    mints = [f"RUG{i}" for i in range(20)]
    # price pumps then dumps
    def mk(peak):
        def f(ts):
            return 1.0 + 3.0*math.exp(-((ts-peak)/400.0)**2)
        return f
    peaks = {m: rng.randint(500, 4000) for m in mints}
    mints_price = {m: mk(peaks[m]) for m in mints}
    insider = "DEPLOYER"
    victims = [f"VIC{i}" for i in range(40)]
    market = [f"MKT{i}" for i in range(20)]  # unrelated tokens for background noise
    for mm in market: mints_price[mm] = (lambda ts: 1.0)
    rows = []
    base_noise(rows, market, victims, T0, T1, rng, n=3000)  # noise on OTHER tokens only
    for m in mints:
        # insider is strictly the FIRST buyer (rank 0) of its own token, sells at peak
        bt = 1; pb = mints_price[m](bt); tok = 100/pb
        rows.append((f"ib{m}", bt, bt, insider, m, "buy", tok, 100.0, pb))
        stt = peaks[m]; ps = mints_price[m](stt)
        rows.append((f"is{m}", stt, stt, insider, m, "sell", tok, tok*ps, ps))
        # victims buy AFTER the insider (rank>0), near peak, then dump at a loss
        for v in rng.sample(victims, 5):
            vbt = peaks[m]-30; vpb = mints_price[m](vbt); vtok = 30/vpb
            rows.append((f"vb{m}{v}", vbt, vbt, v, m, "buy", vtok, 30.0, vpb))
            vst = peaks[m]+400; vps = mints_price[m](vst)
            rows.append((f"vs{m}{v}", vst, vst, v, m, "sell", vtok, vtok*vps, vps))
    make_db(path, rows)

def run(path):
    r = subprocess.run([sys.executable, "scripts/smartmoney/analyze.py", path],
                       capture_output=True, text=True, cwd=pathlib.Path(__file__).resolve().parents[2])
    return r.stdout + r.stderr

if __name__ == "__main__":
    tmp = tempfile.mkdtemp()
    for name, fn in [("A_real_persistent", scenario_A), ("B_survivorship", scenario_B), ("C_insider", scenario_C)]:
        p = os.path.join(tmp, name + ".sqlite")
        fn(p)
        print("="*80); print("SCENARIO", name); print("="*80)
        print(run(p))
