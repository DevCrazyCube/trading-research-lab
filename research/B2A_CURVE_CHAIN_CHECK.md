# B2a — Exact Integer Curve-Chain Verification

Run: 2026-07-27, approximately 11:30–11:45 UTC. Author: Claude.
Sampled consecutive finalized blocks near slot 435,530,915 and 435,531,115.
Current program version = deploy of slot 433,095,571 (2026-07-15).

Read-only mainnet RPC plus offline integer arithmetic. No keys, no signing, no transactions.
Script: `scripts/b2a_curve_chain_check.py`. IDL: pinned `research/pump_idl_9c82f61.json`.

This is the **B2 precondition test**: can curve state and quotes be reproduced exactly at integer
precision from the event stream alone? Both tests are exact-equality by construction — per
`DECISIONS.md`, deterministic quantities reconcile exactly or not at all.

## Headline

**Partially. Reserve chaining is exact for non-Mayhem tokens and for sells; buy-side quote
reproduction is not yet solved.** This is a negative result on the buy path and it is more useful
than a pass would have been, because it localises exactly what Phase 2 still has to model.

## T1 — Reserve continuity

Test: do consecutive `TradeEvent`s for one mint chain exactly?
`v_sol[i] ± sol_amount[i+1] == v_sol[i+1]` and `v_tok[i] ∓ token_amount[i+1] == v_tok[i+1]`.

| Population | Exact | Break |
|---|---:|---:|
| **Non-Mayhem** (`buy`, `sell`, `buy_exact_sol_in`, `buy_exact_quote_in`) | **28** | **0** |
| **Mayhem** | 11 | 4 |

**F16 — Non-Mayhem curve state chains exactly from events alone (verified on this sample).**
28 of 28 consecutive transitions reproduced exactly. Combined with F11, this means curve state is
reconstructible from the event stream without account snapshots — the property Jetstreamer
backfill requires, since Old Faithful carries no account updates.

**F17 — Mayhem virtual reserves are externally mutable, so Mayhem curves are NOT self-consistent
from the event stream (strong indication, small sample).**
Every break occurred on a `mayhem_mode = true` token, and in every break **the token side matched
exactly while only the SOL/quote side diverged**:

```
23YMqksPtE5k  buy   v_sol 85406640 -> 91315373  (delta 5908733, sol_amount 5009144)   sol_ok=False
                    v_tok ...                    (delta == token_amount)               tok_ok=True
63nvmEAeGcjU  buy   v_sol 116164095865 -> 126665409513 (delta 10501313648, sol_amount 239650601)
```

The deltas exceed the traded amounts on the SOL side only. The pinned IDL contains
`set_mayhem_virtual_params` and `set_virtual_quote_reserves` — instructions that adjust virtual
quote reserves outside of trading — which is consistent with what is observed. That is an
inference from the field pattern plus the IDL surface, not a decoded observation of those
instructions firing; confirming it requires catching one in a block.

**Why this matters beyond Mayhem:** `PLAN.md` already excludes Mayhem from the initial tradable
population as a scope choice. This supplies a *mechanical* reason: a simulator cannot reconstruct
a Mayhem curve from trades alone, because a third party can move the reserves between trades.
Excluding Mayhem is now a correctness requirement, not a preference.

## T2 — Constant-product quote reproduction

Test: given pre-trade reserves and the input, does exact integer constant-product reproduce the
observed output? `k = v_sol * v_tok`; buy → `tok_out = v_tok - k/(v_sol + sol_in)`;
sell → `sol_out = v_sol - k/(v_tok + tok_in)`. Floor and ceiling divisions both tried.

Wider re-run (85 chained transitions):

| Instruction | Exact (ceil-k) | Mismatch |
|---|---:|---:|
| `sell` | **49** | 0 |
| `buy` | 17 | 11 |
| `buy_exact_sol_in` | 0 | 5 |
| `buy_exact_quote_in` | 0 | 3 |

**F18 — Sells reproduce exactly; the rounding convention is ceiling (verified on this sample).**
`sol_out = v_sol - ceil(k / (v_tok + tok_in))`, **49 of 49**, zero mismatches. Together with F12's
`fee = ceil(amount × bps / 10000)`, ceiling is so far the consistent convention.

**F19 — Buy-side quotes do NOT reproduce with the naive formula (verified negative).**
On a wider re-run (85 transitions: 49 sells all exact, 17 buys exact, 19 mismatched), every
mismatch has the observed output **smaller** than predicted, with relative residuals between
`1.8e-10` and `7.0e-8`.

**The obvious explanation is refuted.** I hypothesised a fee deducted from the input before the
curve. To test it I solved, by binary search, for the effective input `s_eff` that would reproduce
each observed output. Result:

- `s_eff` differs from `sol_amount` by **0 or 1 lamport**, while the fees on those same trades are
  10⁵–10⁷ lamports. A pre-curve fee deduction is **not** the cause.
- More decisively, **0 of 19 were reproduced exactly even after solving for `s_eff`**. The observed
  output falls strictly between the outputs produced by consecutive integer inputs, so it is *not
  achievable by any integer input* under `tok_out = v_tok − k/(v_sol + s)`.

That makes this a **difference in the shape of the computation, not in its inputs** — most likely
where intermediate rounding happens inside a u128 evaluation, since the constant-product identity
is violated by only ~1e-8 relative. Note also that 17 buys *did* match the same ceiling formula,
so this affects a subset of buy paths rather than all of them.

Unresolved, and it must be resolved before Phase 2's gate can be met. Recorded as a failed
hypothesis with its residuals rather than absorbed into a tolerance.

## Limitations

- Small sample: 85 chained transitions across two runs; 19 T2 mismatches. Directionally clear,
  not a distribution.
- 11 transitions were skipped for a zero denominator. These are likely quote-denominated
  (non-SOL) trades where `sol_amount`/`virtual_sol_reserves` are zero and the `quote_*` fields
  carry the values. **The test used the SOL fields throughout and is therefore not valid for
  quote-paired trades** — a separate run against `quote_amount`/`virtual_quote_reserves` is needed.
- Ordering within a block used transaction index then inner-instruction index. That matches the
  canonical ordering rule, but a mis-ordering would present as a T1 break, so T1's 28/28 on
  non-Mayhem is also weak evidence the ordering is right.
- Current program version only; the ~13-day upgrade cadence means this must be re-run per version.
- F17's causal explanation is inferred from the IDL surface, not observed directly.

## Follow-ups

1. Resolve F19. The input-adjustment hypothesis is refuted; the remaining candidate is a
   different intermediate-rounding shape inside the program's u128 evaluation. The decisive test
   is reading the buy path in the deployed program or a published reference implementation,
   rather than more black-box fitting.
2. Re-run T1/T2 against `quote_*` fields for non-SOL pairs.
3. Catch a `set_mayhem_virtual_params` or `set_virtual_quote_reserves` instruction in a block to
   confirm F17 directly.
4. Re-run across upgrade boundaries once the boundary sweep identifies regime changes.

## Superseding result: B2b

F19's source-level question is resolved in `research/B2B_OFFICIAL_BUY_FORMULA.md`. The pinned
official IDL specifies an exact-input formula with `net_input - 1` inside both numerator and
denominator; it is not equivalent to T2 after integer rounding. Instruction-specific T3 checks
subsequently reproduced 11/11 sampled exact-input buys and 9/9 newly tested legacy exact-token buys with
zero tolerance. Preserve F19 above as the failed-hypothesis record, but do not treat it as a
current blocker for sampled SOL/non-Mayhem paths.
