# Birth-origin V1: specification before signal inspection

Author: Codex. Date: 2026-09-08 UTC. Status: working hypothesis; observation only.

## Hypothesis and difference from the previous experiment

When several unrelated launch actors independently reuse a name fragment, attention
may accrue to the earliest *already observed* coin using that fragment. The proposed
recipient is that earlier coin, not the newly launched copy. This is a testable
cross-mint information channel, not a claim that similar names establish a narrative,
independent actors, demand, or positive returns. Creation can include a buy in the
same transaction: a creation event does not imply an opportunity before any price move.

The existing NARRATIVE_FORMATION_PREREGISTRATION.md scores the new coin from prior
launches and evaluates first-sighting returns. That contract remains unchanged. This
instrument observes when a fourth exact-identity group arrives and identifies the
earliest supporting mint in the preceding six hours. It does not rank on price,
volume, wallets' past profits, future graduation, listing, or subsequent bar counts.

## Frozen observer mechanics

- Source: complete chain-enumerated CreateEvent records, ordered by slot, transaction
  index, outer instruction index, inner instruction index. A transaction is the
  indivisible observation boundary. None of its sibling creates can count as prior
  evidence for another sibling. Malformed, duplicate, conflicting, or unordered
  records refuse visibly. Backward block clocks refuse rather than reorder chain truth.
- Universe for this bounded prototype: native-SOL, non-Mayhem launches. All other
  launches remain counted as explicit scope exclusions. No graduation or price joins
  enter the observer. Missing creator/user identity is unavailable, not independent.
- Text: Unicode NFKC + casefold, alphabetic words of at least three characters from
  name and symbol. Fixed stop words are in code; no vocabulary learned on the full
  window, external text, embeddings, or hand-tagged current themes.
- At each transaction, for each word use births in [t-6h, t) and earlier transactions.
  Pool creator and user addresses in one identity space. Connected components are
  ONLY transitive exact-address equality across these two roles, using every already
  observed creation as identity context, including other words and older births.
  A later bridge never rewrites an earlier observation. Shared funders are
  not inferred; independent economic ownership remains unverified.
- Emit when the transaction raises a word's group count from fewer than four to at
  least four. Choose the earliest prior mint carrying the word in that window. That
  mint is called first-in-observed-window, not the global original. If it shares an
  exact identity component with the arriving transaction, refuse the candidate.
- Require six hours of preceding enumerated history. Each candidate mint is emitted
  at most once per replay, even across words. The threshold and lookback are inherited
  from the existing formation proposal, not selected using outcomes.
- Every observation is NO_TRADE. Historical replay is historical_oracle, never a live
  receipt or executable decision. No price, fee, order, wallet, or network adapter exists
  in the observer. It is not an operational paper or live trading bot.

## Hostile checks and gates

Before any entry-screen or return evaluation, identify the owner's +354%/-49% pair and
their actual entry instants and reconstruct these exact features there. No pair-specific
parameter fitting is allowed. Missing evidence means unavailable, never a fabricated pass.

Future observations must not change any prior output. Renaming a future coin must not
make a past word eligible. Creator spam, creator/user bridges, same-transaction births,
duplicate mints, absent actors, and partial lookbacks are negative controls. A known
synthetic four-actor wave is a positive control. Placebo formation diagnostics permute
name/symbol payloads within exact-identity groups while preserving their event times;
they test temporal text association only, not profitability. Retain all preset seeds.

The already inspected B11a corpus is development evidence only. Its <24-hour launch
span cannot satisfy three disjoint daily replications, much less weeks of returns.
No old strategy grid or old return result is rerun. No positive performance claim may
come from this replay or from the lexical signal's prevalence.

Any later money test needs a separate frozen, fresh observation cohort and actual
post-observation route quotes. Use the user's next REAL bar/open convention for a
historical diagnostic, one position per mint, mint-equal mean AND median, resolution
rates at every horizon and -30/-50/-100% missing-exit stresses. The supplied 1.14%
round-trip toll is a historical diagnostic scenario; executable costs must reconcile
the route/version/notional at each side. No API dropout is proof of an LP withdrawal.

Profitability placebo tests must rerun the WHOLE strategy-selection pipeline with
creator/day/funding dependencies preserved and labels shuffled in appropriate blocks.
Reject if noise produces as many survivors. The formation-only placebo is insufficient.
Require positive net mean and median under full-loss stress, creator/wallet/funding
dependency controls, removal of the best mint and best day, multiple fresh weeks, and
the repository's execution/promotion gates. Stop if delayed copies dominate, the
source coin already moved before observation, signals are too rare, or their route
cannot pay costs. Live money is not enabled by this specification.

## Explicit conflict resolution

The owner's current instruction supersedes the old trade-pooled -2.92% benchmark:
use the stated mint-equal -14% to -23% range as context, not a mismatched control for
a new cohort. Dropout penalties are sensitivity scenarios, not actual fills or proof
of death. Old PLAN.md current-status paragraphs are historical; later dated retirement
decisions govern old bots. The user's newly requested non-price experiment is scoped
separately and reactivates none of those retired instruments. All raw evidence remains
unchanged. A negative unconditional market mean does not mathematically exclude a
positive conditional subset; equally, it supplies no evidence that this subset exists.

Engineering correction before any price/return evaluation: the first implementation
formed exact-identity groups inside each word's supporting births. That missed known
creator/user bridges on other words. The corrected observer carries one causal identity
graph across all births. Two additional adversarial controls reproduce the missed bridge
and forbid future bridges from rewriting prior outputs. The first output directory is
preserved as engineering-invalid for this cross-word identity requirement; no threshold,
horizon, stoplist, null seed, or economic result was selected or altered from its counts.
