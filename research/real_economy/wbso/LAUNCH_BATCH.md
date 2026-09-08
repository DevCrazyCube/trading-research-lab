# WBSO — vetted launch batch (owner review)

> **Honest status, 2026-08-19.** This is the ethics-linter-clean set the tool can stand behind **right now** — **8 briefings**, every one passing `wbso.cli lint` (no eligibility assertion, no unsourced URL, all required disclosures present). Each is stamped **CONCEPT — NIET VERZENDEN**. Nothing has been sent; no account, domain, or money exists.

## Why 8 and not 25

The plan was to top the batch up to 25. Run honestly against the **existing package unchanged**, it does not reach 25 cleanly, and the guardrail is explicit — *never pad with junk to hit a number.* What happened, plainly:

- A larger scan (96 fresh NL GitHub orgs) was run and 20 new briefings generated. **The frozen ethics linter rejected all 20** — each carried a website URL in the body with no matching evidence row (the rate-limited run did not complete the website-probe enrichment, so the linter failed *closed*, exactly as designed).
- The fresh pool also pulled in entities the exclusion rules should catch: **projectlombok** (worldwide Java OSS, not an NL SME), **eca-d** (European Climate Assessment dataset), **maritimeresearchinstitutenetherlands / MARIN** (a research institute — RVO: *u bent geen publieke kennisinstelling*).
- Regenerating overwrote two previously-clean briefings (Badge.Team, Yireo), so the clean core is now **8**, not the earlier 10. That was a cost of the top-up; owned, not hidden.

**The real finding:** the population of free-signal NL SMEs that passes *both* the exclusion rules *and* the fail-closed ethics linter is **thin — on the order of 10, not 25.** Padding to 25 means shipping linter-failing or non-SME briefings, which the guardrail forbids and which would poison the reply-rate signal.

## The 8 vetted briefings

| # | company | evidence rows | GitHub | file |
|---|---|---|---|---|
| 1 | Forkbomb | 8 | https://github.com/ForkbombEu | `briefings/02_forkbombeu.md` |
| 2 | Datastudy | 8 | https://github.com/datastudy-nl | `briefings/03_datastudy-nl.md` |
| 3 | WeProDev | 8 | https://github.com/weprodev | `briefings/04_weprodev.md` |
| 4 | Netherlands IT | 5 | https://github.com/NetherlandsIT | `briefings/06_netherlandsit.md` |
| 5 | CreateWorker | 6 | https://github.com/CreateWorkerAI | `briefings/07_createworkerai.md` |
| 6 | Codar B.V. | 5 | https://github.com/codarBV | `briefings/08_codarbv.md` |
| 7 | Cre8-IT | 5 | https://github.com/Cre8-IT-Code | `briefings/09_cre8-it-code.md` |
| 8 | FYN Software | 4 | https://github.com/FYN-Software | `briefings/10_fyn-software.md` |

Each briefing links every claim to a public source with a read-date, quotes RVO's 2026 parameters, states the reader **may** qualify (never that they do), tells them they can apply themselves free via RVO's WBSO-wijzer, and carries the Telecommunicatiewet 11.7 / AVG sender + opt-out block. The KVK number (where a Peppol name-match exists) is in the private `*.dossier.json`, never in the recipient copy.

## Recommendation

1. **The launch decision does not need 25.** Eight vetted, evidence-clean briefings are enough to send the first tranche and start measuring against the pre-frozen kill criterion (**<2 replies per 100 delivered = STOP**). Quality of the 8 is what tells you whether this is worth pursuing — read two or three.
2. **To reach ~20-25 cleanly, a small tool fix is needed (a follow-up task), because T28 was scoped to leave the package unchanged:** (a) make the briefing generator drop any website URL it has no evidence row for (so incomplete enrichment yields a shorter *clean* briefing instead of a linter failure), and (b) add hard exclusions for research institutes and worldwide OSS projects. That recovers ~5-8 legitimate SMEs already seen — NAVARA, Creative Fabrica, KE-works, Techonomy, Staxxer — toward a real 20+.
3. **Owner steps unchanged:** register a KVK (~€85) + domain/mailbox (~€40/yr), fill the sender profile (fills the opt-out link), read/approve, send personally. No send code exists in the package.

