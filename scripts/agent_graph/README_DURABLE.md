# Durable supervisor — autonomous trading-research on the OS crontab

This is the **durable, self-restarting** replacement for the fragile session-only
`CronCreate` jobs. The schedule lives in the on-disk **user crontab** and is fired by
**cronie** (`crond`), so it keeps running with **no manual re-arming** across:

- Claude-session death (the tick spawns its own fresh headless Claude each time),
- crashes (each tick is independent and takes an `flock` so it can't stack),
- reboots (cronie is a system service; the crontab is on disk).

**Research / paper only.** No real money, no orders, no broker auth, no spend, no
`git commit`. It never touches the t4 real-money path.

---

## Cadence — AGGRESSIVE

```
0 */3 * * *   ->  every 3 hours, on the hour: 00 03 06 09 12 15 18 21  = 8 ticks/day
```

Each tick is **bounded**: it runs the cheap pure-python engines, then does **exactly one**
thinking chunk chosen by hour-of-day. Over a day all four chunks run, but no single tick
runs all of them — that is what keeps per-tick token use bounded.

| hour        | chunk                                   |
|-------------|-----------------------------------------|
| 00, 12      | **A — Strategist** (primary; converge on a trading direction) |
| 03, 15      | **B — Invention round** (fresh angles, honest discipline, dead-ledger) |
| 06, 18      | **C — Newsdesk propose** (read live news; asymmetric setups or abstain) |
| 09, 21      | **D — Predmarket propose** (agent-vs-crowd calibration on politics markets) |

---

## What one tick does (`durable_tick.sh`)

1. **flock** — non-blocking lock; if the previous tick is still running, log and exit
   (no stacking).
2. **cd repo + source `.env` defensively** — only well-formed `KEY=VALUE` lines are
   exported, which sidesteps the known `.env` line-5 bare-key bug
   (`CHAINSTACK_API_URL` with no `=`) that would otherwise break `source`.
3. **Pure-python engines** (cheap, free, self-guarded — they refuse on their own if not
   due / already ran / market closed), each under a 600s timeout and `|| true`:
   - `python -m scripts.trading_bot.basket_forward session --refresh-cash`
   - `python -m scripts.trading_bot.newsdesk resolve`
   - `python -m scripts.trading_bot.predmarket resolve`
   These need **no LLM**.
4. **One headless Claude** for the thinking chunk:
   `timeout 3600 claude -p "$(cat supervisor_prompt.txt)" --permission-mode bypassPermissions`
   — a single non-interactive turn that can use bash / write / edit (there is no human to
   answer a permission prompt). Hard 1-hour timeout so a hang can't wedge the tick. All
   output goes to a dated log.
5. **Heartbeat** — one line appended to `logs/durable_heartbeat.log`.

`bypassPermissions` is the permission mode that lets the headless turn use tools without
an interactive prompt; `--dangerously-skip-permissions` is the equivalent flag if you
ever prefer it. `acceptEdits` alone is **not** enough here because the agent must also run
bash and its engine CLIs.

---

## Honest token cost

Every tick spawns a **headless Claude that does real thinking and uses tools** — this is
not free.

- **Per tick:** one bounded agent turn — orient (skim agenda / FINDINGS / memory) plus one
  focused chunk (strategist decision, one invention round, or a newsdesk/predmarket
  proposal pass). Bounded by rotation (one chunk, not four) and the 1-hour wall, but a
  real multi-step agent session's worth of tokens, not a one-shot completion.
- **Per day:** **8 such turns** (every 3 hours). Running fully autonomously, that is 8
  agent sessions/day, ~56/week. This is the real cost of "aggressive." To cut it, widen
  the interval in the crontab line (e.g. `0 */6 * * *` = 4/day) and re-run the installer.

The pure-python engines are negligible by comparison.

---

## How to watch it

```bash
tail -f /home/anont/meme/scripts/agent_graph/logs/durable_heartbeat.log   # one line/tick
ls -t  /home/anont/meme/scripts/agent_graph/logs/                         # dated tick/claude logs
tail -f /home/anont/meme/scripts/agent_graph/logs/cron.log                # raw cron stdout/stderr
crontab -l                                                                # confirm the line is armed
```

Heartbeat lines look like:
`2026-08-23T18:00:03+02:00 TICK hour=18 python={basket_forward newsdesk_resolve predmarket_resolve} claude=ok`

---

## Activate / stop — the exact commands

**Building these scripts does nothing on its own.** Nothing runs until the crontab line is
installed. The owner arms and disarms it:

```bash
# ACTIVATE (arm the every-3-hours schedule; idempotent; preserves all other crontab lines):
bash /home/anont/meme/scripts/agent_graph/install_durable_cron.sh

# STOP (remove only the durable line; leaves the t4 lines and everything else intact):
bash /home/anont/meme/scripts/agent_graph/uninstall_durable_cron.sh
```

The installer removes any prior `durable_tick` line before adding a fresh one, so
re-running it never duplicates. It **preserves** every other entry — the t4 real-money
lines, the `T4_MODE=submit` env line, and the battery/updates/posture checks.
