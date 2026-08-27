# INVENT_0822 — LARGE-GROSS forced / mechanical flow

**Date:** 2026-08-22 · **Scope:** research only. No orders, no money, no wallet. Free data only.
**Pre-registration:** `INVENT_0822_forcedflow_PREREGISTRATION.md` (frozen before the design pass)
**Design-window shortlist:** `INVENT_0822_forcedflow_SHORTLIST.md` (frozen before the held-out)
**Numbers:** `INVENT_0822_forcedflow.json` · design/held-out passes in
`INVENT_0822_forcedflow_{design,heldout}.json`
**Code:** `scripts/trading_bot/inv0822_flow_{calendar,bars,engine,run,diag,master}.py`

---

## 0. The one-paragraph answer

**The flow is real, it is gigantic, it is mandated, its date is known in advance — and it is
completely pre-priced.** The median S&P 500 addition trades **$4.3 billion at 29.7× normal
volume** in the closing auction of the session before its effective date, and the abnormal
return *on that day* is **+0.02%, t = 0.49**. Out of 47 pre-registered formulas across index
adds, deletes, migrations, IPO lockup expiries and secondary offerings, **not one tradable
formula survived the held-out window.** The two effects that *are* real and *did* replicate out
of sample are both untradable for the same structural reason: they are single-instant
repricings — an S&P announcement jump (96% of a +10% move in one day, nothing left after that
day's close: −0.28%, t −0.83) and a shelf-takedown disclosure that this data timestamps one
session before the market sees it. **Theme verdict: NOISE.** The honest contribution of this
round is not a signal; it is (a) a working point-in-time index-membership-change feed that four
previous rounds recorded as unavailable, and (b) a measurement showing *why* the largest
mandated flow in equities pays nothing.

---

## 1. What this round unblocked

Every prior round hit the same wall, recorded verbatim in `INVENT_R3_event_calendar.md`,
`INVENT_D0821_MASTER.md`, `DEEPMINE_overnight_event.md` and `DEEPMINE_MASTER.md`:
*"index add/delete reconstitution proper — no point-in-time membership data."*
`DEEPMINE_overnight_event`'s `R01_rankpromote` was an admitted **proxy** (names entering a
trailing top-500-ADV screen) and it died correctly, because a liquidity-rank promotion carries
no mandated flow at all.

That wall is gone. Free, and now cached in this repo:

| source | what it gives | volume |
|---|---|---|
| Wikipedia `Historical components of the S&P 500`, `List of S&P 400/600 companies` | effective date, added ticker, removed ticker, reason | **2,974 constituent-change events**; S&P 500 back to 1976, S&P 400 from 2012, S&P 600 from 2019 |
| SEC EDGAR full-index `form.idx` + `company_tickers.json` | `424B4` (IPO final prospectus) and `424B5` (shelf takedown) with filing dates | **26,881 filings** → 2,470 IPO-lockup dates, 16,971 secondary-offering events |
| Alpaca SIP daily bars, `adjustment=all` | prices **including delisted symbols** (verified: `WLTW` serves bars through its 2022-01-07 merger) | 3,427 symbols |

Two implementation notes worth keeping: the S&P 500 change table was **moved off** the
`List of S&P 500 companies` article in August 2026 — it now lives at `Historical components of
the S&P 500`, and a scraper pointed at the old page silently returns zero rows. And EDGAR's
`form.idx` filed-date column is `yyyymmdd` in recent quarters but `yyyy-mm-dd` in older ones.

## 2. The convention check — and the magnitude the theme was built on

S&P changes are effective *before the open* of the effective date, so trackers must execute in
the **closing auction of the previous session**. Call it **R**. If that is right, volume spikes
at R and not at the effective date. It does, overwhelmingly:

| offset from R | R−2 | R−1 | **R** | R+1 | R+2 |
|---|---:|---:|---:|---:|---:|
| median relative $ volume | 1.6× | 2.1× | **17.7×** | 1.9× | 1.6× |

and per family, at R:

| event | n | median rel-volume at R | median $ traded at R |
|---|---:|---:|---:|
| **S&P 500 add** | 191 | **29.7×** | **$4,301 M** |
| S&P 400 add | 472 | 17.8× | $1,073 M |
| S&P 600 add | 460 | 19.6× | $466 M |
| S&P 500 delete | 174 | 15.1× | $1,318 M |
| S&P 400 delete | 429 | 16.5× | $455 M |
| S&P 600 delete | 409 | 14.8× | $82 M |

This is the largest, most mandated, most calendar-known flow available to a retail-data
researcher. The theme's premise — *magnitude matters* — is satisfied by the flow. It is the
**price impact** that turns out not to exist.

## 3. The 47 formulas and the bars

`N = 47` → expected max under the null `sqrt(2 ln 47)` = **2.77** one-sided, `sqrt(2 ln 94)` =
**3.01** two-sided (the relevant one for the sign-flipped re-tests in blocks 2–4, which were
added after seeing block 1 and are recorded as such in the pre-registration amendment). The
pooled cross-round bar carried in from earlier rounds is **3.28**.

Blocks: **1** (F01–F34) the pre-registered index/corporate families plus two magnitude-
conditioned variants; **2** (F35–F38) the migration mechanism with the sign corrected;
**3** (F39–F41) terminal vs live deletes; **4** (F42–F47) the four migration *types* signed by
the passive-ownership differential.

**Zero formulas were spent on regime conditioners** (0/107 survived round 3). The only
conditioning used is event *intensity* — the size of this event's own mandated print, read off
the R close itself.

## 4. Design → held-out: every tradable candidate died

The shortlist was frozen (`INVENT_0822_forcedflow_SHORTLIST.md`) before the held-out ran.

| formula | design t | **held-out t** | verdict |
|---|---:|---:|---|
| `F12_SP600ADD_RUNUP5` | +7.45 | **+7.87** | replicates — **untradable** (§5) |
| `F15_PROMOTE_RUNUP5` | −6.76 | −3.15 | replicates — untradable, same reason |
| `F27_SEC424B5_REB5` | −5.86 | **−5.48** | replicates — **lookahead** (§6) |
| `F28_SEC424B5_REB20` | −4.35 | −5.41 | same |
| **`F37_PROMOTE_REB5`** | **+3.09** | **−1.12** | **DEAD** — the one tradable design leader |
| `F20_ALLADD_LAST1` | −2.71 | −1.45 | dead |
| `F42_MIG_400to500_R5` | −2.62 | −0.06 | dead |
| `F44_MIG_600to400_R5` | +2.39 | −0.99 | dead (sign flipped) |
| `F35_MIGPAIR_REB5` | +2.04 | −0.66 | dead |
| `F16_PROMOTE_REV20` | −2.01 | −0.53 | dead |
| `F24_LOCKUP_PRE` | +1.90 | +0.87 | dead (and never above the bar) |

`F37` deserves a note because it was the best tradable result and it looked robust: **positive
in all six design years** (+0.61%, +0.82%, +0.77%, +2.98%, +2.61%, +0.88%) and positive in both
transition types. It still died. What saved this round from promoting it was not the held-out
but **block 4, run before the held-out**: F37 pools `400→500` (which buys ~20% of float and
sells ~4% — a huge mandated NET BUY) with `600→400` (buys ~4%, sells ~7% — a modest NET SELL).
Temporary price pressure requires these to carry *opposite* post-R signs. Both were positive.
The shortlist recorded, in advance, that *"whatever F37 measures, it is not the reversal of a
mandated flow"*. The held-out then agreed.

## 5. Why the index effect pays nothing: it is one announcement instant

Decomposing the pre-effective move for S&P 600 additions (design window):

| day | R−5 | R−4 | R−3 | R−2 | R−1 | **R** |
|---|---:|---:|---:|---:|---:|---:|
| mean hedged return | +0.62% | +1.73% | +2.02% | +4.11% | +2.96% | **−1.34%** |

The total R−5→R move is **+10.1%**, and **96% of it is the single largest day** — the
announcement. Then, out of sample:

| held-out 2022–2026 | n | R−5→R | **announcement close → R** | **on the R flow day** | R→R+5 |
|---|---:|---:|---:|---:|---:|
| S&P 600 add | 359 | +2.26% (t +6.31) | **−0.28% (t −0.83)** | −0.24% (t −1.81) | −0.20% (t −0.20) |
| S&P 400 add | 196 | +0.70% (t +1.87) | −0.35% (t −0.94) | −0.48% (t −2.69) | −1.32% (t −1.79) |
| S&P 500 add | 73 | +2.64% (t +2.77) | +0.41% (t +1.55) | **+0.02% (t +0.49)** | −0.17% (t −0.27) |
| S&P 600 delete | 270 | −2.49% (t −3.47) | −0.79% (t −2.14) | −0.44% (t −2.01) | +2.21% (t +1.48) |

**Read the middle two columns.** Once the announcement day's close has passed, the return to
the rebalance is zero. And *on the day the $4.3bn actually trades*, the price moves +0.02%.
The arbitrage community absorbs the entire mandated print at no concession. Buying a real-time
S&P press-release feed would not help: the row above is exactly what such a feed would earn.

This also settles the `ANN` flag honestly. `F12`'s spectacular t-stats (+7.45 design, +7.87
held-out) are a **measurement of the announcement jump**, not a signal. You cannot enter before
an announcement whose date you do not know, and there is nothing after it.

## 6. Why the one confirmed corporate signal is a lookahead

`F27` (short after a `424B5` shelf takedown) cleared every bar on both windows: design −98 bp
per event at t −5.86 across 3,336 events, held-out −150 bp at t −5.48 across 2,728, portfolio
Sharpe ≈ +1.5 for the short book. Then the timing control:

| held-out 2022–2026, `424B5` | n | mean | t |
|---|---:|---:|---:|
| entry at the **filing-day close** F, hold 5 | 2,729 | −1.41% | **−6.68** |
| entry at the **F+1 close**, hold 5 | 2,747 | −0.23% | **−0.80** |
| placebo, dates shifted +60 sessions | 2,529 | −0.31% | −1.46 |

and the per-day profile shows why:

| day | F−1 | **F** (filing day) | **F+1** | F+2 | F+3 |
|---|---:|---:|---:|---:|---:|
| all names | −0.78% (t −3.19) | **−0.09% (t −0.63)** | **−1.16% (t −7.12)** | −0.00% | +0.04% |
| >$20M ADV | −0.32% (t −0.81) | −0.18% (t −1.16) | −0.64% (t −4.33) | +0.09% | +0.04% |

**The filing day itself is flat and the entire move is the next session.** An offering prices
after the close and the market marks it down at the following open — so EDGAR's filed-date
stamps the event one session before the market can act on it, and *entering at the F close is
entering before the information is public*. Move the entry to the first unambiguously-public
close and the signal evaporates: −0.23% at t −0.80, and **+0.06% at t +0.31 in names above
$20M ADV**.

One thread was chased to the end rather than left dangling. The 20-day version entered at the
F+1 close is held-out significant (−1.70%, t −3.85). It is still not promotable, for two
independent reasons:

| 424B5, tradable F+1 entry, 20-day hold | design | held-out |
|---|---:|---:|
| all > $2M ADV | −0.50% (t −1.96) | −1.70% (t −3.85) |
| **> $20M ADV** | **+0.09% (t −0.24)** | **−0.45% (t −0.62)** |
| > $100M ADV | +0.60% (t +0.66) | −0.64% (t −0.30) |
| micro $2–20M ADV | −1.28% (t −2.04) | −3.64% (t −4.22) |

It **failed design** (t −1.96, below the 3.01 two-sided bar and far below the pooled 3.28), so
the held-out number is selection on the held-out. And it lives **entirely in $2–20M ADV
microcaps**, vanishing in every liquid bucket in both windows. That is a microcap short, where
borrow availability and borrow cost bind and where neither quantity is in this dataset.

## 7. What this round adds to the standing lessons

* **A new failure mode, distinct from the execution-cost wall.** `EXECUTION_COST_WALL.md`
  established that the wall is a *significance* wall — a sub-bar gross signal is not rescued by
  a cheaper rail. This theme adds the complement: **a signal can be enormous, significant on
  both windows, and still worthless because its gross return is an instant, not an interval.**
  `F12` (t +7.87 out of sample) and `F27` (t −5.48 out of sample) are both this. The diagnostic
  that separates them from tradable alpha is cheap and should be standard: **decompose the event
  window into single days and ask which day carries it; then re-enter one session later.** If
  the effect does not survive the one-session delay, the event date is a timestamp, not a signal.
* **Mandated ≠ impactful.** The theme's premise was that flow this large must move price. It
  does — but only against people who have to trade, and it is fully absorbed by the time the
  print happens. 17–30× normal volume produced +0.02% on the S&P 500 add day.
* **Forced-flow reversal is now a closed book on free data**, alongside the already-dead
  merger-arb, spinoff, crosslist (0/30), ETF-structural (0/51), holdco (0/130) and GDX/GDXJ
  tethers. Do not re-propose index reconstitution, index migration, IPO lockup expiry or
  secondary-offering pressure without a data source this round did not have (intraday
  timestamps on the announcement, or a borrow feed for the microcap tail).
* **The mechanism arithmetic is worth keeping** even though it did not pay: passive ownership is
  ~20% of float for an S&P 500 name against ~4% (S&P 400) and ~7% (S&P 600), so a `400→500`
  promotion is a mandated net *buy* and a `600→400` promotion a mandated net *sell*. Any future
  work that pools "promotions" is pooling two opposite signs.

## 8. Reusable artifacts

* `research/data/inv0822_flow/raw/index_changes.json` — 2,974 point-in-time S&P 500/400/600
  constituent changes with effective date, side and reason.
* `research/data/inv0822_flow/raw/edgar_424.json` — 26,881 `424B4`/`424B5` filings with ticker.
* `research/data/inv0822_flow/bars/*.npz` — 3,427 symbols of daily adjusted OHLCV including
  delisted names.
* `scripts/trading_bot/inv0822_flow_diag.py` — the event-clock volume-spike check; run it before
  trusting any event date scraped from a wiki.
