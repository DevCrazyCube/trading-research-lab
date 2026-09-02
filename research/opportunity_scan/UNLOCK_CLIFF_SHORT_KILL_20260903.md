# Token unlock-cliff shorts — tested and killed (2026-09-03)

The widely-cited claim (Keyrock, syndicated across crypto trade press) is that token unlock cliffs produce
**−8% to −15%** price pressure over the surrounding 30-day window, and **~−25%** for team/insider unlocks.
This repo's own `INVENT_R3` had declared the family **UNTESTED** for lack of a vesting feed. That blocker is
gone: DefiLlama's dataset host serves the full emissions schedule with **no key** (the metered `api.llama.fi`
route returns HTTP 402; the public front-end host does not).

Tested against our survivorship-complete Binance USD-M perp panel (`research/data/t23_cache`, 919 symbols
**including delisted names**). Total cost: **$0**, about 30 minutes.

## Gate 1 — coverage census: PASS

| step | count |
|---|---|
| cliff events in the free feed | 41,620 |
| with a positive token amount | 40,736 |
| token maps to a live USDT perp | 31,000 |
| **and ≥1% of circulating float** | 4,135 |
| **and in-window with the perp listed ≥30d before the cliff** | **1,136** |

78 distinct tokens, median cliff **2.12%** of float. Categories: insiders 355, noncirculating 205,
privateSale 191, farming 98. Kill line was 400 — passed at 2.8×.

## Gate 2 — power census, computed BEFORE reading any effect

Residual after subtracting the same-day cross-sectional median of the surviving universe (excluding names
within ±30d of their own ≥1% cliff), clustered by event date with a conservative ICC of 0.3:

| stratum | n | clusters | residual sd | MDE | claimed | verdict |
|---|---|---|---|---|---|---|
| pooled ≥1% | 1,135 | 520 | 63.6 pp | 5.46 pp | ~8 pp | **KILL** (line 3 pp) |
| **insiders + privateSale** | **545** | **311** | 59.3 pp | **6.99 pp** | ~25 pp | **PASS** |
| cliffs ≥5% of float | 217 | 126 | 102.6 pp | 19.09 pp | ~8 pp | KILL |
| ≥5% AND insider/private | 101 | 60 | 112.1 pp | 30.44 pp | ~25 pp | KILL |
| cliffs ≥10% of float | 103 | 61 | 134.6 pp | 36.22 pp | ~15 pp | KILL |

Alt-coin 44-day returns carry a 60–135 pp residual sd. Only the pre-declared insider/privateSale bucket is
adequately powered, so it is the only one whose effect may honestly be read.

## Gate 3 — the effect, on the one powered stratum: KILL

Market-controlled −30d → +14d return, insiders + privateSale, n=545 across 311 event-date clusters,
5,000-draw cluster bootstrap:

- **mean +6.61%** — the **wrong sign**
- median **−4.75%**
- cluster-bootstrap 95% CI **[−0.26%, +16.87%]**
- P(mean<0) = 0.036

Pre-registered gate (frozen before the data): mean ≤ −1.5% **and** CI-upper < 0 **and** funding < 50% of
gross. Both testable conditions **FAIL**.

## What actually killed it, and why it matters

**The published −8% to −15% is alt-sector beta, not an unlock effect.** Unlocking tokens are
disproportionately recent-vintage alts in a drawdown; subtract the same-day cross-section and the drop
disappears. This was pre-registered as kill-risk #1 and it is what fired.

**And the residual payoff is short-gamma — the worst possible shape for a short.** The median event is
−4.75% while the mean is **+6.61%**: you would win most trades and still lose money, because a minority of
tokens rip violently against the short. Shorting a right-skewed distribution is the classic way to be right
often and broke anyway.

**Conclusion: the unlock-cliff short is dead, on a properly controlled, adequately powered test.** The
family is now closed with a number rather than left as folklore, and the census + panel are reusable for any
future event-study on this venue.
