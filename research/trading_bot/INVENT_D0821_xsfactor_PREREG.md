# INVENT D0821 — cross-sectional equity factors, fresh structures: PRE-REGISTRATION

Written **before any design-window number exists** for these 28 signals. Only the
self-test (planted edge / sign flip / pure noise / lookahead control / cluster
stability) has been run.

Theme key: `xsfactor`. Script: `scripts/trading_bot/invent_d0821_xsfactor.py`.

## What this is NOT re-testing

The `NEWTERR xs_equity` sweep already spent **132 cells (44 signals × 3 horizons)** on
this exact panel, universe, cost model and fill convention, and killed all of them
(max net t = **+0.89**, zero picks, held-out never opened). Dead and not repeated here:

`REV1 REV2 REV5 REV10 REV1_RESID REV5_RESID REV1_STD REV5_STD REV_INTRA REV_ON
REV1_LAG1 CLOSE_LOC RANGE_SHOCK_REV REV1_x_ILLIQ REV1_x_VOLSHOCK REV1_x_SIG
REV_ON_INTRA_SPREAD AMIHUD SIZE_ILLIQ ZERORET DV_SHOCK_REV DV_TREND_REV LOWVOL
LOWIVOL LOWBETA LOW_VOV LOWMAX LOWSKEW LOWRANGE MOM20_SKIP1 MOM5_SKIP1 MOM20_RESID
HI52 MOM_INTRA5 SVR_LEVEL SVR_SHOCK SVR_TREND SVR_x_REV SVR_DISP` plus the five
`REV1_*_UNIV` sub-universe conditioners.

Also excluded by instruction: **every regime gate / conditioner** (round-3 meta-result:
gating is noise and harmful, 0/107 survivors). There is not one gated formula below.

## Windows (inherited, unchanged)

- **Design**: 2016-01-04 → 2021-12-31
- **Held out**: 2022-01-03 → 2026-08-14 — not touched until the design picks are on disk.

Group-fitted signals (clusters, peers, hedge betas) need a 250-session warm-up, so they
are flat until ~2017-01. Days on which a book carries no notional are **excluded** from
its statistics rather than scored as zero-return days.

## Universe, construction, costs — identical to NEWTERR xs_equity

close ≥ $5, 20d geometric-median dollar volume ≥ $20M, ≥200 valid closes in 260 sessions,
delisted names retained. Decile long/short, equal-weight, dollar-neutral, gross 1.0.
Signal from close of *t*, **entry at the open of t+1, exit at the open of t+1+h**,
h ∈ {1,3,5}, overlapping cohorts averaged. Cost = shape-preserving Corwin–Schultz half
spread anchored to a 5 bp universe mean, +0.5 bp fees, on |Δbook|, +50 bp/yr borrow on
short notional. Stressed additionally at flat 5 bp and flat 10 bp per side.

## Point-in-time group machinery (new)

At each quarterly refresh (`STEP=63`) using **only** the prior 250 sessions:
SVD of standardised returns → 10 PC loadings → k-means into **15 statistical sectors**;
top-**10** correlation peers per name; OLS hedge beta on the peer basket.
Self-test: 39 periods, median 1533 names labelled, **91.2 %** pair-level cluster
agreement between consecutive quarters (the sectors are stable, not resampled noise).

## The 28 formulas, with mechanism and sign declared in advance

Sign convention: higher signal ⇒ LONG. A formula whose design t is negative under its
declared sign is DEAD; a sign flip is not a rescue.

| # | name | family | signal | declared sign / mechanism |
|---|---|---|---|---|
| 1 | `SEC_REV1` | sector | −(r − cluster r), 1d | dislocation vs statistical sector reverts |
| 2 | `SEC_REV5` | sector | −Σ5 (r − cluster r) | same, 5d |
| 3 | `SEC_REV1_Z` | sector | −(r−clu)/σ20(r−clu) | same, risk-normalised |
| 4 | `SEC_REV5_Z` | sector | −Σ5(r−clu)/σ√5 | same, 5d risk-normalised |
| 5 | `SEC_MOM20` | sector | +mean20 lag1 (r−clu) | sector-relative info diffuses slowly |
| 6 | `CLU_REV1` | sector | −cluster's own 1d return | cluster-level flow is non-informational |
| 7 | `CLU_MOM20` | sector | +cluster's own 20d return | sector news diffuses slowly |
| 8 | `FR_REV1` | mfresid | −ε, ε = XS resid on beta,size,vol,peercorr,hedgebeta | true factor-neutral reversal |
| 9 | `FR_REV5` | mfresid | −Σ5 ε | same, 5d |
| 10 | `FR_REV1_Z` | mfresid | −ε/σ20(ε) | same, risk-normalised |
| 11 | `FR_MOM20` | mfresid | +mean20 lag1 ε | factor-neutral momentum |
| 12 | `PEER_DIV1` | peer | −(r − peer-basket r) | pairwise correlation-breakdown reverts |
| 13 | `PEER_DIV5` | peer | −Σ5 (r − peer r) | same, 5d |
| 14 | `PEER_DIV5_Z` | peer | −Σ5(r−peer)/σ√5 | same, the desk-standard z form |
| 15 | `PEER_DIV20_Z` | peer | −Σ20(r−peer)/σ√20 | slower breakdown reverts |
| 16 | `PEER_HEDGE_DIV5` | peer | −Σ5 (r − β̂·peer r) | beta-hedged breakdown |
| 17 | `PEER_CORR_LOW` | peer | −mean peer correlation | un-hedgeable risk earns a premium |
| 18 | `BETA_DOWN_UP` | betashape | +(β⁻ − β⁺), 250d | poor hedges trade at a discount |
| 19 | `BETA_INSTAB` | betashape | +σ120(β60) | unstable exposure is costly to warehouse |
| 20 | `IDIO_SHARE` | betashape | +σ60(ε)/σ60(r) | scale-free idiosyncratic share, premium |
| 21 | `IVOL_MF_LOW` | ivol | −σ20(ε) | multi-factor ivol, leverage constraint |
| 22 | `IVOL_CHG_LOW` | ivol | −(σ20(ε)/σ120(ε) − 1) | vol jumps attract lottery buyers |
| 23 | `IVOL_SEC_LOW` | ivol | −σ20(r − cluster r) | sector-relative ivol |
| 24 | `AMIHUD_SIZENEUT` | liq | +XS resid of log-Amihud on size | Amihud is not just size |
| 25 | `AMIHUD_CHG` | liq | +(log-Amihud20 − log-Amihud120) | liquidity deterioration is repriced late |
| 26 | `SPREAD_LEVEL` | liq | +modelled half spread | spread, not impact, as the premium |
| 27 | `SQRT_IMPACT` | liq | +log mean20 |r|/√$vol | square-root impact functional form |
| 28 | `ILLIQ_VOLNEUT` | liq | +XS resid of log-Amihud on size and vol | illiquidity net of size and vol |

## Bars

N = 28 × 3 = **84** cells ⇒ within-theme E[max|t|] ≈ √(2 ln 84) = **2.98**.
Pooled with the 132 NEWTERR cells that searched the same theme on the same panel:
N = 216 ⇒ **3.28**. **The pooled 3.28 is the bar that applies**, because both searches
are being read together as "does anything in short-horizon US equity cross-section work".

A formula is real only if design net t **clearly** beats the bar **and** held-out net
Sharpe is positive after the cost model above. Design survivors additionally face a
**lag-kill** (entry at the open of t+2): losing most of the edge to one extra day of lag
means it was a staleness artefact.

---

## ADDENDUM — held-out declaration (written after the design run, before the held-out run)

The design run is on disk (`INVENT_D0821_xsfactor_DESIGN.json`): **0 frozen picks**,
max net t **+0.78**, max GROSS t **+2.32** — nothing reached the within-theme bar (2.98),
let alone the pooled bar (3.28). **No formula is promotable, and the held-out window
cannot change that.**

The held-out window is therefore opened for **one diagnostic question only**, declared
here in advance: *the design window says the factor-neutral reversal mechanism produces
real GROSS alpha that is smaller than the spread. Is that a design-window artefact, or a
structural fact about this asset class?* This matters to the programme's standing
"free-data wall" question (is the wall a signal wall or a cost wall?), and it can only
be answered on virgin data.

Exactly three things will be read out of the held-out window. Nothing else in the
held-out file is evidence for or against anything:

1. `FR_REV1 h=1` **gross** Sharpe and t (the design-window gross maximum).
2. `REV1`-family cost geometry: gross bp/day and break-even cost of `FR_REV1 h=1`.
3. The **net** Sharpe of the five design-best-by-net-t cells
   (`BETA_INSTAB` h1/h3/h5, `SPREAD_LEVEL` h5/h3) — reported as-is, including negatives.

The full 84-cell held-out sweep is written to disk for completeness. **Its maximum is
NOT a result** and will not be quoted as one: picking from it would be a second search.
The theme verdict is already fixed by the design window.
