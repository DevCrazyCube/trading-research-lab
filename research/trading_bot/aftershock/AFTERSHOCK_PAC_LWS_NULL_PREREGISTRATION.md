# AFTERSHOCK PAC LWS NULL — Launch-Window Sentinel Scalper (control arm, veto OFF)

**Status:** PREREGISTERED PAPER-SCENARIO INSTRUMENT — NOT A PROFIT CLAIM, NO WALLET, NO ORDERS, NO SIGNER.

**Preregistered UTC:** 2026-09-01. A separate ledger; inherits no PAC performance. Reuses V2.4's
already-anchored processed-inclusion executor calibration, so latency modelling is matched against the
veto arm (`AFTERSHOCK_PAC_LWS`).

## Why this exists — the matched control

This is the veto-OFF twin of `AFTERSHOCK_PAC_LWS`. It shares the IDENTICAL sealed code, creation-
anchored feed, V2.4 calibration, caps, convex exit, and coverage-only admission — its ONLY difference
is `veto_enabled = FALSE`: it admits every surviving-window mint regardless of the B20B verdict (the
verdict is still computed and logged as shadow). `LWS − LWS_NULL` over the identical anchored mint
stream isolates the B20B veto's marginal SOL with ZERO population confound, and this arm's raw book IS
the answer to the headline population question — does the fresh-mint (t0+60) population hard-stop less /
trail more than the mid-life exhaustion population the momentum scalp trades.

## Frozen design (set-once)

Identical to `AFTERSHOCK_PAC_LWS` in every respect (creation-anchored feed, coverage-only clause-4
admission, `ReserveState` reconstruction from the feed's `real_token`, `pac_scalp_policy` convex exit,
`pac_v2_runner` audited core reused byte-identically, N_MAX=4 / 0.80 SOL gross cap / cooldown /
correlated-dump breaker, hash-chained ledger + marks, no lookahead) EXCEPT: **`veto_enabled = FALSE`**
— the B20B deadness verdict is computed and shadow-logged but never blocks an entry.

## Honest status

Pre-committed expectation: this control is expected to eat the guaranteed-loss rugs the veto arm avoids
(the atomic unexitable / high-concentration mints), so `net(NULL) ≤ net(LWS)` if B20B's window-1 result
carries forward — but both books are expected materially negative (defense, not edge). Its purpose is
measurement, not profit. Read alongside the B20B window-2 verdict.
