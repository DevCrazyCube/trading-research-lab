# B0b/c/d — Current-Regime Pump Interface Probe

Run: 2026-07-27, approximately 10:44–10:58 UTC. Author: Claude.
Sampled slots 435,523,453–435,523,458 and a second window minutes later.
Current program version = the deploy of slot 433,095,571 (2026-07-15).

Read-only JSON-RPC against `https://api.mainnet-beta.solana.com`. No keys, no signing,
no transactions. Scripts: `scripts/b0b_interface_probe.py`, `scripts/b0c_discriminator_resolve.py`,
`scripts/b0d_event_probe.py`.

## Method note — why these names are derivations, not guesses

Anchor derives discriminators deterministically:

```
instruction discriminator = sha256("global:" + snake_case_name)[:8]
event discriminator       = sha256("event:"  + CamelCaseName)[:8]
```

A name is reported as **RESOLVED** only when its hash equals the observed bytes. Candidate names
that do not hash to an observed value are discarded; observed values that no candidate matches are
reported as **UNKNOWN** rather than assigned a plausible label. This satisfies the `AGENTS.md`
prohibition on inventing instruction layouts.

## Findings

### F5 — C2 is confirmed on the current program version (verified fact)

Every successful sampled transaction carried Pump self-CPI inner instructions bearing Anchor's
event tag `e445a52e51cb9a1d`. In the 60-transaction window, 38 of 60 transactions contained
self-CPI event data and exactly 38 of 60 succeeded — self-CPI coverage among successful
transactions was **100%**. The emitted event resolves by derivation:

| Event discriminator | Name | Body size |
|---|---|---|
| `bddb7fd34ee661ee` | `TradeEvent` (RESOLVED) | 350–363 bytes |

C2 moves from `[unverified]` to verified **for this program version**. Decoding from
inner-instruction data is viable today; a decoder does not need `logMessages` for trade events.

Caveat stated plainly: **no log truncation was observed** in the 60-transaction sample (0 hits).
That is not a refutation of the truncation risk — it means truncation did not occur in a
~6-slot window. The argument for preferring self-CPI data stands on availability, which is now
measured, rather than on an observed truncation rate, which is not.

### F6 — v2 instructions have NOT displaced v1; both are live simultaneously (verified fact)

`DOCUMENTATION.md` records that Pump "recommends unified `buy_v2`, `sell_v2`, and
`buy_exact_quote_in_v2` integration instructions." Measured traffic on the current version:

| Discriminator | Resolved name | Outer | Inner (routed) |
|---|---|---:|---:|
| `66063d1201daebea` | `buy` | 24 | 7 |
| `f945a4da9667548a` | `close_user_volume_accumulator` | 15 | – |
| `33e685a4017f83ad` | `sell` | 5 | 5 |
| `b817ee6167c5d33d` | `buy_v2` | 2 | 1 |
| `5df6823ce7e940b2` | `sell_v2` | – | 4 |
| `c2ab1c46684d5b2f` | `buy_exact_quote_in_v2` | – | 1 |
| `253a237ebe35e4c5` | `claim_cashback` | 1 | – |
| `d6904cec5f8b31b4` | `create_v2` | 1 | – |

**A decoder must support v1 and v2 concurrently** — treating the documented recommendation as a
description of actual traffic would have silently dropped most trades. Account counts also differ
by variant (`buy` = 18 accounts, `buy_v2` = 27, `sell` = 16/17/24), so account-index assumptions
must be per-discriminator.

> **CORRECTION (2026-07-27 11:20 UTC, B0f).** The original text of F6 said "legacy `buy`/`sell`
> dominate observed traffic." That generalised from a single narrow window and is **withdrawn**.
> Sampling blocks around slot 433,095,571 showed `buy_exact_sol_in` (`38fc74089edfcd5f`) as the
> overwhelmingly dominant outer instruction — 147 occurrences pre-boundary and 276 post-boundary —
> while it appeared *zero* times in the recent window that produced the table above.
>
> The surviving, stronger claim: **the mix of trade-instruction variants varies dramatically
> between windows, so no variant may be assumed dominant and all must be decoded.** This is the
> same lesson as F9 — point-in-time sampling of this market produces confidently wrong
> generalisations — and it applies to my own finding.

### F7 — A non-trading instruction is a large share of program traffic (verified fact)

`close_user_volume_accumulator` was the second most common outer instruction (15 of 48 outer
Pump instructions). Any activity, transaction-count, or "trading intensity" feature that does not
classify by discriminator will be materially polluted by non-trade traffic. This matters directly:
`DOCUMENTATION.md`'s cited study attributes predictive value to *trading intensity*.

### F8 — The two initially unknown discriminators are resolved (verified against pinned official IDL)

The official `pump-fun/pump-public-docs` `pump.json` at commit
`9c82f61cb711b044a17f770ab8ce9f9bdf78f333` identifies `253a237ebe35e4c5` as
`claim_cashback` and `d6904cec5f8b31b4` as `create_v2`; the decimal discriminator bytes match
exactly. The downloaded IDL SHA-256 was
`b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49`.
Both are non-trade activity and reinforce F7: raw Pump instruction counts are not trade counts.

### F9 — Transaction failure rates are high and extremely unstable (working hypothesis)

| Window | Sampled | Failed | Rate |
|---|---:|---:|---:|
| Window A (60 sigs, slots 435523453–458) | 60 | 22 | 36.7% |
| Window B (40 sigs, minutes later) | 40 | 34 | 85.0% |

Both windows span only a handful of slots, so **neither is a failure rate** — they are two
snapshots that disagree by a factor of 2.3. Two things follow:

1. Directionally, this supports the existing working hypothesis that *transaction landing
   reliability may contribute more to net performance than a small improvement in direction
   classification*. A strategy ignoring landing probability is modelling a minority of its
   attempts.
2. Methodologically, the disagreement is the argument for B6. Point-in-time sampling of this
   market produces confidently wrong numbers. Only continuous recording can establish the
   distribution.

**Do not quote either figure as the Pump failure rate.** They are evidence that the quantity is
volatile and must be measured continuously, nothing more.

## Limitations

- Both windows are a few slots wide at one moment on one day; nothing here is a rate, a base
  rate, or a distribution.
- Sampling is via `getSignaturesForAddress` on the program, which returns recent-first and is
  therefore biased toward whatever was happening in those seconds.
- Public endpoint, not archival; no cross-provider verification.
- Instruction *names* are confirmed; instruction *semantics, account roles, and field layouts*
  are not. Only the official pinned IDL can supply those.
- Findings apply to the post-2026-07-15 version only. Given the ~13-day upgrade cadence measured
  in B0, they may not hold for historical slot ranges and should be re-run per version boundary.

## Follow-ups

1. Repeat the probe across B0's upgrade boundaries to find where the discriminator set changes —
   this is the concrete, cheap way to convert loader events into semantic regime boundaries and
   to answer whether the 2026-07-15 deploy broke anything.
2. Decode `TradeEvent`'s 350–363 byte body against the IDL; the size variation across otherwise
   identical events needs explaining before reserves can be trusted.
3. Let B6 measure the actual failure-rate distribution.
