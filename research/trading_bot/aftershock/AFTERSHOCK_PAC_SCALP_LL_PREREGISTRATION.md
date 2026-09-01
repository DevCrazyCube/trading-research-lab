# AFTERSHOCK_PAC_SCALP_LL — preregistration

Status: `PRESEAL_DEFAULT_OFF`, paper-only. No live order path is authorized.

## Verified starting facts

- The burned PAC scalp book resolved 322 paper scenarios at mean all-cost return `-0.1183899491R`;
  its `-6%` all-cost stop fired on 282 rows and was inside the measured toll/noise floor.
- Its public-route hard-stop decision-to-resolution p90 was `6.461s`. Schema-1 marks cannot measure
  whether a proactive stop landed before a rug, so no rug-catch claim is inherited.
- PAC entry features did not separate later winners and losers. This experiment does not create another
  entry-feature arm and inherits no performance rows.

## Working hypothesis

A paid/staked submit route can reduce build/sign/send/processed-observation latency enough that one
precommitted `-12%` all-cost full-position stop preserves the right tail while catching at least 70% of
otherwise unexitable rugs. This is a hypothesis, not a profit claim.

## Stage A — matched latency calibration

- Exactly the first 100 **deterministic attempted pairs** are selected. Each pair sends one public-control and one
  low-latency-intervention transaction in SHA-256-randomized order.
- Both arms use byte-equivalent transaction shape: ComputeBudget limit/price, fixed 5,000-lamport tip,
  and a campaign memo. The parser proves there are no Pump accounts or trading instructions.
- A third endpoint observes first successful processed status. Effective latency is build-start through
  that observation minus the explicit `getFeeForMessage` measurement interval. Raw signatures and wires
  remain local; a commit-safe summary contains hashes and aggregates only.
- A send/landing failure remains in its assigned arm at the frozen 30-second deadline; the sender never
  keeps sampling until it accumulates a flattering success-only set. Every attempted signature must
  later be independently re-read (or explicitly absent) at finalized commitment. Local processed
  observations alone remain `UNATTESTED_LOCAL` and cannot activate a runner.
- Calibration can proceed only in this order: prereg+frozen+dependency seal committed; campaign committed
  in a strict descendant; explicit `--broadcast`; campaign-wide cap `3,000,000` lamports; exactly one
  manifest-owned journal under an exclusive writer lock; raw collection; finalized attestation;
  evidence commit; then a separate set-once activation commit.
- Calibration eligibility requires intervention p90 `<=1,000,000,000ns` and no more than half the paired
  control p90. Failure to meet either threshold kills the low-latency convexity premise without strategy
  execution.

## Stage B — matched paper execution

- The entry detector is unchanged between route arms. A decision is filled only on a fresh provider-bound
  state at or after that arm's attested p90 landing target, with own curve impact and all costs.
- Before activation, one commit-safe runtime profile binds each arm's submit/observe identity and exact
  entry, exit, and ATA-close AttemptCost. The profile is committed after the campaign and is reverified
  with the calibration summary and finalized attestation; caller-supplied provider/cost drift refuses.
- Exit policy is fixed before data: full-position exit at all-cost equity `<=88/100` of entry, an absolute
  horizon, or the existing upside trail. The stop is a trigger, never a guaranteed fill price.
- Curve failure/completion routes through the typed PumpSwap state machine. A full loss is legal only at
  the bounded cross-venue deadline. Conditional ATA rent is supplementary and cannot improve primary
  paper P&L until an explicit full sale and close are both evidenced.
- The unified schema-2 ledger records every mark, attempt cost, route identity, decision, landing target,
  later snapshot, venue transition, and terminal result. No historical tick can become a fill.

Primary discovery gate after 100 fully costed low-latency resolutions:

1. mean net return `>0` and normalized $100/$10 capital index `>100`;
2. mean remains `>0` after removing the single best result;
3. proactive rug-catch fraction `>=70%`, where a catch requires a full sell to land after a stop decision
   and before the first causally observed unpriceable terminal state; and
4. no integrity, seal, route-drift, stale-state, or reconciliation failure.

Winner early-dip rate and public-control performance are diagnostic and cannot rewrite the stop. A later
untouched confirmation slice is required before any real-money promotion decision.

## Portfolio policy (paper evaluation only)

- Start with `$100.00`; the initial position is `$10.00`.
- Each next position is 10% of realized trading equity, clamped to `$10..$50`, no larger than one sixth
  of current executable exit capacity. Maximum concurrent gross exposure is 40%.
- On every positive realized result, 25% of profit moves to a non-trading reserve and 75% compounds.
  Unrealized gains never resize an order. A 20% UTC-day realized loss halts new entries until next day;
  a day reset never restores lost capital.
- This portfolio path is reported beside fixed-$10 expectancy. It cannot turn negative per-trade
  expectancy into an edge and cannot authorize live funds.

## Kill / boundary

If low latency fails its calibration thresholds or the 100-resolution discovery gate, retire this
memecoin-scalping family. Do not create another PAC threshold variant from its outcomes. The honest next
domain must have structurally slower price discovery or an execution edge that can be independently
observed. All work remains paper-only; infrastructure/calibration spend is not trading authorization.
