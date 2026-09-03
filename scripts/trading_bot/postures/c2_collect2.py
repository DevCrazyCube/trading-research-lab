"""POSTURE C2 collector part 2: ECB survivorship-complete FX + Yahoo country panels."""
import datetime
import json
import os

import numpy as np

import c2_collect as C

ROOT = "/home/anont/meme"
CACHE = os.path.join(ROOT, "research/data/c2_cache")

# Currencies the ECB no longer publishes: euro-absorbed (fixed conversion, holder
# lost nothing) or suspended (RUB, 2022 - holder faced an unhedgeable stop).
DEAD = {"EEK", "LTL", "LVL", "SKK", "CYP", "MTL", "SIT", "HRK", "RUB"}
EM_SET = {"BRL", "CNY", "CZK", "HKD", "HUF", "IDR", "ILS", "INR", "KRW", "MXN",
          "MYR", "PHP", "PLN", "RON", "THB", "TRY", "ZAR", "SGD", "TWD",
          "EEK", "LTL", "LVL", "SKK", "CYP", "SIT", "HRK", "RUB", "BGN", "ISK"}
DM_SET = {"USD", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD", "SEK", "NOK", "DKK"}


def read_ecb(paths):
    """-> dict ccy -> (dates yyyymmdd, EUR-per-... inverted to 'value of 1 unit')."""
    raw = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p) as f:
            hdr = f.readline().strip().split(",")
            ic = hdr.index("CURRENCY")
            it = hdr.index("TIME_PERIOD")
            iv = hdr.index("OBS_VALUE")
            for line in f:
                fl = line.strip().split(",")
                if len(fl) <= iv:
                    continue
                ccy, t, v = fl[ic], fl[it], fl[iv].strip()
                if not v or v in ("NaN", "."):
                    continue
                try:
                    val = float(v)
                except ValueError:
                    continue
                if val <= 0:
                    continue
                raw.setdefault(ccy, []).append(
                    (int(t.replace("-", "")), val))
    out = {}
    for ccy, rows in raw.items():
        rows.sort()
        d = np.array([r[0] for r in rows], dtype=np.int64)
        # ECB quotes units of FX per 1 EUR -> invert so a rise = FX appreciates
        v = 1.0 / np.array([r[1] for r in rows], dtype=float)
        out[ccy] = (d, v)
    return out


def yload(sym):
    p = os.path.join(CACHE, "yraw", sym.replace("/", "_") + ".json")
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p))["chart"]["result"][0]
    except Exception:
        return None
    ts = d.get("timestamp")
    if not ts:
        return None
    ind = d["indicators"]
    px = None
    if "adjclose" in ind and ind["adjclose"] and ind["adjclose"][0].get("adjclose"):
        px = ind["adjclose"][0]["adjclose"]
    if px is None:
        px = ind["quote"][0]["close"]
    ds, vs = [], []
    for t, p_ in zip(ts, px):
        if p_ is None or p_ <= 0:
            continue
        dt = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
        ds.append(dt.year * 10000 + dt.month * 100 + dt.day)
        vs.append(float(p_))
    if len(ds) < 100:
        return None
    return np.array(ds, dtype=np.int64), np.array(vs, dtype=float)


def main():
    ecb = read_ecb([os.path.join(CACHE, "ecb", "all.csv"),
                    os.path.join(CACHE, "ecb", "dead.csv")])
    print("ECB currencies: %d  (%s)" % (len(ecb), " ".join(sorted(ecb))))
    dead_have = sorted(set(ecb) & DEAD)
    print("  discontinued present: %s" % " ".join(dead_have))

    em = {k: v for k, v in ecb.items()
          if k not in DM_SET and k != "CURRENCY"}
    dm = {k: v for k, v in ecb.items() if k in DM_SET}
    if em:
        C.save(C.build_panel(em, "ecb_fx_em"))
    if dm:
        C.save(C.build_panel(dm, "ecb_fx_dm"))
    if ecb:
        C.save(C.build_panel({k: v for k, v in ecb.items() if k != "CURRENCY"},
                             "ecb_fx_all"))

    import c2_yfetch as Y
    for names, tag in ((Y.IDX, "country_idx"), (Y.ETF, "country_etf")):
        mem = {}
        for s in names:
            r = yload(s)
            if r is None:
                print("  MISS %s" % s)
                continue
            mem[s.replace("^", "")] = r
        if mem:
            C.save(C.build_panel(mem, tag))


if __name__ == "__main__":
    main()
