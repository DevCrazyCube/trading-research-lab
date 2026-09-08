# T56 -- NEWSDESK truncated tape: discharged 2026-09-06 (CHUNK B / T61 instrument-integrity duty)

**Filed** 2026-09-05 (while building T55). **Discharged** 2026-09-06T13:0xZ. Shell verified by
execution canary `TICKCANARY-3618019-1788699600-18511`.

## The defect, measured
`newsdesk read` defaulted to `--limit 60`. Measured live this tick against the real feeds:

| quantity | value |
|---|---|
| raw events across 4 feeds (pre-dedup) | **439** |
| unique events after cross-feed dedup | **387** |
| events an agent tick actually saw (old default) | **60** |
| **agent coverage of its own decision surface** | **15.5%** |

All 30 records in `NEWSDESK_PREREGISTRATION_LOG.jsonl` -- every abstention and every frozen setup --
were reasoned over that ~16% slice, and **not one record said so**. `event_stream_id` is `null` in
every record; the coverage ratio appeared, at best, as free text inside a `reason` string.

This is the programme's named failure shape (T52, `selftests-dont-cover-the-data-path`): a green
decision path, a passing selftest and an intact freeze hash, all sitting on a quietly clipped input
surface. It is the **third** confirmed case (after the 56h MEME ARENA outage and T60's i.i.d.-SE
fake-pass) and the second on a *currently live* instrument.

### Second, smaller defect found in the same read
The digest printed `feed_counts` (raw, pre-dedup: 439) beside `shown_counts` (post-dedup: 387) with
no label. Read as coverage, that ratio is wrong in the *conservative* direction (e.g. YAHOO_RSS
259/309 looked like 84% shown when in fact 100% of unique Yahoo events were shown; the other 50 were
cross-feed duplicates). Cosmetic, but it is exactly the kind of unlabelled denominator that turns
into a false claim later.

## Verdict
**NOT cosmetic.** The truncation was at the agent's eyes, i.e. at the decision surface itself, not at
the display of an already-made decision. It also biased T55: counting catalyst starvation on the
display slice would have driven the count down and manufactured the very kill verdict T55 exists to
test. (T55's own docstring already knew this and pulls `--limit 400`; nothing else did.)

## Correction APPLIED (observability only -- no rule, threshold, universe or frozen spec touched)
1. `read` default is now the **whole deduped tape** (`--limit 1000`) rendered in a compact field set
   (`id, source, ts_utc, headline, tickers, assets`). Measured cost: **103 KB / ~26k tokens** for all
   387 events, versus 289 KB with `snippet`+`link` bodies. `--full` restores the bodies. The root
   cause is removed rather than annotated: the default read is now 100.0% coverage.
2. Every read writes a **tape receipt** to `research/data/newsdesk_cache/last_read_receipt.json`:
   `pulled_utc, n_raw_prededupe, n_events, n_shown, coverage_pct, feed_counts_raw_prededupe,
   shown_counts, feed_errors, tape_sha256` (sha256 over the sorted deduped event-id list -- proves
   *which* tape was read).
3. `propose` staples that receipt into every record as `tape_coverage`. For a **frozen setup it goes
   INSIDE the hashed body**, so the coverage claim is part of the tamper-evident forward commitment.
   Verified: `selftest.freeze_hash_stable` still passes.
4. Honest failure modes are explicit, not inferable: no receipt on disk -> `receipt: MISSING`
   ("proposal made without reading the tape"); receipt older than 3h -> `receipt: STALE` with
   `receipt_age_h`. A partial read still prints a loud `COVERAGE_WARNING` naming the exact ratio.
5. `world_reader` now returns `n_raw` and labels the pre-dedup counts `feed_counts_raw_prededupe`.

Verification this tick: hermetic selftest `ALL_PASSED: true` (11/11); live read returned
`n_events 387 / n_shown 387 / coverage_pct 100.0`, `tape_sha256 708fbda5...`, zero feed errors.

## Explicitly NOT done
- **Past ledger records were NOT rewritten.** The 30 existing records stand as written; this document
  is their annotation. Any read of NEWSDESK results before 2026-09-06 must be understood as reasoned
  over ~16% of the available tape, undisclosed at the time.
- No restart, re-epoch, re-freeze or resolution of any instrument. `NEWSDESK_FROZEN.json`,
  `NEWSDESK_PREREGISTRATION.md`, the kill switch and every threshold are untouched.
- No commit, no stage. t4 real-money path untouched.

## Owner note
The applied change is strictly additive observability: it alters what the agent *sees* and what the
record *discloses*, never what counts as a valid setup. If the owner judges that widening the read
default itself constitutes a mid-flight change to a live instrument, the honest remedy is a regime
break marked at 2026-09-06 (per `selftests-dont-cover-the-data-path`: mark a regime break at the fix),
not a rollback -- reverting would restore a known-false input surface.

## Kill-condition status
T56 kill-condition (a) -- "the read path always pulls the full stream **and** prereg records carry
n_shown/n_events" -- is **met**. T56 -> done.
