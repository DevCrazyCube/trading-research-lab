# Free RPC endpoints, measured — for the next collection, not this one

Measured while B11a's block phase was running at ~2.6 calls/s on paid Chainstack, because the
question "can a second endpoint halve this" deserved a number rather than an opinion.

Target slot 436,100,000 — mid-window, ~10 days old at the time. Archival access is the filter that
eliminates most free tiers: they serve recent blocks and drop history.

| endpoint | archival | rate | note |
|---|---|---|---|
| `api.mainnet-beta.solana.com` | **yes** | **2.92 calls/s** @ 4 workers, 0 errors | official public; explicitly not-for-production |
| `solana-rpc.publicnode.com` | no | — | "Block 436100000 cleaned up, does not exist on node" |
| `solana.drpc.org` | no | — | HTTP 400, chain not available |
| `rpc.ankr.com/solana` | no | — | HTTP 403, key required |
| blockdaemon try-rpc | no | — | DNS does not resolve |

Latency at 1/2/4 workers: 588 / 454 / 563 ms. Concurrency past 2 buys little, the same
server-side queueing shape the paid endpoint shows.

## Why it was NOT adopted for B11a

Roughly a 2x throughput gain, ~10 hours saved on the ~22 remaining. Against that:

- **Provenance.** Every response is preserved byte-for-byte with a single recorded endpoint. Two
  sources means each stored response must say which one served it, or the artifact claims one
  origin for data that had two. That is a schema change to a manifest-pinned file — full review,
  re-attestation, restart.
- **The restart discards ~31,000 blocks already fetched**, about 3.5 hours, so the net saving is
  ~6 hours on a ~22 hour job.
- **A 30-call probe is not a sustained-load test.** The public endpoint is documented as
  not-for-production, and a throttle appearing three hours in would quarantine the run and cost
  more than the gain.

The owner's call was to let it finish. Recorded here so the next collection — if the population is
larger and the saving proportionally bigger — starts from a measurement rather than a guess.

## What would actually be needed

Per-response endpoint provenance in the artifact, so a mixed collection stays auditable. That is
the whole change; the fetching itself is trivial. The evidence model is the hard part, as usual.
