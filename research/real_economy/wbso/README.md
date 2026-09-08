# WBSO candidate scanner + evidence-backed Dutch briefing generator

**T27.** Built against T26 §7 ("the concrete first move"), which ranked *public-money discovery for
NL SMEs, WBSO first* as the one mechanism where a fast AI plus one operator has a genuine edge.

**What exists here:** a scanner that finds Dutch organisations with public evidence of software
development, and a generator that turns each into a one-page Dutch briefing saying *you may qualify
— here is the public evidence, here are RVO's numbers, here is the deadline, and here is everything
we cannot see.*

**What does not exist here, by design:** any way to send anything. There is no `send` subcommand,
no mail configuration, no address list export. Nothing was sent, no account was created, no company
was registered, nothing was bought, nothing was deployed. Sections 2 and 3 below are the owner's,
and they are the only route from this directory to a customer.

---

## 1. What it does, honestly

```
19,575 GitHub organisations with location:Netherlands   (free, unauthenticated, probed 2026-08-19)
        │  stratified sample across creation years — a sample, never a census
        ▼
   screen: does it own a non-fork public repository pushed recently?
        │
        ▼
   enrich: GitHub org profile · Peppol NL legal-entity corroboration · own website + careers page
        │
        ▼
   exclude: public knowledge institutions (RVO rule), too-large orgs, non-NL, no contact channel
        │
        ▼
   score, then generate one Dutch briefing per survivor, each line linked to its source
        │
        ▼
   lint every briefing: no eligibility assertion, no unsourced claim, required disclosures present
```

Run it:

```bash
cd research/real_economy/wbso
python -m pytest tests -q                       # 108 tests, hermetic, no network
python -m wbso.cli probe                        # re-verify every source is up, free and open
python -m wbso.cli dryrun --limit 10            # scan + brief + DRYRUN_REPORT.md
python -m wbso.cli rescore                      # re-apply the rules to a scan, no refetch
python -m wbso.cli lint                         # re-lint what is already in briefings/
```

`DRYRUN_REPORT.md` holds the last run's funnel, exclusion reasons and lint results.
`briefings/NN_login.md` is a briefing; `briefings/NN_login.dossier.json` is what the owner must
check before that briefing could ever be sent.

### The four sources, and what each is worth

| source | endpoint | status 2026-08-19 | what it proves | what it does not |
|---|---|---|---|---|
| GitHub | `api.github.com/search/users`, `/search/repositories`, `/orgs/{login}` | 200, free, no key. **19,575** NL-located orgs | this organisation writes code, publicly, this month | that it is a Dutch legal entity, its headcount, or that the work is technically novel |
| Peppol Directory | `directory.peppol.eu/search/1.0/json` | 200, free, no key. **112,678** NL participants | an NL-registered entity with this *name* exists, with a KVK (ICD 0106) or BTW (9944) identifier | that it is the *same* organisation — it is a name match, never an identity claim |
| RVO | `rvo.nl/subsidies-financiering/wbso*` | 200 | the 2026 parameters, conditions and deadlines, quoted with URLs | anything about a specific company |
| TenderNed | `tenderned.nl/papi/.../publicaties` | 200, free, no key | which public bodies are buying software work right now | **the awarded supplier's name — it is not in the JSON.** See §7 |

### What the live runs taught the exclusion rules

The rules below are not a priori hygiene. Each was written after a real candidate got through a live
scan and should not have — which is the only way to find out what a population proxy actually
contains. Live runs of 2026-08-19: **165 organisations screened, 28 passed, 19 kept, 10 briefed.**

| what came through | rule now | why it is a rule and not a preference |
|---|---|---|
| `ai4mde.liacs.nl` — a Leiden university CS lab | any academic hostname (`liacs.nl`, `tudelft.nl`, `.edu`, `.ac.*`, …) | RVO: *"U bent geen publieke kennisinstelling"* |
| a scouting association | volunteer/association name patterns (`scouting`, `vereniging`, `hackerspace`, `meetup`, …) | no S&O wage base to compute a credit on |
| `ExOrtis.com is available`, `Virenix — Coming Soon` | parked / for-sale / unbuilt homepage titles | there is no operating company behind the domain |
| `Aventus` — an MBO college whose homepage says *"De school waar jij 't maakt"* | education words in the page title raise a **flag**, not an exclusion | "school" also appears on companies selling *to* schools |
| a volunteer badge community that looks exactly like a small software firm | **no rule** — it becomes a `review_flag` | no mechanical rule separates these; the dossier asks the owner |

The last row is the important one. `review_flags` in each dossier lists the doubts no rule could
settle (no Peppol corroboration, no careers page, no company name, one thin repository, no public
email). They do not exclude anyone; they are what the owner reads before deciding to send.

### The two things that make a briefing legitimate rather than spam

1. **Every claim about the company carries a URL the company can open**, with the date we looked.
2. **The briefing never asserts eligibility.** It says *mogelijk in aanmerking*, states RVO's own
   conditions including "technisch nieuw voor uw bedrijf", has a section headed *Wat wij niet weten*,
   and tells the reader they can apply themselves via RVO's free WBSO-wijzer without us.

Both are enforced by `wbso/ethics.py` and tested in `tests/test_ethics.py` against the exact
sentences a careless generator would produce ("U komt in aanmerking", "Uw WBSO-voordeel bedraagt
€ 24.000", "Wij garanderen toekenning"). The dry run exits non-zero if any briefing trips it.

The benefit arithmetic is `wbso/benefit.py` and it reproduces **all three worked examples RVO
publishes** (€ 9.750 / € 49.250 / € 151.964) to the euro — `tests/test_benefit.py`. If a parameter
edit breaks any of them, the tests fail before a briefing can be generated.

---

## 2. Owner next steps — exactly, in order

Everything in this section is an owner action. None of it has been done.

| # | step | cost | why it cannot be delegated |
|---|---|---|---|
| 1 | **Read 10 briefings in `briefings/`** and judge them. Would *you* send this to a stranger over your own name? | 30 min | your name is on every claim |
| 2 | Register an **eenmanszaak** at KVK | **€ 85,15** one-time — *cited in T26, and we did **not** confirm it: the fee page moved and returned 404 on 2026-08-19. Check kvk.nl before budgeting* | it is your legal identity |
| 3 | Buy a domain + business mailbox | **~€ 40/yr** | a purchase |
| 4 | Fill `params/sender_profile.json` (copy the `.example`) with real KVK number, address, opt-out address, privacy URL | — | the data does not exist until step 2 |
| 5 | Widen the scan, then re-brief: `python -m wbso.cli scan --max-orgs 300 --max-enriched 60 --budget 500 --fetch-sites` (≈ 35 min at the unauthenticated rate) and `python -m wbso.cli brief --limit 25 --sender params/sender_profile.json`. At the measured ≈ 12 briefable per 100 screened, 300 is what 25 briefings needs | — | — |
| 6 | **Re-check RVO before sending**: parameters, and whether the 2027 calendar is published (see §5) | 10 min | a wrong number in a briefing is your liability |
| 7 | **Read and approve each of the 25 briefings individually**, editing freely | 1–2 h | see step 1 |
| 8 | **Send the 25 emails yourself**, from your own mailbox | € 0 | contacting customers is an owner action, full stop |
| 9 | Log every send, every reply and every opt-out; honour opt-outs permanently | — | legal obligation, and the kill criterion needs the denominator |

**Total spend to reach step 9: about € 125**, on the cited KVK fee. Nothing in this repository
spends it, and no step above has been taken.

### What the owner must never delegate to this code

Signing or submitting a WBSO application, asserting to anyone that they qualify, sending mail,
and pricing. A wrongly-claimed WBSO is clawed back with penalties; the application is prepared *with*
the client and stands on facts only the client has.

---

## 3. The frozen test — decided now, before any send

Written before a single email exists, so it cannot be moved afterwards. This is the programme's
standing method (freeze, then test) applied to a non-market claim.

> **Hypothesis under test:** *an evidence-backed, personalised artifact earns a reply from a cold
> B2B recipient where a generic pitch does not.*
>
> **KILL — fewer than 2 replies per 100 briefings delivered.** Stop. Do not rewrite the email and
> try again: the thing that failed is the hypothesis the entire mechanism rests on, not the wording.
> T26 §8 notes that mechanisms #1, #3, #4 and #6 share this acquisition channel, so a kill here
> falsifies four entries at once, which is exactly why it is worth measuring first.
>
> **CONTINUE — 2 or more replies per 100.** Proceed to 500.
>
> **WIN — one signed no-cure-no-pay engagement within 45 days of the first send.**
>
> **Denominator rules, so the test cannot be quietly gamed:** *delivered* means accepted by the
> recipient's mail server, not sent. A reply is any human response including a refusal; an
> auto-reply, a bounce and an opt-out are **not** replies. The 100 are counted in one continuous
> batch, not cherry-picked across batches. If the run is stopped early, it counts as a kill.

---

## 4. The honest base rates

| claim | figure | status |
|---|---|---|
| NL-located GitHub organisations | **19,575** | ours, measured 2026-08-19 |
| NL participants in the Peppol Directory | **112,678** | ours, measured 2026-08-19 |
| of 165 sampled NL orgs, share owning a **non-fork public repo pushed since 2026-02** | **17 %** (28/165) | ours, measured |
| of those 28, share surviving every exclusion rule | **68 %** (19/28) | ours, measured |
| **end-to-end: briefable candidates per 100 NL GitHub orgs scanned** | **≈ 12** | ours, measured; a scanner statistic, not a truth statistic |
| of 19 kept candidates, share with an NL legal entity corroborated in Peppol | **0 %** (0/19) | ours, measured — see the note below |
| **reply rate to a cold personalised B2B briefing** | **unmeasured** | this is the whole risk; §3 measures it |
| NL subsidy-advisor fee, no cure no pay | 10–20 % of realised benefit | industry practice, cited in T26, not verified by us |
| typical WBSO benefit, small dev firm | € 15–40k | cited in T26, not verified by us |
| median-honest first year, one operator | 2–5 clients, € 6–25k | T26's estimate, not a measurement |
| WBSO annual national budget | ~€ 1.8 bn | cited in T26, not verified by us |

**The row that matters is the reply rate.** Every euro figure below it is conditional on a rate
nobody in this programme has measured. Treat the industry rows as priors from people who sell the
service, not as results.

**Two measured rows deserve reading twice.** First, **17 %** — T26's §2 subsample suggested 44 % of
NL GitHub orgs had pushed recently. That subsample came from an unpartitioned best-match search,
which surfaces prominent organisations; a sample stratified across creation years finds far fewer.
The recent-activity population is roughly **3,300 organisations, not 8,000**. Second, **0/19 Peppol
matches**: the directory holds 112,678 NL participants, but they are the firms that e-invoice
government and large customers, and a strict exact-name match finds none of nineteen small GitHub
orgs. Peppol corroborates the kind of company we are *not* mostly finding. Both numbers make the
population smaller and the identity gap wider than T26 assumed, and neither was visible before the
scanner existed.

### What would make this build worthless

- **Reply rate below the kill line.** Then the artifact does not work and no amount of scanning fixes it.
- **The population proxy.** "GitHub org located in NL" is a proxy for "NL SME doing R&D". Our own
  first probe returned JetBrains as hit #1 — a large foreign org with a Dutch office. The exclusion
  rules exist for that, and the dry run reports how many they drop and why, but precision can only
  really be judged by a human reading dossiers.
- **Owner hours.** Steps 7–9 are hours of the owner's own time per batch. If those hours are not
  available, this mechanism is unavailable, and T26's honest fallback is its #2 or #7/#8.
- **Saturation.** If per-company AI briefings become universal, inboxes saturate and the artifact
  stops working. T26 assumes a 12–24 month window; the durable asset is the client relationships and
  the domain knowledge, not this code.

---

## 5. Legal and data-protection posture

Not legal advice; this is what the build assumes and where the owner must check.

- **Email to businesses (Telecommunicatiewet 11.7).** NL permits unsolicited B2B email to a legal
  person, provided sender identity and a working opt-out are present. Every briefing carries a
  sender block (name, trading name, KVK, address, email, phone), the reason the recipient received
  it, and an opt-out instruction. The opt-out must be honoured permanently and logged.
- **AVG/GDPR.** Only *business* contact information from public sources is collected. Lawful basis:
  legitimate interest (art. 6(1)(f)); retention 12 months after last contact, stated in the briefing.
  The scanner stores no personal names. `params/sender_profile.json` and `data/` should not be
  committed with real contact data.
- **robots.txt and rate limits.** `wbso/http_client.py` consults robots.txt for every non-API host,
  refuses any Authorization/token header by construction, throttles per host, caps every run with a
  request budget, and logs every request to `logs/requests.jsonl`. Company websites are fetched only
  with `--fetch-sites`, at most two pages each (homepage + one careers page linked from it).
- **No affiliation.** Briefings state that the sender is independent and does not act for RVO or the
  Belastingdienst.
- **Parameter freshness.** `params/rvo_wbso_2026.json` was read off RVO on 2026-08-19 and carries
  every source URL and quote. **The 2027 calendar was not published on that date** — the 20 December
  2026 deadline in the briefings is RVO's standing rule ("wilt u vanaf 1 januari gebruikmaken,
  dien dan uiterlijk 20 december in"), not a date RVO has printed for 2027. Re-check before sending.
  There is also a nearer deadline: **30 September 2026** for an extra application covering
  October–December 2026.

---

## 6. What the owner should judge on this sample

The dry-run briefings exist so this question can be answered before any money is spent:

1. Does the evidence section make you think *"they actually looked at us"* — or *"mail merge"*?
2. Is the uncertainty paragraph believable, or does it read as a disclaimer bolted on?
3. Would telling the reader they can do it themselves (§7 of each briefing) lose the sale, or is it
   the reason a sceptical Dutch engineer replies at all?
4. Of the 10 candidates, how many are plausibly real NL SMEs doing R&D? That fraction is the
   precision of the whole population proxy, and nothing in this code can measure it.

---

## 7. A correction to T26 §7

T26's day-1 plan named "the winning-supplier names in the 2,214 TenderNed awards we already hold" as
a second candidate population. Probed on 2026-08-19: the awarded supplier's name is **not in the
TenderNed API** — not in the publication list, not in the publication detail. `detail_fields` in
`logs/probe_report.json` shows the full field inventory; the supplier appears only inside the award
PDF. Building on that assumption would have failed after the build, so TenderNed is implemented here
as what it can actually deliver for free: a demand signal (which public bodies are buying software
work), not a supplier list.

The Peppol Directory correction runs the other way. T26 §2 recorded it as "200 but 0 matches on our
query syntax". The working syntax is `?q=<name>&rpc=<n>` / `?country=NL`, and it returns 112,678 NL
participants with KVK and BTW identifiers — a free, partial route around the paywalled KVK API. It
is used only as corroboration, and the matched identifier is deliberately kept out of the briefing.

---

## 8. Layout

```
params/rvo_wbso_2026.json          frozen RVO parameters: every number with URL, date and quote
params/sender_profile.example.json placeholders only; the generator refuses to call a briefing sendable
wbso/params.py                     load + validate the freeze
wbso/benefit.py                    the arithmetic (proven against RVO's three worked examples)
wbso/http_client.py                budgeted, robots-aware, credential-refusing HTTP with receipts
wbso/model.py                      Candidate and Evidence: nothing enters a briefing without a URL
wbso/sources/github_orgs.py        population + R&D evidence
wbso/sources/peppol.py             NL legal-entity corroboration
wbso/sources/tenderned.py          demand signal + the measured negative in §7
wbso/sources/website.py            liveness + careers signal, robots-permitting, opt-in
wbso/scanner.py                    funnel, scoring, exclusions (each with a reason)
wbso/briefing.py                   the Dutch briefing and the owner dossier
wbso/ethics.py                     the ethical spine as a linter
wbso/cli.py                        probe · scan · brief · dryrun · rescore · lint  (no send)
tests/                             108 hermetic tests (arithmetic, ethics linter, rules, client, briefing)
briefings/                         dry-run output: NN_login.md + NN_login.dossier.json
logs/                              request receipts, probe/scan/briefing reports
DRYRUN_REPORT.md                   the last dry run, with its funnel and losses
```
