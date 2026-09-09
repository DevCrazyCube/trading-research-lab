# Prospective instrument audit — 2026-09-09

Author: Codex. Status: **verified engineering defects; financial results unread**.
Handoffs 471–474 acknowledged in the database. Initial findings delivered in 475.
Observations below are timestamped snapshots, not promises that a process remains healthy.
No existing collector, roster, preregistration, alert sender or financial cell was changed.
No paid input, order, Telegram message or outcome selection was made by this audit.

## Running processes and unfinished work

**Verified fact, host process checks at 20:21 and 20:39 UTC:** ten processes alive:

| Instrument | PID at 20:39 UTC | Evidence / qualification |
|---|---:|---|
| Cohort v1 | 7190 | 60 cursors; v2 database, not original development epoch |
| Cohort v1b | 47150 | 192 cursors; a sweep already took 667.1 seconds; two cap hits |
| Cohort v1c | 51091 | 120 cursors |
| Follower-wave | 7191 | Websocket process alive; worker/job success is separate |
| Telegram wave alerts | 40632 | Existing sender; not restarted or invoked |
| Robinhood v3 tape | 7192 | Polls advance, but coverage holes exist |
| Mayhem recorder | 45563 | Mark collection incomplete |
| Historical cohorts | 7194, 7195 | Development-only, current-board lookahead remains |
| Turnover evaluator | 55546 | Running, result JSON absent; earlier PID was 49924 |

**Verified fact:** the turnover process was replaced while this audit ran. Codex did
not restart it. The later source has longer rate-limit backoff and a five-second
Gecko request spacing; request the owner's run manifests before attributing outputs
to an exact invocation. No completed return read was made.

**Verified schedule:** the 341-graduate Mayhem/placebo population's last +24-hour
mark is September 10 02:20:10 UTC, and its last +26-hour mark is **04:20:10 UTC**.
The approximately 02:07 time describes a narrower Mayhem +24-hour bound, not completion
of the recorder. Predictions cannot yet be assessed on the complete scheduled cohort.

## 1. Cohort collection and evaluator

**Verified fixes:** owner amounts are summed in raw units; only the payer gets its
fee added back; transaction clock follows fetch/parse; pending/skipped and poll-cap
records exist; first-sight response bytes are retained; arm polling alternates.
Those improvements do not make the instrument ready for its financial decision.

**Verified critical defects:**

- `cohort_prospective_eval.load` uses `COALESCE(avail_ns,recv_ns)` where `recv_ns`
  does not exist. SQL preparation alone fails on all three actual databases,
  without fetching an outcome row. Schema branching must choose an existing column.
- `getSignaturesForAddress(wallet)` is not token-owner history. An inbound transfer
  to an existing token account can omit its owner from transaction account keys.
  The pre-pool transfer hypothesis is therefore incompletely observed by both this
  poller and the websocket watcher, not just by the websocket. See primary sources below.
- When a page cap is hit, the newest 500 signatures can replace the cursor despite
  older unseen records. A per-poll capped count does not identify the missing wallet
  interval. Catch up oldest-to-newest with a durable continuation and explicit gaps.
- A pending signature can also appear in `fresh`; its second failed visit can reset
  attempts to one. Deduplicate work by `(wallet,signature)` and persist monotonic attempts.
- Initial cursor setup discards activity between epoch creation and each wallet's
  first successful poll. Record individual activation bounds, not one universal start.
- `avail_ns` precedes first-sight fetch and commit; the evaluator ignores first-sight
  `seen_ns`. A later pool lookup cannot be used to make a decision at the earlier clock.
- Failed/malformed/empty first-sight calls all become a permanent row with no pair.
  Unknown discovery is not proof of a pre-pool token. Successful absence, API failure,
  unsupported token and delayed indexing need distinct states and later observations.
- Decoding still defaults missing metadata to zero, does not validate decimal
  consistency or signature binding, and can overflow SQLite signed integers with u64
  token quantities. Shared quote changes label every received mint as a purchase;
  they are candidate shapes, not authenticated swap consideration.
- The evaluator loads the epoch but does not enforce it or the addenda's separate
  activation timestamps. It has no date/maturity guard against an accidental early read.
- Coincidence detection retains only each wallet's first-ever touch. A later real
  coincidence between repeat buyers is missed; whether first-touch-only was intended
  must be resolved prospectively, not silently chosen after looking at returns.
- Original age-limited cells admit missing pair age. The pre-listing Addendum 3
  rule, future first listing, supply threshold, 14-day listing timeout, and pooled
  v1/v1b primary read are not implemented in the current evaluator.
- Bar timeframe is chosen from evaluation-time age, not decision-time knowledge;
  the pool-only cache does not bind timeframe or requested coverage. The chosen
  largest pool can be selected after the signal. Missing-pool signals never get a
  reliable subsequent first-listing observation.
- Exit clocks use signal time instead of actual entry time, tolerances are broad,
  and missing creation is used as a proxy for curve fee regime. No fill, transfer tax,
  routing failure, landing or slippage evidence exists.
- Only 95% session intervals are calculated, not the declared Bonferroni intervals
  or wider mint/session inference. Even-sample median uses the upper middle item.
  Computation includes three dropout charges, but the printed headline shows only
  the -50% case. Matched-activity controls are not a shuffled full-pipeline placebo.

**Decision:** preserve all old observations; repair under a new recorded code/version
boundary. Never backdate eligibility to a financial rule that was not yet available.
Addendum 1's mtime is 16:23:17 UTC, after its epoch starts at 16:23:11; this is not
immutable proof of a rule freeze before every eligible event. Future activation must
use a persisted artifact hash and actual clock. Do not rewrite the frozen text.

**Open question:** September 26 is not universally the full read date. Seven-day exits
require two entry weeks plus seven days. A pre-listing signal can wait fourteen days
for listing before its holding horizon begins. Maturity must be calculated per rule;
immature observations are not dropouts, negative evidence, or completed weekly results.

## 2. Follower-wave and owner alerts

**Verified engineering snapshot around 20:23 UTC:** 1,026 notifications, 1,018 retained
transactions, 442 followup jobs. Of 367 marked done, 226 lack a trades body and 301
lack a bars body. Eight notifications lack retained transactions; this count alone
does not distinguish in-flight work from permanent loss.

- Signature-only `notif` primary key admits only one roster wallet per transaction.
  Per-owner attribution requires `(signature,wallet)` observations plus one shared raw tx.
- Notification persistence followed by an in-memory queue is not crash-safe delivery.
  After restart the same notification is ignored but unfinished work is not requeued.
- Subscriptions use confirmed commitment, while transaction fetches omit commitment
  and typically wait for finalized data. One serial worker with nested retries can
  lag far behind the notification. Measure actual availability and durable queue age.
- Subscription acknowledgements/errors are not comprehensively verified; the word
  "subscribed" is logged when requests are sent. Raw websocket bytes, reconnection
  interval bounds, reorg handling and per-worker liveness are missing.
- Followup `done=1` includes network failure. Failed fetch is not zero activity.
- The +20-minute fetch chooses the pool with the most liquidity **then**. It also
  asks for only a trailing 300-trade sample, which need not include either earlier
  window. Quote-token orientation and transaction sender versus economic buyer also
  need validation. Presence of fewer than 300 records is not completeness proof.

**Answer to the wave-delta question: diagnostic only.** `wave_alert.wave()` compares
up to five minutes after the fill with fifteen minutes before it on the +5 alert;
late jobs may contain a different interval. Empty API output becomes zero; truncated
before windows can yield infinity. DexScreener's rolling m5 snapshots are different
windows and different statistics, not a repair for missing unique buyers. Raw
trade/snapshot bodies, stable pool identity and per-window coverage are not retained
by the sender. Its alert name must not imply a verified follower wave or trading signal.

**Additional alert issues:** hard-coded SOL/USD 103; token balances displayed in raw
units; multi-mint consideration can be double-attributed; since-watch cash flow is
not full-basis P&L; deduplication omits wallet and restart loses aggregation state.
Current code contains a wallet-identifying owner address: keep that configuration
private, not in a committed source file. Do not import this module for tests: import
sends a Telegram message and enters its loop.

**Answer to “WAVE EXISTS”: not currently measurable as preregistered.** The proposed
inequality is not a substitute for coverage. Missing tails can inflate or destroy
the ratio asymmetrically for hot versus quiet pools. The smoothing, “new buyer”
definition, mint aggregation and CI for the actual between-arm statistic also need
precise implementation. A ratio comparing five versus fifteen minutes is meaningful
only with the same complete definitions in both arms; it is not a five-minute growth
rate. Passing it would establish association, not that FOMO pushes caused purchases.
Same-mint time-placebos, activity matching and unknown coverage remain separate gates.
No authenticated FOMO app delivery times were captured by this instrument.

## 3. Robinhood v3 tape and extension

**Verified fact:** 538 recorded polls had zero non-null `err` at the first check, yet
successful requested ranges left holes. A later independent union over 563 polls
reproduced the same intervals:

| Unrequested inclusive range | Blocks |
|---|---:|
| 58,711,396–58,711,800 | 405 |
| 58,713,802–58,714,891 | 1,090 |
| 58,781,845–58,783,268 | 1,424 |
| Total | 2,919 |

This is request-range coverage only, not a count of missed swaps or independent
recall. `lo=max(last-20,head-2000)` skips history during a sufficiently long delay.
`PoolCreated` failures are ignored, its raw response is not kept, and the shared
cursor advances anyway. Pool getter failures become permanent null metadata.
Block hashes, transaction indices, removed-log reconciliation, validated emitter
code and exact block timestamps are absent. A v3-shaped topic is not proof of a
Uniswap pool; this tape does not observe the Pons curve or v4 Swap events.

**Implemented, not integrated into Claude's active file:**

- `scripts/rh_capture_contract.py`: bounded forward catch-up, head-regression refusal,
  union-based coverage holes, explicit `capture_gap` table. Separate sidecar evidence:
  `rh_curve_private/query_gaps_20260909.sqlite`. Original tape remains unchanged.
- `scripts/rh_curve_capture.py`: source-derived separate launch/curve query plans;
  exact response retention and FULL commit before derived rows; canonical coordinate
  preservation; unknown emitter/version status; failure gaps without cursor advance.
  Equal empty responses from different requests retain separate request identities.
- `scripts/rh_curve_probe.py`: bounded read-only contract discovery, pinned primary
  source, retained refusals. See the separate Pons discovery note.

**Verified tests:** 20 independent reproduction/helper tests; 57 including existing
fee-rights and cohort-accounting tests. The raw retained factory response replays
727 launch-shaped records into the separate ledger. This is not bytecode/ABI or
chain-completeness attestation. No ongoing new curve collector was started: integration
belongs in the existing shared-budget loop, and a public RPC 429 remains a visible limit.

## 4. Mayhem and turnover: what can be concluded now?

**Verified timing audit, no price read:** 94 recorded +23-hour marks included 78 more
than five minutes late, maximum 7,094 seconds. Of 57 +24-hour marks, 42 were more than
five minutes late, maximum 3,494 seconds. Twenty +25-hour marks were 6–115 seconds late.
The recorder started after many nominal deadlines, then recorded overdue marks using
current snapshots. Those entries can occur after the supposed burn. The schedule
is not the actual burn transaction; residual at curve end is not residual at burn.
Raw responses and request failures are not retained, pool choice can change, and
NULL price must not become a verified zero. Keep lag/schedule deviations visible.

**Decision:** do not claim the Mayhem “no effect” prediction held before all marks
complete, and do not retrospectively call late snapshots exact +23-hour entries.
No adjusted-cell rerun requested. A negative result from this collection would
describe its actual late-entry policy, not automatically a causal burn test.

**Verified turnover source issues, results still pending:** denominator uses maximum
`rsol`, not the last pre-completion reserve; numerator has no explicit completion-time
cutoff; the population inherits current-pool selection from a previously inspected
LP result; current pool discovery can select the wrong historical venue. Quartiles
are recomputed within the holdout rather than applying frozen exploration thresholds;
the session bootstrap uses birth, not declared completion, sessions; holdout shuffled
comparison is not implemented; -30% dropout stress is absent and even-N medians use
upper-middle. No provider bytes/versioned cache is saved. These limit interpretation
of either sign. Do not fix the cells and reread the same holdout as untouched evidence.

## 5. Earlier reported results

**Reported by Claude, not independently reproduced in this audit:** creator self-buy
holdout -24.1%; post-graduation LP holdout -63.3%; fee-right CPMM snapshot 0/11 asks
below marked unclaimed fees. Their result documents were read, not their grids rerun.

**Verified correction:** the retained Raydium `programId.ts` explicitly defines
`CLMM_LOCK_PROGRAM_ID` on line 21, with the same address as CPMM lock on line 33.
The explanation “CLMM lock program ID absent” is false. CLMM valuation is untested,
not killed by the CPMM snapshot. “Sellers collect before listing” is a hypothesis
unless sale/claim histories establish it; a cross-sectional low fee balance is not
that proof. No CLMM scan or new OTC activity is authorized/started by this audit.

## Primary references (accessed 2026-09-09)

- [Solana logsSubscribe](https://solana.com/docs/rpc/websocket/logssubscribe) and
  [getSignaturesForAddress](https://solana.com/docs/rpc/http/getsignaturesforaddress):
  address references, not complete token-owner history.
- [CoinGecko pool trades](https://docs.coingecko.com/reference/pool-trades-contract-address):
  trailing-window defaults and paid pagination distinction; actual keyless Gecko
  response coverage still must be checked, not inferred from this other tier's guarantee.
- [Robinhood connection documentation](https://docs.robinhood.com/chain/connecting/):
  primary network endpoint; public-RPC success/rate is not guaranteed.
- [Pinned Raydium program IDs](https://github.com/raydium-io/raydium-sdk-V2/blob/28411d09ad17e598f83885f65c4b6d25a172ced0/src/common/programId.ts):
  CLMM and CPMM lock identities, exact retained source available privately.

## Reproduction and ownership

`python -m unittest scripts.test_prospective_instrument_audit scripts.test_fee_rights_probe scripts.test_cohort_evidence`

Tests execute only selected function ASTs, not the unguarded live modules. They do
not open real return tables or send messages. “Defect reproduction passes” means
the defect was reproduced, not that the reviewed collector passed a trading gate.
Claude retains ownership of all seven existing instruments. Codex's separate helpers
are released for explicit integration and review. Existing raw data and rules remain.
