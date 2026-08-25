# INVENT_0825 — OPEN-DRIVE / CLOSE-DRIVE MICROSTRUCTURE — PRE-REGISTRATION

**Written before any design statistic exists.** Research only, cached/free data, no orders.

---

## 0. Standing hazard: this theme is 60–80% already dead

`INVENT_0823_intramicro.md` scored **28** low-turnover intraday formulas and returned NOISE ON
GROSS (best gross +1.34 vs a +1.40 best-of-28 bar; 0 of 28 beat the gross bar). Its families
already cover three of the four bullets in this brief:

| brief bullet | already killed by 0823 |
|---|---|
| opening-30min drive continuation vs reversal | family **A** (5 formulas), best gross +0.60 |
| last-30min "close drive" direction | families **F/G** (6 formulas), best gross +1.34, gap-test fired |
| first-hour range as a signal | family **D** ORB (4 formulas), best gross +0.23 |
| gap-and-go vs gap-fade conditioned on the opening auction | **NOT TESTED** |

Also dead nearby: `SWEEP_intraday_rv` (98 configs, friction), B22D/B22E index intraday momentum
(Gao et al., dead OOS), auction-imbalance (died on ρ1). T3 owns the close→open overnight leg, so
**every formula here is strictly within one session** and cannot rediscover T3.

Therefore this round is pre-registered as a **disjointness sweep**: 26 formulas, none of which is
a re-parameterisation of an 0823 config. Three genuinely new instruments carry it:

1. **the official opening-auction print** (`t3_cache/auctions.json.gz`, 3.62M symbol-days,
   2016–2026) — 0823's Panel B never used it as a signal, only `p29/po` as a drive;
2. **path efficiency / choppiness of the first hour** — a shape statistic, not a level or a range;
3. **the opening-print dislocation** `open / VWAP(first 5-min bar) − 1`.

If those three are empty too, the theme closes.

---

## 1. Panels (both pre-existing caches, nothing re-downloaded)

**Panel A — 5-minute cube**, `research/data/im0823_cache/cube.npz`:
(1410 days × 78 slots × 132 symbols) o/h/l/c/vwap/dollar-volume/trade-count, Alpaca SIP,
`adjustment=all`, RTH, 2021-01-04 → 2026-08-14. Universes `MEGA` (34 single names) and
`LIQETF` (49 unlevered non-same-claim ETFs). **Survivorship-biased** (Alpaca serves today's
symbols); no formula may filter on a price level.

**Panel B — point-in-time top-500 auction rail**, `research/data/auc0822_cache/panel.npz`:
(2669 days × 1611 symbols) official open `po`, official close `pc`, 15:29 / 15:49 / 15:59 prints,
corporate-action flag `ca`, point-in-time membership `in_uni`, trailing ADV. 2016-01-04 →
2026-08-14. Prices are RAW/unadjusted, so **the only cross-session quantity ever computed is the
overnight gap `po[d]/pc[d−1] − 1`, and it is set to NaN whenever `ca[d]` is true.** Everything else
is within one session.

## 2. Windows (frozen now)

- **DESIGN** 2021-01-04 → 2024-12-31 (both panels, so one pooled best-of-N null is valid).
- **HELD OUT** 2025-01-02 → 2026-08-14. Untouched until the shortlist is committed.
- **PRE-SAMPLE** (Panel B only, declared in advance, **cannot promote anything, can only kill**)
  2016-01-04 → 2020-12-31.

**Disclosed contamination:** 0823 read the 2025–2026 held-out window for exactly four named
configs (`E4_PDPOC_MAGNET`, `A5_DRIVE_EX_GAP`, `F2_LD_REV`, `G3_LD500_CONT_TOP150`). None of the
26 formulas below is any of those four, and none is a monotone re-parameterisation of one. The
window is therefore not virgin for the *theme*, and that is stated rather than hidden.

## 3. Execution rails — the anti-bounce discipline (lesson 3)

Panel A entry is the **VWAP of bar s+1**; the signal only observes bars `0..s`, so signal and fill
never share a print. Exit is the **VWAP of bar 77**, unconditional, so the exit carries no signal.

Panel B entry is the **15:49 print** (signal observes at most through the 15:29 print and the
opening auction); exit is the **closing auction**, charged 0 bp of spread (M0 measured the official
print on 99.96% of top-500 symbol-days) but still charged the 0.15 bp regulatory fee.

**One-bar-gap re-entry gate (the ρ1 analogue on a bar panel).** Every config is re-run with the
fill pushed one slot later — Panel A bar `s+2`, Panel B the 15:59 print. A config is **disqualified
as a bounce artefact, whatever its primary number**, unless

> gap-fill net Sharpe ≥ 0.5 × primary net Sharpe **and** gap-fill net Sharpe > 0.

The 0823 harness self-test proved this gate can see a planted one-bar artefact (+7.84 primary →
+1.53 gap). The same gate code is reused unchanged.

## 4. Costs

0.5 / 1.0 / 2.0 / 2.5 bp per side on |Δw|, **headline 1.0 bp**, plus 0.15 bp per unit turnover for
SEC 31 + FINRA TAF. Panel B's exit pays fee only. Repo-measured liquid-name close half-spread is
1.13 bp (T3, 19,835 symbol-days); Dyhrberg et al. (JFE 168, 2025) put the liquid retail taker at
2.5 bp before price improvement. Borrow = 0 and that is exact: every config is flat at every close.

## 5. Both nulls

- **Null 1 (operative, family-wise):** stationary block bootstrap, block = 5 sessions, 2000
  resamples, of each config's demeaned daily PnL, **drawing the same day indices for every config**
  so the sweep's internal correlation survives. The bar is the **p95 of the best-of-26**. Reported
  on gross and on net@1.0bp. The analytic √(2 ln N) is reported only as a cross-check and is known
  to understate.
- **Null 2 (per-config, mechanism):** ADV-decile signal permutation — symbols bucketed into ADV
  deciles *within each day*, score permuted *within* buckets. 500 draws. Run on **GROSS**
  (0823 §7.4: running it on net is mis-specified). Rotate-the-returns is not used.

## 6. Promotion rule (all four must hold)

1. design **GROSS** Sharpe > the best-of-26 bootstrap p95 on gross; **and**
2. passes the one-bar-gap gate; **and**
3. per-config ADV-permutation p < 0.05 on gross; **and**
4. held-out **net @ 1.0 bp** > 0.

Anything short of all four is reported as noise. A survivor is a **PROPOSAL in the master doc
only** — the basket forward clock is LOCKED and nothing here is added to the frozen basket.

## 7. The 26 formulas (frozen before any number)

**Panel A — path shape (new instrument: efficiency / choppiness)**
| # | name | score | s |
|---|---|---|---|
| 1 | `PA_ER_DRIVE_CONT` | r60 × ER | 11 |
| 2 | `PA_ER_DRIVE_FADE` | −r60 × ER | 11 |
| 3 | `PA_CHOP_DRIVE_FADE` | −r60 × chop | 11 |
| 4 | `PA_ER_HI_CONT` | r60 · 1{ER above the day's cross-sectional median} | 11 |

ER = |r60| / Σ|5-min bar returns, bars 0..11|; chop = fraction of sign flips among those 12 bars.

**Panel A — range-scaled drive (range as a scaler, not a breakout level)**
| 5 | `PA_RCOMP_DRIVE_CONT` | r60 / rr | 11 |
| 6 | `PA_REXP_DRIVE_FADE` | −r60 × rr | 11 |
| 7 | `PA_H1LOC_FADE` | −(location of price in the first-hour range − ½) | 11 |
| 8 | `PA_RCOMP_DRIVE_CONT_ETF` | r60 / rr, LIQETF | 11 |

rr = first-hour (high−low)/open ÷ its own trailing-20-day median.

**Panel A — opening-print dislocation (new instrument)**
| 9 | `PA_ODISL_FADE` | −(open / VWAP(bar 0) − 1) | 1 |
| 10 | `PA_ODISL_CONT` | +(open / VWAP(bar 0) − 1) | 1 |
| 11 | `PA_ODISL_X_GAP` | −(open / VWAP(bar 0) − 1) × sign(gap) | 1 |

**Panel A — open drive → close drive (the brief's headline question, new hold)**
| 12 | `PA_OD30_CD_CONT` | r30 | 70 |
| 13 | `PA_OD30_CD_FADE` | −r30 | 70 |
| 14 | `PA_GAP_CD_FADE` | −gap_z | 70 |

**Panel B — gap conditioned on the opening auction (the untested bullet)**
| 15 | `PB_GAPZ_FADE` | −gap/σ60(gap) |
| 16 | `PB_GAPZ_GO` | +gap/σ60(gap) |
| 17 | `PB_IDIOGAP_FADE` | −(gap − cross-sectional mean gap)/σ60(gap) |
| 18 | `PB_GAPGO_CONFIRMED` | gap_z where sign(drive)=sign(gap), else 0 |
| 19 | `PB_GAPFADE_UNCONF` | −gap_z where sign(drive)≠sign(gap), else 0 |
| 20 | `PB_TOTMOVE_FADE` | −(gap_z + drive_z) |
| 21 | `PB_GAPZ_FADE_T150` | −gap_z, top-150 ADV only |

**Panel B — vol-scaled drive (0823 only tested the RAW-sign drive on this panel)**
| 22 | `PB_DRIVEZ_FADE` | −drive/σ60(drive) |
| 23 | `PB_DRIVEZ_GO` | +drive/σ60(drive) |
| 24 | `PB_DRIVE_EXMKT_FADE` | −(drive − cross-sectional mean drive)/σ60(drive) |
| 25 | `PB_DRIVE_CONF_FADE` | −drive_z where sign(gap)=sign(drive), else 0 |
| 26 | `PB_GAPDRIVE_CROSS` | −gap_z × drive_z |

drive = p29/po − 1; gap = po/pc[−1] − 1 (NaN on corporate-action days); σ60 = trailing 60-session
standard deviation, strictly excluding the current session.

All weights are cross-sectionally demeaned (dollar-neutral) and L1-normalised to gross 1.0.
Minimum 10 valid names (Panel A) / 20 (Panel B) per day or the day is skipped.

---

**Nothing in this file may be edited after the first design number is produced.**
