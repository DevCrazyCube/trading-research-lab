# Creation-stream measurement contract and owner corrections

Author: Codex. Date: 2026-09-08 UTC. Status: **decision**, recording only / NO_TRADE.

This is a new instrument, not an amendment of
`NARRATIVE_FORMATION_PREREGISTRATION.md` (SHA-256
`1b25538f988a561dd9a8234cd9b1397b1287a1ece4adfbadeaa75e2f7aaf5141`).
Its ranked, market-cap-filtered collector cannot test launch-rate formation at birth.
No outcome from that experiment was re-evaluated. The birth-origin development
specification and result hashes are also retained unchanged for reproducibility.
Their earlier pair-check requirement/metadata is explicitly superseded below.

## Owner corrections, not independently audited trade evidence

**Decision:** exclude the ANON/BRO anecdote from every validation set, test gate,
threshold choice, and sizing conclusion. The owner states neither trade has a
repository ledger, fills, or supporting bars. N=2, approximate times, unaudited.

- ANON: `0x293efF1b996c56f6E0F6AFDc9E955301eea86DC7`, owner-reported
  Robinhood/Uniswap/USDG, 2026-09-05 around 16:00Z ±10 minutes.
- BRO: `0x292655A45D04CA013c637694447Ec94Ca4bE7777`, owner-reported
  BSC/Pancakeswap/QQQB, 2026-09-05 around 19:20Z ±10 minutes.

The same reported 0.773 drawdown feature cannot distinguish these two cases.
It does not show that all entry information was identical, especially across
different chains/quotes. The +354% is reported realized timing, not terminal return.
No trim/size conclusion is inferred from the separate eight-trade story. Any future
sizing experiment must fix sizes before entry and preregister its fresh cohort.
The owner's reported DexScreener verification is not represented as our own call.

**Decision:** drop the pre-graduation-buyer → post-graduation-LP-withdrawal project
from this work list. Preserve the descriptive label **single-minute drawdown ≥90%**,
with mechanism unknown. The supplied 65.1% is an owner-reported historical statistic,
not newly recomputed here. A discontinuous price jump cannot be assigned a fill at
the crossed stop price. Neither a candle nor provider failure identifies LP removal.

## Recording instrument

`scripts/birth_stream.py` subscribes directly to finalized Pump program logs on a
public Solana endpoint. It retains every received raw data frame before decoding,
with per-frame wall and monotonic receipt clocks, SHA-256 chain, and SQLite FULL
synchronous commits. All creation regimes and failed-transaction evidence remain
in the raw and derived observation tables. There is no price, market-cap, volume,
listing or future-bar-count admission rule. Creator, user and URI are distinct fields.

Unknown Pump discriminators, malformed payloads, broken program invocation stacks,
clock jumps, disconnects and capacity stops are recorded visibly. A failed transaction
is not a successful birth. The storage limit is checked before the next receive;
it can overshoot by at most one maximum frame plus SQLite overhead. No old files are
removed. Sixteen GiB free-space reserve; fixed duration; no silent reconnect/backfill.

**Open question:** single-source logs may be incomplete, delayed, or truncated.
Finalized observation latency is real, not a claim to detect launches before their
first buy. Same-transaction creation/buy can precede receipt. The finalized slot and
log index are not a complete canonical coordinate. Missing transaction/outer/inner
coordinates are NULL, never replaced with arrival or log order.

`scripts/birth_stream_verify.py` replays a closed session from its compressed raw
frames and compares every derived creation field and receipt byte-for-byte. Optional
bounded public-RPC reconciliation retains raw `getTransaction`/`getBlock` responses
before parsing, matches wire signature/slot/success, block transaction order, and exact
program-bound CPI event payload. Successful rows use the existing B7d `create_event`
field schema. Later HTTP receipt never replaces the original observation clock.
Matching observed transactions is **not** proof of missed-event recall, independent
providers, or an attested program deployment boundary. No live detector consumes these
rows yet; they remain recording/engineering evidence.

## Required gates before any money experiment

**Decision:** the original seven-point harness remains mandatory, expanded by the
owner's session-dependence correction. This document does not choose returns from
already inspected development data or activate a strategy.

1. Decision inputs must have actually arrived before the decision. Preserve on-chain
   coordinates separately from availability clocks. Historical diagnostics enter at
   the next REAL bar's open, never the signal bar's open; execution simulation also
   needs feasible route/latency evidence. No retrospective idealized fill.
2. One position per mint, no overlap/re-entry; fixed notional chosen before entry.
3. Mint-equal primary summaries and mint-equal contemporaneous controls. The supplied
   -14% to -23% random-bar range is context, not a matched control for a different cohort.
4. At EVERY horizon report eligible signals, attempted entries, entry-resolution rate,
   entered positions, exit-resolution rate, and all three -30/-50/-100% missing-exit
   stresses. Preserve unresolved observations in denominators. Never invent entries
   for unavailable routes or quietly exclude failed attempts; report their counts.
   Dropout scenarios are sensitivities, not measured fills or assertions of death.
5. Never require minimum bar count, trade count or continued listing. Missingness
   cannot become a positive admission feature. No survivor-selected price source/pool.
6. Report all-cost simple-return mean AND median, fixed-notional PnL and week/session
   results. A large positive mean with a negative median fails the owner's requirement.
   Log returns are not fixed-notional account PnL. The 1.14% historical direct toll is
   a required comparison scenario, not a substitute for contemporaneous route costs,
   spread/impact, failed-transaction costs and measured execution latency.
7. Preregister and run the WHOLE selection/entry/exit/cost pipeline on shuffled data,
   preserving the relevant dependencies. Retain every seed and every attempted rule;
   if noise produces as many profitable survivors, reject. Text-count permutations
   alone do not satisfy this requirement. Correct selection multiplicity.

**Decision:** freeze session boundaries BEFORE outcomes. Report uncertainty from
both mint-cluster and session-cluster resampling (and dependence-aware joint analysis),
not a trade-level iid bootstrap. Creator, wallet, token and funding-cluster connections
must not leak across development/confirmation splits. Exact creator/user equality is
only a partial anti-spam control, not proof of independent ownership. Funding information
learned later cannot be inserted into historical features.

The owner's 4.01 percentage-point session-noise estimate is explicitly owner-reported
historical context. Do not subtract it as a fee or assert it is a universal standard
error. A candidate requires repeatable gains beyond session variation, not merely a
pooled bootstrap win. Require fresh untouched sessions/weeks, mint and session confidence
intervals, no best-mint or best-session dependence, and mean/median positivity under the
full-loss stress. Exact cohort horizon, gates, and multiplicity rules must be frozen
before observing its financial outcomes; this instrument has no such outcome cohort yet.

**Open gates:** independent creation census/recall; usable causal history; program
version boundary; anti-spam/funding controls; exact pool and executable entry/exit
evidence; whole-pipeline profitability placebo; repeated fresh weeks; PLAN promotion
gates and separate explicit authorization before any real orders. Default NO_TRADE.

## Primary protocol sources

Access date: 2026-09-08 UTC. Sources describe interfaces, not performance guarantees.

- [Solana logsSubscribe](https://solana.com/docs/rpc/websocket/logssubscribe):
  slot/signature/err/logs notifications; no transaction index in the notification.
- [Solana getBlock](https://solana.com/docs/rpc/http/getblock): block signatures and
  transaction-detail options used for order reconciliation.
- [Solana public clusters](https://solana.com/docs/references/clusters): public
  endpoint context; no completeness or uptime guarantee is inferred.
- Pump official IDL commit `9c82f61cb711b044a17f770ab8ce9f9bdf78f333`, local
  `research/pump_idl_9c82f61.json`, SHA-256
  `b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49`.
  This hash is checked in code and recorded in each session manifest.
