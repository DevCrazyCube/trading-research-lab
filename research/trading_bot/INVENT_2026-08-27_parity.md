# INVENT_2026-08-27 — put-call-parity implied carry on the free DoltHub panel: DEAD (honest zero), two durable facts

**Tick:** 2026-08-27 03:00 CEST, supervisor CHUNK B. **Prereg:** `INVENT_2026-08-27_parity_PREREG.md`
(sha256 `abb3c3f5…094bb`, written before any number). **Code:** `scripts/trading_bot/invent_0827_parity.py`.
**Raw:** `INVENT_2026-08-27_parity.json`. **Formulas:** 2 return formulas + 1 diagnostic + 1 data verdict.
**Survivors: 0. Basket action: NONE** (clock locked). **Held-out F1/F2 returns were NOT read** (design gate failed, §4).

## 1. Result table (design 2020-03-04 → 2023-06-28, 172 weekly cross-sections, 51 mega-caps)

| formula | pre-registered sign | weekly t | mean/wk | ann. Sharpe | placebo p99 | bar (t ≥ 2.5 & > p99) |
|---|---|---:|---:|---:|---:|---|
| **F1** executable (close t+1 → t+6), long LOW / short HIGH implied carry | + | **−2.43** | −25.3 bp | −1.33 | +24.1 bp | **FAIL** |
| F2 same-print (close t → t+5), diagnostic only | + | −2.48 | −24.8 bp | −1.37 | +22.4 bp | FAIL (cannot promote anyway) |

**F1 is dead on its own pre-registered sign.** The wrong-sign magnitude (|t| 2.43, just under the bar) is the
sign-flip trap the programme has met before (`DOLT_OPTIONS.md` PUT_SLOPE: held-out +2.07 vs design −0.89). A
post-hoc "long HIGH implied carry" object is **not** admitted: no ex-ante mechanism exists for expensive-to-borrow
names *outperforming* (the only published channel says the opposite), the asynchrony channel (§2) would make it a
late-day-continuation microstructure object — a family already closed by `INVENT_0825_MASTER` — and a flipped
+2.43 would still fail the 2.5 bar. The held-out window (159 weeks) stays unread for returns; it is NOT to be used
as a design window for a flipped sign.

F2 ≈ F1 (−2.48 vs −2.43): moving the fill one session off the signal's own print changes nothing, so whatever the
book is, it is not a same-print artifact — it is simply noise with a negative draw.

## 2. F3 — the EOD option snapshot is stamped BEFORE the stock close, and increasingly so (durable, panel-level)

Pooled regression of `c_res` on the snapshot-day open→close stock return:

| window | slope | t | R² | n |
|---|---:|---:|---:|---:|
| design 2020–23H1 | +0.081 | **5.2** | 0.003 | 8,306 |
| held-out 2023H2–26 | +0.322 | **14.8** | 0.027 | 7,947 |

A positive slope is exactly what a stale (earlier-than-close) option quote produces: `F` carries an earlier `S`, so
`c_res = r − ln(F/S)/T` rises with the late-day move. The slope quadrupled post-2023 → the DoltHub snapshot's lag
behind the 16:00 print has *grown*. R² is small (the variance of `c_res` is mostly quote noise, §3) but the sign
and t are unambiguous. **Implication:** this converts the T35 "Clause 2 — entry marks only, never vol-vs-realised"
caveat from a suspicion into a measured property of the source. It does **not** touch T35/T36 (the December read
uses the forward-collected T31/T33 panels, not Dolt); it does say that *any* future Dolt-based object that
compares the option snapshot to the same-day stock close inherits a measurable, growing asynchrony.

## 3. D — the free panel CANNOT measure borrow (data-acquisition verdict)

| window | median cross-sectional IQR of `c_res` | median quote-noise floor `hw/(S·T)` | ratio | verdict (≥ 2 needed) |
|---|---:|---:|---:|---|
| design | 2.08 %/yr | 1.45 %/yr | 1.44 | **not measurable** |
| held-out | 2.11 %/yr | 1.51 %/yr | 1.40 | **not measurable** |

The cross-sectional dispersion of implied dividend-plus-borrow across 51 mega-caps is ~2 %/yr, while the bid/ask
band of the `C−P` synthetic alone is worth ~1.5 %/yr — the two are the same order. Median implied carry level
0.3 %/yr (design) → 0.7 %/yr (held-out), i.e. ≈ dividend yield, consistent with borrow ≈ 0 on general-collateral
names. **The 2026-08-22 ranking stands: a borrow-availability / lending-fee feed remains a PAID ask; the free
options panel is not a substitute, even on the most liquid names** (and it has no chains at all for the preferred
series where the borrow question actually bites).

## 4. Dead-ledger additions (do not re-propose)
- **Parity-implied-carry cross-section (long low / short high implied dividend-plus-borrow), weekly, mega-cap,
  free EOD chains** — design t −2.43 on the pre-registered sign, fails t and placebo; dead. Sign-flipped variant
  explicitly NOT admitted (no mechanism; would still fail the bar; family closed).
- **Options-implied borrow as a free borrow-cost proxy** — dispersion 1.4× the quote-noise floor; not measurable.
- **Any Dolt-panel object comparing the option snapshot to the same-day stock close** — stamp asynchrony
  measured (t 5 → 15, slope growing); Clause-2 async-clock artifact by construction.

## 5. Discipline
Prereg hashed before any read; sign, bars, split, cost and kill fixed in advance; held-out returns gated in code
and not read; no network; no basket change; no orders; no commit.
