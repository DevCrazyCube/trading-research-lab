# FOMO feasibility and creation-tracker completion

Author: Codex. Updated 2026-09-09 UTC. **Status: NO_TRADE; no profit claim.**

## Actual FOMO access

**Verified observation:** one authenticated `/ws/alerts` connection on September 8,
21:49:38.987–21:50:04.183 UTC reported `realtime: true`, `delaySeconds: 0`. The planned
90-second probe stopped after 25.196 seconds with `WebSocketConnectionClosedException`.
Its underlying cause is unknown; exception bodies were not logged because they can
contain authenticated URLs. No reconnect, paid upgrade, REST lookup, signing, or order.

106 frames: one welcome, 100 explicitly replayed alerts, five alerts without replay
flags. Missing flags remain UNKNOWN. The raw receipt-bound hash chain reproduces
exactly; no malformed messages or clock discontinuities were detected. Unflagged
messages concerned Solana (2), BSC (1), and Robinhood (2). Receipt minus provider `ts`
ranged 0.888–2.121 seconds for those five: this is NOT block-to-app latency.

**Verified schema finding:** none of 105 alerts contains a transaction hash or signature.
Recursive inspection found only `raw.title` and `raw.text` below `raw`. Chain, token,
display identity and rounded size do not prove exact transaction identity. No chain
join, executable return, or 15-second advantage was established.

**Decision:** before a timing experiment, establish point-in-time wallet mapping,
exact chain-event matching, replay/retraction handling and app-delivery semantics.
Preserve every prospectively eligible event: never admit historical entries because
we later learn they received an alert. A separate frozen financial test still needs
all costs, next-real-bar entry, missing-exit stresses, mint/session dependence and
untouched weekly confirmation. No paid plan or trading activation is justified here.

### Reproduction and containment

`scripts/fomo_probe.py` has 11 tests: replay/delay handling, malformed/unknown input,
clock changes, negative provider-age values, receipt hashes, raw durability before
another receive, single connection, no redirects, secret-echo refusal, private file
permissions, exception redaction and closed-tail deletion. This is a raw transport
probe, not a canonical event/feature feed.

Private evidence is git-ignored under `research/midcap/fomo_private/`; SQLite mode 0600.
Report: `python -m scripts.fomo_probe --report research/midcap/fomo_private/probe_network_20260908.sqlite`.
The separate sandbox DNS failure received zero frames and is preserved. Network retry
used explicit approval. Actual credit debit was not measured; one authenticated
connection was made, and vendor documentation says stream messages are free.

Capture-time source is preserved as `fomo_private/probe_capture_source_20260908.py`:
SHA256 `a96046ca517329baa43063a2eb962a90e6957ef147631490fd5bc98a869ffb7a`, matching
the manifest. Current reporting additionally handles non-string message types as
UNKNOWN; this capture still reproduces. Raw-chain tail:
`5752f3d5bf4bb1d9f86767d914a23b8b37650c464ae51c78e8fe8c375175fd8e`.

## Account-report correction

**Verified offline finding:** the 100-swap response is explicitly capped/incomplete.
29 chain/token groups contain some purchase, not necessarily their original entry;
two start with a sell, and three have materially negative observed inventory prefixes
under a zero-opening-inventory assumption. They span 31 position IDs, a different
denominator. Missing purchases/transfers/basis must be resolved rather than ignored.

ANON bought 18,798.42 visible tokens and sold 88,893.90. Its first visible row is a
sell. Claimed +$39.62 is $48.99884 proceeds minus $9.38163 visible purchases, without
opening basis. Aggregate -$110.99619 reproduces as visible cash flow plus selected
later marks, not independently reconciled all-cost P&L. The -18.414% deployed-dollar
ratio cannot validate a mint-equal 15-minute Solana benchmark across other chains and
holding periods. Sell-count and forced-trim conclusions remain unproven.

Saved source reviewed at `/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/`:
`k_swaps.json` SHA256 `f5cc0a3938bb9e72cccbafe453f577484806e950e21c988017c4b814551e3589`;
`k_balances.json` SHA256 `37969071b50fc45e9674a5232e2f4a9cc0eebef5cfef629f41e671f7a8c33d2f`.
These improve on chat anecdotes but do not promote ANON/BRO into a validation set.

## Creation tracker completed; full replay EXACT

**Verified database/log status:** duration complete, closed 2026-09-09 02:21:14.861 UTC.
9,613,996 frames; 10,891 creation observations; 10,747 distinct observed creation
transaction signatures; 10,122 successful observations (9,993 distinct successful
signatures); 769 failed observations. Observations, signatures and mints differ.

Eight epochs, seven UNKNOWN_UNREPAIRED gaps, one decode refusal, zero pending raw and
zero uncommitted received frames. Refusal at frame 4,236,245 independently reproduces:
truncated transaction logs. That is not absence of a creation or a token failure.

The longest connection epoch is 107.880 minutes. Thus elapsed duration does NOT supply
six hours of uninterrupted history. Even uninterrupted transport would not prove
complete chain discovery. Narrative-history and recall gates remain open.

`scripts/birth_stream_replay_job.py` wraps the existing verifier unchanged, caches its
pinned IDL map, and saves progress every 100,000 notification-decoder calls. No RPC
or sampling. The 7,482-frame real pilot produced an identical original-verifier report
except added job provenance. Combined recorder/replay/FOMO engineering suite: 58 pass.

**Verified completion, September 9:** full job
`research/midcap/birth_stream_full_replay_20260909/result.json` reports EXACT for all
9,613,996 frames and 10,891 creation observations. Elapsed 2,453.209 seconds (40.9
minutes), not eight hours of processing. Session `birth-replay-20260909` ended.
Result SHA256 `55cde4aae333ed40977f9b2c309c1691b3aae2d216f26a61bddbc239f12d05ef`.
142 duplicate creation observations, seven unrepaired gaps and the single refusal
are preserved, not erased by replay success. Source and original verifier unchanged.
Successful unique mints: 9,995; this differs from observations and transaction counts.
The decoded accounting includes 1,169,143 TradeEvent observations, not necessarily
unique successful trades. This is internal recording consistency, not independent
chain census, complete wallet history, exact execution, or profitability.

**Correction to the supplied 99.43% coverage claim:** summing time from the last
receipt to detecting a gap omits reconnection and delivery lag. The saved gap fields
sum to 168.353 seconds from last receipt to resumed notification, not 150.6 seconds.
The two approximately instantaneous 1006 detections resume 170 and 137 slots later.
Neither socket-clock percentage establishes chain recall or bounds missed creations;
62 missing births is a rate-based extrapolation, not an observed upper bound.
The record remains useful development data. No assertion of complete history follows.

## Paired timing feasibility stopped; no financial hypothesis verdict

**Verified local observations:** separate paired Robinhood/FOMO probes preserve
raw HTTP and WebSocket receipts, encoded bodies, response metadata, hash chains,
replays and failures in private SQLite. Three handles were fixed by prior pilot
receipt order, not later P&L. Mapping cost headers showed 10 credits each, 30 total.
The second paired run reused those mappings and spent no new resolution credits.
No plan purchase, paid-stream connection, signer, or order was used.

| Private run | RPC calls | Validated log ranges | Alerts / explicit replays | End |
|---|---:|---:|---:|---|
| paired_network_v2_20260909 | 125 | 61 | 119 / 100 | HTTP 429 |
| paired_network_v3_20260909 | 52 | 25 | 117 / 100 | HTTP 429 |

Both observed zero eligible alerts and zero token transfers for the three previously
selected identities. This is no timing result, not evidence of a negative return or
universal impossibility. Other tokens' contemporaneous activity is not an exact join.
The 2-second cadence failed first; a 5-second cadence also failed. No undocumented
RPC throughput guarantee is inferred. Both processes are stopped; no more retries.

**Engineering:** `scripts/fomo_chain_probe.py` handles bounded gzip/deflate responses
after an initial gzip decoding refusal. Previous raw capture and exact v1/v2 source
snapshots remain private and unchanged. Strict ERC20-shaped logs exclude ERC721
four-topic events. Flow is never asserted to be a swap. A unique coarse match is
still only a candidate association, particularly with incomplete capture. Public
RPC logs remain single-source/unfinalized, not canonical consumer events. Twelve
tests pass; no live or historical return is computed by this probe.

**Separate owner inventory check:** `scripts/fomo_inventory_probe.py` made 30 bounded
public RPC reads, no FOMO calls. It bracketed the capped-history cutoff but historical
`eth_call` returned RPC error -32000, `metadata is not found, 55261805`. No token
balance, opening basis or P&L was established. Raw response and closure are preserved
under `fomo_private/owner_inventory_20260909`. Four tests cover block search and ABI
selectors. The RPC error is not a zero balance or proof of token death.

**Decision:** leave these feasibility probes stopped and continue the owner's newly
supplied multi-day cohort investigation. Do not restart the paid-attention, handling,
scalp/copy or other retired experiments. See `COHORT_EVIDENCE_AUDIT_20260909.md`.

## Primary interface references

Accessed 2026-09-08 and rechecked September 9 UTC; interface claims, not performance verification:

- https://fomoapi.io/openapi.json — version 2.0.0 declares the provider independent and
  unofficial and describes pass-through P&L/history.
- https://fomoapi.io/docs — free realtime trial then added 15-second delay;
  welcome/replay semantics and vendor-claimed on-chain-stream lead.
- https://docs.robinhood.com/chain/connecting/ — mainnet 4663, public RPC explicitly
  rate-limited; production/archive providers distinguished from public endpoints.
- https://eips.ethereum.org/EIPS/eip-20 — Transfer shape and token balance interface;
  interface conformance is not authenticated economic intent.
