#!/usr/bin/env python3
"""Stream Binance 5m kline zips -> hourly OHLCV CSV. Low RSS: one zip in memory at a time."""
import csv, io, pathlib, sys, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "research" / "data" / "orphanflush_cache" / "raw" / "klines5m"
OUT = ROOT / "research" / "data" / "calendar_cache"
OUT.mkdir(parents=True, exist_ok=True)

def build(sym):
    d = RAW / sym
    files = sorted(d.glob(f"{sym}-5m-*.zip"))
    hours = {}
    for p in files:
        try:
            z = zipfile.ZipFile(p)
        except Exception:
            continue
        for name in z.namelist():
            if not name.endswith(".csv"):
                continue
            with z.open(name) as f:
                for line in io.TextIOWrapper(f, encoding="utf-8"):
                    parts = line.split(",")
                    if len(parts) < 6 or not parts[0].strip().isdigit():
                        continue
                    ms = int(parts[0]); o=float(parts[1]); h=float(parts[2]); l=float(parts[3]); c=float(parts[4]); v=float(parts[5])
                    hb = ms - (ms % 3600000)
                    r = hours.get(hb)
                    if r is None:
                        hours[hb] = [o,h,l,c,v]
                    else:
                        if h > r[1]: r[1]=h
                        if l < r[2]: r[2]=l
                        r[3]=c; r[4]+=v
        z.close()
    out = OUT / f"{sym}_1h.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ms","o","h","l","c","v"])
        for k in sorted(hours):
            r = hours[k]
            w.writerow([k, r[0], r[1], r[2], r[3], round(r[4],4)])
    print(sym, len(hours), "hours ->", out)

for sym in sys.argv[1:] or ["BTCUSDT","ETHUSDT"]:
    build(sym)
