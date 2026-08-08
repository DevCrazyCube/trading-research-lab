"""How many signatures does a REAL B11a curve actually have? Sampled, not extrapolated.

The 2.8M-call figure scales the burned study's 94,985 signatures over 1,601 curves -- 59 per curve
-- to 33,866. But B11a enumerated EVERY create in a 24h window, and most pump.fun launches barely
trade. If the true mean is far lower the whole stage-5 estimate collapses. This asks the chain.
"""
import importlib.util, json, pathlib, random, sqlite3, statistics, sys, urllib.request, urllib.error

ROOT = pathlib.Path("/home/anont/meme")
probe = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("probe", pathlib.Path(__file__).parent / "rate_probe.py"))
probe.__spec__.loader.exec_module(probe)

SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 40
url = probe.endpoint()

db = sqlite3.connect(f"file:{ROOT}/research/b11a/b11a_cohort.sqlite?mode=ro", uri=True)
curves = [r[0] for r in db.execute("SELECT bonding_curve FROM cohort_identity")]
db.close()
random.seed(11)                       # fixed seed: a rerun samples the same curves
picked = random.sample(curves, SAMPLE)
print(f"population {len(curves):,} curves; sampling {SAMPLE} at random (seed fixed)\n")

def count(address):
    """Signatures for one curve, paging like b9c does, capped so one whale cannot dominate."""
    total, before, pages = 0, None, 0
    while pages < 10:
        params = [address, {"limit": 1000, **({"before": before} if before else {})}]
        body = json.dumps({"jsonrpc":"2.0","id":1,"method":"getSignaturesForAddress",
                           "params": params}).encode()
        try:
            with urllib.request.urlopen(probe.HTTP.json_rpc_request(url, body), timeout=30) as r:
                payload = json.loads(r.read())
        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}"
        rows = payload.get("result") or []
        total += len(rows); pages += 1
        if len(rows) < 1000:
            return total, None
        before = rows[-1]["signature"]
    return total, "capped at 10 pages"

counts, notes = [], []
for i, address in enumerate(picked, 1):
    n, note = count(address)
    if n is None:
        print(f"  ABORT on {note}"); break
    counts.append(n)
    if note: notes.append(note)
    if i % 10 == 0:
        print(f"  {i}/{SAMPLE} sampled, running mean {statistics.mean(counts):.1f}")

counts.sort()
mean = statistics.mean(counts)
print(f"\nSIGNATURES PER CURVE over {len(counts)} sampled:")
print(f"  min {counts[0]}   p25 {counts[len(counts)//4]}   MEDIAN {statistics.median(counts):.0f}"
      f"   p75 {counts[3*len(counts)//4]}   max {counts[-1]}")
print(f"  MEAN {mean:.1f}   (burned study's implied mean was 59.3)")
print(f"  zero-or-one-signature curves: {sum(1 for c in counts if c <= 1)}/{len(counts)}")
projected = mean * 33866
print(f"\nPROJECTED total signatures for 33,866 curves: {projected:,.0f}")
print(f"  vs the linear extrapolation from the burned study: 2,009,220")
for label, rate in (("serial 5.85/s", 5.85), ("4 workers 13.76/s", 13.76)):
    print(f"  stage 5 at {label:20} {projected/rate/3600:6.1f} hours ({projected/rate/86400:.1f} days)")
pathlib.Path(sys.argv[2]).write_text(json.dumps(
    {"sampled": len(counts), "mean": mean, "median": statistics.median(counts),
     "counts": counts, "projected_signatures": projected, "notes": notes}, indent=2)+"\n")
