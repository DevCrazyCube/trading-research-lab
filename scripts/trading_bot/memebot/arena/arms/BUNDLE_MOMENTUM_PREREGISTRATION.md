# ARM 2 — BUNDLE_MOMENTUM_V1 — Pre-Registration

Status: PRE-ACTIVATION paper measurement. No wallet, signer, transaction sender or live-money authority.
The burned `+1.167R` SWF result has zero prior weight and used non-executable marginal fills.
The PumpPortal `subscribeTokenTrade` lane is paid data (provider schedule verified 2026-09-02:
0.01 SOL per 10,000 trade events) and must fail closed without a dedicated
`PUMPPORTAL_DATA_API_KEY`; a Lightning/trading credential is never accepted as a substitute.

## Frozen cohort and entry

- Universe is only PumpPortal mints observed by this host at CREATE and then subscribed for trades.
  Mid-stream first sights are excluded and counted. Local receive nanoseconds are the ordering clock;
  chain slots are diagnostic because the public websocket may omit them.
- The first six buy events must span no more than 1.0 second. At the sixth buy, wallet net token
  holdings over every observed buy/sell up to that coordinate are computed. Entry requires at least two
  positive holders and largest-positive/total-positive <95%. This is an at-s6 concentration proxy, not
  the validated t0+60 B20B gate.
- One primary sample per mint, no re-entry. Decision is the sixth-buy receive coordinate.

## Causal paper execution

- Fixed size 0.5 SOL. Entry target is decision+0.9 seconds and fills only on the first same-mint reserve
  observation received at/after that target. No boundary within 60 seconds is `VOID_NO_ENTRY_BOUNDARY`
  and never enters performance N.
- Both curve legs use constant-product virtual reserves, 1.5% fee each leg, 2,250,000 lamports fixed
  round-trip cost and a real-SOL-withdrawable exit cap. Every exit trigger creates a new target at
  trigger+0.9 seconds and fills only on a later boundary. No boundary within 60 seconds is a full loss.
- Primary exit is -12% all-cost, widening 18/25/35% trail, 12-hour horizon. A flat 10% trail comparator
  runs on the same causal entry and tape but cannot choose the primary outcome. Ten minutes without a
  same-mint observation opens a dead-coin exit; absence of a later fill boundary is a full loss.

## Decision

Primary N=120 distinct resolved mints; one early futility KILL is allowed at N>=40 when CI95-hi<0.
PASS requires CI95-lo>0 and survival of the preregistered latency {0.45,0.9,1.8}s x clump
{0.6,1.0,1.5}s replay grid. CI crossing zero extends once to N=240, then KILL. Any broken tape/ledger
chain, missing create coverage, duplicate mint, unresolved lifecycle, or stale/replayed coordinate makes
the read invalid. PASS earns only a co-located landed-transaction V2, never real-money authorization.
