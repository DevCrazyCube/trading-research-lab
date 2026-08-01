# Project Plan

## Mission

Research and, only if evidence supports it, build a selective Pump.fun trading system optimized for risk-adjusted executable return in an adversarial market. The system should survive rugs and manipulation through rejection, position sizing, liquidity-aware exits, and independent risk controls. It cannot guarantee profit or make rugs safe.

## Definition of success

Promotion requires all of the following:

- Positive net expectancy after protocol fees, creator/LP fees, base fees, priority fees, Jito tips, slippage, failed transactions, and unavailable exits.
- Chronological out-of-sample performance across multiple market regimes.
- Results not dominated by one creator, wallet cluster, token, or extreme winner.
- Calibrated risk estimates and acceptable drawdown under stress assumptions.
- Small divergence between simulated, shadow, and eventual live execution.
- Complete auditability from raw observation through decision and outcome.

Numeric thresholds remain research hypotheses until supported by data. They must not be optimized repeatedly on the final test set.

## Non-goals

- Guaranteed profit, an arbitrary 80% win rate, or maximum screenshot PnL.
- Blind launch sniping.
- Market manipulation, wash trading, deceptive promotion, or exploiting private information.
- Trading client funds or providing regulated services without separate legal review.

## Phases and gates

### Phase 0 — research specification

- [ ] Freeze definitions for graduation, executable return, drawdown, and liquidity failure.
- [x] Freeze the leakage constraints R1–R5 that every future rug/dump outcome label must satisfy.
  Rug/dump label construction remains in Phase 3; Phase 0 freezes the constraints, not outcome
  thresholds that cannot yet be selected without contaminated calibration.
- [ ] Choose initial regime: likely SOL-paired, non-Mayhem bonding-curve launches only.
- [ ] Define point-in-time and leakage rules.
- [ ] Define capital, position, daily-loss, and kill-switch policies.
- [ ] Obtain appropriate Netherlands/EU legal and tax advice before live operation.

Gate: labels, exclusions, and evaluation protocol are documented before model research.

### Phase 1 — historical and live recorder

- [ ] Start minimal raw live Geyser capture first; preserve processed/confirmed/finalized transitions, provider receipt timestamps, gaps, and orphan observations even before the final decoder exists.
- [ ] Benchmark Jetstreamer on a small Pump-heavy slot range.
- [ ] Enumerate Pump/PumpSwap program upgrades and configuration regimes with slot boundaries.
- [ ] Build a Pump/PumpSwap decoder from official IDLs with version tracking.
- [ ] Normalize historical Jetstreamer and live Geyser events into one schema.
- [ ] Store immutable raw records and canonical finalized state.
- [ ] Store observations separately from canonical events; retain multi-source/commitment observations and parentless never-canonical observations.
- [ ] Record sessions, gaps, heartbeats, slot statuses, clock synchronization, subscription hashes, and unknown frames.
- [ ] Reconcile exact pre-instruction reserves, integer quote outputs, payer balance deltas, fees, errors, and ordering against independent evidence.

Gate: deterministic replay; complete classified decode accounting; exact integer quote reproduction; and no unexplained reserve, cost, ordering, or slot-coverage divergence in a large randomized validation sample.

### Phase 2 — simulator

- [ ] Implement exact integer quote, fee, and rounding behavior by protocol version.
- [ ] Replay observed ordering and empirical latency distributions.
- [ ] Model failures, expiration, compute fees, tips, slippage, migration, and constrained exits.
- [ ] Produce optimistic, executable, and stressed outcomes.

Gate: deterministic reserve, quote, fee, rent, tip, and cost calculations reproduce eligible observations exactly at integer precision. Stochastic landing, contention, failure, and fill distributions reproduce forward observations within separately documented statistical tolerances.

### Phase 3 — wallet intelligence and labels

- [ ] Build point-in-time creator, trader, funder, and token histories.
- [ ] Create probabilistic wallet clusters with evidence and confidence.
- [ ] Calculate raw and cluster-adjusted concentration.
- [ ] Create executable return, drawdown-first, dump hazard, rug/dump, graduation, and liquidity
  labels, each satisfying the Phase 0 leakage constraints R1–R5.
- [ ] Add timestamped metadata/social observations without retroactive leakage.

Gate: label audit demonstrates that no post-decision information enters features.

### Phase 4 — models and policy

- [ ] Establish do-nothing, random, momentum, and curve-progress baselines.
- [ ] Start with logistic, tree, calibration, and survival models.
- [ ] Use purged chronological walk-forward evaluation and grouped uncertainty estimates.
- [ ] Put a deterministic risk veto above all model entries.
- [ ] Evaluate net expectancy, drawdown, calibration, capacity, and regime stability.

Gate: statistically credible improvement over baselines under executable and stressed simulation.

### Phase 5 — shadow and paper execution

- [ ] Run continuously through multiple market conditions.
- [ ] Preserve each feature vector, model version, decision, rejection reason, and intended order.
- [ ] Compare intended, simulated, and observable fills.
- [ ] Exercise feed failures, RPC disagreement, signer failure, and emergency shutdown.

Gate: stable forward performance and operational reliability; no retrospective decision rewriting.

### Phase 5b — devnet plumbing rehearsal

Runs alongside Phase 5, not instead of it. Devnet proves mechanics only.

- [ ] Construct, sign, submit, and confirm real transactions using free devnet SOL.
- [ ] Exercise ATA creation, compute-budget and priority-fee paths, blockhash expiry, retries, and failure classification.
- [ ] Exercise signer failure, kill switch, and emergency shutdown against a live cluster.
- [ ] Reconcile submitted transactions end to end.

Gate: mechanics are reliable and every failure mode is classified. **No devnet performance or profit figure may be reported as evidence of edge** — devnet has no real Pump market, competition, contention, or MEV.

### Phase 6 — tiny capped live trading

- [x] Explicit user authorization granted 2026-07-27, forward-looking and demo-first; see `DECISIONS.md`. It waives no gate below.
- [ ] Phases 1–5 gates met, plus the Phase 5b rehearsal.
- [ ] Use a dedicated limited wallet and independent risk service.
- [ ] Start with fixed tiny size, strict daily loss, and no automatic scaling.
- [ ] Reconcile every transaction and compare live performance with forecasts.

Gate: scaling requires a new recorded decision backed by substantial live evidence.

## Current status

Current phase: **Phase 0 / architecture research**, with the first Phase 1 measurement complete.

Completed:

- Established risk-adjusted executable return as the objective.
- Identified Jetstreamer as a strong historical-backfill candidate, not a live trading feed.
- Identified live Geyser/Yellowstone plus independent RPC and execution paths as separate needs.
- Reviewed 61 public memecoin-bot repositories and documented reusable components, recurring research failures, clone/security signals, and differentiation opportunities.
- **B0 partial — Pump program upgrade inventory measured against mainnet** (`research/B0_PUMP_PROGRAM_UPGRADE_INVENTORY.md`). The program is mutable and was last upgraded 2026-07-15. All 95 returned transactions were classified: 54 successful loader upgrades overall, including 15 in 2026 (13.36-day mean interval). Archival completeness and semantic/bytecode differences remain unverified, so loader events are not yet trading-regime boundaries.

- **B0b/c/d — current-regime interface measured on mainnet** (`research/B0B_CURRENT_INTERFACE_PROBE.md`). C2 verified on-chain: successful sampled transactions emit Anchor self-CPI `TradeEvent`s. Instruction mix changed radically between narrow windows, so no variant may be assumed dominant and all pinned-IDL variants must decode. The two initially unknown discriminators resolve to non-trades (`claim_cashback`, `create_v2`). Observed failure snapshots were highly unstable, supporting continuous measurement rather than a point estimate.
- **PumpSwap B0 partial** (`research/B0_PUMPSWAP_PROGRAM_UPGRADE_INVENTORY.md`). The primary-source program address is confirmed and all 31 public-RPC results classified: 23 successful loader upgrades, nine in 2026. The latest upgrade (2026-07-15 18:07 UTC) is followed about six minutes later by an official PumpSwap IDL/docs commit for pool virtual quote reserves, strongly identifying a semantic boundary. Archival completeness remains unverified.

- **B0e — `TradeEvent` decoded exactly against the pinned official IDL** (`research/B0E_TRADEEVENT_DECODE.md`). 26/26 events decoded with zero bytes remaining. Post-trade curve reserves are present in the event stream, so curve state is reconstructible without account snapshots. First exact economic invariant verified: `fee == ceil(quote_amount * bps / 10000)`, 25/25 and 11/11, ceiling rounding, zero mismatches. Observed 95/30 bps confirms the documented 1.25% split from on-chain data.
- **Historical retrievability confirmed.** `getBlock` serves boundary slots back to 2024 on the public endpoint, and Pump instructions decode from blocks straddling the 2026-07-15 upgrade. An archival provider is a throughput optimization, not a hard dependency.
- **B0f/g — all 54 Pump upgrade blocks swept in exact ledger order** (`research/B0F_UPGRADE_BOUNDARY_SWEEP.md`). All blocks and upgrade signatures were retrieved with zero errors. Same-block samples had traffic on both sides for only 29/54 boundaries, so short-window absence cannot identify interface removal. Adjacent blocks give two-sided coverage for all 15 boundaries in 2026. The July 15 post-window contains the first local observation of `collect_creator_fee_v2`, a candidate boundary signal rather than proof.
- **B2a/b — current-regime SOL curve arithmetic reproduced exactly** (`research/B2A_CURVE_CHAIN_CHECK.md`, `research/B2B_OFFICIAL_BUY_FORMULA.md`). The official exact-input formula resolves the naive buy mismatches: 11/11 sampled exact-input buys and 9/9 newly tested legacy exact-token buys reproduced exactly, alongside 49/49 sells from B2a. Non-Mayhem reserve chains were exact. Mayhem and non-SOL quote paths remain excluded/unverified.
- **B6 sizing estimate superseded** (`research/B6A_CAPTURE_VOLUME.md`, `research/B6C_RECORDER_PILOT.md`). The initial 94–172 GB/day storage conclusion omitted measured compression and is withdrawn. Polling JSON compressed 10.15× with zlib-6 and 27.03× with LZMA-1, making a 72-hour pilot plausibly affordable on reclaimed internal ext4 space. Actual Geyser protobuf volume and compression must be measured before fixing retention.
- **B6-lite recorder audited and corrected** (`research/B6C_RECORDER_PILOT.md`, `research/B6D_RECORDER_AUDIT_AND_COMPRESSION.md`). I3's missing-sequence hint and endpoint credential handling were fixed and regression-tested. Polling JSON is explicitly normalized—not a byte-identical provider frame—so raw fidelity remains a Geyser gate. Streaming per-segment throughput is 30.1 MiB/s zlib-6 and 20.6 MiB/s LZMA-1, both above the JSON snapshot's ~2.66 MiB/s projected input; codec/retention remain unfixed pending concurrent Geyser measurement.
- **Free push transport verified** (`research/B6F_FREE_PUSH_FEED.md`, `research/B6G_FREE_LOGS_AUDIT.md`). Public `blockSubscribe` is disabled, but free `logsSubscribe` accepts confirmed and processed Pump filters and sustained 88–537 notifications/s in separate 30-second windows. Raw notifications include failures and TradeEvent log payloads. Event-bearing-transaction coverage was 88.1%/94.1%; successful non-event traffic was primarily legitimate maintenance/claim activity. Geyser is no longer an immediate research blocker; metadata requires selective RPC backfill, while orphan/account-update evidence remains unavailable.
- **B7d/e — exhaustive historical cohort enumeration and mature lifecycle reconstruction complete** (`research/B7D_HISTORICAL_CREATE_ENUMERATION.md`, `research/B7E_MATURE_COHORT_LIFECYCLES.md`). The preregistered 2,000-slot window yielded 200 launches; all member histories completed below cap and 20,698 exact `TradeEvent`s were decoded. Seventeen tokens resumed after at least 24 hours of trade silence, so the withdrawn 24-hour `D_dead` remains invalid and no replacement is selected. The cohort is burned from model evaluation.
- **B7h — bonding-curve discovery recall verified for the burned cohort** (`research/B7H_BONDING_CURVE_RECALL.md`). All 2,000 preregistered slots were accounted for (1,996 blocks and four independently verified skips). Exact full-block decoding and bonding-curve histories matched bidirectionally on all 13,861 in-window `TradeEvent`s with zero decode errors, missing events, or extras. This removes the load-bearing recall caveat for B7e/B7g in this window; it does not select `D_dead` or generalize across regimes.

Next concrete task:

1. Implement B6-lite polling capture against the frozen schema and measure real compression, crash recovery, gaps, and local duty cycle.
2. Target USDC-paired samples to validate `quote_*` reserve chaining, fees, and rounding; keep Mayhem excluded until its non-trade mutations are captured.
3. Use B6-lite results to choose the rolling-raw/permanent-decoded storage split, then select a Geyser provider by required capabilities.
4. Re-run upgrade inventories against an archival RPC and compare available artifacts/IDLs at candidate boundaries.
5. Specify the initial tradable regime and label definitions.
