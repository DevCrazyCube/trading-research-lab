#!/usr/bin/env python3
"""NEWTERR shortint: build aligned panels from on-disk T16 FINRA data + xll price panel.

Outputs one npz: research/data/newterr_shortint/panels.npz
  symbols (S,), dates (D,)            -- trading calendar from xll (2016-01-04..2026-08-14)
  close, open, vol                    -- SPLIT-ADJUSTED price/volume panels (S,D) float32
  si_pos, si_prev, si_adv, si_dtc     -- short interest at settlement dates, (S,K) float32
  si_settle (K,)                      -- settlement dates
  si_avail_idx (K,)                   -- index into `dates` of the first session on which the
                                         print is PUBLIC (settlement + 8 business days, FINRA
                                         dissemination lag), i.e. the earliest a backtest may see it
  sv_short, sv_exempt, sv_total       -- Reg SHO daily short volume, (S,D) float32 (nan where absent)
  is_etf (S,)                         -- name-based ETF/fund flag from FINRA issueName
No returns, no signals, no verdicts here. Collection only.
"""
import gzip, json, os, sys, csv
import numpy as np
from collections import defaultdict

ROOT = "/home/anont/meme"
OUT_DIR = os.path.join(ROOT, "research/data/newterr_shortint")
os.makedirs(OUT_DIR, exist_ok=True)

print("loading xll price panel", flush=True)
z = np.load(os.path.join(ROOT, "research/data/xll_cache/eq_daily_panel.npz"), allow_pickle=True)
symbols = np.array([str(s) for s in z["symbols"]])
dates = np.array([str(d) for d in z["dates"]])
close = np.array(z["close"], dtype=np.float32)
opn = np.array(z["open"], dtype=np.float32)
vol = np.array(z["vol"], dtype=np.float32)
S, D = close.shape
sidx = {s: i for i, s in enumerate(symbols)}
didx = {d: i for i, d in enumerate(dates)}
print("panel", S, D, dates[0], dates[-1], flush=True)

# ---- split adjustment ------------------------------------------------------
print("applying split adjustment", flush=True)
ca = json.load(gzip.open(os.path.join(ROOT, "research/data/t7_cache/corporate_actions_all.json.gz")))
events = defaultdict(list)  # sym -> [(ex_date, ratio)] ratio = new/old shares
for rec in (ca.get("forward_splits") or []):
    try:
        r = float(rec["new_rate"]) / float(rec["old_rate"])
    except Exception:
        continue
    events[rec["symbol"]].append((rec["ex_date"], r))
for rec in (ca.get("reverse_splits") or []):
    try:
        r = float(rec["new_rate"]) / float(rec["old_rate"])
    except Exception:
        continue
    events[rec["symbol"]].append((rec["ex_date"], r))
n_applied = 0
for sym, evs in events.items():
    i = sidx.get(sym)
    if i is None:
        continue
    for ex, r in evs:
        if r <= 0 or abs(r - 1.0) < 1e-9:
            continue
        j = didx.get(ex)
        if j is None:
            # ex_date may be a non-trading day: take first session >= ex
            k = int(np.searchsorted(dates, ex))
            if k >= D:
                continue
            j = k
        # prices strictly BEFORE ex-date are in old (pre-split) units -> divide by r
        close[i, :j] /= r
        opn[i, :j] /= r
        vol[i, :j] *= r
        n_applied += 1
print("split events applied:", n_applied, flush=True)

# ---- FINRA short interest --------------------------------------------------
print("loading FINRA short interest", flush=True)
si_root = os.path.join(ROOT, "research/data/t16_panels/finra_short_interest/raw")
settle_dirs = sorted(os.listdir(si_root))
settles = [d.split("=")[1] for d in settle_dirs]
K = len(settles)
si_pos = np.full((S, K), np.nan, dtype=np.float32)
si_prev = np.full((S, K), np.nan, dtype=np.float32)
si_adv = np.full((S, K), np.nan, dtype=np.float32)
si_dtc = np.full((S, K), np.nan, dtype=np.float32)
issue_name = {}
for k, dname in enumerate(settle_dirs):
    p = os.path.join(si_root, dname)
    files = sorted(os.listdir(p))
    # earliest observation = closest to a point-in-time snapshot (revisions come later)
    f = os.path.join(p, files[0])
    with gzip.open(f, "rt", newline="") as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            sym = row.get("symbolCode") or ""
            i = sidx.get(sym)
            if i is None:
                continue
            if sym not in issue_name:
                issue_name[sym] = row.get("issueName") or ""

            def fl(x):
                try:
                    return float(x)
                except Exception:
                    return np.nan
            si_pos[i, k] = fl(row.get("currentShortPositionQuantity"))
            si_prev[i, k] = fl(row.get("previousShortPositionQuantity"))
            si_adv[i, k] = fl(row.get("averageDailyVolumeQuantity"))
            si_dtc[i, k] = fl(row.get("daysToCoverQuantity"))
    if k % 40 == 0:
        print("  si", k, dname, flush=True)

# dissemination lag: FINRA publishes ~8 business days after settlement.
# avail_idx = index of the first session strictly after settlement + 8 sessions.
si_avail_idx = np.full(K, -1, dtype=np.int32)
LAG_SESSIONS = 8
for k, s in enumerate(settles):
    j = int(np.searchsorted(dates, s))          # first session >= settlement
    j2 = j + LAG_SESSIONS
    if j2 < D:
        si_avail_idx[k] = j2
print("si loaded", K, "settlements", flush=True)

# ---- Reg SHO daily short volume -------------------------------------------
print("loading Reg SHO daily", flush=True)
rs_root = os.path.join(ROOT, "research/data/t16_panels/finra_regsho_daily/raw")
sv_short = np.full((S, D), np.nan, dtype=np.float32)
sv_exempt = np.full((S, D), np.nan, dtype=np.float32)
sv_total = np.full((S, D), np.nan, dtype=np.float32)
sess_dirs = sorted(os.listdir(rs_root))
nload = 0
for n, dname in enumerate(sess_dirs):
    sess = dname.split("=")[1]
    j = didx.get(sess)
    if j is None:
        continue
    p = os.path.join(rs_root, dname)
    files = sorted(os.listdir(p))
    f = os.path.join(p, files[0])
    try:
        with gzip.open(f, "rt", newline="") as fh:
            rd = csv.DictReader(fh)
            for row in rd:
                i = sidx.get(row.get("symbol") or "")
                if i is None:
                    continue
                try:
                    sv_short[i, j] = float(row["short_volume"])
                    sv_exempt[i, j] = float(row["short_exempt_volume"])
                    sv_total[i, j] = float(row["total_volume"])
                except Exception:
                    pass
    except Exception as e:
        print("  skip", sess, e, flush=True)
        continue
    nload += 1
    if n % 200 == 0:
        print("  regsho", n, sess, flush=True)
print("regsho sessions loaded", nload, flush=True)

# ---- ETF / fund flag from issueName ---------------------------------------
FUND_TOKENS = ("ETF", "TRUST", "FUND", " SHARES", "ISHARES", "SPDR", "PROSHARES",
               "DIREXION", "INVESCO", "VANGUARD", "INDEX", "PORTFOLIO", "ETN",
               "NOTES", "PREFERRED", " PFD", "WARRANT", "UNITS", " UNIT",
               "RIGHTS", "DEPOSITARY", "ULTRA", "BEAR", "BULL", "VIX",
               "WISDOMTREE", "GLOBAL X", "GRANITESHARES", "AMPLIFY", "FIRST TRUST")
is_etf = np.zeros(S, dtype=bool)
for sym, nm in issue_name.items():
    u = (nm or "").upper()
    if any(t in u for t in FUND_TOKENS):
        is_etf[sidx[sym]] = True
print("etf/fund-flagged", int(is_etf.sum()), flush=True)

np.savez_compressed(
    os.path.join(OUT_DIR, "panels.npz"),
    symbols=symbols, dates=dates, close=close, open=opn, vol=vol,
    si_pos=si_pos, si_prev=si_prev, si_adv=si_adv, si_dtc=si_dtc,
    si_settle=np.array(settles), si_avail_idx=si_avail_idx,
    sv_short=sv_short, sv_exempt=sv_exempt, sv_total=sv_total,
    is_etf=is_etf,
)
print("WROTE", os.path.join(OUT_DIR, "panels.npz"), flush=True)
