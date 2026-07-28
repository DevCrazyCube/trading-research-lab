# B7b — Deriving `D_dead` from a Burned Sample

> **Codex audit correction, 2026-07-27:** the proposed 24-hour value is **not ready for
> ratification**. A reproducible rerun with the original six-page ceiling removed found 3/30
> tokens (10%) had an interior gap of at least 24 hours. More importantly, the proxy-direction
> claim below was backwards: non-trade address activity splits true trade-silence intervals, so
> this proxy can produce a threshold that is too short. The original proposal is preserved below
> as historical context and is superseded by the audit section at the end.

Run: 2026-07-27, approximately 16:15 UTC. Author: Claude.
RPC via `SOLANA_RPC_URL` (Helius); key never printed or persisted. Read-only, no signing.
Script: `scripts/b7b_dead_threshold.py`.

## Burned sample — record and never reuse

> **Slots 435,566,652 – 435,566,690 are BURNED.**
> 30 tokens, 81,974 inter-activity gaps. This range must never appear in any training,
> validation, or test set. It exists only to choose `D_dead`, and choosing a label parameter
> from data that is later evaluated on is optimising on the evaluation set.

Activity proxy: all signatures on the mint address.

> **WRONG — corrected inline 2026-07-27.** The original text here read: *"This over-counts trading
> …, so measured gaps are a lower bound on true trade-silence, and a threshold drawn from them
> errs conservative."* The direction is **inverted**. Non-trade activity (transfers, ATA creation)
> inserts timestamps *between* trades and therefore **splits** a true trade-silence interval into
> shorter pieces. Measured gaps are consequently **shorter** than true trade-silence, and a
> threshold drawn from them is **too short — anti-conservative** for the exact failure it was
> meant to prevent, namely labelling a live-but-quiet token as inactive.
>
> Every "conservative by construction" claim below inherits this error and is void. Superseded by
> `research/B7C_TRADE_ONLY_GAPS.md`, which decodes `TradeEvent` timestamps directly and measures
> the distortion instead of assuming its direction.

## Gap distribution

| Percentile | Gap |
|---|---:|
| p50 | 0 s |
| p90 | 1 s |
| p99 | 38 s |
| p99.9 | 1,938 s (32.3 min) |
| p99.99 | 89,694 s (**24.9 h**) |
| max | 1,623,037 s (**450.8 h ≈ 18.8 days**) |

Live tokens are overwhelmingly busy — the median gap is under a second. The distribution then
jumps four orders of magnitude in the last 0.1%.

## F50 — The silence tail is heavy, so no threshold makes abandonment certain

Every gap measured is **interior**: by construction the token resumed activity afterwards. So each
row below counts silences from which tokens *did* come back.

| Silence ≥ | Gaps that still resumed | % of all gaps |
|---:|---:|---:|
| 1 h | 56 | 0.0683% |
| 6 h | 26 | 0.0317% |
| 12 h | 13 | 0.0159% |
| 24 h | 9 | 0.0110% |
| 48 h | 5 | 0.0061% |
| 72 h | 3 | 0.0037% |
| — | max observed resumption after **450.8 h** | |

**The tail does not terminate.** A token resumed after 18.8 days of silence. There is therefore no
`D_dead` at which "abandoned" becomes a fact rather than a label, and any wording implying
otherwise is wrong.

Two design consequences follow, and they matter more than the number itself:

1. **T2 must not be absorbing.** A token labelled abandoned that later trades again must be
   recorded as a **re-entry**, not silently reclassified and not dropped. Treating T2 as terminal
   would quietly delete exactly the 0.011% of cases that a "dead token revives" strategy would
   care about — and those are plausibly the ones with unusual dynamics.
2. **This is why Phase 4 specifies survival models.** A hard threshold forces a binary answer onto
   a censored-duration problem. `D_dead` should define a *label* for bookkeeping and cohort
   accounting, while the modelling treats silence duration as a continuous, censored quantity.

## Proposed value

**`D_dead` = 24 hours**, proposed for ratification, on these grounds:

- p99.99 of interior gaps is 24.9 h, so 24 h sits at the knee of the distribution.
- Only 0.011% of interior gaps exceed it.
- `docs/DEFINITIONS.md` C2 requires the launch window to end at least `D_dead` before the
  observation window. 24 h is an acceptable operational tail; 72 h triples it for a reduction from
  0.011% to 0.0037%, which is not a good trade.
- ~~Conservative by construction, since the activity proxy over-counts.~~ **VOID** — the proxy
  direction was inverted (see the correction above). This proposal is withdrawn, not merely
  unratified: both its percentile basis (six-page pagination cap) and its safety argument
  (proxy direction) were defective.

## Limitations — read before ratifying

- **Per-token incidence is unmeasured.** 9 gaps ≥24 h across 30 tokens could be nine different
  tokens (30% of the sample) or one erratic token nine times. These are very different worlds, and
  the second would make 24 h far safer than the first. **This should be measured before
  ratification.**
- 30 tokens, all sampled from a single ~15-second burst of trading activity, so they skew toward
  *currently active* tokens. Tokens that died before the burn window are absent by construction.
- Activity proxy is mint signatures, not `TradeEvent`s.
- Right-censoring is not handled here: a token's final silence is ongoing and was excluded, so
  these figures describe *interior* gaps only.

## Follow-ups

1. Measure per-token incidence of ≥24 h gaps before ratifying.
2. Re-derive on a second, disjoint burned sample and check the knee is stable.
3. Define the re-entry record format required by consequence 1.

## Codex reproducibility audit — same burned slots, uncapped histories

The original range was rerun exactly as Python's half-open interval
`range(435566652, 435566690)`, with 30 tokens and a 20,000-signature cap. No history reached the
cap. This replaces the original silent six-page/6,000-signature ceiling.

| Silence ≥ | Interior gaps | Distinct tokens |
|---:|---:|---:|
| 1 h | 56 / 128,085 (0.0437%) | 5 / 30 (16.7%) |
| 6 h | 26 (0.0203%) | 4 / 30 (13.3%) |
| 12 h | 13 (0.0101%) | 4 / 30 (13.3%) |
| 24 h | 9 (0.0070%) | **3 / 30 (10.0%)** |
| 48 h | 5 (0.0039%) | 3 / 30 (10.0%) |
| 72 h | 3 (0.0023%) | 3 / 30 (10.0%) |

The nine ≥24-hour gaps are concentrated in three tokens, closing the stated incidence question.
That concentration does not make 24 hours safe: a per-gap denominator hid a 10% per-token
incidence in this activity-selected sample.

Corrected distribution with complete-to-endpoint histories: p99 20 s, p99.9 1,065 s (17.8 min),
p99.99 45,585 s (12.66 h), maximum 1,623,037 s (450.84 h). The change from the original
percentiles proves the pagination ceiling was material even though the ≥24-hour gap count happened
to remain nine.

**Decision:** keep `D_dead` unset. The next derivation must decode actual `TradeEvent` timestamps
from a second disjoint burned sample, report per-token as well as per-gap incidence, record every
pagination/capture cap, and preserve re-entry as an explicit transition.
