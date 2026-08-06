# B17c — shadow-readiness gap and ownership map

**What exists, what does not, and which slices are disjoint enough for two agents to take without
colliding.** Every claim below is evidence-backed: a file path, a test count, or an explicit
"nothing exists."

**Nothing here authorizes execution.** No wallet, key, transaction construction, signing, simulation
or submission exists anywhere in the repository, and the B17a scan proves it over the live closure
rather than asserting it.

---

## 1. Inventory: what is actually built

| area | artifact | state |
|---|---|---|
| curve eligibility | `scripts/b11b_*` | built, used by B12a |
| risk decision | `scripts/b12a_risk_manager.py` | built; 11 reason codes R01–R11; kill switch |
| read-only snapshot | `scripts/b12b_*` | built; `FORBIDDEN_SUBSTRINGS` guard |
| exit policy / capacity | `scripts/b15m_*` | built; capacity gate against the observed book |
| cost model | `scripts/b15*` | built; exact-integer, full executable costs |
| simulator kernel | B10a, commit `c0679f9` | replays 92,510/92,510 direct-Pump trades exactly |
| shadow rehearsal | `scripts/b17a_shadow_rehearsal.py` | **new this handoff** |
| measurement contract | `research/B17B_EXECUTION_MEASUREMENT_CONTRACT.json` | **new this handoff**, frozen v1.0.0, canonical sha256 `29f480fcad6dd93cc40ab3ab16ae3368c02280a27a286e7f6458577451ad2ce4` |
| recorder | — | **does not exist** |
| wallet / treasury | — | **does not exist, and must not yet** |
| operator UX | `scripts/interactive_dashboard.py` | agent coordination only; not an operator surface |

## 2. What B17a proves, precisely

`python scripts/b17a_shadow_rehearsal.py` runs a full chain with no signing and no network:

```
observation → proposal → B12a decision → simulated entry → path → exit → reconciliation → B12b snapshot
```

Verified in that run:

- **decision approved**, no veto reasons; the arithmetic-only position reconciles against
  `B12A.exposure_snapshot` rather than a re-derivation (projected exposure 406,788,560 lamports)
- **kill-switch counterexample**: with the switch engaged the decision is `R02_KILL_SWITCH_ENGAGED`
  and `simulated_round_trip` is `None` — a rejected proposal is never priced. This is the seam that
  matters: refusal must happen *before* anything computes a number that could be mistaken for a plan.
- **execution surface: empty**, from an AST walk over the 9-module transitive closure, matching 18
  tokens (`sendTransaction`, `signTransaction`, `Keypair`, `private_key`, `partial_sign`, …) against
  code string constants and identifiers — **docstrings excluded**, because a denylist that trips on
  its own documentation cannot distinguish prose from capability.
- **network refused at runtime**, not promised: `socket.socket` is replaced for the duration of the
  chain and raises `NetworkAttempted`. A comment saying "we don't call the network" is not evidence;
  a socket that cannot open is.
- **no custody**: reconciliation states plainly that no wallet holds anything, and the position
  exists only as arithmetic.

**What it does not prove:** that the numbers mean anything. The observation is synthetic. B17a is a
plumbing proof, not a result, and its output is not evidence about any strategy.

## 3. Gaps, by consequence

### G1 — the recorder does not exist (blocks everything downstream)
There is no component that takes a live observation stream and writes canonical records. B15 studies
read a frozen corpus; B11 collects but for enumeration, not for decisions. Until a recorder exists,
"shadow" means replaying synthetic or burned inputs — which is what B17a does and all it can do.
**Requirement:** read-only, canonically ordered `(slot, transaction_index, outer_index, inner_index)`,
fail-closed on gaps, and it must record the B17b clock fields with **nulls, not zeros**, for
everything it cannot measure.

### G2 — no shadow record conforms to B17b yet
B17a emits a rehearsal snapshot, not a B17b record. The contract is frozen precisely so the first
implementation is judged against it rather than defining it. A shadow record must have the **same
shape** as a live one, with the build/sign/send/land fields null + `U_NOT_APPLICABLE` — otherwise
shadow and live are not comparable and the whole exercise proves nothing.

### G3 — wallet and treasury architecture is undesigned, and that is currently correct
Nothing exists. The gap is real but **must not be closed by writing code**; the useful work is a
written architecture that nobody implements: key custody boundary, spend limits enforced where they
cannot be bypassed by a caller, the separation between a decision process and anything holding value,
and what a compromised component can and cannot do. Note the standing distinction: **wallet equality
is not owner identity**, and no design may quietly assume otherwise.

### G4 — operational failure rehearsals are ad hoc
Two live-watcher deaths this project (Cloudflare 403 on the default UA; a transient `URLError`
misclassified as fatal) were diagnosed *after* they killed a run. B11c now has quarantine, two-clock
liveness and Q02/Q04–Q09/Q12 invariants — but they were retrofitted from incidents. What is missing is
**rehearsed** failure: provider 403/429/5xx, DNS failure, clock step, partial write, duplicate stage,
resumption after kill — each injected deliberately, with the expected refusal asserted.

### G5 — the strategy backlog has no leakage discipline yet
B16d is the template that worked: preregistration committed **alone**, before any outcome, canonical
hash pinned in code, tampering refuses. Every future strategy question needs that shape. The known
open questions (all leakage-hazardous, none authorized to be answered opportunistically): exit-timing
policy beyond B15m's gate, size-dependence of the capacity wall, whether any *non-issuance* signal
survives costs at all. **No threshold may be tuned from outcomes**, and issuance is not recommended
as a strategy regardless of what B16 measured about it.

### G6 — no operator surface
No way for a human to see what a decision process would do, or to stop it. A kill switch that exists
in `b12a` but has no operator-reachable control is a switch nobody can throw. Minimum: read-only
status, the reason code for every refusal, and a kill control whose default is *engaged*.

## 4. Suggested split (non-overlapping)

These touch disjoint files, so both can proceed without lock contention:

| slice | files touched | why disjoint |
|---|---|---|
| **A. Recorder preparation (G1+G2)** | new `scripts/b18*`, reads B17b | writes new modules only |
| **B. Failure rehearsal harness (G4)** | new `tests/`, injects into b11c *copies* | must **not** edit manifest-pinned b11c while a watcher runs |
| **C. Wallet/treasury architecture (G3)** | `research/` document only | prose; no code |
| **D. Strategy preregistrations (G5)** | `research/` preregs, committed alone | prose; no code |
| **E. Operator surface (G6)** | new module | read-only; must not import b12a's mutators |

**Hard constraint on all five:** B11 stays untouched — no reads of composition or outcomes, no edits
to `research/b11a`, the watcher, its artifacts, or manifest-pinned collection code.

## 5. Evidence for the "nothing exists" claims

The absences in §1 are not assumptions. `b17a`'s scan walks the transitive import closure of the
rehearsal chain — b12a, b12b, b11b, b15m, the cost model and their dependencies, 9 modules — and
returns an empty surface map. A repository-wide scan is a distinct and weaker claim; the closure scan
is the one that matters, because it covers exactly the code that would run.
