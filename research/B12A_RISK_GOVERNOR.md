# B12a — deterministic fail-closed risk governor, verified

Date: 2026-08-02. Author: Claude (handoff 72). Offline library only.
Code: `scripts/b12a_risk_governor.py`. Schema: `docs/RISK_DECISION_SCHEMA.md`.
Tests: `tests/test_b12a_risk_governor.py`.

```
python scripts/b12a_risk_governor.py --contract
python -m pytest tests/test_b12a_risk_governor.py
```

## 0. Scope, and what was not touched

No server, UI, model, signal, wallet, key, transport, signing, submission or live RPC. **B11b was
not altered and B11a was not unlocked** — tests assert both, including that B11b's preregistration
hashes are unchanged and that B11a's unlock report still fails on `U3`.

No cap in this module was chosen from any outcome, burned or fresh. Every limit is caller-supplied
and the config must declare itself `operator_unratified`.

## 1. The design decision the rest follows from

**The governor may not resize an order.** A governor that shrinks a proposal to fit a limit changes
the thing being evaluated: the policy proposed 0.1 SOL, the book received 0.03 SOL, and every
return, drawdown and capacity figure downstream describes a strategy nobody wrote.

So there are exactly two outcomes — approve the exact order, or reject it with every applicable
reason. `order_was_resized` is on every record, always `false`, and a record invariant refuses one
where it is not. A test also scans the serialized record for `suggested_size`, `adjusted_quote`,
`max_allowed_size` and friends, because the tempting way to reintroduce resizing is to *suggest* a
size rather than apply one.

## 2. Fail closed, in three senses that are separately tested

| sense | mechanism | test |
| --- | --- | --- |
| default is no trade | the empty reason list is the only thing that approves | an approved record carrying reasons is refused by an invariant |
| absence is refusal | every config/health/portfolio/proposal field required; unknown config keys refused | each field removed in turn; `None` limits refused; an extra key alongside a complete config refused |
| a bug cannot open the system | any non-refusal exception becomes `RiskRefused` | a fault **injected at a real seam**, because bad input is caught by validation and exercises a different path |

**No financial limit defaults to zero or to infinity.** Zero silently disables trading; infinity
silently disables the limit. Both are decisions nobody made, and the second is the one that loses
money. An unknown config key is refused too: a misspelled limit is an absent limit wearing a
plausible name.

## 3. One limit rule, stated once and applied everywhere

**A limit is the largest permitted value; strictly exceeding it rejects.** That holds for every
control including the daily realised loss, where "limit reached" colloquially suggests otherwise.
Consistency beats colloquialism when the alternative is two rules nobody can remember which is
which. Every limit is tested at cap−1, cap and cap+1.

The drawdown limit is an exact rational compared by cross-multiplication: at a 1/4 limit on a
10,000,000,000-lamport peak, 7,500,000,000 passes and 7,499,999,999 rejects. A float comparison at
that magnitude cannot be relied on to say so.

## 4. Two things the first version got wrong

**The record did not show what the loss and drawdown controls were checked against.** Those two
controls read portfolio-level figures — realised PnL today, peak and current realizable value — that
appear nowhere in the exposure block. An operator could see *that* they passed but not against what,
and worse, the decision hash was blind to both: two materially different books produced a
byte-identical record. Found by a hash-stability test, not by inspection. Fixed by adding a
`portfolio_risk` block carrying the inputs and the current drawdown as an exact reduced pair.

**Per-creator position counting was under-tested.** A mutant that counted *every* position against
*every* creator survived the first run, because the concentration test only asserted the exposure
figure and not the count. That mutation would have turned the concentration limit into a second,
tighter copy of the global one — silently, and in the conservative direction, which is exactly the
kind of bug that never gets investigated.

## 5. Eligibility is delegated, not reimplemented

`b11b.evaluate_vetoes` is called and its eight `V`-codes are mapped to `R`-codes. A governor that
admitted a different set of curves than the evaluation contract would make every evaluated result
unachievable in practice. A test asserts the mapping is total in both directions and that no curve
formula appears in this module.

## 6. Precedence, and why the two orders differ

Every applicable reason is reported, ordered by a frozen precedence tuple, with `primary_reason` the
most severe. Controls are **evaluated grouped by concern** and **reported ordered by severity**, and
the two orders differ deliberately — so that emitting reasons in computation order produces visibly
wrong output rather than accidentally-correct output.

`order_reasons` takes the precedence as a parameter so a test can hand it a permuted tuple and prove
the sort follows that rather than insertion order or alphabetical coincidence. The reason codes
happen to be numbered in precedence order, so an alphabetical sort would agree with the correct one
on the shipped tuple; parameterising is what makes the specified sort distinguishable from the
accident.

## 7. Concurrency without shared state

No module-level book, cache or counter. `apply_approved` returns a **new** snapshot and never
mutates its input; the caller threads it. Pending orders count toward every exposure limit because
they will become positions, and a re-submitted `proposal_id` is rejected as a duplicate rather than
double-counted.

The test that matters: with a total-exposure limit of exactly one order, the first proposal is
approved, the returned snapshot is threaded, and the second proposal is rejected on
`R16_TOTAL_EXPOSURE_LIMIT_EXCEEDED`. Two orders that each fit alone and together do not is the
concurrency failure a limit exists to prevent.

## 8. Verification — 36 mutants, all killed

76 tests in this suite. Every mutant is a real textual edit to the shipped source, applied, the
suite run, then reverted, with each anchor required to match exactly once.

By the classes the directive named: missing values (7), one-lamport cap boundaries (7), stale
timestamps and slots (3), creator concentration (3), pending double-count (3), reason-order drift
(3), input mutation (1), fail-open exceptions (4), hash stability (2), emergency and kill switch
(2), eligibility reuse (1).

**Four did not die on the first run, and two of those were my mutants being wrong rather than the
code being right** — a `() or f(...)` mutation that still called `f`, and an anchor matching two
sites. Both were retargeted. The other two were genuine test gaps:

- *creator position counting* — described above; the assertion was added.
- *fail-open* — the existing test provoked a fault with bad input, which validation catches on a
  different path, so the generic handler was never exercised. Replaced with an injected fault
  through the real entry point.

A third gap surfaced when the unknown-key mutant survived: the misspelling test renamed a required
field, so the "missing field" check fired and the unknown-key check was never reached. A second test
now adds an extra key alongside a *complete* config, where only the unknown-key check can notice.

**36 of 36 killed** after. 1,112 tests pass repository-wide.

## 9. What this does not do

It does not decide whether an order is a good idea — no model, no signal, no view. It does not
choose its own limits. It does not execute, route, submit, retry, cancel or settle, and it holds
nothing it could sign with. It governs entry proposals only; exit-side risk is not covered.

Every record states `approval_is_simulation_only` and `NO_SIGNING_OR_SUBMISSION`. An approval here
is a risk clearance for a simulated order, under limits no operator has yet ratified.
