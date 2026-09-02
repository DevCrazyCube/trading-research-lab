# ARM — MIGRATION_ACCEPTANCE_V1 — Pre-Registration

Status: PRE-ACTIVATION paper measurement. No wallet, signer, transaction sender, or live-money authority.
A NEW instrument with its own ledger dir `research/data/arena/MIGRATION_ACCEPTANCE_V1/`. It models the
`MEMEBOT_GRAD_V1` PumpSwap-exact-CP runtime but adds an executable EXIT-CAPACITY STRESS TEST as a hard
entry precondition and routes every real total-loss through the Helius arbiter.

## Thesis
A pump.fun graduation is only tradeable if the migrated PumpSwap pool can actually ABSORB our exit at
position size. Most −100% memecoin outcomes are unexitable dumps, not directional losses. This arm enters
ONLY after a CONFIRMED migration whose live pool passes a size-aware stress test, so a failed stress test is
a screened-out candidate (VOID), never a trade and never a loss.

## Frozen cohort and entry
- Universe: CREATE-confirmed pump.fun mints observed by this host, then a `migrate`/`migration` tape event.
  Pre-migration trades are bucketed; at migration the mint is labelled `PROXY_PASS` if the V1 first-six
  bundle signal fired on the bucket, else `CONTROL_PROXY_FAIL`. Controls are the null baseline: measured and
  reported separately, NEVER in primary N (`include_resolution` keeps only `PROXY_PASS`) and they NEVER take
  a global slot.
- Enter ONLY after the migration is CONFIRMED on-chain (`getTransaction` slot) and the live PumpSwap pool is
  observable at `migration_slot + LATENCY_SLOTS`. A late fill beyond `MAX_ENTRY_LAG_S` is `ENTRY_LAG_EXCEEDED`
  (lookahead-adjacent backlog casualty), VOIDed before any economic read. An unconfirmed migration or
  unobservable pool within its timeout is `UNCONFIRMED_MIGRATION` / `UNCONFIRMED_LIVE_POOL` VOID.

## Executable exit-capacity stress test (BINDING precondition)
Before any entry, on the live confirmed-pool reserves, `stress_test_exit_capacity` runs a PURE executable
simulation (reserve deltas are modelled with the audited exact-CP `sell_quote`, never sent) that must pass
ALL of:
1. **Capacity gate:** the clip must be ≤ 5% of the pool's exit capacity (`sizer.exit_capacity_ok`, capacity =
   the quote/WSOL reserve valued at the causal SOL/USD mark) — never trade blind/thin liquidity. Failure here
   is an `EXIT_CAPACITY_VOID`.
2. **`STRESS_SELLS = 2` independent position-size sells absorbed:** each exact-CP sell of the full position is
   priced against the reserves the PRIOR sell left (modelling our own exit plus concurrent dumps depressing
   the pool); each must net ≥ `(1 − MAX_STRESS_SLIPPAGE)` of the SOL deployed.
3. **Recovery into the depressed pool:** after that depression, the FULL $10 position must STILL sell absorbed
   at the same slippage floor.

A failure at (2)/(3) is a `STRESS_TEST_FAILED`. Every stress failure is a STRATEGY VOID — never an entry,
never a loss. (The `+ LATENCY_SLOTS` observation delay is already applied when the entry pool is captured, so
the recovery leg is modelled on the depressed reserves rather than a second network read.)

## Causal paper execution
- Clip = fixed $10, sized in SOL via `solusd_recorder.latest_observation` + `q_lamports_for_usd` at the
  entry observation. Entry buy priced exact-integer on the confirmed pool (`buy_quote`, fee-on-input). Fixed
  entry/exit route + ATA rent/close lamport costs are charged.
- **Global slot for PRIMARY only:** a `PROXY_PASS` entry claims one of the ≤ 2 global PRIMARY slots; if both
  are taken it is a `PRIMARY_SLOT_FULL` STRATEGY VOID. `CONTROL_PROXY_FAIL` entries never touch the slot.
  The slot is released when a PRIMARY position pops (resolved or measurement void). `reconcile_slots` at each
  cycle start self-heals a crash-orphaned PRIMARY slot.
- Marks re-observe the pool each cycle; primary exit is −12% all-cost, widening trail, 90-minute horizon.
- **Real total-loss routing:** an `UNAVAILABLE_FULL_LOSS` (pool gone unobservable past the poll budget while
  an exit is pending) is routed through `helius_rug_arbiter.classify_unpriced(mint, pool)`. Only
  `RUG_CONFIRMED` books a real −100%; otherwise it is a `MEASUREMENT_FAILURE` void (right-censored, excluded
  from primary N). F1 holds: every open resolves as either a priced terminal, a confirmed −100%, or a
  right-censored measurement void — never silently dropped.

## Decision
Primary N = 100 distinct resolved `PROXY_PASS` mints. Predeclared N ≥ 30 one-sided sign tripwire KILLs a
median < 0. At N = 100 a 27-test multiplicity-adjusted cluster-bootstrap CI decides: CI-hi < 0 → KILL,
CI-lo > 0 → PASS_TO_CONFIRMATION (paper only), else KILL. `censored_fraction` > 35% invalidates the read. Any
broken chain, duplicate mint, unresolved lifecycle, boot-closure drift, or stale coordinate is invalid. A
PASS earns only a stricter landed-transaction confirmation, never real-money authorization.
