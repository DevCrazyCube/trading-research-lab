# B19G Erratum 1 — the censoring statement describes the wrong population

**Binds to.** `research/B19G_EVALUATION_RESULT.json`, result sha256
`8e5c66d3a06d58c6b8eee323d79de30e55ddca12c098cfaa9a7d3fda1a302f1e`, ledger entry 3
(`B19G_CAPACITY_WALL_HISTORICAL_V3`, window
`dccb911d1fcde8b277d5f07d9f1629f98ae8539a619b2a1348a9ee712e847676`).

**No number changes.** Not one figure, count, order statistic or refusal tally in B19G is affected.
The result artifact remains byte-identical and its ledger entry is untouched. This erratum corrects
a factual claim *about* the population, not a measurement *of* it.

**Authorised by the owner**, on the recommendation of both reviewing seats, who each argued for an
erratum over a V4 and a re-run.

---

## The defective sentence, verbatim as published

> conditioned on cells where BOTH an entry and an exit account checkpoint exist; B15f schedules from
> B15a, which B15k measured holding 29% of the launches B15i observes, so this population is
> censored by the recorders and not by the market

It appears in every group of B19G's `family`, under `summary.censoring`.

## Where it came from

`B19C_CAPACITY_WALL_SIZE_DEPENDENCE_V1` requires this statement **verbatim** beside every figure,
and `b19c.verify_preregistration` refuses on any drift from it — a paraphrase would misdescribe the
population, so the rule exists for good reason and is enforced.

`B19G_CAPACITY_WALL_HISTORICAL_V3` inherits B19C's reporting rules by pin, deliberately and
wholesale, so that only the population clause and the monotonicity method differ. The verbatim
requirement came with them.

**The mechanism worked exactly as designed.** Nothing failed, nothing drifted, no check was
bypassed. The gap is in the rule's *scoping*: B19C bakes a population-specific factual claim into a
reporting requirement, so inheriting the requirement faithfully onto a different population
transports a false statement with it. Verbatim inheritance is the right default for a rule about
*wording*; it is the wrong default for a rule whose wording contains an empirical claim.

## Why it is false for B19G

B15i, B15f, B15a and B15k are the **live shadow-feed recorders**. They record which launches a
running process actually caught. A historical corpus has no such record — that is precisely why
B19G exists as a separate study from B19C, whose population is B15M's capture-based universe and
cannot be rebuilt from a recorded chain.

No cell in B19G was censored by a recorder, because no recorder was involved.

## The correct censoring, in one sentence

> B19G's population is censored by three conditions on the historical window and by no recorder at
> all: the curve must carry a t0 coordinate and a decodable fee schedule (3,196 of 3,932 evaluable
> curves do), the first observation at or after `t0_slot + delay` must fall within B15L's inherited
> 150-slot lateness tolerance, and an exit state must exist at the horizon — so the censoring is a
> property of what the chain recorded and of the frozen admission rules, not of any process that
> was or was not watching at the time.

That sentence is given in full because the wrong one is exactly the sentence a reader would quote,
and an erratum that only says "the other sentence is wrong" leaves them with nothing to quote
instead.

## What this does not license

- It does not change any B19G figure, and none may be restated on the strength of it.
- It does not apply to B19C or B15M, whose own runs used the capture-based population the sentence
  correctly describes.
- It is not a claim that B19G's population is *less* censored. It is differently censored, and the
  share is stated: 3,196 of 3,932 carry a schedule, and the grid-executability counts in the result
  show how few of those carry a book of any depth.

## Forward note — not retroactive

Any future study that inherits B19C's reporting rules onto a different population must **scope or
restate the censoring clause at freeze time**, in its own preregistration, before it runs. This
applies from B19H onward. It is deliberately not applied retroactively: B19G's document is frozen,
its pass is spent, and rewriting a frozen document to repair a statement is the move this project
has refused every other time it came up.
