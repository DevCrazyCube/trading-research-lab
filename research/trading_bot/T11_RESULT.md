# T11 — result: cash-merger arbitrage spread (shortlist #7)

**Verdict: DEAD.** Formally `DEAD-BY-INSUFFICIENT-POWER` on the gate that fires first, and dead on
**all five** pre-registered gates independently. It also fails at **zero transaction cost**, which
means this is not a friction-floor death — it is an economics death.

Frozen rule: `T11_PREREGISTRATION.md`, sha256
**`b2aa8c60419a5058437ba26a1df6093d7c85a752f9010a16322edf6ae43e9880`**, hashed before any price was
divided by any other price. Runner `scripts/t11_evaluate.py` refuses to run against any other hash.
Design 2020–2021, held out **2022-01-03 → 2026-08-14**, run **once**.

Artifacts: `T11_EVENT_CENSUS.json` (counts, pre-freeze), `T11_HELDOUT_RESULT.json` (the single
held-out run), `T11_DIAGNOSTICS.json` (post-verdict, no gate re-run).

---

## 1. The five gates

| gate, all frozen in advance | held-out | outcome |
|---|---|---|
| **0. power** — MDE ≤ the literature's own effect | MDE **1.324 %** vs benchmark **1.179 %**; `n_required` **417**, available **330** | **fails** |
| **1. net mean excess over T-bills > 0** | **−0.827 %** per event, t **−0.985**, annualised **−2.81 %** | **fails** |
| **2. event-label permutation p < 0.05** | right tail **p = 0.876** (null median +0.876 %, null p95 +4.04 %) | **fails** |
| **3. DSR ≥ 0.95 at 3 declared trials** | **0.0391** — observed per-obs Sharpe **−0.0188** against a chance ceiling of **+0.0290**. At 12 trials, 0.0027 | **fails** |
| **4. break gate** — `b*(L = −25 %) > 10 %` | `b*` is **negative**: the book is already below T-bills before a single deal breaks | **fails** |

Primary horizon **H = 63 sessions**, selected on the design window by the criterion written into
§3 of the pre-registration (design t: H=5 **−0.92**, H=21 **+0.02**, H=63 **+1.80** → 63).

## 2. And it loses with every cost switched off

The B19P instrument, because the programme's habit is to ask it:

| half-spread rung (measured `h` = 2.41 bp) | mean net excess per event | t |
|---|---|---|
| 0 × h | **−0.779 %** | −0.93 |
| 0.5 × h | −0.803 % | −0.96 |
| **1 × h (primary)** | **−0.827 %** | **−0.985** |
| 2 × h | −0.875 % | −1.04 |
| 4 × h | −0.972 % | −1.16 |
| **frictionless (every cost zero, regulatory included)** | **−0.776 %** | **−0.92** |

The whole ladder spans 20 bp on a −83 bp number. **Friction is not what kills this one**, which
makes it different from T10 and from every memecoin result in `FINDINGS.md` §1. Measured
first-party half-spread of the merger targets themselves, `[15:59:59, 16:00:00) ET` on their actual
entry days: **2.41 bp** median held out (n = 1,048 symbol-days, 750 days), 2.64 bp in the design
window. Merger targets quote tightly — that was never the problem.

## 3. All three horizons, and the term structure

| H | n | mean net excess | t | mean days held | annualised | daily book: ann. return / Sharpe / maxDD |
|---|---|---|---|---|---|---|
| 5 | 481 | −1.370 % | −2.56 | 23.0 | −21.8 % | −44.9 % / −1.11 / −92.4 % |
| 21 | 481 | −1.815 % | −2.77 | 44.4 | −14.9 % | −22.7 % / −1.32 / −70.4 % |
| **63 (primary)** | **330** | **−0.827 %** | **−0.985** | 107.5 | **−2.81 %** | −3.6 % / −0.30 / −21.7 % |

Every horizon is negative, and the two short ones are negative at better than two standard errors.
The paired difference against SPY over the identical dates is **−2.36 % per event, t −2.58**.
Year by year at H = 63: 2022 **+1.76 %**, 2023 **−2.48 %**, 2024 **+0.37 %**, 2025 **−0.04 %**,
2026 **−4.00 %** — no persistence, both signs, nothing that looks like a premium.

## 4. What is actually in the left tail — and the honest correction to it

The task's guardrail was that the tail be modelled, not averaged away. It is, and looking at it
changes the interpretation of §1 substantially.

**The measured held-out distribution (H = 63, n = 330):** mean −0.83 %, median **+0.54 %**, sd
15.25 %, **skew −4.93**, kurtosis 30.7, **p01 −99.7 %**, min −102 %, 33.6 % of events lose.

The mean is *below the median* by 137 bp, and the whole gap is **13 events (3.9 % of the book)
whose entry price was more than 20 % above the cash they eventually received**, averaging
**−66.5 %** each. Named, they are `THRD LUNRW NNAVW ENBA MBT CDR DO MMP RVNC RVNC GLOP TRTN GAZ`,
and inspection finds **four definitional defects in this pre-registration**, not four economic
events:

1. **Mixed-consideration deals recorded as cash.** `DO`, `MMP` and `TRTN` appear in
   `stock_and_cash_mergers` within three sessions of the same effective date — `DO` at
   $5.65 cash **+ 0.2316 NE**, `MMP` at $25 **+ 0.667 OKE**, `TRTN` at $54.61 **+ 0.7585 BIPC**.
   Dividing the cash leg alone by the pre-close price manufactures a 60 % loss the actual holder
   never took. **17 such records exist universe-wide.**
2. **Warrants and units.** `LUNRW`, `NNAVW` are warrants cashed out at $0.01 and they pass a bare
   `^[A-Z]{1,5}$` shape test. **33 warrant/unit/rights-shaped acquirees exist universe-wide.**
3. **Names that stopped trading long before the deal closed.** §4 exclusion 3 forbids bars *after*
   the effective date and says nothing about a gap *before* it, so `MBT` — a sanctioned Russian
   ADR whose last print is in 2022 and whose cash-out is dated 2026 — enters with a 4.4-year
   holding period. **7 held-out events** have a last bar more than 10 sessions before their
   effective date.
4. **Restated duplicates.** 100 of the 1,782 records are the same acquiree at the same rate on a
   neighbouring effective date (`RVNC` and `HSII` both appear twice above). The dedup key
   `(symbol, effective_date, rate)` does not collapse them.

**These are errors in the frozen rule, and they are reported rather than repaired.** Fixing a
definition after seeing the verdict is the exact move a freeze exists to forbid.

## 5. The cleanest version of the trade that this dataset can produce — and it still fails

§4 exclusion 8 declared, in advance, a symmetric `|gross spread| ≤ 20 %` robustness variant. It
removes all thirteen tail events (and 4 % of the book). It is the **most favourable object this
data can yield**, because on top of both oracles of §1b it also conditions on the entry price
already being near the eventual cash consideration — i.e. on the deal being announced *and* on
track *and* completed. It is not tradable. Here it is anyway:

| | |
|---|---|
| events | **317** |
| mean net excess over T-bills per event | **+1.866 %** |
| t | **+6.87** |
| mean holding period | 102.3 calendar days |
| **annualised excess over T-bills** | **+6.66 %** |

So the merger spread **is real** and it is about the size the literature says. Now the
pre-registered break gate, applied to it — the `b*` formula of §7, unchanged:

| loss given break `L` | −10 % | −20 % | **−25 %** | −30 % | −40 % |
|---|---|---|---|---|---|
| **break-even break rate `b*`** | 14.4 % | 8.1 % | **6.68 %** | 5.67 % | 4.35 % |

**The gate required `b* > 10 %` at `L = −25 %`. It is 6.68 %, and the commonly quoted failure rate
for announced deals is 5–10 %.** The break-even break rate lands *inside* the band of the thing it
has to survive, at every loss assumption of −20 % or worse.

> **That is the finding, and it is precisely the null the shortlist wrote:** *"annualised spread
> capture equals the risk-free rate after deal-break losses."* We measured a +6.66 %/yr spread and
> a break-even break rate of 6.7 % at a −25 % break loss. The spread **is** the deal-risk premium.
> It is not an anomaly, and nothing in it is left over for the arbitrageur.

The Monte Carlo of §7(c) says the same thing about the pre-registered primary book: at a 5 % break
rate the book's mean is **−2.08 %** per event with a 5 % CVaR of **−3.99 %** and
**P(book loses) = 99.6 %**; at 0 % breaks it is already **−0.83 %** with P(loss) 84 %.

## 6. Why the true test could not be built, measured rather than asserted

`EDGE_SHORTLIST.md` §7 scored this candidate `D = 2` and asked for one cheap check first:
*"measure how reliably an announcement date can be recovered from the news endpoint on a sample of
50 known deals."* It has now been done on **80** deals (seed `20260817`), and the shortlist's
caution was right:

| deterministic headline rule | matched | of 80 |
|---|---|---|
| LOOSE (any acquisition-shaped phrase on a headline tagged to the acquiree) | 42 | 52.5 % |
| STRICT (acquiree required in the **object** position, via issuer name) | 14 | 17.5 % |
| acquiree has an issuer name in `/v2/assets` at all | 29 | 36 % |
| acquiree has **zero** Benzinga items in the 760 days before close | **17** | 21 % |

LOOSE's 52.5 % is bought with roughly a one-in-three false-positive rate — its matches include the
acquiree *acquiring somebody else* (`PAE to Acquire CENTRA Technology`, `Convey Health to Acquire
HealthSmart`, `Nexstar … to Acquire BestReviews from Tribune Publishing`), an activist letter, a
litigation headline and a newsletter round-up. STRICT fails differently: **64 % of these delisted
acquirees have no issuer name**, and where they do the ticker has frequently been **recycled** to a
live unrelated instrument (`LMNX` → a Defiance ETF, `MIC` → a 2× daily ETF, `TRIL` → a Tidal
trust) — a symbol-keyed join to a delisted name is not safe.

And the recall failure is **not random**: it concentrates on the small, uncovered names, which is
exactly the "retail-scaled small deals are genuinely under-arbitraged" population the mechanism
claims the edge lives in. There is no announcement-date feed here, and there is no NLP shortcut to
one at an error rate this test could carry.

**Second, and worse: `/v1/corporate-actions` contains only deals that COMPLETED.** A break leaves
no corporate action of any type. The left tail is not rare in this dataset, it is structurally
absent — which is why the test was built as an oracle upper bound (§1b of the pre-registration) and
why §7's break-even analysis, not the mean, is the load-bearing output.

**Third, the feed's cash-merger history begins in 2020**, not 2016 — the same truncation T9 found
in the spin-off feed on the same endpoint. The declared 2016–2021 design window held two years, not
six. `T11_EVENT_CENSUS.json` has the full funnel; at H = 21 it runs
267 → 117 (design) and 1,515 → 487 (held out), with the largest single held-out cut being the
**official closing auction print** (1,279 → 813): a third of completed-merger targets have no
closing auction at all.

## 7. What to carry forward

- **The merger spread is real, measurable and exactly the size of the risk it carries.** +6.66 %/yr
  over T-bills on the cleanest 317 deals; break-even at a 6.7 % failure rate against a 5–10 %
  quoted band. A candidate whose *own* payoff is the compensation for its *own* tail is not an
  edge, and this is now the programme's first candidate killed by a tail rather than by friction.
- **Costs were irrelevant here (20 bp of ladder on an 83 bp loss)** — the first equity candidate in
  this programme where that is true. The friction floor is not the only floor.
- **`/v1/corporate-actions` mis-types mixed cash-and-stock deals into `cash_mergers`** (17 records
  universe-wide, carrying only the cash leg), admits **warrants and units** (33), and **restates
  the same deal on neighbouring dates** (100 near-duplicates in 1,782). Any future use of this
  endpoint should cross-join against `stock_and_cash_mergers` and reject non-common-stock ticker
  shapes. That is a data note worth more than this candidate was.
- **Third instance of the same endpoint truncation**: cash mergers start 2020, spin-offs ~2020
  (T9 §2b). Treat `/v1/corporate-actions` as a ~2020+ feed regardless of what the date parameters
  accept.
- **A cap that fences lookahead on one side fences data errors on the other.** The asymmetric cap
  of §4 exclusion 8 was written to stop pre-announcement entries flattering the result; the
  symmetric variant turned out to be the one that separates real deals from feed defects. Next
  time, declare both and say which is primary *and why*, rather than treating the symmetric one as
  robustness.

## 8. Next candidate

`EDGE_SHORTLIST.md` scores after #1 (T3, dead), #2 (T7, dead), #4 (T9, dead), #6 (T10, dead) and
now #7 (T11, dead). **#8 reverse-split drift (12)** is already ruled out on `A = 1` — the tradable
side is the short side and Alpaca will not lend those names. **#9 borrow-fee signal (11)** needs a
feed we do not hold. **#10 LETF rebalance (10)** needs AUM history that returned a bot-block page
and is partially pre-refuted by B22E. **#11 vol-ETP carry (10)** is not shortable at our broker.

**Nothing above 12 remains untested.** The honest recommendation is therefore **not** another
shortlist item: it is that the shortlist is exhausted at the current data tier, and the fork —
buy a data feed (borrow fees / short interest / announcement dates), or re-scope — is an
**owner call**, not one to infer from a technical case.

## 9. What this result does not claim

- It does not claim merger arbitrage is unprofitable for a desk that can short the acquirer in
  stock deals, lever the book, borrow at institutional rates and diversify across a hundred
  simultaneous deals. It claims that the **long-the-target cash slice**, the retail-accessible one,
  pays a spread equal to its own break risk.
- It does not measure the break rate first-party and says so everywhere: §7's band is a declared
  sensitivity, not a measurement.
- The four definitional defects of §4 mean the pre-registered primary number is contaminated
  *downward*, and this document says so plainly rather than banking the negative. **Gates 1, 2 and
  3 were run once, on the frozen configuration, and were not re-run on the clean variant** — doing
  so would be a second test on the held-out window and is exactly what the freeze forbids. What
  *was* applied to the clean variant is gate 4, because `b*` is a closed-form function of the mean
  that §7 fixed in advance; it fails there at **6.68 % against the 10 % required**. The honest
  statement is therefore: the pre-registered verdict is DEAD on all five gates, and the one gate
  that can legitimately be evaluated on the cleanest data this dataset can produce fails there
  too.
- It authorises no execution. Real money remains owner-gated.
