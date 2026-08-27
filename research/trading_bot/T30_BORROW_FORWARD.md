# T30 — daily borrow-fee/availability forward collection (IBKR shortstock)

**Date stood up:** 2026-08-24 (03:00 CEST durable tick, CHUNK B).
**Task:** `T30_borrow_fee_forward_collector` (agenda, queued by STRATEGIST 2026-08-24 00:00).
**Status:** collector built, cron installed, first clean snapshot on disk.

## What this is

A daily archive of Interactive Brokers' public securities-lending availability file
(`usa.txt`: `SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI`) — the actual
loan-desk feed, free, keyless. It converts the preferred-series-RV borrow wall from a
broker *flag* (Alpaca `easy_to_borrow`, which produced the 0/113-pairs verdict) into a
measured *rate and availability*. Scoping and symbology: `BORROW_FEED_SCOPE.md`.

- **Snapshots:** `research/data/borrow_forward/raw/usa_YYYY-MM-DD.txt.gz` (full file)
  plus `extract/extract_YYYY-MM-DD.json` (the 602-symbol target universe:
  508 preferred-RV universe symbols — includes all 226 legs of the 113 B01 pairs —
  plus the 100-symbol B22B/B22G ORB pool; `universe.json`).
- **Integrity:** per-day sha256 + row counts in `manifest.json`; `#EOF` row-count
  trailer validated on every fetch; completeness ledger in `ledger.json`
  (days attempted / clean / failed). `--status` prints the ledger.
- **Schedule:** daily 16:30 Europe/Amsterdam (10:30 ET, US loan desk active), via a
  non-t4 user crontab line:
  `30 16 * * * /usr/bin/python3 /home/anont/meme/scripts/trading_bot/t30_borrow_collect.py >> /home/anont/meme/research/data/borrow_forward/cron.log 2>&1`
- **Manual fallback from any other machine:**
  `curl "ftp://shortstock:@ftp2.interactivebrokers.com/usa.txt" -o usa.txt`
  then `python3 scripts/trading_bot/t30_borrow_collect.py --ingest usa.txt`.

## Access-path facts (measured 2026-08-24, this box)

`BORROW_FEED_SCOPE.md` assumed the FTP wall was the agent sandbox. Measured today:
**the wall is host-side, not ours.** Generic port-21 egress works (ftp.gnu.org
answers); `ftp3.` and `ftp.interactivebrokers.com` connect-timeout on 21 and 990,
while **`ftp2.interactivebrokers.com` serves the file normally** (1.79 MB, 19,676
rows, 772 preferred rows on the 2026-08-23 20:04 stamp). The collector tries ftp2
first and keeps the others as fallbacks. HTTPS republications remain blocked
(iborrowdesk: empty reply; ChartExchange: bot-block per B22G).

## Frozen decision rule (restated verbatim from the agenda, frozen 2026-08-24 00:00 —
## BEFORE any borrow data existed on disk)

> KILL-CONDITION: after 30 clean days, if <10 of the 113 pairs have both legs
> borrowable at fee < that pair's measured gross edge, preferred-series RV is
> PERMANENTLY DEAD and the collector downgrades to passive archive.

Evaluation protocol (frozen now, before any pair-level number has been read):

1. Evaluated once, at the **30th clean snapshot day**, not before. No pair-level
   FEERATE/AVAILABLE readout until then; until that day the only numbers anyone reads
   from the snapshots are the manifest integrity counts.
2. "Both legs borrowable" = both IBKR SYMs present with `AVAILABLE > 0` on ≥80% of
   that pair's clean days. "Fee < gross edge" = median over clean days of
   max(leg FEERATEs) converted to bp/week at fee/52 × 100, compared to that pair's
   measured gross weekly edge from the INVENT_0822 B01 record.
3. Symbology joins via `alpaca_sym.replace(".PR", " PR")`; pairs whose legs cannot be
   joined count as NOT borrowable (missing-data conservatism, per BORROW_FEED_SCOPE §3).

## Honest expectation, stated before the data (BORROW_FEED_SCOPE §4)

**This feed is programme infrastructure, not a B01 rescue.** B01's held-out net is
t 1.48 (insignificant) and dies at 2× the measured half-spread — that fragility is
independent of borrow. Even a best-case borrow result moves B01 from "0% executable"
to "executable at a net indistinguishable from zero." The feed's real value: the
standing both-legs-shortable pre-condition for **all** future RV pair proposals, and
re-opening the 424B5 microcap short tail where Alpaca's refusal-to-lend was mislabelled
as unavailability.

## Ops notes

- The file's `#BOF` stamp showed ~20:04 on Sunday 2026-08-23 at the 03:00 Monday
  fetch — weekend snapshots are stale desk data. The 30-clean-day clock counts
  calendar days as the ledger records them; staleness on weekends is expected and
  does not fail validation.
- Never touches the t4 crontab lines. Collector is idempotent per day (re-runs
  after a clean snapshot are no-ops).

## Amendment — 2026-08-26 03:00 CEST (T35): the day-30 rule is now CODE, pinned on day 2

**Why.** The evaluation protocol above was prose; prose leaves room to choose a window, a
threshold or a pair set after seeing rates. `scripts/trading_bot/t30_borrow_evaluate.py`
implements steps 1–3 verbatim and is sha256-pinned in `T30_BORROW_FORWARD.sha256` together
with the pair record it joins against. On the 30th clean day the tick runs
`--evaluate` once; the script itself refuses below 30 clean days (no override flag) and
refuses if its own hash, the pair record's or this document's has drifted from the pin.

**Pair record.** `INVENT_0822_pairtether_B.json` records B01 only in aggregate, so the rule's
"that pair's measured gross weekly edge" had no per-pair source. `--build-edges` rebuilt the
113 B01 pairs **deterministically from the frozen INVENT_0822 cache** (same files, same screens,
same z52/2.0/0.5/26w state machine as `invent0822_preftether.py`; the count reproduced exactly:
113) and wrote `research/trading_bot/T30_B01_PAIR_EDGES.json` (pinned). The edge used by the
rule is each pair's mean **gross** P&L per active week over the full cached sample
(2018-01-02 → 2026-08-14, 434 weekly points, 302 in design); the design-only figure is stored
alongside, unused. Aggregate only, for the record: median 37.2 bp/active-week, p25 20.5,
p75 58.0, 112/113 positive. Nothing in that file comes from the forward panel. Fee comparison:
`median over clean days of max(leg FEERATE %/yr) / 52 × 100` bp/week — the *more expensive* leg
is charged because the trade is symmetric in z and either leg may be the short.

**Day-1 format check (counts only, 2026-08-24 extract):** 592 rows / 602 universe / 592
matched; 103 distinct B01 legs, 102 present; **107/113 pairs have both legs present** in the
IBKR file (the 6 missing pairs count as NOT borrowable by step 3). FEERATE/AVAILABLE parse
100 %. No rate or availability figure was printed or read. `--evaluate` on day 2: `REFUSED: 2
clean days < 30` (exit 3), as designed.

**Hashes.** The `.sha256` now pins five files: this doc, `t30_borrow_collect.py`,
`universe.json` (unchanged), plus `t30_borrow_evaluate.py` and `T30_B01_PAIR_EDGES.json`. The
pre-amendment doc hash `df2c31a998ca8839a2fed514a2df3ea8258abc7868ee853f5aed994e3d9e1f31` is the
audit trail. Gate day unchanged (≈ 2026-09-22/23, 30 clean calendar days from 2026-08-24).
