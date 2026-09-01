# ARM 1 — VIRALITY_ARRIVAL_V2_2 — Pre-Registration

Status: PRE-ACTIVATION, paper-only, no wallet or orders. V2.1 produced zero opens and zero terminal
rows; its genesis/state are retained as diagnostic-only. V2.2 is a new instrument because the shared
lifecycle and all-cost stop changed before any outcome existed.

## Frozen mechanism

- Universe: DexScreener boosted Solana tokens, pair identity pinned on first observation.
- Entry requires pair age >=60 minutes, m5 buys >=10, m5 buys >=40% above the immediately preceding
  observation, buys>sells, price higher, and the honestly-labelled tier-1 transaction-count proxy.
- The two observations must be received no more than 330 seconds apart. A process/network/laptop gap
  cannot become acceleration evidence. The activation cycle only warms history and cannot enter.
- Exactly one sampled position per mint for the entire instrument. Re-entry is forbidden.
- Entry and every terminal outcome are state-first WAL events and idempotent ledger records. A crash at
  either append boundary must replay exactly once.
- Fill basis is `snapshot`, explicitly an optimistic KILL-first bound: multiplicative 1.5% buy and 1.5%
  sell toll, no executable impact or landing delay. A PASS can only earn a causal version.
- Exit: -12% **all-cost** hard stop, widening raw-mark trail 18/25/35%, 12-hour horizon. Three consecutive
  fresh refresh attempts without a price resolve as a full loss. A stale cached mark is never a fill.

## Decision

At 120 distinct resolved mints, use the mint+entry-day cluster bootstrap. PASS requires CI95 lower bound
above zero and no negative late-entry monotonic split. KILL requires CI95 upper bound below zero, the
predeclared late-entry exhaustion signature, an event rate below one entry/week, or a negative book whose
sign is carried by full-loss rugs. CI crossing zero extends once to 200, then KILL. No read is valid with
open/pending positions, a broken chain, duplicate mints, or lifecycle reconciliation failure.

The count proxy is not B20B. This arm cannot authorize real-money trading.
