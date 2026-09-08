# T48 — forward-collector DATA-PATH audit, tranche 1: T30 (borrow) + T45 (ETF liquidation)

Date: 2026-09-03 03:00 CEST (CHUNK B tick).  Auditor: `scripts/trading_bot/t48_datapath_audit.py`
(read-only, offline, selftest ALL_PASSED — 3/3 synthetic fault classes caught).
Paper/research only.  No collector was edited, no pin re-cut, no frozen rule touched, no commit.

## Why this tranche is not a formality
Four input-surface faults have been found in live instruments (T33 staleness; newsdesk weekday-name
sort; predmarket `--limit 40` display artifact; newsdesk RSS-provenance mis-attribution) and **none**
was caught by a green decision-path selftest.  T30 reads its gate in ~19 days (2026-09-22).  A
corrupt input there does not produce a wrong number you can see — it produces a *verdict* that looks
mechanical and is actually about our own plumbing.

## Method — the three assertions (agenda T48 acceptance)
(a) RECENCY, (b) REPRESENTATION, (c) ATTRIBUTION, evaluated against the window the **consumer**
actually reads, not against the collector's own success log.

## T30 — IBKR borrow (`research/data/borrow_forward`, consumer = `t30_borrow_evaluate.py --evaluate`)
**CLEAN BILL, one recorded caveat.**

- (a) RECENCY — **PASS.** 10/10 clean days carry a distinct upstream file: 10 distinct `sha256_raw`,
  10 distinct `#BOF` stamps, no day duplicating its predecessor.  This is the load-bearing check:
  `days_clean` is the literal denominator of the frozen 30-day gate and of `both_available_frac`, so
  a repeated upstream file would have inflated the gate *and* biased every pair statistic toward one
  snapshot, invisibly.  It has not happened.
  - CAVEAT (recorded, not a fault): day 1 (label `2026-08-24`) carries content stamped
    `2026.08.23|21:04:48` — a Sunday-evening vintage, whereas days 2-10 are all same-day `~10:26`
    files.  The offset is stored honestly in `manifest.bof_stamp`; it is a vintage offset, not a
    duplicate, and it shifts one of thirty days by ~13 hours.  No action.
- (b) REPRESENTATION — **PASS.** All 103 distinct B01 legs (113 pairs) join the extract; minimum
  presence 8/10 days; zero pairs fail for a join reason; zero duplicate `SYM` rows within any day.
  The 602-symbol universe misses 6-10 rows/day — these are genuine IBKR-side absences that rotate
  day to day (e.g. `AHL PRF`, `CMS PRB`, `KIM PRL`), not a truncation or a sort artifact.
  - WATCH for the 09-22 read: `KIM PRL` 8/10, `BML PRJ` 9/10, `PSA PRI` 9/10.  The frozen rule needs
    both legs available on ≥80% of clean days; a leg absent from the *file* is scored identically to
    a leg that is *not borrowable*.  That is the frozen rule's own missing-data conservatism and must
    not be retuned — but if the verdict lands near the 10-pair threshold, the verdict note must state
    how many pairs failed for absence rather than for cost.  `KIM PRL` sits exactly on the floor.
- (c) ATTRIBUTION — **PASS.** `SYM`→`NAME` is stable across all 10 days for every leg, and the row's
  own `NAME` corroborates the `alpaca.PR* → 'SYM PR*'` mapping from content rather than from the
  query (`JPM PRC`→JPMORGAN CHASE, `MS PRA`→MORGAN STANLEY DEP SHARES SER A, `GAB PRG`→GABELLI
  EQUITY TRUST).  This is precisely the check the newsdesk failed on 09-03.

## T45 — ETF liquidation (`research/data/etf_liquidation_forward`, prereg 6821745b + A1)
**CLEAN BILL, two latent gaps that cannot be fixed without re-cutting a pin.**

- (a) RECENCY — **PASS.** `last_scan` 2026-09-02T21:15Z (same day).  All 11 candidates have
  `file_date` inside the declared 10-day lookback of their own `first_seen`, so EDGAR is honouring
  `dateRange=custom` — it is not silently serving a relevance-ranked all-time list.
- (b) REPRESENTATION — **PASS, empirically.** One-shot probe of all three frozen queries this tick:
  `hits.total.value` == number of hits returned (3/3, 5/5, 7/7), and a deliberately wide 3-month
  probe returned 78/78.  So no truncation is occurring at current volumes.
  - LATENT GAP 1 (cannot fix): `cmd_scan` never compares `hits.total.value` with `len(hits)`, so if a
    window ever exceeds the endpoint's page cap the miss would be silent — the exact newsdesk
    `--limit` fault class.  Measured headroom is ≥78 hits vs a 10-day window that has carried 3-7.
    The collector script is sha-pinned (`T45_PIN.sha256`, verified matching this tick), so adding the
    guard means re-cutting a prereg pin: **owner-gated, not an autonomous act.**  Logged, not done.
  - LATENT GAP 2 (cannot fix, measured): Yahoo v8 returns `close=None` for the **most recent** daily
    bar while `meta.regularMarketPrice` carries the settled close (verified this tick on SPY/XLU/PSA:
    14 non-null closes of 15 bars, null always the latest session).  `yahoo_daily_closes` drops nulls,
    so the entry freeze lags one session.  This is ABSORBED by the frozen design — entry is
    announcement+1 with a +6-calendar-day cap, and the next daily pull fills the bar — but it means
    the price path has a systematic one-session publication lag that nobody had measured, because
    zero tickers have ever been pulled (0 events).  `range=15d` itself works and returns 15 *sessions*
    (~3 calendar weeks) with correct UTC→session-date mapping.
- (c) ATTRIBUTION — **PASS by construction.** Candidate `ciks`/`display_names` are read from each
  hit's own `_source`, never inherited from the query string; the ticker is assigned by an agent
  reading the filing prose and every event carries its source accession.

## T46 standing duty (same tick)
`t45_etf_liquidation_collect status`: chain OK (23 links), 0 candidates `review=pending`, 0 events,
DECIDER = COLLECTING.  All 11 candidates triaged with filing-read reasons (mutual funds, insurance
separate accounts, ETF→ETF share-exchange reorgs, historical SAI boilerplate).  Nothing to promote.
Honest read: 11 hits in 10 days, **zero** cash-liquidating ETFs — K1 (<4 complete events by
2026-09-23 → BLOCKED_ON_DATA) is the live risk for this lane, and it is a *world* rate, not a
process failure.

## Verdict
Two of five collectors audited, both CLEAN on all three criteria.  The data-path thesis is **not**
confirmed here: the faults found so far were in the *reader* instruments (newsdesk, predmarket),
while the *archival* collectors, which were written with manifests and hash chains, hold up.  That
is itself the finding — the fault rate tracks whether a collector records provenance, not whether it
has a selftest.

Remaining for T48: T31 (Deribit), T33 (US options), predmarket puller — one or two per tick.

---

# Tranche 2 — NEWSDESK1 **price path** (2026-09-03 06:00 CEST tick, CHUNK C)

The 09-02/09-03 newsdesk faults (lexicographic merge sort; `feed_ticker` mistaken for attribution)
were both on the **news** path. This tranche audits the **price** path of the same instrument — the
surface that supplies `entry_ref` at freeze and every bar the resolver scores against. NEWSDESK1 was
not on T48's original five-collector list; it should have been, and this is why.

## (a) RECENCY — **FAIL**, and the fault is slot-specific

At 04:02Z Yahoo's own `currentTradingPeriod` for the watchlist reports post-market ending
**09-03T00:00Z** and pre-market starting **09-03T08:00Z**. The 06:00 CEST supervisor tick therefore
lands in a window where **no US session is trading at all**. `prices.py:spot_price` takes the last
bar of a 2-day `equity_path` window, and `equity_path` pins `includePrePost=false`
(`scripts/trading_bot/newsdesk/prices.py:41`) — so the newest bar available is the **09-02 regular
close**, ~8h stale, and no fillable price will exist for another ~4h.

Measured this tick — the value `spot` would freeze vs. the last extended print (09-02T23:59Z), all
18 equity watchlist names:

| | |
|---|---|
| mean \|gap\| | **22.3 bp** |
| max | **86.7 bp** (META) |
| next largest | AMZN +55.7, NVDA +41.9, GOOGL +30.0, NFLX −27.8 |
| **AVGO** | **−82.0 bp** |

AVGO is not incidental: it is the tick's *only* hard catalyst (Q3 after the 09-02 close). The gap is
therefore **signed toward the news** — the defect manufactures the most phantom edge in exactly the
case where the agent has something real to read. On a 1%-risk 2:1 setup, 22–87 bp of unfillable head
start is a material fraction of 1R.

**Slot asymmetry (the actionable part).** This is not a defect of the instrument in general. The
18:00 CEST newsdesk tick lands at 16:00Z, inside the regular session, where the identical code path
is sound. Only the **06:00 CEST** slot is structurally broken, and only for equities — crypto
(CoinGecko, 24/7) is exempt.

## (b) REPRESENTATION — **PASS**
All 18 declared equity symbols returned a live chart result; no symbol silently absent, no truncation.

## (c) ATTRIBUTION — **PASS**
Prices join on the symbol actually requested; `path_for` dispatches on the setup's own
`asset_class`. (The *news*-side `feed_ticker` fault is tranche-1 business and already fixed.)

## Second finding — the same flag biases the **RESOLVER**, in the instrument's favour

`includePrePost=false` sits in `equity_path`, which is also what the resolver consumes. Two
compounding biases follow, and **both flatter the instrument**:

1. **Invisible adverse excursion.** A stop breached at 02:00Z and recovered before 13:30Z is never
   observed; the setup stays open and can still book its target.
2. **Loss truncation at gaps.** `resolve.py:_walk` returns exactly `(-1.0,'stop',stop)` as soon as
   `low<=stop`, however far the bar gapped through. Horizons run 1–240h, so *every* setup is held
   across at least one overnight gap.

**Nothing was changed.** `-1R`-at-stop is the frozen scoring definition and the adverse tie-break is
frozen in §6; §7 makes the scoring path and resolution convention immutable — an improvement is a
NEW instrument, never an edit to this one. A headless tick is the wrong actor to reopen a frozen
scoring rule. Recorded, not fixed, and recorded **in the ledger** (correction record frozen
2026-09-03T04:0xZ) so it travels with the numbers it qualifies.

**Why this strengthens the negative read.** Status shows expectancy −0.474R, edge vs null −0.941R —
`n` far below `N_min=30`, **not a verdict**, and none is licensed before n≥30. But that negative
stands *despite* two favourable-direction biases. Distance from zero beats sample size: an
instrument already negative on charitable accounting is not a near-miss that better fills rescue.
This does **not** fire the kill switch and must not be read as firing it.

## Recommendation (owner/strategist call — not taken autonomously)
Cheapest correct fix is **scheduling, not code**: move the newsdesk chunk off hour 06 (e.g. to 07/19
CEST → 05/17Z, or simply run it only at 18:00 CEST), so every equity freeze happens against a live
session. A code fix to `includePrePost` would touch the frozen resolution path and requires a new
instrument. Until then the 06:00 slot should **abstain on equities by default** and may propose only
crypto.

## Verdict
Three of five(+1) collectors covered. Pattern from tranche 1 holds and hardens: **the faults are all
in the reader instruments, never the archival ones** — and this one was invisible to a green
selftest because the selftest asserts the decision path, not whether the price it decided on was
one anybody could have traded.

Remaining for T48: T31 (Deribit), T33 (US options), predmarket puller.
