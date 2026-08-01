# B9n — the direct-route cost boundary, and a proposed simulator cost contract

Measured 2026-08-01 over the **full frozen population, all 94,985 transactions**. No sampling.
Artifact read-only, zero network calls, collector not restarted, **no simulator implementation
started**.

Status: **UNRATIFIED PROPOSAL.** `DECISIONS.md` remains authoritative. §4 is a proposal for the
owner to accept, amend or reject; nothing in it is frozen by this document existing.

## 1. The question

B9m established that all 4,962 unattributed transactions contain at least one unpinned program, and
raised the obvious next move: pin the 62 third-party ABIs. Before spending that, the prior question
is whether those programs can affect the route **this project would actually execute**.

`PLAN.md` line 37 and `DECISIONS.md` (2026-08-01) freeze the regime: *"Initial entries are Pump-only;
PumpSwap is not an entry venue."* Our route is a direct Pump bonding-curve buy or sell in a
transaction the simulator constructs itself.

## 2. The measurement that answers it

**Which programs can execute inside a Pump trade's own CPI subtree?** A transaction we construct
contains only the instructions we put in it, so the only way an unpinned program reaches our cost is
if Pump itself invokes it. Measured across **93,448 Pump trade instructions**:

| program | trade subtrees containing it | pinned? |
| --- | ---: | --- |
| `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ` | **93,448 / 93,448 (100%)** | **NO** |
| `6EF8rrec…` (Pump self-CPI) | 93,448 | yes |
| `TokenzQdB…` (Token-2022) | 93,405 | yes |
| `1111…` (System) | 52,704 | yes |
| `Tokenkeg…` (SPL Token) | 787 | yes |
| `AToken…` (ATA) | 52 | yes |

**Exactly one unpinned program appears inside a Pump trade: `pfee`, and it appears in every single
one.** Jupiter, `DF1ow4ts…`, `proVF4pM…`, `BBRouter…` and the other 61 unpinned programs **never**
appear inside a Pump trade subtree — they are outer-level routers wrapping the trade.

### Consequence, and it inverts the plan

- **The 61 router ABIs do not need pinning for the cost model.** They cannot enter a transaction we
  construct. A 62-ABI pinning campaign would buy nothing for the direct route. This is the answer to
  "identify `DF1ow4ts` only to the extent needed": its identity does not matter, because its
  *position* — outside every Pump trade subtree — already settles the question.
- **`pfee` is the one that does need pinning**, and it is the one that looked like noise. It is
  unavoidable, on 100% of trades, and its ABI is not pinned. It is now the top evidence gap.

`b9m.DIRECT_ROUTE_PROGRAMS` includes `pfee` for exactly this reason. That inclusion asserts it is
**unavoidable**, and is the opposite of calling it pinned — the two sets are held distinct by test.

## 3. Where the cost model is already complete

Splitting the population by route:

| | direct route | routed |
| --- | ---: | ---: |
| transactions | 32,364 | 62,621 |
| `exact` | **32,272 — 99.716%** | 56,097 — 89.582% |
| `undecodable_instruction` | **0 — 0.000%** | 1,654 — 2.641% |
| `unattributed_movement` | 92 — 0.284% | 4,870 — 7.777% |

**All 1,654 SPL Token tag-45 instructions are on routed transactions. Zero are on the direct
route.** The bounded unknown that B9l left fail-closed cannot occur on the path we would execute, so
it does not gate the simulator. It remains refused where it does occur.

### The 92 direct-route residuals, investigated individually

All 92 were examined transaction by transaction, not sampled.

- **All 92 residuals are negative, without exception.** `residual = payer_debit − attributed`, so a
  negative residual means the payer **received** lamports the model did not credit. A cost model
  that ignores them therefore **overstates** cost. The error is bounded and in the conservative
  direction — that is a property worth stating precisely, not a reason to dismiss them.
- **Magnitude, excluding one non-trade row:** 91 trade-bearing transactions, total 0.6148 SOL,
  **max 0.0234 SOL**, median 0.0066 SOL, p90 0.0147 SOL.
- **One row carries 11.115 SOL of the 11.73 SOL aggregate and is not a trade at all** (`n_trades =
  0`). Quoting the aggregate without separating it would misdescribe the exposure by 18×.
- Composition: 62 sells, 17 buys, 12 multi-trade, 1 non-trade — reconciling exactly with the 79
  named in the previous handoff (79 = 62 + 17; the other 13 are claimed by earlier categories).

**Causes tested and refuted**, each because the evidence invites it:

1. **Account lifecycle** — closed/created accounts explain only **4 of 92** exactly (4 more within
   2%). 33 have **no closed account at all** yet still carry a negative residual.
2. **A pinned Pump account's rent.** The dominant constant, `−1,844,400`, is exactly the rent-exempt
   minimum for a **137-byte** account under `890880 + 6960·size`. All five Pump account layouts were
   sized from the pinned IDL: `BondingCurve` 115 B (1,691,280), `UserVolumeAccumulator` 106 B
   (1,628,640), `GlobalVolumeAccumulator` 544 B, `Global` 1045 B. **None is 137 bytes.** The
   arithmetic is exact and the attribution is still wrong.
3. **The payer being a fee recipient.** The payer *is* the TradeEvent `user` in 91 of 92 (and also
   the `creator` in 10), yet **no pinned fee field** — `fee`, `creator_fee`, `cashback`,
   `buyback_fee` — equals the residual in any of the 92.
4. **Accounts closing via `CloseAccount`.** 59 of 92 have an account that closes, but only 10 carry
   a `CloseAccount` instruction. Accounts are closing with **no instruction recording it**, which is
   the signature of a program closing an account it owns.

**No defect in pinned reconciliation is established, so no behaviour was changed.** The residuals
are consistent with program-owned movement by `pfee` — which §2 shows is present in every trade —
but "consistent with" is not evidence, and `pfee` is not called neutral or pinned on the strength of
it. Two observed sells show two accounts receiving near-identical amounts (21,464,338 / 21,464,337),
which looks like an even fee split; that is a lead, not a finding.

## 4. Proposed cost contract

### 4a. The principle: price our route, never filter the population

`DECISIONS.md` (2026-08-01) already rejected restricting the population to wallet-cost-exact
transactions because *"that selection depends on transaction shape and rent-reclaim behavior; it
would bias the evaluation."* **Selecting on route is the same move and is equally forbidden.** A
cohort member must not be dropped because the trader who happened to be observed used Jupiter.

The resolution is that these are different objects:

- **Eligibility** is a point-in-time predicate on the *token and market state* at the decision
  instant — SOL-paired, non-Mayhem, curve open. It never reads any transaction's realized structure.
  Every eligible decision is priced.
- **Cost** is a deterministic function of *our* constructed direct-route transaction, evaluated
  against market state. It never reads the observed trader's costs.

Because cost consumes market state rather than an observed transaction, realized transaction
structure cannot enter the evaluation, and the selection-bias problem does not arise.

**This requires amending `docs/EXECUTABLE_RETURN.md` §1**, which currently defines `Q_in` as *"quote
lamports debited to acquire the position, **from the entry transaction's own balance evidence**."*
That reads someone else's route — including their router fees — and is the exact defect this section
exists to prevent. Proposed replacement: `Q_in` is the quote debited by *our* constructed direct
trade at the decision instant's reserves. Flagged as an owner decision, not changed here.

### 4b. Cost terms, with verification status

| term | source | status |
| --- | --- | --- |
| curve quote (`quote_amount`) | pinned curve arithmetic at decision-instant reserves | **exact**, 93,253/93,253 |
| protocol fee | `ceil(quote·bps/10000)` | **exact**, verified |
| creator fee | `ceil(quote·bps/10000)` | **exact**, verified |
| cashback | pinned `TradeEvent` field | **exact** |
| base signature fee | 5,000 lamports/signature | deterministic |
| ATA rent | `2,039,280`, refunded on close | deterministic; point-in-time predicate on whether the ATA exists |
| **buyback fee** | `floor(fee · bps / 10000)` — base is the protocol `fee`, rounding FLOOR | **RESOLVED 2026-08-01**, exact 93,253/93,253 |
| **`pfee` program movement** | both its accounts are `writable = False` in the pinned Pump IDL | **RESOLVED 2026-08-01** — cannot move lamports on this route |
| fee tier table | `fee_basis_points` constant at 95 across all 93,448 observations in-window | **in-window only**; a tier crossing needs `FeeConfig` |
| priority fee | our choice; *level required to land* unmeasured | **UNMEASURED** |
| Jito tip | unmeasured | **UNMEASURED** |
| slippage under competition | unmeasured | **UNMEASURED** |
| failed-transaction fees | 1,192,263 of 1,287,248 in-window signatures failed | **UNMEASURED** for our own submissions |

### 4b-i. The two gaps that were blocking ratification, and how they closed

**Buyback fee base — resolved.** `buyback_fee == floor(fee · buyback_fee_basis_points / 10000)`,
exact on **93,253/93,253** through the B9i gate and **93,448/93,448** over every decoded
`TradeEvent`. The base is the protocol `fee`; the rounding is **floor**, and it is the only fee in
the module that does not use `ceil`. The long-standing *"matches `ceil` on 46,500 of 93,253 —
essentially half"* was never evidence of an unknown base: at 5,000 bps `ceil` and `floor` agree
exactly when `fee` is even, so ~50% is the signature of the wrong rounding mode. B9i's
`unestablished` bucket is now **empty** on the full population.

**`pfee` — resolved for cost, not pinned as an ABI.** See `research/B9O_PFEE_ROUTE_SEMANTICS.md`.
The already-pinned Pump IDL declares `fee_config` and `fee_program` as **`writable = False`** on all
six trade instructions, and those are exactly the two accounts the fee CPI receives. The runtime
forbids modifying a non-writable account's lamports, so `pfee` **cannot move lamports on the direct
route** whatever its instruction set is — a structural guarantee, corroborated by 12,022/12,022
unchanged balance observations. Its ABI remains unpinned and unknown discriminators stay
fail-closed; that is sufficient because the ABI is not needed for cost.

### 4b-ii. Preregistered conservative defaults

Frozen **before** any return is computed, so they cannot be tuned to an outcome:

| policy | default | why conservative |
| --- | --- | --- |
| protocol fee | 95 bps | the only value observed; a tier crossing fails closed instead |
| creator/cashback 30 bps | per-token, from the token's own observations | **constant within every one of 1,110 mints** — 0 vary, so it is a point-in-time token property, not a per-trade unknown |
| buyback fee | `floor(fee · 5000/10000)` | exact, no default needed |
| base fee | 5,000 lamports per signature | deterministic |
| ATA rent | charge `2,039,280` on entry; **assume no refund** on exit | refusing to credit the reclaim understates proceeds |
| priority fee | charge a non-zero floor; **never assume zero** | zero priority fee is the optimistic extreme |
| Jito tip | charge if modelled; never credit | unmeasured |
| failed submissions | charge base + priority fee for each modelled failure | only 7.38% of in-window signatures succeeded |
| direct-route residuals | **ignore the 92** | all negative, so ignoring them overstates cost; bounded ≤0.0234 SOL per affected trade |

### 4c. Fail-closed rules

The model **refuses to price** and records a no-trade with a reason, rather than emitting a number,
when any of these hold:

1. **Curve complete at the decision instant** → `L3` structural unavailability. No invented mark, no
   assumed migration (`DECISIONS.md` exit boundary).
2. **Reserves not reconstructible** at the instant from the pinned path → refuse. A quote from
   unverified reserves is a guess wearing integer precision.
3. **Quote mint is not native SOL, or Mayhem mode is set** → outside the frozen regime.
4. **The buyback fee applies and its base is unresolved** → refuse, or price an explicit upper bound
   and label it. Do not treat an unresolved fee as zero.
5. **Any instruction on our constructed route fails to decode against a pinned ABI** → refuse. This
   is the existing `FreezeViolation` discipline, not a new rule.
6. **Position size exceeds what reserves can absorb** → `L2` constrained exit; price at the
   constrained amount, never at size × quoted price.

Rule 4 and rule 6 are the ones that make the difference between a cost model and a wish.

### 4d. What the contract does not cover

- **Landing, contention, tips, slippage.** `PLAN.md` Phase 2 holds these to forward observations.
  Until then any return computed is **simulated, not executable**, and must be labelled so. This is
  the largest remaining gap by far, and no amount of decode work closes it — it needs forward data.
- **The fee tier table.** `fee_basis_points` is constant at 95 across all 93,448 in-window
  observations, so no tier lookup is exercised here. Pricing a trade whose market cap crosses a
  `FeeTier.market_cap_lamports_threshold`, or any trade outside this window, needs the `FeeConfig`
  account, of which this project holds no snapshots.
- **The 92 direct-route residuals.** Bounded at ≤0.0234 SOL per affected trade and all negative, so
  the conservative default (ignore them) overstates cost. Their cause is still open: `pfee` is now
  excluded, so they must originate in Pump's own writable accounts.
- **`Q_out` path effects** — the reserve path between entry and exit, which B9d exists to measure.

## 5. Status of the two blocking gaps

Both are closed, so the contract is no longer blocked on decode work:

| gap | status |
| --- | --- |
| buyback fee base | **RESOLVED** — `floor(fee·bps/10000)`, exact 93,253/93,253 |
| `pfee` route semantics | **RESOLVED for cost** — structurally cannot move lamports on this route |

**The 62-ABI campaign is not needed and should not be started.**

What remains before a return may be called *executable* rather than *simulated* is forward
measurement of landing, contention, tips and slippage — a Phase 2 gate against forward observations,
not a decode problem. Ratification of §4 as project policy is an owner decision; this document
proposes it and does not assume it.

No profitability claim is made and nothing here is a trading recommendation.
