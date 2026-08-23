# INVENT_0823 `sympathy` — intra-group lead-lag: when a leader moves sharply, do close peers catch up?

**Verdict: NO. The theme is noise as a tradable claim — 0 of 26 formulas clears the noise bar, 25
of 26 are net-negative, and 18 of 26 still lose money at a *literally zero* half-spread.**

And the reason is not the spread. The reason is that **the "under-reaction" this whole family is
built on does not exist**. At a 3σ leader shock the peers already transmit **88 %** of their
beta-implied move *inside the same five-minute bar*, versus 99 % on an average bar; and the
missing 12 % — a signed **−2.85 bp** — **never comes back**. Over the following hour the peer
closes **0.36 bp of a 19.25 bp measured gap (1.9 %, t = 0.87)**, peaking at 0.54 bp (t = 1.51) at
40 minutes. A sharp leader move is simply *more idiosyncratic to the leader* than its average
move, the market prices that correctly in real time, and there is nothing left over to trade.

Pre-registration: `INVENT_0823_sympathy_PREREGISTRATION.md`, sha256
`2d284d0b7dd22f5b2c068cf8ec9ce7e523463ec09b1ef172a8f1941753db43aa`, written and hashed **before
`--stage design` produced a number**; `sympathy0823.py` refuses to run against any other hash.

---

## 1. What was searched — 26 formulas, twelve structurally different claims

Design **2021-01-04 → 2024-12-31** (1 005 sessions, 3.99 y), held out **2025-01-02 → 2026-08-14**
(405 sessions). 132 US symbols, 5-minute bars (`research/data/rv_cache/panel_rv.npz`), ten tight
groups fixed ex ante in the pre-registration. Costs: per-symbol `headline_half_bp` (floor 1.0 bp,
provenance TICK_FLOOR_TIMES_ADVERSITY) + 0.15 bp/turnover SEC §31 + FINRA TAF — mean round trip
**3.46 bp** on one leg.

**The timing rule is the point.** The leader's move is measured to the close of bar `b`; the peer
is bought at the close of bar **`b + 1`**. Signal and fill are never the same print and the whole
of the peer's immediate reaction bar is forfeited. Entry lag is a free parameter of the evaluator,
so every formula is priced at lags 0 (diagnostic only), 1 (the design), 2, 3 and 6.

| claim | what it says | formulas |
|---|---|---:|
| C1/C2 | peer under- / over-reacts to a 3–4σ leader bar; trade the β-deficit | 6 |
| C3 | index heavyweight moves; QQQ under-reacts by its weight | 2 |
| C4 | no leader — the group's *consensus* move, trade the laggard | 2 |
| C5/C6 | leader's overnight **gap** → peer's residual gap, held to the close | 4 |
| C7 | leader's **last 30 minutes** → peer's *next* morning gap | 2 |
| C8 | leader **volume** shock rather than return shock | 2 |
| C9 | direction test: the sector **ETF leads its members** | 2 |
| C10 | asymmetry: leader down-shocks vs up-shocks | 2 |
| C11 | leader's cumulative 30-minute move | 2 |
| C12 | post-shock intra-group **dispersion**, dollar-neutral | 2 |

Same-index sibling pairs are excluded from every peer set and at most one ETF per group is
admitted, so this cannot re-derive the ETF-sibling RV artefact under a new name.

**Self-test** (`INVENT_0823_sympathy_SELFTEST.json`): on a synthetic panel carrying a *known*
catch-up, the engine returns Sharpe **+16.3** when the catch-up lands at `b+2/b+3` and only
**+1.9** when the identical catch-up lands entirely in the forfeited bar `b+1`, and **−0.26**
under a sign flip. The harness finds real sympathy and refuses sympathy it cannot reach.

## 2. The noise bar, and the fact that nothing goes near it

| bar | value (Sharpe units, 3.99 y) |
|---|---:|
| analytic `√(2 ln 26)/√3.99` | **1.278** |
| PLACEBO-A, day-shifted events, p95 of max over 26 | 0.904 |
| PLACEBO-B, event sign flip, p95 of max over 26 | 0.835 |
| **bar used** (the strictest) | **1.278** |

Both placebos are *size-matched by construction* — same trades, same slots, same counts, only the
sympathy link destroyed — and they come in **below** the analytic bar here rather than above it.
That is not the usual overlapping-book inflation being absent; it is because half the 26 are exact
sign mirrors of the other half, so the max-statistic over them behaves like a max over ~10
effectively independent bets.

| statistic over the 26 | gross | **net** | net at a **literally zero** half-spread |
|---|---:|---:|---:|
| max | **+0.72** (`C1d`) | **+0.01** (`C7b`) | +0.42 (`C10a`) |
| median | +0.10 | −2.36 | −0.08 |
| min | −0.59 | −8.47 | −0.80 |
| n positive | 18 / 26 | **1 / 26** | 8 / 26 |

The best **gross** Sharpe in the family is **+0.72**, i.e. t = 1.44 over four years, against a bar
of 1.278 — and that is *before a single basis point of cost*. **0 of 26 formulas passed a single
one of the four pre-registered promotion gates.**

## 3. Held out — the pre-registered near-miss run

No formula passed, so §8 of the pre-registration carried the top two by design net Sharpe out of
sample **labelled BELOW THE NOISE BAR**. Running them was not a promotion.

| formula | design gross | design net | held-out gross | **held-out net** | t | legs |
|---|---:|---:|---:|---:|---:|---:|
| `C7b_LATEMOVE_NEXTOPEN_FADE` | +0.25 | +0.01 | +1.04 | **+0.80** | +1.01 | 862 |
| `C5a_GAP_CATCHUP_close` | +0.03 | −0.22 | −1.27 | **−1.58** | −2.00 | 916 |

`C7b` — fade the peer's *next-morning* gap after the leader's last-30-minute move — is the only
cell in the family that is net-positive on both windows, and it is net-positive by +0.01 and +0.80
Sharpe at t = 1.01 on 483 design events. Its design gross of +0.25 is a fifth of the noise bar. It
is a near miss reported as a near miss, and nothing more.

## 4. Why it dies — three numbers, none of them the spread

**(a) The gap is real and it is permanent.** Pooled over the nine stock-led groups, 39 076 leg-
events at 3σ:

| minutes after the leader's shock bar | 5 | 10 | 20 | 30 | 40 | 60 |
|---|---:|---:|---:|---:|---:|---:|
| cumulative **signed** peer move (bp) | 0.10 | 0.16 | 0.12 | 0.23 | **0.54** | 0.36 |
| t | 0.65 | 0.81 | 0.41 | 0.73 | 1.51 | 0.87 |

against a **mean measured mispricing of 19.25 bp** (median 13.33) and a **3.46 bp** round trip.
The peer recovers **1.9 %** of the gap in an hour, insignificantly.

**(b) The peers are not slow, the shock is idiosyncratic.** Transmission of the beta-predicted
move, measured contemporaneously in the shock bar itself:

| | SEMI | MEGATECH | BANK | ENERGY | HEALTH | STAPLE | DISCR | GOLD | PAYMENT | **pooled** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| at a 3σ leader shock | 0.92 | 0.91 | 0.95 | 0.87 | 0.59 | 0.80 | 0.77 | 1.03 | 0.65 | **0.883** |
| on an average bar | 1.00 | 1.00 | 1.00 | 0.98 | 0.90 | 0.96 | 0.97 | 1.00 | 0.88 | **0.986** |

The peer group absorbs 88 % of the predicted move *within the same five minutes*. The 12 % it does
not absorb is the correct answer, not a queue.

**(c) The direction trade is worse, and its held-out "signal" is an accounting illusion.** The
purest form of the claim — after a leader up-shock simply buy the peers, no deficit at all — earns
**+0.09 bp/day (t +0.10)** in the design window and **−0.59 bp/day (t −0.52)** held out, on the
tradable leg (enter `b+1` close, exit `b+12` close), against 3.5 bp of cost. Held out, the *naive*
leg-level event study shows +2.35 bp at t = 3.1 — but 0.93 bp of that lands in the forfeited bar
`b+1` and the rest evaporates the moment the t is clustered by day instead of pretending 17 744
correlated legs are independent. This is exactly the shape of a false positive, caught by the
timing rule and the clustering, not by luck.

**Cost ÷ gross, best cells:** `C10a` 3.4×, `C11b` 3.9×, `C5b` 4.9×, `C3a` 5.1×, `C9a` 5.8×,
`C3b` 6.1×; median across the family **12×**. Even a *perfect* zero-spread rail leaves 18 of 26
negative, because at this turnover the SEC/TAF pass-through alone (0.30 bp per event round trip)
is comparable to the entire gross edge (0.02–0.94 bp).

## 5. The bounce check — clean, and the lag profile says where the apparent edge lived

ρ1 of the first difference of all **41** traded hedged spreads: min −0.153, median **−0.028**, max
−0.005. **Zero fail the −0.35 gate** — these spreads carry no bid-ask bounce worth the name.

But the catch-up family's gross Sharpe still decays sharply with the fill: `C1a` **+0.83 → +0.33 →
−0.07** at lags 0 / 1 / 2. That decay is *not* a spread artefact; it is in the **signal
construction** — the deficit `β·r_L − r_p` is measured off the peer's own bar-`b` close, so a peer
whose close printed on the bid gets a spuriously positive deficit and a fill one print later at
the ask. Filling at the signal print flatters the whole family and filling one bar later does not.
It is the same lesson in a new costume: **a gross Sharpe that lives at the signal print is
evidence against.**

The one cell whose gross does **not** decay is `C3b` (heavyweight → QQQ, β-hedged): +0.57 / +0.65 /
+0.58 at lags 0/1/2 on the design window, and it persists out of sample (held-out gross +0.55 at
lag 1, +0.95 at lag 2 — read post hoc, outside the shortlist, and therefore a diagnostic and not
evidence). Its net is **−2.7** on both windows. The index heavyweight → index under-reaction is
the one member of this family that looks like a real micro-effect; it is 6× inside its own cost
and it is not a business.

## 6. What this closes

* Intra-group sympathy at 5-minute resolution, in every form tested — leader→peer, ETF→member,
  consensus→laggard, gap→intraday, close→next open, volume-shock, dispersion — is **dead**, and it
  is dead *gross*, before cost, which is a stronger statement than the RV family's death (that one
  had a real +2.93 gross signal and lost it to the spread).
* Do not re-test this with a cheaper rail. 18 of 26 lose at zero spread; the constraint is that
  peers respond in the same five minutes.
* The only surviving research question worth anything here is the **index-heavyweight → index**
  micro-effect (`C3b`), and its own numbers say it needs spreads **6× tighter** than a 1 bp floor.
  That is not a rail that exists.

## 7. Artefacts

| file | what |
|---|---|
| `INVENT_0823_sympathy_PREREGISTRATION.md` / `.sha256` | frozen design, hashed before any number |
| `scripts/trading_bot/sympathy0823.py` | engine — stages `selftest / design / diag / nulls / shortlist / holdout` |
| `scripts/trading_bot/sympathy0823_addendum.py` | zero-spread bound, ρ1 gate, post-hoc `C3b` read |
| `INVENT_0823_sympathy_SELFTEST.json` | the harness catches a real catch-up and misses an unreachable one |
| `INVENT_0823_sympathy_DESIGN.json` / `_daily.npz` | all 26 formulas × 5 entry lags |
| `INVENT_0823_sympathy_DIAG.json` | event study, per-group, cost ÷ gross, gross-by-lag |
| `INVENT_0823_sympathy_NULLS.json` | 400 draws × 2 size-matched placebos |
| `INVENT_0823_sympathy_SHORTLIST.json` | 0 passing; the near-miss picks, frozen before the held-out read |
| `INVENT_0823_sympathy_HOLDOUT.json` | the two near-miss picks out of sample |
| `INVENT_0823_sympathy_TRANSMISSION.json` | 0.883 vs 0.986 |
| `INVENT_0823_sympathy_DIRECTIONAL{,_CLUSTERED}.json` | the pure direction trade and its day-clustered t |
