"""Signatures per curve INSIDE the observation window, which is what b9c actually inventories."""
import importlib.util, json, pathlib, random, sqlite3, statistics, sys, urllib.request, urllib.error
ROOT = pathlib.Path("/home/anont/meme")
probe = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("probe", pathlib.Path(__file__).parent / "rate_probe.py"))
probe.__spec__.loader.exec_module(probe)
CUTOFF = 437_211_659
SAMPLE = int(sys.argv[1])
url = probe.endpoint()
db = sqlite3.connect(f"file:{ROOT}/research/b11a/b11a_cohort.sqlite?mode=ro", uri=True)
curves = [(r[0], r[1]) for r in db.execute("SELECT bonding_curve, launch_slot FROM cohort_identity")]
db.close()
random.seed(23)
picked = random.sample(curves, SAMPLE)
print(f"sampling {SAMPLE} of {len(curves):,}, counting ONLY slots <= cutoff {CUTOFF:,}\n")

def windowed(address):
    total, in_window, before, pages = 0, 0, None, 0
    while pages < 15:
        params = [address, {"limit": 1000, **({"before": before} if before else {})}]
        body = json.dumps({"jsonrpc":"2.0","id":1,"method":"getSignaturesForAddress","params":params}).encode()
        try:
            with urllib.request.urlopen(probe.HTTP.json_rpc_request(url, body), timeout=30) as r:
                rows = (json.loads(r.read()).get("result") or [])
        except urllib.error.HTTPError as e:
            return None, None, f"HTTP {e.code}"
        total += len(rows); pages += 1
        in_window += sum(1 for x in rows if x.get("slot", 0) <= CUTOFF)
        if len(rows) < 1000: return total, in_window, pages
        before = rows[-1]["signature"]
    return total, in_window, pages

allc, winc, pagec = [], [], []
for i, (addr, _) in enumerate(picked, 1):
    t, w, p = windowed(addr)
    if t is None: print("  ABORT", p); break
    allc.append(t); winc.append(w); pagec.append(p if isinstance(p, int) else 15)
    if i % 20 == 0: print(f"  {i}/{SAMPLE}, running windowed mean {statistics.mean(winc):.0f}")

w = sorted(winc)
mean_w = statistics.mean(winc)
print(f"\nIN-WINDOW SIGNATURES PER CURVE ({len(w)} sampled):")
print(f"  min {w[0]}  p25 {w[len(w)//4]}  MEDIAN {statistics.median(w):.0f}  p75 {w[3*len(w)//4]}  max {w[-1]}")
print(f"  MEAN {mean_w:.1f}   (all-time mean was {statistics.mean(allc):.1f})")
proj = mean_w * 33866
se = statistics.stdev(winc)/ (len(w) ** 0.5) if len(w) > 1 else 0
print(f"\nPROJECTED in-window signatures: {proj:,.0f}   (+/- {se*33866:,.0f} one standard error)")
print(f"STAGE 4 pages to fetch: ~{statistics.mean(pagec)*33866:,.0f}")
for label, rate in (("serial 5.85/s", 5.85), ("4 workers 13.76/s", 13.76)):
    print(f"  stage 5 at {label:20} {proj/rate/86400:6.1f} days")
pathlib.Path(sys.argv[2]).write_text(json.dumps(
    {"sampled": len(w), "windowed_mean": mean_w, "windowed_median": statistics.median(w),
     "alltime_mean": statistics.mean(allc), "projected": proj, "stderr_projected": se*33866,
     "mean_pages": statistics.mean(pagec)}, indent=2)+"\n")
