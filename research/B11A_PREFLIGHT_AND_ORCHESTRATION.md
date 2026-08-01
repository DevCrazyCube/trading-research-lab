# B11a — window verification, maturity preflight, and the locked collection pipeline

Date: 2026-08-02. Author: Claude (handoff 68).
Freeze: `research/B11A_FRESH_COHORT_PREREGISTRATION.json` (committed **alone**, in `b764898`,
before any chain query). Code: `scripts/b11a_window_freeze.py`.
Tests: `tests/test_b11a_window_freeze.py`. Receipt: `research/B11A_PREFLIGHT.json`.

```
python scripts/b11a_window_freeze.py verify
python scripts/b11a_window_freeze.py preflight
python scripts/b11a_window_freeze.py plan
```

## 1. The frozen window re-derives exactly

`b11a_window_freeze.py` restates the burned-range register **from `DECISIONS.md`, not from the
document it is checking** — a checker that takes its inputs from the thing under test cannot detect
drift in it — and recomputes all four endpoints independently:

| quantity | value |
| --- | --- |
| maximum inclusive burned endpoint | 435,569,149 (B7c) |
| launch window | **435,569,150 .. 435,772,750** (203,601 slots, inherited from B8b) |
| observation cutoff | **437,211,659** (1,642,509 slots after launch start, inherited from B9d) |
| disjoint from all seven burned ranges | yes, launch window **and** full observation span |
| file / canonical SHA-256 | `5faabb33…` / `ae4d2f03…`, both matching the committed bytes |

Any drift — one slot in any endpoint, a changed span, a register entry that disagrees with the
record, a range added or dropped — raises. The two hashes are not redundant: reformatting the JSON
preserves the canonical hash, so only the file hash can tell that the committed bytes moved, and a
diff nobody can see is exactly the edit a freeze exists to catch.

## 2. Preflight — one method, and no way to call a second

**Result: the window is NOT mature.**

| quantity | value |
| --- | --- |
| finalized tip at preflight | 436,654,559 |
| frozen observation cutoff | 437,211,659 |
| **slots remaining** | **557,100** |
| estimated wait | **≈ 2.69 days** (2.3934 slots/s, measured on 438 consecutive B7j blocks over 183 s — an estimate, not a commitment) |
| methods called | `getSlot` only |
| composition queried | **no** |
| endpoint recorded | `https://mainnet.helius-rpc.com/` — scheme and host only; no credential reaches the receipt |

**The window was not moved, shortened, split or re-placed.** The slot count is the exact quantity
and the wall-clock figure is an estimate, reported in that order deliberately: the slot count does
not drift when the network speeds up.

Note what is already true: the **launch window is entirely in the past** (it ended at 435,772,750,
well below the tip). The cohort is already fixed on chain and nothing about it can be influenced by
anything done here. Only the observation tail is still accruing.

The preflight cannot issue a composition query. `PREFLIGHT_ALLOWED_METHODS` is an **allowlist**
containing `getSlot` and nothing else. A denylist would have to anticipate every method that leaks
composition; an allowlist has to anticipate nothing, and a test asserts that a method invented next
year is refused just as `getBlock` is.

## 3. The pipeline is planned and locked

The existing B8/B9/B10 chain is declared as ten stages, each carrying two independent flags —
whether it may run before results are unlocked, and whether its output describes the window.

| stage | script | may run pre-unlock | numbers withheld |
| --- | --- | --- | --- |
| `enumerate_creates` | `b7d_create_enumerator.py` | yes | yes |
| `signature_inventory` | `b9c_signature_inventory.py` | yes | yes |
| `transaction_bodies` | `b9d_transaction_bodies.py` | yes | yes |
| `program_boundary` | `b9d … --boundary` | yes | **no** |
| `decode_and_reserves` | `b9d … --decode` | yes | yes |
| `reserve_coverage_gate` | `b9e_reserve_coverage.py` | yes | yes |
| `failure_coverage_gate` | `b9f_failure_coverage.py` | yes | yes |
| `simulator_replay_gate` | `b10a … --gate` | yes | yes |
| `position_paths` | `b10b_path_dataset.py` | **no** | yes |
| `outcome_labels` | `b10c_label_corpus.py` | **no** | yes |

Two distinctions are doing the work here, and the second one was tightened after first writing it
down the easy way:

- **A gate must be able to fail before unlock.** Data that has not been gated cannot be shipped, so
  `b9e`/`b9f`/`b10a` run — but their *counts* describe the window, so only pass/fail survives
  `redact_composition`. One bit is unavoidable; a distribution is not.
- **Collection counts are composition too.** The first draft marked enumeration and body collection
  as composition-free. That is wrong: enumerating the cohort produces its membership list, and
  "there are N launches in this window" is a description of it. Only the program-boundary probe is
  genuinely composition-free, because an upgrade slot is a property of the program rather than of
  this cohort. All four collection stages now withhold their numbers.

While the window is immature **nothing runs at all**, including collection. That is the directive's
rule, and it happens to be right for a second reason: the enumeration would reveal membership.

## 4. B10c's enum was deliberately not extended

`scripts/b10c_outcome_labels.py` still accepts only `window_status: burned_development` and refuses
`fresh_preregistered`. Extending it now would open a path to revealing this window's labels before
any model, horizon or threshold is frozen against them — which is the single failure this
preregistration exists to prevent, and a strange way to celebrate finally having a clean window. A
test pins the refusal, and unblocking it requires its own `DECISIONS.md` entry recording that the
freezing happened first.

## 5. Verification — 23 mutants, 22 killed, and one survivor with a proof

45 tests in this suite. Every mutant is a real textual edit to the shipped source, applied, the
suite run, then reverted, with each anchor required to match exactly once.

Killed: half-open normalised as inclusive; B7b read as half-open (which would leave a burned slot
inside the evaluation window); the start landing *on* the last burned slot; the launch span losing
its inclusive `+1`; the observation span gaining a spurious one; the launch end off by one;
disjointness never finding an overlap; a drifted endpoint or span accepted; the file hash unpinned;
a composition query allowed through; `getBlock` added to the allowlist; the maturity boundary off by
one; results runnable before unlock; an immature window no longer blocking; withheld composition
returned in full; the window edited after preflight; a replaced preregistration accepted; an unknown
stage treated as permitted; the credentialed URL kept in the receipt; a missing `SOLANA_RPC_URL`
falling back to a public endpoint; and the label stages reclassified as harmless collection.

**One survivor, recorded rather than papered over:** deleting the observation-span disjointness
check changes nothing observable. It is **redundant by construction** — the start rule is
`max(burned last) + 1`, so every burned range ends strictly before the window begins and none can
reach into `[start, cutoff]`. No fixture can distinguish its presence.

That was worth chasing rather than accepting at face value. The first attempt to kill it added an
explicit start-rule invariant to the module; the mutant survived that too, because with the register
consistent and the derivation correct the invariant is *unreachable*. **The invariant was then
removed.** A check that cannot fire is worse than no check: it makes the file look more careful than
it is. The redundant span check is kept — it is free, and it is what would catch a future change to
the start rule that the drift checks happened to miss — and the redundancy is now stated in the
code, asserted as a proof in the test suite, and listed as a known survivor in the mutation set. A
mutation set containing only mutants you can kill is a flattering one.

## 6. What happens next, and what must not

**Next, at maturity (≈ 2.69 days from the preflight):** run the frozen enumeration and collection
with raw preservation and the existing rate and single-writer safeguards, decide abort branch A2
from the boundary probe, and run the coverage and replay gates with their counts withheld. Nothing
about the window may be adjusted on the way.

**Must not, until models, horizons and thresholds are frozen and recorded in `DECISIONS.md`:** any
census, yield count, regime split, actor concentration, path result, label or return figure for this
window. Abort branch A7 — that is what burns it, and there is no eighth window queued behind this
one.

No paid subscription, UI, server, model, signal, baseline, live transaction or signing was created
or authorised by this work. Credentials remain environment-only and appear in no artifact.
