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

## 2026-08-02 — Baseline evaluation contract frozen before any fresh label exists (B11b)

- **Status:** preregistration committed **alone** (`dc96132`) before the feature materializer was
  written; implementation committed separately. No B11a composition, count, feature distribution,
  path result, label or return has been computed, and that window has still never been queried.
- **Decision:** the first evaluation on the B11a window is a **BASELINE / PIPELINE** evaluation with
  `model_family: none`, zero learned parameters and zero fitted thresholds. Freeze:
  `research/B11B_BASELINE_EVALUATION_PREREGISTRATION.json`, file SHA-256
  `55263060716e99500a097f11260c047d03dbf16c4779a37b3f159d55592cb220`, canonical SHA-256
  `90b159fb4f7492c98571429855c7939d95654c15543e891aaaee279bdf4c506d`.
- **Adopted — the no-string rule.** Every t0 feature value is an integer, a boolean or null, and
  **no string may appear in a feature block**. That is the structural form of "identities group,
  never predict", and its virtue is being checkable without anyone having to notice which strings
  happen to be identities. It is not sufficient alone — a `creator_hash_bucket` integer would pass
  it — so `FEATURE_FIELDS` is pinned as an exact tuple by a test and adding any field fails.
- **Adopted — no transform was selected, because selecting one requires looking.** No log, bucket,
  rank, quantile or standardisation appears. The only arithmetic in the feature set is one
  accounting identity. No feature distribution has been inspected on any window, including the
  burned one; the materializer ran over 1,136 curves and reports only that it worked.
- **Verified fact:** t0 is inside the launch transaction for **1,136 of 1,136** curves, which is
  what makes "the creator bought at launch" a t0 fact rather than a peek. "The creator's first buy
  ever" would be a look into the future and is not offered.
- **Adopted — five non-adaptive policies:** do-nothing; all-eligible fixed 0.1 SOL (**primary**); a
  mint-hash random control with seed `b11b-random-control-2026-08-02` at a frozen rate of 1/2, whose
  role is artefact detection rather than performance comparison; and the two arms of the
  creator-initial-buy partition. No top-k, quantile or rank. Only the control reads an identity, as
  deterministic noise. Invariants enforced: P0 empty, P3 ⊎ P4 = P1, P2 ⊆ P1. **Momentum and
  curve-progress baselines are deliberately absent: both need a threshold, and no threshold may be
  chosen before labels exist.**
- **Adopted — eight hard vetoes** cross-checked against what `b10a.price_entry` actually refuses,
  so the list is the regime rather than documentation. An unstated program-version check is refused,
  because an unstated check is not a passed one.
- **Adopted — B10c state-in-force label semantics exclusively**, named in every metric record and
  refused if anything else. B10b's `slot_horizon` exit rule fires at the FIRST reachable exit at or
  after t0+H; B10c values the LAST observation at or before it. On the burned corpus those differ
  enormously, and a number computed under one and reported under the other would be a different
  quantity wearing the same name.
- **Adopted — whole-cohort denominators and no censored-as-loss shortcut.** Vetoed, declined and
  censored curves are all counted and contribute zero capital; `not_entered_by_policy` is kept
  separate from the pipeline's own `no_decision`. Censored rows carry NULL and never enter the
  headline. An explicitly named `worst_case_lower_bound_return` assigns them a total loss as a
  **bound**; there is no matching upper bound, because an unobserved value is bounded below by zero
  and not above. Grouped uncertainty is a leave-one-group-out jackknife over `creator ∪ user`, which
  makes the `PLAN.md` no-domination criterion computable without a distributional assumption. No
  float appears anywhere; ratios are exact reduced integer pairs compared by cross-multiplication.
- **Adopted — the primary result is designated before it exists:** `P1 × h_1000_slots ×
  capital_weighted_net_return`, on operational meaning and a prior document (1,000 slots is ~7
  minutes, bracketing the ~4.4-minute median graduation time already in `DOCUMENTATION.md`), never
  on a burned return. The horizon number is inherited unchanged; only the designation is new. Family
  size **16** declared now; secondary cells may not be promoted afterwards; no test is computed.
- **Adopted — the unlock evidence B11a must require:** U1 this preregistration committed with both
  hashes recorded here; U2 `model_family: none` or a model artifact hash frozen first; U3 collection
  complete and gates passed; U4 a decision entry naming both window and evaluation hashes; U5 the
  on-disk contract still hashing to what was frozen. **U3 fails today — nothing has been collected,
  so results are locked**, and b10c's `window_status` enum stays locked with them.
- **Adopted — B11a is evaluation data and may never tune a policy.** Once labels are revealed, no
  feature, veto, policy, horizon, metric or primary designation may change in response. That
  requires a new preregistration AND a new window, and B11a would then be burned.
- **Verification:** 31 mutants across the seven named failure classes, all killed. One survived
  first — the feature/identity disjointness check read the module constants, which are disjoint, so
  it could never fire. It became `assert_disjoint_contract(feature_fields, grouping_fields)`, taking
  its inputs as arguments so a test can hand it overlapping sets: a guard nobody can make fire is a
  guard nobody can show works. 69 tests in the suite, 1,036 repository-wide.
- **Ratified by:** the Codex directive of handoff 70. **Owner review not separately obtained.**
- **NOT authorised:** model fitting, UI, server, live RPC, signing, spending, paid subscription, or
  any computation on the B11a window.

## 2026-08-02 — The risk veto is a fail-closed library above the policy, and may never resize (B12a)

- **Status:** implemented offline library (`scripts/b12a_risk_governor.py`,
  `docs/RISK_DECISION_SCHEMA.md`, `research/B12A_RISK_GOVERNOR.md`). No server, UI, model, signal,
  wallet, key, transport, signing, submission or live RPC. **B11b unaltered and B11a still locked**,
  both asserted by tests.
- **Decision — the governor approves the exact proposed order or rejects it. There is no third
  outcome.** A governor that quietly shrinks a proposal to fit a limit changes the thing being
  evaluated: the policy proposed 0.1 SOL, the book received 0.03 SOL, and every return, drawdown
  and capacity figure downstream then describes a strategy nobody wrote. `order_was_resized` is on
  every record, always false, and a record invariant refuses one where it is not. A test also scans
  for `suggested_size`-style fields, because the tempting way back in is to suggest a size rather
  than apply one.
- **Adopted — fail closed in three separately tested senses.** The empty reason list is the only
  thing that approves. Every config, health, portfolio and proposal field is required, **no
  financial limit defaults to zero or to infinity**, and an unknown config key is refused because a
  misspelled limit is an absent limit wearing a plausible name. Any unexpected exception becomes a
  refusal: a bug can stop this system and can never open it.
- **Adopted — one limit rule everywhere: a limit is the largest permitted value, and strictly
  exceeding it rejects.** That holds even for the daily realised loss, where "limit reached"
  colloquially suggests otherwise; consistency beats colloquialism when the alternative is two rules
  nobody can remember. Every limit is tested at cap-1, cap and cap+1.
- **Adopted — both clocks are checked for staleness.** Slots stop advancing during an outage while
  the wall clock keeps running, and a stalled provider can replay an old slot under a fresh
  timestamp; checking one is checking neither. Evidence dated after the current instant is
  conflicting evidence, not fresh evidence.
- **Adopted — an unverifiable drawdown rejects.** A peak of zero is not evidence of no decline, and
  a limit that cannot be checked has not been passed.
- **Adopted — eligibility is delegated to `b11b.evaluate_vetoes`, not reimplemented.** A governor
  admitting a different set of curves than the evaluation contract would make every evaluated result
  unachievable in practice. A test asserts the veto-to-reason mapping is total in both directions
  and that no curve formula appears in the governor.
- **Adopted — all reasons reported, in a frozen precedence.** Controls are EVALUATED grouped by
  concern and REPORTED ordered by severity, and the two orders differ deliberately so that emitting
  reasons in computation order produces visibly wrong output. `order_reasons` takes the precedence
  as a parameter so a test can prove the sort follows that tuple rather than insertion order or an
  alphabetical coincidence.
- **Adopted — no state between calls.** `apply_approved` returns a NEW portfolio snapshot and never
  mutates its input; the caller threads it. Pending orders count toward every exposure limit because
  they will become positions, and a re-submitted `proposal_id` is a duplicate rather than a
  double-count. Two orders that each fit alone and together do not is the concurrency failure a
  limit exists to prevent, and it is tested end to end.
- **Every cap is caller-supplied and `operator_unratified`.** No treasury or risk authorization
  exists, so the ratification enum accepts nothing else; adding a value requires a decision entry
  here. Every record carries `approval_is_simulation_only` and `NO_SIGNING_OR_SUBMISSION`.
- **Two defects the first version had, both found by tests rather than inspection.** (1) The record
  did not publish the realised-PnL and peak/current figures the loss and drawdown controls read, so
  an operator could see that those passed but not against what — and the decision hash was blind to
  both, meaning two materially different books produced a byte-identical record. A `portfolio_risk`
  block now carries them plus the current drawdown as an exact reduced pair. (2) Per-creator
  position counting was under-tested: a mutant counting every position against every creator
  survived, which would have turned the concentration limit into a tighter copy of the global one,
  silently and in the conservative direction.
- **Verification:** 36 mutants, all killed. Four survived the first run; two were my mutants being
  wrong rather than the code being right (a `() or f(...)` mutation that still called `f`, and an
  anchor matching two sites) and were retargeted, and two were real test gaps — the creator count
  above, and a fail-open mutant that survived because the existing test provoked a fault with bad
  input, which validation catches on a different path from the generic handler. A third gap appeared
  when the unknown-key mutant survived: the misspelling test renamed a required field, so the
  missing-field check fired first. 76 tests in the suite, 1,112 repository-wide.
- **Ratified by:** the Codex directive of handoff 72. **Owner review not separately obtained.**
- **NOT authorised:** execution, routing, submission, retry, cancellation, settlement, exit-side
  risk, any model, or any live or devnet transaction.

## 2026-08-02 — The operator console computes nothing, and cannot act (B12b)

- **Status:** implemented offline (`scripts/b12b_operator_snapshot.py`,
  `ui/operator_console.html`, `scripts/b12b_preview_server.py`,
  `docs/OPERATOR_SNAPSHOT_SCHEMA.md`, `research/B12B_OPERATOR_CONSOLE.md`). This is the trading
  system's operator view, **not** the collaboration dashboard. No dependency added. **B11a was not
  read or computed on, B11b was unaltered, results remain locked on U3** — all asserted by tests.
- **Decision — an adapter sits between the pipeline and the page, and the page performs no
  arithmetic on data.** A console that divides two integers to show a percentage has quietly become
  a second implementation of the metric, and the two will disagree on the day it matters. So the
  adapter assembles, validates and hashes; the console formats exact integers and exact
  `[numerator, denominator]` pairs. `1 / 4`, never `25%`. Tests assert the script contains no
  `toFixed`, `Math.round`, `parseFloat`, `* 100` or `/ 100`.
- **Adopted — the snapshot fails closed** on an executable claim (`EXECUTABLE` is not a value this
  schema has), an approval contradicting the system's own halt or staleness state, an `is_stale`
  flag disagreeing with its own clocks, a float at any depth, an undeclared field, anything
  credential-shaped including a URL with embedded credentials, and every internal disagreement.
- **Adopted — unknown is never zero.** Every optional numeric field is present and explicitly
  `null`, never omitted and never substituted. The demo carries a position with an unknown
  realisable value so the state is exercised, and a render test asserts the word *unknown* appears
  where a `0` would be wrong while a real `0` still prints as `0`.
- **Adopted — labels are a deterministic mapping from stable codes, and the code always travels
  with the label.** All 24 risk reason codes are covered, asserted total. An unrecognised code
  renders as `Unrecognised code (X)` and is never dropped: omitting a code shows a shorter list than
  the truth, which is worse than showing one nobody can read yet.
- **The console's safety is readable rather than trusted.** No `fetch`, `XMLHttpRequest`,
  `WebSocket`, `EventSource`, beacon, worker, external resource, form, submit control, wallet
  surface or telemetry, each scanned for. Data reaches the page only through `textContent`.
- **Verified by executing the page, not only by reading it.** `node` is present, so the pure helpers
  and the whole render path run against a minimal DOM stub written inside the test file; the tests
  skip if `node` is absent rather than faking a pass. That caught what scanning cannot — every
  element id the script addresses is asserted to exist, since a mistyped id silently yields `null`
  and leaves a section blank.
- **One test-side correction worth recording:** the console's own prose names every primitive it
  refuses to use, so the first scanners reported the strictest file in the repository as the worst
  one. Scanners now strip comments and read code only; otherwise documenting a safety property is
  indistinguishable from violating it.
- **The preview server is a preview, not an API.** Standard library only, loopback only, `GET`/`HEAD`
  only with every other method `405` before reaching a handler, no path outside `ui/`, restrictive
  CSP. There is no route that writes, mutates, approves, signs or submits. Live-checked.
- **One source of truth for the demo:** `--embed` rewrites the console's embedded JSON from
  `build_demo_snapshot()`, and tests assert the embedded copy, the standalone file and the adapter
  agree, that embedding is idempotent, and that the payload cannot close the script element early.
- **Documentation-only clarification to B12a**, as directed: the drawdown control reads **treasury
  net asset value**, and genesis must supply a positive current and peak NAV rather than inferring
  zero from an empty positions list. Passing zero because the book is empty is a category error that
  makes the governor reject every first trade and look broken. **No behaviour changed.**
- **Verification:** 80 tests, 222 subtests; 1,192 repository-wide. **No mutation run on this area**,
  deliberately: the substance is what the artifacts *cannot* do, and those properties are asserted
  directly — by executing the page, driving the server and scanning for absent capabilities — rather
  than by perturbing a decision function. Recorded as a difference from B10a–B12a rather than
  glossed.
- **Ratified by:** the Codex directive of handoff 74. **Owner review not separately obtained.**
- **NOT claimed:** operational readiness, any live or automatic feed, any real data in the
  interface, or any human review of the visual design. The layout is verified structurally and by
  execution, not by anybody looking at it.

## 2026-08-02 — B12b hardening: display strings are exact and derived, layout fixed by rendering

- **Status:** bounded hardening pass on the B12b area only (handoff 76). No behaviour changed in
  B12a; B11a still unread and locked; B11b unaltered. UI work stops here.
- **Adopted — the adapter publishes deterministic display strings, and the raw value stays
  authoritative.** The console must not divide, but an operator reading `306788560` and
  `[3834857, 12500000]` is doing the arithmetic in their head instead — the same computation,
  performed by the person least able to check it and most likely to be tired. So SOL amounts and
  percentages are derived **in the adapter, by integer arithmetic**, versioned under
  `display_format`, and included in the snapshot hash.
- **SOL is exact; percent is not, and says so.** `lamports // 1_000_000_000` with the remainder as
  nine fixed decimals shows every lamport and rounds nothing; digits are never trimmed because a
  fixed width cannot be mistaken for a rounded one. Percentages truncate the magnitude toward zero
  to two decimals by integer division, carry a leading `≈`, and state the bound
  `|displayed| ≤ |exact| < |displayed| + 0.01` — verified by a test that itself uses only integer
  cross-multiplication. **No float anywhere.**
- **`assert_display_consistent` is total in both directions.** A display string with no raw sibling
  is an unsourced number on an operator's screen; a raw field with no display string is a silent gap
  where the console would show nothing. Both are refused.
- **Identifiers are no longer truncated at all.** An ellipsised mint cannot be copied, pasted into
  an explorer, or compared against anything, and the only reason to shorten one is to make a table
  look tidier than the data is. They wrap instead.
- **Mutation sweep on the adapter: 42 mutants, all killed.** Six survived the first run and **every
  one was a genuine gap, not an equivalent mutant** — only the slot clock was exercised for
  staleness; the emergency stop was never tested against an approval; secrets were only ever planted
  in mappings, never in a list, which is where text actually accumulates; the overview *total* count
  was untested while the approved count was; nothing asserted that `build_snapshot` validates before
  hashing, so the hash could certify a record nothing had checked; and the guard against a payload
  closing the script element had no test that could make it fire. All six now have tests, and
  `embed_demo` was hardened to validate whatever it is handed. **Nothing to disclose as equivalent.**
- **Three layout defects fixed, none of them visible from the source.** Rendered in headless Firefox
  at 1440x3200 and 390x6000: a 44-character mint squeezed into four ragged lines (the identifier
  cell now has a width floor as well as a ceiling); stacked-card labels sitting *beside* multi-line
  values instead of above them; and `word-break: break-all` splitting "0.306788560 SOL" into
  "SO / L". A fourth was a mislabelled header reading "Utilisation (exact)" above a deliberately
  approximate percentage. **This is the argument for rendering rather than only reading**, and it is
  why the DOM-stub tests are kept as a complement to real-browser evidence rather than a substitute.
- **Verification:** 107 tests in the suite, 260 subtests; 1,219 repository-wide; 42 adapter mutants
  killed. The UI itself still has no mutation run, deliberately — its substance is what it cannot
  do, asserted by executing it and scanning for absent capabilities — but the adapter, which has the
  same shape as the earlier decision modules, now does.
- **Ratified by:** the Codex directive of handoff 76. **Owner review not separately obtained.**
- **NOT claimed:** operational readiness, any live feed, or any real data in the interface. The
  layout has now been rendered and inspected at both widths by both agents; the owner has not seen
  it.

## 2026-08-02 — Point-in-time histories publish lower bounds, never totals (B13a)

- **Status:** Phase 3 foundation implemented offline (`scripts/b13a_history.py`,
  `scripts/b13a_history_corpus.py`, `docs/HISTORY_SCHEMA.md`,
  `research/B13A_HISTORY_FOUNDATION.md`). **B11a not queried, enumerated or read**; B11b, B12a and
  B12b unchanged; no model, baseline, threshold or cluster.
- **Decision — the boundary is the canonical coordinate, inclusive at t0 and exclusive one
  coordinate later.** Insertion order is never consulted. The rule is published on every record and
  a record carrying any other text is refused. **A judgement flagged for audit:** a looser reading
  would admit the remainder of t0's own transaction, since that transaction completes before any
  order of ours could land — B10b's own argument. The stricter reading was taken because an event
  wrongly dropped costs information while an event wrongly admitted costs correctness.
- **Adopted — every count is named `_observed` and declared a lower bound.** A bounded window cannot
  know what preceded it, so `prior_launch_count_observed == 0` is a fact about the window and not
  the claim "this creator has never launched before". A test refuses any field name that states a
  total; `counts_are_lower_bounds` is asserted equal to `coverage.left_truncated`;
  `actor_seen_in_window` separates "seen and did nothing" from "not seen"; and
  `require_complete_history` **fails closed** for any policy needing a true count. Using a truncated
  history as though its counts were totals must be an explicit act, never an omission.
- **Adopted — direction is kept exact and separate everywhere**: buys and sells, quote and token,
  inbound and outbound funding. A net figure hides a wallet that cycled a hundred SOL through one
  curve behind one that never traded.
- **Adopted — no string in any feature block**, the same rule as the B11b feature contract; identity
  and feature field sets are declared, disjoint, and the disjointness check takes its field sets as
  arguments so it is reachable rather than a guard nobody can make fire.
- **Adopted — subject consistency is checked.** The subject's declared creator and bonding curve
  must match its launch event's. A caller passing the wrong creator would otherwise receive a
  well-formed history full of zeros, which is the most convincing possible way to be wrong. **The
  check caught the project's own new test fixture disagreeing with itself the moment it was added.**
- **Adopted — clusters are not inferred.** Funding edges are published raw with direction, source,
  destination, amount, coordinate and provenance. Entity resolution, its confidence and its leakage
  are a separate task; **funding-cluster leakage remains an open gate**.
- **Measured on the burned B8b corpus, plumbing only:** 44,438 events — 1,136 launches, 16
  completions, 7,718 trades and **35,568 funding edges decoded from the pinned System ABI** — with
  25/25 subjects respecting the boundary, keeping identities out of features and producing
  order-independent results, and zero errors. **No feature value, distribution, correlation or
  label association was computed, on any window**: a history is one join away from an outcome.
- **Verification:** 31 mutants, 30 killed. Three survived the first run and each was a genuine gap —
  no test distinguished a completion belonging to another creator, the disjointness check could
  never fire, and no fixture placed two events at an identical coordinate so the ordering tiebreak
  was untested. **One equivalent mutant is disclosed rather than removed:** deleting
  `assert_history` from `build_as_of_history` changes nothing observable, because no caller input
  can make that self-check fire; it is kept for the class of future edit it would catch. 62 tests,
  1,281 repository-wide.
- **Consequence — the cohort-based collection plan is specified and NOT executed.** Histories will
  be collected only for B11a's own enumerated actors and tokens, under a lookback preregistered in
  slots before it is measured, with a completeness gate stated in advance, coverage published per
  actor rather than per cohort, and no history inspected before the labels are. **None of its
  parameters may be chosen by looking at an observed history**, and the lookback is deliberately not
  chosen in this pass.
- **Ratified by:** the Codex directive of handoff 78. **Owner review not separately obtained.**
- **NOT claimed:** any model, threshold, cluster, feature distribution or operational readiness.

## 2026-08-02 — Untruncated geometry is not completeness (B13a, handoff 80)

- **Decision:** a point-in-time history may not claim complete evidence on the strength of window
  geometry alone. Every coverage carries a `decode_accounting` that must **partition** exactly three
  ways — transactions, System instructions, and lamport-moving instructions — and every piece of
  evidence that was *lost rather than absent* is listed in `unresolved` with a full canonical
  coordinate, one of four declared reason codes and a non-empty detail. `complete = True` is refused
  while anything is unresolved.
- **Why:** the previous coverage measured how far the window reached and nothing about whether what
  lay inside it was read. A payload the extractor cannot decode produces no event, and an absent
  event is indistinguishable from an event that never happened — the exact confusion the rest of the
  module exists to prevent, arriving one level below where it was being checked. A funding edge lost
  to a decode failure does not announce itself; it surfaces later as a cluster that is not there.
  **Sums rather than counters**, because a counter can be forgotten at one `continue` and a
  partition that must add up cannot be.
- **Per-subject poisoning, not per-window.** An unresolved instruction at or before a subject's t0
  poisons that subject, since the edge it would have produced is precisely the one its history is
  missing. One after t0 does not, since it cannot have removed anything that decision could have
  seen. Poisoning every subject for a failure none could have seen would be fail-closed in form and
  useless in substance. `D03`/`D04` are transaction-level failures and sort at `outer = inner = -1`,
  before the transaction's first instruction, because an unreadable body may have held an edge
  anywhere inside it.
- **Failures are coded, not boolean.** `C01`–`C04` name which kind of incompleteness applies;
  "incomplete" tells an operator nothing about what to fix.
- **A real production bug the pinned fixture found:** `except B9D.FreezeViolation` never matched,
  because `b9j`'s `FreezeViolation` reached directly is a **different class object** from the one
  reached through B13a's chain — each module here loads its own dependency graph by path. An
  undecodable payload would have escaped as an unhandled crash instead of being recorded. A test now
  asserts the two classes are distinct, so the bug cannot return silently the day the loader changes.
- **Why the corpus would never have caught it:** the full b9j survey — **94,985 transactions,
  412,028 System instructions** — contains exactly **two** undecodable payloads, both padded
  `CreateAccount` bodies in signature `5nYDQmEz8Zdj…xY4U` at `(433968746, 858)`, outer 2 / inner 0
  and outer 2 / inner 2. Neither is in the 60-curve slice, so the gate reports `undecodable: 0` and
  always would have. Both coordinates are pinned.
- **Measured, structural counts only:** the burned slice accounts for 36,869 System instructions
  (35,568 moving + 1,301 non-moving + 0 undecodable) across 7,712 transactions (all with bodies),
  0 unresolved, and **completeness refused for 25/25 subjects** — refused on geometry alone, since
  nothing was lost. The history hash chain is byte-identical to the pre-correction run, so the
  accounting added evidence about the extraction without changing the extraction.
- **Verification:** 54 mutants, 52 killed. Of the 23 added on this seam, six survived the first run
  and **five were genuine gaps** — `assert_coverage` required the accounting without validating it,
  `completeness_failures` was never driven with it absent, the code assertions checked set
  membership rather than which code was reported, and the two never-observed moving buckets and two
  transaction-level failures had no test at all. The moving classification was extracted into a pure
  `classify_moving_instruction` so the buckets real data has never produced can be driven directly.
  **Two equivalent mutants are disclosed rather than removed** (`assert_history` and the extractor's
  own `assert_decode_accounting`): no caller input can make either self-check fire, but both fire
  the moment the code around them changes — unlike the b10b check that was deleted for being
  unreachable under any future edit. 89 tests, 240 subtests; **1,308 passing repository-wide**.
- **Ratified by:** the Codex directive of handoff 80, which named this a blocking defect before
  B13b. **Owner review not separately obtained.**
- **NOT claimed:** any cluster, lookback, feature distribution or model. B11a was not queried,
  enumerated or read; no baseline changed.

## 2026-08-02 — Association evidence, never association conclusions (B13b, handoff 82)

- **Decision:** the actor-association layer is an **evidence ledger** with
  `confidence_status = "uncalibrated_evidence_only"`. It publishes pairwise observations with
  coordinates and source hashes, and it emits no cluster, no entity, no merge, no probability, no
  score and no "same owner" claim.
- **Why:** the tempting chain is one short step — shared funder, therefore same actor, therefore
  higher concentration, therefore riskier — and by the fourth arrow every judgement has turned into
  a number that looks like a measurement. A cluster is **indistinguishable from an observation**
  once it is in a record: `prior_launch_count_observed` says where it came from, `cluster_id` does
  not, and three phases later nobody remembers which was inferred.
- **Four refusals are structural, not promised.**
  1. **A link must be witnessed.** Every evidence item names its `witness_addresses` and every item
     must name both endpoints, so A—B evidence witnesses {A,B}, B—C witnesses {B,C}, and no A—C link
     can be written from them. Non-transitivity is a property of the data structure.
  2. **Exact identity is a separate relation type** requiring `address_a == address_b` and admitting
     only equality evidence — the wall between "they transacted" and "they are the same".
  3. **Nothing calibrated may enter, by name or by type.** Any field whose NAME contains `cluster`,
     `probability`, `same_owner`, `score`, `merge`, `posterior`, `component`, `entity_id`,
     `likelihood` or `calibrat` is refused at any depth, and no float may appear anywhere.
  4. **The clustering operations exist in order to refuse.** All five raise `ClusterRefused`, a
     distinct subclass, because an absent operation invites a caller to write their own.
- **Each evidence kind carries what it does not mean**, and that half travels on the record: a
  direct transfer is evidence of a transfer and nothing else; a shared funder is a shared
  counterparty, not common control; co-occurrence is being named, not acting; co-signing is a shared
  action, weaker than shared control. **The kinds overlap and are therefore not independent** — a
  transfer is also a co-occurrence — which is recorded on the item and is one more reason these
  counts may never be summed into a score.
- **`unknown` counts AGAINST a link.** A shared service wallet is the obvious false link, so absence
  of a known service role is not evidence of absence of a service. Registering an address explicitly
  as `unknown` is refused: unknown is what absence already means. Under today's data no role is
  established, so **every measured link carries counter-evidence** — the correct output, not a gap.
- **Direction is never dropped and never netted**, and incompleteness propagates from B13a with
  `require_complete_neighbourhood` failing closed per address against that address's own t0.
- **Measured, structural counts only:** 270 links and 10,988 evidence items over 12 focus addresses
  at 5 instants of the burned corpus; 5/5 on boundary, witnessing, counter-evidence, identity
  containment and order independence; 60/60 neighbourhoods refused; 5/5 refusing operations verified
  to refuse; zero errors. **Focus addresses are chosen by first appearance in canonical order, never
  by degree** — selecting the most connected wallets would pick the population on the very quantity
  the ledger measures. No association degree or distribution was computed. `E05` is disclosed as
  unexercised by this corpus and covered by fixtures instead.
- **Verification:** 53 mutants, 53 killed, **none disclosed as equivalent**. Nine survived the first
  run: six were genuine gaps (one-way repetition collapsed to two-way, the ledger-level confidence
  status, canonical link ordering as distinct from mere determinism, the evidence derivation's own
  tiebreak, and the corpus runner's focus selection and gate conditions). **Three were redundant
  checks and were removed rather than disclosed** — a duplicate no-evidence check, a ledger-level
  transitivity call that could never fire behind the strictly stronger per-item rule, and gate
  conditions inlined where only a full corpus run could reach them. The last became a pure
  `gate_failures` function: a gate whose conditions can only be exercised by running the whole
  corpus is a gate nobody can show works. 98 tests, 62 subtests; **1,406 passing repository-wide**.
- **Consequence — the clustering gate is now concrete.** Before any cluster may be inferred, a
  preregistration must settle the merge rule and threshold before the cohort is enumerated; how a
  cluster is invalidated when a service role appears on one of its links; **funding-cluster
  leakage**, still open, since a cluster fitted on a population chosen with outcomes visible encodes
  which actors mattered even when every edge predates t0; and what a cluster claims when its
  neighbourhood is incomplete — today all 60 measured ones are.
- **Not chosen, deliberately:** the lookback (in slots), the repetition threshold, any probability
  calibration and any merge threshold. Each needs its own preregistration written before the actors
  it applies to are known, and none may be picked by looking at an observed ledger.
- **Ratified by:** the Codex directive of handoff 82. **Owner review not separately obtained.**
- **NOT claimed:** any cluster, model, threshold, degree distribution or label association. B11a was
  not queried, enumerated or read; no baseline changed.

## 2026-08-02 — External observations are judged by two clocks, not one (B13c, handoff 84)

- **Decision:** an off-chain observation is feature-eligible at t0 **if and only if** we received it
  at or before t0's wall instant **and** its claimed publication instant is at or before t0's. Both
  halves are required, the rule text travels on every record, and a record carrying any other text
  is refused.
- **Why:** on-chain leakage is one comparison, because a coordinate either precedes t0 or does not.
  External data has a **second clock**, and that is where the leak hides. An article published last
  Tuesday but fetched today has a genuine publication date, and every field a naive schema records
  checks out; the only thing wrong is that we did not have it, and that fact lives nowhere except a
  clock nobody wrote down. Backfilling is the most natural mistake in this area and produces a
  backtest that is right for a reason that will never repeat. Neither half of the rule implies the
  other: receipt alone admits a provider's future-dated item, publication alone admits the backfill.
- **Unavailable and ambiguous are different facts and both are unusable.** A clock we never got has
  no reading; a local timestamp with no timezone has a reading nobody can bound. Guessing a zone
  would invent the very thing being checked. Claims carry the **width of their own uncertainty**, so
  a date without a time is read at the latest instant it could mean and becomes usable at the end of
  its day rather than the start — arithmetic on a recorded interval, not a remembered policy.
- **The slot-to-wall join is refused, not derived.** A chain coordinate carries no wall time and the
  mapping between them is itself an observation with error, so the caller supplies the decision
  instant's wall time and says where it came from. Deriving one here would hide a source of error
  inside a leakage check.
- **Both receipt clocks are recorded, and the pairing does real work.** A wall clock can legitimately
  jump — NTP, a suspend, a timezone mistake — so it cannot detect reordering; a monotonic clock can,
  and one running backwards inside a fetch session is refused.
- **History is never rewritten. A deletion received after t0 does not reach back.** Corrections,
  edits, deletions and restores are new observations in a linked revision chain; as-of replay returns
  the version a decision actually knew and keeps every prior one. Replaying Tuesday without a post
  withdrawn on Wednesday would make the backtest quietly better than live trading can ever be,
  because live trading does not get to un-see things. **Data hygiene applied retroactively is
  leakage.**
- **`Absent` raises on `bool()`.** Unknown, unavailable, deleted and not-yet-known are four facts and
  none of them is zero; a sentinel that quietly evaluated to False is how "we never received a price"
  becomes "the price was nothing".
- **A ticker is not a token.** Exact mint/account binding — which must name an address *and* show
  where it was found — is separated from name matches and from a provider's bare claim, and
  `require_exact_binding` fails closed, with an explicit waiver for questions that are not about a
  token at all.
- **A value never travels without its unit.** Financial values live with unit, quote asset, basis and
  effective time and are kept out of the feature block entirely, because a number that can be
  separated from its unit eventually will be. Mixed units fail closed rather than converting: a
  conversion needs a rate, and a rate is itself a timestamped observation nobody supplied. The
  freshness bound belongs to the caller and must arrive with a rationale — no default is offered,
  because a module that supplied one would have chosen a threshold for everybody.
- **Licence `unknown` fails closed to hash-only.** Storing raw text under a licence nobody has read
  is a decision nobody made.
- **Nothing is derived.** `sentiment`, `embedding`, `engagement_score`, `source_credibility`,
  `market_cap` and `call_language_model` all exist and all raise; any field whose *name* asserts such
  a quantity is refused at any depth, and no float may appear. **`LLM_IN_DECISION_PATH` is False** —
  a model in the path would make every decision unreproducible, unauditable at the instant it
  mattered, and dependent on a remote service that changes without notice.
- **Measured on synthetic fixtures only:** 16 observations, 13 revision chains, 5 replay instants,
  80 observation-instant judgements (30 eligible, 50 refused across four reason codes); 13/13 chains
  validated, 16/16 hashes stable, 5/5 on backfill refusal, deletion non-rewriting, version
  preservation and order independence; reused-identifier and unit-mixing refusals verified; 6/6
  refusing computations verified; zero errors. **No content appears in the report and a test greps
  it to prove that.** `restore` is disclosed as unexercised by the corpus and covered by unit tests.
- **Verification:** 76 mutants, 76 killed, **none disclosed as equivalent**. Five survived the first
  run and all five were genuine gaps: no fixture built an ambiguous claim that also stated a
  precision, or an unavailable claim still carrying a reading; the feature contract was never driven
  with an extra or missing field; and no test supplied a malformed effective coordinate. 98 tests,
  228 subtests; **1,504 passing repository-wide**.
- **No collection was performed.** No network call, no adapter, no credential, no vendor selected,
  nothing purchased. Future adapter rules are specified in advance: credentials environment-only and
  never persisted, query specs pinned by hash, receipt clocks taken at the adapter boundary before
  parsing, licence and retention decided per provider before the first fetch, author handles kept as
  evidence and never as features, and an adapter that cannot record a receipt time may not be used
  at all.
- **Ratified by:** the Codex directive of handoff 84. **Owner review not separately obtained.**
- **NOT claimed:** any model, score, sentiment, embedding, probability, price transform or
  distribution. The burned corpus was not opened and B11a was not queried, enumerated or read.

## 2026-08-02 — Both denominators, always (B13d, handoff 86)

- **Decision:** every concentration share is published under **both** the total-supply and the
  circulating-user denominator, in exact gcd-reduced rationals, and a record carrying only one is
  refused. The circulating denominator is the **sum of user-role balances**, never supply minus
  exclusions, and each view publishes its own `scope_roles` because the two differ in numerator as
  well as denominator.
- **Why:** concentration is not a hard measurement, it is a ratio, and the denominator does all the
  work. A curve holding 800M of 1B units makes a 120M holder either 12% or 60%; both figures are
  exactly right and they support opposite conclusions. Publishing one is a choice made silently on
  the reader's behalf, and it is the easiest place in this project to produce a number that
  flatters. A sum names what it included; a subtraction hides what it removed, so the record asserts
  that the published circulating denominator equals the user-role total — that mismatch is the shape
  an exclusion takes when it hides.
- **The direction of the error decides the default.** Counting `unknown` as `user` would enlarge the
  denominator and shrink every share: the flattering direction. A rule that errs toward "this token
  looks fine" is not a rule. So unknown is excluded from circulating by construction, negative
  balances are refused rather than clamped (clamping turns a broken decode into a plausible holder),
  zero-balance accounts are kept in the enumeration and out of the holder count, and the supply
  residual is published rather than absorbed.
- **Accounts are never collapsed to owners without exact evidence for every account.** One
  unresolved account blocks it entirely: it could belong to the largest holder, so a top-1 computed
  without it is a lower bound wearing the costume of a measurement — and a lower bound published as
  a share is what later gets compared against a threshold. The creator share follows the same rule
  and adds one: its numerator is scoped exactly like its denominator, or a creator holding through
  an excluded role would produce a share above one.
- **Exact arithmetic.** Gcd-reduced rationals, cross-multiplied comparisons, no float anywhere: a
  raw supply of 10^15 units does not survive a double. The Herfindahl is one ratio `Σbᵢ²/D²`, not a
  sum of squared ratios — summing rounded squares is where a float implementation loses the small
  holders entirely. The tests check the arithmetic against `fractions.Fraction`, an oracle
  independent of the implementation, rather than against constants copied after a run.
- **Undefined is not zero.** A token whose whole supply sits in the curve has no circulating-user
  share; the block is `defined: false` and carries no `top_1` rather than a `0/1`. `select_snapshot`
  returns `Absent(not_yet_known)` when nothing exists at or before t0, with the detail saying that
  not knowing the concentration is not the same as it being low. This pass added a fifth reason,
  `undefined`, to B13c's absence vocabulary for values that cannot exist rather than merely being
  missing.
- **Point-in-time is strict.** A later holder state cannot be backfilled: the balances that existed
  after a decision are not the balances it was made against.
- **Cluster adjustment is structurally unavailable.** It is the most dangerous number this project
  could publish — it looks like a measurement, it moves in the direction that justifies action, and
  every input to it is a judgement. Both operations always raise,
  `ACCEPTED_CLUSTER_ARTIFACT_TYPES` is empty (not "none supplied" but "no type is acceptable yet"),
  and **the record carries no cluster field at all**, since a field named for a quantity we refuse
  to compute teaches the next reader that we compute it. A **B13b association ledger passed as a
  cluster map gets its own refusal naming what it is** — it declares itself uncalibrated, its links
  explicitly do not assert common control, and passing it here would launder "we do not know" into
  a merge. It is recognised by self-declaration OR by shape, each path tested alone.
- **Measured on synthetic fixtures only:** 9 snapshots, 33 accounts; 9/9 on reconciliation,
  both-denominator publication, exact rationals, top-k monotonicity, role accounting, hash stability
  and order independence; 3/3 later snapshots refused; owner-collapse refusal, zero-balance
  preservation, undefined denominator and published residual each exercised; all three cluster
  refusals verified; zero errors. **No concentration value appears in the report** and a test walks
  it for any numerator/denominator pair to prove that.
- **Verification:** 75 mutants, 75 killed, **none disclosed as equivalent**. Five survived the first
  run and all were genuine gaps: the per-role account-count sum, the two ledger-recognition paths
  only ever exercised together, the denominator rule on the computed record, and the ranking
  tiebreak. The tiebreak is unobservable through the published sums today, so rather than disclose
  it as equivalent the test drives `_sorted_balances` directly — **a sort key nobody can observe
  today is a sort key that silently stops working tomorrow**, and the first field to publish a
  ranking would inherit a non-deterministic record. 87 tests, 81 subtests; **1,591 passing
  repository-wide**.
- **Not chosen, deliberately:** any concentration threshold, veto, profitability class or rug label.
  A concentration figure is a measurement; everything downstream of it is a decision.
- **No RPC was queried.** Future token-account capture requirements are specified in advance:
  enumeration completeness asserted or denied with a residual; the snapshot atomic at one slot,
  since balances read across a range are not a snapshot of anything and a transfer between two reads
  can appear twice or vanish; owner resolution from the account data rather than inferred from
  transfer history; roles from a pinned roster cited per account; the declared supply from the mint
  account at the same slot, or the residual measures a disagreement between two sources; capture
  cohort-scoped like B13a's plan; credentials environment-only with the endpoint hashed into
  provenance.
- **Ratified by:** the Codex directive of handoff 86. **Owner review not separately obtained.**
- **NOT claimed:** any model, threshold, cluster, component, label or real concentration value. The
  burned corpus was not opened and B11a was not queried, enumerated or read.

## 2026-08-02 — The history lookback is reused geometry, frozen before any actor is known (B13e, handoff 88)

- **Decision:** the actor/token history lookback is **1,642,509 slots**, computed as
  `B9D_CUTOFF_SLOT − B8B_WINDOW_START_SLOT` — the same quantity B11a already inherited as
  `observation_span_slots`. Applied per decision as `[max(0, t0_slot − 1,642,509), t0 coordinate]`.
- **Why reuse rather than choose:** a lookback picked after seeing how far back actor histories
  happen to run is a lookback picked for its results, and the only histories available to look at
  are the burned ones whose outcomes have already been measured. Reusing geometry the project is
  already committed to removes the choice entirely — there is no version of this number that could
  have been made larger or smaller by anything observed. A round number in hours would have been
  worse twice over: it would have been chosen, and it would need a slot-to-wall-clock conversion
  that is itself an estimate with error.
- **Never translated to wall-clock time.** Slot production varies, so a wall-clock lookback is a
  different number of slots on every day it is applied, and a parameter whose length depends on
  network conditions is not frozen. `hours_of_lookback()` exists and raises.
- **The bounds are asymmetric on purpose.** The upper bound is a **leakage** boundary: exact to the
  instruction, inclusive at t0. The lower bound is a **coverage** boundary at slot granularity,
  because half a slot of lookback is not a meaningful quantity and a coordinate-exact lower bound
  would make the window's length depend on where inside a slot the decision fell — two decisions one
  instruction apart would get measurably different histories for no defensible reason.
- **Genesis clamps, and the clamp is truncation.** `max(0, …)` never computes a negative slot, and a
  clamped window sets `left_truncated`; reporting it complete would claim knowledge of a period
  before the chain existed.
- **A short source reports incomplete and never shifts the start.** Moving the start up to whatever
  a provider happened to have would redefine the parameter per actor, so "no prior launches" would
  mean a different lookback for each — and the actors with the least history would get the shortest
  window, which is exactly backwards.
- **Burned events may be CONTEXT; burned members may never be EVIDENCE.** The lookback reaches deep
  into burned ranges for most fresh decisions, and those events genuinely happened first, so
  excluding them would report a zero that is a collection artefact presented as a fact about the
  creator. But a burned member may never be an evaluated subject, a label, tuning data or
  performance evidence. **A burned curve may appear in a FEATURE and may never appear in a METRIC.**
  Both directions are checked: promoting burned data to evidence is refused, and so is dropping
  burned context from a window that admits it.
- **A mechanical property nobody arranged:** because B11a starts one slot after the maximum burned
  endpoint and the lookback equals the observation span, the burned overlap decays to exactly zero
  at the observation cutoff — a decision at 437,211,659 looks back precisely to 435,569,150, the
  fresh window's first slot. A test pins it so changing either constant breaks visibly. Corollary:
  the slot immediately before the fresh window is itself burned.
- **Coverage is per actor and averaging is refused outright.** The overall verdict is an AND, never
  a mean: an average is exactly the statistic that hides the single actor whose history is missing,
  and there is no percentage to pick because picking one would require averaging.
  `coverage_fraction()` raises.
- **Two commits, in order.** The preregistration was committed **alone and first**; the validator
  came second. A parameter committed alongside the machinery that consumes it can always be claimed
  to have been adjusted until the machinery worked, and the git ancestry is the only evidence
  otherwise — so a test asserts the document's commit is an ancestor of the module's.
- **What is pinned versus what is cross-checked.** The document's hash pins every parameter. Beyond
  that, code re-checks exactly one class of value: **anything it holds its own independent copy of**
  — the lookback, its two operands, and the burned-role table — because those can disagree with the
  document without the document changing. Values only the document states are deliberately **not**
  re-read: a second check on a value the hash already fixes could never fire, and a check that
  cannot fire is worse than no check. Three such re-reads were removed during the mutation sweep for
  exactly that reason.
- **Also enforced:** cohort is B11a's enumeration exactly (wider selects on what the broader
  population contained, narrower on collectability, which correlates with activity); no query before
  maturity and U3, since before that the cohort is unknown and a run would have chosen its own
  population; `QueryGuard` is permission rather than a client and holds no endpoint; pagination
  exhaustion must be **proved** and a page cap is not exhaustion; decode accounting is asserted
  rather than trusted; snapshots must be atomic at one slot; methods are allowlisted rather than
  denylisted, because the next client version adds one nobody thought to forbid; credentials are
  refused rather than redacted, since a redaction that fails silently looks like one that worked.
- **Verification:** 67 mutants, 67 killed, **none disclosed**. 102 tests, 103 subtests; **1,693
  passing repository-wide**. The eleven first-run survivors included four checks that could not
  fire — three document re-reads and a redundant sort — which were **removed** rather than
  disclosed, and one inert mutant that was rewritten to be observable.
- **Ratified by:** the Codex directive of handoff 88. **Owner review not separately obtained.**
- **NOT claimed and NOT done:** no RPC call, no B11a unlock, enumeration or inspection, no history
  collected, no cluster, probability, threshold or label, and no change to B11b's frozen no-model
  baseline evaluation.

## 2026-08-02 — A 99-field feature contract frozen before the machinery, and eligible for nothing (B13f, handoff 90)

- **Decision:** an exact **ordered tuple of 99 raw point-in-time facts** — B11b's 17 t0 fields with
  names unchanged, 26 B13a history counts and directional flows renamed `_in_lookback`, and 56 B13d
  concentration fields under both denominators. Committed **alone and first**; the materializer came
  second, and a test asserts the contract's commit is an ancestor of the module's.
- **Why the split, again:** a feature list committed alongside the machinery that computes it can
  always be claimed to have been trimmed until the numbers came out well. The git ancestry is the
  only evidence otherwise.
- **Eligible for nothing, and explicitly not B11a.** `eligible_windows` is empty. B11a's evaluation
  was frozen as a *no-model* baseline over 17 declared fields and its unlock evidence was written
  against that; a 99-field vector there would evaluate something nobody preregistered on a window
  whose maturity conditions were set for something else. **The B11a refusal is unconditional** — it
  does not consult the document's own flag, so a contract re-pinned with `eligible_for_b11a: true`
  still cannot produce one. Any future use requires a new design that names a fresh window, states
  its split and **fits every transform on training folds only**; nothing here is a fitted transform
  and there is deliberately nowhere to put one.
- **Nothing is recomputed.** Every value is read from an already-validated B11b, B13a or B13d record
  through that module's own validator, so an upstream change fails rather than silently diverging.
- **Order is part of the contract.** `feature_order_sha256` hashes the order, not the set: two
  vectors with the same fields in different positions are the same set and a different matrix, and
  a model trained on one and scored on the other is wrong in every row while set-equality passes.
- **Rationals travel as two named integers.** Never one `share` field — a single number is what a
  later adapter float-rounds. After gcd reduction the pair no longer carries the magnitude, so
  `*_units` travels alongside; the ratio and the scale are different facts.
- **Exclusions, each with a reason rather than an omission:** B13b association evidence (declares
  itself uncalibrated; admitting it turns "we do not know" into a weighted number), clusters, B13c
  text/URLs/handles, sentiment/engagement/market-cap transforms, ranks/quantiles/logs/normalisation
  (each fitted on a distribution, and a distribution computed outside a fold has already seen the
  evaluation data), **every absolute slot number** (a calendar index a model learns "later is
  better" from, which does not survive a different window), constants under a complete window, and
  fields duplicating B11b's.
- **Unavailable is not zero.** Seven coded reasons, and an unavailable vector carries **no feature
  block at all** — `null`, not an empty dict, because an empty one invites a caller to fill it in. A
  zero claims the thing did not happen; a median claims the subject was typical and is fitted
  outside a fold; a missingness flag chosen because it improved a score is the outcome leaking in
  through the door marked "handling missing data".
- **Two genuinely optional field groups** (owner grouping, creator share) carry frozen availability
  rules represented separately from their numeric fields, and are `null` rather than zero when
  unavailable — a creator share of zero says the creator holds nothing, null says we cannot say, and
  a model that cannot tell them apart will learn from the difference anyway. Both directions are
  checked.
- **Provenance is order-dependent on purpose.** Feature values are independent of input order;
  evidence hashes are not, because they record the hash of the input actually consumed. Two
  snapshots differing only in account order give identical features and different
  `concentration_sha256`, and provenance that ignored that would be provenance of something else.
- **Verification:** 62 mutants, **61 killed, one disclosed equivalent**. 79 tests, 413 subtests;
  **1,772 passing repository-wide**. Of eleven first-run survivors, two were unfireable code that
  was **removed** (a redundant residual clause B13d already guarantees, and a deep-copy that guarded
  nothing observable — the no-mutation test is the reachable guard), eight were genuine gaps, and
  one is the disclosed equivalent below.
- **A known constant, disclosed rather than hidden:** `concentration_supply_residual_units` is
  always 0 in any available vector, because an incomplete enumeration makes the vector unavailable
  and B13d already refuses a complete enumeration with a residual. It is kept as a **tripwire**: if
  a future edition relaxes the completeness rule the field is already in the frozen tuple and starts
  carrying signal without forking the contract. A mutant hardcoding it to zero is therefore
  equivalent.
- **Ratified by:** the Codex directive of handoff 90. **Owner review not separately obtained.**
- **NOT claimed and NOT done:** no model fitted, no transform selected, no window named, no corpus
  read, no feature value or distribution reported, and no change to B11b's frozen baseline.

## 2026-08-02 — The purge is computed on the label window, and identities are pooled (B14a, handoff 92)

- **Decision:** walk-forward folds are strictly chronological with caller-supplied preregistered
  ranges; a training row survives only if `label_window_end_slot + purge_slots < first evaluation
  slot`; a later training segment admits a row only if `t0_slot >= previous_evaluation_last_slot +
  embargo_slots`; and rows are grouped by the transitive closure of exact identity equality over the
  **pooled** set of creator and user addresses.
- **Why the purge is on the label window and never on t0:** a decision at slot 1,950 sits safely
  inside a training range ending at 2,000 while its outcome is observed to 2,550, inside a
  validation segment starting at 2,500. The row is labelled by the very period it is evaluated
  against, and **nothing about its t0 says so**. This is what "sort by t0 and cut" produces every
  time, and it leaves no trace. The fixture corpus holds two rows with the *same* t0 and different
  label windows so a test can demonstrate that t0 alone cannot separate them.
- **The purge measures against the earliest evaluation instant.** Chronology is enforced, so
  validation always precedes test and a window reaching test has already reached validation; the
  per-segment loop carried a branch that could never fire and was **removed** rather than disclosed.
- **Why creator and user share one identity space:** an address that creates one token and trades
  another is one address. Separate role-spaces would let the same person appear under two labels and
  sit on both sides of a boundary while every check passed. The closure is transitive — A—B through
  a shared creator and B—C through a shared user put all three in one group — and the fixture holds
  exactly that bridge with nothing linking A to C directly, so a non-transitive implementation fails
  visibly.
- **A group spanning two segments is dropped whole.** Splitting it would put an actor's own future
  in their training set; keeping the larger half would select on which side happened to have more
  rows. The group key derives from the sorted membership, not from whichever union-find root was
  picked, so two identical groupings cannot look different.
- **A censored outcome may not carry a label value at all** — refused at the door, so the recoding
  cannot happen before the planner sees the row. Recoding "we stopped looking" as "it went to
  nothing" does not add noise; it adds a systematic mass of false negatives concentrated on exactly
  the rows whose observation was cut short.
- **No defaults, and the refusal says why.** A split boundary chosen after seeing which side scored
  better is the oldest mistake in this field, and a module supplying one would have made that choice
  for everybody who ever used it.
- **A plan must say which rows it planned.** The sweep found that changing a row's t0 did not change
  the plan hash, because the plan stored only identifiers — the corpus underneath could have been
  swapped entirely while the hash stayed identical, and an artifact bound to it would inherit the
  blindness. `row_evidence_sha256` now hashes the rows themselves.
- **The artifact envelope is not a model.** It binds the feature contract and **order** hashes,
  label and split hashes, target/horizon, algorithm identifier, explicitly declared hyperparameters,
  seed, train-only transforms and calibration, training row/evidence hashes and the
  code/environment manifest — every one of which is invisible in the weights. Three refusals: no
  default anything (a hyperparameter must be declared by name before it may carry a value, so a
  later one is *undeclared* rather than a new default, and a declared name with no value is a
  default hiding in the algorithm); no transform or calibration fitted outside training folds (a
  probability calibrated on the evaluation fold is calibrated against the answer); and no
  performance claim — the status is locked, `seal_artifact` takes no argument for it, and every
  claim status is refused **by name**, since a status nobody listed is a status somebody invents.
- **No float anywhere, hyperparameters included.** The same value serialised on two machines can
  differ in its last bits, so two artifacts that are the same model hash differently — or two
  different models hash the same. Rationals travel as named integer pairs.
- **Funding-cluster leakage is an explicit OPEN GATE.** Only `research_plumbing_only` is attainable;
  `ACCEPTED_CLUSTER_ARTIFACT_TYPES` is empty. The honest statement of the limit: **two actors can be
  one person without sharing an address**, so a split this planner calls clean may still put one
  operator on both sides. A B13b ledger offered to close the gate gets its own refusal naming that
  it declares itself uncalibrated and that its links explicitly do not assert common control.
- **A bug in the fixtures that the tests found:** the fixture module loaded the planner and the
  artifact envelope as two separate module graphs, so each had its own `SplitRefused` and the gate's
  `except` around an artifact call would have caught nothing — reporting clean while missing every
  artifact refusal. That is the fourth appearance of this module-identity trap in the project, and
  it was caught only because a test asserted on the exception class.
- **Measured on synthetic rows only:** 22 rows, 19 identity groups, largest group 3 (the bridge),
  9/4/4 assigned, 5 excluded across censored, purged and spanning reasons; order-independent; all
  gated statuses refused; zero errors. **No metric appears in the report**, and the test that
  enforces that scans field *names* rather than raw JSON — the report carries hex digests, and a
  substring search over those matches `f1` and `auc` by coincidence.
- **Verification:** 96 mutants, 96 killed, **none disclosed**. Of nine first-run survivors, two were
  unfireable code **removed** (the per-segment purge branch, and a duplicate-assignment check
  sitting behind a range check that always fired first — now reordered so it can fire and gives the
  better message), six were genuine test gaps, and one was an inert mutant rewritten to be
  observable. 129 tests, 152 subtests; **1,901 passing repository-wide**.
- **Ratified by:** the Codex directive of handoff 92. **Owner review not separately obtained.**
- **NOT claimed and NOT done:** no model fitted, no weights, no algorithm implementation, no metric,
  no threshold, no cluster, no eligible window, and B11a was never accessed.

## 2026-08-02 — Every headline is published twice, or not at all (B14b, handoff 94)

- **Decision:** every headline evaluation figure is published on **two bases at once** —
  `observed_evaluable` over the rows that produced an outcome, and `whole_cohort_worst_case` with
  every unevaluable at-risk row assigned a total loss of its deployed capital. A report carrying one
  basis is refused; a headline metric present on one basis and absent from the other is refused; and
  neither may be labelled as the other.
- **Why:** a headline computed on the rows that happened to be evaluable is survivorship, and it
  always flatters. The rows that fail are **not a random sample** — a curve with no observed state
  is one nothing traded against, a structurally unavailable exit is one the book could not absorb.
  Those are the outcomes that went wrong in ways the pipeline could not price. Neither basis is the
  answer: the truth lies between them, and **the distance between them is the size of what nobody
  knows**, which makes it the most informative number in the report. A test asserts the two
  genuinely differ on the fixture corpus, because if they ever collapsed together, mislabelling one
  as the other would be invisible.
- **Censoring is refused three ways**, because it can arrive three ways: at the door (a non-marked
  side carrying a realised figure or a class label — an outcome nobody observed has no class); in
  the specification (`recode_as_zero`, `recode_as_loss`, `impute_median`, `drop_silently` and
  `carry_forward` refused **by name**, an invented one refused for not being declared); and in the
  arithmetic (censored capital must move between the two bases by exactly the censored amount).
  A decision the policy **declined** is a fourth thing: it deployed nothing, so it cannot lose
  anything even under the worst case.
- **Selection on evaluability is the pairing's own leak.** The paired cohort is *exactly* the rows
  where both sides produced an outcome, a caller-supplied one is refused, and the asymmetry is
  published rather than resolved. Order size, horizon and cost policy live on the **row**, making a
  per-side difference unrepresentable rather than merely checked.
- **Exactness where it is load-bearing:** Brier sums as one rational over a common denominator, not
  a mean of rounded terms; concordance counts only pairs whose **outcomes differ**, since two
  identical outcomes cannot rank each other and counting them would let a model that separates
  nothing score one half by default; maximum drawdown comes from the published path, and the fixture
  holds a path that fell to −700,000 and recovered to +10,000, where endpoint arithmetic reports no
  drawdown at all.
- **Jackknife leaves out whole identity groups**, not rows: rows sharing a creator or a trader are
  not independent, and leaving one row out leaves the rest of that actor's behaviour in — narrowing
  the spread in the flattering direction. It is a **spread and never a p-value**, and a test greps
  the output to keep it so.
- **Multiplicity binds the frozen family (16) and B11b's frozen primary cell.** A family that shrank
  between preregistration and evaluation shrinks the correction with it, the cheapest way to make a
  secondary cell look primary; promoting a secondary after the numbers are in is choosing the
  hypothesis to match the result.
- **Nothing has a default** — metric, class threshold, calibration bin edge, censoring treatment,
  worst-case rule. There is no performance-cutoff field at all, because nobody has earned a "good
  enough" line. Calibration edges must name the folds they were chosen on: edges chosen by looking
  at the evaluation fold are edges fitted to the answer.
- **Status locked** to `synthetic_plumbing_only` / `not_evaluated`; `publication_grade` is refused
  and the refusal names the **still-open funding-cluster gate**.
- **Measured on synthetic rows only:** 11 rows, 11 groups, 7 paired, one evaluability asymmetry each
  way, 2/2 bases, 3/3 headline metrics on both, 7/7 refusals verified, zero errors. **No metric
  value or return distribution appears**, and the enforcing test scans field *names* rather than raw
  JSON, since hex digests match metric words by coincidence.
- **Verification:** 65 mutants, 65 killed, **none disclosed**. Of five first-run survivors, one was
  dead code **removed** (a zero-return branch for non-at-risk sides that `assert_side` already
  guarantees), two were fixture weaknesses (both sides deployed identical capital, so a return
  divided by the wrong denominator was the same number; and no test drove an *undeclared* censoring
  treatment as distinct from a refused-by-name one), and two were properties the report does not
  expose, now driven directly — canonical row ordering and the fixtures using one module graph — on
  the same reasoning as B13d's tiebreak. 84 tests, 108 subtests; **1,985 passing repository-wide**.
- **A property of the project written down at last:** refusals form a chain across modules, so a
  module re-exporting an earlier validator raises the *ancestor* class. A caller catching only the
  newest class silently misses the checks it inherited; **catch the project base**. Tested in both
  directions.
- **Ratified by:** the Codex directive of handoff 94. **Owner review not separately obtained.**
- **NOT claimed and NOT done:** no model fitted, no real metric, no return distribution, no
  threshold, no eligible window, and no B11a outcome read — this module opens no file and connects
  to no database, asserted against its own source.

## 2026-08-02 — The watcher waits on a finalized slot and quarantines rather than mis-collecting (B11c, handoff 96)

- **Decision:** a durable unattended supervisor polls `getSlot` at **finalized** through B11a's
  one-method allowlist every 300 s, and at the frozen cutoff runs the frozen collection stages once
  each with the **A2 program-boundary probe first**. It is **running** as of this entry.
- **Finalized, and exactly the cutoff.** A processed or confirmed slot can be rolled back, and a
  window opened on a slot that later disappears was opened on nothing. One slot early is early.
- **The A2 probe first** because an upgrade boundary is a property of the program rather than of the
  window, so it costs no composition — and if version coverage cannot be proven there is nothing
  worth collecting.
- **BLOCKING FINDING, surfaced by the dry-run planner rather than at maturity:** the existing
  collection scripts are wired to the burned corpus. `b9d run` reads its population from the
  module-level `B9C_PATH`/`B9A_PATH` constants and accepts **no override**; `b9c` expects a
  B9a-shaped cohort while this window's population comes from B7d. Running either unchanged would
  collect this window into the burned corpus's paths or read the burned corpus as this window's
  population, and both destroy an artifact that cannot be recollected. The watcher therefore reports
  `launch_ready_for_collection: false`, runs what it can prove — the A2 probe and the create
  enumeration — and **quarantines** with `Q11_stage_wiring_unresolved`. Resolving it needs a
  separate reviewed change to the collection scripts before the cutoff.
- **Stopping beats guessing.** Every quarantine condition is one where continuing would risk a
  one-shot resource: a stage interrupted mid-flight quarantines rather than resuming, because a
  partial artifact is not a checkpoint and this process cannot tell an interrupted run from a
  corrupted one. Completed stages must be a true **prefix** of the run order — `["simulator_replay_
  gate"]` alone is in run order and is not a prefix, which means every earlier stage was skipped.
- **A match on a secret is fatal, not redacted.** The endpoint is recorded as `scheme://host`
  because the configured URL carries its key in the query string. Every durable write is scanned
  against the live environment secrets, and a hit refuses the write — a redaction that fails
  silently looks exactly like one that worked.
- **A composition leak is a NUMBER keyed by a window word**, not the word appearing anywhere. The
  stage `enumerate_creates` is a name; a scan that fired on the pipeline's own vocabulary would be
  switched off within a week.
- **One enforcement for the results lock**, B11a's own `assert_stage_permitted` with
  `results_unlocked=False`, which already encodes both maturity and the lock. Two local copies of
  the same rule were removed during the sweep for being unfireable behind it; `FORBIDDEN_STAGES`
  stays as a published declaration and is asserted to equal the pipeline's own results stages — a
  declaration that drifted from what it describes reads like a guarantee and guarantees nothing.
- **A bug the tests caught before launch:** `run_stage` called `write_state` without a path, so it
  wrote to the **real** `research/b11a/supervisor_state.json` during tests. A stray quarantined
  state file was left behind, which a real run would have refused to start against. Every path is
  now a parameter, and a test asserts it.
- **Verification:** 42 mutants, 42 killed, **none disclosed**. Thirteen first-run survivors were
  almost all guards protecting constants that nothing could drive; `verify_preregistration`,
  `verify_git_ancestry` and `verify_stage_order` are now parameterised so each is reachable, and one
  duplicate endpoint comparison was **removed** because B11a's `assert_matches_preregistration` is
  exactly that check. 69 tests, 94 subtests; **2,054 passing repository-wide**.
- **Launch, verified:** running read-only at 300 s. One `getSlot` poll observed, state
  `waiting_for_maturity`, tip 436,783,843 with 427,816 slots remaining, endpoint recorded as
  `https://mainnet.helius-rpc.com` with no query, **no credential in state or logs**, no receipts and
  no collection artifacts. Authorized read-only research collection; no paid service, no
  transaction, no signing.
- **Ratified by:** the Codex directive of handoff 96. **Owner review not separately obtained.**
- **NOT done:** no B10b paths, no B10c labels, no B11b evaluation, no outcome stage, no label
  enumeration unlock. **U4 and U5 remain a later explicit decision after collection.**

## 2026-08-02 — An adapter, not a fabricated B9a; and a status that can see death (B11c/B11d, handoff 99)

- **Decision:** the fresh window's cohort is derived by `b11d_cohort_adapter` from the B7d
  enumeration, carrying exactly the four columns B9c and B9d read — `mint`, `bonding_curve`,
  `launch_slot`, `is_mayhem_mode` — established by reading their SQL rather than assumed. The real
  table is `cohort_identity`; `outcome` is a VIEW over it so the consumers' SQL works unchanged.
- **Why not manufacture a B9a.** The tempting repair is a table called `outcome` with the identity
  columns filled and the rest null. Every gate downstream would run, and fabricated results would
  sit underneath a collection nobody could later distinguish from a real one. The table carries one
  column the view does not — `create_signature` — which is provenance and is also what proves the
  view is a projection rather than the table renamed; before it existed, `SELECT *` and the explicit
  column list produced identical views and neither guard could be driven.
- **Nothing is filtered.** Every create becomes a member, mayhem included: a cohort selected on any
  property of what happened afterwards is a cohort selected on the answer. Integrity failures
  **abort the build** rather than dropping rows, because a dropped row is a filter nobody declared.
  Coverage is asserted: every slot in the declared window visited and resolved, and any decode error
  aborts — an unscanned slot is a create nobody looked for.
- **Burned pins describe one corpus and no other.** b9d now distinguishes burned from fresh sources:
  burned keeps the pinned hashes and the frozen counts (94,985 signatures over 38,853 slots), fresh
  applies neither and must verify itself as a cohort artifact, and a **mixed pair is refused** —
  that collects one window's signatures under another window's identity map with no sign afterwards.
  A fresh population that derives nothing is still refused: its two sources do not agree.
- **A status that reads a file and asks nothing else cannot see death.** `--status` would have
  reported `waiting_for_maturity` indefinitely for a process that died days earlier. It now reports
  three independent signals and publishes the stored value separately as `reported_state`. **The pid
  check is the subtle one:** matching the module name in a command line answers "yes" for a test
  runner invoked on the test file — including the process asking the question — so it matches the
  script path and `--watch` together, and the test uses the test process itself as the adversary.
- **A correction to the prompting handoff.** Handoff 99 reported the watcher dead. It was alive:
  PPID 1, holding its flock, polls advancing on schedule. The liveness claim was not correct on the
  facts — but the defect underneath it was real, and the only reason the status was not misreporting
  is that the process happened to still be running. **A check that is right by luck is worth
  fixing.** The durability concern was fair too, and it now runs in a detached tmux session.
- **Two launch lessons, recorded because both were silent:** a tmux session inherits the SERVER's
  environment rather than the launching client's, so the first attempts died instantly with
  `SOLANA_RPC_URL is not set`; and `tmux new-session -e VAR=value` puts the value in a process argv
  where `ps` shows it to every user. The entrypoint sources `.env` itself, and a sweep across
  `/proc` confirms no process exposes the credential.
- **Verification:** 80 mutants across two sweeps, 80 killed, **none disclosed**. Four survivors were
  resolved by making guards real rather than by weakening tests, including adding the provenance
  column that made the view guards drivable. 2,109 passing repository-wide.
- **Running, verified from a separate shell:** pid 542344 in tmux `b11a-watcher`, liveness alive on
  all three signals, polls 3→4 in 260 s at a 300 s interval, tip 436,789,600 with 422,059 slots
  remaining, endpoint `https://mainnet.helius-rpc.com`, no credential anywhere, no receipts, no
  artifacts. The superseded pre-repair run is archived under `research/b11a/superseded/`, not erased.
- **Ratified by:** the Codex directive of handoff 99. **Owner review not separately obtained.**
- **NOT done:** no collection, no composition queried or published, no result stage, no label, no
  unlock. U4 and U5 remain a later explicit decision.

## 2026-08-04 — The tested 0.1 SOL direct-RPC launch snipe is rejected on cost and liquidity, and on nothing wider (B15Q, handoff 158)

- **Status:** accepted, for the tested configuration only
- **Ratified by:** agent-proposed (Codex directive of handoff 158; owner review not separately
  obtained)
- **Decision:** Reject the **current tested configuration** — a 100,000,000-lamport (0.1 SOL)
  direct-RPC launch snipe entered 1, 2 or 4 slots after launch and exited at 1,000 or 10,000 slots —
  on cost and liquidity grounds. Do **not** generalize the rejection to other position sizes, venues,
  entry delays, exit horizons, reactive books, or strategies.
- **Evidence:** `research/B15Q_CLEAN_REPLICATION_FINDING.md`, from the immutable artifact
  `research/b15q/replication.json`
  (sha256 `45644bc852d8ab15640bb852ee862e311167f58ea0b589ffb2d35410742c0f6b`), preregistered alone at
  `b116f0f` before any figure was computed, and independently audited at handoff 154 with every
  published figure recomputed from stored evidence and **0 mismatching fields**.
  - On 5,000 consecutive launches with fees decoded from each launch's own transaction, the round
    trip is negative at the median in **all eighteen** scenario×horizon×delay groups: −10,735,986 to
    −15,002,651 lamports on a 100,000,000-lamport position, with 96.48%–98.81% of priced cells at or
    below zero.
  - External liquidity capacity — what the **observed** book could absorb, excluding reserves our own
    buy would have added — has a median of **12 to 15 lamports**, against a position roughly seven
    million times larger. Only 9.9%–17.9% of cells could absorb the full position.
  - The median net is negative at every size on the frozen grid and worsens monotonically with size.
- **Reason:** No estimate of landing probability is required to reach this conclusion. Landing
  probability scales exposure to an opportunity that is negative at the median and, on roughly 90% of
  cells, not executable at this size at all — so a higher landing rate makes this configuration
  worse, not better. The figures are already generous to the strategy: the counterfactual credits our
  own buy's contribution to the exit reserves, and on 86.5% of priced cells the observed book could
  not pay for the sale at all.
- **Consequence:** This configuration is not promoted and is not a candidate for any later
  authorization. It is **not** evidence against the venue, against launch-time entry in general, or
  in favour of any alternative size — measuring a different configuration requires its own
  preregistration and its own evidence.
- **Limitations preserved, and none of them are closed by this entry:** landing probability and
  competitor response are **unmeasured** (the assumption is `UNREACTING_ORDER_FLOW`, and the
  self-impact diagnostic is a lower bound on that error, formable on only 13.5% of cells); 904 of
  5,000 members published no fee basis points at t0 and are absent as coverage, never filled from a
  later trade; the h_1000_slots and h_10000_slots populations **differ** (4,163–4,229 cells per delay
  against 5,000, the gap concentrated in the earliest launches through prospective-only scheduling),
  so the gap between their medians is not a horizon effect; and **no return, expected value, profit
  or probability of any outcome is claimed**.
- **NOT done:** nothing was signed, simulated, submitted or spent; no threshold, model gate or live
  worker was touched; the B15O artifact recording the empty-population result stands unedited beside
  this one.

## 2026-08-04 — B11 collection is GO after the Chainstack Growth archive unlock (B11c, handoff 162)

- **Status:** accepted
- **Ratified by:** user (the Growth upgrade was the owner's decision, and the owner asked for the
  archive capacity to be used); verified by Claude at handoff 162
- **Decision:** The operational verdict on the armed B11c nine-stage pipeline changes from **NO-GO**
  (handoff 161) to **GO**. No code changed and the watcher was not restarted: the endpoint URL is
  unchanged and the entitlement is account-side, so the running process inherited it.
- **What was blocking, and what cleared it:** the previous plan answered HTTP 403 / JSON-RPC `-32002`
  "Archive, Debug and Trace requests are not available on your current plan" for `getBlocks`,
  `getBlock`, `getBlockTime` and `getSignaturesForAddress`. Under Growth, all ten method-and-parameter
  shapes the nine stages actually issue now return HTTP 200 with the expected semantic shape, probed
  against preserved slot 433894233 and public program constants only. Archive depth is unrestricted —
  a header-only `getBlock` is served at slot 1.
- **Re-verified alongside it:** liveness on all three signals, manifest `a5b7c9fb` equal to disk (13
  files), both preregistration hashes and the state's pin, the window re-derived from the burned
  register and disjoint from all seven burned ranges, nine stages resolved, B11e dry run `passed` with
  no findings and all four gates exiting non-zero on an empty artifact, zero stages, zero receipts, no
  quarantine, and the endpoint recorded as scheme+host with no credential anywhere.
- **Cost, measured rather than assumed, and correcting handoff 161:** `getBlock` with
  `jsonParsed`/`full` — one call per launch-window slot — measures a mean 1,527 ms and 6.53 MB, not
  the 250 ms handoff 161 assumed. On the burned corpus analogue (the same 203,601-slot span) the run
  is therefore roughly **342,000 requests, ~1.34 TB of transfer and ~36.5 hours**, dominated by
  `enumerate_creates` (~21.6 h at its default 4 workers) and by `transaction_bodies` (~14.9 h at
  b9d's fixed 2.5 calls/second). The earlier 18–20 hour figure was too optimistic.
- **Headroom:** disk 129 GB free against ~5.6 GB of expected artifacts (b7d persists decoded events
  and slot summaries, never raw blocks, so the 1.34 TB is transient transfer). Memory measures ~31 MB
  per worker and ~122 MB peak at four, against ~1.2 GB available. File descriptors ample.
- **The one thing not verified:** Growth request-unit headroom. The endpoint exposes no rate, quota
  or credit headers, so the RU budget for ~342,000 calls of this weight cannot be read from the RPC
  side and must be confirmed in the Chainstack console. This is a stated residual risk, not a
  measured pass.
- **Residual operational risk carried forward from handoff 161, and now larger:** b9c and
  `b7d.rpc_block` treat 5xx as terminal where b9d retries it, so a single transient gateway error in
  `enumerate_creates` or `signature_inventory` quarantines the run. Over a ~36-hour pass rather than
  the ~18 hours previously estimated, that is roughly twice the exposure. Fail-closed and resumable,
  but it will stop the pipeline. `b11c` is also still absent from its own MANIFEST_FILES.
- **NOT done:** no stage run early, no fresh-window query, no composition inspected, no cadence or
  concurrency changed, no provider switched, no signing/simulation/submission/spend, and no change to
  B15Q, the B15 workers or any model gate.
## 2026-08-06 — Wallet, treasury and emergency-control boundaries are architecture only (B19a)

- **Status:** design recorded; unimplemented and operator-unratified.
- **Decision:** any future execution system separates research/decision services, an independent
  risk service, a keyless transaction builder, an isolated policy-enforcing signer, a dedicated
  balance-limited operating wallet, and an offline/manual treasury. The browser console remains
  read-only. Emergency state belongs to a separate minimal control process, defaults engaged on
  uncertainty, and never auto-clears.
- **Reason:** a strategy, recorder, UI or builder compromise must not imply custody or unbounded
  spending. Approval binds the exact proposal, risk decision and full transaction message; the
  signer independently refuses unknown programs/accounts, extra instructions, stale evidence,
  changed fees/tips, duplicate hashes or an engaged/ambiguous emergency state.
- **Not authorized:** no wallet/address/key is created, no signer or control service is implemented,
  no limit is selected or ratified, and no funding, signing, simulation, submission or transaction
  occurs. Phase 5b, Phase 6, legal/tax review and explicit owner authorization remain gates.
- **Specification:** `research/B19A_WALLET_TREASURY_ARCHITECTURE.md`.
- **Independently audited 2026-08-07** (Claude, handoff 194). Four defects and one omission were
  corrected in the specification; the audit and its findings are recorded in that document's final
  section. The material one: the compromise table credited signer policy with bounding the loss from
  a compromised signer host, and an attacker holding that host holds the policy too — the operating
  wallet balance is the only real bound there.

## 2026-08-07 — The strategy backlog is preregistered before B11 lands, not after (B19b/c/d)

- **Status:** accepted; documents frozen, no study run.
- **Ratified by:** the owner, who chose slice D over slice E when both agent seats had recommended
  waiting for B11. Recorded as an owner decision rather than an agent preference because it
  reverses the advice in handoffs 195 and 197.
- **Decision:** the three open G5 questions are preregistered now —
  `research/B19B_EXIT_TIMING_POLICY_PREREGISTRATION.json`,
  `research/B19C_CAPACITY_WALL_SIZE_DEPENDENCE_PREREGISTRATION.json` and
  `research/B19D_NON_ISSUANCE_SIGNAL_PREREGISTRATION.json` — with canonical hashes pinned in
  `scripts/b19_preregistration_register.py`, which refuses a changed or non-conforming document.
- **Reason, which reverses the earlier argument:** a preregistration's value comes entirely from
  being fixed before the evidence it will be judged against exists. The burned sets (B8b/B9/B10/B16)
  exist today and will still exist later, so waiting does not shrink the fitting surface by one
  byte — it only adds B11's result to what is known at authorship. After B11 lands, a B11-adjacent
  preregistration cannot honestly be written at all. Both agent seats subsequently accepted this.
- **Three disciplines added beyond the B16d template**, because a hash pin does not produce them:
  a mandatory `known_at_authorship_time` disclosure block, so a later reader can audit the fit
  rather than trust an assurance; **no tunable threshold by construction** — B19d's candidate
  signals are all booleans drawn from the frozen B11b t0 contract, and a boolean has no cut to
  move; and questions whose *specification* would depend on B11's output shape are deferred in
  writing with a reason rather than written thinly and amended later.
- **Sequencing:** the preregistration documents are committed **alone**, before the register and
  its tests, so the git history itself shows they preceded the analysis. A preregistration committed
  alongside the code that consumes it cannot later be shown to have come first.
- **NOT done:** no study was run, no outcome computed, no threshold chosen, no size recommended, no
  B11a composition or outcome read, no network call, and no wallet, signer or control service
  implemented. B19d may be evaluated only on a window nobody has read; burned-corpus runs are
  development-only and may never be reported as evaluation.

## 2026-08-07 — Mutation evidence becomes reproducible, forward only (G7)

- **Status:** accepted; framework in place, two sweeps declared.
- **Ratified by:** the owner, after the claude seat found the gap and the codex seat sized it and
  proposed the constraints. Neither agent started it; it touches both lanes.
- **The gap:** mutation numbers are what this project cites to claim a test is load-bearing, and
  **131 of 270 commits cite them**, while every sweep producing them lived in a scratch directory
  deleted at session end. A reader could re-run the suite and could not re-run the thing that
  establishes the suite means anything. Same species as the failure the B17c gap map exists for.
- **Decision:** `scripts/mutation_sweep.py` makes a sweep a declared, committed, re-runnable
  artefact — `research/mutation/<id>.sweep.json` in, `<id>.result.json` out — with four properties
  chosen because the obvious implementation fails in ways that look like success: an unmatched
  pattern refuses rather than skipping; a green baseline is required before any mutant counts;
  every mutant is applied to a **staged copy of the git-tracked tree** and never to the working
  tree, which is re-hashed and asserted byte-identical on exit; and survivors must be declared in
  data with a justification, with the sweep refusing both an undeclared survivor and a declared one
  that starts being killed.
- **Why the staged copy is non-negotiable here:** a live watcher has run for days holding its code
  in memory and four files are manifest-pinned. Restore-in-finally does not survive SIGKILL. This
  is the same upgrade B18c made — structure instead of care.
- **Not in the default suite:** a sweep costs minutes per target and a suite people stop running is
  worse than the gap. The suite checks only that declarations are well-formed and that every
  declared mutant still matches its target, which is the decay that would silently empty a sweep.
- **Self-applied:** 18/18 killed, 0 survivors. Two guards no correct run can trigger were extracted
  into `assert_within` and `assert_tree_unchanged` so tests could reach them; inline they would
  have been checks that cannot fire and would have survived while reading as protection.
- **FORWARD ONLY, and recorded rather than implied:** the 131 historical mutation figures are
  **reported and not reproduced**. They are not retrofitted — infeasible, and a `research/mutation/`
  directory appearing now would make every past number look reproducible by association. Only
  declared sweeps are re-runnable; at this commit those are `b19` (15/15) and `mutation_sweep`
  (18/18).
- **NOT done:** no existing sweep result was re-derived or corrected, no test was changed to make a
  mutant die, and the b18a/b18b/b18c sweeps remain unported — they are the claude seat's lane.

## 2026-08-07 — The emergency-state owner is implemented (slice E, closing G6)

- **Status:** implemented; unwired and operator-unratified.
- **Ratified by:** the owner, explicitly. This is the control-service class a standing instruction
  forbids implementing, and no accumulation of evidence substituted for being told to build it.
  Both agent seats had held it blocked all session on exactly that ground.
- **Decision:** `scripts/b20a_emergency_state.py` owns emergency state and implements B19a's
  required semantics without inventing any. Engaged is the default at process start and on no
  state, an unreadable or malformed record, a bad MAC, a missing secret, a stale heartbeat, a clock
  conflict, or verifier disagreement — ten reason codes of which exactly one is not engaged. The
  read path NEVER raises and never returns unknown, because a read that raised would hand the
  decision back to the caller, which is the gap G6 described.
- **It closes the reader/writer gap:** `b12a.assert_health` refuses a snapshot omitting
  `kill_switch_engaged` or `emergency_state`, and nothing produced either. `health_fields` now does,
  and a test carries them through `assert_health` into `_health_reasons` and asserts R01 and R02.
- **Clearing is the only privileged operation** and the only route to a not-engaged state: an
  authenticated operator, a reason, the generation they believe is current, and a durable
  append-only receipt. It never happens by restart or timeout. Engaging requires no strategy, RPC or
  signer, because a control that is hard to pull is not a control.
- **Two independent verifiers**, per B19a: the state file and the tail of the append-only receipt
  log, read through different paths. Disagreement engages. A test shows the state file alone
  verifies perfectly in every disagreement case, which is why one reader is not enough.
- **Custody boundary held:** no wallet, key, address or transaction, verified by running B17a's
  execution-surface scanner over the module rather than asserting it. The single secret is an
  operator authentication secret, environment-only and never in argv, used to MAC a local state
  file; it authenticates a human to a local control process and cannot authorize a transaction
  because nothing here can construct one.
- **Console untouched:** `snapshot` is read-only and a test asserts neither
  `ui/operator_console.html` nor `scripts/b12b_preview_server.py` references this module.
- **Guards:** 48 tests, both runners; mutation sweep 25/25, 0 survivors. The sweep's first run
  surfaced two tests passing for a neighbouring guard's reason — the `recorded_unix_nanos`
  future-check was masked by the heartbeat check, and the heartbeat-cannot-clear test was kept alive
  by verifier disagreement rather than by the heartbeat. Both now isolate the guard they name.
- **A guard whose claim changed:** `test_the_kill_switch_really_has_no_writer` asserted an absence
  this slice deliberately filled. It is now `test_the_kill_switch_has_exactly_one_owner`, because
  two components answering "is the switch engaged" is worse than none — they can disagree and both
  look authoritative. The inventory's ABSENT entry became SUPERSEDED and states what remains absent.
- **NOT done:** nothing consumes it. b12b does not read the snapshot, no process runs the heartbeat,
  no operator surface invokes engage or clear, no limit is ratified, and no wallet, signer,
  transaction, signing, submission or spend exists anywhere. Phase 5b, Phase 6 and explicit owner
  authorization remain gates.

## 2026-08-07 — B11c cost and schedule measured in flight; the handoff-162 estimate is superseded

- **Status:** correction of record. No code changed, nothing was restarted, and the watcher was not
  touched — every figure below is passive observation of a run in progress.
- **Supersedes:** the cost paragraph of the 2026-08-05 GO decision (handoff 162). That decision
  itself corrected an earlier 18–20 hour figure as "too optimistic"; it was still optimistic, and
  for a reason neither estimate modelled.
- **Measured 2026-08-07 at 95.1% through `enumerate_creates` (193,600 / 203,601 slots), 65.7 hours
  into a run with no quarantine and zero retries:**

  | quantity | handoff 162 | measured |
  |---|---|---|
  | transfer per block | 6.53 MB | **11.5 MB average**; 17.0 MB in a directly sampled window |
  | `getBlock` latency | 1,527 ms | **4,800 ms** sustained |
  | rate | 9,430 slots/h implied | **~3,000 slots/h** |
  | `enumerate_creates` | ~21.6 h | **~69 h** (3.2x) |
  | whole nine-stage run | ~36.5 h | **not yet estimable; see below** |
  | transfer, this stage | — | **~2.3 TB** |

- **The reason, and it is not throttling.** Sustained throughput is 9.4 MB/s (76 Mbit/s) over
  `wlan0`; the machine has no wired interface. At 9.4 MB/s with ~17 MB blocks the ceiling is
  0.55 blocks/s, and the observed rate is 0.56 blocks/s. **The run is link-bound.** Zero retries,
  zero backoffs and zero 429s appear in 65.7 hours of stage log, so the provider is not limiting
  anything — the connection is simply full.
- **Why both estimates missed it:** each multiplied a probed per-call latency by the slot count and
  divided by worker count, which silently assumes bandwidth is free. Once a run is link-bound the
  worker count stops being a lever, which is why four workers buy nothing here. The probe also
  sampled unusually small blocks: Solana block size varies with network activity and the window's
  real average is ~1.8x what was probed.
- **Consequence for the remaining seven stages.** `transaction_bodies` (estimated 14.9 h at b9d's
  fixed 2.5 calls/second) is the other heavyweight and will meet the same ceiling. **No replacement
  whole-run figure is offered here**, because extrapolating one stage's overrun across seven
  differently-shaped stages would repeat the error being corrected. What is now known: the run is
  days rather than hours, and it is bounded by the link and not by the endpoint.
- **Disk is NOT the risk, and the earlier reasoning on that holds.** 98 MB is on disk after ~2.2 TB
  transferred — about 0.5 KB kept per slot, roughly 23,000x discarded. The stage projects to ~102 MB
  against 128 GB free. The transfer figure matters only for a metered or capped connection, which is
  a household constraint rather than a research one and is recorded here so it is not rediscovered.
- **Deliberately NOT done:** the network was not changed, no worker count was altered, no stage was
  restarted and nothing manifest-pinned was edited. The stage is ~3 hours from completion, the run
  has survived 65 hours without a quarantine, and this project has already lost two runs to
  transient network faults. Chasing an hour by moving a live run onto a different link is a bad
  trade, and the correct time to act on this is before the next heavy stage begins, not during one.

## 2026-08-07 — `transaction_bodies` is rate-bound, not link-bound; my own generalisation corrected

- **Status:** correction of an entry made earlier the same day. No code changed, nothing restarted,
  the watcher untouched.
- **Corrects:** the closing line of *"B11c cost and schedule measured in flight"* (023cd09), which
  said the run "is bounded by the link and not by the endpoint". **That is true of stage 2 and false
  of stage 5**, and stating it about "the run" was the same error this session has now recorded four
  times: a property proved of one part, asserted about the whole.
- **What binds `transaction_bodies`:** `b9d_transaction_bodies.py` paces itself at a fixed
  `calls_per_second=2.5`, and the watcher passes no override. Bandwidth would only bind above
  **3.76 MB per transaction** (9.4 MB/s ÷ 2.5 s⁻¹); a `getTransaction` response is tens of kilobytes,
  three orders of magnitude below that. **The measured 9.4 MB/s does not transfer to this stage.**
- **The floor, which is a fact and not an estimate:** elapsed ≥ `signatures / 2.5` seconds, whatever
  the network does. Sensitivity, offered as a table precisely because it is not a forecast:

  | signatures | floor |
  |---|---|
  | 100,000 | 11 h |
  | 500,000 | 2.3 days |
  | 1,000,000 | 4.6 days |
  | 3,000,000 | 13.9 days |

- **NO FORECAST IS OFFERED, because its input does not exist yet.** The signature count is produced
  by `signature_inventory`, **stage 4**; the pipeline is on stage 2. Until that stage completes there
  is no number to multiply, and any figure produced now would be a third derived estimate from a
  seat whose previous two were both corrected.
- **Why this is worth an entry rather than a note:** the run is currently reported by a
  within-stage slot meter that cannot see the seven stages behind it, which led both agent seats to
  describe B11 as nearly finished. It is on **stage 2 of 9**, and stage 5 has a hard floor that may
  be measured in days. Anyone planning against "nearly done" is planning against a meter reading
  something narrower than the question.
- **Bears on Slice D:** `B19B`/`B19C`/`B19D` are frozen and waiting on B11. The wait is
  substantially longer than either seat had assumed, which changes no decision but should stop the
  backlog being treated as nearly unblocked.

## 2026-08-07 — `b9d`'s 2.5 calls/second is calibrated to a different endpoint; recorded, not changed

- **Status:** observation recorded. **No code changed, nothing restarted, the watcher untouched.**
  Owner's decision on 2026-08-07 was to record and change nothing.
- **The mismatch.** `scripts/b9d_transaction_bodies.py` paces `transaction_bodies` at a hardcoded
  `calls_per_second=2.5`, and `b11c` passes no override. That figure is a **measured property of the
  FREE PUBLIC endpoint**: B6J's F40 records *"the free endpoint sustains ~2.5 `getTransaction`/s"*
  and states the ceiling was **server-side, not client-side**. B7A's comparison table measures
  Helius at **7.8/s** against the same demand. **The watcher runs on paid Chainstack Growth.**
- So a server-side ceiling of one provider is pacing collection against a different one. It is not a
  politeness setting — the original measurement says the limit belonged to the free endpoint.
- **Why it is worth recording before stage 5 rather than after.** `transaction_bodies` is
  rate-bound, not link-bound, with a floor of `signatures / rate` seconds. At one million signatures
  that is **4.6 days at 2.5/s** and roughly **1.5 days at 7.8/s**. It is the single largest lever on
  how long B11 takes, and the pipeline is on stage 2 of 9, so the window is open rather than past.
- **What was NOT done, deliberately:**
  - **Chainstack's actual `getTransaction` rate was not measured.** Doing so means firing RPC at the
    provider while a collection runs against it, and the run is at 2 d 21 h with no quarantine. The
    claim here is about the constant's **provenance**, not a measured superiority.
  - **No code was changed.** `b9d` is manifest-pinned collection code, and editing it while a
    watcher runs is forbidden.
- **The argument for changing nothing, which is not merely caution.** Altering a collection
  parameter has provenance consequences beyond speed: the manifest, the frozen population and the
  receipts all describe a pipeline configured a particular way. *"We could go faster"* is not the
  same claim as *"re-opening a frozen pipeline is safe"*, and only the first has any evidence.
- **This is the fifth instance today of a constant or instrument calibrated in one regime and
  applied to another** — after a latency probe that could not see bandwidth, Request Units that
  could not see bandwidth, random sampling that could not see a float boundary, and a within-stage
  slot meter read as whole-run progress. That pattern, rather than any individual figure, is the
  finding worth carrying forward.

## 2026-08-17 — B22B has been RUN; `MEASURED_B22B` becomes a gate on an artifact, not a flat refusal

- **Status:** decision, implemented. `scripts/trading_bot/costs.py`, `scripts/trading_bot/__init__.py`,
  `tests/test_t2_backtest_harness.py`. New data artifacts `research/B22B_SLIPPAGE_RESULT.json` and
  `research/B22G_BORROW_COST.json`. **Nothing committed; the frozen harness is untouched and still
  hashes to `a0f1b4c4…`.**

- **What changed and why.** `SlippageProvenance.MEASURED_B22B.assert_available()` used to refuse
  unconditionally, on the true statement that B22B had never been run. It has now been run over the
  full pinned 30-day 2025 sample, so that statement is false and the refusal would have been
  asserting a stale fact. The *rule* behind it is what must survive, so the refusal became a **gate
  on the result file**: the provenance is available only while `research/B22B_SLIPPAGE_RESULT.json`
  exists **and reports all 30 pinned days**. Delete it, or truncate it to a partial pass, and the rig
  refuses again. A partial pass presenting itself as the measurement is exactly the failure the
  checkpointed runner was added to prevent, so the gate refuses that case by name.

- **The measurement.** 429 triggered stock-days. At the 100 ms rung the median entry slippage is
  **0 bp of R** — 166 of 429 fill exactly at the stop — verdict **NOT_YET_FATAL**, the most
  favourable verdict the preregistration permits. The tail is where it bites: p90 **1181 bp of R**
  and p95 **1654 bp of R**, against the **800 bp of R** the paper reports as its own per-trade edge
  at the filter it uses. **Roughly one entry in ten costs more than the paper's whole edge**, and
  this is entry only.

- **Why the cost model charges the MEAN and not the median.** A backtest charges friction on every
  trade and sums it, so the quantity that governs the equity curve is the mean per trade. The median
  is zero, and a cost model whose headline number is zero is one bad inference from the failure this
  module exists to prevent. B22B records `sum` and `n` rather than a mean precisely so the mean can
  be taken exactly downstream.

- **Precision, deliberately changed.** The cost model reads `notional_centibp` (hundredths of a basis
  point), not `notional_bp`. Whole basis points are too coarse for this measurement: the typical
  entry gap is a fraction of a bp on a $50 stock, so integer bp truncates most of the distribution
  to 0 and makes a genuine small cost indistinguishable from no cost. The mean at 100 ms is
  **0.81 bp of notional**, which whole-bp arithmetic would have reported as zero.

- **`half_spread` is zero in the measured model, and that is not an omission.** B22B prices the fill
  at the prevailing ask (long) or bid (short) against a stop set at a traded level, so its number
  already contains the half-spread. Adding the 2.5 bp half-spread on top would double-count it. The
  component says so in its own source string rather than relying on a reader knowing it.

- **Borrow is now measured, and the old warning held.** `retail_taker_costs()` carried
  `borrow_annual = 0.003` with a source string warning that hard-to-borrow names are not that. B22G
  measured the ORB most-actives pool: easy-to-borrow median **0.33 %/yr**, hard-to-borrow median
  **10.28 %/yr**, p90 **123 %/yr**, max **259.96 %/yr**. New provenance `VENDOR_FEED_SNAPSHOT` for
  it, because a snapshot of somebody else's published feed is stronger than a paper's assumption and
  weaker than our own controlled measurement, and blurring it into either neighbour would lose that.

- **The finding a rate cannot express.** **36 of the 100 names in the ORB pool are hard-to-borrow AND
  `shortable=False` at Alpaca** — not an expensive short, no short at any price. The short leg is the
  *majority* of the rule's signals in this sample (227 of 429 triggered stock-days), and **17.2 % of
  those shorts are in names that cannot be shorted at this broker today**. That is not a cost the
  model can carry; it removes the trade. `measured_borrow_annual()` states it in the component's
  source string so it cannot be read as priced-in.

- **What was NOT done.** The frozen harness was not edited — only the runner, and only its fetch
  layer (per-stock-day checkpointing, backoff-retry, and a worker partition over the pinned days).
  Early-stopping the trade paging would have cut the run time several-fold and was **rejected after
  testing**: Alpaca's SIP trade pages are **not** monotonic in time (verified on NVDA, 138,665 trades
  over 14 pages), so truncating them could miss an earlier-timestamped breach. The run was left slow
  rather than made subtly wrong.

## 2026-08-17 — The cost model is PER SIDE; the exit leg was being charged the entry's zero spread

- **Status:** decision, implemented. **Ratified by:** agent-proposed (T6, correcting T5).
  `scripts/trading_bot/costs.py`, `scripts/trading_bot/engine.py`, `scripts/trading_bot/README.md`,
  `tests/test_t2_backtest_harness.py` (113 tests, all passing). New blocks appended to
  `research/B22B_SLIPPAGE_RESULT.json` and `research/B22G_BORROW_COST.json`. **Nothing committed;
  the frozen harness is untouched and still hashes to `a0f1b4c4…`.**

- **The defect.** `b22b_measured_costs()` carries `half_spread = 0`, and the entry above explains
  why that is correct: B22B prices the fill at the far side of the book against a stop set at a
  traded level, so its number already contains the spread. But `CostModel.trade_cost_fraction()`
  charged that single number **side-agnostically**, and `engine.py` handed it the lumped
  `|pos − prev|`. So every **exit** — a stop-loss market order or a market-on-close, neither of
  which B22B ever measured — was charged a **zero half-spread** and the entry's small measured
  drift. The task whose entire purpose was honest net returns shipped a cost model **3.44× cheaper
  than its own honest lower bound**, biased in the strategy's favour. That is the exact
  self-deception this programme exists to prevent, and it survived because "the half-spread is
  legitimately zero here" was true of the leg it was written about and false of the other one.

- **The fix.** There is no side-agnostic spread/slippage number any more.
  `split_turnover(previous, target)` decomposes each position change into the part that OPENS
  exposure and the part that CLOSES it — a +1 → −1 reversal is a 1.0 exit *and* a 1.0 entry, not
  "2.0 of turnover" — and the two legs are priced separately. The decomposition is asserted to sum
  to the old `|Δpos|`, so it reallocates turnover rather than inventing a charge.
  `spread_and_slippage_fraction()` and the one-argument `trade_cost_fraction()` both **refuse by
  name** instead of quietly pricing at the cheaper side, and a `CostModel` built without an exit
  side refuses to construct: absence is a refusal, never a zero.

- **What the exit is charged, and on what authority.** `exit_half_spread` = max(2.5 bp from
  Dyhrberg/Shkilko/Werner JFE 168 (2025), half of B22B's own **measured** mean quoted spread over
  the 429 triggered stock-days = 2.409 bp) → **2.5 bp**. Two unrelated sources landing within 4% of
  each other is the useful part; charging the larger is the guardrail. `exit_extra_slippage` = the
  entry's measured magnitude charged **again**, under a new provenance
  `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG` so it can never be read as a measurement of the exit. A
  stop exit is triggered *by* the move going against the position and an MOC takes whatever the
  auction clears at; no mechanism makes either systematically gentler than a stop entry, and the
  alternative was zero.

- **Round trip, corrected: 1.63 bp → 5.59 bp** (entry 1.55 + exit 4.05), against
  `retail_taker_costs()` at 5.00 bp. The measured model is now the *more* expensive of the two,
  which is the right way round: it is the one carrying an unmeasured leg.

- **The headline entry mean was contaminated, and the contamination flattered us.** The
  preregistered trigger is "first trade at or through the stop", and SIP includes odd-lot and
  out-of-sequence prints, so a dislocated print triggers a stock-day at a level nobody could trade;
  the fill is then measured against a stop that was never really touched, lands in the
  **favourable** tail, and pulls the charged **mean** down. The 1-ATR sensitivity already in the
  result file is too loose to catch the very print its own prose cites — TSLA 2025-03-12, a sell
  stop at $244.30 triggered by a $223.92 print against a $248.07 bid, is **0.92 ATR** through and
  survives it. `measured_extra_slippage(atr_filter=…)` now names a rung of a published ladder;
  default **0.1 ATR**, which is not arbitrary but **one full R** (R ≡ 10% of ATR(14), the paper's
  own risk unit). Mean charged: **0.813 → 1.545 bp (+90%)**. Sensitivity, reported next to it and
  in the component's own source string: 1.0 ATR 0.852 (+4.8%), 0.5 ATR 1.210 (+48.8%), 0.1 ATR
  1.545 (+90.0%). `atr_filter=None` still gives the raw preregistered mean and the component then
  calls itself CONTAMINATED.

- **Two claims from the previous entry are withdrawn as overstated.**
  1. **"36 of the 100 names cannot be shorted at any price"** — wrong denominator and an overclaim.
     100 is the size of the ORB **screen input**; the B22B rule only ever screened **52** names, of
     which **8 are hard-to-borrow and not shortable at Alpaca — 15.4%, not 36%**. And a broker flag
     measures *this broker's* willingness to locate, not the borrow market: **7 of the 11**
     hard-to-borrow names with an obtainable IBKR rate have shares **available** to borrow there at
     2.32–259.96%/yr. They are expensive, not impossible — a **cost** elsewhere, not a constraint.
     The correct wording is **"not shortable at Alpaca"**.
  2. **"17.2% of shorts are unavailable"** is arithmetically right (39 of 227) but was presented as
     a borrow-market fact. **38 of those 39** signals are in **leveraged or inverse ETPs** (SQQQ,
     TSLL, SOXL, SOXS, MSTU) — an Alpaca **product** restriction, not borrow scarcity. Exactly
     **one** is an ordinary common stock (ONDS). A universe filter or a different broker removes
     most of the constraint. The corrected figures live in
     `B22G_BORROW_COST.json → t6_correction_screened_universe` and are read from there by the cost
     component, which refuses if the block is missing rather than reverting to the old wording.

- **Tests were changed to CATCH the old behaviour, not to record the new one.** The new
  `PerSideCostTests` were run against a rebuilt pre-T6 model as a negative control: the exit-costs-
  more assertion, the ≥5 bp round-trip assertion and the lumped-turnover refusal all **fail**
  against it and pass against the fix. `test_the_measured_model_does_not_charge_the_spread_twice`
  was kept (the entry zero is still right) and extended to require the exit spread to be non-zero
  — the two halves of that test are exactly the distinction that was missed.

- **Stated limit, not fixed here.** A position still open on the final bar is never closed and so
  never pays an exit; that is honest marking, but it means buy-and-hold pays one entry and no exit,
  and a comparison against it must not credit the difference. Also unchanged: the exit proxy is a
  proxy. The real fix is a measured exit, which needs a new pinned harness — B22B is entry-only by
  design and was not touched.

## 2026-08-18 — The T4 paper bot never filled: `tif=cls` EXPIRES on Alpaca paper, and a non-fill was accruing a phantom weight

- **The defect is measured, not inferred.** T4 was scheduled, firing, owner-authorised and
  arithmetically correct, and it had placed exactly one order: `3a5487f8-b9bc-46b2-89a1-f19ba46e964c`,
  93 SPY BUY, `type=market`, `time_in_force=cls`, submitted `2026-08-17T13:50:54Z`. At the close it
  came back `status="expired"`, `filled_qty=0`, `filled_avg_price=null`, and `GET /v2/positions/SPY`
  returned 404. **Alpaca's PAPER account does not run the closing auction; a market-on-close order
  sits all day and expires.** The account's whole order history says the same thing — four orders,
  three `cls`/`opg` probes and this one, zero fills, ever. So the forward test was not accruing
  slowly, it was accruing *never*, and would have done so indefinitely without saying so.

- **The execution mechanism changed and nothing else did.** The order is now
  `type=market, time_in_force=day`, submitted inside `ACTION_WINDOW_ET = 15:50–15:58 ET`, which
  fills immediately against the paper book. **Verified byte-identical across the change on a pinned
  clock**, which is the §3 test and the reason this is being reported as maintenance at all:
  `target_weight = 0.7242369236978444`, `realised_vol_annual = 0.13807636248289454`,
  reference close `2026-08-14`, **93 shares BUY** — before and after, along with the entire
  `decision`, `data` and `sizing` blocks. Only `type` and `time_in_force` moved. `T13_FROZEN_CONFIG`,
  `T13_PREREGISTRATION.md` and `T4_FORWARD_PREREGISTRATION.md` were not touched and their hashes
  still verify (`0eda5f7a…`, `42ef30e1…`, `52f3eea2…`).

- **THE SECOND BUG WAS WORSE THAN THE FIRST, and it was invisible.** Nothing noticed the non-fill.
  The decision the expired order was meant to execute stayed queued in `pending_weights`, and two
  runs later `bind_pending_weight` would have filed a **0.724 weight** into `weight_changes` and
  `settle` would have advanced the curves for a position **the account never held**. That is a
  fabricated track record, and in the PnL a phantom weight is indistinguishable from a real one.
  `reconcile_fill` now resolves an order into one of three states: filled (decision stands; a
  *partial* fill is flagged for FG3, never silently re-derived), terminal with zero shares (**the
  pending weight is dropped** — no position was established, so the previous weight stayed in force,
  which is what the account actually did), or still live (order *and* decision left outstanding and
  re-asked next run; dropping either would be guessing). Six tests pin this, including an end-to-end
  one that expires an order and then asserts `weight_changes == {}`, `settled == []` and
  `equity == 1.0`.

- **The priced rail is now knowingly NOT the executed rail, and that is recorded rather than
  restated.** The cost model is still M0's auction rail — a MEASURED zero half-spread, measured for
  an auction this bot no longer trades. A near-close market order crosses the spread and takes a few
  minutes of drift, so the auction number is a **lower bound** and `cost_if_taker_rail` (2.5 bp/side)
  is the better model of what is actually paid. **The primary model was deliberately not switched**:
  restating an accrual mid-flight is exactly what the frozen protocol reserves to FG4, which measures
  the realised shortfall, and to T4 prereg §5, which restates the entire accrual at the taker rail if
  FG4 fails. Every record now carries `costs.rail_note` saying so, and `forward_eval`'s FG4 block
  carries `rail_measured`, derived from `ACTION_WINDOW_ET` so the label cannot drift from the
  schedule it describes. Note also that `shortfall_bp_adverse_positive` **changed meaning** on this
  date — near-close market fill vs the print, not auction fill vs the print. Same field, not the same
  measurement; the drift is unbiased so FG4's *median* threshold still reads correctly, but the
  dispersion will be wider.

- **OPEN SCOPE CALL FOR THE OWNER — the classification is genuinely ambiguous and is not the agent's
  to settle.** §3's *operative test* — "would the fix change the weight the strategy targets on a day
  it already traded?" — is verified **NO**, which makes this maintenance and the ledger continues.
  But §3's *table* lists **"the execution rail or order type"** in the rule-change column, and
  `FORWARD_REGISTER.json` describes T4's rail as `"market-on-close both sides, Alpaca PAPER"`, which
  is now false. §3 itself says ambiguous cases go to the owner with a recommendation.
  **Recommendation: treat it as maintenance and continue the ledger** — the operative test is
  unambiguous, and the register records **0 settled sessions and 0 fills**, so there is no accrued
  evidence that continuing could launder; standing up a new forward test to repair a bot that never
  once executed would be ceremony over substance. **Either way the register's `rail` field must be
  corrected**, and because the register is a control document that edit was left to the owner rather
  than made unilaterally. Proposed value:
  `"near-close market order (type=market, tif=day, 15:50-15:58 ET) both sides, Alpaca PAPER; was market-on-close until 2026-08-18, which expired unfilled"`.

- **NOT CONFIRMED: a live fill.** The fix was completed while the market was closed (18:47 ET, next
  open 09:30 ET 2026-08-18), so **no order has yet filled on the paper account and this entry does
  not claim one.** What was proven: the submit path refuses correctly against the *real* broker clock
  while the market is closed; the exact payload `run_session` POSTs is `type=market`,
  `time_in_force=day`, `qty=93`; and a full end-to-end `run_session` submit against a stubbed
  transport (real class, real gates, real payload builder) writes the fill, the pending order and the
  byte-identical sizing. **The 2026-08-18 session at 15:50 ET is what will confirm an actual fill**,
  and until `fill_reconciliation.position_established` is `true` on a real record, it is unconfirmed.

- **The scheduler is now part of the execution price, and the installed cron is thin.** A market DAY
  order fills *when it is sent*. The window's lower bound is 15:50 specifically because the installed
  `*/10 12-23 * * 1-5` fires on ten-minute marks — a tighter 15:55–15:58 window would never fire, and
  a fix that needs a second uninstalled fix is not a fix. That leaves **one attempt per day**;
  `50-58 12-23 * * 1-5` gives nine and is recommended in `T4_FORWARD.md`. **The crontab was not
  edited** (the change was blocked by the permission layer and is an operator action). A separate
  named guard, `SUBMIT_HARD_CUTOFF_ET = 15:59`, refuses submission independently of the window,
  because a market DAY order landing after the bell queues to the **next open** and would establish
  the weight one session late at a price from the wrong session — the one execution failure that
  would corrupt the ledger rather than merely miss a day.

## 2026-08-27 — Memecoin paper evaluation uses executable/full-loss adjudication; clean V3 replaces mixed sniper ledgers

- **Status:** decision, implemented; **PAPER ONLY**. No wallet, signer, key, order, transfer or on-chain
  write was added or enabled. Old append-only ledgers and frozen instruments were not rewritten.

- **Verified fact — legacy sniper accounting was not one experiment.** The local all-ledger audit found
  that `live_trades*.jsonl` mixed rows that were gross of toll/tip with later rows that charged both.
  Its typical inverse-vol order was about **$0.10** while the pinned fixed priority-fee estimate was
  **$0.075 round trip**, or 75% of notional before venue toll and slippage. Repricing the legacy arms
  under the current pinned costs makes every arm strongly negative (roughly −1.3R mean). Those files
  persisted only resolutions: 13 historical watchdog restarts could silently lose open positions and
  their `frozen_sha256` cannot be recomputed from retained fields. At controlled retirement, the final
  scorecards still showed **70 open paper positions**; their point-in-time counts and source hashes are
  preserved in `SNIPER_LEGACY_CUTOVER_2026-08-27.json` and full-loss stressed. Earlier dropout identities
  remain unknowable.

- **Decision — explicit USD/equity units and append-only lifecycle.** Sniper sizing is now an explicit
  **$1,000 paper equity per arm**, 2% of *current* equity, $2 minimum, Pump bonding-curve only. Losses
  change subsequent order sizes. Entry events fsync the full signal, intent, fill, costs, config, equity,
  canonical commitment and hashes before outcome; a terminal event carries both reported and stress R.
  Gap-through stops use the worse observed close. A silent horizon has no executable stale-price fill and
  is full-loss adjudicated. A true process restart terminally marks unresolved entries
  `INVALID_RESTART_GAP`, charges −100% plus pinned costs, and restores the next process from that reduced
  adjudication equity.

- **Decision — reconnect is not restart.** V2 immediately demonstrated that ordinary public-stream
  disconnects rebuilt the strategy book every few minutes. The runtime now exists once per OS process;
  provider reconnects preserve positions, peaks and flow streaks. V2 remains immutable engineering
  evidence, including deployment-triggered invalidations, and is not used as the clean strategy cohort.
  Clean **V3** began only after that fix with empty `v3_*` ledgers and preregistration SHA-256
  `ea486d591f426bfaec0c8d12a2d7e3b2a711405659b78d9e441582d76191e5e9`. Its primary gate is stress
  equity/mean R after 100 terminal entries per arm; that paper gate still does not authorize live trading.

- **Verified fact — EXIT did not test Pump.fun.** At the audit snapshot, all 20 resolved PASS trades in
  `MEMEBOT_EXIT` were non-Pump venues; its $10k reserve floor selected away from the repository's initial
  Pump bonding-curve scope. It also valued an unavailable exit at the −25% stop floor. The old freeze and
  ledger remain untouched. New `MEMEBOT_EXIT_V2` is separately frozen: Pump-only scope (off-venue rows
  enter neither PASS nor control), ≥3 demonstrated sellers, $3k reserve floor, eight-minute horizon,
  worse-observed stop gaps and −100% unavailable-exit recovery. Its pre-registration hash is
  `8ffeeb2c250b7fa3c7a8276cfe2263f7a65c682a3d3495d93c51cf7341ae3e96`.

- **Verified fact and decision — genome fitness had survivorship bias.** Terminal `UNPRICED` PASS rows
  outnumbered priced PASS rows, yet v1 excluded them from `pass_R`; one genome could also be simultaneously
  falsified and re-declared because the declaration pass ignored the falsified registry. Fitness v2 ranks,
  kills, declares and confirms on a terminal stream in which `UNPRICED`/`UNEXITABLE` receive the full-loss
  bound; a claim must clear both displayed priced R and stress R on a fresh slice. Falsified ids cannot
  re-declare. Provider refusal/budget exhaustion is labeled `UNPRICED_PROVIDER_UNAVAILABLE`, not a fake
  executable stop, and refresh work is call/wall-clock bounded so a 429 cannot block state persistence or
  selection. Existing generations remain adaptive-search history, not clean evidence. At implementation,
  no genome cleared the K-corrected bar after full-loss stress and no edge was confirmed.

- **Verification.** Hermetic MEMEBOT and genome selftests pass; sniper strategy selftest passes 34/34;
  V2/V3 ledger selftest proves recomputable entry commitments, idempotent restart invalidation and reduced-
  equity restoration. `memecoin_trade_audit.py` hash-pins the exact byte snapshots it reads and reports
  legacy, V2/V3, all frozen MEMEBOT instruments and every genome ledger without summing parallel arms into
  a fictitious portfolio.

## 2026-08-27 — Failed memecoin gates now stop entries; archived EVO remains inside the all-trade census

- **Status:** decision, implemented and independently re-verified; **PAPER ONLY**. No wallet, signer,
  order, transfer or on-chain write was added or enabled. Historical/frozen rows were not rewritten.

- **Verified fact — Claude's honest-measurement continuation is present and passes locally.** Sniper
  entry/mark/resolution events now reopen reconstructable positions across a true process restart and
  invalidate only malformed/unreconstructable entries; the restart selftest passes and the controlled
  runtime restart reported zero invalidations. MEMEBOT scoring makes full-loss stress the displayed
  decider, its seen-pool cache evicts by recency, and EVO V2 refuses preregistration/hash or engine-
  constant drift. EVO V1 was moved intact to `memebot_evo/v1_archive` and V2 began at generation zero.

- **Decision — a HALTED decider is an entry gate, not dashboard decoration.** MEMEBOT previously showed
  `honest-kill HALTED` while `scan_once` continued opening PASS and control rows. The scanner now records
  the newly-seen universe and continues resolving existing positions, but opens nothing new for an
  instrument whose full-loss-stress kill is HALTED. Sniper V3 similarly kept accumulating hundreds of
  entries after its frozen N=100 review gate had failed. Its entry path now permanently closes at/after
  N=100 unless stress mean R > 0, stress equity exceeds the $1,000 initial equity, and accounting is
  clean. All three V3 arms failed, so V3 is retired from new entries; one last-open position was left to
  drain normally. The point-in-time basis is pinned in `SNIPER_V3_RETIREMENT_2026-08-27.json`.

- **Verified fact — the loss mechanism is broad, not one tunable threshold.** In the clean V3 cohort,
  every fixed surge, buy-fraction, liquidity and notional slice with at least 20 terminal observations
  remained negative. `exit:maxhold_timeout` supplied roughly 34–48% of negative R and trail exits roughly
  32–42%. The CONFIRM state machine was not a strict BALANCED subset: after waiting it rechecked only buy
  fraction, so some entries fired below the base surge/liquidity thresholds and it accumulated more
  entries than BALANCED. This is recorded as a mechanism defect for any future design; the frozen V3
  detector is not silently edited.

- **Verified fact and working-hypothesis boundary — EXIT_V2 is still killed by the unavailable tail.**
  At 16 terminal PASS rows, six targets contributed +11.28R, four stop gaps −7.33R and four unavailable
  exits −16.48R. The unavailable rows supplied 68.8% of all negative R. Conditional on the observed
  non-unavailable payoff, break-even would require an unavailable rate below about 8.18%, versus 25%
  observed. That 8.18% is explicitly post-hoc and is not a new screen rule. EXIT_V2 remains unchanged
  until its frozen N=30 minimum; no V3/V4 threshold is selected from these rows.

- **Decision — experiment namespace is part of genome identity.** The all-trade audit now scans both
  current `ledgers/` and `v1_archive/ledgers/`, with separate population/state/K bars. Two deterministic
  seed ids recur in both experiments, so bare genome id cannot key a combined census. At the snapshot,
  V1 contained 94 ledger arms, 2,354 terminal PASS arm-observations and a 64.4% unpriced rate; its priced
  mean was +0.585R but full-loss stress was −4.732R, with no K-corrected clearer. Current V2 remains
  immature and unchanged.

- **Verification and artifacts.** `memecoin_audit_selftest` pins archive inclusion, duplicate ids across
  experiments, loss attribution and the exitability mixture equation. Sniper restart/strategy/execution/
  signal, MEMEBOT and EVO selftests pass. `MEMECOIN_TRADE_AUDIT.{json,md}` is the complete hash-pinned
  census; `MEMECOIN_LOSS_DIAGNOSTICS.{json,md}` is explicitly post-hoc causal attribution, not a result
  or a license to optimize on the same observations.

## 2026-08-27 — AFTERSHOCK execution-realism engine (handoff 422 durable choices)

Building the measurement-chain repair BEFORE any secondary-sell test. Pure, paper-only, no network/wallet/signing. Not integrated into V1–V5; current V1–V5 post-reset books are BURNED / plumbing-only, never evidence.

- **Latency is a REQUIRED caller-supplied parameter, no default.** The 2-slot/4-slot values from the first design are WITHDRAWN — landing/latency/slippage/failure distributions are UNMEASURED (B17B records clocks, no calibrated distribution). Missing latency ⇒ refuse. Any sensitivity ladder is `CALIBRATION_UNCALIBRATED` robustness plumbing — not strategy arms, not executable evidence, cannot promote real money.
- **Observation ≠ canonical identity.** Input carries `observation_unix_nanos` (local receive) separate from a canonical coordinate `(slot, transaction_index, outer_index, inner_index)` + integer pre/post reserves + source/evidence hashes. Decisions use only locally-observed events; later reconciliation may canonicalize but never rewrites a decision. Late/out-of-order/conflicting ⇒ no-trade/invalid, never retrospective reorder. PumpPortal-only tape has no canonical order ⇒ every result labeled `PUMPPORTAL_RECEIVE_TIME_SCENARIO` + uncalibrated, never "canonical" or "executable".
- **Fill semantics.** Order sent ⇒ lands against the reserve state *immediately before* its landing coordinate, subject to a frozen max-in/min-out/slippage bound; bound violated ⇒ `failed_on_chain/dropped/expired`, attempt cost charged, each retry a distinct attempt. Fill coordinate STRICTLY AFTER all signal evidence; never the trigger state. Cannot bracket the landing state ⇒ refuse (or bounded worst-case), never a stale state. Clock invariant: observation ≤ decision ≤ build ≤ send < land.
- **Own impact = b10a integer kernel only (immediate).** We do NOT persist our reserve delta into later observed states nor replay external orders against shifted reserves (repo proves no Pump instruction variant makes that exact). Every path keeps the b10b `SIMULATED_OBSERVED_PATH` limitation. Returns are an observed-state SCENARIO until a separately-authorized Phase-2 forward-fill calibration; not "executable".
- **Restart is event-sourced.** Append-only session record + last-observed canonical coordinate persisted (fsync) before processing; on restart resume state-sourced; gap/state-loss ⇒ no entries until a full post-restart warm-up window; pre-activation state is a point snapshot only, may not seed wallet/flow/shock windows. Activation event fsynced before subscribe/scan, referencing already-sealed hashes; never mutate a manifest to insert activation after evidence.
- **Fail-CLOSED freeze.** `freeze_epoch` refuses missing/malformed/naive/non-UTC timestamps (no `return 0.0`); parse explicit-offset UTC only.
- **Manifest seal (no self-referential cycle).** Seal prereg-md + canonical-JSON + engine/constants hashes FIRST; then append a separately-hashed activation event that REFERENCES that seal.
- **Numeraire/rent.** SOL_USD is per-entry point-in-time evidence (source+timestamp+value), not one frozen constant; `q_sol = target_usd / observed_SOLUSD`. Remove the impossible simultaneous `bankroll_usd=100` & `bankroll_sol=5`. Report return in SOL AND USD-equity separately (SOL beta ≠ memecoin edge). ATA rent is LOCKED capital with an explicit lifecycle: `NOT_CREATED/PREEXISTING | LOCKED | RECLAIMED_FULL_SELL_CLOSE | CLOSE_FAILED | STRANDED_AT_HORIZON`; reclaim only on proven zero balance + successful close; a partial exit never reclaims. Pin the caller-stated rent + actual close-tx cost.

## 2026-08-28 — AFTERSHOCK handoff 424 closes caller-verification, activation-root, detector-evidence, and clock seams

- **Status:** decision, implemented and locally verified; **PAPER-ONLY MEASUREMENT PLUMBING**. No strategy
  thresholds, outcome books, wallet, signing, submission, devnet, or live-trading path changed. V1–V5
  remain burned/plumbing evidence and are not integrated with this chain.

- **Verified fact — caller attestation was removed.** `ExecutionContext` now contains only a
  manifest-derived `SessionProof`; the former caller-set `verified` and `warmup_complete` booleans no
  longer exist. The public decision and attempt paths reload the latest seal/session proof every time.
  A seal must be tracked and clean against `HEAD` before activation, and every completed first/restart
  session needs a separately tracked, clean activation-root file. Rehashing the complete activation chain
  after backdating fails against those committed roots. Deleting or dirtying any known historical root
  also refuses.

- **Decision — restart state is a new authorization epoch.** Every activation uses an internal clock.
  The frozen JSON states a minimum post-activation event count and receive-time span; the warm-up record
  stores and reconciles both endpoints and every event commitment. A restart requires a monotonic
  persisted canonical coordinate, invalidates the old proof immediately, and admits no decision until
  all warm-up coordinates are strictly post-resume and the new root is externally anchored.

- **Decision — the engine, not the caller, runs the sealed detector.** A `DecisionRecord` names the
  detector's repository-relative module path, callable, and sealed hash. The engine derives the complete
  receive-time prefix available at its internally recorded decision clock, loads the exact sealed module,
  and records the full prefix root plus every detector evidence commitment; `signal_index` is their
  maximum. Every attempt reruns that detector against the same prefix. A publicly rehashed record that
  omits a detector evidence item refuses rather than trusting a caller's evidence list.

- **Decision — unmeasured execution clocks stay null.** The latency input remains required and
  `CALIBRATION_UNCALIBRATED`, but it creates a `modeled_land_target`, not a claimed send/land time. The
  first later observation is named `scenario_boundary_observation`; build/send/land remain null. No
  future boundary yields `RIGHT_CENSORED_NO_BOUNDARY` with unknown cost, not “never sent.” Positive quote
  results are explicitly `SCENARIO_*`, always `SIMULATED_OBSERVED_PATH`, and PumpPortal additionally
  `PUMPPORTAL_RECEIVE_TIME_SCENARIO`.

- **Verified fact — cost, unit, state, sizing, and rent seams are fail-closed.** B10a is invoked with
  `failed_attempts=0`, so retries cannot hide inside another record's 210k cost; each retry has a distinct
  content id and immediate predecessor. Only B10a's named `SimulationRefused` maps to quote unavailability;
  unknown exceptions propagate. Intent/output units, reserve signs, exact integers, costs, slippage bounds,
  point-in-time SOL/USD evidence, sub-lamport sizing, and the full ATA lifecycle are validated.

- **Dependency and verification boundary.** The seal uses the real `b10b_position_path.py` and pins the
  B10a/B9i/B9d chain, RPC identity module, official pinned IDLs, generic execution modules, and an exact
  non-empty future-experiment module list declared in canonical frozen JSON. The 56-check adversarial
  execution selftest and the full AFTERSHOCK bundle pass. Positive unit fixtures emulate git anchoring;
  no real experiment seal/activation root was created or committed. Secondary-sell preregistration remains
  **NO-GO** until a separate frozen experiment and its owner-gated anchors exist; forward clock calibration
  and every promotion gate remain open.

## 2026-08-28 — Latest memecoin audit retires non-causal loops and fails closed on dead tick data

- **Status:** decision, implemented and locally verified; **PAPER ONLY**. No wallet, signer, order,
  transfer, or on-chain write was added or enabled. Existing ledgers were preserved byte-for-byte.

- **Verified fact — operations were productive, returns were not yet profitable.** The point-in-time
  all-trade census at `2026-08-27T23:48:03Z` contains 16,458 legacy sniper resolutions, 1,640 terminal
  clean V3 sniper rows, 141 frozen MEMEBOT PASS rows, and 4,566 current EVO V2 resolutions. Every
  investable frozen arm remains negative after honest costs/stress. `MEMEBOT_EXIT_V2` reduced the
  unavailable-exit rate to 15.62% versus 40--58% in older fast/exit variants and outperformed its control,
  but still lost `-0.7770R` per PASS trade and its frozen honest-kill gate is closed. Increasing size would
  multiply a measured negative expectancy; it is not a fee fix.

- **Verified fact — the current evolutionary sub-minute search measured a dead oracle.** Its Bitquery
  mint-keyed candle cache stopped advancing on 2026-08-25. The server reports `usage quota reached`, while
  the ingester's server-error branch performed a clean `break`, reset backoff on the preceding ACK, and
  reconnected hundreds of times per minute. The sub-minute census was 1,851/1,851 terminal outcomes
  without a priced tick path (PASS and controls combined). `status` also crashed when a stress-mature
  genome had no priced t-statistic.

- **Decision — unavailable entry data refuses before an entry exists.** Every sub-minute PASS and control
  candidate now requires a causal local tick at or before the common scan decision time and no more than
  ten seconds old. Missing, future-only, malformed, or stale data refuses. Ten seconds is a data-validity
  ceiling tied to the existing 4--8 second writer flush cadence, not a fitted return threshold. The
  Bitquery ingester now treats server errors as typed failures, resets health only after actual data, and
  applies a 300-second quota/traffic circuit-breaker. The running read-only ingester was restarted and the
  observed quota path now logs one `reconnect in 300s`, not a busy loop.

- **Decision — EVO V2 and legacy AFTERSHOCK V1--V3 are retired, not silently amended.** EVO V2 results
  existed before the entry-data repair, so continuing under the same freeze would mix measurement regimes.
  `EVO_V2_RETIREMENT.json` closes track/scan/selection while preserving all files; a future search requires
  a separately frozen V3. AFTERSHOCK V1--V3 still used the burned historical entry/exit resolver even after
  the causal engine was built. Their watchdogs now terminate exact legacy loop command lines and never
  restart them. V4/V5 remain retired. No old AFTERSHOCK book is evidence.

- **Decision — secondary-sell claims match observable data.** `AFTERSHOCK_SS` now detects two sequential
  0.05-SOL reserve-withdrawal/recovery cycles; it does not claim independent sellers or fresh independent
  capital because actor/cluster completeness is absent. Recovery 2 must be the newest observed event, so
  an old pattern cannot fire later. Its evidence is exactly four coordinates. Exact point-in-time $10
  sizing must be no larger than the fixed 0.05-SOL evidence floor (thus refuses below SOL/USD $200), and
  selftests write only in a temporary evidence directory. SS remains scenario-only and NO-GO: add/exit,
  calibrated latency, capacity/cluster gates, and an anchored forward runner are still incomplete.

- **Verification.** MEMEBOT_EVO selftest passes including missing/stale/future-only tick refusal; the
  read-only `status` path now reports the zero-priced case without crashing. Bitquery circuit-breaker
  selftest passes. AFTERSHOCK_SS detector + public decision/attempt path passes, including stale-pattern
  refusal, sizing coverage, and temp-only manifest artifacts. The full AFTERSHOCK execution bundle remains
  required before any future freeze. These tests verify machinery, not edge.

## 2026-08-28 — Consolidate memecoin research into one PAC successor; retire all strategy loops

- **Status:** decision, implemented and locally verified; **PAPER/SCENARIO ONLY**. No wallet, signer,
  transaction construction, submission, funding, or live execution was added. No legacy ledger was
  deleted or rewritten.

- **Verified fact — there is no currently proven profitable bot to select.** Every investable frozen
  sniper/MEMEBOT/EVO arm failed honest costs or had no priced path. The least-bad legacy AFTERSHOCK
  headline was V2 arm C at roughly +2.3% pot growth, but both entry and exit selected historical boundary
  states unavailable at the bot's action time. `AFTERSHOCK_V2_RETIREMENT.json` therefore records it as
  burned non-causal evidence; a reset may not inherit its P&L, positions, or thresholds.

- **Decision — operational consolidation.** The MEMEBOT and sniper watchdogs now terminate only their
  exact strategy command lines and never restart them, matching the already retired EVO V2 and AFTERSHOCK
  V1--V5 watchdogs. Host-process verification found none of those strategy loops alive. The read-only
  RPC tape ingester, quota-backed Bitquery collector, MEMEBOT listener, and dashboard remain because they
  collect/display evidence and cannot place orders. `aftershock.frozen.ACTIVE_INSTRUMENTS` is empty.

- **Working hypothesis — Payable Absorption Compression (PAC).** A fresh instrument,
  `AFTERSHOCK_PAC_V1`, observes two sequential full reserve-recovery cycles and admits only when the second
  withdrawal is at least as large, its recovery is no slower, and both the pre-withdrawal and recovered
  external-SOL baselines do not decline. Equivalently, with withdrawals `W`, durations `D`, pre-reserves
  `B`, and recovered reserves `E`, `min(W2/W1, D1/D2, B2/B1, E2/E1) >= 1`, evaluated component-wise using
  exact integers. This is a causal mechanism hypothesis, not a fitted or verified edge; no independent-
  wallet/fresh-capital claim is made.

- **Decision — meaningful but non-compounding discovery size.** The frozen paper probe is exactly $10
  from a $100 bankroll, at most one position, no add and no $2 dust. Point-in-time Decimal SOL/USD sizing
  must fit inside both demonstrated withdrawals. Scaling/compounding requires a new frozen policy after
  positive discovery and untouched confirmation; it cannot be inferred from the invalid V2 headline.

- **Decision — uncapped causal exit hypothesis.** PAC has no take-profit or partial exit. It tracks the
  curve-exact quote for selling the whole position, requests one causal exit after a 12% give-back,
  coverage below 6x, or 12 minutes, and records an unavailable quote as unexitable full loss rather than a
  fictitious exit/mark. Every actual scenario sell still requires a later boundary through the execution
  engine; the pure policy is not a fill.

- **Burned feasibility only.** After freezing the formula, a read-only terminal-prefix census found 12
  PAC signals among 1,979 valid cached prefixes (0.61%) versus 47 for the weaker secondary-sell rule.
  Median pattern span was 23.20 seconds and median smaller withdrawal 0.157 SOL. Duplicate provider-second
  timestamps required a deterministic +1ns diagnostic tie-break. These numbers prove only that the rule
  is non-empty; they contain no returns and cannot select or tune a threshold.

- **Decision — causal feed provenance is part of the instrument.** Live tape rows now retain an exact
  local `received_unix_nanos`, explicit observation source, mint, reconciled reserves, and transaction
  signature. Legacy float/provider-time rows may seed the preceding reserve state but may never become
  PAC evidence. Public-RPC observations are labelled `PUBLIC_RPC_PROCESSED`, not PumpPortal. The global
  warm-up proof is receive-ordered across mints; a per-mint decision stream must begin strictly after that
  global boundary. This repairs the earlier one-mint activation assumption without inventing cross-mint
  state continuity.

- **Decision — point-in-time USD sizing uses retained primary evidence.** The read-only recorder stores
  Coinbase Exchange `SOL-USD` last-trade raw JSON, its SHA-256, provider trade time, request-start clock,
  local receipt clock, and the exact Decimal price. It refuses stale, future, malformed, tampered, or
  wrong-numeraire observations. Primary documentation accessed 2026-08-28:
  `https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker` and
  `https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-single-product`.

- **Verification and open gates.** PAC detector/policy tests pass 17 controls, the tape adapter passes 7,
  and the SOL/USD recorder passes 4. They cover stale/weaker/slower/eroded/forged evidence, unavailable
  quotes, exact-$10 sizing, cross-mint global warm-up, source/signature enforcement, raw-price
  reconciliation, and a later-boundary real-kernel entry. The execution engine's 56-control regression
  also passes. `AFTERSHOCK_PAC_V1_SEAL.json` now verifies 25 declared dependencies, including the proposed
  runner, but is **UNANCHORED**. It is not committed and no activation chain/root exists. The runner core
  is built but failed the subsequent accounting/causality re-audit described below; latency and
  submission-failure scenarios remain uncalibrated. Therefore no PAC trade, return, promotion, or
  real-money claim exists.

## 2026-08-28 — PAC dashboard is fail-closed; proposed runner remains NO-GO after re-audit

- **Verified fact — the proposed exit loop decides after simulating the sell.** `pac_runner.poll_exit`
  first creates an `EXACT_TOKEN_SELL` AttemptRecord and only then gives that attempt's output to
  `pac_policy.decide_exit`. When the policy returns `HOLD`, a `SCENARIO_FILLED` sell attempt is discarded
  as if it were merely a quote. A causal implementation must observe a non-mutating quote at decision
  time, decide whether to request an exit, and only then create an order attempt that can land at a later
  boundary. The existing nine positive runner tests do not exercise this ordering defect.

- **Verified fact — the proposed resolved return is gross/incomplete.** Its ledger calculates
  `sell_quote - quote_input`; it does not subtract entry/exit curve fees, entry and exit attempt costs, or
  measured ATA rent. The execution adapter exposes attempt gas separately and the B10a kernel exposes the
  exact curve fees and wallet deltas, but the runner does not persist/reconcile them. That output cannot
  satisfy the frozen `positive_after_all_costs` gate.

- **Verified fact — state and ledger are not crash-atomic.** Resolution is appended before the updated
  open book is saved, while opening is appended before the newly open book is saved. A crash between
  those files can double-resolve/reopen or leave an orphan event; there is no event id/idempotent replay or
  pending transaction journal. No PAC production state/ledger exists yet, so this finding burns no data.

- **Decision — performance display refuses incomplete evidence.** The new read-only `#/pac` dashboard
  polls its small state/ledger every two seconds and displays formula, operational gates, feed freshness, discovery progress,
  open book, exact all-cost R, win/full-loss rates, drawdown, activity, and a visible 100-index curve. Its
  adapter publishes performance only for anchored schema-2 rows where each resolution references one
  earlier entry and exactly reconciles all-in entry cost to net exit proceeds. Gross/legacy rows,
  duplicate event ids, state/ledger mismatch, an unfinished crash transaction, malformed rows, or
  unanchored evidence all fail closed and leave the chart at an explicitly labelled baseline. The index
  is `100 + 10 × all-cost return` per fixed discovery probe; it is labelled normalized and is not USD P&L.
  The slow seal/tape inventory is cached for 60 seconds, while SOL/USD freshness is independently checked
  from the latest raw-hash-reconciled recorder row, so fast chart refresh does not compete with ingestion.

- **Verification.** PAC dashboard negative controls pass 7/7. Python compilation and JavaScript syntax
  checks pass. The live local API reports `NO_FORWARD_EVIDENCE`, `NOT_ACTIVE`, `UNANCHORED`, zero resolved,
  and no open position; a headless browser render confirms the chart, gates, table, and two-second live
  indicator are visible. The read-only dashboard process was restarted; no strategy process was enabled.

## 2026-08-28 — PAC runner mechanics promoted from NO-GO to paper-scenario GO

- **Verified fact — no PAC outcome existed before repair.** The production PAC state and scenario ledger
  were absent, the seal was uncommitted, and no activation chain existed. The runner defects could
  therefore be corrected and preregistered before observing a strategy outcome; no result was discarded,
  migrated, or used to choose the repair parameters.

- **Decision — quote, decision, and order are separate causal states.** The exit policy now consumes a
  non-mutating, curve-exact net full-position quote at the newest decision-state reserve. `HOLD` persists
  only its peak and creates no attempt. Trail, capacity, or horizon persists a complete sealed
  DecisionRecord and a 1,000-bps decision-quote guard before a sell can be attempted; the attempt can fill
  only at the first observed boundary after decision time plus explicit positive latency. Entry uses the
  same durable decision-before-attempt chain. Production code no longer accepts a caller-injected clock.

- **Decision — every wallet component is retained.** Entry all-in cost is quote input plus curve fee,
  recorded attempt cost, and ATA rent. Exit net proceeds are gross curve quote minus curve fee and
  recorded attempt cost. No separately evidenced ATA-close attempt exists, so discovery conservatively
  charges rent and invents no refund. Slippage failures are separate portfolio-cost events. Unavailable
  exit evidence remains an exact full loss and never becomes a mark or fictitious fill.

- **Decision — state/ledger is restart-exact.** Schema-2 state holds at most one open position and one
  pending order, binds to one activation session, and journals self-hashed schema-2 ledger rows before
  append. Append is idempotent by authenticated event id; restart replays an interrupted journal exactly
  once. A continuous paper command now holds a single-process lock and writes the next scan watermark
  before discovery. First start skips backlog; crashes may omit a window but cannot admit it later.
  Reaction latency is mandatory on the command line and deliberately has no default.

- **Decision — scope of GO.** `runner_audit=GO_CAUSAL_ALL_COST_CRASH_ATOMIC` means the paper-scenario
  plumbing cleared these four defects. It is not evidence of edge, executable calibration, activation,
  wallet readiness, or profit. The regenerated 25-dependency seal
  `e9fb7a9ba6bb64063a9fd0ba4147d28fb8fc20e5be89373fa12c0a003cebbe82` verifies locally but remains
  UNANCHORED; owner-gated commit, activation/warm-up anchor, measured latency/failure calibration, 100
  resolved discovery positions, and untouched confirmation remain open.

- **Verification.** Execution engine 56/56; runner 18/18 including HOLD-without-attempt, later-boundary
  entry/exit, exact all-cost reconciliation, unavailable full loss, two injected crash boundaries,
  tamper refusal, explicit latency, no-backfill watermark, and exclusive lock; dashboard 7/7 including
  failed-attempt cost in the portfolio curve. The dashboard runner gate recognizes the scoped `GO_`
  status and failed attempts appear as activity. Its watchdog now matches exact argv fields instead of a
  loose process-name substring that could mistake an inspector command for the server. The read-only
  server was restarted and its local API reports the new runner GO. These tests validate mechanics, not
  strategy performance.

## 2026-08-28 — PAC seal anchored and first paper-scenario session activated

- **Decision — owner gate opened explicitly.** The user explicitly authorized committing and activating
  PAC. Commit `e202719` contains the complete dirty portion of the 25-dependency seal closure plus the
  preregistration, frozen JSON, and seal; it does not sweep unrelated worktree changes. Seal
  `e9fb7a9ba6bb64063a9fd0ba4147d28fb8fc20e5be89373fa12c0a003cebbe82` now reports `ANCHORED`.

- **Verified fact — the activation evidence is strictly post-commit and post-activation.** The set-once
  first activation is `335d3c874e00c3cfcefba19d21a4558d1b7e01ea4074f94e68328c8d61af07b5`.
  Feed-global warm-up selected 30 valid `public_rpc_processed` observations spanning 700,619,697 ns; the
  root is `f7327fb45bcc2d3fed3965d3731ceabafff813e43f30952629180f975208416b` and its anchor is
  `e1a569422f8c42e363bfc06b42e3f3f7f03966396dcb8d5d06f51fb821d262c9`. One mint file failed closed on
  impossible negative reserves and was neither repaired nor admitted. Commit `244b523` anchors both the
  activation hash-chain and root; manifest-derived SessionProof re-verifies them from disk.

- **Decision — start one uncalibrated paper scenario, not a performance claim.** The first foreground
  cycle returned exactly `WATERMARK_INITIALIZED_NO_BACKFILL`. The persistent sealed runner then started
  with explicit `reaction_nanos=800000000`, the original two-slot scenario proposal; this remains
  `CALIBRATION_UNCALIBRATED` and cannot be relabelled executable. The read-only dashboard reports
  `ACTIVE_PAPER_SCENARIO`, live process/watermark, both anchors, and the remaining calibration/discovery/
  confirmation gates. A first $10-sized entry decision is pending a strictly later observed boundary;
  there are still zero fills, ledger rows, or performance observations, so `NO_FORWARD_EVIDENCE` is the
  only valid performance status.

- **Boundary.** No wallet, key, signer, transaction construction, transaction submission, real SOL, live
  order, compounding, or promotion was added. Activation licenses only the anchored uncalibrated paper
  collection already preregistered.
## 2026-08-28 — PAC incomplete-prefix and terminal-exit liveness repair

- **Verified fact:** PAC session 1 created one entry DecisionRecord and no AttemptRecord, fill, open
  position, ledger row, resolved outcome, or performance observation. The mint tape later contained 431
  observations, but the runner refused every service cycle with `DecisionRecord omitted an observation
  already available at decision time`. Candidate enumeration had captured an older cutoff than the
  engine-owned decision clock, so the persisted prefix became incomplete before its first attempt.
- **Decision:** Burn sessions 1 and 2 as measurement diagnostics. Never backfill either missed signal or
  score a hypothetical buy/sell. Schema-3 binds each DecisionRecord to the exact processed-stream count
  and hash available to the detector. Rows materialized later are excluded from that frozen detector
  prefix even when their receive clock predates the decision, but remain in the full reserve path so the
  eventual fill boundary inherits every intervening trade. Mutation or omission inside the committed
  snapshot still refuses. Right-censored entries become no-trades and release their lock; a censored
  non-horizon exit requires a fresh decision; a censored hard-horizon exit is an exact stressed full loss.
  When gas makes triggered all-cost exit proceeds non-positive, settle an exact full loss without
  inventing a sale or charging an unobserved attempt.
- **Decision:** `800,000,000` ns remains `CALIBRATION_UNCALIBRATED`. Its resolved feasibility scenarios
  may be charted with that label but contribute zero to the 100-position promotion discovery count.
  Promotion counting requires separately frozen measured build/sign/send/land and failure clocks.
- **Verified fact:** Under the third anchored session, a fresh signal passed the processed-snapshot path,
  the first terminal entry chain released without wedging, a subsequent fresh decision filled strictly
  later, and one schema-2 `opened` ledger row was reconciled to the schema-3 state. The runner continues
  causal exit polling; this verifies liveness mechanics only, not profitability.
- **Open question:** No measured sign/send/land path exists in this paper-only repository. Closing that
  gate requires a separately authorized forward-clock stage; it cannot be inferred from public market
  receive timestamps.

## 2026-08-28 — PAC fixed-deadline pipeline optimization

- **Verified fact:** The pre-optimization session completed two all-cost uncalibrated scenarios:
  `+17437723/97080989 R` and `-19433241/97241491 R`. Their combined normalized 100-index is
  `99.7977521167743469620453624452`. Both rows, state, activation chain, and seal are preserved in the
  session-3 archive. They remain plumbing evidence and contribute zero to promotion discovery.
- **Verified fact:** A production profile found 126 changed mint streams required 5.55 seconds per flat
  pass; repeated complete-tape decode consumed 4.54 seconds, after which the old loop slept another two
  seconds. On the same two-second inventory slice, bounded admission took 115.136 ms versus 721.701 ms
  for full decode (`6.27x`) with the same signal set.
- **Decision:** The optimized experiment starts a fresh denominator. Flat discovery runs the unchanged
  PAC detector on an exact-reserve receive-time tail bounded by the already-frozen 180-second pattern
  horizon. That result has admission authority only. A positive mint must still rebuild from the complete
  tape and pass the sealed provenance, ordering, hash, detector, coverage, decision, and later-boundary
  path. A per-mint decode refusal is surfaced and isolated; it can neither authorize entry nor halt other
  mints. Active-position corruption remains fail-closed.
- **Decision:** Scan starts use a fixed 250 ms deadline including compute time. Append-only SOL/USD sizing
  reads backward to the latest record available at the decision clock and retains full raw-hash/derived
  reconciliation. The SessionProof is cached for the flat hot path, reverified within five seconds, and
  independently reverified by every decision/attempt. A sealed supervisor restarts an unexpectedly
  exited runner after 250 ms and relies on the same state/session/journal validations after restart.
- **Verified fact:** The first 250 ms diagnostic session persisted 15 decisions across 340 cycles but
  produced zero attempts, fills, ledger rows, or outcomes: a poll before the modeled 800 ms landing was
  being mistaken for terminal right-censoring. That empty session is burned. The replacement distinguishes
  `WAITING_FOR_LANDING`; after landing it permits a fixed two-second observed-boundary wait before the
  existing bounded censor rule applies. This restores liveness without admitting a pre-landing fill.
- **Boundary:** The modeled landing delay remains `800,000,000` ns and
  `CALIBRATION_UNCALIBRATED`. Formula, thresholds, `$10` size, costs, trail, horizon, and promotion gates
  are unchanged. Faster local observation is not measured transaction execution and adds no wallet path.

## 2026-08-28 — PAC V1 killed as a strategy; PAC V2 challenger fixes the measurement boundary

- **Verified fact — V1 is decisively negative even before its full-loss tail.** The repaired dashboard
  validator now admits the sealed producer's exact two-row unavailable-exit relation without admitting a
  duplicate attempt. It validates 525 resolved all-cost scenarios: 113 wins, 412 losses, 28 full losses,
  21.52% win rate, mean −0.1255R, median −0.1286R, and normalized index −559.0818. The underlying curve
  move itself averages −8.21% (median −8.53%); entry friction averages 3.53% of quote and exit friction
  1.25%. Removing all 28 full losses still leaves the remaining book negative. Capacity exits are 1/56
  winners; the supposedly protective trail is 112/440 winners with mean −0.0691R. These are uncalibrated
  paper scenarios, not executable PnL, but they refute V1 as the focused mechanism rather than justify
  tuning it.

- **Verified fact — V1's liveness boundary remains structurally wrong.** Its current open position has a
  persisted trail-exit decision but waits for a later trade event; the mint can remain silent long after
  the observable spike/dump. The scanner's 800ms value remains unmeasured, and decision, materialization,
  and runner clocks cannot establish transaction landing. V1's sealed detector/policy/runner are therefore
  left byte-identical as a burned baseline. Its ledger is preserved and may not seed V2 thresholds.

- **Decision — PAC V2 is a separate frozen challenger, not a V1 retune.** It retains the two-cycle PAC
  core and exact $10 probe, then requires the second recovery to survive an authentic measured-p90
  execution dwell, at least three distinct observed buyer addresses, and real quote reserve at least 6×
  the larger of planned size and largest observed setup withdrawal. Address breadth is explicitly not
  ownership/funding independence. These gates were fixed from the causal failure analysis before V2 has
  any forward outcome.

- **Decision — account snapshots replace later-trade fills.** Entry and each requested full-position exit
  persist decision + calibrated-p90 target, then price the first processed bonding-curve account snapshot
  requested at/after that target through the existing exact-integer B10a kernel. No later trade is needed.
  Source-received, event-materialized, and runner-seen clocks remain separate. The consumer is incremental
  by durable byte offset and refuses truncation, orphan receipts, duplicate identities, backward clocks,
  wrong-owner/closed accounts, pinned-IDL drift, and state/runtime binding drift.

- **Decision — exit liveness is absolute and bounded.** Horizon is evaluated first at 12 minutes even
  when no event arrives; capacity <6× and the 12% quote trail follow. Snapshot observation may retry for
  30 seconds. At the horizon, unavailable/net-negative dust or observation timeout settles the conservative
  full-loss bound and releases the one-position lock. A non-horizon timeout returns to HOLD/redecision.
  Primary all-cost return continues charging ATA rent; no refund is claimed without a separately observed
  close-account attempt and cost.

- **Decision — authentic latency is a hard activation dependency.** There is no latency default and the
  old 800ms scenario cannot migrate. Activation requires a whole-file-hash-pinned artifact with at least
  100 unique authentic landed transactions and ordered decision/build/sign/send/ack/land clocks; exact
  nearest-rank p90 is derived by the loader. The repository has no authorized signer/sender/landing recorder,
  so V2 remains `CALIBRATION_REQUIRED_NOT_ACTIVE`. Synthetic selftest fixtures prove refusal/causality but
  cannot activate or become performance evidence.

- **Verification.** PAC V2 passes 23 controls including calibration count/tamper, dwell/breadth/erosion,
  horizon priority, exact account layout, incremental/orphan feed handling, post-target entry, no-new-trade
  horizon exit, restart non-replay, bounded horizon outage, and runtime-binding tamper. The complete
  AFTERSHOCK regression suite passes. The dashboard now labels V1 as baseline and surfaces V2's seal,
  calibration, activation, formula, and snapshot-execution status separately.

## 2026-08-28 — PAC V2 handoff-439 authenticity and liveness repair

- **Verified fact — the prior V2 seal was NO-GO.** The calibration file could validate caller-chosen
  clocks without proving a Solana landing; first-fill response time could exceed the cycle clock and
  crash before commit; permanent account-decode refusals escaped the bounded exit path. Snapshot age,
  activation freshness, first-event continuity, receipt recovery, and durable appends also had gaps.

- **Decision — authenticity is a campaign-bound three-artifact bundle.** A pre-sampling git commit binds
  one fee payer, distinct submit/verifier origins, and a memo-only transaction profile. Each sample's
  signed wire contains a deterministic SPL Memo challenge over campaign id, sample index, and previous
  sample id. A separate finalized RPC read must return the identical signature, wire bytes, fee payer,
  successful metadata and slot. Whole-file hashes and campaign → evidence → activation commit ancestry
  are rechecked on every runtime load. This prevents unrelated fee-payer transactions and self-hashed
  handwritten rows from satisfying the gate; it does not make local clocks a remote cryptographic oracle.

- **Decision — every lock-affecting refusal is durable and terminal where required.** Entry fills commit
  before policy service. A permanent snapshot/schema refusal rejects an entry and conservatively settles
  an open position as full loss; transport retries are bounded to 30 seconds, with horizon priority.
  Snapshot context must not predate decision evidence. Feed seeds cannot become evidence, interrupted
  event/receipt pairs recover with a later clock, orphan receipts advance visibly, and authority/state/
  ledger directory entries are fsynced.

- **Open gate — V2 is not active.** The repaired seal may be anchored, but no authentic 100-landing
  campaign, independent attestation, or later activation exists. Creating/funding a payer and sending
  the campaign transactions remains a separately authorized measurement stage. Until it exists, the
  supervisor must refuse and the dashboard must say `CALIBRATION_REQUIRED_NOT_ACTIVE`.

## 2026-08-29 — PAC V2 live cutoff deferral and allocated-account boundary

- **Verified fact — the cycle-cutoff refusal was structural.** In the handoff-444 live run,
  `consume()` read receipts appended after the runner sampled its engine-owned cycle clock and rejected
  the entire batch because `materialized_unix_nanos > runner_seen_unix_nanos`. Because consumption
  preceded pending-order completion, this also delayed an otherwise ready entry snapshot. The repair
  snapshots receipts before events, consumes only the receipt prefix materialized at or before the
  cycle cutoff, and leaves the first later receipt's byte offset plus its pending event for the next
  cycle. This also closes the valid event/receipt orphan race created by the prior events-first read.

- **Verified fact — the fill-time rejection rate was a decoder mismatch, not failed qualification.**
  The preserved processed-RPC exchanges accessed 2026-08-29 from
  `https://api.mainnet-beta.solana.com` contain 110/110 Pump-owned BondingCurve accounts over context
  slots 442,464,290–442,487,089 with the pinned discriminator and the pinned 115-byte IDL body inside
  an exact 151-byte allocation; every 36-byte allocation suffix is zero. The old exact-length check
  rejected all 30 attempted entries as `SNAPSHOT_PERMANENT_REFUSAL` before pricing. All 110 accounts
  also encode the native-SOL sentinel (`11111111111111111111111111111111`) in the quote-mint field;
  the old fixture and decoder incorrectly required the SPL wSOL mint instead.

- **Decision — allocated padding is admitted narrowly and visibly.** Snapshot decoding accepts the
  exact 115-byte IDL serialization or the observed 151-byte allocation only when bytes 115–150 are all
  zero, and requires the native-SOL sentinel in the quote field. The wSOL mint and any other length,
  discriminator, non-boolean field, quote mint, or non-zero reserved suffix refuse. This does not infer
  or ignore an unknown extension. The cutoff, allocation, and quote-sentinel changes are measurement-
  chain changes, so the old seal-bound calibration/activation cannot authorize the repaired runner; a
  new sealed campaign and clean calibration are required before restart.

## 2026-08-29 — PAC V2 collector reconnect is a reserve-continuity boundary

- **Verified fact:** The first post-activation paper run initialized successfully, then began refusing
  every cycle with `PAC V2 durable buffer ordering/reconciliation failed`. The durable per-mint buffer
  contained usable events from two collector epochs; the later epoch had correctly restarted its own
  continuity chain, so its first usable event could not reconcile to the prior epoch's last reserve.
  No PAC scenario ledger row or open/pending position was created by this run. The diagnostic state is
  preserved under `research/data/aftershock/pac_v2/superseded/`.
- **Decision:** A collector reconnect is a hard continuity boundary for strategy buffers. When the first
  usable event from a new `collector_epoch` arrives, the runner clears that mint's prior buffer before
  appending the event. `feed.consume()` continues to omit the epoch seed, so no synthetic cross-epoch
  reserve delta is admitted. An open position may still receive the newest observed post-state, but its
  qualification history cannot bridge the reconnect.
- **Boundary:** This is sealed runtime behavior. The existing activation cannot authorize the repaired
  code; a fresh seal, campaign-bound calibration, independent finalized attestations, and activation are
  required before restarting PAC V2. No calibration sample is reused across that seal change.
