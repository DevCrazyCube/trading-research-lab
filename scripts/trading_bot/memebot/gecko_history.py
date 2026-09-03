"""Fetch minute OHLCV for the survivorship-free b11a graduate cohort.

Universe = every `complete=1` mint in research/b11a/window_labels.sqlite. That window was
enumerated from chain, so it includes graduates that subsequently died -- no survivorship.
Resumable; paced for the GeckoTerminal free tier. Detached crawl, never inline.
"""
from __future__ import annotations
import json, sqlite3, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "research" / "b11a" / "window_labels.sqlite"
OUT = ROOT / "research" / "midcap" / "grad_ohlcv.sqlite"
B = "https://api.geckoterminal.com/api/v2"
PACE = 2.6

def db():
    c = sqlite3.connect(OUT)
    c.execute("""create table if not exists ohlcv(
        mint text primary key, pool text, n_bars int, first_ts int, last_ts int,
        bars_json text, fetched_at int, status text)""")
    c.commit(); return c

def get(u, tries=4):
    for i in range(tries):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0",
                                                 "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(10 + 5 * i); continue
            return e.code, None
        except Exception:
            time.sleep(3); continue
    return 429, None

def main():
    lab = sqlite3.connect(LABELS)
    rows = lab.execute("select mint, block_time from window_label "
                       "where complete=1 and mint is not null").fetchall()
    c = db()
    done = {m for (m,) in c.execute("select mint from ohlcv")}
    todo = [(m, bt) for m, bt in rows if m not in done]
    print(f"{len(rows)} graduates, {len(done)} already fetched, {len(todo)} to go", flush=True)
    ok = 0
    for i, (mint, bt) in enumerate(todo):
        st, d = get(f"{B}/networks/solana/tokens/{mint}/pools?page=1"); time.sleep(PACE)
        pools = (d or {}).get("data") or []
        if not pools:
            c.execute("insert or replace into ohlcv values(?,?,?,?,?,?,?,?)",
                      (mint, None, 0, None, None, None, int(time.time()), f"nopool:{st}"))
            c.commit(); continue
        addr = pools[0]["attributes"]["address"]
        before = int(bt) + 86400 if bt else int(time.time())
        st2, d2 = get(f"{B}/networks/solana/pools/{addr}/ohlcv/minute"
                      f"?aggregate=1&limit=1000&before_timestamp={before}")
        time.sleep(PACE)
        bars = (d2 or {}).get("data", {}).get("attributes", {}).get("ohlcv_list") or []
        c.execute("insert or replace into ohlcv values(?,?,?,?,?,?,?,?)",
                  (mint, addr, len(bars),
                   bars[-1][0] if bars else None, bars[0][0] if bars else None,
                   json.dumps(bars) if bars else None, int(time.time()),
                   "ok" if bars else f"nobars:{st2}"))
        c.commit()
        if bars: ok += 1
        if i % 25 == 0:
            print(f"[{time.strftime('%H:%M:%S')}] {i}/{len(todo)}  with-bars={ok}", flush=True)
    print(f"DONE. {ok} mints with bars.", flush=True)

if __name__ == "__main__":
    main()
