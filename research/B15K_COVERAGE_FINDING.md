# B15k finding: B15a under-records launches; it is not a fork oracle

Measured 2026-08-03, under `research/B15K_COVERAGE_AUDIT_PREREGISTRATION.json`, committed alone
before any comparison was computed and before any confirmation query was sent.

## The question

B15i observes launches at `processed` that B15a's `confirmed` recorder does not hold. Two
explanations fit and they are opposites:

- **Fork orphans.** Processed carries transactions that confirmed never accepted. A property of the
  chain, and the missing cells are correctly excluded.
- **Confirmed-feed miss.** B15a under-records launches that did confirm. A defect in our own
  instrument, and we are discarding real launches while reporting the discard as a fork rate.

## The comparison, inside a closed interval only

Both recorders had demonstrably passed `[436880576, 436902268]` — each extent shrunk by a 300-slot
closure margin. Outside that window an absence means only that a recorder has not arrived, and
comparing across an open edge measures lag and calls it a miss.

| class | count |
|---|---|
| comparable launches | 2,755 |
| CORROBORATED (B15a holds a decoded launch) | 798 |
| B15A_DECODE_FAILED | 0 |
| B15A_SAW_NON_LAUNCH | 0 |
| **ABSENT_FROM_B15A** | **1,957** |

B15a holds **29.0%** of the launches B15i observed inside a window B15a had already passed.

`ABSENT_FROM_B15A` was deliberately not named orphan, fork or miss. An orphan is a claim about the
chain; an absence is a fact about our recorder.

## The independent query

200 signatures, selected by ascending SHA-256 of the signature — a rule fixed in the freeze before
any result existed, reproducible from the population alone, and independent of slot, arrival time
and base58 prefix. Each queried with `getTransaction` at `confirmed`, two per second, raw exchange
preserved before the answer was judged.

| outcome | count |
|---|---|
| **CONFIRMED_ON_CHAIN** | **200** |
| NOT_FOUND_AT_CONFIRMED | 0 |
| QUERY_FAILED | 0 |

**Two hundred of two hundred.** Every sampled launch that B15a never recorded was on chain at
confirmed commitment.

## What this settles, and what it changes

**B15a under-records. There is no fork story here.** The gap is our instrument, not the chain.

Consequences, applied:

- **B15a is no longer a confirmation oracle in B15i.** `reconcile` still PROMOTES on a B15a or B15b
  record — a signature they hold did confirm, and that is sound — but it can no longer ORPHAN
  anything. The previous rule orphaned whatever a peer recorder had passed without recording, which
  assumed the peer sees everything that confirms. It does not.
- **Only the chain orphans.** A new bounded, rate-limited `confirmation_worker` asks
  `getTransaction` at confirmed for each unresolved launch older than the margin. An explicit
  not-found is the only thing that marks an observation orphaned. A failed query returns `None`,
  which is not `False`, and decides nothing.
- **The earlier orphan counts are withdrawn.** The 1,318 launches B15i reported orphaned were
  measuring B15a's coverage. They are not evidence of forks and were never published as a rate.

## The limitation, recorded

This is a property of the standard `logsSubscribe` transport at `confirmed` on this provider, not a
property of Solana. Nothing here estimates how many launches BOTH feeds missed: that would need a
third independent feed, which this project does not have. Every coverage figure in B15i and B15k is
conditional on the observing feed, and neither recorder establishes what neither saw.

No return, executability or landing probability is measured or claimed.
