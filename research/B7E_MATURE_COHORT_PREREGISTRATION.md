# B7e — Mature Lifecycle Cohort Preregistration

**Frozen before enumeration:** 2026-07-27  
**Status:** methodology-development cohort; permanently excluded from model training, validation,
and testing

## Frozen windows

- Launch window: **`[429,998,000, 430,000,000)`** (half-open; 2,000 requested slots).
- Observation cutoff: **slot 435,570,000**.
- Program regime: after upgrade 422,112,651 and before upgrade 433,095,571.
- IDL: pinned `research/pump_idl_9c82f61.json`; exact decode or visible failure.

The launch window is immediately before, but does not overlap, B7d's 500-slot engineering pilot.
The cutoff gives every member approximately 5.57 million slots of potential observation and was
chosen before launch counts, attributes, histories, graduation, or outcomes were inspected.

## Membership

Every exactly decoded `CreateEvent` in the launch window is a member. There is no filter on:

- later activity or history size;
- graduation or migration;
- Mayhem or cashback status;
- SOL/USDC quote mint;
- creator, user, name, symbol, metadata, or reserves.

Ledger-skipped slots are allowed only when absence is verified through `getBlocks`. Any unexplained
slot, successful create/Event mismatch, unknown schema, or decode failure makes enumeration
incomplete and blocks lifecycle conclusions.

## Lifecycle measurement

The intended unit is a decoded Pump `TradeEvent`, not an arbitrary mint-address signature.
Transactions are included only at or before cutoff slot 435,570,000 and ordered by canonical chain
coordinates. Each member's final silence at the cutoff is right-censored, never converted into an
interior gap. Completion and migration remain separate anchors.

No `D_dead` value is preregistered. This cohort may describe the empirical distribution and
per-token incidence of resumed trade silences; it may not choose a threshold and then be reused to
evaluate that choice. Any candidate derived here requires validation on a disjoint untouched
window.

## Resource and failure rules

- Pagination and transaction-fetch caps must be explicit in output.
- A capped or RPC-incomplete token remains in the cohort with `incomplete` status; it is never
  dropped or replaced.
- Processing order is canonical launch order, not affordability or activity.
- Partial results may report pipeline progress only, never lifecycle rates.
- Credentials are loaded from `.env` and never persisted.

## Planned artifacts

- resumable B7d launch database and deterministic JSONL export;
- resumable lifecycle database with per-signature fetch/decode status;
- a completeness manifest separating complete, capped, RPC-failed, and censored members;
- a report with per-gap and per-token incidence only after the entire cohort is accounted for.
