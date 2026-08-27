# T7 — pre-registration: ex-dividend drop-off, executed close-to-close in the auctions

**Frozen before any return, signal, portfolio or drop-off ratio was computed.** Written
2026-08-17. The only Alpaca calls made before this file existed were *structural* probes — does
the endpoint exist, what fields does it return — and two reads of files already on disk from the
T3 run. Both are listed in §10.

Candidate under test: **#2 in `EDGE_SHORTLIST.md`** (score 15/20), nominated in advance by
`T3_PREREGISTRATION.md` §8 as the successor if #1 died. #1 died (`T3_RESULT.md`, held-out
DSR 0.9379 against a threshold of 0.95 frozen first).

Harness: **T2**, `scripts/trading_bot/` — `stats.py` (DSR, permutation, moments, Sharpe,
drawdown, CAGR) and `costs.py` (the T6-corrected **per-side** cost model) are imported, not
copied. Collection reuses `scripts/t3_pressure_reversal.py` for the calendar, the asset pool,
the point-in-time monthly universe screen and the official auction prints; those are the same
verified objects T3 ran on, and reusing them is what makes this test cheap.

---

## 1. The claim, and its null

**Mechanism claimed.** On the ex-dividend date the price falls by **less than the dividend** on
average (Elton & Gruber 1970; shrunk but not eliminated after decimalisation per Graham, Michaely
& Roberts 2003). The residual is a **tax-clientele** effect — a constraint on who wants to hold a
dividend across the ex-date, not an information event — so attention does not compete it away.

**H1.** A position bought in the **official closing auction of the cum-day** and sold in the
**official closing auction of the ex-date**, market-hedged, earns a positive net total return:
the dividend received exceeds the market-adjusted price drop plus friction.

**H0 (the null actually tested).** The net (post-friction) mean daily return of the dollar-neutral
book — long the equal-weight basket of that day's ex-dividend names, short SPY — is **≤ 0**;
equivalently, the drop-off ratio is 1 and going ex-dividend carries no information about the
market-adjusted total return.

**The pairing is mandatory and it is the short SPY leg.** An unpaired long basket would be
dominated by the common equity drift, which is the exact error `FINDINGS.md` §5c records. The
equal-weight return of the same-day *non*-ex-dividend universe is reported beside every result as
a second, independent control.

**Why both legs are auction prints, and why that is the whole point of this candidate.** T3 died
with 6.8 bp of gross against 1.4 bp of *measured entry friction*, and its one spread-free variant
(D2, both legs in the auctions) had to commit before the 15:50 MOC cutoff and was t = 1.38. This
candidate has **no timing problem at all**: an ex-dividend date is published weeks in advance, so
an MOC order on the cum-day and an MOC order on the ex-date are both submittable long before
15:50. The modelled quoted spread is therefore genuinely zero on *both* sides rather than 1.4 bp
on one. §6 states what is charged instead, and what happens if that zero is wrong.

---

## 2. Universe — point in time, monthly, reused verbatim from T3

**Pool.** Every Alpaca `us_equity` asset with status `active` **or `inactive`**, listed on
NYSE / NASDAQ / AMEX / ARCA / BATS. Delisted names are in the pool by construction, so companies
that were acquired or failed after paying a dividend are not silently dropped.

**Screen**, computed from RAW monthly bars of month `m-1` and applied to month `m`:

| filter | value |
|---|---|
| month-end **raw** close | > $5.00 |
| dollar ADV (`vw × volume ÷ trading days in month`) | > $20 M |
| rank by that ADV, keep | **top 500** (or top 300 — a declared trial axis, §7) |

`adjustment='raw'` for both level filters, per `data.py`'s
`assert_levels_are_point_in_time()`. This is `t3_pressure_reversal.build_universe(top_n)` called
unchanged; the auction-print cache covers exactly this universe's union (1,648 symbols,
3,618,237 symbol-days, 2016-01-04 → 2026-08-14).

**Stated limitation, not a deviation.** The tax-clientele story predicts the *largest* residual in
high-yield names, and a top-500-ADV screen selects for size and liquidity rather than yield. This
test therefore measures the effect **where it is tradeable on the auction rail**, which is the
only place this programme could trade it, and it will under-state any effect that lives in
illiquid high-yield names. Recorded here rather than discovered afterwards.

---

## 3. Events

Every `cash_dividend` returned by `/v1/corporate-actions` for a universe symbol with
`ex_date` in [2016-01-04, 2026-08-14]. Fields used: `symbol`, `ex_date`, `rate`, `special`.

- **Cum-day** = the trading day immediately preceding `ex_date` in Alpaca's own calendar.
- Buying in the cum-day's closing auction makes the account a holder going into the ex-date, so
  the dividend `rate` per share is received. Selling at any time on the ex-date does not forfeit
  it.
- If a symbol has **several** cash dividends with the same `ex_date`, the rates are **summed**
  into one event.

## 4. The trade

For each surviving event on ex-date `t`:

```
r_stock(i,t) = ( P_close_auction(i, t) - P_close_auction(i, cum) + D(i) ) / P_close_auction(i, cum)
r_spy(t)     = ( P_close_auction(SPY, t) - P_close_auction(SPY, cum) ) / P_close_auction(SPY, cum)
```

`P_close_auction` is the **official closing auction print** from `/v2/stocks/auctions`, condition
code `6`, largest size if several — the same field and the same selection rule T3 used. Prices are
RAW, and `D` is the raw per-share rate, so the two are in the same units by construction.

**Portfolio, one observation per trading day that has at least one surviving event.** Dollar
neutral, gross exposure 100 %:

```
gross(t) = 0.5 * mean_i r_stock(i,t) - 0.5 * r_spy(t)
```

Equal weight across the day's events. Days with no event are **not** observations — the book is
flat and holds nothing.

**Holding period.** Exactly one session, cum-close to ex-close. Positions never overlap, so the
daily series is one independent-by-construction observation per day.

**No minimum event count.** A day with one event is an observation with one name in it. That is
what the strategy would actually hold, and imposing a minimum would be a choice with no
justification other than variance.

## 5. Exclusions — identical in the design and test periods

1. Event dropped if the **cum-day or ex-date official closing auction print is missing** for that
   symbol.
2. Event dropped if the symbol is **not in the universe of the cum-day's month AND of the
   ex-date's month**. Both screens are computed from strictly earlier months, so no value from
   either traded day touches the selection.
3. Event dropped if **any non-cash-dividend corporate action** (forward/reverse split, spin-off,
   merger, redemption, name change) has a recorded date equal to the cum-day or the ex-date for
   that symbol. Raw prices would otherwise show a mechanical gap. The T3 corporate-action date
   cache is the source.
4. Event dropped if `rate <= 0`, or if any of the four prices is non-positive.
5. Event dropped if `rate / P_close_auction(i, cum) > 0.20`. A 20 %-of-price distribution is a
   partial liquidation or a return of capital, not the effect under test.
6. **Whole day dropped** if SPY's closing auction print is missing on the cum-day or the ex-date.
7. **Whole day dropped** if SPY itself has a cash-dividend ex-date on the cum-day or the ex-date:
   a short SPY hedge held across SPY's own ex-date owes that dividend, and the hedge is not free
   there.
8. **Whole day dropped** if the exchange calendar shows an **early close** (≠ 16:00) on the cum-day
   or the ex-date.
9. Event dropped if the cum-day and the ex-date are not **consecutive** entries in Alpaca's
   trading calendar.

## 6. Costs — the T6-corrected PER-SIDE model, with the auction zero stated rather than inherited

`costs.py` is imported and a `CostModel` is constructed with **both** sides named explicitly. T6's
correction was that an unmeasured exit must never inherit the entry's number; here the entry and
the exit are the *same kind of object* — a single-price auction — and each says so in its own
component, with its own source string.

| component | charged | basis |
|---|---|---|
| `entry_half_spread` | **0 bp** | The cum-day **closing auction** is a single-price call: every participant clears at one price and there is no bid-ask to cross. T1 §2c verified `type=market, tif=cls` is accepted by the broker. |
| `exit_half_spread` | **0 bp** | The ex-date **closing auction**, same mechanism. **This zero is declared, not inherited** — it is the same fact about the same venue, stated separately so that a future change to one leg cannot silently move the other. |
| `entry_extra_slippage` / `exit_extra_slippage` | **0 bp** | Not a claim that impact is zero: a stated LOWER BOUND, swept by the stress ladder below. At $100 k against single-stock closing auctions clearing $28–130 M (T1 §2e) it is a tolerable omission and it is an omission all the same. |
| **regulatory pass-through, sale legs only** | **SEC §31 at 0.278 bp of sale notional + FINRA TAF at $0.000166/share sold** | The two sale legs are the stock sold at the ex-close and the **short sale** of SPY at the cum-close. Charged on 0.5 notional each. §31 is charged at **$27.80 per $1 M, the top of the 2016–2026 range**, in both periods — the fee is reset annually and tracking it exactly would flatter the earlier years. TAF is charged exactly, per share, from each leg's own price. **This is the friction the auction does not remove, and it is why the primary cost rung is not zero.** |
| commission | 0 | Alpaca and every zero-commission US retail broker, $0/share |
| borrow | **33 bp/yr** on the 50 % SPY short notional, per **calendar** day held | `costs.measured_borrow_annual("etb_general_collateral")` — B22G's own measured ETB general-collateral median, not the 30 bp default. SPY is easy to borrow. |

**Stress ladder, reported always, never a single cost number.** A half-spread `h` is charged on
**every one of the four legs** at rungs `0` (the auction rail as modelled), `0.5h`, `h`, `2h`,
`4h`, where `h` is **T3's own first-party measurement on this exact universe**: **1.13 bp**
(2016–2021) and **1.43 bp** (2022–2026), median quoted half-spread in the final second before the
close, ~20,000 symbol-days per period, `research/trading_bot/T3_HELDOUT_RESULT.json`. Plus the
B19P frictionless diagnostic (all costs zero, including the regulatory ones): *if it loses there,
no execution improvement can rescue it.*

**Assumption stated, not hidden.** T1's prerequisite measurement **M0 — do MOC orders actually
fill at the official closing print — has NOT been performed**, and this candidate rests on it
twice, once per leg, where T3 rested on it once. The `h` and `2h` rungs are the price of being
wrong about it.

## 7. Design phase — 2016-01-04 → 2021-12-31

The **only** configurations that will ever be run, and there are exactly **eight**:

| axis | values |
|---|---|
| yield filter (`rate / P_cum`) | all dividends, ≥ 0.50 % |
| universe size | top 500, top 300 |
| special dividends (`special` flag) | included, excluded |

2 × 2 × 2 = **8 trials. Declared here, before any of them is run.** The configuration with the
highest **net annualised Sharpe on the design period** is frozen — the same freezing rule T3 used.
The sample variance of the eight design-period per-observation Sharpes is the `sharpe_variance`
input to the deflation, which is the honest input `stats.sharpe_variance_from_trials` asks for.

No configuration outside this grid will be run for the verdict. If the grid is extended for any
reason, the extension is a new pre-registration and the trial count changes with it. **The
close-to-OPEN variant (cum-close → ex-date opening auction) is deliberately NOT in the grid** and
carries no verdict; if it is computed at all it is an exploratory diagnostic, labelled as one, run
only after the frozen verdict, exactly as T3's D1/D2 were.

## 8. Held-out test — 2022-01-03 → 2026-08-14

The single frozen configuration is run **once**. Reported:

- net mean per event-day, its t-statistic, annualised Sharpe, annualised return, max drawdown;
- the realised **drop-off ratio** `1 - (market-adjusted price change)/D`, the quantity the
  literature reports, in both periods;
- the **equal-weight non-ex-dividend control** on the same days (the second pairing);
- **DSR** (`stats.deflated_sharpe`) on the held-out net return series, `trials = 8` with the
  design-phase cross-trial Sharpe variance; sensitivity reported at `trials = 24`;
- **cross-sectional label permutation**, 10,000 shuffles, seed `20260817`. Within each day, the
  `k` real ex-dividend names are replaced by `k` names drawn without replacement from that same
  day's *non*-ex-dividend universe members that have both closing auction prints and no corporate
  action. Every permutation trades the same days, holds the same number of names, and faces the
  same market move; only **which stocks are labelled "went ex-dividend today"** changes. The
  pseudo-events have no dividend to add back, which is exactly H0: under a drop-off ratio of 1 an
  ex-dividend stock's *total* return is indistinguishable from an ordinary stock's price return.
  Add-one corrected. This is the instrument `FINDINGS.md` §5c prescribes for a label object;
- the T2 exposure-timing permutation (`stats.permutation_test`) as a **wiring check only** — this
  book is fully invested and dollar-neutral on every observation day, so its exposure is constant
  and permutes to itself, and p = 1.0 is the correct answer rather than evidence;
- the full stress ladder of §6 and the zero-cost diagnostic;
- a year-by-year net breakdown, so no single year can be carrying the result unnoticed.

## 9. Kill conditions — fixed in advance

**DEAD if ANY of the following holds on the held-out period:**

1. net mean per event-day **≤ 0** at the primary cost rung (auction spread zero, regulatory
   pass-through and borrow charged); **or**
2. label-permutation right-tail **p ≥ 0.05**; **or**
3. **DSR < 0.95** at `trials = 8`.

**SURVIVES** only if all three pass. Anything in between is reported as *not established*, which
is not a pass.

**And one further gate that is not statistical and cannot be waived by any backtest.** A taxable
US retail account receives the dividend as **ordinary income**, and a one-day hold can never meet
the 61-day qualified-dividend holding period of IRC §1(h)(11)(B)(iii). The after-tax arithmetic is
written up in the result document **whatever the statistical verdict is**, and the recommendation
distinguishes a taxable account from a tax-deferred one. It is an **owner call**, not mine, and it
is stated as one.

**If DEAD, a next candidate is nominated** from `EDGE_SHORTLIST.md` with the reason, in the result
document.

---

## 10. What was probed before this file was written

Structural only. No return, no signal, no portfolio, no drop-off ratio:

- one `/v1/corporate-actions` page for three symbols over two months, `types=cash_dividend`, to
  confirm the field names (`ex_date`, `rate`, `special`, `foreign`, `process_date`, `symbol`);
- two reads of files already on disk from the T3 run: `auctions.json.gz` (record count, symbol
  count, presence of SPY, presence of the `c` closing-print key) and `B22G_BORROW_COST.json`
  (the ETB general-collateral rate).

No price of any dividend-paying stock on any ex-date was read, and no return was computed, before
this file was written and hashed.

## 11. What this pre-registration does not claim

- It does not claim the auction rail is free. **M0 is unperformed** and §6's ladder exists for it.
  It rests on M0 twice, once per leg.
- It does not correct survivorship perfectly — Alpaca's inactive list is a partial record of what
  once listed, and a name that never appears in it is invisible to this test.
- It does not model queue position, partial fills, size-dependent impact, or the possibility that
  a closing-auction imbalance on a heavy ex-dividend date is itself informative.
- It does not model the dividend's **payment lag**: the cash arrives on the payable date, weeks
  later, and this test credits it on the ex-date. That flatters the strategy by the risk-free
  carry on the dividend over that lag — a few thousandths of a basis point at 2016–2026 rates on a
  0.6 % dividend, far below the resolution of anything measured here, and stated rather than
  omitted.
- **It does not settle the tax question.** It quantifies it. That is deliberate.
- It does not authorise execution of any kind. Real money remains owner-gated.
