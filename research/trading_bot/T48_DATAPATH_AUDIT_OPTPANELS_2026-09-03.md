# T48 tranche 3 — DATA-PATH audit of the two option-quote forward panels (T31, T33)

**Date:** 2026-09-03 15:00 CEST · CHUNK B tick · read-only audit, paper only, no orders, no spend
**Tool:** `scripts/trading_bot/t48_datapath_audit.py --t31 --t33` (offline, opens no socket; both
hermetic selftests ALL_PASSED — a planted off-clock day and a planted inherited-ticker row are
each caught before the live run)
**Scope:** the two collectors feeding the pinned convexity evaluator (`convexity_evaluate.py`,
prereg `CONVEXITY_PREREGISTRATION.md`). Instruments 6 and 7 of the T48 audit.

Prior faults: 5 input-surface faults in 5 audited *reader* instruments, 0 in archival collectors
with provenance ([[selftests-dont-cover-the-data-path]]). This tranche audits two archival
collectors, so it is also a test of that pattern.

## Result: 10 checks, 1 FAIL, 1 contained WARN, 8 clean

### T31 (Deribit) — FAIL, recency: one off-clock day counted as a clean gate day

`T31_DERIBIT_FORWARD.md` declares the snapshot clock as **02:15 Europe/Amsterdam = 00:15 UTC**,
and says explicitly that the 9 historical Tardis samples are comparable *only* where the snapshot
clock matches 00:15 UTC. Ten of eleven clean days are metronomic (00:15:00–00:15:01 UTC). The
**first** day is not:

| day | captured_utc | off declared clock |
|---|---|---|
| 2026-08-24 | 13:05:09Z | **11h10m** |
| 2026-08-25 … 2026-09-03 | 00:15:00–00:15:01Z | 0m |

That is the build-day snapshot taken by hand when the collector was written, before the cron
existed. It is recorded honestly in the manifest — nothing checked it. Two consequences:

1. It counts as **clean day 1 of 11** toward the day-30 gate (~2026-09-23), i.e. it is inside the
   gate's own denominator, which is the number that matters.
2. The evaluator steps the T31 panel by **calendar-day difference** (`convexity_evaluate.py:358`
   gap rule, `:653` annualisation). The 08-24 → 08-25 interval spans **11.2 hours** but is
   annualised as a full day, so the first realized-move interval of the panel is measured over
   less than half the horizon it is priced against.

Magnitude: 1 interval of an eventual 30 — small, and it does not touch the sign of anything. But
it is a real inhomogeneity in a frozen forward panel, and the honest disposition is to **exclude
the 08-24→08-25 interval and re-index the gate to 30 on-clock days**, not to silently keep it.

**OWNER-GATED — not fixed autonomously.** `days_clean` is the frozen gate's denominator; dropping
a day from it is re-cutting the pin, which is not an autonomous act (same rule that left the two
T45 gaps open). What this tick DID do: add the assertion, so the fault is visible and cannot be
forgotten at the 09-23 read. Recommended owner decision at that read: score the gate on on-clock
days only (T31 then reads 10 clean, gate ~2026-09-24), and drop 2026-08-24 from any day-over-day
realized-move calculation.

### T33 (US options) — WARN, recency: stale two-sided quotes exist but are CONTAINED

864 rows across the 6 clean days (≈144/day, all **XLE**) carry a two-sided bid/ask stamped
**2025-12-04** — nine months stale — sitting next to live rows with a live-looking price
(e.g. `XLE260930C00074000` bid 18.38 / ask 21.56, dte 28). A consumer that read `bid`/`ask`
without checking `quote_ts` would treat a nine-month-old quote as today's market.

It is contained, twice over, and both containments were verified in code, not assumed:
- `convexity_evaluate.py:220–224` — the evaluator's `two_sided` flag requires
  `quote_ts.startswith(snapshot_date)`. Row-level. Stale rows are excluded from the design.
- The frozen v2 per-underlying eligibility rule (fresh_ok on ≥95% of the first 30 clean days,
  `convexity_evaluate.py:176–194`) excludes XLE and HYG from the December design outright — both
  have sat at fresh_frac 0.62–0.69 vs the 0.70 floor on every single day.

A further 314 stale NVDA rows (stamped 2024-06-10) exist but are **not** two-sided, so they cannot
poison a price either way. No other underlying carries a stale two-sided quote.

**No action.** This is a clean bill with the mechanism written down: the exposure is real, the
guard is real and row-level, and the residual risk is that a *future* consumer of these snapshots
reads bid/ask without the quote_ts test. That is now an asserted check.

### Clean on everything else

- **T31 recency** — 11/11 clean days carry a distinct snapshot sha256; BTC and ETH index prices
  both move on every consecutive day pair (no re-archived stale file inflating the denominator).
- **T31 representation** — BTC and ETH each above the frozen 300-row floor on all 11 days
  (BTC 932–1070, ETH 814–906); enrich_frac 1.0 throughout.
- **T31 attribution** — every row's currency and strike are corroborated by its own Deribit
  instrument name, and the consumer derives the currency the same way (`symbol.split("-")[0]`,
  `convexity_evaluate.py:234`) rather than inheriting it from the query. This is the exact fault
  class that killed the newsdesk's ticker tagging; T31 does not have it.
- **T33 representation** — all 14 declared underlyings present above the frozen 200-contract floor
  on all 6 clean days; `fetch_pages` follows `next_page_token` to exhaustion (this is the
  predmarket page-1 fault, checked for and absent).
- **T33 attribution** — underlying, expiry and strike are all re-derivable from the row's own OCC
  symbol; `parse_occ` raises if the OCC root disagrees with the queried ticker.
- **T33 spot** — exactly one `underlying_price` per underlying per day, never empty, and its
  `underlying_ts` always falls on the snapshot's own date.

**Latent gap (recorded, not a live fault):** `t33_us_options_collect.py:243` swallows a
`parse_occ` failure with a bare `continue` and no counter, so a mis-rooted row would be dropped
**silently and unobservably** — post-hoc audit cannot see it, because the dropped row is not in
the file. Zero evidence of it firing (row counts are stable at 37.9k–40.1k and every surviving row
parses), but the collector is inside its forward window and adding a counter changes the
collector, so: recorded, owner-gated, not touched.

## What this says about the T48 thesis

Six instruments audited, six faults — but the split holds and sharpened:

| instrument class | audited | faults |
|---|---|---|
| reader / proposer surfaces | 5 | 5 (newsdesk sort, newsdesk attribution, predmarket display, predmarket paging, T33 staleness Aug) |
| archival collectors with provenance | 4 (T30, T45, T31, T33) | 1, and it is a *schedule* fault, not a content fault |

T31's fault is of a different kind from the five reader faults: nothing is mis-joined, mis-sorted
or truncated: the data is exactly what it claims to be, and the manifest recorded the anomaly
faithfully. What was missing was any check that the *clock* matched the declared protocol. The
generalisable lesson is narrower than "readers are broken": **a collector's declared schedule is
part of its data contract, and nothing was testing it.**

Remaining for the thesis's kill-condition: **window-2 and MEME ARENA**. If both audit clean, T48
closes `done` and no further auditing is authorised.
