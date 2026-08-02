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

- **B13a verified fact — funding edges are recoverable from the frozen artifact.** Decoding System
  instructions against the pinned ABI over a bounded slice of the burned corpus (60 curves' worth of
  transactions) yielded **35,568 transfer edges** carrying source, destination, amount, canonical
  coordinate and provenance. Funding-edge evidence therefore exists in this project's data; entity
  resolution over it does not, and **funding-cluster leakage remains an open gate**. Every System
  instruction in that slice is accounted for — 36,869 = 35,568 lamport-moving + 1,301 non-moving +
  0 undecodable — so the edge count is a partition of the evidence rather than a tally of whatever
  happened to decode. See `research/B13A_HISTORY_FOUNDATION.md`.

- **B13a measured fact — undecodable System payloads exist, at a density no corpus run would
  catch.** Surveying the whole b9j artifact (**94,985 transactions, 412,028 System instructions**)
  found exactly **two** payloads the pinned ABI refuses, both padded `CreateAccount` bodies (52 of
  56 bytes decoded, 4 trailing) in one transaction at coordinate `(433968746, 858)`. Two in 412,028
  is the density at which a corpus gate proves nothing: the handling path for them was crashing,
  and only a pinned fixture exposed it. Undecodable payloads are therefore a real, rare and
  permanent condition of this data, not a hypothetical.

- **B13b design fact — a cluster is indistinguishable from an observation once it is in a record.**
  `prior_launch_count_observed` says where it came from; `cluster_id` does not. That asymmetry is
  why the association ledger publishes evidence and refuses conclusions, and why the refusal is
  enforced on **field names** rather than values: a field called `cluster_id` holding `"none"` still
  teaches the next reader that clusters are something this record has. See
  `research/B13B_ASSOCIATION_LEDGER.md`.

- **B13b design fact — overlapping evidence is not independent evidence.** Every direct transfer
  between two addresses is also a co-occurrence in the same transaction, so one observation can
  produce several evidence items of different kinds. The ledger records the overlap on the item
  itself; summing these counts into a score would count one event as several corroborating ones.

- **B13c design fact — external data has a second clock, and that is where leakage hides.** An
  article's publication date can be genuinely before t0 while we did not have it until long after;
  every field a naive schema records checks out, and the only thing wrong lives in a clock nobody
  wrote down. Eligibility therefore requires receipt AND publication at or before t0, because
  neither implies the other: receipt alone admits a future-dated item, publication alone admits the
  backfill. See `research/B13C_EXTERNAL_OBSERVATIONS.md`.

- **B13c design fact — a deletion received after a decision must not reach back.** Replaying an
  earlier decision without a post that was withdrawn later would make the backtest quietly better
  than live trading can ever be, because live trading does not get to un-see things. Data hygiene
  applied retroactively is leakage.

- **B13d design fact — concentration is a ratio, and the denominator does all the work.** A curve
  holding 800M of 1B units makes a 120M holder either 12% (of total supply) or 60% (of circulating
  user balances). Both are exactly right and they support opposite conclusions, so publishing one of
  them is a silent choice on the reader's behalf. Every share is therefore published under both, and
  the circulating denominator is built by summing inclusions rather than subtracting exclusions —
  a sum names what it included. See `research/B13D_CONCENTRATION_FOUNDATION.md`.

- **B13d design fact — the direction of an error decides which default is safe.** Counting an
  unknown-role balance as a user balance enlarges the denominator and shrinks every share: the
  flattering direction. A rule that errs toward "this token looks fine" is not a rule, so unknown is
  excluded by construction, negative balances are refused rather than clamped, and one unresolved
  account blocks owner-level collapsing entirely.

- **B13e verified fact — the fresh window's lookback overlap with burned territory decays to
  exactly zero at the observation cutoff.** Because B11a starts one slot after the maximum burned
  endpoint (435,569,149) and the reused lookback equals the observation span (1,642,509), a decision
  at the observation cutoff 437,211,659 looks back precisely to 435,569,150 — the fresh window's
  first slot. Nobody arranged that; it falls out of the arithmetic. A corollary worth knowing: the
  slot immediately before the fresh window is itself burned, so "just before t0" is never an
  unburned fixture. See `research/B13E_LOOKBACK_PREREGISTRATION.md`.

- **B13e design fact — a parameter is only frozen if something notices when it thaws, and only the
  values held in two places can be cross-checked.** The document's hash pins everything; beyond
  that, code re-checks only what it holds its own independent copy of (the lookback, its operands,
  the burned-role table), because those can disagree without the document changing. Re-reading a
  value the hash already fixes would add a check no input can make fire.

- **B13f design fact — feature ORDER is part of a feature contract, not a presentation detail.**
  Two vectors with the same fields in different positions are the same set and a different matrix,
  and a model trained on one and scored on the other is wrong in every row while every set-equality
  check passes. The contract therefore hashes the order, and the materializer compares
  `list(features)` rather than `set(features)`. See `docs/FEATURE_VECTOR_SCHEMA.md`.

- **B13f design fact — an absolute slot number is a calendar index, not a property of a token.** A
  model given one can learn "later is better", which does not survive contact with a different
  window and is a split leak in a time-ordered evaluation. The relative spans B13a already computes
  (`slots_since_launch`, `slots_since_previous_launch`) carry the same information without the
  calendar, so no absolute slot is admitted as a feature.

- **B14a design fact — the split leak that t0 cannot see.** A decision at slot 1,950 sits safely
  inside a training range ending at 2,000, while its outcome is observed to 2,550 — inside a
  validation segment beginning at 2,500. The row is labelled by the period it is evaluated against,
  and nothing about its t0 says so. The purge is therefore computed on the label window end, and the
  fixture corpus holds two rows with the same t0 and different label windows so a test can show t0
  alone cannot separate them. See `research/B14A_SPLIT_AND_ARTIFACT.md`.

- **B14a design fact — creator and user must share one identity space.** An address that creates one
  token and trades another is one address. A grouping that keeps creator-space and user-space apart
  lets the same person appear under two labels and sit on both sides of a split while every check
  passes, so R5 pools them and closes the graph transitively.

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

**The operator surface.** `ui/operator_console.html` (`docs/OPERATOR_SNAPSHOT_SCHEMA.md`) renders
one canonical snapshot built by `scripts/b12b_operator_snapshot.py`. The architectural rule is that
**the browser computes nothing**: a UI that divides two integers to show a percentage has become a
second implementation of a research metric, and the two will disagree on the day it matters. So the
adapter assembles, validates and hashes; the page formats exact integers and exact
`[numerator, denominator]` pairs. It is a single self-contained file with no network primitive, no
form, no control that could submit or sign, and no wallet surface — properties checkable by reading
the file rather than by trusting it. It is **not operationally ready**: no pipeline feeds it and the
only shipped fixture is synthetic.

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
