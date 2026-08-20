#!/usr/bin/env python3
"""Live Alpaca /v2/assets snapshot: shortable + easy_to_borrow for the US legs.
A LIVE snapshot is an executability bound applied FORWARD; it is not a point-in-time
history of borrow status and the result file says so."""
import json, pathlib, sys, time, urllib.request
sys.path.insert(0, "/home/anont/meme")
from scripts.trading_bot.data import load_env_credentials
from scripts.t29_crosslist.xl_universe import US_SYMBOLS, COUNTRY_ETF
from datetime import datetime, timezone

OUT = pathlib.Path("/home/anont/meme/research/data/t29_crosslist_cache/etb_flags.json")
key, secret = load_env_credentials()
H = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
flags = {}
syms = US_SYMBOLS + sorted(set(COUNTRY_ETF.values()))
for s in syms:
    try:
        r = urllib.request.Request(
            f"https://paper-api.alpaca.markets/v2/assets/{s.replace('.', '.')}", headers=H)
        d = json.loads(urllib.request.urlopen(r, timeout=20).read())
        flags[s] = {"tradable": d.get("tradable"), "shortable": d.get("shortable"),
                    "easy_to_borrow": d.get("easy_to_borrow"),
                    "exchange": d.get("exchange"), "status": d.get("status")}
    except Exception:
        flags[s] = None
    time.sleep(0.05)
OUT.write_text(json.dumps({"_captured_utc": datetime.now(timezone.utc).isoformat(),
                           "_source": "Alpaca /v2/assets live snapshot",
                           "flags": flags}, indent=1))
ok = sum(1 for v in flags.values() if v)
etb = sum(1 for v in flags.values() if v and v.get("easy_to_borrow"))
print("resolved", ok, "/", len(syms), " ETB:", etb)
