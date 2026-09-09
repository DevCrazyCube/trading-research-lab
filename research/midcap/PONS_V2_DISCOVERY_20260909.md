# Pons V2 contract discovery and curve-capture readiness

Author: Codex. 2026-09-09. **NO_TRADE; engineering development observations only.**
No existing Robinhood return tape was opened. The requests below inspect primary
source, contract identities/settings, and launch-event structure, not price returns.

## Verified on the public RPC

At block **58,835,011**, chain ID 4663:

- Current README factory: `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e`.
  Runtime length 24,177 bytes; SHA256
  `226a042e6d68a69a6038d4fda211925b03eb5299399434b87a7877f79f6e3848`.
- `launchEnabled()` returned true; `snipeTaxStartBps()` 9,900;
  `snipeTaxSeconds()` **3**, not 5 and not the source initializer 15.
- `memeHook()` returned `0xe5e702641ea86f4ae6cc3cdaed2b886f976be044`;
  `poolManager()` returned `0x8366a39cc670b4001a1121b8f6a443a643e40951`.
- The previously indexed factory `0x7E1EAbd52Ae29598e6483F72dCf1a70b14284dB8`
  has 22,757 runtime bytes and returned `launchEnabled=false`. A later tax getter
  call returned an RPC error, not zero tax. That is an older deployment, not a
  substitute target for new launches.
- The current factory returned 727 TokenLaunched-shaped logs in the inclusive
  20,001-block development slice ending at that block. This is not a universe
  estimate, graduation rate or profitable result. Raw response SHA256:
  `2002173b0905db083a4191fb847a981f6e1ea6948d5586629fabfb34f5503c9b`.

One mechanically selected curve identity was checked at block **58,836,054**:

- Curve `0x1792daa72f78d582e1b7f1ffd4475d13aa6d496f`.
- Token `0x309bbc15efb8fa1eaaae6a9f23f83025c8ccb6bf`.
- Its `factory()` and `token()` matched the selected factory launch log.
- `pairToken()` returned zero address (native quote); `feeBps()` and
  `creatorTaxBps()` each returned 100. Do not apply a universal 1% total toll.
- Runtime SHA256 `f98ee27d4ff3d33545df6651c5129420d8f4d737a0efb1d637b15c6cbfa46aa7`.
- The attempt to fetch this curve's historical logs returned HTTP 429. No curve
  trade tape, tax-decay return, or second-curve attestation was established.

Raw public observations are under `research/midcap/rh_curve_private/`:
`discovery_network_20260909`, `rpc_discovery_20260909`, `curve_identity_20260909`.
Every request has response bytes/hash and timestamps; failed requests remain visible.
Earlier sandbox DNS refusal is preserved separately. No .env or credentials were read.

## Primary-source conflict — unresolved, not silently waived

Pinned project commit: **0445a2c39df623169dc4cf3a939308ef4e0f7a60**,
reported commit time 2026-09-09 19:19:43 UTC. This supersedes unpinned indexed README
addresses only as a source reference; the on-chain observations above stand separately.

The retained factory source calls `PonsV2BondingCurve(curve).exemptFromSnipeTax`.
The retained curve source from the same commit contains no corresponding method
and no `currentSnipeTaxBps` method. It cannot presently serve as a verified exact
model of the deployed tax logic. Factory defaults do not override per-launch snapshots.
Blockscout API verification returned a Cloudflare HTTP403, retained as a refusal.
The product documentation endpoint returned a region restriction in browsing; it was
not bypassed. Public GitHub source and public RPC reads were used independently.

**Open gates:** deployed ABI/source correspondence; actual curve tax snapshot and
recipient exemptions; canonical launch provenance and pool-manager/hook mapping;
v4 execution and migration behavior; state checkpoints; full fee/rounding/gas model;
retail receipt-to-landing measurement. No public mempool does not itself imply fair
ordering, zero private flow, zero MEV, or a profitable retail entry.

## Implemented capture integration (not a live strategy)

`scripts/rh_curve_capture.py` derives distinct query plans from retained source shapes:

- factory `TokenLaunched(address,address,address,address,uint256,uint256)`;
- curve `CurveBuy(address,address,uint256,uint256,uint256,uint256)`;
- curve `CurveSell(address,address,uint256,uint256,uint256,uint256)`;
- curve `CurveCompleted(address,uint256,uint256)`.

These do not match v3 Swap. Factory-address membership and curve source-shaped events
remain separately labeled; a malicious contract can emit an identical topic. The
module retains raw response bytes before derived indexing, keeps block/transaction/log
coordinates and hashes, records errors/gaps without cursor advancement, and never
calls the indexed records canonical merely because the topic matches.

The retained real factory response successfully replays 727 records through this
extension into `factory_shape_replay_20260909.sqlite`. Pure helper tests pass.
The live `rh_tape.py` was not edited concurrently with its owner. Integrate into
that existing shared-budget reader with separate stream cursors and raw PoolCreated
retention; do not launch another uncoordinated poller after the observed 429.
This is **integration-ready raw infrastructure**, not continuous curve capture,
an exact tax decoder, or an executable-return evaluator.

## Robinhood preregistration boundary

**Decision:** no financial preregistration is activated here. The owner's instruction
requires approximately 24 hours of collection before writing it, and writing it
before opening the outcome tape. Neither a completed 24-hour curve collection nor
a verified curve tax/execution model exists yet. This note is not a replacement
preregistration, not an amended sealed rule, and not permission for an early read.

Prepare the eventual retail-entry experiment around a declared non-exempt recipient,
fixed quote notional, actual rule/roster/source availability, next executable state
after measured latency, exact per-launch tax snapshots, all failed/unavailable exits,
independent pipeline placebo, mint/session/funding dependence, and fixed untouched
entry weeks. The original seven-point harness and promotion gates still apply.
Choose/freeze numeric cells only before the eligible future cohort; no tax-window
grid is being fitted to the discovered launches. Existing development observations
cannot become the untouched evaluation by renaming them.

## Sources (accessed 2026-09-09)

- [Pinned Pons README](https://github.com/ponsdotdev/ponsfamily/blob/0445a2c39df623169dc4cf3a939308ef4e0f7a60/README.md).
- [Pinned factory source](https://github.com/ponsdotdev/ponsfamily/blob/0445a2c39df623169dc4cf3a939308ef4e0f7a60/contractsV2/src/v2/PonsV2LaunchFactory.sol).
- [Pinned curve source](https://github.com/ponsdotdev/ponsfamily/blob/0445a2c39df623169dc4cf3a939308ef4e0f7a60/contractsV2/src/v2/PonsV2BondingCurve.sol).
- [Robinhood primary network reference](https://docs.robinhood.com/chain/connecting/).
