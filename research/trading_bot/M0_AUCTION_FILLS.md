# M0 — is the auction rail free? The measurement

## VERDICT, in one paragraph, and it is not the one I expected to write

**The zero-spread auction-rail charge SURVIVES for the universe #1 and #2 actually traded, and it
fails outside it.** In the top-500-ADV universe an official closing print exists on **99.96 %** of
symbol-days and clears a median **$37 M**, so a retail-sized market-on-close is not the auction and
has no bid-ask to cross. Charging that leg zero was defensible and remains defensible. But two
things in this measurement are new and one of them is uncomfortable. First, **the print is almost
never the midpoint** — it sits at the closing NBBO mid on **1.9 %** of symbol-days and *entirely
outside* the closing NBBO on **31.1 %** — so the mental model "the auction is the mid, for free",
which is how the shortlist phrased it, is simply false; it is only harmless because T3 and T7
marked at the print itself rather than at a mid. Second, **availability collapses down the
liquidity ladder**: 99.5 % at ADV rank 501–1500, **94.6 %** at 1501–3000, **62.1 %** at 3001–6000.
And the half of M0 that a tape cannot answer — that *our broker's* on-close order joins that cross —
remains unmeasured and needs live paper sessions. §10 is the bounded protocol for it; it was not run,
and §10 says why.

**Plainly, for the record `FINDINGS.md` keeps:** M0 does not kill #1 or #2. They are dead on Deflated
Sharpe and on permutation respectively, and this measurement does not revive them either — T3's
fourth stress rung, which charged a full half-spread on the auction leg as insurance against being
wrong about M0, turns out to have been **over**-conservative for a top-500 MOO exit. The cost model
was not the thing that was wrong.

---

## 0. Provenance

| artifact | value |
|---|---|
| collection + analysis code | `scripts/m0_auction_fills.py` |
| raw records | `research/data/m0_cache/records.json.gz` (5,760 symbol-days) |
| computed result | `research/trading_bot/M0_AUCTION_FILLS.json` |
| cost-model change | `scripts/trading_bot/costs.py` — additive, §9 |
| data | Alpaca SIP: `/v2/stocks/auctions`, `/v2/stocks/quotes` (NBBO), `/v2/stocks/bars` 1-minute raw |
| broker mechanics | Alpaca *Orders at Alpaca* documentation, fetched 2026-08-17, §6 |

**Sample.** 66 trading days drawn with seed `20260817`, stratified 6 per calendar year over
2016-01-04 → 2026-08-14. 64 were collected — the two 2016-01 days have no month *m−1* to screen on,
the same Alpaca-history limitation T3 recorded as its deviation 2. One early close (2019-11-29) is
excluded, for the same reason T3 and T7 excluded early closes: the print exists but every 15:59
reference window sits *after* it, so the comparison would be measuring a stale post-close quote.
**63 full sessions, 5,670 symbol-days survive.**

**Universe.** Six ADV-rank tiers, ranked on month *m−1* raw dollar volume, 15 names per tier per
day. The point of a ladder rather than a top-500 cut is that "a call auction has no spread" is a
claim about a *mechanism*, so it either holds across the mechanism's whole domain or it is a claim
about mega-caps wearing a mechanism's clothes.

**Disclosed selection.** Names are ranked on month *m−1* but additionally required to have a monthly
bar in month *m*, so a delisted ticker is not requested. That is a lookahead on *which names get
measured*, never on any measured quantity. It is in the script's module docstring too.

**Sign convention.** `dev = (print − reference) / reference`, in bp. Positive means the print cleared
**above** the reference: adverse to a buyer, favourable to a seller.

---

## 1. The claim, decomposed into what is and is not answerable from a tape

"The order fills at the official print with zero spread" is three claims stacked, and they have very
different evidential status.

| | claim | answerable from SIP history? | this document |
|---|---|---|---|
| **C1** | an official auction print *exists* for the name that day | **yes** | §2 — measured |
| **C2** | the print is a *good* price, and specifically what its relationship to the quoted market is | **yes** | §3 — measured |
| **C3** | the auction is *large enough* that our order is not the auction | **yes** | §4 — measured |
| **C4** | *our* order, submitted through *our* broker, is one of the orders that clears in it | **no** | §10 — live protocol, not run |

C4 is the one the cost model actually leans on, and it is the one a tape cannot reach. What C1–C3
buy is a bound: they establish that the thing the order is supposed to join is present, large, and
priced, so that C4 collapses from "does this mechanism work?" to the much narrower "does this broker
route correctly, and does it get rejected?" — which is exactly what a bounded live batch answers.

---

## 2. C1 — does an official print exist? Measured, and it degrades hard

Availability of the primary-listing official prints — condition `6` at the close, condition `O` at
the open, largest size wins where several venues print.

| ADV tier | symbol-days | **official CLOSE print** | **official OPEN print** |
|---|---|---|---|
| A — rank 1–50 | 945 | **99.89 %** | 99.89 % |
| B — rank 51–200 | 945 | **100.00 %** | 100.00 % |
| C — rank 201–500 | 945 | **100.00 %** | 100.00 % |
| D — rank 501–1500 | 945 | **99.47 %** | 99.79 % |
| E — rank 1501–3000 | 945 | **94.60 %** | 98.73 % |
| F — rank 3001–6000 | 945 | **62.12 %** | 77.25 % |
| **top-500 proxy (A+B+C)** | **2,835** | **99.96 %** | **99.96 %** |

Conditional on the name having traded at all in the closing minute, the close print exists on 100.0 %
of A/B/C days, 99.7 % of D, 95.8 % of E and 82.2 % of F — so tier F's failure is partly "the stock
did not trade" and partly "it traded and still did not cross". For an MOC order the distinction does
not matter: **there is nothing to fill in.**

**Read this the right way.** For the universe #1 and #2 traded, C1 holds to four nines and the
zero-spread charge is not exposed here. For anything reaching past ADV rank ~1,500 it is exposed
badly, and a strategy that widens its universe to get more names is buying a friction it has not
priced. That is a constraint on *future* candidates, and it is the reason the ladder was measured.

---

## 3. C2 — where does the print actually sit? It is not the midpoint

### 3a. The single most direct table in this document

Placement of the official closing print inside the closing NBBO (last NBBO before 16:00:00 ET).

| ADV tier | at bid | at ask | inside, not mid | **at mid** | below bid | above ask |
|---|---|---|---|---|---|---|
| A — rank 1–50 | 18.6 % | 21.4 % | 10.0 % | **1.4 %** | 20.9 % | 27.8 % |
| B — rank 51–200 | 24.3 % | 24.7 % | 8.3 % | **1.6 %** | 19.7 % | 21.5 % |
| C — rank 201–500 | 29.9 % | 29.1 % | 7.0 % | **1.1 %** | 16.5 % | 16.4 % |
| D — rank 501–1500 | 31.3 % | 33.8 % | 7.6 % | **2.4 %** | 11.5 % | 13.4 % |
| E — rank 1501–3000 | 32.7 % | 36.5 % | 9.4 % | **2.5 %** | 9.8 % | 9.2 % |
| F — rank 3001–6000 | 28.0 % | 35.2 % | 21.8 % | **3.3 %** | 5.3 % | 6.4 % |
| **all, n = 5,250** | **27.4 %** | **29.7 %** | 9.9 % | **1.9 %** | **14.6 %** | **16.5 %** |

**The closing auction clears at the closing NBBO midpoint on 1.9 % of symbol-days. It clears outside
the closing NBBO entirely on 31.1 % — and on 48.7 % of mega-cap days**, because a mega-cap's quote is
locked one tick wide and the cross goes wherever the imbalance puts it.

### 3b. The same fact as a distribution

|dev| = |print − closing NBBO mid|, and the same quantity expressed in units of the closing
half-spread.

| ADV tier | \|dev\| median | \|dev\| p95 | closing half-spread, median | **\|dev\| ÷ half-spread, median** | …mean |
|---|---|---|---|---|---|
| A | 1.61 bp | 8.07 bp | 0.90 bp | **1.00** | 3.37 |
| B | 1.64 bp | 7.64 bp | 0.96 bp | **1.00** | 3.36 |
| C | 1.83 bp | 8.15 bp | 1.18 bp | **1.00** | 2.91 |
| D | 2.26 bp | 11.04 bp | 1.77 bp | **1.00** | 2.04 |
| E | 4.61 bp | 18.93 bp | 4.19 bp | **1.00** | 1.56 |
| F | 11.34 bp | 83.70 bp | 12.09 bp | **1.00** | 1.15 |
| **all** | **2.43 bp** | **19.08 bp** | 1.69 bp | **1.00** (p25 also 1.00) | **2.49** |

The median is exactly 1.00 in **every** tier and the p25 is 1.00 pooled: in three-quarters of cases
the print is *at least* a full half-spread away from the mid, and the modal case is exactly at the
bid or exactly at the ask. Mega-caps have the largest ratio (mean 3.4 half-spreads) precisely because
their spread is a single tick and the cross has more ticks of room to travel.

Against the volume-weighted closing minute rather than the mid, |print − VWAP(15:59)| is a median
**3.46 bp** pooled (A 2.67, C 3.13, D 3.43, F 8.66) — larger, not smaller, than against the mid.

### 3c. Why this is *not* automatically a cost, said explicitly so the document cannot be misread

If the backtest marks the leg at the **official print** and the order executes at the **official
print**, then the gap measured above is not a friction — it is inside the return series already, on
both sides of the trade, and charging it would be double-counting. T3 exits at the opening print and
T7 transacts at closing prints on both legs; both are in this case.

The gap becomes a real, unmodelled cost the moment a backtest marks the leg at anything else — a
minute-bar close, a midpoint, a VWAP — and then claims auction execution. The magnitude of that
mistake is exactly the table above: a median **1.9 bp** between the print and the 15:59 last trade
(mean 5.2, p95 18.0), and a median **2.4 bp** between the print and the closing mid.

**And there is one way the gap stops being harmless even for a print-marked backtest.** It is not
independent of a closing-window signal. Regressing the print's deviation from the closing mid on the
last-ten-minute return gives a slope of **+0.0464 bp per bp, t = +11.69** (n = 4,964): the print
leans the way the last ten minutes leaned. The level is small — mean deviation runs from −0.26 bp in
the most-sold quintile to +0.52 bp in the most-bought — but it is not noise, and it means a signal
built out of the closing window shares microstructure with the price it marks at. §8 is the full
diagnostic and it is exploratory.

---

## 4. C3 — is the auction big enough to hide in? At the close, yes

Notional cleared in the official print, `size × price`.

| ADV tier | **close, median** | close, p05 | **open, median** | open, p05 | close print ÷ 15:59 minute volume, median |
|---|---|---|---|---|---|
| A — rank 1–50 | **$104.7 M** | $8.0 M | $16.2 M | $2.0 M | 3.10× |
| B — rank 51–200 | **$37.8 M** | $2.2 M | $5.0 M | $1.0 M | 3.22× |
| C — rank 201–500 | **$15.6 M** | $0.40 M | $1.9 M | $0.42 M | 2.96× |
| D — rank 501–1500 | $3.4 M | $42.7 k | $457 k | $91 k | 2.31× |
| E — rank 1501–3000 | $0.55 M | $8.6 k | $95 k | $12 k | 1.98× |
| F — rank 3001–6000 | **$14.2 k** | $151 | $15.8 k | $555 | 1.00× |
| **top-500 proxy** | **$37.0 M** | **$1.29 M** | **$4.8 M** | **$669 k** | — |

The closing auction is a genuine liquidity event: **2.5× the entire last minute's volume** at the
median, 3.1× in mega-caps. The opening auction is roughly **7× smaller** than the closing one and is
the binding constraint on any close-to-open strategy.

**Capacity arithmetic for a T3-shaped book** (≈477 names a night, equal-weight, dollar-neutral),
using the thinnest 5 % of top-500 *opening* auctions at $669 k, and a 1 % participation ceiling:

> per-name budget $6.7 k → **≈ $3.2 M of capital** before the thinnest twentieth of exits exceeds 1 %
> of their auction; ≈ $16 M at a 5 % ceiling.

That is a real ceiling and it was never stated. It is also comfortably above any size this programme
is close to deploying, so it is a note for later, not a finding against anything now.

---

## 5. The opening leg, which is a different animal

| ADV tier | \|print − first post-print NBBO mid\|, median | p95 | post-open half-spread, median | \|print − VWAP(09:30)\|, median |
|---|---|---|---|---|
| A | 3.42 bp | 22.6 bp | 4.08 bp | **2.97 bp** |
| B | 6.79 bp | 38.1 bp | 10.44 bp | 2.27 bp |
| C | 9.40 bp | 55.1 bp | 18.70 bp | 1.37 bp |
| D | 14.94 bp | 102.2 bp | 33.83 bp | 1.22 bp |
| E | 21.77 bp | 142.2 bp | 56.70 bp | 0.45 bp |
| F | 28.25 bp | 237.5 bp | 66.56 bp | **0.00 bp** |
| **all** | **11.34 bp** | 108.7 bp | 20.71 bp | **1.38 bp** |

Read the two outer columns together, because separately each is misleading. The print is far from the
NBBO midpoint at 09:30 — but the NBBO at 09:30 is itself a median 20.7 bp wide and unstable, so that
distance is mostly the *quote* being uninformative, not the print being bad. Against the opening
minute's own volume-weighted price the print is a median **1.38 bp** away, and the gap *shrinks* to
zero as liquidity falls, because in a thin name the opening print simply **is** the opening minute's
volume.

**The honest statement about the open:** the opening print is a real, executable, dominant-volume
price and marking a MOO leg at it is legitimate. What it is *not* is a low-uncertainty price — a
trader who commits to MOO gives up a median 11 bp of price certainty relative to what the quoted
market will say seconds later, and 108 bp at the 95th percentile. That is variance the backtest
carries but does not display, and it is a reason to prefer the closing auction to the opening one
wherever a candidate has the choice.

---

## 6. Broker mechanics — the constraint T3's D2 found, confirmed at the broker

From Alpaca's own order documentation, fetched 2026-08-17:

| | |
|---|---|
| MOO / LOO | `time_in_force = opg`, with `market` or `limit` |
| MOC / LOC | `time_in_force = cls`, with `market` or `limit` |
| **`cls` submissions are REJECTED** | **15:50–19:00 ET** |
| **`opg` submissions are REJECTED** | **09:28–19:00 ET** |
| routing | "routed to the primary exchange", executing "per the exchange's auction rules" |
| timing caveat | orders "do not necessarily execute exactly at 9:30am / 4:00pm ET" |

Two things follow.

1. **T3's D2 was right, and now it is right at two levels.** The 15:50 cutoff is not only the
   exchange's MOC deadline, it is the broker's hard rejection boundary. A signal measured to 15:59
   can never be submitted on-close. D2 already priced that and found the pre-cutoff version of the
   signal at t = 1.38. Nothing here rescues it.
2. **A close-to-open book is operationally feasible.** Enter as a taker at 15:59:5x, then submit the
   `opg` exit any time after 19:00 ET the same evening or before 09:28 the next morning. Both windows
   are open.

Alpaca's own wording — "per the exchange's auction rules", "not necessarily exactly at 4:00pm" —
is a description of the mechanism, **not a guarantee that a submitted `cls` order joins the primary
closing cross**. That gap is precisely C4 and it is what §10 exists to close.

---

## 7. What this does to shortlist candidates #1 and #2

Guardrail 2 asked for this plainly, in either direction.

| | |
|---|---|
| **#1 (T3, pressure reversal)** — entry taker at 15:59, exit MOO at the opening print | The exit leg's zero charge **holds**: 99.96 % availability, median $4.8 M opening auction, order size negligible against it. **M0 does not further condemn #1.** It stays dead on DSR = 0.9379 against a pre-registered 0.95. |
| T3's fourth stress rung (`h` entry + `h` exit, "the auction rail is not free") | **Over-conservative**, now that the rail is measured. It priced a risk that C1–C3 have largely retired for this universe. The candidate did not die there anyway. |
| **#2 (T7, ex-dividend)** — both legs MOC at closing prints | The zero charge on **both** legs holds for the top-500 universe. **M0 does not further condemn #2.** It stays dead on permutation p = 0.213 and DSR = 0.076, and on the tax arithmetic in T7 §6. |
| the shortlist's *framing* — "fills at the official close/open price with **zero spread**" | Half right, and the wrong half matters for future work. There is no spread to cross. There is also **no midpoint**: the print is at the mid 1.9 % of the time and outside the NBBO 31 % of the time. Any future candidate that marks a leg at a mid, a bar close or a VWAP and then claims auction execution is wrong by a median 1.9–3.5 bp, with a p95 of 18–21 bp. |

**The load-bearing negative that survives all of this is unchanged**: both candidates died on the
statistics, not on the costs. This measurement removes the excuse that they might have been killed by
an unmeasured cost assumption. They were not.

---

## 8. Exploratory diagnostics — NOT pre-registered, no verdict follows from them

Labelled here and in the JSON because a number that was not frozen is not evidence. Both were run
after the availability/placement measurement, to explain it.

### 8a. Does the print's deviation from the closing mid revert overnight? **Cannot be resolved here.**

Regression of the overnight return (close print → next opening print, bp) on the deviation (bp):

| | slope | t | R² |
|---|---|---|---|
| **pooled, n = 5,210** | **−0.597** | **−4.50** | **0.0039** |
| A — rank 1–50 | −3.715 | −2.62 | 0.0072 |
| B — rank 51–200 | +1.409 | +1.23 | 0.0016 |
| C — rank 201–500 | −2.054 | −3.69 | 0.0142 |
| D — rank 501–1500 | +0.344 | +0.66 | 0.0005 |
| E — rank 1501–3000 | +0.086 | +0.22 | 0.0001 |
| F — rank 3001–6000 | −0.654 | −4.79 | 0.0402 |

The pooled point estimate says 60 % of the dislocation unwinds by the next open, and the pooled
t-statistic looks respectable. **Do not believe it.** R² is 0.4 %, the sign flips across tiers, and
two of the tier slopes are *below −1*, which would mean the print overshoots by more than the whole
deviation — an estimate that is not physically sensible and is telling us the regressor is tiny
relative to overnight noise. The honest statement is that **this sample cannot resolve whether the
auction dislocation reverts.** It is recorded so a later, better-powered pass does not have to
rediscover the question, and because reporting only the flattering pooled row would be exactly the
failure `FINDINGS.md` §6 records against every retracted claim in this programme.

### 8b. Does the print's deviation carry what T3's signal trades on? **Suggestive, and underpowered.**

| regression (all in bp, n = 4,964) | coefficient | t |
|---|---|---|
| **P1** — deviation ~ last-10-min return | **+0.04639** | **+11.69** |
| **P2** — overnight ~ last-10-min return | −0.0404 | −0.81 |
| **P3** — overnight ~ last-10-min return **+** deviation | r10 −0.0301 / dev −0.2221 | −0.60 / −1.25 |

Quintiles by last-10-minute return:

| quintile | mean r10 | mean deviation | mean overnight |
|---|---|---|---|
| 1 (most sold) | −43.97 bp | **−0.258 bp** | +15.45 bp |
| 2 | −9.62 bp | +0.275 bp | +13.26 bp |
| 3 | +0.91 bp | +0.682 bp | +17.47 bp |
| 4 | +11.17 bp | +0.059 bp | +26.98 bp |
| 5 (most bought) | +42.98 bp | **+0.520 bp** | +29.86 bp |

**P1 is the finding and it is firm**: the closing print leans the way the closing move leaned, at
t = +11.7. **P2 and P3 are not findings at all** — this sample is six liquidity tiers pooled across
days with no cross-sectional demeaning and no decile portfolio, which is not T3's estimator, and it
reproduces neither T3's reversal nor its absence (t = −0.81). Nothing here confirms or refutes T3.
What it does establish is a *mechanism to be careful of*: a signal measured in the closing window is
correlated with the auction print's own dislocation, so a future candidate of that shape needs the
bounce-free check T3 ran as its D1, not an assumption.

---

## 9. The honest charge, and what changed in `costs.py`

### 9a. The number

For a leg that is **(a)** in ADV tiers A–D (rank ≤ 1500), **(b)** executed `cls`/`opg` and submitted
inside the broker's window, **(c)** marked in the backtest at the official print, and **(d)** sized
well under 1 % of that print:

> **quoted half-spread = 0 bp. That is now a measurement, not a mechanism argument.**

plus a **non-fill provision** — P(no official close print) × a full quoted spread to unwind by hand:

| ADV tier | P(no close print) | median half-spread | **provision** |
|---|---|---|---|
| A — rank 1–50 | 0.11 % | 0.90 bp | **0.0019 bp** |
| B — rank 51–200 | 0.00 % | 0.96 bp | **0.0000 bp** |
| C — rank 201–500 | 0.00 % | 1.18 bp | **0.0000 bp** |
| D — rank 501–1500 | 0.53 % | 1.77 bp | **0.0187 bp** |
| E — rank 1501–3000 | 5.40 % | 4.19 bp | **0.4520 bp** — refused, see below |
| F — rank 3001–6000 | 37.88 % | 12.09 bp | **9.1622 bp** — refused, see below |

The provision is a **floor**: it prices the spread of the manual unwind and *not* the overnight gap
risk of carrying a position the strategy never meant to hold. In the liquid core it is two
thousandths of a basis point and rounds away. Outside it, it stops being a rounding error, which is
the whole point of measuring the ladder.

### 9b. The change

Additive, in `scripts/trading_bot/costs.py`. **No existing cost number was changed**, so no prior
result moves. `tests/test_t2_backtest_harness.py` — 113/113 still pass.

1. New `SlippageProvenance.MEASURED_M0_AUCTION_PRINT`, gated in `assert_available()` on
   `research/trading_bot/M0_AUCTION_FILLS.json` existing **and** covering ≥ 5,000 symbol-days.
   Delete or truncate the result and the rig returns to refusing, exactly as `MEASURED_B22B` does.
   The provenance string states in its own text what it does **not** claim: that the broker's order
   joins the cross.
2. `EXCHANGE_MECHANISM_UNVERIFIED_FILL`'s text amended. It used to say M0 was UNPERFORMED. It now
   says which half of M0 is done and which half still needs live orders, and it still requires an
   accompanying real-half-spread stress rung. It is kept rather than deleted so that
   `T7_HELDOUT_RESULT.json`, which carries the label, stays readable.
3. New `measured_auction_leg(leg, tier)` returning the `(half_spread, extra_slippage)` pair for one
   MOC/MOO side, reading the provision out of the M0 result rather than having it typed in, and
   **refusing** for tiers E and F rather than extrapolating a zero into a liquidity band where the
   measurement says the auction is often not there at all.

---

## 10. SECONDARY — the live paper protocol, written and deliberately NOT run

The task offered a bounded batch of small paper MOC/LOC/MOO orders as an optional forward
measurement. **No order of any kind was submitted in the course of this work.** The reason is the
guardrail itself, and it is worth stating rather than eliding:

> Guardrail 1 requires that the session end with **0 open positions and 0 open orders, verified**.
> An on-close order that satisfies that constraint inside one agent run is an order that was
> **cancelled before the auction**, and a cancelled MOC measures nothing. A real measurement of C4
> requires holding a live `cls` order through 16:00 and comparing the fill to the print published
> afterwards — which accrues across sessions and needs an owner decision about carrying paper state
> between runs. That is a process call, and per the standing rule it is the owner's, not mine.

The protocol, ready to authorise:

| | |
|---|---|
| account | PAPER only (`paper-api.alpaca.markets`); `scripts/trading_bot/paper.py` still refuses `submit()` by construction and would need the owner-gated diff first |
| batch | 20 symbols/session — 5 each from tiers A, B, C, D — 1 share each, both sides |
| orders | day 1: `market` + `tif=cls` submitted 15:40–15:45 ET. day 2 (flatten): `market` + `tif=opg` submitted after 19:00 ET the previous evening |
| primary metric | (fill price − official print) in bp, per order; and **fill rate**, which is the actual C4 question |
| secondary | fill timestamp vs print timestamp; whether LOC orders collar; whether short sales are accepted on-close |
| stop rule | any unfilled or off-print fill is the finding — do not scale the batch to chase a clean number |
| sessions | ≥ 10, so a 1-in-20 non-fill is distinguishable from a 1-in-200 one |
| cost | ~$1,000 of paper notional per session; zero real money at any point |

Ten sessions of 20 orders gives 200 observations, enough to bound the non-fill rate below ~1.5 % and
to detect any systematic off-print fill larger than a fraction of a basis point. That is the whole
remaining question.

---

## 11. What this document does not claim

- **It does not claim our orders fill.** C4 is unmeasured. Everything here bounds the question; none
  of it answers it. Any cost model quoting `MEASURED_M0_AUCTION_PRINT` says so in its own text.
- **It does not revive #1 or #2.** Both died on pre-registered statistical gates. This measurement
  removes one excuse for them and adds nothing in their favour.
- **It measures 63 sessions, not the tape.** 5,670 symbol-days is enough for availability rates and
  placement fractions, which are proportions; it is *not* enough for the reversion regression in §8a,
  which is why §8a refuses to conclude.
- **It does not price impact.** C3 measures the auction's size, from which a participation ceiling
  follows; it does not measure what happens to the print when you take 5 % of it. Nobody has measured
  that here, and the capacity numbers in §4 are participation ratios, not impact estimates.
- **It does not price the overnight gap risk of a non-fill.** The provision in §9a is a spread-only
  floor and says so.
- **Survivorship is reduced, not eliminated**, in the same way and for the same reason as T3 §8: the
  universe is assembled from Alpaca's asset list, and a name absent from it is invisible here.
- **One early close was excluded**, not modelled. Half-days have a 13:00 auction and their own
  microstructure; this document says nothing about them.
