# PAC V2.1 processed-inclusion calibration — implementation contract

**Status:** DESIGN FOR IMPLEMENTATION; BROADCAST DEFAULT-OFF; NO CAMPAIGN AUTHORIZED.

## Measurement target

The estimand is local monotonic time from the engine-owned decision clock immediately before build to
the first successful submit-origin `getSignatureStatuses` response for the exact sent signature whose
`confirmationStatus` is one of `processed`, `confirmed`, or `finalized` and whose `err` is null. Commitment
levels are ordered `processed < confirmed < finalized`; observing a stronger status is an admissible but
slower first observation. The polling interval and every null response are part of measured latency.

This is an observation-latency scenario, not a cryptographic proof of the earliest cluster execution.
A public RPC can observe later than the cluster, and `processed` can be on a fork. Therefore every sample
must later be independently attested at `finalized` with identical signature and wire bytes. A sample that
never finalizes remains a visible failure and cannot enter the p90.

## Campaign and sample chain

1. Commit a campaign before sampling. It binds instrument, V2.1 seal, exact fee payer, distinct submit and
   verifier HTTPS origins, start time, maximum transaction count, maximum lamports, 100 ms polling cadence,
   30-second processed deadline, and the memo-only transaction profile.
2. Each unique transaction contains one deterministic memo challenge over campaign id, attempt index, and
   previous successful sample id. Broadcast refuses until the fixed campaign artifact is committed cleanly
   after the current seal. Persist the exact signed wire atomically before sending its first byte; an
   uncertain send is a visible failed attempt and its signature is never reused.
3. Preserve exact wall and monotonic clocks for decision, build start, sign done, send start, send ack and
   processed observation. Preserve the signed wire, send request/response, and every status-poll request,
   response, start/end clock and digest.
4. Earlier successful poll responses must have a null status. The terminal processed sample must be the
   first recorded non-null status, have null `err`, exact signature identity, an exact positive slot, and a
   declared confirmation status in the ordered set. RPC/program errors, timeout and ambiguous schemas are
   durable failure outcomes; they are never omitted or rewritten as latency.
5. Before send, preserve the exact `getFeeForMessage` request/response for the signed message. An
   independent verifier later calls `getTransaction(..., commitment=finalized, encoding=base64)` for
   every processed success. It must recover the identical wire bytes, signature, fee payer, successful meta
   and processed-observed slot, and finalized `meta.fee` must equal the pre-send quote. Missing/different/
   fork-dropped samples remain failures.

Activation requires at least 100 independently finalized processed successes plus every campaign failure.
The nearest-rank p90 uses only those authenticated successes; failure rate is separately mandatory and a
campaign with any unclassified send is refused. This is deliberately stricter than merely collecting 100
transactions.

## Safety rails

- Dry-run is the default and performs no RPC send.
- Broadcast requires an explicit flag, exact pre-committed keypair and origins, transaction-count cap, and
  campaign-wide lamport cap including resumed samples.
- Only the existing parsed-and-ed25519-verified single-signer SPL Memo profile is permitted.
- Resume validates the full attempt hash chain and never resends a persisted signature.
- No strategy, wallet, or order instruction exists in the calibration module.

## Primary-source verification

Accessed 2026-08-29:

- Solana `getSignatureStatuses`: `confirmationStatus` is returned per signature and may be `processed`,
  `confirmed`, or `finalized`; the replacement guidance for deprecated `confirmTransaction` explicitly
  requires a null `err` and orders those levels.
  <https://solana.com/docs/rpc/http/getsignaturestatuses>
  <https://solana.com/docs/rpc/deprecated/confirmtransaction>
- Solana transaction-confirmation guidance warns that `processed` can observe a fork and recommends a
  stronger commitment for safety. V2.1 therefore measures processed observation for timing but separately
  requires independent finalized byte identity.
  <https://solana.com/uk/developers/cookbook/transactions/confirmation>
- Finalized transaction attestation uses the official `getTransaction` contract.
  <https://solana.com/docs/rpc/http/gettransaction>
