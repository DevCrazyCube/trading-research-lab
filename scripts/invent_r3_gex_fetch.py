#!/usr/bin/env python3
"""INVENT-R3 dealer-positioning: build a free per-strike SPY option-activity cache.

Alpaca serves expired OPRA option daily bars from ~2024-02-01. There is NO free
open-interest history anywhere, so this builds the closest free substitute:
per-contract DAILY VOLUME, accumulated from listing, per expiry, near the money.

For each expiry E (every SPY trading day in the window -- SPY lists daily expiries),
fetch daily bars for strikes round(S_{E-6}) +/- STRIKE_HALFWIDTH, calls and puts,
over [E-9 calendar days, E]. That yields, for any observation day t <= E, the
cumulative traded volume by strike for that expiry -- an OI proxy.

Writes one JSON per expiry to research/data/gex_cache/exp/<YYYY-MM-DD>.json
Idempotent: skips expiries already on disk.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

ROOT = "/home/anont/meme"
CACHE = os.path.join(ROOT, "research/data/gex_cache")
EXPD = os.path.join(CACHE, "exp")
STRIKE_HALFWIDTH = 15  # +/- $15 in $1 steps -> 31 strikes -> 62 contracts
BATCH = 31
START = "2024-02-01"


def creds():
    env = {}
    for line in open(os.path.join(ROOT, ".env")):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    return {
        "APCA-API-KEY-ID": env["ALPACA_API_KEY_ID"],
        "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET_KEY"],
    }


H = creds()


def get(url, params, tries=6):
    u = url + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            r = urllib.request.Request(u, headers=H)
            return json.load(urllib.request.urlopen(r, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** i)
                continue
            raise
        except Exception:
            time.sleep(2 ** i)
    raise RuntimeError("give up: " + u[:200])


def spy_daily():
    p = os.path.join(CACHE, "spy_daily.json")
    if os.path.exists(p):
        return json.load(open(p))
    out, tok = [], None
    while True:
        q = {
            "symbols": "SPY", "timeframe": "1Day", "start": "2015-12-01",
            "end": "2026-08-19", "limit": 10000, "adjustment": "raw",
        }
        if tok:
            q["page_token"] = tok
        d = get("https://data.alpaca.markets/v2/stocks/bars", q)
        out += d["bars"].get("SPY", [])
        tok = d.get("next_page_token")
        if not tok:
            break
    json.dump(out, open(p, "w"))
    return out


def occ(exp: date, cp: str, strike: int) -> str:
    return f"SPY{exp:%y%m%d}{cp}{strike * 1000:08d}"


def main():
    os.makedirs(EXPD, exist_ok=True)
    bars = spy_daily()
    days = [(b["t"][:10], b["c"]) for b in bars]
    idx = {d: i for i, (d, _) in enumerate(days)}
    todo = [d for d, _ in days if d >= START]
    print(f"{len(todo)} expiries to consider", flush=True)
    done = 0
    for n, ed in enumerate(todo):
        out_p = os.path.join(EXPD, ed + ".json")
        if os.path.exists(out_p):
            continue
        i = idx[ed]
        ref = days[max(0, i - 6)][1]
        k0 = int(round(ref))
        strikes = list(range(k0 - STRIKE_HALFWIDTH, k0 + STRIKE_HALFWIDTH + 1))
        syms = [occ(date.fromisoformat(ed), cp, k) for k in strikes for cp in "CP"]
        st = (date.fromisoformat(ed) - timedelta(days=12)).isoformat()
        rec = {}
        for j in range(0, len(syms), BATCH):
            chunk = syms[j:j + BATCH]
            tok = None
            while True:
                q = {
                    "symbols": ",".join(chunk), "timeframe": "1Day",
                    "start": st, "end": ed, "limit": 10000, "sort": "asc",
                }
                if tok:
                    q["page_token"] = tok
                d = get("https://data.alpaca.markets/v1beta1/options/bars", q)
                for s, bs in (d.get("bars") or {}).items():
                    rec.setdefault(s, []).extend(
                        [[b["t"][:10], b["v"], b["c"], b["o"], b["h"], b["l"]] for b in bs]
                    )
                tok = d.get("next_page_token")
                if not tok:
                    break
        json.dump({"expiry": ed, "ref": ref, "bars": rec}, open(out_p, "w"))
        done += 1
        if done % 25 == 0:
            print(f"{n+1}/{len(todo)} {ed} contracts={len(rec)}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
