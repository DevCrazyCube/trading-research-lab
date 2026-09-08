# B20B — the deadness screen: the one finding that cleared the full bar

**Status.** Leakage-free observation on burned window-1 data. **Not a preregistered result, not an
edge, and not fraud detection.** It is a defensive entry filter, and it is the only thing in this
programme — across the memecoin thread, the minute-trading thread, and the rug-detector thread —
that survived every requirement in [B20A](B20A_LEAKAGE_AUDIT_CRITERIA.md).

**Verified by both seats independently**, on different corpus subsets with different pipelines.

---

## The screen

> **At `t0 + 60` slots, compute the share of all tokens bought so far that is held by the single
> largest buyer. If it is ≥ 0.95, do not enter.**

That is the whole rule. Every input is computable from the first 60 slots of trading, and nothing
downstream of the decision is used.

## What it predicts, and what it does not

It predicts **unexitability** — that a 0.1 SOL position will never be recoverable for even half its
cost from *external* money. It does **not** predict fraud, and it is not a rug detector.

The mechanism is plain once stated: a concentration of ≥0.95 means one wallet holds essentially
everything bought in the first 60 slots, which means **nobody else showed up**. You would be the only
other bag-holder, and there is no external money to exit into. It is [B19G's capacity wall](
B19G_EVALUATION_RESULT.json) turned into an entry filter.

## Held-out performance

Threshold chosen on a training half; every number below is from the held-out half, which was never
used to select anything.

| | flagged | passed |
|---|---|---|
| share of tokens | 39% | 61% |
| **unexitable rate** | **69.7%** | **13.0%** |

Base rate with no screen: **35.3%**. The screen catches **77.7% of all unexitable tokens** at **69.7%
precision**, and cuts the rate among tokens you actually buy from **35% to 13%**.

Train and test agree — +52.4pp lift on train, +56.7pp on test. **No shrinkage**, which is what a real
effect looks like and what a fitted one does not.

## The threshold barely matters, which is the point

| threshold | flags | precision | recall | **passed rate** | good tokens discarded |
|---|---|---|---|---|---|
| 0.70 | 50% | 57.0% | 81.7% | 13.1% | — |
| 0.90 | 42% | 66.4% | 80.1% | **12.2%** | 22% |
| 0.95 | 39% | 69.7% | 77.7% | 13.0% | 18% |
| 0.99 | 34% | 76.1% | 73.8% | 14.1% | — |
| 1.00 | 29% | 79.9% | 66.2% | 16.9% | 9% |

Anywhere between 0.70 and 0.99, the rate among tokens you *don't* screen out sits at **12–14%**. A
knife-edge optimum would have been a fitting red flag; a flat plateau means the effect is a property
of the population rather than of the parameter.

**The cost is real and should be stated with the benefit:** at 0.95 you also discard 18% of the
tokens that *were* exitable. You are trading away roughly one good token in five to cut your bad rate
from 35% to 13%.

## Why it survived when everything else did not

Not because concentration is a better feature than the ones the peer seat tested. **Because the label
was wrong for both of us**, and fixing it was the whole finding.

**Two label designs are broken on this venue:**

**The acute-event label** (a >50% single-step price collapse) is confounded by observation density:

| post-window observations | collapse rate |
|---|---|
| 2–3 | 0.0% |
| 3–10 | 0.0% |
| 10–73 | 6.1% |
| 73+ | 21.9% |

You cannot *observe* a collapse when there are two observations to look at. Two features passed a
permutation test against this label at p=0.003 — and both vanished once observation count was held
fixed. They were detection bias wearing the costume of a signal.

**A fixed-horizon price label is broken more deeply**, and the cause is a property of the venue:
**on a bonding curve the price only moves when someone trades.** A token nobody touches again shows a
perfectly flat price forever, so a price-based label records it as having *held its value* when it is
worthless and unsellable.

**The exitability label is not an artifact.** "Never traded again" correctly counts as unexitable
rather than as safe, and the relationship with observation count becomes causal instead of spurious:
0–1 later observations → 100% unexitable, which is the right answer rather than a bug.

## What cleared, specifically

| requirement (B20A) | result |
|---|---|
| decision time stated, features from `[t0, t0+60]` only | yes, K fixed in advance |
| gap between feature and label windows | yes, label strictly after t0+60 |
| census with drop rate | 2,062 scored; 1,177 unreadable (<2 buyers); 621 no label window |
| held-out reporting | threshold on train, reported on test |
| base rate stated | 35.3% |
| permutation, **both tails** | p = 0.002 |
| not a proxy for money already in the curve | +85pp spread *within* a fixed reserve band |
| independent replication | peer seat, different corpus and pipeline: p = 0.000, +46pp held-out |

## What it is worth

It avoids a class of guaranteed losses. **It creates no edge.** Everything the programme established
about the toll still stands: screening out dead tokens does not make the surviving ones profitable,
and no trade is rescued by it. Its value is that ~35% of tokens that pass a naive eye are positions
you could never have exited, and this removes three quarters of them using only the first minute of
trading.

*Burned data. A leakage-free observation, not a preregistered result. The honest next step would be
to freeze this rule and evaluate it once on window 2, which is exactly what the B19 machinery
exists for.*

---

## OUT-OF-SAMPLE (window-2) forward test — DECODE STATUS (2026-08-24)

**Status: decode RUNNING on the free public RPC; OOS verdict PENDING.** The single blocker — the
window-2 transaction-body decode that had 0 rows — is now unblocked and collecting.

- **Free RPC confirmed to retain the window-2 slots.** Contrary to the earlier
  `MEMECOIN_RECHECK.md` note, `https://api.mainnet-beta.solana.com` *does* serve BOTH
  `getTransaction` and `getBlock` for the window-2 range (slots 437,211,673–438,846,716,
  block_time ~2026-08). Verified directly: getTransaction on a known window-2 sig resolves; getBlock
  for a window-2 slot returns 1,329 signatures. So the decode runs for $0, no key, read-only.
- **The prior death was a code bug, not data unavailability.** `b9d.rpc_request` caught
  `urllib.error.*`/`TimeoutError` but not a bare `ConnectionResetError` raised inside
  `response.read()` (an `OSError`, not a urllib subclass). One transient reset after ~3,500 blocks
  killed the otherwise-resumable run. Fixed: `OSError` added to the retry `except` (it routes to the
  existing `is_retryable_error`, which already accepts `OSError`, so a genuinely fatal error still
  exhausts the 8 backoff retries and raises). b9d's source is not hash-pinned by the B20B prereg
  (only the runner is), so this edit is safe.
- **Launched detached + resumable.** `research/b11m_window2/run_free_decode.sh` (restart loop; each
  restart resumes from the per-row checkpoint on the same endpoint → no metadata drift). Settings:
  `--workers 2 --calls-per-second 4` against the free endpoint. Log:
  `research/b11m_window2/logs/free_decode.log`. Output DB: `b11a_bodies.sqlite` (fresh, single
  endpoint; the 3%-complete Chainstack partial was moved to `b11a_bodies.chainstack-partial.sqlite`
  because the endpoint-drift guard forbids mixing two endpoints' evidence in one artifact).
- **Scale / ETA.** Full frozen population for the 5,000-curve subsample: **366,688 signatures +
  118,384 getBlock slots ≈ 485K read-only calls.** The public endpoint throttles hard (429s even at
  <2 cps), so measured steady rate ≈ **1.87 calls/s** ⇒ **~72 h (~3 days)**. The pinned B20B label
  needs full-life reserves (real_quote after t0+60), so the *full* population is required — the
  first-60-slot predictor alone (138k sigs) is not sufficient for the label, and b9d's exhaustive
  freeze gates refuse a partial anyway.
- **After the decode (all OFFLINE, no more RPC):** supervisor stage `decode_and_reserves`
  (`b9d ... decode`, pinned-IDL decode + reserve reconstruction) → then the pinned
  `b20b_deadness_screen_runner.py` against `--bodies`/`--paths`/`--identity` emits the verdict
  (CONFIRMED / WEAKENED / FAILED vs the window-1 prior: 77.7% recall, 69.7% precision, ≥30pp lift).
- **Honest framing unchanged:** this is a loss-*avoidance* entry filter, not an edge. A CONFIRMED
  verdict means the guaranteed-loss class is filterable out of sample; it creates no return.

**How to check progress:** `tail research/b11m_window2/logs/free_decode.log` and
`sqlite3 research/b11m_window2/b11a_bodies.sqlite "SELECT count(*) FROM raw_block_signatures;
SELECT count(*) FROM raw_transaction;"` (targets: 118,384 blocks then 366,688 bodies).
