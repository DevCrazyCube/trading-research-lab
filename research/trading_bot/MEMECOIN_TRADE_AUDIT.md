# Memecoin paper-trade audit

Generated UTC: `2026-08-27T10:31:06.034349+00:00`

**Verified fact:** every figure below is recomputed from the source snapshots whose SHA-256 is stored in the accompanying JSON. Parallel variants share opportunities and are not added into one investable portfolio.

**Stress assumption:** `UNEXITABLE_TIMEOUT` and terminal `UNPRICED` are valued at a full position loss before the pinned toll. This is a conservative bound, not a claim that every missing mark was literally worth zero.

## Sniper

Resolved rows across arms: **16,458**. Watchdog restart events: **17**. Entries/open positions were not persisted historically. The controlled cutover preserved **70** last-observed open legacy positions as full-loss-stressed dropouts; earlier restart identities remain unknowable.

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
| v3_core_bal | 70 | 47 | 23 | -0.3603 | -0.3603 | 902.5892 | 0 | 0/0 |
| v3_core_confirm | 45 | 28 | 17 | -0.3763 | -0.3763 | 937.7242 | 0 | 0/0 |
| v3_core_ratchet | 69 | 45 | 24 | -0.2844 | -0.2844 | 925.4338 | 0 | 0/0 |

## Frozen MEMEBOT variants

| instrument | pass n | reported mean R | Pump-only n/mean R | full-loss stress mean R | reported paper SOL | stress paper SOL | unexitable | screen violations | non-Pump PASS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MEMEBOT1 | 5 | -0.5200 | 2/-1.1200 | -1.7200 | 9.8700 | 9.5700 | 0.4000 | 0 | 3 |
| MEMEBOT_FAST | 36 | -0.1156 | 5/-0.4301 | -1.1990 | 9.7919 | 7.8419 | 0.3611 | 0 | 31 |
| MEMEBOT_RUNNER | 1 | -1.1364 | 1/-1.1364 | -1.1364 | 9.9500 | 9.9500 | 0.0000 | 0 | 0 |
| MEMEBOT_G73 | 2 | -1.1364 | 1/-1.1364 | -4.6818 | 9.9000 | 9.5880 | 1.0000 | 0 | 1 |
| MEMEBOT_QUICK | 20 | -0.3335 | 7/-0.2629 | -1.9835 | 9.6665 | 8.0165 | 0.5500 | 0 | 13 |
| MEMEBOT_EXIT | 20 | -0.3346 | 0/— | -1.8346 | 9.6654 | 8.1654 | 0.5000 | 0 | 20 |
| MEMEBOT_EXIT_V2 | 1 | 1.8800 | 1/1.8800 | 1.8800 | 10.0940 | 10.0940 | 0.0000 | 0 | 0 |

## Genome population

Ledger genomes: **91**; active: **60**; priced PASS resolutions across arms: **837**; terminal unpriced PASS rows: **1,402**.

| reported rank (mature) | n | mean R | stress rank (mature) | n | stress mean R |
|---|---:|---:|---|---:|---:|
| gbf5381889cc | 53 | 1.3365 | g6660a80499e | 20 | 0.4828 |
| g6660a80499e | 20 | 1.2580 | gccff49ad832 | 20 | 0.4027 |
| g4a46b10f29e | 31 | 1.0790 | g4a46b10f29e | 31 | 0.2939 |
| g73c7da8372a | 86 | 0.9592 | g73c7da8372a | 86 | 0.1102 |
| gccff49ad832 | 20 | 0.8318 | g983d66ffda8 | 24 | 0.1061 |
| g983d66ffda8 | 24 | 0.8304 | g4a86499e9ec | 20 | 0.0993 |
| g297afb0cd08 | 20 | 0.7681 | ge3f1878f15a | 20 | 0.0884 |
| ge3f1878f15a | 20 | 0.5761 | g297afb0cd08 | 20 | -0.0567 |
| gfd95f9aa149 | 25 | 0.4322 | g5b24ec025ed | 20 | -0.2118 |
| g4a86499e9ec | 20 | 0.3015 | gfd95f9aa149 | 25 | -0.8081 |

## Mechanical findings

- Sniper median fixed round-trip tip/notional: **0.7500**.
- Legacy sniper ledgers contain only resolutions; entries lost on historical restarts are unknowable and entry hashes cannot be recomputed from the retained fields.
- Genome candidates that are simultaneously in the falsified registry: **none**.
- Genomes clearing the K=77 noise bar after the full-loss stress: **none**.
- Reported price marks remain paper observations. Exact position-sized on-chain exit quotes, landing failures and latency are not present in these ledgers.
