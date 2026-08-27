# UK / EUROPEAN INVESTMENT TRUSTS — does the T12 CEF discount-level edge extend?

**Date:** 2026-08-24 · **Author:** research agent · **Scope:** data recon + verdict for extending the
programme's one bar-clearing survivor (T12-S2, CEF discount-LEVEL tilt, held-out Sharpe 2.35) to
UK/European closed-end funds ("investment trusts", ITs). **Research only. No orders, no accounts, no
money, no git commit.** Every fetch below was a small verification fetch; no bulk crawl was launched.

---

## 0. TL;DR — VERDICT: **DATA-GATED. Cannot be scored REAL or NOT-REAL on free small-fetch data.**

The *structural* case is the strongest of any untried direction in the programme — it genuinely
extends the one proven winner rather than hunting a new mechanism, and every structural precondition
the T12 edge needs is present in the UK IT universe (large, dispersed, wide discounts, a published NAV
tether). **But the tether itself — multi-year per-trust NAV history — is not freely obtainable at
scale.** The clean machine-readable source (CEFData.com, the direct UK analogue of the CEFConnect feed
T12 rode) is **commercial only**; the free legal source (per-trust daily RNS "Net Asset Value(s)"
announcements) exists and parses, but recovering a ≥50-trust / multi-year panel from it is a
multi-day detached scrape of tens of thousands of *heterogeneously-formatted* announcements, with
exactly the point-in-time-NAV / parse-defect risk that the T12 write-up already flags as its single
biggest unfalsifiable weakness — made worse here, not better.

So this is another instance of the programme's own **free-data convexity wall** (MEMORY:
"sizeable+survivable retail chart edge isn't findable on FREE data; escape = forward-collect … pay for
data, or pivot") — but with an unusually strong prior, because it extends T12 instead of starting cold.
It therefore is the **best candidate in the corpus to justify a *small* paid-data spend or a
forward-collection job** — and both of those are owner gates (spend / time), not a research call I can
close by myself. I did **not** fabricate a backtest on data I could not stand behind.

---

## 1. THE STRUCTURAL CASE (why this was worth checking) — CONFIRMED PRESENT

UK investment trusts are closed-end funds in the exact T12 sense: fixed share count, a published NAV,
and a market price that floats to a discount/premium. Verified structural facts:

| precondition T12 needs | US CEF (T12) | UK IT — measured this session |
|---|---|---|
| Large universe | ~360 funds (CEFConnect snapshot) | **~400 trusts** ("AIC universe"); CEFData tracks **290+** FTSE-listed CEFs |
| Published NAV tether | CEFConnect daily NAV | **Daily NAV published via LSE RNS** ("Net Asset Value(s)") — the timestamped *legal* source |
| Dispersed / wide discounts | decile spread is the signal | **Average IT discount 9.6%** (Aug-2026, *narrowest since 2022*, so historically far wider); wides run **>20% to 77%** (Macau Property Opps 77%, Tetragon 70%) — dispersion is large and fat-tailed |
| Plausibly *less* arbitraged | the thesis | Directionally supported — smaller, more retail-held, less quant coverage than US CEFs; but **unmeasured** without the panel |

The mechanism (discount convergence to a published NAV), the universe size, and the discount
dispersion are all present and if anything richer than the US CEF space. **The thesis' structural half
holds.** What is missing is the data to test the empirical half.

---

## 2. DATA RECON — the make-or-break. Honest situation.

### 2a. SHARE PRICE — **FREE, deep, trivial. ✓**
Yahoo `v8/finance/chart/{TICKER.L}` returns daily OHLCV in GBp for LSE tickers, no key. Verified live:
- `SMT.L` (Scottish Mortgage), `FCIT.L` (F&C) → `firstTradeDate` epoch **−31,597,200** (i.e. 1969);
  `TMPL.L` (Temple Bar) → **−63,388,800** (1967). Decades of daily price history, free.
- This is the *tradeable* leg and it is a non-issue. The problem is entirely the NAV leg.

### 2b. NAV / DISCOUNT HISTORY AT SCALE — **NOT freely obtainable. This is the wall.**

Every candidate source, probed live:

| source | what it has | free machine access? | verdict |
|---|---|---|---|
| **CEFData.com** (cefadvisors) | Daily close, **last published NAV**, premium/discount, total-return NAV & price series **back to 1990**, for **290+ London CEFs** — the *direct UK analogue of CEFConnect* | **No.** No public API; site behind AWS-WAF captcha; access is a **paid tier-priced feed** (XLSX/CSV or API) — "email sales@cefadvisors.com for a sample/quote" | **PAID — the clean path, and it costs money** |
| **AIC** (theaic.co.uk find-&-compare) | Current NAV/discount + charts per trust; 53-yr *average*-discount history | **No.** Pure JS app, Morningstar-sourced, **redistribution licence-restricted** ("prepared by Morningstar … for information purposes only"); static HTML exposes **zero** data/JSON endpoints (only a reCAPTCHA script). No bulk/Excel by their own statement | **Gated (Morningstar licence)** |
| **Morningstar UK** (tools/util endpoints) | Per-security NAV timeseries | **No.** Autocomplete + timeseries endpoints returned empty / blocked to a plain client (JS/cookie/apikey-gated); licence-restricted regardless | **Gated** |
| **Yahoo quoteSummary** | price modules | **No NAV field** for UK ITs (unlike US CEFs/ETFs). No companion "-NAV" instrument exists (search for "Scottish Mortgage NAV" → 0 quotes) | **No NAV** |
| **LSE RNS "Net Asset Value(s)"** (via investegate) | The **primary legal daily NAV** — one announcement per trust per trading day | **Free but unstructured.** Verified: SMT's announcement list carries the NAV RNS stream; a single announcement parses (e.g. NAV/share **1430.89 / 1464.88** pence recovered from the 23-Jul-2026 print) | **FREE — but a heavy, fragile crawl (see §3)** |
| **ii.co.uk "Discount Delver"** | Weekly free "10 cheapest trusts" snapshot | Free | **Snapshot only, top-10, no history** |

**Bottom line:** current-snapshot discounts are free (AIC UI, Discount Delver); **multi-year per-trust
NAV history — the panel a freeze-then-test requires — is behind either a paywall (CEFData/Morningstar)
or a large RNS scrape.** There is no free, clean, bulk NAV-history source equivalent to the CEFConnect
`/api/v3/pricinghistory` feed that made T12 cheap to run.

---

## 3. THREE PATHS TO THE PANEL (none is a "free small fetch")

**A. Buy the history now — CEFData.com or Morningstar Direct.**
CEFData is the on-the-nose UK CEFConnect analogue: daily price + last-published NAV + discount for 290+
London CEFs back to 1990, delivered as CSV/API. Price is a bespoke quote (not published); a research-
grade feed at this scope is plausibly low-hundreds to low-thousands USD/yr. **This is a spend gate → owner.**
If bought, the T12 harness (`scripts/t12_evaluate.py`) transfers almost verbatim: swap the CEFConnect
loader for the CEFData panel, keep the discount-LEVEL decile tilt, weekly rebalance, H=4 hold, the
design/held-out split, the ρ1(Δspread) gate, the size-matched decile-label placebo null, DSR at the
declared trial count, and honest costs (see §4). Test would run same-day.

**B. Backfill by scraping RNS — free, but engineering-heavy and PIT-fragile.**
For ~50 trusts × ~4 years ≈ **50,000 announcement pages** to enumerate (paginated), fetch, and parse.
Must be a **detached** job (not launched here — beyond this task's free-small-fetch limit, and correctly
so). Two real hazards: (i) **heterogeneous formats** — each trust lays out its NAV RNS differently
(cum- vs ex-income, capital-only, sub-fund NAVs, comma vs pence formatting), so the parser carries
material defect risk; (ii) a NAV parse error feeds *straight* into the discount signal, which is exactly
the **point-in-time-NAV / restatement risk the T12 write-up names as its #1 unfalsifiable weakness** —
and it would be worse here. Net: a *partial, noisy* panel at best. Not recommended as the first move.

**C. Forward-collect for free — the zero-dollar escape (the MEMORY-sanctioned move).**
Stand up a tiny **daily** detached job: one NAV RNS + one Yahoo price snapshot per trust. At ~400 trusts
that is ~400 small fetches/day — trivial, polite, keyless, and the RNS is a **timestamped PIT source**,
so the forward panel is *cleaner* than CEFConnect's (no restatement ambiguity). Cost is **time, not
money**: T12's power came from 116 weekly obs; ~2 years of forward collection reaches parity. Mirrors the
programme's own documented escape ("forward-collect Deribit option quotes"). Zero dollars, zero spend
gate — but a 2-year clock. **This is the move I'd start now regardless of the buy decision**, because it
is free and compounding.

---

## 4. EXECUTABILITY — even with data, the UK trade is *harder* than the US CEF trade

Flagged now so the owner prices it before any spend, mirroring T12's honest-cost discipline:

- **Stamp duty:** UK **0.5% (50 bp) reserve tax on every buy** of IT shares. T12's whole held-out edge
  is +13.4 bp/week at 0.42 turnover; a 50 bp buy-side tax is **~3–4× the entire weekly gross** unless
  turnover is cut hard (longer hold, wider decile bands) — this alone could kill the naive weekly form.
  A long-hold / low-turnover variant is mandatory, not optional.
- **Spreads:** UK IT half-spreads are wider than large US CEFs, especially the small/deep-discount names
  that carry the signal — the T12 friction (11.53 bp median half-spread) is a *floor*, likely higher here.
- **Borrow (short leg):** UK ITs are frequently **hard or impossible to borrow** (small, retail-held) —
  the same wall that killed the T9 fresh-stub short and the dual-class thin-leg short at this broker
  (`shortable = False`, not merely expensive). The **long-only-vs-market-hedge** version (long widest-
  discount basket vs a FTSE All-Share / index-future hedge) is therefore the realistic default, and it
  gives up the premium-fund short leg that T12 showed carries *slightly more* than half the edge.
- **Net:** even a REAL signal would face stamp duty + wider spreads + a broken short leg. The honest
  prior is that the UK version is **structurally more likely to be "real but not executable"** than the
  US CEF version — the borrow/tax wall is the same family of gate that has blocked several corpse revivals.

---

## 5. VERDICT

**Does the T12 CEF discount edge extend to UK investment trusts? → UNKNOWN, DATA-GATED.**

- **Not NOT-REAL:** every structural precondition is present and the discount dispersion is *larger* than
  the US space, so there is no structural reason to expect it to fail — the prior is genuinely favourable.
- **Not (yet) REAL:** the empirical test cannot be run on free small-fetch data. The NAV-history tether is
  paywalled (CEFData/Morningstar) or a fragile multi-day RNS scrape. I will not report a Sharpe I cannot
  stand behind.
- **Executability caveat stands regardless:** UK stamp duty (50 bp/buy), wider spreads, and a
  hard-to-borrow short leg mean that even a real signal is at serious risk of landing in the "real but not
  executable" bucket — the naive weekly form is almost certainly tax-dead, and a long-only-vs-hedge form
  is the only realistic expression.

**Recommendations (all owner gates — I proceed on none of them):**
1. **Start Path C (free forward-collection) now** — zero dollars, zero spend gate, compounding a clean PIT
   panel; the only downside is a ~2-year clock to power. Strongest risk-adjusted move.
2. **Consider Path A (buy CEFData/Morningstar history)** *only if* the owner wants an immediate answer and
   will authorise a small data spend — this is the fastest route to a verdict and the T12 harness ports
   almost unchanged. **Spend gate → owner.**
3. **Do not lead with Path B (RNS backfill scrape)** — free but engineering-heavy and PIT-defect-prone;
   at most a noisy corroborator, and it re-introduces exactly the NAV-integrity risk T12 flags as fatal.
4. **Do NOT propose an ACTIVE_UNSIZED basket leg** — there is no held-out net Sharpe to freeze. This
   direction is a *data acquisition* decision, not a freeze-ready edge.

---

## 6. WHAT WAS VERIFIED LIVE (audit trail)
- Yahoo `chart` GBp daily bars for SMT.L/FCIT.L/TMPL.L, firstTradeDate 1967–1969 → **price leg free & deep**.
- Yahoo `search`/`quoteSummary` → **no NAV instrument / no NAV field** for UK ITs.
- theaic.co.uk find-&-compare → JS app, Morningstar-licensed, **no data endpoint in static HTML**.
- Morningstar UK autocomplete + component timeseries → **empty/blocked** to a plain client.
- cefdata.com/london-cef-page → 290+ London CEFs, NAV+discount **back to 1990**, **paid feed only**, WAF-gated.
- investegate SMT feed → daily **"Net Asset Value(s)"** RNS stream present; single announcement parsed
  (NAV/share 1430.89 / 1464.88 pence) → **RNS is a free, parseable, PIT source but a heavy heterogeneous scrape**.
- WebSearch → AIC average IT discount **9.6%** (Aug-2026, narrowest since 2022), wides **20–77%**; universe **~400 trusts**.

*No bulk download was launched. No order, account, purchase, or commit was made.*
