# B19a — wallet, treasury and emergency-control architecture

**Status:** architecture only; unimplemented and operator-unratified.

This document creates no wallet, address, seed, key, signer, transaction, endpoint or financial
limit. It authorizes no signing, submission, funding or trading. Phase 5b and every Phase 6 gate in
`PLAN.md` remain open.

## Objective

If research is eventually promoted, a defect or compromise in data ingestion, strategy code, the
operator console or transaction construction must not gain custody of treasury funds or obtain an
unbounded ability to spend. The safest failure is no transaction.

The design separates five trust zones:

1. **Research and decision services** observe data and produce immutable proposals. They hold no
   signing material and cannot submit transactions.
2. **Independent risk service** evaluates an exact proposal and exact portfolio/health snapshot. It
   approves that exact order or rejects it; it cannot resize it. Approval is not a signature.
3. **Transaction builder** may construct only the route authorized by the approved proposal. It
   holds no private key and cannot change the proposal, limits or destination.
4. **Isolated signer** is the only component able to authorize the dedicated operating wallet. It
   verifies the complete transaction against an independently loaded policy before signing.
5. **Treasury and operator control** remain outside all four services. Treasury funding and
   withdrawal are manual, and emergency state is owned by a minimal independent control process.

The browser console stays read-only. It displays signed or hashed state snapshots but has no wallet
connection, secret, write route or direct kill-switch mutation. A separate authenticated local
operator mechanism owns emergency state; adding that mechanism is a later implementation task.

## Funds and custody boundaries

- The **treasury wallet** and **operating wallet** are distinct. The treasury wallet is never loaded
  by the bot host.
- The operating wallet is dedicated to this system, intentionally balance-limited and never reused
  as a creator, personal, exchange-deposit or research identity.
- There is no automatic treasury top-up. Exhausting the operating balance stops trading.
- Withdrawals are manual to a separately verified treasury destination. Strategy code cannot choose
  or alter that destination.
- **"Manual" needs resolving against zone 4, and the two readings differ in consequence.** If the
  isolated signer is the only thing that can authorize the operating wallet, a withdrawal is not
  fully manual — it is an operator-initiated request that still passes the signer, which is the
  safer reading and the one this document adopts. The alternative, an operator key held outside the
  signer, would contradict zone 4 and create a second signing path with no policy over it. So:
  withdrawals are **operator-initiated and signer-enforced**, with the destination drawn from the
  ratified policy rather than from the request, and the signer refusing any destination not in it.
- No component may infer common ownership merely because two addresses fund, trade or co-occur.
  The custody design knows its configured addresses; wallet-intelligence features do not receive
  that private ownership fact.
- **The operating wallet's own activity is public, and the rule above cuts both ways.** Forbidding
  reuse keeps the wallet from being linked to other identities, but its trades are visible from the
  first one, and anyone may treat *it* as a signal. B16d measured exactly this from the other side:
  whether a follower could trade a public wallet's observable behaviour. It found the observable
  edge dominated by selection rather than information, and every priced variant negative — which is
  a reason not to assume followers are harmless, not a reason to assume they are. Wallet rotation,
  if ever adopted, is a decision about this exposure and not only about compromise.
- Wallet creation method, custody medium, recovery material, operators and all numeric limits remain
  undecided. They require a separate recorded decision and must never be stored in this repository.

## Exact authorization chain

Every boundary consumes an immutable object and emits a new immutable object:

```text
observation + evidence hashes
  -> proposal hash
  -> independent risk-decision hash
  -> transaction-message hash
  -> signer policy decision
  -> signature (future phases only)
  -> submission-attempt record
  -> landing/finalization/reconciliation records
```

The signer must bind the full transaction message to the approved proposal and risk decision. A
match on mint, amount or program alone is insufficient. The checked message includes, at minimum:

- recent blockhash or nonce choice and expiry;
- payer and every account key, including lookup-table-expanded keys;
- every program id and instruction payload;
- compute-unit limit and compute-unit price;
- Jito tip amount and destination when applicable;
- token mint, bonding curve, direction and exact maximum wallet outlay;
- ATA creation and rent exposure;
- allowed destination for any withdrawal-like movement;
- proposal, risk-decision, policy-version and evidence hashes.

Any extra instruction, unknown program, writable account not authorized by policy, changed order,
changed fee/tip, stale decision, missing hash or ambiguous decode refuses signing. The signer never
repairs or silently removes an instruction.

## Independent enforcement

Risk limits cannot rely solely on the caller that requested the trade. Before signing, the isolated
boundary independently checks a ratified policy snapshot covering:

- operating-wallet maximum balance and maximum transaction outlay;
- maximum order, pending exposure, total exposure and open positions;
- creator concentration, daily realized loss and portfolio drawdown;
- evidence and decision age in both slots and wall-clock time;
- kill switch and emergency state;
- exact allowed programs, routes and instruction families;
- fee, tip, rent and retry ceilings;
- duplicate proposal and duplicate transaction-message hashes.

No number is selected here. Until separately ratified, every financial cap remains unknown and the
signer design therefore remains disabled. Unknown never means zero or infinity.

**The policy snapshot needs its own integrity, and a version hash is not it.** The authorization
chain binds a `policy-version` hash into the checked message, which proves the builder and signer
are talking about the same policy. It does not prove that policy was ever ratified — a compromised
builder supplies a consistent pair, and consistency is not authorization. The signer must therefore
carry an owner-ratified policy identity it loaded independently, and refuse any policy hash absent
from it. Without that, "independently loaded policy" means only "loaded twice".

## Emergency-state owner

The missing writer identified by B17c belongs in a minimal local control service, separate from the
read-only browser and from strategy code.

Required semantics for a future implementation:

- Default at process start, unreadable state, invalid signature, clock conflict or stale heartbeat:
  **engaged**.
- Engaging the switch requires no strategy, RPC or signer availability and immediately blocks new
  signatures.
- Clearing it requires explicit authenticated operator action, a reason, a monotonically increasing
  generation, and a durable append-only receipt. It never auto-clears on restart or timeout.
- The risk service and signer each verify the state independently. A disagreement means engaged.
- Existing positions may be observed while engaged; exit authority requires its own pre-ratified
  emergency policy and must not become an unrestricted transfer path.
- The console consumes a read-only snapshot of this state. It does not own or mutate it.

## Retry and replay boundary

- A retry is a new attempt record under the frozen B17b contract, never an incremented counter that
  erases the previous attempt.
- A fresh blockhash produces a new transaction-message hash and requires the signer to re-check the
  unchanged proposal and risk decision for freshness.
- Retrying may not raise fees or tips beyond the approved envelope. Adaptive fee escalation requires
  an independently ratified rule and is absent until then.
- A landed, finalized, expired, refused or ambiguous attempt cannot be replayed as if it were new.
- Unknown landing state blocks conflicting replacement orders until reconciliation or expiry rules
  establish safety.

## Compromise limits

| compromised component | maximum intended consequence | must remain impossible |
|---|---|---|
| recorder/data provider | stale or malicious proposal, then refusal by evidence/risk gates | custody or signing |
| model/strategy | many bad proposals, all bounded and independently checked | changing limits or transaction bytes |
| operator console | misleading display if snapshot validation also fails | writing emergency state, signing or submitting |
| risk service | false approval within signer-enforced hard policy | arbitrary program/account access or treasury custody |
| transaction builder | malformed message, then signer refusal | signing its own message |
| signer host | **loss bounded by the operating-wallet balance alone** | access to treasury wallet or automatic refill |
| RPC/Jito route | censorship, delay, replay attempt or false receipt | changing a signed transaction or learning keys |

This table is a design target, not a demonstrated security property. Each row needs adversarial tests
in Phase 5b before it becomes a claim.

**On the signer-host row specifically.** An earlier version of this table said the loss was bounded
by "operating-wallet balance **and signer policy**". It is not. An attacker holding the signer host
holds the key and the policy file together, and can sign anything the wallet can pay for; a policy
enforced by the compromised component is not a bound on that component. The balance is the only real
limit, which is the argument for keeping the operating balance small and is why "intentionally
balance-limited" above is load-bearing rather than tidy. Every other row's bound is enforced by a
component the attacker does *not* hold, and those bounds stand.

## Lifecycle and recovery

- Key rotation, host replacement and wallet retirement require reconciling every pending signature
  and token account first.
- Secrets are supplied only to the isolated signer through an owner-approved mechanism. They never
  enter command lines, logs, state snapshots, crash reports, repository files or browser storage.
- Backups and recovery shares, if any, are created and tested outside the bot host. Their design is
  an owner/legal/security decision still open.
- Loss, suspected exposure, policy drift, program upgrade, unexplained balance movement or
  reconciliation failure engages emergency state and prevents new signatures.
- The operating wallet is not reused after suspected compromise.

## Promotion evidence still required

Before implementation or funding:

1. B11 and subsequent model gates support promotion to shadow mode.
2. Shadow operation demonstrates stable decisions across multiple regimes.
3. B17b-conforming **execution** records exist and reconcile. As of commit `a6245b1`,
   B17b-conforming **shadow** records exist (`scripts/b18a_shadow_record.py`) and the failure
   vocabulary is exercised by injected faults (`scripts/b18b_failure_rehearsal.py`). Neither is an
   execution record: nothing has been built, signed or sent, `landed` is unreachable, and the
   rehearsal records are marked as evidence of nothing. This gate is **not** satisfied by them.
4. Phase 5b exercises construction, signing, ATA/rent, expiry, retry and emergency behavior using
   free devnet SOL; no devnet profit claim is permitted.
5. Independent review verifies signer policy, custody, recovery and compromise limits.
6. Netherlands/EU legal and tax advice is obtained.
7. The owner explicitly ratifies every numeric limit and authorizes wallet creation and funding.

Until all seven hold, this document remains architecture and nothing more.

## Independent audit, 2026-08-07 (Claude, handoff 194)

Audited against `PLAN.md`, `DECISIONS.md`, `scripts/b12a_risk_governor.py` and the frozen
`B17B_EXECUTION_MEASUREMENT_CONTRACT.json`. The design held up; four defects and one omission were
corrected in place, each marked in the section it belongs to.

**Corrected:**

1. **The signer-host compromise row overclaimed its bound.** It credited signer policy with limiting
   the loss when an attacker holding the host holds the policy too. Narrowed to the wallet balance.
2. **The policy snapshot had no ratification binding.** A `policy-version` hash proves builder and
   signer agree; it does not prove the policy was authorized. Added the requirement that the signer
   hold an owner-ratified policy identity independently and refuse anything absent from it.
3. **"Manual withdrawals" contradicted zone 4.** Resolved to operator-initiated and
   signer-enforced, with the destination from the ratified policy rather than the request.
4. **Promotion gate 3 had become ambiguous.** Shadow records now exist; execution records do not.
   Qualified so the gate cannot be read as already met.

**Added:** the operating wallet's own activity is a public signal, cross-referenced to B16d, which
measured the follower side of exactly that question.

**Checked and found accurate, so recorded rather than changed:**

- "the risk service cannot resize" matches `b12a_risk_governor.py:485-487`, which returns
  `order_was_resized: False` and `resizing_is_not_available`. The claim is code-backed.
- "unknown never means zero or infinity" matches the frozen contract's governing rule exactly.
- "a retry is a new attempt record under the frozen B17b contract" matches both the contract and
  `b18a`/`b18b`, where every attempt is its own record and duplicates are refused.
- The emergency defaults are fail-closed throughout: engaged at start, on unreadable state, on
  invalid signature, on clock conflict, on stale heartbeat, and on disagreement between verifiers.
  This matches the project's standing rule that absence is refusal, never a permissive default.
- Wallet equality is kept distinct from owner identity, including the subtle direction — our own
  knowledge of our own addresses must not leak into wallet-intelligence features.

**Not done, and outside this audit's authority:** no wallet, signer or control service implemented,
no limit chosen, no secret touched, and no numeric value proposed anywhere.
