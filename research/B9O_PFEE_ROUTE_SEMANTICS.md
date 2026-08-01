# B9o — `pfee` on the direct Pump route: what it is, and why its ABI does not gate the cost model

Measured 2026-08-01 over the frozen artifact. Artifact read-only, **zero network calls**, collector
not restarted, no simulator implementation started.

## What was asked, and what actually settles it

Handoff 58 asked for `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ` to be pinned from an
authoritative versioned source, because B9n showed it executes inside **100% of Pump trades** and
its ABI was unpinned — the last route-wide gap.

**Its instruction ABI is still not pinned, and this document does not pin it.** What it establishes
instead is stronger for the cost model and weaker as a general claim: on the direct Pump route,
`pfee` **cannot move lamports at all**, so its internal semantics cannot affect wallet cost. That is
settled from a source already pinned in this repository, with no network access.

## The authoritative binding, from an already-pinned source

`research/pump_idl_9c82f61.json` — the pinned Pump IDL, already SHA-256 verified by the loader —
declares the fee program on **all six** trade instructions, by hard-coded address:

| instruction | `fee_config` | `fee_program` |
| --- | --- | --- |
| `buy` | `writable = False` | `writable = False`, address `pfeeUxB6…` |
| `buy_v2` | `writable = False` | `writable = False`, address `pfeeUxB6…` |
| `buy_exact_sol_in` | `writable = False` | `writable = False`, address `pfeeUxB6…` |
| `buy_exact_quote_in_v2` | `writable = False` | `writable = False`, address `pfeeUxB6…` |
| `sell` | `writable = False` | `writable = False`, address `pfeeUxB6…` |
| `sell_v2` | `writable = False` | `writable = False`, address `pfeeUxB6…` |

`fee_program` is declared with a **fixed address**, not a caller-supplied account, so the identity
is pinned by the IDL rather than inferred from traffic.

## Why non-writable is the whole argument

The Solana runtime permits an instruction to modify an account's lamports **only if that account is
marked writable in the transaction message.** Both accounts the fee CPI receives are declared
non-writable. Therefore no execution of `pfee` reachable from a Pump trade can debit or credit
anything, whatever its instruction set turns out to be.

This is a **structural** guarantee about the route, not a statistical generalisation from observed
traffic — which matters, because a "we never saw it move lamports" claim would be exactly the kind
of sampled agreement this project has been burned by before.

## Corroboration from the artifact

Measured over 6,000 transactions:

- **6,011** `pfee` instructions carrying discriminator `e7257e55cf5b3f34`.
- Every one carries exactly **2 accounts**: the fee-config PDA (`8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt`
  for Pump; `5PHirr8j…` for PumpSwap) and the calling program.
- **12,022 of 12,022** account-balance observations on those accounts are **unchanged**. Zero
  exceptions.
- Invoked by Pump (`6EF8rrec…`) 5,913 times; by PumpSwap 45; the rest are not on our route.
- Stack heights 2–3, i.e. always a CPI beneath the trade instruction, never top-level.

Payload shape, 34 bytes: `e7257e55cf5b3f34` ‖ `u8` ‖ `u128` ‖ `u64` ‖ `u8`. The `u128` is consistent
with `FeeTier.market_cap_lamports_threshold` in the pinned IDL, i.e. a market-cap-keyed fee-schedule
lookup. **That reading is not asserted as semantics** — it is shape agreement, which this project
does not accept as identification. It is recorded only because it is consistent with the
`FeeConfig` type the IDL already defines:

```
FeeConfig { bump: u8, admin: pubkey, flat_fees: Fees,
            fee_tiers: Vec<FeeTier>, stable_fee_tiers: Vec<FeeTier> }
FeeTier   { market_cap_lamports_threshold: u128, fees: Fees }
Fees      { lp_fee_bps: u64, protocol_fee_bps: u64, creator_fee_bps: u64 }
```

## Scope limit, stated because it is easy to over-read

This result covers **the direct Pump route only.** On routed transactions `pfee` also appears with
11, 13, 19 and 20 accounts, invoked by `EWucdoZf…`, `BSfD6SHZ…` and PumpSwap. Those account lists
are not declared by the Pump IDL, their writability is not established here, and **`pfee` may well
move lamports on those paths.** Nothing in this document says otherwise. It is not needed, because
those paths are not ours.

## A correction to the previous handoff

B9n reported that the 92 direct-route residuals were *"consistent with program-owned movement by
`pfee`."* **That is now refuted.** `pfee` cannot move lamports on the direct route, so it cannot be
their cause. The residuals must originate in accounts that *are* writable on that route — Pump's own
program-owned accounts. This narrows the open question rather than closing it, and the earlier
sentence should not be relied on.

## What `pfee`'s ABI would still be needed for

Not for wallet cost. It would be needed to **compute the fee schedule for a counterfactual trade**
— our constructed order at a decision instant. Measured across the full population, that dependency
is currently inert in this window:

- `fee_basis_points` is **95 on all 93,448 observations** — one value, no tier variation observed.
  So no tier lookup is exercised in-window and the protocol rate is a constant for pricing purposes
  **within this window only**.
- The remaining 30 bps goes to **either** the creator **or** cashback, never both:
  `creator=30, cashback=0` on 36,745 and `creator=0, cashback=30` on 56,703 (plus one observation
  with `buyback=0`).

A trade priced at a market cap that crosses a tier threshold, or outside this window, would need the
tier table — which lives in the `FeeConfig` account this project holds no snapshots of. That is a
**named, bounded gap**, not a closed one, and it is recorded in the cost contract.

## Verdict

- `pfee`'s instruction ABI: **NOT pinned.** Unknown discriminator behaviour stays fail-closed.
- `pfee`'s ability to affect direct-route wallet cost: **excluded**, from the pinned Pump IDL's
  non-writable declarations plus the runtime's writability rule, corroborated 12,022/12,022.
- Consequence: the `pfee` gap does **not** block the direct-route cost contract. The fee-tier table
  remains an open dependency for pricing outside the observed window.

No profitability claim is made and nothing here is a trading recommendation.
