# T15 — result: PEAD, post-earnings-announcement drift (shortlist candidate #12)

## VERDICT: **DEAD — BY INSUFFICIENT POWER.** STEP 2 was not run and 2022–2026 was not spent.

The power gate was written and hashed **before the census was executed**, on the literature's own
effect size, and it is the gate that decides. It fails by **4.93×**.

| gate, frozen before the number existed | held-out result | outcome |
|---|---|---|
| **MDE at 80 % power ≤ 0.90 %** (Martineau's pooled full-sample large-cap random-walk decile spread over `BHAR[2,60]`) | **MDE = 4.44 %** on **5,991** held-out events in **18** earnings seasons | **FAILS by 4.93×** |

**Headline, and the number worth carrying forward:** this candidate's held-out window cannot
detect **any version of PEAD the literature reports for large caps — including the classic-era
one.** It could detect Foster, Olsen & Shevlin's 1984 5 % decile spread. It could **not** detect
Martineau's own 1973–1990 estimate (2.7 %), his pooled 1973–2019 estimate (0.90 %), or Chordia et
al.'s most-liquid-quintile figure (0.12 %). Closing the gap needs **≈ 146,000 events** against the
**5,991** we have: **113 years** of collection at this universe width, or a universe of **12,164
names** — more than the entire investable US listed market.

**And the scoping arithmetic that promoted this candidate was wrong by 9.8×.**
`DATA_PURCHASE_SCOPE.md` §5b put the event-level MDE at **0.29–0.53 %** and called PEAD *"the only
remaining candidate that clears a power census"*. Measured, it is **4.44 %**. §4 below decomposes
the 9.8× into three multiplicative errors, and the largest of them has nothing to do with earnings
seasons.

---

## 0. Provenance

| | |
|---|---|
| **power gate, frozen first** | `research/trading_bot/T15_POWER_GATE.md` |
| sha256, taken 2026-08-17 12:29:30 UTC with `T15_POWER_CENSUS.json` verified absent | `76f712f7d03af75b65f193bb74f5c6f312a30c03be03d520ab09ecbf90de2b89` |
| collection + census (no signal, no sort, no surprise anywhere in it) | `scripts/t15_pead.py` |
| machine-readable census | `research/trading_bot/T15_POWER_CENSUS.json` |
| machine-readable verdict (**refuses to run against a changed gate hash**) | `research/trading_bot/T15_RESULT.json` |
| data cache (SEC + Alpaca, all free) | `research/data/t15_cache/` |
| costs | `scripts/trading_bot/costs.py` — the T6-corrected per-side model, M0 auction rail |

**No pre-registration exists and none should.** `T15_POWER_GATE.md` §4 says in advance that a
failed gate means STEP 2 is not run: no rule is frozen, no held-out number is produced, and the
2022–2026 window is not burned. That is the T9 lesson (`FINDINGS.md` §5g) applied *before* the
expense instead of after it.

**Everything computed before the gate was hashed was a count.** Universe membership, CIK matches,
filing timestamps, XBRL fact dates, bar presence. No price had been divided by any other price;
`T15_POWER_CENSUS.json` did not exist and its absence was checked in the same shell command that
took the hash.

**Nothing in the census is sorted on a surprise.** The dispersion input is the *unconditional*
market-adjusted event-window return, and the two placebo books are signal-free by construction.
There is no configuration here that could have been tuned toward a verdict.

---

## 1. What was built — and it works, which is worth saying plainly

The free-data claim in `DATA_PURCHASE_SCOPE.md` §5a is **substantially correct and is now
verified end to end**. Both missing pieces exist, are free, and are point-in-time.

| piece | source | result |
|---|---|---|
| earnings announcement calendar, **to the second** | `data.sec.gov/submissions/CIK*.json`, 8-K **item 2.02** with `acceptanceDateTime` | **72,649** item-2.02 8-Ks over 1,264 CIKs, **0 fetch failures** |
| point-in-time EPS | `data.sec.gov/api/xbrl/companyconcept/.../EarningsPerShareDiluted` | **196,974** facts, each carrying its `filed` date; 140 of 1,264 CIKs (11 %) never use the tag |
| universe | rebuilt from T3's cached monthly bars, no new spend | 128 months, point-in-time top-500 ADV |
| prices | Alpaca adjusted daily bars | 1,648 symbols |

**Session placement, measured rather than assumed** — the discipline T3 and T10 each failed at
first pass (`FINDINGS.md` §5e, §5h):

| placement of the release, by acceptance timestamp in ET | share |
|---|---|
| **pre-open** (before 09:30) | 7,295 — **52.3 %** |
| **post-close** (at/after 16:00) | 5,995 — **43.0 %** |
| intraday | 658 — **4.7 %** |
| outside any session | 2 |

Ninety-five per cent of large-cap earnings releases land outside the session. There is no timing
assumption anywhere in this test, which is exactly what the 8-K route buys.

---

## 2. The census — every number is a count

### 2a. Universe → CIK

| step | count |
|---|---|
| distinct symbols ever in the point-in-time top-500-ADV universe, 2016-01 → 2026-08 | **1,648** |
| mapped to a CIK (1,206 by ticker, 77 by issuer name against EDGAR's full name index) | **1,283** → 1,264 distinct CIKs |
| unmapped | 365 |
| …of which **ETF-shaped** (correctly excluded — an ETF has no item 2.02) | **323** |
| …of which **operating companies with no recoverable CIK** | **42** |

**The 42 are all delisted names** — AABA, ANDV, ARRS, CAVM, CELG, DWDP, ESRX, RHT, SHPG, … SEC's
`company_tickers.json` carries only current registrants and EDGAR's ticker lookup returns nothing
for a dead ticker. It is a **3.2 % symbol-level loss concentrated in names that stopped existing**,
i.e. survivorship-flavoured, and it is stated rather than hidden. It does not move the verdict:
adding 3.2 % more events changes the MDE by 1.6 %.

### 2b. Events

| step | count |
|---|---|
| item-2.02 8-Ks for these CIKs, 2016-01-04 → 2026-08-14, after de-duplicating re-issues within 45 days (−2,792) | 38,032 |
| **the symbol was not in the top-500 universe in the month of the announcement** | −24,082 |
| the 60-session hold would run past the data end | −355 |
| CIK has no item-2.02 filing at all (203 issuers) | — |
| **usable events** | **13,950** |
| priced on both legs (adjusted closes, entry and exit) | **13,907** |
| …design window 2016–2021 | 7,916 |
| …**held out 2022-01-03 → 2026-08-14** | **5,991** |

**The arrival rate is 1,297 events/yr, not the 2,000 the scoping document assumed.** A top-500-*ADV*
universe is not 500 operating companies four times a year: it contains ETFs, it contains dual-class
listings of one issuer, and membership churns month to month so a name's announcement often falls
in a month it was outside the screen.

### 2c. Earnings seasons — 42 in the full sample, **18 held out**

Events per calendar quarter are remarkably flat, 281–357, mean **331**:

| | 2022Q1 | Q2 | Q3 | Q4 | 2023Q1 | Q2 | Q3 | Q4 | 2024Q1 | Q2 | Q3 | Q4 | 2025Q1 | Q2 | Q3 | Q4 | 2026Q1 | Q2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| events | 318 | 325 | 327 | 333 | 336 | 340 | 347 | 340 | 338 | 335 | 344 | 343 | 343 | 332 | 350 | 346 | 334 | 281 |

---

## 3. The point-in-time SUE — the second thing this census settles, and it is GOOD news with a hole

The 8-K item 2.02 carries the earnings number in a **press-release exhibit that is not
XBRL-tagged**. The structured fact arrives with the periodic report. So: *how late?*

**Measured, `filed`(XBRL) − `filed`(8-K), n = 10,481:**

| min | p05 | p25 | **median** | p75 | p95 | mean |
|---|---|---|---|---|---|---|
| −5 | 0 | 0 | **1 day** | 10 | 29 | 15.0 |

**34.7 % of announced quarters are already in XBRL on or before the 8-K date, and 51.6 % within
one day.** Large-cap issuers file the 10-Q essentially alongside the release. The fear that a
free-XBRL SUE would be 30–40 days stale is **wrong for this universe**, and that is a real,
reusable finding.

**The hole is fiscal Q4.** 3,469 of 13,950 events (**24.9 %**) have **no quarterly EPS fact within
60 days of the 8-K at all** — because the 10-K tags the **annual** period and no 90-day fact for
the fourth quarter is ever filed. The form actually carrying the fact:

| 10-Q | 10-K | 10-K/A | 8-K | other |
|---|---|---|---|---|
| 9,147 | 1,324 | 4 | **3** | 3 |

**Three.** Item-2.02 8-Ks essentially never carry XBRL-tagged EPS, which settles that route.

**Strictly point-in-time availability at the entry decision:**

| requirement, all `filed` ≤ entry day | events | share of 13,950 |
|---|---|---|
| announced quarter's EPS public | 4,957 | 35.5 % |
| **+ the same quarter one year earlier + ≥ 8 prior quarters** (a full seasonal-random-walk SUE) | **4,723** | **33.9 %** |

> **This makes the power problem worse, never better.** The gate below is computed on **all 5,991**
> held-out events — i.e. it *grants* the strategy a surprise it does not have for two-thirds of
> them. It fails anyway, by 4.93×. Restricting to the 33.9 % with a genuine point-in-time SUE
> would raise the MDE by a further ~1.7×.

---

## 4. THE GATE — and the decomposition of the 9.8× error that promoted this candidate

### 4a. The numbers

Held out: **5,991 events, 18 seasons, 591 decile pairs**, per-event 60-session market-adjusted
buy-and-hold dispersion **σ = 18.76 %**.

| framing | held-out MDE at 80 % power | vs the 0.90 % gate |
|---|---|---|
| naive — every event independent (the scoping document's framing) | **3.06 %** | fails 3.4× |
| **season block bootstrap, PERSISTENT placebo, 1-season blocks — the declared primary** | **4.44 %** | **fails 4.93×** |
| season block bootstrap, IID placebo | 4.35 % | fails 4.8× |
| within-season rank regression on **all** events — the most powerful framing that exists | **3.33 %** | fails 3.7× |

**No framing passes.** The verdict does not depend on the design choice, which is why all four
were declared in advance.

### 4b. Where the scoping document's 0.29–0.53 % went

`DATA_PURCHASE_SCOPE.md` §5b computed `2.80 × 0.155 / √9,200 = 0.45 %`. Three multiplicative
errors, in order of size:

| error | factor |
|---|---|
| **A decile long-short book does not get n observations — it gets n/5, and their difference has twice the variance.** `SE = σ√2/√n_pairs` with `n_pairs = 591`, not `σ/√5,991` | **×5.58** (combined with the event-count error below) |
| **the event count is 5,991, not 9,200** — 1,297/yr, not 2,000 | *(folded into the 5.58 above)* |
| σ is **18.76 %**, not the 15.5 % borrowed from T9's spin-off instrument | **×1.21** |
| **earnings-season clustering**, the one the document did flag | **×1.45** |
| **total** | **×9.80** ⇒ 0.45 % → **4.44 %** |

> **The lesson is the first row, and it is transferable.** The season-clustering worry the document
> raised was real and cost **1.45×**. The error it did *not* raise — that a **decile** book spends
> a fifth of its sample and doubles its variance — cost **5.58×**, four times as much. *Count the
> observations the ESTIMATOR uses, not the observations the dataset has.*

### 4c. The clustering, now measured rather than feared

| | |
|---|---|
| naive SE (events independent) | 0.01092 |
| season block bootstrap SE | 0.01584 |
| **variance inflation factor** | **2.11** |
| **effective independent decile pairs** | **280 of 591** |

Block lengths of 1, 2 and 4 seasons agree to within 3 % — the answer does not depend on the block
length. The inflation is **not** the market factor (a within-season long-short book cancels it by
construction): it is **volatility heterogeneity across seasons**, a handful of which — 2022's
drawdown above all — carry most of the dispersion. A block bootstrap finds this; a pooled σ hides
it.

### 4d. It is not an outlier artefact

| treatment of the held-out event returns | per-event σ | naive MDE |
|---|---|---|
| raw | 18.76 % | 3.06 % |
| winsorised 1 % | 16.76 % | 2.73 % |
| winsorised 2.5 % | 15.20 % | 2.48 % |
| winsorised 5 % (aggressive, and would have to be declared) | 13.73 % | 2.24 % |

Even at 5 % winsorisation the clustered MDE is ≈ **3.25 %**, failing the gate by 3.6×.

### 4e. Horizon ladder — declared in advance, and no horizon rescues it

| H (sessions) | σ | MDE, primary framing |
|---|---|---|
| 5 | 5.69 % | **1.29 %** |
| 21 | 10.25 % | **2.30 %** |
| **60 (primary)** | 18.76 % | **4.44 %** |

H = 5 is the closest call. **It is not a rescue**, because 0.90 % is Martineau's `BHAR[2,60]`
number and cannot be reused at `[2,5]`: his `[2,5]` coefficient for all-but-microcap stocks is
**not distinguishable from zero in any period after 1990**, and the only surviving short-horizon
drift he finds is in **microcaps**, whose measured spreads in this programme are **120 bp/leg**
(T1 §2d). Trading a 1.29 %-detectable window for a benchmark of approximately zero is not a
powered test; it is a differently-shaped negative.

---

## 5. What would be needed — the T9-shaped finding

To reach `MDE = 0.90 %` the variance must fall **24.3×**:

| | |
|---|---|
| decile pairs required | **14,377** (have 591) |
| **events required** | **145,743** (have 5,991) |
| observed arrival rate | **1,297 events/yr** |
| **years of prospective collection at this universe width** | **113** |
| **or, universe width required at this window length** | **12,164 names** |

There are roughly four thousand US-listed operating companies with meaningful volume. **The width
route does not exist**, and the part of it that does — going down into small and microcap names —
is the exact region where Chordia, Goyal, Sadka, Sadka & Shivakumar (2009) measured that
*transaction costs consume 63 % to 100 % of gross profits*, and where this programme's own T1 §2d
measured 120 bp per leg.

**What the window CAN detect, against what the literature reports:**

| effect | size over 60 sessions | detectable at 80 % power? |
|---|---|---|
| Foster, Olsen & Shevlin (1984) / Bernard & Thomas (1989), classic era, all sizes | ≈ 5 % | **yes** — and the literature says it is gone |
| Martineau (2021), all-but-microcap, random-walk surprise, **1973–1990** | 2.7 % | **no** |
| Martineau (2021), all-but-microcap, random-walk surprise, **pooled 1973–2019** | 0.90 % | **no** |
| Chordia et al. (2009), **most liquid quintile** | ≈ 0.12 % | **no** |

---

## 6. Friction — measured, and irrelevant, which is itself the finding

Per event, for the trade the gate describes (one MOC in, one MOC out, 60 sessions ≈ 87 calendar
days), priced with the T6-corrected per-side model on M0's measured auction rail:

| component | charge |
|---|---|
| entry + exit half-spread, MOC/MOO, ADV tier C (rank 201–500) | **0 bp** (M0: official closing print on 100 % of 945 sampled symbol-days, non-fill provision 0.0000 bp) |
| SEC §31, one sale leg per event, top of the 2016–2026 range | 0.278 bp |
| FINRA TAF, $0.000166/share sold | ≈ 0.02 bp |
| borrow, 33 bp/yr (B22G measured ETB general collateral) × 87 days, on the short half of the book | 3.93 bp |
| **total, auction rail** | **4.23 bp** |
| total, +1 measured half-spread per leg (T3's 1.43 bp, 2022–2026) | 7.09 bp |

| | |
|---|---|
| per-event dispersion | **1,876 bp** |
| **dispersion ÷ friction** | **444×** |

**T9's inversion, three times more extreme.** T3 died at 6.8 bp of gross against 1.4 bp of
friction; T9's ratio was 139×; T15's is **444×**. Friction is not the constraint here and no
execution improvement touches the verdict. **The binding constraint is sample size, for the second
time in this programme.**

*The M0 caveat still stands and is stated rather than assumed away:* the zero half-spread is the
**tape** half of M0. Whether a broker's on-close order joins the cross is M0's **C4**, still
unperformed. At 444× it does not matter to *this* candidate — which is the first time that has
been true.

---

## 7. The literature prior — recorded because it is evidence, and it was not what decided this

The gate decided this. But the prior deserves recording, because it is unusually direct and it
matches the instrument exactly.

**Martineau, C. (2021), "Rest in Peace Post-Earnings Announcement Drift", *Critical Finance
Review*** (accessed 2026-08-17, `cfr.ivo-welch.org/published/papers/martineau2021rest.pdf`). The
paper's surprise measure is `(EPS_t − EPS_{t−4}) / P` — **the seasonal random walk this candidate
would have built** — and its dependent variable is `BHAR[2,60]`.

Table 4, Panel B, **all-but-microcap** stocks, coefficient on the surprise decile rank:

| full 1973–2019 | 1973–90 | 1991–95 | 1996–2000 | 2001–05 | 2006–10 | 2011–15 | **2016–19** |
|---|---|---|---|---|---|---|---|
| 0.001** | 0.003*** | 0.001* | −0.002 | −0.000 | −0.003 | −0.000 | **−0.003*** |

> Abstract: *"In modern financial markets, stock prices fully reflect earnings surprises on the
> announcement date, leading to the disappearance of post-earnings announcement drifts (PEAD).
> **For large stocks, PEAD have been non-existent since 2006.**"*

**Every subperiod since 1996 is zero or negative on exactly this surprise, in exactly this size
bucket, at exactly this horizon**, and 2016–2019 overlaps this programme's own design window.
`DATA_PURCHASE_SCOPE.md` §5c had already written *"a free test of a famous decayed anomaly is most
likely an eighth honest negative"* and put `P(pass) ≈ 0.08`. That estimate was, if anything,
generous.

---

## 8. Corrections this result makes to `DATA_PURCHASE_SCOPE.md`

Recorded here rather than by silently editing that document, because **every one of the errors was
flattering** — the pattern `FINDINGS.md` §6 says to watch for.

| §5b claim | measured |
|---|---|
| "≈ 2,000 earnings events/yr" | **1,297/yr** in the point-in-time top-500-ADV universe |
| "≈ 9,200 held-out events" | **5,991** |
| "event-level MDE at 80 % power is 0.29 %–0.53 %" | **4.44 %** — the error is 9.8×, and §4b decomposes it |
| "**below** the decayed large-cap PEAD effect the literature reports" | **4.9× above** the most generous literature figure for this instrument |
| "the only remaining candidate that clears a power census" | **it does not clear one** |
| §5a "per-company series back to 2006 each tagged with its `filed` date, so the panel is point-in-time by construction" | **true, and better than feared** — median lag 1 day — **but** 24.9 % of events (fiscal Q4) have no quarterly fact at all, and a full point-in-time SUE exists for **33.9 %** of events |
| §7 ranking PEAD **#1** on EV-per-dollar with an "undefined / infinite" denominator | **a free test that cannot detect the effect has EV zero, not infinite.** Dividing by a zero cost is not the right instrument; the right one is the power census, and it costs an hour |

---

## 9. What is worth keeping

1. **A universe-wide, free, point-in-time US earnings-announcement calendar with second-resolution
   session placement now exists in this repository** — 72,649 item-2.02 8-Ks, `research/data/t15_cache/`,
   rebuilt by `python scripts/t15_pead.py collect`. Any future candidate that needs to *avoid*
   earnings dates (an event filter rather than an event edge) gets it for nothing. That is
   probably its real use.
2. **The XBRL filing lag for large caps is 1 day at the median**, not the 30–40 days assumed. Free
   point-in-time fundamentals are more usable than this programme believed.
3. **The decile-book power rule.** A quantile long-short book estimates its mean from `n/5`
   observations with twice the variance of a single leg: `SE = σ√2 / √(n/10)`. Applying an
   all-events MDE to a decile spread overstates power by **√(2·n/n_pairs)** — here 5.58×. This is
   now the largest single scoping error in the programme's history and it is arithmetic, not
   opinion.
4. **A block bootstrap on the clustering unit is worth running even when theory says the cluster
   cancels.** A within-season long-short book cancels the season's *market* move — and still
   carries a **2.11×** variance inflation from volatility heterogeneity *across* seasons.
5. **A collection bug worth remembering:** requesting `Accept-Encoding: gzip` from `data.sec.gov`
   and then calling `.decode()` on the body raises `UnicodeDecodeError` on every response —
   urllib does not decompress. Every request burned its eight retries and the failure looked
   **exactly** like rate limiting. Two throttle rewrites were spent on the wrong diagnosis.
   *`FINDINGS.md` §8: verify the diagnostic, not just the system.*

---

## 10. Next candidate — and a process recommendation that outranks it

**The candidate list is now six deep in honest negatives** (#1 T3, #2 T7, #4 T9, #6 T10, #7 T11,
plus T13's risk pivot), and **#12 is the seventh — dead before it was tested, for an hour's work
rather than a slice's.** The gate did its job.

What remains, ranked by this seat, with the reason:

1. **M0's C4 — the live auction-fill measurement.** Still unperformed. Now load-bearing for five
   dead candidates and for anything that ever trades. Bounded, days not years, and the cheapest
   outstanding item in the programme. **T15 does not need it (444×) and that is not a reason to
   keep deferring it.**
2. **The free forward panels — FINRA short interest and the IBKR borrow-fee mirror — started as a
   daily cron *now*.** `DATA_PURCHASE_SCOPE.md` §8a ranked this third and it is the only action on
   the whole list that *creates* an asset: history that does not exist can only be made by
   starting. It is not a test and should not be scored as one.
3. **#9 short interest (the free half)** — the scope document's rank 2. **Run a power census
   first**, and run it on the *estimator* this time: a bi-monthly cross-sectional sort over 4.6
   held-out years is ~110 portfolio observations, which is a T10-shaped Sharpe-certification
   problem, not a T15-shaped event-count one. The census is an hour either way.

> **The process recommendation, which this seat rates above any of the three.** T9 and T15 have now
> both died on a power census that took **under two hours** and that neither candidate's scoring
> document had run. **Make the power census a mandatory, pre-registered gate on every future
> candidate, computed on the estimator that will actually be used, before any harness is written.**
> It has now killed two candidates for a combined cost of one afternoon, against the days each
> harness would have taken — and, more importantly, it did so **without burning the held-out
> window**, which is the only genuinely scarce resource this programme has.

**Which of the three, and whether the shortlist is worth continuing at all, is an owner scope
call** — `DECISIONS.md`'s standing rule, and the honest position after seven negatives is that the
question "is there a *different kind* of candidate" now outranks "which candidate is next".
