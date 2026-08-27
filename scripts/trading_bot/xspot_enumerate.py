#!/usr/bin/env python3
"""Enumerate every Binance SPOT symbol that has monthly 1d klines on data.binance.vision."""
import json, sys, urllib.request, xml.etree.ElementTree as ET

BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
OUT = "/home/anont/meme/research/data/xspot_cache/symbols.json"


def list_prefixes(prefix):
    marker, out = "", []
    while True:
        url = f"{BASE}?delimiter=/&prefix={prefix}&marker={marker}"
        with urllib.request.urlopen(url, timeout=60) as r:
            root = ET.fromstring(r.read())
        for cp in root.findall(f"{NS}CommonPrefixes"):
            out.append(cp.find(f"{NS}Prefix").text)
        trunc = root.find(f"{NS}IsTruncated").text == "true"
        if not trunc:
            return out
        nm = root.find(f"{NS}NextMarker")
        marker = urllib.parse.quote(nm.text if nm is not None else out[-1])


def main():
    pfx = list_prefixes("data/spot/monthly/klines/")
    syms = [p.split("/")[-2] for p in pfx]
    print(f"total spot symbols: {len(syms)}", flush=True)
    usdt = sorted(s for s in syms if s.endswith("USDT"))
    print(f"USDT-quoted: {len(usdt)}", flush=True)
    json.dump({"all": sorted(syms), "usdt": usdt}, open(OUT, "w"))


if __name__ == "__main__":
    import urllib.parse
    main()
