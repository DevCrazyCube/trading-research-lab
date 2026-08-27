# T12 — result: closed-end-fund discount mean reversion — **DEAD**

**Candidate:** #5 in `EDGE_SHORTLIST.md` (14/20, uniqueness U = 4).
**Frozen rule:** `T12_PREREGISTRATION.md`, sha256
`d88663008a813064816f53cb8ac19c051d057a115560ebc9f41114186037bd3e`, written and hashed
**before any price was divided by any other price**. `scripts/t12_evaluate.py` refuses to run
against any other hash.

**VERDICT: DEAD.** The pre-registered primary fails three of the four kill conditions.

| gate (frozen in §7 of the pre-registration) | result | |
|---|---|---|
| 0. history gate — can this window see the effect at all? | min detectable annualised Sharpe **1.745** ≤ benchmark **1.859** | **PASS** |
| 1. net mean per week > 0, held out, primary | **−0.27 bp/week**, t **−0.08** | **FAIL** |
| 2. decile-label permutation p < 0.05 | **p = 0.0539** | **FAIL** |
| 3. DSR ≥ 0.95 at trials = 6 | **DSR = 0.1542** | **FAIL** |

**And the interesting part is that it did NOT die of the thing the task expected.** The
guardrail anticipated `DEAD-BY-INSUFFICIENT-HISTORY`. The history gate is the one gate that
passed — narrowly, and only because the long-short book turned out to be unusually *quiet*
(σ̂ = 3.23 %/yr). This candidate got a real out-of-sample test and lost it on the merits.

---

## 1. The usable data span, stated up front as the task required

`research/trading_bot/T12_DATA_CENSUS.json`, taken before the freeze.

CEFConnect's `/api/v3/pricinghistory/{ticker}/{period}` serves exactly five periods. `6M`,
`10Y`, `Max` and every numeric period return **HTTP 200 with an empty array** — a silent empty,
which is the shape of lie this programme has learned to probe for rather than trust.

| | **5Y window** | **1Y window** |
|---|---|---|
| live funds in the snapshot | 360 | 360 |
| funds with history | **353** | 359 |
| sampling (median gap between observations) | **WEEKLY (7 d)** | **DAILY (1 d)** |
| union of dates | 249 | 253 |
| span | **2021-08-20 → 2026-08-14** | 2025-08-18 → 2026-08-14 |
| rows with a missing NAV or discount | 0 | 0 |

**`EDGE_SHORTLIST.md` §2b's summary was exactly right**, now verified on the full 360-fund
universe rather than one probe: ~1 year daily, 5 years weekly, and no window that is both.

**Deeper NAV history does not exist inside the broker either.** Alpaca serves `ADX` and `PDI`
daily bars from 2016-01-04, but the NAV pseudo-ticker `XADEX` returns **zero bars**. The price
leg has ten years of history; the NAV leg has five, weekly. NAV is the binding constraint and
nothing we hold relaxes it.

**Usable grid after hygiene: 243 weekly dates, 2021-08-20 → 2026-08-07.** Six of the 249 raw
dates carry 1–28 funds — five are US market holidays on which a handful of sponsors published
anyway (2025-04-18, 2025-07-04, 2026-04-03, 2026-06-19, 2026-07-03) and one is the truncated
final date (2026-08-14). *This is a post-freeze data-hygiene rule and it is declared as one*:
the threshold is structural (half the live universe must be quoted), it cannot be tuned, and the
dates it removes are listed rather than absorbed. It is `EDGE_SHORTLIST.md` §2f's own lesson —
a pinned sample must come from the trading calendar, not from weekdays.

**Split:** design **125 weeks** (2021-08-20 → 2024-02-23), held out **117 weekly returns**
(2024-03-01 → 2026-08-07). The held-out half had never been looked at when the rule was frozen.

---

## 2. Why the history gate passed, and what it cost to pass

The gate (§3 of the pre-registration) asks whether the held-out window could detect the
**strongest documented version** of the effect — Pontiff (1995)'s **6 %/yr** — at the DSR
threshold the programme requires.

| quantity | value |
|---|---|
| held-out weekly observations | **117** |
| declared trials | 6 |
| sd of the six design-window per-observation Sharpes | 0.0670 |
| min detectable annualised Sharpe, **trials = 6** | **1.745** |
| min detectable annualised Sharpe, **trials = 1** (no search penalty at all) | 1.108 |
| σ̂ of the primary book, design window, annualised | **3.23 %/yr** |
| benchmark: 6 %/yr ÷ 3.23 %/yr | **1.859** |
| **gate** | **PASS** (1.745 ≤ 1.859) |
| held-out weeks that would have been *required* | 97 (1.87 yr) — we have 117 (2.25 yr) |

The gate passed for one reason and it is worth naming: **a dollar-neutral CEF decile book is
extremely low-volatility** (3.2 %/yr), so 6 %/yr of edge would be a Sharpe of 1.86 and even a
2¼-year weekly window can see that. Had the book's volatility been an ordinary 10 %/yr, the
benchmark Sharpe would have been 0.60 against a 1.745 requirement and the verdict *would* have
been `DEAD-BY-INSUFFICIENT-HISTORY`.

**So the honest generalisation is narrower than "five years of weekly data is enough".** It is:
*this particular book is quiet enough that 2¼ years of weekly data can just barely see a 6 %/yr
effect, and cannot see anything much smaller.* Design B — the daily 1-year feed — was rejected in
advance and the arithmetic confirms why: at n ≈ 126 daily it needs an annualised Sharpe of
**2.35 even at one trial**, more than twice as demanding despite having more rows.

---

## 3. The held-out result — run once, all six declared trials

Primary is **trial 4** (S1, L = 52 weeks, H = 4 weeks), declared a priori because
`EDGE_SHORTLIST.md` §5 wrote the null as *"next-month return"* on 2026-08-16.

| trial | signal | L | H | design net bp/wk | design ann SR | **held-out net bp/wk** | held-out t | **held-out ann SR** |
|---|---|---|---|---|---|---|---|---|
| 1 | S1 own-mean z | 26 | 1 | +13.92 | +2.14 | **−6.14** | −1.71 | −1.146 |
| 2 | S1 own-mean z | 26 | 4 | +15.57 | +2.42 | **+1.16** | +0.34 | +0.225 |
| 3 | S1 own-mean z | 52 | 1 | +12.54 | +2.03 | **−2.53** | −0.69 | −0.459 |
| **4 — PRIMARY** | **S1 own-mean z** | **52** | **4** | **+7.14** | **+1.15** | **−0.27** | **−0.08** | **−0.056** |
| 5 | S2 raw discount level | — | 1 | +16.93 | +2.51 | **+12.93** | +3.43 | +2.298 |
| 6 | S2 raw discount level | — | 4 | +13.85 | +2.02 | **+14.48** | +3.83 | +2.566 |

**The mean-reversion family (S1) is dead in every form.** All four S1 trials were strongly
positive in the design window (+7 to +16 bp/week, annualised Sharpe 1.15 to 2.42) and **three of
four went negative out of sample**. That is the signature of a fitted design window, and it is
the reason the freeze exists.

### 3a. The primary, in full

| | held out, primary, at the measured cost rung |
|---|---|
| net mean | **−0.271 bp/week**, t **−0.084** |
| net annualised return / Sharpe | −0.14 % / **−0.056** |
| gross (pre-friction) mean | +3.30 bp/week, t +1.03, annualised Sharpe +0.691 |
| **DSR, trials = 6** | **0.1542** (trials = 1, i.e. no search penalty at all: **0.467**; trials = 12: 0.100) |
| decile-label permutation, 10,000 shuffles, seed 20260817 | **p = 0.0539** |
| **permutation dispersion ratio** | **1.524** |
| turnover per rebalance | 1.103 of a 2.0 full round trip (**55 % of the book replaced**) |
| friction per rebalance | **12.93 bp** |
| negative weeks | 60 of 116 |

Year by year, held out, primary: **2024 +3.86 bp/wk (41 wk, +1.56 % total), 2025 −2.63 bp/wk
(48 wk, −1.27 %), 2026 −2.34 bp/wk (27 wk, −0.65 %)** — positive only in the stub year adjacent
to the design window, and negative in both full years after it.

**The dispersion ratio is reported because `FINDINGS.md` §5c requires it.** At 1.52 the real
decile book carries half again the dispersion of a random partition of the same names, so
p = 0.0539 is partly answering *"is this partition special?"* rather than *"is the mean
positive?"* — the T10 §5 lesson. It fails the gate either way, so nothing turns on it here, but
it is stated.

### 3b. The stress ladder — and where the friction floor actually sits

Held out, primary, cost varied and nothing else:

| rung | net bp/week | net annualised Sharpe |
|---|---|---|
| **zero cost** (B19P diagnostic — spread, slippage and borrow all zero; SEC §31 and TAF still charged, which is the 0.05 bp gap to the +3.30 gross) | +3.25 | +0.680 |
| half-spread 0, borrow and regulatory charged | +2.91 | +0.608 |
| half-spread 0.5 h = 5.76 bp | +1.32 | +0.275 |
| **half-spread h = 11.53 bp (MEASURED, primary)** | **−0.27** | **−0.056** |
| half-spread 2 h = 23.05 bp | −3.45 | −0.690 |
| h + 5 bp impact | −1.65 | −0.337 |
| h + 10 bp impact | −3.03 | −0.609 |
| h + 25 bp impact | −7.16 | −1.342 |
| h + 50 bp impact | −14.06 | −2.240 |

**The break-even half-spread is ≈ 10.6 bp, against a measured 11.53 bp.** This is the sixth
domain in this programme to die within a whisker of its own friction floor — but note carefully
that **at zero cost it is still only annualised Sharpe 0.68**, so friction is not the sole
executioner here. Even a free rail leaves it below the 1.745 the DSR gate demands. *Unlike T10,
no execution improvement rescues this one.*

---

## 4. Friction, measured first-party on the traded names

`research/trading_bot/T12_FRICTION_CENSUS.json`. Median `(ask − bid) / (2 × mid)` from SIP
quotes in `[15:59:59, 16:00:00) ET` — same instrument and declared deviation as
`t3.measure_half_spread` — over **3,067 CEF symbol-days**, 12 dates × 360 names:

| p25 | **median** | p75 | p90 | p95 | max |
|---|---|---|---|---|---|
| 7.15 bp | **11.53 bp** | 18.38 bp | 27.25 bp | 36.40 bp | 185.74 bp |

For scale, on the identical instrument and window this programme has measured **SPY at 0.116 bp**,
its **top-500-ADV universe at 1.13–1.43 bp**, and a **freshly distributed spin-off stub at
7.47 bp** (`T9_RESULT.md`) — until today the thinnest thing it had ever priced.

> **The median closed-end fund is 1.5× more expensive to cross than a spin-off stub and 99×
> more expensive than SPY.** This is a new first-party number and it outlives the candidate.

**And there is no auction rail to escape it.** `EDGE_SHORTLIST.md` §2e measured CEF closing
auctions clearing **$0.0–0.3 M**; `costs.measured_auction_leg` refuses outside M0's measured ADV
tiers and CEFs are outside them. Every leg of this candidate crosses a continuous spread, on both
sides, and the T6-corrected model charges it that way in two separately-named components.

Cost model as charged: entry 11.53 bp + exit 11.53 bp (measured, per side), extra slippage 0 bp
(stated lower bound), SEC §31 at 0.278 bp of sale notional, FINRA TAF at $0.000166/share sold,
commission $0, borrow 33 bp/yr on short notional per calendar day
(`costs.measured_borrow_annual("etb_general_collateral")` — a **floor**, see §6).

---

## 5. The one result that did not die, and why it is NOT a pass

**Trials 5 and 6 — the naive "long the widest *raw* discount, short the narrowest" form — were
strongly positive out of sample: +12.93 and +14.48 bp/week, t +3.43 and +3.83, annualised
Sharpe +2.30 and +2.57, net of the measured 11.53 bp spread on every leg.** Design-window values
(+16.93, +13.85) and held-out values are *consistent*, which is not what an overfit looks like.
DSR at the declared six trials is **0.9912 and 0.9971**; permutation p = 0.0005.

**This is reported, not claimed.** The primary was declared in advance and the verdict runs on
it; promoting a non-primary trial after seeing its result is precisely the multiple-testing
failure the freeze exists to prevent. `research/trading_bot/T12_DIAGNOSTICS.json` records the
hostile follow-up, and it found four things that materially damage the number:

**(a) It is not a mean-reversion strategy at all — it is a near-static tilt.**
Across the 29 held-out rebalances, **81.4 % of the long decile and 79.1 % of the short decile
carry over unchanged** (turnover 0.42 of a 2.0 round trip). By contrast the pre-registered S1
book replaces 55 % of itself each rebalance. S2 does not trade the *deviation* of a discount from
its own mean; it holds the funds that are permanently cheapest and shorts the ones permanently
dearest, and it barely moves. **Its 2¼-year held-out record is a handful of independent bets in
one regime, not 117 of them**, and no DSR computed on the return series can see that.

**(b) A large part of the P&L is the assets, not the discount.** On a like-for-like
non-distribution-adjusted basis the book returns **+18.78 bp/week** while the untradeable **NAV
leg alone returns +9.45 bp/week** — i.e. roughly half of it is the wide-discount funds' *assets*
outperforming the premium funds' assets. The claimed mechanism (the discount narrowing) accounts
for the other half. The realised discount convergence over a 4-week tranche is **+0.40 pp on the
long leg and −0.73 pp on the short**, which is real but small.

**(c) The two legs are structurally different funds.** Long leg: US equity (200 slots), Asia
equity (146), global equity (100), US allocation (86), EM equity (83). Short leg: multi-sector
fixed income (133), sector equity (110), investment grade (95), preferreds (70), convertibles
(62), munis (43). *Honest correction to my own first reading:* regressing the held-out weekly net
series on **(SPY − AGG)** gives a beta of only **+0.057** with alpha +12.62 bp/week (t +3.51), and
on SPY a beta of **+0.051**. **So the equity-versus-bond tilt does NOT explain it at the index
level** — I expected it would, and the measurement says otherwise. What remains is a persistent
CEF-specific asset-selection effect that this test cannot separate from the discount effect.

**(d) Survivorship bites this trial hardest of anything in the test.** CEFConnect publishes only
funds alive today; there is no delisted list. S2's long leg is *the permanently deepest-discount
funds*, which is exactly the population where "still quoted in 2026" is most informative. A
name-matching heuristic over Alpaca's 19,195 inactive `us_equity` assets finds **131 plausible
CEF names that stopped trading** against 360 alive — an order-of-magnitude **~27 % attrition the
panel cannot see**. (A name match is not a classification; this is a magnitude, not a
measurement.) The *direction* is genuinely unknown: a fund tendered or open-ended at a wide
discount is a deleted **gain** for the long leg, while one delisted after its NAV collapsed is a
deleted **loss**. Unknown is what it is reported as.

**(e) Half its short leg cannot be borrowed here.** Only **57.2 %** of the held-out short-leg
slots are `shortable` at Alpaca today (universe-wide: 186 of 358, 51.96 %). Deep-*premium* CEFs
are small, retail-crowded and exactly the hard-to-borrow case, so the 33 bp/yr general-collateral
borrow charged above is a **floor and probably a substantial understatement**. These are live
flags with no history, so they are *not* applied as a backtest screen — but they bound what could
actually be put on.

> **What S2 is, stated plainly: a static, high-persistence, deep-discount-versus-premium tilt in
> closed-end funds, on a survivor-only panel, with a short leg that is half unborrowable.** It is
> the first thing in this programme to reproduce out of sample at a positive net Sharpe, and it
> is *not* the pre-registered candidate. It deserves its own pre-registration — see §8 — and the
> decision to spend a slice on that is an owner call, not mine.

---

## 6. What this test does not claim

- It does not claim CEFConnect's weekly discount is point-in-time. NAV is struck after the close
  and published with a lag; whether the value the site serves today for a 2022 date was
  *available* on that date cannot be asked of this feed. The design acts on the **following**
  week's price, never the same day's, which mitigates but does not prove.
- It does not repair survivorship (§5d) and does not know the sign of the bias.
- It does not model queue position, partial fills, or size-dependent impact in a $389 M-median
  fund whose entire closing auction is under $0.3 M.
- It prices borrow as a cost and reports the 48 %-non-shortable share as an executability caveat
  rather than modelling it as a constraint.
- It does not test the forward daily collection `EDGE_SHORTLIST.md` §5 proposed.
- **It does not authorise execution of any kind. Real money remains owner-gated.**

---

## 7. What outlives the candidate

1. **The median CEF quoted half-spread is 11.53 bp** (n = 3,067 symbol-days, first party) — 99×
   SPY, 1.5× a spin-off stub. Any future CEF idea starts from this number.
2. **CEF NAV history is hard-capped at 5 years weekly / 1 year daily**, verified on the full
   360-fund universe, and the broker does not relax it (`XADEX` returns zero bars). Written down
   so nobody re-probes it.
3. **A quiet book can pass a power gate that a normal one cannot.** The gate here passed only
   because σ̂ = 3.23 %/yr. `T9_PREREGISTRATION.md` §7 asked "can we see the literature's effect";
   the answer depends on the book's volatility as much as on the sample length, and the T9 form
   of the gate handles that correctly. Worth keeping.
4. **Design-window Sharpe of 1.15–2.51 across all six trials, three of four S1 trials negative
   out of sample.** Another entry for the same ledger: this rig's design windows produce
   attractive numbers routinely, and they mean nothing until frozen.
5. **The dispersion-ratio rule works.** 1.52 for the primary, **1.91 for S2** — for S2 the
   p = 0.0005 is substantially a statement about *which partition*, exactly as `T10_RESULT.md`
   §5 predicted it would be for a sorted book.

---

## 8. Recommendation — and the fork is the owner's

Candidate #5 is **DEAD** as pre-registered. The mean-reversion mechanism the shortlist ranked it
for does not survive out of sample and does not clear its own friction floor.

That leaves a genuine fork, and per standing practice it goes to the owner with a recommendation
rather than being decided here:

**Option A — pre-register the S2 tilt properly (my recommendation, if any slice is spent on
CEFs at all).** The pre-registration would have to be built around the four attacks in §5, not
around the return: (i) a **survivorship-robust panel** — the binding requirement, and it needs a
delisted-fund source we do not currently hold; (ii) the short leg restricted to the borrowable
half with a **measured, not assumed, borrow rate**; (iii) an explicit NAV-return control so the
discount component is separated from the asset-selection component *ex ante*; (iv) honest
treatment of the fact that a book with 80 % persistence has an effective n far below its weekly
count. **Without (i) I would not believe a positive answer, and (i) is a data-acquisition
question before it is a research question.**

**Option B — do not spend the slice.** `FINDINGS.md` §10 already records that the remaining
shortlist is thin and that **M0's C4** (the live paper-order batch establishing that our on-close
order joins the cross) is the cheapest outstanding measurement in the programme, now with five
dead candidates resting on it. Nothing in T12 changes that; T12 in fact *adds* to it, since a
CEF strategy is the one family the auction rail cannot help.

**What T12 does settle:** the "run a one-hour power census on #5 before spending a slice on it"
instruction from `T9_RESULT.md` §8 has been executed. The census said the history is thin but
survivable for a quiet book; the test then ran and the candidate lost on its own merits. The
programme does not need to revisit candidate #5 as ranked.

---

*Collection: `scripts/t12_cef_discount.py`. Verdict: `scripts/t12_evaluate.py` (refuses without
the frozen hash). Hostile follow-up: `scripts/t12_diagnostics.py`. Artefacts:
`T12_DATA_CENSUS.json`, `T12_FRICTION_CENSUS.json`, `T12_HELDOUT_RESULT.json`,
`T12_DIAGNOSTICS.json`. All endpoints read-only; no order was placed.*
