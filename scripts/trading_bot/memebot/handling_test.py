"""Evaluator for research/midcap/HANDLING_TEST_PREREGISTRATION.md (sha 874314606b...).

Fixed unconditional entry, fixed handling rules, exact constant-product fills using the
recorded virtual reserves and the recorded fee basis points. Mint-equal metrics, creator- and
session-clustered bootstrap, chronological 60/40 split, single holdout read. Paper only.
"""
import json, math, random, sqlite3, sys, time
from collections import defaultdict

TAPE = "research/midcap/tape_v3.sqlite"
CAP = "research/midcap/birth_stream_forward_v3_20260908T1901.sqlite"
SIZE = 50_000_000            # 0.05 SOL in lamports
TX_FEE = 5_000 + 100_000     # base + priority, per transaction (b15c p50)
RULES = ["H0", "H1", "H2", "H3", "H4", "H5", "H6"]
HORIZONS = {"30m": 1800, "120m": 7200, "end": None}
ENTRIES = ["E1", "E2"]


def bps_of(fields, key, fallback_num, fallback_den):
    v = fields.get(key)
    if isinstance(v, int) and 0 <= v <= 10_000:
        return v
    return int(round(10_000 * fallback_num / fallback_den)) if fallback_den else 0


def buy(vsol, vtok, sol_in, fee_bps, cfee_bps):
    fees = sol_in * (fee_bps + cfee_bps) // 10_000
    net = sol_in - fees
    tok = vtok - (vsol * vtok) // (vsol + net)
    return tok, vsol + net, vtok - tok


def sell(vsol, vtok, tok_in, fee_bps, cfee_bps):
    gross = vsol - (vsol * vtok) // (vtok + tok_in)
    fees = gross * (fee_bps + cfee_bps) // 10_000
    return gross - fees


def load():
    t = sqlite3.connect(f"file:{TAPE}?mode=ro", uri=True)
    c = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    births = {}
    for slot, oj in c.execute("SELECT slot, observation_json FROM create_observation WHERE succeeded=1"):
        f = json.loads(oj)["fields"]
        births.setdefault(f["mint"], (slot, int(f["timestamp"]), f["creator"]))
    done = {}
    for mint, slot in t.execute("SELECT mint, MIN(slot) FROM event WHERE name='CompleteEvent' GROUP BY mint"):
        done[mint] = slot
    tape = defaultdict(list)
    q = ("SELECT mint, slot, ts, vsol, vtok, fee, creator_fee, sol_amount FROM trade "
         "WHERE vsol>0 AND vtok>0 ORDER BY mint, slot, seq, log_index")
    for mint, slot, ts, vsol, vtok, fee, cfee, sol_amt in t.execute(q):
        if mint not in births: continue
        fb = int(round(10_000 * (fee or 0) / sol_amt)) if sol_amt else 95
        cb = int(round(10_000 * (cfee or 0) / sol_amt)) if sol_amt else 30
        tape[mint].append((slot, ts, vsol, vtok, fb, cb))
    return births, done, tape


def simulate(rows, k, done_slot, rule, horizon_s):
    """Enter on state after row k; return net lamports out minus in, or None if unexitable."""
    slot0, ts0, vs, vt, fb, cb = rows[k]
    tok, _, _ = buy(vs, vt, SIZE, fb, cb)
    cost = SIZE + TX_FEE
    p0 = vs / vt
    held = tok; out = 0; txs = 0; peak = p0
    l1 = l2 = l5 = False
    last_idx = None
    for j in range(k + 1, len(rows)):
        slot, ts, vs, vt, fb, cb = rows[j]
        if done_slot is not None and slot >= done_slot: break   # curve completed; no further curve fills
        if horizon_s is not None and ts - ts0 > horizon_s: break
        last_idx = j
        p = vs / vt; peak = max(peak, p)
        def part(frac):
            nonlocal held, out, txs
            q = int(held * frac)
            if q <= 0: return
            out += sell(vs, vt, q, fb, cb); held -= q; txs += 1
        if rule == "H3" and p <= 0.7 * p0: part(1.0); break
        if rule == "H4" and peak >= 1.5 * p0 and p <= 0.6 * peak: part(1.0); break
        if rule in ("H1", "H6"):
            if not l1 and p >= 1.5 * p0: part(1 / 3); l1 = True
            if not l2 and p >= 2.5 * p0: part(0.5); l2 = True    # 33% of original = half of remainder
        if rule == "H5" and not l5 and p >= 2.0 * p0: part(0.5); l5 = True
        if rule in ("H2", "H6") and ts - ts0 >= 600: part(1.0); break
        if held <= 0: break
    if held > 0:
        if last_idx is None: return None                       # nothing observable after entry
        slot, ts, vs, vt, fb, cb = rows[last_idx]
        out += sell(vs, vt, held, fb, cb); txs += 1; held = 0
    return out - cost - txs * TX_FEE


def entry_index(rows, slot0, ts0, entry):
    for i, (slot, ts, *_r) in enumerate(rows):
        if entry == "E1" and slot >= slot0 + 2: return i
        if entry == "E2" and ts >= ts0 + 60: return i
    return None


def boot_ci(vals, groups, n=4000, alpha=0.05, seed=7):
    rng = random.Random(seed)
    by = defaultdict(list)
    for v, g in zip(vals, groups): by[g].append(v)
    keys = list(by); means = []
    for _ in range(n):
        s = [x for k in (rng.choice(keys) for _ in keys) for x in by[k]]
        means.append(sum(s) / len(s))
    means.sort()
    lo = means[int(alpha / 2 * n)]; hi = means[min(n - 1, int((1 - alpha / 2) * n))]
    return lo, hi


def evaluate(mints, births, done, tape, cells, dropout=-1.0, nboot=1000, alpha=0.05):
    res = {}
    for entry, rule, hz in cells:
        vals, cre, ses, drops, ngrad = [], [], [], 0, 0
        for m in mints:
            slot0, ts0, creator = births[m]
            rows = tape.get(m, [])
            k = entry_index(rows, slot0, ts0, entry)
            if k is None: drops += 1; r = dropout
            else:
                net = simulate(rows, k, done.get(m), rule, HORIZONS[hz])
                r = dropout if net is None else net / SIZE
                if net is None: drops += 1
            if m in done: ngrad += 1
            vals.append(r); cre.append(creator); ses.append(ts0 // 1800)
        vals_s = sorted(vals); n = len(vals)
        mean = sum(vals) / n; med = vals_s[n // 2]
        lo1, hi1 = boot_ci(vals, cre, n=nboot, alpha=alpha); lo2, hi2 = boot_ci(vals, ses, n=nboot, alpha=alpha)
        res[(entry, rule, hz)] = dict(n=n, mean=mean, median=med, win=sum(v > 0 for v in vals) / n,
                                      drop=drops, grad=ngrad, ci=(min(lo1, lo2), max(hi1, hi2)))
    return res


def main():
    births, done, tape = load()
    mints = sorted(births, key=lambda m: births[m][0])
    cut = int(len(mints) * 0.6)
    explore, hold = mints[:cut], mints[cut:]
    print(f"population {len(mints)} mints | with trades {sum(1 for m in mints if tape.get(m))} | "
          f"graduated in-window {len(done)} | explore {len(explore)} holdout {len(hold)}", flush=True)
    cells = [(e, r, h) for e in ENTRIES for r in RULES for h in HORIZONS]
    t0 = time.time()
    ex = evaluate(explore, births, done, tape, cells)
    print(f"exploration done in {time.time()-t0:.0f}s\n", flush=True)
    print(f"{'entry':5} {'rule':4} {'hz':5} {'n':>5} {'mean':>8} {'median':>8} {'win%':>5} {'drop':>5} {'ci_lo':>8} {'ci_hi':>8}")
    for key in cells:
        r = ex[key]
        print(f"{key[0]:5} {key[1]:4} {key[2]:5} {r['n']:5d} {r['mean']*100:+7.1f}% {r['median']*100:+7.1f}% "
              f"{r['win']*100:4.0f}% {r['drop']:5d} {r['ci'][0]*100:+7.1f}% {r['ci'][1]*100:+7.1f}%")
    # pre-declared: best exploration cell by mean -> ONE holdout read
    best = max(cells, key=lambda k: ex[k]["mean"])
    h0 = {k: ex[k] for k in cells if k[1] == "H0"}
    print(f"\nBEST exploration cell by mean: {best}  mean {ex[best]['mean']*100:+.2f}%  "
          f"(H0 same entry/hz: {h0[(best[0],'H0',best[2])]['mean']*100:+.2f}%)")
    ho = evaluate(hold, births, done, tape, [best], nboot=20000)[best]
    hob = evaluate(hold, births, done, tape, [best], nboot=20000, alpha=0.05/42)[best]
    ho["ci_bonferroni"] = hob["ci"]
    ho50 = evaluate(hold, births, done, tape, [best], dropout=-0.5, nboot=200)[best]
    ho["mean_dropout50"] = ho50["mean"]
    ex50 = evaluate(explore, births, done, tape, [(best[0], "H0", best[2]), best], dropout=-0.5, nboot=200)
    print(f"\nexploration at -50% dropout: H0 {ex50[(best[0],'H0',best[2])]['mean']*100:+.2f}%  best {ex50[best]['mean']*100:+.2f}%")
    # Bonferroni over 42 cells: need CI at alpha 0.05/42
    vals = []
    print(f"HOLDOUT (single read) {best}: n={ho['n']} mean {ho['mean']*100:+.2f}% median {ho['median']*100:+.2f}% "
          f"win {ho['win']*100:.0f}% drop {ho['drop']} 95%CI [{ho['ci'][0]*100:+.2f}%, {ho['ci'][1]*100:+.2f}%]  "
          f"Bonferroni(0.05/42) CI [{ho['ci_bonferroni'][0]*100:+.2f}%, {ho['ci_bonferroni'][1]*100:+.2f}%]  "
          f"mean@-50%drop {ho['mean_dropout50']*100:+.2f}%")
    out = {"prereg_sha256": "874314606b38aaf0d75869cf3ff454ef6e6ca5c67d609fe2cdd85912fe69ba93",
           "population": len(mints), "explore": {"|".join(k): v for k, v in ex.items()},
           "holdout_cell": "|".join(best), "holdout": ho}
    json.dump(out, open("research/midcap/handling_test_result.json", "w"), indent=1, default=str)
    print("\nwritten research/midcap/handling_test_result.json")


if __name__ == "__main__":
    main()
