#!/usr/bin/env python3
"""Fast keep-alive fetch of Binance SPOT monthly klines for a symbol list (incl. delisted pairs)."""
import io, json, os, sys, threading, zipfile, urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import requests
from requests.adapters import HTTPAdapter

HOST = "https://data.binance.vision"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
CACHE = "/home/anont/meme/research/data/xspot_cache"
INTERVAL = os.environ.get("XSPOT_INTERVAL", "1d")
MARKET = os.environ.get("XSPOT_MARKET", "spot")
SYMDIR = os.environ.get("XSPOT_OUT", f"{CACHE}/sym")
SYMLIST = os.environ.get("XSPOT_SYMS", "")
os.makedirs(SYMDIR, exist_ok=True)

SESS = requests.Session()
SESS.mount("https://", HTTPAdapter(pool_connections=64, pool_maxsize=256, max_retries=2))


def get(url, tries=3):
    for _ in range(tries):
        try:
            r = SESS.get(url, timeout=45)
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                return None
        except Exception:
            pass
    return None


def list_keys(sym):
    prefix = f"data/{MARKET}/monthly/klines/{sym}/{INTERVAL}/"
    marker, keys = "", []
    while True:
        b = get(f"{S3}?prefix={prefix}&marker={marker}")
        if b is None:
            return sym, keys
        root = ET.fromstring(b)
        got = [c.find(f"{NS}Key").text for c in root.findall(f"{NS}Contents")]
        keys += [k for k in got if k.endswith(".zip")]
        tr = root.find(f"{NS}IsTruncated")
        if tr is None or tr.text != "true" or not got:
            return sym, keys
        marker = urllib.parse.quote(got[-1])


def parse(buf):
    rows = []
    with zipfile.ZipFile(io.BytesIO(buf)) as z:
        txt = z.read(z.namelist()[0]).decode("utf-8", "replace")
    for line in txt.splitlines():
        if not line or line[0] not in "0123456789":
            continue
        f = line.split(",")
        try:
            t = int(f[0])
            if t > 10 ** 14:
                t //= 1000
            rows.append((t, float(f[1]), float(f[2]), float(f[3]), float(f[4]),
                         float(f[5]), float(f[7]), float(f[8]), float(f[9]), float(f[10])))
        except (ValueError, IndexError):
            continue
    return rows


def main():
    if SYMLIST:
        syms = [s for s in SYMLIST.split(",") if s]
    else:
        syms = json.load(open(f"{CACHE}/symbols.json"))["usdt"]
    syms = [s for s in syms if not os.path.exists(f"{SYMDIR}/{s}.npz")]
    print(f"symbols to fetch: {len(syms)}", flush=True)

    keymap = {}
    with ThreadPoolExecutor(max_workers=48) as ex:
        for i, (sym, keys) in enumerate(ex.map(list_keys, syms)):
            keymap[sym] = keys
            if (i + 1) % 100 == 0:
                print(f"  listed {i+1}/{len(syms)}", flush=True)
    tasks = [(s, k) for s, ks in keymap.items() for k in ks]
    print(f"files to download: {len(tasks)}", flush=True)

    store = defaultdict(list)
    lock = threading.Lock()
    cnt = [0]

    def work(t):
        sym, key = t
        b = get(f"{HOST}/{key}")
        rows = []
        if b:
            try:
                rows = parse(b)
            except Exception:
                rows = []
        with lock:
            store[sym] += rows
            cnt[0] += 1
            if cnt[0] % 2000 == 0:
                print(f"  dl {cnt[0]}/{len(tasks)}", flush=True)

    with ThreadPoolExecutor(max_workers=96) as ex:
        list(ex.map(work, tasks))

    nw = 0
    for sym, rows in store.items():
        if not rows:
            continue
        rows.sort()
        a = np.asarray(rows, dtype=np.float64)
        _, keep = np.unique(a[:, 0], return_index=True)
        a = a[keep]
        np.savez_compressed(f"{SYMDIR}/{sym}.npz", t=a[:, 0].astype(np.int64),
                            o=a[:, 1].astype(np.float32), h=a[:, 2].astype(np.float32),
                            l=a[:, 3].astype(np.float32), c=a[:, 4].astype(np.float32),
                            v=a[:, 5].astype(np.float32), qv=a[:, 6].astype(np.float32),
                            n=a[:, 7].astype(np.float32), tbb=a[:, 8].astype(np.float32),
                            tbq=a[:, 9].astype(np.float32))
        nw += 1
    print(f"wrote {nw} symbols", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
