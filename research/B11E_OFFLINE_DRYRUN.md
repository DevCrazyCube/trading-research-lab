# B11e — offline end-to-end dry run of the nine B11a stages

`scripts/b11e_pipeline_dryrun.py`, tests in `tests/test_b11e_pipeline_dryrun.py`.
No network, no chain, no live-directory access. `python scripts/b11e_pipeline_dryrun.py --gate`
exits non-zero on any finding.

## What it checks, and why each one

| Check | The failure it exists for |
|---|---|
| Every flag the plan passes is declared by the target script's own `--help` | `b9d run` once had no `--b9c`/`--b9a` at all; the plan "passed" them and the stage collected the burned corpus |
| Declared read/write graph joins up, and matches the actual argv | A pipeline whose stage N writes a path stage N+1 does not read fails at the join, hours in |
| No argument mentions a burned artifact | A fresh window that reads or writes the burned corpus destroys both |
| A source override that equals its module default is refused | The defaults **are** the burned corpus; passing one explicitly is not parameterisation |
| Every gate refuses an empty artifact | A gate that passes on nothing is worse than no gate — its output looks like success |
| Missing sources are refused **as the project's refusal type** | See defects 1 and 2 below |
| Receipts, resume, duplicate refusal, manifest drift | Driven through B11c's own fake-runner seam |
| The fixture inherits no RPC credential | Otherwise a stage that reached the network would succeed quietly and the audit would prove nothing |

`build_cohort` is executed **for real** — it is offline by construction — and the artifact is then
queried with b9c's and b9d's own SQL rather than checked against a copy of their expectations.

Result: nine stages, no findings. Gate exit codes on an empty artifact: all non-zero.
Every check above has a test that breaks its invariant and confirms it goes red.

## Defects found and fixed

**1. `b9d.sha256_file` raised a bare `OSError` for a missing source.** Every caller is written
`except FreezeViolation`, so a missing source escaped the handler meant to contain it. Unreachable
on the burned paths — those files always exist — and routine on the fresh path, where every source
is something a previous stage was supposed to write. Now a `FreezeViolation`.

**2. `b11d.assert_fresh_cohort` raised a bare `sqlite3.OperationalError` for a missing cohort.**
Read-only URI mode fails *at connect*, before any statement, so the per-statement handlers inside
could not catch it. b9d wraps this exact call in `except CohortRefused` — that wrapper was
inapplicable to the most ordinary bad cohort of all, one that is not there. Now a `CohortRefused`.

**3. The integrity manifest was verified once, before the wait, and never again.** This is the
serious one. A run attests its manifest at `watch()` start, then waits for maturity — currently on
the order of days — and only then executes the stages, as subprocesses that read whatever is on
disk *at that moment*. The attestation therefore describes the scripts present when the waiting
began, not the ones that run. Any edit landing during the wait is collected under, and attested
away by, a digest describing different code: precisely the provenance lie the manifest exists to
prevent, wide open on the only path where it matters.

Fixed by `assert_manifest_unchanged`, now called both at start and again at the waiting→running
transition, which is the last instant before any stage executes.

## Consequence for the currently armed run

Fixes 1 and 2 touch `scripts/b9d_transaction_bodies.py` and `scripts/b11d_cohort_adapter.py`, both
manifest-pinned. The armed run's recorded manifest is consequently drifted from disk. The running
process will not notice — it holds the pre-fix code, which only checks at start — so at maturity it
would execute the corrected scripts while attesting the superseded digest. It has completed **zero
stages**, so a restart costs nothing but the relaunch.

Per the standing constraint the watcher was **not** restarted or altered. This is an operator
decision. Recommendation: restart before maturity, which re-attests cleanly and picks up fix 3.

## Assessment: should `b11c_watcher_entrypoint.sh` enter the next-run integrity manifest?

**No.** It should be pinned as provenance, not as a resume precondition.

What the manifest is for: refusing to *continue* a run when something that determines the collected
artifacts has changed underneath it. The entrypoint controls four things — the working directory,
sourcing `.env`, the default poll cadence, and log redirection. Only the second is substantive, and
it is already covered more strongly: the watcher receipts the endpoint it *actually used*
(scheme+host), which beats pinning a script that merely says which one it intends to load.

The decisive argument is timing. The entrypoint `exec`s and is gone before the watcher starts;
nothing it does can change after that point. So:

- It cannot drift *during* a run in any way that affects the run. A manifest entry for it would
  guard a window in which nothing it controls can still matter — a check that cannot fire.
- It would, however, fire *spuriously*. Editing the log path or the poll default mid-run would
  quarantine a sound run and force the discard of hours of collection, for a change that provably
  could not have touched one collected byte, because the process had already exec'd past it.

Inclusion therefore trades no real coverage for a real false-positive. Note the watcher script
itself is out of the manifest for the same reason: it is loaded once at start, and the running
process is unaffected by later edits to it.

What is genuinely missing is a record of *what launched this run*. The right instrument is a
provenance field in the start receipt — the entrypoint's digest and the poll cadence — which
answers "how was this started" without pretending it is a live precondition. Not implemented here:
it changes the receipt schema, and the schema belongs to a run that has not begun.
