"""POSTURE C2 collector: assemble free cross-sections outside equities & crypto.

Sources (all free, keyless):
  FRED   fredgraph.csv           daily FX (H.10) + Treasury constant-maturity yields
  cached research/data/ts_cache  Yahoo daily adjclose (commodity/rate/FX/index futures)
  cached research/data/ratescredit_cache/etf_daily.json  Yahoo daily bond+credit ETFs
  cached research/data/rv_cache  5-min bars -> daily close (US sector ETFs, single names)
  cached research/data/optimp_cache  CBOE daily volatility indices

Writes one npz per cross-section into research/data/c2_cache/.
"""
import json
import os
import sys
import time
import subprocess
import urllib.request

import numpy as np

ROOT = "/home/anont/meme"
OUT = os.path.join(ROOT, "research/data/c2_cache")
FRED_DIR = os.path.join(OUT, "fred")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"


# ---------------------------------------------------------------- FRED
def fred(sid, tries=4):
    os.makedirs(FRED_DIR, exist_ok=True)
    p = os.path.join(FRED_DIR, sid + ".csv")
    if os.path.exists(p) and os.path.getsize(p) > 200:
        return open(p).read()
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + sid
    for i in range(tries):
        try:
            b = subprocess.run(["curl", "-sS", "--max-time", "45", url],
                               capture_output=True, timeout=60).stdout.decode(
                                   "utf-8", "replace")
            if b.startswith("observation_date") or b.startswith("DATE"):
                open(p, "w").write(b)
                return b
        except Exception as e:
            sys.stderr.write("fred %s try%d %s\n" % (sid, i, e))
        time.sleep(1 + 2 * i)
    return ""


def fred_series(sid):
    """-> (dates as YYYYMMDD int array, values float array) with '.' dropped."""
    txt = fred(sid)
    if not txt:
        return np.array([], dtype=np.int64), np.array([])
    ds, vs = [], []
    for line in txt.strip().split("\n")[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0], parts[1].strip()
        if v in (".", "", "NA"):
            continue
        try:
            vs.append(float(v))
        except ValueError:
            continue
        ds.append(int(d.replace("-", "")))
    return np.array(ds, dtype=np.int64), np.array(vs, dtype=float)


# ------------------------------------------------------- cached Yahoo daily
def yahoo_daily(path):
    """ts_cache raw json -> (yyyymmdd int array, adjclose float array)."""
    import datetime
    d = json.load(open(path))["chart"]["result"][0]
    ts = d["timestamp"]
    ind = d["indicators"]
    if "adjclose" in ind and ind["adjclose"][0].get("adjclose"):
        px = ind["adjclose"][0]["adjclose"]
    else:
        px = ind["quote"][0]["close"]
    ds, vs = [], []
    for t, p in zip(ts, px):
        if p is None:
            continue
        dt = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
        ds.append(dt.year * 10000 + dt.month * 100 + dt.day)
        vs.append(float(p))
    return np.array(ds, dtype=np.int64), np.array(vs, dtype=float)


def etfjson_daily(blob, key):
    import datetime
    d = blob[key]
    ts = d["t"]
    px = d.get("ac") or d.get("adjclose") or d.get("c")
    ds, vs = [], []
    for t, p in zip(ts, px):
        if p is None:
            continue
        dt = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
        ds.append(dt.year * 10000 + dt.month * 100 + dt.day)
        vs.append(float(p))
    return np.array(ds, dtype=np.int64), np.array(vs, dtype=float)


def npz_5min_to_daily(path):
    """rv_cache 5-min bars -> daily last close (US/Eastern-ish via UTC date of bar)."""
    import datetime
    z = np.load(path, allow_pickle=True)
    t = z["t"].astype(np.int64)
    c = z["c"].astype(float)
    # bars are epoch seconds; use US/Eastern calendar date (UTC-5/-4 -> subtract 5h is
    # enough to keep 09:30-16:00 ET inside one calendar day)
    dd = np.array([(datetime.datetime.fromtimestamp(int(x) - 5 * 3600,
                                                    datetime.timezone.utc)).strftime("%Y%m%d")
                   for x in t], dtype=np.int64)
    # last close per date
    order = np.argsort(dd, kind="stable")
    dd, c = dd[order], c[order]
    uniq, last_idx = np.unique(dd, return_index=True)
    ends = np.append(last_idx[1:], len(dd)) - 1
    return uniq, c[ends]


# ------------------------------------------------------------- panel build
def build_panel(members, name, min_members=8):
    """members: dict sym -> (dates,int64 ; values,float). Returns dict for npz."""
    syms = sorted(members)
    alld = sorted(set().union(*[set(members[s][0].tolist()) for s in syms]))
    alld = np.array(alld, dtype=np.int64)
    idx = {d: i for i, d in enumerate(alld.tolist())}
    P = np.full((len(alld), len(syms)), np.nan)
    for j, s in enumerate(syms):
        ds, vs = members[s]
        for d, v in zip(ds.tolist(), vs.tolist()):
            P[idx[d], j] = v
    return {"name": name, "dates": alld, "syms": np.array(syms), "px": P}


def save(panel):
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, panel["name"] + ".npz"),
                        dates=panel["dates"], syms=panel["syms"], px=panel["px"])
    print("saved %-24s members=%3d dates=%5d  %d..%d"
          % (panel["name"], len(panel["syms"]), len(panel["dates"]),
             panel["dates"][0], panel["dates"][-1]))


# ------------------------------------------------------------------ specs
# FRED H.10. Convention: DEXUS** = USD per foreign (rise -> foreign appreciates).
#                        DEX**US = foreign per USD  (rise -> foreign DEPRECIATES; invert).
G10 = {  # sid: (label, invert?)
    "DEXUSEU": ("EUR", False), "DEXJPUS": ("JPY", True), "DEXUSUK": ("GBP", False),
    "DEXSZUS": ("CHF", True), "DEXUSAL": ("AUD", False), "DEXCAUS": ("CAD", True),
    "DEXUSNZ": ("NZD", False), "DEXSDUS": ("SEK", True), "DEXNOUS": ("NOK", True),
    "DEXDNUS": ("DKK", True),
}
EM = {
    "DEXBZUS": ("BRL", True), "DEXMXUS": ("MXN", True), "DEXKOUS": ("KRW", True),
    "DEXSIUS": ("SGD", True), "DEXTAUS": ("TWD", True), "DEXTHUS": ("THB", True),
    "DEXINUS": ("INR", True), "DEXMAUS": ("MYR", True), "DEXSFUS": ("ZAR", True),
    "DEXCHUS": ("CNY", True), "DEXHKUS": ("HKD", True), "DEXVZUS": ("VEF", True),
    "DEXSLUS": ("LKR", True), "DEXKUUS": ("KWD", True), "DEXNOUS_skip": ("x", True),
}
EM.pop("DEXNOUS_skip")

TSY = ["DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2", "DGS3", "DGS5",
       "DGS7", "DGS10", "DGS20", "DGS30"]
# approximate modified duration for a par bond at each constant maturity
TSY_DUR = {"DGS1MO": 0.083, "DGS3MO": 0.25, "DGS6MO": 0.49, "DGS1": 0.98,
           "DGS2": 1.94, "DGS3": 2.85, "DGS5": 4.55, "DGS7": 6.1,
           "DGS10": 8.2, "DGS20": 13.5, "DGS30": 16.5}

COMMOD_FUT = ["CL=F", "BZ=F", "NG=F", "HO=F", "RB=F", "GC=F", "SI=F", "HG=F",
              "PL=F", "PA=F", "ZC=F", "ZS=F", "ZW=F", "ZL=F", "ZM=F", "ZO=F",
              "KC=F", "CC=F", "SB=F", "CT=F", "OJ=F", "LE=F", "GF=F", "HE=F"]
COMMOD_ETF = ["DBC", "DBA", "DBB", "DBE", "GSG", "DJP", "PDBC", "COMT", "FTGC",
              "USO", "USL", "BNO", "UNG", "UNL", "UGA", "GLD", "IAU", "SLV",
              "PPLT", "CPER", "CORN", "WEAT", "SOYB", "CANE"]
SECTOR = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU",
          "XLV", "XLY"]
SECTOR_V = ["VAW", "VCR", "VDC", "VDE", "VFH", "VGT", "VHT", "VIS", "VPU", "VNQ"]
SINGLE = ["AAPL", "ABBV", "ADBE", "AMD", "AMZN", "AVGO", "BAC", "COST", "CRM",
          "CSCO", "CVX", "GOOGL", "HD", "INTC", "JNJ", "JPM", "KO", "LLY", "MA",
          "META", "MRK", "MSFT", "NFLX", "NVDA", "ORCL", "PEP", "PG", "TSLA",
          "UNH", "V", "WMT", "XOM"]
VOLIDX = ["VIX", "VIX9D", "VIX3M", "VIX6M", "VVIX", "VXN", "VXD", "RVX", "OVX",
          "GVZ", "VXEEM", "VXEWZ", "VXFXI", "VXAPL", "VXGDX", "VXSLV", "VXXLE",
          "VXTLT", "VXEFA"]


def main():
    os.makedirs(OUT, exist_ok=True)
    ts_raw = os.path.join(ROOT, "research/data/ts_cache/raw")
    rv = os.path.join(ROOT, "research/data/rv_cache")

    # --- FX (FRED, daily noon rates)
    for tag, spec in (("fx_g10", G10), ("fx_em", EM)):
        mem = {}
        for sid, (lab, inv) in spec.items():
            d, v = fred_series(sid)
            if len(d) < 100:
                print("  MISS %s (%s) n=%d" % (sid, lab, len(d)))
                continue
            if inv:
                v = 1.0 / v
            mem[lab] = (d, v)
        if mem:
            save(build_panel(mem, tag))

    # --- Treasury constant maturities -> duration-proxy price index
    mem = {}
    for sid in TSY:
        d, y = fred_series(sid)
        if len(d) < 100:
            print("  MISS %s" % sid)
            continue
        dur = TSY_DUR[sid]
        dy = np.diff(y) / 100.0
        # daily total return approx: carry (y/252) - D * dy
        r = y[1:] / 100.0 / 252.0 - dur * dy
        px = np.concatenate([[1.0], np.cumprod(1.0 + r)])
        mem[sid.replace("DGS", "UST")] = (d, px)
    if mem:
        save(build_panel(mem, "ust_curve"))

    # --- cached Yahoo daily
    def from_ts(names, tag):
        mem = {}
        for s in names:
            p = os.path.join(ts_raw, s + ".json")
            if not os.path.exists(p):
                print("  MISS ts %s" % s)
                continue
            d, v = yahoo_daily(p)
            if len(d) > 100:
                mem[s.replace("=F", "")] = (d, v)
        if mem:
            save(build_panel(mem, tag))

    from_ts(COMMOD_FUT, "commod_fut")
    from_ts(COMMOD_ETF, "commod_etf")

    # --- bond / credit ETFs
    p = os.path.join(ROOT, "research/data/ratescredit_cache/etf_daily.json")
    if os.path.exists(p):
        blob = json.load(open(p))
        mem = {}
        for k in blob:
            try:
                d, v = etfjson_daily(blob, k)
            except Exception:
                continue
            if len(d) > 100:
                mem[k] = (d, v)
        if mem:
            save(build_panel(mem, "bond_credit_etf"))

    # --- sector ETFs & single names from 5-min cache
    def from_rv(names, tag):
        mem = {}
        for s in names:
            p = os.path.join(rv, s + ".npz")
            if not os.path.exists(p):
                print("  MISS rv %s" % s)
                continue
            d, v = npz_5min_to_daily(p)
            if len(d) > 100:
                mem[s] = (d, v)
        if mem:
            save(build_panel(mem, tag))

    from_rv(SECTOR + SECTOR_V, "sector_etf")
    from_rv(SINGLE, "us_singlename")

    # --- CBOE volatility indices (cached)
    oc = os.path.join(ROOT, "research/data/optimp_cache")
    mem = {}
    for s in VOLIDX:
        p = os.path.join(oc, "cboe_%s.csv" % s)
        if not os.path.exists(p):
            continue
        ds, vs = [], []
        for line in open(p).read().strip().split("\n")[1:]:
            f = line.split(",")
            if len(f) < 5:
                continue
            dt = f[0].strip()
            try:
                if "/" in dt:
                    m, dd, yy = dt.split("/")
                    key = int(yy) * 10000 + int(m) * 100 + int(dd)
                else:
                    key = int(dt[:10].replace("-", ""))
                val = float(f[4])
            except ValueError:
                continue
            if val > 0:
                ds.append(key)
                vs.append(val)
        if len(ds) > 100:
            mem[s] = (np.array(ds, dtype=np.int64), np.array(vs))
    if mem:
        save(build_panel(mem, "vol_index"))


if __name__ == "__main__":
    main()
