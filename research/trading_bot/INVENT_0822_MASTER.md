# INVENT_0822 — MASTER SYNTHESIS

**Date:** 2026-08-22
**Scope:** 5 fresh themes, **256 formulas**, all pre-registered design-window → untouched held-out.
**Verdict: ZERO PROMOTIONS. ZERO FREEZES RECOMMENDED. BASKET1 UNTOUCHED.**

One candidate (`B01_same_issuer_preferred_RV`) satisfies the *letter* of the three-part test —
gross design clears the pooled bar, held-out net is positive, ρ1 gate passes — and is still
**not promotable**, killed by an absolute borrow wall and an insignificant held-out net.
It is filed as a **characterised object**, not an open question.

---

## 1. THE POOLED BAR

| quantity | value |
|---|---|
| formulas this round (N) | **256** |
| pooled expected-max-under-null, √(2 ln 256) | **t = 3.330** |
| two-sided variant √(2 ln 512) (sign-flip re-tests) | t = 3.532 |
| programme-cumulative (≈1,215 formulas incl. this round) | **t ≈ 3.77** |

Per-theme analytic bars, for reference: tether-scale 2.82 (N=54), forced-flow 2.77 (N=47),
low-turnover 2.96 (N=81), crypto-tether 2.68 (N=36), vol-ETP 2.70 (N=38).

**The analytic bar is a FLOOR, not the operative bar.** The single most important number in the
round is a *measured* null: 300 draws of size-matched, **untethered** cross-category CEF pair-sets,
pushed through the identical formula and identical costs, score a median design gross **t of 4.96
and a maximum of 7.65**. The analytic bar for that family was 2.78. For an overlapping weekly
pair book, √(2 ln N) understates the true null by roughly **2×**. Every design-window t in a
pair-book family must from now on be read against a size-matched tether-free placebo, not against
the closed form. This one script is the difference between "twenty edges" and zero in Family A.

---

## 2. THEME LEDGER

| # | theme | N | best design gross | vs bar | held-out | verdict |
|---|---|---|---|---|---|---|
| 1 | Structurally-anchored cointegrated spreads at scale (pairwise CEF relative premium; same-issuer preferred-series RV; preferred-vs-common) | 54 | **t 7.49 / SR 3.41** (B01) | **CLEARS** | gross 3.08 replicates; net +0.93 (t 1.48) | **Real tether, untradable** |
| 2 | Large-gross forced/mechanical flow (S&P 500/400/600 reconstitution, index migration, IPO lockup, 424B5 takedowns) | 47 | t 3.09 tradable (F37) | fails 3.33 | F37 → t −1.12 | **NOISE** |
| 3 | Low-turnover weekly/monthly signals where the cost wall does not bind | 81 | t 1.82 (0.65× bar) | fails | 8/8 sign run, tiny | **NOISE** |
| 4 | Crypto spot with a structural tether (peg, wrapped/staked, triangular, cross-venue) | 36 | event-level t 2.74 (A6) | fails 3.33 | net +0.49 (t 0.93) | **NOISE** |
| 5 | Vol-ETP complex as a mechanically tethered RV family (daily-reset prospectus identity) | 38 | t 1.07 | fails | 0/38 held-out net positive | **NOISE** |

**Themes that were noise: 4 of 5.** The fifth is not a survivor — it is a *confirmed tether whose
edge is consumed twice over by execution reality*, which is a different and more useful kind of zero.

---

## 3. EVERY CANDIDATE THAT REACHED THE FINAL GATE

### 3.1 `B01_same_issuer_preferred_RV` — clears the bar, NOT PROMOTABLE

**Construction.** Two preferred series of the *same issuer*: spread = log **raw** price ratio,
52-week rolling z, enter |z|≥2, exit |z|≤0.5, 26-week cap. 113 pairs across 38 issuers, weekly,
equal-weight across active pairs. Returns from dividend-adjusted closes so coupon carry sits in the
P&L; levels from raw closes because `adjustment=all` injects a coupon-difference drift into the ratio.

| test | value | pass? |
|---|---|---|
| design gross Sharpe / t | 3.41 / **7.49** | vs pooled 3.33 → **PASS** |
| vs *measured* untethered placebo t | 7.49 vs **2.23** | **PASS** |
| held-out gross Sharpe | **3.08** | replicates |
| ρ1(Δs) median | **−0.245** (p10 −0.398, p90 −0.076); 79.6% of pairs > −0.35 | **PASS** |
| ADF | rejects at 5% for 67.3%, median t −3.35; OU half-life 4.4 wk | pass |
| held-out **net** @ measured 17.5 bp half-spread | +0.93 Sharpe, **t 1.48**, +9.6 bp/wk, bootstrap P(>0)=0.92 | positive, **not significant** |
| held-out net @ 2× spread | **−0.98** | fail |
| **shortability** | **0 of 113 pairs have both legs shortable**; only 28 (25%) have even one | **ABSOLUTE FAIL** |

**Structural tether.** Two preferred series of one issuer are claims of **identical seniority on the
same balance sheet**, differing only in coupon and call date; the price ratio is pinned by the coupon
ratio plus a call-option term. This is confirmed *empirically*, not asserted — a monotone tether
gradient under one identical formula and identical costs:

| population | design gross | held-out gross |
|---|---|---|
| same-issuer, same-seniority | **3.41** | **3.08** |
| cross-issuer PLACEBO | 1.02 | 0.95 |
| preferred vs its own COMMON | 0.55 | 0.14 |

**Diversifying vs BASKET1?** Yes — no shared security, issuer or asset class with T3, ETF-sibling RV,
dual-class RV, T7, T12 CEF or XS_GLSR_Z. Moot in practice.

**Freeze recommendation: DO NOT FREEZE.** Guard, if it were ever revived: it requires a **borrow feed
showing both legs shortable on ≥30 pairs** and a **realised half-spread ≤ 9 bp** (half the measured
17.5 bp), because the trade is symmetric in z — whichever way the spread points, the rich leg must be
shorted, and today it cannot be, in either direction, on any of the 113 pairs.

This is a **legitimate execution-cost-wall casualty, not a sub-bar mirage**: the gross signal cleared
the bar *first*, which is the order EXECUTION_COST_WALL demands. It is the cleanest tether confirmation
the programme has produced and it is still worth nothing.

**Trap caught inside this family.** Cells B04 and B16 (six OU-gated liquid pairs: GS.PRA/GS.PRC,
GS.PRA/GS.PRD, PSA.PRF/PSA.PRG, PSA.PRQ/PSA.PRR, TRTN.PRA/TRTN.PRB, TWO.PRA/TWO.PRC) held out at net
Sharpe **1.86** (t 2.69) and **2.76** (t 1.99) and survived 2× costs. Both die to a matched-size null
(400 draws of size-6 pair-sets): B04's 1.86 is ≈p99 of "pick six tethered pairs at random"
(p95 1.47, p99 1.79) = exactly the expected max of 21 cells; B16's 2.76 sits *below* that null's p90
of 3.54. The OU gate adds nothing beyond the tether. Ten of those twelve legs are unshortable anyway.

### 3.2 Candidates that FAIL the pooled bar — not promoted, recorded so they are not rediscovered

| formula | why it fails |
|---|---|
| `A6_PEG_PREM_ONLY` (crypto) | design gross SR 1.35 (t 2.90) vs a pooled bar of t 3.33; on the correct unit of observation (independent depeg **episodes**, not days) t 2.74 vs its own 2.68 family bar and far under pooled. Held-out net +0.49 (t 0.93). Design net goes to **+0.08 under a $25M/day liquidity floor** — the design edge lives in pairs trading $0.05–0.9M/day where a 10 bp taker fee is fiction. ρ1 passes (−0.07…−0.30). **LOG-ONLY, pile B, alongside XS_GLSR_Z. Not a basket proposal.** |
| `A12_PEG_BAND20_SEASONED` (crypto) | search maximum of its theme (design gross 2.64, t 5.66) and disqualified: on 15 episodes t **2.28**; its entire design advantage over the unfiltered `A2_PEG_BAND20` is that a 250-day seasoning filter mechanically excluded **UST** (~140 days old at collapse) — one binding instance; out of sample the filter **lowers** gross Sharpe (1.53 → 1.17); −0.03 design net under the liquidity floor. |
| `F27_SEC424B5_REB5` (forced flow) | biggest numbers in the round (design −98 bp/event, t −5.86, n=3,336; held-out −150 bp, t −5.48) and it is a **lookahead**. The whole move is on day F+1 (−1.16%, t −7.12) while the filing day is flat (−0.09%, t −0.63): offerings price after the close and EDGAR stamps the event one session before the market can act. Tradable F+1 entry: −0.23%, t −0.80. The 20-day version lives entirely in $2–20M ADV microcaps and is exactly zero in every liquid bucket in both windows. |
| `F37_PROMOTE_REB5` (forced flow) | only tradable formula above the two-sided theme bar (design t +3.09, positive in all six design years and both transition types) → **held-out t −1.12**. Killed *before* the held-out by a mechanism control: passive ownership is ~20% of float for an S&P 500 name vs ~4%/~7% for 400/600, so 400→500 is a mandated net BUY and 600→400 a net SELL; price pressure demands opposite post-R signs and both were positive. |
| `DIV_CUT_DEPTH` (low-turnover) | best genuine design gross t **1.82 = 0.65× its own theme bar**. Positive in 8/8 gross cells, net in 7/8 — worth far less than 2⁻⁸ because the cells heavily overlap. Cost is 24–34% of gross with break-evens 15–74 bp against a 5.5 bp charge: **cost genuinely does not bind, the signal is simply too small.** LOG-ONLY at most. |
| `X_DISAGREE_RANK` (vol) | design gross SR 0.54 vs a circular-shift bootstrap E[max] of 1.08. Held-out net −3.67. |

---

## 4. WHAT THIS ROUND ACTUALLY BOUGHT — the methodology yield

Six results here are worth more than the zero, and three of them are corrections to standing lessons.

**(a) MEASURE THE NULL; the closed form is not conservative.** §1. Size-matched, tether-free,
same-formula, same-cost placebo draws. Analytic 2.78 vs measured median 4.96 / max 7.65.

**(b) DEMAND A TETHER GRADIENT BEFORE READING ANY SHARPE.** Family B's gradient
(3.41 / 1.02 / 0.55, replicated at 3.08 / 0.95 / 0.14) is what a real tether looks like. Family A's
is flat — and worse, **deleting the NAV information entirely (A18, plain price log-ratio on the same
46 pairs) scored BETTER than the premium spread.** *A tether whose defining information can be thrown
away is not a tether.* Make this test mandatory and cheap; it precedes the P&L.

**(c) CORRECTION TO LESSON 2 — the ρ1 gate must run BEFORE the gross bar, not after it.**
Clearing the gross bar is **necessary but not sufficient** for an RV spread. In the crypto theme
**9 of 36 formulas cleared the gross t-bar and every one of them sitting on a ρ1-failing spread had a
break-even under 5.1 bp/side** against a 10 bp fee. A bounce-dominated spread *manufactures* gross
significance: B1_WBTC_LIN30 gross t 5.69 / net −9.02; C1_TRI_TRY_XS gross t 3.48 / net −21.21;
D3_XV_XS net −13.01. **Corollary: ADF strength and low Hurst are actively ANTI-diagnostic.** The
triangular USDC gap has ADF t = −50.8, Hurst 0.264, half-life 0.1 d — and is the single most
untradable series in the round.

**(d) INSIDE A TETHERED FAMILY, HIGH GROSS SHARPE IS EVIDENCE AGAINST THE SPREAD.** Across 19
structurally tethered bond/credit ETF RV pairs on 24 years of daily data at a weekly clock, the rank
correlation between **ρ1(Δs) and design gross Sharpe is −0.837** (Pearson −0.76); on *net* Sharpe it
collapses to −0.30. The highest design gross t in that theme, 5.12 (RV_SHORTGOV_SCHO_VGSH), has
ρ1 = −0.428 and net Sharpe −2.86 design / −6.30 held out. **Every candidate clearing the design gross
bar fails ρ1; every ρ1-passing candidate is far below the bar. No cell exists in either corner.**
This reproduces OU_MEAN_REVERSION's five-pair equity finding on 19 pairs, a different asset class, a
different clock and a 24-year sample, and adds the sign.

**(e) ρ1 MUST BE REQUIRED IN BOTH WINDOWS.** In the vol-ETP family **4 of 6 pairs flip the gate's
verdict between design and held-out** (VXX/VIXY −0.553→−0.044; VXZ/VIXM −0.100→−0.525;
SVXY/VIXY −0.081→−0.491; UVXY/VXX −0.450→−0.031). A single-window ρ1 is not an ex-ante certificate.
Also note the gate has **no middle** in that family: pairs that pass, pass by having ρ1 ≈ −0.08 —
i.e. nothing to harvest.

**(f) NEW WALL, COMPLEMENTARY TO EXECUTION_COST_WALL — the gross return can be an INSTANT, not an
INTERVAL.** A signal can be enormous, replicate on both windows, and be worthless.
`F12_SP600ADD_RUNUP5` goes design t +7.45 → held-out **t +7.87**, and `F15` −6.76 → −3.15; both are
announcement-instant repricings entered before an announcement whose timestamp this data does not
contain. **Standard cheap diagnostic, now mandatory for any event study:** decompose the event window
into single days, find which day carries it, then re-enter one session later. If it does not survive
one session of delay, the event date is a *timestamp*, not a signal.

**(g) MANDATED ≠ IMPACTFUL.** A median S&P 500 addition trades **$4.3bn at 29.7× normal volume** in the
rebalance auction and the abnormal return **on that day is +0.02% (t +0.49)**, held out. Announcement-
close to rebalance-close, held out: S&P 600 adds −0.28% (t −0.83), S&P 500 +0.41% (t +1.55),
S&P 400 −0.35% (t −0.94). 96% of the pre-effective +10.1% S&P 600 move is one announcement-day jump,
so buying a live S&P press-release feed would earn exactly the zero above. The event-clock volume
check *passed emphatically* (median 17.7× relative dollar volume at R vs ~2× on adjacent days) — the
flow is real, enormous, and completely pre-priced.

**(h) THE "GO SLOWER" ESCAPE ROUTE IS CLOSED.** The low-turnover theme confirms the *mechanics* and
refutes the *edge*. At 21–63 day holds the 5 bp half-spread genuinely stops binding: turnover
0.004–0.027 of book/day, break-evens 15–226 bp, cost 6–34% of gross instead of all of it. **Slow
signals do escape the execution-cost wall. There is nothing behind it.** Best design gross t = 1.82.
The published slow tilts were outright negative in this window/universe (BAB design gross SR
−0.55/−0.53, held-out −0.36/−0.38; IVOL_LOW −0.22/−0.25; DIVY_TTM −0.23/−0.25; DIVY×LOWVOL −0.47/−0.50).
The illiquidity/neglect premium — the most attractive idea going in, since it *pays you* to hold what
is expensive to trade — is dead at both $20M+ and $2M+ ADV, in both Amihud and spread-level form
(ILLIQ_AMIHUD wide held-out gross −0.87/−0.70).

**(i) STRUCTURAL LEGITIMACY IS NOT SUFFICIENT — the payoff SHAPE can be untradable.** Two independent
instances:
- **Peg fade = selling a deep-OTM put on the issuer.** The stablecoin peg is the one crypto-spot
  tether that passes ρ1, and it is not a Sharpe object: flat most days, resolving in 15 independent
  stress episodes in 8 years. Re-scored per episode, the natural `A2_PEG_BAND20` earns **−146 bp/episode
  (t −0.50) despite 80% of episodes being winners**, because UST alone is −4,159 bp. Buying the
  discount is −614 bp/episode, worst episode −10,082 bp. Free daily price data cannot price an issuer's
  default probability. (Survivorship integrity: the 15-name universe comes from a listing-window-only
  screen that **admits UST by construction** — it traded at $1.0003 with 0.079%/day vol for 60 days.
  Excluding UST would have flipped A2 from −0.29 to +0.72 design net.)
- **A wide, mechanically legitimate premium can go wider for months.** The Barclays VXX issuance
  suspension (2022-03-14) is a free, mechanical, structurally-anchored dislocation, plainly visible
  (VXX/VIXY residual sd 202 bp/day in 2022 vs 18–48 bp every other year). Fading it over
  2022-03-14…2022-10-31 (n=161) is **negative at every lag**: gross SR −0.62 / −0.18 / −0.17 at lag 0/1/2.

**(j) THE BORROW WALL is an independent wall.** B01 is the first candidate the programme has killed on
shortability alone rather than on significance or spread. Any future RV proposal must state, up front,
what fraction of its pairs have **both legs** shortable. B01's answer was 0%.

---

## 5. THE UNIFYING STRUCTURAL CLAIM

Every dead end in this round has one shape: **free data prices a STATISTIC, but not a CLAIM.**

The two objects the programme owns that actually work (T12 CEF discount, dual-class RV) work because a
**third party publishes the tether's true value** — a NAV, a share-class ratio. OHLCV+DIV publishes
nothing of the kind. Where the round found a genuine published claim (a preferred series' indenture),
the tether was real, monotone and replicated out of sample — and was then taken by the half-spread and
the borrow desk. Where it inferred a tether from prices alone (wBTC/BTC, triangular gaps, vol-ETP
disagreement, cross-venue basis), what it measured was the half-spread bouncing; the vol theme proved
this arithmetically — gross bp per unit of turnover **equals** the round-trip half-spread
(VXX/VIXY 7.66 vs 9.0; UVXY/VXX 7.41 vs 7.0; SVXY/VIXY 6.92 vs 12.3; VXZ/VIXM 8.33 vs 46.0).

This is the same wall as `free-data-convexity-wall`, reached from three new directions in one round.

**The productive question is no longer "which formula?" It is: which cheap feed PUBLISHES A TETHER
VALUE the programme does not yet consume?** Concrete unconsumed candidates, in rough order of
cost-to-value: a **borrow/short-availability feed** (would unblock B01 and re-open the microcap short
tail of the 424B5 family); **intraday timestamps on announcements and EDGAR filings** (would decide
F12/F15/F27, whose gross effects are real and instantaneous); **BDC quarterly NAV** (no free source
wired — confirmed in DEEPMINE_CEFNAV §2); **intraday quotes for the vol ETPs** — though that last is a
rescue attempt on a signal whose honest-lag gross alpha is already exactly zero, which the cost wall
says is a poor prior.

---

## 6. DEAD LEDGER — ADDITIONS (do not re-propose on free data)

From this round, in addition to the standing list (all published equity edges, VRP, all carry-standalone,
box, Orphan Flush, Coiled, the 18 SIZE candidates, the noise-sweep themes, the cost-killed daily reversal
family, crosslist 0/30, ETF-structural 0/51, holdco 0/130, GDX/GDXJ):

- **Index reconstitution (S&P 500/400/600 add/delete), index migration between size indices, IPO lockup
  expiry, secondary-offering / 424B5 pressure.** Reviving any needs intraday announcement/filing
  timestamps or a borrow feed for the microcap tail.
- **Preferred-vs-common RV** — different seniority is not a tether (0.55 design → 0.14 held out), dead
  exactly as predicted a priori.
- **Pairwise CEF relative premium** (same-manager families). Not diversifying anyway — it trades the
  same 353 CEFs as L5.
- **Slow cross-sectional equity tilts; the illiquidity/neglect premium; duration-tethered bond/credit RV
  on a weekly clock; curve-shape RV (2s10s30s, belly-vs-wing, TIPS breakeven — ρ1 ≈ 0 and honest, but
  half-lives of 288–1,678 days with ADF failing to reject); the rebalancing/diversification premium;
  duration-matched term premium; monthly sector rotation.**
- **Triangular / cross-quote no-arb gaps; per-name cross-exchange spot basis; wBTC-vs-BTC;
  wBETH/BETH/BNSOL-vs-underlying; XAUT-vs-PAXG; index-token-vs-basket on free daily data; the DISCOUNT
  side of the stablecoin peg.**
- **The vol-ETP complex as an RV family** (daily-reset prospectus identity). The tether is real
  (R² 0.992 UVXY/VIXY, 0.965 VXX/VIXY) and the alpha is entirely at lag 0: mean design gross Sharpe
  +1.40 at lag0 → **−0.06 at lag1** → −0.31 at lag2. One day of slack destroys 100% of it. The
  dislocation is also decaying — SVXY/VIXY now tracks to 15 bp/day, *below* one round trip.
- **The VXX-suspension fade, as an idea** (§4i).

Recorded so it is not rediscovered as an edge: `SEC_RESID_LTREV` held-out t 2.24 off a design of −0.10
is a coin, not a signal.

---

## 7. DISCIPLINE AUDIT

- **Zero formulas spent on regime conditioners or gates**, in all five themes (lesson 1). The only
  conditioning used anywhere was event *intensity* (F30–F34, the size of the event's own mandated print),
  and it was also noise (design t −0.20 to +0.77).
- **Gross-first ordering** honoured throughout (lesson 2); no cost-fix was attempted on any sub-bar-gross
  signal. Where gross was already zero (vol lag1), charging 0 bp was verified to change no verdict.
- **ρ1 gate** applied; it killed 3 of 4 crypto sub-families *before* any P&L and was right every time,
  and it would have saved the entire vol sweep.
- **Held-out integrity:** picks frozen in writing before the held-out was touched
  (`INVENT_0822_slowturn_FREEZE.md`, `INVENT_0822_forcedflow_SHORTLIST.md`,
  `INVENT_0822_forcedflow_PREREGISTRATION.md` with its recorded amendment for the sign-flip blocks).
  The one instance of held-out mining is *labelled as such and not counted as evidence*: the crypto
  liquid-only held-out read (A6 → +1.27, t 2.40 at the $25M floor) used a restriction chosen after
  seeing the design result, and is logged as a forward observation only.
- **Self-tests passed before results were read** in every theme: planted-edge recovery (slow engine
  SR 13.9, sign flips correctly, ~0 on noise; vol oracle +6.68 and −0.08 when delayed two days, i.e. no
  leakage), an iid-bounce series earning gross −0.21 / net −3.67 in the crypto harness (it does not
  manufacture profit from bounce), Feb-2018 SVXY −86% kept rather than winsorised, and SVIX/UVIX
  **declared unevaluable and excluded from N** rather than silently dropped.
- **Known caveats, stated rather than buried:** corporate-family bar coverage is 65% of the ticker
  universe (alphabetical truncation, uncorrelated with returns; index families are 100% complete); the
  CIK→ticker map is today's SEC file, so bankrupt post-dilution issuers are missing, which biases
  measured post-offering returns *up*, i.e. conservatively against the short; 424B5 mixes equity and
  IG-debt takedowns, which dilutes rather than inflates the measured effect.
- **No git commits, no orders, no money moved. BASKET1 frozen and untouched.**

---

## 8. NEW DATA UNBLOCKED (usable by future rounds)

Four previous rounds recorded "index membership — no point-in-time data". **That is now false.**

- Wikipedia constituent-**change** tables → 2,974 point-in-time S&P 500/400/600 changes (S&P 500 back to
  1976). ⚠ the table **moved in Aug 2026** to "Historical components of the S&P 500"; a scraper on the
  old page silently returns zero.
- SEC EDGAR `form.idx` → 26,881 424B4/424B5 filings. ⚠ the date column is `yyyymmdd` in recent quarters
  and `yyyy-mm-dd` in older ones.
- Alpaca SIP serves **delisted** symbols (WLTW returns bars through its 2022 merger), so index deletions
  are not survivorship-dropped.
- **First-party preferred half-spread**, newly measured: six 2-minute historical NBBO windows across six
  sessions → median **17.5 bp**, p25 6.0, p75 34.3, p90 71.2. Plus raw *and* adjusted daily bars
  2018–2026 for 508 preferred symbols.
- Caches: `research/data/inv0822_flow/` (96 MB, 3,426 symbols), `research/data/inv0822_tether/`,
  `research/data/inv0822_cache/`.

**Reusable tool:** `scripts/trading_bot/inv0822_flow_diag.py` — the event-clock volume-spike check. Run
it before trusting any event date scraped from a wiki.

---

## 9. ARTIFACTS

| theme | markdown | json |
|---|---|---|
| tether scale | `research/trading_bot/INVENT_0822_tether_scale.md` | `INVENT_0822_tether_scale.json`, `INVENT_0822_pairtether_{A,B}.json`, `INVENT_0822_pairtether_{A,B}_null.json` |
| forced flow | `INVENT_0822_forcedflow.md` | `INVENT_0822_forcedflow{,_design,_heldout}.json` + `_PREREGISTRATION.md`, `_SHORTLIST.md` |
| low turnover | `INVENT_0822_lowturnover.md` | `INVENT_0822_lowturnover.json`, `INVENT_0822_slowturn_{XS_DESIGN,XS_HOLDOUT,WIDE,SECTOR,TS}.json`, `INVENT_0822_slowturn_FREEZE.md` |
| crypto tether | `INVENT_0822_crypto_tether.md` (313 lines, all 36 formulas, nothing dropped) | `INVENT_0822_crypto_tether{,_DIAG,_EVENTS,_LIQUIDITY}.json` |
| vol ETP | `INVENT_0822_vol.md` | `INVENT_0822_vol{,_RAW,_STATS}.json` |

Engines: `scripts/trading_bot/invent0822_{pairtether,preftether,null_A,null_B,pref_fetch,pref_fetch2}.py`,
`inv0822_flow_{calendar,bars,engine,run,diag,master}.py`,
`invent0822_slow_{xs,wide,sector,ts}.py`,
`invent0822_tether_{lib,build,sweep,events,liquidity}.py`,
`invent0822_volrv_{panel,sweep,stats}.py`.

---

## 10. RECOMMENDATION

1. **Freeze nothing. Promote nothing. BASKET1 unchanged.**
2. `A6_PEG_PREM_ONLY` → **pile B, forward log line only**, the same status as XS_GLSR_Z: sub-bar,
   capacity-tiny, flat under a liquidity floor in design, and its own tail (a USDT failure) is
   *unmeasured rather than absent*. `DIV_CUT_DEPTH` may take a second log line on the same terms.
3. **Stop adding formulas to any family already swept.** 256 more failed today; the cumulative bar is
   now ≈3.77 and rising with every sweep. Adding formulas to the volatility family alone means clearing
   a bar 229 formulas have already failed.
4. **Adopt as standing pre-conditions, before any P&L is computed** — each earned its place today:
   (a) a size-matched, tether-free **measured** null; (b) a **tether gradient** (real / placebo /
   anti-tether) that is monotone; (c) **ρ1(Δs) > −0.35 in BOTH windows**, run *before* the gross bar;
   (d) for events, the **one-session-delay** re-entry test; (e) for RV, the **both-legs-shortable
   fraction**, stated up front.
5. **The next move is a data acquisition, not a formula sweep.** Rank and cost the four unconsumed
   tether-value feeds in §5 — borrow availability first, since it is the single input that would decide
   an already-confirmed, already-replicated, already-ρ1-passing spread.
