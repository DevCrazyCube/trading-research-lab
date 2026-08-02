# Point-in-time concentration schema — v1.0.0

Produced by `scripts/b13d_concentration.py`. Read-only: consumers must treat every record as
immutable and must pin `schema_version`.

Status: **Phase 3 foundation, raw arithmetic only.** No RPC has been queried, no threshold has been
chosen, no cluster exists, and every snapshot exercised so far is synthetic.

## Concentration is whatever the denominator says it is

Divide by total supply and a token whose bonding curve holds 90% of it looks broadly distributed.
Divide by circulating user balances and the same holdings look extreme. **Both figures are true**,
and publishing one of them is a choice made on the reader's behalf — the single easiest place in
this project to produce a number that flatters.

So every share is published under **both** denominators, side by side, and a record carrying only
one is refused.

| denominator | value | balances ranked |
| --- | --- | --- |
| `total_supply` | the declared supply | **every** account, including the curve's |
| `circulating_user` | the **sum** of `user`-role balances | user accounts only |

The two views differ in **numerator as well as denominator**, so each block publishes its
`scope_roles`. A reader given a ratio without the scope cannot tell which one they have.

**The circulating denominator is a sum of inclusions, never supply minus exclusions.** A sum names
what it included; a subtraction hides what it removed. A record whose published circulating
denominator does not equal the user-role total is refused — that mismatch is exactly how an
exclusion hides.

## Roles: unknown is never a user

| role | meaning |
| --- | --- |
| `user` | an ordinary holder; **the only role counted as circulating** |
| `bonding_curve` | the curve's own reserve |
| `vault` | a protocol or team vault |
| `burn` | an address the tokens cannot return from |
| `program_owned` | held by a program, not by anyone deciding |
| `unknown` | nobody established what this is |

Counting `unknown` as `user` would enlarge the denominator and shrink every share — the flattering
direction, and therefore the one refused by construction. Every role is published with its account
count and units even when empty, and the roles must account for **every** unit and **every**
enumerated account.

Each account states its own `role` and non-empty `role_evidence`. A role asserted without evidence
is a guess that will be read as a fact.

## Accounts are not owners

One owner can hold many token accounts, so collapsing changes every figure here. Both groupings are
published:

- `by_account` — always available;
- `by_owner` — **only when every account has exact owner evidence.**

One unresolved account blocks collapsing entirely, because that account could belong to the largest
holder and a top-1 computed without it is a lower bound wearing the costume of a measurement. When
collapsing is unavailable the block says so with a reason rather than quietly ranking accounts.

An account is either `exact_owner_evidence` with an owner and evidence, or `unresolved` with
neither. An unresolved account naming an owner is refused — unknown is not a name we happen to have.

## Reconciliation is not optional

| condition | outcome |
| --- | --- |
| the same token account twice | refused |
| a negative raw balance | refused, never clamped |
| a second mint in the enumeration | refused |
| mixed decimals | refused |
| an undeclared or evidence-free role | refused |
| an unresolved account naming an owner | refused |
| accounts holding more than the declared supply | refused |
| `enumeration_complete` with a non-zero residual | refused |
| an enumeration count disagreeing with the accounts present | refused |
| an enumeration naming no sources | refused |

A negative balance is refused rather than clamped: it means the decode is wrong, and clamping would
turn a broken parse into a plausible holder.

**The residual is published, never absorbed.** `supply_residual_units` is the declared supply minus
what the accounts hold, and `held + residual == declared_supply` is asserted on every record. An
incomplete enumeration with a residual is legitimate; one claiming completeness is not.

**Zero-balance accounts are kept.** They stay in `accounts_enumerated`, appear in
`zero_balance_account_count_observed`, and are excluded from every holder count and ranking.
Dropping them would change a holder count nobody was told about.

## Exact arithmetic, no floats

Every share is a gcd-reduced `{numerator, denominator}` pair. A raw supply of 10^15 units does not
survive a double, and a rounded number here later reads as a measurement. Comparisons cross-multiply
rather than converting to a decimal. A rational not in lowest terms is refused: two equal shares
must have equal representations, or a hash comparison silently says they differ.

The Herfindahl index is `Σbᵢ²` over `D²` — a **single** exact ratio, not a sum of rounded squares,
which is where a float implementation loses the small holders entirely.

## Top-k

`top_1`, `top_5`, `top_10`, each publishing `share`, `units`, `entries_available` and
`entries_counted`. A top-k must take exactly `min(k, available)`: taking more is not a top-k, taking
fewer silently understates concentration. The counts are published because a "top 10" over seven
accounts is the whole set, and a reader not told that will compare it against a genuine top 10
somewhere else. Monotonicity across k is asserted — a top-1 exceeding a top-10 is arithmetically
impossible and means the ordering or the summation is wrong.

Ranking is descending by balance, then ascending by key, so ties order deterministically.

## The creator share

Published under both denominators, and only when:

1. `creator_binding.status` is `exact_binding` with an address **and** evidence, and
2. **every** account's owner is resolved.

Otherwise the block is `defined: false` with the reason. An unresolved account could be the
creator's, so any figure computed without it is a lower bound, not a share.

The creator's units are **scoped exactly like the denominator**. A creator holding through an
excluded role would otherwise contribute to the numerator but not the denominator, and produce a
share above one.

## Absence is not zero

An empty denominator yields `defined: false` with an `undefined_reason`, never a `0/1`. A token
whose entire supply sits in the curve has **no** circulating-user share — that is undefined, and
reporting it as zero would be the most confident possible way to be wrong.

`select_snapshot` returns `Absent(not_yet_known)` when nothing exists at or before t0, and its
detail says the quiet part: *not knowing the concentration is not the same as it being low*.
`Absent` raises on `bool()`.

## Point in time

> A holder-balance snapshot may inform a decision at t0 only if its own canonical coordinate is at
> or before t0's.

Inclusive at t0, exclusive one coordinate later. A later holder state cannot be backfilled: the
balances that existed *after* a decision are not the balances it was made against, and using them
would encode the outcome in the input. The rule travels on every record and a record carrying any
other is refused.

## Cluster adjustment is structurally unavailable

`cluster_adjusted_concentration` and `connected_components` both exist and both raise
`ClusterAdjustmentRefused`. `ACCEPTED_CLUSTER_ARTIFACT_TYPES` is **empty** — not "no artifact was
supplied" but "no artifact type is acceptable yet".

A cluster-adjusted concentration is the most dangerous number this project could publish: it looks
like a measurement, it moves in the direction that justifies action, and every input to it is a
judgement.

**A B13b association ledger passed as a cluster map gets its own refusal**, naming what it actually
is. It declares itself `uncalibrated_evidence_only`, its links are pairwise observations that
explicitly do not assert common control, and it refuses transitive closure by construction. Passing
it here would launder an explicit "we do not know" into a merge. It is recognised by its
self-declaration **or** by its shape — either alone is enough, because a caller stripping one of
them is exactly how the mistake happens.

A future artifact must be:

- **calibrated** against a validation set that is not the one it will be used on;
- **preregistered** — merge rule and threshold frozen before the cohort was enumerated;
- **complete and point-in-time** — every link from evidence at or before t0, over a neighbourhood
  whose completeness is asserted rather than assumed;
- **provenanced** — naming its inputs, its rule and its hash.

**The record carries no cluster field of any kind.** B13b's judgement applies unchanged: a field
named for a quantity we refuse to compute teaches the next reader that we compute it. Any field
whose name contains `cluster`, `adjusted`, `probability`, `score`, `threshold`, `veto`, `rug`,
`profitab`, `risk_`, `verdict`, `label` or `predict` is refused anywhere at any depth.

## Determinism

Canonical JSON with sorted keys; `snapshot_sha256` and `concentration_sha256` each over everything
but themselves. Account order never changes a result.

## Future token-account capture — required before any real snapshot

No RPC is queried here and none may be until these are settled. They are written down now because
each is a decision that would otherwise be made implicitly by whoever writes the fetcher:

1. **Enumeration must be complete or say it is not.** A paginated `getProgramAccounts` scan that
   silently truncates produces a snapshot whose top-k is a lower bound. The cursor, page count and
   termination condition go into `enumeration_method`, and any short read sets
   `enumeration_complete = false` with the residual published.
2. **The snapshot must be atomic at one slot.** Balances read across a range of slots are not a
   snapshot of anything; a transfer between two reads can appear twice or vanish. Capture must pin
   a slot and record it as the `as_of` coordinate, with the RPC's own slot response as
   `receipt_provenance`.
3. **Owner resolution needs the account data, not a guess.** The SPL token account's owner field is
   the evidence; an owner inferred from a transfer history is `unresolved`.
4. **Roles need a pinned roster.** The bonding curve's associated token account is derivable and
   therefore exact; vaults, burns and program-owned accounts need an evidence source that is cited
   per account. Everything else is `unknown`, and `unknown` is not `user`.
5. **The declared supply must come from the mint account at the same slot**, not from metadata and
   not from a provider — otherwise the residual measures the disagreement between two sources
   rather than the units nobody enumerated.
6. **Cohort-scoped, like B13a's plan.** Snapshots are captured only for the mints an enumeration
   produces, at instants that enumeration defines, and never for a wider population that is then
   filtered.
7. **Credentials are environment-only and never persisted**, and the endpoint identity belongs in
   `receipt_provenance` as a hash, not in the clear.

## Measured

```
python scripts/b13d_concentration.py --contract
python scripts/b13d_concentration_fixtures.py --gate
```

See `research/B13D_CONCENTRATION_FOUNDATION.md`.

## Not covered

- Any concentration threshold, veto, profitability class or rug label — **none is chosen**.
- Any cluster, merge, component or cluster-adjusted figure.
- Any real concentration value or distribution.
- The burned corpus and B11a. Neither is opened by anything in this module.
