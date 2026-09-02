# ARENA V2 — Master Build Plan (ultracode design+attack, 2026-09-02)

## Arm verdicts
- preboost: design=DESIGN_WITH_CAVEATS survives_attack=False buildable=False
- bundle2: design=DESIGN_READY survives_attack=False buildable=True
- migration: design=DESIGN_READY survives_attack=False buildable=True

## Framework design

{
 "arm": "SHARED_RUNTIME_FRAMEWORK (virality_arrival / bundle_momentum / graduation)",
 "verdict": "DESIGN_WITH_CAVEATS",
 "entry": "Unchanged shared open path: frozen entry_ok on at/before-decision features, cadence-gated, one-sample-per-mint, WAL append_opened. New sizer.py sets the clip and enforces a GLOBAL (not per-arm) max 2 concurrent PRIMARY via arena/portfolio.json under flock; fixed $10 clip = no martingale; clip <= 5% of causal_fill_cp exit capacity at entry reserves.",
 "exit": "exit_engine unchanged for real exits. RUG_UNPRICED no longer auto -100%: 3-consecutive-no-price enqueues state[pending_rug_checks] and leaves the position OPEN; a Helius arbiter resolves it PRIMARY total loss only on RUG_CONFIRMED (reserves below dust), else append_censored (right-censored VOID, excluded from PRIMARY N). Horizon with no confirmation -> censored, never a booked loss.",
 "executable_fill": "Arms 2/3 (bundle, graduation): causal_fill_cp walks the constant-product curve for the actual clip on both legs, caps exit at real withdrawable SOL, charges both tolls + lamports, decomposes marginal-vs-honest. Arm 1 (virality, free snapshot data) uses honest_fill_snapshot optimistic bound and is flagged exit_capacity_unverified \u2014 a PASS there earns only a causal re-test, never a money claim.",
 "prereg_pass_kill": "Interim KILL@30 (ci_hi<0); decide@120 DISTINCT mints. PASS requires ALL of: cluster-bootstrap ci_lo>0; median>0; no single-winner dominance (drop largest mint-cluster, re-bootstrap ci_lo>0 survives); max drawdown on the frozen-clip equity curve <= 40% bankroll; latency/liquidity stability (2x latency AND 25% reserve haircut both keep ci_lo>0). INVALID if censored_fraction exceeds the prereg cap or chain/distinct/pending gate trips.",
 "coverage_or_data_requirement": "Helius (funded, HELIUS_API_KEY, generous limits): one bounded getAsset+getAccountInfo per rug candidate on the bonding-curve/pool account \u2014 a one-shot sidecar verifier writing a verdict file, NOT an in-loop crawl. Reserves for causal arms come from the single PumpPortal listener buffer (ws_data.read_buffer), never a second tape socket. Snapshot arm has no reserves so cannot run exit-capacity sizing (flagged, not faked).",
 "buildable_today": true,
 "biggest_honesty_risk": "Informative censoring. A genuine liquidity pull kills the DexScreener price feed at the SAME instant it drains the curve, so a later Helius check that finds reserves 'present' (a partial/slow rug not yet complete, or a transient outage overlapping a real loss window) can misclassify a true loss as a censored VOID and bias the PRIMARY mean upward. Mitigation must be pre-registered: compare the Helius slot against last_good_mark_ns and book any reserve DROP between marks as RUG_CONFIRMED, cap censored_fraction as a validity gate, and report the censored cohort's would-be returns as a sensitivity bound \u2014 right-censoring is only unbiased if censoring is independent of outcome, which here it is not."
}

## Master build plan

I have enough grounding. I verified all three attack findings against the live code, and mapped the design packet onto the arena that already exists on disk. Here is the synthesis.

---

# ARENA V2 — MASTER BUILD PLAN

Verified against the live tree at `scripts/trading_bot/memebot/arena/`. The honesty spine (`fill.py`, `scorer.py`, `exit_engine.py`, `chainledger.py`, `manifest.py`) is already built and sound; `fill.py` correctly charges both tolls on the causal leg and decomposes marginal-vs-honest. The gaps below are real and confirmed in code, not hypothetical.

## PER-ARM VERDICT

### ARM 1 — Attention/virality
**Two distinct things collapsed into one slot; keep them separate.**

- **PREBOOST_ATTENTION_V1 (paid X filtered stream): REFUSE.** Attack `survives:false`. It cannot run at $0 — it needs X Pro (~$5k/mo) or the Enterprise firehose, and affordable Pro is volume-correlated-sampled (drops hardest exactly at a spike, so a distinct-author *count* threshold is a biased estimator). Its own flagged biggest risk — reflexivity/reverse-causality (whale buys, then tweets) — is real, and the honest enforcement of its own control split is a KILL, not a PASS. Full-CA mint binding is sparse-to-absent; symbols are spoofable. The stream has no replay, so a consumer crash fabricates both false lulls and false spikes. This is precisely the memory-flagged failure mode ("paid endpoints on unproven/reflexive theses have been money pits — LL latency chain"). **Do not spend on X Pro.** If the owner ever wants to revisit, the only honest first step is a $0 free-tier pre-measurement of real CA-mention density and delivery-time ordering — and that pre-check is expected to fail.

- **VIRALITY_ARRIVAL_V2_2 (free snapshot, already live): KEEP AS-IS.** This is the honest $0 substitute for the attention thesis and it already exists (`arms/virality_arrival.py`, collecting per the "Virality Gate-B live" memory). It is explicitly an OPTIMISTIC-BOUND filter (`honest_fill_snapshot`, `exit_capacity_unverified`): a KILL is decisive, a PASS earns only a causal re-test, never a money claim. It only needs to fold in the shared RUG fix below (its "6 -100% rugs" are the DexScreener price-unavailability artifact, not real rugs — the empirical ground truth). No rebuild.

### ARM 2 — BUNDLE_MOMENTUM_V2: **BUILD** (survived attack with a fixable must-fix list)
Attack `survives:false` but every hole is buildable today at $0 on funded Helius. The live code is still **V1** (`arms/bundle_momentum.py`: `SIZE_SOL=0.5`, no Helius, no coverage gate) — running it now is running the exact truncation artifact the design flags (41% of candidates show create→first-buy >5s). Must-fix before any activation, all confirmed in code:

1. **Coverage-VOID gate (unbuilt).** `bundle_runtime._process_row` opens purely on `BM.first_six_signal(...)` with zero on-chain cross-check. On-chain buys N…N+5 get scored as buys 1…6, corrupting *both* clump timing and the wallet-concentration set. Build a `getSignaturesForAddress(bonding-curve)` reconstruction of the true ordered first-K buys, query only after a bounded settlement delay `t0+Δ` (an immediate query validates truncation against an equally-unindexed chain), pin a deterministic buy/sell/wallet classifier matching PumpPortal `traderPublicKey` semantics, and VOID the mint if buffer-first-6 ≠ on-chain-first-6 — *inside `entry_ok`, before any `pending_entry` is created.*

2. **Created-set trim bug (false −100% generator), CONFIRMED.** `_created_after_activation` re-derives eligibility every cycle from `ws_data.read_buffer()` (trimmed to ~6000 creates ≈ a few hours < the 12h horizon). A still-open winner's create scrolls out → `_process_row` hits `if mint not in created: advance cursor; return` → `last_event_ns` freezes → `_timeouts` fires `DEAD_SILENCE → RUG_UNPRICED = −100%` on a live token. This preferentially destroys the long-lived winners that carry the CI. **Fix: persist the admitted mint set in `state["mints"]` once first seen; never re-derive from a trimmed buffer.**

3. **Decider doesn't enforce the prereg PASS rule, CONFIRMED.** `scorer.decide` gates only on cluster-bootstrap `ci_lo>0` + event-rate floor. The prereg additionally requires **positive median, no single-winner dominance, and manageable drawdown** — none implemented. On rug-prone lottery tokens one +N00% winner lifts `ci_lo>0` while the median is deeply negative = false PASS. (Note `graduation.py`'s `final_verdict` already adds a sign test + Bonferroni; `decide` itself still lacks median/dominance/drawdown for everyone.)

### ARM 3 — GRADUATION (MEMEBOT_GRAD_V1): **BUILD-CONDITIONAL**
Its adversarial-attack packet was **not included in this synthesis input** (truncated after bundle2), so I cannot certify it survived attack the way I can for bundle2. What I can say from the code: it is the **strongest-fill arm** — canonical/graduated PumpSwap pools, exact-CP quote math (`arms/graduation.py buy_quote`, `graduation_runtime.py`), price read from real pool reserves so it sidesteps the RUG_UNPRICED/DexScreener trap by construction, and it already has the most disciplined `final_verdict` (one-sided sign test at N≥30, 27-test Bonferroni-adjusted bootstrap at N=100, an explicit CONTROL_PROXY_FAIL cohort). Proceed on the shared-framework fixes, but **flag to the owner that Arm 3 has not been through the same red-team pass** — get its adversarial review before it earns any weight beyond COLLECTING.

**If Arm 2 and Arm 3 both fail their reads and PREBOOST stays refused, all three "offensive" arms are dead → pivot to X2_FLOWSTREAK** (real 2025–2026 orderbook coverage + aggTrades, possibly paid L2 around the 17.9 bp breakeven). Do not treat the surviving free snapshot filter as a money arm — a PASS there is only a causal-test ticket.

## BUILD ORDER — shared framework first, then arms

**Existing ledgers stay untouched.** V2 bundle gets a NEW instrument name + NEW ledger dir; the V1 `ledger.jsonl` and every existing prereg are frozen.

### Phase 0 — Shared framework (blocks everything)
1. **`arena/scorer.py`** — extend `decide()` to the full frozen PASS rule: add `median>0`; a single-winner/top-cluster dominance test (verdict flips if dropping the max `(mint,entry_day)` cluster kills `ci_lo>0`); a max-drawdown gate on the frozen-clip equity curve (≤40% bankroll); and the latency×liquidity stability grid as a gate, not a report line. Keep the cluster bootstrap. This one file fixes bundle must-fix #3 and hardens graduation and virality simultaneously.
2. **`arena/helius_rug_arbiter.py`** (NEW) — the RUG fix + informative-censoring guard. A one-shot sidecar (NOT an in-loop crawl): on a 3-consecutive-no-price / DEAD_SILENCE candidate, one bounded `getAsset`+`getAccountInfo` on the bonding-curve/pool account. Book **RUG_CONFIRMED (PRIMARY total loss)** only if reserves are below dust **or** dropped between `last_good_mark_ns` and the Helius slot; otherwise **right-censored VOID**, excluded from PRIMARY N. Writes a verdict file the runtime consumes. Pre-register `censored_fraction` as a validity gate and report the censored cohort's would-be returns as a sensitivity bound (right-censoring here is NOT independent of outcome — this is the framework's biggest honesty risk and must be stated, not hidden).
3. **`arena/sizer.py`** (NEW) — global (not per-arm) max-2 concurrent PRIMARY via `arena/portfolio.json` under `flock`; fixed $10 clip from the activation `sol_usd` (no martingale); clip ≤ 5% of `causal_fill_cp` exit capacity at entry, else reduce-or-VOID (frozen rule).
4. **Ledger cohort separation** — verify `chainledger.py` + each runtime bucket **controls / primary / voids / measurement-failures** as four distinct cohorts everywhere (append_opened/resolved/void already exist; add the censored/measurement-failure cohort so a read-failure is never scored as a rug or a loss).

### Phase 1 — Arm 2 (BUNDLE_MOMENTUM_V2)
5. **`arena/helius_coverage.py`** (NEW) — `getSignaturesForAddress` first-K reconstruction + `t0+Δ` settlement delay + PumpPortal-semantics classifier (bundle must-fix #1).
6. **`arena/arms/bundle_momentum_v2.py`** (NEW instrument `BUNDLE_MOMENTUM_V2`) — `SIZE_SOL` frozen from activation `sol_usd` (~0.05–0.067 SOL = a real $10 clip, replacing V1's 0.5); `entry_ok` calls the coverage gate before signalling; wires `sizer.py`.
7. **`arena/bundle_runtime.py`** — persist the admitted mint set (must-fix #2); route RUG_UNPRICED through `helius_rug_arbiter` instead of the −100% floor; point at the new instrument dir (V1 ledger untouched).
8. **`arena/arms/BUNDLE_MOMENTUM_V2_PREREGISTRATION.md`** (NEW) — pin the `.py` sha + every constant (K_BUYS=6, CLUMP_NS=1e9, CONC 95/100, frozen SIZE_SOL, LATENCY_S=0.9, HARD_STOP=0.12, trail tiers, 5% cap, DEAD_SILENCE=600, timeouts=60s, `censored_fraction` cap, sensitivity grid latency{0.45,0.9,1.8}×clump{0.6,1.0,1.5}) BEFORE the first resolve; genesis binds code+prereg+spec+git-activation sha.

### Phase 2 — Arm 3 (graduation) & Arm 1 (virality)
9. **`arena/graduation_runtime.py` / `arms/graduation.py`** — adopt `sizer.py` + `helius_rug_arbiter`; obtain the missing adversarial-attack pass before weighting.
10. **`arms/virality_arrival.py`** — fold in `helius_rug_arbiter` so its snapshot "-100% rugs" are re-classified (RUG_CONFIRMED vs censored measurement-failure); leave its optimistic-bound flag and one-sample-per-mint intact.

## Bottom line
- **REFUSE:** PREBOOST_ATTENTION_V1 (paid, reflexive, no-replay — a money pit; expected KILL).
- **BUILD:** BUNDLE_MOMENTUM_V2 (3 confirmed must-fixes) and the shared framework (scorer gate, Helius RUG arbiter, sizer).
- **BUILD-CONDITIONAL:** GRADUATION — strongest-fill arm, but its red-team review was not in this packet; get it before weighting.
- **KEEP:** VIRALITY_ARRIVAL_V2_2 as the honest $0 attention filter (KILL-only value).
- **Critical path:** `scorer.py` gate → `helius_rug_arbiter.py` → `sizer.py` → then Arm 2. If Arm 2 and Arm 3 both die on their reads, pivot to X2_FLOWSTREAK. No wallet, no orders, no spend at any step.