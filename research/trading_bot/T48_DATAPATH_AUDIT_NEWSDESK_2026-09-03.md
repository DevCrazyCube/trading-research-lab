# T48 tranche 4 -- data-path audit: NEWSDESK world-reader

Date: 2026-09-03 18:00 CEST (tick hour 18, CHUNK C -- NEWSDESK propose)
Instrument: `scripts/trading_bot/newsdesk/` (world_reader.py, __main__.py, selftest.py)
Status: **THREE FAULTS FOUND (all confirmed live), ALL FIXED, hermetically regression-tested.**

The audit was not the assignment -- CHUNK C is "read the world and propose or abstain". The faults
were found *while doing the chunk*, by applying the standing method rule (assert recency AND per-feed
representation on the input surface before reasoning over it). That is the intended way for this rule
to fire: the surface check is cheap enough to run inside the normal duty.

## Fault #7 -- the digest hid most of the stream, and whole feeds

`cmd_read` pulled all feeds into one stream, sorted it globally by timestamp descending, then emitted
`events[:60]`. Representation was therefore luck-of-the-timestamp, and the highest-volume feed won.

Measured live at 2026-09-03T16:01Z (`feed_counts` 340 events):

| feed | in stream | shown to the agent | visible |
|---|---|---|---|
| YAHOO_RSS | 315 | 38 | 12% |
| SEC_8K | 40 | 7 | **18%** |
| COINGECKO_TRENDING | 15 | 15 | 100% |
| GOOGLE_NEWS | 15 | **0** | **0%** |

The agent that proposes off this digest was seeing 17.6% of the stream, and the bias was not random:
CoinGecko stamps its events at pull time (age 0.00h) so it always won the head, while SEC_8K -- the
only feed carrying hard, non-narrative catalysts -- was 82% invisible, and Google News was entirely
invisible. **Fix:** `_stratified()` round-robins across feeds so every feed present is represented by
construction, and the digest now reports `shown_counts` per feed alongside `feed_counts`. Post-fix
read: SEC_8K 30, YAHOO_RSS 30, GOOGLE_NEWS 15, COINGECKO 15.

## Fault #8 -- per-query failures were swallowed silently

`read_google_news` caught `Refused`/`ParseError` **per query** and `continue`d. All five standing
queries could fail and the feed would report `count=0` with `feed_errors == {}`. `_collect`'s error
handler only fires if the whole function raises, which this function never did. The module's own
docstring promises "a feed that errors is recorded as an error rather than silently dropped" -- it
was not true for the one feed that loops. Observed live: GOOGLE_NEWS went 15 -> 0 across two pulls
90 seconds apart with no error recorded. **Fix:** failures accumulate; a partial failure is surfaced
through `feed_errors` as `PARTIAL: ...`, and total failure raises past the boundary.

## Fault #9 -- the throttle is a valid, empty, 200 OK response (the worst of the three)

Google News RSS throttles by serving a **well-formed RSS envelope containing zero `<item>`s**. HTTP
200, valid XML, correct channel title, current `lastBuildDate`. No exception is raised, so fault #8's
fix would not have caught it either. Measured directly:

```
stock market       bytes=1118  items=0
Federal Reserve    bytes=1124  items=0
earnings           bytes=124443 items=103   <- then, ~60s later:
earnings           bytes=1110  items=0
inflation          bytes=1112  items=0
```

The same broad query returned 103 items and then 0 within a minute. Not encoding (`quote_plus`
behaves identically), not query-specific -- it is a request-rate throttle. This is the sharpest case
yet of the family: the module's stated principle "absence is not a signal" is *correct for a real
feed and exactly wrong for a throttled one*, and nothing in the code distinguished them. **Fix:** for
a broad standing keyword query, an empty-but-valid result is not a state of the world; it is recorded
as `BLANK (valid RSS, 0 items -- throttled)` and flows into `feed_errors`, with all-blank raising.

## Regression tests

`newsdesk selftest` gains two assertions (green, hermetic, no network):
- `datapath_digest_represents_every_feed` -- a synthetic 500/3/1 three-feed stream must show all
  three feeds in a 60-slot digest, and must not starve the low-volume feeds.
- `datapath_feed_failure_never_silent` -- a flaky feed must surface `partial_errors`; a blank-but-
  valid feed must raise; a fully failing feed must raise.

## What this tick's CHUNK C actually decided

**ABSTAINED** (logged to the newsdesk ledger). Content reason: the tape is entirely second-day
AI-narrative commentary already traded (AVGO 2028 guide, NVDA/HuggingFace $12.9B, SNOW/HPE
post-earnings takes), and the now-visible 8-K feed is FHLB Item 2.03 debt boilerplate, CMBS trust
exhibits and routine Item 5.02 officer changes -- no statable asymmetry. Method reason, decisive:
this was the first read through a repaired surface, so a proposal today would confound a new setup
with a change in the selection process.

**REGIME BREAK recorded 2026-09-03.** The newsdesk's pre-fix and post-fix proposal pools are not the
same experiment and must not be pooled. The ledger's 2 resolved rows (expectancy -0.474R) were all
selected off ~18% of the stream; they stay in the record, labelled, and the forward count for any
newsdesk verdict starts from the post-fix proposals.

## Scoreboard for the T48 thesis

Nine faults now, across eight audited instruments. The split holds and sharpens:
**7 faults in 6 reader/discretionary surfaces, 1 fault in 4 archival collectors** (and that one was a
schedule fault, not a content fault). The thesis' claim -- that our blind spots live in the surfaces
an agent *reads through*, not in the ones that *write to disk with provenance* -- is now supported by
the two instruments that had never been checked at all.

Refinement the tranche adds: the faults are not bugs in fetching. All three here are faults in
**what the fetched data was reduced to before an agent saw it** -- a truncation, a swallowed
exception, and a silence that looked like data. A collector is honest because someone later diffs its
output against the source. A reader is never diffed against anything, because its output goes
straight into a judgement.

## Kill-condition (unchanged)

window-2 and MEME ARENA are the last two instruments. If both audit clean, T48 closes `done` and no
further auditing is authorised -- the programme holds the line to the 09-22 / 09-23 clocks.
