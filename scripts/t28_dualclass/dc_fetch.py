#!/usr/bin/env python3
"""Fetch daily bars for candidate dual-class share-class pairs (Alpaca SIP, free tier)."""
import json, pathlib, sys, time
sys.path.insert(0, "/home/anont/meme")
from scripts.trading_bot.data import load_env_credentials, _fetch_page

OUT = pathlib.Path("/home/anont/meme/research/data/t28_dualclass_cache")
OUT.mkdir(parents=True, exist_ok=True)

PAIRS = [
    ("GOOGL", "GOOG"), ("BRK.A", "BRK.B"), ("FOXA", "FOX"), ("NWSA", "NWS"),
    ("UAA", "UA"), ("LEN", "LEN.B"), ("HEI", "HEI.A"), ("MOG.A", "MOG.B"),
    ("GEF", "GEF.B"), ("CWEN", "CWEN.A"), ("BIO", "BIO.B"), ("CRD.A", "CRD.B"),
    ("HVT", "HVT.A"), ("RUSHA", "RUSHB"), ("BF.A", "BF.B"), ("STZ", "STZ.B"),
    ("PARA", "PARAA"), ("WSO", "WSO.B"), ("GTN", "GTN.A"), ("LGF.A", "LGF.B"),
    ("TAP", "TAP.A"), ("MKC", "MKC.V"), ("CENTA", "CENT"), ("AGM", "AGM.A"),
    ("WLY", "WLYB"), ("JW.A", "JW.B"), ("LBRDA", "LBRDK"), ("LSXMA", "LSXMK"),
    ("FWONA", "FWONK"), ("BATRA", "BATRK"), ("QRTEA", "QRTEB"), ("Z", "ZG"),
    ("UHAL", "UHAL.B"), ("DISCA", "DISCK"), ("VIAC", "VIACA"), ("FCNCA", "FCNCB"),
    ("KELYA", "KELYB"), ("PBR", "PBR.A"), ("CIG", "CIG.C"), ("LILA", "LILAK"),
    ("LTRPA", "LTRPB"), ("VIAB", "VIA"), ("CBS", "CBS.A"), ("DISCB", "DISCA"),
    ("HEIA", "HEI"), ("SNBR", "SNBRX"),
]
SYMS = sorted({s for p in PAIRS for s in p})

START, END = "2016-01-04", "2026-08-18"


def fetch(adjustment):
    key, secret = load_env_credentials()
    out = {}
    token = None
    pages = 0
    chunk = ",".join(SYMS)
    while True:
        params = {"symbols": chunk, "timeframe": "1Day", "start": START, "end": END,
                  "limit": 10000, "feed": "sip", "adjustment": adjustment}
        if token:
            params["page_token"] = token
        p = _fetch_page("/v2/stocks/bars", params, key, secret)
        for sym, bars in (p.get("bars") or {}).items():
            out.setdefault(sym, []).extend(bars)
        pages += 1
        token = p.get("next_page_token")
        if not token:
            break
        if pages > 400:
            raise SystemExit("paging runaway")
    print(adjustment, "pages", pages, "symbols", len(out))
    return out


for adj in ("raw", "all"):
    path = OUT / f"bars_{adj}.json"
    if path.exists():
        print("cached", path)
        continue
    d = fetch(adj)
    path.write_text(json.dumps(d))
    print("wrote", path, sum(len(v) for v in d.values()), "bars")
