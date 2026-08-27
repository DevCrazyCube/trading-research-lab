#!/usr/bin/env python3
"""Fetch SEC EDGAR filing indexes for the CEFConnect universe (free, rate-limited).

Writes research/data/cef0822c_cache/edgar_submissions.json.gz :
   {ticker: {"cik": int, "filings": [[form, filingDate, primaryDocDescription], ...]}}

Detached background use only (SEC allows <=10 req/s; we do ~5).
"""
import gzip
import json
import os
import sys
import time
import urllib.request

UA = "meme-research officialjoy04@gmail.com"
OUT_DIR = "/home/anont/meme/research/data/cef0822c_cache"
T12 = "/home/anont/meme/research/data/t12_cache"

KEEP_PREFIX = ("SC 13D", "SC 13G", "SC TO", "SC 14D", "425", "N-2", "N-14", "DEF 14A",
               "PRE 14A", "8-K", "N-23C", "40-17", "497", "N-54")


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Encoding": "gzip, deflate"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except Exception as e:
            if i == tries - 1:
                sys.stderr.write("FAIL %s %s\n" % (url, e))
                return None
            time.sleep(1.5 * (i + 1))
    return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    tickers = sorted(json.load(gzip.open(os.path.join(T12, "universe.json.gz"))),
                     key=lambda x: x["Ticker"])
    tickers = [t["Ticker"] for t in tickers]

    ct = get("https://www.sec.gov/files/company_tickers.json")
    tmap = {}
    for v in ct.values():
        tmap.setdefault(v["ticker"].upper(), int(v["cik_str"]))

    out = {}
    miss = []
    n = 0
    for tk in tickers:
        cik = tmap.get(tk.upper())
        if cik is None:
            miss.append(tk)
            continue
        n += 1
        sub = get("https://data.sec.gov/submissions/CIK%010d.json" % cik)
        time.sleep(0.22)
        if sub is None:
            miss.append(tk)
            continue
        rows = []
        rec = sub.get("filings", {}).get("recent", {})
        forms = rec.get("form", [])
        dates = rec.get("filingDate", [])
        descs = rec.get("primaryDocDescription", [""] * len(forms))
        items = rec.get("items", [""] * len(forms))
        for i in range(len(forms)):
            f = forms[i]
            if any(f.startswith(p) for p in KEEP_PREFIX):
                rows.append([f, dates[i], (descs[i] or "")[:80], (items[i] or "")[:40]])
        earliest = min(dates) if dates else "9999"
        # older chunks if the recent block does not reach back to 2021
        if earliest > "2021-06-01":
            for fmeta in sub.get("filings", {}).get("files", []):
                nm = fmeta.get("name")
                if not nm:
                    continue
                if fmeta.get("filingTo", "9999") < "2021-06-01":
                    continue
                old = get("https://data.sec.gov/submissions/" + nm)
                time.sleep(0.22)
                if not old:
                    continue
                of = old.get("form", [])
                od = old.get("filingDate", [])
                odd = old.get("primaryDocDescription", [""] * len(of))
                oi = old.get("items", [""] * len(of))
                for i in range(len(of)):
                    if any(of[i].startswith(p) for p in KEEP_PREFIX):
                        rows.append([of[i], od[i], (odd[i] or "")[:80], (oi[i] or "")[:40]])
                if min(od or ["9999"]) < "2021-06-01":
                    break
        out[tk] = {"cik": cik, "filings": rows}
        if n % 25 == 0:
            sys.stderr.write("...%d tickers, last=%s rows=%d\n" % (n, tk, len(rows)))
            sys.stderr.flush()

    with gzip.open(os.path.join(OUT_DIR, "edgar_submissions.json.gz"), "wt") as fh:
        json.dump({"fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "n_tickers": len(out), "missing": miss, "data": out}, fh)
    sys.stderr.write("DONE %d tickers, %d missing\n" % (len(out), len(miss)))


if __name__ == "__main__":
    main()
