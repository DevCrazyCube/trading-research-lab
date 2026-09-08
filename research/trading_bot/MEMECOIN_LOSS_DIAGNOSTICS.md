# Memecoin loss diagnostics

Generated UTC: `2026-08-27T15:09:50.288621+00:00`

**Verified fact:** all figures are recomputed from the byte snapshots hash-pinned in the JSON.

**Method warning:** this is post-hoc diagnosis. The fixed feature slices may explain losses, but they are contaminated and cannot become an entry rule without a new frozen forward cohort.

## Why the legacy sniper lost

| arm | n | gross mean R | toll drag R | tip drag R | current-cost mean R | median USD size | gross winners turned net losers |
|---|---:|---:|---:|---:|---:|---:|---:|
| legacy | 290 | -0.0491 | 0.0417 | 1.2454 | -1.3361 | 0.1000 | 77 |
| convex_core | 905 | -0.0616 | 0.0417 | 1.2430 | -1.3463 | 0.1000 | 233 |
| convex_flowmain | 407 | -0.1697 | 0.0417 | 1.2400 | -1.4514 | 0.1000 | 86 |
| convex_widetrail | 415 | -0.1819 | 0.0417 | 1.2406 | -1.4641 | 0.1000 | 89 |
| core_bal | 4390 | -0.0562 | 0.0416 | 1.2441 | -1.3420 | 0.1000 | 1112 |
| core_confirm | 2774 | -0.0473 | 0.0416 | 1.2192 | -1.3081 | 0.1000 | 741 |
| core_ratchet | 2894 | -0.0638 | 0.0417 | 1.2448 | -1.3502 | 0.1000 | 1033 |
| core_rugfilter | 1339 | -0.0564 | 0.0417 | 1.2420 | -1.3401 | 0.1000 | 375 |
| core_tight | 2055 | -0.0902 | 0.0417 | 1.2500 | -1.3819 | 0.1000 | 492 |
| core_wide | 989 | -0.0759 | 0.0417 | 1.2123 | -1.3299 | 0.1000 | 261 |

## Clean sniper V3

| arm | terminal | open | stress mean R | paper equity USD | floor-size share | N100 gate |
|---|---:|---:|---:|---:|---:|---|
| v3_core_bal | 479 | 0 | -0.5484 | 130.3468 | 0.0000 | FAIL |
| v3_core_confirm | 651 | 0 | -0.3807 | 128.5524 | 0.0000 | FAIL |
| v3_core_ratchet | 510 | 0 | -0.5177 | 130.8086 | 0.0000 | FAIL |

Every fixed surge/buy-fraction/liquidity/notional slice with n≥20 remained non-positive: **True**. CONFIRM also was not a strict BALANCED subset (651 vs 479 entries): 34 entries fired below +400 bps and 44 below $15/s after the confirmation wait.

### V3 loss by exit reason

| arm | reason | n | mean R | sum R | share of negative R | median hold s |
|---|---|---:|---:|---:|---:|---:|
| v3_core_bal | exit:catastrophe | 14 | -1.2986 | -18.1809 | 0.0593 | 14.5000 |
| v3_core_bal | exit:flow | 172 | -0.0318 | -5.4748 | 0.1157 | 123.5000 |
| v3_core_bal | exit:maxhold | 1 | 0.3031 | 0.3031 | 0.0000 | 1804.0000 |
| v3_core_bal | exit:maxhold_timeout | 85 | -1.7388 | -147.8003 | 0.4824 | 1825.8223 |
| v3_core_bal | exit:trail | 207 | -0.4421 | -91.5134 | 0.3427 | 23.0000 |
| v3_core_confirm | exit:catastrophe | 21 | -1.2273 | -25.7734 | 0.0775 | 85.0000 |
| v3_core_confirm | exit:flow | 304 | 0.0571 | 17.3692 | 0.1646 | 123.5000 |
| v3_core_confirm | exit:maxhold | 2 | 0.0579 | 0.1158 | 0.0003 | 1804.5000 |
| v3_core_confirm | exit:maxhold_timeout | 65 | -1.7346 | -112.7491 | 0.3390 | 1832.2130 |
| v3_core_confirm | exit:trail | 259 | -0.4896 | -126.8123 | 0.4186 | 42.0000 |
| v3_core_ratchet | exit:breakeven | 73 | -0.2033 | -14.8434 | 0.0483 | 34.0000 |
| v3_core_ratchet | exit:catastrophe | 11 | -1.3399 | -14.7390 | 0.0480 | 9.0000 |
| v3_core_ratchet | exit:flow | 170 | -0.0429 | -7.2900 | 0.1167 | 133.0000 |
| v3_core_ratchet | exit:maxhold | 1 | 0.3033 | 0.3033 | 0.0000 | 1804.0000 |
| v3_core_ratchet | exit:maxhold_timeout | 82 | -1.7387 | -142.5715 | 0.4639 | 1825.1914 |
| v3_core_ratchet | exit:trail | 173 | -0.4905 | -84.8615 | 0.3232 | 21.0000 |

## Frozen MEMEBOT arms

| arm | PASS n | reported mean R | honest stress mean R | unavailable share of negative R | minimum |
|---|---:|---:|---:|---:|---:|
| MEMEBOT1 | 5 | -0.5200 | -1.7200 | 0.7863 | 30 |
| MEMEBOT_FAST | 40 | -0.2161 | -1.4161 | 0.8676 | 30 |
| MEMEBOT_RUNNER | 1 | -1.1364 | -1.1364 | 0.0000 | 30 |
| MEMEBOT_G73 | 2 | -1.1364 | -4.6818 | 1.0000 | 30 |
| MEMEBOT_QUICK | 29 | -0.3707 | -2.1293 | 0.9399 | 30 |
| MEMEBOT_EXIT | 29 | -0.3237 | -1.9789 | 0.9515 | 30 |
| MEMEBOT_EXIT_V2 | 16 | -0.7548 | -0.7548 | 0.6880 | 30 |

### EXIT_V2 loss by exit reason

| reason | n | mean stress R | sum stress R | share of negative R |
|---|---:|---:|---:|---:|
| HORIZON_MARK | 2 | 0.2286 | 0.4573 | 0.0059 |
| STOP | 4 | -1.8333 | -7.3333 | 0.3061 |
| TARGET | 6 | 1.8800 | 11.2800 | 0.0000 |
| UNEXITABLE_TIMEOUT | 4 | -4.1200 | -16.4800 | 0.6880 |

At the observed conditional payoffs, EXIT_V2 needs unavailable exits below **0.0818** to break even; observed was **0.2500**. This is a post-hoc working-hypothesis boundary, not a licensed new threshold.

## Evolutionary experiments

| experiment | arms | PASS arm-observations | unpriced rate | reported priced mean R | stress mean R | confirmed |
|---|---:|---:|---:|---:|---:|---|
| v1_archive | 94 | 2,354 | 0.6444 | 0.5851 | -4.7323 | none |
| v2_current | 24 | 43 | 0.6977 | -1.0299 | -3.0945 | none |

## Evidence-supported actions

- retire V3 from new paper entries: every arm passed N=100 and failed its frozen positive-stress gate.
- do not promote any legacy MEMEBOT arm; FAST crossed N=30 and is honest-kill HALTED.
- continue EXIT_V2 unchanged only until its frozen N=30 gate; current N is below its minimum.
- keep EVO V2 unchanged until genomes mature; archived V1 produced no K-corrected stress clearer.
- do not select a threshold from the post-hoc feature slices in this report.

Open execution gap: these feeds store paper marks, not position-sized on-chain quotes, landing failures, or measured latency.
