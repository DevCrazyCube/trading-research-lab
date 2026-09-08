#!/usr/bin/env python3
"""Smart-money copy study -- DETACHED trade collector (PAPER / READ-ONLY).

Pulls pump.fun DEXTrades from the Bitquery EAP HTTP endpoint (aggregated QUERY, not a
subscription) into a local sqlite cache. NO orders, NO wallet, NO money, NO on-chain writes.

The free EAP archive only serves roughly the last ~4-5 hours of Solana DEXTrades, so this
collects a contiguous recent window that a later analysis step splits into an earlier
IDENTIFICATION sub-window and a later HELD-OUT COPY sub-window.

Pagination: the window is sliced into fixed SLICE_SECONDS chunks; each chunk returns < the
25k row cap (pump.fun runs ~70 trades/s => ~13k per 3 min), so one query captures a whole
chunk with no cursor drift. Slices already present in the cache are skipped (resume). The
public free tier rate-limits hard, so calls are spaced and 429s get exponential backoff.

Usage: collect_trades.py <START_ISO> <END_ISO> [slice_seconds]
"""
from __future__ import annotations
import json, os, pathlib, sqlite3, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV = ROOT / ".env"
CACHE = ROOT / "research" / "data" / "smartmoney_cache" / "trades.sqlite"
LOG = ROOT / "research" / "data" / "smartmoney_cache" / "collect.log"
URL = "https://streaming.bitquery.io/eap"
SOL = {"11111111111111111111111111111111", "So11111111111111111111111111111111111111112"}
SLICE_CAP = 25000
MIN_SPACING = 5.0  # seconds between successful calls

def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    with open(LOG, "a") as fh: fh.write(line + "\n")
    print(line, flush=True)

def token():
    for l in ENV.read_text().splitlines():
        if l.strip().startswith("BITQUERY_API="):
            return l.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no BITQUERY_API")

def db():
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(CACHE)
    c.execute("""CREATE TABLE IF NOT EXISTS trade(
        signature TEXT, slot INTEGER, ts INTEGER, wallet TEXT, mint TEXT,
        side TEXT, token_amount REAL, usd REAL, price_usd REAL,
        PRIMARY KEY(signature, mint, side, wallet))""")
    c.execute("CREATE INDEX IF NOT EXISTS trade_mint_ts ON trade(mint, ts)")
    c.execute("CREATE INDEX IF NOT EXISTS trade_wallet ON trade(wallet)")
    c.execute("CREATE TABLE IF NOT EXISTS slice_done(a TEXT, b TEXT, n INTEGER, PRIMARY KEY(a,b))")
    c.commit()
    return c

def run_query(tok, q, tries=8):
    body = json.dumps({"query": q}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(URL, data=body,
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + tok})
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 8 * (i + 1); log(f"429 backoff {wait}s"); time.sleep(wait); continue
            log(f"HTTP {e.code}: {e.read().decode()[:200]}"); raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            wait = 5 * (i + 1); log(f"neterr {type(e).__name__} backoff {wait}s"); time.sleep(wait); continue
    raise RuntimeError("exhausted retries")

QTMPL = """{ Solana { DEXTrades(
  limit: {count: %d}, orderBy: {ascending: Block_Time},
  where: {Trade: {Dex: {ProtocolFamily: {is: "Pumpfun"}}}, Block: {Time: {after: "%s", before: "%s"}}}) {
  Block { Time Slot } Transaction { Signer }
  Trade { Buy {Amount AmountInUSD PriceInUSD Currency{MintAddress}}
          Sell {Amount AmountInUSD PriceInUSD Currency{MintAddress}} } } } }"""

def parse(rows):
    out = []
    for t in rows:
        try:
            sig = t["Transaction"]["Signer"]  # trader identity (fee payer / initiator)
            slot = int(t["Block"]["Slot"])
            ts = int(datetime.strptime(t["Block"]["Time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
            b, s = t["Trade"]["Buy"], t["Trade"]["Sell"]
            bm, sm = b["Currency"]["MintAddress"], s["Currency"]["MintAddress"]
            if bm not in SOL and sm in SOL:      # token acquired, SOL spent -> BUY
                side, mint, tok_amt = "buy", bm, float(b["Amount"] or 0)
                usd, price = float(s["AmountInUSD"] or 0), float(b["PriceInUSD"] or 0)
            elif sm not in SOL and bm in SOL:    # token given up, SOL received -> SELL
                side, mint, tok_amt = "sell", sm, float(s["Amount"] or 0)
                usd, price = float(b["AmountInUSD"] or 0), float(s["PriceInUSD"] or 0)
            else:
                continue  # token-token or SOL-SOL, not a memecoin cash trade
            # signature is not returned to save points; synthesize a per-row id from slot+wallet+mint+amounts
            rid = f"{slot}:{sig[:8]}:{mint[:8]}:{tok_amt:.3f}:{usd:.4f}"
            out.append((rid, slot, ts, sig, mint, side, tok_amt, usd, price))
        except (KeyError, TypeError, ValueError):
            continue
    return out

def main():
    start = sys.argv[1]; end = sys.argv[2]
    slice_s = int(sys.argv[3]) if len(sys.argv) > 3 else 180
    tok = token(); conn = db()
    t0 = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    t1 = datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    slices = []
    t = t0
    while t < t1:
        nxt = min(t + timedelta(seconds=slice_s), t1)
        slices.append((t.strftime("%Y-%m-%dT%H:%M:%SZ"), nxt.strftime("%Y-%m-%dT%H:%M:%SZ")))
        t = nxt
    log(f"START collect {start}..{end} slice={slice_s}s slices={len(slices)}")
    done = {(a, b) for a, b in conn.execute("SELECT a,b FROM slice_done")}
    total = 0
    for i, (a, b) in enumerate(slices):
        if (a, b) in done:
            continue
        r = run_query(tok, QTMPL % (SLICE_CAP, a, b))
        rows = (r.get("data") or {}).get("Solana", {}).get("DEXTrades") or []
        if len(rows) >= SLICE_CAP:
            log(f"WARN slice {a} hit cap {SLICE_CAP}; subdividing")
            # subdivide this slice into 3 and process recursively via smaller queries
            sub0 = datetime.strptime(a, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            sub1 = datetime.strptime(b, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            step = (sub1 - sub0) / 3
            allrows = []
            for k in range(3):
                sa = (sub0 + step * k).strftime("%Y-%m-%dT%H:%M:%SZ")
                sb = (sub0 + step * (k + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                time.sleep(MIN_SPACING)
                rr = run_query(tok, QTMPL % (SLICE_CAP, sa, sb))
                allrows += (rr.get("data") or {}).get("Solana", {}).get("DEXTrades") or []
            rows = allrows
        recs = parse(rows)
        conn.executemany("INSERT OR IGNORE INTO trade VALUES (?,?,?,?,?,?,?,?,?)", recs)
        conn.execute("INSERT OR REPLACE INTO slice_done VALUES (?,?,?)", (a, b, len(recs)))
        conn.commit()
        total += len(recs)
        log(f"slice {i+1}/{len(slices)} {a} rows={len(rows)} kept={len(recs)} cum={total}")
        time.sleep(MIN_SPACING)
    n = conn.execute("SELECT COUNT(*) FROM trade").fetchone()[0]
    log(f"DONE collect. distinct trade rows in cache={n}")

if __name__ == "__main__":
    main()
