# AFTERSHOCK PAC V1 — Payable Absorption Compression

**Status:** frozen PAPER research hypothesis. No wallet, signer, transaction construction, submission,
real SOL, or live-trading path. Every execution result remains `SIMULATED_OBSERVED_PATH` and
`CALIBRATION_UNCALIBRATED` until the repository's execution gates are separately met.

**Pre-activation amendment, 2026-08-28.** No PAC activation, position, or outcome existed when this
amendment was made. It closes the runner-audit defects without changing the PAC signal or exit thresholds:

- entry and exit are durable two-stage chains: persist the sealed decision first, then allow a scenario
  attempt only against an observed boundary strictly after decision time plus explicit positive latency;
- the exit policy observes a curve-exact **net** full-position quote at the decision state. `HOLD` creates
  no sell attempt and no fee. A triggered exit persists a separate sell order before it can land;
- both sides use an a-priori `1,000` bps maximum adverse-output guard, measured from the decision-state
  exact quote. A slippage refusal is not retried implicitly and its observed attempt cost remains P&L;
- schema-2 state persists complete DecisionRecords and pending orders. Schema-2 ledger rows are
  self-hashed, idempotent, and committed with a state-first write-ahead journal so restart replay is
  exactly-once at every tested crash boundary;
- the entry denominator includes quote input, entry curve fee, recorded attempt cost, and ATA rent. Exit
  proceeds are gross curve output minus exit curve fee and recorded attempt cost. Because this runner has
  no separately evidenced ATA-close attempt, rent is conservatively charged and never invented as a
  refund. Failed attempts are separate portfolio-cost events;
- a persistent scan watermark is written before discovery. First start skips all backlog; after a crash
  the runner may miss a window but can never enter it retrospectively. The production command requires
  explicit positive `reaction_nanos` and has no latency default.

**Lineage boundary.** `AFTERSHOCK_V2_C` had the least-bad legacy headline, but its entries and exits used
historical states that were unavailable at action time. Its +2.3% pot-growth observation is burned and
invalid as return evidence. PAC V1 inherits only its mechanism hypothesis—external reserves must prove
they can pay sellers—and runs through the causal measurement chain as a new instrument. Old ledgers are
preserved and never merged.

**Post-activation measurement repair, 2026-08-28.** The first anchored session produced one entry
decision but no attempted fill, open position, ledger row, resolved outcome, or performance observation.
It exposed two runner liveness defects before any outcome existed: candidate enumeration used an older
cutoff than the internal decision clock, so a newly materialised pre-decision observation permanently
invalidated the saved prefix; and a right-censored attempt remained fillable forever. That session is
burned as a measurement diagnostic and cannot enter any denominator. The replacement session freezes:

- schema-3 state records the last measurement refusal independently of the performance ledger;
- the DecisionRecord's hashed prefix is the complete **processed** snapshot. A row appended after that
  prefix whose receive clock is at/before the decision is measured pipeline lag: it is excluded from
  detector replay and labelled, never added retrospectively to the signal. Its reserve effect remains
  inside the later boundary's `pre_state`, so fill pricing stays post-gap. Any mutation/omission inside
  the hashed prefix still invalidates and releases the decision;
- a right-censored entry is one closed no-trade diagnostic, not an indefinitely pending order;
- a right-censored trail/capacity exit releases that attempt and requires a fresh decision. At the
  12-minute hard horizon, a still-unobservable execution boundary is stressed to exact full loss;
- a priceable exit whose all-cost wallet proceeds are non-positive may hold for recovery, but once the
  frozen trail, capacity, or horizon rule requests exit it settles as exact full loss without inventing
  a successful sell or charging an unobserved attempt;
- candidate inventory is refreshed immediately before the internally clocked decision. Any remaining
  snapshot race still fails closed under the invalidation rule above.

The `800,000,000` ns runner setting remains `CALIBRATION_UNCALIBRATED`. Resolved rows from that setting
are feasibility scenarios only and **do not increment the 100-position promotion discovery counter**.
That counter starts only under a separately frozen engine backed by measured build/sign/send/land clocks
and failure observations. No threshold, detector formula, size, trail, coverage, or horizon changed.

**Post-outcome pipeline amendment, 2026-08-28.** Session 3 produced exactly two fully costed
`CALIBRATION_UNCALIBRATED` scenarios before this amendment (`+17.9620%` and `-19.9845%` all-cost R).
They remain preserved as plumbing evidence but are excluded from the fresh optimized-session denominator.
No detector, sizing, or exit threshold is fitted to those returns. The plumbing change is justified by
the production wall-time profile: 126 changed mints required 5.55 s, of which 4.54 s was repeated
full-tape decode, while the configured loop slept another 2 s after work.
The optimized runner freezes these measurement rules before its next signal:

- scan starts are scheduled on a fixed 250 ms deadline, including compute time. This changes only how
  quickly a receive-time signal is observed; modeled landing remains the explicit uncalibrated
  `800,000,000` ns and is not shortened;
- a service poll before modeled landing is `WAITING`, never a censored attempt. After landing, the
  decision waits at most `2,000,000,000` ns for a post-landing observed-state boundary; only then may
  the already-frozen right-censor terminal rule release or stress the order. This preserves the bounded
  wait implicit in the old two-second cadence without making a sub-landing fill;
- flat discovery first reads only the latest 180-second receive-time tail and runs the unchanged sealed
  PAC comparisons on exact reserve states. This is admission-only: every positive candidate is rebuilt
  from the complete mint tape and must pass the full hashes, provenance, ordering, detector, coverage,
  decision, and later-boundary path before it can become pending;
- a candidate-local decode refusal is reported and skipped for that mint. It can never authorize a
  trade or halt unrelated valid mints. Active-position corruption still fails closed;
- the append-only SOL/USD consumer searches backward to the latest record available at the decision
  clock, then performs the same raw-response hash and derived-field reconciliation. Future receipts are
  skipped rather than leaked and stale quotes still refuse;
- the anchored SessionProof is loaded once and reverified at most 5 seconds later. Every actual decision
  or attempt independently re-verifies it through the sealed execution engine;
- the fixed supervisor restarts an unexpectedly exited paper runner after 250 ms. State validation,
  session binding, the state-first watermark, and the exactly-once ledger journal run again on restart.

The PAC formula, `$10` probe, one-position limit, 12% trail, 6x capacity exit, 12-minute horizon,
slippage guard, fees, rent, full-loss rules, and promotion gates are unchanged. This amendment does not
create a wallet or make the 800 ms setting calibrated.

## Hypothesis and unique formula

Pump.fun losses in this repository have two dominant forms: no executable exit, or frequent churn whose
small gross movement does not clear curve and wallet costs. Counting buys does not solve either. PAC asks
a narrower question: **is the market becoming better, not merely willing once, at replacing external SOL
after an exit-sized withdrawal?**

For two sequential observed reserve withdrawal/recovery cycles, define:

```text
Wi    = external-SOL reserve immediately before withdrawal i
       minus external-SOL reserve immediately after withdrawal i
Di    = local receive-clock time from withdrawal i to the first full recovery
Bi    = external-SOL reserve immediately before withdrawal i
Ei    = external-SOL reserve at full recovery i

PAC = min(W2/W1, D1/D2, B2/B1, E2/E1)
```

PAC passes only when every component is at least one, evaluated by exact integer comparisons:

- `W2 >= W1`: the second stress is not easier;
- `D2 <= D1`: the second stress is paid back no slower;
- `B2 >= B1` and `E2 >= E1`: the reserve baseline and recovered capacity do not decay.

This is a **working hypothesis**, not a verified edge. It makes no wallet-independence or fresh-capital
claim because the current causal event schema cannot prove either.

## Frozen entry

The sealed detector at `scripts/trading_bot/aftershock/pac_detector.py` must return exactly
`(withdraw1, recover1, withdraw2, recover2)`. All evidence is strictly post-warm-up and the second
recovery is the newest observed event. Both cycles must:

- withdraw at least `50,000,000` lamports of external reserves;
- return to at least their own pre-withdrawal reserve;
- be non-overlapping and finish within one `180,000,000,000` ns pattern span;
- satisfy every PAC component above.

The fixed 0.05-SOL floor is a minimum observable stress, not a statement that it always equals $10.
After a point-in-time Decimal SOL/USD observation computes the exact `$10.00` quote input, the order path
must independently prove that exact size is no larger than **both** observed withdrawals. Otherwise it
refuses. No stale completed pattern, retrospective scan price, or post-signal event may enter.

Only newly recorded `public_rpc_processed` tape rows with an exact local integer receive clock, explicit
source, transaction signature, and reconciling per-mint reserve chain are eligible. PumpPortal and public
RPC are distinct scenario sources and may never be mixed or relabelled. The processed public-RPC stream
has no canonical instruction coordinate, so PAC remains receive-time scenario evidence.

## Frozen discovery sizing and portfolio boundary

- Paper bankroll starts at `$100.00`; discovery probe is exactly `$10.00` (10% initial exposure).
- One open PAC position at a time. No second tranche, martingale, averaging down, or $2 dust orders.
- Settled SOL P&L and USD equity are reported separately.
- The frozen adverse-output guard is 1,000 bps from each decision-state exact quote; it is a scenario
  bound, not empirical calibration and never permits a same-decision-state fill.
- No compounding or size increase is permitted from discovery results. A future scaling policy requires
  a new frozen instrument after PAC clears discovery and untouched confirmation data.

Larger size does not repair negative expectancy. The `$10` probe is economically meaningful but still
small enough that one unexitability cannot consume the whole `$100` research bankroll.

Point-in-time SOL/USD comes from the public Coinbase Exchange `SOL-USD` last-trade ticker. The raw JSON,
raw hash, provider trade time, request-start clock, and local response-receive clock are retained. Local
age over 5 seconds, provider last-trade age over 30 seconds at receipt, future skew over 5 seconds,
non-USD product/source, malformed Decimal price, or raw/derived mismatch refuses. Source documentation,
accessed 2026-08-28:
`https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker`.

## Frozen exit

The sealed pure policy at `scripts/trading_bot/aftershock/pac_policy.py` consumes only the curve-exact,
net quote for selling the **entire** token position:

- update the peak full-position exit quote causally;
- exit all at a 12% drawdown from that peak;
- request a causal full exit if external reserve coverage drops below 6x the original quote input;
- score an unavailable full-position quote/reserve as unexitable full loss—never invent an exit or mark;
- request a causal full exit at a 12-minute hard horizon.

There is no take-profit, partial exit, ratchet, or scale-out. The 12% trail is an explicitly inherited
lineage hypothesis, not a newly optimized value. It must be executed as a new causal sell decision after
positive latency, against the later boundary state; the pure policy alone is not a fill.

## Evidence and promotion gates

PAC cannot start a forward evidence book until its preregistration, canonical JSON, dependency seal,
activation session, warm-up root, and activation anchor are committed and byte-clean. The uncalibrated
latency model remains scenario-only; no scenario may be relabelled executable.

Warm-up scope is `feed_global`: its committed root proves the read-only feed ran after activation, while
each mint decision stream contains only observations strictly after that completed global warm-up. A
global warm-up is never copied in front of every mint as a false reserve-continuity prefix.

Minimum discovery adjudication is 100 resolved, fully costed positions and must show all of:

- positive log growth after curve fees, own impact, every observed attempt cost, and conservatively
  unreclaimed ATA rent unless a future separately frozen close-attempt chain measures reclamation;
- positive growth per UTC day and per observable creator cluster;
- positive after dropping the largest winner;
- unavailable/full-loss rate below 13% (the independent B20B held-out baseline, not an edge claim);
- then positive on a fresh, untouched, separately anchored confirmation slice.

Failure of any gate retires PAC without threshold editing. Passing licenses only the next paper/shadow
gate in `PLAN.md`; it does not authorize a wallet or real-money trading.
