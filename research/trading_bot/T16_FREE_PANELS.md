# T16 — the free forward-data panels

**This is a data asset, not a finding.** Nothing in this document is evidence for or against any
strategy, and the collector computes no signal. Its entire argument is the one
`DATA_PURCHASE_SCOPE.md` §8a makes in a sentence:

> **History that does not exist can only be created by starting now.**

Four free panels, collected append-only, point-in-time, on an hourly cron. Total cost **$0**. No
account was created, no payment detail was entered, and no paid source is used.

**And the honest counterweight, stated before the details rather than after them:** the candidate
this most directly feeds — shortlist **#9, short interest** — is very probably **underpowered**.
FINRA publishes **24 settlement dates a year**. A rule keyed on the SI cycle has roughly **110
bi-monthly observations** in a 2022+ held-out window. `DATA_PURCHASE_SCOPE.md` §7 prices
P(pass) at **~0.05**, and §2b measured Spearman ρ(days-to-cover, borrow fee) = **−0.40** — the free
panel is *anti*-correlated with the variable the mechanism actually runs on. **Collecting is
cheap and the option is real; the option is not an edge.**

---

## 1. What is collected

| # | panel | source | key | cadence | cost |
|---|---|---|---|---|---|
| 1 | **FINRA Consolidated Short Interest** | `api.finra.org` — no key, no account | `settlementDate × symbolCode` | bi-monthly, 24/yr | $0 |
| 2 | **Alpaca asset borrow flags** | `paper-api.alpaca.markets/v2/assets`, read-only GET | `asof_date × symbol` | daily | $0 (key already held) |
| 3 | **iborrowdesk borrow fee** | `iborrowdesk.com/api/ticker/<SYM>` — free IBKR stock-loan mirror | `asof_date × symbol` | daily, watchlist-capped | $0 |
| 4 | **FINRA Reg SHO daily short volume** | `cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt` — no key, no account | `session_date × symbol` | **daily, 252/yr** | $0 |

**Panel 1 — verified live, 2026-08-17.** `GET /partitions/group/otcMarket/name/consolidatedShortInterest`
enumerates **207 settlement dates, 2017-12-29 → 2026-07-31**. `POST /data/...` pages 5,000 rows at
a time (`record-max-limit`, reported by the API), with `record-total` in the response headers.
**3,904,106 rows** across the panel; 15.5k rows/date at the 2017 start, 22.3k at the 2026 end.
Fields: current *and* previous cycle short position, average daily volume, days to cover, percent
change, market class, split flag, revision flag.

**Panel 2 — 14,233 active US equities** (the sealed manifest count; an earlier draft of this
document said 14,214, which was a pre-seeding probe). `shortable`, `easy_to_borrow`,
`borrow_status`, `marginable`, and both margin requirements per symbol. On the seeding run:
**5,233 shortable, 5,234 easy-to-borrow, 8,999 not easy-to-borrow.** This is a **live snapshot with no history anywhere,
including at Alpaca** — which is exactly why snapshotting it daily is worth something. It is also
**our own broker's constraint**, so unlike a third-party fee it is directly actionable:
`DATA_PURCHASE_SCOPE.md` §2b found *every* hard-to-borrow name in the B22G pool was also
`shortable=False` at Alpaca. Panel 2 turns that one-date observation into a growing panel.

**Panel 3 — best-effort, and it is dead at the source.** See §4. It is wired, it is throttled, and
it records its own failure rather than leaving a silent hole. Re-probed 2026-08-17 13:50 UTC: still
a bare connection close on every `/api/` path.

**Panel 4 — added 2026-08-17, precisely because panel 3 is unreachable.** Pipe-delimited,
`Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market`, **~12.2k symbol rows per session**,
with a bare record-count line at the foot that the collector checks against the rows it parsed
before it seals anything. It is not a borrow *fee* — nothing free is — but it is the only free,
**working**, **daily** short-side panel we could find, and it sits on exactly the axis panel 1 is
underpowered on: **252 observations a year against panel 1's 24**.

**And it is the one panel here with a real deadline.** FINRA's CDN keeps a *rolling* retention
window: probed on 2026-08-17, `2018-07-02` returns 403 and `2018-08-01` returns 200. Panel 1's
history is refetchable from a public archive whenever we want it; **panel 4's is not — a session
that ages out is gone.** That makes §8a's argument literally true here rather than rhetorically:
every day this does not run is a session that cannot be bought back.

A 403 is recorded as `UNAVAILABLE`, not as an error, because the CDN answers 403 both for a market
holiday and for a date past retention and the two are indistinguishable from outside. An
`UNAVAILABLE` date older than six days is **retired** and never asked for again; a *recent* one is
retried, because session D's file appears on D+1.

---

## 2. The point-in-time discipline, stated precisely

Two dates, never confused. The distinction is the entire value of the panel.

| | |
|---|---|
| `settlement_date` | the date the short position was **as of**. FINRA's key. |
| `observed_utc` | the moment **we** pulled the bytes. Ours, and unrecoverable later. |

FINRA disseminates a settlement date roughly **eight business days** after it, and the API serves
only the **latest state** of every date — a revision (`revisionFlag='R'`) silently replaces what was
published. Three mechanisms follow from that:

1. **A snapshot file is never overwritten.** The path carries `observed=<UTC timestamp>`; an
   existing path is a hard `Refused`, not a clobber. Manifests and logs are opened in append mode
   only, flushed and `fsync`ed per record.
2. **Re-observing a date writes a SECOND snapshot beside the first** (`--refresh-revisions`, or
   the bounded `--refresh-recent N` the weekly cron line uses). The pair *is* the revision record.
   Nothing is ever replaced. **This matters more than it looks:** a collector that only fetches
   dates it has never seen would never observe a single revision, so the panel's central claim —
   that it records what was knowable *when* — would rest on a mechanism that never fires. The
   weekly line re-observes the four most recent settlement dates whose last look is over a week
   old: ~2.5 MB a year, and without it the revision record is empty by construction.
3. **`verify` re-hashes every sealed snapshot** against the sha256 in its manifest. `gzip` is
   written with `mtime=0`, so the hash is a hash of the *data* and can be recomputed from a copy
   made anywhere. A mismatch means something overwrote a prior snapshot — the one failure this
   design exists to make visible.

### The backfill is NOT point-in-time, and it is labelled

Every backfilled record carries `"backfill": true`. Those dates carry whatever revisions FINRA
applied **before this panel existed**, and their true dissemination date is unknown to us. **A
backtest that treats a backfilled settlement date as knowable on its settlement date is looking
about eight business days into the future.**

Only dates whose *first appearance in the partitions listing* we watched carry
`is_discovery: true` in `FINRA_FIRST_SEEN.jsonl`, with a `first_seen_utc` that bounds real
availability within the poll interval — one hour, on the recommended schedule. **That timestamp is
the asset.** It does not exist in any vendor's history file, and it starts accruing today.

---

## 3. Layout, and what is worth keeping

```
research/data/t16_panels/
  finra_short_interest/
    MANIFEST.jsonl                                  append-only, one record per sealed snapshot
    raw/settlement=<date>/observed=<stamp>.csv.gz   immutable
  finra_regsho_daily/
    MANIFEST.jsonl                                  OK rows carry a sha256; 403s carry a reason
    raw/session=<date>/observed=<stamp>.csv.gz      immutable
  borrow/
    MANIFEST.jsonl
    alpaca_assets/raw/asof=<date>/observed=<stamp>.csv.gz
    iborrowdesk/raw/asof=<date>/observed=<stamp>.csv.gz
  FINRA_FIRST_SEEN.jsonl    append-only discovery log — the irreplaceable file
  COLLECTION_LOG.jsonl      append-only, one record per run INCLUDING failed ones
  COVERAGE.json             derived summary; the only file that is rewritten
  borrow_watchlist.txt      politeness budget for panel 3, editable by hand
```

**`COVERAGE.json` is the only file the collector ever rewrites**, and it is pure derivation from
the manifests. Its `rows_held` for panel 1 counts the **latest snapshot per settlement date**, not
every snapshot: summing all of them would make the coverage number grow fastest exactly when a
re-observation brought the *least* new information, which is the wrong direction for a coverage
figure to move. The raw sum is kept beside it as `rows_across_all_snapshots`.

**On git.** The `raw/` blobs are several hundred MB and are added to `.gitignore`, following the `t3_cache`
precedent (`.gitignore` §"T3 market-data cache": *"The irreplaceable material is the markdown
record, not these blobs"*). The **manifests, the first-seen log, the collection log and
`COVERAGE.json` are small and are NOT ignored** — they carry every sha256, so a blob restored from
a backup can be proved identical to the one that was sealed.

**Which of these blobs are actually recoverable, since `.gitignore` is a bet on that question:**
the panel-1 short-interest blobs are refetchable from FINRA's API at any time, so ignoring them
costs nothing. `FINRA_FIRST_SEEN.jsonl` is not refetchable from anywhere, which is why it is
tracked. **The panel-4 Reg SHO blobs are the awkward case: they are too large to track and they
age out of the CDN, so once retention passes they exist only on this disk.** They belong in a
backup, not in git — flagged here rather than discovered later.

---

## 4. What worked and what did not, on the seeding run of 2026-08-17

| leg | result |
|---|---|
| FINRA partitions enumeration | ✅ 207 settlement dates, 2017-12-29 → 2026-07-31 |
| FINRA backfill | ✅ 207/207 dates, **3,904,106 rows**, 129.4 MB sealed |
| **FINRA Reg SHO daily (panel 4)** | ✅ **2,020 sessions, 2018-08-01 → 2026-08-14, 19,289,192 rows**, 224.2 MB, **0 failures**; 81 dates answered 403 (holidays + pre-retention) and are recorded as `UNAVAILABLE`, not as errors |
| Alpaca borrow flags | ✅ 14,233 assets in one read-only GET (5,233 shortable, 5,234 ETB) |
| revision re-observation (`--refresh-recent 2`) | ✅ 2026-07-15 and 2026-07-31 re-observed; **both original snapshots still on disk beside the new ones**, identical sha256 ⇒ no revision in that interval, which is the mechanism reporting a true negative rather than failing to fire |
| `verify` re-hash of every sealed snapshot | ✅ **2,230/2,230 match, 0 mismatched, 0 missing** |
| **iborrowdesk borrow fee** | ❌ **every `/api/*` path closes the connection without a response** |

Total sealed: **355 MB across 2,230 immutable snapshots**, every one carrying a sha256 in a
manifest that is opened in append mode and never rewritten.

**Steady-state cost, measured:** once seeded, a full `daily` pass through the entrypoint takes
**2.7 seconds** and makes two cheap probes (the FINRA partitions listing and one Reg SHO URL). The
hourly schedule is therefore free in every sense that matters. A not-yet-published session is
probed every hour but recorded **at most once per UTC day**, so the manifest stays a record
instead of accumulating 24 identical rows a day; verified by running three consecutive passes and
confirming the manifest line count did not move.

**The panel-3 failure, honestly.** `https://iborrowdesk.com/` serves its HTML and its JS bundle
normally; `https://iborrowdesk.com/api/ticker/AAPL`, `/api/home_stats`, `/api/most_expensive` and
`/api/v2/coverage` all return `RemoteDisconnected` — nginx **HTTP 444**, a bare connection close.
This is the exact behaviour `DATA_PURCHASE_SCOPE.md` §1 documented (*"returns HTTP 444 after a few
hundred requests"*), and this address had already been used to probe that host earlier the same
day. The API paths were confirmed against the site's own JS bundle, so the route is right and the
block is rate-limiting, not a moved endpoint.

Consequences, all deliberate:

- The leg **never blocks the other two**. It is called last, its exceptions are caught, and a
  zero-row day is written to the borrow manifest as `"status": "FAILED"` with an error count.
- It **gives up after five consecutive failures**, so a banned host is not hammered hourly.
- Its response parser accepts a bare list, a wrapped series under any of six plausible keys, or a
  flat object, and **returns `None` rather than a row of nulls** if none of them carries a `fee`.
  The shape could not be re-verified while the host was closed, and a collector that quietly
  stores nulls for a year is worse than one that logs zero rows.
- IBKR's own file was re-probed as an alternative and is still unreachable: FTP blocked,
  `ftp3.interactivebrokers.com/usa.txt` times out, the `f=4587` page and its
  `ViewShortableStocks.php` sibling render but expose **no data URL** in their markup or scripts.

**So the borrow-*fee* leg may stay empty, and it should be described that way rather than as
"pending".** As of 2026-08-17 there is **no reachable free borrow-fee source at all** — that is a
finding about the world, not a bug in the collector, and anyone who later needs a borrow *rate*
should expect to pay for it. Panel 2 answers the question that actually gates the trade at our
broker — *can we borrow this at all* — without answering *at what rate*. Panel 4 was added in the
gap because it was the one free short-side source that both worked and accrues daily.

---

## 5. Running it

```bash
# one-off, by hand
python3 -m scripts.trading_bot.t16_free_panels backfill        # every SI date + Reg SHO session not held
python3 -m scripts.trading_bot.t16_free_panels backfill --regsho-limit 20   # bounded first look
python3 -m scripts.trading_bot.t16_free_panels daily           # the cron pass, all four legs
python3 -m scripts.trading_bot.t16_free_panels daily --refresh-recent 4     # + revision re-observation
python3 -m scripts.trading_bot.t16_free_panels coverage        # rebuild + print COVERAGE.json
python3 -m scripts.trading_bot.t16_free_panels verify          # re-hash every sealed snapshot
python3 -m scripts.trading_bot.t16_free_panels seed-watchlist  # panel-3 symbols from latest FINRA
python3 -m scripts.trading_bot.t16_free_panels crontab-line    # prints the line below
python3 -m scripts.trading_bot.t16_free_panels selftest        # offline; no network, no key
```

`selftest` checks the two properties the panel's value rests on, on the **failing** side, per
`README.md` §9: that a sealed path **refuses** rather than clobbers, and that the sha256 is a hash
of the **data** rather than of the moment — without the second, `verify` could not distinguish a
restored copy from a tampered one and the append-only claim would be unfalsifiable. It also checks
that a truncated file fails re-hashing, and that the borrow-fee parser returns `None` rather than a
row of nulls.

`backfill` and `daily` run the **same** FINRA rule deliberately: a poll that only ever looks at the
newest date cannot heal a gap left by a night the machine was down, and a panel with an unexplained
hole is worth less than one that self-heals.

### The crontab line — FOR THE OWNER TO INSTALL

**This task installed no crontab and the collector installs none.** Run `crontab -e` and add
exactly this line:

```
17 * * * * /home/anont/meme/scripts/trading_bot/t16_entrypoint.sh
```

and, **optionally but recommended — without it no FINRA revision is ever observed** — this second
line as well:

```
41 6 * * 0 /home/anont/meme/scripts/trading_bot/t16_entrypoint.sh --revisions
```

`--revisions` is the only argument the entrypoint accepts; anything else exits 2 rather than being
passed through, so a typo in a crontab line cannot quietly change what gets collected.

**Why hourly rather than daily.** Each leg is idempotent per UTC day: the two FINRA legs fetch only
dates absent from their manifests, and the two borrow legs skip outright once the day is snapshotted.
So a machine asleep at 21:00 still collects when it wakes, and a new FINRA settlement date gets a
`first_seen_utc` accurate to **within an hour** instead of within a day. That resolution is the
point of the panel. Minute 17 keeps it clear of the top-of-hour jobs already in this crontab.

**Overlap is handled, and it had to be.** The hourly schedule assumes a pass finishes inside the
hour, which is true once the panel is seeded but *false* for a first run or a long catch-up after
downtime — those walk years of Reg SHO sessions and take tens of minutes. The entrypoint takes a
non-blocking `flock` on `research/data/t16_panels/.collector.lock`; a second pass logs one line and
exits 0 rather than racing the first on the same manifests. Verified by holding the lock and
running the entrypoint: it skipped and exited 0.

**Stop:** remove the line(s). There is no other state to unwind — the panel is inert data and
nothing reads it automatically.

---

## 6. What this does not do

- **It finds no edge, and no number here is evidence.** It is a collection.
- **It does not make candidate #9 powered.** 24 observations a year is 24 observations a year, and
  the free variable is anti-correlated with the mechanism's variable. Panel 4's 252 sessions a year
  is a *different* variable — daily short-sale **volume**, not short **interest** and not a borrow
  fee — so it does not rescue #9 either. It is a new panel to build a new candidate on, and no such
  candidate has been specified, let alone tested, let alone survived anything.
- **It places no orders and touches no order path.** Every endpoint is a read-only GET or POST
  against a free source; the Alpaca call is `/v2/assets` on the paper host.
- **It buys nothing.** `DATA_PURCHASE_SCOPE.md` §8's recommendation was *do not buy*, and this
  implements the free half of that recommendation and nothing else.
- **It does not backfill panels 2 and 3.** Neither has any history to backfill — that is the whole
  reason they must start now.
- **It does not solve the borrow-fee problem.** No free source for it is reachable today. Panel 4
  is a substitute in *availability*, not in content.
