# INVENT 2026-08-26 — MASTER SYNTHESIS (daily invention)

**Date:** 2026-08-26
**Theme:** Event-driven / catalyst — **earnings-8K announcement-return drift** (price-reaction momentum, **NOT** accounting-SUE PEAD), filing-time (BMO/AMC) asymmetry, reporting-day crowding, and pre-announcement run-up fade.
**Data:** cached `t15_cache` — 34,025 matched Item-2.02 earnings-8K filings (with exact filing timestamps) + close-only daily bars. Design window **2016–2020**; held out **2021–2026** kept untouched until the design freeze. No network; all reads from pre-existing gitignored caches.
**Verdict: HONEST ZERO. 0 survivors. 0 basket proposals.** Two candidates cleared the design bar; **both were REFUTED on the untouched held-out window.**
**Basket action: NONE.** No leg added, no weight changed, no re-freeze.

---

## 1. The three angles tried

All three angles are sub-strands of the same catalyst object: the **announcement-day price reaction** of an 8-K Item-2.02 (results of operations) filing, used as a *momentum* signal — sign/size of the market-adjusted reaction, **not** an accounting-surprise (SUE) signal. Discipline throughout: design → held-out split, pooled multiple-testing bar via **√(2 ln N)**, everything scored **net of realistic cost**.

| # | Angle | Object | N formulas | Pooled noise bar (√(2 ln N), t-units) | Design-clearing? | Honest zero? |
|---|---|---|---:|---|---|---|
| 1 | **Announcement-return momentum** | Monthly tercile L/S on signed announcement-day reaction `AR_res`, 20-session market-adjusted hold; conditioned on |AR| size (BIGGAP) | screened across the pooled family | pooled bar ≈ **t 2.5–3** across all candidates screened | **YES** (2 candidates, S8/S6) | **YES on held-out** |
| 2 | **Filing-time (BMO/AMC) asymmetry** | Same reaction-momentum, split by filing time of day (`BMO`<14 UTC → same session; `AMC` → next session), reaction-session `t0` mapping | included in pooled family | same pooled bar | no distinct design-clearing member beyond the t0-mapping already baked into S8/S6 | **YES** |
| 3 | **Reporting-day crowding + pre-announcement run-up fade** | Restrict to crowded reporting days (>median same-session reporters); pre-announcement run-up fade variants | included in pooled family | same pooled bar | **YES** (crowding member, S6) | **YES on held-out** |

The two members that cleared the design bar (S8_BIGGAP, S6_CROWD) are the **same core object** — signed announcement-return tercile momentum with a 20-session market-adjusted hold — differentiated only by the conditioning gate (above-median |AR| vs crowded reporting session). The filing-time-asymmetry and pre-announcement run-up-fade strands produced **no** design-clearing candidate on their own. So even before the held-out read, 2 of 3 angles were honest zeros at the design stage; the survivor angle then failed OOS.

**Pooled multiple-testing framing.** The operative bar is the expected max of N noise candidates, **√(2 ln N)** in the Sharpe/t units of the window. As the held-out analysis notes, across the many candidates this programme has screened the pooled bar sits at roughly **t ≥ 2.5–3** — well above the single-test 1.96. Neither survivor's held-out t (0.62, 0.81) comes anywhere near it; both also fail the far weaker single-test bar.

---

## 2. Design-window candidates that cleared the bar

Both are real design-window objects. Both were reproduced from cache under an honest construction (the S8 sanity check reproduces the claimed design t on the design window at ~5 bp/side, confirming the design number already bakes in cost).

### 2.1 `S8_BIGGAP_earnings_momentum_H20`
- **Formula:** Among earnings-8K events with |market-adj announcement return| above the cross-sectional median, form monthly tercile long-short on sign/size of the announcement-day reaction `AR_res = (close[t0]/close[t0-1] − 1) − SPY_ret`; hold **20 sessions** market-adjusted. `t0` = reaction session (BMO filing <14 UTC → same session; AMC → next).
- **Design:** t = **2.74**, netSharpe = **1.22** (2016–2020, 60 months, ~5 bp/side).
- **Data:** `t15_cache` `earnings_8k.jsonl` + `daily_bars.json.gz`; 33,367 usable Item-2.02 events (cik→ticker mapped), close-only bars, SPY market adjustment.
- **Clears design bar:** YES.

### 2.2 `S6_CROWD_earnings_momentum_H20`
- **Formula:** Announcement-return tercile L/S momentum restricted to events falling on **crowded reporting days** (> median number of same-session reporters), 20-day market-adjusted hold.
- **Design:** t = **2.07**, netSharpe = **0.94** (59 months).
- **Data:** same `t15_cache`; 13,938 priced 8-K Item-2.02 events, announcement-day market-adjusted reaction as the momentum signal, entry at reaction-day close (point-in-time).
- **Clears design bar:** YES (though the held-out rebuild could **not** reproduce t=2.07 under any honest construction — best design variant t=0.86, baseline design net t=0.52 — a red flag in its own right).

---

## 3. Held-out verdicts — BOTH REFUTED

### 3.1 `S8_BIGGAP_earnings_momentum_H20` — **REFUTED**
- **Held-out net Sharpe 0.26, net t = 0.62** (2021–2026, 67 months).
- Faithful re-implementation from cache (33,367 usable 2.02 events; close-only `daily_bars`; SPY adjustment; BMO<14 UTC→same-session / AMC→next-session `t0`; monthly above-median-|AR_res| filter → signed-AR terciles, long winners/short losers, 20-session market-adjusted hold).
- **Sanity check PASSES:** on the design window at ~5 bp/side reproduces t=2.75, netSharpe=1.23 (claimed 2.74/1.22) — the design number already includes ~5 bp/side cost.
- **Collapse on held-out.** Even at **ZERO cost** held-out mean = +0.51%/mo, t=1.03, Sharpe=0.44 — already failing any t≥2 bar. At the design's own ~5 bp/side: t=0.62, netSharpe=0.26. At a standard 10 bp/side (20 bp round trip): t=0.21, netSharpe=0.09. At 20 bp/side it goes **negative** (t=−0.60).
- **Diagnosis:** classic design-window overfit / post-2020 decay of an earnings price-reaction momentum effect. Neither clearly positive net-of-realistic-cost nor anywhere near the pooled bar (t≈2.5–3). **REFUTED.**

### 3.2 `S6_CROWD_earnings_momentum_H20` — **REFUTED**
- **Held-out net Sharpe 0.36, net t = 0.81** (2021–2026).
- Rebuilt from cache (13,938 priced Item-2.02 events; announcement-day market-adjusted reaction as signal; within-crowded-session terciles > median reporters; 20-session market-adjusted hold; entry at reaction-day close so the signal is point-in-time). Costs = test half-spread 1.43 bp/leg both legs + SEC31 + FINRA TAF + short borrow ≈ **4.05 bp round-trip/name**.
- **Two failures:**
  1. **Not clearly positive/significant** — net t=0.81 < 1, below even the single-test 1.96 bar and far below the pooled bar (~3+ given the dozens of strategies screened).
  2. **Spec-fragile** — equally-defensible variants swing the sign: pooled-tercile/monthly t=0.99, but seasonal (quarterly) aggregation collapses to t=0.18 (daily terciles) and t=−0.10 (pooled, negative).
- Compounding: the claimed design t=2.07 / Sharpe 0.94 could **not** be reproduced under any honest construction (best design variant t=0.86, baseline design net t=0.52). **REFUTED.**

---

## 4. SURVIVORS

**[] — HONEST ZERO.**

No candidate cleared the held-out gauntlet. Both design-clearing candidates were refuted on the untouched 2021–2026 window; neither is clearly positive net of realistic cost, and neither comes near the pooled multiple-testing bar. **Nothing is promoted. No basket leg proposed. Forward clock untouched.**

---

## 5. Dead-ledger additions

Log these so they are **not re-proposed**:

- **`S8_BIGGAP_earnings_momentum_H20`** — earnings-8K announcement-return **momentum**, above-median-|AR| conditioned, monthly signed-AR terciles, 20-session market-adjusted hold. Design t=2.74/SR 1.22 reproduced; held-out t=0.62/SR 0.26, and **already dead at zero cost** (t=1.03). Design-window overfit / post-2020 decay. **DEAD.**
- **`S6_CROWD_earnings_momentum_H20`** — same object restricted to crowded reporting sessions, 20-session hold. Held-out t=0.81/SR 0.36, spec-fragile (quarterly/daily variants sign-flip), and the design t=2.07 was **not reproducible** under honest construction. **DEAD.**
- **Whole family — earnings-8K price-reaction (announcement-return) momentum on free close-only bars.** Signed/sized announcement-day reaction as a momentum signal, in every conditioning tried this round: |AR| size gate (BIGGAP), filing-time BMO/AMC asymmetry, reporting-day crowding, and pre-announcement run-up fade. The effect exists on the 2016–2020 design window and **decays away post-2020**; net of a realistic ~4–5 bp round-trip it is indistinguishable from noise on held-out. **Do not re-propose earnings announcement-return momentum in these forms.** Distinct from accounting-SUE PEAD (`t15_pead`), which is a separate object and not what died here.
- **Method note for the ledger:** a design-window number that a faithful rebuild **cannot reproduce** (S6: 2.07 → 0.52–0.86) is itself a refutation signal, independent of the held-out read. Treat non-reproducibility of the design claim as a fail.

---

## 6. Discipline / disclosure

- **Split:** design 2016–2020 (~59–60 months); held out 2021–2026 (67 months), scored only after the design construction was fixed. Held-out window was untouched during design.
- **Pooled correction:** operative bar = expected max of the screened family via **√(2 ln N)**; across the candidates screened this sits at t ≈ **2.5–3**, above the single-test 1.96. Both survivors fail even the single-test bar.
- **Net of cost:** S8 charged ~5 bp/side (design number already bakes this in, verified by sanity check); held-out re-priced across 5/10/20 bp/side rungs. S6 charged test half-spread 1.43 bp/leg both legs + SEC31 + FINRA TAF + short borrow ≈ 4.05 bp round-trip/name.
- **Point-in-time entry:** reaction-day close entry; `t0` mapped BMO(<14 UTC)→same session, AMC→next session. No same-bar/look-ahead fills.
- **No network.** All reads from `t15_cache` (`earnings_8k.jsonl`, `daily_bars.json.gz`, cik/ticker maps).
- **Research only.** No orders, no money, no git-commit from this round.

## 7. Files

- This file: `research/trading_bot/INVENT_2026-08-26_MASTER.md`
- Data (gitignored): `research/data/t15_cache/{earnings_8k.jsonl, daily_bars.json.gz, ...}`
- Code: `scripts/t15_pead.py` (SUE-PEAD object; distinct from the announcement-return momentum family killed here)
