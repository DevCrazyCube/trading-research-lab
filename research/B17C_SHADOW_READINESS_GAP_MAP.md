# B17c — shadow-readiness gap and ownership map

**Corrected 2026-08-06.** The first version of this document asserted that the recorder and the
operator surface did not exist. **Both do.** Codex's independent verification found the false claims
and they are corrected below, with the specifics kept rather than quietly deleted. See
[§0](#0-what-this-document-got-wrong).

**What exists, what does not, and which slices are disjoint enough for two agents to take without
colliding.** Every claim is evidence-backed: a file path, a test count, or an absence with a named
verification. The inventory is now data — `research/COMPONENT_INVENTORY.json` — guarded by
`tests/test_component_inventory.py`, because this document proved that prose drifts from the
filesystem silently.

**Nothing here authorizes execution.** No wallet, key, transaction construction, signing, simulation
or submission exists in this repository.

---

## 0. What this document got wrong

| original claim | truth |
|---|---|
| "the recorder does not exist" | `scripts/recorder.py` (31 KB) implements `docs/schema/RAW_CAPTURE_SPEC.md` v0.3, with `tests/test_recorder.py` and ~21 MB of B6 evidence in `research/b6g_*` |
| "no operator surface" | `ui/operator_console.html` (46 KB), `scripts/b12b_operator_snapshot.py`, `scripts/b12b_preview_server.py`, `tests/test_b12b_operator_console.py` |
| "`scripts/interactive_dashboard.py` — agent coordination only; not an operator surface" | true of that file, but it was presented as the *only* UX, which it is not |

**How the error happened, because that is the part worth keeping.** B17a's execution-surface scan
walks the transitive `_load` closure of the rehearsal chain — 9 modules. `recorder.py` and the b12b
console are not in that closure, so the scan never saw them. I read "empty result over the closure"
as "absent from the repository." A scoped negative result is not a global one, and I extended it
without checking. Two fixes: the scan now returns an explicit `scope` field stating it is **not**
repository-wide, and the inventory is swept from disk by marker rather than written from memory.

**The distinction this document now maintains throughout:** `EXISTS_NOT_SHADOW_CONFORMING` is not
`ABSENT`. A working component whose records lack the B17b fields needs *extending*; an absent one
needs *building*. Confusing them proposes duplicate work, which is exactly what the five-slice plan
below originally did.

## 0.1 What the widened sweep then found

Adding `record` and `shadow` to the sweep markers when b18a landed surfaced **five B15 shadow
components no inventory had ever listed**, including `scripts/b15a_shadow_pilot.py` — a 1,101-line
**live shadow pilot** that subscribes to public log notifications, preserves frames as delivered,
decodes CreateEvents with the pinned IDL, and records what the frozen B11b P1 policy would
hypothetically have proposed. It implements a preregistration committed alone before the file
existed, and it has tests.

Nothing had claimed these were absent. They were simply never enumerated — the quieter version of
the §0 failure, and the reason the sweep discovers from disk rather than validating a list. All five
are now classified; none is B17b-conforming, because all predate the contract.

**This changes how slice A should be read.** b18a is not the first shadow component; it is the first
one that emits records in the frozen shape. Bridging `b15a_shadow_pilot.py`'s output into B18a
records is a genuine follow-on, and it was not part of slice A.

## 1. Inventory

Full data with per-component reasoning in `research/COMPONENT_INVENTORY.json`.

| area | artifact | state |
|---|---|---|
| curve eligibility | `scripts/b11b_*` | exists, used by B12a |
| risk decision | `scripts/b12a_risk_governor.py` | exists; R01–R11; kill switch **read** at `b12a_risk_governor.py:394` |
| snapshot builder | `scripts/b12b_operator_snapshot.py` | **exists**, not B17b-conforming |
| operator console | `ui/operator_console.html` | **exists**; self-contained, read-only, displays `kill_switch_engaged` |
| console preview server | `scripts/b12b_preview_server.py` | **exists**; loopback only, GET/HEAD only, 405 otherwise, no write path |
| raw capture recorder | `scripts/recorder.py` | **exists**, not B17b-conforming — see G1 |
| capture spec | `docs/schema/RAW_CAPTURE_SPEC.md` | exists, v0.3 |
| B6 capture evidence | `research/b6g_*` (4 files, ~21 MB) | exists |
| exit policy / capacity | `scripts/b15m_*` | exists |
| cost model | `scripts/b15*`, `scripts/b9k_wallet_cost.py` | exists; exact-integer |
| simulator kernel | B10a, commit `c0679f9` | replays 92,510/92,510 direct-Pump trades exactly |
| live shadow pilot | `scripts/b15a_shadow_pilot.py` (1,101 lines) | **exists**, not B17b-conforming — see §0.1 |
| shadow fixtures / readiness gate | `scripts/b15a_shadow_fixtures.py`, `scripts/b15a_shadow_entrypoint.sh` | exists |
| shadow entry / path pricing | `scripts/b15d_shadow_entry.py`, `scripts/b15e_shadow_path.py` | exists, not B17b-conforming |
| shadow rehearsal | `scripts/b17a_shadow_rehearsal.py` | exists |
| shadow record layer | `scripts/b18a_shadow_record.py` | **exists**, B17b-conforming — slice A, delivered |
| shadow records | `research/b18a/records.json` | exists (synthetic segment; 6 measured fields, 37 nulls each with a reason) |
| measurement contract | `research/B17B_EXECUTION_MEASUREMENT_CONTRACT.json` | frozen v1.0.0, **canonical** sha256 `29f480fcad6dd93cc40ab3ab16ae3368c02280a27a286e7f6458577451ad2ce4` — see the note below |
| devnet/mainnet record | — | absent; b18a emits `stage=shadow` only and refuses a shadow record carrying a send, sign or land clock |
| failure-rehearsal harness | `scripts/b18b_failure_rehearsal.py` | **exists**; 6/7 outcomes and both failure-only reason codes exercised by injected fault |
| wallet/treasury architecture | `research/B19A_WALLET_TREASURY_ARCHITECTURE.md` | exists (prose only); audited |
| failure record from a REAL send | — | absent, and requires a send |
| kill-switch **control** | — | absent; see G6 |
| wallet / treasury | — | absent, and must stay so |

> **The contract's pin is not its file hash, and `sha256sum` will look like tampering.** The raw file
> digests to `c96f8b56ceb277884751e4adf3af9108586bfd86ed600ae85e9a01b6052a11a2`. The pin is over
> canonical serialization (`sort_keys=True, separators=(",",":")`), so it survives reindentation and
> key reordering — the contract's *meaning* is frozen, not its whitespace. An auditor raised this as
> a false tampering alarm on 2026-08-07, which is why it is written down.
>
> The obvious remedy — a note inside the contract's own header — **would add a key and change the
> canonical hash, breaking the pin it was meant to explain.** So it lives here and in
> `scripts/b18a_shadow_record.py`, which holds the pin. Two tests assert both digests, so
> reformatting the file fails loudly instead of silently invalidating the reference value.

## 2. What B17a proves, precisely

`python scripts/b17a_shadow_rehearsal.py` runs, with no signing and no network:

```
observation → proposal → B12a decision → simulated entry → path → exit → reconciliation → B12b snapshot
```

- **decision approved**, no vetoes; the arithmetic-only position reconciles against
  `B12A.exposure_snapshot` rather than a re-derivation (projected exposure 406,788,560 lamports)
- **kill-switch counterexample**: with the switch engaged the decision is `R02_KILL_SWITCH_ENGAGED`
  and `simulated_round_trip` is `None`. Refusal happens *before* anything computes a number that
  could be mistaken for a plan.
- **execution surface empty over the closure** — an AST walk of 9 modules, 18 tokens, docstrings
  excluded, denylists recognised structurally.
- **network refused at runtime**: `socket.socket` is replaced for the duration. A comment saying "we
  don't call the network" is not evidence; a socket that cannot open is.
- **no custody**: the position exists only as arithmetic.

**Scope, stated in the artifact itself:** the scan covers the rehearsal's transitive closure and
**says nothing about modules outside it**. That sentence is in the returned JSON and asserted by
`RealClosureTests.test_the_scan_states_its_scope_and_does_not_claim_the_repository`, because its
absence is what produced §0.

**What it does not prove:** that the numbers mean anything. The observation is synthetic. B17a is a
plumbing proof, not a result.

## 3. Gaps, by consequence

### G1 — the recorder exists but records the wrong layer (revised)
**Not absent.** `scripts/recorder.py` is a B6-lite raw capture recorder with segment framing and
CRC32C, sessions, gap detection, crash recovery, clock samples, compression, duty cycle and a 64 MiB
segment roll. It is read-only against the network and holds no keys.

The real gap is that it records **raw provider frames**, not **decision or execution records**. It
carries none of the B17b clocks, no fee or tip fields, no slippage, no outcome. Its own docstring
also states two limits honestly: the polling adapter reconstructs filtered block JSON marked
`b6-lite-normalized-v1` and is **not byte-identical** to provider frames, and provider sequence
numbers, heartbeats, commitment transitions, latency and dead-slot notifications remain
**Geyser-phase gates**.

So the work was an **extension**, not a build: a decision/execution record layer conforming to B17b,
sitting alongside the raw capture rather than replacing it. **Delivered as `b18a`** — it reads
segments through `RECORDER.scan_segment` and never calls a recorder writer, asserted from the AST,
with a test that a segment's bytes are unchanged after a full read.

**One thing found while reading the framing, reported and not repaired.** CRC32C of an empty body is
`0`, so a run of zero bytes satisfies the recorder's own scanner as a sequence of valid empty
records — a preallocated or sparse region would read as observations. `recorder.py` is not this
layer's to change, so b18a refuses a zero-length frame header instead, and a test pins both halves:
that the recorder's scanner accepts the zeros, and that b18a does not.

**The safety objection I raised against a recorder-side fix is now resolved (2026-08-07).** I said a
reader that starts rejecting zero-length headers must first be shown to reject no real historical
frame. It cannot: `SegmentWriter.write` derives the header length from `json.dumps(header).encode()`,
whose shortest possible output is two bytes, so `header_len == 0` is **unreachable from the writer**
rather than merely unobserved. A test writes five headers through the real `SegmentWriter` —
including `{}`, `None` and `[]` — and asserts every emitted frame carries `header_len >= 2`.

Separately, a sweep found **no recorder-framed file anywhere in the repository**: `SegmentWriter` is
called only inside `recorder.py` and by tests, `research/b6g_*_raw.bin` use an 8-byte length prefix
from a different tool, and `research/b15*/segments` hold gzipped JSONL. So there was no history to
sample — but an empty population is not evidence of safety, and the claim rests on the
reachability argument, not on the emptiness.

This **removes the objection** to a recorder-side fix. It is **not** authorization to make one:
`recorder.py` is collection code and that change belongs to whoever owns it.

### G2 — CLOSED for shadow by `scripts/b18a_shadow_record.py` (slice A)
`b18a` reads recorder segments through the recorder's own CRC scanner and emits records conforming
to the frozen contract. It reads the contract at import and **pins its canonical hash**, so an
edited contract makes the module refuse to load rather than emit records claiming a conformance
nobody froze.

Shadow and live are the same shape: a shadow record carries every key a live one would, with the
send-side fields null + `U_NOT_APPLICABLE`. In `research/b18a/records.json`, 6 fields are measured
and 37 are null — **each of the 37 with a reason code**, 30 `U_NOT_APPLICABLE` (structurally
impossible in shadow) and 7 `U_NOT_INSTRUMENTED` (possible, not wired). Those are different facts
and the layer keeps them different.

What remains open under G2: devnet and mainnet records (blocked, correctly), records driven by a
real B12a decision rather than a supplied `decision_unix_nanos`, and any record with a failure
outcome — see the note under §4.

### G3 — wallet and treasury architecture is undesigned, and that is currently correct
Nothing exists. The gap is real but **must not be closed by writing code**; the useful work is a
written architecture nobody implements: custody boundary, spend limits enforced where a caller
cannot bypass them, separation between a decision process and anything holding value, and the blast
radius of a compromised component. **Wallet equality is not owner identity**, and no design may
quietly assume otherwise.

### G4 — CLOSED for the record layer by `scripts/b18b_failure_rehearsal.py` (slice B)
Two live-watcher deaths this project (Cloudflare 403 on the default UA; a transient `URLError`
misclassified as fatal) were diagnosed *after* they killed a run. b18b rehearses them deliberately,
by injected fault, with no network and nothing sent.

**6 of the 7 frozen outcomes are now reached** — `never_sent`, `unknown`, `dropped`, `expired`,
`rejected_by_provider`, `failed_on_chain` — along with both failure-only reason codes,
`U_PROVIDER_SILENT` and `U_LOST`. `landed` is unreachable without a real send, and a test asserts it
stays that way: if it ever starts passing, something in this repository sent a transaction.

**The retry decision comes from `rpc_http_identity`, the module the live watcher uses**, not a copy.
So a 403 produces exactly one record (a client refusal is terminal) while 429, 500 and 503 produce a
chain — and a transport error is retryable *by type*, which is the exact rule whose absence killed a
watcher.

The distinction the harness is built around is the one a zero would erase: `never_sent` after a DNS
failure means **we know it did not happen**, and `unknown` after provider silence means **we do not
know what happened, and it may have landed**. Their land clocks carry `U_NOT_APPLICABLE` and
`U_PROVIDER_SILENT` respectively, and a mutant that collapses either into the other dies.

Also rehearsed: clock step and causal inversion, partial durable write (write-then-rename, with the
destination absent if the rename never completes), duplicate attempts, kill and resume (lost attempts
are reported as lost, never renumbered or reconstructed from memory), and quarantine.

**Still open under G4:** these are record-layer rehearsals. The *watcher's* operational failures —
duplicate stage, resumption after kill against a live collection — remain exercised only by b11c's
retrofitted invariants, and touching those while a watcher runs is still forbidden.

### G4-original — operational failure rehearsals are ad hoc (superseded above)
Two live-watcher deaths this project (Cloudflare 403 on the default UA; a transient `URLError`
misclassified as fatal) were diagnosed *after* they killed a run. B11c now has quarantine, two-clock
liveness and Q02/Q04–Q09/Q12 — retrofitted from incidents. Missing: **rehearsed** failure — provider
403/429/5xx, DNS failure, clock step, partial write, duplicate stage, resumption after kill — each
injected deliberately with the expected refusal asserted.

### G5 — CLOSED for the backlog by the B19 preregistration group (slice D)
All three named open questions are now preregistered, frozen before the evidence they will be judged
against exists: `B19B_EXIT_TIMING_POLICY_PREREGISTRATION.json` (exit-timing policy beyond B15m's
gate), `B19C_CAPACITY_WALL_SIZE_DEPENDENCE_PREREGISTRATION.json` (size-dependence of the capacity
wall above B15m's frozen ceiling) and `B19D_NON_ISSUANCE_SIGNAL_PREREGISTRATION.json` (whether any
non-issuance signal survives complete costs). `scripts/b19_preregistration_register.py` pins each
canonical hash and refuses a changed document.

**Why they were written before B11 rather than after, which reverses the earlier argument here.** A
preregistration's value comes entirely from being fixed *before* the evidence it will be judged
against exists. The burned sets (B8b/B9/B10/B16) exist today and will still exist later, so waiting
does not shrink the fitting surface by one byte — it only adds B11's result to what is known at
authorship. After B11 lands, a B11-adjacent preregistration cannot honestly be written at all. Both
agent seats originally argued for delay; the owner decided otherwise and the reasoning was
subsequently accepted by both.

**Three disciplines beyond the B16d template**, each because a pin alone does not produce them:
- a mandatory `known_at_authorship_time` block stating what the author had already seen, so a later
  reader can *audit* the fit instead of trusting an assurance that none occurred. `assert_conforms`
  refuses a document without one.
- **no tunable threshold, structurally rather than by promise.** B19d's candidate signals are all
  booleans from the frozen B11b t0 contract; a boolean has no cut to move. Signals over the
  contract's integer fields are recorded as *deferred with a reason*, not silently omitted — the
  same reason B11b excluded the momentum and curve-progress baselines.
- questions whose *specification* would depend on B11's output shape are deferred in writing rather
  than written thinly and amended later, an amendment after seeing a result being the failure this
  group exists to prevent.

**Still open under G5:** none of the three has been *run*, and B19d may only be evaluated on a window
nobody has read. **No threshold may be tuned from outcomes**, and issuance is not recommended as a
strategy.

### G5-original — the strategy backlog has no leakage discipline yet (superseded above)
B16d is the template that worked: preregistration committed **alone** before any outcome, canonical
hash pinned in code, tampering refuses. Open questions, all leakage-hazardous: exit-timing policy
beyond B15m's gate, size-dependence of the capacity wall, whether any *non-issuance* signal survives
costs.

### G6 — the console shows the kill switch but nothing owns its state (revised)
**Not "no operator surface."** The console exists, is read-only by design, and displays
`kill_switch_engaged`. Its read-only property is a feature: a write endpoint would destroy the thing
that makes "this page cannot leak a snapshot and cannot touch a wallet" checkable by reading it.

The precise gap is narrower and more interesting: **`kill_switch_engaged` has no writer.** A
repository-wide grep finds it read by b12a and rendered by b12b, but assigned nowhere outside a test
fixture and b17a's counterexample. It arrives as an input field in `health` that no component
produces from an operator action.

**Sharper still, found by the codex seat on 2026-08-07 and verified here.** The field is not merely
unwritten — it is **mandatory and unwritten**. `b12a.assert_health` (`b12a_risk_governor.py:239-243`)
*refuses* a health snapshot that omits any required flag: "an unstated health flag is not a healthy
one". So `kill_switch_engaged` cannot be defaulted, cannot be skipped, and is produced by nothing.
Every caller must invent it. The one occurrence that looks like a default —
`b12b_operator_snapshot.py:621` setting it `False` — is inside `demo_components()`, a labelled
synthetic fixture, so it is not a zero-by-absence violation; it was checked specifically because it
would have been one anywhere else.

That is a stronger argument for slice E than the original phrasing: the system already refuses to
run without an answer to "is the kill switch engaged", and there is no component whose job it is to
answer. So the missing piece is not a button — it is an **owner of the
switch's state**, with a control surface separate from the read-only console. `test_the_kill_switch_
really_has_no_writer` re-verifies this absence on every run rather than trusting this paragraph.

## 4. Revised slice plan

The original plan proposed building a recorder and an operator surface that already exist. Corrected,
narrowed, and still non-overlapping:

| slice | files touched | why disjoint |
|---|---|---|
| ~~**A. B17b record layer (G1+G2)**~~ | `scripts/b18a_shadow_record.py` | **DONE** |
| ~~**B. Failure rehearsal harness (G4)**~~ | `scripts/b18b_failure_rehearsal.py` | **DONE** (record layer; watcher-side still open) |
| **B'. Watcher failure rehearsals** | new `tests/`, b11c **copies** only | must not edit manifest-pinned b11c while a watcher runs |
| ~~**C. Wallet/treasury architecture (G3)**~~ | `research/B19A_WALLET_TREASURY_ARCHITECTURE.md` | **DONE** (Codex); independently audited 2026-08-07 |
| ~~**D. Strategy preregistrations (G5)**~~ | `research/B19B..B19D` preregs + `scripts/b19_preregistration_register.py` | **DONE** (codex seat, 2026-08-07); documents committed alone, register and tests separately |
| **E. Kill-switch state owner (G6)** | new module; **must not** add a write path to `b12b_preview_server.py` or the console | leaves the read-only surface intact |

**State as of 2026-08-07: A, B (record layer), C and D are done. B' and E remain open.**

**B'** is the watcher-side half of G4 and concerns the one component that is actually running and
has already died twice. It is takeable now — new `tests/` against **copies** of b11c — and remains
forbidden from editing the manifest-pinned files while a watcher runs.

**E is not a dependency, it is parallel.** The kill-switch state owner needs nothing from the record
layer and blocks nothing in it. It is also the slice with the most room to go wrong — the only one
that could grow a write path near the read-only surface — which is an argument for doing it
deliberately rather than early. **It additionally requires explicit owner authorization**, because a
standing instruction forbids implementing a wallet, signer or control service and an emergency-state
owner is that class of component. As of this writing that authorization has not been given, so E is
**authorization-blocked, not refuted** — the evidence for it in G6 above is stronger than when it was
first argued.

**Superseded reasoning, kept rather than deleted:** before slice B landed, this section named B the
narrowest next slice because B17b's frozen failure vocabulary — `dropped`, `expired`,
`rejected_by_provider`, `failed_on_chain`, `U_PROVIDER_SILENT`, `U_LOST` — could not be produced by
anything in the repository. `scripts/b18b_failure_rehearsal.py` now reaches six of the seven outcomes
and both failure-only reason codes.

**Hard constraint on all five:** B11 stays untouched — no reads of composition or outcomes, no edits
to `research/b11a`, the watcher, its artifacts, or manifest-pinned collection code.

## 5. How the inventory is kept honest

`tests/test_component_inventory.py`:

- every inventoried path exists on disk (no phantom entries), and every status is recognised
- the five files this document wrongly called absent are individually named, asserted present, and
  asserted **not** recorded as `ABSENT`
- **a sweep discovers candidates from disk**, not from a list somebody remembered to update: any file
  under `scripts/` or `ui/` whose name carries a readiness marker (`recorder`, `operator`, `console`,
  `preview`, `capture`, `wallet`, `treasury`, `execut`) must be classified — even if the answer is
  `NOT_A_READINESS_COMPONENT`. Silence is not an answer. This is the guard that would have caught the
  original error; one that only checked existing entries could not have.
- every absence carries a named verification, and the kill-switch absence is re-derived by grep on
  each run
- **no line of this document may claim an absence while naming a path that exists on disk** — the
  literal defect, as a test

## 6. Test runner

`python -m pytest` and `python -m unittest` both work: 68 of 75 test files use `unittest.TestCase`.
`tests/test_b17a_shadow_rehearsal.py` originally used bare pytest functions with `tmp_path`,
`monkeypatch` and `pytest.raises`, so **`python -m unittest` reported zero tests for it** — the
discrepancy Codex asked about. The commit's "31 tests" was a pytest count and was accurate for
pytest; under the standard-library runner the file looked unguarded. It has been converted to
`unittest.TestCase` and is now discoverable by both. Five pre-existing files remain pytest-only and
are recorded in the inventory rather than left to be rediscovered:
`test_b9b_curve_history_counts.py`, `test_b9c_signature_inventory.py`,
`test_b9g_decode_readiness.py`, `test_b9g_seal_collection.py`, `test_handoff_queue.py`.
