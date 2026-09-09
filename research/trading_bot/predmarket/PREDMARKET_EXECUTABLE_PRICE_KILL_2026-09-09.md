# PREDMARKET CHUNK D, 2026-09-09 09:00 tick — the coherence track dies at the bid/ask

Shell canary verified. Book: one fresh pull, `pulled_utc 2026-09-09T07:04:33Z`, 3000 markets,
`n_selectable` per pull; T71 respected (every leg below is from THIS pull, no frozen-log prices).

**Outcome: ABSTAIN on probability estimates. Two structural results logged, one screen defect
opened, one wording trap catalogued.**

## 1. The T47 coherence screen scores flags on MIDS. Every flag this tick is worth ≤ 0 at executable prices.

This is the tick's real finding and it is a KILL on the track as currently run.

### 1a. Date-ladder flag — Trump pardons Ghislaine Maxwell (the screen's ONLY flag over 1,045 candidates)

| leg | id | bid | mid | ask | vol | close |
|---|---|---|---|---|---|---|
| "by end of 2026" | 566760 | 0.050 | 0.0550 | 0.060 | $748k | 2026-12-31T00:00Z |
| "before 2027"    | 687689 | 0.044 | 0.0445 | 0.045 | $22.8k | 2027-01-01T04:59Z |

Nesting is real: "before 2027" ⊇ "by end of 2026", so p_later ≥ p_earlier is required, and the
mids violate it by **1.05pp**. The screen flagged it correctly.

The trade is sell 566760 at bid 0.050, buy 687689 at ask 0.045 → **+0.50pp gross**, not 1.05pp;
half the apparent violation is the wide leg's own spread. Against that half-point:
- capital is tied ~3.8 months (to 2027-01-01), so ~1.6%/yr gross before any fee or gas;
- the residual is NOT zero — the two close stamps differ, so a pardon on 2026-12-31 itself is a
  gap the "arb" does not cover;
- the short leg is the $748k book, the long leg is $22.8k, so the +0.5pp exists at one thin ask.

**DEAD at the friction floor.** Distance from zero, not sample size: half a point over four
months is indistinguishable from the cost of holding it.

### 1b. Exhaustive numeric partitions — the overround is 100% spread

Polymarket's Musk tweet-count buckets are the cleanest coherence test in the whole book: a
mechanically exhaustive numeric partition, so `sum(p) = 1` is an identity, not a judgement.

| family | legs | Σ mid | Σ bid | Σ ask | sell-all-at-bid P&L |
|---|---|---|---|---|---|
| Sep 4 → Sep 11 | 11 | 1.0245 | **1.0000** | 1.0490 | **exactly 0.00pp** |
| Sep 7 → Sep 9  |  3 | 1.0075 | **0.9920** | 1.0230 | **−0.80pp** |

The Sep 4–11 family shows a +2.45pp mid overround and pays **exactly zero** — Σbid = 1.0000 to
the tick. The 3-leg family pays **negative**. The market makers on this venue are already
running this screen and quote to it; the mid-overround is the spread and nothing else.

**Verdict: mid-price coherence screening on Polymarket partitions is dead. Do not re-open it.**

## 2. Cross-venue Press Secretary gap — CATALOGUED TRAP, not an edge (10pp, fully explained by wording)

A 10-point gap on nominally the same event and deadline, both liquid, both cheap:

| venue | market | deadline | p | rt cost | vol |
|---|---|---|---|---|---|
| Polymarket | 3701625 "announced by September 30, 2026?" | 2026-10-01T03:59Z | 0.345 | 0.005 | $40.5k |
| Kalshi | KXPRESSSECANNOUNCE-26AUG-OCT01 "Before Oct 1, 2026" | 2026-10-01T03:59Z | 0.445 | 0.045 | $28.7k |

Reading both resolution texts settles it:
- Polymarket: *"An individual announced as an acting or interim Press Secretary will **not** qualify."*
- Kalshi: *"naming the next White House Press Secretary (**including acting/interim**)"*

Kalshi's event set **strictly contains** Polymarket's, so p_Kalshi ≥ p_Poly is *required*. The
10pp is the market's price for an acting/interim-only announcement, which is a perfectly
sensible number with Leavitt's seat vacant. Same-deadline, same-venue nesting is coherent too:
Poly 3701624 (by Sep 11) 0.0325 ≤ Poly 3701625 (by Sep 30) 0.345 ≤ Kalshi 0.445.

This is the exact T47 trap class — near-duplicate wording is load-bearing — and it is the single
largest apparent cross-venue gap in the current book, so it *will* be rediscovered. Added to
`CATALOGUED_TRAPS` in `scripts/trading_bot/predmarket_coherence_screen.py` so it is suppressed
by name from here on.

## 3. Why no probability estimate was frozen

Screened 3000 pulled markets → 366 unseen, liquid (vol > $25k), mid-priced (0.10–0.90), rt ≤ 0.05,
closing within 120 days. Every one of them is foreign or post-cutoff domestic politics — Sweden
(d=3), Berlin/Mecklenburg (d=10–11), Brazil's full federal book (d=24, up to $10.2M on a single
leg), Russia's Duma (d=20), Israel (d=47), Vancouver (d=37). My knowledge cutoff is May 2026.
Against a $10M book on an event four months past my cutoff I have no defensible view, and the
tracker is a *calibration* instrument: freezing an estimate I cannot defend does not make it
informative, it makes the Brier score a measurement of my prior instead of my skill.

Abstention logged via the CLI. This is the disciplined outcome, not a null one — but see the
standing-track note below: abstention every tick since 08-31 is now itself the signal.

## 4. What this means for the track (honest read)

T47 was opened precisely because the agent's cutoff blocks forecasting, so a knowledge-free
arithmetic edge was the way out. This tick prices that escape route at executable prices for the
first time and it is **zero to negative on the cleanest test the book offers**. Combined with the
08-31 → 09-08 abstention streak, the working conclusion is that PREDMARKET1 is a *calibration
logger with no edge thesis behind it*, and the coherence idea was the last live candidate for one.

Opened `T76` to force executable-price scoring into the screen so no future tick spends itself on
a spread mirage. Recommend STRATEGIST (next CHUNK A, hour 12) rule on whether the whole
predmarket lane stays open, given the goal is a US-equities bot and this lane cannot reach it.

**Kill-condition for the coherence track, pre-registered here:** if the next 3 CHUNK D ticks
produce no flag whose *executable* value (sell-at-bid / buy-at-ask, both legs, net of the close-
stamp gap) exceeds **+2.0pp**, T47 is downgraded from STANDING DUTY to killed and CHUNK D stops
running it.
