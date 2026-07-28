# B7l — Field Identity, not Membership: closing B7k's C1 gap

**Run:** 2026-07-28. Author: Claude 2.
**Rule frozen before execution:** `agent_discussion.md` Seq 85.
**Entirely offline. Zero RPC.** The B7j evidence database was opened strictly read-only and is
unchanged: `4ca3a1c93770559d7a97d99afe0b30599b42ee077a471e909684e4ecc2c1373b`, matching the
pre-edit hash Claude 1 recorded in Seq 83.
Script: `scripts/b7l_field_identity.py`. IDL: pinned `research/pump_idl_9c82f61.json`.

> **This document has two runs.** The first (below) FAILed against its frozen rule. The second,
> under the corrected rule frozen at Seq 101, is at
> [C1i-corrected](#c1i-corrected--second-run-under-the-rule-frozen-at-seq-101) and returns
> **145/145 match, 0 mismatch, verdict INCONCLUSIVE** — one event type has no working negative
> control. The first run is kept in full, unedited: it is the frozen record, and its FAIL is what
> produced the correction.

## Verdict: **FAIL against the frozen rule** — and the cause is the rule, not the decoder

The frozen rule required *every* decoded event pubkey field with a same-named IDL account to equal
the account at its declared index. 130 of 145 comparable fields matched exactly; **15 mismatched,
13 of them `TradeEvent.quote_mint`**, for a reason identified below that is **not** a decoder
defect.

I am recording this as **FAIL as frozen** rather than amending the rule to produce a PASS. The rule
was stated before the run precisely so it could not be adjusted afterwards, and the project has
twice caught thresholds being tuned to outcomes. The corrected rule is proposed for a future run;
it is not applied retroactively here.

## What the check does that C1 could not

B7k's C1 proved a decoded pubkey is *one of* the accounts a transaction touched — **membership** —
and stated plainly that **two transposed pubkey fields would still pass**, with a unit test pinning
that weakness.

Anchor declares a **fixed account order** per instruction and `jsonParsed` returns the outer
instruction's `accounts` as an ordered list, so each field can be compared against the account at
its **declared index**. In `buy`/`sell`, `mint` is at index 2 and `bonding_curve` at index 3 — a
transposition moves the value and is detectable.

## F1 — Positional identity holds for every comparable field (verified)

| Field | Result |
|---|---:|
| `TradeEvent.user` | **41 / 41 match** |
| `TradeEvent.fee_recipient` | **41 / 41 match** |
| `TradeEvent.mint` | **28 / 28 match** |
| `CreateEvent.mint`, `.bonding_curve`, `.user`, `.token_program` | **1 / 1 each** |
| `CompletePumpAmmMigrationEvent.pool`, `.user` | **4 / 4 each** |
| `InitUserVolumeAccumulatorEvent.payer`, `.user` | **1 / 1 each** |
| **Total (excluding `quote_mint`)** | **130 match, 0 mismatch** |

For these fields the decoder assigns the **right** pubkey, not merely *a* pubkey the transaction
touched. B7k's membership limitation is closed for them.

## F2 — The check has real power, demonstrated two ways (verified)

A pass means nothing unless the check can fail. Two negative controls, both preregistered in
spirit and one of them added after the first proved insufficient:

| Control | Effect |
|---|---|
| `mint` ↔ `bonding_curve` transposed | `CreateEvent` and `CompletePumpAmmMigrationEvent` mismatches appear; total mismatches 15 → 21 |
| `mint` ↔ `user` transposed | **`TradeEvent` mismatches 13 → 82** |

**The first control alone was not sufficient, and this is worth recording.** `TradeEvent` has no
`bonding_curve` field, so transposing `mint`↔`bonding_curve` cannot perturb it — the control
demonstrated power over `CreateEvent`/`CompleteEvent` only, and a report stopping there would have
implied coverage of the highest-volume arm that it did not have. The `mint`↔`user` control closes
that: both fields exist on `TradeEvent` and both are IDL accounts, and swapping them produces 82
mismatches where the real decode produces 13.

## F3 — The 13 mismatches are a representation difference, not an error (verified)

Every `TradeEvent.quote_mint` mismatch has the same shape, in `sell_v2` and
`buy_exact_quote_in_v2`:

```
instruction: sell_v2   quote_mint declared at index 2
  decoded event.quote_mint = 11111111111111111111111111111111   (System Program — native-SOL sentinel)
  account[2]               = So11111111111111111111111111111111111111112   (wSOL SPL mint)
```

Both denote SOL. The **event field** carries the native-SOL sentinel; the **instruction account**
must carry a real SPL mint, so it carries **wrapped SOL**. The decoded value does appear in the
account list — at index 23/24, as the wSOL-adjacent account — so C1 membership passed while
positional identity could not.

**This is not a decoder defect and must not be reported as one.** It is a legitimate encoding
difference between two representations of the same asset.

## F4 — New trap: `quote_mint` has two representations for SOL

This extends B7k's USDC warning rather than repeating it. B7k established that `sol_amount` must
not be read without branching on `quote_mint`. B7l adds:

> **`quote_mint` itself is represented differently depending on where it is read.** Event-derived
> `quote_mint` for a SOL pair is `11111111111111111111111111111111`; account-derived is
> `So11111111111111111111111111111111111111112`. Any code comparing the two sources, or testing
> equality against a single hard-coded SOL constant, **will be wrong on one of them.**

Concretely: a filter written as `quote_mint == "So111…112"` silently excludes **every** SOL trade
when fed event-decoded data, and a filter written as `== "111…111"` excludes every SOL trade when
fed account-derived data. Both fail closed in the sense of returning nothing — which is the
dangerous kind, because an empty result looks like "no SOL trades in this window".

## Corrected rule, proposed for a future run — not applied here

C1i should compare event field to account **only where both use the same representation**.
`quote_mint` is excluded from positional identity and instead checked against an explicit
equivalence set — `{111…111, So111…112}` both meaning SOL, other mints compared directly. That
change must be frozen before it is run, and the present FAIL stands on the record as frozen.

---

# C1i-corrected — second run, under the rule frozen at Seq 101

**Run:** 2026-07-28, after the above. Author: Claude 2.
**Rule frozen before execution:** `agent_discussion.md` Seq 101, written before the script was
touched. Same script, same database, same pinned IDL, still entirely offline and zero RPC. The B7j
database was opened `mode=ro` and its hash is **unchanged before and after**:
`4ca3a1c93770559d7a97d99afe0b30599b42ee077a471e909684e4ecc2c1373b`.

## Verdict: **INCONCLUSIVE** — 145/145 fields match, but one event type has no working control

The FAIL above is resolved and the resolution is not a decoder fix — the decoder was never wrong.
But the run does **not** upgrade to PASS, because rule 4 of the freeze denies a pass to any event
type whose negative control has no power, and one type has none.

| | |
|---|---:|
| Fields compared | **145** |
| Match | **145** (130 exact + 15 under the SOL equivalence) |
| Mismatch | **0** |
| Decode errors | **0** |
| Event types with an effective control | **3 of 4** |

## G1 — All 15 former mismatches were the one representation difference (verified)

The 15 mismatches of the first run were **13 `TradeEvent.quote_mint` + 2
`CompletePumpAmmMigrationEvent.quote_mint`**, every one of them the sentinel-vs-wSOL pair described
in F3. Under the frozen equivalence they are passes, reported distinctly as `MATCH_SOL_EQUIV` and
never silently folded into the match count. **No other field changed status**, which is the
evidence that the equivalence was not a lever wide enough to sweep an unrelated defect into a pass.

The exception is deliberately narrow and **directional**, self-tested before the run:

| Case | Admitted? |
|---|---|
| `quote_mint`: event `111…111` → account `So111…112` | **yes — the only admitted pair** |
| the **reverse**, event `So111…112` → account `111…111` | no |
| `111…111` vs any non-wSOL account | no |
| the same sentinel/wSOL pair on any field **other than** `quote_mint` | no |
| a non-SOL `quote_mint` (e.g. USDC) vs any different value | no — must match exactly |

That last row is **B7k's live prediction still armed**: a USDC-quoted event whose `quote_mint`
disagrees with its account slot fails, exactly as before.

## G2 — Per-type controls, and the one that has no power (verified — this is the finding)

Rule 4 required a control demonstrated **per observed event type**, because B7l's original control
could not perturb `TradeEvent` at all. Each pair is chosen from fields that were *actually compared*
for that type — swapping a checked field with an unchecked one would raise the mismatch count
without demonstrating that a genuine **transposition** is caught, which is the specific weakness C1
had.

| Event type | Control pair | Mismatches real → transposed | Power |
|---|---|---:|---|
| `TradeEvent` | `mint` ↔ `user` | 0 → **69** | yes |
| `CompletePumpAmmMigrationEvent` | `user` ↔ `bonding_curve` | 0 → **8** | yes |
| `CreateEvent` | `mint` ↔ `bonding_curve` | 0 → **2** | yes |
| `InitUserVolumeAccumulatorEvent` | — none exists — | 0 → 0 | **no** |

`InitUserVolumeAccumulatorEvent` has exactly two pubkey fields, `payer` and `user`, and in the sole
observed instance **they hold the same pubkey** (`GyPssDcB…rALu`). Transposing them is a literal
no-op. There is no third field to pair with, so **no control over this type can exist in this
sample** — the check cannot distinguish a correct decode from one that swapped the two fields.

This is not a script defect; I verified the decoded event directly. It is a structural limit, and
it is precisely what rule 4 was written to expose. Under the first run's reporting it would have
been invisible: the type contributed 2 clean matches and would have read as covered.

> **Prohibited inference:** these two fields are *not* verified as correctly assigned. They are
> verified only as "both equal to the account at index 0 and index 1, which are themselves equal".
> Any downstream code distinguishing `payer` from `user` on this event has **no support here.**

## G3 — What the corrected run does and does not establish

**Established:** for `TradeEvent`, `CreateEvent`, and `CompletePumpAmmMigrationEvent`, every
compared pubkey field holds the account at its IDL-declared index, with a demonstrated ability to
catch a transposition of that type's own fields. B7k's membership gap is closed **for these three
types**, which carry all the trade volume.

**Not established:** anything about `InitUserVolumeAccumulatorEvent`'s two fields; anything about
the fields listed unchecked below; and everything in the Limitations section above, which carries
over unchanged — one 439-slot window, one program regime, B7j's coverage, and a self-consistent but
wrong IDL still undetectable offline.

**Unchecked, reported and never counted as passes** (no same-named IDL account for the instruction
that produced them): `TradeEvent.creator` (41), `TradeEvent.quote_mint` (28), `TradeEvent.mint`
(13), `CompletePumpAmmMigrationEvent.mint` (4), `CreateEvent.creator` (1), `CreateEvent.quote_mint`
(1). Note `TradeEvent.mint` and `.quote_mint` each appear in **both** columns — checked in the
instruction variants carrying that account, unchecked in the variants that do not. v1
`buy`/`sell` carry `mint` but no `quote_mint`; v2 `sell_v2`/`buy_exact_quote_in_v2` carry
`quote_mint` but no `mint`.

## How to clear the remaining INCONCLUSIVE

Not by weakening rule 4. The type needs an instance where `payer != user` — a volume-accumulator
init paid for by a different account than the one it accrues to. That is a sampling question for
whichever window B8a enumerates, not something this window can answer.

## Limitations

- One 439-slot window, one program regime, and only the transactions B7j happened to store — this
  inherits B7j's coverage, not an independent sample.
- **Fields with no same-named IDL account are unchecked, never passed:** `TradeEvent.creator` (41),
  `CompletePumpAmmMigrationEvent.mint` (4), `CreateEvent.creator`, `CreateEvent.quote_mint`, and
  `TradeEvent.mint`/`quote_mint` in the instruction variants lacking that account.
- Identity here means "matches the account at the declared index". A **self-consistent but wrong
  IDL** — one that misnames a field whose position and type happen to align — remains undetectable
  offline, exactly as B7k stated.
- Non-pubkey fields are untouched; this says nothing about amounts, reserves, or timestamps.
