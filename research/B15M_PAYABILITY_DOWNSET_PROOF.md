# The payability down-set theorem

**Status.** Proposed. Corroborated but NOT accepted. Nothing depends on it yet, and B19G remains
not-runnable-of-record until this argument is reviewed and a document amendment is authorised.

**What it is for.** `b15m.assert_prefix_shape` verifies, by scanning every integer lamport from the
resolution floor to the ceiling, that the admissible set is a contiguous prefix. At B19C's raised
ceiling of 10,000,000,000 that is ten billion payability evaluations per cell against 23,592 cells
— on the order of five hundred thousand hours, which is why B19G was declared not runnable. This
argues the scan verifies a theorem.

**History of this document.** Version 1 of the argument was WRONG, and was broken by an adversarial
agent that executed the predicate instead of reading it. The hypothesis was stated as "all reserve
fields non-negative", which admits `virtual_quote = 0`, and there the predicate is not total. That
counterexample and the corrections it forced are recorded in full at the end, because an argument
that has survived one refutation deserves less trust than its conclusion suggests, and the reader
should see what it took.

---

## The functions, quoted from source

From `scripts/b9i_quote_reproduction.py`:

```
tokens_out_for_exact_quote_in(vq, vt, q) = (q - 1) * vt // (vq + q - 1)      # requires q > 0
quote_out_for_tokens_in(vq, vt, t)       = t * vq // (vt + t)                # requires t >= 0
```

From `scripts/b15m_liquidity_capacity.py`:

```
tokens_for(E, q)     = 0 if q <= 0 else tokens_out_for_exact_quote_in(E.vq, E.vt, q)
gross_draw(E, X, q)  = 0 if tokens_for(E, q) <= 0
                       else quote_out_for_tokens_in(X.vq, X.vt, tokens_for(E, q))
is_payable(E, X, q)  = True                            if q == 0
                       False                           if tokens_for(E, q) > E.real_token
                       gross_draw(E, X, q) <= X.real_quote   otherwise
```

All arithmetic is Python integer arithmetic: `//` is floor division, ints are arbitrary precision,
and no float appears anywhere on the call path.

## Hypotheses

**H1.** `E.virtual_quote >= 1` and `E.virtual_token >= 1`.
**H2.** `X.virtual_quote >= 1` and `X.virtual_token >= 1`.
**H3.** `E.real_token` and `X.real_quote` are integers. *(No sign condition. See Remark 3.)*

H1 and H2 are exactly what `b15m.assert_reserves_possible` enforces — it requires both virtual
reserves **strictly** positive on a state and rejects negative real reserves — and `b19c.capacity`
calls it on **both** states before `assert_prefix_shape`. The hypotheses are therefore discharged by
code that already runs, in the right order. **That ordering is load-bearing and must be pinned, not
remembered.**

## Lemma 1 (the ratio map is non-decreasing)

For integers `k >= 0`, `c >= 1`, the map `u |-> u*k // (c + u)` is non-decreasing on `u >= 0`.

*Proof.* Let `u2 > u1 >= 0`. Both denominators `c + u1` and `c + u2` are `>= 1`, hence positive, so
cross-multiplication preserves the inequality:

```
u1*k*(c + u2) <= u2*k*(c + u1)
  <=>  k*c*u1 + k*u1*u2  <=  k*c*u2 + k*u1*u2
  <=>  k*c*u1 <= k*c*u2
```

which holds since `k >= 0`, `c >= 1`, `u1 < u2`. So `u1*k/(c+u1) <= u2*k/(c+u2)` as rationals, and
floor is monotone, giving `u1*k // (c+u1) <= u2*k // (c+u2)`. ∎

*Note.* `c >= 1` is required and is not cosmetic: at `(u, c) = (0, 0)` the expression is `0 // 0`,
which raises rather than evaluating. That single case is the whole of the version-1 refutation.

## Lemma 2 (`tokens_for` is non-decreasing in q)

Under H1, `tokens_for(E, ·)` is non-decreasing on `q >= 0`.

*Proof.* For `q >= 1` write `u = q - 1 >= 0`, `k = E.vt >= 1`, `c = E.vq >= 1`. Then
`tokens_for(E, q) = u*k // (c + u)`, non-decreasing in `u` by Lemma 1, hence in `q`, and the
denominator `c + u = E.vq + q - 1 >= 1` is never zero.

**The seam at `q = 0 -> 1`.** For `q <= 0` the guard returns `0`. At `q = 1`, `u = 0` and the
formula gives `0*k // c = 0`. Guard value and formula value agree, so no discontinuity is
introduced and the map is non-decreasing across the seam. ∎

## Lemma 3 (`gross_draw` is non-decreasing in q)

Under H1 and H2, `gross_draw(E, X, ·)` is non-decreasing on `q >= 0`.

*Proof.* Let `h(t) = t * X.vq // (X.vt + t)`. By Lemma 1 with `k = X.vq >= 1`, `c = X.vt >= 1`, `h`
is non-decreasing on `t >= 0`, and its denominator `X.vt + t >= 1` is never zero.

**The seam at `t = 0`.** `gross_draw` returns the guard value `0` when `tokens_for(E, q) <= 0`,
rather than evaluating `h`. Since `h(0) = 0 * X.vq // X.vt = 0`, the guard agrees with the formula.

`tokens_for` is non-negative everywhere under H1 (Lemma 2 gives `tokens_for(E, q) >= tokens_for(E, 0)
= 0`), so `gross_draw = h ∘ tokens_for` on the whole domain, a composition of non-decreasing maps
with matching seams, hence non-decreasing. ∎

## Theorem (payability is a down-set)

Under H1–H3, for fixed `E` and `X` the set `P = { q ∈ Z, q >= 0 : is_payable(E, X, q) }` is a
down-set: if `q ∈ P` and `0 <= q' <= q`, then `q' ∈ P`.

*Proof.* `is_payable` is total under H1–H2: every division it performs has a denominator `>= 1`, by
Lemmas 2 and 3.

Take `q ∈ P` and `0 <= q' <= q`. If `q' = 0` then `q' ∈ P` by the first branch. Otherwise `q' >= 1`.

Since `q ∈ P` and `q >= q' >= 1`, the second branch did not fire at `q`, so
`tokens_for(E, q) <= E.real_token`. The code's test is the strict `tokens_for > real_token -> False`;
its negation is the non-strict `tokens_for <= real_token`, which is the form used here. By Lemma 2,
`tokens_for(E, q') <= tokens_for(E, q) <= E.real_token`, so the second branch does not fire at `q'`
either.

The third branch held at `q`: `gross_draw(E, X, q) <= X.real_quote`. By Lemma 3,
`gross_draw(E, X, q') <= gross_draw(E, X, q) <= X.real_quote`. So `is_payable(E, X, q')` is True and
`q' ∈ P`. ∎

## Corollary (the resolution-floor half)

`assert_prefix_shape` asserts two things, and both follow. The second is that every input below the
computed floor acquires zero tokens. `{ q : tokens_for(E, q) = 0 }` is a down-set by the same
argument applied to Lemma 2 alone: `tokens_for` is non-decreasing and non-negative, so if it is zero
at `q` it is zero at every `q' <= q`. ∎

## Remarks on what the theorem does NOT give

**Remark 1 — it is about `is_payable`, not `is_admissible`.** `is_admissible` adds
`gross_draw >= 1`, a lower bound, making the admissible set an *interval* rather than a down-set.
The existing code already separates these for exactly this reason and only bisects the payable half.

**Remark 2 — negative virtual reserves genuinely break it,** they do not merely crash it.
`X.virtual_quote < 0` makes `h` *decreasing*, and paired with `X.real_quote < 0` yields a real
False-to-True flip. H1/H2 exclude this, and `assert_reserves_possible` enforces H1/H2.

**Remark 3 — the thresholds need no sign condition.** `E.real_token` and `X.real_quote` may be any
integers: a sublevel set of a non-decreasing function is down-closed whatever the constant.
`E.real_quote` and `X.real_token` are never read by `is_payable`.

**Remark 4 — this certifies a reading of today's source.** The scan executes the actual predicate
every time; a proof certifies four short function bodies as they are written now. A fee folded into
`tokens_for`, or a rounding change after the next program revision, would silently detach the proof
while every test still passed. This is the strongest argument against relying on it, and it is why
the proposed replacement pins those bodies by hash and falls back to the scan on any drift, rather
than asking a reader to trust that nobody edited them.

---

## Appendix: the refutation of version 1

Version 1 stated the hypothesis as "all reserve fields non-negative integers". An adversarial agent
executed the predicate and produced:

```
E = {virtual_quote: 0, virtual_token: 10, real_quote: 0, real_token: 10}
X = {virtual_quote: 100, virtual_token: 100, real_quote: 100, real_token: 0}

is_payable(E, X, 0) = True
is_payable(E, X, 1) = ZeroDivisionError      # (1-1)*10 // (0 + 1 - 1)  =  0 // 0
is_payable(E, X, 2) = True
```

`P` contains 0 and 2 but not 1. Not a down-set: the predicate is not even total there. Verified
against the live module.

Four defects in version 1, all corrected above:

1. **`c >= 0` where `c >= 1` was needed.** The case `(u, c) = (0, 0)` *is* the counterexample, so the
   loose bound was not pedantry — it was precisely the hole.
2. **No proof that the denominator stays positive**, which is what makes `//` the floor of the real
   quotient rather than an error. Lemma 1 now cross-multiplies positive denominators and never
   appeals to "floor preserves monotonicity" over an unchecked range.
3. **The seams were never checked.** `gross_draw` is not the bare composition — both functions are
   spliced with guards. They agree, but that is a fact requiring proof, and when `X.vt = 0` the
   guard is the only thing preventing a second `0 // 0`. H2 now excludes that case and Lemmas 2 and
   3 state the seam values explicitly.
4. **The `q = 0` case and the strict-to-non-strict conversion were omitted.** Both are now explicit
   in the Theorem.

Corroboration gathered after the correction, which is evidence and not proof:

- exhaustive sweep over 400 random small states, every `q` in `[0, 260)`: 104,000 evaluations,
  176 states carrying both payable and unpayable sizes, **zero** down-set violations;
- 762 real window state-pairs with a genuine payability boundary located by bisection, 6,170 probes
  strictly at or above each boundary at the full 10,000,000,000 ceiling: **zero** violations;
- the adversarial agent's own independent hunt — the full non-negative grid over six fields to
  saturation, 7,000 randomised states to 10^15 with exhaustive low-`q` windows, 200,000 monotonicity
  probes to 10^12: **zero** literal False-to-True flips, every violation being the `vq = 0` crash
  family excluded by H1.

A first attempt at the second sweep reported violations that were an error in the *test*: it probed
`CEILING // 2`, which can lie *below* the located boundary, so correct down-set behaviour was
flagged as a counterexample. Recorded because anyone writing their own probe will meet the same
trap.
