# T17 — the ORB multi-position day-trading strategy, run once through the honest harness

**Verdict on the frozen gates: DEAD.** Two of the three pre-registered gates pass decisively;
the deflated-Sharpe gate fails, and the pre-registration says all three are required.

**The finding that matters more than the verdict:** at the paper's own zero-slippage
assumption this rig reproduces the paper almost exactly — **held-out Sharpe 2.743 against the
claimed 2.81, max drawdown 11.4 % against the claimed 12 %**. Charging the friction the paper
omitted, and that T5/B22B measured, takes that to **0.674 or 1.088 depending on which of two
legitimate transfers of the same measurement you use**, and to **−0.034** once the paper's own
$0.0035/share commission is added on top. **Roughly two thirds of the published Sharpe is
friction the paper did not model.**

| | file | sha256 |
|---|---|---|
| power gate, hashed before the census | `T17_POWER_GATE.md` | `03d257ce8ff6c92c09b0be4c896dacc6a424c8925d96a805e2fc25a80fec6465` |
| pre-registration, hashed before any PnL | `T17_PREREGISTRATION.md` | `9871b73619b8cc0fc104ec1ec5eb90fdbc27f7eb6866ea748a397c2cdfab87b6` |
| the rule | `scripts/trading_bot/t17_orb.py` | `c54b0349a847fa05a68bb1050fe8855a74afd549516c910026181458975907c6` |
| the driver | `scripts/trading_bot/t17_run.py` | `62f0818c4481c73bcb8555c4b911c11c35cb5ec553ccc442599366b2dbf2c7ae` |
| the pinned B22B arithmetic, consumed not copied | `scripts/b22b_slippage_harness.py` | `a0f1b4c4…` (unchanged) |

---

## 1. STEP 1 — the mandatory power census

Judged against `T17_POWER_GATE.md`, hashed **before** `T17_POWER_CENSUS.json` existed and
with that file's absence asserted in the same command.

| gate | measured | threshold | |
|---|---|---|---|
| **G0** data census | 1,158 held-out sessions with a full top-20; **99.95 %** of selected stock-days served by SIP | ≥ 900 sessions, ≥ 98 % | **PASS** |
| **G1** portfolio power — *the binding gate* | MDE annualised Sharpe **1.306** over 4.60 years | ≤ 1.405 | **PASS** |
| **G2** trade count | 18,753 projected held-out trades on 1,158 sessions | ≥ 2,000 / ≥ 500 | **PASS** |
| **G3** per-trade MDE — *the diagnostic* | **0.0863 R** | ≤ 0.080 R | **FAIL** by 7.8 % |
| **G4** cost resolution | 429 measured stock-days | ≥ 100 | **PASS** |

**This programme's usual failure mode did not occur.** T9 and T15 died because their windows
could not see the effect they were testing. This one can: the claimed Sharpe of 2.81 needs
**0.99 years** to certify and the held-out window has **4.60**, so the test can detect a
strategy running at *half* the advertised rate.

**G3 failed and both readings are recorded** (`T17_POWER_CENSUS.json` →
`verdict_note_appended_after_the_census_ran`). The census script's strict `all()` returns
POWER-BLOCKED. The frozen gate document attaches a blocking consequence to exactly two gates
— G1 ("Fail ⇒ POWER-BLOCKED and the window is not spent") and G4 ("Fail ⇒ the test is not
run") — and states twice that the daily portfolio series is "the binding one" and the
per-trade statistic "a diagnostic". Both pass. The window was spent on that basis, and the
strict reading is left in the artifact unchanged rather than edited away. The honest,
same-day-cluster-adjusted per-trade MDE is **0.348 R**, which fails by 4.3× — which is
precisely why the gate named the per-trade statistic a diagnostic in the first place.

### The census number that decides the whole question

R — the paper's risk unit, 10 % of ATR(14) — is **32.3 basis points of notional at the median
on T17's own selected stock-days** (mean 45.7 bp; B22B's 2025 most-actives pool was wider at
51.4 bp, which is why both are reported).

> The T6 per-side round trip is **5.59 bp of notional = 0.173 R**.
> The paper's own reported per-trade edge at the filter it uses is **0.08 R**.
> **The honest round-trip cost is 2.16× the paper's headline per-trade edge, before a single
> trade is simulated.**

That arithmetic was written into the power gate before the number was looked up.

---

## 2. STEP 2 — the held-out run. 2022-01-03 → 2026-08-14, 1,158 sessions, 18,851 trades. Once.

Universe: 14,794 tickers (NASDAQ/NYSE/ARCA/BATS/AMEX, **delisted names included**), screened
point-in-time to a median of **1,127** eligible names a session in this window, of which the
top 20 by opening relative volume are traded — median relative volume of a selected name
**565 %** of its own 14-session average.

| configuration | Sharpe | ann. return | max DD | t | DSR |
|---|---|---|---|---|---|
| **zero cost — DIAGNOSTIC ONLY, this is the paper's assumption** | **2.743** | +79.6 % | 11.4 % | 5.88 | 0.9997 |
| T6 measured, slippage as bp of **notional** | 0.674 | +13.4 % | 39.1 % | 1.44 | 0.0739 |
| **T6 measured, slippage as bp of R — PRIMARY** | **1.088** | **+24.1 %** | **27.9 %** | **2.33** | **0.2945** |
| T6 + the paper's own $0.0035/share, notional | **−0.034** | −3.1 % | 54.7 % | −0.07 | 0.0018 |
| T6 + the paper's own $0.0035/share, R | 0.374 | +6.0 % | 41.7 % | 0.80 | 0.0188 |
| T6 measured, rank-truncated sizing (~2 names/day) | 1.084 | +108 % | **75.2 %** | 2.32 | 0.2656 |

**The gates, as frozen:**

| gate | result | |
|---|---|---|
| net mean daily return > 0 | +0.0953 %/day | **PASS** |
| permutation p < 0.05 | **p = 0.0005**, 0 of 2,000 direction-randomised runs matched it | **PASS** |
| deflated Sharpe ≥ 0.95 | **0.2945** | **FAIL** |

**Verdict: DEAD.**

### Why the DSR gate failed, stated plainly rather than argued away

The observed per-observation Sharpe is 0.0686. The chance ceiling implied by the six declared
trials and their cross-trial variance is **0.0836** — an annualised Sharpe of **1.327**. The
result is *below its own chance ceiling*, the same shape of death as T10.

**And the input to that ceiling is arguably wrong, which is recorded here and not used to
overturn anything.** The six declared trials are one strategy priced six ways, not six
searches over strategy space. Their spread is dominated by the deliberately mislabelled
zero-cost diagnostic (Sharpe 2.74) and the commission variant (−0.03), so `sharpe_variance`
measures **cost-model sensitivity, not search luck**, and Bailey & López de Prado's deflation
wants the latter. At `trials = 1` — a single fully specified published rule with nothing
searched — the statistic reduces to the probabilistic Sharpe against zero:

| | DSR at 6 declared trials | PSR at trials = 1 (POST HOC) |
|---|---|---|
| T6, slippage as bp of R | 0.2945 | **0.9931** |
| T6, slippage as bp of notional | 0.0739 | **0.9323** |

**Even under the most generous specification available, one of the two legitimate transfers of
the same measurement still fails the 0.95 threshold.** The pre-registered number is 0.2945 and
the verdict stands at DEAD. What the post-hoc column establishes is that this is a knife-edge
result, not a rout — and a knife-edge result is not a bot.

---

## 3. Where the money goes, per trade, in the strategy's own unit

| | R per trade |
|---|---|
| gross, before any friction | **+0.2060** |
| price slippage, drawn from B22B's 425 decontaminated measurements | −0.0535 |
| notional charge (the exit half-spread) | −0.0793 |
| **net** | **+0.0732** |

**Friction is 0.133 R per trade against a pre-friction edge of 0.206 R — it consumes 64 % of
it.** (The reported `mean_gross_r` of +0.1525 is *after* the price slippage is already in the
fill, which is why it does not equal the top row; the two sum correctly to the net.)

For scale: the paper's own reported per-trade edge in the bucket it trades is **+0.08 R**.
Our pre-friction 0.206 R is larger because the top-20 selection sits far above the 100 %
relative-volume threshold — median 565 % — which is exactly the effect the paper documents.
**The edge is bigger than advertised and the cost is bigger still.**

The distribution is not a distribution anyone should size a bot on:

| | net R |
|---|---|
| p1 | −4.05 |
| p25 | −1.19 |
| **p50** | **−1.10** |
| p75 | −1.04 |
| p95 | +8.57 |
| p99 | +20.41 |
| min / max | −26.70 / +95.18 |

**85.6 % of trades are stopped out and only 13.9 % are net winners.** The median trade loses
1.1 R. Every dollar of the result comes from a right tail of 5 % of trades, in a rule whose
stop is 0.32 % of price. The paper's 48.4 % "hit rate" is a share of profitable *days*; the
share of profitable *trades* is a seventh of that.

---

## 4. The fat tail, modelled explicitly

**a. Re-drawing the friction.** 50 independent draw sequences from the same measured
distribution, nothing else changed (`T17_FAT_TAIL_HELDOUT.json`, POST HOC):

| | min | p10 | p50 | p90 | max |
|---|---|---|---|---|---|
| Sharpe | 0.907 | 1.040 | 1.101 | 1.190 | 1.223 |
| max drawdown | 23.7 % | 25.2 % | 27.5 % | 29.8 % | 31.3 % |
| t | 1.94 | 2.23 | 2.36 | 2.55 | 2.62 |

6 % of draw sequences land below Sharpe 1.0. **The randomness of the draw is not what kills
this — the level of the friction is.** Note also that the honest drawdown is **27.9 %**
against the paper's reported 12 %: friction more than doubles the drawdown while halving
the return.

**b. Charging the tail to every trade.** If B22B's p90 or p95 slippage were the typical fill
rather than the tail, the strategy is not marginal, it is destroyed: Sharpe **−2.34** and
**−4.88**, drawdowns of 93.8 % and 99.3 %. This is not a forecast; it is the distance to the
cliff.

**c. The single most load-bearing assumption in this whole test is bar granularity.** R is
0.32 % of price and a one-minute bar in a top-relative-volume name routinely spans that. The
frozen rule deems the stop hit on the entry bar only if the bar **closes** through it, because
most of that bar's low happened *before the position existed*. Under the maximally adverse
reading — the entry bar's whole low — the held-out Sharpe is **−8.36** with a **99.6 %**
drawdown.

> **The truth is somewhere between +1.09 and −8.36, and one-minute bars cannot say where.**
> Resolving it needs tick-level entry and stop timing on ~19,000 held-out stock-days. B22B
> already did exactly that measurement for *entries* on 429 stock-days; nobody has done it for
> exits. **This is the single measurement that would settle T17**, and it is the same gap the
> T6 correction flagged: the exit leg has never been measured.

**d. The short leg.** Long-only Sharpe 0.721 (9,646 trades), short-only 0.719 (9,205). The two
legs are symmetric, so this is not a short-side artifact — but B22G found 8 of the 52 names
B22B screened are hard-to-borrow and not shortable at Alpaca, point-in-time shortability is
not obtainable, and losing the short leg halves the trade count.

---

## 5. The secondary window: entirely after the paper's own study period

2024-01-02 → 2026-08-14, 657 sessions, 10,540 trades. The paper's sample ends in 2023, so none
of this is theirs.

| configuration | Sharpe | ann. return | max DD | t |
|---|---|---|---|---|
| zero cost (diagnostic) | 2.865 | +89.7 % | 9.2 % | 4.63 |
| T6, bp of R | 1.207 | +28.7 % | 13.3 % | **1.95** |
| T6, bp of notional | 0.921 | +20.6 % | 17.4 % | 1.49 |
| T6 + paper commission, bp of notional | 0.268 | +3.6 % | 22.6 % | 0.43 |

**Verdict on the same frozen gates: DEAD** (DSR 0.4186). The pattern is identical and the
strategy has not decayed since publication — **what removes it is cost, not crowding.**

---

## 6. What this establishes, and what it does not

**Established.**

1. **The ORB rule is real and this rig reproduces it.** Held-out zero-cost Sharpe 2.743 and
   max drawdown 11.4 % against the paper's 2.81 and 12 %, on a different data vendor, a
   different universe construction, and a window 57 % of which is outside the paper's own
   sample entirely.
   The permutation null is destroyed: **0 of 2,000** direction-randomised runs matched the
   observed mean. **The opening candle's colour genuinely predicts which side breaks.**
2. **Between 60 % and 75 % of the published Sharpe is friction the paper did not model.**
   2.743 → 1.088 or 0.674. The paper's text contains `slippage`, `bid-ask`, `market impact`,
   `capacity` and `fill` zero times, and this is what that omission is worth.
3. **The paper's own commission assumption, added to our measured slippage, takes it to
   zero.** −0.034 Sharpe. The single cost the authors *did* model is enough to finish it once
   the ones they did not are present.
4. **It fails the pre-registered gate.** DSR 0.2945 against 0.95.
5. **Multi-position day trading does not die at the friction floor the way everything else in
   this programme did.** This is the first candidate to survive to a *marginal* answer rather
   than a 13-sigma negative. That is a genuinely different result and it should not be
   flattened into "another one dead".

**Not established, and load-bearing.**

- **Whether the entry-bar stop rule is right.** ±1.09 to −8.36 rides on it. Unresolved without
  tick data.
- **Which transfer of the B22B measurement is correct** — the same measured slippage charged
  as basis points of R gives Sharpe 1.088, charged as basis points of notional it gives 0.674.
  Both are legitimate readings of one measurement and the verdict differs between them even at
  the most generous PSR specification (0.9931 vs 0.9323).
- **The exit leg has still never been measured.** Half the round trip is an
  `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG`.
- **Capacity.** B22B measured tens to hundreds of shares resting at the touched side. This
  test charges a price but never asks whether the size fills. At 4× gross on twenty names the
  per-name notional is 20 % of equity, and nothing here says that clears.
- **Survivorship is mitigated, not cured**, and daily bars are raw, so a split leaves an ATR
  jump for up to 14 sessions.

---

## 7. Recommendation to the owner — a decision, not a green light

The pre-registered verdict is **DEAD** and it is not being overturned. But this candidate did
not die the way the previous twelve did, and the honest summary is:

> **The ORB edge is real, it is large before costs, it is uncorrelated, and after honest
> friction it is worth somewhere between a Sharpe of 0.67 and 1.09 — with an error bar that
> includes catastrophic, driven by one unmeasured quantity.**

Three options, with a recommendation:

1. **Stop.** Defensible: it failed its own gate, and a Sharpe near 1 with a 28 % drawdown and
   an 87 % friction ratio is not what the programme set out to find.
2. **Measure the exit and the entry-bar timing on tick data, then re-run under a new
   pre-registration.** This is the *only* thing that would move the answer, it is a known and
   bounded measurement (B22B's harness already does the entry half), and it resolves a
   −8.36-to-+1.09 spread. **This is the recommendation.**
3. **Paper-trade it forward now, T4-style.** Premature. A forward test cannot resolve the
   entry-bar ambiguity — a live fill would, but that is the expensive way to learn what a tick
   measurement gives for free, and the pre-registered gate says DEAD.

**No orders were placed and nothing was committed.** Live execution remains owner-gated.
