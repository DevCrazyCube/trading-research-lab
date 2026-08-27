# T3 re-run — the honest number under realistic execution

## VERDICT: **ALIVE for a small, live forward test.** Not a DSR-certified edge; a positive,
executable candidate whose one remaining unknown is a live question, not a backtest question.

The original T3 was killed on **one** of three pre-registered gates — Deflated Sharpe 0.9379 vs a
frozen 0.95 — while passing the other two (net > 0 at t = +2.73; label-permutation p = 0.0001). The
second stated reason for shelving it, *"the free auction rail is unreachable,"* was about a **different
variant** (D2, both legs MOC), never about the frozen rule. Two things measured since — that near-close
market orders fill on Alpaca (T4/T20), and that the closing/opening auction economics are as assumed
for the top-500 universe (M0) — remove that second reason entirely. Under realistic retail execution
the net point estimate is **+5.04 bp/night, t = +2.57, out-of-sample Sharpe 1.21**, positive in **≈99.5%
of a night-level bootstrap**. It still does **not** clear DSR 0.95 (it comes in at 0.917). Framed as
the owner asked — *is this a positive, executable, forward-test candidate?* — the answer is **yes**.

This document is read-only research. No order was submitted, no data purchased, no commit made.

---

## 1. Reproduced the original number (sanity check: can we rebuild it?)

Recomputed **fully offline** from the cached panel (`research/data/t3_cache/panel.json.gz`, 1,139
held-out nights) and the frozen config (`window=10, cut=0.10, top_n=500`), reimplementing the portfolio
math without touching the network. Matches the frozen result **to the digit**:

| series | this re-run | `T3_HELDOUT_RESULT.json` |
|---|---|---|
| net @ h = 1.4267 bp, exit 0, borrow 30 bp/yr | **+5.351713 bp, t = +2.732041** | +5.351713 bp, t = +2.732041 |
| gross (zero cost) | +6.839168 bp, t = +3.491461 | +6.839168 bp, t = +3.491461 |

The `+5.35 bp / t = +2.73` figure is reproduced exactly. Everything below is built on the same panel.

---

## 2. What "realistic retail execution" actually is for this rule — and why the kill's second reason doesn't apply

The frozen rule's execution is **already** the realistic one, and this was obscured in the original
write-up by lumping it with the D2 diagnostic:

- **Entry — taker market order at 15:59:5x.** The rule enters at the last-minute price and is charged
  one measured quoted half-spread (h = 1.43 bp) for crossing to the touch. T20/T4 established that
  near-close **market** orders do fill on a retail broker, so this leg is executable as modelled. It is
  **not** a closing-auction (MOC) order and never needed the 15:50 cutoff.
- **Exit — MOO at the next opening print.** Charged **zero spread** because a single-price call auction
  has no bid-ask to cross. M0 measured this directly for the traded universe:
  - official **opening** print exists on **99.96%** of top-500 symbol-days;
  - median opening auction **$4.8 M**, so a retail-sized order is not the auction;
  - the rule marks the leg **at the official print** (`po`), so M0's finding that the print ≠ the
    midpoint is *not a cost here* — it is inside the return series on both sides (M0 §3c, §7);
  - `opg` orders are accepted after 19:00 ET the prior evening or before 09:28 — **operationally
    feasible** (M0 §6.2).

The *"auction rail unreachable, t = 1.38"* result was the **D2** variant that tried to put **both** legs
on the free MOC/MOO rail and therefore had to commit before 15:50 — nine minutes before the signal
exists. The frozen rule pays the entry spread precisely so it doesn't need that. **M0's own conclusion:
T3's 4th stress rung (a full half-spread charged on the auction leg as insurance) was *over*-conservative
— the cost model was not what was wrong.**

The one honest addition realistic execution demands is **regulatory fees** (SEC 31 + FINRA TAF),
~0.31 bp/night on the ~100% of notional sold over a round trip. (`costs.py` folds these into its
half-spread round-up; T3 uses the raw measured 1.43 bp, so I add them explicitly rather than assume
them away.) The M0 non-fill provision for top-500 is 0.000–0.002 bp — rounds away.

---

## 3. The realistic-execution net number

Entry = measured quoted half-spread (1.43 bp) · exit = 0 (MOO, M0-confirmed) · fees 0.31 bp ·
borrow 30 bp/yr GC on the short leg:

| | mean bp/night | t | OOS Sharpe (ann.) | DSR (8 trials) |
|---|---|---|---|---|
| **realistic net** | **+5.04** | **+2.57** | **1.21** | **0.917** |
| realistic net, fees inside the round-up (costs.py convention) | +5.35 | +2.73 | 1.29 | 0.938 |

**Night-level bootstrap** (20,000 resamples of the 1,139 nightly returns):

- mean **+5.04 bp**, 95% CI **[+1.27, +8.94] bp**, 90% CI [+1.84, +8.28] bp;
- **P(mean ≤ 0) = 0.46%** — the point estimate is positive in ~99.5% of resamples.
- Cross-sectional label permutation (from the frozen run, unchanged): **p = 0.0001**. The signal's
  reality is not in question, and D1 already showed it is not a bid-ask-bounce artifact (bounce-free
  entry still +6.07 bp, t = +3.10).

**Plainly: yes, the net-of-realistic-cost point estimate is still positive, and we are fairly sure of
it** — bootstrap and permutation both put the chance the *mean is actually ≤ 0* at well under 1%.

### The honest negative, stated with equal weight
- **DSR = 0.917 < 0.95.** Under realistic costs it fails the strict Deflated-Sharpe gate by *more* than
  the original (0.938), because the fee shaves the observed Sharpe against the same 8-trial chance
  ceiling and 12.3 kurtosis. This candidate **does not clear DSR 0.95** and this re-run does not pretend
  it does. DSR is a *certainty* threshold built from the 8 configurations we admitted trying; it is not
  a test of whether the mean is positive, and the owner's instruction is explicitly to judge the latter.
- **C4 is unmeasured.** Whether *our* `opg`/taker order actually fills *at the print* is the half of M0
  a tape cannot answer (M0 §10). This is the real forward-test question — and it is a live-order
  question, not a backtest one.
- **2026 YTD is flat** (−0.93 bp, t = −0.11, n = 154), as in the original. Four of five years positive,
  no collapse, but worth watching for decay in a forward test.

---

## 4. Robustness — where the edge lives, honestly

**Execution-cost ladder** (entry cost varied; exit 0, fees 0.31, borrow 30):

| entry assumption | mean bp | t | ann. Sharpe |
|---|---|---|---|
| h = 1.43 bp (measured quoted) | +5.04 | +2.57 | 1.21 |
| 1.5 h | +4.33 | +2.21 | 1.04 |
| **2.5 bp (Dyhrberg effective half-spread, post price-improvement)** | **+3.97** | **+2.03** | 0.95 |
| 2 h (impact insurance) | +3.61 | +1.85 | 0.87 |
| 4 h | +0.76 | +0.39 | 0.18 |

The edge survives the *published academic* retail effective-spread (2.5 bp, which already nets ~44%
price improvement) at t = +2.03, and survives doubling the quoted spread at t = +1.85. It only dies at
4× — the same friction floor the original flagged. Nothing here needs a flattering cost assumption to
stay positive.

**Liquid sub-universe** (realistic cost) — a genuinely cleaner variant:

| universe | mean bp | t | ann. Sharpe | kurtosis | DSR-8 |
|---|---|---|---|---|---|
| top 500 | +5.04 | +2.57 | 1.21 | 12.3 | 0.917 |
| **top 300** | **+5.72** | **+2.64** | 1.24 | 9.4 | 0.925 |
| top 200 | +6.18 | +2.61 | 1.23 | 8.0 | 0.921 |

Concentrating into the more liquid names **keeps all the edge and mildens the tail** (kurtosis 12.3 →
8.0), which matters more for a fat-tailed nightly book than the small Sharpe differences. This is the
recommended forward-test vehicle. (Wider decile cut = 0.20 also stays positive: +3.16 bp, t = +2.35.)

---

## 5. Call and recommended sizing

**ALIVE for a small live forward test.** The net-of-realistic-cost point estimate is **+5.0 bp/night,
t = +2.6, Sharpe ≈ 1.2**, positive with ~99.5% bootstrap confidence and permutation p = 0.0001; the
execution rails it depends on are now measured-feasible (T4/T20 for the taker entry, M0 for the MOO
exit); and it survives conservative cost stress. It belongs in the **forward-test candidate pile, not
the genuinely-dead pile** — the genuinely-dead pile is for edges whose net goes to zero or negative
under honest costs (carry, the 0-for-8 directional set), and this one plainly does not.

It is **not** a DSR-certified edge (0.917 < 0.95) and should not be described as one. The DSR miss is a
statement about certainty given 8 trials, not about the sign of the mean; the owner's brief is precisely
to not kill a positive-but-imperfect edge on that gate alone.

**Recommended forward test, if authorised (owner gate — not taken here):**
- **Vehicle:** top-300 sub-universe, 10-min signal, decile cut, dollar-neutral. Milder tail, same edge.
- **Purpose:** measure **C4** — do our taker-entry and `opg`-exit orders fill at/near the modelled
  prices? That is the only load-bearing unmeasured input, and it is exactly M0 §10's protocol.
- **Size: tiny — this is a measurement, not a money-maker.** M0's capacity ceiling for a T3-shaped book
  is ~$3.2 M at 1% participation of the thinnest top-500 opening auctions (~$16 M at 5%); a forward test
  should run **1–2 orders of magnitude under that** (e.g. $10–50 k gross) so fill quality, not impact,
  is what's being read. Size for the 12.3-kurtosis tail, not the +5 bp mean.
- **Stop rule:** any systematic off-print fill or non-fill is the finding — do not scale to chase a clean
  number (M0 §10).

**Bottom line for `FINDINGS.md`:** T3's signal is real, its net is positive under realistic retail
execution (+5.0 bp/night, ~99.5% bootstrap-positive), and its execution is now feasible on measured
rails. It fails only the strict DSR 0.95 certainty gate. Correct disposition: a small live forward test
to close the one open question (C4), not a place on the dead pile.

---

### Provenance
- Reproduction + realistic re-pricing: `scripts/t3_pressure_reversal.py` / `t3_evaluate.py` (frozen
  logic), recomputed offline from `research/data/t3_cache/panel.json.gz` against
  `T3_FROZEN_CONFIG.json`. Stats via `scripts/trading_bot/stats.py`
  (`deflated_sharpe`, `annualised_sharpe`, `moments`).
- Auction economics: `research/trading_bot/M0_AUCTION_FILLS.md` / `.json` (top-500 opening-print
  availability 99.96%, zero-spread charge vindicated, C4 still open).
- Fill feasibility of near-close market orders: T4/T20 paper-bot work. Fee convention: `costs.py`
  (SEC 31 + FINRA TAF sub-bp).
- Original verdict and gates: `research/trading_bot/T3_RESULT.md`, `T3_HELDOUT_RESULT.json`.
