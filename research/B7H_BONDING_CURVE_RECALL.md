# B7h — Bonding-curve history recall validation

Date: 2026-07-27  
Status: complete for the preregistered window; cohort remains burned

## Question

Does the B7e discovery path—fetching transaction histories from each launch's bonding-curve
address—recover every cohort `TradeEvent` in the fixed launch window
`[429998000, 430000000)`?

This is a recall check for the historical discovery path. It is not a profitability result, a
population estimate, or a validation of any abandonment threshold.

## Frozen method

The method was fixed before the full reference scan in
`research/B7H_BONDING_CURVE_RECALL_PREREGISTRATION.md`:

1. Decode every successful Pump `TradeEvent` for B7e cohort mints from all produced blocks in the
   half-open window.
2. Reconcile skipped slots independently with `getBlocks`.
3. Compare the block reference and B7e bonding-curve-history events bidirectionally by
   `(signature, mint, outer_instruction_index, inner_instruction_index, raw event payload)`.
4. Fail on any unresolved slot, decode error, missing event, or extra event.

Blocks were read from Solana mainnet RPC. The successful completion pass used the public primary
endpoint `https://api.mainnet-beta.solana.com`, accessed 2026-07-27. The pinned official Pump IDL
hash recorded in the database is
`b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49`.

## Verified result

- Slot window: 2,000 slots.
- Retrieved blocks: **1,996**.
- Independently verified ledger skips: **4**, slots `429998132`–`429998135`.
- Block-reference `TradeEvent`s: **13,861**.
- Bonding-curve-history `TradeEvent`s in the same window: **13,861**.
- Block minus history: **0**.
- History minus block: **0**.
- Decode errors: **0**.
- Distinct reference coordinates: **13,861**, equal to the reference row count.
- SQLite `PRAGMA integrity_check`: **ok**.
- Scanner exit code: **0**.

The bonding-curve history discovery path therefore had **100% observed event recall (13,861 / 
13,861)** in this fixed window, with exact payload equality and no false extras. This is a verified
window-specific fact, not a universal RPC guarantee. The evidence removes the load-bearing recall
caveat from the B7e/B7g silence analysis for this window.

## Transport correction

The first scan attempts failed because the scanner submitted all large full-block requests at once
and used 20-block JSON-RPC batches. Responses were roughly multi-megabyte per block; batching caused
HTTP 413, while unbounded outstanding futures pinned gigabytes in memory. These were transport
defects, not recall mismatches.

The corrected scanner defaults to one block per request, bounds outstanding futures, commits each
slot durably, does not retry HTTP 403/429, and stops fail-closed on sustained throttling. Eleven
focused tests pass through both direct-file and module execution. The frozen window, decoder, and
comparison key did not change.

## Reproducibility

Artifacts at completion:

- `research/b7h_recall_429998000_430000000.sqlite` — 11,255,808 bytes; SHA-256
  `8d737675fb58a9c431fe33adaae190e738648af58d0011a5821b886273074f2a`
- `scripts/b7h_bonding_curve_recall.py` — SHA-256
  `b62a1c16e98aadec2a4b1b3721daad9847999060e1ba9d7aff63f7d9b0a7edb1`
- `tests/test_b7h_bonding_curve_recall.py` — SHA-256
  `db47d4a79176019b7e276d4f4073244c4fce24eef63966058dee4c0466476176`
- preregistration — SHA-256
  `3275fc33d422437e2f16f014d578d4c73bdc32b0bfe52389b21b5cc5bd93cd47`

Re-run the focused verification with:

```bash
python tests/test_b7h_bonding_curve_recall.py
python -m unittest tests.test_b7h_bonding_curve_recall
```

## Independence of the two compared paths (added at audit)

The two sides of this comparison are independent on two axes, which is stronger than the result was
originally stated to be:

- **Different RPC methods.** The reference set comes from `getBlock` full-block decoding; the
  history set comes from `getSignaturesForAddress` on bonding-curve addresses followed by
  `getTransaction`. These read different provider indexes, so an index-level omission on one side
  would not be mirrored on the other.
- **Different providers.** The B7h reference pass ran against the **public** endpoint
  `api.mainnet-beta.solana.com` (the credentialed endpoint was throttled). The B7e history was
  built against the **credentialed** endpoint (`endpoint_ref = configured-mainnet` in the
  lifecycle database metadata). Agreement is therefore cross-provider, which rules out a
  single-provider blind spot for this window.

**But the paths are NOT independent on a third axis: the decoder.** Both sides used the same pinned
IDL (`idl_sha256 = b90bc471…8e49`, identical in both databases) and the same decode logic. A
decoder-level blind spot — for example a `TradeEvent` shape the decoder fails to recognise, or a
program version whose layout it mis-parses — would be **common-mode**: both paths would miss the
same events identically and this test would still report perfect agreement.

So the correct reading is: *discovery* recall is validated cross-provider and cross-method;
*decoding* completeness is not tested by this comparison and rests on the pinned IDL being correct
and complete for this window's program version.

## Limits and next action

- The result validates one 2,000-slot historical window and one pinned program/IDL regime. It does
  not prove provider completeness in every era or after future program changes.
- **Decoder blind spots are not excluded** — see the independence section above.
- The B7e/B7g cohort remains burned from model training, validation, and test.
- `D_dead` remains unset. Recall validation makes the measured resumption curve trustworthy for
  this window; it does not create a natural threshold where none was observed.
- Graduation/migration anchors and a disjoint preregistered validation cohort remain required
  before adopting lifecycle labels.

