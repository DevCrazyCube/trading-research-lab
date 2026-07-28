# B7k — Decoder common-mode validation (preregistration)

**Frozen (document only):** 2026-07-28
**Status:** FROZEN before any result was computed. No decoded field value has been inspected.
**Owner:** Claude (Seq 70)
**Network cost:** **zero.** No RPC call. Offline only, against already-persisted artifacts.

## The limitation this addresses

Recorded in Seq 54 and carried forward unresolved through B7h, B7i and B7j:

> Both paths use the same pinned IDL and decode logic, so a mis-parsed event layout would be
> missed identically by both and still report agreement.

B7h and B7j each compared two **discovery** paths — `getBlock` full decode versus
`getSignaturesForAddress` + `getTransaction`. Those paths are independent on RPC method and on
provider, which is why B7h's cross-check was strong evidence about *recall*. They are **not**
independent on the decoder: both call the same `decode_events` against the same pinned IDL
(`idl_sha256 b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49`). A wrong field
offset, a wrong type width, or a wrong field order produces the *same* wrong answer on both sides,
and the comparison reports exact agreement.

Every recall result in this project is therefore conditional on a decoder that nothing has tested.

## What makes this test independent

The comparison is against evidence the **validator** produced, not evidence the IDL produced:

- **Resolved account keys** — the set of pubkeys the transaction actually touches.
- **`meta.preBalances` / `postBalances`** — lamport deltas per account.
- **`meta.pre/postTokenBalances`** — SPL token deltas per account.
- **`blockTime`** — the block's wall-clock stamp.

None of these derive from the pinned IDL. If the decoder assigns bytes to the wrong fields, decoded
pubkeys become effectively random 32-byte values and will not be members of the transaction's
account-key set; decoded `i64` timestamps will not equal `blockTime`. This is the property the test
exploits.

## Scope

**In scope.** The two frozen B7j event types, decoded from the B7j artifact
`research/b7j_positive_control_435564885_435565324.sqlite`
(SHA-256 `4ca3a1c93770559d7a97d99afe0b30599b42ee077a471e909684e4ecc2c1373b`):

- `CompleteEvent` — fields `user`, `mint`, `bonding_curve`, `timestamp`, `quote_mint`
- `CompletePumpAmmMigrationEvent` — fields `user`, `mint`, `mint_amount`, `sol_amount`,
  `pool_migration_fee`, `bonding_curve`, `timestamp`, `pool`, `quote_mint`

**Larger-n arm.** `TradeEvent`, decoded from the 439 full `raw_block` records in the same artifact.
This exists because the graduation arm has **n = 4**, which is too small to be load-bearing on its
own. Both arms are reported separately and never pooled.

**Out of scope, and prohibited as inferences in every outcome branch:**

1. **No recall claim.** This tests decoding, not discovery. It neither strengthens nor weakens B7h
   or B7j recall.
2. **No prevalence, performance, or cohort inference.**
3. **No cross-regime generalisation.** The artifact is one 439-slot window in one program regime.
4. **A PASS does not prove the IDL is correct.** It proves the decoder's field assignment is
   consistent with independent transaction evidence *for the fields checked*. Fields with no
   independent witness are explicitly listed as unvalidated rather than silently counted as passed.
5. **No claim about event types not decoded here.**

## Frozen checks

Each check is evaluated per event. Every check records a per-event result; no check may be dropped
after seeing results.

### Load-bearing checks

**C1 — pubkey account-key membership.**
For `CompleteEvent`: `user`, `mint`, `bonding_curve`.
For `CompletePumpAmmMigrationEvent`: `user`, `mint`, `bonding_curve`, `pool`.
For `TradeEvent`: `mint`, `user`.
Each must appear in the transaction's resolved account-key set. If any transaction resolves
addresses through an address lookup table (`meta.loadedAddresses` non-empty), its resolved set must
include those addresses; if they cannot be resolved offline, the event is recorded as
**UNRESOLVABLE** and counted separately — never as a pass.

**C2 — timestamp equals block time.** Decoded `timestamp` must equal the transaction's `blockTime`
exactly. A field-offset error moves an `i64` off a real Unix second and this fails immediately.

**C3 — exact payload consumption.** Each event payload must decode with **zero bytes remaining**.
Re-verified here per event rather than inherited from B0e.

### Reported, not load-bearing

**C4 — `quote_mint` consistency.** Must decode to a well-formed 32-byte pubkey and be identical
across all events in the window. `quote_mint` may legitimately be a mint the transaction never
touches, so membership is **not** required and its absence from account keys is **not** a failure.

**C5 — economic reconciliation (exploratory).** For `CompletePumpAmmMigrationEvent`, compare
`sol_amount`, `mint_amount` and `pool_migration_fee` against lamport and token balance deltas.
This is declared exploratory **in advance** because the exact accounting identity — which accounts,
net of which fees and rent — is not established by any existing evidence in this project. It is
reported as observation, and **a C5 mismatch does not fail the run**. Preregistering it as
load-bearing would mean discovering the identity from the data and then declaring the data
consistent with it, which is circular.

## Verdict rule

- **PASS** — every in-scope event satisfies C1, C2 and C3, with zero UNRESOLVABLE events.
- **FAIL** — any load-bearing check fails on any event. A failure is a finding, not an error: it
  would mean existing recall results rest on a mis-parsed layout, and it must be reported as
  prominently as a pass.
- **INCONCLUSIVE** — the in-scope event set is empty, or events are UNRESOLVABLE. An empty set is
  never a pass.

The graduation arm and the `TradeEvent` arm each receive their own verdict. **The graduation arm's
n = 4 is stated with its verdict in every branch**, so a PASS there is never read as more than it is.

## Known limitations, frozen in advance

- **C1 is a membership test, not an identity test.** It proves a decoded pubkey is one of the
  ~29 accounts the transaction touched. It does not prove it is the *right* one of those accounts.
  Two pubkey fields could be transposed and both would still pass C1. This is a genuine residual
  weakness and is **not** resolved by this design.
- **A systematically wrong IDL that is self-consistent would still pass.** If the published IDL
  itself misnames fields whose types and positions happen to align, no offline test can detect it.
- **`timestamp` shares a witness across events in the same transaction**, so C2's effective
  independent-sample count is the number of distinct transactions, not events.
- **n = 4 on the graduation arm.** The window contained two of each frozen type. This arm cannot
  support a statistical claim and does not attempt one.

## Execution order, frozen

1. This document is written and its SHA-256 recorded **before** the scanner is written.
2. The scanner is implemented and unit-tested against synthetic fixtures with **known** layouts,
   including a deliberately corrupted-offset fixture that must FAIL, so the instrument is shown to
   be capable of failing before it is pointed at real data.
3. Only then is it run against the artifact.
4. Results are reported whatever they are.
