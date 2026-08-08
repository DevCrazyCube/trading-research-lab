"""What does a FULL block actually cost in bytes? The calls-vs-bytes question, measured.

getBlock-per-slot is ~26x fewer calls than getTransaction-per-signature for the full cohort. That
is a fact about CALLS. It says nothing about bytes or request units, and a full block carries every
transaction in it -- almost none of which belong to our curves. Five blocks settles the magnitude.
"""
import importlib.util, json, pathlib, statistics, sys, urllib.request, urllib.error
ROOT = pathlib.Path("/home/anont/meme")
probe = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("probe", pathlib.Path(__file__).parent / "rate_probe.py"))
probe.__spec__.loader.exec_module(probe)
url = probe.endpoint()

# Slots spread across the observation window, including its far end (archival retention check).
SLOTS = [435_569_200, 435_772_700, 436_100_000, 436_800_000, 437_211_000]

def fetch(slot, detail):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"getBlock","params":[slot, {
        "commitment":"finalized","transactionDetails":detail,"rewards":False,
        "maxSupportedTransactionVersion":0}]}).encode()
    try:
        with urllib.request.urlopen(probe.HTTP.json_rpc_request(url, body), timeout=60) as r:
            raw = r.read()
        payload = json.loads(raw)
        if "error" in payload:
            return None, payload["error"].get("message", "")[:90], len(raw)
        result = payload.get("result")
        if result is None:
            return 0, "skipped slot (null result)", len(raw)
        n = len(result.get("transactions", result.get("signatures", [])))
        return n, None, len(raw)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}", 0

print(f"endpoint {probe.HTTP.endpoint_identity(url)}\n")
rows = []
for detail in ("signatures", "full"):
    print(f"--- transactionDetails={detail!r} ---")
    sizes, counts = [], []
    for slot in SLOTS:
        n, err, size = fetch(slot, detail)
        if n is None:
            print(f"   slot {slot:,}: REFUSED -- {err}")
            continue
        sizes.append(size); counts.append(n)
        print(f"   slot {slot:,}: {n:>5} txns, {size/1024:>9,.0f} KiB")
    if sizes:
        rows.append((detail, statistics.mean(sizes), statistics.mean(counts)))
        print(f"   mean {statistics.mean(sizes)/1024:,.0f} KiB over {len(sizes)} blocks\n")

SPAN = 1_642_510
print("PROJECTED OVER THE 1,642,510-SLOT OBSERVATION WINDOW:")
for detail, mean_bytes, mean_txns in rows:
    tb = mean_bytes * SPAN / 1024**4
    print(f"   {detail:11} {mean_bytes/1024:>8,.0f} KiB/block -> {tb:6.2f} TB, ~{mean_txns:,.0f} txns/block")
pathlib.Path(sys.argv[1]).write_text(json.dumps(
    {"slots": SLOTS, "rows": [{"detail": d, "mean_bytes": b, "mean_txns": t} for d, b, t in rows],
     "span": SPAN}, indent=2) + "\n")
