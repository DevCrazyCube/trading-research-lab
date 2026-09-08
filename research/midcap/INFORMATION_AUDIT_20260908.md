# New-information audit and birth-origin prototype

Author: Codex. Date: 2026-09-08 UTC. Status: verified engineering work and an
unproven working hypothesis. **No profitable trading system demonstrated.**

The old entry/exit grids, sniping, momentum, reversion, arbitrage, and perp studies
were not rerun. No trading process was activated and no transaction was submitted.
Existing raw files, frozen strategies, and unrelated working-tree changes were preserved.

## The concrete invention

**Working hypothesis:** new launch actors copying a name can send attention to the
earliest already observed coin using that name. At the arrival of a fourth exact
creator/user identity group within six hours, observe the earlier coin as the possible
recipient, rather than buying the new copy. It is a non-price, cross-mint information
channel; calling it demand remains a hypothesis. The first-in-window coin is not
asserted to be the original meme, and exact address groups are not proven independent
economic owners.

Implemented in `scripts/birth_origin.py`, specified in
`BIRTH_ORIGIN_V1_SPEC.md`. It consumes actual canonical creation records, uses only
past names and identity links, observes transactions as indivisible units, accounts
for every launch's scope, requires a six-hour history, and emits a mint at most once.
All observations are **NO_TRADE / historical_oracle**, with source evidence hashes.
It has no price or return input, order path, or live adapter. A separate raw live
recorder is now implemented and pilot-verified below; it is not wired to trading or
the observer. This is a detector prototype, not a completed paper or live bot.

**Verified fact:** replay over 33,866 creations, slots
`[435569150, 435772751)`, produced 1,212 distinct candidate observations. There were
26,393 native-SOL/non-Mayhem launches, 7,473 explicit scope exclusions, and 8,743
in-scope births during the six-hour warmup. The launch span is 85,802 seconds
(23.83 hours), so the corpus cannot establish three disjoint daily replications.

**Hostile result:** all 20 fixed within-actor text permutations produced MORE
candidate observations: 1,319–1,417 versus 1,212 real. The permutations preserve
creation times and creator/user identity groups, moving only name/symbol term sets
within those groups; 18,556–18,707 rows changed text. No seeds were discarded.

This is a warning against interpreting word crossings as an edge. It is NOT a
profitability placebo or a strategy-survivor count: no returns were evaluated, and
signal frequency alone cannot establish or refute conditional profitability.
There is no positive financial result to promote. Performance mean, median,
resolution rate, and profitable survivors are all **not evaluated**, not zero.

Results: `birth_origin_v1_validated_20260908/result.json` and its
`observations.json`. Logical source hash:
`789c1411a89f085e447dbb0849980a6638bc2da91c48fa16082bf94fae9cb3c2`.
Observation hash:
`1bfa6ad0709b89f30d1d36cb73ef230c7568bfa56b245203a610d664d8ff4337`.

An initial implementation missed known creator/user bridges on other words. Its
output is retained in `birth_origin_v1_20260908/` as engineering-invalid for that
requirement. The corrected implementation carries causal identity context across
all words and older births. The real count happened to stay unchanged; that is not
the reason for accepting the correction. Synthetic bridge attacks now pass. No
economic result, threshold, word list, or seed was selected from this repair.

## What the repository audit actually killed

**Decision: reject the existing fresh snapshots as a birth census.** The producer
`scripts/trading_bot/memebot/fresh_scan.py` enumerates by market cap/recent trades and
keeps only coins above $100,000. All 2,464 first sightings in the audited prefix
were already at least $100,000. The prefix contains 262,006 coin snapshots, 2,257
cycle rows and one incomplete trailing line, which is counted and excluded from
interpretation without altering it. Median first-sighting age under its recorded
clock is 107.357 seconds. This says nothing about creations never admitted by the
collector. The existing under-$300,000 formation universe is therefore effectively
a first-seen $100,000–$300,000 subset, not all coins before their first move.

**Verified fact: the observation clock is early.** `now_ms` is sampled BEFORE the
network harvest and reused on every returned row. In 118 first sightings, `ts_ms`
is earlier than `created_ms`. These are recorded clock contradictions, not births
predicted in advance. A future-data guard needs individual response receipt times;
the existing timestamps cannot supply them retrospectively. No outcome from the
old frozen formation experiment was opened or re-evaluated.

**Decision: reject a 90% candle as proof of LP withdrawal.** Price collapse, selling
by a large holder, unavailable provider data, and withdrawal of pool liquidity are
different events. Pump's [pinned primary documentation](https://raw.githubusercontent.com/pump-fun/pump-public-docs/9c82f61cb711b044a17f770ab8ce9f9bdf78f333/docs/PUMP_PROGRAM_README.md)
says migration LP tokens are burned. More decisively, the local raw transactions
show positive LP burns for **82/82 distinct migrated mints**. There are 122 cached
migration instructions; 82 have positive same-transaction LP burn evidence and 40
do not. Repeated migration calls must not be counted as separate pools.

The auditor rechecks each retained raw-response SHA-256, successful transaction and
slot, raw instruction/account equality, pinned migration discriminator, exact LP
mint and token program, and strict SPL Burn/BurnChecked bytes. It uses the existing
canonical envelope parser. This establishes positive migration-burn evidence. It
does not claim every later deposit or withdrawal is observed, or that burned initial
LP tokens prevent all forms of loss. Post-graduation selling remains dangerous.

**Verified fact: the proposed identity join is smaller and less direct than claimed.**
The reserve corpus now has 3,932 curves. Of them, 82 have complete graduate labels;
70 also have nonempty OHLCV. Only **67 of those 70** have a stored OHLCV pool matching
their canonical migration pool. The cache contains **zero decoded PumpSwap withdraw
instructions**, but it was not collected as a complete pool-history census. Absence
of recorded withdrawals therefore is not proof of no withdrawals. The buyer-to-LP-pull
prediction task has no verified withdrawal target in this cache. **Decision after
owner correction: drop this join from the work list**, not merely defer it until more
data arrive. The retained statistical label is single-minute drawdown ≥90%, mechanism
unknown. Its supplied prevalence was not recomputed here.

**Verified fact: the OHLCV denominator contains provider failures.** Its 1,075 rows
partition into 972 `ok`, 34 `nobars:200`, 32 `nobars:429`, and 37 `nopool:429`.
HTTP 429 denotes retrieval failure, not proof that a token had no pool or died.
There are 110,199 stored bars and 96 mint rows with duplicate bar timestamps. The
collector requests the first returned pool much later and one page of up to 1,000
bars. Chain enumeration of the mint universe does not by itself prove unbiased
pool selection, complete price histories, or executable exits. These are audit
findings, not a recalculation or reversal of the old negative return results.

Audit artifact: `information_audit_20260908/result.json`. It contains the full mint
join, raw migration evidence, logical SQL hashes and snapshot prefix hash/byte limit.
The auditor is `scripts/memecoin_information_audit.py`.

## Conflicts explicitly resolved

**Decision:** follow the owner's corrected mint-equal benchmark (-14% to -23%) in
place of the old closure report's trade-pooled -2.92%. A new cohort still needs its
own comparable control; an old aggregate is not a causal matched control.

**Verified arithmetic:** the pasted ledger categories total
`2072 - 9683 + 2175 = -5436 SOL`. The closure document additionally lists 7,110 SOL
retained in curves, giving **+1,674 SOL**, not zero. These written aggregates need
reconciliation. The original raw conservation audit was not rerun; this discrepancy
does not by itself disprove its raw result. It does invalidate citing this particular
written table as a demonstrated zero-sum identity.

**Verified mathematical fact:** negative unconditional expectancy does not prove
every conditional strategy must lose. It also gives no evidence that a profitable
condition exists. The closure report's universal impossibility wording is stronger
than its quoted measurements support. No old failed strategy is reopened by that
logical correction.

**Verified discrepancy:** `discipline_bot.py` describes $21.57/$68.60 as average
position SIZE; the current prompt describes winners/losers averaging those amounts.
The owner subsequently confirmed the ledger/pair do not exist in the repository:
they are unaudited manual-trade chat anecdotes, not validation evidence. ANON is
owner-reported Robinhood; BRO is BSC, not Robinhood. No sizing or entry conclusion is
inferred from them. Trimming winners can follow their subsequent path; the 3/4 versus
0/4 observation alone is not an identified causal edge. Exact owner-supplied identifiers
and the exclusion decision are in `BIRTH_STREAM_FORWARD_CONTRACT_20260908.md`.

Historical status paragraphs in PLAN/DOCUMENTATION are superseded by later dated
retirement decisions. The old formation contract remains unchanged. This newly
requested non-price prototype has no authority to restart any retired bot.

## Robinhood and remaining requirements

**Verified fact:** official Robinhood documentation identifies mainnet 4663, and
a read-only public RPC call returned `eth_chainId = 0x1237` (4663) and a nonempty
block number. Mainnet availability is no longer an assumption. Blockscout's stats
endpoint returned challenge HTML from this host, so that path provided no census.
This is not a kill of Robinhood or proof of an edge; no new base rate was measured.
Primary URLs, versions, access date and exact RPC response are retained in
`INFORMATION_SOURCES_20260908.json`.

**Open questions blocking an entry test:** fresh full-birth receipt history and
measured recall; exact pool/route and exit evidence;
funding dependencies; and forward outcomes over multiple weeks. The existing
live decoder discards the creation's distinct `creator` and URI while retaining
`user`, so its normalized birth records cannot establish the proposed creator
groups without a separate raw-evidence adapter. It was not modified or restarted.

The next money experiment must be separately frozen only after those inputs exist.
The owner explicitly excludes the pair from validation; it is no longer a gate.
The preserved development spec/result's earlier pair requirement is superseded by
`BIRTH_STREAM_FORWARD_CONTRACT_20260908.md`, without changing their pinned bytes. Apply the
owner's next-real-bar, one-mint-once, mint-equal mean/median, resolution and three
dropout stresses, a whole-pipeline profitability placebo, and fresh chronological
confirmation. A positive diagnostic must also survive best-mint/day removal and
actual route costs, plus mint- and session-cluster uncertainty. The supplied 4.01pp
session-noise estimate is owner-reported context, not a fee or universal standard
error. The supplied 1.14% toll is a historical scenario, not a universal
current execution guarantee. Until those checks pass, the implementation says
NO_TRADE and has no order path.

## Direct creation-stream pilot, verified 2026-09-08

**Verified engineering fact:** `scripts/birth_stream.py` captured 8,502 raw frames
in its bounded 45-second pilot. Six creation observations represent five successful
transactions and one failed attempt; zero decoder issues, zero pending frames,
zero duplicated create observations. All regimes, distinct creator/user fields,
URI, per-frame wall/monotonic receipt clocks and raw payloads are retained. No market
cap endpoint/filter is involved. Source: `birth_stream_pilot_network_20260908.sqlite`.
The earlier sandbox-DNS failure session is preserved separately, not counted as a
successful capture.

**Verified engineering fact:** `scripts/birth_stream_verify.py` reproduced every
frame and derived creation exactly, then reconciled all six observations with
preserved public-RPC transaction bodies and block signatures. Five exact program-bound
CPI CreateEvent payloads matched; the failed transaction remains NOT_A_BIRTH. Success
slots: 445398682, 445398685, 445398689, 445398694, 445398697. Canonical event coordinates
use the existing B7d `create_event` schema, not receipt or log order. Later HTTP fetch
times do not replace original receipt times. The raw frame chain ends at
`2516d3166e031c980e55984d8d66c41c1e634089aa28c3e65f592e36cc18e4a6`.

Evidence: `birth_stream_verify_network_20260908/` includes every raw RPC request/
response and receipt hash; `birth_stream_verify_offline_20260908/` independently
recomputes the same reconciliation from those bytes without new network requests.
The failed sandbox-RPC attempt is retained in `birth_stream_verify_20260908/`.

**Open gates:** matching the six observed transactions does NOT establish full
creation recall, independent-provider agreement, deployment-version boundaries,
fresh six-hour causal history, anti-funding-spam controls, or executable returns.
The source is single-provider, finalized, and observation-only. No money result or
profitable survivor was evaluated. See `BIRTH_STREAM_FORWARD_CONTRACT_20260908.md`
for the complete owner-corrected measurement and forward-evaluation contract.

**Verified operational snapshot:** an eight-hour bounded recorder started at
2026-09-08 18:03:27 UTC in its own `birth-create-20260908-1805` tmux session
(pane process 241967). At 18:03:53 UTC it had 4,501 frames, seven successful
creation observations and zero issues; later snapshots must be checked directly,
not inferred from this sentence. Output: `birth_stream_forward_20260908T1805.sqlite`
and `.log`. It stops around 2026-09-09 02:03:27 UTC or sooner on disconnect, 8 GiB
capture capacity, or the 16 GiB free-space reserve. The session suffix is a name,
not the authoritative start clock. There is no watchdog/reconnect, detector hookup,
paper activation, or order path. A process or sparse creation count is not a census.

## Reproduction and verification

```sh
python -m unittest scripts.test_birth_origin scripts.test_memecoin_information_audit scripts.test_birth_stream scripts.test_birth_stream_verify
python -m scripts.memecoin_information_audit --out /tmp/memecoin-information-new-run
python -m scripts.birth_origin --out /tmp/birth-origin-new-run
python -m scripts.birth_stream --out /tmp/birth-stream-new.sqlite --seconds 60 --max-mib 128
python -m scripts.birth_stream_verify --source research/midcap/birth_stream_pilot_network_20260908.sqlite --out /tmp/birth-replay-new --rpc-evidence research/midcap/birth_stream_verify_network_20260908
```

Use output paths that do not already exist. Source databases are opened read-only;
JSONL is read to a recorded byte boundary. If a collector appends, its newly audited
prefix will naturally differ. The four test modules pass **51 tests** covering future
text and identity leakage, same-transaction timing, spam, stale history, malformed
and duplicate records, wrong-mint/program burns, truncated/padded payloads, raw-before-
decode persistence, derived-record tampering, receipt hashes, canonical reconciliation,
and saved-RPC replay without network access.
Those are engineering checks. There is no profitability test result and no promise
of green weeks.
