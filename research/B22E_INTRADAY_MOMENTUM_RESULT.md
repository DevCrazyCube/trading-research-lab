# B22E — intraday momentum, tested out of sample: **DEAD**

**This is our own measurement, not a literature claim.** Run 16 Aug 2026 against the rule frozen in
[B22D](B22D_INTRADAY_MOMENTUM_CANDIDATE.md), using the script committed *before* the data was fetched
(`scripts/b22d_intraday_momentum_test.py`, commit made prior to execution).

**Verdict: the effect is not present out of sample, and its conditional structure is inverted.**

---

## The test

Gao/Han/Li/Zhou's rule, unmodified: `r1` = previous close → 10:00 ET return; long SPY at 15:30 if
`r1 > 0`, short if `r1 < 0`, exit at the 16:00 close.

**2,668 observations, 2016-01-05 to 2026-08-14.** Every one after the paper's sample (ends 2013) and
2,000+ of them after publication (2018). 1,492 long, 1,169 short, 7 flat.

## The result

| entry half-spread | ann. return | ann. vol | Sharpe | t-stat | win % |
|---|---|---|---|---|---|
| **0.0 bp (free)** | **−0.71%** | 4.92% | −0.14 | −0.47 | 49.6% |
| 0.6 bp (the paper's own cost) | −2.22% | 4.92% | −0.45 | −1.47 | 47.4% |
| 1.0 bp | −3.22% | 4.92% | −0.66 | −2.13 | 46.4% |
| 2.0 bp | −5.74% | 4.92% | −1.17 | −3.79 | 43.1% |

**It loses money at zero transaction cost.** This is not the cost story that killed the other four
candidates in this programme. The gross edge is simply absent.

**Nine of eleven years negative** at the paper's own cost assumption. Only 2020 (+5.16%) and 2023
(+3.38%) are positive — and it was already negative in **2016, 2017, 2018 and 2019**, the first two of
which are *before* publication.

| year | strategy | year | strategy |
|---|---|---|---|
| 2016 | −2.69% | 2022 | −6.28% |
| 2017 | −4.08% | 2023 | +3.38% |
| 2018 | −3.55% | 2024 | −2.15% |
| 2019 | −1.81% | 2025 | −1.71% |
| 2020 | +5.16% | 2026 (partial) | −0.09% |
| 2021 | −9.82% | | |

## The implementation is validated, so the negative result is real

A negative result from a broken harness is worthless, so this was checked before being believed:

| check | result |
|---|---|
| session count | **2,669** complete vs ~2,671 expected (252/yr × 10.6yr); 1 dropped |
| **reproduces the paper's own benchmark** | always-long 15:30–16:00 = **−1.13%/yr**, against Gao's **−0.74%/yr** on 1993–2013 |
| SPY close-to-close | +15.88%/yr, Sharpe 0.89 — plausible for 2016–2026 |
| `r1` dispersion | sd 0.740% vs 1.123% full-day, ratio 0.66 — a first half-hour should be a fraction of a day |
| price levels | dividend-adjusted, consistent with ~1.5%/yr yield accumulated backwards |

The second row is the important one. **The paper's own unconditional benchmark reproduces
independently**, which means the last-half-hour return — the quantity the whole strategy is built on —
is being computed correctly. The machinery is right. The strategy loses.

## Why it fails, decomposed

| condition | n | mean | annualised | t |
|---|---|---|---|---|
| all days | 2,668 | −0.45 bp | −1.13% | −0.74 |
| morning UP → paper says long | 1,492 | −0.65 bp | −1.65% | −0.95 |
| morning DOWN → paper says short | 1,169 | −0.19 bp | −0.48% | −0.18 |

> **UP minus DOWN = −0.46 bp/day (−1.17%/yr). The paper's entire claim is that this is positive. Out
> of sample it is negative.**

A raw correlation of `corr(r1, last_half_hour) = +0.0385, t = +1.99` looks like weak survival, and
would have been easy to report as such. **It is not.** That correlation is driven by magnitude and
outliers; the strategy trades the *sign*, and the sign-conditioned spread is negative. Reporting the
correlation without the conditional means would have been the flattering error available here.

**And the paper's own conditional prediction inverts.** Gao et al. state the effect is *stronger* on
high-volatility days:

| |r1| tercile | annualised | t |
|---|---|---|
| smallest | **+1.87%** | +1.01 |
| middle | −0.22% | −0.11 |
| largest | **−3.77%** | −1.04 |

Exactly backwards. This matters more than the flat aggregate: an effect that has merely decayed gets
weaker everywhere, but an effect whose own cross-sectional signature has flipped was either never
structural or has been arbitraged into its opposite.

**Year-by-year correlation is noise around zero**: +0.042, −0.046, −0.038, −0.005, **+0.161**,
**−0.225**, −0.064, +0.055, −0.061, −0.062, +0.045. Only two years exceed |t| = 2, and they have
opposite signs (2020: +2.59; 2021: −3.65).

## Against the pre-committed interpretation

B22D §5 fixed this in advance: *"the test can show the effect INTACT (t ≈ 3.5) or DEAD, but cannot
certify a decayed-but-alive version (t ≈ 1.4). An ambiguous result is to be reported as ambiguous."*

**This is not ambiguous.** The point estimate is negative at zero cost, the sign-conditioned spread is
negative, nine of eleven years lose, and the paper's own conditional structure is inverted. Every
diagnostic points the same way.

Strictly, t = −0.47 at zero cost means *"cannot reject zero"* rather than *"significantly negative."*
That distinction does not rescue anything: a strategy needs to be positive **and** clear its costs.
This is negative before costs.

## What this does and does not say

**Does not say the 1993–2013 finding was wrong.** It is a JFE paper with a mechanism and out-of-sample
support inside its own era. The honest reading is that the effect existed and no longer does.

**A likely mechanism for its disappearance, from an independent source.** The New York Fed published
*[The Disappearing Overnight Drift](https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/)*
in **July 2026**: the 2:00–3:00 ET window that generated **~3.7%/yr** over 1998–2020 has been **flat
since 2021**, and they attribute it to *compression in end-of-day imbalance dispersion* — the standard
deviation of end-of-day relative signed volume **fell from 6.5% to 2.9%**.

**That is the same underlying flow.** Intraday momentum's proposed mechanism (Bogousslavsky's
infrequent rebalancing) is *also* end-of-day institutional rebalancing. If the dispersion of
end-of-day imbalances halved, both effects should weaken together — and both did.

The Fed post also records that an ETF launched in June 2022 to harvest the overnight drift **closed
fourteen months later**. Real money, real fund, same trade, same outcome.

## The cost of finding this out

About an hour, and $0 of data. The apparatus did exactly what it exists for: a candidate that looked
extremely strong on paper — top-3 journal, explicit cost treatment, a named mechanism, zero free
parameters — was killed by one out-of-sample test before a cent was risked on it.

**This is the fifth domain to fail, but it fails differently.** Memecoins, Binance, MNQ futures and
individual equities all had a real gross edge that friction consumed. Here there is no gross edge to
consume. That distinction matters for what we try next: cheaper execution cannot rescue this one.

---

*Data: SPY 30-minute bars, Alpaca SIP feed, split/dividend adjusted, cached at
`research/data/spy_30min_bars.json` (83,851 bars). Reproducible via
`python scripts/b22d_intraday_momentum_test.py`.*
