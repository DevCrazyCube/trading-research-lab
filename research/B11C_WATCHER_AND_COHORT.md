# B11c/B11d — the wiring that pointed at the wrong corpus, and the status that could not see death

Date: 2026-08-02. Author: Claude (handoffs 96, 99).
Code: `scripts/b11c_maturity_watcher.py`, `scripts/b11d_cohort_adapter.py`,
`scripts/b11c_watcher_entrypoint.sh`, and the b9d source-mode repair.
Schema: `docs/MATURITY_WATCHER.md`.

## 1. The wiring defect, and why an adapter rather than a fake B9a

B9c and B9d were written against B9a, whose `outcome` table carries reserves, completeness and
account state. A fresh window has no B9a. The tempting repair is to manufacture one — create a table
called `outcome`, fill the identity columns, leave the rest null — and every gate downstream would
run. It would also put fabricated results underneath a collection nobody could later distinguish
from a real one.

So the first step was to find out what the consumers actually read, by reading their SQL:

```
b9c   SELECT mint, bonding_curve, launch_slot FROM outcome
b9d   SELECT bonding_curve, is_mayhem_mode FROM outcome
b9d   SELECT mint, bonding_curve FROM outcome WHERE is_mayhem_mode = 0
```

Four columns, all identity or regime, all present in B7d's `create_event`. No consumer reads a
reserve, a completeness flag or an account balance. The adapter therefore carries exactly those
four and **manufactures nothing**.

Three details carry the argument:

- **The real table is `cohort_identity`**, and `outcome` is a VIEW over it. The consumers' SQL works
  unchanged, and nobody reading the schema believes there are outcomes in the file.
- **The table holds one column the view does not** — `create_signature`, the create event each row
  came from. That is provenance, and its absence from the view is what proves the view is a
  projection rather than the table wearing a different name. It also makes the column check
  testable: before it existed, `SELECT *` and the explicit column list produced identical views and
  neither guard could be driven.
- **`metadata.contains_outcomes` is `0`**, and consumers check it. A source that cannot say what it
  is may not stand where B9a stood.

Nothing is filtered. Every create the enumeration found becomes a member, mayhem included: a cohort
selected on any property of what happened afterwards would be a cohort selected on the answer. The
only rows "excluded" are ones that fail an integrity check, and those **abort the build** rather
than being dropped — a dropped row is a filter nobody declared.

Coverage is asserted rather than assumed: every slot in the declared window must have been visited
and resolved, and any decode error aborts. An unscanned slot is a create nobody looked for.

## 2. Burned pins do not describe a fresh window

`b9d run` accepted no `--b9c`/`--b9a`, so it would have read the burned corpus's inventory while
writing into `research/b11a/`. Adding the options was the easy half. The harder half is that b9d
also pins the burned artifacts' SHA-256s and the burned population's exact counts — 94,985
signatures across 38,853 slots — and those describe one corpus and no other.

So b9d now distinguishes **burned** from **fresh** sources:

- burned → the pinned hashes and counts apply, unchanged;
- fresh → the pins do not apply, and the cohort must verify **itself** instead;
- **mixed → refused.** A fresh inventory against the burned cohort collects one window's signatures
  under another window's identity map, and neither artifact shows a sign of it afterwards.

What still holds for both is that a population must be non-empty: a fresh run deriving nothing means
its two sources do not agree about a single signature, and collecting nothing is not a successful
run.

## 3. The status that could not see death

`--status` read the state file and asked nothing else. A supervisor that died on Tuesday would have
reported `waiting_for_maturity` on Friday, indefinitely, and the report would have looked healthy.

It now reports three independent signals — the pid running **this** watcher, the lock actually held,
and a heartbeat within three poll intervals — and publishes the stored value separately as
`reported_state`. All three agreeing is `alive`; none is `dead`; anything between is `stale`,
because signals that disagree are never "running normally".

**The pid check is the subtle one.** Matching the module name in a process's command line answers
"yes" for a test runner invoked on `tests/test_b11c_maturity_watcher.py` — including the very
process asking the question. It matches the script path and `--watch` together, and the test that
proves it uses the test process itself as the adversary.

## 4. A correction to the handoff that prompted this work

Handoff 99 reported that PID 450989 was not alive and that `--status` was falsely reporting
`waiting_for_maturity`. At the time of this work the process **was** alive: PPID 1, holding its
flock, with `polls` advancing on the 300-second schedule. The liveness claim was not correct on the
facts.

The defect underneath it was entirely real, which is why it is fixed above: a status that reads a
file and asks nothing else *would* have reported exactly that, and the only reason it was not
misreporting is that the process happened to still be running. A check that is right by luck is
worth fixing.

The durability concern was also fair. The original launch was `nohup`'d from a Claude shell — it had
reparented to init and survived, but it was not supervised. It now runs in a detached `tmux` session.

## 5. Two things learned launching it

- **A tmux session inherits the server's environment, not the client's.** The server had been
  running since long before this shell exported anything, so the first two launches died instantly
  with `SOLANA_RPC_URL is not set` — loudly, and into the log, which is the behaviour one wants.
- **`tmux new-session -e VAR=value` puts the value in a process argv**, where `ps` shows it to every
  user on the machine. The entrypoint sources `.env` itself instead, and a check across `/proc`
  confirms no process exposes the credential.

## 6. Measured

Watcher: 85 tests, 113 subtests, 41 mutants, 41 killed. Adapter and b9d repair: 34 + 242 tests,
39 mutants, 39 killed. None disclosed. **2,109 passing repository-wide.**

Running at the time of writing: pid 542344 in tmux session `b11a-watcher`, `liveness: alive`, polls
advancing (3 → 4 in 260 s at a 300 s interval), tip 436,789,600 with 422,059 slots to the cutoff,
endpoint recorded as `https://mainnet.helius-rpc.com`, no credential in state or logs, no receipts
and no collection artifacts.

## 7. Not claimed

No collection has run. No composition has been queried or published. No result stage, label or
unlock. U4 and U5 remain a later explicit decision after collection.
