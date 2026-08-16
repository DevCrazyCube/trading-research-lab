# B22F — the overnight/intraday split, measured: **I overstated this and the correction matters**

**Our own measurement.** SPY, 2,668 sessions, 2016-01-05 to 2026-08-14, same cached bars as
[B22E](B22E_INTRADAY_MOMENTUM_RESULT.md), split/dividend adjusted.

---

## What I claimed, and what is actually true

**What I said** (in [B22D §7](B22D_INTRADAY_MOMENTUM_CANDIDATE.md) and to the owner): *"essentially the
entire long-run equity risk premium is earned overnight … intraday returns are on average slightly
negative,"* and therefore *"a day trader operates entirely inside the window where the market's expected
return is negative."*

**What the data says for SPY over the last decade:**

| leg | ann. return | ann. vol | **Sharpe** | t |
|---|---|---|---|---|
| **overnight** (prev close → 09:30 open) | **+10.06%** | 11.55% | **+0.87** | +2.83 |
| **intraday** (09:30 open → 16:00 close) | **+5.79%** | 13.36% | **+0.43** | +1.41 |
| full day (close → close) | +15.88% | 17.82% | +0.89 | +2.90 |

**Intraday is positive, not negative.** It contributed **+5.79%/yr** — about 36% of the arithmetic
annual return. The strong form of the claim is false for this instrument over this period, and the
"structural headwind" framing I built on it was overstated.

## What survives the correction, and it is not nothing

**Overnight is roughly twice as risk-efficient as intraday: Sharpe 0.87 vs 0.43.** Overnight delivers
63% of the arithmetic annual return while carrying 65% of the daily volatility budget — and it does so
in a window that requires no trading at all.

So the defensible statement is not *"intraday has negative expectancy"* but:

> **Per unit of risk, the intraday session pays about half what the overnight session pays — and the
> overnight half is available for free by simply holding, with no execution cost, no timing, and no
> skill.**

That is a weaker claim than the one I made, and it still argues that an intraday strategy must clear a
real bar: it has to beat not just zero but the risk-adjusted return of doing nothing.

## Year by year

| year | overnight | intraday | full day |
|---|---|---|---|
| 2016 | −1.05% | **+14.23%** | +13.03% |
| 2017 | +13.51% | +7.21% | +21.70% |
| 2018 | +15.32% | **−17.56%** | −4.92% |
| 2019 | +14.31% | +14.71% | +31.13% |
| 2020 | +12.28% | +5.37% | +18.31% |
| 2021 | +18.14% | +8.95% | +28.72% |
| 2022 | −13.83% | −5.02% | −18.16% |
| 2023 | +6.02% | **+19.02%** | +26.18% |
| 2024 | **+25.03%** | −0.14% | +24.86% |
| 2025 | +9.97% | +7.05% | +17.72% |
| 2026 (partial) | +9.46% | +4.57% | +14.46% |

Intraday is negative in only 3 of 11 years. The two legs diverge violently — 2018 (+15.3 overnight,
−17.6 intraday) and 2024 (+25.0 overnight, −0.1 intraday) — which is why the aggregate claim needs
measuring rather than citing.

## Why the literature and this measurement disagree

They are not measuring the same thing, and I conflated them.

- **Lou, Polk & Skouras (JFE 2019)** and the surrounding literature study the **cross-section of US
  stocks** over long samples, and their striking results concern *anomaly portfolios* — momentum,
  value, and so on — whose premia they find are overnight phenomena with intraday returns of opposite
  sign.
- **This measures a single broad-market ETF over one recent decade.** SPY is not an anomaly portfolio
  and 2016–2026 is not 1993–2013.

The literature claim may be perfectly correct on its own terms. **It simply does not license the
sentence I wrote about SPY**, and the honest fix is to state what we measured rather than to soften
the citation.

## The methodological point, recorded because it keeps recurring

This is the same error class as the fee-distribution mistake (reading a truncated tail as the venue),
the 85× depth mistake (comparing against a virtual reserve), and the obs50 leak. **A cited result was
imported without checking that its sample and instrument matched the use I put it to.** The cost here
was low only because the data to check it was already sitting in the cache from B22E.

**Rule to carry forward:** a literature claim used as an *argument for a decision* gets measured on our
own instrument and period before it is allowed to carry weight. Citing is not measuring.

---

*Reproducible from `research/data/spy_30min_bars.json` (sha256 aabf1bd4…), the same cache as B22E.*
