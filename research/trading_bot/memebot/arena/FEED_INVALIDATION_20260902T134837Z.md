# Arena feed invalidation — 2026-09-02T13:48:37Z

**Verified fact.** The first Helius fallback decoder admitted 10,487 Pump `TradeEvent` rows whose decoded
SOL reserve relationship was outside the classic SOL-quoted, non-Mayhem bonding-curve regime. The affected
raw interval starts at Helius sequence 40,252 and its last out-of-regime event is sequence 147,203. The raw
hash-chained tape is preserved; no source observations were deleted.

**Decision.** `BUNDLE_MOMENTUM_V2` and `MIGRATION_ACCEPTANCE_V1` activated inside that interval. Their
epochs are diagnostic-only and cannot contribute performance evidence. At invalidation, Bundle reported
26 resolved rows with mean net return `+0.03956865384615385`; Migration reported zero resolved primary
rows, four resolved controls with mean `-0.7938061509167011`, and five open positions. None of these values
is an edge estimate.

The invalidated artifacts were moved intact to
`research/data/arena/superseded/20260902T134837Z_idl_decoder_regime/`. Pre-move SHA-256:

- Bundle state: `170f98c0e138a4bf6dc269a5c21e91dbd873189ff73bea0ad4043582594009f8`
- Bundle ledger: `2349cde0695ed6021c8a900186e4aa722a62c98cf9588c886bda60e6add2c531`
- Bundle activation: `d9c0b22f71f44bb9b158069fc0bbf0d4fa907487e6f5ae6c168e7434723c38ad`
- Migration state: `dacb9e8b6ea8d0538384eb9e78b9c04fb11759191a906f98f11025272e00fec5`
- Migration ledger: `527a2eea5b576a3a304906ac08a2eb1e7c7b177a52c87b58305111b086761b70`
- Migration activation: `0e12ab2f15c4587ecd442ec6aa6d6e96e4177b83af3cbd73af5717c73716c515`
- Shared portfolio state: `83f1d8541310957e7a1819a70ee46b2ff9e0766b67bf251ab11fffac36ddaaad`

**Replacement boundary.** A fresh activation may be written only after the official IDL, exact decoder,
Helius listener and feed-health gate are included in each arm's closure and committed. It must pin the
then-current tape sequence/head, making every pre-activation row unreachable as forward evidence.

**Boundary.** Paper-only. This repair validates causal data plumbing, not profitability and not live-money
readiness.
