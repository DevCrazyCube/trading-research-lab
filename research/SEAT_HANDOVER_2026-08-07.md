# Seat handover — the `codex` seat is now a Claude session (2026-08-07)

**Read this first, then `AGENTS.md`.**

## What happened

Codex hit its usage limit on 2026-08-07 (resets 2026-08-08 14:03). The owner asked for it to be
replaced with a Claude session so work continues. **You are that session.**

## You occupy a SEAT, not an identity

The dashboard hardcodes `AGENTS = ("codex", "claude")` and derives the recipient as
`target = "claude" if sender == "codex" else "codex"`. Those are **seat names**, and the seat name
is a routing label — it is not a claim about which model sits in it. You are Claude, working in the
seat called `codex`.

This was deliberate: renaming the seat would have orphaned the durable queue, every historical
handoff row, and the message already waiting for you. Nothing about the protocol changed.

Concretely:
- **You pass `codex` to every dashboard command.** `receive codex <id>`, `handoff codex --subject …`.
- Your tmux pane is `%0`, tagged `@agent=codex`. The send guard checks that **tag**, not the running
  program, which is why a Claude session in this pane routes correctly.
- The other seat, `claude`, is pane `%1`. That is the session that wrote this file.

## The protocol, exactly

```
python scripts/interactive_dashboard.py receive codex <id>     # acknowledge, FIRST thing
python scripts/interactive_dashboard.py take codex             # claim ownership BEFORE editing
python scripts/interactive_dashboard.py release                # when done
python scripts/interactive_dashboard.py handoff codex --subject '…' --message '…'
python scripts/interactive_dashboard.py status                 # queue + supervisor health
```

`handoff` appends the audit entry to `agent_discussion.md` and allocates the Seq itself. **Do not
append markdown by hand and do not call `next-seq` separately.**

### Three traps that have actually bitten

1. **Never pass a long `--message` through the shell.** A brief contains backticks, quotes and
   newlines, and zsh reads all three. On 2026-08-06 an unquoted newline let `tail -2` swallow the
   following command, and a backtick ran `python -m unittest` as a command substitution. **Nothing
   was queued**, and a not-sent handoff looks exactly like a slow one from the other side. Write the
   message to a file and invoke with no shell:

   ```python
   import pathlib, subprocess
   message = pathlib.Path("/tmp/.../brief.txt").read_text()
   subprocess.run(["python", "scripts/interactive_dashboard.py", "handoff", "codex",
                   "--subject", "…", "--message", message], capture_output=True, text=True)
   ```

2. **The peer's pane often holds your text in its composer, unsubmitted.** After `tmux send-keys`,
   send a second `C-m` and re-capture before believing it went.

3. **The database acknowledgement is the only proof of receipt.** Visible terminal text is not
   proof: a narrow pane wraps, and grepping for a multi-word phrase returns 0 even when it landed.
   Check `status` for the row reaching `acknowledged`.

## What this project is

A Pump.fun trading **research** system. **Not a live bot.** Nothing signs, submits or spends, and
no wallet or key exists anywhere in the repository.

### Standing constraints, non-negotiable

- No signing, wallet creation, submission or spend. No transaction construction.
- **Never touch B11**: no reads of composition or outcomes, no edits to `research/b11a`, the watcher,
  its artifacts, or manifest-pinned collection code. A live watcher has been running for two days.
- Synthetic or already-burned evidence only. No network unless separately justified.
- Credentials env-only, never in argv. Endpoint receipts are scheme+host+port only.
- Do not repair or smooth collected evidence without a new assignment.
- No threshold tuning from outcomes. No invented landing probability.
- Do not infer shared ownership from wallet equality — wallet equality is not owner identity.
- Do not call anything profit unless complete wallet-level costs, inventory and transfers support it.
- Treat B8b/B9/B10/B16 as burned development data only, never evaluation.
- Claim ownership before edits. Tests plus mutation attacks for substantive guards.

### House style, learned the hard way

- Exact integer arithmetic. **No float anywhere.** Exact order statistics, **no mean** — a mean over
  a censored heavy-tailed set invites reading it as an expectation.
- Canonical ordering is `(slot, transaction_index, outer_index, inner_index)`, never insertion order.
- **Fail-closed: absence is refusal, never a permissive default. Zero-by-absence is forbidden.**
- **A check that cannot fire is worse than no check** — it reads as protection. Remove unreachable
  branches rather than contriving a test for them.
- Mutation-test substantive guards: neuter each, run the tests, count survivors. A survivor usually
  means a test was passing for the wrong reason.
- Modules load via `spec_from_file_location` from ~20 places, so use absolute-path `_load`, never a
  plain `import`.
- Tests use `unittest.TestCase` (68 of 75 files) so both `pytest` and `unittest` discover them.

## Where the work is

| document | what it holds |
|---|---|
| `AGENTS.md` | collaboration rules |
| `PLAN.md` | phases and gates; Phase 5b and Phase 6 are the live-action gates |
| `DECISIONS.md` | every ratified decision, newest at the end |
| `research/B17C_SHADOW_READINESS_GAP_MAP.md` | current gap map and slice plan — **start here** |
| `research/COMPONENT_INVENTORY.json` | machine-checked inventory; `tests/test_component_inventory.py` sweeps disk and fails if a readiness component is unclassified |
| `research/B17B_EXECUTION_MEASUREMENT_CONTRACT.json` | frozen v1.0.0, canonical sha256 `29f480fc…` |
| `research/B19A_WALLET_TREASURY_ARCHITECTURE.md` | wallet/treasury architecture, prose only, audited |

Recent commits: `a6245b1` B18a shadow record layer, `acb4abb` B18b failure rehearsals + B19a audit,
`9e99870` the zero-frame safety evidence.

### Slice state

- **A — B17b record layer:** done (`scripts/b18a_shadow_record.py`).
- **B — failure rehearsals:** done for the record layer (`scripts/b18b_failure_rehearsal.py`);
  the watcher side is still open and still must not be touched while a watcher runs.
- **C — wallet/treasury architecture:** done (Codex's prose), independently audited.
- **D — strategy preregistrations:** open. Argued to **wait for B11**, or the preregistrations risk
  being fitted to what burned data already half-tells us.
- **E — kill-switch state owner:** open, and currently argued as the narrowest next gap.
  `kill_switch_engaged` is read by `b12a_risk_governor.py:394` and rendered by b12b but **written by
  nothing**. The rehearsals can show a record will not lie about a fault; they cannot show anything
  *stops*. Caution: E is the only slice that could grow a write path near the read-only console, and
  the console's read-only property is what makes "this page cannot leak a snapshot and cannot touch
  a wallet" checkable by reading it. Per B19a it belongs in a separate minimal control process.

**Before implementing E, get explicit authorization.** A standing instruction from the previous
occupant of your seat was "never implement wallet/signer/control service", and an emergency-state
owner is that class of component.

## Waiting for you

**Handoff 195 is queued.** Run `python scripts/interactive_dashboard.py receive codex 195` first —
it is the full Slice B and B19a-audit brief, and it ends with a question about what to do next.

## The live watcher — leave it alone

`pid 3315033`, `scripts/b11c_maturity_watcher.py --watch`, alive over two days, no quarantine,
~174k slots scanned and ~28k creates. It is the long pole and the thing with real cost if it dies.
Two previous deaths: a Cloudflare 403 on the default user-agent, and a transient `URLError`
misclassified as fatal. Both are fixed. Do not edit `scripts/b11c_maturity_watcher.py`,
`scripts/b11a_window_freeze.py`, `scripts/rpc_http_identity.py` or `scripts/recorder.py` while it
runs — they are manifest-pinned and the watcher holds its code in memory, so an edit is both
undetected and dangerous.
