"""Rate-limited Yahoo daily fetcher for C2 country cross-sections.

Run DETACHED (nohup ... &). Free, keyless. One request every SLEEP seconds.
Writes raw chart JSON into research/data/c2_cache/yraw/.
"""
import json
import os
import subprocess
import sys
import time

OUT = "/home/anont/meme/research/data/c2_cache/yraw"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
SLEEP = 4.0

IDX = ["^GSPC", "^GDAXI", "^FTSE", "^FCHI", "^IBEX", "^SSMI", "^AEX", "^OMX",
       "^ATX", "^BFX", "FTSEMIB.MI", "PSI20.LS", "^OSEAX", "^OMXC25",
       "^N225", "^HSI", "^KS11", "^TWII", "^STI", "^AXJO", "^NZ50", "^JKSE",
       "^KLSE", "^BSESN", "^NSEI", "^GSPTSE", "^BVSP", "^MXX", "^IPSA",
       "^MERV", "XU100.IS", "^TA125.TA", "^STOXX50E", "^SET.BK", "^VN30",
       "IMOEX.ME", "^CASE30", "WIG20.WA", "^BUX.BD", "^JN0U.JO"]

ETF = ["EWA", "EWC", "EWD", "EWG", "EWH", "EWI", "EWJ", "EWK", "EWL", "EWM",
       "EWN", "EWO", "EWP", "EWQ", "EWS", "EWT", "EWU", "EWW", "EWY", "EWZ",
       "EZA", "EIS", "EIRL", "EPU", "ECH", "EPHE", "THD", "TUR", "INDA",
       "EIDO", "ARGT", "GREK", "NORW", "EDEN", "EFNL", "EPOL", "QAT", "KSA",
       "UAE", "VNM", "NGE", "EGPT", "RSX", "GXG", "ENZL", "PAK", "KWT"]


def one(sym):
    p = os.path.join(OUT, sym.replace("/", "_") + ".json")
    if os.path.exists(p) and os.path.getsize(p) > 500:
        return "cached"
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/"
           + sym.replace("^", "%5E")
           + "?period1=-2208988800&period2=2000000000&interval=1d"
             "&includeAdjustedClose=true")
    for i in range(3):
        r = subprocess.run(["curl", "-sS", "--max-time", "60", "-A", UA, url],
                           capture_output=True, timeout=90)
        b = r.stdout.decode("utf-8", "replace")
        if b.startswith("{") and '"result":[{' in b:
            open(p, "w").write(b)
            try:
                d = json.loads(b)["chart"]["result"][0]
                return "ok n=%d" % len(d.get("timestamp") or [])
            except Exception:
                return "ok"
        time.sleep(10 + 20 * i)
    return "FAIL " + b[:80].replace("\n", " ")


def main():
    os.makedirs(OUT, exist_ok=True)
    for s in IDX + ETF:
        st = one(s)
        print("%-14s %s" % (s, st), flush=True)
        if st != "cached":
            time.sleep(SLEEP)


if __name__ == "__main__":
    main()
