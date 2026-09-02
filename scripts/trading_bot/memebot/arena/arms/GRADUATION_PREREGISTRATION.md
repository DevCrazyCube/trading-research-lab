# ARM 3 — MEMEBOT_GRAD_V1 — Pre-Registration

Status: PRE-ACTIVATION, paper-only, read-only public Solana RPC. No signer or order method.
PumpPortal CREATE and migration subscriptions are free under the provider schedule verified
2026-09-02, but the at-s6 primary/control cohort requires the metered token-trade stream and therefore
fails closed without a dedicated `PUMPPORTAL_DATA_API_KEY`. Execution pricing remains read-only RPC.

## Cohort

- A migration must be received by the forward PumpPortal migration subscription for a mint whose CREATE
  this host observed after activation. The migration signature must independently resolve to a confirmed
  Solana slot; otherwise it is censused `UNCONFIRMED_MIGRATION` after 60 seconds and excluded.
- The measurement cohort requires the same at-s6 concentration proxy as Bundle Momentum. Proxy failures
  enter an identically executed `CONTROL_PROXY_FAIL` cohort; they never enter the primary statistic.
  This is not exact t0+60 B20B and is labelled accordingly.

## Causal PumpSwap paper fill

- Entry decision is the confirmed migration slot. Entry lands on the first read-only PumpSwap reserve
  snapshot with context slot >= migration slot+15. The full cohort includes every confirmed live pool;
  a pool still absent after 120 seconds is censused, never silently dropped.
- Size is exact point-in-time USD 10 from the hash-validated Coinbase SOL/USD recorder. Buy impact uses
  constant-product reserves and fees charged on quote input. Entry includes base+priority cost and ATA
  rent. Exit uses the audited PumpSwap sell quote; ATA rent is reclaimed only after a full sale and a
  modeled close cost. No marginal or migration-open price is a fill.
- Exit: -12% all-cost stop, widening 18/25/35% trail, 90-minute horizon. An exit lands only on a fresh
  reserve snapshot at least 15 slots after its decision. Twelve consecutive unavailable reads after an
  exit decision resolve as a full loss; every entered position reaches one terminal row.
- Max entry-lag (frozen, `MAX_ENTRY_LAG_S = MIGRATION_CONFIRM_TIMEOUT_S + POOL_CONFIRM_TIMEOUT_S = 180s`):
  a candidate whose migration-signal→fill latency exceeds this bound (a backlog casualty, whose earliest
  observable reserves are far past the modeled +LATENCY_SLOTS entry) is VOIDed with reason
  `ENTRY_LAG_EXCEEDED`, never filled late. The bound is a latency-based, outcome-independent, pre-declared
  measurement parameter (frozen in SPEC) — it removes a late-fill distortion, it does not cherry-pick.

## Decision

KILL-only tripwire at 30 primary rows if a one-sided exact sign test rejects median>=0 at p<0.05.
At 100 distinct primary rows: KILL if CI95-hi(mean net R)<0; PASS-to-confirmation only if CI95-lo>0 and
the full search/multiple-testing penalty is disclosed. The proxy-fail control is reported separately.
Any duplicate mint, open/pending lifecycle, broken tape/ledger chain or missing all-cost reconciliation
invalidates the read. PASS cannot authorize real money.
