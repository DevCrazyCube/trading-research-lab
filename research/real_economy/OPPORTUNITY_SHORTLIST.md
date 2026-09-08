# T26 — the ranked REAL-ECONOMY opportunity shortlist

**What this is.** A survey and ranking of **22 concrete, legitimate mechanisms by which a fast
tireless AI plus one human operator can convert work into income outside financial markets** —
digital products and micro-SaaS, information and data products, marketplace/mispricing-at-scale
arbitrage, AI-productised service work, and niche tools. Nineteen are ranked; three are named and
**disqualified on the legal/ethical gate** rather than quietly omitted.

**Why the programme is here.** Eight directional equity candidates dead, the memecoin venue proven
extractive by construction, and `FINDINGS.md` §1's −16.89 % *at zero transaction cost*. Financial
markets are the most competitive zero-sum arena that exists and this programme has now measured its
own edge there at approximately zero. This document asks the only remaining question: **where does
an AI's actual advantage — breadth, tirelessness, and code — convert to money in a positive-sum
setting?**

**Status.** Survey **plus first-party measurement**. §2 is our own probing, run 2026-08-19 against
live public APIs. Every income figure, base rate and saturation claim attributed to an outside
source is **cited and marked as a claim, not verified by us**. §7's first move rests on WBSO
parameters read directly off RVO.

**Nothing here is a certified result and nothing here has been executed.** No account was created,
nothing was purchased, nothing was deployed, no order was placed. Every action in §7 that touches
money, identity, a customer or a platform is marked **OWNER** and is the owner's to take or refuse.

---

## 0. The one law this document is organised around

The trading work has a one-line structural result: *the toll is the house edge, and the house is the
protocol.* The real-economy equivalent, and it is now measurable, is:

> **Wherever an AI's output is cheap to produce and expensive to verify, the venue closes.**
> Money accrues only where the output is **expensive to produce** *or* **cheap for the buyer to
> verify** — and is tied to an outcome that buyer can price.

This is not a theory. It is what happened in 2026, in public:

- **Bug bounty.** HackerOne reports a **>100 % industry-wide surge** in report volume after the
  early-2026 model releases and a **76 % YoY jump** through March, with the share of reports
  containing a real vulnerability **flat at 25 %**. curl ended its programme. GitHub cut public
  payouts roughly in half and moved the top tier invite-only. Google, Bugcrowd and the Internet Bug
  Bounty all restructured, suspended or narrowed scope in the same year. Torvalds called the kernel
  security list "almost entirely unmanageable." *An AI's ability to generate more submissions
  destroyed the venue that paid for submissions.*
- **SEO content.** Google Search pageviews across Chartbeat's publisher network fell **34 %**
  Dec-2024 → Dec-2025; zero-click is ~60 % of queries; sites shipping bulk unedited AI pages took
  **50–80 %** traffic drops; Google's own *Network* (external AdSense) revenue fell 4 % while search
  on its own surfaces grew 19 %. *The venue that paid for words stopped paying.*

Both were the categories an AI is most obviously "good at". Both are now the worst places to stand.
**The corollary that orders this entire shortlist:**

> **The scarce input is no longer production. It is distribution, trust, and the operator's hours.**
> An AI automation agency's own practitioners put it exactly: *"the build is the cheap 10 %; the
> other 90 % is getting to five clients."*

So a mechanism is ranked high here **only if it either (a) inherits distribution from somewhere that
already has it, or (b) makes the AI's breadth visible to a buyer as a personalised artifact that a
competitor cannot afford to produce.** Everything else is a hobby with a Stripe button.

---

## 0b. The binding constraint, discovered while doing this work

**The operator is in the Netherlands.** Evidence, first-party: `timedatectl` → `Europe/Amsterdam
(CEST, +0200)`; `locale` → `LANG=nl_NL.UTF-8`; every git commit timestamped `+0200`.

This was not in the task brief and it **reorders the shortlist**, because the standard
make-money-online canon is written for a US operator. Consequences, all load-bearing:

| consequence | effect |
|---|---|
| **US federal contracting/grants are effectively out.** SAM.gov set-asides are US-entity instruments; our probe of `api.sam.gov` returns **404 without a key** anyway | kills the highest-value English-language procurement play |
| **NL/EU procurement is wide open instead.** TenderNed's full national stream is a **free, keyless API** (§2) | replaces it with something we measured working |
| **B2B cold email is legal in NL** — Telecommunicatiewet art. 11.7 carries a **B2B exemption Germany and France did not take**, and the AP has not imposed stricter national rules than GDPR for B2B prospecting to professional addresses. ACM enforces opt-out/identity; AP enforces the lawful basis | this is the single biggest structural advantage the operator has, and it is jurisdictional. The outreach-heavy mechanisms are *legal here and not in the two largest neighbouring markets* |
| **Registration is cheap and fast.** KVK one-time `inschrijfvergoeding` **€85.15** (2026), **no annual fee** thereafter | capital is not the barrier |
| **A Dutch-language, Dutch-regulation niche is a real moat** | global AI tooling is built for English and US rules; NL rules (WBSO, saldering, Peppol, AVG) are a small, well-defined, high-value corpus an AI can actually master |
| **Dated national deadlines create dated demand** | see §7: **WBSO for calendar-2027 must be filed by 20 December 2026**. Four months out. The entire NL subsidy-advisory industry sells into Sept–Dec |

---

## 1. The rubric

Each mechanism scores **1–5, higher is better**. Total is the unweighted sum; the legal gate is
pass/fail and overrides the total.

- **I — realistic net income to *us* in the first 12 months, at the median outcome, not the top of
  the range.** 5 = >€50k · 4 = €20–50k · 3 = €5–20k · 2 = €1–5k · 1 = ≈€0.
- **L — AI leverage.** Share of total work the AI can genuinely do end-to-end.
  5 = >80 % · 4 = 60–80 % · 3 = 40–60 % · 2 = 20–40 % · 1 = <20 %.
- **S — speed to first euro.** 5 = <2 weeks · 4 = 2–6 weeks · 3 = 6–12 weeks · 2 = 3–6 months ·
  1 = >6 months.
- **X — executability with what we have today**: data we hold or probed free, skills present,
  capital under €200, no licence required. 5 = everything present · 1 = blocked on capital, licence
  or data we do not have.
- **D — durability.** Does it compound, or is it commoditised the moment it works?
  5 = compounding asset with a moat · 1 = replicated within months by anyone with the same models.
- **E — legal/ethical gate.** **PASS** or **FAIL**. A FAIL is not ranked at any score.

**Ties break on X, then D** — the programme's earned ordering: prefer the thing we can actually
start over the thing that scores well on paper, and prefer the thing that still exists next year.

---

## 2. What we actually hold — probed live, 2026-08-19

Read-only GET/POST probes from this machine. No key was created, nothing was purchased.

| source | probe result | what it enables |
|---|---|---|
| **TenderNed** `papi/tenderned-rs-tns/v2/publicaties` | **200, free, no key. 144,965 publications**; we pulled **5,000** covering 2026-06-10 → 2026-08-19 | the complete NL public-procurement stream |
| …composition of that 5,000 | **70.4 publications/day**; 2,214 awards · 1,342 open calls · 282 market consultations · 241 prior notices. **Diensten 2,915 / Leveringen 1,437 / Werken 648.** 4,306 EU-threshold vs **694 below-threshold (national)**. **457** negotiated *without prior call for competition* | the size and shape of the addressable flow |
| …**open right now** (closing ≥ today) | **1,630 open tenders**, of which **254** match an ICT/software/data keyword; **only 9** of those are below the EU threshold | the honest bad news for "bid on them yourself" — see #4 |
| **Grants.gov** `v1/api/search2` | **200, free, no key. 1,656 open/forecast opportunities** | US federal grants — mostly unusable from NL, kept for completeness |
| **NIH RePORTER** v2 | 200, free. **50,150 FY2026 projects** | research-funding data products |
| **Federal Register** API | 200, free. **74 documents on 2026-08-18** alone | US regulatory monitoring products |
| **openFDA**, **CourtListener** v4, **SEC EDGAR full-text search** | 200, free, no key | public-data product raw material |
| **USAspending** v2 | 200, free, no key | US award analytics |
| **GitHub search API** | 200, free unauthenticated. **19,574 organisations with `location:Netherlands`.** In a random n=25 subsample: **21 have a website, 12 publish an email, 11 pushed since 2026-02** | **a free, high-precision list of Dutch companies that demonstrably write software** — i.e. the WBSO-eligible population, with public evidence of the R&D attached |
| **EnergyZero** price API | 200, free, no key. Hourly NL day-ahead consumer prices | dynamic-tariff / post-saldering modelling |
| **RVO** subsidy pages | 200. WBSO 2026 read directly: **36 %** of the first **€391,020** S&O-grondslag, **16 %** above it, **+50 % starter uplift**; self-employed deduction **€15,979**, starters **+€7,996** | the arithmetic in §7 is RVO's, not ours |
| **Steam Community Market** | 200, free. **524,033 listed items** | scannable — and **disqualified**, see #20 |
| **RDAP / Verisign**, **expireddomains.net** | 200 | domain-space scanning |
| **KVK API** (`api.kvk.nl`) | ✗ **401** | the Dutch company register is **key-gated and paid**. This is the single biggest data gap for any NL B2B play, and §7 routes around it |
| **OpenCorporates**, **overheid.io/openkvk** | ✗ **401** each | same gap, same routing |
| **SAM.gov** opportunities v2 | ✗ **404** without a key | US federal contracting closed to us today |
| **eBay Browse API** | ✗ **403** — OAuth app registration required (free, **OWNER** action) | marketplace arbitrage scanning is gated on an owner-created developer app |
| **ICANN CZDS** zone files | ✗ **401** — requires an approved ICANN account (**OWNER**, free, slow) | bulk domain analysis gated |
| **EU Funding & Tenders** SEDIA search | ✗ 500 on the documented call | EU-level grants need more work than TenderNed did |
| **Peppol directory** JSON | 200 but **0 matches** on our query syntax | e-invoicing readiness targeting needs a different query |

**The one-line reading:** *public-sector and open-data spaces are free and wide open to us; private
company registries are paywalled; marketplace APIs need an owner-registered app.* That fact alone
pushes the shortlist toward public-money and public-procurement mechanisms and away from
private-company enrichment plays.

---

## 3. The ranking

| # | mechanism | I | L | S | X | D | Σ | E |
|--:|---|--:|--:|--:|--:|--:|--:|:--:|
| **1** | **Public-money discovery for NL SMEs — WBSO-first, subsidy stack second** | 3 | 4 | 4 | 4 | 3 | **18** | PASS |
| **2** | **Marketplace-distributed micro-SaaS / niche tool** (Shopify, Chrome, VS Code, WordPress, Notion) | 2 | 5 | 2 | 5 | 3 | **17** | PASS |
| 3 | Tender discovery + bid-qualification service (TenderNed/TED) | 3 | 4 | 3 | 5 | 2 | **17** | PASS |
| 4 | Productised recurring automation retainer, one NL vertical | 3 | 3 | 4 | 3 | 3 | **16** | PASS |
| 5 | Paid niche research / independent benchmark subscription | 2 | 4 | 2 | 4 | 4 | **16** | PASS |
| 6 | Productised one-off audits (AI-visibility/GEO, WCAG accessibility, Peppol readiness) | 3 | 4 | 4 | 3 | 1 | **15** | PASS |
| 7 | Expert AI-training marketplaces (Mercor, Surge, Handshake) — direct labour | 3 | 1 | 5 | 4 | 2 | **15** | PASS* |
| 8 | High-rate ZZP contracting via public DAS / inhuurdesk | 4 | 1 | 3 | 3 | 3 | **14** | PASS |
| 9 | Data product from joined public sources (dataset / API / alerting) | 2 | 5 | 2 | 4 | 2 | **15** | PASS |
| 10 | Free-tool-led growth with a paid tier ("tool as the ad") | 2 | 5 | 1 | 5 | 2 | **15** | PASS |
| 11 | Micro-acquisition of a failing micro-SaaS + AI turnaround | 4 | 4 | 3 | 1 | 3 | **15** | PASS |
| 12 | Post-saldering / dynamic-tariff household energy optimisation software | 2 | 4 | 2 | 3 | 2 | **13** | PASS |
| 13 | Digital templates, kits and courses (Gumroad, Lemon Squeezy, Etsy digital) | 2 | 4 | 3 | 4 | 1 | **14** | PASS |
| 14 | Physical goods resale arbitrage (Marktplaats, eBay, boekenveilingen, surplus) | 2 | 2 | 3 | 2 | 2 | **11** | PASS |
| 15 | Domain / expired-domain flipping | 1 | 4 | 1 | 3 | 2 | **11** | PASS |
| 16 | Kaggle / ML-competition prize money | 1 | 4 | 2 | 3 | 1 | **11** | PASS |
| 17 | KDP low-content books & print-on-demand merch | 2 | 4 | 3 | 3 | 1 | **13** | PASS† |
| 18 | Bug bounty / vulnerability research at scale | 1 | 3 | 2 | 3 | 1 | **10** | PASS |
| 19 | SEO content site + display advertising | 1 | 5 | 1 | 4 | 1 | **12** | PASS |
| — | Steam / in-game item arbitrage | — | — | — | — | — | — | **FAIL** |
| — | Ticket resale at scale / bot-assisted buying | — | — | — | — | — | — | **FAIL** |
| — | AI-generated reviews, engagement, fake identities, MLM, "AI-agency-in-a-box" reseller kits | — | — | — | — | — | — | **FAIL** |

\* #7 passes only if the platform's terms permit model assistance on the specific task — several
explicitly prohibit it, and the whole point of the work is *human* judgment. See the entry.
† #17 passes the gate but sits one step from it; see the entry.

**Note on the totals — the ranking is not sorted by Σ, and every place it disagrees is listed here.**
Arithmetic checked: all nineteen rows satisfy Σ = I+L+S+X+D exactly. Four positions are deliberately
out of Σ order, each for a stated reason, so that no inconsistency is silent:

| position | Σ | why it sits below a lower-Σ entry |
|---|--:|---|
| #9 data product | 15 | ranked under #8 (Σ14) because **we cannot name a buyer.** L=5 flatters it; a product with no identified customer is a hobby |
| #10 free tool + paid tier | 15 | **S=1.** X=5 and L=5 flatter it; a tool nobody has heard of earns nothing, possibly forever |
| #11 micro-acquisition | 15 | **X=1.** Blocked on €10–50k of owner capital that has not been authorised, so it is not startable |
| #13 templates/courses | 14 | ranked under #12 (Σ13) because **D=1 and it presumes an audience the operator does not have** |
| #17 KDP / POD | 13 | ranked under three Σ11 entries because it is **one step from the ethical gate** — see the entry |
| #19 SEO content | 12 | ranked **last** despite Σ12 because §0's measurements say the venue is dead, not merely crowded |

The ordering is by **(Σ, X, D)** and then by the §0 law — *does this inherit distribution, or make
the AI's breadth visible to a buyer?* — never by Σ alone.

---

## 4. The entries

Each: what it is · realistic income and time-to-first-euro · capital · **what the AI does vs what
only the OWNER can do** · saturation · moat · legal status.

### 1. Public-money discovery for NL SMEs — WBSO first, the subsidy stack second · Σ18

**What.** Thousands of Dutch companies are entitled to money they do not claim, under schemes with
public rules and published parameters. The largest is **WBSO** (R&D payroll-tax credit): **36 % of
the first €391,020 of S&O wage base, 16 % above it, +50 % uplift for starters**; self-employed take
a fixed deduction of **€15,979** (starters **+€7,996**) — RVO, read 2026-08-19. Alongside it sit
**MIT** (feasibility/R&D collaboration), **SLIM** (60 % of SME training costs) and the EU layer. A
published NL worked example stacks WBSO €11,700 + MIT feasibility €7,000 + MIT R&D €16,450 + SLIM
€3,600 = **€38,750, 47 % of project cost** (cited, not verified by us).

**Why an AI is a genuine edge here, and not just faster.** The binding problem is *identification*:
which of ~2 million NL businesses is both eligible and unaware. That is a scan over a space no human
advisor can cover — and §2 found a **free** proxy population with the evidence attached: **19,574
GitHub organisations located in the Netherlands**, of which our n=25 subsample gives 21 with a
website, 12 with a public email and 11 with a push since 2026-02 — **84 % / 48 % / 44 %, on n=25, so
±10 pp at best; an order of magnitude, not a rate.** A public repository
with recent commits *is* documentary evidence of development work. No competitor is producing an
evidence-backed, per-company briefing at that scale, because for a human it costs an hour each.

**Income.** NL subsidy advisors work `no cure no pay` at roughly 10–20 % of realised benefit
(industry practice, cited). At a typical WBSO benefit of €15–40k per small dev firm, a 15 % fee is
**€2–6k per client**. Median-honest first year for a one-operator shop: **2–5 clients, €6–25k**;
a good year with retention (WBSO is annual and recurring) reaches the €20–50k band in year two,
because *last year's client re-files*. **Time to first euro: 4–10 weeks** — engagement signed in
weeks, fee on approval.

**Capital.** KVK **€85.15** one-time, domain + mailbox ≈ **€40/yr**. Under €200 total. No licence
exists for subsidy advice.

**AI does:** build and maintain the candidate population; extract per-company evidence of qualifying
S&O work; compute the benefit at RVO's published parameters; draft the NL-language briefing; draft
the technical project description that is the genuinely hard part of a WBSO filing; maintain the
deadline calendar and the hour-administration templates; run the suppression list.
**OWNER only:** KVK registration; domain/mailbox purchase; **sending every email**; every call and
meeting; the engagement agreement; eHerkenning/machtiging; **signing and submitting any application**
and standing behind its truthfulness; invoicing.

**Saturation.** Real and named — Leap, Subsidiebird, Subsidiebureau Nederland, PNO, the Big Four all
sell this, and some already advertise AI. But the market is enormous and fragmented (WBSO's national
budget is cited at ~€1.8 bn/yr), and incumbents compete on relationships, not on scan coverage. We
are not trying to out-advise them; we are trying to *reach the firms none of them called*.

**Moat.** Weak-to-medium and honest about it: the moat is the **candidate-identification pipeline**
plus accumulating NL-specific domain knowledge plus annual recurrence. It is copyable in a year.

**Legal/ethical.** Fully legitimate. **The bright line: the briefing may only ever say "you may
qualify — here is the public evidence and the arithmetic", never "you qualify".** The application
itself must be truthful and prepared with the client; a wrongly-claimed WBSO is clawed back with
penalties, and an AI that flatters a marginal case is the failure mode. Email must carry sender
identity, physical address, privacy notice and a working opt-out (Telecommunicatiewet 11.7 + AVG).

---

### 2. Marketplace-distributed micro-SaaS / niche tool · Σ17

**What.** A small paid tool listed where buyers already search: Shopify App Store, Chrome Web Store,
VS Code Marketplace, WordPress.org, Notion/Figma galleries, Zapier/Make directories. **The
marketplace supplies the distribution that §0 says is the scarce input.** Shopify takes 0 % of a
developer's first $1 M/yr and 15 % above it.

**Income — brutally.** The distribution is power-law and the median is bad: the **median listed
Shopify app earns under $1,000/month**, top 10 % clear $100k ARR, top 1 % clear $1M ARR (cited). The
broader indie-SaaS picture is worse — across 8,000+ tracked startups with *any* revenue the **median
is $145 MRR**, mean $4,298, and only **6.1 % clear $10k MRR**; ~70 % of micro-SaaS sit under $1k MRR
(cited). Realistic first 12 months for one good listing: **€1–5k total**, not monthly.
**Time to first euro: 3–6 months.**

**Capital.** €0–€100 (Chrome Web Store developer fee is one-time and trivial; Shopify Partner is
free). **AI does:** ~90 % — market gap analysis from public review corpora, the entire build, the
listing copy, screenshots, support macros, changelog. **OWNER only:** developer-account creation,
payout/tax setup, app-store review responses, refunds, and any customer conversation.

**Saturation.** Severe on generic categories, thin on boring ones. **Moat:** the listing's review
history and ranking, which does compound. **Legal:** clean, provided platform terms are followed.

---

### 3. Tender discovery + bid-qualification for NL SMEs · Σ17

**What.** Not "alerts" — TenderNed already alerts for free and TenderGuide/Negometrix sell that.
The product is **qualification**: of 1,630 currently-open tenders, which three could *this* company
actually win, with the eligibility criteria, the closing date, and a first-draft response outline.

**The honest measurement that caps this.** §2: of 254 open ICT/software tenders, **only 9 are below
the EU threshold**. The winnable-by-a-small-firm slice is thin, and the big ones are won on past
performance a new entrant does not have. That is why D=2 and why this is a *service to SMEs that
already bid*, not a way for us to win contracts ourselves.

**Income:** €150–500/month retainer per SME, or per-bid support at €500–2,000. **First euro: 6–12
weeks.** **Capital:** ~€0 — we already have the data pipe working. **AI does:** ingest, classify,
score fit, draft. **OWNER:** sells, signs, delivers the human judgment on go/no-go.
**Legal:** clean; TenderNed data is public. **Saturation:** established incumbents at the alerting
layer, weak at the qualification layer.

---

### 4. Productised recurring automation retainer, one NL vertical · Σ16

**What.** Pick one vertical (e.g. NL accountancy offices, installation firms, or e-commerce
merchants) and sell one recurring, measurable automation — not "AI consulting". The pattern works;
its economics are also documented honestly by its own practitioners: reaching **$10–50k/month within
6–12 months** is possible for specialists, but *"the build is the cheap 10 %, the other 90 % is
getting to five clients"*, and one operator hits a delivery wall at roughly five accounts (cited).
Also cited and worth pricing in: **automation ROI decays 15–25 %/yr without maintenance** — which is
the argument for the retainer, not against it.

**Income:** €400–1,500/month per client; realistic year one **€5–20k**. **First euro: 2–6 weeks** —
the fastest of the product-shaped options. **Capital:** ~€0. **AI does** the build, the docs, the
monitoring, the reporting. **OWNER** does the entire acquisition funnel, every call, and holds the
relationship. **Saturation:** high and rising; the differentiator is vertical depth, not tooling.
**Legal:** clean, with the standard AVG/processor-agreement obligations when touching client data.

---

### 5. Paid niche research / independent benchmark subscription · Σ16

**What.** The one thing this programme is *demonstrably* world-class at: hostile, leakage-free,
reproducible measurement of claims that vendors publish without evidence. Sold as a paid report or
subscription to a professional audience. `FINDINGS.md` is, in form, already this product.

**Why it ranks despite low income.** D=4 — it is the only entry whose asset *appreciates*: a
reputation for being right is not commoditised by better models. It is also the only entry where our
existing artefacts are the raw material.

**Income:** €0 for months, then €1–5k/yr per small audience; **realistic year one €1–5k**.
**First euro: 3–6 months.** **Capital:** ~€0. **AI does** ~80 % — the measurement, the writing, the
reproducibility harness. **OWNER:** publishes, and is the named human who stands behind the numbers
(that name is the product). **Saturation:** low — almost nobody does adversarial measurement,
because it is slow and makes enemies. **Legal:** clean; be careful with defamation when publishing
negative vendor findings, and stick to measured facts.

---

### 6. Productised one-off audits · Σ15

**What.** A fixed-scope, fixed-price automated audit with a human-reviewed report: AI-visibility/GEO,
WCAG accessibility (EU Accessibility Act pressure), Peppol/e-invoicing readiness. The GEO market is
real and priced: agencies **€1,500–50,000/month**, boutiques **$5–15k/month**, consultants
**$200–450/hour**, and *"generative engine optimization services"* costs **$44/click** on paid search
(DataForSEO, June 2026, cited) — a strong revealed-demand signal.

**Why D=1.** An audit is exactly the artifact §0 warns about: cheap for an AI to produce, and within
a year every competitor ships the same PDF. Take the money while the window is open; do not build a
company on it. **Income:** €500–2,500 per audit, year one **€5–20k**. **First euro: 2–6 weeks.**
**AI does** the audit and the report. **OWNER** sells it and defends it in the meeting.
**Legal:** clean. Do not overstate what an audit proves.

---

### 7. Expert AI-training marketplaces · Σ15 · conditional PASS

**What.** Mercor, Surge, Handshake AI et al. pay credentialed specialists to produce evaluation and
training data. Cited rates: Mercor **$85 average expert hour**, **$60–90/hr** general document work,
**$130–180/hr** for high-demand specialisms, seniors above **$200**; Surge **$50–200** for vetted
frontier experts; general AI-training work averages **$31/hr**.

**Why it is ranked but not recommended.** It is **the fastest real euro on this list** (S=5, days)
and the operator plausibly qualifies on quantitative-finance and blockchain-research credentials.
But **L=1**: they are buying *the human's* judgment, and several platforms explicitly prohibit model
assistance. **Using the AI to do the work would be both a terms violation and a corruption of the
product being sold.** So it is honest hourly labour with a good rate and no leverage — a bridge, not
a business. **Capital €0. OWNER does 100 % of it** (identity verification, interview, the work
itself).

---

### 8. High-rate ZZP contracting via public DAS / inhuurdesk · Σ14

**What.** NL government bodies hire ICT freelancers through dynamic purchasing systems and hiring
desks — §2 saw the DAS notices in the live TenderNed stream. Rates for senior data/ICT roles are
typically €80–120/hr (market practice, not verified by us). **Highest I on the list (4)** and
**lowest L (1)**: it is a job. Included because intellectual honesty requires noting that the
highest-expected-value use of the operator's next 500 hours may simply be billing them — and because
it can *fund* everything above it. **OWNER:** everything. **Legal:** clean; note the NL
`Wet DBA`/schijnzelfstandigheid enforcement regime when contracting.

---

### 9. Data product from joined public sources · Σ15, ranked 9th on tie-break

**What.** Take sources no one has bothered to join — §2's TenderNed + Federal Register + NIH
RePORTER + EDGAR + CourtListener are all free and keyless — clean them, and sell the join as a
dataset, API or alerting feed. **L=5**: this is pure AI work. **The reason it is not higher: we
cannot name the buyer.** Every specific buyer we could think of already has the data or does not
know it wants it, and a data product with no named buyer is a hobby. **Promote this only when a
customer from #1/#3/#4 asks for it by name.** **Income year one €1–5k. First euro 3–6 months.**
**Legal:** check each source's licence individually — most US federal data is public domain,
TenderNed's re-use terms must be read before any resale.

---

### 10. Free-tool-led growth with a paid tier · Σ15, ranked 10th on tie-break (S=1)

**What.** Ship a genuinely useful free tool; convert a slice. **X=5, L=5** — we can build it today.
**S=1** — a free tool with no distribution earns nothing, possibly forever, and §0's law says the
"just build it and they will come" era ended when production got free. Only rational as the *front
end* of #1 or #3, where the tool is the outreach artifact rather than the business.

---

### 11. Micro-acquisition of a failing micro-SaaS + AI turnaround · Σ15, ranked 11th on X=1

**What.** Buy a small SaaS cheap and fix it with an AI that can rewrite the whole codebase. The
prices are real: deals **under $100k close at ~1.68× profit**, versus 4.3× above $1M (Flippa/Acquire,
cited); sub-$50k inventory lives on Flippa. Buying €500/mo MRR for ~€10k and doubling it is the
highest **I** of any product-shaped entry.

**Why X=1.** It needs **€10–50k of the owner's capital, spent on an asset, on the owner's
authority** — squarely outside this task's guardrails and a decision only the owner makes. Flagged
as the best *capital-deployment* idea on the list should the owner ever want one, and explicitly not
recommended now.

---

### 12. Post-saldering / dynamic-tariff household energy optimisation · Σ13

**What.** **The salderingsregeling ends 1 January 2027** with no phase-out (Rijksoverheid); feed-in
is then remunerated at **≥50 % of the base supply rate ex-tax until 2030**. Millions of Dutch solar
households face a genuine, computable, individual optimisation — battery or not, dynamic contract or
fixed, when to shift load — and §2 confirmed **free hourly NL price data** (EnergyZero, 200, no key).
A per-household calculation is exactly what an AI does well, and it is a dated national demand wave
four months out. This is the closest thing on the list to the owner's "water or sunlight".

**Why only Σ13.** The buyer is a consumer, consumer acquisition is expensive, and the incumbents
(Zonneplan, Tibber, HomeWizard, Enever, the comparison sites) already monetise this via
supplier/installer affiliate fees — a channel that rewards volume marketing, which one operator does
not have. **The viable shape is B2B2C: sell the calculation engine to installers**, which is
mechanism #4 with a specific vertical. **Income year one €1–5k. First euro 3–6 months.**
**Legal:** clean; if any affiliate/lead fee is ever taken, it must be disclosed on the page.

---

### 13. Digital templates, kits, courses · Σ14, ranked 13th on D=1

Real but audience-gated and now flooded. Without an existing audience the median outcome is a
handful of sales. **Income year one €1–5k. First euro 2–6 weeks** *if* an audience exists — the
operator has none, which is the whole objection.

### 14. Physical goods resale arbitrage · Σ11

Marktplaats/eBay/surplus/book-lot arbitrage. **The AI edge is real on the scan and near-zero on the
doing** — every unit must be bought, stored, photographed, packed and shipped by the owner, and
capital is tied up per unit. Professional resellers already run the same scanners. §2 also found the
scan gated: **eBay Browse returns 403 without an owner-registered OAuth app.** Include a category of
this kind only if the owner *wants* physical work. **Legal:** clean.

### 15. Domain / expired-domain flipping · Σ11

Scanning is trivially automatable and §2 confirmed RDAP and drop-list access. The economics are the
problem: near-total illiquidity, a years-long holding period, renewal costs that bleed, and a
sale-probability per name that rounds to zero. **I=1.** Kept on the list as the canonical example of
*"the AI can scan it, therefore it must be an edge"* being false — scanning is not the scarce input;
a buyer is.

### 16. Kaggle / ML-competition prizes · Σ11

Legitimate, meritocratic, and priced like a lottery: prize pools go to the top handful out of
thousands, and the same models are available to every entrant. Effective hourly rate for a
non-specialist is poor. Worth doing for reputation, not income.

### 17. KDP low-content books & POD merch · Σ13, ranked 17th on D=1 and on the gate

The category still pays — the cited picture is $2–5 royalty per sale, €500–1,500/month achievable at
20–50 titles over 6–12 months, and heavy survivorship bias in every success story. **It ranks last
among PASSes because it sits one step from the gate:** the version that works at scale is
indistinguishable from the bulk-slop that §0 says kills its own venue, and it is the one entry where
"the AI made 500 of them" is the *strategy*. It passes only in the form where each title is
genuinely useful and genuinely reviewed by the owner — which destroys the volume economics. **We do
not recommend it.**

### 18. Bug bounty / vulnerability research at scale · Σ10

See §0. This was the single most obvious "AI advantage" category eighteen months ago and it is the
most damaged today: >100 % report-volume surge, valid-report share flat at 25 %, curl's programme
ended, GitHub's public payouts halved, four major programmes restructured or narrowed in 2026.
Legitimate work — a *real* vulnerability responsibly disclosed still pays and still helps — but the
open-submission economics have inverted. **I=1.**

### 19. SEO content site + display advertising · Σ12, ranked last

See §0. **Dead as a new venture.** 34 % decline in Google-sourced pageviews across a large publisher
network in twelve months; ~60 % zero-click; 50–80 % drops for bulk-AI sites; Google's external
network revenue shrinking while its own surfaces grow. Anyone selling this in 2026 is selling a 2021
playbook.

---

### The three that FAIL the gate

- **Steam / in-game item arbitrage.** The scan is trivial (§2: 524,033 listed items) and the whole
  thing is a trap: **Steam Market proceeds are wallet-locked and not withdrawable.** Every route to
  actual cash runs through third-party cash-out that violates the Steam Subscriber Agreement. Not
  income; a ToS violation with an extra step.
- **Ticket resale at scale / bot-assisted purchasing.** Bot-acquired-ticket resale is prohibited
  under EU consumer law and every primary-seller's terms. Excluded.
- **AI-generated reviews, engagement, fake identities, MLM, and "AI-agency-in-a-box" reseller
  programmes.** Fraud, platform-terms violations, or a business whose customers are its own
  downline. Excluded on the gate, and named here because they are the most heavily marketed
  "AI money" categories of 2026 and the owner will meet all of them.

---

## 5. The recommendation

> **Primary: #1 — public-money discovery for NL SMEs, WBSO first.**
> **Parallel background build: #2 — one marketplace-distributed micro-SaaS.**

**Why #1 wins on this programme's own criteria.** It is the only entry that scores well on *all
five* axes at once, and the only one where the AI's specific superpower — reading a whole national
population and producing a bespoke, evidence-backed artifact for each member of it — is the thing the
buyer pays for, rather than a thing the buyer must be persuaded to want. The value created is
unambiguously positive-sum: a Dutch company that was entitled to €20k of R&D credit and did not know
it now gets it, the state gets the R&D it legislated for, and we get a fee only if it lands.
Jurisdiction cooperates (NL B2B email exemption; €85.15 registration; no licence). And there is a
**dated deadline four months out** — 20 December 2026 for calendar-2027 WBSO — which converts
"someday" into a season.

**Why #2 runs alongside and not instead.** #1's ceiling is the owner's hours; #2's ceiling is the
market's. #2 costs the owner almost nothing per week (the AI builds it), inherits distribution from
a marketplace, and is the only candidate that could still be earning while the operator sleeps in
year three. Its median outcome is genuinely poor (median listed Shopify app <$1k/month; median
tracked indie SaaS $145 MRR) — which is precisely why it should be the *background* process funded
by #1, never the thing everything depends on.

**What we are NOT recommending, and why, so the owner is choosing rather than ratifying:**
#7 (AI-training marketplaces) would produce cash faster than anything else on this list, this week,
at $85–200/hour — and it is a job with zero AI leverage that may forbid AI assistance outright.
#11 (micro-acquisition) has the best income ceiling of any product entry and is blocked on €10–50k
of owner capital. #8 (ZZP contracting) probably has the highest raw expected value per hour of the
operator's time and no leverage at all. **If the owner's objective is "money soonest", the answer is
#7 or #8 and this document should say so plainly. If the objective is "a machine that makes money",
it is #1 funding #2.**

---

## 6. The honest base rates, in one place

Because the failure mode of a document like this is optimism:

| claim | figure | source status |
|---|---|---|
| median tracked indie startup with revenue | **$145 MRR** | cited |
| share of tracked startups clearing $10k MRR | **6.1 %** | cited |
| micro-SaaS under $1k MRR | **~70 %** | cited |
| median *listed* Shopify app | **< $1,000/month** | cited |
| sub-$100k SaaS acquisition multiple | **1.68× profit** | cited |
| valid-vulnerability share of bug-bounty reports | **25 %, flat**, on >100 % volume growth | cited |
| Google-sourced publisher pageviews, Dec-24 → Dec-25 | **−34 %** | cited |
| AI automation agency: share of the work that is the build | **~10 %** | cited (practitioner) |
| NL open tenders winnable by a small ICT firm (below EU threshold) | **9 of 254** | **ours, measured** |
| NL companies with public evidence of software development | **19,574** GitHub orgs, ~84 % with a website | **ours, measured** |

**Read the two rows in bold together.** They are the argument of this whole document: the space where
we must *compete* is thin, and the space where we can *scan* is enormous.

---

## 7. The concrete first move — startable this week

**Build the WBSO candidate scanner and briefing generator, and put 25 real briefings in front of
25 real Dutch companies.**

Not a category. A specific artifact, from data we probed working today.

### What the AI does — days 1–3, no owner action, no spend, no accounts

**Day 1 — the population.** Assemble a candidate list from the three free sources §2 verified:
1. **GitHub orgs `location:Netherlands`** — 19,574; keep those with a push since 2026-02 and a
   resolvable website. Expected survivors on our sampled rates: **~7,000–8,000**.
2. **TenderNed award notices** — the winning-supplier names in the 2,214 awards we already hold are
   NL entities with proven revenue and a public-sector customer.
3. **Public vacancy pages** on those companies' own sites advertising developer roles — the
   strongest single public signal of S&O wage base, and the input to the benefit arithmetic.
Deduplicate to legal entities. **Store no personal data beyond a business contact address, with a
retention rule and a documented lawful basis (AVG legitimate interest) written before the first row
is stored.**

**Day 2 — the briefing.** For each of the top 100 candidates by evidence strength, generate a
one-page **Dutch-language** briefing containing, and only containing:
- the public evidence of qualifying development work (named repositories, recent commit activity,
  the vacancy text), quoted and linked so the reader can check it;
- an estimated eligible S&O wage base from the visible dev headcount, with the assumption stated;
- the benefit computed at **RVO's published 2026 parameters** (36 % / €391,020 / 16 % / 50 % starter
  / €15,979 zelfstandigenaftrek), with a worked line the reader can verify;
- **the deadline: 20 December 2026 for calendar-2027 WBSO**;
- an explicit uncertainty paragraph — *"this is an outside estimate from public information; whether
  your work qualifies depends on facts we cannot see."*
**The briefing never asserts eligibility.** That sentence is the ethical spine of the whole plan.

**Day 3 — the compliance layer and the kill criteria.** Sender identity, physical address, privacy
notice, one-click opt-out, permanent suppression list, per-send log (Telecommunicatiewet 11.7 + AVG,
both of which apply). Freeze the acceptance test **before** any send:

> **KILL:** 100 briefings delivered → **fewer than 2 replies** ⇒ the artifact is not compelling.
> Stop. Do not iterate the email; the hypothesis "an evidence-backed personalised artifact earns a
> reply" is what failed, and it is the hypothesis the entire mechanism rests on.
> **CONTINUE:** ≥2 replies per 100 ⇒ proceed to 500.
> **WIN:** one signed no-cure-no-pay engagement within 45 days.

### What only the OWNER can do — days 4–5, ~€130 total

| step | cost | why it cannot be delegated |
|---|---|---|
| Register an **eenmanszaak** at KVK | **€85.15**, one-time, no annual fee | it is the owner's legal identity |
| Domain + business mailbox | ~€40/yr | a purchase |
| Read and approve the 25 briefings before any send | — | the owner's name is on every claim |
| **Send the 25 emails, personally** | €0 | contacting customers is an owner action, full stop |
| Take the replies; run the calls; sign the engagement | — | the relationship, and the liability |
| Decide the fee (recommendation: **15 % of realised benefit, no cure no pay, capped**) | — | pricing is the owner's |

### Why this and not something else, in one paragraph

It uses data we **already pulled today** (§2), needs **no capital** beyond €130, has a **dated
deadline** that makes the next four months the selling season, is **legal in NL specifically** in a
way it is not in Germany or France, creates **unambiguous positive-sum value** (a company gets money
the state legislated to give it), fails **cheaply and legibly** if the premise is wrong, and its core
asset — a national-scale, evidence-linked candidate map — **transfers directly** to mechanism #3
(tenders) and #4 (automation retainers) if WBSO itself disappoints.

### Week 2, in parallel and only if week 1's build is done

Start #2: mine a public marketplace's review corpus for a repeatedly-requested, unbuilt feature,
and ship one small paid listing. **No owner time beyond creating the developer account.**

---

## 8. What would make this document wrong

- **The reply rate.** Everything rests on an assumption we have not tested: that a personalised,
  evidence-backed artifact earns a reply where a generic pitch does not. §7's kill criterion tests
  exactly that, at n=100, in weeks. If it fails, mechanisms #1, #3, #4 and #6 all lose their
  acquisition channel simultaneously — they share it — and the shortlist collapses to #2, #5 and #7.
- **The population proxy.** "GitHub org in NL" is a *proxy* for "NL company doing R&D", and our
  sample of 25 already showed the noise (large foreign orgs appear under NL locations). If precision
  is below ~50 % the day-1 population is mostly waste and the KVK paywall (§2) becomes binding.
- **Owner hours.** Every top-ranked mechanism converts owner hours into money at some rate. If the
  owner cannot or will not spend those hours on customer contact, **the entire top half of this
  ranking is unavailable** and the honest recommendation becomes #2 and #10 — slow, low-income,
  low-owner-load — or #7/#8 as paid labour.
- **§0's law applied to ourselves.** If per-company AI briefings become universal, inboxes saturate
  and the artifact stops working, exactly as bug-bounty submissions did. **Assume a 12–24 month
  window**, and treat #1's real output as the *client relationships and the domain knowledge*, which
  survive the channel.

---

## 9. Open — for the owner

1. **Objective, explicitly: "money soonest" or "a machine that makes money"?** They give different
   answers (#7/#8 versus #1→#2) and this document cannot choose for you.
2. **Owner hours per week available for customer contact?** This is the single input that most
   changes the ranking.
3. **Authorise the €130** (KVK €85.15 + domain/mailbox) — or decline it, in which case §7 stops at
   day 3 with the briefings built and unsent.
4. **Is any capital available for #11 (micro-acquisition)?** If €10–50k exists, that entry's income
   ceiling is the highest on the list and it deserves its own scoping task.
5. **Country/entity confirmation.** §0b's constraint was inferred from timezone and locale, not
   stated. If the operator is not NL-resident, **§0b, the ranking and §7 must all be redone** — the
   B2B-email exemption, the KVK route and the entire WBSO mechanism are Dutch-specific.

---

*Compiled 2026-08-19. First-party probes in §2 are read-only and reproducible. No account was
created, nothing was purchased, nothing was deployed, and nothing in §7 has been executed.*

---

## Addendum A — what building §7 measured, 2026-08-19 (T27)

*Appended, not merged into the text above: the document stands as written and this records where
building the thing changed the numbers. Everything here is first-party and reproducible from
`research/real_economy/wbso/`.*

**Three of §2's and §7's claims moved.**

| claim above | what building it found | consequence |
|---|---|---|
| §7 day 1: *"TenderNed award notices — the winning-supplier names in the 2,214 awards we already hold"* | **The awarded supplier's name is not in the TenderNed API.** Neither `…/publicaties` nor `…/publicaties/{id}` carries a supplier field; the full detail-field inventory is in `wbso/logs/probe_report.json`. The name exists only inside the award PDF | the second candidate population in §7 does not exist without a PDF-parsing build. TenderNed is implemented as a *demand* signal (which public bodies buy software work), not a supplier list |
| §2: *"Peppol directory JSON — 200 but 0 matches on our query syntax"* | **The syntax works**: `directory.peppol.eu/search/1.0/json?q=<name>&rpc=<n>` (or `?country=NL`) returns **112,678 NL participants**, each with an ISO-6523 identifier — `0106` is `NL:KVK` and `9944` is `NL:VAT` per OpenPeppol's own published code list | a free, partial route around the paywalled KVK API — but see the next row |
| §1 entry: *"19,574 GitHub orgs … 11 of 25 pushed since 2026-02 (44 %)"* | On a sample **stratified across creation years** (n=165, not a best-match top-25): **28/165 = 17 %** own a non-fork public repo pushed since 2026-02. Of those 28, **19 survive every exclusion rule** | the recent-activity population is roughly **3,300 organisations, not the 7,000–8,000 §7 projected**. §2's n=25 came from an unpartitioned best-match search, which surfaces prominent orgs |

**And one that did not move but got sharper.** §8 predicted the population proxy would fail on
foreign multinationals. It fails differently: what actually comes through is **volunteer projects,
a scouting association, a university lab (`ai4mde.liacs.nl`), an MBO college, and parked domains**.
Each is now a rule or a review flag, derived from RVO's own condition *"U bent geen publieke
kennisinstelling"* where one applies. **0 of 19 kept candidates matched an NL entity in Peppol** —
the directory holds the firms that e-invoice government, which is largely not the population a
GitHub scan finds, so the KVK gap is narrower than §2 thought but still open for exactly the small
firms this mechanism targets.

**What is built:** scanner, Dutch briefing generator, an ethics linter that fails the run on any
eligibility assertion or unsourced claim, benefit arithmetic proven against RVO's three published
worked examples, 110 hermetic tests, and **10 real briefings** for the owner to judge.
**What is not done, and is the owner's:** KVK, mailbox, reading the briefings, and sending them.
§7's kill criterion is frozen verbatim in `wbso/README.md` §3 with its denominator rules.
