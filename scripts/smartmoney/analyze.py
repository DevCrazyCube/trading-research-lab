#!/usr/bin/env python3
"""Smart-money copy study -- the HONESTY TEST (paper / measurement only).

Reads the trade cache (scripts/smartmoney/collect_trades.py) or a synthetic cache and runs:

  1. Split time into an earlier IDENTIFICATION window and a later HELD-OUT COPY window.
  2. IDENTIFICATION: per-wallet realized PnL via average-cost matching. Identify "smart-money"
     wallets: realized PnL > 0, >= MIN_SELLS closed positions, hit-rate >= MIN_HIT, min volume.
  3. INSIDER/BUNDLER FLAG: flag wallets whose profit comes from being among the very first
     buyers of tokens (deployer/bundle that dumps on copiers -- un-copyable). Excluded.
  4. COPY SIM (held-out): for each identified wallet, copy their NEW buys with a realistic LAG
     (fill at the price L seconds later) and a per-trade TOLL; exit on their (lagged) sell, a
     fixed horizon, or a stop. Report net PnL.
  5. NULL: same copy sim on RANDOM wallets (matched count) -> the survivorship-free baseline.
  6. LAG DECAY: copy-window net PnL at L in {1,5,15}s.
  7. PERSISTENCE: do ID-window-profitable wallets stay profitable trading themselves in the
     copy window? (rank correlation + transition rates.)

The decisive output: copy-window net PnL of identified wallets (lagged+tolled) vs the random
null, and whether profitable-wallet status persists at all.
"""
from __future__ import annotations
import sqlite3, sys, math, random, statistics, pathlib, json

# ---- knobs (pre-registered defaults) ----
MIN_SELLS   = 4       # >= this many closed positions in ID window to be eligible
MIN_HIT     = 0.5     # >= this fraction of closed positions profitable
MIN_VOL_USD = 200.0   # >= this total buy volume in ID window (not one dust hit)
TOLL_BPS    = 100     # 1% per fill (pump.fun bonding-curve ~1% fee + slippage floor)
HORIZON_S   = 900     # 15 min max hold if the tracked wallet never sells
STOP_FRAC   = 0.40    # bail if mark drops 40% below entry
LAGS        = [0, 1, 5, 15]   # 0 = ideal same-instant ceiling; 1/5/15 = realistic copy lag
SEED        = 20260825

def load(path):
    c = sqlite3.connect(path)
    rows = c.execute("SELECT ts, wallet, mint, side, token_amount, usd, price_usd FROM trade ORDER BY ts, slot").fetchall()
    return rows

def realized_pnl(trades):
    """Average-cost realized PnL per wallet. trades: list of (ts,wallet,mint,side,tok,usd,price).
    Returns per-wallet dict with pnl, sells(closed positions count), wins, vol, and per-token first-buy flags."""
    # group by (wallet,mint)
    from collections import defaultdict
    pos = defaultdict(lambda: {"tok": 0.0, "cost": 0.0})  # inventory, cost basis (usd)
    wal = defaultdict(lambda: {"pnl": 0.0, "sells": 0, "wins": 0, "buyvol": 0.0, "mints": set()})
    for ts, w, m, side, tok, usd, price in trades:
        p = pos[(w, m)]; a = wal[w]
        if side == "buy":
            if tok <= 0 or usd <= 0: continue
            p["tok"] += tok; p["cost"] += usd
            a["buyvol"] += usd; a["mints"].add(m)
        else:  # sell
            if tok <= 0 or usd <= 0 or p["tok"] <= 0:
                continue
            sell_tok = min(tok, p["tok"])
            avg = p["cost"] / p["tok"] if p["tok"] > 0 else 0.0
            proceeds = usd * (sell_tok / tok) if tok > 0 else usd
            basis = avg * sell_tok
            pnl = proceeds - basis
            a["pnl"] += pnl; a["sells"] += 1; a["wins"] += 1 if pnl > 0 else 0
            p["tok"] -= sell_tok; p["cost"] -= basis
    return wal

def first_buyer_rank(trades):
    """For each mint, order buys by time; record for each (wallet,mint) whether wallet was in the
    first K buyers -> proxy for deployer/bundle/insider (early on the token they may have created)."""
    from collections import defaultdict
    seen = defaultdict(int)  # mint -> buyer count so far
    rank = {}  # (wallet,mint) -> earliest buy rank (0-based)
    for ts, w, m, side, tok, usd, price in trades:
        if side != "buy": continue
        if (w, m) not in rank:
            rank[(w, m)] = seen[m]
        seen[m] += 1
    return rank

def insider_flag(id_trades, wal, K=3, frac=0.6):
    """Flag a wallet as insider/bundler if >=frac of its ID-window realized PnL comes from tokens
    where it was among the first K buyers observed."""
    rank = first_buyer_rank(id_trades)
    # recompute per-(wallet,mint) realized pnl to attribute
    from collections import defaultdict
    pos = defaultdict(lambda: {"tok": 0.0, "cost": 0.0})
    wm_pnl = defaultdict(float)
    for ts, w, m, side, tok, usd, price in id_trades:
        p = pos[(w, m)]
        if side == "buy":
            if tok <= 0 or usd <= 0: continue
            p["tok"] += tok; p["cost"] += usd
        else:
            if tok <= 0 or usd <= 0 or p["tok"] <= 0: continue
            sell_tok = min(tok, p["tok"]); avg = p["cost"]/p["tok"] if p["tok"]>0 else 0
            proceeds = usd*(sell_tok/tok) if tok>0 else usd; basis = avg*sell_tok
            wm_pnl[(w, m)] += proceeds - basis
            p["tok"] -= sell_tok; p["cost"] -= basis
    flagged = set()
    for w in wal:
        tot = sum(v for (ww, m), v in wm_pnl.items() if ww == w and v > 0)
        early = sum(v for (ww, m), v in wm_pnl.items() if ww == w and v > 0 and rank.get((ww, m), 99) < K)
        if tot > 0 and early / tot >= frac:
            flagged.add(w)
    return flagged

def price_at(mint_trades, t):
    """First observed trade price on a mint at time >= t (simulates a lagged fill / mark)."""
    import bisect
    times = mint_trades["t"]; prices = mint_trades["p"]
    i = bisect.bisect_left(times, t)
    if i < len(times): return prices[i]
    return prices[-1] if prices else None

def build_mint_index(trades):
    from collections import defaultdict
    idx = defaultdict(lambda: {"t": [], "p": []})
    for ts, w, m, side, tok, usd, price in trades:
        if price and price > 0:
            idx[m]["t"].append(ts); idx[m]["p"].append(price)
    return idx

def copy_sim(copy_trades, wallets, lag, toll_bps=TOLL_BPS, horizon=HORIZON_S, stop=STOP_FRAC):
    """Copy each wallet's BUYS in the copy window. Enter at price lag-seconds later + toll;
    exit at the wallet's next SELL of that mint (price lag-seconds after their sell), else at
    horizon, else stop. Returns list of per-copy fractional returns (net of toll both sides)."""
    idx = build_mint_index(copy_trades)
    # collect each wallet's buys and sells per mint (time-ordered)
    from collections import defaultdict
    buys = defaultdict(list); sells = defaultdict(list)
    for ts, w, m, side, tok, usd, price in copy_trades:
        if w not in wallets: continue
        (buys if side == "buy" else sells)[(w, m)].append(ts)
    toll = toll_bps / 10000.0
    rets = []
    for (w, m), bts in buys.items():
        mi = idx.get(m)
        if not mi: continue
        stimes = sorted(sells.get((w, m), []))
        for bt in bts:
            entry = price_at(mi, bt + lag)
            if not entry or entry <= 0: continue
            # find their first sell strictly after this buy
            exit_t = None
            for st in stimes:
                if st > bt: exit_t = st + lag; break
            if exit_t is None:
                exit_t = bt + horizon
            # stop check: scan marks between entry and exit for a stop breach
            import bisect
            i0 = bisect.bisect_left(mi["t"], bt + lag)
            i1 = bisect.bisect_left(mi["t"], exit_t)
            exit_price = price_at(mi, exit_t)
            stopped = False
            for j in range(i0, min(i1, len(mi["t"]))):
                if mi["p"][j] <= entry * (1 - stop):
                    exit_price = entry * (1 - stop); stopped = True; break
            if not exit_price or exit_price <= 0: continue
            gross = exit_price / entry
            net = gross * (1 - toll) * (1 - toll) - 1.0  # toll on entry and exit
            rets.append(net)
    return rets

def summ(rets):
    if not rets: return {"n": 0}
    n = len(rets); mean = statistics.mean(rets)
    wins = sum(1 for r in rets if r > 0)
    med = statistics.median(rets)
    # bootstrap 95% CI of the mean
    random.seed(SEED); means = []
    for _ in range(2000):
        s = [rets[random.randrange(n)] for _ in range(n)]
        means.append(sum(s)/n)
    means.sort(); lo, hi = means[49], means[-50]
    return {"n": n, "mean_ret": mean, "median_ret": med, "hit": wins/n,
            "ci_lo": lo, "ci_hi": hi, "total_ret_sum": sum(rets)}

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "research/data/smartmoney_cache/trades.sqlite"
    trades = load(path)
    if not trades:
        print("no trades in cache:", path); return
    t_min, t_max = trades[0][0], trades[-1][0]
    span = t_max - t_min
    split = t_min + int(span * 0.62)  # earlier 62% = ID, later 38% = held-out copy
    id_tr = [r for r in trades if r[0] < split]
    cp_tr = [r for r in trades if r[0] >= split]
    print(f"# trades={len(trades)} span={span}s  ID={len(id_tr)} COPY={len(cp_tr)}")
    print(f"# ID window [{t_min}..{split}) COPY window [{split}..{t_max}]")

    wal = realized_pnl(id_tr)
    # eligibility
    smart = {w for w, a in wal.items()
             if a["pnl"] > 0 and a["sells"] >= MIN_SELLS and a["buyvol"] >= MIN_VOL_USD
             and (a["wins"]/a["sells"] if a["sells"] else 0) >= MIN_HIT}
    flagged = insider_flag(id_tr, {w: wal[w] for w in smart})
    smart_clean = smart - flagged
    print(f"\n## IDENTIFICATION")
    print(f"total wallets active in ID: {len(wal)}")
    print(f"smart-money (pnl>0, sells>={MIN_SELLS}, hit>={MIN_HIT}, vol>=${MIN_VOL_USD:.0f}): {len(smart)}")
    print(f"  flagged insider/bundler (early-buyer profit >=60%): {len(flagged)}  -> excluded")
    print(f"  clean copyable smart-money: {len(smart_clean)}")

    # PERSISTENCE: same wallets' realized PnL in the copy window
    wal_cp = realized_pnl(cp_tr)
    both = [w for w in smart_clean if w in wal_cp and wal_cp[w]["sells"] >= 1]
    stay_pos = sum(1 for w in both if wal_cp[w]["pnl"] > 0)
    print(f"\n## PERSISTENCE (identified wallets' OWN trading in held-out window)")
    print(f"identified-clean wallets that traded again in copy window: {len(both)}")
    if both:
        print(f"  still net-positive on their own trades: {stay_pos}/{len(both)} = {stay_pos/len(both):.1%}")
    # rank corr between ID pnl and copy pnl for wallets active in both
    common = [w for w in wal if w in wal_cp and wal[w]["sells"]>=1 and wal_cp[w]["sells"]>=1]
    if len(common) >= 8:
        xs = [wal[w]["pnl"] for w in common]; ys = [wal_cp[w]["pnl"] for w in common]
        def spearman(a, b):
            ra = {v:i for i,v in enumerate(sorted(range(len(a)), key=lambda k:a[k]))}
            rb = {v:i for i,v in enumerate(sorted(range(len(b)), key=lambda k:b[k]))}
            ar=[ra[i] for i in range(len(a))]; br=[rb[i] for i in range(len(b))]
            n=len(a); d2=sum((ar[i]-br[i])**2 for i in range(n))
            return 1-6*d2/(n*(n*n-1))
        print(f"  Spearman(ID pnl, COPY pnl) over {len(common)} wallets active both windows: {spearman(xs,ys):+.3f}")

    # COPY SIM at each lag, identified-clean vs random null
    random.seed(SEED)
    pool = [w for w in wal_cp]  # wallets active in copy window
    null_wallets = set(random.sample(pool, min(len(smart_clean), len(pool)))) if pool else set()
    print(f"\n## COPY SIM (held-out window; toll={TOLL_BPS}bps/side, horizon={HORIZON_S}s, stop={STOP_FRAC:.0%})")
    print(f"{'lag':>4} | {'copy smart-clean':>34} | {'random null':>34}")
    print(f"{'':>4} | {'n   mean%   hit    95%CI':>34} | {'n   mean%   hit    95%CI':>34}")
    results = {}
    for lag in LAGS:
        rs = summ(copy_sim(cp_tr, smart_clean, lag))
        rn = summ(copy_sim(cp_tr, null_wallets, lag))
        results[lag] = {"smart": rs, "null": rn}
        def fmt(s):
            if s["n"]==0: return f"{'0':>4}  --"
            return f"{s['n']:>4} {s['mean_ret']*100:>6.2f} {s['hit']*100:>5.1f}  [{s['ci_lo']*100:+.2f},{s['ci_hi']*100:+.2f}]"
        print(f"{lag:>4}s| {fmt(rs):>34} | {fmt(rn):>34}")

    print(f"\n## VERDICT INPUTS")
    for lag in LAGS:
        rs = results[lag]["smart"]; rn = results[lag]["null"]
        if rs["n"] and rn["n"]:
            edge = rs["mean_ret"] - rn["mean_ret"]
            pos = rs["ci_lo"] > 0
            beats = rs["ci_lo"] > rn["mean_ret"]
            print(f"  lag={lag}s: smart mean {rs['mean_ret']*100:+.2f}% vs null {rn['mean_ret']*100:+.2f}% "
                  f"(edge {edge*100:+.2f}pp); net-positive={pos}; beats-null={beats}")
    out = {"path": path, "id_n": len(id_tr), "copy_n": len(cp_tr), "smart": len(smart),
           "flagged": len(flagged), "clean": len(smart_clean),
           "persistence": {"both": len(both), "stay_pos": stay_pos},
           "results": {str(k): v for k, v in results.items()}}
    outp = pathlib.Path("research/data/smartmoney_cache/analysis_result.json")
    outp.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {outp}")

if __name__ == "__main__":
    main()
