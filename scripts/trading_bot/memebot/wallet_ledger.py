"""Reconstruct the owner's true fill history from ERC-20 Transfer logs.

The FOMO /swaps endpoint is capped at 100 fills with no cursor, and a visible BUY
there does not mean the ENTRY is visible: 10 of 37 mints carried unexplained opening
inventory. Chain logs are the only complete record.

The wallet is an EIP-7702 delegated EOA (code = 0xef0100 || delegate), so its own
nonce is 1 and a sender-based tx listing finds nothing. Transfers must be found by
scanning Transfer logs with the wallet in either indexed address topic.

Read-only. No key, no signing, no order path.
"""
import json, os, sqlite3, sys, time, urllib.request

RPCS = {
    4663: "https://rpc.mainnet.chain.robinhood.com",
    56:   "https://bsc-dataseed.bnbchain.org",
}
WALLET = "0x5cf2c0b7fe6e3a51e031d118893714ef4a90bb23".lower()
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
PAD = "0x" + "0" * 24 + WALLET[2:]
OUT = os.path.join(os.path.dirname(__file__), "wallet_ledger.sqlite")
SPAN, MIN_SPAN, PACE = 50_000, 2_000, 0.35


def rpc(url, method, params, tries=6):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    delay = 1.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers={"content-type": "application/json", "User-Agent": "Mozilla/5.0"})
            d = json.loads(urllib.request.urlopen(req, timeout=45).read())
            if "error" in d:
                raise RuntimeError(d["error"])
            return d["result"]
        except Exception as exc:
            if attempt == tries - 1:
                raise
            print(f"  retry {attempt+1}: {str(exc)[:90]}", flush=True)
            time.sleep(delay)
            delay = min(30.0, delay * 2)


def db_open():
    db = sqlite3.connect(OUT)
    db.execute("""CREATE TABLE IF NOT EXISTS transfer(
        chain INT, block INT, tx TEXT, logidx INT, token TEXT,
        sender TEXT, recipient TEXT, raw TEXT, PRIMARY KEY(chain, tx, logidx))""")
    db.execute("CREATE TABLE IF NOT EXISTS progress(chain INT, lo INT, hi INT, PRIMARY KEY(chain, lo))")
    db.commit()
    return db


def scan(db, chain, first_block, last_block):
    url = RPCS[chain]
    done = {r[0]: r[1] for r in db.execute("SELECT lo, hi FROM progress WHERE chain=?", (chain,))}
    lo, span, found = first_block, SPAN, 0
    while lo <= last_block:
        if lo in done:
            lo = done[lo] + 1
            continue
        hi = min(lo + span - 1, last_block)
        try:
            logs = []
            for pos in (1, 2):          # wallet as sender, then as recipient
                topics = [TRANSFER, None, None]
                topics[pos] = PAD
                logs += rpc(url, "eth_getLogs",
                            [{"fromBlock": hex(lo), "toBlock": hex(hi), "topics": topics}])
        except Exception as exc:
            if span > MIN_SPAN:
                span = max(MIN_SPAN, span // 4)
                print(f"  narrowing to {span}: {str(exc)[:70]}", flush=True)
                continue
            raise
        for g in logs:
            t = g["topics"]
            if len(t) < 3:
                continue
            db.execute("INSERT OR IGNORE INTO transfer VALUES(?,?,?,?,?,?,?,?)",
                       (chain, int(g["blockNumber"], 16), g["transactionHash"],
                        int(g["logIndex"], 16), g["address"].lower(),
                        "0x" + t[1][-40:], "0x" + t[2][-40:], json.dumps(g)))
        found += len(logs)
        db.execute("INSERT OR REPLACE INTO progress VALUES(?,?,?)", (chain, lo, hi))
        db.commit()
        pct = (hi - first_block) / max(1, last_block - first_block) * 100
        print(f"chain {chain} {lo}-{hi} ({pct:5.1f}%) +{len(logs)} total {found}", flush=True)
        lo = hi + 1
        span = min(SPAN, span * 2)
        time.sleep(PACE)
    return found


if __name__ == "__main__":
    days = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    db = db_open()
    for chain, secs_per_block in ((4663, 0.101), (56, 3.0)):
        head = int(rpc(RPCS[chain], "eth_blockNumber", []), 16)
        back = int(days * 86400 / secs_per_block)
        start = max(0, head - back)
        print(f"=== chain {chain}: blocks {start}..{head} ({days}d) ===", flush=True)
        try:
            n = scan(db, chain, start, head)
            print(f"=== chain {chain} done, {n} transfer logs ===", flush=True)
        except Exception as exc:
            print(f"=== chain {chain} ABORTED: {exc} ===", flush=True)
    print("TOTAL", db.execute("SELECT count(*) FROM transfer").fetchone()[0], flush=True)
