# B7e — Mature Cohort Trade Lifecycles

**Run date:** 2026-07-27  
**Status:** complete methodology-development measurement; cohort burned from all model evaluation  
**Preregistration:** `research/B7E_MATURE_COHORT_PREREGISTRATION.md`

## Result

**Verified fact:** all 2,000 slots in preregistered launch window
`[429,998,000, 430,000,000)` are accounted for. The RPC returned 1,996 blocks and an
independent `getBlocks` check verified four skipped ledger slots. Exact pinned-IDL decoding found
200 `CreateEvent`s for 200 distinct mints, with no decode or reconciliation failure.

**Verified fact:** every cohort member's bonding-curve address history was paginated through cutoff
slot 435,570,000 without hitting the explicit 100,000-signature cap. The histories contain 164,621
signatures: 143,822 chain-failed and 20,799 successful. Every successful transaction was retrieved;
exact event decoding produced 20,698 `TradeEvent`s in 20,693 transactions for 199 tokens. There
were no transaction-fetch or event-decode failures. The remaining 106 successful transactions had
no lifecycle event decoded and remain retained in the database.

Both SQLite databases pass `PRAGMA integrity_check`.

## Trade-silence evidence

Program event timestamps were sorted per token. Across 20,499 interior trade-to-trade intervals:

| Minimum resumed silence | Gaps | Tokens | Cohort fraction |
|---:|---:|---:|---:|
| 1 hour | 98 | 47 | 23.5% |
| 6 hours | 55 | 29 | 14.5% |
| 12 hours | 38 | 22 | 11.0% |
| 24 hours | 27 | 17 | 8.5% |
| 48 hours | 15 | 11 | 5.5% |
| 72 hours | 11 | 8 | 4.0% |
| 7 days | 5 | 5 | 2.5% |

The median interior interval was 0 seconds, p90 5 seconds, p99 507 seconds, p99.9 118,749
seconds, and the maximum was 1,325,555 seconds (about 15.34 days). For the 199 tokens with a
trade, final silence at the cutoff is right-censored; its median was 2,297,092 seconds and must not
be treated as abandonment.

**Decision:** `D_dead` remains unset. In particular, 24 hours is contradicted as a safe absorbing
dead-token boundary by 17 observed tokens that resumed afterward. This development cohort may
suggest candidates, but the preregistration forbids choosing and evaluating one on the same data.
Any candidate needs a disjoint untouched validation window and must remain a censored-duration
policy rather than a statement of fact.

## Completeness and limitations

- **Verified fact:** launch membership is exhaustive for the frozen slot window under the stated
  reconciliation rules; no token was excluded for activity, history size, Mayhem, quote mint, or
  outcome.
- **Verified fact:** every address history finished below the cap (minimum 1, mean 823.29, maximum
  14,072 signatures).
- **Working hypothesis:** bonding-curve address history is the intended complete discovery path for
  Pump curve trades because that account participates in the pinned trade instruction layouts. An
  independent block-level cross-check has not yet established recall.
- **Open question:** no `CompleteEvent` or `CompletePumpAmmMigrationEvent` was observed through this
  address-history path. This is not evidence that no member graduated; graduation status requires
  an independent account/state or migration-path check.
- **Open question:** global canonical transaction indices remain unresolved for 20,585 events.
  Only 59 event-bearing slots were block-enriched before the expensive enrichment was stopped.
  The reported per-token timestamp interval multiset does not depend on same-timestamp ordering,
  but no globally canonical event export is claimed.
- These are historical-chain observations, not executable returns, landing probabilities, or live
  latency evidence.

## Reproduction and artifacts

- Launch database: `research/b7e_create_429998000_430000000.sqlite` (SHA-256
  `6a7ce0590b80a0b4712c515889d6c32c5fd554f9b2996620ea8fde4ca5b9544b`)
- Deterministic launch JSONL: `research/b7e_create_429998000_430000000.jsonl` (SHA-256
  `b19ff5184cab5853a03e34f51845ce9e8194a9f06f606919c232dd863cce3bc4`)
- Lifecycle database: `research/b7e_lifecycle_429998000_430000000.sqlite` (SHA-256
  `92a9f05f16666be24eec969596c9061bcf18d1b9eea019331b5ec79cab055c06`)
- Completeness manifest: `research/b7e_lifecycle_summary.json` (SHA-256
  `fc104aebc0a9b139386e73700acb4a527e10e38565d5c8cd914237d49b7ff327`)
- Analysis: `research/b7e_lifecycle_analysis.json` (SHA-256
  `986dd4200b5b956809d8b5d416c618a86720805de7b20c702b2d722b460cf45d`)
- Implementations: `scripts/b7d_create_enumerator.py`,
  `scripts/b7e_lifecycle_reconstruct.py`, and `scripts/b7f_enrich_analyze.py`

Credentials were loaded from ignored `.env`; they are not present in these artifacts or commands.
