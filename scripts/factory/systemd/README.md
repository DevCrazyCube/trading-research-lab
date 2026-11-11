# Daily timer for the FORWARD-CRYPTO v1 paper logger

**Status: INSTALLED by the owner on 2026-11-10 at 20:27:51 UTC**, with the one command below, typed by the owner.
The copies in `~/.config/systemd/user/` were byte-identical to these two files at 20:28 UTC. A test start through
systemd at 20:28:56 UTC exited 0 (`NO_FORWARD_ROW_YET`, 54.5 s, 839 MB peak memory).

**First scheduled run: 2026-11-11 01:20:29 UTC, exit 0.** It appended the first forward day (10 ledger rows for
2026-11-11) and ended at 01:33:35 UTC. Re-verified by hand at 01:36 UTC: hash chain OK, 2,349 stored responses
re-hashed, continuity exact, all 10 rows reproduced within 1e-12 (`DECISIONS.md`, 2026-11-11 01:40 UTC).

These two files are the templates. Editing them changes nothing until they are copied again and
`systemctl --user daemon-reload` is run.

History: earlier that evening an agent's own attempt to install them was denied by the auto-mode permission check.
The agent did not route around that (see `DECISIONS.md`, 2026-11-10 20:18 UTC).

What the job is: `python -m scripts.factory.forward_crypto run`, a paper LOGGER. It places no orders, holds no keys,
touches no account. It reads public Binance and Kraken market data and writes only under
`research/factory/forward/crypto_v1/`.

## Install (owner, one command, from the repo root)

```sh
mkdir -p ~/.config/systemd/user \
  && cp scripts/factory/systemd/forward-crypto-v1.service scripts/factory/systemd/forward-crypto-v1.timer ~/.config/systemd/user/ \
  && systemctl --user daemon-reload \
  && systemctl --user enable --now forward-crypto-v1.timer \
  && systemctl --user list-timers forward-crypto-v1.timer --no-pager
```

It then runs every day at 01:20 UTC (02:20 Dutch winter time). `Persistent=true` makes it catch up after sleep or a
reboot; linger is already on for this user, so no login is needed.

## Check

```sh
systemctl --user list-timers forward-crypto-v1.timer --no-pager     # next run
journalctl --user -u forward-crypto-v1.service -n 30 --no-pager      # last run's output
sed -n '1,12p' research/factory/forward/crypto_v1/STATUS.md          # what the logger says
```

Exit codes of the job: 0 ok, 2 incident (a pin, the hash chain, the data continuity: it appends nothing and writes
`INCIDENT_<utc>.json`), 3 endpoint unreadable (retried after 20 minutes, at most 4 starts in 8 hours), 1 crash,
4 another run holds the lock.

## Memory

Measured: 839 MB peak on the test start (a run that appended nothing) and 785 MB on the first appending run
(2026-11-11, 13 min 7 s wall clock, 97 s CPU: the request pacing dominates). The unit caps it at 2 GB.

This laptop runs `earlyoom` (active since 2026-10-25, default limits). With swap full, it sends SIGTERM to the
process with the highest `oom_score` once available memory is at or below 10 % of what it counts as user memory
(available plus anonymous pages). At its kill of 2026-11-11 01:36 UTC that was 1,013 of 10,305 MiB, so the limit
sits near 1 GB available. The service runs with `OOMScoreAdjust=200`, the user manager's default (checked with
`systemctl --user show`). On 2026-11-10 earlyoom stopped processes in this order: jobs with adjustment 1000, Steam
web helpers and Chrome renderers (300), then adjustment-200 processes by size. A logger run of under 1 GB therefore
comes after those, and after any larger adjustment-200 job such as a video render of another session.

Expected from the unit's settings, not yet observed: a run that is killed counts as a failure, systemd starts it
again after 20 minutes (at most 4 starts in 8 hours), and a later run backfills the missed day.

A manual `status --verify` needs about as much memory as a run (84 s). On 2026-11-11 at 01:36 UTC such a check
overlapped with a 2.25 GB render of another session, and earlyoom stopped the render. Look at `free -m` and at
running renders before starting one. The daily run already re-simulates every ledgered row, so a manual verify is
for doubts, not for routine.

```sh
journalctl -u earlyoom --since today --no-pager | grep 'sending SIG'   # what earlyoom stopped, and when
```

## Remove

```sh
systemctl --user disable --now forward-crypto-v1.timer \
  && rm ~/.config/systemd/user/forward-crypto-v1.service ~/.config/systemd/user/forward-crypto-v1.timer \
  && systemctl --user daemon-reload
```

## Without a timer

Run it by hand any time after 01:10 UTC: `research/factory/.venv/bin/python -m scripts.factory.forward_crypto run`.
A late run backfills the missed days with the same prints and marks those rows `backfilled: true`. Two things a
late run cannot recover: the Kraken ticker snapshot of a missed day (informational, never in P&L), and the Kraken
instrument listing of that day (a backfilled KRAKEN-5K row is simulated with the listing of the day it is appended).
The IDEAL accounts, which carry the pre-declared readings, are unaffected.

Do not edit anything under `scripts/factory/strategies/`, the pinned library files, `landscape/venues.json` or the
CRYPTO-PERP manifest while this runs: the logger refuses with `INCIDENT:PINS`.
