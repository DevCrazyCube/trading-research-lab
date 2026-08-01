# Decision Log

Durable decisions belong here. Append new entries; do not rewrite old decisions merely because they were superseded.

Each entry carries two independent fields:

- **Status** — the *evidence* axis: `accepted` means the reasoning is settled; `provisional` means it awaits measurement and may be overturned by data.
- **Ratified by** — the *authority* axis: `agent-proposed` means only Codex and/or Claude agreed; `user` means the project owner approved it.

The two do not imply each other. A user-ratified decision can remain provisional pending a pilot, and ratification is never a substitute for evidence.

**Ratification does not authorize live trading.** Phase 6 in `PLAN.md` requires separate, explicit authorization that no entry below grants.

## 2026-07-27 — Optimize executable risk-adjusted return

- **Status:** accepted
- **Ratified by:** user (2026-07-27)
- **Decision:** Optimize net executable expectancy and survival, not win rate, raw chart return, or earliest possible entry.
- **Reason:** Fees, latency, failed transactions, slippage, and constrained exits can erase apparent returns. Big-hit and high-win-rate objectives also conflict.
- **Consequence:** All labels and reports must include costs and exit feasibility.

## 2026-07-27 — Recorder and simulator precede live trading

- **Status:** accepted
- **Ratified by:** user (2026-07-27)
- **Decision:** Build and validate complete recording, reconstruction, and execution simulation before live-buy logic.
- **Reason:** A model cannot be evaluated honestly without point-in-time inputs and executable outcomes.
- **Consequence:** Live trading remains out of scope until explicit promotion gates and user authorization.

## 2026-07-27 — Hybrid historical/live ingestion

- **Status:** provisional; benchmark required
- **Ratified by:** user (2026-07-27)
- **Decision:** Evaluate Jetstreamer for historical backfill, use live Geyser/Yellowstone for low-latency recording, and normalize both through one decoder/schema.
- **Reason:** Jetstreamer can replay historical transactions efficiently but lacks account-update events and is not a live execution feed.
- **Consequence:** Run a bounded feasibility benchmark and independent RPC reconciliation before committing.

## 2026-07-27 — Evidence-first model development

- **Status:** accepted
- **Ratified by:** user (2026-07-27)
- **Decision:** Begin with interpretable baselines, tree/logistic/survival models, chronological testing, and a deterministic risk veto. Do not begin with reinforcement learning.
- **Reason:** Interpretability and leakage detection are more valuable than model complexity at the current stage.
- **Consequence:** Complex models require demonstrated incremental executable value.

## 2026-07-27 — Separate canonical truth from observation history

- **Status:** provisional; validate during the live-capture pilot
- **Ratified by:** user (2026-07-27)
- **Decision:** Store canonical chain events separately from a many-to-one observation relation. Preserve repeated source/commitment observations and allow observed events that never become canonical to remain parentless with an explicit terminal classification.
- **Reason:** Historical replay describes later canonical truth, while a live strategy operates on delayed, partial, multi-source observations that can be rolled back. Collapsing them creates silent look-ahead bias and destroys orphan evidence.
- **Consequence:** Features consume a decision-time observation view, not canonical events directly. Historical oracle data must be degraded with an empirically measured observability model.

## 2026-07-27 — Capture raw provider frames before semantic decoding

- **Status:** provisional; validate during the 72-hour pilot
- **Ratified by:** user (2026-07-27)
- **Decision:** The minimum live recorder stores immutable raw frames plus minimal indexes, sessions, gaps, slot statuses, and clock samples. Use an enumerated provenance class rather than hand-assigned observation confidence.
- **Reason:** A decoder can be corrected and replayed; a dropped frame, outage, orphan, or corrupted timing interval cannot be reconstructed later.
- **Consequence:** Provider selection must document sequence/heartbeat and slot-status capabilities. Recorder downtime and unknown frames remain visible data.

## 2026-07-27 — Exact deterministic economics, statistical execution tolerances

- **Status:** accepted
- **Ratified by:** user (2026-07-27)
- **Decision:** Deterministic integer quantities—including reserves, quotes, protocol fees, rent, tips, and reconstructed payer deltas—must reconcile exactly for eligible cases. Only stochastic execution quantities may use documented statistical tolerances.
- **Reason:** A rounding tolerance would hide decoder or economic-model defects; landing and contention are genuinely stochastic.
- **Consequence:** The pilot may inform sample size, stratification, and named exclusions, but must not weaken exact-equality requirements.

## 2026-07-27 — Local-only operation

- **Status:** accepted
- **Ratified by:** user (2026-07-27)
- **Decision:** The system runs on the user's own machine. No hosted or cloud deployment, no public service, no externally reachable endpoint, and no colocation or deployment-region optimization.
- **Reason:** Stated project scope. The objective is a research instrument the owner runs locally, not operated infrastructure.
- **Consequence:**
  - Deployment-region latency, colocation, and hosting-cost questions are out of scope until the scope changes.
  - "Local" constrains where software and data live; it does not remove network access. Live Geyser/Yellowstone and Old Faithful historical data are inherently remote sources, so an upstream data provider is still required and still needs the sequence/heartbeat and slot-status capabilities recorded above.
  - Single-machine, single-recorder topology means there is no failover: any local restart, sleep, crash, or network drop is a real data gap. This *raises* the importance of the `gap` and `session` relations rather than lowering it, and the 72-hour pilot must measure realistic local uptime rather than assume continuous capture.
  - Retention is bounded by local disk, so the pilot's measured bytes-per-slot determines feasible subscription breadth.

## 2026-07-27 — Disk budget 100 GB; tiered retention required

- **Status:** provisional; the tier sizes are set by the B6 pilot's measured compression ratio
- **Ratified by:** user (2026-07-27) for the budget; the tiering is agent-proposed and follows from it
- **Decision:** Total local capture budget is **75–100 GB**. Because full-fidelity capture does not fit in that budget, storage is tiered: a **rolling raw-frame window** (short, re-decodable, aged out) plus a **permanent decoded-event store** (slim, kept indefinitely).
- **Reason:** Measured, not estimated. At full Pump-program breadth, raw transactions plus metadata run ≈**94 GB/day** (optimistic protobuf assumption) to ≈**172 GB/day** (JSON upper bound) — see `research/B6A_CAPTURE_VOLUME.md`. **100 GB therefore buys roughly one day** of undifferentiated capture. Decoded `TradeEvent`-class records run ≈**2 GB/day**, roughly 50× smaller.
- **Consequence:**
  - The `DECISIONS.md` principle "capture raw frames before semantic decoding" is **retained but bounded in time** rather than abandoned. Raw frames remain the authority for the rolling window, so a decoder bug found within the window is still fully repairable by replay.
  - Outside the window, decoded events are the only surviving record. **A decoder defect older than the window is unrecoverable**, which makes decoder correctness gates and the `unknown`-frame alarm rate materially more important than they would be with unlimited disk.
  - Indicative split within 100 GB: ~60 GB rolling raw (≈2–3 days compressed) + ~40 GB permanent events (≈20+ days, growing).
  - Compression is now load-bearing, not an optimization. The pilot must measure the achieved ratio rather than assume one.
  - This does **not** reopen `docs/schema/RAW_CAPTURE_SPEC.md`, which explicitly deferred retention to the pilot. It answers that deferred question.

## 2026-07-27 — Storage layout corrected against measured hardware

- **Status:** provisional; supersedes the tier sizes in the preceding entry, not its reasoning
- **Ratified by:** agent-proposed — **the corrected capacity figures need owner confirmation**
- **Decision:** Tier 1 (hot rolling raw frames) writes to the **internal ext4** filesystem at ~25 GB. Tier 2 (permanent decoded events) is written as sealed, SHA-256-checksummed, immutable segments to the **external drive** at ~100 GB.
- **Reason:** A hardware audit (`research/B6B_STORAGE_HARDWARE_AUDIT.md`) found three assumptions wrong. The external drive is **115 GB, not 200 GB**, and reports as a USB `FLASH DRIVE`. The internal disk is **89% full with only 52 GB available**, which was not part of the stated budget and is the binding constraint. Realistic total usable is **≈140 GB, not 300 GB**. Separately, the external drive is **exFAT, which has no journaling** — an interrupted write can corrupt directory structures rather than only the tail of the active segment, defeating capture-spec invariant I3's requirement that crash loss be bounded and detectable. Consumer flash also lacks the write endurance for a sustained ~2.8 TB/month capture load.
- **Consequence:**
  - The 60/40 GB split from the previous entry is **withdrawn**; it assumed internal space that does not exist.
  - Hot append-only writes never target removable or non-journaled storage. Sealed segments may, because their checksum sidecars make corruption detectable — the property that matters for a cold archive.
  - F20 stands and is strengthened: a 72-hour full-fidelity pilot needs 220–280 GB and still does not fit. **Tiering remains mandatory.**
  - Reformatting the external drive to ext4 would remove the I3 concern, but it is destructive and is the owner's decision alone.
  - `storage_detached` is proposed as an additional `gap.detected_by` cause. The frozen spec is **not** edited; per the agreed freeze, an observed pilot failure is the trigger.

## 2026-07-27 — Capacity no longer forces tiering; retention constants still unfixed

- **Status:** provisional; supersedes the capacity argument in the two preceding storage entries
- **Ratified by:** agent-proposed
- **Decision:** The claim that full-fidelity raw capture is unaffordable is **withdrawn**. Tiered retention is no longer *required* by capacity. No retention constants are fixed pending a Geyser-sourced re-measurement.
- **Reason:** Measured, not assumed (`research/B6C_RECORDER_PILOT.md`). Per-segment compression is **10.15x (zlib-6)** and **27.03x (lzma-1)**, against the 4x previously assumed. At 1,168 KB/block the full slot rate is 241 GB/day raw, i.e. **23.7 GB/day zlib** or **8.9 GB/day lzma**. A 72-hour full-fidelity pilot costs **27-71 GB**, not the 220-280 GB asserted in F20. Separately, 114 GB of disk was reclaimed, so ~166 GB is free.
- **Consequence:**
  - Tiering may still be adopted for bounded-replay and query-cost reasons, but not on affordability grounds.
  - The external USB drive is **not needed**. Both tiers fit on internal journaled ext4, which removes the exFAT crash-safety concern (F23) and the flash-endurance concern (F24) entirely.
  - Compression ratios were measured on RPC **JSON**. Geyser protobuf starts smaller but compresses less; the ratio must be re-measured before any constant is fixed.

## 2026-07-27 — Polling cannot be a recorder; Geyser is a hard requirement

- **Status:** accepted
- **Ratified by:** agent-proposed
- **Decision:** A polling `getBlock` recorder is validated as a **schema and mechanics test only**. It must never be used as the capture source for research data.
- **Reason:** Measured sustained throughput is ~0.35 blocks/s against ~2.5 slots/s produced — **~14% coverage**. The deficit is not random: it correlates with large, slow-to-serve blocks, i.e. the busiest and most information-rich ones, which is exactly the correlated-loss failure mode the project forbids.
- **Consequence:** An upstream Geyser/Yellowstone subscription is a hard dependency for Phase 1, not an optimization. The recorder's framing, sealing, integrity, session, gap, clock and crash-recovery machinery is source-agnostic and carries over unchanged.

## 2026-07-27 — Yellowstone gRPC is the recorder source; derived feeds are not

- **Status:** accepted (schema requirements verified against primary source); vendor choice open
- **Ratified by:** agent-proposed
- **Decision:** The live recorder subscribes to **Yellowstone gRPC** (Triton One's Dragon's Mouth schema). Derived/interpreted feeds — including Bitquery CoreCast — are rejected as the capture source. A derived feed may later be purchased as an optional independent cross-check oracle, never as the recorder.
- **Reason:** Verified from the primary source, `geyser.proto` in `rpcpool/yellowstone-grpc`, not vendor marketing. Yellowstone satisfies every recorded requirement: `SubscribeUpdatePing`/`Pong` heartbeat; a `SlotStatus` enum carrying `SLOT_PROCESSED`, `SLOT_CONFIRMED`, `SLOT_FINALIZED` and **`SLOT_DEAD`** plus a `dead_error` field; `account_include`/`account_required` server-side program filtering; native protobuf frames storable unchanged; and a `created_at` provider timestamp. It also carries account updates, which Old Faithful lacks. Bitquery CoreCast fails twice over: its `transactions` topic is documented as **finalized** transactions, which delivers exactly what history already gives us and defeats the entire purpose of live recording (C3); and its topics (`dex_trades`, `dex_pools`) are a vendor's *interpretation* of the chain, which `AGENTS.md` subordinates to exact on-chain decoding from official IDLs.
- **Consequence:**
  - `raw_frame.provider_seq` stays **null** for this source. Yellowstone gives a heartbeat, not a per-message monotonic counter, so gap detection rests on ping/pong liveness plus slot continuity. Spec v0.2 anticipated this ("never synthesize it").
  - Vendor selection is commercial, not technical — the schema is identical across vendors. Choose on **sustained-bandwidth policy**, not headline price: measured Pump-only traffic is ~241 GB/day raw, so a metered cap can cost more than a flat plan and, worse, a mid-month cap becomes a correlated capture gap of exactly the kind this project forbids.
  - The owner creates the account and holds the credentials. The recorder refuses to persist credential-bearing URLs, and that refusal is regression-tested.

## 2026-07-27 — No paid feed until evidence justifies it; research on free historical data first

- **Status:** accepted
- **Ratified by:** user (2026-07-27) — owner declined recurring cost
- **Decision:** Do not purchase a Yellowstone gRPC subscription now. Build Phases 3-4 (wallet intelligence, labels, models) on **free historical data** via `getBlock`/`getTransaction`, using **cohort-based** capture rather than firehose capture. Purchase execution-grade streaming only if and when a model shows credible edge under simulation.
- **Reason:** No provider offers Yellowstone gRPC on a free tier (checked: Chainstack, Helius, Shyft, Solana Tracker, dRPC, QuickNode); entry pricing is ~$49-200/mo. Meanwhile B0f established that `getBlock` serves history back to 2024 for free. Phases 3-4 need point-in-time *chain* data, which history supplies completely. Only Phases 2 (latency realism), 5 and 6 need observation-time data, which history cannot supply.
- **Consequence:**
  - **This partially inverts C3.** C3 argued live recording must start immediately because latency and orphan data have an irrecoverable wall-clock cost. That remains true, and is the price of this decision. The counterweight: paying monthly for months *before* knowing whether any edge exists is precisely the "buy execution infrastructure before evidence" pattern that `research/MEMECOIN_BOT_REPOSITORY_REVIEW.md` identified as the dominant failure across 61 public projects. If the research shows nothing, no money is spent.
  - **Hard constraint:** results built on historical data alone must never be reported as executable. Latency, contention, landing probability, and orphan behaviour are *not modelled* in this mode. Phase 2's executable and stressed views stay unavailable, and Phase 1's live-capture gate stays open.
  - Capture is **cohort-based**: select an unbiased set of tokens (all launches in a chosen historical window), then pull each token's complete history directly. Firehose block capture is not viable at free rate limits - the measured ceiling is ~0.35 blocks/s against 2.5 slots/s produced (F26).
  - Revisit when either a model earns it, or the owner's cost tolerance changes.

## 2026-07-27 — Free `logsSubscribe` push feed is the Phase 1 capture source

- **Status:** provisional; long-run stability unmeasured
- **Ratified by:** agent-proposed
- **Decision:** Capture Phase 1 research data from the **free public `logsSubscribe` WebSocket** with `mentions: [Pump]`. No paid subscription, no account, no credentials. `blockSubscribe` is unavailable on the public endpoint (`-32601 Method not found`).
- **Reason:** Measured over a 70-second continuous run: **17,071 notifications (243.8/s), 17,071 unique signatures, 2,003 TradeEvents decoded directly from logs, zero truncated logs, zero disconnects, 24.1 GB/day raw** (~2.4 GB/day at F27's 10x compression, so ~2 months in 166 GB). Pump emits `TradeEvent` via Anchor `emit!` into `Program data:` logs **as well as** via self-CPI, so the full event payload is available over this transport.
- **Consequence:**
  - **Corrects Seq 18.** I claimed `logsSubscribe` "cannot carry the C2 decode path at all". That was wrong; it carries the complete `TradeEvent`. C2's reasoning stands — logs are truncatable and self-CPI remains authoritative — but logs are a viable *transport*, with truncation a detectable risk rather than a disqualifier. A truncated-log detector must be wired to the `unknown`-frame alarm.
  - The stream **includes failed transactions**, which is exactly the landing-reliability data the research needs.
  - It does **not** carry fees paid, compute units, tips, account keys, balance deltas, slot status, commitment transitions, dead slots, or account updates. So cost reconstruction needs selective `getTransaction` backfill, and **orphan derivation (R2) and latency modelling (C3) remain impossible**. Phase 1's live-capture gate stays open and Phase 2's executable/stressed views stay unavailable.
  - Consistent with the preceding decision: research on free data now, buy execution-grade streaming only if a model earns it.

## 2026-07-27 — `D_dead` = 24 hours (PROPOSED — **WITHDRAWN**, do not ratify)

- **Status:** **WITHDRAWN 2026-07-27.** Do not ratify. Two independent defects found by Codex audit:
  (a) the derivation silently capped histories at six pages, so the 24.9 h p99.99 that justified the value was an artifact of truncated data — uncapped rerun gives p99.99 = 12.66 h;
  (b) the safety argument was inverted — the mint-signature proxy *splits* true trade-silence intervals, so a threshold drawn from it is too SHORT, i.e. anti-conservative.
  Per-token incidence, the original blocker, resolved at **3/30 tokens (10%)** — not negligible. `D_dead` remains **unset**. Superseded by `research/B7C_TRADE_ONLY_GAPS.md`.
- **Ratified by:** **agent-proposed — NOT user-ratified.** Nothing may be built on this until the owner approves it.
- **Decision (proposed):** The abandonment threshold `D_dead` is **24 hours** of trade silence. A cohort member with no `TradeEvent` for 24 consecutive hours, and no `CompleteEvent`, is labelled T2 abandoned.
- **Reason:** Derived from a **burned sample** (slots 435,566,652–435,566,690; 30 tokens, 81,974 gaps) that is permanently excluded from training, validation and test — see `research/B7B_DEAD_THRESHOLD.md`. Interior-gap p99.99 is 24.9 h, so 24 h sits at the distribution's knee; only 0.011% of interior gaps exceed it. Extending to 72 h triples the required observation tail to cut that to 0.0037%, which is a poor trade.
- **Consequence:**
  - **T2 is NOT absorbing.** The silence tail does not terminate — a token was observed resuming after **450.8 hours (18.8 days)**. "Abandoned" is a label, never a fact. A T2 token that trades again must be recorded as a **re-entry**, never silently reclassified and never dropped.
  - Per `docs/DEFINITIONS.md` C2, the launch window must end at least 24 h before the observation window ends, or abandonment rates are biased downward by window geometry alone.
  - Modelling must treat silence as a censored continuous duration (Phase 4 survival models); `D_dead` is for cohort bookkeeping, not for forcing a binary onto a censored problem.
  - Freezing is real: changing this value later requires a new entry stating why, and every result computed under the old value must be re-derived or discarded.
- **BLOCKER before ratification:** per-token incidence of ≥24 h gaps is **unmeasured**. Nine such gaps across 30 tokens could be nine distinct tokens (30% of the sample) or one erratic token nine times. Those imply very different misclassification rates. Measure before approving.

## 2026-07-28 — Graduation-anchor discovery recall validated for the B7j envelope

- **Status:** accepted for the tested envelope; **does not generalise**
- **Ratified by:** agent-proposed (Codex conditional approval 2026-07-27 21:44:30Z; Codex independent audit passed, `agent_discussion.md` Seq 63)
- **Decision:** The bonding-curve address-history discovery path is accepted as recalling graduation anchors (`CompleteEvent`, `CompletePumpAmmMigrationEvent`) **within the frozen 439-slot envelope `[435,564,885, 435,565,324)`**, on the pinned IDL `b90bc471…8e49`.
- **Reason:** Preregistered positive control, frozen at `4a5c3445…a333d1` **before** the run. Result PASS: 4 reference events and 4 candidate events, both event types present on both sides, `missing_from_candidate = 0`, `extra_in_candidate = 0`, 439/439 slots accounted for, zero decode and zero fetch errors. Independently recomputed from the artifact (`4ca3a1c9…373b`) twice — by Claude in Seq 62 and by Codex in Seq 63 — including slot-set equality rather than a count comparison. Path independence held: different RPC methods on different providers, fallback forbidden.
- **Consequence:**
  - **The recall direction is the load-bearing one.** `missing_from_candidate = 0` is purely empirical. `extra_in_candidate = 0` is **partly structural**, because the candidate path filters to the reference-discovered mint set and so cannot surface an event for another mint. The two directions are not equally strong evidence.
  - **Prohibited inferences, binding:** no prevalence, no performance, **no cohort inference** — the envelope sits ~5.5M slots after the B7e launch window, so this says nothing about whether any of the 200 B7e tokens graduated and **does not validate B7e's zero-anchor observation** through cutoff `435,570,000`; **no same-token or T1b inference**; no cross-regime generalisation.
  - **Common-mode decoder failure remains unexcluded.** Both paths share the pinned IDL and decode logic, so a mis-parsed graduation-event layout would be missed identically by both and still report agreement. This validates *discovery*, not *decoding*. No evidence in the project addresses it.
  - Two scanner defects remain unfixed and block safe reuse: candidate event rows are written only in a final batch (a mid-loop death loses them all), and the metadata-reuse resume path deletes all six data tables. **`scripts/b7j_positive_control.py` must not be run against the existing database until the second is fixed.**

## 2026-07-28 — Window 435,564,885–435,565,324 is BURNED

- **Status:** accepted
- **Ratified by:** user (2026-07-28)
- **Decision:** The B7j/B7k envelope `[435,564,885, 435,565,324)` is **burned**. It may never enter model training, validation, or test, and no performance number may be computed from it.
- **Reason:** Two results have come out of it, and the window itself was selected **outcome-positive** — chosen because it was known to contain graduation events. Any model figure derived from it would be measuring data that was picked for its outcome. Burning is the conservative call and costs nothing: the window's job was to validate instruments, and it did that.
- **Consequence:**
  - B7j (graduation-anchor discovery recall) and B7k (decoder common-mode) remain **valid as instrument validation** — burning the window does not retract them. It only forbids reusing the same slots for evaluation.
  - Any future cohort or evaluation window must be preregistered and **disjoint** from this range.
  - The B7e cohort `[429,998,000, 430,000,000)` was already burned; the two burned ranges are separate and both stand.

## 2026-07-28 — `D_dead` = 7 days (RATIFIED)

- **Status:** accepted
- **Ratified by:** **user (2026-07-28)** — "7 days 2.5% is fine", answering the gate raised in `agent_discussion.md` Seq 82.
- **Decision:** The abandonment threshold `D_dead` is **7 days (604,800 s) of trade silence**. A cohort member with no `TradeEvent` for 7 consecutive days, and no `CompleteEvent`, is labelled **T2**.
- **Reason:** This was never a research question. `research/B7G_COHORT_AUDIT.md` measured P(a silence of length *t* ever ends) at 12.1% (24 h), 5.3% (72 h), **2.5% (7 d)**, 0.5% (14 d), and found **no knee** — the curve decays smoothly, so no natural boundary exists to discover. Choosing `D_dead` is therefore selecting an acceptable **false-death rate** against the observation tail it costs. The owner accepted **~2.5%**.
- **Consequence:**
  - **T2 is NOT absorbing.** The silence tail does not terminate — a token was observed resuming after **450.8 hours (18.8 days)**. "Abandoned" is a label, never a fact. A T2 member that trades again is recorded as a **re-entry**, never silently reclassified or dropped.
  - **`docs/DEFINITIONS.md` C2 is now concrete:** the launch window must end at least 7 days before the observation window ends. In the authorised B8a window `[433,302,364, 433,304,364)` with its accepted ~10.96-day tail, this leaves **~3.96 days** of usable observation beyond the deadness call.
  - **A 14-day `D_dead` was unreachable in that cohort** (−3.04 days) and is recorded here so the point is not re-litigated. 7 days is the longest horizon that cohort supports.
  - Modelling still treats silence as a **censored continuous duration** (Phase 4 survival models). `D_dead` is cohort bookkeeping, not a binary forced onto a censored problem.
  - The withdrawn 24-hour proposal **stays withdrawn**; it was defective on both its percentile basis and its safety argument.
  - **Scope limit:** this ratifies **`D_dead` only**. `docs/DEFINITIONS.md` as a whole remains **unratified** — the terminal-state and censoring rules still await owner ratification, and `W_launch`/`W_obs` derive from the authorised B8a freeze rather than from this entry.
  - Changing this value later requires a new entry stating why, and every result computed under it must be re-derived or discarded.

## 2026-07-27 — Live trading authorized in principle, demo-first, gates unchanged

- **Status:** accepted
- **Ratified by:** user (2026-07-27)
- **Decision:** The owner authorizes eventual live trading, conditional on a demo-first staging ladder and on the existing Phase 0–5 gates. This authorization is **forward-looking**: it permits live trading to become reachable, it does not permit it now, and it waives no gate. It applies to the owner's own funds only.
- **Reason:** Direct owner instruction, with the owner's own stipulation that demo funds come first.
- **Consequence — "demo funds" resolves to three distinct stages that prove different things and are not substitutes for one another:**
  1. **Paper / shadow (Phase 5) — no funds at all.** Live data, real decisions, nothing submitted. Proves selection logic, forecast stability, and rejection behaviour. Cannot prove that an order would have landed or filled.
  2. **Devnet — free airdropped SOL.** Proves transaction construction, signing, ATA handling, compute-budget and fee mechanics, error paths, and emergency shutdown. **Cannot prove edge:** devnet has no real Pump market, no competing traders, no realistic contention, latency, or MEV. A devnet profit figure is meaningless and must never be reported as performance.
  3. **Mainnet tiny capped (Phase 6) — real funds, smallest viable size**, dedicated limited wallet, independent risk service, strict daily loss cap, no automatic scaling.
- **Consequence — the honest limitation, recorded so it is not rediscovered later:** there is no fake-money version of a real adversarial market. Devnet tests plumbing; paper tests decisions; only mainnet tests reality. This is a reason to run the demo stages, not a reason to treat passing them as evidence of profitability.
- **Consequence:** Stage promotion requires the `PLAN.md` gate for that phase to be met and a recorded decision. Scaling beyond the initial tiny cap remains a separate decision requiring substantial live evidence.

## 2026-07-27 — Proposed 24-hour `D_dead` remains unratified after proxy audit

- **Status:** correction; no threshold adopted
- **Ratified by:** agent evidence; owner decision not requested until the measurement is valid
- **Decision:** Keep `D_dead` unset. The prior 24-hour proposal is not promoted.
- **Reason:** An exact rerun of the burned sample with the silent 6,000-signature ceiling removed found that 3/30 tokens (10%) resumed after an interior silence of at least 24 hours. The earlier 0.011% per-gap framing obscured per-token incidence. More decisively, all mint-address activity is an anti-conservative proxy for trade silence: non-trade activity inserts timestamps and splits true `TradeEvent` gaps, so a threshold derived from it can be too short.
- **Consequence:** Derive the next candidate from `TradeEvent`-only timestamps in a second disjoint burned sample. Report both per-gap and per-token incidence, explicit pagination/capture caps, and re-entry transitions. No cohort result may treat 24 hours as adopted.

## 2026-07-27 — Historical cohorts are enumerated exhaustively from `CreateEvent`

- **Status:** accepted as research methodology; pilot validated
- **Ratified by:** agent evidence; consistent with existing no-left-truncation and exhaustive-window rules
- **Decision:** Historical cohort membership comes from every exactly decoded `CreateEvent` in an explicit half-open slot window. Enumeration is resumable and records every slot as retrieved, ledger-skipped, or visibly failed. Export requires zero unexplained gaps and exact equality between successful create instructions and decoded events.
- **Reason:** Selecting currently active or cheaply decodable tokens caused B7c's age/size selection bias. B7d validated the replacement on 500 historical slots: 496 retrieved, four independently verified ledger skips, 63 successful create instructions, 63 exact events, and zero decode/reconciliation failures.
- **Consequence:** No filtering by later activity, history size, graduation, or outcome may occur during cohort construction. Launch attributes remain recorded for later point-in-time policy analysis. RPC `-32009` alone never proves a skipped slot; `getBlocks` or independent evidence must resolve its “skipped or missing” ambiguity.

## 2026-07-27 — Mature lifecycle cohort does not set `D_dead`

- **Status:** accepted research result; no threshold adopted
- **Ratified by:** agent evidence under the preregistered B7e methodology
- **Decision:** Keep `D_dead` unset. The B7e cohort is permanently burned from training,
  validation, and test; it may generate a threshold candidate only for testing in a disjoint untouched
  window.
- **Reason:** Exhaustive enumeration produced 200 launches and uncapped TradeEvent-only reconstruction
  completed for all 200. Seventeen tokens (8.5%) resumed after an interior silence of at least 24
  hours, 11 after 48 hours, eight after 72 hours, and five after seven days. The longest resumed
  silence was 1,325,555 seconds (about 15.34 days). This directly contradicts an absorbing 24-hour
  interpretation and provides no same-sample license to select a replacement.
- **Consequence:** Model lifecycle duration as censored and record re-entry explicitly. Before any
  threshold is adopted, independently validate a preregistered candidate and independently verify
  the bonding-curve history discovery path and graduation anchors. See
  `research/B7E_MATURE_COHORT_LIFECYCLES.md`.

## 2026-07-27 — Bounded Codex–Claude CLI handoffs may run unattended

- **Status:** accepted
- **Ratified by:** user (2026-07-27)
- **Decision:** A single-process supervisor may alternate the installed Codex and Claude CLIs for
  safe repository research and implementation without requiring the owner to type “your turn.”
  `agent_discussion.md` remains the append-only handoff record and only one model runs at a time.
- **Reason:** The owner explicitly requested immediate reciprocal handoffs and wants to be involved
  only when a genuine user decision is necessary. Tmux provides crash persistence but not
  coordination by itself.
- **Consequence:** Structured `handoff`, `user_required`, `blocked`, and `complete` states control
  the loop. Duplicate supervisors, repeated no-progress turns, and excessive turns stop visibly.
  Autonomy does not expand authority: wallet operations, secrets, signing, transaction submission,
  funding, spending, paid services, deployment, destructive operations, and live/devnet execution
  remain hard user gates. See `AUTONOMY.md`.

## 2026-07-27 — Historical full-block scans use bounded single-block RPC scheduling

- **Status:** accepted engineering methodology
- **Ratified by:** measured failure and successful complete replay
- **Decision:** Full historical `getBlock` scans default to one block per JSON-RPC request, keep a
  bounded number of futures in flight, persist each completed slot durably, surface HTTP 403/429
  without retrying, and stop fail-closed on sustained throttling. Larger RPC batches require an
  explicit unsafe override.
- **Reason:** Twenty-block batches of multi-megabyte parsed blocks produced HTTP 413, and submitting
  the entire remaining window at once pinned gigabytes of completed responses behind earlier
  futures. With bounded single-block scheduling, B7h completed all 1,996 produced blocks plus four
  verified skips and reconciled 13,861 events exactly.
- **Consequence:** Transport failures remain visible checkpoint states and can never be interpreted
  as absent events. A partial or throttled scan returns nonzero and cannot publish a recall
  conclusion. See `research/B7H_BONDING_CURVE_RECALL.md`.

## 2026-07-28 — Decoder field assignment is validated against validator evidence, not against a second decoder

- **Status:** accepted research methodology + evidence
- **Ratified by:** B7k, preregistered and frozen before execution
  (`05704fc910b680c3136187b9326901faab8eae0283e2121181d0f36644334a07`)
- **Decision:** Decoder correctness is tested by comparing decoded **values** against evidence the
  validator produced — resolved account keys, `blockTime`, and exact payload consumption — never by
  comparing two code paths that share an IDL. Any future recall or decode cross-check must state
  which axes its two paths are independent on, and must not present a shared-decoder agreement as
  evidence about decoding.
- **Reason:** B7h and B7j compared two discovery paths that were independent on RPC method and on
  provider but shared one decoder and one pinned IDL. A wrong field offset, type width, or field
  order is invisible to both and still reports exact agreement, so every recall result in this
  project was conditional on a decoder nothing had tested. B7k found zero failures across
  8,075 `TradeEvent`s in 7,957 distinct transactions and 4 graduation events, on all three
  load-bearing checks, at zero network cost.
- **Consequence:** A gross layout error is ruled out for the checked fields, and B7h/B7j recall no
  longer rests on a wholly untested decoder. Three limits are binding on anything built downstream:
  membership is **not** identity, so two transposed pubkey fields still pass and are undetected; a
  self-consistent but wrong published IDL is undetectable offline; and fields with no independent
  witness (`sol_amount`, `mint_amount`, `pool_migration_fee`, `quote_mint`, `TradeEvent` reserves)
  are **unvalidated**, not passed. See `research/B7K_DECODER_COMMON_MODE.md`.

## 2026-07-28 — The B7j positive-control window spans two quote regimes, including USDC

- **Status:** accepted correction to recorded scope
- **Ratified by:** B7k C4, a preregistered non-load-bearing check whose prediction failed
- **Decision:** The B7j fixture pair must be described as spanning **two quote regimes**, not as a
  homogeneous SOL sample. `4R2Sxa8j…pump` carries `quote_mint = 11111111111111111111111111111111`;
  `5iHCTc3Q…pump` carries `quote_mint = EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` (USDC).
- **Reason:** C4 was frozen predicting `quote_mint` would be constant across the window. It is not,
  and this survived B7j's design, freeze, execution and audit unnoticed. Freezing C4 as
  **reported, not load-bearing** is why a correct decode was recorded as a finding rather than
  scored FAIL for a reason unrelated to decoding.
- **Consequence:** B7j's PASS is undisturbed — it measured discovery recall and both events were
  found on both paths. But the field named `sol_amount` differs by roughly four orders of magnitude
  between the two regimes, consistent with being denominated in the quote mint rather than in
  lamports. **That reading is an inference from two observations and is not established.** Any
  consumer of `sol_amount` must branch on `quote_mint` or be treated as unsafe. This is a concrete
  instance of the USDC-paired `quote_*` validation already open in `PLAN.md`.

## 2026-07-28 — A rerun may never destroy raw evidence implicitly

- **Status:** implementation policy adopted in `scripts/b7j_positive_control.py`; **not yet owner-ratified**
- **Ratified by:** pending owner review; adopted now because the alternative was leaving a known
  evidence-destroying path live behind a comment in `agent_discussion.md`
- **Decision:** A scanner that reuses an existing database must **fail closed** before clearing it.
  Two rules: (1) any database already holding data from an earlier run requires an explicit
  `--reset`; (2) a database holding a **completed** run — identified by a `metadata.summary` row —
  refuses reuse **even with `--reset`**. A finished artifact is moved aside by hand or a new
  `--database` path is used; no flag may overwrite it.
- **Reason:** B7j's rerun path deleted `event_row`, `run_error`, `raw_payload`, `raw_block`,
  `raw_history_page` and `curve_history` on any second invocation of the same command line. The
  *clearing* was correct — every run rescans all 439 slots, so retained partial state would
  contaminate the verdict — but doing it implicitly conflated derived state with **primary
  evidence**. Raw blocks, transactions and history pages cannot be re-derived; they are the audit
  trail a PASS verdict rests on. This is why the scanner has carried a standing "do not run against
  the existing database" warning since Seq 62.
- **Consequence:** The B7j database can no longer be destroyed by an accidental re-invocation, and
  the warning is now enforced by the code rather than by an instruction a future agent must
  remember to read. The same two rules should be applied to any future scanner that reuses a
  database; they are not specific to B7j.

## 2026-07-28 — Durable persistence is per unit of work, not per run

- **Status:** implementation policy adopted in `scripts/b7j_positive_control.py`; **not yet owner-ratified**
- **Ratified by:** pending owner review
- **Decision:** Decoded rows are committed in the same transaction as the raw payload they were
  derived from. No path may accumulate results in memory and write them in a single batch after
  its loop completes.
- **Reason:** B7j's candidate path committed each raw transaction as it was fetched but wrote the
  decoded `event_row` rows only after the whole candidate loop finished. Any crash, throttle or
  fetch failure therefore left a database in which `raw_payload` proved the transactions had been
  examined while `event_row` held **zero** candidate rows — a state indistinguishable from "we
  looked and found nothing". A silent-looking negative is exactly the failure mode
  `AGENTS.md` forbids.
- **Consequence:** An interrupted candidate path now leaves a truthful partial record instead of a
  misleading empty one. The final table contents of a completed run are unchanged.

## 2026-07-29 — Agent-pane identity upgrades fail closed on ambiguity

- **Status:** implementation policy adopted in `scripts/interactive_dashboard.py`.
- **Decision:** Claude 1/Claude 2 routing uses unique live tmux `@agent` pane tags. During legacy
  dashboard upgrade, an untagged pane may be migrated only from an explicit, non-conflicting
  legacy title. Two anonymous Claude panes are never assigned by pane id, sort order, position, or
  current TUI title. Duplicate tags, unknown tags, role collisions, and tag/title conflicts abort
  the upgrade before any identity tag or handoff is written.
- **Reason:** Pane titles are cosmetic and Claude overwrites them with activity text. The earlier
  routing incident persisted because a guessed/stale mapping looked healthy: both panes ran the
  same executable, so downstream liveness checks could not distinguish self-delivery from a real
  handoff. Seq 173's claim that the current tags were inverted was separately retracted in Seq 175
  after the reporting agent corrected its own identity; that retraction proves the live mapping is
  currently correct, but it does not justify retaining a migration path that can create a new
  authoritative mapping from anonymous pane order.
- **Consequence:** Existing correctly-tagged dashboards upgrade in place even when the TUI has
  replaced their titles. Ambiguous legacy dashboards must be restarted or explicitly identified;
  the tool refuses to convert uncertainty into durable routing state.

## 2026-07-28 — `W_launch` = 24 hours, `W_obs` = 8 days (RATIFIED)

- **Status:** accepted
- **Ratified by:** **user (2026-07-28)**, answering the gate raised in `agent_discussion.md` Seq 106/108/112/113 and put to the owner directly. This closes the last two unset parameters in `docs/DEFINITIONS.md` §4.
- **Decision:** The launch window `W_launch` is **24 hours**. The observation window `W_obs` is **8 days**.
- **Reason:** `W_obs ≥ W_launch + D_dead` is the constraint the definitions document imposes, and with `D_dead` frozen at 7 days the owner chose the **minimum** satisfying value: 1 + 7 = 8 days. This buys the shortest calendar delay before any T2 label is valid. It is a scheduling choice, not an empirical claim, and it was made **before any outcome in a candidate cohort was inspected** — which is the property that matters for a label parameter.
- **Consequence:**
  - **A T2 label is not valid until 8 days after the launch window opens.** A cohort launched today cannot be labelled until day 8; anything computed earlier is right-censored by window geometry alone, per C2.
  - **The cohort will be far too large to use whole and therefore REQUIRES a subsample.** B8a observed **242 launches in 813 s**, i.e. ~17.6/min, which extrapolates to roughly **25,000 launches per 24-hour window**. The extrapolation is from a single 14-minute window and is an order-of-magnitude estimate, not a measurement — but it is more than enough to establish that a subsample is unavoidable.
  - **The subsampling rule is a SEPARATE decision and is NOT ratified here.** It must be frozen a priori, before outcomes are inspected, exactly as this parameter was. **It must group by `creator ∪ user`, never by token or by time** — 50.4% of B8a members came from a creator with more than one launch in a 14-minute window (39.9% in the tradable, Mayhem-excluded population), so a naive split puts the same actor on both sides and lets a model learn actor identity. See `agent_discussion.md` Seq 104/105 and `research/B8A_COHORT_CENSUS.md`.
  - **Funding-cluster leakage remains unmeasured and is a superset of the above.** Two creator pubkeys funded from one source are one actor; nothing currently detects that. Recorded as a known gap, not as a solved problem.
  - **The authorised B8a cohort is unaffected.** Its window was pinned by its own preregistered freeze, and the entry above records that `W_launch`/`W_obs` derive from that freeze rather than from a general rule. This entry governs **future** cohorts.
  - Changing either value later requires a new entry stating why, and every result computed under the old values must be re-derived or discarded.

## 2026-07-28 — The project is under version control, with `.env` excluded before the first `git add` (RATIFIED)

- **Status:** accepted
- **Ratified by:** **user (2026-07-28)**, answering the gate raised repeatedly from `agent_discussion.md` Seq 104 onward.
- **Decision:** A git repository is initialised **inside `/home/anont/meme`**, with a local `.gitignore` excluding `.env`, `*.sqlite*` and `__pycache__/` **committed as the first commit, before any other file is staged**.
- **Reason:** The project had **zero** tracked files: `/home/anont/.gitignore` line 2 is `/*`, so the entire tree was ignored by the parent repository and `git ls-files` returned nothing. `agent_discussion.md`, `DECISIONS.md` and every research document had no backup, and a single bad fixture write would have been unrecoverable loss — a near-miss already occurred (Seq 96) and is what prompted `tests/_isolation.py`.
- **Consequence:**
  - **`.env` was protected only because everything was ignored.** Creating a repository removes that protection at the instant it is created, which is why the ordering above is a requirement and not a style preference. `.env` must never appear in `git ls-files`.
  - **Evidence artifacts (`*.sqlite`) are deliberately NOT tracked.** They are large, and their integrity is already established by the recorded SHA-256 hashes in this file and in the research documents. The irreplaceable material is the markdown record.
  - The parent repository at `/home/anont` is unaffected: it ignores `meme/` entirely, and a nested repository is independent of it.


## 2026-07-28 — B8b sample size: complete as frozen and report achieved precision (option A)

- **Status:** accepted
- **Ratified by:** **user (2026-07-28)** — *"go with A"*, answering the gate raised in `agent_discussion.md` Seq 129.
- **Decision:** The B8b run **completes exactly as frozen**. The realised `n` is reported whatever it turns out to be, together with the confidence interval that `n` actually supports. **No claim may be made at a precision the realised `n` does not support.** The sampling rule, the block size and the window are unchanged.
- **Reason:** The realised launch rate is running ~25% below the B8a extrapolation, so `n` is projected near **1,300** rather than the ~1,715 assumed in freeze §4. At n=1,300 the 95% half-width at p=1% is **±0.541 pp**, against a design bar of ±0.5 pp — a miss of 0.041 pp. `research/B8B_SUBSAMPLING_PREREGISTRATION.md` §4 had already pre-committed to this outcome: *"the realised `n` falls where it falls and is reported, whatever it is… not a reason to resize the sample mid-run."*
- **Consequence:**
  - **The freeze is NOT amended.** It stays at `56d8a83b…8374`. Option A requires no change to it, which is the point — amending an authorised freeze after learning its bar would be missed is the failure mode the discipline exists to prevent, even when the amendment tightens.
  - **The shortfall is itself a finding.** B8a's 25,718/day came from a single 13.6-minute window and the freeze labelled it *"not a measurement"*. A realised rate ~25% lower confirms that caveat, and vindicates freezing the **fraction** rather than a target count — had the count been frozen, the sampling would now be being stretched to reach it.
  - **The miss is narrow, and overstating it would be its own error.** At n≈1,300 the ±0.5 pp bar still holds for **every p ≤ 0.85%**; it fails only in a band around 1%.
  - **Option B (a second 24-hour window, n≈2,600, ±0.38 pp, ~6.2 h) was offered and not chosen.** It remains available later as a *new* preregistered decision, and would still be defensible on blinded-sample-size grounds only while no label or outcome exists.
  - **Option C — widening the precision bar to fit the realised `n` — was recommended against and is not adopted.** Moving a success criterion after seeing it will be missed is goalpost-moving regardless of the parameter involved.
  - `scripts/b8b_census.py` now prints the achieved half-widths and the largest `p` still meeting the bar, so the interval is reported with the count rather than left to a reader.

## 2026-07-28 — Window 433,894,233–434,097,833 (B8b) is BURNED for future cohort selection

- **Status:** accepted as a consequence of an existing ratified rule; **agent-recorded, not a new owner decision**
- **Ratified by:** not separately ratified. This applies `research/B8B_SUBSAMPLING_PREREGISTRATION.md` §7 — the clause that burned B8a — to B8b, on the same reasoning. Recorded here rather than only in the census because a burn that lives in one research document is a burn that the next window-chooser will not find.
- **Decision:** The B8b window `[433,894,233, 434,097,833]` is **burned for future cohort selection**. A later cohort may not be placed using knowledge of this window's composition, and these members may not be reused as evaluation data for a model whose window was chosen after reading the census.
- **Reason:** `research/B8B_COHORT_CENSUS.md` inspects this window's composition in detail — quote-regime split, Mayhem breakdown, per-stratum yield, actor concentration. Freeze §7 burned B8a for exactly this and the logic does not distinguish the two cases. **Selecting a new window with those numbers in hand is selection with outcomes partly in view.**
- **Consequence:**
  - **B8b remains fully valid as the cohort it was authorised to be.** Burning it does not retract the enumeration, the census, or anything computed under the frozen rule. It forbids one thing: using this window's contents to choose or justify a *later* window.
  - The burned-range list is now **seven** entries. Any future preregistration must check disjointness against all of them and fail closed, per freeze §6.1.
  - This burn is triggered by the census **existing**, not by anyone acting on it. It applies from 2026-07-28 regardless of whether the numbers are ever read.

## 2026-07-29 — Interactive handoffs use one Codex pane and one Claude pane

- **Status:** implementation policy adopted in `scripts/interactive_dashboard.py`.
- **Decision:** The dashboard has exactly two agent roles, `codex` and `claude`, plus a control
  pane. Released work routes to the other model from the author field in the append-only handoff
  log. Pane identity remains bound by the durable tmux `@agent` tag. Startup requires the expected
  foreground executable to remain alive through initialisation before reporting success.
- **Reason:** Two identical Claude executables made identity and self-delivery failures hard to
  observe, while the owner explicitly selected one Codex and one Claude. Author-based routing is
  deterministic after restarts and does not depend on stale `active_agent` state. The stability
  check closes the observed failure where Codex briefly started, exited, and its identity prompt
  was typed into the returned shell.
- **Consequence:** Legacy two-Claude sessions must be restarted rather than guessed into the new
  topology. Codex uses the owner-specified no-approval, workspace-write command with its startup
  update check disabled. Environments that mount Codex's state database read-only fail visibly
  and require that command to be launched from the host terminal.

## 2026-07-29 — Composer detection is per-application and read from the bottom of the pane

- **Status:** implementation policy adopted in `scripts/interactive_dashboard.py`.
- **Decision:** `composer_text()` scans a pane's capture from the **last** line upward and
  recognises both agents' prompt glyphs — Claude Code's `❯` (U+276F) and Codex's `›` (U+203A).
  Any probe of a pane's *user interface*, not just this one, must be checked against both
  applications before the two-model topology can rely on it.
- **Reason:** Both TUIs echo a **delivered** user message back into the transcript behind the same
  glyph the composer uses, so a top-down scan returned the echo of the message that had just
  landed. `send()`'s post-condition then read a successful delivery as "still sitting in the
  composer", raised, and the supervisor left the Seq unconsumed and retried forever, pressing bare
  Enter into the pane each pass; `supervisor.log` holds eleven identical "typed into pane %1 but
  NOT submitted" lines for one delivered handoff. Matching only Claude's glyph was the same defect
  inverted: for the Codex pane `composer_text()` returned `""` for every capture, so the
  post-condition was not wrong but **inert**, and every send into Codex was recorded as delivered
  whether or not it was. The one-Codex/one-Claude rebuild changed which application occupies the
  second pane without revisiting the Claude-specific probes written against it.
- **Consequence:** Delivery verification is live in both panes and stops inverting on success. An
  empty Codex composer reports its greyed placeholder rather than `""`; that is harmless for the
  only caller, which asks whether a prefix of the pending text appears in the message being sent.

## 2026-07-29 — An open ownership claim protects an agent from supervisor interrupts

- **Status:** implementation policy adopted in `scripts/interactive_dashboard.py`.
- **Decision:** Before dispatching, the supervisor computes `open_claim_holders()` — the agents
  whose most recent `agent_discussion.md` entry claims ownership and has not released it. Neither
  the outgoing `active_agent` interrupt nor `send_handoff`'s busy-target interrupt may send `C-c`
  to such an agent. Delivery still proceeds; it simply waits for the pane to go idle.
- **Reason:** AGENTS.md makes a claim binding until its author releases it, but the dispatcher read
  only the *latest* entry, so an outstanding claim was invisible to it. Routing is by author, so
  the moment either agent appends a release the other is handed work — and `agent_busy()` cannot
  distinguish stale UI state from claimed work in flight. Seq 182 records the supervisor
  interrupting an active Claude for exactly this reason; the rebuild changed the topology and kept
  the interrupt, leaving the same edge live against a Codex pane 200 curves into a claimed B9b run.
  Waiting costs little, because an undelivered handoff already leaves the Seq unconsumed and
  retries; destroying a colleague's in-flight measurement to deliver a message sooner is the worse
  trade, and AGENTS.md requires preserving work over convenience.
- **Consequence:** An agent that claims an area and then stops writing entries will not be
  interrupted by the supervisor at all. That is intended — the release entry is what ends a claim —
  but it means a genuinely stuck claimant needs the explicit `interrupt` command, which is
  unchanged and remains available to the owner.

## 2026-07-29 — B9d transaction-body reconstruction frozen before execution (NOT authorised to run)

- **Status:** methodology frozen; **execution requires a new owner authorisation that does not yet
  exist**.
- **Ratified by:** not separately ratified. Preregistered under the same discipline as B9c, before
  any transaction body was fetched or inspected. Full text:
  `research/B9D_TRANSACTION_BODY_PREREGISTRATION.md`.
- **Decision:** B9d fetches and classifies exactly the 94,985 distinct successful in-window
  signatures of the tradable non-Mayhem B8b population, derived by one pinned query against the
  B9c artifact at its pinned SHA-256. Byte-exact response bodies are primary evidence; every
  instruction is classified at every nesting level against a pinned IDL **revision**; unknown
  discriminators fail visibly; reserve paths are assembled in canonical
  `(slot, transaction_index, outer_instruction_index, inner_instruction_index)` order and never by
  insertion order. No token, creator, activity-size, history-size, graduation, terminal-reserve, or
  outcome filter may reduce the fetch set, and no event-name shortcut is authorised.
- **Reason and the three things this freeze adds beyond B9c's request:**
  - **The population was re-derived before being frozen.** All eight of B9c's published figures
    reproduce exactly from the artifact, with zero contradictory `err` statuses, zero signatures
    straddling the Mayhem/tradable split, and zero curves present in B9c but absent from B9a.
  - **A predicate trap is frozen against.** `err_json` stores `json.dumps(err)`, so success is the
    string `'null'` and the column is never SQL `NULL`. The natural `err_json IS NULL` test
    classifies all 1,347,469 signatures as failed while reproducing every other published figure —
    a clean, plausible, entirely wrong table. B9d must assert the population equals 94,985 before
    fetching anything.
  - **Program-version coverage is a check, not an assumption.** B0 puts the last Pump deploy at slot
    433,095,571, 798,662 slots before the window opens — but B0 ran 2026-07-27 ~10:15 UTC and the
    cutoff slot's block time is 12:19:42 UTC the same day, so the inventory misses the window's
    final ~2 hours, and its ProgramData history has unverified archival completeness. B9d
    re-verifies boundaries across `[433,894,233, 435,536,742]` and decodes version-aware if any
    exists.
- **Consequence:**
  - **Two scope limits are stated in advance rather than discovered.** Curve histories are
    address-indexed and their exhaustiveness for this window is *inherited* from B7h's different
    window and regime, which `PLAN.md` says does not generalise; B9d must either run a
    preregistered-sample recall check or publish an unhedged caveat. And reserve paths end at
    graduation by construction, because post-migration PumpSwap activity need not touch the curve
    address — 16 of the tradable population are affected and must be labelled truncated.
  - **Cost is a gate, not a footnote.** ~10.6 continuous hours and ~0.95 GB at B6j's measured rate,
    against a standing authorisation (Seq 121) of 4 min/hour for ~6.2 hours granted for B8b.
    Freezing the method is free; running it is not, and the second does not follow from the first.
  - A high classification-failure rate is a publishable result. Reporting a partial classification
    as if it were complete is the recurring failure this project has documented twelve times.

## 2026-07-29 — B9d canonical ordering adds 38,853 block lookups; recall claim remains withheld

- **Status:** accepted pre-execution methodology correction; execution still not authorised
- **Ratified by:** agent audit before any B9d transaction body was fetched
- **Decision:** B9d cannot derive `transaction_index` from `getTransaction`. It must preserve
  `getBlock` signature lists for every distinct involved slot and map each frozen signature to one
  unique zero-based list position. The frozen 94,985-signature population spans **38,853 distinct
  non-null slots**, so the minimum request count is 133,838 before boundary verification. B9d also
  freezes the conservative branch for address-index recall: it publishes no exhaustiveness claim;
  any recall experiment is a separate preregistration, never a sample chosen after bodies are seen.
- **Reason:** The original freeze required the full canonical key while specifying no evidence
  source for transaction index, leaving insertion/fetch order as the only implementable fallback —
  explicitly forbidden by AGENTS.md. Its recall section also left both branch choice and sample
  size free, so it was not a freeze. Offline B9c re-derivation gives 94,985 signatures, 38,853 slots,
  and zero null-slot rows without inspecting a transaction body.
- **Consequence:** B9d's exact request floor is **133,838 calls**, plus boundary verification. The
  transaction component retains B6j's separate ~10.6-hour estimate. **14.9 hours is only a scenario
  assuming `getBlock` signatures sustain the `getTransaction` rate**, not a lower bound; block-call
  throughput and volume are unmeasured. Only transaction-body volume has the prior ~0.95 GB
  estimate. Owner authorization must cover this corrected scope and endpoint. See the Seq 197 amendment in
  `research/B9D_TRANSACTION_BODY_PREREGISTRATION.md`.

## 2026-07-29 — Handoff submission uses bounded TUI acceptance polling

- **Status:** accepted collaboration-infrastructure correction
- **Decision:** After pressing Enter, the dashboard polls for up to five seconds and accepts either
  composer clearance or the agent TUI's busy marker as proof that the turn started. A draft that
  remains after the bounded window still fails visibly and leaves the handoff sequence unconsumed.
  Supervisor liveness is verified from the host control pane's job table; sandbox `/proc` and
  `os.kill` checks are not valid for host PIDs across namespace boundaries.
- **Reason:** PID 285256 was alive in the authoritative control-pane `jobs -l`, disproving the
  sandbox PID diagnosis in Seq 208. The real log showed accepted handoffs being reported as
  pending because a single check after 0.6 seconds raced Claude Code's composer redraw. The target
  pane subsequently showed the handoff in its transcript and an active turn.
- **Consequence:** slow-but-real submissions are recorded once instead of retried indefinitely;
  genuinely stuck drafts remain fail-closed. Restarting the watcher is still a controlled host-pane
  operation and must never be inferred from namespace-local PID visibility.

## 2026-07-29 — B9d read-only historical collection authorized

- **Status:** owner-authorized execution decision (agent_discussion Seq 218)
- **Decision:** Run the frozen B9d workload against the existing credentialed RPC endpoint from the
  ignored environment: 94,985 `getTransaction` calls, 38,853 `getBlock` signature calls, and the
  required boundary/preflight evidence. The run is resumable and may take roughly 15 hours; that is
  a scenario, because block-call throughput was previously unmeasured.
- **Reason:** The owner explicitly authorized continuing without further approval to finish the
  project after being shown the exact request floor, endpoint choice, and duration estimate.
- **Consequence:** Endpoint credentials remain excluded from commands, logs, artifacts, and commits;
  only a query-free endpoint reference is recorded. This authorizes read-only historical evidence
  collection only. It does not authorize wallets, signing, transaction submission, spending,
  deployment, or live/devnet trading, whose PLAN gates remain binding.

## 2026-07-30 — Phase 0's objective definitions drafted; the rug/dump phase conflict is an OPEN OWNER DECISION

- **Status:** **proposal, NOT ratified.** Full text: `docs/EXECUTABLE_RETURN.md` v0.1. No parameter
  is frozen by it and nothing in it may be treated as adopted because it exists.
- **Gap it addresses:** `PLAN.md` Phase 0 requires frozen definitions for "rug, dump, graduation,
  executable return, drawdown, and liquidity failure", and gates model research on labels and
  evaluation protocol being documented. `docs/DEFINITIONS.md` (RATIFIED v0.3) closes **graduation**
  and the censoring rules. **Executable return, drawdown and liquidity failure were defined in no
  document in this repository** — so the objective every promotion gate is stated against was
  unspecified while Phase 1 measurement proceeded.
- **Proposed definitions, grounded only in measured quantities:**
  - **Executable return** as an exact integer-lamport round trip net of every cost `PLAN.md` line 11
    enumerates, explicitly **including transactions that failed** — B9c measured only **94,985 of
    1,287,248 (7.38%)** distinct in-window tradable signatures as successful, so a cost model
    pricing only successes prices a market that does not exist. Integer exactness is not aspirational:
    B2a/B2b reproduced 11/11 exact-input buys, 9/9 legacy exact-token buys and **49/49** sells, and
    B0e verified `fee == ceil(quote_amount * bps / 10_000)` at 95/30 bps with zero mismatches.
  - **Drawdown** on the **executable exit value** path, never on quoted price, and meaningless
    without a stated position size. B9a measured median terminal `real_quote_reserves` of
    **0.0000 SOL** with **94.6% under 0.01 SOL**; a price-marked series there reports orderly
    decline where nothing could be sold.
  - **Liquidity failure** split into three conditions — no counterparty at any size, constrained
    exit, and structural unavailability (curve `complete`, T1b, or the transaction cannot land.)
    Reporting them as one number is the mistake B9a's F2 made.
- **Deliberately NOT frozen, and why:** the "no counterparty at any size" threshold depends on
  position size and the cost floor of a landed transaction. Choosing a number now, with B9a's
  outcome distribution already published and in view, would be selecting a definition after seeing
  outcomes — the exact move preregistration exists to prevent, and Seq 178 already recorded one
  covariate contaminated this way. It must be frozen a priori and **never measured on B8b**.
- **OPEN CONFLICT REQUIRING THE OWNER.** `PLAN.md` line 31 places **rug** and **dump** in Phase 0.
  `DEFINITIONS.md` §2 deliberately defers them to Phase 3, because a rug label recognised from
  post-collapse behaviour is a leakage vector. **Both cannot hold.** AGENTS.md forbids silently
  selecting the more convenient claim, so neither was applied and rug/dump remain undefined. The
  owner must either amend `PLAN.md` line 31 to move them to Phase 3, or state that Phase 0 requires
  a leakage-safe rug definition and cannot close without one. **Phase 0 cannot be marked complete
  either way until this is resolved.**
- **Consequence:** the objective is now written down and auditable, and its unmeasured components
  (landing, contention, tip and slippage distributions; the reserve path B9d is collecting) are named
  rather than assumed. No return, drawdown or liquidity figure may be computed for the B8b cohort
  until B9d publishes the reserve path.

## 2026-07-30 — Rug/dump constraints freeze in Phase 0; label construction remains in Phase 3

- **Status:** accepted project-methodology decision; thresholds remain explicitly unfrozen.
- **Ratified by:** owner continuity directive on 2026-07-30, implemented after independent Codex
  review of Claude's owner-ready Option A audit (`docs/PHASE0_RUG_DUMP_RECOMMENDATION.md`).
- **Decision:** Phase 0 freezes the following constraints for every future rug/dump outcome label;
  Phase 3 constructs the labels after a fresh preregistered cohort and appropriate path evidence
  exist.
  - **R1 — point-in-time separation:** fix decision instant `t0` at the feature-vector timestamp;
    the label window is `(t0, t0+H]`, and no feature may read an observation made after `t0`.
  - **R2 — no outcome-informed definition:** freeze every definition and threshold before measuring
    it on an evaluation cohort.
  - **R3 — burned-cohort exclusion:** never measure or tune the label on B8b; use a fresh
    preregistered window disjoint from every burned range.
  - **R4 — horizon geometry:** members unable to reach horizon `H` are right-censored, never dropped
    or labelled negative.
  - **R5 — actor grouping:** split at least by `creator ∪ user`; funding-cluster leakage remains an
    unmeasured superset and therefore an open gate.
- **Evidence:** `PLAN.md` already separates Phase 0 definition from Phase 3 construction for
  graduation, executable return, drawdown, and liquidity labels. A future outcome is valid label
  evidence but is forbidden from the historical feature vector. A full rug/dump threshold cannot
  be selected honestly yet because it needs magnitude and horizon choices informed by reserve-path
  evidence B9d has not published; B8b's outcomes are already visible and burned.
- **Consequence:** the prior wording conflict is resolved without inventing thresholds. T1b,
  Mayhem exclusion, overlap with liquidity-failure labels, horizon `H`, and whether rug is one label
  or several remain open questions for Phase 3. This decision does not authorize model research,
  live execution, or treating post-decision state as a feature.

## 2026-07-30 — Anchor CPI events are decoded and parented before reserve materialization

- **Status:** accepted offline decoding invariant; reserve reconstruction remains incomplete.
- **Decision:** A target self-CPI beginning with Anchor event tag `e445a52e51cb9a1d` is decoded
  exactly as `[event tag][IDL event discriminator][Borsh body]` against the pinned program revision.
  It is recorded as a named event instruction, not an unknown target discriminator. Its mutating
  parent is the most recent instruction at stack height `h-1` within the same outer instruction;
  missing stack height or parent is a visible failure, never a nearest-name guess.
- **Evidence:** Read-only validation on the first 1,000 preserved B9d bodies decoded and associated
  1,047 CPI events with zero failures: 380 `TradeEvent`s from height 1→2, 614 from 2→3, two from
  3→4, and 51 non-trade events. This is a bounded point-in-time structural observation, not a
  completeness or economic result.
- **Consequence:** Event post-state evidence can now be attributed to the actual invoking
  instruction across nested CPI. `reserve_observation` remains unpopulated until exact pre-state,
  non-trade mutation, and transaction balance reconciliation are implemented; event presence alone
  never proves complete reserve coverage.

## 2026-07-30 — Automatic handoffs are terminal-only and post-submit uncertainty is at-most-once

- **Status:** collaboration-infrastructure policy adopted after a live duplicate-delivery failure.
- **Decision:** Only entries whose status is a terminal handoff/release/completion route
  automatically. A failure proven to occur before typing remains retryable. Once the text has been
  submitted but TUI acceptance is uncertain, the sequence is quarantined and consumed rather than
  replayed; the append-only discussion log remains the recovery source.
- **Evidence:** Seq 248 reached Codex repeatedly while supervisor state remained at observed Seq
  247. The earlier requested-action widening also classified 39 historical non-terminal entries,
  including ownership claims/resumptions and active collection, as task briefs.
- **Consequence:** automatic delivery prefers at-most-once behavior after submission, preventing a
  prompt flood. Explicit mid-work requests must be directly prompted by their author; completed
  assignments continue to route automatically.

## 2026-07-30 — Automatic handoffs carry the released entry and never interrupt turns

- **Status:** collaboration-infrastructure policy adopted.
- **Decision:** The supervisor sends the complete released `agent_discussion.md` entry as the next
  model's input, framed with sender and receiver identities. Automatic routing never sends `C-c`
  to either source or target. If the target is busy, the sequence remains unconsumed and delivery
  retries after the target becomes idle; no draft is typed into an active composer.
- **Reason:** A generic “read the latest handoff” prompt hid the actual brief and introduced a race
  with later log entries. Interrupting the source made completed conversations visibly terminate,
  while interrupting the target could destroy unrelated claimed work. Sequential automation needs
  message delivery, not terminal preemption.
- **Consequence:** The append-only log remains the audit record and the actual entry becomes the
  wire message. A non-terminal coordination entry with a real `Requested action` is also delivered
  immediately; `none`, audit-only notes, and active ownership claims remain log-only. Handoffs may
  wait for a long turn to finish, but they do not corrupt or terminate either conversation.
  When a large literal paste remains staged after the first Enter, the sender issues exactly one
  second Enter only if the same handoff is still in the live composer and no busy marker exists.

## 2026-07-30 — Bonding-curve reserve paths are anchored, self-checking, and irreparable after gaps

- **Status:** accepted offline reconstruction invariant; publication remains gated on completion of
  the frozen B9d body population.
- **Decision:** Pump `CreateEvent` supplies the launch anchor. Each later Pump `TradeEvent` supplies
  an exact post-state and independently derives its pre-state from its signed token/quote deltas.
  The derived pre-state must equal the preceding observed post-state. A disagreement emits a
  `classification_failure`, permanently breaks that curve's chain, and is never smoothed or
  repaired by a later matching event. PumpSwap pool reserves remain a separate quantity.
- **Balance evidence:** Aggregate signed `TradeEvent.quote_amount` per curve and transaction must
  equal that curve account's lamport delta when no account-lifecycle instruction touches it.
  `create_v2` and `extend_account` transactions are explicitly marked confounded because their
  lamport delta also contains rent funding; no measured rent constant is subtracted as a repair.
  For non-SOL quotes, lamports are inapplicable: resolve the pinned IDL's
  `associated_quote_bonding_curve` role and compare exact raw `preTokenBalances`/
  `postTokenBalances` units for the declared quote mint and token program. UI amounts are never
  evidence; missing sides mean zero only when that account's corresponding lamport balance is zero.
- **Evidence:** On the first 37,396 preserved bodies, independent replay found 21 discontinuity
  rows across 10 curves. The implementation preserves the first 10 mismatches and the 11 downstream
  rows as permanent-break failures. In a separate first-5,000-body balance replay, 4,956 curve-
  transaction checks were exact and 38 were lifecycle-confounded, with zero clean mismatches.
  These are bounded interim measurements, not full-population results.
- **Subsequent verification:** On 45,745 preserved bodies, 43,448 native-quote checks and all 19
  non-SOL quote checks reconciled exactly; 677 native checks were lifecycle-confounded and no
  unexplained mismatch remained. This remains an interim snapshot while collection is active.
- **Consequence:** `reserve_observation` contains only evidence-supported Pump curve states.
  Left-truncated first trades and eventless PumpSwap `init_boost` remain explicit unresolved rows.
  Final counts and any exhaustiveness claim wait for all 94,985 bodies and publication gates.

## 2026-07-30 — Reserve paths are materialized only for frozen B8b cohort identities

- **Status:** accepted scope correction after independent offline replay.
- **Decision:** keep every decoded instruction/event in the canonical instruction stream, but build
  `reserve_observation`, reserve continuity failures, and balance reconciliations only for the
  pinned B9a non-Mayhem `mint → bonding_curve` population. An in-scope mint naming a different
  curve fails closed; an out-of-cohort mint is an incidental bundled instruction, not a partial
  cohort history to publish.
- **Evidence:** At 47,181 preserved bodies, the frozen cohort contained 45,691 decoded Pump trades
  with **zero** consecutive four-field reserve discontinuities. All 31 apparent discontinuities
  occurred among 95 trades on mints absent from B9a. Those histories were never enumerated by B9c;
  treating them as exhaustive manufactured the gap by construction. See
  `research/B9D_RESERVE_SCOPE_AUDIT.md`.
- **Correction:** Earlier interim statements treating 21/24 discontinuities as positive evidence
  against B9c cohort-history exhaustiveness were wrong in scope and are superseded. §8a's original
  conservative caveat remains: address-index recall is unproven for this window, but these rows do
  not test it.
- **Consequence:** publication no longer mixes deliberately partial incidental paths into the B8b
  result. This correction does not authorize a post-hoc recall experiment or relax any completeness
  gate.

## 2026-07-30 — Persisted decoder output has an independent publication verifier

- **Status:** accepted offline publication invariant; executable after boundary evidence permits a
  complete decode.
- **Decision:** decoder success and its in-memory counters are not publication evidence.
  `verify_decoded_artifact()` independently checks persisted instruction-to-transaction identity,
  reserve-to-target-Pump parent identity, classification-failure coordinates and counts, frozen
  curve scope, target classification accounting, complete/nonnegative reserve states, and canonical
  per-curve `previous after == current before` continuity.
- **Reason:** raw artifact verification covered no derived table. A plausible but corrupted reserve
  series, orphan row, incidental curve, or missing classification failure could therefore survive
  decoding and be consumed downstream without an independent gate.
- **Consequence:** publication must run both raw `verify_artifact()` and derived
  `verify_decoded_artifact()` read-only. The latter refuses a missing `decoded_at_unix` marker, so an
  empty not-yet-decoded artifact cannot pass vacuously. This does not bypass §4 boundary collection;
  the active artifact still cannot decode until program-version evidence exists.

## 2026-07-30 — Boundary coverage derives ProgramData identity before reading its header

- **Status:** accepted implementation of B9d preregistration §4; live execution remains under the
  existing Seq 218 authorization and the artifact's single-writer lock.
- **Decision:** first fetch each executable program account with finalized `getAccountInfo` and a
  36-byte slice, decode upgradeable-loader variant 2 and its embedded ProgramData pubkey, and require
  equality with the primary-source inventory. Then fetch only that derived account with a 12-byte
  slice containing ProgramData variant and current last-deploy slot. Preserve both byte-exact
  responses; require contexts at or beyond the cutoff, loader ownership, executable/non-executable
  state as appropriate, and variants 2/3. Feed only the decoded deploy slot into the frozen interval
  derivation.
- **Reason:** current ProgramData state is sufficient only when its most recent deploy is at or
  before the observation-range start; then no later deployment can lie inside the range. Fetching a
  multi-megabyte program body adds no evidence about the header and creates avoidable RPC volume.
- **Failure branch:** if either current last-deploy slot is newer than the range start, preserve the
  response but write no false coverage. The separately specified loader-history path is then
  required. Existing raw responses and version rows are immutable and must reproduce exactly on
  resume.
- **Consequence:** `collect-boundary` supplies the missing wiring from preserved primary evidence
  to `program_version`. It is resumable and bounded to four sliced account calls on the expected
  branch. This prevents a valid-but-mistyped ProgramData address from proving coverage for a
  different account—the exact defect caught in the first implementation.
  It cannot run concurrently with the active body collector because both mutate the same evidence
  artifact under the single-writer invariant.
- **Publication verification:** `verify_artifact()` independently reconstructs the two exact request
  identities per program, rechecks compressed bytes and hashes, decodes both loader headers, binds
  Program and ProgramData evidence keys to their correct roles, and reproduces context/deploy
  metadata from the preserved responses. A key that merely exists elsewhere in the table is not
  provenance; cross-program and cross-role references fail closed.

## 2026-07-31 — Agent handoffs use an acknowledged SQLite queue

- **Status:** accepted operational architecture; unrelated research and trading gates unchanged.
- **Decision:** `agent_discussion.md` is an append-only human audit log, not a work queue. The
  dashboard `handoff` command stores an immutable, checksummed message in SQLite as `preparing`,
  durably appends a unique handoff marker to the audit log, then promotes it to `queued`. Startup
  recovery completes a preparation interrupted at either boundary idempotently. Strict
  cross-resource ACID is impossible between SQLite and a Markdown file; this recoverable two-phase
  protocol provides the required no-loss/no-duplicate outcome.
- **Delivery:** the supervisor injects only a compact message ID plus a `receive` command into the
  addressed idle agent. Full task text never travels through terminal paste. A notification is not
  delivery: only the receiver's target-bound, checksum-verifying SQLite acknowledgement advances
  the queue. The oldest unacknowledged message blocks later messages, preserving sequential work.
- **Lifecycle:** one process holds a filesystem singleton lock and writes a database heartbeat.
  Status reports heartbeat health rather than trusting a PID across namespaces. An exited agent is
  relaunched in its tagged pane; notifications are nonblocking and retain errors for inspection.
- **Reason:** screen scraping, composer glyph detection, markdown file order, and `send-keys` exit
  status repeatedly produced unsent drafts, duplicate turns, silent quarantine, and dead or
  duplicated supervisors. None of those signals can establish that an agent received a task.
- **Verification requirement:** queue state/recovery/target/integrity tests plus isolated real-tmux
  Enter delivery and supervisor lock/crash-restart tests are required for behavior changes.

## 2026-07-31 — Reserve coverage is measured against the frozen cohort, not the surviving rows

- **Decision:** before any B9d reserve path may be consumed by a measurement, every frozen
  non-Mayhem cohort curve is classified into exactly one of `broken`, `left_truncated`,
  `anchored_complete`, or `absent`, and publication requires **all** of them to be
  `anchored_complete`. Only `anchored_complete` curves are eligible for full-history reserve
  measurements. Preregistered in `research/B9E_RESERVE_COVERAGE_PREREGISTRATION.md` §5 and enforced
  by `assert_publication_gate` in `scripts/b9e_reserve_coverage.py`.
- **Why the cohort is the denominator:** a broken chain does not produce inconsistent rows, it
  produces **missing** ones, because `advance_curve_chain` refuses to advance past a break. The
  survivors are self-consistent and pass every structural gate. Measuring over "curves that have
  reserve paths" is therefore measuring over the curves whose histories happened to survive
  decoding — a selection rule correlated with trading activity, bundling and left truncation, which
  is to say with the behaviour under study. A curve that produced nothing is invisible in the
  artifact and appears only because the cohort names it.
- **Why the threshold cannot move:** a shortfall is missing evidence to repair, or grounds for a
  separately preregistered estimand over a separately preregistered cohort. It is never grounds to
  lower the number. A threshold set after the distribution is known would be set to whatever the
  distribution turned out to be, and would pass by construction — a description of the result
  wearing the costume of a check. `broken` may never be declared eligible under any future
  preregistration, because its hole is at a known coordinate and any statistic over it is computed
  across a discontinuity.
- **Separation of duties:** the classifier and gate were implemented and tested with both thresholds
  unset and fail-closed; the numbers were then ratified separately, still before any decode pass.
  Neither party had seen the distribution.
- **Verification requirement:** the gate's coupling to `advance_curve_chain`'s wording is pinned by
  tests that generate each reserve-chain reason through the real function, and the preregistered
  numbers are pinned against the document, so lowering the threshold or widening the eligible set
  fails the suite rather than passing quietly.

## 2026-07-31 — The instruction stream is bounded by category, not described after the fact

- **Decision:** before any measurement consumes the B9d instruction stream, every persisted
  `classification_failure` must fall into exactly one declared category — `short_discriminator`,
  `unknown_discriminator`, `eventless_reserve_candidate`, `balance_unresolved`, `balance_mismatch`
  — with reserve-chain discontinuities delegated to B9e. Each category carries a ceiling
  preregistered before decoding. Specified in `research/B9F_FAILURE_COVERAGE_PREREGISTRATION.md`
  and enforced by `assert_failure_coverage` in `scripts/b9f_failure_coverage.py`. Ceilings are
  currently unset and the gate is fail-closed until they are ratified.
- **No `other` bucket, ever.** A reason matching no declared category raises. An `other` bucket is
  where an unrecognised failure class goes to stop being noticed, and a growing bucket of
  not-understood instructions is indistinguishable from a healthy one once it has a name.
- **The denominator is the target instruction population**, never the observed failures. A rate
  whose denominator is the failures themselves cannot fall, so it measures nothing.
- **Every target instruction is either named or explained.** A target row with no `idl_name` and no
  failure at its coordinates was neither understood nor reported, and is invisible to any check
  that walks the failure table, because there is nothing there to walk. This is the invariant the
  gate exists for; the rates are secondary.
- **A partial ceiling mapping is refused** rather than treated as unbounded for the categories it
  omits, and `reserve_chain` may not be given a B9f ceiling at all — charging one curve break
  against two gates makes neither number mean anything.
- **Verification requirement:** each category is pinned by a test that generates its reason through
  the real producer in `b9d_transaction_bodies`, so a rewording fails the suite rather than
  silently creating an unrecognised category or matching an existing one and being counted as
  something it is not.

## 2026-07-31 — Failure classes are stated by the decoder, not inferred from its prose

- **Decision:** `classification_failure` carries a machine-readable `category` column, written at
  every insert site from constants in `scripts/b9d_transaction_bodies.py`. The B9f coverage gate
  reads that column. Prose matching is retained only as a cross-check: a row whose stated category
  disagrees with its own message is refused, because one of the two was edited without the other
  and there is no way to tell which is right.
- **Ratified ceilings (B9f §5):** zero for every category — `short_discriminator`,
  `unknown_discriminator`, `eventless_reserve_candidate`, `balance_unresolved`, `balance_mismatch`.
  Frozen from correctness invariants rather than fitted counts: each category is a statement that
  part of the instruction stream was not understood or not reconciled, and the remedy is repairing
  the evidence, never raising the ceiling. `reserve_chain` is delegated to B9e and may not be given
  a B9f ceiling.
- **Legacy rows are refused, never backfilled.** `migrate_failure_categories` adds the column
  reproducibly and deliberately leaves existing rows NULL, so a migrated legacy artifact is still
  refused and the operator re-decodes. A category inferred from prose after the fact is a guess
  wearing a fact's column name, and backfilling would resolve the refusal by inventing exactly the
  facts the column exists to record.
- **Reconciliation is bidirectional:** every failure resolves to a parent target instruction, every
  unnamed target instruction has a failure, and the persisted row count must equal the decoder's own
  `decoder_classification_failures` tally.
- **Verification requirement:** the decode path itself is tested to populate `category` with a value
  the gate recognises, and the ratified ceilings are pinned against the preregistration document, so
  relaxing either fails the suite rather than passing quietly.

## 2026-07-31 — Decode readiness is established before decoding, not inferred from row counts

- **Decision:** `scripts/b9g_decode_readiness.py` is a single fail-closed offline command that must
  pass immediately before any decode pass. It requires: the single-writer collector lock is unheld;
  an immutable `collection_completed_at_unix` marker is present; no derived rows or decoder metadata
  exist yet; and the full structural verification (exact population, source hashes, boundary
  completeness and version coverage) passes.
- **Why row counts are not enough:** the collector is resumable, so it exits for many reasons and
  most of them are not completion. An artifact caught mid-run has a self-consistent PREFIX of the
  frozen population — every gate comparing rows to other rows passes, and the counts are exactly
  what resuming changes. `mark_collection_complete` therefore writes its marker only after the
  population assertions pass, so the marker means "completed having preserved the frozen set"
  rather than "stopped". It is immutable: a second call returns the first value, so a later partial
  state cannot re-stamp the artifact.
- **Boundary ORDER is explicitly not checked, correcting an earlier proposal of mine.** Boundary
  evidence is collected after the bodies on purpose, to preserve the single-writer invariant. It
  need only complete before decode: finalized current ProgramData evidence whose latest deploy slot
  precedes the observation start proves no in-range upgrade regardless of fetch order. B9g checks
  boundary completeness, never boundary ordering.
- **The readiness probe never takes the lock it is testing.** It probes non-blockingly and refuses
  while the lock is held. A readiness check that can block on the lock will eventually acquire it,
  and a check that can acquire the lock can stop the thing it is inspecting.
- **Verification requirement:** the held-lock test is time-bounded, so a regression to a blocking
  probe fails with a diagnosis instead of wedging the suite.

## 2026-07-31 — The post-collection runbook is executable data, and its order is tested

- **Decision:** the ten-step post-collection order is frozen in `scripts/b9h_runbook.py` as an
  ordered tuple, not as prose in a handoff. The rehearsal executes the real functions in that order
  against a synthetic complete artifact and records what it actually ran; the test compares the
  trace to the tuple, so swapping or dropping a step fails.
- **Frozen order:** collector exits naturally -> seal under the free lock -> raw-body backup ->
  collect-boundary -> raw verify plus B9g readiness -> sealed raw+boundary backup -> atomic decode
  -> verify_decoded_artifact -> B9f measure then zero-ceiling gate -> B9e measure then 100% gate.
- **Why the order is the substance:** each step exists to make a specific later step recoverable.
  The raw-body backup precedes the boundary write so a failed boundary fetch has clean state to
  return to. The sealed backup precedes decode because it is the only state a failed decode may
  restore from. Readiness precedes decode because `refuse_if_complete` makes a decode over partial
  evidence permanent.
- **Recovery policy:** boundary or readiness failure restores the pre-boundary backup; decode or
  gate failure restores only the sealed raw+boundary backup. A gate failure is never resolved by
  moving a threshold.
- **Backups are verified when taken, not when needed.** `backup_artifact` refuses to overwrite an
  earlier recovery point and hashes the copy against the source; `restore_artifact` re-verifies the
  backup still hashes to what it did when taken. A backup nobody hashed is a backup nobody can
  trust, and the moment you need it is the worst time to find out.
- **Verification requirement:** the rehearsal proves an injected mid-decode failure leaves no
  derived rows and leaves the artifact byte-identical to the sealed backup, and that running decode
  or readiness out of order is refused by the functions themselves rather than only by convention.

## 2026-08-01 — The legacy Pump buy takes floor+1, not ceil, and fees are unreproducible on exact-input buys

- **Correction to a ratified document.** `research/B2B_OFFICIAL_BUY_FORMULA.md` concluded that the
  legacy exact-token `buy` reserve input is `ceil(t*vq / (vt-t))`, noting parenthetically that this
  equals `floor(ratio)+1` "when the division has a remainder". The two forms differ ONLY when the
  division is exact, and none of B2b's 9 samples divided exactly — so that sample could not select
  between them. It is now measured over the full frozen population: 31,397 legacy buys, exactly one
  exactly-divisible (slot 433,988,917, remainder zero), and it moved the extra lamport —
  `ceil` 7,000,000,000 against an observed 7,000,000,001. **The program adds the lamport
  unconditionally.** ceil reproduces 31,396/31,397; floor+1 reproduces 31,397/31,397. B2b should be
  amended; this entry records the measurement that forces it.
- **Why this is worth a decision entry rather than a bug fix:** a one-in-31,397 boundary is exactly
  the kind of discrepancy a sample cannot find and a full population can. It is also the kind that
  a trading system would hit eventually and silently mis-size against. The lesson is the sampling
  one, not the arithmetic one: an integer rounding form must be selected on the boundary case, or
  it is not selected at all.
- **No fee component is reproducible on exact-input buys.** Measured over all 20,803: the protocol
  fee misses 103, `creator_fee` 20, `cashback` 3 — every one short by exactly one lamport. The fee
  there is taken from a gross input the `TradeEvent` never states, so the base is not in evidence.
  All three are therefore `unestablished` on those instructions rather than nearly-right, and
  `reproduce_fees` returns nothing rather than certifying arithmetic it cannot do. On legacy `buy`
  and `sell` all three are exact across all 72,450 observations.
- **The buyback fee is unestablished everywhere.** Its declared 5,000 bps matches
  `ceil(fee*bps/10000)` on 46,500 of 93,253 — essentially half — so its base is unknown and it is
  reported, never certified.
- **Gate:** `scripts/b9i_quote_reproduction.py` requires exact integer reproduction of every
  published trade from the B9e-gated reserve path plus the event's own stated basis points. No fee
  constant is hard-coded; IDLs load through the SHA-256-verifying `load_pinned_idl`.
- **Verification requirement:** the exactly-divisible legacy buy is a regression test in its own
  right, because it is the single observation in the corpus that distinguishes the two forms.

## 2026-08-01 — The exact-input fee base is the parent instruction's own pinned gross argument

- **Decision:** the protocol, creator and cashback fees on exact-input buys are reproduced from the
  GROSS input the parent instruction states, not from the quote that reaches reserves. Both
  exact-input instructions declare it as their first pinned `u64` argument —
  `buy_exact_sol_in.spendable_sol_in` and `buy_exact_quote_in_v2.spendable_quote_in` — so the base
  is decoded evidence, never an inferred constant. The program takes the fee-inclusive net,
  `net = floor(gross * 10000 / (10000 + fee_bps + creator_bps + cashback_bps))`, and charges each
  component `ceil(net * its_bps / 10000)`.
- **What this closed:** reproducing those fees from the quote is short by exactly one lamport on
  roughly 0.5% of exact-input buys, which is why all three were `unestablished`. With the gross
  decoded, all three reproduce EXACTLY across the whole published population: 93,253 of 93,253,
  where previously only the 72,450 legacy buy and sell observations were certifiable.
- **Fail-closed on layout, not just value:** the gross is read only when the parent's discriminator
  is in the pinned IDL AND its first argument still matches the pinned name and `u64` type. A
  revision that renames or retypes it would still yield a plausible integer at that offset, and a
  wrong base is a wrong fee that still looks like a reproduction.
- **The decomposition is reported, not required.** `gross == quote + fee + creator + cashback` holds
  on 20,800 of 20,803; three `buy_exact_quote_in` observations leave exactly one lamport whose
  destination is not in evidence. Requiring it would fail an artifact whose quotes and fees all
  reproduce exactly, and tolerating a residue of "1" would be inventing a tolerance to fit the
  observation. It is published with its residue, and `assert_gross_identity_residue` lets a caller
  enforce it under a bound the caller states.
- **Still unestablished, and deliberately not guessed:** the buyback fee, whose declared 5,000 bps
  matches `ceil(fee*bps/10000)` on 46,500 of 93,253 — essentially half — so its base is unknown on
  every path.
- **Verification requirement:** the loop, not only the functions. A mutant that never called the
  gross-based reproduction and fell back to the quote base survived unit tests of the fee function;
  it is now held by an integration test whose fixture is chosen so the two bases give DIFFERENT
  fees, since most grosses cannot tell them apart.

## 2026-08-01 — Initial trading regime and operator-UI boundary are frozen

- **Initial regime:** entries are limited to SOL-paired, non-Mayhem Pump launches whose bonding
  curve is open at the decision instant. These are point-in-time predicates. A token may not be
  excluded because it later graduates, migrates, fails, or becomes illiquid; those are outcomes and
  execution risks. PumpSwap is not an initial entry venue.
- **Exit boundary:** the first simulator models executable Pump exits while the curve remains open.
  If a position reaches curve completion before exit, it becomes unavailable rather than receiving
  an invented mark or assumed seamless migration. A PumpSwap exit path may be added only after its
  reserves, fees, ordering, and wallet costs pass the same gates.
- **Reason:** this is the narrowest regime supported by the published B9d curve paths without using
  Mayhem or USDC observations that have different mechanics. Restricting to the currently 50.29%
  wallet-cost-exact transactions is rejected because that selection depends on transaction shape
  and rent-reclaim behavior; it would bias the evaluation. SPL Token decoding must close that gap.
- **Automation boundary:** models or fixed policies may score opportunities, but deterministic code
  owns eligibility, sizing, risk vetoes, transaction construction, and kill switches. An LLM is not
  in the live signing or discretionary execution loop.
- **Operator UI:** build the product UI on a stable read-only simulator/shadow API, not directly on
  research tables. It must show mode, feed health, opportunities and explanations, executable-cost
  assumptions, positions, intended-versus-observed fills, reconciliation, drawdown, and hard risk
  controls. Signing material stays outside the browser. Full UI implementation waits until the
  simulator result schema is stable; this prevents duplicating research arithmetic in presentation
  code while making the UI a required product milestone rather than an afterthought.

## 2026-08-01 — The two route-wide cost gaps are closed; cost prices our route, not the observed trader's

- **Buyback fee base — established.** `buyback_fee == floor(fee * buyback_fee_basis_points / 10000)`.
  The base is the protocol `fee`; the rounding is **FLOOR**, the only fee in `b9i` that is not
  `ceil`. Exact on **93,253/93,253** through the B9i gate and **93,448/93,448** over every decoded
  `TradeEvent`. `b9i`'s `unestablished` bucket is now empty on the full population.
- **Why it looked unidentifiable for three handoffs:** it was recorded as *"matches
  `ceil(fee*bps/10000)` on 46,500 of 93,253 — essentially half — so whatever base it uses is not
  established."* That near-50% was never evidence of an unknown base. At the observed 5,000 bps,
  `ceil` and `floor` agree exactly when `fee` is even, so ~half is precisely what testing the wrong
  rounding mode produces. The base had been correct all along.
- **`pfee` cannot move lamports on the direct Pump route.** The already-pinned Pump IDL declares
  `fee_config` and `fee_program` with `writable = False` on all six trade instructions, and those
  are exactly the two accounts its CPI receives. The Solana runtime forbids modifying a
  non-writable account's lamports, so this holds whatever `pfee`'s instruction set is — a
  structural guarantee, not a generalisation from traffic. Corroborated by 12,022/12,022 unchanged
  balance observations over 6,011 CPIs. **Its ABI remains unpinned** and unknown discriminators stay
  fail-closed; the ABI is not needed for cost. Scope is the direct route only — on routed
  transactions `pfee` appears with 11/13/19/20 accounts whose writability is not established.
- **No broad router-ABI campaign.** Of the 62 unpinned programs, only `pfee` ever executes inside a
  Pump trade's CPI subtree. The other 61 are outer-level routers and cannot enter a transaction we
  construct.
- **Cost is a function of market state and our own order, never of the observed trader's route.**
  `docs/EXECUTABLE_RETURN.md` §1 previously drew `Q_in` *"from the entry transaction's own balance
  evidence"*; 62,621 of 94,985 observed transactions routed through an aggregator, so that imported
  router costs on a path the frozen regime forbids. Amended: eligibility is a point-in-time
  predicate on the token, cost is a deterministic function of the transaction *we* would construct.
  Dropping routed observations instead would be selecting on realized transaction structure, which
  the 2026-08-01 regime entry already rejected.
- **Conservative defaults are preregistered before any return is computed** in
  `research/B9N_DIRECT_ROUTE_COST_BOUNDARY.md` §4b-ii — ATA rent charged with no refund assumed,
  priority fee never assumed zero, failed submissions charged, and the 92 direct-route residuals
  ignored (all negative, so ignoring them overstates cost, bounded ≤0.0234 SOL per affected trade).
- **The 30 bps creator/cashback split is a per-token property.** Constant within **all 1,110 mints**;
  zero vary between trades. So it is determinable at decision time rather than a per-trade unknown.
- **Ratified by:** measurement over the full frozen population plus the already-pinned Pump IDL,
  under the Codex directive of handoff 58. **Owner review not separately obtained** for adopting §4
  as project policy; the simulator remains unimplemented and gated.
- **Still open, and not closed by any of the above:** landing probability, contention, priority-fee
  and tip levels required to land, and realised slippage — Phase 2, against forward observations.
  Until those are measured, any computed return is **simulated, not executable**.

## 2026-08-01 — The direct-route cost contract is adopted; every residual on our route is explained

- **All 92 direct-route residuals are causally explained and exactly reconciled**
  (`research/B9P_CONSTRUCTED_ROUTE_AUDIT.md`, full population, no sampling):
  `A_outside_constructed_route 92, B_inside_trade_subtree 0, C_insufficient 0`. **Zero lie inside
  the Pump trade subtree**, so no unexplained cost divergence remains on the route we would execute.
- **Why this was needed rather than the previous "bounded and conservative" answer.** `PLAN.md`'s
  Phase 1 gate reads *no unexplained* reserve, cost, ordering or slot-coverage divergence. A bound
  in the safe direction is not an explanation, and adopting the contract on that basis would have
  read the gate as something weaker than it says.
- **The cause is `close_user_volume_accumulator`**, present in 91 of the 92. It sends the user's
  volume-accumulator PDA's entire balance to the user, and nothing in a trade records it. The credit
  is the balance **at close**, not the pre-transaction balance: 32 of the 92 have a pre-balance of
  zero because the accumulator is created and closed in the same transaction, and still refund full
  rent. Reconstructed from pinned semantics only — pre-balance, decoded System credits, and the
  pinned `TradeEvent.cashback` — and order-independently. The 92nd is a creator harvesting PumpSwap
  fees, reconciled against `CollectCoinCreatorFeeEvent.coin_creator_fee`.
- **One double-count was resolved from evidence rather than tolerance.** On 3 transactions the
  cashback reaches the accumulator by an explicit System transfer and so appears both as a decoded
  System credit and as the event field. It arrives by exactly one mechanism per transaction; the
  guard counts it once. No tolerance was introduced anywhere, and a one-lamport miss is still
  reported as a blocker rather than accepted.
- **"Direct route" is redefined by SHAPE, not by program set.** A transaction is an instance of our
  route only if it contains **exactly one** Pump trade at outer level. The previous program-only
  predicate admitted a fee-harvest transaction containing no trade, whose 11.115 SOL residual was
  18x the combined total of the other 91 — it dominated a trade-cost diagnostic while not being a
  trade. Companion instructions default to *not ours*; adopting an unrecognised instruction would
  silently take a stranger's lamport movement as our cost.
- **Adopted:** the direct-route cost contract in `research/B9N_DIRECT_ROUTE_COST_BOUNDARY.md` §4,
  including its preregistered conservative defaults.
- **Ratified by:** measurement over the full frozen population under the Codex directive of handoff
  60, verified by 7 mutants including the two it named — accepting optional companions, and hiding
  an in-subtree divergence. **Owner review not separately obtained.**
- **Explicitly NOT closed by this.** Routed transactions still carry 4,870 unattributed and 1,654
  undecodable observations; they are not our route and are not claimed to be explained. Landing
  probability, contention, priority-fee and tip levels, and realised slippage remain unmeasured and
  need forward observation — until then any computed return is **simulated, not executable**. The
  simulator remains unimplemented.

## 2026-08-01 — Phase 2 first slice: a deterministic direct-Pump simulator kernel

- **Implemented:** `scripts/b10a_simulator_kernel.py` with a versioned read-only result schema
  (`docs/SIMULATOR_RESULT_SCHEMA.md`, v1.0.0). Pure library — no server, UI, model, signal, wallet,
  signing or live RPC.
- **Measured validation gate:** every eligible observed direct Pump trade replays at exact integer
  precision — `net_quote` 31,132/31,132, `quote_out` 40,717/40,717, `tokens_out` 20,661/20,661,
  **92,510/92,510, zero mismatches**. 743 out-of-regime observations (non-SOL quote or Mayhem) are
  counted in `skipped_out_of_regime`, not silently dropped. Rows are read in canonical order
  (`slot, transaction_index, outer_index, inner_index`); database insertion order is never used.
- **The kernel reuses B9i's functions rather than copying them.** `b9i` was refactored to expose
  `tokens_out_for_exact_quote_in`, `quote_in_for_exact_tokens_out` and `quote_out_for_tokens_in`
  as pure functions, with `reproduce_trade` delegating to them. A simulator carrying a private copy
  of a formula drifts from the gate that validates it, and the drift is invisible until it matters.
- **Three refusals are definitional, not configuration.** No execution parameter is ever invented —
  a cost policy missing `priority_fee_lamports` is refused, because absence is not zero and zero is
  the most optimistic assumption available. No post-decision state reaches entry pricing —
  `price_entry` has no parameter for a later state, which is structural rather than a convention.
  No result is ever labelled executable — every record carries `SIMULATED` and `uncalibrated`.
- **The size guard is against the REAL reserve, not the virtual one.** The curve formula approaches
  the virtual reserve asymptotically and never reaches it, so a virtual-reserve check looks like a
  size guard and never fires however large the order. This was written wrong first and caught by
  its own test.
- **The buyback fee is reported, never charged.** It is a split of the protocol fee, not an
  addition; the pinned gross identity carries no buyback term, so charging it would take half the
  protocol fee twice. The field is named `buyback_fee_reported_not_charged`.
- **ATA rent is charged on entry with no refund, by contract.** Failed attempts cost
  `base_fee + priority_fee` each. Exit proceeds may be negative and are reported, never clamped.
- **Verification:** 8 mutants, all killed — including one that survived first. A `ceil` buyback
  mutant passed because the fixture's fee was EVEN, and floor and ceil agree on every even fee at
  5,000 bps. That is the second time the same even-fee trap has been walked into; the fixture now
  asserts its own fee is odd. A pairing defect in the first gate run also produced a spurious
  389,217,712-lamport mismatch, which was the gate's own bug and not the venue's.
- **Ratified by:** measurement over the full frozen population under the Codex directive of handoff
  62. **Owner review not separately obtained.**
- **NOT claimed, explicitly.** The stochastic half of the `PLAN.md` Phase 2 gate — landing,
  contention, failure and fill distributions against forward observations — is untouched. No
  scenario in this kernel is calibrated; "optimistic", "base" and "stressed" are deliberately absent
  as names because they would imply a measured distribution that does not exist. Until forward data
  exists, every computed return is **simulated, not executable**.

## 2026-08-02 — Phase 2 second slice: an observed-state position path evaluator

- **Implemented:** `scripts/b10b_position_path.py` (engine) and `scripts/b10b_path_dataset.py`
  (corpus and validation), with a versioned read-only schema (`docs/POSITION_PATH_SCHEMA.md`
  v1.0.0) and a measured report (`research/B10B_OBSERVED_PATH_VALIDATION.md`). Pure offline
  library — no server, UI, model, signal, wallet, signing or live RPC.
- **The contract is deliberately narrow, and the label enforces it.** Every record carries
  `SIMULATED_OBSERVED_PATH`, not b10a's `SIMULATED`. The later reserve observations came from a
  world in which our hypothetical trade never happened; they are an *observed-state scenario
  diagnostic*, never a counterfactual replay. B10a's entry impact is preserved at t0 and our own
  exit impact is priced against each observed state, but the **persistence of our entry impact and
  other participants' response to it are not modelled, and the sign of that bias is not claimed** —
  their observed order sizes are not invariant to reserves they never saw.
- **Counterfactual replay was refused with a reason, not out of caution.** No trade variant makes
  it valid: exact-input buys pin the quote, legacy buys pin the tokens, sells pin the tokens, and
  each carries a signed slippage bound the shifted price may violate — in which case the observed
  transaction **would have failed and the observation would not exist**. No reserve delta is added
  to any later state, no order is replayed, no small-impact assumption is made, and there is no
  tolerance anywhere in the module.
- **An exit cannot land inside another party's transaction.** 1,121 transactions carry more than
  one reserve observation on the same curve, so 1,209 of 94,389 observations are not
  transaction-terminal and are recorded, never priced. t0 is advanced to the first
  transaction-terminal state, which for **910 of 1,136 curves** is past the launch instruction
  because the launch transaction also carries the creator's own first buy.
- **Completion applies from its transaction, inclusive.** `CompleteEvent` fires after the trade
  that completed the curve, so an exclusive comparison would publish one tradable state per
  completed curve that never existed for us — and it would sit at the top of the curve.
- **`L1m_no_executable_size` is explicitly NOT the economic L1 of `docs/EXECUTABLE_RETURN.md` §3.**
  That threshold stays unfrozen; `L1m` is the mechanical arithmetic floor beneath it and chooses no
  threshold. The drawdown ratio is an exact integer pair, never a float, and is withheld entirely
  when the peak is not strictly positive — an undefined ratio is not a small one.
- **Right-censoring is a first-class outcome.** A rule that does not fire within the observation
  window is `right_censored` (`DEFINITIONS.md` C1) — not a loss, not a win, not a zero. A curve that
  completes first is `structurally_unavailable`. 551 of 884 paths right-censor on a 10,000-slot
  horizon; scoring those would report on the observation window, not the market.
- **Measured validation gate:** 1,136/1,136 curves in strictly increasing canonical order; 884
  paths over 91,296 evaluated marks; **zero arithmetic errors**; a coverage partition summing
  exactly to 94,389 observations; a byte-identical corpus rebuild and two byte-identical validation
  runs. The corpus's 753 out-of-regime observations equal b10a's independently measured 743
  out-of-regime trades plus their 10 `CreateEvent`s — the two modules agree on the regime boundary
  rather than each defining its own, and a test pins the equality.
- **Verification:** 15 mutants, 3 survived first, and each survivor changed the code rather than
  only the tests — the entry feature view was not proven to be what `decide_entry` actually hands
  over, the completion comparison was inline and untested at transaction granularity, and the
  coverage partition check could not be made to report failure. After extracting `is_complete_at`
  and `coverage_partition_error` and pinning the feature view at the call site: **15 of 15 killed.**
- **Ratified by:** measurement over the full frozen population under the Codex directive of handoff
  64. **Owner review not separately obtained.**
- **Explicitly NOT claimed.** No profitability figure, expectancy, win rate or strategy result is
  computed, and no entry is selected: one fixed order size is applied to every eligible curve so the
  corpus exercises the evaluator rather than being searched for a rule. The stochastic half of the
  `PLAN.md` Phase 2 gate — landing, contention, failure and fill distributions against forward
  observations — remains untouched, so every value here is **simulated, not executable**.

## 2026-08-02 — Phase 3 slice: a leakage-safe simulated outcome label materializer

- **Implemented:** `scripts/b10c_outcome_labels.py` (engine) and `scripts/b10c_label_corpus.py`
  (identities and corpus run), with a versioned read-only schema (`docs/OUTCOME_LABEL_SCHEMA.md`
  v1.0.0), a committed preregistration (`research/B10C_PREREGISTRATION_PLUMBING.json`) and a
  measured report (`research/B10C_LABEL_MATERIALIZATION.md`). Pure offline library — no server, UI,
  model, signal, split, baseline, wallet, signing or live RPC.
- **The corpus is the burned B8b cohort, and that governs everything here.** All 1,136 `CreateEvent`s
  fall inside `[433,894,233, 434,097,833]`, burned 2026-07-28, and R3 forbids measuring or tuning a
  label on it. So `window_status` is a required preregistration field whose ONLY accepted value is
  `burned_development` — adding another requires a decision entry naming a fresh disjoint window —
  every row carries it, and **the corpus runner refuses to compute or report a return
  distribution**, stating `returns: NOT COMPUTED` in its own output. Reporting it would be measuring
  a label on a burned window whether or not anybody called the number a finding.
- **R1 is enforced structurally in four independent ways**, because in a label table the question
  and the answer sit in the same row: a declared field partition that refuses any undeclared key;
  `build_decision_facts` having no path/mark/result/horizon parameter, pinned by a signature test; a
  reference-graph walk at the merge seam refusing any row whose decision half can reach a mark; and
  the decision block being asserted identical across every horizon of one decision. Measured:
  1,136/1,136 constant decision blocks, 4,544/4,544 rows partitioned and mark-free.
- **A slot horizon labels the STATE IN FORCE at `t0+H`, not the next trade after it.** R1 fixes the
  label window at `(t0, t0+H]`; taking the first observation after the target would label "the value
  whenever this token next traded", which moves with how quiet the token went. This deliberately
  differs from B10b's `slot_horizon` *exit rule* — B10b right-censored 551 of 884 at 10,000 slots,
  B10c censors none — because the two answer different questions and conflating them would have
  discarded 843 labels.
- **"Nothing traded inside the window" is a distinct status, not censoring.**
  `no_observed_state_in_window` (105 rows) is kept out of `right_censored` because the window covers
  the horizon; what is missing is a state our own entry has not already changed. Folding them
  together would hide our unmodelled impact behind window geometry.
- **Absence is never a number.** Every censored, unavailable, no-observed-state and no-decision row
  carries NULL for every value field — never zero, never minus one — and must state a reason; the
  arithmetic check refuses both a zero slipped in and an absence with no reason. Every curve
  produces rows including the 252 we would not have entered, because conditioning on evaluability
  would select on tradability, which correlates with the outcomes a model would be asked to predict.
- **No default horizon exists anywhere in the module** and a test asserts the absence. Horizons come
  from a preregistration carrying an identifier and a purpose, whose SHA-256 is stamped on every
  row. Value-selected horizons (`net_value_at_or_below/above`, `first_full_size_exit`) are **refused
  by name with their reason**: an exit instant chosen by an outcome property is an oracle exit
  embedding a decision no strategy could have made at t0.
- **Adopted:** return is `EXECUTABLE_RETURN.md` §1 exactly — `(Q_out - Q_in - C)/(Q_in + C)` with C
  every entry and exit cost — as an exact integer pair in lowest terms, never a float, re-derived by
  a second route so a double-counted cost is caught. Drawdown is recomputed **to the horizon**, not
  taken from the path record, because a label at H must not see past H.
- **Adopted:** the observation window end is the `cutoff_slot = 435,536,742` the collection recorded
  about itself, not the maximum observed slot. `materialize` takes it as a required parameter and
  refuses a preregistration that disagrees; censoring against an uncollected window would report
  geometry that never existed.
- **Measured gate:** 4,544 rows = 1,136 curves × 4 horizons exactly, 0 arithmetic errors over all
  4,544, 2,994/2,994 marks found in the corpus they cite, 1,642/1,642 slot-horizon rows citing a
  state at or before their own target, two byte-identical runs. Cross-checks: the observation
  horizon and the administrative horizon reproduce B10b's independently implemented rule engine
  exactly (469/408/7 and 883/1).
- **Verification:** 28 mutants. The first 20 were killed immediately, which was treated as
  suspicious rather than reassuring; a harder set aimed at the seams no test walked directly saw
  **4 of 8 survive**, and each survivor changed the code rather than only the tests — the
  reachability check and the field-partition check were tested but their call sites were not, the
  create-precedes-t0 proof sat beside the row construction as a droppable line, and the window-end
  cross-check lived in `main` where no test reached it. The ordering proof is now inside
  `identity_row` so dropping the check drops the row, and the window end is now a required
  parameter of `materialize`. **28 of 28 killed after.** 922 tests pass repository-wide.
- **Ratified by:** measurement over the full frozen population under the Codex directive of handoff
  66. **Owner review not separately obtained.**
- **Explicitly NOT claimed.** No return distribution, expectancy, win rate, profitability class or
  success label — a test asserts no field name contains a verdict. No entry selected, no split,
  model, baseline or feature vector. Rug/dump remain unconstructed and need their own preregistration
  on a fresh window. The economic L1 threshold stays unfrozen. The stochastic half of the Phase 2
  gate is untouched, so every value remains **simulated, not executable**.

## 2026-08-02 — Window 435,569,150–435,772,750 is the FIRST FRESH EVALUATION COHORT (B11a)

- **Status:** preregistration frozen and committed **alone, before any chain or RPC query**
  (commit `b764898`), then verified and preflighted in a separate commit. Not yet collected.
- **Decision:** the fresh cohort is the launch window `[435,569,150, 435,772,750]` inclusive, with
  observation cutoff `437,211,659` inclusive. Freeze:
  `research/B11A_FRESH_COHORT_PREREGISTRATION.json`, file SHA-256
  `5faabb33ad317240824450a9b8a3a4026137a04e4457b4767e95488a5c469ac0`, canonical SHA-256
  `ae4d2f0351aaba193fe7d87cde8cd68ce83aa8d21515d4d20af0a158f8dafe9f`. Marked `fresh_preregistered`.
- **Why this exists:** every cohort this project has is burned, so R3 could not be satisfied by any
  existing window and no model could have been evaluated honestly on anything. B10c established in
  code that the current corpus IS the burned B8b cohort. This is the first clean window.
- **Derived, never chosen.** Launch start = `max(inclusive_last over the seven burned ranges) + 1` =
  435,569,149 + 1. Launch span and observation span are inherited from B8b/B9d **unchanged and in
  slots** — re-deriving them from a slot rate would make the window's size depend on how fast the
  network happens to be running, which is a property of the regime under evaluation. No candidate
  window was inspected and rejected, and no endpoint was adjusted for yield, regime, activity,
  outcomes, convenience or collection cost.
- **Normalisation is load-bearing.** A half-open `[a, b)` source range contributes `b-1`, and where
  a document's burn STATEMENT is wider than the code range it describes — B7b scanned
  `range(435566652, 435566690)` but declared 435,566,652–435,566,690 burned — the wider statement
  governs. Getting either convention backwards moves the whole window.
- **Preflight result: NOT mature.** One `getSlot` at finalized commitment, no composition query.
  Tip 436,654,559 against a cutoff of 437,211,659: **557,100 slots remaining, about 2.69 days** at
  the measured 2.3934 slots/s (an estimate; the slot count is the exact quantity). **The window was
  not moved, shortened, split or re-placed** — abort branch A3. Receipt in
  `research/B11A_PREFLIGHT.json`, endpoint recorded as scheme and host only.
- **Adopted:** the preflight may call `getSlot` and nothing else. The restriction is an ALLOWLIST,
  not a denylist: a denylist would have to anticipate every method that leaks composition, while an
  allowlist anticipates nothing. `getSignaturesForAddress`, `getBlock` and anything invented later
  are refused by not being `getSlot`.
- **Adopted:** the pipeline is declared with two independent flags per stage —
  `permitted_before_unlock` and `emits_composition`. Gates may run before unlock because data that
  has not been gated cannot be shipped, but only their pass/fail survives; a count is a description
  of the window. **Collection counts are composition too**: enumerating the cohort produces its
  membership list, and "there are N launches" describes the window. Only the program-boundary probe
  is composition-free, because an upgrade slot is a property of the program. B10b and B10c stages
  are refused entirely until results are unlocked.
- **B10c's `window_status` enum is deliberately NOT extended.** It must keep refusing
  `fresh_preregistered` until a separate decision entry records that models, horizons and thresholds
  were frozen first. Extending it now would open a path to revealing this window's labels before
  anything is frozen against them, which is the single failure the preregistration exists to
  prevent. A test pins the refusal.
- **Consequence — the burned-range list stays at seven.** This window is NOT burned; it is
  authorised evaluation data. It becomes burned the moment any census, yield, regime split, actor
  concentration, path result, label or return figure is computed on it before models, horizons and
  thresholds are frozen and recorded here (abort branch A7). There is no eighth window queued behind
  it.
- **Verification:** 23 mutants, 22 killed — including half-open normalised as inclusive, B7b read as
  half-open, the start landing on the last burned slot, both spans off by one, a widened allowlist,
  the maturity boundary off by one, results runnable before unlock, and a credentialed URL surviving
  into the receipt. **One survivor is recorded rather than papered over:** deleting the
  observation-span disjointness check changes nothing observable, because the start rule makes it
  redundant by construction. An attempt to kill it by adding an explicit start-rule invariant
  produced *unreachable* code, and that invariant was **removed** — a check that cannot fire makes a
  file look more careful than it is. 45 tests in the suite.
- **Ratified by:** the Codex directive of handoff 68. **Owner review not separately obtained.**
- **NOT authorised by this decision:** Yellowstone or any paid forward capture, UI, server, model,
  signal, baseline, live transaction, signing or spending. Credentials remain environment-only.
