# PAY-OR-STOP — OWNER DECISION PACKET

**Written 2026-09-04 12:00 CEST by the durable supervisor (CHUNK A, shell-dead session, file tools only).**
**Task T49. Assembly of the existing record only — no new research, no new candidate, no gate moved.**

> **Read this cold.** It assumes you remember nothing. It exists so that when the T30 read lands
> (~2026-09-22) you receive a decision with a document, instead of a tick doing archaeology under
> time pressure. Every number below is already in the record; this packet adds no measurement.

---

## 0. The decision, in one paragraph

For thirteen months this programme has tested candidate trading edges against a hostile bar
(freeze-then-test, held-out windows, deflated Sharpe, permutation, an explicit friction floor).
**Nothing has come out net-profitable at size.** Two things survived, and neither makes money — a
drawdown reduction on a position you were holding anyway, and a screen that avoids a class of
guaranteed losses. The programme's own diagnosis is that the binding constraint is no longer
signal-finding but **data access**: the strongest surviving object (T30 preferred-series RV) is
unpromotable for one reason only — we cannot see who can be borrowed, and that fact is not on any
free feed. So the fork is: **buy the data that unblocks the one replicated object, or stop.**

**The fork fires at the T30 day-30 read, ~2026-09-22**, if T30 dies. If T30 lives, there is no fork
(see §6 — but read §6 anyway, because "T30 lives" is weaker news than it sounds).

---

## 1. What died, and how — the dead ledger in one screen

All anchors are `research/FINDINGS.md` §5d (the consolidated ledger) unless stated. Each row is a
*frozen-first* test: the gate was written and hashed before the held-out data was touched.

### 1a. Directional edges — 0 for 8

| # | candidate | how it died | anchor |
|---|---|---|---|
| T3 | End-of-day pressure reversal, exit in opening auction | held-out DSR **0.9379** vs a 0.95 threshold frozen first | `T3_RESULT.md`, §5e |
| T7 | Ex-dividend drop-off, close-to-close in the auctions | permutation **p = 0.213**, DSR **0.076**; all 8 design trials negative | `T7_RESULT.md` |
| T9 | Spin-off forced-selling drift | **insufficient power** — MDE 5.51% vs a 2.40% literature effect on 62 held-out events | `T9_RESULT.md` |
| T10 | Overnight-vs-intraday premium | dead **twice, independently** — held-out DSR 0.3772, *and* dead at 0.26× one measured half-spread | `T10_RESULT.md` |
| T11 | Cash-merger arbitrage spread | dead on **all five** frozen gates; killed by a **tail**, not friction — loses at zero cost | `T11_RESULT.md` |
| T15 | PEAD (post-earnings drift) | **insufficient power before testing** — MDE 4.44% vs a ≤0.90% gate, fails by 4.93×; held-out window not spent | `T15_RESULT.md` |
| T23 | Cross-sectional perp funding carry | **insufficient power** — MDE 15.25 pp/yr vs a 2.20 pp claim (6.93×) | `FUNDING_CARRY_VALIDATION.md` |
| T25 | Cross-venue perp funding differential | **both** blocking gates fail; needs 22.5 years of a 3.3-year-old venue — *no split of this data can ever work* | `T25_RESULT.md` |

Two of these deaths are worth reading twice. **T11 loses at zero cost** — the spread is real and
correctly priced, and the payoff is compensation for the payoff's own tail. **T25's signal works and
still loses**: it calls next month's sign 79–84% of the time and is beaten by T-bills.

### 1b. Carry — dead four ways

1. **Funding carry (crypto)** — below the risk-free rate: −0.46 pp vs T-bills, and needs +1.47 pp to
   pay for its tail. §5d.
2. **T23 cross-sectional funding carry** — insufficient power, above.
3. **T25 cross-venue funding differential** — insufficient power, above.
4. **Parity-implied carry (equity options)** — dead 2026-08-27; the free options panel *cannot measure
   borrow*, which is precisely why item (a) on the paid menu exists. `INVENT_2026-08-27_parity`.

### 1c. Risk-shaping — the pivot away from direction, also dead

**T13**: the SMA crash filter is **−9.65 pp of drawdown *worse*** than a de-risked buy-and-hold at
matched volatility. The vol-targeting overlay gets +7.25 pp and +0.66%/yr but **p = 0.233** — it
clears the size threshold and not the significance one. `T13_RESULT.md`, §5d.

This retro-qualifies the one survivor: §5b's crash-filter drawdown claim must be read as *"protects
inside crashes"*, **never** as *"reduces the drawdown you will live through"*. §5i.

### 1d. The free-data convexity wall

Both invention rounds are exhausted. The recorded conclusion: **a sizeable *and* survivable retail
chart edge is not findable on FREE data.** The free-data daily/intraday cross-section sweep category
was formally **CLOSED on 2026-08-24** after three consecutive honest zeros, with a pooled
multiple-testing bar that predicted zero survivors *ex ante*. A round run outside the ticks on
2026-08-27 tested 27 more formulas anyway and returned another honest zero — confirming the closure
was right. This is the single most load-bearing fact behind the fork.

### 1e. Structural (non-predictive) residuals — the surface is fully mapped

Our only real wins were ever *structural*, not predictive. That surface has now been swept to its end:

| residual | verdict |
|---|---|
| Odd-lot tender offers | soft zero |
| Interlisted TSX/NYSE intraday convergence | **dead twice** on a pre-registered measurability probe — true premium ~1 bp, HFT-only; free 1-min bars measure their own error (median ρ₁(dS) −0.478) |
| Non-US closed-end/trust NAV | **not dead — data-blocked.** This is menu item (c). |
| SPX box spread (RTH executable) | **permanently dead** — 2.958% vs T-bill 3.71%, −0.75 pp. No fourth probe. |
| CEF NAV-innovation | dead |
| LETF rebalance / decay harvest | dead (L7); pre-refuted by our own B22E |
| SPAC trust tether | dead 2026-08-25 |
| Preferred call-date par pinning | borrow wall + deterministic-cash-anchor soft zero |

### 1f. Prediction markets — three structural zeros

The discretionary structural hunt on the political book is **CLOSED** (2026-09-04): favorite-longshot
bias, near-certain yield, and cross-market consistency all returned zero **on the wide book** (27,827
selectable markets, after the page-1 truncation fault was fixed). The last excuse — "we only ever saw
2% of the book" — is gone. A mechanical coherence screen survives at its pre-registered 1-of-6
retire counter; it is a $0 background process, not a candidate.

### 1g. Memecoins — structural kills

Closed by construction, not by a failed backtest. The exit-rule family loses **−18.94% per position at
t = −16.2**, and **even trading for free loses 16.89%** — no venue, size, cost or rebate change
reaches it, because the failure is the *shape* of the outcome distribution (§1, §2). Death is a −90%
jump that stops cannot fill; momentum entry is *negative* alpha versus random entry; session noise
(4.01 pp) is larger than every measured edge; and the real toll is 1.14% direct (terminals charge
3.6–4.2%). Independently corroborated externally (Marino et al.: all predictive features "remained
below the economic breakeven curve"). §1–§4.

### 1h. The two survivors, stated honestly

| survivor | what it is | what it is not |
|---|---|---|
| **B20B deadness screen** | classifier; cuts the unexitable rate 35.3% → 13.0%, catches 77.7% of unexitable tokens at 69.7% precision; permutation p = 0.000, held-out with **no shrinkage**, replicated on a different corpus by a different pipeline | **It creates no edge.** It avoids losses, and discards ~18% of tokens that *were* exitable. §3 |
| **Crash-filter drawdown** | −84.9% → −69.5% full sample, 5 of 7 crashes protected, zero harmful, two data sources, two implementations | **Insurance, not alpha.** Its *return* claim is dead (DSR 0.224–0.341; 9 of 10 lengths lose to buy-and-hold), and T13 shows it fails full-path drawdown vs a vol-matched null. §5b, §5d |

**The programme's own summary sentence, in the repo's words: *"there is no currently proven profitable
bot to select"* (`DECISIONS.md:3055`).**

---

## 2. What is still running, what it reads, and when it reads

Nothing below has been peeked at. All are $0 forward collectors on frozen pre-registrations.

| clock | what it collects | state as of 2026-09-04 | reads |
|---|---|---|---|
| **T30 borrow** | daily two-leg borrowability + fee for the 113 preferred-RV pairs | **11/11 clean days**, 0 failed | **day-30 ≈ 2026-09-22 — this is the fork** |
| **T31 Deribit** | daily BTC/ETH option wing quotes | **12/12 clean**, today's row on-clock | ≈ 09-23 (collection gate); design read 12-23 |
| **T33 US options** | daily US wing quotes, 14 underlyings | 7 clean / 8 attempted | day-30 ≈ 10-07 |
| **T45 ETF liquidation** | EDGAR scan for cash-liquidating ETFs | 11 accessions, **0 events** | K1 ≈ 09-23. **K1 is the live risk and it is a *world* rate, not a process failure** — the events simply are not happening |
| **Convexity (T31+T33 joint)** | bought-convexity designs D1/D2/D3 | pins intact | **first reading 2026-12-23**, one extension to 2027-04-22. *Honest prior recorded at freeze: all-dead* (DoltHub design prior — bought strangles lose ~32% of premium per 2 weeks and no trigger flips the sign) |
| **BASKET1 v8** | forward paper logger, imperfect-edge basket | clock **advancing**, freeze untouched since 08-20 | per-leg N_min = 40 ≈ mid-Oct |
| **PREDMARKET1** | agent-vs-crowd calibration | first settlements **09-06** / 09-20 | calibration only; not a money lane |
| **NEWSDESK1** | forward paper event logger | 2/30 resolved; forward clock effectively **restarted 09-02** after a reader fault | needs 30 resolved |
| **Window-2 / T38** | memecoin B20B out-of-sample read | **fully collected and gated**; all stages complete, 0 faults, 318,938 replay obs / 0 mismatches | **BLOCKED — needs your U4 entry.** See §5 |

---

## 3. The fork's trigger, stated exactly

**T30 = same-issuer preferred-series relative value.** It is the strongest object the programme ever
produced: **gross t = 7.49**, an OOS-replicated gradient, **held-out net +0.93**. It is unpromotable
for exactly one reason — **0 of 113 pairs had both legs shortable on the historical proxy**, and that
proxy is the only free instrument that exists. So we started collecting borrowability forward.

> **KILL RULE (frozen):** T30 is **DEAD** if, at the day-30 read, `t30_borrow_evaluate.py --evaluate`
> finds **fewer than 10 of 113 pairs** with **both legs borrowable at a fee below that pair's measured
> gross edge**.

One pre-registered caveat for the read, already logged: **separate the pairs that fail for ABSENCE
from the pairs that fail for COST.** (One pair, KIM PRL, sits exactly on the 80% availability floor.)
Absence is a data problem and is what money buys; cost is a world problem and money does not fix it.

---

## 4. The paid-data menu — three items, frozen since 2026-08-27

These are **the only three purchases with an already-replicated object waiting behind them.** The
menu was deliberately frozen so the fork is one decision against a fixed list, not a fresh survey. It
has not grown, and this packet does not grow it.

---

### (a) Borrow-availability / securities-lending feed

**What it buys.** Direct, historical, per-name two-leg borrowability and fee. This is the *only* item
that decides an existing replicated result rather than opening a new question.

**The specific test it unblocks.** T30 preferred-series RV — immediately and completely. With
historical borrow data the whole 113-pair book can be scored *retrospectively* over years instead of
waiting 30 days for a 30-observation forward panel. It would also retire the "preferred call-date par
pinning" soft zero (§1e), which died on the same wall.

**Why no free substitute exists.** Proven, not assumed: `INVENT_2026-08-27_parity` established that
**the free options panel cannot measure borrow**. Alpaca's `easy_to_borrow` is a live snapshot with
no history, and the hard-to-borrow names are exactly the ones Alpaca will not lend.

**Cost.** **Not priceable from public sources.** The institutional vendors — [S&P Global Securities
Finance](https://www.spglobal.com/market-intelligence/en/solutions/products/securities-finance)
(daily data from 650+ practitioners, 120 custodian banks, 40+ prime brokers) and [FIS Securities
Finance Market Data](https://www.fisglobal.com/products/fis-securities-finance-market-data) — are
quote-only, no published rate card. Expect institutional pricing (four to five figures per year) and
expect a sales process, not a checkout page.

> **⚠ PRE-PURCHASE CHECK — do this before spending a cent, and it may make this item free.**
> [Interactive Brokers' SLB / short-securities availability](https://www.interactivebrokers.com/en/trading/short-securities-availability.php)
> publishes quantity available, number of lenders and indicative borrow rate, updated intraday; and
> [IBorrowDesk](https://www.iborrowdesk.com/) has been archiving IBKR borrow fees and availability
> **with history** for years. If IBorrowDesk's history covers our 113 names over the T30 window at
> usable granularity, **item (a) collapses from a purchase to a download.**
> **This is unverified by us** — it is a lead surfaced while pricing the menu, not a result, and it
> does **not** change the frozen menu. It is one bounded check, and it is the highest-value hour
> available before any money moves.

---

### (b) Bond / credit-ETF NAV tether

**What it buys.** A synchronous NAV reference for bond and credit ETFs — the thing that makes a
price-vs-value gap *measurable* rather than an artifact of asynchronous marks.

**The specific test it unblocks.** The `INVENT_0823` bond/credit-ETF tether family. Note the honest
context: our validated wins have always been **structural (synchronous-mark)**, never predictive, and
this is a structural-mark instrument.

**Cost.** Not priced. Lower expected cost than (a); several vendors carry ETF NAV history.

**Rank: third of three.** It unblocks a family, not a replicated object.

---

### (c) Non-US investment-trust NAV history (UK / CA / AU / JP)

**What it buys.** Historical NAV and discount series for non-US closed-end investment trusts.

**The specific test it unblocks.** A direct geographic extension of the **ALIVE** T12 / L5 / L7
discount-level tilt — i.e. an object that already survived testing in the US, applied to a venue
where it has not been arbitraged as hard. Recorded as **data-blocked, not dead** (§1e).

**Cost.** Not priceable precisely, but this is the **cheapest and most tractable of the three.**
Source landscape: [the AIC](https://www.theaic.co.uk/) publishes per-trust NAV and share-price
performance sourced from Morningstar; [Morningstar Direct Web Services / Equity Data
API](https://equityapi.morningstar.com/) exposes `timeseries_price` with daily frequency and a start
date; and [`mstarpy`](https://github.com/Mael-J/mstarpy) is a free Python package against public
Morningstar data. **The free alternative already costed in the record is a ~2-year RNS
forward-collect** — i.e. a two-year wait, which is what buying this actually purchases.

**Rank: second of three, and the best value if T30 dies.** It is the only menu item that leads to a
*new lane* rather than to resurrecting an old one, and its free substitute costs two years.

---

## 5. Two things on your desk that cost nothing and are blocking real reads

These are not part of the fork, but they are the cheapest actions available and both have been
waiting multiple ticks. **The first of them is worth more than any purchase on the menu.**

1. **U4 — the window-2 unlock.** Window-2 is **fully collected and fully gated**: all stages
   complete, all three gates exit 0 (4,049/4,049 anchored complete, 0 failure-class faults, 318,938
   replay observations with 0 mismatches), quarantine null. `results_unlocked: false`. Nothing has
   been read. The B20B out-of-sample result — the honest test of the programme's single best
   surviving object — is **hours of work and $0**, and it waits on **one attended entry in
   `DECISIONS.md` naming the window and evaluation hashes.** A cron tick must not write it; that is
   the whole point of the gate. **Absent for six consecutive ticks as of 2026-09-04 09:00.**

2. **T50 Step 3 — the tick canary.** Needs an actor with a working shell (see §7).

3. **The rotation itself** — see §7. **This item fired today.**

---

## 6. The STOP option, written as a real option

This section exists because a fork with only one live branch is not a decision. **Stopping is
defensible on the programme's own evidence, and here is its case made properly.**

**The case FOR stopping:**

- **The base rate is brutal and it is ours, not a prior.** Every family that reached a frozen
  held-out test died: 8 directional, carry 4 ways, risk-shaping, the whole structural residual
  surface, three predmarket structural zeros, memecoins by construction. That is not bad luck; the
  programme's own diagnosis is that **the strongest candidates lose *even at zero cost***, which
  means the binding constraint is cost/variance/data-access, and **buying data only moves one of
  those three.**
- **Buying data does not buy an edge — it buys a *test*.** Item (a) does not make T30 profitable; it
  makes T30 *decidable*. The honest prior on the answer is death.
- **The one thing that would most change our knowledge is free** (§5.1) and has not been done.
- **Power, not signal, killed four candidates outright** (T9, T15, T23, T25). Paid data does not add
  years of history to a 3.3-year-old venue. If the next candidate also dies of insufficient power,
  the purchase bought nothing.
- **⚠ The "T30 survives" branch is weaker than it sounds, and this is the most under-appreciated fact
  in the packet.** The forward test that would follow a T30 survival (`PREFRV`, pre-registered blind
  on 2026-08-30, sha `b01b51ba…`) carries an **honest power finding**: at the ≥10-alive-pair floor,
  the book needs **~4,430 book-weeks** to detect the design's net effect at 80% power. The
  pre-registered N_max is **156 weeks → RETIRED unproven.** The recorded expectation is
  **UNDECIDED→RETIRED or DEAD.** So: *T30 surviving on 09-22 does not produce a tradeable strategy;
  it produces a three-year forward test that is most likely to end "unproven".* If you are buying
  item (a) to accelerate that, buy it knowing that is what it accelerates.

**The case AGAINST stopping (i.e. for paying):**

- **T30 is not a search-max.** Gross t = 7.49 with an OOS-replicated gradient and held-out net +0.93
  is a different object from a sweep survivor, and it failed for a *stated, mechanical, purchasable*
  reason rather than for a statistical one.
- **The menu is closed and small.** Three items, each with a replicated object behind it. This is a
  bounded, one-time spend, not an open-ended data budget.
- **Item (c) buys two years.** Its free substitute is a ~2-year forward collect; the purchase price
  is measured against that, and against your own time horizon.
- **You already made this call once.** On **2026-09-01** you chose **pay for data** over building
  more bots (recorded as the pay-or-stop fork), with the qualifier **free-first**. §8 is the adjacent
  record on that.

**A third option, stated so it is not invented under time pressure: STOP-AND-HOLD.** Buy nothing;
let T31/T33/convexity/BASKET1/PREDMARKET run to their frozen dates as $0 background; take the U4
read; and revisit only if one of them surprises. Cost: $0 and no agent time. This is the default that
happens if you do nothing, so it deserves to be named as a choice rather than as drift.

---

## 7. One process item, escalated today

**The agent-side rotation is effectively offline.** Four consecutive supervisor sessions (03:00,
06:00, 09:00, 12:00 on 2026-09-04) could not execute a **single shell command** — output-producing
commands return exit 1 with no output; no-ops report success; a redirect creates an *empty* file. The
06:00 tick pre-committed that two more consecutive shell-dead ticks would make this an owner
escalation in its own right. **That trigger fired at 12:00 today.**

**The scope is session-local, not host-level — the clocks are safe.** The cron shell ran three Python
engines at 12:00:27 in the same minute this session could not run `echo`. All collectors are intact
with **zero missing days**, and no frozen gate denominator is at risk.

**The damage is to the queue, not the data.** Three of four rotation chunks (INVENTION, NEWSDESK,
PREDMARKET) are CLI-only and have been unreachable since 03:00. Writing this packet was the one
prio-1 task reachable with file tools alone — and it is now done, which means **the next shell-dead
tick has nothing left it can usefully do.**

**Earned rule, recorded because it generalises:** *work that must happen on a clock belongs in a
self-guarded pure-Python engine, not in an agent's tick.* Everything that survived this outage was
written as a program; everything that died was written as an instruction to an agent. Concretely, the
PREDMARKET 09-06 settlement is safe regardless, because its harvest is engine-side.

---

## 8. Adjacent record — flagged, deliberately NOT added to the menu

There is a **separate** live pay-or-stop thread on the crypto side that this packet does not merge,
but that you should see before spending, because it bears on the same budget:

**`X2_FLOWSTREAK`** — the 1-of-598 formula that survived pooled multiple testing (cross-sectional
quintile book on 24h Binance taker-flow one-sidedness, top-50 perps, 24h hold; virgin 2025-01→2026-08
**net +2.31 @ 5.5 bp**, breakeven **17.9 bp/side**). Decision rule frozen at commit `1856bb8e`. Its
gating measurement — perp taker slippage — was expected to need paid Tardis L2, and the design-window
PoC came back at **~7 bp/side on FREE Binance bookDepth**, well inside breakeven. **Paid data is the
fallback there, not the plan.** Status: `PENDING_DATA` — needs a held-out depth download, which is
free.

**Why it is here and not on the menu:** the menu is frozen and this is a different universe (perps,
not US equities/ETFs). But it is the one place where "free-first" already paid off, and it is
evidence for §6's point that **the free check should always precede the purchase.**

---

## 9. What happens next, and what each tick is allowed to do

| date | event | who acts |
|---|---|---|
| **any time** | **U4 entry in `DECISIONS.md`** → unblocks T38, the nearest real read | **you, attended** |
| **any time** | the IBorrowDesk pre-purchase check (§4a) | any tick with a working shell |
| 09-06 | PREDMARKET first settlement | engine-side, automatic |
| **09-22** | **T30 day-30 read — THE FORK** | one tick runs the pinned evaluator **once** |
| 09-23 | T31 collection gate; T45 K1 | tick |
| 10-07 | T33 day-30 | tick |
| 12-23 | Convexity D1/D2/D3 first reading (prior: all-dead) | tick |

**Standing constraints, unchanged:** the free-data sweep category is CLOSED; no BASKET1 leg and no
re-freeze (hard rule, after ten re-freezes each of which reset its own forward clock to zero); no new
forward lanes; `t4` untouched; paper only.

---

### Provenance of this document

Assembled 2026-09-04 12:00 CEST from: `research/FINDINGS.md` §1–§5d, §5e, §5i;
`research/trading_bot/STRATEGIST_2026-08-27_1200.md` §2 (the frozen menu);
`research/trading_bot/STRATEGIST_2026-09-04_0900.md` (current clock state);
`scripts/agent_graph/agenda.json` (T30/T33/T38/T39/T45/T47/T48/T49/T50 records);
and the standing memory index. Two bounded vendor-price web lookups were made, as the task's
acceptance permits; both returned **quote-only** for the institutional feeds, and that is reported as
such rather than guessed.

**No number in this packet was measured by this tick.** No gate, pre-registration, pin or
kill-condition was moved. The paid menu's three items are unchanged. No orders, no spend, no wallet,
no broker, no commit.

---

## AMENDMENT A1 — 2026-09-06 12:00 CEST (durable supervisor, CHUNK A)

*Appended, not rewritten. No gate, trigger, pin or kill-condition is moved. The paid menu in §4 is
unchanged and still has exactly three items. This amendment records one new death and its
consequence for how §9 ticks should spend the next 16 days.*

### A1.1 The directional ledger is now 0-for-9, and a third data family is closed

Add to §1a:

| # | candidate | how it died | anchor |
|---|---|---|---|
| T58 | STICKYSHORT — settle-through rate `ΔSI / Σ daily short volume`, long churn / short committed | **dead at the friction floor**: gross +6.00%/yr, CI90 [−1.20%, +13.37%] on 88 usable periods; measured turnover 171%/period costs 4.45%/yr → **net +1.56%/yr against a 3%/yr size floor frozen first (K3)**, and net CI90-lo −5.63%/yr (K2) | `T58_STICKYSHORT_DESIGN_HALF.md`, sha `a74062879b7abe5b` |

Three things about this death are worth the owner's attention:

1. **It is honest in the sign.** K5 did not fire — the effect ran in the pre-registered direction. It
   is not a wrong theory, it is a **true-but-too-small** one eaten by its own turnover. That is the
   same shape as five of the eight rows above it, and it is the programme's characteristic failure
   mode, not an accident.
2. **It is not the published short-interest anomaly.** K4's days-to-cover control returns
   −1.69%/yr, so the normalizer was genuinely uncrowded. Being uncrowded did not save it.
3. **The held-out half was NOT spent.** Per amendment K0 (recorded before either half ran),
   settlement dates 104–207 were left untouched. If the owner ever buys data that changes the cost
   side of this object, a clean held-out window still exists. **It must not be run on free data.**

**Consequence.** §1d recorded the free *price/chart* surface as closed and §1b recorded *carry* as
dead four ways. T58 closes the third and last free family the programme had left: the **regulatory
short-side quantity/flow panel**. Every free data family the programme knows how to reach has now
returned an honest zero. This does not add an item to the paid menu; it removes the last reason to
believe a free substitute is still out there.

### A1.2 What this changes about §9 — and what it deliberately does not

**Unchanged:** the fork's trigger (§3), its date (~09-22), the menu (§4), the STOP option (§6), and
every standing constraint. Nothing here brings the fork forward. The T30 read decides it, on time.

**Changed:** what a tick is *usefully* allowed to do while waiting. Until 09-22, **invention rounds
on free data are suspended** — three closed families and nine dead directional candidates mean the
prior on a tenth free candidate is not merely low, it is a prior the programme has already priced
and paid for four separate times. Ticks that would have invented instead do **instrument-integrity
work** on the live forward instruments: the class of work that produced T52 (a 56-hour input outage
that every green proxy missed) and T60 (a scheduled fake-pass built into a live kill-switch).

The rationale is narrow and should be read narrowly: **the fork's verdict is worth exactly what the
instruments' input integrity is worth.** On 09-22 a single pinned evaluator runs once against a
30-day forward panel and its answer is final. If that panel has a clipped input surface — the defect
already proven live on NEWSDESK (60 of ~374 events, T56) and suspected on the T45 clock (T59) — then
the fork is decided by an artifact. Sixteen days is enough to audit every live instrument's *inputs*
and not nearly enough to find a tenth edge.

### A1.3 Nothing was bought, moved or promised

No order, no spend, no wallet, no broker auth. No BASKET1 leg and no re-freeze. `t4` untouched. No
instrument restarted, re-activated, re-epoched or resolved. Nothing committed or staged.
