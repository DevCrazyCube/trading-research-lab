# XS_GLSR_Z re-verification on a corrected full cross-section

**Question.** Round 3 (INVENT_R3_MASTER.md P4) escalated the incumbent basket leg
`XS_GLSR_Z` (Binance USD-M perp "fade the retail crowd": cross-sectional short of coins
whose global account long/short z-score just spiked most long) because it appeared to
decay out of sample: `+3.00 net (design 2023-01..2024-06) -> +0.30 (2024-06..2025-01) ->
-1.21 (2025-01..2026-08)`. But that terminal window was flagged as a "thin ~20-name
alphabetically-biased A-B-ticker cross-section". This note re-verifies the leg on a
**full** cross-section to decide: is the decay REAL (kill the leg) or an ARTIFACT of the
biased cross-section (keep logging-only)?

Status: **research only.** No orders, no money, no change to the frozen basket spec. The
disposition below is a recommendation to the basket owner, who owns
`BASKET_FORWARD_FROZEN.json`.

---

## 1. The coverage gap is confirmed — and it is worse than "thin"

The GLSR signal is built from `count_long_short_ratio` in the Binance USD-M **daily
metrics** dumps. Those metrics were fetched by `orphanflush_fetch.py`, which crawls
symbols **alphabetically** and (being hardwired to the 2023-01..2024-12 design window)
was never extended. The crawl **stopped mid-alphabet at `BNXUSDT`.**

Evidence (from `research/data/orphanflush_cache/raw/metrics/` and
`panel1h_r3meta.npz`, the exact panel round 3 used):

- Only **60** symbols have *any* 2025 metrics file, and they are exactly the alphabetical
  head `0G…A…B` up to `BNXUSDT`. Every major coin (BTC, ETH, SOL, XRP, DOGE, …) hard-stops
  at **2024-12-31**.
- In the terminal window **2025-01..2026-08**, exactly **28** symbols carry finite GLSR —
  all A-B tickers, ending at BNXUSDT. That is the "cross-section" the -1.21 was computed on.
- The deployed universe screen picks the **top-50 by trailing-7d volume**. In the terminal
  window that top-50 is populated with the real high-volume names (BTC, ETH, …) for
  *price*, but only **~11** of them have finite GLSR — **below the harness's `MIN_NAMES=30`
  floor.** So `weights_from_signal` zeroes the book on almost every bar: measured turnover
  in the terminal window collapses to **0.002/day** (vs ~1.15/day in the design window).

**The -1.21 was not a signal that reversed. It was a portfolio that could not form.** The
book was flat almost every day of 2025-26 because fewer than 30 volume-ranked names had a
GLSR value at all, and the residual Sharpe is noise on the handful of A-B names that leaked
through. This is a data-coverage artifact, full stop.

### Reproduction on the current (truncated) panel

`scripts/trading_bot/glsr_recheck_eval.py` reruns the leg with the exact sweep construction
(`perpmicro_sweep.build_features -> lg_z = zscore(log(glsr),168h)`, cross-sectional quintile,
dollar-neutral, H=24h open-to-open, funding, 5.5 bp/side). Fade sign frozen at -1 on the
design window. It reproduces the escalation:

| window | median live names | median names w/ GLSR | net Sharpe (top-50) | turnover/day |
|---|---|---|---|---|
| design 2023-01..2024-06 | 50 | 50 | **+2.94** | 1.15 |
| hold 2024-06..2025-01 | 50 | 50 | **+0.44** | 1.15 |
| terminal 2025-01..2026-08 | 50 | **11** | **-0.79** | **0.002** |

The `median names w/ GLSR` column *is* the finding: it falls off a cliff (50 -> 11) exactly
when the alphabetical crawl ran out, and the turnover column shows the book stops trading.

---

## 2. Backfill of the missing metrics (DETACHED, per the no-inline-crawl rule)

`scripts/trading_bot/glsr_metrics_backfill.py` downloads the missing daily metrics zips for
all 150 panel-grid symbols across 2023-01..2026-08 from the free no-auth
`data.binance.vision` archive (the same endpoint and throttle the incumbent fetcher uses,
~20 req/s), skipping cached files. It was launched detached:

```
setsid nohup python3 scripts/trading_bot/glsr_metrics_backfill.py \
    > research/data/perpmicro_cache/logs/glsr_backfill.log 2>&1 &
```

- PID **948568**, ~130k uncached jobs, ETA ~**105-110 min** at 20 req/s.
- A chained job (`glsr_recheck_chain.sh`, launched detached) waits for the backfill to
  exit, rebuilds the GLSR panel with `perpmicro_r3_metapanel.py`
  (`panel1h_r3meta.npz`, on the 150-symbol / 33,984-hour grid), then re-runs
  `glsr_recheck_eval.py`.

The 27 grid symbols that are pure-2025 listings (HYPE, FARTCOIN, PENGU, PUMP, PNUT, …) have
no metrics dir yet; the backfill creates them, so the rebuilt panel picks up the real
high-volume 2025 coins that belong in the top-50.

---

## 3. Corrected result on the full cross-section (319-symbol backfill complete)

The alphabetical backfill completed (metrics now reach ZRXUSDT, 319 symbols). Corrected top-50
deployable numbers by window (sign -1, 5.5 bp/side):

| window | median names w/ GLSR | net Sharpe | turnover/day | note |
|---|---|---|---|---|
| design 2023-01..2024-06 | 50/50 | **+2.94** | 1.15 | strong, real |
| hold 2024-06..2025-01   | 50/50 | +0.44 | 1.15 | positive |
| terminal 2025-01..2026-08 | **11/50** | -0.79 | **0.002** | DATA HOLE: signal barely fires |
| full 2023-01..2026-08 | 49/50 | +1.66 | 0.64 | real over the span with data |

**Verdict: the leg is NOT a spurious edge, but it is going UN-OBSERVABLE on free data.**
The terminal-window decay is NOT the strategy failing and NOT (only) an alphabetical-coverage
artifact — after the full backfill, the terminal window still has only 11/50 names carrying a
`count_long_short_ratio` value and turnover collapses to ~0/day. Binance has largely STOPPED
publishing the global-account long/short ratio for most symbols since ~2025, so the signal has
almost no data to act on going forward. Where the data exists (2023->2025-01) the edge is strong
and real (net Sharpe 2.94 -> 0.44, full-span 1.66).

## 4. Disposition (recommendation to the basket owner)

KEEP LOGGING-ONLY (status quo), do NOT size, do NOT remove. Rationale: historically real (so not a
false leg to purge) but increasingly un-observable on free data (so not sizeable). It cannot be
revived without a GLSR data source Binance no longer gives away free. The forward logger will
naturally show ~0 activity for it, which is the honest signature. Revisit only if a free
global-positioning feed reappears. This is a DATA-AVAILABILITY death, distinct from an edge death.

> **[SUPERSEDED 2026-08-23 — see §5.]** The §3–4 "data-availability death" conclusion is
> WRONG and is retained here only for the record. The `count_long_short_ratio` archive was
> NOT withdrawn by Binance; the "11/50 terminal names / 0.002 turnover" was measured on a
> panel built before the metrics backfill had actually landed the 2025–2026 major-coin files.
> The corrected re-run is in §5. Short version: the data-death is overturned, but the leg does
> **not** recover to a sizeable positive net Sharpe either — it decayed to ~breakeven
> out-of-sample. Disposition still KEEP LOGGING-ONLY, but for a different, honest reason.

---

## 5. CORRECTION (2026-08-23) — data-death OVERTURNED, edge DECAYED to breakeven

**Trigger.** `FREE_DATASET_HUNT.md` (Target 3) re-downloaded the raw `data.binance.vision`
metrics zips and found `count_long_short_ratio` **fully populated at 5-min granularity into
2026-08 for every major coin**, contradicting the §3–4 death verdict. This section re-pulls
and re-runs honestly.

### What was actually wrong with §3
The metrics **were already on disk and complete** when I checked. The 2025–2026 major-coin
files (BTC…DOGE, HYPE, FARTCOIN, …) were downloaded during the 2026-08-21 backfill (file
mtimes 18:50–19:57) and the panel `panel1h_r3meta.npz` was rebuilt at 20:26 — *after* they
landed. Direct inspection of the **current** panel:

- BTC/ETH/SOL/XRP/DOGE `glsr` are **100% finite** across the terminal window; FARTCOIN 100%,
  HYPE 75% (its pre-listing months are legitimately absent). **126/150** grid symbols carry
  >50% finite `glsr` in the terminal window; overall terminal `glsr` finite-fraction = **0.84**.
- The eval's deployable screen now shows **median names-with-GLSR = 50/50** in the terminal
  window (not 11/50) and **turnover 1.14/day** (not 0.002).

So the "11/50, turnover→0" figure in §1/§3 was a **stale/premature-panel artifact**: it was
computed before the backfill's major-coin files were folded in. The archive was never gone.
Binance's 2025 files even carry Aug-2026 upload timestamps — it looks re-published/backfilled.

### Corrected re-run — `glsr_recheck_eval.py` on the current full-coverage panel
Same construction (lg_z = zscore(log glsr, 168h), cross-sectional quintile, dollar-neutral,
H=24h open-to-open, funding, fade sign −1 frozen on design). **Top-50 deployable, 5.5 bp/side:**

| window | names w/ GLSR | net Sharpe | gross Sharpe | turnover/day | breakeven bp/side |
|---|---|---|---|---|---|
| design 2023-01..2024-06 | **50/50** | **+2.94** | 4.02 | 1.15 | 20.5 |
| hold 2024-06..2025-01   | **50/50** | **−0.01** | 1.11 | 1.16 | 5.4 |
| terminal 2025-01..2026-08 | **50/50** | **+0.01** | 0.91 | 1.14 | 5.6 |
| full 2023-01..2026-08   | **50/50** | **+1.06** | 2.04 | 1.15 | 11.4 |

(Top-120 upper bound, not deployable: design +3.19 / hold +0.87 / terminal +0.29 / full +1.37.)

### Honest reading
1. **The data-death verdict is dead.** Terminal window: 50/50 names, turnover 1.14/day. The
   book forms and trades normally on free data. §3–4's core premise was false.
2. **But the edge did NOT recover to sizeable-positive.** The terminal net Sharpe is **+0.01**
   — statistically indistinguishable from zero, *not* the −1.21/−0.79 of the broken-book run
   and *not* a deployable positive. The **hold** window is also ~0 (−0.01). Out of sample
   (everything after the 2024-06 design cut) the leg is **~breakeven net of 5.5 bp/side**.
3. **The gross signal edge survives, thinly.** Terminal gross Sharpe +0.91 (positive) with
   breakeven **5.6 bp/side ≈ the 5.5 bp/side assumed cost**. The crowd-fade still points the
   right way gross, but realistic costs eat essentially all of it at top-50. The full-span
   +1.06 net is carried almost entirely by the strong 2023–2024 design period.
4. **Lookahead audit — clean.** Signal `zs(lg,168)` uses only trailing bars ≤ t
   (`roll_mean/roll_std`). `hold_from_weights` lags the weight ≥1 bar
   (`hold[:,H:] = mean(w[:, j-H..j-1])`), and `p.ret[:,t] = open_{t+1}/open_t` is open-to-open,
   so a signal at bar t's close is entered at an open strictly *after* t. The universe screen is
   trailing-7d volume and explicitly refuses to use next-open availability as a filter
   (`perpmicro_sweep.py` L180–182). Entry uses only information through the signal bar.

### Corrected disposition (recommendation to the basket owner — spec unchanged, owner's call)
**KEEP LOGGING-ONLY — but delete the "data death" rationale.** The correct reason is now:
the free GLSR data is fully present and the leg forms a normal book, yet its **out-of-sample
net Sharpe has decayed to ≈0 at deployable top-50 size** (hold −0.01, terminal +0.01); the
gross edge (+0.9 terminal) does not clear a realistic 5.5 bp/side. This is an **edge decay to
breakeven**, not a data-availability death and not a spurious/inverted leg (it never goes
negative net with full data, so nothing to purge). Do **NOT** re-freeze to SIZED on this
evidence. It is a **monitoring candidate**: revisit only if (a) execution cost falls materially
(breakeven ~5.6 bp/side leaves no room at 5.5), or (b) it demonstrably adds orthogonal value
inside a combined book rather than standalone. The forward logger will now show *normal*
activity (turnover ~1.1/day) with ~0 net edge — the honest signature of a decayed, not absent,
leg.

Re-pull note: a fresh idempotent `glsr_metrics_backfill.py` was launched detached (2026-08-23,
PID 1749804) to top up any straggler gaps; it does not change the above — the deployable top-50
terminal cross-section was already fully populated in the current panel.
