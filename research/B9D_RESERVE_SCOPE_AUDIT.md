# B9d reserve materialization scope audit

**Date:** 2026-07-30  
**Status:** interim offline result; B9d collection is still active  
**Network calls:** zero; artifacts opened read-only

## Result

**Verified fact:** the apparent reserve discontinuities were all on incidental, out-of-cohort Pump
curves bundled into transactions fetched for a B8b curve. They are not evidence that B9c omitted
transactions from a frozen cohort curve history.

At a fixed read-only replay start of 47,181 preserved bodies:

| Scope | Decoded Pump `TradeEvent`s | Consecutive four-field discontinuities |
|---|---:|---:|
| Frozen non-Mayhem B8b cohort | 45,691 | **0** |
| Incidental Pump mints absent from B9a | 95 | **31** |

All 31 discontinuities were among the incidental events. Their transactions were present only
because a separate cohort address selected the bundled transaction. B9c never enumerated the
incidental curves, so their partial paths are expected and must not be materialized.

## Reproduction

1. Load the 1,136 frozen non-Mayhem `mint → bonding_curve` pairs from the pinned B9a `outcome`
   table.
2. Stream preserved B9d bodies in canonical coordinate order.
3. Decode and parent Pump `TradeEvent`s exactly against the pinned IDL.
4. Derive each event's four-field pre-state from its own signed quote/token delta and compare it to
   the previous observed post-state for that mint.
5. Count results separately by membership in the frozen B9a mint set.

**Verified fact:** every apparent gap changed virtual quote, virtual token, real quote, and real
token together. This confirms the arithmetic signal but does not place an out-of-cohort curve into
scope.

## Address-lookup hypothesis

**Verified fact:** a separate 46,979-body replay found 45,545 observed Pump trades whose bonding
curve resolved from static keys and **40** whose curve resolved from loaded writable addresses.
Therefore address-lookup-table use is not categorically absent from B9c's address-index results.

**Open question:** provider/index recall for lookup-loaded addresses remains unproven for this
window, exactly as preregistered in §8a. The local evidence neither proves universal recall nor
identifies an ALT omission. The frozen branch still forbids retrofitting a post-outcome recall
experiment into B9d.

## Implementation consequence

`reserve_observation`, reserve-chain failures, and reserve balance reconciliation are restricted to
the frozen non-Mayhem B8b mint/curve identity. An in-scope event naming a different curve fails
closed. Incidental Pump instructions/events remain preserved in the canonical `instruction` table;
only their deliberately incomplete reserve paths are excluded.

This correction does not establish full address-index exhaustiveness and makes no profitability or
model-performance claim.
