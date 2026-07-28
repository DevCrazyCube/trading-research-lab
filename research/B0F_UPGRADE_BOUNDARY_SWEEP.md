# B0f/g — Pump Upgrade-Boundary Traffic Sweep

Run: 2026-07-27. Read-only `getBlock` calls against Solana's public mainnet RPC.
Scripts: `scripts/b0f_boundary_sweep.py`, `scripts/b0g_boundary_neighbors.py`.

## Method

For every one of the 54 verified Pump loader `Upgrade` transactions, fetch its block, locate the
upgrade transaction in ledger order, and classify Pump outer and inner instruction discriminators
before versus after it. This gives an exact temporal cut inside the upgrade slot. For all 15
boundaries in 2026, widen the sample with the complete preceding and following blocks.

Evidence:

- `research/b0f_boundary_sweep_all_2026-07-27.jsonl` — all 54 same-block cuts.
- `research/b0f_boundary_sweep_2026-07-27.jsonl` — 15 same-block cuts for 2026.
- `research/b0g_boundary_neighbors_2026-07-27.jsonl` — 2026 cuts plus adjacent blocks.

## Verified results

All 54 upgrade blocks were retrieved and all 54 upgrade signatures were found, with zero RPC or
matching errors. The blocks contained 73,919 transactions. Same-block cuts observed 548
Pump-touching transactions before upgrades and 219 after. Only 29 of 54 boundaries had Pump
traffic on both sides, demonstrating that a same-block discriminator-set difference is generally
underpowered and must not be called a semantic change.

Adding one neighboring block to each side gave non-zero Pump observations on both sides of every
2026 boundary. This improves coverage but does not solve the rare-instruction problem: absence in
a short traffic window is not proof that an instruction was removed.

## July 15 boundary

The latest boundary has the strongest local sample: 317 Pump-touching transactions in the widened
pre-window and 288 in the post-window. `buy_exact_sol_in` dominated both (295 before, 276 after).
The current-IDL instruction `collect_creator_fee_v2` appeared once after and zero times before.
This is a **candidate interface-boundary signal**, consistent with the upgrade, but not standalone
proof that the instruction was introduced at this boundary: a rare pre-existing instruction can
be absent by chance.

## What this establishes

1. Public `getBlock` retrieval is sufficient to inspect all observed upgrade slots.
2. Loader-order cuts can date an observed first use but cannot prove program capability from
   absence in small traffic windows.
3. Discriminator traffic is highly non-stationary; interface inference needs larger windows,
   official IDL/artifact history, or deliberately submitted simulation—not one-block presence.
4. The full sweep should be treated as a candidate-boundary generator, not a regime oracle.

## Next

The higher-value experiment is now B2: chain consecutive `TradeEvent`s for one mint and reproduce
the integer curve transition. This tests whether event-only backfill supports the execution
simulator. Boundary classification can then be revisited with wider windows only where decoder
failures or IDL history identify a concrete change.
