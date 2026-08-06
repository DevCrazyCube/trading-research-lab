# B16d — could a follower trade a public creator re-entry?

**Answer: no, on this evidence.** Every one of the 18 frozen variants is negative at the median, for
the signal and for both baselines, and the signal fires on 110 of 1,136 curves before refusals cut it
to 23–58 usable cells.

**BURNED DEVELOPMENT DATA.** Not an evaluation result, not a return, not a recommendation.
`executable=false`, `performance_status=not_evaluated`, `execution_status=never_executed`.
Assumption: `UNREACTING_ORDER_FLOW`.

**Preregistration:** `research/B16D_CREATOR_REENTRY_SIGNAL_PREREGISTRATION.json`, canonical sha256
`b2b18193a5a559886d7eb1ea954b299816fe1a7cc78ea95bbdcda3d2a7229585`, committed **alone at `1a7b49d`
before any outcome below was computed**. **Artifact:** `research/b16d/signal.json`.
**Guards:** 27 tests, mutation sweep 11/11 killed.

## The question, and what the follower is

B16b and B16c measured what creator-equal wallets did. This asks whether somebody *watching* them
could have done anything with it. The outcome is priced entirely from a hypothetical follower's own
entry and exit; **the creator wallet's own flow never enters the arithmetic**, and a test reads the
AST of the pricing function to confirm it cannot.

## Selection coverage, stated before any outcome

| | |
|---|---|
| curves in the cohort | 1,136 |
| curves with a creator re-entry signal | **110 (9.7%)** |
| curves with a non-creator buy signal (baseline) | 727 |
| curves with a decodable fee schedule | 960 |
| curves whose decodable schedules disagreed, refused | 17 |

Refusals on the signal family: **927 capacity-refused**, 258 right-censored, 6 with no entry
observation, 6 with no fee schedule. The capacity gate — B15M's, against the *observed* exit book — is
by far the largest, which is B15M's result appearing again from a different direction.

**The observability gate cost nothing here: zero same-slot-only opportunities.** Every signal that
produced a usable cell had a later-slot entry available, so refusing same-slot capture removed no
evidence. That was not knowable in advance, which is why the rule was frozen first.

## Outcomes: every variant negative at the median

Net lamports after full executable costs, in SOL, base scenario. Creator signal against both frozen
non-model baselines, on the same machinery and denominator:

| size | horizon | delay | creator n | median | any-buy n | median | launch n | median |
|---|---|---|---|---|---|---|---|---|
| 0.001 | 1,000 | 1 | 58 | −0.0023 | 284 | −0.0024 | 305 | −0.0024 |
| 0.001 | 10,000 | 1 | 38 | −0.0023 | 158 | −0.0025 | 164 | −0.0025 |
| 0.010 | 1,000 | 1 | 55 | −0.0025 | 264 | −0.0039 | 284 | −0.0035 |
| 0.010 | 10,000 | 1 | 34 | −0.0026 | 144 | −0.0053 | 149 | −0.0047 |
| 0.100 | 1,000 | 1 | 43 | −0.0054 | 192 | −0.0170 | 197 | −0.0143 |
| 0.100 | 10,000 | 1 | 23 | −0.0054 | 91 | −0.0276 | 93 | −0.0262 |

(Delays 2 and 4 are in the artifact and move nothing material; all 18 variants are negative.)

The creator signal is consistently **less bad** than both baselines — at 0.1 SOL / 1,000 slots,
−0.0054 against −0.0170 and −0.0143 — but it is **never positive at the median**, and at 0.1 SOL /
1,000 slots 36 of its 43 cells (84%) are at or below zero, against 85% and 84% for the baselines. The
share of losing cells is indistinguishable; only the magnitude of the loss differs.

## The finding that decides the question

**The creator-signal median does not move with delay: −0.0054 at delay 1, at delay 2 and at delay 4.**

An information edge decays. If the creator buy carried a signal a follower could act on, waiting four
slots instead of one should erode it. It does not budge. What that pattern is consistent with is not
timing at all but **curve selection**: curves on which a creator re-enters are slightly better curves
to have traded, and entering them one slot or four slots later makes no difference because there was
never a decaying informational advantage to capture.

That also explains the gap to the baselines without needing an edge: the creator-signal cohort is 110
self-selected curves, while the baselines run on 727 and 1,136. Comparing a selected subset against
the whole cohort measures the selection, not the signal.

## Could a follower actually capture it?

**No, and three independent things block it:**

1. **It is negative.** Less negative than the alternatives is not a strategy.
2. **The capacity gate refuses 927 cells.** On most curves the observed exit book could not pay for
   the exit at these sizes, so the follower could not have got out — the same wall B15M measured.
3. **It fires on 9.7% of curves.** A follower waiting for this signal sits out nine curves in ten,
   and the ones it fires on are identified only *after* the creator has already bought.

## What this does not say

- It does **not** say creator re-entry carries no information — only that a follower entering at
  1/2/4 slots, at these three sizes, with these costs and capacity gates, on this burned corpus, was
  worse off than not trading.
- It is **not** an evaluation result. This is burned development data and cannot be reported as one.
- No threshold, delay, horizon or size was changed after seeing an outcome, and no variant was added.
  The preregistration hash is pinned in the code and a tampered document refuses.
- No wallet is recommended to follow, and no ownership was inferred anywhere.
- The `UNREACTING_ORDER_FLOW` assumption flatters every figure here: the observed path is replayed as
  if the follower's own order had not moved it, which it would have.
