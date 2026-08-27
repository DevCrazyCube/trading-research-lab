# T15 — the POWER GATE for candidate #12 (PEAD), declared BEFORE the census is run

**Written 2026-08-17, before `scripts/t15_pead.py census` has ever been executed.** At the moment
this file is hashed, `research/trading_bot/T15_POWER_CENSUS.json` does not exist, no minimum
detectable effect has been computed, no abnormal return has been formed, and no surprise, rank,
decile or portfolio exists anywhere on disk. The only things done so far are **collection**: a
point-in-time universe rebuilt from T3's cached monthly bars, a ticker→CIK map, 8-K item-2.02
filing metadata, XBRL `EarningsPerShareDiluted` facts, and adjusted daily bars. Counts only.

This file exists because `FINDINGS.md` §5g's earned rule is *count the events before building the
harness*, and because a power threshold chosen after seeing the MDE is not a threshold. T9
declared its gate first and the gate is what decided it; T15 does the same.

---

## 1. What is being tested

Candidate **#12** in `EDGE_SHORTLIST.md`. The shortlist's own null, written 2026-08-16 before any
earnings datum was touched and quoted here as the a-priori commitment it is:

> **"Post-announcement market-adjusted drift is zero conditional on surprise decile."**

`DATA_PURCHASE_SCOPE.md` §5 re-scored it from 9 to 13 on the ground that its data is free and that
it is *"the only remaining candidate that clears a power census"*, while explicitly flagging that
the clearing had **not been demonstrated**:

> *"The event-level MDE treats 9,200 events as independent. **They are not** — they cluster into
> four earnings seasons a year… resolving that is an hour of arithmetic with a block bootstrap,
> not a backtest."*

This file fixes the arithmetic's acceptance criterion before the arithmetic runs.

## 2. The instrument the gate is computed on

- **Universe:** point-in-time top-500 by prior-month dollar ADV, raw close > $5, ADV > $20 M —
  the identical screen T3 and T10 used, rebuilt from T3's cached monthly bars.
- **Event:** an 8-K carrying **item 2.02**, placed in the session by its
  `acceptanceDateTime`, not by its filing date.
- **Entry:** the closing auction of the first session whose regular hours begin after the
  acceptance timestamp (`D0`). The announcement jump is therefore **excluded** — this measures
  drift, not reaction, which is what the null of §1 is about.
- **Exit:** the closing auction `H` sessions later. `H ∈ {5, 21, 60}`; **the primary is H = 60**,
  which is Foster, Olsen & Shevlin's window and Martineau's `BHAR[2,60]`.
- **Per-event return:** market-adjusted buy-and-hold, SPY as the benchmark, adjusted
  (total-return) closes on both legs.
- **Book:** long the top decile / short the bottom decile of the surprise **within each earnings
  season**, equal weight — the shortlist's own "conditional on surprise decile".

## 3. The benchmark effect — the literature's own number, for OUR universe and OUR surprise

The gate compares the MDE against the effect the literature reports **for the same instrument**:
a *seasonal-random-walk* surprise (no analyst estimates), on *large, liquid* stocks, over
`BHAR[2,60]`. Three published anchors, most to least generous:

| source | what it measures | figure, converted to a 60-session decile spread |
|---|---|---|
| Foster, Olsen & Shevlin (1984); Bernard & Thomas (1989) — the classic era, all sizes | SUE decile hedge over 60 days | **≈ +4 % to +6 %** |
| **Martineau (2021), *Critical Finance Review*, Table 4 Panel B** — random-walk surprise decile rank → `BHAR[2,60]`, **all-but-microcap**, pooled 1973–2019 | β = **0.001**\*\* per decile rank ⇒ 9 ranks | **+0.90 %** |
| Chordia, Goyal, G. Sadka, R. Sadka & Shivakumar (2009), *FAJ* — hedge return in the **most liquid** quintile | **0.04 %/month** value-weighted | **≈ +0.12 %** over ~3 months |

**The gate uses +0.90 %, the middle and deliberately charitable figure.** Reasons, stated now:

- The classic 4–6 % is from a period and a universe (all sizes, pre-decimalisation) that this test
  does not sample, so using it would make the gate trivially passable and meaningless.
- Chordia et al.'s 0.12 % is the *closest* match to our universe — top-500 ADV is more liquid than
  their most-liquid quintile — and using it would make the gate essentially impossible. Adopting
  the number that most favours the candidate is the honest direction to err.
- Martineau's 0.90 % is measured on **exactly** the surprise definition this candidate would build
  (`EPS_t − EPS_{t−4}`, no analysts), on **exactly** the horizon, over a **pooled** sample that
  includes the decades when PEAD worked. It is the most generous figure that is still *about this
  instrument*.

> **Recorded because it is evidence, not because it decides the gate:** Martineau's own
> subperiods for all-but-microcap stocks on this surprise are **0.001\* (1991–95), −0.002
> (1996–2000), −0.000 (2001–05), −0.003 (2006–10), −0.000 (2011–15), −0.003\* (2016–19)**, and the
> paper's abstract states *"For large stocks, PEAD have been non-existent since 2006."* The prior
> against this candidate is strong and pre-existing. **That is a reason to demand power, not a
> substitute for measuring it.**

## 4. THE GATE

Let `SE` be the standard error of the held-out mean per-event long/short decile-book return,
estimated by a **block bootstrap over earnings SEASON** (not over events), and let

```
MDE = 2.8016 x SE          # 80% power, two-sided alpha = 0.05
```

> **GATE.** The held-out test is adequately powered **only if `MDE ≤ 0.90 %`** at the primary
> horizon H = 60 — i.e. only if this instrument could detect Martineau's pooled full-sample
> large-cap random-walk PEAD eight times out of ten.

**If the gate fails, the verdict is `DEAD-BY-INSUFFICIENT-POWER` and STEP 2 is not run.** No
pre-registration is written, no rule is frozen, no held-out number is produced. A candidate whose
minimum detectable effect exceeds the literature's own effect size is dead before it is tested,
and 2022–2026 is not spent on it.

**If the gate passes**, STEP 2 proceeds exactly as T3/T7: a sha256 pre-registration written and
hashed **before** any surprise is computed, design 2016–2021 / held out 2022-01-03 → 2026-08-14,
and the four gates net mean > 0, permutation p < 0.05, DSR ≥ 0.95, honest T6/M0 per-side costs.

### 4a. Three ways the SE can be computed, and which one binds

All three are reported. The gate is decided by the **decile-book season block bootstrap under the
PERSISTENT placebo** — a signal-free score fixed per firm, which reproduces the fact that SUE is
autocorrelated (Bernard & Thomas 1989) and that the real book therefore holds many of the same
names season after season.

| framing | why it is reported |
|---|---|
| naive, every event independent | the framing `DATA_PURCHASE_SCOPE.md` §5b used to get 0.29–0.53 %; reported so the correction is visible |
| season block bootstrap, **IID** placebo | a fresh random score per event; factor-neutral within the season **by construction**, so it is a LOWER bound on SE and an OPTIMISTIC MDE |
| season block bootstrap, **PERSISTENT** placebo | one random score per firm, reused every season; carries the cross-season position overlap a real SUE book has. **This one decides.** |
| within-season **rank regression** on all events | the most powerful framing available (uses every event, not a fifth); reported so the gate cannot be accused of failing on a design choice |

Block lengths of **1, 2 and 4 seasons** are all reported; the primary is **1 season**.

### 4b. A second, independent kill condition — point-in-time SUE availability

The 8-K item 2.02 carries the earnings number in a press-release exhibit that is **not**
XBRL-tagged. The structured `EarningsPerShareDiluted` fact for the announced quarter normally
arrives with the **10-Q**. The census measures `filed(XBRL) − filed(8-K)` directly.

> **If the announced quarter's EPS is not public in XBRL by the entry day for the majority of
> events, then a point-in-time seasonal-random-walk SUE does not exist at the announcement**, and
> the candidate is `DEAD-BY-DATA-UNAVAILABILITY` on the free route regardless of power. Guardrail 1
> forbids the alternative — reading the number from a later filing and pretending it was known —
> and that is the classic PEAD leakage.

## 5. What has been computed at the moment this file is hashed

Counts, timestamps and file contents. **No price has been divided by any other price.** No
abnormal return, no surprise, no rank, no decile, no portfolio and no standard error exists on
disk. `research/trading_bot/T15_POWER_CENSUS.json` does not exist.

Collected: universe (128 months, 1,648 distinct symbols, 1,283 mapped to 1,264 CIKs, 365 unmapped
of which 323 are ETF-shaped), 72,649 item-2.02 8-Ks with acceptance timestamps, XBRL EPS facts,
and adjusted daily bars.

## 6. What this gate does not claim

- It does not claim 0.90 % is the true effect today. It is a *ceiling on the plausible*, chosen
  charitably. The evidence in §3's note says the true value is nearer zero.
- It does not claim the census is the whole test. Passing it licenses STEP 2 and nothing else.
- It does not claim the free SEC route is the only route. A paid analyst-consensus SUE is a
  different, stronger surprise measure — but it is a **different candidate**, it costs money, and
  `DATA_PURCHASE_SCOPE.md` §8b already rules that buying it before the free version is tested
  inverts the ordering.
