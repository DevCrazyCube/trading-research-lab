# ARM 2 — BUNDLE_MOMENTUM_V2 — Pre-Registration

Status: PRE-ACTIVATION paper measurement. No wallet, signer, transaction sender or live-money authority.
V2 is the causal MONEY-BOOK evolution of BUNDLE_MOMENTUM_V1: the SAME frozen at-s6 bundle signal (imported
verbatim from `bundle_momentum.first_six_signal`, no entry drift), wired into the Phase-0 honesty framework
V1 was built before. It is a NEW instrument with its own activation and ledger
(`research/data/arena/BUNDLE_MOMENTUM_V2/`); the V1 instrument dir and ledger are untouched. The burned
`+1.167R` window-1 DEV number carries zero prior weight and used non-executable marginal fills. The
PumpPortal `subscribeTokenTrade` lane is paid data and must fail closed without a dedicated
`PUMPPORTAL_DATA_API_KEY`; a Lightning/trading credential is never accepted as a substitute.

Runtime: `scripts/trading_bot/memebot/arena/bundle_v2_runtime.py` (standalone; NOT wired into the snapshot
`runtime.py` loop, so activating V2 does not drift the V1/graduation/virality closures). Activation is
written set-once and git-anchored via `python -m scripts.trading_bot.memebot.arena.bundle_v2_runtime
--activate` and committed before the first resolve.

## Frozen cohort and entry (identical to V1)

- Universe is only PumpPortal mints observed by this host at CREATE and then subscribed for trades.
  Mid-stream first sights are excluded and counted. Local receive nanoseconds are the ordering clock;
  chain slots are diagnostic because the public websocket may omit them.
- The first six buy events must span no more than 1.0 second. At the sixth buy, wallet net token holdings
  over every observed buy/sell up to that coordinate are computed. Entry requires at least two positive
  holders and largest-positive/total-positive < 95%. This is an at-s6 concentration proxy, not the
  validated t0+60 B20B gate (which remains an ex-post AUDIT only, never back-applied at s6).
- One primary sample per mint, no re-entry. Decision is the sixth-buy receive coordinate.

## V2 must-fix wiring (the only changes vs V1)

1. **COVERAGE VOID gate (must-fix #1).** Before any pending entry, `helius_coverage.coverage_ok` runs
   inside the entry decision on the create timestamp and the captured first-K buys. The cheap $0 gate
   requires the buffer's first captured buy within `MAX_CREATE_GAP_S = 3.0s` of the create; a larger gap
   means a subscription race dropped the true opening buys, so the first-six clump/concentration are a
   measurement artifact. A mismatch (or too-few captured buys) is a `COVERAGE_VOID` STRATEGY VOID — never
   a trade. `SETTLEMENT_DELAY_S = 8.0s` governs the rigorous on-chain first-K cross-check when a bonding
   curve address and Helius are available.
2. **The shared $10 money-book clip.** The SOL size is not V1's constant 0.5. It is `sizer.clip_sol` of
   the fixed `CLIP_USD = $10` clip, frozen at the fill boundary from the causal `solusd_recorder`
   observation (`<= 5s` staleness). No fresh causal SOL/USD at the fill => `SOL_USD_UNAVAILABLE` strategy
   void (never size blind). The frozen `size_sol` is threaded through every leg of `causal_fill_cp` and the
   PumpSwap migration exit, and recorded on the open and resolved rows.
3. **The GLOBAL primary slot.** Opening a position atomically claims one of the `MAX_CONCURRENT_PRIMARY = 2`
   PRIMARY slots across ALL arms via `sizer.try_acquire_primary` over one flock'd shared
   `research/data/arena/portfolio.json`. The slot is released at the ledger drain of the resolved (or
   measurement-void) pop. `reconcile_slots` at cycle start releases any of THIS arm's own slots whose mint
   is not in its live open set, healing the acquire-side crash leak. When both slots are held the candidate
   is a `PORTFOLIO_SLOTS_FULL` strategy void — never a blind over-limit trade. The comparator control never
   touches the slot.
4. **The RUG arbiter on BOTH RUG_UNPRICED sites.** Every would-be −100% (a migrated pool that goes
   unpriceable past its exit boundary, and a pending exit whose fill boundary never lands within
   `EXIT_BOUNDARY_TIMEOUT_S = 60s` after a `DEAD_SILENCE_S = 600s` silence) routes through
   `helius_rug_arbiter.classify_unpriced`. Only a positively-dead coin (`RUG_CONFIRMED`: no recent on-chain
   trades AND liquidity drained to dust) books a real −100% PRIMARY loss. `MEASUREMENT_VOID` /
   `INDETERMINATE_VOID` (and any arbiter error) become a single `MEASUREMENT_FAILURE` void of the whole
   open — right-censored, excluded from primary N, never fabricated as a loss. The comparator control
   cannot decide the open's fate: if it alone goes unpriceable after a clean primary exit, its −100% is
   booked only on `RUG_CONFIRMED`, otherwise its control return is censored (null) so the real primary
   sample still finishes.
5. **Boot-closure guard (handoff 460).** The arm's closure sha is captured at import; a cycle refuses
   "BOOT CLOSURE DRIFT" if the on-disk closure changed since boot, so a stale process never runs old code
   under a freshly-written activation. The closure hash covers the arm, the V2 runtime, the V1 predicate it
   imports, every framework module it wires (`sizer`, `helius_coverage`, `helius_rug_arbiter`, `cohorts`),
   the shared honesty spine, and the aftershock quote/price/SOL-USD deps.

## Causal paper execution (unchanged spine)

- Entry target is decision+0.9s; the fill lands only on the first same-mint reserve observation at/after
  the target. No boundary within `ENTRY_BOUNDARY_TIMEOUT_S = 60s` is `VOID_NO_ENTRY_BOUNDARY` and never
  enters performance N.
- Both curve legs use constant-product virtual reserves, 1.5% fee each leg, 2,250,000 lamports fixed
  round-trip cost, and a real-SOL-withdrawable exit cap (executable fills — walk the curve for the real
  size + toll + latency, never a marginal mark). Every exit trigger creates a new target at trigger+0.9s
  and fills only on a later boundary.
- Primary exit is −12% all-cost, widening 18/25/35% trail, 12-hour horizon. A flat-10% trail comparator
  runs on the same causal entry and tape but cannot choose the primary outcome. Ten minutes without a
  same-mint observation opens a dead-coin exit; absence of a later fill boundary routes through the arbiter
  (site #2 above), never an automatic −100%.
- F1: every opened position resolves — as a real primary outcome, a `RUG_CONFIRMED` −100%, or a
  right-censored `MEASUREMENT_FAILURE` void. WAL replay is idempotent; the tape cursor/head continuity and
  the ledger hash chain are verified every cycle.

## Cohorts and validity

Terminal rows split via `cohorts.split_cohorts`: PRIMARY (incl. `RUG_CONFIRMED` −100%), CONTROL (the
flat-10 comparator column travels with its primary; no separate control cohort), MEASUREMENT_FAILURE
(right-censored), STRATEGY_VOID (`COVERAGE_VOID`, `VOID_NO_ENTRY_BOUNDARY`, `PORTFOLIO_SLOTS_FULL`,
`SOL_USD_UNAVAILABLE`). `censored_fraction = MEASUREMENT_FAILURE / (PRIMARY + MEASUREMENT_FAILURE)` is a
frozen validity gate at `<= CENSORED_FRACTION_LIMIT = 0.35`; above it the read is INVALID and the censored
cohort's would-be-total-loss bound is reported as a sensitivity, never silently dropped.

## Decision

Primary N=120 distinct resolved mints; one early futility KILL is allowed at N>=40 when CI95-hi<0. PASS
requires CI95-lo>0 AND median>0 AND no single-winner dominance AND drawdown <= 40% (the shared
`scorer.decide` rule, via `runtime.report_arm`), plus survival of the pre-registered latency
{0.45,0.9,1.8}s x clump {0.6,1.0,1.5}s replay grid. A CI crossing zero extends once to N=240, then KILL.
Any broken tape/ledger chain, duplicate mint, unresolved lifecycle, stale/replayed coordinate, or a
censored fraction over the limit makes the read INVALID. A KILL is decisive; a PASS earns only a stricter
co-located landed-transaction V3, never real-money authorization. No wallet, no orders, no spend.
