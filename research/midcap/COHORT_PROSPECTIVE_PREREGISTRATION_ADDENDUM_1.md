# Addendum 1 to COHORT_PROSPECTIVE_PREREGISTRATION.md (sha 91b47ac2...) — written before any v2-eligible event

Actual creation of the original prereg (filesystem mtime, UTC): 2026-09-09T15:34:37. The "~16:05 UTC" in its header was an
estimate written at ~15:39 UTC and is superseded by this recorded mtime. The original file is not modified.

## Eligible cohort = v2 epoch
Watcher v2 (Codex handoff 470 repairs: availability clock after fetch, no cursor advance past failures, pagination with cap flag,
raw first-sight retention with labeled fields, alternating poll order) started at **2026-09-09T16:23:11.312701+00:00** and writes
research/midcap/cohort_watch_v2.sqlite. Only events with avail_ns >= that epoch are eligible. Everything from the v1 watcher
(15:20 UTC -> v2 start; cohort_watch.sqlite) is DEVELOPMENT-ONLY and retained.

## Additional pass criterion (stricter; added before any eligible event)
5. board arm median net return at 72 h > 0 (a negative-median strategy is not accepted even if the mean is positive).

## Corrected timeline
Entry week 1 = epoch -> epoch+7d; entry week 2 = epoch+7d -> epoch+14d; outcomes mature +72 h. Earliest full two-week decision:
**epoch + 17 days (~2026-09-26)**. A week-1 interim look (~2026-09-19) is descriptive only and cannot pass or fail the test.

## Unchanged limitations
Control wallets are not activity- or funding-matched; the control arm is the whole-pipeline placebo only in the sense that it runs
the identical code path; chart marks are not fills; quote/transfer taxes and route failures are not measured here.
