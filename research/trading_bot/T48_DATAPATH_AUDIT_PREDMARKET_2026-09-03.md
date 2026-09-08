# T48 tranche 2 -- DATA-PATH audit of the PREDMARKET puller

Date: 2026-09-03 (STRATEGIST tick, 12:00 CEST)
Instrument: `scripts/trading_bot/predmarket/venues.py` (the venue readers behind `predmarket pull`)
Status: **FAULT FOUND (confirmed live), FIXED, hermetically regression-tested.**
Money: none. Read-only public GETs. No ledger row was written by this audit (`--no-resolve` path only).

## Why this collector was next

Four input-surface faults have now been found in live forward instruments and **none** was caught by
a green decision-path selftest (method rule, 2026-09-02). All four lived in *reader* instruments,
not archival collectors with provenance. The predmarket puller is a reader, and it had never been
audited against the three criteria: **recency**, **representation**, **attribution**.

## The fault: both venue feeds are PAGED, and both were read one page deep

Measured live, at the moment of the audit:

| feed | what the puller read | what actually exists |
|---|---|---|
| Kalshi `/events?limit=200&status=open` | page 1 = exactly 200 events, non-empty `cursor` never followed. Of those 200, only **39** were rank-1 political (Politics/Elections/World) -> **268 political markets visible** | >= **11,687** political markets over >= 2,282 political events; still not exhausted after 20 pages / 4,000 events |
| Polymarket `/events?tag_slug=...&limit=100` | one page per tag, `offset` never used | **6 of 8** declared tags returned exactly the cap (truncated). Two declared tags -- `policy` and `us-current-affairs` -- return **0 events** and never did contribute anything |

So since the 2026-08-23 freeze the proposer has been choosing from **<= 2.3% of the Kalshi political
book**, and the slice was selected by *the venue's own undisclosed page ordering*, not by us. The
digest then sorted that slice by volume and printed it, which made it look like the top of the book.
That is the same shape as the 2026-09-02 newsdesk fault (a sort/truncation upstream of a correct
decision rule) and the same shape as the T43 `--limit 40` digest fault: **a filter applied after an
invisible truncation cannot tell you what it never saw.**

## Fix (input surface only -- no frozen decision rule touched)

`is_selectable`, the rank-1 category set, the cost model and every proposal rule are **unchanged**.
Only the breadth of the read and its reporting changed:

* `pull_kalshi(max_pages=60)` now follows the `cursor`; `pull_polymarket(..., max_pages_per_tag=6)`
  now pages by `offset` and stops early when a page comes back short.
* Both return `(markets, feed_stats)`. `pull_open_markets` surfaces `feed_stats` and a
  `data_path_warnings` list; `predmarket pull` prints both, plus `n_displayed` / `display_rule`
  and an explicit DISPLAY-TRUNCATED warning when the volume-ranked digest is cut.
* New CLI knobs: `--kalshi-max-pages` (1 reproduces the pre-fix read), `--poly-max-pages`,
  `--criteria-chars` (bounds the digest now that the whole book is in scope).

Post-fix live read: **27,827 selectable markets** (vs ~200 before), 46 s, and the pull now says out
loud that it is *still* capped and that two declared tags are empty. **A truncation you can see is a
bounded sample; one you cannot see is a bug.** The residual cap is deliberate: an unbounded page
walk inside a tick is the crawl the standing rule forbids.

## Regression test (the point of the exercise)

`predmarket selftest` gains `datapath_pagination_follows_and_truncation_is_reported`: a synthetic
cursor-paged feed asserts the pager reaches exhaustion, that hitting the cap is reported as
`exhausted: false`, and that a truncated feed / a zero-row feed / a declared-but-empty tag each
raise a warning. `ALL_PASSED` green including the new check. This is a **data-path** assertion --
none of the eight pre-existing decision-path assertions moved, and none of them would have failed.

## Ledger consequence -- a REGIME BREAK, recorded not smoothed

Proposals frozen **before 2026-09-03T10:04Z** were selected from a ~2% page-1 slice; proposals after
are selected from a ~100x wider, volume-ranked book. These are two input regimes.

* **Selection-conditioned metrics do NOT pool**: hypothetical expectancy, edge size, hit rate.
* **Calibration DOES survive**: Brier-agent vs Brier-market is scored per market against the same
  market's own price, so it remains a valid observation whatever process surfaced the market. The
  65 open estimates stay open and stay scorable on calibration; the first settlements (09-06,
  09-20) are unaffected. `PREDMARKET_PREREGISTRATION_LOG.jsonl` was not touched and no hash moved.

## What is still unaudited (T48 remaining)

T31 (Deribit), T33 (US options), window-2, MEME ARENA. Newsdesk fixed 09-02; T30/T45 clean 09-03.
