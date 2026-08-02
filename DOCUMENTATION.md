# Project Documentation

Last reviewed: 2026-07-27.

## Research status vocabulary

- **Verified fact:** supported by a cited primary source or directly reproducible observation.
- **Working hypothesis:** plausible and testable, but not established for our dataset.
- **Decision:** an adopted design choice recorded in `DECISIONS.md`.
- **Open question:** unresolved and not safe to assume.

## Verified protocol facts

| Fact | Source | Reviewed |
|---|---|---|
| Pump bonding curves use constant-product pricing. **Graduation and pool migration are two distinct on-chain steps, not one automatic action** — see the correction note below. | [Pump bonding-curve documentation](https://pump.fun/docs/bonding-curve) + on-chain observation | 2026-07-27 |
| At review time, bonding-curve trading fees were documented as 1.25% total: 0.300% creator and 0.95% protocol. This is a point-in-time documented value, not a simulator constant. Canonical PumpSwap fees vary by market cap. | [Pump fee documentation](https://pump.fun/docs/fees) | 2026-07-27 |
| Pump supports SOL- and USDC-paired launches and recommends unified `buy_v2`, `sell_v2`, and `buy_exact_quote_in_v2` integration instructions. | [Official Pump public docs](https://github.com/pump-fun/pump-public-docs) | 2026-07-27 |
| Official IDL program address for the Pump program is `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`. | [Official Pump IDL](https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json) | 2026-07-27 |
| Solana priority fees depend on requested compute-unit limit, not actual units consumed. | [Solana compute-budget docs](https://solana.com/docs/core/fees/compute-budget) | 2026-07-27 |
| Jetstreamer replays Old Faithful historical blocks and executed transactions at high throughput; it does not execute transactions and Old Faithful lacks account-update events. | [Anza Jetstreamer](https://github.com/anza-xyz/jetstreamer) | 2026-07-27 |

All time-sensitive facts must be rechecked before implementation. On-chain configuration at the relevant slot is authoritative.

### Correction 2026-07-27 — graduation and migration are separate steps

The earlier wording of the first row ("migrate automatically and irreversibly … after graduation")
was taken from vendor documentation and is **not what the chain shows**. Evidence in
`research/B7A_LIFECYCLE_AND_MAYHEM.md` (F46):

- `CompleteEvent` and `CompletePumpAmmMigrationEvent` are separate IDL events, and `migrate` /
  `migrate_v2` are separate instructions.
- In a 220-block scan: 1 `CompleteEvent`, 1 `CompletePumpAmmMigrationEvent`, and **0 transactions
  containing both**. The migration arrived in its own `migrate_v2` transaction.
- `set_params` exposes **`enable_migrate`**, a globally settable flag, so migration is not merely
  deferred scheduling — it can be turned off.

A token therefore passes through an intermediate state: **curve complete, pool not yet migrated.**
This matters because it is precisely the window in which the bonding curve is closed and the
PumpSwap pool may not yet exist, so an exit may be unavailable at any price. Any exit-liquidity or
graduation label must model this state explicitly rather than assuming continuity of trading.

**Scope of this correction:** the *existence* of the intermediate state is established. Its
**duration is unmeasured** (n=1), and no claim is made about how often migration is delayed,
fails, or is disabled. Treat duration as an open question, not a small number.

## Evidence from research

These are study-specific results, not universal base rates:

- **B7h verified fact (fixed window `[429998000,430000000)`):** exact full-block decoding found
  13,861 cohort `TradeEvent`s and the B7e bonding-curve-history path contained the identical 13,861
  coordinate/payload rows, with zero missing events, zero extras, zero decode errors, 1,996 blocks,
  and four independently verified skipped slots. This validates observed discovery recall for the
  burned cohort window only; it is not a universal RPC guarantee. See
  `research/B7H_BONDING_CURVE_RECALL.md`.

- **B10b verified facts (frozen B9d artifact, 1,136 curves, 94,389 reserve observations).** Two
  structural properties of this venue that a position-path evaluator must respect, both measured
  rather than assumed. See `research/B10B_OBSERVED_PATH_VALIDATION.md`.
  - **A state that exists only part-way through another party's transaction is not a state we could
    trade against**, because our own transaction cannot land inside theirs. **1,121 transactions**
    carry more than one reserve observation on the same curve (1,033 with two, 88 with three), so
    **1,209 of 94,389** observations are not transaction-terminal. Separately, **910 of 1,136
    curves** publish a mid-transaction launch state, because the launch transaction also carries the
    creator's own first buy.
  - **`CompleteEvent` fires at an inner index after the trade that completed the curve.** A trade
    observation in the completing transaction therefore describes a curve already finished before
    anything of ours could follow it. Treating completion as effective only from the *next*
    instruction would publish exactly one tradable state per completed curve that never existed for
    us, and it would be the highest-valued state on that curve's whole path.

- **B10c verified fact — the B9d/B10b corpus is the burned B8b cohort.** All **1,136 of 1,136**
  `CreateEvent`s in the reserve corpus fall inside `[433,894,233, 434,097,833]`, the window
  `DECISIONS.md` burned on 2026-07-28. **R3 therefore applies to every label computed on it: it may
  never be measured or tuned there.** This is not a caveat on B10c; it is a constraint that predates
  it, and it is enforced in code — `window_status` is a required preregistration field whose only
  accepted value is `burned_development`, and the corpus runner refuses to compute a return
  distribution. Any future label work needs a fresh preregistered window disjoint from all burned
  ranges. See `research/B10C_LABEL_MATERIALIZATION.md`.

- **B10c verified fact — the observation window's end is recorded evidence, not an inference.** The
  `b9d` artifact states `cutoff_slot = 435,536,742` in its own metadata. Right-censoring is a claim
  about window geometry (C1/C2), so a censoring decision made against the maximum *observed* slot
  instead would be censoring against a window that was never collected. The label materializer
  requires the stated end and refuses a preregistration that disagrees with the artifact.

- **B11a verified fact — the burned-range register has seven entries and their maximum inclusive
  endpoint is 435,569,149** (B7c trade-only gap sample). Normalising is not cosmetic: a half-open
  `[a, b)` source range contributes `b-1`, and where a document's burn *statement* is wider than the
  code range it describes — B7b scanned `range(435566652, 435566690)` but declared slots
  435,566,652–435,566,690 burned — **the wider statement governs**, because the reading that keeps a
  slot out of evaluation is the safe one. Getting either convention backwards moves the whole fresh
  window. See `research/B11A_FRESH_COHORT_PREREGISTRATION.md`.

- **B11b verified fact — t0 is inside the launch transaction for every curve.** t0 is the first
  transaction-terminal state, and the `CreateEvent`'s transaction contains at least one observation
  for the curve, so the first transaction-terminal observation is necessarily inside it. Verified on
  the burned-development corpus: **1,136 of 1,136 curves, 0 in a later transaction.** This is what
  makes "the creator bought at launch" a point-in-time t0 fact rather than a look into the future,
  and it is the reason that feature is admissible at all. See `research/B11B_BASELINE_PLUMBING.md`.

- A 2026 Pump.fun study reported a median time to graduation of about 4.4 minutes among graduated tokens in its sample. Curve progress alone did not yield a profitable buy-and-hold rule; trading intensity and point-in-time creator/trader identity contained additional predictive information. [Study](https://arxiv.org/abs/2602.14860)
- A WebSci 2025 Solana memecoin sample found more concentrated and structurally fragile transaction communities in rug-pull projects. [Study](https://faculty.washington.edu/weicaics/paper/papers/YueyaoLYHC2025.pdf)
- Leakage is a central rug-detection risk: post-collapse signals cannot be used as early-warning features. [TM-RUGPULL](https://arxiv.org/abs/2602.21529)
- A static review of 61 public memecoin-bot repositories found that public implementations concentrate on execution while rarely providing complete point-in-time data, executable simulation, or chronological performance evidence. See [`research/MEMECOIN_BOT_REPOSITORY_REVIEW.md`](research/MEMECOIN_BOT_REPOSITORY_REVIEW.md) for method, limitations, and per-repository findings.

## Working hypotheses

- Cluster-adjusted holder concentration is more predictive than raw holder concentration.
- Funding convergence, coordinated entry timing, creator-linked distributions, and recycled flow help identify manipulated demand.
- Confirmation-based entries after observable sell absorption may outperform blind launch sniping after costs.
- Exit-liquidity prediction and transaction landing reliability may contribute more to net performance than a small improvement in direction classification.
- Rejecting most launches is likely necessary for positive risk-adjusted expectancy.

None of these hypotheses may be described as an edge until it passes chronological, executable evaluation.

## Proposed system boundaries

```text
Jetstreamer historical replay ─┐
                              ├─> shared decoder -> canonical events -> raw/state stores
Live Geyser/Yellowstone ──────┘                         |
                                                       v
                                      wallet graph + point-in-time features
                                                       |
                                                       v
                                          risk veto + predictive models
                                                       |
                                                       v
                                         simulator / shadow decision log
                                                       |
                                                       v
                                separately authorized execution + risk services
```

**Implemented so far, and where the risk veto actually sits.** `scripts/b12a_risk_governor.py`
(`docs/RISK_DECISION_SCHEMA.md`) is the "risk veto" box, built as a **deterministic, fail-closed
library above the policy rather than inside it**. It consumes a candidate order, the exact curve
state, a portfolio snapshot, a health snapshot and an explicit `RiskConfig`, and returns approve-or-
reject with ordered reason codes.

The load-bearing architectural choice: **it may not resize an order.** A governor that shrinks a
proposal to fit a limit changes the thing being evaluated, so every return and drawdown figure
downstream would describe a strategy nobody wrote. Two outcomes only, never three. It also holds no
state between calls — the caller threads the portfolio snapshot — so concurrent proposals are
accounted for without a mutable global, and it holds no wallet, key or transport: every record
carries `NO_SIGNING_OR_SUBMISSION`.

### Historical ingestion

Use Jetstreamer for bounded historical backfills. Write a custom Rust plugin that filters and decodes Pump, PumpSwap, fee, Mayhem, Token/Token-2022, associated-token, system-transfer, compute-budget, and relevant tip instructions.

Jetstreamer limitations that must remain visible:

- It provides archived, already-executed transactions rather than pre-execution intent.
- It lacks historical Geyser account-update events.
- Parallel replay can deliver writes to storage out of order.
- The advertised throughput is a hardware-dependent vendor benchmark, not expected local performance.

### Live ingestion

Use Geyser/Yellowstone for live transactions, account writes, slots, blocks, and commitment transitions. Record provider receipt timestamps and retain processed, confirmed, finalized, failed, expired, and orphaned distinctions. Use at least one independent path for verification.

Record the full observable Pump market even when the initial trading policy excludes a regime. In particular, preserve Mayhem activity as a time-varying market covariate so changes in attention and liquidity are not misdiagnosed as model decay.

### Canonical ordering

Never depend on ingestion or database insertion order. Preserve and sort by:

```text
slot -> transaction index -> outer instruction index -> inner instruction index
```

Record source-provider timestamps separately; they describe observation latency, not chain order.

### Observability envelope

Historical canonical replay and live observation are not interchangeable. Canonical chain events and observations are separate relations:

- A canonical event records chain truth and canonical ordering.
- An observation records that a source saw a payload/event at a particular time and commitment.
- One canonical event can have many observations across sources and commitments.
- An observation is allowed to remain without a canonical parent when what was observed never becomes canonical.

Each observation must carry `first_observed_at`, `commitment_at_observation`, `source_id`, and an enumerated provenance class such as `observed_live`, `observed_live_after_gap`, `backfilled_rpc`, `historical_oracle`, or `reconstructed`. Do not store a hand-assigned numeric confidence. If numeric confidence is later useful, derive it from measured source behavior and provenance.

Historical features must be degraded through an empirically measured live visibility/latency model before they are treated as decision-time inputs. Never allow finalized archive replay to imply zero latency, perfect visibility, or knowledge of later-canonical ordering.

### Minimal raw live capture

Capture first and decode later. Preserve at least these append-only relations:

1. `raw_frame`: recorder/session identifiers, monotonic sequence, monotonic and UTC receipt clocks, unmodified payload, payload encoding/schema version, vendor-neutral provider kind, and subscription identifier.
2. `frame_index`: nullable minimal classification (`transaction`, `account_update`, `slot_status`, `block_meta`, `heartbeat`, `error`, or `unknown`), slot, commitment, and signature. Unknown frames remain stored and counted.
3. `session`: endpoint reference without credentials, subscription specification and hash, open/close clocks, close reason, and frame count.
4. `gap`: sequence, slot, session, and heartbeat discontinuities with detectable missing-range hints.
5. `slot_observation`: repeated processed/confirmed/finalized/dead-or-skipped status observations used later to derive orphan behavior.
6. `clock_sample`: synchronization state and estimated offset so unreliable latency windows can be excluded visibly.

Use content-addressed append-only segments and a documented fsync policy with a bounded, detectable crash-loss tail. Recorder downtime must never be indistinguishable from market quiet. The 72-hour pilot determines bytes per slot and informs retention sizing.

### Event decoding and configuration state

Prefer Anchor CPI event data from inner-instruction metadata over `logMessages` when the Pump program version emits CPI events. Anchor documents that program logs may be truncated by data providers, while `emit_cpi!` places event data in CPI instruction data. Use logs for diagnostics or explicitly tested fallback paths, never as a silently lossy sole source. Inventory each historical Pump/PumpSwap version before assuming all versions emit identical CPI events.

Maintain a versioned `program_config` timeline from on-chain accounts and configuration-changing instructions. Quotes and costs must read the configuration active at the relevant slot/instruction; fee rates, recipients, initial reserves, migration parameters, and related configuration must not be hardcoded as timeless constants.

### Data layers

1. Immutable raw source records.
2. Versioned decoded events.
3. Reconstructed canonical state.
4. Point-in-time feature snapshots.
5. Immutable decisions and simulated/live outcomes.

Every derived row should identify decoder, schema, feature, label, and model versions.

## Required event families

- Block, slot, transaction, and transaction outcome.
- Outer and inner instructions.
- Pump creation, buy, sell, migration, configuration, fee, and creator-sharing events.
- SOL and token balance changes.
- Curve and PumpSwap pool state transitions.
- Compute budget, priority fee, Jito tip, base fee, and rent costs.
- Wallet funding and transfer edges.
- Metadata and social snapshots with observation timestamps.
- Strategy feature vector, decision, rejection reason, intended order, and actual outcome.
- Recorder raw frames, sessions, heartbeats, clock samples, subscription specifications, disconnects, gaps, and slot-status observations.

## Evaluation requirements

- Purged chronological walk-forward splits.
- Creator, wallet, and funding-cluster dependency accounted for in uncertainty estimates.
- Program, fee, quote-asset, Mayhem, and market regimes separated when appropriate.
- Baselines: no trade, random, simple momentum, and curve progress.
- Metrics: net expectancy, drawdown, calibration, tail loss, capacity, failure rate, and execution divergence.
- Three simulation views: optimistic markout, latency-adjusted executable outcome, and stressed outcome.

## Open questions

- Which exact slot/date range offers enough current-regime history without mixing incompatible fee and instruction regimes?
- How close to chain tip is Old Faithful in normal operation, and what gaps occur?
- Which Pump program upgrades require separate decoder/state versions?
- Can historical reserve state be reconstructed exactly from archived transaction metadata for all relevant instruction versions?
- What wallet-clustering evidence achieves useful precision without mislabeling exchange or service wallets?
- Which social sources are legally and technically recordable with trustworthy observation timestamps?
- What capture latency, throughput, disk cost, and realistic uptime are achievable on the user's local machine? (Operation is local-only per `DECISIONS.md`; hosted deployment and region selection are out of scope.)

## Source policy

Prefer, in order:

1. On-chain program/configuration state and raw transactions.
2. Official Pump, Solana/Anza, Jito, and infrastructure documentation.
3. Peer-reviewed or transparent reproducible research.
4. Third-party analysis, clearly labeled and independently checked.

Web pages change. Record access dates and archive critical specifications or pin official IDL revisions when implementation begins.
