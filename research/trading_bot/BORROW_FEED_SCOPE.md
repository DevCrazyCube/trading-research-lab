# BORROW_FEED_SCOPE — cheapest data to resolve the B01 preferred-RV borrow wall

**Date:** 2026-08-22
**Question:** What data tells us short-borrow *availability + rate* for US preferred shares,
and what is the cheapest (ideally free) way to get it, so we can answer:
*"are BOTH legs of ≥30 same-issuer preferred pairs shortable, and at what rate?"*
**Scope:** research/recommendation only. No purchases, no accounts, no payment, no git commit.

---

## TL;DR RECOMMENDATION

- **Cheapest source that answers the question: IBKR's public `usa.txt` short-availability file — FREE, no account.**
  Pipe-delimited `SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI`; `FEERATE` is the indicative
  borrow cost %/yr, `AVAILABLE` is shares on loan-desk. It is the *actual securities-lending* feed and
  it covers preferreds (IBKR is the deepest retail SLB desk). This is the right instrument.
- **Cost: FREE / $0.** No account, no key. Published for anyone.
- **Free-and-testable, with one access caveat:** the file is served over **FTP (port 21), which is
  firewalled from this agent sandbox** (connect timeout to `ftp3.interactivebrokers.com`, confirmed twice
  today; same wall B22G hit). It is **not** firewalled from a normal machine. So it is fetchable *now*
  either **from the owner's own network**, or as a **detached non-sandboxed background job** (the
  sanctioned pattern per the `no-network-crawls-in-agents` memory). Not a purchase decision — an access-path
  decision.
- **The existing Alpaca ETB feed is EXHAUSTED and cannot answer this.** It already produced the
  0/113-pairs verdict, and per B22G's own lesson its `shortable=False` means "this broker won't locate it,"
  not "unborrowable anywhere." It is structurally biased against preferreds (see §1a). Re-querying it
  yields nothing new.
- **BRUTALLY HONEST OUTCOME (§4): resolving borrow will NOT promote B01.** Borrow is the *first* wall,
  not the *only* one. The held-out net is +0.93 Sharpe, **t 1.48 (insignificant)**, and **dies at 2×
  spread**. That fragility is independent of borrow. A clean IBKR feed showing 30+ pairs both-legs-
  borrowable moves B01 from "0% executable" to "maybe executable at an insignificant, spread-fragile net" —
  it does not clear any bar. **Fetch the feed as free reusable infrastructure, not as a B01 rescue.**

---

## 0. WHAT THE PROGRAMME ALREADY HAS (sources traced)

**The B01 shortability verdict came from Alpaca.** `research/data/inv0822_tether/pref_flags.json.gz`
(508 symbols: 361 preferred series + 147 commons) is a `GET /v2/assets` snapshot — same endpoint,
same shape, same provenance as `research/data/t28_dualclass_cache/etb_flags_frozen.json`
(`"_source": "Alpaca /v2/assets live snapshot"`). `invent0822_preftether.py:53,127` reads
`pref_flags.json.gz`, takes `flags[sym]["shortable"]`, and forms `both_short = SHORT[i] and SHORT[j]`.

**So the dual-class L3 ETB screen and the B01 preferred screen are the SAME free feed: Alpaca
`/v2/assets`.** It is a status flag only — no rate.

**Measured on the actual cache (this session):**

| population | count | shortable at Alpaca |
|---|---|---|
| preferred series (`X.PRy`) | 361 | **34 (9.4%)** — all mega-bank (BAC/JPM/MS/GS/C/COF/DLR/NEE…) |
| commons | 147 | 135 (92%) |

The 34 shortable preferreds are exactly the names a broker lends freely; the other 327 are `False` +
`easy_to_borrow=False` in one block. That pattern is a **lending policy**, not a borrow-market
measurement. **B22G proved this distinction empirically:** of 11 Alpaca-HTB names with an IBKR rate,
**7 were borrowable at IBKR** (2.32–259.96%/yr) — expensive, not impossible.

**Borrow-cost anchor already established (B22G, `research/B22G_BORROW_COST.json`):** IBKR ETB indicative
fee **p50 0.33%/yr** (14 ETB names), HTB median 10.28%/yr. Alpaca's own `/v1/locates/quotes` rate
endpoint returns **403** for this key (no live/HTB entitlement) — **no free rate from Alpaca, confirmed.**

---

## 1. FREE ROUTES, cheapest first

### 1a. Existing Alpaca ETB feed — COVERS preferreds, but ANSWERS NO (and can't give a rate)
- **Coverage:** yes — 361 preferred series already fetched.
- **Verdict:** **exhausted.** It *is* the source of the 0/113 wall. It is a boolean, gives no rate,
  and reflects Alpaca declining to locate 327/361 preferreds. Its `False` is not a borrow-market fact.
- **Not the answer.** Reusing it just reproduces the wall.

### 1b. IBKR `usa.txt` short-availability file — THE ANSWER. FREE, no account. ★
- **What:** IBKR republishes its US securities-lending availability ~every 15 min. Pipe-delimited:
  `SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI`.
  `FEERATE` = indicative borrow fee %/yr; `AVAILABLE` = shares available (or `>10000000`).
- **Covers preferreds:** yes — it is IBKR's entire shortable US universe, and IBKR lends far more
  preferreds than Alpaca will. This is precisely the set Alpaca refuses. It is the correct instrument.
- **Cost:** **$0**, no key, no account (public `shortstock` login / anonymous).
- **Access caveat (the one real friction):** served over **FTP port 21**, which is **firewalled from
  this sandbox** — `ftp://ftp3.interactivebrokers.com/usa.txt` and `ftp://ftp.interactivebrokers.com/…`
  both connect-timeout here (confirmed today; identical to B22G). Mirrors: `ftp.`, `ftp2.`,
  `ftp3.interactivebrokers.com`. **Fetchable from any non-sandboxed machine** (owner's box, or a detached
  background job outside the request-timeout wall).
- **HTTPS alternative exists but the raw endpoint is not keyless-reachable from here:** the human tool
  `https://www.interactivebrokers.com/en/trading/ViewShortableStocks.php?cntry=usa` returns HTTP 200 but
  is a JS single-page app (widget `ndcdyn.interactivebrokers.com/cstools/ibslb/v3/`); the underlying data
  URL was not locatable without deeper crawling (out of policy in-agent). The FTP file is the clean route.
- **Exact fetch (run off the sandbox):**
  ```
  curl -s "ftp://shortstock@ftp3.interactivebrokers.com/usa.txt" -o usa.txt
  # (public 'shortstock' user, blank password; historically anonymous. Try ftp2/ftp if ftp3 refuses.)
  ```
  Then filter rows whose `SYM` is a preferred (contains ` PR`) and join to the B01 pair list.

### 1c. Reg SHO threshold lists / FINRA short-interest — FREE, but WRONG INSTRUMENT
- Nasdaq/NYSE/FINRA Reg-SHO threshold lists (fails-to-deliver) and FINRA bi-monthly short interest are
  free, but they report **fails / interest**, not **availability or a borrow rate**. They cannot say
  "both legs borrowable at rate X." Not fit for purpose.

### 1d. Alpaca borrow-rate API — FREE tier does NOT expose it
- `GET /v1/locates/quotes` = **403** without live/HTB entitlement (B22G, re-confirmed). `/v2/assets`
  gives the boolean only. No free rate from Alpaca.

### Republications (all IBKR data, all blocked or paid)
- **iborrowdesk.com** — free JSON per symbol, but **403 (Cloudflare)** to sandbox curl and WebFetch.
  Works from a real browser/IP; would give the owner the same IBKR numbers keyless if run off-sandbox.
- **shortinteresttracker.com** — 403. **ChartExchange** — bot-blocks after ~22 symbols (B22G).
  **fintel.io** — paid.

---

## 2. CHEAPEST PAID (only if the free FTP path is somehow refused)

Essentially **unnecessary** — the free file answers the question. If a hosted/keyed option is ever wanted:
- **Apify "IBKR Shortable Stocks Scraper"** — pay-per-run, small (single-digit $ per bulk pull), no IBKR
  account, re-serves the same `usa.txt` fields across 18 exchanges. This is the cheapest *paid* wrapper
  and it is a wrapper around the same free data.
- **IBKR paper/live account** — free to open; Client Portal SLB search + TWS API generic ticks 46/47
  give per-symbol availability & rate. **Out of scope (no accounts).**

No purchase is recommended. Nothing here approaches the €130 / $200–300 spends the owner has killed.

---

## 3. SYMBOLOGY CROSS-CHECK — messy but deterministic

| feed | format for BAC Series L pfd |
|---|---|
| Alpaca `pref_flags` (what B01 uses) | `BAC.PRL` (dot-PR) |
| IBKR `usa.txt` SYM (TWS local symbol) | `BAC PRL` (space-PR) |
| NYSE / common alt | `BAC-L`, `BAC PRB`↔`BAC-B` |

**Join rule:** `alpaca_sym.replace(".PR", " PR")` → IBKR SYM. A one-line transform, so the feeds *are*
matchable to the B01 pairs. **Residual risk:** a minority of series will still miss on join (IBKR root
variants, sub-series letters, or IBKR listing under a different local symbol), so the realised
both-legs-borrowable pair count must be measured against actual `usa.txt` rows, not assumed. Expect to
recover most, not all, of the 113 pairs. This matching cost is real but small and one-time.

---

## 4. HONEST EXPECTED OUTCOME — does resolving borrow promote B01? NO.

B01 held-out economics (from INVENT_0822_MASTER §3.1):
- net **+0.93 Sharpe, t 1.48**, +9.6 bp/wk, bootstrap P(>0)=0.92 → **~8% chance the true net is ≤ 0.**
- **dies at 2× the measured 17.5 bp half-spread → −0.98.**
- promotion guard the master itself set: needs **both legs shortable on ≥30 pairs AND realised
  half-spread ≤ 9 bp.**

Now overlay a *best-case* IBKR result (30+ pairs both-legs-borrowable at ETB ~0.33%/yr):
- **Borrow COST is negligible:** 0.33%/yr ≈ **0.63 bp/week**, trivial against a 9.6 bp/wk net. So if
  borrow *availability* clears, borrow *cost* barely dents the edge.
- **But availability was never the thing that would kill the P&L — the half-spread is.** The edge is
  already insignificant (t 1.48) at 1× spread and negative at 2×. Borrow is the *first* wall you hit;
  behind it stands the *same* spread wall that governs every RV finding in this programme.
- A t 1.48 net clears **neither** the cumulative programme bar (t ≈ 3.77) **nor** a standalone
  significance bar. Fixing borrow changes "0% executable" into "possibly executable at a net that is not
  statistically distinguishable from zero and halves under a realistic spread."

**Conclusion on B01 specifically: the edge is too marginal for the borrow feed to rescue it.** B01 should
stay a *characterised object*. Do **not** fetch data expecting a promotion.

**BUT the feed is worth fetching anyway — as free, reusable infrastructure, not as a B01 fix:**
1. It is **$0** and a one-time script.
2. It becomes the standing **both-legs-shortable pre-condition input** the master made mandatory for
   *all* future RV proposals (§4(e)/rec 4) — every future pair-book needs exactly this feed up front.
3. It re-opens the **microcap short tail of the 424B5 forced-flow family** (MASTER §5/§8), where Alpaca's
   refusal-to-lend was also mislabelled as unavailability.
4. It replaces B22G's bot-blocked, 25-of-100 partial IBKR pull with a complete, repeatable file.

So: **acquire the free IBKR `usa.txt` feed as programme infrastructure. Set the expectation that it does
NOT promote B01.** If the owner's only interest is B01, the honest answer is **skip it** — B01 is dead on
significance regardless of borrow.

---

## 5. DECISION REQUESTED OF THE OWNER

- **(a) Cheapest source:** IBKR public `usa.txt` short-availability file (SYM|…|FEERATE|AVAILABLE).
- **(b) Cost:** **FREE / $0.** No account, no key. (Cheapest paid fallback, unneeded: Apify scraper, low
  single-digit $/run.)
- **(c) Testable now?** Yes — *provided* it runs off this firewalled sandbox (owner's machine or a detached
  background job). Not a spend gate; an access-path choice.
- **(d) How to fetch:** `curl "ftp://shortstock@ftp3.interactivebrokers.com/usa.txt"` (try ftp2/ftp
  mirrors if refused); keep preferred rows (`SYM` contains ` PR`); join to B01 pairs via
  `alpaca_sym.replace(".PR"," PR")`; report per-pair both-legs `AVAILABLE>0` and `FEERATE`.
- **(e) Expected value:** as a **B01 rescue — negative**; the edge is insignificant (t 1.48) and
  spread-fragile independent of borrow. As **reusable borrow infrastructure for all future RV work and the
  424B5 tail — positive and free.** Recommend fetching it on the infrastructure rationale, with no
  expectation of promoting B01.

**HARD LIMITS OBSERVED:** research/recommendation only. Nothing bought, no account, no payment, no git
commit. FTP file not bulk-downloaded (port firewalled here); only small keyless HTTPS verification fetches
were made to confirm coverage and format.
