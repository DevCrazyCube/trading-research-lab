# PREDMARKET side-measurements, 2026-09-04 21:00 CEST tick (CHUNK D)

Two knowledge-free structural scans run over the same 3,000-market pull that produced this
tick's five frozen estimates. Recorded as MEASUREMENTS, not as edges. Neither is tradeable
as-is; the second is a candidate build item with an explicit precondition.

## 1. Cross-venue basis on US House control -- MEASURED, NOT AN EDGE

| venue | market | p(Dem control) | spread | volume |
|---|---|---|---|---|
| Kalshi | `CONTROLH-2026-D` | 0.845 | 0.01 | $17.2M |
| Polymarket | `562802` | 0.885 | 0.01 | $5.7M |

A 4.0pp gap between two books with >$5M each on what is nominally the same event. It is NOT
a free 4pp: the two contracts do not resolve at the same time. Kalshi closes 2027-02-01
(seating) vs Polymarket 2026-11-03 (election night), so Kalshi ties capital ~3 months longer
and its YES must trade at a discount equal to the carry on that capital plus the small
election-to-seating tail risk. At plausible rates that explains a low-single-digit-point
basis, i.e. most or all of what is observed. **Verdict: the basis is structurally expected,
not mispricing. No estimate frozen against it.** Logged so a future tick does not rediscover
it and mistake it for alpha.

## 2. Polymarket district book -> House-control aggregation -- BLOCKED ON COVERAGE

The pull contains 379 per-district contracts of the form "Will the {Democratic,Republican}
Party win the {XX-NN} House seat?", spanning 251 distinct districts, 128 of which have BOTH
party legs quoted. Internal coherence of those 128 is excellent: the D+R sum ranges
[0.9505, 1.0100] -- i.e. the per-district books are near-arbitrage-free, so the district
prices are usable as probabilities.

The interesting test is the AGGREGATION one: convolve the 435 independent-ish district
Bernoullis into a distribution over Democratic seats, read off P(seats >= 218), and compare
that to the headline control markets above. If the aggregate and the headline disagree by
more than the correlation adjustment can carry, one of them is wrong -- and that is a
knowledge-free, defensible view of exactly the kind this tracker wants.

**It is BLOCKED, and honestly so.** The pull is volume-truncated at 3,000 markets, so we
have 251 of 435 districts. The missing 184 are the low-volume ones, which are precisely the
safe seats -- assigning them by prior would inject the modeller's own assumption into the
answer, and the disagreement we measured would then be a measurement of that assumption
rather than of the market. Uncorrelated convolution is also wrong on its face: district
outcomes share a national swing, and ignoring that correlation systematically UNDERSTATES
the tails, which is the direction that would manufacture a fake edge at the 218 threshold.

PRECONDITION to run it: (a) a full-coverage district pull (all 435, not volume-truncated),
and (b) a stated national-swing correlation structure frozen BEFORE the aggregate is
computed. Absent both, this stays unrun rather than run badly. Not added to the agenda as a
build item this tick -- it is a prediction-market side-quest, and the programme's converged
direction remains the equities forward-data spine.
