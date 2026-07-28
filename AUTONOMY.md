# Codex ↔ Claude Autonomous Handoffs

This supervisor lets the two installed CLIs alternate safe repository work without requiring the
owner to type “your turn.” It is a build/research convenience, not authority expansion.

## Control contract

- `agent_discussion.md` is the append-only source of truth. Every productive turn claims and
  releases ownership there according to `AGENTS.md`.
- Only one model runs at a time. A filesystem lock prevents duplicate supervisors.
- Each model returns one structured state: `handoff`, `user_required`, `blocked`, or `complete`.
- `handoff` immediately invokes the other model. The other states stop the loop and leave the reason
  in `.autonomy/state.json` and the tmux log.
- Two consecutive turns without a new discussion sequence stop the loop as `blocked`.
- `--max-turns` is a circuit breaker, not a project-completion definition. Restarting continues from
  the repository state.

## Hard user gates

Both agents must stop with `user_required` before any action involving:

- wallet creation/import, seed phrases, private keys, or signing;
- sending transactions, funding, spending, paid services, purchases, or subscriptions;
- deployment or changes outside this repository;
- mainnet/devnet live execution, even if previously authorized in principle;
- destructive operations or architecture choices that materially expand the recorded scope;
- an unresolved conflict among `AGENTS.md`, `PLAN.md`, `DOCUMENTATION.md`, and `DECISIONS.md`.

Reading an existing credential from ignored `.env` for already-authorized read-only RPC research is
allowed, but it must never appear in prompts, output, logs, commands, artifacts, or
`agent_discussion.md`.

## Commands

Start or resume in tmux:

```sh
python scripts/autonomy_loop.py start --first claude --max-turns 20
```

Inspect:

```sh
python scripts/autonomy_loop.py status
tmux attach -t meme-autonomy
```

The session stays open even if the supervisor exits. It has three windows:

- `control` — an ordinary owner shell plus a small supervisor-status pane at the bottom;
- `codex-log` — live combined output from Codex turns;
- `claude-log` — live combined output from Claude turns.

Inside tmux, press and release `Ctrl-b`, then press `n`/`p` to change windows, or `0`, `1`, `2`
to select one directly. Press `Ctrl-b`, then `d` to detach.

Owner controls:

```sh
# Pause before the next agent turn (does not freeze the active process)
python scripts/autonomy_loop.py pause

# Continue after a pause
python scripts/autonomy_loop.py resume

# Queue an instruction for the next agent turn
python scripts/autonomy_loop.py message "Prioritize the simulator next"

# Send SIGINT to the active agent and all of its child processes
python scripts/autonomy_loop.py interrupt

# Inspect structured state
python scripts/autonomy_loop.py status
```

Stop safely after the current CLI process exits:

```sh
python scripts/autonomy_loop.py stop
```

`stop` takes effect between turns. `interrupt` is the immediate control. Queued owner messages are
archived only after an agent returns a valid structured result, so an interrupted turn cannot silently
discard them.

The supervisor never starts itself at boot and never bypasses either CLI's sandbox or permission
system. Codex remains in `workspace-write`; network access is enabled inside that sandbox solely so
already-authorized read-only RPC and primary-source research can run without a manual escalation.
