"""Does buying the fresh trending universe make money? Measured, net of toll.

mcap is proportional to price on a fixed 1B supply, so log(mcap ratio) = log(price ratio).
Survivorship is handled explicitly: coins that drop out of the feed are counted and charged,
never silently dropped (that would bias every return UP).
"""
from __future__ import annotations
import json, math, random, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SNAP = ROOT / "research" / "midcap" / "fresh_snapshots.jsonl"
TOLL = 0.030
DROPOUT_CHARGE = -0.50   # conservative: an unresolved coin is assumed -50%

def load():
    snaps = {}
    if not SNAP.exists():
        return snaps
    with SNAP.open() as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: r = json.loads(line)
            except Exception: continue
            if r.get("_meta"): continue
            if r.get("mcap"): snaps.setdefault(r["ts_ms"], []).append(r)
    return snaps

def series(snaps):
    by = {}
    for ts, rows in snaps.items():
        for r in rows:
            by.setdefault(r["mint"], {})[ts] = r
    return by

def fwd(snaps, by, horizon_ms, filt=None):
    """Return (resolved_obs, n_dropout). obs = list of (ts, mint, logret)."""
    ts_all = sorted(snaps)
    if not ts_all: return [], 0
    last_ts = ts_all[-1]
    obs, drop = [], 0
    slack = horizon_ms * 0.5
    for ts in ts_all:
        if ts + horizon_ms > last_ts:      # not yet resolvable -- not a dropout
            continue
        for r in snaps[ts]:
            if filt and not filt(r, ts): continue
            s = by.get(r["mint"], {})
            cand = [(abs(t - (ts + horizon_ms)), t) for t in s
                    if abs(t - (ts + horizon_ms)) <= slack and t > ts]
            if not cand:
                drop += 1; continue
            _, t1 = min(cand)
            m0, m1 = r["mcap"], s[t1]["mcap"]
            if not m0 or not m1 or m0 <= 0 or m1 <= 0:
                drop += 1; continue
            obs.append((ts, r["mint"], math.log(m1 / m0)))
    return obs, drop

def report(obs, drop, label, horizon_lbl):
    if len(obs) < 30:
        print(f"  {label:<26} {horizon_lbl}: only {len(obs)} obs, {drop} unresolved -- too few")
        return
    byts = {}
    for ts, _, r in obs: byts.setdefault(ts, []).append(r)
    per = {ts: sum(v)/len(v) for ts, v in byts.items()}
    vals = list(per.values())
    gross = st.mean(vals)
    net = gross - TOLL
    n = len(obs); res_rate = n / (n + drop) if (n + drop) else 1.0
    surv = (gross * n + DROPOUT_CHARGE * drop) / (n + drop) if (n + drop) else gross
    random.seed(20260903)
    boot = sorted(st.mean(random.choices(vals, k=len(vals))) for _ in range(3000))
    med = st.median([r for _, _, r in obs])
    win = sum(1 for _, _, r in obs if r > TOLL) / n
    print(f"  {label:<26} {horizon_lbl}: n={n:5d} snaps={len(per):3d} resolved={res_rate:5.1%}")
    print(f"      gross {gross*100:+7.2f}%  NET {net*100:+7.2f}%  CI[{(boot[75]-TOLL)*100:+.2f},"
          f"{(boot[-75]-TOLL)*100:+.2f}]  median {med*100:+6.2f}%  win>toll {win:5.1%}")
    if drop:
        print(f"      survivorship-charged gross (dropouts at {DROPOUT_CHARGE:+.0%}): {surv*100:+7.2f}%"
              f"  -> NET {(surv-TOLL)*100:+7.2f}%")

def main():
    snaps = load()
    if len(snaps) < 2:
        print(f"snapshots: {len(snaps)} -- need more collection time"); return
    ts = sorted(snaps)
    span_m = (ts[-1] - ts[0]) / 60000
    by = series(snaps)
    print(f"snapshots {len(snaps)}  span {span_m:.0f} min  distinct mints {len(by)}  "
          f"rows {sum(len(v) for v in snaps.values())}\n")
    HZ = [(900_000, "+15m"), (1_800_000, "+30m"), (3_600_000, "+1h"), (7_200_000, "+2h")]
    def near_ath(r, ts, lo=0.95):
        return bool(r.get("ath")) and r["mcap"] / r["ath"] >= lo
    def off_ath(r, ts, hi=0.80):
        return bool(r.get("ath")) and r["mcap"] / r["ath"] < hi
    def young(r, ts, h=6.0):
        return bool(r.get("created_ms")) and (ts - float(r["created_ms"])) / 3.6e6 <= h
    def band(r, ts):
        return 3e5 <= (r["mcap"] or 0) <= 1e7
    arms = [("BUY EVERYTHING", None),
            ("at/near ATH (>=95%)", near_ath),
            ("off ATH (<80%)", off_ath),
            ("age <= 6h", young),
            ("mcap $300k-$10M", band)]
    for hz, lbl in HZ:
        any_ = False
        for name, f in arms:
            o, d = fwd(snaps, by, hz, f)
            if len(o) >= 30: any_ = True
            report(o, d, name, lbl)
        if any_: print()

if __name__ == "__main__":
    main()
