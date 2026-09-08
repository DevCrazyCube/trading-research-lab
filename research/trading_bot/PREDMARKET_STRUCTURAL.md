# Kalshi STRUCTURAL edges — three-hypothesis test (research only)

**Date:** 2026-08-26 · **Author:** agent (officialjoy04@gmail.com) · **Status:** research only — NO
orders, NO money, NO account, NO wallet, NO git-commit. Free keyless public Kalshi data only.

**What this is (and is not).** The project already runs a *calibration* tracker
(`scripts/trading_bot/predmarket/`) that asks "can the agent out-forecast the crowd." This is a
different question: does the **structure** of Kalshi markets leak a fee-surviving edge you can take
without any information advantage. Three classic structural hypotheses, tested honestly on **resolved**
Kalshi markets with settlement + intraday price history.

**Legal constraint (respected).** Kalshi is CFTC-regulated and US-legal for the owner; **Polymarket is
US-illegal for the owner**. Every rule below is designed **Kalshi-only** and every number comes from
Kalshi's own public API (`api.elections.kalshi.com`, keyless read). Polymarket was **not** touched, as
a venue or as data, in this study. No cross-venue arb is proposed (it would require the illegal leg).

---

## Data & method

- **Source:** Kalshi public REST — settled `markets` (gives binary `result` yes/no) + per-market
  `candlesticks` (1-min `yes_bid`/`yes_ask` book history). Keyless GET only; long pulls detached as
  background subprocesses per the project's no-crawl-in-agent rule.
- **Sample (H1/H2):** **n = 2,907 resolved binary markets** across **14 recurring liquid series** and
  categories — crypto 15-min (BTC/ETH/SOL) and daily (BTCD); weather daily-high (NYC/LAX/MIA/CHI); MLB
  game moneyline / totals / strikeouts / hits; NFL game; WNBA game. Chosen for liquidity + diverse
  probability coverage so no single series drives the calibration curve. Book quality is high:
  **median quoted spread = 1¢; 87% of markets ≤ 2¢, 95% ≤ 5¢.**
- **Price used:** the tradeable book (`yes_bid`/`yes_ask`) at **50% of each market's life** — genuinely
  *pre-resolution* and *executable* (you could transact there and hold to settlement). Mid for the
  calibration curve; **buy at ask / sell at bid** for every net-edge number.
- **Cost model (realistic, per the frozen predmarket spec):** Kalshi taker fee per contract =
  `ceil(0.07·p·(1−p)·100)/100` dollars, charged on **entry**; you **cross the spread** on entry;
  **settlement is free** (buy-and-hold pays no exit fee). This is the *minimum* real cost — it ignores
  slippage beyond top-of-book, which only makes the edges worse.
- **Honesty discipline:** design/held-out split by close-time median; residual noise bars (SE) on every
  bin and rule; multiple-testing bar `sqrt(2 ln N)` where many cuts were tried; the honest **zero**
  reported wherever a signal is noise or too small to beat cost.
- **Reproduce:** collectors `scripts/trading_bot/predmarket_structural_collect.py` (H1/H2) and
  `predmarket_h3_collect.py` (H3); analyzers `predmarket_structural_analyze.py`,
  `predmarket_h3_analyze.py`; raw + result JSON under `research/data/predmarket_structural/`.

---

## H1 — Favorite-longshot bias  →  **VERDICT: NO edge (calibration is good; nothing survives cost + a held-out split).**

Realized YES-rate vs implied probability, binned (n = 2,907):

| implied bin | n | mean implied | realized YES | residual (real−impl) | ±SE |
|---|---|---|---|---|---|
| 0.00–0.02 | 231 | 0.015 | 0.004 | **−0.011** | 0.004 |
| 0.02–0.05 | 270 | 0.031 | 0.033 | +0.002 | 0.011 |
| 0.05–0.10 | 178 | 0.071 | 0.067 | −0.004 | 0.019 |
| 0.10–0.20 | 288 | 0.152 | 0.104 | **−0.048** | 0.018 |
| 0.20–0.30 | 275 | 0.248 | 0.258 | +0.010 | 0.026 |
| 0.30–0.40 | 244 | 0.347 | 0.348 | +0.001 | 0.030 |
| 0.40–0.50 | 339 | 0.450 | 0.493 | +0.043 | 0.027 |
| 0.50–0.60 | 347 | 0.547 | 0.579 | +0.032 | 0.026 |
| 0.60–0.70 | 207 | 0.647 | 0.618 | −0.029 | 0.034 |
| 0.70–0.80 | 144 | 0.752 | 0.757 | +0.005 | 0.036 |
| 0.80–0.90 | 167 | 0.848 | 0.880 | +0.032 | 0.025 |
| 0.90–0.95 | 82 | 0.924 | 0.963 | +0.039 | 0.021 |
| 0.95–0.98 | 49 | 0.965 | 0.980 | +0.015 | 0.020 |
| 0.98–1.00 | 86 | 0.993 | 1.000 | +0.007 | 0.000 |

- The curve hugs the diagonal. There is **no monotone longshots-overpriced / favorites-underpriced
  gradient** — the signature of favorite-longshot bias is absent. The extreme-longshot bins (0–2¢, 2–5¢,
  5–10¢) sit within ~1 SE of the diagonal (residuals −0.011, +0.002, −0.004), i.e. essentially perfectly
  calibrated, not the systematic over-pricing the classic bias would predict.
- **Pre-registered structural rule** (fade longshots ≤10¢ = buy NO; back favorites ≥90¢ = buy YES),
  net of fee + spread, buy-and-hold:
  - All: **−0.0067 / contract** (SE 0.0056, **t = −1.19**, n = 898) — negative.
  - Liquid only (≤3¢ spread): **−0.0025 / contract** (t = −0.48) — **zero**.
  - Design half −0.0033 (t = −0.51); held half −0.0108 (t = −1.13). Never positive.
- **The one flag, honestly killed.** The 0.10–0.20 bin is overpriced at **−0.048 (−2.7σ)** — it clears
  the 14-bin multiple-testing bar (`sqrt(2 ln 14) = 2.30`). But a "fade 10–20¢" rule **fails
  out-of-sample**: design half +0.050 (t = 2.16) → held half **+0.004 (t = 0.16)**, and it is
  **weather-concentrated** (KXHIGHLAX/CHI 15¢ markets resolved 0% while KXMLBTOTAL in the same band
  resolved 32% — opposite sign). It is a design-half artifact, not a coherent structural bias.

**H1 net edge: ≈ 0 (−0.0025 to −0.0067 /contract), indistinguishable from zero after cost. No forward
test warranted.** Kalshi's ~1¢ books have already priced out the longshot bias that survives on
higher-vig venues (racetracks, Betfair, some Polymarket books).

---

## H2 — Near-certain settlement yield ("prediction-market T-bill")  →  **VERDICT: NO real yield (net ≈ 0, and it carries a blow-up tail for that zero).**

Systematically buy YES in the high-confidence band, hold to settlement, net of fee + spread:

| band | n | mean net PnL/contract | ±SE | t | blow-up rate (resolved NO) | mean entry (ask) | mean hold | naïve annualized |
|---|---|---|---|---|---|---|---|---|
| 0.95–0.995 | 62 | **−0.0012** | 0.0164 | −0.07 | 1.6% (1/62) | 0.975 | 0.12 d | ≈ 0 / neg |
| 0.96–0.99 | 47 | −0.0105 | 0.0216 | −0.49 | 2.1% | 0.979 | 0.10 d | neg |
| 0.98–0.995 | 13 | +0.0008 | 0.0005 | 1.44 | 0% | 0.989 | 0.02 d | +15% (n=13, trivial) |

- The gross yield is real but tiny: buying at ~97.5¢ and mostly collecting \$1 is ~2.5¢ gross. It is
  **exactly eaten** by the ~1¢ entry fee + the half-spread crossed + the rare **blow-up** (a 98¢ market
  that resolves NO costs you ~97¢). Net lands on **zero (t = −0.07)**.
- "Annualizing" is a mirage here: holds are hours-to-a-day, so one blow-up dominates the annualized
  figure and it swings wildly negative. The only nominally-positive slice (0.98–0.995, +0.0008) is
  n = 13, within noise, and too small to clear any real slippage.

**H2 net edge: ≈ 0.** It is a T-bill that pays **nothing** after costs and still hands you a ~2% tail of
losing ~97¢. Not worth holding. No forward test warranted.

---

## H3 — Cross-market internal consistency  →  **VERDICT: NO arb (the naïve "9% arb rate" was a measurement artifact; corrected, it is zero).**

**Critical honesty note.** A naïve pass on the H1 sample flagged a ~9% "locked riskless arb" rate with
huge sizes (mean 0.20, max 0.80). **Both drivers were artifacts:** (1) sibling strikes in one event
were snapshotted at *different wall-clock times* (each at 50% of *its own* life — hours apart), and
(2) "ladders" like MLB-strikeouts actually bundle **different players** (`…CWSAKAY18` vs
`…TEXJDEGROM48`) that merely share an event id — different underlyings with no monotonicity constraint.
Corrected test uses **simultaneous books** (all legs sampled at one common timestamp inside their
overlapping live window) and only **genuine single-underlying** structures:

- **Nested thresholds** — KXMLBTOTAL "Over N runs" (must be monotone decreasing in strike).
  **30 events, 198 adjacent pairs.** Mid-monotonicity violations: 5 (2.5%), mean size 0.126 — all
  **sub-spread noise**. **Locked riskless arbs net of fees: 0.** Zero even among the **188 liquid
  pairs** (≤3¢ spread, ≥200 vol). A riskless arb needs `ask_low < bid_high`; it never happens.
- **Exclusive+exhaustive partition** — KXHIGH* daily-high buckets ("79° or below" … "88° or above",
  exactly one resolves YES). **53 events.** Exactly-one-YES validated (98.1%). **Mean sum of YES mids =
  1.022** — i.e. a ~2.2% overround, which *is the market's built-in spread*, not free money. Arbs net
  of fees: **buy-all-YES 0, sell-all-YES 0** (0 in the liquid subset). The ~2% overround is never wide
  enough to cross both sides' spreads plus two fees.

**H3 net edge: 0.** Kalshi's market-makers keep ladders and partitions internally consistent to inside
the spread. There is no risk-limited spread to harvest.

---

## Bottom line

**There is NO real, Kalshi-legal, fee-surviving structural edge in any of the three hypotheses.** All
three land on an honest zero:

- **Favorite-longshot bias:** absent — calibration is good; the pre-registered rule nets −0.0025 to
  −0.0067/contract (t ≈ 0 to −1.2), and the single suggestive bin fails out-of-sample.
- **Near-certain yield:** net −0.001/contract (t = −0.07); the ~2.5¢ gross yield is fully consumed by
  fee + spread + a ~2% blow-up tail.
- **Cross-market consistency:** zero locked arbs once books are compared *simultaneously* on genuinely
  single-underlying ladders; the naïve positive was a sampling/bundling artifact.

**Why:** prediction markets are only more retail-exploitable than liquid equities *if a structural bias
survives the fee.* On the **liquid, high-frequency Kalshi series** (sports, crypto, weather) the books
are ~1¢ wide and the classic biases are already arbed out — the fee/spread wall is the same wall that
killed the equities edges. It is **priced / too-small, like everything else.** No forward paper test is
recommended for these three.

**Scope caveat (the one place not fully closed).** This sample is deliberately the *liquid* corner of
Kalshi. The category where retail longshot bias is most cited — **low-frequency political / macro
longshots** (elections, one-off policy) — is under-represented here because few such markets had
resolved recently and those that did carried **wide, effectively untradeable spreads** (10–40¢ on deep
strikes) in spot checks. So the honest boundary is: *no edge in liquid recurring Kalshi markets;* the
illiquid political-longshot tail is unproven but looks untradeable on spread alone. If any future look
is wanted, it would target resolved **political/econ longshots specifically** and would live or die on
whether their spreads ever tighten enough to transact — a low-priority lead given everything above.

**Gates (unchanged, not triggered):** any real position would need (1) a forward *paper* validation of
a *specific* frozen rule first, then (2) an explicit owner money/account gate. Nothing here clears bar
(1), so neither gate is engaged.

---

## Addendum 2026-09-03 (21:00 CEST tick) — two more structural zeros, now on the WIDE book

The scope caveat above ("the illiquid political-longshot tail is unproven") is the exact corner this
tick tested, and it is now materially closer to closed. This was the **first proposer tick to run on
the T48-fixed data path** (`research/trading_bot/T48_DATAPATH_AUDIT_PREDMARKET_2026-09-03.md`):
27,819 selectable markets versus the ~200 page-1 slice every prior tick saw. If a crowd-beating
structural bias existed in the political book, a 100x wider read is where it should have shown up.

Two knowledge-free tests, both pre-stated, both zero:

**(1) Named-longshot overpricing — FALSIFIED, not merely unproven.** Target: the Polymarket Nobel
Peace Prize 2026 book (20 named candidates, 0.6–7.5¢, resolves ~2026-10-09) — as pure a
political-longshot basket as exists. The thesis says a book of named longshots sums well above 1.
Measured: **Σ p(named) = 0.339**, leaving 0.661 on the unnamed field. That sits *inside* the
historical base rate for "the winner was on the public shortlist." The crowd has already priced the
prize's obscurity bias correctly; there is nothing to fade. Note the direction: on the liquid Kalshi
sample the bias was *absent*; here on the illiquid political tail it is absent too, and by the
mechanism the bias story predicts should be strongest.

**(2) Tenor-monotonicity arbitrage — zero.** For cumulative "will X happen by <DATE>" events, an
earlier deadline can never be worth more than a later one. Grouped all 3,000 volume-ranked markets by
question stem modulo their date token and tested every within-stem pair for `bid(earlier) >
ask(later)` at a 0.5¢ threshold. **0 violations.** The Iran/Hormuz/blockade ladders (Sep 7 / 14 / 30)
are cleanly monotone, and the US–Iran-meeting YES/NO complement sums to 0.987 — inside its own spread.
One apparent contradiction (United Russia "gain the most seats" 0.705 vs "win the most seats" 0.991)
was checked and is **not** one: the 0.705 leg belongs to a coherent net-seat-*gain* partition summing
to 1.009. Same lesson as §cross-market above, now on a much larger sample: the naïve positives are
bundling artifacts, and simultaneous quotes leave nothing.

**Declined on purpose (recorded so it is not mistaken for an edge later).** ~a dozen markets are
structurally near-certain and priced just short of it (United Russia wins most seats, 0.991; honest
estimate ≥0.997). That gap is **cost of capital on a month-locked position, not crowd error** — the
same finding as "near-certain yield: net −0.001/contract" above. Logging a batch of these would pad
the tracker's Brier with guaranteed micro-wins and contaminate the calibration read it exists to
produce. Abstention logged instead.

**Standing:** the tracker keeps its 66 open calibration estimates and its first settlements (09-06,
09-20). Those still answer the only live question here — *can the agent out-forecast the crowd on
markets it chose* — and that verdict is untouched. But the *structural* (knowledge-free) side of the
prediction-market thesis is now **three-for-three dead**, and the last excuse for it ("we only ever
looked at the liquid corner / we only ever saw 2% of the book") is gone. Do not spend further ticks
re-running structural scans on this book; only the calibration clock is worth waiting on.
