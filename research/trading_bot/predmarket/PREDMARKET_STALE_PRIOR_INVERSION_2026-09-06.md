# PREDMARKET — the agent's "structural base rate" edge is INVERTED, and that kills the last
# non-news thesis in this instrument

**Date:** 2026-09-06 (predmarket tick, hour 21, CHUNK D)
**Status:** THESIS KILLED. No estimate frozen; logged as an abstention in
`PREDMARKET_PREREGISTRATION_LOG.jsonl`. No spec edited, no bet, no money.
**One line:** where an LLM's institutional base rate diverges most from a deep, liquid,
internally-coherent prediction market, that divergence measures **the agent's staleness**, not the
crowd's error — so the divergence's own magnitude is an anti-signal.

## 1. Why this thesis was next

The non-news, non-memory-contaminated edge sources in a prediction book are being exhausted in order:

| thesis | screened | verdict |
|---|---|---|
| cross-market **coherence violations** | 2026-09-02 | dead — zero exploitable, 5 false-positive traps |
| **family underround** | 2026-09-03 | dead — 1 candidate, killed on depth-walk + carry (≈ −$20) |
| **favourite–longshot bias** (short the tail) | 2026-09-05 | dead — arithmetically unshortable below the carry threshold |
| **stale-institutional-base-rate fade** | **this tick** | **dead, and worse than dead — inverted** |

The survivor thesis was the most attractive-looking one left, because it needs **no post-cutoff fact**.
The claim: for questions governed by durable institutions (a managed-autocracy parliamentary election,
a hereditary/clerical succession), the base rate is a structural constant an LLM knows cold, and a
retail crowd chasing headlines will drift away from it. That is a real, textbook edge shape.
It is also, as measured below, backwards.

## 2. The measurement (read-only, this tick)

`predmarket pull --no-resolve --limit 400` — 29,015 markets pulled, 28,466 selectable, top 400 by
volume displayed. Filtered to markets **not already in our book**, `0.20 < p_market < 0.85` (i.e.
deliberately ORTHOGONAL to the 69%-longshot-fade cluster documented in
`PREDMARKET_CORRELATED_BOOK_2026-09-06.md`), closing within 200 days → **29 candidates**.

Four of those candidates carry a price that my May-2026 institutional priors call near-impossible:

| market | p_market | what my prior says | prior-implied edge |
|---|---|---|---|
| New People (NL) win most seats, next Russian Duma election (close 09-30) | **0.256** | ~0.00 — NL held 13 seats vs United Russia's 324 in 2021, in an administratively-determined election | −0.25 |
| United Russia win most seats, same election | 0.675 | ~0.99 | +0.31 |
| **Mojtaba** Khamenei head of state of Iran, end-2026 | **0.849** | ~0.05 — implies the succession has *already* happened | +0.80 |
| **Gadi Eizenkot** next PM of Israel (Netanyahu 0.295) | **0.508** | ~0.03 | +0.48 |
| Nicolás Maduro leader of Venezuela, end-2026 | 0.828 | ~0.95 | +0.12 |

A naive reading: five fat mispricings, edges of 12–80 points, on a book where round-trip cost is
0.5 cents. That reading is wrong, and the reason it is wrong is the finding.

## 3. Why it is an anti-signal, not an edge

**The books are not thin, and they are not incoherent.** Both are the standard excuses for a fat
apparent edge, and both are excluded by measurement:

| family | legs seen | sum(ask) | sum(bid) | total volume |
|---|---|---|---|---|
| Iran head of state end-2026 | 8 | 0.939 | 0.918 | $24.2M |
| Venezuela leader end-2026 | 12 | 0.978 | 0.954 | $51.7M |
| Israel next PM | 16 | 0.982 | 0.943 | $34.1M |
| Russian Duma, most seats | 7 | **1.006** | 0.980 | $23.7M |

(Sums below 1.0 are truncation — only the volume-ranked top 400 markets were displayed, so the
low-volume tail legs of each family are missing. No family is arbitrageable; the Duma family, seen
complete, overrounds by 0.6%.)

So: tens of millions of dollars, tight two-sided books, arithmetically coherent leg sets, all
simultaneously agreeing on a world-state that my priors call absurd. The likelihood ratio runs the
wrong way for us. `P(a $24M coherent book is wrong by 80 points)` is far smaller than
`P(a model with a May-2026 cutoff has missed four months of world history)`.

And the four months are visibly load-bearing: Mojtaba Khamenei at 0.85 to be head of state at
year-end is not a forecast about a possible succession, it is a book that has **already priced one
in**. Eizenkot at 0.51 ahead of Netanyahu at 0.30 is a book that has already priced in an Israeli
government change. These are not markets drifting from a base rate; these are markets that have
*re-based* on events after the cutoff.

**The inversion, stated precisely.** The agent's prior error is not independent of the size of the
apparent edge. The bigger the divergence between an LLM base rate and a liquid market, the more
likely it is that a regime-changing event happened after the cutoff — which is exactly the
condition under which the base rate no longer applies at all. Sorting candidate estimates by
`|q_prior − p_market|` descending — the natural way to rank a book for conviction — therefore sorts
them by **probability of agent staleness**, descending. It is a maximally adversarial selection rule.

## 4. Consequences for the instrument

1. **The stale-base-rate fade is dead.** It joins coherence, underround and longshot-carry. There is
   now **no non-news edge thesis left standing** in PREDMARKET1. Anything this instrument can still
   earn must come from *reading current information*, which is the Newsdesk's channel, not a prior.
2. **A hard proposer discipline follows** (recommended, NOT applied — the spec is frozen and editing
   it is an owner decision): refuse, or at minimum flag, any proposal whose thesis rests on an
   institutional/base-rate argument when `|q_agent − p_market| > ~0.25` on a market with volume above
   some floor. Under this rule all five rows in §2 are refused, which is the correct outcome.
3. **It compounds the correlated-book defect.** The one repair for a book that is 69% a single
   longshot-fade cluster is to add *orthogonal* estimates. This tick went looking for exactly those
   and found that the orthogonal candidates are precisely where the agent is least informed. The
   correlated-book defect is therefore **harder to repair than it looked**: we cannot diversify our
   way out of it with confident views, because our confident orthogonal views are stale-prior
   artifacts. Cluster-level scoring (the §"Required correction" in the correlated-book doc) remains
   the only honest fix.

## 5. Kill-condition for THIS finding

This finding is itself falsifiable, and cheaply: on 2026-10-01, the Russian Duma market settles. If
United Russia does win the most seats — i.e. the crowd's 0.675 was the mispriced number and my 0.99
prior was right — then the inversion argument is materially weakened on at least one family and this
document must be reopened. Recorded here so the check is mechanical and cannot be quietly skipped.
The abstention frozen this tick is what makes that a real, costless test: we take no position either
way and still get to read the answer.

## 6. What was logged

An abstention (`predmarket propose --no-trade`) citing the inversion. Zero estimates frozen. This is
a disciplined outcome, not an empty tick: the correct action on a book where every apparent edge is
a measure of our own ignorance is to not commit, and to write down why.
