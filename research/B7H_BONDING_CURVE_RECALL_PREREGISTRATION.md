# B7h — Bonding-Curve History Recall Cross-Check Preregistration

**Frozen before block scan:** 2026-07-27  
**Status:** discovery-path validation; no model use

## Fixed comparison window

- Block window: **`[429,998,000, 430,000,000)`**, identical to the B7e launch window.
- Cohort: all 200 B7e mints, fixed by the already-complete launch database.
- Reference source: exact pinned-IDL `TradeEvent`s decoded directly from every retrievable block.
- Candidate source: B7e `lifecycle_event` rows discovered from each mint's bonding-curve address
  history.

The range is fixed before inspecting block-level trade counts or matches. It was selected because it
is already independently reconciled as 1,996 produced blocks and four skipped slots and contains
the first observable trades for the full launch cohort.

## Pass/fail rule

For every successful cohort `TradeEvent` decoded from blocks, the lifecycle database must contain
an identical key and payload at `(signature, mint, outer_instruction_index,
inner_instruction_index, event_payload_base64)`. The reverse comparison is also required for every
lifecycle event whose slot lies in the fixed window.

Any missing event, extra event, payload mismatch, block fetch failure, unknown event schema, or
create-slot reconciliation mismatch fails the discovery-path validation visibly. Zero reference
events is also an invalid test rather than a pass.

This validates recall only for this slot window and pinned program regime. It does not prove recall
across upgrades or alternate instructions forever.
