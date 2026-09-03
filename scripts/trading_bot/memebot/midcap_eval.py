"""Scorer + forward-return evaluator for the mid-cap flow screen.

Implements the FROZEN signal from research/midcap/MIDCAP_FLOW_PREREGISTRATION.md (sha 3f235481).
Reads only; writes no snapshots. Touches no arena closure member.

  imb(w)   = (buys(w) - sells(w)) / (buys(w) + sells(w))
  decel    = chg.m5*12 - chg.h1                 (per-hour accel; negative = fading)
  rotation = imb(m5) - imb(h6)                  (negative = sells rotating in early)
  LATE     = -(z(decel)) - (z(rotation)) - (z(imb_h1))
"""
from __future__ import annotations
import json, math, statistics as st, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SNAP = ROOT / "research" / "midcap" / "snapshots.jsonl"
TOLL = 0.030  # 3.0% round trip, per prereg

def load():
    snaps, meta = {}, []
    if not SNAP.exists():
        return snaps, meta
    with SNAP.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("_meta"):
                meta.append(r); continue
            snaps.setdefault(r["ts_ms"], []).append(r)
    return snaps, meta

def _imb(r, w):
    b, s = r["buys"].get(w, 0), r["sells"].get(w, 0)
    return None if (b + s) == 0 else (b - s) / (b + s)

def _z(vals):
    v = [x for x in vals if x is not None and math.isfinite(x)]
    if len(v) < 3:
        return {}
    m = st.mean(v); sd = st.pstdev(v)
    return {"m": m, "sd": sd if sd > 1e-12 else None}

def score_snapshot(rows):
    """Return rows annotated with the frozen LATE score. Cross-sectional z within the snapshot."""
    feats = []
    for r in rows:
        ch = r.get("chg") or {}
        try:
            m5 = float(ch.get("m5")) if ch.get("m5") is not None else None
            h1 = float(ch.get("h1")) if ch.get("h1") is not None else None
        except Exception:
            m5 = h1 = None
        decel = (m5 * 12 - h1) if (m5 is not None and h1 is not None) else None
        i5, i6, i1 = _imb(r, "m5"), _imb(r, "h6"), _imb(r, "h1")
        rot = (i5 - i6) if (i5 is not None and i6 is not None) else None
        feats.append({"r": r, "decel": decel, "rot": rot, "imb1": i1})
    zs = {k: _z([f[k] for f in feats]) for k in ("decel", "rot", "imb1")}
    out = []
    for f in feats:
        parts, ok = [], True
        for k in ("decel", "rot", "imb1"):
            st_ = zs.get(k) or {}
            if f[k] is None or not st_.get("sd"):
                ok = False; break
            parts.append((f[k] - st_["m"]) / st_["sd"])
        if not ok:
            continue
        f["late"] = -(parts[0]) - (parts[1]) - (parts[2])
        out.append(f)
    return out

def forward_returns(snaps, horizon_ms):
    """Join each scored token-snapshot to its price `horizon_ms` later (nearest within 40% slack)."""
    ts_sorted = sorted(snaps)
    by_mint = {}
    for ts in ts_sorted:
        for r in snaps[ts]:
            if r.get("price_usd"):
                by_mint.setdefault(r["mint"], []).append((ts, r["price_usd"]))
    obs = []
    slack = horizon_ms * 0.4
    for ts in ts_sorted:
        scored = score_snapshot(snaps[ts])
        for f in scored:
            r = f["r"]; p0 = r.get("price_usd")
            if not p0:
                continue
            series = by_mint.get(r["mint"], [])
            target = ts + horizon_ms
            cand = [(abs(t - target), t, p) for t, p in series if abs(t - target) <= slack and t > ts]
            if not cand:
                continue
            _, _, p1 = min(cand)
            obs.append({"ts": ts, "mint": r["mint"], "sym": r["sym"],
                        "late": f["late"], "fwd": math.log(p1 / p0)})
    return obs

def main():
    snaps, meta = load()
    if not snaps:
        print("no snapshots yet"); return
    ts_sorted = sorted(snaps)
    span_h = (ts_sorted[-1] - ts_sorted[0]) / 3_600_000 if len(ts_sorted) > 1 else 0.0
    print(f"snapshots {len(snaps)}  span {span_h:.2f}h  rows {sum(len(v) for v in snaps.values())}  "
          f"distinct mints {len({r['mint'] for v in snaps.values() for r in v})}")
    for h, lbl in ((1_800_000, "+30m"), (7_200_000, "+2h"), (21_600_000, "+6h")):
        obs = forward_returns(snaps, h)
        print(f"  {lbl}: {len(obs)} resolved token-snapshots  (GATE 1 needs 400 at +2h)")
    latest = ts_sorted[-1]
    sc = sorted(score_snapshot(snaps[latest]), key=lambda f: f["late"])
    print(f"\nCurrent snapshot {time.strftime('%H:%M:%S', time.localtime(latest/1000))} "
          f"-- LATE score (UNVALIDATED, decision-support only)")
    print(f"  {'sym':<12}{'LATE':>7}{'h1 b/s':>13}{'h1%':>8}{'h24%':>9}{'liq$':>12}")
    print("  --- most EARLY ---")
    for f in sc[:6]:
        r = f["r"]; bs = f"{r['buys']['h1']}/{r['sells']['h1']}"
        print(f"  {str(r['sym'])[:11]:<12}{f['late']:>7.2f}{bs:>13}{str(r['chg']['h1']):>8}"
              f"{str(r['chg']['h24']):>9}{r['liq_usd']:>12,.0f}")
    print("  --- most LATE ---")
    for f in sc[-6:]:
        r = f["r"]; bs = f"{r['buys']['h1']}/{r['sells']['h1']}"
        print(f"  {str(r['sym'])[:11]:<12}{f['late']:>7.2f}{bs:>13}{str(r['chg']['h1']):>8}"
              f"{str(r['chg']['h24']):>9}{r['liq_usd']:>12,.0f}")

if __name__ == "__main__":
    main()
