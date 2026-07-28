# B6e — Provider Evaluation: Bitquery CoreCast vs Yellowstone gRPC

Date: 2026-07-27. Author: Claude.
Prompted by the owner surfacing <https://docs.bitquery.io/docs/grpc/solana/introduction/>.

Sources are vendor documentation plus, decisively, the **primary source**: the Yellowstone
`geyser.proto` schema in `rpcpool/yellowstone-grpc`. Per `DOCUMENTATION.md`'s source policy,
official protocol definitions outrank vendor marketing.

## The requirements being tested against

Recorded in `agent_discussion.md` Seq 6 and 18, and in `DECISIONS.md`:

1. Per-message sequence numbers **or** a heartbeat — else gap detection degrades to slot
   discontinuity only, and short outages become invisible.
2. Slot status transitions **including dead/skipped slots** — else the orphan record (R2) cannot
   be derived, and orphan data is the one artefact that cannot be bought later.
3. Commitment transitions processed → confirmed → finalized — the entire motivation for C3.
4. Server-side filtering by program id.
5. Raw protobuf bytes storable unchanged (capture-first).
6. Sustained bandwidth at our measured volume.

## Bitquery CoreCast — fails as a primary recorder source

| Requirement | Result |
|---|---|
| Sequence numbers / heartbeat | **Not documented** |
| Slot status incl. dead slots | **Not documented** |
| Commitment transitions | **Not documented**; `transactions` topic is described as *"Finalized transactions"* |
| Program-id filtering | **Yes** — `program_ids` is a supported server-side filter |
| Raw protobuf | Protobuf, but of a **proprietary schema** (`bitquery-corecast-proto`), not Geyser |
| Plan | Paid; not in the free tier by default; filters mandatory (empty filter sets rejected) |

Two independent disqualifiers:

**F30 — Finalized-only delivery defeats the purpose of live recording (verified from docs).**
The stated reason for starting live capture before anything else (C3) is that latency, orphaned
slots, and commitment transitions are *not recoverable from history*. A finalized-only feed
delivers exactly the information Old Faithful already has. Paying for it would buy a slower,
costlier copy of data we can backfill for free.

**F31 — It is an interpreted product, not a chain feed (verified from docs).**
Topics include `dex_trades`, `dex_orders`, `dex_pools` — Bitquery's *interpretation* of on-chain
activity. `AGENTS.md` requires exact on-chain decoding from official IDLs over third-party
interpretation, and requires third-party claims be treated as claims. Recording CoreCast frames
byte-for-byte would satisfy capture-first mechanically while storing a vendor's opinion of the
chain rather than the chain. Our own decoder work (B0b–B2c) would sit downstream of someone
else's parsing, and every exactness result established so far would become unverifiable.

**Where it could still be useful:** `DOCUMENTATION.md` calls for "at least one independent path
for verification." A derived feed is a legitimate *cross-check* oracle — disagreement between it
and our decoder is a signal worth having. That is a later, optional purchase, not the recorder.

## Yellowstone gRPC — satisfies every requirement

Verified directly from `geyser.proto`:

| Requirement | Evidence from the proto |
|---|---|
| Heartbeat | `SubscribeUpdatePing` / `SubscribeUpdatePong` in the `SubscribeUpdate` oneof |
| Slot status incl. dead | `SlotStatus` enum: `SLOT_PROCESSED`, `SLOT_CONFIRMED`, `SLOT_FINALIZED`, `SLOT_FIRST_SHRED_RECEIVED`, `SLOT_COMPLETED`, `SLOT_CREATED_BANK`, **`SLOT_DEAD`**, plus an optional `dead_error` field |
| Commitment transitions | the same enum, delivered as slot updates |
| Program-id filtering | `SubscribeRequestFilterTransactions` with `account_include`, `account_exclude`, `account_required` |
| Raw protobuf | native protobuf; frames storable unchanged |
| Provider timing | `created_at` (`google.protobuf.Timestamp`) on `SubscribeUpdate` |

Also available: `accounts`, `slots`, `transactions`, `transactions_status`, `blocks`,
`blocks_meta`, `entries` — including the account-update stream that Old Faithful lacks, which is
the other thing history cannot supply.

**One honest nuance:** Yellowstone provides a **heartbeat**, not a per-message monotonic sequence
number. Our Seq-6 requirement was "sequence numbers *or* heartbeat", so this satisfies it — but
gap detection will rest on ping/pong liveness plus slot continuity rather than on a strict
per-message counter. The `raw_frame.provider_seq` field stays null for this source, exactly as
spec v0.2 anticipated ("never synthesize it").

## Vendor selection — a bandwidth question, not a price question

Yellowstone is a standard (Triton One's Dragon's Mouth), so the schema is identical across
vendors and the choice is commercial, not technical. Indicative 2026 entry pricing: Chainstack
from $49/mo for one stream; Shyft from $199/mo; Solana Tracker €200/mo flat and unmetered;
Helius, QuickNode and Triton also offer it.

**The decisive variable is the data policy, not the headline price.** B6a/B6c measured Pump-only
traffic at ~241 GB/day raw. A cheap metered plan can cost more than an expensive unmetered one at
that volume, and worse, a mid-month cap becomes a **correlated capture gap** — the failure mode
this project explicitly forbids. Evaluate on sustained-bandwidth policy and overage behaviour
first, price second.

## Recommendation

1. Yellowstone gRPC, vendor chosen on bandwidth policy. A metered plan needs its cap checked
   against ~241 GB/day raw before purchase.
2. Do **not** buy CoreCast as the recorder. Reconsider it later, optionally, as an independent
   cross-check oracle.
3. **The owner must create the account and hold the credentials.** Neither agent should. The
   recorder already refuses to persist a credential-bearing URL, and that refusal is
   regression-tested (`tests/test_recorder.py::CredentialLeakTests`).

## Limitations

- Pricing figures are vendor marketing at one point in time and were not verified against a
  contract or invoice.
- The Bitquery assessment rests on its public documentation. Undocumented capabilities may exist;
  "not documented" is not "absent", and a sales conversation could change the answer.
- No vendor was trialled and no throughput was measured. Sustained-rate behaviour under a real
  Pump subscription remains unmeasured for every candidate.
