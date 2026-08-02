# B13d — concentration is whatever the denominator says it is

Date: 2026-08-02. Author: Claude (handoff 86). Offline library and report only.
Code: `scripts/b13d_concentration.py`, `scripts/b13d_concentration_fixtures.py`.
Schema: `docs/CONCENTRATION_SCHEMA.md`. Tests: `tests/test_b13d_concentration.py`.

## 0. Scope, and what was not touched

Exact arithmetic and synthetic fixtures only. **No RPC was queried**, the burned corpus was not
opened, and **B11a was not read**. No threshold, veto, profitability class or rug label was chosen.
No cluster exists, no component was inferred, and no real concentration value or distribution was
computed on anything.

## 1. The number that flatters

A token's bonding curve holds 800 million of a billion units. One holder has 120 million.

Under total supply that holder has 12%. Under circulating user balances — the 200 million the curve
does not hold — the same holder has 60%. **Both figures are exactly right**, and they support
opposite conclusions.

That is the whole problem with concentration. It is not a hard measurement; it is a ratio, and the
denominator does all the work. Publishing one of the two is a choice made silently on the reader's
behalf, and it is the easiest place in this project to produce a number that flatters.

So this module publishes **both, always**, and refuses a record carrying only one. The two views
also differ in *numerator*: under total supply every account is ranked including the curve's, under
circulating user only user balances are. Each block therefore states its own `scope_roles`, because
a reader given a ratio without the scope cannot tell which one they are holding.

**The circulating denominator is a sum of inclusions, never supply minus exclusions.** A sum names
what it included; a subtraction hides what it removed. The record asserts that the published
circulating denominator equals the user-role total, and that mismatch is exactly the shape an
exclusion takes when it hides.

## 2. Unknown is not a user, and the direction of the error is why

`unknown` is a declared role, and counting it as `user` would enlarge the circulating denominator
and shrink every share. That is the flattering direction. A rule that errs toward "this token looks
fine" is not a rule, so unknown is excluded from circulating by construction and published as its
own line.

The same asymmetry runs through the rest of the reconciliation. A negative balance is refused rather
than clamped, because clamping turns a broken decode into a plausible holder. Zero-balance accounts
are kept in the enumeration and out of the holder count, because dropping them changes a count
nobody was told about. The supply residual is published rather than absorbed, because
`held + residual == declared_supply` is the only statement that makes "every unit is somewhere"
checkable.

## 3. Accounts are not owners, and one unresolved account stops everything

One owner holding four accounts of 100 million looks like four 10% holders by account and one 40%
holder by owner. The fixture corpus contains exactly that case, and the test asserts the two figures
differ — because if they ever stopped differing, the grouping would have quietly collapsed.

Collapsing requires **exact owner evidence for every account**. One unresolved account blocks it
entirely, and the reason travels on the record: that account could belong to the largest holder, so
a top-1 computed without it is a lower bound wearing the costume of a measurement. A lower bound
published as a share is precisely the kind of number that later gets compared against a threshold.

The creator share follows the same rule, and adds one of its own: the creator's units are scoped
exactly like the denominator. A creator holding through an excluded role would otherwise contribute
to the numerator but not the denominator and produce a share above one — an impossible figure that
would nonetheless render.

## 4. Exact rationals, and the Herfindahl in particular

Every share is a gcd-reduced numerator/denominator pair. A raw supply of 10^15 units does not
survive a double, and a rounded number here later reads as a measurement. Comparisons
cross-multiply.

The Herfindahl is computed as `Σbᵢ²` over `D²` — one exact ratio, not a sum of squared ratios.
Summing rounded squares is where a float implementation loses the small holders entirely, and the
mutant that does it is in the sweep.

The tests check this arithmetic against `fractions.Fraction` rather than against hand-copied
expected values. An oracle from the standard library is independent of the implementation; a
constant I typed after running the code is not.

## 5. What is undefined is not zero

A token whose entire supply sits in the curve has **no** circulating-user share. The block is
`defined: false` with a reason, and carries no `top_1` at all rather than a `0/1`.

`select_snapshot` returns `Absent(not_yet_known)` when nothing exists at or before t0, and its
detail says the quiet part out loud: *not knowing the concentration is not the same as it being
low*. This reuses B13c's `Absent`, which raises on `bool()`; the one addition this pass made to B13c
was a fifth reason, `undefined`, for values that cannot exist rather than merely being missing.

## 6. Cluster adjustment is structurally unavailable

A cluster-adjusted concentration is the most dangerous number this project could publish: it looks
like a measurement, it moves in the direction that justifies action, and every input to it is a
judgement. So the operation is exposed and always raises, `ACCEPTED_CLUSTER_ARTIFACT_TYPES` is
empty — not "none supplied" but "no type is acceptable yet" — and no component is inferred from
anything.

**A B13b association ledger passed as a cluster map gets its own refusal**, naming what it is. That
ledger declares itself `uncalibrated_evidence_only`, its links are pairwise observations that
explicitly do not assert common control, and it refuses transitive closure by construction. Passing
it here would launder an explicit "we do not know" into a merge, and the reader needs to be told
which mistake they made rather than getting a generic no. It is recognised by its self-declaration
**or** by its shape, and the tests drive each path alone — a caller stripping one of them is exactly
how the mistake happens.

**The record carries no cluster field at all.** B13b's judgement applies unchanged: a field named
for a quantity we refuse to compute teaches the next reader that we compute it. A test greps the
canonical JSON for `cluster`, `adjusted`, `threshold`, `veto` and `rug` and fails on any of them.

## 7. Measured — the synthetic fixture corpus

```
python scripts/b13d_concentration_fixtures.py --gate
```

| quantity | value |
| --- | --- |
| synthetic snapshots | 9 |
| synthetic accounts | 33 |
| snapshots reconciled | **9 / 9** |
| concentrations computed | **9 / 9** |
| both denominators published | **9 / 9** |
| every share an exact rational | **9 / 9** |
| top-k monotone | **9 / 9** |
| roles account for every unit | **9 / 9** |
| snapshot hashes stable | **9 / 9** |
| result independent of account order | **9 / 9** |
| owner grouping refused where evidence is missing | 1 fixture |
| owner and account groupings genuinely differ | 1 fixture |
| zero-balance account preserved | 1 fixture |
| undefined denominator not reported as zero | 1 fixture |
| supply residual published | 1 fixture |
| decision instants replayed | 3 |
| later snapshot refused at every instant | **3 / 3** |
| cluster adjustment / ledger-as-cluster-map / components refused | **yes / yes / yes** |
| errors | **0** |

**No concentration value appears in that report and none may**, and a test walks the report looking
for any numerator/denominator pair to prove it. A share published here would be read as a finding
about a token that does not exist, and the thresholds it would be compared against have
deliberately not been chosen.

## 8. Verification — 75 mutants, 75 killed, none disclosed

87 tests, 81 subtests.

Covering every failure mode the directive named: denominator swapping (6), curve balance silently
excluded (4), owner/account conflation (7), top-k off-by-one (8), HHI float and rounding (6),
duplicate owner accounts (2), unknown role treated as user (3), supply mismatch (6), future snapshot
leakage (5), incomplete enumeration promoted to complete (3), creator binding error (6), a B13b
ledger passed as a cluster map (7), source and hash drift (4), plus mixed mint/decimals (2) and the
gate's own conditions (7).

**Five survived the first run and every one was a genuine gap:** no test broke the per-role *account
count* sum; the two association-ledger recognition paths were only ever exercised together, so
either alone could be deleted; nothing asserted the denominator rule on the computed record; and the
ranking tiebreak was unobservable through the published sums.

That last one is worth stating plainly. Under ties the published figures are equal whichever order
the ranking produces, so the tiebreak could be deleted with no visible effect today. Rather than
disclose it as equivalent, the test now drives `_sorted_balances` directly: **a sort key nobody can
observe today is a sort key that silently stops working tomorrow**, and the first field that
publishes a ranking would inherit a non-deterministic record.

No equivalent mutants remain to disclose.

## 9. Specified, and deliberately not chosen

**No threshold, veto, profitability class or rug label.** A concentration figure is a measurement;
everything downstream of it is a decision, and this module ships none.

The future token-account capture requirements are written down in the schema rather than left to
whoever writes the fetcher, because each is a decision that would otherwise be made implicitly:
enumeration completeness must be asserted or denied with a residual; the snapshot must be atomic at
one slot, since balances read across a range are not a snapshot of anything and a transfer between
two reads can appear twice or vanish; owner resolution needs the account data rather than an
inference from transfer history; roles need a pinned roster with per-account citation; the declared
supply must come from the mint account at the same slot, or the residual measures a disagreement
between two sources rather than the units nobody enumerated; capture is cohort-scoped like B13a's
plan; and credentials stay environment-only with the endpoint identity hashed into provenance.

## 10. Not claimed

No model, no threshold, no cluster, no merge, no component, no probability, no label. No real
concentration value or distribution. No operational readiness. The counts in this document are
counts of synthetic records, arithmetic agreements and checks.
