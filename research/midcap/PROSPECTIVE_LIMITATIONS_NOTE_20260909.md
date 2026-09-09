# Recorded limitations of the prospective instruments (from Codex's audit, 2026-09-09) — read with every result

1. Transfers into an EXISTING token account of a roster wallet are invisible to both watchers (owner absent from account
   keys; `mentions`/`getSignaturesForAddress(wallet)` miss them). Coverage is FIRST receipt per wallet-mint (ATA creation
   references the owner). The cohort cells use first positioning per wallet-mint, so the definition is covered; repeat
   allocations of an already-held mint are not. Addendum 3's 7-day window inherits this.
2. Telegram wave deltas (+5/+15 min, last-300-trades sample + DexScreener m5 counts) are DIAGNOSTIC ONLY, never the
   pre-registered wave gate; empty API output is not zero; hot pools truncate the before-window.
3. Follower-wave follow-ups marked done may lack trades/bars (rate-limit starvation on 2026-09-09 evening: 294 re-queued;
   retries added). Coverage per event must be reported with the wave read, not assumed.
4. rh_tape v1 skipped 2,919 blocks across three ranges despite err=NULL (head-minus-cap catch-up). Repaired by integrating
   Codex's `next_range` and `capture_gap`; the three holes are backfilled and marked, not hidden.
5. Mayhem recorder: marks whose due time preceded the recorder start (20:12 UTC) were recorded late (up to ~2 h); the
   primary read uses only coins whose +23 h mark is on/after recorder start, and reports the late set separately.
6. Cohort `firstsight` age uses a later pool lookup; missing pair can be a failed lookup, not pre-pool. The evaluator's
   pre-pool flag must be reported as PRE_POOL_OR_LOOKUP_FAILED until the sight is re-checked at signal time.
7. All public-RPC workers share one budget; v1b polls reached 667 s; wallet-interval gaps under CAP are not identified.
