# Research agent graph

The durable replacement for the tmux Codex↔Claude handoff loop (`autonomy_loop.py`,
`interactive_dashboard.py`), which was two brittle TUIs poking each other with `send-keys` and died
on every crash. This one is a **native Claude agent graph** with **on-disk state that survives
crashes** — no tmux, no second CLI.

## The three pieces

| piece | file | role |
|---|---|---|
| **state** | `agenda.json` | the durable work-list. Every task carries its own guardrails. Survives crashes. |
| **graph** | `graph.js` | a Workflow: each task runs `execute → adversarial-verify` in a pipeline. |
| **loop** | `loop.py` | deterministic bookkeeping — selects pending tasks, folds results back. Never calls a model. |
| **UI** | `server.py` + `dashboard.html` + `app.css` + `app.js` | multi-page control dashboard — `python scripts/agent_graph/server.py` → http://localhost:8787. Pages: **Control** (loop pause/resume, batch size, reclaim, queue-run, pipeline graph, live agent feed), **Agenda** (task table: add / re-prioritise / re-queue / delete), **Portfolio** & **Profits** (live Alpaca *paper* account — equity, positions, orders, equity curve), **Accounts** (connected accounts, masked). |
| **control** | `control.json` | loop control flags — `{paused, batch, run_requested}`. Both the UI (POST /api/loop/*) and `loop.py next` read/respect it. `loop.py control [pause\|resume\|batch N\|request-run]`. |
| **feed** | `watch.py` | terminal tail of the newest run's agent thinking/tools (the raw version of the UI's feed). |

**Trading endpoints are READ-ONLY against the PAPER account.** Placing/cancelling live orders and
adding real-money wallets/keys are owner-gated and deliberately not exposed through the web UI — add
credentials to `.env` and they surface (masked) on the Accounts page.

## One iteration (what the loop does each turn)

```sh
# 1. select the top-N pending tasks (marks them running). Emits graph.js's `args`.
python scripts/agent_graph/loop.py next 3 > /tmp/graph_args.json

# 2. run the graph on them (from the Claude session, via the Workflow tool):
#    Workflow({ scriptPath: "scripts/agent_graph/graph.js", args: <contents of graph_args.json> })
#    -> writes its structured results to a file, say /tmp/graph_results.json

# 3. fold the verdicts back into the agenda (verified / blocked / re-queued):
python scripts/agent_graph/loop.py merge /tmp/graph_results.json
```

`graph.js` returns `{ results: [ { id, status, result, verdict }, ... ] }`. `loop.py merge` maps:

- `CONFIRMED` + executor `done` → **verified**
- `REFUTED` → **pending** (re-queued; the claim did not survive the skeptic)
- `NEEDS_OWNER` / `PLAUSIBLE` / `partial` → **blocked** (needs owner sign-off or more evidence)
- executor `blocked` / `killed` → that status verbatim

## Crash recovery

State is entirely in `agenda.json`, so a crash never loses progress. After any crash:

```sh
python scripts/agent_graph/loop.py reclaim   # resets orphaned 'running' tasks -> pending
python scripts/agent_graph/loop.py status    # see exactly where every task stands
```

A `running` task means the graph died mid-iteration before its result was merged, so re-queuing it
is always safe (the execute agent had not committed anything the guardrails reserve for the owner).

The Workflow itself is also resumable within a session: relaunch with
`Workflow({ scriptPath, resumeFromRunId })` and completed agents return cached results.

## The self-scheduling loop

`CronCreate` fires a "run one iteration" prompt on a schedule while this Claude session is idle.
**Caveat: cron jobs are session-only** — they die when the Claude session exits, and auto-expire
after 7 days. The *state* (`agenda.json`) is what survives; the schedule must be re-armed on a fresh
session (one line — see the cron prompt in `loop.py status` context or re-issue `CronCreate`).

For crash-durable scheduling independent of any Claude session, an OS-level cron entry invoking the
CLI headless is the upgrade path — not set up by default because it needs headless auth verified.

## Guardrails are load-bearing

Every task's `guardrails` array is pasted verbatim into both the execute and verify prompts. This is
how the graph respects freezes it must never break — e.g. T1 (window-2) is a **blind, preregistered
out-of-sample test**: the agent diagnoses the *pipeline* failure and must never read or infer the
screen's results. The adversarial verifier explicitly re-checks whether a guardrail was violated.

## Adding work

```sh
python scripts/agent_graph/loop.py add "task title" equities 6
```

then edit `agenda.json` to fill in `why` / `acceptance` / `guardrails` (the fields that make a task
executable and safe). A `completeness critic` agent can also be added as a graph phase to propose new
tasks when the agenda drains.
