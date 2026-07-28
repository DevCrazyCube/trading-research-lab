# B7c — Trade-Only Silence Intervals: a Failed Sample Design, and One Usable Number

Run: 2026-07-27, approximately 16:40–17:00 UTC. Author: Claude.
RPC via `SOLANA_RPC_URL` (Helius); key never printed or persisted. Read-only, no signing.
Script: `scripts/b7c_trade_only_gaps.py`.

> **Headline: this run does NOT produce a `D_dead` candidate.** The token-selection filter
> introduced a bias that makes long silences impossible by construction. The failure is in my
> sample design, and it is reported rather than worked around.

## Burned sample

> **Slots 435,569,119 – 435,569,149 are BURNED** — disjoint from B7b's
> 435,566,652–435,566,690. Never for training, validation, or test.

## Caps, all reported (none silent — the B7b defect)

| Cap | Value | Effect |
|---|---|---|
| `--max-sigs` | 100,000 | histories hitting it: **0** |
| `--max-hist` | 700 | **the fatal one — see below** |
| `--min-hist` | 40 | small histories excluded |
| tokens | 8 | of 13 eligible, from 51 discovered |

## F51 — The sample design is invalid for measuring long silences

8 tokens, 1,352 transactions decoded exhaustively. Trade-only gap results:

| Threshold | Gaps ≥ | Tokens ≥ |
|---|---:|---:|
| 1 h … 168 h | **0** | **0** |

Maximum trade gap across all eight tokens: **0.05 hours (3 minutes).**

That is not evidence that long silences are rare. It is an artifact. To decode every transaction
exhaustively I filtered to tokens with 40–700 signatures. A token that is *currently trading* and
has only a few hundred lifetime transactions is almost certainly **newly launched** — so its entire
history spans minutes, and it **cannot** exhibit a multi-hour gap.

**I selected precisely the tokens incapable of showing the phenomenon being measured.** The
constraint that made the measurement affordable is the same constraint that made it meaningless.

This is the third iteration on `D_dead` and the third distinct defect (B7b: silent pagination cap;
B7b: inverted proxy direction; B7c: selection bias). That is a structural difficulty, not bad luck:
**tokens that are cheap to sample are young, and tokens old enough to show long silences are
expensive to enumerate.** Any future attempt must confront that trade-off directly rather than
filter around it.

## F52 — One usable result: the proxy is 96.7% trades

Measured, not assumed — this is what B7b asserted a direction for without checking:

| | |
|---|---:|
| Median trade fraction of mint-address signatures | **0.967** |
| Range across 8 tokens | 0.84 – 0.98 |

So mint-address signatures are ~97% Pump trades for these tokens, and the all-signature versus
trade-only gap ratio sits at **0.93–1.16** across every percentile — near 1.0.

**Scope limit, and it matters:** both figures come from young, busy tokens whose gaps are measured
in *seconds*. Interval-splitting by non-trade activity does its damage when true silence is
**long** and a stray transfer lands in the middle. This sample contains no long silences, so it
cannot bound the distortion where the distortion matters. F52 is a fact about short-gap regimes
only and must not be extrapolated to threshold selection.

## What a valid derivation requires

1. **Select tokens by age, not by history size.** Cohort members must be drawn from `CreateEvent`s
   in a launch window that is old enough for multi-day silences to be observable — which means
   historical `CreateEvent` enumeration, not sampling from current trading activity.
2. **Accept the decoding cost, or bound it honestly.** Exhaustive `TradeEvent` decoding for mature
   tokens is expensive at 7.8 req/s. Either budget for it, or use bonding-curve-address signatures
   (a far tighter proxy than mint signatures, since trades write to that account) and state the
   residual distortion.
3. **Report per-token and per-gap incidence**, as Codex established — the per-gap denominator hid a
   10% per-token incidence in B7b.
4. **Handle right-censoring**: each token's final ongoing silence is censored, not a gap.

## Status

`D_dead` remains **unset**, and the withdrawn 24-hour proposal stays withdrawn. Nothing
cohort-related may be built until a valid derivation exists.
