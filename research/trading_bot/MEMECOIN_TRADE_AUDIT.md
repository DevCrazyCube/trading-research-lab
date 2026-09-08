# Memecoin paper-trade audit

Generated UTC: `2026-08-27T15:09:50.760681+00:00`

**Verified fact:** every figure below is recomputed from the source snapshots whose SHA-256 is stored in the accompanying JSON. Parallel variants share opportunities and are not added into one investable portfolio.

**Stress assumption:** `UNEXITABLE_TIMEOUT` and terminal `UNPRICED` are valued at a full position loss before the pinned toll. This is a conservative bound, not a claim that every missing mark was literally worth zero.

## Sniper

Resolved rows across arms: **16,458**. Watchdog restart events: **19**. Entries/open positions were not persisted historically. The controlled cutover preserved **70** last-observed open legacy positions as full-loss-stressed dropouts; earlier restart identities remain unknowable.

| variant | n | reported mean R | current-cost mean R | median round-trip tip / notional | cost regimes (gross / toll / full / other) |
|---|---:|---:|---:|---:|---|
| legacy | 290 | -0.0491 | -1.3361 | 0.7500 | 290/0/0/0 |
| convex_core | 905 | -0.0616 | -1.3463 | 0.7500 | 905/0/0/0 |
| convex_flowmain | 407 | -0.1697 | -1.4514 | 0.7500 | 407/0/0/0 |
| convex_widetrail | 415 | -0.1819 | -1.4641 | 0.7500 | 415/0/0/0 |
| core_bal | 4390 | -0.8795 | -1.3420 | 0.7500 | 1579/0/2811/0 |
| core_confirm | 2774 | -1.2406 | -1.3081 | 0.7500 | 148/0/2626/0 |
| core_ratchet | 2894 | -1.3188 | -1.3502 | 0.7500 | 71/0/2823/0 |
| core_rugfilter | 1339 | -0.0564 | -1.3401 | 0.7500 | 1339/0/0/0 |
| core_tight | 2055 | -0.0902 | -1.3819 | 0.7500 | 2055/0/0/0 |
| core_wide | 989 | -0.0759 | -1.3299 | 0.7500 | 989/0/0/0 |

### Sniper append-only event streams (V2 shakeout + clean V3)

| variant | entries | terminal | open | reported mean R | stress mean R | stress equity USD | restart invalidations | commitment/experiment failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v2_core_bal | 149 | 127 | 22 | -0.2412 | -0.9065 | 403.2665 | 57 | 0/0 |
| v2_core_confirm | 68 | 56 | 12 | -0.1950 | -0.9037 | 710.7974 | 26 | 0/0 |
| v2_core_ratchet | 150 | 129 | 21 | -0.2172 | -0.8827 | 408.7453 | 57 | 0/0 |
| v3_core_bal | 479 | 479 | 0 | -0.5484 | -0.5484 | 130.3468 | 0 | 0/0 |
| v3_core_confirm | 651 | 651 | 0 | -0.3807 | -0.3807 | 128.5524 | 0 | 0/0 |
| v3_core_ratchet | 510 | 510 | 0 | -0.5177 | -0.5177 | 130.8086 | 0 | 0/0 |

V3 is **retired from new paper entries** after every arm failed its frozen N=100 positive-stress gate. Existing open positions drain through the restart-proof book.

## Frozen MEMEBOT variants

| instrument | pass n | reported mean R | Pump-only n/mean R | full-loss stress mean R | reported paper SOL | stress paper SOL | unexitable | screen violations | non-Pump PASS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MEMEBOT1 | 5 | -0.5200 | 2/-1.1200 | -1.7200 | 9.8700 | 9.5700 | 0.4000 | 0 | 3 |
| MEMEBOT_FAST | 40 | -0.2161 | 6/-0.5451 | -1.4161 | 9.5679 | 7.1679 | 0.4000 | 0 | 34 |
| MEMEBOT_RUNNER | 1 | -1.1364 | 1/-1.1364 | -1.1364 | 9.9500 | 9.9500 | 0.0000 | 0 | 0 |
| MEMEBOT_G73 | 2 | -1.1364 | 1/-1.1364 | -4.6818 | 9.9000 | 9.5880 | 1.0000 | 0 | 1 |
| MEMEBOT_QUICK | 29 | -0.3707 | 10/0.0800 | -2.1293 | 9.4625 | 6.9125 | 0.5862 | 0 | 20 |
| MEMEBOT_EXIT | 29 | -0.3237 | 0/— | -1.9789 | 9.5306 | 7.1306 | 0.5517 | 0 | 30 |
| MEMEBOT_EXIT_V2 | 16 | -0.7548 | 16/-0.7548 | -0.7548 | 9.3962 | 9.3962 | 0.2500 | 0 | 0 |

## Genome experiments

Ledger files across V1 archive + current V2: **118**; current active genomes: **24**; priced PASS resolutions across both experiments: **850**; terminal unpriced PASS rows: **1,547**.

| experiment | ledger arms | active | K | all resolutions | priced PASS | unpriced PASS | stress clearers |
|---|---:|---:|---:|---:|---:|---:|---|
| v1_archive | 94 | 60 | 80 | 18,615 | 837 | 1,517 | none |
| v2_current | 24 | 24 | 24 | 770 | 13 | 30 | none |

### v1_archive mature ranks

| reported rank | n | mean R | stress rank | n | stress mean R |
|---|---:|---:|---|---:|---:|
| gbf5381889cc | 53 | 1.3365 | gccff49ad832 | 20 | 0.4027 |
| g6660a80499e | 20 | 1.2580 | g73c7da8372a | 86 | 0.1102 |
| g4a46b10f29e | 31 | 1.0790 | g983d66ffda8 | 24 | 0.1061 |
| g73c7da8372a | 86 | 0.9592 | g4a86499e9ec | 20 | 0.0993 |
| gccff49ad832 | 20 | 0.8318 | ge3f1878f15a | 20 | 0.0884 |
| g983d66ffda8 | 24 | 0.8304 | g4a46b10f29e | 33 | -0.0033 |
| g297afb0cd08 | 20 | 0.7681 | g6660a80499e | 22 | -0.0176 |
| ge3f1878f15a | 20 | 0.5761 | g297afb0cd08 | 20 | -0.0567 |
| gfd95f9aa149 | 25 | 0.4322 | g5b24ec025ed | 20 | -0.2118 |
| g4a86499e9ec | 20 | 0.3015 | gfd95f9aa149 | 25 | -0.8081 |

### v2_current mature ranks

| reported rank | n | mean R | stress rank | n | stress mean R |
|---|---:|---:|---|---:|---:|
| — | — | — | — | — | — |

## Mechanical findings

- Sniper median fixed round-trip tip/notional: **0.7500**.
- Legacy sniper ledgers contain only resolutions; entries lost on historical restarts are unknowable and entry hashes cannot be recomputed from the retained fields.
- Genome candidates that are simultaneously in the falsified registry: **none**.
- Genomes clearing their own experiment's K noise bar after full-loss stress: **v1_archive=none; v2_current=none**.
- Reported price marks remain paper observations. Exact position-sized on-chain exit quotes, landing failures and latency are not present in these ledgers.
