# B2c — Non-SOL Quote-Pair Verification

Run: 2026-07-27, approximately 13:15–13:25 UTC. Author: Claude.
Two samples near slots 435,543,285 and 435,543,407. Current program version (2026-07-15 deploy).

Read-only mainnet RPC plus offline integer arithmetic. No keys, no signing, no transactions.
Script: `scripts/b2c_quote_pair_check.py`. IDL: pinned `research/pump_idl_9c82f61.json`.

Purpose: close the limitation carried since B2a — every curve and arithmetic result so far was
tested against the `sol_*` fields, leaving the `quote_*` fields unverified.

## F28 — On SOL pairs, `quote_*` fields mirror `sol_*` exactly (verified fact)

Across **337 decoded TradeEvents** (159 + 178 in two samples), every SOL-quoted event satisfied:

| Check | Result |
|---|---:|
| `sol_amount == quote_amount` | **178 / 178** |
| `virtual_sol_reserves == virtual_quote_reserves` | **178 / 178** |
| `real_sol_reserves == real_quote_reserves` | **178 / 178** |

Zero divergences.

**Consequence:** every result established in B2a and B2b — reserve continuity, the sell formula,
and the official buy formulas — applies **identically to the `quote_*` fields for SOL-quoted
trades**, because the two field sets carry the same integers. The B2a limitation is closed for the
SOL case, and it is closed by measurement rather than by assuming the fields are aliases.

## F29 — Non-SOL quote pairs were not observed and remain unverified (negative result)

| | count |
|---|---:|
| TradeEvents decoded | 337 |
| `quote_mint == 11111111111111111111111111111111` (native SOL sentinel) | **337** |
| Non-SOL quote mints | **0** |

By the rule of three, 0 observations in 337 gives a 95% upper bound of roughly **0.9%** — non-SOL
quote pairs are under about 1% of current bonding-curve trade traffic. That is an upper bound on
*frequency in this window*, not evidence that they do not exist: the IDL carries `add_quote_mint`
and `remove_quote_mint` instructions and four dedicated `*_quote_*` event fields, so the capability
is plainly real and deliberate.

**The genuinely non-SOL arithmetic paths therefore remain UNVERIFIED.** Random block sampling is
the wrong instrument at this rate — finding a usable chain of consecutive events for one non-SOL
mint would take thousands of blocks.

**Practical consequence, which is favourable:** `PLAN.md` already scopes the initial tradable
regime to SOL-paired bonding-curve launches. At <1% of traffic, non-SOL is not on the critical
path and should not block Phase 1 or Phase 2. It must simply not be *silently* mishandled — a
decoder meeting a non-SOL `quote_mint` should fail visibly rather than assume the SOL mirroring
of F28 holds.

## Limitations

- Two windows of 10–14 blocks each on one day. Pump traffic is non-stationary (F9), so the <1%
  bound describes this window, not a stable base rate.
- F28's mirroring is measured on the current program version only. Given the ~13-day upgrade
  cadence, it must not be assumed across version boundaries.
- The mirroring result means the SOL and quote fields are *numerically identical* here. It does not
  prove they are the same field internally, nor that they will remain equal under a future version.

## Follow-ups

1. To find non-SOL pairs efficiently, stop sampling blocks. Decode the `add_quote_mint` /
   `remove_quote_mint` instruction history to learn which quote mints are registered and when,
   then search targeted slot ranges for those mints. That converts a needle-in-haystack scan into
   a directed lookup.
2. Add a fail-visible assertion to the decoder: a `quote_mint` other than the native sentinel must
   raise rather than silently reuse SOL-path assumptions.
3. Re-check F28's mirroring at each program-version boundary.
