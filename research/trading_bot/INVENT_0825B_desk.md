# INVENT_0825B — CHUNK B (15:00 CEST) invention record: three angles, all killed at the desk by the ledger

**Date:** 2026-08-25 15:00 CEST tick · **Formulas run: 0 · Numbers read: 0 · Survivors: 0 · Basket action: NONE.**
Context: today's 07:23 round (`INVENT_0825_MASTER.md`, 54 formulas, 0 survivors) closed free-bar intraday
equity microstructure and the perp funding window; the DoltHub free options panel was tested the same
morning (`DOLT_OPTIONS.md`, honest zero). The 00:00/12:00 STRATEGIST notes order CHUNK B ticks to T33 → T34 →
T35 with **no new free daily/intraday sweeps**. This tick's real work was **T34** (window-2 restart verified
and ledgered: `research/b11m_window2/T34_RESTART_2026-08-25.md`). The invention round below was held to the
pre-registration desk: mechanism, test, cost and kill were written, then each angle was checked against the
dead ledger *before* any data was read. All three were already dead. That is the round's result.

| # | Angle (original framing) | Mechanism / claimed tether | Pre-registered test (never run) | Where the ledger already killed it |
|---|---|---|---|---|
| 1 | **CEF issuer tender / rights-offer discount convergence** — discount must converge to the published tender price (contractual claim, published synchronous NAV) | event study: entry at the open *after* the EDGAR acceptance stamp (0822 EDGAR-instant rule), exit at tender expiry; N ≈ 100–300 SC TO-I events 2015–26; cost = CEF half-spread 10–30 bp; kill: net mean ≤ 0 or t < pooled bar | `INVENT_0822C_cefdeep.md` §8e: issuer tenders, repurchase notices, rights offerings (N-2/424B cohort 1.42 → 0.50 → −0.18) all ≈ 0 in both windows; form-type label too coarse, needs filing *text* |
| 2 | **Term-CEF pull-to-NAV carry** — rank by annualised discount-to-term (d/T) instead of discount level; mandated wind-up makes the claim contractual | cross-sectional tilt, `t12_cache/history_5Y` (360 funds, weekly price+NAV+discount, 2021–26), design/held-out split, ρ1 gate first, size-matched null | `DEEPMINE_CEFNAV.md` X01 / `INVENT_0822C_cefdeep.md`: term-fund / mandated-wind-up screen 0.02 design, 0.05 held — the wind-up story does not price on free NAV data; d/T is a re-parametrisation of a dead screen |
| 3 | **SPAC trust-value tether** — buy below published trust, redeem at NAV | — | `INVENT_0823_exotic.md`: trust value per share is not free; and by construction the spread is a T-bill-minus (T11-type death) |

Also considered and not proposed: the earnings-date IV-crush study `DOLT_OPTIONS.md` names as the panel's
"only untested corner" — it is a *published* effect (violates the originality rule) and a short-vol-around-events
object (tail guardrail), so it is not an invention candidate.

## Durable output of this tick (the only one)
**Recommendation for T35 (08-26 03:00 tick): use the DoltHub panel as the convexity DESIGN window.**
`research/data/doltopts_cache/` holds 347 weekly EOD chains (2019-05 → 2026-08, dense from 2020-01) with
**bid/ask** on ~50 liquid names (`DOLT_OPTIONS.md` §1). Bought-wing/straddle *cost* — the quantity the
free-data-convexity-wall memory said was unmeasurable — is measurable there for ≤ ~50 DTE, which is exactly the
T33 collector's expiry band. Writing the joint T31/T33 convexity pre-registration with its ≤ 3 trigger designs
sized and costed on 2020–26 Dolt data makes the forward panels a *pure held-out* rather than design+test on the
same panel. Caveats to carry into the pre-reg: no OI/volume (no positioning trigger), front-month only, single
EOD snapshot of uncertain stamp (Clause 2 — entry marks only, never vol-vs-realised). Zero forward-panel
numbers are read by doing this.

**Dead-ledger additions:** none new (all three deaths pre-existed). **Basket:** untouched, clock locked.
