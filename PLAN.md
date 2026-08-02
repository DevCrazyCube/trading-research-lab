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
- [x] Initial regime frozen: SOL-paired, non-Mayhem Pump bonding-curve launches while the curve is
  open at decision time. Later graduation/migration is an outcome and execution risk, never an
  exclusion chosen with future knowledge. Initial entries are Pump-only; PumpSwap is not an entry
  venue, and any post-graduation exit remains unavailable until separately validated.
- [x] **First FRESH evaluation window preregistered before inspection**
  (`research/B11A_FRESH_COHORT_PREREGISTRATION.json`, committed alone before any chain query;
  `research/B11A_PREFLIGHT_AND_ORCHESTRATION.md`). Launch window **435,569,150 – 435,772,750**,
  observation cutoff **437,211,659**, every endpoint derived mechanically from the seven burned
  ranges and the B8b/B9d geometry inherited unchanged in slots. Disjointness machine-checked and
  failing closed. Preflight (one `getSlot`, no composition query) found the cutoff **not mature:
  557,100 slots remaining, about 2.69 days**; the window was not moved or shortened. Collection is
  planned and locked, and every path/label stage is refused until models, horizons and thresholds
  are frozen. **This is evaluation data, not tuning data.**
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

- [x] **First bounded slice implemented and measured** (`scripts/b10a_simulator_kernel.py`,
  `docs/SIMULATOR_RESULT_SCHEMA.md`). Deterministic direct-Pump kernel with a versioned read-only
  result schema, reusing B9i's proven integer functions rather than duplicating them. Replay gate:
  **92,510 of 92,510 eligible observed direct Pump trades reproduce at exact integer precision,
  zero mismatches** (743 out-of-regime observations counted and skipped). Entry and exit are direct
  Pump only; Mayhem, non-SOL quotes, a completed curve, oversize orders against the real reserve,
  and incomplete state all fail closed. Post-decision reserve state cannot reach entry pricing, and
  that boundary is structural rather than conventional. Priority fee, tip, landing, latency and
  slippage are caller-supplied or refused — never defaulted. **The stochastic half of the Phase 2
  gate is untouched: no landing, contention, failure or fill distribution is calibrated, so every
  result is labelled SIMULATED and none is executable.**
- [x] **Second bounded slice implemented and measured** (`scripts/b10b_position_path.py`,
  `scripts/b10b_path_dataset.py`, `docs/POSITION_PATH_SCHEMA.md`,
  `research/B10B_OBSERVED_PATH_VALIDATION.md`). A canonical **observed-state** position path
  evaluator: one entry priced by B10a at t0, then an executable-size-constrained exit mark at every
  later canonical observation for the same mint, with drawdown on realisable net exit value,
  liquidity states, reason codes, and caller-stated horizon/exit-rule outcomes that right-censor
  rather than score. Measured over the full 1,136-curve canonical reserve corpus: **1,136/1,136
  curves in strictly increasing canonical order, 884 paths evaluated over 91,296 marks, zero
  arithmetic errors**, a coverage partition summing exactly to 94,389 observations, and a
  byte-identical rebuild and re-validation. **Distinct schema label `SIMULATED_OBSERVED_PATH`**,
  because the later states are OBSERVED — from a world without our hypothetical trade — and are
  never called counterfactual. No reserve delta is added to any later state and no observed order
  is replayed: no trade variant makes that provably valid. **No profitability figure is computed
  and no entry is selected.** The stochastic Phase 2 gate remains untouched.
- [ ] Implement exact integer quote, fee, and rounding behavior by protocol version.
- [ ] Replay observed ordering and empirical latency distributions.
- [ ] Model failures, expiration, compute fees, tips, slippage, migration, and constrained exits.
- [ ] Produce optimistic, executable, and stressed outcomes.
- [x] **Read-only result schema exposed and consumed by a local console**
  (`scripts/b12b_operator_snapshot.py`, `docs/OPERATOR_SNAPSHOT_SCHEMA.md`,
  `ui/operator_console.html`, `research/B12B_OPERATOR_CONSOLE.md`). One versioned canonical
  snapshot combining pipeline/gate status, outcome labels, proposals, risk decisions, portfolio
  aggregates, evidence freshness, ratification and provenance. **Research calculations are not
  reimplemented in the browser: the page performs no arithmetic on data at all**, displaying exact
  integers and exact `[numerator, denominator]` pairs as they arrive. The adapter fails closed on
  floats, undeclared fields, credential-shaped strings, executable claims, stale-calling-itself-
  fresh, and every internal contradiction.

Gate: deterministic reserve, quote, fee, rent, tip, and cost calculations reproduce eligible observations exactly at integer precision. Stochastic landing, contention, failure, and fill distributions reproduce forward observations within separately documented statistical tolerances.

### Phase 3 — wallet intelligence and labels

- [~] **Point-in-time history foundation built; cohort collection specified, not executed**
  (`scripts/b13a_history.py`, `scripts/b13a_history_corpus.py`, `docs/HISTORY_SCHEMA.md`,
  `research/B13A_HISTORY_FOUNDATION.md`). Immutable canonical event schema (launch, trade,
  completion, funding transfer, each with source evidence hashes) and a pure as-of-t0 materializer
  for creator, trader/user, token and funding-edge histories. **Only events whose canonical
  coordinate is at or before t0 enter**, inclusive at t0 and exclusive one coordinate later, never
  insertion order. **Every count is named `_observed` and declared a lower bound**, because a
  bounded window cannot know what preceded it; `require_complete_history` fails closed for any
  policy needing a total. Identity strings never enter a feature block. Measured on the burned B8b
  corpus: 44,438 events including **35,568 funding edges decoded from the pinned System ABI**,
  25/25 subjects with the boundary respected, identities kept out of features and results
  independent of arrival order, zero errors — **and no feature value, distribution or correlation
  reported, on any window**. **Handoff 80 closed a decode-completeness seam**: coverage measured
  window geometry only, so a payload the extractor could not decode produced no event and an absent
  event was indistinguishable from one that never happened. Coverage now carries a
  `decode_accounting` that must partition three ways (transactions, System instructions,
  lamport-moving instructions), lists every piece of lost evidence with a coordinate and a reason
  code, refuses `complete` while anything is unresolved, and poisons a subject only when the
  unresolved coordinate is at or before *that subject's* t0. The pinned fixture found a real
  production crash — `except B9D.FreezeViolation` never matched the `B9J.FreezeViolation` actually
  raised, because each module loads its own graph by path. 54 mutants, 52 killed, two disclosed as
  equivalent. Clusters are NOT
  inferred and funding-cluster leakage remains an open gate. The cohort-based collection plan,
  including a preregistered lookback and completeness gate, is specified and awaits B11a unlocking.

- [~] **Actor association EVIDENCE LEDGER built; clustering still gated**
  (`scripts/b13b_association.py`, `scripts/b13b_association_corpus.py`,
  `docs/ASSOCIATION_SCHEMA.md`, `research/B13B_ASSOCIATION_LEDGER.md`). A pure point-in-time ledger
  of pairwise evidence over B13a identity roles and raw funding edges: six typed evidence kinds
  (exact address equality, direct transfer, shared funder, repeated counterparty, co-occurrence,
  co-signing launch roles), each carrying what it does NOT mean, each with canonical coordinates at
  or before t0 and a source hash per observation. **Four refusals are structural**: every link must
  be witnessed by evidence naming BOTH endpoints, so A—B plus B—C cannot manufacture A—C; exact
  identity is a separate relation type from association; any field whose NAME asserts a cluster,
  probability, score or owner is refused anywhere at any depth, and no float may appear; and
  `cluster_id`, `connected_component`, `merge_addresses`, `association_probability` and
  `cluster_adjusted_concentration` all exist and all raise. `confidence_status` is
  `uncalibrated_evidence_only` throughout. Counter-evidence is mandatory and an **unknown service
  role raises the flag rather than lowering it**, because a shared service wallet is the obvious
  false link. Incompleteness propagates from B13a and `require_complete_neighbourhood` fails closed
  per address. Measured on the burned corpus, structural counts only: 270 links and 10,988 evidence
  items over 12 focus addresses at 5 instants, 5/5 on boundary, witnessing, counter-evidence,
  identity containment and order independence, 60/60 neighbourhoods refused, 5/5 refusing
  operations verified to refuse, zero errors — **and no association degree or distribution
  reported, on any window**. 53 mutants, 53 killed, none disclosed. **The lookback, repetition
  threshold, probability calibration and merge threshold are specified and NOT chosen**; each needs
  its own preregistration before the actors it applies to are known. Clusters are NOT
- [ ] Create probabilistic wallet clusters with evidence and confidence.
- [ ] Calculate raw and cluster-adjusted concentration.
- [ ] Create executable return, drawdown-first, dump hazard, rug/dump, graduation, and liquidity
  labels, each satisfying the Phase 0 leakage constraints R1–R5.
  - **Label materializer built and measured, on a BURNED window** (`scripts/b10c_outcome_labels.py`,
    `scripts/b10c_label_corpus.py`, `docs/OUTCOME_LABEL_SCHEMA.md`,
    `research/B10C_LABEL_MATERIALIZATION.md`). One row per preregistered decision × horizon over
    B10b path records, with an exact-rational return and drawdown, explicit horizon geometry,
    censoring reasons, R5 grouping keys and evidence hashes. R1 is enforced structurally in four
    independent ways. **4,544 rows = 1,136 curves × 4 horizons, zero arithmetic errors, coverage
    preserved for every curve including the 252 we would not have entered, byte-identical reruns.**
    **The B9d/B10b corpus IS the B8b cohort, burned 2026-07-28, so R3 forbids measuring or tuning
    any label on it: no return distribution is computed and none may be.** No rug/dump threshold,
    profitability class or success label is constructed, and no split, model or baseline exists.
- [ ] Add timestamped metadata/social observations without retroactive leakage.

- [~] **External observation ledger built; no collection performed**
  (`scripts/b13c_observations.py`, `scripts/b13c_observation_fixtures.py`,
  `docs/OBSERVATION_SCHEMA.md`, `research/B13C_EXTERNAL_OBSERVATIONS.md`). An immutable,
  leakage-safe record of off-chain observations — token metadata, social posts, news articles,
  timestamped financial quotes and configuration facts — each carrying provider, provider
  observation id, query-spec hash, payload digest and byte length, fetch session and provenance,
  decoder name and version, licence and retention status, mapping evidence, and **four clocks kept
  apart**: event time, publication time, receipt time (wall **and** monotonic) and the on-chain
  effective coordinate. **The availability rule requires both clocks**: an item is feature-eligible
  at t0 only if we RECEIVED it at or before t0 AND its claimed publication instant is at or before
  t0 — receipt alone admits a future-dated item, publication alone admits the backfill. Unavailable
  and ambiguous clocks yield an unusable `Absent`, never a guess, and a claim carries the width of
  its own uncertainty so a date without a time is read at the latest instant it could mean.
  **Corrections, edits and deletions are new observations and never rewrite history**: as-of replay
  returns the version a decision actually knew and preserves every prior one, and a deletion
  received after t0 does not reach back and remove the text an earlier decision saw. `Absent`
  carries a reason and **raises on `bool()`** — unknown, unavailable, deleted and not-yet-known are
  four facts and none is zero. **A ticker is not a token**: exact mint/account binding is separated
  from name matches and provider claims, and `require_exact_binding` fails closed. Financial values
  live with their unit, quote asset, basis and effective time and never in a feature block; mixing
  units fails closed rather than converting, and the freshness bound belongs to the caller with a
  stated rationale. Licence and retention are checked against each other with `unknown` failing
  closed to hash-only. `sentiment`, `embedding`, `engagement_score`, `source_credibility`,
  `market_cap` and `call_language_model` all exist and all raise; **no language model is in the
  decision path**. Measured on synthetic fixtures only: 16 observations, 13 revision chains, 5
  replay instants, 80 observation-instant judgements, 13/13 chains validated, 5/5 on backfill
  refusal, deletion non-rewriting, version preservation and order independence, 6/6 refusing
  computations verified, zero errors — **and no content, distribution or derived quantity
  reported**. 76 mutants, 76 killed, none disclosed. **No network collection, no adapter, no
  credential, no vendor selected**; future adapter and credential/privacy rules are specified. The
  burned corpus and B11a were never opened.

Gate: label audit demonstrates that no post-decision information enters features.

### Phase 4 — models and policy

- [x] **Baseline evaluation contract frozen before any fresh label exists**
  (`research/B11B_BASELINE_EVALUATION_PREREGISTRATION.json`, committed alone;
  `docs/BASELINE_EVALUATION_SCHEMA.md`, `research/B11B_BASELINE_PLUMBING.md`). `model_family:
  none`, zero learned parameters, zero fitted thresholds. Frozen in advance: a 17-field t0 feature
  contract in which **no string may appear**, eight hard vetoes cross-checked against B10a's actual
  refusals, five non-adaptive policies (do-nothing, all-eligible fixed 0.1 SOL, a frozen-seed
  mint-hash random control, and the two arms of the creator-initial-buy partition), the four B10c
  horizons unchanged, whole-cohort metric definitions with no censored-as-loss shortcut, the single
  primary result, family size 16, eight validity requirements and five unlock requirements.
  Measured: **1,136/1,136 t0 feature records materialized on the burned-development corpus with
  zero leakage violations and no distribution inspected**; 31/31 mutants killed. Momentum and
  curve-progress baselines are NOT included — both would need a threshold, and no threshold may be
  chosen before labels exist. **Results are locked: U3 fails because nothing has been collected.**
- [ ] Establish do-nothing, random, momentum, and curve-progress baselines.
- [ ] Start with logistic, tree, calibration, and survival models.
- [ ] Use purged chronological walk-forward evaluation and grouped uncertainty estimates.
- [x] **Deterministic risk veto implemented above any model** (`scripts/b12a_risk_governor.py`,
  `docs/RISK_DECISION_SCHEMA.md`, `research/B12A_RISK_GOVERNOR.md`). Fail-closed library: eleven
  control families (kill switch, emergency state, evidence completeness/conflict/version/staleness
  in both slots and wall-clock, regime eligibility delegated to B11b, reserve capacity, order size,
  total and pending exposure, open-position and per-creator concentration, daily realised loss, and
  realizable-portfolio drawdown), 24 reason codes in a frozen precedence with all reasons reported.
  **It never resizes a proposal** — approve the exact order or reject it — because a governor that
  silently shrinks an order changes the thing being evaluated. Integer lamports and exact rationals
  only, no float; no limit defaults to zero or infinity; every unexpected failure refuses rather
  than approves; no state between calls. Measured: **36/36 mutants killed**, 76 tests.
  **Every cap is caller-supplied and `operator_unratified`** until treasury/risk authorization, and
  every record carries `NO_SIGNING_OR_SUBMISSION`.
- [ ] Evaluate net expectancy, drawdown, calibration, capacity, and regime stability.

Gate: statistically credible improvement over baselines under executable and stressed simulation.

### Phase 5 — shadow and paper execution

- [ ] Run continuously through multiple market conditions.
- [ ] Preserve each feature vector, model version, decision, rejection reason, and intended order.
- [ ] Compare intended, simulated, and observable fills.
- [ ] Exercise feed failures, RPC disagreement, signer failure, and emergency shutdown.
- [~] **Local read-only console built; not operationally ready and not fed by any pipeline.**
  Single self-contained file with no network primitive of any kind, no form, no control that could
  submit/approve/sign/execute, no wallet surface and no telemetry. Sections: status banner,
  kill-switch and halt state, overview, gate progress, opportunities with plain-language reasons,
  strategy and window warnings, simulated paths with liquidity and censoring, portfolio exposure and
  limits, evidence and provenance. Unknown values render as visibly unknown, never zero. Accessible
  (landmarks, table captions and scopes, skip link, live region, reduced motion, both colour
  schemes) and responsive. Verified by executing the page against a DOM stub, not only by reading
  it. Synthetic fixture only. Reconciliation and any live feed remain unbuilt.
- [ ] Ship the operator UI for overview, opportunities, explanations, positions, reconciliation,
  and hard risk controls. Keep signing material outside the browser and distinguish research,
  shadow, paper, and live modes unmistakably.

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
