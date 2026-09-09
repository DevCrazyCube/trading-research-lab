# Multi-day cohort candidate: repair the test, keep the hypothesis open

Author: Codex, 2026-09-09 UTC. **Status: DEVELOPMENT / NO_TRADE.**
Owner supplied Claude's runner/cohort investigation and asked to continue building.
This is not another run of a retired momentum, handling, paid-attention or scalp test.
No profitable bot has been established; no finding below claims all possibilities closed.

## The candidate worth testing

**Working hypothesis:** a roster identified using information already available can
repeatedly accumulate tokens whose incremental demand lasts days, allowing a copier
to enter after actual observation and costs. This differs in holding horizon from the
failed sub-second scalp replication. Slower opportunities are possible, not verified.
Profit would still come from later willing buyers, not the fact a wallet ranks highly.

The actionable question is **future returns after known-roster accumulation**, not
what today's winning wallets held before they became winners. Public leaderboards,
successful token transfers, distinct addresses and paper marks are each weaker than
audited profit, economic independence, purchased inventory or executable exits.

## Verified defects in the current experiment

Inspected source, left unchanged under Claude's ownership:
`scripts/trading_bot/memebot/{cohort_history,cohort_history_controls,cohort_cluster_test,books_snapshot}.py`.

1. **Roster lookahead.** Leaderboard `capturedAt` is 2026-09-09T12:30:48.905Z.
   Replaying its prior 14 days uses future winner selection for older entries.
   Random-wallet controls cannot remove that information leak. Historical output is
   development data, never an out-of-sample positive result. Provider capture time is
   itself not a retained local receipt; prospective availability must be later.
2. **Unequal opportunities.** The history arms contain 126 versus 30 roster wallets.
   The same k-wallet threshold is mechanically more likely in the larger arm. Equal
   sample size is necessary but does not establish matching on prior activity or
   funding dependencies. Distinct addresses are not necessarily independent people.
3. **Owner accounting.** Dictionaries overwrite rather than sum multiple token
   accounts for one owner/mint; floats and nullable `uiAmount` discard raw precision.
   Fee addback applies to every owner appearing in a transaction, not just its payer.
   Native SOL changes also contain rent/transfers/wrapping, not only consideration.
4. **Flow versus purchase.** USDC out plus another token in repairs the SOL-only
   heuristic but does not prove those legs belong to one swap. Multiple asset changes,
   transfers, account ownership changes and routed operations require instruction
   reconciliation. A zero-SOL transfer does not prove a free allocation: USDC, another
   token, earlier payment or external consideration may exist. No cost basis is implied.
5. **History completeness.** Failed RPC requests become `None`, skipped transactions
   disappear, and wallets can be marked `done` anyway. The 1,500-signature cap and
   variable `time.time()-14 days` cutoff have no auditable completion states. Owner
   address history is not all token-account history. Raw transaction responses are
   not stored in these databases, preventing an offline exact accounting replay.
6. **Current-pool selection.** `pair_created` chooses among pools returned now;
   disappeared pools/mints leave the denominator. Earliest currently returned pool
   is not proven first issuance or the contemporaneously executable route. Current
   marketCap/price is not an authenticated historical circulating supply.
7. **Entries and missingness.** The evaluator uses index 4 (close), not index 1
   (open), of the next OHLCV bar. Missing pool/entry bars are dropped. Horizon
   tolerances mix widely different elapsed times; there is no complete all-signal
   resolution table or all three dropout scenarios. Chart prices are not fills.
8. **Costs and inference.** `TOLL=0.0114` is applied twice via `(1-TOLL)**2`, despite
   1.14% being the supplied historical ROUND-TRIP assumption. Neither number verifies
   this cohort's contemporary routes, transfer taxes, failures or capacity. There is
   no mint/session clustered financial uncertainty or whole-pipeline shuffle test.

**Verified live-database snapshot, about 15:17 UTC:** board 9,828 rows, 6,801 distinct
signatures, 757 mints, 13 wallets with rows and 12 marked done; control 1,100 rows,
141 mints, one wallet with rows and zero marked done. Board 9,750 and control 1,057
rows precede the leaderboard's reported snapshot. These are mutable collection
snapshots, not completion, audit of every row, or performance figures.

## Implemented independently

`scripts/cohort_evidence.py` is offline-only and does not alter either collector.

- Sums exact raw integers across owner token accounts, including nullable display
  amounts and Token-2022-shaped metadata; keeps program/mint/decimals separate.
- Credits transaction fee only to the actual fee payer; preserves native delta and
  rent/transfer ambiguity. No native-SOL sign is automatically promoted to a purchase.
- Refuses missing owners/metadata, duplicate balances, decimal conflicts, failed
  transaction token mutations, wrong signatures and unexpanded versioned keys.
- Keeps transaction/instruction order explicitly unresolved without independent block
  evidence. An account-delta record is not a DEX instruction or a replacement for
  the repository's canonical event schema; it is input evidence awaiting reconciliation.
- Emits quote-exchange CANDIDATE only, never `buy_proven`. Even a two-leg payment
  shape could comprise unrelated transfers and requires protocol authentication.
- Enforces roster/rule/feature availability before entry. Diagnostic chart sensitivity
  retains missing entry/exit rows, all three dropout scenarios, true resolved zero
  exits, mint uniqueness, mean, median and resolution denominator. It is explicitly
  **not executable P&L** and implements neither bootstrap nor promotion.

**Verified tests:** 23 unit/adversarial tests pass. Twelve saved transaction bodies
yielded 27 decoded owner/transaction cases; 15 reproduce the old non-payer fee-addback
error. Token deltas agree on those particular cases; the multi-account overwrite defect
is demonstrated synthetically, not claimed to occur in that small real fixture.
Seven non-transaction wrappers in the selected fixture list were not decoded; counts
and input hashes are preserved in `cohort_decoder_validation_20260909.json`. The
fixture is selected engineering data, not a strategy validation cohort.

Reproduce guards and current DB audit:

```sh
python -m unittest scripts.test_cohort_evidence
python -m scripts.cohort_evidence
```

## Forward identity freeze completed; financial rule NOT frozen or activated

**Decision:** preserve a deterministic 30-wallet sample of the current board and all
30 supplied controls, disjoint/equal-sized, sampled by SHA256 rather than later P&L.
Raw identities remain private under `fomo_private/cohort_roster_v1_20260909/roster.json`.
Local freeze: 2026-09-09 15:20:14.748359579 UTC. Never backdate this availability.
Manifest SHA256 `6f572e3501d750924ff6d1921c53c7a90a646ec9af9161ac0991f678bfe5ee2f`.
Source board SHA256 `f3d782c297684e58031ca634866da79656f1b4e2ec36dc1a3c555fb3b0ba2466`;
controls SHA256 `7be5e602ce595401ccaf8865fd62bb33d3da61b3c64b537c45c4766d135d4d14`.
The other 96 board wallets remain in the source, not silently discarded history.

This freezes identities only. Control provenance/activity matching and funding
independence are still unproven; it is not a valid financial placebo yet. No later
price, outcome or desired signal frequency informed the deterministic sample.
No new cohort network collector or money runner was started by Codex in this work.

**Next implementation boundary:** collector owner must retain exact RPC responses,
successful/failed/unknown states, fixed history boundaries and cap/page checkpoints,
then use the corrected decoder with protocol-level purchase authentication. A new
financial contract must fix k, timing, size, portfolio limits and exits *before* its
future outcome cohort; use actual next-real-open availability, exact route/fees,
all-signal missingness, matched controls and mint/session/funding inference. No
post-hoc trailing exit or enlarged roster may be sold as a result on the same cohort.
The sealed window-2 asset is untouched. No real-money activation is authorized.

## Separate corrections to the supplied recap

The tracker replay has finished EXACT, not pending. It attests internal bytes/derived
records, not 99.43% recall or a complete wallet ledger. Socket gap arithmetic cannot
bound missing births; see `FOMO_FEASIBILITY_20260909.md` for measured boundaries.
Fast graduation is not a fake graduation merely because it was fast; establishing
self-dealing requires transaction/funding evidence. Missing later trades in a 7.3-hour
record are not proof a mint died. These distinctions keep the data usable honestly.

The FOMO timing probes are stopped with no lead result. Unique coarse matching is
not mathematically impossible, but it would remain an unauthenticated association
under incomplete capture. A paid subscription would not by itself prove profitable
execution. No additional FOMO credits were used for this cohort audit or roster freeze.

## Primary interface sources

Accessed 2026-09-09, Solana RPC `jsonParsed`, max transaction version 0:

- https://solana.com/docs/rpc/json-structures — raw token amounts, account indexes,
  owners, metadata optionality and parsed/loaded account structure.
- https://solana.com/docs/rpc/http/getsignaturesforaddress — address-reference history,
  newest-first pagination and limits, not a whole-owner balance-history guarantee.
- https://solana.com/docs/rpc/http/gettransaction — null/unavailable transaction and
  version/encoding semantics.
- https://solana.com/docs/core/fees — fee payer and failed-transaction fees.
- https://fomoapi.io/docs — leaderboard and history are vendor-supplied interfaces;
  no independent audit or future-return guarantee follows from a ranking.
