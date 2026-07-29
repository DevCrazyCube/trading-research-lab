# B9b — Bonding-curve history counts before reserve-path reconstruction

**Status:** complete bounded sizing measurement; full reconstruction not started  
**Access date:** 2026-07-29  
**Program/version scope:** the frozen 1,601-member B8b launch cohort; bonding-curve addresses from
the audited B9a artifact  
**Source:** configured Solana mainnet JSON-RPC; credential omitted  
**Artifact:** `research/b9b_curve_history_counts.sqlite`, current SHA-256 recorded in the release
handoff. The initially published hash `3d302630…af515` was superseded when a logical no-op rerun
rewrote identical metadata; the rerun defect and correction are recorded explicitly below.

> **Evidence correction:** B9b preserves derived per-curve counts but not the raw RPC pages.
> Reproducing or auditing those counts therefore requires repeating the requests. The aggregate is
> a valid observed sizing result, but this artifact is **derived evidence, not primary evidence**.
> B9c must preserve compressed raw pages and normalized signature metadata before publishing any
> deduplication, failure-rate, or narrowing result.

## Question

B9a's terminal account snapshot cannot establish the reserve path. A curve can accumulate quote
reserves and later round-trip to its launch state. Exact `TradeEvent` reconstruction can measure
peak reserves, time to peak, and whether an exit window existed, but first B9b prices the required
transaction retrieval without fetching transaction bodies.

## Method

`scripts/b9b_curve_history_counts.py` reads all 1,601 distinct bonding curves from B9a with SQLite
`mode=ro`. For every curve it paginates finalized `getSignaturesForAddress` results in pages of up
to 1,000, to a frozen cap of 10,000. Each completed curve commits separately to a resumable SQLite
artifact. A curve reaching the cap is marked censored rather than reported as exact. Empty pages,
missing pagination cursors, transport failures, row-count disagreement, and integrity failure are
visible failures.

The implementation did **not** persist each returned raw page. This defect was identified
immediately after publication and is not repaired retroactively or hidden by rerunning B9b.
The first completed-artifact rerun also used `INSERT OR REPLACE` for identical metadata, which
changed the SQLite bytes while leaving every measured row unchanged. The code now inserts only
missing metadata, with a byte-immutability regression test. Hash history is retained in the handoff
log; no earlier hash is silently replaced.

The run used four workers, made 2,535 RPC page requests, completed all 1,601 curves, and passed
SQLite `integrity_check`. The full repository suite passed 297 tests after the measurement.

These are **address-signature counts**, not Pump trades. They include failed and non-trade
transactions. They are therefore a conservative retrieval-work count for a naive
one-`getTransaction`-per-signature reconstruction, not a count of economic events or fills.

## Results

| population | curves | observed signatures | capped | median | p75 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| whole cohort | 1,601 | **≥1,316,593** | 6 | 163 | 986 | 2,703 | 3,751 | 7,269 |
| tradable, non-Mayhem | 1,136 | **≥1,256,211** | 6 | 342 | 1,629 | 3,175 | 4,345 | 7,513 |
| excluded Mayhem | 465 | 60,382 | 0 | 64 | 167 | 305 | 460 | 982 |
| tradable non-graduates | 1,120 | **≥1,199,053** | 3 | 337 | 1,620 | 3,134 | 4,290 | 7,269 |

No curve had zero indexed signatures. Six non-Mayhem curves reached 10,000 and are right-censored;
three were graduated and three were not. The largest exact uncapped count was 9,004. Consequently,
the aggregate totals containing those six are lower bounds, not exact totals.

## Interpretation

- **Verified fact:** the frozen cohort exposes at least 1,316,593 bonding-curve address signatures;
  the currently tradable population contributes at least 1,256,211 (95.4%). The earlier working
  guess that most members might never have traded does not imply a small retrieval job and is not
  supported by these address-history counts.
- **Verified fact:** activity is highly heterogeneous. The all-cohort median is 163, while the
  uncapped upper tail reaches 9,004 and six curves exceed the measurement cap.
- **Working estimate:** applying B6j's single-endpoint observation of approximately 2.5 successful
  `getTransaction` calls/second to the tradable lower bound implies at least **5.8 continuous days**
  of transaction retrieval. Applying B6j's roughly 10 KB/transaction observation implies at least
  about **12.6 GB** of response payload. These are cross-run planning estimates, not RPC guarantees;
  endpoint capacity and transaction size vary.
- **Decision implication:** do not launch a naive full-cohort transaction-body reconstruction next.
  First design a lossless deduplication and narrowing pass that uses already-preserved raw evidence
  or event-bearing signatures where possible, while retaining the exhaustive curve population and
  making every excluded signature class auditable. Sampling tokens by observed history size would
  be outcome-dependent selection and is forbidden.
- **Open question:** exact workload above 10,000 remains unknown for six curves. The present lower
  bound is already decisive for rejecting an immediate naive full fetch, so increasing the cap
  would spend requests without changing that decision.
- **Open question:** signature counts do not establish reserve peaks, timing, trade direction,
  economic amounts, failure incidence, or executable exits. B9b sizes the missing measurement; it
  does not answer it.

## Reproduction

```bash
python3 -m pytest tests/test_b9b_curve_history_counts.py -q
SOLANA_RPC_URL='<credential-bearing endpoint>' \
  python3 scripts/b9b_curve_history_counts.py --workers 4 --cap 10000
```

The endpoint credential must remain outside tracked files and captured output. Re-running against
the completed artifact is resumable and performs zero RPC calls when all rows are present.
