# B7a — Mayhem Mutability, Lifecycle Anchors, and the Helius Rate Ceiling

Run: 2026-07-27, approximately 15:40–16:00 UTC. Author: Claude.
RPC via `SOLANA_RPC_URL` (registered Helius endpoint). **The key is never printed or persisted.**
Read-only. No signing, no transactions.

Scripts: `scripts/b7a_lifecycle_scan.py`. IDL: pinned `research/pump_idl_9c82f61.json`.

Answers the open questions raised in `docs/DEFINITIONS.md` §6.

## F42 — The Helius ceiling is ~7.8 `getTransaction`/s, 3.1× the public endpoint (verified)

| Concurrency | ok/s | errors | p50 |
|---:|---:|---:|---:|
| 4 | **7.8** | 0 | 351 ms |
| 16 | 7.9 | 72 | 961 ms |
| 32 | 5.9 | 169 | 1883 ms |

Best clean rate is **7.8/s at concurrency 4**; pushing past that trades errors for nothing, and
concurrency 32 is *slower* than 4. Compare B6J's public-endpoint measurement of 2.5/s.

**This revises F41 without overturning it.** Against B6h's measured demand:

| Demand | Rate | Public (2.5/s) | Helius (7.8/s) |
|---|---:|---:|---:|
| Successful Pump transactions | 12.0/s | 21% | **65%** |
| All Pump-mentioning transactions | 168.5/s | 1.5% | 4.6% |

Cost-level enrichment of *every* successful trade market-wide is still out of reach, so
`PLAN.md`'s "complete auditability" remains unmeetable market-wide. But cohort work is now **3.1×
cheaper**, and 65% coverage changes what a bounded cohort can afford.

## F43 — `toggle_mayhem_mode` is a GLOBAL switch, not per-token (verified from IDL)

This was `docs/DEFINITIONS.md`'s sharpest open question, because a per-token toggle would have
invalidated launch-time Mayhem exclusion and let B2a's F17 contaminate a cohort selected as
non-Mayhem.

```
toggle_mayhem_mode   disc 01096fd0641fffa3
  global            [w] PDA
  authority         [w,s]
  event_authority   [-] PDA
  program           [-]
  args: enabled: bool
```

It writes only to the **global config PDA**. No `bonding_curve` account appears, so it cannot flip
an individual live token's `is_mayhem_mode`.

**Consequences:**
1. **Launch-time Mayhem exclusion is valid per token.** `is_mayhem_mode` is on `CreateEvent`, is
   knowable at t=0, and no instruction rewrites it for an existing curve. Cohort selection can
   exclude Mayhem with no lookahead.
2. **But the launch *population* is time-varying.** An admin flipping the global switch changes
   whether new launches are Mayhem, so the non-Mayhem cohort's composition shifts over calendar
   time. That is a **regime covariate**, and it independently justifies the existing decision to
   record Mayhem activity even while excluding it from trading.

## F44 — F17's mechanism is now named: `set_mayhem_virtual_params` (verified from IDL)

B2a inferred that Mayhem curves are mutated outside trading, from the field pattern plus the IDL
surface, and explicitly flagged the causal claim as unconfirmed. The account list confirms it:

```
set_mayhem_virtual_params   disc 3da9bcbf99952a61
  sol_vault_authority  [w,s] PDA
  mayhem_token_vault   [w]   PDA
  mint                 [-]
  global               [-]   PDA
  bonding_curve        [w]   PDA   <-- writable, per-token
  token_program        [-]
  event_authority      [-]   PDA
  program              [-]
  args: none
```

A **writable `bonding_curve`** on a per-mint instruction is exactly the mechanism F17 predicted.
Mayhem curves therefore are not reconstructible from the trade stream alone unless this
instruction is also captured and decoded.

By contrast, **`set_virtual_quote_reserves` touches only `global`** and takes
`initial_virtual_quote_reserves` — it sets the starting point for *new* launches and does **not**
mutate live curves. F17's cause is narrowed to `set_mayhem_virtual_params` alone.

## F45 — `set_params` confirms global fee mutability (verified from IDL)

```
set_params   disc 1beab2349302bb8d   (global [w], authority [w,s])
  args: initial_virtual_token_reserves, initial_virtual_sol_reserves,
        initial_real_token_reserves, token_total_supply, fee_basis_points,
        withdraw_authority, enable_migrate, pool_migration_fee,
        creator_fee_basis_points, set_creator_authority, admin_set_creator_authority
```

`fee_basis_points`, `creator_fee_basis_points`, `pool_migration_fee` and `enable_migrate` are all
settable at any time by the authority. This **confirms C5's requirement** for a versioned
`program_config` timeline: the 95/30 bps observed in F12 is a point-in-time value, and any quote
or cost computation must read the configuration active at the relevant slot.

`enable_migrate` is notable — migration can apparently be **disabled globally**, which bears
directly on the T1b question below.

## Empirical scan — 220 blocks, 220/220 retrieved

Roughly 88 seconds of chain. All 220 blocks retrieved with zero failures, which is itself a
contrast with the public endpoint (F26: 0.35 blocks/s and heavy loss).

### F46 — T1b is real: completion and migration are separate transactions (verified, n=1)

| Event | Count |
|---|---:|
| `CompleteEvent` | 1 |
| `CompletePumpAmmMigrationEvent` | 1 |
| `CompleteEvent` **with migration in the same transaction** | **0** |

The one completed token (`4R2Sxa8j219C8ydPoi1TDAgDFBHoWA7zMv8XyFpvpump`) had no migration event in
its transaction, and the single migration event arrived via a separate `migrate_v2` at slot
435,565,104.

**`DOCUMENTATION.md` describes migration as automatic and irreversible following graduation. That
is not what the chain shows.** Completion and migration are distinct transactions, so a token
demonstrably passes through **T1b — completed, not yet migrated**. Combined with F45's finding that
`enable_migrate` is a globally settable flag, the interval is not merely a scheduling artefact:
migration is a separate, disableable action.

This is the state where the bonding curve is closed and the PumpSwap pool may not yet exist —
precisely where exit liquidity would vanish. **n=1**, so the *duration* of T1b is unmeasured and
this must not be treated as a distribution. But its existence is established, and the
documentation claim needs correcting.

### F47 — Launch rate ≈ 0.23/block, and all launches use `create_v2` (verified)

| | |
|---|---:|
| `CreateEvent` observed | 50 in 220 blocks (**0.23/block**) |
| Projected | **≈ 49,700 launches/day** |
| `create_v2` outer instructions | 50 |
| `create` (v1) outer instructions | **0** |

Unlike `buy`/`sell`, where F6's correction showed v1 and v2 coexisting, **`create_v2` has fully
displaced `create`** in this window. A launch-detection path built on the v1 discriminator alone
would currently find nothing.

### F48 — Launch attributes are all knowable at t=0 (verified)

| Attribute | Distribution |
|---|---|
| `is_mayhem_mode` | **45 false / 5 true** (10% Mayhem) |
| `is_cashback_enabled` | 34 true / 16 false |
| `quote_mint` | **50/50 native SOL sentinel** |

All three are carried on `CreateEvent`, so cohort selection can filter on them **with no
lookahead**. The 10% Mayhem share means a non-Mayhem cohort discards roughly a tenth of launches —
material, and the exact figure will move as the global switch (F43) is toggled.

Zero non-SOL launches, consistent with B2c's <1% bound now measured at launch as well as at trade.

### F49 — Curve-mutating admin instructions were not observed

`toggle_mayhem_mode`, `set_mayhem_virtual_params`, `set_virtual_quote_reserves` and `set_params`:
**zero occurrences** in 220 blocks. Only one `migrate_v2` fired.

**Absence over ~88 seconds is not evidence of rarity at research timescales.** These are admin
operations; F45 shows `set_params` can change fee rates globally at any moment, and F44 shows
`set_mayhem_virtual_params` can rewrite a live Mayhem curve. Both must be *captured and alarmed on*
even though neither appeared here. A standing monitor is the right response, not an assumption of
rarity.

### Cohort sizing, re-grounded

With F42's 7.8 `getTransaction`/s ≈ **674,000 requests/day**, and F47's **≈49,700 launches/day**,
an exhaustive launch window is now sizeable rather than speculative: a one-hour exhaustive window
contains roughly **2,070 launches**. Whether their complete histories fit inside 674k requests/day
still depends on the per-token lifetime distribution, which remains unmeasured and, per
`docs/DEFINITIONS.md`, remains undefined until `D_dead` is frozen.

## Limitations

- F43–F45 are read from the pinned IDL. The IDL is authoritative for account structure and
  argument lists; it does not tell us how often these instructions are actually invoked, nor
  whether the deployed bytecode matches the published IDL. Frequency is an empirical question.
- The throughput figures are one endpoint, one plan tier, one time of day, ~8 requests per
  concurrency step. Helius plan limits are not published per-tier in a form we verified.
- Demand figures come from a single 90-second B6h window; Pump traffic is non-stationary (F9).
