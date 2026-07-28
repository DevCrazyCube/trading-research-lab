# B7j — Graduation-Anchor Positive-Control Preregistration

**Frozen (document only):** 2026-07-27
**Status:** FROZEN and **EXECUTED**. Conditionally approved by Codex 2026-07-27 21:44:30Z; the run
completed and passed. Result: `research/B7J_POSITIVE_CONTROL.md`.
**Author:** Claude. Envelope construction and scope corrections: Codex review.

> **Status-line correction (2026-07-28).** This line previously read *"awaiting Codex approval. No
> RPC call has been made. No scanner exists."* That was accurate only until the approval and run,
> and was left stale afterwards — a document asserting no scanner exists while a completed scanner
> and a passed run sat beside it. The freeze *content* below is unchanged and was not reopened; only
> this status line was wrong. Frozen content hash at time of execution:
> `4a5c344522883e6bba0c8ef4d4e8be3b8b509bc3730a6b2419aae73b70a333d1`.

## Why a positive control, and why B7i was not run

B7i preregistered the graduation-anchor cross-check over the 2,000-slot launch window. It was
**reviewed but not authorised**: expected information value too low. That window is ~13 minutes at
launch and B7e observed zero graduation events across 23 days, so the reference set would almost
certainly be empty — and B7i's frozen vacuity rule makes an empty reference set `INCONCLUSIVE`,
never a pass. A test that cannot produce positive instances cannot distinguish a working detector
from a broken one.

B7j exercises the detector against a window **deduced to contain known positives**, fixed **without
searching alternative boundaries**. The selection is explicitly **outcome-positive** — that is what
a positive control is.

## Frozen window — a conservative envelope, derived not searched

`research/B7A_LIFECYCLE_AND_MAYHEM.md` records two facts that together fix a window without any
lookup:

1. Both positives (one `CompleteEvent`, one `CompletePumpAmmMigrationEvent`) occurred within **one
   contiguous 220-block scan**.
2. The migration event's slot is **S = 435,565,104**.

Any contiguous 220-slot window `[a, a+220)` containing `S` must satisfy `a ∈ [S-219, S]`. The union
of all such windows is therefore

```
[S-219, S+220)  =  [435,564,885, 435,565,324)      439 slots
```

**This envelope necessarily contains every slot of whatever 220-block window B7a actually used**,
and hence both documented positives — whatever B7a's exact boundaries were. It is derived
arithmetically from two recorded numbers, so it was fixed **without searching alternative
boundaries**: no candidate window was inspected and rejected in favour of a better-looking one.

**The selection is nevertheless explicitly outcome-positive.** The envelope was chosen *because*
positives are known to lie inside it. That is the defining property of a positive control, and it
is stated here rather than softened.

This construction also **removes the coordinate blockers** in the previous draft. B7a's truncated
signatures, missing instruction indices and missing payloads are no longer needed — the reference
path rediscovers them from the envelope directly.

## Design — two independent paths

**Reference (block path).** Scan **every retrievable block** in the envelope. Decode **all** events
in the frozen two-event set, via the Anchor CPI-tag path against the pinned IDL
`research/pump_idl_9c82f61.json` (`idl_sha256 = b90bc471…8e49`).

**No pre-known fixture mints are used.** The reference path is not told what to look for beyond the
two event types; it discovers every instance in the envelope. Each decoded reference event supplies
its own `mint` **and** `bonding_curve` — both fields are present on both event types in the pinned
IDL — which is what the candidate path then needs.

**Endpoints are pinned per path, and fallback is forbidden.** The reference path uses the **public**
endpoint used by B7h (`api.mainnet-beta.solana.com`); the candidate path uses the **credentialed**
endpoint used by B7e (`endpoint_ref = configured-mainnet`). This preserves the cross-provider and
cross-method independence that made B7h's result meaningful. If either path is unavailable or
throttled, the run is **FAIL or INCONCLUSIVE** — there is **no silent provider fallback**, because
falling back would collapse both paths onto one provider and destroy the independence the test
depends on.

**Candidate (address-history path).** For each `bonding_curve` supplied by a reference event, query
that address's history via `getSignaturesForAddress`, fetch with `getTransaction`, decode, and
filter to the frozen window, the frozen event set, and that event's `mint`. This is the identical
discovery mechanism B7e relied on and whose recall B7h validated **for `TradeEvent` only**.

**Candidate pagination and de-duplication are frozen.** Each **distinct** reference
`bonding_curve` is queried **once**. Its history is paginated backwards until a returned page
**proves** it has crossed below the window start — reaching a page whose oldest entry has
`slot < window_start`, or an empty page. A pagination cap, an ambiguous boundary, or any fetch
failure **fails visibly**; it is never treated as "history exhausted". Decoded candidate events are
then **unioned and de-duplicated on the canonical key** before comparison, and only then filtered by
window, frozen event set, and the reference-discovered mint set. Filtering per reference event
instead would duplicate rows whenever one curve supplies several events.

**Extra positives are included, never dropped.** If the envelope contains graduation events beyond
the two B7a documented, they enter the comparison on the same terms. Discarding them would convert
a clean test into a curated one.

## Frozen event set

Exactly two, discriminators **derived, never hardcoded**, as `sha256("event:" + name)[:8]` against
the pinned IDL:

- `CompleteEvent`
- `CompletePumpAmmMigrationEvent`

## Frozen canonical comparison key

```
(slot, transaction_index, signature, outer_instruction_index, inner_instruction_index,
 event_ordinal, mint, event_payload_base64)
```

`slot` and `transaction_index` are included so the key carries canonical chain ordering, not only
intra-transaction position.

**Canonical key amendment (frozen before the run).** `getTransaction` does not return a
transaction's index within its block, so the **candidate path cannot supply `transaction_index`**.
It is therefore **excluded from the equality projection by explicit rule**, and the projection used
for bidirectional comparison is

```
(slot, signature, outer_instruction_index, inner_instruction_index, event_ordinal, mint,
 event_payload_base64)
```

`transaction_index` is still recorded on the reference side for canonical ordering and is reported,
but it is never silently equated across paths. This amendment is stated here rather than left as a
code-level divergence from the freeze. `event_ordinal` is assigned in decode order within each
`(signature, outer, inner)` group on both sides and is never defaulted. Payload comparison is
**byte equality** on the base64 payload, not field-wise equality.

## Pass / fail rules — frozen before any lookup

1. **PASS** requires **all** of:
   - at least **one reference instance of each** of the two event types (a run that finds only one
     type does not pass — it has exercised only half the detector);
   - **full slot accounting** across the envelope: every slot either retrieved or independently
     reconciled as skipped via `getBlocks`;
   - **zero** decode errors and zero fetch errors;
   - **exact bidirectional equality** of reference and candidate sets on the **frozen equality
     projection** defined in the canonical key amendment above (i.e. excluding
     `transaction_index`), not on the full canonical key.
2. **FAIL** — any missing event, extra event, payload mismatch, ordinal mismatch, unexplained slot,
   decode error, or fetch error. Fails visibly; no conclusion published.
3. **INCONCLUSIVE** — the envelope yields no instance of one or both event types. Reported as such;
   the graduation-anchor recall question stays open.

**Decode-error semantics.** A CPI-tagged inner instruction whose discriminator equals one of the two
frozen discriminators but whose payload fails to decode, or decodes with trailing bytes, is a
**visible decode error and fails the run**. Any other discriminator — including `TradeEvent`, other
Pump events, or discriminators absent from the pinned IDL — is **out of scope and skipped
silently**. Policing unrelated events would fail the run for reasons unconnected to graduation-anchor
recall.

## Retrospective selection — stated plainly

The **envelope** is derived arithmetically, but the knowledge that positives exist inside it comes
from having already observed them. This is a **positive control**: it deliberately targets a region
known to contain the phenomenon in order to check the instrument fires. That is valid for measuring
**detector recall** and invalid for anything else.

### Prohibited inferences (binding in every outcome branch)

1. **No prevalence inference.** B7j says nothing about how often tokens graduate or migrate. The
   window was chosen because it contains positives.
2. **No performance inference.** Nothing here supports any claim about returns, exit liquidity, or
   strategy viability.
3. **No cohort inference.** The envelope sits ~5.5M slots after the B7e launch window, so these are
   **not B7e cohort members**. A pass says nothing about whether any of the 200 cohort tokens
   graduated, and nothing about B7e's zero-anchor observation through cutoff `435,570,000`.
4. **No same-token or T1b inference.** Whether a `CompleteEvent` and a migration event in this
   envelope belong to the same mint is **out of scope and prohibited**. Detector recall is measured
   **per event type**; the T1a→T1b transition is a separate question requiring a separate design.
5. **No generalisation across regimes.** One program version, one 439-slot window.

## Common-mode limitation (carried forward, unresolved)

Both paths use the **same pinned IDL and the same decode logic**. A decoder blind spot — an
unrecognised or mis-parsed graduation-event layout — is **common-mode**: both paths would miss it
identically and the comparison would still report agreement. B7j tests *discovery* recall, not
*decoding* completeness. No evidence in this project addresses that, and B7j does not change it.

## Audit persistence — frozen

The run must persist enough to be re-audited without re-querying:

- **every retrieved reference block**, stored compressed and keyed by slot — not only
  event-bearing transactions, because reference *completeness* cannot be audited from a subset;
- **every candidate history page** returned by `getSignaturesForAddress`, stored compressed and
  keyed by `(bonding_curve, page_index)` — page counts alone cannot reproduce discovery;
- **every in-window candidate transaction fetched, including those that decode zero frozen
  events** — otherwise "we looked there and found nothing" is not auditable;
- **metadata**: pinned IDL SHA-256, the frozen window bounds, and an opaque `endpoint_ref` per path
  (**never a URL or credential**);
- **per-slot status** across the envelope, including reconciled skips;
- **every error**, retained rather than summarised away;
- a **deterministic summary** — stable ordering and stable serialisation, so the artifact hash is
  reproducible from the same inputs.

## Gates

Read-only RPC only, and none yet performed. No signing, no spending, no deployment, no live or
devnet transactions. The endpoint is sourced silently from the ignored `.env` and never printed or
persisted. B7a, B7e, B7h and B7i artifacts are inputs and will not be modified.
