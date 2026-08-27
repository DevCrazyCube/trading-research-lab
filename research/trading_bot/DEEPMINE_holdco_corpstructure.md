# DEEPMINE — Holdco / corporate-structure relative value

**Date:** 2026-08-20
**Machine-readable result:** `research/trading_bot/DEEPMINE_holdco_corpstructure.json`
**Code:** `scripts/holdco_rv/{hc_universe,hc_fetch,hc_sweep,hc_report,hc_bridge}.py`
**Cache:** `research/data/holdco_cache/` (bars 2015-01-02..2026-08-18, ~330k daily bars, 165 symbols, 6 MB)

## Verdict

**The sub-family is noise.** 130 formula configurations were evaluated on the design window.
The expected maximum |t| under the null for 130 tries is `sqrt(2 ln 130) = 3.12` SE.
**The best design t across all 130 was 2.35.** Nothing cleared the bar — not one configuration,
in any of the four structural groups. Held-out numbers confirm it: the design-selected formula
collapses in three of four groups, and the fourth dies on a shortability screen.

No candidate is basket-ready.

## What was tested

Four structurally distinct groups, all with an explicit identical-claim or known-ratio link:

| grp | structure | pairs used (design / holdout) |
|---|---|---|
| **P** | paired-entity / dual-listed-company / holdco-of-one-asset — two listed lines that are the **same claim** with a stated (usually 1:1) exchange right | 7 / 4 — BIPC/BIP, BEPC/BEP, BAMR/BAM, BBL/BHP, RDS.A/RDS.B, UN/UL, PAGP/PAA |
| **H** | holdco or tracking stock whose dominant asset is a **listed** stake; ratio drifts, so estimated not asserted | 14 / 13 — Liberty complex (LBRDA/K–CHTR, LSXMA/K–SIRI, LTRPA–TRIP), DVMT/VMW, DELL/VMW, IAC/MTCH, IAC/ANGI, L/CNA, IEP/CVI, FMX/KOF, HRG/SPB, BN/BAM, NVST/DHR |
| **S** | post-spinoff parent/child **pair-RV** (the drift is already known dead) | 26 / 39 of 40 |
| **M** | stock-for-stock merger **deal-ratio spread** — target contractually convertible into a fixed number of acquirer shares | 24 / 9 of 34 deals |

Formula axes (one parameterised vectorised sweep, 66 s wall, <300 MB RSS):

- **spread measure** — z of log price ratio · z of cumulative *return* spread (no level anchor) ·
  z of rolling-OLS log-price residual (estimated hedge ratio) · **level vs the contractual ratio** (P/M only)
- **z window** 60 / 125 / 250 · **entry** 1.5 / 2.0 / 2.5σ (or 0.5 / 1 / 2 / 4 % for the deal spread)
- **exit** full-cross (0σ) / 0.5σ · **max hold** 5 / 20 / 60 / 250 sessions
- **hedge** dollar-neutral / rolling-beta-neutral · **conditioner** none / low-vol regime / high-vol regime / DV > $10M

Conventions: signal on **raw** closes (levels point-in-time), P&L on **adjusted** closes,
fill at the **next** session's close (no same-bar fill). Costs = 2 crossings per leg ×
Corwin-Schultz half-spread measured per symbol per window + SEC s31 0.278 bp per sale +
borrow on the short leg pro-rata (T6/T7/M0). Borrow 0.33 %/yr ETB and 10.28 %/yr HTB, both
from `B22G_BORROW_COST`. A one-session |Δlog ratio| > 0.15 is treated as a corporate action:
the contractual anchor is re-scaled and any open position abandoned without booking P&L.

## Full result distribution

| window | min | p10 | p25 | median | p75 | p90 | max | n t>0 | n t>2 | **n t>3.12** |
|---|---|---|---|---|---|---|---|---|---|---|
| design  | −2.75 | −1.28 | −0.60 | **+0.12** | +0.99 | +2.01 | **+2.35** | 68/130 | 13 | **0** |
| holdout | −2.89 | −1.85 | −1.20 | −0.17 | +1.06 | +1.37 | +3.21 | 58/130 | 4 | 1 |

Design best per group: P 2.35 · M 2.17 · S 2.10 · H 1.43. A distribution centred on zero with a
maximum below the multiple-comparison bar is exactly what a null looks like.

## Design → held-out bridge (selection made on design only)

| grp | design-selected formula | design net/t/SR | **held-out net/t/SR** |
|---|---|---|---|
| P | `ret/L60/K2.5σ/E0.5σ/MH20/dollar` | +80.4 bp, t 2.35, SR 0.96 (n=71) | **+13.2 bp, t 0.26, SR 0.12** (n=46) |
| H | `z/L125/K2.0σ/E0.5σ/MH60/dollar` | +109.9 bp, t 1.43, SR 0.59 (n=170) | **+151.9 bp, t 1.29, SR 0.60** (n=124) |
| S | `ret/L250/K2.0σ/E0.5σ/MH20/dollar` | +168.4 bp, t 2.10, SR 0.86 (n=177) | **−8.3 bp, t −0.19, SR −0.09** (n=521) |
| M | `deal/K0.5%/E0.0%/MH250` | +190.5 bp, t 2.17, SR 0.95 (n=49) | **−558.9 bp, t −1.33, SR −0.75** (n=13) |

Family best on design is P at t 2.35 (bar 3.12); its held-out number is +13 bp/trade at SR 0.12.

**The holdout's one above-bar reading is holdout mining, not confirmation.** `H ret/L60/K2.5`
posts t 3.21 out of sample — but on the design window group H produced the four *worst* t-stats
in the entire sweep (−2.75, −2.57 is S, −2.24, −1.82). Selecting it would be selecting on the
held-out data, which is the thing this protocol exists to prevent.

## Two robustness checks that kill the survivors

**1. Shortability screen (T6-style screened universe).** Alpaca's asset records show `BIP`,
`IEP`, `LTRPA`, `UN` and `AMTD` are not shortable. In group H, **10 of 170 design trades (6 %)
require shorting IEP or LTRPA and carry 68 % of the group's design P&L.** Removing the trades
whose short leg is unborrowable:

| | unscreened | screened |
|---|---|---|
| H design | +109.9 bp, t 1.43, SR 0.59 | **+36.8 bp, t 0.50, SR 0.20** |
| H holdout | +151.9 bp, t 1.29, SR 0.60 | +113.1 bp, t 0.96, SR 0.45 |
| P design | +80.4 bp, t 2.35, SR 0.96 | +88.9 bp, t 2.39, SR 0.98 |
| P holdout | +13.2 bp, t 0.26, SR 0.12 | +51.9 bp, t 1.03, SR 0.48 |

Group H — the only group that *rose* out of sample — loses two thirds of its design edge the
moment the short leg has to be borrowable. This is the same failure mode that took dual-class
down to −45 bp.

**2. Borrow at the measured HTB rate (10.28 %/yr).** Three of four groups go negative on both
windows: P design +26.8 bp / holdout −39.3 bp; H −19.0 / +3.4; S +93.6 / −84.7; M −122.8 / −1089.3.

**Concentration.** Every group's design P&L rests on 3–4 pairs, several on literally three
trades: P is 42 % PAGP/PAA plus 35 % from three BEPC/BEP trades; H is 41 % IEP/CVI plus 30 %
LTRPA/TRIP; S is 26 % HLT/PK plus 20 % from three HON/REZI trades; M's four largest
cash-and-stock deals are 56 % of the total.

## Where free data is the binding constraint — honestly

**What free data unexpectedly *does* give.** Alpaca's SIP free tier serves daily bars for
**delisted** tickers back to 2016-01-04. That is what made groups P, H and M testable at all:
DVMT, VMW, XLNX, BBL, RDS.A/B, UN, BAMR, CXO, RTN, UTX, CELG, ETFC, MXIM, PXD, HES, PACW, CIT,
UMPQ all resolve. This is a reusable finding for any future delisted-universe work.

**What it does not give — in order of how much it hurt:**

1. **Point-in-time holdco constituent ratios.** Liberty Broadband's CHTR-per-share, Liberty
   SiriusXM's SIRI-per-share, Loews' CNA stake and IEP's CVI stake all drift with buybacks and
   issuance, and there is no free point-in-time series. Group H therefore had to use an
   *estimated* ratio (rolling z / rolling OLS), which **downgrades it from an identical-claim
   trade to an ordinary statistical pair** — and an ordinary statistical pair is precisely the
   thing this programme has already killed eight times. This is the single biggest binding
   constraint in the sub-family, and it is the reason the "holdco vs sum-of-listed-parts"
   trade as literally specified could not be run.
2. **Holdcos with unlisted parts** (FWONA, BATRA, GLIBA, QRTEA) need a NAV/sum-of-parts series
   that does not exist free. Excluded entirely.
3. **A survivorship-free merger-deal universe.** Group M's 34 deals come from recall, and recall
   is overwhelmingly of deals that *closed*. There is no free machine-readable universe of
   announced US stock-for-stock deals with exchange ratios. **The design-window group-M number
   is an upper bound, not an estimate** — the loss tail (broken deals) is structurally absent
   from the sample. Its held-out number (−559 bp) is the honest one and it is negative anyway.
4. **Historical borrow rates.** B22G could only obtain a same-day IBKR snapshot; 0.33 % / 10.28 %
   are applied as constants across ten years.
5. **ADR↔ordinary and non-US mappings.** Prosus/Tencent, SoftBank/Alibaba, Exor/Ferrari-Stellantis
   are not on the free US tape. That international-holdco branch is **untested**, not disproven.

## Data-hygiene traps found (reusable)

Alpaca serves a series **by ticker** and silently **stitches successive occupants**, sometimes
carrying the previous occupant's last price forward flat. Verified by price level:

- `BBT` is **Beacon Financial**, not BB&T; `STI` is **Solidion Technology**, not SunTrust →
  the STI/BBT all-stock deal had to be dropped.
- `DOW` carries Dow Chemical's last close **flat** from 2017-08 to 2019-04-01, then becomes
  Dow Inc → the DD/DOW 1.282 deal had to be dropped, and the DD/DOW spin pair clipped.
- `LLL` = L3 stitched to L3Harris; `AMTD` = TD Ameritrade stitched to AMTD IDEA Group;
  `UN` = Unilever NV then, after a five-year hole, a leveraged UNH ETF.

Three guards now sit in `hc_sweep.series()` and should be reused by anything that touches
delisted US tickers: per-symbol validity windows verified against known price levels; gap
segmentation (>20 calendar-day hole = a different listing); stale-price drop (≥5 identical
consecutive raw closes). They removed 393 DOW, 574 LLL, 346 LTRPA and 333 AMTD sessions.

## What would change the answer

A point-in-time holdco constituent-ratio series; a survivorship-free announced-deal universe
with exchange ratios; a borrow-rate history. None is a parameter-tuning problem, so **no further
sweep of this family on free data is worth running.** All three are paid-data asks and belong in
`DATA_PURCHASE_SCOPE.md` if this branch is ever revisited.
