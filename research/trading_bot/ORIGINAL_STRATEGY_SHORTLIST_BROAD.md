# ORIGINAL STRATEGY SHORTLIST — BROAD (non-perp) squad

**Synthesis judge's verdict on 15 invented theories across 5 lenses, after adversarial critique.**
Date 2026-08-19. Scope: everything except crypto perpetuals (separate squad).

---

## 0. Verdict in one paragraph

Fifteen theories were invented and gauntleted. **Two survive** the strict filter
(`overall == PROMISING` **and** `free_data_available == true`). Eleven were killed, two were marked
WEAK. Both survivors are US-listed exchange-traded products reached through the same Alpaca SIP
credential, so **the breadth this squad was asked to deliver is not there** — the honest statement is
"two survivors, one venue, two instrument classes", not "three picks across three asset classes". I
decline to promote a WEAK candidate to make the list look wider.

Both survivors share the one property that killed T9, T15, T23, T24 and T25 five times over and that
FINDINGS §10 names as the programme's binding constraint: **their estimand is a paired relative
return with the common factor zero by construction, so the `(2.80/S)²`-years wall of §5h does not
engage, and the data they need is already on disk.** Neither needs a forward-collection wait. Both
resolve for compute, not for calendar.

Both are also **expected to die**, and I say so before either is funded. My honest priors: Pick 1
~30 % survives its own design-window gross gate; Pick 2 ~15 %. That is the point — each is
structured so the kill costs an afternoon on the design window and **does not burn the held-out
window**, which is the process rule §5j says outranks any next candidate.

---

## 1. The filter, applied mechanically

| lens | theory | gauntlet | free data | kept? |
|---|---|---|---|---|
| Equity/ETF microstructure | **Wrapper-spread reversion in same-claim ETF sibling groups** | **PROMISING** | **true** | **✅ PICK 1** |
| Equity/ETF microstructure | Dual-class flow residue (index rules split the cash flow) | WEAK | true | ✗ |
| Equity/ETF microstructure | "The wrapper the calendar buys" (dated allocation flow) | WEAK | true | ✗ (fold in as declared arm 2 of Pick 1) |
| Options / vol surface | Vol-Time Sawtooth (Deribit clock-composition) | KILL | true | ✗ |
| Options / vol surface | Charm Clock (dealer time-decay rebalancing) | KILL | true | ✗ |
| Options / vol surface | Gamma Cliff (08:00 UTC expiring-gamma extinction) | KILL | **false** | ✗ |
| FX & rates | Segregated-Tape Duration Transmission (US rates → alt/BTC) | KILL | true | ✗ |
| FX & rates | The Only Live Lira (Binance TRY tape → TUR) | KILL | true | ✗ |
| FX & rates | Creation Unit Bigger Than The Market (currency trusts) | KILL | true | ✗ |
| Commodities | **The Settlement-Print Concession** | **PROMISING** | **true** | **✅ PICK 2** |
| Commodities | Shuttered-Pit Lead-Lag (grain ETFs overnight) | KILL | true | ✗ |
| Commodities | The Fragmented Roll Calendar | KILL | true | ✗ |
| Method / ML | Two-timescale voting-premium filter (dual-class) | WEAK | true | ✗ (see §5, conditional third) |
| Method / ML | Wrapper-redundancy relative value | KILL | true | ✗ |
| Method / ML | Exhaustively-enumerated cell miner | KILL | true | ✗ (promote the **machinery**, not the trade) |

**Survivor count: 2.**

---

## 2. Ranking the survivors

Scored on originality × plausibility-the-inefficiency-is-real × resolvability-on-free-data ×
bounded-tail. 1–5, higher better.

| | originality | inefficiency real? | resolvable? | bounded tail? | product |
|---|---|---|---|---|---|
| **Pick 1 — pre-cutoff sibling-wrapper dislocation** | 4 | 3 | **5** | 4 | **240** |
| **Pick 2 — settlement-print concession** | 4 | 2 | 4 | 4 | **128** |

Pick 1 ranks first on three grounds. (a) Half its friction is a **fixed transfer tax** (SEC §31), not
a spread, because the exit leg clears in a call auction that M0 measured at a 99.96 % print rate and a
$37 M median print for exactly this tier. (b) Its exit print carries **1.6 bp of noise against a
17-hour leg's 4.8 bp**, so its per-observation sd is 2.9 bp rather than 6.7 — and MDE scales linearly
in sd. (c) Its observations are already on disk for both windows. Against that, the coverage probe I
ran for this document (§3.2a) cut its nominal universe from 15 independent spreads to **4–6** and
forced the primary arm to change; the score above is the post-probe one.

Pick 2 ranks second because its friction (~3.9 bp) is a **spread**, its gross is unmeasured, and the
market publishes its own quote for the very concession the theory wants to harvest — CME's
Trade-at-Settlement basis in WTI runs 0–2 ticks ≈ **0–2.9 bp**, at or *below* the ETF round trip. The
honest prior is that Pick 2 is dead. It is still worth an afternoon because the kill is decisive,
costs no held-out window, and the measurement is reusable.

---

## 3. PICK 1 — Pre-cutoff dislocation in same-claim ETF sibling groups

### 3.1 The thesis, rewritten after the gauntlet

The theory as invented claimed a −0.79 to −0.91 reversion beta on the **closing-print** spread
between same-claim wrappers. **That claim is retracted here before it is tested.** Two independent
critics converged on the same objection and they are right:

- An errors-in-variables regression whose regressor is dominated by transient measurement noise
  returns exactly `beta = −var(u)/var(d)`. A beta of −0.85 is a statement that **85 % of the
  close-print spread deviation IS print noise**, not that 85 % of a mispricing reverts.
- M0 independently sizes that noise: `|print − mid|` median **1.61 bp** per leg in tier A, the print
  sits at the closing NBBO mid on **1.9 %** of symbol-days and *entirely outside* the closing NBBO on
  **31.1 %**. M0 §8a already refused to conclude on this exact regression.
- The method lens independently *measured* the close-print z-fade across 13 wrapper pairs on the
  auction rail, 1,168 round trips, 2016–2026: pooled **+2.33 bp gross** against a 0.6–1.2 bp friction
  band, with **92 % of the gross concentrated in two pairs** (VOO/SPY +20.9 bp on 48 trades,
  IVV/SPY +17.6 bp on 47) and the other eleven pairs pooling to **+0.83 bp** — zero to negative
  before borrow. And the gold and BTC-ETF wrapper clusters showed `AC1 −0.436…−0.554`, `VR(5)
  0.20–0.27`, which is the **exact iid-measurement-noise limit** (a constant plus white noise gives
  AC1 −0.50, VR(5) 0.20).

So the close-print arm is print noise and must not be traded. **What survives is a narrower and more
defensible claim, and it is the one M0 already measured the ground for:**

> The *continuous* cross-wrapper spread is enforced to 1–2 bp by every ETF desk on earth — a market
> maker long SPY / short IVV holds a riskless offsetting pair at near-zero capital cost and needs no
> creation unit at all, so the no-arbitrage band is a few bp, not "tens of bp". **But the residue
> that exists only in the auction print cannot be arbitraged by any continuous quote, because it does
> not exist until 16:00:00.** The tradeable object is therefore the *pre-cutoff* (15:45) deviation of
> the continuous spread from its own trailing level, whose resolution the closing cross and the
> following opening cross deliver.

The theory's originality claim is **not crowded at the rail it trades on, and crowded at the
mechanism it invokes** — the thesis must be stated that way. It is genuinely not Petajisto: no NAV,
no iNAV, no holdings file is used anywhere.

### 3.2 Exact instrument and FREE venue

**Venue/endpoint (all Alpaca SIP, free tier, credential already in `.env` — note the §2a quote-stripping
trap):**

| datum | endpoint | verified |
|---|---|---|
| official closing print and opening print | `GET https://data.alpaca.markets/v2/stocks/auctions?symbols=…&feed=sip` | **yes, live, 2026-08-19**, and **with a coverage defect that changes the design — see §3.2a** |
| 15:45 continuous reference price | `GET /v2/stocks/bars?timeframe=1Min&adjustment=raw&feed=sip` | yes — 2016 → present per §2b |
| 15:45 NBBO (for the honest half-spread charge on arm B) | `GET /v2/stocks/quotes` | yes — 2016 → present, ~15-min recency embargo (irrelevant for history) |
| ex-distribution dates (mandatory screen) | `GET /v1/corporate-actions` | yes — universe-wide 2016 → present |
| order acceptance | `type=market,tif=cls` and `tif=opg` both **accepted** on the paper account (§2c) | yes |

**Instrument universe — same-claim groups only.** A pair qualifies only if both wrappers track the
*identical* index. This deliberately excludes VTI/ITOT/SCHB (CRSP vs S&P Total Market vs DJ US
Broad), AGG/BND, EFA/IEFA/VEA and EEM/IEMG/VWO, which are *not* the same claim, and excludes the
**gold and BTC-ETF wrapper clusters outright** because the method lens measured them at the
white-noise limit.

| group | wrappers | independent spreads |
|---|---|---|
| S&P 500 | SPY, IVV, VOO, SPLG | 3 |
| S&P MidCap 400 | MDY, IJH, SPMD | 2 |
| S&P SmallCap 600 | IJR, SPSM, VIOO | 2 |
| Nasdaq-100 | QQQ, QQQM (from 2020-10) | 1 |
| Russell 1000 | IWB, VONE | 1 |
| Russell 2000 | IWM, VTWO | 1 |
| Russell 3000 | IWV, VTHR | 1 |
| S&P 500 Growth | IVW, SPYG, VOOG | 2 |
| S&P 500 Value | IVE, SPYV, VOOV | 2 |

**≈ 15 independent spreads across 9 index factors**, subject to a hard liquidity screen (below) —
**and to the coverage defect measured in §3.2a, which is worse than the liquidity screen.**

### 3.2a The auction-coverage defect — measured today, and it re-orders the arms

I ran the coverage probe rather than assuming the endpoint behaves uniformly. It does not, and the
failure is silent.

**(i) The official-close condition code is NOT stable across the sample.**

| symbol | 2019-06-03 close record | 2026-08-13 close record |
|---|---|---|
| IVV | `('6','P',252.…)` | `('6','P',…)` **and** `('M','P',…)`, same price, same size |
| **VOO** | `('6','P',252.12, 36,973)` | **`('M','P',710.17, 359,971)` — condition `6` absent** |

A harness that filters on condition `6` — which is what "official closing print" means everywhere in
this repo — **silently drops VOO's entire 2026 closing auction** and reads a stray $5 k print instead
of the real $255 M cross. Measured consequence of that one-character bug: VOO's median closing-print
notional reads **$0.005 M** under a `6`-only filter and **$255 M** under a code-agnostic one. On a
*paired* strategy a dropped leg does not go missing, it manufactures a fake several-hundred-bp
dislocation on every affected session, and the rule then trades it at maximum size. This is FINDINGS
§8's rule arriving through the data layer: *verify the diagnostic, not just the system.*
**Extractor must accept the primary-listing exchange's official close under `6` **or** `M`, take the
largest-size record, and assert one and only one survives per symbol-session.**

**(ii) The OPENING print — which arm A's exit depends on — is missing outright in part of the
held-out window.** VOO 2026-08-13 returns `'o': []`. **SPLG returns zero auction records at all for
2026-06-01 → 2026-08-14, having returned them normally in 2019.**

**(iii) Closing- and opening-auction notional, measured 2026-06-01 → 2026-08-14, code-agnostic where
noted (53 sessions):**

| | SPY | IVV | VOO | SPLG | QQQ | QQQM | IWM | VTWO | MDY | IJH | IJR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| median close print, $M | 888 | 408 | 255* | **n/a** | 386 | 16.1 | 142 | 1.79 | 13.6 | 6.91 | 12.9 |
| median open print, $M | 93.3 | 30.1 | 72.4 | **n/a** | 95.5 | 15.8 | 24.3 | 1.15 | 1.70 | 3.83 | 6.72 |

\* code-agnostic. And the thin tail is thinner than the theory assumed: **SPMD 0.54, SPSM 0.68,
VIOO 0.034, VONE 0.039, VTHR 0.021, VOOV 0.072, VOOG 0.60, SPYV 0.73, SPYG 0.97** $M median closing
print. Nine of the twenty-four nominated wrappers clear **less than $1 M** in their own closing
auction — at a 5 %-of-equity leg on a $100 k account that is 0.5 % of the print in the best of them
and it is not a rail, it is a puddle.

**Three consequences, and they are design decisions, not runtime ones.**

1. **Arm B leads, arm A becomes secondary.** Arm A (MOC entry → MOO exit) requires *both* prints in
   *both* legs; the opening print is unavailable for VOO and SPLG in the held-out window, and thin
   everywhere below the top four. Arm B (15:45 continuous entry → close print exit) requires only the
   close, which a code-agnostic extractor gets everywhere the liquidity screen passes. **Arm B is
   also the more direct test of the thesis** — that the cross resolves a pre-cutoff dislocation —
   and it is the arm whose horizon (15 minutes) contains no overnight gap at all.
2. **The universe collapses to what the auction can actually carry: SPY, IVV, VOO, QQQ, QQQM, IWM,
   MDY, IJH, IJR — plus IWB/IVW/IVE at $2–4 M.** That is roughly **4–6 independent spreads**, not
   15. Every power number below must be read against the census, not against the nominal list.
3. **The step-0 census must include a per-symbol, per-YEAR condition-code and coverage audit**, and
   must refuse to run the harness on any symbol-year whose close-print rate is below 98 %.

### 3.3 How to fetch

1. `t26_collect.py` pulls, for 2016-01-04 → 2026-08-14, per symbol: daily auctions (open + close
   price and size), 1-minute raw bars restricted to 15:40–16:00 ET, and the corporate-actions feed.
   Cache to `research/data/t26_cache/` with a sha256 manifest, gitignored, regenerable — the T23
   pattern. **Fetch cost measured, not estimated:** a paged pull of SPY/IVV/VOO/SPLG for
   2018-01→2021-12 returned **2,014,529 minute bars and 1,008 auction sessions per symbol in ~4
   minutes**. Restricting to the 15:40–16:00 window cuts the bar volume ~20×, so the full 10.6-year
   universe pull is **tens of minutes, single-digit GB** — it is not a collection project.
2. **Liquidity screen, point-in-time, trailing only.** A wrapper enters the universe for month *m*
   only if in month *m−1* its median closing-auction notional ≥ **$2 M** and an official print
   existed on ≥ 95 % of sessions. M0 measured print availability at 99.5 % for ADV rank 501–1500 and
   **94.6 %** at 1501–3000 — VONE, VTHR, VIOO, SPSM, VOOG and VOOV sit in or below that band and
   several will be screened out. **This screen decides the effective n and must run before anything
   else.**
3. **Distribution screen.** Auction prints are RAW. A same-claim pair whose two wrappers pay on
   different schedules manufactures fake 100+ bp dislocations (the method lens measured IAU/GLD at
   **582 bp** daily log-ratio sd on raw auction prints vs **3.1 bp** once distribution days are
   removed). Drop any pair-session within ±1 session of either leg's ex-date.

### 3.4 Estimand, observation unit, obs/day

**Observation unit:** one *pair-session*. **Estimand:** the coefficient `β` in

```
r_pair(close_t → open_{t+1})  =  α + β · z_t  +  ε
z_t = [ ln(P_A/P_B)|15:45  −  mean_60(ln(P_A/P_B)|15:45) ] / sd_60(ln(P_A/P_B)|15:45)
```

estimated **unconditionally over every qualifying pair-session**, not as the mean of gated trades.
This is not a preference; it is the Lens-4 rule and the T15 rule (§5j): *count the observations the
ESTIMATOR uses.* A gated mean at a 1.5σ two-sided trigger fires on ~13 % of pair-nights and needs
roughly 8× the calendar.

`z_t` uses only information available at **15:45:00 ET**, five minutes before the 15:50 MOC cutoff,
and the trailing window ends at session `t−1`'s 15:45 observation. **Audit the implementation
against this sentence before the harness runs** — T3 found a nine-minute lookahead worth more than
half its result and T10 found a ten-minute one worth *minus* half of its.

**Realistic obs/day — after §3.2a, not before.** 15 nominal independent spreads; the auction-coverage
and liquidity screens cut it to **4–6**; cross-group flow correlation (the same
allocation-vs-trading-wrapper flow moves S&P, mid, small and the style pairs together) makes it
effective **3–4 pair-sessions/day**. The census measures this rather than asserting it, and the
census runs before a line of harness is written — that is the §5j rule.

### 3.5 Power — explicit

Per-observation sd, rebuilt from M0's own numbers rather than accepted from the proposal:

| component | arm A (close→open) | **arm B (15:45→close)** |
|---|---|---|
| entry noise, 2 legs | close print: 1.61 bp × √2 = **2.3** | 15:45 quote mid: ~0.5 bp × √2 = **0.7** |
| exit noise, 2 legs | open print: M0 §5 median 3.42 bp × √2 = **4.8** | close print: 1.61 bp × √2 = **2.3** |
| true move in the pair spread over the horizon | overnight, ~4.0 | 15 min, ~1.5 |
| **total per pair-session** | **≈ 6.7 bp** | **≈ 2.9 bp** |

Arm B's sd is 2.3× smaller because it carries one print instead of two and fifteen minutes instead of
seventeen hours. **That is the second reason it leads.**

At 3.5 effective obs/day × 252 = **882 independent pair-sessions/yr**.

```
ARM B:  MDE(80%) = 2.80 × 2.9 / √n
  1 yr   (n =   882)  → 0.273 bp
  6 mo   (n =   441)  → 0.387 bp
  3 mo   (n =   221)  → 0.546 bp

ARM A:  MDE(80%) = 2.80 × 6.7 / √n
  1 yr   (n =   882)  → 0.631 bp
  2 yr   (n = 1,764)  → 0.446 bp
```

Inverting for the number that matters — **arm B must clear its ~1.7 bp friction by 2×, i.e. gross
≥ 3.4 bp**, and an effect of 3.4 bp resolves in **under one month of data**. A marginal 2.0 bp gross
resolves in **2.9 months**. Even a 1.0 bp gross resolves in **11.6 months**, i.e. the window can
certify effects far below the level at which the trade is worth doing — which is the property this
programme has lacked five times running.

Arm A needs gross ≥ 1.5 bp against its 0.75 bp friction; at 1.5 bp that is **4.4 months of data**, at
1.0 bp **9.9 months**.

**Months to 80 % = 0 of accrual, for both arms.** The design window 2016-01 → 2021-12 holds ~5,300
pair-sessions and the held-out window 2022-01 → 2026-08 holds ~4,050 — both already on disk.
Engineering: **~2–3 weeks**. Stated the honest other way: *if we had to collect this forward it would
be 1–5 months; we do not.*

The headline effect the theory originally claimed (2.7–6.2 bp) is **not** what I expect. Honest
sizing: the 15:45 continuous spread is MM-enforced to 1–2 bp, so a 1.5σ pre-cutoff dislocation is
2–3 bp, times a reversion coefficient of ~0.7 gives gross **1.7–2.2 bp**, net **1.0–1.5 bp**.
**Pre-register the smaller number.**

### 3.6 Design / held-out split

- **Design:** 2016-01-04 → 2021-12-31. Every parameter choice, every screen threshold, every arm and
  the entire trial count is frozen here and hashed.
- **Held out:** 2022-01-03 → 2026-08-14. Touched **once**, and only if the design gate passes.
- The declared trial budget must be frozen *before step 1 runs*, not after. T3 died on DSR 0.9379 at
  eight declared trials with a genuine +6.07 bp/night gross, and its eight was "certainly an
  undercount".

### 3.7 Honest cost model

Per pair round trip, both legs on the auction rail:

| item | bp | source |
|---|---|---|
| SEC §31, 0.278 bp × 2.00 notional sold | **0.556** | T10's own identically-derived figure |
| FINRA TAF, $0.000166/share | 0.005 (SPY ≈ $650) – 0.05 (SPLG ≈ $70) | fee schedule |
| one night ETB borrow @ IBKR ETB p50 0.33 %/yr | 0.13 | `B22G_BORROW_COST.json` |
| quoted half-spread, both legs | **0.00** | M0: 99.96 % print rate, $37 M median print, tier A |
| **total (auction-to-auction, arm A)** | **≈ 0.70–0.75** | |
| add for arm B (15:45 continuous entry): 2 half-spreads | +0.6–1.0 | §2d: SPY 0.13 bp half-spread; IVV/VOO/SPLG 0.3–0.5 |
| **total (continuous-to-auction, arm B)** | **≈ 1.5–1.7** | |

**Two cost items the theory omitted and which are priced here.**

1. **Scale and benchmark.** At ~10 screened pairs and a 1.5σ two-sided trigger (~13 % of
   pair-nights) the book fires ~1.3 pairs/night; at a 5 %-of-equity-per-leg cap that is 13 % gross,
   **~87 % of the account idle**, and 0.4–0.9 %/yr on equity at 1.5–3 bp net. Against T-bills at
   ~4 % that is the T11 death — *"real spread, below the risk-free forward"*. **The benchmark must
   be by-year T-bills from day one**, exactly as T23 and T25 were forced to do. Hold the collateral
   in SGOV/BIL and run the pair book against it. **Levering with Alpaca margin at 6–8 %/yr is not
   the fix** — the margin rate exceeds the unlevered return.
2. **Capacity.** The universe is too small to deploy the account. That is a *capacity* finding, not a
   validity finding, and it belongs in the pre-registration rather than being discovered afterwards.

### 3.8 Worst-case single trade — explicit

Both legs are the same diversified index portfolio, the horizon cannot be extended, there is no
averaging down, and the size cap is hard.

**Arm B (primary) is the milder of the two and that is a third reason it leads.** Entry 15:45
continuous, exit at the 16:00 cross: **fifteen minutes, no overnight gap, no halt-across-a-gap
path.** Its named worst case is an intraday LULD halt in one leg between 15:45 and the close leaving
the other leg naked into the cross — a broad-index ETF moving 2–5 % in fifteen minutes, so **−200 to
−500 bp on the pair**, at 5 %-of-equity-per-leg **−10 to −25 bp of account equity**. Its second-worst
is the whole-market late-session halt, where *both* legs miss the cross and the position carries
overnight unhedged in neither direction — a wash, not a loss, but it must be a counted observation
class.

**Arm A (secondary) carries the real gap.**

- **Named worst case:** a 2015-08-24-style disorderly open in which one MOO leg fills and the other
  is LULD-halted, leaving a naked broad-index ETF through a −5 % to −10 % gap. That is **−500 to
  −1,000 bp on the pair**, at 5 %-of-equity-per-leg **−25 to −50 bp of account equity**; a
  simultaneous four-pair book **−100 to −200 bp**. A bad week, not ruin.
- **The same tail arriving through the ENTRY, which the theory missed.** A short MOC in an ETF is a
  short sale, and **M0 §10 lists "whether short sales are accepted on-close" as explicitly
  UNMEASURED**. A rejected short leg leaves a naked **long** overnight — identical magnitude.
- **Missed ex-distribution:** ~35 bp, one-directional, non-reverting. Screened in §3.3.
- **The disorderly-open branch must be a counted, reported observation class in the
  pre-registration**, not a footnote, or the win rate gets quoted from the orderly subset only.

Not short-vol. Not martingale. Not fade-every-move-into-an-unbounded-gap. **Tail: survivable.**

### 3.9 Pre-registered SURVIVES / DEAD thresholds

**Blocking prerequisite — do not spend a slice before it is done.** M0's **C4**: does *our* on-close
order join the primary cross? For T3/T7/T10 an unfilled MOC cost a spread. **Here the auction print
gap IS the edge.** If our MOC is internalised at or near the mid instead of joining the cross, the
entire claimed source of relative value evaporates by construction. M0 §10 is a written, bounded,
10-session / 200-order paper protocol that answers it for a fortnight and zero real money. C4 has now
been load-bearing for **six** dead candidates and is the cheapest measurement in the programme.

**Step 0 — census (half a day, no trading, no gate).** Per symbol **per year**: close-print rate under
a code-agnostic extractor, open-print rate, median print notional, and the count of *jointly
available* pair-sessions after the liquidity and distribution screens. Report the **effective**
independent count (block bootstrap by session date, and by index factor). Freeze the trial count.
- **DEAD if** effective pair-sessions in the held-out window < **2,000** (below which arm B's MDE
  exceeds 0.41 bp and the candidate cannot certify a 3.4 bp gross at this programme's measured 4.1×
  design→held-out shrinkage).
- **DEAD if** fewer than **3** index factors survive the screens — one factor is not a cross-section,
  and a single-factor result cannot be separated from that factor's own wrapper idiosyncrasy.

**Step 1 — design window only, 2016-01 → 2021-12, gross, unconditional.**
Report `β`, its bootstrap CI, and the implied **gross mean per fired trade at |z| ≥ 1.5**, for
**arm B (primary: 15:45-continuous → close print)** and arm A (secondary: auction-to-auction)
separately.
- **SURVIVES only if** arm B gross ≥ **3.4 bp/pair-session** (2 × its 1.7 bp all-in friction) *or*
  arm A gross ≥ **1.5 bp** (2 × its 0.75 bp friction).
- **DEAD if** below. Held-out window not spent.
- **DEAD REGARDLESS OF SIGNIFICANCE if** the pre-cutoff arm's gross is < **50 %** of the same rule's
  close-print-deviation arm's gross. That inequality is the print-noise signature; it means we are
  re-measuring M0's auction dislocation, not a mispricing. **This is the discriminating gate and it
  is the reason to run the candidate at all.**
- **DEAD if** the dispersion of the signal-sorted book against a random partition of the same pairs
  exceeds ~1.5× (the §5h rule: report the ratio beside any permutation p, far from 1 means the p is
  not about the mean).

**Step 2 — held out 2022-01 → 2026-08, once.**
- net mean per pair-night **> 0** at **t > 2.80**;
- **DSR ≥ 0.95** at the frozen trial count;
- net gross ≥ **2 ×** measured friction;
- book return **> by-year T-bills + 1.00 pp/yr** (the T23/T25 bar);
- all four required. Any failure = DEAD.

### 3.10 Declared arm 2 (folded in, not funded separately)

The "wrapper the calendar buys" theory (WEAK on its own) shares this candidate's instruments, rail,
data pull, cost model and tail, so its marginal cost inside this harness is ~zero. Fold it in as
**declared arm 2** with four conditions: (i) the payroll settlement lag `L` frozen at a **single**
a-priori value — a 3-value × 3-arm grid is a 9-cell search and DSR at 9+ declared trials is what
killed T3 at 0.9379 and T10 at 0.3772; (ii) the distribution arm's **payment-in-lieu** charged
explicitly (being short the allocation wrapper across its own ex-date owes the distribution in cash,
~35 bp, not a qualified dividend, deductible only as investment interest); (iii) block bootstrap **by
event date** as the primary variance estimator, because on each payroll and month-end date *all*
groups fire on the same shock — the correlation is the hypothesis, not a nuisance; (iv) **the netting
rule declared in writing before any data is pulled** — arm 1 fades whichever wrapper is rich, arm 2
sells the allocation wrapper unconditionally, and on ~100 dates a year they take opposite positions in
the same pair. Both arms count in the DSR budget.

My prior on arm 2 is worse than on arm 1, for a reason the theory argued backwards: a residue is
compensation for **warehousing risk**, and there is none in a flow whose date, sign and approximate
size are published months in advance. Arm 1's residue survives because the imbalance is unknown until
the cross.

---

## 4. PICK 2 — The Settlement-Print Concession

### 4.1 Thesis

Commodity futures settle in fixed clock windows (COMEX metals 13:30 ET, NYMEX energy 14:30 ET). Index
and roll flow that is *mandated* to transact at settlement pays a concession for that certainty. The
claim is that the **ETF wrapper** carries an intraday residue of that concession which is not arbitraged
because it lives in the wrapper, not in the futures calendar spread where Mou (2010) and every
practitioner note look for it.

Two corrections that must be applied before anything is built, because the theory got them wrong:

1. **Drop the flow-score sizing term.** "Levered-ETP net assets from free SEC EDGAR N-PORT,
   computable the night before" is false twice over: N-PORT is filed quarterly with only the third
   month public at a 60–150 day lag, **and** most of this universe (USO, UNG, UCO, SCO, BOIL, KOLD,
   DBC, DBO, GSG, DJP) are commodity pools or ETNs that file 10-K/10-Q and **never file N-PORT at
   all**. Daily shares outstanding exists only as an issuer-site scrape — the D = 2 block that ranked
   shortlist #10 at 10/26. The core fade does not need the term.
2. **The LETF rebalance is immaterial here.** UCO + SCO at ~$700 M combined gives `6 × TNA × r` ≈
   $126 M of WTI on a 3 % day against ~$100 bn of daily WTI volume — **0.1 % of ADV**. The only
   plausibly material size term is index roll flow (GSCI + BCOM tracking, order $200 bn), which is
   free and deterministic from the published methodology PDFs.

**Where the theory's structural argument is wrong and where it is right.** "Nobody supplies liquidity
because they must carry naked commodity risk across the print" is **false for energy and metals** —
Globex does not close during the 13:30/14:30 windows, so the settlement-window liquidity provider
hedges continuously. It is valid only for pit-hours products, i.e. the grains, which are a different
(and separately killed) universe. What is genuinely uncrowded is the **ETF residual**, not the
mechanism; the mechanism is competed for by futures desks via TAS.

### 4.2 Exact instrument and FREE venue

**Venue/endpoint:** Alpaca SIP `GET /v2/stocks/bars?timeframe=1Min&adjustment=raw&feed=sip`, 2016 →
present. **Verified live today**, 2016-03-01 session, bars-per-day:

| USO | UCO | UNG | GLD | SLV | DBC | BNO | DJP | DBO | BOIL | GSG | PDBC | KOLD | CPER |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1000+ | 951 | 902 | 878 | 822 | 628 | 509 | 433 | 423 | 248 | 204 | 117 | 66 | **6** |

**This probe kills half the proposed universe on the spot.** A rule that enters at settlement + 60 s
and exits at 15:55 needs a print in *both* minutes. CPER (6 bars/day), KOLD (66), PDBC (117) and GSG
(204) cannot supply one reliably in 2016, and requiring one introduces a selection that correlates
with volatility. **Screen: a fund-session qualifies only if the name printed ≥ 300 one-minute bars
that session.**

Cross-checking against the measured half-spreads, the executable set collapses further:

| fund | half-spread | round trip + SEC §31 | verdict |
|---|---|---|---|
| GLD | 0.37 bp | 1.02 bp | keep |
| SLV | 0.84 bp | 1.96 bp | keep |
| USO | ~1.5 bp | 3.28 bp | keep |
| DBC | 1.66 bp | 3.60 bp | keep |
| UCO | ~2.0 bp | 4.28 bp | marginal |
| PDBC | 2.78 bp | 5.84 bp | drop (and bar-density fails) |
| DBO | 2.37 bp | 5.02 bp | drop |
| UNG | 4.89 bp | 10.06 bp | **dead on cost at any plausible gross** |
| BOIL / KOLD / DJP / GSG / CPER | 2.4–5.1 bp | 5.1–10.4 bp | drop |

**Executable universe ≈ GLD, SLV, USO, DBC, (UCO) → 3 independent underlyings: gold, silver,
crude.** The distribution is adversely sorted: the cheap names are the most arbitraged and least
likely to carry a concession; the names where the flow should bite (UNG, PDBC, DBO, BOIL) are
cost-dead. **That sorting is itself half the reason my prior is 15 %.**

### 4.3 How to fetch

`t27_collect.py` pulls 1-minute raw bars 09:30–16:00 ET for the screened universe plus SPY and the
underlying-complex proxies, 2016-01-04 → 2026-08-14, into `research/data/t27_cache/` with a sha256
manifest. Settlement clocks come from the CME product pages (free, static) and are frozen in the
pre-registration, **DST-aware** (the §2f correction).

### 4.4 Estimand, observation unit, obs/day

**Observation unit:** one *fund-session*. **Estimand:** the coefficient in a regression of the
**post-settlement** return (settlement + 60 s → 15:55) on the **pre-settlement orthogonalised
residual** (the fund's return across the settlement window, orthogonalised to SPY and to the
underlying-complex return over the same minutes), run across **all** fund-sessions.

**This estimator choice is load-bearing and must be frozen first.** The gated-trade mean needs
**76 months** and fails; the unconditional regression needs 30 and passes. The gate is a trading
decision, not part of the hypothesis test.

**Realistic obs/day:** 4–5 nominal fund-sessions after the screens; **3 effective**, because the
crude complex is one factor, and gold/silver are two more that co-move.

### 4.5 Power — explicit

Claimed per-observation Sharpe 2.5 bp / 45 bp = **0.0556** → `n = (2.80/0.0556)² = 2,536` effective
observations.

```
at 3 effective fund-sessions/day → 845 sessions = 3.4 yr = 40 months OF DATA
design window 2016-01 → 2021-12  = 1,500 sessions × 3 = 4,500 effective  ✅ resolves inside design alone
held out    2022-01 → 2026-08    = 1,160 sessions × 3 = 3,480 effective
MDE(held out) = 2.80 × 45 / √3,480 = 2.14 bp
```

**Months to 80 % = 0 of accrual** (10.6 years exist on the free SIP tier; 4.6 unburned). Engineering:
**one afternoon for step 1, ~1 week for the full harness.**

But read the two numbers together, because this is the whole verdict: **the window can certify a
gross of ~2.1 bp, and the trade needs a gross of ~7.7 bp to be worth 2 × its 3.87 bp friction.** The
candidate is therefore *statistically resolvable and economically improbable* — which is exactly the
cheap kill this programme wants.

### 4.6 Design / held-out split

Design 2016-01-04 → 2021-12-31; held out 2022-01-03 → 2026-08-14, touched once and only on a passed
design gate. Trial count frozen before step 1.

### 4.7 Honest cost model

Mean half-spread across the executable set ≈ **1.10 bp** → **2.20 bp** round trip, plus SEC §31
0.278 bp on the sale = **≈ 2.5 bp** for the tight subset; **3.87 bp** if the wider names are kept
(mean 1.796 bp over 14 funds). No auction rail: this is a continuous-market entry and a
continuous-market exit, so **the spread is charged in full on both legs**, twice. Nothing here gets
M0's zero.

Independent order-of-magnitude read on the gross: **CME publishes TAS markets precisely so
settlement risk transfer can be priced explicitly, and the WTI TAS basis trades 0–2 ticks = 0–2.9 bp.**
That is the market's own quote for the concession this theory wants to harvest, and it sits **at or
below** the ETF round trip.

### 4.8 Worst-case single trade — explicit

Intraday only — **zero overnight gap exposure**, which is the largest tail source in commodity ETPs.
Hard 3× residual stop, no averaging down, unlevered.

- **Worst single trade: −1.0 % of equity** at a 15 %-per-name cap with a 3× stop on a limit-move day.
- **The tail hole in the theory as written, corrected here.** "At most 6 concurrent names" does not
  constrain the *underlying*. USO, UCO, SCO, DBO and BNO are all crude, and DBC/GSG/PDBC are 55–70 %
  energy — six concurrent tickers can legally be a **90 %-of-equity single-barrel crude bet**, and
  UNG + BOIL + KOLD is one natgas bet at 45 % with a 2× and a −2× inside it. **Fix: cap by
  UNDERLYING, not by ticker — max one name per underlying group, max 4 concurrent, 15 % per name.**
  With that fix the honest book worst day is **−3 % of equity**, not the −3 % the theory claimed while
  silently assuming 6 independent factors in a universe that has about 3.
- Not short-vol, not martingale, not fade-every-move-into-an-unbounded-gap.

### 4.9 Pre-registered SURVIVES / DEAD thresholds

**Step 1 — design window only, one afternoon, no gate, no trading.** Measure the **gross** mean
post-settlement reversal per fund-session, per underlying group, unconditionally.
- **SURVIVES only if** gross ≥ **8.0 bp** per fund-session (≈ 2 × the 3.87 bp all-in round trip on
  the full universe, ≈ 3 × on the tight subset).
- **DEAD if** below — **including if it is statistically significant**. That is the T10 friction-floor
  rule: a real effect smaller than its own round trip is a measurement, not a strategy.
- **DEAD if** the effect does not survive orthogonalisation to SPY and the underlying complex, i.e. if
  it is a beta rather than a residual.
- **DEAD if** the sign is not stable across the three underlying groups on the design window — an
  unstable sign is what a search-max looks like (T23's finding).
- Held-out window not spent in either failure.

**Step 2 — held out, once:** net > 0 at t > 2.80; DSR ≥ 0.95 at frozen trials; net ≥ 2 × measured
friction; beats by-year T-bills + 1.00 pp/yr. All four required.

**Expected outcome: DEAD at step 1.** The CME TAS quote of 0–2.9 bp is the honest prior and it sits
below the 8 bp bar. This is worth an afternoon anyway — it kills a family (the whole "ETF wrapper
carries a futures-market concession" class) for the price the T9/T15 rule says a candidate should
cost.

---

## 5. What did NOT survive, and the one conditional third

**Not promoted, and why — recorded so it is not reinvented.**

| candidate | the single sentence that killed it |
|---|---|
| Vol-Time Sawtooth (Deribit calendar) | 32.5 bp of measured 4-leg entry half-spread + ~9.5 bp taker + 12–25 bp of hourly hedging against an 18–40 bp gross; and the entry gate demands a 65 bp signal to trade an 8–25 bp effect, so **as written the rule fires never** — and Deribit serves **no historical bid/ask**, so the backtest cannot price its own execution. |
| Charm Clock | The novelty claim ("charm flow is computed by essentially nobody") is false — SpotGamma, TradeGEX, VannaCharmAlgo and others sell it, *and the theory's own falsification condition appears verbatim in their marketing*; the Cboe feed is 15-min delayed so the trade-signing step is unimplementable; and OCC's series-search returns **zero** open interest against Cboe's 21.9 M, so the mandatory second source does not exist. |
| Gamma Cliff | Deribit direction-tagged trade history exists for **~48 hours** and nothing beyond; the proposed workaround classifies prints against a mid fitted **to those same prints**; and the two-tercile filter selects 11 %, not the 50 % claimed — a 4.5× error in the candidate's own favour. |
| Segregated-Tape Duration Transmission | The premise ("US crypto desks are not yet staffed at 04:00 ET") is false — that is 09:00–14:30 London; and friction is 15–25 bp against a 20–30 bp gross. |
| The Only Live Lira | The premise is factually wrong: offshore interbank USDTRY trades 24/5 in London and New York, so the "only live lira" window does not exist; and the tail (−1,500 to −2,000 bp political jumps) eats 11–125 % of the claimed edge. |
| Creation Unit Bigger Than The Market | The cost model charges one leg twice instead of two legs once; corrected, net is **−4.0 bp** at the rule's own declared threshold, in its own best name. And the mechanism is only measurable in the names where it is predicted absent. |
| Shuttered-Pit Lead-Lag | A predictor whose entire predictable component is ~6 bp is claimed to deliver 15–35 bp gross; and it is a 54–58 % win rate collecting 12 bp against a WEAT-style multi-night limit-locked gap (−45 % compounded), controlled only by an operator's willingness to obey a re-entry ban. |
| Fragmented Roll Calendar | "The concession is a permanent step down in the fund's NAV" is wrong — if the index is computed at the distorted settlement, the fund's NAV is too, so no relative step appears; and the executable universe collapses to one pair. |
| Wrapper-redundancy relative value | Measured, 1,168 round trips: +2.33 bp gross, 92 % of it in two pairs, +0.83 bp across the other eleven against a 0.6–1.2 bp floor. Dies the way ORB died. |
| Exhaustively-enumerated cell miner | Computes its power at a **single-test** critical value (2.80) while pre-declaring a **family-wise** threshold over 972 hypotheses (≈4.64) — a 1.66× inflation of every MDE — and the moat argument and the detectability argument point in opposite directions. |

**The conditional third — NOT a pick.** *Two-timescale voting-premium filter on structurally-linked
share classes* (method lens, WEAK). It is the only killed candidate whose census was actually **run**:
744 design-window round trips, one shared parameter set, **+26.6 bp mean, 61.8 % hit rate, per-trade
Sharpe 0.125, book Sharpe 1.31**, with a real structural anchor (identical cash-flow claims, so the
equilibrium is corporate law, not a fitted regression) and a 16-of-16 AC1/VR signature demonstrably
*not* a Roll artifact. It is not promoted because (i) it is a **published** edge — Schultz & Shive
(2010, *JFE*) does exactly this trade and documents exactly this reversion; Froot–Dabora (1999) and
Lamont–Thaler (2003) are the canonical twins papers — which is failure mode (a) from the 0-for-8
post-mortem; (ii) its `obs_per_day` was overstated **4.2×** and exceeded its own mechanical ceiling;
(iii) it needs 55–61 months against 56 available, a margin that **any** normal design→held-out
shrinkage erases (this programme's measured shrinkage is 4.1× on T10). **Promote it only if Pick 1
dies and the owner wants a fourth swing — and then only as a frozen power census plus one held-out
run, expecting the T3 outcome: real signal, dies on the deflation gate.**

---

## 6. Assets that survive the kills (free, reusable, not strategies)

Per FINDINGS §10's rule that an item which *creates* an asset outranks one that tests a claim:

- **Alpaca `/v2/stocks/auctions` serves official auction prints back to 2016 for ETF wrappers** —
  verified live 2026-08-19 — **but the condition code is not stable and coverage is not uniform, and
  both failures are silent.** VOO's official close carries condition `6` in 2019 and condition `M` in
  2026; a `6`-only filter reads VOO's 2026 median closing print as **$0.005 M** instead of **$255 M**.
  VOO has **no opening print** in the 2026 sample and **SPLG returns zero auction records at all** for
  2026-06→08 while returning them normally in 2019. **Every future auction-rail design in this repo
  must (a) extract the official close code-agnostically (`6` or `M`, largest size, assert exactly one
  survives), and (b) run a per-symbol per-YEAR coverage audit before the harness.** On a paired trade
  a silently dropped leg does not go missing — it manufactures a several-hundred-bp fake dislocation
  that the rule then trades at maximum size.
- **Closing-auction notional for the index-wrapper universe, measured 2026-06→08, 53 sessions:** SPY
  888, IVV 408, VOO 255, QQQ 386, IWM 142, QQQM 16.1, MDY 13.6, IJR 12.9, IJH 6.9, IVW 4.0, IWB 3.6,
  IVE 3.5 ($M median) — and then a cliff: **SPYG 0.97, SPSM 0.68, VOOG 0.60, SPMD 0.54, VTWO 1.79,
  IWV 1.88, VOOV 0.072, VONE 0.039, VIOO 0.034, VTHR 0.021.** Nine of twenty-four nominated wrappers
  clear under $1 M in their own closing auction. Reusable screen for any wrapper-pair design.
- **Minute-bar density is a screen, not a given.** 2016-03-01: CPER 6 bars/day, KOLD 66, PDBC 117,
  GSG 204 — measured. Any intraday commodity-ETP design must screen on bar count or it silently
  selects on volatility.
- **Auction prints are RAW.** IAU/GLD daily log-ratio sd is **582 bp** on raw auction prints and
  **3.1 bp** once distribution days are removed. Every future auction-rail pair design needs the
  corporate-actions screen.
- **The iid-noise signature is diagnostic and cheap.** A constant plus white noise gives
  `AC1 = −0.50, VR(5) = 0.20`. Gold and BTC-ETF wrappers measure −0.44…−0.55 / 0.20–0.27 (noise);
  dual-class pairs measure −0.06…−0.36 / 0.42–0.88 (structure). **Run this before believing any
  measured mean reversion on a print series.** One line of code, and it separated two candidates.
- **Deribit:** near-dated ATM straddle entry half-spread **15.5–17.0 bp of underlying**; the chart
  endpoint serves **trade OHLC only, no bid/ask at any horizon**; direction-tagged trade history
  reaches back **~48 hours** and returns zero beyond. Any Deribit backtest must assume its own
  execution price, which is disqualifying.
- **BTC intraday variance seasonal, 6,000 free Binance hourly bars / 250 days:** hour 15 UTC =
  **2.479×** mean hourly variance, hour 04 UTC = **0.474×**, ratio **5.23×**. This is the US cash
  session and it is the correct clock control for any crypto intraday design.
- **Binance/OKX dual-listed spot basis, 220 coins, live:** p50 **3.7 bp**, p75 8.1, p90 15.7, p95
  21.9, p99 **51.6 bp**. **No cross-venue spot-arb thesis above ~50 bp has a population to trade.**
  Of 109 fully-severed coins exactly one has a live pair on both venues; full severance is the
  *aftermath* of a migration or delisting, not a tradeable outage.
- **Ethereum free RPC:** `ethereum-rpc.publicnode.com` returns **403** on archive `eth_getLogs`
  ("Archive requests require a personal token"); `eth.drpc.org` serves archive logs and archive
  `eth_call`, but **silently truncates** — a 10,000-block span returned 6,988 logs where ~15,600 were
  due. Keep ranges small or swaps are dropped without error.
- **Cboe `cdn.cboe.com` SPY chain** returns 200 / 6.3 MB / 14,160 contracts with per-row iv, delta,
  gamma, theta, vega, but is **15-min delayed with no dated archive** (403 on snapshot URLs), and
  OCC's `series-search` returns **zero** open interest for the same underlying. Worth collecting as a
  **forward panel via detached background cron** (the no-network-crawls-in-agents rule); worthless as
  history.
- **The enumerated-null machinery** from the killed cell miner — a pre-hashed, fully enumerated
  hypothesis space whose family-wise threshold is *computed* by within-day permutation plus a
  stationary block bootstrap rather than *declared* — fixes a named repeated defect (T3 died at
  "declared eight trials" that was certainly an undercount). **Build it as a one-day reusable tool
  every future candidate calls. Do not run it as a candidate.**
- **Instrument fact worth recording:** a US-listed ETF whose US underlying is shut 14:20–16:00 ET has
  a mathematically frozen NAV in that window with no hedge instrument in existence. Correct, and as
  far as anyone here can establish unpublished. It is not a licence to short CANE overnight.

---

## 7. What this document does not claim

- It does not claim either survivor is an edge. Both are **candidates with a resolvable estimand and
  a bounded tail**, and both are expected to die on their own design-window gross gate (Pick 1 ~30 %,
  Pick 2 ~15 %).
- It does not claim breadth. Two survivors, one venue, two instrument classes. The FX, rates, options,
  vol-surface and on-chain lenses produced **zero** survivors between them, and that is the honest
  result of this round.
- It does not claim Pick 1's mechanism is uncrowded. It is crowded *at the mechanism* and uncrowded
  *at the rail*, and the whole candidate stands or falls on that distinction — which is precisely what
  step 1's discriminating gate (§3.9) tests.
- No number here was produced by a search over parameters. The three live probes run for this document
  (auction-print availability and condition codes; auction notional by wrapper; minute-bar density in
  the commodity ETPs) are stated with their dates and are reproducible in one call each. **One of them
  changed the recommendation** — §3.2a moved Pick 1's primary arm from auction-to-auction to
  continuous-to-auction and cut its universe by ~3×. A synthesis that had accepted the endpoint's
  behaviour on the theory's word would have shipped a harness that manufactured its own signal.

- **Recommended order of work, if a slice is granted.** (1) M0's **C4** paper protocol — 10 sessions,
  200 orders, no real money — because Pick 1's edge *is* the auction print gap and C4 has been
  load-bearing for six dead candidates. (2) Pick 1 step 0 census, half a day. (3) Pick 2 step 1, one
  afternoon, expected DEAD, kills a whole family cheaply. (4) Pick 1 step 1. Do not run Pick 1 step 2
  until steps 1–3 have all reported.
