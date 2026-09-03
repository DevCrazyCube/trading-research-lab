# The real constraint: we cannot detect an edge the size of the S&P 500

Four postures were measured and independently re-verified (12 of 15 load-bearing numbers reproduced, several
to four decimals). The verdicts were right. The *reason* they were right is not what we thought.

## What we thought the answer was

That crypto is uniquely tail-dominated, and that our month failed because we were picking names in the one
asset class where that cannot work. **That part is true and it verified exactly:**

| cross-section | mean−median gap (bp/day) | CI |
|---|---|---|
| **crypto perps** | **+57.07** | [54.41, 59.72] |
| equities, top-500 | **+1.43** | [−0.03, +2.93] — includes zero |
| DM FX vs EUR | +0.021 | [−0.21, +0.25] |
| US Treasury curve | +0.050 | [−0.28, +0.38] |

Compounded: the crypto daily cross-sectional median goes to **−99.9994%** while its basket makes +64.9%.
The equity median compounds to **+85.0%** while its basket makes +136.8% — **the median tracks the mean.**
Per-name buy-and-hold: crypto median **−79.1%** with 87.7% of names negative; equities median **+10.4%**
with only 42.4% negative, *after* charging every delisted name −30%.

So "don't pick names" is a property of **crypto**, not a law of markets. That is a real finding.

## What the answer actually is

**With 6.6–8 years of free daily data, no strategy with a true Sharpe below ~0.9 can be established at all.**

    MDE_Sharpe = 2.4865 / sqrt(independent_years)

At 8 years that is **0.879**. SPY's Sharpe in this same window is **0.842** — *below* our own detection
threshold. **The apparatus does not have 80% power to detect the S&P 500.**

The uncomfortable retroactive implication: across ~60 retirements in this repo, **"dead" and "undetectable"
were never separated.** An unknown fraction of those strategies were killed by a design that could not have
found them even if they were real.

## Nothing built in a month beats doing nothing

Same window, same pipeline, net of measured costs:

| holding | CAGR | vol | Sharpe | max drawdown |
|---|---|---|---|---|
| **SPY, buy and hold** | **15.27%** | 19.0% | **0.842** | **−33.8%** |
| QQQ, buy and hold | 20.17% | 24.2% | 0.882 | −35.0% |
| EW top-500 equities, monthly | 11.25% | 21.5% | 0.604 | −36.0% |
| BTCUSDT perp, net funding | 23.42% | 60.8% | 0.657 | −78.9% |
| EW crypto basket, monthly | 6.40% | 81.9% | 0.496 | −90.0% |
| EW crypto basket, daily | −4.32% | 82.4% | 0.370 | −91.8% |

SPY wins on Sharpe *and* drawdown simultaneously, and requires no research, no turnover, no funding, no
venue, no latency, and no retirements.

## The other two postures, for the record

- **Own the basket — DEAD.** Net of measured turnover and funding the EW crypto basket returns **−2.06%/yr
  with a −91.9% drawdown**; not one variant cleared its own MDE. The basket does not diversify the tail, it
  *relocates* it: drop the best 10 days of 2,403 and CAGR falls to −23.3%. Owning everything just moves the
  lottery from "which coin" to "which ten days." And the whole +64.9% is one calendar year — excluding 2021
  the basket is **−75.4%**.
- **Be the venue — DEAD, structurally and permanently.** Fee income scales as σ^1.14 while the LVR toll
  scales as σ^2.00, so pooled Uniswap v3 LP nets **−1.87%/yr** (CI [−2.99, −0.71]). Range width cancels
  exactly — it scales fees and LVR identically — so **no operator lever exists**. The LVR engine reproduced
  the published worked example to four decimals before any conclusion was drawn.

## The recommendation, and how to prove it wrong

**Own a broad index. Stop hunting for a tradeable edge on free daily data.** Not because edges don't exist,
but because at this sample size they are **unmeasurable by construction** — and an unmeasurable edge is
indistinguishable from a story.

Before building anything else, run one line of arithmetic:

    MDE_Sharpe = 2.4865 / sqrt(independent_years_available)

If it exceeds the Sharpe the candidate could plausibly earn, **the test cannot succeed and must not be run.**
Getting below 0.40 requires **38.6 independent years**.

**This is falsified if either of two things is true**, and both are worth one afternoon:
1. A strategy family with a defensible prior Sharpe **above 0.9**, or
2. **30+ years** of survivorship-complete free data.

## Caveats against my own conclusion

2018–2026 is an exceptionally kind equity regime — SPY's true long-run drawdown is **−56.8%** (2007–09), not
the −33.8% measured here. The crypto panel ends 2026-07-31 and is roughly a month stale. And allocation is
the owner's decision, not the researcher's.
