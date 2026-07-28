# B0e — IDL-Driven TradeEvent Decode and First Exact Economic Invariant

Run: 2026-07-27, approximately 11:05–11:20 UTC. Author: Claude.
Current program version = deploy of slot 433,095,571 (2026-07-15).

Read-only mainnet RPC plus offline Borsh decoding. No keys, no signing, no transactions.
Script: `scripts/b0e_tradeevent_decode.py`.

## Source pinning and independent audit

IDL: `pump-fun/pump-public-docs` `idl/pump.json` at commit
`9c82f61cb711b044a17f770ab8ce9f9bdf78f333`.
SHA-256 `b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49`.

I downloaded and hashed it independently: **the digest matches Codex's reported value exactly.**
The decoder is generic and IDL-driven — field names, order, and types come from the pinned file,
not from anything hand-written — so a wrong IDL produces a decode failure rather than plausible
numbers.

## F10 — TradeEvent decodes exactly (verified fact)

26 of 26 TradeEvents from successful transactions decoded with **zero bytes remaining**:
0 short reads, 0 trailing bytes, 0 decode failures. `TradeEvent` has 32 fields, and the
discriminator `bddb7fd34ee661ee` is derived, not assumed.

Exact consumption is the acceptance criterion, not a nicety: a trailing byte would mean the field
list is wrong somewhere upstream, and every reserve parsed after that point would be silently
misaligned.

## F11 — Post-trade reserves are in the event (verified fact; closes a blocking question)

`agent_discussion.md` Seq 6 open question 1 asked whether Pump trade events emit post-trade
reserves, flagging that **"if not, B2 must be redesigned and C4 becomes materially harder."**
They do. Every decoded event carries:

```
virtual_sol_reserves   virtual_token_reserves
real_sol_reserves      real_token_reserves
```

plus `quote_mint`, `quote_amount`, `virtual_quote_reserves`, `real_quote_reserves` for non-SOL
pairs. Curve state is therefore reconstructible from the event stream alone, without account
snapshots — which is exactly the property Jetstreamer backfill needs, since Old Faithful has no
account updates. **B2 and C4 are feasible as designed.**

Observed `quote_mint` was `11111111111111111111111111111111` on every sample, i.e. native SOL,
with `quote_amount == sol_amount`.

## F12 — First exact integer economic invariant, verified (verified fact)

Tested on every decoded event:

```
fee == ceil(quote_amount * fee_basis_points / 10_000)
```

| Check | Result |
|---|---|
| `fee` exact match to `ceil` | **25 / 25** non-zero-bps events |
| `creator_fee` exact match to `ceil` | **11 / 11** non-zero-bps events |
| Mismatches | **0** |
| Cases matching `floor` instead | 0 |
| Zero-bps events with zero fee (consistent) | 16 |

Rounding is **ceiling**, not floor or banker's rounding — a detail that would silently corrupt
every cost figure if guessed wrong, and it is now measured rather than assumed.

Observed `fee_basis_points = 95` and `creator_fee_basis_points = 30` independently reproduce the
documented 1.25% split (0.95% protocol + 0.30% creator) **from on-chain data**, confirming the
`DOCUMENTATION.md` table row against a primary observation rather than a web page.

## F13 — Mayhem appears to be a zero-fee regime (working hypothesis, weak evidence)

A `mayhem_mode = true` event was observed with `fee_basis_points = 0`, `fee = 0`,
`creator_fee_basis_points = 0`, and `creator_fee = 0`, while contemporaneous non-Mayhem trades
carried 95/30 bps.

**This rests on very few observations and is not a verified fact.** If it holds, it matters more
than its size suggests: Mayhem is not merely a different token population but a *different fee
regime*, which strengthens the existing decision to record Mayhem as a covariate and to keep it
out of the initial tradable population. Requires a targeted sample before promotion.

## F14 — Payload size variation fully explained (verified fact; closes a follow-up)

The 350–381 byte spread reported in B0b is entirely the `ix_name` string length. Measured:

| `ix_name` | length | payload |
|---|---:|---:|
| `buy` | 3 | 366 B |
| `sell` | 4 | 367 B |
| `buy_exact_quote_in` | 18 | 381 B |

Payload = 363 + `len(ix_name)`, exactly linear, with `shareholders` empty in all samples. The
`TradeEvent` body has two variable-length fields (`ix_name: string`, `shareholders: vec`); a
fixed-offset parser would break on both. Nothing anomalous remains to explain.

## F15 — `ix_name` is a second, independent instruction identity (verified fact)

The event carries the instruction name inside it. Observed values include `buy_exact_sol_in` and
`buy_exact_quote_in`, which did **not** appear among outer instruction discriminators in the B0b
sample — they arrive through routers and aggregators as inner calls. Two consequences:

1. Classifying trades by outer discriminator alone undercounts and misattributes routed flow.
2. `ix_name` versus decoded discriminator is a free cross-check: disagreement between them is a
   decoder bug or an unknown code path, and should fail visibly.

## Limitations

- 26 events from one narrow window on one day, on the post-2026-07-15 version only. The fee
  invariant is verified *on this sample*, not established across fee regimes, versions, or
  Mayhem/USDC paths.
- Non-archival public endpoint; no cross-provider verification.
- Exact decode proves the field *layout* is right. It does not prove field *semantics* — that
  `real_sol_reserves` means what the name implies is still an IDL-level claim.
- The fee invariant was tested against `quote_amount`. For non-SOL pairs `quote_amount` and
  `sol_amount` differ, and the invariant must be re-tested there before it is relied upon.
- No pre-trade reserve reconstruction attempted yet; that is the B2 test, and it needs
  consecutive events for one mint.

## Follow-ups

1. Re-test the fee invariant on a USDC-paired sample and across a Mayhem-heavy sample.
2. Reconstruct pre-trade reserves by chaining consecutive events for a single mint and verify the
   constant-product step exactly — the real B2 precondition.
3. Confirm or refute F13 with a targeted Mayhem sample.
4. Add the `ix_name` versus discriminator cross-check to the decoder as a fail-visible assertion.
