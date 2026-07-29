# B9c — Raw signature inventory and lossless narrowing preregistration

**Status:** methodology frozen before B9c network execution  
**Date:** 2026-07-29  
**Population:** all 1,601 B8b members; tradable reporting excludes Mayhem only under the already
frozen policy  
**Inputs opened read-only:** B8b cohort, B9a outcomes, and B9b derived counts

## Audit finding

No existing artifact contains the B8b cohort's complete observation-period transaction index.
B8b preserves sampled launch blocks, not post-launch histories. B7e/B7h cover a different burned
cohort and regime; B7j covers an unrelated 439-slot positive-control envelope. Reusing any of them
as if it covered B8b would silently substitute adjacent evidence.

B9b measured at least 1,316,593 address signatures, but preserved only derived curve totals. Its
artifact cannot support deduplication or failure-rate claims because the raw RPC pages are absent.
B9c therefore repeats the signature pagination into a new evidence-grade artifact.

## Frozen purpose

B9c will answer only:

1. How many raw address-history rows are observed for the exhaustive cohort?
2. How many distinct transaction signatures remain after exact signature deduplication across
   curves?
3. Within the frozen observation interval, how many rows are RPC-classified successful, failed,
   or unknown?
4. What exact `getTransaction` workload remains for reserve-path reconstruction when failed
   transactions are retained as execution evidence but excluded from the state-mutation fetch set?

It will not decode trades, calculate returns, select tokens, or claim exit availability.

## Frozen observation envelope

- Launch-window start time is the B8b metadata value `1784463582` (2026-07-19 12:19:42 UTC).
- `W_obs` is the owner-ratified 8 days, so the outcome cutoff time is **`1785154782`**
  (2026-07-27 12:19:42 UTC).
- Before member pagination, resolve and preserve the canonical cutoff slot as the greatest produced
  finalized slot whose primary-source `blockTime <= 1785154782`; preserve every RPC response used
  to bracket it. Do not infer the slot from a slots-per-day average.
- A normalized signature is in-window only when `launch_slot <= slot <= cutoff_slot`. Rows newer
  than cutoff are preserved but excluded from the reconstruction workload. A null/malformed slot
  is `unknown`, never silently excluded.

This corrects a limitation in B9b: its current-tip counts include post-`W_obs` activity and are a
conservative workload bound, not the frozen-label workload.

## Evidence artifact

Use a new SQLite database with `WAL`, `synchronous=FULL`, and at least:

1. `metadata`: source hashes/paths, endpoint reference without credentials, program id, cap,
   cutoff timestamp/slot, schema version, and completion summary.
2. `raw_rpc_response`: content-addressed compressed exact response bodies for cutoff resolution and
   every history page, including request method and non-secret params, curve, page index, receipt
   time, and SHA-256. The stored bytes, not a reconstructed JSON object, are primary evidence.
3. `curve_scan`: curve, page count, observed rows, in-window rows, boundary status, cap status, and
   terminal error. A curve is complete only when pagination proves it crossed below its launch
   slot or exhausted history.
4. `signature_observation`: curve, signature, slot, block time, `err` payload, memo, confirmation
   status, page coordinate, and in-window classification. Primary key is `(curve, signature)`;
   repeated signatures across curves remain distinct observations.
5. A derived distinct-signature view/table whose source observations remain traceable.

Each raw page and its normalized rows commit in one transaction. A completed artifact can never be
overwritten, even with a reset flag. A partial artifact resumes only after source metadata matches
exactly. Unknown fields, pagination ambiguity, cap exhaustion, HTTP/RPC errors, or missing cursors
fail visibly.

## Lossless narrowing rules

- **Exact cross-curve deduplication is allowed:** one transaction signature needs one body fetch,
  while all curve memberships remain linked.
- **Time-envelope exclusion is allowed:** rows after the frozen cutoff or before the member launch
  remain preserved and counted but are outside this label measurement.
- **RPC `err != null` rows are excluded only from reserve-state mutation fetching.** They remain
  preserved for execution-failure modelling and reported separately. This relies on validator
  transaction atomicity; no failed transaction is described as economically irrelevant because it
  can still matter to a future execution model.
- **No token, creator, activity-size, graduation, terminal-reserve, or outcome filter is allowed.**
  In particular, B9b's history-size distribution cannot choose a cheaper token subset.
- **No event-name filter is yet allowed.** Non-trade instructions can mutate relevant state, and
  unknown instructions must fail visibly. Event-only narrowing requires a separate completeness
  proof against fetched transaction bodies.
- Mayhem remains recorded exhaustively and reported separately; it is excluded from the tradable
  reconstruction workload only by the pre-existing frozen safety policy, never because B9b showed
  it is cheaper.

## Publication gates

B9c publishes no workload result unless all 1,601 curves have a proven launch boundary or an
explicit incomplete classification; every raw response hash re-verifies; normalized counts
reproduce from raw pages; source membership matches B9a/B8b bidirectionally; the cutoff derivation
is preserved; SQLite integrity is `ok`; and no completed source artifact changed hash.

The output is still an index, not reserve-path evidence. Fetching and decoding transaction bodies
requires a separate B9d freeze after B9c reports the exact distinct-successful workload.
