# B2b — Official Buy Formula Validation

Run: 2026-07-27. Read-only mainnet RPC plus exact integer arithmetic.

## Source

The pinned official Pump IDL (`research/pump_idl_9c82f61.json`, upstream commit
`9c82f61cb711b044a17f770ab8ce9f9bdf78f333`) documents `buy_exact_sol_in` arithmetic explicitly:

```
tokens_out = floor((net_quote - 1) * virtual_tokens
                   / (virtual_quote + net_quote - 1))
```

This is not algebraically identical under integer rounding to the naive B2a expression
`virtual_tokens - floor(k / (virtual_quote + net_quote))`. That explains B2a's small residuals.

`buy` and `buy_v2` are exact-token instructions (`amount`, `max_sol_cost`), whereas
`buy_exact_sol_in` and `buy_exact_quote_in_v2` are exact-input instructions. They must not be
validated with one common directional formula.

## Test

`scripts/b2a_curve_chain_check.py` now retains its original naive T2 result and adds T3 using
instruction-specific formulas. Two new live samples were taken:

- 12 blocks: 132 events, with 20 multi-event mint chains.
- 6 blocks: 47 events, with 10 multi-event mint chains.

For exact-input buys, T3 uses the official IDL equation above with the event's reserve-changing
`sol_amount`. For legacy exact-token `buy`, the original sample tested the observed reserve input against
`ceil(token_amount * virtual_quote / (virtual_tokens - token_amount))`.

## Results

| Path | Exact | Mismatch |
|---|---:|---:|
| `buy_exact_sol_in` official exact-input formula | 6 | 0 |
| routed `buy_exact_quote_in` same curve formula | 5 | 0 |
| legacy `buy` reverse exact-token formula | 9 | 0 |

The 12-block run initially tested the IDL's documented reverse-quote `+1` form against legacy
`buy`; 46/46 mismatched because that formula belongs to quoting an exact-input instruction in
reverse, not to legacy `buy`'s reserve delta. A second run compared the plausible integer reverse
forms explicitly: all 9 legacy buys matched `ceil(ratio)` (equivalently `floor(ratio)+1` when the
division has a remainder). That sample had no exactly divisible ratio and therefore could not
determine whether the extra lamport was conditional.

## Full-population correction — 2026-08-01

The published B9d reserve path contains 31,397 legacy buys and one decisive exact-division
observation (signature
`4sbHFQcTD6UJvsYdfKmjJCQt5Y28HC1uX8wGfKLJW36nEgKWJEJ8erHRMhtnAFr4me5ZTyVoReUGnfSjnNpddvVy`,
slot 433,988,917): the ratio is exactly 7,000,000,000 lamports and the observed quote amount is
7,000,000,001. Therefore the legacy exact-token buy expression is:

```
floor(token_amount * virtual_quote / (virtual_tokens - token_amount)) + 1
```

Across the full published population, `ceil` reproduces 31,396/31,397 legacy buys; the corrected
`floor + 1` expression reproduces 31,397/31,397. This supersedes only the legacy-buy rounding claim
above; the exact-input formula and the documented scope limitations remain unchanged.

## Conclusion

B2a F19 is resolved for the published current-regime SOL paths. The mismatches were caused by using
the wrong integer expression and by conflating exact-input with exact-output instruction
semantics—not by approximate arithmetic. Exact reconstruction remains mandatory. The full B9d
population establishes exact trade-quantity reproduction for sells, exact-input buys, and legacy
buys. Fee reproduction is established only where its input base is preserved; see the B9i gate.

The Phase 2 precondition is still not generally complete: USDC/other quote-mint paths require the
same checks using `quote_*` fields, Mayhem requires non-trade reserve mutations, and current-version
results cannot silently be applied across historical decoder regimes.
