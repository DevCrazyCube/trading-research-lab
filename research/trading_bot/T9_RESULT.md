# T9 — result: spin-off forced-selling drift (shortlist candidate #4)

## VERDICT: **DEAD — BY INSUFFICIENT POWER**, and it also fails all three statistical gates.

The power gate was written into the pre-registration **before any return existed**, and it is the
gate that decides. It fails by a factor of **2.3×**. The other three gates then fail too, so
nothing about this verdict depends on where the power threshold was drawn.

| gate, all four frozen before any fitting | held-out result | outcome |
|---|---|---|
| **§7 power gate** — MDE at 80 % power ≤ 2.4 % (a +10 %/yr Cusatis-sized effect over 60 sessions) | **MDE = 5.51 %** on **62** held-out events | **FAILS** |
| net mean per event > 0 at the primary cost rung | **−0.82 %**, t **−0.39**, 95 % CI [−4.88 %, +3.25 %] | fails |
| event-label permutation right-tail p < 0.05 | **p = 0.627** | fails |
| DSR ≥ 0.95 at the declared 3 trials | **0.0629** | fails |

**Headline number, and the one worth carrying forward:** this candidate needs **≈ 327 tradeable
spin-off events** to detect the literature's own effect eight times in ten. It has **62**. At the
observed arrival rate of **13.4 tradeable events per year**, closing that gap takes **24 years of
prospective collection.** That is the finding. The point estimate is irrelevant beside it.

---

## 0. Provenance

| | |
|---|---|
| pre-registration | `research/trading_bot/T9_PREREGISTRATION.md` |
| sha256, frozen 2026-08-17 08:06 UTC | `cd36949cce70cce4fabe1a268b549a0e99a6518e1be3f2e41a3f4fcf16715510` |
| collection / census (no arithmetic on any price) | `scripts/t9_spinoff_drift.py` |
| evaluation (refuses to run on a changed hash) | `scripts/t9_evaluate.py` |
| machine-readable result | `research/trading_bot/T9_HELDOUT_RESULT.json` |
| per-event and daily series | `research/trading_bot/T9_DIAGNOSTICS.json` |
| event census, taken **before** the freeze | `research/trading_bot/T9_EVENT_CENSUS.json` |
| statistics | `scripts/trading_bot/stats.py` — imported, not reimplemented |
| costs | `scripts/trading_bot/costs.py` — the **T6-corrected per-side** model |

**What was known before the freeze:** counts of records, counts of bars. No price was divided by
any other price, and no return, Sharpe, drift or portfolio existed on disk when the hash was
taken. §10 of the pre-registration lists every probe.

**This candidate never had a fitted parameter.** Because the design window turned out to hold 14
usable events (§1), the pre-registration took the stricter route and declared the configuration
*a priori* from `EDGE_SHORTLIST.md`'s own pre-data wording — "1–60 trading days" — rather than
selecting one on 14 observations. Nothing in this result was chosen by looking at a number.

---

## 1. The first finding: "243 spin-off records" is not 243 spin-offs

The task, `FINDINGS.md` §10 and `T7_RESULT.md` §9 all record **243 spin-off records already on
disk**. That count was mine and it was right about the file and wrong about the world. What the
243 rows survive down to:

| step | count |
|---|---|
| raw `spin_offs` records, 2016-01-04 → 2026-08-14 | 243 |
| unique by the provider's own `id` | 228 |
| unique by `(source_symbol, new_symbol, ex_date)` | 225 |
| `new_symbol` is **not a ticker** — CVRs, contingent/escrow entitlements, bare CUSIPs (`878CVR018`, `007ESC031`, `09175M606`) | −48 |
| **candidate stub events** | **177** |
| `new_symbol == source_symbol` (a restatement, not a distribution) | −13 |
| the same stub appearing again at a later ex-date | −15 |
| **no quotable entry price within 5 sessions of the ex-date** | −39 |
| entry-day closing print ≤ $5 | −23 |
| entry-day dollar volume ≤ $1 M | −5 |
| **events the strategy could actually have traded** | **82** |
| …of which held out (2022-01-03 → 2026-08-14), at H = 60 | **62** |
| …of which in the design window (2016–2021) | **14** |

**One in three of the "243" is a tradeable spin-off.** Every one of these exclusions was declared
in §2a and §4 of the pre-registration before the count was taken, and each is reported rather than
absorbed.

**The largest single exclusion was checked rather than assumed.** All **39** events dropped for
"no quotable entry price within 5 sessions" have **no daily bar at all** in that window — not one
of them has a bar but a missing auction print. The stub simply did not trade on any SIP-covered
venue in the week after its distribution. The exclusion is a tradeability fact, not an artifact of
insisting on the official closing print.

### 1a. And the provider's spin-off history is truncated, not thin

| year | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate stub events | **0** | 1 | **0** | 1 | 5 | 14 | 22 | 37 | 25 | 47 | 23 |

Zero spin-offs in 2016. Zero in 2018. One in 2019. That is not what happened in the world, and it
was checked rather than assumed. A live probe of `/v1/corporate-actions` for nine named, large,
well-documented US spin-offs of the design window returns **no `spin_off` record for any of
them**:

> Corteva (`CTVA`, ex 2019-06-03), Dow (`DOW`, 2019-04-01), Adient (`ADNT`, 2016-10-31), Lamb
> Weston (`LW`, 2016-11-09), Valvoline (`VVV`, 2017-05), Resideo (`REZI`, 2018-10-29), Garrett
> Motion (`GTX`, 2018-10-01), Arlo (`ARLO`, 2018-12-31), Brighthouse (`BHF`, 2017-08-04).

Five of the nine return **cash dividends** over the identical query window, so the symbols and the
window are being served — the gap is in the feed's spin-off coverage before ~2020, not in our
query. A universe-wide year-by-year probe confirms it: 0, 1, 0, 1, 5 records for 2016–2020.

**This is the fact that broke the standard design.** The T3/T7 split puts 2016–2021 in the design
window; for this candidate that window holds **14** usable events. Fourteen events cannot select a
configuration, and freezing a grid fitted on them would have been worse than not freezing at all.
The pre-registration says so in §2b and replaces the design phase with an a-priori declaration.

**Recorded as a correction to this programme's own index:** `FINDINGS.md` §10 and `T7_RESULT.md`
§9 both advertise "243 spin-off records already on disk" as an asset. The honest restatement is
**82 tradeable events, 62 of them held out, and a feed that lost every 2016–2019 spin-off.**

---

## 2. THE POWER GATE — computed before the verdict, on design-window quantities only

| quantity | value |
|---|---|
| σ̂, standard deviation of the per-event net excess return, **design window only** (14 events, H = 60) | **15.49 %** |
| held-out events, H = 60 | **62** |
| **MDE at 80 % power, two-sided α = 0.05** = `2.80 × σ̂ / √n` | **5.51 %** |
| benchmark effect: Cusatis, Miles & Woolridge's ≈ +10 %/yr over 60 sessions | **2.40 %** |
| **gate** (MDE ≤ benchmark) | **FAILS, by 2.3×** |
| events required to reach MDE = 2.40 % | **327** |
| observed arrival rate of tradeable events | **13.4 / year** |
| **years of prospective collection required** | **24.3** |

**Read that as the answer to the question the task asked.** n is not "a bit small". The
instrument is **five times too wide** to see the strongest version of the effect the literature
has ever reported, and it stays too wide for another quarter of a century. Anything positive this
test had produced would have been un-interpretable; anything negative fails to exclude the
literature's effect. Both directions were foreclosed before the number was computed, which is
precisely why the gate is written in the pre-registration and not here.

**And the ratio that makes it concrete.** Per event, at H = 60 held out:

| | value |
|---|---|
| total modelled friction | **11.78 bp** |
| standard deviation of the per-event outcome | **1,635 bp** |
| **noise ÷ friction** | **139 ×** |

**This is the first candidate in the programme that does not die at the friction floor.** T3 died
with 6.8 bp of gross against 1.4 bp of measured entry friction. T7 died with 0.84 bp against
0.37 bp of irreducible regulatory cost. Here friction is 11.8 bp and the noise is 1,635 bp. Making
execution free would move the answer by **0.72 %** of one per-event standard deviation, or
**5.7 %** of one standard error. **The binding constraint is sample size, and no amount of cost
engineering touches it.**

---

## 3. The held-out period — 2022-01-03 → 2026-08-14, run once

### 3a. The primary configuration, H = 60 sessions

| | held out (62 events) | design (14 events) |
|---|---|---|
| gross mean per event | −0.70 % | −8.38 % |
| **net mean per event** | **−0.82 %** | −8.50 % |
| t | **−0.39** | −2.05 |
| 95 % CI | **[−4.88 %, +3.25 %]** | [−16.6 %, −0.39 %] |
| sd per event | 16.35 % | 15.49 % |
| fraction of events positive | 46.8 % | — |
| median event | −0.79 % | — |
| net annualised Sharpe (daily book) | **−0.27** | −0.88 |
| max drawdown (daily book) | −63.1 % | −45.2 % |
| mean names held | 3.36 | 1.97 |
| sessions the book held anything | 1,099 | 426 |

**Both periods are negative.** The confidence interval spans the literature's effect and spans
zero and spans an effect four times the literature's, in both directions. That is what an
underpowered instrument looks like from the inside.

### 3b. The three declared horizons — the entire trial space

| H | design (14) | held out | held-out t | all (design + held out) | all t |
|---|---|---|---|---|---|
| 21 | −6.53 % | **−1.87 %** (67 events) | −1.50 | −2.67 % (81) | **−2.33** |
| **60 (primary)** | −8.50 % | **−0.82 %** (62 events) | −0.39 | −2.23 % (76) | −1.19 |
| 126 | −6.56 % | **+4.64 %** (59 events) | +0.73 | +2.49 % (73) | +0.48 |

**The sign flips with the horizon and none of the three reaches |t| = 2 out of sample.** That is
the signature of noise, not of a drift with a shape.

### 3c. The other two gates

**Event-label permutation** — 10,000 shuffles, seed `20260817`. Each real stub is replaced by a
control name holding the identical dates, facing the identical market move; only *which stock was
the spin-off stub* changes. Median control pool per event: **1,284 names**.

> **p (right tail) = 0.627.** The observed mean is at the **37th percentile** of the null. Being
> a spin-off stub was, if anything, mildly worse than being a randomly chosen liquid stock over
> the same 60 sessions.

**Control basket** (the second pairing, k = 5 per event): **+0.09 %** per event against the
stubs' **−0.70 %** gross. Same days, same holding period, same hedge.

**Deflated Sharpe** on the held-out **daily portfolio** net series (n = 1,099 sessions),
`trials = 3` with `sharpe_variance` from the three declared horizons' per-observation Sharpes:

| | |
|---|---|
| observed Sharpe / observation | **−0.01717** |
| expected-max under the null, 3 trials | +0.03103 |
| **DSR at trials = 3** | **0.0629** |
| DSR at trials = 12 (sensitivity) | 0.0068 |
| skew / kurtosis of the daily series | +4.79 / 76.9 |

The observed Sharpe is **negative** and the chance ceiling is positive, so the DSR is not a near
miss — it is the wrong side of zero before deflation even starts.

### 3d. Year by year, held out

| year | n | net mean per event |
|---|---|---|
| 2022 | 12 | −3.90 % |
| 2023 | 18 | +2.78 % |
| 2024 | 14 | −1.70 % |
| 2025 | 13 | −5.89 % |
| 2026 | 5 | +9.29 % |

Two positive years, three negative, and the largest of them rests on **five events**. Nothing is
carrying the result because there is no result to carry.

---

## 4. Friction, measured first-party on the traded names

The pre-registration refused to inherit T3's liquid-universe half-spread and measured the stubs
themselves — median `(ask − bid)/(2 × mid)` from SIP quotes in `[15:59:59, 16:00:00) ET`, on the
**actual entry and exit dates of the actual stubs**.

| | value |
|---|---|
| **stub median quoted half-spread** | **7.47 bp** |
| stub p25 / p75 / p95 | 3.40 / 18.42 / **59.57** bp |
| stub mean | 20.86 bp |
| n symbol-days | 134 |
| **SPY, same instrument, same days** | **0.116 bp** |
| T3's top-500-ADV universe, same instrument | 1.13 bp (2016–21) / 1.43 bp (2022–26) |

**A spin-off stub costs 5–6× the liquid universe at the median and 42× at the 95th percentile.**
This is a genuine first-party measurement and it transfers: it is the friction number for any
future candidate that trades freshly distributed stubs, and it sits between T1 §2d's liquid names
(0.26–6.2 bp) and its small-cap most-active (119.6 bp), which is where it should sit.

### The cost model, per side, and the stress ladder

Per event at H = 60, held out (fractions of the unit position's equity):

| component | charge | note |
|---|---|---|
| half-spread, four legs | **7.58 bp** | 7.47 bp on the two stub legs, 0.116 bp on the two SPY legs — **each side declared separately**, the T6 correction |
| extra slippage | 0 bp | a stated **lower bound**, not a claim; swept below |
| SEC §31, sale legs only | 0.28 bp | 0.278 bp of sale notional, top of the 2016–2026 range, both periods |
| FINRA TAF, sale legs only | **0.00005 bp** | $0.000166/share — charged exactly, and it is genuinely negligible at these prices |
| borrow on the 50 % SPY short, **calendar** days | **3.92 bp** | 33 bp/yr, `measured_borrow_annual("etb_general_collateral")`, ≈ 87 calendar days |
| commission | 0 | $0/share |
| **total** | **11.78 bp** | |

| rung | net mean per event | t |
|---|---|---|
| **frictionless (B19P diagnostic — all costs zero)** | **−0.698 %** | −0.34 |
| 0 (spread zero, regulatory + borrow charged) | −0.740 % | −0.36 |
| 0.5 h | −0.777 % | −0.37 |
| **h (primary)** | **−0.815 %** | −0.39 |
| 2 h | −0.891 % | −0.43 |
| 4 h | −1.043 % | −0.50 |

**It loses at zero cost.** By B19P's own rule that closes every execution-improvement idea for
this candidate — and it also demonstrates the §2 point arithmetically: the whole ladder, from free
to four times the measured spread, moves the answer by **35 bp** against a **1,635 bp** standard
deviation.

---

## 5. Deviations from the pre-registration

**One, and it is a narrowing, declared here.** §4 exclusion 4 anticipated dropping events with too
few sessions in the holding window; in practice the terminal-price rule of §5 absorbed all of
them, and exactly **one** held-out event (of 62) exited early under that rule. No event was
dropped for sparse bars.

**No other deviation.** The exclusion counts of §1 are the §4 rules applied once. The three
horizons are the three declared. The seed is the declared `20260817`. The half-spread window is
T3's already-declared `[15:59:59, 16:00:00)` deviation, inherited with its reason.

---

## 6. What this test does not claim, and three things it can't see

- **It cannot see what the feed does not send.** §1a proves the `spin_off` type is demonstrably
  incomplete before 2020. A feed that lost every 2016–2019 spin-off may be losing smaller ones
  after 2020 too. The direction of that bias is **unknown**, and unknown is what it is reported
  as — not as "probably fine".
- **The `spin_off` type is heterogeneous even after the ticker filter.** The held-out set contains
  a warrant (`ENVXW`) and AMC's preferred-unit distribution (`APE`) alongside genuine stubs
  (`GEHC`, `GEV`, `CEG`, `SOLV`, `VLTO`, `SNDK`, `WBD`, `FTRE`, `RXO`, `VSTS`, `AMTM`, `PHIN`,
  `EMBC`, `KLG`, `ZIMV`, `NXT`, `SEG`, `BRBR`). A hand-curated event set would be cleaner — and at
  n = 62 it would still be five times too small, so curating it would not change the verdict.
- **It does not model when-issued trading, the due-bill period, cash-in-lieu of fractional stub
  entitlements, queue position or size-dependent impact in a stub's first closing auction** —
  which is exactly where a $100 k account is least likely to be negligible, and where the
  still-unperformed **M0** bites hardest.
- **It does not authorise execution of any kind.** Real money remains owner-gated.

---

## 7. One observation, reported with its caveats, that is NOT a finding

At the shortest declared horizon the drift is **negative**: H = 21, all 81 events, −2.67 % per
event, t = **−2.33**. Held out alone it is −1.87 %, t = −1.50; the design window's 14 events carry
most of the apparent significance (−6.53 %, t = −2.31 on 14 observations).

That sign is **consistent with the forced-selling mechanism running the other way from the
candidate's own hypothesis** — index funds dumping an unwanted stub push the price *down* first,
and the documented long-run outperformance is a later, separate phenomenon. If it were real, the
tradeable expression would be to **short** the stub.

**It is not a finding, for four reasons stated together:**

1. It is the wrong sign for the pre-registered H1, so treating it as an edge is a new hypothesis
   generated from the same data — the exact move `FINDINGS.md` §5c exists to forbid.
2. Its significance is carried by 14 design-window events at 10.6 % dispersion.
3. It would fail DSR immediately: the daily-book Sharpe at H = 21 is **−0.97 annualised** on the
   held-out period, which is a *loss* on the long side, not a certified short edge.
4. **The trade is unavailable.** `EDGE_SHORTLIST.md` #8 already establishes it: a freshly
   distributed stub is precisely the name Alpaca will not lend, and this test holds no borrow-fee
   or locate data (`D = 1`). A negative-drift signal you cannot short is not a strategy.

Recording it so that a future reader does not rediscover it and mistake it for something.

---

## 8. What this means for the programme

**Three candidates, three different causes of death, and the third is new.**

| candidate | died of | the number |
|---|---|---|
| #1 T3 end-of-day pressure reversal | **search selection** — real signal, below the chance ceiling | DSR 0.9379 vs 0.95 |
| #2 T7 ex-dividend drop-off | **the effect is smaller than the noise it lives in** | p 0.213, DSR 0.076, residual 2.9 bp vs ±2.4 bp |
| **#4 T9 spin-off drift** | **there is not enough of the event in the world** | MDE 5.51 % vs 2.40 %; 327 events needed, 62 held |

**The method item worth keeping.** T7's result document argued that a pre-registration should
carry a power calculation *before* collection rather than a post-mortem after failure. This one
did, and the power gate produced the verdict **on its own, from design-window and structural
quantities only** — before the held-out number existed and independent of it. That is the gate
working as designed, and it is cheap: the census that killed this candidate took minutes and could
have been run before any of the collection.

> **Rule earned here, proposed for `FINDINGS.md` §8:** *count the events before building the
> harness.* A candidate whose minimum detectable effect exceeds the literature's own effect size
> is dead before it is tested, and finding that out is a counting exercise, not a backtest.

### Nomination, with a recommendation and a fork for the owner

Four of the thirteen shortlist candidates are now resolved: #1 dead, #2 dead, #4 dead, and #6
was pre-refuted by B22F. The ranked remainder is **#3 turn-of-month (15)**, then **#5 CEF discount
mean reversion (14)**, then **#7 merger arb (12)**.

**Apply this candidate's own lesson to them before spending a slice on either.** The census is
the cheap part:

- **#3 turn-of-month** has **≈ 60 held-out month-ends**. `T7_RESULT.md` §9 already recommended
  against it on exactly this ground, and T9 has now made that argument quantitative rather than
  rhetorical. **It should be power-censused first, and I expect it to fail the same gate** — a
  daily portfolio at n = 60 observations needs an enormous per-event effect to reach DSR 0.95.
- **#5 CEF discount mean reversion** is the one remaining candidate whose n is **large** (360
  funds × weekly observations) and whose mechanism — institutionally uneconomic to arbitrage at
  retail size — is genuinely the "too small to matter" corner a $100 k account should want. Its
  known weakness is friction (§2e: CEF closing auctions clear $0–0.3 M, so the free auction rail
  is unavailable and every leg crosses 4–36 bp) and shallow NAV history (daily only ~1 year).
  **That is a friction problem, and this programme knows how to price friction. It does not have
  a power problem.**

**My recommendation, and it is a recommendation because the scope call is the owner's:**

1. **Run M0 first.** It is now load-bearing for **three** dead candidates and remains unperformed.
   Bounded, a measurement not a search, and both outcomes are worth having.
2. **Then #5 (CEF discount), not #3.** #3 is the ranked successor and I am nominating it as such
   for the record, but I recommend against running it: it is the candidate most likely to
   reproduce exactly the failure documented above, and T9 has now given us the instrument to
   predict that before spending the slice.
3. **Before either, run a one-hour power census** on both — count the events, estimate σ from the
   design window, compute the MDE, and compare it to the literature's effect. On T9's evidence
   that census is worth more than the backtest it replaces.

**The fork is the owner's:** run #3 as ranked; run M0 then #5 as recommended; or stop adding
candidates and spend the slice on the prospective forward test that T7 §7 identified (the
close-to-open ex-dividend residual), which is the only live positive this programme has that has
not yet been given a clean rail to be tested on.

---

## 9. What this document does not claim

- It does not claim spin-off drift does not exist. It claims **this instrument cannot see it**,
  and quantifies by how much: 5.51 % detectable against 2.40 % claimed, 62 events against 327
  needed.
- It does not claim the feed's post-2020 spin-off coverage is complete.
- It does not claim the negative sign at H = 21 is an edge. §7 gives four reasons it is not.
- It does not authorise real-money execution, which remains owner-gated.
