# Codex + Claude Dashboard Cheat Sheet

## Open and leave the dashboard

```sh
tmux attach -t meme-agents
```

- Detach safely: press `Ctrl-b`, release both keys, then press `d`.
- Mouse selection is enabled: click a pane before typing into it.
- `Ctrl-b` followed by `Ctrl-b` sends a literal `^B`; it does not detach.

## Pane layout

```text
┌──────────── interactive Codex ───────────┬────────── interactive Claude ──────────┐
│                                          │                                        │
├──────────────────────── owner control shell ──────────────────────────────────────┤
└───────────────────────────────────────────────────────────────────────────────────┘
```

## Dashboard controls

Run these from the bottom control shell:

```sh
# Inspect state
python scripts/interactive_dashboard.py status

# Send a message to one model
python scripts/interactive_dashboard.py send codex "your message"
python scripts/interactive_dashboard.py send claude "your message"

# Take manual control and pause automatic input
python scripts/interactive_dashboard.py take codex
python scripts/interactive_dashboard.py take claude

# Release manual ownership (automation remains off)
python scripts/interactive_dashboard.py release

# Enable sequential automatic handoffs
python scripts/interactive_dashboard.py auto

# Disable automatic handoffs
python scripts/interactive_dashboard.py pause

# Interrupt one model
python scripts/interactive_dashboard.py interrupt codex
python scripts/interactive_dashboard.py interrupt claude

# Stop the handoff watcher
python scripts/interactive_dashboard.py stop
```

## Tmux pane commands

- Split selected pane left/right: `Ctrl-b`, then `%`.
- Split selected pane top/bottom: `Ctrl-b`, then `"`.
- Close the selected pane: type `exit` in its shell.
- Force-close selected pane: `Ctrl-b`, then `x`, then confirm with `y`.
- Move selection: click a pane, or use `Ctrl-b` followed by an arrow key.

Always select the intended pane before closing it.

## Restore Codex if its pane was closed

1. Click the Claude pane.
2. Press `Ctrl-b`, release, then press `%` to recreate the side pane.
3. Run this in the new pane:

```sh
codex --no-alt-screen -C /home/anont/meme -a never -s workspace-write \
  -c sandbox_workspace_write.network_access=true resume --last
```

`-a never` prevents approval prompts. `workspace-write` remains enabled, so operations outside the
workspace fail instead of silently receiving broader access.

## Restore Claude if its pane was closed

Create a side pane and run:

```sh
claude -c --permission-mode auto
```

## Recreate the whole dashboard

Only do this when the `meme-agents` session does not already exist:

```sh
python scripts/interactive_dashboard.py start --first codex
tmux attach -t meme-agents
```

The research databases and scans are checkpointed independently of the dashboard.
